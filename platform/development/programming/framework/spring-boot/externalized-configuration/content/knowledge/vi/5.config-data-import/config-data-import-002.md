# Nhập tệp properties hoặc YAML từ classpath và hệ thống tệp

Spring Boot hỗ trợ **Config Data Import** để một tệp cấu hình đang được nạp có thể khai báo thêm các tệp `.properties` hoặc `.yml`/`.yaml` làm nguồn cấu hình cho ứng dụng. Tính năng này đặc biệt hữu ích khi muốn tách cấu hình chung, thông số của một nhóm chức năng, cấu hình vận hành bên ngoài JAR hoặc những giá trị tùy môi trường thành các tệp có mục đích rõ ràng.

Trọng tâm của bài là khóa **`spring.config.import`**: viết ở đâu, nhập tệp từ **classpath** và **file system** như thế nào, đường dẫn được phân giải ra sao, nguồn nhập có độ ưu tiên gì, cách xử lý khi tệp không tồn tại và mối liên hệ với profile. Các ví dụ dùng cơ chế Config Data của Spring Boot 2.4 trở lên, bao gồm Spring Boot 3.x.

## 1. Bản đồ luồng nạp Config Data

~~~text
Tham số khởi động / môi trường chạy
        |
        v
Spring Boot chuẩn bị Environment và tìm Config Data ban đầu
        |
        v
application.properties / application.yml
        |
        +-- spring.config.import=classpath:defaults/client.yml
        |              |
        |              +-- Đọc tệp nằm trong classpath
        |
        +-- spring.config.import=optional:file:./config/local.properties
                       |
                       +-- Đọc tệp ngoài ứng dụng từ hệ thống tệp
        |
        v
Hợp nhất PropertySource theo thứ tự ưu tiên và profile đang active
        |
        v
Environment -> @Value / @ConfigurationProperties / điều kiện cấu hình
        |
        v
Các bean sử dụng giá trị hiệu lực
~~~

Một import là một phần của **quá trình chuẩn bị cấu hình khi ứng dụng khởi động**. Nó không phải lệnh Java đọc tệp trong service và cũng không phải cơ chế tự động theo dõi sự thay đổi của tệp khi ứng dụng đang chạy. Spring Boot xử lý vị trí nhập, tài liệu cấu hình và profile trước khi những bean phụ thuộc vào cấu hình được khởi tạo.

**Một câu cần nhớ:** tệp đang được nạp có thể khai báo `spring.config.import` để yêu cầu Spring Boot nạp thêm Config Data tại một vị trí xác định, sau đó kết hợp các key của tệp nhập vào `Environment`.

## 2. Điều kiện để import hoạt động

Một project Spring Boot thường có tệp gốc:

~~~text
order-service/
  src/
    main/
      java/
      resources/
        application.yml
~~~

Tệp gốc ở `src/main/resources` được đóng gói vào classpath khi build ứng dụng Java theo cấu trúc thông dụng. Spring Boot tự nhận diện những tệp `application.properties` hoặc `application.yml` ở các vị trí cấu hình mặc định.

Để **nhập thêm một tệp**, đặt thuộc tính `spring.config.import` trong một tài liệu Config Data đang được Spring Boot nạp. Ví dụ:

~~~properties
# application.properties
spring.config.import=classpath:defaults/client.properties
~~~

hoặc:

~~~yaml
# application.yml
spring:
  config:
    import: "classpath:defaults/client.yml"
~~~

Từ đây, Spring Boot tìm và nạp vị trí được khai báo. Tệp nhập không cần có tên `application.properties` hoặc `application.yml`: có thể dùng tên theo mục đích như `client-defaults.yml`, `mail.properties` hoặc `regional-overrides.yaml`.

Tuy nhiên, **chỉ đặt một tệp ở classpath hoặc một thư mục ngoài JAR chưa đủ để Spring Boot tự import tệp đó**. Tệp phải được tìm qua cơ chế Config Data mặc định, được chỉ định bằng một cấu hình location thích hợp hoặc được tham chiếu bởi `spring.config.import`.

## 3. Hai nguồn đường dẫn thường gặp: classpath và file

| Prefix | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `classpath:` | Tìm tài nguyên qua classpath của ứng dụng | `classpath:defaults/client.yml` |
| `file:` | Tìm tệp theo đường dẫn hệ thống tệp | `file:./config/local.properties` |
| Không có prefix | Vị trí tương đối được giải quyết dựa trên vị trí của tệp đang khai báo import | `client-overrides.yml` |
| `optional:` đứng trước vị trí | Cho phép bỏ qua khi vị trí không tồn tại | `optional:file:./config/local.properties` |

### 3.1. Nhập từ classpath

Giả sử project có:

~~~text
order-service/
  src/main/resources/
    application.yml
    defaults/
      client.yml
      cache.properties
~~~

Trong `application.yml`:

~~~yaml
spring:
  config:
    import: "classpath:defaults/client.yml"
~~~

