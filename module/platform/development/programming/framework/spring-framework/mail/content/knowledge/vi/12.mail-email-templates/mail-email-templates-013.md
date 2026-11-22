# Versioning template và khả năng tương thích dữ liệu

Email giao dịch thường được gửi từ các template HTML như xác nhận đơn hàng, hóa đơn, đặt lại mật khẩu hoặc thông báo giao hàng. Theo thời gian, template thay đổi: thêm trường hiển thị, đổi bố cục, hỗ trợ ngôn ngữ mới hoặc bổ sung liên kết. Đồng thời, dữ liệu mà ứng dụng truyền vào template cũng thay đổi theo model và nghiệp vụ.

Nếu template mới yêu cầu một trường mà event cũ chưa có, email có thể lỗi khi render. Nếu một trường bị đổi tên hoặc đổi ý nghĩa mà template cũ vẫn sử dụng, nội dung có thể sai dù ứng dụng vẫn gửi thư thành công. Vì vậy, cần quản lý hai thứ có liên quan nhưng không đồng nhất:

- **Template version:** phiên bản của nội dung và cấu trúc trình bày email.
- **Data contract/schema version:** phiên bản của cấu trúc và ý nghĩa dữ liệu mà template nhận để render.

Trong **Spring Framework Mail**, template engine như Thymeleaf render body từ model; `JavaMailSender` và `MimeMessageHelper` đóng gói, gửi MIME message. Việc versioning cần được tổ chức ở tầng quản lý template và model, trước khi message được gửi.

## 1. Vì sao template email cần versioning?

Một template ban đầu có thể chỉ hiển thị tên khách hàng và mã đơn hàng:

```html
<p>Xin chào <span th:text="${customerName}">Khách hàng</span>.</p>
<p>Đơn hàng <strong th:text="${orderCode}">ORD-001</strong> đã được xác nhận.</p>
```

Sau đó, nhóm sản phẩm muốn thêm tổng tiền và ngày giao dự kiến:

```html
<p>Tổng tiền: <span th:text="${totalAmountLabel}">0 ₫</span></p>
<p>Dự kiến giao: <span th:text="${estimatedDeliveryLabel}">Ngày giao</span></p>
```

Template mới có thể cần các biến:

```text
customerName
orderCode
totalAmountLabel
estimatedDeliveryLabel
```

Trong khi một event cũ đang nằm trong hàng đợi có thể chỉ chứa:

```json
{
  "customerName": "Nguyễn An",
  "orderCode": "ORD-001"
}
```

Nếu hệ thống thay template hiện tại bằng phiên bản yêu cầu tất cả bốn biến mà không có chiến lược tương thích, event cũ có thể render thiếu dữ liệu hoặc thất bại. Đây là vấn đề **hợp đồng dữ liệu giữa producer và consumer**:

```text
Business service / event producer
          |
          | dữ liệu theo schema
          v
      Mail model
          |
          | biến được truyền vào
          v
     Email template
          |
          | HTML / plain text
          v
 MimeMessageHelper -> JavaMailSender -> SMTP
```

Template là một consumer của dữ liệu. Mỗi lần thay đổi template hoặc model cần xem xét liệu consumer và producer vẫn hiểu cùng một hợp đồng hay không.

Versioning giúp:

- Giữ email cũ có thể render trong lúc hàng đợi còn event cũ.
- Triển khai thay đổi nội dung theo từng bước mà không làm gián đoạn gửi thư.
- Biết chính xác template nào đã tạo ra một email khi cần điều tra.
- Hỗ trợ rollback về phiên bản đã biết là tương thích.
- Phân biệt thay đổi giao diện với thay đổi cấu trúc hoặc ý nghĩa dữ liệu.
- Quản lý nhiều ngôn ngữ, tenant hoặc loại thông báo có vòng đời riêng.

## 2. Phân biệt template version và data schema version

Hai phiên bản này có thể thay đổi độc lập.

| Khái niệm | Mô tả | Ví dụ |
| --- | --- | --- |
| **Template version** | Phiên bản nội dung HTML/text và cách trình bày | `order-confirmation/v2` đổi bố cục, thêm phần tổng tiền |
| **Data schema version** | Phiên bản cấu trúc và ý nghĩa của model được truyền vào template | `OrderConfirmationDataV2` có `totalAmountLabel` |
| **Business event version** | Phiên bản payload của event nghiệp vụ được lưu hoặc gửi qua queue | `OrderConfirmedV1` được phát hành từ service đơn hàng |
| **Renderer version** | Phiên bản logic chuẩn bị model hoặc render template | Bộ chuyển đổi legacy model sang model mới |

Không nên mặc định một số version duy nhất đại diện cho tất cả các lớp. Ví dụ, template `v3` vẫn có thể dùng data schema `v2`; một template có thể được chỉnh màu sắc mà không thay đổi model; hoặc một schema có thể được nâng cấp trong khi template vẫn giữ nguyên.

### Ví dụ các phiên bản độc lập

```text
Template order-confirmation/v1
        |
        +-- dùng OrderConfirmationDataV1

Template order-confirmation/v2
        |
        +-- dùng OrderConfirmationDataV1
        |      (chỉ đổi layout, chưa cần dữ liệu mới)
        |
        +-- hoặc OrderConfirmationDataV2
               (bổ sung totalAmountLabel)
```

Một metadata request có thể là:

```json
{
  "templateKey": "order-confirmation",
  "templateVersion": 2,
  "dataSchemaVersion": 1,
  "locale": "vi-VN"
}
```

Điều này cho biết template trình bày ở phiên bản 2 nhưng vẫn nhận schema dữ liệu phiên bản 1. Đây là lựa chọn hợp lệ nếu template v2 không cần trường mới hoặc renderer có thể cung cấp giá trị mặc định.

## 3. Xác định data contract của template

Trước khi version template, cần xác định rõ **template được phép nhận dữ liệu gì**. Một data contract tốt mô tả tên trường, kiểu dữ liệu, ý nghĩa, khả năng rỗng và cách định dạng.

Ví dụ contract cho email xác nhận đơn hàng:

| Field | Kiểu | Bắt buộc? | Ý nghĩa |
| --- | --- | --- | --- |
| `customerName` | String | Có | Tên hiển thị đã được chuẩn hóa |
| `orderCode` | String | Có | Mã đơn hàng |
| `orderUrl` | URI/String | Có | URL HTTPS do ứng dụng tạo |
| `totalAmountLabel` | String | Không ở schema v1; có thể bắt buộc ở v2 | Tổng tiền đã format theo locale/currency |
| `estimatedDeliveryLabel` | String | Không | Ngày giao dự kiến đã được format |
| `locale` | Locale/code | Có theo yêu cầu gửi | Ngôn ngữ và quy ước định dạng |

Contract nên ghi rõ hơn tên biến:

- **Kiểu:** String, BigDecimal, Instant, UUID, enum hoặc kiểu dữ liệu riêng.
- **Nullability:** trường có thể thiếu, null hay luôn phải có.
- **Ý nghĩa:** `orderDate` là thời điểm tạo đơn, xác nhận hay thanh toán?
- **Định dạng:** số tiền có kèm currency, ngày giờ theo múi giờ nào?
- **Nguồn:** field đến từ service nào và đã qua bước kiểm tra nào?
- **Ngữ cảnh bảo mật:** dữ liệu có được phép đưa vào email và hiển thị cho recipient này không?
- **Quy tắc hiển thị:** khi giá trị không có, ẩn cả phần, hiển thị nội dung thay thế hay coi là lỗi?

### Đừng truyền toàn bộ entity vào template

Không nên đưa trực tiếp entity database hoặc object domain lớn vào template context chỉ vì tiện:

```java
// Không nên: template có thể truy cập quá nhiều field không liên quan.
context.setVariable("order", orderEntity);
context.setVariable("customer", customerEntity);
```

Hãy tạo một **mail model** chỉ chứa dữ liệu cần hiển thị:

```java
public record OrderConfirmationDataV1(
        String customerName,
        String orderCode,
        String orderUrl
) {}
```

Mail model đóng vai trò ranh giới giữa nghiệp vụ và template. Khi entity thay đổi, template không bị phụ thuộc trực tiếp vào cấu trúc database. Đồng thời, việc chọn lọc field giúp giảm nguy cơ lộ thông tin không dành cho email.

## 4. Thay đổi nào tương thích, thay đổi nào phá vỡ hợp đồng?

Một thay đổi được coi là tương thích hay không phụ thuộc vào **chiều thay đổi**: template mới đọc dữ liệu cũ, hay template cũ đọc dữ liệu mới.

### 4.1. Thay đổi thường tương thích ngược

Trong ngữ cảnh template consumer, template mới vẫn có thể dùng dữ liệu cũ:

- Thêm một field **optional** và template có fallback khi field thiếu.
- Thêm một phần trình bày không cần dữ liệu mới.
- Thay đổi màu sắc, font, khoảng cách hoặc bố cục mà không đổi contract.
- Thêm một trường chỉ dùng nếu có giá trị, không bắt buộc cho event cũ.
- Bổ sung một biến mà renderer có thể tạo từ các field cũ với ý nghĩa tương đương.

Ví dụ, template v2 thêm dòng giao dự kiến nhưng chỉ hiển thị khi có dữ liệu:

```html
<p th:if="${estimatedDeliveryLabel != null}">
  Dự kiến giao:
  <span th:text="${estimatedDeliveryLabel}">Chưa có thông tin</span>
</p>
```

Nếu model cũ không cung cấp `estimatedDeliveryLabel`, template vẫn có thể render phần còn lại. Tuy nhiên, nếu biến không được đưa vào context, cần bảo đảm biểu thức của template engine xử lý trường hợp thiếu theo cách mong muốn; cách rõ ràng hơn là renderer chuẩn hóa model và luôn cung cấp giá trị null hoặc giá trị mặc định.

### 4.2. Thay đổi có thể phá vỡ tương thích

| Thay đổi | Vì sao có thể breaking? | Cách xử lý |
| --- | --- | --- |
| Xóa field đang được template dùng | Template không còn dữ liệu để render | Giữ field trong giai đoạn chuyển tiếp hoặc tạo schema mới |
| Đổi tên `customerName` thành `recipientName` | Consumer cũ vẫn tìm tên cũ | Adapter hoặc version schema/template mới |
| Đổi kiểu `totalAmount` từ số sang chuỗi không có quy ước | Logic format có thể sai hoặc lỗi | Định nghĩa field mới với kiểu và ý nghĩa rõ |
| Đổi `orderDate` từ thời điểm tạo sang thời điểm xác nhận | Tên giữ nguyên nhưng ý nghĩa thay đổi | Dùng tên field mới hoặc version contract |
| Biến optional thành bắt buộc | Event cũ có thể không có giá trị | Migrate dữ liệu hoặc phát hành schema mới |
| Đổi format ngày mà không báo trước | Template hoặc client đọc sai | Giữ kiểu thời gian chuẩn và format tại tầng phù hợp |
| Đổi `orderUrl` từ URL đầy đủ sang path tương đối | Template/renderer có thể tạo link sai | Dùng field mới hoặc giữ hợp đồng cũ |
| Đổi đơn vị tiền tệ nhưng giữ tên field | Nội dung có thể sai về nghiệp vụ | Gắn currency rõ ràng và version contract |

**Đổi ý nghĩa của field cũng là breaking change**, dù tên và kiểu dữ liệu không đổi. Ví dụ `amount` trước đây là tổng tiền sau thuế nhưng nay trở thành tiền trước thuế; template vẫn render được nhưng email cung cấp thông tin sai.

### 4.3. Tương thích tiến

Tương thích tiến trong trường hợp này thường có nghĩa **consumer cũ vẫn xử lý được dữ liệu mới**:

- Producer thêm field mới, template cũ bỏ qua vì không sử dụng.
- DTO adapter chỉ chuyển những field mà template cũ cần.
- Event payload có field mở rộng nhưng vẫn giữ nguyên field cũ và ý nghĩa cũ.

Template engine thường không quan tâm đến những biến không được tham chiếu. Tuy nhiên, nếu renderer strict validation toàn bộ model hoặc thay đổi tên/kiểu field cũ, tính tương thích có thể mất. Vì vậy, nên xác định rõ contract thay vì dựa vào việc template engine bỏ qua field lạ.

## 5. Chiến lược đặt version cho template

Có nhiều cách quản lý template version. Lựa chọn phù hợp phụ thuộc template được đóng gói cùng ứng dụng hay được quản lý độc lập.

### 5.1. Version trong đường dẫn tài nguyên

Với template nằm trong classpath:

```text
src/main/resources/templates/mail/
└── order-confirmation/
    ├── v1.html
    ├── v2.html
    └── v3.html
```

Renderer chọn tên template cụ thể:

```java
String templateName = switch (version) {
    case 1 -> "mail/order-confirmation/v1";
    case 2 -> "mail/order-confirmation/v2";
    default -> throw new IllegalArgumentException(
            "Unsupported template version: " + version
    );
};
```

Ưu điểm:

- Phiên bản cũ và mới có thể cùng tồn tại trong một artifact.
- Dễ xem thay đổi trong Git.
- Có thể render lại một event cũ bằng đúng template version.
- Rollback có thể chọn lại version trước nếu model tương thích.

Hạn chế:

- Muốn sửa template thường phải build và deploy ứng dụng.
- Nếu có nhiều locale, số file tăng theo template × version × locale.
- Cần quy ước dọn phiên bản cũ sau khi không còn event cần chúng.

### 5.2. Version trong hệ thống lưu template

Với template được quản lý trong database hoặc dịch vụ nội bộ, có thể lưu metadata:

| Field | Ví dụ |
| --- | --- |
| `template_key` | `order-confirmation` |
| `version` | `2` |
| `locale` | `vi-VN` |
| `data_schema_version` | `2` |
| `status` | `DRAFT`, `PUBLISHED`, `RETIRED` |
| `created_at` | Thời điểm tạo |
| `published_at` | Thời điểm phát hành |
| `content_hash` | Hash nội dung template |

Một bản đã **PUBLISHED** nên được xem là bất biến. Nếu cần chỉnh sửa, tạo version mới thay vì sửa đè nội dung đã phát hành. Điều này giúp biết chính xác nội dung nào đã tạo ra email.

Hệ thống quản lý template cũng cần:

- Phân quyền ai được sửa, ai được publish.
- Lưu lịch sử thay đổi và người thực hiện.
- Xác thực template trước khi phát hành.
- Kiểm soát biến được phép dùng.
- Hạn chế truy cập template từ nguồn không đáng tin.
- Có cơ chế chọn phiên bản hiện hành và rollback.

### 5.3. Alias `current` hoặc `active`

Ứng dụng có thể có một con trỏ logic:

```text
order-confirmation/current -> order-confirmation/v3
```

Alias giúp chọn phiên bản mới cho email phát sinh sau khi rollout. Nhưng nếu một event nằm trong queue nhiều giờ và worker chỉ tra `current` khi xử lý, event đó có thể được render bằng template mới dù được tạo khi version cũ đang hoạt động.

Đó có thể là hành vi mong muốn hoặc không. Nếu cần khả năng tái tạo nội dung, hãy **lưu version đã chọn cùng event hoặc mail request** khi tạo yêu cầu gửi.

### 5.4. Có nên dùng Semantic Versioning?

Có thể dùng cách đặt số có ý nghĩa:

- **Major:** thay đổi contract không tương thích, ví dụ xóa/đổi tên field bắt buộc hoặc thay ý nghĩa.
- **Minor:** bổ sung field optional hoặc khả năng mới tương thích với model cũ.
- **Patch:** sửa lỗi trình bày, typo hoặc CSS không đổi contract.

Ví dụ `2.1.3` biểu diễn template major 2, minor 1, patch 3. Đây là **quy ước quản trị do dự án lựa chọn**, không phải chuẩn bắt buộc của Spring Mail hoặc Thymeleaf. Nếu dự án chỉ cần số nguyên `v1`, `v2`, điều đó cũng có thể đủ; quan trọng là cách phân loại breaking change nhất quán.

## 6. Versioning data contract

Template version chỉ cho biết **dùng nội dung nào**. Để render chính xác, ứng dụng còn cần biết model theo schema nào.

Một cách đơn giản là định nghĩa DTO riêng theo version:

```java
import java.util.Locale;

public record OrderConfirmationDataV1(
        String customerName,
        String orderCode,
        String orderUrl,
        Locale locale
) {}

public record OrderConfirmationDataV2(
        String customerName,
        String orderCode,
        String orderUrl,
        String totalAmountLabel,
        String estimatedDeliveryLabel,
        Locale locale
) {}
```

Ở đây V2 bổ sung hai trường. V1 vẫn giữ nguyên hợp đồng cũ để event hoặc luồng xử lý cũ có thể tiếp tục sử dụng.

### Không nên chỉ thêm field vào một Map không có contract

Ví dụ:

```java
Map<String, Object> model = new HashMap<>();
model.put("customerName", customerName);
model.put("orderCode", orderCode);
model.put("totalAmount", amount);
```

Map linh hoạt nhưng có một số rủi ro:

- Sai chính tả tên field chỉ được phát hiện khi render hoặc khi nội dung bị thiếu.
- Kiểu dữ liệu có thể thay đổi ngầm giữa các producer.
- Không thể hiện rõ trường nào bắt buộc, trường nào optional.
- Ý nghĩa của một key có thể bị đổi mà không có compiler hỗ trợ.

Nếu dùng Map vì template engine cần context dạng key-value, hãy tạo Map từ **DTO có kiểu rõ ràng** ở một bước adapter. Đừng để mọi service tự do đặt key theo ý mình.

### Phân biệt field thiếu, null và rỗng

Ba trạng thái này có thể mang ý nghĩa khác:

| Trạng thái | Ý nghĩa có thể có | Cách xử lý |
| --- | --- | --- |
| Field không có trong payload | Producer cũ chưa biết field | Adapter cung cấp default hoặc null |
| Field có giá trị null | Producer biết field nhưng chưa có dữ liệu | Hiển thị nội dung thay thế hoặc ẩn phần |
| Field là chuỗi rỗng | Có field nhưng giá trị không có ký tự | Chuẩn hóa theo contract |
| Field có giá trị hợp lệ | Có dữ liệu để trình bày | Render theo đúng ngữ cảnh |

Đừng dựa vào cách template engine xử lý biến thiếu như một quy tắc contract. Nên chuẩn hóa trạng thái trong mail model để template nhận dữ liệu có ý nghĩa rõ ràng.

## 7. Dùng adapter để tương thích dữ liệu cũ và mới

Khi producer cũ phát event theo schema V1 nhưng template mới cần V2, có thể dùng **adapter** chuyển đổi:

```text
Legacy event V1
  customerName, orderCode, orderUrl
          |
          v
   OrderConfirmationAdapter
          |
          | bổ sung giá trị mặc định hoặc tra dữ liệu phù hợp
          v
   OrderConfirmationDataV2
          |
          v
   Template order-confirmation/v2
```

Ví dụ:

```java
public final class OrderConfirmationAdapter {

    private OrderConfirmationAdapter() {}

    public static OrderConfirmationDataV2 fromV1(
            OrderConfirmationDataV1 oldData
    ) {
        return new OrderConfirmationDataV2(
                oldData.customerName(),
                oldData.orderCode(),
                oldData.orderUrl(),
                null,
                null,
                oldData.locale()
        );
    }
}
```

Adapter trên **không bịa dữ liệu**: hai trường mới được để null vì V1 không chứa thông tin đó. Template V2 cần xử lý trạng thái thiếu một cách có chủ đích.

Nếu có thể truy xuất dữ liệu mới từ nguồn có thẩm quyền, adapter có thể nhận thêm một service để tra cứu. Nhưng cần cân nhắc:

- Dữ liệu có còn đúng tại thời điểm gửi không?
- Event cũ có nên phản ánh trạng thái đơn hàng lúc phát sinh hay trạng thái hiện tại?
- Việc tra cứu có làm thay đổi ý nghĩa của email đã được tạo từ trước không?
- Nếu dịch vụ dữ liệu không sẵn sàng, email nên chờ, dùng fallback hay thất bại?

Adapter là nơi chuyển đổi hợp đồng, không nên giấu logic nghiệp vụ quan trọng trong biểu thức template.

## 8. Thiết kế template mới có fallback rõ ràng

Một template V2 có thể nhận các trường mới nhưng vẫn xử lý được dữ liệu cũ:

```html
<h1>Đơn hàng đã được xác nhận</h1>
<p>
  Xin chào
  <strong th:text="${customerName}">Khách hàng</strong>!
</p>
<p>
  Mã đơn hàng:
  <strong th:text="${orderCode}">ORD-001</strong>
</p>

<section th:if="${totalAmountLabel != null and !#strings.isEmpty(totalAmountLabel)}">
  <p>
    Tổng tiền:
    <strong th:text="${totalAmountLabel}">0 ₫</strong>
  </p>
</section>

<section th:if="${estimatedDeliveryLabel != null and !#strings.isEmpty(estimatedDeliveryLabel)}">
  <p>
    Dự kiến giao:
    <span th:text="${estimatedDeliveryLabel}">Chưa có thông tin</span>
  </p>
</section>

<a th:href="${orderUrl}">Xem đơn hàng</a>
```

Template dùng `th:if` để chỉ hiển thị phần có dữ liệu. Các giá trị text dùng `th:text` để được escape. `orderUrl` phải do backend tạo từ domain tin cậy và kiểm tra trước khi truyền vào template; HTML escaping của `th:href` không tự xác thực đích URL.

Một fallback có ý nghĩa phải được xác định bởi nghiệp vụ. Ví dụ, nếu không có ngày giao dự kiến, ẩn dòng đó có thể hợp lý. Nhưng nếu thiếu mã xác nhận bảo mật, **không được tự tạo một giá trị giả** chỉ để template render thành công.

## 9. Lựa chọn template version cho từng email

Khi đã có nhiều phiên bản, hệ thống cần một quy tắc chọn:

- Dùng version mới nhất cho mọi email mới.
- Pin version theo event khi event được tạo.
- Chọn theo loại thông báo, locale, tenant hoặc chiến dịch.
- Giữ version cũ cho các event tồn đọng trong queue.
- Cho phép rollout một phần rồi mở rộng.

Một metadata request có thể là:

```java
public record TemplateRef(
        String templateKey,
        int templateVersion,
        int dataSchemaVersion,
        String locale
) {}
```

Ví dụ:

```java
TemplateRef ref = new TemplateRef(
        "order-confirmation",
        2,
        1,
        "vi-VN"
);
```

Điều đó có nghĩa dùng template v2 nhưng model schema v1. Nếu template v2 cần schema v2, request phải thể hiện rõ hoặc adapter phải chuyển đổi.

### Chọn template bằng allowlist

Không lấy tên template trực tiếp từ input không đáng tin cậy:

```java
// Không nên: dữ liệu ngoài quyết định tên template tùy ý.
String templateName = request.templateName();
String html = templateEngine.process(templateName, context);
```

Hãy ánh xạ một key/version đã được ứng dụng cho phép:

```java
public String resolveTemplateName(TemplateRef ref) {
    if (!"order-confirmation".equals(ref.templateKey())) {
        throw new IllegalArgumentException("Unsupported template key");
    }

    return switch (ref.templateVersion()) {
        case 1 -> "mail/order-confirmation/v1";
        case 2 -> "mail/order-confirmation/v2";
        default -> throw new IllegalArgumentException(
                "Unsupported template version"
        );
    };
}
```

Trong ứng dụng thực tế, có thể dùng registry/catalog thay vì switch. Dù dùng cách nào, version phải được tra từ danh sách đã đăng ký và được phép sử dụng.

### Version nào được dùng cho event đang chờ?

Đây là quyết định quan trọng trong hệ thống bất đồng bộ:

| Chính sách | Cách xử lý event cũ trong queue | Phù hợp khi |
| --- | --- | --- |
| **Pin at creation** | Lưu template version lúc tạo yêu cầu; worker dùng lại version đó | Cần khả năng tái tạo và nội dung nhất quán |
| **Resolve at send time** | Worker chọn `current` khi bắt đầu gửi | Muốn mọi email dùng nội dung mới nhất |
| **Pin schema, resolve template** | Giữ schema của event nhưng chọn template tương thích với schema đó | Có nhiều template visual nhưng data contract ổn định |
| **Adapter then current** | Chuyển event cũ sang model hiện tại rồi dùng template active | Có adapter tin cậy và muốn giảm số template phải giữ |

Không có một chính sách đúng cho mọi sản phẩm. Email hóa đơn hoặc xác nhận có thể cần giữ nội dung/version gắn với thời điểm nghiệp vụ; email marketing có thể muốn dùng template active khi gửi. Hãy xác định chính sách trước khi triển khai.

## 10. Rollout thay đổi contract theo kiểu additive

Khi cần thêm trường mới, cách triển khai ít gây gián đoạn là **thêm trước, sử dụng sau, rồi mới bắt buộc nếu thật sự cần**.

Giả sử V1 chỉ có `customerName`, `orderCode`, `orderUrl`; V2 bổ sung `totalAmountLabel`.

### Giai đoạn 1 — Mở rộng producer theo cách tương thích

Producer thêm trường mới nhưng vẫn giữ field cũ:

```json
{
  "schemaVersion": 1,
  "customerName": "Nguyễn An",
  "orderCode": "ORD-001",
  "orderUrl": "https://app.example.org/orders/...",
  "totalAmountLabel": "1.250.000 ₫"
}
```

Trong giai đoạn này, consumer/template cũ bỏ qua field mới. Nếu field mới đã trở thành một phần chính thức của schema, hãy phát hành schema v2 thay vì âm thầm thay đổi hợp đồng v1.

### Giai đoạn 2 — Phát hành template/renderer hỗ trợ trường optional

Template V2 hiển thị `totalAmountLabel` khi có giá trị. Model adapter có thể cung cấp null cho event cũ.

### Giai đoạn 3 — Bắt đầu gửi dữ liệu mới

Producer mới phát event theo schema V2; consumer biết cách đọc V1 và V2 hoặc có adapter chuyển đổi. Template V1 vẫn hoạt động với model cũ nếu còn event cần xử lý.

### Giai đoạn 4 — Theo dõi và ngừng V1

Chỉ ngừng hỗ trợ V1 khi:

- Không còn event V1 trong queue/retry/dead-letter queue cần render.
- Các producer cũ đã được nâng cấp hoặc ngừng phát.
- Những nơi lưu payload cũ đã được migrate hoặc có adapter lâu dài.
- Có thể khôi phục hoặc tra cứu nội dung cũ theo chính sách lưu trữ.

Không xóa template/schema cũ chỉ vì deployment mới đã hoàn tất; queue, retry và dữ liệu lưu lâu dài có thể vẫn tham chiếu version cũ.

## 11. Quy trình migration khi field đổi tên hoặc đổi ý nghĩa

Giả sử field `customerName` cần đổi thành `recipientDisplayName`.

**Cách dễ gây lỗi:**

1. Đổi tên field trong producer.
2. Xóa `customerName`.
3. Deploy template mới.
4. Event cũ vẫn chứa `customerName`, template mới tìm `recipientDisplayName` và không có dữ liệu.

