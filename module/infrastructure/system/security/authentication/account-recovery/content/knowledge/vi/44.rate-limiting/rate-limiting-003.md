# Per network rate limit — Giới hạn tần suất theo mạng trong khôi phục tài khoản

## 1. “Theo mạng” có nghĩa là gì?

**Per network rate limit** là giới hạn lưu lượng dựa trên nguồn mạng của yêu cầu, chẳng hạn một địa chỉ IP hoặc một prefix CIDR. Trong khôi phục tài khoản, lớp này giúp hạn chế một nguồn tạo nhiều yêu cầu gửi email, SMS, thử mã hoặc tiêu thụ tài nguyên xử lý.

Ví dụ, một máy liên tục gọi chức năng quên mật khẩu với hàng nghìn địa chỉ email khác nhau. Giới hạn theo từng tài khoản có thể chưa đủ vì mỗi tài khoản chỉ bị gọi một lần. Một ngân sách dùng chung cho nguồn mạng giúp phát hiện và kìm lưu lượng đó.

Tuy nhiên, địa chỉ IP không tương đương một người, thiết bị hoặc tài khoản:

- Nhiều người có thể dùng chung IP công cộng qua NAT, proxy hoặc VPN.
- Một người có thể đổi IP khi chuyển Wi-Fi, mạng di động hoặc VPN.
- Một thiết bị IPv6 có thể sử dụng nhiều địa chỉ trong cùng prefix.
- Kẻ tấn công có thể phân tán request qua nhiều mạng.

Vì vậy, giới hạn theo mạng là một lớp chống lạm dụng, không phải bằng chứng sở hữu tài khoản. Nó phải phối hợp với giới hạn theo tài khoản, đích nhận, challenge và chi phí toàn hệ thống.

## 2. Chọn đối tượng mạng cần đếm

| Đối tượng | Ý nghĩa | Điểm mạnh | Giới hạn |
| --- | --- | --- | --- |
| IPv4 /32 | Một địa chỉ IPv4 | Kìm một nguồn cụ thể | Có thể là địa chỉ chung của nhiều người |
| IPv6 /128 | Một địa chỉ IPv6 | Nhận diện lưu lượng ở mức địa chỉ | Dễ bị phân tán bằng nhiều địa chỉ cùng mạng |
| Prefix CIDR | Một nhóm địa chỉ có chung phần đầu | Gộp được một số hành vi xoay địa chỉ | Có thể gộp nhiều người dùng không liên quan |
| Nhóm nhà mạng hoặc ASN | Phạm vi hạ tầng lớn | Hữu ích cho phân tích chiến dịch | Quá thô để mặc định xem là một người dùng |
| Nguồn qua proxy đã xác định | Biên mạng có thể tin cậy quan sát | Phù hợp hệ thống đứng sau CDN hoặc gateway | Phụ thuộc cấu hình chuỗi proxy đúng |

Một prefix dùng để rate limit là **nhóm chính sách**, không tự chứng minh quyền quản lý hoặc danh tính của những địa chỉ bên trong.

Không mặc định mọi IPv4 /24 hay IPv6 /64 đều cần cùng một trần cố định. Độ rộng prefix phải được lựa chọn từ mô hình mạng, dữ liệu vận hành và mức chặn nhầm chấp nhận được.