Trong `src/main/resources/defaults/client.yml`:

~~~yaml
app:
  client:
    base-url: https://api.example.test
    connect-timeout: 3s
    max-retries: 2
~~~

Spring Boot nạp những key như `app.client.base-url` và `app.client.connect-timeout` vào hệ thống cấu hình. Khi ứng dụng được đóng gói, `defaults/client.yml` có thể nằm trong JAR; cú pháp `classpath:` vẫn áp dụng vì class loader của ứng dụng tìm tài nguyên đó.

Một phiên bản tệp properties cũng hợp lệ:

~~~properties
# src/main/resources/defaults/cache.properties
app.cache.ttl=20m
app.cache.maximum-size=64MB
~~~

~~~properties
# application.properties
spring.config.import=classpath:defaults/cache.properties
~~~

Với `classpath:`, Spring Boot tìm **tài nguyên mà class loader nhìn thấy**, không tìm tệp theo đường dẫn tương đối của thư mục mà người dùng đang đứng khi gọi `java -jar`.

### 3.2. Nhập từ hệ thống tệp

Giả sử tổ chức tệp triển khai như sau:

~~~text
order-service/
  order-service.jar
  config/
    client-overrides.properties
~~~

Trong tài liệu Config Data chính:

~~~properties
spring.config.import=optional:file:./config/client-overrides.properties
~~~

Tệp nằm bên ngoài JAR:

~~~properties
# ./config/client-overrides.properties
app.client.base-url=https://internal-api.example.test
app.client.connect-timeout=800ms
~~~

Trong ví dụ chạy từ thư mục `order-service/`:

~~~bash
java -jar order-service.jar
~~~

`file:./config/client-overrides.properties` tham chiếu tệp theo đường dẫn file system tương đối với **working directory của tiến trình**. Nếu chạy cùng JAR từ một working directory khác, `./config/...` có thể trỏ đến vị trí khác. Vì vậy, khi cấu hình triển khai không tìm thấy, cần kiểm tra thư mục làm việc thực tế của tiến trình, container hoặc service manager.

Có thể dùng đường dẫn tuyệt đối trên một hệ thống Unix-like:

~~~properties
spring.config.import=file:/etc/order-service/client-overrides.yml
~~~

Đường dẫn tuyệt đối khác giữa Linux, macOS và Windows. Với Docker/Kubernetes, hãy xác minh vị trí mount có thật **trong filesystem của container**; đường dẫn trên máy host không tự xuất hiện trong container nếu không được mount.

## 4. Viết spring.config.import trong properties và YAML

### Một tệp

~~~properties
spring.config.import=classpath:config/client.properties
~~~

~~~yaml
spring:
  config:
    import: "classpath:config/client.yml"
~~~

### Nhiều tệp trong một khai báo

`spring.config.import` có thể nhận danh sách vị trí được phân cách bởi dấu phẩy trong properties:

~~~properties
spring.config.import=classpath:defaults/client.properties,optional:file:./config/client-local.properties
~~~

Trong YAML, có thể dùng chuỗi chứa dấu phẩy:

~~~yaml
spring:
  config:
    import: "classpath:defaults/client.yml,optional:file:./config/client-local.yml"
~~~

Hoặc danh sách YAML để mỗi location một dòng:

~~~yaml
spring:
  config:
    import:
      - "classpath:defaults/client.yml"
      - "optional:file:./config/client-local.yml"
~~~

Hai cách YAML trên đều mô tả các vị trí import. Với các vị trí chứa ký tự `:`, dấu nháy trong YAML giúp người đọc và parser thấy đây là chuỗi. Trong tệp `.properties`, dấu `:` sau dấu `=` đầu tiên là một phần của value và không cần nháy.

**Thứ tự các import trong cùng danh sách có ý nghĩa khi key trùng nhau:** những vị trí nhập về sau được ưu tiên hơn những vị trí nhập trước, theo quy tắc Config Data Import. Cần xem cả nguồn cấu hình bên ngoài và profile active trước khi xác định giá trị cuối cùng toàn ứng dụng.

## 5. Ví dụ hoàn chỉnh: cấu hình mặc định trong JAR và override ngoài JAR

Đây là tình huống phổ biến khi cùng một artifact được chạy ở nhiều môi trường.

~~~text
order-service/
  src/main/resources/
    application.yml
    defaults/
      client.yml
  config/
    client-local.yml
~~~

**Bước 1 — Tệp chính `application.yml`:**

~~~yaml
spring:
  application:
    name: order-service
  config:
    import:
      - "classpath:defaults/client.yml"
      - "optional:file:./config/client-local.yml"

app:
  client:
    connect-timeout: 5s
    max-retries: 1
~~~

**Bước 2 — Giá trị mặc định trong classpath:**

~~~yaml
# src/main/resources/defaults/client.yml
app:
  client:
    base-url: https://api.example.test
    connect-timeout: 3s
    max-retries: 2
~~~

**Bước 3 — Tệp override bên ngoài JAR:**

