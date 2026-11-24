# Tra cứu username trong quá trình khôi phục tài khoản

Trong chương **Identifier Handling** của module **SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY**, **username lookup during recovery** là việc xử lý tên đăng nhập để tìm đúng tài khoản hoặc giúp chủ tài khoản lấy lại thông tin đăng nhập đã quên.

Người dùng có thể còn mật khẩu, MFA hoặc passkey nhưng không nhớ username. Ngược lại, một người yêu cầu có thể biết chính xác username mà chưa kiểm soát bất kỳ phương thức xác thực nào. Hai tình huống này cần những cách xử lý khác nhau.

Mục tiêu của bài học là tìm đúng tài khoản trong khi giữ giới hạn tiết lộ dữ liệu và quyền khôi phục. Biết username không chứng minh quyền sở hữu; tìm được username cũng không tự cấp quyền đặt lại mật khẩu, gỡ MFA hay tạo phiên đăng nhập.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt username, định danh tài khoản nội bộ, tên hiển thị và kênh khôi phục.
- Tách tra cứu tài khoản bằng username khỏi hành trình quên username.
- Thiết kế tra cứu chính xác, nhất quán với quy tắc đăng ký và đăng nhập.
- Xử lý đổi tên, bí danh, tái sử dụng username và nhiều phạm vi tổ chức.
- Ngăn biểu mẫu tra cứu trở thành công cụ dò tài khoản hoặc liên kết email với danh tính.
- Cấp quyền tìm thông tin đăng nhập theo phạm vi, không gộp với quyền khôi phục toàn bộ tài khoản.

## 2. Username có vai trò gì?

Username là một định danh mà sản phẩm cho phép sử dụng để nhận diện tài khoản trong một ngữ cảnh. Nó thường không phải bí mật xác thực.

| Thành phần | Ví dụ minh họa | Vai trò |
| --- | --- | --- |
| Username | an.nguyen | Tên đăng nhập theo quy tắc sản phẩm |
| Định danh nội bộ | account-482 | Liên kết ổn định giữa giao dịch, credential và tài khoản |
| Tên hiển thị | An Nguyễn | Nội dung giao diện; có thể trùng giữa nhiều người |
| Email liên hệ | an@example.test | Địa chỉ nhận thông tin; chỉ là kênh khôi phục khi được thiết lập phù hợp |
| Định danh tại bên quản lý danh tính | Một tham chiếu do bên quản lý cung cấp | Liên kết với danh tính ngoài theo mô hình tích hợp |

Không nên dùng tên hiển thị làm căn cứ duy nhất để quyết định tài khoản đích. Cũng không nên coi mọi email trong hồ sơ là tên đăng nhập hoặc kênh được phép nhận quyền khôi phục.

Username có thể công khai trên hồ sơ nhưng mối liên hệ giữa username và email, số điện thoại, tổ chức hoặc trạng thái bảo mật vẫn có thể cần được bảo vệ.

### Hai nghĩa của việc tra cứu

**Tra cứu bằng username:** người dùng nhập username để hệ thống xác định nội bộ tài khoản cần khôi phục.

**Tìm lại username:** người dùng quên username và sử dụng một đường phù hợp để biết lại thông tin đăng nhập của mình.

Ở nghĩa thứ nhất, hệ thống cần tránh tiết lộ kết quả tra cứu cho người chưa có quyền. Ở nghĩa thứ hai, hệ thống cần xác minh căn cứ cho việc tiết lộ thông tin đăng nhập. Không được dùng một API công khai trả danh sách username cho bất kỳ ai biết một email.

## 3. Xác định trước phạm vi tra cứu

Một chuỗi username có thể chỉ duy nhất trong một tổ chức, không duy nhất trên toàn sản phẩm. Cần biết phạm vi nào đang áp dụng trước khi tìm tài khoản.

Ví dụ, tổ chức A và tổ chức B đều có username “an”. Không được tìm toàn hệ thống rồi lấy bản ghi đầu tiên, hoặc chọn theo ngày tạo tài khoản gần nhất.

Một khóa tra cứu có thể được hiểu về mặt khái niệm là:

~~~text
khóa_tra_cứu = phạm_vi + loại_định_danh + giá_trị_theo_quy_tắc_sản_phẩm
~~~

Phạm vi cần được xác định qua ngữ cảnh mà sản phẩm hỗ trợ, chẳng hạn điểm đăng nhập của tổ chức hoặc lựa chọn phù hợp. Dữ liệu do client gửi vẫn phải được máy chủ kiểm tra; một trường “tenantId” không tự là quyền tác động tới tổ chức đó.

Việc yêu cầu người dùng chỉ rõ phạm vi cũng cần tránh làm lộ thêm thông tin. Không nên gợi ý danh sách mọi tổ chức có người dùng trùng email cho một người chưa được phép biết.

### Quyền khôi phục phải giữ tài khoản đích ổn định

Sau khi xác định tài khoản, giao dịch nên liên kết với định danh nội bộ và phạm vi tổ chức. Không chỉ lưu username rồi tra cứu lại tên đó tại bước đổi credential.

Nếu username đổi hoặc được cấp cho người khác trong lúc giao dịch đang diễn ra, một quyền đã phát hành cho tài khoản cũ không được chuyển sang tài khoản mới.

## 4. Chuẩn hóa phải nhất quán với đăng ký và đăng nhập

Tra cứu khôi phục cần sử dụng cùng quy tắc so sánh định danh đã được sản phẩm xác định. Nếu đăng nhập và khôi phục hiểu một chuỗi khác nhau, người dùng có thể bị đưa nhầm tài khoản.

Những quyết định cần ghi rõ gồm:

- Username có phân biệt chữ hoa và chữ thường không?
- Khoảng trắng ở đầu hoặc cuối được từ chối hay được xử lý theo quy tắc nào?
- Những ký tự nào được chấp nhận?
- Nếu hỗ trợ ký tự Unicode, cách chuẩn hóa và so sánh được định nghĩa ra sao?
- Bí danh nào được chấp nhận và do đâu thiết lập?
- Khi quy tắc thay đổi, dữ liệu cũ và các trường hợp xung đột được xử lý thế nào?

Không tự chuyển mọi username thành chữ thường nếu sản phẩm cho phép hai tên khác nhau theo chữ hoa. Không xóa dấu chấm, khoảng trắng bên trong hoặc ký tự phân cách chỉ vì muốn tìm được nhiều kết quả hơn.

Ví dụ, “an.nguyen” và “annguyen” chỉ được xem là cùng tên khi quy tắc sản phẩm thật sự định nghĩa như vậy. Sự giống nhau khi nhìn không tự tạo ra quan hệ sở hữu.

### Không dùng tìm gần đúng để tự chọn tài khoản

Tìm gần đúng có thể phù hợp với một số chức năng tìm kiếm nội dung, nhưng không nên tự quyết định tài khoản khôi phục.

Những cách như chọn tên gần nhất, tìm theo tiền tố rồi lấy kết quả đầu hoặc coi ký tự trông giống nhau là tương đương có thể tạo sai tài khoản đích.

Nếu người dùng không nhớ đủ username, cần chuyển sang đường tìm lại thông tin đăng nhập được thiết kế riêng, thay vì mở rộng truy vấn cho đến khi có một tài khoản khớp.

### Tránh xung đột giữa các thành phần

Quy tắc ở giao diện, dịch vụ xác thực, cơ sở dữ liệu và cache phải nhất quán. Một thành phần phân biệt chữ hoa còn thành phần khác không phân biệt có thể tạo kết quả khác nhau.

Có thể lưu phiên bản quy tắc để quản lý thay đổi và điều tra. Tuy nhiên, thêm phiên bản không giải quyết xung đột nếu hai bản ghi cùng trở thành một khóa theo quy tắc mới. Việc chuyển đổi cần phát hiện xung đột và xử lý trước khi dùng kết quả để cấp quyền.

## 5. Tra cứu bằng username mà không công khai kết quả

Một luồng công khai có thể nhận username, xác định tài khoản nội bộ rồi xử lý theo chính sách. Nó không cần trả ngay tài khoản có tồn tại hay không.

