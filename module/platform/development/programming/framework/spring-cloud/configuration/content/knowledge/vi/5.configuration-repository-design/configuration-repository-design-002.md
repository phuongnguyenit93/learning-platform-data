# Tổ chức tệp theo ứng dụng, profile và thư mục

## 1. Mục tiêu của thiết kế kho cấu hình

Trong `SPRING_CLOUD_CONFIGURATION`, Git repository là nguồn lưu trữ có phiên bản cho cấu hình được Spring Cloud Config Server phân phối đến nhiều ứng dụng Spring Boot. Khi số lượng dịch vụ và môi trường tăng lên, cách đặt tên file và bố trí thư mục quyết định việc nhóm vận hành có tìm, review, kiểm thử và phát hành cấu hình chính xác hay không.

Một kho cấu hình tốt cần trả lời rõ ba câu hỏi:

- **Ứng dụng nào nhận cấu hình?** Được xác định bởi application name, thường là `spring.application.name`.
- **Cấu hình áp dụng trong profile nào?** Được xác định bởi profile mà Config Client yêu cầu, ví dụ `dev`, `staging` hoặc `prod`.
- **Ứng dụng đang dùng phiên bản cấu hình nào?** Được xác định bởi label, thường là branch, tag hoặc commit của Git backend.

Từ ba chiều đó, Config Server tìm các file phù hợp, tạo `Environment` gồm các property source rồi trả kết quả cho client. Cách tổ chức file cần giúp ánh xạ ba chiều này dễ hiểu, tránh trùng lặp và không làm lẫn cấu hình của các dịch vụ.

Ví dụ, `order-service` chạy profile `prod` và yêu cầu label `release-2026-11` có thể nhận cấu hình chung, cấu hình production chung và cấu hình riêng của order service tại đúng revision Git đó.

## 2. Quy tắc đặt tên file

Với Git backend, Spring Cloud Config hỗ trợ quy ước tên file theo application và profile. Các tên thường gặp gồm:

| Tên file | Phạm vi thường dùng |
|---|---|
| `application.yml` | Cấu hình mặc định dùng chung cho các client. |
| `application-prod.yml` | Cấu hình chung khi client yêu cầu profile `prod`. |
| `order-service.yml` | Cấu hình mặc định dành cho `order-service`. |
| `order-service-prod.yml` | Cấu hình dành cho `order-service` khi profile `prod` được yêu cầu. |
| `payment-service-staging.yml` | Cấu hình dành cho `payment-service` khi profile `staging` được yêu cầu. |

Quy tắc tổng quát là:

```text
{application}.yml
{application}-{profile}.yml
application.yml
application-{profile}.yml
```

Trong đó `application` là tên ứng dụng mà client gửi đến Config Server; `profile` là một profile đang hoạt động. Các định dạng `.yaml` và `.properties` cũng có thể được sử dụng tùy cấu hình và phiên bản. Nên chọn một định dạng chính cho cả repository để việc review và kiểm tra tự động nhất quán.

Tên application phải khớp với `spring.application.name` của client. Ví dụ:

```yaml
spring:
  application:
    name: order-service
```

Tên file theo ứng dụng khi đó bắt đầu bằng `order-service`. Nếu ứng dụng đổi tên thành `orders-api` nhưng file vẫn giữ tiền tố `order-service`, Config Server sẽ không tự hiểu hai tên đó là một.

Nên thống nhất cách đặt tên dễ đọc, chẳng hạn chữ thường và dấu gạch ngang (`order-service`, `payment-service`, `inventory-service`). Profile cũng nên dùng một tập tên chuẩn xuyên suốt hệ thống (`dev`, `test`, `staging`, `prod`) để tránh các biến thể như `production`, `prd` và `prod` cùng chỉ một môi trường.

## 3. Chiến lược 1: Một thư mục phẳng cho toàn bộ ứng dụng

