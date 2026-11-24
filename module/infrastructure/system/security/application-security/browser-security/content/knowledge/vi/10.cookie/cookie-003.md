# Cookie Domain attribute: phạm vi host và ranh giới tin cậy

## 1. Domain attribute quyết định điều gì?

Cookie là dữ liệu nhỏ mà trình duyệt lưu và tự động gửi kèm các HTTP request phù hợp. Khi server trả header `Set-Cookie`, thuộc tính **`Domain`** có thể xác định host nào được nhận cookie trong những request tiếp theo.

Ví dụ, server tại `https://app.example.com` có thể trả:

```http
Set-Cookie: session=abc123; Domain=example.com; Path=/; Secure; HttpOnly; SameSite=Lax
```

Cookie này có thể được gửi tới `app.example.com`, `api.example.com` và các subdomain phù hợp khác của `example.com`. Nếu bỏ thuộc tính `Domain`, cookie trở thành **host-only cookie**: chỉ được gửi tới đúng host đã thiết lập nó, chẳng hạn `app.example.com`.

Đây là khác biệt quan trọng về bảo mật. Việc đặt `Domain=example.com` chia sẻ cookie với nhiều subdomain, đồng thời mở rộng số hệ thống có thể nhận cookie đó. Nếu một subdomain do nhóm khác, nhà cung cấp bên ngoài hoặc nội dung người dùng quản lý bị chiếm quyền, phạm vi chia sẻ rộng có thể làm tăng nguy cơ đánh cắp, ghi đè hoặc làm nhiễu cookie.

Trong module `SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY`, cần đặt Domain attribute trong đúng bối cảnh: trình duyệt, origin, site, cookie và ứng dụng web. Cookie Domain không thay đổi Same-Origin Policy, không cấp quyền JavaScript đọc dữ liệu và cũng không thay thế xác thực, phân quyền hay phòng vệ CSRF.

### Kết quả học tập

Sau bài này, người học có thể:

1. Phân biệt host-only cookie với domain cookie.
2. Giải thích quy tắc domain-match và xác định host nào nhận cookie.
3. Nhận diện giới hạn của `Domain`: không bao gồm scheme, port hay path.
4. Đánh giá rủi ro khi chia sẻ cookie tới toàn bộ subdomain.
5. Sử dụng prefix `__Host-` và `__Secure-` đúng mục đích.
6. Thiết kế kiểm thử cho public suffix, cookie trùng tên, cookie deletion và các subdomain không cùng mức tin cậy.

## 2. Host-only cookie và domain cookie

### 2.1. Bỏ Domain: cookie chỉ dành cho host thiết lập

Giả sử response được trả từ `https://app.example.com/login`:

```http
Set-Cookie: session=abc123; Path=/; Secure; HttpOnly; SameSite=Lax
```

Do không có `Domain`, browser lưu cookie dưới dạng **host-only**. Cookie được gửi tới host `app.example.com` trong các request phù hợp với Path và các thuộc tính còn lại. Nó không được gửi tới `api.example.com` hay `example.com`.

Đây thường là lựa chọn an toàn hơn cho session cookie: ứng dụng chỉ cấp cookie cho host thực sự cần sử dụng nó.

### 2.2. Có Domain: cookie áp dụng cho domain và subdomain phù hợp

Nếu response từ `app.example.com` trả:

```http
Set-Cookie: session=abc123; Domain=example.com; Path=/; Secure; HttpOnly; SameSite=Lax
```

Browser có thể gửi cookie tới:

- `app.example.com`
- `api.example.com`
- `admin.example.com`
- `v2.api.example.com`

Cookie không tự động được gửi tới một domain khác như `example.net`, và `Domain=example.com` không có nghĩa là mọi website có chứa chuỗi `example.com` đều phù hợp.

### 2.3. So sánh trực tiếp

| Đặc điểm | Host-only cookie | Domain cookie |
| --- | --- | --- |
| Cách tạo | Không khai báo `Domain` | Khai báo `Domain=example.com` |
| Host nhận cookie | Chỉ host đã đặt cookie | Domain được chỉ định và các subdomain phù hợp |
| Ví dụ đặt từ `app.example.com` | Chỉ `app.example.com` | `example.com`, `app.example.com`, `api.example.com` và subdomain phù hợp |
| Phạm vi chia sẻ | Hẹp | Rộng hơn |
| Lựa chọn cho session | Ưu tiên khi không cần chia sẻ subdomain | Chỉ dùng khi kiến trúc thực sự cần |

