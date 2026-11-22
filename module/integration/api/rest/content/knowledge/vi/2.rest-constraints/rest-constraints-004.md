# Cacheable và khai báo khả năng lưu đệm

## Mục tiêu và phạm vi

Trong chương **Ràng buộc REST** của module **INTEGRATION_API_REST**, bài học này giải thích ràng buộc **cacheable**: thông tin trong response phải giúp các thành phần biết liệu kết quả có thể được lưu đệm và dùng lại hay không. Mục tiêu là giảm trao đổi qua mạng và tải xử lý mà vẫn giữ đúng ý nghĩa của dữ liệu.

Module tập trung vào thiết kế REST API dựa trên resource, URI, phương thức và mã trạng thái HTTP, với hợp đồng dữ liệu rõ ràng. Trong bài này, cache được nhìn từ hợp đồng HTTP giữa client, origin server và các lớp trung gian. Ví dụ dùng sản phẩm công khai và hồ sơ cá nhân; phần Java/Spring minh họa cách công bố chính sách trong response.

Sau bài học, bạn có thể:

- Phân biệt lưu response, dùng lại khi còn fresh và xác minh lại với origin.
- Giải thích đúng `public`, `private`, `no-store`, `no-cache`, `max-age`, `s-maxage` và `must-revalidate`.
- Dùng `ETag`, `Last-Modified` và request có điều kiện để hiểu luồng `304 Not Modified`.
- Nhận ra vai trò của cache key, `Vary`, danh tính người gọi và invalidation.
- Kiểm tra chính sách cache như một phần của hợp đồng API, thay vì xem đó là tùy chọn tối ưu ở cuối dự án.

## 1. Cacheable là một ràng buộc kiến trúc

### 1.1. Vấn đề mà cache giải quyết

Giả sử nhiều client cùng đọc thông tin một sản phẩm:

```http
GET /products/prd-10 HTTP/1.1
Host: api.example.test
Accept: application/json
```

Nếu dữ liệu ít thay đổi, mỗi request đều gọi origin, truy vấn database và truyền lại cùng payload sẽ tốn tài nguyên. Một cache có thể giữ response phù hợp rồi phục vụ request sau, hoặc hỏi origin xem bản đã giữ còn sử dụng được không.

Lợi ích có thể gồm ít lượt gọi origin hơn, giảm độ trễ và giảm lượng dữ liệu truyền. Đánh đổi là client có thể đọc một biểu diễn cũ trong khoảng thời gian mà chính sách cho phép. Nếu thông tin cache không rõ, các bên có thể dùng lại dữ liệu sai hoặc bỏ lỡ cơ hội dùng lại hợp lệ.

Ràng buộc cacheable của REST yêu cầu khả năng cache được xác định, một cách tường minh hoặc ngầm định theo các quy tắc áp dụng. Điều này không có nghĩa mọi response đều phải được cache, và cũng không bắt buộc mỗi response phải có một header tự đặt tên `cacheable`.

Với HTTP API, phương thức, mã trạng thái và các header cache cùng cung cấp thông tin đó. Dù HTTP có quy tắc mặc định và heuristic cho một số trường hợp, khai báo chính sách rõ ràng thường giúp hợp đồng API dễ hiểu và kiểm soát hơn.

### 1.2. Cache HTTP khác cache bên trong ứng dụng

| Loại cache | Ví dụ | Ai trực tiếp sử dụng? |
| --- | --- | --- |
| Cache HTTP riêng | Cache của trình duyệt hoặc HTTP client dành cho một người dùng | Client đó |
| Cache HTTP dùng chung | Reverse proxy, gateway hoặc CDN lưu response để phục vụ nhiều request | Nhiều client theo chính sách của cache |
| Cache dữ liệu trong ứng dụng | Cache kết quả truy vấn hoặc đối tượng bằng bộ nhớ, Redis, Caffeine | Mã xử lý ở phía server |

`Cache-Control` trong response mô tả chính sách cho cache HTTP. Nó không tự bật hoặc tắt Redis, không tự xóa cache truy vấn và không thay thế cấu hình cache của từng thư viện client.

Tương tự, `@Cacheable` trong Spring thường liên quan đến cache kết quả gọi phương thức ở phía ứng dụng. Chỉ thêm annotation đó không công bố chính sách cache HTTP cho trình duyệt hoặc proxy.

