# Attribute freshness

## 1. Độ mới của thuộc tính là gì?

**Attribute freshness** là mức độ mà một giá trị thuộc tính còn đủ mới để được sử dụng cho **một quyết định cụ thể**. Câu hỏi không chỉ là “giá trị này có chữ ký hợp lệ không?” mà còn là:

> Nguồn có thẩm quyền đã xác nhận giá trị này vào lúc nào, nó có thể đã thay đổi từ đó đến nay không, và quyết định hiện tại chấp nhận độ trễ bao nhiêu?

Trong IAM, những thuộc tính như trạng thái tài khoản, membership tenant, vai trò, nhóm, thiết bị tuân thủ hay quyền đặc biệt có thể thay đổi trong khi phiên đăng nhập vẫn tồn tại.

Ví dụ:

~~~text
09:00: Alice có quyền EXPORT_CUSTOMER_DATA.
09:05: Quản trị viên thu hồi quyền.
09:06: Alice gọi API xuất dữ liệu bằng một credential còn hạn.
~~~

Nếu API chỉ kiểm tra credential chưa hết hạn rồi dùng quyền từ snapshot lúc 09:00, quyết định có thể dựa trên dữ liệu cũ.

Độ mới là một điều kiện đầu vào của phân quyền. Một thuộc tính đủ mới vẫn có thể dẫn đến `DENY`, chẳng hạn trạng thái tài khoản mới nhất là `DISABLED`. Ngược lại, một giá trị có nội dung cho phép nhưng đã quá cũ không nhất thiết còn được dùng để cho phép.

Trong nền tảng IAM, chủ đề này liên quan trực tiếp đến vòng đời quyền, MFA, phiên, SSO, OAuth/OIDC, cấp phát tài khoản, workload identity và kiểm toán. Người học cần biết dữ liệu quyền đi qua những lớp nào và thời điểm nào thực sự quyết định việc thực thi.

Sau bài này, người học có thể:

- Phân biệt độ mới của thuộc tính, tuổi token và thời điểm xác thực.
- Xác định các mốc thời gian, nguồn có thẩm quyền và độ trễ liên quan.
- Thiết kế hợp đồng freshness cho từng thuộc tính và hành động.
- Tính thời hạn tái sử dụng mà không vô tình làm mới bằng chứng cũ.
- Phối hợp TTL, version, sự kiện thu hồi và kiểm tra tại thời điểm sử dụng.
- Kiểm thử tình huống dữ liệu cũ, mất kết nối và cập nhật đến sai thứ tự.

## 2. Đúng nguồn, toàn vẹn và đủ mới là các yêu cầu khác nhau

| Yêu cầu | Câu hỏi | Ví dụ lỗi |
| --- | --- | --- |
| Toàn vẹn | Giá trị có bị sửa trên đường truyền/lưu trữ không? | Client sửa `role` trong JSON |
| Nguồn có thẩm quyền | Nguồn này có quyền xác nhận thuộc tính không? | Hồ sơ tự sửa được dùng để quyết định vai trò |
| Đúng phạm vi | Giá trị áp dụng cho đúng subject, tenant và tài nguyên không? | Dùng role tenant A cho tenant B |
| Độ mới | Bằng chứng còn nằm trong mức tuổi được chấp nhận không? | Dùng membership đã bị thu hồi |
| Hiệu lực nghiệp vụ | Giá trị đã bắt đầu hoặc đã hết hiệu lực chưa? | Dùng quyền tạm thời sau thời điểm kết thúc |
| Tính nhất quán | Những thuộc tính được kết hợp có tạo thành trạng thái hợp lệ không? | Ghép role mới với trạng thái tài khoản cũ |

Chữ ký hợp lệ có thể bảo vệ một snapshot cũ nguyên vẹn. Đọc dữ liệu qua TLS có thể xác nhận đúng server nhưng server đó vẫn đang dùng bản sao chưa đồng bộ.

Vì vậy, cần xác minh đúng nguồn và đúng phạm vi trước khi tuổi dữ liệu có ý nghĩa. Không thể dùng một timestamp rất mới do client tự đặt để chứng minh quyền mới.

Đồng thời, “mới” không đồng nghĩa “đúng với thế giới thực”. Nếu dữ liệu nhân sự chưa được cập nhật sau khi nhân viên nghỉ việc, việc đọc cơ sở dữ liệu ngay bây giờ chỉ xác nhận trạng thái đang được lưu tại nguồn đó.

## 3. Những chiếc đồng hồ không được đánh đồng

### 3.1. Các mốc thời gian thường gặp

Tên trường dưới đây là cách đặt tên minh họa, không phải schema chung của một chuẩn:

| Mốc | Ý nghĩa |
| --- | --- |
| `effectiveAt` | Khi thay đổi có hiệu lực theo nghiệp vụ |
| `sourceUpdatedAt` | Khi nguồn ghi nhận việc thay đổi giá trị |
| `authorityCheckedAt` | Khi giá trị được xác nhận bằng một phép đọc/đánh giá có ý nghĩa tại nguồn có thẩm quyền |
| `fetchedAt` | Khi một thành phần lấy được bản biểu diễn |
| `cachedAt` | Khi bản biểu diễn được đưa vào cache |
| `tokenIssuedAt` | Khi token được cấp |
| `authenticatedAt` | Khi người dùng được xác thực theo cơ chế tương ứng |
| `decidedAt` | Khi policy đưa ra quyết định |
| `enforcedAt` | Khi hành động được thực thi |
| `validUntil` | Khi giá trị hoặc bằng chứng hết hiệu lực theo hợp đồng |

Các mốc này có thể gần nhau, nhưng không được tự thay thế cho nhau.

### 3.2. Cập nhật lần cuối không phải xác nhận lần cuối

Một thuộc tính `department = FINANCE` có thể không thay đổi trong nhiều năm. Nếu nguồn có thẩm quyền vừa được kiểm tra và vẫn xác nhận giá trị đó, dữ liệu có thể đủ mới cho quyết định.

