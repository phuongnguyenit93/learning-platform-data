# Configuration validation

## 1. Mục tiêu và phạm vi

Configuration validation là việc kiểm tra một cấu hình có thỏa mãn các ràng buộc đã đặc tả trước khi hệ thống sử dụng cấu hình đó. Trong chương Configuration security, mục tiêu bảo mật là ngăn một thay đổi cấu hình làm mất xác thực, mở rộng quyền truy cập, sử dụng sai nguồn định danh, bỏ sót nhật ký bắt buộc hoặc làm hệ thống không thể phục hồi an toàn.

Một file YAML đọc được chưa chứng minh cấu hình an toàn. Giá trị `session.maxLifetimeSeconds: 86400` có thể đúng kiểu số nguyên nhưng vượt giới hạn phiên mà hệ thống chấp nhận. Hai giá trị hợp lệ riêng lẻ cũng có thể mâu thuẫn, chẳng hạn thời gian hết hạn do không hoạt động lớn hơn thời gian sống tối đa của phiên.

Trong đặc tả yêu cầu bảo mật, validation phải trả lời được:

- Cấu hình nào được phép tồn tại trong từng ngữ cảnh triển khai?
- Ràng buộc nào được kiểm tra bằng máy, tại điểm nào?
- Điều gì xảy ra khi một cấu hình không hợp lệ hoặc không thể xác minh?
- Bằng chứng nào cho thấy đúng cấu hình đã được kiểm tra và kích hoạt?

Bài học dùng ví dụ một dịch vụ xử lý đơn hàng. Các con số và chính sách bên dưới là **hợp đồng minh họa cho dịch vụ này**, cần được lựa chọn lại theo mô hình đe dọa và nhu cầu vận hành của hệ thống thực tế.

## 2. Từ rủi ro đến bất biến cấu hình

Rủi ro cấu hình thường xuất phát từ lỗi thao tác, cách diễn giải khác nhau giữa các công cụ, nguồn ghi đè không được kiểm soát hoặc quyền sửa cấu hình bị lạm dụng.

| Tình huống | Hậu quả có thể xảy ra | Bất biến cần đặc tả |
| --- | --- | --- |
| Một biến môi trường đặt `requireAuthentication=false` | Người chưa xác thực gọi API được bảo vệ | Mọi cấu hình hoạt động của dịch vụ phải yêu cầu xác thực cho API được bảo vệ |
| Đổi nhà phát hành token sang địa chỉ do người sửa tự chọn | Hệ thống tin token không thuộc miền định danh dự kiến | Issuer và audience phải thuộc tập được phê duyệt cho môi trường triển khai |
| Tăng thời gian sống phiên vượt chính sách | Phiên bị đánh cắp có hiệu lực lâu hơn mức chấp nhận | Thời gian sống phải dương và không vượt mức tối đa được phê duyệt |
| Tắt audit để xử lý sự cố | Mất dấu vết hành vi đặc quyền | Các sự kiện audit bắt buộc phải có tuyến ghi đáp ứng chính sách |
| Hai thành phần hiểu khóa YAML trùng khác nhau | Kiểm tra và chạy sử dụng hai giá trị khác nhau | Khóa trùng bị từ chối ngay khi phân tích từng nguồn |
| Chỉ cập nhật được một phần cấu hình đang chạy | Xác thực và phân quyền dùng các phiên bản không tương thích | Kích hoạt toàn bộ một snapshot đã kiểm tra như một đơn vị |
| Khôi phục bản cũ chứa khóa đã thu hồi | Quay lại trạng thái không còn an toàn | Rollback phải được đánh giá theo chính sách và trạng thái thu hồi hiện tại |

Một yêu cầu tốt nêu điều kiện, hành vi bắt buộc và bằng chứng kiểm tra được. “Cấu hình phải an toàn” chưa đủ. “Dịch vụ từ chối kích hoạt cấu hình có `access.defaultDecision` khác `deny`; kiểm thử phải xác nhận phiên bản đang chạy không thay đổi khi cập nhật bị từ chối” là một yêu cầu có thể xác minh.

Validator cũng có giới hạn tin cậy. Nếu cùng một chủ thể có thể tùy ý sửa cả cấu hình ứng viên lẫn bộ quy tắc phê duyệt, họ có thể làm cho thay đổi nguy hiểm vượt qua kiểm tra. Quyền sửa schema, chính sách, danh sách cho phép và chương trình validation cần được bảo vệ tương ứng với ảnh hưởng của chúng.

## 3. Những lớp kiểm tra cần phân biệt

### 3.1. Cú pháp và giới hạn đầu vào

Parser cần phát hiện tài liệu sai cú pháp, khóa trùng và cấu trúc vượt giới hạn cho phép. Đặc tả phải giới hạn kích thước tài liệu, độ sâu lồng nhau, độ dài chuỗi và số phần tử theo khả năng của hệ thống. Nếu dùng YAML, cần cấu hình parser để không khởi tạo đối tượng tùy ý từ tag và kiểm soát việc mở rộng alias.

