# Quy ước tên application.yml và tệp theo tên ứng dụng

Trong một hệ thống có nhiều ứng dụng Spring Boot, kho cấu hình của Spring Cloud Config cần một quy ước tên file rõ ràng. Quy ước này giúp phân biệt cấu hình dùng chung với cấu hình riêng của từng ứng dụng và từng môi trường. Nếu tên file không khớp với tên ứng dụng hoặc profile mà client yêu cầu, Config Server có thể trả về thiếu cấu hình, hoặc ứng dụng nhận một giá trị mặc định không phù hợp.

Spring Cloud Config Server nhận diện cấu hình thông qua ba thông tin: **application**, **profile** và **label**. Với backend Git hoặc Native, server tìm các tài liệu theo tên file và vị trí thư mục tương ứng. Bài học này trình bày cách đặt tên `application.yml`, file theo tên ứng dụng, file theo profile và cách tổ chức repository để nhiều dịch vụ có thể dùng chung cấu hình mà vẫn giữ được quyền kiểm soát riêng.

## 1. Ba thành phần định danh một yêu cầu cấu hình

Trước khi đặt tên file, cần hiểu ba thông tin mà Config Server dùng để tìm cấu hình:

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| Application | `orders-service` | Xác định ứng dụng cần nhận cấu hình. Client thường khai báo bằng `spring.application.name`. |
| Profile | `dev`, `test`, `prod` | Xác định nhóm cấu hình theo môi trường hoặc mục đích chạy. Một yêu cầu có thể bao gồm nhiều profile. |
| Label | `main`, `release-2026.11` | Chọn phiên bản cấu hình trong backend, thường là branch, tag hoặc commit khi dùng Git. |

Ví dụ, client có tên `orders-service`, đang chạy profile `prod` và yêu cầu label `main`. Config Server dùng bộ thông tin đó để tìm file chung và file riêng cho `orders-service` ở profile `prod` trong phiên bản Git `main`.

Application và profile quyết định nhóm file cần đọc. Label quyết định phiên bản của các file đó. Vì vậy, tên file đúng vẫn chưa đủ nếu client yêu cầu nhầm profile hoặc label.

## 2. Bốn quy ước tên file cơ bản

Spring Cloud Config hỗ trợ các tên file theo quy ước của Spring Boot. Với YAML, bốn dạng thường gặp là:

| Tên file | Phạm vi | Ví dụ |
|---|---|---|
| `application.yml` | Cấu hình mặc định dùng chung cho các ứng dụng | Timeout mặc định, múi giờ hoặc tên vùng mặc định. |
| `application-{profile}.yml` | Cấu hình dùng chung cho một profile | Thiết lập logging hoặc giới hạn kết nối dùng chung ở `prod`. |
| `{application}.yml` | Cấu hình mặc định riêng cho một ứng dụng | URL tích hợp và giới hạn xử lý của `orders-service`. |
| `{application}-{profile}.yml` | Cấu hình riêng của ứng dụng trong một profile | Database endpoint và chính sách retry riêng của `orders-service` ở `prod`. |

Trong đó `{application}` được thay bằng tên ứng dụng mà client gửi đến Config Server; `{profile}` được thay bằng tên profile đang được yêu cầu.

Ví dụ với `orders-service` và `prod`, các file có thể được tổ chức như sau:

```text
config-repo/
├── application.yml
├── application-prod.yml
├── orders-service.yml
└── orders-service-prod.yml
```

Ý nghĩa từng file:

- `application.yml`: giá trị nền mà nhiều ứng dụng có thể sử dụng.
- `application-prod.yml`: điều chỉnh giá trị dùng chung khi chạy production.
- `orders-service.yml`: bổ sung cấu hình mặc định cho riêng dịch vụ orders.
- `orders-service-prod.yml`: cấu hình cụ thể của orders khi chạy production.

Có thể dùng phần mở rộng `.properties` thay cho `.yml`, ví dụ `application.properties` hoặc `orders-service-prod.properties`. Nên chọn một định dạng chính cho repository để dễ đọc, review và kiểm tra thay đổi. Nếu cùng một khóa xuất hiện trong nhiều file, cần hiểu thứ tự property source mà Config Server trả về để xác định giá trị nào được ưu tiên.

## 3. application.yml: nơi đặt cấu hình dùng chung

`application.yml` là điểm bắt đầu phù hợp cho các giá trị có ý nghĩa với nhiều ứng dụng. Ví dụ:

```yaml
app:
  region: ap-southeast-1
  connect-timeout: 2s
  read-timeout: 5s
```

