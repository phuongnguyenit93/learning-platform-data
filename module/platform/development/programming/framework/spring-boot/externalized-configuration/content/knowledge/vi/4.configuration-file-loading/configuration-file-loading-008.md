# Vị trí wildcard và thứ tự xét các thư mục cấu hình bên ngoài trong Spring Boot

## 1. Vì sao cần hiểu vị trí wildcard?

Trong ứng dụng Spring Boot, cùng một bản JAR có thể được chạy ở nhiều môi trường với cấu hình bên ngoài khác nhau. Thay vì đóng gói mọi giá trị vào `src/main/resources/application.properties`, người vận hành có thể đặt các file `application.properties` hoặc `application.yml` dưới những thư mục bên ngoài JAR.

Khi ứng dụng có nhiều bộ cấu hình được mount độc lập, ví dụ `config/database/`, `config/redis/` và `config/messaging/`, việc phải liệt kê từng đường dẫn làm cấu hình khởi động khó duy trì. **Wildcard location** giải quyết bài toán này: một mẫu đường dẫn duy nhất cho phép Spring Boot xét các thư mục con trực tiếp của một thư mục cha.

Ví dụ:

~~~text
/workspace/
├── app.jar
└── config/
    ├── database/
    │   └── application.properties
    ├── messaging/
    │   └── application.yml
    └── redis/
        └── application.properties
~~~

Nếu chạy ứng dụng với thư mục làm việc là `/workspace`, vị trí mặc định `file:./config/*/` có thể tìm các file `application.*` trong cả ba thư mục con. Đây là tính năng của **Spring Boot Config Data** trong các phiên bản Spring Boot hiện đại, không phải glob của shell và cũng không phải chức năng tự động có sẵn của Spring Framework thuần.

Hai câu hỏi cần tách biệt:

1. **Spring Boot tìm những file nào?** Điều này phụ thuộc tên cấu hình, location, wildcard, profile và thư mục làm việc.
2. **Nếu nhiều file chứa cùng một khóa thì giá trị nào thắng?** Điều này phụ thuộc mức ưu tiên của location, nhóm location, profile và các nguồn cấu hình khác.

Hiểu hai bước này giúp tránh nhầm rằng thứ tự liệt kê thư mục trong hệ điều hành hoặc thứ tự tạo file sẽ quyết định cấu hình hiệu lực.

## 2. Các vị trí tìm kiếm mặc định

Khi không thay đổi `spring.config.name`, `spring.config.location` hoặc `spring.config.additional-location`, Spring Boot tìm những tệp có tên cơ sở `application` theo các vị trí Config Data mặc định. Có thể biểu diễn thứ tự các nhóm vị trí theo mức độ ưu tiên tăng dần như sau:

| Nhóm | Vị trí tìm kiếm | Ý nghĩa |
| --- | --- | --- |
| Classpath | `optional:classpath:/` | Gốc classpath, thường chứa `application.properties` đóng gói trong JAR |
| Classpath | `optional:classpath:/config/` | Thư mục `config` trong classpath |
| Bên ngoài JAR | `optional:file:./` | Thư mục làm việc hiện tại |
| Bên ngoài JAR | `optional:file:./config/` | Thư mục `config` của thư mục làm việc hiện tại |
| Bên ngoài JAR | `optional:file:./config/*/` | Các thư mục con trực tiếp nằm trong `./config/` |

Trong tài liệu chính thức, các location mặc định được tổ chức theo **nhóm** (các location cùng nhóm được ngăn bằng `;`). Có thể tóm tắt bằng hai nhóm:

~~~text
optional:classpath:/;optional:classpath:/config/
optional:file:./;optional:file:./config/;optional:file:./config/*/
~~~

Nhóm bên ngoài JAR có mức ưu tiên cao hơn nhóm classpath khi cùng có một property. Ngoài thứ tự location, Spring Boot còn xét các phiên bản file dành riêng cho profile, ví dụ `application-prod.properties`.

**Quy tắc thực hành:** file `application.properties` đóng gói trong JAR thường cung cấp giá trị mặc định; file bên ngoài JAR có thể ghi đè các giá trị đó. Nếu cùng một khóa được khai báo nhiều lần trong những location có độ ưu tiên khác nhau, nguồn có độ ưu tiên cao hơn xác định giá trị được sử dụng.

Không nên hiểu bảng trên là thứ tự duy nhất của **mọi** nguồn cấu hình. Command-line arguments, Java system properties, biến môi trường, `@PropertySource` và các nguồn khác có thứ tự ưu tiên riêng. Ví dụ `--server.port=9090` thường có thể ghi đè `server.port` đọc từ một file bên ngoài.

### 2.1. Dấu `./` phụ thuộc thư mục làm việc, không phụ thuộc thư mục đặt JAR

Giả sử file JAR nằm tại `/opt/app/app.jar`:

~~~bash
cd /opt/app
java -jar app.jar
~~~

Lúc này `file:./config/` tương ứng với `/opt/app/config/`. Nhưng nếu chạy:

~~~bash
cd /tmp
java -jar /opt/app/app.jar
~~~

thì `file:./config/` lại trỏ tới `/tmp/config/`. Hai lệnh cùng chạy một JAR nhưng có thể đọc bộ cấu hình bên ngoài khác nhau.

Trong container, thư mục làm việc có thể do `WORKDIR` trong Dockerfile hoặc `workingDir` của Pod quy định. Khi không chắc cấu hình đang được tìm ở đâu, kiểm tra working directory của tiến trình trước khi kiểm tra nội dung file.

## 3. Wildcard location là gì?

Wildcard location là một địa chỉ Config Data có ký tự `*` ở **đoạn cuối phù hợp của đường dẫn**. Spring Boot mở rộng mẫu này khi nạp cấu hình để xét các thư mục con trực tiếp của thư mục cha.

Ví dụ:

~~~text
file:./config/*/
~~~

Nghĩa là: tìm các thư mục con trực tiếp của `./config/`, rồi tìm các file cấu hình phù hợp trong từng thư mục con đó.

Với cấu trúc:

~~~text
config/
├── database/
│   └── application.properties
├── cache/
│   └── application.properties
├── nested/
│   └── deep/
│       └── application.properties
└── application.properties
~~~

`file:./config/*/` xét:

- `config/cache/` và file `config/cache/application.properties`;
- `config/database/` và file `config/database/application.properties`;
- `config/nested/` nếu có file cấu hình phù hợp trực tiếp trong thư mục đó.

Mẫu này **không tự duyệt đệ quy** tới `config/nested/deep/application.properties`. File `config/application.properties` của thư mục cha được xử lý bởi location `file:./config/`, không phải do dấu wildcard trong `file:./config/*/`.

### 3.1. Cú pháp hợp lệ

Trong quy tắc wildcard của Spring Boot Config Data, chỉ được dùng **một dấu `*`** trong location wildcard; vị trí đó phải có dạng phù hợp ở cuối đường dẫn:

| Cấu hình | Diễn giải |
| --- | --- |
| `file:./config/*/` | Mẫu thư mục: tìm tên file cấu hình trong mỗi thư mục con trực tiếp |
| `file:./config/*/application.properties` | Mẫu file: tìm file có tên chỉ định trong mỗi thư mục con trực tiếp |
| `file:/etc/myapp/*/` | Mẫu thư mục dưới một đường dẫn tuyệt đối |
| `file:/etc/myapp/*/application.yml` | Mẫu file YAML ở một cấp thư mục con |
| `classpath:/config/*/` | Không được hỗ trợ: wildcard chỉ dành cho vị trí bên ngoài |
| `file:./config/**/` | Không phải cú pháp wildcard đệ quy được hỗ trợ ở đây |
| `file:./*/services/*/` | Không hợp lệ vì có nhiều dấu `*` và cấu trúc wildcard không phù hợp |

Với wildcard cho thư mục, mẫu phải kết thúc bằng `*/`. Với wildcard cho file, mẫu có dạng `*/<filename>`. Đặc biệt, `file:` cho biết đây là vị trí trên hệ thống tệp; không được thay bằng `classpath:` để quét thư mục con bên trong JAR.

### 3.2. Không nhầm với glob của shell

Trong lệnh sau, dấu `*` thuộc giá trị của một property do Spring Boot phân tích:

~~~bash
java -jar app.jar "--spring.config.additional-location=optional:file:./config/*/"
~~~

Đây không phải yêu cầu shell liệt kê file trước khi Java chạy. Giữ toàn bộ đối số trong dấu ngoặc kép là cách dễ đọc và giúp tránh những diễn giải không mong muốn của shell khi giá trị có ký tự đặc biệt.

Khác với lệnh `find`, `ls` hay glob `**` của một số công cụ, Spring Boot áp dụng đúng quy tắc wildcard Config Data của nó; đừng suy luận rằng mọi mẫu glob của shell đều được hỗ trợ.

## 4. Wildcard được mở rộng và sắp thứ tự như thế nào?

### 4.1. Chỉ xét thư mục con trực tiếp