Kiểm tra khóa trùng phải diễn ra **trước khi parser làm mất thông tin đó**. Một schema chạy trên map đã bị ghi đè không thể phát hiện chắc chắn rằng nguồn ban đầu chứa hai khóa cùng tên.

### 3.2. Cấu trúc, kiểu và miền giá trị

Schema hoặc bộ ràng buộc tương đương xác định:

- Các trường bắt buộc và các trường được phép xuất hiện.
- Kiểu dữ liệu, đơn vị đo và cách biểu diễn.
- Giá trị liệt kê, khoảng hợp lệ và giới hạn độ dài.
- Cách xử lý trường không biết và phiên bản schema không được hỗ trợ.
- Ý nghĩa của trường bị thiếu, giá trị `null`, chuỗi rỗng và giá trị mặc định.

Ví dụ, `audit.enabled` phải là boolean thật. Nếu hợp đồng không cho phép ép kiểu ngầm thì chuỗi `"false"` bị từ chối, dù một công cụ binding nào đó có thể chuyển nó thành boolean.

Với trường liên quan bảo mật, không nên âm thầm bỏ qua khóa lạ. Lỗi gõ `requireAuthenticaton` phải được báo rõ, thay vì khiến người vận hành tưởng rằng yêu cầu xác thực đã được cấu hình.

### 3.3. Ngữ nghĩa và quan hệ giữa các trường

Kiểu dữ liệu không đủ để chứng minh:

- `0 < idleTimeoutSeconds <= maxLifetimeSeconds <= 900`.
- `requireAuthentication` phải bật khi API có dữ liệu riêng tư.
- `defaultDecision` phải là `deny`.
- `audit.enabled=true` phải đi cùng một tuyến ghi audit được phê duyệt.
- Một loại thông tin xác thực phải đi cùng đúng loại tham chiếu khóa.

Các quan hệ này phải được kiểm tra trên **cấu hình hiệu lực**, sau khi kết hợp các nguồn và áp dụng các giá trị mặc định được phép.

### 3.4. Ngữ cảnh triển khai

Cấu hình hợp lệ ở một môi trường chưa chắc hợp lệ ở môi trường khác. Issuer thử nghiệm không được tự động trở thành issuer sản xuất.

Ngữ cảnh dùng để chọn chính sách phải đến từ nguồn triển khai đáng tin cậy. Không dùng chính trường `environment` trong cấu hình ứng viên làm căn cứ duy nhất để hạ yêu cầu bảo mật. Nếu người sửa cấu hình có thể đổi `production` thành `development`, họ không được vì thế mà bỏ qua chính sách sản xuất.

### 3.5. Tham chiếu và điều kiện vận hành

Tham chiếu tới khóa, chứng thư, nơi nhận audit hoặc dịch vụ định danh cần được kiểm tra về tính phù hợp:

- Có thuộc tài nguyên, tenant và môi trường được phê duyệt không?
- Phiên bản tài nguyên có còn được phép sử dụng không?
- Quyền truy cập có đủ và nằm trong phạm vi cần thiết không?
- Khóa hoặc chứng thư có thỏa điều kiện hiệu lực tại thời điểm sử dụng không?
- Điều kiện vận hành có cho phép cung cấp chức năng được bảo vệ không?

Phân biệt hai kết quả: **cấu hình vi phạm chính sách** và **chưa thể xác minh điều kiện phụ thuộc**. Một tham chiếu đúng định dạng nhưng kho bí mật tạm thời không truy cập được không đồng nghĩa với sai schema; cũng không đủ cơ sở để công bố ứng dụng đã sẵn sàng.

Kiểm tra tại một thời điểm không bảo đảm tài nguyên sẽ luôn sẵn sàng hoặc luôn hợp lệ. Hệ thống vẫn cần kiểm tra khi sử dụng, xử lý thu hồi và chính sách ứng phó với lỗi trong thời gian chạy.

## 4. Ví dụ cấu hình và hợp đồng của dịch vụ

Đây là cấu hình ứng viên minh họa. Các tham chiếu chỉ là định danh do nền tảng quản lý, không phải giá trị bí mật:

```yaml
schemaVersion: 1
environment: production

identity:
  issuer: https://id.example.com/realms/orders
  audience: orders-api

access:
  requireAuthentication: true
  defaultDecision: deny
  adminPublic: false

session:
  maxLifetimeSeconds: 900
  idleTimeoutSeconds: 300

audit:
  enabled: true
  destinationRef: audit-orders-production

credentials:
  signingKeyRef: secrets/orders/production/signing-key
```

Trong ví dụ này:

1. Dịch vụ triển khai ở production theo ngữ cảnh do nền tảng triển khai cấp.
2. Issuer và audience phải khớp danh sách được phê duyệt riêng cho dịch vụ và môi trường đó.
3. Mọi API được bảo vệ yêu cầu xác thực; quyết định phân quyền mặc định là từ chối.
4. Giao diện quản trị không được công khai bằng cấu hình `adminPublic=true`.
5. Thời gian sống tối đa của phiên nằm trong khoảng 1–900 giây; thời gian không hoạt động dương và không lớn hơn thời gian sống tối đa.
6. Audit bắt buộc phải bật và dùng đích được phê duyệt.
7. Tham chiếu khóa phải thuộc đúng dịch vụ, môi trường và phiên bản đang được phép sử dụng.

Các trường trên chỉ mô tả một phần của kiến trúc. Ví dụ, `adminPublic=false` không thay thế phân quyền quản trị và các giới hạn mạng đã đặc tả ở lớp triển khai. Validator phải kiểm tra những đầu vào liên quan, còn thiết kế kiểm soát phải chỉ rõ thành phần thực sự cưỡng chế từng bất biến.

Giới hạn 900 giây chỉ có ý nghĩa khi thành phần quản lý phiên thực sự áp dụng nó. Nếu hệ thống còn chấp nhận token do bên khác cấp, cần đặc tả riêng các điều kiện chấp nhận token, thời gian hiệu lực và cơ chế thu hồi; không mặc định coi một trường cấu hình phiên là đã kiểm soát toàn bộ token.

## 5. Viết yêu cầu bảo mật có thể nghiệm thu

Mỗi yêu cầu nên có mã định danh, rủi ro liên quan, điểm cưỡng chế và tiêu chí chấp nhận. Bảng sau minh họa cách chuyển hợp đồng ở trên thành yêu cầu cụ thể.

| Mã | Yêu cầu | Tiêu chí chấp nhận và bằng chứng |
| --- | --- | --- |
| SEC-CFG-01 | Mọi nguồn cấu hình phải được phân tích bằng quy tắc cú pháp thống nhất; từ chối khóa trùng, trường lạ và schema không hỗ trợ | Các mẫu sai tương ứng bị từ chối trước kích hoạt; lỗi chỉ ra mã và đường dẫn trường |
| SEC-CFG-02 | Chính sách môi trường phải được chọn từ ngữ cảnh triển khai đáng tin cậy | Trên production, đổi `environment` trong ứng viên không cho phép áp dụng chính sách development |
| SEC-CFG-03 | Cấu hình hiệu lực phải yêu cầu xác thực, dùng phân quyền mặc định từ chối và không công khai quản trị | Mỗi thay đổi vi phạm bị từ chối; không có lần xử lý yêu cầu mới nào dùng cấu hình đó |
| SEC-CFG-04 | Giới hạn phiên phải thỏa `0 < idle <= max <= 900` giây | Các trường hợp 0, âm, 901 và `idle > max` thất bại; các giá trị biên hợp lệ vượt qua kiểm tra này |
| SEC-CFG-05 | Issuer, audience, đích audit và tham chiếu khóa phải thuộc tập được phê duyệt cho ngữ cảnh hiện tại | Giá trị khác môi trường hoặc ngoài danh sách cho phép bị từ chối, kể cả khi đúng định dạng |
| SEC-CFG-06 | Không được kích hoạt ứng viên thiếu điều kiện audit hoặc thông tin xác thực bắt buộc | Kiểm thử chứng minh không công bố sẵn sàng hoặc kích hoạt bản mới khi thiếu các điều kiện đã quy định |
| SEC-CFG-07 | Việc kích hoạt phải sử dụng nguyên vẹn snapshot đã kiểm tra và chỉ thành công khi phiên bản nền còn phù hợp | Kiểm thử cập nhật cạnh tranh không tạo trạng thái trộn; mỗi yêu cầu dùng một snapshot nhất quán |
| SEC-CFG-08 | Khi cập nhật bị từ chối, chỉ được giữ bản đang chạy nếu bản đó vẫn hợp lệ theo chính sách hiện tại | Kiểm thử phân biệt bản cũ còn hiệu lực với bản đã bị thu hồi hoặc hết hạn |
| SEC-CFG-09 | Kết quả validation phải quan sát được mà không lộ bí mật | Có phiên bản, mã lỗi và đường dẫn trường; không có token, mật khẩu, nội dung khóa hoặc toàn bộ cấu hình trong log |
| SEC-CFG-10 | Rollback phải được kiểm tra lại theo chính sách hiện tại và có thẩm quyền phù hợp | Bản cũ chứa khóa đã thu hồi không được kích hoạt dù từng vượt qua kiểm tra |

