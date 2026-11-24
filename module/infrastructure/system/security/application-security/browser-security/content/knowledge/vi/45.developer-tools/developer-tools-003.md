# Debug endpoint

Trong trình duyệt Chromium, debug endpoint là giao diện điều khiển mà công cụ phát triển có thể dùng để kết nối với một phiên trình duyệt hoặc một tab đang mở. Giao diện này thường được cung cấp qua Chrome DevTools Protocol (CDP). DevTools, Puppeteer, Playwright và các công cụ tự động hóa có thể dùng CDP để đọc trạng thái trang, kiểm tra DOM, quan sát request, thực thi JavaScript trong ngữ cảnh trang và điều khiển tab.

Debug endpoint giúp việc phát triển và kiểm thử thuận tiện, nhưng nó cũng có quyền lực rất lớn. Một tiến trình kết nối được vào endpoint có thể điều khiển trình duyệt dưới quyền của người đang chạy trình duyệt. Nếu phiên đó đang đăng nhập tài khoản thật, mở ứng dụng nội bộ hoặc chứa dữ liệu nhạy cảm, endpoint bị lộ có thể dẫn đến chiếm phiên, đọc dữ liệu và thao tác thay mặt người dùng.

Trong bài này, `Debug endpoint` chủ yếu nói đến endpoint điều khiển trình duyệt qua CDP. Endpoint chẩn đoán do chính ứng dụng web cung cấp, chẳng hạn `/debug`, `/metrics` hoặc `/actuator`, là một nhóm bề mặt tấn công khác; cần bảo vệ chúng riêng theo cùng nguyên tắc không để lộ giao diện quản trị và dữ liệu vận hành.

## Debug endpoint hoạt động như thế nào?

Khi Chromium được khởi chạy với remote debugging, trình duyệt mở một cổng TCP hoặc một kênh pipe để công cụ bên ngoài gửi lệnh. Với chế độ TCP, một HTTP endpoint cung cấp thông tin khám phá target và địa chỉ WebSocket để mở phiên CDP.

~~~mermaid
flowchart LR
    Tool[DevTools hoặc automation tool] -->|HTTP discovery| HTTP[Debug HTTP endpoint]
    HTTP -->|Target ID và WebSocket URL| WS[CDP WebSocket]
    WS <-->|Lệnh và sự kiện CDP| Browser[Chromium browser process]
    Browser --> Tab[Tab / page target]
    Browser --> Worker[Worker target]
    Browser --> Profile[Browser profile và session]
~~~

Luồng cơ bản gồm hai bước:

1. Công cụ gọi endpoint HTTP để tìm phiên trình duyệt và các target đang hoạt động.
2. Công cụ mở WebSocket được trả về rồi gửi lệnh CDP; trình duyệt phản hồi bằng kết quả và các sự kiện tương ứng.

Một số endpoint thường gặp trong cấu hình Chromium có bật remote debugging:

| Endpoint | Mục đích | Điều cần lưu ý |
|---|---|---|
| `GET /json/version` | Trả thông tin phiên bản browser, phiên bản protocol và WebSocket URL cấp browser | Có thể tiết lộ địa chỉ điều khiển browser |
| `GET /json/list` | Liệt kê các target như tab hoặc page, thường kèm ID, URL, tiêu đề và WebSocket URL | Có thể làm lộ thông tin trang đang mở và đường kết nối CDP |
| `GET /json/protocol` | Trả mô tả protocol mà phiên bản browser hỗ trợ | Hữu ích cho công cụ phát triển, không phải cơ chế xác thực |
| `/devtools/browser/<id>` | Kênh WebSocket điều khiển ở cấp browser | Có phạm vi điều khiển rộng |
| `/devtools/page/<id>` | Kênh WebSocket gắn với một page target | Có thể thao tác trên trang tương ứng |

Các endpoint phụ trợ để tạo, kích hoạt hoặc đóng target có thể xuất hiện tùy phiên bản và cấu hình. Đừng coi các đường dẫn này là API ứng dụng ổn định; chúng thuộc giao diện debug nội bộ của trình duyệt và có thể thay đổi.

Ví dụ, khi phiên debug chạy trên máy phát triển và chỉ bind vào loopback, có thể xem thông tin browser bằng lệnh:

~~~bash
curl http://127.0.0.1:9222/json/version
~~~

Để xem các target đang mở:

~~~bash
curl http://127.0.0.1:9222/json/list
~~~

