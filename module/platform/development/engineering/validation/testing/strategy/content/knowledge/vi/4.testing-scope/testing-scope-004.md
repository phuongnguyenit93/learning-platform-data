# Xác định phiên bản, nền tảng, trình duyệt và cấu hình cần hỗ trợ

Một sản phẩm có thể chạy tốt trên máy của nhóm phát triển nhưng gặp lỗi khi người dùng mở bằng trình duyệt cũ, thiết bị có bộ nhớ thấp, hệ điều hành chưa được cập nhật hoặc cấu hình mạng khác biệt. Vì vậy, phạm vi kiểm thử cần xác định rõ những môi trường nào sản phẩm cam kết hỗ trợ và những tổ hợp nào phải được kiểm chứng trước khi phát hành.

Danh sách môi trường hỗ trợ là một quyết định sản phẩm và vận hành. Nó ảnh hưởng đến người dùng có thể tiếp tục sử dụng sản phẩm sau khi thiết bị được cập nhật hay không, nhóm phải duy trì bao nhiêu môi trường kiểm thử, cách xử lý lỗi tương thích và thời điểm ngừng hỗ trợ một phiên bản. Quyết định này cần dựa trên khách hàng mục tiêu, dữ liệu sử dụng, rủi ro, vòng đời của nền tảng và năng lực duy trì.

## 1. Phân biệt môi trường được hỗ trợ và môi trường được kiểm thử

Hai khái niệm này có liên quan nhưng phục vụ mục đích khác nhau:

- **Môi trường được hỗ trợ:** môi trường mà sản phẩm cam kết hoạt động theo mức chất lượng đã công bố hoặc thỏa thuận.
- **Môi trường được kiểm thử:** môi trường đã được chọn để chạy các hoạt động xác minh, có thể bao gồm toàn bộ hoặc một tập đại diện của môi trường hỗ trợ.
- **Môi trường tương thích có điều kiện:** môi trường có thể sử dụng nhưng có giới hạn đã công bố, chẳng hạn một số tính năng không khả dụng.
- **Môi trường không còn hỗ trợ:** môi trường nằm ngoài chính sách hiện hành; nhóm không cam kết sửa lỗi riêng cho môi trường đó.

Không nên suy ra rằng một môi trường được hỗ trợ chỉ vì sản phẩm tình cờ chạy được trên đó. Cũng không thể tuyên bố đã hỗ trợ mọi môi trường chỉ vì một vài tổ hợp đã vượt qua kiểm thử.

Ví dụ, một ứng dụng web có thể công bố hỗ trợ các phiên bản trình duyệt ổn định còn được nhà cung cấp duy trì, nhưng chỉ chạy bộ kiểm thử hồi quy đầy đủ trên một số phiên bản đại diện. Chính sách phải nói rõ tiêu chí phiên bản được hỗ trợ, các phiên bản thực sự được kiểm thử, cách xử lý lỗi trên phiên bản chưa có trong ma trận và giới hạn đã biết.

Khi xây dựng phạm vi, hãy tách ba quyết định:

1. Người dùng được phép sử dụng sản phẩm trên những môi trường nào?
2. Nhóm cần kiểm thử đầy đủ, kiểm thử khói hoặc kiểm tra tương thích trên môi trường nào?
3. Môi trường nào sẽ bị loại khỏi hỗ trợ, và người dùng được thông báo hoặc chuyển đổi ra sao?

## 2. Thu thập bằng chứng để chọn môi trường mục tiêu

Đừng chọn nền tảng chỉ vì nhóm đang có sẵn thiết bị hoặc công cụ kiểm thử. Trước tiên, hãy hiểu người dùng thực sự sử dụng sản phẩm trong điều kiện nào.

Các nguồn thông tin hữu ích gồm:

