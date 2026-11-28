# Phân biệt native backend với kho Git có URI file

Spring Cloud Config Server có thể đọc cấu hình từ các file trực tiếp trên filesystem bằng **native backend**, hoặc đọc từ một repository Git bằng **Git backend**. Cả hai đều có thể xuất hiện URI bắt đầu bằng `file:`, nhưng chúng không phải cùng một cơ chế. Native backend dùng `file:` để chỉ vị trí chứa các file YAML hoặc properties; Git backend dùng `file:` làm địa chỉ của một repository Git mà server phải clone hoặc fetch.

Điểm phân biệt quan trọng nằm ở thuộc tính cấu hình và nội dung đích:

- `spring.cloud.config.server.native.search-locations` trỏ tới thư mục hoặc classpath chứa file cấu hình thông thường.
- `spring.cloud.config.server.git.uri` trỏ tới repository Git có metadata và lịch sử Git, kể cả khi repository đó nằm trên cùng máy với Config Server.

Hiểu rõ sự khác nhau này giúp tránh lỗi cấu hình backend, chọn đúng cách quản lý phiên bản và thiết kế quyền truy cập phù hợp.

## 1. Vì sao hai cách dễ bị nhầm?

Hai cấu hình sau đều dùng scheme `file`, nhưng đối tượng được trỏ tới khác nhau:

```yaml
# Native backend: file: trỏ tới thư mục chứa các file cấu hình
spring:
  profiles:
    active: native
  cloud:
    config:
      server:
        native:
          search-locations:
            - file:/srv/config-files
```

```yaml
# Git backend: file: trỏ tới một repository Git
spring:
  cloud:
    config:
      server:
        git:
          uri: file:///srv/git/config-repo.git
```

Trong ví dụ đầu, `/srv/config-files` chỉ cần chứa các file như `application.yml`, `order-service.yml` hoặc `order-service-production.yml`. Không cần khởi tạo Git repository.

Trong ví dụ thứ hai, `/srv/git/config-repo.git` phải là một repository Git hợp lệ. Chỉ đặt các file YAML vào một thư mục rồi dùng đường dẫn đó làm Git URI sẽ không biến thư mục thành repository. Git backend cần đọc được refs và object database để phân giải branch, tag hoặc commit.

Có thể nhớ quy tắc: **native tìm file; Git tìm phiên bản của repository**. Chuỗi `file:` chỉ mô tả cách truy cập filesystem; thuộc tính `native.search-locations` hay `git.uri` mới xác định cách Config Server diễn giải tài nguyên.

## 2. Native backend: đọc trực tiếp thư mục cấu hình

Native backend phù hợp khi cấu hình được cung cấp như các file trong filesystem hoặc classpath của Config Server. Để kích hoạt, Config Server cần chạy với profile `native`.

Ví dụ cấu hình:

```yaml
spring:
  profiles:
    active: native
  cloud:
    config:
      server:
        native:
          search-locations:
            - file:/srv/config-files
            - file:/srv/config-files/{application}
```

`search-locations` xác định những nơi Config Server tìm file. Các placeholder như `{application}`, `{profile}` và `{label}` có thể được dùng để tổ chức đường dẫn theo tên ứng dụng, profile hoặc label. Chỉ khai báo những đường dẫn cần thiết và kiểm tra kết quả thực tế bằng API, đặc biệt khi nhiều search location có file trùng tên.

Nếu không khai báo search location riêng, native backend có các vị trí classpath mặc định như `classpath:/` và `classpath:/config`. Với cấu hình triển khai bên ngoài ứng dụng, nên khai báo đường dẫn rõ ràng để tránh phụ thuộc vào nội dung đóng gói trong JAR hoặc working directory của tiến trình.

Một cấu trúc thư mục đơn giản có thể là:

```text
/srv/config-files/
├── application.yml
├── application-production.yml
├── order-service.yml
├── order-service-production.yml
├── inventory-service.yml
└── inventory-service-production.yml
```

Các file được đọc trực tiếp từ vị trí này. Người vận hành có thể cập nhật file bằng quy trình triển khai filesystem, đồng bộ artifact hoặc mount volume. Native backend không yêu cầu Git, không clone repository và không cung cấp lịch sử commit.

### Native backend và label

Native backend không có ngữ nghĩa branch, tag hoặc commit của Git. Nếu cấu hình search location có `{label}`, giá trị label được dùng như một phần của đường dẫn theo quy ước thư mục mà đội vận hành tự tổ chức. Ví dụ:

```yaml
spring:
  profiles:
    active: native
  cloud:
    config:
      server:
        native:
          search-locations:
            - file:/srv/config-files/{label}
```

