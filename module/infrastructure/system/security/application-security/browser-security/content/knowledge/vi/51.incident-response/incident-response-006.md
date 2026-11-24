# Sự cố extension độc hại

Sự cố extension độc hại xảy ra khi một tiện ích trình duyệt thực hiện hành vi vượt quá mục đích được người dùng hoặc tổ chức chấp thuận, chẳng hạn thu thập nội dung trang, lấy thông tin đăng nhập, đọc cookie, theo dõi hoạt động duyệt web, chèn mã vào website hoặc gửi dữ liệu đến máy chủ không được phép. Extension có thể độc hại ngay từ đầu, bị chiếm quyền phát hành hoặc nhận một bản cập nhật đã bị cài mã độc.

Extension chạy trong môi trường trình duyệt nhưng có thể được cấp quyền rộng hơn JavaScript của một trang web thông thường. Tùy permission, host access và API được browser hỗ trợ, extension có thể đọc hoặc thay đổi DOM trên nhiều website, quan sát tab, gửi request, truy cập storage hoặc tương tác với các thành phần đặc quyền của browser. Nếu extension độc hại hoạt động trong một profile đã đăng nhập, dữ liệu bị ảnh hưởng có thể gồm nội dung ứng dụng, phiên đăng nhập, token, thông tin tài khoản và dữ liệu doanh nghiệp.

Ứng phó cần xác định extension và phạm vi ảnh hưởng, chặn hoạt động tiếp diễn, bảo toàn bằng chứng, xử lý các phiên và thông tin xác thực có thể đã bị lộ, sau đó khôi phục browser trong trạng thái tin cậy. Việc gỡ extension không tự thu hồi cookie, token hoặc quyền OAuth mà extension có thể đã lấy trước đó.

## Phạm vi và dấu hiệu nhận biết

Một extension có thể xuất hiện dưới nhiều hình thức:

- Extension được cài từ cửa hàng chính thức nhưng có hành vi không đúng với mô tả.
- Extension hợp lệ bị chiếm tài khoản nhà phát triển hoặc quy trình phát hành, sau đó phát hành bản cập nhật độc hại.
- Extension bị thay đổi sau khi cài do máy tính hoặc thư mục extension bị xâm nhập.
- Extension được cài ngoài cửa hàng, ở chế độ developer/unpacked hoặc qua chính sách quản trị doanh nghiệp.
- Extension hợp lệ có dependency, thư viện hoặc dịch vụ máy chủ bị xâm phạm và bắt đầu gửi dữ liệu đến nơi khác.

Không thể kết luận an toàn chỉ dựa trên tên, biểu tượng, số lượt cài đặt hoặc việc extension xuất hiện trong cửa hàng chính thức. Cần đối chiếu ID, phiên bản, nguồn cài, quyền, nội dung gói và hành vi mạng.

Các dấu hiệu đáng chú ý gồm:

| Nhóm tín hiệu | Ví dụ | Cần xác minh |
|---|---|---|
| Cài đặt bất thường | Extension mới xuất hiện, người dùng không nhớ đã cài hoặc extension bị cài lại sau khi gỡ | ID, nguồn cài, thời điểm, browser policy và trạng thái đồng bộ profile |
| Quyền thay đổi | Bản cập nhật yêu cầu thêm quyền đọc mọi website, cookies, history hoặc tabs | So sánh manifest và quyền giữa phiên bản trước/sau |
| Hành vi trang | Nội dung bị thay đổi, form bị chèn, redirect hoặc popup lạ | Content script, script injection, DOM mutation và route bị ảnh hưởng |
| Hành vi mạng | Request đến domain mới, gửi dữ liệu trang hoặc tạo lưu lượng nền bất thường | Endpoint, thời điểm, payload đã được làm sạch và tiến trình khởi tạo |
| Tài khoản | Đăng nhập lạ, session mới, token hoặc OAuth grant không rõ nguồn | Audit log của identity provider và dịch vụ liên quan |
| Vận hành browser | Browser chậm, tab mở bất thường, extension bật lại sau khi disable | Policy force-install, browser sync, native messaging host và phần mềm đi kèm |