- **Phân khúc khách hàng:** doanh nghiệp hay cá nhân, quy mô tổ chức, ngành nghề, khu vực và các yêu cầu mua sắm.
- **Dữ liệu sử dụng:** phiên bản hệ điều hành, trình duyệt, loại thiết bị, kích thước màn hình, ngôn ngữ và tỷ lệ người dùng theo môi trường.
- **Yêu cầu khách hàng và hợp đồng:** danh sách nền tảng được phê duyệt, thiết bị do tổ chức quản lý, thời hạn hỗ trợ và yêu cầu tích hợp.
- **Vòng đời nhà cung cấp:** ngày phát hành, thời gian hỗ trợ, bản cập nhật bảo mật và lịch ngừng hỗ trợ của hệ điều hành, trình duyệt hoặc runtime.
- **Kiến trúc sản phẩm:** công nghệ giao diện, thư viện, API, trình điều khiển, phần cứng hoặc dịch vụ phụ thuộc.
- **Lịch sử lỗi:** sự cố theo trình duyệt, phiên bản, thiết bị, độ phân giải, cấu hình hoặc khu vực.
- **Kế hoạch sản phẩm:** tính năng sắp ra mắt, thay đổi giao diện, nâng cấp framework và yêu cầu tích hợp mới.

Nếu dùng dữ liệu telemetry, hãy kiểm tra dữ liệu có đại diện cho khách hàng mục tiêu không. Người dùng ít hoạt động, khách hàng mới hoặc môi trường chỉ xuất hiện trong quy trình nghiệp vụ quan trọng có thể bị đánh giá thấp trong thống kê. Dữ liệu quan sát cũng cần tuân theo mục đích thu thập, quyền riêng tư và chính sách lưu giữ.

Ghi rõ thời điểm trích xuất dữ liệu và khoảng thời gian quan sát. Thống kê sáu tháng trước có thể không còn phản ánh môi trường người dùng sau một đợt nâng cấp trình duyệt hoặc triển khai thiết bị doanh nghiệp mới.

## 3. Liệt kê các chiều môi trường cần xem xét

Một môi trường không chỉ là tên hệ điều hành hoặc trình duyệt. Nó là tổ hợp nhiều yếu tố có thể tương tác với nhau.

| Chiều môi trường | Ví dụ giá trị | Lý do cần xem xét |
|---|---|---|
| Hệ điều hành và phiên bản | Windows, macOS, Linux, Android, iOS và các phiên bản cụ thể | API hệ thống, quyền, font, thông báo, lưu trữ và chính sách bảo mật có thể khác nhau |
| Nền tảng và kiểu ứng dụng | Web, web di động, ứng dụng native, desktop, thiết bị nhúng | Cách cài đặt, cập nhật, vòng đời và khả năng tích hợp khác nhau |
| Trình duyệt và engine | Chrome, Edge, Firefox, Safari; Chromium, Gecko, WebKit | Cách diễn giải chuẩn web, API, cookie, media và rendering có thể khác |
| Phiên bản runtime hoặc framework | Java, .NET, Node.js, JVM, runtime di động, framework giao diện | Khác biệt API, hành vi thư viện và hỗ trợ bảo mật |
| Thiết bị và phần cứng | Điện thoại, máy tính bảng, laptop, máy quét, máy in, GPU | Tài nguyên, cảm biến, trình điều khiển và đặc điểm hiển thị khác nhau |
| Màn hình và phương thức nhập | Độ phân giải, mật độ điểm ảnh, cảm ứng, chuột, bàn phím | Bố cục, thao tác, cuộn và khả năng tiếp cận có thể thay đổi |
| Mạng và kết nối | Băng thông thấp, độ trễ cao, mất kết nối, proxy, VPN | Ảnh hưởng tải trang, timeout, đồng bộ và phục hồi |
| Ngôn ngữ và định dạng vùng | Ngôn ngữ giao diện, múi giờ, lịch, định dạng số và tiền tệ | Có thể làm thay đổi nội dung, sắp xếp, ngày giờ và quy tắc nhập liệu |
| Cấu hình bảo mật | Cookie, quyền camera, chứng chỉ, chính sách CSP, SSO, proxy | Có thể ngăn đăng nhập, tích hợp hoặc tải tài nguyên |
| Cấu hình sản phẩm | Feature flag, gói dịch vụ, tenant, module bật/tắt | Cùng phiên bản ứng dụng có thể có hành vi khác nhau |

Không phải dự án nào cũng cần đưa mọi chiều vào ma trận. Hãy chọn chiều có ảnh hưởng đến yêu cầu, kiến trúc hoặc rủi ro của sản phẩm. Nếu ứng dụng không sử dụng camera, việc lập ma trận mọi phiên bản quyền camera có thể không tạo thêm giá trị. Ngược lại, nếu camera là chức năng chính, quyền truy cập, trình duyệt, thiết bị và API media phải nằm trong phạm vi.

