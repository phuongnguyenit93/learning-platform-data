# Thiết lập search-locations và đường dẫn file trên Windows hoặc Linux

Spring Cloud Config Server thường đọc cấu hình từ Git, nhưng cũng hỗ trợ native backend để đọc file trực tiếp từ filesystem hoặc classpath. Native backend hữu ích khi phát triển local, kiểm thử, chạy trong môi trường bị giới hạn kết nối Git hoặc khi nền tảng triển khai đã mount một thư mục cấu hình vào máy chủ. Để dùng backend này đúng cách, cần kích hoạt profile `native` và khai báo `spring.cloud.config.server.native.search-locations` trỏ đến những thư mục mà tiến trình Config Server có thể đọc.

Đường dẫn filesystem phải được viết theo cú pháp resource location mà Spring hiểu. Windows và Linux có cách biểu diễn đường dẫn khác nhau ở hệ điều hành, nhưng cấu hình Spring nên dùng URI `file:` với dấu gạch chéo xuôi. Điều này giúp tránh lỗi escape ký tự, sai ổ đĩa, sai working directory và nhầm lẫn giữa đường dẫn máy host với đường dẫn bên trong container.

## 1. Native backend hoạt động như thế nào?

Native backend là một loại Environment Repository của Spring Cloud Config Server. Khi profile `native` được kích hoạt ở chính Config Server, server đọc các file cấu hình từ những vị trí được khai báo thay vì lấy nội dung từ Git.

Ví dụ cấu hình cơ bản:

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
            - file:/opt/spring-config
```

Trong cấu hình này:

- `spring.profiles.active: native` kích hoạt native Environment Repository trên Config Server.
- `spring.cloud.config.server.native.search-locations` liệt kê các vị trí server cần tìm file.
- `file:/opt/spring-config` là một đường dẫn tuyệt đối đến thư mục trên filesystem của máy đang chạy Config Server.
- `server.port` chỉ định cổng HTTP của ứng dụng; nó không ảnh hưởng cách tìm file.

Profile `native` phải được kích hoạt ở ứng dụng Config Server. Không đặt profile này trong Config Client với mục đích yêu cầu client đọc file local của server. Client vẫn gọi Config Server qua HTTP bằng `spring.config.import` hoặc cơ chế bootstrap mà dự án đang dùng.

Nếu Config Server đang chạy với các profile khác, có thể kích hoạt đồng thời profile môi trường và `native`, ví dụ `native,prod`. Cần xác nhận không có profile cấu hình khác vô tình bật thêm một backend hoặc ghi đè các thuộc tính native.

## 2. Tổ chức thư mục cấu hình

Giả sử server đọc một thư mục chứa cấu hình chung, cấu hình theo ứng dụng và cấu hình theo profile:

```text
spring-config/
├── application.yml
├── order-service.yml
├── order-service-dev.yml
├── order-service-prod.yml
├── inventory-service.yml
└── inventory-service-prod.yml
```

Các tên file tuân theo quy ước của Config Server:

- `application.yml` chứa thuộc tính dùng chung cho nhiều ứng dụng.
- `{application}.yml` chứa cấu hình riêng của ứng dụng, ví dụ `order-service.yml`.
- `{application}-{profile}.yml` chứa phần cấu hình riêng theo profile, ví dụ `order-service-prod.yml`.

Config Client khai báo tên ứng dụng và profile:

```yaml
spring:
  application:
    name: order-service
  profiles:
    active: prod
  config:
    import: "configserver:http://config-server:8888"
```

Client yêu cầu cấu hình cho `order-service` với profile `prod`; Config Server tìm các file phù hợp trong vị trí native đã cấu hình. `search-locations` chỉ xác định nơi tìm kiếm. Tên ứng dụng và profile vẫn quyết định tên file nào được chọn.

Không nên tạo các tên file tùy ý rồi kỳ vọng Config Server tự hiểu. Nếu nhóm chọn quy ước riêng, hãy cấu hình vị trí tìm kiếm và placeholder có chủ đích, sau đó kiểm tra response Environment cho từng application/profile.

## 3. Cú pháp đường dẫn trên Windows

Trên Windows, đường dẫn hệ điều hành thường có dạng `C:\spring-config`, nhưng dấu gạch chéo ngược có ý nghĩa escape trong nhiều định dạng cấu hình. Với Spring resource location, nên chuyển đường dẫn thành URI `file:` dùng dấu gạch chéo xuôi.

Ví dụ thư mục `C:\spring-config`:

```yaml
spring:
  profiles:
    active: native
  cloud:
    config:
      server:
        native:
          search-locations:
            - "file:///C:/spring-config"
