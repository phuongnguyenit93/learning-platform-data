# search-paths và placeholder theo ứng dụng, profile hoặc label

Git backend của Spring Cloud Config Server có thể đọc cấu hình từ nhiều thư mục trong cùng một repository. Thuộc tính `search-paths` khai báo các thư mục mà server cần tìm file cấu hình. Trong các đường dẫn này, có thể dùng placeholder `{application}`, `{profile}` và `{label}` để chọn thư mục theo request hiện tại.

Cách tổ chức này hữu ích khi repository có nhiều ứng dụng, nhiều môi trường hoặc nhiều dòng cấu hình. Thay vì đặt tất cả file ở thư mục gốc, nhóm có thể phân chia theo phạm vi rồi để Config Server tìm đúng vị trí dựa trên thông tin client gửi lên. Cần hiểu rõ placeholder được thay thế ở phía Git backend, cách các thư mục được kết hợp và cách kiểm tra property source để tránh đọc nhầm cấu hình.

## 1. search-paths giải quyết vấn đề gì?

Một repository nhỏ có thể đặt tất cả file cấu hình ở thư mục gốc:

```text
config-repo/
├── application.yml
├── application-prod.yml
├── orders-service.yml
├── orders-service-prod.yml
├── payment-service.yml
└── payment-service-prod.yml
```

Khi số lượng ứng dụng và profile tăng, thư mục gốc có thể trở nên khó quản lý. Tên file vẫn cho biết application và profile, nhưng các nhóm muốn tách vùng sở hữu, cấu hình dùng chung và cấu hình theo release thành các thư mục riêng.

Ví dụ, có thể tổ chức:

```text
config-repo/
├── shared/
│   ├── application.yml
│   └── application-prod.yml
├── applications/
│   ├── orders-service/
│   │   ├── orders-service.yml
│   │   └── orders-service-prod.yml
│   └── payment-service/
│       ├── payment-service.yml
│       └── payment-service-prod.yml
├── profiles/
│   ├── dev/
│   │   └── application-dev.yml
│   └── prod/
│       ├── application-prod.yml
│       └── orders-service-prod.yml
└── snapshots/
    ├── main/
    │   └── application.yml
    └── release-2026.11/
        └── application.yml
```

Config Server cần được chỉ dẫn để tìm trong các thư mục này. Đó là vai trò của `spring.cloud.config.server.git.search-paths`.

`search-paths` là danh sách đường dẫn tương đối bên trong Git working tree mà backend Git sử dụng. Mỗi phần tử có thể là đường dẫn cụ thể hoặc pattern có placeholder và wildcard. Server tìm các file cấu hình phù hợp với application/profile trong các vị trí được chỉ định rồi đưa chúng vào Environment trả về cho client.

## 2. Cấu hình search-paths tĩnh

Nếu repository có một số thư mục cố định, có thể khai báo trực tiếp:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.com/platform/config-repo.git
          default-label: main
          clone-on-start: true
          search-paths:
            - shared
            - applications
            - profiles
```

Cấu hình trên yêu cầu Git backend tìm file cấu hình trong các thư mục `shared`, `applications` và `profiles`. Tuy nhiên, nếu mỗi ứng dụng nằm trong một thư mục con riêng, chỉ khai báo `applications` có thể chưa đủ để chỉ đúng các thư mục con cần tìm. Khi đó, dùng placeholder hoặc wildcard để mô tả cấu trúc sâu hơn.

Đường dẫn trong `search-paths` được tính từ gốc repository đã checkout. Nếu muốn tiếp tục sử dụng file ở thư mục gốc, có thể thêm `.` vào danh sách search path. Nếu toàn bộ cấu hình đã được chuyển vào các thư mục con, không cần thêm thư mục gốc.

Nên khai báo các path rõ ràng và giới hạn phạm vi tìm kiếm. Một pattern quá rộng có thể khiến server đọc thêm file của ứng dụng khác hoặc tạo ra nhiều property source khó kiểm soát.

## 3. Placeholder {application}, {profile} và {label}

Git backend hỗ trợ ba placeholder chính trong search path:

| Placeholder | Giá trị được thay thế | Ví dụ request |
| --- | --- | --- |
| `{application}` | Tên application mà client yêu cầu | `orders-service` |
| `{profile}` | Profile mà client yêu cầu | `prod` |
| `{label}` | Label Git được yêu cầu | `release-2026.11` |

Có thể khai báo:

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
            - "applications/{application}"
            - "profiles/{profile}"
            - "snapshots/{label}"
```

