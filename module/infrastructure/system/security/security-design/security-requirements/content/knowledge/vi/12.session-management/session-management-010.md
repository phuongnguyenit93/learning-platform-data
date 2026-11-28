# Cookie Secure

## 1. Thuộc tính Secure bảo vệ điều gì?

`Secure` là thuộc tính của cookie, yêu cầu trình duyệt chỉ gửi cookie qua kết nối được nó coi là an toàn, trong triển khai web thông thường là HTTPS. Với cookie mang thông tin phiên, mục tiêu là ngăn trình duyệt gửi bí mật phiên qua HTTP không được bảo vệ trên đường truyền.

Ví dụ, phản hồi đăng nhập có thể cấp cookie như sau:

```http
Set-Cookie: __Host-session=opaque-session-value; Path=/; Secure; HttpOnly; SameSite=Lax
```

Trong ví dụ này, `Secure` điều khiển điều kiện truyền cookie. Nó không tự mã hóa giá trị cookie, không xác nhận người dùng, không làm cookie vô hình với JavaScript và không ngăn mọi kiểu giả mạo request.

Yêu cầu “cookie phải an toàn” vì vậy chưa đủ cụ thể. Đặc tả cần xác định cookie nào phải có `Secure`, đường cấp nào chịu yêu cầu, nơi quan sát header sau cùng và cách xử lý khi ứng dụng chạy sau proxy hoặc nhiều tầng kết thúc TLS.

Giá trị `opaque-session-value` chỉ là ký hiệu minh họa. Một hệ thống thực tế còn phải tạo, lưu, kiểm tra và thu hồi thông tin phiên theo yêu cầu riêng; việc thêm `Secure` không biến một giá trị dễ đoán thành bí mật phiên an toàn.

## 2. Từ nguy cơ lộ phiên đến yêu cầu kiểm soát

Giả sử trình duyệt có cookie phiên không mang `Secure`. Người dùng đã đăng nhập qua HTTPS nhưng sau đó mở một URL HTTP vẫn khớp phạm vi cookie. Cookie có thể được gửi trong request HTTP trước khi server trả về chuyển hướng sang HTTPS. Chuyển hướng diễn ra sau request đó nên không thể bảo vệ ngược lại thông tin đã truyền.

Với cookie `Secure` và một tên miền triển khai thông thường, trình duyệt không gửi cookie đó trong request HTTP. Đây là điểm bảo vệ trực tiếp của thuộc tính này.

| Nguy cơ | Secure đóng góp gì? | Kiểm soát vẫn cần có |
|---|---|---|
| Cookie bị gửi qua HTTP khớp phạm vi | Hạn chế trình duyệt gửi cookie trên kênh không an toàn | HTTPS, kiểm soát truy cập HTTP và chính sách chống hạ cấp phù hợp |
| JavaScript đọc cookie phiên | Không trực tiếp ngăn | `HttpOnly`, phòng chống chèn mã và kiểm soát phía ứng dụng |
| Request giả mạo từ ngữ cảnh khác | Không trực tiếp ngăn | Chính sách `SameSite` và cơ chế chống giả mạo request thích hợp |
| Cookie có giá trị dễ đoán | Không khắc phục | Sinh bí mật đủ mạnh và quản lý phiên đúng |
| Token bị ghi vào log hoặc URL | Không bảo vệ bản sao đã lộ | Giới hạn nơi chứa bí mật, che dữ liệu và kiểm soát log |
| Máy người dùng hoặc tiện ích trình duyệt bị kiểm soát | Không cung cấp bảo vệ toàn diện | Các kiểm soát thiết bị và xác thực theo mức rủi ro |
| Phiên đã bị đánh cắp được dùng qua HTTPS | Không phân biệt người dùng hợp lệ với kẻ giữ bí mật | Thu hồi, giới hạn phiên và xác thực lại theo chính sách |

Đây là thuộc tính bảo vệ việc vận chuyển cookie theo hành vi của client hỗ trợ nó. Server vẫn phải từ chối các đường truy cập không được phép và kiểm tra phiên; không được chỉ trông chờ client cư xử đúng.