“Có log lỗi” không phải tiêu chí đủ cho SEC-CFG-09. Hợp đồng cần nêu các trường được ghi, nơi nhận, quyền đọc, thời gian lưu và cách kiểm thử không rò rỉ. Tương tự, ngưỡng cảnh báo số lần validation thất bại cần được thống nhất theo vận hành của dịch vụ.

### Ví dụ tiêu chí theo Given/When/Then

```text
Given:
  Dịch vụ production đang dùng cấu hình thế hệ 41.
  Chính sách giới hạn thời gian sống phiên tối đa là 900 giây.

When:
  Ứng viên thế hệ 42 đặt maxLifetimeSeconds = 901.

Then:
  Ứng viên bị từ chối với mã SESSION_MAX_OUT_OF_RANGE.
  Thế hệ hoạt động vẫn là 41 nếu nó còn hợp lệ.
  Không có yêu cầu mới nào quan sát cấu hình thế hệ 42.
  Sự kiện từ chối chứa phiên bản và tên trường, không chứa bí mật.
```

Các tiêu chí này kiểm tra cả kết quả validation lẫn tác động của nó lên hệ thống.

## 6. Kiểm tra cấu hình hiệu lực sau khi kết hợp nguồn

Một dịch vụ có thể đọc cấu hình từ file nền, file môi trường, biến môi trường, tham số khởi chạy và hệ thống cấu hình tập trung. Kiểm tra riêng từng nguồn vẫn có thể bỏ sót giá trị ghi đè nguy hiểm.

Ví dụ:

```text
File nền:
  access.requireAuthentication = true

Nguồn ghi đè:
  access.requireAuthentication = false

Kết quả thực sự mà ứng dụng sử dụng:
  access.requireAuthentication = false
```

Quy trình cần đặc tả rõ:

1. Những nguồn nào được phép cung cấp từng nhóm trường.
2. Thứ tự ưu tiên và quy tắc thay thế object, list, giá trị rỗng.
3. Giá trị mặc định nào được phép áp dụng, trong môi trường nào.
4. Cách phân biệt thiếu trường với chủ ý xóa giá trị.
5. Cách lưu nguồn gốc của giá trị hiệu lực để điều tra.
6. Điểm validation cuối cùng trước khi cấu hình được sử dụng.

Một giá trị mặc định chỉ nên được dùng khi hợp đồng cho phép thiếu trường. Giá trị đã được cung cấp nhưng sai không được âm thầm thay bằng mặc định. Với trường bắt buộc như tham chiếu khóa của production, thiếu giá trị phải dẫn đến kết quả từ chối hoặc chưa sẵn sàng theo chính sách đã định.

Có thể lưu nguồn gốc theo dạng `field -> source-id`, nhưng không vì thế ghi lại toàn bộ giá trị nhạy cảm. Quyền cung cấp cấu hình cũng phải được giới hạn: nếu một nguồn không được phép quyết định issuer thì giá trị issuer từ nguồn đó phải bị từ chối, thay vì chỉ dựa vào thứ tự ưu tiên.

Các lớp kiểm tra nên dùng cùng quy tắc chuẩn hóa và cùng biểu diễn mà runtime sử dụng. Tránh việc CI kiểm tra chuỗi trước khi thay biến, trong khi ứng dụng chạy một giá trị khác sau khi thay biến hoặc đọc nguồn bổ sung.

## 7. Ví dụ Java: kiểm tra ngữ nghĩa trên cấu hình đã có kiểu

Ví dụ dùng Java 17 trở lên và thư viện chuẩn. Đoạn mã minh họa một phần validation, sau khi parser đã kiểm tra cú pháp, khóa trùng, trường lạ và binder đã chuyển dữ liệu thành kiểu rõ ràng.

`Rules` đến từ chính sách đáng tin cậy của môi trường triển khai, không do ứng viên cấu hình tự cấp. Các giá trị `Duration` được binder tạo từ số giây theo hợp đồng.