```

Một ổ đĩa khác, ví dụ `D:\shared\config-repository`, được biểu diễn:

```yaml
spring:
  cloud:
    config:
      server:
        native:
          search-locations:
            - "file:///D:/shared/config-repository"
```

Hãy chú ý các điểm sau:

- Dùng `file:///C:/...` cho đường dẫn ổ đĩa Windows; có ba dấu `/` trước tên ổ đĩa.
- Dùng dấu `/` thay cho dấu gạch chéo ngược trong URI.
- Đặt URI trong dấu nháy để YAML đọc giá trị như một chuỗi rõ ràng.
- Đảm bảo ổ đĩa và thư mục tồn tại trong phiên đăng nhập mà dịch vụ Config Server đang chạy.
- Cấp quyền đọc cho tài khoản chạy dịch vụ; quyền của người dùng đang mở IDE không nhất thiết là quyền của Windows Service hoặc tiến trình chạy nền.

Nếu đường dẫn có dấu cách, URI phải mã hóa dấu cách thành `%20`. Ví dụ:

```yaml
search-locations:
  - "file:///C:/Spring%20Cloud/config"
```

Trong môi trường Windows Server, tránh phụ thuộc vào ổ đĩa mạng được map trong phiên desktop của một người dùng. Dịch vụ chạy dưới tài khoản khác có thể không nhìn thấy mapping đó. Nếu cần đọc thư mục mạng, hãy cấu hình đường dẫn và danh tính truy cập phù hợp với tài khoản dịch vụ, hoặc mount tài nguyên mạng theo cách nền tảng vận hành hỗ trợ.

## 4. Cú pháp đường dẫn trên Linux

Trên Linux, các đường dẫn tuyệt đối thường bắt đầu từ `/`, ví dụ `/etc/spring-config` hoặc `/opt/config-repository`. Có thể biểu diễn bằng `file:` URI như sau:

```yaml
spring:
  profiles:
    active: native
  cloud:
    config:
      server:
        native:
          search-locations:
            - "file:/etc/spring-config"
```

Hoặc viết dạng URI có ba dấu gạch chéo:

```yaml
search-locations:
  - "file:///etc/spring-config"
```

Cả hai cách đều chỉ đến một đường dẫn file tuyệt đối trên Linux. Chọn một cách viết thống nhất trong dự án để giảm nhầm lẫn khi đọc và review cấu hình.

Nếu cấu hình được đặt dưới `/opt/config-repository`, ví dụ:

```yaml
spring:
  cloud:
    config:
      server:
        native:
          search-locations:
            - "file:///opt/config-repository"
```

Hãy xác nhận user chạy Config Server có quyền `x` trên từng thư mục cha để đi xuyên qua cây thư mục và quyền `r` trên các file cấu hình. Chỉ có quyền đọc file nhưng thiếu quyền truy cập thư mục cha vẫn có thể khiến server không mở được file.

Đường dẫn tương đối như `file:./config` phụ thuộc working directory của tiến trình. Khi chạy từ IDE, systemd, Docker hoặc Kubernetes, working directory có thể khác nhau. Với môi trường cần vận hành ổn định, nên dùng đường dẫn tuyệt đối hoặc một biến môi trường được quản lý rõ ràng.

## 5. Khai báo nhiều search locations

`search-locations` nhận một hoặc nhiều resource location. Có thể đặt thư mục dùng chung và thư mục riêng theo ứng dụng trong danh sách:

```yaml
spring:
  profiles:
    active: native
  cloud:
    config:
      server:
        native:
          search-locations:
            - "file:///etc/spring-config/common"
            - "file:///etc/spring-config/services"
```

Ví dụ cấu trúc:

```text
/etc/spring-config/
├── common/
│   └── application.yml
└── services/
    ├── order-service.yml
    ├── order-service-prod.yml
    └── inventory-service.yml
```

Nếu muốn chia thư mục theo tên ứng dụng, native backend hỗ trợ placeholder trong search location, chẳng hạn `{application}`, `{profile}` và `{label}`. Ví dụ:

```yaml
spring:
  cloud:
    config:
      server:
        native:
          search-locations:
            - "file:///etc/spring-config/{application}"
```

Với cách này, request cho `order-service` sẽ tìm trong thư mục tương ứng `/etc/spring-config/order-service`. Có thể tổ chức thư mục theo profile hoặc label nếu quy ước của hệ thống yêu cầu, nhưng cần kiểm tra kỹ đường dẫn thực tế mà mỗi request tạo ra.

Khi có nhiều location, không nên giả định thứ tự khai báo tự động mang ý nghĩa ưu tiên giống nhau trong mọi cách tổ chức. Nếu cùng một khóa xuất hiện ở nhiều vị trí, hãy gọi endpoint Environment và kiểm tra thứ tự `propertySources` cũng như giá trị cuối cùng mà Config Client nhận được. Tránh đặt cùng một khóa ở nhiều thư mục nếu không có mục đích ghi đè được tài liệu hóa.

## 6. Phân biệt `file:` và `classpath:`

Native backend có thể đọc tài nguyên từ filesystem hoặc classpath:

```yaml
spring:
  cloud:
    config:
      server:
        native:
          search-locations:
            - "classpath:/config"
            - "file:/etc/spring-config"
```

Hai loại location có vòng đời khác nhau:

| Loại location | Nguồn dữ liệu | Cách cập nhật |
|---|---|---|
| `classpath:` | Tài nguyên được đóng gói trong JAR hoặc classpath của ứng dụng Config Server | Thường cần build/redeploy hoặc cập nhật classpath |
| `file:` | File bên ngoài tiến trình, nằm trên filesystem hoặc thư mục được mount | Có thể thay file mà không build lại server; cần kiểm tra cache và thời điểm server đọc lại |

`classpath:` thuận tiện cho cấu hình mẫu hoặc dữ liệu đi kèm artifact. `file:` phù hợp khi cần tách file cấu hình khỏi gói triển khai. Với production, thư mục ngoài phải được quản lý như một thành phần triển khai có phiên bản, quyền truy cập, backup và quy trình rollback.

Không đặt bí mật dạng rõ trong classpath hoặc file native chỉ vì các file đó nằm ngoài Git. Cơ chế bảo vệ bí mật vẫn phải được thiết kế riêng, ví dụ cấp secret từ Vault/KMS hoặc secret manager của nền tảng.

## 7. Đưa đường dẫn vào biến môi trường

Để cùng một gói Config Server chạy trên nhiều hệ điều hành hoặc môi trường, có thể đưa vị trí cấu hình ra biến môi trường:

```yaml
spring:
  profiles:
    active: native
  cloud:
    config:
      server:
        native:
          search-locations:
            - "${CONFIG_REPOSITORY_LOCATION:file:/opt/spring-config}"
```

Linux có thể cấp biến trước khi khởi chạy:

```bash
export CONFIG_REPOSITORY_LOCATION=file:///etc/spring-config
java -jar config-server.jar
```

PowerShell trên Windows có thể đặt biến cho tiến trình hiện tại:

```powershell
$env:CONFIG_REPOSITORY_LOCATION = 'file:///C:/spring-config'
java -jar config-server.jar
```

Nếu dùng Windows Service, Docker hoặc Kubernetes, hãy khai báo biến trong cấu hình dịch vụ/deployment tương ứng. Biến môi trường cần chứa đúng `file:` URI mà Spring Resource Loader có thể đọc. Không trộn đường dẫn Windows với biến cấu hình của container Linux: tiến trình trong container chỉ nhìn thấy filesystem của container và các volume được mount vào đó.

Có thể dùng biến môi trường chuẩn của Spring Boot để đặt trực tiếp thuộc tính native. Tên biến tương ứng với `spring.cloud.config.server.native.search-locations` là:

```text
SPRING_CLOUD_CONFIG_SERVER_NATIVE_SEARCHLOCATIONS
```

Nếu cung cấp nhiều location bằng một biến môi trường dạng chuỗi, cần dùng cú pháp phân tách mà Spring Boot hỗ trợ và kiểm tra kết quả bind trong môi trường thực tế. Với cấu hình nhiều thư mục phức tạp, khai báo danh sách trong YAML thường dễ review hơn.

## 8. Đường dẫn khi Config Server chạy trong Docker hoặc Kubernetes

