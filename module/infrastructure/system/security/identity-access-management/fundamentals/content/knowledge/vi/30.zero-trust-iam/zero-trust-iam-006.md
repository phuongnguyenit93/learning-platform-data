# Network context

## 1. Ngữ cảnh mạng là một tín hiệu của quyết định truy cập

Trong IAM theo tư duy Zero Trust, **network context** là tập thông tin về môi trường mạng và đường kết nối liên quan đến một yêu cầu truy cập. Nó có thể gồm địa chỉ nguồn quan sát được, vùng mạng, đường đi qua VPN hoặc proxy đã quản lý, vị trí địa lý suy ra và các dấu hiệu thay đổi kết nối.

Ví dụ, cùng một người dùng có thể truy cập hệ thống từ văn phòng, qua VPN khi làm việc từ xa hoặc qua mạng di động. Một yêu cầu từ đường quản trị được tổ chức kiểm soát có ngữ cảnh khác một yêu cầu đi trực tiếp từ Internet.

Tuy nhiên, thông tin mạng không tự trả lời đầy đủ hai câu hỏi: người gọi là ai và người gọi được làm gì. Nhiều người có thể cùng xuất hiện dưới một địa chỉ IP; một thiết bị nằm trong mạng nội bộ vẫn có thể bị chiếm quyền.

Nguyên tắc cốt lõi là:

> Sử dụng ngữ cảnh mạng để bổ sung điều kiện và đánh giá rủi ro, đồng thời tiếp tục xác thực danh tính và kiểm tra quyền đối với tài nguyên.

Một request từ mạng công ty không được tự động trở thành request quản trị. Ngược lại, một request từ mạng bên ngoài không nhất thiết phải bị từ chối nếu hệ thống có chính sách cho phép làm việc từ xa với đủ điều kiện.

## 2. Những thành phần thường gặp của network context

| Thành phần | Điều có thể hỗ trợ đánh giá | Giới hạn cần hiểu |
| --- | --- | --- |
| Địa chỉ IP nguồn quan sát được | Kết nối đến từ địa chỉ nào tại điểm quan sát | Có thể là địa chỉ NAT, VPN hoặc proxy, không phải một người duy nhất |
| Dải mạng hoặc vùng mạng | Kết nối có đi từ phạm vi đã quản lý không | Thành viên trong dải mạng vẫn cần xác thực và phân quyền |
| Đường VPN hoặc cổng truy cập | Request có đi qua một đường kết nối được kiểm soát không | Việc đã vào VPN không chứng minh mọi hành động đều hợp lệ |
| Proxy, gateway hoặc đường ingress | Request đi qua các điểm kiểm soát nào | Header về đường đi chỉ đáng tin nếu nguồn và chuỗi chuyển tiếp được bảo vệ |
| Vị trí địa lý suy ra từ IP | Dấu hiệu tương đối về khu vực kết nối | Không phải bằng chứng chắc chắn về vị trí vật lý của con người |
| Thay đổi địa chỉ hoặc vùng mạng | Phiên có chuyển ngữ cảnh so với trước không | Có thể do chuyển mạng hợp lệ, không nhất thiết là chiếm phiên |
| Tín hiệu an ninh về địa chỉ nguồn | Có dấu hiệu cần xem xét thêm không | Chất lượng, độ mới và độ bao phủ của nguồn tín hiệu có giới hạn |

Không nên gộp tất cả thành một cờ `trustedNetwork=true` mà không giữ lại ý nghĩa và nguồn của dữ liệu. Một địa chỉ thuộc dải văn phòng và một kết nối đi qua cổng quản trị được xác thực có thể hỗ trợ những điều kiện khác nhau.

Cũng cần phân biệt ngữ cảnh mạng với ngữ cảnh thiết bị. IP trong dải doanh nghiệp không chứng minh máy đang đáp ứng chính sách bản vá, được quản lý hay do đúng người sở hữu sử dụng. Những thuộc tính đó cần nguồn kiểm chứng riêng.

## 3. Vì sao địa chỉ IP không phải danh tính?

### 3.1. Nhiều chủ thể cùng chia sẻ một địa chỉ

NAT, proxy và các cổng ra Internet có thể khiến nhiều người dùng hoặc workload cùng xuất hiện dưới một IP công cộng. Nếu hệ thống cấp quyền chỉ theo IP đó, quyền có thể được trao cho những chủ thể không có cùng vai trò hay nhiệm vụ.

Ví dụ, đội phát triển và đội kế toán cùng đi qua một cổng mạng. Địa chỉ nguồn giống nhau không có nghĩa kỹ sư được đọc dữ liệu lương của kế toán.