~~~yaml
# ./config/client-local.yml
app:
  client:
    base-url: http://localhost:8090
    connect-timeout: 750ms
~~~

Nếu tiến trình chạy với working directory chứa thư mục `./config` trên và không có nguồn ưu tiên cao hơn, bảng giá trị hiệu lực trong ví dụ là:

| Key | `application.yml` | `defaults/client.yml` | `config/client-local.yml` | Giá trị hiệu lực |
| --- | --- | --- | --- | --- |
| `app.client.base-url` | Không khai báo | `https://api.example.test` | `http://localhost:8090` | `http://localhost:8090` |
| `app.client.connect-timeout` | `5s` | `3s` | `750ms` | `750ms` |
| `app.client.max-retries` | `1` | `2` | Không khai báo | `2` |

Điểm rất dễ nhầm: **Config Data được import có độ ưu tiên cao hơn tài liệu đã khai báo import**. Vì vậy, `max-retries=2` trong `defaults/client.yml` thắng `max-retries=1` trong `application.yml` của ví dụ. Import thứ hai lại có thể ghi đè key từ import thứ nhất.

Trong ví dụ này, nếu `./config/client-local.yml` không tồn tại, từ khóa `optional:` cho phép bỏ qua vị trí đó; các giá trị còn lại vẫn được nạp bình thường. Khi đó `app.client.base-url` là `https://api.example.test` và `app.client.connect-timeout` là `3s`, giả sử không bị nguồn khác ghi đè.

Để tệp ngoại vi thực sự được dùng, phải giữ đúng **đường dẫn** và **working directory** trong lệnh chạy. Nếu đang làm việc với file source trong IDE, tệp `./config/client-local.yml` không nhất thiết được copy vào JAR và không cần copy nếu muốn giữ khả năng tùy biến ngoài artifact.

## 6. Thứ tự ưu tiên: import thắng gì và có thể bị gì ghi đè?

Spring Boot chuẩn bị những `PropertySource` có thứ tự ưu tiên. Khi cùng một key nằm trong nhiều nguồn, giá trị thuộc nguồn có ưu tiên cao nhất sẽ là giá trị mà ứng dụng nhận được.

Đối với import thông thường:

1. Tài liệu được import được đặt vào chuỗi Config Data gần tài liệu khai báo `spring.config.import`.
2. **Giá trị từ tài liệu được import được ưu tiên hơn giá trị trong tài liệu gọi import**.
3. Nếu một khai báo import nhiều vị trí, **những import khai báo sau có thể ghi đè giá trị từ import trước**.
4. Nếu một location nhập tệp có phiên bản theo profile, việc kích hoạt profile có thể thay đổi tập tài liệu được nạp và kết quả precedence.
5. Những nguồn ngoài nhóm Config Data, chẳng hạn command-line arguments, có thể có ưu tiên cao hơn và ghi đè giá trị đang có.

Ví dụ:

~~~properties
# application.properties
spring.config.import=classpath:config/common.properties
app.scheduler.enabled=false
~~~

~~~properties
# config/common.properties
app.scheduler.enabled=true
~~~

Với hai tài liệu này và không có nguồn khác ghi đè, Spring Boot nhìn thấy `app.scheduler.enabled=true` là giá trị hiệu lực. Đừng suy luận theo kiểu “vì `application.properties` là file chính nên dòng trong đó luôn thắng”.

Khi chạy:

~~~bash
java -jar order-service.jar --app.scheduler.enabled=false
~~~

Đối số command-line có thể ghi đè để giá trị hiệu lực là `false` trong tình huống này.

### Import có bị nạp lặp vô hạn không?

Spring Boot theo dõi các tài liệu Config Data được import và không nạp cùng một tài liệu lặp vô hạn chỉ vì có nhiều nơi tham chiếu cùng location. Điều đó không có nghĩa mọi graph import phức tạp đều nên được sử dụng: một cấu trúc ít tầng, đường dẫn minh bạch và không có vòng tham chiếu về mặt thiết kế vẫn dễ bảo trì hơn.

Một cấu hình khó hiểu thường phát sinh khi nhiều tệp cùng định nghĩa một key và lồng nhiều cấp import. Hãy quy định vai trò từng tệp như `defaults`, `region` và `local override` để giải thích được nguồn thắng.

## 7. Đường dẫn cố định và đường dẫn tương đối

`spring.config.import` hỗ trợ cách viết **fixed location** và **import-relative location**.

### Fixed location

Một vị trí được coi là fixed khi bắt đầu bằng `/` hoặc có prefix chỉ nguồn như `classpath:` hay `file:`:

~~~properties
spring.config.import=classpath:defaults/client.yml
~~~

~~~properties
spring.config.import=file:./config/client.yml
~~~

Vị trí cố định được giải quyết theo cơ chế của prefix thay vì dựa trên vị trí của tài liệu đang khai báo import.

### Import-relative location

Vị trí không có prefix có thể được giải quyết **tương đối với thư mục của tài liệu đang nhập nó**.

