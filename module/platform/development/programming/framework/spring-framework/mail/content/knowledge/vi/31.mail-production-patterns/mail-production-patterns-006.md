# Template registry và phiên bản nội dung

Trong một hệ thống **Spring Framework Mail** hoạt động ở production, email không chỉ là vài chuỗi **subject**, **text** và **HTML** được viết trực tiếp trong Java. Một sản phẩm có thể gửi email xác thực, biên nhận, thông báo bảo mật, hóa đơn, thay đổi lịch hẹn và chiến dịch chăm sóc khách hàng bằng nhiều ngôn ngữ, cho nhiều tenant, qua nhiều provider. Nội dung phải thay đổi theo thời gian nhưng vẫn giữ khả năng kiểm soát, đối soát và tái hiện những gì từng được gửi.

**Template registry** là một kho đăng ký mẫu email cùng metadata, hợp đồng dữ liệu, phiên bản, trạng thái phê duyệt và quy tắc chọn mẫu. Ứng dụng không phải hard-code toàn bộ HTML vào business service; nó yêu cầu một mẫu bằng **template key**, **locale**, **tenant/brand** và một **phiên bản xác định**. Registry trả về một bản nội dung đã được đăng ký phù hợp, sau đó template engine kết xuất thành phần Subject, plain text và HTML để gửi qua **JavaMailSender**.

**Phiên bản nội dung** rất quan trọng: nếu ngày hôm nay thay đổi câu chữ của email “Đơn hàng đã xác nhận”, một notification được enqueue hôm qua nhưng gửi lại ngày mai phải dùng mẫu nào? Nếu không quyết định từ trước, cùng một notification logic có thể tạo ra nội dung khác nhau ở các lần retry, gây sai lệch audit, thông tin giá và quy tắc pháp lý.

Tài liệu này hướng dẫn thiết kế template registry và quản lý version **theo tư duy production**: danh tính và hợp đồng của template; workflow draft–approve–publish; phiên bản bất biến; lựa chọn theo locale/tenant; kiểm soát variables; tích hợp Spring Mail và Thymeleaf; pin version trong outbox; cache; rollout/rollback; bảo mật; thử nghiệm; monitoring và runbook.

> **Nguyên tắc cốt lõi:** Một bản template đã **published** và từng được sử dụng phải được coi là **immutable**. “Rollback” nghĩa là đổi con trỏ active sang một phiên bản đã được duyệt, **không sửa đè nội dung lịch sử**. Với email cần tính nhất quán, notification/outbox phải lưu rõ phiên bản và dữ liệu đầu vào đã được chốt.

## 1. Vấn đề của việc hard-code template trong code

Một cách triển khai đơn giản:

~~~java
String subject = "Xác nhận đơn " + orderId;
String html = "<h1>Xin chào " + customerName + "</h1>";
mailSender.send(...);
~~~

Cách này có thể phù hợp cho demo, nhưng trong production có nhiều hạn chế:

- Mỗi lần đổi câu chữ phải sửa code, chạy test và triển khai lại.
- Nội dung email lẫn vào logic nghiệp vụ, khó cho nhóm nội dung/pháp chế duyệt.
- Không xác định được bản nội dung từng gửi nếu template bị sửa tại chỗ.
- Khó hỗ trợ nhiều ngôn ngữ, tenant, thương hiệu và loại email.
- Không có schema biến đầu vào: thiếu biến có thể chỉ phát hiện khi gửi.
- Không có preview, lịch sử người duyệt, changelog hoặc rollback nhanh.
- Không thể rollout có kiểm soát theo môi trường, tenant hay tỷ lệ.
- Các lần retry có thể kết xuất lại với nội dung mới ngoài ý định.

Một registry giải quyết các vấn đề quản lý và chọn nội dung. Nó **không tự thay thế** hệ thống gửi mail, transactional outbox, MIME helper hoặc khả năng kiểm tra quyền gửi.

## 2. Các thành phần trong thiết kế

~~~text
Business Application
       |
       v
Notification Service
       |
       +--> Delivery policy (consent/suppression)
       |
       +--> Template Resolution
       |       |
       |       +--> Template Registry
       |       +--> Active Revision Mapping
       |       +--> Locale/Tenant Fallback Policy
       |       '--> Variables Contract
       |
       +--> Template Renderer
       |       |
       |       +--> Subject
       |       +--> text/plain
       |       '--> text/html
       |
       '--> Mail Composer
               |
               +--> MIME / attachments / CID
               |
               v
           JavaMailSender
               |
               v
           SMTP Provider
~~~

Nếu dùng outbox:

~~~text
Business Transaction
        |
        v
Notification Outbox + pinned template revision
        |
        v
Worker loads immutable template revision
        |
        v
Render + Compose MIME
        |
        v
SMTP submission
~~~

Các vai trò nên tách:

| Thành phần | Trách nhiệm | Không nên làm |
| --- | --- | --- |
| **Business service** | Chọn loại notification và dữ liệu nghiệp vụ | Chứa HTML/email layout dài |
| **Template registry** | Lưu template/version/metadata/activation | Gửi SMTP trực tiếp |
| **Resolver** | Chọn đúng revision theo policy | Tự sửa published body |
| **Variable validator** | Kiểm tra hợp đồng model | Thầm lặng bỏ qua biến quan trọng |
| **Renderer** | Kết xuất text/HTML/subject | Quyết định quyền gửi mail |
| **MIME composer** | Tạo MimeMessage và attachments | Thay đổi nội dung đã được duyệt |
| **Mail sender** | Nộp thư qua SMTP | Coi SMTP accepted là Inbox delivered |
| **Outbox worker** | Retry/delivery và lưu outcome | Chọn nội dung mới ngẫu nhiên ở mỗi retry |

## 3. Từ khóa định danh template đến revision

Trước hết cần phân biệt **mẫu logic** và **bản nội dung cụ thể**.

Ví dụ:

~~~text
Template key:
  ORDER_CONFIRMED

Locale:
  vi-VN

Brand:
  retail-main

Variant:
  default

Published revision:
  17

Content hash:
  sha256:...
~~~

Một cặp **template key + locale + brand + variant** có thể có nhiều revisions. Mỗi revision là một snapshot bất biến gồm subject, body, metadata và schema model (hoặc tham chiếu bất biến tới schema).

### Các loại định danh

| Trường | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **templateKey** | ORDER_CONFIRMED | Loại email logic, ổn định |
| **locale** | vi-VN | Ngôn ngữ/khu vực nội dung |
| **brand/tenant scope** | retail-main | Bộ nhận diện hoặc nội dung theo tenant |
| **variant** | default, short | Biến thể được thiết kế có chủ đích |
| **revisionId** | UUID | Định danh duy nhất một bản nội dung |
| **versionNumber** | 17 | Số phiên bản dễ đọc trong một scope |
| **active pointer** | revision 17 | Bản được chọn cho yêu cầu mới |
| **contentHash** | SHA-256 | Dấu vết bytes nội dung canonical |
| **schemaVersion** | 3 | Phiên bản hợp đồng biến dữ liệu |

**revisionId** không phải **notificationId**. Một revision có thể được dùng cho hàng triệu notification; một notification nên pin một revision và một model snapshot có nghĩa khi cần tái hiện.

### Template key không phải là filename

Không nên dùng tên tệp **order-confirmed-17.html** như khóa nghiệp vụ duy nhất. Filename là cách lưu trữ; registry có thể dùng database, object storage hoặc artifact bundle. **Template key** phải là định danh logic độc lập vị trí vật lý.

## 4. Template registry lưu gì?

Một registry production không chỉ chứa đoạn HTML. Một record có thể gồm:

~~~text
Template Definition
  - templateKey: PASSWORD_RESET
  - ownerTeam: identity-platform
  - purpose: SECURITY
  - allowedChannels: EMAIL
  - defaultLocale: vi-VN
  - complianceClassification: TRANSACTIONAL

Template Revision
  - revisionId
  - locale / brand / variant
  - subjectTemplate
  - plainTextTemplate
  - htmlTemplate
  - variableSchemaVersion
  - assetManifest
  - contentHash
  - lifecycleStatus
  - createdBy / reviewedBy / approvedAt
  - createdAt / publishedAt

Template Activation
  - environment / tenant scope
  - templateKey / locale / brand / variant
  - activeRevisionId
  - effectiveFrom
  - activatedBy / reason
~~~

### Phân biệt nội dung và cấu hình vận chuyển

Registry nên xác định **nội dung, layout, biến và nguồn asset**. Thông tin như SMTP credentials, provider access token và retry policy không thuộc template body. Các chính sách From/Reply-To có thể được tham chiếu bằng **verified sender profile** do mail service quản lý, thay vì cho tác giả template nhập địa chỉ bất kỳ.

### Mẫu có thể gồm nhiều phần

| Phần | Công dụng |
| --- | --- |
| **Subject** | Chủ đề mail, thường có biến |
| **Preheader** | Dòng preview, có thể được đưa vào HTML |
| **Plain text** | Bản đọc được nếu client không render HTML |
| **HTML** | Nội dung có định dạng |
| **CTA label/link** | Văn bản/đường dẫn hành động được tạo an toàn |
| **Inline asset manifest** | Logo, icon theo revision |
| **Attachment policy** | Cho phép loại attachment, không nhất thiết lưu bytes tại registry |
| **Variable schema** | Trường bắt buộc, kiểu dữ liệu, formatter, default |
| **Locale metadata** | Ngôn ngữ và quy tắc formatting |

Một bản email hoàn chỉnh có thể có nhiều nội dung tham chiếu chung. Nếu layout/header/footer là một template khác, phải **pin phiên bản dependencies** hoặc tạo snapshot bundle; nếu không, phần layout đổi sẽ khiến revision cũ render khác mà không ai thay revision đó.

## 5. Immutable revisions và mutable active pointer

Đây là ranh giới quan trọng nhất.

~~~text
ORDER_CONFIRMED / vi-VN
   |
   +-- Revision 15 (PUBLISHED, immutable)
   +-- Revision 16 (PUBLISHED, immutable)
   +-- Revision 17 (PUBLISHED, immutable)
   '-- Revision 18 (DRAFT, editable before publish)

Active pointer ----> Revision 17
~~~

Khi rollback:

~~~text
Before rollback: active -> Revision 17
After rollback:  active -> Revision 16

Revision 16/17 không thay đổi bytes.
~~~

### Vì sao không sửa published version tại chỗ?

Giả sử một notification đã được tạo với revision 17. Nếu nhân viên sửa HTML của revision 17 mà không tạo revision mới:

- Event audit không tái hiện được nội dung từng gửi.
- Retry cùng notification có thể thay đổi văn bản.
- Cache có thể giữ bản cũ trong khi database chứa bản mới.
- Hệ thống so sánh kết quả theo version sẽ cho số liệu sai.
- Phê duyệt cũ không còn bảo đảm cho nội dung mới.

**Revision sau publish là bất biến**; chỉnh sửa phải tạo revision 18. Cùng nguyên tắc áp dụng cho inline assets và templates phụ thuộc.

### Draft có thể chỉnh sửa, nhưng cần ghi nhận lịch sử

Một draft có thể cập nhật nhiều lần; khi workflow yêu cầu review, nên snapshot chính xác bản được gửi đi duyệt. Có thể dùng **draft generation** hoặc tạo revision immutable ở thời điểm submit for review để người duyệt không bị kiểm tra “bản đang di chuyển”.

### Cùng tên phiên bản không bảo đảm cùng nội dung

Một human-readable version như **v1.2** có thể bị trùng do thao tác nhập liệu. Sử dụng revisionId/unique constraint và contentHash; không dùng string “v1.2” một mình làm khóa bất biến.

## 6. Vòng đời một template

Một state machine minh họa:

~~~text
        Create
          |
          v
        DRAFT
          |
          v
      VALIDATING
        |     |
   Failed     Passed
        |     |
        v     v
       DRAFT  IN_REVIEW
                  |
              +---+---+
              |       |
           Rejected  Approved
              |       |
              v       v
             DRAFT   APPROVED
                       |
                       v
                   PUBLISHED
                       |
                 +-----+------+
                 |            |
                 v            v
             DEPRECATED    REVOKED
~~~

Đây là mô hình ứng dụng, không phải state machine mặc định của Spring Mail.

### Nghĩa từng trạng thái

| Trạng thái | Ý nghĩa | Có được dùng cho gửi production mới? |
| --- | --- | --- |
| **DRAFT** | Nội dung đang soạn | Không |
| **VALIDATING** | Kiểm tra schema, syntax, preview/tests | Không |
| **IN_REVIEW** | Đang được duyệt | Không |
| **APPROVED** | Đã phê duyệt bản snapshot | Chưa, nếu chưa activation |
| **PUBLISHED** | Có thể được activation theo policy | Có, khi active |
| **DEPRECATED** | Không còn chọn cho yêu cầu mới | Có thể cho retry đã pin theo policy |
| **REVOKED** | Nội dung bị cấm sử dụng, kể cả retry nếu policy yêu cầu | Không; cần xử lý theo quy trình khẩn cấp |

**PUBLISHED** và **ACTIVE** không đồng nghĩa. Một revision published có thể không được chọn bởi active pointer, hoặc chỉ active ở staging/cho một số tenants.

### Không xóa revision lịch sử để “ngừng dùng”

Nếu một revision từng gửi email, metadata và hash của nó có giá trị audit. Có thể thu hồi quyền phát sinh thư mới bằng active pointer/revocation policy. Việc xóa/ẩn dữ liệu thực tế vẫn phải tuân thủ retention và privacy rules, nhưng **không mặc định xóa revision** khi bỏ dùng.

## 7. Luồng tác giả, reviewer và người vận hành

Một workflow thực tế:

~~~text
Content Author
    |
    v
Create draft revision
    |
    v
Edit subject / plain / HTML / translations
    |
    v
Run validation + render preview
    |
    v
Submit immutable review snapshot
    |
    v
Reviewer approves exact revision hash
    |
    v
Release operator publishes
    |
    v
Activate for chosen environment/tenants
    |
    v
Monitor delivery / bounce / user feedback
    |
    v
Keep or rollback active pointer
~~~

### Tách quyền hạn

