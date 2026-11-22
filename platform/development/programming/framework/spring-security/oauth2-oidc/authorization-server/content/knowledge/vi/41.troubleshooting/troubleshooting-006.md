# Lỗi issuer, forwarded headers và discovery sau reverse proxy

Spring Authorization Server thường chạy phía sau load balancer, ingress controller hoặc reverse proxy. Ứng dụng có thể nhận request nội bộ qua HTTP và cổng khác, trong khi người dùng truy cập bằng HTTPS trên hostname công khai. Nếu Authorization Server nhận diện nhầm địa chỉ bên ngoài, nó có thể phát hành token với `iss` sai, tạo redirect về hostname nội bộ, công bố `jwks_uri` không truy cập được hoặc trả metadata OIDC khác nhau giữa các instance.

Nhóm lỗi này thường xuất hiện sau khi bật TLS termination, đổi domain, thêm path prefix, chuyển ingress hoặc triển khai nhiều proxy nối tiếp. Cách xử lý hiệu quả là xác định một issuer công khai chuẩn, thiết lập ranh giới tin cậy cho forwarded headers, rồi kiểm tra metadata và token từ đúng điểm nhìn của client bên ngoài.

## 1. Hiểu issuer và địa chỉ bên ngoài

Issuer là định danh của Authorization Server. Ví dụ:

```text
https://identity.example.com
```

Issuer xuất hiện trong metadata OAuth/OIDC và claim `iss` của ID token hoặc JWT access token. Resource Server và OIDC client dùng giá trị này để xác định token được phát hành bởi đúng nhà cung cấp tin cậy. Việc so sánh issuer phải chính xác; không tự chuẩn hóa dấu `/` cuối, đổi hostname alias hoặc chấp nhận issuer gần giống.

Khi chạy sau proxy, một request có thể có hai bộ địa chỉ:

| Góc nhìn | Ví dụ | Ai nhìn thấy? |
|---|---|---|
| Địa chỉ bên ngoài | `https://identity.example.com` | Trình duyệt, OAuth client, OIDC client và Resource Server |
| Địa chỉ nội bộ | `http://authorization-server:8080` | Proxy và ứng dụng trong mạng triển khai |

Ứng dụng thường chỉ nhìn thấy kết nối từ proxy: scheme `http`, host nội bộ và port `8080`. Proxy phải truyền thông tin gốc của request bằng header đã được tin cậy, chẳng hạn `Forwarded` hoặc `X-Forwarded-*`. Framework/container dùng những header đó để dựng lại scheme, host, port và prefix mà client bên ngoài đã sử dụng.

Các header thường gặp:

| Header | Thông tin |
|---|---|
| `Forwarded` | Header chuẩn hóa theo RFC 7239; có thể mang `proto`, `host` và `for` |
| `X-Forwarded-Proto` | Scheme bên ngoài, thường là `https` |
| `X-Forwarded-Host` | Hostname công khai |
| `X-Forwarded-Port` | Port công khai, thường là `443` |
| `X-Forwarded-Prefix` | Path prefix công khai nếu proxy thêm hoặc bỏ prefix khi chuyển tiếp |
| `X-Forwarded-For` | Địa chỉ IP client qua chuỗi proxy; hữu ích cho audit/rate limit nhưng không xác định issuer |

Không nên để `Forwarded` và `X-Forwarded-*` chứa các giá trị mâu thuẫn. Chọn một quy ước thống nhất cho toàn bộ proxy chain và cấu hình Spring để xử lý đúng quy ước đó.

## 2. Triệu chứng thường gặp và nguyên nhân

