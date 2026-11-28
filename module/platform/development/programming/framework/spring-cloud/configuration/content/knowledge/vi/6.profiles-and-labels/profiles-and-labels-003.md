# Quy tắc kết hợp cấu hình mặc định và cấu hình theo profile

Một ứng dụng Spring Boot thường cần hai nhóm thiết lập: giá trị nền có thể dùng trong nhiều môi trường và giá trị thay đổi theo môi trường chạy. Spring Cloud Config hỗ trợ cách tổ chức này bằng các tài liệu cấu hình dùng chung, tài liệu riêng cho từng ứng dụng và các file theo profile. Khi client yêu cầu cấu hình, Config Server tìm những nguồn phù hợp rồi trả về một `Environment` chứa danh sách `PropertySource`.

Hiểu cách các nguồn được kết hợp giúp đội ngũ tránh sao chép toàn bộ cấu hình cho từng môi trường, xác định nơi nên đặt một thuộc tính và giải thích vì sao một giá trị đang thắng giá trị khác.

## 1. Cấu hình mặc định và cấu hình theo profile

**Cấu hình mặc định** chứa những giá trị ứng dụng có thể sử dụng khi không có điều chỉnh theo profile. Ví dụ: thời gian chờ cơ sở, số lần retry mặc định, tên vùng hoặc các cờ chức năng an toàn.

**Cấu hình theo profile** điều chỉnh một phần các giá trị đó cho một môi trường hoặc mục đích chạy cụ thể, chẳng hạn `dev`, `test`, `staging` hay `prod`.

Với Spring Cloud Config, bốn mẫu file YAML thường được sử dụng:

| Mẫu tên | Phạm vi | Ví dụ |
|---|---|---|
| `application.yml` | Mặc định dùng chung cho các ứng dụng | `application.yml` |
| `application-{profile}.yml` | Dùng chung theo profile | `application-prod.yml` |
| `{application}.yml` | Mặc định riêng của một ứng dụng | `orders-service.yml` |
| `{application}-{profile}.yml` | Riêng ứng dụng theo profile | `orders-service-prod.yml` |

Với ứng dụng `orders-service` chạy profile `prod`, Config Server có thể lấy cả bốn file tương ứng từ repository Git. Những file không chứa khóa nào đó không làm mất giá trị của khóa ấy ở nguồn khác. Khi nhiều nguồn có cùng một khóa, nguồn có độ ưu tiên cao hơn quyết định giá trị được sử dụng.

## 2. Application, profile và label xác định tập nguồn

Config Server cần ba thông tin để tìm cấu hình:

- **Application** là tên ứng dụng, mặc định lấy từ `spring.application.name` của client. Có thể chỉ định tên yêu cầu riêng bằng `spring.cloud.config.name`.
- **Profile** là profile hoặc danh sách profile client yêu cầu, thường được thiết lập bằng `spring.profiles.active`.
- **Label** chọn phiên bản trong backend. Với Git, label thường là branch, tag hoặc commit.

Ví dụ, client có thể khai báo tên và Config Data import như sau:

```yaml
spring:
  application:
    name: orders-service
  config:
    import: "configserver:http://localhost:8888"
  cloud:
    config:
      label: main
```

Khi triển khai, profile `prod` có thể được kích hoạt từ môi trường:

```bash
SPRING_PROFILES_ACTIVE=prod
```

Yêu cầu khi đó tương ứng với application `orders-service`, profile `prod` và label `main`. Label không phải là profile: profile chọn tập cấu hình theo môi trường, còn label chọn phiên bản của kho cấu hình.

Nếu không kích hoạt profile tường minh, Spring Boot sử dụng profile mặc định `default`. Khi chẩn đoán, hãy xem profile thực tế mà client gửi tới Config Server thay vì suy ra từ tên máy chủ hoặc môi trường triển khai.

## 3. Cách các file mặc định và file profile bổ sung cho nhau

Giả sử repository có cấu trúc phẳng:

```text
config-repo/
├── application.yml
├── application-prod.yml
├── orders-service.yml
└── orders-service-prod.yml
```

`application.yml` chứa các giá trị cơ sở dùng chung:

```yaml
app:
  region: ap-southeast-1
  connect-timeout: 2s
  read-timeout: 5s
  retry:
    max-attempts: 3
    backoff: 200ms
  payment:
    mode: sandbox
```

`application-prod.yml` điều chỉnh những giá trị dùng chung khi chạy production:

```yaml
app:
  connect-timeout: 1s
  read-timeout: 3s

logging:
  level:
    root: INFO
```

