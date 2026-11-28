# Cross-site scripting detection

**Cross-site scripting (XSS)** là nhóm lỗ hổng trong đó dữ liệu không đáng tin cậy được đưa vào trang web theo cách khiến trình duyệt diễn giải dữ liệu đó thành mã hoặc nội dung có khả năng thực thi ngoài ý định của ứng dụng. Kẻ tấn công có thể lợi dụng XSS để thao tác giao diện, thực hiện hành động trong ngữ cảnh người dùng hoặc tiếp cận thông tin mà JavaScript trên trang có quyền sử dụng.

**Cross-site scripting detection** là quá trình phát hiện những dấu hiệu cho thấy dữ liệu đi vào hoặc xuất hiện trong ứng dụng web có khả năng gây XSS. Với **Web Application Firewall (WAF)**, việc phát hiện thường bắt đầu từ kiểm tra yêu cầu HTTP, nhận diện các mẫu đáng ngờ và đối chiếu chúng với quy tắc bảo vệ. Một số giải pháp còn có khả năng kiểm tra phản hồi, liên kết dữ liệu với log ứng dụng hoặc kết hợp phân tích hành vi.

Trong module **SECURITY_NETWORK_SECURITY**, nhận diện XSS bằng WAF là một thành phần của kiến trúc mạng an toàn cùng với phân đoạn, firewall, VPN, IDS/IPS, xác thực kết nối, DNS, mạng không dây và hạ tầng đám mây. WAF giúp hạn chế một số yêu cầu nguy hiểm đến ứng dụng, nhưng **không thay thế xử lý đầu ra an toàn trong mã nguồn, xác thực, phân quyền hay kiểm soát phía trình duyệt**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích bản chất XSS thông qua luồng dữ liệu từ nguồn không tin cậy đến ngữ cảnh thực thi trong trình duyệt.
2. Phân biệt **reflected XSS**, **stored XSS** và **DOM-based XSS** theo nguồn và nơi xử lý dữ liệu.
3. Mô tả vai trò của WAF khi kiểm tra HTTP request và các trường hợp có thể kiểm tra HTTP response.
4. Nhận diện các loại tín hiệu phát hiện XSS và giải thích vì sao một chuỗi đáng ngờ chưa chắc là lỗ hổng có thể khai thác.
5. Thiết kế chính sách phát hiện, ghi log, điều chỉnh cảnh báo và triển khai chặn có kiểm soát.
6. Xây dựng bộ kiểm thử gồm trường hợp tấn công mô phỏng, dữ liệu hợp lệ dễ bị báo động giả và trường hợp WAF khó quan sát.
7. Kết hợp WAF với **context-aware output encoding**, sanitization, Content Security Policy (CSP) và những API DOM an toàn.

## 2. Hiểu XSS từ đường đi của dữ liệu

XSS không đơn giản là “trong request có từ script”. Rủi ro xuất hiện khi một giá trị không đáng tin cậy đi từ **nguồn dữ liệu** (*source*) đến vị trí được trình duyệt diễn giải (*sink*) trong **ngữ cảnh không được xử lý an toàn**.

Ví dụ về nguồn dữ liệu:

- Tham số query của URL, trường biểu mẫu và JSON request body.
- Nội dung bình luận, mô tả sản phẩm, tên hiển thị hoặc dữ liệu đã lưu trong database.
- Dữ liệu từ API đối tác, hệ thống quản trị nội dung hay kho nội dung bên ngoài.
- Fragment của URL, dữ liệu local storage hoặc thông điệp được JavaScript trên trang nhận về.

Ví dụ về nơi dữ liệu có thể được sử dụng:

- Chèn vào nội dung HTML.
- Đặt trong giá trị thuộc tính HTML.
- Ghép vào mã JavaScript hoặc biểu thức thực thi.
- Tạo URL cho liên kết hoặc tài nguyên.
- Chèn vào DOM bằng những API xử lý chuỗi như HTML.

Một dữ liệu giống HTML có thể hoàn toàn vô hại nếu được hiển thị như **văn bản**, nhưng nguy hiểm nếu bị đưa vào trình phân tích HTML và tạo thành phần tử hoặc thuộc tính có khả năng thực thi.

~~~mermaid
flowchart LR
    U["Dữ liệu từ người dùng / nguồn ngoài"] --> R["HTTP request / dữ liệu lưu trữ"]
    R --> B["Ứng dụng xử lý và tạo nội dung"]
    B --> C{"Đưa dữ liệu vào ngữ cảnh nào?"}
    C -->|"Văn bản được encode an toàn"| S["Trình duyệt hiển thị dữ liệu"]
    C -->|"HTML / JavaScript / URL không an toàn"| X["Nguy cơ XSS khi trình duyệt diễn giải"]
    W["WAF quan sát các luồng HTTP đi qua nó"] -.-> R
    W -. "Không thấy mọi nguồn và sink phía client" .-> C
~~~

Điểm cần phân biệt:

- **Dấu hiệu trong input**: ví dụ có ký tự đánh dấu HTML hoặc chuỗi giống script.
- **Cách ứng dụng xử lý**: giá trị được lưu nguyên, kiểm tra, encode, sanitize hay ghép vào template?
- **Kết quả trên trình duyệt**: giá trị được hiển thị dưới dạng văn bản hay được trình duyệt phân tích thành phần tử/mã thực thi?

Chỉ khi hiểu đủ chuỗi này mới có thể đánh giá khả năng khai thác. WAF thường chỉ nhìn thấy **một phần** của đường đi.

## 3. Các dạng XSS quan trọng khi thiết kế phát hiện

### 3.1. Reflected XSS

**Reflected XSS** xảy ra khi ứng dụng đưa dữ liệu từ yêu cầu hiện tại vào phản hồi và trình duyệt diễn giải dữ liệu đó trong ngữ cảnh không an toàn.

Ví dụ, trang tìm kiếm nhận query từ người dùng rồi chèn trực tiếp query vào HTML của thông báo “Kết quả cho ...”. Nếu ứng dụng không thực hiện xử lý phù hợp với ngữ cảnh, dữ liệu có cấu trúc HTML/JavaScript có thể trở thành nội dung thực thi.