> **Ghi nhớ:** Không có thuộc tính `Domain` không có nghĩa cookie chỉ tồn tại trong một path hoặc một port. Host-only chỉ ràng buộc host; Path và các quy tắc cookie khác vẫn được áp dụng riêng.

## 3. Quy tắc domain-match

Browser xác định một cookie có phù hợp với host của request hay không bằng quy tắc **domain-match**. Với hostname DNS thông thường, host request phù hợp với cookie Domain khi:

1. Host trùng chính xác domain; hoặc
2. Host kết thúc bằng domain và ngay trước phần domain đó có dấu chấm phân cách nhãn.

Ví dụ với cookie `Domain=example.com`:

| Host request | Domain-match? | Giải thích |
| --- | :---: | --- |
| `example.com` | Có | Trùng chính xác |
| `app.example.com` | Có | Subdomain kết thúc bằng `.example.com` |
| `api.example.com` | Có | Subdomain kết thúc bằng `.example.com` |
| `v2.api.example.com` | Có | Subdomain sâu hơn |
| `notexample.com` | Không | Không có ranh giới dấu chấm trước `example.com` |
| `example.com.attacker.test` | Không | Host thực thuộc `attacker.test` |
| `other.example.net` | Không | Domain khác |

Điều kiện dấu chấm rất quan trọng. So khớp bằng `endsWith("example.com")` trong code có thể chấp nhận nhầm `notexample.com`; nếu cần tự kiểm tra domain, phải so sánh chính xác hoặc kiểm tra suffix có ranh giới nhãn DNS.

### 3.1. Domain attribute không thể mở rộng tùy ý

Một server tại `app.example.com` có thể đặt cookie cho `example.com`, vì host hiện tại domain-match domain đó. Server không thể đặt cookie cho một domain không phải chính nó hoặc domain cha hợp lệ:

```http
# Từ app.example.com: domain cha phù hợp
Set-Cookie: a=1; Domain=example.com; Path=/

# Không hợp lệ: domain không liên quan
Set-Cookie: b=1; Domain=attacker.test; Path=/
```

Browser sẽ từ chối cookie có Domain không phù hợp với host response. Một website không thể đặt cookie cho domain của một website khác chỉ bằng cách ghi domain đó vào header.

### 3.2. Dấu chấm đứng đầu không tạo thêm phạm vi

Cách viết cũ:

```http
Set-Cookie: session=abc; Domain=.example.com; Path=/
```

Trong cookie hiện đại, dấu chấm đứng đầu bị bỏ qua; `Domain=.example.com` có cùng ý nghĩa phạm vi với `Domain=example.com`. Không dựa vào dấu chấm để phân biệt cookie host-only và domain cookie. Sự khác biệt được quyết định bởi **có khai báo Domain hay không**.

## 4. Public Suffix List và giới hạn Domain

Một domain có thể là **public suffix**: phần hậu tố mà nhiều người dùng hoặc tổ chức có thể đăng ký riêng, chẳng hạn `com`, `co.uk` hoặc các suffix trong Public Suffix List (PSL). Nếu website bất kỳ được phép đặt cookie cho public suffix, cookie có thể ảnh hưởng tới nhiều website không liên quan.

Ví dụ không được phép dùng:

```http
Set-Cookie: session=abc; Domain=com; Path=/
Set-Cookie: session=abc; Domain=co.uk; Path=/
```

Browser hiện đại thường từ chối cookie Domain trỏ tới public suffix. Có một ngoại lệ xử lý phụ thuộc quy tắc user agent khi domain được khai báo trùng chính xác host của request; không nên dựa vào ngoại lệ đó để thiết kế cookie. Dùng domain đăng ký thực sự của ứng dụng và kiểm thử trên browser mục tiêu.

### Ví dụ với tên miền nhiều tầng

Giả sử:

```text
app.example.co.uk
api.example.co.uk
example.co.uk
co.uk
```

