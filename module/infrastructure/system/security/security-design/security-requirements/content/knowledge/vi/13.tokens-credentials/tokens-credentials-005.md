# Token expiry

## 1. Token expiry là một giới hạn truy cập, không chỉ là trường thời gian

**Token expiry** là quy tắc xác định thời điểm một token không còn được chấp nhận làm bằng chứng cho hành động thuộc phạm vi của nó. Token có thể dùng để gọi API, làm mới quyền truy cập, đặt lại mật khẩu, xác nhận địa chỉ email hoặc truy cập một tài nguyên trong thời gian giới hạn.

Một token chứa thời điểm hết hạn chưa đủ để chứng minh yêu cầu bảo mật đã được thực thi. Thành phần quyết định quyền phải kiểm tra thời hạn bằng nguồn thời gian phù hợp, xử lý đúng biên và không cho cache hay đường gọi khác tiếp tục sử dụng token sau giới hạn đã cam kết.

Ví dụ, access token hết hạn sau năm phút nhưng gateway cache quyết định cho phép trong mười phút. Nếu gateway không kiểm tra lại thời hạn, quyền truy cập có thể kéo dài hơn năm phút. Yêu cầu “token TTL = 5 phút” đúng ở nơi phát hành nhưng sai ở nơi thực thi.

Đặc tả tốt cần trả lời:

- Token thuộc loại nào, dùng cho hành động nào và tại tài nguyên nào?
- Ai đặt thời hạn, dựa trên chính sách và giới hạn ủy quyền nào?
- Tại thời điểm nào của request hệ thống kiểm tra token còn hạn?
- Clock skew, cache và kết nối dài có làm kéo dài thời gian chấp nhận không?
- Hết hạn, refresh, thu hồi và kết thúc phiên khác nhau thế nào?
- Bằng chứng nào cho thấy mọi điểm thực thi đều áp dụng đúng quy tắc?

### 1.1. Vì sao thời hạn token quan trọng?

Token bị lộ có thể được sử dụng trong phạm vi mà cơ chế xác thực và phân quyền cho phép. Thời hạn ngắn làm giảm khoảng thời gian sử dụng **một token cụ thể** nếu không có cách lấy token mới. Nó không tự chặn kẻ vẫn kiểm soát refresh token, credential nguồn hoặc workload được phép liên tục xin token.

Vì vậy, token expiry là một lớp kiểm soát. Nó phải phối hợp với phạm vi quyền, audience, lưu trữ an toàn, thu hồi, bảo vệ refresh credential và giám sát. Không thể bù cho một token quyền quá rộng bằng cách chỉ giảm TTL.

## 2. Phân biệt các khái niệm về thời gian và vòng đời

| Khái niệm | Ý nghĩa | Điểm cần lưu ý |
| --- | --- | --- |
| Thời điểm phát hành | Lúc bên phát hành tạo token theo nguồn thời gian của mình | Không tự chứng minh token được dùng từ lúc đó hoặc còn hiệu lực |
| Not-before | Thời điểm sớm nhất được chấp nhận theo hợp đồng | Phải được kiểm tra nếu thuộc profile token đang dùng |
| Expiry | Thời điểm kết thúc khả năng chấp nhận token theo quy tắc | Cần định nghĩa chính xác phép so sánh và clock tolerance |
| TTL/lifetime của token | Khoảng thời gian hiệu lực được cấp | Không đồng nghĩa với thời gian còn lại ở lúc client nhận token |
| Idle timeout | Giới hạn không hoạt động của phiên hoặc grant | Thường cần trạng thái bổ sung; không tự xuất hiện từ một access token cố định |
| Absolute timeout | Giới hạn cuối của phiên hoặc ủy quyền dù có hoạt động | Refresh không được vượt nếu chính sách ràng buộc token vào giới hạn này |
| Revocation | Thu hồi trước thời điểm hết hạn dự kiến | Cần cơ chế truyền quyết định tới nơi thực thi |
| Rotation | Thay token/credential bằng giá trị mới | Không tự chứng minh bản cũ đã hết hạn hoặc bị thu hồi |

Logout ở một trình duyệt không mặc nhiên làm mọi access token đã cấp mất hiệu lực. Ngược lại, một access token hết hạn không nhất thiết có nghĩa phiên đăng nhập hoặc refresh grant đã kết thúc. Phải xác định từng vòng đời thay vì dùng chung một từ “session hết hạn” cho mọi trường hợp.

## 3. Biểu diễn và kiểm tra thời hạn

### 3.1. Token tự chứa và token tham chiếu