Giả sử tệp classpath:

~~~text
src/main/resources/
  application.properties
  features/
    checkout.properties
    rules.properties
~~~

Tệp `features/checkout.properties`:

~~~properties
spring.config.import=rules.properties
app.checkout.enabled=true
~~~

Khi `features/checkout.properties` đã được nạp trong classpath và khai báo `rules.properties`, Spring Boot giải quyết tham chiếu tương đối tại cùng vị trí thư mục tương ứng, tức tài nguyên `features/rules.properties`.

Nếu cùng câu `spring.config.import=rules.properties` nằm trong một tệp khác ở thư mục khác, vị trí được suy ra có thể khác. Đây là lý do phải biết **tệp nào khai báo import**, không chỉ copy giá trị import từ một ví dụ sang vị trí khác.

**Để tránh nhầm khi hướng dẫn triển khai:** dùng prefix tường minh `classpath:` hoặc `file:` nếu muốn mô tả chính xác nguồn và đường dẫn; dùng import-relative có chủ đích khi các tệp được đóng gói thành một nhóm cùng thư mục.

## 8. Tệp không tồn tại: optional: và lỗi khởi động

Không phải mọi file import đều luôn có mặt. Một cấu hình mặc định đi cùng ứng dụng nên thường là bắt buộc; file override riêng cho developer hoặc từng môi trường thường có thể là tùy chọn.

### Import bắt buộc

~~~properties
spring.config.import=file:./config/required-client.properties
~~~

Nếu vị trí bắt buộc không được tìm thấy, Spring Boot có thể dừng khởi động với lỗi liên quan đến `ConfigDataLocationNotFoundException` hoặc thông báo cho biết không thể tìm thấy location cần nạp. Điều này giúp tránh âm thầm chạy với cấu hình thiếu.

### Import tùy chọn

~~~properties
spring.config.import=optional:file:./config/local.properties
~~~

Nếu tệp `./config/local.properties` không tồn tại, Spring Boot **bỏ qua location đó** thay vì dừng chỉ vì thiếu location. Nhưng `optional:` **không sửa lỗi cú pháp**, lỗi truy cập nghiêm trọng hoặc giá trị bắt buộc bị thiếu trong bean sau khi nạp. Nó chỉ diễn đạt khả năng vắng mặt của nguồn cấu hình.

Có thể dùng `optional:` với classpath:

~~~properties
spring.config.import=optional:classpath:defaults/preview.properties
~~~

Quy tắc sử dụng đề xuất:

| Loại tệp | Cách import thường phù hợp | Lý do |
| --- | --- | --- |
| Default thiết yếu được đóng gói cùng ứng dụng | `classpath:defaults/client.yml` | Thiếu tệp là sai đóng gói |
| Override riêng cho máy lập trình | `optional:file:./config/local.properties` | Máy khác có thể không có |
| Cấu hình bắt buộc do môi trường triển khai cấp | `file:/etc/order-service/runtime.properties` | Nên thất bại nếu thiếu |
| Tệp thử nghiệm không phải môi trường nào cũng dùng | `optional:classpath:config/experiment.yml` | Cho phép vắng mặt có chủ đích |

Việc chọn `optional:` là một quyết định vận hành: nếu hệ thống không thể chạy an toàn khi không có tệp, hãy để import bắt buộc và định nghĩa validation cho những key cần thiết.

## 9. Profile ảnh hưởng thế nào tới tệp được import?

Config Data Import được tích hợp vào quá trình xử lý **profile-specific configuration** của Spring Boot. Khi một import trỏ tới tài nguyên có bản theo profile phù hợp, Spring Boot có thể cân nhắc cả biến thể profile-specific của location đó.

Ví dụ:

~~~text
src/main/resources/
  application.properties
  config/
    client.properties
    client-dev.properties
    client-prod.properties
~~~

Tệp chính:

~~~properties
spring.config.import=classpath:config/client.properties
~~~

Tệp cơ sở:

~~~properties
# config/client.properties
app.client.base-url=https://api.example.test
app.client.connect-timeout=3s
~~~

Tệp theo profile `dev`:

~~~properties
# config/client-dev.properties
app.client.base-url=http://localhost:8090
app.client.connect-timeout=500ms
~~~

Tệp theo profile `prod`:

~~~properties
# config/client-prod.properties
app.client.base-url=https://internal-api.example.test
app.client.connect-timeout=2s
~~~

Khi chạy:

~~~bash
java -jar order-service.jar --spring.profiles.active=dev
~~~

Spring Boot xem xét biến thể phù hợp với profile đang active và có thể dùng các giá trị từ `client-dev.properties`. Khi profile `prod` active, biến thể `client-prod.properties` được xét.

Nếu một giá trị xuất hiện trong nhiều tài liệu hoặc có nhiều profile cùng active, kết quả cần được đánh giá theo quy tắc Config Data và thứ tự profile thực tế. **Profile không đồng nghĩa với việc một tệp bất kỳ có hậu tố `-prod` tự động được nạp:** tệp vẫn phải nằm trong phạm vi của location được Spring Boot nạp hoặc import.

