# Layered system với proxy, gateway và cache trung gian

## Mục tiêu bài học

Trong chương **Ràng buộc REST** của module **INTEGRATION_API_REST**, bài học này giải thích cách một API có thể hoạt động qua nhiều lớp trung gian mà client vẫn tương tác bằng một hợp đồng HTTP ổn định.

Sau bài học, bạn cần:

- Giải thích đúng ràng buộc **layered system** và phân biệt nó với cách chia tầng trong mã ứng dụng.
- Phân biệt vai trò của forward proxy, reverse proxy, API gateway và cache trung gian.
- Theo dõi một request qua các lớp, kể cả khi response được trả từ cache mà không gọi ứng dụng gốc.
- Nhận diện ảnh hưởng của các lớp đến URI, header, cache, xác thực, phân quyền và xử lý lỗi.
- Đề xuất những kiểm thử tích hợp cần thiết với Java/Spring hoặc công nghệ tương đương.

Các ví dụ tập trung vào một API bán hàng: thông tin sản phẩm công khai có thể cache; đơn hàng thuộc người dùng cần chính sách truy cập và lưu trữ khác.

## 1. Layered system ràng buộc điều gì?

Trong kiến trúc REST, **layered system** tổ chức các thành phần thành những lớp sao cho một thành phần không cần nhìn xuyên qua lớp mà nó đang trực tiếp tương tác để biết toàn bộ cấu trúc phía sau.

Client gọi một địa chỉ API công khai. Thành phần nhận request trực tiếp có thể là một reverse proxy, một gateway hoặc một cache. Client không cần biết request cuối cùng được xử lý bởi instance ứng dụng nào, hay có bao nhiêu lớp trung gian ở phía sau.

Ví dụ:

~~~text
Client
  |
  | HTTPS: api.example.com
  v
Reverse proxy / cache biên
  |
  v
API gateway
  |
  v
Ứng dụng API
  |
  v
Kho dữ liệu
~~~

Response đi ngược lại qua các lớp cần thiết. Nếu cache có một response được phép tái sử dụng, đường đi có thể kết thúc ngay tại cache, không đi tiếp tới gateway và ứng dụng.

Đây là một cấu trúc minh họa, không phải số lớp bắt buộc. Một hệ thống nhỏ có thể dùng một reverse proxy trước ứng dụng; hệ thống khác có thể dùng nhiều lớp. Một sản phẩm hạ tầng cũng có thể đồng thời làm proxy, gateway, cân bằng tải và cache.

### 1.1. Client phụ thuộc vào hợp đồng công khai, không phụ thuộc topology nội bộ

Client cần biết những điều như:

- URI công khai của resource.
- Method và dữ liệu được gửi.
- Media type và schema dữ liệu nhận về.
- Mã trạng thái và cấu trúc lỗi.
- Cách xác thực và điều kiện sử dụng API.

Client không nên phải biết:

- Tên máy nội bộ chạy ứng dụng.
- Cổng của từng instance.
- Resource hiện được route tới phiên bản triển khai nào.
- Cache nằm trước hay sau gateway.
- Số lượng instance đang hoạt động.

Ví dụ, chuyển từ hai instance sang bốn instance không nên buộc ứng dụng di động thay URL gọi API.

Tuy nhiên, “không cần biết” không có nghĩa hệ thống phải giấu mọi dấu vết về hạ tầng. Header như `Age`, thông tin truy vết hoặc phản hồi lỗi có thể cho biết đã có lớp trung gian. Điểm cốt lõi là client không phải phối hợp trực tiếp với toàn bộ chuỗi thành phần để hoàn thành một tương tác bình thường.

### 1.2. Không đồng nhất với controller–service–repository

Cấu trúc:

~~~text
Controller → Service → Repository
~~~

là cách tổ chức trách nhiệm trong mã ứng dụng. Nó có ích nhưng không tự chứng minh rằng tương tác giữa các thành phần phân tán đáp ứng ràng buộc layered system của REST.

Tương tự, có nhiều microservice không tự làm hệ thống đạt ràng buộc này. Nếu client phải dò tìm từng service nội bộ, chọn instance và tự điều phối theo topology triển khai, tính độc lập giữa các lớp vẫn bị suy yếu.

## 2. Các thành phần trung gian thường gặp

