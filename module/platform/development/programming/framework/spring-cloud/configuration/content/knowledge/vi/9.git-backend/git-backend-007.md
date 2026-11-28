# Ánh xạ nhiều repository bằng mẫu tên ứng dụng và profile

Khi số lượng ứng dụng và môi trường tăng lên, một Git repository duy nhất có thể trở nên khó quản lý: nhiều nhóm cùng thay đổi cấu hình, quyền đọc/ghi khác nhau và lịch phát hành không giống nhau. Spring Cloud Config Server cho phép khai báo nhiều Git repository và chọn repository dựa trên tên ứng dụng hoặc kết hợp tên ứng dụng với profile.

Cơ chế này giúp tách quyền sở hữu và vòng đời cấu hình. Ví dụ, cấu hình của nhóm thanh toán có thể nằm trong repository riêng, cấu hình production có thể được quản lý bởi một quy trình phát hành chặt hơn, còn các ứng dụng nhỏ vẫn dùng repository mặc định. Để thiết kế đúng, cần hiểu cách `pattern` khớp với application/profile, thứ tự chọn repository và vai trò độc lập của Git label.

## 1. Vì sao cần ánh xạ nhiều Git repository?

Một repository tập trung phù hợp khi các ứng dụng có cùng quy trình quản lý và quyền truy cập. Khi tổ chức phát triển, có thể xuất hiện nhu cầu:

- Nhóm thanh toán quản lý cấu hình trong repository chỉ nhóm đó được ghi.
- Các ứng dụng thuộc môi trường production dùng repository hoặc nhánh đã được phê duyệt riêng.
- Các ứng dụng theo nhóm sản phẩm cần lịch phát hành cấu hình độc lập.
- Một số dịch vụ cần search path hoặc Git label mặc định khác.
- Repository mặc định tiếp tục phục vụ các ứng dụng chưa có quy tắc định tuyến riêng.

Git backend của Config Server hỗ trợ cấu hình `repos`, trong đó mỗi entry có một hoặc nhiều pattern cùng URI repository. Khi nhận request, server so khớp application/profile để chọn repository phù hợp. Entry có thể cấu hình URI, label mặc định, search paths và thông tin kết nối Git riêng.

## 2. Phân biệt application, profile và label

Config Server nhận request Environment với dạng phổ biến:

```text
/{application}/{profile}/{label}
```

Ba thành phần này có vai trò khác nhau:

| Thành phần | Ví dụ | Dùng để làm gì? |
|---|---|---|
| Application | `payment-service` | Xác định ứng dụng cần lấy cấu hình |
| Profile | `prod` | Xác định cấu hình theo môi trường hoặc nhóm hành vi |
| Label | `release-2026.11` | Chọn branch, tag hoặc Git ref bên trong repository đã chọn |

`pattern` quyết định repository nào phục vụ application hoặc cặp application/profile. `label` sau đó chọn phiên bản cấu hình bên trong repository đó. Vì vậy, đổi label không tự chuyển request sang một repository khác; đổi profile có thể làm request khớp một pattern khác nếu pattern chứa profile.

Ví dụ:

```text
GET /payment-service/prod/main
```

Request này có application `payment-service`, profile `prod` và label `main`. Config Server dùng application/profile để tìm repository, rồi đọc ref `main` trong repository được chọn.

## 3. Cấu hình nhiều repository bằng `repos`

Có thể khai báo một URI Git mặc định ở cấp `git` và các repository chuyên biệt trong `repos`:

```yaml
server:
  port: 8888

spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.com/platform/config-default.git
          default-label: main
          clone-on-start: true
          repos:
            payment-production:
              pattern:
                - 'payment-service/prod'
                - 'payment-service/perf'
              uri: https://git.example.com/payments/config-production.git
              default-label: release
              search-paths:
                - config

            catalog-staging:
              pattern: 'catalog-service/staging'
              uri: https://git.example.com/catalog/config-staging.git
              default-label: main

            payment-applications:
              pattern: 'payment-*'
              uri: https://git.example.com/payments/config.git
              default-label: main
```

Trong ví dụ:

- `payment-production` phục vụ `payment-service` với profile `prod` hoặc `perf`.
- `catalog-staging` phục vụ `catalog-service` với profile `staging`.
- `payment-applications` phục vụ các application có tên khớp `payment-*` khi không có pattern cụ thể hơn được chọn.
- `uri` ở cấp `git` là repository mặc định cho request không khớp entry chuyên biệt.

Tên `payment-production`, `catalog-staging` và `payment-applications` là tên định danh entry trong cấu hình Config Server. Chúng không phải application name mà client gửi lên.

Trong YAML, có thể khai báo một pattern dạng chuỗi hoặc một danh sách pattern. Dùng dấu nháy cho pattern có ký tự đặc biệt để YAML giữ nguyên nội dung.

## 4. Cách pattern khớp application và profile

Pattern có thể khớp tên application hoặc cặp application/profile:

| Pattern | Ý nghĩa | Request ví dụ được khớp |
|---|---|---|
| `payment-service` | Khớp application cụ thể | `payment-service/dev` |
| `payment-*` | Khớp các application có tiền tố `payment-` | `payment-service/prod` |
| `*/staging` | Khớp mọi application dùng profile `staging` | `catalog-service/staging` |
| `payment-service/prod` | Khớp đúng application và profile | `payment-service/prod` |
| `order-*/prod` | Khớp nhóm application và profile production | `order-service/prod` |

Nếu pattern có phần profile, Config Server so khớp theo cặp `application/profile`. Nếu pattern chỉ có tên application, nó được so khớp theo application. Ký tự `*` thường được dùng làm wildcard cho phần tên tương ứng.

Một entry có thể khai báo nhiều pattern khi cùng một repository phục vụ nhiều cặp application/profile:

```yaml
repos:
  payment-release:
    pattern:
      - 'payment-service/prod'
      - 'payment-service/perf'
      - 'refund-service/prod'
    uri: https://git.example.com/payments/release-config.git
```

Chỉ gộp các ứng dụng vào cùng repository khi chúng thực sự chia sẻ quyền sở hữu, quy trình review và vòng đời phát hành. Pattern càng rộng thì phạm vi ứng dụng được định tuyến vào repository càng lớn.

## 5. Đặt pattern cụ thể trước pattern tổng quát

Khi nhiều pattern có thể khớp cùng một request, thứ tự khai báo ảnh hưởng đến entry được chọn. Hãy đặt pattern cụ thể trước, pattern rộng sau và để repository mặc định làm phương án dự phòng.

Ví dụ có ba quy tắc:

```yaml
repos:
  payment-prod:
    pattern: 'payment-service/prod'
    uri: https://git.example.com/payments/prod-config.git

  all-prod:
    pattern: '*/prod'
    uri: https://git.example.com/platform/all-prod-config.git

  payment-family:
    pattern: 'payment-*'
    uri: https://git.example.com/payments/shared-config.git
```

Với request `payment-service/prod`, quy tắc `payment-prod` là quy tắc chuyên biệt cần được chọn trước. Nếu đặt `*/prod` trước, quy tắc tổng quát có thể nhận request trước và khiến repository chuyên biệt không được sử dụng. Vì vậy:

1. Đặt exact match của application/profile lên đầu.
2. Tiếp theo là pattern theo nhóm ứng dụng hoặc profile.
3. Cuối cùng mới đến pattern rộng.
4. Giữ URI mặc định cho các request không khớp repository chuyên biệt.

Không nên tạo hai entry có pattern trùng nhau hoặc chồng lấn nếu không có lý do rõ ràng. Khi thay đổi thứ tự, hãy kiểm tra lại các request đại diện cho từng nhóm ứng dụng để phát hiện route bị thay đổi ngoài dự kiến.

## 6. Tổ chức nội dung bên trong từng repository

Mỗi repository được chọn vẫn dùng quy ước tên tệp Config Server quen thuộc. Ví dụ repository `config-production`:

```text
config-production/
├── application.yml
├── application-prod.yml
├── payment-service.yml
├── payment-service-prod.yml
└── refund-service-prod.yml
```

