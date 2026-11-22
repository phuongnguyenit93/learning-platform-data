# End-to-end header, hop-by-hop header và vai trò trung gian

## Mục tiêu bài học

Trong chương **Nền tảng HTTP** của module **INTEGRATION_API_REST**, bài học này giúp bạn hiểu một header có ý nghĩa trên phạm vi nào khi request và response đi qua proxy, gateway hoặc cache.

Sau bài học, bạn cần:

- Phân biệt header **end-to-end** với header **hop-by-hop**.
- Giải thích vì sao hai kết nối ở hai phía của một proxy có thể có chính sách độc lập.
- Đọc và xử lý đúng ý nghĩa của `Connection` trong HTTP/1.1.
- Phân biệt metadata của representation với thông tin framing và quản lý kết nối.
- Nhận diện khác biệt khi trung gian chuyển đổi giữa HTTP/1.1, HTTP/2 và HTTP/3.
- Xác định trách nhiệm của ứng dụng Java/Spring, HTTP stack và hạ tầng khi kiểm thử API qua trung gian.

Trong bài, các khối HTTP/1.1 là cách trình bày thông điệp để học. Những ví dụ không nhằm thay thế toàn bộ quy tắc serialization, framing và xử lý lỗi của một HTTP implementation.

## 1. Một chuỗi HTTP gồm nhiều chặng

Xét hệ thống:

~~~text
Client ── kết nối A ──> Reverse proxy ── kết nối B ──> Origin server
~~~

**Origin server** là server chịu trách nhiệm cho resource mà request hướng tới. Reverse proxy tiếp nhận giao tiếp ở phía client và chuyển request tới hệ thống phía sau.

Hai kết nối A và B là hai chặng khác nhau:

- A có thể dùng HTTP/2, còn B dùng HTTP/1.1.
- Thời gian giữ kết nối ở A có thể khác B.
- Việc đóng A không bắt buộc phải đóng toàn bộ pool kết nối B.
- Một response có thể được proxy đọc, chuyển cách đóng gói rồi gửi sang chặng còn lại.

Vì vậy, không thể xem proxy như thao tác “copy nguyên mọi dòng header sang một socket khác”.

HTTP vẫn cần giữ được ý nghĩa của request và response qua chuỗi trung gian. Nhưng những thông tin chỉ điều khiển kết nối hiện tại phải được xử lý ngay tại chặng tương ứng.

Nếu một trung gian chỉ tạo tunnel và không xử lý thông điệp HTTP bên trong, cách nhìn sẽ khác với một proxy đang phân tích và tái tạo request. Các quy tắc chuyển tiếp trong bài tập trung vào trung gian thực sự xử lý thông điệp HTTP.

## 2. End-to-end và hop-by-hop khác nhau ở đâu?

| Tiêu chí | End-to-end | Hop-by-hop |
|---|---|---|
| Phạm vi ý nghĩa | Có ý nghĩa xuyên chuỗi xử lý theo định nghĩa của field | Chỉ áp dụng cho chặng/kết nối nhận thông điệp hiện tại |
| Vai trò trung gian | Hiểu hoặc chuyển tiếp theo semantics và chính sách phù hợp | Tiêu thụ, loại bỏ hoặc tạo lại cho chặng kế tiếp |
| Ví dụ điển hình | `Content-Type`, `ETag`, `If-Match`, `Cache-Control` | `Connection` và những field được khai báo là chỉ thuộc kết nối |
| Có đồng nghĩa với đáng tin cậy không? | Không | Không |
| Có đồng nghĩa với phải giữ nguyên từng byte không? | Không | Không |

**End-to-end** không có nghĩa chỉ origin hoặc client cuối cùng được đọc header. Proxy hoặc cache có thể cần hiểu `Cache-Control`, `Vary` hay validator để xử lý đúng.

Nó cũng không có nghĩa header được bảo vệ khỏi mọi thay đổi. Việc thêm, sửa hoặc xóa phải theo semantics của field và vai trò của thành phần, không dựa vào một quy tắc “mọi end-to-end header đều bất biến”.