Với số lượng dịch vụ nhỏ hoặc vừa, có thể đặt file cấu hình ở thư mục gốc của repository:

```text
config-repo/
├── application.yml
├── application-dev.yml
├── application-staging.yml
├── application-prod.yml
├── order-service.yml
├── order-service-dev.yml
├── order-service-prod.yml
├── payment-service.yml
├── payment-service-dev.yml
├── payment-service-prod.yml
├── inventory-service.yml
└── inventory-service-prod.yml
```

Ưu điểm của cách này là đơn giản. Không cần cấu hình `search-paths`; Config Server có thể tìm file theo quy ước tên ngay trong repository. Người mới dễ hiểu file nào dùng chung, file nào dành riêng cho một ứng dụng và profile.

Ví dụ `application.yml` chứa các giá trị mặc định chung:

```yaml
logging:
  level:
    root: INFO

platform:
  http:
    connect-timeout: 3s
    read-timeout: 10s
```

`application-prod.yml` có thể điều chỉnh một số giá trị chung ở production:

```yaml
logging:
  level:
    root: WARN

platform:
  http:
    connect-timeout: 2s
    read-timeout: 8s
```

`order-service.yml` chứa cấu hình mặc định riêng của order service:

```yaml
orders:
  reservation-timeout: 10s
  max-items-per-request: 100
```

`order-service-prod.yml` có thể điều chỉnh giới hạn riêng cho production:

```yaml
orders:
  reservation-timeout: 6s
  max-items-per-request: 50
```

Không cần tạo file theo mọi tổ hợp application/profile nếu ứng dụng không có giá trị riêng cần thay đổi. File dùng chung có thể cung cấp mặc định; file cụ thể chỉ nên xuất hiện khi thực sự có khác biệt. Điều này giảm số file và tránh tạo ra nhiều bản sao gần giống nhau.

Khi repository có hàng chục hoặc hàng trăm dịch vụ, thư mục phẳng có thể trở nên khó duyệt. Tên file dài và danh sách file lớn cũng làm pull request khó theo dõi. Khi đó có thể chuyển sang bố cục theo thư mục.

## 4. Chiến lược 2: Chia thư mục theo ứng dụng

Một cách tổ chức khác là đặt cấu hình từng ứng dụng trong thư mục riêng, đồng thời dành một thư mục cho cấu hình dùng chung:

```text
config-repo/
├── common/
│   ├── application.yml
│   └── application-prod.yml
├── order-service/
│   ├── order-service.yml
│   ├── order-service-dev.yml
│   └── order-service-prod.yml
├── payment-service/
│   ├── payment-service.yml
│   ├── payment-service-staging.yml
│   └── payment-service-prod.yml
└── inventory-service/
    ├── inventory-service.yml
    └── inventory-service-prod.yml
```

Config Server có thể tìm trong nhiều thư mục bằng Git `search-paths`. Ví dụ cấu hình runtime của Config Server:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: ${CONFIG_REPO_URI}
          default-label: main
          search-paths:
            - '{application}'
            - common
