# Ứng xử khi vị trí không tồn tại: `optional:` và `spring.config.on-not-found` trong Spring Boot

## 1. Bối cảnh: không phải môi trường nào cũng có cùng một tệp cấu hình

Một ứng dụng Spring Boot có thể chạy từ cùng một JAR trên laptop, máy kiểm thử, máy chủ và container. Những môi trường đó thường có cấu hình khác nhau:

- JAR chứa `application.yml` với các giá trị chung.
- Máy chủ production có thể gắn thêm thư mục `/etc/order-service/` với cấu hình riêng.
- Laptop của lập trình viên có thể không có thư mục `/etc/order-service/`.
- Một số môi trường có `feature-flags.yml` hoặc `secrets` dưới dạng volume được mount; môi trường khác không dùng những tài nguyên này.

Câu hỏi là: **nếu Spring Boot được yêu cầu nạp một tệp hoặc thư mục cấu hình nhưng vị trí đó không tồn tại thì ứng dụng phải làm gì?**

Spring Boot áp dụng nguyên tắc **fail fast** với nhiều vị trí Config Data được khai báo tường minh: nếu một vị trí được yêu cầu mà không tìm thấy, ứng dụng có thể dừng ngay khi khởi động và thông báo lỗi. Hành vi này tránh tình trạng ứng dụng chạy với thiết lập thiếu hoặc sai.

Đối với vị trí thật sự có thể vắng mặt, Spring Boot cung cấp hai cơ chế:

1. Tiền tố `optional:` — bỏ qua lỗi không tìm thấy của **một vị trí Config Data cụ thể**.
2. Thuộc tính `spring.config.on-not-found=ignore` — chọn cách **bỏ qua lỗi không tìm thấy Config Data trên phạm vi rộng** trong quá trình nạp cấu hình.

Hai cơ chế có phạm vi khác nhau. Chúng không thay thế việc kiểm tra những thuộc tính mà nghiệp vụ thật sự bắt buộc.

## 2. Config Data và lỗi “không tìm thấy”

Config Data là cơ chế Spring Boot đọc các file cấu hình ứng dụng, thường là `application.properties`, `application.yml` hoặc `application.yaml`, từ classpath, hệ thống tệp hoặc các vị trí được khai báo thêm. Ngoài đường dẫn tìm kiếm mặc định, ứng dụng có thể dùng:

| Khai báo | Vai trò |
| --- | --- |
| `spring.config.location` | Chỉ định **danh sách vị trí thay thế** các vị trí tìm kiếm mặc định |
| `spring.config.additional-location` | **Bổ sung** vị trí vào danh sách mặc định |
| `spring.config.import` | **Nhập** tài nguyên cấu hình được chỉ định trong một tài liệu Config Data |

Ví dụ:

~~~bash
java -jar order-service.jar --spring.config.additional-location=file:/etc/order-service/
~~~

Nếu vị trí `file:/etc/order-service/` được khai báo rõ nhưng không tồn tại, Spring Boot có thể dừng bằng lỗi thuộc nhóm `ConfigDataLocationNotFoundException`. Thông báo thường nêu vị trí gây lỗi và gợi ý thêm tiền tố `optional:` nếu vị trí được phép thiếu.

Phân biệt một điểm dễ nhầm: Spring Boot có các **vị trí tìm kiếm mặc định**, ví dụ `classpath:/` và `file:./config/`. Việc máy tính không có một thư mục cấu hình mặc định như `./config/` là bình thường; không đồng nghĩa mọi ứng dụng đều phải tạo sẵn thư mục đó. Câu chuyện fail fast ở đây chủ yếu quan trọng khi ta **tự khai báo một vị trí Config Data phải được nạp**.

Nếu file tồn tại nhưng nội dung YAML sai cú pháp, định dạng không được hỗ trợ hoặc xảy ra một lỗi nạp khác, đó là vấn đề khác với “không tìm thấy”.