| Thành phần | Vai trò chính | Ai thường cấu hình hoặc lựa chọn? |
|---|---|---|
| Forward proxy | Thay mặt client gửi request tới các server bên ngoài | Client hoặc mạng phía client |
| Reverse proxy | Đại diện phía server, nhận request công khai rồi chuyển tới backend | Bên vận hành dịch vụ |
| API gateway | Áp dụng các chính sách và định tuyến ở điểm vào API | Bên cung cấp nền tảng/API |
| Shared cache | Lưu và tái sử dụng response cho nhiều client khi HTTP và chính sách cho phép | Hạ tầng dịch vụ hoặc trung gian |
| Bộ cân bằng tải HTTP | Phân phối request tới các backend theo chính sách | Bên vận hành dịch vụ |

Các tên trên nhấn mạnh chức năng. Chúng không nhất thiết chỉ các máy hoặc sản phẩm khác nhau.

Trong thuật ngữ HTTP, gateway còn có nghĩa kỹ thuật gần với reverse proxy: nó đóng vai server ở phía nhận request và chuyển yêu cầu về phía hệ thống phía sau. “API gateway” trong thực hành thường nói thêm đến nhóm chức năng quản lý API như xác thực, hạn mức và định tuyến.

### 2.1. Forward proxy

Ví dụ:

~~~text
Ứng dụng của nhân viên
  → proxy của công ty
  → api.example.com
~~~

Proxy nằm ở phía truy cập ra ngoài. Nó có thể áp dụng chính sách truy cập, ghi nhận kết nối hoặc chuyển tiếp yêu cầu.

Với HTTPS, một forward proxy có thể tạo đường hầm để chuyển dữ liệu đã mã hóa; điều đó không có nghĩa nó luôn đọc được method, header hay JSON bên trong. Khả năng quan sát hoặc can thiệp phụ thuộc cách thiết lập kết nối và TLS.

### 2.2. Reverse proxy

Ví dụ:

~~~text
Client → api.example.com → instance A hoặc instance B
~~~

Client nhìn thấy địa chỉ công khai; reverse proxy chọn backend phù hợp.

Các chức năng thường được kết hợp gồm:

- Kết thúc kết nối TLS công khai.
- Định tuyến theo host hoặc đường dẫn.
- Cân bằng tải và kiểm tra tình trạng backend.
- Giới hạn kích thước request.
- Chuyển tiếp hoặc chuẩn hóa một số header.
- Cache response khi được cấu hình phù hợp.

Kết thúc TLS ở reverse proxy chỉ mô tả một đoạn kết nối. Nếu cần bảo vệ dữ liệu trên đường từ proxy tới ứng dụng, đoạn đó cũng phải có cơ chế bảo vệ phù hợp; không nên mặc định HTTPS ở địa chỉ công khai đã mô tả toàn bộ đường đi nội bộ.

### 2.3. API gateway

Gateway thường áp dụng các chính sách chung:

- Chọn backend theo API và phiên bản.
- Xác thực thông tin người gọi.
- Giới hạn tần suất hoặc hạn mức.
- Kiểm soát kích thước và một số đặc điểm của request.
- Gắn thông tin truy vết.
- Chuẩn hóa cách trả lỗi tại điểm vào.

Gateway có thể từ chối request trước khi gọi backend, chẳng hạn vì vượt hạn mức. Khi đó backend không có log xử lý request đó; việc điều tra cần xem dữ liệu tại gateway.

Gateway cũng không nên trở thành nơi duy nhất biết toàn bộ quy tắc nghiệp vụ nếu điều đó làm mọi thay đổi đều phải đi qua một thành phần trung tâm quá phức tạp.

### 2.4. Cache trung gian

Shared cache có thể trả một response đã lưu cho nhiều client, nhưng chỉ khi việc lưu và tái sử dụng đáp ứng quy tắc HTTP, cấu hình và yêu cầu bảo mật.

CDN là một ví dụ về hạ tầng phân phối có thể kết hợp reverse proxy và cache ở nhiều vị trí. Không phải mọi response đi qua CDN đều được cache.

Cần phân biệt:

- Cache riêng của trình duyệt có phạm vi sử dụng riêng.
- Shared cache phục vụ nhiều người gọi.
- Cache trong ứng dụng có thể lưu đối tượng hoặc kết quả truy vấn theo quy tắc riêng.