Ví dụ phản hồi:

> Nếu thông tin phù hợp với một tài khoản và đường khôi phục được hỗ trợ, hướng dẫn sẽ được gửi.

Phản hồi này không được ngầm hứa rằng có thể gửi tới bất kỳ địa chỉ người yêu cầu nhập thêm. Đích nhận phải đến từ đường đã được thiết lập và đủ điều kiện phía máy chủ.

| Hành vi dễ tiết lộ | Thông tin có thể bị suy ra |
| --- | --- |
| “Không tìm thấy username” đối lập với “Đã gửi email” | Sự tồn tại của tài khoản |
| Chỉ username thật mới chuyển sang màn hình MFA | Cấu hình xác thực |
| Hiển thị ảnh đại diện hoặc tên thật ngay sau tra cứu | Liên hệ giữa định danh và hồ sơ |
| Trả email hoặc số điện thoại được che bớt | Mối liên hệ với thông tin liên hệ |
| Khác mã phản hồi, đường chuyển trang hoặc thời gian rõ rệt | Kết quả tra cứu dù câu chữ giống nhau |
| API gửi lại trả chi tiết khác với API ban đầu | Kết quả có thể bị dò qua một đường khác |

Che bớt email hoặc số điện thoại không tự làm thông tin phù hợp để công khai. Độ dài, miền email, đuôi số và số lượng lựa chọn vẫn có thể hỗ trợ suy luận.

Thông tin nhạy cảm cũng không nên được gửi xuống HTML ẩn hoặc dữ liệu API rồi chỉ che bằng giao diện. Giới hạn tiết lộ phải được thực thi phía máy chủ.

### Kết quả nội bộ có thể chi tiết hơn phản hồi công khai

Nội bộ có thể cần phân biệt không tìm thấy, sai phạm vi, định danh đã ngừng dùng, tài khoản không đủ điều kiện hoặc lỗi tải dữ liệu. Những kết quả này phục vụ xử lý và kiểm toán.

Chúng không mặc nhiên được trả toàn bộ cho người chưa xác minh. Một lỗi vận hành cũng không nên bị xử lý thành quyền tiếp tục trên một tài khoản chưa xác định rõ.

## 6. Hành trình người dùng quên username

Khi người dùng quên username, một đường minh họa là sử dụng kênh khôi phục đã thiết lập để nhận hướng dẫn hoặc hoàn thành xác minh có phạm vi.

Các bước có thể gồm:

1. Người dùng chọn “quên tên đăng nhập”.
2. Hệ thống nhận thông tin liên hệ theo định dạng được hỗ trợ.
3. Máy chủ tra cứu trong phạm vi phù hợp và áp dụng điều kiện tài khoản, kênh cùng kiểm soát lạm dụng.
4. Phần công khai trả phản hồi chung, không hiển thị danh sách tài khoản.
5. Nếu có đường đủ điều kiện, hệ thống gửi hướng dẫn tới kênh hợp lệ do máy chủ xác định.
6. Người yêu cầu hoàn tất bước xác minh được thiết kế.
7. Hệ thống chỉ tiết lộ thông tin đăng nhập được phép cho mục đích này.

~~~mermaid
flowchart TD
    A[Quên username] --> B[Nhập thông tin theo đường được hỗ trợ]
    B --> C[Tiếp nhận với phản hồi công khai phù hợp]
    C --> D[Tra cứu và kiểm tra điều kiện nội bộ]
    D --> E{Có đường đủ điều kiện?}
    E -- Có --> F[Gửi hướng dẫn tới kênh đã thiết lập]
    E -- Không --> G[Không tiết lộ kết quả tra cứu; hướng dẫn đường khác nếu được phép]
    F --> H[Xác minh bằng chứng có phạm vi]
    H --> I{Đủ điều kiện tiết lộ thông tin đăng nhập?}
    I -- Có --> J[Hiển thị thông tin tối thiểu được phép]
    I -- Chưa --> K[Không cấp thêm quyền; xử lý theo chính sách]
    J --> L[Tiếp tục đăng nhập với các yêu cầu còn áp dụng]
