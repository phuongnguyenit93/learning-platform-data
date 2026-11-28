# Chọn một kho Git hay nhiều kho theo ranh giới sở hữu

Khi nhiều ứng dụng Spring Boot lấy cấu hình từ Spring Cloud Config Server, nhóm cần quyết định cấu hình sẽ nằm trong một Git repository dùng chung hay được chia thành nhiều repository theo dịch vụ, nhóm hoặc miền nghiệp vụ. Quyết định này ảnh hưởng đến quyền sở hữu, quyền truy cập, cách review thay đổi, khả năng rollback và độ phức tạp khi vận hành Config Server.

Không có một cách tổ chức phù hợp cho mọi hệ thống. Một kho tập trung thường dễ bắt đầu và thuận tiện khi một nhóm nền tảng quản trị cấu hình cho toàn hệ thống. Nhiều kho phù hợp hơn khi các nhóm có quyền sở hữu, lịch phát hành hoặc yêu cầu truy cập độc lập. Điều quan trọng là ranh giới repository phải phản ánh cách tổ chức và chịu trách nhiệm thực tế, đồng thời cách Config Server định tuyến yêu cầu phải dễ hiểu và kiểm chứng.

## 1. Repository cấu hình cần giải quyết những gì?

Một repository cấu hình là nơi lưu các file mà Config Server đọc để trả cấu hình cho Config Client. Nội dung thường gồm cấu hình dùng chung, cấu hình theo tên ứng dụng và cấu hình theo profile. Ví dụ:

```text
config-repository/
├── application.yml
├── order-service.yml
├── order-service-dev.yml
├── order-service-prod.yml
├── inventory-service.yml
└── inventory-service-prod.yml
```

Trong ví dụ này, `application.yml` có thể chứa các giá trị mặc định dùng chung; `order-service.yml` và `inventory-service.yml` chứa cấu hình riêng của từng ứng dụng; các file có hậu tố profile mô tả khác biệt theo môi trường.

Repository cần hỗ trợ ít nhất các nhu cầu sau:

- **Sở hữu rõ ràng:** biết nhóm hoặc người chịu trách nhiệm cho từng thay đổi cấu hình.
- **Review phù hợp:** thay đổi được xem xét bởi người hiểu tác động của ứng dụng và môi trường.
- **Quyền truy cập:** chỉ những danh tính cần thiết mới có thể đọc hoặc thay đổi cấu hình.
- **Lịch sử và rollback:** xác định được phiên bản cấu hình đã được triển khai và cách quay lại phiên bản trước.
- **Phân phối dự đoán được:** Config Server tìm đúng file theo application, profile và label.
- **Khả năng vận hành:** cấu trúc repository, nhánh, thẻ và thông tin xác thực có thể được duy trì khi số ứng dụng tăng lên.

Git cung cấp lịch sử commit, branch, tag và cơ chế review thông qua nền tảng lưu trữ. Tuy nhiên, chỉ tạo repository không tự động tạo ra quyền sở hữu hay quy trình phê duyệt. Những điều này cần được quy định trong quyền repository, quy tắc bảo vệ nhánh và quy trình triển khai.

## 2. Một repository tập trung

Với mô hình một kho, các ứng dụng dùng chung một repository cấu hình. Config Server đọc một Git URI và chọn file theo tên ứng dụng, profile và label.

Ví dụ cấu hình Config Server:

```yaml
server:
  port: 8888

spring:
  cloud:
    config:
      server:
        git:
          uri: https://git.example.com/platform/config-repository.git
          default-label: main
```

Các file có thể được tổ chức theo quy ước tên của Spring Cloud Config như `application.yml`, `{application}.yml` và `{application}-{profile}.yml`. Cấu trúc này giúp người vận hành tìm được file cấu hình của dịch vụ mà không cần duy trì một Git URI cho từng ứng dụng.

### Ưu điểm

- Một nơi để tìm kiếm, review và kiểm tra thay đổi cấu hình của toàn hệ thống.
- Dễ chia sẻ giá trị mặc định qua `application.yml` và giảm việc sao chép cấu hình chung.
- Config Server có cấu hình Git đơn giản, ít thông tin xác thực và ít quy tắc định tuyến.
- Có thể xem nhiều thay đổi liên quan trong cùng một pull request hoặc commit, thuận tiện khi một đợt triển khai cần cập nhật nhiều dịch vụ đồng thời.
- Dễ áp dụng quy ước chung về tên file, profile, label, kiểm tra cú pháp và quy trình phát hành.