Các chuỗi chứa dấu ngoặc nhọn được đặt trong dấu nháy để YAML hiểu đó là scalar. Khi nhận request:

```text
/orders-service/prod/release-2026.11
```

Các search path có placeholder được mở rộng thành:

```text
shared
applications/orders-service
profiles/prod
snapshots/release-2026.11
```

Server tìm file cấu hình trong các vị trí này trên revision Git đã chọn. Ví dụ, `{application}` giúp mỗi ứng dụng có một thư mục riêng; `{profile}` giúp gom file theo môi trường; `{label}` có thể dùng khi repository có cấu trúc thư mục nội bộ gắn với nhãn phát hành.

Lưu ý quan trọng: `{label}` trong search path là tên label được thay vào đường dẫn thư mục bên trong revision đã checkout. Label vẫn quyết định branch, tag hoặc commit mà Git backend đọc. Nếu chọn label `release-2026.11`, server trước hết đọc revision Git đó, sau đó search path `snapshots/{label}` trỏ tới thư mục `snapshots/release-2026.11` bên trong chính revision đó. Đây không phải một lần checkout Git thứ hai.

## 4. Kết hợp search-paths với tên file cấu hình

Placeholder xác định thư mục cần tìm; quy tắc đặt tên file vẫn dựa trên application và profile. Trong ví dụ trên, request có application `orders-service`, profile `prod` và label `release-2026.11`. Một số file server có thể tìm thấy là:

```text
shared/application.yml
shared/application-prod.yml
applications/orders-service/orders-service.yml
applications/orders-service/orders-service-prod.yml
profiles/prod/application-prod.yml
profiles/prod/orders-service-prod.yml
snapshots/release-2026.11/application.yml
```

Mỗi thư mục có thể chứa file dùng chung hoặc file riêng theo application/profile. Không bắt buộc mọi thư mục phải có đủ mọi loại file. Nếu một file không tồn tại ở một search path, server tiếp tục xử lý các nguồn còn lại.

Ví dụ nội dung:

```yaml
# shared/application.yml
platform:
  region: ap-southeast-1
  connect-timeout: 2s
```

```yaml
# applications/orders-service/orders-service.yml
orders:
  retry:
    max-attempts: 2
```

```yaml
# profiles/prod/orders-service-prod.yml
orders:
  retry:
    max-attempts: 4
  http:
    read-timeout: 10s
```

```yaml
# snapshots/release-2026.11/application.yml
platform:
  configuration-release: "2026.11"
```

Với request production của `orders-service`, các file phù hợp có thể đóng góp các key khác nhau vào Environment. Giá trị `orders.retry.max-attempts` được khai báo ở nhiều nơi nên cần kiểm tra thứ tự property source trong response để xác nhận giá trị nào có hiệu lực.

Không nên giả định thứ tự thư mục trong Git hoặc thứ tự alphabet của file chính là thứ tự ưu tiên. Hãy kiểm tra danh sách `propertySources` mà Config Server trả về. Nếu một key được khai báo lặp lại, response JSON là căn cứ để xem nguồn nào được đặt trước và nguồn nào bị ghi đè.

## 5. Dùng wildcard trong search-paths

Ngoài placeholder, search path có thể dùng wildcard để khớp nhiều thư mục. Ví dụ:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          search-paths:
            - "shared"
            - "applications/*"
            - "teams/*/config"
