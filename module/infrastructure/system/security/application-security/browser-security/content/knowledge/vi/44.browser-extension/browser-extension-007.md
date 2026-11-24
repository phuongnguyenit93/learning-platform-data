# Extension độc hại

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao một tiện ích mở rộng trình duyệt có thể trở thành điểm xâm nhập dù được cài từ cửa hàng chính thức.
- Đọc manifest và đánh giá quyền truy cập theo chức năng thực tế của extension.
- Nhận diện hành vi thu thập dữ liệu, sửa nội dung trang, chiếm quyền tìm kiếm và liên lạc mạng đáng ngờ.
- Kiểm tra một extension trong trình duyệt và thu thập bằng chứng ban đầu.
- Giảm rủi ro cho người dùng, tổ chức và nhóm phát triển extension.
- Thực hiện các bước ứng phó khi phát hiện extension có dấu hiệu độc hại.

## 1. Extension độc hại là gì?

Extension độc hại là tiện ích mở rộng trình duyệt sử dụng quyền được cấp để thực hiện hành vi gây hại hoặc vượt quá mục đích mà người dùng đã đồng ý. Hành vi đó có thể xuất hiện ngay khi cài đặt, chỉ xảy ra trên một số website, bắt đầu sau một lần cập nhật, hoặc được kích hoạt theo điều kiện như thời gian, tài khoản đăng nhập hay địa chỉ mạng.

Không phải extension nào có nhiều quyền cũng là mã độc. Một công cụ quản lý tab có thể cần quyền đọc thông tin tab; trình quản lý mật khẩu có thể cần tương tác với biểu mẫu đăng nhập; tiện ích chặn quảng cáo có thể cần quyền quan sát hoặc lọc yêu cầu mạng. Rủi ro xuất hiện khi quyền và hành vi không phù hợp với chức năng đã công bố, dữ liệu được gửi đến nơi không có lý do hợp lệ, hoặc extension bí mật thay đổi trải nghiệm và quyết định của người dùng.

Một extension có thể trở nên độc hại theo nhiều cách:

- Nhà phát triển chủ ý phát hành một sản phẩm thu thập dữ liệu, chiếm quyền tìm kiếm hoặc chèn quảng cáo.
- Tài khoản nhà phát triển bị chiếm, kẻ tấn công phát hành bản cập nhật có mã độc.
- Một extension hợp pháp được bán hoặc chuyển giao, rồi chủ sở hữu mới thay đổi cách xử lý dữ liệu.
- Thư viện phụ thuộc, công cụ xây dựng hoặc quy trình phát hành bị xâm nhập.
- Extension giả mạo thương hiệu, tên và biểu tượng của sản phẩm phổ biến để đánh lừa người dùng.
- Extension ban đầu hữu ích nhưng dần mở rộng thu thập dữ liệu mà không giải thích rõ.

Vì vậy, đánh giá extension cần xem xét cả danh tính nhà phát hành, quyền, mã nguồn hoặc hành vi quan sát được, lịch sử cập nhật và luồng dữ liệu.

## 2. Vì sao extension có quyền lực đặc biệt?

Một extension chạy trong môi trường do trình duyệt quản lý. Nó có thể gồm nhiều thành phần với quyền và ngữ cảnh khác nhau:

- **Content script** chạy trên các trang được phép khớp với quy tắc trong manifest. Nó thường chạy trong isolated world riêng, nhưng vẫn nhìn thấy và thao tác DOM của trang.
- **Background script hoặc extension service worker** xử lý sự kiện, quản lý trạng thái và gọi các API extension. Trong Chrome Manifest V3, phần nền thường là service worker có thể bị dừng khi nhàn rỗi rồi khởi động lại khi có sự kiện.
- **Popup, trang options và trang extension** là giao diện do extension cung cấp. Chúng có thể sử dụng API extension theo quyền đã khai báo.
- **Tài nguyên web-accessible** là những tệp được extension chủ động công khai để trang web có thể tải theo quy tắc khai báo. Không nên đưa dữ liệu riêng tư hoặc mã nội bộ không cần thiết vào nhóm này.
- **Native messaging host** là chương trình cài trên máy tính mà extension có thể giao tiếp nếu người dùng hoặc quản trị viên thiết lập. Khả năng của chương trình native phụ thuộc chính chương trình đó và có thể vượt ra ngoài phạm vi trình duyệt.

Extension không tự động có toàn quyền trên mọi trang. Khả năng thực tế phụ thuộc vào manifest, quyền người dùng đã cấp, cấu hình site access, API trình duyệt và ngữ cảnh mà mã đang chạy. Tuy nhiên, khi được cấp quyền phù hợp, extension có thể hoạt động ở vị trí rất nhạy cảm: giữa người dùng và các ứng dụng web mà họ tin cậy.

### 2.1. Isolated world không có nghĩa là DOM được cách ly

Content script thường có JavaScript global scope riêng, không trực tiếp dùng chung biến JavaScript với mã của trang. Cơ chế này giúp hạn chế việc trang web đọc hoặc sửa biến nội bộ của extension.

Nhưng DOM vẫn là bề mặt dùng chung. Content script có thể đọc hoặc thay đổi những phần tử mà trang hiển thị, quan sát biểu mẫu, thêm nút, sửa liên kết hoặc theo dõi sự kiện tương tác. Trang web cũng có thể thay đổi DOM để tác động đến dữ liệu mà content script đọc được.

Do đó:

- Isolated world bảo vệ một phần môi trường JavaScript, không che giấu nội dung DOM.
- Không được coi dữ liệu lấy từ DOM là dữ liệu đáng tin cậy.
- Không đưa chuỗi lấy từ trang vào innerHTML hoặc lệnh thực thi.
- Không gửi dữ liệu nhạy cảm từ content script về background nếu chức năng không thật sự cần.
- Không cho phép một thông điệp từ content script tùy ý yêu cầu background gọi API có đặc quyền.

### 2.2. Quyền extension và ranh giới origin

Same-Origin Policy tiếp tục bảo vệ các trang web theo quy tắc của trình duyệt, nhưng extension có thể được cấp những API hoặc host permission cho phép thực hiện một số thao tác vượt qua giới hạn mà JavaScript thông thường của trang không được làm. Đây là quyền có điều kiện, không phải một cơ chế bỏ toàn bộ Same-Origin Policy.

Ví dụ, một content script được phép chạy trên https://portal.example có thể đọc DOM của trang đó. Một extension có quyền cookies cùng host permission thích hợp có thể truy vấn cookie của host được cấp quyền thông qua API extension. Một extension có quyền scripting và quyền truy cập host hoặc activeTab có thể chèn script vào tab trong phạm vi được phép.

Không nên suy luận rằng extension có thể đọc mọi cookie hoặc mọi dữ liệu của mọi website. Hãy kiểm tra quyền cụ thể, host cụ thể, thời điểm cấp quyền và API thực tế được sử dụng.

### 2.3. Extension và các cơ chế bảo vệ ứng dụng web

Extension độc hại là một tác nhân chạy trong trình duyệt với những quyền người dùng đã cấp. Các cơ chế bảo vệ website vẫn rất cần thiết, nhưng mỗi cơ chế có một phạm vi riêng:

| Cơ chế | Bảo vệ chính | Giới hạn khi đối mặt với extension có quyền |
|---|---|---|
| CORS | Kiểm soát việc JavaScript của một origin đọc response từ origin khác | Extension có host permission và ngữ cảnh đặc quyền có thể thực hiện request theo mô hình quyền của trình duyệt; CORS không phải cơ chế xác thực người dùng |
| CSRF token và SameSite cookie | Giảm khả năng website khác tạo request được xác thực ngoài ý muốn | Extension hoạt động trên trang đã được cấp quyền có thể tương tác với DOM và luồng người dùng; không được bỏ kiểm tra CSRF ở phía máy chủ |
| CSP và Trusted Types | Hạn chế nguồn script và việc đưa dữ liệu không tin cậy vào các DOM sink nguy hiểm | Không thu hồi quyền extension và không che nội dung DOM khỏi content script được phép |
| frame-ancestors hoặc X-Frame-Options | Ngăn website bị nhúng vào frame theo chính sách | Không ngăn extension được phép sửa DOM của trang đang mở hoặc thêm giao diện phủ lên trang |
| Security headers | Tăng cường cách trình duyệt xử lý nội dung, referrer và một số khả năng của trang | Không thay thế kiểm soát cài đặt, quyền và vòng đời extension |