**Khả năng quan sát của WAF:** một WAF đặt trước ứng dụng có thể nhìn thấy tham số request, nhận diện dấu hiệu đáng ngờ và áp dụng quy tắc. Tuy vậy, chỉ nhìn request không chứng minh ứng dụng phản chiếu dữ liệu ở vị trí dễ khai thác. Nếu phản hồi có thể được kiểm tra, việc hiểu ngữ cảnh thực tế vẫn là bài toán phức tạp.

### 3.2. Stored XSS

**Stored XSS** xảy ra khi dữ liệu độc hại được lưu lại, chẳng hạn trong bình luận, hồ sơ người dùng hoặc dữ liệu của hệ thống quản trị nội dung, rồi được hiển thị cho một hay nhiều người dùng sau đó.

Ví dụ, trường bình luận chấp nhận nội dung HTML không được xử lý phù hợp. Khi trang quản trị tải danh sách bình luận, trình duyệt có thể diễn giải nội dung không tin cậy như mã thực thi.

**Khả năng quan sát của WAF:** WAF có thể thấy request lúc dữ liệu được gửi tới ứng dụng **nếu request đi qua WAF và được WAF kiểm tra đúng phần dữ liệu**. Nhưng nó có thể không thấy thao tác nhập dữ liệu từ luồng khác, hoặc dữ liệu đã tồn tại từ trước. Thêm nữa, request lưu dữ liệu và response hiển thị dữ liệu có thể cách nhau nhiều ngày, do những người dùng khác nhau thực hiện.

### 3.3. DOM-based XSS

**DOM-based XSS** phát sinh từ cách mã JavaScript trên trình duyệt đọc dữ liệu và đưa dữ liệu đó vào DOM hoặc ngữ cảnh thực thi không an toàn. Thao tác nguy hiểm có thể diễn ra hoàn toàn ở phía client, không cần server phản chiếu nội dung gây lỗi.

Ví dụ, mã client đọc một giá trị từ fragment URL rồi đưa trực tiếp vào một HTML sink. Phần fragment bắt đầu bằng dấu **#** trong URL thông thường **không được trình duyệt gửi trong HTTP request tới server**. Vì vậy, WAF tại biên có thể không nhìn thấy dữ liệu gây ra thao tác DOM này.

**Điểm giới hạn:** WAF không thể bảo đảm phát hiện mọi DOM-based XSS bằng cách kiểm tra request/response. Cần kiểm tra mã JavaScript, sử dụng API DOM an toàn, áp dụng chính sách CSP/Trusted Types phù hợp và kiểm thử hành vi trong trình duyệt.

### 3.4. So sánh ba dạng

| Dạng | Nơi dữ liệu đi vào | Thời điểm có thể gây hại | WAF dễ quan sát gì? | Khoảng trống thường gặp |
| --- | --- | --- | --- | --- |
| Reflected | Request tới ứng dụng | Khi phản hồi của request được trình duyệt xử lý | Query, body, cookie hoặc một phần response | Không hiểu đầy đủ ngữ cảnh render của ứng dụng |
| Stored | Request trước đó, API khác hoặc nguồn dữ liệu lưu trữ | Khi dữ liệu lưu được hiển thị về sau | Request tạo/sửa dữ liệu nếu đi qua điểm lọc | Dữ liệu từ luồng ngoài WAF, nội dung đã lưu sẵn, ngữ cảnh hiển thị |
| DOM-based | URL fragment, trạng thái client, dữ liệu do JavaScript xử lý | Khi script client cập nhật DOM | Một phần request/response và tài nguyên tải qua WAF | Nguồn/sink chỉ tồn tại trong browser, không qua HTTP tới server |

Ba nhóm này mô tả đường dữ liệu; chúng không nhất thiết loại trừ nhau trong mọi tình huống triển khai.

## 4. WAF đứng ở đâu trong kiến trúc?

WAF thường được triển khai tại **reverse proxy**, CDN edge, API gateway hoặc một điểm trung gian có khả năng hiểu HTTP. Để kiểm tra nội dung HTTP được bảo vệ bởi TLS, giải pháp phải nhìn thấy dữ liệu sau khi TLS đã được kết thúc hoặc được cung cấp nội dung đã giải mã bởi thành phần được tích hợp.

~~~mermaid
flowchart LR
    B["Browser / API client"] -->|"HTTPS"| E["Edge / CDN có WAF"]
    E -->|"Request được kiểm tra"| P["Application gateway"]
    P --> A["Web app / API"]
    A --> D[("Database / nội dung lưu")]
    A -->|"HTTP response"| P
    P --> E
    E -->|"Response tới browser"| B
    E -.-> L["WAF / security logs"]
    A -.-> AL["Application / error logs"]
    B -.-> CR["CSP violation reports nếu cấu hình"]
~~~

Các điểm cần xác minh trong sơ đồ triển khai:

1. **Phạm vi hostname và đường vào:** mọi public endpoint dự kiến có thật sự đi qua WAF không? Có đường tới origin, API phụ, host quản trị hoặc môi trường thử nghiệm không qua điểm kiểm tra không?
2. **TLS và định dạng HTTP:** WAF có khả năng phân tích nội dung của các luồng được hỗ trợ không, bao gồm HTTP/1.1, HTTP/2 hoặc HTTP/3 theo thiết kế nền tảng?
3. **Request body và content type:** phần JSON, form, multipart, URL-encoded và các giới hạn kích thước có được phân tích chính xác không?
4. **Response inspection:** sản phẩm có hỗ trợ kiểm tra phản hồi hay chỉ kiểm tra request? Có khả năng quan sát phản hồi sau cache/CDN không?
5. **Log và dữ liệu nhạy cảm:** thông tin nào được ghi để phân tích sự kiện và thông tin nào phải che hoặc loại bỏ?

Không nên mặc định mọi WAF đều đọc response, hỗ trợ phân tích JavaScript hoặc có cùng thuật toán phát hiện.

## 5. Các dấu hiệu XSS mà WAF có thể kiểm tra

Những cơ chế phổ biến bao gồm **signature matching**, phân tích cú pháp, quy tắc theo nội dung/ngữ cảnh, phát hiện bất thường và đánh giá điểm rủi ro (*anomaly scoring*).