Kết quả thường chứa một trường `webSocketDebuggerUrl` có dạng `ws://127.0.0.1:9222/devtools/...`. Địa chỉ này cho công cụ biết cách mở phiên CDP. URL có ID khó đoán không phải là cơ chế xác thực đủ mạnh; người có thể truy cập endpoint khám phá thường cũng có thể lấy URL kết nối.

## Vì sao endpoint có quyền cao?

CDP là giao diện điều khiển ở cấp trình duyệt. Nó không bị giới hạn như JavaScript thông thường chạy trong một trang web. JavaScript của trang vẫn chịu Same-Origin Policy, CORS và các cơ chế cách ly của trình duyệt; còn một client CDP đã được phép kết nối đang thao tác qua kênh debug có thẩm quyền cao hơn.

Tùy target, phiên bản browser và các domain CDP được hỗ trợ, client có thể:

- Liệt kê, mở, đóng và điều hướng tab.
- Đọc DOM, trạng thái trang, console và lỗi JavaScript.
- Thực thi JavaScript trong ngữ cảnh của page để kiểm tra hành vi.
- Quan sát request, response và sự kiện mạng.
- Chụp ảnh màn hình, đọc nội dung hiển thị và kiểm tra trạng thái ứng dụng.
- Truy cập dữ liệu phiên hoặc thông tin lưu trữ mà browser cho phép qua các domain debug tương ứng.

Vì vậy, nếu endpoint bị người không được phép kiểm soát, hậu quả có thể vượt xa việc xem log. Kẻ tấn công có thể thao tác trên một phiên đã đăng nhập, đọc dữ liệu mà người dùng đang xem hoặc thực hiện hành động trong ứng dụng với quyền của phiên đó. HttpOnly bảo vệ cookie khỏi JavaScript của trang, nhưng không nên xem đó là ranh giới bảo vệ trước một client debug có quyền điều khiển browser.

CDP cũng có thể nhìn thấy nhiều target thuộc các origin khác nhau trong cùng phiên browser. Điều đó không có nghĩa một website bất kỳ được phép bỏ qua SOP; nó có nghĩa kênh debug là một quyền quản trị riêng và phải được bảo vệ như quyền truy cập vào chính phiên trình duyệt.

## Những đường dẫn làm lộ debug endpoint

Rủi ro thường xuất hiện do cấu hình phát triển được mang sang môi trường dùng chung hoặc do cổng debug được mở rộng phạm vi mạng.

| Tình huống | Vì sao nguy hiểm |
|---|---|
| Chạy browser với `--remote-debugging-port` trên máy dùng chung | Tiến trình khác có thể kết nối nếu nó truy cập được cổng và không có lớp kiểm soát bổ sung |
| Bind cổng vào `0.0.0.0` hoặc địa chỉ mạng công khai | Máy khác trong mạng có thể tiếp cận endpoint |
| Container publish cổng debug ra host hoặc mạng ngoài | Cổng có thể bị chuyển tiếp khỏi network namespace của container |
| Reverse proxy chuyển tiếp WebSocket mà không xác thực | Người truy cập proxy có thể điều khiển browser qua WebSocket |
| SSH tunnel hoặc port forward tồn tại lâu hơn phiên kiểm thử | Cổng có thể tiếp tục được truy cập sau khi mục đích debug kết thúc |
| Dùng profile cá nhân hoặc profile đăng nhập production | Phiên debug kế thừa cookie, token và dữ liệu người dùng trong profile đó |
| Chạy automation trong CI với secret thật | Người kiểm soát endpoint hoặc log có thể chiếm phiên và dữ liệu pipeline |

Loopback (`127.0.0.1` hoặc `::1`) làm giảm khả năng truy cập từ máy khác, nhưng không tự tạo xác thực cho tiến trình cục bộ. Malware, tiến trình không tin cậy hoặc tài khoản khác có quyền truy cập phù hợp trên cùng máy vẫn có thể là mối đe dọa. Cần xem cả quyền hệ điều hành, cấu hình firewall, port forwarding và các proxy đang chạy.

Không nên dựa vào việc endpoint có ID ngẫu nhiên, WebSocket URL khó đoán hoặc chính sách Origin của một phiên bản browser để thay thế kiểm soát mạng và quyền truy cập. Những cơ chế này không phải ranh giới xác thực đầy đủ cho một dịch vụ có khả năng điều khiển browser.

## Cấu hình debug an toàn