**Cách chuyển đổi có giai đoạn:**

```text
Schema V1:
  customerName
      |
      v
Adapter:
  recipientDisplayName = customerName
      |
      v
Schema V2:
  recipientDisplayName
      |
      v
Template V2
```

Trong giai đoạn chuyển tiếp, adapter hiểu cả hai schema:

```java
public String resolveRecipientDisplayName(
        Integer schemaVersion,
        String customerName,
        String recipientDisplayName
) {
    if (schemaVersion != null && schemaVersion >= 2) {
        return recipientDisplayName;
    }
    return customerName;
}
```

Đây là ví dụ đơn giản. Code thực tế nên dùng DTO versioned và kiểm tra trường bắt buộc; không để nhiều tham số nullable không liên quan làm contract trở nên mơ hồ.

Sau khi mọi producer đã chuyển sang V2 và không còn dữ liệu V1 cần xử lý, có thể ngừng field cũ trong một release sau. Nếu ý nghĩa field thay đổi, **đừng tái sử dụng tên cũ với semantics mới**; hãy tạo field mới hoặc schema mới.

## 12. Quản lý version khi template có nhiều ngôn ngữ

Một template có thể có nhiều locale:

```text
mail/
└── order-confirmation/
    ├── v1/
    │   ├── vi-VN.html
    │   └── en-US.html
    └── v2/
        ├── vi-VN.html
        └── en-US.html
```

Version layout và locale là hai chiều độc lập:

| Template version | Locale | Mục đích |
| --- | --- | --- |
| v1 | vi-VN | Bản tiếng Việt cũ |
| v1 | en-US | Bản tiếng Anh cũ |
| v2 | vi-VN | Bản tiếng Việt mới |
| v2 | en-US | Bản tiếng Anh mới |

Khi chỉ dịch nội dung mà không đổi data contract hoặc layout, có thể coi đó là thay đổi của locale asset trong cùng một version hoặc phát hành patch theo quy ước dự án. Nếu ngôn ngữ mới cần field mới hoặc cấu trúc riêng, cần đánh giá như một thay đổi template/data contract.

Không nên tự fallback sang ngôn ngữ khác mà không có quy tắc. Ví dụ, nếu thiếu `vi-VN`, fallback sang `en-US` có thể khiến người nhận nhận nội dung không hiểu. Hãy định nghĩa locale fallback rõ ràng, chẳng hạn `vi-VN -> vi -> default`, và quyết định khi không có bản dịch.

## 13. Quản lý version cho template được lưu ngoài ứng dụng

Một số hệ thống cho phép biên tập nội dung email qua admin portal và lưu template trong database/object storage. Khi đó cần tách:

- **Template key:** định danh ổn định của loại email.
- **Version:** phiên bản bất biến sau khi publish.
- **Locale:** ngôn ngữ.
- **Data schema version:** hợp đồng model mà template cần.
- **Status:** draft, published, retired.
- **Metadata:** người tạo, thời điểm, nội dung/hash, mô tả thay đổi.

Ví dụ bản ghi logic:

```json
{
  "templateKey": "order-confirmation",
  "templateVersion": 3,
  "dataSchemaVersion": 2,
  "locale": "vi-VN",
  "status": "PUBLISHED",
  "contentHash": "sha256:...",
  "publishedAt": "2026-11-12T09:00:00Z"
}
```

Khi render, dịch vụ template phải:

1. Xác định key/version/locale theo chính sách.
2. Lấy đúng bản đã publish.
3. Kiểm tra data schema version mà template yêu cầu.
4. Chạy adapter nếu model chưa đúng schema.
5. Render với dữ liệu đã chuẩn hóa.
6. Trả kết quả cùng metadata version để tầng gửi ghi nhận.

Template do người biên tập quản lý vẫn là **mã trình bày**. Không cho phép template thực thi tùy ý Java, gọi service nội bộ hoặc truy cập secrets. Hạn chế quyền chỉnh sửa và kiểm soát biểu thức/template feature theo threat model của ứng dụng.

## 14. Xử lý lỗi khi template version không tương thích

Một hệ thống nên phân biệt lỗi chọn template, lỗi contract và lỗi gửi SMTP.

| Lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Không tìm thấy template version | Event tham chiếu v3 nhưng artifact chỉ có v1/v2 | Kiểm tra registry/deployment; chỉ fallback nếu có mapping tương thích được định nghĩa |
| Không hỗ trợ data schema | Template v2 yêu cầu schema 2 nhưng model là schema 1 | Chạy adapter hoặc chọn template tương thích |
| Thiếu field bắt buộc | `orderCode` null | Dừng render và báo lỗi nghiệp vụ; không tự bịa dữ liệu |
| Field optional thiếu | `estimatedDeliveryLabel` null | Ẩn phần tương ứng hoặc hiển thị nội dung thay thế đã định nghĩa |
| Locale không có | Không có template `vi-VN` | Áp dụng locale fallback đã công bố hoặc từ chối rõ ràng |
| Lỗi cú pháp template | Biểu thức Thymeleaf không hợp lệ | Sửa/publish lại template; không retry SMTP |
| SMTP tạm thời không sẵn sàng | Timeout, phản hồi 4xx | Retry có giới hạn/backoff theo chính sách gửi |
| SMTP từ chối vĩnh viễn | Recipient hoặc sender bị từ chối | Xử lý địa chỉ/quyền gửi; không retry vô hạn |

### Có nên fallback tự động về template cũ?

Chỉ khi đã xác định template cũ **tương thích với model hiện tại và nội dung vẫn đúng về nghiệp vụ**. Fallback không có kiểm soát có thể gửi thông tin lỗi thời, thiếu thông tin pháp lý hoặc dùng đường dẫn không còn hợp lệ.

Ví dụ:

- Template v2 chỉ đổi màu và khoảng cách, model không đổi: fallback về v1 có thể chấp nhận.
- Template v2 thêm thông tin bắt buộc về điều khoản thanh toán: fallback về v1 có thể không còn phù hợp.
- Template v2 dùng field mới nhưng adapter có thể chuyển đổi chính xác: fallback có thể được cho phép theo chính sách.

Khi fallback, cần ghi nhận **version được yêu cầu** và **version thực tế đã render**, cùng lý do. Không âm thầm thay version vì sẽ gây khó khăn khi điều tra.

### Fallback plain-text có thay thế template version không?

Không hoàn toàn. Bản plain-text là một định dạng trình bày thay thế trong cùng message (`multipart/alternative`), còn template version là version của nội dung/contract. Có thể có template HTML v2 và plain-text v2; nếu HTML render lỗi, một plain-text fallback đã được chuẩn bị riêng có thể giúp thông báo cơ bản vẫn gửi được. Tuy nhiên, cần chắc chắn bản fallback truyền tải đủ nội dung và không bỏ sót thông tin quan trọng.

## 15. Ví dụ Spring Boot: render theo template version