## 3. Tiền tố `optional:`: cho phép thiếu một vị trí cụ thể

Khi thêm `optional:` vào đầu một vị trí, bạn nói với Spring Boot:

> Hãy cố nạp tài nguyên cấu hình tại đây; nếu tài nguyên không tồn tại, có thể tiếp tục khởi động mà không coi riêng sự vắng mặt đó là lỗi.

Ví dụ:

~~~bash
java -jar order-service.jar --spring.config.additional-location=optional:file:/etc/order-service/
~~~

Nếu thư mục `/etc/order-service/` có cấu hình hợp lệ, ứng dụng nạp như bình thường. Nếu thư mục không có, Spring Boot bỏ qua vị trí này và vẫn dùng những nguồn cấu hình khác có sẵn.

Cú pháp quan trọng:

~~~text
optional:<vị-trí-config-data>
~~~

Ví dụ các dạng thông dụng:

~~~text
optional:file:./config/
optional:file:/etc/order-service/
optional:file:/etc/order-service/override.yml
optional:classpath:/custom-settings.yml
optional:configtree:/run/secrets/
~~~

Ở đây:

- `file:` chỉ tài nguyên trên filesystem.
- `classpath:` chỉ tài nguyên trên classpath.
- `configtree:` hỗ trợ đọc thư mục chứa các file mà tên file trở thành tên thuộc tính và nội dung file trở thành giá trị.
- `optional:` không phải là một thư mục và không phải một kiểu dữ liệu; nó là tiền tố xử lý **trường hợp tài nguyên vắng mặt**.

Một đường dẫn thư mục dùng với `spring.config.location` hoặc `spring.config.additional-location` thường cần dấu `/` ở cuối, để Spring Boot có thể ghép tên file cấu hình cần tìm. Ví dụ `optional:file:/etc/order-service/` diễn tả thư mục, còn `optional:file:/etc/order-service/custom.yml` diễn tả file cụ thể.

### 3.1. `optional:` trong `spring.config.additional-location`

Đây là lựa chọn thực tế khi muốn giữ mặc định đóng gói trong JAR và bổ sung cấu hình bên ngoài tùy môi trường.

Giả sử trong JAR có `application.yml`:

~~~yaml
server:
  port: 8080
app:
  maintenance-mode: false
~~~

Tại production có thể có file `/etc/order-service/application.yml`:

~~~yaml
server:
  port: 9090
app:
  maintenance-mode: true
~~~

Khởi động:

~~~bash
java -jar order-service.jar --spring.config.additional-location=optional:file:/etc/order-service/
~~~

Kết quả trong phạm vi không có nguồn cấu hình ưu tiên cao hơn:

| Tình huống | `server.port` | `app.maintenance-mode` | Ứng dụng |
| --- | --- | --- | --- |
| Có thư mục ngoài và file hợp lệ | `9090` | `true` | Khởi động với cấu hình bổ sung |
| Không có thư mục ngoài | `8080` | `false` | Khởi động với cấu hình từ JAR |
| File ngoài tồn tại nhưng YAML sai | Không thể giả định | Không thể giả định | Có thể khởi động thất bại do lỗi cú pháp |

Để giữ giá trị mặc định từ JAR, `additional-location` thường phù hợp hơn `location`.

### 3.2. `optional:` trong `spring.config.location`

Ví dụ:

~~~bash
java -jar order-service.jar --spring.config.location=optional:file:/etc/order-service/
~~~

Lệnh này khác với ví dụ trước: `spring.config.location` **thay thế** danh sách vị trí tìm kiếm mặc định. Nếu thư mục bên ngoài vắng mặt, ứng dụng có thể bỏ qua lỗi không tìm thấy, nhưng **không vì thế mà tự khôi phục việc tìm file `application.yml` trong JAR theo các vị trí mặc định đã bị thay thế**.

Một ứng dụng vẫn có thể không chạy được nếu thiếu những giá trị thiết yếu như URL datasource. Do đó:

- Chọn `spring.config.location` khi thực sự muốn kiểm soát lại toàn bộ danh sách vị trí.
- Chọn `spring.config.additional-location` khi muốn mặc định đóng gói vẫn được nạp và chỉ bổ sung cấu hình triển khai.

Nếu muốn dùng `location` mà vẫn có classpath, phải khai báo các vị trí classpath cần thiết trong danh sách, ví dụ:

~~~bash
java -jar order-service.jar --spring.config.location=classpath:/,optional:file:/etc/order-service/
~~~

Các vị trí được phân tách bằng dấu phẩy. Khi một danh sách có cả vị trí bắt buộc và vị trí tùy chọn, `optional:` chỉ áp dụng cho phần tử được gắn tiền tố, không tự biến tất cả các phần tử còn lại thành tùy chọn.

### 3.3. `optional:` trong `spring.config.import`

Một tài liệu cấu hình có thể nhập thêm tài nguyên ở nơi khác:

~~~yaml
# application.yml đóng gói trong JAR
spring:
  application:
    name: order-service
  config:
    import: "optional:file:./config/feature-flags.yml"

app:
  checkout:
    enabled: false
~~~

Nếu file `./config/feature-flags.yml` tồn tại:

~~~yaml
app:
  checkout:
    enabled: true
~~~

Spring Boot nạp tài liệu được import, và cấu hình import có thể ghi đè thuộc tính `app.checkout.enabled` từ tài liệu khai báo import. Nếu file không tồn tại, ứng dụng có thể tiếp tục với giá trị `false` trong file đóng gói.

`spring.config.import` phù hợp khi một file cần chỉ rõ **tài nguyên cụ thể** phải nhập, thay vì thêm cả một thư mục vào danh sách tìm `application.*`.

**Lưu ý:** đường dẫn `file:./config/feature-flags.yml` được hiểu tương đối với **working directory** của tiến trình. Thư mục chứa JAR không đương nhiên là working directory. Nếu cần đường dẫn không phụ thuộc nơi gọi lệnh, hãy dùng đường dẫn tuyệt đối hoặc chiến lược triển khai thống nhất.

## 4. `spring.config.on-not-found=ignore`: bỏ qua lỗi thiếu Config Data trên diện rộng

Trong một số tình huống, bạn muốn cấu hình chính sách rằng mọi vị trí Config Data không tìm thấy sẽ được bỏ qua. Spring Boot hỗ trợ:

~~~properties
spring.config.on-not-found=ignore
~~~

Ví dụ truyền qua đối số chương trình:

~~~bash
java -jar order-service.jar --spring.config.on-not-found=ignore
~~~

Hoặc qua Java system property:

~~~bash
java -Dspring.config.on-not-found=ignore -jar order-service.jar
~~~

Hoặc đặt biến môi trường:

~~~bash
export SPRING_CONFIG_ON_NOT_FOUND=ignore
java -jar order-service.jar
~~~

Đây là thiết lập **toàn cục cho chính sách xử lý các vị trí Config Data không tìm thấy**. Nếu một vị trí không có `optional:` nhưng không tồn tại, chính sách `ignore` có thể khiến quá trình nạp cấu hình tiếp tục thay vì dừng vì loại lỗi thiếu vị trí đó.

Khác biệt cốt lõi:

- `optional:` nói rằng **vị trí cụ thể này** có thể thiếu.
- `spring.config.on-not-found=ignore` nói rằng **lỗi không tìm thấy vị trí Config Data nói chung** có thể bị bỏ qua.

Ví dụ, khi có hai vị trí:

~~~bash
java -jar order-service.jar --spring.config.additional-location=file:/etc/order-service/,file:/mnt/team-config/
~~~

Nếu một trong hai vị trí được yêu cầu không tồn tại, ứng dụng có thể dừng. Khi bổ sung:

