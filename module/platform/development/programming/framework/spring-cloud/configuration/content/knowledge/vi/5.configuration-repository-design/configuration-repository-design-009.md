# Tài liệu hóa khóa cấu hình và trách nhiệm bảo trì

Một kho cấu hình Git có thể chứa hàng trăm khóa được nhiều ứng dụng Spring Boot sử dụng. Khi một giá trị thay đổi, nhóm cần biết khóa đó có ý nghĩa gì, ứng dụng nào đọc nó, môi trường nào bị ảnh hưởng, ai có quyền sửa và cách kiểm tra kết quả. Nếu chỉ nhìn tên khóa hoặc đọc mã nguồn của từng dịch vụ, việc bảo trì dễ phụ thuộc vào kiến thức cá nhân và có thể dẫn đến thay đổi sai phạm vi.

Vì vậy, thiết kế kho cấu hình Spring Cloud Config cần đi kèm tài liệu mô tả khóa và quy định trách nhiệm bảo trì. Config Server cung cấp các property source theo ứng dụng, profile và label; tài liệu của nhóm bổ sung ngữ cảnh mà bản thân các tệp YAML không thể hiện đầy đủ, như mục đích nghiệp vụ-kỹ thuật, chủ sở hữu, mức độ nhạy cảm, quy trình thay đổi và phương án quay lui.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao cần tài liệu hóa khóa cấu hình trong repository dùng chung.
- Xác định các thông tin cần ghi cho mỗi khóa: mục đích, kiểu dữ liệu, đơn vị, giá trị mặc định, phạm vi, profile, nguồn, độ nhạy cảm và tác động khi thay đổi.
- Thiết kế quy ước đặt tên và cấu trúc tài liệu sao cho người bảo trì tìm được khóa và hiểu cách sử dụng.
- Phân biệt chủ sở hữu nghiệp vụ, chủ sở hữu ứng dụng, nhóm nền tảng và người quản lý bí mật.
- Thiết lập quy trình review, kiểm tra, phát hành, refresh, quay lui và ngừng sử dụng khóa.
- Giữ tài liệu đồng bộ với mã nguồn và phiên bản cấu hình đang được triển khai.

## 2. Vì sao phải tài liệu hóa khóa cấu hình?

Tên khóa như `payment.gateway.timeout` có thể gợi ý mục đích, nhưng không cho biết timeout được tính bằng mili giây hay giây, giá trị nào được chấp nhận, dịch vụ nào sử dụng hoặc ai có quyền thay đổi. Một khóa có tên rõ vẫn có thể bị sử dụng sai nếu thiếu thông tin về ngữ cảnh.

Tài liệu tốt giúp nhóm:

- **Hiểu nhanh:** người mới biết khóa dùng để làm gì và cấu hình ở đâu.
- **Thay đổi đúng phạm vi:** người sửa biết ứng dụng, profile và môi trường chịu ảnh hưởng.
- **Giảm xung đột:** các nhóm biết ai sở hữu khóa và ai cần tham gia review.
- **Vận hành có thể dự đoán:** người trực hệ thống hiểu giá trị hợp lệ, tác động khi refresh và cách quay lui.
- **Kiểm soát bí mật:** tài liệu cho biết khóa có nhạy cảm hay không và cách lấy giá trị mà không tiết lộ secret.
- **Hỗ trợ kiểm toán:** có thể liên kết khóa với commit, ticket, người phê duyệt và lịch sử thay đổi.

Spring Cloud Config không tự sinh một danh mục đầy đủ về ý nghĩa và chủ sở hữu của mọi khóa. Config Server cung cấp cấu hình; nhóm dự án phải xây dựng và duy trì tài liệu cũng như quy trình quản trị tương ứng.

## 3. Những thông tin nên có trong tài liệu của một khóa

Mỗi khóa quan trọng nên được mô tả bằng một bộ thông tin nhất quán. Không phải khóa nào cũng cần một trang riêng; có thể dùng bảng danh mục, README theo ứng dụng hoặc tài liệu sinh tự động từ metadata. Điều quan trọng là các trường cần thiết có thể tìm thấy và được cập nhật cùng thay đổi cấu hình.