## 3. Đọc đúng Set-Cookie và Cookie

### 3.1. Secure là cờ, không phải một biến Boolean trong header

Cú pháp thông thường đặt `Secure` như một thuộc tính độc lập:

```http
Set-Cookie: session=opaque-value; Path=/; Secure; HttpOnly
```

Không dùng cách biểu diễn `Secure=false` để diễn đạt rằng cookie không cần bảo vệ. Các tham số cấu hình Boolean của framework là một lớp khác; header phát ra phải dùng đúng ngữ nghĩa cờ mà trình duyệt xử lý.

Mỗi cookie cần được kiểm tra theo header thực tế, không chỉ theo tên một biến cấu hình. Nếu thư viện, proxy hoặc bộ lọc ghi lại header, kết quả sau cùng có thể khác cấu hình ở nơi tạo cookie.

### 3.2. Request không gửi lại các thuộc tính cookie

Khi gửi request, trình duyệt gửi tên và giá trị cookie, không gửi lại các thuộc tính `Secure`, `HttpOnly` hay `SameSite`:

```http
Cookie: __Host-session=opaque-session-value
```

Vì vậy, backend không thể nhìn header `Cookie` rồi khẳng định cookie đã được cấp với `Secure`. Một client tùy ý cũng có thể tự gửi header đó. Bằng chứng cấu hình phải lấy từ các phản hồi cấp cookie và hành vi của client kiểm chứng, còn việc chấp nhận phiên phải do server quyết định.

Nếu một phản hồi cấp nhiều cookie, cần bảo toàn từng header `Set-Cookie`. Không gộp chúng tùy tiện thành một chuỗi phân cách bằng dấu phẩy; cú pháp và cách xử lý cookie khác với một số header danh sách thông thường.

### 3.3. Phân biệt gửi cookie với bảo vệ dữ liệu lưu trữ

`Secure` không quy định cookie phải được mã hóa trên đĩa của thiết bị, cũng không che giá trị khỏi mọi công cụ của người sở hữu trình duyệt. TLS bảo vệ kết nối; thuộc tính `Secure` giúp tránh gửi cookie trên một kết nối không đáp ứng điều kiện đó. Những bản sao trong log, bộ nhớ ứng dụng hoặc công cụ chẩn đoán cần được bảo vệ riêng.

## 4. Kết hợp với phạm vi cookie và các thuộc tính khác

### 4.1. Secure và HttpOnly

Một cookie có `Secure` nhưng không có `HttpOnly` vẫn có thể được JavaScript truy cập khi các điều kiện truy cập cookie khác cho phép. Ngược lại, `HttpOnly` không thay thế `Secure`: ngăn đọc bằng API JavaScript không tự bảo vệ việc gửi cookie qua HTTP.

Cookie phiên không cần cho mã phía client thường nên được đặc tả với cả hai thuộc tính. Tuy nhiên, `HttpOnly` cũng không khiến một lỗ hổng chèn mã trở nên vô hại: mã độc trong trang vẫn có thể gây ra request bằng phiên của người dùng dù không đọc trực tiếp được giá trị cookie.

### 4.2. Secure và SameSite

`SameSite` kiểm soát những ngữ cảnh gửi cookie liên quan đến site, còn `Secure` kiểm soát điều kiện kênh truyền. Không được dùng một thuộc tính để suy ra thuộc tính kia.

Khi sản phẩm cần cookie trong một số luồng khác site, cấu hình phải xét yêu cầu của các trình duyệt được hỗ trợ. Ví dụ, cookie dùng `SameSite=None` trong môi trường trình duyệt hỗ trợ cơ chế này cần được cấu hình với `Secure`; nhưng việc có cả hai thuộc tính vẫn không bảo đảm mọi ngữ cảnh bên thứ ba đều được phép gửi cookie, vì còn chính sách quyền riêng tư và lưu trữ của client.

Không nên bỏ `Secure` để khắc phục một luồng đăng nhập hoặc tích hợp bị lỗi. Cần xác định lỗi đến từ ngữ cảnh gửi cookie, phạm vi tên miền, cấu hình proxy, chính sách trình duyệt hay xử lý callback.