| Triệu chứng | Nguyên nhân có khả năng cao | Nơi cần kiểm tra |
|---|---|---|
| `iss` trong JWT là `http://authorization-server:8080` | Issuer được suy ra từ request nội bộ hoặc cấu hình sai | `AuthorizationServerSettings`, forwarded headers và proxy |
| Discovery trả `issuer` là HTTP trong khi người dùng truy cập HTTPS | `X-Forwarded-Proto` thiếu, bị ghi đè hoặc không được xử lý | Proxy cuối trước ứng dụng và `server.forward-headers-strategy` |
| Metadata công bố hostname nội bộ hoặc port `8080` | Host/port nội bộ lọt vào URL công khai | `Host`, `X-Forwarded-Host`, `X-Forwarded-Port` |
| Redirect login/callback trỏ đến domain hoặc scheme sai | Request wrapper không phản ánh URL gốc hoặc ứng dụng tự dựng URL | Forwarded headers, context path, redirect handler |
| Discovery endpoint trả 404 | Sai đường dẫn well-known, issuer có path, OIDC chưa bật hoặc proxy rewrite sai | `AuthorizationServerSettings`, endpoint configurer và ingress route |
| OIDC client báo issuer mismatch | Issuer metadata khác `iss` trong ID token hoặc khác issuer đã đăng ký | Metadata công khai, token và cấu hình client |
| `jwks_uri` trỏ về URL nội bộ hoặc không truy cập được | Metadata được tạo từ request sai hoặc proxy không route JWKS endpoint | Discovery response, JWKS endpoint và proxy path |
| Một số request đúng, một số request sai | Các proxy/node gửi header khác nhau hoặc cache metadata cũ | Mỗi hop proxy, cấu hình từng replica và cache của client |

Issuer sai có thể làm toàn bộ OIDC login thất bại dù trang đăng nhập vẫn hiển thị bình thường. Vì vậy, không kết luận hệ thống hoạt động chỉ từ việc `/login` hoặc `/oauth2/authorize` trả về trang HTML.

## 3. Chọn một issuer công khai ổn định

Trong môi trường production, nên khai báo issuer công khai rõ ràng trong `AuthorizationServerSettings`, thay vì để nó thay đổi theo hostname mà từng request gửi đến:

```java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://identity.example.com")
            .build();
}
```

Giá trị trong ví dụ là issuer chuẩn của môi trường. Nếu hệ thống thực sự được publish dưới một path prefix, issuer cần chứa đúng prefix theo thiết kế, ví dụ `https://example.com/identity`. Không thêm prefix chỉ vì ứng dụng nội bộ có `context-path`; phải căn cứ vào URL công khai mà OIDC client và Resource Server dùng để nhận diện issuer.

Tất cả instance của cùng một Authorization Server phải dùng cùng issuer. Không cấu hình issuer theo tên pod, hostname nội bộ, địa chỉ IP, request Host tùy ý hoặc URL của từng node. Nếu có staging và production, mỗi môi trường phải có issuer riêng, metadata và khóa phù hợp với môi trường đó.

Issuer nên được quản lý như cấu hình triển khai:

```yaml
app:
  security:
    authorization-server:
      issuer: https://identity.example.com
```

Sau đó inject giá trị cấu hình vào bean `AuthorizationServerSettings`. Tránh khai báo cùng một issuer ở nhiều nơi như biến môi trường, code và ingress annotation mà không có một nguồn cấu hình chuẩn.

Khai báo issuer tĩnh giúp metadata và claim `iss` nhất quán. Nó không sửa được các URL endpoint khác nếu proxy path, forwarded host hoặc cấu hình endpoint còn sai. Vẫn phải kiểm tra toàn bộ metadata và luồng redirect qua URL công khai.

## 4. Cấu hình forwarded headers trong Spring Boot

Spring Boot có thuộc tính `server.forward-headers-strategy` để chọn cách xử lý forwarded headers. Các giá trị thường dùng:

| Giá trị | Cách xử lý | Khi cân nhắc |
|---|---|---|
| `NONE` | Không xử lý forwarded headers | Ứng dụng không ở sau proxy hoặc proxy không cung cấp header tin cậy |
| `NATIVE` | Dùng hỗ trợ của web server/container | Container có cơ chế xử lý forwarded headers phù hợp với topology |
| `FRAMEWORK` | Dùng cơ chế của Spring Framework, thường qua `ForwardedHeaderFilter` | Cần xử lý header theo cách nhất quán của Spring Framework |

Ví dụ dùng cơ chế framework:

```yaml
server:
  forward-headers-strategy: framework
```

Hoặc nếu container được cấu hình để tự xử lý các header phù hợp:

```yaml
server:
  forward-headers-strategy: native
```

Chỉ chọn một chiến lược theo cách triển khai. Không bật đồng thời cơ chế native của container, tự đăng ký `ForwardedHeaderFilter` và thêm một filter tùy chỉnh cùng sửa scheme/host nếu chưa hiểu thứ tự xử lý. Nhiều lớp cùng rewrite request có thể tạo ra host hoặc prefix bị nhân đôi.