## 4. Xây dựng chính sách phiên bản được hỗ trợ

Chính sách phiên bản xác định phiên bản tối thiểu, tối đa hoặc nhóm phiên bản được hỗ trợ, cách cập nhật danh sách và thời điểm kết thúc hỗ trợ.

### 4.1. Chọn mô hình theo vòng đời nền tảng

Một số mô hình thường gặp:

| Mô hình | Cách áp dụng | Phù hợp khi |
|---|---|---|
| Phiên bản tối thiểu | Công bố phiên bản thấp nhất đáp ứng yêu cầu; phiên bản mới hơn được hỗ trợ theo điều kiện | Ứng dụng native hoặc sản phẩm phụ thuộc API hệ điều hành |
| Nhánh hỗ trợ dài hạn (LTS) | Hỗ trợ một số nhánh LTS đã chọn trong thời gian xác định | Runtime, nền tảng doanh nghiệp hoặc hệ thống cần chu kỳ nâng cấp ổn định |
| Bản ổn định hiện hành | Hỗ trợ bản stable hiện hành và chuyển tiếp theo chu kỳ phát hành | Trình duyệt tự cập nhật hoặc dịch vụ có thể theo kịp chu kỳ ngắn |
| Tập phiên bản được phê duyệt | Liệt kê chính xác phiên bản hoặc cấu hình đã được khách hàng chấp thuận | Môi trường doanh nghiệp bị khóa phiên bản hoặc hệ thống chuyên dụng |
| Chính sách theo thiết bị hoặc nhà cung cấp | Hỗ trợ các mẫu thiết bị, firmware hoặc driver nằm trong danh sách | Phần mềm phụ thuộc phần cứng, máy quét, máy POS hoặc thiết bị công nghiệp |

Không có mô hình chung phù hợp cho mọi sản phẩm. Chọn mô hình dựa trên quyền kiểm soát cập nhật, vòng đời của nhà cung cấp, khả năng tương thích ngược và mức độ quan trọng của khách hàng đang sử dụng nền tảng đó.

### 4.2. Xác định phiên bản tối thiểu

Phiên bản tối thiểu cần đủ mới để cung cấp API, giao thức, cơ chế bảo mật và hiệu năng cần thiết. Tuy nhiên, nâng mức tối thiểu có thể loại bỏ người dùng vẫn đang sử dụng thiết bị cũ.

Trước khi nâng phiên bản tối thiểu, hãy:

1. Xác định tính năng hoặc yêu cầu kỹ thuật buộc phải nâng cấp.
2. Kiểm tra tỷ lệ và nhóm khách hàng bị ảnh hưởng bằng dữ liệu hiện có.
3. Đánh giá hợp đồng, cam kết hỗ trợ và khả năng nâng cấp của khách hàng.
4. Ước lượng thời gian chuyển đổi và phương án thay thế.
5. Xác định ngày công bố, ngày bắt đầu cảnh báo và ngày ngừng hỗ trợ.
6. Cập nhật ma trận kiểm thử, tài liệu hỗ trợ và thông báo sản phẩm.

Nếu có thể, duy trì một giai đoạn chuyển tiếp trong đó người dùng nhận được cảnh báo rõ ràng và hướng dẫn nâng cấp trước khi tính năng bị giới hạn.

### 4.3. Quản lý phiên bản mới và phiên bản hết hỗ trợ

Phiên bản mới có thể được nhà cung cấp phát hành thường xuyên. Nhóm cần quy định khi nào phiên bản mới được đưa vào phạm vi, ai đánh giá, kiểm tra nào phải chạy và cách xử lý khi có lỗi tương thích.

Với phiên bản sắp hết hỗ trợ, đánh giá rủi ro bảo mật, số người dùng còn lại, yêu cầu hợp đồng và chi phí duy trì. Ngày kết thúc hỗ trợ phải được truyền đạt trước, có người phê duyệt và có kế hoạch chuyển đổi. Không nên âm thầm loại một môi trường khỏi ma trận vì điều đó làm mất khả năng giải thích cam kết với khách hàng.

## 5. Chọn hệ điều hành, nền tảng và thiết bị