Ví dụ dưới đây sử dụng Thymeleaf và Spring Mail. Hai template được đóng gói trong classpath:

```text
src/main/resources/templates/mail/order-confirmation/v1.html
src/main/resources/templates/mail/order-confirmation/v2.html
```

Hai DTO:

```java
import java.util.Locale;

public record OrderConfirmationV1(
        String customerName,
        String orderCode,
        String orderUrl,
        Locale locale
) {}

public record OrderConfirmationV2(
        String customerName,
        String orderCode,
        String orderUrl,
        String totalAmountLabel,
        String estimatedDeliveryLabel,
        Locale locale
) {}
```

Renderer chọn template version một cách tường minh:

```java
import org.springframework.stereotype.Component;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

@Component
public class OrderConfirmationRenderer {

    private final TemplateEngine templateEngine;

    public OrderConfirmationRenderer(TemplateEngine templateEngine) {
        this.templateEngine = templateEngine;
    }

    public String renderV1(OrderConfirmationV1 data) {
        Context context = new Context(data.locale());
        context.setVariable("customerName", data.customerName());
        context.setVariable("orderCode", data.orderCode());
        context.setVariable("orderUrl", data.orderUrl());

        return templateEngine.process(
                "mail/order-confirmation/v1",
                context
        );
    }

    public String renderV2(OrderConfirmationV2 data) {
        Context context = new Context(data.locale());
        context.setVariable("customerName", data.customerName());
        context.setVariable("orderCode", data.orderCode());
        context.setVariable("orderUrl", data.orderUrl());
        context.setVariable("totalAmountLabel", data.totalAmountLabel());
        context.setVariable(
                "estimatedDeliveryLabel",
                data.estimatedDeliveryLabel()
        );

        return templateEngine.process(
                "mail/order-confirmation/v2",
                context
        );
    }
}
```

Renderer chỉ chịu trách nhiệm chuyển DTO thành HTML. Nó không gửi email và không tự truy cập database để tìm dữ liệu thiếu.

### Template V1

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<body>
  <h1>Đơn hàng đã được xác nhận</h1>
  <p>Xin chào <span th:text="${customerName}">Khách hàng</span>.</p>
  <p>Mã đơn: <strong th:text="${orderCode}">ORD-001</strong></p>
  <a th:href="${orderUrl}">Xem đơn hàng</a>
</body>
</html>
```

### Template V2

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<body>
  <h1>Đơn hàng đã được xác nhận</h1>
  <p>Xin chào <span th:text="${customerName}">Khách hàng</span>.</p>
  <p>Mã đơn: <strong th:text="${orderCode}">ORD-001</strong></p>

  <p th:if="${totalAmountLabel != null}">
    Tổng tiền: <strong th:text="${totalAmountLabel}">0 ₫</strong>
  </p>
  <p th:if="${estimatedDeliveryLabel != null}">
    Dự kiến giao:
    <span th:text="${estimatedDeliveryLabel}">Chưa có thông tin</span>
  </p>

  <a th:href="${orderUrl}">Xem đơn hàng</a>
</body>
</html>
```

Template V2 hỗ trợ các trường optional. Các giá trị text được escape bằng `th:text`; URL phải được backend tạo và kiểm tra theo domain tin cậy trước khi đưa vào model.

### Chọn version và gửi bằng `JavaMailSender`

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;

@Service
public class OrderConfirmationMailService {

    private final JavaMailSender mailSender;
    private final OrderConfirmationRenderer renderer;

    public OrderConfirmationMailService(
            JavaMailSender mailSender,
            OrderConfirmationRenderer renderer
    ) {
        this.mailSender = mailSender;
        this.renderer = renderer;
    }

    public void sendV1(
            String recipient,
            OrderConfirmationV1 data
    ) throws MessagingException {
        String html = renderer.renderV1(data);
        String plain = "Xin chào " + data.customerName()
                + ". Đơn hàng " + data.orderCode()
                + " đã được xác nhận: " + data.orderUrl();

        send(recipient, data.orderCode(), plain, html);
    }

    public void sendV2(
            String recipient,
            OrderConfirmationV2 data
    ) throws MessagingException {
        String html = renderer.renderV2(data);
        String plain = "Xin chào " + data.customerName()
                + ". Đơn hàng " + data.orderCode()
                + " đã được xác nhận: " + data.orderUrl();

        if (data.totalAmountLabel() != null) {
            plain += "\nTổng tiền: " + data.totalAmountLabel();
        }
        if (data.estimatedDeliveryLabel() != null) {
            plain += "\nDự kiến giao: " + data.estimatedDeliveryLabel();
        }

        send(recipient, data.orderCode(), plain, html);
    }

    private void send(
            String recipient,
            String orderCode,
            String plain,
            String html
    ) throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                true,
                StandardCharsets.UTF_8.name()
        );
        helper.setFrom("notifications@example.org");
        helper.setTo(recipient);
        helper.setSubject("Xác nhận đơn hàng " + orderCode);
        helper.setText(plain, html);
        mailSender.send(message);
    }
}
```

Đoạn code minh họa hai entry point versioned để thấy rõ model nào đi với template nào. Trong ứng dụng lớn, có thể gom logic vào một registry/dispatcher thay vì tạo nhiều method tương tự. Địa chỉ sender trong ví dụ phải được thay bằng địa chỉ đã được SMTP provider cấp quyền.

**Điểm quan trọng:** `renderV1` không nhận V2 một cách ngầm định và `renderV2` không giả định mọi event cũ đã có trường mới. Mỗi đường render có contract rõ ràng.

## 16. Dispatcher theo metadata của mail request

Khi có nhiều loại email, có thể lưu một request độc lập:

```java
public record MailTemplateSelection(
        String templateKey,
        int templateVersion,
        int dataSchemaVersion,
        String locale
) {}
```

Một dispatcher có thể chọn model adapter và renderer:

```java
public String renderOrderConfirmation(
        MailTemplateSelection selection,
        Object eventData
) {
    if (!"order-confirmation".equals(selection.templateKey())) {
        throw new IllegalArgumentException("Unknown template key");
    }

    return switch (selection.templateVersion()) {
        case 1 -> {
            OrderConfirmationV1 model =
                    adaptToV1(selection.dataSchemaVersion(), eventData);
            yield renderer.renderV1(model);
        }
        case 2 -> {
            OrderConfirmationV2 model =
                    adaptToV2(selection.dataSchemaVersion(), eventData);
            yield renderer.renderV2(model);
        }
        default -> throw new IllegalArgumentException(
                "Unsupported template version"
        );
    };
}
```

Các hàm `adaptToV1(...)` và `adaptToV2(...)` là phần chuyển đổi do ứng dụng triển khai; chúng phải kiểm tra schema thực tế và không được tự tạo giá trị nghiệp vụ giả. `Object` ở ví dụ giúp tập trung vào dispatch; trong code production, nên dùng kiểu event/DTO cụ thể hoặc một registry có type-safe mapping.

## 17. Versioning khi gửi bất đồng bộ qua queue

Một trường hợp dễ bị bỏ quên: email được tạo từ event, nhưng worker gửi sau đó.

```text
Thời điểm T1:
Order service phát event V1
       |
       v
