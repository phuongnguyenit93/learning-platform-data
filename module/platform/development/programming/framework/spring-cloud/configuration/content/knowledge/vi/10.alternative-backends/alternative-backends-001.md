# Native backend với classpath và hệ thống tệp

Spring Cloud Config Server có thể đọc cấu hình từ Git, nhưng trong một số môi trường ta muốn lưu cấu hình ngay trong ứng dụng Config Server hoặc ở một thư mục trên máy chủ. **Native backend** đáp ứng nhu cầu đó bằng cách đọc tài liệu cấu hình từ classpath hoặc filesystem thông qua cơ chế resource của Spring.

Native backend phù hợp cho phát triển cục bộ, kiểm thử, triển khai nhỏ hoặc môi trường mà nền tảng đã quản lý file cấu hình bằng volume/secret mount. Để chọn đúng cách lưu trữ, cần phân biệt file nằm trong classpath của Config Server với file nằm trên hệ thống tệp của máy chủ, đồng thời hiểu cách `search-locations` kết hợp với application, profile và label.

## 1. Native backend hoạt động ở phía Config Server

Native backend là một implementation của `EnvironmentRepository`. Khi client yêu cầu cấu hình, Config Server tìm file trong các vị trí đã khai báo, chuyển nội dung thành `PropertySource` rồi trả về một `Environment`.

Luồng xử lý cơ bản:

1. Client yêu cầu cấu hình theo application, profile và label.
2. Config Server chọn Native `EnvironmentRepository`.
3. Repository tìm tài liệu YAML hoặc properties trong các vị trí classpath/filesystem.
4. Các tài liệu phù hợp được chuyển thành property source và sắp xếp theo quy tắc của Config Server.
5. Client nhận cấu hình từ xa và đưa các property source vào `Environment` của ứng dụng.

Điểm quan trọng: profile `native` là profile kích hoạt backend ở chính Config Server. Nó khác với profile `prod`, `dev` hoặc `test` mà client yêu cầu để chọn nội dung cấu hình. Một Config Server có thể chạy với profile `native`, trong khi client đồng thời yêu cầu cấu hình profile `prod`.

## 2. Kích hoạt Native backend

Để Config Server sử dụng Native backend, kích hoạt profile `native` và khai báo `search-locations`:

```yaml
server:
  port: 8888

spring:
  profiles:
    active: native
  cloud:
    config:
      server:
        native:
          search-locations:
            - file:./config-repo
```

Trong ví dụ này:

- `spring.profiles.active: native` chọn Native repository ở phía Config Server.
- `search-locations` liệt kê các vị trí server sẽ tìm file cấu hình.
- `file:./config-repo` là đường dẫn tương đối theo working directory của tiến trình Config Server.

Với production, đường dẫn tuyệt đối thường dễ kiểm soát hơn:

```yaml
spring:
  profiles:
    active: native
  cloud:
    config:
      server:
        native:
          search-locations:
            - file:/etc/config-server/config-repo
```

Nếu cấu hình Native không có `search-locations` tùy chỉnh, Spring Cloud Config sử dụng các vị trí tài nguyên mặc định của ứng dụng Spring Boot. Trong hệ thống thực tế, nên khai báo rõ vị trí để người vận hành biết chính xác Config Server đang đọc file ở đâu.

## 3. Đọc cấu hình từ classpath

Classpath là tập tài nguyên được đóng gói cùng ứng dụng Java, ví dụ trong `src/main/resources`. Khi Config Server chạy từ JAR, các file trong thư mục resources sẽ nằm bên trong artifact và có thể được đọc bằng URL `classpath:`.

Ví dụ cấu trúc dự án Config Server:

```text
config-server/
├── src/
│   └── main/
│       └── resources/
│           └── config-repo/
│               ├── application.yml
│               ├── application-prod.yml
│               ├── orders-service.yml
│               └── orders-service-prod.yml
└── build.gradle
```