### 1.3. Response được cache là một biểu diễn cụ thể

Tài nguyên `/products/prd-10` có thể có nhiều biểu diễn: JSON hoặc định dạng khác, tiếng Việt hoặc tiếng Anh, dữ liệu công khai hoặc dữ liệu gắn với quyền của người gọi.

Cache phải dùng lại đúng biểu diễn cho đúng request. Việc hai request có cùng path chưa đủ chứng minh chúng có thể nhận chung một response.

## 2. Ba quyết định cần tách biệt

Đừng dùng một câu “API này có cache” để thay cho ba câu hỏi sau:

1. **Có được lưu response không?** Chính sách có cho phép cache riêng hoặc cache dùng chung giữ response này không?
2. **Có được dùng lại mà không hỏi origin không?** Bản đã lưu còn fresh và đáp ứng các điều kiện của request hiện tại không?
3. **Nếu phải xác minh lại, xác minh thế nào?** Có validator để hỏi origin mà không cần truyền lại toàn bộ body không?

Ví dụ:

```http
Cache-Control: private, no-cache
ETag: "profile-v7"
```

Cache riêng được phép lưu response, nhưng phải xác minh thành công trước mỗi lần dùng lại theo chỉ thị `no-cache`. Cache dùng chung không được lưu response này do `private`.

Ngược lại:

```http
Cache-Control: no-store
```

yêu cầu cache không lưu response. Đây không phải cùng ý nghĩa với “lưu được, nhưng phải hỏi lại trước khi dùng”.

Việc có được lưu còn phụ thuộc các quy tắc HTTP khác, bao gồm phương thức, mã trạng thái, request liên quan và khả năng của cache. Một header thời gian sống không biến mọi loại response thành response có thể tái sử dụng trong mọi hoàn cảnh.

## 3. Các chỉ thị Cache-Control quan trọng

### 3.1. Phạm vi lưu và điều kiện dùng lại

Bảng dưới nói về các chỉ thị response không kèm danh sách tên field đặc biệt.

| Chỉ thị | Ý nghĩa chính | Điều không được suy ra |
| --- | --- | --- |
| `public` | Cho phép cache dùng chung lưu response khi các quy tắc còn lại cho phép | Không chứng minh body thực sự là dữ liệu công khai; không vô hiệu hóa `no-store` hoặc `private` |
| `private` | Cache dùng chung không được lưu; cache riêng có thể lưu nếu không có ràng buộc khác | Không mã hóa dữ liệu và không tự đặt thời gian fresh |
| `no-store` | Cache không được lưu response này | Không phải lệnh xóa mọi bản cũ đã được lưu trước đó |
| `no-cache` | Có thể lưu, nhưng không được dùng lại nếu chưa xác minh thành công với origin | Không đồng nghĩa với cấm lưu |
| `must-revalidate` | Khi response đã stale, không được tự dùng lại nếu chưa xác minh thành công | Không bắt buộc hỏi origin khi response vẫn fresh |

Một cách nhớ hữu ích:

- `no-store` nói về **lưu**.
- `no-cache` nói về **xác minh trước khi dùng lại**.
- `private` nói về **cache nào được lưu**.
- `must-revalidate` ràng buộc **việc dùng lại sau khi hết freshness**.

`no-store` là chỉ thị dành cho các cache tuân thủ HTTP. Nó không thay thế phân quyền, không điều khiển mọi loại lưu trữ bên ngoài cache HTTP và không tự xóa một response từng được phát với chính sách khác.

### 3.2. Thời gian fresh

| Chỉ thị hoặc header | Vai trò |
| --- | --- |
| `max-age=60` | Đặt thời gian fresh tối đa 60 giây, dựa trên tuổi của response |
| `s-maxage=300` | Đặt thời gian fresh cho cache dùng chung; ở đó nó ưu tiên hơn `max-age` và `Expires` |
| `Expires` | Nêu thời điểm hết freshness theo ngày giờ HTTP; `max-age` có ưu tiên hơn khi cùng xuất hiện |
| `Date` | Thời điểm gắn với việc tạo thông điệp tại origin, dùng trong việc tính tuổi theo quy tắc HTTP |
| `Age` | Thông tin về tuổi response theo cơ chế cache HTTP, giúp bên nhận tính phần freshness còn lại |