### 4.3. Domain, Path và tiền tố tên cookie

`Secure` không thu hẹp cookie vào đúng một host hoặc một đường dẫn. Nếu đặt `Domain` rộng, cookie có thể được gửi đến nhiều host phù hợp qua HTTPS. Một subdomain không đáng tin vẫn là vấn đề dù kết nối đến nó có TLS.

`Path` điều khiển phạm vi gửi cookie theo đường dẫn, không phải ranh giới phân quyền tin cậy giữa các ứng dụng. Cookie cũng không được cô lập theo cổng như cách nhiều người hình dung về origin: không nên coi hai ứng dụng ở hai cổng trên cùng host là hai kho cookie độc lập.

Các tiền tố tên có thể giúp trình duyệt hỗ trợ chúng áp dụng thêm ràng buộc:

| Tiền tố | Ràng buộc liên quan | Ý nghĩa khi thiết kế |
|---|---|---|
| `__Secure-` | Cookie phải có `Secure` và được cấp từ ngữ cảnh kết nối phù hợp | Bổ sung kiểm tra khi nhận cookie, không tự cấm `Domain` |
| `__Host-` | Có `Secure`, `Path=/`, không có `Domain`, cùng yêu cầu ngữ cảnh cấp phù hợp | Giúp ràng buộc cookie vào host cấp và tránh một số cấu hình phạm vi rộng |

Tiền tố có phân biệt chữ hoa/chữ thường và không tự bổ sung `HttpOnly` hay chính sách `SameSite`. Chúng cũng không tạo cách ly theo cổng. Khả năng kiểm soát từ tiền tố phải được đánh giá trên tập client được hỗ trợ; server không được dùng tên có tiền tố như bằng chứng thay thế kiểm tra phiên.

## 5. HTTPS, chuyển hướng và HSTS

### 5.1. Không cấp phiên trên đường HTTP

Đường đăng nhập, callback xác thực và endpoint cấp hoặc gia hạn cookie phiên cần sử dụng HTTPS theo contract triển khai. Một phản hồi qua HTTP có gắn `Secure` không làm phản hồi đó được mã hóa hoặc biến đường cấp HTTP thành đường an toàn.

Trình duyệt có thể không chấp nhận cookie `Secure` được đặt từ ngữ cảnh không đáp ứng điều kiện bảo mật. Một số môi trường cục bộ có xử lý đặc biệt, nên việc chạy được trên máy phát triển không chứng minh cấu hình công khai là đúng. Yêu cầu và kiểm chứng phải lấy môi trường HTTPS tương ứng với triển khai thực tế làm căn cứ.

Với endpoint HTTP, cần chốt hành vi cụ thể: từ chối, hoặc chuyển hướng đối với những request được phép theo thiết kế. Dù chọn cách nào, không cấp bí mật phiên hoặc xử lý đăng nhập nhạy cảm trên đường HTTP rồi trông chờ chuyển hướng ở bước sau.

### 5.2. HSTS hỗ trợ một mục tiêu khác

HSTS cho client hỗ trợ nó biết rằng host phải được truy cập qua HTTPS theo chính sách đã nhận. Nó có thể giảm nguy cơ client thực hiện truy cập HTTP sau khi chính sách có hiệu lực, nhưng không thay thế việc gắn `Secure` lên từng cookie nhạy cảm.

Phạm vi host, subdomain, thời gian hiệu lực và cơ chế để client biết chính sách trước lần truy cập đầu tiên cần được xem xét riêng. Không giả định mọi client đã biết chính sách chỉ vì server vừa thêm header vào một phản hồi HTTPS.

Không được hứa rằng một chuyển hướng HTTP sang HTTPS tự ngăn lộ cookie đã được cấp sai trước đó. Request HTTP có thể đã rời client trước khi nó nhận bất kỳ phản hồi nào.

## 6. Triển khai sau reverse proxy hoặc load balancer

### 6.1. Phân biệt kết nối ngoài và kết nối nội bộ

Một kiến trúc thường có đường đi:

```text
Trình duyệt -- HTTPS --> proxy kết thúc TLS -- kết nối nội bộ --> ứng dụng
```

Ứng dụng có thể chỉ quan sát kết nối nội bộ và cho rằng request là HTTP. Nếu việc thêm `Secure` phụ thuộc hoàn toàn vào nhận định đó, cookie gửi về trình duyệt có thể thiếu thuộc tính dù người dùng truy cập qua HTTPS.

Yêu cầu cần xác định nơi chịu trách nhiệm quyết định thuộc tính cookie. Với một dịch vụ công khai chỉ hỗ trợ HTTPS, có thể cấu hình cookie phiên luôn mang `Secure` thay vì phụ thuộc vào suy luận từ từng request, đồng thời kiểm soát đúng các đường truy cập ứng dụng.

Nếu ứng dụng sử dụng thông tin giao thức gốc do proxy truyền, chỉ được tin dữ liệu từ proxy đã xác định là tin cậy. Header như `X-Forwarded-Proto` do client tự gửi không được quyết định tính an toàn của đường cấp phiên. Điểm vào cần xử lý header chuyển tiếp theo ranh giới tin cậy đã định và ngăn đường truy cập trực tiếp bỏ qua kiểm soát.

### 6.2. Secure không bảo vệ mọi chặng trong kiến trúc

Thuộc tính `Secure` điều khiển hành vi gửi cookie của trình duyệt, không tự mã hóa kết nối từ proxy đến backend. Nếu cookie đi qua một chặng nội bộ chưa được bảo vệ theo yêu cầu, rủi ro ở chặng đó vẫn tồn tại.

Đặc tả phải nêu yêu cầu bảo vệ và giới hạn tin cậy cho từng chặng xử lý bí mật. Không dùng câu “cookie đã Secure” để kết luận TLS kết thúc ở proxy là đủ cho mọi kiến trúc.

Proxy, gateway và ứng dụng cũng có thể cùng sửa `Set-Cookie`. Cần tránh nhiều tầng áp dụng quy tắc mâu thuẫn, làm mất thuộc tính hoặc tạo thêm cookie cùng tên. Bằng chứng kiểm chứng phải quan sát header thực tế ra khỏi điểm phục vụ client, đồng thời xác định tầng nào tạo thay đổi nếu có sai lệch.

## 7. Bao phủ toàn bộ vòng đời cookie phiên

### 7.1. Những đường cấp dễ bị bỏ sót

Một cấu hình đúng ở trang đăng nhập không bảo đảm mọi đường khác đều đúng. Danh mục đường cấp hoặc thay thế cookie cần xét:

- Đăng nhập bằng thông tin xác thực tại ứng dụng.
- Callback từ hệ thống cung cấp danh tính.
- Hoàn tất xác thực nhiều yếu tố hoặc nâng mức bảo đảm.
- Gia hạn phiên và quay vòng ID phiên.
- Khôi phục tài khoản khi luồng đó tạo một phiên được xác thực.
- Cơ chế ghi nhớ đăng nhập hoặc cookie làm mới có khả năng tạo phiên mới.
- Các luồng quản trị hoặc hỗ trợ được phép tạo phiên thay mặt theo chính sách.
- Trang lỗi, chuyển hướng hoặc middleware có thể tạo lại cookie tự động.

Phải phân loại theo khả năng cấp quyền thực tế. Một cookie không tên là `session` nhưng có thể đổi lấy phiên vẫn cần được bảo vệ như thông tin xác thực tương ứng.

### 7.2. Không để lần gia hạn làm mất Secure

Mỗi phản hồi cấp lại cookie cần giữ các thuộc tính bắt buộc. Không được giả định rằng một thuộc tính từng được đặt sẽ tự được giữ nếu ứng dụng phát ra một lệnh `Set-Cookie` mới không mang nó.

Ví dụ cần tránh:

```http
Set-Cookie: session=new-opaque-value; Path=/; HttpOnly
```

Nếu đây là cookie phiên trong môi trường công khai yêu cầu HTTPS, phản hồi trên thiếu `Secure`, bất kể phản hồi đăng nhập ban đầu đã có thuộc tính này.