```

Placeholder `{application}` cho phép tìm thư mục có tên ứng với application mà client yêu cầu. Với `order-service`, server tìm trong thư mục `order-service` và thư mục `common`. File `application-prod.yml` trong `common` có thể cung cấp giá trị chung theo profile; file `order-service-prod.yml` trong thư mục ứng dụng chứa phần riêng của order service.

Khi sử dụng `search-paths`, phải kiểm tra kết quả endpoint để xác nhận server đã tìm đúng file và property source. Nếu cùng một khóa xuất hiện ở cả thư mục chung và thư mục ứng dụng, không nên dựa vào cảm giác về thứ tự thư mục để kết luận giá trị nào thắng. Hãy xem thứ tự property source trả về trên đúng phiên bản Spring Cloud Config và kiểm chứng bằng một khóa thử nghiệm.

Một phương án khác là chia thư mục theo môi trường, chẳng hạn `dev/`, `staging/`, `prod/` và dùng placeholder `{profile}` trong `search-paths`. Cách này có thể phù hợp khi nhóm vận hành quản lý thay đổi theo môi trường, nhưng cần kiểm tra kỹ khi một client kích hoạt nhiều profile hoặc khi cấu trúc file có cả cấu hình chung và cấu hình riêng theo ứng dụng. Với hệ thống mới, chia theo ứng dụng thường dễ kiểm soát quyền sở hữu hơn.

`search-paths` chỉ điều khiển nơi Config Server tìm file trong repository. Nó không phải cơ chế phân quyền, không tự giới hạn client chỉ được đọc thư mục cùng tên và không thay thế việc bảo vệ endpoint Config Server.

## 5. Chiến lược 3: Tách nhiều Git repository theo nhóm ứng dụng

Khi nhiều nhóm phát triển có vòng đời phát hành, quyền truy cập hoặc yêu cầu cô lập khác nhau, một repository duy nhất có thể không còn phù hợp. Config Server Git backend hỗ trợ cấu hình nhiều repository và chọn repository theo pattern của application/profile.

Ví dụ bố cục repository:

```text
configuration-sources/
├── platform-shared-config/
├── orders-config/
├── payments-config/
└── inventory-config/
```

Config Server có thể khai báo repository mặc định và các repository chuyên biệt:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: ${DEFAULT_CONFIG_REPO_URI}
          default-label: main
          repos:
            orders:
              pattern: 'order-service/*'
              uri: ${ORDERS_CONFIG_REPO_URI}
            payments:
              pattern: 'payment-service/*'
              uri: ${PAYMENTS_CONFIG_REPO_URI}
            inventory:
              pattern: 'inventory-service/*'
              uri: ${INVENTORY_CONFIG_REPO_URI}
```

Pattern được xét dựa trên application/profile mà client yêu cầu. Ví dụ `order-service/prod` có thể được định tuyến đến repository cấu hình orders. Cần kiểm tra cú pháp pattern và hành vi chọn repository trên phiên bản Spring Cloud Config đang triển khai; nếu pattern chồng lấn, hãy làm cho chúng rõ ràng và không nhập nhằng.

Mỗi repository có thể có `search-paths`, `default-label` và thông tin truy cập riêng nếu cần. Tách repository giúp:

- Phân quyền đọc và ghi theo nhóm sở hữu.
- Review, phát hành và rollback cấu hình của một nhóm độc lập.
- Giảm phạm vi ảnh hưởng khi một nhóm thay đổi cấu hình.
- Áp dụng quy tắc bảo vệ branch và quy trình phê duyệt riêng.

Đổi lại, số repository, credential, pipeline và quy tắc đồng bộ tăng lên. Nếu nhiều ứng dụng vẫn dùng chung một bộ giá trị nền tảng, cần quyết định rõ cách quản lý phần cấu hình chung: dùng repository mặc định, đưa cấu hình chung vào từng repository theo quy trình đồng bộ, hay dùng một backend phù hợp với mô hình tổ chức. Không nên sao chép thủ công cùng một file vào nhiều nơi vì các bản sao sẽ dần lệch nhau.

Lưu ý: định tuyến đến repository khác nhau không tự động đồng nghĩa với phân quyền client. Config Server vẫn phải xác thực và kiểm soát application/profile mà mỗi danh tính được phép yêu cầu.

## 6. Hiểu đúng ba chiều application, profile và label

Ba chiều này có quan hệ với nhau nhưng giải quyết ba vấn đề riêng.

| Chiều | Câu hỏi | Ví dụ | Tác động đến việc tìm cấu hình |
|---|---|---|---|
| Application | Dịch vụ nào đang yêu cầu? | `order-service` | Chọn nhóm file hoặc repository ứng với ứng dụng. |
| Profile | Ứng dụng đang chạy trong chế độ nào? | `prod` | Chọn file cấu hình theo môi trường hoặc profile. |
| Label | Cần đọc phiên bản cấu hình nào? | `release-2026-11` | Chọn branch, tag hoặc commit của Git backend. |