Một tín hiệu riêng lẻ có thể có nguyên nhân hợp lệ. Ví dụ, một extension quản lý mật khẩu cần quyền tương tác với form đăng nhập; một công cụ hỗ trợ nội bộ có thể cần host access cho một cổng doanh nghiệp. Điều tra phải đối chiếu quyền với chức năng đã được phê duyệt và bằng chứng runtime.

## Đánh giá mức độ nghiêm trọng

Phân loại ban đầu dựa trên khả năng truy cập, dữ liệu có thể bị lấy, số người dùng và bằng chứng hoạt động độc hại.

| Mức | Tình huống tham khảo | Hướng xử lý |
|---|---|---|
| Thấp | Extension không rõ nguồn nhưng chưa có quyền nhạy cảm hoặc hành vi bất thường được xác nhận | Xác minh nguồn, quyền và chủ sở hữu; hạn chế cài đặt mới trong lúc đánh giá |
| Trung bình | Extension có host access rộng, thay đổi quyền không được giải thích hoặc gửi telemetry đến endpoint chưa được duyệt | Cô lập extension trên thiết bị liên quan, thu thập bằng chứng và rà soát người dùng có cùng extension |
| Cao | Có bằng chứng đọc dữ liệu trang nhạy cảm, lấy cookie/token, chèn script hoặc gửi dữ liệu ra ngoài | Vô hiệu hóa trên diện rộng, thu hồi session/token, điều tra endpoint và tài khoản bị ảnh hưởng |
| Nghiêm trọng | Extension có thể kiểm soát nhiều profile/tổ chức, đánh cắp thông tin quản trị hoặc có dấu hiệu xâm nhập thêm vào endpoint | Kích hoạt quy trình incident cấp tổ chức, cô lập thiết bị và phối hợp đội identity, endpoint, network, legal/privacy theo quy định |

Mức độ có thể thay đổi khi có bằng chứng mới. Một extension chỉ được cài trên một máy vẫn có thể gây tác động lớn nếu người dùng đó có quyền quản trị, truy cập hệ thống tài chính hoặc điều khiển môi trường sản xuất.

## Quy trình ứng phó tổng thể

~~~mermaid
flowchart TD
    A[Phát hiện tín hiệu] --> B[Phân loại và xác định extension]
    B --> C[Bảo toàn bằng chứng tối thiểu cần thiết]
    C --> D[Cô lập extension và thiết bị]
    D --> E[Đánh giá dữ liệu, session và tài khoản bị ảnh hưởng]
    E --> F[Thu hồi quyền và loại bỏ persistence]
    F --> G[Khôi phục browser/profile sạch]
    G --> H[Theo dõi và đóng incident]
    H --> I[Rút kinh nghiệm và cập nhật kiểm soát]
~~~

Thứ tự có thể điều chỉnh theo mức độ nguy hiểm. Nếu extension đang đánh cắp dữ liệu theo thời gian thực, ưu tiên chặn hoạt động và thu hồi session có nguy cơ ngay. Nếu tình huống cho phép, thu thập nhanh thông tin nhận diện và bằng chứng dễ mất trước khi disable hoặc gỡ extension. Không trì hoãn containment chỉ để hoàn tất một bộ hồ sơ pháp chứng đầy đủ.

## Bước 1: Xác định extension và thiết bị bị ảnh hưởng

Ghi lại thông tin sau cho từng browser profile:

- Người dùng, thiết bị, hệ điều hành và tên browser.
- Browser version, profile đang dùng và thời điểm phát hiện.
- Tên extension, extension ID, phiên bản và trạng thái enabled/disabled.
- Nguồn cài đặt: cửa hàng, developer/unpacked, chính sách quản trị hoặc nguồn khác.
- Quyền API, host permissions, optional permissions đã được cấp và danh sách website được phép truy cập.
- Thời điểm cài đặt, cập nhật gần nhất và thay đổi quyền được người dùng nhìn thấy.
- Đường dẫn extension hoặc gói cài nếu cần bảo toàn bằng chứng.
- Các domain, IP, request hoặc hành vi đáng ngờ đã quan sát được.

Trên Chromium-based browser, trang quản lý extension thường hiển thị ID và quyền của tiện ích. Có thể mở trang quản lý tương ứng, ví dụ `chrome://extensions` trên Chrome hoặc `edge://extensions` trên Edge. Với Safari, dùng phần quản lý Extensions trong cài đặt Safari hoặc hệ điều hành. Tên menu và mức chi tiết có thể khác theo phiên bản.