~~~bash
java -jar order-service.jar --spring.config.on-not-found=ignore --spring.config.additional-location=file:/etc/order-service/,file:/mnt/team-config/
~~~

Spring Boot được hướng dẫn bỏ qua các lỗi không tìm thấy thuộc phạm vi chính sách này. Nhưng nếu ứng dụng cần một khóa chỉ có ở một vị trí đã bị bỏ qua, lỗi bind, validation hoặc khởi tạo bean vẫn có thể xảy ra sau đó.

### 4.1. Cần cung cấp thiết lập `on-not-found` từ sớm

`spring.config.on-not-found` chi phối quá trình **tải Config Data**. Vì vậy, cách rõ ràng nhất là truyền nó vào một nguồn đã sẵn sàng từ giai đoạn khởi động: đối số chương trình, Java system property hoặc biến môi trường.

Không nên phụ thuộc vào việc đặt `spring.config.on-not-found` trong **chính file đang bị thiếu**, vì Spring Boot không thể đọc một file không tồn tại để lấy chỉ thị bỏ qua việc thiếu file đó.

### 4.2. Vì sao không nên bật `ignore` mọi nơi?

Một cấu hình production thường có tài nguyên bắt buộc: endpoint thanh toán, địa chỉ máy chủ dữ liệu, cấu hình chứng thư hoặc tham số bảo mật. Nếu vô tình đặt sai đường dẫn tới các file này mà toàn bộ lỗi “không tìm thấy” đều bị bỏ qua, ứng dụng có thể:

1. Chạy bằng giá trị mặc định không dành cho production.
2. Khởi động được nhưng chỉ phát hiện thiếu cấu hình khi người dùng gọi chức năng.
3. Phát sinh lỗi khác, làm nguyên nhân gốc là thiếu file khó nhận biết hơn.

Vì vậy, nên ưu tiên `optional:` cho các tệp thật sự tùy chọn và giữ hành vi **fail fast** với tệp bắt buộc. Dùng `spring.config.on-not-found=ignore` khi có lý do rõ ràng cho việc bỏ qua đồng loạt, đồng thời có cơ chế kiểm tra cấu hình cần thiết ở bước tiếp theo.

## 5. So sánh trực tiếp ba cách khai báo

Giả sử `/etc/order-service/` **không tồn tại**. Cấu hình chung trong JAR vẫn có mặt, và không có nguyên nhân lỗi khác.

| Cách chạy | Hành vi khi thiếu vị trí ngoài | Phạm vi |
| --- | --- | --- |
| `--spring.config.additional-location=file:/etc/order-service/` | Thường dừng ở bước tìm Config Data | Vị trí ngoài được yêu cầu |
| `--spring.config.additional-location=optional:file:/etc/order-service/` | Bỏ qua vị trí ngoài, tiếp tục với nguồn khác | Chỉ vị trí có `optional:` |
| `--spring.config.on-not-found=ignore --spring.config.additional-location=file:/etc/order-service/` | Có thể bỏ qua lỗi không tìm thấy này | Chính sách chung cho Config Data |

Với hai vị trí được khai báo:

~~~text
file:/etc/order-service/,optional:file:/etc/order-service/local-overrides/
~~~

Chỉ `local-overrides/` có `optional:`. Vị trí `/etc/order-service/` vẫn là vị trí được yêu cầu. Cần chú ý đúng ranh giới của từng phần tử, đặc biệt khi giá trị chứa nhiều vị trí cách nhau bằng dấu phẩy.

`optional:` không làm vị trí nạp sớm hay muộn hơn, không thay đổi thứ tự ưu tiên thuộc tính và không tự biến một giá trị thiếu thành giá trị mặc định. Nó chỉ ảnh hưởng đến việc **có dừng vì tài nguyên không tìm thấy hay không**.

## 6. Phân biệt “không tìm thấy” với các lỗi cấu hình khác