Client có thể khai báo tên và profile:

```yaml
spring:
  application:
    name: order-service
  profiles:
    active: prod
  config:
    import: "configserver:${CONFIG_SERVER_URI}"
  cloud:
    config:
      label: release-2026-11
```

Yêu cầu tương ứng có dạng:

```text
GET /order-service/prod/release-2026-11
```

Profile không phải tên branch và label không phải tên thư mục môi trường. Ví dụ `prod` chọn bộ cấu hình production, trong khi `release-2026-11` chọn revision của repository chứa bộ file đó. Dùng label cố định như tag hoặc commit giúp một lần phát hành có thể tái lập. Dùng branch di động có nghĩa nội dung cấu hình tại cùng label có thể thay đổi sau mỗi commit.

Nếu client kích hoạt nhiều profile, request có thể chứa danh sách profile. Thứ tự profile có thể ảnh hưởng việc ghép property source. Hãy thống nhất thứ tự kích hoạt và kiểm tra phản hồi endpoint thay vì giả định các profile có thể hoán đổi vị trí.

## 7. Cách thiết kế cấu hình chung và cấu hình riêng

Một quy tắc hữu ích là đặt mặc định dùng chung ở phạm vi rộng nhất cần thiết, rồi chỉ ghi phần khác biệt ở phạm vi hẹp hơn.

Ví dụ:

```text
application.yml                 # timeout và logging mặc định
application-prod.yml             # logging/timeout chung cho production
order-service.yml                # chính sách mặc định của order service
order-service-prod.yml           # khác biệt của order service ở production
payment-service.yml              # chính sách mặc định của payment service
payment-service-prod.yml         # khác biệt của payment service ở production
```

Khi cùng một khóa xuất hiện ở nhiều nguồn, giá trị cuối phụ thuộc thứ tự property source của Config Server và Spring Environment. Vì vậy:

- Chỉ đưa giá trị thật sự dùng chung vào `application.yml`.
- Không đặt cấu hình nghiệp vụ riêng của một dịch vụ vào file dùng chung chỉ để tránh tạo thêm file.
- Hạn chế lặp lại toàn bộ file chung trong từng file ứng dụng; chỉ khai báo các khóa cần điều chỉnh.
- Khi có giá trị đặc biệt cho một môi trường, ghi rõ trong file application-profile tương ứng.
- Kiểm tra property source trả về và giá trị đã bind trong client sau khi thay đổi.

Không dùng profile để biểu diễn tên nhóm hoặc tên ứng dụng. Profile nên thể hiện chế độ chạy (ví dụ `prod`); application name biểu diễn dịch vụ (ví dụ `order-service`). Nếu đưa cả tên team, region, tenant và môi trường vào một chuỗi profile dài, số tổ hợp sẽ tăng nhanh và khó kiểm soát.

## 8. Những gì không nên đưa vào kho cấu hình dùng chung

Git giúp quản lý phiên bản và review, nhưng không tự biến repository thành nơi lưu bí mật an toàn. Không commit trực tiếp:

- Mật khẩu database hoặc message broker.
- API token, OAuth client secret và access key.
- Private key, certificate key store password và khóa mã hóa.
- Credential dùng để Config Server clone repository riêng tư.
- Thông tin xác thực để client gọi Config Server.

Ưu tiên secret manager hoặc cơ chế cấp phát secret của nền tảng triển khai. Nếu dùng mã hóa của Spring Cloud Config với giá trị `{cipher}`, khóa giải mã phải được cấp riêng cho Config Server và bảo vệ khỏi repository mà server phân phối. Cần hiểu rằng giá trị đã giải mã có thể được trả về client được phép yêu cầu; do đó quyền truy cập endpoint và repository vẫn rất quan trọng.