Với token tự chứa được bảo vệ toàn vẹn, thời hạn có thể nằm trong payload. Thành phần xác thực phải kiểm tra tính xác thực/toàn vẹn và các ràng buộc cần thiết, không chỉ giải mã payload rồi tin trường thời gian.

Với token tham chiếu hay opaque token, client có thể chỉ thấy một chuỗi không mang ý nghĩa thời gian. Server hoặc dịch vụ xác thực tra cứu trạng thái/token metadata để biết hạn dùng. Hình thức opaque không làm thời hạn kém quan trọng; nguồn chuẩn chỉ nằm ở nơi khác.

Hai mô hình cần đạt cùng một điều: token không được chấp nhận ngoài khoảng hiệu lực đã quy định, trừ phần dung sai thời gian được chính sách cho phép và đã tính vào cam kết.

### 3.2. Các trường thời gian trong ví dụ JWT

Một payload minh họa:

```json
{
  "iss": "https://identity.example.invalid",
  "sub": "account-274",
  "aud": "orders-api",
  "iat": 1700000000,
  "nbf": 1700000000,
  "exp": 1700000300,
  "scope": "orders.read"
}
```

Đây chỉ là dữ liệu minh họa, không phải token hoàn chỉnh và không có giá trị xác thực. Trong cách biểu diễn thời gian JWT này, giá trị thời gian dùng số giây tính từ mốc Unix, không phải số mili giây. Hai giá trị `iat` và `exp` ở ví dụ cách nhau 300 giây.

Các điểm cần đặc tả:

- `iat` biểu diễn thời điểm phát hành; chỉ có `iat` không tạo ra một hạn dùng.
- `nbf` biểu diễn thời điểm bắt đầu chấp nhận khi profile yêu cầu sử dụng trường này.
- `exp` biểu diễn thời điểm hết hạn và phải được kiểm tra theo profile của ứng dụng.
- Profile token của ứng dụng phải nói rõ trường nào bắt buộc. Không suy ra rằng mọi token mang định dạng JWT đều tự có đủ các trường đó.
- Chuỗi ngày tháng, số vượt miền biểu diễn hoặc đơn vị sai phải được xử lý theo schema đã chốt, không ép kiểu tùy tiện để tiếp tục xác thực.

Nếu profile yêu cầu `exp`, token thiếu trường này phải bị từ chối. Nếu profile còn yêu cầu `iat` và lifetime tối đa, cần kiểm tra cả sự hợp lệ của mốc phát hành, thứ tự thời gian và khoảng lifetime; không chỉ kiểm tra token có chữ ký hợp lệ.

### 3.3. Biên hết hạn phải rõ ràng

Giả sử không có dung sai thời gian và chính sách dùng khoảng hiệu lực nửa mở:

```text
Token hợp lệ về thời gian khi:
    nbf <= now < exp

Tại now == exp:
    token đã hết hạn, không được dùng để cấp quyền.
```

Đây là quy tắc cần được phản ánh nhất quán trong thư viện, gateway và các dịch vụ liên quan. Sai lệch giữa `>` và `>=` ở đúng biên có thể làm các thành phần đưa ra quyết định khác nhau.

Độ phân giải cũng quan trọng. Nếu token dùng giây nhưng phép kiểm tra dùng mili giây, phải chuyển đổi có kiểm soát. Không nhân/chia sai đơn vị, làm tròn không nhất quán hoặc dùng kiểu số khiến timestamp bị tràn. Profile có thể chọn số giây nguyên trong miền giới hạn cụ thể; đó là ràng buộc của profile, không nên coi là thuộc tính mặc nhiên của mọi hệ thống token.

## 4. Clock skew và leeway phải nằm trong mô hình rủi ro

### 4.1. Dung sai có thể kéo dài cửa sổ chấp nhận

Đồng hồ bên phát hành và bên kiểm tra có thể lệch nhau. Một hệ thống có thể cho phép dung sai `L` để giảm lỗi do chênh lệch nhỏ. Với quy tắc minh họa:

```text
Chấp nhận về thời gian nếu:
    now_local >= nbf - L
    và now_local < exp + L
```

Áp dụng dung sai như trên cho phép chấp nhận sớm hơn `nbf` và muộn hơn `exp`. Có hệ thống chọn chính sách khác cho mỗi biên; yêu cầu phải nói rõ cách áp dụng và kiểm tra cấu hình thực tế của thư viện.

Không được ghi “token tuyệt đối không dùng được sau exp” trong khi cấu hình lại cho phép dùng thêm 30 giây. Cần định nghĩa cam kết là expiry danh nghĩa hay thời điểm từ chối có tính dung sai.