Một sai lầm nguy hiểm là cho rằng thêm `optional:` sẽ làm một cấu hình lỗi trở nên hợp lệ. Không phải vậy.

| Tình huống | `optional:` có phải cách xử lý phù hợp? | Hướng xử lý |
| --- | --- | --- |
| File tùy chọn hoàn toàn không tồn tại | Có | Bỏ qua và sử dụng nguồn cấu hình còn lại |
| Thư mục bổ sung trên laptop chưa được tạo | Có, nếu thật sự tùy chọn | Dùng `optional:file:.../` |
| File cấu hình production bắt buộc không tồn tại | Không nên | Giữ fail fast; sửa mount, đường dẫn hoặc quy trình cấp phát |
| File YAML tồn tại nhưng thụt lề sai, cú pháp sai | Không | Sửa nội dung YAML |
| File có khóa `app.timeout` nhưng giá trị không chuyển thành `Duration` được | Không | Sửa giá trị hoặc kiểu binding |
| File đã đọc nhưng thiếu khóa nghiệp vụ bắt buộc | Không giải quyết được | Cung cấp khóa cần thiết hoặc cấu hình validation |
| Tài nguyên tồn tại nhưng bị từ chối quyền đọc | Không nên kỳ vọng `optional:` sẽ xử lý | Kiểm tra quyền file và quyền của tiến trình |
| Đường dẫn tài nguyên bị khai báo sai định dạng | Không | Sửa cú pháp location/import |

Về mặt ý nghĩa, `optional:` dành cho **sự vắng mặt hợp lệ**, không dùng để che mọi dạng lỗi dữ liệu. Tương tự, `on-not-found=ignore` không có nghĩa “bỏ qua mọi lỗi khởi động của ứng dụng Spring Boot”.

## 7. Ví dụ thực tế: một JAR, ba môi trường

