# YAML nhiều tài liệu và `spring.config.activate.on-profile`

Một ứng dụng Spring Boot thường có cấu hình mặc định và một số giá trị cần thay đổi theo môi trường như `development`, `staging` hoặc `production`. Ta có thể tách mỗi môi trường thành một file riêng, hoặc đặt nhiều tài liệu YAML trong cùng một file rồi khai báo điều kiện để Spring Boot chỉ nạp tài liệu phù hợp với profile đang hoạt động.

Spring Boot hỗ trợ cách thứ hai thông qua cú pháp YAML nhiều tài liệu và thuộc tính `spring.config.activate.on-profile`. Cách tổ chức này giúp gom các cấu hình liên quan vào một file, giảm số file phải quản lý và thể hiện rõ điều kiện áp dụng của từng nhóm thuộc tính. Để dùng đúng, cần hiểu ranh giới tài liệu YAML, cách profile được kích hoạt và thứ tự ưu tiên khi nhiều nguồn cùng khai báo một thuộc tính.

## 1. YAML nhiều tài liệu là gì?

Một file YAML thông thường chứa một tài liệu. YAML cho phép nhiều tài liệu nối tiếp nhau trong cùng file; dấu phân cách `---` ở đầu dòng bắt đầu một tài liệu mới. Mỗi tài liệu có thể chứa một cây mapping và các giá trị YAML độc lập.

Ví dụ:

```yaml
app:
  name: order-service
  timeout: 2s
---
app:
  name: inventory-service
  timeout: 3s
```

Đoạn trên là hai tài liệu YAML. Khi được đọc như một file cấu hình Spring Boot, các tài liệu này trở thành những nguồn thuộc tính riêng để Spring Boot xử lý theo thứ tự và điều kiện kích hoạt. Dấu `---` phải đứng ở đầu dòng, không thụt vào như một thuộc tính con.

Trong file cấu hình Spring Boot, mỗi tài liệu thường biểu diễn một lớp cấu hình:

- Tài liệu đầu tiên chứa giá trị mặc định dùng chung.
- Tài liệu tiếp theo chứa các giá trị chỉ áp dụng khi một điều kiện được thỏa mãn.
- Có thể có nhiều tài liệu điều kiện khác nhau trong cùng file.

YAML cho phép dấu `...` kết thúc một tài liệu, nhưng cấu hình Spring Boot thường chỉ cần `---` để bắt đầu tài liệu tiếp theo. Không cần thêm `...` giữa các phần.

## 2. Kích hoạt tài liệu theo profile

Thuộc tính `spring.config.activate.on-profile` khai báo biểu thức profile mà tài liệu hiện tại yêu cầu. Nếu biểu thức khớp với các profile đang hoạt động, tài liệu được đưa vào quá trình nạp cấu hình; nếu không khớp, các thuộc tính trong tài liệu đó không được áp dụng.

Ví dụ file `application.yml`:

```yaml
server:
  port: 8080

logging:
  level:
    root: INFO
---
spring:
  config:
    activate:
      on-profile: staging

server:
  port: 8081

logging:
  level:
    root: DEBUG
---
spring:
  config:
    activate:
      on-profile: production

server:
  port: 8080

logging:
  level:
    root: WARN
```

Khi không kích hoạt profile `staging` hoặc `production`, tài liệu đầu tiên cung cấp cổng `8080` và mức log `INFO`. Khi profile `staging` hoạt động, tài liệu staging được nạp và ghi đè các thuộc tính trùng tên bằng cổng `8081` và mức log `DEBUG`. Khi profile `production` hoạt động, tài liệu production đặt mức log `WARN`.

Thuộc tính kích hoạt nằm trong chính tài liệu cần điều kiện. Tài liệu đầu tiên không có `spring.config.activate.on-profile`, nên nó là cấu hình mặc định. Các tài liệu sau tự mô tả profile mà chúng áp dụng.

`spring.config.activate.on-profile` được dùng với Spring Boot Config Data từ Spring Boot 2.4 trở lên. Dự án dùng phiên bản cũ cần kiểm tra hướng dẫn migration và cú pháp tương ứng của phiên bản đó; không nên sao chép cấu hình mới vào một ứng dụng cũ mà chưa xác minh khả năng hỗ trợ.

