# Xử lý label chứa dấu gạch chéo trong API của Config Server

Trong Spring Cloud Config, tham số label thường đại diện cho một Git branch, tag hoặc commit dùng để chọn phiên bản cấu hình. Endpoint môi trường của Config Server có dạng /{application}/{profile}/{label}. Nếu tên branch hoặc tag chứa dấu gạch chéo /, chẳng hạn feature/checkout, đưa nguyên tên đó vào URL sẽ tạo thêm một đoạn path. Spring MVC và các proxy phía trước có thể hiểu dấu gạch chéo đó là ranh giới giữa các tham số URL, khiến Config Server không nhận được label như mong muốn.

Với Git backend mặc định, Spring Cloud Config quy định một cách biểu diễn an toàn: thay mỗi dấu / trong label bằng chuỗi đặc biệt (_). Vì vậy, Git ref feature/checkout được gọi qua API bằng feature(_)checkout. Config Server chuyển ký hiệu này trở lại dấu gạch chéo khi tìm Git ref.

Bài học này giải thích vì sao cần quy ước đó, cách gọi endpoint trực tiếp, cách cấu hình Config Client và cách chẩn đoán khi API không tìm thấy branch. Nội dung áp dụng cho Git backend mặc định của Spring Cloud Config; backend khác có thể định nghĩa ý nghĩa label khác.

Sau bài học, bạn có thể:

- Giải thích xung đột giữa dấu / trong Git ref và cấu trúc path của HTTP endpoint.
- Chuyển label có một hoặc nhiều dấu gạch chéo sang dạng (_) khi gọi API trực tiếp.
- Phân biệt cách truyền label cho REST API với cấu hình spring.cloud.config.label ở Config Client.
- Kiểm tra request, response và Git ref để tìm nguyên nhân lỗi.
- Thiết kế kiểm thử để tránh lỗi khi branch hoặc tag có tên phân cấp.

## 1. Endpoint của Config Server và vai trò của label

Config Server cung cấp cấu hình theo ba tham số chính:

| Tham số | Ý nghĩa | Ví dụ |
|---|---|---|
| application | Tên ứng dụng cần lấy cấu hình | order-service |
| profile | Profile hoặc danh sách profile | prod |
| label | Phiên bản cấu hình trong Git backend | main, release-2026-11, feature/checkout |

Endpoint môi trường dạng JSON thường có cấu trúc:

~~~text
GET /{application}/{profile}/{label}
~~~

Ví dụ với branch đơn giản:

~~~text
GET http://localhost:8888/order-service/prod/main
~~~

Ở đây, main không chứa dấu gạch chéo nên có thể đứng nguyên trong một path segment.

Label là tham số định tuyến đến phiên bản cấu hình. Nó không phải profile và cũng không phải tên file cấu hình. Profile chọn tập thuộc tính phù hợp với môi trường hoặc mục đích chạy; label chọn revision của repository Git mà Config Server đọc. Ví dụ prod là profile, còn release-2026-11 có thể là tag Git.

## 2. Vì sao dấu gạch chéo gây lỗi?

Git cho phép tên branch và tag có dấu gạch chéo để nhóm các nhánh theo quy ước. Ví dụ:

~~~text
feature/checkout
feature/payment-v2
release/2026/11
hotfix/order-timeout
~~~

Trong khi đó, URL dùng dấu / để phân chia các đoạn path. Nếu ghép nguyên branch feature/checkout vào endpoint, request trở thành:

~~~text
GET http://localhost:8888/order-service/prod/feature/checkout
~~~

URL này có thêm một đoạn checkout. Endpoint môi trường cần ba tham số application, profile và label; dấu gạch chéo trong Git ref đã làm thay đổi cấu trúc đường dẫn. Tùy phiên bản Spring MVC, servlet container, reverse proxy hoặc API gateway, request có thể không khớp route, bị từ chối hoặc bị diễn giải thành một đường dẫn khác.

Không nên phụ thuộc vào việc mã hóa slash thành %2F. Một số proxy hoặc container giải mã ký tự này trước khi định tuyến, một số cấu hình chặn encoded slash, và kết quả có thể khác nhau giữa các môi trường. Spring Cloud Config cung cấp token riêng để biểu diễn dấu gạch chéo trong path.

## 3. Quy tắc thay slash bằng ký hiệu (_)

Với Git backend mặc định, mỗi dấu / trong branch hoặc tag phải được thay bằng chuỗi (_) khi đưa label vào HTTP URL.

| Git label thật | Label đặt trong HTTP path |
|---|---|
| feature/checkout | feature(_)checkout |
| feature/payment-v2 | feature(_)payment-v2 |
| release/2026/11 | release(_)2026(_)11 |
| hotfix/order/timeout | hotfix(_)order(_)timeout |
| main | main |

Ví dụ, Git ref feature/checkout được gọi như sau:

~~~text
GET /order-service/prod/feature(_)checkout
~~~