Không chỉ tìm extension theo tên hiển thị. ID ổn định hơn để đối chiếu giữa thiết bị, policy và audit log. Tuy nhiên, ID cũng không chứng minh gói hiện tại là chính hãng: cần kiểm tra phiên bản, nguồn phân phối, chữ ký hoặc hash của gói nếu quy trình tổ chức hỗ trợ.

## Bước 2: Bảo toàn bằng chứng

Trước khi xóa dữ liệu hoặc profile, bảo toàn những thông tin có thể mất khi extension bị disable, cập nhật hoặc gỡ bỏ. Chỉ thu thập dữ liệu cần thiết cho điều tra và lưu ở kho bằng chứng có phân quyền.

Danh mục bằng chứng có thể gồm:

1. Ảnh chụp trang quản lý extension thể hiện tên, ID, phiên bản, trạng thái và quyền.
2. Manifest của extension, đặc biệt `permissions`, `host_permissions`, `optional_host_permissions`, `content_scripts`, `background`, `web_accessible_resources`, `externally_connectable` và `update_url` nếu có.
3. Bản sao gói hoặc thư mục extension theo quy trình pháp chứng của tổ chức; tính hash để xác định tính toàn vẹn.
4. Browser version, profile path, thời gian cài đặt/cập nhật và chính sách quản trị đang áp dụng.
5. Browser/extension logs, console, network trace, DNS/proxy/firewall logs và endpoint telemetry có liên quan.
6. Audit log của tài khoản, SSO, OAuth provider và các dịch vụ mà người dùng truy cập trong thời gian nghi ngờ.
7. Thông tin thời gian, múi giờ, người thu thập, công cụ và mọi thao tác đã thực hiện.

Không mở hoặc chạy lại extension nghi ngờ trên profile đang dùng. Nếu cần phân tích mã, thực hiện trong môi trường cách ly, không có thông tin đăng nhập thật và không có quyền truy cập mạng ngoài phạm vi đã kiểm soát. Không gửi nguyên thư mục profile, cookie database hoặc dữ liệu người dùng lên ticket hay kênh chat rộng quyền truy cập.

Nếu việc tiếp tục thu thập làm kéo dài thời gian extension hoạt động, hãy ghi nhận thông tin tối thiểu có thể thu nhanh rồi tiến hành containment. Ghi rõ bằng chứng nào chưa thu được và lý do.

## Bước 3: Cô lập extension và chặn hoạt động

Containment phải ngăn extension tiếp tục đọc dữ liệu hoặc liên lạc với hạ tầng bên ngoài.

### Với một thiết bị cá nhân hoặc thiết bị thử nghiệm

- Nếu có thể làm an toàn, ghi nhận ID, phiên bản, quyền và trạng thái trước khi disable.
- Disable extension qua trang quản lý browser. Nếu extension đang có hành vi đánh cắp dữ liệu, thực hiện ngay sau khi thu thập bằng chứng tối thiểu.
- Ngắt kết nối mạng hoặc cô lập thiết bị theo quy trình endpoint nếu có dấu hiệu extension tải thêm mã, giao tiếp với máy chủ điều khiển hoặc đi kèm malware.
- Không tiếp tục đăng nhập vào hệ thống nhạy cảm bằng profile bị ảnh hưởng.
- Kiểm tra extension có được cài lại bởi browser sync, tài khoản đồng bộ hoặc chính sách quản trị hay không.

### Với môi trường doanh nghiệp

- Dùng công cụ quản trị browser hoặc endpoint management để chặn extension ID và ngăn cài đặt lại.
- Kiểm tra policy cho phép/cấm extension, danh sách force-install, nguồn cài đặt và các extension được phép theo allowlist.
- Xác định tất cả thiết bị và profile có cùng extension ID/version; ưu tiên những người dùng có quyền truy cập dữ liệu nhạy cảm.
- Chặn endpoint mạng độc hại ở DNS, proxy hoặc firewall khi đã xác minh, đồng thời đánh giá nguy cơ ảnh hưởng đến dịch vụ hợp lệ.
- Nếu có native messaging host hoặc ứng dụng companion liên quan, phối hợp đội endpoint để cô lập và kiểm tra thành phần đó.