```java
import java.net.URI;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public final class SecurityConfigValidator {
    public record Candidate(
            Boolean requireAuthentication,
            String defaultDecision,
            URI issuer,
            String audience,
            Duration maxLifetime,
            Duration idleTimeout,
            Boolean auditEnabled) {
    }

    public record Rules(
            Set<URI> allowedIssuers,
            Set<String> allowedAudiences,
            Duration maximumLifetime) {
        public Rules {
            allowedIssuers = Set.copyOf(allowedIssuers);
            allowedAudiences = Set.copyOf(allowedAudiences);
            if (maximumLifetime == null
                    || maximumLifetime.isZero()
                    || maximumLifetime.isNegative()) {
                throw new IllegalArgumentException("INVALID_LIFETIME_POLICY");
            }
        }
    }

    public record Violation(String field, String code) {
    }

    public static List<Violation> validate(Candidate candidate, Rules rules) {
        Objects.requireNonNull(rules, "rules");
        if (candidate == null) {
            return List.of(new Violation("$", "CONFIG_REQUIRED"));
        }

        List<Violation> errors = new ArrayList<>();

        if (!Boolean.TRUE.equals(candidate.requireAuthentication())) {
            errors.add(new Violation(
                    "access.requireAuthentication", "AUTH_REQUIRED"));
        }

        if (!"deny".equals(candidate.defaultDecision())) {
            errors.add(new Violation(
                    "access.defaultDecision", "DEFAULT_DENY_REQUIRED"));
        }

        URI issuer = candidate.issuer();
        boolean approvedIssuer = issuer != null
                && issuer.isAbsolute()
                && "https".equalsIgnoreCase(issuer.getScheme())
                && issuer.getHost() != null
                && issuer.getUserInfo() == null
                && issuer.getQuery() == null
                && issuer.getFragment() == null
                && rules.allowedIssuers().contains(issuer);

        if (!approvedIssuer) {
            errors.add(new Violation(
                    "identity.issuer", "ISSUER_NOT_APPROVED"));
        }

        if (candidate.audience() == null
                || !rules.allowedAudiences().contains(candidate.audience())) {
            errors.add(new Violation(
                    "identity.audience", "AUDIENCE_NOT_APPROVED"));
        }

        boolean validMax = isPositive(candidate.maxLifetime());
        if (!validMax
                || candidate.maxLifetime().compareTo(
                        rules.maximumLifetime()) > 0) {
            errors.add(new Violation(
                    "session.maxLifetimeSeconds", "SESSION_MAX_OUT_OF_RANGE"));
        }

        boolean validIdle = isPositive(candidate.idleTimeout());
        if (!validIdle) {
            errors.add(new Violation(
                    "session.idleTimeoutSeconds", "SESSION_IDLE_OUT_OF_RANGE"));
        } else if (validMax
                && candidate.idleTimeout().compareTo(
                        candidate.maxLifetime()) > 0) {
            errors.add(new Violation(
                    "session.idleTimeoutSeconds", "SESSION_IDLE_EXCEEDS_MAX"));
        }

        if (!Boolean.TRUE.equals(candidate.auditEnabled())) {
            errors.add(new Violation(
                    "audit.enabled", "AUDIT_REQUIRED"));
        }

        return List.copyOf(errors);
    }

    private static boolean isPositive(Duration value) {
        return value != null && !value.isZero() && !value.isNegative();
    }
}
```

Với ví dụ production, bên khởi tạo chính sách cung cấp issuer `https://id.example.com/realms/orders`, audience `orders-api` và `Duration.ofSeconds(900)`.

Một số điểm thiết kế cần giữ:

- Kiểm tra issuer kết hợp cấu trúc URI và tập giá trị được phê duyệt. Chỉ kiểm tra bắt đầu bằng `https://` hoặc có chứa tên miền là không đủ.
- Cách biểu diễn và so sánh issuer phải được thống nhất với thành phần xác thực. Không tùy tiện bỏ path, port hoặc dấu gạch chéo để “chuẩn hóa” thành một định danh khác.
- Lỗi chỉ trả về tên trường và mã lỗi do chương trình định nghĩa; không ghép nguyên giá trị đầu vào vào thông báo.
- Dùng `Duration` để làm rõ đại lượng thời gian; binder vẫn phải từ chối số không biểu diễn được, sai đơn vị hoặc sai kiểu.
- `List.copyOf` và các trường bất biến giúp giữ kết quả kiểm tra ổn định sau khi trả về.

Đây chưa phải toàn bộ validator của cấu hình YAML ở phần trước. Đoạn mã chưa thực hiện kiểm tra quyền nguồn cấu hình, `adminPublic`, phiên bản schema, đích audit, tham chiếu khóa hoặc trạng thái phụ thuộc. Các yêu cầu đó phải được triển khai trong pipeline tương ứng, không được coi là đã đáp ứng chỉ vì hàm trên trả về danh sách rỗng.

## 8. Pipeline kiểm tra và kích hoạt

Một quy trình tham khảo:

```text
Nguồn được phép + giới hạn tài liệu
  -> phân tích nghiêm ngặt từng nguồn
  -> kết hợp theo quy tắc ưu tiên đã công bố
  -> tạo cấu hình hiệu lực và thông tin nguồn gốc
  -> kiểm tra schema và chuyển sang kiểu rõ ràng
  -> kiểm tra ngữ nghĩa và chính sách theo ngữ cảnh
  -> kiểm tra tham chiếu, phiên bản và điều kiện vận hành
  -> tạo snapshot bất biến
  -> kích hoạt toàn bộ snapshot nếu điều kiện phiên bản còn đúng
  -> ghi nhận kết quả và phiên bản đang hoạt động
```

### 8.1. Không đọc lại nguồn có thể đổi sau validation