Với `file:./config/*/`, Spring Boot liệt kê các thư mục con trực tiếp của `./config/` và mở rộng mỗi thư mục thành một location cụ thể.

Ví dụ:

~~~text
/workspace/config/
├── 10-base/
│   └── application.properties
├── 20-database/
│   └── application.properties
└── 30-overrides/
    └── application.properties
~~~

Mẫu wildcard được mở rộng thành các location tương ứng với `10-base`, `20-database` và `30-overrides`. Với mẫu thư mục, Boot sẽ dùng tên file cơ sở do `spring.config.name` quy định, mặc định là `application`, và xem xét các định dạng cũng như biến thể profile phù hợp.

### 4.2. Thứ tự alphabet theo đường dẫn tuyệt đối

**Spring Boot sắp các location wildcard đã mở rộng theo thứ tự alphabet dựa trên đường dẫn tuyệt đối của tên file.**

Với ba thư mục trên cùng một thư mục cha, thứ tự có thể hình dung:

~~~text
/workspace/config/10-base/application.properties
/workspace/config/20-database/application.properties
/workspace/config/30-overrides/application.properties
~~~

Nếu cùng một property được khai báo ở cả ba file trong cùng tình huống nạp và cùng mức profile, giá trị ở nguồn được xét sau có thể ghi đè nguồn xét trước theo quy tắc **last wins**.

Ví dụ:

~~~properties
# config/10-base/application.properties
app.retry-count=1
app.region=ap-southeast-1
~~~

~~~properties
# config/20-database/application.properties
app.retry-count=2
database.pool-size=20
~~~

~~~properties
# config/30-overrides/application.properties
app.retry-count=5
~~~

Nếu không có nguồn ưu tiên cao hơn ghi đè:

| Khóa | Giá trị hiệu lực | Lý do |
| --- | --- | --- |
| `app.retry-count` | `5` | Khai báo cuối trong các location wildcard tương ứng |
| `app.region` | `ap-southeast-1` | Chỉ khai báo ở `10-base` |
| `database.pool-size` | `20` | Chỉ khai báo ở `20-database` |

Lưu ý: cách diễn giải last-wins ở đây áp dụng cho tình huống đơn giản cùng một nhóm location, không có khác biệt profile hay import. Với cấu hình profile-specific phức tạp, cần xét cả **location group** trước khi kết luận nguồn thắng.

**Thứ tự alphabet không dựa trên:** thời gian tạo thư mục, thời gian sửa file, thứ tự mount volume, thứ tự hiển thị trong Explorer, hay thứ tự hệ điều hành trả về khi liệt kê thư mục.

### 4.3. Không đặt độ ưu tiên vận hành dựa hoàn toàn vào tên thư mục

Một số đội ngũ cố tình dùng tên `00-defaults`, `50-services`, `99-overrides` để tạo thứ tự dễ đoán khi dùng wildcard. Cách này có thể hoạt động trong nhóm cấu hình đơn giản, nhưng việc đổi tên hoặc thêm thư mục mới có thể làm thay đổi giá trị hiệu lực.

Khi cần kiểm soát chính xác thứ tự của các nhóm cấu hình có khóa trùng nhau, hãy liệt kê location cụ thể theo thứ tự mong muốn thay vì chỉ dựa vào thứ tự alphabet của wildcard.

Ví dụ:

~~~bash
java -jar app.jar \
  "--spring.config.additional-location=optional:file:/etc/myapp/base/,optional:file:/etc/myapp/overrides/"
~~~

Trong cùng cách tổ chức location phù hợp, vị trí `overrides/` được đặt sau có khả năng ghi đè `base/`. Nếu dùng profile-specific properties, cần xét thêm tác động của dấu `,` và `;`.

## 5. Khác nhau giữa `spring.config.location` và `spring.config.additional-location`

### 5.1. `spring.config.location` thay thế các vị trí mặc định

Khi khai báo:

~~~bash
java -jar app.jar \
  "--spring.config.location=optional:file:/etc/myapp/*/"
~~~

Spring Boot dùng những location được cấu hình để **thay thế** tập location tìm kiếm mặc định. Do đó, các file `application.properties` đóng gói sẵn trong JAR hoặc ở `./config/` không còn được tìm theo danh sách mặc định nếu không được đưa vào location mới bằng cách thích hợp.

Đây là công cụ phù hợp khi người vận hành muốn kiểm soát hoàn toàn những nơi ứng dụng lấy cấu hình. Nhưng nếu chỉ muốn thêm cấu hình bổ sung, thay thế toàn bộ đường dẫn mặc định có thể làm mất các giá trị mặc định mà ứng dụng dựa vào.