| Loại tín hiệu | Ví dụ ý nghĩa | Hạn chế |
| --- | --- | --- |
| Cấu trúc thẻ HTML đáng ngờ | Dữ liệu chứa thẻ hoặc thuộc tính có thể ảnh hưởng trình duyệt | Ứng dụng chỉnh sửa HTML hoặc tài liệu lập trình có thể cần chứa chuỗi tương tự |
| Mẫu liên quan JavaScript | Dữ liệu có dấu hiệu mã thực thi hoặc cú pháp thao tác DOM | Không đủ chứng minh mã sẽ được thực thi trong response |
| Giá trị thuộc tính và URL nguy hiểm theo ngữ cảnh | Dấu hiệu yêu cầu ứng dụng diễn giải dữ liệu theo cách không an toàn | Phải biết dữ liệu được chèn vào ngữ cảnh nào |
| Biến đổi và mã hóa của dữ liệu | Ký tự đặc biệt xuất hiện dưới dạng đã encode hoặc qua dạng biểu diễn khác | Dễ sai khi cách decode của WAF khác cách ứng dụng xử lý |
| Lặp lại yêu cầu đáng ngờ | Một nguồn gửi nhiều yêu cầu có kiểu dữ liệu tương tự | Không tự chứng minh có khai thác; có thể là kiểm thử được ủy quyền |
| Bất thường so với schema | Trường chỉ cần số hoặc mã định danh nhưng chứa cấu trúc HTML | Cần schema chính xác và hiểu nghiệp vụ để tránh chặn dữ liệu hợp lệ |

Ví dụ, trường **quantity** trong API đặt hàng chỉ được phép là số nguyên dương. Việc nhận một chuỗi chứa cấu trúc HTML tại trường này là bất thường và có thể bị từ chối **do sai kiểu dữ liệu** mà không cần kết luận request chứa XSS khai thác được.

Ngược lại, trường **articleBody** của trình soạn thảo tài liệu có thể chủ động chứa mã HTML để hiển thị như đoạn code. Chặn tất cả ký tự **<** và **>** ở mọi trường sẽ gây báo động giả và phá chức năng hợp lệ.

### 5.1. Tín hiệu không đồng nghĩa với khai thác thành công

Một WAF phát hiện chuỗi giống script trong input chỉ có thể đưa ra nhận định như **“request có dấu hiệu XSS”**. Để xác định lỗ hổng thực sự, phải xem ứng dụng phản chiếu hoặc lưu dữ liệu thế nào, dữ liệu được render trong ngữ cảnh nào và trình duyệt có thực sự diễn giải thành mã có khả năng thực thi hay không.

Nếu ứng dụng dùng output encoding đúng ngữ cảnh, một chuỗi rất giống XSS vẫn có thể hiển thị hoàn toàn an toàn. WAF có thể cảnh báo request đó, nhưng **cảnh báo không phải bằng chứng người dùng đã bị tấn công thành công**.

## 6. Chuẩn hóa dữ liệu trước khi so khớp

HTTP có nhiều dạng biểu diễn dữ liệu: query string, form URL encoding, JSON, multipart, Unicode và những phép biến đổi do framework hoặc proxy thực hiện. Bộ lọc chỉ kiểm tra chuỗi thô có thể bỏ sót những ký tự mà ứng dụng sẽ diễn giải sau đó.

Một pipeline phát hiện có thể gồm:

1. Xác định đường dẫn, phương thức HTTP, content type và giới hạn dữ liệu cần kiểm tra.
2. Phân tích request theo cú pháp thực tế, nhận diện các trường và giá trị thay vì coi toàn bộ body như văn bản không cấu trúc.
3. Chuẩn hóa những cách mã hóa **theo hành vi được hỗ trợ và có thể dự đoán của ứng dụng**.
4. Áp dụng quy tắc phát hiện cho từng trường hoặc ngữ cảnh thích hợp.
5. Ghi nhận loại tín hiệu, rule ID và quyết định cuối cùng để phục vụ điều tra.

**Ví dụ minh họa về cách biểu diễn dữ liệu:**

~~~text
Chuỗi chứa ký tự HTML:     <script>
Biểu diễn URL-encoded:     %3Cscript%3E
~~~

Đây là **hai cách biểu diễn chuỗi**, không phải kết luận có XSS. Nếu WAF và ứng dụng giải mã theo cách khác nhau, đánh giá có thể thiếu chính xác. Chuẩn hóa quá nhiều lần hoặc áp dụng phép biến đổi không đúng ngữ cảnh cũng có thể tạo kết quả sai. Cần hiểu parser của ứng dụng và chính sách của nhà cung cấp WAF để đánh giá, không tùy tiện thêm các phép giải mã.

### 6.1. Những điều dễ bị bỏ qua

- **Giới hạn kích thước body:** phần request vượt ngưỡng kiểm tra của WAF có thể không được phân tích đầy đủ; phải xác định hành vi khi vượt giới hạn.
- **Content type không phổ biến:** parser có thể không đọc đúng JSON lồng nhau, multipart, nội dung nhị phân hoặc format riêng.
- **Nhiều giá trị cùng tên:** framework có thể diễn giải duplicate parameters khác với proxy hoặc WAF.
- **Chuyển đổi dữ liệu ở backend:** ứng dụng có thể decode hoặc biến đổi dữ liệu sau khi WAF đã hoàn tất kiểm tra.
- **Dữ liệu từ nơi khác:** thông điệp qua queue, DB, công cụ quản trị hoặc endpoint không qua WAF có thể trở thành nguồn cho stored XSS.

Không thể giải quyết mọi khác biệt parser chỉ bằng cách bật một rule chữ ký.

## 7. Phát hiện và phòng ngừa phải dựa trên ngữ cảnh xuất dữ liệu

XSS phụ thuộc vào **ngữ cảnh** mà dữ liệu được dùng. Các biện pháp xử lý cần khác nhau:

| Ngữ cảnh xuất | Ví dụ sử dụng | Biện pháp chính |
| --- | --- | --- |
| Nội dung văn bản trong HTML | Hiển thị tên khách hàng hoặc câu tìm kiếm | HTML text encoding hoặc template engine tự escape đúng ngữ cảnh |
| Giá trị thuộc tính HTML | Đưa dữ liệu vào thuộc tính an toàn | Attribute encoding, đặt giá trị qua API an toàn và kiểm soát tên thuộc tính |
| JavaScript | Dữ liệu được nhúng trong đoạn script | Tránh ghép chuỗi vào mã; truyền dữ liệu qua định dạng/cơ chế phù hợp |
| URL | Tạo liên kết hoặc điểm điều hướng | Kiểm tra scheme, đích và xây dựng URL qua API phù hợp |
| HTML có chủ đích | Nội dung rich text do người dùng biên soạn | Sanitization bằng thư viện được duy trì, policy allowlist theo ngữ cảnh |
| DOM ở trình duyệt | Cập nhật một phần giao diện | Ưu tiên textContent, createTextNode hoặc API tạo node an toàn; hạn chế HTML sinks |

### 7.1. Ví dụ xử lý DOM an toàn

Đoạn minh họa dưới đây đưa dữ liệu của người dùng vào **nội dung văn bản**, không diễn giải dữ liệu thành HTML:

~~~javascript
const titleNode = document.getElementById("search-term");
const query = new URLSearchParams(window.location.search).get("q") ?? "";

// Hiển thị nguyên văn giá trị, kể cả khi có ký tự < hoặc >.
titleNode.textContent = query;
~~~

Nếu thay bằng cơ chế chèn trực tiếp HTML chưa được kiểm soát, cùng một dữ liệu có thể bị trình duyệt phân tích thành node hoặc mã thực thi. Giải pháp ứng dụng là **chọn sink an toàn**, encode đúng ngữ cảnh và chỉ cho phép HTML có chủ đích qua cơ chế sanitization đã được kiểm thử.

### 7.2. Vì sao WAF không thay thế sửa ứng dụng?

WAF không có đủ thông tin về mọi vị trí render hoặc quyền của từng người dùng. Một rule có thể chặn vài mẫu đáng ngờ nhưng không bảo đảm bảo vệ các đường xử lý khác, nội dung có sẵn trong database hoặc JavaScript client. **Cách khắc phục gốc** là bảo vệ nơi dữ liệu đi vào ngữ cảnh thực thi, kết hợp xác thực/phân quyền và kiểm thử bảo mật ứng dụng.

## 8. Content Security Policy và Trusted Types

### 8.1. Content Security Policy (CSP)

**CSP** là cơ chế trình duyệt thực thi chính sách về nguồn và kiểu nội dung được phép tải hoặc thực thi. Một CSP có thể giảm khả năng thực thi một số đoạn script không được phép và tạo báo cáo vi phạm.

Ví dụ minh họa của một policy tương đối chặt cho ứng dụng được thiết kế để dùng file script từ cùng origin:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'
~~~

**Không sao chép policy này trực tiếp lên mọi ứng dụng.** Những ứng dụng dùng nguồn script khác, inline script hoặc chức năng đặc thù có thể bị ảnh hưởng. Cần thiết kế theo ứng dụng, kiểm thử và ưu tiên chiến lược nonce/hash cho script khi thích hợp. CSP không phải phương án duy nhất ngăn XSS và một policy cấu hình lỏng có thể tạo cảm giác an toàn giả.

**Content-Security-Policy-Report-Only** cho phép quan sát những vi phạm chính sách đề xuất mà chưa thực thi chặn, thuận tiện khi chuẩn bị triển khai. Không nên coi mọi báo cáo CSP là bằng chứng có tấn công: một extension trình duyệt, script hợp lệ bị thiếu allowlist hoặc cấu hình ứng dụng sai cũng có thể gây cảnh báo.

### 8.2. Trusted Types

**Trusted Types**, trên những trình duyệt và môi trường có hỗ trợ, giúp hạn chế việc truyền chuỗi không an toàn tới một số DOM sink có nguy cơ chèn HTML hoặc script. Ứng dụng có thể áp dụng policy tạo giá trị được tin cậy từ quá trình xử lý thích hợp, và phối hợp CSP để yêu cầu tuân thủ.

Trusted Types **không tự làm sạch mọi dữ liệu**, không phải cơ chế thay thế cho sanitization và không có hỗ trợ giống nhau trên tất cả trình duyệt. Nó có giá trị đặc biệt đối với việc kiểm soát DOM-based XSS ở phía ứng dụng.

### 8.3. Cookie và các kiểm soát bổ sung

Thuộc tính **HttpOnly** giúp JavaScript không đọc trực tiếp cookie tương ứng, nhưng **không ngăn mọi hậu quả của XSS**: JavaScript chạy trong origin hợp lệ vẫn có thể thực hiện yêu cầu trong ngữ cảnh phiên người dùng. Secure và SameSite có những vai trò khác nhau trong bảo vệ cookie, không phải cách sửa XSS.

## 9. Thiết kế chính sách WAF phát hiện XSS

Một chính sách triển khai nên chỉ rõ **tài sản được bảo vệ, vị trí quan sát, loại dữ liệu được kiểm tra, chiến lược chấm điểm, hành động và quy trình điều chỉnh**.

### 9.1. Các chế độ vận hành

| Chế độ | Cách xử lý | Khi nào hữu ích |
| --- | --- | --- |
| Monitor / log-only | Ghi nhận các dấu hiệu nghi ngờ nhưng chưa chủ động chặn | Triển khai ban đầu, đánh giá false positives |
| Block | Từ chối request phù hợp chính sách chặn | Khi rule đã được xác minh và có ngưỡng rủi ro đủ rõ |
| Challenge hoặc rate limit | Áp dụng bước kiểm tra/giới hạn nếu nền tảng hỗ trợ | Phù hợp một số trường hợp tự động hóa hoặc lưu lượng lặp lại; không thay thế phát hiện XSS |
| Exception có phạm vi | Giảm hoặc bỏ qua một kiểm tra cụ thể tại trường/route được xác minh | Khi có dữ liệu hợp lệ gây báo động giả, có người duyệt và thời hạn |