### Import chỉ dành cho một profile

Có thể khai báo import trong tài liệu YAML được kích hoạt bởi profile:

~~~yaml
# application.yml
spring:
  application:
    name: order-service
  config:
    import: "classpath:defaults/client.yml"

---
spring:
  config:
    activate:
      on-profile: dev
    import: "optional:file:./config/dev-client.yml"
~~~

Phần dưới dấu phân cách `---` chỉ được áp dụng khi điều kiện `dev` phù hợp. Lúc đó Spring Boot mới xét import `./config/dev-client.yml` của tài liệu này.

Trong YAML, dấu `---` là dấu phân cách tài liệu. Trong `application.properties`, Spring Boot hỗ trợ dấu phân cách tài liệu Config Data đặc biệt dạng `#---`:

~~~properties
spring.config.import=classpath:defaults/client.properties

#---
spring.config.activate.on-profile=dev
spring.config.import=optional:file:./config/dev-client.properties
~~~

Đừng đặt `spring.profiles.active` trong tài liệu đã bị ràng buộc bằng `spring.config.activate.on-profile`; cơ chế kích hoạt profile có ràng buộc về những nguồn được phép xác định active profile.

## 10. Khi cần gợi ý phần mở rộng cho tệp không có extension

Một số nguồn cấu hình được mount vào container dưới tên tệp không có đuôi `.properties` hoặc `.yaml`. Spring Boot Config Data hỗ trợ **extension hint** để giải thích định dạng cho tệp được import.

Ví dụ, tệp ngoài JAR tại `/etc/order-service/client-config` thực chất có nội dung YAML:

~~~yaml
app:
  client:
    connect-timeout: 2s
~~~

Có thể import bằng:

~~~properties
spring.config.import=file:/etc/order-service/client-config[.yaml]
~~~

Cú pháp `[.yaml]` là một **hint về phần mở rộng**, không phải yêu cầu đặt tên thực tế của tệp thành `client-config[.yaml]`. Nó cho Spring Boot biết cần đọc nội dung theo định dạng YAML dù tên tệp không có extension.

Nếu tệp có đuôi hợp lệ như `client.properties`, `client.yml` hoặc `client.yaml` thì thông thường không cần hint.

## 11. So sánh import với spring.config.location và additional-location

Ba cơ chế liên quan nhưng có mục đích khác nhau:

| Cơ chế | Vai trò | Ví dụ |
| --- | --- | --- |
| `spring.config.import` | Một tài liệu Config Data đang được nạp khai báo nguồn bổ sung cần nhập | `spring.config.import=classpath:defaults/client.yml` |
| `spring.config.location` | Chỉ định các location dùng để tìm Config Data mặc định, thay thế tập vị trí mặc định theo cơ chế của Boot | `--spring.config.location=file:./deploy/application.yml` |
| `spring.config.additional-location` | Thêm các location bên cạnh những vị trí mặc định | `--spring.config.additional-location=optional:file:./extra-config/` |

Ví dụ truyền location khi khởi động:

~~~bash
java -jar order-service.jar --spring.config.additional-location=optional:file:./extra-config/
~~~

**Vì sao không khai báo `spring.config.location` trong chính `application.yml`?** Các thuộc tính chọn nơi tìm Config Data phải được xử lý rất sớm, trước khi Spring Boot biết sẽ đọc tệp `application.yml` nào. Vì vậy, chúng được đặt ở nguồn có sẵn từ đầu, như tham số dòng lệnh, system property hoặc biến môi trường thích hợp. Ngược lại, `spring.config.import` được thiết kế để nằm trong tài liệu đã được nạp và kéo thêm tài liệu liên quan.

Nếu muốn một tệp gốc import các tệp cấu hình theo chức năng, `spring.config.import` thường phù hợp. Nếu muốn môi trường triển khai quyết định **thư mục tìm cấu hình ban đầu**, hãy xem xét `spring.config.additional-location` hoặc `spring.config.location`.

## 12. Một ứng dụng Java đọc giá trị đã nhập ra sao?

Sau khi Spring Boot nạp các location, phần lớn mã ứng dụng không cần biết key đến từ classpath hay file system. Tất cả có thể được tra cứu qua `Environment`:

~~~java
import java.time.Duration;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ClientSettingsReader {
    private final Environment environment;

    public ClientSettingsReader(Environment environment) {
        this.environment = environment;
    }

    public Duration timeout() {
        return environment.getProperty(
            "app.client.connect-timeout", Duration.class);
    }

    public String baseUrl() {
        return environment.getProperty("app.client.base-url");
    }
}
~~~

Với nhiều key thuộc cùng một cấu hình, nên gộp thành một bean:

~~~java
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    URI baseUrl,
    Duration connectTimeout,
    int maxRetries
) {}
~~~