### 4.2. Phân biệt leeway cấu hình với sai lệch đồng hồ thực tế

Giả sử:

```text
Thời điểm exp theo mốc thời gian chuẩn: 10:05:00
Leeway khi kiểm tra: 30 giây
Đồng hồ validator chậm so với mốc chuẩn: 20 giây
```

Validator dùng `now_local < exp + 30 giây` có thể tiếp tục chấp nhận gần tới 10:05:50 theo đồng hồ chuẩn. Đây là hệ quả của hai yếu tố cộng lại: dung sai được cấu hình và validator chạy chậm.

Một ước lượng cho giới hạn chấp nhận muộn ở phép kiểm tra này:

```text
Mốc chấp nhận muộn nhất theo thời gian chuẩn
    <= exp + leeway + độ chậm đồng hồ tối đa được bảo đảm
```

Ước lượng chỉ hữu ích khi hệ thống thật sự kiểm soát được sai lệch đồng hồ và không có cache/đường xử lý khác kéo dài thêm. Nếu đồng hồ lệch không giới hạn hoặc bị chỉnh lùi tùy ý, TTL danh nghĩa không tạo ra một giới hạn thực tế đáng tin.

Yêu cầu vận hành cần quy định nguồn đồng bộ thời gian, ngưỡng lệch được chấp nhận, tín hiệu cảnh báo và hành vi khi không còn tin được đồng hồ. Không tự bỏ kiểm tra expiry khi đồng hồ có vấn đề. Đồng hồ đơn điệu có thể hữu ích để đo khoảng thời gian cục bộ, nhưng không tự thay thế cách đối chiếu timestamp tuyệt đối được phát hành bởi hệ thống khác.

## 5. Chọn lifetime theo mục đích sử dụng

Không có một TTL phù hợp cho mọi token. Thời hạn cần cân bằng phạm vi ảnh hưởng khi bị lộ, khả năng thu hồi, yêu cầu thao tác, tần suất xin token và khả năng hoạt động khi thành phần phát hành gặp sự cố.

| Loại token | Câu hỏi quyết định lifetime | Ví dụ yêu cầu bổ sung |
| --- | --- | --- |
| Access token gọi API | Quyền mạnh đến đâu, tài nguyên nhạy cảm thế nào, có thu hồi sớm được không? | Giới hạn audience/scope và kiểm tra expiry tại API |
| Refresh token | Grant/phiên được kéo dài tới đâu, có idle timeout và absolute timeout không? | Không phát hành token mới từ refresh credential hết hạn/đã thu hồi |
| Token đặt lại mật khẩu | Người dùng cần bao lâu để hoàn tất và hậu quả nếu link bị lộ là gì? | Chỉ dùng cho đúng mục đích, tài khoản và số lần được phép |
| Token xác nhận email | Xác nhận hành động nào và điều gì xảy ra nếu thông tin đã thay đổi? | Ràng buộc giao dịch, không tái sử dụng sai ngữ cảnh |
| Token tải tài nguyên | Hạn dùng áp dụng khi bắt đầu tải hay xuyên suốt quá trình truyền? | Hạn chế tài nguyên và quy định đối với kết nối đang mở |
| Token workload | Workload có thể tự xin token mới không và nguồn identity còn đáng tin không? | Ràng buộc môi trường chạy, quyền tối thiểu và đường thu hồi |

Ví dụ một dự án có thể chọn access token tối đa năm phút, token reset mật khẩu tối đa 20 phút và refresh grant có absolute lifetime bảy ngày kèm idle timeout 24 giờ. Đây chỉ là các giá trị minh họa, không phải yêu cầu chuẩn áp dụng cho mọi hệ thống.

Tính dùng một lần là yêu cầu độc lập với expiry. Token reset mật khẩu còn hạn không nên được phép thực hiện lại hành động đã hoàn tất nếu hợp đồng quy định một lần sử dụng. Kiểm tra thời gian và đánh dấu đã dùng cần phối hợp an toàn khi có hai request đồng thời.

## 6. Quy tắc tại thời điểm phát hành

### 6.1. Bên phát hành quyết định hạn dùng từ chính sách đáng tin

Client có thể đề nghị thời hạn hoặc gửi loại thao tác, nhưng không được tự chọn một `exp` dài hơn quyền được cấp rồi yêu cầu server ký nguyên payload đó. Bên phát hành phải xác thực chủ thể, xác định phạm vi và áp dụng chính sách thời gian tương ứng.

Một công thức khái niệm:

```text
exp_new <= min(
    thời_điểm_cấp + lifetime_tối_đa_của_loại_token,
    giới_hạn_tuyệt_đối_của_phiên/grant nếu hợp đồng yêu cầu ràng buộc,
    thời_điểm_kết_thúc_ủy_quyền liên quan theo chính sách
)
```

Cần xác định mốc nào thật sự là giới hạn của quyền được ủy quyền. Không phải mọi bằng chứng đầu vào ngắn hạn đều bắt buộc có cùng hạn dùng với token đầu ra: một assertion có thể chỉ được dùng trong cửa sổ ngắn để đổi lấy token theo một chính sách riêng. Ngược lại, nếu grant chỉ cho phép truy cập đến 17:00 thì hệ thống không được tự cấp token làm quyền đó kéo dài quá 17:00 trái hợp đồng.

### 6.2. Kiểm tra token bị phát hành sai chính sách

Chữ ký hợp lệ không có nghĩa token đáp ứng mọi chính sách của tài nguyên. Một token có `exp` quá xa, `iat` nằm bất thường trong tương lai hoặc lifetime lớn hơn mức được duyệt có thể phản ánh lỗi cấu hình hoặc phát hành sai.

Nếu profile quy định lifetime tối đa và các trường cần thiết, validator phải kiểm tra chúng theo hợp đồng. Chỉ kiểm tra `exp - iat <= 300` chưa đủ nếu chấp nhận `iat` rất xa trong tương lai và không kiểm tra khoảng thời gian được phép tại thời điểm hiện tại.

Mỗi loại token cần có schema và giới hạn rõ ràng. Token thiếu trường bắt buộc, sai kiểu, thời gian đảo ngược hoặc vượt miền số phải bị từ chối thay vì được xử lý bằng giá trị mặc định vô hạn.

## 7. Refresh và expiry không phải cùng một thao tác

### 7.1. Cấp token mới không sửa thời hạn của token cũ

Với token tự chứa đã được bảo vệ toàn vẹn, không thể chỉ sửa `exp` trong payload rồi tiếp tục coi token cũ là hợp lệ. Phải phát hành token mới với bảo vệ tương ứng và chính sách mới được kiểm tra.

```text
Access token A1: cấp lúc T0, hết hạn tại T1.
Refresh hợp lệ: phát hành access token A2, hết hạn tại T2.

A1 vẫn có vòng đời riêng.
A2 không tự làm A1 mất hiệu lực.
Việc A1/A2 có được cùng tồn tại hay không phải theo chính sách.
```

Ở mô hình tham chiếu, server có thể hỗ trợ cập nhật trạng thái hạn dùng, nhưng đó phải là thao tác được cấp phép, được audit và bị giới hạn bởi vòng đời grant/phiên. Không kéo dài token chỉ vì client gửi lại giá trị đang giữ.

### 7.2. Refresh không được xóa giới hạn tuyệt đối

Nếu refresh token có idle timeout, việc sử dụng hợp lệ có thể cập nhật mốc hoạt động theo hợp đồng. Điều đó không tự đặt lại absolute lifetime từ đầu. Nếu mỗi lần refresh lại mở thêm bảy ngày bất kể grant gốc, một yêu cầu absolute timeout bảy ngày sẽ không được đáp ứng.

Token refresh hết hạn hoặc bị thu hồi không được tạo token mới. Tùy mô hình, refresh token có thể được rotation và kiểm soát tái sử dụng; những cơ chế đó cần được thiết kế cùng vòng đời family/grant. Chỉ đổi chuỗi refresh token không chứng minh rằng chuỗi cũ không còn dùng được.

### 7.3. Refresh sớm để giữ trải nghiệm không tạo grace ngoài chính sách

Client có thể xin token mới trước khi token hiện tại hết hạn để tránh gián đoạn do độ trễ. Khoảng refresh sớm là lựa chọn vận hành, không phải quyền dùng token đã hết hạn.

Thông tin như `expires_in` có thể giúp client lập lịch, nhưng quyết định chấp nhận token vẫn thuộc server. Đồng hồ đếm ngược hoặc thời gian trên điện thoại không phải nguồn chuẩn của validator. Khi ứng dụng trở lại từ trạng thái ngủ, cần xử lý khả năng token đã hết hạn thay vì giả định bộ đếm cục bộ vẫn chính xác.

Client cũng cần tránh refresh dồn dập: nhiều request có thể cùng phát hiện token sắp hết hạn. Phối hợp refresh và retry phải không gây bão yêu cầu, không làm mất các ràng buộc rotation và không làm một lỗi xác thực trở thành vòng lặp vô hạn.