Khai báo vị trí classpath:

```yaml
spring:
  profiles:
    active: native
  cloud:
    config:
      server:
        native:
          search-locations:
            - classpath:/config-repo/
```

`classpath:/config-repo/` trỏ đến thư mục `config-repo` trong classpath của Config Server. Nó không trỏ đến `src/main/resources` của client và cũng không tự động đọc tài nguyên từ mọi ứng dụng Spring Boot kết nối tới server.

### Khi nào nên dùng classpath?

Classpath phù hợp khi bộ cấu hình nhỏ, ít thay đổi và cần được đóng gói cùng phiên bản Config Server. Mỗi lần thay đổi file, đội ngũ cần tạo artifact mới và triển khai lại Config Server để đưa nội dung mới vào classpath.

Ưu điểm:

- Không cần mount thêm thư mục cấu hình từ máy chủ.
- Đường dẫn nằm trong artifact nên dễ tái lập giữa các lần triển khai cùng phiên bản.
- Phù hợp cho demo, bài thực hành và cấu hình mặc định ít thay đổi.

Giới hạn:

- Thay đổi cấu hình thường gắn với quy trình build và phát hành Config Server.
- Không có lịch sử commit cấu hình độc lập như Git backend.
- Bí mật được đóng gói trong JAR/image có thể bị lộ cho bất kỳ ai có quyền đọc artifact; không đóng gói secret dạng rõ vào classpath.

## 4. Đọc cấu hình từ filesystem

Filesystem backend đọc file từ thư mục trên máy chủ hoặc trong container. Cách này cho phép tách vòng đời cấu hình khỏi artifact Config Server.

Ví dụ cấu trúc thư mục:

```text
/etc/config-server/config-repo/
├── application.yml
├── application-prod.yml
├── orders-service.yml
├── orders-service-prod.yml
└── inventory-service.yml
```

Khai báo đường dẫn:

```yaml
spring:
  profiles:
    active: native
  cloud:
    config:
      server:
        native:
          search-locations:
            - file:/etc/config-server/config-repo
```

Trong trường hợp này, Config Server cần quyền đọc thư mục và file. Nếu chạy bằng Docker hoặc Kubernetes, thư mục phải được mount vào đúng container hoặc pod. Đường dẫn trên host không tự động xuất hiện bên trong container.

### Đường dẫn tương đối và tuyệt đối

Đường dẫn tương đối như `file:./config-repo` phụ thuộc working directory tại thời điểm tiến trình khởi chạy. Nếu systemd, Docker entrypoint hoặc nền tảng triển khai đổi working directory, Config Server có thể tìm sang vị trí khác.

Đường dẫn tuyệt đối như `file:/etc/config-server/config-repo` làm rõ vị trí cần mount và dễ kiểm tra quyền truy cập hơn. Với production, hãy ưu tiên đường dẫn được quy định rõ trong manifest triển khai.

### Cập nhật file khi server đang chạy

Filesystem có thể được cập nhật mà không cần đóng gói lại JAR, nhưng cần xác định cách Config Server đọc và cache tài nguyên trong phiên bản đang sử dụng. Sau khi thay file, hãy gọi lại Environment API để xác nhận server trả nội dung mới. Client đang chạy vẫn có thể giữ giá trị đã nạp trước đó; chúng cần quy trình refresh phù hợp hoặc khởi động lại tùy loại bean và cấu hình.

## 5. Tổ chức tên file theo application và profile

Native backend dùng các quy ước tên file quen thuộc của Spring Cloud Config. Ví dụ với application `orders-service` và profile `prod`:

```text
config-repo/
├── application.yml
├── application-prod.yml
├── orders-service.yml
└── orders-service-prod.yml
```