Một rule có thể dùng cơ chế **anomaly scoring**: các dấu hiệu khác nhau đóng góp điểm, request bị chặn khi vượt ngưỡng. Đây là mô hình thường gặp, không phải yêu cầu bắt buộc cho mọi WAF.

### 9.2. Ví dụ mô tả policy trung lập với nhà cung cấp

~~~yaml
wafPolicy:
  name: customer-web-xss-protection
  protectedRoutes:
    - /search
    - /comments
    - /profile
  inspection:
    direction: request
    parseByContentType: true
    checkQueryParameters: true
    checkFormFields: true
    checkJsonBody: true
    checkRelevantHeaders: true
    checkBodyLimits: true
  detection:
    methods:
      - signature-rules
      - context-aware-validation-where-supported
      - anomaly-scoring
    categories:
      - suspicious-html-or-script-constructs
      - unexpected-input-format
  enforcement:
    initialMode: monitor
    blockingRequiresValidatedRules: true
  logging:
    recordRuleId: true
    recordRouteAndField: true
    redactSensitiveValues: true
  exceptions:
    requireReason: true
    requireOwner: true
    requireReviewDate: true
~~~

**Đây là YAML mô hình hóa**, không phải cấu hình dùng trực tiếp với một WAF cụ thể. Tên trường như **context-aware-validation-where-supported** là mô tả năng lực mong muốn, không hàm ý mọi WAF đều có thể xác định ngữ cảnh render. Khi triển khai, phải đối chiếu cú pháp, parser, thứ tự xử lý, logging và giới hạn sản phẩm thật.

### 9.3. Lưu ý về baseline và quy tắc sẵn có

Một số WAF hỗ trợ bộ quy tắc cộng đồng hoặc managed rules để phát hiện các nhóm tấn công web như XSS. Có thể dùng chúng làm **baseline**, sau đó đánh giá trên request thực tế của ứng dụng. Cần theo dõi phiên bản, mức nhạy, những thay đổi quy tắc và ảnh hưởng khi cập nhật. **Không mặc định bật chế độ chặn toàn bộ rule ngay trên production** khi chưa xem false positives.

## 10. Ví dụ phân tích request trong môi trường học tập

Giả sử ứng dụng demo có endpoint cho phép gửi bình luận. Đây là dữ liệu **giả lập**; đoạn minh họa chỉ nhằm giúp nhận diện tín hiệu của WAF trên một hệ thống được phép kiểm thử.

~~~http
POST /comments HTTP/1.1
Host: demo.example.test
Content-Type: application/json

{"articleId":42,"body":"<script>console.log('xss-lab')</script>"}
~~~

WAF có thể nhận diện cấu trúc script trong trường **body** và tạo cảnh báo loại XSS. Tuy nhiên, còn ít nhất ba trường hợp khác nhau:

1. Ứng dụng hiển thị bình luận bằng textContent hoặc HTML escaping phù hợp: chuỗi chỉ hiện ra như văn bản, không thực thi.
2. Ứng dụng đưa dữ liệu vào HTML sink không an toàn: người dùng mở trang bình luận có thể gặp stored XSS.
3. Endpoint có chức năng lưu **mã mẫu** hoặc bài giảng lập trình: nội dung có thể hoàn toàn hợp lệ theo nhu cầu nghiệp vụ và WAF chặn sẽ là báo động giả.

Để kết luận lỗ hổng, nhóm kiểm thử phải xác minh cách render trong **môi trường được ủy quyền**; không thể chỉ dựa trên chuỗi request.

### 10.1. Cùng dữ liệu, hai cách hiển thị

~~~html
<!-- Minh họa cách hiển thị văn bản đã được encode -->
<p class="comment">&lt;script&gt;console.log('xss-lab')&lt;/script&gt;</p>
~~~

Trong ví dụ này, ký tự đặc biệt được encode khi đưa vào HTML, nên người dùng thấy **đoạn chữ** thay vì một thẻ script. Đây là một trong các lý do phản hồi của ứng dụng quan trọng hơn việc chỉ đếm số mẫu XSS mà WAF chặn.

## 11. False positive và false negative

**False positive** là trường hợp WAF cảnh báo hoặc chặn một request hợp lệ. **False negative** là trường hợp hành vi nguy hiểm không được nhận diện hoặc lọt qua chính sách.

| Trường hợp | Loại sai lệch có thể gặp | Nguyên nhân hoặc bối cảnh |
| --- | --- | --- |
| Người dùng gửi bài hướng dẫn chứa đoạn mã HTML | False positive | Dữ liệu là tài liệu cần hiển thị nguyên văn |
| Người biên tập gửi rich text đã được sanitization đúng | False positive | Bộ lọc chỉ nhìn thấy cấu trúc HTML, không hiểu policy render |
| Dữ liệu độc hại được nhập từ queue hoặc DB bên ngoài WAF | False negative | Không có request gây lỗi đi qua điểm kiểm tra |
| DOM script dùng fragment URL không gửi tới server | False negative | WAF biên không nhìn thấy giá trị fragment |
| Parser của WAF không hiểu content type hoặc body quá giới hạn | False negative | Phần dữ liệu chứa tín hiệu không được kiểm tra đủ |
| WAF và ứng dụng diễn giải dữ liệu khác nhau | False negative hoặc false positive | Sai lệch parse/chuẩn hóa |
| Rule quá nhạy trên endpoint cho phép nhập HTML | False positive | Chưa thiết kế ngoại lệ có phạm vi hoặc kiểm soát đầu ra |

### 11.1. Cách giảm false positive

- Gắn rule theo **route, phương thức và trường dữ liệu**, thay vì chặn mọi ký tự đặc biệt trên toàn website.
- Tận dụng schema: trường số nguyên, email hoặc mã định danh nên được kiểm tra đúng kiểu và giới hạn.
- Phân biệt endpoint nhận **rich text** với endpoint chỉ nhận giá trị đơn giản.
- Dùng giai đoạn **monitor** để thu thập tín hiệu, phân nhóm quy tắc gây ảnh hưởng và xác định owner.
- Tạo ngoại lệ **đủ hẹp**, có lý do, thời hạn và kế hoạch rà soát. Không vô hiệu toàn bộ lớp chống XSS chỉ để bỏ một cảnh báo.

### 11.2. Cách giảm false negative