Tên policy và cách triển khai khác nhau giữa Chrome, Edge, Firefox, Safari và công cụ quản trị. Không áp dụng một cấu hình cho mọi browser khi chưa xác minh tài liệu của nền tảng. Với extension bị force-install bởi policy, disable thủ công ở một profile có thể không đủ; cần xử lý nguồn policy ở cấp quản trị.

Không chỉ chặn domain điều khiển mà bỏ qua extension. Extension có thể đổi endpoint, dùng dịch vụ hợp pháp làm trung gian hoặc lưu dữ liệu để gửi sau. Cần vô hiệu hóa nguồn thực thi và kiểm tra các dữ liệu đã có thể bị thu thập.

## Bước 4: Đánh giá phạm vi dữ liệu và tài khoản bị ảnh hưởng

Extension độc hại có thể truy cập dữ liệu tùy theo quyền được cấp và thiết kế của browser. Hãy đánh giá theo từng khả năng thay vì giả định mọi extension đều có toàn quyền.

| Khả năng hoặc quyền | Dữ liệu/rủi ro cần đánh giá |
|---|---|
| Host access và content script | Nội dung trang, dữ liệu biểu mẫu, thông tin người dùng, mã trang và thao tác trên website trong phạm vi được cấp |
| `cookies` cùng host access phù hợp | Cookie của website trong phạm vi quyền; xem xét nguy cơ session hijacking |
| `tabs` hoặc quyền quan sát tab | URL, tiêu đề và trạng thái tab theo khả năng API và quyền được cấp |
| `history` | Lịch sử duyệt web và suy luận hoạt động người dùng |
| `storage` | Dữ liệu extension lưu cục bộ hoặc đồng bộ, có thể chứa token hay cấu hình |
| `webRequest` hoặc API mạng liên quan | Quan sát hoặc tác động đến request theo API và phiên bản browser hỗ trợ |
| `downloads` | Tệp tải xuống, tên tệp và hành vi tải tệp theo quyền được cấp |
| Native messaging | Khả năng trao đổi với chương trình native chạy ngoài browser |
| `debugger` hoặc quyền điều khiển đặc biệt | Khả năng quan sát hoặc điều khiển sâu hơn trên target được cấp quyền |

Quyền thực tế còn phụ thuộc browser, manifest version, host permission, user gesture và API cụ thể. Reviewer cần đọc manifest và kiểm tra mã/hành vi để xác định extension đã sử dụng quyền nào.

### Đánh giá session, token và quyền bên thứ ba

Nếu extension có thể đọc cookie, nội dung trang hoặc token, hãy giả định các session liên quan có thể đã bị lộ cho đến khi điều tra loại trừ được:

- Thu hồi session đăng nhập và refresh token trên các dịch vụ có khả năng bị truy cập.
- Xoay vòng mật khẩu hoặc secret nếu có bằng chứng extension đã lấy hoặc người dùng nhập thông tin vào form bị chèn.
- Thu hồi OAuth consent, API key, personal access token và ứng dụng bên thứ ba không rõ nguồn.
- Kiểm tra đăng nhập mới, thiết bị lạ, thay đổi MFA, thay đổi recovery method và thao tác nhạy cảm trong audit log.
- Ưu tiên thực hiện thay đổi thông tin xác thực từ một thiết bị và browser profile đã được xác minh sạch.

Cookie `HttpOnly` không thể được đọc bằng `document.cookie`, nhưng không nên xem nó là bảo vệ đầy đủ trước extension có quyền đặc biệt hoặc trước một thiết bị đã bị xâm nhập. Một extension có thể truy cập cookie qua API được cấp quyền; ngoài ra, session có thể bị sử dụng thông qua thao tác trong browser mà không cần trích xuất cookie theo cách thông thường.

Không chỉ đổi mật khẩu rồi đóng incident. Refresh token, session cookie, OAuth grant và API key có vòng đời riêng; cần thu hồi đúng loại credential và xác minh token cũ không còn dùng được.

## Bước 5: Xác định nguyên nhân và đường xâm nhập