Trong cấu trúc này, label `release-2026.11` có thể dẫn tới thư mục `/srv/config-files/release-2026.11`. Tuy nhiên, Config Server không thực hiện Git checkout hoặc xác minh lịch sử cho thư mục đó. Việc tạo phiên bản, bảo vệ thư mục, rollback và kiểm soát thay đổi do quy trình triển khai filesystem chịu trách nhiệm.

## 3. Git backend với URI `file://`: đọc repository Git cục bộ

Git backend thường được dùng với remote Git qua HTTPS hoặc SSH. Tuy nhiên, backend cũng có thể truy cập repository nằm trên filesystem của máy chạy Config Server thông qua URI `file:`.

Ví dụ:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: file:///srv/git/config-repo.git
          default-label: main
          clone-on-start: true
```

Trong ví dụ này:

- `uri` trỏ tới repository Git cục bộ.
- `default-label` chỉ định label mặc định khi client không gửi label.
- `clone-on-start` yêu cầu Config Server kiểm tra và clone repository khi server khởi động, giúp phát hiện sớm lỗi URI hoặc quyền truy cập.

Repository đích phải được khởi tạo và có commit/branch phù hợp với label dự kiến. Một bare repository thường phù hợp làm nguồn Git cục bộ vì không có working tree đang checkout branch. Có thể tạo bare repository và clone một working copy để cập nhật:

```bash
git init --bare /srv/git/config-repo.git
git clone /srv/git/config-repo.git /srv/work/config-repo
cd /srv/work/config-repo
git switch -c main
# Thêm file cấu hình, sau đó commit và push branch main
git add .
git commit -m "Add initial configuration"
git push -u origin main
```

Ví dụ trên tạo branch `main` để khớp với `default-label: main`. Sau khi thêm hoặc sửa file cấu hình trong working copy, tạo commit và push branch lên bare repository. Config Server đọc repository này bằng Git backend, nên vẫn có thể dùng branch, tag và commit làm label giống khi nguồn Git nằm trên máy chủ Git từ xa.

### Cách viết URI file

Với đường dẫn tuyệt đối trên hệ thống Unix-like, URI dạng `file:///srv/git/config-repo.git` thể hiện đường dẫn filesystem cục bộ. Trên Windows, URI thường có dạng `file:///C:/config/config-repo.git`; dùng dấu gạch chéo `/` theo cú pháp URI và kiểm tra cách thư viện Git phân giải đường dẫn trong môi trường chạy.

Đừng nhầm `file:///path/to/repo` với `file://host/path`. Dạng đầu chỉ tới đường dẫn cục bộ trên máy Config Server. Dạng có host là URI với authority và có thể không được hỗ trợ như một filesystem remote theo cách bạn mong đợi. Nếu repository nằm trên máy khác, thường nên dùng HTTPS hoặc SSH; nếu dùng network share, hãy mount nó vào filesystem của máy/container và kiểm thử quyền truy cập thực tế.

## 4. So sánh hai backend

| Tiêu chí | Native backend | Git backend với URI `file://` |
|---|---|---|
| Thuộc tính chính | `native.search-locations` | `git.uri` |
| Đối tượng được trỏ tới | Thư mục/classpath chứa file YAML hoặc properties | Repository Git cục bộ |
| Cần Git metadata | Không | Có |
| Kích hoạt | Profile `native` | Cấu hình Git backend; thường dùng backend Git mặc định |
| Phiên bản cấu hình | Do cấu trúc thư mục và quy trình triển khai tự quản lý | Branch, tag, commit |
| Lịch sử thay đổi | Không có lịch sử Git tích hợp | Có lịch sử commit và diff của Git |
| Cách cập nhật | Thay file hoặc cập nhật volume/artifact | Commit/push vào repository, Git backend fetch theo cơ chế của nó |
| Rollback | Khôi phục file hoặc thư mục phiên bản trước | Chọn tag, branch hoặc commit đã biết là tốt |
| Quyền filesystem | Tài khoản chạy server cần đọc các search location | Tài khoản chạy server cần đọc repository và Git metadata |
| Trường hợp phù hợp | Cấu hình đơn giản, đóng gói cùng triển khai hoặc do hệ thống file quản lý | Cần lịch sử, label Git và quy trình review/release |

Hai backend vẫn có thể được kết hợp trong kiến trúc có chủ đích thông qua composite environment repository, nhưng cần hiểu thứ tự ưu tiên giữa các repository và kiểm thử property source. Với một Config Server thông thường, hãy chọn backend rõ ràng để tránh vô tình chạy native profile trong khi mong đợi Git backend hoặc ngược lại.

## 5. Client gọi API giống nhau dù backend khác nhau

Config Client thường không cần biết Config Server đang đọc file trực tiếp hay đọc Git repository. Client gửi application, profile và label; server chịu trách nhiệm phân giải nguồn dữ liệu.

Ví dụ request:

```text
/{application}/{profile}/{label}
```