- Bảo đảm các đường vào ứng dụng dự kiến đều đi qua điểm WAF và các content type liên quan được phân tích.
- Kiểm tra giới hạn request body, khả năng parse, cách xử lý khi vượt giới hạn và tính nhất quán với backend.
- Kết hợp log ứng dụng, static analysis, dynamic application testing trong phạm vi được phép và kiểm thử trực tiếp tại browser.
- Dùng CSP và các biện pháp tại ứng dụng để phát hiện/giảm thiểu những trường hợp WAF không quan sát được.
- Rà soát quy tắc khi ứng dụng thêm endpoint, chuyển công nghệ frontend hoặc thay đổi cấu trúc API.

Mục tiêu không phải “tối ưu số request bị chặn càng cao càng tốt”, mà là **phát hiện có ý nghĩa, ít ảnh hưởng nghiệp vụ và giảm rủi ro XSS thực sự**.

## 12. Ghi log và điều tra cảnh báo XSS

WAF cần ghi đủ dữ liệu để người vận hành đối chiếu với ứng dụng mà không làm lộ dữ liệu nhạy cảm. Một log hữu ích có thể bao gồm:

- Thời điểm chuẩn hóa múi giờ và định danh request/correlation ID.
- Host, route, HTTP method, content type và HTTP status nếu được quan sát.
- Rule ID, nhóm dấu hiệu, điểm rủi ro nếu có và hành động monitor/block.
- Tên tham số hoặc vị trí dữ liệu gây cảnh báo, tránh sao chép toàn bộ giá trị bí mật.
- Client IP nhìn thấy qua proxy chain và danh tính liên quan nếu hệ thống xác thực có cung cấp một cách đáng tin cậy.
- Thông tin phiên, tỷ lệ lỗi, log ứng dụng hoặc báo cáo CSP cùng mốc thời gian.

### 12.1. Log minh họa

~~~json
{
  "timestamp": "2026-11-28T10:15:00+07:00",
  "event": "waf_xss_candidate",
  "host": "demo.example.test",
  "method": "POST",
  "path": "/comments",
  "content_type": "application/json",
  "field": "body",
  "rule_category": "suspicious-script-construct",
  "decision": "monitor",
  "request_id": "lab-req-1042",
  "application_outcome": "not-yet-verified",
  "data_classification": "synthetic-training-data"
}
~~~

Đây là **log giả lập**. Giá trị **application_outcome** cho thấy WAF chưa có đủ thông tin để kết luận ứng dụng đã xảy ra XSS. Trong môi trường thật, tránh ghi token, cookie phiên, thông tin cá nhân hoặc toàn bộ nội dung bình luận vào log bảo mật khi không cần thiết; dùng cơ chế giới hạn truy cập và lưu giữ phù hợp.

### 12.2. Triage một cảnh báo

1. **Xác định phạm vi:** request đến hostname/route nào, đã bị chặn hay chỉ ghi nhận, dữ liệu có đi qua ứng dụng không?
2. **Đọc lý do phát hiện:** rule nào khớp, tại tham số nào, dữ liệu có thực sự trái schema không?
3. **Đối chiếu ngữ cảnh:** endpoint có nhiệm vụ nhận tài liệu HTML, code sample hay dữ liệu thuần văn bản?
4. **Liên kết với ứng dụng:** log request, trạng thái xử lý, nơi lưu dữ liệu và nơi render có cung cấp chứng cứ rủi ro không?
5. **Kiểm tra tác động:** có lỗi, thay đổi giao diện, hành động trái kỳ vọng hoặc CSP violation cùng phiên không?
6. **Kết luận phù hợp mức bằng chứng:** candidate attack, false positive, blocked suspicious request, hoặc confirmed application vulnerability sau kiểm thử được phép.
7. **Chọn hành động:** điều chỉnh rule, sửa ứng dụng, tăng theo dõi, tạo ticket và ghi nhận người phụ trách.

Một HTTP 403 từ WAF chứng minh request cụ thể bị từ chối tại điểm đó; **không chứng minh ứng dụng không có XSS** trên các đường khác. Ngược lại, một request được cho qua cũng không chứng minh đã khai thác thành công.

## 13. Kiểm thử phát hiện XSS có kiểm soát

Việc kiểm thử cần diễn ra trong **lab hoặc môi trường được ủy quyền**, với tài khoản và dữ liệu thử nghiệm. Mục tiêu là xác minh cả khả năng nhận diện của WAF lẫn tính an toàn của ứng dụng.

### 13.1. Ma trận test mẫu

| Mã | Tình huống kiểm thử | Kỳ vọng với WAF | Kỳ vọng với ứng dụng |
| --- | --- | --- | --- |
| T-01 | Trường số nhận một chuỗi HTML thay vì số | Cảnh báo hoặc từ chối sai schema | Trả lỗi validation; không lưu như dữ liệu hợp lệ |
| T-02 | Request chứa thẻ script đơn giản trong trường bình luận demo | Tạo tín hiệu XSS theo chính sách thử nghiệm | Hiển thị như văn bản hoặc xử lý an toàn, không thực thi |
| T-03 | Câu bình luận bình thường, không có cấu trúc HTML | Không báo động XSS | Hiển thị đúng |
| T-04 | Bài viết kỹ thuật hợp lệ chứa đoạn mã HTML | Không chặn sau khi điều chỉnh đúng route/trường | Hiển thị thành đoạn code, không thực thi |
| T-05 | Dữ liệu thử nghiệm đã được lưu trước khi bật WAF | Không kỳ vọng request filter thấy nội dung cũ | Khi hiển thị vẫn phải encode/sanitize đúng |
| T-06 | DOM client nhận dữ liệu từ fragment URL trong ứng dụng demo | WAF có thể không quan sát được nguồn này | Client xử lý bằng API DOM an toàn |
| T-07 | API JSON có giá trị mã hóa URL hợp lệ theo schema | Parse theo ngữ cảnh, không báo sai | Decode và validate đúng |
| T-08 | CSP Report-Only báo sự kiện ở môi trường thử nghiệm | WAF và CSP log có thể tương quan | Rà soát nguyên nhân trước khi áp dụng chặn |