Điều tra cần trả lời extension được cài như thế nào, thay đổi gì trước khi phát hiện và thành phần nào đã thực hiện hành vi độc hại.

Các hướng kiểm tra:

- **Cài đặt ban đầu:** người dùng tự cài, được hướng dẫn cài qua trang giả mạo, được cài bởi policy hay đi kèm phần mềm khác?
- **Chiếm quyền cập nhật:** extension có bản cập nhật mới ngay trước khi xuất hiện hành vi bất thường không? Quyền hoặc mã nguồn có thay đổi so với phiên bản đã duyệt không?
- **Tài khoản nhà phát triển:** có dấu hiệu đăng nhập bất thường, thay đổi email, MFA hoặc quy trình phát hành của nhà phát triển không?
- **Dependency và build:** thư viện bên thứ ba, script build, package registry hoặc pipeline phát hành có bị thay đổi không?
- **Native component:** extension có đăng ký native messaging host, cài companion app hoặc gọi một tiến trình ngoài browser không?
- **Đồng bộ profile:** extension có được đồng bộ sang thiết bị khác hoặc tự cài lại sau khi người dùng xóa không?
- **Hạ tầng mạng:** endpoint, DNS, certificate, redirect và thời điểm gửi dữ liệu có liên quan đến một chiến dịch khác không?

So sánh manifest và mã giữa phiên bản hiện tại với bản đã được phê duyệt nếu có. Chú ý thay đổi bất ngờ trong `permissions`, `host_permissions`, content script match pattern, background service worker, `externally_connectable`, `web_accessible_resources`, `update_url` và các endpoint mạng.

Không suy luận rằng extension vô hại chỉ vì mã đã bị làm rối hoặc không thể đọc ngay. Bảo toàn hash và nguồn gói, sau đó chuyển phân tích sâu cho người có chuyên môn malware/reverse engineering trong môi trường cách ly.

## Bước 6: Loại bỏ extension và persistence

Sau khi đã ghi nhận bằng chứng cần thiết và xác định cách cài đặt, loại bỏ extension cùng các thành phần liên quan.

1. Gỡ hoặc chặn extension qua cơ chế quản trị được hỗ trợ.
2. Xác minh extension không còn trong các profile và browser khác thuộc phạm vi sự cố.
3. Kiểm tra browser policy, force-install list, extension sync và nguồn cài ngoài cửa hàng để ngăn tái xuất hiện.
4. Kiểm tra native messaging host, companion app, helper process và thành phần cài kèm nếu extension sử dụng.
5. Kiểm tra scheduled task, startup item hoặc persistence ở hệ điều hành nếu có bằng chứng extension đã cài thêm phần mềm native; chuyển đội endpoint xử lý theo quy trình malware.
6. Xác minh các domain và endpoint độc hại đã được chặn hoặc gỡ khỏi cấu hình hợp lệ.
7. Giữ bản sao bằng chứng và hash theo quy trình lưu trữ; không giữ bản extension độc hại trong thư mục cài đặt đang hoạt động.

Gỡ extension không nhất thiết xóa Cache Storage, IndexedDB, local storage hoặc dữ liệu extension đã đồng bộ. Kiểm tra từng kho dữ liệu theo phạm vi browser và ứng dụng. Không xóa toàn bộ profile trước khi xác định bằng chứng cần bảo toàn; nếu profile bị nghi xâm nhập sâu, có thể tạo profile mới sau khi đã bảo toàn dữ liệu cần thiết.

## Bước 7: Khôi phục hoạt động an toàn

Khôi phục nên bắt đầu từ một browser/profile sạch và credential đã được xử lý:

- Cập nhật browser lên phiên bản được tổ chức hỗ trợ và áp dụng security updates.
- Tạo profile mới nếu profile cũ có khả năng bị sửa đổi hoặc chứa dữ liệu extension không tin cậy.
- Chỉ cài lại extension từ nguồn đã xác minh và danh sách được phê duyệt; kiểm tra ID, publisher, version và quyền trước khi cài.
- Khôi phục bookmark hoặc dữ liệu cần thiết sau khi quét và kiểm tra; tránh phục hồi toàn bộ extension state từ bản sync có nguy cơ mang extension trở lại.
- Đăng nhập lại sau khi session/token cũ đã bị thu hồi; xác minh MFA và recovery options.
- Kiểm tra các luồng ứng dụng quan trọng: đăng nhập, thanh toán, biểu mẫu, SSO, tải tệp và truy cập dashboard.
- Theo dõi request mạng, extension inventory và audit log trong thời gian tăng cường sau phục hồi.

