# Chọn YAML hoặc properties và thống nhất quy ước đặt khóa

Kho cấu hình của Spring Cloud Config thường được quản lý trong Git và được nhiều ứng dụng Spring Boot đọc qua Config Server. Khi repository có nhiều file, nhiều profile và nhiều nhóm cùng thay đổi, định dạng file và cách đặt tên khóa ảnh hưởng trực tiếp đến khả năng tìm kiếm, review, tái sử dụng và vận hành cấu hình.

Spring Boot hỗ trợ cả YAML và Java properties. Hai định dạng có thể biểu diễn cùng một tập thuộc tính, nhưng cách viết và điểm dễ mắc lỗi khác nhau. Điều quan trọng là chọn một quy ước rõ ràng cho repository, giữ tên khóa nhất quán giữa các file, profile và ứng dụng, rồi kiểm tra cấu hình bằng chính cơ chế binding của Spring Boot.

Sau bài học, bạn có thể:

- So sánh YAML và `.properties` theo cấu trúc, khả năng đọc và các rủi ro khi chỉnh sửa.
- Biểu diễn cùng một nhóm cấu hình bằng cả hai định dạng.
- Thiết kế tên khóa có prefix, kebab-case và phân cấp rõ ràng.
- Tổ chức file dùng chung, file theo ứng dụng, profile và label trong Git repository.
- Kiểm tra cấu hình bằng `@ConfigurationProperties` và quy trình review tự động.

## 1. Vai trò của định dạng và quy ước đặt tên

YAML và properties chỉ là hai cách biểu diễn dữ liệu cấu hình. Khi Spring Boot nạp chúng, các giá trị được đưa vào `Environment` dưới dạng các property name/value. Các cơ chế như `Environment`, `@Value` và `@ConfigurationProperties` đọc thuộc tính từ môi trường này, không phụ thuộc ứng dụng đã viết giá trị trong YAML hay properties.

Với Spring Cloud Config, Config Server đọc file từ Git repository và trả các property sources phù hợp với tên ứng dụng, profile và label mà Config Client yêu cầu. Ví dụ, một client có thể lấy cấu hình cho `order-service`, profile `prod`, label `release-2026-11`. Khi đó, cùng một quy ước tên khóa cần được áp dụng ở cấu hình dùng chung và cấu hình riêng của dịch vụ.

Có thể hình dung luồng như sau:

```mermaid
flowchart LR
    G["Git repository"] --> F["YAML hoặc properties"]
    F --> S["Spring Cloud Config Server"]
    S --> C["Config Client: application/profile/label"]
    C --> E["Spring Environment"]
    E --> B["@ConfigurationProperties / @Value"]
    B --> A["Mã ứng dụng"]
```

Chọn định dạng giúp nhóm thống nhất cách viết. Quy ước đặt khóa giúp các nhóm thống nhất ý nghĩa và vị trí của từng thuộc tính. Hai việc này cần được quyết định cùng nhau.

## 2. YAML và properties khác nhau như thế nào?

| Tiêu chí | YAML (`.yml` / `.yaml`) | Java properties (`.properties`) |
|---|---|---|
| Cấu trúc | Phân cấp bằng thụt lề | Phẳng, phân cấp bằng dấu chấm trong tên khóa |
| Khả năng đọc nhóm cấu hình | Tốt khi có nhiều nhóm lồng nhau | Dễ đọc với file nhỏ hoặc danh sách khóa ngắn |
| Danh sách | Viết dạng sequence với dấu gạch đầu dòng | Dùng chỉ số như `items[0]`, `items[1]` |
| Giá trị nhiều dòng | Có block scalar `|` và `>` | Cần escape hoặc continuation |
| Rủi ro khi chỉnh sửa | Sai thụt lề, kiểu scalar, key trùng | Escape ký tự, continuation, key trùng |
| Công cụ chỉnh sửa | Editor YAML và YAML linter | Editor text, properties linter |
| Phù hợp | Cấu hình phân cấp, nhóm và danh sách | Cấu hình phẳng, đơn giản, cần cú pháp trực tiếp |

