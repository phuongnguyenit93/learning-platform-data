# Khi nào cần kết hợp nhiều EnvironmentRepository

Spring Cloud Config Server lấy cấu hình thông qua một `EnvironmentRepository`. Backend đơn có thể đọc từ Git, filesystem, Vault hoặc một nguồn được hỗ trợ khác. Trong hệ thống nhiều ứng dụng, một backend duy nhất đôi khi không đáp ứng được tất cả nhu cầu: cấu hình chung nằm trong Git, cấu hình riêng của một nhóm nằm ở repository khác, còn bí mật được quản lý trong secret store. Khi đó, Config Server có thể kết hợp nhiều `EnvironmentRepository` thành một kết quả `Environment` thông qua **composite environment repository**.

Composite repository phù hợp khi các nguồn cấu hình cần được phân phối qua cùng một API và cùng bộ ba application, profile, label. Tuy nhiên, càng kết hợp nhiều backend thì thứ tự ưu tiên, khả năng truy cập, xử lý lỗi và quyền sở hữu cấu hình càng cần được xác định rõ.

## 1. EnvironmentRepository là gì?

`EnvironmentRepository` là thành phần phía Config Server chịu trách nhiệm tìm cấu hình cho một yêu cầu. Client gửi application, profile và label; repository dùng các thông tin này để tìm các property source phù hợp và trả về một `Environment`.

Một số backend thường gặp:

| Backend | Nguồn dữ liệu | Trường hợp sử dụng |
| --- | --- | --- |
| Git | Repository Git | Cấu hình có lịch sử commit, review và phát hành theo branch/tag |
| Native | File system hoặc classpath | Cấu hình cục bộ, môi trường phát triển hoặc cấu hình được mount vào server |
| Vault | Secret store HashiCorp Vault | Bí mật, credential và dữ liệu cần kiểm soát truy cập tập trung |
| JDBC | Cơ sở dữ liệu quan hệ | Cấu hình được quản trị qua bảng dữ liệu |
| SVN | Repository Subversion | Hệ thống còn sử dụng quy trình quản lý cấu hình bằng SVN |

Mỗi backend có cách xác thực, cách chọn revision và yêu cầu vận hành riêng. Composite repository cho phép nhiều backend cùng đóng góp property source vào một phản hồi thay vì bắt tất cả dữ liệu phải nằm trong cùng một loại lưu trữ.

## 2. Khi nào nên kết hợp nhiều repository?

Kết hợp nhiều `EnvironmentRepository` hữu ích khi có một ranh giới rõ ràng giữa các nhóm cấu hình:

1. **Cấu hình dùng chung và cấu hình theo nhóm dịch vụ:** một Git repository lưu giá trị chung; repository khác lưu cấu hình riêng của nhóm thanh toán hoặc kiểm kê.
2. **Cấu hình ứng dụng và cấu hình tại môi trường triển khai:** Git lưu cấu hình có thể review; native repository cung cấp một số giá trị được mount tại máy chủ hoặc container.
3. **Cấu hình thông thường và bí mật:** Git lưu timeout, feature flag hoặc endpoint không nhạy cảm; Vault cung cấp password, token hoặc credential.
4. **Di chuyển backend theo giai đoạn:** một nguồn mới có thể được đưa vào composite trong lúc hệ thống chuyển dần khỏi backend cũ, nếu thứ tự ưu tiên và hành vi trùng khóa đã được kiểm soát.
5. **Phân chia quyền sở hữu:** các nhóm có thể quản trị repository riêng với quyền đọc và vòng đời thay đổi khác nhau, trong khi ứng dụng vẫn truy vấn qua một Config Server.

Không nên thêm backend chỉ để gom thêm một tệp cấu hình nhỏ nếu lợi ích không bù được chi phí vận hành. Mỗi repository mới tạo thêm dependency về mạng, xác thực, tính sẵn sàng, giám sát và xử lý lỗi. Nếu một nguồn có thể được tổ chức rõ ràng trong repository hiện có mà không làm mất ranh giới bảo mật hoặc vòng đời, một backend đơn giản thường dễ vận hành hơn.

## 3. Bật composite environment repository

Để dùng danh sách repository tổng hợp, Config Server kích hoạt profile `composite` và khai báo từng backend trong `spring.cloud.config.server.composite`.

Ví dụ kết hợp hai Git repository và một native repository:

```yaml
server:
  port: 8888

spring:
  application:
    name: configuration-server
  profiles:
    active: composite
  cloud:
    config:
      server:
        composite:
          - type: git
            uri: https://git.example.com/platform/billing-config.git
            default-label: main
            clone-on-start: true
          - type: git
            uri: https://git.example.com/platform/shared-config.git
            default-label: main
            clone-on-start: true
          - type: native
            search-locations:
              - file:/etc/config-server/defaults
```