Registrable domain là `example.co.uk`; `co.uk` là public suffix. Cookie `Domain=example.co.uk` có thể chia sẻ cho các subdomain phù hợp. Cookie `Domain=co.uk` bị browser từ chối trong trường hợp thông thường.

Không tự suy luận public suffix bằng cách lấy hai nhãn cuối hostname. Các suffix như `co.uk` và các private suffix được quản lý bởi PSL; quy tắc này cũng là một lý do nên dùng thư viện hoặc browser platform phù hợp khi cần xác định registrable domain.

## 5. Domain không phải Origin và cũng không phải Site

Cookie Domain thường bị nhầm với origin hoặc site. Ba khái niệm trả lời ba câu hỏi khác nhau:

| Khái niệm | Thành phần/ý nghĩa | Câu hỏi |
| --- | --- | --- |
| Origin | Scheme + host + port | JavaScript có cùng origin để truy cập DOM/API không? |
| Schemeful site | Scheme + registrable domain (với quy tắc host đặc biệt) | Request có được xem là same-site hay cross-site? |
| Cookie Domain | Host-only hoặc domain-match | Cookie có phù hợp với host request không? |

Ví dụ:

```text
Frontend: https://app.example.com:443
API:      https://api.example.com:8443

Origin: cross-origin (host và port khác)
Site:   thường same-site (cùng https và example.com)
Cookie: Domain=example.com có thể domain-match cả hai host
```

Cookie không được cô lập theo port. Nếu hai dịch vụ chạy trên `example.com:443` và `example.com:8443`, cookie phù hợp host/path có thể được gửi tới cả hai port. Vì vậy, **không dùng port như ranh giới bảo mật cookie**.

Tương tự, Domain không bao gồm scheme. Cookie có `Secure` được giới hạn gửi qua kết nối an toàn theo quy tắc browser; thuộc tính Secure mới là yếu tố liên quan tới HTTPS. Domain không có nghĩa cookie tự động được gửi qua HTTP và HTTPS như nhau.

## 6. Domain và Path: hai bộ lọc khác nhau

Ví dụ:

```http
Set-Cookie: admin_session=xyz; Domain=example.com; Path=/admin; Secure; HttpOnly
```

Cookie cần thỏa cả domain-match và path-match mới đủ điều kiện gửi:

| Request URL | Domain phù hợp? | Path phù hợp? | Cookie được gửi xét riêng hai điều kiện? |
| --- | :---: | :---: | :---: |
| `https://app.example.com/admin` | Có | Có | Có |
| `https://api.example.com/admin/users` | Có | Có | Có |
| `https://app.example.com/account` | Có | Không | Không |
| `https://other.test/admin` | Không | Có | Không |

Path không phải ranh giới bảo mật mạnh. Các tài liệu cùng host có thể có khả năng tương tác qua nhiều cơ chế browser; Path chủ yếu giúp giới hạn request mà cookie được gửi tới. Không đặt quyền truy cập chỉ dựa trên `Path=/admin`; server vẫn phải xác thực và phân quyền cho từng endpoint.

### 6.1. Path mặc định

Nếu response không khai báo `Path`, browser tính default-path từ request URL đã đặt cookie. Ví dụ response tại `/account/login` có thể tạo cookie với default-path `/account`. Để tránh phụ thuộc vào suy luận này, hãy khai báo Path rõ ràng.

Với session cookie dùng prefix `__Host-`, Path bắt buộc là `/`. Đây là một phần của bảo đảm prefix, không phải vì mọi cookie đều cần Path root.

## 7. Rủi ro bảo mật khi chia sẻ Domain tới nhiều subdomain

### 7.1. Subdomain takeover hoặc subdomain do bên thứ ba quản lý

Giả sử cookie phiên được đặt:

```http
Set-Cookie: session=secret; Domain=example.com; Path=/; Secure; HttpOnly; SameSite=Lax
```

Cookie có thể được gửi tới `legacy.example.com` hoặc `preview.example.com` nếu các host đó domain-match và những điều kiện khác thỏa. Nếu một subdomain bị chiếm quyền, kẻ tấn công có thể nhận các request chứa cookie đến host đó.