~~~

Đây là một thiết kế minh họa, không phải mọi sản phẩm phải có đường email. Một tài khoản không có kênh phù hợp có thể cần authenticator khác, phiên còn đủ tin cậy hoặc quy trình hỗ trợ được thiết kế trước.

### Gửi username trực tiếp hay gửi đường dẫn xác minh?

Sản phẩm có thể cân nhắc hai lựa chọn:

- Gửi thông tin đăng nhập được phép trực tiếp tới kênh đã thiết lập.
- Gửi hướng dẫn hoặc đường dẫn tới một bước xác minh rồi hiển thị thông tin theo phạm vi.

Lựa chọn thứ nhất đơn giản hơn nhưng thông tin có thể nằm lâu trong hộp thư hoặc xuất hiện trên bản xem trước. Lựa chọn thứ hai có thể kiểm soát phạm vi và thời hạn tốt hơn nếu được triển khai đúng, nhưng thêm bước cho người dùng.

Dù chọn cách nào, cần tránh đưa thông tin tài khoản không cần thiết vào tiêu đề, thông báo đẩy hoặc nội dung có thể bị xem trên thiết bị dùng chung. Kênh nhận phải đủ điều kiện cho mục đích tiết lộ, không chỉ là một địa chỉ có trong hồ sơ.

## 7. Khi một kênh liên hệ gắn với nhiều tài khoản

Một email hoặc số điện thoại có thể được liên kết hợp lệ với nhiều tài khoản trong mô hình sản phẩm. Điều đó không cho phép API công khai trả mọi username và tổ chức liên quan.

Cần xác định chính sách cho ba vấn đề:

- Phạm vi nào người yêu cầu đang muốn tìm.
- Bằng chứng nào cho phép tiết lộ từng mối liên hệ.
- Thông tin nào thật sự cần cho bước đăng nhập tiếp theo.

Không tự chọn một tài khoản theo thứ tự tạo hoặc theo lần hoạt động gần nhất nếu lựa chọn đó có thể sai. Cũng không tự gộp các tài khoản chỉ vì cùng email.

Sau khi người yêu cầu đạt điều kiện thích hợp, sản phẩm có thể cung cấp lựa chọn tối thiểu trong phạm vi được phép. Cần tránh kéo theo dữ liệu của những tổ chức hoặc hồ sơ ngoài phạm vi giao dịch.

### Tài khoản liên kết và tài khoản không dùng username cục bộ

Một ứng dụng có thể có tài khoản chỉ đăng nhập qua bên quản lý danh tính hoặc qua phương thức không cần nhập username theo giao diện hiện tại.

Không nên tự tạo username hoặc mật khẩu cục bộ chỉ để biểu mẫu quên username có kết quả. Hành trình phải phản ánh đúng mô hình đăng nhập đã được hỗ trợ.

Nếu việc hướng dẫn sử dụng bên quản lý danh tính làm lộ quan hệ với tổ chức, mức tiết lộ cũng cần được xem xét theo quyền của người yêu cầu.

## 8. Đổi tên, bí danh và tái sử dụng username

### 8.1. Username đã đổi

Sản phẩm cần quyết định tên cũ còn được chấp nhận trong thời gian nào, cho mục đích nào và có được dùng để bắt đầu khôi phục không.

Một tên cũ có thể được lưu cho kiểm toán nhưng không còn là bí danh đăng nhập. Không nên coi mọi tên từng tồn tại đều là khóa khôi phục đang có hiệu lực.

Nếu hỗ trợ tên cũ, nó cần ánh xạ rõ ràng tới đúng tài khoản và được kiểm tra theo chính sách hiện tại. Không suy luận chủ tài khoản từ lịch sử văn bản tự do.

### 8.2. Username được cấp lại

Giả sử “an.nguyen” từng thuộc tài khoản A rồi được cấp hợp lệ cho B. Một token được phát hành cho A không được tác động tới B chỉ vì token chứa chuỗi username đó.

Quyền khôi phục phải liên kết với định danh tài khoản ổn định, phạm vi, hành động và giao dịch. Username trong thông báo hoặc giao diện chỉ là thông tin trình bày, không được trở thành nguồn quyết định lại tài khoản đích.