## 8. Expiry không thay thế thu hồi trước hạn

Giả sử access token còn hạn bốn phút nhưng tài khoản vừa bị khóa do sự cố. Nếu API chỉ kiểm tra chữ ký và `exp` ngoại tuyến, nó có thể vẫn chấp nhận token cho đến khi hết hạn có tính dung sai. Đó là đặc tính phải được đưa vào yêu cầu thu hồi, không phải lỗi có thể bỏ qua vì TTL tương đối ngắn.

Nếu nghiệp vụ yêu cầu chặn trong mười giây nhưng token có thể còn dùng được bốn phút, cần cơ chế bổ sung phù hợp: kiểm tra trạng thái, version/epoch, danh sách thu hồi hoặc một cách kiểm soát tại tài nguyên. Cơ chế nào được chọn phải được kiểm chứng ở các điểm thực thi thuộc phạm vi.

Một token hết hạn không được tiếp tục dùng chỉ vì dịch vụ thu hồi đang lỗi. Ngược lại, biết token còn hạn cũng không chứng minh nó chưa bị thu hồi, đúng audience, đúng scope hoặc chủ thể còn đủ điều kiện truy cập.

Có thể biểu diễn điều kiện tổng quát:

```text
Cho phép hành động =
    token có nguồn gốc/toàn vẹn hợp lệ
    AND đúng loại token, issuer và audience
    AND hợp lệ về thời gian theo profile
    AND đáp ứng kiểm soát thu hồi/trạng thái được yêu cầu
    AND đủ quyền cho hành động và tài nguyên hiện tại
```

## 9. Thực thi expiry xuyên qua cache và các lớp dịch vụ

### 9.1. Cache kết quả xác thực không được vượt deadline

Nếu cache một quyết định `ALLOW`, thời hạn cache phải bị chặn bởi thời điểm kết thúc chấp nhận token theo hợp đồng. Không chỉ lấy một TTL cố định từ thời điểm cache được ghi.

```text
Ví dụ:
    token chỉ còn được chấp nhận 20 giây;
    TTL mặc định của cache là 60 giây.

Yêu cầu:
    kết quả cache không được tiếp tục cho phép đủ 60 giây
    nếu không còn phép kiểm tra expiry ở đường sử dụng.
```

Có thể thiết kế deadline cache không muộn hơn deadline token, hoặc kiểm tra lại thời gian khi đọc cache. Nếu còn có yêu cầu thu hồi nhanh, cache cũng phải đáp ứng giới hạn của cơ chế thu hồi; giới hạn expiry không tự giải quyết giới hạn thu hồi.

Metadata trả về từ một dịch vụ kiểm tra token cũng cần được áp dụng đúng. Một kết quả “active” nhận được lúc token còn hạn không thể được dùng vĩnh viễn mà không xét metadata thời gian và chính sách cache.

### 9.2. Gateway đã kiểm tra không có nghĩa downstream được tin vô thời hạn

Request có thể nằm trong hàng đợi hoặc được chuyển giữa nhiều dịch vụ. Nếu gateway kiểm tra token trước expiry nhưng downstream thực hiện hành động sau đó, hệ thống cần quyết định điểm nào là điểm chấp nhận quyền.

Một cờ `authenticated=true` không mang ngữ cảnh thời gian không nên trở thành quyền vô hạn. Nếu truyền một authentication context nội bộ, phải bảo vệ nguồn gốc, phạm vi và thời hạn của context theo thiết kế. Thời hạn của bằng chứng chuyển tiếp không được tự mở rộng quyền gốc trái hợp đồng.

### 9.3. Expiry của record lưu trữ và expiry bảo mật khác nhau

TTL của database/cache có thể chỉ quyết định khi nào record được dọn, với thời điểm cleanup thực tế không trùng chính xác mốc hết hạn. Validator phải kiểm tra deadline logic nếu hợp đồng cần từ chối ngay tại biên; không chỉ đợi record biến mất.

Tương tự, giữ một record hết hạn để audit không có nghĩa token vẫn được phép sử dụng. Lưu giữ bằng chứng và chấp nhận quyền truy cập là hai quyết định khác nhau.

## 10. Request dài, stream và tác vụ bất đồng bộ

### 10.1. Chọn thời điểm kiểm tra theo hành động

Một yêu cầu có thể được xác thực trước expiry nhưng hoàn tất sau expiry. Không thể tự kết luận mọi công việc phải bị hủy đúng lúc token hết hạn, cũng không thể mặc định mọi kết nối đã mở được tiếp tục vô thời hạn.