Đơn vị của `max-age` và `s-maxage` là giây.

Ví dụ:

```http
Cache-Control: public, max-age=60, s-maxage=300
```

Cache riêng áp dụng thời gian fresh 60 giây; cache dùng chung áp dụng 300 giây. Đây không phải lời hứa rằng mỗi bên nhận luôn có thêm trọn 60 hoặc 300 giây tính từ lúc nhận. Response có thể đã có tuổi khi đến bên nhận.

Một ví dụ khác:

```http
Cache-Control: max-age=0
```

không cấm lưu. Response coi như hết freshness ngay; để kiểm soát chặt việc xác minh trước khi dùng lại, cần hiểu thêm các chỉ thị như `no-cache` hoặc `must-revalidate` thay vì coi `max-age=0` là từ đồng nghĩa của chúng.

### 3.3. Không khai báo Cache-Control có nghĩa gì?

Không có `Cache-Control` không đồng nghĩa với `no-store`. Theo các điều kiện của HTTP, một số response, chẳng hạn một số response `200` hoặc `404`, có thể được cache và áp dụng heuristic freshness.

Vì vậy, một endpoint vừa tạo tài nguyên có thể gặp tình huống khó hiểu: trước đó cache đã giữ `404`, sau khi tạo xong một client vẫn nhận bản `404` cũ. Chính sách đối với response lỗi cũng cần được xem xét, không chỉ response thành công.

Không nên dựa vào suy đoán “client chắc không cache”. Hãy công bố chính sách cho những trường hợp mà hành vi cache ảnh hưởng đến tính đúng đắn của nghiệp vụ.

## 4. Freshness không đồng nghĩa với dữ liệu mới nhất tuyệt đối

### 4.1. Fresh và stale

Một response **fresh** là response còn nằm trong thời gian mà cache được phép dùng lại theo chính sách, với các điều kiện liên quan. Response **stale** đã vượt thời gian đó.

Hai trạng thái này là khái niệm của cache, không phải kết luận tuyệt đối về dữ liệu tại origin:

- Một response còn fresh vẫn có thể khác dữ liệu mới nhất nếu origin vừa cập nhật.
- Một response đã stale vẫn có thể giống hệt dữ liệu hiện tại, nhưng cần được xử lý theo quy tắc xác minh hoặc tái sử dụng stale được phép.

Dạng khái niệm của phép kiểm tra là:

```text
fresh khi current_age < freshness_lifetime
```

HTTP có quy tắc tính tuổi xét thời điểm, truyền thông và thời gian lưu tại cache. Không nên triển khai bằng cách chỉ lấy “bây giờ trừ lúc client cuối nhận body” rồi bỏ qua `Date` và `Age`.

### 4.2. Ví dụ với Age

```http
HTTP/1.1 200 OK
Date: Tue, 17 Nov 2026 03:00:00 GMT
Cache-Control: public, max-age=60
Age: 50
Content-Type: application/json

{"id":"prd-10","name":"Bàn phím"}
```

Nếu bỏ qua phần thời gian truyền thêm để minh họa, response còn khoảng 10 giây freshness, không phải 60 giây mới bắt đầu từ lúc nhận. Một cache trung gian không được làm response “trẻ lại” bằng cách bỏ qua tuổi đã tích lũy.

### 4.3. Chọn thời gian theo nghiệp vụ

| Dữ liệu | Câu hỏi trước khi chọn chính sách |
| --- | --- |
| Danh mục công khai ít thay đổi | Chấp nhận hiển thị thông tin cũ trong bao lâu? |
| Giá hoặc tồn kho để tham khảo | Dữ liệu hiển thị có khác dữ liệu phải kiểm tra khi chốt đơn không? |
| Trạng thái đơn hàng | Client có cần thấy ngay thay đổi vừa thực hiện không? |
| Hồ sơ người dùng | Có được lưu ở client không, và có cần xác minh mỗi lần dùng lại không? |
| Response chứa thông tin cần hạn chế lưu | Có cần chỉ thị `no-store` thay vì chỉ đặt TTL ngắn không? |

TTL phải gắn với cam kết mà API đưa ra. Một bản tồn kho được cache để hiển thị không thể thay cho việc kiểm tra điều kiện giữ hàng tại thời điểm thực hiện nghiệp vụ.

## 5. Validator và xác minh lại với origin