### 8.3. Bí danh có trạng thái riêng

Một bí danh có thể đang hoạt động, chỉ giữ cho lịch sử hoặc đã ngừng dùng. Bộ tra cứu cần biết trạng thái nào được phép cho hành động hiện tại.

Nếu dữ liệu có nhiều bản ghi xung đột, kết quả phải được xử lý như tình trạng cần giải quyết nội bộ. Không chọn tùy một tài khoản để tiếp tục cấp quyền.

### 8.4. Tài khoản đã đóng hoặc xóa

Tìm được tên trong dữ liệu cũ không chứng minh tài khoản còn đủ điều kiện khôi phục. Trạng thái vòng đời và chính sách hiện tại vẫn phải được áp dụng.

Một tài khoản mới dùng lại cùng username hoặc email không kế thừa quyền của tài khoản đã xóa. Đường tìm thông tin đăng nhập không được tự trở thành đường tái tạo danh tính cũ.

## 9. Mô hình tra cứu phía máy chủ

Một mô hình khái niệm có thể tách:

- Tài khoản nội bộ và phạm vi tổ chức.
- Bản ghi username hoặc bí danh theo loại, khóa so sánh và trạng thái.
- Kênh được phép dùng cho tìm thông tin đăng nhập.
- Giao dịch có mục đích riêng cho việc tiết lộ định danh.
- Kết quả xác minh và phạm vi quyền đã cấp.

Một truy vấn minh họa:

~~~sql
SELECT account_id
FROM account_alias
WHERE tenant_id = :tenant_id
  AND alias_type = :alias_type
  AND lookup_key = :lookup_key
  AND state = 'ACTIVE';
~~~

Các tham số phải được truyền bằng cơ chế tham số hóa phù hợp. Không ghép trực tiếp chuỗi người dùng vào truy vấn.

Cơ sở dữ liệu và mô hình ứng dụng cần bảo đảm quy tắc duy nhất phù hợp với phạm vi. Nếu phát hiện nhiều tài khoản cho một khóa vốn phải duy nhất, không dùng “lấy bản ghi đầu tiên” để che vấn đề.

Kết quả có thể được xử lý nội bộ như sau:

~~~text
lookupRecoveryTarget(input, allowedScope):
    parsed = parseSupportedIdentifier(input)

    if parsed is invalid:
        return INVALID_INPUT_UNDER_PUBLIC_FORMAT_RULES

    key = applyProductIdentifierRules(parsed)
    matches = lookupAuthoritativeAliases(
        scope = allowedScope,
        type = parsed.type,
        key = key
    )

    if matches has no account:
        return INTERNAL_NO_MATCH

    if matches has conflicting accounts:
        return INTERNAL_AMBIGUOUS_MATCH

    account = loadAccount(matches.singleAccountId)

    if account is not eligible for the requested recovery purpose:
        return INTERNAL_UNAVAILABLE_FOR_PURPOSE

    return INTERNAL_TARGET(
        accountId = account.id,
        tenantId = account.tenantId,
        purpose = requestedPurpose
    )
~~~

Các kết quả nội bộ này không phải hợp đồng phản hồi công khai. Lớp tiếp nhận cần chuyển chúng thành phản hồi đúng với quyền hiện tại của người yêu cầu.

### Không dựa vào kết quả cache như quyền cuối cùng

Cache có thể chứa tên cũ, trạng thái cũ hoặc ánh xạ vừa được thay. Nếu dùng cache cho hiệu năng, cần xác định cách giữ nhất quán và kiểm tra lại dữ liệu ảnh hưởng đến quyền.

Tìm đúng một bản ghi trong cache không đồng nghĩa đã xác minh người yêu cầu. Trước khi cấp quyền hoặc thực hiện thay đổi nhạy cảm, phải kiểm tra các điều kiện cần thiết từ trạng thái có thẩm quyền.

## 10. Quyền tìm username phải có phạm vi riêng

Một token hoặc kết quả xác minh dùng để tìm username nên có mục đích rõ. Ví dụ về mặt khái niệm:

~~~text
purpose: DISCOVER_LOGIN_IDENTIFIER
account: định danh tài khoản đã cố định
scope: phạm vi tổ chức được phép
transaction: giao dịch tìm thông tin đăng nhập
validity: thời hạn theo chính sách
permissions: chỉ tiết lộ thông tin được phép cho mục đích này
~~~

Đây là ví dụ mô hình quyền, không phải yêu cầu dùng một định dạng token cụ thể.

Quyền này không được API đặt lại mật khẩu hoặc gỡ MFA chấp nhận chỉ vì nó có chữ ký hợp lệ. Mục đích, tài khoản, giao dịch, thời hạn và trạng thái sử dụng vẫn phải được kiểm tra.

Nếu người dùng tìm được username rồi tiếp tục quên mật khẩu, bước tiếp theo cần đường cấp quyền tương ứng. Không tự tạo phiên đăng nhập đầy đủ sau khi hiển thị tên đăng nhập.

Khi dùng mã hoặc liên kết dùng một lần, trạng thái tiêu thụ phải được kiểm soát nhất quán. Giao dịch đã hủy, hết hạn hoặc mất điều kiện không được tiếp tục chỉ vì chuỗi token còn đúng cấu trúc.

### Thay đổi dữ liệu giữa lúc phát hành và sử dụng

Trong lúc người dùng chờ mở hướng dẫn, username, kênh, trạng thái tài khoản hoặc chính sách có thể thay đổi.

Hệ thống cần quy tắc cho việc hiển thị thông tin hiện tại hoặc yêu cầu thực hiện lại. Tuyệt đối không tra lại username trong token rồi chuyển sang tài khoản mới đang dùng tên đó.

Nếu kênh bị thu hồi hoặc được xác định không còn đủ điều kiện, cần kiểm tra tác động đến quyền đã phát hành. Việc gửi thông báo trước đó không tạo quyền vĩnh viễn.

## 11. Chống dò và chống lạm dụng

Tra cứu username có thể bị dùng để dò danh sách tài khoản, liên kết email với danh tính hoặc tạo nhiều thông báo. Cần bảo vệ cả đường tra cứu, gửi hướng dẫn, xác minh và truy vấn trạng thái.

Những kiểm soát có thể cần gồm:

- Giới hạn phù hợp theo nguồn, đích nhận, giao dịch và bối cảnh.
- Kiểm soát thử sai cho mã xác minh.
- Giới hạn gửi lại để tránh quấy rối.
- Theo dõi yêu cầu tìm theo tiền tố hoặc biến thể định danh hàng loạt.
- Xử lý thống nhất các phản hồi mà người chưa xác minh quan sát được.
- Cơ chế thử lại khi thành phần phụ thuộc lỗi mà không hạ điều kiện cấp quyền.

Chỉ thêm một khoảng trễ ngẫu nhiên không tự loại bỏ chênh lệch thời gian có thể đo lặp lại. Có thể tách tiếp nhận khỏi xử lý và gửi, nhưng toàn bộ đường công khai vẫn cần được đánh giá về thông tin tiết lộ.

Một bộ đếm chỉ tăng với username có thật rồi trả thông báo giới hạn khác biệt cũng có thể làm lộ kết quả. Giới hạn lạm dụng cần được thiết kế cùng chính sách phản hồi.

Yêu cầu tra cứu chưa xác minh không nên tự khóa mọi hoạt động, thu hồi phiên hoặc hủy mọi giao dịch của chủ tài khoản. Nếu không, đối thủ có thể dùng biểu mẫu hỗ trợ để gây mất quyền truy cập.

## 12. Hỗ trợ và người dùng không còn kênh phù hợp

Người dùng có thể không nhớ username và không truy cập được email hoặc số điện thoại đã thiết lập. Sản phẩm cần mô tả các đường thực sự hỗ trợ, chẳng hạn:

- Dùng authenticator hoặc phiên còn đáp ứng yêu cầu của chính sách.
- Dùng bằng chứng khôi phục đã được cấp từ trước.
- Đi qua quy trình xem xét nếu có căn cứ và thẩm quyền phù hợp.
- Kết thúc chưa đủ căn cứ khi không có đường khả thi.