**CORS không phải hàng rào tin cậy cho extension.** CORS chủ yếu quyết định JavaScript của trang có được đọc response cross-origin hay không. Extension service worker hoặc background có host permission phù hợp có thể gọi endpoint theo mô hình quyền extension; content script có thể chịu quy tắc mạng của page context tùy trình duyệt và API. Vì vậy, không dùng CORS thay cho xác thực, phân quyền và kiểm tra dữ liệu ở máy chủ.

**CSRF vẫn cần được phòng vệ ở phía máy chủ.** Extension có thể tương tác với website đang mở, đọc token chống CSRF được đặt trong DOM nếu token đó hiển thị cho trang, hoặc kích hoạt thao tác trong phạm vi quyền. Máy chủ vẫn cần xác minh token gắn với phiên, kiểm tra Origin hoặc Referer khi phù hợp, cấu hình cookie SameSite và yêu cầu xác nhận bổ sung cho thao tác rủi ro cao. CORS đơn lẻ không phải biện pháp chống CSRF.

**XSS và extension là hai đường tác động khác nhau lên DOM.** Ứng dụng web cần mã hóa đầu ra, dùng API DOM an toàn, áp dụng CSP và Trusted Types phù hợp để giảm XSS. Những biện pháp này bảo vệ ứng dụng khỏi nhiều kiểu chèn mã từ nội dung web, nhưng không làm DOM biến mất khỏi content script đã được cấp quyền. Vì vậy, nhóm vận hành vẫn phải quản lý extension được cài và nhà phát hành được tin cậy.

**Chống clickjacking không chặn mọi giao diện giả.** CSP frame-ancestors hoặc X-Frame-Options giúp ngăn website bị nhúng vào frame trái phép. Một extension có quyền thao tác DOM vẫn có thể thêm lớp phủ, nút hoặc thông báo giả ngay trên tab đang mở. Người dùng và tổ chức cần kiểm soát extension song song với việc bảo vệ website.

Khi điều tra, hãy xem security headers là một lớp bảo vệ của ứng dụng web, còn quyền extension là một lớp năng lực riêng do trình duyệt cấp. Không có một header đơn lẻ nào thay thế được việc giới hạn extension theo ID, nhà phát hành, quyền và phạm vi website.

## 3. Mô hình đe dọa và vòng đời của extension độc hại

### 3.1. Tài sản có thể bị ảnh hưởng

Một extension có quyền quá rộng hoặc có logic độc hại có thể nhắm đến:

| Tài sản | Ví dụ tác động |
|---|---|
| Dữ liệu trên trang | Đọc nội dung email, tài liệu, hồ sơ khách hàng hoặc dữ liệu biểu mẫu |
| Thông tin đăng nhập | Thu thập dữ liệu người dùng nhập vào biểu mẫu đăng nhập hoặc trang thanh toán |
| Phiên đăng nhập | Lạm dụng quyền cookie hoặc dữ liệu phiên mà extension có thể truy cập |
| Lịch sử duyệt web | Lập hồ sơ sở thích, tìm kiếm và hoạt động của người dùng |
| Tab và điều hướng | Theo dõi URL, thay trang chủ, đổi công cụ tìm kiếm hoặc chuyển hướng |
| Clipboard | Đọc dữ liệu đã sao chép nếu có quyền và API tương ứng |
| Tệp tải xuống | Theo dõi, thay đổi hoặc kích hoạt thao tác tải xuống trong phạm vi API |
| Yêu cầu mạng | Quan sát hoặc thay đổi yêu cầu theo quyền được cấp |
| Thiết bị cục bộ | Giao tiếp với chương trình native đã cài qua native messaging |
| Quy trình làm việc | Chèn giao diện giả, nút giả hoặc nội dung gây hiểu nhầm |

Một extension không cần đánh cắp mật khẩu thô mới gây thiệt hại. Việc thu thập URL nội bộ, nội dung tài liệu, thông tin khách hàng, mã xác thực đang hiển thị hoặc token lưu sai chỗ cũng có thể dẫn đến lộ dữ liệu và chiếm tài khoản.

### 3.2. Các giai đoạn tấn công thường gặp

~~~mermaid
flowchart TD
    A["Nhà phát triển hoặc chuỗi cung ứng bị xâm nhập"] --> B["Extension được phát hành"]
    B --> C["Người dùng cài đặt và cấp quyền"]
    C --> D["Content script và background hoạt động"]
    D --> E["Đọc hoặc sửa DOM"]
    D --> F["Gọi API được cấp"]
    E --> G["Thu thập hoặc biến đổi dữ liệu"]
    F --> G
    G --> H["Gửi dữ liệu hoặc điều khiển trang"]
    H --> I["Duy trì qua cập nhật hoặc cấu hình"]
~~~

Đây là mô hình khái quát. Không phải extension độc hại nào cũng dùng tất cả các bước. Một số chỉ sửa công cụ tìm kiếm; số khác chỉ theo dõi một nhóm website; một số chờ cập nhật hoặc cấu hình từ máy chủ trước khi kích hoạt.

### 3.3. Các kiểu hành vi độc hại

**Thu thập dữ liệu trang.** Extension đọc nội dung DOM, trường biểu mẫu, thông tin tài khoản hoặc tài liệu mà người dùng mở. Dữ liệu có thể được lọc theo từ khóa, domain hoặc loại trang trước khi gửi đi.

**Đánh cắp thông tin đăng nhập và phiên.** Extension theo dõi biểu mẫu đăng nhập, dữ liệu được tự động điền hoặc cookie trong phạm vi quyền được cấp. Thuộc tính HttpOnly ngăn JavaScript thông thường của trang đọc cookie, nhưng không phải lá chắn tuyệt đối trước extension có quyền cookies và host permission tương ứng.

**Chèn nội dung và lừa người dùng.** Extension thay nút thanh toán, chèn biểu mẫu giả, thay địa chỉ nhận tiền, thêm quảng cáo hoặc hiển thị cảnh báo giả. Vì nội dung xuất hiện ngay trong website quen thuộc, người dùng có thể khó phân biệt.

**Chiếm quyền tìm kiếm và điều hướng.** Extension đổi trang tab mới, công cụ tìm kiếm mặc định, trang chủ hoặc chuyển hướng truy cập qua một dịch vụ trung gian. Mục đích có thể là kiếm tiền từ liên kết giới thiệu, thu thập truy vấn hoặc dẫn người dùng đến trang lừa đảo.

**Theo dõi hành vi.** Extension ghi lại URL, thời gian truy cập, truy vấn tìm kiếm, tương tác và thông tin môi trường. Dữ liệu có thể được dùng cho quảng cáo, lập hồ sơ hoặc bán lại.

**Lạm dụng yêu cầu mạng.** Tùy API và quyền, extension có thể quan sát một phần thông tin yêu cầu, chặn hoặc thay đổi yêu cầu bằng các cơ chế được trình duyệt hỗ trợ. Hành vi có thể làm lộ metadata, thay nội dung hoặc chuyển người dùng qua endpoint không mong muốn.

**Tải thêm cấu hình và thay đổi hành vi.** Extension có thể nhận dữ liệu cấu hình từ máy chủ để quyết định domain nào cần theo dõi, thời điểm nào kích hoạt hoặc nội dung nào cần hiển thị. Trong Chrome Manifest V3, chính sách cấm mã thực thi được lưu trữ từ xa; quy tắc này không loại bỏ nguy cơ mã độc đã được đóng gói trong extension hoặc logic cục bộ bị điều khiển bằng dữ liệu từ xa.

**Lạm dụng tài nguyên và thiết bị.** Extension có thể tạo lưu lượng mạng bất thường, làm chậm trình duyệt, tiêu thụ CPU hoặc giao tiếp với chương trình native. Khả năng cụ thể phụ thuộc quyền và thành phần được cài trên máy.

## 4. Đọc quyền để đánh giá mức độ rủi ro

Manifest cho biết extension yêu cầu những quyền và phạm vi website nào. Đây là điểm bắt đầu của việc đánh giá, không phải kết luận cuối cùng. Cần đọc cả permissions, optional_permissions, host_permissions, optional_host_permissions, content_scripts, background, web_accessible_resources và các khai báo liên quan.

### 4.1. Quyền thường cần xem xét kỹ