Ngược lại, hồ sơ người dùng vừa đổi tên hiển thị không chứng minh role và membership trong hồ sơ đó vừa được kiểm tra lại từ nguồn gốc.

Cần phân biệt:

~~~text
lastChangedAt:
    Giá trị thay đổi lần cuối khi nào?

lastAuthoritativelyCheckedAt:
    Lần gần nhất có đủ bằng chứng rằng giá trị đang đúng
    theo hợp đồng nguồn là khi nào?
~~~

Không nên dùng tuổi từ `lastChangedAt` làm tiêu chí duy nhất để loại bỏ mọi thuộc tính lâu không đổi.

### 3.3. Fetch mới từ cache cũ không làm dữ liệu mới

~~~text
Nguồn gốc -> bản sao đồng bộ -> broker danh tính -> API -> cache quyền
~~~

Nếu API vừa nhận dữ liệu từ broker nhưng broker đang dùng bản sao cũ, `fetchedAt = now` chỉ mô tả thời điểm API nhận dữ liệu.

Không được thực hiện:

~~~text
Đọc bản cache cũ.
Gán lại checkedAt = now.
Coi giá trị đủ mới thêm một chu kỳ nữa.
~~~

Đó là việc kéo dài tuổi bằng chứng mà không có xác nhận mới. Nếu mọi lớp đều làm như vậy, dữ liệu có thể được giữ quá lâu mà từng cache riêng lẻ vẫn có vẻ “vừa cập nhật”.

## 4. Token, xác thực lại và freshness thuộc tính

### 4.1. `iat` và `exp` mô tả token