Không đặt bí mật ở `application.yml` dùng chung với suy nghĩ rằng chỉ một dịch vụ cần dùng đến nó. File dùng chung có thể được phân phối đến nhiều client. Nếu một secret chỉ dành cho `payment-service`, phải thiết kế nguồn cấp phát và quyền truy cập theo phạm vi đó.

## 9. Quy ước quản trị repository

Thiết kế file tốt cần đi cùng quy trình thay đổi rõ ràng:

1. **Quy ước tên**: thống nhất application name, profile, extension và cách viết key.
2. **Quyền sở hữu**: xác định team chịu trách nhiệm cho từng ứng dụng hoặc thư mục.
3. **Review**: dùng pull request, yêu cầu người sở hữu dịch vụ phê duyệt thay đổi liên quan.
4. **Kiểm tra tự động**: parse YAML, kiểm tra schema, kiểu dữ liệu, khóa bắt buộc, tên file và secret bị commit nhầm.
5. **Phiên bản**: dùng branch cho phát triển, tag hoặc commit cố định cho phát hành cần tái lập.
6. **Rollback**: revert commit hoặc chuyển label về revision đã xác nhận tốt.
7. **Theo dõi**: ghi nhận application, profile, label và commit cấu hình đã dùng cho từng lần triển khai.

Với production, không nên để một branch `main` di động là bằng chứng duy nhất cho cấu hình của một phiên bản ứng dụng. Pipeline nên ghi lại commit hoặc tag thực tế để điều tra và khôi phục sau sự cố.

## 10. Kiểm tra Config Server đã tìm đúng file

Config Server cung cấp endpoint theo dạng:

```text
GET /{application}/{profile}/{label}
```

Ví dụ:

```text
GET https://config.example.internal/order-service/prod/release-2026-11
```

Phản hồi chứa thông tin `Environment` và danh sách property source. Khi kiểm tra, chú ý:

- `name`, `profiles` và `label` có đúng với yêu cầu không.
- Các property source có đến từ đúng file hoặc thư mục không.
- File cấu hình chung và file riêng của ứng dụng có được tìm thấy không.
- Revision hoặc label có đúng với lần phát hành không.
- Có khóa nhạy cảm nào vô tình xuất hiện trong phản hồi không.

Sau đó kiểm tra phía client để xác nhận giá trị cuối cùng mà ứng dụng bind được. Kết quả endpoint cho biết server tìm thấy nguồn nào; Spring `Environment` của client còn có thể chứa các nguồn cục bộ, biến môi trường, JVM property hoặc tham số dòng lệnh có độ ưu tiên khác.

Nếu server trả về thiếu cấu hình, hãy điều tra theo thứ tự:

1. Xác nhận `spring.application.name` của client.
2. Xác nhận profile thực sự đang active, bao gồm profile được kích hoạt bổ sung.
3. Xác nhận label có tồn tại trong Git repository được chọn.
4. Kiểm tra tên file có khớp quy ước application/profile không.
5. Kiểm tra `search-paths` và placeholder thư mục có trỏ đến vị trí đúng không.
6. Nếu dùng nhiều repository, kiểm tra pattern có chọn đúng repository không.
7. Kiểm tra quyền đọc Git và log của Config Server.

Không nên sửa nhiều file cùng lúc khi chưa xác định tầng gây lỗi. Một thay đổi có kiểm soát sẽ giúp phân biệt lỗi định tuyến repository, lỗi tìm file và lỗi ưu tiên property source.

## 11. Chọn chiến lược tổ chức phù hợp

