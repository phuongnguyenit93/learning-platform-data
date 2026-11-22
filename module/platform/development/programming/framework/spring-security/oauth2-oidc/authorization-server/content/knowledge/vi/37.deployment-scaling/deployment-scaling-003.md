# Tin cậy Forwarded headers từ proxy được phép

Khi Spring Authorization Server chạy phía sau reverse proxy hoặc load balancer, ứng dụng thường nhận kết nối nội bộ qua HTTP dù người dùng truy cập bằng HTTPS. Ứng dụng cũng có thể nhìn thấy tên máy chủ, cổng và đường dẫn nội bộ thay vì địa chỉ công khai. Proxy dùng các HTTP header như Forwarded hoặc X-Forwarded-* để chuyển tiếp thông tin của request bên ngoài.

Các header này ảnh hưởng trực tiếp đến cách Spring dựng URL, xác định request có an toàn hay không và tạo metadata cho OAuth 2.0/OpenID Connect. Nếu ứng dụng tin mọi giá trị được gửi đến, một client có thể giả mạo scheme, host hoặc địa chỉ IP. Hệ quả có thể là URL sai, issuer không nhất quán, cookie thiếu thuộc tính Secure, log sai nguồn truy cập hoặc các quyết định bảo mật dựa trên IP không đáng tin.

Nguyên tắc triển khai là: **chỉ diễn giải forwarded headers sau khi một proxy nằm trong ranh giới tin cậy đã loại bỏ giá trị do client tự gửi và ghi lại giá trị đã xác thực**. Spring có thể đọc các header này, nhưng bản thân bộ lọc không xác thực proxy gửi request.

## 1. Hiểu ranh giới tin cậy

Một topology phổ biến:

~~~text
Trình duyệt
    |
    | HTTPS https://auth.example.com
    v
Reverse proxy / Load balancer
    |
    | HTTP nội bộ, kèm forwarded headers đã chuẩn hóa
    v
Spring Authorization Server
~~~

Proxy có thể kết thúc TLS ở biên mạng rồi chuyển request đến ứng dụng qua HTTP. Vì vậy, nếu chỉ nhìn kết nối socket nội bộ, ứng dụng có thể thấy:

- Scheme là http thay vì https.
- Host là tên service nội bộ thay vì auth.example.com.
- Port là cổng nội bộ thay vì cổng công khai 443.
- Client IP là địa chỉ của proxy thay vì địa chỉ nguồn mà proxy đã quan sát.
- Request URI có thể thiếu prefix công khai nếu proxy ánh xạ một đường dẫn bên ngoài sang context path khác ở backend.

Forwarded headers mô tả lại một phần thông tin bên ngoài. Chúng là dữ liệu trong HTTP request, không phải bằng chứng mật mã rằng request đã đi qua proxy đáng tin. Client có thể tự gửi các header cùng tên nếu proxy không xóa hoặc ghi đè chúng.

### Các header thường gặp

| Header | Ý nghĩa thường dùng | Điểm cần kiểm soát |
|---|---|---|
| Forwarded | Header chuẩn RFC 7239; có thể chứa for, by, host và proto | Proxy phải chuẩn hóa hoặc tạo lại giá trị; chú ý chuỗi nhiều proxy |
| X-Forwarded-For | Địa chỉ client và/hoặc các hop proxy | Không dùng trực tiếp cho quyết định phân quyền nếu chưa xác minh chuỗi proxy |
| X-Forwarded-Host | Host mà client dùng ở phía ngoài | Chỉ chấp nhận host thuộc danh sách domain hợp lệ |
| X-Forwarded-Proto | Scheme bên ngoài, thường là http hoặc https | Phải phản ánh kết nối client đến biên tin cậy |
| X-Forwarded-Port | Port công khai | Phải nhất quán với scheme và host |
| X-Forwarded-Prefix | Prefix đường dẫn công khai được proxy ánh xạ | Chỉ đặt khi có rewrite tương ứng; tránh thêm prefix hai lần |

Không nên để client tự quyết định các giá trị trên. Ví dụ, một request gửi trực tiếp đến proxy có thể mang sẵn X-Forwarded-Host: attacker.example và X-Forwarded-Proto: https. Nếu proxy chuyển nguyên các header này đến ứng dụng, ứng dụng có thể xử lý request như thể nó đến từ domain của kẻ tấn công.

### Điều kiện để tin proxy

Một proxy chỉ được xem là đáng tin khi hệ thống kiểm soát được cả đường đi của request và cách proxy tạo header:

1. Backend chỉ nhận traffic từ proxy hoặc từ các hop nội bộ đã xác định. Dùng private subnet, firewall, security group, Kubernetes NetworkPolicy hoặc cơ chế tương đương để chặn truy cập trực tiếp.
2. Proxy tại ranh giới bên ngoài xóa các Forwarded và X-Forwarded-* do client gửi, sau đó tự tạo lại các giá trị cần thiết.
3. Host bên ngoài được kiểm tra theo danh sách domain được phép. Không dùng Host tùy ý từ request để tạo issuer hoặc URL công khai.
4. Nếu có nhiều proxy, xác định rõ proxy nào được phép thêm thông tin và quy tắc xử lý chuỗi header. Không dựa vào vị trí phần tử đầu tiên hoặc cuối cùng nếu chưa kiểm soát toàn bộ chuỗi.
5. Ứng dụng chỉ bật cơ chế diễn giải forwarded headers khi topology mạng bảo đảm request đến từ proxy đáng tin.

Nếu backend vẫn có thể được gọi trực tiếp từ Internet hoặc từ mạng không kiểm soát, chỉ bật ForwardedHeaderFilter là chưa đủ. Bộ lọc này không cung cấp danh sách IP proxy tin cậy và không tự xác thực nguồn gửi header.

## 2. Spring xử lý forwarded headers như thế nào?

Trong ứng dụng Servlet, Spring Framework cung cấp ForwardedHeaderFilter trong package org.springframework.web.filter. Bộ lọc đọc Forwarded hoặc X-Forwarded-* và bọc HttpServletRequest để các thành phần phía sau nhìn thấy thông tin bên ngoài, chẳng hạn:

- getScheme() trả về scheme công khai.
- isSecure() phản ánh HTTPS bên ngoài.
- getServerName() và getServerPort() phản ánh host và port công khai.
- Các thuộc tính URI và context path có thể được điều chỉnh theo forwarded prefix.

Điều này giúp những thành phần tạo URL hoặc redirect dựa trên request xây dựng địa chỉ phù hợp với góc nhìn của client. Tuy nhiên, bộ lọc không thể biết một header có thực sự do proxy đáng tin tạo ra hay không. Ranh giới tin cậy phải được thiết lập ở proxy và mạng.

### Cấu hình với Spring Boot

Nếu ứng dụng dùng Spring Boot và muốn Spring Framework diễn giải các header, cấu hình:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Giá trị chiến lược thường gặp:

| Giá trị | Cách xử lý |
|---|---|
| none | Không bật xử lý forwarded headers tự động |
| framework | Dùng cơ chế của Spring Framework, thường là ForwardedHeaderFilter |
| native | Dùng cơ chế hỗ trợ của web server hoặc servlet container |

Chọn một cơ chế phù hợp với runtime đang dùng. Với native, hành vi và cấu hình proxy tin cậy phụ thuộc container. Ví dụ, Tomcat có cơ chế RemoteIpValve và các thuộc tính cấu hình riêng. Cần kiểm tra cấu hình của container thay vì giả định rằng mọi runtime xử lý header giống nhau.

Không nên vừa bật xử lý native vừa đăng ký thêm ForwardedHeaderFilter cho cùng một request. Hai lớp cùng diễn giải một header có thể khiến scheme, port hoặc prefix bị thay đổi hai lần. Nếu Spring Boot đã tự đăng ký filter theo cấu hình framework, không đăng ký một filter thứ hai chỉ để lặp lại cùng chức năng.

Trong ứng dụng Servlet không dùng cơ chế tự cấu hình của Spring Boot, có thể đăng ký ForwardedHeaderFilter thủ công. Filter phải chạy trước các filter hoặc thành phần cần đọc scheme, host, port và context path, bao gồm Spring Security filter chain. Cần kiểm tra thứ tự filter thực tế trong ứng dụng thay vì chỉ dựa vào việc bean đã được khai báo.

### Khi chỉ muốn loại bỏ header

Có môi trường không cho phép ứng dụng tin forwarded headers, nhưng vẫn muốn loại bỏ chúng trước khi request đi sâu vào hệ thống. ForwardedHeaderFilter có chế độ remove-only để loại bỏ các header được hỗ trợ mà không dùng chúng để thay đổi request. Cách này hữu ích khi cần ngăn code phía sau vô tình đọc lại header thô.

Dù dùng framework, native hay remove-only, proxy biên vẫn cần lọc và chuẩn hóa header. Đừng coi cấu hình ở ứng dụng là biện pháp thay thế cho kiểm soát ingress.

## 3. Chuẩn hóa header tại reverse proxy

Ví dụ dưới đây minh họa Nginx nhận HTTPS trực tiếp từ client và chuyển request đến Spring Authorization Server qua mạng nội bộ:

~~~nginx
server {
    listen 443 ssl;
    server_name auth.example.com;

    location / {
        proxy_pass http://authorization-server;

        # Host công khai đã được giới hạn bởi server block.
        proxy_set_header Host auth.example.com;

        # Loại bỏ Forwarded do client tự gửi.
        proxy_set_header Forwarded "";

        # Ghi lại các giá trị do proxy kiểm soát.
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Host auth.example.com;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;
    }
}
~~~

Ví dụ này giả định Nginx là điểm tiếp nhận trực tiếp kết nối từ client và server block chỉ phục vụ domain đã nêu. Việc đặt X-Forwarded-For bằng $remote_addr ghi lại địa chỉ mà Nginx quan sát được, thay vì giữ chuỗi do client gửi đến.

Nếu Nginx nằm sau một load balancer, $remote_addr có thể là địa chỉ của load balancer. Chỉ cấu hình cơ chế real IP của Nginx khi đã xác định chính xác CIDR của các load balancer được phép và header mà chúng tạo. Không tin mọi nguồn gửi X-Forwarded-For. Sau khi xác minh hop phía trước, Nginx mới có thể dùng địa chỉ client đã được xác thực để tạo header chuyển tiếp.

Nếu triển khai nhiều domain, có thể cần dùng host theo từng virtual host thay vì chuỗi cố định. Khi đó, cấu hình ingress phải từ chối host không thuộc allowlist và không để một Host tùy ý đi xuyên qua đến ứng dụng. Việc phản chiếu trực tiếp giá trị Host do client cung cấp vào X-Forwarded-Host có thể mở đường cho host header poisoning.

Có thể chọn dùng header chuẩn Forwarded thay cho nhóm X-Forwarded-*. Điều quan trọng là proxy phải tạo giá trị theo một quy tắc nhất quán và ứng dụng phải diễn giải đúng quy tắc đó. Tránh gửi đồng thời hai nhóm header với các giá trị mâu thuẫn.

### Trường hợp có prefix công khai

Giả sử client truy cập https://auth.example.com/auth/... nhưng proxy bỏ prefix /auth trước khi chuyển request đến backend. Nếu ứng dụng cần biết prefix công khai để dựng URL, proxy có thể chuyển X-Forwarded-Prefix: /auth.

Chỉ đặt prefix khi việc rewrite thực sự diễn ra. Nếu proxy giữ nguyên prefix và ứng dụng cũng đã cấu hình context path tương ứng, thêm X-Forwarded-Prefix lần nữa có thể tạo URL dạng /auth/auth/.... Cần kiểm tra request URI, context path và các endpoint sau khi triển khai.

## 4. Cấu hình issuer ổn định cho Authorization Server

Đối với Authorization Server, issuer là định danh quan trọng trong OAuth 2.0 và OpenID Connect. Issuer xuất hiện trong metadata của Authorization Server và OpenID Provider; với token JWT, claim iss cũng phải nhất quán với issuer đã công bố.

Nếu issuer được suy ra từ request hiện tại, một host hoặc scheme bị giả mạo có thể làm máy chủ công bố định danh không mong muốn. Cách phù hợp với một Authorization Server có domain cố định là cấu hình issuer công khai một cách tường minh:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .build();
}
~~~

Đoạn cấu hình này giả định ứng dụng có một issuer công khai cố định. Nếu issuer triển khai dưới một path, chẳng hạn https://auth.example.com/auth, giá trị issuer phải phản ánh chính xác định danh được công bố và phải nhất quán với các endpoint mà client sử dụng.

Khi OIDC được bật, kiểm tra tài liệu discovery tại endpoint tương ứng, ví dụ:

~~~text
https://auth.example.com/.well-known/openid-configuration
~~~

Các URL trong metadata như issuer, authorization_endpoint, token_endpoint và jwks_uri phải trỏ đến địa chỉ công khai có thể truy cập. Nếu cấu hình issuer có path, endpoint discovery cũng phải tuân theo quy tắc well-known URI tương ứng với issuer đó.

Cần phân biệt hai việc:

- Forwarded headers mô tả cách request đến ứng dụng qua proxy, hỗ trợ dựng URL theo góc nhìn bên ngoài.
- AuthorizationServerSettings xác định issuer mà Authorization Server công bố.

Một issuer cố định giúp danh tính máy chủ không phụ thuộc vào Host hoặc X-Forwarded-Host của từng request. Forwarded headers vẫn cần chính xác để ứng dụng xử lý request và URL đúng, nhưng chúng không nên trở thành nguồn tùy ý quyết định issuer.