### 7.3. Xóa và xử lý cookie cũ

Việc xóa cookie ở client cần khớp phạm vi nhận diện cookie đã cấp, đặc biệt là tên, host hoặc `Domain` và `Path`. Nếu có nhiều cookie cùng tên ở phạm vi khác nhau, xóa một cookie không đồng nghĩa tất cả bản còn lại đã biến mất.

Ví dụ hết hạn cookie dùng tiền tố `__Host-` qua phản hồi HTTPS:

```http
Set-Cookie: __Host-session=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax
```

Đồng thời, server cần vô hiệu hóa phiên theo yêu cầu đăng xuất. Xóa cookie phía client không thu hồi một bản sao giá trị phiên mà người khác đã giữ.

Nếu hệ thống từng cấp cookie thiếu `Secure`, kế hoạch chuyển đổi cần kiểm kê phạm vi cũ, đặt lại hoặc xóa đúng cookie và quyết định có thu hồi phiên cũ hay không theo rủi ro. Chỉ bật cấu hình mới không làm mọi bản cookie đã cấp được sửa ngay lập tức, cũng không thu hồi bí mật có thể đã lộ.

## 8. Viết yêu cầu có thể kiểm chứng

Các yêu cầu sau minh họa cách chuyển mục tiêu “bảo vệ cookie phiên khi truyền” thành hành vi có thể quan sát. Tên cookie và phạm vi cần được thay bằng danh mục thật của hệ thống.

| ID | Yêu cầu mẫu | Bằng chứng hoặc tình huống kiểm chứng dự kiến |
|---|---|---|
| CS-01 | Mọi cookie có thể xác thực phiên hoặc cấp lại phiên trên giao diện web công khai phải có thuộc tính `Secure` trong mọi phản hồi tạo, thay thế hoặc gia hạn. | Kiểm kê cookie và quan sát từng đường cấp qua điểm phục vụ client. |
| CS-02 | Hệ thống chỉ được cấp bí mật phiên trên các đường HTTPS được phép; endpoint HTTP không được tạo phiên xác thực hoặc trả bí mật phiên trong phản hồi. | Gửi request tới đường HTTP và kiểm tra phản hồi cùng trạng thái phiên tại server. |
| CS-03 | Trên tập trình duyệt được hỗ trợ với tên miền kiểm chứng thông thường, cookie phiên `Secure` không được xuất hiện trong request HTTP khớp phạm vi. | Cấp cookie qua HTTPS rồi quan sát request HTTP bằng dữ liệu và phiên thử nghiệm. |
| CS-04 | Cookie phiên không cần cho JavaScript phải có cả `Secure` và `HttpOnly`; chính sách `SameSite` phải được xác định riêng theo luồng nghiệp vụ. | Kiểm tra header cuối cùng và thử các luồng truy cập thuộc phạm vi hỗ trợ. |
| CS-05 | Cookie phiên chỉ dùng tại một host không được có `Domain` rộng nếu chưa có yêu cầu chia sẻ được phê duyệt; cấu hình `__Host-` phải đáp ứng các ràng buộc tương ứng. | Quan sát header, kho cookie của client và các request tới host hoặc subdomain khác. |
| CS-06 | Header giao thức chuyển tiếp từ một nguồn không tin cậy không được khiến hệ thống cấp cookie với chính sách khác hoặc chấp nhận đường cấp không được phép. | Gửi header giao thức giả qua điểm vào công khai và thử đường truy cập trực tiếp nằm trong phạm vi kiểm chứng. |
| CS-07 | Mọi lần quay vòng phiên và callback xác thực phải giữ nguyên các thuộc tính cookie bắt buộc. | So sánh header trước và sau đăng nhập liên kết, xác thực nhiều yếu tố và gia hạn. |
| CS-08 | Khi đăng xuất, hệ thống phải vô hiệu hóa phiên phía server và phát lệnh hết hạn cookie đúng phạm vi qua HTTPS. | Phát lại giá trị phiên thử nghiệm cũ và kiểm tra các cookie ở những phạm vi đã cấp. |
| CS-09 | Hệ thống phải phát hiện cookie phiên cùng tên có phạm vi khác nhau gây nhập nhằng; cách xử lý không được phụ thuộc vào việc tùy tiện chọn giá trị đầu tiên. | Tạo các cookie thử nghiệm trùng tên nhưng khác host hoặc path phù hợp tình huống đã định. |
| CS-10 | Log và bằng chứng vận hành không được ghi nguyên giá trị cookie xác thực, dù cookie đó có `Secure`. | Kiểm tra dữ liệu ghi nhận ở ứng dụng, proxy và công cụ quan sát bằng phiên thử nghiệm. |