Ba loại này không tự có cùng khóa, thời hạn hay cơ chế xóa dữ liệu. Việc xóa cache trong ứng dụng không tự xóa một response đã lưu ở proxy.

## 3. Lợi ích của việc chia lớp

### 3.1. Thay đổi triển khai sau một giao diện ổn định

Ứng dụng có thể thay instance, nâng cấp hoặc thay đổi cách triển khai mà client vẫn dùng cùng host và URI công khai.

Tính độc lập này chỉ được giữ nếu hệ thống không làm rò rỉ địa chỉ nội bộ vào những phần client phải sử dụng, chẳng hạn `Location`, link phân trang hoặc URL tải kết quả.

### 3.2. Tập trung một số chính sách dùng chung

Gateway và reverse proxy có thể triển khai nhất quán các chính sách về hạn mức, kích thước request hoặc theo dõi lưu lượng.

Lợi ích là giảm việc lặp lại một số cấu hình ở từng ứng dụng. Chi phí là phải xác định rõ chính sách nào thuộc hạ tầng và chính sách nào phải do ứng dụng quyết định.

### 3.3. Giảm tải khi cache phù hợp

Một response sản phẩm công khai có thể được nhiều client tái sử dụng, giúp giảm số request và truy vấn tới ứng dụng.

Nhưng cache hit chỉ là lợi ích khi response đúng người dùng, đúng biến thể và được phép tái sử dụng. Một response trả nhanh nhưng thuộc về người khác là lỗi nghiêm trọng.

### 3.4. Có thể mở rộng hoặc bảo vệ từng khu vực

Các lớp có thể được mở rộng và bảo vệ theo vai trò riêng. Ví dụ, reverse proxy lọc request quá lớn trước khi chúng chiếm tài nguyên của ứng dụng.

Đổi lại, mỗi lớp có thể thêm độ trễ, cấu hình, kết nối và điểm phát sinh lỗi. Layered system tạo khả năng phân tách trách nhiệm; nó không yêu cầu thêm lớp chỉ để sơ đồ trông đầy đủ.

## 4. Theo dõi một request qua proxy, gateway và cache

Xét một resource sản phẩm công khai, với representation giống nhau đối với mọi người gọi trong ví dụ:

~~~http
GET /products/42 HTTP/1.1
Host: api.example.com
Accept: application/json
~~~

### 4.1. Cache miss

Một luồng xử lý có thể là:

1. Cache tìm response phù hợp nhưng chưa có bản được phép tái sử dụng.
2. Request được chuyển đến gateway.
3. Gateway kiểm tra các chính sách áp dụng và chọn backend.
4. Ứng dụng đọc sản phẩm và tạo response.
5. Response đi ngược qua các lớp.
6. Cache lưu response nếu đủ điều kiện rồi trả cho client.

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=60
ETag: "product-42-v7"

{
  "id": 42,
  "name": "Bình giữ nhiệt",
  "price": 125000,
  "currency": "VND"
}
~~~

Ví dụ này giả định giá và các trường đều công khai, không phụ thuộc tài khoản, tenant hoặc chương trình ưu đãi riêng.

`public` cho biết response có thể được shared cache lưu theo các quy tắc áp dụng; nó không bắt buộc mọi cache phải lưu. `max-age=60` thiết lập thời gian freshness 60 giây theo chính sách này.

### 4.2. Cache hit

Một client khác gọi cùng representation khi bản lưu vẫn fresh. Cache có thể trả response mà không gọi ứng dụng.

Response qua shared cache có thể kèm:

~~~http
Age: 18
~~~

`Age` thể hiện ước lượng tuổi của response theo cơ chế cache HTTP, tính bằng giây; nó không phải số lần cache hit.

Trong tình huống này:

- Backend không nhất thiết nhận request mới.
- Log ở backend không phản ánh toàn bộ lưu lượng client.
- Cần đo cache hit/miss và lưu lượng ở lớp trung gian.
- Nội dung client nhìn thấy là bản được phép tái sử dụng, chưa chắc là dữ liệu mới nhất trong cơ sở dữ liệu.

### 4.3. Bản lưu cần được kiểm tra lại

Khi response không còn fresh, cache có thể hỏi lại bằng validator:

~~~http
GET /products/42 HTTP/1.1
Host: api.example.com
If-None-Match: "product-42-v7"
~~~

Nếu representation chưa thay đổi theo validator, ứng dụng có thể trả:

~~~http
HTTP/1.1 304 Not Modified
ETag: "product-42-v7"
Cache-Control: public, max-age=60
~~~

Response `304` không có body. Cache dùng thông tin nhận được để cập nhật metadata và tái sử dụng body đã lưu theo quy tắc HTTP.

Cần phân biệt hai cuộc trao đổi:

- Cache có thể gửi request có điều kiện tới origin và nhận `304`.
- Nếu client ban đầu không gửi điều kiện, cache có thể trả `200` cùng body đã lưu cho client sau khi kiểm tra lại.

Vì vậy, không được chuyển mọi `304` từ origin tới mọi client một cách máy móc. Điều kiện của request phía client và representation mà client đã có phải được xử lý đúng.

## 5. Khóa cache và biến thể response

Cache cần nhận ra những request nào có thể dùng chung representation. Cơ sở thường là method và URI đích, kết hợp các biến thể được chỉ ra bởi `Vary` hoặc chính sách cấu hình.

Xét các request:

~~~text
GET /products?page=1&size=20
GET /products?page=2&size=20
GET /products?page=1&size=50
~~~

Chúng không có cùng URI và có thể mang các trang dữ liệu khác nhau. Nếu cấu hình cache bỏ qua các query parameter có ý nghĩa, client có thể nhận sai trang.

Tương tự, đường dẫn giống nhau dưới hai host hoặc hai tenant không được tùy tiện coi là cùng một resource.

### 5.1. Vary cho biết representation phụ thuộc header nào

Nếu API có nội dung theo ngôn ngữ:

~~~http
GET /products/42 HTTP/1.1
Host: api.example.com
Accept-Language: vi
~~~

Response có thể có:

~~~http
Content-Language: vi
Vary: Accept-Language
~~~

Cache cần xét giá trị header được nêu trong `Vary` khi chọn bản lưu. Nếu response còn thay đổi theo `Accept`, cần thiết kế phân biệt media type tương ứng.

`Vary` không thay thế toàn bộ chính sách cache và không tự sửa một khóa cache tùy biến sai. Phải bảo đảm cả ứng dụng và hạ tầng đồng ý về những yếu tố làm thay đổi representation.

Đặc biệt, `Vary` không phải cơ chế phân quyền. Thêm `Vary: Authorization` không đủ để chứng minh dữ liệu cá nhân đã an toàn để shared cache lưu.

### 5.2. Không tự giả định mọi header hay cookie đều được đưa vào khóa

Một ứng dụng có thể tạo giá riêng theo tài khoản nhưng chỉ cấu hình cache theo URI. Khi đó hai người dùng gọi cùng URI có nguy cơ nhận chung một response không phù hợp.

Ngược lại, đưa mọi header vào khóa một cách tùy tiện làm số biến thể tăng mạnh và giảm hiệu quả cache.

Cần xác định rõ:

1. Resource này có công khai không?
2. Những yếu tố nào thực sự làm nội dung thay đổi?
3. Shared cache có được lưu response này không?
4. Chính sách tái sử dụng có đáp ứng quyền và freshness không?

HTTP có các hạn chế riêng đối với shared cache khi request mang `Authorization`, và có những chỉ thị tường minh có thể cho phép lưu trong các điều kiện cụ thể. Không nên thay các quy tắc đó bằng giả định “có token thì cache không bao giờ lưu” hoặc “trả 200 thì cache được”.

## 6. Ranh giới bảo mật khi cache nằm trước gateway

Trong sơ đồ đầu bài, cache đứng trước gateway. Điều này có một hệ quả quan trọng: cache hit có thể không đi qua bước xác thực hoặc giới hạn tần suất ở gateway.

Với danh mục hoàn toàn công khai, đây có thể là lựa chọn có chủ đích. Với đơn hàng cá nhân, cần một thiết kế khác hoặc chính sách ngăn lưu và phục vụ sai dữ liệu.

Ví dụ response đơn hàng:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "id": 42,
  "status": "CONFIRMED"
}
~~~

Một lựa chọn dễ kiểm soát cho route nhạy cảm là:

- Cấu hình shared cache bỏ qua route đó.
- Ứng dụng trả chỉ thị không lưu phù hợp, như `no-store`.
- Request vẫn phải tới điểm thực hiện xác thực và phân quyền.
- Kiểm tra việc áp dụng trong triển khai thực tế.

`private` có ý nghĩa khác: nó ngăn shared cache lưu response nhưng vẫn có thể cho cache riêng lưu theo điều kiện áp dụng. `no-cache` cũng không phải “không lưu”; nó yêu cầu xác thực lại trước khi tái sử dụng theo quy tắc áp dụng.

Không nên xem việc chuyển cache ra sau gateway là lời giải đầy đủ cho mọi trường hợp. Nếu response của người A được cache rồi trả cho người B mà không có chính sách phân tách và kiểm tra đúng, lỗi vẫn tồn tại.

Các route thay đổi từ công khai sang riêng tư cũng cần xử lý những bản đã lưu trước đó. Chỉ thay header tại origin không bảo đảm mọi cache còn giữ bản fresh sẽ lập tức biết chính sách mới.

## 7. URI công khai, chuyển tiếp và header đáng tin cậy

### 7.1. Giữ đúng URI mà client có thể sử dụng

Giả sử đường đi là:

~~~text
Client:
https://api.example.com/v1/orders

Gateway chuyển tiếp:
http://order-service:8080/orders
~~~

Ứng dụng tạo đơn hàng thành công. Response trả cho client nên tham chiếu tới địa chỉ công khai phù hợp:

~~~http
HTTP/1.1 201 Created
Location: https://api.example.com/v1/orders/42
Content-Type: application/json

{
  "id": 42,
  "status": "PENDING"
}
~~~

Nếu `Location` trỏ đến `http://order-service:8080/orders/42`, client có thể không truy cập được; địa chỉ còn làm lộ chi tiết triển khai.

Cần xử lý nhất quán cả:

- Scheme `https`.
- Host công khai.
- Tiền tố đường dẫn như `/v1`.
- Link phân trang, link resource và redirect.

Có thể dùng cấu hình base URI công khai hoặc metadata chuyển tiếp đã được xác thực theo hạ tầng. Mỗi cách cần bảo đảm không lấy dữ liệu do người gọi tùy ý cung cấp để dựng URL tin cậy.

### 7.2. Forwarded không mặc nhiên đáng tin

Các header như `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Proto` hoặc `X-Forwarded-Host` thường được dùng để truyền thông tin về request ban đầu.

Ví dụ minh họa:

~~~http
Forwarded: for=192.0.2.10;proto=https;host=api.example.com
~~~

Địa chỉ IP trong ví dụ là giá trị minh họa. Trong thực tế, client có thể tự gửi những header cùng tên.

Một ranh giới tin cậy cần được xác định rõ:

1. Lớp tiếp nhận đầu tiên xử lý các header chuyển tiếp do bên ngoài gửi theo chính sách, thường là loại bỏ hoặc thay thế.
2. Các proxy được tin cậy thêm thông tin theo quy ước nhất quán.
3. Ứng dụng chỉ diễn giải các giá trị qua chuỗi proxy được tin cậy.
4. Đường truy cập trực tiếp vào backend được kiểm soát để không bỏ qua ranh giới này.

Không nên lấy tùy tiện phần tử đầu tiên của `X-Forwarded-For` làm căn cứ phân quyền hoặc hạn mức. Cần hiểu cách hạ tầng xây dựng và kiểm tra chuỗi địa chỉ.

Tương tự, nếu ứng dụng tin mọi `X-Forwarded-Host`, kẻ gọi có thể ảnh hưởng URL mà ứng dụng tạo ra. Đây là vấn đề cấu hình tin cậy, không phải điều REST tự ngăn chặn.

### 7.3. Không chuyển tiếp mọi header một cách máy móc

Một số trường thuộc kết nối giữa hai thành phần liền kề, không phải metadata cần giữ nguyên xuyên suốt. Proxy HTTP phải xử lý đúng các trường theo từng chặng, bao gồm những trường được nêu bởi `Connection`.

Ngược lại, những thông tin có ý nghĩa với hợp đồng như điều kiện `If-Match`, validator `ETag` hoặc chỉ thị cache không nên bị bỏ đi vô cớ.