### Hạn chế

- Quyền đọc và ghi ở cấp repository có thể quá rộng nếu nhiều nhóm cùng sử dụng nhưng không được phép xem hoặc sửa cấu hình của nhau.
- Thay đổi ở một khu vực có thể ảnh hưởng dịch vụ khác nếu cấu hình chung bị sửa mà không kiểm tra đầy đủ.
- Quy trình review dễ trở thành nút thắt nếu mọi thay đổi phải qua một nhóm nền tảng duy nhất.
- Lịch sử commit chứa thay đổi của nhiều ứng dụng, nên việc xác định phạm vi tác động của một commit cần quy ước rõ.
- Một repository lớn với nhiều profile và file trùng tên có thể khó điều hướng nếu không có cấu trúc và quy tắc đặt tên nhất quán.

Mô hình tập trung phù hợp khi tổ chức có nhóm nền tảng chịu trách nhiệm chung, các nhóm được phép đọc cùng một phạm vi cấu hình và quy trình phát hành có thể phối hợp. Đây cũng thường là lựa chọn đơn giản cho hệ thống mới có ít dịch vụ.

## 3. Nhiều repository theo nhóm hoặc miền nghiệp vụ

Trong mô hình nhiều kho, mỗi nhóm hoặc miền nghiệp vụ quản lý repository riêng. Ví dụ:

```text
platform-config/
├── application.yml
└── platform-defaults.yml

orders-config/
├── order-service.yml
├── order-service-dev.yml
└── order-service-prod.yml

inventory-config/
├── inventory-service.yml
└── inventory-service-prod.yml
```

Config Server có thể khai báo nhiều Git repository và chọn repository theo pattern của tên ứng dụng hoặc profile:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          repos:
            orders:
              pattern: order-service
              uri: https://git.example.com/orders/orders-config.git
              default-label: main
            inventory:
              pattern: inventory-service
              uri: https://git.example.com/supply/inventory-config.git
              default-label: main