RFC 7519 định nghĩa `iat` là thời điểm JWT được cấp và `exp` là thời điểm hết hạn xử lý token. Hai claim này không định nghĩa thời điểm mọi thuộc tính bên trong được đọc lại từ nguồn gốc. [Nguồn: RFC 7519, mục 4.1.4 và 4.1.6](https://www.rfc-editor.org/rfc/rfc7519.html#section-4.1.4).

Một token vừa được cấp có thể chứa:

~~~text
tokenIssuedAt = 09:10
role = ADMIN, được lấy từ snapshot lúc 08:40
~~~

Tuổi token là một phút vào 09:11, nhưng bằng chứng về role đã có tuổi 31 phút nếu 08:40 là mốc xác nhận có ý nghĩa.

Token ngắn hạn có thể giới hạn khoảng tái sử dụng snapshot trong một thiết kế phù hợp. Nó không tự giải quyết độ trễ nguồn, quy trình cấp lại dùng dữ liệu cũ hoặc các cache nằm sau bước xác minh token.

### 4.2. `auth_time` không phải thời điểm mọi quyền được làm mới

Trong OpenID Connect, `max_age` giới hạn thời gian kể từ lần người dùng được xác thực tích cực; khi dùng tham số này, ID token trả về phải có `auth_time`. Đây là cơ chế về tuổi của việc xác thực. [Nguồn: OpenID Connect Core, mục 3.1.2.1](https://openid.net/specs/openid-connect-core-1_0.html#AuthRequest).

Một lần xác thực lại hoặc hoàn tất MFA giúp cung cấp bằng chứng về người đang hiện diện và mức bảo đảm tương ứng. Nó không tự chứng minh rằng quyền xuất dữ liệu chưa bị thu hồi, nếu policy vẫn đọc role từ snapshot cũ.

Nếu hành động cần cả xác thực gần đây và quyền mới, cần kiểm tra riêng hai điều kiện:

~~~text
authentication_age đủ nhỏ
AND authorization_attributes đủ mới
AND nội dung policy cho phép hành động
~~~

### 4.3. Refresh token không phải lệnh “refresh mọi thuộc tính”

Dùng refresh token có thể tạo access token mới theo hợp đồng của authorization server. Việc authorization server đọc lại nguồn quyền nào, sử dụng cache nào và áp dụng chính sách nào là đặc tính triển khai cần được biết.

Không được suy ra:

~~~text
access token mới -> membership mới nhất ở mọi hệ thống
~~~

Tương tự, gọi UserInfo hoặc một API hồ sơ ngay bây giờ chỉ cung cấp dữ liệu theo ngữ nghĩa và độ mới mà endpoint đó thực sự bảo đảm. Thời điểm nhận response không chứng minh mọi nguồn phía sau đã đồng bộ.

## 5. Định nghĩa freshness theo thuộc tính và hành động

### 5.1. Không có một TTL phù hợp cho mọi dữ liệu

Tên hiển thị, trạng thái tài khoản, quyền quản trị và tình trạng thiết bị có mức thay đổi và hậu quả khác nhau.

Một nhóm phát triển có thể thiết kế bảng như sau:

| Thuộc tính | Hành động | Yêu cầu trong ví dụ |
| --- | --- | --- |
| `displayName` | Hiển thị lời chào | Chấp nhận snapshot dài hơn |
| `membershipState` | Đọc tài liệu tenant | Có giới hạn tuổi và xử lý thu hồi |
| `exportPermission` | Xuất dữ liệu khách hàng | Giới hạn tuổi ngắn hơn, kiểm tra gần bước tạo kết quả |
| `deviceCompliance` | Truy cập dữ liệu nhạy cảm | Kiểm tra theo bằng chứng từ nguồn đánh giá thiết bị |
| `privilegedGrant` | Thao tác quản trị | Ràng buộc thời hạn grant và quy tắc kiểm tra hiện tại |

Bảng chỉ minh họa cách phân loại. Giá trị thời gian cụ thể phải xuất phát từ yêu cầu nghiệp vụ, độ trễ nguồn và bảo đảm hệ thống thực sự đạt được.

Đặt TTL rất ngắn cho một bản sao vốn chậm nhiều giờ không tạo ra dữ liệu gần thời gian thực.

### 5.2. Hợp đồng freshness cần trả lời đủ câu hỏi

Với từng thuộc tính dùng để cho phép, có thể ghi rõ:

~~~text
Tên thuộc tính và ý nghĩa:
    membershipState trong application tenant

Khóa phạm vi:
    tenantId + subjectId + membership generation

Nguồn có thẩm quyền:
    membership service

Phép xác nhận:
    đọc trạng thái theo hợp đồng nhất quán đã chọn

Tuổi tối đa được chấp nhận:
    theo hành động đang xét

Độ trễ phía nguồn và bất định thời gian:
    giới hạn đã biết, không phải ước lượng tùy ý

Thời hạn nghiệp vụ:
    validFrom, validUntil nếu có

Làm mới:
    lấy lại bằng chứng từ nguồn phù hợp

Khi không làm mới được:
    dừng, yêu cầu thử lại hoặc dùng ngoại lệ đã được định nghĩa

Thu hồi:
    sự kiện, version, kiểm tra hiện tại và độ trễ hiệu lực

Audit:
    nguồn, thời điểm xác nhận, version và thời hạn sử dụng
~~~

Một cờ `fresh=true` không đủ nếu không có phạm vi, chính sách và mốc thời gian để diễn giải.

### 5.3. Độ mới có thể là một kết quả trung gian

Một thành phần lấy dữ liệu thuộc tính có thể cung cấp bằng chứng cho bộ quyết định policy. Có thể phân biệt:

~~~text
FRESH:
    Đủ điều kiện thời gian theo rule đang dùng.

REFRESH_REQUIRED:
    Cần lấy bằng chứng mới trước khi xét cho phép.

INVALID / UNTRUSTED:
    Không thể dùng bằng chứng này theo hợp đồng.

DENY:
    Nội dung policy không cho phép hành động.
~~~

`FRESH` chưa phải `ALLOW`. Đổi `membershipState` từ `ACTIVE` sang `REVOKED` rồi đọc lại sẽ tạo ra dữ liệu mới nhưng phải làm hành động bị từ chối.

## 6. Tính thời hạn sử dụng mà không đặt lại tuổi bằng chứng

### 6.1. Một mô hình tính minh họa

Giả sử ứng dụng có:

- `t_check`: mốc xác nhận có ý nghĩa được truyền cùng bằng chứng.
- `B`: ngân sách tuổi tối đa cho thuộc tính ở hành động hiện tại.
- `L`: giới hạn độ trễ nguồn phía trước chưa được phản ánh trong `t_check`.
- `U`: bất định đồng hồ mà policy dự phòng theo hướng thận trọng.
- `t_business_end`: thời điểm hết hiệu lực nghiệp vụ của bằng chứng.

Có thể chọn:

~~~text
freshness_deadline = t_check + B - L - U

usable_until = min(
    freshness_deadline,
    t_business_end
)
~~~

Theo hợp đồng của ví dụ, bằng chứng chỉ được dùng khi:

~~~text
now < usable_until
~~~

Các điều kiện khác như đúng nguồn, đúng subject/tenant, chưa bị vô hiệu hóa và đã đến thời điểm bắt đầu hiệu lực vẫn cần được kiểm tra.

`L` phải dựa trên mô hình nguồn thực tế. Không trừ cùng một độ trễ hai lần nếu `t_check` đã mô tả mốc quan sát tại nguồn gốc. Ngược lại, không gán `L = 0` chỉ vì không biết độ trễ.

Nếu không có giới hạn đáng tin cậy cho độ trễ nguồn, không thể dùng công thức này để tuyên bố một giới hạn cứng về độ mới so với nguồn gốc hoặc thế giới thực.

### 6.2. Ví dụ số

Giả sử đây là các giá trị do hệ thống minh họa đã xác lập:

~~~text
t_check        = 09:00:00
B              = 120 giây
L              = 20 giây
U              = 5 giây
t_business_end = 09:10:00
~~~

Khi đó:

~~~text
freshness_deadline = 09:01:35
usable_until       = 09:01:35
~~~

Ở 09:01:34, điều kiện thời gian còn đạt. Tại đúng 09:01:35, nó không còn đạt theo quy tắc nửa mở đã chọn.

Nếu quyền tạm thời hết hiệu lực lúc 09:01:00, `usable_until` phải là 09:01:00 dù dữ liệu vẫn chưa vượt ngân sách tuổi.

Những con số này chỉ phục vụ bài toán minh họa, không phải khuyến nghị TTL cho mọi hệ thống IAM.

### 6.3. Không cộng “clock skew” tùy ý để kéo dài quyền

Sai lệch đồng hồ phải được xử lý theo hợp đồng thời gian. Không nên tự thêm một khoảng dung sai ở từng tầng rồi vô tình kéo dài thời hạn qua nhiều tầng.

Ví dụ của bài dự phòng `U` bằng cách rút ngắn thời hạn. Nó cũng từ chối timestamp xác nhận nằm trong tương lai so với đồng hồ kiểm tra. Hệ thống khác có thể có quy tắc riêng, nhưng phải biết quy tắc đó ảnh hưởng thế nào đến bảo đảm.

Một timestamp thay đổi giữa các máy không tự tạo ra thứ tự toàn cục cho các sự kiện. Version hoặc thứ tự stream cũng cần ngữ nghĩa riêng.

## 7. Cache nhiều tầng có thể cộng dồn độ trễ

Giả sử role ở nguồn bị thu hồi lúc 09:00:00:

~~~text
Broker giữ cache role cũ thêm gần 60 giây.
09:00:59: Broker cấp token mới từ cache cũ.
Token đó có thời hạn 5 phút.
API chỉ dùng role trong token đến lúc token hết hạn.
~~~

Nếu không có cơ chế chặn khác, snapshot quyền cũ có thể còn được chấp nhận gần đến 09:05:59. Việc token có thời hạn năm phút không đồng nghĩa thu hồi được áp dụng trong năm phút kể từ thay đổi ở nguồn.

Với một chuỗi xử lý nối tiếp, giới hạn trễ có thể cần tính đến:

~~~text
Độ trễ phát hiện thay đổi tại nguồn
+ độ trễ đồng bộ
+ thời gian còn tái sử dụng snapshot ở tầng cấp credential
+ thời gian tái sử dụng tại tầng nhận
+ độ trễ thực thi hoặc vô hiệu hóa
+ phần bất định liên quan
~~~

Không phải mọi kiến trúc đều cộng các số theo cách này. Một kiểm tra chặn độc lập có thể rút ngắn cửa sổ; nhiều nhánh khác nhau có thể có đường chậm khác nhau. Cần phân tích đúng đường thực thi của hành động, không chỉ đọc TTL ở một lớp.

Một nguyên tắc hữu ích là truyền mốc xác nhận hoặc deadline của bằng chứng thay vì chỉ truyền thời điểm copy:

~~~text
Cache A xác nhận bằng chứng dùng được đến 09:01:35.
Cache B nhận lúc 09:01:20.
Cache B chỉ còn tối đa 15 giây theo deadline đó,
không được bắt đầu lại một TTL 120 giây.
~~~

Nếu một lớp thật sự xác nhận lại với nguồn theo hợp đồng, nó có thể tạo bằng chứng mới. Việc chỉ nạp lại cùng một snapshot không đáp ứng điều kiện đó.

## 8. Ví dụ Java: đánh giá độ mới của một bằng chứng

### 8.1. Phạm vi của ví dụ

Đoạn mã Java 17 sau đánh giá điều kiện thời gian cho một thuộc tính, chẳng hạn `membershipState`. Nó áp dụng mô hình ngân sách ở phần trước.

Dữ liệu đầu vào phải được tạo bởi adapter server sau khi nguồn, kênh truyền và nội dung bằng chứng đã được xác minh. So sánh một chuỗi `sourceId` không tự xác thực nguồn; đó chỉ là kiểm tra nguồn đã xác minh có phù hợp rule đang dùng không.

`upstreamLagBound` là giới hạn mà adapter có cơ sở để xác nhận. Nếu không biết giới hạn này thì chưa có đủ bằng chứng cho mô hình, không tự điền số không.

~~~java
import java.time.DateTimeException;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

final class AttributeFreshness {
    enum Status {
        FRESH,
        INVALID_EVIDENCE,
        WRONG_SCOPE,
        UNTRUSTED_SOURCE,
        UPSTREAM_LAG_EXCEEDED,
        FUTURE_TIMESTAMP,
        NOT_YET_VALID,
        BUSINESS_EXPIRED,
        REFRESH_REQUIRED
    }

    record Scope(
        String subjectId,
        String tenantId,
        String attributeName
    ) {
        Scope {
            Objects.requireNonNull(subjectId);
            Objects.requireNonNull(tenantId);
            Objects.requireNonNull(attributeName);
        }
    }

    record Evidence(
        Scope scope,
        String value,
        String sourceId,
        Instant checkedAt,
        Instant validFrom,
        Instant validUntil,
        Duration upstreamLagBound
    ) {
        Evidence {
            Objects.requireNonNull(scope);
            Objects.requireNonNull(value);
            Objects.requireNonNull(sourceId);
            Objects.requireNonNull(checkedAt);
            Objects.requireNonNull(validFrom);
            Objects.requireNonNull(validUntil);
            Objects.requireNonNull(upstreamLagBound);
        }
    }

    record Rule(
        String trustedSourceId,
        Duration maxAge,
        Duration maxUpstreamLag,
        Duration clockUncertainty
    ) {
        Rule {
            Objects.requireNonNull(trustedSourceId);
            Objects.requireNonNull(maxAge);
            Objects.requireNonNull(maxUpstreamLag);
            Objects.requireNonNull(clockUncertainty);

            if (maxAge.isZero() || maxAge.isNegative()
                    || maxUpstreamLag.isNegative()
                    || clockUncertainty.isNegative()) {
                throw new IllegalArgumentException(
                    "Invalid freshness rule"
                );
            }
        }
    }

    record Assessment(Status status, Instant usableUntil) {}

    private static Assessment reject(Status status) {
        return new Assessment(status, null);
    }

    static Assessment assess(
        Evidence evidence,
        Scope expectedScope,
        Rule rule,
        Instant now
    ) {
        if (evidence == null || expectedScope == null
                || rule == null || now == null) {
            return reject(Status.INVALID_EVIDENCE);
        }

        if (!expectedScope.equals(evidence.scope())) {
            return reject(Status.WRONG_SCOPE);
        }

        if (!rule.trustedSourceId().equals(evidence.sourceId())) {
            return reject(Status.UNTRUSTED_SOURCE);
        }

        if (evidence.upstreamLagBound().isNegative()
                || !evidence.validUntil()
                    .isAfter(evidence.validFrom())) {
            return reject(Status.INVALID_EVIDENCE);
        }

        if (evidence.upstreamLagBound()
                .compareTo(rule.maxUpstreamLag()) > 0) {
            return reject(Status.UPSTREAM_LAG_EXCEEDED);
        }

        if (evidence.checkedAt().isAfter(now)) {
            return reject(Status.FUTURE_TIMESTAMP);
        }

        if (now.isBefore(evidence.validFrom())) {
            return reject(Status.NOT_YET_VALID);
        }

        if (!now.isBefore(evidence.validUntil())) {
            return reject(Status.BUSINESS_EXPIRED);
        }

        try {
            Instant deadline = evidence.checkedAt()
                .plus(rule.maxAge())
                .minus(evidence.upstreamLagBound())
                .minus(rule.clockUncertainty());

            if (evidence.validUntil().isBefore(deadline)) {
                deadline = evidence.validUntil();
            }

            if (!now.isBefore(deadline)) {
                return reject(Status.REFRESH_REQUIRED);
            }

            return new Assessment(Status.FRESH, deadline);
        } catch (DateTimeException | ArithmeticException ex) {
            return reject(Status.INVALID_EVIDENCE);
        }
    }
}
~~~

### 8.2. Cách sử dụng kết quả

Một luồng xét quyền có thể là:

~~~text
assessment = assess(evidence, expectedScope, rule, serverNow)

Nếu assessment không phải FRESH:
    làm mới theo hợp đồng hoặc dừng hành động.

Nếu assessment là FRESH:
    tiếp tục kiểm tra nội dung thuộc tính và policy.

Ví dụ:
    membershipState phải là ACTIVE;
    permission phải bao gồm hành động;
    tenant và tài nguyên phải phù hợp.
~~~

`value = REVOKED` có thể có assessment `FRESH`. Đây là bằng chứng mới cho một kết quả từ chối.

Không nhận `now` từ request của client. Trong ứng dụng thật, thời gian nên đến từ đồng hồ server được truyền vào thành phần đánh giá; có thể dùng `Clock` để kiểm thử các ranh giới mà không cần chờ thời gian thực.

Các constructor chỉ kiểm tra một phần cấu trúc tối thiểu. Adapter còn cần kiểm tra schema, ý nghĩa thuộc tính, định danh và cơ chế bảo vệ dữ liệu theo hợp đồng thật.

### 8.3. Những bảo đảm không nằm trong hàm

Hàm chưa xác minh token, không đọc lại nguồn, không kiểm tra version hiện tại và không khóa một membership khỏi thay đổi đồng thời. Nó chỉ đánh giá bằng chứng theo rule và thời gian đã truyền vào.

Ngay cả khi assessment vừa trả `FRESH`, membership vẫn có thể bị thu hồi sau đó. Nhu cầu chặn thao tác đang chạy phải được giải quyết ở cơ chế thực thi, không thể suy ra từ phép tính timestamp.

Ví dụ không biểu diễn yêu cầu “không cho phép bất kỳ độ trễ nào” bằng `maxAge = 0`. Một yêu cầu nhất quán mạnh cần mô tả điểm kiểm tra, nguồn đọc và thứ tự với lệnh thu hồi; đặt TTL bằng không không tự tạo ra bảo đảm đó.

## 9. Các cách lấy thuộc tính và giới hạn của chúng

### 9.1. Snapshot trong credential

Ưu điểm là giảm số lần gọi nguồn và hỗ trợ xác minh cục bộ. Đổi lại, snapshot có thể tiếp tục tồn tại sau khi dữ liệu gốc thay đổi.

Phù hợp hay không phụ thuộc tuổi được chấp nhận, cơ chế thu hồi và hành động. Nếu dùng snapshot, cần biết mốc xác nhận có ý nghĩa hoặc bảo đảm nguồn khi snapshot được tạo; không tự dùng `iat` thay thế.

### 9.2. Đọc theo yêu cầu

API hoặc bộ cung cấp thuộc tính có thể đọc trạng thái từ nguồn trước quyết định. Cách này giảm phụ thuộc vào snapshot lâu sống, nhưng còn phụ thuộc:

- Nguồn đọc là authority hay replica.
- Mức nhất quán và độ trễ của nguồn.
- Cache trong client, broker hoặc dịch vụ nguồn.
- Hành vi khi nguồn không truy cập được.

Một lệnh gọi qua mạng ở mỗi request không có nghĩa mỗi request đọc được trạng thái mới nhất đã commit tại nguồn gốc.

### 9.3. OAuth introspection

OAuth introspection cho resource server hỏi authorization server về trạng thái `active` và metadata của token. RFC 7662 cho phép cache nhưng nêu rõ đánh đổi về độ mới; response có `exp` không được cache vượt mốc đó. [Nguồn: RFC 7662, mục 2.2 và 4](https://www.rfc-editor.org/rfc/rfc7662.html#section-4).

`active = true` không tự nói rằng mọi role vừa được truy vấn lại từ nguồn nhân sự. Phải biết server tính trạng thái và metadata bằng nguồn nào. Nếu nó chỉ xác minh token rồi trả claim gốc, việc gọi endpoint không tự làm mới claim đó.

### 9.4. Đồng bộ hoặc nhận sự kiện thay đổi

Ứng dụng có thể duy trì bản sao thuộc tính bằng đồng bộ định kỳ hoặc sự kiện. Cách này hỗ trợ giảm độ trễ mà không đọc authority cho mọi request.

Nhưng cần biết dữ liệu đã được đồng bộ đến đâu, sự kiện có bị mất không, và bản sao có bị phân kỳ không. Đồng bộ là một đường truyền dữ liệu có trạng thái, không phải lời bảo đảm mặc định rằng mọi replica luôn mới.

Có thể kết hợp snapshot có tuổi giới hạn, sự kiện vô hiệu hóa nhanh và đối soát để phát hiện sự kiện bị bỏ sót.

## 10. Metadata SCIM không phải xác nhận mới cho từng thuộc tính

SCIM định nghĩa `meta.lastModified` là thời điểm gần nhất chi tiết resource được cập nhật tại service provider. `meta.version` liên quan đến entity-tag và cơ chế versioning của resource. [Nguồn: RFC 7643, mục 3.1](https://www.rfc-editor.org/rfc/rfc7643.html#section-3.1).

Điều đó không tự biến `meta.lastModified` thành thời điểm nguồn nhân sự vừa xác nhận mọi thuộc tính. Một thay đổi trên hồ sơ có thể không liên quan đến role hoặc membership đang xét.

Không nên coi một entity-tag bất kỳ là số nguyên tăng dần. Nếu thiết kế cần thứ tự sự kiện hoặc authorization epoch, cần trường có hợp đồng phù hợp; không so sánh từ điển hai ETag để đoán bản nào mới hơn.

Ví dụ về dữ liệu nội bộ do ứng dụng tự định nghĩa:

~~~text
value = ACTIVE
sourceResourceVersion = một định danh phiên bản opaque
authorityCheckedAt = mốc xác nhận theo hợp đồng adapter
localReceivedAt = mốc ứng dụng nhận dữ liệu
~~~

Các trường bổ sung phải có nguồn gốc rõ ràng. Không tự gán `authorityCheckedAt = localReceivedAt` nếu adapter chỉ nhận một bản sao không biết độ trễ.

## 11. Sự kiện thu hồi, version và thứ tự cập nhật

### 11.1. Sự kiện giúp rút ngắn cửa sổ, nhưng vẫn cần xử lý lỗi

Giả sử:

~~~text
membership(Alice, T-A), version 41: ACTIVE
membership(Alice, T-A), version 42: REVOKED
~~~

Khi sự kiện version 42 tới, ứng dụng có thể cập nhật bản sao, vô hiệu hóa cache và ngừng chấp nhận snapshot cũ theo policy.

Version phải có phạm vi và thứ tự được định nghĩa. Một số tăng dần theo membership không nhất thiết so sánh được với số của membership khác hoặc nguồn khác.

### 11.2. Sự kiện đến sai thứ tự không được khôi phục quyền cũ

~~~text
Nhận version 42: REVOKED.
Sau đó nhận lại version 41: ACTIVE.
~~~

Nếu xử lý theo “response tới sau thắng”, trạng thái cũ có thể ghi đè trạng thái thu hồi.

Một thiết kế có version tăng dần có thể cập nhật có điều kiện:

~~~text
Chỉ áp dụng sự kiện nếu version mới hơn
version đã chấp nhận cho đúng subject + tenant + generation.
~~~

Nếu xảy ra khoảng trống version hoặc nguồn không bảo đảm chuỗi đầy đủ, consumer cần hành vi phù hợp như lấy snapshot hiện tại hoặc đối soát. Không suy ra rằng thiếu sự kiện nghĩa là không có thay đổi.

### 11.3. Xóa và tạo lại cần tránh hồi sinh bằng chứng cũ

Nếu membership được xóa rồi tạo mới với version quay về `1`, credential của membership trước có thể bị hiểu sai.

Có thể cần định danh thế hệ membership, authorization epoch hoặc cơ chế không tái sử dụng định danh/phiên bản theo cách gây nhập nhằng.

Một dấu thu hồi hoặc watermark phải sống đủ lâu để chặn các snapshot cũ mà hệ thống vẫn có thể chấp nhận. Xóa dấu thu hồi quá sớm có thể làm credential chưa hết hạn hoạt động lại nếu đường kiểm tra mặc định cho phép.

### 11.4. “Có số version” chưa đủ để biết hiện tại

Token có `membershipVersion = 41` chỉ giúp phát hiện cũ nếu bên nhận biết version hiện tại đáng tin cậy là bao nhiêu.

Nếu bên nhận đang cache version 41 trong khi authority đã ở 42, phép so sánh vẫn trả “khớp”. Cơ chế cấp và làm mới watermark/version phải có bảo đảm độ mới riêng.

Cần kiểm tra thứ tự ghi dữ liệu, phát sự kiện, consumer và cache. Nếu thay đổi đã commit nhưng sự kiện không được phát, chỉ có TTL hoặc đối soát không nhất thiết đáp ứng yêu cầu thu hồi nhanh.

## 12. Freshness của nhiều thuộc tính và quyết định được cache

### 12.1. Thời hạn quyết định phụ thuộc mọi bằng chứng cần thiết

Giả sử một quyết định xuất dữ liệu cần:

~~~text
membershipState dùng được đến 09:01:35
exportPermission dùng được đến 09:01:10
deviceCompliance dùng được đến 09:00:50
credential dùng được đến 09:05:00
~~~

Nếu không có xác nhận mới, quyết định `ALLOW` không được tái sử dụng vượt 09:00:50.

Có thể mô hình hóa:

~~~text
decision_usable_until = min(
    thời hạn các thuộc tính cần thiết,
    thời hạn credential,
    thời hạn grant nghiệp vụ,
    thời hạn tái sử dụng policy/quyết định
)
~~~

Công thức chỉ giới hạn thời gian. Cache key và điều kiện vô hiệu hóa còn cần phản ánh subject, tenant, action, resource, version policy và dữ liệu thực sự ảnh hưởng quyết định.

### 12.2. Mới riêng lẻ chưa chắc nhất quán khi kết hợp

Giả sử một thay đổi nghiệp vụ vừa:

~~~text
Chuyển người dùng khỏi nhóm A.
Thu hồi grant do nhóm A cấp.
~~~

Nếu policy đọc membership cũ nhưng grant mới hoặc ngược lại, nó có thể kết hợp các phần không cùng một trạng thái logic.

Tùy yêu cầu, có thể cần snapshot chung, revision vector, transaction trong cùng nguồn hoặc đọc lại các điều kiện liên quan. Không giả định mọi thuộc tính có timestamp gần nhau thì chắc chắn nhất quán.

Cũng không thể dùng một số version toàn cục giả định khi dữ liệu đến từ nhiều nguồn không có cơ chế phối hợp đó.

### 12.3. Cache từ chối cũng có tác động

Cache `DENY` quá lâu có thể làm người vừa được cấp quyền tiếp tục bị chặn. Đây chủ yếu là vấn đề khả dụng và tính đúng chức năng, trong khi cache `ALLOW` sau thu hồi có thể làm lộ quyền.

Không nên dùng chung một chính sách thời gian một cách máy móc cho mọi kết quả. Cache `DENY` cũng cần đúng phạm vi, không được làm sai quyền của tenant hoặc subject khác.

## 13. Khi không làm mới được: biểu diễn đúng trạng thái

Các tình huống sau cần được phân biệt:

| Kết quả lấy thuộc tính | Ý nghĩa |
| --- | --- |
| Nguồn xác nhận membership `REVOKED` | Có dữ liệu cho một quyết định từ chối |
| Không có membership theo hợp đồng nguồn | Không có quan hệ cho phép tương ứng |
| Timeout khi gọi nguồn | Chưa xác định được trạng thái hiện tại |
| Bản cache đã quá hạn | Có snapshot cũ nhưng không đủ mới cho rule này |
| Response sai schema hoặc sai phạm vi | Không có bằng chứng hợp lệ cho yêu cầu |
| Nguồn chỉ đưa tuổi dữ liệu không rõ | Không đủ cơ sở khẳng định giới hạn freshness |

Không ghi đè trạng thái thật thành `ACTIVE` hoặc `REVOKED` chỉ vì request gọi nguồn thất bại.

Với hành động cần bằng chứng mới, luồng có thể dừng và trả lỗi phù hợp để thử lại. Hành động không được thực hiện thành công chỉ vì hệ thống đang thiếu thông tin.

Một số sản phẩm có thể định nghĩa cho phép dùng dữ liệu cũ có giới hạn đối với chức năng ít nhạy cảm. Nếu chọn điều đó, cần phạm vi, thời hạn tuyệt đối và điều kiện rõ ràng; không dùng ngoại lệ cho mọi hành động hoặc gia hạn vô tận khi nguồn tiếp tục lỗi.

`Stale-while-revalidate` có thể phù hợp cho thông tin hiển thị. Với dữ liệu dùng để cấp quyền, trả snapshot cũ trước rồi kiểm tra lại sau chỉ hợp lệ khi chính sách thực sự chấp nhận độ trễ tương ứng. Việc cập nhật sau không thu hồi được lần đọc dữ liệu đã hoàn tất.

## 14. Kiểm tra gần thời điểm thực thi và tác vụ chạy lâu

### 14.1. Quyết định đầu request có thể hết hiệu lực trước khi dùng

~~~text
09:00:00: Kiểm tra thuộc tính, ALLOW.
09:00:20: Người dùng bị thu hồi quyền.
09:03:00: Một job bắt đầu đọc dữ liệu để xuất.
~~~

Nếu yêu cầu nghiệp vụ là người dùng phải còn quyền lúc xuất, kiểm tra lúc nhận request chưa đủ.

Cần định nghĩa quyền được xét tại lúc tạo job, lúc bắt đầu, từng lô xử lý hay trước khi giao kết quả. Job hệ thống phải có policy workload riêng; không tự dùng quyền tài khoản dịch vụ để bỏ qua yêu cầu của job thực hiện thay người dùng.

### 14.2. Một luồng có điểm làm mới và dừng rõ ràng

~~~mermaid
flowchart TD
    A[Nhận yêu cầu và phạm vi] --> B[Lấy các bằng chứng thuộc tính]
    B --> C[Đánh giá nguồn, hiệu lực và độ mới]
    C -->|Cần làm mới| D[Lấy bằng chứng mới theo hợp đồng]
    D --> C
    C -->|Không thể xác minh| E[Dừng theo chính sách lỗi]
    C -->|Đủ điều kiện| F[Đánh giá nội dung policy]
    F -->|DENY| E
    F -->|ALLOW| G[Thực thi trong thời hạn và cơ chế nhất quán]
    G --> H[Ghi audit và trả kết quả]
~~~

Luồng làm mới phải có giới hạn số lần/thời gian. Không lặp vô hạn khi nguồn luôn trả dữ liệu không đủ mới.

### 14.3. Freshness không tự giải quyết TOCTOU

Khoảng trống giữa kiểm tra và sử dụng liên quan đến thứ tự với lệnh thu hồi. Nếu cần bảo đảm một thu hồi đã commit sẽ chặn thao tác chưa commit, phải thiết kế cơ chế nhất quán phù hợp.

Có thể cần kiểm tra version tại bước ghi, phối hợp transaction hoặc một điểm quyết định có thứ tự rõ ràng. Chỉ đặt timestamp rất gần thời điểm thực thi không tạo ra tính nguyên tử.

Đối với tác dụng phụ bên ngoài như gửi email, xuất file hoặc gọi hệ thống thanh toán, rollback dữ liệu nội bộ không tự thu hồi hành động đã gửi. Cần xác định bước nào thực sự được bảo vệ và điểm nào không thể rút lại theo quy trình.

Freshness là bảo đảm có giới hạn thời gian; nó không tự chứng minh tính nhất quán tuyến tính hoặc thu hồi tức thì trên một hệ thống phân tán.

## 15. Quan sát, đo lường và kiểm toán

Một quyết định có thể ghi metadata tối thiểu:

~~~text
subjectId
tenantId
action
resourceReference
attributeNames
sourceIds
sourceVersions
checkedAt của các bằng chứng liên quan
freshnessRuleVersion
decidedAt
decisionUsableUntil
decision
internalReason
requestId
~~~

Không nhất thiết log toàn bộ giá trị thuộc tính, token hoặc hồ sơ người dùng. Metadata thời gian và nguồn thường đã đủ để điều tra vì sao snapshot được dùng; bản thân log vẫn cần kiểm soát truy cập.

Những chỉ số có thể hữu ích:

- Tuổi bằng chứng tại thời điểm quyết định.
- Độ trễ từ thay đổi nguồn đến khi điểm thực thi ngừng cho phép.
- Số lần làm mới thất bại hoặc bị từ chối vì dữ liệu cũ.
- Độ trễ đồng bộ, khoảng trống sự kiện và số lần đối soát sửa lệch.
- Tỷ lệ timestamp bất thường hoặc version đến sai thứ tự.
- Số thao tác bắt đầu trước nhưng thực thi sau thời điểm thu hồi.

Giá trị trung bình hoặc percentile tốt không tự chứng minh giới hạn cứng. Nếu policy dựa vào độ trễ tối đa 20 giây, cần hiểu cách phát hiện và xử lý khi nguồn vượt giới hạn.

Cần xác định thời điểm bắt đầu đo: từ thay đổi nghiệp vụ, từ lúc nguồn ghi nhận hay từ lúc sự kiện được phát. Các phép đo có mốc bắt đầu khác nhau không thể dùng thay cho nhau.

## 16. Kiểm thử bằng đồng hồ kiểm soát được

Với ví dụ số ở phần 6, hãy giữ `now` dưới sự điều khiển của test thay vì dùng sleep. Có thể dùng `Clock.fixed` hoặc truyền trực tiếp `Instant` vào hàm như ví dụ Java.

| Tình huống | Kết quả thời gian/phạm vi mong đợi |
| --- | --- |
| Đúng nguồn, đúng phạm vi, trước deadline | `FRESH` |
| Tại đúng `usableUntil` | Không còn `FRESH` theo hợp đồng nửa mở |
| Sau deadline, còn trong hiệu lực nghiệp vụ | `REFRESH_REQUIRED` |
| Chưa đến `validFrom` | `NOT_YET_VALID` |
| Tại đúng `validUntil` nghiệp vụ | `BUSINESS_EXPIRED` |
| Timestamp xác nhận nằm trong tương lai | `FUTURE_TIMESTAMP` theo ví dụ |
| Evidence thuộc tenant khác | `WRONG_SCOPE` |
| Evidence thuộc subject khác | `WRONG_SCOPE` |
| Nguồn đã xác minh nhưng rule không chấp nhận | `UNTRUSTED_SOURCE` |
| Giới hạn lag nguồn vượt mức rule cho phép | `UPSTREAM_LAG_EXCEEDED` |
| Lag nguồn không xác định | Không tự tạo evidence có lag bằng không |
| Cộng/trừ thời gian vượt miền biểu diễn | `INVALID_EVIDENCE` |
| Giá trị `REVOKED` nhưng đủ mới | Có thể `FRESH`, nhưng policy phải từ chối |
| Cache B nhận snapshot cũ từ cache A | Không đặt lại deadline |
| Token mới dùng role từ snapshot cũ | Tuổi thuộc tính không đổi thành tuổi token |
| Sự kiện version mới tới trước version cũ | Không khôi phục trạng thái cũ |
| Consumer bỏ lỡ sự kiện thu hồi | Phát hiện/đối soát và giới hạn tuổi phải hoạt động |
| Nguồn timeout khi bằng chứng đã hết hạn | Không cho phép hành động cần bằng chứng mới |
| Quyết định cache qua deadline của một thuộc tính | Không tiếp tục tái sử dụng `ALLOW` |
| Job chạy sau thu hồi | Tuân thủ thời điểm xét quyền đã công bố |

Cần thêm test tích hợp chứng minh rằng:

1. Adapter không gán lại mốc xác nhận khi chỉ đọc cache cũ.
2. Policy không hiểu `FRESH` thành `ALLOW`.
3. Deadline qua các tầng không bị kéo dài.
4. Credential hết hạn không được cứu bằng cache quyết định còn hạn.
5. Cơ chế version xử lý đúng subject, tenant và generation.
6. Thao tác bị từ chối không tạo tác dụng phụ trái phép.
7. Bảo đảm về thao tác đồng thời được kiểm chứng với hệ thống dữ liệu thật.

Ma trận là nội dung hướng dẫn kiểm thử, không phải báo cáo rằng các đoạn mã đã được chạy trên ứng dụng hoàn chỉnh.

## 17. Ngộ nhận và bài tập vận dụng

| Ngộ nhận | Cách hiểu chính xác hơn |
| --- | --- |
| JWT hợp lệ nghĩa là thuộc tính hiện tại | Token có thể bảo vệ nguyên vẹn snapshot cũ |
| `iat` mới nghĩa là role mới | Cần biết mốc xác nhận và nguồn của role |
| `auth_time` mới nghĩa là membership mới | Tuổi xác thực và độ mới thuộc tính là hai điều kiện |
| Refresh token luôn đọc lại mọi quyền | Phụ thuộc hợp đồng và cache của authorization server |
| Fetch lại là làm mới | Có thể chỉ lấy lại cùng bản sao cũ |
| `lastModified` mới chứng minh mọi trường mới | Có thể chỉ một phần resource vừa thay đổi |
| Có introspection là không còn dữ liệu cũ | Cần biết cách tính metadata và cache của nó |
| Có sự kiện thu hồi là thu hồi tức thì | Cần xử lý độ trễ, mất sự kiện và thứ tự |
| Có version là biết version hiện tại | Bản tham chiếu version cũng có yêu cầu độ mới |
| TTL bằng không tạo nhất quán mạnh | Cần nguồn đọc và thứ tự thực thi/thu hồi phù hợp |
| Dữ liệu `FRESH` thì cho phép | Nội dung thuộc tính và policy vẫn có thể từ chối |
| Tất cả dữ liệu hết hạn cùng lúc | Quyết định phải tuân theo deadline của bằng chứng cần thiết |

Bài tập: một cổng quản trị cho phép xuất danh sách khách hàng khi:

~~~text
accountState = ACTIVE
membershipState = ACTIVE
permission bao gồm CUSTOMER_EXPORT
deviceCompliance = COMPLIANT
~~~

Hãy thiết kế hợp đồng freshness cho từng điều kiện và trả lời:

- Nguồn nào có thẩm quyền xác nhận từng thuộc tính?
- Mốc nào là thời điểm xác nhận có ý nghĩa, thay vì thời điểm copy?
- Những độ trễ nào tồn tại từ nguồn đến API?
- Credential mới có thể được cấp từ cache cũ ở đâu?
- Deadline của quyết định xuất được tính thế nào?
- Khi quyền bị thu hồi lúc job đang đợi, bước nào phải kiểm tra lại?
- Nếu đồng bộ mất sự kiện hoặc source timeout, hành động nào được tiếp tục?
- Có thể đo và kiểm thử độ trễ thu hồi từ mốc nào?

Một thiết kế đủ rõ phải chỉ ra **bằng chứng đến từ đâu, được xác nhận khi nào, được dùng đến bao giờ và điều gì xảy ra khi không còn đủ mới**. Những câu trả lời cần gắn với đúng hành động và đường thực thi thực tế.