Với ứng dụng Spring không dùng auto-configuration của Boot, có thể đăng ký filter tường minh:

```java
@Bean
ForwardedHeaderFilter forwardedHeaderFilter() {
    return new ForwardedHeaderFilter();
}
```

Chỉ làm như vậy khi ứng dụng chưa có filter tương đương. `ForwardedHeaderFilter` thay đổi cách request được nhìn nhận bởi ứng dụng; nó không tự xác minh proxy nào được tin cậy. Ranh giới tin cậy phải được thiết lập ở mạng và proxy phía trước.

Tên thuộc tính và hành vi container có thể thay đổi theo phiên bản Spring Boot, servlet container và môi trường triển khai. Đối chiếu tài liệu của đúng phiên bản đang chạy, sau đó xác minh bằng request thực tế thay vì chỉ nhìn cấu hình YAML.

## 5. Cấu hình reverse proxy gửi đúng thông tin gốc

Ví dụ Nginx dưới đây giả định Nginx là điểm kết thúc TLS công khai cho hostname `identity.example.com`, sau đó proxy đến ứng dụng nội bộ qua HTTP. Nginx ghi đè các header forwarded bằng giá trị đã xác định ở proxy:

```nginx
server {
    listen 443 ssl;
    server_name identity.example.com;

    location / {
        proxy_pass http://authorization-server:8080;
        proxy_set_header Host identity.example.com;
        proxy_set_header X-Forwarded-Host identity.example.com;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        # Chọn X-Forwarded-* làm quy ước; không chuyển tiếp một
        # Forwarded header do client bên ngoài tự cung cấp.
        proxy_set_header Forwarded "";
    }
}
```

Nếu ứng dụng được publish dưới prefix `/identity` và Nginx giữ nguyên prefix khi proxy, cấu hình route và forwarded prefix phải phản ánh đúng path công khai. Nếu Nginx bỏ prefix trước khi gửi request nội bộ, cần truyền prefix công khai theo cách Spring/container đang dùng hỗ trợ, đồng thời kiểm tra redirect và metadata có prefix đúng một lần. Không thêm `X-Forwarded-Prefix` khi URL bên ngoài không có prefix.

Trong mô hình có load balancer đứng trước Nginx, `$scheme` tại Nginx có thể là `http` dù client đã dùng HTTPS đến load balancer. Khi đó, không được lấy `$scheme` nội bộ làm scheme công khai. Load balancer phải truyền thông tin TLS đã xác thực đến Nginx qua một kênh tin cậy; Nginx chỉ sử dụng thông tin đó sau khi xác định request đến từ load balancer được phép. Không tin header forwarded bất kỳ từ Internet.

Các quy tắc quan trọng:

- Proxy đầu tiên nhận traffic không tin cậy phải xóa hoặc ghi đè `Forwarded` và mọi `X-Forwarded-*` do client gửi lên.
- Chỉ chấp nhận forwarded headers từ proxy nằm trong mạng tin cậy; giới hạn kết nối trực tiếp đến ứng dụng để client không thể bỏ qua proxy.
- Mỗi hop proxy phải có quy ước rõ ràng về việc giữ, nối hay ghi đè header. Không để các node nhận giá trị khác nhau cho cùng một request.
- Host công khai phải được giới hạn bằng virtual host/allowlist. Không phản chiếu một Host header tùy ý thành issuer hoặc redirect URL.
- Chỉ truyền prefix nếu có route prefix thật ở bên ngoài và kiểm tra proxy rewrite có nhất quán.

## 6. Kiểm tra discovery và metadata

Khi OIDC được bật, client thường truy xuất OpenID Provider Configuration qua well-known URI. OAuth Authorization Server Metadata theo RFC 8414 có quy tắc dựng URI well-known riêng. Với issuer không có path, các URL phổ biến là:

```text
Issuer:
https://identity.example.com

OpenID Provider Configuration:
https://identity.example.com/.well-known/openid-configuration

OAuth Authorization Server Metadata:
https://identity.example.com/.well-known/oauth-authorization-server
```