| Trường tài liệu | Nội dung cần ghi | Ví dụ minh họa |
| --- | --- | --- |
| Tên khóa | Tên đầy đủ theo dạng phân cấp | `platform.http.read-timeout` |
| Mục đích | Khóa điều khiển hành vi nào | Thời gian chờ đọc khi gọi HTTP nội bộ |
| Ứng dụng sử dụng | Tên client đọc khóa | `order-service`, `payment-service` |
| Phạm vi | Dùng chung, riêng ứng dụng hay theo môi trường | Mặc định chung, có thể override theo dịch vụ |
| Kiểu dữ liệu | Kiểu mà ứng dụng bind và mong đợi | `Duration` |
| Đơn vị/định dạng | Cách biểu diễn giá trị | `2s`, `500ms` |
| Giá trị mặc định | Giá trị mặc định trong repository hoặc trong mã | `5s` trong `application.yml` |
| Bắt buộc | Ứng dụng có thể chạy khi thiếu khóa không | Có, phải cung cấp ở môi trường sản xuất |
| Miền giá trị | Giới hạn và giá trị được chấp nhận | Lớn hơn `0`, tối đa `30s` |
| Profile/label | Nguồn hoặc phiên bản áp dụng | `application.yml`, `order-service-prod.yml`, label phát hành |
| Nguồn cung cấp | Git, biến môi trường, secret manager hoặc nền tảng triển khai | Git cho giá trị thường; secret manager cho token |
| Độ nhạy cảm | Công khai nội bộ, hạn chế hay bí mật | Không nhạy cảm |
| Chủ sở hữu | Nhóm chịu trách nhiệm về ngữ nghĩa và thay đổi | Nhóm nền tảng |
| Người review | Nhóm cần phê duyệt thay đổi | Chủ sở hữu `order-service` |
| Tác động | Hành vi có thể thay đổi khi cập nhật | Tăng thời gian chờ và thời gian xử lý request |
| Cách áp dụng | Chỉ lúc khởi động hay có thể refresh | Có thể refresh nếu thành phần sử dụng hỗ trợ |
| Kiểm tra | Cách xác minh giá trị hợp lệ | Validation `Duration` và kiểm thử HTTP client |
| Trạng thái vòng đời | Đang dùng, deprecated hay đã loại bỏ | Đang dùng |

Với khóa đơn giản, một hàng trong bảng có thể chứa đủ thông tin. Với khóa nhạy cảm hoặc ảnh hưởng lớn, cần mô tả chi tiết hơn về cách cấp giá trị, quyền truy cập, kế hoạch triển khai và quay lui.

### Giá trị mặc định và giá trị hiệu lực

Tài liệu cần phân biệt:

- **Giá trị mặc định trong repository:** giá trị được khai báo trong `application.yml` hoặc tệp cấu hình khác.
- **Giá trị mặc định trong mã:** giá trị dự phòng do ứng dụng đặt khi thuộc tính không được cung cấp.
- **Giá trị hiệu lực:** kết quả sau khi Spring Boot hợp nhất các property source, gồm cấu hình từ xa, file cục bộ, biến môi trường và các nguồn khác theo thứ tự ưu tiên thực tế.

Ba giá trị này có thể khác nhau. Nếu tài liệu ghi một giá trị duy nhất mà không nói rõ đó là loại nào, người vận hành có thể hiểu nhầm giá trị đang chạy. Với khóa quan trọng, ghi rõ nguồn và cách xác định giá trị hiệu lực.

## 4. Quy ước đặt tên khóa

Tên khóa nên mô tả cấu trúc và ngữ nghĩa thay vì chỉ phản ánh tên biến trong một lớp Java. Một quy ước thường dùng là các phần chữ thường phân tách bằng dấu chấm:

```text
<domain>.<component>.<property>
```

Ví dụ:

```yaml
platform:
  http:
    connect-timeout: 2s
    read-timeout: 5s

payment:
  gateway:
    base-url: https://sandbox.example.invalid
    retry-count: 2

order:
  inventory:
    max-connections: 20
```

