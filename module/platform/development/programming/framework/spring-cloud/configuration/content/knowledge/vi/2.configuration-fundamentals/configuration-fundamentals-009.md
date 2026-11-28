# Phân biệt khóa không tồn tại, giá trị rỗng và giá trị mặc định

Khi quản lý cấu hình tập trung, một thuộc tính có thể xuất hiện trong nhiều file và nhiều nguồn: `application.yml`, file riêng của dịch vụ, file theo profile, biến môi trường hoặc cấu hình lấy từ Spring Cloud Config Server. Để hiểu giá trị cuối cùng mà ứng dụng nhận được, cần phân biệt ba trạng thái thường bị nhầm lẫn: khóa không được khai báo, khóa được khai báo với giá trị rỗng và khóa không có giá trị tường minh nên ứng dụng dùng giá trị mặc định.

Sự khác biệt này ảnh hưởng trực tiếp đến việc kế thừa cấu hình giữa các profile, ghi đè cấu hình chung, bật tắt tính năng và xử lý thay đổi qua refresh. Một dòng YAML bị xóa, một chuỗi được đặt thành `""` và một giá trị mặc định trong Java có thể tạo ra ba kết quả khác nhau.

## 1. Ba trạng thái cần phân biệt

### Khóa không tồn tại

Một property source không khai báo khóa thì source đó không cung cấp giá trị cho thuộc tính. Khi Spring tìm kiếm thuộc tính qua nhiều nguồn theo thứ tự ưu tiên, nó có thể tiếp tục tìm ở nguồn thấp hơn. Nếu không nguồn nào cung cấp giá trị, ứng dụng mới đi đến cơ chế mặc định hoặc trạng thái không có giá trị.

Ví dụ file cấu hình profile production không khai báo `checkout.retry-limit`:

```yaml
checkout:
  enabled: true
```

Việc thiếu `retry-limit` trong file này không có nghĩa thuộc tính chắc chắn bằng `null` hay bằng `0`. Một file cấu hình chung, biến môi trường hoặc giá trị mặc định trong ứng dụng vẫn có thể cung cấp giá trị đó.

### Giá trị rỗng

Giá trị rỗng là một giá trị chuỗi có độ dài bằng không. Trong YAML, hãy viết rõ bằng cặp dấu nháy:

```yaml
checkout:
  banner: ""
```

Trong file `.properties`, cách viết tương đương là:

```properties
checkout.banner=
```

Khóa vẫn tồn tại và giá trị của nó là chuỗi rỗng. Khi giá trị này đến từ nguồn có độ ưu tiên cao hơn, nó có thể ghi đè chuỗi ở nguồn thấp hơn. Ứng dụng nhận được `""`, không tự động nhận lại giá trị mặc định chỉ vì chuỗi đang rỗng.

Ví dụ, nếu cấu hình chung đặt `checkout.banner` là `"Chào mừng"`, còn file production đặt `checkout.banner: ""`, giá trị production có thể chủ động xóa nội dung banner kế thừa.

### Giá trị mặc định

Giá trị mặc định là phương án dự phòng được khai báo ở một tầng nào đó, chẳng hạn:

- Trong file cấu hình chung như `application.yml`.
- Trong khai báo thuộc tính của ứng dụng, ví dụ giá trị khởi tạo của trường trong lớp `@ConfigurationProperties`.
- Trong placeholder, ví dụ `${checkout.retry-limit:2}`.
- Trong quy tắc nghiệp vụ của ứng dụng khi không có cấu hình phù hợp.

Giá trị mặc định chỉ được dùng khi quá trình phân giải không tìm thấy giá trị có hiệu lực theo quy tắc của tầng đó. Một giá trị được khai báo tường minh, kể cả `false`, `0` hoặc chuỗi rỗng, có thể thay thế giá trị mặc định. Vì vậy, không nên dùng phép kiểm tra kiểu “nếu giá trị false thì lấy mặc định” khi `false` là một lựa chọn hợp lệ.

## 2. Ví dụ với Spring Cloud Config và các profile

Giả sử Config Server đọc repository Git có cấu trúc:

```text
config-repository/
├── application.yml
├── order-service.yml
└── order-service-prod.yml
```

`application.yml` chứa cấu hình chung cho các ứng dụng:

```yaml
checkout:
  banner: "Thông báo chung"
  retry-limit: 3
  enabled: true
```

`order-service-prod.yml` chỉ khai báo những giá trị production cần thay đổi:

```yaml
checkout:
  banner: ""
  enabled: false
```

Khi `order-service` lấy cấu hình với profile `prod`, có thể hiểu kết quả theo từng thuộc tính như sau, giả sử các property source được ghép theo quy tắc thông thường của Config Server:

| Thuộc tính | File chung | File production | Kết quả mong đợi |
|---|---|---|---|
| `checkout.banner` | `"Thông báo chung"` | `""` | Chuỗi rỗng ghi đè giá trị chung |
| `checkout.retry-limit` | `3` | Không khai báo | Kế thừa giá trị `3` từ nguồn chung |
| `checkout.enabled` | `true` | `false` | `false` ghi đè giá trị chung |

Điểm quan trọng là **không khai báo** và **khai báo chuỗi rỗng** có ý nghĩa khác nhau. Nếu production không khai báo `banner`, cấu hình chung có thể tiếp tục được sử dụng. Nếu production khai báo `banner: ""`, ứng dụng nhận giá trị rỗng để biểu thị ý định xóa nội dung kế thừa.

Config Server định tuyến cấu hình theo tên ứng dụng, profile và label của repository. Profile chọn nhóm file phù hợp với bối cảnh chạy; label chọn phiên bản Git cần đọc. Việc chọn profile hoặc label không biến một khóa bị thiếu thành chuỗi rỗng. Kết quả vẫn phụ thuộc các property source mà Config Server và Spring Boot đưa vào môi trường cùng thứ tự ưu tiên của chúng.

## 3. Giá trị mặc định trong Spring Boot

Có thể đặt giá trị mặc định trong lớp `@ConfigurationProperties` bằng cách khởi tạo trường:

```java
@ConfigurationProperties(prefix = "checkout")
public class CheckoutProperties {

    private String banner = "Thông báo mặc định trong ứng dụng";
    private int retryLimit = 2;
    private boolean enabled = true;

    public String getBanner() {
        return banner;
    }

    public void setBanner(String banner) {
        this.banner = banner;
    }

    public int getRetryLimit() {
        return retryLimit;
    }

    public void setRetryLimit(int retryLimit) {
        this.retryLimit = retryLimit;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
```

Nếu không có property source nào cung cấp `checkout.retry-limit`, giá trị khởi tạo `2` vẫn được giữ. Nếu cấu hình cung cấp `checkout.retry-limit: 5`, Binder gán `5`. Tương tự, `checkout.enabled: false` là giá trị tường minh và sẽ thay thế mặc định `true`.

Với thuộc tính chuỗi, nếu cấu hình cung cấp `checkout.banner: ""`, trường `banner` được gán chuỗi rỗng. Giá trị khởi tạo `"Thông báo mặc định trong ứng dụng"` không được dùng để thay thế chuỗi rỗng. Đây là hành vi cần nhớ khi dùng giá trị khởi tạo làm default cho `@ConfigurationProperties`.

Placeholder cũng có cú pháp mặc định:

```java
@Value("${checkout.banner:Thông báo mặc định}")
private String banner;
```

Nếu `checkout.banner` không được phân giải từ các nguồn cấu hình, phần sau dấu `:` được dùng làm mặc định. Nếu thuộc tính được phân giải thành chuỗi rỗng, kết quả vẫn là chuỗi rỗng. Placeholder default không phải là phép thay thế cho mọi giá trị rỗng hoặc chuỗi chỉ chứa khoảng trắng.

## 4. Phân biệt chuỗi rỗng với YAML null

YAML có một điểm dễ gây nhầm lẫn: giá trị không có nội dung sau dấu `:` không đồng nghĩa với chuỗi rỗng.

```yaml
checkout:
  banner: ""       # Chuỗi rỗng
  subtitle:        # Giá trị null theo cú pháp YAML
  footer: null     # Giá trị null tường minh
```

Muốn biểu diễn chuỗi rỗng, hãy dùng `""` hoặc `''`. Dạng `subtitle:` và `footer: null` biểu diễn null. Trong mô hình property source của Spring Cloud Config, một giá trị null không ngăn property source có độ ưu tiên thấp hơn cung cấp giá trị. Resolver có thể xem null như không có giá trị khi phân giải thuộc tính. Vì vậy, không nên dùng YAML null với kỳ vọng nó sẽ xóa một chuỗi được khai báo ở cấu hình chung.