`orders-service.yml` khai báo các thiết lập riêng cho ứng dụng orders:

```yaml
server:
  port: 8081

app:
  retry:
    max-attempts: 4
  payment:
    mode: sandbox
```

Cuối cùng, `orders-service-prod.yml` điều chỉnh cấu hình đặc thù của orders trong production:

```yaml
app:
  retry:
    max-attempts: 2
  payment:
    mode: live
```

Mô hình ưu tiên dự kiến là từ tổng quát đến cụ thể:

1. `application.yml`: mặc định chung.
2. `application-prod.yml`: điều chỉnh chung cho profile `prod`.
3. `orders-service.yml`: điều chỉnh riêng cho `orders-service`.
4. `orders-service-prod.yml`: điều chỉnh cụ thể nhất cho ứng dụng và profile đó.

Trong ví dụ này, các giá trị kết quả mong đợi ở phía client là:

| Thuộc tính | Giá trị | Nguồn quyết định |
|---|---|---|
| `app.region` | `ap-southeast-1` | `application.yml` |
| `app.connect-timeout` | `1s` | `application-prod.yml` |
| `app.read-timeout` | `3s` | `application-prod.yml` |
| `app.retry.max-attempts` | `2` | `orders-service-prod.yml` |
| `app.retry.backoff` | `200ms` | `application.yml` |
| `app.payment.mode` | `live` | `orders-service-prod.yml` |
| `server.port` | `8081` | `orders-service.yml` |
| `logging.level.root` | `INFO` | `application-prod.yml` |

Điểm quan trọng là cấu hình được kết hợp theo khóa. Một file profile chỉ cần khai báo những giá trị khác với mặc định; các khóa không xuất hiện trong file đó vẫn có thể lấy từ nguồn có độ ưu tiên thấp hơn.

Thứ tự trên mô tả cách tổ chức mong muốn cho bốn loại file. Khi repository có nhiều profile, nhiều search path hoặc composite repository, hãy xác nhận thứ tự `PropertySource` thực tế từ phản hồi Config Server. Danh sách nguồn trong `Environment` là bằng chứng trực tiếp về thứ tự server trả cấu hình; đừng chỉ dựa vào tên file để kết luận.

## 4. Phân biệt hợp nhất thuộc tính với ghi đè giá trị

Việc kết hợp các file không có nghĩa là Config Server nối nguyên văn các file YAML thành một file duy nhất. Server tạo các `PropertySource`; Spring phân giải giá trị dựa trên khóa và độ ưu tiên của nguồn.

Ví dụ, cấu hình mặc định có:

```yaml
app:
  retry:
    max-attempts: 3
    backoff: 200ms
```

File production chỉ khai báo:

```yaml
app:
  retry:
    max-attempts: 2
```

Khi được bind thành các thuộc tính, `max-attempts` nhận giá trị `2`, còn `backoff` vẫn có thể nhận `200ms` từ nguồn mặc định vì profile không cung cấp khóa này.

Với `@ConfigurationProperties`, cần lưu ý cách Binder xử lý cấu trúc dữ liệu. Các thuộc tính map có thể nhận các khóa từ nhiều nguồn; list thường được thay thế theo nguồn có độ ưu tiên cao hơn thay vì ghép từng phần tử. Ví dụ, nếu mặc định có ba URL trong một list và profile chỉ khai báo một URL, ứng dụng có thể nhận list một phần tử từ profile. Nếu muốn bổ sung phần tử, hãy thiết kế cấu hình theo map có khóa rõ ràng hoặc kiểm tra kết quả binding trong phiên bản Spring Boot đang sử dụng.

Không nên dùng cùng một khóa cho các ý nghĩa khác nhau ở các file. Khi ghi đè là chủ đích, hãy giữ nguyên ý nghĩa, kiểu dữ liệu và đơn vị của thuộc tính. Ví dụ, `app.read-timeout` nên luôn biểu diễn thời gian, không phải lúc là mili giây, lúc là số lần retry.

## 5. Nhiều profile đang hoạt động

Một ứng dụng có thể kích hoạt nhiều profile, ví dụ:

```bash
SPRING_PROFILES_ACTIVE=prod,region-apac
```

Trong trường hợp này, client gửi danh sách profile đến Config Server. Repository có thể tìm các file dùng chung và file riêng phù hợp với những profile được yêu cầu. Cách các nguồn được sắp xếp phụ thuộc vào thứ tự profile và cách Spring Cloud Config xử lý yêu cầu.