### 5.1. ETag và Last-Modified

**Validator** giúp client hoặc cache hỏi xem biểu diễn đã lưu còn phù hợp hay không.

- `ETag` là một giá trị opaque, tức client không nên tự suy diễn cấu trúc hoặc tính toán ý nghĩa từ chuỗi đó.
- `Last-Modified` cho biết thời điểm sửa đổi theo thông tin server công bố và có thể dùng với điều kiện thời gian.

Ví dụ:

```http
ETag: "prd-10-vi-r7"
Last-Modified: Tue, 17 Nov 2026 02:55:00 GMT
```

ETag có dấu ngoặc kép. Chuỗi này không bắt buộc là hash của database hoặc mã phiên bản theo một định dạng cụ thể. Server phải bảo đảm validator phản ánh đúng biểu diễn mà nó áp dụng.

Một **strong ETag** không có tiền tố `W/` phải đáp ứng điều kiện so sánh mạnh về biểu diễn. Một **weak ETag**, chẳng hạn `W/"prd-10-r7"`, biểu đạt khả năng tương đương theo ngữ nghĩa phù hợp nhưng không hứa body đồng nhất từng byte.

Đừng lấy số phiên bản của một hàng database làm strong ETag nếu response còn chứa dữ liệu khác có thể thay đổi mà số đó không đổi. Ngôn ngữ, định dạng, dữ liệu tổng hợp và quá trình biến đổi biểu diễn cũng cần được xét khi tạo validator.

`Last-Modified` có độ phân giải thời gian giới hạn; nhiều thay đổi trong cùng một giây hoặc việc xác định thời điểm sửa đổi không chính xác có thể làm nó kém phù hợp hơn một ETag được thiết kế đúng.

### 5.2. Luồng conditional GET

Lần đầu client đọc:

```http
GET /products/prd-10 HTTP/1.1
Host: api.example.test
Accept: application/json
Accept-Language: vi
```

Origin trả:

```http
HTTP/1.1 200 OK
Date: Tue, 17 Nov 2026 03:00:00 GMT
Cache-Control: public, max-age=60
ETag: "prd-10-vi-r7"
Vary: Accept-Language
Content-Type: application/json

{"id":"prd-10","name":"Bàn phím"}
```

Sau khi cần xác minh lại, client gửi:

```http
GET /products/prd-10 HTTP/1.1
Host: api.example.test
Accept: application/json
Accept-Language: vi
If-None-Match: "prd-10-vi-r7"
```

Nếu biểu diễn tương ứng vẫn phù hợp với validator:

```http
HTTP/1.1 304 Not Modified
Date: Tue, 17 Nov 2026 03:01:05 GMT
Cache-Control: public, max-age=60
ETag: "prd-10-vi-r7"
Vary: Accept-Language
```

`304` không có response body. Cache dùng body đã lưu, cập nhật metadata theo quy tắc HTTP và quyết định khả năng dùng lại tiếp theo. Ứng dụng dùng HTTP client có hỗ trợ cache có thể nhìn thấy nội dung đã được kết hợp, thay vì trực tiếp xử lý một `304` trống.

Nếu biểu diễn đã đổi, origin trả `200` cùng body và validator mới. Việc có request hỏi origin vẫn phát sinh chi phí mạng và có thể có chi phí xử lý; revalidation thường tiết kiệm truyền body, không nhất thiết loại bỏ toàn bộ truy vấn backend.

### 5.3. Điều kiện và giới hạn

`If-Modified-Since` có thể dùng cùng `Last-Modified`. Khi request có `If-None-Match`, điều kiện đó được ưu tiên; không nên tự ghép các điều kiện theo cách làm một biểu diễn đã đổi bị trả nhầm `304`.

`304 Not Modified` gắn với request đọc có điều kiện như `GET` hoặc `HEAD`; không dùng nó như thông báo chung rằng “mọi thao tác đều không thay đổi gì”.

`If-None-Match` trong luồng đọc dùng quy tắc so sánh phù hợp cho cache, có thể làm việc với weak validator. Đừng đánh đồng với `If-Match` để bảo vệ cập nhật đồng thời: phép so sánh mạnh và hành vi của điều kiện ghi là chủ đề khác.