| Quyền hoặc khai báo | Khả năng liên quan | Câu hỏi đánh giá |
|---|---|---|
| "&lt;all_urls&gt;" trong host permissions hoặc match patterns | Mở rộng phạm vi hoạt động đến nhiều website | Vì sao một tiện ích chỉ phục vụ một website lại cần truy cập mọi website? |
| tabs | Đọc metadata của tab như URL hoặc tiêu đề trong phạm vi API cho phép | Chức năng có cần biết người dùng đang mở trang nào không? |
| scripting | Chèn JavaScript hoặc CSS vào trang theo điều kiện quyền | Extension cần sửa trang nào, vào thời điểm nào và để làm gì? |
| cookies | Truy vấn hoặc thay đổi cookie của host được cấp quyền | Có lý do rõ ràng để thao tác cookie không? |
| history | Truy cập lịch sử duyệt web qua API tương ứng | Chức năng có thật sự cần lịch sử không? |
| webRequest | Quan sát thông tin yêu cầu mạng theo quyền và giới hạn trình duyệt | Extension cần quan sát loại yêu cầu nào? Có thu thập dữ liệu thừa không? |
| declarativeNetRequest | Áp dụng quy tắc khai báo để chặn hoặc thay đổi yêu cầu | Bộ quy tắc có phù hợp chức năng và có thể giải thích được không? |
| downloads | Theo dõi và điều khiển thao tác tải xuống trong phạm vi API | Có cần quản lý tải xuống hay chỉ cần hiển thị thông tin? |
| clipboardRead | Đọc clipboard qua API được cấp quyền | Có thông báo rõ lúc nào dữ liệu clipboard được đọc không? |
| nativeMessaging | Trao đổi dữ liệu với chương trình native đã cài | Chương trình native là gì, do ai cài và có quyền hệ điều hành nào? |
| debugger | Dùng giao thức gỡ lỗi để điều khiển hoặc quan sát tab | Vì sao một tiện ích thông thường cần quyền có phạm vi rộng như vậy? |
| management | Truy vấn hoặc quản lý extension khác qua API được hỗ trợ | Có chức năng quản trị rõ ràng và được người dùng mong đợi không? |
| storage | Lưu dữ liệu thuộc extension | Extension lưu loại dữ liệu gì, có chứa token hoặc thông tin cá nhân không? |

Một số điểm cần hiểu đúng:

- Quyền tabs không tự động đồng nghĩa với quyền đọc toàn bộ DOM của mọi trang. Khả năng đọc nội dung phụ thuộc content script, host permission, scripting hoặc quyền tạm thời khác.
- storage là API lưu trữ của extension; nó không tự động cấp quyền đọc localStorage của website. Tuy nhiên, extension có thể lưu dữ liệu nhạy cảm mà chính nó đã thu thập.
- activeTab thường cấp quyền truy cập tạm thời vào tab sau một thao tác rõ ràng của người dùng. Phạm vi và thời hạn phụ thuộc trình duyệt và API.
- host_permissions giới hạn những host extension có thể truy cập bằng các API cần quyền host. content_scripts.matches xác định những trang mà content script được tự động đưa vào.
- optional_permissions và optional_host_permissions cho phép yêu cầu thêm quyền trong lúc chạy. Vì vậy, kiểm tra manifest lúc cài đặt chưa chắc phản ánh mọi quyền có thể được yêu cầu sau này.
- Tên quyền và cách triển khai có thể khác giữa Chrome, Edge, Firefox và các trình duyệt tương thích WebExtensions. Luôn đối chiếu tài liệu của trình duyệt đang sử dụng.

### 4.2. Đánh giá quyền theo chức năng

Hãy đặt mỗi quyền cạnh một chức năng cụ thể. Ví dụ:

| Chức năng được công bố | Quyền có thể hợp lý | Dấu hiệu cần giải thích |
|---|---|---|
| Chỉ đổi màu giao diện trên một website | Host permission giới hạn ở website đó; quyền cần cho content script | Truy cập mọi website, đọc lịch sử hoặc clipboard |
| Chặn quảng cáo theo bộ lọc | Quyền lọc yêu cầu phù hợp với API trình duyệt | Đọc nội dung biểu mẫu đăng nhập hoặc lịch sử toàn bộ |
| Quản lý tab | tabs hoặc quyền tương ứng của trình duyệt | Quyền đọc cookie và chèn script vào mọi trang |
| Tự động điền biểu mẫu | Host permission giới hạn, quyền lưu trữ cần thiết | Gửi toàn bộ nội dung trang về máy chủ không được công bố |
| Đồng bộ cấu hình | storage và kết nối dịch vụ được giải thích | Gửi URL, nội dung trang hoặc dữ liệu clipboard không liên quan |
| Hỗ trợ ứng dụng nội bộ | Host permission giới hạn theo domain nội bộ | Quyền truy cập toàn bộ Internet mà không có lý do |

Quyền rộng có thể có lý do hợp lệ, nhưng nhà phát triển phải giải thích được lý do đó. Nếu chức năng có thể hoạt động với quyền hẹp hơn, nên ưu tiên quyền hẹp hơn và yêu cầu quyền bổ sung đúng lúc cần dùng.

### 4.3. Manifest ví dụ để phân tích

Manifest dưới đây cố ý khai báo phạm vi rộng. Nó chỉ minh họa bề mặt cần kiểm tra, không phải bằng chứng tự thân rằng extension là mã độc.

~~~json
{
  "manifest_version": 3,
  "name": "Ví dụ cần đánh giá kỹ",
  "version": "1.0.0",
  "permissions": [
    "tabs",
    "scripting",
    "storage"
  ],
  "host_permissions": [
    "<all_urls>"
  ],
  "background": {
    "service_worker": "background.js"
  },
  "content_scripts": [
    {
      "matches": ["<all_urls>"],
      "js": ["content.js"],
      "run_at": "document_idle"
    }
  ]
}
~~~

Khi gặp manifest tương tự, hãy trả lời:

1. Sản phẩm tuyên bố giải quyết vấn đề gì?
2. Tại sao cần chạy content script trên mọi website?
3. Có thể thay "<all_urls>" bằng một danh sách domain hẹp hơn không?
4. tabs và scripting có phục vụ chức năng được mô tả không?
5. Dữ liệu nào được đọc, lưu và gửi ra ngoài?
6. Người dùng có thể bật quyền theo từng website hoặc chỉ khi nhấn nút không?
7. Chính sách quyền riêng tư có nêu rõ mục đích, thời hạn lưu và bên nhận dữ liệu không?

Không kết luận chỉ dựa trên số lượng quyền. Hãy đối chiếu quyền với mã nguồn, giao diện, tài liệu, hành vi mạng và lịch sử phát hành.

## 5. Dấu hiệu nhận biết extension đáng ngờ

Không có một dấu hiệu đơn lẻ nào đủ để kết luận extension độc hại. Cần kết hợp nhiều bằng chứng và cân nhắc chức năng hợp lệ của sản phẩm.

### 5.1. Dấu hiệu về nguồn gốc và phát hành

- Tên, biểu tượng hoặc mô tả bắt chước sản phẩm nổi tiếng nhưng nhà phát hành khác.
- Nhà phát hành không có website, tài liệu, chính sách quyền riêng tư hoặc kênh hỗ trợ đáng tin cậy.
- Số lượt cài đặt, đánh giá hoặc lịch sử hoạt động không tương xứng với tuyên bố của sản phẩm.
- Tên extension hoặc nhà phát hành thay đổi bất thường.
- Bản cập nhật mới yêu cầu thêm quyền rộng mà không giải thích chức năng mới.
- Một extension lâu không cập nhật đột nhiên phát hành phiên bản có thay đổi lớn.
- Tài liệu mô tả một chức năng đơn giản nhưng danh sách quyền cho thấy khả năng truy cập rộng.

Đánh giá cửa hàng và số lượt cài đặt là tín hiệu tham khảo. Chúng có thể bị thao túng, không chứng minh mã nguồn an toàn và không thay thế việc kiểm tra quyền.

### 5.2. Dấu hiệu trong hành vi trình duyệt

- Công cụ tìm kiếm, trang chủ hoặc trang tab mới tự đổi.
- Trang web xuất hiện quảng cáo, banner, nút hoặc biểu mẫu mà trước đó không có.
- Liên kết bị thay đổi hoặc chuyển hướng qua domain lạ.
- Trình duyệt mở tab mới hoặc tải tệp không có thao tác tương ứng của người dùng.
- Một website chỉ hoạt động bình thường sau khi tắt extension.
- Extension tự bật lại, không thể gỡ hoặc bị chính sách quản trị cài lại.
- Trình duyệt chậm, CPU hoặc lưu lượng mạng tăng bất thường sau khi cài một tiện ích.
- Người dùng nhận được cảnh báo đăng nhập, xác thực hoặc giao dịch không do họ thực hiện.

