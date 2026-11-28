# Dùng tag hoặc commit để xác định phiên bản cấu hình

Spring Cloud Config cho phép client yêu cầu cấu hình theo ba thông tin chính: tên ứng dụng, profile và label. Tên ứng dụng xác định dịch vụ cần cấu hình; profile xác định biến thể cấu hình theo môi trường hoặc mục đích chạy; label xác định phiên bản cấu hình trong backend. Khi dùng Git làm backend, label có thể trỏ tới branch, tag hoặc commit.

Việc chọn label ảnh hưởng trực tiếp đến khả năng tái lập triển khai. Nếu production luôn đọc một branch đang thay đổi, cùng một bản ứng dụng có thể nhận bộ cấu hình khác nhau ở hai thời điểm. Nếu production dùng tag phát hành được bảo vệ hoặc commit cụ thể, nhóm vận hành có thể xác định chính xác snapshot cấu hình mà client cần nhận. Bài học này tập trung vào cách dùng tag và commit để phát hành, truy vết và rollback cấu hình một cách có kiểm soát.

## 1. Phân biệt profile và label

Profile và label giải quyết hai chiều khác nhau:

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| Application name | Ứng dụng nào cần cấu hình? | `order-service` |
| Profile | Ứng dụng chạy theo biến thể nào? | `staging`, `production` |
| Label | Cần phiên bản repository nào? | `config-release-2026.11.0`, một commit SHA |

Ví dụ, `order-service` có thể yêu cầu cấu hình với profile `production` và label `config-release-2026.11.0`. Profile production chọn các giá trị dành cho môi trường production; label chọn snapshot Git chứa các file cấu hình tại thời điểm phát hành.

Một snapshot có thể chứa nhiều file profile. Vì vậy, cùng một label có thể cung cấp cấu hình staging hoặc production tùy profile mà client yêu cầu. Đây là cơ sở để kiểm thử một phiên bản cấu hình rồi promote chính snapshot đó qua các môi trường, trong khi mỗi môi trường vẫn nhận giá trị phù hợp.

## 2. Label của Git backend có thể trỏ tới đâu?

Git có nhiều loại reference. Spring Cloud Config Git backend có thể dùng label để chọn branch, tag hoặc commit:

| Loại label | Đặc điểm | Trường hợp phù hợp |
|---|---|---|
| Branch, ví dụ `main` | Trỏ tới commit đầu nhánh và thay đổi khi có commit mới | Phát triển liên tục, môi trường thử nghiệm cần nhận cấu hình mới |
| Tag, ví dụ `config-release-2026.11.0` | Đánh dấu một phiên bản phát hành; có thể bảo vệ để không bị di chuyển hoặc xóa | Staging, production và các đợt phát hành cần truy vết |
| Commit SHA | Xác định trực tiếp một commit cụ thể | Pin chính xác snapshot, điều tra sự cố hoặc tái lập triển khai |

Branch thuận tiện cho phát triển nhưng là reference có thể thay đổi. Nếu client yêu cầu `main` vào hôm nay và ngày mai, kết quả có thể khác dù cấu hình client không đổi.

Tag thường dễ đọc hơn commit SHA và có thể mang ý nghĩa phát hành. Tag không tự bất biến về mặt kỹ thuật: người có quyền vẫn có thể xóa hoặc tạo lại tag trỏ tới commit khác. Để tag thực sự đáng tin cậy, repository cần bảo vệ quy tắc tạo, cập nhật và xóa tag.

Commit SHA xác định nội dung commit cụ thể. Dùng đầy đủ SHA giúp tránh nhầm lẫn do dạng rút gọn có thể không còn duy nhất khi repository lớn lên. Commit SHA là lựa chọn phù hợp khi cần ghi lại chính xác commit mà hệ thống đã sử dụng.

## 3. Cấu hình Config Server và Config Client

Config Server dùng Git backend để đọc repository. Có thể cấu hình nhánh mặc định rõ ràng thay vì phụ thuộc vào giá trị mặc định của phiên bản thư viện:

```yaml
server:
  port: 8888

spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.internal/platform/config-repo.git
          default-label: main
```

`default-label` xác định label Git mà server sử dụng khi request không chỉ định label. Giá trị mặc định có thể khác theo phiên bản Spring Cloud Config; hãy khai báo rõ để tránh phụ thuộc vào mặc định lịch sử của nhánh Git.

Config Client có thể chỉ định label bằng `spring.cloud.config.label`. Ví dụ:

```yaml
spring:
  application:
    name: order-service
  profiles:
    active: production
  config:
    import: "configserver:https://config.example.internal"
  cloud:
    config:
      label: config-release-2026.11.0
```

Client cần khai báo label từ nguồn cấu hình có sẵn trước khi tải cấu hình tập trung, chẳng hạn biến môi trường hoặc cấu hình triển khai. Không nên đặt duy nhất label cần dùng bên trong chính bộ cấu hình mà client phải tải mới biết được label đó.

Ví dụ có thể truyền label từ môi trường triển khai:

```bash
SPRING_CLOUD_CONFIG_LABEL=config-release-2026.11.0
SPRING_PROFILES_ACTIVE=production
```

Khi request tới Config Server, endpoint REST có dạng tổng quát:

```text
/{application}/{profile}/{label}
```

Ví dụ:

```text
https://config.example.internal/order-service/production/config-release-2026.11.0
```

Endpoint trên yêu cầu cấu hình của `order-service`, profile `production`, tại label đã chỉ định. Cần bảo vệ endpoint bằng TLS và xác thực/phân quyền phù hợp vì response có thể chứa thông tin cấu hình nội bộ.

## 4. Tạo tag phát hành cho repository cấu hình

Một quy trình đơn giản là merge thay đổi đã review vào nhánh tích hợp, kiểm tra commit, sau đó tạo tag phát hành. Nên ưu tiên annotated tag để lưu thông điệp và metadata phát hành.

Ví dụ:

```bash
# Xem commit đang được chọn để phát hành
git log -1 --oneline

# Tạo annotated tag tại commit hiện tại
git tag -a config-release-2026.11.0 -m "Configuration release 2026.11.0"

# Đẩy tag lên remote
git push origin config-release-2026.11.0
```

Nếu cần tạo tag cho một commit đã xác định, truyền commit SHA làm đối số cuối:

```bash
git tag -a config-release-2026.11.0 FULL_COMMIT_SHA -m "Configuration release 2026.11.0"
```

`FULL_COMMIT_SHA` là chỗ giữ chỗ; thay bằng SHA đầy đủ đã được kiểm tra trong repository. Không dùng nguyên văn chuỗi giữ chỗ trong lệnh thực tế.

Sau khi tạo tag, xác minh tag trỏ đúng commit:

```bash
git show --no-patch --format=fuller config-release-2026.11.0
git rev-parse config-release-2026.11.0^{commit}
```

Sau đó, kiểm tra tag đã xuất hiện trên remote và Config Server có thể đọc được label này. Việc tạo tag thành công ở máy local chưa đảm bảo tag đã được đẩy lên remote mà Config Server truy cập.

## 5. Quy trình phát hành cấu hình có thể tái lập

Một quy trình release tốt cần liên kết được pull request, commit, tag, kết quả kiểm thử và môi trường đang chạy.

1. **Tạo thay đổi:** nhóm sở hữu cập nhật file cấu hình và mở pull request.
2. **Review:** kiểm tra ý nghĩa thuộc tính, phạm vi ứng dụng/profile bị ảnh hưởng và rủi ro vận hành.
3. **Kiểm tra tự động:** parse YAML, kiểm tra schema, phát hiện secret, xác minh quy ước tên và gọi thử Config Server.
4. **Merge:** đưa thay đổi đã duyệt vào nhánh tích hợp.
5. **Chốt snapshot:** ghi nhận commit SHA và tạo tag phát hành trỏ đúng commit đó.
6. **Kiểm thử staging:** cấu hình client hoặc môi trường staging sử dụng tag này; xác minh ứng dụng nhận đúng property source và hành vi mong muốn.
7. **Promote production:** dùng cùng tag cho production, với profile production.
8. **Lưu dấu vết:** ghi lại tag, commit SHA, thời điểm phát hành, người phê duyệt và các dịch vụ bị ảnh hưởng.

Ví dụ cùng một tag `config-release-2026.11.0` có thể được dùng như sau:

| Môi trường | Application | Profile | Label |
|---|---|---|---|
| Staging | `order-service` | `staging` | `config-release-2026.11.0` |
| Production | `order-service` | `production` | `config-release-2026.11.0` |
| Staging | `inventory-service` | `staging` | `config-release-2026.11.0` |
| Production | `inventory-service` | `production` | `config-release-2026.11.0` |