Đối với label có nhiều dấu gạch chéo, thay tất cả các dấu đó. Không chỉ thay dấu đầu tiên hoặc cuối cùng.

(_) là ký hiệu dành cho việc biểu diễn path của Config Server. Nó không đổi tên branch trong Git. Repository vẫn có branch thật là feature/checkout; người quản trị Git vẫn checkout, merge và xóa branch bằng tên thật đó.

## 4. Gọi REST API trực tiếp

Khi kiểm tra Config Server bằng trình duyệt, curl hoặc HTTP client tự viết, hãy dùng label đã thay slash bằng (_).

Ví dụ với branch feature/checkout:

~~~bash
curl --fail --show-error 'http://localhost:8888/order-service/prod/feature(_)checkout'
~~~

Ví dụ với branch release/2026/11:

~~~bash
curl --fail --show-error 'http://localhost:8888/order-service/prod/release(_)2026(_)11'
~~~

Nên đặt toàn bộ URL trong dấu nháy đơn khi dùng command line. Dấu ngoặc trong token có thể được shell xử lý như cú pháp riêng; quote URL giúp giữ nguyên chuỗi gửi đi. Tài liệu Spring Cloud Config cũng lưu ý cần escape token khi gọi bằng công cụ dòng lệnh như curl.

Khi request thành công, response JSON biểu diễn một Environment với thông tin ứng dụng, profile, label, version/state và danh sách property sources. Kiểm tra các trường này để xác nhận Config Server đã trả về đúng ứng dụng, profile và Git ref mong muốn. Không chia sẻ response đầy đủ nếu nó có thể chứa thông tin cấu hình nhạy cảm.

## 5. Cấu hình label trong Spring Cloud Config Client

Config Client cũng có thể yêu cầu một label cụ thể qua spring.cloud.config.label. Ví dụ:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import: "configserver:http://localhost:8888"
  cloud:
    config:
      label: feature/checkout
~~~

Cần phân biệt hai trường hợp:

- **Cấu hình Config Client:** thuộc tính spring.cloud.config.label mô tả Git label mà ứng dụng muốn lấy. Trong Config Client hiện hành, loader chuyển label có slash sang dạng path-safe trước khi tạo request đến Config Server. Vì vậy, có thể khai báo Git ref thật feature/checkout trong cấu hình client.
- **Gọi REST API trực tiếp:** người gọi tự xây dựng URL nên phải thay slash bằng (_), ví dụ feature(_)checkout.

Nếu đang dùng phiên bản Config Client cũ, chế độ bootstrap cũ hoặc một HTTP client tự viết, hãy kiểm tra request thực tế và tài liệu đúng phiên bản trước khi quyết định dạng giá trị cần cấu hình. Một client tùy biến có thể không thực hiện bước chuyển đổi này. Không thay slash bằng %2F theo suy đoán và không encode token hai lần.

Ví dụ với client dùng label release/2026/11, request path an toàn mà server cần nhận tương đương:

~~~text
/order-service/prod/release(_)2026(_)11
~~~

Trong log của client, có thể kiểm tra URL request và response status. Không bật log chứa credentials, token hoặc toàn bộ nội dung cấu hình ở production chỉ để xác minh label.

## 6. Token cũng có thể dùng cho application

Tài liệu Git backend của Spring Cloud Config cho biết ký hiệu (_) cũng có thể được áp dụng cho tham số application nếu giá trị tham số đó chứa dấu gạch chéo. Điều này có thể hữu ích trong một số cách tổ chức tên ứng dụng hoặc tổ chức/repository.

Ví dụ, khi tham số application được biểu diễn bởi team-a/order-service, dạng path-safe là:

~~~text
team-a(_)order-service
~~~

Đây là quy tắc dành cho tham số path của Config Server. Không tự áp dụng token vào profile hoặc các giá trị cấu hình khác nếu tài liệu của endpoint không yêu cầu.

## 7. Quy trình kiểm tra khi API không tìm thấy label

Khi request trả về lỗi hoặc Config Server trả về cấu hình không đúng, hãy kiểm tra theo thứ tự:

1. **Xác nhận Git ref tồn tại:** kiểm tra branch hoặc tag chính xác trong remote repository. Chú ý chữ hoa/chữ thường, dấu gạch ngang và tên đầy đủ.
2. **Kiểm tra URL path:** nếu Git ref có slash, thay tất cả slash bằng (_) trong request trực tiếp.
3. **Kiểm tra shell và proxy:** quote URL khi dùng curl; kiểm tra gateway có rewrite, decode hoặc chặn path hay không.
4. **Xác nhận application và profile:** kiểm tra spring.application.name, profile và thứ tự profile client gửi.
5. **Xác nhận Config Server đọc đúng repository:** kiểm tra Git URI, quyền truy cập, label được fetch và cấu hình refresh/cache của backend.
6. **Đọc response:** xác nhận status code, tên application, profiles, label và property sources. Một response thành công vẫn cần được kiểm tra để bảo đảm đúng revision.
7. **So sánh với request của Config Client:** nếu gọi trực tiếp thành công nhưng client thất bại, kiểm tra phiên bản client và đường dẫn client thực sự gửi.