Đặc tả phải chọn rõ, chẳng hạn:

| Loại hoạt động | Câu hỏi phải chốt |
| --- | --- |
| Request đọc ngắn | Token cần hợp lệ tại điểm tiếp nhận/ủy quyền nào? |
| Giao dịch nhạy cảm | Có kiểm tra lại trước commit hoặc cần xác thực mới không? |
| WebSocket/stream | Kiểm tra khi mở, định kỳ, khi nhận thông điệp hay đóng tại deadline? |
| Tải file dài | Cho hoàn tất phiên truyền đã được chấp nhận hay cắt khi hết hạn? |
| Job chạy nền | Quyền được chuyển thành ủy quyền job có giới hạn như thế nào? |

Nếu stream được kiểm tra định kỳ, chu kỳ kiểm tra và độ trễ thực thi ảnh hưởng tới thời điểm dừng truy cập. Chúng phải được tính vào cam kết, thay vì chỉ nêu hạn dùng của token mở kết nối.

### 10.2. Không giữ bearer token của người dùng làm quyền chạy job vô hạn

Một job có thể chạy lâu hơn access token ban đầu. Thiết kế cần xác định quyền của job, tài nguyên, chủ thể khởi tạo và hành vi khi quyền bị thay đổi. Có thể sử dụng mô hình ủy quyền riêng hoặc identity workload phù hợp, nhưng phải giới hạn theo nghiệp vụ và có audit.

Không kéo dài token người dùng tùy ý chỉ để job không lỗi, cũng không coi việc đã xếp hàng một job là quyền làm mọi việc sau đó. Nếu hợp đồng chỉ yêu cầu token còn hạn khi nhận job, phải nói rõ những kiểm soát tiếp theo và loại thao tác đã được ủy quyền.

## 11. Xử lý lỗi và trải nghiệm client

API phải từ chối token hết hạn theo hợp đồng lỗi của giao thức/API. Ví dụ, endpoint dùng bearer authentication có thể trả lỗi xác thực tương ứng; không nên đánh đồng hết hạn với trường hợp người dùng đã xác thực nhưng thiếu quyền.

Thông báo cho client nên đủ để chọn refresh hay đăng nhập lại, không chứa raw token hoặc chi tiết nhạy cảm không cần thiết. Nội bộ có thể dùng reason code như `TOKEN_EXPIRED`, `TOKEN_NOT_YET_VALID`, `TOKEN_TIME_INVALID` hoặc `TOKEN_LIFETIME_EXCEEDED` để phân biệt nguyên nhân.

Sau lỗi expiry:

1. Client kiểm tra có đường refresh hợp lệ theo thiết kế hay không.
2. Nếu refresh thất bại do credential hết hạn/thu hồi, chuyển sang xác thực lại phù hợp.
3. Chỉ retry request khi ngữ nghĩa hành động cho phép và có biện pháp chống thực hiện lặp nếu cần.
4. Không lặp refresh/retry vô hạn và không bỏ qua kiểm tra token để giữ trải nghiệm.

Đối với thao tác ghi, timeout hoặc response lỗi ở một lớp không luôn chứng minh nghiệp vụ chưa xảy ra. Tự động gửi lại thanh toán sau refresh có thể tạo tác dụng phụ lặp nếu thiếu cơ chế idempotency phù hợp. Yêu cầu expiry cần kết nối với hợp đồng retry của từng hành động, không áp một quy tắc retry chung cho mọi request.

## 12. Bộ yêu cầu có thể kiểm chứng

Ví dụ sau giả định profile access token bắt buộc có các mốc thời gian cần thiết, lifetime danh nghĩa tối đa 300 giây và có chính sách dung sai được công bố. Các giá trị chỉ minh họa cách đặc tả.