## 3. Chọn profile đang hoạt động

Điều kiện trong tài liệu chỉ được đánh giá dựa trên profile mà ứng dụng đang hoạt động. Có thể kích hoạt profile từ nhiều nguồn cấu hình của Spring Boot, ví dụ:

**Trong `application.yml` ở tài liệu không điều kiện:**

```yaml
spring:
  profiles:
    active: staging
```

**Bằng biến môi trường:**

```bash
SPRING_PROFILES_ACTIVE=staging
```

**Bằng tham số dòng lệnh:**

```bash
java -jar order-service.jar --spring.profiles.active=staging
```

Trong thực tế, môi trường triển khai thường quyết định profile bằng biến môi trường hoặc tham số khởi chạy. Cách này giúp cùng một artifact có thể chạy ở nhiều môi trường mà không phải sửa file cấu hình đóng gói bên trong ứng dụng.

Lưu ý: `spring.profiles.active`, `spring.profiles.default`, `spring.profiles.include` và `spring.profiles.group` chỉ được khai báo trong tài liệu không phụ thuộc profile. Không đặt các thuộc tính này trong một tài liệu đã được kích hoạt bằng `spring.config.activate.on-profile` hoặc trong file cấu hình riêng cho profile. Tài liệu điều kiện có nhiệm vụ cung cấp thuộc tính cho profile đã chọn, không tự thay đổi danh sách profile đang hoạt động.

## 4. Biểu thức profile

`spring.config.activate.on-profile` hỗ trợ biểu thức để tài liệu được kích hoạt theo một hoặc nhiều điều kiện. Các toán tử thường dùng:

| Cú pháp | Ý nghĩa | Ví dụ |
|---|---|---|
| Tên profile | Khớp khi profile có tên đó hoạt động | `staging` |
| `!` | Phủ định điều kiện | `!test` |
| `&` | Cả hai điều kiện đều đúng | `production & eu-west` |
| `|` | Một trong các điều kiện đúng | `staging | development` |
| `(...)` | Gom nhóm để biểu diễn thứ tự logic | `production & (eu-west | eu-central)` |

Ví dụ chỉ bật một nhóm cấu hình cho môi trường production ở một trong hai vùng:

```yaml
---
spring:
  config:
    activate:
      on-profile: "production & (eu-west | eu-central)"

app:
  payment:
    strict-validation: true
```

Nên đặt biểu thức phức tạp trong dấu nháy để dễ đọc và tránh hiểu nhầm cú pháp YAML. Khi dùng `&` và `|` cùng lúc, hãy dùng ngoặc để diễn đạt rõ nhóm điều kiện. Biểu thức chỉ quyết định tài liệu có được kích hoạt; nó không tạo ra profile và cũng không thay thế cấu hình profile ở môi trường triển khai.

## 5. Thứ tự áp dụng và ghi đè thuộc tính

Nhiều tài liệu YAML có thể khai báo cùng một thuộc tính. Khi các tài liệu đều được nạp, tài liệu xuất hiện sau có thể ghi đè giá trị từ tài liệu trước. Ví dụ:

```yaml
app:
  request-timeout: 2s
  retry-count: 2
---
spring:
  config:
    activate:
      on-profile: production

app:
  request-timeout: 5s
```

Với profile `production`, `app.request-timeout` là `5s`, còn `app.retry-count` vẫn là `2` vì tài liệu production không khai báo lại thuộc tính này. Việc ghi đè diễn ra theo từng thuộc tính, không có nghĩa toàn bộ mapping `app` từ tài liệu trước bị xóa.

Thứ tự trong một file nhiều tài liệu chỉ là một phần của quy tắc ưu tiên tổng thể. Spring Boot còn xử lý file cấu hình theo profile, cấu hình được import, biến môi trường, tham số dòng lệnh và các property source khác. Thứ tự chính xác phụ thuộc loại nguồn và vị trí nạp. Không nên kết luận một giá trị cuối cùng chỉ bằng cách nhìn một file YAML nếu ứng dụng còn nhận cấu hình từ nơi khác.