### 3.2. Một chủ thể có thể xuất hiện dưới nhiều địa chỉ

Một người có thể chuyển từ Wi-Fi sang mạng di động, đổi đường VPN hoặc dùng các tuyến IPv4/IPv6 khác nhau. Dịch vụ cũng có thể thay đổi địa chỉ ra ngoài khi hạ tầng điều chỉnh.

Vì vậy, buộc mọi phiên phải giữ nguyên một địa chỉ IP trong mọi hoàn cảnh có thể gây gián đoạn không cần thiết. Cách phản ứng phải phù hợp với tài nguyên và chính sách phiên, thay vì coi mọi thay đổi IP đều là tấn công.

### 3.3. Địa chỉ nhìn thấy phụ thuộc điểm quan sát

Ứng dụng sau reverse proxy thường nhìn thấy kết nối trực tiếp từ proxy. Một dịch vụ đích có thể chỉ quan sát được IP của gateway hoặc dịch vụ gọi gần nhất. Địa chỉ đó không tự đại diện cho người dùng ban đầu.

Khi phân tích network context, cần nói rõ: IP được quan sát ở đâu, thuộc chặng nào và đang được dùng để đánh giá chủ thể nào.

## 4. Thu thập ngữ cảnh mạng qua proxy một cách có kiểm soát

Xét một đường truy cập:

```text
Client
   |
   v
Edge proxy
   |
   v
Gateway nội bộ
   |
   v
Ứng dụng
```

Ứng dụng có thể cần địa chỉ kết nối ban đầu do các proxy chuyển tiếp. Các header như `Forwarded` hoặc `X-Forwarded-For` có thể chứa thông tin liên quan, nhưng tên header không tự tạo ra tính xác thực.

Nếu một client có thể tự gửi:

```http
X-Forwarded-For: 10.20.30.40
X-Network-Zone: corporate
```

thì ứng dụng không được coi request đã đến từ mạng doanh nghiệp chỉ vì các giá trị đó xuất hiện.

Một thiết kế cần xác định rõ:

1. Proxy hoặc gateway nào được phép cung cấp thông tin mạng cho ứng dụng.
2. Kết nối giữa các điểm đó được xác minh và bảo vệ như thế nào.
3. Header do client gửi được loại bỏ, ghi đè hoặc xử lý ra sao tại điểm vào.
4. Các proxy hợp lệ bổ sung dữ liệu theo quy tắc nào.
5. Thành phần nào diễn giải chuỗi chuyển tiếp và tạo ngữ cảnh chuẩn hóa cho policy engine.
6. Người gọi có thể bỏ qua đường kiểm soát để truy cập trực tiếp ứng dụng hay không.

Không có quy tắc “luôn lấy phần tử đầu tiên” hoặc “luôn lấy phần tử cuối cùng” đúng cho mọi kiến trúc proxy. Cách chọn địa chỉ phải phù hợp với chuỗi proxy đáng tin cậy và quy tắc xử lý header đã triển khai.

Nếu cho phép đường truy cập trực tiếp, nó phải có chính sách riêng phù hợp; không được để client giả mạo thông tin như thể request đã qua gateway. Nếu thiết kế yêu cầu mọi request đi qua gateway, đường truy cập trực tiếp cần được chặn bằng những kiểm soát tương ứng.

Một ngữ cảnh chuẩn hóa có thể chứa:

```text
observedPeerAddress: địa chỉ của bên kết nối trực tiếp
effectiveSourceAddress: địa chỉ nguồn đã được phân giải theo quy tắc
networkZone: vùng được hệ thống ánh xạ
ingressId: định danh đường vào được xác minh
provenance: nguồn và cách xác lập thông tin
observedAt: thời điểm quan sát
quality: verified | partial | unknown
```

Đây là mô hình minh họa. Giá trị `verified` chỉ có nghĩa dữ liệu đã qua cơ chế xác minh được định nghĩa; nó không khẳng định chủ thể hoặc thiết bị hoàn toàn an toàn.

## 5. Kết hợp ngữ cảnh mạng với danh tính và quyền

Một quyết định truy cập cần xác định chủ thể, hành động, tài nguyên và những điều kiện bắt buộc. Network context là một nhóm điều kiện trong quyết định đó.

Ví dụ, hệ thống quản lý tài khoản có hai thao tác:

- Nhân viên xem thông tin hồ sơ của mình từ môi trường làm việc được cho phép.
- Quản trị viên thay đổi phương thức khôi phục của người khác, với điều kiện truy cập quản trị chặt hơn.

Chính sách minh họa:

```text
evaluate(subject, action, resource, context):
    if not subject.authenticated or not subject.active:
        return DENY

    if not authorization.hasPermission(subject, action, resource):
        return DENY

    if action == "profile.read-own":
        require resource.owner == subject.id
        require context.session.meetsStandardPolicy
        return ALLOW

    if action == "recovery-method.change-for-other":
        require context.session.meetsAdminAuthenticationPolicy
        require context.device.meetsAdminDevicePolicy
        require context.network.quality == "verified"
        require context.network.isFreshEnough
        require context.network.ingressId == "managed-admin-ingress"
        require context.network.zone in allowedAdminZones
        return ALLOW

    return DENY
```

Trong mã giả này, `require` thất bại dẫn đến từ chối; chưa có lệnh thay đổi tài nguyên nào được thực hiện trước quyết định cho phép. Các thuộc tính mạng và thiết bị do thành phần tin cậy cung cấp, không lấy trực tiếp từ dữ liệu client tự khai báo.

Ví dụ thể hiện một chính sách cụ thể, không phải quy định rằng mọi ứng dụng Zero Trust đều phải đi qua cùng một loại ingress. Hệ thống có thể sử dụng cách kiểm soát khác nếu đáp ứng yêu cầu bảo vệ tài nguyên.

Một người không có quyền thay đổi phương thức khôi phục vẫn bị từ chối ngay cả khi đang ở đúng vùng mạng. Tương tự, làm thêm MFA không tự thay thế điều kiện bắt buộc về đường quản trị hoặc cấp một quyền nghiệp vụ còn thiếu.

## 6. Phân biệt điều kiện bắt buộc và tín hiệu rủi ro

Network context có thể được dùng theo hai cách khác nhau.

**Điều kiện bắt buộc** là một ràng buộc mà request phải đáp ứng. Ví dụ, thao tác quản trị hạ tầng chỉ được thực hiện qua đường quản trị được kiểm soát. Nếu không chứng minh được điều kiện này, hệ thống từ chối theo chính sách.

**Tín hiệu rủi ro** hỗ trợ đánh giá nhưng không tự quyết định mọi thứ. Ví dụ, đăng nhập từ một vùng địa lý chưa từng thấy có thể dẫn đến xác minh bổ sung, giới hạn phiên hoặc đánh giá thêm.

| Tình huống | Cách diễn giải phù hợp | Phản ứng có thể được thiết kế |
| --- | --- | --- |
| Request quản trị bỏ qua đường vào bắt buộc | Vi phạm một điều kiện truy cập | Từ chối |
| IP thay đổi sau khi người dùng chuyển Wi-Fi sang di động | Ngữ cảnh thay đổi, chưa đủ kết luận bị chiếm phiên | Đánh giá lại theo mức nhạy cảm của phiên và hành động |
| Vị trí suy ra từ IP khác khu vực quen thuộc | Tín hiệu cần xem xét cùng các bằng chứng khác | Xác minh thêm hoặc giới hạn truy cập theo chính sách |
| Tín hiệu mạng thiếu nguồn xác minh | Chưa có bằng chứng đáng tin về ngữ cảnh cần kiểm tra | Áp dụng quy tắc thiếu dữ liệu, không tự coi là đạt |
| IP thuộc dải văn phòng nhưng tài khoản đã bị khóa | Mạng không bù được trạng thái tài khoản | Từ chối |

Một điểm rủi ro thấp không nên vô hiệu hóa điều kiện bắt buộc. Nếu chính sách cấm truy cập tài nguyên ngoài tenant, địa chỉ mạng thuận lợi không tạo ra ngoại lệ liên tenant.

Ngược lại, cần tránh tăng mức độ chắc chắn quá mức từ một tín hiệu yếu. Vị trí IP có thể phản ánh điểm thoát của VPN hoặc proxy. Một cảnh báo di chuyển bất thường cần được diễn giải trong bối cảnh đó, thay vì được xem là bằng chứng tuyệt đối về vị trí người dùng.

## 7. VPN, mạng nội bộ và phân đoạn mạng có vai trò gì?

### 7.1. VPN kiểm soát một đường kết nối

VPN có thể giúp bảo vệ đường truyền và kiểm soát việc kết nối vào một phạm vi mạng. Nó không tự thay thế việc kiểm tra quyền ở ứng dụng.

Nếu người dùng được vào VPN để truy cập ứng dụng nhân sự, điều đó không có nghĩa họ được đọc dữ liệu cơ sở hạ tầng hoặc gọi API quản trị danh tính. Tài nguyên vẫn phải kiểm tra bằng chứng xác thực và quyền cần thiết.