| Tên file | Phạm vi |
|---|---|
| `application.yml` | Cấu hình mặc định dùng chung. |
| `application-prod.yml` | Cấu hình dùng chung khi client yêu cầu profile `prod`. |
| `orders-service.yml` | Cấu hình mặc định riêng cho orders service. |
| `orders-service-prod.yml` | Cấu hình riêng cho orders service ở profile `prod`. |

Ví dụ nội dung `application.yml`:

```yaml
app:
  region: ap-southeast-1
  connect-timeout: 2s
  read-timeout: 5s
```

Ví dụ nội dung `orders-service-prod.yml`:

```yaml
server:
  port: 8081

app:
  payment:
    endpoint: https://payments.internal.example.com
```

Client yêu cầu cấu hình bằng tên ứng dụng và profile:

```yaml
spring:
  application:
    name: orders-service
  config:
    import: "configserver:http://localhost:8888"
```

Profile có thể được kích hoạt trong môi trường triển khai:

```bash
SPRING_PROFILES_ACTIVE=prod
```

Config Server đang chạy profile `native`, nhưng vẫn tìm file `orders-service-prod.yml` vì client yêu cầu profile `prod`. Hai profile phục vụ hai vai trò khác nhau.

## 6. Dùng placeholder trong search-locations

Native backend hỗ trợ placeholder trong vị trí tìm kiếm, giúp chia cấu hình theo application, profile hoặc label. Ví dụ:

```yaml
spring:
  profiles:
    active: native
  cloud:
    config:
      server:
        native:
          search-locations:
            - file:/etc/config-repo/{application}
            - classpath:/shared-config
```

Với yêu cầu application `orders-service`, vị trí đầu tiên được phân giải thành thư mục `/etc/config-repo/orders-service`. Vị trí `classpath:/shared-config` có thể chứa các giá trị dùng chung.

Các placeholder thường dùng:

- `{application}`: tên application mà client yêu cầu.
- `{profile}`: profile mà client yêu cầu.
- `{label}`: label mà client yêu cầu.

Có thể dùng chúng để tách thư mục theo từng ứng dụng hoặc phiên bản:

```yaml
spring:
  cloud:
    config:
      server:
        native:
          search-locations:
            - file:/etc/config-repo/{application}/{profile}
```

Hãy kiểm tra đường dẫn sau khi placeholder được thay thế và bảo đảm thư mục đó tồn tại. Khi kết hợp nhiều vị trí classpath/filesystem, không nên tự giả định nguồn nào thắng nếu cùng khai báo một khóa; kiểm tra `propertySources` trong Environment API để xác nhận thứ tự thực tế.

Label trong Native backend không hoạt động như branch hoặc commit Git. Nó không tự tạo version history. Nếu `{label}` được dùng trong `search-locations`, label chỉ tham gia tạo đường dẫn tài nguyên theo cấu hình đó. Muốn truy vết phiên bản file, cần quản lý version bên ngoài, chẳng hạn qua Git, artifact versioning hoặc quy trình phát hành riêng.

## 7. Kết hợp nhiều vị trí classpath và filesystem

Native backend cho phép khai báo nhiều `search-locations`. Một mô hình thường gặp là lưu giá trị chung trong classpath và cấu hình môi trường trên filesystem:

```yaml
spring:
  profiles:
    active: native
  cloud:
    config:
      server:
        native:
          search-locations:
            - classpath:/shared-config/
            - file:/etc/config-server/environment-config/
```

Classpath có thể chứa giá trị dùng chung, còn filesystem chứa phần điều chỉnh theo môi trường triển khai. Cách kết hợp này giúp một artifact Config Server dùng chung cho nhiều môi trường mà vẫn nhận được cấu hình được mount riêng.

Tuy nhiên, khi cùng một khóa xuất hiện trong nhiều vị trí, kết quả phụ thuộc thứ tự các property source mà repository trả về và cách Spring xử lý chúng. Hãy giữ các nguồn có trách nhiệm rõ ràng, tránh khai báo trùng khóa không cần thiết và xác minh kết quả bằng Environment API.