**Hop-by-hop** không có nghĩa header vô dụng hoặc có thể bị xóa trước khi đọc. Ví dụ, thông tin framing phải được xử lý đúng trước khi tái tạo body cho chặng tiếp theo.

Đặc biệt, phạm vi header không phải cơ chế xác thực. Một header tùy biến có thể đi xuyên chuỗi nhưng vẫn do client giả mạo.

## 3. Connection trong HTTP/1.1: cơ chế khai báo phạm vi

Một thông điệp HTTP/1.1 có thể chứa:

~~~http
Connection: close, X-Hop-Note
X-Hop-Note: edge-only
~~~

Trong đó:

- `close` là một option điều khiển kết nối hiện tại.
- `X-Hop-Note` chỉ tên một field được giới hạn ở chặng hiện tại.
- Không nhất thiết có một field tên `Close` đi kèm.

Theo quy tắc chuyển tiếp, trung gian phải đọc các option trong `Connection`, loại các header/trailer mang tên tương ứng, rồi bỏ `Connection` nhận vào hoặc thay bằng điều khiển của chính nó cho chặng mới. Tên option không phân biệt hoa thường. Xem [RFC 9110, mục 7.6.1](https://www.rfc-editor.org/rfc/rfc9110.html#section-7.6.1).

### 3.1. Vì sao chỉ dùng danh sách cố định là chưa đủ?

Giả sử proxy có danh sách lọc:

~~~text
Connection
Keep-Alive
Transfer-Encoding
Upgrade
~~~

Nhưng client gửi:

~~~http
Connection: X-Hop-Note
X-Hop-Note: edge-only
~~~

Nếu chỉ xóa những tên cố định, proxy có thể để `X-Hop-Note` đi tới backend dù người gửi đã giới hạn nó cho chặng hiện tại.

Cần kết hợp:

1. Phân tích danh sách option của thông điệp đang nhận.
2. Xử lý các field có semantics kết nối đã biết.
3. Tạo metadata phù hợp cho giao thức và kết nối đầu ra.

Tên bắt đầu bằng `X-` không tự mang nghĩa hop-by-hop. Trong ví dụ, chính sự khai báo hợp lệ qua `Connection` và hợp đồng field mới tạo ngữ cảnh cần xử lý.

### 3.2. Không được tùy tiện biến field quan trọng thành connection option

Một người gửi không được dùng `Connection` để đánh dấu một field vốn dành cho toàn chuỗi thành thông tin chỉ thuộc kết nối. Chẳng hạn, đưa `Cache-Control` vào danh sách này không phải một cách hợp lệ để vô hiệu hóa chính sách cache.

Về thiết kế ứng dụng, cũng không nên tạo cơ chế bảo mật có thể bị bỏ qua nếu một header biến mất ở trung gian. Nếu thông điệp không hợp lệ hoặc thiếu bằng chứng xác thực bắt buộc sau xử lý, hệ thống phải từ chối theo chính sách thích hợp, thay vì mặc định người gọi được phép.

### 3.3. close chỉ nói về kết nối hiện tại

Nếu client gửi:

~~~http
Connection: close
~~~

thì ý định đóng liên quan đến kết nối giữa client và thành phần nhận trực tiếp.

Reverse proxy có thể:

- Hoàn tất response và đóng kết nối phía client.
- Vẫn giữ một kết nối hợp lệ tới backend để tái sử dụng.
- Hoặc chọn đóng kết nối backend theo chính sách riêng.

Client không dùng `Connection: close` để ra lệnh đóng mọi kết nối nội bộ của hệ thống.

Ngược lại, backend đóng kết nối của nó cũng không tự buộc proxy phải hủy một kết nối client còn có thể sử dụng an toàn. Việc này phụ thuộc khả năng hoàn tất thông điệp và chính sách của từng bên.

## 4. Những field thường gặp và cách đọc đúng

Bảng sau là bản đồ học tập, không phải một bộ lọc hoàn chỉnh cho proxy.

| Field | Điểm cần hiểu |
|---|---|
| `Connection` | Điều khiển chặng hiện tại trong HTTP/1.1; không chuyển nguyên giá trị nhận vào sang chặng mới |
| `Keep-Alive` | Metadata liên quan kết nối; không phải hợp đồng nghiệp vụ để controller tự áp đặt lên toàn chuỗi |
| `Proxy-Connection` | Field không chuẩn còn gặp trong một số hệ thống; không dùng làm nền tảng thiết kế mới |
| `Transfer-Encoding` | Mô tả transfer coding/framing của thông điệp HTTP/1.1; trung gian phải xử lý trước khi đóng gói lại |
| `TE` | Khả năng nhận transfer coding/trailer của bên gửi request; khác với `Transfer-Encoding` |
| `Upgrade` | Tham gia cơ chế chuyển giao thức ở kết nối phù hợp; cần xử lý chuyên biệt |
| `Content-Type` | Media type của nội dung/representation được gửi |
| `Content-Encoding` | Coding đã áp dụng lên representation, chẳng hạn gzip |
| `Content-Length` | Số octet theo semantics của thông điệp; có liên quan framing, không phải field cần xóa chỉ vì có chữ “Length” |
| `ETag`, `If-None-Match` | Validator và điều kiện liên quan representation |
| `If-Match` | Điều kiện request, thường được dùng để bảo vệ cập nhật theo phiên bản |
| `Cache-Control`, `Vary` | Chính sách cache và những yếu tố phân biệt representation |

### 4.1. Không dùng lại một danh sách cũ mà bỏ qua định nghĩa từng field

Một số tài liệu hoặc đoạn mã trên mạng gom các tên thành một danh sách “hop-by-hop” cố định. Danh sách đó có thể không phản ánh đầy đủ ngữ cảnh giao thức hoặc semantics của từng field.

Ví dụ:

- `Content-Length` không nên bị xóa vô điều kiện khỏi mọi response.
- `Trailer` là metadata khai báo những field có thể xuất hiện trong phần trailer; không nên đánh đồng với `Transfer-Encoding`.
- Các field xác thực proxy có đối tượng nhận riêng, cần xử lý theo cơ chế xác thực proxy.
- Field tùy biến có thể được nêu trong `Connection`, nên không thể biết hết chỉ từ danh sách biên dịch sẵn.

Khi xây dựng một proxy thực tế, cần dùng HTTP stack xử lý đúng giao thức và đọc định nghĩa liên quan, thay vì biến bảng học tập thành mã lọc duy nhất.

### 4.2. HTTP/1.1 không cần Keep-Alive để mọi request được tái sử dụng kết nối

HTTP/1.1 hỗ trợ kết nối persistent theo quy tắc của nó. Không nên thêm `Connection: keep-alive` và `Keep-Alive` vào mọi controller với kỳ vọng sẽ làm API nhanh hơn.

Tái sử dụng kết nối còn phụ thuộc việc thông điệp được đọc hết, framing đúng, timeout, giới hạn pool và tình trạng kết nối.

Đây là trách nhiệm HTTP stack/hạ tầng; không phải thuộc tính nên lặp lại như dữ liệu nghiệp vụ trong mỗi endpoint REST.

## 5. Ví dụ đầy đủ: một request đi qua reverse proxy

### 5.1. Thông điệp phía client

~~~http
GET /products/42 HTTP/1.1
Host: api.example.com
Accept: application/json
If-None-Match: "product-42-v6"
Connection: close, X-Hop-Note
X-Hop-Note: client-to-edge
~~~

Giả sử reverse proxy chịu trách nhiệm route tới backend catalog và không cần `X-Hop-Note` ở phía backend.

### 5.2. Thông điệp phía backend

Một request đầu ra có thể là:

~~~http
GET /products/42 HTTP/1.1
Host: catalog.internal
Accept: application/json
If-None-Match: "product-42-v6"
Via: 1.1 edge-proxy
~~~

Điểm đáng chú ý:

- `X-Hop-Note` không đi tiếp.
- `Connection: close` nhận từ client không bị sao chép sang kết nối backend.
- `Accept` và điều kiện `If-None-Match` vẫn có ý nghĩa đối với việc xử lý request.
- Host đầu ra phù hợp với cách reverse proxy định tuyến trong ví dụ.
- `Via` có thể mô tả quá trình chuyển tiếp; một field nói về trung gian không vì thế tự trở thành hop-by-hop.

Ví dụ chỉ minh họa một chính sách reverse proxy cụ thể. Không được áp dụng việc thay `Host` một cách tùy tiện cho mọi loại proxy và mọi dạng request target.

### 5.3. Response phía backend

Giả sử representation hiện tại khác validator client gửi. Backend trả `200` với transfer coding chunked:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "product-42-v7"
Transfer-Encoding: chunked

9
{"id":42}
0

~~~

Các dòng chunk là biểu diễn học tập; framing HTTP/1.1 thực dùng những dấu phân cách đúng quy định. Chuỗi JSON ASCII `{"id":42}` có 9 octet.

### 5.4. Response phía client

Nếu proxy đã nhận đầy đủ nội dung và chọn gửi bằng độ dài xác định, response đầu ra có thể là:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "product-42-v7"
Content-Length: 9
Connection: close

{"id":42}
~~~

Nội dung JSON được giữ nguyên, nhưng framing đã thay đổi:

- Proxy giải mã chunked phía nhận.
- Không chuyển nguyên `Transfer-Encoding: chunked` sang response đã gửi body không còn chunked.
- Proxy tạo `Content-Length` phù hợp với nội dung đầu ra.
- `Connection: close` trong response phía client là quyết định của chặng đó.

Không phải proxy nào cũng buffer toàn bộ body và tạo `Content-Length`. Một proxy streaming có thể chọn cách framing hợp lệ khác. Điều bắt buộc là thông tin đóng gói khớp với thông điệp thực tế.

## 6. Transfer-Encoding khác Content-Encoding

Hai field này thường bị nhầm vì đều có thể liên quan đến cách mã hóa dữ liệu.

### 6.1. Transfer-Encoding mô tả truyền thông điệp

~~~http
Transfer-Encoding: chunked
~~~

Ở HTTP/1.1, nội dung có thể được chia thành chunk để truyền mà không biết trước tổng độ dài.

Một trung gian có thể giải mã rồi đóng gói lại cho chặng tiếp theo. Việc bỏ các đường biên chunk không đồng nghĩa thay đổi ý nghĩa JSON.

### 6.2. Content-Encoding mô tả representation

~~~http
Content-Type: application/json
Content-Encoding: gzip
~~~

Ở đây representation đã được mã hóa bằng gzip. Bên nhận phải xử lý coding phù hợp trước khi đọc JSON.

Nếu proxy giải nén rồi gửi dữ liệu không còn gzip, nó không được giữ `Content-Encoding: gzip` như thể body vẫn nén. Những metadata khác có liên quan cũng phải nhất quán với representation đầu ra.

Đặc biệt, không thể thay đổi dữ liệu của representation rồi mặc định giữ nguyên một strong ETag vốn mô tả representation trước đó.

### 6.3. TE khác Accept-Encoding

Một ví dụ HTTP/1.1:

~~~http
TE: trailers
Connection: TE
~~~

không có cùng nghĩa với:

~~~http
Accept-Encoding: gzip
~~~

Cái đầu mô tả khả năng nhận trailer trong ngữ cảnh giao thức tương ứng. Cái sau nói về content coding có thể chấp nhận cho representation.

Trong thực hành, không nên chuyển hai field này qua lại chỉ vì chúng đều liên quan đến từ “encoding”.

## 7. Content-Length và framing: không được sửa header tách rời body

Một lỗi nguy hiểm là xóa `Transfer-Encoding` rồi giữ nguyên dữ liệu chunked; bên nhận sau đó không còn được hướng dẫn đúng cách xác định body.

Lỗi ngược lại là gửi body đã giải mã nhưng vẫn khai báo chunked.

Với HTTP/1.1, sender không được tạo thông điệp đồng thời chứa `Transfer-Encoding` và `Content-Length`. Khi nhận một thông điệp có cả hai, trung gian cần xử lý theo quy tắc framing và chính sách lỗi, không chuyển nguyên trạng vì hai parser có thể hiểu khác nhau. Xem [RFC 9112, mục 6.2–6.3](https://www.rfc-editor.org/rfc/rfc9112.html#section-6.3).

Ở mức thiết kế và kiểm thử, cần bảo đảm:

- Không chuyển tiếp một `Content-Length` đã biết là sai.
- Không tự đếm độ dài bằng số ký tự Java.
- Không cho các lớp hiểu khác nhau về nơi một thông điệp kết thúc.
- Không chỉ “làm sạch header” mà bỏ qua việc HTTP stack đã đọc body ra sao.

Với chuỗi Java, số ký tự và số byte UTF-8 có thể khác nhau:

~~~java
byte[] bytes = body.getBytes(java.nio.charset.StandardCharsets.UTF_8);
int byteLength = bytes.length;
~~~

Ví dụ này chỉ minh họa đơn vị byte. Trong ứng dụng web thông thường, nên để HTTP stack tạo framing thay vì tự tính `Content-Length` trong controller, đặc biệt khi có nén, streaming hoặc chuyển đổi nội dung.

## 8. Khác biệt trong HTTP/2 và HTTP/3

### 8.1. Không mang nguyên cơ chế Connection của HTTP/1.1 sang HTTP/2

HTTP/2 không dùng `Connection` để đánh dấu field theo kết nối. Các field connection-specific như `Connection`, `Keep-Alive`, `Proxy-Connection`, `Transfer-Encoding` và `Upgrade` không được đưa vào thông điệp HTTP/2; thông điệp chứa chúng bị xem là malformed. Ngoại lệ là request có thể chứa `TE` với giá trị duy nhất `trailers`. Xem [RFC 9113, mục 8.2.2](https://www.rfc-editor.org/rfc/rfc9113.html#section-8.2.2).

Khi gateway nhận HTTP/1.1 rồi gửi HTTP/2, nó phải thực hiện chuyển đổi giao thức, không phải chỉ sửa dòng phiên bản.

Các pseudo-header như `:method`, `:scheme`, `:authority` và `:path` là control data của giao thức. Không được coi chúng là những dòng header HTTP/1.1 tùy ý để copy sang socket.

### 8.2. HTTP/3 cũng có quy tắc riêng

HTTP/3 không cho phép field connection-specific kiểu HTTP/1.x. Request có thể dùng `TE: trailers` theo ngoại lệ được quy định; không được thêm `Connection: TE` theo thói quen HTTP/1.1. Xem [RFC 9114, mục 4.2](https://www.rfc-editor.org/rfc/rfc9114.html#section-4.2).

Các frame và stream của HTTP/3 thực hiện việc truyền thông điệp theo giao thức của nó. `Transfer-Encoding: chunked` không phải cách để bật streaming cho HTTP/3.

### 8.3. Một hành trình có thể dùng nhiều phiên bản

~~~text
Client ── HTTP/3 ──> Edge ── HTTP/2 ──> Gateway ── HTTP/1.1 ──> API
~~~

Với cùng request nghiệp vụ:

- Method và điều kiện cập nhật vẫn cần giữ đúng ý nghĩa.
- Cách biểu diễn control data và framing thay đổi theo từng chặng.
- Quản lý stream/kết nối thuộc từng giao thức.
- Một header hợp lệ ở một chặng không mặc nhiên hợp lệ ở chặng khác.

Vì vậy, chỉ kiểm thử trực tiếp API bằng HTTP/1.1 chưa chứng minh đường đi thực tế qua gateway dùng HTTP/2 hoặc HTTP/3 đã đúng.

## 9. Phân biệt Authorization với xác thực proxy

Không phải field nào có tiền tố `Proxy-` cũng nên được xử lý như một phần tử trong danh sách lọc chung mà không đọc semantics.

| Cặp field | Mục đích |
|---|---|
| `WWW-Authenticate` / `Authorization` | Challenge và thông tin xác thực cho phía cung cấp resource |
| `Proxy-Authenticate` / `Proxy-Authorization` | Challenge và thông tin xác thực cho proxy yêu cầu xác thực |

Thông tin xác thực proxy phải tới đúng proxy cần nó, không được làm rò rỉ vào origin như thể đó là credential của API. Một chuỗi proxy có thể có cơ chế phối hợp riêng; không được suy rằng credential proxy luôn được copy qua mọi thành phần.

Còn với API, sự có mặt của proxy không biến `Authorization` thành một field có thể bỏ vô cớ. Proxy chuyển tiếp thông thường không được tự sửa credential của request. Những mô hình gateway chấm dứt một cơ chế xác thực rồi gọi một dịch vụ khác cần được thiết kế thành ranh giới danh tính và hợp đồng tin cậy rõ ràng.

Đối với ứng dụng:

- Không dùng credential proxy thay cho danh tính người dùng API.
- Không mặc định header danh tính nội bộ do client gửi là đáng tin.
- Không coi “đã qua gateway” là đủ để bỏ kiểm tra quyền trên resource.
- Không ghi nguyên token vào log chỉ để theo dõi việc chuyển header.

## 10. Phạm vi truyền tiếp khác độ tin cậy

Một số field như `Forwarded`, `X-Forwarded-For` hoặc một header correlation ID có thể được dùng xuyên nhiều lớp.

Điều đó không làm giá trị của chúng tự đáng tin. Client có thể gửi một header cùng tên trước khi request tới reverse proxy.

Cần một chính sách riêng:

1. Xác định những proxy nào được phép cung cấp metadata.
2. Xử lý giá trị do bên ngoài gửi tại ranh giới tin cậy.
3. Xác định lớp nào tạo, thay hoặc nối thêm thông tin.
4. Ngăn đường truy cập bỏ qua lớp kiểm soát.
5. Chỉ dùng dữ liệu đã xác thực cho quyết định nhạy cảm.

Có thể phân tích một header theo ba câu hỏi độc lập:

| Câu hỏi | Ví dụ |
|---|---|
| Header có được phép đi qua chặng này không? | Đọc `Connection` và quy tắc phiên bản giao thức |
| Header có ý nghĩa gì đối với xử lý request? | `If-Match` là điều kiện cần được kiểm tra |
| Giá trị có đáng tin để ra quyết định không? | Một user ID do client tự khai báo không phải bằng chứng xác thực |

Nhầm ba câu hỏi thành một thường dẫn tới một trong hai lỗi: xóa quá nhiều làm mất hợp đồng hoặc chuyển tiếp quá rộng làm vượt ranh giới tin cậy.

## 11. Vai trò của proxy, gateway và cache

### 11.1. Proxy phải bảo toàn ý nghĩa, không bảo toàn mọi byte

Một proxy có thể thay cách đóng gói thông điệp, nhưng không được vì thế làm mất điều kiện nghiệp vụ.

Ví dụ, bỏ `If-Match` khỏi một request cập nhật có thể khiến backend mất điều kiện phiên bản mà client yêu cầu. Đây không phải thao tác tối ưu kết nối.

Tương tự, chuyển sai `Content-Type` có thể khiến server giải mã body bằng hợp đồng khác.

### 11.2. Gateway áp dụng chính sách cần tính đến tính mở rộng

Một gateway chỉ cho qua vài header quen thuộc có thể làm hỏng API khi hợp đồng bổ sung validator, khóa idempotency hoặc thông tin thương lượng nội dung.

Chính sách allowlist có thể là lựa chọn có chủ đích trong một hệ thống cụ thể, nhưng phải được quản lý như một phần hợp đồng. Không nên gọi mọi field chưa biết là hop-by-hop.

Tên field không phân biệt hoa thường. Tuy vậy, không được chuyển toàn bộ giá trị sang chữ thường: token xác thực, chuỗi quoted và nhiều kiểu giá trị khác có quy tắc riêng.

Các field có nhiều dòng cũng cần được xử lý theo định nghĩa của chúng. Không phải mọi field đều có thể ghép bằng dấu phẩy; `Set-Cookie` là một ví dụ cần giữ cách biểu diễn phù hợp.

### 11.3. Cache cần metadata có ý nghĩa xuyên chuỗi

Nếu gateway bỏ `Cache-Control`, `Vary` hoặc `ETag`, cache có thể mất thông tin cần thiết cho freshness, phân biệt representation hoặc kiểm tra lại.

Ngược lại, giữ các header đó nhưng thay body không nhất quán cũng gây lỗi.

Header end-to-end hỗ trợ cache không có nghĩa mọi response đều được shared cache lưu. Dữ liệu cá nhân, quyền người gọi và các chỉ thị không lưu vẫn phải được xem xét theo hợp đồng.

## 12. Liên hệ với Java/Spring

Trong một ứng dụng Spring MVC, controller thường tập trung vào hợp đồng của resource:

~~~java
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    @GetMapping(value = "/orders/42", produces = "application/json")
    public ResponseEntity<OrderView> getOrder() {
        OrderView order = new OrderView(42, "CONFIRMED");

        return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .cacheControl(CacheControl.noStore())
            .body(order);
    }

    public record OrderView(long id, String status) {
    }
}
~~~

Đoạn mã dùng Java có hỗ trợ `record`, trong ứng dụng đã có bộ chuyển đổi JSON phù hợp. Resource cố định để minh họa metadata; ứng dụng thực tế vẫn cần truy cập dữ liệu và thực thi xác thực, phân quyền.

Controller không tự thêm `Connection`, `Keep-Alive` hoặc `Transfer-Encoding`. Container/HTTP stack và hạ tầng quyết định những chi tiết của từng kết nối.

Có thể phân chia trách nhiệm:

| Thành phần | Trách nhiệm điển hình |
|---|---|
| Controller và tầng nghiệp vụ | Status, media type, dữ liệu, lỗi, điều kiện nghiệp vụ và quyền |
| HTTP connector/container | Parse/serialize, framing, quản lý kết nối và quy tắc phiên bản |
| Proxy/gateway | Chuyển tiếp đúng, chính sách route, xử lý field theo chặng và ranh giới tin cậy |
| Kiểm thử tích hợp | Xác minh hợp đồng vẫn đúng trên đường đi thực tế |

Nếu xây một gateway bằng Java, không nên copy toàn bộ `HttpHeaders` từ request nhận vào sang một HTTP client khác. Cần xử lý request target, field theo kết nối, body, framing, credential và semantics chuyển đổi.

Ngược lại, cũng không nên dùng một hàm xóa tên field cố định rồi coi đã xây được proxy chuẩn. Các ví dụ trong bài là mô hình tư duy, không phải một HTTP proxy implementation hoàn chỉnh.

## 13. Kiểm thử qua trung gian

Một nhóm có thể dùng những tình huống sau để thiết kế kiểm thử tích hợp:

| Tình huống | Điều cần quan sát |
|---|---|
| HTTP/1.1 có field tùy biến được nêu trong Connection | Field chỉ thuộc chặng nhận, không xuất hiện vô cớ ở backend |
| Client yêu cầu đóng kết nối | Không làm chính sách pool backend bị áp đặt sai |
| Request có If-Match | Điều kiện còn nguyên ý nghĩa khi tới nơi thực thi cập nhật |
| Response chunked được chuyển sang độ dài xác định | Body đúng, không còn framing mâu thuẫn |
| Có nén representation | Content-Encoding, độ dài và validator nhất quán |
| Gateway gửi HTTP/2 hoặc HTTP/3 | Không mang field connection-specific bị cấm |
| Request HTTP/2 có TE | Chỉ giá trị được giao thức cho phép |
| Request có credential proxy | Không rò rỉ credential vào origin không liên quan |
| Field có nhiều dòng | Không làm mất giá trị hoặc ghép sai cú pháp |
| Client tự khai báo metadata nội bộ | Không vượt qua ranh giới tin cậy |
| Header hợp đồng mới được bổ sung | Không bị bộ lọc gateway xóa ngoài chủ đích |

Với một số lỗi framing hoặc field bị cấm, HTTP stack có thể từ chối request trước khi controller được gọi. Vì vậy, chỉ nhìn log controller sẽ không thấy đầy đủ hành vi cần kiểm tra.

Kiểm thử controller riêng vẫn hữu ích cho hợp đồng ứng dụng. Nhưng xác nhận semantics qua trung gian cần kiểm thử ở những điểm thật sự có chuyển tiếp hoặc chuyển đổi giao thức.

## 14. Tự kiểm tra

### Câu hỏi

1. Header bắt đầu bằng `X-` có tự động là hop-by-hop không?
2. Proxy chỉ xóa một danh sách field cố định mà không đọc `Connection` có đủ không?
3. `Connection: close` từ client có bắt proxy đóng mọi kết nối backend không?
4. Xóa `Transfer-Encoding` nhưng giữ nguyên dữ liệu chunked có đúng không?
5. `Content-Encoding: gzip` có cùng nghĩa với `Transfer-Encoding: chunked` không?
6. Khi gửi HTTP/2, có thể giữ `Connection: keep-alive` vì client muốn tái sử dụng kết nối không?
7. `TE: trailers` trong HTTP/2 có cần thêm `Connection: TE` không?
8. Vì sao end-to-end không đồng nghĩa với đáng tin?
9. Có nên xóa `If-Match` vì nó không nằm trong danh sách header mà gateway từng biết không?
10. Controller trả JSON đúng có đủ chứng minh một proxy đã chuyển framing đúng không?

### Gợi ý trả lời

1. Không. Cần xem định nghĩa và ngữ cảnh, bao gồm việc khai báo hợp lệ trong Connection nếu áp dụng.
2. Không. Field tùy biến có thể được khai báo theo kết nối trong chính thông điệp đang nhận.
3. Không. Nó liên quan chặng client–thành phần nhận trực tiếp; chặng backend có chính sách riêng.
4. Không. Phải xử lý transfer coding và tạo framing đầu ra phù hợp.
5. Không. Một field nói về representation coding, field còn lại nói về transfer coding/framing.
6. Không. HTTP/2 không dùng field Connection để quản lý kết nối và cấm field đó trong thông điệp.
7. Không. Ngoại lệ TE của HTTP/2 không cho phép đưa Connection trở lại.
8. Vì dữ liệu có thể do một client không tin cậy gửi; phạm vi truyền tiếp khác với bằng chứng danh tính hoặc tính toàn vẹn.
9. Không được xóa vô cớ. Làm mất điều kiện có thể thay đổi semantics của thao tác cập nhật.
10. Không. Có thể phải kiểm tra HTTP stack và đường đi qua trung gian, nơi body được phân tích hoặc đóng gói lại.

Khi đọc một chuỗi request/response, hãy xác định riêng **ý nghĩa của thông điệp**, **metadata của representation**, **điều khiển từng chặng** và **nguồn đáng tin của giá trị**. Cách phân tích này giúp API giữ đúng hợp đồng khi đi qua proxy, gateway và các phiên bản HTTP khác nhau.