Khi issuer có path, vị trí well-known URI phụ thuộc quy tắc của đặc tả tương ứng. OIDC Discovery đặt `/.well-known/openid-configuration` sau issuer path; RFC 8414 chèn `/.well-known/oauth-authorization-server` giữa authority và path của issuer. Ví dụ với issuer `https://example.com/identity`:

```text
OIDC Discovery:
https://example.com/identity/.well-known/openid-configuration

OAuth Authorization Server Metadata:
https://example.com/.well-known/oauth-authorization-server/identity
```

Không suy ra một URL well-known duy nhất cho cả hai đặc tả. Dùng issuer mà client đã cấu hình và quy tắc discovery của protocol/client tương ứng. Kiểm tra ingress có route đến đúng endpoint sau khi xử lý path prefix.

Lấy metadata từ bên ngoài proxy:

```bash
curl -i https://identity.example.com/.well-known/openid-configuration
```

Nếu ứng dụng bật OAuth Authorization Server Metadata riêng, kiểm tra thêm URI theo RFC 8414. Trong JSON response, đối chiếu ít nhất:

| Trường | Điều cần xác minh |
|---|---|
| `issuer` | Khớp chính xác issuer chuẩn, bao gồm scheme, host, port và path |
| `authorization_endpoint` | Dùng HTTPS và hostname/path công khai |
| `token_endpoint` | Trỏ đến token endpoint công khai, không phải service DNS nội bộ |
| `jwks_uri` | Truy cập được từ client/resource server và trả JWK Set hợp lệ |
| `userinfo_endpoint` | Đúng URL công khai nếu OIDC UserInfo được bật |
| `end_session_endpoint` | Đúng URL công khai nếu provider công bố logout endpoint |
| `response_types_supported` | Phù hợp các response type server thực sự hỗ trợ |
| `grant_types_supported` | Không quảng bá grant mà server chưa cấu hình xử lý |
| `code_challenge_methods_supported` | Có `S256` nếu authorization code + PKCE được hỗ trợ |

Metadata không nên chứa `http://`, hostname container, địa chỉ private, port nội bộ hoặc path bị thiếu/lặp. Các URL phải dùng được từ mạng của client bên ngoài, không chỉ từ trong cluster.

Kiểm tra JWKS riêng:

```bash
curl -i https://identity.example.com/oauth2/jwks
```

Đường dẫn JWKS có thể đã được tùy chỉnh. So sánh `jwks_uri` trong metadata với URL thực tế và kiểm tra response có `keys`, `kid`, `kty`, `use`/`key_ops` phù hợp. Không công bố private key trong JWK Set. Nếu metadata đúng nhưng client vẫn không xác minh được token, kiểm tra `kid`, thuật toán ký, cache JWKS và quá trình xoay khóa.

## 7. Chẩn đoán theo từng loại lỗi

### 7.1. `iss` hoặc metadata dùng HTTP thay vì HTTPS

**Dấu hiệu:** Người dùng truy cập `https://identity.example.com`, nhưng ID token có `iss` là `http://identity.example.com` hoặc metadata công bố HTTP.

**Nguyên nhân thường gặp:** TLS kết thúc ở load balancer, kết nối từ load balancer đến ứng dụng là HTTP, nhưng `X-Forwarded-Proto` không được thiết lập đúng hoặc Spring không xử lý header đó.

**Cách kiểm tra:**

1. Gửi request qua domain công khai và lấy metadata.
2. Kiểm tra `issuer` trong metadata và claim `iss` trong token đã xác minh.
3. Kiểm tra proxy cuối cùng trước ứng dụng có đặt `X-Forwarded-Proto: https` hay `Forwarded: proto=https` không.
4. Xác nhận `server.forward-headers-strategy` đang dùng đúng cơ chế.
5. Kiểm tra proxy trung gian có ghi đè scheme thành `http` hay không.

**Cách sửa:** Cố định issuer công khai trong `AuthorizationServerSettings` và cấu hình proxy gửi scheme gốc đã xác thực. Sau khi sửa, xác minh metadata, authorization redirect và token mới. Token đã phát hành với issuer sai vẫn sai; không thể sửa claim `iss` của token cũ bằng cách thay metadata.

### 7.2. Metadata hoặc redirect chứa hostname nội bộ

**Dấu hiệu:** URL công bố là `http://authorization-server:8080/...`, `http://10.x.x.x/...` hoặc tên service trong Kubernetes.