Quy ước nên thống nhất các điểm sau:

- Dùng tên nhóm có ý nghĩa như `platform`, `payment`, `order` hoặc tên miền tương ứng.
- Dùng tên thuộc tính thể hiện mục đích, ví dụ `read-timeout` thay vì `timeout2`.
- Dùng hậu tố đơn vị nếu điều đó giúp tránh nhầm lẫn, hoặc quy định một kiểu dữ liệu có đơn vị rõ như `Duration`.
- Không mã hóa môi trường vào tên khóa nếu profile đã là chiều phân tách, ví dụ tránh tạo `payment.prod.base-url` song song với `payment.gateway.base-url` mà không có lý do.
- Không tái sử dụng cùng một tên khóa cho hai ý nghĩa khác nhau ở các ứng dụng.
- Giữ tên ổn định; nếu cần đổi tên, xem đó là thay đổi hợp đồng cấu hình và có kế hoạch chuyển tiếp.

Spring Boot hỗ trợ relaxed binding khi ánh xạ thuộc tính vào cấu hình có kiểu. Dù vậy, repository nên giữ một dạng viết nhất quán, thường là kebab-case trong YAML, để việc tìm kiếm và review dễ dàng.

## 5. Gắn khóa với cấu trúc repository

Tài liệu cần chỉ rõ khóa được khai báo ở đâu và vì sao nằm ở phạm vi đó. Ví dụ cấu trúc repository:

```text
config-repo/
├── application.yml
├── application-prod.yml
├── order-service.yml
├── order-service-dev.yml
├── order-service-prod.yml
├── payment-service.yml
└── payment-service-prod.yml
```

Quy ước tham khảo:

- `application.yml`: mặc định kỹ thuật thực sự dùng chung.
- `application-{profile}.yml`: giá trị chung cho các ứng dụng trong một profile.
- `{application}.yml`: cấu hình riêng của một ứng dụng, dùng cho mọi profile nếu không bị override.
- `{application}-{profile}.yml`: cấu hình riêng của ứng dụng trong profile cụ thể.

Trong tài liệu của khóa, nên ghi đường dẫn file tương ứng, profile và ứng dụng nhận giá trị. Nếu cùng một khóa xuất hiện ở nhiều file, giải thích rõ ý đồ override. Đừng chỉ ghi “cấu hình trong Git” vì điều đó chưa giúp người bảo trì xác định nguồn cụ thể.

Ví dụ danh mục rút gọn:

| Khóa | File nguồn | Profile/phạm vi | Ghi chú |
| --- | --- | --- | --- |
| `platform.http.read-timeout` | `application.yml` | Dùng chung | Mặc định kỹ thuật |
| `order.inventory.max-connections` | `order-service.yml` | `order-service`, mọi profile | Có thể override nếu môi trường cần giới hạn khác |
| `payment.gateway.base-url` | `payment-service-dev.yml`, `payment-service-prod.yml` | Theo profile | Endpoint sandbox và production |

Config Server trả về property source theo tên ứng dụng, profile và label. Label chọn phiên bản repository; tài liệu phát hành nên ghi label hoặc commit được dùng trong môi trường để có thể tái tạo trạng thái cấu hình.

## 6. Tài liệu hóa thứ tự ưu tiên và ghi đè

Một khóa có thể được khai báo trong nhiều nguồn. Tài liệu cần cho biết nơi nào là nguồn chuẩn, nơi nào được phép override và ai có quyền thực hiện thay đổi.

Hãy mô tả ít nhất:

1. Giá trị chuẩn được đặt ở file nào.
2. Ứng dụng/profile nào được phép khai báo giá trị khác.
3. Nguồn nào được phép override nguồn nào theo cấu hình client hiện tại.
4. Cách kiểm tra property source và giá trị hiệu lực.
5. Ai phê duyệt thay đổi có phạm vi ảnh hưởng rộng.

Ví dụ, `platform.http.read-timeout` có mặc định `5s` trong `application.yml`; `order-service.yml` có thể đặt `3s` vì đặc điểm gọi inventory. Nếu một profile production cần `8s`, tài liệu phải chỉ rõ override đó có chủ đích, ai sở hữu và kiểm thử nào chứng minh giá trị phù hợp.