Nếu browser profile được đồng bộ trên nhiều thiết bị, cần xác minh trạng thái extension và cấu hình đồng bộ ở từng thiết bị. Việc xóa extension trên một máy không đảm bảo extension đã biến mất khỏi các profile khác.

## Ví dụ tình huống: extension tiện ích bị cập nhật độc hại

Một nhóm nhân viên sử dụng extension giúp định dạng nội dung trong hệ thống CRM. Extension ban đầu chỉ cần quyền trên CRM. Sau một bản cập nhật, nó yêu cầu quyền truy cập mọi website và bắt đầu gửi URL cùng nội dung một số trang đến một endpoint mới.

Đội vận hành phát hiện thay đổi qua inventory extension và proxy log. Quy trình xử lý có thể diễn ra như sau:

1. Ghi nhận extension ID, phiên bản cũ/mới, manifest, quyền mới, thời điểm cập nhật và danh sách thiết bị có extension.
2. Bảo toàn gói extension và hash; thu proxy/DNS log và audit log của tài khoản nhà phát triển nếu có quyền truy cập.
3. Chặn extension ID qua browser management policy, disable trên các profile cá nhân và ngăn cài lại.
4. Xác định nhân viên đã mở CRM, email, hệ thống tài chính hoặc dashboard quản trị trong khoảng thời gian extension có quyền rộng.
5. Thu hồi session và token của các dịch vụ có khả năng bị đọc; kiểm tra OAuth grant và hoạt động tài khoản bất thường.
6. Phân tích thay đổi giữa hai phiên bản trong môi trường cách ly, xác định endpoint và dữ liệu đã gửi.
7. Tạo profile sạch, cài lại phiên bản đã xác minh hoặc thay thế bằng tiện ích được phê duyệt.
8. Theo dõi extension inventory, endpoint mạng và audit log để phát hiện tái xuất hiện hoặc hoạt động tiếp diễn.

Trong tình huống này, việc extension được cài từ cửa hàng chính thức không loại trừ nguy cơ supply-chain compromise. Thay đổi quyền và hành vi mạng sau update là bằng chứng cần điều tra độc lập.

## Giao tiếp và phối hợp trong incident

Sự cố extension có thể liên quan nhiều nhóm. Người điều phối cần chỉ định một incident owner, ghi mốc thời gian và thống nhất nguồn dữ liệu sự thật.

Các nhóm có thể cần phối hợp:

- **Browser/endpoint management:** inventory, policy, disable/block và kiểm tra thiết bị.
- **Identity và ứng dụng:** thu hồi session/token, xem audit log, kiểm tra OAuth grants và hoạt động tài khoản.
- **Network/SOC:** phân tích DNS, proxy, firewall, endpoint và correlation với các chiến dịch khác.
- **Security engineering:** phân tích manifest, permission, mã extension và nguyên nhân gốc.
- **Privacy/legal/compliance:** đánh giá dữ liệu cá nhân hoặc dữ liệu khách hàng có thể đã bị truy cập và nghĩa vụ thông báo theo chính sách/quy định áp dụng.
- **Helpdesk/communications:** hướng dẫn người dùng không cài lại extension, nhận diện dấu hiệu và báo cáo thiết bị liên quan.

Thông báo nội bộ nên nêu ID extension, hành động cần thực hiện, phạm vi browser/profile và kênh báo cáo. Tránh gửi payload, cookie, token hoặc dữ liệu khách hàng trong thông báo rộng. Không yêu cầu người dùng tự tải và chạy công cụ không được phê duyệt để “làm sạch” máy.

## Chỉ số và tiêu chí đóng sự cố

Theo dõi các chỉ số để xác nhận containment và recovery:

- Số thiết bị/profile phát hiện extension, số đã disable/gỡ và số còn chờ xử lý.
- Tỷ lệ extension ID bị chặn thành công ở cấp quản trị.
- Số lần extension tái xuất hiện sau khi disable hoặc gỡ.
- Số session/token/OAuth grant đã thu hồi và số dịch vụ đã xác minh.
- Số tài khoản có đăng nhập hoặc hành vi bất thường trong khoảng thời gian ảnh hưởng.
- Endpoint mạng độc hại còn được truy cập hay không.
- Số thiết bị cần tạo profile mới hoặc xử lý endpoint bổ sung.
- Thời gian từ phát hiện đến containment, thu hồi credential và phục hồi.

Chỉ đóng incident khi:

1. Extension và các thành phần liên quan đã bị vô hiệu hóa hoặc loại bỏ trên mọi thiết bị/profile đã xác định.
2. Chính sách cài đặt ngăn extension quay lại; nguồn cài và browser sync đã được kiểm tra.
3. Session, token, OAuth grant và secret có khả năng bị lộ đã được xử lý.
4. Các tài khoản và dịch vụ liên quan đã được rà soát audit log, hoạt động bất thường và tác động dữ liệu.
5. Thiết bị/profile đã được xác minh sạch hoặc chuyển sang quy trình xử lý malware riêng.
6. Bằng chứng, quyết định, phạm vi ảnh hưởng và hành động khắc phục đã được ghi nhận.
7. Có biện pháp phòng ngừa tái diễn và người chịu trách nhiệm theo dõi.

Nếu còn thiết bị chưa xác minh hoặc credential chưa thể thu hồi, giữ incident ở trạng thái đang xử lý hoặc ghi rõ rủi ro tồn đọng và người chấp nhận rủi ro theo quy trình tổ chức.

## Checklist ứng phó sự cố extension độc hại

- [ ] Xác định extension ID, phiên bản, publisher, nguồn cài và browser profile.
- [ ] Ghi lại permissions, host permissions, content scripts và background behavior.
- [ ] Xác định thời điểm cài/update và danh sách thiết bị/profile bị ảnh hưởng.
- [ ] Bảo toàn manifest, gói extension, hash, browser logs và network evidence cần thiết.
- [ ] Disable/block extension và ngăn cài lại qua browser policy hoặc endpoint management.
- [ ] Cô lập thiết bị nếu có dấu hiệu malware hoặc exfiltration đang tiếp diễn.
- [ ] Đánh giá dữ liệu trang, cookie, session, token và OAuth grant có thể bị truy cập.
- [ ] Thu hồi session/token/secret từ thiết bị sạch và kiểm tra audit log tài khoản.
- [ ] Kiểm tra extension sync, force-install policy, native messaging host và companion app.
- [ ] Loại bỏ extension và persistence sau khi bảo toàn bằng chứng.
- [ ] Khôi phục bằng browser/profile sạch và extension đã được xác minh.
- [ ] Theo dõi tái xuất hiện, endpoint mạng, tài khoản và hành vi sau phục hồi.
- [ ] Ghi nhận tác động, quyết định thông báo, nguyên nhân gốc và biện pháp phòng ngừa.

## Câu hỏi tự kiểm tra

1. Vì sao extension từ cửa hàng chính thức vẫn có thể trở thành độc hại?
2. Những trường nào trong manifest giúp xác định phạm vi truy cập của extension?
3. Vì sao cần bảo toàn extension ID, version, manifest và hash trước khi gỡ khi tình huống cho phép?
4. Tại sao disable hoặc uninstall extension không đủ để xử lý nguy cơ session/token đã bị lộ?
5. Khi extension bị force-install bởi policy, cần xử lý ở những lớp nào để ngăn cài lại?
6. Vì sao cần kiểm tra native messaging host và companion app trong một số sự cố?
7. Những điều kiện nào phải được xác minh trước khi đóng incident?

Sự cố extension độc hại cần được xử lý như một sự cố có khả năng ảnh hưởng đến phiên trình duyệt và danh tính người dùng. Xác định đúng extension, chặn hoạt động, bảo toàn bằng chứng, thu hồi thông tin xác thực có nguy cơ và khôi phục từ profile sạch là các bước cốt lõi. Sau incident, cập nhật allowlist, chính sách quyền, quy trình review extension và giám sát thay đổi phiên bản để giảm khả năng tái diễn.