### 5.2. `spring.config.additional-location` bổ sung các vị trí

Khi khai báo:

~~~bash
java -jar app.jar \
  "--spring.config.additional-location=optional:file:/etc/myapp/*/"
~~~

Spring Boot vẫn xét các vị trí mặc định, rồi bổ sung location đã cấu hình. Những giá trị được nạp từ location bổ sung có thể ghi đè giá trị mặc định trong JAR.

Đây là lựa chọn thường gặp khi phân phối một JAR có cấu hình mặc định và muốn người triển khai mount thêm các thư mục cấu hình ngoài.

### 5.3. Thuộc tính chọn location phải có từ rất sớm

`spring.config.location`, `spring.config.additional-location` và `spring.config.name` được dùng ngay khi Spring Boot xác định file cần nạp. Vì vậy, nên đặt chúng ở nguồn đã có lúc khởi động:

- command-line arguments, ví dụ `--spring.config.additional-location=...`;
- biến môi trường, ví dụ `SPRING_CONFIG_ADDITIONAL_LOCATION`;
- Java system properties, ví dụ `-Dspring.config.additional-location=...`.

Không nên kỳ vọng đặt `spring.config.location` trong một file được tìm thấy quá muộn sẽ làm Boot quay lại tìm các vị trí khác theo cách không được bảo đảm. Cần phân biệt **chọn nơi tìm file** và **đọc nội dung file**.

Ví dụ với biến môi trường trong Linux:

~~~bash
export SPRING_CONFIG_ADDITIONAL_LOCATION="optional:file:/etc/myapp/*/"
java -jar app.jar
~~~

Ví dụ với JVM system property:

~~~bash
java -Dspring.config.additional-location=optional:file:/etc/myapp/*/ -jar app.jar
~~~

Khi lệnh được thực thi qua shell có xử lý ký tự đặc biệt, đặt giá trị trong dấu ngoặc kép để tránh lỗi parsing đối số.

### 5.4. Thư mục có dấu `/` kết thúc; file có tên đầy đủ

Nếu khai báo một **thư mục** trong `spring.config.location` hoặc `spring.config.additional-location`, location phải kết thúc bằng `/`. Spring Boot dùng `spring.config.name` để tạo tên file cần tìm trong thư mục đó.

~~~properties
# Thư mục: Boot tìm application.properties, application.yml...
spring.config.additional-location=optional:file:./config/custom/
~~~

Nếu khai báo **file** cụ thể, dùng đầy đủ tên file:

~~~properties
# File chỉ định trực tiếp
spring.config.additional-location=optional:file:./config/custom/custom.properties
~~~

Với wildcard, tương ứng là `file:./config/*/` hoặc `file:./config/*/custom.properties`. Location chỉ ra file cụ thể không có nghĩa Boot sẽ tự đọc mọi file có tên khác trong thư mục.

## 6. `optional:` và tình huống thiếu thư mục

Khi một location được khai báo tường minh nhưng không tồn tại, Spring Boot có thể báo `ConfigDataLocationNotFoundException` và dừng khởi động.

Để cho phép bỏ qua location không tồn tại, thêm `optional:`:

~~~bash
java -jar app.jar \
  "--spring.config.additional-location=optional:file:/etc/myapp/*/"
~~~

Điều này đặc biệt phù hợp với cấu hình mount tùy môi trường: thư mục ngoài có thể tồn tại ở production nhưng không tồn tại trên máy developer.

`optional:` **không có nghĩa** Boot bỏ qua mọi lỗi trong file đã tìm thấy. Một file tồn tại nhưng sai cú pháp, có giá trị không chuyển đổi được hoặc gây lỗi cấu hình vẫn có thể khiến ứng dụng thất bại khi khởi động.

Một cơ chế khác là `spring.config.on-not-found=ignore` để bỏ qua các lỗi thiếu location theo phạm vi rộng hơn. Khi có thể, nên dùng `optional:` trên từng location cụ thể nhằm thể hiện rõ chỗ nào được phép vắng mặt.

## 7. Location group và thứ tự ghi đè giữa các profile

Từ góc nhìn Config Data, **location group** là tập các location được xem xét tại cùng một mức. Hai ký tự phân cách quan trọng:

- Dấu phẩy `,`: tách các location hoặc nhóm location để xét theo thứ tự; location phía sau có thể ghi đè location phía trước.
- Dấu chấm phẩy `;`: ghép nhiều location ở **cùng một nhóm**, nhờ đó việc áp dụng các file theo profile diễn ra ở cùng cấp ưu tiên.