Validator không phải thông tin xác thực. Server vẫn phải kiểm tra người gọi có quyền nhận biểu diễn trước khi trả dữ liệu hoặc xác nhận điều kiện tương ứng. Một ETag biết được từ trước không cấp quyền đọc tài nguyên.

## 6. Cache key và Vary: chọn đúng bản đã lưu

### 6.1. URI là điểm bắt đầu, chưa luôn là toàn bộ khóa

Một cache HTTP dùng phương thức và URI đích để nhận diện response liên quan, cùng các yếu tố khác theo quy tắc áp dụng. Với API đọc bằng `GET`, URI bao gồm cả query string:

```text
/products?page=1&size=20
/products?page=2&size=20
```

Đây là hai đích khác nhau. Cấu hình cache không được tùy tiện bỏ query parameter nếu chúng làm thay đổi biểu diễn, chẳng hạn trang, bộ lọc hoặc thứ tự sắp xếp.

Host cũng có ý nghĩa. Không thể gộp hai URI của hai tenant hoặc hai origin chỉ vì path giống nhau.

### 6.2. Khi header request làm thay đổi biểu diễn

Giả sử cùng một URI trả tên sản phẩm theo ngôn ngữ:

```http
Vary: Accept-Language
```

Chỉ thị này cho cache biết việc lựa chọn response phụ thuộc vào header `Accept-Language` của request. Một bản tiếng Việt không được tự dùng cho request tiếng Anh chỉ vì URI trùng nhau.

Nếu còn đàm phán theo `Accept`, response có thể cần:

```http
Vary: Accept, Accept-Language
```

Nếu có nén hoặc biến đổi ở một lớp khác, các lớp phải phối hợp để giữ metadata về biến thể nhất quán, chẳng hạn `Vary: Accept-Encoding` khi phù hợp. Không được ghi đè làm mất giá trị `Vary` do lớp trước đã thêm.

`Vary` không đặt TTL và không cấp quyền đọc dữ liệu. Nó chỉ mô tả các chiều header liên quan đến việc chọn biểu diễn. Thêm nhiều chiều không cần thiết có thể phân mảnh cache và giảm tỷ lệ dùng lại.

### 6.3. Validator phải thuộc đúng biến thể

Nếu response tiếng Việt và tiếng Anh khác nội dung, không thể gán cùng một strong ETag rồi coi chúng là cùng một biểu diễn. Khi xác minh, origin phải xác định đúng biến thể trước khi đánh giá validator tương ứng.

Một lỗi điển hình:

```text
Request A: Accept-Language: vi → body tiếng Việt, ETag "r7"
Request B: Accept-Language: en → body tiếng Anh, ETag "r7"
```

Nếu validator được dùng sai và cache key cũng thiếu ngôn ngữ, client có thể nhận nhầm body hoặc một `304` không phù hợp. Cách xử lý là thiết kế thống nhất việc chọn biểu diễn, metadata `Vary` và validator; chỉ sửa một trong ba chưa chắc giải quyết được lỗi.

## 7. Dữ liệu theo người dùng và cache dùng chung

### 7.1. Cùng URI không đồng nghĩa cùng dữ liệu

```http
GET /me HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
```

URI `/me` có thể trả hai hồ sơ khác nhau tùy người gọi. Nếu cache dùng chung chỉ lấy path làm khóa rồi lưu response như dữ liệu công khai, người sau có thể nhận dữ liệu của người trước.

Một chính sách cho phép cache riêng lưu nhưng phải xác minh trước khi dùng lại có thể là:

```http
Cache-Control: private, no-cache
```

Nếu hợp đồng không cho phép lưu response ở cache HTTP, chọn:

```http
Cache-Control: no-store
```

Đây là hai quyết định khác nhau. Chọn quyết định nào phụ thuộc yêu cầu về dữ liệu và trải nghiệm, không chỉ phụ thuộc việc endpoint có xác thực.

`private` phân biệt cache riêng với cache dùng chung; nó không tự tạo khóa riêng cho từng tài khoản trên cùng một trình duyệt. Khi người dùng đăng xuất hoặc chuyển tài khoản, vẫn cần xem chính sách dùng lại, danh tính hiện tại và hành vi của client. Một response cá nhân còn fresh tại `/me` không tự trở nên đúng cho tài khoản kế tiếp.

### 7.2. Authorization và Cookie không thay thế chính sách

