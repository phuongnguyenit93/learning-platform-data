# Quốc tế hóa mô tả bằng rest-messages.properties trong Spring Data REST

## Mục tiêu

Spring Data REST cung cấp metadata mô tả repository, resource và các thuộc tính domain. Bạn có thể viết các mô tả này trong message bundle để API trả về nội dung phù hợp với ngôn ngữ của client.

Cơ chế này hữu ích khi cùng một API phục vụ nhiều nhóm người dùng, chẳng hạn giao diện tiếng Việt và tiếng Anh. Bạn có thể bản địa hóa phần mô tả metadata mà không phải thay đổi tên endpoint, tên thuộc tính hay dữ liệu nghiệp vụ.

Sau bài này, bạn có thể:

- Tạo message bundle cho mô tả tài nguyên Spring Data REST.
- Khai báo các message key theo resource và thuộc tính.
- Tách nội dung theo locale bằng hậu tố ngôn ngữ.
- Gửi request với Accept-Language và kiểm tra metadata được trả về.

## 1. Mô tả resource trong Spring Data REST là gì?

Khi xuất bản repository, Spring Data REST cung cấp các tài nguyên và metadata để client khám phá API. Các mô tả giúp client hiểu ý nghĩa của resource hoặc thuộc tính mà không cần đọc mã nguồn server.

Ví dụ, ứng dụng quản lý người dùng có repository được xuất bản tại collection resource **/people**, với domain type **Person** gồm các thuộc tính **firstName** và **lastName**.

Các mô tả có thể cung cấp thông tin như:

- Resource **people** chứa danh sách người dùng.
- Resource **person** đại diện cho một người dùng.
- Thuộc tính **firstName** lưu tên.
- Thuộc tính **lastName** lưu họ.

Spring Data REST có thể đưa các mô tả này vào metadata/profile của API, chẳng hạn ALPS. Client có thể đọc metadata để hiểu resource và các thuộc tính được cung cấp.

Cần phân biệt mô tả metadata với dữ liệu entity. Quốc tế hóa mô tả **firstName** không làm thay đổi giá trị thực tế của trường **firstName** trong JSON response.

## 2. Tạo rest-messages.properties

Tạo file **rest-messages.properties** trong thư mục resources của ứng dụng:

~~~text
src/
└── main/
    └── resources/
        └── rest-messages.properties
~~~

Ví dụ nội dung mặc định bằng tiếng Anh:

~~~properties
rest.description.people=Collection of people available in the system.
rest.description.person=An individual person resource.
rest.description.person.firstName=The first name of the person.
rest.description.person.lastName=The last name of the person.
~~~

Các key có tiền tố **rest.description.**. Phần tiếp theo xác định resource hoặc thuộc tính cần mô tả.

Trong ví dụ:

- **rest.description.people** mô tả collection resource có relation **people**.
- **rest.description.person** mô tả resource của domain type **Person**.
- **rest.description.person.firstName** mô tả thuộc tính **firstName**.
- **rest.description.person.lastName** mô tả thuộc tính **lastName**.

Tên relation và tên domain type phụ thuộc vào cách ứng dụng xuất bản repository. Nếu bạn tùy chỉnh repository path, relation hoặc tên thuộc tính, hãy dùng đúng tên mà Spring Data REST đang sử dụng khi phân giải mô tả. Không tự suy ra key từ URL nếu relation đã được tùy chỉnh.

## 3. Tạo message bundle theo từng ngôn ngữ

Java ResourceBundle hỗ trợ các file có hậu tố locale. Bạn có thể giữ một bundle mặc định và tạo file riêng cho từng ngôn ngữ.

Ví dụ cấu trúc:

~~~text
src/main/resources/
├── rest-messages.properties
├── rest-messages_en.properties
└── rest-messages_vi.properties
~~~

File **rest-messages_vi.properties** chứa mô tả tiếng Việt:

~~~properties
rest.description.people=Danh sách người dùng có trong hệ thống.
rest.description.person=Thông tin tài nguyên của một người dùng.
rest.description.person.firstName=Tên của người dùng.
rest.description.person.lastName=Họ của người dùng.
~~~

File **rest-messages_en.properties** có thể chứa nội dung tiếng Anh:

~~~properties
rest.description.people=Collection of people available in the system.
rest.description.person=An individual person resource.
rest.description.person.firstName=The first name of the person.
rest.description.person.lastName=The last name of the person.
~~~

File không có hậu tố locale, **rest-messages.properties**, đóng vai trò bundle mặc định. Khi một locale không có message tương ứng, cơ chế ResourceBundle có thể fallback về bundle mặc định.

Bạn không cần tạo lại cấu trúc key cho từng ngôn ngữ. Giữ nguyên key và chỉ dịch phần value. Nhờ đó client vẫn nhận cùng một API metadata structure dù nội dung mô tả thay đổi theo locale.

## 4. Đăng ký basename trong Spring Boot

Ứng dụng cần có MessageSource sử dụng basename **rest-messages** để các message trong bundle được phân giải.

Có thể khai báo trong **application.yml**:

~~~yaml
spring:
  messages:
    basename: rest-messages
    encoding: UTF-8
~~~

Nếu ứng dụng đã sử dụng các bundle khác, hãy giữ chúng trong danh sách basename thay vì ghi đè cấu hình hiện có. Ví dụ:

~~~yaml
spring:
  messages:
    basename: messages,rest-messages
    encoding: UTF-8
~~~

