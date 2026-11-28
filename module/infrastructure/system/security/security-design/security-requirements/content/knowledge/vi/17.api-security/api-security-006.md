# Mass assignment

## 1. Mass assignment là lỗi cấp quyền ghi thuộc tính

Mass assignment xảy ra khi ứng dụng nhận các thuộc tính do client cung cấp rồi tự động gán chúng vào đối tượng nội bộ mà không kiểm soát đầy đủ thuộc tính nào người gọi được phép sửa. Vấn đề không nằm ở việc một request có nhiều trường; vấn đề là dữ liệu đầu vào quyết định được những thay đổi vượt quyền nghiệp vụ.

Giả sử học viên được sửa tên hiển thị và múi giờ. Entity tài khoản đồng thời có `role`, `tenantId`, `emailVerified` và `accountLocked`. Nếu API bind request trực tiếp vào entity hoặc sao chép mọi thuộc tính trùng tên, học viên có thể gửi thêm trường không xuất hiện trên giao diện. Một giá trị hoàn toàn đúng kiểu, như `emailVerified: true`, vẫn là thay đổi trái quyền.

OWASP khuyến nghị DTO đầu vào chỉ chứa trường được phép sửa hoặc allowlist rõ ràng khi binding; các cơ chế này vẫn phải đi cùng phân quyền đối tượng và thao tác. [OWASP: Mass Assignment Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html).

Trong module yêu cầu bảo mật, câu hỏi cần đặc tả không chỉ là “endpoint này dành cho ai?” mà còn là: với đúng đối tượng, trạng thái và thao tác đó, người gọi được đọc, đặt, xóa hay thay đổi những thuộc tính nào?

Sau bài học, người học cần xây dựng được ma trận quyền ghi theo trường, chọn ranh giới DTO phù hợp và viết tiêu chí chứng minh trường nhạy cảm giữ nguyên trước các request ngoài hợp đồng.

## 2. Một request hợp lệ về JSON vẫn có thể vượt quyền

Request mà màn hình chỉnh hồ sơ dự định gửi:

```http
PUT /api/v1/me/profile
Content-Type: application/json

{
  "displayName": "Lan Nguyễn",
  "timezone": "Asia/Ho_Chi_Minh",
  "emailNotifications": true
}
```

Một client tự viết có thể bổ sung các trường sau, dù giao diện không có ô nhập tương ứng:

```json
{
  "displayName": "Lan Nguyễn",
  "timezone": "Asia/Ho_Chi_Minh",
  "emailNotifications": true,
  "role": "TENANT_ADMIN",
  "emailVerified": true,
  "tenantId": "another-tenant",
  "accountLocked": false
}
```

Đây là ví dụ kiểm tra cho hệ thống được phép đánh giá, không phải thay đổi cần thực hiện trong module học tập. Điều phải quan sát là trạng thái lưu trữ và hiệu ứng nghiệp vụ: role có đổi không, cờ xác minh có được đặt không, hoặc dữ liệu có dịch sang tenant khác không?

Một API có thể trả lỗi nhưng đã ghi một phần thay đổi trước đó. Ngược lại, một API bỏ qua trường ngoài schema có thể trả thành công mà không sửa trường nhạy cảm. Do đó mã HTTP một mình chưa chứng minh có hay không có mass assignment; phải đối chiếu contract và trạng thái sau xử lý.

### 2.1. Những điều không phải hàng rào quyền ghi

Ẩn field khỏi form chỉ giới hạn giao diện thông thường. Kiểm tra rằng người dùng đã đăng nhập chỉ xác định danh tính. `@Valid` có thể xác minh dữ liệu đáp ứng constraint, nhưng một giá trị role hợp lệ vẫn chưa chắc được người dùng đó phép đặt. Escape đầu ra cũng không ngăn server lưu một thuộc tính trái quyền.

Các kiểm soát này hữu ích cho nhiệm vụ riêng của chúng. Quyền ghi trường phải được thể hiện bằng hợp đồng đầu vào và logic nghiệp vụ ở server.

## 3. Phân biệt ba mức phân quyền

| Mức | Câu hỏi | Ví dụ vi phạm |
| --- | --- | --- |
| Thao tác hoặc chức năng | Người gọi có được thực hiện hành động này không? | Học viên gọi thao tác cấp quyền quản trị |
| Đối tượng | Người gọi có được tác động đúng tài khoản hay khóa học này không? | Sửa hồ sơ của một người khác bằng cách đổi ID |
| Thuộc tính | Trong đối tượng được phép, trường nào có thể thay đổi? | Sửa hồ sơ của chính mình nhưng đặt `emailVerified=true` |

Mass assignment thường liên quan mức thuộc tính, nhưng có thể phá cả phạm vi đối tượng nếu `ownerId` hay `tenantId` được lấy từ body. Một DTO không có `role` vẫn chưa đủ nếu endpoint cho phép sửa tài khoản bất kỳ mà không kiểm tra quyền đối tượng.