Nếu validator kiểm tra file A rồi runtime mở lại đường dẫn đó, nội dung có thể đã thay đổi giữa hai lần đọc. Cần kích hoạt đúng dữ liệu đã kiểm tra, hoặc dùng cơ chế phiên bản bất biến có bảo đảm tương đương.

Tương tự, tham chiếu khóa mang nghĩa “latest” có thể trỏ tới một phiên bản khác lúc sử dụng. Khi kiến trúc cần tính nhất quán, hãy phân giải tới phiên bản cụ thể và ràng buộc snapshot với phiên bản đó. Trạng thái thu hồi vẫn phải được kiểm soát theo chính sách hiện hành.

### 8.2. Cập nhật cạnh tranh

Hai ứng viên có thể cùng được kiểm tra dựa trên thế hệ 41. Sau khi ứng viên thứ nhất kích hoạt thế hệ 42, ứng viên còn lại không được tự động ghi đè bằng kết quả kiểm tra dựa trên trạng thái cũ.

Có thể dùng kiểm tra phiên bản có điều kiện khi commit. Nếu phiên bản cấu hình nền hoặc phiên bản chính sách đã đổi, cần đánh giá lại theo quy trình. Một `AtomicReference` có thể hỗ trợ thay snapshot trong một tiến trình Java, nhưng không tự giải quyết đồng bộ nhiều tiến trình, nhiều instance hoặc một hệ thống phân tán.

Mỗi yêu cầu nên lấy một snapshot nhất quán theo ranh giới xử lý đã định. Nếu liên tục đọc cấu hình mới ở từng bước, cùng một yêu cầu có thể xác thực bằng phiên bản cũ nhưng phân quyền bằng phiên bản mới. Với thay đổi thu hồi khẩn cấp, đặc tả riêng điểm kiểm tra và thời hạn áp dụng cần thiết.

### 8.3. Phiên bản và khả năng truy vết

Cần phân biệt:

- `schemaVersion`: cấu trúc dữ liệu mà phần mềm hiểu.
- Thế hệ cấu hình: thứ tự hoặc định danh của một bản cấu hình.
- Phiên bản chính sách: tập quy tắc được dùng để đánh giá.
- Phiên bản tài nguyên tham chiếu: khóa, chứng thư hoặc cấu hình phụ thuộc đã được ràng buộc.

Có thể ghi dấu vân tay trên biểu diễn chuẩn hóa của **phần cấu hình được phép công khai** để đối chiếu bản đã kiểm tra với bản hoạt động. Không băm toàn bộ bí mật rồi coi kết quả đó là dữ liệu công khai; bí mật có không gian giá trị nhỏ vẫn có thể bị đoán. Các định danh tài nguyên nhạy cảm cũng cần được hạn chế ghi log theo chính sách.

Chữ ký hoặc checksum có thể hỗ trợ xác minh nguồn gốc và tính toàn vẹn trong thiết kế phù hợp. Chúng không chứng minh cấu hình thỏa chính sách, cũng không tự ngăn việc phát lại một bản cũ không còn an toàn.

## 9. Xử lý lỗi khi khởi động và khi thay đổi

### 9.1. Lần khởi động đầu tiên

Nếu chưa có cấu hình hợp lệ:

- Không công bố sẵn sàng cung cấp các chức năng được bảo vệ.
- Không tự bật chế độ cho phép truy cập để ứng dụng “chạy được”.
- Trả kết quả lỗi có cấu trúc qua kênh vận hành được phép.
- Chỉ cho phép kiểm tra chẩn đoán tối thiểu theo chính sách truy cập riêng.

Một dịch vụ có thể dừng tiến trình hoặc giữ tiến trình sống để chờ điều kiện phụ thuộc, tùy thiết kế. Cả hai cách đều cần bảo đảm không phục vụ chức năng mà yêu cầu bảo mật chưa được đáp ứng. Trạng thái sống của tiến trình và trạng thái sẵn sàng phục vụ cần được phân biệt.

### 9.2. Ứng viên mới không hợp lệ

Khi đang chạy với một bản hợp lệ, ứng viên sai phải bị từ chối trước kích hoạt. Giữ bản đang chạy chỉ phù hợp khi bản đó vẫn thỏa chính sách hiện tại và các tài nguyên liên quan chưa hết hiệu lực hoặc bị thu hồi.

Không có quy tắc an toàn chung rằng “cứ giữ bản tốt gần nhất”. Nếu khóa của bản đó đã bị thu hồi, hệ thống phải áp dụng hành vi hạn chế hoặc dừng chức năng được bảo vệ theo yêu cầu đã đặc tả.

### 9.3. Phụ thuộc tạm thời không sẵn sàng

Ví dụ đích audit không truy cập được. Hợp đồng phải lựa chọn rõ liệu:

- Có bộ đệm bền vững đã được phê duyệt và còn đủ dung lượng để đáp ứng nghĩa vụ audit.
- Hay cần từ chối thao tác bắt buộc phải có audit khi không thể bảo đảm ghi nhận.