Đây không chỉ là chuyện trình bày chuỗi: khi ứng dụng có nhiều active profile, việc dùng `,` hoặc `;` có thể làm thay đổi property nào thắng.

### 7.1. Ví dụ không dùng cùng một nhóm

Giả sử có các file:

~~~text
cfg/
└── application-live.properties
ext/
└── application-prod.properties
~~~

~~~properties
# cfg/application-live.properties
app.mode=cfg-live
~~~

~~~properties
# ext/application-prod.properties
app.mode=ext-prod
~~~

Hai profile hoạt động: `prod,live`.

Khởi chạy:

~~~bash
java -jar app.jar \
  "--spring.profiles.active=prod,live" \
  "--spring.config.location=optional:file:./cfg/,optional:file:./ext/"
~~~

Với hai location tách bằng dấu phẩy, toàn bộ các file phù hợp thuộc `cfg/` được xử lý trước các file thuộc `ext/`. Trong ví dụ này, `ext/application-prod.properties` được xét sau và có thể ghi đè `app.mode` thành `ext-prod`, dù `live` đứng sau `prod` trong danh sách profile.

### 7.2. Ví dụ ghép vào cùng location group

Nếu muốn hai thư mục ở cùng cấp ưu tiên:

~~~bash
java -jar app.jar \
  "--spring.profiles.active=prod,live" \
  "--spring.config.location=optional:file:./cfg/;optional:file:./ext/"
~~~

Dấu `;` khiến `cfg/` và `ext/` thuộc cùng một nhóm. Khi xét các file theo profile ở cấp nhóm, profile `live` được xét sau `prod`. Trong ví dụ, `cfg/application-live.properties` có thể là nguồn thắng và `app.mode` nhận `cfg-live`.

Quy tắc profile-specific chung: file `application-{profile}.properties` được xét cùng các vị trí tìm kiếm như file cơ sở; khi kích hoạt nhiều profile, giá trị thuộc profile xuất hiện sau có thể ghi đè profile xuất hiện trước **ở cấp location group**. Đây là lý do cần nhìn cả cấu trúc nhóm lẫn đường dẫn file khi giải thích giá trị hiệu lực.

### 7.3. Wildcard tương tác với location group ra sao?

Wildcard như `file:./config/*/` tự mở rộng thành các location con được sắp alphabet. Nếu hệ thống còn có các location bổ sung khác hoặc nhiều profile, thứ tự và ưu tiên cuối cùng phụ thuộc vị trí của wildcard trong chuỗi location và cách định nghĩa location group.

Ví dụ:

~~~bash
java -jar app.jar \
  "--spring.profiles.active=prod" \
  "--spring.config.additional-location=optional:file:./config/*/,optional:file:/etc/myapp/overrides/"
~~~

Mẫu wildcard đọc các thư mục con của `./config/`, sau đó location `/etc/myapp/overrides/` được xét ở vị trí bổ sung phía sau theo cấu hình. Nếu muốn group các nguồn vào cùng cấp, cần chủ động dùng `;` và kiểm tra quy tắc profile của nhóm.

**Không có quy tắc tuyệt đối “folder tên cuối alphabet luôn thắng mọi trường hợp”.** Đó chỉ là kết quả có thể dự đoán trong một lớp location wildcard đơn giản, khi không có nguồn, import hoặc profile ở mức ưu tiên khác chen vào.

## 8. Ví dụ triển khai thực tế với các thư mục mount ngoài JAR

### 8.1. Một JAR, nhiều thư mục cấu hình

Giả sử triển khai service trong `/srv/orders`:

~~~text
/srv/orders/
├── orders.jar
└── config/
    ├── inventory/
    │   └── application.properties
    ├── messaging/
    │   └── application.properties
    └── payment/
        └── application-prod.properties
~~~

Các file:

~~~properties
# config/inventory/application.properties
orders.inventory.timeout=3s
orders.inventory.max-retries=2
~~~

~~~properties
# config/messaging/application.properties
orders.messaging.topic=orders.events
orders.messaging.enabled=true
~~~

~~~properties
# config/payment/application-prod.properties
orders.payment.endpoint=https://payments.example.test
~~~

Chạy:

~~~bash
cd /srv/orders
java -jar orders.jar --spring.profiles.active=prod
~~~

Vì vị trí mặc định có `file:./config/*/`, Spring Boot có thể xét các thư mục `inventory`, `messaging` và `payment`. Với profile `prod` đang hoạt động, file `application-prod.properties` bên trong `payment/` cũng được xét.