Các ứng dụng có thể sử dụng những giá trị này nếu không khai báo giá trị riêng. Khi một ứng dụng có yêu cầu khác, file theo tên ứng dụng có thể bổ sung hoặc ghi đè khóa tương ứng.

Chỉ nên đặt ở `application.yml` những thuộc tính thực sự có ý nghĩa chung. Không nên đưa mọi cấu hình của mọi dịch vụ vào file này chỉ để giảm số lượng file. Cấu hình riêng của database, cổng HTTP, tích hợp đối tác hoặc giới hạn xử lý thường cần được quản lý trong file ứng dụng tương ứng để tránh làm lộ mối quan hệ không cần thiết giữa các dịch vụ.

Giá trị dùng chung nên là giá trị an toàn, ít thay đổi và không chứa bí mật. Nếu một ứng dụng không thể hoạt động an toàn với giá trị mặc định, hãy để cấu hình bắt buộc được cung cấp trong file riêng hoặc từ hệ thống quản lý bí mật.

## 4. File theo tên ứng dụng

Tên file riêng phải khớp với `spring.application.name` của client. Ví dụ client `orders-service`:

```yaml
spring:
  application:
    name: orders-service
  config:
    import: "optional:configserver:http://localhost:8888"
```

Mặc định, client dùng `spring.application.name` làm application name khi yêu cầu cấu hình. Nếu khai báo `spring.cloud.config.name`, client có thể dùng thuộc tính đó để chỉ định tên application gửi đến Config Server; khi ấy tên file riêng phải khớp với giá trị được gửi. Trong ví dụ này, các file `orders-service.yml` và `orders-service-prod.yml` là những file riêng tương ứng.

Ví dụ nội dung `orders-service.yml`:

```yaml
server:
  port: 8081

app:
  order:
    max-items-per-request: 50
    reservation-timeout: 10s
  payment:
    base-url: https://sandbox-payments.example.com
```

Một dịch vụ khác, chẳng hạn `inventory-service`, có thể có file riêng:

```yaml
server:
  port: 8082

app:
  inventory:
    low-stock-threshold: 15
    sync-interval: 30s
```

Việc tách file theo tên ứng dụng giúp reviewer biết thay đổi ảnh hưởng đến dịch vụ nào. Nó cũng hạn chế tình trạng một thay đổi cấu hình của orders vô tình làm thay đổi hành vi của inventory.

Tên application nên ngắn gọn, ổn định và theo một quy ước thống nhất, ví dụ chữ thường kết hợp dấu gạch nối (`orders-service`, `inventory-service`, `billing-api`). Tránh thay tên tùy tiện giữa `orders`, `orders-service` và `order-service`, vì Config Server xem đây là các tên ứng dụng khác nhau. Cần giữ nguyên tên trong file cấu hình, `spring.application.name`, tài liệu triển khai và hệ thống giám sát.

## 5. File theo profile

Profile cho phép thay đổi cấu hình theo môi trường mà không phải nhân bản toàn bộ file. Một ứng dụng có thể dùng các profile như `dev`, `test`, `staging` và `prod`.

File dùng chung theo profile có dạng `application-{profile}.yml`:

```yaml
# application-prod.yml
app:
  connect-timeout: 1s
  read-timeout: 3s

logging:
  level:
    root: INFO
```

File riêng theo profile có dạng `{application}-{profile}.yml`:

```yaml
# orders-service-prod.yml
server:
  port: 8081

app:
  payment:
    base-url: https://payments.internal.example.com
  order:
    max-items-per-request: 100
```

Client có thể kích hoạt profile bằng biến môi trường hoặc tham số chạy, ví dụ:

```bash
SPRING_PROFILES_ACTIVE=prod
```

Khi client yêu cầu cấu hình với profile `prod`, Config Server tìm các file mặc định và file `prod` phù hợp. Không nên đặt tên file tùy ý như `orders-service-production.yml` nếu profile thực tế là `prod`; tên hậu tố phải khớp chính xác với profile được yêu cầu.

Nếu ứng dụng sử dụng nhiều profile cùng lúc, ví dụ `prod,region-apac`, Config Server có thể tìm cấu hình theo danh sách profile được gửi. Khi đó, thứ tự profile và quy tắc kết hợp nguồn có thể ảnh hưởng kết quả. Nên giữ số lượng profile nhỏ, mỗi profile có một trách nhiệm rõ ràng, chẳng hạn phân biệt môi trường (`prod`) và vùng triển khai (`region-apac`). Tránh tạo quá nhiều tổ hợp profile khiến việc dự đoán cấu hình trở nên khó khăn.

## 6. Thứ tự ưu tiên khi nhiều file cùng khai báo một khóa

Một khóa có thể xuất hiện trong cả bốn loại file. Ví dụ:

```yaml
# application.yml
app:
  timeout: 5s
```

```yaml
# application-prod.yml
app:
  timeout: 3s
```

```yaml
# orders-service.yml
app:
  timeout: 4s
```

```yaml
# orders-service-prod.yml
app:
  timeout: 1s
```

Với yêu cầu `orders-service` và profile `prod`, Config Server kết hợp các nguồn dùng chung và nguồn riêng theo thứ tự ưu tiên của nó. Quy tắc tổng quát là cấu hình riêng của ứng dụng có thể ghi đè cấu hình dùng chung, còn cấu hình theo profile có thể ghi đè cấu hình mặc định. Do đó, `orders-service-prod.yml` là nơi thích hợp để khai báo giá trị đặc thù nhất cho dịch vụ trong production.

Không nên suy đoán giá trị cuối chỉ từ tên file khi repository có nhiều nguồn, nhiều profile hoặc composite repository. Hãy gọi endpoint Environment JSON của Config Server và xem danh sách `propertySources`. Các nguồn được trả về theo thứ tự ưu tiên; khi một khóa xuất hiện nhiều lần, vị trí của nguồn cho biết giá trị nào được ưu tiên trong tập nguồn từ xa.

Ngoài ra, client còn có các nguồn cấu hình khác như file cục bộ, biến môi trường, thuộc tính JVM và tham số dòng lệnh. Giá trị cuối cùng trong ứng dụng phụ thuộc cả thứ tự ưu tiên của Spring Boot lẫn chính sách override cấu hình từ xa của Spring Cloud Config. Vì vậy, phản hồi Config Server cho biết server đã tìm được gì, còn kiểm tra `Environment` của client cho biết ứng dụng thực sự sử dụng gì.

## 7. Tổ chức repository theo thư mục

Với số lượng ứng dụng nhỏ, cấu trúc phẳng ở thư mục gốc dễ hiểu và dễ kiểm tra. Khi số lượng ứng dụng tăng, có thể chuyển sang cấu trúc thư mục để giảm sự lộn xộn.

Ví dụ:

```text
config-repo/
├── shared/
│   ├── application.yml
│   └── application-prod.yml
├── orders-service/
│   ├── orders-service.yml
│   └── orders-service-prod.yml
├── inventory-service/
│   ├── inventory-service.yml
│   └── inventory-service-prod.yml
└── billing-api/
    ├── billing-api.yml
    └── billing-api-prod.yml
```

Config Server có thể tìm file trong các thư mục được khai báo bằng `search-paths`. Ví dụ:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.com/platform/config-repo.git
          default-label: main
          search-paths:
            - shared
            - '{application}'
```

`shared` là thư mục chứa cấu hình dùng chung; `{application}` được thay bằng tên ứng dụng của yêu cầu. Với `orders-service`, server tìm trong thư mục `shared` và `orders-service`. Cần kiểm tra cách backend kết hợp các tài liệu ở nhiều search path và thứ tự property source trong phản hồi thực tế, nhất là khi cùng một khóa xuất hiện ở nhiều thư mục.

Khi tổ chức theo thư mục, nên thống nhất một kiểu đặt tên. Ví dụ trên dùng tên ứng dụng ngay cả trong thư mục riêng để người đọc có thể nhận diện file khi xem log, diff hoặc khi tài liệu được di chuyển. Một phương án khác là đặt `application.yml` trong từng thư mục ứng dụng, nhưng khi đó phải xác minh rõ search path và quy tắc tìm kiếm của Config Server để tránh nhầm file chung với file riêng.

Không nên dùng một thư mục cho mỗi môi trường rồi đặt mọi file ứng dụng vào đó nếu cấu trúc ấy khiến server khó phân biệt cấu hình dùng chung và cấu hình riêng. Tổ chức thư mục phải giúp người vận hành trả lời nhanh hai câu hỏi: file này thuộc ứng dụng nào, và file này áp dụng cho profile nào?

## 8. Kết nối client với Config Server

Một client Spring Boot dùng Config Data API có thể khai báo:

```yaml
spring:
  application:
    name: orders-service
  config:
    import: "optional:configserver:http://localhost:8888"
  cloud:
    config:
      label: main