Nguyên tắc đầu tiên là chỉ bật remote debugging khi thật sự cần. Khi công cụ hỗ trợ, ưu tiên kênh pipe thay vì mở TCP port vì pipe không tạo một cổng mạng để các máy hoặc tiến trình khác dò tìm. Dù dùng pipe, vẫn phải bảo vệ tiến trình cha, các handle và tài khoản hệ điều hành có quyền giao tiếp với browser.

Nếu cần CDP qua TCP, hãy giới hạn phạm vi như sau:

1. **Bind loopback:** chỉ lắng nghe trên `127.0.0.1` hoặc `::1`; không bind vào mọi interface nếu không có kiến trúc truy cập từ xa đã được bảo vệ.
2. **Dùng profile riêng:** khởi chạy một user data directory riêng cho phiên debug. Không gắn CDP vào profile cá nhân hoặc profile đang chứa session production.
3. **Dùng dữ liệu thử nghiệm:** đăng nhập bằng tài khoản kiểm thử có quyền tối thiểu, dữ liệu giả và secret có thể thu hồi.
4. **Giới hạn thời gian:** chỉ bật cổng trong thời gian cần kiểm thử; đóng browser và xác nhận cổng đã ngừng lắng nghe khi hoàn tất.
5. **Giới hạn người truy cập:** kiểm soát quyền trên máy, firewall, container network và quy trình automation. Không chia sẻ WebSocket URL trong log, ticket hoặc kênh chat công khai.
6. **Tách môi trường:** không chạy browser debug có dữ liệu nhạy cảm trên máy build hoặc máy chủ dùng chung nếu không có cách ly và kiểm soát phù hợp.

Ví dụ khởi chạy Chromium trên máy thử nghiệm với cổng loopback và profile tạm:

~~~bash
chromium \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/chromium-debug-profile
~~~

Đường dẫn executable và tùy chọn có thể khác theo hệ điều hành, bản phân phối và phiên bản Chromium. Mục tiêu của ví dụ là dùng profile riêng và chỉ mở endpoint trên loopback. Sau khi kiểm thử, đóng tiến trình browser và xóa profile thử nghiệm nếu không còn cần giữ.

Nếu cần điều khiển browser trên máy từ xa, không mở trực tiếp CDP ra Internet. Có thể dùng SSH tunnel hoặc VPN có xác thực để đưa cổng loopback của máy từ xa đến một cổng loopback trên máy của người vận hành. Ví dụ với SSH local forwarding:

~~~bash
ssh -L 9222:127.0.0.1:9222 developer@debug-host
~~~

Khi tunnel hoạt động, công cụ trên máy local có thể kết nối `127.0.0.1:9222`. Quyền truy cập SSH, tài khoản máy từ xa, thời gian sống tunnel và quyền trên browser vẫn cần được quản lý. Không tạo một reverse proxy công khai chỉ để thuận tiện cho DevTools.

## Kiểm tra endpoint trên máy phát triển

Review cần xác nhận endpoint chỉ tồn tại khi được chủ động bật và không lắng nghe ngoài phạm vi dự kiến. Hãy thực hiện trên máy và phiên browser do bạn quản lý.

**Bước 1: kiểm tra endpoint khám phá.** Nếu phiên debug được bật có chủ đích, gọi `/json/version` và `/json/list` trên loopback. Xác nhận browser, target và WebSocket URL thuộc đúng phiên kiểm thử. Nếu không bật debug, request cần thất bại hoặc không có dịch vụ tương ứng.

**Bước 2: kiểm tra địa chỉ lắng nghe.** Trên Windows PowerShell:

~~~powershell
Get-NetTCPConnection -LocalPort 9222 -State Listen
~~~

Trên Linux:

~~~bash
ss -ltnp | grep 9222
~~~

Địa chỉ `127.0.0.1:9222` cho thấy listener IPv4 chỉ gắn với loopback. `0.0.0.0:9222` cho thấy listener nhận kết nối trên mọi interface IPv4; `[::]:9222` có thể nhận trên các interface IPv6 và cách ánh xạ IPv4 phụ thuộc hệ điều hành. Cần đối chiếu kết quả với cấu hình firewall và port mapping thực tế.

**Bước 3: kiểm tra khả năng truy cập từ bên ngoài.** Từ một máy kiểm thử được phép trong cùng mạng, xác minh không thể truy cập endpoint khi thiết kế yêu cầu loopback-only. Không quét mạng của bên thứ ba. Nếu endpoint được truy cập qua tunnel, xác minh chỉ tài khoản và máy được cấp quyền mới tạo được tunnel.