`HttpOnly` ngăn JavaScript đọc cookie trực tiếp qua `document.cookie`, nhưng **không ngăn browser gửi cookie tới subdomain phù hợp**. Nếu subdomain bị kiểm soát bởi bên tấn công, server tại đó vẫn có thể nhận header Cookie trong request.

Phòng vệ:

- Dùng host-only cookie cho session nếu ứng dụng không cần chia sẻ phiên giữa các host.
- Không cấp Domain rộng cho subdomain preview, upload, user-generated content hoặc host do nhà cung cấp bên ngoài quản lý.
- Kiểm kê DNS, CNAME và các dịch vụ subdomain; thu hồi record không còn sử dụng.
- Dùng cookie prefix `__Host-` cho session cần ràng buộc vào một host.
- Kiểm tra server-side authentication và rotation session; không dựa vào việc cookie khó đọc từ JavaScript.

### 7.2. Cookie tossing và cookie shadowing

Một subdomain có thể cố đặt cookie cùng tên với cookie của domain cha:

```http
# Từ app.example.com
Set-Cookie: session=legitimate; Domain=example.com; Path=/

# Từ compromised.example.com
Set-Cookie: session=attacker-value; Domain=example.com; Path=/
```

Nếu ứng dụng nhận nhiều cookie cùng tên nhưng khác Domain hoặc Path, header `Cookie` gửi lên server có thể chứa các cặp trùng tên. Header request không gửi lại thuộc tính Domain/Path để server phân biệt nguồn tạo cookie. Framework có thể chọn giá trị đầu, cuối hoặc xử lý khác nhau.

Điều này tạo ra rủi ro **cookie tossing/shadowing**: cookie do một host ít tin cậy đặt có thể gây nhầm lẫn với cookie hợp lệ của ứng dụng. Cách xử lý:

1. Dùng tên cookie riêng, tránh tái sử dụng một tên chung cho nhiều chức năng.
2. Ưu tiên host-only cookie và prefix `__Host-` cho session.
3. Không giả định server luôn chọn đúng giá trị khi header có cookie trùng tên.
4. Kiểm tra và từ chối trường hợp session cookie xuất hiện nhiều lần nếu framework cho phép phát hiện.
5. Không lưu quyền hoặc trạng thái nhạy cảm chỉ trong một cookie không được xác thực.

### 7.3. Same-site không có nghĩa cùng mức tin cậy

`app.example.com` và `marketing.example.com` có thể cùng site, nhưng được vận hành bởi hai nhóm khác nhau. Cookie Domain rộng có thể được gửi đến cả hai; `SameSite=Strict` cũng không ngăn mọi request từ một subdomain cùng site.

Do đó, **SameSite và Domain giải quyết hai khía cạnh khác nhau**:

- Domain xác định host nào có thể nhận cookie.
- SameSite hạn chế cookie theo ngữ cảnh site của request.

Không dùng `SameSite` để thay thế việc giới hạn Domain, cũng không dùng Domain hẹp để thay thế CSRF token.

## 8. Cookie prefix: __Host- và __Secure-

Cookie prefix là quy ước tên mà browser hỗ trợ để áp đặt thêm điều kiện khi chấp nhận cookie. Prefix cần được viết đúng chữ hoa/thường như quy định.

### 8.1. Prefix `__Host-`

Cookie có tên bắt đầu bằng `__Host-` phải thỏa các điều kiện chính:

- Được thiết lập từ secure origin.
- Có thuộc tính `Secure`.
- Có `Path=/`.
- **Không được có thuộc tính `Domain`**.

Ví dụ:

```http
Set-Cookie: __Host-session=opaque-value; Path=/; Secure; HttpOnly; SameSite=Lax
```

Browser hỗ trợ prefix sẽ từ chối cookie `__Host-session` nếu server cố đặt `Domain=example.com` hoặc bỏ `Secure`/Path root. Vì không có Domain, cookie là host-only và subdomain khác không thể đặt cookie cùng tên với prefix hợp lệ để mở rộng phạm vi lên parent domain.

Đây là lựa chọn rất phù hợp cho session cookie khi một host không cần chia sẻ session cookie với subdomain khác.

### 8.2. Prefix `__Secure-`

Cookie có prefix `__Secure-` phải được thiết lập trong secure context và có thuộc tính `Secure`, nhưng vẫn có thể khai báo Domain:

```http
Set-Cookie: __Secure-preference=value; Domain=example.com; Path=/; Secure; SameSite=Lax
```

Vì vậy, `__Secure-` đảm bảo điều kiện Secure nhưng **không ép cookie thành host-only**. Nếu cần ràng buộc host, dùng `__Host-`.

### 8.3. Bảng so sánh

| Đặc điểm | `__Host-` | `__Secure-` |
| --- | --- | --- |
| Secure origin | Bắt buộc | Bắt buộc |
| `Secure` | Bắt buộc | Bắt buộc |
| `Path=/` | Bắt buộc | Không bắt buộc |
| `Domain` | **Không được khai báo** | Có thể khai báo |
| Host-only | Có | Không nhất thiết |
| Mục đích | Bảo vệ cookie gắn với đúng host | Bảo đảm cookie được thiết lập qua secure context |

Không dựa vào prefix nếu trình duyệt mục tiêu không hỗ trợ; vẫn cấu hình đầy đủ thuộc tính cookie và kiểm thử trên browser thực tế. Prefix không thay thế việc xác thực nội dung cookie hoặc bảo vệ session ở server.

## 9. Xóa và thay thế cookie Domain đúng cách

Để xóa cookie, server thường gửi một `Set-Cookie` cùng tên, cùng phạm vi Domain/host-only và Path tương ứng, với thời hạn đã hết:

```http
Set-Cookie: session=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax
```

Nếu cookie ban đầu là domain cookie:

```http
Set-Cookie: preference=; Domain=example.com; Path=/; Max-Age=0; Secure
```

thì khi xóa cần dùng đúng Domain và Path. Cookie host-only và domain cookie có thể cùng tên nhưng có khóa lưu trữ khác nhau khi domain lưu trữ hoặc Path khác nhau; ví dụ host-only cookie của `app.example.com` và domain cookie `Domain=example.com`. Xóa một cookie không nhất thiết xóa cookie kia. Các cookie cùng tên với Path khác nhau cũng có thể cùng tồn tại. Nếu tên, domain lưu trữ và Path trùng nhau, cookie mới có thể thay thế cookie đã lưu.

| Cookie đã tạo | Header xóa cần tương ứng |
| --- | --- |
| Host-only tại `app.example.com`, Path `/` | Không có Domain, Path `/` |
| Domain `example.com`, Path `/` | Domain `example.com`, Path `/` |
| Domain `example.com`, Path `/admin` | Domain `example.com`, Path `/admin` |

Không dùng việc thay đổi Domain để mong xóa tất cả cookie cùng tên trên mọi subdomain. Mỗi cookie có phạm vi riêng và có thể cần thao tác thu hồi tương ứng tại host/domain đã tạo nó. Khi đăng xuất, server nên vô hiệu hóa session ở phía server và xóa cookie phù hợp.

## 10. Kiểm tra Domain attribute trong DevTools

### 10.1. Quan sát cookie

1. Mở ứng dụng qua HTTPS trên một host thử nghiệm mà bạn kiểm soát.
2. Mở DevTools → **Application** (Chrome/Edge) hoặc **Storage** (Firefox).
3. Chọn **Cookies** và host tương ứng.
4. Kiểm tra các cột Name, Domain, Path, Expires/Max-Age, Secure, HttpOnly, SameSite và Partition Key nếu browser hiển thị.
5. So sánh cookie được đặt có Domain với cookie host-only.

Trong một số DevTools, cookie host-only được biểu diễn bằng host không có dấu chấm đầu; domain cookie có thể được biểu diễn khác. Cách hiển thị không phải tiêu chuẩn để code dựa vào. Hãy kiểm tra header `Set-Cookie` và hành vi request thực tế.

### 10.2. Quan sát request

Mở DevTools → **Network**, chọn request tới từng host:

```text
https://app.example.com/
https://api.example.com/
https://legacy.example.com/
https://other.test/
```

Kiểm tra Request Headers → `Cookie`. Cookie host-only của `app.example.com` không nên xuất hiện khi gọi `api.example.com`; cookie Domain `example.com` có thể xuất hiện ở các host phù hợp nếu Path, Secure, SameSite và các điều kiện khác đều cho phép.