| ID | Yêu cầu | Bằng chứng nghiệm thu |
| --- | --- | --- |
| TE-01 | Mỗi loại token có mục đích, lifetime tối đa, trường bắt buộc và nguồn thời gian đã xác định | Profile/contract đầy đủ; mẫu hợp lệ và không hợp lệ được kiểm tra |
| TE-02 | Bên phát hành không cấp access token vượt lifetime tối đa hoặc giới hạn grant mà hợp đồng yêu cầu | Yêu cầu client đề nghị hạn dài bị giới hạn/từ chối; token cấp ra đáp ứng chính sách |
| TE-03 | Validator kiểm tra thời gian sau khi xác minh nguồn gốc/toàn vẹn và theo đúng profile | Token payload bị sửa, sai loại hoặc thiếu thời gian bắt buộc không được cấp quyền |
| TE-04 | Phép so sánh biên `exp` và dung sai được áp dụng nhất quán | Kiểm tra trước biên, đúng biên và sau biên với từng cấu hình leeway trong phạm vi |
| TE-05 | Đơn vị thời gian và miền số không bị ép kiểu tùy tiện | Token dùng mili giây sai hợp đồng, sai kiểu hoặc vượt miền bị từ chối |
| TE-06 | Cache xác thực không kéo dài quyền ngoài deadline token theo hợp đồng | Làm nóng cache sát expiry; gọi lại sau deadline vẫn bị từ chối |
| TE-07 | Refresh hết hạn/thu hồi không tạo token mới và không đặt lại absolute deadline trái chính sách | Thử refresh tại các biên và gần giới hạn cuối của grant |
| TE-08 | Clock skew/leeway có giới hạn và được tính vào mốc chấp nhận thực tế | Mô phỏng lệch đồng hồ trong/ngoài ngưỡng; đo hành vi tại các validator |
| TE-09 | Tất cả đường truy cập thuộc phạm vi có điểm kiểm tra expiry rõ ràng | Kiểm tra gateway, gọi nội bộ được phép, stream và job theo hợp đồng từng đường |
| TE-10 | Lỗi nguồn thời gian/store không tự bỏ kiểm tra thời hạn | Mô phỏng lỗi; kết quả tuân thủ hành vi lỗi đã chốt và không chấp nhận token ngoài hạn |
| TE-11 | Hết hạn và thu hồi được kiểm tra như hai điều kiện độc lập khi yêu cầu có cả hai | Token còn hạn nhưng bị thu hồi và token hết hạn chưa bị thu hồi đều bị từ chối tương ứng |
| TE-12 | Audit phân biệt nguyên nhân lỗi thời gian mà không lưu credential thô | Log có loại sự kiện, kết quả và correlation ID; không có raw bearer token |

Một yêu cầu như “mọi API từ chối token sau deadline” phải được gắn với phạm vi, điểm quyết định quyền và dung sai cụ thể. Nếu yêu cầu đo theo thời gian chuẩn, còn phải tính sai lệch đồng hồ được bảo đảm. Không dùng kết quả tốt ở một node để suy ra toàn hệ thống đã đạt.

## 13. Thiết kế ca nghiệm thu

### 13.1. Kiểm tra đúng biên bằng đồng hồ có thể điều khiển

Thay vì chờ nhiều phút trong mỗi phép kiểm tra, môi trường kiểm thử có thể cung cấp nguồn thời gian có kiểm soát. Với token giả lập hợp lệ theo profile, `nbf=1000`, `exp=1300`, không leeway:

| Thời gian tại validator | Kỳ vọng về thời gian |
| --- | --- |
| 999 | Chưa tới thời điểm được chấp nhận |
| 1000 | Có thể hợp lệ nếu các điều kiện khác đều đạt |
| 1299 | Chưa hết hạn |
| 1300 | Đã hết hạn |
| 1301 | Đã hết hạn |

“Có thể hợp lệ” không đồng nghĩa tự động được phép gọi mọi API: vẫn cần chữ ký/nguồn gốc, audience, trạng thái và quyền tương ứng.

Nếu cho leeway 30 giây theo công thức ở phần trên, biên từ chối expiry chuyển sang `now_local >= 1330`. Cần có ca ở 1329 và 1330, đồng thời kiểm tra biên `nbf` theo đúng chính sách. Không dùng bộ kỳ vọng không leeway để đánh giá cấu hình có leeway rồi coi khác biệt là ngẫu nhiên.

### 13.2. Kiểm tra cache không che khuất expiry

```gherkin
Feature: Cache không kéo dài quyền của token hết hạn

  Scenario: Quyết định cho phép đã được cache sát deadline
    Given token hợp lệ cho API thử nghiệm và chỉ còn thời gian hiệu lực ngắn
    And một request đã làm nóng cache xác thực/phân quyền liên quan
    When nguồn thời gian đi qua deadline chấp nhận theo profile
    And client gửi request mới bằng đúng token cũ
    Then request không nhận dữ liệu hoặc thực hiện hành động được bảo vệ
    And cache không giữ quyết định cho phép vượt deadline
    And audit ghi nguyên nhân thời gian phù hợp mà không chứa raw token
```

Không chỉ kiểm tra response code; cần xác nhận hành động có quyền không xảy ra phía sau một response lỗi. Với nhiều lớp cache, phải kiểm tra các đường thực tế có thể cấp quyền.