Không có định dạng nào luôn tốt hơn. YAML thường dễ đọc khi cấu hình có nhiều nhóm lồng nhau hoặc danh sách. Properties thường phù hợp với tập khóa ngắn, phẳng và dễ grep. Cả hai đều có thể biểu diễn cấu hình của Spring Boot; hãy chọn theo độ phức tạp thực tế và khả năng kiểm tra trong CI.

## 3. Cùng một cấu hình ở hai định dạng

Giả sử dịch vụ đặt hàng cần endpoint fulfillment, timeout kết nối, số lần retry và danh sách vùng được hỗ trợ.

### Dạng YAML

```yaml
order:
  fulfillment:
    endpoint: "https://fulfillment.internal"
    connect-timeout: 2s
    retry:
      max-attempts: 3
      backoff: 500ms
    supported-regions:
      - "ap-southeast-1"
      - "ap-northeast-1"
```

YAML thể hiện quan hệ cha-con qua thụt lề. Nhóm `order.fulfillment` chứa endpoint, timeout, retry và danh sách vùng. Khi đọc file, người vận hành có thể nhận ra cấu trúc mà không cần lặp lại prefix ở từng dòng.

### Dạng properties

```properties
order.fulfillment.endpoint=https://fulfillment.internal
order.fulfillment.connect-timeout=2s
order.fulfillment.retry.max-attempts=3
order.fulfillment.retry.backoff=500ms
order.fulfillment.supported-regions[0]=ap-southeast-1
order.fulfillment.supported-regions[1]=ap-northeast-1
```

Properties biểu diễn cùng dữ liệu bằng tên khóa đầy đủ. Cách này dễ tìm một khóa cụ thể và phù hợp với file cấu hình phẳng. Với danh sách, cần chỉ rõ chỉ số phần tử theo cú pháp binder hỗ trợ.

Hai ví dụ trên có cùng ý nghĩa đối với binder nếu lớp cấu hình khai báo đúng kiểu. Chẳng hạn:

```java
import java.net.URI;
import java.time.Duration;
import java.util.List;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "order.fulfillment")
public record FulfillmentProperties(
        URI endpoint,
        Duration connectTimeout,
        Retry retry,
        List<String> supportedRegions) {

    public record Retry(int maxAttempts, Duration backoff) {
    }
}
```

Lớp cấu hình cần được đăng ký với Spring, ví dụ bằng `@ConfigurationPropertiesScan` trên lớp ứng dụng hoặc `@EnableConfigurationProperties(FulfillmentProperties.class)`. Với cấu hình production, nên bổ sung validation cho những giá trị bắt buộc và giới hạn hợp lệ. Nếu dùng annotation validation, ứng dụng cần dependency triển khai Bean Validation phù hợp với phiên bản Spring Boot.

## 4. Quy ước đặt tên khóa

Tên khóa nên mô tả rõ miền chức năng, thành phần và ý nghĩa của giá trị. Một quy ước hữu ích là dùng tên phân cấp, chữ thường và kebab-case cho từng thành phần:

```text
<domain>.<component>.<setting-name>
```

Ví dụ:

```text
order.fulfillment.endpoint
order.fulfillment.connect-timeout
order.fulfillment.retry.max-attempts
order.fulfillment.retry.backoff
order.fulfillment.supported-regions
```

### Dùng prefix theo miền chức năng

Mỗi nhóm cấu hình nên có prefix đại diện cho miền nghiệp vụ hoặc thành phần kỹ thuật. Ví dụ `order`, `payment`, `inventory`, `notification`. Prefix giúp tránh xung đột khi nhiều thư viện hoặc module cùng có các tên chung như `enabled`, `timeout` hoặc `endpoint`.