Không thể kiểm tra Domain chỉ bằng cách nhìn cookie có được lưu hay không. Cần xem **request đích** để xác nhận browser có thực sự gửi cookie.

## 11. Thực hành: mô phỏng host-only và domain cookie

Thực hành nên chạy trên các hostname thử nghiệm mà bạn quản lý, chẳng hạn:

```text
app.example.test
api.example.test
legacy.example.test
other.test
```

Bạn có thể ánh xạ hostname tới môi trường local bằng DNS/hosts theo quyền quản trị máy. Nếu không có quyền cấu hình hostname, có thể thực hành trên một domain staging riêng đã được cấp; không dùng domain của bên thứ ba.

### 11.1. Đặt hai cookie để so sánh

Từ response của `https://app.example.test`, trả hai header:

```http
Set-Cookie: host_session=host-only; Path=/; Secure; HttpOnly; SameSite=Lax
Set-Cookie: shared_session=domain-wide; Domain=example.test; Path=/; Secure; HttpOnly; SameSite=Lax
```

Kết quả dự kiến khi các điều kiện khác cho phép:

| Request tới | `host_session` | `shared_session` |
| --- | :---: | :---: |
| `app.example.test` | Gửi | Gửi |
| `api.example.test` | Không gửi | Gửi |
| `legacy.example.test` | Không gửi | Gửi |
| `other.test` | Không gửi | Không gửi |

### 11.2. Thử prefix __Host-

Đặt:

```http
Set-Cookie: __Host-session=secure-session; Path=/; Secure; HttpOnly; SameSite=Lax
```

Sau đó thử một response khác:

```http
Set-Cookie: __Host-session=invalid; Domain=example.test; Path=/; Secure; HttpOnly
```

Browser hỗ trợ prefix sẽ từ chối cookie thứ hai vì `__Host-` không cho phép Domain. Kiểm tra Console/Issues và bảng Cookies để xác nhận. Cookie hợp lệ chỉ được gửi tới đúng host đã đặt nó.

### 11.3. Thử cookie trùng tên

Trong môi trường thử nghiệm, tạo hai cookie tên `session`:

```http
Set-Cookie: session=host-value; Path=/; Secure; HttpOnly
Set-Cookie: session=domain-value; Domain=example.test; Path=/; Secure; HttpOnly
```

Quan sát Application/Storage và request header `Cookie`. Browser có thể gửi cả hai cặp tên/giá trị nếu chúng cùng phù hợp. Không dựa vào thứ tự trong header để quyết định cookie nào đáng tin; ứng dụng phải tránh nhập nhằng và dùng prefix phù hợp.

### 11.4. Thử xóa cookie

Xóa từng cookie bằng header có cùng tên, phạm vi Domain/host-only và Path, dùng `Max-Age=0`. Xác nhận cookie đúng biến mất trong Storage và request tiếp theo không còn gửi nó.

## 12. Tình huống thiết kế: nhiều subdomain, một session

Một hệ thống có:

```text
https://app.example.com       Ứng dụng chính
https://api.example.com       API
https://admin.example.com     Quản trị
https://uploads.example.com   Tệp người dùng
https://preview.example.com  Bản xem trước do người dùng tạo
```

Đội phát triển muốn dùng một cookie `session` với `Domain=example.com` để mọi dịch vụ dùng chung phiên. Hãy đánh giá:

1. `uploads` và `preview` có cùng mức tin cậy với ứng dụng chính không?
2. Nếu `preview` hiển thị nội dung do người dùng tạo và có thể bị XSS, cookie Domain rộng có bị gửi tới host đó không?
3. `HttpOnly` có ngăn server của `preview` nhận cookie trong request không?
4. Nếu subdomain bị chiếm quyền, liệu nó có thể đặt cookie cùng tên cho parent domain không?
5. Các service có thực sự cần dùng cùng một cookie, hay có thể dùng token/session riêng và giao tiếp qua API được xác thực?

### Hướng thiết kế