**Nguyên nhân thường gặp:** Header `Host`/`X-Forwarded-Host` không được proxy đặt, request wrapper dùng host nội bộ, hoặc ứng dụng dựng URL từ cấu hình endpoint nội bộ.

**Cách sửa:** Dùng hostname canonical trong cấu hình issuer và cấu hình proxy ghi đè host công khai. Kiểm tra `authorization_endpoint`, `token_endpoint`, `jwks_uri`, redirect URI và các link trong trang đăng nhập. Không dùng một Host header tùy ý từ client để tạo URL.

### 7.3. Sai port hoặc HTTPS bị chuyển thành HTTP sau một proxy chain

**Dấu hiệu:** Metadata có `:8080`, `:80` hoặc port không khớp với URL người dùng truy cập.

**Nguyên nhân thường gặp:** Proxy không truyền `X-Forwarded-Port`, hoặc proxy ở giữa thêm giá trị port nội bộ. Cũng có thể TLS termination xảy ra ở một hop trước proxy đang ghi header.

**Cách sửa:** Vẽ rõ đường đi của request và xác định hop nào biết scheme/port công khai. Cấu hình hop đó gửi giá trị tin cậy; các hop sau chỉ tiếp nhận từ upstream được xác thực. Nếu issuer tĩnh, bảo đảm endpoint URL trong metadata vẫn dùng authority công khai.

### 7.4. Discovery trả 404 hoặc client không tìm thấy well-known endpoint

**Nguyên nhân có thể:**

- OIDC chưa được bật trong `OAuth2AuthorizationServerConfigurer` nên OpenID Provider Configuration không được công bố.
- Client gọi sai well-known URI hoặc áp dụng sai quy tắc khi issuer chứa path.
- Ingress chỉ route `/oauth2/**` nhưng không route `/.well-known/**`.
- Proxy xóa hoặc thêm path prefix sai số lần.
- Endpoint bị chặn bởi security matcher hoặc một filter chain khác.

**Cách kiểm tra:** Gọi trực tiếp URL well-known theo issuer từ mạng bên ngoài. So sánh cùng request qua ingress và vào service nội bộ. Kiểm tra status, `Location`, `Host`, path thực tế và access log ở proxy. Nếu endpoint nội bộ hoạt động nhưng URL công khai 404, lỗi thường nằm ở route/rewrite của proxy. Nếu cả hai đều 404, kiểm tra OIDC/metadata endpoint configuration và phiên bản thư viện.

### 7.5. `issuer mismatch` ở OIDC client hoặc Resource Server

**Dấu hiệu:** Client từ chối ID token vì issuer không bằng issuer đã dùng để discovery; Resource Server từ chối JWT vì `iss` không khớp cấu hình.

**Cách sửa:** Chọn một issuer chuẩn và dùng chính xác trong `AuthorizationServerSettings`, OIDC client registration và Resource Server validator. Không thêm ngoại lệ chấp nhận cả hostname nội bộ lẫn hostname công khai. Nếu đổi issuer là thay đổi định danh nhà cung cấp, cần kế hoạch migration cho client, validator và token đang còn hạn; metadata mới không làm token cũ tự đổi issuer.

### 7.6. Discovery đúng nhưng redirect URI hoặc callback vẫn sai

Issuer và endpoint metadata không quyết định thay client về `redirect_uri` tùy ý. Redirect URI vẫn phải khớp URI đăng ký của client. Nếu callback bị tạo sai scheme hoặc prefix, kiểm tra forwarded headers, context path và cấu hình redirect URI của client. Không sửa bằng cách nới lỏng redirect URI validation hoặc chấp nhận wildcard domain.

## 8. Kiểm tra forwarded headers mà không làm lộ thông tin

Trong môi trường kiểm thử, có thể ghi log tạm thời các thuộc tính request đã được framework xử lý:

```java
log.debug("External request view: scheme={}, host={}, port={}, contextPath={}",
        request.getScheme(),
        request.getServerName(),
        request.getServerPort(),
        request.getContextPath());
```

Đặt log ở một endpoint chẩn đoán nội bộ được bảo vệ hoặc trong môi trường staging. Không tạo endpoint public phản chiếu toàn bộ header request. Không log cookie, authorization header, token, session ID hoặc giá trị bí mật. Sau khi xác minh, gỡ log chẩn đoán hoặc hạ về mức phù hợp.