Một tài khoản VPN bị chiếm, một endpoint bị xâm nhập hoặc một cấu hình quyền quá rộng có thể tạo đường đi vào hệ thống. Vì vậy, không biến “đã kết nối VPN” thành trạng thái tin cậy toàn cục.

### 7.2. Mạng nội bộ là phạm vi vận hành, không phải chứng nhận danh tính

Trong mạng nội bộ có thể tồn tại nhân viên, khách, thiết bị dùng chung, máy thử nghiệm và workload. Các nhóm này không có cùng nhu cầu truy cập.

Cho phép mọi kết nối nội bộ bỏ xác thực hoặc dùng chung một vai trò rộng làm mất khả năng phân biệt chủ thể. Việc ghi log cũng trở nên kém hữu ích nếu hệ thống chỉ biết “một IP nội bộ đã làm”.

### 7.3. Phân đoạn mạng bổ trợ cho IAM

Phân đoạn mạng giúp giới hạn các kết nối có thể đến tài nguyên. IAM tiếp tục giới hạn chủ thể và hành động được phép sau khi kết nối đã tới nơi.

Ví dụ, một service báo cáo được phép kết nối tới API dữ liệu nhưng chỉ được đọc một tập dữ liệu nhất định. Chính sách mạng không nhất thiết diễn đạt được mọi điều kiện nghiệp vụ đó; service đích vẫn phải thực thi quyền.

Hai lớp cùng có ích: giảm đường tiếp cận không cần thiết và giới hạn tác vụ có thể thực hiện trên đường tiếp cận hợp lệ.

## 8. Ngữ cảnh mạng trong giao tiếp giữa các workload

Với service-to-service, địa chỉ IP của workload có thể thay đổi do khởi động lại, mở rộng hoặc thay đổi hạ tầng. Nhiều workload cũng có thể dùng chung một địa chỉ ra ngoài.

Do đó, một chính sách chỉ cho phép theo IP thường không biểu diễn đầy đủ danh tính và trách nhiệm của workload. Cần xác thực workload bằng cơ chế phù hợp với nền tảng, rồi cấp quyền theo chức năng và tài nguyên.

Ví dụ, API thanh toán nhận request từ một gateway nội bộ. Gateway đã xác thực không có nghĩa mọi request phía sau được phép hoàn tiền. API còn cần biết danh tính thực thi, mô hình ủy quyền và quyền đối với giao dịch đích.

Nếu gateway chuyển thông tin về người dùng gốc hoặc mạng gốc, dữ liệu đó phải được bảo vệ và có ý nghĩa được định nghĩa rõ. Service không nên trộn IP của gateway với IP của người dùng rồi coi chúng là cùng một bằng chứng.

Ngữ cảnh mạng vẫn có thể làm điều kiện bổ sung: đúng môi trường, đúng đường kết nối, đúng vùng dịch vụ. Nó không nên thay thế vai trò của danh tính workload hoặc tạo quyền rộng chỉ vì hai service ở cùng cụm.

## 9. Độ mới, cache và thay đổi trong phiên

Ngữ cảnh mạng là dữ liệu có thể thay đổi. Thông tin quan sát ở lúc đăng nhập không nhất thiết mô tả đúng kết nối khi thực hiện một tác vụ nhạy cảm nhiều giờ sau đó.

Cần xác định:

- Những thuộc tính nào được quan sát lại trên mỗi request hoặc mỗi kết nối.
- Những thuộc tính nào được kế thừa từ phiên và có hiệu lực bao lâu.
- Sự kiện thay đổi nào dẫn đến đánh giá lại hoặc yêu cầu xác thực bổ sung.
- Với phiên dài hoặc kết nối liên tục, cơ chế nào phát hiện và xử lý thay đổi liên quan.

Không nên chỉ ghi một cờ “đăng nhập từ văn phòng” vào phiên rồi dùng cờ đó cho mọi tác vụ về sau. Nếu quyền quản trị phụ thuộc đường vào hiện tại, phải có cách xác minh điều kiện tại thời điểm chính sách yêu cầu.

Cache quyết định phân quyền cũng cần tính đến ngữ cảnh ảnh hưởng quyết định. Một kết quả cho phép khi request đi qua đường quản trị không nên được tái sử dụng cho request đi qua đường khác chỉ vì cùng người dùng và API.

Khi ngữ cảnh không còn đáp ứng, phản ứng có thể là từ chối tác vụ, giảm phạm vi, xác minh lại hoặc kết thúc phiên tùy thiết kế. Cần hiểu khả năng thực tế của hệ thống: thay đổi một chính sách không tự bảo đảm mọi kết nối và token đang tồn tại bị vô hiệu hóa ngay lập tức.