| Tiêu chí | Thư mục phẳng | Thư mục theo ứng dụng | Nhiều Git repository |
|---|---|---|---|
| Độ đơn giản ban đầu | Cao | Trung bình | Thấp hơn |
| Số ứng dụng phù hợp | Ít đến vừa | Vừa đến nhiều | Nhiều, có nhóm sở hữu độc lập |
| Cấu hình server cần thêm | Hầu như không | `search-paths` | `repos` và pattern |
| Quyền sở hữu theo team | Khó hơn khi repo lớn | Dễ phân vùng review | Rõ hơn theo repository |
| Phát hành độc lập | Theo label/branch chung | Theo label/branch chung | Có thể độc lập theo repo |
| Chi phí vận hành | Thấp | Vừa | Cao hơn do nhiều repo và credential |

Không có một bố cục đúng cho mọi tổ chức. Hãy bắt đầu từ cấu trúc đơn giản nhất đáp ứng số lượng ứng dụng, số profile, quyền sở hữu và yêu cầu phát hành. Chuyển sang thư mục hoặc nhiều repository khi có vấn đề cụ thể về khả năng tìm kiếm, quyền truy cập hoặc vòng đời thay đổi.

## 12. Bài thực hành

### Bước 1: Tạo repository phẳng

Tạo `application.yml`, `application-prod.yml`, `order-service.yml` và `order-service-prod.yml`. Dùng cùng một khóa thử nghiệm với các giá trị khác nhau để quan sát những property source được trả về.

**Kết quả cần đạt:** xác định được quy ước đặt tên và các file ứng với application/profile.

### Bước 2: Chuyển sang thư mục theo ứng dụng

Tạo thư mục `common/` và `order-service/`. Cấu hình `search-paths` có `{application}` và `common`, sau đó gọi endpoint cho `order-service/prod/main`.

**Kết quả cần đạt:** xác nhận Config Server tìm được file trong nhiều thư mục và hiểu tác động của search path.

### Bước 3: Thử label khác nhau

Tạo branch hoặc tag cấu hình thứ hai, thay đổi một giá trị, rồi gọi endpoint với từng label.

**Kết quả cần đạt:** phân biệt label với profile và biết cách ghim phiên bản cấu hình.

### Bước 4: Thử định tuyến nhiều repository

Tạo repository riêng cho `order-service`, khai báo pattern trong `spring.cloud.config.server.git.repos`, sau đó yêu cầu cấu hình của order service và một ứng dụng không có pattern riêng.

**Kết quả cần đạt:** giải thích được Config Server chọn repository nào và khi nào dùng repository mặc định.

### Bước 5: Kiểm tra quyền và chất lượng

Thử truy cập endpoint bằng danh tính được phép và không được phép. Bổ sung kiểm tra YAML/schema trong pull request, đồng thời rà soát file để chắc chắn không chứa secret.

**Kết quả cần đạt:** hiểu rằng tổ chức file cần đi cùng xác thực, phân quyền, review và kiểm tra tự động.

## 13. Tự kiểm tra

1. File `application-prod.yml` và `order-service-prod.yml` khác nhau ở phạm vi nào?
2. Vì sao tên file phải khớp với `spring.application.name`?
3. Khi nào nên dùng repository phẳng và khi nào nên chia thư mục theo ứng dụng?
4. `search-paths` giải quyết vấn đề gì? Nó không giải quyết vấn đề gì?
5. Placeholder `{application}` trong `search-paths` giúp ích thế nào?
6. Khi nào nên tách nhiều Git repository theo pattern?
7. Profile và label khác nhau như thế nào trong một lần yêu cầu cấu hình?
8. Làm sao xác minh Config Server đã chọn đúng repository, thư mục và revision?
9. Vì sao không nên commit secret vào `application.yml` dùng chung?
10. Cần lưu thông tin nào để tái lập cấu hình của một lần phát hành production?

Khi hoàn thành bài thực hành, người học có thể thiết kế repository theo quy mô hệ thống, tổ chức file theo application/profile, chọn label có kiểm soát và xác minh được Config Server phân phối đúng cấu hình đến từng client.