Không nên mô tả một thứ tự ưu tiên chung như quy luật bất biến cho mọi ứng dụng. Thứ tự property source phụ thuộc vào phản hồi của Config Server, phiên bản Spring Boot/Spring Cloud và chính sách override của Config Client. Khi có xung đột, kiểm tra endpoint Config Server và nguồn trong `Environment` của client bằng công cụ chẩn đoán đã được bảo vệ.

## 7. Phân loại độ nhạy cảm và tài liệu hóa secret

Tài liệu cần cho người vận hành biết một khóa có chứa dữ liệu nhạy cảm hay không. Có thể thống nhất ba mức:

| Mức | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| Nội bộ thông thường | Giá trị kỹ thuật không phải bí mật | Lưu trong Git theo quyền truy cập repository |
| Hạn chế | Giá trị có thể tiết lộ kiến trúc hoặc thông tin vận hành | Giới hạn người đọc, tránh đưa vào log hoặc tài liệu công khai |
| Bí mật | Mật khẩu, token, private key, credential | Lưu trong secret manager hoặc cơ chế bí mật được phê duyệt; không ghi giá trị thật vào tài liệu/Git |

Với khóa bí mật, tài liệu chỉ nên ghi:

- Tên tham chiếu hoặc tên secret, không ghi giá trị.
- Hệ thống quản lý bí mật đang cung cấp giá trị.
- Ứng dụng hoặc danh tính được phép đọc.
- Người/nhóm sở hữu và quy trình yêu cầu quyền.
- Chu kỳ xoay vòng và cách xử lý khi secret bị lộ hoặc hết hạn.
- Cách ứng dụng nhận giá trị, ví dụ placeholder được phân giải từ môi trường hoặc tích hợp với secret manager.

Ví dụ tài liệu an toàn:

| Khóa cấu hình | Tham chiếu | Nguồn | Quyền đọc |
| --- | --- | --- | --- |
| `spring.datasource.password` | `secret/orders/database-password` | Secret manager của nền tảng | Danh tính `order-service` |
| `payment.gateway.api-key` | `secret/payments/gateway-api-key` | Secret manager của nền tảng | Danh tính `payment-service` |

Không đưa giá trị bí mật vào ví dụ, ảnh chụp màn hình, log build, ticket hoặc nội dung review. Việc một khóa được đánh dấu “secret” trong tài liệu không tự bảo vệ giá trị; quyền truy cập và cách phân phối phải được cấu hình ở hệ thống thực tế.

## 8. Xác định chủ sở hữu và trách nhiệm bảo trì

Mỗi khóa quan trọng cần có một chủ sở hữu chịu trách nhiệm về ý nghĩa và tính đúng đắn của giá trị. Có thể phân chia trách nhiệm như sau:

| Vai trò | Trách nhiệm chính |
| --- | --- |
| Chủ sở hữu ứng dụng | Xác định ứng dụng cần khóa nào, miền giá trị hợp lệ và tác động đến hành vi ứng dụng |
| Nhóm nền tảng/SRE | Duy trì Config Server, Git integration, quy ước repository, quyền truy cập và khả năng phân phối |
| Chủ sở hữu nghiệp vụ | Phê duyệt các giá trị phản ánh chính sách hoặc giới hạn nghiệp vụ |
| Nhóm bảo mật | Định nghĩa cách phân loại, cấp quyền, xoay vòng và ứng phó sự cố secret |
| Người bảo trì repository | Giữ tài liệu, cấu trúc file, lịch sử thay đổi và quy trình review nhất quán |
| Người phê duyệt thay đổi | Đánh giá rủi ro, phạm vi ảnh hưởng và bằng chứng kiểm thử trước khi merge |

Một người có thể đảm nhiệm nhiều vai trò trong nhóm nhỏ, nhưng trách nhiệm cần được ghi rõ. Không nên để một khóa dùng chung quan trọng ở trạng thái “không rõ chủ sở hữu”, vì khi có sự cố sẽ không biết ai xác nhận giá trị và tác động.