Điều kiện quan trọng:

1. Tiến trình chạy ở đúng working directory.
2. Thư mục con xuất hiện trực tiếp dưới `config/`.
3. File có đúng tên, đuôi và định dạng được Config Data hỗ trợ.
4. Không có nguồn khác ưu tiên cao hơn ghi đè cùng property.

Ví dụ này cho thấy wildcard phù hợp khi các bộ cấu hình có **các khóa riêng biệt**; nếu các bộ cùng khai báo một khóa, cần quy tắc ưu tiên rõ ràng.

### 8.2. Đường dẫn tuyệt đối cho môi trường container

Trong container hoặc Kubernetes, các ConfigMap có thể được mount vào các thư mục con khác nhau:

~~~text
/etc/myapp/
├── db/
│   └── application.properties
└── cache/
    └── application.properties
~~~

Có thể khai báo:

~~~bash
java -jar /app/app.jar \
  "--spring.config.additional-location=optional:file:/etc/myapp/*/"
~~~

Khi đó vị trí cấu hình không phụ thuộc thư mục làm việc của tiến trình. Cách khai báo explicit này phù hợp với môi trường có quy ước mount ổn định.

Nếu ứng dụng cần bảo đảm một thư mục quan trọng luôn tồn tại, không dùng `optional:` cho thư mục đó; thiếu cấu hình bắt buộc nên được phát hiện sớm thay vì rơi về mặc định không mong muốn.

## 9. Phân biệt wildcard file location với wildcard `configtree:`

Spring Boot có khái niệm **configuration tree** để đọc giá trị từ các file riêng lẻ mà tên file thường trở thành khóa cấu hình. Nó thường dùng với volume mount trong container.

Giả sử cấu trúc:

~~~text
/etc/secrets/
├── database/
│   ├── db.username
│   └── db.password
└── messagebroker/
    ├── mq.username
    └── mq.password
~~~

Đây **không phải** các file `application.properties`. Nếu dùng:

~~~properties
spring.config.import=optional:configtree:/etc/secrets/*/
~~~

Spring Boot có thể coi các thư mục con trực tiếp là những configuration tree và tạo ra các property tương ứng với tên file, chẳng hạn `db.username` và `mq.password`.

Ngược lại:

~~~text
file:/etc/secrets/*/
~~~

là một **file location pattern** cho cơ chế tìm các file cấu hình mang tên `application.*` (hoặc tên được cấu hình). Nó không biến mỗi file bí mật tùy ý thành property.

Đối với wildcard `configtree:`, các thư mục được sắp theo alphabet khi nạp. Nếu cần ưu tiên khác, hãy liệt kê rõ từng location nhập. Với bí mật thật, cần kiểm soát quyền trên file và tránh hiển thị giá trị trong log hoặc endpoint chẩn đoán.

## 10. Khi nhiều file cùng chứa một khóa: cách xác định giá trị thắng

Một cách suy luận thực tế gồm bốn bước.

### Bước 1. Xác định chính xác tập location đang dùng

Ứng dụng có dùng mặc định không? Có khai báo `spring.config.location` để thay thế mặc định không? Có thêm `spring.config.additional-location` không?

Ví dụ:

~~~text
--spring.config.additional-location=optional:file:/etc/myapp/*/
~~~

nghĩa là vị trí mới được bổ sung vào những nơi tìm cấu hình mặc định. Ngược lại:

~~~text
--spring.config.location=optional:file:/etc/myapp/*/
~~~

nghĩa là danh sách vị trí được thay thế bằng lựa chọn cấu hình rõ ràng đó.

### Bước 2. Mở rộng wildcard và sắp thứ tự

Liệt kê **các thư mục con trực tiếp**, rồi sắp theo đường dẫn tuyệt đối. Kiểm tra các file có mặt trong từng location sau khi mở rộng.

Ví dụ:

~~~text
/etc/myapp/20-db/application.properties
/etc/myapp/40-mq/application.properties
/etc/myapp/90-overrides/application.properties
~~~

Những file không tồn tại hoặc không khớp tên cấu hình không tham gia đóng góp property.

### Bước 3. Áp dụng profile và location group

Xác định `spring.profiles.active`, các file `application-{profile}.*` và vị trí dấu `,`/`;`. Một file profile-specific ở nhóm phù hợp có thể ghi đè giá trị của file không dành cho profile; giữa các profile, cần xét thứ tự profile và quy tắc nhóm.