CS-03 kiểm tra hành vi client hỗ trợ, còn CS-02 và các kiểm tra phiên phía server kiểm soát đường truy cập hệ thống. Một client tùy chỉnh cố ý gửi cookie qua HTTP không chứng minh trình duyệt vi phạm thuộc tính, nhưng là lý do server vẫn phải có chính sách xử lý HTTP rõ ràng.

Không nên lấy kết quả của một endpoint hoặc một trình duyệt làm bằng chứng toàn hệ thống nếu có nhiều đường cấp, nhiều miền hoặc nhiều loại client thuộc phạm vi hỗ trợ.

## 9. Ví dụ: cổng quản trị sau proxy

Một cổng quản trị chỉ phục vụ ở `https://admin.example.test`. Proxy kết thúc TLS và chuyển request đến ứng dụng. Cookie phiên không cần chia sẻ sang host khác và không cần JavaScript đọc trực tiếp.

Contract của đường cấp phiên có thể mô tả:

```yaml
cookieName: __Host-admin-session
secure: true
httpOnly: true
path: /
domainAttribute: OMIT
sameSite: Lax
publicTransport: HTTPS_ONLY
forwardedMetadataPolicy: TRUST_CONFIGURED_PROXY_ONLY
sessionLifecycle:
  preserveCookieAttributesOnRotation: true
  invalidateServerSessionOnLogout: true
```

Đây là cấu hình minh họa yêu cầu, không phải file cấu hình sẵn dùng cho mọi framework. Việc chọn `Lax` còn phải phù hợp các luồng đăng nhập và tích hợp thực tế; không được mặc định mọi ứng dụng đều có cùng yêu cầu ngữ cảnh gửi cookie.

Phản hồi cuối cùng đến trình duyệt:

```http
HTTP/1.1 200 OK
Set-Cookie: __Host-admin-session=opaque-value; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
```

`Cache-Control` minh họa một yêu cầu riêng cho phản hồi chứa dữ liệu nhạy cảm; nó không thay thế `Secure` và không thu hồi dữ liệu đã bị sao chép.

Nếu framework thấy kết nối nội bộ là HTTP, cấu hình công khai vẫn phải phát đúng cookie `Secure`. Nếu một người gửi `X-Forwarded-Proto: http` từ ngoài, header đó không được phép làm cookie phiên mất cờ. Nếu người đó gửi `X-Forwarded-Proto: https` đến một đường HTTP không được phép cấp phiên, nó cũng không được biến đường đó thành đường cấp hợp lệ.

## 10. Tình huống nghiệm thu cần có

Các tình huống dưới đây phục vụ thiết kế triển khai và kiểm chứng sau này, không phải kết quả kiểm thử đã thực hiện.

**Đăng nhập qua HTTPS:** Phản hồi cấp cookie phải có đúng tên, `Secure` và các thuộc tính bắt buộc khác. Kiểm tra cả header thực tế và việc client chấp nhận cookie, không chỉ giao diện báo đăng nhập thành công.

**Truy cập HTTP sau đăng nhập:** Sử dụng tên miền thử nghiệm và dữ liệu không nhạy cảm để quan sát request. Cookie `Secure` không được gửi bởi trình duyệt thuộc phạm vi hỗ trợ; phản hồi HTTP không được cấp một phiên xác thực thay thế.

**Chuyển hướng từ HTTP:** Kiểm tra request ban đầu và phản hồi chuyển hướng tách biệt. Việc đích cuối là HTTPS không được dùng để bỏ qua một cookie thiếu `Secure` đã đi trong request đầu.