Có thể dùng profile để tách các chiều cấu hình khác nhau:

- `prod` mô tả môi trường triển khai.
- `region-apac` mô tả vùng triển khai.
- `blue` hoặc `green` có thể biểu diễn một nhóm triển khai nếu quy trình phát hành cần cấu hình riêng.

Tuy nhiên, mỗi profile nên có một mục đích dễ hiểu. Nếu tạo profile cho mọi tổ hợp môi trường, vùng, tenant và phiên bản ứng dụng, số lượng file sẽ tăng nhanh và khó xác định nguồn nào đang ghi đè khóa. Hãy ưu tiên cấu hình chung cho giá trị giống nhau và chỉ tạo profile bổ sung khi nó đại diện cho một chiều cấu hình thực sự cần tách.

Để biết profile nào thực sự được dùng, kiểm tra trường `profiles` trong phản hồi Environment. Đối với thuộc tính bị ghi đè khi có nhiều profile, xem thứ tự `propertySources` và kiểm tra giá trị cuối trong `Environment` của client.

## 6. Dùng profile an toàn trong Spring Boot

Profile thường được kích hoạt từ môi trường chạy, tham số dòng lệnh hoặc cấu hình bootstrap phù hợp. Ví dụ:

```bash
java -jar orders-service.jar --spring.profiles.active=prod
```

Hoặc đặt biến môi trường `SPRING_PROFILES_ACTIVE=prod` trong manifest triển khai. Việc kích hoạt profile phải diễn ra đủ sớm để client yêu cầu đúng cấu hình từ xa.

Spring Boot có quy tắc riêng cho thuộc tính điều khiển profile. Không đặt `spring.profiles.active` hoặc `spring.profiles.default` trong tài liệu cấu hình chỉ được kích hoạt bởi profile; các thuộc tính này cần được xác định ở nguồn không phụ thuộc profile. Điều này tránh vòng phụ thuộc khi Spring phải biết profile nào hoạt động trước khi chọn tài liệu profile.

Với YAML nhiều tài liệu, Spring Boot cũng hỗ trợ điều kiện `spring.config.activate.on-profile` để chỉ áp dụng một tài liệu khi profile phù hợp đang hoạt động. Đây là một cách tổ chức khác với việc tách thành file `application-prod.yml`. Chỉ nên dùng khi nhóm cấu hình nhỏ và việc chia tài liệu giúp dễ đọc; với kho cấu hình nhiều ứng dụng, các file riêng theo quy ước thường dễ review và truy vết hơn.

## 7. Cấu hình từ xa và cấu hình cục bộ của client

Config Server trả về các property source từ xa, nhưng `Environment` phía client còn có thể chứa:

- File `application.yml` và file theo profile được đóng gói trong ứng dụng.
- Biến môi trường và thuộc tính JVM.
- Tham số dòng lệnh.
- Các nguồn cấu hình khác do nền tảng hoặc ứng dụng cung cấp.

Do đó, có hai bước cần phân biệt khi điều tra giá trị:

1. **Phía server:** Config Server đã tìm đúng application, profile, label và trả các property source theo thứ tự nào?
2. **Phía client:** sau khi tích hợp cấu hình từ xa với nguồn cục bộ và áp dụng chính sách override, ứng dụng đang dùng giá trị nào?

Spring Cloud Config có các tùy chọn kiểm soát việc cấu hình từ xa có thể bị ghi đè bởi nguồn cục bộ, như `spring.cloud.config.allowOverride`, `spring.cloud.config.overrideNone` và `spring.cloud.config.overrideSystemProperties`. Các tùy chọn này phải được đặt ở nơi phù hợp với phiên bản Spring Cloud Config đang dùng; không giả định rằng thêm chúng vào file cục bộ luôn thay đổi được chính sách. Hãy xác định chính sách override rõ ràng và kiểm tra hành vi thực tế của client.

Nếu cấu hình tập trung là bắt buộc, tránh dùng `optional:configserver:` một cách tùy tiện. Tiền tố `optional:` cho phép client tiếp tục khởi động khi Config Server không truy cập được; điều này có thể khiến ứng dụng chạy với cấu hình cũ hoặc cấu hình cục bộ không đầy đủ. Với dịch vụ cần cấu hình từ xa để hoạt động an toàn, hãy để lỗi kết nối được phát hiện khi khởi động.

## 8. Kiểm tra thứ tự nguồn và giá trị thực tế

Với Config Server chạy ở cổng `8888`, có thể kiểm tra phản hồi Environment bằng:

```bash
curl http://localhost:8888/orders-service/prod/main
```