Đăng ký bean properties bằng `@ConfigurationPropertiesScan` trên ứng dụng Spring Boot:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Sau khi cấu hình được bind, mã Java có thể sử dụng `ClientProperties` với những kiểu `URI`, `Duration` và `int`. Đối tượng chỉ phản ánh **giá trị hiệu lực đã được quyết định bởi quá trình cấu hình**, chứ không mang ý nghĩa “luôn lấy dữ liệu từ tệp client.yml”.

### Import không bằng cách nào tự tạo Bean?

Một dòng:

~~~properties
spring.config.import=classpath:defaults/client.properties
~~~

chỉ đưa giá trị vào hệ thống cấu hình. Nếu mã không khai báo bean, không sử dụng `@Value`, không gọi `Environment` và không có auto-configuration liên quan, các key tùy biến trong tệp vẫn không tự biến thành chức năng của ứng dụng.

Một key như `server.port` có thể được Spring Boot tự sử dụng vì framework biết nó. Còn `app.client.connect-timeout` là key do ứng dụng định nghĩa và cần được mã ứng dụng tiêu thụ.

## 13. Một bài thực hành có thể chạy từ JAR

Giả sử đã build ra `order-service.jar` với hai tệp classpath:

~~~text
src/main/resources/
  application.properties
  defaults/
    client.properties
~~~

Tệp `application.properties`:

~~~properties
spring.application.name=order-service
spring.config.import=classpath:defaults/client.properties,optional:file:./config/client-overrides.properties
app.client.max-retries=1
~~~

Tệp `defaults/client.properties`:

~~~properties
app.client.base-url=https://api.example.test
app.client.connect-timeout=3s
app.client.max-retries=2
~~~

Trường hợp A — không có tệp ngoài JAR:

~~~bash
java -jar order-service.jar
~~~

Các giá trị của nhóm client theo hai tệp trên sẽ là `base-url=https://api.example.test`, `connect-timeout=3s` và `max-retries=2`, nếu không có nguồn khác override.

Trường hợp B — tạo tệp ngoài JAR:

~~~text
./config/client-overrides.properties
~~~

Nội dung:

~~~properties
app.client.base-url=http://localhost:8090
app.client.connect-timeout=900ms
~~~

Sau đó khởi động từ đúng working directory:

~~~bash
java -jar order-service.jar
~~~

Giá trị của nhóm client trở thành `base-url=http://localhost:8090`, `connect-timeout=900ms` và `max-retries=2` theo nguyên tắc import trong ví dụ.

Trường hợp C — giữ tệp ngoài JAR và truyền thêm đối số:

~~~bash
java -jar order-service.jar --app.client.connect-timeout=100ms
~~~

Bây giờ `connect-timeout` có giá trị hiệu lực là `100ms` do command-line argument có ưu tiên cao hơn trong tình huống khởi động thông thường. Điều này chứng minh import bổ sung nguồn dữ liệu vào `Environment`, trong khi việc chọn giá trị cuối cùng còn phụ thuộc thứ tự nguồn.

## 14. Cách xử lý lỗi import bằng quy trình truy vết

Khi ứng dụng báo thiếu tệp hoặc giá trị cấu hình không như mong muốn, hãy lần theo trình tự sau.

### A. Kiểm tra đúng tên location và prefix

Đối chiếu `classpath:config/client.yml` với vị trí thực trong classpath, hoặc `file:./config/client.yml` với vị trí thực trên filesystem. Sai một cấp thư mục có thể gây lỗi tìm location.

Kiểm tra xem có viết đúng phần mở rộng `.properties`, `.yml` hoặc `.yaml` hay không. Nếu tệp cố tình không có extension, cần dùng cơ chế extension hint phù hợp.

### B. Kiểm tra tài liệu khai báo import có thật sự được nạp

Nếu `spring.config.import` nằm trong một tài liệu chỉ active với `dev` nhưng ứng dụng chạy `prod`, import đó có thể không được áp dụng. Cần xác định profile thật sự của tiến trình rồi mới kết luận tệp import bị lỗi.

Tương tự, nếu nhập tương đối, phải kiểm tra vị trí **của tài liệu khai báo import**, vì nó ảnh hưởng đến cách giải quyết đường dẫn.

### C. Kiểm tra working directory đối với file:./...

Trong container hoặc hệ thống chạy service, câu lệnh Java có thể được gọi từ một thư mục khác với thư mục chứa JAR. `file:./config/client.yml` là đường dẫn của tiến trình; nó không mặc nhiên nằm cạnh tệp JAR.

Ví dụ, trong container có thể cần mount cấu hình vào `/app/config` và cấu hình working directory là `/app`, hoặc khai báo đường dẫn tuyệt đối có thể truy cập được. Không suy ra đường dẫn host từ path trong container.

### D. Kiểm tra optional có phản ánh đúng ý định không