Kỳ vọng của WAF **phụ thuộc ruleset và chế độ** đang kiểm thử: không phải mọi sản phẩm đều phát hiện các trường hợp như nhau. Trước khi chạy, ghi rõ rule/version, chế độ monitor/block, nơi kết thúc TLS, đường request và cách thu thập log.

### 13.2. Các bước thực hiện

1. Chuẩn bị ứng dụng demo và dữ liệu giả lập; bảo đảm không dùng cookie hoặc tài khoản khách hàng thật.
2. Ghi lại baseline: request bình thường, phản hồi ứng dụng, mức độ lỗi và log WAF trước kiểm thử.
3. Chạy lần lượt các ca theo ma trận với số lượng nhỏ và thời gian đã duyệt.
4. Ghi nhận request ID, rule ID, quyết định của WAF và kết quả thực tế trong trình duyệt.
5. Đối chiếu: WAF có phát hiện nhưng ứng dụng vẫn an toàn? WAF không thấy nhưng trình duyệt xử lý an toàn? Có ca nào thực sự cho thấy ứng dụng render sai ngữ cảnh?
6. Sửa lỗi tại ứng dụng khi phát hiện rủi ro, điều chỉnh WAF để giảm báo động giả và thử lại.
7. Theo dõi những thay đổi sau deploy và nâng cấp ruleset để tránh hồi quy.

### 13.3. Phân biệt test WAF và test an toàn ứng dụng

**Test WAF** trả lời: dữ liệu đáng ngờ có được phát hiện, ghi log hoặc chặn theo chính sách đã khai báo không?

**Test ứng dụng** trả lời: dữ liệu không tin cậy có bị đưa vào ngữ cảnh thực thi hay không, và các biện pháp ở ứng dụng có chặn được hậu quả không?

Hai câu hỏi liên quan nhưng **không thể thay thế nhau**. Một WAF phát hiện tốt vẫn có thể đứng trước ứng dụng có lỗ hổng; ứng dụng được thiết kế an toàn vẫn có thể nhận những request gây cảnh báo chữ ký.

## 14. Tình huống: hệ thống bình luận và trang quản trị

Giả sử website thương mại điện tử cho khách gửi bình luận. Nội dung được lưu trong database, rồi hiển thị ở trang sản phẩm và trang quản trị duyệt bình luận.

**Giai đoạn 1 – Nhận dữ liệu:** khách gửi bình luận chứa đoạn HTML giống mã script. WAF phát hiện cấu trúc đáng ngờ và ghi log. Nếu WAF ở chế độ monitor, request vẫn có thể tới ứng dụng.

**Giai đoạn 2 – Lưu nội dung:** ứng dụng lưu bình luận. Việc dữ liệu được lưu **không tự chứng minh có lỗ hổng**; yếu tố quyết định nằm ở cách dữ liệu được xử lý lúc hiển thị.

**Giai đoạn 3 – Hiển thị:** nếu trang quản trị đưa bình luận vào một HTML sink không an toàn, stored XSS có thể xảy ra. Nếu ứng dụng dùng textContent hoặc encode đúng ngữ cảnh, nội dung chỉ hiển thị như văn bản.

**Giai đoạn 4 – Khắc phục:** đội phát triển sửa cách render, áp dụng sanitization nếu thật sự hỗ trợ rich text, kiểm thử các ngữ cảnh xuất dữ liệu. Đội WAF dùng log để xem những request tương tự, đánh giá false positives và xác định có cần chặn bổ sung hay không.

**Bài học:** Phát hiện dấu hiệu ở request có thể hữu ích để giám sát, nhưng **xử lý đầu ra trong ứng dụng** là nơi quyết định việc dữ liệu không đáng tin cậy có biến thành mã thực thi hay không.

## 15. Đưa XSS detection vào phòng vệ nhiều lớp

| Lớp bảo vệ | Vai trò đối với XSS | Điều không giải quyết được một mình |
| --- | --- | --- |
| WAF tại edge/API gateway | Phát hiện hoặc chặn một số request đáng ngờ | Không thấy mọi nguồn dữ liệu và sink trong browser |
| Validation tại API | Giới hạn kiểu, độ dài, định dạng và mục đích trường | Không thay thế output encoding đúng ngữ cảnh |
| Output encoding / safe DOM API | Ngăn dữ liệu bị diễn giải thành mã tại vị trí hiển thị | Cần áp dụng nhất quán ở mọi chỗ render |
| Sanitization cho rich text | Giữ một tập HTML an toàn có chủ đích | Phải dùng thư viện/policy được duy trì và kiểm thử |
| CSP / Trusted Types | Giảm khả năng thực thi script ngoài ý định và kiểm soát DOM sink khi hỗ trợ | Không bảo đảm loại bỏ tất cả XSS hoặc lỗi logic |
| IDS/IPS, log, SIEM | Liên kết cảnh báo, nhận biết hành vi bất thường | Không thay thế sửa lỗ hổng ứng dụng |
| Phân đoạn, firewall, VPN, IAM | Giới hạn đường vào và quyền hệ thống nếu có sự cố | Không giải quyết lỗi XSS trong trình duyệt |

Với hệ thống triển khai trên cloud hoặc CDN, cần quản lý **đường đi tới origin**, HTTPS termination, logging, secrets và quyền sửa WAF policy. Một người có quyền sửa rule quá rộng hoặc mở đường vào origin có thể làm giảm hiệu quả bảo vệ, nên hoạt động cấu hình WAF cũng cần xác thực mạnh, phân quyền và kiểm toán.

## 16. Những sai lầm cần tránh