Không nên yêu cầu một loạt thông tin công khai rồi coi trả lời đúng là đủ để tiết lộ mọi tài khoản. Ngày sinh, tên hiển thị, một phần email hoặc lịch sử mà người yêu cầu kể lại có thể đã bị biết.

Giấy tờ cũng không tự gắn một người với một username nếu sản phẩm không có căn cứ đối chiếu phù hợp. Thu thập thêm dữ liệu nhạy cảm mà không giải quyết được quan hệ sở hữu không làm đường khôi phục mạnh hơn.

Nhân viên hỗ trợ chỉ nên xem và tiết lộ thông tin cần cho quy trình được giao. Không đọc ra dần các ký tự để người gọi đoán cho đến khi đúng, vì chính cuộc trao đổi có thể trở thành công cụ dò.

## 13. Dữ liệu, thông báo và quan sát vận hành

Một bản ghi vận hành có thể cần mã sự kiện, mục đích, phạm vi, trạng thái xử lý và lý do nội bộ. Không nhất thiết phải ghi nguyên username, email hoặc số điện thoại ở mọi tầng log.

Những dữ liệu cần hạn chế đặc biệt gồm:

- Token, OTP, mã dự phòng và cookie.
- Liên kết xác minh còn sử dụng được.
- Danh sách đầy đủ các tài khoản gắn với một kênh.
- Thông tin định danh không cần thiết trong URL, sự kiện phân tích hoặc dữ liệu gửi cho bên khác.
- Nội dung thông báo chứa nhiều hơn mục đích tìm thông tin đăng nhập cần.

Băm email hoặc username không tự biến chúng thành dữ liệu vô danh; các giá trị dễ đoán có thể bị thử và đối chiếu. Cần lựa chọn cách bảo vệ, quyền truy cập và thời hạn lưu phù hợp, đồng thời giảm dữ liệu được thu thập.

Các chỉ số hữu ích có thể gồm tỷ lệ hoàn tất đường quên username, lỗi gửi, số ca không còn kênh phù hợp, kết quả mơ hồ và dấu hiệu dò hàng loạt. Chúng giúp cải thiện hành trình mà không cần công khai dữ liệu tài khoản.

Kết quả tra cứu cũng không được dùng lại như bằng chứng danh tính trong hỗ trợ hoặc phân tích rủi ro. “Người yêu cầu biết username” chỉ cho thấy họ biết một định danh, không chứng minh quyền kiểm soát tài khoản.

## 14. Những tình huống minh họa

### Tình huống A: Quên username nhưng còn email đã thiết lập

An nhập email vào đường quên username. Phần công khai không trả tên đăng nhập hoặc xác nhận tài khoản tồn tại.

Nếu email đáp ứng điều kiện, hệ thống gửi hướng dẫn theo chính sách. Sau bước được thiết kế, An nhận thông tin đăng nhập trong phạm vi cho phép rồi tiếp tục xác thực bằng mật khẩu, MFA hoặc phương thức còn áp dụng.

**Giới hạn:** việc biết lại username không tự tạo phiên đăng nhập và không tự gỡ MFA.

### Tình huống B: Cùng username trong hai tổ chức

Hai tài khoản cùng có username “binh” nhưng ở hai tổ chức khác nhau. Người dùng bắt đầu từ một phạm vi đăng nhập đã được xác định.

Hệ thống tra trong phạm vi phù hợp, không tìm toàn bộ rồi chọn một tài khoản tùy ý. Quyền của giao dịch được gắn với đúng tài khoản và tổ chức.

**Giới hạn:** không tiết lộ rằng cùng người hoặc cùng email có tài khoản ở tổ chức khác nếu chưa có căn cứ cho việc tiết lộ đó.

### Tình huống C: Username đổi sau khi quyền được phát hành

Chi nhận một quyền tìm thông tin đăng nhập. Sau đó username cũ được đổi theo chính sách, và tên cũ có thể được sử dụng trong một ngữ cảnh khác.