HTTP có các ràng buộc riêng đối với cache dùng chung và request chứa `Authorization`. Việc tái sử dụng có thể được cho phép bởi các chỉ thị response phù hợp, chẳng hạn `public` hoặc `s-maxage`, trong những điều kiện của chuẩn.

Do đó, không nên suy ra “có Authorization thì chắc chắn không thể cache”, nhưng cũng không được thêm `public` chỉ để tăng tỷ lệ cache cho dữ liệu cá nhân. Chỉ công bố khả năng dùng chung khi biểu diễn thực sự có cùng ý nghĩa cho những bên được phục vụ và chính sách đáp ứng yêu cầu truy cập.

Tương tự, sự có mặt của `Cookie` hoặc `Set-Cookie` không tự tương đương với `Cache-Control: no-store`. Nếu dữ liệu phụ thuộc phiên hoặc người dùng, response cần một chính sách rõ ràng và cấu hình các lớp trung gian phù hợp.

Không nên coi `Vary: Authorization` hoặc `Vary: Cookie` là biện pháp duy nhất thay cho quyết định cache có được lưu dữ liệu đó không. Phạm vi lưu, việc chọn biến thể và phân quyền là các trách nhiệm cần phối hợp.

## 8. Cập nhật dữ liệu và invalidation

### 8.1. TTL chấp nhận một khoảng dữ liệu cũ

Giả sử response sản phẩm được cache với `max-age=60`. Sau 10 giây, người quản trị đổi tên sản phẩm tại origin. Một cache đang giữ bản còn fresh vẫn có thể phục vụ tên cũ trong khoảng thời gian được cho phép.

ETag mới tại origin không tự được đẩy đến mọi cache. Nó chỉ có tác dụng khi có trao đổi xác minh hoặc lấy response mới. Vì vậy, không thể chỉ thêm ETag rồi hứa mọi client luôn thấy thay đổi ngay.

### 8.2. Không phải mọi URI liên quan đều tự được xóa

HTTP có quy tắc invalidation cho URI đích khi cache quan sát thao tác ghi và response đáp ứng các điều kiện của chuẩn. Điều đó không có nghĩa mọi cache đều thấy request ghi, hoặc mọi URI chứa dữ liệu liên quan đều tự được làm mới.

Ví dụ sửa `/products/prd-10` có thể ảnh hưởng:

- Biểu diễn chi tiết của sản phẩm.
- Một trang `/products?page=1&size=20`.
- Một kết quả tìm kiếm `/products?category=keyboards`.
- Một biểu diễn tổng hợp của danh mục.

Cache không tự hiểu mọi quan hệ nghiệp vụ giữa các URI. Tùy yêu cầu, hệ thống có thể phối hợp TTL phù hợp, revalidation, purge ở hạ tầng hoặc URI có phiên bản cho nội dung bất biến.

Purge tại một CDN cũng không tự xóa mọi bản đã nằm trong cache riêng của client. Cam kết về độ mới phải xét toàn bộ đường đi của response, không chỉ cache mà đội ngũ trực tiếp điều khiển.

### 8.3. Stale không phải quyền dùng lại vô điều kiện

Khi response stale, thông thường cache cần xác minh hoặc lấy lại trước khi phục vụ. Một số điều kiện HTTP hoặc extension có thể cho phép dùng stale trong một phạm vi nhất định; không nên giả định cache luôn được dùng bản cũ khi origin lỗi.

Nếu response có `must-revalidate`, cache phải tuân thủ yêu cầu xác minh sau khi stale. Khi không xác minh được, nó không được tùy tiện trả bản cũ như thể vẫn hợp lệ.

Nếu API cho phép phục vụ dữ liệu cũ để tăng tính sẵn sàng, cần công bố rõ phạm vi và kiểm tra sự hỗ trợ của các thành phần. Đó là một lựa chọn nghiệp vụ về mức dữ liệu cũ chấp nhận được, không chỉ một nút bật hiệu năng.

## 9. Minh họa khai báo trong Java/Spring

### 9.1. Response công khai có thời gian fresh và ETag

Đoạn dưới đặt trong một Spring MVC controller, minh họa metadata cho một endpoint chỉ trả một biểu diễn JSON công khai, không thay đổi theo danh tính hoặc ngôn ngữ. `catalog`, `ProductSnapshot` và `ProductView` là các kiểu nghiệp vụ minh họa; cấu hình, import và triển khai service được lược bỏ.