```

Một số tình huống có thể dùng wildcard:

- `applications/*`: tìm trong các thư mục con trực tiếp của `applications`.
- `teams/*/config`: tìm trong thư mục `config` của từng nhóm.
- `*/{application}`: tìm thư mục ứng dụng dưới các vùng phân loại ở cấp đầu tiên.

Khi dùng wildcard cùng placeholder, hãy kiểm tra pattern thực tế có khớp với cấu trúc Git hay không. Wildcard giúp giảm cấu hình lặp lại nhưng có thể mở rộng phạm vi đọc rộng hơn dự kiến. Nếu hai thư mục cùng chứa key giống nhau, nhiều property source có thể cùng xuất hiện và tạo ra kết quả khó đoán nếu không review thứ tự.

Với repository có hàng trăm ứng dụng, pattern rộng có thể khiến server phải tìm kiếm nhiều vị trí hơn. Hãy cân bằng giữa tính linh hoạt và khả năng truy vết; ưu tiên cấu trúc thư mục có quy ước rõ ràng, chỉ dùng wildcard khi số lượng thư mục thực sự cần mở rộng động.

## 6. Phân biệt placeholder search path với placeholder trong giá trị

Hai cú pháp có vẻ gần giống nhau nhưng được xử lý ở các giai đoạn khác nhau.

**Placeholder trong search path** dùng dấu ngoặc nhọn đơn:

```yaml
search-paths:
  - "applications/{application}"
  - "profiles/{profile}"
```

Git backend thay các placeholder này bằng thông tin của request để xác định thư mục cần tìm.

**Placeholder trong giá trị cấu hình** thường dùng cú pháp `${...}`:

```yaml
orders:
  service-name: ${spring.application.name}
  region: ${PLATFORM_REGION:ap-southeast-1}
```

Đây là placeholder của Spring Property Resolver. Nó được phân giải khi ứng dụng sử dụng Environment, theo các nguồn thuộc tính có sẵn và cú pháp mặc định nếu có. Nó không điều khiển thư mục Git mà Config Server tìm kiếm.

Không viết `${application}` thay cho `{application}` trong `search-paths`; đó là hai cơ chế khác nhau. Ngược lại, không dùng `{profile}` trong giá trị cấu hình nếu mục tiêu là tham chiếu property của Spring.

## 7. Truy vấn và kiểm tra kết quả

Sau khi cấu hình server, gọi endpoint Environment với đúng application, profile và label:

```bash
curl http://localhost:8888/orders-service/prod/release-2026.11
```

Response JSON có danh sách property source. Một ví dụ rút gọn:

```json
{
  "name": "orders-service",
  "profiles": ["prod"],
  "label": "release-2026.11",
  "version": "a1b2c3d4",
  "propertySources": [
    {
      "name": "profiles/prod/orders-service-prod.yml",
      "source": {
        "orders.retry.max-attempts": 4,
        "orders.http.read-timeout": "10s"
      }
    },
    {
      "name": "applications/orders-service/orders-service.yml",
      "source": {
        "orders.retry.max-attempts": 2
      }
    },
    {
      "name": "shared/application.yml",
      "source": {
        "platform.region": "ap-southeast-1",
        "platform.connect-timeout": "2s"
      }
    }
  ]
}
```

Đây là response minh họa để giải thích cách quan sát nguồn; thứ tự và tên source thực tế phụ thuộc kết quả xử lý của server. Khi kiểm tra, chú ý:

1. `name` có đúng application mà client yêu cầu không.
2. `profiles` có chứa profile dự kiến không.
3. `label` và `version` có trỏ đến revision cần triển khai không.
4. Các `propertySources[].name` có cho thấy đúng các thư mục dự kiến được tìm kiếm không.
5. Một key xuất hiện ở nhiều source thì source nào có độ ưu tiên cao hơn theo thứ tự response.

Có thể yêu cầu YAML hoặc properties để xem cấu hình tổng hợp:

```bash
curl http://localhost:8888/orders-service-prod.yml
curl http://localhost:8888/orders-service-prod.properties
```

Endpoint Environment JSON hữu ích hơn khi chẩn đoán vì nó cho biết metadata và từng property source. YAML/properties tiện đọc hoặc chuyển tiếp nhưng thường không giữ đầy đủ thông tin nguồn gốc như response JSON.

Nếu server không trả file từ một thư mục dự kiến, kiểm tra search path đã được bind đúng, placeholder được thay bằng giá trị mong đợi, file nằm trong revision đang yêu cầu và file có tên phù hợp với application/profile.

## 8. Tác động của nhiều profile và label

Khi client gửi nhiều profile, ví dụ `prod,observability`, Config Server có thể cần tìm các file theo từng profile. Search path có `{profile}` vì thế cần được kiểm tra với chính request nhiều profile đó. Đừng giả định một chuỗi profile luôn tương ứng với một thư mục duy nhất như `profiles/prod,observability`. Hãy xem endpoint Environment JSON để xác nhận server đã mở rộng các profile và tạo property source như thế nào trong phiên bản đang sử dụng.

Tương tự, label có thể là branch, tag hoặc commit. Nếu label là branch có dấu gạch chéo, cách biểu diễn label trong URL cần tuân theo quy tắc của Config Server. Khi placeholder `{label}` được dùng trong thư mục, tên label được đưa vào đường dẫn sau khi server xử lý request. Với branch phức tạp hoặc label chứa ký tự đặc biệt, nên thử endpoint trước và dùng tên tag đơn giản nếu quy ước repository cho phép.

Label quyết định Git revision, còn placeholder `{label}` chỉ định một thư mục bên trong revision đó. Đừng dùng search path để thay thế quy trình phát hành Git hoặc để giả lập branch. Để rollback, chọn lại tag hoặc commit đã được phê duyệt, sau đó xác nhận response Environment có revision mong muốn.

## 9. Tổ chức repository cho nhiều ứng dụng

Một cấu trúc dễ quản lý thường chia theo trách nhiệm và chỉ lặp lại những gì thực sự khác nhau:

```text
config-repo/
├── shared/
│   ├── application.yml
│   └── application-prod.yml
├── applications/
│   ├── orders-service/
│   │   ├── orders-service.yml
│   │   └── orders-service-prod.yml
│   ├── payment-service/
│   │   ├── payment-service.yml
│   │   └── payment-service-prod.yml
│   └── inventory-service/
│       ├── inventory-service.yml
│       └── inventory-service-prod.yml
├── profiles/
│   ├── dev/
│   │   └── application-dev.yml
│   ├── staging/
│   │   └── application-staging.yml
│   └── prod/
│       └── application-prod.yml
└── snapshots/
    ├── main/
    └── release-2026.11/