```

Khi triển khai production, profile có thể được truyền từ môi trường:

```bash
SPRING_PROFILES_ACTIVE=prod
```

`optional:` cho phép ứng dụng khởi động khi Config Server không truy cập được và tiếp tục dùng các nguồn cấu hình còn lại. Chỉ dùng khi ứng dụng có thể hoạt động an toàn trong tình huống đó. Nếu cấu hình tập trung là bắt buộc, hãy bỏ `optional:` để ứng dụng báo lỗi khi không lấy được cấu hình cần thiết.

Tên application trong repository phải khớp với `spring.application.name`. Label `main` trong ví dụ chọn nhánh cấu hình tương ứng; với môi trường cần triển khai có thể tái lập, nên cân nhắc dùng tag hoặc commit cố định theo quy trình phát hành của tổ chức.

## 9. Kiểm tra quy ước tên file

Khi một client không nhận được cấu hình như dự kiến, hãy kiểm tra từ yêu cầu đến file:

1. Xác nhận `spring.application.name` có đúng tên file hoặc tiền tố file trong repository không.
2. Xác nhận profile đang hoạt động, ví dụ `prod`, có khớp hậu tố file hay không.
3. Xác nhận label đang yêu cầu có chứa phiên bản file mới nhất cần dùng không.
4. Kiểm tra `search-paths` để chắc chắn server tìm đến đúng thư mục.
5. Gọi endpoint `/{application}/{profile}/{label}` và xem `name`, `profiles`, `label`, `version` cùng `propertySources`.
6. Nếu Config Server trả đúng nguồn nhưng ứng dụng vẫn dùng giá trị khác, kiểm tra property source và thứ tự ưu tiên ở phía client.

Ví dụ kiểm tra trực tiếp:

```bash
curl http://localhost:8888/orders-service/prod/main
```

Các lỗi thường gặp:

| Hiện tượng | Nguyên nhân có thể |
|---|---|
| Chỉ nhận cấu hình chung | Tên `spring.application.name` không khớp tên file riêng hoặc file riêng nằm ngoài search path. |
| Không nhận cấu hình production | Profile chưa được kích hoạt hoặc tên file dùng hậu tố khác với profile thực tế. |
| Cấu hình vừa sửa chưa xuất hiện | Client yêu cầu label khác, server chưa cập nhật bản clone hoặc commit chưa nằm trong branch/tag đang dùng. |
| Hai dịch vụ nhận cùng cấu hình riêng | Cả hai client đang dùng cùng `spring.application.name`, hoặc file được đặt nhầm tên. |
| Giá trị từ file đúng vẫn không có hiệu lực | Một property source có độ ưu tiên cao hơn đang ghi đè ở server hoặc client. |

## 10. Nguyên tắc đặt tên và quản trị thay đổi

Một repository dễ vận hành cần tuân theo các nguyên tắc nhất quán:

- Dùng `application.yml` cho thiết lập dùng chung có chủ đích.
- Dùng `{application}.yml` cho cấu hình mặc định riêng của từng ứng dụng.
- Dùng hậu tố `-{profile}` để biểu diễn cấu hình theo profile.
- Dùng cùng một cách viết tên application giữa client, file, tài liệu triển khai và giám sát.
- Tránh lặp lại khóa ở nhiều file nếu không có lý do override rõ ràng.
- Không lưu mật khẩu, token hoặc private key dạng rõ trong repository; dùng secret manager hoặc cơ chế cung cấp bí mật an toàn.
- Review thay đổi cấu hình như thay đổi mã nguồn; ghi nhận label và commit được dùng cho triển khai quan trọng.
- Sau khi cập nhật cấu hình, thực hiện quy trình refresh phù hợp để các client đang chạy nhận giá trị mới.

Đặt tên file rõ ràng không chỉ giúp Config Server tìm đúng tài liệu mà còn giúp đội ngũ hiểu phạm vi ảnh hưởng của mỗi thay đổi. Khi một khóa chỉ phục vụ một dịch vụ, hãy đặt nó trong file của dịch vụ đó. Khi nhiều dịch vụ thực sự cần cùng một giá trị, hãy đặt ở cấu hình dùng chung và cho phép ứng dụng ghi đè có chủ đích.

## 11. Tổng kết

- `application.yml` chứa cấu hình mặc định dùng chung; `application-{profile}.yml` chứa cấu hình dùng chung theo profile.
- `{application}.yml` chứa cấu hình mặc định riêng của ứng dụng; `{application}-{profile}.yml` chứa cấu hình riêng của ứng dụng theo profile.
- `{application}` phải khớp với tên client gửi, thường được khai báo bằng `spring.application.name`.
- Profile quyết định file theo môi trường được tìm; label chọn phiên bản cấu hình trong backend.
- Có thể tổ chức repository theo thư mục bằng `search-paths`, nhưng cần kiểm tra thứ tự property source khi nhiều đường dẫn cùng khai báo một khóa.
- Dùng Environment API để xác minh server đã tìm đúng file và kiểm tra phía client để xác định giá trị cuối cùng.
- Duy trì quy ước tên, review, versioning, bảo mật bí mật và quy trình refresh để cấu hình được phân phối nhất quán.