Một lỗi phổ biến là cấu hình đường dẫn trên máy host rồi mong Config Server trong container tự truy cập được. Container có filesystem riêng. Nếu thư mục trên host không được mount, `file:` URI bên trong container không thể đọc file đó.

Ví dụ Docker bind mount thư mục cấu hình host vào container:

```bash
docker run --rm \
  -p 8888:8888 \
  -v /srv/spring-config:/etc/spring-config:ro \
  -e SPRING_PROFILES_ACTIVE=native \
  -e SPRING_CLOUD_CONFIG_SERVER_NATIVE_SEARCHLOCATIONS=file:///etc/spring-config \
  config-server:1.0.0
```

Trong ví dụ này, `/srv/spring-config` là đường dẫn trên host Linux, còn `/etc/spring-config` là đường dẫn nhìn thấy bên trong container. Config Server chỉ sử dụng đường dẫn phía trong container. Mount `:ro` giúp tiến trình chỉ đọc cấu hình và tránh sửa dữ liệu nguồn ngoài ý muốn.

Với Kubernetes, có thể mount ConfigMap hoặc volume vào Pod:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: config-server
spec:
  replicas: 1
  selector:
    matchLabels:
      app: config-server
  template:
    metadata:
      labels:
        app: config-server
    spec:
      containers:
        - name: config-server
          image: config-server:1.0.0
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: native
            - name: SPRING_CLOUD_CONFIG_SERVER_NATIVE_SEARCHLOCATIONS
              value: file:///etc/spring-config
          volumeMounts:
            - name: config-files
              mountPath: /etc/spring-config
              readOnly: true
      volumes:
        - name: config-files
          configMap:
            name: config-server-files
```

Đây là ví dụ minh họa mount ConfigMap. ConfigMap phù hợp với dữ liệu cấu hình không bí mật; không dùng nó để lưu password hoặc private key. Nếu cấu hình được cập nhật, cần xác định cách volume cập nhật và khi nào Config Server đọc lại file. Một số ứng dụng hoặc cache có thể vẫn giữ giá trị cũ cho đến khi được refresh hoặc khởi động lại.

Khi chạy nhiều replica Config Server, mọi replica cần nhìn thấy cùng một phiên bản dữ liệu hoặc một quy trình phát hành đồng bộ. Nếu mỗi Pod mount nội dung khác nhau, cùng một request từ Config Client có thể nhận cấu hình khác nhau tùy replica được load balancer chọn.

## 9. Kiểm tra search location và quyền đọc

Trước khi kết nối Config Client, hãy kiểm tra từng lớp:

1. Xác nhận profile `native` đang active trên Config Server.
2. Kiểm tra giá trị `search-locations` sau khi bind cấu hình.
3. Xác nhận đường dẫn tồn tại trong filesystem mà tiến trình server nhìn thấy.
4. Kiểm tra tài khoản chạy server có quyền duyệt thư mục và đọc file.
5. Xác nhận file có tên đúng với application/profile cần truy vấn.
6. Gọi endpoint Environment và kiểm tra danh sách `propertySources`.
7. Gọi lại từ mạng của Config Client để xác nhận hostname, cổng và API path.

Ví dụ kiểm tra endpoint Environment:

```bash
curl -i http://localhost:8888/order-service/prod/main
```

Nếu có cấu hình, response thường có một hoặc nhiều property source. Nếu response rỗng, kiểm tra `search-locations`, cấu trúc file và tên application/profile. Tùy `spring.cloud.config.server.accept-empty`, Environment rỗng có thể được trả về như một response thành công hoặc bị từ chối. Vì vậy, cần đọc cả status HTTP lẫn body.

### Kiểm tra bằng lệnh hệ điều hành

Trên Linux, có thể dùng:

```bash
ls -ld /etc/spring-config
find /etc/spring-config -maxdepth 2 -type f
```

Trên Windows PowerShell:

```powershell
Test-Path 'C:\spring-config'
Get-ChildItem -Path 'C:\spring-config' -Recurse -File
```

Các lệnh này cần được chạy trong cùng môi trường hoặc cùng danh tính mà Config Server sử dụng. Nếu server chạy trong container, hãy kiểm tra bên trong container thay vì chỉ kiểm tra host.

## 10. Các lỗi đường dẫn thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Config Server trả Environment rỗng | Sai `search-locations`, sai tên file, sai profile hoặc file không nằm trong location được tìm | Kiểm tra profile `native`, URI và cấu trúc file |
| Không đọc được đường dẫn Windows | Dùng backslash không đúng, thiếu dấu `/`, sai ký tự ổ đĩa hoặc tài khoản dịch vụ không có quyền | Dùng `file:///C:/...`, kiểm tra quyền của tài khoản chạy server |
| Không đọc được đường dẫn Linux | Đường dẫn tương đối, sai mount hoặc thiếu quyền traverse/read | Dùng đường dẫn tuyệt đối và kiểm tra quyền thư mục cha/file |
| Chạy được local nhưng lỗi trong Docker | Đường dẫn host chưa được bind mount vào container | Mount thư mục và trỏ `search-locations` đến đường dẫn container |
| Một số replica trả cấu hình khác nhau | Các replica mount hoặc cache nội dung khác phiên bản | Đồng bộ volume, quy trình phát hành và refresh |
| File mới chưa xuất hiện trong response | Server/cache chưa đọc lại hoặc file đặt ngoài search path | Kiểm tra location, cache và khởi động/refresh theo thiết kế |
| YAML không parse được | Cú pháp YAML sai hoặc kiểu dữ liệu không phù hợp | Kiểm tra cú pháp và log Config Server |