Những biểu hiện này cũng có thể do phần mềm khác, cấu hình trình duyệt, đồng bộ tài khoản hoặc lỗi website. Hãy xác định extension liên quan bằng cách so sánh hành vi khi extension được bật và tắt, trong hồ sơ trình duyệt thử nghiệm hoặc môi trường an toàn.

### 5.3. Dấu hiệu trong mã nguồn và luồng dữ liệu

Khi được phép kiểm tra mã nguồn hoặc gói extension, cần chú ý:

- Content script được khai báo trên quá nhiều website so với chức năng.
- Mã đọc hàng loạt trường biểu mẫu, nội dung trang hoặc dữ liệu clipboard mà không có lý do rõ.
- Thông điệp từ content script được background xử lý như lệnh đáng tin cậy mà không xác thực loại lệnh và nguồn gửi.
- Dữ liệu trang được gửi đến domain không xuất hiện trong tài liệu hoặc chính sách quyền riêng tư.
- URL, truy vấn, nội dung trang hoặc thông tin tài khoản bị thêm vào query string hay payload gửi mạng.
- Có nhiều lớp mã hóa, làm rối hoặc tải cấu hình khó giải thích. Làm rối mã không tự động là độc hại, nhưng cần xem xét kỹ hơn.
- Mã thay đổi công cụ tìm kiếm, trang chủ, proxy hoặc nội dung website mà không thuộc chức năng đã công bố.
- Extension lưu dữ liệu nhạy cảm lâu dài hoặc đồng bộ dữ liệu vượt quá nhu cầu.
- Tài nguyên web-accessible công khai dữ liệu không cần thiết.
- Quyền native messaging được dùng nhưng không có giải thích về chương trình native.

Tìm thấy fetch, WebSocket, XMLHttpRequest, chrome.cookies hoặc chrome.scripting không đủ để kết luận có mã độc. Các API này có nhiều mục đích hợp pháp. Câu hỏi quan trọng là dữ liệu nào được xử lý, bởi ai, theo quyền nào, gửi đến đâu và vì sao.

## 6. Quy trình kiểm tra một extension

### 6.1. Bước 1: Ghi nhận danh tính

Mở trang quản lý extension của trình duyệt:

- Chrome: chrome://extensions
- Microsoft Edge: edge://extensions
- Firefox: about:addons

Bật chế độ nhà phát triển nếu cần xem ID hoặc thông tin kỹ thuật. Ghi lại:

- Tên và ID extension.
- Nhà phát hành.
- Phiên bản hiện tại.
- Thời điểm cài đặt hoặc thời điểm người dùng nhận thấy bất thường.
- Nguồn cài đặt và hồ sơ trình duyệt liên quan.
- Trạng thái bật/tắt, quyền và site access.
- Extension có được cài qua chính sách tổ chức hay không.

Không chia sẻ công khai ảnh chụp có URL nội bộ, email, tên khách hàng hoặc dữ liệu tài khoản. Khi cần gửi bằng chứng cho đội bảo mật, hãy dùng kênh được tổ chức phê duyệt.

### 6.2. Bước 2: Đối chiếu chức năng và quyền

Đọc trang giới thiệu, tài liệu, chính sách quyền riêng tư và quyền trong trang chi tiết extension. Tách các quyền thành ba nhóm:

- **Cần thiết:** trực tiếp phục vụ chức năng cốt lõi.
- **Có thể cần:** chỉ cần trong một số luồng hoặc khi người dùng chủ động bật tính năng.
- **Chưa giải thích được:** không có quan hệ rõ với chức năng được công bố.

Với quyền chưa giải thích được, tìm lý do trong tài liệu hoặc yêu cầu nhà phát triển giải thích. Nếu không có câu trả lời thuyết phục, không cài hoặc tạm thời vô hiệu hóa extension theo quy trình của tổ chức.

### 6.3. Bước 3: Kiểm tra thay đổi trình duyệt

Kiểm tra công cụ tìm kiếm mặc định, trang chủ, trang tab mới, quyền thông báo, proxy và danh sách extension. Xem extension nào có thể thay đổi các thiết lập đó. Một số trình duyệt có mục cho biết thiết lập bị extension quản lý.

Đừng chỉ nhìn tên extension trong giao diện. Đối chiếu ID, vì nhiều extension có thể dùng tên gần giống nhau.

### 6.4. Bước 4: Quan sát hành vi mạng

Nếu có quyền kiểm tra kỹ thuật:

1. Dùng hồ sơ thử nghiệm hoặc máy phân tích, tránh thử nghiệm trên tài khoản thật.
2. Mở DevTools và quan sát Network trong lúc tái hiện chức năng bình thường.
3. Kiểm tra domain đích, thời điểm gửi, tần suất, initiator và loại dữ liệu trong request.
4. Tìm yêu cầu được tạo khi mở một website, nhập dữ liệu hoặc chuyển tab.
5. Đối chiếu endpoint với tài liệu và chính sách quyền riêng tư.
6. Ghi lại request đáng ngờ cùng thời gian, URL đã được che dữ liệu nhạy cảm và phiên bản extension.

Trong Chrome, trang chrome://extensions có thể cung cấp liên kết kiểm tra service worker hoặc view của extension khi có thành phần đang hoạt động. Firefox có công cụ gỡ lỗi extension trong about:debugging. Tên và khả năng hiển thị thay đổi theo phiên bản trình duyệt.

Một request đến domain bên thứ ba không mặc nhiên độc hại. Dịch vụ phân tích, đồng bộ hoặc cập nhật có thể cần kết nối ngoài. Hãy kiểm tra dữ liệu gửi đi và mục đích của endpoint.

### 6.5. Bước 5: Kiểm tra gói và mã nguồn

Nếu có quyền và có bản mã nguồn đáng tin cậy:

- Xác minh gói thuộc đúng extension ID, nhà phát hành và phiên bản.
- So sánh với bản phát hành hoặc repository chính thức.
- Đọc manifest trước, sau đó lần theo các điểm vào như content script, background service worker và listener thông điệp.
- Tìm nơi đọc DOM, trường biểu mẫu, cookie, clipboard, lịch sử và thông tin tab.
- Tìm nơi gọi mạng, lưu trữ, sửa URL hoặc thay đổi nội dung trang.
- Kiểm tra thư viện phụ thuộc và thay đổi giữa các phiên bản.

Không tải gói từ nguồn không rõ chỉ để phân tích trên máy làm việc. Không cài thử extension nghi độc hại trên hồ sơ có dữ liệu thật. Nếu cần phân tích động, dùng máy ảo hoặc môi trường kiểm tra đã được cô lập và có quy trình thu thập bằng chứng.

## 7. Phòng vệ cho người dùng

### 7.1. Trước khi cài

- Chỉ cài extension có chức năng thực sự cần thiết.
- Kiểm tra tên nhà phát hành, website, chính sách quyền riêng tư và lịch sử cập nhật.
- Đọc quyền và site access; tự hỏi mỗi quyền có liên quan đến chức năng không.
- Kiểm tra kỹ extension yêu cầu truy cập mọi website, cookie, lịch sử, clipboard, debugger hoặc native messaging.
- Không dựa hoàn toàn vào số lượt cài đặt, dấu xác minh hoặc đánh giá.
- Tránh cài tệp extension từ website, quảng cáo, diễn đàn hoặc liên kết không rõ nguồn.
- Không cài extension chỉ vì một trang web yêu cầu để xem nội dung hoặc nhận phần thưởng.

### 7.2. Trong khi sử dụng

- Giới hạn site access ở những website cần thiết; chọn chỉ khi nhấn nếu chức năng hỗ trợ.
- Tắt hoặc gỡ extension không còn dùng.
- Kiểm tra trang quản lý extension sau khi trình duyệt thông báo thay đổi quyền hoặc sau một bản cập nhật đáng kể.
- Dùng hồ sơ trình duyệt riêng cho công việc nhạy cảm nếu tổ chức cho phép.
- Không cấp quyền native messaging, debugger hoặc clipboard cho tiện ích không có lý do rõ ràng.
- Giữ trình duyệt và hệ điều hành được cập nhật.
- Dùng xác thực đa yếu tố và cảnh báo đăng nhập cho các tài khoản quan trọng.