Các tệp có ý nghĩa:

- `application.yml`: cấu hình chung trong repository này.
- `application-prod.yml`: cấu hình profile production dùng chung trong repository này.
- `payment-service.yml`: cấu hình riêng cho `payment-service`.
- `payment-service-prod.yml`: cấu hình riêng cho ứng dụng và profile production.

Có thể đặt cấu hình trong thư mục con bằng `search-paths`:

```yaml
repos:
  payment-production:
    pattern: 'payment-service/prod'
    uri: https://git.example.com/payments/config-production.git
    search-paths:
      - services/payment
      - shared
```

Khi đó, Config Server tìm các tệp cấu hình trong những search path đã khai báo theo quy tắc của Git environment repository. Đảm bảo các thư mục tồn tại trong repository và không đặt cùng một key ở nhiều thư mục nếu không có chủ đích về ưu tiên. Tên nguồn trong response Environment giúp kiểm tra key được lấy từ file hoặc path nào.

Lưu ý rằng pattern routing chọn repository phù hợp cho request. Nó không tự động lấy `application.yml` từ repository mặc định rồi ghép thêm `payment-service-prod.yml` từ repository chuyên biệt. Nếu cần một bộ cấu hình chung thực sự được kết hợp từ nhiều backend, cần thiết kế composite environment repository hoặc cơ chế chia sẻ phù hợp; không giả định fallback repository sẽ được merge với repository đã match.

## 7. Repository riêng có thể có label và cấu hình Git riêng

Mỗi repository có thể cần branch mặc định khác nhau:

```yaml
repos:
  payment-production:
    pattern: 'payment-service/prod'
    uri: https://git.example.com/payments/config-production.git
    default-label: release

  catalog-staging:
    pattern: 'catalog-service/staging'
    uri: https://git.example.com/catalog/config-staging.git
    default-label: develop
```

Nếu client không truyền label, Config Server dùng `default-label` của repository được chọn hoặc giá trị mặc định ở cấp Git tùy cấu hình. Nếu request truyền label rõ ràng, label đó được tìm trong repository đã chọn.

Ví dụ:

```text
GET /payment-service/prod/release
GET /catalog-service/staging/develop
```

Một label phải tồn tại trong đúng repository được chọn. Nếu `release` chỉ có ở repository thanh toán nhưng request được route sang repository khác, server không tự tìm label đó ở repository còn lại.

Các entry cũng có thể dùng `search-paths` hoặc thông tin xác thực riêng nếu Git server yêu cầu. Không đưa username/password dạng rõ vào file được commit. Cấp credential qua secret manager, biến môi trường hoặc cơ chế bảo mật của nền tảng triển khai; giới hạn quyền đọc theo từng repository khi có thể.

## 8. Kiểm tra repository được chọn bằng HTTP

Để xác minh routing, nên đặt một key marker không nhạy cảm trong mỗi repository:

```yaml
# Trong config-production/application.yml
repository:
  source: payments-production
```

```yaml
# Trong config-staging/application.yml
repository:
  source: catalog-staging
```

Gửi request đến Config Server:

```bash
curl "http://localhost:8888/payment-service/prod/release"
curl "http://localhost:8888/catalog-service/staging/develop"
curl "http://localhost:8888/order-service/dev/main"
```

Kiểm tra các trường trong response Environment:

- `name`: application được yêu cầu.
- `profiles`: profile được dùng để phân giải.
- `label`: Git ref được chọn.
- `version`: commit ID nếu backend trả về.
- `propertySources`: các nguồn được đọc từ repository đã chọn.
- `repository.source`: marker giúp nhận biết repository trong bài kiểm tra.

Marker là dữ liệu kiểm thử do nhóm tự đặt, không phải field chuẩn mà Config Server tự sinh. Trong môi trường thật, có thể dùng `version` và `propertySources[].name` cùng với log server để truy vết repository và commit. Tránh ghi giá trị bí mật vào marker hoặc response.

Nếu response thiếu marker, kiểm tra pattern, URI, label, branch và vị trí tệp. Nếu marker cho thấy repository khác, kiểm tra các pattern chồng lấn và thứ tự entry.