Với ứng dụng web, hệ điều hành có thể ảnh hưởng đến font, bộ gõ, quyền hệ thống, thông báo, quản lý cửa sổ, thiết bị ngoại vi và cách trình duyệt tích hợp với hệ thống. Với ứng dụng native, khác biệt API, quyền riêng tư, chính sách nền và vòng đời tiến trình có thể ảnh hưởng trực tiếp đến chức năng.

Hãy phân nhóm thiết bị theo đặc điểm có ý nghĩa:

- Nhóm thiết bị phổ biến trong khách hàng mục tiêu.
- Thiết bị có cấu hình thấp hoặc giới hạn tài nguyên.
- Thiết bị có kích thước màn hình hoặc tỷ lệ hiển thị đặc biệt.
- Thiết bị có phần cứng hoặc phụ kiện bắt buộc.
- Thiết bị do doanh nghiệp quản lý với chính sách cấu hình riêng.
- Thiết bị đã cũ nhưng vẫn nằm trong cam kết hỗ trợ.

Đối với phần cứng, ghi rõ model hoặc dòng thiết bị, phiên bản firmware, driver, giao diện kết nối và cấu hình phụ thuộc. Chỉ ghi “hỗ trợ máy quét” là chưa đủ nếu các model có hành vi, giao thức hoặc trình điều khiển khác nhau.

Khi không thể kiểm thử mọi model, hãy chọn thiết bị đại diện dựa trên chipset, kích thước, phiên bản hệ điều hành, mức tài nguyên và lịch sử lỗi. Giữ lại ít nhất một số thiết bị thật cho chức năng phụ thuộc phần cứng hoặc cảm biến; trình giả lập không luôn tái tạo chính xác hành vi vật lý.

## 6. Chọn trình duyệt, engine và chế độ sử dụng

Với ứng dụng web, danh sách trình duyệt hỗ trợ cần dựa trên người dùng, yêu cầu khách hàng và khác biệt kỹ thuật. Hai trình duyệt có giao diện gần giống nhau vẫn có thể khác về engine, cookie, sandbox, quyền, codec, font hoặc chính sách bảo mật.

Cần làm rõ:

- Trình duyệt và nhánh phát hành nào được hỗ trợ.
- Phiên bản stable, ESR hoặc kênh quản trị doanh nghiệp nào nằm trong phạm vi.
- Trình duyệt chạy trên hệ điều hành nào.
- Ứng dụng có hỗ trợ chế độ riêng tư, chặn cookie bên thứ ba hoặc chính sách hạn chế tracking hay không.
- Các tính năng cần API đặc thù như camera, microphone, thông báo, tải tệp hoặc clipboard có điều kiện gì.
- Có hỗ trợ trình duyệt nhúng trong ứng dụng khác (webview) hay không.
- Những tiện ích mở rộng, proxy hoặc chính sách doanh nghiệp nào nằm ngoài phạm vi.

Đối với ứng dụng web di động, không nên mặc định rằng cùng một trình duyệt có hành vi giống hệt giữa desktop và mobile. Thanh địa chỉ, bàn phím ảo, vùng an toàn màn hình, chuyển ứng dụng, quyền cảm biến và bộ nhớ có thể tạo ra các tình huống riêng.

Hãy phân biệt lỗi do ứng dụng với lỗi do tiện ích mở rộng hoặc chính sách bên ngoài. Tuy nhiên, nếu khách hàng doanh nghiệp sử dụng một chính sách quản lý trình duyệt cụ thể, chính sách đó có thể trở thành một cấu hình hỗ trợ cần kiểm chứng.

## 7. Chọn cấu hình và tổ hợp cần kiểm thử

Số tổ hợp tăng nhanh khi kết hợp hệ điều hành, phiên bản, trình duyệt, thiết bị, độ phân giải, ngôn ngữ, mạng và feature flag. Kiểm thử toàn bộ tích Descartes thường không khả thi.

Ví dụ, nếu có 4 hệ điều hành, 3 trình duyệt, 3 phiên bản trình duyệt, 4 nhóm thiết bị và 3 cấu hình mạng, số tổ hợp lý thuyết là:

\[
4 \times 3 \times 3 \times 4 \times 3 = 432
\]