Với cấu hình này, Spring Boot đăng ký các bundle theo basename đã khai báo. Spring Data REST sử dụng MessageSource để phân giải các mô tả metadata tương ứng.

Nếu ứng dụng tự khai báo bean **MessageSource**, hãy bảo đảm bean đó cũng có basename **rest-messages** và hỗ trợ các locale cần dùng. Tránh tạo nhiều MessageSource độc lập khiến bundle được đăng ký ở một nơi nhưng Spring Data REST lại sử dụng nguồn message khác.

Lưu file properties bằng UTF-8 để nội dung tiếng Việt được đọc đúng. Với cấu hình encoding UTF-8, các ký tự có dấu được giữ nguyên khi message được phân giải.

## 5. Client yêu cầu ngôn ngữ bằng Accept-Language

Client có thể gửi HTTP header **Accept-Language** để chỉ định locale mong muốn.

Ví dụ yêu cầu metadata tiếng Việt:

~~~http
GET /profile
Accept: application/alps+json
Accept-Language: vi
~~~

Ví dụ yêu cầu metadata tiếng Anh:

~~~http
GET /profile
Accept: application/alps+json
Accept-Language: en
~~~

Nếu API cung cấp profile link trong response, client nên sử dụng URL profile do server trả về. Đường dẫn **/profile** ở trên là ví dụ với cấu hình phổ biến; base path và cách xuất bản metadata có thể thay đổi theo ứng dụng.

Spring MVC thường có thể xác định locale từ header **Accept-Language**. Nếu ứng dụng tùy chỉnh cơ chế phân giải locale, hãy kiểm tra cấu hình đó để bảo đảm locale của request được truyền tới MessageSource.

Khi locale là **vi**, các message key có bản dịch trong **rest-messages_vi.properties** sẽ được phân giải thành tiếng Việt. Khi locale là **en**, bundle tiếng Anh được sử dụng nếu có.

## 6. Kiểm tra mô tả đã được bản địa hóa

Sau khi tạo bundle và cấu hình MessageSource, kiểm tra theo các bước sau:

1. Khởi động ứng dụng và xác nhận repository resource được xuất bản.
2. Gửi request tới profile hoặc metadata endpoint với **Accept-Language: vi**.
3. Tìm các descriptor có mô tả tương ứng với resource và thuộc tính đã khai báo.
4. Gửi lại request với **Accept-Language: en**.
5. So sánh giá trị mô tả để xác nhận locale đã được áp dụng.

Ví dụ, cùng một descriptor có thể có mô tả tiếng Việt trong request thứ nhất và tiếng Anh trong request thứ hai. Key, relation và cấu trúc metadata vẫn giữ nguyên.

Nếu nội dung không đổi theo locale, kiểm tra:

- Tên file có đúng quy ước **rest-messages_vi.properties** hoặc **rest-messages_en.properties** không.
- Basename **rest-messages** đã được đăng ký trong MessageSource chưa.
- Key có khớp với resource relation, domain type và tên thuộc tính được xuất bản không.
- Header **Accept-Language** có được gửi tới đúng endpoint không.
- Ứng dụng có custom LocaleResolver hoặc MessageSource làm thay đổi cách phân giải locale không.
- Bundle đã được đóng gói trong classpath sau khi build chưa.

## 7. Phạm vi của rest-messages.properties

**rest-messages.properties** phục vụ các mô tả metadata mà Spring Data REST tra cứu qua MessageSource. Không nên xem đây là cơ chế dịch tự động cho toàn bộ nội dung API.

| Nội dung | Cách xử lý phù hợp |
|---|---|
| Mô tả repository/resource/property của Spring Data REST | Dùng các key mô tả trong rest-messages bundle |
| Giá trị dữ liệu entity, ví dụ tên người dùng | Lưu và trả về dữ liệu theo nghiệp vụ; không tự dịch bằng resource description |
| Thông báo validation | Dùng message bundle và cơ chế validation của Spring |
| Thông báo trong controller tự viết | Dùng MessageSource hoặc cơ chế i18n của ứng dụng |
| URL, repository path, relation name | Cấu hình API; không được đổi chỉ vì dịch mô tả |

Một số điểm cần lưu ý:

- **Giữ key ổn định:** các locale phải dùng cùng key để client nhận cùng cấu trúc metadata.
- **Dịch value, không dịch key:** không đổi **rest.description.person.firstName** thành key tiếng Việt.
- **Có bundle mặc định:** cung cấp message mặc định để tránh thiếu mô tả khi locale chưa được hỗ trợ.
- **Kiểm tra fallback:** nếu một key chưa có trong bundle theo locale, kiểm tra nội dung fallback và bổ sung bản dịch còn thiếu.
- **Không nhầm locale với múi giờ:** Accept-Language chọn ngôn ngữ, không tự thay đổi timezone hoặc định dạng dữ liệu nghiệp vụ.
- **Cập nhật tài liệu client:** nếu client hiển thị mô tả metadata, cần xác định cách gửi locale nhất quán trong các request.

## Ghi nhớ

Để quốc tế hóa mô tả metadata trong Spring Data REST, tạo **rest-messages.properties**, khai báo các key **rest.description.*** cho resource và thuộc tính, sau đó bổ sung bundle theo locale như **rest-messages_vi.properties** và **rest-messages_en.properties**. Đăng ký basename **rest-messages** trong MessageSource và gửi **Accept-Language** từ client. Cách này bản địa hóa phần mô tả metadata mà vẫn giữ nguyên key và cấu trúc API.