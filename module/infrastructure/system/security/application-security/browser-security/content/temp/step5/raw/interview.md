Bạn định nghĩa origin của một trang web theo scheme, host và port như thế nào, và vì sao từng thành phần đều quan trọng?
Bạn phân biệt same-origin với same-site và giải thích vì sao hai khái niệm này dẫn đến các quyết định bảo mật khác nhau như thế nào?
Bạn mô tả Same-Origin Policy giới hạn việc đọc dữ liệu giữa các origin trong DOM, storage và request như thế nào?
Bạn phân biệt hành vi gửi một cross-origin request với quyền đọc response của request đó theo SOP như thế nào?
Bạn giải thích vì sao SOP không phải cơ chế xác thực hoặc phân quyền truy cập API phía máy chủ như thế nào?
Bạn phân tích các trường hợp origin opaque phát sinh từ sandboxed iframe, data URL hoặc tài liệu đặc biệt như thế nào?
Bạn xác định tác động của scheme, port và hostname khác nhau đến việc trình duyệt đánh giá hai URL có cùng origin hay không như thế nào?
Bạn mô tả cách CORS cho phép server công bố quyền truy cập response cho một origin khác như thế nào?
Bạn phân biệt CORS simple request với preflight request và xác định điều kiện khiến trình duyệt gửi OPTIONS như thế nào?
Bạn giải thích vai trò của Origin, Access-Control-Allow-Origin và Access-Control-Allow-Methods trong quá trình kiểm tra CORS như thế nào?
Bạn lựa chọn cách phản hồi Access-Control-Allow-Headers khi client gửi custom header hoặc Authorization header như thế nào?
Bạn phân biệt Access-Control-Allow-Credentials với việc trình duyệt tự động gửi cookie hoặc HTTP authentication như thế nào?
Bạn giải thích vì sao Access-Control-Allow-Origin không thể dùng wildcard khi response cho phép credentials như thế nào?
Bạn thiết kế CORS policy cho API phục vụ nhiều frontend origin đã đăng ký mà không phản chiếu tùy tiện giá trị Origin như thế nào?
Bạn đánh giá rủi ro bảo mật khi server phản hồi Access-Control-Allow-Origin bằng mọi origin được gửi lên như thế nào?
Bạn sử dụng Vary: Origin để tránh cache dùng nhầm response CORS giữa các origin khác nhau như thế nào?
Bạn xác định vai trò của Access-Control-Max-Age và các giới hạn của việc cache kết quả preflight như thế nào?
Bạn xử lý tình huống preflight OPTIONS bị reverse proxy hoặc authentication middleware chặn trước khi tới ứng dụng như thế nào?
Bạn phân biệt lỗi CORS do trình duyệt chặn response với lỗi HTTP thực sự do server trả về như thế nào?
Bạn kiểm tra CORS bằng DevTools Network và console để xác định header hoặc bước preflight bị cấu hình sai như thế nào?
Bạn giải thích vì sao Postman hoặc curl gọi API thành công không chứng minh trình duyệt sẽ cho phép JavaScript đọc response như thế nào?
Khi một CORS request đi qua redirect, bạn kiểm tra từng response và request tiếp theo để tìm bước không đáp ứng policy ra sao?
Bạn phân biệt CORS policy cho fetch/XHR với các cơ chế kiểm soát việc nhúng ảnh, script, font hoặc iframe từ origin khác như thế nào?
Bạn giải thích vai trò của Cross-Origin Resource Policy, Cross-Origin Embedder Policy và Cross-Origin Opener Policy trong cách ly tài nguyên trình duyệt như thế nào?
Bạn xác định khi nào cần cấu hình COOP, COEP và CORP để tạo cross-origin isolation và những hệ quả tương thích nào cần kiểm tra?
Bạn phân biệt cookie host-only với cookie có Domain attribute và đánh giá phạm vi gửi cookie giữa các subdomain như thế nào?
Bạn giải thích tác động của Path, Expires, Max-Age, Secure, HttpOnly và SameSite đến hành vi cookie như thế nào?
Bạn phân biệt SameSite=Strict, Lax và None trong các luồng điều hướng top-level, form submission và embedded request như thế nào?
Bạn xác định khi nào cookie SameSite=None bắt buộc phải đi cùng Secure và ảnh hưởng của chính sách chặn third-party cookie ra sao?
Bạn thiết kế cookie phiên đăng nhập an toàn khi frontend và API nằm trên các subdomain hoặc site khác nhau như thế nào?
Những thuộc tính Secure, Path=/ và việc bỏ Domain tạo ra bảo đảm gì cho tiền tố __Host-, và __Secure- bổ sung ràng buộc nào?
Bạn phân biệt cookie HttpOnly với cơ chế chống XSS và giải thích vì sao HttpOnly không ngăn mọi tác động của XSS như thế nào?
Bạn phân tích cách trình duyệt gửi cookie theo domain, path, secure context và SameSite khi request được khởi tạo từ trang khác origin như thế nào?
Bạn đánh giá rủi ro session fixation hoặc session hijacking và cách quản lý vòng đời session cookie như thế nào?
Bạn giải thích XSS xảy ra khi dữ liệu không tin cậy được đưa vào execution context của trình duyệt như thế nào?
Bạn phân biệt reflected XSS, stored XSS và DOM-based XSS qua nguồn dữ liệu và điểm thực thi như thế nào?
Bạn xác định các context HTML, attribute, JavaScript, CSS và URL đòi hỏi cách output encoding khác nhau như thế nào?
Bạn lựa chọn output encoding phù hợp với context thay vì dùng một hàm escape chung cho mọi vị trí như thế nào?
Bạn phân biệt sanitization HTML với output encoding và xác định khi nào ứng dụng cần từng biện pháp như thế nào?
Bạn thiết kế cách xử lý rich text do người dùng nhập để chỉ cho phép markup an toàn mà không mở đường cho XSS như thế nào?
Bạn nhận diện các DOM sink nguy hiểm như innerHTML, outerHTML, document.write và đánh giá lựa chọn API an toàn hơn như thế nào?
Bạn giải thích vì sao textContent hoặc createElement thường an toàn hơn khi hiển thị dữ liệu không tin cậy như thế nào?
Bạn phân tích rủi ro DOM-based XSS qua location, URL fragment, postMessage hoặc dữ liệu lưu trong browser storage như thế nào?
Bạn đánh giá giới hạn của việc chỉ dựa vào input validation để phòng chống XSS như thế nào?
Bạn mô tả cách Content Security Policy giảm khả năng thực thi script ngoài ý muốn trong trình duyệt như thế nào?
Bạn phân biệt CSP report-only với enforce mode và thiết kế lộ trình triển khai policy mới như thế nào?
Bạn thiết kế CSP dùng nonce hoặc hash để cho phép script hợp lệ mà không cần unsafe-inline, đồng thời xử lý cache response như thế nào?
Bạn giải thích tác dụng và rủi ro của unsafe-inline, unsafe-eval và strict-dynamic trong CSP như thế nào?
Bạn thiết kế directive script-src, object-src, base-uri, frame-ancestors và connect-src theo các tài nguyên thực tế của ứng dụng như thế nào?
Bạn lựa chọn nonce ngẫu nhiên theo từng response và bảo đảm nonce không bị tái sử dụng hoặc lộ qua cache như thế nào?
Bạn xử lý CSP khi ứng dụng dùng inline script, third-party analytics, CDN hoặc script loader như thế nào?
Bạn phân tích CSP violation report để phân biệt policy quá chặt với hành vi tải script không hợp lệ như thế nào?
Bạn giải thích Trusted Types giúp kiểm soát dữ liệu đi vào DOM XSS sinks như innerHTML như thế nào?
Bạn triển khai require-trusted-types-for 'script' và trusted-types policy để giới hạn nơi tạo TrustedHTML hoặc TrustedScript như thế nào?
Bạn phân biệt Trusted Types với HTML sanitization và giải thích vì sao Trusted Types không tự làm sạch dữ liệu như thế nào?
Bạn thiết kế migration sang Trusted Types trong ứng dụng có nhiều thư viện frontend cũ như thế nào?
Bạn xác định các trình duyệt và phiên bản cần kiểm thử trước khi dựa vào Trusted Types làm lớp bảo vệ như thế nào?
Bạn giải thích CSRF xảy ra khi trình duyệt tự động gửi thông tin xác thực của người dùng tới một site khác như thế nào?
Bạn phân biệt CSRF với XSS về điều kiện khai thác, mục tiêu và cơ chế phòng vệ như thế nào?
Bạn xác định những request thay đổi trạng thái nào cần CSRF protection và vì sao GET không nên thực hiện thao tác thay đổi dữ liệu như thế nào?
Bạn thiết kế synchronizer token pattern để ràng buộc request thay đổi trạng thái với phiên người dùng như thế nào?
Bạn giải thích double-submit cookie pattern và những điều kiện cần có để tránh việc attacker tự đặt hoặc ghi đè token như thế nào?
Bạn kết hợp SameSite cookie, CSRF token và kiểm tra Origin hoặc Referer theo mô hình threat nào như thế nào?
Bạn đánh giá giới hạn của việc chỉ dựa vào SameSite để phòng CSRF khi ứng dụng hỗ trợ trình duyệt cũ hoặc luồng cross-site hợp lệ như thế nào?
Bạn sử dụng Fetch Metadata headers như Sec-Fetch-Site, Sec-Fetch-Mode và Sec-Fetch-Dest để bổ sung kiểm soát CSRF như thế nào?
Bạn xử lý request API từ mobile client hoặc service-to-service không có browser cookie khi bật CSRF protection như thế nào?
Bạn xác định vì sao CORS không tự động ngăn CSRF và những request cross-origin nào vẫn có thể được gửi như thế nào?
Bạn kiểm thử CSRF trong các luồng form POST, fetch có credentials và điều hướng cross-site bằng cách nào?
Bạn giải thích clickjacking bằng cách attacker nhúng trang mục tiêu trong iframe và lừa người dùng thao tác như thế nào?
Bạn so sánh phạm vi bảo vệ của X-Frame-Options với CSP frame-ancestors và giải thích vì sao frame-ancestors phải được gửi qua HTTP header như thế nào?
Bạn thiết kế frame-ancestors cho ứng dụng cần được nhúng bởi một số đối tác được tin cậy mà vẫn ngăn clickjacking từ origin khác như thế nào?
Bạn đánh giá rủi ro UI redressing đối với các thao tác nhạy cảm như chuyển tiền, đổi email hoặc cấp quyền như thế nào?
Bạn xác định khi nào sandbox attribute của iframe giúp giới hạn nội dung nhúng và những quyền nào cần cấp lại có kiểm soát như thế nào?
Bạn thiết kế giao tiếp postMessage giữa parent window và iframe để xác minh origin, source và schema của message như thế nào?
Bạn phân tích rủi ro khi dùng targetOrigin là wildcard hoặc chấp nhận message mà không kiểm tra event.origin như thế nào?
Bạn phân biệt X-Content-Type-Options nosniff, Referrer-Policy, Permissions-Policy và Strict-Transport-Security theo mục đích bảo vệ như thế nào?
Bạn thiết lập HSTS và lựa chọn includeSubDomains hoặc preload dựa trên khả năng HTTPS của toàn bộ domain như thế nào?
Bạn cấu hình Referrer-Policy để giảm rò rỉ URL hoặc query parameter nhạy cảm khi người dùng điều hướng sang site khác như thế nào?
Bạn lựa chọn Permissions-Policy để giới hạn camera, microphone, geolocation và các browser feature theo nhu cầu ứng dụng như thế nào?
Bạn xác định những security headers nào cần đặt ở application, reverse proxy hoặc CDN để tránh cấu hình xung đột như thế nào?
Bạn kiểm tra header thực tế sau redirect, cache và reverse proxy để xác minh policy bảo mật được áp dụng nhất quán như thế nào?
Bạn phân biệt header bảo mật có hiệu lực ở browser với header chỉ mang tính gợi ý hoặc không được browser thực thi như thế nào?
Bạn sử dụng Subresource Integrity (SRI) để xác minh script hoặc stylesheet từ CDN, và khi nào cần thuộc tính crossorigin cùng CORS trên tài nguyên như thế nào?
Bạn xây dựng quy trình kiểm thử browser security bằng DevTools, automated browser tests và security scanner như thế nào?
Bạn thiết kế bộ test chứng minh SOP, CORS, cookie attributes, CSP, Trusted Types và frame protection hoạt động đúng trong trình duyệt mục tiêu như thế nào?
Bạn điều tra tình huống API hoạt động với curl nhưng frontend báo CORS error bằng cách lần theo request, preflight và response headers như thế nào?
Bạn xử lý sự cố người dùng bị logout ngẫu nhiên sau khi bật SameSite hoặc thay đổi domain cookie bằng cách kiểm tra luồng browser nào như thế nào?
Bạn điều tra XSS chỉ xuất hiện trên một route hoặc một trình duyệt bằng cách truy vết nguồn dữ liệu, DOM sink, CSP report và phiên bản frontend như thế nào?
Bạn xây dựng quy trình triển khai security headers theo report-only, đo vi phạm, sửa tương thích và chuyển sang enforce như thế nào?
Bạn xác định tiêu chí nghiệm thu end-to-end để chứng minh ứng dụng bảo vệ đúng origin boundary, cookie, XSS, CSRF và clickjacking mà không phá vỡ chức năng hợp lệ như thế nào?