```

Có thể bắt đầu với các search path:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          search-paths:
            - "shared"
            - "applications/{application}"
            - "profiles/{profile}"
            - "snapshots/{label}"
```

Với cấu trúc này:

- `shared` chứa giá trị dùng chung cho mọi ứng dụng.
- `applications/{application}` cô lập cấu hình theo service.
- `profiles/{profile}` chứa phần điều chỉnh theo môi trường.
- `snapshots/{label}` chỉ nên dùng nếu repository thực sự cần thư mục nội bộ tương ứng với label.

Không bắt buộc phải dùng đủ cả bốn kiểu path. Nếu profile đã được biểu diễn hoàn toàn bằng hậu tố file, có thể bỏ `profiles/{profile}`. Nếu không có cấu trúc thư mục gắn với label, bỏ `snapshots/{label}`; Git label vẫn hoạt động bình thường để chọn revision. Tránh tạo thư mục rỗng chỉ để làm cho cấu hình trông tổng quát.

## 10. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Config Server không tìm thấy file theo application | Tên thư mục không khớp `spring.application.name` hoặc sai placeholder | So sánh request và thư mục đã mở rộng |
| Profile-specific config không xuất hiện | Profile không được truyền hoặc thư mục không khớp `{profile}` | Kiểm tra `profiles` trong Environment response |
| Label-specific directory không được đọc | Label request khác tên thư mục hoặc revision Git không chứa path | Kiểm tra `label`, `version` và nội dung Git revision |
| File ở thư mục con không được tìm thấy | Thiếu path trong `search-paths` hoặc pattern không khớp | Kiểm tra cấu hình Git backend và response propertySources |
| Giá trị bị ghi đè ngoài dự kiến | Nhiều search path cung cấp cùng key | Kiểm tra thứ tự property source và loại bỏ khai báo trùng |
| Config Server vẫn trả dữ liệu cũ | Đang dùng label/branch khác hoặc server chưa fetch revision mới | Kiểm tra Git ref, fetch policy và trường version |
| Placeholder không được thay thế | Sai cú pháp, đặt trong property khác hoặc YAML parse sai | Dùng `{application}`, `{profile}`, `{label}` đúng trong search path |
| Tìm thấy cấu hình của ứng dụng khác | Wildcard quá rộng hoặc thư mục dùng chung có key riêng không phù hợp | Thu hẹp pattern và phân tách quyền sở hữu file |