Không nên tạo prefix quá sâu nếu các cấp không mang ý nghĩa phân nhóm thực sự. Ví dụ `order.fulfillment.retry.max-attempts` có cấu trúc dễ hiểu; thêm các cấp trung gian không cần thiết sẽ làm tên khóa dài và khó dùng.

### Thống nhất kebab-case

Trong file cấu hình, ưu tiên tên thuộc tính canonical dạng chữ thường, các từ ngăn cách bằng dấu gạch nối:

- Dùng `connect-timeout`, không trộn `connectTimeout`, `connect_timeout` và `connect-timeout` trong cùng repository.
- Dùng `max-attempts`, không dùng các biến thể khác cho cùng một ý nghĩa.
- Giữ nguyên prefix và cách viết giữa cấu hình dùng chung, cấu hình theo profile và cấu hình riêng từng ứng dụng.

Spring Boot có relaxed binding để ánh xạ một số biến thể tên thuộc tính, nhưng khả năng chấp nhận nhiều cách viết không phải lý do để tạo nhiều alias cho cùng một cấu hình. Khi ghi đè bằng biến môi trường, hãy tuân theo quy tắc chuyển đổi của Spring Boot: dấu chấm thành dấu gạch dưới, bỏ dấu gạch nối và viết hoa tên. Ví dụ `order.fulfillment.connect-timeout` được ánh xạ thành `ORDER_FULFILLMENT_CONNECTTIMEOUT`. Với danh sách, chỉ số phần tử được đặt giữa các dấu gạch dưới. Hãy kiểm tra giá trị cuối cùng trong đúng môi trường triển khai. Tên canonical nhất quán giúp tìm kiếm, tài liệu, kiểm tra và chuyển cấu hình giữa YAML, properties và các nguồn khác dễ hơn.

### Đặt tên theo ý nghĩa, không theo vị trí hiện tại

Tên khóa nên mô tả ý nghĩa nghiệp vụ hoặc kỹ thuật ổn định. Ví dụ `payment.gateway.endpoint` có ý nghĩa rõ hơn `payment.url1`. Tránh đưa tên máy, pod, tài khoản cá nhân hoặc chi tiết triển khai tạm thời vào tên khóa nếu đó không phải một phần của hợp đồng cấu hình.

Dùng tên boolean có nghĩa rõ ràng như `enabled`, `read-only`, `require-signature`. Tránh tên phủ định kép như `disable-validation` nếu một tên khẳng định như `validation-enabled` diễn đạt rõ hơn. Trong code, đọc `if (properties.validationEnabled())` dễ hiểu hơn phải suy luận từ một cờ phủ định.

### Thể hiện đơn vị và kiểu dữ liệu

Tên khóa hoặc kiểu dữ liệu cần giúp người đọc hiểu giá trị đo lường điều gì. Với thời lượng, ưu tiên biểu diễn có đơn vị như `2s`, `500ms`, `3m` và bind thành `Duration`. Với dung lượng, ghi rõ đơn vị hoặc dùng kiểu phù hợp để tránh nhầm byte, KB và MB. Không đặt một giá trị `2000` mà không giải thích đó là mili giây, giây hay một giới hạn khác.

Nếu thư viện đã hỗ trợ `Duration` hoặc `DataSize`, nên tận dụng chuyển đổi kiểu của Spring Boot thay vì tự parse chuỗi trong nhiều lớp nghiệp vụ.

## 5. Lưu ý riêng khi viết YAML

YAML dễ đọc nhờ cấu trúc thụt lề, nhưng parser xử lý kiểu scalar và ký tự đặc biệt theo quy tắc của YAML. Một số nguyên tắc giúp tránh lỗi:

- Dùng dấu cách để thụt lề; không trộn tab và spaces.
- Các phần tử cùng cấp phải thẳng hàng.
- Không khai báo hai key trùng nhau trong cùng một mapping.
- Quote giá trị cần được giữ nguyên như chuỗi, đặc biệt là mã có số 0 ở đầu hoặc chuỗi dễ bị hiểu thành boolean, null hay số.
- Quote chuỗi có ký tự đặc biệt như `#` ở vị trí có thể bắt đầu comment, dấu `:` theo sau khoảng trắng hoặc token có cú pháp YAML; khoảng trắng thông thường trong scalar không bắt buộc phải quote.
- Không dùng `yes/no`, `on/off` để diễn đạt boolean; dùng `true/false` rõ ràng.
- Chọn block scalar `|` hoặc `>` có chủ đích khi lưu nội dung nhiều dòng; kiểm tra newline có được giữ hoặc gộp như mong muốn.

Ví dụ, mã định danh `00127` phải được giữ là chuỗi:

```yaml
customer:
  external-code: "00127"
  enabled: true
  description: "Kênh #2: đơn hàng ưu tiên"
```

Nếu bỏ dấu nháy quanh mã có số 0 ở đầu, parser có thể diễn giải nó thành giá trị số và làm mất định dạng mã định danh. Tương tự, một chuỗi như `null` cần quote nếu ý nghĩa mong muốn là bốn ký tự chữ, không phải giá trị null.

Không nên lạm dụng YAML anchors và aliases cho cấu hình được nhiều nhóm vận hành. Chúng có thể giảm lặp, nhưng làm cho kết quả sau khi merge khó nhìn hơn và không phải mọi công cụ xử lý YAML đều hỗ trợ cùng cách. Với cấu hình quan trọng, ưu tiên nội dung tường minh và dễ review.

## 6. Lưu ý riêng khi viết properties

Properties dùng một dòng cho mỗi khóa và giá trị. Dấu `=` hoặc `:` có thể phân tách key và value; dấu `#` hoặc `!` ở đầu dòng dùng để ghi chú. Ký tự đặc biệt và khoảng trắng đầu dòng/giá trị có quy tắc escape riêng. Dấu gạch chéo ngược ở cuối dòng có thể dùng để nối dòng, vì vậy cần cẩn thận khi giá trị thực sự kết thúc bằng backslash.

Ví dụ:

```properties
# Kết nối dịch vụ fulfillment
order.fulfillment.endpoint=https://fulfillment.internal
order.fulfillment.connect-timeout=2s
order.fulfillment.retry.max-attempts=3
order.fulfillment.retry.backoff=500ms
```

Một số lưu ý:

- Giữ một khóa trên một dòng để diff và review dễ dàng.
- Tránh định nghĩa cùng một khóa nhiều lần trong cùng file hoặc nhiều file cùng phạm vi nếu không có lý do rõ ràng.
- Escape đúng các ký tự phân tách, dấu cách đầu giá trị, dấu `#` hoặc backslash khi chúng là dữ liệu thực.
- Dùng cú pháp index cho list và kiểm tra binder nhận đúng thứ tự phần tử.
- Không thêm khoảng trắng tùy tiện vào tên khóa; hãy giữ canonical key name nhất quán.

Properties không có cấu trúc thụt lề nên các nhóm lớn có thể khó đọc nếu prefix không được tổ chức tốt. Khi file dài, dùng comment phân khu theo miền chức năng và giữ các khóa cùng prefix gần nhau.

## 7. Tổ chức file trong Git repository của Config Server

Spring Cloud Config thường dùng tên file để chọn cấu hình chung, cấu hình ứng dụng và cấu hình theo profile. Một repository có thể tổ chức như sau:

```text
config-repo/
  application.yml
  application-prod.yml
  order-service.yml
  order-service-prod.yml
  inventory-service.yml
  inventory-service-prod.yml
```

Ý nghĩa thường gặp:

| File | Phạm vi |
|---|---|
| `application.yml` | Giá trị mặc định dùng chung cho các ứng dụng |
| `application-prod.yml` | Giá trị dùng chung khi profile `prod` hoạt động |
| `order-service.yml` | Cấu hình riêng cho `order-service` |
| `order-service-prod.yml` | Cấu hình riêng cho `order-service` trong profile `prod` |
| `inventory-service.yml` | Cấu hình riêng cho `inventory-service` |

Config Client xác định ứng dụng bằng `spring.application.name`, profile bằng profile đang hoạt động và label bằng nhánh, tag hoặc commit mà nó yêu cầu. Label giúp chọn revision của repository; profile giúp chọn tập cấu hình theo môi trường hoặc mục đích chạy.

Có thể dùng properties với cùng quy ước tên file, ví dụ `order-service-prod.properties`. Trong một repository, hãy chọn định dạng chuẩn cho các file cùng phạm vi. Tránh để cùng một khóa được định nghĩa lặp ở cả `order-service-prod.yml` và `order-service-prod.properties`, vì nhiều nguồn có thể được nạp cùng lúc và làm người vận hành khó xác định giá trị cuối cùng. Nếu cần đổi định dạng, hãy chuyển đổi có kiểm soát và loại bỏ bản cũ sau khi đã xác minh.

Không nên đưa bí mật dạng rõ vào Git. Thông tin xác thực cần được cấp từ secret manager hoặc cơ chế bảo vệ phù hợp; nếu dùng mã hóa của Spring Cloud Config, khóa giải mã phải được quản lý riêng khỏi repository cấu hình.

## 8. Chọn một chuẩn cho cả nhóm

Một quy ước hiệu quả cần đủ cụ thể để người viết và người review áp dụng giống nhau. Ví dụ, nhóm có thể thống nhất:

1. File cấu hình dùng YAML làm chuẩn; chỉ dùng properties khi có yêu cầu tương thích rõ ràng.
2. Tên khóa luôn theo canonical kebab-case và phân cấp bằng dấu chấm.
3. Mỗi nhóm cấu hình có prefix theo miền chức năng hoặc tên thành phần.
4. Danh sách dùng YAML sequence hoặc properties index theo cùng một thứ tự logic.
5. Thời lượng dùng hậu tố đơn vị như `ms`, `s`, `m`; giá trị được bind thành kiểu có nghĩa.
6. Giá trị chuỗi có thể bị parser hiểu thành kiểu khác phải được quote.
7. Mỗi khóa có một nguồn sở hữu rõ ràng; tránh khai báo trùng giữa file chung và file riêng nếu không có chủ đích override.
8. Thay đổi cấu hình được review như thay đổi mã nguồn: có người chịu trách nhiệm, kiểm tra cú pháp và kiểm tra tác động đến profile.

Nếu tổ chức chọn properties thay vì YAML, các nguyên tắc về prefix, kebab-case, kiểu dữ liệu, profile và ownership vẫn giữ nguyên. Chỉ cách biểu diễn cấu trúc và danh sách thay đổi.

## 9. Kiểm tra tính nhất quán trước khi merge

Không nên chỉ dựa vào việc file nhìn có vẻ đúng. Pipeline có thể kiểm tra nhiều lớp:

- **Kiểm tra cú pháp:** parse YAML hoặc properties để phát hiện thụt lề, escape và cấu trúc sai.
- **Kiểm tra key trùng:** phát hiện một khóa được định nghĩa nhiều lần trong cùng file hoặc các file có phạm vi chồng lấn.
- **Kiểm tra quy ước:** tìm tên khóa không theo kebab-case, prefix sai hoặc khóa không có owner.
- **Kiểm tra kiểu và giá trị:** bind cấu hình vào `@ConfigurationProperties`, dùng validation cho giá trị bắt buộc, giới hạn số lần retry, timeout và endpoint.
- **Kiểm tra profile:** khởi tạo context với các profile quan trọng, ví dụ `dev`, `staging`, `prod`, để phát hiện khóa thiếu hoặc override ngoài dự kiến.
- **Kiểm tra kết quả Config Server:** gọi endpoint theo application/profile/label trong môi trường kiểm thử và xác nhận property sources chứa giá trị mong muốn.