### Bước 4. So sánh với những nguồn ưu tiên cao hơn Config Data

Đừng dừng ở file. Cùng một property có thể được khai báo qua:

~~~bash
java -jar app.jar \
  "--spring.config.additional-location=optional:file:/etc/myapp/*/" \
  "--orders.inventory.timeout=8s"
~~~

Trong cách khởi động thông dụng, đối số `--orders.inventory.timeout=8s` có thể ghi đè giá trị `orders.inventory.timeout` từ file Config Data. Lúc này tìm kiếm trong các thư mục wildcard vẫn hoạt động, nhưng giá trị hiệu lực không nhất thiết đến từ bất kỳ file nào.

## 11. Chẩn đoán khi Spring Boot không tìm thấy hoặc dùng sai file

### 11.1. Kiểm tra tên file và thư mục

Những lỗi rất thường gặp:

- Viết `config/**/` với kỳ vọng tìm đệ quy nhiều cấp.
- Đặt file bên dưới `config/zone/east/application.properties` và kỳ vọng `config/*/` tìm tới `east/`.
- Đặt file trong thư mục JAR nhưng tiến trình chạy với working directory khác.
- Dùng `classpath:/config/*/` dù wildcard chỉ hỗ trợ external directories.
- Viết `file:./config/*` mà thiếu `/` cuối cho wildcard directory location.
- Gõ nhầm `application-prod.properties` hoặc dùng sai active profile.
- Sử dụng `spring.config.location` khiến các location mặc định bị thay thế ngoài ý muốn.
- Tưởng `optional:` sẽ bỏ qua cả lỗi nội dung file.

### 11.2. Bật log liên quan Config Data khi cần

Để xem quá trình xử lý cấu hình trong quá trình khởi động, có thể thử bật log chi tiết cho các lớp liên quan:

~~~bash
java -jar app.jar \
  --logging.level.org.springframework.boot.context.config=TRACE
~~~

Mức độ chi tiết và tên các thông báo có thể khác nhau theo phiên bản Spring Boot. Chỉ bật log chi tiết trong phạm vi chẩn đoán phù hợp; một số hệ thống có thể cần kiểm soát để không làm lộ đường dẫn nội bộ hay dữ liệu nhạy cảm.

Nếu có Spring Boot Actuator được cấu hình và bảo vệ, endpoint `/actuator/env` có thể giúp quan sát những property source góp phần tạo giá trị hiệu lực. Cần giữ các biện pháp xác thực, phân quyền và che giấu giá trị nhạy cảm.

### 11.3. Kiểm tra tại ứng dụng bằng `Environment`

Một điểm kiểm tra đơn giản cho property không nhạy cảm:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigurationProbe {
    private final Environment environment;

    public ConfigurationProbe(Environment environment) {
        this.environment = environment;
    }

    public String inventoryTimeout() {
        return environment.getProperty(
            "orders.inventory.timeout", "not-configured");
    }
}
~~~

API này cho biết giá trị được Spring phân giải, nhưng tự nó chưa chỉ rõ file cụ thể nào thắng. Khi cần tìm nguồn, phải đối chiếu property sources với location, profile và các giá trị ở từng file. Không in mật khẩu hoặc token ra log chỉ để điều tra việc ghi đè.

## 12. Các tình huống dễ nhầm

| Nhận định | Giải thích đúng |
| --- | --- |
| “Wildcard tìm tất cả file ở mọi độ sâu.” | `config/*/` chỉ mở rộng các thư mục con trực tiếp, không duyệt đệ quy |
| “Wildcard dùng được trong `classpath:`.” | Wildcard location của Config Data chỉ hỗ trợ các vị trí bên ngoài |
| “Thư mục vừa được mount sẽ được xét sau.” | Wildcard được sắp alphabet theo đường dẫn tuyệt đối, không theo thời điểm mount |
| “`spring.config.location` chỉ thêm một thư mục mới.” | Thuộc tính này thay thế tập location mặc định; `additional-location` mới dùng để bổ sung |
| “Hai location phân cách bằng `,` hay `;` đều như nhau.” | `;` đặt các location cùng nhóm; sự khác biệt có thể đổi kết quả profile-specific |
| “Mọi file trong thư mục wildcard đều thành property.” | File location tìm các file cấu hình phù hợp tên/định dạng; `configtree:` là cơ chế khác |
| “`optional:` sẽ bỏ qua file sai cú pháp.” | `optional:` chủ yếu cho phép thiếu location; file hỏng vẫn có thể gây lỗi |
| “Cùng một khóa trong file cuối alphabet chắc chắn thắng.” | Còn phải xét location group, profile, import và các nguồn có độ ưu tiên cao hơn |