Với hệ thống đa tenant hoặc nhiều issuer, không nên lấy bất kỳ host nào trong request rồi dùng làm issuer. Hãy ánh xạ host đã được proxy xác thực sang một issuer trong danh sách cho phép. Cơ chế phân giải issuer tùy chỉnh phải từ chối host không biết và phải giữ nhất quán giữa metadata, token và các endpoint của tenant.

### Forwarded headers không thay thế kiểm tra redirect_uri

Khi Authorization Server chuyển trình duyệt về client, redirect_uri phải được kiểm tra theo cấu hình client đã đăng ký. Forwarded headers không làm thay đổi quy tắc khớp redirect_uri và không phải lý do để nới lỏng kiểm tra này.

Không dựng redirect_uri của client từ X-Forwarded-Host. Địa chỉ callback thuộc cấu hình của client, còn issuer là định danh của Authorization Server. Hai giá trị có vai trò khác nhau và cần được quản lý độc lập.

### Ảnh hưởng đến HTTPS và cookie

Khi TLS kết thúc ở proxy, backend có thể nhận kết nối HTTP. Nếu request không được diễn giải đúng là HTTPS, code dựa vào isSecure() có thể tạo URL HTTP hoặc cấu hình cookie phiên thiếu thuộc tính Secure. Trình duyệt có thể từ chối cookie hoặc gửi cookie không theo chính sách mong muốn.

Sau khi cấu hình forwarded headers, hãy kiểm tra response thực tế qua domain công khai, đặc biệt là:

- URL trong redirect và metadata có dùng HTTPS hay không.
- Cookie phiên có thuộc tính Secure khi cần hay không.
- Domain, path và SameSite của cookie có phù hợp với topology và luồng đăng nhập hay không.
- Proxy có giữ nguyên các header bảo mật cần thiết hoặc áp dụng chính sách bảo mật tại edge hay không.

Không dùng một kết quả isSecure() đúng trong unit test để kết luận toàn bộ đường đi TLS đã an toàn. Cần xác minh cả cấu hình TLS tại proxy và khả năng truy cập backend.

## 5. Xử lý nhiều proxy và địa chỉ client

Trong môi trường thực tế, request có thể đi qua CDN, load balancer, ingress controller rồi mới đến ứng dụng. Mỗi hop có thể thêm hoặc thay đổi forwarded headers. Chuỗi header vì thế có thể chứa nhiều địa chỉ và nhiều giá trị.

Hãy xác định rõ:

- Hop nào là điểm tin cậy đầu tiên tiếp nhận traffic từ Internet.
- Hop nào được phép ghi hoặc nối thêm header.
- Header nào được sử dụng làm nguồn thông tin chính.
- Ứng dụng nhận request trực tiếp từ hop nào và mạng có chặn nguồn khác hay không.

Proxy biên nên xóa dữ liệu do client gửi rồi tạo thông tin mới. Các hop phía sau chỉ được nối thêm theo một quy ước đã kiểm soát. Nếu hệ thống cần địa chỉ client thật, phải cấu hình chuỗi proxy tin cậy tại thành phần có trách nhiệm phân giải địa chỉ đó.

Không dùng X-Forwarded-For thô làm căn cứ xác thực người dùng, cấp quyền, bỏ qua MFA hoặc cho phép truy cập endpoint quản trị. Địa chỉ IP có thể hữu ích cho logging, rate limiting hoặc chính sách mạng, nhưng chỉ sau khi hệ thống đã xác định đúng proxy tin cậy và cách chọn địa chỉ trong chuỗi. ForwardedHeaderFilter chủ yếu điều chỉnh góc nhìn của request; nó không thay thế bộ phân giải IP client đáng tin cho các quyết định bảo mật.

## 6. Kiểm thử cấu hình sau triển khai

Kiểm thử cần đi qua đường truy cập công khai và xác minh cả kết quả tích cực lẫn khả năng chống giả mạo.

### Kiểm tra metadata công khai

Gọi endpoint discovery từ bên ngoài:

~~~bash
curl -fsS https://auth.example.com/.well-known/openid-configuration
~~~

Nếu có jq, có thể lọc các trường quan trọng:

~~~bash
curl -fsS https://auth.example.com/.well-known/openid-configuration \
  | jq '{issuer, authorization_endpoint, token_endpoint, jwks_uri}'
~~~

Xác nhận các URL sử dụng scheme và host công khai, issuer khớp với cấu hình AuthorizationServerSettings và JWKS endpoint có thể được client truy cập. Nếu OIDC chưa được bật, dùng endpoint metadata phù hợp với cấu hình hiện tại của Authorization Server.

### Thử header giả mạo từ phía client