**Bước 4: kiểm tra vòng đời.** Đóng browser hoặc dừng phiên automation rồi kiểm tra lại cổng. Không để process browser mồ côi, tunnel hoặc proxy tiếp tục giữ endpoint mở.

**Bước 5: kiểm tra dữ liệu lộ ra.** Xem response discovery, log, terminal output và artifact CI để chắc chắn không lưu URL trang nhạy cảm, WebSocket URL, token hoặc dữ liệu tài khoản. Nếu cần lưu bằng chứng, che giá trị nhạy cảm trước khi chia sẻ.

Không kết nối vào một debug endpoint không thuộc quyền quản lý của bạn để thử lệnh CDP. Chỉ kiểm tra quyền điều khiển trên phiên browser thử nghiệm được tạo riêng cho bài kiểm thử.

## Tích hợp với DevTools và công cụ automation

DevTools frontend có thể kết nối với browser qua CDP để hiển thị Elements, Console, Network và các panel khác. Puppeteer hoặc Playwright có thể khởi chạy browser mới hoặc kết nối vào browser đã chạy. Hai cách này có mô hình quyền khác nhau:

- **Launch browser:** automation tool tạo tiến trình browser và kiểm soát tham số khởi chạy, profile, thời gian sống. Đây thường là lựa chọn dễ kiểm soát hơn cho job tự động.
- **Connect to existing browser:** tool gắn vào phiên đang chạy. Cần xác minh rõ browser nào, profile nào, ai sở hữu phiên và dữ liệu nào đang có trong profile.

Không đưa endpoint CDP dùng chung cho nhiều tenant hoặc nhiều job không tin cậy. Một job có quyền điều khiển browser có thể đọc hoặc thay đổi trạng thái của job khác nếu chúng dùng chung browser process hoặc profile. Mỗi job nên có browser process, profile, tài khoản hệ điều hành và network namespace riêng phù hợp với mức độ nhạy cảm.

Trong CI/CD, hãy dùng tài khoản kiểm thử có quyền tối thiểu, secret ngắn hạn, profile tạm và mạng chỉ cho phép các dịch vụ cần thiết. Xóa artifact chứa dữ liệu trang hoặc session sau khi job kết thúc theo chính sách lưu trữ. Không bật remote debugging trên browser đang dùng để truy cập dashboard production hoặc tài khoản quản trị thật.

## Debug endpoint của ứng dụng web cũng cần được bảo vệ

Một ứng dụng có thể cung cấp endpoint chẩn đoán riêng như `/debug`, `/health`, `/metrics`, `/actuator`, `/env`, `/config` hoặc trang thông tin runtime. Những endpoint này không phải CDP, nhưng có thể tiết lộ biến môi trường, cấu hình, đường dẫn nội bộ, phiên bản thư viện, thông tin database hoặc trạng thái hệ thống.

Khi review endpoint ứng dụng:

- Chỉ công khai health check tối thiểu cần cho load balancer; tách thông tin chẩn đoán chi tiết khỏi endpoint public.
- Đặt metrics và debug API sau xác thực, phân quyền và network policy phù hợp.
- Không trả password, token, cookie signing key, connection string hoặc biến môi trường nhạy cảm.
- Tắt debug mode và stack trace chi tiết trong production; trả lỗi chung cho client và lưu chi tiết ở log nội bộ được kiểm soát.
- Kiểm tra cả route cũ, endpoint của framework, plugin, thư viện monitoring và cấu hình reverse proxy.
- Kiểm thử từ góc nhìn người dùng chưa đăng nhập và từ mạng bên ngoài để xác minh endpoint nội bộ không bị public ngoài ý muốn.

Không dùng tên đường dẫn để kết luận endpoint an toàn. Một route `/health` có thể chỉ trả trạng thái sống, nhưng cũng có thể để lộ dependency và thông tin nội bộ. Cần đọc nội dung phản hồi và kiểm tra quyền thực tế.

## Xử lý khi phát hiện endpoint bị lộ

Nếu CDP endpoint có thể truy cập từ mạng không được phép hoặc đã xuất hiện trong log công khai, hãy coi phiên browser liên quan có khả năng bị điều khiển. Trình tự xử lý nên là:

1. Ngắt truy cập mạng hoặc dừng listener debug để chặn kết nối mới.
2. Đóng browser process và thu hồi tunnel, proxy hoặc port forwarding không còn cần thiết.
3. Xác định profile và tài khoản đã chạy trong phiên đó; giả định cookie, token và dữ liệu trang có thể đã bị đọc.
4. Thu hồi session, đăng xuất các phiên liên quan và xoay vòng secret có khả năng bị lộ theo quy trình ứng phó sự cố.
5. Kiểm tra log hệ điều hành, firewall, proxy, automation và browser để xác định khoảng thời gian endpoint bị mở, nguồn kết nối và hành động đã xảy ra.
6. Sửa cấu hình khởi chạy, network policy và quy trình CI; sau đó xác minh endpoint không còn truy cập được ngoài phạm vi cho phép.

Không chỉ đổi cổng hoặc đổi ID WebSocket rồi tiếp tục dùng profile cũ. Nếu một người không được phép đã có khả năng điều khiển phiên browser, cần xử lý session và secret như dữ liệu có thể đã bị xâm phạm.

## Ví dụ review: cổng debug trong môi trường kiểm thử

Một nhóm QA chạy Chromium trong container với `--remote-debugging-port=9222` để một dashboard nội bộ có thể kết nối và xem trạng thái test. Container được publish cổng `9222` trên tất cả interface của máy host. Browser dùng profile đã đăng nhập vào hệ thống staging bằng tài khoản có quyền quản trị.

Review phát hiện ba vấn đề:

1. Cổng debug được publish ra mạng rộng hơn nhóm QA cần dùng. Người có thể truy cập cổng có thể lấy danh sách target và WebSocket URL để điều khiển browser.
2. Profile dùng lại giữa nhiều test run, nên dữ liệu phiên và tab của job trước có thể còn tồn tại.
3. Dashboard nội bộ chuyển tiếp WebSocket mà không có xác thực riêng cho từng người dùng.

Biện pháp khắc phục là chạy browser với profile tạm riêng cho từng job, chỉ bind CDP vào loopback trong network namespace phù hợp, dùng tunnel hoặc gateway đã xác thực cho người vận hành, giới hạn tài khoản staging và đóng browser sau mỗi job. Sau khi sửa, QA xác minh endpoint không truy cập được từ máy không được phép, WebSocket URL không xuất hiện trong log dùng chung và session thử nghiệm bị xóa khi job kết thúc.

## Checklist review

- [ ] Xác định rõ endpoint là CDP của browser hay debug API của ứng dụng.
- [ ] Chỉ bật remote debugging khi có nhu cầu được phê duyệt.
- [ ] Ưu tiên pipe khi công cụ hỗ trợ; nếu dùng TCP, listener chỉ bind loopback.
- [ ] Không publish cổng CDP ra Internet hoặc mạng dùng chung.
- [ ] Dùng profile riêng, dữ liệu giả và tài khoản kiểm thử có quyền tối thiểu.
- [ ] Không dùng profile cá nhân hoặc profile production cho phiên debug.
- [ ] Bảo vệ WebSocket URL, log, tunnel, proxy và artifact CI.
- [ ] Mỗi automation job hoặc tenant có browser process và profile được cách ly phù hợp.
- [ ] Đã kiểm tra địa chỉ listener, firewall, container port mapping và khả năng truy cập từ xa.
- [ ] Đã xác minh listener, tunnel và process kết thúc sau phiên debug.
- [ ] Có quy trình thu hồi session và secret nếu endpoint từng bị lộ.
- [ ] Debug API của ứng dụng được xác thực, giới hạn dữ liệu và tắt hoặc bảo vệ trong production.

## Câu hỏi tự kiểm tra

1. Vì sao `webSocketDebuggerUrl` là thông tin nhạy cảm dù nó không chứa mật khẩu?
2. Debug endpoint CDP khác JavaScript chạy trong trang web như thế nào về quyền và ranh giới bảo mật?
3. Bind vào `127.0.0.1` giảm rủi ro nào, và những rủi ro nào vẫn còn trên cùng máy?
4. Vì sao một phiên CDP cần profile riêng và tài khoản kiểm thử thay vì profile đang đăng nhập production?
5. Nếu endpoint đã bị truy cập trái phép, vì sao cần thu hồi session và xoay vòng secret thay vì chỉ đổi port?

Một debug endpoint an toàn phải có chủ sở hữu, phạm vi truy cập, thời gian tồn tại và dữ liệu thử nghiệm được xác định rõ. Khi review, hãy kiểm tra cả cách endpoint được bật, nơi nó lắng nghe, ai có thể mở WebSocket và profile browser nào nằm sau quyền điều khiển đó.