Ví dụ, có thể dùng một lớp cấu hình có validation:

```java
import java.net.URI;
import java.time.Duration;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "order.fulfillment")
@Validated
public record FulfillmentSettings(
        @NotNull URI endpoint,
        @NotNull Duration connectTimeout,
        @NotNull @Valid Retry retry,
        @NotEmpty List<String> supportedRegions) {

    public record Retry(
            @Min(1) int maxAttempts,
            @NotNull Duration backoff) {
    }
}
```

Lớp Java này khớp với cấu trúc YAML và properties ở phần trước: `retry.max-attempts`, `retry.backoff` và `supported-regions` được bind vào các trường lồng nhau và danh sách. Khi dùng annotation validation, ứng dụng cần có implementation Jakarta Bean Validation, thường được thêm qua `spring-boot-starter-validation`.

## 10. Các lỗi thiết kế thường gặp

| Vấn đề | Hậu quả | Cách khắc phục |
|---|---|---|
| Mỗi ứng dụng tự đặt tên khóa | Khó chia sẻ và tìm kiếm cấu hình | Thống nhất prefix và canonical key name |
| Trộn camelCase, snake_case và kebab-case | Tăng nhầm lẫn khi review và chuyển nguồn | Dùng kebab-case trong file cấu hình |
| Dùng tên chung như `timeout` ở nhiều miền | Dễ xung đột và khó hiểu ngữ cảnh | Đặt prefix như `payment.gateway.timeout` |
| YAML sai thụt lề hoặc key trùng | Parser lỗi hoặc giá trị bị ghi đè ngoài ý muốn | Dùng formatter, linter và kiểm tra key trùng |
| Properties chứa escape hoặc continuation sai | Giá trị nhận được khác nội dung dự kiến | Kiểm tra ký tự đặc biệt và giữ mỗi khóa trên một dòng |
| Cùng khóa nằm ở YAML và properties | Khó giải thích giá trị cuối cùng | Chọn một định dạng chuẩn và loại bỏ định nghĩa lặp |
| Cấu hình theo profile thiếu key bắt buộc | Ứng dụng lỗi lúc chạy hoặc dùng default không an toàn | Dùng validation và kiểm thử từng profile |
| Dùng chuỗi cho timeout hoặc dung lượng | So sánh và tính toán dễ sai | Bind thành `Duration` hoặc `DataSize` |
| Lưu secret dạng rõ trong Git | Rò rỉ thông tin xác thực | Dùng secret manager hoặc mã hóa có quản lý khóa riêng |

## 11. Tự kiểm tra

1. Khi nào YAML dễ bảo trì hơn properties? Khi nào properties là lựa chọn phù hợp?
2. Hai ví dụ YAML và properties ở bài học biểu diễn danh sách vùng được hỗ trợ như thế nào?
3. Vì sao nên dùng tên khóa `order.fulfillment.connect-timeout` thay vì `timeout`?
4. Relaxed binding có đồng nghĩa nhóm nên dùng nhiều kiểu viết khác nhau cho cùng một khóa không? Vì sao?
5. Trong repository Config Server, `application-prod.yml` khác `order-service-prod.yml` ở phạm vi cấu hình như thế nào?
6. Vì sao không nên để cùng một khóa tồn tại đồng thời trong file YAML và properties cùng phạm vi?
7. Những bước kiểm tra nào nên chạy trước khi merge một thay đổi cấu hình?

Hãy chọn một nhóm cấu hình thực tế của dịch vụ, biểu diễn bằng YAML và properties, rồi so sánh khả năng đọc, diff và kiểm tra. Sau đó thống nhất một định dạng cho repository, áp dụng canonical kebab-case cho tất cả khóa và kiểm tra binding với từng profile mà dịch vụ triển khai.