Đặc biệt, đừng nhầm `file:///C:/spring-config` trên Windows host với `/etc/spring-config` trong container Linux. Đường dẫn phải được đánh giá từ góc nhìn của tiến trình đang chạy Config Server.

## 11. Native backend trong môi trường production

Native backend không cung cấp sẵn lịch sử commit, pull request, branch protection và audit trail như Git. Nếu dùng native backend trong production, nhóm phải tự bảo đảm các khả năng tương đương bằng hệ thống quản lý file hoặc pipeline triển khai:

- Phiên bản hóa thư mục cấu hình hoặc artifact chứa cấu hình.
- Review và kiểm tra thay đổi trước khi copy/mount vào server.
- Lưu bản sao trước khi cập nhật và có phương án rollback.
- Đồng bộ nội dung giữa các Config Server replica.
- Giám sát dung lượng, quyền truy cập và tính sẵn sàng của filesystem/network volume.
- Không lưu bí mật dạng rõ; cấp secret qua hệ thống quản lý bí mật.
- Xác minh giá trị thực tế qua API trước và sau khi refresh client.

Nếu cần nhiều nhóm cùng thay đổi cấu hình, theo dõi lịch sử và rollback theo commit, Git backend thường thuận tiện hơn. Native backend phù hợp khi filesystem là nguồn cấu hình được quản lý có chủ đích, không phải một thư mục tạm trên máy cá nhân.

## 12. Nguyên tắc cần ghi nhớ

- Kích hoạt profile `native` trên Config Server để sử dụng filesystem/classpath backend.
- Dùng `spring.cloud.config.server.native.search-locations` để khai báo các resource location.
- Dùng `file:///C:/...` cho ổ đĩa Windows và `file:/...` hoặc `file:///...` cho đường dẫn tuyệt đối Linux.
- Ưu tiên dấu gạch chéo xuôi, URI có dấu nháy và đường dẫn tuyệt đối.
- Phân biệt `file:` với `classpath:` theo cách lưu trữ và vòng đời cập nhật.
- Đường dẫn trong container là đường dẫn bên trong container; phải mount thư mục host hoặc volume vào đúng vị trí.
- Kiểm tra quyền đọc của tài khoản chạy server, không chỉ quyền của người dùng đăng nhập.
- Xác minh application/profile/label và `propertySources` qua API Config Server.
- Nếu dùng production, tự thiết kế versioning, review, đồng bộ replica, backup và rollback cho nguồn file.

`search-locations` là cầu nối giữa native backend và filesystem mà Config Server có thể truy cập. Khi profile `native`, URI `file:`, cấu trúc file, quyền đọc và đường dẫn container được cấu hình nhất quán, Config Server có thể phân phối cấu hình từ Windows, Linux hoặc volume được mount mà không phụ thuộc vào đường dẫn trên máy phát triển.

## Tài liệu tham khảo

- [Spring Cloud Config Server — File System Backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/file-system-backend.html)
- [Spring Cloud Config Server — tài liệu chính thức](https://docs.spring.io/spring-cloud-config/reference/server.html)