Không tự động bỏ qua audit. Nếu cho phép dùng bộ đệm, cần đặc tả giới hạn, quyền truy cập, bảo vệ nội dung, hành vi khi đầy và điều kiện chuyển dữ liệu tới đích. Kiểm tra một kết nối thành công lúc khởi động không thay thế các yêu cầu này.

### 9.4. Rollback

Rollback là một lần đề xuất cấu hình mới theo hướng dùng lại nội dung cũ. Nó cần đi qua validation với chính sách hiện tại, quyền thực hiện phù hợp và bằng chứng truy vết.

Cơ chế chống phát lại bản cũ cần cho phép quy trình rollback được ủy quyền theo thiết kế. Không nên dùng một quy tắc số phiên bản đơn giản rồi buộc người vận hành vô hiệu hóa validator để phục hồi. Bản từng hoạt động tốt vẫn phải bị từ chối nếu chứa khóa đã thu hồi hoặc giá trị không còn được phép.

## 10. Thiết kế kiểm thử từ yêu cầu

Kiểm thử phải chứng minh cả cấu hình hợp lệ được chấp nhận và cấu hình vi phạm không thể trở thành trạng thái hoạt động.

| Nhóm kiểm tra | Dữ liệu hoặc tình huống | Kết quả mong đợi |
| --- | --- | --- |
| Đường đi hợp lệ | Cấu hình mẫu, tham chiếu và điều kiện phụ thuộc hợp lệ | Tạo và kích hoạt được snapshot; có định danh bản hoạt động |
| Biên thời gian | `max=900, idle=900` | Vượt qua quy tắc thời gian của hợp đồng minh họa |
| Vượt biên | `max=901`, hoặc `idle=301, max=300` | Từ chối với mã lỗi tương ứng |
| Thiếu và sai kiểu | Thiếu trường bắt buộc; boolean là chuỗi | Từ chối trước sử dụng; không âm thầm áp giá trị khác |
| Khóa lạ | Viết nhầm `requireAuthenticaton` | Từ chối khóa không được hỗ trợ |
| Khóa trùng | Một nguồn có hai khóa `audit.enabled` khác nhau | Parser từ chối trước bước kết hợp nguồn |
| Nguồn ghi đè | File nền bật xác thực; biến môi trường tắt xác thực | Cấu hình hiệu lực bị từ chối |
| Giả mạo môi trường | Ứng viên tự khai development trên triển khai production | Không hạ chính sách; từ chối bất tương thích |
| Issuer không được phép | Đổi host, path hoặc issuer của môi trường khác | Từ chối dù vẫn là URL HTTPS hợp lệ |
| Tham chiếu không hợp lệ | Khóa thuộc dịch vụ khác, đã hết hạn hoặc bị thu hồi | Không kích hoạt ứng viên |
| Lỗi phụ thuộc | Kho khóa hoặc đích audit không khả dụng | Áp dụng đúng trạng thái chưa sẵn sàng hoặc hạn chế đã đặc tả |
| Cập nhật cạnh tranh | Hai bản cùng dựa trên một thế hệ | Không ghi đè ngoài điều kiện phiên bản; không trộn snapshot |
| Nội dung đổi sau kiểm tra | Nguồn bị thay trước khi runtime đọc | Runtime chỉ dùng snapshot đã kiểm tra hoặc từ chối thay đổi |
| Rollback không còn hợp lệ | Bản cũ dùng khóa đã thu hồi | Từ chối rollback |
| Giới hạn tài liệu | Vượt kích thước, độ sâu hoặc giới hạn parser đã công bố | Từ chối có kiểm soát, không làm cạn tài nguyên xử lý |
| Không lộ bí mật | Đầu vào có giá trị nhạy cảm và cố ý gây lỗi | Log, thông báo và metric không chứa giá trị đó |

Với mỗi phép thử âm, cần quan sát cả phiên bản đang hoạt động và hành vi truy cập. Chỉ xác nhận có thông báo lỗi chưa chứng minh cấu hình xấu không được dùng.

Các tầng kiểm thử có thể bao gồm:

- Kiểm thử quy tắc thuần để kiểm tra miền giá trị và quan hệ giữa trường.
- Kiểm thử parser và binding để phát hiện khác biệt biểu diễn.
- Kiểm thử tích hợp để kiểm tra tham chiếu, trạng thái sẵn sàng và quá trình kích hoạt.
- Kiểm thử qua API để xác nhận xác thực, phân quyền và quản lý phiên thực sự thực thi hợp đồng.
- Kiểm thử vận hành cho rollback, thu hồi, phụ thuộc gián đoạn và phát hiện bản cấu hình không khớp.