Với Git backend, label như `main` hoặc `config-release-2026.11.0` có thể trỏ tới branch hoặc tag Git. Với native backend, label chỉ có ý nghĩa theo cách search location sử dụng placeholder `{label}` hoặc quy tắc lưu trữ đã cấu hình.

Ví dụ gọi endpoint:

```bash
curl --fail --silent --show-error \
  "https://config.example.internal/order-service/production/main"
```

Đây là ví dụ endpoint tổng quát; response có thể chứa cấu hình nội bộ hoặc bí mật. Trong môi trường thật, dùng xác thực và TLS, đồng thời không in hoặc lưu response nhạy cảm vào log. Khi kiểm tra backend, hãy xác nhận metadata `name`, `profiles`, `label` và các property source phù hợp.

## 6. Cập nhật và khả năng tái lập

Với native backend, nội dung được đọc từ các file trong search location. Khi file thay đổi, khả năng nhìn thấy giá trị mới phụ thuộc vào cách filesystem được cập nhật, cách triển khai và cơ chế đọc/cache của phiên bản đang dùng. Native backend không fetch Git và không thể dùng commit SHA để tái lập nội dung. Nếu cần rollback, đội vận hành phải giữ artifact hoặc snapshot thư mục đã phát hành.

Với Git backend, Config Server dùng Git để phân giải label và đồng bộ repository theo cấu hình backend. Có thể quản lý `refresh-rate`, branch, tag và commit theo nhu cầu. Branch mutable như `main` có thể trỏ tới commit mới theo thời gian; tag phát hành hoặc commit cụ thể phù hợp hơn khi cần tái lập cấu hình production.

Khi dùng Git URI cục bộ, vẫn cần cập nhật bare repository hoặc repository nguồn đúng quy trình. Thay đổi file trong một working directory khác không tự động thay đổi repository mà Config Server đang đọc. Cần commit và push tới repository được URI chỉ định, sau đó xác nhận Config Server đã nhìn thấy commit mới theo chính sách fetch/cache.

## 7. Quyền truy cập và bảo mật

Với native backend, tài khoản hệ điều hành chạy Config Server phải có quyền đọc các search location. Chỉ mount những thư mục cần thiết, ưu tiên mount read-only và không đặt file bí mật trong thư mục có thể được phục vụ cho nhiều client. Nếu dùng placeholder trong đường dẫn, cần kiểm soát application/profile/label đầu vào và giới hạn search location trong vùng cấu hình được phép.

Với Git backend qua `file://`, tài khoản chạy Config Server phải có quyền đọc repository và Git metadata. URI cục bộ không dùng xác thực SSH/HTTPS của Git server; quyền truy cập được quyết định chủ yếu bởi quyền filesystem, user/group, mount và chính sách của máy chủ. Hãy giới hạn quyền đọc repository và tránh cho các tiến trình không liên quan có thể sửa refs hoặc object database.

Ở cả hai backend:

- Bảo vệ endpoint Config Server bằng TLS, xác thực và phân quyền phù hợp.
- Không lưu password, token hoặc private key dạng rõ trong file cấu hình được phân phối rộng.
- Không công khai endpoint Actuator có thể tiết lộ property source.
- Chỉ cấp quyền cho workload cần đọc cấu hình.
- Theo dõi thay đổi file hoặc Git commit và lưu dấu vết phát hành.

## 8. Chạy nhiều Config Server instance

Nếu Config Server có nhiều replica, mỗi instance phải nhìn thấy cùng một nguồn cấu hình nhất quán.

Với native backend, nếu mỗi container có filesystem riêng, cập nhật file ở một instance không làm các instance khác tự động nhận nội dung mới. Có thể dùng image/artifact bất biến hoặc mount volume dùng chung ở chế độ phù hợp, rồi triển khai đồng nhất tới các replica.

Với Git backend dùng `file://`, mọi replica cần truy cập được repository nguồn cùng một trạng thái. Nếu mỗi replica có một bản repository local độc lập, cần quy định cách cập nhật và đồng bộ để tránh trả các label hoặc commit khác nhau. Với hệ thống phân tán, remote Git qua HTTPS/SSH thường dễ quản trị và kiểm toán hơn so với chia sẻ một repository qua filesystem.

Không nên giả định một đường dẫn tuyệt đối trên host tự động tồn tại trong container hoặc trên mọi node. Hãy kiểm tra mount, UID/GID, quyền đọc, tính sẵn sàng của volume và cách triển khai khi pod được tạo lại.