Giao dịch vẫn gắn với định danh tài khoản của Chi. Máy chủ áp dụng quy tắc hiện tại để hiển thị hoặc yêu cầu tiếp tục phù hợp, không chuyển quyền theo tên cũ.

**Giới hạn:** username có thể thay đổi, nhưng quyền đã phát hành không được đổi chủ theo chuỗi tên.

### Tình huống D: Biết username nhưng không còn bằng chứng

Một người nhập đúng username của Dung và yêu cầu gửi tên đăng nhập cùng liên kết đặt lại tới email mới họ cung cấp.

Việc nhập đúng username không đủ để chấp nhận đích nhận mới. Hệ thống chỉ sử dụng đường đã được thiết lập hoặc quy trình khác được phép.

**Giới hạn:** đường tìm định danh không được trở thành đường thay kênh và tiếp quản tài khoản.

## 15. Các lỗi thiết kế cần tránh

| Lỗi | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Trả ngay danh sách username theo email | Lộ mối liên hệ giữa kênh và tài khoản | Tiết lộ qua đường có bằng chứng và phạm vi phù hợp |
| Lấy tài khoản đầu tiên khi tên trùng | Khôi phục sai tài khoản | Giữ đúng phạm vi và xử lý kết quả mơ hồ |
| Dùng tên hiển thị làm định danh duy nhất | Nhầm những người có cùng tên | Dùng định danh được thiết lập và khóa tra cứu phù hợp |
| Tự sửa gần đúng username | Gộp hoặc chọn nhầm danh tính | Áp dụng quy tắc nhất quán, không tự suy đoán |
| Chuẩn hóa khác nhau giữa đăng nhập và khôi phục | Kết quả tra cứu không nhất quán | Dùng cùng quy tắc định danh của sản phẩm |
| Gắn token chỉ với username | Quyền có thể bị chuyển khi tên đổi hoặc được cấp lại | Gắn với tài khoản nội bộ, phạm vi và giao dịch |
| Chấp nhận token tìm username để gỡ MFA | Vượt phạm vi quyền | Kiểm tra mục đích và hành động tại từng API |
| Gửi tới email tùy ý người yêu cầu nhập | Đưa thông tin hoặc quyền cho đối thủ | Máy chủ kiểm tra đường và xác định đích nhận được phép |
| Chỉ giữ câu chữ giống nhau | Các API phụ, thời gian hoặc chuyển trang vẫn làm lộ kết quả | Bảo vệ toàn bộ hành vi công khai |
| Hỗ trợ tiết lộ dần ký tự để người gọi đoán | Biến hỗ trợ thành công cụ dò | Xác minh trước, tiết lộ tối thiểu theo quy trình |

## 16. Danh sách kiểm tra khi thiết kế

Một đặc tả tra cứu username đủ rõ cần trả lời được:

- Đây là tìm tài khoản bằng username hay giúp người dùng tìm lại username?
- Username có duy nhất trong phạm vi nào?
- Quy tắc chuẩn hóa có thống nhất với đăng ký, đăng nhập và cơ sở dữ liệu không?
- Tên cũ, bí danh ngừng dùng và username được cấp lại được xử lý thế nào?
- Giao dịch có giữ tài khoản đích và tổ chức ổn định không?
- Người chưa xác minh có thể suy ra kết quả qua nội dung, API phụ hoặc hành vi không?
- Nếu tìm lại username qua kênh liên hệ, kênh đó đã được thiết lập và đủ điều kiện chưa?
- Quyền tìm định danh có bị dùng nhầm cho đặt lại mật khẩu, gỡ MFA hoặc đăng nhập không?
- Người dùng không còn kênh phù hợp có đường thực tế nào được hỗ trợ?
- Log, thông báo và nhân viên hỗ trợ có giữ đúng giới hạn dữ liệu không?

Tra cứu username an toàn phải tìm đúng tài khoản và tiết lộ đúng phạm vi. Định danh giúp định tuyến yêu cầu; bằng chứng mới quyết định quyền; còn mọi thay đổi credential hoặc phiên đăng nhập vẫn phải đi qua điều kiện riêng.