Nếu mục tiêu là ghi đè một chuỗi kế thừa thành chuỗi rỗng, hãy khai báo rõ:

```yaml
checkout:
  banner: ""
```

Nếu mục tiêu là tắt một chức năng, hãy dùng giá trị boolean tường minh:

```yaml
checkout:
  banner-enabled: false
```

Không nên dùng chuỗi rỗng, null hoặc việc xóa khóa làm tín hiệu tắt chức năng nếu mô hình cấu hình có thể diễn đạt rõ bằng `enabled: false`.

## 5. Giá trị false, 0 và chuỗi chỉ có khoảng trắng

Không phải mọi giá trị “trông như không có gì” đều là thiếu giá trị:

| Giá trị | Ý nghĩa |
|---|---|
| `false` | Boolean có giá trị, thường dùng để tắt một tùy chọn |
| `0` | Số có giá trị; ý nghĩa nghiệp vụ phụ thuộc thuộc tính |
| `""` | Chuỗi rỗng có chủ đích |
| `"   "` | Chuỗi chứa khoảng trắng, không phải chuỗi rỗng |
| Không khai báo | Property source hiện tại không cung cấp khóa |
| `null` | Giá trị null; cách phân giải phụ thuộc property source và Binder |

Ví dụ, `retry-limit: 0` có thể mang nghĩa không cho phép thử lại. Nếu ứng dụng tự động thay `0` bằng mặc định `3`, ứng dụng sẽ không tuân theo cấu hình người vận hành đã chọn. Tương tự, `enabled: false` phải giữ nguyên ý nghĩa tắt tính năng.

Với chuỗi bắt buộc có nội dung, chuỗi rỗng hoặc chỉ chứa khoảng trắng thường là cấu hình không hợp lệ. Có thể kiểm tra bằng Bean Validation:

```java
@NotBlank
private String paymentGatewayUrl;
```

`@NotBlank` kiểm tra chuỗi không null và có ít nhất một ký tự không phải khoảng trắng. `@NotEmpty` chỉ yêu cầu chuỗi hoặc tập hợp không rỗng, do đó chuỗi gồm khoảng trắng vẫn có thể vượt qua. Chọn ràng buộc theo ý nghĩa của thuộc tính và thực hiện validation khi ứng dụng bind cấu hình.

Với thuộc tính số hoặc boolean mà cần phân biệt “không được cung cấp” với `0` hoặc `false`, kiểu wrapper như `Integer` và `Boolean` có thể biểu đạt trạng thái chưa có giá trị rõ hơn kiểu nguyên thủy. Dù vậy, ứng dụng vẫn nên định nghĩa default và validation một cách tường minh thay vì dựa vào giá trị mặc định ngầm của Java như `0` hoặc `false`.

## 6. Cách kiểm tra giá trị hiệu lực

Khi một thuộc tính có giá trị bất ngờ, hãy kiểm tra theo thứ tự sau:

1. Xác nhận tên ứng dụng, profile và label mà Config Client đang sử dụng.
2. Kiểm tra file cấu hình chung, file riêng của ứng dụng và file theo profile trong Git.
3. Tìm các khai báo trùng tên ở biến môi trường, tham số JVM, tham số dòng lệnh và các property source khác.
4. Xác định nguồn nào có độ ưu tiên cao hơn trong cấu hình Spring Boot và các tùy chọn override của Spring Cloud Config đang dùng.
5. Phân biệt khóa không tồn tại, chuỗi rỗng, null, `false` và `0` tại đúng nguồn cung cấp giá trị.
6. Kiểm tra default trong `@ConfigurationProperties`, placeholder hoặc logic ứng dụng; xác nhận default đó có thực sự được dùng hay đã bị một nguồn khác ghi đè.

Spring Boot Actuator có endpoint `env` và `configprops` hỗ trợ kiểm tra môi trường thuộc tính và cấu hình đã bind khi được bật. Các endpoint này có thể tiết lộ tên thuộc tính nhạy cảm hoặc thông tin vận hành, vì vậy cần giới hạn quyền truy cập và cấu hình việc hiển thị giá trị phù hợp. Không công khai endpoint quản trị chỉ để tiện gỡ lỗi.