Một số dấu hiệu thường gặp:

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Request có thêm đoạn path sau label và trả 404 | Slash trong label chưa được thay | Dùng (_) cho từng slash |
| Request bị proxy từ chối | Proxy chặn encoded slash hoặc ký tự path | Dùng token (_) theo quy ước Config Server và kiểm tra rule gateway |
| API trả lỗi không tìm thấy branch | Git ref sai, chưa được fetch hoặc label gửi sai | Kiểm tra branch/tag trên remote và Git backend |
| API trả cấu hình của branch khác | Nhầm label, fallback hoặc cấu hình client không như dự kiến | Đối chiếu label trong request và response |
| Gọi API trực tiếp được nhưng Config Client lỗi | Khác biệt phiên bản hoặc client tự dựng URL không chuyển slash | Kiểm tra URL client gửi và cách xử lý label của phiên bản đó |
| Branch có nhiều slash vẫn lỗi | Chỉ thay một slash | Thay mọi slash bằng (_) |

## 8. Kiểm thử tự động cho label có slash

Nên có kiểm thử tích hợp cho ít nhất một branch hoặc tag có slash. Mục tiêu là xác minh cả API trực tiếp lẫn Config Client chọn được đúng revision.

Ví dụ kiểm tra thủ công trong môi trường test:

~~~bash
# Git ref thật: feature/checkout
curl --fail --show-error 'http://localhost:8888/order-service/test/feature(_)checkout'
~~~

Nếu có thể tạo fixture Git cho kiểm thử, hãy đặt một giá trị dễ nhận biết trong từng label:

~~~yaml
config:
  revision-marker: feature-checkout
~~~

Sau đó kiểm tra response có config.revision-marker=feature-checkout. Tạo thêm một label khác với marker khác để phát hiện trường hợp server vô tình trả cấu hình từ branch mặc định.

Với Config Client, khởi động context kiểm thử bằng spring.cloud.config.label=feature/checkout, rồi xác nhận giá trị được nạp đúng. Kiểm thử nên chạy cùng phiên bản Spring Cloud Config Client và Server mà hệ thống triển khai; không nên suy ra hành vi của một phiên bản chỉ từ kết quả của phiên bản khác.

## 9. Quy ước vận hành cho Git label

Để giảm lỗi khi phát triển nhiều nhánh cấu hình, nhóm có thể thống nhất:

- Dùng tên branch có cấu trúc rõ ràng như feature/..., release/... hoặc hotfix/....
- Ghi nhận Git ref thật trong tài liệu triển khai và pull request.
- Khi gọi Config Server REST API trực tiếp, luôn chuyển slash thành (_).
- Khi dùng Config Client, cấu hình Git label theo cách mà phiên bản client hỗ trợ; kiểm tra request khi nâng cấp hoặc đổi chế độ bootstrap.
- Tránh tạo Git ref chứa nguyên chuỗi đặc biệt (_), vì nó được dùng làm ký hiệu thay slash trong path và có thể gây mơ hồ khi ánh xạ.
- Ghi nhận label và commit SHA thực tế khi triển khai để có thể tái lập hoặc rollback.
- Bảo vệ Config Server endpoint bằng xác thực, phân quyền và TLS; không để endpoint cấu hình mở công khai nếu không có kiểm soát.

## 10. Tự kiểm tra

1. Vì sao branch feature/checkout không nên được đặt nguyên vào đoạn label của URL /{application}/{profile}/{label}?
2. Với Git label release/2026/11, URL path phải dùng chuỗi nào?
3. Token (_) có đổi tên branch trong Git hay chỉ thay đổi cách biểu diễn trong HTTP path?
4. Khi nào bạn cần tự thay slash bằng (_) và khi nào Config Client có thể thực hiện bước chuyển đổi?
5. Nếu request dùng đúng token nhưng vẫn không tìm thấy branch, cần kiểm tra những thành phần nào?
6. Vì sao không nên mặc định dùng %2F để thay thế quy ước (_)?

Hãy tạo một branch thử nghiệm có tên feature/config-label-demo, thêm một thuộc tính nhận diện vào cấu hình, rồi gọi Config Server bằng URL chứa feature(_)config-label-demo. Sau đó khởi động Config Client với label tương ứng, kiểm tra giá trị nhận được và đối chiếu label/version trong response để xác nhận cả hai đường đi cùng trỏ đến một Git ref.

## Tài liệu tham khảo

- [Spring Cloud Config — Git Backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/git-backend.html)
- [Spring Cloud Config — Client: Locating Remote Configuration Resources](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [ConfigServerConfigDataLoader.java — Spring Cloud Config source](https://github.com/spring-cloud/spring-cloud-config/blob/main/spring-cloud-config-client/src/main/java/org/springframework/cloud/config/client/ConfigServerConfigDataLoader.java)