Kiểm tra các trường:

| Trường | Câu hỏi cần trả lời |
|---|---|
| `name` | Server đang trả cấu hình cho đúng application chưa? |
| `profiles` | Profile yêu cầu có đúng môi trường không? |
| `label` | Server đang đọc đúng branch, tag hoặc commit không? |
| `version` | Có thể truy vết cấu hình về đúng phiên bản nguồn không? |
| `propertySources` | Những file nào được tìm thấy, và thứ tự của chúng ra sao? |

Nếu `app.retry.max-attempts` có giá trị bất ngờ, hãy tìm khóa này trong từng `propertySources`, ghi lại tên file chứa nó và xem nguồn nào có độ ưu tiên cao nhất. Sau đó kiểm tra client để xác định có biến môi trường, JVM property hoặc tham số dòng lệnh đang ghi đè hay không.

Một số tình huống phổ biến:

| Hiện tượng | Điều cần kiểm tra |
|---|---|
| Không nhận giá trị production | Profile `prod` chưa được kích hoạt hoặc client gửi profile khác. |
| Giá trị chung thắng giá trị riêng | File riêng chưa được tìm thấy, tên application sai hoặc thứ tự nguồn không như dự kiến. |
| Một thuộc tính còn mặc định dù profile đã hoạt động | File profile không khai báo đúng khóa hoặc YAML dùng sai cấu trúc phân cấp. |
| Danh sách cấu hình bị mất phần tử | Binder thay thế list bằng list từ nguồn ưu tiên cao hơn. |
| Server trả đúng nhưng client dùng giá trị khác | Nguồn cục bộ hoặc chính sách override phía client đang tác động. |
| Cấu hình vừa thay đổi chưa có hiệu lực | Client chưa lấy lại cấu hình hoặc chưa nhận sự kiện refresh. |

## 9. Quản trị thay đổi theo profile

Thay đổi cấu hình production có thể ảnh hưởng đến nhiều ứng dụng cùng lúc nếu thuộc tính nằm trong `application-prod.yml`. Vì vậy, thay đổi file dùng chung cần được review theo phạm vi ảnh hưởng rộng hơn file riêng của một dịch vụ.

Nên áp dụng các nguyên tắc sau:

- Thay đổi giá trị mặc định chung phải kiểm tra các ứng dụng đang kế thừa giá trị đó.
- Thay đổi file profile chung phải đánh giá tất cả dịch vụ đang chạy profile tương ứng.
- Thay đổi file riêng chỉ cần tập trung vào ứng dụng liên quan, nhưng vẫn phải kiểm tra các thành phần phụ thuộc.
- Ghi nhận label và commit đã triển khai để có thể truy vết hoặc quay lại phiên bản cấu hình đã biết.
- Không lưu bí mật dạng rõ trong file mặc định hoặc file profile; lấy chúng từ secret manager hoặc cơ chế quản lý bí mật của nền tảng.
- Sau khi cập nhật Git, thực hiện quy trình refresh phù hợp. Commit mới không tự động cập nhật các bean đang chạy trong mọi client.

Nếu dùng Spring Cloud Bus, một sự kiện refresh có thể được phân phối đến nhiều instance. Các bean cần nhận giá trị mới phải hỗ trợ refresh theo cơ chế phù hợp, ví dụ `@RefreshScope`. Endpoint quản trị và kênh truyền sự kiện cần được bảo vệ bằng xác thực, phân quyền và giới hạn truy cập mạng.

## 10. Tổng kết

- Cấu hình mặc định cung cấp giá trị nền; cấu hình profile điều chỉnh những khóa cần thay đổi theo môi trường.
- Bốn mẫu file chính là `application.yml`, `application-{profile}.yml`, `{application}.yml` và `{application}-{profile}.yml`.
- Application xác định dịch vụ, profile xác định môi trường hoặc nhóm cấu hình, label xác định phiên bản của kho cấu hình.
- Các nguồn được kết hợp theo từng khóa; khóa không bị ghi đè có thể tiếp tục lấy giá trị từ nguồn mặc định.
- Không suy đoán thứ tự ưu tiên trong repository phức tạp; kiểm tra `propertySources` từ Config Server và `Environment` phía client.
- Nhiều profile, list binding và nguồn cục bộ có thể làm kết quả khác dự kiến; cần kiểm tra profile thực tế và giá trị sau binding.
- Review thay đổi theo phạm vi ảnh hưởng, bảo vệ bí mật và thực hiện refresh để cấu hình được phân phối nhất quán.