**Gia hạn hoặc quay vòng phiên:** Phiên mới phải dùng giá trị phù hợp cơ chế quay vòng và giữ các thuộc tính bảo vệ. Một nhánh gia hạn thiếu cờ phải được coi là không đáp ứng yêu cầu dù đăng nhập ban đầu đúng.

**Đường callback khác:** Hoàn tất đăng nhập liên kết hoặc xác thực bổ sung qua một endpoint khác. Cookie tạo tại nhánh đó cũng phải chịu cùng chính sách, kể cả khi middleware khác chịu trách nhiệm tạo nó.

**Proxy và header giả:** Gửi các header giao thức chuyển tiếp từ nguồn không tin cậy. Thuộc tính cookie và quyết định cho phép cấp phiên không được bị thay đổi trái với contract.

**Cookie trùng tên:** Tạo cookie thử nghiệm cùng tên ở path hoặc phạm vi host khác để xác định cách xử lý. Không kết luận đúng chỉ vì công cụ hiển thị một bản có `Secure` trong khi bản khác vẫn tồn tại.

**Đăng xuất và cookie cũ:** Xác nhận lệnh hết hạn khớp phạm vi cookie đã cấp, rồi thử dùng lại giá trị phiên cũ để kiểm tra thu hồi phía server. Hai mục tiêu này phải được xác nhận độc lập.

**Môi trường cục bộ khác triển khai:** Một kết quả trên host phát triển có xử lý đặc biệt không thay thế kiểm chứng HTTPS ở tên miền đại diện cho môi trường công khai.

## 11. Bằng chứng và lỗi đặc tả thường gặp

Bằng chứng nên ghi endpoint, loại luồng, host, đường đi qua proxy, phiên bản cấu hình, tên cookie, sự hiện diện của các thuộc tính và kết quả hành vi client. Cần che giá trị cookie xác thực; mục tiêu kiểm tra cờ không yêu cầu lưu bí mật phiên nguyên vẹn vào báo cáo.

| Cách hiểu hoặc cách làm | Vấn đề | Cách đặc tả rõ hơn |
|---|---|---|
| “Đã dùng HTTPS nên cookie tự an toàn” | Cookie thiếu `Secure` vẫn có thể bị gửi trong ngữ cảnh HTTP phù hợp | Bắt buộc cờ trên từng cookie nhạy cảm và kiểm tra mọi đường cấp |
| “Secure nghĩa là cookie được mã hóa” | Nhầm điều kiện truyền với mã hóa giá trị hoặc lưu trữ | Nêu vai trò của TLS và các vị trí giữ bản sao bí mật |
| “HttpOnly đã đủ” | Không bảo vệ việc gửi qua HTTP | Áp dụng độc lập hai yêu cầu |
| “Chỉ cần sửa cấu hình ở ứng dụng” | Proxy hoặc nhánh khác có thể thay header | Quan sát phản hồi cuối cùng đến client |
| “Tin mọi header Forwarded” | Client có thể tác động cách ứng dụng hiểu đường truyền | Xác định proxy tin cậy và ngăn đường đi bỏ qua kiểm soát |
| “Bật Secure là hết rủi ro subdomain” | `Domain` rộng vẫn có thể làm cookie đến host không mong muốn qua HTTPS | Thu hẹp phạm vi host và kiểm soát nhu cầu chia sẻ |
| “Cookie đã xóa nên phiên đã thu hồi” | Giá trị phiên bị sao chép vẫn có thể dùng | Vô hiệu hóa phía server và kiểm chứng phát lại |
| “Login đúng là mọi luồng đúng” | Gia hạn, callback hoặc trang lỗi có thể tạo cookie thiếu cờ | Kiểm kê và kiểm chứng toàn bộ vòng đời |

Đặc tả Cookie Secure cần nối được rủi ro truyền bí mật qua kênh không an toàn với header phát ra và hành vi gửi cookie của client. Kết quả chỉ đủ tin cậy khi bao phủ đúng phạm vi cookie, mọi đường cấp và các tầng triển khai thực sự xử lý phiên.