Không nên dựa vào việc nhìn riêng một file YAML để kết luận giá trị cuối cùng. Cùng một khóa có thể xuất hiện ở nhiều property source, và thứ tự ưu tiên còn chịu ảnh hưởng bởi cách import cấu hình cũng như các thiết lập override. Hãy kiểm tra giá trị đã được phân giải trong đúng môi trường chạy.

## 7. Điều gì xảy ra khi xóa khóa hoặc đặt khóa rỗng rồi refresh?

Giả sử `application.yml` cung cấp `checkout.banner: "Thông báo chung"` và file `order-service-prod.yml` từng đặt `checkout.banner: "Thông báo riêng"`.

- Nếu xóa khóa khỏi file production, sau khi ứng dụng nhận cấu hình mới, giá trị chung có thể trở lại vì file production không còn cung cấp giá trị ghi đè.
- Nếu đổi giá trị production thành `checkout.banner: ""`, chuỗi rỗng sẽ ghi đè giá trị chung.
- Nếu đặt `checkout.banner: null`, không nên kỳ vọng null sẽ xóa giá trị chung trong cơ chế phân giải property source của Spring Cloud Config.
- Nếu xóa khóa khỏi mọi nguồn, ứng dụng có thể dùng default trong `@ConfigurationProperties` hoặc placeholder; nếu không có default, thuộc tính có thể không được cung cấp và validation hoặc quá trình sử dụng có thể thất bại.

Một commit mới trong Git không tự động thay đổi các instance đang chạy. Client cần khởi động lại hoặc nhận quy trình refresh phù hợp. Spring Cloud Bus có thể phát thông báo refresh đến nhiều instance, nhưng chỉ những bean và thuộc tính hỗ trợ cơ chế refresh mới cập nhật như mong đợi. Sau refresh, cần xác minh giá trị đã bind và hành vi thực tế của dịch vụ; không giả định mọi đối tượng trong bộ nhớ đều tự thay đổi.

Khi xóa một khóa, cũng cần xem xét giá trị cũ có còn được giữ trong bean hay cache hay không. Nếu ứng dụng dùng `@RefreshScope`, kiểm tra bean có thực sự được tạo lại khi refresh. Nếu cấu hình được sao chép vào đối tượng tự quản lý hoặc cache riêng, cần có cơ chế cập nhật tương ứng.

## 8. Quy ước quản trị nên áp dụng

- Dùng việc không khai báo khóa để kế thừa giá trị từ property source thấp hơn hoặc để ứng dụng sử dụng default đã định nghĩa.
- Dùng `""` khi thật sự muốn đặt một thuộc tính chuỗi thành rỗng và đã xác nhận mã ứng dụng xử lý được trường hợp đó.
- Dùng `false`, `0` hoặc giá trị tường minh phù hợp cho các lựa chọn boolean và số; không coi chúng là thiếu cấu hình.
- Không dùng YAML null như một cách đáng tin cậy để xóa giá trị kế thừa trong Spring Cloud Config.
- Đặt default ở một tầng có chủ đích, ghi rõ default thuộc file cấu hình chung hay mã ứng dụng và tránh nhiều default mâu thuẫn.
- Dùng validation như `@NotBlank`, `@Min` hoặc `@Max` cho thuộc tính có ràng buộc; thông báo lỗi cần chỉ ra khóa cấu hình nhưng không tiết lộ bí mật.
- Khi thay đổi hoặc xóa khóa trong Git, review tác động đến profile khác, refresh, fallback và rollback trước khi áp dụng production.

Phân biệt khóa không tồn tại, chuỗi rỗng và giá trị mặc định giúp nhóm kiểm soát việc kế thừa và ghi đè cấu hình một cách dự đoán được. Trong Spring Cloud Config, một khóa bị bỏ qua có thể cho phép nguồn thấp hơn cung cấp giá trị, chuỗi rỗng có thể chủ động ghi đè một chuỗi kế thừa, còn default chỉ phát huy khi không có giá trị hiệu lực. Hiểu rõ cả null, `false`, `0` và quy trình refresh sẽ giúp cấu hình Git được phân phối nhất quán và tránh những thay đổi vận hành ngoài ý muốn.