Chế độ site access giới hạn phạm vi hoạt động trên website, nhưng không loại bỏ mọi quyền khác của extension. Hãy đọc toàn bộ danh sách quyền.

### 7.3. Bảo vệ tài khoản khi nghi ngờ bị lộ

Nếu extension có thể đã đọc dữ liệu đăng nhập hoặc phiên:

- Dùng một thiết bị và hồ sơ trình duyệt sạch để truy cập tài khoản.
- Đổi mật khẩu nếu thông tin đăng nhập có khả năng đã bị thu thập.
- Đăng xuất các phiên hoặc thu hồi phiên đang hoạt động từ trang quản lý tài khoản.
- Thu hồi token, khóa API hoặc quyền OAuth có thể đã bị lộ.
- Bật hoặc kiểm tra MFA và rà soát lịch sử đăng nhập.
- Kiểm tra quy tắc chuyển tiếp email, thiết bị tin cậy, phương thức khôi phục và hoạt động giao dịch.
- Liên hệ đội bảo mật nếu tài khoản công việc, dữ liệu khách hàng hoặc hệ thống nội bộ có thể bị ảnh hưởng.

Đổi mật khẩu không phải lúc nào cũng vô hiệu hóa mọi phiên hoặc token đã phát hành. Cần thu hồi phiên và thông tin xác thực liên quan theo khả năng của dịch vụ.

## 8. Kiểm soát cho tổ chức

Tổ chức thường quản lý nhiều thiết bị, nhiều hồ sơ trình duyệt và extension được cài theo chính sách. Một extension độc hại có thể tạo rủi ro lan rộng nếu được triển khai tập trung hoặc người dùng dùng chung hồ sơ cho công việc và cá nhân.

Các kiểm soát nên có:

**Danh mục extension được phê duyệt.** Lưu ID, tên, nhà phát hành, phiên bản, chức năng, chủ sở hữu nghiệp vụ, quyền được chấp nhận và ngày đánh giá gần nhất.

**Chính sách cài đặt.** Dùng chính sách quản trị của trình duyệt để chỉ cho phép extension đã duyệt, chặn extension không được phép hoặc giới hạn nguồn cài đặt. Tên chính sách và cách cấu hình phụ thuộc trình duyệt và phiên bản.

**Quản lý thay đổi.** Đánh giá lại khi extension đổi nhà phát hành, tăng quyền, thay đổi chính sách quyền riêng tư hoặc có bản cập nhật làm thay đổi chức năng.

**Phân vùng dữ liệu.** Hạn chế extension trên hồ sơ dùng để truy cập hệ thống tài chính, quản trị, dữ liệu khách hàng hoặc hệ thống sản xuất. Không cấp extension không cần thiết cho tài khoản đặc quyền.

**Giám sát.** Theo dõi danh sách extension, ID, phiên bản, nguồn cài đặt, quyền và thay đổi chính sách trên thiết bị được quản lý. Kết hợp với log endpoint, DNS, proxy, EDR hoặc telemetry phù hợp để phát hiện endpoint bất thường.

**Quy trình ngoại lệ.** Nếu bộ phận nghiệp vụ cần một extension mới, yêu cầu nêu chức năng, dữ liệu truy cập, quyền, nhà phát hành và thời hạn sử dụng. Phê duyệt nên có chủ sở hữu và ngày xem xét lại.

**Ứng phó tập trung.** Chuẩn bị cách vô hiệu hóa hoặc chặn extension theo ID, xác định thiết bị bị ảnh hưởng, thu thập bằng chứng và thông báo cho chủ sở hữu dữ liệu.

Một danh sách cho phép cần được rà soát định kỳ. Extension từng an toàn vẫn có thể bị chiếm tài khoản nhà phát hành hoặc thay đổi sau một lần cập nhật.

## 9. Hướng dẫn cho nhà phát triển extension an toàn

Nhà phát triển có trách nhiệm giảm quyền cần thiết, giới hạn dữ liệu và bảo vệ quy trình phát hành. Một extension có chức năng hợp pháp vẫn có thể tạo rủi ro nếu thiết kế quyền quá rộng hoặc xử lý thông điệp thiếu kiểm tra.

### 9.1. Áp dụng nguyên tắc quyền tối thiểu

- Chỉ khai báo API cần cho chức năng thực tế.
- Giới hạn host permission theo domain cụ thể.
- Dùng optional permissions khi quyền chỉ cần cho một tính năng phụ.
- Yêu cầu quyền tại thời điểm người dùng kích hoạt tính năng có liên quan, kèm giải thích dễ hiểu.
- Ưu tiên activeTab khi chỉ cần truy cập tab sau một thao tác rõ ràng và API hỗ trợ.
- Không khai báo "<all_urls>" chỉ để tránh thiết kế lại phạm vi quyền.
- Tránh debugger, nativeMessaging, clipboardRead và cookies nếu sản phẩm không có yêu cầu rõ ràng.

Ví dụ yêu cầu quyền host bổ sung sau thao tác người dùng:

~~~javascript
const granted = await chrome.permissions.request({
  origins: ["https://portal.example.com/*"]
});

if (granted) {
  // Chỉ bật tính năng cần truy cập portal.example.com.
} else {
  // Giải thích tính năng nào chưa thể hoạt động.
}
~~~

Lời gọi yêu cầu quyền phải được gắn với một thao tác người dùng phù hợp và tuân thủ quy tắc của trình duyệt. Không liên tục hỏi lại khi người dùng từ chối.

### 9.2. Xác thực thông điệp giữa content script và background

Content script xử lý dữ liệu từ trang, nên background không được xem mọi thông điệp là đáng tin. Hãy giới hạn loại thông điệp, xác thực sender, kiểm tra cấu trúc dữ liệu và chỉ cho phép thao tác cần thiết.

Ví dụ minh họa:

~~~javascript
const ALLOWED_MESSAGE_TYPES = new Set([
  "GET_FEATURE_STATUS"
]);

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id) {
    return;
  }

  if (!message || !ALLOWED_MESSAGE_TYPES.has(message.type)) {
    return;
  }

  if (message.type === "GET_FEATURE_STATUS") {
    sendResponse({ enabled: true });
  }
});
~~~

Đây là lớp kiểm tra cơ bản, không thay thế xác thực ngữ cảnh cụ thể. Với thao tác nhạy cảm, cần kiểm tra tab, frame, URL hoặc origin được phép, kiểu và kích thước dữ liệu, trạng thái người dùng và quyền cần thiết. Không xây dựng một message handler tổng quát cho phép content script truyền tên API hoặc tham số tùy ý để background thực thi.

Nếu extension hỗ trợ thông điệp từ extension khác, hãy giới hạn externally_connectable và xác thực sender theo danh sách được phép. Không nhận lệnh quản trị chỉ vì thông điệp có cấu trúc hợp lệ.

### 9.3. Xử lý DOM và dữ liệu không tin cậy

- Xem nội dung trang, thuộc tính HTML, URL và thông điệp từ content script là dữ liệu không tin cậy.
- Dùng textContent khi chỉ cần hiển thị văn bản.
- Tránh innerHTML với dữ liệu lấy từ trang hoặc máy chủ.
- Kiểm tra scheme và host trước khi mở URL.
- Không đưa dữ liệu trang vào eval, Function, bộ xử lý template có khả năng thực thi hoặc API tương đương.
- Giới hạn loại dữ liệu được gửi về background.
- Không ghi nội dung biểu mẫu, token hoặc cookie vào console log.

### 9.4. Bảo vệ dữ liệu và kết nối

- Thu thập ít dữ liệu nhất có thể.
- Nêu rõ mục đích, loại dữ liệu, bên nhận và thời gian lưu.
- Gửi dữ liệu qua HTTPS và xác thực endpoint.
- Không đặt token dịch vụ dùng chung hoặc khóa bí mật dài hạn trong mã extension; gói extension được phân phối cho người dùng không phải nơi giữ bí mật.
- Không lưu mật khẩu hoặc token nhạy cảm trong storage.sync hay storage.local nếu không có thiết kế bảo vệ phù hợp.
- Có cơ chế xóa dữ liệu và xử lý yêu cầu quyền riêng tư.
- Giới hạn quyền truy cập backend theo người dùng, phạm vi và mục đích.
- Không coi dữ liệu do extension gửi lên là đáng tin chỉ vì nó đến từ extension ID đã biết.