Một số nguyên tắc thực tế:

- Đặt giá trị mặc định dùng chung ở tài liệu đầu tiên.
- Chỉ ghi đè các thuộc tính thực sự khác biệt ở tài liệu có điều kiện.
- Dùng profile-specific file như `application-production.yml` khi muốn tách cấu hình thành file riêng; Spring Boot hỗ trợ cả cách tách file và cách dùng tài liệu nhiều phần.
- Kiểm tra nguồn thuộc tính thực tế khi có nhiều lớp cấu hình, đặc biệt khi kết hợp cấu hình cục bộ với Spring Cloud Config.

## 6. Kết hợp với Spring Cloud Config

Trong hệ thống nhiều ứng dụng, Spring Cloud Config Server có thể lấy cấu hình từ Git và cung cấp cho Config Client. Client gửi tên ứng dụng, profile và label để yêu cầu bộ cấu hình tương ứng. Những khái niệm này có liên hệ với tài liệu YAML nhiều phần nhưng có vai trò khác nhau:

| Thành phần/khái niệm | Vai trò |
|---|---|
| YAML document (`---`) | Chia một file thành nhiều tài liệu cấu hình |
| `spring.config.activate.on-profile` | Điều kiện profile để kích hoạt một tài liệu trong Config Data |
| Profile | Chọn biến thể cấu hình theo môi trường hoặc mục đích chạy |
| Application name | Chọn cấu hình riêng cho ứng dụng, ví dụ `order-service` |
| Label | Chọn phiên bản cấu hình trong backend, thường là branch, tag hoặc commit Git |
| Config Server | Đọc backend và cung cấp các property source cho client |

Ví dụ repository Git có thể tổ chức các file:

```text
config-repo/
├── application.yml
├── order-service.yml
├── order-service-staging.yml
└── order-service-production.yml
```

Với cách tổ chức này, Config Server có thể phân phối cấu hình dùng chung và cấu hình riêng theo ứng dụng/profile. Nếu chọn YAML nhiều tài liệu thay vì tách file, cần kiểm tra cách phiên bản Spring Cloud Config đang dùng đọc, lọc và trả các tài liệu đó cho client. Hành vi kích hoạt của Spring Boot Config Data ở file cục bộ và quá trình Config Server xây dựng Environment từ Git là hai bước khác nhau trong chuỗi nạp cấu hình; cần kiểm chứng bằng phiên bản thực tế của server và client.

Đặc biệt, không nhầm `spring.config.activate.on-profile` với profile trong yêu cầu Config Server. Profile của yêu cầu xác định bộ cấu hình mà Config Server tìm cho client; điều kiện `on-profile` mô tả tài liệu YAML được kích hoạt theo profile trong cơ chế xử lý Config Data. Hai cơ chế có liên quan nhưng không nên xem là cùng một thuộc tính hay cùng một tầng xử lý.

## 7. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Tài liệu theo môi trường không được nạp | Profile điều kiện chưa được kích hoạt hoặc viết sai tên | Kiểm tra `spring.profiles.active`, biến môi trường và biểu thức `on-profile` |
| Thuộc tính mặc định bị ghi đè ngoài dự kiến | Nhiều tài liệu hoặc property source cùng khai báo một key | Kiểm tra thứ tự tài liệu và nguồn cấu hình có độ ưu tiên cao hơn |
| Đặt `spring.profiles.active` trong tài liệu điều kiện | Cấu hình profile đang hoạt động bị khai báo ở tài liệu profile-specific | Chuyển khai báo active/include/group về tài liệu không điều kiện hoặc cấu hình khởi chạy |
| Dấu `---` không chia tài liệu như mong đợi | Dấu phân cách bị thụt lề hoặc file không được nạp bằng YAML Config Data | Đặt dấu phân cách ở đầu dòng và kiểm tra tên/nguồn file |
| Cấu hình chạy khác nhau giữa máy local và môi trường dùng Config Server | Client còn nhận cấu hình từ biến môi trường, tham số dòng lệnh hoặc server | Kiểm tra toàn bộ property source và xác minh hành vi theo đúng phiên bản Spring Boot/Spring Cloud |
| Dùng biểu thức profile khó đọc | Kết hợp nhiều toán tử mà không nhóm điều kiện | Dùng ngoặc và dấu nháy để làm rõ ý định |