```java
@GetMapping(
    value = "/public/products/{id}",
    produces = MediaType.APPLICATION_JSON_VALUE
)
public ResponseEntity<ProductView> getPublicProduct(
        @PathVariable("id") String id) {
    ProductSnapshot snapshot = catalog.getPublicSnapshot(id);

    CacheControl policy = CacheControl
            .maxAge(60, TimeUnit.SECONDS)
            .cachePublic();

    return ResponseEntity.ok()
            .cacheControl(policy)
            .eTag(snapshot.getEtag())
            .body(snapshot.getBody());
}
```

`CacheControl`, `MediaType` và `ResponseEntity` thuộc Spring HTTP; `TimeUnit` là `java.util.concurrent.TimeUnit`. Service phải cung cấp body cùng ETag nhất quán cho đúng biểu diễn; không tạo một ETag ngẫu nhiên mới cho mỗi request khi body vẫn như cũ.

Spring MVC hỗ trợ xử lý conditional request khi trả `ResponseEntity` có validator phù hợp. Cần kiểm tra hành vi thực tế của endpoint và các filter hoặc proxy liên quan, thay vì tự viết phép so sánh chuỗi đơn giản chỉ xử lý được một dạng `If-None-Match`.

Nếu sau này endpoint chọn ngôn ngữ hoặc định dạng từ request header, phải bổ sung việc chọn biến thể, `Vary` và validator tương ứng. Không được giữ nguyên giả định “một biểu diễn công khai” khi hợp đồng đã thay đổi.

### 9.2. Response không cho lưu

Ví dụ một endpoint hồ sơ có chính sách không lưu response ở cache HTTP:

```java
@GetMapping("/me")
public ResponseEntity<ProfileView> getProfile(Principal principal) {
    return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(profiles.getFor(principal.getName()));
}
```

Ví dụ giả định lớp bảo mật đã yêu cầu xác thực cho `/me` và service thực hiện kiểm tra quyền cần thiết. `Principal` thuộc `java.security`. Đoạn code chỉ minh họa chính sách response; không phải một ứng dụng bảo mật hoàn chỉnh.

Nếu hợp đồng cho phép lưu trong cache riêng và yêu cầu xác minh mỗi lần dùng lại, có thể công bố `private, no-cache` thay vì `no-store`. Không cần thêm các chỉ thị có ý nghĩa khác nhau chỉ để header trông “mạnh hơn”; hãy chọn đúng hành vi mong muốn.

## 10. Kiểm tra hợp đồng cache như thế nào?

Các tình huống sau là ví dụ kiểm tra khi triển khai API. Chúng phân biệt chính sách công bố, điều kiện tái sử dụng và quyền nhận dữ liệu.

| Tình huống | Điều cần xác minh |
| --- | --- |
| Đọc sản phẩm công khai lần đầu | Response có đúng policy, validator và metadata biến thể không? |
| Đọc lại khi bản lưu còn fresh | Cache có dùng lại đúng bản, đúng request và đúng phạm vi không? |
| Xác minh bằng ETag chưa đổi | Conditional GET có nhận `304` không body và metadata phù hợp không? |
| Xác minh sau khi nội dung đổi | Có nhận `200`, body mới và validator tương ứng không? |
| Request thay đổi ngôn ngữ | Có chọn đúng biểu diễn và tránh dùng nhầm bản của ngôn ngữ khác không? |
| Hai tài khoản cùng gọi `/me` | Có tránh dùng lại response sai danh tính, kể cả khi chuyển tài khoản trên cùng client không? |
| Response `404` trước khi tạo dữ liệu | Chính sách cache lỗi có gây giữ kết quả không tồn tại lâu hơn cam kết không? |
| Origin không truy cập được khi bản đã stale | Cache có tuân thủ chính sách về xác minh và việc dùng stale không? |
| Cập nhật tài nguyên liên quan tới danh sách | Độ trễ thấy dữ liệu mới có nằm trong cam kết cho mọi biểu diễn liên quan không? |

Khi xem response từ proxy hoặc CDN, hãy quan sát cả `Cache-Control`, `Age`, `Date`, `Vary` và validator. Một header chẩn đoán như `X-Cache` có thể hữu ích nhưng thuộc quy ước của hạ tầng; nó không thay thế ngữ nghĩa HTTP chuẩn.