RFC 7421 phân tích vai trò phổ biến của ranh giới /64 trong kiến trúc IPv6. Đây là tài liệu về địa chỉ mạng, không quy định rằng rate limiter của ứng dụng bắt buộc dùng /64 cho mọi tình huống. [Nguồn: RFC 7421](https://www.rfc-editor.org/rfc/rfc7421.html).

## 3. Mô hình đe dọa của giới hạn theo mạng

| Cách lạm dụng | Vì sao một bộ giới hạn đơn giản thất bại? | Hướng xử lý |
| --- | --- | --- |
| Xoay IP trong cùng prefix | Mỗi địa chỉ có bộ đếm mới | Kết hợp giới hạn địa chỉ và prefix phù hợp |
| Dùng nhiều mạng độc lập | Không nguồn nào vượt trần riêng | Thêm giới hạn theo tài khoản, đích nhận và ngân sách tổng |
| Giả mạo header IP | Máy chủ dùng dữ liệu do client tự khai | Xác định nguồn qua chuỗi proxy tin cậy |
| Gọi nhiều endpoint cùng tác động | Mỗi route có bộ đếm riêng | Gom các route liên quan vào nhóm hành động |
| Tiêu thụ ngân sách mạng dùng chung | Người dùng thật cùng NAT bị từ chối | Phân tầng biện pháp và bảo vệ đường tiếp tục hợp lệ |
| Tạo nhiều khóa bộ đếm | Kho trạng thái bị đầy hoặc churn | Giới hạn tài nguyên, thời hạn lưu và xử lý tại biên |
| Đi thẳng đến origin | Bỏ qua giới hạn tại CDN | Bảo vệ đường vào origin và kiểm soát trong dịch vụ |
| Chạy qua nhiều instance | Mỗi instance cho một hạn mức đầy đủ | Dùng ngân sách chung hoặc phân bổ có giới hạn rõ |

Chặn đúng số request theo mạng vẫn có thể bỏ sót notification flooding đến một nạn nhân từ nhiều mạng. Tương tự, giảm lưu lượng tổng không tự bảo đảm số lần thử recovery code trên một tài khoản đã được giới hạn.

## 4. Xác định địa chỉ nguồn trước khi đếm

### 4.1. Peer của kết nối và địa chỉ trong header khác nhau

Khi ứng dụng kết nối trực tiếp với client, địa chỉ peer của kết nối là dữ liệu mạng do tầng kết nối cung cấp. Khi ứng dụng đứng sau reverse proxy, peer thường là proxy gần ứng dụng nhất.

Các header như X-Forwarded-For hoặc Forwarded chỉ hữu ích khi được xử lý theo một mô hình tin cậy rõ ràng. Client có thể tự gửi chúng; tên header không làm nội dung trở thành đáng tin.

Một cấu hình dễ bị lợi dụng:

~~~text
clientIp = request.header("X-Forwarded-For").firstValue()
limitBy(clientIp)
~~~

Người gọi chỉ cần đổi giá trị đầu header để tạo khóa khác nếu hệ thống chấp nhận trực tiếp dữ liệu này.

### 4.2. Đi từ biên tin cậy vào chuỗi địa chỉ

Một phương án dùng danh sách proxy tin cậy:

1. Lấy địa chỉ peer thực của kết nối.
2. Nếu peer không thuộc proxy tin cậy, không dùng header chuyển tiếp để chọn nguồn.
3. Nếu peer được tin cậy, phân tích chuỗi chuyển tiếp theo đúng giao thức triển khai.
4. Đi từ phía gần ứng dụng ra ngoài, bỏ qua các hop đã được cấu hình là proxy tin cậy.
5. Dừng tại địa chỉ đầu tiên nằm ngoài phạm vi tin cậy; đó là biên nguồn dùng cho quyết định an ninh.
6. Không tiếp tục đi sang phần do hop không tin cậy có thể tự khai báo.

Địa chỉ tìm được có thể là một proxy trung gian không tin cậy, không nhất thiết là thiết bị gốc. MDN mô tả cách chọn từ phải sang trái theo danh sách proxy tin cậy và lưu ý giới hạn này. [Nguồn: MDN X-Forwarded-For](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Forwarded-For#selecting_an_ip_address).

Ví dụ minh họa:

~~~text
Client thực -> Proxy biên tin cậy -> Ingress tin cậy -> Ứng dụng

Header ứng dụng nhận:
X-Forwarded-For: địa-chỉ-do-client-tự-khai, địa-chỉ-client-thực, proxy-biên

Peer kết nối:
ingress
~~~

Nếu các proxy được cấu hình và hoạt động đúng theo hợp đồng đó, việc đi từ phải sang trái sẽ dừng ở địa chỉ client thực. Không dùng ngay phần tử đầu vì phần đó có thể do client tự thêm.

### 4.3. Cấu hình tin cậy cần khớp đường đi thực tế

- Proxy biên cần xóa, ghi đè hoặc bổ sung header theo chính sách nhất quán.
- Origin phải được bảo vệ để người gọi không tùy ý đi vòng qua proxy tin cậy.
- Không coi mọi địa chỉ private hoặc toàn bộ dải cloud là proxy được tin cậy.
- Không dùng số hop cố định nếu hệ thống có nhiều đường vào với độ dài chuỗi khác nhau.
- Quy định cách xử lý header lặp, chuỗi quá dài, địa chỉ sai và dữ liệu mâu thuẫn.
- Nếu dùng PROXY protocol, chỉ chấp nhận nó trên đường kết nối được kiểm soát phù hợp.

Đừng chọn “IP đầu tiên không phải private” làm thuật toán tin cậy. Tính public/private của địa chỉ không chứng minh hop đó có quyền khai báo nguồn cho hệ thống.

Khi không xác định được nguồn hợp lệ, dùng chính sách lỗi hoặc dự phòng đã thiết kế. Không tạo một khóa ngẫu nhiên mới cho mỗi request lỗi, vì điều đó làm mất tác dụng giới hạn.

## 5. Chuẩn hóa IPv4, IPv6 và prefix

### 5.1. Một địa chỉ có thể có nhiều cách biểu diễn

IPv6 có dạng rút gọn và dạng đầy đủ. Nếu dùng nguyên chuỗi đầu vào làm khóa, cùng một địa chỉ có thể được đếm khác nhau.

Ví dụ các dạng biểu diễn tương đương cần được đưa về cùng giá trị địa chỉ:

~~~text
2001:db8:1200:34::10
2001:0db8:1200:0034:0000:0000:0000:0010
~~~

Nên phân tích thành địa chỉ nhị phân hợp lệ, chuẩn hóa họ địa chỉ và áp mặt nạ prefix bằng phép toán trên địa chỉ. Không tạo prefix bằng cách cắt một số ký tự từ chuỗi IPv6.

Dùng parser địa chỉ literal phù hợp; không để việc phân tích một header tùy ý kích hoạt truy vấn DNS. Quy định rõ việc chấp nhận dạng có cổng, dấu ngoặc hoặc dữ liệu không phải địa chỉ IP.

Với IPv4-mapped IPv6 như ::ffff:198.51.100.17, thống nhất cách chuẩn hóa theo cách tầng mạng thực sự cung cấp địa chỉ. Không suy rộng rằng mọi dạng nhúng hoặc chuyển đổi IPv6 đều có thể tùy ý rút về IPv4.

### 5.2. Tạo khóa mạng nhất quán

Các địa chỉ tài liệu minh họa sau không phải cấu hình triển khai:

| Địa chỉ | Chính sách prefix minh họa | Nhóm đếm |
| --- | --- | --- |
| 198.51.100.17 | IPv4 /32 | 198.51.100.17/32 |
| 198.51.100.17 và 198.51.100.99 | IPv4 /24 | 198.51.100.0/24 |
| 2001:db8:1200:34::10 và 2001:db8:1200:34::ff01 | IPv6 /64 | 2001:db8:1200:34::/64 |
| 2001:db8:1200:35::10 | IPv6 /64 | 2001:db8:1200:35::/64 |

Gộp /64 có thể hạn chế việc đổi phần địa chỉ thiết bị trong cùng prefix, nhưng không ngăn người gọi sử dụng nhiều prefix. Gộp quá rộng có thể khiến một người tiêu thụ ngân sách của nhiều khách hàng khác.

Một khóa chính sách có thể được tạo từ:

~~~text
policyVersion | scope | actionGroup | addressFamily | prefixLength | maskedAddress
~~~

Scope phải do máy chủ xác định. Nếu chỉ chia theo tenant, một nguồn có thể dùng nhiều tenant để tăng tải tổng; có thể cần thêm lớp nguồn chung ở hạ tầng.

Có thể dùng HMAC để che địa chỉ trong khóa lưu trữ. Khóa đó vẫn là định danh có thể liên kết, cần kiểm soát truy cập và thời hạn lưu. Việc đổi khóa HMAC hoặc policyVersion cũng có thể tạo ngân sách mới, nên phải tính đến khi chuyển cấu hình.

## 6. Đặt giới hạn đúng giai đoạn khôi phục

| Giai đoạn | Mục tiêu giới hạn theo mạng | Kiểm soát vẫn cần giữ riêng |
| --- | --- | --- |
| Khởi tạo recovery | Hạn chế quét tài khoản, tạo công việc và gửi thông báo | Phản hồi tránh dò tài khoản; hạn mức tài khoản và người nhận |
| Gửi lại mã hoặc link | Ngăn đổi endpoint để khuếch đại số lần gửi | Cooldown và vòng đời challenge |
| Kiểm tra OTP hoặc recovery code | Giảm số lần thử từ một nguồn | Tổng số lần thất bại theo tài khoản/challenge và chính sách xác minh |
| Hoàn tất đổi mật khẩu | Bảo vệ tài nguyên và hành động nhạy cảm | Token đúng phạm vi, dùng một lần, kiểm tra nguyên tử |
| Gắn lại MFA hoặc passkey | Hạn chế tự động hóa tại bước cấp quyền mới | Bằng chứng sở hữu và quyền thực hiện hành động |
| Tải bằng chứng cho hỗ trợ | Hạn chế tải lên và chi phí phân tích | Phân quyền, dung lượng và xử lý nội dung không tin cậy |

Nếu “quên mật khẩu”, “gửi lại” và “khôi phục MFA” đều có thể phát SMS, những lớp kiểm soát phù hợp cần tính được tác động chung. Không chỉ đặt một trần cho từng URL rồi để người gọi chuyển route.

Thay IP không được làm bộ đếm thất bại của tài khoản hoặc challenge quay về không. Ngược lại, IP chung bị quá tải không phải lý do khóa tài khoản, gỡ MFA hoặc thu hồi toàn bộ phiên của mọi người trong mạng.

OWASP khuyến nghị chống lạm dụng biểu mẫu đặt lại mật khẩu, phản hồi tránh dò tài khoản và không thay đổi trạng thái tài khoản chỉ vì một yêu cầu chưa được xác minh. Giới hạn theo mạng bổ sung cho các yêu cầu này. [Nguồn: OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

## 7. Chọn thuật toán và hiểu ý nghĩa hạn mức

### 7.1. Các lựa chọn thường gặp

| Thuật toán | Đặc điểm | Điểm cần cân nhắc |
| --- | --- | --- |
| Fixed window | Đếm trong từng khoảng cố định | Có thể tạo burst lớn quanh ranh giới hai cửa sổ |
| Sliding window | Xét lưu lượng trong khoảng gần nhất | Chi phí trạng thái và mức xấp xỉ tùy triển khai |
| Token bucket | Có sức chứa burst và tốc độ nạp lại | Phải xác định capacity, refill và chi phí hành động |
| Giới hạn đồng thời | Chặn quá nhiều công việc đang chạy | Không thay thế giới hạn số request theo thời gian |

Một nguồn tạo nhiều request tuần tự có thể không chạm giới hạn đồng thời. Một nguồn mở nhiều công việc chậm có thể làm cạn tài nguyên dù tần suất chưa cao. Tùy tác động cần bảo vệ, hai lớp có thể cùng cần thiết.

### 7.2. Ví dụ token bucket

Gọi:

- B là sức chứa tối đa.
- r là số đơn vị được nạp mỗi giây.
- w là chi phí của một hành động.
- t là thời gian từ lần cập nhật trước.

Số đơn vị được nạp:

~~~text
available = min(B, previousAvailable + r * t)
~~~

Chỉ chấp nhận nếu available lớn hơn hoặc bằng w; sau đó trừ w trong cùng thao tác nguyên tử.

Ví dụ minh họa B = 20, r = 0,5 và w = 1 cho phép một burst đầu tối đa hai mươi request khi bucket đầy. Trong sáu mươi giây, lượng được cấp không vượt quá B + r × 60 = 50 đơn vị theo mô hình lý tưởng đó. Đây không phải lời khuyên đặt ngưỡng cho một dịch vụ cụ thể.

Một hành động gửi SMS và một lần mở trang tĩnh có thể có chi phí khác nhau. Tuy nhiên, trọng số mạng không thay thế ngân sách gửi theo người nhận hoặc cơ chế chống dò mã.

Khi dùng nhiều tầng, ví dụ /128 và /64, việc còn ngân sách ở tầng nhỏ không cho phép bỏ qua tầng tổng. Đồng thời, tầng tổng quá chặt có thể tạo chặn nhầm cho nhiều người; cần lựa chọn biện pháp phản ứng phù hợp thay vì chỉ thu nhỏ mọi ngưỡng.

## 8. Cập nhật bộ đếm nguyên tử và quản lý trạng thái

### 8.1. Không tách đọc, quyết định và ghi

Mã giả sau minh họa một bucket dùng chung:

~~~text
tryConsume(key, policy, cost):
    requireValidPolicy(policy)
    require(0 < cost <= policy.capacity)

    atomic at authoritative limiter store:
        state = loadOrInitializeFullBucket(key)
        now = readTrustedStoreTime()

        effectiveNow = max(now, state.lastUpdate)
        elapsed = effectiveNow - state.lastUpdate
        available = min(
            policy.capacity,
            state.available + policy.refillRate * elapsed
        )

        if available >= cost:
            state.available = available - cost
            decision = ALLOW
        else:
            state.available = available
            decision = LIMIT

        state.lastUpdate = effectiveNow
        persistWithCorrectExpiration(key, state)
        return decision
~~~

Đây là mô tả thuật toán, không phải triển khai hoàn chỉnh. Đọc trạng thái, nạp đơn vị, trừ đơn vị và ghi kết quả phải nằm trong bảo đảm đồng thời của kho đã chọn.

Thời gian không lấy từ header hay tham số do client khai báo. Cần xử lý độ chính xác, sai lệch đồng hồ và thay đổi thời gian giữa các nút. Việc không cho thời gian cập nhật lùi là một biện pháp trong mô hình, không tự giải quyết mọi lỗi đồng hồ; bước nhảy lớn về phía trước cũng có thể cấp thêm ngân sách ngoài dự kiến.

Các request bị từ chối không được tự làm thời điểm nạp lại lùi vô hạn. Nếu có chính sách phạt hoặc thời gian tạm hạn chế riêng, nó phải được thiết kế rõ thay vì vô tình tạo ra từ cách cập nhật timestamp.

### 8.2. TTL và dung lượng kho cũng ảnh hưởng bảo đảm

Có thể xóa một bucket khi trạng thái tương đương đã nạp đầy trở lại. Nếu TTL ngắn hơn thời gian cần để bucket đầy, việc xóa rồi khởi tạo lại sẽ cấp thêm một burst sớm.

Cần tính thời hạn lưu theo thuật toán, mức ngân sách còn lại và quy tắc thời gian. Đặt TTL tùy ý như “mọi khóa sống ba mươi giây” có thể phá chính sách có thời gian nạp dài hơn.

Giới hạn số khóa, dung lượng và tốc độ tạo khóa để chống làm cạn kho. Việc đổi chính sách, eviction hoặc khôi phục dữ liệu cũng có thể khiến bucket bị khởi tạo lại; phải tính tác động này vào hành vi khi quá tải.

### 8.3. Nhiều ngân sách không mặc nhiên là một giao dịch

Nếu request cần qua cả bucket địa chỉ, prefix và tenant, cần xác định cách trừ ngân sách. Hai lựa chọn có thể là:

- Cấp quyền nhiều chiều trong một cơ chế nguyên tử có hỗ trợ phù hợp.
- Kiểm tra theo tầng với quy tắc tính phí thận trọng, chấp nhận rằng một tầng có thể đã trừ dù tầng sau từ chối.

Lựa chọn thứ hai có thể phù hợp cho bảo vệ tài nguyên, nhưng phải hiểu tác động lên công bằng và khả năng bị người khác làm cạn ngân sách. Không gọi nó là “tất cả hoặc không có gì” nếu các bước thực tế độc lập.

Không hoàn trả đơn vị một cách mù quáng khi timeout: thao tác có thể đã được thực hiện. Nếu hỗ trợ xử lý lại quyết định sau lỗi, cần định danh thao tác và ràng buộc để không biến việc gửi lại request thành cách lấy lại ngân sách.

## 9. Đặt giới hạn ở nhiều lớp mà không nhân hạn mức

~~~mermaid
flowchart TD
    A[Internet] --> B[CDN hoặc gateway: bảo vệ lưu lượng thô]
    B --> C[Ingress: xác nhận đường vào và metadata]
    C --> D[Ứng dụng: nguồn mạng đã chuẩn hóa]
    D --> E{Ngân sách mạng cho nhóm hành động}
    E -->|Không đủ| F[Phản hồi hạn chế phù hợp]
    E -->|Đủ| G[Kiểm soát tài khoản, challenge và đích nhận]
    G --> H[Xác minh và thực thi nghiệp vụ]
~~~

Gateway có thể chặn sớm lưu lượng rõ ràng bất thường. Ứng dụng vẫn cần hiểu nhóm hành động và những chủ thể mà gateway không biết.

Nếu có bốn instance, mỗi instance cấp một bucket đầy đủ B và tốc độ r cho cùng mạng, tổng có thể thành bốn lần hạn mức dự kiến. Một khóa có cùng chuỗi tên nhưng nằm trong bốn vùng nhớ không phải một bộ đếm chung.

Các cách tổ chức có thể gồm nguồn trạng thái phối hợp chung, định tuyến ổn định đến chủ sở hữu bucket hoặc phân bổ quota cho từng nút. Nếu dùng phân bổ cục bộ, tổng phần được cấp và quy tắc cấp lại phải được kiểm soát.

Với nhiều vùng địa lý, cần nêu rõ phạm vi chính sách:

| Chính sách | Phạm vi cam kết |
| --- | --- |
| Giới hạn tại một edge hoặc một Region | Chỉ bảo đảm trong phạm vi đó |
| Ngân sách chung nhiều Region | Cần cơ chế phối hợp tương ứng |
| Bộ đếm xấp xỉ | Có sai số hoặc vượt ngưỡng được đánh giá |
| Trần cứng cho hành động bảo mật cụ thể | Cần điểm cưỡng chế đủ mạnh cho cam kết đó |

Bộ đếm mạng xấp xỉ có thể hữu ích chống tải, nhưng không được dùng để tuyên bố một giới hạn chính xác về số lần dò mã theo tài khoản.

Origin và các đường vào nội bộ cũng cần phạm vi truy cập rõ. Không để một endpoint cũ, một host trực tiếp hoặc API hỗ trợ bỏ qua toàn bộ chính sách gửi thông báo và kiểm tra mã.

## 10. Phản hồi HTTP và tránh lộ tài khoản

### 10.1. Khi nào dùng 429?

RFC 6585 định nghĩa HTTP 429 Too Many Requests cho tình huống bị giới hạn tần suất; phản hồi có thể kèm Retry-After. Tài liệu không bắt buộc một cách duy nhất để nhận diện chủ thể hay đếm request. [Nguồn: RFC 6585, mục 4](https://www.rfc-editor.org/rfc/rfc6585.html#section-4).

Một phản hồi theo nguồn mạng có thể là:

~~~http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Cache-Control: no-store
Retry-After: 30

{
  "code": "RECOVERY_REQUEST_RATE_LIMITED",
  "message": "Có quá nhiều yêu cầu từ nguồn kết nối này. Hãy chờ trước khi thử lại."
}
~~~

Ba mươi giây trong ví dụ chỉ minh họa định dạng. Giá trị thực phải đến từ chính sách và trạng thái có thể công bố an toàn.

Retry-After không phải đặt chỗ cho một lượt gửi tương lai. Khi hết thời gian, request còn phải đáp ứng các giới hạn khác và có thể tiếp tục cạnh tranh với lưu lượng cùng mạng.

Không để cache dùng chung lưu một phản hồi hạn chế rồi áp cho mọi người gọi cùng URL. RFC 6585 không cho phép cache lưu phản hồi 429; cấu hình hạ tầng phải giữ đúng hành vi này.

### 10.2. Đừng đưa bộ đếm tài khoản vào phản hồi nguồn mạng

Một giới hạn theo mạng được đánh giá trước đối chiếu tài khoản có thể trả cùng chính sách cho cả email tồn tại và không tồn tại.

Ngược lại, trả những thông tin sau có thể làm lộ dữ liệu:

- “IP này đã gửi ba lần cho tài khoản đang tồn tại.”
- Số lượt còn lại của một tài khoản chưa được xác minh.
- Thời điểm tài khoản đó vừa yêu cầu recovery.
- Header Retry-After chỉ xuất hiện khi email đã đăng ký.
- Mã lỗi hoặc độ trễ khác biệt đủ để suy ra kết quả tra cứu.

Phải phân biệt kiểm soát nguồn công khai với hạn mức nội bộ theo tài khoản hoặc đích nhận. Nội dung, status code, header và đường xử lý cần được lựa chọn theo mục tiêu tránh dò tài khoản.

Một lỗi kho rate limit cũng không nhất thiết là đã vượt hạn mức. Có thể cần phản hồi tạm không phục vụ được theo chính sách, thay vì báo sai rằng người dùng đã gửi quá nhiều.

## 11. Mạng dùng chung và khả năng tiếp tục của người dùng thật

### 11.1. Không trừng phạt tài khoản vì hàng xóm mạng

Một doanh nghiệp có hàng trăm người đi qua một IP egress. Một bot trong mạng đó có thể làm bucket IP hết đơn vị, khiến người khác không gửi được yêu cầu khôi phục.

Không thể phân biệt chắc chắn mọi người chỉ bằng IP chung. Thiết kế cần thừa nhận giới hạn này thay vì coi mọi request cùng mạng là một tác nhân.

Có thể phân tầng phản ứng:

| Mức tín hiệu | Phản ứng có thể cân nhắc |
| --- | --- |
| Burst ngắn từ mạng dùng chung | Giới hạn tạm thời, hướng dẫn chờ |
| Lưu lượng bất thường lặp lại | Biện pháp chống tự động hóa theo rủi ro |
| Có bằng chứng tiếp tục recovery hợp lệ | Đường xử lý có ngân sách riêng và quyền hạn hạn chế |
| Có chiến dịch phối hợp | Kết hợp điều tra nguồn, tài khoản và đích nhận |
| Người dùng không thể tiếp tục | Hỗ trợ qua quy trình xác minh đã thiết lập |

Các phản ứng phải có giới hạn tài nguyên. CAPTCHA hoặc một cookie mới không tự chứng minh chủ tài khoản và không nên tự cấp quyền gửi không giới hạn.

### 11.2. Tách khởi tạo công khai khỏi hoàn tất được cấp quyền

Tạo yêu cầu recovery công khai và tiếp tục một challenge đã được cấp hợp lệ có mức thông tin khác nhau. Có thể thiết kế chính sách riêng cho bước tiếp tục để người dùng thật bớt bị mắc kẹt do flood ở bước khởi tạo.

Điều đó không có nghĩa bỏ giới hạn kiểm tra mã hoặc bỏ kiểm tra replay. Một challenge còn hợp lệ vẫn phải có đúng scope, thời hạn, số lần thử và trạng thái tiêu thụ.

Nếu dùng authenticator còn hoạt động hoặc quy trình hỗ trợ đã xác minh, quyền ưu tiên cần gắn với đúng chủ thể và hành động. Không mở một API công khai cho phép client tự khai “đã xác minh” để bỏ qua limiter.

Không hủy token đang có, gỡ MFA hoặc thu hồi phiên đăng nhập chỉ vì IP đã chạm trần. Cũng không cấp lại quyền tài khoản cho người gọi chỉ vì họ sử dụng một mạng được xem là quen thuộc.

### 11.3. Đổi mạng không phải mặc định là tấn công

Người dùng có thể bắt đầu trên Wi-Fi rồi hoàn tất trên mạng di động. Có thể sử dụng thay đổi mạng như tín hiệu rủi ro, nhưng việc ràng buộc cứng mọi link với một IP có thể làm hỏng các tình huống hợp lệ.

Quyết định có yêu cầu thêm bằng chứng hay không phải đến từ thiết kế recovery và mức rủi ro, không từ giả định IP ổn định tương đương danh tính.

## 12. Khi kho giới hạn hoặc metadata nguồn gặp lỗi

Chính sách dự phòng cần xác định trước theo hành động:

| Sự cố | Hành vi cần cân nhắc |
| --- | --- |
| Kho limiter không truy cập được | Hạn chế gửi mới chưa xác minh hoặc dùng ngân sách dự phòng hữu hạn |
| Metadata proxy không hợp lệ | Từ chối hoặc dùng fallback đã được thiết kế; không tin header tùy ý |
| Mất đồng bộ giữa các vùng | Giữ đúng phạm vi cam kết và giới hạn mức vượt cho phép |
| Bộ đếm bị xóa hoặc đổi phiên bản | Kiểm soát burst mới được cấp |
| Lỗi mạng dùng chung kéo dài | Tiếp quản vận hành và đường hỗ trợ có xác minh |

Một fallback cục bộ có thể giúp duy trì một phần dịch vụ, nhưng mỗi instance không được tự nhận lại toàn bộ ngân sách tổng. Cần công bố rõ giới hạn bảo vệ trong chế độ dự phòng.

Không chuyển sang trạng thái “limiter lỗi thì gửi SMS thoải mái”. Đồng thời, cũng không mặc định mọi lỗi limiter phải khóa toàn bộ tài khoản đang có phiên an toàn.

Bất kỳ chế độ dự phòng nào cũng không được bỏ qua các kiểm soát riêng về số lần dò mã, xác minh danh tính, token dùng một lần hoặc quyền gắn MFA/passkey.

Nếu không đủ điều kiện để thực hiện hành động nhạy cảm an toàn, dừng hành động đó và cung cấp hướng dẫn thử lại hoặc hỗ trợ phù hợp. Từ chối một lần gửi mới và làm mất quyền kiểm soát tài khoản là hai tác động khác nhau.

## 13. Ví dụ xuyên suốt: nhiều người cùng một mạng, một nguồn lạm dụng

Một công ty dùng chung IP egress. Bình thường có vài người yêu cầu khôi phục trong một khoảng thời gian. Sau đó một máy trong công ty tự động gửi nhiều request đến các endpoint quên mật khẩu và gửi lại mã.

| Diễn biến | Hành vi thiết kế mong muốn |
| --- | --- |
| Máy tự động gửi request nhanh | Bucket địa chỉ hoặc prefix hạn chế tác động từ nguồn chung |
| Máy đổi email mục tiêu | Hạn mức mạng vẫn áp dụng dù account_id thay đổi |
| Máy chuyển sang endpoint gửi lại | Nhóm hành động chung ngăn nhân ngân sách theo route |
| Người dùng thật cùng IP bị hạn chế | Có hướng dẫn chờ và đường tiếp tục được cấp quyền phù hợp |
| Request tự thêm một IP khác vào X-Forwarded-For | Không được đổi nguồn đã xác định qua proxy tin cậy |
| Một người mở challenge cũ còn hợp lệ từ mạng di động | Kiểm tra quyền challenge và chính sách rủi ro, không chỉ so IP |
| Bot chuyển sang nhiều mạng độc lập | Giới hạn tài khoản, người nhận và ngân sách tổng tiếp tục bảo vệ |

Sau khi chặn được nguồn mạng, không kết luận cuộc tấn công đã kết thúc. Cần xem số thông báo thực tế, số lần thử mã và trạng thái các tài khoản liên quan.

Trong một biến thể, cả ứng dụng chỉ nhìn thấy IP của ingress vì chưa thiết lập chuỗi chuyển tiếp đúng. Tất cả người dùng bị đưa vào một bucket. Dấu hiệu vận hành là số lượng nguồn mạng thấp bất thường đi kèm nhiều tài khoản và nhiều thiết bị khác nhau; vấn đề cần xử lý nằm ở việc xác định nguồn, không nhất thiết ở ngưỡng quá thấp.

## 14. Quan sát, riêng tư và điều chỉnh chính sách

### 14.1. Đo khả năng bảo vệ và tác động đến người dùng

Các chỉ số có ích:

- Request được chấp nhận hoặc hạn chế theo nhóm hành động, họ địa chỉ và loại prefix.
- Số lượng khóa bucket và tốc độ tạo khóa mới.
- Độ trễ, timeout và lỗi kho limiter.
- Mức chặn nhầm nghi ngờ ở mạng NAT, VPN hoặc egress doanh nghiệp.
- Tỷ lệ người dùng hợp lệ hoàn tất recovery sau khi gặp hạn chế.
- Số thông báo thực tế và số lần thử mã không hợp lệ còn xảy ra.
- Mức vượt giới hạn quan sát được khi có nhiều instance hoặc nhiều vùng.
- Tần suất đi vào chế độ dự phòng.

Không dùng IP, account_id hoặc raw header làm nhãn metric có số lượng giá trị không giới hạn. Khi cần điều tra sâu, lưu dữ liệu giới hạn trong nhật ký được kiểm soát truy cập.

Địa chỉ mạng và chuỗi proxy có thể là dữ liệu nhạy cảm. Chỉ giữ phần cần thiết, có thời hạn và mục đích; không ghi thêm recovery token, OTP hay URL chứa bí mật vào sự kiện rate limit.

### 14.2. Ghi được lý do quyết định

~~~json
{
  "eventType": "RECOVERY_NETWORK_LIMIT_DECISION",
  "actionGroup": "RECOVERY_MESSAGE_REQUEST",
  "decision": "LIMIT",
  "networkFamily": "IPv6",
  "prefixLength": 64,
  "sourceResolution": "TRUSTED_PROXY_CHAIN",
  "policyVersion": "example-network-policy-v2",
  "requestId": "request_example_44",
  "accountMutationApplied": false
}
~~~

Ví dụ không chứa địa chỉ thật hoặc bí mật recovery. Nếu cần tham chiếu nguồn để điều tra, dùng định danh có kiểm soát theo chính sách lưu trữ; không coi việc băm địa chỉ là đã loại bỏ mọi yêu cầu bảo vệ dữ liệu.

Khi thay độ rộng prefix, quota hoặc danh sách proxy tin cậy, xem tác động đến phân nhóm và ngân sách đang tồn tại. Một thay đổi nhìn như cấu hình nhỏ có thể gộp nhiều người vào một bucket hoặc mở lại nhiều bucket đầy.

Có thể đánh giá quyết định dự kiến trước khi áp dụng hạn chế mạnh hơn và theo dõi kết quả sau thay đổi. Mục tiêu là hiểu tác động thực tế, không chỉ tăng tỷ lệ request bị chặn.

## 15. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Hướng xử lý |
| --- | --- | --- |
| Lấy phần tử đầu X-Forwarded-For | Client đổi khóa giới hạn bằng header | Dựa vào peer và chuỗi proxy được tin cậy |
| Chỉ đếm peer của ứng dụng sau proxy | Gộp mọi người vào IP ingress | Cấu hình nguồn theo topology thực tế |
| Dùng chuỗi IPv6 nguyên bản làm khóa | Cùng địa chỉ có nhiều khóa | Phân tích literal và chuẩn hóa nhị phân |
| Dùng /64 như quy tắc đúng cho mọi mạng | Gộp hoặc chia sai người dùng | Chọn prefix theo mô hình và dữ liệu vận hành |
| Mỗi instance có quota đầy đủ riêng | Tổng hạn mức bị nhân lên | Phối hợp hoặc phân bổ ngân sách rõ |
| TTL bucket quá ngắn | Khởi tạo lại cấp burst sớm | Bảo toàn trạng thái theo thời gian nạp |
| Mỗi endpoint một trần không liên quan | Đổi route để né giới hạn | Nhóm theo tác động nghiệp vụ |
| Hạn chế IP rồi khóa các tài khoản liên quan | Người cùng NAT bị mất quyền truy cập | Tách hạn chế nguồn khỏi quyết định tài khoản |
| Dùng mạng quen thuộc để bỏ qua xác minh | IP bị xem nhầm là danh tính | Giữ nguyên bằng chứng sở hữu và quyền hành động |
| Kho limiter lỗi thì cho phép vô hạn | Mất bảo vệ khi hệ thống yếu nhất | Dự phòng hữu hạn hoặc từ chối có kiểm soát |

Giới hạn theo mạng có giá trị khi nguồn được xác định đáng tin cậy, nhóm địa chỉ được chọn phù hợp và ngân sách thực sự được cưỡng chế trong phạm vi đã cam kết. Nó giúp giảm lạm dụng recovery, nhưng không thay thế xác minh danh tính, chống phát lại hoặc kiểm soát session của tài khoản.

## Tài liệu tham khảo

- [MDN — X-Forwarded-For](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Forwarded-For): lựa chọn địa chỉ qua proxy và các vấn đề tin cậy.
- [RFC 6585 — 429 Too Many Requests](https://www.rfc-editor.org/rfc/rfc6585.html#section-4): ngữ nghĩa phản hồi hạn chế tần suất.
- [RFC 7421 — Analysis of the 64-bit Boundary in IPv6 Addressing](https://www.rfc-editor.org/rfc/rfc7421.html): bối cảnh ranh giới /64 trong IPv6.
- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): chống lạm dụng và tránh dò tài khoản trong luồng đặt lại mật khẩu.