## 13. Bài tập suy luận giá trị hiệu lực

Giả sử chỉ có các nguồn sau, không có biến môi trường, command-line property ghi đè hoặc import:

~~~text
/workspace/
├── app.jar
└── config/
    ├── 10-core/
    │   └── application.properties
    ├── 20-service/
    │   └── application.properties
    └── 30-local/
        └── application.properties
~~~

~~~properties
# 10-core/application.properties
app.color=blue
app.timeout=2s
app.region=asia
~~~

~~~properties
# 20-service/application.properties
app.color=green
app.timeout=5s
~~~

~~~properties
# 30-local/application.properties
app.timeout=10s
~~~

Chạy ứng dụng tại `/workspace` với danh sách location mặc định và không bật profile riêng. Spring Boot tìm cả ba file qua `file:./config/*/` và sắp chúng theo đường dẫn tuyệt đối.

Kết quả kỳ vọng của tình huống này:

~~~properties
app.color=green
app.timeout=10s
app.region=asia
~~~

Lý do: `app.color` cuối cùng được khai báo trong `20-service`; `app.timeout` được ghi đè ở `30-local`; còn `app.region` chỉ có ở `10-core`.

Nếu thêm:

~~~bash
java -jar app.jar --app.timeout=30s
~~~

thì giá trị hiệu lực của `app.timeout` thông thường trở thành `30s` vì đối số dòng lệnh có độ ưu tiên cao hơn dữ liệu file. Điều này không làm wildcard ngừng hoạt động; nó chỉ thay đổi nguồn quyết định giá trị cuối.

## 14. Khuyến nghị tổ chức cấu hình

1. **Đặt cấu hình mặc định trong JAR** để bản build có thể khởi động ở môi trường cơ sở khi phù hợp.
2. **Dùng một thư mục `config/` rõ ràng** cho external configuration, nhất quán với working directory hoặc dùng đường dẫn tuyệt đối trong môi trường container.
3. **Dùng `config/*/` khi các nhóm cấu hình độc lập** và được tạo từ các mount khác nhau, chẳng hạn database, cache và messaging.
4. **Hạn chế khai báo trùng khóa giữa các thư mục wildcard.** Việc một property bị ghi đè do tên thư mục dễ tạo ra phụ thuộc khó thấy.
5. **Liệt kê location rõ ràng khi thứ tự quan trọng.** Cân nhắc `,` và `;` khi nhiều profile được dùng đồng thời.
6. **Dùng `spring.config.additional-location`** khi muốn giữ file mặc định trong JAR và bổ sung cấu hình bên ngoài.
7. **Chỉ đánh dấu `optional:` cho location được phép vắng mặt.** Cấu hình thiết yếu nên thất bại sớm khi thiếu.
8. **Phân biệt `file:` với `configtree:`.** Một bên tải file cấu hình có tên phù hợp, bên kia có thể đọc giá trị từ file mount riêng lẻ.
9. **Quan sát giá trị hiệu lực tại runtime** khi điều tra lỗi, và tránh hiển thị secret.

## 15. Tóm tắt quy tắc cần nhớ

- Spring Boot tìm cấu hình theo các nhóm location mặc định, từ classpath tới thư mục làm việc và các thư mục cấu hình bên ngoài.
- `file:./config/*/` đã nằm trong danh sách tìm kiếm mặc định: mẫu này xét **một cấp thư mục con** của `./config/`.
- Wildcard location chỉ cho phép **một** `*` trong dạng `*/` hoặc `*/<filename>` phù hợp, và **không hỗ trợ `classpath:`**.
- Các wildcard location được mở rộng và **sắp alphabet theo đường dẫn tuyệt đối**.
- Thứ tự ưu tiên còn chịu ảnh hưởng của **location group**, profile, imports và nguồn cấu hình ngoài Config Data.
- `spring.config.location` **thay thế** các vị trí mặc định, còn `spring.config.additional-location` **bổ sung** vị trí; `optional:` cho phép thiếu location.
- Đối với nhiều active profile, dấu `,` và `;` có thể cho kết quả ghi đè khác nhau.
- Với cấu hình quan trọng hoặc nhiều khóa trùng, hãy đặt thứ tự location tường minh và xác minh property source đang thắng.

### Tham khảo

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html), các mục **External Application Properties**, **Optional Locations**, **Wildcard Locations**, **Profile Specific Files** và **Configuration Trees**.