Không cần lặp toàn bộ quy tắc ở mọi tầng. Mỗi tầng nên chứng minh một ranh giới mà các tầng khác chưa chứng minh được.

## 11. Liên kết với kiến trúc và vòng đời phát triển

Ví dụ chuỗi truy vết:

| Rủi ro | Yêu cầu | Điểm cưỡng chế trong kiến trúc | Bằng chứng |
| --- | --- | --- | --- |
| R-01: bỏ xác thực do nguồn ghi đè | SEC-CFG-03 | Validator cấu hình hiệu lực và lớp xác thực | Test ghi đè bị từ chối; API được bảo vệ từ chối yêu cầu chưa xác thực |
| R-02: chấp nhận miền định danh ngoài dự kiến | SEC-CFG-05 | Chính sách issuer theo môi trường và bộ kiểm tra token | Test cấu hình issuer lạ; test token có issuer không được phép |
| R-03: không còn dấu vết thao tác đặc quyền | SEC-CFG-06 | Kiểm tra tuyến audit và chính sách xử lý khi mất đích | Test điều kiện sẵn sàng, bộ đệm và hành vi khi không bảo đảm audit |
| R-04: trạng thái bảo mật không nhất quán khi reload | SEC-CFG-07 | Snapshot bất biến và cơ chế kích hoạt có điều kiện | Test cập nhật cạnh tranh, kiểm tra phiên bản dùng trong một yêu cầu |

Trong thiết kế, đội ngũ thống nhất các bất biến và nguồn tin cậy. Khi triển khai, họ hiện thực schema, validator, nguồn tham chiếu và cơ chế kích hoạt. CI kiểm tra trước các ứng viên có thể xác minh, còn cổng triển khai đánh giá các ràng buộc gắn với môi trường thực.

Runtime vẫn phải kiểm tra đúng đầu vào thực tế mà nó nhận, vì các giá trị có thể được cung cấp hoặc ghi đè sau CI. Bằng chứng phát hành cần liên kết bản ứng dụng, bản cấu hình và bản chính sách phù hợp với mức truy vết của tổ chức.

Khi bổ sung hoặc bỏ một trường bảo mật, cần xem xét tương thích giữa phiên bản ứng dụng và schema. Có thể cần một giai đoạn triển khai chuyển tiếp được đặc tả rõ. Âm thầm bỏ qua trường mới trên instance cũ có thể khiến cùng một lần phát hành tạo ra hai cách thực thi bảo mật khác nhau.

Theo dõi cấu hình thay đổi ngoài quy trình giúp phát hiện drift. Validation kiểm tra tính chấp nhận được của ứng viên; kiểm soát quyền thay đổi, cơ chế phân phối và phát hiện drift bổ sung cho nó trong vận hành.

## 12. Lỗi thường gặp và cách hoàn thiện đặc tả

| Lỗi trong đặc tả hoặc triển khai | Cách hoàn thiện |
| --- | --- |
| Chỉ nói “file phải đúng YAML” | Bổ sung schema, ngữ nghĩa, ngữ cảnh, tham chiếu và hành vi kích hoạt |
| Kiểm tra từng file nhưng không kiểm tra sau merge | Đặt validation bắt buộc trên cấu hình hiệu lực |
| Tự sửa giá trị nguy hiểm về mặc định | Từ chối giá trị đã cung cấp nhưng sai; chỉ dùng mặc định theo hợp đồng |
| Để ứng viên tự quyết định môi trường và danh sách phê duyệt | Tách nguồn ngữ cảnh và chính sách đáng tin cậy khỏi quyền sửa ứng viên |
| Tin rằng kiểm tra CI là đủ | Kiểm tra đầu vào thực tế tại ranh giới triển khai và sử dụng |
| Log toàn bộ cấu hình khi có lỗi | Dùng mã lỗi, đường dẫn trường và metadata được phép công khai |
| Từ chối reload nhưng vẫn cập nhật vài thành phần | Kích hoạt snapshot theo đơn vị đã đặc tả, không sửa dần trạng thái dùng chung |
| Cho rằng bản từng hợp lệ luôn có thể rollback | Kiểm tra lại chính sách, hiệu lực và thu hồi hiện tại |
| Dùng hash hoặc chữ ký thay cho kiểm tra chính sách | Kiểm tra riêng nguồn gốc, tính toàn vẹn, tính mới và tính chấp nhận được |
| Coi validator là đủ để chống mọi chủ thể có quyền quản trị | Bảo vệ cả đường thay đổi chính sách, validator và cơ chế cưỡng chế |

Một đặc tả đủ dùng phải cho phép người triển khai xây dựng validator, người kiểm thử xác định kết quả kỳ vọng và người vận hành biết cách xử lý thất bại. Khi rủi ro được liên kết với bất biến, điểm cưỡng chế và bằng chứng, configuration validation trở thành một phần kiểm chứng được của thiết kế bảo mật.