Giả sử dịch vụ gửi thông báo có cấu hình mặc định trong `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: notification-service

app:
  notification:
    enabled: false
    max-attempts: 2
  report:
    format: csv
~~~

Ở môi trường production có thể có file `/etc/notification-service/application.yml`:

~~~yaml
app:
  notification:
    enabled: true
    max-attempts: 5
~~~

Lệnh khởi động cho cả laptop và production:

~~~bash
java -jar notification-service.jar --spring.config.additional-location=optional:file:/etc/notification-service/
~~~

**Trên laptop:** thư mục `/etc/notification-service/` không tồn tại. Ứng dụng tiếp tục với `notification.enabled=false`, `max-attempts=2` và `report.format=csv`.

**Trên production:** thư mục và file cấu hình có mặt. Ứng dụng nhận `notification.enabled=true`, `max-attempts=5`, còn `report.format=csv` tiếp tục đến từ JAR.

**Trên production nhưng bị quên mount:** ứng dụng cũng có thể khởi động với giá trị mặc định từ JAR. Đây chính là rủi ro nếu file ngoài thực chất là **bắt buộc**. Khi đó không nên thêm `optional:` một cách máy móc; hãy dùng vị trí yêu cầu bắt buộc hoặc kiểm tra rõ cấu hình production trước khi phục vụ request.

Nếu yêu cầu là “production phải có tệp chính sách riêng”, có thể triển khai production bằng lệnh **không** có `optional:`:

~~~bash
java -jar notification-service.jar --spring.config.additional-location=file:/etc/notification-service/
~~~

Cách thiết kế phù hợp là quyết định tính **bắt buộc hay tùy chọn theo ý nghĩa vận hành**, trước khi chọn cú pháp.

## 8. Kết hợp với profile và thứ tự ưu tiên

Spring Boot có thể nạp cả `application.yml` và file theo profile như `application-prod.yml`. Cấu hình bên ngoài cũng có các biến thể tương tự. Ví dụ:

~~~text
classpath:/application.yml
classpath:/application-prod.yml
file:./config/application.yml
file:./config/application-prod.yml
~~~

Khi profile `prod` đang kích hoạt, các nguồn có thể cùng định nghĩa một khóa như `server.port`. Giá trị cuối được quyết định bởi **thứ tự ưu tiên giữa các nguồn**.

Việc thêm `optional:` cho thư mục ngoài chỉ cho phép **không có thư mục đó** mà không gây lỗi thiếu vị trí. Nó **không** làm file ngoài có ưu tiên thấp đi, cũng không làm file đóng gói có ưu tiên cao hơn khi file ngoài tồn tại.

Chẳng hạn:

~~~bash
java -jar service.jar --spring.profiles.active=prod --spring.config.additional-location=optional:file:/etc/service/
~~~

- Nếu `/etc/service/application-prod.yml` có mặt và hợp lệ, nó có thể ghi đè giá trị trong file cùng tên đóng gói.
- Nếu thư mục `/etc/service/` không tồn tại, những cấu hình còn lại vẫn được nạp theo quy tắc thông thường.
- Nếu một nguồn khác ưu tiên cao hơn, chẳng hạn đối số `--server.port=7070`, giá trị đó có thể thắng giá trị từ mọi file Config Data.

Vì vậy, trong khi phân tích kết quả, hãy trả lời hai câu hỏi theo thứ tự: **nguồn nào được nạp?** rồi **nguồn nào có quyền ưu tiên cao hơn cho khóa đang xét?**

## 9. Config tree và bí mật triển khai

Một cách phổ biến trong môi trường container là gắn file dưới dạng volume, chẳng hạn:

~~~text
/run/secrets/
  payment.username
  payment.password
~~~

Spring Boot có thể nhập những giá trị này dưới dạng configuration tree:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
~~~

Nếu thư mục được mount, tên file tương ứng tên thuộc tính và nội dung file được nạp thành giá trị. Nếu thư mục không tồn tại, tiền tố `optional:` cho phép tiếp tục.

Tuy nhiên, hãy suy nghĩ về vai trò của các file đó:

- Với **feature flag** có giá trị mặc định an toàn, việc thư mục vắng mặt có thể chấp nhận được.
- Với **thông tin xác thực database hoặc khóa ký** bắt buộc, cho phép bỏ qua tệp có thể khiến ứng dụng chạy thiếu bí mật quan trọng.

Nếu secret bắt buộc, hãy dùng đường dẫn không có `optional:` và xác thực các thuộc tính cần thiết. Không nên đưa mật khẩu thật vào ví dụ, vào file đã commit hay in toàn bộ giá trị cấu hình ra log để chẩn đoán.

## 10. Đặt cấu hình ở đâu để Spring Boot thấy kịp thời?

Một số thuộc tính quyết định **chính quá trình tìm và đọc Config Data**, gồm:

- `spring.config.name`
- `spring.config.location`
- `spring.config.additional-location`
- `spring.config.on-not-found`

Các thuộc tính này cần có trước hoặc trong giai đoạn Spring Boot thiết lập quá trình đọc Config Data. Nguồn cấp thường dùng là đối số command line, Java system properties hoặc biến môi trường.

Ví dụ:

~~~bash
java -Dspring.config.on-not-found=ignore -jar service.jar --spring.config.additional-location=file:/opt/service/optional/
~~~

Hoặc trong Docker Compose:

~~~yaml
services:
  service:
    image: example/service:latest
    environment:
      SPRING_CONFIG_ADDITIONAL_LOCATION: "optional:file:/etc/service/"
    volumes:
      - ./config:/etc/service:ro
~~~

Ví dụ Compose trên minh họa cách truyền vị trí tùy chọn. Trong thực tế, cơ chế volume mount, quyền đọc và sự tồn tại của thư mục nguồn phụ thuộc cấu hình triển khai.

Còn `spring.config.import` thường được khai báo trong một tài liệu Config Data đã được nạp:

~~~yaml
spring:
  config:
    import: "optional:file:/etc/service/feature-flags.yml"
~~~

Đừng đặt chính chỉ dẫn tìm tài liệu bị thiếu vào tài liệu đó, vì một file không tồn tại sẽ không thể cung cấp giá trị để cứu quá trình tìm kiếm.

## 11. Chẩn đoán lỗi khi ứng dụng không khởi động

Khi thấy thông báo liên quan đến Config Data, nên kiểm tra tuần tự:

1. **Xác định vị trí:** log nói thiếu `file:/...`, `classpath:/...` hay `configtree:/...`? Tên đường dẫn được truyền bằng tham số nào?
2. **Xác định mức độ bắt buộc:** tài nguyên này là mặc định tùy chọn, phần bổ sung cho developer hay yêu cầu bắt buộc của production?
3. **Kiểm tra working directory:** với `file:./...`, thư mục hiện hành của tiến trình có đúng như dự kiến không?
4. **Kiểm tra đường dẫn và mount:** container hoặc host có thực sự cung cấp file/thư mục? Tên có đúng chữ hoa, chữ thường và extension không?
5. **Kiểm tra hình thức vị trí:** đường dẫn thư mục dùng `/` cuối khi thích hợp; cú pháp `optional:` gắn với đúng phần tử trong danh sách.
6. **Kiểm tra nguồn khai báo:** `spring.config.location` đang thay thế vị trí mặc định hay `spring.config.additional-location` chỉ bổ sung?
7. **Nếu file có mặt nhưng vẫn lỗi:** đọc thông báo parser, quyền truy cập, chuyển kiểu và validation. Không coi đó là lỗi thiếu file.

Nếu muốn kiểm thử riêng hành vi `optional:`, hãy dùng tệp/đường dẫn hoàn toàn không tồn tại trong một môi trường thử nghiệm và xác nhận ứng dụng còn có đủ giá trị cần thiết để khởi động. Nếu muốn kiểm thử fail fast, dùng cùng đường dẫn nhưng bỏ `optional:`.

Không nên tự động chuyển mọi lỗi sang `spring.config.on-not-found=ignore` trước khi hiểu tài nguyên nào bị thiếu; điều đó có thể che đi thông tin hữu ích về lỗi triển khai.

## 12. Các lỗi nhầm lẫn thường gặp

| Nhận định sai | Giải thích đúng |
| --- | --- |
| “Thư mục `./config/` mặc định không có thì Spring Boot luôn lỗi.” | Các vị trí mặc định có thể vắng mặt; hành vi fail fast đặc biệt quan trọng với vị trí được chỉ định tường minh là phải nạp. |
| “`optional:` là lệnh bỏ qua lỗi YAML.” | Nó xử lý trường hợp vị trí/tài nguyên Config Data không tìm thấy, không đảm bảo bỏ qua lỗi cú pháp. |
| “`optional:` làm file có ưu tiên thấp hơn.” | Ưu tiên thuộc tính là cơ chế riêng; tiền tố chỉ ảnh hưởng đến thiếu tài nguyên. |
| “`spring.config.on-not-found=ignore` chỉ áp dụng cho một file.” | Đây là chính sách rộng đối với lỗi không tìm thấy Config Data. |
| “`spring.config.location` có `optional:` sẽ tự quay lại dùng mọi file mặc định trong JAR.” | `location` thay thế danh sách vị trí mặc định; `optional:` không khôi phục danh sách đã thay. |
| “Nếu thiếu file secret bắt buộc thì thêm `optional:` là cách sửa.” | Cần sửa quy trình cấp secret hoặc fail fast, không che thiếu hụt cấu hình. |
| “Ứng dụng khởi động được nghĩa là mọi giá trị cần thiết đều hợp lệ.” | Một số lỗi chỉ xuất hiện lúc binding, khởi tạo bean hoặc xử lý request nếu thiếu validation. |

## 13. Bài tập tự kiểm tra

### Bài 1 — Vị trí tùy chọn

Ứng dụng có cấu hình trong JAR:

~~~yaml
app:
  greeting: "Xin chào"
~~~

Lệnh chạy:

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:/opt/app/overrides/
~~~

Thư mục `/opt/app/overrides/` không tồn tại. Trong điều kiện không có lỗi hoặc override khác, kết quả là gì?

**Đáp án:** ứng dụng có thể tiếp tục khởi động, `app.greeting` giữ giá trị `Xin chào` từ JAR. Thiếu thư mục tùy chọn không phải lỗi.

### Bài 2 — Vị trí bắt buộc

Dùng lệnh:

~~~bash
java -jar app.jar --spring.config.additional-location=file:/opt/app/required/
~~~

Thư mục `/opt/app/required/` không tồn tại. Có nên thêm `optional:` nếu ứng dụng production bắt buộc có cấu hình này?

**Đáp án:** thông thường **không**. Hãy sửa bước cung cấp thư mục/file. Dừng ngay khi thiếu cấu hình bắt buộc giúp phát hiện sai sót triển khai.

### Bài 3 — Toàn cục hay từng vị trí?

Cho hai khai báo:

~~~text
A) --spring.config.additional-location=optional:file:/opt/app/overrides/
B) --spring.config.on-not-found=ignore
~~~

Cách nào chỉ cho phép thiếu một vị trí đã nêu; cách nào thay đổi chính sách chung?

**Đáp án:** A chỉ tác động vị trí `/opt/app/overrides/`. B áp dụng chính sách rộng hơn đối với lỗi không tìm thấy Config Data.

### Bài 4 — `location` khác `additional-location`

Một JAR có `classpath:/application.yml`. Chạy:

~~~bash
java -jar app.jar --spring.config.location=optional:file:/opt/app/missing/
~~~

Thư mục ngoài không tồn tại. Có thể kết luận file mặc định trong JAR chắc chắn vẫn được nạp không?

**Đáp án:** **không**. `spring.config.location` thay thế danh sách tìm mặc định, nên `optional:` không tự phục hồi vị trí classpath đã bị thay thế. Nếu muốn giữ cấu hình đóng gói, chọn `additional-location` hoặc khai báo tường minh vị trí classpath cần thiết.

### Bài 5 — File tồn tại nhưng sai

File `/etc/service/extra.yml` tồn tại nhưng chứa cú pháp YAML không hợp lệ. `application.yml` có:

~~~yaml
spring:
  config:
    import: "optional:file:/etc/service/extra.yml"
~~~

Có thể tin rằng Spring Boot sẽ bỏ qua lỗi nội dung file vì đã có `optional:` không?

**Đáp án:** **không**. `optional:` cho phép thiếu tài nguyên, còn file có mặt nhưng cú pháp sai là lỗi khác cần được sửa.

## 14. Ghi nhớ

- Khi một **vị trí Config Data được yêu cầu** không tồn tại, Spring Boot có thể dừng khởi động để báo lỗi sớm.
- Dùng `optional:` khi một **file hoặc thư mục cụ thể thật sự được phép vắng mặt**.
- Dùng `spring.config.on-not-found=ignore` khi có chủ đích **bỏ qua rộng rãi lỗi không tìm thấy Config Data** và có biện pháp kiểm soát cấu hình thiết yếu khác.
- `spring.config.additional-location` bổ sung vị trí, còn `spring.config.location` thay thế vị trí tìm kiếm mặc định.
- `optional:` không thay đổi thứ tự ưu tiên, không bỏ qua lỗi YAML và không cung cấp giá trị mặc định cho khóa bắt buộc.
- Với cấu hình bắt buộc của production, **fail fast và validation rõ ràng** thường an toàn hơn.
- Kiểm tra working directory, đường dẫn, mount, tên file và nguồn thuộc tính trước khi sửa hành vi xử lý lỗi.

**Tài liệu tham khảo:** [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).