Trong ví dụ:

- Repository Git thứ nhất cung cấp cấu hình riêng cho nhóm billing.
- Repository Git thứ hai cung cấp cấu hình dùng chung.
- Native repository cung cấp các giá trị mặc định có sẵn trên filesystem của Config Server.
- `type` chỉ rõ loại `EnvironmentRepository` mà mỗi phần tử sử dụng.
- Các thuộc tính còn lại được cấu hình theo backend tương ứng, chẳng hạn `uri`, `default-label`, `clone-on-start` hoặc `search-locations`.

Profile `composite` cho Config Server biết cần tạo composite repository. Mỗi phần tử trong danh sách được khởi tạo theo loại backend đã khai báo. Hãy bảo đảm dependency tương ứng đã có trong ứng dụng server và cấu hình của từng backend hợp lệ.

## 4. Thứ tự repository quyết định ưu tiên

Khi nhiều repository cùng cung cấp một khóa, thứ tự của các nguồn quyết định giá trị nào được ưu tiên trong kết quả composite. Theo cách sắp xếp thông thường của composite repository, property source từ repository đứng trước có ưu tiên cao hơn property source từ repository đứng sau.

Giả sử ba repository trả về:

```yaml
# billing-config.git
acme:
  billing:
    connect-timeout: 4s
```

```yaml
# shared-config.git
acme:
  billing:
    connect-timeout: 2s
    currency: VND
```

```yaml
# native defaults
acme:
  billing:
    connect-timeout: 1s
    retry:
      max-attempts: 3
```

Với thứ tự khai báo billing, shared, native như ví dụ trước, giá trị `connect-timeout` từ repository billing đứng trước sẽ được ưu tiên. `currency` vẫn đến từ repository shared vì billing không khai báo khóa đó. `retry.max-attempts` đến từ native vì hai nguồn đứng trước không cung cấp khóa này.

Thứ tự ưu tiên chỉ có ý nghĩa khi các repository cùng cung cấp một khóa. Nó không có nghĩa toàn bộ nội dung của repository đứng trước xóa các khóa chỉ tồn tại trong repository phía sau. Các khóa không trùng vẫn có thể được hợp nhất vào `Environment`.

Để tránh nhầm lẫn, hãy dùng một khóa thử nghiệm có giá trị khác nhau ở mỗi repository, gọi API Config Server và kiểm tra thứ tự `propertySources` cùng giá trị tương ứng. Không nên suy luận ưu tiên chỉ từ tên repository hoặc cấu trúc Git.

## 5. Giữ ranh giới theo application bằng pattern

Trong hệ thống nhiều nhóm, không phải repository nào cũng cần phục vụ mọi application. Composite repository hỗ trợ cấu hình pattern để giới hạn những ứng dụng mà một repository áp dụng. Ví dụ, một repository chỉ phục vụ các ứng dụng có tên bắt đầu bằng `billing-`:

```yaml
spring:
  profiles:
    active: composite
  cloud:
    config:
      server:
        composite:
          - type: git
            uri: https://git.example.com/platform/billing-config.git
            pattern: billing-*
          - type: git
            uri: https://git.example.com/platform/shared-config.git
```

Pattern giúp chọn repository theo application name. Khi nhiều pattern có thể khớp cùng một ứng dụng, cần kiểm tra quy tắc matching và kết quả thực tế của phiên bản đang dùng. Không dùng pattern như một ranh giới bảo mật: quyền đọc repository vẫn phải được thiết lập ở Git/Vault và Config Server phải được bảo vệ bằng xác thực, phân quyền và mạng.

## 6. Label và khả năng tương thích giữa các nguồn

Với Git backend, label thường là branch, tag hoặc commit. Khi một request composite mang label, các Git repository tham gia cần có khả năng giải quyết label đó. Nếu một repository không có branch/tag được yêu cầu hoặc không thể checkout revision, toàn bộ request có thể gặp lỗi.

Do đó, khi kết hợp nhiều Git repository, nên thống nhất chiến lược label:

- Tạo cùng tên branch hoặc tag phát hành ở các repository cần phát hành đồng bộ.
- Ghi nhận commit SHA riêng của từng repository nếu cần tái lập chính xác toàn bộ tập cấu hình.
- Kiểm tra quyền đọc và khả năng checkout label ở tất cả repository trước khi rollout.
- Xác định cách xử lý khi một repository cập nhật chậm hơn các repository còn lại.

Không phải backend nào cũng có khái niệm label giống Git. Native repository chủ yếu đọc từ vị trí cấu hình đã khai báo; Vault hoặc JDBC có cách phân vùng dữ liệu riêng. Vì vậy, cần kiểm tra semantics của từng backend thay vì giả định label có ý nghĩa giống nhau ở mọi nguồn.