- **Author:** tạo/chỉnh draft.
- **Reviewer:** xác nhận nội dung và schema, không được duyệt bản tự thay đổi sau lúc xem.
- **Publisher:** phát hành revision đã được duyệt.
- **Operator:** kích hoạt, tắt hoặc rollback phiên bản theo policy.
- **Auditor:** xem lịch sử approval, hash, phạm vi đã active, không nhất thiết có quyền chỉnh sửa.

Với email bảo mật, pháp lý hoặc tài chính, có thể cần người duyệt độc lập, đánh giá accessibility và compliance. Quy tắc hai người (four-eyes principle) cần phù hợp quy trình tổ chức; Spring Framework Mail không tự áp dụng các quyền này.

### Phê duyệt phải gắn với content hash

Nếu reviewer duyệt HTML A nhưng tác giả sửa draft thành HTML B trước lúc publish, approval đã mất ý nghĩa. Tại thời điểm duyệt, ghi **revisionId + contentHash + variableSchemaVersion + assetBundleHash** để publish biết đúng bản nào đã được phê duyệt.

## 8. Template manifest và hợp đồng dữ liệu

Một template cần khai báo nó mong chờ dữ liệu gì, loại nào và cách xử lý khi thiếu.

Ví dụ manifest (cú pháp ứng dụng tự định nghĩa):

~~~yaml
templateKey: ORDER_CONFIRMED
locale: vi-VN
brand: retail-main
variant: default
version: 17
purpose: TRANSACTIONAL
renderer: THYMELEAF
requiredVariables:
  - name: customerDisplayName
    type: STRING
    maxLength: 120
  - name: orderCode
    type: STRING
    maxLength: 64
  - name: total
    type: MONEY
    currencyField: currency
  - name: orderLink
    type: VERIFIED_URL
optionalVariables:
  - name: supportContact
    type: STRING
    default: "Bộ phận hỗ trợ"
assets:
  logo: "sha256:immutable-logo-blob-hash"
senderProfile: "retail-transactional"
~~~

**MONEY**, **VERIFIED_URL** và toàn bộ manifest schema ở đây là quy ước nghiệp vụ, không phải kiểu của Thymeleaf. Production cần một validator có schema chính thức, ràng buộc định dạng và chính sách URL/sender cụ thể.

### Lợi ích của manifest

- Phát hiện biến bắt buộc thiếu trước khi SMTP gửi.
- Ngăn dùng một biến sai kiểu cho URL/tiền tệ.
- Xác định template có tương thích với event/model version không.
- Cho phép editor và preview tự hiển thị form nhập variables mẫu.
- Định nghĩa giới hạn độ dài và fallback hiển thị.
- Tạo bộ test fixture cho nhiều locale/tenant.
- Ghi được nội dung/biến nào đã được duyệt tại revision cụ thể.

### Không mặc định mọi giá trị null thành chuỗi rỗng

Nếu **orderCode** thiếu mà renderer vẫn gửi Subject “Xác nhận đơn ”, email không còn đúng nghiệp vụ. Biến bắt buộc nên **fail closed** với một error category rõ; biến tùy chọn mới có thể dùng default đã được khai báo và kiểm chứng.

## 9. Schema biến: kiểu dữ liệu, default và formatters

Trong một registry tốt, model variables không chỉ là **Map<String, Object>** truyền tùy ý.

| Loại dữ liệu | Ví dụ | Validation/formatting |
| --- | --- | --- |
| **STRING** | customerDisplayName | Không null, max length, Unicode |
| **INTEGER** | quantity | Phạm vi số hợp lệ |
| **DECIMAL** | totalAmount | Độ chính xác, scale, đơn vị tiền |
| **MONEY** | total + currency | Locale-specific display, không dùng double cho giá trị kế toán |
| **DATE / INSTANT** | appointmentAt | Timezone, date pattern theo locale |
| **BOOLEAN** | showSupportLink | Render có điều kiện |
| **ENUM** | deliveryStatus | Danh sách giá trị cho phép |
| **URL** | orderLink | HTTPS, trusted host, path/query hợp lệ |
| **LIST** | lineItems | Giới hạn số phần tử, cấu trúc từng item |
| **OBJECT** | shippingAddress | Field schema lồng nhau, xử lý PII |

### Money và timezone phải được xác định

Đừng chỉ gọi **amount.toString()** cho email đa ngôn ngữ rồi mặc định người dùng sẽ hiểu giá trị. Cần biết currency, locale, rounding policy và dữ liệu nguồn. Tương tự, một Instant phải được chuyển sang timezone của người nhận hoặc nghiệp vụ, không lấy timezone mặc định của container một cách tình cờ.

Ví dụ hàm chuẩn hóa:

~~~java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

public final class MoneyFormatter {

    public String format(
            BigDecimal amount,
            Currency currency,
            Locale locale
    ) {
        if (amount == null || currency == null || locale == null) {
            throw new IllegalArgumentException("Money data missing");
        }

        NumberFormat format = NumberFormat.getCurrencyInstance(locale);
        format.setCurrency(currency);
        return format.format(amount);
    }
}
~~~

Đoạn code minh họa cách format hiển thị; quy tắc làm tròn và minimum/maximum fraction digits của nghiệp vụ vẫn cần xác định riêng. Không dùng chuỗi đã format để tính tiền lại.

### Chỉ cho phép default với biến thực sự tùy chọn

~~~text
supportContact missing
  -> default "Bộ phận hỗ trợ" theo revision/locale

orderCode missing
  -> RENDER_VALIDATION_FAILED
  -> Không gửi email xác nhận đơn không có mã đơn
~~~

Default cũng là **một phần nội dung versioned**. Nếu default string thay đổi, revision nên thay theo; nếu default được lưu ở cấu hình toàn cục, nội dung lịch sử có thể không còn tái tạo chính xác.

### Tránh render dữ liệu “sống” ngẫu nhiên

Không nên để template trực tiếp gọi database/API khi render:

~~~text
Rendering ORDER_CONFIRMED
  -> calls orderService.getLatestPrice()
  -> calls currencyService.getTodayRate()
  -> calls userService.getCurrentName()
~~~

Khi retry vài ngày sau, giá hoặc chiết khấu có thể đổi và email cùng notification sẽ sai. Tốt hơn là **business service tạo model snapshot** tại thời điểm nghiệp vụ quyết định gửi, bao gồm giá trị đã chốt và link đã được phát hành theo policy.

## 10. Chọn template theo locale, tenant, brand và variant

Một resolver có thể nhận:

~~~java
public record TemplateSelector(
        String templateKey,
        String tenantId,
        String brand,
        String locale,
        String variant,
        String environment
) {
}
~~~

Những trường trên có mục đích khác nhau:

- **templateKey**: email logic cần gửi.
- **tenantId**: ai là chủ sở hữu/nhóm cấu hình nội dung.
- **brand**: bộ nhận diện hiển thị.
- **locale**: ngôn ngữ/khu vực.
- **variant**: biến thể được lựa chọn có kiểm soát.
- **environment**: dev, staging, production, không để staging trỏ nhầm production.

### Fallback locale có quy tắc, không đoán

Một ví dụ cho người nhận muốn **vi-VN**:

~~~text
Requested: vi-VN / brand-A / default
    |
    +-- 1. Exact locale + brand
    |
    +-- 2. Parent language vi + brand (if approved)
    |
    +-- 3. Default locale + brand
    |
    '-- 4. No eligible revision -> resolution failure
~~~

Một số nội dung có thể **không được phép fallback**: điều khoản pháp lý đặc thù vùng, email có thông tin quy định theo quốc gia, hoặc mẫu bảo mật phải được biên dịch và duyệt riêng. Fallback policy nên được định nghĩa theo template/purpose, không tự chọn “một ngôn ngữ có sẵn bất kỳ”.

### Tenant isolation quan trọng hơn convenience

Nếu tenant A không có mẫu riêng, có thể fallback sang **global template** được phê duyệt. Nhưng tuyệt đối không fallback sang mẫu tenant B, làm lộ branding, URL hoặc dữ liệu riêng.

~~~text
tenant-A exact revision
    -> tenant-A generic brand
    -> approved global revision
    -> ERROR

Không bao giờ -> tenant-B revision
~~~

### Variant và A/B testing

**Variant** có thể dùng để thử subject/layout. Với một notification, nên **chọn variant một lần** theo experiment assignment ổn định và lưu nó vào outbox. Nếu lần retry đổi từ variant A sang B, kết quả A/B test bị nhiễu và nội dung không nhất quán.

Chỉ thực hiện experiment khi email purpose và chính sách liên quan cho phép. Với email bảo mật hoặc pháp lý, thay đổi nội dung cần phê duyệt nghiêm ngặt hơn thử nghiệm marketing.

## 11. ResolvedTemplate là snapshot, không phải một lời hứa tra lại

Resolver nên trả về một bản revision có thể tái hiện:

~~~java
import java.time.Instant;
import java.util.Map;
import java.util.UUID;

public record ResolvedMailTemplate(
        UUID revisionId,
        String templateKey,
        String locale,
        String brand,
        String variant,
        int contentVersion,
        int schemaVersion,
        String subjectTemplate,
        String plainTextTemplate,
        String htmlTemplate,
        String contentHash,
        Instant publishedAt,
        Map<String, String> assetReferences
) {
}
~~~

### Immutable nghĩa là không nhận tham chiếu draft mutable

Không nên trả **TemplateDraft** có thể bị người khác sửa trong lúc render. Nên lấy snapshot immutable revision đã published, bảo đảm subject/plain/HTML/assets/schema cùng thuộc một revision nhất quán.

### Active pointer có thể thay đổi giữa hai lần query

~~~text
T1: Query subject -> active revision 17
T2: Operator activate revision 18
T3: Query HTML -> active revision 18
~~~

Email có Subject v17 và HTML v18 là kết quả sai. Resolver phải **chọn một revisionId trước**, rồi đọc toàn bộ nội dung bằng revisionId đó.

### Revision ID nên xuất hiện trong audit

~~~text
notification_id: 8a...
template_key: ORDER_CONFIRMED
template_revision_id: 6f...
template_hash: sha256:...
locale: vi-VN
variant: default
render_model_hash: sha256:...
sent_at: ...
smtp_submission_outcome: ACCEPTED
~~~

Không cần log toàn bộ model snapshot ra text logs vì có thể chứa dữ liệu cá nhân. Hash chỉ hỗ trợ kiểm chứng bytes theo canonicalization; muốn tái render còn phải giữ model snapshot và assets được phép lưu.

## 12. Data model với Java records và interfaces

Một API registry có thể được định nghĩa:

~~~java
import java.util.UUID;

public interface TemplateRegistry {

    ResolvedMailTemplate resolveActive(
            TemplateSelector selector
    );

    ResolvedMailTemplate getRevision(UUID revisionId);

    TemplateManifest getManifest(UUID revisionId);
}

public record TemplateManifest(
        UUID revisionId,
        int schemaVersion,
        java.util.List<VariableDefinition> variables,
        String senderProfile
) {
}

public record VariableDefinition(
        String name,
        VariableType type,
        boolean required,
        int maxLength,
        String formatter
) {
}

public enum VariableType {
    STRING, DECIMAL, MONEY, DATE, URL, BOOLEAN, LIST, OBJECT
}
~~~

Đây là contracts **do ứng dụng định nghĩa**, không phải interfaces Spring Mail có sẵn.

### Hai API có ý nghĩa khác nhau

- **resolveActive(selector)** dùng khi tạo notification mới và chưa được pin.
- **getRevision(revisionId)** dùng khi retry hoặc điều tra notification đã pin.

Không gọi lại resolveActive trong retry nếu chính sách yêu cầu giữ nguyên nội dung.

### Khi không có revision hợp lệ

Resolver nên trả lỗi phân loại:

~~~text
TEMPLATE_NOT_FOUND
TEMPLATE_NOT_ACTIVE
LOCALE_NOT_ALLOWED
TENANT_SCOPE_VIOLATION
TEMPLATE_REVOKED
SCHEMA_NOT_COMPATIBLE
ASSET_BUNDLE_MISSING
~~~

Không âm thầm chuyển sang templateKey khác hoặc gửi email trắng. Thiếu template production có thể cần alert và xử lý chính sách thay vì retry SMTP vô hạn.

## 13. Tổ chức lưu trữ trong PostgreSQL

Một thiết kế tối thiểu có ba nhóm bảng:

1. **mail_template_definition** — định danh logic và owner.
2. **mail_template_revision** — nội dung và metadata phiên bản, immutable sau publish.
3. **mail_template_activation** — mapping active revision theo scope.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE mail_template_definition (
    template_key VARCHAR(120) PRIMARY KEY,
    owner_team VARCHAR(120) NOT NULL,
    purpose VARCHAR(50) NOT NULL,
    default_locale VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE mail_template_revision (
    revision_id UUID PRIMARY KEY,
    template_key VARCHAR(120) NOT NULL
        REFERENCES mail_template_definition(template_key),
    tenant_scope VARCHAR(120) NOT NULL,
    brand VARCHAR(120) NOT NULL,
    locale VARCHAR(40) NOT NULL,
    variant VARCHAR(80) NOT NULL,
    version_number INTEGER NOT NULL,
    schema_version INTEGER NOT NULL,
    subject_template TEXT NOT NULL,
    plain_text_template TEXT NOT NULL,
    html_template TEXT NOT NULL,
    manifest_json JSONB NOT NULL,
    asset_bundle_hash VARCHAR(128),
    content_hash VARCHAR(128) NOT NULL,
    status VARCHAR(40) NOT NULL,
    created_by VARCHAR(120) NOT NULL,
    approved_by VARCHAR(120),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    approved_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    CONSTRAINT uq_template_revision_scope
        UNIQUE (
            template_key, tenant_scope, brand,
            locale, variant, version_number
        )
);

CREATE TABLE mail_template_activation (
    environment VARCHAR(40) NOT NULL,
    tenant_scope VARCHAR(120) NOT NULL,
    brand VARCHAR(120) NOT NULL,
    locale VARCHAR(40) NOT NULL,
    variant VARCHAR(80) NOT NULL,
    template_key VARCHAR(120) NOT NULL,
    active_revision_id UUID NOT NULL
        REFERENCES mail_template_revision(revision_id),
    activated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    activated_by VARCHAR(120) NOT NULL,
    PRIMARY KEY (
        environment, tenant_scope, brand,
        locale, variant, template_key
    )
);
~~~

Đây là schema minh họa, không phải database tables được Spring Mail tạo. **FK active_revision_id** chứng minh revision tồn tại nhưng **chưa đủ** để chứng minh nó cùng template key/locale/tenant và status PUBLISHED. Phải thêm transaction/service validation hoặc ràng buộc tham chiếu theo khóa scope phù hợp.

### Cần chặn UPDATE published revisions

Ứng dụng kiểm tra trạng thái chưa đủ nếu có nhiều đường ghi SQL. Có thể:

- Chỉ cấp quyền INSERT draft/new revision, hạn chế UPDATE những rows đã published.
- Thực hiện trigger hoặc stored procedure chặn thay đổi nội dung immutable.
- Dùng migration/phê duyệt có kiểm soát cho các thao tác đặc biệt.
- Bảo vệ stored assets khỏi overwrite cùng object key.

Việc sửa metadata audit hoặc thay status DEPRECATED có thể vẫn được phép nếu thiết kế riêng; **body, manifest và content hash** của revision published phải bất biến.

### Không dùng thứ tự version number như active policy

Version cao nhất không đồng nghĩa bản được dùng production. Revision 19 có thể là DRAFT, revision 18 đã PUBLISHED nhưng chỉ active cho tenant thử nghiệm, còn revision 17 active rộng. Chọn theo bảng activation, không **MAX(version_number)**.

## 14. Atomic activation và rollback

Khi kích hoạt revision 18, thao tác cần:

1. Xác minh revision đã được phê duyệt/published.
2. Kiểm tra cùng templateKey/tenant/brand/locale/variant được phép.
3. Kiểm tra active pointer hiện tại hoặc version stamp.
4. Đổi pointer trong một transaction ngắn.
5. Ghi audit event trước/sau.
6. Phát thông báo invalidation cache nếu dùng.

### Tránh race giữa hai operators

~~~text
Operator A đọc active=17, muốn activate=18.
Operator B đọc active=17, muốn rollback=16.
Nếu UPDATE không điều kiện, người cuối cùng ghi sẽ thắng.
~~~

Có thể dùng compare-and-set:

~~~sql
UPDATE mail_template_activation
SET
    active_revision_id = :new_revision_id,
    activated_at = CURRENT_TIMESTAMP,
    activated_by = :operator
WHERE environment = :environment
  AND tenant_scope = :tenant_scope
  AND brand = :brand
  AND locale = :locale
  AND variant = :variant
  AND template_key = :template_key
  AND active_revision_id = :expected_old_revision_id;
~~~

Nếu affected rows = 0, active pointer có thể đã thay đổi. API nên trả conflict, tải lại state rồi yêu cầu thao tác lại theo policy; không tự overwrite mà operator không biết.

### Đừng thực hiện external I/O trong transaction activation

Không giữ database transaction mở khi gửi notifications cho toàn bộ workers hoặc gọi service render. Commit pointer trước, sau đó phát cache invalidation event; consumers cần xử lý invalidation bị mất/stale bằng TTL/versioning.

### Rollback không xóa lịch sử

~~~text
14:00 active=17
14:30 active=18
14:45 rollback active=17

Activation audit:
  [14:30] 17 -> 18, reason campaign update
  [14:45] 18 -> 17, reason render regression
~~~

Nếu event đã được enqueue với revision 18 trong khoảng 14:30–14:45, không được âm thầm đổi chúng sang 17 chỉ vì rollback. Cần chính sách rõ cho pending jobs và trường hợp revoke khẩn cấp.

## 15. Rendering với Thymeleaf trong Spring

**Thymeleaf** là một lựa chọn template engine phổ biến khi tạo email HTML/text. Spring Framework Mail/JavaMailSender **không tự render Thymeleaf**; ứng dụng cần cấu hình template engine rồi đưa nội dung đã render cho MIME helper.

Ví dụ HTML thuộc revision:

~~~html
<!DOCTYPE html>
<html xmlns:th="http://www.thymeleaf.org" lang="vi">
<body>
  <h1 th:text="|Xin chào ${customerDisplayName}|">Xin chào</h1>
  <p>Đơn <strong th:text="${orderCode}">ORD-000</strong>
     đã được xác nhận.</p>
  <p>Tổng: <span th:text="${formattedTotal}">0 ₫</span></p>
  <a th:href="${orderLink}">Xem chi tiết</a>
</body>
</html>
~~~

Ví dụ text template:

~~~text
Xin chào [[${customerDisplayName}]],

Đơn [[${orderCode}]] đã được xác nhận.
Tổng: [[${formattedTotal}]]
Chi tiết: [[${orderLink}]]
~~~

Subject template (Thymeleaf TEXT mode):

~~~text
Xác nhận đơn [[${orderCode}]]
~~~

### Không dùng resolver sai cho registry

**ClassLoaderTemplateResolver** đọc template từ classpath; nó không tự biết body thuộc revision đang lưu trong database. Nếu registry trả về nội dung trực tiếp, có thể cấu hình **StringTemplateResolver**, dùng source string làm template content thay vì filename. Lựa chọn này cần kiểm soát ai được quyền nhập template, vì server-side template engines có khả năng biểu thức mạnh hơn plain placeholder replacement.

### Ví dụ renderer xử lý một immutable revision

~~~java
import java.util.Locale;
import java.util.Map;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;
import org.thymeleaf.templatemode.TemplateMode;
import org.thymeleaf.templateresolver.StringTemplateResolver;

public final class ThymeleafMailContentRenderer {

    private final TemplateEngine htmlEngine;
    private final TemplateEngine textEngine;

    public ThymeleafMailContentRenderer() {
        this.htmlEngine = engine(TemplateMode.HTML);
        this.textEngine = engine(TemplateMode.TEXT);
    }

    private static TemplateEngine engine(TemplateMode mode) {
        StringTemplateResolver resolver = new StringTemplateResolver();
        resolver.setTemplateMode(mode);
        resolver.setCacheable(false);

        TemplateEngine engine = new TemplateEngine();
        engine.setTemplateResolver(resolver);
        return engine;
    }

    public RenderedMailContent render(
            ResolvedMailTemplate revision,
            Map<String, Object> checkedModel
    ) {
        Locale locale = Locale.forLanguageTag(revision.locale());
        Context context = new Context(locale, checkedModel);

        String subject = textEngine.process(
                revision.subjectTemplate(), context
        );
        String plainText = textEngine.process(
                revision.plainTextTemplate(), context
        );
        String html = htmlEngine.process(
                revision.htmlTemplate(), context
        );

        if (subject.isBlank()
                || subject.contains("\r")
                || subject.contains("\n")) {
            throw new IllegalArgumentException(
                    "Rendered subject is invalid"
            );
        }

        return new RenderedMailContent(
                subject, plainText, html,
                revision.revisionId(),
                revision.contentHash()
        );
    }
}

public record RenderedMailContent(
        String subject,
        String plainText,
        String html,
        java.util.UUID revisionId,
        String contentHash
) {
}
~~~

Ví dụ có chủ đích tắt cache ở **StringTemplateResolver** để tránh cache nhầm theo source template text. Production có thể cache compiled templates theo **revisionId + contentHash** nếu engine/resolver hỗ trợ đúng, nhưng không dùng một tên key động như **ORDER_CONFIRMED** cho các bytes thay đổi mà không invalidation. Renderer ở trên giả định **checkedModel** đã được validate, các template là nguồn nội dung được phê duyệt và dependencies/expressions bị giới hạn theo chính sách.

### Render cùng một context cho ba phần

Subject, plain và HTML nên dùng một **model snapshot** và một **revisionId**, tránh:

~~~text
Subject: revision 18, order total = 250
Plain:   revision 17, order total = 200
HTML:    revision 18, order total = 220
~~~

Renderer có thể tạo object **RenderedMailContent** bất biến và được test không cần mở SMTP connection.

## 16. Nội dung template phải chống injection

Một khách hàng có tên:

~~~text
<img src=x onerror=alert(1)>
~~~

Nếu chuỗi được nối trực tiếp thành HTML không escape, markup do người dùng kiểm soát có thể đi vào email. Với Thymeleaf, **th:text** sử dụng escaping theo context; **th:utext** chèn HTML không escape và chỉ phù hợp cho nội dung đã được phê duyệt/sanitize theo policy.

### Các rủi ro theo ngữ cảnh

| Vị trí | Rủi ro | Biện pháp |
| --- | --- | --- |
| **HTML text** | HTML injection | Escaping đúng context |
| **HTML attribute** | Dữ liệu làm hỏng attribute | Attribute-aware rendering, validate |
| **URL** | Scheme nguy hiểm hoặc host giả | Allowlist HTTPS/host, URL builder |
| **Subject/Header** | CRLF/header injection | Reject CR/LF, giới hạn độ dài |
| **Plain text** | Nội dung gây hiểu lầm/lộ dữ liệu | Schema và content review |
| **CSS/inline styles** | Tracking/remote asset, client khác nhau | Asset policy, preview |
| **Dynamic template syntax** | Server-side template injection | Không cho dữ liệu người dùng làm template source |

### Không compile dữ liệu người dùng thành template

Sai:

~~~java
String templateSource = request.getParameter("html");
// Sau đó render như server-side template tin cậy.
~~~

Nếu người viết nội dung được phép tạo template trong registry, họ có quyền tiềm tàng lên cấu trúc render. Editor cần RBAC, allowlist template features và sandbox/engine restrictions nếu tác giả không hoàn toàn tin cậy. Chỉ sử dụng **StringTemplateResolver** với revision đã được review; không coi engine server-side là một sandbox an toàn mặc định.

### URLs nên được tạo bởi ứng dụng

Nếu email chứa link xác nhận:

~~~text
https://app.example.test/verify?token=...
~~~

Không để template nhận baseUrl tùy ý từ người dùng. Business service nên tạo URL bằng trusted configuration, encode query/path đúng cách, có TTL và one-time token theo policy. Template chỉ hiển thị URL đã được xác minh.

### Preview cũng phải an toàn

Trang quản trị preview HTML nên dùng sandbox/CSP phù hợp, không chạy script hoặc tự tải external resources chỉ vì template đã được lưu ở registry. Email clients có hành vi render khác nhau nhưng điều đó không biện minh cho việc cho phép HTML tùy ý có quyền như trang quản trị.

## 17. Tạo MimeMessage từ nội dung đã render

Sau khi resolver và renderer hoàn tất, **JavaMailSender** nhận nội dung cuối. Template registry không cần biết password SMTP, transport socket hoặc retries.

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class SpringMailComposer {

    private final JavaMailSender sender;

    public SpringMailComposer(JavaMailSender sender) {
        this.sender = sender;
    }

    public void submit(
            String verifiedFrom,
            String validatedRecipient,
            RenderedMailContent content
    ) throws Exception {
        MimeMessage message = sender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

        helper.setFrom(verifiedFrom);
        helper.setTo(validatedRecipient);
        helper.setSubject(content.subject());
        helper.setText(content.plainText(), content.html());

        sender.send(message);
    }
}
~~~

**MULTIPART_MODE_MIXED_RELATED** thường phù hợp khi có cả body alternatives, inline resources và attachments. Nếu không có attachments hoặc inline images, có thể chọn MIME mode đơn giản hơn theo nhu cầu và tính tương thích mail clients.

### MIME helper không đọc template registry

**MimeMessageHelper** giúp đặt From/To/Subject, plain/HTML, CID images và attachments; nó không chọn phiên bản nội dung cho ứng dụng. Tất cả quyết định về revision/locale/schema phải xảy ra trước.

### Đính kèm không nên phụ thuộc vào draft asset

Nếu revision 17 tham chiếu logo v3, khi gửi lại một notification dùng revision 17 sau một tháng, asset logo v3 vẫn phải có thể được lấy (trong giới hạn retention). Không nên luôn gọi **assetService.getLatestLogo()** rồi khiến nội dung version cũ thay đổi.

### SMTP accepted chưa phải delivered

**JavaMailSender.send(...)** thành công nói lên transport submission đã hoàn tất theo semantics tương ứng, không chứng minh người nhận đã thấy trong Inbox. Phần registry/version phục vụ **content consistency**; trạng thái delivered, bounced, complaint và unsubscribed cần theo dõi riêng qua mail providers khi áp dụng.

## 18. Pin phiên bản lúc nào: enqueue hay send?

Hai chiến lược có ý nghĩa khác nhau:

### Chiến lược A — Pin khi tạo notification

~~~text
T0 Business event xảy ra
   -> resolve active template revision 17
   -> snapshot model
   -> insert outbox(notification, revision 17, model)

T1 Operator activate revision 18

T2 Worker gửi notification cũ
   -> getRevision(17)
   -> render model snapshot
   -> send
~~~

**Ưu điểm:** mỗi notification có nội dung nhất quán; retry không đổi template; dễ audit. **Nhược điểm:** có thể gửi nội dung v17 đã lỗi hoặc hết hiệu lực nếu bị trì hoãn lâu, cần cơ chế revoke/expiry.

### Chiến lược B — Resolve ở thời điểm gửi lần đầu

~~~text
T0 Business event -> save notification intent + model
T1 Operator activate revision 18
T2 Worker first attempt
   -> resolve active revision 18
   -> persist pin 18
   -> send
T3 Retry same notification
   -> use pinned 18
~~~

**Ưu điểm:** có thể chọn nội dung mới nhất đã duyệt khi worker bắt đầu gửi. **Nhược điểm:** notification tạo cùng thời điểm nhưng được xử lý ở hai thời điểm khác nhau có thể dùng revisions khác nhau; cần chấp nhận và ghi rõ policy.

### Cả hai đều cần pin trước external side effect

Dù chọn A hay B, sau khi attempt đã được nộp SMTP, những retries/reconciliation liên quan phải giữ snapshot phù hợp. Nếu T2 gửi v18 và T3 resolve lại active v19 sau timeout, người nhận có thể nhận hai email với nội dung khác nhau.

### Các loại email thường chọn policy khác nhau

| Use case | Gợi ý pinning | Lý do |
| --- | --- | --- |
| **Receipt / invoice** | Pin lúc nghiệp vụ chốt | Số tiền và wording cần tái hiện |
| **Password reset / OTP** | Pin lúc tạo/sớm, có deadline ngắn | Tránh thay đổi link/code qua retry |
| **Security alert** | Pin version an toàn đã duyệt | Nội dung quan trọng, cần audit |
| **Scheduled marketing** | Theo campaign snapshot/activation policy | Campaign có lịch và phê duyệt riêng |
| **Product updates** | Có thể resolve ở dispatch trước attempt | Chấp nhận nội dung mới đã được duyệt |

Không có một chính sách duy nhất bắt buộc cho mọi sản phẩm, nhưng **quy tắc phải được định nghĩa và lưu lại**, không phụ thuộc vào thứ tự ngẫu nhiên worker chạy.

## 19. Render model cũng phải được version hoặc snapshot

Pin revision 17 nhưng mỗi lần retry gọi lại:

~~~text
orderService.findCurrentOrder(orderId)
~~~

vẫn có thể gây ra nội dung khác nhau. Chẳng hạn đơn hàng đã được hoàn tiền sau khi email xác nhận ban đầu được enqueue.

### Những gì cần chốt

Một snapshot có thể chứa:

~~~json
{
  "modelSchemaVersion": 3,
  "customerDisplayName": "Khách hàng",
  "orderCode": "ORD-1528",
  "totalAmount": "250000.00",
  "currency": "VND",
  "orderLinkId": "order-view-7b8"
}
~~~

Đối với **link nhạy cảm**, không nhất thiết phải lưu nguyên token trong model snapshot dài hạn. Có thể lưu một reference và định nghĩa rõ thời điểm phát hành token, TTL và retry semantics, hoặc render mail snapshot một lần rồi lưu MIME/subject/content được bảo vệ trong retention phù hợp. Chọn cách nào cũng phải cân bằng bảo mật với tính tái hiện.

### Model snapshot phải có schema version

Khi domain DTO thay đổi từ:

~~~text
v1: totalPrice -> STRING
v2: totalAmount -> DECIMAL, currency -> STRING
~~~

một notification pin revision cũ cần được render bằng đúng hợp đồng mà revision đó hỗ trợ. Đừng truyền DTO mới thẳng vào template cũ và hy vọng tên trường tự khớp.

### Re-render khác resend nguyên MIME

- **Re-render:** từ revision + model + formatter + assets; có thể phụ thuộc phiên bản renderer/runtime.
- **Resend MIME snapshot:** gửi lại bytes đã lưu, giữ nội dung chính xác hơn nhưng khó quản lý MIME headers, Message-ID, token TTL và retention.

Không có chiến lược nào bảo đảm exactly-once SMTP. Khi provider có thể đã accepted mà client timeout, cần **UNKNOWN/reconciliation** trước khi quyết định gửi lại.

### Định danh riêng lần gửi và phiên bản nội dung

Một notification:

~~~text
notificationId = N-101
revisionId = R-17
modelSnapshotId = M-101
attemptId = A-1, A-2, ...
~~~

**attemptId** thay theo mỗi lần thử; **notificationId**, **revisionId** và model snapshot ID thường giữ nguyên đối với cùng logical notification.

## 20. Outbox schema cho template version pinning

Một bảng outbox minh họa:

~~~sql
CREATE TABLE mail_notification_outbox (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(120) NOT NULL,
    notification_key VARCHAR(250) NOT NULL,
    purpose VARCHAR(60) NOT NULL,
    recipient_ref VARCHAR(180) NOT NULL,
    template_key VARCHAR(120) NOT NULL,
    template_revision_id UUID NOT NULL
        REFERENCES mail_template_revision(revision_id),
    template_hash VARCHAR(128) NOT NULL,
    model_schema_version INTEGER NOT NULL,
    model_snapshot_json JSONB NOT NULL,
    locale VARCHAR(40) NOT NULL,
    variant VARCHAR(80) NOT NULL,
    status VARCHAR(40) NOT NULL,
    available_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_notification_dedup
        UNIQUE (tenant_id, notification_key)
);

CREATE INDEX idx_mail_outbox_due
ON mail_notification_outbox (available_at, id)
WHERE status IN ('PENDING', 'RETRY_WAIT');
~~~

**recipient_ref** có thể trỏ đến recipient record được phân quyền thay vì lưu trực tiếp email address; nếu cần giữ địa chỉ tại thời điểm tạo notification, phải thiết kế snapshot/PII encryption/retention. **model_snapshot_json** cũng có thể chứa PII; cần mã hóa, phân quyền, purge policy và tránh ghi vào logs.

### Ghi vào cùng transaction nghiệp vụ khi cần

~~~text
BEGIN
  Update Order state
  Insert mail_notification_outbox(
      template_revision_id,
      model_snapshot_json,
      notification_key
  )
COMMIT
~~~

Nếu business data và outbox ở cùng transaction database, có thể bảo đảm ý định gửi được lưu cùng thay đổi nghiệp vụ. Việc SMTP accepted nằm ngoài transaction nên vẫn cần lease, retries và idempotency/reconciliation.

### Pinning khi worker lần đầu chọn revision

Nếu dùng policy resolve-on-first-send, cột template_revision_id có thể tạm null **trước** attempt đầu. Phải thay đổi schema cho phép null và thực hiện atomic update để hai workers không pin hai revision khác nhau. Không dùng schema NOT NULL ở trên rồi tuyên bố hỗ trợ null: đó là **hai thiết kế khác nhau**.

### Không sửa pinned revision do một lần retry SMTP lỗi

Một lỗi connect/refused hoặc 4xx không liên quan template. Worker nên giữ pinned revision và chỉ retry transport theo policy, không “chọn bản mới nhất” để chữa lỗi SMTP.

## 21. Kết hợp với transactional outbox và idempotency

Template registry giải quyết **which content**; transactional outbox giải quyết **durable notification intent**.

~~~text
OrderConfirmed event
      |
      v
Select revision 17 + model snapshot
      |
      v
Write outbox row with stable notification key
      |
      v
Worker claims job atomically
      |
      v
Render revision 17 + snapshot
      |
      v
Submit SMTP
      |
      +-- Accepted -> ACCEPTED
      +-- Proven not accepted retryable -> RETRY_WAIT
      +-- Permanent reject -> PERMANENT_FAILED
      '-- Unknown after network ambiguity -> UNKNOWN
~~~

### Outbox có thể được claim nguyên tử

Với PostgreSQL:

~~~sql
WITH candidate AS (
    SELECT id
    FROM mail_notification_outbox
    WHERE status IN ('PENDING', 'RETRY_WAIT')
      AND available_at <= CURRENT_TIMESTAMP
    ORDER BY available_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE mail_notification_outbox AS job
SET status = 'IN_FLIGHT',
    updated_at = CURRENT_TIMESTAMP
FROM candidate
WHERE job.id = candidate.id
RETURNING
    job.id,
    job.template_revision_id,
    job.model_snapshot_json;
~~~

Đây là ví dụ tối giản về claim, **chưa phải worker implementation đủ an toàn**: production cần lease owner/token, timeouts, attempt history, recovery, fencing, retry policy và phân loại outcome. Quan trọng là không có hai workers tự đọc PENDING rồi gửi trước khi sở hữu job.

### Content consistency không đồng nghĩa gửi đúng một lần

Nếu SMTP server nhận xong DATA rồi client mất response, worker có thể không biết thư đã accepted hay chưa. Dù template revision và model snapshot đã pin chính xác, retry vẫn có thể gửi bản trùng. **Immutable template giúp nội dung nhất quán, không tạo exactly-once delivery**.

### Dedup notification và template revision là hai khóa khác nhau

**notification_key** ngăn business event được enqueue trùng, còn **revisionId** định danh nội dung. Hai notification khác nhau có thể dùng cùng revision, không được gộp chúng chỉ vì cùng template key/version.

## 22. Thay đổi nội dung đối với notification đang chờ

Đây là một quyết định sản phẩm, không chỉ là thao tác SQL.

Giả sử:

~~~text
10:00  20.000 notification được enqueue với revision 17
10:15  Content team phát hiện revision 17 có câu chữ sai
10:20  Publish revision 18 và đổi active pointer
10:30  8.000 notification v17 vẫn chưa gửi
~~~

### Có ba nhóm cần phân biệt

1. **Chưa có attempt:** có thể cân nhắc policy migration nếu nội dung mới thật sự cần thiết.
2. **Đang IN_FLIGHT:** không đổi revision giữa lúc đang submit; outcome có thể không rõ.
3. **ACCEPTED/UNKNOWN:** không tự biến thành gửi lại revision 18; cần đối soát/rủi ro gửi trùng.

### Chiến lược xử lý pending revisions

| Chính sách | Hành vi | Khi phù hợp |
| --- | --- | --- |
| **Keep pinned** | Mọi notification v17 tiếp tục v17 | Thay đổi câu chữ không nghiêm trọng |
| **Pause + review** | Tạm dừng jobs v17 chưa gửi | Nội dung lỗi cần quyết định |
| **Migrate not-attempted** | Đổi selected jobs v17 sang v18 với audit | Nội dung cần thay và chưa submit |
| **Revoke** | Chặn dùng v17 cho cả future attempts | Lỗi bảo mật/pháp lý nghiêm trọng |
| **Cancel + recreate** | Hủy jobs chưa gửi, tạo notification mới theo business policy | Nội dung/sự kiện logic thực sự thay đổi |

### Migration phải có điều kiện

Không thực hiện:

~~~sql
-- Không nên chạy mù trên production:
UPDATE mail_notification_outbox
SET template_revision_id = :revision_18
WHERE template_revision_id = :revision_17;
~~~

Lệnh này có thể sửa cả jobs đã ACCEPTED/UNKNOWN và làm sai audit. Một migration hợp lệ phải giới hạn trạng thái chưa có attempt, kiểm tra model schema tương thích, ghi old/new revision, reason, operator và xác nhận từng batch. Nếu job đã gửi, cần quy trình **correction notice** riêng chứ không thay lén lịch sử.

### Revoke cần policy rõ

Một revision chứa URL nguy hiểm hoặc thông tin pháp lý sai có thể phải bị khóa kể cả với jobs đã pin. Điều đó không có nghĩa xóa revision; hệ thống giữ metadata và chuyển jobs chưa được gửi sang **NEEDS_REVIEW** hoặc hủy theo policy. Việc phát lại một email sửa lỗi cho người đã nhận là một **notification mới có chủ đích**, không phải retry âm thầm với nội dung đổi.

## 23. Dependencies, layout và asset versions

Một template email hiếm khi chỉ có một HTML file:

~~~text
ORDER_CONFIRMED revision 17
   |
   +-- subject template v17
   +-- plain template v17
   +-- html body v17
   +-- shared header layout v5
   +-- shared footer layout v9
   +-- logo asset hash A
   +-- button style asset hash B
   '-- variable schema v3
~~~

Nếu shared header tự thay theo bản mới nhất, revision 17 có thể render khác dù row template chính không đổi. Vì vậy cần **pin dependency graph** hoặc tạo một immutable **render bundle**.

### Immutable bundle manifest

~~~json
{
  "revisionId": "6f15ed00-0000-4000-8000-000000000017",
  "renderer": "THYMELEAF",
  "html": "sha256:html-body-v17",
  "plain": "sha256:plain-v17",
  "subject": "sha256:subject-v17",
  "layout": "sha256:header-v5",
  "footer": "sha256:footer-v9",
  "assets": {
    "logo": "sha256:logo-v3",
    "button": "sha256:button-v2"
  }
}
~~~

Các hash là giá trị minh họa, không phải SHA-256 thật. Trong production, dùng canonicalization rõ và hash bytes thực để kiểm chứng integrity.

### Inline asset và remote asset khác nhau

- **CID inline image:** đóng gói ảnh trong MimeMessage, cần content bytes từ asset revision đã pin.
- **Remote HTTPS image:** email client có thể tải sau khi gửi; hình ảnh có thể thay đổi hoặc bị chặn, không nhất thiết tái hiện được nội dung nhìn thấy.
- **Attachment:** thường có dữ liệu nghiệp vụ nhạy cảm; lưu chính sách hoặc references rõ, không luôn lấy bản mới nhất vào retry.

Với email audit quan trọng, phải xác định bản nào của attachments/layout/resources cần giữ. Một content hash của HTML **không đủ** để bảo đảm toàn bộ email render lại giống trước nếu assets hoặc formatter library đổi.

## 24. Cache registry: immutable content và mutable activation

Đọc cùng một revision hàng nghìn lần có thể gây tải database, vì vậy registry thường cần cache. Nhưng phải phân biệt:

| Cache | Key phù hợp | Đặc tính |
| --- | --- | --- |
| **Revision content** | revisionId + contentHash | Bất biến, có thể TTL dài |
| **Manifest** | revisionId + schemaVersion | Bất biến cùng revision |
| **Compiled template** | revisionId + engineVersion + contentHash | Phụ thuộc renderer/runtime |
| **Active pointer** | environment + tenant + key + locale + brand + variant | Thay đổi, cần invalidation |
| **Fallback resolution** | toàn bộ selector + policyVersion | Thay đổi khi activation/policy đổi |
| **Recipient-specific rendered output** | Không nên cache theo templateKey | Có PII, token và dữ liệu nghiệp vụ |

### Vì sao active pointer khó cache hơn revision?

~~~text
Node A cache: active -> revision 17
Node B cache: active -> revision 17

Operator activate revision 18
  |
  +-- Node A invalidate ngay -> 18
  '-- Node B miss invalidation -> vẫn 17
~~~

Kết quả là notifications mới có thể dùng hai revisions khác nhau trong một khoảng thời gian. Nếu yêu cầu chọn phiên bản tức thời/chính xác, cần policy consistency phù hợp: đọc active pointer từ nguồn authoritative, TTL rất ngắn, version stamp hoặc invalidation có xác nhận.

### Revision cache có thể dùng long TTL khi nội dung immutable

Khi revision 17 thật sự bất biến, cache theo revisionId + hash có thể tồn tại lâu mà không sợ một operator sửa nội dung đằng sau. Tuy nhiên:

- Phải kiểm tra **REVOKED** từ authoritative policy nếu yêu cầu chặn gửi ngay.
- Đảm bảo assets/dependency bundle vẫn có thể lấy.
- Bảo vệ eviction và dung lượng cache.
- Nếu renderer thay đổi, compiled output cache có thể cần namespace khác.

### Cache miss không nên biến thành gửi bản bất kỳ

Nếu cache miss và registry database tạm thời không truy cập được, worker nên retry theo policy hoặc fail closed tùy mục đích. Không chọn file local cũ không rõ version chỉ để SMTP gửi thành công.

### Không cache rendered output có token mà thiếu ranh giới

Nếu cache kết quả HTML theo **templateKey** nhưng không có recipient/model identity, một người có thể nhận link token của người khác. Nếu thực sự cần cache kết quả personalized, phải có key đúng, TTL, encryption, access control và đánh giá rủi ro; nhiều hệ thống nên chỉ cache **revision source** chứ không cache HTML đã điền PII.

## 25. Cache invalidation và tính nhất quán khi rollout

Một chiến lược phổ biến:

~~~text
Operator publishes revision 18
          |
          v
DB transaction changes active pointer
          |
          v
Commit + record activation event
          |
          v
Event bus / pub-sub invalidates selector caches
          |
          v
Workers resolve revision 18 for NEW notifications
~~~

Nếu invalidation event bị mất, TTL hoặc version-check phải giúp cache hội tụ về state đúng. Không mặc định pub-sub delivery là exactly-once; activation event có thể lặp hoặc trễ.

### Version stamp cho active pointer

Một activation row có thể có:

~~~text
templateKey=ORDER_CONFIRMED
tenant=tenant-A
locale=vi-VN
activeRevision=18
activationVersion=6
~~~

Cache giữ kèm activationVersion để phát hiện state cũ. Atomic pointer update phải tăng version trong cùng transaction.

### Kịch bản consistency

| Yêu cầu | Giải pháp khả thi |
| --- | --- |
| Staging / dev | TTL ngắn có thể đủ |
| Marketing campaign rollout | Activation snapshot và canary assignment |
| Transactional audit | Pin revision khi enqueue |
| Security template emergency revoke | Revocation check mạnh tại send time |
| Nhiều region | Quy định max propagation lag và fallback khi không xác thực được |

### Không tách subject và body thành hai cache key mutable

Nếu cache subject theo templateKey còn HTML theo templateKey+locale nhưng update/invalidate không đồng bộ, một lần render có thể dùng hai revisions. Resolver phải trả **snapshot revision hoàn chỉnh**, sau đó render toàn bộ từ snapshot đó.

## 26. Tách bản phát hành khỏi active traffic

**Publish** làm revision đủ điều kiện sử dụng; **activate** đưa nó vào traffic. Tách hai việc giúp:

1. Publish revision 18 sau review.
2. Preview ở staging/tenant thử.
3. Chạy smoke tests/golden fixtures.
4. Activate revision 18 cho 1% nhóm đủ điều kiện.
5. Theo dõi error/bounce/support feedback.
6. Tăng 5%, 25%, 100% theo policy.

### Rollout có trọng số phải ổn định

Nếu mỗi lần worker chọn variant bằng random:

~~~text
Attempt 1: variant A
Retry 2:   variant B
~~~

cùng một notification có thể thay nội dung. Hãy tính assignment bằng **stable notification/recipient/experiment ID** hoặc lưu kết quả phân nhóm trước external side effect.

Một thiết kế lựa chọn:

~~~java
public record TemplateAssignment(
        String experimentId,
        String variant,
        java.util.UUID revisionId
) {
}
~~~

### Không dùng A/B cho những nội dung cần tuân thủ nhất quán

Thử nghiệm wording marketing có thể chấp nhận; với hóa đơn, thuế hoặc reset password, cần review/tracking nghiêm ngặt hơn. Một campaign marketer không nên có quyền thay một template security-critical chỉ qua một experiment config.

### Rollout phải có đủ dữ liệu quan sát

Một revision có syntax hợp lệ vẫn có thể tạo link sai ở locale hiếm. Vì vậy theo dõi:

- Render failure rate theo revision/locale.
- Tỷ lệ email rejected/accepted và bounce khi có provider events.
- Các biến thiếu/mismatch.
- Complaints hoặc support ticket tăng bất thường.
- Tỷ lệ failures ở nhóm canary so với nhóm control có cùng purpose.

**SMTP acceptance rate** không đo đầy đủ trải nghiệm người nhận; để đánh giá campaign, còn cần đo delivered/bounced nếu provider cung cấp và tuân thủ chính sách tracking.

## 27. Preview, fixtures và golden render snapshots

Một registry có giá trị khi người duyệt nhìn được nội dung thực tế trước publish. Preview nên dùng **model fixtures** theo locale, tenant và các trường hợp rìa.

### Các fixtures cần có

| Fixture | Mục đích |
| --- | --- |
| **happy-path** | Dữ liệu thông thường |
| **long-customer-name** | Tràn dòng/đứt layout |
| **missing-optional** | Kiểm tra default và conditional rendering |
| **currency-vnd / currency-usd** | Định dạng số tiền |
| **rtl-locale** (nếu hỗ trợ) | Kiểm tra chiều văn bản |
| **special-characters** | Unicode, dấu nháy, HTML escaping |
| **url-with-query** | Link encoding và host |
| **many-line-items** | Giới hạn chiều dài email |
| **no-attachments** | Plain/HTML vẫn đầy đủ |
| **expired-token** | Không gửi CTA không còn hợp lệ |

Ví dụ fixture:

~~~json
{
  "fixture": "long-customer-name",
  "templateKey": "ORDER_CONFIRMED",
  "revisionId": "6f15ed00-0000-4000-8000-000000000017",
  "locale": "vi-VN",
  "model": {
    "customerDisplayName": "Một tên khách hàng rất dài có ký tự < & >",
    "orderCode": "ORD-1528",
    "formattedTotal": "250.000 ₫",
    "orderLink": "https://app.example.test/orders/ORD-1528"
  }
}
~~~

Fixture phải được xử lý theo chính sách dữ liệu: dùng **dữ liệu giả/synthetic**, không paste raw thông tin khách hàng hoặc token production vào hệ thống preview.

### Golden snapshot nên test có chủ đích

Có thể lưu expected rendered Subject/plain/HTML cho một revision và model fixture. Nếu output khác sau thay engine/version, developer thấy trước khi triển khai. Khi nội dung thay đổi có chủ đích, tạo revision và cập nhật snapshots theo quy trình review, không tự động overwrite expected snapshots.

### Visual rendering theo email clients

HTML email hiển thị khác nhau giữa Outlook, Gmail và các mobile clients. Test có thể bao gồm ảnh chụp/visual preview ở clients được hỗ trợ, kiểm tra responsive layout, alt text, dark mode và tình trạng image blocking. Điều này thuộc quy trình publish template; nó không yêu cầu worker STEP 4 của bài học chạy thử nội dung trên một client cụ thể.

### Plain text phải là nội dung có nghĩa

Không để **plainTextTemplate** trống chỉ vì hầu hết người dùng đọc HTML. Plain text hỗ trợ các client và công cụ truy cập không render HTML, đồng thời cần có link/hướng dẫn tương ứng.

## 28. Static analysis của template trước publish

Ngoài preview, bước kiểm tra tự động có thể phát hiện:

- Template key/revision/locale/brand thiếu.
- Cú pháp renderer không hợp lệ.
- Biến tham chiếu không có trong manifest.
- Biến required thiếu ở fixture.
- Dead branch hoặc conditional không có coverage.
- Subject có line breaks sau render.
- Link HTTP ngoài allowlist hoặc scheme không an toàn.
- HTML thẻ không đóng/định dạng không phù hợp.
- Ảnh không có alt text theo policy.
- Thiếu bản plain-text.
- Nội dung/copyright/footer bắt buộc bị xóa.
- Asset references không còn tồn tại.
- Nội dung quá dài hoặc có vùng placeholder chưa được thay.

### Static analysis không chứng minh runtime correctness

Một template có thể pass syntax và sample fixtures nhưng fail khi data thật dài hơn hoặc service trả biến null. Vì vậy cần **runtime variable validation** với lỗi được phân loại và alert, không chỉ kiểm tra một lần lúc publish.

### Schema compatibility khi publish

Nếu revision 18 cần biến **trackingUrl** mới nhưng business producer chưa cung cấp:

~~~text
Producer model schema v2
Template revision 18 expects schema v3
   -> SCHEMA_NOT_COMPATIBLE
   -> Không activate production
~~~

Có thể chọn thiết kế biến optional có default an toàn hoặc deploy producer trước, rồi publish template. Không âm thầm cho engine render null thành text “null” trong email.

## 29. Tương thích với nhiều phiên bản ứng dụng

Trong rolling deployment, workers v1 và v2 có thể đồng thời tồn tại:

~~~text
Worker v1 supports model schema: 1, 2
Worker v2 supports model schema: 2, 3

Template revision 18 requires schema 3
~~~

Nếu active revision 18 trong khi worker v1 vẫn xử lý notifications mới, sẽ có render failures. Một release plan có thể:

1. Deploy code hiểu schema v3 theo cách backward-compatible.
2. Xác minh mọi active workers đã hỗ trợ v3.
3. Publish/activate template revision 18.
4. Theo dõi lỗi và canary.
5. Chỉ xóa hỗ trợ schema cũ khi outbox không còn notification pin cũ và retention cho phép.

### Event/model contract phải explicit

Model snapshot có thể mang **modelSchemaVersion=2** trong outbox. Renderer có thể có adapters **v2→v3** nếu thiết kế hỗ trợ. Nhưng adapters phải được test/pin rõ, không tự đoán tên biến thay đổi.

### Renderer engine version cũng quan trọng

Hai phiên bản Thymeleaf hoặc formatter library có thể khác nhau về escaping, locale formatting, template expressions. Đối với email audit quan trọng, có thể ghi **rendererVersion** hoặc **renderBundleVersion** cùng revision để hỗ trợ tái hiện. Nếu yêu cầu chính xác bytes cực cao, cân nhắc lưu **rendered content snapshot** theo chính sách bảo mật/retention.

### Tránh sửa template language ngầm

Nếu revision 17 từng dùng Thymeleaf nhưng engine mới chuyển sang FreeMarker, không thể cho cùng revision source được diễn giải bằng parser khác mà không có migration. **renderer type/version** là metadata cần được ghi bền vững.

## 30. Bảo vệ registry trước truy cập và thay đổi trái phép

Template có thể chứa logo, URLs, legal text và hướng dẫn xử lý tài khoản. Ai sửa được template có thể lợi dụng nó để lừa người dùng hoặc chuyển họ đến website giả.

### Quyền theo vai trò và scope

| Vai trò | Quyền mẫu |
| --- | --- |
| **Viewer** | Xem approved content theo tenant |
| **Author** | Tạo/sửa draft trong scope |
| **Reviewer** | Phê duyệt snapshot chính xác |
| **Publisher** | Publish revision đã approve |
| **Operator** | Activate/rollback theo scope |
| **Auditor** | Xem history và hashes |
| **Security administrator** | Emergency revoke có audit |

Các thao tác phải có authentication và tenant-scoped authorization. Không chỉ ẩn nút “Publish” ở UI; server API cũng phải chặn thao tác.

### Ngăn content editor thay sender identity

Nội dung template có thể do marketing team quản lý, nhưng **From domain, Return-Path, Reply-To, DKIM và DMARC** liên quan policy gửi. Không cho editor nhập sender From tùy ý rồi gửi dưới domain chưa xác minh. Sử dụng sender profile ID từ allowlist.

### Review nội dung có yếu tố phishing

Một template mới có link “Đăng nhập để xác minh” trỏ đến host không thuộc quyền kiểm soát của sản phẩm là rủi ro cao. Static URL allowlist, người duyệt độc lập và monitoring thay đổi là hàng rào hữu ích. Không chỉ kiểm tra HTML có hợp lệ.

### Secrets tuyệt đối không thuộc template body

SMTP credentials, provider API tokens, signing keys không được đi vào variable schema, draft preview hay template source. Token người nhận có thể cần xuất hiện trong link một lần; việc tạo và lưu chúng thuộc authentication/business service, phải có TTL, audit và chính sách không log.

### Audit là append-only

Một audit record nên cho biết:

~~~text
action=PUBLISH
revisionId=...
previousStatus=APPROVED
newStatus=PUBLISHED
actor=content-publisher-1
at=2026-01-01T09:00:00Z
contentHash=sha256:...
reason=release-notes-reference
~~~

Không nên cho phép content editors xóa history của các approvals/activations đã xảy ra. Retention và privacy có thể yêu cầu xóa một số dữ liệu; cần thiết kế metadata audit để giữ bằng chứng tối thiểu phù hợp chính sách.

## 31. Monitoring và metrics cho template registry

Template registry là một hệ thống điều khiển nội dung, nên sự cố có thể xuất hiện trước cả SMTP. Ví dụ database registry không truy cập được, locale fallback sai, cache vẫn trả active revision cũ hoặc renderer gặp biến thiếu.

### Metrics nên có

| Tên logic | Loại | Ý nghĩa |
| --- | --- | --- |
| **mail_template_resolutions** | Counter | Số lần resolve theo kết quả |
| **mail_template_resolution_seconds** | Timer | Độ trễ resolve revision |
| **mail_template_renderings** | Counter | Thành công/lỗi khi render |
| **mail_template_render_seconds** | Timer | Thời gian render |
| **mail_template_missing_variables** | Counter | Lỗi thiếu biến required |
| **mail_template_schema_mismatch** | Counter | Producer và revision không tương thích |
| **mail_template_cache_requests** | Counter | Hit/miss/cache failure |
| **mail_template_activation_changes** | Counter | Số lần activate/rollback |
| **mail_template_revoked_blocked** | Counter | Jobs bị chặn vì revision revoked |
| **mail_template_resolution_fallback** | Counter | Số lần fallback locale/brand/scope |
| **mail_template_preview_failures** | Counter | Lỗi khi preview draft/revision |
| **mail_notification_stuck_due_template** | Gauge | Pending notifications bị kẹt vì lỗi template |

Đây là metrics **do ứng dụng tự triển khai**, không có sẵn từ **JavaMailSender**. Khi xuất sang Prometheus, tên có thể được chuẩn hóa và counter có hậu tố **_total** theo registry.

### Labels có cardinality thấp

Có thể dùng:

~~~text
purpose=security|transactional|marketing
result=success|not_found|invalid_model|revoked
locale=vi-VN|en-US|other
environment=staging|production
renderer=thymeleaf|freemarker
~~~

**templateKey** và **revisionId** có thể hữu ích cho điều tra nhưng cần đánh giá cardinality vì có thể tăng mạnh theo số mẫu/phiên bản. Không đưa recipient address, notificationId, orderId, raw subject hoặc model values vào metric labels.

### Ví dụ Micrometer wrapper

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.Map;

public final class MeteredTemplateRenderer {

    private final ThymeleafMailContentRenderer delegate;
    private final MeterRegistry registry;

    public MeteredTemplateRenderer(
            ThymeleafMailContentRenderer delegate,
            MeterRegistry registry
    ) {
        this.delegate = delegate;
        this.registry = registry;
    }

    public RenderedMailContent render(
            ResolvedMailTemplate revision,
            Map<String, Object> checkedModel
    ) {
        Timer.Sample sample = Timer.start(registry);
        String result = "failure";
        try {
            RenderedMailContent output =
                    delegate.render(revision, checkedModel);
            result = "success";
            return output;
        } finally {
            registry.counter(
                    "mail_template_renderings",
                    "result", result
            ).increment();
            sample.stop(
                    registry.timer("mail_template_render_seconds")
            );
        }
    }
}
~~~

Ví dụ đo số lần render và duration, chưa phân loại từng exception. Trong production có thể map lỗi sang các reason codes hữu hạn, không dùng raw exception text làm label.

### Nhận diện lỗi trước SMTP

Nếu mail outbox due backlog tăng nhưng **mail_template_renderings{result=failure}** cũng tăng, không nên tập trung điều tra SMTP host trước. Cần kiểm tra registry lookup, schema model, asset availability hoặc renderer runtime.

### Active revision dashboard

Một panel có thể cho biết:

~~~text
Template key         Locale   Active   Activated at
ORDER_CONFIRMED      vi-VN    rev17    ...
ORDER_CONFIRMED      en-US    rev15    ...
PASSWORD_RESET       vi-VN    rev04    ...

Render failures (5m):  12
Fallback resolutions:  43
Cache stale warnings:   2
Revoked jobs blocked:   0
~~~

Trên hệ thống nhiều tenant/revision, dashboard cần phân trang/lọc scope. Không cố đưa tất cả keys vào Prometheus labels nếu cardinality quá lớn; có thể dùng read-only registry query để điều tra chi tiết.

## 32. Alerting theo mức độ ảnh hưởng

Không phải lỗi template nào cũng nghiêm trọng như nhau. Một mẫu marketing thử nghiệm thất bại có thể xử lý trong giờ làm việc, trong khi **PASSWORD_RESET** bị missing revision có thể khiến người dùng không khôi phục tài khoản.

### Các cảnh báo gợi ý

| Alert | Tín hiệu | Hành động |
| --- | --- | --- |
| **Security template unavailable** | Không resolve được template security critical | Điều tra activation/registry nhanh |
| **Render failure spike** | Render errors tăng theo purpose | Kiểm tra schema/locale/renderer |
| **Template missing variables** | Required variable errors | Producer/template compatibility |
| **Cache not converging** | Nodes trả active revision khác authoritative | Invalidate/reconcile cache |
| **Revoked revision still attempted** | Worker cố dùng revoked content | Chặn send, kiểm tra policy |
| **Template asset missing** | Không thể lấy immutable asset | Object store/retention/manifest |
| **Approval bypass** | Publish không có approval hợp lệ | Security audit, khóa activation |
| **Mail due backlog caused by rendering** | Job chờ vì render lỗi | Fix content/model, không chỉ scale SMTP |

### Alert cần gắn với purpose và trạng thái

Không alert vì “revision 18 chưa có active pointer” nếu revision đó còn ở DRAFT. Nhưng nếu một key bắt buộc cho production bị thiếu active revision thì phải có tín hiệu rõ, kể cả chưa phát sinh lượt gửi nào trong vài phút qua. Có thể dùng **config readiness validation** trước khi release cộng với runtime failure metrics.

### Không coi rollback là đã xử lý hết incident

Sau khi đưa active pointer về 17, các notifications đã pin 18 vẫn có thể đang PENDING/RETRY_WAIT. Alert phải theo dõi **jobs pinned to revoked/bad revision**, không chỉ dashboard active pointer.

## 33. Kiểm thử registry resolution

Các test về resolver nên bao gồm đúng tổ hợp template key, tenant, locale, variant và environment.

### Ví dụ policy test với fake registry

Một interface resolver:

~~~java
public interface ActiveTemplateResolver {
    ResolvedMailTemplate resolve(TemplateSelector selector);
}
~~~

Test đầu vào:

~~~text
Template:
  key=ORDER_CONFIRMED
  locale=vi-VN
  tenant=tenant-A
  brand=retail
  active=rev17

Given:
  selector tenant-A / vi-VN / retail
Expected:
  resolved revision rev17
~~~

### Các cases bắt buộc

| Kịch bản | Kết quả |
| --- | --- |
| Exact tenant/locale/brand exists | Chọn chính xác |
| Tenant revision thiếu, global approved allowed | Fallback global được phê duyệt |
| Tenant B revision tồn tại nhưng A không có | Không chọn B |
| Locale vi-VN thiếu, fallback en-US bị cấm | Resolution failure |
| Active pointer trỏ DRAFT | Chặn gửi, báo cấu hình sai |
| Active revision REVOKED | Chặn gửi |
| Version number mới nhất DRAFT | Không tự chọn |
| Revision tồn tại nhưng asset thiếu | Asset integrity failure |
| Manifest không tương thích producer | Schema mismatch |
| Operator đổi active trong lúc resolve | Một response vẫn thuộc một revision |

### Test concurrency

Hai operators cùng activate different revisions với cùng expected pointer: một thao tác nên thành công và thao tác khác nhận conflict thay vì ghi đè im lặng. Nếu có multi-region replication, test thêm tính hội tụ và hành vi khi pointer cũ.

### Test isolation

Một tenant không thể đọc, activate hoặc preview draft/asset thuộc tenant khác nếu không có quyền. Kiểm tra ở server API/repository, không chỉ trên UI.

## 34. Unit test render và biến bắt buộc

Renderer được tách khỏi SMTP, nên test có thể gọi trực tiếp:

~~~text
revision 17 + checked model -> RenderedMailContent
~~~

### Bộ test đề xuất

1. **Required variable missing:** fail trước SMTP.
2. **Optional variable missing:** dùng default từ manifest đúng revision.
3. **Wrong type:** fail với reason code xác định.
4. **HTML escaping:** tên chứa ký tự <, >, & không trở thành markup ngoài ý muốn.
5. **URL validation:** link sai host/scheme bị từ chối.
6. **Subject CRLF:** không có line break/header injection.
7. **Locale formatting:** giá và ngày dùng locale/timezone đúng.
8. **Long fields:** giới hạn length, không làm render OOM.
9. **Plain + HTML:** cùng thông tin nghiệp vụ cần thiết.
10. **Shared layout version:** revision 17 vẫn lấy asset/layout đã pin.
11. **Renderer upgrade:** golden output ở fixtures không đổi bất ngờ.
12. **Revoked revision:** không được dùng để send theo policy.

### Một JUnit ví dụ ngắn

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class ThymeleafMailContentRendererTest {

    @Test
    void rendersSubjectAndBothBodyForms() {
        ResolvedMailTemplate revision =
                new ResolvedMailTemplate(
                        UUID.randomUUID(),
                        "ORDER_CONFIRMED",
                        "vi-VN",
                        "retail-main",
                        "default",
                        17,
                        3,
                        "Xác nhận đơn [[${orderCode}]]",
                        "Đơn [[${orderCode}]] đã được xác nhận.",
                        "<p th:text=\"${orderCode}\">old</p>",
                        "sha256:demo",
                        Instant.parse("2026-01-01T00:00:00Z"),
                        Map.of()
                );

        RenderedMailContent result =
                new ThymeleafMailContentRenderer().render(
                        revision,
                        Map.of("orderCode", "ORD-1528")
                );

        assertEquals(
                "Xác nhận đơn ORD-1528",
                result.subject()
        );
        assertTrue(result.plainText().contains("ORD-1528"));
        assertTrue(result.html().contains("ORD-1528"));
        assertEquals(revision.revisionId(), result.revisionId());
    }
}
~~~

Đoạn test minh họa renderer; bước **validate variables** nằm trước renderer trong kiến trúc nên cần test riêng. Dữ liệu UUID/hash chỉ là test values; không dùng hash giả làm bằng chứng integrity của template thật.

### Test không cần SMTP

Chỉ để kiểm tra template, không cần gửi email thật. Các integration tests MIME composer/SMTP có thể dùng GreenMail hoặc SMTP test fixture cô lập. Nên tách thời gian chạy test parser/renderer nhanh khỏi các test network/integration.

## 35. Integration test với Spring Mail và SMTP fixture

Một integration test có thể:

~~~text
In-memory/fake Registry
        |
        v
Pinned revision 17
        |
        v
Validator + Renderer
        |
        v
MimeMessageHelper
        |
        v
GreenMail local SMTP
        |
        v
Captured MIME
        |
        +-- Subject
        +-- plain/html
        +-- charset
        '-- attachment/inline asset refs
~~~

### Những assertion quan trọng

- Subject thực tế chứa đúng mã đơn/biến.
- To/From là địa chỉ đã được validation/verified policy cho phép.
- Plain và HTML đều có nội dung chính.
- MIME charset phù hợp với tiếng Việt/Unicode.
- HTML không chứa placeholder chưa được render.
- Inline CID và attachments tương thích với manifest.
- Revision 17 được render dù active pointer đã chuyển sang 18 trước retry.
- Mail đã được accepted thì không tự gửi lại chỉ vì registry activation đổi.

### Test rollback không sửa notification cũ

~~~text
Given:
  N1 pinned=revision17
  active pointer changed=revision18
  operator rollback active=revision16

When:
  N1 is dispatched

Then:
  N1 uses revision17
  contentHash matches pinned revision17
~~~

### Test version migration chỉ cho jobs chưa attempt

Một integration test khác có thể xác minh migration 17→18 chỉ thay những notifications chưa gửi, chưa IN_FLIGHT, chưa UNKNOWN/ACCEPTED, với schema compatible và audit. Mục đích là không ghi lại lịch sử của những gì đã submit SMTP.

### Test SMTP timeout không được dùng để đổi template

Nếu server có thể đã accepted nhưng client mất response, job chuyển UNKNOWN. Không tự chọn revision mới nhất rồi gửi lần nữa như một “khắc phục” sự cố.

## 36. Runbook: bản template mới làm email gửi lỗi

Giả sử sau khi kích hoạt revision 18, dashboard báo **render failure** tăng và mail outbox backlog tăng. Một runbook cần tránh kết luận vội rằng lỗi nằm ở SMTP.

### Bước 1 — Xác minh triệu chứng

Thu thập:

~~~text
templateKey / purpose:
environment / tenant / locale / variant:
active revision:
revision hash:
activation time:
first render failure time:
failure category:
number of pending notifications:
number of attempts already submitted:
oldest due age:
~~~

Đối chiếu thời điểm lỗi với thay đổi active pointer, producer deployment hoặc renderer version. Nếu lỗi chỉ xảy ra với locale hiếm hoặc tenant cụ thể, đừng tắt mọi gửi email ngoài phạm vi bị ảnh hưởng.

### Bước 2 — Phân biệt resolver, model và rendering

| Hiện tượng | Nghi vấn |
| --- | --- |
| **TEMPLATE_NOT_FOUND** | Activation/mapping sai hoặc scope thiếu |
| **LOCALE_NOT_ALLOWED** | Fallback policy không cho phép |
| **SCHEMA_NOT_COMPATIBLE** | Producer model và revision mismatch |
| **MISSING_REQUIRED_VARIABLE** | Producer thiếu biến |
| **ASSET_NOT_FOUND** | Asset bundle/retention lỗi |
| **RENDERER_PARSE_ERROR** | Cú pháp template/engine version |
| **INVALID_SUBJECT** | CRLF hoặc subject rỗng |
| **SMTP_CONNECT_FAILURE** | Transport, không phải template |

Một failure category rõ giúp không phải dump nguyên model/HTML chứa dữ liệu cá nhân.

### Bước 3 — Chặn tác động mới nếu cần

Nếu template mới có link sai hoặc câu chữ vi phạm chính sách, cần xem xét:

- **Pause** những notification thuộc key/scope bị ảnh hưởng.
- **Rollback active pointer** cho yêu cầu mới.
- **Revoke revision** nếu không được phép gửi tiếp dù đã pin.
- Tạm dừng campaign hoặc chỉ giữ transactional flow hợp lệ.

Rollback active pointer **không đổi** revision đã pin trong outbox. Cần xử lý nhóm đang chờ riêng.

### Bước 4 — Phân nhóm outbox

~~~text
Group A: no attempt yet, pinned bad revision
Group B: IN_FLIGHT, possibly submitting
Group C: ACCEPTED, already submitted
Group D: UNKNOWN, result ambiguous
Group E: render failed before SMTP submission
~~~

Với Group E, có thể sửa model hoặc migrate revision theo policy nếu chứng minh chưa gửi; với Group C không được thay lịch sử đã accepted, còn Group D cần reconciliation trước khi retry.

### Bước 5 — Xử lý cùng phiên bản hay tạo revision mới?

Nếu revision 18 chỉ sai một chữ, **không sửa lại revision 18 tại chỗ**. Tạo revision 19 từ bản đã sửa, kiểm tra và approve. Những notification đang chờ dùng revision 18 phải xử lý theo migration policy có audit, thay vì “revision 18 bỗng trở thành nội dung mới”.

### Bước 6 — Xác nhận phục hồi

- New notifications resolve đúng revision đang active.
- Renderer errors giảm.
- Pending due jobs và oldest age giảm.
- Không có notification sai template gửi thêm ngoài quyết định có chủ đích.
- Các jobs pin bản cũ được giữ/migrate/revoke theo trạng thái.
- Audit có đủ operator, reason, old/new revision.
- Caches đã hội tụ hoặc bị chặn nếu stale.

### Bước 7 — Postmortem

Xem lỗi vì sao vượt qua validation/preview, có thiếu fixtures hay hợp đồng schema? Có thể bổ sung test cho variant, locale, token URL hoặc producer version, đồng thời phân biệt lỗi template với lỗi SMTP trong alert.

## 37. Runbook: active pointer đúng nhưng email vẫn dùng bản cũ

Triệu chứng:

~~~text
Registry DB active = revision 18
App node A emits revision 18
App node B emits revision 17
~~~

Các nguyên nhân có thể:

- Cache active pointer của B chưa invalidated.
- B trỏ database region/replica đang replication lag.
- Environment/tenant/brand/locale selector khác nhau.
- Một số notifications đã được **pin revision 17 trước khi activation** (đây có thể là đúng).
- Worker render từ một template source classpath thay vì registry.
- Compiled template cache được key bằng templateKey thay vì revisionId/hash.

### Phân tích theo đúng loại dữ liệu

**Trường hợp 1 — New notification, expected revision 18:** cần kiểm tra resolver/cache consistency và activation scope.

**Trường hợp 2 — Existing notification pinned 17:** không phải lỗi cache; đó là chủ ý của pinning policy. Nếu business muốn thay, cần migration chưa-attempt và audit.

### Thao tác an toàn

- Kiểm tra **notificationId -> pinned revision** trước.
- Đối chiếu selector đầy đủ và activationVersion.
- Nếu stale cache, invalidate đúng scope hoặc tạm bypass cache.
- Xác minh revision body hash từ source authoritative.
- Không sửa contentHash trong database để cho khớp dữ liệu cũ.
- Không replay những email đã accepted chỉ để thống nhất version.

### Hậu quả của sửa cache key sai

Nếu compiled template cache theo **ORDER_CONFIRMED** còn dữ liệu mới theo **revision 18**, engine có thể trả body đã compile v17. Vì vậy cache key phải chứa revisionId/contentHash/renderer version theo hợp đồng, không được trông chờ một lệnh invalidate thủ công mỗi lần publish.

## 38. Lưu trữ lịch sử, retention và quyền riêng tư

Template revision metadata thường có tuổi thọ dài hơn một notification cá nhân. Nhưng **model snapshot** và **rendered MIME** có thể chứa PII, nên retention của từng loại phải khác nhau.

| Dữ liệu | Có thể cần giữ | Rủi ro |
| --- | --- | --- |
| **Template source revision** | Lịch sử nội dung công khai/được phê duyệt | Có thể chứa URL nội bộ hoặc nội dung giới hạn |
| **Content hash + audit** | Dấu vết kiểm chứng và approval | Có thể tiết lộ các thay đổi nhạy cảm |
| **Model snapshot** | Tái hiện nội dung theo notification | PII, tên, địa chỉ, số tiền, token |
| **Rendered MIME** | Điều tra/hồ sơ giao dịch | Nội dung đầy đủ và attachments |
| **Sender/recipient metadata** | Delivery audit, suppression | Địa chỉ email, thông tin cá nhân |
| **Asset bundle** | Reproduce revision | Đồ họa, tài liệu có bản quyền, tracking |

### Không lưu token vô thời hạn để phục vụ re-render

Password reset token hoặc link một lần thường có TTL ngắn. Một yêu cầu audit không tự động hợp thức hóa việc giữ token plaintext nhiều năm. Thay vào đó có thể giữ metadata, hash/opaque reference và thông tin về template; khi cần tái hiện, hiển thị bản đã redact hoặc một bản proof không chứa secret.

### Content retention khác delivery history

Có thể giữ:

~~~text
revisionId + contentHash + approvedAt
~~~

trong thời gian dài, nhưng xóa/pseudonymize:

~~~text
recipient full address
model snapshot with PII
raw attachment bytes
~~~

theo chính sách dữ liệu tương ứng. Nếu đã xóa model, phải ghi rõ không còn khả năng tái render chính xác cho notification đó. Không hứa “luôn tái tạo 100% email” khi retention đã xóa dữ liệu cần thiết.

### Audit không nên ghi mọi nội dung vào application logs

Log gợi ý:

~~~text
event=mail_template_resolved
template_key=ORDER_CONFIRMED
revision_id=6f...
locale=vi-VN
resolution=EXACT
render_result=SUCCESS
notification_id=opaque-id
~~~

Các opaque IDs vẫn có thể có rủi ro correlation, nên quyền truy cập/retention logs cũng cần được quản lý.

## 39. Những lỗi triển khai thường gặp

### Lỗi 1 — Sửa published revision trực tiếp

**Hậu quả:** audit sai, retry dùng nội dung khác với notification cũ, caches không nhất quán.

**Cách xử lý:** tạo revision mới và chỉ đổi active pointer sau approve.

### Lỗi 2 — Chọn template bằng MAX(versionNumber)

**Hậu quả:** có thể chọn DRAFT hoặc revision chưa active.

**Cách xử lý:** resolve theo activation mapping và scope.

### Lỗi 3 — Subject và HTML lấy từ hai revisions

**Hậu quả:** người nhận thấy nội dung mâu thuẫn.

**Cách xử lý:** một ResolvedTemplate snapshot chứa tất cả parts.

### Lỗi 4 — Không pin revision trong outbox

**Hậu quả:** retry sau deploy có thể tạo email khác với attempt trước.

**Cách xử lý:** pin tại enqueue hoặc trước first attempt và giữ nguyên.

### Lỗi 5 — Pin template nhưng không pin model

**Hậu quả:** cùng revision render giá/tên/link khác theo dữ liệu cập nhật.

**Cách xử lý:** model snapshot/versioning hoặc rendered content snapshot theo policy.

### Lỗi 6 — Fallback tenant sang mẫu của tenant khác

**Hậu quả:** lộ branding/link/nội dung riêng.

**Cách xử lý:** explicit approved fallback chain; không cross-tenant.

### Lỗi 7 — Fallback locale mà không kiểm tra compliance

**Hậu quả:** gửi legal wording sai khu vực.

**Cách xử lý:** fallback policy theo purpose/region và phê duyệt.

### Lỗi 8 — Default mọi biến null thành chuỗi rỗng

**Hậu quả:** email thiếu mã đơn, số tiền hoặc CTA.

**Cách xử lý:** validate required variables; default chỉ cho optional.

### Lỗi 9 — Dùng double cho số tiền

**Hậu quả:** lỗi precision, formatting hoặc rounding.

**Cách xử lý:** BigDecimal/currency và formatter theo nghiệp vụ.

### Lỗi 10 — Coi HTML escaping là đủ cho URL

**Hậu quả:** một URL có scheme/host nguy hiểm vẫn có thể được render.

**Cách xử lý:** URL validation, trusted host và link builder.

### Lỗi 11 — Dùng th:utext cho dữ liệu người dùng

**Hậu quả:** HTML injection trong email/preview.

**Cách xử lý:** th:text/escaping hoặc sanitizer được phê duyệt.

### Lỗi 12 — Dùng StringTemplateResolver với source chưa tin cậy

**Hậu quả:** server-side template expression có thể có khả năng vượt ngoài thay placeholder.

**Cách xử lý:** template author RBAC, review, sandbox/allowlist phù hợp và giới hạn context.

### Lỗi 13 — Cache active revision quá lâu

**Hậu quả:** operator đã rollback nhưng node vẫn render bản cũ.

**Cách xử lý:** TTL, activationVersion, invalidation/reconciliation.

### Lỗi 14 — Cache compiled template theo templateKey

**Hậu quả:** bytes của revision mới bị nhầm với compiled output của revision cũ.

**Cách xử lý:** key theo revisionId/contentHash và engine version.

### Lỗi 15 — Cache HTML cá nhân hóa theo templateKey

**Hậu quả:** một người nhận thông tin/token của người khác.

**Cách xử lý:** không cache rendered PII chung; cache immutable source.

### Lỗi 16 — Revision body immutable nhưng logo vẫn dùng bản latest

**Hậu quả:** không tái hiện được nội dung đã duyệt.

**Cách xử lý:** pin asset manifest/dependency bundle.

### Lỗi 17 — Rollback pointer rồi cho rằng tất cả pending email đã sửa

**Hậu quả:** jobs pin revision xấu vẫn gửi.

**Cách xử lý:** phân tích nhóm chưa attempt, IN_FLIGHT, UNKNOWN và ACCEPTED.

### Lỗi 18 — Migrating revision cho jobs đã accepted

**Hậu quả:** audit/version record không phản ánh email thực tế.

**Cách xử lý:** chỉ thay jobs chưa submit khi policy cho phép, có audit.

### Lỗi 19 — Dùng template review preview với PII production

**Hậu quả:** dữ liệu khách hàng/token lộ cho người duyệt hoặc logs.

**Cách xử lý:** synthetic fixtures và access control.

### Lỗi 20 — Tạo URL reset password trong template

**Hậu quả:** token TTL/host không được quản lý ở lớp tin cậy.

**Cách xử lý:** business/auth service tạo verified URL và template chỉ hiển thị.

### Lỗi 21 — Cho marketing editor thay verified From tùy ý

**Hậu quả:** DMARC alignment, phishing hoặc gửi từ domain chưa xác minh.

**Cách xử lý:** senderProfile allowlist riêng với template content.

### Lỗi 22 — Chỉ có HTML mà không có plain text

**Hậu quả:** một số clients và accessibility workflows bị ảnh hưởng.

**Cách xử lý:** duy trì text/plain có nội dung tương đương.

### Lỗi 23 — Không version schema biến

**Hậu quả:** rolling deploy producer v2, renderer v3 bị mismatch.

**Cách xử lý:** modelSchemaVersion và compatibility matrix.

### Lỗi 24 — Chặn mọi revision deprecated kể cả retries đã pin

**Hậu quả:** các notification hợp lệ cũ không thể hoàn tất ngoài ý định.

**Cách xử lý:** phân biệt DEPRECATED và REVOKED; định nghĩa send-time policy.

### Lỗi 25 — Coi SMTP error là template error

**Hậu quả:** team sửa nội dung dù lỗi là provider outage.

**Cách xử lý:** tách resolution/render/MIME/SMTP metrics và states.

### Lỗi 26 — Coi SMTP accepted là delivered

**Hậu quả:** khẳng định người nhận đã thấy email khi mới nộp provider.

**Cách xử lý:** theo dõi delivery/bounce events riêng.

### Lỗi 27 — Lỗi render làm retry vô hạn

**Hậu quả:** backlog tăng, không có cải thiện vì template vẫn sai.

**Cách xử lý:** phân loại permanent/config/temporary, alert và pause/review.

### Lỗi 28 — Không lưu người phê duyệt và hash

**Hậu quả:** không biết ai duyệt bản nào khi incident.

**Cách xử lý:** immutable review snapshot, audit append-only.

### Lỗi 29 — Rollout variant thay đổi giữa retries

**Hậu quả:** cùng notification có nhiều bản nội dung, kết quả experiment nhiễu.

**Cách xử lý:** stable assignment và pin revision.

### Lỗi 30 — Cho rằng template versioning tạo exactly-once SMTP

**Hậu quả:** retry UNKNOWN có thể gửi trùng.

**Cách xử lý:** phân loại SMTP outcome, reconciliation, idempotent notification logic và chính sách rủi ro rõ.

## 40. Các tình huống thực hành

### Tình huống A — Chỉnh sửa một câu trong email đã published

Revision 17 đang active cho ORDER_CONFIRMED. Nhóm nội dung muốn đổi một câu giới thiệu nhưng giữ nguyên số version.

**Hỏi:** có thể UPDATE html_template của revision 17?

**Đáp:** không. Tạo revision 18, thay đổi/duyệt nội dung rồi activate theo policy. Revision 17 phải bất biến để những email cũ và những jobs đã pin có thể được kiểm chứng.

### Tình huống B — Subject v18, HTML v17

Worker tải subject và HTML qua hai API “getActiveTemplatePart”, operator activate giữa hai requests.

**Hỏi:** sửa cách đọc thế nào?

**Đáp:** resolve **revisionId một lần**, rồi lấy toàn bộ subject/plain/HTML/assets của đúng revision đó. Không đọc active pointer riêng cho từng part.

### Tình huống C — Email marketing theo lịch ba ngày sau

Campaign được phê duyệt hôm nay với revision 12. Ngày mai người viết sửa copy và activate revision 13.

**Hỏi:** campaign ngày kia dùng bản nào?

**Đáp:** tùy chính sách đã định. Nếu campaign snapshot pin revision 12, dùng 12. Nếu thiết kế resolve-at-send, chọn 13 trước attempt đầu rồi pin; phải có phê duyệt cho thay đổi theo lịch. Không để lựa chọn phụ thuộc vào worker timing một cách ngẫu nhiên.

### Tình huống D — Retry email hóa đơn sau một ngày

Hóa đơn đã phát hành với giá 250.000 VND, nhưng order database ngày hôm sau phản ánh hoàn tiền 50.000 VND.

**Hỏi:** template revision 17 đã pin có đủ để giữ nội dung cũ?

**Đáp:** chưa. Phải pin **model snapshot**/fact đã chốt hoặc rendered content để retry vẫn gửi đúng giá trị tại thời điểm hóa đơn. Không query current order totals trong mỗi attempt.

### Tình huống E — Locale vi-VN chưa có bản template

Global fallback en-US tồn tại, nhưng mẫu là thông báo pháp lý chỉ được phép gửi bản dịch theo quốc gia.

**Hỏi:** có nên fallback en-US?

**Đáp:** không nếu policy cấm. Ghi resolution failure và alert/manual review thay vì gửi wording không được duyệt.

### Tình huống F — Tenant A thiếu bản riêng

Tenant B có revision đã duyệt rất đẹp, global không có.

**Hỏi:** có thể chọn revision tenant B?

**Đáp:** không. Fallback chỉ qua scopes được cho phép, ví dụ approved global. Cần bảo đảm tenant isolation.

### Tình huống G — Nội dung template có URL nguy hiểm

Revision 18 có CTA trỏ domain ngoài allowlist.

**Hỏi:** cú pháp Thymeleaf hợp lệ có đủ cho publish?

**Đáp:** không. URL phải được validate theo trusted-host/scheme policy; security/content review chặn publish nếu không hợp lệ.

### Tình huống H — Một biến required bị thiếu

Model không có orderCode nhưng Subject cần mã đơn.

**Hỏi:** gửi email với subject trống hay fail?

**Đáp:** fail closed ở variable validator với reason rõ, không SMTP submit. Chỉ những biến optional được manifest xác nhận mới dùng default.

### Tình huống I — Một node vẫn dùng revision cũ

DB active=18, một node mới resolve=18 còn node khác resolve=17.

**Hỏi:** có phải tất cả email v17 đều sai?

**Đáp:** không. Trước tiên phân biệt **new notification** với **old pinned notification**. Nếu new notification đáng lẽ resolve 18 nhưng node trả 17, điều tra stale cache/activation scope. Old jobs pin 17 dùng 17 có thể hoàn toàn đúng.

### Tình huống J — Rollback ngay sau phát hiện lỗi nghiêm trọng

Revision 18 có thông tin sai, 3.000 jobs chưa gửi nhưng đã pin 18.

**Hỏi:** đổi active về 17 có đủ?

**Đáp:** không. Rollback chỉ ảnh hưởng selections mới. Phải pause/migrate/revoke nhóm jobs chưa-attempt theo policy, giữ nguyên trạng thái IN_FLIGHT/ACCEPTED/UNKNOWN để không sai audit hoặc gửi trùng.

### Tình huống K — Thử nghiệm A/B subject

Một user thuộc variant A ở lần gửi đầu, retry lại chọn B do random.

**Hỏi:** sai ở đâu?

**Đáp:** variant assignment không ổn định. Tính stable assignment và pin revision/variant trong notification record.

### Tình huống L — Content editor muốn thay From

Người viết template nhập địa chỉ From thuộc một domain chưa xác minh với SMTP provider.

**Hỏi:** registry có nên cho phép?

**Đáp:** nên tách senderProfile được quản lý bởi mail delivery policy và domain verification. Template author không thể tự vượt verified sender identity.

### Tình huống M — Link password reset hết hạn

Notification pin revision 5, token TTL đã hết trong lúc retry.

**Hỏi:** tiếp tục gửi link cũ?

**Đáp:** cần business deadline và token policy. Không dùng template engine để tự tạo token mới không kiểm soát trong retry. Có thể hủy notification cũ và cho phép user yêu cầu một notification mới có token mới.

### Tình huống N — Shared layout thay logo

Body revision 17 không đổi, nhưng footer/logo global được update.

**Hỏi:** có tái hiện chính xác email v17?

**Đáp:** chỉ nếu dependencies/assets đã pin. Nếu layout dùng latest, cùng revision có thể render khác. Cần immutable bundle hoặc dependency manifest.

### Tình huống O — SMTP báo accepted nhưng người dùng chưa nhận

Revision/render không lỗi, SMTP submission đã accepted.

**Hỏi:** rollback template có giải quyết được không?

**Đáp:** chưa chắc. Kiểm tra downstream delivery, bounce, suppression, spam và provider status. Registry/content consistency khác deliverability.

### Tình huống P — Hai operator kích hoạt đồng thời

Operator A định activate 18, B định activate 16 từ pointer 17.

**Hỏi:** làm sao biết ai ghi đè ai?

**Đáp:** sử dụng compare-and-set hoặc activation version; thao tác thất bại khi expected pointer không còn khớp, yêu cầu operator xem lại state.

### Tình huống Q — Revision mới yêu cầu schema model mới

Template v19 cần biến trackingUrl nhưng worker cũ chưa cung cấp.

**Hỏi:** chỉ cần activate để phát hiện lỗi ở runtime?

**Đáp:** không. Dùng compatibility validation và rollout sequence: deploy producer/renderer hỗ trợ trước, test fixtures rồi activate.

### Tình huống R — Preview dùng dữ liệu khách hàng thật

Content editor không có quyền xem hóa đơn nhưng template preview tải hóa đơn production.

**Hỏi:** an toàn không?

**Đáp:** không. Dùng synthetic fixtures, RBAC và không đưa token/PII vào preview/logs. Nếu preview cần data thật trong trường hợp đặc biệt, phải có quyền và bảo vệ riêng.

### Tình huống S — Revision bị REVOKED khẩn cấp

Một template có CTA host bị chiếm quyền; các jobs đã pin vẫn đang pending.

**Hỏi:** worker nên gửi tiếp vì đã pin?

**Đáp:** không nếu revocation policy chặn toàn bộ send. Pinning bảo đảm consistency, nhưng emergency security policy có thể ghi đè quyền sử dụng revision. Jobs nên được pause/review; không tự chọn bản mới rồi gửi nếu chưa qua migration/authorization.

### Tình huống T — Template engine nâng cấp

Thymeleaf version mới tạo whitespace/escaping khác, dù source revision cũ không đổi.

**Hỏi:** contentHash của source có bảo đảm rendered bytes giống cũ?

**Đáp:** không. Để tái render chính xác, cần biết renderer/dependency versions, model snapshot và asset bundles; trường hợp yêu cầu chặt có thể lưu rendered snapshot được bảo vệ.

## 41. Cân nhắc các kiến trúc registry

Không phải mọi sản phẩm đều cần một CMS chuyên dụng. Có thể lựa chọn theo quy mô và quy trình.

| Phương án | Lợi ích | Hạn chế |
| --- | --- | --- |
| **Templates trong Git/classpath** | Review qua PR, đơn giản, gắn release | Đổi nội dung thường phải deploy |
| **Database registry** | Activation runtime, metadata/audit dễ tra | Cần RBAC, schema, cache, migrations |
| **Object storage + DB metadata** | Lưu immutable bundle lớn, nội dung versioned | Cần asset integrity, consistency và retention |
| **CMS/headless editor** | Quy trình tác giả/preview thuận tiện | Phải tích hợp approval, security và snapshot |
| **External ESP templates** | Provider render/gửi, ít self-host | Lock-in, khó pin cross-provider, audit và data controls |
| **Hybrid** | Shared design system + runtime activation | Phức tạp hơn, phải pin dependencies |

### Git-based phù hợp khi nào?

Nếu chỉ có một vài transactional templates hiếm thay đổi, dùng templates trong repository với version được gắn theo code release có thể đủ. Nhưng để replay notification sau upgrade, vẫn cần biết **application/template artifact version** và model snapshot. Không có một registry database không đồng nghĩa không thể có content versioning.

### DB registry phù hợp khi nào?

Khi nhiều tenants/locales, non-developer authors, content approval và rollback/rollout không cần deploy, registry runtime có giá trị. Đổi lại cần vận hành một control-plane có quyền bảo mật và audit tương ứng.

### Dùng template do ESP lưu sẵn

Một số email providers cho phép lưu template và version ở hệ thống của họ. Nếu dùng nhiều providers để failover, tên template **template_123** ở A không nhất thiết tồn tại ở B hoặc render giống nhau. Cần mapping và pin provider-specific versions, hoặc render ở ứng dụng rồi nộp SMTP/API cùng nội dung đã chốt.

### Giữ domain độc lập với renderer

Domain service nên nói:

~~~text
Send ORDER_CONFIRMED with order snapshot
~~~

thay vì:

~~~text
Render Thymeleaf file templates/mail/order-confirmed-v17.html
~~~

Registry/resolver/renderer adapter xử lý chi tiết, nên về sau thay Thymeleaf bằng FreeMarker hoặc external ESP template không buộc domain viết lại toàn bộ.

## 42. Checklist triển khai production

### Danh tính và nội dung

- **templateKey** ổn định, phân biệt với filename và notificationId.
- Scope gồm tenant/brand/locale/variant/environment được định nghĩa rõ.
- Một revision chứa subject, plain text, HTML và metadata liên quan.
- Content/dependency hashes và revision IDs được lưu.
- Renderer type/version và variable schema có hợp đồng.
- Published revisions và assets bất biến.

### Quy trình phát hành

- Author/reviewer/publisher/operator có quyền được giới hạn.
- Approval gắn với đúng revision content hash.
- Publish không tự động active nếu policy tách hai bước.
- Active pointer update atomic và có compare-and-set.
- Audit append-only ghi actor, timestamp, reason, old/new revision.
- Có preview và fixture cho locale/tenant/edge cases.
- Có canary/failback/rollback scope và emergency revoke.

### Rendering và gửi mail

- Variable validator xử lý required, optional, type, length, URLs.
- Subject CR/LF validation và HTML escaping phù hợp.
- Plain text có nội dung tương ứng HTML.
- Links/tokens được tạo bởi trusted application service.
- Verified sender profile không được nội dung template tùy tiện thay.
- MIME composer dùng cùng revision/model cho mọi parts.
- Mail delivery policy vẫn kiểm tra consent/suppression.

### Retry và nhất quán

- Xác định pin revision tại enqueue hoặc trước first attempt.
- Model snapshot có schema version hoặc rendered snapshot phù hợp.
- Attempts dùng lại revision và variant đã pin.
- IN_FLIGHT/UNKNOWN không tự migrate content.
- Emergency revoke có cách chặn pending attempts.
- Notification key, template revision và attempt IDs được tách.
- Không nhầm immutable rendering với exactly-once SMTP.

### Vận hành và dữ liệu

- Cache revision riêng cache active pointer, có invalidation.
- Có alert cache stale, render errors và schema mismatch.
- Có retention policy cho model/HTML/MIME/PII.
- Preview dùng synthetic fixtures và sandbox.
- Subject/content không bị in raw vào logs ngoài phạm vi hợp lệ.
- Có audit và runbook khi template lỗi/rollback.
- Có kiểm thử compatibility qua rolling deployments.
- Với assets remote/inline, dependency versions được pin rõ.

## 43. Sơ đồ chọn template cho một notification

~~~text
                  New business notification
                            |
                            v
                  Delivery policy allows?
                       |            |
                      No           Yes
                       |            |
                       v            v
                  SUPPRESSED    Resolve selector
                                    |
                       +------------+-----------+
                       |                        |
                  No eligible revision      Revision found
                       |                        |
                       v                        v
                  FAIL / REVIEW         Validate schema contract
                                                |
                                        +-------+-------+
                                        |               |
                                     Invalid           Valid
                                        |               |
                                        v               v
                                  FAIL / REVIEW      Choose pin policy
                                                        |
                                       +----------------+---------------+
                                       |                                |
                                  Pin at enqueue                   Pin at first send
                                       |                                |
                                       +----------------+---------------+
                                                        |
                                                        v
                                           Save revision + model snapshot
                                                        |
                                                        v
                                             Worker claims notification
                                                        |
                                                        v
                                          Is revision still allowed to send?
                                                |               |
                                               No              Yes
                                                |               |
                                                v               v
                                          PAUSE / REVIEW     Load exact revision
                                                                |
                                                                v
                                                       Render subject/plain/HTML
                                                                |
                                                     +----------+---------+
                                                     |                    |
                                                  Failure               Success
                                                     |                    |
                                                     v                    v
                                               Triage/error          Compose MIME
                                                                          |
                                                                          v
                                                                     SMTP submit
                                                                          |
                                                   +----------------------+----------------+
                                                   |                      |                |
                                                ACCEPTED            NOT_ACCEPTED         UNKNOWN
                                                   |                      |                |
                                                   v                      v                v
                                                 Record                Retry            Reconcile
                                                                        pinned
                                                                       revision
~~~

Đây là **sơ đồ nghiệp vụ minh họa**, không phải state machine Spring Mail có sẵn. Production cần transaction/outbox, lease/fencing, provider outcomes và recovery phù hợp. Đặc biệt, một revision đã pin nhưng **REVOKED** không được tự gửi chỉ vì content hash vẫn khớp.

## 44. Tóm tắt nguyên tắc cần nhớ

~~~text
Template key                    = danh tính mẫu logic
Template revision ID            = một bản nội dung cụ thể
Active pointer                  = chọn revision cho request mới
Published revision              = immutable
Rollback                        = đổi active pointer, không sửa lịch sử
Template latest version         != active revision
Template approval               = cho đúng snapshot/hash
Variable schema                 = hợp đồng đầu vào, không chỉ Map tùy ý
Required variable missing       -> fail closed
Optional variable               -> default rõ ràng theo revision
Tenant fallback                 -> chỉ qua scope được phép
Locale fallback                 -> theo policy, không ngẫu nhiên
Pinned revision                 -> cùng notification render nhất quán
Pinned revision alone           != model snapshot
Rendered output                 = subject + plain + HTML cùng revision
Shared header/footer/logo       -> pin dependency versions
Preview                         -> dùng dữ liệu giả, không lộ token
Renderer compiled cache         -> key theo revision/hash/engine
Active pointer cache            -> cần invalidation/versioning
Security revoke                 -> có thể chặn pinned revisions
Outbox retry                    -> giữ stable notification/revision/variant
SMTP accepted                   != delivered
Immutable content               != exactly-once SMTP
~~~

**Template registry và phiên bản nội dung** là một mẫu thiết kế production giúp tách **quyết định gửi email** khỏi **nội dung được phê duyệt và có thể kiểm chứng**. Trong Spring Framework Mail, business service tạo notification với một template key và model có hợp đồng; registry chọn một revision đã published theo tenant/locale/variant; renderer như Thymeleaf kết xuất nội dung; MimeMessageHelper đóng gói MIME; còn JavaMailSender nộp qua SMTP. Quy tắc quyết định là **published revision bất biến, active pointer có thể thay đổi, notification phải pin đúng revision và dữ liệu cần thiết theo policy**. Khi bổ sung approval/audit, cache có kiểm soát, schema compatibility, canary, rollback, emergency revoke và transactional outbox, hệ thống có thể cập nhật nội dung linh hoạt mà không đánh mất khả năng giải thích một email đã được tạo từ **bản nào, dữ liệu nào và vì sao được phép gửi**.