### 13.3. Các ca cần bổ sung

- Token thiếu `exp` trong profile bắt buộc có trường này.
- `exp` sai kiểu, sai đơn vị, quá xa hoặc thời gian đảo ngược theo schema.
- Token có chữ ký hợp lệ nhưng lifetime vượt mức chính sách cho phép.
- `iat` quá xa trong tương lai khi profile kiểm soát mốc phát hành.
- Đồng hồ validator chậm hoặc nhanh ở ngưỡng cho phép.
- Refresh đúng trước, đúng tại và sau biên hết hạn theo chính sách.
- Refresh liên tục gần absolute deadline của grant.
- Token còn hạn nhưng đã bị thu hồi.
- Gọi qua gateway và đường nội bộ được phép, kiểm tra không có đường bỏ qua.
- Kết nối dài mở trước expiry và tiếp tục trao đổi sau deadline theo hợp đồng.
- Request đã được nhận trước expiry nhưng tới điểm thực thi sau đó.
- Client retry thao tác ghi sau refresh, kiểm tra không tạo nghiệp vụ lặp.

Đây là tiêu chí cho hệ thống được thiết kế, không phải kết quả kiểm thử sản phẩm đã thực hiện khi soạn bài học.

## 14. Audit và những lỗi đặc tả thường gặp

Một sự kiện xác thực thất bại có thể ghi:

```json
{
  "eventType": "token.validation",
  "tokenType": "access_token",
  "validator": "orders-api",
  "outcome": "DENY",
  "reason": "TOKEN_EXPIRED",
  "policyVersion": "access-time-v2",
  "correlationId": "request-8e42"
}
```

Log không cần chứa bearer token nguyên văn để giải thích token bị từ chối vì hết hạn. Nếu cần liên kết sự kiện, sử dụng tham chiếu được thiết kế cho audit với quyền truy cập phù hợp. Không tin các trường chưa được xác thực trong token để kết luận danh tính và ghi chúng như sự thật.

Các lỗi dễ gặp:

- **“Có `exp` nên tự hết hiệu lực.”** Chỉ đúng nếu mọi nơi cấp quyền thực sự kiểm tra nó và không bị cache bỏ qua.
- **“TTL năm phút nghĩa là không dùng được sau đúng năm phút theo mọi đồng hồ.”** Leeway và clock skew có thể kéo dài thời điểm chấp nhận thực tế.
- **“Refresh gia hạn cùng một token.”** Token cũ và mới có vòng đời riêng; phải xác định khả năng cùng tồn tại.
- **“Logout là thu hồi mọi token.”** Cần cơ chế thực thi ở tài nguyên; xóa dữ liệu client chưa đủ.
- **“Dùng Redis/database TTL thay kiểm tra thời gian.”** Cleanup vật lý không nhất thiết xảy ra đúng deadline bảo mật.
- **“Access token ngắn hạn nên refresh token không cần giới hạn.”** Credential nguồn còn dùng được có thể tiếp tục phát hành quyền mới.
- **“Request đã qua gateway thì context xác thực dùng vô hạn.”** Hàng đợi, downstream và kết nối dài vẫn cần hợp đồng thời gian.
- **“Expiry lỗi thì cho qua để giữ trải nghiệm.”** Biến lỗi hạ tầng thành đường cấp quyền ngoài chính sách.

## 15. Câu hỏi tự kiểm tra

1. Deadline đang nói tới là `exp` danh nghĩa hay thời điểm từ chối đã tính leeway và sai lệch đồng hồ?
2. Mỗi loại token có profile riêng về mục đích, trường bắt buộc, lifetime và cách thu hồi chưa?
3. Có cache hoặc đường gọi nội bộ nào tiếp tục chấp nhận token sau deadline không?
4. Refresh có bị ràng buộc bởi idle timeout và absolute deadline của grant theo yêu cầu không?
5. Nếu token bị lộ nhưng refresh credential còn hoạt động, TTL access token giới hạn được phần rủi ro nào?
6. Stream, request dài và job bất đồng bộ kiểm tra quyền ở thời điểm nào?
7. Bằng chứng nghiệm thu có kiểm tra đúng biên thời gian, nhiều validator và trạng thái cache thực tế không?

Một yêu cầu token expiry hoàn chỉnh phải nối được chính sách phát hành, cách biểu diễn thời gian, kiểm tra tại điểm thực thi và vòng đời refresh/thu hồi. Chỉ một giá trị TTL trong cấu hình không chứng minh được giới hạn truy cập của toàn hệ thống.