## 7. Điều gì xảy ra khi một repository bị lỗi?

Theo mặc định, composite repository thường coi lỗi từ một repository thành phần là lỗi của yêu cầu tổng hợp. Ví dụ, Git shared hoạt động nhưng Git billing không truy cập được thì request composite có thể thất bại, dù một phần cấu hình vẫn đọc được.

Trong các phiên bản hỗ trợ, có thể cấu hình `spring.cloud.config.server.fail-on-composite-error: false` để cho phép bỏ qua lỗi từ một repository thành phần và tiếp tục với các nguồn còn lại:

```yaml
spring:
  cloud:
    config:
      server:
        fail-on-composite-error: false
```

Đây là lựa chọn có ảnh hưởng trực tiếp đến tính đầy đủ của cấu hình. Nếu repository billing chứa timeout hoặc endpoint bắt buộc, bỏ qua lỗi của nó có thể khiến ứng dụng nhận giá trị mặc định từ repository khác hoặc thiếu thuộc tính cần thiết. Khi cân nhắc chế độ tiếp tục một phần, cần xác định rõ backend nào có thể bỏ qua, khóa nào bắt buộc, cách phát hiện response thiếu nguồn và cách cảnh báo.

Không nên coi `fail-on-composite-error: false` là cơ chế tự động fallback an toàn. Nó có thể giúp một số ứng dụng vẫn nhận được cấu hình trong tình huống suy giảm, nhưng cũng có thể che giấu lỗi backend và làm thay đổi giá trị cuối cùng. Hãy kiểm thử với đúng phiên bản Spring Cloud Config và dùng validation ở Config Client để từ chối cấu hình thiếu các thuộc tính bắt buộc.

## 8. Bảo mật khi kết hợp Git và secret store

Một lý do quan trọng để dùng composite là tách cấu hình thường khỏi bí mật. Ví dụ, Git có thể chứa:

```yaml
acme:
  billing:
    endpoint: https://billing.internal.example
    connect-timeout: 4s
```

Vault hoặc secret manager cung cấp password và token cho ứng dụng. Cách tổ chức này giúp credential có chính sách truy cập, audit và xoay vòng riêng. Tuy nhiên, sau khi Config Server tổng hợp các nguồn, phản hồi API vẫn có thể chứa dữ liệu nhạy cảm. Composite không tự động che hoặc bảo vệ bí mật.

Các nguyên tắc cần giữ:

- Cấp quyền đọc riêng cho từng repository và secret path.
- Dùng TLS và xác thực giữa Config Client với Config Server, cũng như giữa Config Server với backend.
- Không commit password, token hoặc private key trong Git.
- Không đưa giá trị bí mật vào log, trace, response mẫu hoặc báo cáo chẩn đoán.
- Giới hạn endpoint Config Server theo application và nhóm client được phép truy cập.
- Kiểm tra chính sách masking và quyền truy cập của Actuator/endpoint quản trị.

Nếu nhiều nhóm dùng chung một Config Server nhưng có quyền bí mật khác nhau, cần xác minh khả năng phân quyền ở tầng Config Server hoặc triển khai các server/repository tách biệt. Việc ghép nhiều backend vào một response không tự tạo ra ranh giới truy cập theo từng client.

## 9. Kiểm tra response composite

Sau khi khởi động Config Server, gọi endpoint cho một application đại diện:

```bash
curl -i "http://localhost:8888/billing-api/prod/main"
```

Kiểm tra các trường metadata và `propertySources`:

1. `name`, `profiles` và `label` có đúng với request không?
2. `propertySources` có chứa nguồn từ tất cả backend dự kiến không?
3. Tên property source có giúp xác định repository hoặc vị trí nguồn không?
4. Với khóa trùng, repository nào đứng trước và giá trị nào được chọn?
5. Nếu một backend bị ngắt, HTTP response và log có thể hiện lỗi hoặc nguồn bị bỏ qua không?
6. `version` có được cung cấp không; nếu có nhiều Git repository, cần ghi nhận revision của từng nguồn nếu metadata cho phép.

Ví dụ kiểm tra khóa trùng bằng `jq`:

```bash
curl -sS "http://localhost:8888/billing-api/prod/main" \
  | jq '.propertySources[] | {name, value: .source["acme.billing.connect-timeout"]}'
```

Lệnh này hiển thị nguồn nào cung cấp `acme.billing.connect-timeout` và giá trị tại từng nguồn. Chỉ chia sẻ output đã loại bỏ thông tin nhạy cảm.

## 10. Quy trình kiểm thử lỗi một backend

Trong môi trường thử nghiệm riêng, có thể xác minh hành vi composite theo trình tự:

1. Khởi tạo ít nhất hai repository có cùng một khóa nhưng giá trị khác nhau.
2. Gọi endpoint khi cả hai backend hoạt động; xác nhận thứ tự property source và giá trị ưu tiên.
3. Ngắt một backend bằng cách dừng dịch vụ thử nghiệm hoặc thu hồi credential thử nghiệm.
4. Gọi lại endpoint và ghi HTTP status, lỗi trong log, property source còn lại và giá trị cuối cùng.
5. Lặp lại với `fail-on-composite-error` ở chế độ mặc định và chế độ bỏ qua lỗi nếu phiên bản hỗ trợ.
6. Khôi phục backend, xác nhận request tiếp theo có đầy đủ property source.
7. Khởi động Config Client mới và kiểm tra validation để chắc chắn ứng dụng không khởi động với cấu hình bắt buộc bị thiếu.

Không thực hiện thao tác ngắt mạng hoặc thu hồi credential trên repository production. Dùng dữ liệu không nhạy cảm, backend riêng và log đã che thông tin xác thực.

## 11. Những đánh đổi khi vận hành composite

| Khía cạnh | Lợi ích | Chi phí/rủi ro |
| --- | --- | --- |
| Tách nguồn dữ liệu | Mỗi loại cấu hình dùng backend phù hợp | Nhiều kết nối, credential và chính sách vận hành |
| Thứ tự ưu tiên | Có thể ghi đè giá trị chung bằng cấu hình chuyên biệt | Dễ gây nhầm lẫn nếu khóa trùng mà không có quy ước |
| Nhiều Git repository | Nhóm có quyền sở hữu và lịch sử thay đổi riêng | Đồng bộ label/revision phức tạp hơn |
| Bỏ qua lỗi một nguồn | Có thể duy trì một phần chức năng | Cấu hình trả về có thể thiếu hoặc đổi giá trị ngoài dự kiến |
| Tách secret store | Tăng khả năng audit và xoay vòng bí mật | Config Server vẫn cần quyền truy cập bí mật và phải bảo vệ response |

Composite cũng làm tăng độ trễ request nếu nhiều backend phải được truy cập hoặc refresh. Cần đo thời gian phản hồi, số lần fetch, lỗi từng backend và tỷ lệ response thiếu nguồn. Đặt timeout, retry và circuit breaker theo khả năng của từng backend, nhưng tránh retry dồn dập làm tăng tải khi một repository đang lỗi.

## 12. Khi nào nên dùng composite và khi nào nên tách Config Server?

Dùng composite khi các nguồn cần được hợp nhất cho cùng nhóm client, có thể áp dụng chung chính sách xác thực và có thứ tự ưu tiên rõ ràng. Dùng Config Server hoặc deployment tách biệt khi các nhóm ứng dụng cần ranh giới truy cập khác nhau, có yêu cầu cô lập sự cố hoặc có vòng đời phát hành độc lập đến mức việc hợp nhất gây khó kiểm soát.

Trước khi thêm repository, hãy trả lời:

- Nguồn mới cung cấp khóa hoặc loại dữ liệu nào?
- Có khóa nào trùng với nguồn hiện tại không, và nguồn nào phải thắng?
- Label, profile và application được ánh xạ thế nào ở backend mới?
- Điều gì xảy ra nếu backend mới offline hoặc trả về dữ liệu thiếu?
- Ai sở hữu credential, review thay đổi và xử lý sự cố?
- Client nào được phép nhận dữ liệu từ nguồn này?

## 13. Checklist triển khai

- [ ] Đã xác định lý do nghiệp vụ cần nhiều `EnvironmentRepository`.
- [ ] Đã bật profile `composite` và thêm dependency cho từng backend.
- [ ] Đã khai báo URI, search path, label và credential riêng cho từng nguồn.
- [ ] Đã xác định thứ tự ưu tiên và kiểm tra khóa trùng bằng response thực tế.
- [ ] Đã thống nhất label/revision cho các Git repository cần phát hành đồng bộ.
- [ ] Đã quyết định cách xử lý khi một backend lỗi; không bật bỏ qua lỗi nếu chưa đánh giá cấu hình thiếu.
- [ ] Đã kiểm tra quyền đọc, TLS, secret store và bảo vệ response.
- [ ] Đã thử backend offline, response thiếu nguồn và validation ở Config Client.
- [ ] Đã thiết lập log, metric và cảnh báo theo từng backend.

Kết hợp nhiều `EnvironmentRepository` giúp Config Server tập hợp cấu hình từ những nơi có vòng đời và mục đích khác nhau. Lợi ích chỉ bền vững khi nhóm kiểm soát được thứ tự ưu tiên, khả năng tương thích label, hành vi lỗi và quyền truy cập. Một composite repository được thiết kế tốt sẽ làm rõ nguồn gốc của từng giá trị và giúp việc phân phối cấu hình giữa nhiều ứng dụng Spring Boot nhất quán hơn.