Thiếu tệp bắt buộc cần được sửa ở vị trí mount, đường dẫn hoặc quy trình đóng gói. Dùng `optional:` chỉ khi việc thiếu tệp là hợp lệ. Đừng thêm `optional:` cho mọi lỗi rồi bỏ qua thực tế là ứng dụng thiếu thông số quan trọng.

### E. Kiểm tra key bị ghi đè

Tệp đã nạp thành công vẫn có thể không cung cấp giá trị thắng vì có nguồn ưu tiên cao hơn: import khác được khai báo sau, biến thể theo profile, biến môi trường hay command-line.

Xác định **key canonical**, tìm tất cả nơi có thể khai báo key đó, rồi xem precedence. Ví dụ `app.client.connect-timeout` trong ba tài liệu có thể khác nhau mà không có lỗi cú pháp.

### F. Kiểm tra lỗi chuyển kiểu và validation

Các value trong YAML/properties sau import được bind sang các kiểu Java. Một chuỗi `abc` không phù hợp cho `Duration` nếu ứng dụng mong thời lượng; `max-retries=none` không phù hợp cho `int`. Đây là lỗi của dữ liệu/kiểu đích, không nhất thiết là lỗi đường dẫn import.

### G. Kiểm tra bằng công cụ quan sát có kiểm soát

Nếu ứng dụng có Spring Boot Actuator, endpoint `env` và `configprops` khi được cấu hình và bảo vệ phù hợp có thể giúp tìm nguồn và giá trị đã bind. Nhiều giá trị nhạy cảm có thể được che; tuyệt đối không công khai secrets hay in token/mật khẩu ra log để gỡ lỗi.

Một số phiên bản/cấu hình có thể cung cấp thông tin nguồn hoặc origin hữu ích khi điều tra. Cũng có thể bật logging chẩn đoán phù hợp trong môi trường thử nghiệm, tránh bật mức ghi log quá chi tiết trên môi trường production nếu không có nhu cầu.

## 15. Những hiểu nhầm hay gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Tệp ở `src/main/resources/config` sẽ tự được import vì có đuôi YAML.” | Cần thuộc vị trí tìm cấu hình hoặc được tham chiếu qua import phù hợp. |
| “Import classpath dùng đường dẫn của thư mục chạy lệnh Java.” | `classpath:` tìm tài nguyên trong classpath, kể cả tài nguyên đóng gói trong JAR. |
| “`file:./config/...` luôn tìm cạnh JAR.” | Đường dẫn `./` phụ thuộc working directory của tiến trình. |
| “Tệp chính `application.yml` luôn thắng tệp nó import.” | Giá trị nhập được ưu tiên hơn tài liệu gọi import. |
| “Tệp import không tồn tại thì Spring Boot luôn bỏ qua.” | Mặc định location bắt buộc gây lỗi; `optional:` cho phép vắng mặt có chủ đích. |
| “`optional:` sẽ bỏ qua bất kỳ lỗi cấu hình nào.” | Nó dành cho location không tồn tại, không chữa lỗi chuyển kiểu hay validation. |
| “Tệp theo profile chỉ cần tồn tại là được dùng.” | Profile và cơ chế tìm/import location phải khiến tệp được nạp. |
| “Thay tệp ngoài JAR thì bean tự cập nhật ngay.” | Config Data thường được xử lý lúc startup; refresh động cần cơ chế riêng. |
| “Import tạo sẵn bean có mọi key `app.*`.” | Import chỉ đưa key vào nguồn cấu hình; ứng dụng quyết định cách tiêu thụ. |
| “`spring.config.import` tương đương `spring.config.location`.” | Một cơ chế khai báo import trong Config Data, cơ chế kia chọn nơi tìm dữ liệu cấu hình ban đầu. |

## 16. Khi nào nên tổ chức theo classpath, khi nào theo hệ thống tệp?

**Cấu hình trong classpath** phù hợp cho những giá trị mặc định gắn với phiên bản ứng dụng: thời gian chờ đề xuất, danh sách tính năng mặc định, các thiết lập thường không cần thay đổi giữa môi trường. Điều này giúp build artifact có baseline cấu hình rõ ràng và có thể tái hiện.

**Cấu hình ngoài JAR** phù hợp cho những giá trị do môi trường triển khai quyết định: địa chỉ service, tham số dung lượng theo môi trường, cờ bật tính năng và đường dẫn tích hợp. Nó giúp dùng chung một JAR cho nhiều môi trường, còn dữ liệu cấu hình được cấp tại điểm triển khai.

Một mẫu thường gặp là:

~~~properties
spring.config.import=classpath:defaults/client.properties,optional:file:./config/client-overrides.properties
~~~

Nếu file ngoài JAR phải có trong production, nên dùng import bắt buộc tại vị trí production hoặc kiểm tra thiếu cấu hình bằng validation. Không lưu mật khẩu hay khóa API thật trong file classpath được commit vào repository; sử dụng hệ thống secrets và quyền truy cập file phù hợp của môi trường.