## 9. Quy trình thiết kế và thay đổi pattern

Trước khi thêm một repository hoặc sửa pattern, thực hiện các bước:

1. **Phân nhóm ứng dụng:** xác định nhóm sở hữu, môi trường và quyền đọc/ghi cấu hình.
2. **Chọn ranh giới repository:** tách khi cần độc lập về quyền, review, lịch phát hành hoặc chính sách vận hành.
3. **Viết pattern:** xác định chính xác pattern khớp application hay application/profile; tránh wildcard quá rộng.
4. **Sắp xếp quy tắc:** đặt pattern cụ thể trước pattern tổng quát và xác định rõ URI mặc định.
5. **Chọn label:** quy định branch/tag mặc định và cách client yêu cầu label phát hành.
6. **Cấu hình truy cập:** cấp quyền đọc tối thiểu, TLS và credential riêng khi cần.
7. **Kiểm tra routing:** gửi request cho application/profile đại diện, xác nhận marker, version và property sources.
8. **Theo dõi và rollback:** lưu lại thay đổi mapping; khi route sai, khôi phục cấu hình server trước đó và xác minh các request liên quan.

Một thay đổi pattern có thể làm nhiều client chuyển sang repository khác mà không cần thay mã nguồn. Vì thế, cấu hình định tuyến Git cần được review và phát hành như một thay đổi hạ tầng có ảnh hưởng đến nhiều dịch vụ.

## 10. Lỗi thường gặp khi ánh xạ nhiều repository

| Hiện tượng | Nguyên nhân có thể có | Cách kiểm tra |
|---|---|---|
| Client nhận cấu hình từ repository mặc định | Không có pattern khớp hoặc pattern viết sai | So sánh application/profile trong URL với từng pattern |
| Request production bị route vào repository chung | Pattern `*/prod` đặt trước pattern chuyên biệt | Sắp xếp lại pattern và kiểm tra request cụ thể |
| Repository được chọn nhưng thiếu tệp | Tệp nằm sai thư mục hoặc thiếu `search-paths` | Kiểm tra cấu trúc repo và `propertySources[].name` |
| Label không tìm thấy | Label không tồn tại trong repository đã chọn | Kiểm tra branch/tag trong đúng repository và `default-label` |
| Config Server không clone được một repository | URI sai, credential thiếu hoặc server không có quyền | Xem log server và thử xác thực từ môi trường triển khai |
| Hai ứng dụng nhận cùng cấu hình ngoài ý muốn | Pattern wildcard quá rộng hoặc hai rule chồng lấn | Kiểm tra thứ tự pattern và marker trong từng repo |
| Cấu hình chung bị mất sau khi tách repo | Nghĩ rằng repository mặc định sẽ được merge với repo chuyên biệt | Đưa baseline vào repo được chọn hoặc thiết kế composite repository |

## 11. Nguyên tắc vận hành an toàn

- Dùng pattern hẹp và dễ đọc; tránh wildcard bao phủ nhiều ứng dụng ngoài dự kiến.
- Đặt exact match trước pattern nhóm và pattern profile rộng.
- Xem label là Git ref bên trong repository đã chọn, không phải tiêu chí thay repository.
- Giữ repository mặc định làm fallback có chủ đích; kiểm tra ứng dụng nào đang dựa vào fallback đó.
- Dùng marker không nhạy cảm, `version` và `propertySources` để xác minh routing.
- Quản lý credential ngoài Git, giới hạn quyền đọc và bảo vệ Config Server bằng HTTPS/TLS cùng xác thực.
- Kiểm thử tất cả application/profile quan trọng sau khi thay đổi mapping.

Ánh xạ nhiều Git repository giúp tổ chức tách quyền sở hữu và vòng đời cấu hình theo nhóm ứng dụng hoặc môi trường. Khi pattern được thiết kế rõ ràng, sắp xếp có chủ đích và kiểm tra qua HTTP request, Config Server có thể định tuyến đúng nguồn cấu hình mà vẫn giữ được khả năng truy vết phiên bản và kiểm soát thay đổi.