## 10. Cấu hình dải mạng và xử lý dữ liệu không xác định

Một danh sách dải mạng cần có người sở hữu, mục đích, phạm vi áp dụng và quy trình thay đổi. Dải dùng cho văn phòng không nên mặc nhiên được dùng cho mọi tác vụ quản trị.

Khi đánh giá địa chỉ thuộc dải, cần phân tích và so sánh địa chỉ mạng bằng thư viện phù hợp, xử lý rõ IPv4, IPv6 và các biểu diễn được hệ thống hỗ trợ. Không dùng phép kiểm tra chuỗi đơn giản như `startsWith("10.")` để thay thế logic chính sách mạng.

Cần kiểm tra cả đường truy cập được hỗ trợ thực tế. Nếu ứng dụng có IPv4 và IPv6, một chính sách chỉ được xác minh trên một đường có thể để đường còn lại hoạt động ngoài dự kiến.

Nếu bộ phân giải IP, nguồn vị trí hoặc kho cấu hình gặp lỗi, hệ thống phải áp dụng quy tắc đã định nghĩa. `unknown` khác với “đã chứng minh nằm ngoài dải” và cũng khác với “đã chứng minh nằm trong dải”.

Với điều kiện mạng bắt buộc cho tác vụ nhạy cảm, không xác minh được điều kiện không được âm thầm biến thành cho phép. Nếu có chế độ suy giảm hoặc truy cập khẩn cấp, phạm vi, thời hạn, người được sử dụng và việc giám sát phải được thiết kế riêng.

## 11. Ghi nhận và kiểm chứng network context

Nhật ký nên giúp giải thích được quyết định: chủ thể nào, hành động nào, tài nguyên nào, ngữ cảnh mạng được xác lập từ đâu và điều kiện nào đã được áp dụng.

Một sự kiện minh họa:

```json
{
  "subjectId": "principal-1042",
  "action": "recovery-method.change-for-other",
  "resourceId": "account-2050",
  "ingressId": "managed-admin-ingress",
  "networkZone": "admin-zone",
  "networkContextQuality": "verified",
  "decision": "DENY",
  "reasonCode": "MISSING_REQUIRED_PERMISSION",
  "correlationId": "request-902"
}
```

Ví dụ cố ý cho thấy một request có ngữ cảnh mạng phù hợp vẫn có thể bị từ chối vì thiếu quyền. Chỉ log địa chỉ IP hoặc chỉ log “mạng tin cậy” sẽ khó giải thích được kết quả này.

Thông tin mạng có thể phản ánh hoạt động và vị trí tương đối của người dùng. Cần giới hạn người được đọc, mục đích và thời gian lưu phù hợp. Không đưa mật khẩu, token hoặc dữ liệu bí mật không cần thiết vào log để phục vụ phân tích mạng.

Các tình huống kiểm chứng quan trọng gồm:

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Client tự khai IP nội bộ trong header chuyển tiếp | Không thể giả ngữ cảnh mạng được tin cậy |
| Request cố truy cập trực tiếp ứng dụng phía sau gateway | Bị chặn hoặc chịu chính sách riêng đúng thiết kế |
| Người dùng hợp lệ nhưng thiếu quyền, đi từ văn phòng | Không được cấp thêm quyền chỉ vì vị trí mạng |
| Nhiều người cùng IP NAT | Quyết định và nhật ký vẫn gắn đúng danh tính |
| Người dùng chuyển Wi-Fi sang mạng di động | Phản ứng theo chính sách, không mặc định mọi thay đổi là chiếm phiên |
| Proxy hoặc VPN thay đổi điểm thoát | Vị trí IP được diễn giải với giới hạn của đường kết nối |
| Request chuyển từ đường quản trị sang đường thường | Không tái sử dụng quyết định cho phép với ngữ cảnh cũ |
| IPv4 được kiểm soát nhưng ứng dụng còn IPv6 | Không tồn tại đường truy cập ngoài chính sách dự kiến |
| Nguồn tín hiệu mạng lỗi hoặc quá cũ | Không tự đánh dấu điều kiện bắt buộc là đã đạt |
| Workload cùng mạng gọi một API không được cấp quyền | Bị từ chối tại điểm thực thi quyền |

Network context có giá trị khi được thu thập đúng nguồn, diễn giải đúng giới hạn và kết hợp với danh tính, quyền cùng trạng thái phiên. Trong Zero Trust, mạng giúp mô tả điều kiện của truy cập; quyết định cuối cùng vẫn phải gắn với chủ thể, hành động và tài nguyên cụ thể.