- Session của `app.example.com`: ưu tiên host-only và prefix `__Host-session`.
- API: nếu cần xác thực request, thiết kế cơ chế token/session riêng hoặc luồng cấp quyền có kiểm soát; không mở rộng cookie Domain chỉ để tránh thiết kế authentication.
- Admin: có thể có cookie riêng với chính sách truy cập và vòng đời riêng.
- Upload/preview: cách ly nội dung không tin cậy bằng origin/site riêng khi phù hợp; không gửi cookie ứng dụng tới các host này.
- Mọi endpoint: xác thực, phân quyền, kiểm tra CSRF và validate dữ liệu ở server.

Không phải hệ thống nào cũng cần một cookie dùng chung giữa các subdomain. Việc chia sẻ session làm tăng coupling và phạm vi tác động khi một host bị xâm phạm. Chỉ chọn domain cookie khi yêu cầu sản phẩm thật sự cần và đã đánh giá các subdomain được bao phủ.

## 13. Những nhầm lẫn thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Bỏ Domain nghĩa cookie chỉ dùng cho một path.” | Bỏ Domain tạo host-only cookie; Path là thuộc tính độc lập. |
| “Domain=.example.com chỉ áp dụng cho subdomain, không áp dụng example.com.” | Dấu chấm đầu bị bỏ qua; domain cookie phù hợp cả domain và subdomain. |
| “Domain bao gồm port.” | Cookie không được cô lập theo port. |
| “Domain quyết định HTTP hay HTTPS.” | `Secure` mới giới hạn cookie theo kết nối an toàn; Domain chỉ xác định host phạm vi. |
| “SameSite=Strict ngăn mọi subdomain gửi cookie.” | Subdomain cùng site có thể tạo request same-site; cookie Domain vẫn có thể phù hợp. |
| “HttpOnly ngăn subdomain nhận cookie.” | HttpOnly ngăn JavaScript đọc cookie, không ngăn browser gửi cookie tới host phù hợp. |
| “Cùng origin và cùng cookie Domain là một khái niệm.” | Origin, site và cookie Domain là các ranh giới khác nhau. |
| “Xóa cookie cùng tên là đủ.” | Cần đúng host-only/domain và Path tương ứng; cookie cùng tên có thể tồn tại song song. |
| “Cookie prefix chỉ là quy ước đặt tên.” | Browser hỗ trợ prefix sẽ áp đặt điều kiện khi chấp nhận cookie. |
| “Mọi subdomain đều đáng tin vì cùng registrable domain.” | Subdomain có thể do đội khác hoặc bên thứ ba quản lý, và có mức tin cậy khác nhau. |

## 14. Checklist khi thiết kế Domain attribute

- [ ] Nếu không cần chia sẻ cookie giữa subdomain, bỏ thuộc tính `Domain`.
- [ ] Với session cookie, cân nhắc prefix `__Host-`, `Secure`, `HttpOnly`, `Path=/` và `SameSite` phù hợp.
- [ ] Nếu cần domain cookie, chọn domain hẹp nhất đáp ứng nghiệp vụ.
- [ ] Xác minh Domain domain-match host hiện tại và không phải public suffix.
- [ ] Kiểm kê tất cả subdomain sẽ nhận cookie, gồm preview, upload, marketing, legacy và CNAME bên thứ ba.
- [ ] Không xem port là ranh giới cô lập cookie.
- [ ] Không dựa vào Path để bảo vệ endpoint nhạy cảm.
- [ ] Tránh cookie trùng tên giữa host-only và domain cookie; dùng prefix khi phù hợp.
- [ ] Xóa cookie bằng đúng tên, Domain/host-only và Path đã tạo.
- [ ] Kiểm thử request thực tế trong DevTools trên browser mục tiêu.
- [ ] Server vẫn xác thực, phân quyền và kiểm tra CSRF độc lập.

### Ghi nhớ

**Không khai báo `Domain` tạo host-only cookie; khai báo `Domain=example.com` mở rộng cookie tới domain đó và các subdomain phù hợp.** Phạm vi này không bao gồm scheme, port hoặc thay thế Path. Domain rộng làm tăng số host có thể nhận cookie và có thể tạo rủi ro khi một subdomain bị chiếm quyền hoặc không cùng mức tin cậy. Ưu tiên host-only cho session, dùng `__Host-` khi phù hợp, và chỉ chia sẻ domain cookie khi kiến trúc thật sự cần. Xác thực, phân quyền và CSRF vẫn phải được bảo vệ ở phía server.
