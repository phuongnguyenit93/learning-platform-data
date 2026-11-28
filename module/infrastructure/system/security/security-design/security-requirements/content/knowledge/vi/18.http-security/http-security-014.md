# Proxy trust boundary

## 1. Mục tiêu và phạm vi

Proxy trust boundary là ranh giới xác định một thành phần được tin cậy để khẳng định điều gì về request, trong điều kiện kết nối và cấu hình nào. Trong một hệ thống HTTP có reverse proxy, gateway hoặc load balancer, ứng dụng có thể nhận thông tin về client, scheme và host qua các header chuyển tiếp. Những giá trị đó chỉ có ý nghĩa bảo mật khi nguồn phát biểu và đường truyền của chúng đã được kiểm soát.

Ví dụ, `X-Forwarded-For` có thể giúp ứng dụng biết địa chỉ client trước proxy. Nhưng nếu ứng dụng lấy bất kỳ giá trị nào của header này làm sự thật, một client có thể tự khai địa chỉ khác để ảnh hưởng bộ đếm, audit hoặc một quyết định dựa vào địa chỉ mạng.

Trong thiết kế yêu cầu bảo mật, câu “ứng dụng chạy sau proxy tin cậy” chưa đủ. Cần chỉ rõ proxy nào, được phép đặt trường nào, backend xác nhận nguồn bằng gì, dữ liệu từ ngoài ranh giới bị xử lý thế nào và hành vi khi chuỗi chuyển tiếp không hợp lệ.

Sau bài này, người học có thể:

- Phân biệt peer trực tiếp, client được suy ra và danh tính người dùng đã xác thực.
- Mô hình hóa các hop và thẩm quyền của từng proxy đối với metadata.
- Đặc tả xử lý `Forwarded`, các header `X-Forwarded-*` và header danh tính nội bộ.
- Giữ ranh giới tin cậy khi có nhiều đường vào, thay đổi số hop hoặc TLS termination.
- Viết tiêu chí nghiệm thu cho giả mạo metadata, truy cập trực tiếp backend và dữ liệu mâu thuẫn.

Bài tập trung vào hợp đồng tin cậy giữa các thành phần. Nó không thay tài liệu cấu hình riêng của từng sản phẩm hoặc các yêu cầu độc lập về authentication, authorization, TLS và phân tích cú pháp HTTP.

## 2. Mô hình hóa đường đi và nguồn phát biểu

### 2.1. Một request đi qua nhiều kết nối

Xét mô hình minh họa:

```text
Client C
    → Edge proxy E
    → Load balancer L
    → Ứng dụng A
```

Ứng dụng A trực tiếp kết nối với L. Nếu có TLS giữa A và L, phiên đó xác thực và bảo vệ đoạn A/L theo cấu hình của nó; nó không tự chứng minh toàn bộ thông tin mà C từng gửi đã đúng.

Có thể dùng các địa chỉ tài liệu để theo dõi ví dụ:

```text
C: 198.51.100.24
E: 192.0.2.10
L: 192.0.2.20
```

Đây là địa chỉ minh họa, không phải cấu hình mạng của một hệ thống thực tế. Trong mô hình này, A cần biết peer trực tiếp là L và chỉ chấp nhận metadata theo hợp đồng của L, E cùng các ràng buộc đường vào đã xác định.

### 2.2. Ba loại danh tính không được gộp chung

| Thông tin | Ý nghĩa | Không tự chứng minh |
| --- | --- | --- |
| Peer trực tiếp | Bên thiết lập kết nối đang đi vào thành phần nhận | Người dùng cuối là ai |
| Địa chỉ client suy ra | Địa chỉ được khôi phục theo chuỗi proxy và policy | Chủ thể có quyền nghiệp vụ nào |
| Danh tính ứng dụng | Người dùng hoặc dịch vụ đã được nhận diện theo cơ chế xác thực | Mọi metadata mạng trong request đều đáng tin |

Một địa chỉ private không đồng nghĩa là quản trị viên. Một request đi từ proxy được phép cũng không đồng nghĩa người dùng cuối được đọc mọi dữ liệu. Những kết luận đó cần các quy tắc độc lập.

### 2.3. Tin cậy phải gắn với một phát biểu cụ thể

Một edge proxy có thể được tin để xác nhận scheme của kết nối phía client và ghi địa chỉ peer mà nó quan sát. Nó chưa chắc có quyền tự xác định tenant nghiệp vụ hoặc role quản trị.

Một gateway xác thực có thể được phép gửi danh tính đã kiểm chứng cho backend trong một hợp đồng riêng. Nhưng quyền đó cần điều kiện như danh tính gateway được xác nhận, header từ caller bị loại bỏ và backend không có đường vào bỏ qua gateway.

Nên mô tả sự tin cậy theo dạng:

```text
Thành phần nào được phép phát biểu về trường dữ liệu nào,
qua kênh nào, và bên nhận phải kiểm tra điều kiện gì trước khi sử dụng?
```

## 3. Header chuyển tiếp là dữ liệu có nguồn gốc, không phải bằng chứng tự thân