OWASP API3:2023 Broken Object Property Level Authorization bao gồm việc công bố thuộc tính ngoài quyền và việc cho phép thay đổi thuộc tính nhạy cảm ngoài quyền; mass assignment thuộc phía ghi của vấn đề này. [OWASP API Security: API3:2023](https://api-security.owasp.org/editions/2023/en/0xa3-broken-object-property-level-authorization/).

Trong thiết kế cổng học tập, nên kiểm tra cả ba mức theo thứ tự rõ ràng: thao tác có được cấp không, đối tượng thuộc phạm vi nào, rồi tập thay đổi trường có được phép không. Không suy ra quyền sửa toàn bộ thuộc tính chỉ vì đã tải được entity.

## 4. Lập ma trận quyền ghi trước khi chọn annotation

Với tính năng hồ sơ, một ma trận mẫu có thể như sau:

| Trường | Học viên sửa hồ sơ mình | Quản trị tổ chức | Nguồn thay đổi được chốt |
| --- | --- | --- | --- |
| `displayName` | Có, trong giới hạn nội dung | Có qua thao tác được phân quyền riêng | DTO của đúng thao tác |
| `timezone` | Có, là zone được hỗ trợ | Có nếu nghiệp vụ cho phép | DTO và kiểm tra miền |
| `emailNotifications` | Có, bắt buộc là lựa chọn rõ | Không tự suy ra từ quyền admin | Tùy chọn của chủ tài khoản |
| `role` | Không | Chỉ thao tác cấp quyền riêng, trong phạm vi tổ chức | Dịch vụ phân quyền |
| `emailVerified` | Không | Không qua chỉnh hồ sơ | Luồng xác minh email |
| `accountLocked` | Không | Chỉ thao tác khóa hoặc mở khóa riêng | Dịch vụ quản trị tài khoản |
| `tenantId` | Không | Không qua chỉnh hồ sơ | Ngữ cảnh tổ chức đã được server xác lập |
| `createdAt` | Không | Không | Server và lưu trữ |
| `version` | Không ghi trực tiếp | Không ghi trực tiếp | Cơ chế kiểm soát đồng thời |

Đây là policy minh họa, không phải ma trận bắt buộc cho mọi nền tảng. Chẳng hạn quyền sửa tùy chọn thông báo của người khác có thể khác theo sản phẩm; nếu được cấp, phải có lý do và thao tác riêng, không phát sinh ngầm từ DTO quá rộng.

Mỗi ô “có” cần gắn với điều kiện. Người dùng đã bị khóa có còn được sửa hồ sơ không? Quản trị có được sửa tài khoản thuộc tenant khác không? Đổi role có cần xác thực bổ sung hay chặn tự tăng quyền không? Các điều kiện đó thuộc hợp đồng nghiệp vụ, không nằm trong cơ chế binder.

## 5. Tách request DTO, domain model và response DTO

Một thiết kế dễ kiểm chứng dùng ba mô hình có mục đích riêng:

```text
UpdateMyProfileRequest
  displayName
  timezone
  emailNotifications

UserAccount (domain và lưu trữ)
  userId, tenantId, displayName, timezone, emailNotifications,
  role, emailVerified, accountLocked, createdAt, version

MyProfileResponse
  displayName
  timezone
  emailNotifications
```

Request DTO không có `role` vì chỉnh hồ sơ không phải thao tác cấp quyền. Response DTO không được tái sử dụng máy móc làm request DTO: một trường người dùng được xem, như trạng thái xác minh email, chưa chắc là trường họ được phép đặt.

Tương tự, không dùng một DTO chung cho đăng ký, tự sửa hồ sơ và quản trị tài khoản chỉ vì các thao tác cùng liên quan đến `UserAccount`. Khi quyền thay đổi, contract đầu vào cũng thay đổi.

Mapping từ DTO sang domain phải ghi rõ từng thay đổi được phép. Những đoạn như `copyProperties(request, entity)`, ORM merge object do client tạo, hoặc vòng lặp gọi setter theo tên field làm tập quyền ghi phụ thuộc vào hình dạng class. Một setter mới có thể vô tình mở thêm quyền cho endpoint cũ.

Ranh giới DTO giúp giảm tập thuộc tính có thể nhận; mapping tường minh giúp giảm tập thuộc tính thực sự được ghi. Hai lớp bổ sung cho nhau, thay vì mặc định một DTO tên “safe” tự bảo đảm mọi hành vi phía sau.

## 6. Ví dụ Java: chỉ tạo ba thay đổi được phép

Ví dụ dưới đây dùng Java 17. Nó minh họa service cho thao tác thay thế toàn bộ ba tùy chọn hồ sơ, không phải một JSON Merge Patch. Các interface và record được đặt cùng ví dụ để thể hiện ranh giới; repository thực tế phải giữ đúng contract đã mô tả.

```java
import java.time.DateTimeException;
import java.time.ZoneId;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;

public final class ProfileApplication {
    // Chỉ adapter xác thực của server tạo actor này.
    // Không deserialize record này từ request body hoặc header tùy ý.
    public record TrustedActor(UUID userId, UUID tenantId) {
        public TrustedActor {
            Objects.requireNonNull(userId, "userId");
            Objects.requireNonNull(tenantId, "tenantId");
        }
    }

    public record UpdateMyProfileRequest(
            String displayName,
            String timezone,
            Boolean emailNotifications
    ) {}

    public record ProfileChanges(
            String displayName,
            String timezone,
            boolean emailNotifications
    ) {}

    public record ProfileSnapshot(boolean accountLocked, long version) {}

    public interface ProfileRepository {
        Optional<ProfileSnapshot> find(UUID userId, UUID tenantId);

        // Chỉ cập nhật ba field của ProfileChanges và tăng version.
        // Điều kiện ghi bao gồm userId, tenantId, expectedVersion,
        // và trạng thái tài khoản chưa bị khóa.
        int updatePreferences(
                UUID userId,
                UUID tenantId,
                long expectedVersion,
                ProfileChanges changes
        );
    }

    private final ProfileRepository repository;

    public ProfileApplication(ProfileRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    public void updateSelf(TrustedActor actor, UpdateMyProfileRequest request) {
        Objects.requireNonNull(actor, "Authenticated actor required");
        ProfileChanges changes = validate(request);

        ProfileSnapshot current = repository.find(actor.userId(), actor.tenantId())
                .orElseThrow(() -> new IllegalStateException("Profile unavailable"));
        if (current.accountLocked()) {
            throw new IllegalStateException("Profile cannot be changed");
        }

        int updated = repository.updatePreferences(
                actor.userId(), actor.tenantId(), current.version(), changes
        );
        if (updated != 1) {
            throw new IllegalStateException("Profile changed or unavailable");
        }
    }

    private static ProfileChanges validate(UpdateMyProfileRequest request) {
        if (request == null || request.displayName() == null
                || request.timezone() == null
                || request.emailNotifications() == null) {
            throw new IllegalArgumentException("All profile fields are required");
        }

        String name = request.displayName();
        if (name.isBlank() || name.codePointCount(0, name.length()) > 80
                || name.codePoints().anyMatch(Character::isISOControl)) {
            throw new IllegalArgumentException("Invalid display name");
        }

        String zone = request.timezone();
        if (zone.length() > 64) {
            throw new IllegalArgumentException("Invalid timezone");
        }
        try {
            ZoneId.of(zone);
        } catch (DateTimeException invalidZone) {
            throw new IllegalArgumentException("Invalid timezone");
        }

        return new ProfileChanges(name, zone, request.emailNotifications());
    }
}
```

Tên hiển thị tối đa 80 code point và giới hạn chuỗi zone là lựa chọn của ví dụ. `Boolean` thay vì primitive `boolean` giúp service nhận biết trường bị thiếu hoặc null theo cách binding đã chọn; quy tắc của thao tác này yêu cầu cả ba giá trị rõ ràng.

Kiểm tra múi giờ ở ví dụ chỉ yêu cầu giá trị mà `ZoneId.of` chấp nhận. Nếu sản phẩm chỉ cho phép một tập zone khu vực cụ thể, cần allowlist thêm theo chính sách đó. Validation về miền dữ liệu không tự trở thành phân quyền thuộc tính.

Service không nhận `userId` hay `tenantId` từ body. `TrustedActor` phải được tạo từ ngữ cảnh xác thực và phạm vi tổ chức đã được kiểm tra ở server. Việc đặt tên class là “Trusted” không làm dữ liệu header do client tự gửi trở nên đáng tin.

### 6.1. Câu lệnh lưu trữ cũng giữ tập trường đóng

Contract của repository có thể được thể hiện bằng câu SQL có parameter binding như sau:

```sql
UPDATE user_profiles
SET display_name = :displayName,
    timezone = :timezone,
    email_notifications = :emailNotifications,
    version = version + 1
WHERE user_id = :actorUserId
  AND tenant_id = :actorTenantId
  AND version = :expectedVersion
  AND account_locked = FALSE;
```

Các tên cột cập nhật là hằng trong mã repository. Không xây phần `SET` bằng tên field từ request. `expectedVersion` ở ví dụ được lấy từ snapshot server, không phải một trường entity mà client được tự ghi đè.

Điều kiện version và khóa tài khoản giúp việc kiểm tra không bị tách rời hoàn toàn khỏi thời điểm ghi. Triển khai cần kiểm tra đúng số dòng cập nhật và chọn transaction phù hợp khi có thêm thay đổi hoặc audit. Nếu thao tác cần cập nhật nhiều bảng, phải bảo đảm không có trạng thái chỉ một phần được lưu khi một điều kiện quyền thất bại.

Các exception trong ví dụ chỉ biểu diễn nhánh điều khiển. Adapter HTTP phải ánh xạ chúng thành error contract của sản phẩm và không trả stack trace hoặc chi tiết đối tượng nội bộ cho client.

## 7. Phân biệt JSON deserialization và form data binding trong Spring

Trong Spring MVC, `@RequestBody` đọc và deserialize body thông qua `HttpMessageConverter`. Cần kiểm soát DTO và cấu hình converter tương ứng, không giả định một cấu hình binder cho form đã tự khóa toàn bộ JSON property. [Spring Framework: @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html).

Với form hoặc model binding dùng `WebDataBinder`, Spring khuyến nghị model đầu vào chuyên biệt; nếu dùng property binding, có thể khai báo `allowedFields` theo các đường dẫn được phép. Cần xét cả nested property và constructor binding của cơ chế đang dùng. [Spring Framework: Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html).

Một form cập nhật hồ sơ có thể dùng allowlist rõ ràng:

```java
@InitBinder("profileForm")
void bindProfileForm(WebDataBinder binder) {
    binder.setAllowedFields("displayName", "timezone", "emailNotifications");
}
```

Đây là ví dụ cho đúng form binder được chỉ định. Nó không thay request DTO, kiểm tra quyền đối tượng hoặc mapping ở service. Tránh wildcard rộng như `*` hoặc `preferences.*` nếu domain bên trong có cả thuộc tính không dành cho client.

Đối với JSON, nếu contract quyết định từ chối field ngoài DTO, Jackson 2.x có thể được cấu hình rõ bằng `FAIL_ON_UNKNOWN_PROPERTIES` trên mapper hoặc reader được endpoint thực sự sử dụng. Đừng dựa vào default của một framework hay một mapper khác trong test. Các annotation bỏ qua field, handler tùy chỉnh hoặc setter nhận thuộc tính bất kỳ cũng phải được xét. [Jackson: DeserializationFeature](https://raw.githubusercontent.com/FasterXML/jackson-databind/2.20/src/main/java/com/fasterxml/jackson/databind/DeserializationFeature.java).

```java
ObjectReader profileReader = mapper
        .readerFor(ProfileApplication.UpdateMyProfileRequest.class)
        .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
```

Đoạn mã minh họa một reader có contract từ chối unknown property. Muốn có hiệu lực trong endpoint, adapter hoặc converter phải dùng đúng reader/configuration đó. Chỉ khai báo nó trong một utility không được gọi sẽ không thay đổi đường xử lý HTTP.

Quan trọng hơn, unknown-field rejection chỉ chặn trường không thuộc DTO. Nếu DTO đã chứa `role`, Jackson nhận `role` thành công là hành vi đúng của thư viện; lỗi quyền vẫn nằm trong thiết kế ứng dụng. Cần giữ tập field nhỏ trước, rồi kiểm tra policy của từng thao tác.

## 8. Nested object và đường dẫn thuộc tính cũng thuộc hợp đồng quyền

Một DTO có vẻ nhỏ vẫn có thể mở quá nhiều quyền nếu chứa một object tổng quát:

```java
// Thiết kế cần tránh cho thao tác tự sửa hồ sơ.
record UpdateProfile(String displayName, UserAccount account) {}
```

Client không cần field `role` ở root nếu nó có thể đi qua `account.role`. Tương tự, một `Map<String, Object> preferences` có thể trở thành cửa vào bất kỳ field nào nếu service merge toàn bộ map vào domain.

Các hình thức cần kiểm kê phụ thuộc cơ chế binding thực tế:

| Hình thức đầu vào | Ví dụ | Câu hỏi thiết kế |
| --- | --- | --- |
| JSON object lồng | `{"account":{"role":"ADMIN"}}` | Nested DTO có chứa trường ngoài quyền không? |
| Thuộc tính dạng đường dẫn trong form | `account.role=ADMIN` | Binder có cho truy cập đường dẫn đó không? |
| Phần tử collection | `members[0].role=ADMIN` | Ai được sửa phần tử nào và trường nào? |
| Map mở rộng | `{"metadata":{"role":"ADMIN"}}` | Metadata có bị trộn vào thuộc tính có thẩm quyền không? |
| Alias hoặc naming strategy | Tên JSON khác tên Java | Tất cả tên được chấp nhận có cùng policy không? |
| Trường dẫn xuất | `{"completed":true}` | Trạng thái này được client đặt hay server tính? |

Không mặc định một key chứa dấu chấm trong JSON luôn được xem là nested path. Hành vi do parser, binder và code mapping quyết định. Inventory phải mô tả đường mà ứng dụng thật sự hiểu, thay vì kiểm tra một dạng tên rồi suy ra các dạng khác đều bị chặn.

Với metadata do người dùng tùy chỉnh, có thể cho phép một map nếu nghiệp vụ cần. Nhưng map phải có namespace, giới hạn key/value, giới hạn kích thước và đích lưu riêng. Không dùng metadata để quyết định role, tenant, quyền sở hữu hoặc trạng thái xác minh.

Allowlist cần ở đúng cấp sâu. Cho phép object `settings` không có nghĩa cho phép toàn bộ cây con của `settings`. Nếu sau này thêm `settings.allowExternalAccess`, contract của endpoint cũ không được tự mở quyền ghi field mới chỉ vì wildcard đã có từ trước.

## 9. PATCH không phải quyền sửa mọi thuộc tính

### 9.1. Phân biệt vắng mặt, null và giá trị mới

Request DTO có field null không luôn cho biết client bỏ field đó hay chủ động gửi null. Với cập nhật từng phần, phải có mô hình thể hiện được sự hiện diện của field nếu nghiệp vụ cần phân biệt các trường hợp này.

| Tình huống | Ý nghĩa cần đặc tả |
| --- | --- |
| Không gửi `displayName` | Giữ nguyên tên hay báo thiếu field? |
| Gửi `displayName: null` | Xóa tên, từ chối hay một hành vi khác? |
| Gửi `displayName: ""` | Tên rỗng hợp lệ hay vi phạm validation? |
| Không gửi `role` | Giữ nguyên role hiện tại; không tự đặt default từ object mới |
| Gửi trường bị bảo vệ với null | Vẫn là yêu cầu sửa/xóa thuộc tính ngoài quyền |

Ví dụ Java phía trên chọn thao tác thay thế đầy đủ ba tùy chọn của tài nguyên hồ sơ và từ chối null/thiếu. Nó không cố biểu diễn PATCH bằng ba field nullable rồi đoán ý định của client.

### 9.2. JSON Merge Patch và JSON Patch cần policy riêng

JSON Merge Patch dùng cấu trúc gần với tài liệu đích; một thành viên có giá trị null mang ý nghĩa loại bỏ thành viên tương ứng. Vì vậy “chặn việc đặt role mới” nhưng bỏ qua thao tác xóa role vẫn để hở quyền thay đổi trạng thái. [RFC 7396: JSON Merge Patch](https://www.rfc-editor.org/rfc/rfc7396.html).

Không apply một merge patch chưa kiểm tra lên bản JSON của entity rồi deserialize ngược toàn bộ entity để lưu. Một thiết kế phù hợp hơn là xác định tập thay đổi được phép đối với tài nguyên đầu vào chuyên biệt, validation toàn bộ và mapping sang những thay đổi domain được phép.

JSON Patch biểu diễn các operation có `path`; một số operation còn có `from`. Quyền phải được xét theo operation và đường dẫn, không chỉ theo giá trị cuối. Với `move` hay `copy`, cần kiểm tra cả nguồn lẫn đích theo policy. [RFC 6902: JSON Patch](https://www.rfc-editor.org/rfc/rfc6902.html).

Ví dụ policy cho PATCH hồ sơ có thể chỉ cho operation thay thế ba đường dẫn cố định và từ chối operation khác. Đây là lựa chọn sản phẩm cần ghi rõ. Nếu thao tác ít và ổn định, DTO command riêng thường dễ giải thích và kiểm chứng hơn một engine patch tổng quát.

Kiểm tra đường dẫn phải theo cú pháp chuẩn của format đã chọn, bao gồm cách escape token trong JSON Pointer, chứ không dựa vào `startsWith("/profile")`. So sánh tiền tố có thể cấp quyền rộng hơn các đường dẫn thực sự được phép.

## 10. Từ chối field ngoài hợp đồng hay bỏ qua?

Hai policy có thể được sử dụng nếu được thiết kế và kiểm chứng rõ:

| Policy | Hành vi | Điều phải chứng minh |
| --- | --- | --- |
| Từ chối | Request có field không được hỗ trợ thất bại trước khi thay đổi | Không lưu một phần; error contract rõ |
| Bỏ qua có chủ đích | Field ngoài schema không tham gia command | Không tồn tại đường merge, listener hay mapper khác dùng lại raw input |

Đối với ví dụ hồ sơ, bài học chọn từ chối field ngoài DTO. Cách này giúp client phát hiện lỗi contract và giảm trường hợp tưởng một thao tác đã được thực hiện. Mã lỗi có thể là `400` hoặc mã validation khác theo quy ước API; không có một status code dùng chung thay thế cho policy.

Với field có trong schema của một thao tác nhưng bị cấm cho actor hiện tại, đây là nhánh phân quyền và cần error contract tương ứng. Không cần tiết lộ trong thông báo rằng hệ thống nội bộ có mọi field nhạy cảm nào.

Nếu request có cả thay đổi hợp lệ và thay đổi trái quyền, policy phải quyết định tính nguyên tử. Với chỉnh hồ sơ một người, nên validation và authorization toàn bộ command trước khi ghi, rồi chấp nhận hoặc từ chối cả thao tác. Không sửa tên trước rồi mới phát hiện client đồng thời muốn đổi role.

Các cơ chế blocklist như loại riêng `role` hoặc gắn annotation bỏ qua một field có thể là lớp hỗ trợ trong hệ thống cũ, nhưng không tự đóng tập quyền ghi. Một trường nhạy cảm mới như `billingAdmin` hay `supportImpersonationAllowed` có thể chưa nằm trong danh sách cấm. Nền tảng lâu dài là tập cho phép theo thao tác và mapping rõ ràng.

## 11. Quản trị, batch và import phải dùng cùng ranh giới quyền

### 11.1. Endpoint quản trị không có quyền sửa vô hạn

Thao tác cấp role cần một command riêng, ví dụ `AssignTenantRole`, thay vì thêm `role` vào DTO hồ sơ để tiện cho màn hình admin. Command cần xác định đối tượng trong phạm vi tenant, role được cấp, role mà actor được quyền cấp và các điều kiện như chặn tự tăng quyền nếu policy yêu cầu.

Quản trị tổ chức không tự có quyền cấp role quản trị toàn hệ thống. Không tin một `tenantId` trong body chỉ vì endpoint nằm dưới `/admin`; tenant phải được đối chiếu với quyền đã xác lập của actor.

Các hành động như xác minh email, mở khóa hoặc chuyển quyền sở hữu thường có điều kiện trạng thái và bằng chứng riêng. Gộp chúng thành một API “update user” tổng quát làm mất các gate nghiệp vụ đó, dù mỗi field đều đúng kiểu dữ liệu.

### 11.2. Batch có thể khuếch đại một lỗi field-level

Một endpoint cập nhật nhiều hồ sơ cần kiểm tra từng item theo cả đối tượng và tập field. Không kiểm tra quyền trên phần tử đầu rồi sao chép policy cho cả danh sách. Giới hạn số item và kích thước request cũng cần được chốt để khả năng xử lý không phụ thuộc vào số thuộc tính client tự gửi.

Nếu cho phép thành công từng phần, contract phải mô tả kết quả riêng của từng item và bảo đảm item bị từ chối không gây thay đổi. Nếu chọn all-or-nothing, cần validation/authorization cho toàn bộ tập và transaction phù hợp trước khi xác nhận thành công.

### 11.3. File import và job nền không được mở một đường merge khác

CSV hoặc JSON import vẫn là dữ liệu bên ngoài, dù được tải lên bởi nhân viên hỗ trợ. Cột `role`, `ownerId` hoặc `verified` không được tự trở thành quyền ghi chỉ vì có header tương ứng. Cần mapping cột theo loại tác vụ import và cùng các command nghiệp vụ đã chốt.

Với job nền, cần xác định quyền được kiểm tra lúc gửi, lúc thực thi hay cả hai. Nếu quyền bị thu hồi giữa hai thời điểm, policy phải nêu hành vi. Không để worker nền áp dụng object raw đã lưu với đặc quyền service mà bỏ qua ranh giới của thao tác gốc.

## 12. Audit và phát hiện mà không sao chép dữ liệu nhạy cảm

Một sự kiện từ chối có thể ghi các thông tin tối thiểu sau theo chính sách quan sát của hệ thống:

```json
{
  "event": "PROFILE_UPDATE_REJECTED",
  "reasonCode": "UNSUPPORTED_INPUT_PROPERTY",
  "operation": "UPDATE_MY_PROFILE",
  "actorRef": "internal-actor-reference",
  "tenantRef": "internal-tenant-reference",
  "correlationId": "request-correlation-reference"
}
```

Không cần log toàn bộ body để chứng minh request có thuộc tính ngoài hợp đồng. Body có thể chứa mật khẩu, token hoặc dữ liệu cá nhân do client gửi nhầm. Nếu lưu tên field bị từ chối để điều tra, cần giới hạn số lượng/độ dài và biểu diễn an toàn trong log viewer; không chép raw input không giới hạn vào thông điệp.

Đối với thao tác quản trị được phép, audit nên phản ánh thay đổi mà server thực sự đã áp dụng, không chỉ danh sách client tự khai báo. Ai cấp role gì cho ai, trong phạm vi nào và qua policy nào là bằng chứng hữu ích hơn một bản sao request.

Một lần gửi field lạ có thể là client cũ hoặc lỗi tích hợp. Việc tăng mức cảnh báo cần xét tần suất, số field nhạy cảm và ngữ cảnh actor, thay vì mặc định mọi lỗi schema là một cuộc tấn công. Các ngưỡng phát hiện phải được điều chỉnh theo lưu lượng và dữ liệu thực tế của sản phẩm.

## 13. Bộ yêu cầu bảo mật có thể nghiệm thu

| ID | Yêu cầu mẫu | Bằng chứng nghiệm thu |
| --- | --- | --- |
| SR-MA-01 | Mỗi thao tác ghi có ma trận actor–đối tượng–field và các điều kiện trạng thái | Ma trận được duyệt và mapping tới endpoint/command |
| SR-MA-02 | Endpoint tự sửa hồ sơ chỉ nhận ba field đã chốt; field ngoài DTO bị từ chối | Contract request và ca gửi thêm property |
| SR-MA-03 | `userId` và tenant scope dùng để chọn đối tượng bắt nguồn từ ngữ cảnh server đã xác thực, không từ body | Kiểm tra nguồn actor và ca sửa ID/tenant trong request |
| SR-MA-04 | Service và repository chỉ ghi tập field cho phép; không generic merge từ input vào entity | Đối chiếu mapping/cột cập nhật và trạng thái trước–sau |
| SR-MA-05 | Field nhạy cảm như role, xác minh email và khóa tài khoản chỉ đổi qua command riêng có policy | Ca sử dụng đường hồ sơ để đặt hoặc xóa từng field |
| SR-MA-06 | Allowlist áp dụng cho nested object, collection và alias mà binder chấp nhận | Inventory cơ chế binding và ca theo từng đường dẫn |
| SR-MA-07 | Request chứa thay đổi trái quyền bị chặn trước khi lưu bất kỳ thay đổi hồ sơ nào | Ca trộn field hợp lệ và field cấm, đọc lại dữ liệu |
| SR-MA-08 | PATCH có policy theo operation, path và ý nghĩa null/vắng mặt; không patch trực tiếp entity chưa kiểm tra | Ca replace/remove/copy/move theo format được hỗ trợ |
| SR-MA-09 | Batch/import/job nền không vượt tập quyền ghi của tác vụ được cấp | Ca đối tượng ngoài phạm vi và cột/field ngoài contract |
| SR-MA-10 | Thêm một property vào entity không tự mở quyền ghi của endpoint hiện có | Ca hồi quy với property domain mới |
| SR-MA-11 | Các điều kiện trạng thái và kiểm soát đồng thời được giữ tới thời điểm ghi | Ca khóa tài khoản hoặc đổi version trong lúc cập nhật |
| SR-MA-12 | Audit phản ánh actor, thao tác và kết quả server; không ghi raw body không giới hạn | Kiểm tra sự kiện thành công/từ chối và policy dữ liệu log |

SR-MA-02 là policy cụ thể của ví dụ. Nếu sản phẩm chọn bỏ qua unknown field, phải sửa yêu cầu và tiêu chí tương ứng, đồng thời giữ SR-MA-04: không có field bị bỏ qua nào được dùng lại qua raw map hoặc đường ghi khác.

SR-MA-08 chỉ áp dụng nếu endpoint thực sự hỗ trợ PATCH. Không cần triển khai cả JSON Patch lẫn Merge Patch chỉ để đáp ứng bài học; nên giới hạn số format được hỗ trợ theo nhu cầu sản phẩm.

## 14. Thiết kế ca kiểm thử theo trạng thái thực tế

Phần này mô tả bằng chứng cần có cho một triển khai sản phẩm; không khẳng định các kiểm thử đã được chạy trong bài học.

### 14.1. Chuẩn bị baseline và tập bất biến

Tạo một tài khoản thử có role học viên, email chưa xác minh, tenant A và trạng thái không khóa. Ghi nhận trạng thái ban đầu từ một kênh đọc có thẩm quyền phù hợp môi trường kiểm thử. Tập bất biến của thao tác hồ sơ gồm role, tenant, user ID, cờ xác minh, trạng thái khóa và thời điểm tạo.

Các field kỹ thuật như `version`, `updatedAt` hoặc sự kiện audit có thể được thay đổi theo contract khi thao tác thành công. Không gọi mọi thay đổi phụ là lỗi; phải phân biệt tập thay đổi được phép với các invariant nhạy cảm.

### 14.2. Ma trận ca kiểm thử

| Ca | Dữ liệu/hành động | Kỳ vọng theo policy ví dụ |
| --- | --- | --- |
| M1 | Ba tùy chọn hồ sơ hợp lệ | Chỉ ba giá trị tương ứng và metadata kỹ thuật được phép thay đổi |
| M2 | Thêm `role=TENANT_ADMIN` | Từ chối cả request; role và tên hồ sơ giữ baseline |
| M3 | Thêm `emailVerified=true` | Không thay trạng thái xác minh |
| M4 | Thêm `accountLocked=false` | Không mở khóa qua endpoint hồ sơ |
| M5 | Thêm `tenantId` hoặc `userId` của đối tượng khác | Không thay phạm vi tài khoản được chọn hoặc dữ liệu tenant khác |
| M6 | Gửi object lồng chứa field nhạy cảm | Từ chối nếu ngoài schema; không có cập nhật sâu |
| M7 | Gửi alias, khác casing hoặc tên theo binder đang hỗ trợ | Không tìm được đường ghi field ngoài quyền |
| M8 | Thiếu `emailNotifications` hoặc gửi null | Từ chối theo contract thay thế đủ ba tùy chọn |
| M9 | Tên rỗng, quá 80 code point hoặc có control character | Validation thất bại trước khi ghi |
| M10 | JSON có tên thành viên lặp hoặc nhiều biểu diễn mơ hồ | Hành vi parser được chốt; không có khác biệt giúp vượt policy |
| M11 | Thay đổi version hoặc khóa tài khoản trước conditional update | Không ghi theo snapshot quyền đã hết hiệu lực |
| M12 | Thêm property nhạy cảm mới vào domain trong bản thử | Endpoint hồ sơ vẫn không nhận/ghi property đó |

Ở M7 và M10, ca cụ thể phải dựa vào naming strategy, alias và parser thực tế. Không cần đoán mọi biến thể không được hệ thống hỗ trợ. Nhưng cần chứng minh các tầng như gateway, validation và service không hiểu request theo các tập field khác nhau.

### 14.3. Ca cho các đường cập nhật phụ

Nếu có JSON Patch, cần kiểm tra cả thao tác xóa field bị bảo vệ và operation có đường dẫn nguồn. Nếu có batch, đặt một đối tượng ngoài tenant giữa các đối tượng hợp lệ và xác minh tính nguyên tử hoặc kết quả từng item theo contract.

Nếu có import, thêm một cột nhạy cảm không được phép rồi kiểm tra dữ liệu sau khi job chạy. Nếu job nền dựa vào quyền động, kiểm tra tình huống quyền của actor bị thu hồi trước lúc thực thi. Đường không tồn tại trong sản phẩm không cần được tạo thêm để kiểm thử.

### 14.4. Điều kiện PASS không chỉ là một status code

Một ca từ chối cần chứng minh không có field nhạy cảm thay đổi, không có thay đổi hợp lệ bị lưu một phần trái policy, và không phát sinh tác dụng phụ ngoài hợp đồng. Với role, có thể cần kiểm tra cả quyền hiệu lực sau request trong môi trường thử, bởi một bản ghi role thay đổi có thể chưa xuất hiện trong response hồ sơ.

Đọc lại bằng đúng response DTO có thể chưa đủ nếu DTO cố ý không trả field nhạy cảm. Cần kênh quan sát kiểm thử có thẩm quyền như repository, audit hoặc API quản trị dành cho môi trường đó. Không mở thêm endpoint công khai để phục vụ việc đọc trạng thái nội bộ.

Nên có cả kiểm tra unit cho mapping/policy và kiểm tra tích hợp cho đường HTTP thật. Một reader strict trong unit test không chứng minh controller dùng cùng cấu hình; một service mapping đúng cũng không chứng minh đường import gọi service đó.

## 15. Những quyết định thường làm quyền ghi mở rộng ngoài ý muốn

**Dùng entity làm request vì giảm số class.** Entity thay đổi theo nhu cầu lưu trữ và nghiệp vụ nội bộ. Khi nó là contract HTTP, một thay đổi cấu trúc có thể trở thành thay đổi quyền của client.

**Dùng chung DTO đọc và ghi.** Một field trạng thái được phép xem có thể vô tình trở thành field được phép đặt. Tách hai hướng giúp biểu diễn đúng sự khác nhau đó.

**Kiểm tra role sau khi đã merge request.** Nếu client có thể tác động role của entity hoặc actor dùng trong kiểm tra, quyết định quyền đã dựa vào dữ liệu vừa bị sửa. Giữ ngữ cảnh actor độc lập với đối tượng request.

**Xây entity mới từ body rồi save.** Những field client không gửi có thể bị reset về default hoặc null thay vì giữ giá trị server. Chỉnh ba tùy chọn không nên tạo lại toàn bộ tài khoản từ input.

**Cho phép một map vì “client chỉ gửi field hợp lệ”.** Contract phải được thực thi ở server, kể cả khi client chính thức luôn gửi đúng. Các client tùy biến vẫn nằm trong mô hình đe dọa.

**Chỉ chặn tên field nhạy cảm hiện tại.** Blacklist không bảo vệ field mới và đường dẫn lồng mới. Tập cho phép theo thao tác giữ mặc định từ chối đối với phần mở rộng của domain.

**Cho service nền đặc quyền merge mọi thứ.** Service account là danh tính thực thi, không tự cấp cho request gốc quyền đổi mọi thuộc tính. Command đã duyệt và phạm vi actor phải được giữ qua hàng đợi.

## 16. Bài tập vận dụng

Một nền tảng cho giảng viên sửa khóa học có entity gồm `title`, `description`, `price`, `ownerId`, `tenantId`, `published`, `reviewApproved`, `salesCount` và `version`. Màn hình đang gửi cả object tải từ API đọc trở lại một endpoint cập nhật tổng quát.

Hãy thực hiện các quyết định sau:

1. Tách thao tác sửa nội dung, thay giá và yêu cầu xuất bản; chỉ rõ trường nào là server-owned hoặc cần một luồng duyệt riêng.
2. Lập ma trận quyền ghi cho giảng viên sở hữu khóa học, giảng viên khác và quản trị trong cùng tenant.
3. Thiết kế request DTO cho từng thao tác, không dùng response object làm input chung.
4. Chọn policy đối với field ngoài schema và đối với request trộn trường hợp lệ với trường trái quyền.
5. Viết một invariant cho quyền sở hữu và một invariant cho trạng thái duyệt; chỉ ra vị trí kiểm tra tới thời điểm lưu.
6. Đề xuất ba ca nghiệm thu quan sát được trạng thái sau request, bao gồm một ca nested input hoặc PATCH nếu sản phẩm hỗ trợ.

Kết quả cần thể hiện rõ ai được sửa trường nào trên đối tượng nào và qua thao tác nào. Chống mass assignment là giữ tập quyền ghi đó không bị mở rộng bởi tên field, cơ chế binding hay đường cập nhật phụ do client điều khiển.