Nếu một lớp biến đổi body, nó còn phải giữ nhất quán các metadata liên quan như media type, encoding, độ dài hoặc validator. Không thể sửa JSON rồi giữ nguyên một strong ETag vốn được tạo cho representation cũ.

## 8. Gateway không thay thế phân quyền nghiệp vụ

Gateway có thể kiểm tra token và xác định người gọi. Ứng dụng vẫn phải kiểm tra quyền trên resource cụ thể.

Ví dụ:

~~~http
GET /orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer <token>
~~~

Một token hợp lệ chưa cho biết người gọi có được đọc đơn hàng 42 hay không. Ứng dụng thường cần dữ liệu sở hữu, tổ chức hoặc quyền nghiệp vụ để quyết định.

Nếu gateway chuyển danh tính qua một header nội bộ:

~~~http
X-Authenticated-User: user-15
~~~

thì header đó phải do thành phần tin cậy tạo và được bảo vệ khỏi giả mạo. Không thể nhận trực tiếp cùng header do client gửi rồi coi đó là bằng chứng danh tính.

Tương tự, nếu request đi qua cache trước bước kiểm tra quyền, phải bảo đảm không có đường cache hit làm bỏ qua yêu cầu quyền bắt buộc.

Một cách phân chia trách nhiệm:

| Lớp | Ví dụ trách nhiệm |
|---|---|
| Reverse proxy | Quản lý kết nối, giới hạn body, định tuyến cơ bản |
| Gateway | Xác thực, chính sách truy cập tổng quát, hạn mức theo hợp đồng |
| Ứng dụng | Phân quyền trên resource và trường dữ liệu, kiểm tra nghiệp vụ |
| Cache | Chỉ lưu và phục vụ response được phép, đúng khóa và biến thể |

Đây là phân chia minh họa. Dù triển khai ở đâu, cần có một nơi chịu trách nhiệm rõ ràng và tránh khoảng trống giữa các lớp.

## 9. Cập nhật resource và invalidation

Giả sử các response sau đã được cache:

~~~text
/products/42
/products?page=1&size=20
/products?category=bottles
/homepage/highlights
~~~

Sau đó giá sản phẩm 42 thay đổi. Không thể giả định mọi response liên quan đều tự được xóa chỉ vì một request cập nhật thành công.

Các quy tắc invalidation của HTTP áp dụng cho những URI và điều kiện cụ thể; chúng không tự suy ra mọi quan hệ nghiệp vụ giữa resource sản phẩm, trang danh sách và trang nổi bật.

Nhóm phát triển cần chọn chính sách, chẳng hạn:

- Cho phép dữ liệu cũ trong một khoảng TTL đã thống nhất.
- Kiểm tra lại bằng validator.
- Chủ động invalidation các khóa liên quan.
- Dùng URI hoặc phiên bản cho tài nguyên bất biến khi phù hợp.

Mỗi cách có chi phí. Invalidation chủ động cần biết những bản nào bị ảnh hưởng và xử lý khi việc xóa không thành công. TTL ngắn có thể tăng số request kiểm tra lại. TTL dài có thể làm client thấy dữ liệu cũ lâu hơn.

Trong tình huống cần người vừa cập nhật nhìn thấy trạng thái mới ngay, phải thiết kế cả luồng đọc sau ghi. Cache và tầng lưu trữ phía sau có thể tạo các nguồn trễ khác nhau.

## 10. Lỗi, timeout và retry qua nhiều lớp

Khi có nhiều lớp, response lỗi không nhất thiết được tạo bởi ứng dụng.

| Mã thường gặp | Ý nghĩa trong bối cảnh trung gian |
|---|---|
| `502 Bad Gateway` | Thành phần đang làm gateway/proxy nhận phản hồi không hợp lệ từ upstream |
| `503 Service Unavailable` | Thành phần trả lời hiện không thể xử lý request, chẳng hạn quá tải hoặc bảo trì |
| `504 Gateway Timeout` | Gateway/proxy không nhận phản hồi kịp thời từ upstream cần thiết |

Không được suy rằng mọi lỗi backend đều phải chuyển thành `502`; nếu upstream trả một response HTTP hợp lệ, như `404` theo hợp đồng, proxy thường cần giữ đúng ý nghĩa của response đó.