Nếu cần quy tắc ưu tiên phức tạp giữa nhiều backend độc lập, hãy cân nhắc Composite repository hoặc một backend có khả năng quản lý phiên bản rõ ràng. Native backend phù hợp nhất khi các vị trí tài nguyên có cấu trúc đơn giản và được kiểm soát.

## 8. Triển khai Native backend trong Docker và Kubernetes

Với Docker, có thể mount thư mục cấu hình từ host vào container:

```yaml
services:
  config-server:
    image: example/config-server:1.0.0
    ports:
      - "8888:8888"
    volumes:
      - ./config-repo:/etc/config-server/config-repo:ro
    environment:
      SPRING_PROFILES_ACTIVE: native
```

Config Server dùng `file:/etc/config-server/config-repo` làm search location. Mount `:ro` giúp tiến trình chỉ đọc nội dung cấu hình, giảm nguy cơ ứng dụng vô tình sửa file.

Trong Kubernetes, có thể mount ConfigMap hoặc volume phù hợp vào pod:

```yaml
volumeMounts:
  - name: config-repo
    mountPath: /etc/config-server/config-repo
    readOnly: true
volumes:
  - name: config-repo
    configMap:
      name: config-server-repository
```

Ví dụ này minh họa cách mount một ConfigMap. Với dữ liệu lớn, yêu cầu versioning hoặc cập nhật có kiểm soát, có thể dùng volume và cơ chế phát hành file riêng. Không đưa secret vào ConfigMap; sử dụng Kubernetes Secret hoặc secret manager phù hợp.

Khi chạy trong container, kiểm tra:

- Mount path có trùng với `search-locations` không.
- File có xuất hiện trong container/pod không.
- User chạy Java có quyền đọc file không.
- Volume có cập nhật theo cách nền tảng hỗ trợ không.
- Config Server có đọc được nội dung mới ở request tiếp theo không.

## 9. So sánh classpath và filesystem

| Tiêu chí | Classpath | Filesystem |
|---|---|---|
| Vị trí | Đóng gói trong JAR hoặc classpath của Config Server. | Thư mục trên máy chủ hoặc volume mount. |
| Cập nhật | Thường cần build artifact và triển khai lại. | Có thể cập nhật file/volume độc lập với artifact. |
| Tính tái lập | Gắn với phiên bản artifact. | Phụ thuộc snapshot/version của thư mục hoặc volume. |
| Phù hợp | Demo, kiểm thử, cấu hình ít thay đổi. | Cấu hình môi trường, triển khai container và file được nền tảng quản lý. |
| Quản lý lịch sử | Không có lịch sử Git tự thân. | Không có lịch sử Git tự thân; cần cơ chế versioning riêng. |
| Rủi ro chính | Bí mật hoặc cấu hình bị đóng gói trong artifact. | Sai đường dẫn, quyền file, mount sai hoặc nội dung bị thay đổi ngoài quy trình. |

Chọn classpath khi cấu hình là một phần của artifact và thay đổi cùng nhịp phát hành. Chọn filesystem khi cần tách file cấu hình khỏi vòng đời artifact và nền tảng có thể quản lý mount, quyền truy cập và cập nhật file đáng tin cậy.

## 10. Bảo mật và quản trị thay đổi

Native backend không có xác thực Git hay lịch sử commit tự động. Bảo mật phụ thuộc vào quyền truy cập filesystem, quyền triển khai artifact và cách nền tảng phân phối file.

Một số nguyên tắc vận hành:

- Chỉ cấp quyền đọc thư mục cấu hình cho service account chạy Config Server.
- Mount thư mục read-only nếu Config Server chỉ cần đọc.
- Không đóng gói mật khẩu, token, private key hoặc bí mật dạng rõ trong classpath.
- Lấy bí mật từ secret manager hoặc secret mount được bảo vệ.
- Giới hạn `search-locations` vào các thư mục chuyên dụng, không trỏ đến thư mục rộng như `/` hoặc toàn bộ home directory.
- Review và version hóa thay đổi file bằng Git hoặc hệ thống quản lý artifact bên ngoài.
- Ghi nhận phiên bản cấu hình được triển khai để có thể khôi phục khi cần.
- Sau khi cập nhật, xác minh phản hồi Config Server và thực hiện refresh cho client đang chạy.

Nếu nhiều người hoặc nhiều tiến trình cùng có quyền ghi vào thư mục cấu hình, cần có quy trình kiểm soát thay đổi để tránh cập nhật đồng thời hoặc ghi đè ngoài dự kiến. Đối với hệ thống yêu cầu audit, rollback và review mạnh, Git backend thường cung cấp nền tảng quản trị thuận tiện hơn.

## 11. Kiểm tra và xử lý lỗi Native backend

Sau khi Config Server khởi động, gọi Environment API theo application, profile và label:

```bash
curl -i http://localhost:8888/orders-service/prod/main
```

Kiểm tra các trường `name`, `profiles`, `label`, `version` và `propertySources`. Với Native backend, metadata phiên bản không nhất thiết tương ứng với Git commit; tập trung xác minh đúng file và đúng giá trị được trả về.

Các tình huống thường gặp:

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Không tìm thấy file | Sai `search-locations`, sai tên application/profile hoặc file chưa được đóng gói/mount. |
| Đọc được ở máy phát triển nhưng lỗi trong container | Đường dẫn tương đối khác, mount path sai hoặc quyền đọc của user runtime không đủ. |
| Chỉ nhận cấu hình dùng chung | Tên `spring.application.name` không khớp file riêng hoặc placeholder `{application}` được phân giải khác dự kiến. |
| Không nhận file profile | Client không gửi profile mong muốn hoặc hậu tố file không khớp profile. |
| Giá trị bị ghi đè | Nhiều search location cùng khai báo khóa; kiểm tra thứ tự `propertySources`. |
| File vừa cập nhật nhưng client chưa đổi | Config Server có thể đã đọc nội dung mới, nhưng client chưa refresh hoặc bean chưa hỗ trợ refresh. |
| Lỗi đọc tài nguyên | Quyền filesystem, encoding, YAML/properties syntax hoặc mount volume. |

Quy trình chẩn đoán:

1. Xác nhận Config Server đang chạy với profile `native`.
2. Xác nhận `search-locations` đúng và có thể phân giải thành tài nguyên tồn tại.
3. Kiểm tra file từ bên trong runtime của Config Server, không chỉ từ host.
4. Kiểm tra quyền đọc và nội dung YAML/properties.
5. Gọi đúng Environment API và xem danh sách property source.
6. Nếu server trả đúng giá trị, kiểm tra Environment và refresh ở phía client.

## 12. Tổng kết

- Native backend là `EnvironmentRepository` đọc file cấu hình từ classpath hoặc filesystem.
- Profile `native` kích hoạt backend ở Config Server; profile `prod`, `dev` hoặc `test` vẫn do client yêu cầu để chọn nội dung.
- `classpath:` đọc tài nguyên được đóng gói cùng Config Server; `file:` đọc tài nguyên trên filesystem hoặc volume mount.
- `spring.cloud.config.server.native.search-locations` xác định vị trí tìm file và có thể dùng placeholder application, profile, label.
- Native backend không cung cấp lịch sử commit như Git; label chỉ chọn tài nguyên theo cách search location được cấu hình, không tự đại diện cho branch hoặc commit.
- Với container, kiểm tra mount path, quyền đọc và working directory; ưu tiên đường dẫn tuyệt đối cho production.
- Bảo vệ filesystem, không đóng gói bí mật dạng rõ, quản lý phiên bản thay đổi bên ngoài và xác minh bằng Environment API.