Con số này còn chưa tính ngôn ngữ, quyền, cấu hình tenant hoặc phiên bản backend. Vì vậy, cần chọn tổ hợp theo rủi ro và mức độ tương tác giữa các chiều.

### 7.1. Phân tầng mức độ kiểm thử

Có thể chia môi trường thành các mức:

| Mức | Cách kiểm thử | Mục đích |
|---|---|---|
| Mức 1 – trọng yếu | Bộ hồi quy đầy đủ, luồng nghiệp vụ quan trọng, bảo mật và kiểm thử phi chức năng liên quan | Bảo đảm môi trường có mức sử dụng hoặc rủi ro cao |
| Mức 2 – đại diện | Kiểm thử khói, chức năng chính, giao diện và tích hợp quan trọng | Xác nhận tương thích trên các nhóm môi trường đại diện |
| Mức 3 – bổ sung | Kiểm tra khởi động, đăng nhập, hiển thị và một số luồng cơ bản | Phát hiện lỗi tương thích phổ biến với chi phí thấp |
| Ngoài ma trận hỗ trợ | Kiểm tra có mục tiêu khi cần điều tra hoặc đánh giá chuyển đổi | Thu thập thông tin, không tự động tạo cam kết hỗ trợ |

Tên mức và nội dung cần được điều chỉnh theo dự án. Mỗi môi trường phải có lý do được xếp mức và bộ kiểm tra tương ứng.

### 7.2. Chọn tổ hợp đại diện

Một cách thực tế là kết hợp nhiều phương pháp:

- **Bao phủ đầy đủ các môi trường trọng yếu:** các tổ hợp gắn với giao dịch quan trọng, khách hàng lớn hoặc nghĩa vụ hợp đồng.
- **Bao phủ từng chiều:** bảo đảm mỗi hệ điều hành, trình duyệt, thiết bị hoặc cấu hình quan trọng đều xuất hiện ít nhất trong một phép kiểm tra.
- **Pairwise hoặc kiểm thử tổ hợp:** chọn các tổ hợp sao cho mỗi cặp giá trị quan trọng xuất hiện ít nhất một lần, khi rủi ro tương tác chủ yếu nằm ở các cặp.
- **Kiểm thử theo rủi ro:** bổ sung các tổ hợp có lịch sử lỗi, thay đổi mới hoặc hậu quả cao.
- **Kiểm thử thăm dò:** dùng thiết bị thực để tìm vấn đề khó dự đoán từ ma trận lý thuyết.

Pairwise không bảo đảm phát hiện mọi lỗi tương tác ba chiều trở lên. Nếu lỗi phụ thuộc đồng thời vào hệ điều hành, trình duyệt và chính sách cookie, cần thêm tổ hợp có chủ đích để kiểm tra đúng tình huống đó.

### 7.3. Ví dụ ma trận môi trường

Bảng dưới đây là ví dụ giả định về một cổng quản trị web. Các tên môi trường chỉ minh họa cách tổ chức; không phải danh sách hỗ trợ mặc định cho sản phẩm thực tế.

| Môi trường | Mức kiểm thử | Phạm vi chính | Lý do |
|---|---|---|---|
| Windows + trình duyệt Chromium stable hiện hành | Mức 1 | Hồi quy đầy đủ, SSO, xuất dữ liệu và luồng quản trị | Môi trường phổ biến trong nhóm khách hàng doanh nghiệp giả định |
| macOS + Safari stable hiện hành | Mức 1 | Hồi quy chính, cookie, tải tệp và hiển thị | Engine và chính sách trình duyệt có khác biệt đáng kể |
| Windows + Firefox stable hiện hành | Mức 2 | Kiểm thử khói, bảng dữ liệu và biểu mẫu | Bảo đảm tương thích với engine khác |
| Android + Chrome stable hiện hành | Mức 2 | Đăng nhập, thao tác cảm ứng và luồng xem hồ sơ | Nhóm người dùng truy cập từ thiết bị di động |
| iOS + Safari stable hiện hành | Mức 2 | Đăng nhập, bàn phím ảo, vùng an toàn và tải tệp | Hành vi trình duyệt di động có đặc thù |
| Thiết bị màn hình nhỏ, mạng chậm | Mức 3 hoặc kiểm thử bổ sung | Tải trang, phục hồi mạng và thao tác chính | Kiểm tra giới hạn tài nguyên và kết nối |