### Ví dụ ma trận trách nhiệm

| Hoạt động | Chủ sở hữu ứng dụng | Nền tảng/SRE | Bảo mật | Chủ sở hữu nghiệp vụ |
| --- | --- | --- | --- | --- |
| Định nghĩa khóa timeout của ứng dụng | Chịu trách nhiệm | Tham vấn | — | — |
| Đổi cấu hình dùng chung cho nhiều dịch vụ | Tham vấn | Chịu trách nhiệm | — | Có thể tham vấn |
| Thay đổi secret truy cập | Tham vấn | Phối hợp phân phối | Chịu trách nhiệm chính sách | — |
| Thay đổi giới hạn nghiệp vụ | Phối hợp kiểm thử | Hỗ trợ phân phối | — | Chịu trách nhiệm phê duyệt |
| Cập nhật tài liệu sau khi đổi khóa | Chịu trách nhiệm phần ứng dụng | Chịu trách nhiệm phần repository | Cập nhật phần secret | Cập nhật ý nghĩa nghiệp vụ |

Ma trận là mẫu tham khảo. Nhóm cần điều chỉnh theo mô hình tổ chức và ghi rõ người phê duyệt cuối cùng trong repository hoặc quy trình quản lý thay đổi.

## 9. Tài liệu hóa kiểu dữ liệu, đơn vị và ràng buộc

Tên khóa và ví dụ giá trị chưa đủ để xác định cách ứng dụng sử dụng thuộc tính. Tài liệu phải ghi kiểu dữ liệu và đơn vị, nhất là với số đo, thời gian, dung lượng, tỷ lệ và giới hạn.

Ví dụ:

| Khóa | Kiểu | Đơn vị | Ràng buộc ví dụ |
| --- | --- | --- | --- |
| `platform.http.read-timeout` | `Duration` | giây hoặc mili giây | Lớn hơn `0`, không quá `30s` |
| `order.inventory.max-connections` | `Integer` | số kết nối | Từ `1` đến `200` |
| `payment.gateway.retry-count` | `Integer` | số lần thử lại | Từ `0` đến `5` |
| `platform.feature.new-checkout-enabled` | `Boolean` | không có | `true` hoặc `false` |

Nếu tài liệu nói `timeout=5000` nhưng không nêu đơn vị, một người có thể hiểu là 5 giây trong khi thành phần khác lại coi là 5 mili giây. Nên ưu tiên kiểu có đơn vị như `Duration` và biểu diễn rõ trong YAML, ví dụ `5s` hoặc `500ms`.

Với cấu hình có kiểu, nhóm có thể dùng `@ConfigurationProperties` và validation để kiểm tra dữ liệu lúc ứng dụng khởi động:

```java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "platform.http")
public record HttpProperties(
        Duration connectTimeout,
        Duration readTimeout) {
    public HttpProperties {
        if (connectTimeout == null || connectTimeout.isZero() || connectTimeout.isNegative()) {
            throw new IllegalArgumentException("connect-timeout must be positive");
        }
        if (readTimeout == null || readTimeout.isZero() || readTimeout.isNegative()) {
            throw new IllegalArgumentException("read-timeout must be positive");
        }
    }
}
```

Ví dụ dùng compact constructor để kiểm tra trực tiếp `Duration` lớn hơn 0. Nếu dùng Jakarta Bean Validation, cần tạo constraint validator phù hợp cho `Duration`; không áp dụng `@Positive` trực tiếp vì constraint đó dành cho các kiểu số được hỗ trợ, không phải `Duration`. Giới hạn thực tế phải phù hợp với ứng dụng và được kiểm thử.

Tài liệu nên liên kết khóa với lớp cấu hình hoặc component tiêu thụ nếu điều đó giúp người bảo trì xác định nơi giá trị được bind và áp dụng. Khi tên khóa đổi, cần cập nhật cả repository, lớp cấu hình, kiểm thử và tài liệu.

## 10. Ghi rõ tác động và cách áp dụng thay đổi

Không phải mọi khóa đều có cùng tác động khi thay đổi. Tài liệu cần cho biết:

- Ứng dụng và instance nào đọc khóa.
- Giá trị mới có ảnh hưởng đến kết nối đang mở, pool, cache hay request đang xử lý không.
- Ứng dụng có thể nhận giá trị mới qua refresh hay cần khởi động lại.
- Có thể triển khai thay đổi theo nhóm instance hay phải đồng bộ toàn bộ hệ thống.
- Metric, log hoặc hành vi nghiệp vụ nào cần theo dõi sau thay đổi.
- Phiên bản cấu hình nào là điểm quay lui.

Ví dụ, đổi `platform.logging.level` có thể có tác động khác đổi `spring.datasource.url`. Một số bean có thể đọc giá trị mới sau refresh; các kết nối database hiện hữu có thể cần tái tạo hoặc khởi động lại ứng dụng. Không nên ghi chung rằng “mọi khóa đều refresh được”. Hãy xác nhận cách thành phần tiêu thụ thuộc tính được triển khai.

Với Spring Cloud Bus, một sự kiện refresh có thể được phát đến nhiều client. Tài liệu cần chỉ rõ nhóm ứng dụng nhận sự kiện, điều kiện để bean cập nhật giá trị và endpoint quản trị được phép gọi. Refresh không thay thế review hoặc phê duyệt cấu hình.

## 11. Quy trình thay đổi một khóa

Một thay đổi cấu hình nên đi qua các bước có thể truy vết:

1. **Tạo yêu cầu:** ghi khóa, giá trị hiện tại và giá trị dự kiến, lý do, ứng dụng/profile bị ảnh hưởng, thời điểm mong muốn và người yêu cầu.
2. **Xác định chủ sở hữu:** tìm người chịu trách nhiệm về ngữ nghĩa khóa và người có quyền phê duyệt thay đổi.
3. **Đánh giá tác động:** xác định client sử dụng khóa, nguồn property source, mức độ nhạy cảm, khả năng refresh và rủi ro khi giá trị không hợp lệ.
4. **Cập nhật cấu hình và tài liệu cùng nhau:** thay đổi đúng file, cập nhật bảng khóa, miền giá trị, chủ sở hữu, profile và hướng dẫn vận hành.
5. **Review và kiểm tra:** kiểm tra YAML, schema hoặc validation, kiểm thử ứng dụng, kiểm tra secret scanning và review phạm vi ảnh hưởng.
6. **Phát hành có kiểm soát:** merge theo quy trình, chọn label/commit, áp dụng ở môi trường thử nghiệm trước rồi mở rộng theo kế hoạch.
7. **Xác minh sau thay đổi:** kiểm tra giá trị hiệu lực, log, metric, health và hành vi nghiệp vụ; xác nhận các instance đã nhận phiên bản dự kiến.
8. **Ghi nhận kết quả:** cập nhật commit, ticket, người phê duyệt, thời điểm refresh và kết quả kiểm tra.

Với thay đổi có phạm vi rộng trong `application.yml`, cần xác định tất cả ứng dụng có thể nhận giá trị đó. Một giá trị dùng chung có thể tạo ra tác động ngoài dự kiến ở dịch vụ vốn không được người thay đổi nghĩ đến.

## 12. Quản lý vòng đời khóa: thêm, đổi tên, ngừng dùng

Khóa cấu hình cũng có vòng đời. Nếu không quản lý, repository có thể tích lũy khóa cũ, tên gần giống nhau hoặc thuộc tính không còn được ứng dụng đọc.

### Thêm khóa mới

- Xác định mục đích, kiểu dữ liệu, đơn vị, phạm vi và chủ sở hữu.
- Chọn giá trị mặc định an toàn hoặc xác định rõ khóa bắt buộc.
- Cập nhật lớp `@ConfigurationProperties`, validation và kiểm thử nếu cần.
- Bổ sung tài liệu và ví dụ không chứa bí mật.
- Kiểm tra hành vi khi khóa thiếu hoặc sai kiểu.

### Thay đổi giá trị hoặc ý nghĩa