Hợp đồng lỗi cũng nên tính đến các lỗi do hạ tầng tạo. Nếu API cam kết lỗi JSON nhưng gateway trả một trang HTML mặc định, client cần có khả năng xử lý an toàn và nhóm triển khai cần xem lại tính nhất quán của hợp đồng.

### 10.1. Có thể có nhiều timeout khác nhau

Một request có thể chịu:

- Thời gian chờ tại client.
- Thời gian chờ tại gateway.
- Thời gian chờ khi ứng dụng gọi một dịch vụ khác.
- Thời gian chờ truy vấn hoặc khóa tại cơ sở dữ liệu.

Cần phân bổ thời gian hợp lý để lỗi có cơ hội được xử lý và trả về trước khi lớp ngoài hết hạn. Việc client hoặc gateway ngừng chờ không bảo đảm công việc ở backend đã dừng hoặc tác động ghi chưa xảy ra.

### 10.2. Retry có thể bị nhân lên

Giả sử ba lớp khác nhau đều cho phép tối đa ba lần thử cho một thao tác. Trong một cấu hình retry lồng nhau, một yêu cầu ban đầu có thể dẫn đến tới:

~~~text
3 × 3 × 3 = 27 lần thử ở tầng cuối
~~~

Đây là mô hình minh họa, không phải hành vi mặc định của proxy hay gateway.

Cần xác định nơi chịu trách nhiệm retry, tổng ngân sách thử lại, thời gian chờ và độ trễ giữa các lần thử. Với thao tác ghi như tạo đơn hàng, chỉ cấu hình retry không đủ để chống tác động trùng; cần cơ chế idempotency được triển khai đúng.

Layered system làm rõ ranh giới tương tác, nhưng không tự giải quyết tác động nghiệp vụ khi response bị mất.

## 11. Liên hệ với Java/Spring

Một controller có thể khai báo metadata cache, còn proxy quyết định có lưu hay không theo quy tắc và cấu hình của nó.

Ví dụ tối giản sau dùng Java có hỗ trợ `record` và một ứng dụng Spring MVC có bộ chuyển đổi JSON phù hợp:

~~~java
import java.util.concurrent.TimeUnit;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProductController {

    @GetMapping(value = "/products/42", produces = "application/json")
    public ResponseEntity<ProductView> getProduct() {
        ProductView product =
            new ProductView(42, "Bình giữ nhiệt", 125000, "VND");

        return ResponseEntity.ok()
            .cacheControl(
                CacheControl.maxAge(60, TimeUnit.SECONDS).cachePublic()
            )
            .eTag("\"product-42-v7\"")
            .body(product);
    }

    public record ProductView(
        long id,
        String name,
        long price,
        String currency
    ) {
    }
}
~~~

Endpoint và dữ liệu được cố định để minh họa response công khai. ETag cố định chỉ phù hợp với representation cố định của ví dụ; khi dữ liệu thay đổi, hệ thống thực tế phải sinh validator phù hợp.

Đoạn mã này không tự tạo shared cache, không cấu hình gateway và không chứng minh ranh giới tin cậy của forwarded header đã đúng.

Trong triển khai thực tế cần phối hợp:

- Ứng dụng tạo đúng header cache và validator.
- Hạ tầng tôn trọng chính sách và phân biệt biến thể.
- Cách dựng URI công khai phù hợp với proxy.
- Cấu hình xử lý forwarded header khớp với chuỗi proxy được tin cậy.
- Route riêng tư không bị lưu hoặc phục vụ sai người dùng.
- Timeout và retry giữa các tầng không mâu thuẫn nhau.

Không nên sao chép cấu hình tin mọi proxy chỉ để giải quyết nhanh lỗi URL `http`/địa chỉ nội bộ. Cấu hình phải phản ánh đúng nơi ứng dụng nhận traffic và những thành phần có quyền tạo metadata chuyển tiếp.

## 12. Kiểm thử tương tác qua các lớp

Kiểm thử controller trực tiếp hữu ích nhưng chưa đủ để xác nhận hành vi khi đi qua proxy, gateway và cache. Cần một môi trường kiểm thử có những thành phần liên quan hoặc một cách mô phỏng đúng ranh giới cần kiểm tra.

