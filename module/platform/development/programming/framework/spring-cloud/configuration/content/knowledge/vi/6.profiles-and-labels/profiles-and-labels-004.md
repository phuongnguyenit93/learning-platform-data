# Chọn label và cấu hình nhánh mặc định phía máy chủ

## 1. Label giải quyết vấn đề gì?

Trong Spring Cloud Config, client thường yêu cầu cấu hình theo ba thông tin: tên ứng dụng, profile và label. Application xác định dịch vụ, profile xác định nhóm cấu hình theo môi trường hoặc chế độ chạy, còn label xác định phiên bản của nguồn cấu hình mà Config Server cần đọc.

Với Git backend, label thường là tên branch, tag hoặc commit. Ví dụ, `order-service` chạy profile `prod` có thể yêu cầu label `release-2026-11`. Khi đó Config Server đọc file cấu hình ứng với `order-service` và `prod` tại revision được label chỉ định.

Label rất quan trọng với phát hành. Nếu tất cả client đều đọc branch `main`, nội dung cấu hình mà chúng nhận được có thể thay đổi khi branch có commit mới. Một lần triển khai hôm nay và lần triển khai tuần sau có thể dùng cấu hình khác nhau dù ứng dụng vẫn khai báo cùng một label. Dùng tag hoặc commit cố định giúp xác định chính xác phiên bản cấu hình đã được phát hành.

## 2. Phân biệt label của client và nhánh mặc định của server

Có hai thuộc tính thường bị nhầm lẫn:

| Thuộc tính | Nơi cấu hình | Vai trò |
|---|---|---|
| `spring.cloud.config.label` | Config Client | Chọn label mà client yêu cầu từ Config Server. |
| `spring.cloud.config.server.git.default-label` | Config Server | Chọn label mặc định của Git backend khi request không chỉ định label. |

Client có thể chủ động chọn label. Nếu client không gửi label, Config Server dùng nhánh mặc định đã cấu hình ở server hoặc mặc định của repository được chọn. Do đó, `default-label` không phải là một profile và cũng không phải giá trị thay thế cho `spring.profiles.active`.

Ví dụ: Config Server có `default-label: main`, nhưng một client có thể yêu cầu `release-2026-11`. Request có label tường minh sẽ chọn label đó; giá trị mặc định chỉ được dùng khi request không chỉ định label.

## 3. Cấu hình nhánh mặc định ở Config Server

Config Server là ứng dụng Spring Boot và nhận cấu hình Git backend từ `Environment` runtime của chính nó. Với một repository, có thể khai báo URI và nhánh mặc định như sau:

```yaml
server:
  port: 8888

spring:
  application:
    name: config-server
  cloud:
    config:
      server:
        git:
          uri: ${CONFIG_REPO_URI}
          default-label: main
          clone-on-start: true
```

Trong ví dụ này:

- `uri` trỏ đến Git repository chứa cấu hình client.
- `default-label: main` chỉ định branch được dùng khi client không truyền label.
- `clone-on-start: true` yêu cầu server thử clone repository khi khởi động để phát hiện sớm lỗi URI hoặc quyền truy cập.

Nên khai báo `default-label` tường minh thay vì phụ thuộc vào giá trị mặc định của thư viện. Tên nhánh mặc định của repository có thể khác nhau giữa các tổ chức và hành vi mặc định/fallback cũng có thể thay đổi theo phiên bản Spring Cloud Config. Nếu repository vẫn dùng `master`, có thể đặt rõ `default-label: master`; khi chuyển sang `main`, hãy đổi cấu hình server cùng với việc xác nhận branch đã tồn tại.

Một số phiên bản Git backend có cơ chế tương thích thử nhánh `master` khi nhánh được chọn không tồn tại; chi tiết và tùy chọn kiểm soát như `tryMasterBranch` phụ thuộc release train. Không nên dựa vào fallback này làm chính sách phát hành. Hãy khai báo branch rõ ràng và kiểm tra endpoint với đúng phiên bản server.

## 4. Client chọn label cụ thể

Với Config Data của Spring Boot hiện đại, client khai báo tên ứng dụng, profile và label như sau:

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

Client sẽ yêu cầu cấu hình tương ứng với:

```text
GET /order-service/prod/release-2026-11
```