Có thể kiểm tra response headers bằng curl:

```bash
curl -sS -D - -o /dev/null https://identity.example.com/.well-known/openid-configuration
```

Để phân biệt lỗi proxy với lỗi ứng dụng, so sánh ba điểm:

1. Request đến hostname công khai qua toàn bộ proxy chain.
2. Request từ mạng nội bộ đến service, với Host và forwarded headers được dựng giống proxy tin cậy.
3. Request trực tiếp đến ứng dụng mà không có forwarded headers, chỉ trong môi trường nội bộ kiểm thử.

Nếu kết quả khác nhau, ghi lại request path và header đã được proxy gửi đi ở từng hop. Không gửi request trực tiếp từ Internet vào port ứng dụng để thử forwarded headers; điều đó có thể bỏ qua ranh giới bảo vệ mà production đang dựa vào.

## 9. Rủi ro bảo mật khi tin forwarded headers

Forwarded headers là dữ liệu do proxy cung cấp, không phải bằng chứng tự thân. Nếu ứng dụng nhận request trực tiếp từ Internet và tin `X-Forwarded-Host` hoặc `Forwarded`, attacker có thể cố thay đổi issuer, link, redirect hoặc thông tin client IP bằng cách gửi header giả.

Các biện pháp cần có:

- Chặn truy cập trực tiếp đến cổng ứng dụng từ mạng không tin cậy; chỉ proxy/ingress được phép kết nối.
- Ở edge proxy, xóa các forwarded headers đến từ client và ghi lại giá trị do proxy xác định.
- Không dùng forwarded host làm issuer nếu chưa kiểm soát host allowlist.
- Giới hạn `server.forward-headers-strategy` cho topology thực tế; không bật chỉ để làm biến mất một lỗi redirect.
- Nếu có nhiều proxy, xác định rõ proxy nào được tin và cách header được nối. Không mặc định mọi phần tử trong `X-Forwarded-For` đều đáng tin.
- Kiểm thử request giả mạo `Forwarded`, `X-Forwarded-Host`, `X-Forwarded-Proto` và `X-Forwarded-Prefix` từ client không tin cậy; kết quả công khai phải vẫn giữ hostname/scheme chuẩn.

Một lỗi cấu hình forwarded headers có thể trở thành lỗ hổng host-header injection hoặc open redirect, không chỉ là lỗi hiển thị URL. Vì vậy, việc bật xử lý header phải đi kèm kiểm soát proxy và network.

## 10. Checklist xác minh sau khi sửa

- [ ] `AuthorizationServerSettings` dùng issuer công khai chuẩn và giống nhau trên mọi instance.
- [ ] Proxy ghi đè forwarded headers do client gửi; ứng dụng chỉ nhận traffic từ proxy tin cậy.
- [ ] Chỉ một chiến lược xử lý forwarded headers được áp dụng phù hợp với container/Boot.
- [ ] Scheme, host, port và path prefix sau xử lý khớp URL công khai.
- [ ] OIDC Discovery và OAuth Authorization Server Metadata được gọi qua domain công khai và trả đúng issuer.
- [ ] `authorization_endpoint`, `token_endpoint`, `jwks_uri` và endpoint OIDC khác dùng URL công khai, HTTPS.
- [ ] Claim `iss` trong ID token/JWT mới khớp chính xác metadata và validator của client/resource server.
- [ ] JWKS endpoint truy cập được, không lộ private key và có `kid` phù hợp token đã ký.
- [ ] Redirect URI vẫn được xác minh chính xác theo client đã đăng ký.
- [ ] Kiểm thử hostname/forwarded header giả mạo không làm thay đổi issuer hoặc redirect.
- [ ] Các instance và proxy trong cùng môi trường cho kết quả metadata nhất quán; cache discovery cũ được làm mới theo kế hoạch.

Khi issuer công khai được cố định, proxy chỉ gửi forwarded headers đã xác thực và discovery được kiểm tra từ phía client bên ngoài, các luồng OIDC có một định danh ổn định dù ứng dụng chạy phía sau nhiều lớp mạng. Hãy coi issuer, forwarded headers và metadata là một cấu hình thống nhất của toàn bộ deployment, không phải ba lỗi độc lập ở từng endpoint.