Ma trận nên có thêm các trường như phiên bản chính xác, hệ điều hành, thiết bị, cấu hình, kết quả gần nhất, người sở hữu và ngày rà soát. Khi phiên bản stable thay đổi, tên “stable hiện hành” phải được ánh xạ thành phiên bản thực tế tại thời điểm chạy để kết quả có thể tái lập.

## 8. Thiết kế kiểm thử cho tương thích và cấu hình

Kiểm thử tương thích không chỉ xác nhận trang có mở được. Hãy chọn các luồng thể hiện rủi ro chính của sản phẩm và kiểm tra hành vi trên môi trường đã chọn.

Các kỹ thuật hữu ích gồm:

- **Kiểm thử chức năng theo luồng:** đăng nhập, tạo hoặc cập nhật dữ liệu, tìm kiếm, xuất tệp, thanh toán hoặc quy trình cốt lõi.
- **Kiểm thử giao diện đáp ứng:** kích thước màn hình, hướng hiển thị, zoom, font, cuộn, bàn phím ảo và thao tác cảm ứng.
- **Kiểm thử API và tính năng nền tảng:** cookie, storage, camera, clipboard, thông báo, tải tệp, WebSocket hoặc service worker khi sản phẩm sử dụng.
- **Kiểm thử cấu hình bảo mật:** CSP, CORS, chứng chỉ, SSO, chính sách cookie, quyền và proxy.
- **Kiểm thử mạng:** độ trễ, băng thông thấp, mất kết nối, khôi phục, retry và timeout.
- **Kiểm thử vùng và ngôn ngữ:** ngày giờ, múi giờ, dấu phân cách, định dạng tiền tệ, bộ gõ và nội dung dài.
- **Kiểm thử tài nguyên:** CPU, bộ nhớ, pin và dung lượng lưu trữ trên thiết bị có giới hạn.
- **Kiểm thử nâng cấp:** cập nhật ứng dụng, trình duyệt hoặc hệ điều hành khi có dữ liệu và cấu hình lưu từ phiên bản trước.

Với mỗi phép thử, ghi rõ môi trường, phiên bản, cấu hình, dữ liệu, bước thực hiện và kết quả mong đợi. Nếu chỉ ghi “pass trên Safari”, kết quả sẽ khó tái hiện khi Safari hoặc hệ điều hành được cập nhật.

Khi một lỗi chỉ xuất hiện trên một tổ hợp, hãy giữ lại thông tin đủ để tái hiện: user agent hoặc thông tin phiên bản phù hợp, kích thước viewport, thiết lập quyền, trạng thái cookie, ngôn ngữ, mã build, feature flag và log liên quan. Không thu thập dữ liệu nhận dạng cá nhân hoặc bí mật không cần thiết trong báo cáo lỗi.

## 9. Tổ chức môi trường và công cụ kiểm thử

Nhóm có thể dùng nhiều cách để tiếp cận các môi trường:

- **Thiết bị thật:** cần thiết cho cảm biến, hiệu năng thực tế, bàn phím, trình điều khiển, camera và hành vi hệ điều hành.
- **Máy ảo:** hữu ích để kiểm tra phiên bản hệ điều hành, cấu hình mạng, trình duyệt và khả năng tái tạo môi trường.
- **Trình giả lập:** hỗ trợ kiểm tra nhiều kích thước và phiên bản thiết bị, nhưng có giới hạn khi mô phỏng phần cứng hoặc hiệu năng.
- **Dịch vụ thiết bị trên đám mây:** mở rộng khả năng truy cập thiết bị và trình duyệt mà nhóm không cần sở hữu tất cả phần cứng.
- **Container:** phù hợp với runtime, dịch vụ phụ trợ và cấu hình backend có thể đóng gói; container không thay thế hoàn toàn kiểm thử hệ điều hành hoặc trình duyệt thật.

Trong CI, có thể chia pipeline thành nhiều tầng. Mỗi thay đổi chạy nhanh trên môi trường trọng yếu; các ma trận rộng hơn chạy theo lịch, trước phát hành hoặc khi thay đổi có ảnh hưởng đến tương thích.

Ví dụ cấu trúc pipeline:

~~~mermaid
flowchart TD
    A["Thay đổi mã nguồn hoặc cấu hình"] --> B["Kiểm tra nhanh trên môi trường chuẩn"]
    B --> C["Kiểm thử khói trên ma trận trọng yếu"]
    C --> D["Kiểm thử tương thích trên môi trường đại diện"]
    D --> E["Kiểm thử mở rộng theo lịch hoặc trước phát hành"]
    E --> F["Tổng hợp lỗi theo môi trường và phiên bản"]
    F --> G{"Có lỗi chặn phát hành?"}
    G -->|Có| H["Điều tra, sửa lỗi hoặc đánh giá ngoại lệ"]
    H --> B
    G -->|Không| I["Lưu bằng chứng và đánh giá phạm vi hỗ trợ"]
~~~

Hãy giữ cấu hình môi trường có thể tái tạo: phiên bản trình duyệt, image máy ảo, cấu hình proxy, locale, dữ liệu và feature flag cần được ghi nhận. Tránh để máy kiểm thử tự cập nhật giữa một lượt chạy mà không lưu lại phiên bản thực tế.

## 10. Quản lý thay đổi và lỗi tương thích

Môi trường thay đổi liên tục. Nhà cung cấp có thể phát hành phiên bản mới, ngừng hỗ trợ bản cũ, thay đổi chính sách cookie hoặc sửa hành vi bảo mật. Sản phẩm cũng có thể nâng cấp framework, thư viện hoặc API nền tảng.

Mỗi thay đổi đáng kể cần được đánh giá theo các câu hỏi:

1. Chiều môi trường nào bị ảnh hưởng?
2. Có phiên bản hoặc cấu hình mới nào cần đưa vào ma trận?
3. Có môi trường cũ nào cần loại bỏ hoặc chuyển sang trạng thái có điều kiện?
4. Luồng nghiệp vụ, bảo mật hoặc dữ liệu nào có nguy cơ bị ảnh hưởng?
5. Cần chạy bộ kiểm thử nào và ai xác nhận kết quả?
6. Có cần cập nhật tài liệu hỗ trợ, hợp đồng hoặc thông báo khách hàng không?

Khi phát hiện lỗi tương thích, phân loại mức độ ảnh hưởng:

- Lỗi chặn người dùng hoàn thành công việc quan trọng.
- Lỗi làm sai dữ liệu, quyền truy cập hoặc giao dịch.
- Lỗi ảnh hưởng một tính năng có phương án thay thế.
- Lỗi hiển thị hoặc trải nghiệm với tác động hạn chế.
- Vấn đề chỉ xuất hiện ở môi trường ngoài chính sách hỗ trợ.

Mức độ nghiêm trọng không chỉ dựa vào số lượng người dùng. Một lỗi chỉ xảy ra trên thiết bị chuyên dụng nhưng thiết bị đó phục vụ quy trình an toàn hoặc giao dịch trọng yếu vẫn có thể cần ưu tiên cao.

Nếu sản phẩm không thể hỗ trợ một môi trường, hãy cung cấp hành vi có thể dự đoán: thông báo rõ yêu cầu phiên bản, hướng dẫn nâng cấp hoặc giải thích tính năng bị giới hạn. Không nên để người dùng tiếp tục một giao dịch có thể tạo dữ liệu sai chỉ vì giao diện vẫn tải được.

## 11. Công bố và duy trì chính sách hỗ trợ

Chính sách hỗ trợ cần được công bố ở nơi khách hàng có thể tìm thấy và cần thống nhất với hợp đồng, tài liệu phát hành, hướng dẫn cài đặt và bộ phận hỗ trợ.

Một chính sách rõ ràng nên nêu:

- Các nền tảng, hệ điều hành, trình duyệt và phiên bản được hỗ trợ.
- Phiên bản tối thiểu và cách hiểu “phiên bản hiện hành”.
- Những cấu hình hoặc tính năng có điều kiện.
- Các môi trường không được hỗ trợ.
- Cách xử lý khi nhà cung cấp ngừng hỗ trợ phiên bản.
- Chu kỳ rà soát và nơi công bố thay đổi.
- Thời gian báo trước và ngày kết thúc hỗ trợ.
- Kênh tiếp nhận lỗi tương thích và thông tin cần cung cấp khi báo lỗi.