## 9. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Native backend không tìm thấy file | Chưa kích hoạt profile `native`, sai `search-locations` hoặc server không có quyền đọc | Kiểm tra profile đang hoạt động, đường dẫn tuyệt đối và quyền filesystem |
| Git backend báo lỗi clone/read repository | URI trỏ tới thư mục không phải Git repo hoặc user chạy server không có quyền | Xác minh repository metadata, refs, URI và quyền đọc |
| Dùng `file:` nhưng Config Server không hoạt động như mong muốn | Đặt URI file ở sai thuộc tính hoặc chọn nhầm backend | Native dùng `native.search-locations`; Git dùng `git.uri` |
| Git label không tìm thấy | Branch/tag chưa tồn tại trong repository nguồn hoặc sai `default-label` | Kiểm tra refs và label ở đúng repository |
| Cập nhật file native nhưng API vẫn trả giá trị cũ | Server đọc vị trí khác, volume chưa cập nhật hoặc có cache/instance khác | Kiểm tra search location, mount và response từng replica |
| Commit mới trong local working copy chưa được server thấy | Chưa push vào repository mà `file://` trỏ tới hoặc backend chưa fetch | Kiểm tra remote path, commit/branch và chính sách refresh của Git backend |
| Các replica trả cấu hình khác nhau | Filesystem/repository local không đồng bộ | Dùng nguồn chung có kiểm soát hoặc triển khai cùng snapshot cho mọi replica |

Quy trình chẩn đoán nên bắt đầu từ cấu hình backend đang chạy, sau đó xác minh đường dẫn thực tế mà tiến trình nhìn thấy, quyền đọc và cuối cùng là response của endpoint theo application/profile/label. Đừng chỉ nhìn thấy chuỗi `file:` rồi kết luận server đang dùng native backend.

## 10. Chọn backend nào?

Chọn **native backend** khi:

- Cấu hình là các file đơn giản được đóng gói trong image hoặc mount từ một thư mục được quản trị.
- Không cần branch, tag, commit hoặc lịch sử Git để phân phối cấu hình.
- Quy trình cập nhật và rollback filesystem đã được tổ chức rõ.
- Môi trường phát triển hoặc kiểm thử cần một nguồn file đơn giản.

Chọn **Git backend với URI `file://`** khi:

- Muốn dùng Git repository cục bộ mà không cần Git server từ xa.
- Cần branch, tag, commit và lịch sử thay đổi của Git.
- Có quy trình commit, review, tạo tag và rollback rõ ràng.
- Config Server có quyền truy cập ổn định tới repository trên filesystem.

Nếu nhiều nhóm cùng thay đổi cấu hình, cần review và phát hành độc lập, một Git server từ xa thường phù hợp hơn việc chia sẻ một thư mục Git cục bộ. Nếu chỉ cần đọc một bộ file được đóng gói cùng ứng dụng, native backend có thể đơn giản hơn.

## 11. Checklist xác minh backend

Trước khi đưa Config Server vào vận hành, hãy kiểm tra:

- [ ] Đã xác định rõ backend cần dùng là native hay Git.
- [ ] Native dùng `spring.cloud.config.server.native.search-locations` và profile `native`.
- [ ] Git dùng `spring.cloud.config.server.git.uri` trỏ tới repository Git hợp lệ.
- [ ] Đường dẫn `file:` là đường dẫn tuyệt đối mà tiến trình Config Server thực sự nhìn thấy.
- [ ] Tài khoản chạy server có quyền đọc đúng thư mục hoặc repository.
- [ ] Với Git backend, branch/tag/commit mặc định tồn tại trong repository nguồn.
- [ ] Đã kiểm tra endpoint theo application, profile và label.
- [ ] Đã xác minh các Config Server replica nhìn thấy cùng nguồn dữ liệu.
- [ ] Có quy trình bảo vệ bí mật, review thay đổi và rollback.

## 12. Mục tiêu cần đạt sau bài học

Sau bài này, người học cần có khả năng:

- Giải thích vì sao native `search-locations: file:` và Git `uri: file://` là hai cách truy cập filesystem với ngữ nghĩa khác nhau.
- Cấu hình native backend để đọc trực tiếp file YAML/properties.
- Cấu hình Git backend để đọc một repository Git cục bộ bằng file URI.
- Nhận diện yêu cầu Git metadata, branch/tag/commit và cách label được diễn giải ở từng backend.
- Chẩn đoán lỗi đường dẫn, profile, quyền filesystem, Git refs và đồng bộ giữa nhiều replica.
- Chọn backend phù hợp theo nhu cầu lịch sử, versioning, vận hành và bảo mật.

**Tự kiểm tra:** Một Config Server có `search-locations: file:/srv/config-files` và một Config Server khác có `git.uri: file:///srv/git/config-repo.git`. Hãy giải thích loại dữ liệu mà mỗi đường dẫn phải chứa, trường hợp nào cần profile `native`, vì sao chỉ có file YAML chưa đủ để dùng Git backend và cách xác định một tag release có thể được đọc từ repository cục bộ.