```

Đây là ví dụ minh họa cách khai báo nhiều repository; pattern thực tế cần được thiết kế theo cú pháp mà phiên bản Spring Cloud Config đang sử dụng hỗ trợ và phải được kiểm tra với các request application/profile cụ thể. Khi có nhiều repository, hãy ghi lại quy tắc định tuyến và bảo đảm mỗi ứng dụng khớp với repository dự kiến.

### Ưu điểm

- Nhóm sở hữu dịch vụ có thể review và phát hành cấu hình theo lịch riêng.
- Quyền đọc và ghi có thể được cấp theo repository, phù hợp hơn khi các nhóm có ranh giới truy cập khác nhau.
- Lịch sử và rollback của một dịch vụ ít bị trộn với thay đổi của dịch vụ khác.
- Nhóm có thể áp dụng quy trình kiểm thử hoặc bảo vệ nhánh phù hợp với mức độ rủi ro của miền nghiệp vụ.
- Repository của một nhóm có thể được duy trì độc lập mà không buộc mọi nhóm cùng thay đổi cấu trúc kho trung tâm.

### Hạn chế

- Config Server phải quản lý nhiều URI, pattern, nhánh mặc định và thông tin xác thực hơn.
- Cần có quy ước thống nhất để tránh cùng một ứng dụng bị định tuyến nhầm hoặc không khớp repository nào.
- Cấu hình dùng chung có thể bị sao chép giữa các kho và dần không đồng nhất.
- Một thay đổi liên quan nhiều dịch vụ có thể cần nhiều pull request và nhiều lần triển khai, làm tăng công việc phối hợp.
- Cần theo dõi trạng thái truy cập, clone, cache và khả năng sẵn sàng của nhiều Git repository.

Nhiều repository phù hợp khi ranh giới sở hữu và quyền truy cập thực sự độc lập. Chia kho chỉ để mỗi ứng dụng có một repository có thể làm tăng đáng kể chi phí quản trị mà không mang lại lợi ích tương xứng.

## 4. Không nhầm định tuyến repository với việc ghép nhiều lớp cấu hình

Một điểm thiết kế quan trọng là Config Server chọn repository để phục vụ một yêu cầu theo cấu hình định tuyến. Không nên mặc định rằng khai báo hai repository riêng có nghĩa Config Server sẽ tự động ghép `application.yml` ở kho thứ nhất với `order-service-prod.yml` ở kho thứ hai cho cùng một request.

Nếu cần cấu hình chung và cấu hình riêng cùng xuất hiện trong kết quả, hãy chọn một thiết kế có hành vi ghép được xác định rõ:

- Giữ các file chung và file riêng trong cùng repository, dùng quy ước tên file/profile của Config Server.
- Tổ chức file theo thư mục và dùng `searchPaths` khi cấu trúc kho cần phân vùng theo ứng dụng hoặc nhóm.
- Nếu cần tổng hợp từ nhiều backend hoặc repository độc lập, nghiên cứu và cấu hình rõ cơ chế composite environment repository được phiên bản Spring Cloud Config hỗ trợ; kiểm tra thứ tự property source và hành vi khi một backend lỗi.

Ví dụ, với một repository duy nhất, file `application.yml` có thể chứa giá trị mặc định chung, còn `order-service-prod.yml` chứa giá trị production. Config Server trả các property source theo mô hình chuẩn, và Spring Boot áp dụng thứ tự ưu tiên tương ứng. Với nhiều repository độc lập, cần kiểm tra response thực tế thay vì giả định có cùng cơ chế kế thừa.

Đừng tạo một kho `common-config` riêng rồi kỳ vọng mọi ứng dụng tự động đọc nó cùng kho riêng của mình. Nếu muốn tái sử dụng cấu hình chung, hãy chọn một cơ chế được hỗ trợ, định nghĩa rõ nguồn nào ưu tiên hơn và kiểm thử trường hợp trùng khóa. Đối với các giá trị quan trọng như timeout, endpoint hoặc feature flag, sự mơ hồ về nguồn thắng có thể gây lỗi vận hành khó truy vết.

## 5. Chọn ranh giới theo quyền sở hữu và trách nhiệm

Ranh giới tốt thường trùng với nơi một nhóm có thể chịu trách nhiệm trọn vẹn cho thay đổi cấu hình. Hãy xem xét các câu hỏi sau trước khi tách repository:

| Câu hỏi | Gợi ý thiết kế |
|---|---|
| Ai chịu trách nhiệm phê duyệt thay đổi? | Nếu một nhóm chịu trách nhiệm chung, một kho tập trung có thể phù hợp. Nếu nhiều nhóm có quyền quyết định độc lập, cân nhắc tách kho. |
| Nhóm có được phép đọc cấu hình của nhau không? | Nếu có yêu cầu hạn chế quyền đọc, cần ranh giới truy cập thực sự và chính sách bảo vệ Config Server tương ứng. |
| Các dịch vụ có cùng lịch phát hành cấu hình không? | Lịch phát hành độc lập là lý do hợp lý để tách kho. |
| Các thay đổi có thường xuyên phải đồng bộ nhiều dịch vụ không? | Nếu có, một kho chung hoặc quy trình phối hợp nhiều kho rõ ràng sẽ giảm rủi ro lệch phiên bản. |
| Ai vận hành thông tin xác thực và kết nối Git? | Càng nhiều kho, càng cần quy trình quản lý credential, rotation và giám sát kết nối. |
| Có thể rollback một nhóm dịch vụ độc lập không? | Nếu rollback độc lập là yêu cầu, label hoặc commit của từng ranh giới cần được ghi nhận riêng. |

Không nên lấy số lượng ứng dụng làm tiêu chí duy nhất. Mười dịch vụ do cùng một nhóm sở hữu có thể quản lý tốt trong một repository. Ngược lại, hai miền dữ liệu có yêu cầu bảo mật và chủ sở hữu khác nhau có thể cần hai repository riêng ngay cả khi mỗi miền chỉ có một dịch vụ.

### Ví dụ lựa chọn

**Một nhóm nền tảng quản lý cấu hình cho toàn bộ dịch vụ nội bộ.** Nếu các nhóm ứng dụng được phép đọc cấu hình lẫn nhau và thay đổi đều đi qua quy trình review chung, một repository có file theo tên ứng dụng và profile thường đủ đơn giản.

**Các nhóm thanh toán và kho vận có quyền truy cập độc lập.** Nếu nhóm thanh toán không được xem cấu hình riêng của kho vận, hai repository riêng có thể hỗ trợ phân quyền ở Git. Config Server vẫn cần được bảo vệ để client của nhóm này không thể tùy ý yêu cầu cấu hình của nhóm khác. Tách repository một mình chưa tạo ra chính sách phân quyền ở API.

**Một thay đổi chung cần triển khai đồng thời cho nhiều dịch vụ.** Nếu các dịch vụ phải chuyển sang cùng một endpoint trong một đợt phát hành, một repository chung có thể giúp review các thay đổi trong cùng một commit. Nếu đã tách nhiều repository, cần quy trình phát hành phối hợp và ghi nhận rõ commit/label của từng kho.

## 6. Cấu trúc file, search path và quy ước tên

Dù dùng một hay nhiều repository, cách đặt tên file phải giúp Config Server tìm được cấu hình theo application và profile. Một cấu trúc đơn giản có thể là:

```text
orders-config/
├── application.yml
├── order-service.yml
├── order-service-dev.yml
├── order-service-staging.yml
└── order-service-prod.yml
```

Nếu repository có nhiều dịch vụ, tên ứng dụng cần nhất quán với `spring.application.name` của Config Client. Profile nên phản ánh môi trường hoặc mục đích chạy đã được thống nhất, ví dụ `dev`, `staging`, `prod`; tránh tạo nhiều profile có ý nghĩa gần giống nhau nhưng không có quy tắc sử dụng.

`searchPaths` cho phép Config Server tìm file trong các thư mục con của repository. Tính năng này hữu ích khi nhóm muốn bố trí file theo nhóm hoặc theo ứng dụng. Tuy nhiên, cần tránh cấu trúc lồng quá sâu hoặc có nhiều file cùng tên trong các thư mục được tìm đồng thời. Khi nhiều vị trí có cùng khóa, thứ tự property source có thể làm kết quả khó đoán nếu không được kiểm tra.

Quy ước đặt tên nên bao gồm:

- Tên ứng dụng khớp với `spring.application.name`.
- Profile có danh sách được quản lý, tránh tùy tiện tạo alias.
- File dùng chung chỉ chứa thuộc tính thật sự dùng chung và có default an toàn.
- File riêng ứng dụng chỉ chứa giá trị thuộc quyền sở hữu của ứng dụng đó.
- Không lưu mật khẩu, token, private key hoặc bí mật dạng rõ trong Git.
- Tài liệu hóa các file, thư mục và search path mà Config Server dùng để phân giải một request.

## 7. Quản lý label, branch và phiên bản cấu hình

Config Server sử dụng label để chọn phiên bản của repository, thường là tên branch, tag hoặc commit Git. Label mặc định như `main` thuận tiện khi phát triển, nhưng nội dung của branch có thể thay đổi theo thời gian.

Với môi trường production cần tái lập, nên ghi nhận label cụ thể được triển khai. Có thể dùng tag phát hành hoặc commit đã được phê duyệt, tùy chính sách của nhóm. Nếu dùng branch, cần ghi nhận commit SHA mà Config Server thực tế đã đọc tại thời điểm phát hành để hỗ trợ điều tra và rollback.

Trong mô hình một repository, một label có thể đại diện cho tập cấu hình của nhiều dịch vụ tại cùng một thời điểm. Điều này thuận tiện khi cần đồng bộ cấu hình toàn hệ thống, nhưng có thể làm một thay đổi nhỏ kéo theo việc tạo phiên bản mới cho toàn kho.

Trong mô hình nhiều repository, mỗi kho có lịch sử và label riêng. Một bản phát hành liên quan nhiều dịch vụ cần lưu lại bộ nhãn hoặc commit tương ứng của từng kho. Không nên chỉ ghi “đã triển khai config version 12” nếu không thể xác định version 12 thuộc repository nào.

Hãy giữ các nguyên tắc sau:

- Bảo vệ nhánh dùng làm nguồn cấu hình production.
- Yêu cầu review cho thay đổi ảnh hưởng môi trường production.
- Không sửa tag đã phát hành để trỏ sang nội dung khác.
- Lưu lại label/commit cùng phiên bản ứng dụng trong hồ sơ triển khai.
- Kiểm tra rollback bằng cách đưa ứng dụng về label/commit cấu hình đã biết là tốt.

## 8. Quyền truy cập và bảo vệ bí mật

Git repository cấu hình thường chứa endpoint nội bộ, tên tài nguyên, giới hạn vận hành và thông tin về kiến trúc hệ thống. Những dữ liệu này có thể nhạy cảm ngay cả khi không phải mật khẩu. Cần cấp quyền theo nguyên tắc tối thiểu và phân biệt quyền đọc với quyền ghi.

Config Server thường dùng credential riêng để đọc Git. Credential này cần được cấp qua secret manager hoặc cơ chế bảo mật của nền tảng triển khai, giới hạn quyền ở các repository cần thiết và có quy trình xoay vòng. Không đặt username/password hoặc private key dạng rõ trong file cấu hình được commit.

Ngoài quyền ở Git, cần bảo vệ API của Config Server. Nếu client có thể yêu cầu `/{application}/{profile}/{label}` cho một tên ứng dụng bất kỳ mà không có kiểm soát, client có thể nhận cấu hình ngoài phạm vi dự kiến nếu server cho phép truy cập. Dùng Spring Security hoặc gateway/chính sách xác thực và phân quyền phù hợp để giới hạn ai được truy cập cấu hình nào. Với ranh giới bảo mật nghiêm ngặt, có thể cần các Config Server riêng hoặc một lớp kiểm soát truy cập theo ứng dụng.

Không đưa bí mật vào repository chỉ vì repository đã private. Lịch sử Git có thể giữ lại giá trị nhạy cảm sau khi file hiện tại đã được sửa. Hãy cấp mật khẩu, token và khóa mã hóa từ secret manager, Vault, KMS hoặc cơ chế quản lý bí mật của nền tảng; cấu hình Git chỉ giữ tham chiếu hoặc các giá trị không bí mật.

## 9. Vận hành Config Server khi có nhiều repository

Khi số repository tăng, Config Server phải quản lý thêm kết nối, credential, clone và cache. Một số điểm cần thiết kế trước:

**Clone và khởi động.** Config Server có thể clone repository khi cần hoặc được cấu hình clone từ sớm. Với repository quan trọng, tùy chọn clone khi khởi động giúp phát hiện sớm URI, credential hoặc lỗi truy cập, nhưng cũng có thể làm Config Server khởi động chậm hoặc phụ thuộc mạng Git ngay lúc startup. Chọn hành vi phù hợp với yêu cầu sẵn sàng.

**Cache và cập nhật.** Config Server có thể giữ bản sao local của repository để phục vụ request. Cần hiểu khi nào bản sao được fetch/pull và cách thay đổi Git xuất hiện trong response. Không giả định một commit vừa merge đã lập tức có mặt ở mọi Config Server instance; hãy xác định cơ chế refresh repository, thời gian cache và quy trình kiểm chứng.

**Credential và lỗi kết nối.** Theo dõi lỗi xác thực, lỗi DNS, timeout và repository không tồn tại. Credential cho từng kho cần được quản lý tập trung, giới hạn quyền và xoay vòng theo quy trình. Khi một kho lỗi, phải biết dịch vụ nào bị ảnh hưởng và hành vi fallback có được phép hay không.

**Tính sẵn sàng.** Config Server là một phần của đường khởi động ứng dụng nếu client bắt buộc lấy cấu hình từ xa. Triển khai nhiều instance Config Server, bảo vệ kết nối đến Git và kiểm tra khả năng truy cập từ mạng của ứng dụng. Cân nhắc hành vi của client khi server hoặc repository không sẵn sàng.

**Giám sát định tuyến.** Kiểm tra request cho từng application/profile/label để bảo đảm nó đi đến repository dự kiến. Nên có một danh sách ánh xạ được quản lý giữa tên ứng dụng, nhóm sở hữu, repository và label production.

## 10. Quy trình thay đổi và rollback

Một thay đổi cấu hình có thể làm thay đổi hành vi production mà không có lần build mã nguồn mới. Vì vậy, repository nên có quy trình review và phát hành tương xứng với rủi ro:

1. Người sở hữu tạo branch và thay đổi file cấu hình thuộc phạm vi được giao.
2. Kiểm tra cú pháp YAML/properties, tên khóa, kiểu dữ liệu và các giá trị bắt buộc.
3. Review tác động đến application, profile, các giá trị chung và dịch vụ phụ thuộc.
4. Kiểm tra response Config Server cho đúng application/profile/label trước khi triển khai.
5. Merge thay đổi theo quy tắc bảo vệ nhánh; ghi nhận commit hoặc tag được duyệt.
6. Triển khai hoặc refresh client theo quy trình; quan sát log, lỗi, độ trễ và các chỉ số liên quan.
7. Nếu có vấn đề, quay lại label/commit đã biết là tốt và xác minh cấu hình hiệu lực sau rollback.

Với một repository tập trung, một pull request có thể bao gồm thay đổi cho nhiều dịch vụ. Cần liệt kê các dịch vụ chịu ảnh hưởng và xác nhận chủ sở hữu của từng dịch vụ đã review. Với nhiều repository, thay đổi liên quan nhiều miền cần có một kế hoạch phát hành chung ghi lại commit của từng kho và thứ tự triển khai.

Không nên dùng một nhánh đang phát triển làm nguồn production nếu nội dung có thể thay đổi ngoài quy trình phát hành. Cũng không nên xóa commit hoặc tag cũ đang được tham chiếu bởi lần triển khai hiện tại. Lịch sử cấu hình là dữ liệu quan trọng để điều tra sự cố và tái tạo trạng thái hệ thống.

## 11. Khung quyết định

Có thể bắt đầu bằng bảng định hướng sau:

| Điều kiện thực tế | Lựa chọn thường phù hợp |
|---|---|
| Một nhóm sở hữu và review hầu hết cấu hình | Một repository tập trung |
| Các nhóm có quyền đọc/ghi và lịch phát hành độc lập | Nhiều repository theo nhóm hoặc miền |
| Nhiều dịch vụ cần thay đổi cấu hình đồng bộ | Một repository chung hoặc quy trình phát hành đa kho có điều phối |
| Cần phân tách quyền truy cập mạnh | Tách repository kết hợp xác thực/phân quyền ở Config Server; cân nhắc server riêng |
| Cấu hình dùng chung nhiều và cần kế thừa rõ ràng | Một repository với file chung/riêng hoặc cơ chế composite được cấu hình và kiểm thử tường minh |
| Số dịch vụ còn ít, nhóm vận hành nhỏ | Bắt đầu với một repository và tách khi xuất hiện ranh giới sở hữu rõ ràng |

Đây là điểm khởi đầu để thảo luận, không phải quy tắc cứng. Khi tổ chức phát triển, có thể chuyển từ một kho sang nhiều kho nếu quyền sở hữu hoặc yêu cầu bảo mật thay đổi. Việc chuyển đổi cần giữ được lịch sử cần thiết, cập nhật định tuyến Config Server và kiểm tra response trước khi đổi client hoặc label production.

## 12. Nguyên tắc cần ghi nhớ

- Chọn số lượng repository theo ranh giới sở hữu, quyền truy cập và vòng đời thay đổi.
- Một repository tập trung giúp chia sẻ default và review đồng bộ; nhiều repository giúp nhóm tự chủ và phân quyền theo kho.
- Không giả định nhiều Git repository sẽ tự động ghép cấu hình thành nhiều lớp cho cùng một request.
- Dùng tên ứng dụng, profile, label và search path có quy ước để Config Server định tuyến dự đoán được.
- Bảo vệ cả Git repository lẫn API Config Server; quyền đọc Git không thay thế phân quyền cho Config Client.
- Không commit bí mật dạng rõ; cấp credential cho Config Server từ cơ chế quản lý bí mật.
- Ghi nhận commit hoặc tag đã triển khai, kiểm tra response thực tế và chuẩn bị rollback.
- Khi tách nhiều kho, quản lý mapping ứng dụng-repository-chủ sở hữu và credential như một phần của vận hành nền tảng.

Một Git repository hay nhiều repository đều có thể phục vụ Spring Cloud Config. Lựa chọn tốt là lựa chọn làm rõ ai sở hữu cấu hình, ai được phép đọc và thay đổi, cách các dịch vụ nhận đúng phiên bản, và cách nhóm điều tra hoặc rollback khi cấu hình gây sự cố. Bắt đầu từ ranh giới trách nhiệm thực tế, sau đó thiết kế cấu trúc file, định tuyến Config Server, quyền truy cập và quy trình phát hành tương ứng.