Một cách chẩn đoán hiệu quả là xác định profile thực tế trước, sau đó kiểm tra tài liệu nào thỏa điều kiện, cuối cùng tìm nguồn có độ ưu tiên cao nhất đang cung cấp thuộc tính cần kiểm tra. Có thể dùng Actuator `env` hoặc `configprops` trong môi trường phát triển để quan sát nguồn cấu hình, nhưng các endpoint này có thể tiết lộ thông tin nhạy cảm và phải được bảo vệ khi triển khai.

## 8. Ví dụ hoàn chỉnh cho nhiều môi trường

Giả sử `order-service` cần dùng chung timeout mặc định, bật log chi tiết ở staging và giới hạn hành vi production. Có thể viết một file `application.yml` như sau:

```yaml
# Tài liệu mặc định
spring:
  application:
    name: order-service

app:
  checkout:
    timeout: 2s
    max-retries: 2

logging:
  level:
    root: INFO
---
# Chỉ áp dụng ở staging
spring:
  config:
    activate:
      on-profile: staging

app:
  checkout:
    timeout: 5s

logging:
  level:
    root: DEBUG
---
# Chỉ áp dụng ở production
spring:
  config:
    activate:
      on-profile: production

app:
  checkout:
    timeout: 2s
    max-retries: 1

logging:
  level:
    root: WARN
```

Kết quả mong đợi:

| Profile đang hoạt động | `app.checkout.timeout` | `app.checkout.max-retries` | `logging.level.root` |
|---|---:|---:|---|
| Không có `staging`/`production` | `2s` | `2` | `INFO` |
| `staging` | `5s` | `2` | `DEBUG` |
| `production` | `2s` | `1` | `WARN` |

Khi triển khai staging, nền tảng đặt `SPRING_PROFILES_ACTIVE=staging`; khi triển khai production, đặt `SPRING_PROFILES_ACTIVE=production`. Ứng dụng vẫn dùng cùng một file cấu hình và cùng artifact, trong khi các tài liệu có điều kiện cung cấp phần khác biệt của mỗi môi trường.

Trong ví dụ này, không đưa mật khẩu database, token hay private key vào tài liệu YAML. Các giá trị đó cần được lấy từ nguồn quản lý bí mật phù hợp. Cấu hình profile chỉ quyết định giá trị ứng dụng cần dùng theo môi trường; nó không phải cơ chế kiểm soát quyền đọc bí mật.

## 9. Mục tiêu cần đạt sau bài học

Sau bài này, người học cần có khả năng:

- Giải thích được một file YAML có thể chứa nhiều tài liệu và vai trò của dấu phân cách `---`.
- Viết được tài liệu mặc định và tài liệu có điều kiện bằng `spring.config.activate.on-profile`.
- Kích hoạt profile qua cấu hình, biến môi trường hoặc tham số dòng lệnh.
- Đọc và viết biểu thức profile có phủ định, AND, OR và ngoặc nhóm.
- Giải thích được cách tài liệu sau ghi đè thuộc tính trùng tên và vì sao cần xét toàn bộ property source.
- Phân biệt YAML document, profile, application name và label khi làm việc với Spring Cloud Config.
- Chẩn đoán được trường hợp tài liệu không được kích hoạt hoặc thuộc tính bị ghi đè ngoài dự kiến.

**Tự kiểm tra:** Với file ví dụ ở phần trước, nếu `SPRING_PROFILES_ACTIVE=staging`, hãy xác định giá trị cuối cùng của timeout, số lần retry và mức log. Sau đó chuyển sang `production` và giải thích vì sao `max-retries` thay đổi trong khi `timeout` quay về `2s`. Nếu một biến môi trường khác cũng đặt `APP_CHECKOUT_TIMEOUT`, hãy kiểm tra thứ tự ưu tiên của nguồn cấu hình đó trước khi kết luận giá trị ứng dụng nhận được.