| Tình huống | Kết quả cần quan sát |
|---|---|
| Gọi sản phẩm lần đầu | Cache miss; ứng dụng nhận request; response có header mong đợi |
| Gọi lại khi response còn fresh | Có thể cache hit; body đúng; backend không nhất thiết được gọi |
| Bản cache cần kiểm tra lại | Validator được chuyển đúng; `304` và body lưu được xử lý đúng |
| Gọi hai trang phân trang khác nhau | Không bị trả cùng một trang do bỏ qua query |
| Gọi các ngôn ngữ hoặc media type khác nhau | Không lẫn representation giữa các biến thể |
| Người A và B gọi route cá nhân | Không nhận nhầm dữ liệu; mọi yêu cầu quyền vẫn được bảo đảm |
| Tạo resource qua địa chỉ công khai | `Location` và link dùng đúng scheme, host và tiền tố công khai |
| Client tự gửi header danh tính/chuyển tiếp | Không vượt qua ranh giới tin cậy hoặc giả mạo danh tính |
| Backend chậm hoặc không sẵn sàng | Mã lỗi, thời gian chờ và body phù hợp với hợp đồng |
| Response mất sau một thao tác ghi | Retry không tạo tác động trùng ngoài hợp đồng idempotency |
| Sửa giá sản phẩm | Hành vi freshness/invalidation đúng chính sách đã cam kết |

Khi kiểm tra cache hit, không chỉ nhìn việc response có nhanh hơn hay không. Có thể cần số đếm request ở origin, log tại cache hoặc metric phù hợp.

Khi kiểm tra luồng lỗi, cần biết lớp nào tạo response. Trace/correlation ID có thể hỗ trợ nối các bản ghi, nhưng không nên đưa token hoặc dữ liệu cá nhân vào log để thay cho thiết kế truy vết.

## 13. Tự kiểm tra

### Câu hỏi

1. Thêm controller, service và repository có đủ để nói hệ thống đã đáp ứng layered system của REST không?
2. Client nhận được response nhưng backend không có request log mới. Điều này có luôn là lỗi không?
3. Nếu cache nằm trước gateway, điều gì xảy ra với bước xác thực tại gateway khi cache hit?
4. Vì sao cache bỏ qua query parameter có thể làm hỏng phân trang?
5. `Vary: Authorization` có tự bảo đảm response cá nhân an toàn trong shared cache không?
6. Vì sao không nên tin một `X-Forwarded-Host` do client bất kỳ gửi lên?
7. Origin trả `304` cho cache. Cache có luôn phải trả `304` cho client ban đầu không?
8. Client nhận `504` sau khi tạo đơn. Có thể kết luận chắc chắn đơn chưa được tạo không?

### Gợi ý trả lời

1. Không. Đó là cách chia tầng mã nguồn; ràng buộc REST xét cách các thành phần tương tác qua các lớp trong hệ thống phân tán.
2. Không. Response có thể được phục vụ từ cache hoặc một lớp trung gian khác. Cần quan sát đúng điểm tiếp nhận request.
3. Request có thể không tới gateway. Vì vậy route, quyền truy cập và chính sách cache phải được thiết kế để không bỏ qua kiểm tra bắt buộc.
4. Các trang có URI khác nhau có thể bị gom vào cùng khóa cache, khiến client nhận sai dữ liệu.
5. Không. Cần tuân thủ quy tắc HTTP, quyền truy cập và chính sách lưu/tái sử dụng; `Vary` không thay thế phân quyền.
6. Vì giá trị có thể bị giả mạo và ảnh hưởng URL hoặc quyết định của ứng dụng. Chỉ diễn giải metadata chuyển tiếp trong ranh giới tin cậy được cấu hình.
7. Không. Cần xét điều kiện phía client; cache có thể dùng body đã lưu để trả `200` sau khi xác thực lại.
8. Không. Backend có thể đã hoàn tất tác động ghi nhưng phản hồi không đến kịp gateway. Cần đối soát kết quả hoặc retry theo cơ chế idempotency đã thiết kế.

Một thiết kế layered system tốt cho phép thay đổi hạ tầng phía sau mà client vẫn sử dụng cùng hợp đồng công khai. Để đạt điều đó, mỗi lớp cần có trách nhiệm rõ ràng và phải giữ đúng ý nghĩa của URI, phương thức, mã trạng thái, header, representation và các yêu cầu quyền truy cập.