Quy trình chẩn đoán nên đi từ request đến repository:

1. Ghi nhận application, profile và label client thực sự gửi.
2. Xem cấu hình `spring.cloud.config.server.git.search-paths` mà server đã nạp.
3. Thay placeholder bằng giá trị request để liệt kê các đường dẫn kỳ vọng.
4. Xác nhận các đường dẫn tồn tại trong Git revision đã chọn.
5. Gọi endpoint Environment JSON và xem property source thực tế.
6. Kiểm tra key bị trùng và thứ tự ưu tiên trước khi chỉnh file.

Không nên sửa file hoặc thêm wildcard ngay khi thấy thiếu một thuộc tính. Trước tiên xác định Config Server có tìm đến đúng thư mục hay không; sau đó mới kiểm tra tên file, profile, label và precedence.

## 11. Bảo mật và quản trị search path

Search path xác định vùng repository có thể đóng góp cấu hình cho một request. Nếu wildcard quá rộng hoặc cấu trúc thư mục thiếu quy ước, ứng dụng có thể nhận nhầm key từ nhóm khác. Hãy giới hạn path theo application, profile và phạm vi sở hữu; review thay đổi search path như một thay đổi kiến trúc của Config Server.

Một số nguyên tắc vận hành:

- Không đặt secret dạng rõ trong repository; dùng secret manager hoặc cơ chế mã hóa có quản lý khóa.
- Giới hạn quyền đọc Git repository và bảo vệ thông tin xác thực backend.
- Bảo vệ endpoint Config Server bằng TLS, xác thực và phân quyền phù hợp.
- Không expose Actuator hoặc API cấu hình ra mạng công cộng nếu chưa có kiểm soát.
- Review wildcard để tránh đọc cấu hình của service không liên quan.
- Ghi nhận label hoặc commit đã triển khai để có thể tái hiện và rollback.
- Kiểm tra response JSON sau khi thay đổi search path trước khi rollout đến nhiều client.

Thay đổi `search-paths` có thể ảnh hưởng đồng thời nhiều ứng dụng. Nên thử với một application/profile/label đại diện, kiểm tra toàn bộ property source và giá trị cuối cùng, rồi mới triển khai cấu hình server mới cho các client.

## 12. Nguyên tắc sử dụng

- Dùng `search-paths` để tổ chức nơi Config Server tìm file trong Git working tree.
- Dùng `{application}` để tách cấu hình theo tên ứng dụng.
- Dùng `{profile}` để tìm thư mục gắn với môi trường hoặc profile.
- Dùng `{label}` khi repository có thư mục nội bộ gắn với label; nhớ rằng label vẫn chọn Git revision.
- Dùng wildcard có giới hạn và kiểm tra những thư mục thực sự được khớp.
- Phân biệt placeholder search path `{application}` với placeholder giá trị Spring `${...}`.
- Kiểm tra endpoint Environment JSON để xác nhận property source, revision và thứ tự ưu tiên.
- Chỉ giữ các search path cần thiết, tránh mở rộng phạm vi đọc không có chủ đích.

Khi repository được chia thành các vùng rõ ràng và search path phản ánh đúng cấu trúc đó, Config Server có thể tìm cấu hình cho nhiều ứng dụng mà vẫn giữ được khả năng truy vết. Application, profile và label cung cấp ngữ cảnh của request; các placeholder chuyển ngữ cảnh đó thành đường dẫn Git; property source trả về cho biết những file nào đã tham gia tạo nên Environment của client.