Cũng cần phân biệt các kiểu yêu cầu kiểm tra:

- Request bình thường có thể được đáp ứng từ một bản còn fresh.
- Request có `Cache-Control: no-cache` yêu cầu xác minh trước khi dùng response đã lưu; nó không phải lệnh purge mọi cache.
- Một request có `If-None-Match` cho phép kiểm tra điều kiện về biểu diễn; không nên tự thêm header này nếu client không có body phù hợp để dùng lại khi nhận `304`.

Công cụ kiểm tra có thể tự gửi thêm chỉ thị hoặc tắt cache. Vì vậy, kết quả của một lần reload hoặc một request thủ công chưa đủ kết luận hệ thống hoàn toàn không cache.

## 11. Các lỗi thiết kế thường gặp

| Sai lầm | Hệ quả | Cách sửa theo hợp đồng |
| --- | --- | --- |
| Hiểu `no-cache` là không được lưu | Chọn sai chính sách cho dữ liệu cần hạn chế lưu | Dùng `no-store` khi yêu cầu là không lưu cache HTTP |
| Không gửi header vì nghĩ mặc định không cache | Có thể xuất hiện heuristic caching ngoài dự kiến | Công bố chính sách rõ cho response quan trọng, gồm cả lỗi |
| Dùng `public` cho response cá nhân | Cache dùng chung có thể giữ dữ liệu không phù hợp | Xác định đúng phạm vi lưu và quyền nhận biểu diễn |
| Bỏ query parameter khỏi cache key | Trả nhầm trang, bộ lọc hoặc thứ tự | Giữ những thành phần URI ảnh hưởng đến nội dung |
| Thiếu `Vary` khi chọn biểu diễn bằng header | Dùng nhầm ngôn ngữ hoặc định dạng | Công bố các chiều biến thể cần thiết |
| Strong ETag không thay đổi khi body đổi | Có thể trả nhầm `304` | Tạo validator theo đúng biểu diễn và quy tắc so sánh |
| Trả `304` cùng JSON body mới | Client hoặc cache không nhận nội dung theo cách mong muốn | Dùng `304` không body khi điều kiện phù hợp; nếu đã đổi thì trả `200` |
| Nghĩ ETag tự đồng bộ mọi cache | Client tiếp tục dùng bản còn fresh | Phối hợp TTL, revalidation và invalidation theo cam kết |
| Cho rằng `@Cacheable` đã cấu hình cache HTTP | Client không biết chính sách response | Cấu hình metadata HTTP riêng và giữ nhất quán với dữ liệu phía server |

## 12. Tự xác định một chính sách cache

Với mỗi nhóm response của một endpoint, hãy trả lời lần lượt:

1. **Ai có thể nhận cùng biểu diễn?** Mọi client, một người dùng, hay một nhóm quyền cụ thể?
2. **Có cho lưu không?** Nếu có, cache riêng hay cả cache dùng chung?
3. **Có chấp nhận dữ liệu cũ không?** Chấp nhận trong khoảng nào, với ảnh hưởng nghiệp vụ nào?
4. **Khi nào phải hỏi origin?** Mỗi lần dùng lại, sau khi hết freshness, hay theo điều kiện khác đã công bố?
5. **Xác minh bằng gì?** ETag, Last-Modified hay lấy lại toàn bộ response?
6. **Biểu diễn phụ thuộc vào gì?** URI, query string, header, danh tính và các quy tắc chọn dữ liệu nào?
7. **Sau cập nhật thì sao?** Những bản chi tiết, danh sách và cache ở các lớp sẽ được làm mới trong giới hạn nào?

Ví dụ một danh mục công khai có thể chấp nhận `public, max-age=60` kèm ETag; một hồ sơ cá nhân có thể cần `private, no-cache`; một response không cho phép lưu cần `no-store`. Các giá trị chỉ có ý nghĩa khi phù hợp dữ liệu thực tế và được các thành phần thực hiện đúng.

Cacheable trong REST là một cam kết về khả năng và điều kiện tái sử dụng thông tin. Thiết kế tốt giúp client và hạ tầng biết chính xác khi nào được lưu, khi nào được dùng lại và khi nào phải trao đổi với origin, đồng thời giữ đúng quyền truy cập và ý nghĩa nghiệp vụ của biểu diễn.