Hãy quy định một quy trình chuyển trạng thái cho môi trường:

| Trạng thái | Ý nghĩa | Hành động |
|---|---|---|
| Đang đánh giá | Môi trường mới hoặc thay đổi lớn chưa được xác nhận | Thu thập thông tin và chạy kiểm thử có mục tiêu |
| Được hỗ trợ | Đã được phê duyệt theo chính sách | Đưa vào ma trận kiểm thử theo mức đã định |
| Hỗ trợ có điều kiện | Có giới hạn hoặc tính năng không khả dụng đã công bố | Theo dõi giới hạn và xác minh hành vi thay thế |
| Sắp ngừng hỗ trợ | Đã có quyết định và ngày kết thúc | Thông báo, hướng dẫn chuyển đổi và theo dõi người dùng còn lại |
| Hết hỗ trợ | Nằm ngoài chính sách hiện hành | Không cam kết sửa lỗi riêng; hướng người dùng đến môi trường được hỗ trợ |

Mỗi thay đổi cần có người phê duyệt và lịch sử phiên bản chính sách. Nếu khách hàng có cam kết riêng, phải đánh dấu rõ ngoại lệ theo khách hàng thay vì làm mờ chính sách chung.

## 12. Checklist xác định phạm vi môi trường hỗ trợ

Trước khi chốt ma trận, hãy kiểm tra:

- Đã xác định người dùng mục tiêu, khách hàng và các quy trình quan trọng chưa?
- Dữ liệu sử dụng thực tế có thời điểm, nguồn và giới hạn đại diện rõ ràng chưa?
- Các chiều môi trường liên quan đã được liệt kê, gồm phiên bản, thiết bị, trình duyệt, engine, cấu hình và mạng chưa?
- Đã phân biệt môi trường được hỗ trợ, được kiểm thử và tương thích có điều kiện chưa?
- Chính sách phiên bản tối thiểu, cập nhật và kết thúc hỗ trợ đã rõ chưa?
- Có thiết bị thật cho các chức năng phụ thuộc phần cứng hoặc cảm biến chưa?
- Ma trận có bao phủ đầy đủ các môi trường trọng yếu và các chiều quan trọng không?
- Các tổ hợp còn lại được chọn bằng rủi ro hoặc kỹ thuật kiểm thử tổ hợp có giải thích không?
- Kết quả kiểm thử có lưu phiên bản và cấu hình thực tế để tái lập không?
- CI có tầng kiểm tra nhanh và kiểm tra mở rộng phù hợp không?
- Có quy trình xử lý phiên bản mới, lỗi tương thích và nền tảng hết hỗ trợ không?
- Chính sách công bố, thông báo và ngoại lệ theo khách hàng có chủ sở hữu không?

Sơ đồ quyết định dưới đây tóm tắt cách đưa một môi trường vào hoặc ra khỏi phạm vi hỗ trợ:

~~~mermaid
flowchart TD
    A["Thu thập dữ liệu người dùng và nghĩa vụ"] --> B["Liệt kê chiều môi trường"]
    B --> C["Đánh giá mức sử dụng, rủi ro và vòng đời"]
    C --> D{"Có thuộc phạm vi hỗ trợ?"}
    D -->|Có| E["Chọn mức kiểm thử và tổ hợp đại diện"]
    E --> F["Chạy kiểm thử và lưu bằng chứng"]
    F --> G{"Đạt tiêu chí?"}
    G -->|Có| H["Phê duyệt và công bố hỗ trợ"]
    G -->|Chưa| I["Sửa lỗi, giới hạn có điều kiện hoặc hoãn hỗ trợ"]
    I --> E
    D -->|Chưa| J["Ghi lý do và phương án thay thế"]
    H --> K["Theo dõi phiên bản và rà soát định kỳ"]
    J --> K
    K --> A
~~~

Xác định đúng môi trường hỗ trợ giúp nhóm tập trung kiểm thử vào những tổ hợp có ý nghĩa, công bố cam kết rõ ràng và chủ động quản lý thay đổi nền tảng. Ma trận tốt không chỉ liệt kê tên thiết bị hay trình duyệt; nó giải thích vì sao môi trường nằm trong phạm vi, mức độ bằng chứng cần có, ai chịu trách nhiệm và cách chính sách sẽ thay đổi theo thời gian.