Ở đây `prod` là profile, còn `release-2026-11` là label. Hai giá trị này có thể thay đổi độc lập: cùng một profile `prod` có thể được kiểm thử với một label mới trước khi chuyển toàn bộ ứng dụng sang phiên bản cấu hình đó.

Nếu muốn dùng nhánh mặc định của server, client có thể bỏ `spring.cloud.config.label`:

```yaml
spring:
  application:
    name: order-service
  profiles:
    active: prod
  config:
    import: "configserver:${CONFIG_SERVER_URI}"
```

Khi đó Config Server dùng `default-label` đã cấu hình. Đây là cách thuận tiện cho môi trường phát triển hoặc khi tổ chức chủ động muốn server quyết định nhánh mặc định. Với production cần tái lập chính xác, nên cân nhắc ghim label theo bản phát hành.

Các dự án cũ có thể dùng `bootstrap.yml` và bootstrap context để cấu hình Config Client. Với Spring Boot hỗ trợ Config Data, `spring.config.import` là cách khai báo hiện đại. Cần chọn cú pháp theo cặp phiên bản Spring Boot/Spring Cloud thực tế, không trộn hai cơ chế một cách tùy tiện.

## 5. Dùng branch, tag hay commit làm label?

Git cung cấp nhiều loại tham chiếu có thể dùng làm label. Mỗi loại phù hợp với một mục đích khác nhau.

| Loại label | Đặc điểm | Khi nên dùng |
|---|---|---|
| Branch, ví dụ `main` hoặc `develop` | Trỏ đến commit mới nhất của nhánh và di chuyển khi có commit mới. | Phát triển liên tục, môi trường tích hợp hoặc nơi cần nhận thay đổi thường xuyên. |
| Tag, ví dụ `config-v2.4.0` | Đặt tên cho một revision phát hành; nên được bảo vệ để không bị di chuyển. | Ghim cấu hình cho một lần release và dễ tra cứu bằng tên có ý nghĩa. |
| Commit SHA | Xác định trực tiếp một commit cụ thể. | Tái lập chính xác, điều tra sự cố hoặc rollback có kiểm soát. |

Branch tiện cho cập nhật liên tục nhưng không đảm bảo tính bất biến. Nếu client dùng `main`, hai lần khởi động ở hai thời điểm có thể lấy hai bộ cấu hình khác nhau. Tag dễ nhớ hơn SHA nhưng cần bảo vệ tag khỏi bị xóa hoặc di chuyển. Commit SHA có tính xác định cao, song khó đọc và quản lý thủ công hơn.

Một chiến lược thực tế là dùng branch cho phát triển, tạo tag cấu hình khi phát hành và lưu cả tag lẫn commit SHA trong thông tin triển khai. Với hệ thống yêu cầu tái lập nghiêm ngặt, có thể cấu hình client dùng commit SHA hoặc tag được bảo vệ.

Không nên đặt label là tên môi trường. `prod` nên là profile; `config-v2.4.0` hoặc một commit SHA mới là label. Việc giữ hai khái niệm độc lập cho phép phát hành cùng một phiên bản cấu hình cho nhiều môi trường theo thứ tự kiểm soát.

## 6. Nhánh mặc định toàn cục và nhánh mặc định theo repository

Khi Config Server phục vụ nhiều Git repository, mỗi repository có thể cần một nhánh mặc định khác nhau. Ví dụ repository chung dùng `main`, trong khi một repository cũ của nhóm payments vẫn dùng `master` trong thời gian chuyển đổi.

Có thể khai báo repository mặc định và repository chuyên biệt:

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
              default-label: main
            payments:
              pattern: 'payment-service/*'
              uri: ${PAYMENTS_CONFIG_REPO_URI}
              default-label: master