### 9.5. Bảo vệ chuỗi cung ứng và phát hành

- Bật MFA mạnh cho tài khoản nhà phát hành và tài khoản kho mã nguồn.
- Giới hạn người có quyền phát hành và quyền quản trị.
- Dùng lockfile, phiên bản phụ thuộc có kiểm soát và rà soát thư viện.
- Quét phụ thuộc và kiểm tra thay đổi bất thường trong build.
- Tách môi trường phát triển, kiểm thử và phát hành.
- Tạo gói phát hành từ quy trình CI có kiểm soát.
- Lưu lại mã nguồn, commit, artifact, người phê duyệt và phiên bản đã phát hành.
- Theo dõi quyền và hành vi sau phát hành.
- Có kế hoạch thu hồi hoặc phát hành bản sửa lỗi khi tài khoản, dependency hoặc gói bị xâm nhập.

Chrome Manifest V3 giới hạn việc nạp mã thực thi từ xa và yêu cầu logic thực thi nằm trong gói extension theo chính sách áp dụng. Nhà phát triển cần kiểm tra tài liệu hiện hành của từng cửa hàng và trình duyệt. Việc tuân thủ giới hạn mã từ xa không tự chứng minh extension an toàn; mã độc vẫn có thể được đóng gói trực tiếp trong artifact.

### 9.6. Chính sách extension và bảo vệ nội dung

- Dùng CSP phù hợp cho trang extension và không nới lỏng chính sách chỉ để chạy mã tùy ý.
- Không công khai tài nguyên qua web_accessible_resources nếu không cần.
- Giới hạn externally_connectable ở những website thực sự cần giao tiếp.
- Dùng quy tắc mạng khai báo trong phạm vi phù hợp và rà soát thay đổi.
- Kiểm tra kỹ mọi đường đi từ dữ liệu trang đến API có đặc quyền.
- Không để một content script có thể yêu cầu background đọc cookie, lịch sử hoặc dữ liệu khác chỉ bằng một message không được xác thực.

## 10. Ứng phó khi phát hiện extension độc hại

Mục tiêu ứng phó là ngăn dữ liệu tiếp tục bị thu thập, bảo vệ tài khoản, xác định phạm vi ảnh hưởng và giữ lại bằng chứng cần thiết.

### 10.1. Đối với người dùng cá nhân

1. **Ngừng sử dụng extension đáng ngờ.** Nếu không cần bảo toàn bằng chứng, vô hiệu hóa extension trong trang quản lý. Nếu thiết bị thuộc tổ chức hoặc có điều tra đang diễn ra, liên hệ đội IT/security trước khi gỡ.
2. **Ghi nhận thông tin.** Lưu ID, tên, phiên bản, nhà phát hành, quyền, thời điểm phát hiện và ảnh chụp phù hợp. Che URL, email và dữ liệu riêng tư.
3. **Gỡ extension nếu được hướng dẫn.** Nếu extension tự bật lại hoặc không gỡ được, kiểm tra chính sách quản trị và liên hệ bộ phận hỗ trợ.
4. **Bảo vệ tài khoản.** Dùng thiết bị sạch để đổi mật khẩu, thu hồi phiên, thu hồi token và kiểm tra hoạt động đăng nhập.
5. **Rà soát thay đổi trình duyệt.** Khôi phục công cụ tìm kiếm, trang chủ, tab mới và quyền đã bị thay đổi.
6. **Kiểm tra thiết bị.** Chạy công cụ bảo vệ endpoint phù hợp và kiểm tra chương trình native nếu extension có dùng native messaging.
7. **Theo dõi sau xử lý.** Kiểm tra đăng nhập, giao dịch, email chuyển tiếp và cảnh báo bảo mật trong một khoảng thời gian phù hợp.

### 10.2. Đối với tổ chức

- Mở incident và xác định người chịu trách nhiệm xử lý.
- Thu thập ID, phiên bản, hash artifact nếu có, thiết bị, hồ sơ trình duyệt và thời điểm cài/cập nhật.
- Xác định extension được cài theo chính sách hay do người dùng tự cài.
- Chặn hoặc vô hiệu hóa extension theo ID bằng chính sách quản trị.
- Tìm thiết bị khác có cùng ID hoặc cùng phiên bản.
- Bảo toàn log endpoint, proxy, DNS, trình duyệt và xác thực theo chính sách lưu trữ.
- Xác định website, tài khoản, dữ liệu và token có thể đã bị truy cập.
- Thu hồi phiên và thông tin xác thực bị ảnh hưởng; phối hợp chủ sở hữu ứng dụng để đánh giá tác động.
- Kiểm tra chương trình native hoặc thay đổi hệ thống nếu có dấu hiệu extension đã gọi thành phần cục bộ.
- Thông báo cho chủ sở hữu dữ liệu, pháp chế hoặc bộ phận quyền riêng tư theo quy trình tổ chức.
- Theo dõi bản cập nhật sạch và chỉ cho phép lại sau khi có đánh giá.

Không xóa log hoặc gỡ toàn bộ dấu vết trước khi đội điều tra xác định dữ liệu cần giữ. Với máy cá nhân, việc gỡ extension thường là bước thực tế; với thiết bị có sự cố bảo mật, thứ tự xử lý nên theo quy trình điều tra của tổ chức.

### 10.3. Xác định mức độ ảnh hưởng

Dùng các câu hỏi sau để khoanh vùng:

- Extension đã được cài trên bao nhiêu thiết bị và hồ sơ trình duyệt?
- Phiên bản nào có hành vi đáng ngờ? Bản cập nhật bắt đầu từ khi nào?
- Extension được phép truy cập domain nào?
- Có tài khoản đặc quyền hoặc website nội bộ nào được mở trong thời gian đó?
- Dữ liệu nào có thể xuất hiện trong DOM hoặc trường biểu mẫu?
- Extension có quyền cookies, history, clipboardRead, webRequest, debugger hoặc nativeMessaging không?
- Endpoint bên ngoài nào đã được liên hệ và dữ liệu nào được gửi?
- Có dấu hiệu thay đổi thiết lập, chuyển hướng, cài thêm phần mềm hoặc truy cập trái phép không?
- Có cần thu hồi OAuth grant, API key, phiên đăng nhập hoặc khóa truy cập khác không?

Mức độ ảnh hưởng phải dựa trên bằng chứng. Có quyền đọc một loại dữ liệu không chứng minh dữ liệu đó đã bị lấy đi; ngược lại, không thấy request trong một lần kiểm tra không chứng minh dữ liệu chưa từng được gửi.

## 11. Thực hành kiểm tra an toàn

Các bài thực hành sau dùng manifest minh họa và môi trường thử nghiệm. Không cài extension không rõ nguồn trên hồ sơ thật, không nhập mật khẩu thật và không gửi dữ liệu cá nhân trong quá trình kiểm tra.

### Lab 1: Kiểm kê quyền của extension

**Mục tiêu:** Biết tìm ID, phiên bản, quyền và site access.

**Các bước:**

1. Mở trang quản lý extension của trình duyệt.
2. Chọn một extension đã được tổ chức hoặc cá nhân tin cậy phê duyệt.
3. Ghi lại ID, phiên bản, nhà phát hành và quyền.
4. Mở phần site access và xác định domain extension được phép truy cập.
5. So sánh quyền với chức năng được công bố.
6. Ghi lại ít nhất một quyền cần thiết và một quyền cần được giải thích thêm.

**Kết quả mong đợi:** Có bảng kiểm kê gồm danh tính, chức năng, quyền, phạm vi website và nhận xét. Không kết luận extension độc hại chỉ vì có một quyền rộng.

### Lab 2: Đánh giá manifest mẫu

**Mục tiêu:** Phân tích bề mặt quyền mà không thực thi extension.

Dùng manifest minh họa ở mục 4.3 và điền bảng:

| Trường | Giá trị | Ý nghĩa | Rủi ro cần xác minh |
|---|---|---|---|
| manifest_version | 3 | Phiên bản manifest | Không phải chỉ báo an toàn |
| permissions | tabs, scripting, storage | API extension được yêu cầu | Đối chiếu với chức năng |
| host_permissions | "&lt;all_urls&gt;" | Phạm vi host rộng | Cần lý do rõ ràng |
| content_scripts.matches | "&lt;all_urls&gt;" | Content script có thể chạy trên mọi website khớp | Nguy cơ đọc/sửa DOM diện rộng |
| background.service_worker | background.js | Thành phần xử lý sự kiện nền | Kiểm tra message handler và request mạng |