Gửi header giả mạo đến domain công khai:

~~~bash
curl -i \
  -H 'X-Forwarded-Host: attacker.example' \
  -H 'X-Forwarded-Proto: http' \
  -H 'Forwarded: host=attacker.example;proto=http' \
  https://auth.example.com/.well-known/openid-configuration
~~~

Proxy biên phải xóa hoặc ghi đè các giá trị này. Metadata trả về vẫn phải dùng issuer và URL công khai hợp lệ của Authorization Server. Nếu giá trị attacker.example xuất hiện trong metadata hoặc redirect, cần kiểm tra lại quy tắc sanitize header, host allowlist và cấu hình xử lý forwarded headers.

### Kiểm tra đường truy cập trực tiếp

Thử truy cập backend từ một mạng không thuộc proxy được phép. Request phải bị chặn ở firewall, security group, ingress hoặc NetworkPolicy. Đây là kiểm tra quan trọng vì một request gọi trực tiếp đến backend có thể tự khai báo X-Forwarded-Proto: https và X-Forwarded-Host: auth.example.com.

### Kiểm tra request và response

Trong môi trường kiểm thử, xác minh ứng dụng nhìn thấy scheme https, host auth.example.com và port 443 khi request đi qua proxy. Đồng thời kiểm tra redirect, cookie phiên, context path và các URL tuyệt đối do ứng dụng tạo ra.

Với nhiều proxy, kiểm thử từng đường đi hợp lệ và thử gửi các chuỗi X-Forwarded-For hoặc Forwarded do client tự tạo. Kết quả phải tuân theo quy tắc đã định nghĩa tại ingress. Không kết luận rằng kiểm thử MockMvc hoặc mock request chứng minh được firewall và proxy đang hoạt động đúng; các kiểm thử đó chỉ xác minh hành vi trong phạm vi ứng dụng.

## 7. Lỗi triển khai thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Bật ForwardedHeaderFilter nhưng backend vẫn truy cập công khai | Client có thể tự gửi header giả mạo | Giới hạn ingress để chỉ proxy được phép gọi backend |
| Proxy giữ nguyên X-Forwarded-* do client gửi | Host, scheme hoặc IP có thể bị giả mạo | Xóa và ghi lại header tại proxy biên |
| Dùng Host tùy ý để tạo issuer | Metadata hoặc định danh token có thể sai | Cấu hình issuer tường minh hoặc ánh xạ host qua allowlist |
| Dùng X-Forwarded-For thô để cấp quyền | Kẻ tấn công có thể giả mạo IP | Chỉ dùng IP sau khi xác minh chuỗi proxy |
| Bật đồng thời native và framework | Request có thể bị diễn giải hai lần | Chọn một cơ chế xử lý |
| Thêm X-Forwarded-Prefix không đúng topology | URL có thể lặp hoặc thiếu path | Đồng bộ proxy rewrite, context path và prefix |
| Tin X-Forwarded-Proto từ mọi nguồn | Request HTTP có thể bị nhận nhầm là HTTPS | Chỉ nhận header đã được proxy tin cậy ghi lại |

## 8. Checklist trước khi đưa vào production

- [ ] Backend chỉ nhận traffic từ proxy hoặc các hop nội bộ đã được cho phép.
- [ ] Proxy biên xóa Forwarded và X-Forwarded-* do client gửi.
- [ ] Proxy tạo lại host, proto, port và thông tin client theo cấu hình đã kiểm soát.
- [ ] Host bên ngoài được giới hạn theo domain hợp lệ.
- [ ] Chuỗi nhiều proxy có quy tắc rõ ràng và đã được kiểm thử.
- [ ] Ứng dụng chỉ dùng một cơ chế xử lý forwarded headers.
- [ ] Filter xử lý forwarded headers chạy trước thành phần cần đọc request URL.
- [ ] AuthorizationServerSettings công bố issuer chính xác và ổn định.
- [ ] Metadata OIDC, endpoint và claim iss nhất quán với issuer.
- [ ] redirect_uri vẫn được kiểm tra theo client đã đăng ký.
- [ ] Cookie và redirect đã được kiểm tra qua HTTPS công khai.
- [ ] Request trực tiếp đến backend và header giả mạo đều được kiểm thử.

Tin cậy forwarded headers là quyết định về ranh giới mạng trước khi là quyết định cấu hình Spring. Khi proxy được giới hạn, header được chuẩn hóa và issuer được cấu hình nhất quán, Spring Authorization Server có thể nhận đúng ngữ cảnh của request bên ngoài mà không để client tùy ý điều khiển danh tính hoặc URL công khai của máy chủ.