Nếu chỉ thay giá trị trong miền hợp lệ, vẫn cần đánh giá tác động và cập nhật thông tin vận hành. Nếu ý nghĩa hoặc đơn vị thay đổi, xem đó là thay đổi hợp đồng: tạo khóa mới hoặc có kế hoạch chuyển tiếp thay vì âm thầm đổi cách diễn giải của khóa cũ.

### Đổi tên khóa

Đổi tên có thể làm ứng dụng cũ không còn đọc được cấu hình. Một cách chuyển tiếp an toàn là:

1. Thêm khóa mới và cho ứng dụng hỗ trợ cả tên cũ lẫn tên mới trong một giai đoạn.
2. Cập nhật repository để cung cấp khóa mới, đồng thời giữ khóa cũ nếu các phiên bản ứng dụng còn cần.
3. Triển khai ứng dụng đọc khóa mới và theo dõi việc sử dụng khóa cũ.
4. Xác nhận mọi client đã chuyển sang khóa mới.
5. Đánh dấu khóa cũ deprecated, thông báo mốc loại bỏ và xóa sau khi hết thời gian chuyển tiếp.

Không nên xóa khóa cũ ngay khi vừa sửa mã nguồn nếu vẫn còn instance hoặc phiên bản ứng dụng cũ đang chạy.

### Ngừng sử dụng và xóa khóa

Tài liệu cần ghi trạng thái `deprecated`, lý do, chủ sở hữu, phiên bản thay thế và thời hạn dự kiến loại bỏ. Trước khi xóa, kiểm tra mã nguồn, kiểm thử, dashboard, pipeline, script vận hành và các ứng dụng khác có thể đang đọc khóa. Sau khi loại bỏ, xóa cả khai báo cấu hình, binding, validation, ví dụ và tài liệu liên quan.

## 13. Giữ tài liệu đồng bộ với Git

Tài liệu cấu hình nên được đặt gần repository cấu hình hoặc trong nơi có liên kết rõ ràng với phiên bản repository. Có thể tổ chức như sau:

```text
config-repo/
├── README.md
├── docs/
│   ├── configuration-catalog.md
│   ├── ownership.md
│   └── change-process.md
├── application.yml
├── order-service.yml
└── payment-service.yml
```

Đây là cấu trúc gợi ý; nhóm có thể dùng một tài liệu duy nhất hoặc hệ thống tài liệu nội bộ. Dù chọn cách nào, cần liên kết tài liệu với commit hoặc label cấu hình tương ứng để người vận hành biết họ đang đọc hướng dẫn cho phiên bản nào.

Một số thực hành giúp tài liệu không bị lỗi thời:

- Thay đổi khóa và thay đổi tài liệu trong cùng pull request.
- Dùng CODEOWNERS hoặc cơ chế tương đương để yêu cầu đúng nhóm review file quan trọng.
- Dùng checklist hoặc mẫu pull request yêu cầu ghi lý do, phạm vi, secret classification, kiểm thử và rollback.
- Tự động kiểm tra khóa được khai báo có tài liệu hay không nếu repository có thể trích xuất metadata.
- Định kỳ tìm khóa không còn được tham chiếu và xác nhận với chủ sở hữu trước khi xóa.
- Ghi ngày hoặc commit cập nhật gần nhất cho danh mục có yêu cầu kiểm toán.

Không nên duy trì hai danh mục thủ công mâu thuẫn nhau. Nếu metadata được lưu ở một nguồn có cấu trúc và tài liệu được sinh tự động, hãy xác định rõ nguồn nào là chuẩn và kiểm tra kết quả sinh ra trong CI.

## 14. Mẫu tài liệu cho một khóa

Mẫu sau có thể dùng trong `configuration-catalog.md` hoặc trong pull request:

```markdown
### `payment.gateway.retry-count`

- **Mục đích:** Số lần thử lại khi cổng thanh toán trả về lỗi tạm thời có thể retry.
- **Ứng dụng:** `payment-service`.
- **Phạm vi:** Riêng ứng dụng; có thể khác nhau theo profile.
- **Nguồn:** `payment-service.yml`, có thể override trong `payment-service-prod.yml`.
- **Kiểu:** Integer.
- **Đơn vị:** Số lần thử lại sau lần gọi đầu tiên.
- **Giá trị mặc định:** `2`.
- **Bắt buộc:** Không; dùng mặc định nếu không khai báo.
- **Ràng buộc:** Từ `0` đến `5`.
- **Độ nhạy cảm:** Nội bộ thông thường.
- **Chủ sở hữu:** Nhóm Payment.
- **Review:** Chủ sở hữu Payment và nhóm vận hành khi thay đổi ở production.
- **Tác động:** Giá trị cao hơn có thể tăng độ trễ và số request gửi đến cổng thanh toán.
- **Áp dụng:** Kiểm tra khả năng cập nhật của thành phần retry; nếu không hỗ trợ refresh, triển khai lại instance.
- **Kiểm thử:** Kiểm tra số lần retry, backoff và trường hợp lỗi không được retry.
- **Quay lui:** Trở lại label/commit cấu hình đã được xác minh.
- **Trạng thái:** Đang sử dụng.
```

Ví dụ này chỉ là dữ liệu minh họa. Giá trị mặc định, miền hợp lệ và hành vi retry phải được xác nhận từ implementation thực tế của ứng dụng trước khi dùng làm tài liệu chính thức.

## 15. Tình huống vận hành: thay đổi timeout dùng chung

Giả sử nhóm nền tảng muốn đổi `platform.http.read-timeout` từ `5s` thành `8s` trong `application.yml`. Danh mục khóa cho biết `order-service`, `payment-service` và `inventory-service` đang dùng giá trị chung, trong khi `order-service` có override `3s`.

Trước khi merge, nhóm cần:

1. Xác nhận danh sách ứng dụng nhận giá trị chung và các override hiện có.
2. Hỏi chủ sở hữu từng ứng dụng về tác động của timeout dài hơn, nhất là thời gian giữ request và tài nguyên kết nối.
3. Kiểm tra giới hạn hợp lệ trong `@ConfigurationProperties` và các kiểm thử tích hợp.
4. Xác định ứng dụng nào nhận giá trị qua refresh, ứng dụng nào cần restart hoặc rollout.
5. Thử trên môi trường staging, theo dõi độ trễ, tỷ lệ timeout và số request đang chờ.
6. Ghi nhận label/commit mới và giữ phiên bản trước để quay lui.

Nếu một dịch vụ có nhu cầu khác biệt, chủ sở hữu dịch vụ có thể duy trì override có tài liệu giải thích. Không nên thay đổi override chỉ để buộc tất cả dịch vụ dùng một giá trị chung.

## 16. Checklist review tài liệu và thay đổi cấu hình

- [ ] Mỗi khóa quan trọng có mục đích, kiểu dữ liệu và đơn vị rõ ràng.
- [ ] Đã ghi giá trị mặc định và phân biệt với giá trị hiệu lực.
- [ ] Đã chỉ ra file nguồn, ứng dụng, profile và label/phạm vi liên quan.
- [ ] Đã ghi miền giá trị, điều kiện bắt buộc và cách validation.
- [ ] Đã phân loại độ nhạy cảm; tài liệu không chứa secret thật.
- [ ] Đã chỉ định chủ sở hữu và người review phù hợp.
- [ ] Đã đánh giá tác động, cách refresh/restart và phương án quay lui.
- [ ] Đã cập nhật tài liệu trong cùng thay đổi với repository hoặc mã ứng dụng.
- [ ] Đã có bằng chứng kiểm tra sau khi phát hành và ghi lại commit/label.
- [ ] Nếu khóa bị thay thế, đã có kế hoạch chuyển tiếp và mốc loại bỏ khóa cũ.

Tài liệu hóa khóa và trách nhiệm bảo trì biến repository cấu hình thành một hợp đồng có thể hiểu và kiểm soát giữa các nhóm. Khi mỗi khóa có ý nghĩa, nguồn, phạm vi, chủ sở hữu và quy trình thay đổi rõ ràng, Spring Cloud Config có thể phân phối cấu hình nhất quán hơn, còn nhóm vận hành có đủ thông tin để đánh giá tác động và xử lý sự cố.