Mỗi ứng dụng/profile nhận các file phù hợp trong cùng snapshot Git. Khi có thay đổi riêng cho production, thay đổi đó phải được đưa vào một snapshot mới và phát hành theo quy trình; không sửa tag cũ để cập nhật ngầm nội dung.

## 6. Dùng commit SHA khi cần pin chính xác

Tag giúp con người nhận diện phiên bản; commit SHA giúp máy móc và người vận hành xác định chính xác commit. Có thể dùng SHA đầy đủ làm label trong `spring.cloud.config.label` nếu Git backend và phiên bản Spring Cloud Config đang triển khai hỗ trợ cách phân giải commit label.

Ví dụ:

```yaml
spring:
  cloud:
    config:
      label: FULL_COMMIT_SHA
```

Trong pipeline phát hành, có thể ghi cả tag và SHA vào metadata triển khai:

```text
CONFIG_LABEL=config-release-2026.11.0
CONFIG_COMMIT=FULL_COMMIT_SHA
APPLICATION=order-service
PROFILE=production
```

Tag cung cấp tên phát hành dễ đọc; SHA cho phép xác minh tag vẫn trỏ tới đúng commit. Nếu có yêu cầu kiểm toán cao, pipeline có thể lưu SHA cùng phiên bản ứng dụng trong deployment record hoặc artifact metadata.

Không nên tự động giả định mọi Git backend đều xử lý mọi dạng label giống nhau. Cần thử endpoint Config Server với tag và commit SHA trên đúng phiên bản server trước khi đưa vào pipeline production. Với commit SHA, dùng full SHA và kiểm tra commit thuộc repository/remote mà Config Server đang clone.

## 7. Branch, tag và commit: chọn cách nào?

| Nhu cầu | Lựa chọn nên cân nhắc | Lý do |
|---|---|---|
| Môi trường phát triển cần cập nhật thường xuyên | Branch tích hợp như `main` hoặc `develop` | Mỗi commit mới có thể được thử nghiệm ngay |
| Staging kiểm thử một bản cấu hình ứng viên | Tag ứng viên hoặc commit SHA | Kết quả kiểm thử gắn với một snapshot xác định |
| Production cần tính tái lập | Tag phát hành được bảo vệ hoặc commit SHA | Không trôi theo commit mới trên branch |
| Điều tra sự cố lịch sử | Commit SHA đã ghi trong deployment record | Xác định chính xác nội dung cấu hình tại thời điểm xảy ra lỗi |
| Thử nghiệm thay đổi tạm thời | Branch riêng | Dễ thay đổi, bỏ hoặc merge sau khi thử nghiệm |

Không nên dùng branch mutable làm bằng chứng duy nhất cho một release production. Nếu vẫn dùng branch theo môi trường, phải ghi nhận commit thực tế đã được server phục vụ và có cách tái lập/rollback về commit đó.

## 8. Bảo vệ tag và kiểm soát thay đổi

Tag có thể bị di chuyển hoặc xóa nếu người dùng có quyền phù hợp. Vì vậy, quy trình phát hành cần có chính sách bảo vệ tag:

- Chỉ pipeline release hoặc nhóm được chỉ định mới có quyền tạo tag phát hành.
- Chặn force update và xóa tag release trên remote nếu nền tảng Git hỗ trợ.
- Không tái sử dụng tên tag đã phát hành cho một nội dung khác.
- Nếu phát hiện lỗi sau phát hành, tạo tag phiên bản mới hoặc quay về tag cũ đã biết là tốt.
- Có thể ký annotated tag để xác thực nguồn phát hành nếu tổ chức có hạ tầng quản lý khóa ký.
- Lưu tag và commit SHA trong hồ sơ triển khai.

Không nên xóa tag cũ chỉ để làm danh sách tag gọn hơn. Tag cũ là bằng chứng giúp xác định cấu hình đã được phân phối và là điểm quay lui khi cần. Chính sách lưu trữ có thể quy định thời hạn, nhưng phải đáp ứng yêu cầu truy vết và kiểm toán.

## 9. Rollback bằng tag hoặc commit

Khi cấu hình mới gây lỗi, rollback cần đưa client về snapshot đã biết là tốt. Có thể thực hiện bằng cách thay label triển khai về tag trước đó, sau đó refresh hoặc khởi động lại ứng dụng theo cơ chế đã thiết kế.

Ví dụ:

```text
# Phiên bản đang gặp sự cố
SPRING_CLOUD_CONFIG_LABEL=config-release-2026.11.0

# Phiên bản trước đã được xác minh
SPRING_CLOUD_CONFIG_LABEL=config-release-2026.10.3
```

Sau khi đổi label, cần xác nhận client thực sự gửi request với label mới, Config Server trả đúng phiên bản và các instance đã áp dụng cấu hình. Nếu client chỉ đọc cấu hình khi khởi động, cần restart theo quy trình triển khai. Nếu dùng refresh hoặc Spring Cloud Bus, phải kiểm tra sự kiện đã tới các instance và bean liên quan có thể nhận giá trị mới.

Không nên tạo tag mới trỏ về nội dung cũ chỉ để rollback nếu tổ chức cần giữ nguyên lịch sử release. Có thể deploy lại tag cũ đã xác minh. Nếu cần phát hành bản sửa tiếp theo, tạo tag phiên bản mới với commit mới.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Config Server không tìm thấy label | Tag/branch chưa được push hoặc label viết sai | Kiểm tra remote refs và yêu cầu đúng endpoint |
| Client nhận cấu hình mới dù không đổi label | Client đang dùng branch mutable | Pin tag hoặc commit SHA cho môi trường cần tái lập |
| Tag local đúng nhưng server trả nội dung khác | Tag remote trỏ commit khác, cache/clone chưa cập nhật hoặc tag bị di chuyển | Xác minh remote tag, commit SHA và trạng thái repository của Config Server |
| Hai môi trường khác nhau dù cùng label | Profile khác nhau hoặc nguồn cấu hình khác có độ ưu tiên cao hơn | Kiểm tra application, profile, property source và cấu hình local của client |
| Rollback label nhưng instance vẫn giữ giá trị cũ | Client chưa refresh hoặc bean không hỗ trợ cập nhật nóng | Kiểm tra sự kiện refresh, trạng thái instance hoặc restart |
| Release cũ không thể tái lập | Tag đã bị xóa/di chuyển hoặc commit không còn truy cập được | Bảo vệ tag, lưu SHA và duy trì khả năng truy cập repository lịch sử |

Khi chẩn đoán, hãy ghi nhận đủ ba giá trị application, profile và label. Chỉ kiểm tra label là chưa đủ vì cùng một commit có thể chứa nhiều bộ cấu hình khác nhau theo ứng dụng và profile.

## 11. Checklist phát hành cấu hình

Trước khi promote một snapshot cấu hình, nhóm phát hành có thể xác minh:

- [ ] Pull request đã được review bởi chủ sở hữu phù hợp.
- [ ] CI đã kiểm tra cú pháp, schema và secret scanning.
- [ ] Commit SHA đã được ghi lại.
- [ ] Tag release đã được tạo và push lên remote.
- [ ] Tag được bảo vệ khỏi cập nhật hoặc xóa ngoài quy trình.
- [ ] Config Server trả đúng cấu hình cho application/profile/label cần phát hành.
- [ ] Staging đã kiểm thử đúng tag dự kiến dùng cho production.
- [ ] Deployment record lưu label, SHA, profile, ứng dụng và thời điểm.
- [ ] Có tag hoặc commit trước đó đã xác minh để rollback.

## 12. Mục tiêu cần đạt sau bài học

Sau bài này, người học cần có khả năng:

- Giải thích được vai trò của label trong yêu cầu cấu hình của Spring Cloud Config.
- Phân biệt branch, tag và commit SHA khi dùng Git backend.
- Cấu hình `spring.cloud.config.label` ở Config Client và `default-label` ở Config Server.
- Tạo và xác minh tag phát hành trỏ tới commit mong muốn.
- Thiết kế quy trình kiểm thử staging và promote cùng snapshot sang production.
- Bảo vệ tag release, lưu dấu vết commit và tránh thay đổi nội dung tag đã phát hành.
- Rollback bằng tag hoặc commit đã biết là tốt và xác minh client đã nhận lại cấu hình.

**Tự kiểm tra:** `order-service` đang chạy production với label `config-release-2026.10.3`. Nhóm phát hành thay đổi timeout và tạo tag `config-release-2026.11.0`, sau đó kiểm thử thành công ở staging. Hãy giải thích cách cấu hình production dùng đúng tag mới, dữ liệu nào cần ghi vào deployment record và cách quay lại phiên bản trước nếu sau refresh xuất hiện lỗi. Vì sao không nên chỉ cấu hình production đọc branch `main`?