**Câu hỏi:** Nếu extension chỉ đổi màu giao diện trên một website, cần thu hẹp trường nào? Chức năng nào có thể dùng quyền tạm thời thay cho quyền host dài hạn?

### Lab 3: Quan sát thay đổi hành vi

**Mục tiêu:** Phân biệt hành vi của website với hành vi do extension gây ra.

1. Chọn một website thử nghiệm không chứa dữ liệu thật.
2. Quan sát trang khi extension được bật.
3. Ghi lại các thay đổi về nội dung, URL, tab và request mạng.
4. Tắt extension rồi tải lại website.
5. So sánh kết quả và lặp lại trong hồ sơ thử nghiệm sạch nếu cần.
6. Ghi rõ điều kiện tái hiện, thời điểm và phiên bản extension.

**Kết quả mong đợi:** Một bảng so sánh bật/tắt extension. Chênh lệch là bằng chứng để điều tra tiếp, chưa phải kết luận cuối cùng.

### Lab 4: Xây dựng bảng đánh giá rủi ro

**Mục tiêu:** Đưa ra quyết định dựa trên bằng chứng.

Chấm mỗi yếu tố theo mức Thấp, Trung bình, Cao hoặc Chưa rõ:

| Yếu tố | Câu hỏi |
|---|---|
| Danh tính | Nhà phát hành và ID có xác minh được không? |
| Quyền | Quyền có phù hợp chức năng không? |
| Phạm vi host | Extension truy cập bao nhiêu website? |
| Dữ liệu | Có thu thập dữ liệu nhạy cảm không? |
| Mạng | Endpoint và payload có giải thích được không? |
| Cập nhật | Có thay đổi quyền hoặc hành vi bất thường không? |
| Quản trị | Có thể kiểm soát, vô hiệu hóa và theo dõi không? |

Kết thúc bằng một trong các quyết định: chấp thuận, chấp thuận có điều kiện, yêu cầu giải thích, tạm dừng hoặc chặn. Ghi rõ bằng chứng và người chịu trách nhiệm xem xét lại.

## 12. Những hiểu lầm thường gặp

**“Cài từ cửa hàng chính thức thì chắc chắn an toàn.”** Cửa hàng có quy trình xét duyệt và cơ chế thực thi chính sách, nhưng vẫn có thể xuất hiện extension độc hại, tài khoản nhà phát hành bị chiếm hoặc bản cập nhật có vấn đề.

**“Extension có nhiều lượt cài thì đáng tin.”** Lượt cài và đánh giá không chứng minh mã nguồn, luồng dữ liệu hoặc nhà phát hành hiện tại là an toàn.

**“Isolated world ngăn extension đọc dữ liệu website.”** Isolated world tách môi trường JavaScript, nhưng content script vẫn có thể tương tác với DOM trong phạm vi được phép.

**“HttpOnly bảo vệ cookie trước mọi extension.”** HttpOnly chủ yếu ngăn JavaScript trang đọc cookie. Extension có quyền cookies và host permission phù hợp có thể dùng API extension để truy cập cookie theo phạm vi được cấp.

**“Có quyền tabs nghĩa là đọc được toàn bộ nội dung mọi tab.”** tabs chủ yếu liên quan metadata tab; đọc nội dung trang cần quyền hoặc cơ chế khác như content script, host permission, scripting hoặc activeTab.

**“Manifest V3 loại bỏ mã độc.”** MV3 thay đổi kiến trúc và giới hạn mã thực thi từ xa trong Chrome, nhưng mã độc vẫn có thể nằm trong gói extension hoặc lạm dụng API được cấp.

**“Không thấy request đáng ngờ nghĩa là extension an toàn.”** Hành vi có thể chỉ kích hoạt theo điều kiện, tài khoản, domain, thời gian hoặc bản cập nhật. Một lần quan sát không đủ để chứng minh an toàn.

**“Gỡ extension là đủ.”** Nếu dữ liệu hoặc token đã bị thu thập, cần thu hồi phiên, đổi thông tin xác thực phù hợp và kiểm tra tài khoản, thiết bị cùng dữ liệu liên quan.

**“Mã bị làm rối chắc chắn là mã độc.”** Một số sản phẩm tối ưu hoặc bảo vệ mã nguồn bằng kỹ thuật làm rối. Đây là tín hiệu cần xem xét, không phải kết luận độc lập.

## 13. Checklist đánh giá và vận hành

### Trước khi phê duyệt

- [ ] Xác minh đúng extension ID, nhà phát hành và nguồn phát hành.
- [ ] Hiểu chức năng cốt lõi và dữ liệu extension cần truy cập.
- [ ] Đối chiếu từng quyền với chức năng.
- [ ] Kiểm tra host permissions và content script match patterns.
- [ ] Đánh giá quyền nhạy cảm như cookies, history, clipboard, debugger và native messaging.
- [ ] Đọc chính sách quyền riêng tư và endpoint dịch vụ.
- [ ] Xác định chủ sở hữu nghiệp vụ và thời điểm đánh giá lại.
- [ ] Thử nghiệm trong hồ sơ hoặc thiết bị phù hợp trước khi triển khai rộng.

### Trong vận hành

- [ ] Theo dõi ID, phiên bản, quyền và thay đổi nhà phát hành.
- [ ] Rà soát khi có bản cập nhật lớn hoặc yêu cầu quyền mới.
- [ ] Giới hạn site access theo nhu cầu.
- [ ] Gỡ hoặc vô hiệu hóa extension không còn cần.
- [ ] Theo dõi thay đổi công cụ tìm kiếm, trang chủ, tab mới và proxy.
- [ ] Kiểm tra endpoint mạng khi có dấu hiệu bất thường.
- [ ] Duy trì danh sách cho phép và quy trình ngoại lệ.

### Khi có sự cố

- [ ] Ghi lại ID, phiên bản, thời điểm và thiết bị liên quan.
- [ ] Vô hiệu hóa hoặc chặn extension theo quy trình phù hợp.
- [ ] Xác định phạm vi thiết bị, hồ sơ và tài khoản bị ảnh hưởng.
- [ ] Bảo toàn log và artifact cần cho điều tra.
- [ ] Thu hồi phiên, token và khóa có nguy cơ bị lộ.
- [ ] Kiểm tra hoạt động tài khoản và thay đổi trình duyệt.
- [ ] Thông báo chủ sở hữu dữ liệu và các nhóm chịu trách nhiệm.
- [ ] Theo dõi sau khắc phục và chỉ cho phép lại khi đã đánh giá.

## 14. Câu hỏi tự kiểm tra

### Câu 1

Một extension đổi màu giao diện cho một website nhưng khai báo "&lt;all_urls&gt;" trong host permissions. Kết luận phù hợp nhất là gì?

A. Chắc chắn là mã độc.  
B. Quyền có phạm vi rộng hơn chức năng được mô tả và cần được giải thích hoặc thu hẹp.  
C. Quyền này không tạo rủi ro vì extension chạy trong trình duyệt.  
D. Chỉ cần xem số lượt cài đặt để quyết định.

**Đáp án: B.** Quyền rộng là tín hiệu cần đánh giá. Cần xem chức năng, mã và luồng dữ liệu trước khi kết luận.

### Câu 2

Isolated world của content script bảo vệ điều gì?

A. Che toàn bộ DOM khỏi extension.  
B. Tách một phần môi trường JavaScript của content script khỏi JavaScript của trang.  
C. Ngăn content script đọc mọi trường biểu mẫu.  
D. Tự động mã hóa dữ liệu mà content script gửi đi.

**Đáp án: B.** DOM vẫn là bề mặt dùng chung, vì vậy content script có thể đọc hoặc sửa nội dung trang trong phạm vi được phép.

### Câu 3

Quyền tabs có đồng nghĩa extension có thể đọc toàn bộ nội dung mọi trang không?

A. Có, trong mọi trình duyệt.  
B. Không; đọc nội dung trang còn phụ thuộc content script, host permission, scripting hoặc quyền khác.  
C. Có, nhưng chỉ khi trình duyệt ở chế độ ẩn danh.  
D. Không, vì quyền này chỉ dùng để đổi biểu tượng.