Queue giữ event nhiều giờ

Thời điểm T2:
Ứng dụng deploy template V2

Thời điểm T3:
Mail worker đọc event V1
       |
       v
Chọn template/schema
       |
       +-- không hỗ trợ V1 --> render lỗi
       |
       +-- có adapter/renderer V1 --> gửi được
```

Điều này xảy ra khi queue bị backlog, worker dừng lâu, retry hoặc dead-letter message được phát lại sau nhiều ngày. Do đó:

- Giữ parser/adapter cho event schema cũ trong thời gian cần thiết.
- Ghi `schemaVersion` vào event thay vì đoán từ việc field có tồn tại.
- Nếu cần giữ đúng nội dung tại thời điểm phát sinh, lưu `templateVersion` cùng event.
- Không xóa template cũ khi vẫn còn queue/retry có thể tham chiếu.
- Có chính sách xử lý dead-letter queue và replay rõ ràng.
- Khi replay, quyết định dùng version ban đầu hay version hiện tại và ghi nhận lựa chọn.

### Pin version hay dùng current?

**Pin version khi tạo request** phù hợp với email có ý nghĩa lưu trữ, kiểm toán hoặc nội dung cần tái tạo. **Resolve version khi gửi** phù hợp khi muốn mọi email gửi ra dùng nội dung mới nhất. Dù chọn cách nào, nên ghi nhận version thực tế đã render để điều tra.

Một request bất đồng bộ có thể chứa:

```json
{
  "notificationId": "c3d5e1c4-...",
  "eventType": "OrderConfirmed",
  "eventSchemaVersion": 1,
  "templateKey": "order-confirmation",
  "templateVersion": 1,
  "locale": "vi-VN",
  "recipientId": "customer-123"
}
```

Ví dụ không đưa toàn bộ dữ liệu cá nhân vào payload minh họa. Hệ thống có thể lưu snapshot model hoặc tham chiếu dữ liệu theo chính sách riêng; cần cân nhắc tính nhất quán, quyền riêng tư và thời gian lưu trữ.

## 18. Ghi nhận để có thể điều tra và tái tạo email

Khi người dùng báo “email tôi nhận được khác với email trên màn hình”, đội vận hành cần biết message được tạo từ template và dữ liệu nào.

Metadata hữu ích:

| Metadata | Mục đích |
| --- | --- |
| `notificationId` | ID nghiệp vụ để theo dõi một yêu cầu gửi |
| `templateKey` | Loại email |
| `templateVersion` | Phiên bản nội dung đã render |
| `dataSchemaVersion` | Schema của model đầu vào |
| `locale` | Ngôn ngữ/định dạng |
| `renderedAt` | Thời điểm render |
| `contentHash` | Hash của template hoặc nội dung render để đối chiếu |
| `providerMessageId` | ID do dịch vụ gửi cung cấp nếu có |
| `deliveryStatus` | Trạng thái gửi/giao theo dữ liệu provider |

Không phải lúc nào cũng cần lưu toàn bộ HTML và model. Nếu lưu:

- Xác định thời hạn lưu và quyền truy cập.
- Không ghi token, mật khẩu hoặc dữ liệu nhạy cảm không cần thiết.
- Có thể lưu hash và version thay vì bản sao nội dung nếu đủ cho mục đích đối chiếu.
- Nếu cần tái tạo chính xác, cần snapshot dữ liệu tối thiểu và template bất biến; chỉ lưu tên template là chưa đủ nếu nội dung version có thể bị sửa.

Template đã publish nên được xem là immutable. Nếu sửa trực tiếp nội dung version cũ, metadata `templateVersion=2` không còn xác định được email nào đã được render trước và sau lần sửa.

## 19. Kiểm soát rollout và rollback

Khi phát hành template version mới, có thể rollout theo từng giai đoạn:

1. **Publish version mới** ở trạng thái chưa active.
2. Render thử bằng model đại diện cho schema đang hỗ trợ.
3. Cho một tỷ lệ nhỏ email hoặc một nhóm tenant dùng version mới.
4. Theo dõi lỗi render, thiếu biến, lỗi delivery và phản hồi nội dung.
5. Mở rộng phạm vi nếu kết quả phù hợp.
6. Nếu có vấn đề, chuyển alias `current` về version trước hoặc ngừng chọn version mới cho request mới.

Rollback template không tự khôi phục event payload đã thay đổi. Nếu producer đã ngừng phát schema cũ, template v1 có thể không nhận được model mới. Vì vậy, **rollback cần xem cả template version lẫn data schema version**.

### Bảng tương thích khi rollout

| Producer | Model/adapter | Template | Kết quả mong muốn |
| --- | --- | --- | --- |
| Producer V1 | Data V1 | Template V1 | Hoạt động như trước |
| Producer V1 | Adapter V1 → V2 | Template V2 | Hoạt động nếu adapter cung cấp contract hợp lệ |
| Producer V2 | Data V2 | Template V2 | Hoạt động với field mới |
| Producer V2 | Data V2 | Template V1 | Hoạt động nếu V1 chỉ cần field cũ và adapter giữ semantics |
| Producer V1 | Data V1 không adapter | Template V2 yêu cầu field mới | Có nguy cơ lỗi hoặc thiếu nội dung |

Đây là ma trận cần được xác định trong thiết kế rollout; không nên giả định mọi tổ hợp đều tương thích.

## 20. Quản lý thay đổi template trong Git

Với template được đóng gói trong repository, nên lưu từng version như một artifact riêng:

```text
templates/mail/order-confirmation/
  v1.html
  v2.html
  v3.html