| Nhận định sai | Vì sao sai | Cách tiếp cận phù hợp |
| --- | --- | --- |
| “Request có từ script chắc chắn là XSS” | Cần biết ngữ cảnh render và hành vi trình duyệt | Ghi nhận tín hiệu, xác minh bằng log/app/browser trong phạm vi được phép |
| “Chặn mọi dấu < và > là an toàn” | Dữ liệu hợp lệ như tài liệu code, ký hiệu hoặc rich text bị phá | Validation theo schema và encode/sanitize ở đầu ra |
| “Có WAF thì không cần sửa XSS trong code” | WAF không thấy mọi đường và không xử lý mọi DOM sink | Sửa nguyên nhân ở ứng dụng; WAF là phòng vệ bổ sung |
| “Stored XSS luôn bị WAF thấy khi nhận dữ liệu” | Dữ liệu có thể vào qua queue, import, API phụ hoặc đã tồn tại | Kiểm soát mọi nguồn và mọi điểm hiển thị |
| “WAF có thể chặn toàn bộ DOM XSS” | Fragment URL và thao tác client có thể không qua server | Safe DOM API, review JS, CSP/Trusted Types |
| “Bật toàn bộ rule block lập tức là tốt nhất” | False positives có thể gián đoạn nghiệp vụ | Monitor, kiểm thử, điều chỉnh và triển khai chặn theo rủi ro |
| “WAF 403 có nghĩa ứng dụng không có lỗ hổng” | Chỉ chứng minh request cụ thể đã bị chặn | Kiểm thử an toàn ứng dụng độc lập |
| “Dùng CSP là đủ chống XSS” | CSP có giới hạn và phụ thuộc cấu hình/trình duyệt | Output encoding và sanitization vẫn là cốt lõi |
| “Ghi toàn bộ request body để điều tra cho dễ” | Có thể lộ mật khẩu, token hoặc dữ liệu cá nhân | Ghi metadata, che giá trị nhạy cảm, giới hạn quyền xem |

## 17. Câu hỏi và bài tập tự kiểm tra

### Câu hỏi 1

WAF phát hiện thẻ script trong trường tìm kiếm. Điều gì còn phải xác minh trước khi kết luận ứng dụng có reflected XSS?

**Gợi ý:** kiểm tra ứng dụng có phản chiếu dữ liệu hay không, phản chiếu ở ngữ cảnh nào và có thực hiện encode/giải pháp xử lý an toàn trước khi render hay không.

### Câu hỏi 2

Vì sao stored XSS có thể xuất hiện trên trang quản trị dù WAF không ghi nhận request chứa mẫu XSS trong ngày xảy ra sự cố?

**Gợi ý:** dữ liệu có thể được lưu từ trước, đi qua kênh nhập khác hoặc phát sinh từ hệ thống không qua WAF; trang quản trị hiển thị dữ liệu ở thời điểm muộn hơn.

### Câu hỏi 3

Ứng dụng dùng JavaScript đọc phần fragment URL rồi đưa vào DOM. WAF tại reverse proxy có thể bỏ sót trường hợp này vì sao?

**Gợi ý:** fragment URL thường không được trình duyệt gửi trong HTTP request; xử lý nguy hiểm có thể diễn ra hoàn toàn phía client.

### Câu hỏi 4

Tại sao chặn mọi thẻ HTML ở trường gửi tài liệu lập trình dễ tạo false positive?

**Gợi ý:** mã HTML có thể là nội dung hợp lệ cần hiển thị nguyên văn. Chính sách phải xét chức năng trường, validation và cách ứng dụng render.

### Câu hỏi 5

Khi WAF phát hiện XSS, vì sao không nên ghi toàn bộ cookie và request body vào log?

**Gợi ý:** dữ liệu có thể chứa token phiên, thông tin cá nhân hoặc bí mật; log cần đủ metadata để điều tra nhưng được che và quản lý quyền.

### Câu hỏi 6

CSP và Trusted Types giúp gì cho phòng vệ XSS, và chúng có thay thế được output encoding không?

**Gợi ý:** CSP hạn chế kiểu/nguồn script thực thi và có thể báo vi phạm; Trusted Types giúp kiểm soát một số DOM sink trên nền tảng hỗ trợ. Chúng bổ sung, không thay thế việc xử lý dữ liệu đúng ngữ cảnh.

### Bài tập thực hành

Thiết kế kế hoạch kiểm thử cho ứng dụng demo gồm **Search, Comments và Profile**. Với mỗi endpoint, hãy ghi:

1. Dữ liệu nào được coi là không đáng tin cậy.
2. Những trường nào WAF cần kiểm tra và kiểu dữ liệu nào là hợp lệ.
3. Hai trường hợp thử nghiệm: một dấu hiệu XSS và một dữ liệu hợp lệ dễ bị chặn nhầm.
4. Hành động mong đợi của WAF trong chế độ monitor và sau khi rule được xác minh để block.
5. Cách ứng dụng cần xử lý dữ liệu tại điểm hiển thị.
6. Nguồn log và bằng chứng cần dùng để kết luận phát hiện, báo động giả hoặc lỗ hổng thực sự.

Bài đạt yêu cầu khi mỗi kết luận chỉ khẳng định điều **bằng chứng có thể chứng minh**, đồng thời có biện pháp bảo vệ ở cả WAF và ứng dụng.

## 18. Những điều cần ghi nhớ

- **XSS là lỗi đưa dữ liệu không đáng tin cậy vào ngữ cảnh trình duyệt không an toàn.** Chuỗi đáng ngờ trong HTTP request chỉ là tín hiệu ban đầu.
- **WAF có thể phát hiện nhiều mẫu XSS ở request**, nhưng khả năng phụ thuộc vị trí triển khai, parser, ruleset, giới hạn body và chế độ kiểm tra.
- **Reflected, stored và DOM-based XSS có đường dữ liệu khác nhau.** Đặc biệt, dữ liệu chỉ xử lý phía client có thể nằm ngoài tầm quan sát của WAF.
- **Detection không đồng nghĩa prevention hoặc xác nhận khai thác thành công.** Phải phân biệt request bị chặn, cảnh báo nghi ngờ và lỗ hổng ứng dụng đã được kiểm chứng.
- **Biện pháp chính nằm ở ứng dụng:** output encoding theo ngữ cảnh, DOM API an toàn, sanitization cho rich text, kết hợp CSP/Trusted Types khi phù hợp.
- **Giảm false positives bằng ngữ cảnh nghiệp vụ và schema**, đồng thời bảo vệ đường vào WAF và kết hợp log ứng dụng để giảm false negatives.
- **Kiểm thử có kiểm soát, ghi log an toàn và điều chỉnh liên tục** giúp WAF đóng góp hiệu quả vào kiến trúc phòng vệ mạng nhiều lớp.