**Đáp án: B.** Cần phân biệt metadata tab với quyền truy cập nội dung trang.

### Câu 4

Vì sao HttpOnly không bảo vệ cookie trước mọi extension?

A. Vì HttpOnly chỉ có hiệu lực khi website dùng HTTP.  
B. Vì extension có quyền cookies và host permission phù hợp có thể truy cập cookie qua API extension.  
C. Vì mọi content script đều chạy cùng origin với background.  
D. Vì trình duyệt không hỗ trợ thuộc tính HttpOnly.

**Đáp án: B.** HttpOnly bảo vệ trước JavaScript trang thông thường, không thay thế mô hình quyền của extension.

### Câu 5

Một bản cập nhật yêu cầu thêm quyền truy cập lịch sử duyệt web nhưng không có chức năng mới được giải thích. Nên làm gì?

A. Chấp nhận vì extension đã được cài từ trước.  
B. Xóa log để tránh cảnh báo.  
C. Tạm dừng hoặc yêu cầu giải thích, sau đó đánh giá lại quyền và thay đổi.  
D. Chỉ kiểm tra biểu tượng extension.

**Đáp án: C.** Quyền mới là thay đổi cần được xem xét, đặc biệt khi quyền không phù hợp chức năng.

### Câu 6

Dấu hiệu nào có giá trị nhất khi điều tra việc extension gửi dữ liệu ra ngoài?

A. Chỉ có tên hàm fetch trong mã nguồn.  
B. Endpoint, thời điểm, initiator, payload và quan hệ với dữ liệu mà extension truy cập.  
C. Màu sắc của biểu tượng.  
D. Số lượng file trong gói extension.

**Đáp án: B.** API mạng có thể được dùng hợp pháp; cần phân tích luồng dữ liệu và mục đích.

### Câu 7

Chrome Manifest V3 hạn chế mã thực thi từ xa. Điều đó có nghĩa gì?

A. Extension MV3 không thể độc hại.  
B. Mọi dữ liệu từ máy chủ đều bị cấm.  
C. Mã thực thi phải tuân thủ chính sách đóng gói; mã độc vẫn có thể nằm trong gói hoặc lạm dụng logic được cấp quyền.  
D. Extension không thể kết nối Internet.

**Đáp án: C.** Giới hạn mã từ xa giảm một loại rủi ro nhưng không chứng minh logic extension an toàn.

### Câu 8

Một tổ chức phát hiện cùng một extension đáng ngờ trên nhiều máy. Hành động nào nên được ưu tiên?

A. Chỉ yêu cầu từng người dùng tự tìm và gỡ.  
B. Xác định ID và phạm vi ảnh hưởng, dùng chính sách quản trị để chặn hoặc vô hiệu hóa, đồng thời bảo toàn bằng chứng cần thiết.  
C. Xóa toàn bộ hồ sơ trình duyệt ngay lập tức.  
D. Chỉ đổi mật khẩu quản trị viên.

**Đáp án: B.** Xử lý tập trung giúp kiểm soát phạm vi, giữ bằng chứng và điều phối thu hồi thông tin xác thực.

### Câu 9

Vì sao background không nên thực thi mọi lệnh nhận từ content script?

A. Content script luôn thuộc một tiến trình khác.  
B. Nội dung trang và thông điệp có thể bị tác động bởi website; background có thể có quyền cao hơn nên cần xác thực nguồn, loại lệnh và dữ liệu.  
C. Message API chỉ dùng cho giao diện popup.  
D. Background không thể nhận dữ liệu JSON.

**Đáp án: B.** Kiểm tra thông điệp giúp tránh biến content script thành đường gọi API có đặc quyền tùy ý.

### Câu 10

Người dùng nghi extension đã thu thập token phiên. Đổi mật khẩu có đủ không?

A. Luôn đủ.  
B. Không cần làm gì nếu đã gỡ extension.  
C. Cần đánh giá và thu hồi phiên hoặc token bị ảnh hưởng; đổi mật khẩu có thể là một phần của xử lý.  
D. Chỉ cần xóa lịch sử duyệt web.

**Đáp án: C.** Token và phiên đang hoạt động có thể tồn tại độc lập với mật khẩu.

### Câu 11

Một extension dùng native messaging. Điều cần xác minh thêm là gì?

A. Chỉ cần xem số lượt cài đặt.  
B. Tên, nguồn cài đặt, quyền và hành vi của chương trình native mà extension giao tiếp.  
C. Chỉ cần kiểm tra màu giao diện.  
D. Không cần xác minh vì native messaging là API chính thức.

**Đáp án: B.** Native host có thể thực hiện hành động cục bộ; cần đánh giá toàn bộ chuỗi giao tiếp.

### Câu 12

Không quan sát thấy request bất thường trong một lần kiểm tra chứng minh điều gì?

A. Extension chắc chắn an toàn.  
B. Extension không có quyền truy cập dữ liệu.  
C. Chỉ chứng minh rằng trong lần kiểm tra đó chưa quan sát được request bất thường.  
D. Extension không thể hoạt động sau khi cập nhật.

**Đáp án: C.** Hành vi có thể phụ thuộc điều kiện và thời điểm; kết luận cần nhiều nguồn bằng chứng.

## 15. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Extension | Tiện ích mở rộng bổ sung chức năng cho trình duyệt |
| Manifest | Tệp khai báo metadata, quyền và thành phần của extension |
| Content script | Mã chạy trên trang được phép để tương tác với DOM |
| Isolated world | Môi trường JavaScript riêng của content script |
| Background service worker | Thành phần nền xử lý sự kiện trong kiến trúc Manifest V3 của Chrome |
| Host permission | Quyền truy cập một hoặc nhiều website theo match pattern |
| Optional permission | Quyền bổ sung được yêu cầu khi cần trong lúc chạy |
| activeTab | Quyền truy cập tạm thời vào tab sau thao tác người dùng theo quy tắc trình duyệt |
| Native messaging | Cơ chế giao tiếp giữa extension và chương trình native trên thiết bị |
| Supply chain | Chuỗi công cụ, thư viện, tài khoản và quy trình tạo/phát hành phần mềm |
| Exfiltration | Đưa dữ liệu ra khỏi môi trường hoặc tổ chức trái phép |
| Least privilege | Chỉ cấp quyền tối thiểu cần cho chức năng |
| Artifact | Gói phần mềm được tạo ra từ quy trình build và phát hành |
| Incident response | Quy trình phát hiện, khoanh vùng, xử lý và khôi phục sau sự cố |

## Tài liệu tham khảo

- Chrome for Developers — [Stay secure](https://developer.chrome.com/docs/extensions/develop/security-privacy/stay-secure): hướng dẫn bảo mật extension và thực hành giảm rủi ro.
- Chrome for Developers — [Declare permissions](https://developer.chrome.com/docs/extensions/develop/concepts/declare-permissions): cách khai báo quyền, host permissions và optional permissions.
- Chrome for Developers — [Content scripts](https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts): cách content script hoạt động và tương tác với trang.
- Chrome for Developers — [Extension service workers](https://developer.chrome.com/docs/extensions/develop/concepts/service-workers): vòng đời và mô hình xử lý sự kiện của service worker.
- Chrome for Developers — [Migrate to a service worker](https://developer.chrome.com/docs/extensions/develop/migrate/to-service-workers): khác biệt kiến trúc background trong Manifest V3.
- Chrome for Developers — [Deal with remote hosted code violations](https://developer.chrome.com/docs/extensions/develop/migrate/remote-hosted-code): giới hạn mã thực thi từ xa trong Manifest V3.
- Chrome Web Store — [Program policies](https://developer.chrome.com/docs/webstore/program-policies): yêu cầu chính sách đối với extension phát hành trên Chrome Web Store.
- MDN Web Docs — [Permissions](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/manifest.json/permissions): mô tả quyền WebExtensions và khác biệt triển khai.
- MDN Web Docs — [Content scripts](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Content_scripts): môi trường chạy và giới hạn của content script.
- MITRE ATT&CK — [Browser Extensions (T1176)](https://attack.mitre.org/techniques/T1176/): mô tả kỹ thuật đối thủ lạm dụng extension để duy trì hoặc mở rộng quyền truy cập.

Các API, tên quyền và chính sách cửa hàng có thể thay đổi theo trình duyệt và phiên bản. Khi triển khai hoặc điều tra thực tế, hãy kiểm tra tài liệu chính thức tương ứng với trình duyệt đang sử dụng.