```

Lợi ích:

- Review thấy rõ version nào được thêm hoặc thay đổi.
- Có thể tìm commit đã giới thiệu template.
- Rollback code có thể khôi phục template tương ứng.
- Không làm thay đổi nội dung đã publish của version cũ.

Nếu dùng một file `order-confirmation.html` duy nhất và ghi đè mỗi lần sửa, versioning phải được quản lý ở commit/release hoặc registry khác. Cách này có thể đủ cho ứng dụng nhỏ, nhưng khó render lại một email cũ nếu template cũ không còn trong artifact đang chạy.

### Quy ước tên file

Tên nên chứa:

- Template key ổn định: `order-confirmation`.
- Version: `v1`, `v2`.
- Locale nếu lưu tách file: `vi-VN`, `en-US`.

Ví dụ:

```text
order-confirmation/v2/vi-VN.html
order-confirmation/v2/en-US.html
```

Không nên nhúng số version vào business event name hoặc subject email; đó là metadata vận hành, không phải nội dung người nhận cần thấy.

## 21. Các lỗi thường gặp khi versioning template

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Template mới không render event cũ | Model cũ thiếu field bắt buộc | Adapter, fallback có chủ đích hoặc giữ renderer cũ |
| Email có dòng trống/thiếu thông tin | Field optional không có quy tắc hiển thị | Định nghĩa fallback hoặc ẩn section |
| Template cũ hiển thị sai dữ liệu mới | Field giữ tên nhưng đổi ý nghĩa/đơn vị | Dùng schema version và field mới |
| Queue backlog phát sinh lỗi sau deploy | Worker nhận payload cũ nhưng chỉ còn template/schema mới | Giữ hỗ trợ version cũ hoặc migrate queue có kiểm soát |
| Rollback không hoạt động | Producer đã chuyển schema nhưng template quay về version cũ | Duy trì adapter tương thích hoặc rollback đồng bộ producer |
| Không xác định được email dùng template nào | Không lưu template version thực tế | Ghi metadata render và provider ID |
| Locale bị trộn | Fallback ngôn ngữ không được định nghĩa | Chọn locale theo policy và ghi nhận |
| Một tenant nhận nội dung khác tenant khác | Template alias được cập nhật theo tenant/rollout | Ghi selection context và version đã resolve |
| Email cũ thay đổi khi render lại | Nội dung template version cũ bị sửa đè | Xem published version là immutable |
| Template render thành công nhưng sai nghiệp vụ | Field đổi semantics mà contract không đổi | Version schema khi thay đổi ý nghĩa |
| Không thể replay dead-letter event | Adapter/template cũ đã bị xóa | Định nghĩa retention cho schema và template versions |
| Template mới bị chọn cho event không tương thích | Chọn `current` tại thời điểm gửi mà không kiểm tra schema | Resolver phải kiểm tra cặp template/schema |

### Phân biệt lỗi render và lỗi SMTP

```text
Resolve template version
        |
        +-- version không tồn tại --> Selection error
        |
        v
Adapt data schema
        |
        +-- thiếu dữ liệu bắt buộc --> Contract error
        |
        v
Render HTML/text
        |
        +-- lỗi biểu thức/template --> Render error
        |
        v
Build MimeMessage
        |
        +-- địa chỉ/MIME không hợp lệ --> Message error
        |
        v
JavaMailSender -> SMTP
        |
        +-- timeout/auth/quota/relay --> Transport error
```

Retry chỉ phù hợp với những lỗi có khả năng tự hết, chẳng hạn lỗi mạng tạm thời. Template không tồn tại hoặc model thiếu trường bắt buộc cần được sửa contract/deployment; retry SMTP không giải quyết được.

## 22. Những nguyên tắc quan trọng

1. **Version template và version dữ liệu riêng biệt.** Chúng liên kết qua contract, không nên gộp thành một con số duy nhất.
2. **Giữ contract rõ ràng.** Tên, kiểu, ý nghĩa, nullability, locale và format của field phải được mô tả.
3. **Ưu tiên thay đổi additive.** Thêm field optional và fallback trước khi biến nó thành bắt buộc.
4. **Không đổi semantics tại chỗ.** Nếu ý nghĩa field thay đổi, phát hành schema mới hoặc field mới.
5. **Giữ version cũ đủ lâu.** Queue, retry, dead-letter và lịch sử gửi có thể còn tham chiếu.
6. **Dùng adapter cho migration.** Chuyển đổi dữ liệu ở tầng có kiểu rõ ràng, không giấu logic trong template.
7. **Pin hoặc resolve version theo chính sách.** Với mỗi loại email, xác định version được chọn lúc tạo request hay lúc gửi.
8. **Published template nên bất biến.** Muốn chỉnh sửa thì phát hành version mới.
9. **Ghi metadata version thực tế.** Lưu template key/version, schema version, locale và notification ID khi cần điều tra.
10. **Rollback cả hai phía.** Template và producer/model cần tương thích với nhau khi quay về version cũ.

## 23. Tình huống tự luyện

### Tình huống A: thêm trường tổng tiền vào email

Template v1 chỉ dùng `customerName` và `orderCode`. Template v2 thêm `totalAmountLabel`, nhưng queue vẫn còn event v1.

**Cách xử lý:** giữ hỗ trợ schema v1, dùng adapter đưa dữ liệu v1 sang model v2 với `totalAmountLabel` là null, và để template v2 ẩn phần tổng tiền khi thiếu. Nếu tổng tiền là nội dung bắt buộc theo nghiệp vụ, không được giả lập giá trị; phải tra dữ liệu có thẩm quyền hoặc tiếp tục dùng luồng v1 phù hợp.

### Tình huống B: đổi `deliveryDate` từ ngày dự kiến sang ngày cam kết

Tên field không đổi nhưng ý nghĩa đã thay đổi.

**Cách xử lý:** đây là breaking change về semantics. Dùng field mới như `committedDeliveryDate` hoặc schema mới; không tiếp tục truyền ngày cam kết vào field cũ trong khi template cũ hiểu là ngày dự kiến.

### Tình huống C: template v3 chỉ đổi màu sắc và font

Model không thay đổi.

**Cách xử lý:** có thể tăng template version hoặc patch theo quy ước dự án; không cần tăng data schema version nếu contract không đổi.

### Tình huống D: event v1 được replay sau ba tháng

Template v1 đã bị xóa sau khi deploy v2.

**Cách xử lý:** cần chính sách retention cho template và adapter. Nếu replay phải tái tạo nội dung ban đầu, giữ v1 bất biến. Nếu cho phép dùng template hiện tại, cần chuyển schema có kiểm soát và ghi nhận version thực tế đã render.

### Tình huống E: một tenant thử template mới trước các tenant khác

**Cách xử lý:** resolver có thể chọn version theo tenant/rollout cohort, nhưng phải ghi selection metadata. Không để template key hoặc version đến trực tiếp từ input người dùng; registry chỉ cho phép các bản đã publish và được phê duyệt.

## 24. Kết luận

Versioning template email không chỉ là đổi tên file từ `v1.html` sang `v2.html`. Điều cần quản lý là **sự tương thích giữa nội dung template, data contract, event đang chờ xử lý và logic renderer**. Template version mô tả cách trình bày; data schema version mô tả dữ liệu mà template được phép nhận. Hai phần có thể thay đổi độc lập nhưng phải được nối với nhau bằng một hợp đồng rõ ràng.

Trong Spring Framework Mail, nên dùng DTO riêng cho mail model, adapter để chuyển đổi schema cũ/mới, template version bất biến và resolver chọn phiên bản theo chính sách. Với thay đổi tương thích, ưu tiên thêm field optional và fallback rõ ràng; với thay đổi phá vỡ, phát hành version mới và triển khai theo giai đoạn. Lưu metadata version thực tế giúp điều tra, replay và rollback chính xác. Khi producer, model và template được nâng cấp có kế hoạch, ứng dụng có thể thay đổi nội dung email mà vẫn xử lý được dữ liệu cũ và các event đang nằm trong queue.