Với cấu hình nhạy cảm được mount thành nhiều file, Spring Boot còn có cơ chế Config Tree Import (`configtree:`). Đó là một biến thể Config Data dành cho cấu trúc thư mục chứa từng key; cơ chế này khác nhập trực tiếp một file YAML/properties và không bắt buộc khi chỉ cần hai định dạng đang học.

## 17. Bài tập tự áp dụng

### Tình huống 1: import từ classpath

Có file `src/main/resources/config/limits.properties`:

~~~properties
app.api.rate-limit=200
~~~

Trong `application.properties` khai báo:

~~~properties
spring.config.import=classpath:config/limits.properties
~~~

**Câu hỏi:** key nào được thêm vào Environment? **Đáp án:** `app.api.rate-limit` với value chuỗi `200`. Bean đọc cấu hình có thể bind value đó sang số.

### Tình huống 2: file ngoài JAR không tồn tại

~~~properties
spring.config.import=optional:file:./config/local.properties
~~~

**Câu hỏi:** thiếu tệp này có bắt buộc làm dừng startup không? **Đáp án:** không, `optional:` cho phép bỏ qua location không tồn tại. Nhưng nếu một bean vẫn yêu cầu một key chỉ tệp đó cung cấp, bean có thể lỗi sau đó.

### Tình huống 3: tệp import và tệp gọi import cùng key

~~~properties
# application.properties
spring.config.import=classpath:defaults/retry.properties
app.retry.max-attempts=1
~~~

~~~properties
# defaults/retry.properties
app.retry.max-attempts=4
~~~

**Câu hỏi:** khi không có nguồn khác ghi đè, giá trị hiệu lực là gì? **Đáp án:** `4`. Tài liệu import được ưu tiên hơn tài liệu khai báo import.

### Tình huống 4: hai vị trí import

~~~properties
spring.config.import=classpath:defaults/client.properties,optional:file:./config/local-client.properties
~~~

Giả sử hai tệp đều có `app.client.connect-timeout` và file ngoài JAR thật sự tồn tại.

**Câu hỏi:** giá trị nào thắng trong hai import? **Đáp án:** giá trị từ `./config/local-client.properties`, vì import sau có ưu tiên cao hơn trong ví dụ. Một nguồn có ưu tiên cao hơn cả nhóm Config Data vẫn có thể thay đổi kết quả cuối.

### Tình huống 5: vị trí file ngoài container

Ứng dụng chạy trong container với working directory `/app`, nhưng người triển khai mount file vào `/etc/service/runtime.yml`. Cấu hình vẫn ghi:

~~~properties
spring.config.import=file:./config/runtime.yml
~~~

**Câu hỏi:** vì sao import có thể thất bại? **Đáp án:** Spring Boot tìm `/app/config/runtime.yml`, không phải `/etc/service/runtime.yml`. Cần sửa import thành đường dẫn thật sự bên trong container hoặc chỉnh cách mount/working directory.

### Tình huống 6: profile biến thể

~~~properties
spring.config.import=classpath:config/client.properties
~~~

Có `client.properties` và `client-prod.properties`; tiến trình chạy với `--spring.profiles.active=prod`.

**Câu hỏi:** Boot có chỉ đọc file không hậu tố không? **Đáp án:** không. Config Data Import có hỗ trợ xét biến thể theo profile của các location đã nhập. Cần kiểm tra các giá trị thực sự được nạp và precedence nếu có nhiều tài liệu khác tác động.

## 18. Bảng ghi nhớ nhanh

| Mục tiêu | Cú pháp điển hình |
| --- | --- |
| Nhập properties từ classpath | `spring.config.import=classpath:config/common.properties` |
| Nhập YAML từ classpath | `spring.config.import=classpath:config/common.yml` |
| Nhập properties ngoài JAR | `spring.config.import=file:./config/overrides.properties` |
| Tệp ngoài JAR có thể vắng mặt | `spring.config.import=optional:file:./config/local.properties` |
| Nhiều import theo thứ tự | `spring.config.import=classpath:defaults/a.yml,file:./config/b.yml` |
| Định dạng YAML cho import | `spring.config.import: "classpath:defaults/a.yml"` |
| Import tương đối với tệp khai báo | `spring.config.import=other.properties` |
| Tệp không có extension chứa YAML | `spring.config.import=file:/etc/service/settings[.yaml]` |
| Thêm thư mục cấu hình từ lệnh chạy | `--spring.config.additional-location=optional:file:./extra-config/` |
| Kích hoạt profile khi chạy | `--spring.profiles.active=prod` |

Với mỗi import, hãy trả lời theo thứ tự: **tệp khai báo import nằm ở đâu → location có prefix gì → đường dẫn thực tế được giải quyết thế nào → tệp có bắt buộc không → profile nào đang active → thứ tự ưu tiên xác định key hiệu lực ra sao → bean nào sẽ dùng giá trị đó**. Đây là đường truy vết đủ cụ thể để hiểu và vận hành cấu hình được tách từ classpath hoặc hệ thống tệp.