### 3.1. Forwarded và X-Forwarded-*

`Forwarded` là header chuẩn hóa để proxy chuyển các thông tin như `for`, `proto` và `host`. Tuy nhiên, RFC 7239 chỉ rõ dữ liệu này có thể bị thay đổi bởi các node, kể cả client, nên sự hiện diện hoặc cú pháp đúng không tự tạo tính tin cậy. [RFC 7239, mục 8.1](https://www.rfc-editor.org/rfc/rfc7239.html#section-8.1)

Một giá trị minh họa:

```http
Forwarded: for=198.51.100.24;proto=https;host=portal.example.test
```

Các hệ thống còn dùng họ header khác, chẳng hạn:

```http
X-Forwarded-For: 198.51.100.24
X-Forwarded-Proto: https
X-Forwarded-Host: portal.example.test
```

Không nên giả định hai dạng có cùng grammar, quy tắc chuỗi hoặc mức ưu tiên trong mọi thư viện. Hệ thống cần chọn hợp đồng được hỗ trợ và kiểm soát những dạng còn lại để các thành phần không rút ra kết luận khác nhau.

### 3.2. Phân loại metadata theo mức ảnh hưởng

| Dữ liệu | Cách dùng có thể gặp | Điều cần kiểm soát |
| --- | --- | --- |
| Địa chỉ client | Rate limit, audit, phát hiện bất thường | Nguồn địa chỉ và thuật toán xác định hop |
| Scheme bên ngoài | Redirect, URL tự tham chiếu, xử lý phiên | Proxy nào xác nhận kết nối phía trước và những giá trị nào hợp lệ |
| Host/authority | Chọn ứng dụng, liên kết tuyệt đối, cache | Danh mục host và ánh xạ route được phê duyệt |
| Prefix/path gốc | Xây URL, routing sau rewrite | Phép biến đổi được cho phép và ngữ nghĩa nhất quán |
| User/role/tenant nội bộ | Xác thực và phân quyền ở backend | Nguồn danh tính, kênh bảo vệ và phạm vi ủy quyền |
| Request/trace ID | Liên kết log | Độ dài, định dạng, phạm vi tin cậy và tránh nhầm với danh tính |

Không phải mọi metadata có cùng mức rủi ro. Một trường phục vụ chẩn đoán có thể được ghi nhận là dữ liệu tự khai, trong khi trường dùng để bỏ qua một kiểm tra bảo mật phải có căn cứ đáng tin cậy mạnh hơn.

### 3.3. Ví dụ dữ liệu client tự khai

Một request từ bên ngoài có thể chứa:

```http
GET /requirements HTTP/1.1
Host: portal.example.test
X-Forwarded-For: 127.0.0.1
X-Forwarded-Proto: https
X-User-Role: ADMIN
```

Kỳ vọng của thiết kế an toàn là các trường tự khai này không biến caller thành localhost, không chứng minh kết nối ban đầu là HTTPS và không cấp role quản trị. Proxy ở ranh giới phải xử lý chúng theo hợp đồng trước khi tạo metadata mà các thành phần phía sau sử dụng.

## 4. Thiết lập ranh giới tin cậy

### 4.1. Xác nhận peer bằng thông tin không lấy từ chính header đang xét

Trước khi tin header chuyển tiếp, thành phần nhận phải biết request đến từ peer được phép. Căn cứ có thể gồm danh tính dịch vụ được xác thực bằng mTLS, chính sách mạng và địa chỉ nguồn quan sát từ kết nối theo mô hình triển khai.

Không dùng một header như `X-Trusted-Proxy: true` do caller có thể gửi để xác nhận chính caller. Nếu dùng chứng chỉ client, cần kiểm tra danh tính peer được phép làm proxy, không chỉ kiểm tra chứng chỉ do một CA nào đó ký.

Một CIDR lớn chứa cả proxy lẫn workload không liên quan có thể mở rộng ranh giới quá mức. Danh sách nguồn được tin phải phản ánh đúng những thành phần có thẩm quyền đặt metadata theo hợp đồng.

### 4.2. Giữ được peer gốc trước khi chuẩn hóa

Một module real-IP hoặc filter có thể thay thuộc tính địa chỉ request bằng địa chỉ client suy ra. Sau bước đó, tên trường quen thuộc như remote address có thể không còn là địa chỉ socket peer ban đầu.

Yêu cầu triển khai cần chỉ rõ nơi lấy peer gốc và nơi lưu kết quả đã chuẩn hóa. Không quyết định “có tin proxy hay không” dựa trên một địa chỉ đã được khôi phục từ chính header cần kiểm tra.

### 4.3. Chặn đường vào bỏ qua ranh giới

Nếu ứng dụng chỉ được nhận request qua L, listener phục vụ đó cần được bảo vệ để nguồn ngoài hợp đồng không đi trực tiếp tới backend rồi tự gửi metadata giả.

Các đường vào thường cần kiểm kê gồm địa chỉ trực tiếp của instance, listener quản trị, endpoint nội bộ, tuyến dự phòng và đường đi giữa các vùng. “URL công khai đi qua gateway” chưa chứng minh mọi cách tiếp cận backend đều đi qua gateway.

Nếu hệ thống chủ động cho phép cả truy cập trực tiếp lẫn qua proxy, phải có hai nhánh xử lý rõ. Request trực tiếp không được hưởng mức tin cậy của metadata proxy chỉ vì header có mặt.

### 4.4. Bảo vệ kênh giữa các thành phần được tin

Metadata đã được edge tạo vẫn có thể bị thay trên đường tới backend nếu các đoạn đó không được bảo vệ theo mô hình đe dọa. Cần xác định tính toàn vẹn và xác thực peer cho từng đoạn, không chỉ đoạn client tới edge.

Một proxy được tin đã bị chiếm quyền cũng có thể phát biểu sai trong phạm vi nó được phép. Thiết kế ranh giới không loại bỏ trách nhiệm bảo vệ proxy, giới hạn thẩm quyền của nó và cung cấp bằng chứng điều tra.

## 5. Tạo metadata chuẩn ở điểm vào

### 5.1. Loại bỏ giá trị từ nguồn ngoài ranh giới

Ở điểm chuyển từ nguồn không tin sang chuỗi do hệ thống kiểm soát, policy cần xác định những header phải được loại bỏ hoặc thiết lập lại. Tài liệu Spring nhấn mạnh phải xử lý cả `Forwarded` và họ `X-Forwarded-*` ở ranh giới, tránh để một dạng bị bỏ sót rồi được thành phần khác dùng. [Spring Framework: Forwarded Headers](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html#filters-forwarded-headers)

Ví dụ policy của edge trực tiếp nhận client không được tin:

```text
1. Xác định dữ liệu từ kết nối và listener thực tế.
2. Kiểm tra authority theo danh mục host và route đã cấu hình.
3. Loại bỏ metadata chuyển tiếp hoặc danh tính nội bộ do client tự gửi.
4. Tạo lại những trường mà edge được phép khẳng định.
5. Chuyển request tới peer phía sau qua kênh được bảo vệ.
```

Đây là policy minh họa, không phải một cấu hình bắt buộc cho mọi topology. Nếu phía trước edge còn có CDN được tin, cần xác thực CDN và định nghĩa chính xác phần metadata được chấp nhận từ nó. Không xóa tùy ý thông tin cần thiết rồi đoán lại ở backend.

### 5.2. Không giữ một header phụ có thể tạo kết luận trái ngược

Giả sử proxy đặt lại `X-Forwarded-Proto` nhưng giữ nguyên `Forwarded` do client gửi, trong khi framework ưu tiên `Forwarded`. Thao tác làm sạch một header chưa tạo bảo đảm cho scheme mà ứng dụng sử dụng.

Policy cần liệt kê các dạng metadata thực sự được xử lý và quy tắc cho dạng không được hỗ trợ. Nếu cho phép nhiều nguồn tương đương, phải xác định cách đối chiếu và xử lý mâu thuẫn; không để mỗi thư viện tự chọn nguồn khác nhau.

Tương tự, header nội bộ như user, role hoặc thông tin chứng chỉ client chỉ có ý nghĩa trong hợp đồng riêng. Một tên header nghe giống hạ tầng không tự làm nó đáng tin.

### 5.3. Host và scheme phải đáp ứng hợp đồng độc lập

`Host` hoặc `:authority` tham gia định tuyến ở tầng HTTP, nên không phải một định danh đã được phê duyệt chỉ vì request đã tới server. RFC 9110 lưu ý rủi ro thao túng host/port đối với định tuyến và cache. [RFC 9110, mục 7.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-7.2)

Hệ thống cần danh mục public authority hoặc ánh xạ tenant/host được kiểm soát. Nếu proxy rewrite host sang tên backend nội bộ, phép rewrite đó phải được ghi rõ; không bắt mọi host ở mọi hop phải giống nhau khi kiến trúc chủ động thay đổi chúng.

Scheme bên ngoài được proxy xác nhận có thể khác cơ chế bảo vệ đoạn backend. Một giá trị `https` đáng tin cho đoạn client/edge vẫn không chứng minh edge/backend cũng dùng TLS.

### 5.4. Dữ liệu không hợp lệ không được nâng mức tin cậy

Header có thể thiếu, có nhiều giá trị, quá dài, chứa token không hợp lệ hoặc không phù hợp với topology. Cần parser đúng với định dạng đã chọn và giới hạn tài nguyên xử lý.

Nếu thông tin bắt buộc cho một quyết định không xác định được, phải theo hành vi lỗi đã đặc tả. Không tự chọn một giá trị dễ dãi như localhost hoặc nội bộ để tiếp tục hành động cần mức tin cậy cao.

Một số định dạng có thể hợp lệ nhưng không cung cấp địa chỉ IP cụ thể. Cách dùng metadata cần phân biệt “không biết địa chỉ” với “được phép bỏ kiểm tra”.

## 6. Chuỗi client IP: phải có thuật toán gắn với topology

### 6.1. Ví dụ chuỗi do hai proxy kiểm soát

Trong topology C → E → L → A, giả sử E thiết lập lại XFF thành địa chỉ C mà nó quan sát và L nối địa chỉ peer E vào cuối. A nhận:

```text
Peer trực tiếp của A: 192.0.2.20

X-Forwarded-For: 198.51.100.24, 192.0.2.10
```

Kết quả mong muốn là địa chỉ client `198.51.100.24`, dựa trên đúng hợp đồng hai hop. Địa chỉ cuối trong XFF là E, không phải client; địa chỉ socket là L, cũng không phải client.

Không được dùng quy tắc chung “luôn chọn phần tử đầu” hoặc “luôn chọn phần tử cuối” cho mọi topology. Cần biết proxy nào đã ghi phần tử nào và request có thực sự đi qua các proxy đó hay không.

### 6.2. Duyệt từ phía peer đã biết

Một mô hình xác định địa chỉ có thể bắt đầu từ peer trực tiếp đã được xác nhận, rồi xem chuỗi từ phía gần thành phần nhận và chỉ đi tiếp qua các hop thuộc phạm vi được tin. Khi gặp ranh giới không được tin, không được dùng các phần trước đó làm bằng chứng mạnh hơn.

Ví dụ, nếu một thiết kế giữ cả tiền tố client tự khai, chuỗi có thể là:

```text
203.0.113.66, 198.51.100.24, 192.0.2.10
```

Ở đây `203.0.113.66` là giá trị minh họa do client tự khai. Thuật toán đúng theo mô hình đã chọn phải dừng tại ranh giới C, không lấy tiền tố đó để gán cho caller. Trong policy thiết lập lại tại E ở phần trước, tiền tố tự khai sẽ bị loại bỏ ngay ở E.

Các sản phẩm có cách biểu diễn cấu hình khác nhau. Envoy có cơ chế dựa vào remote address, số hop được tin hoặc phát hiện origin theo CIDR; các tùy chọn này không thể được hiểu chỉ bằng tên header. [Envoy: X-Forwarded-For](https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_conn_man/headers#x-forwarded-for)

### 6.3. Số hop cố định cần một đường đi cố định

Một policy đếm từ phải theo N hop có thể phù hợp nếu mọi request thuộc listener đi qua đúng topology đã định nghĩa. Nếu tồn tại đường ngắn hơn hoặc một tuyến bỏ qua CDN, cùng N có thể chỉ tới một vị trí do caller điều khiển.

Vì vậy, thay đổi topology phải kéo theo đánh giá lại thuật toán. Không chỉ tăng số hop cho tới khi log hiển thị địa chỉ trông có vẻ đúng trong một request.

### 6.4. Cấu hình real-IP không tự xác nhận mọi nguồn

Ví dụ, NGINX tách việc khai báo nguồn được tin bằng `set_real_ip_from`, chọn header bằng `real_ip_header` và cách xử lý chuỗi bằng `real_ip_recursive`. Cần đọc ý nghĩa kết hợp của các cấu hình này thay vì chỉ bật một tùy chọn recursive. [NGINX: ngx_http_realip_module](https://nginx.org/en/docs/http/ngx_http_realip_module.html)

Danh sách hop có thể được tin khi phân tích chuỗi và danh sách peer được phép đi vào listener là những điều kiện liên quan nhưng không thay thế nhau. Một hop xuất hiện hợp lệ trong chuỗi không có nghĩa được phép bỏ qua các lớp phía trước để kết nối trực tiếp.

## 7. Đặc tả yêu cầu bảo mật có thể kiểm chứng

### 7.1. Yêu cầu nền tảng

```text
REQ-PROXY-01 — Nguồn tin cậy của request context

Ứng dụng chỉ được dùng metadata chuyển tiếp cho quyết định bảo mật khi
request tới từ peer được phép, qua đường vào được phê duyệt và metadata
đáp ứng hợp đồng về định dạng, nguồn phát biểu cùng topology.

Metadata từ caller ngoài ranh giới không được làm thay đổi danh tính,
phạm vi quyền, nguồn client hoặc thuộc tính kết nối theo hướng nâng quyền.

Khi thiếu căn cứ bắt buộc, hệ thống phải xử lý theo nhánh lỗi đã đặc tả,
không tự gán một ngữ cảnh có mức tin cậy cao hơn.
```

### 7.2. Các yêu cầu theo ranh giới

| Mã | Nội dung yêu cầu | Bằng chứng nghiệm thu |
| --- | --- | --- |
| REQ-PROXY-02 | Listener backend chỉ nhận các peer được phép theo mô hình triển khai; đường vào khác có policy độc lập | Kiểm tra mạng, danh tính peer và các tuyến dự phòng |
| REQ-PROXY-03 | Điểm vào loại bỏ hoặc thiết lập lại toàn bộ dạng metadata ngoài ranh giới mà các thành phần có thể sử dụng | Giá trị trước/sau edge và request có nhiều họ header |
| REQ-PROXY-04 | Client IP được suy ra bằng thuật toán gắn với topology; không chọn tùy ý phần tử trong chuỗi | Trường hợp tiền tố giả, thiếu hop và nhiều đường đi |
| REQ-PROXY-05 | Scheme và authority được đối chiếu với listener, route và danh mục origin được phê duyệt | Redirect, liên kết tự tham chiếu và các giá trị mâu thuẫn |
| REQ-PROXY-06 | Header danh tính nội bộ chỉ được chấp nhận từ thành phần có quyền khẳng định danh tính theo hợp đồng riêng | Request giả role/user, peer sai danh tính và kiểm tra quyền đối tượng |
| REQ-PROXY-07 | Parser và thứ tự chuẩn hóa không để các thành phần ra quyết định trái ngược về cùng request | Kết quả qua filter, framework và nghiệp vụ |
| REQ-PROXY-08 | Thông tin bắt buộc thiếu hoặc không hợp lệ không được dẫn tới nhánh mặc định tin cậy | Request lỗi metadata, lỗi xác thực peer và lỗi cấu hình |
| REQ-PROXY-09 | Thay đổi topology hoặc cấu hình real-IP phải đánh giá lại hợp đồng và bằng chứng | Hồ sơ thay đổi, cấu hình có hiệu lực và kiểm chứng sau triển khai |

Mỗi yêu cầu cần có nhóm chịu trách nhiệm. Ví dụ, chặn truy cập trực tiếp có thể thuộc hạ tầng, nhưng việc framework khôi phục scheme hoặc ứng dụng dựng liên kết thuộc các lớp khác. Một file cấu hình ở proxy không đủ chứng minh toàn bộ hợp đồng đã đúng.

### 7.3. Xác định điều gì được phép khi thiếu metadata

Một API công khai có thể tiếp tục xử lý khi không biết chính xác client IP, nếu nó dùng nguồn đếm và kiểm soát khác theo policy. Một thao tác chỉ dành cho đường vào đã xác thực proxy có thể phải bị từ chối hoàn toàn.

Hai hành vi trên đều cần được đặc tả. Không gọi mọi trường hợp thiếu IP là một lý do chung để cho phép hoặc từ chối mà không xét quyết định nào đang phụ thuộc vào IP đó.

Nếu có giá trị fallback, cần ghi nguồn và mức tin cậy. Địa chỉ peer quan sát được có thể là dữ liệu thật về kết nối hiện tại, nhưng không được đổi nhãn thành địa chỉ người dùng cuối nếu chưa có căn cứ.

## 8. Tích hợp với ứng dụng Java

### 8.1. Chuẩn hóa một lần trước những thành phần phụ thuộc

Một luồng tích hợp có thể là:

```text
Nhận kết nối và giữ thông tin peer gốc
    → xác nhận listener/peer thuộc hợp đồng
    → phân tích metadata theo đúng định dạng được chọn
    → áp dụng thuật toán topology và kiểm tra authority/scheme
    → tạo request context kèm nguồn gốc
    → chạy các thành phần cần context đã xác minh
    → kiểm tra quyền nghiệp vụ và xử lý request
```

Context nên phân biệt trường quan sát trực tiếp với trường được proxy khẳng định và trường được suy ra. Không để mỗi bộ lọc hoặc controller tự đọc raw header rồi tính lại theo một quy tắc khác.

Trong Spring, `ForwardedHeaderFilter` có thể khôi phục các thuộc tính request từ header, còn chế độ `removeOnly` chỉ loại bỏ mà không sử dụng chúng. Các chức năng này không tự thay cho việc thiết lập ranh giới tin cậy ở hạ tầng và ở điểm vào. Cần đối chiếu API và thứ tự filter của phiên bản đang triển khai. [Spring Framework: ForwardedHeaderFilter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/ForwardedHeaderFilter.html)

### 8.2. Giảm phụ thuộc vào host tự khai khi tạo liên kết nhạy cảm

Một cách giảm rủi ro là tạo liên kết bảo mật từ public origin đã cấu hình, thay vì dùng `Host` hoặc forwarded host chưa được kiểm chứng.

Ví dụ Java dưới đây tạo liên kết xem xét yêu cầu bảo mật. Nó chỉ minh họa nguồn origin, không cấp quyền truy cập tài nguyên cho người mở liên kết:

```java
import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Objects;

public final class RequirementLinks {

    private static final URI PUBLIC_ORIGIN =
            URI.create("https://portal.example.test");

    private RequirementLinks() {
    }

    public static URI reviewLink(String requirementId) {
        String value = Objects.requireNonNull(requirementId, "requirementId");
        String encoded = URLEncoder.encode(value, StandardCharsets.UTF_8);

        return PUBLIC_ORIGIN.resolve("/requirements/review?id=" + encoded);
    }
}
```

Origin trong ví dụ là hằng số minh họa từ cấu hình được kiểm soát. Request có forwarded host khác không làm đổi đích của liên kết. Giá trị ID được đưa vào vị trí tham số query bằng cách biểu diễn phù hợp cho tham số đó.

Trong hệ thống nhiều tenant có domain riêng, có thể lấy origin từ registry đã được quản lý và ánh xạ tenant đã xác minh. Không thay registry bằng giá trị domain mà caller tùy ý gửi trong cùng request.

### 8.3. Giữ độc lập các mục tiêu khác

Liên kết tới đúng origin vẫn cần authorization khi tài nguyên được mở. Cấu hình origin đúng cũng không xác nhận client IP, không bảo vệ mọi redirect và không chứng minh đoạn backend có TLS.

Đối với cookie hoặc callback xác thực, cần có yêu cầu riêng cho đích, thuộc tính cookie và nguồn scheme/host được sử dụng. Không dùng một kết quả như `isSecure()` mà không biết framework đã tính thuộc tính đó từ kết nối thật hay metadata proxy.

## 9. Tính nhất quán giữa các lớp xử lý HTTP

### 9.1. Không chỉ có ranh giới tin cậy của header

Proxy và backend có thể hiểu khác nhau về path, method, cách rewrite hoặc ranh giới request. Khi một lớp áp dụng kiểm soát trên một biểu diễn còn lớp sau thực thi trên biểu diễn khác, kiểm soát ở lớp trước có thể không bảo vệ đúng thao tác sau cùng.

RFC 9112 mô tả request smuggling là hệ quả của khác biệt phân tích giao thức giữa các bên nhận. Bài này không đi vào cách tạo các request đó, nhưng yêu cầu proxy/backend cần xem tính nhất quán phân tích cú pháp là một phần của ranh giới. [RFC 9112, mục 11.2](https://www.rfc-editor.org/rfc/rfc9112.html#section-11.2)

### 9.2. Đặc tả các phép biến đổi hợp lệ

Nếu proxy bỏ prefix công khai hoặc đổi host thành tên dịch vụ nội bộ, cần mô tả phép biến đổi và những thành phần được quyền áp dụng. Header về path hoặc prefix gốc không được trở thành cách caller chỉ định một tuyến được bảo vệ khác.

Các điều kiện truy cập nên được đối chiếu với hành động và tài nguyên mà backend thực sự xử lý. Một ACL theo chuỗi URL ở gateway không thay kiểm tra quyền nghiệp vụ của action sau routing.

### 9.3. Kiểm soát mâu thuẫn và tài nguyên parser

Hợp đồng nên xác định cách xử lý header lặp, chuỗi quá dài, số hop vượt giới hạn, IPv4/IPv6 và giá trị không thể diễn giải thành kiểu dữ liệu cần dùng. Giới hạn phải có lý do vận hành và kiểm chứng, không chỉ để parser không ném exception.

Không tự viết một bộ tách chuỗi đơn giản rồi coi nó hỗ trợ mọi dạng của `Forwarded`. Những yếu tố như quoted value, port hoặc định danh không phải IP cần được xử lý theo định dạng đã chọn.

Với dữ liệu mâu thuẫn liên quan tới quyết định nhạy cảm, policy có thể yêu cầu từ chối hoặc loại bỏ nguồn ngoài hợp đồng. Điều quan trọng là mọi lớp phụ thuộc phải thấy cùng kết quả đã chuẩn hóa, không được một lớp tin `Forwarded` còn lớp khác tin giá trị trái ngược trong `X-Forwarded-*`.

## 10. Ma trận nghiệm thu

### 10.1. Tách kiểm tra cấu hình, nguồn và tác động

Bằng chứng nên có ba phần: cấu hình cho biết ai được tin, quan sát xác nhận request thực tế đi qua đâu và kết quả chứng minh quyết định bảo mật không bị metadata tự khai thay đổi.

Một log hiển thị client IP đúng trong request bình thường chưa chứng minh chống giả mạo. Một firewall chặn truy cập trực tiếp cũng chưa chứng minh edge đã loại bỏ các header từ client.

| Tình huống | Kỳ vọng theo hợp đồng mẫu | Điều cần quan sát |
| --- | --- | --- |
| Request qua đúng E và L, metadata hợp lệ | Khôi phục đúng context | Peer gốc, chain, scheme/host và kết quả suy ra |
| Client gửi XFF giả trước khi tới E | Không điều khiển được client IP đã xác minh | Giá trị sau điểm làm sạch và khóa rate limit/audit tương ứng |
| Client gửi cả Forwarded và X-Forwarded-* mâu thuẫn | Không có hai ngữ cảnh bảo mật trái ngược | Context tại các thành phần phụ thuộc |
| Client tự gửi user/role/tenant nội bộ | Không được cấp quyền từ các trường đó | Danh tính thực tế và kết quả authorization |
| Nguồn không được phép gọi trực tiếp backend | Bị chặn theo policy đường vào | Lớp mạng hoặc xác thực peer và việc không tạo tác động nghiệp vụ |
| Peer có chứng chỉ hợp lệ nhưng không thuộc danh tính proxy được phép | Không được coi là proxy có thẩm quyền | Định danh certificate và quyết định của listener |
| Header cần thiết thiếu hoặc sai định dạng | Theo nhánh lỗi/fallback đã đặc tả | Không xuất hiện giá trị localhost hoặc quyền nội bộ tự gán |
| Host ngoài danh mục hoặc forwarded host giả | Không đổi route hoặc origin nhạy cảm ngoài hợp đồng | Redirect, liên kết và ánh xạ tenant/host |
| Số hop thay đổi hoặc đi qua tuyến ngắn hơn | Không suy ra dữ liệu do caller kiểm soát là dữ liệu đã xác minh | Topology và kết quả thuật toán |
| Request lỗi hoặc async dispatch đi qua đường xử lý khác | Cùng ranh giới nguồn tin cậy có hiệu lực | Context và phản hồi của đường xử lý tương ứng |

Nếu policy chặn ở mạng hoặc TLS, không bắt buộc quan sát một HTTP status. Tiêu chí phải kiểm tra đúng lớp được thiết kế để từ chối request.

### 10.2. Kịch bản chống giả mạo địa chỉ

```text
Given:
  Client C tới ứng dụng theo đường E → L đã được cấu hình.
  Rate limit hoặc audit sử dụng địa chỉ client từ context đã xác minh.
  E trực tiếp quan sát địa chỉ nguồn của C theo mô hình thử nghiệm.

When:
  C gửi các request giống nhau nhưng thay giá trị X-Forwarded-For tự khai.

Then:
  Giá trị tự khai không tạo địa chỉ client đã xác minh mới.
  Các request vẫn thuộc phạm vi đếm hoặc audit đúng theo policy.
  Không có request nào được coi là localhost chỉ vì nội dung header.
  Bằng chứng cho biết E đã tạo gì và L đã chuyển đổi gì.
```

Kịch bản phải cố định những điều kiện mà nó muốn so sánh. Nếu nguồn mạng thật cũng thay đổi, không thể chỉ từ kết quả khác nhau suy ra header đã điều khiển được địa chỉ.

### 10.3. Kịch bản cho origin của liên kết

```text
Given:
  Chức năng tạo liên kết tuyệt đối dùng public origin đã phê duyệt.

When:
  Request gửi Host hoặc forwarded host khác với origin được phép.

Then:
  Request bị từ chối hoặc được xử lý theo ánh xạ đã đặc tả.
  Liên kết, callback hoặc Location không mang origin do caller tùy chọn.
  Không có dữ liệu nhạy cảm được gửi tới một host ngoài hợp đồng.
```

Trường hợp host backend nội bộ do proxy rewrite hợp lệ cần có đối chứng. Nếu không phân biệt phép rewrite chủ động với giả mạo, bộ kiểm chứng có thể từ chối cả request hợp lệ hoặc bỏ sót một ánh xạ sai.

### 10.4. Kiểm chứng mọi đường vào được phép

Cần bao phủ các listener, IPv4/IPv6, vùng triển khai, đường từ CDN và các tuyến dự phòng thuộc phạm vi. Danh sách có thể được chọn theo kiến trúc, nhưng phải có căn cứ cho phần nào được đại diện bằng cùng một kiểm chứng.

Chỉ kiểm tra hostname công khai không phát hiện được một địa chỉ backend vẫn mở ngoài ý muốn. Ngược lại, chỉ chặn backend từ Internet không phát hiện được một workload nội bộ không có quyền nhưng vẫn nằm trong CIDR được tin quá rộng.

## 11. Quan sát vận hành và vòng đời cấu hình

### 11.1. Ghi được nguồn gốc, không chỉ giá trị cuối

Audit có thể cần peer trực tiếp hoặc danh tính proxy, client IP suy ra, policy/phiên bản cấu hình và mã lý do khi metadata không được chấp nhận. Các trường nên có tên phản ánh rõ nguồn, thay vì tất cả đều mang nhãn chung là client.

Không ghi nguyên secret, token hoặc dữ liệu chứng chỉ nhạy cảm vào log để chứng minh đường proxy. Raw header từ nguồn không tin cũng cần giới hạn độ dài và được biểu diễn an toàn để tránh làm sai cấu trúc log.

Thông tin chuỗi proxy có thể tiết lộ cấu trúc mạng và dữ liệu cá nhân. Không phản chiếu nguyên chuỗi ra response cho client nếu không có nhu cầu được phê duyệt. [RFC 7239, mục 8.2–8.3](https://www.rfc-editor.org/rfc/rfc7239.html#section-8.2)

### 11.2. Thay đổi topology là thay đổi bảo mật

Thêm một CDN, bỏ một load balancer, thay TLS terminator hoặc chuyển sang một mesh có thể làm thay đổi số hop, nguồn kết nối quan sát được và metadata được tạo ở từng đoạn.

Mỗi thay đổi cần cập nhật danh sách peer, hợp đồng trường dữ liệu và tiêu chí nghiệm thu. Một cấu hình số hop từng đúng không tự đúng sau khi rollout sang topology khác.

### 11.3. Rollback không được mở rộng tin cậy vô hạn

Khi có lỗi cấu hình, cần rollback về một trạng thái đã được phê duyệt và kiểm chứng. Không sửa nhanh bằng cách tin mọi CIDR, nhận mọi host hoặc chấp nhận header danh tính từ mọi nguồn.

Một ngoại lệ tạm cần có phạm vi và cách kết thúc. Nếu không giữ được điều kiện bắt buộc cho thao tác nhạy cảm, hành vi nên theo nhánh lỗi đã chốt thay vì tự tăng mức tin cậy để khôi phục lưu lượng.

### 11.4. Phân công theo ranh giới thực hiện

| Thành phần | Trách nhiệm điển hình |
| --- | --- |
| Nhóm hạ tầng biên | Xử lý metadata từ ngoài ranh giới, kiểm tra host và xác lập thuộc tính quan sát |
| Nhóm mạng/nền tảng | Giới hạn đường vào và bảo vệ kênh giữa các proxy/backend |
| Nhóm ứng dụng | Chuẩn hóa context đúng thứ tự, kiểm soát nguồn cho URL, audit và các quyết định phụ thuộc |
| Nhóm xác thực/phân quyền | Định nghĩa hợp đồng danh tính được chuyển tiếp và giữ quyền nghiệp vụ độc lập |
| Nhóm kiểm chứng | Xác nhận giả mạo không thay đổi quyết định, đồng thời bao phủ topology thực tế |

## 12. Những sai lầm cần tránh

### 12.1. Tin mọi địa chỉ private

Private address mô tả loại địa chỉ mạng, không chứng minh peer có quyền làm proxy hoặc cấp danh tính. Cần ranh giới nhỏ, rõ và gắn với thẩm quyền được giao.

### 12.2. Dùng header để xác nhận chính header

Một trường tự khai “internal”, “trusted” hoặc “admin” không thể tự tạo bằng chứng. Căn cứ phải đến từ kết nối, danh tính hoặc cơ chế được bảo vệ độc lập.

### 12.3. Chọn phần tử đầu XFF vì đó là địa chỉ gốc

Tiền tố có thể do client tự gửi hoặc tới từ phần chuỗi chưa được xác minh. Cần thuật toán theo topology, không chỉ thứ tự nhìn thấy của danh sách.

### 12.4. Bật xử lý forwarded ở nhiều lớp mà không hiểu thứ tự

Container, proxy nội bộ và filter ứng dụng có thể cùng sửa thuộc tính request. Kết quả có thể bị xử lý lại hoặc mất peer gốc. Cần xác định một luồng chuẩn hóa và kiểm chứng context mà các lớp bảo mật thực sự dùng.

### 12.5. Cho rằng gateway đã kiểm tra thì backend không cần authorization

Một ranh giới metadata đúng không cấp quyền đối tượng cho caller. Backend vẫn phải bảo vệ hành động và tài nguyên theo chủ thể đã được nhận diện.

### 12.6. Đánh giá bằng một request có địa chỉ hiển thị đúng

Điều đó mới chứng minh một đường đi bình thường. Bằng chứng cần cả request giả mạo, đường trực tiếp, chuỗi thiếu hop và những trường hợp mâu thuẫn liên quan.

## 13. Hồ sơ yêu cầu mẫu

Một hồ sơ cho listener ứng dụng có thể viết:

```text
Tài sản:
  Tính toàn vẹn của request context dùng cho audit, rate limit, URL và quyền.

Topology:
  Client → E → L → A; mọi tuyến khác có policy độc lập hoặc bị chặn.

Nguồn được tin:
  A chỉ nhận metadata thuộc hợp đồng từ L đã được xác nhận.
  E và L chỉ được phát biểu những trường đã được giao thẩm quyền.
  Danh tính người dùng và quyền nghiệp vụ có hợp đồng riêng.

Xử lý:
  E loại bỏ metadata tự khai ngoài ranh giới và tạo phần chuẩn được phép.
  L chuyển tiếp hoặc bổ sung đúng theo topology đã định nghĩa.
  A giữ peer gốc, xác minh nguồn, phân tích chuỗi và tạo context thống nhất.
  Host/scheme được đối chiếu với ánh xạ cấu hình và mục đích sử dụng.

Nhánh lỗi:
  Thiếu hoặc sai metadata không được tạo quyền nội bộ hay giá trị localhost.
  Đường vào không được phép không được tới thao tác nghiệp vụ được bảo vệ.

Bằng chứng:
  Cấu hình peer/route, request trước và sau proxy, context đã chuẩn hóa,
  thử giả mạo, truy cập trực tiếp, thay topology và tác động thực tế.
```

Proxy trust boundary đáp ứng mục tiêu khi ứng dụng chỉ tin một phát biểu trong đúng phạm vi mà nguồn của nó có thẩm quyền và đã được xác nhận. Yêu cầu bảo mật phải nối được đường kết nối, nguồn metadata, phép chuẩn hóa và quyết định sử dụng dữ liệu, thay vì gắn mức tin cậy cho một header chỉ dựa trên tên của nó.