```

Trong ví dụ, repository mặc định và repository orders dùng `main`, còn repository payments dùng `master`. Khi client của `payment-service` không chỉ định label, server dùng nhánh mặc định của repository được chọn nếu cấu hình per-repository đó được hỗ trợ trong phiên bản đang dùng.

Khi client gửi label tường minh, label đó là lựa chọn cho request. Vì vậy, một client yêu cầu `release-2026-11` sẽ yêu cầu revision có tên đó thay vì nhánh mặc định. Nếu repository được chọn không có label đó, request sẽ thất bại hoặc trả lỗi theo backend và phiên bản; server không nên âm thầm chuyển sang một nhánh khác mà không có chính sách được kiểm chứng.

Với cấu hình nhiều repository, cần kiểm tra đồng thời hai việc: pattern đã chọn đúng repository và label có tồn tại trong repository đó. Một branch tồn tại ở repository orders không có nghĩa nó tồn tại ở repository payments.

## 7. Thay đổi nhánh mặc định khi repository chuyển từ master sang main

Nhiều repository cũ được khởi tạo với branch `master`, trong khi repository mới thường dùng `main`. Chuyển đổi cần được quản lý như một thay đổi phát hành.

Quy trình gợi ý:

1. Tạo branch `main` từ revision hiện tại của `master` và xác nhận nội dung hai nhánh tương đương tại thời điểm chuyển.
2. Cập nhật branch protection, quyền ghi, pipeline và quy tắc merge để `main` trở thành nhánh phát triển chính.
3. Thử Config Server với label `main` bằng endpoint và một client kiểm thử.
4. Cập nhật `spring.cloud.config.server.git.default-label` hoặc cấu hình default label của repository tương ứng.
5. Kiểm tra các client không khai báo `spring.cloud.config.label`, vì chúng chịu ảnh hưởng trực tiếp từ thay đổi mặc định phía server.
6. Kiểm tra các client đã ghim label cụ thể; chúng tiếp tục yêu cầu label tường minh cho đến khi cấu hình client được đổi.
7. Sau thời gian xác nhận, ngừng cập nhật `master` hoặc xóa branch cũ theo quy trình quản trị repository.

Thay đổi default label có thể ảnh hưởng nhiều client cùng lúc. Nên phát hành thay đổi này qua pull request, có kế hoạch rollback và theo dõi lỗi lấy cấu hình sau khi triển khai.

## 8. Kiểm chứng label bằng endpoint Config Server

Config Server cung cấp endpoint theo dạng:

```text
GET /{application}/{profile}/{label}
```

Ví dụ kiểm tra branch mặc định bằng cách bỏ label khỏi đường dẫn:

```text
GET https://config.example.internal/order-service/prod
```

Sau đó kiểm tra một label cụ thể:

```text
GET https://config.example.internal/order-service/prod/release-2026-11
```

Phản hồi `Environment` cho biết application, profile, label và các property source được trả về. Khi kiểm tra, cần xác nhận:

- Request có dùng label tường minh hay đang để server chọn default label.
- Label trả về có đúng branch, tag hoặc commit mong muốn không.
- File chung và file riêng theo application/profile có được tìm thấy không.
- Giá trị của một khóa thử nghiệm có khớp với revision Git đã chọn không.
- Không có secret nào bị đưa nhầm vào phản hồi.

Endpoint nên được gọi bằng danh tính có quyền đọc và qua HTTPS trong môi trường triển khai. Không ghi toàn bộ phản hồi có dữ liệu nhạy cảm vào log hoặc ticket.

## 9. Lỗi thường gặp khi chọn label

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Client không có label nhưng lấy sai cấu hình | `default-label` phía server trỏ đến branch khác dự kiến hoặc repository được chọn có default riêng. | Kiểm tra cấu hình Git backend và endpoint không có label. |
| Client gửi label nhưng server không tìm thấy | Branch, tag hoặc commit không tồn tại trong repository được chọn; sai chữ hoa/thường hoặc label bị xóa. | Kiểm tra Git refs trong đúng repository và sửa label request. |
| `order-service` hoạt động nhưng `payment-service` lỗi với cùng label | Label tồn tại trong repository orders nhưng không tồn tại trong repository payments. | Kiểm tra định tuyến repository và tạo/triển khai label phù hợp cho từng repository. |
| Một số client vẫn dùng nhánh cũ sau khi đổi default | Client khai báo `spring.cloud.config.label` tường minh hoặc còn cấu hình bootstrap cũ. | Kiểm tra cấu hình client và request thực tế; cập nhật label có chủ đích. |
| Cùng label nhưng hai lần triển khai nhận nội dung khác nhau | Label là branch di động đã có commit mới. | Dùng tag hoặc commit cố định cho release và ghi lại revision. |
| Server tự chuyển sang branch khác khi label không tồn tại | Hành vi fallback của Git backend hoặc phiên bản đang dùng. | Cấu hình default label tường minh, kiểm tra tùy chọn fallback và thử nghiệm trên đúng release train. |

Khi điều tra, hãy xác định theo thứ tự: application/profile request, repository được chọn, label request, default label áp dụng, Git ref thực tế và revision được trả về. Không đổi nhiều thuộc tính cùng lúc khi chưa biết lỗi ở bước nào.

## 10. Quy tắc quản trị label cho từng môi trường

Một chính sách label dễ vận hành có thể như sau:

| Môi trường | Cách chọn label gợi ý | Lý do |
|---|---|---|
| Local/dev | `develop` hoặc branch cá nhân | Nhận thay đổi thường xuyên để phát triển. |
| Test/CI | Branch tích hợp hoặc commit SHA | Kiểm thử đúng nội dung đã được pipeline chọn. |
| Staging | Tag ứng viên phát hành hoặc commit SHA | Xác nhận bộ cấu hình dự kiến đưa lên production. |
| Production | Tag release được bảo vệ hoặc commit SHA | Tái lập và rollback chính xác. |

Đây là quy ước tham khảo; tổ chức cần chọn theo cách phát hành của mình. Điều quan trọng là mỗi lần triển khai phải biết chính xác label và revision Git đã được sử dụng.

Không nên để nhiều nhóm tự đặt tên tag hoặc branch không theo quy tắc. Có thể dùng mẫu như `config-release-YYYY.MM.N` hoặc gắn version cấu hình với release của ứng dụng. Tag cần được bảo vệ khỏi force-update; nếu tag bị di chuyển, tên label không còn đảm bảo cùng một nội dung.

Khi nhiều dịch vụ cần phát hành độc lập, có thể mỗi client chọn label riêng. Tuy nhiên, nếu một thay đổi cấu hình liên quan đến tương thích giữa nhiều dịch vụ, pipeline cần phối hợp các label để tránh trạng thái nửa cũ nửa mới.

## 11. Bài thực hành

### Bước 1: Thiết lập nhánh mặc định

Tạo Git repository có branch `main`. Cấu hình Config Server với `spring.cloud.config.server.git.default-label: main`, khởi động server và gọi endpoint cho một application/profile mà không truyền label.

**Kết quả cần đạt:** xác định được server chọn nhánh nào khi request bỏ trống label.

### Bước 2: Yêu cầu label tường minh

Tạo branch `feature/config-timeout`, thay đổi một giá trị trong file cấu hình và yêu cầu endpoint với label đó. So sánh phản hồi với request không truyền label.

**Kết quả cần đạt:** hiểu label từ client ghi đè lựa chọn mặc định cho request đó.

### Bước 3: Thử tag và commit SHA

Tạo tag release trên một commit, sau đó gọi endpoint bằng tag. Thử dùng commit SHA nếu backend và phiên bản đang triển khai hỗ trợ.

**Kết quả cần đạt:** phân biệt branch di động với tag/commit dùng để ghim revision.

### Bước 4: Thiết lập default label theo repository

Khai báo hai repository với branch mặc định khác nhau và pattern application tương ứng. Gọi endpoint cho mỗi ứng dụng mà không truyền label.

**Kết quả cần đạt:** xác minh default label của repository được chọn và cách nó tương tác với cấu hình toàn cục.

### Bước 5: Diễn tập đổi nhánh mặc định

Chuyển repository thử nghiệm từ `master` sang `main`, cập nhật cấu hình server và kiểm tra cả client không khai báo label lẫn client đã ghim label.

**Kết quả cần đạt:** biết client nào chịu ảnh hưởng khi default label phía server thay đổi.

## 12. Tự kiểm tra

1. `spring.cloud.config.label` và `spring.cloud.config.server.git.default-label` khác nhau ở đâu?
2. Khi client không gửi label, Config Server chọn label nào?
3. Khi client gửi label tường minh, default label có còn được dùng cho request đó không?
4. Branch, tag và commit SHA khác nhau thế nào về tính ổn định?
5. Vì sao production thường nên ghim tag hoặc commit?
6. Có thể cấu hình default label riêng cho từng Git repository không, và cần xác minh điều gì theo phiên bản?
7. Những client nào chịu ảnh hưởng khi server đổi default label?
8. Làm sao xác minh label thực tế và revision Git đã được trả về?

Khi hoàn thành bài thực hành, người học có thể chọn label theo chiến lược phát hành, cấu hình nhánh mặc định ở Config Server, xử lý nhiều repository và xác định chính xác phiên bản cấu hình mà từng client đang sử dụng.
