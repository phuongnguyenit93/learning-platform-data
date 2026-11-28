# API versioning

## 1. Phiên bản API là một phần của bề mặt bảo mật

API versioning giúp một hệ thống thay đổi hợp đồng giao tiếp mà vẫn quản lý được các client chưa chuyển đổi. Trong thiết kế yêu cầu bảo mật, phiên bản không chỉ là đoạn `v1` hay `v2` trong URL. Mỗi contract còn đang phục vụ có thể là một đường tới dữ liệu, quyền và các thao tác nhạy cảm của hệ thống.

Giả sử nền tảng học tập bổ sung kiểm tra quyền sở hữu ở API v2 nhưng vẫn để v1 chạy theo logic cũ. Client không có quyền trên v2 có thể quay lại v1. Nhãn “deprecated” trên tài liệu không chặn được request đó; endpoint vẫn là một phần của hệ thống cần bảo vệ.

OWASP API9:2023 nêu rủi ro từ các phiên bản cũ hoặc endpoint còn hoạt động nhưng không được cập nhật, cùng việc thiếu inventory và kế hoạch retirement. Chạy nhiều phiên bản cũng làm tăng bề mặt cần quản lý. [OWASP API Security: Improper Inventory Management](https://api-security.owasp.org/editions/2023/en/0xa9-improper-inventory-management/).

Mục tiêu của bài học là chuyển nhu cầu “hỗ trợ nhiều version” thành những quyết định có thể kiểm chứng: contract nào được phục vụ, chọn contract như thế nào, kiểm soát bảo mật nào áp dụng, ai chịu trách nhiệm migration và bằng chứng nào xác nhận version cũ đã ngừng xử lý nghiệp vụ.

Các thời điểm, route và ngưỡng trong ví dụ là chính sách minh họa. Chúng không mô tả cấu hình triển khai thực tế của module học tập.

## 2. Phân biệt version hợp đồng với version triển khai

| Khái niệm | Trả lời câu hỏi nào? | Ví dụ |
| --- | --- | --- |
| API contract version | Client phải hiểu cấu trúc và ngữ nghĩa giao tiếp nào? | `/api/v1/courses`, `/api/v2/courses` |
| Build hoặc release của service | Bản phần mềm nào đang xử lý request? | Build `course-service-2026.11.27.3` |
| Schema lưu trữ | Dữ liệu được tổ chức theo migration nào? | Database migration `M042` |
| Revision cấu hình bảo mật | Bộ policy/routing nào đang được thực thi? | Policy revision `course-access-17` |
| Version SDK | Thư viện client nào được phân phối? | SDK có thể gọi một hoặc nhiều API contract |

Một build mới có thể tiếp tục phục vụ cả v1 và v2. Ngược lại, hai host dùng cùng đường `/v1` vẫn có thể chạy build và cấu hình bảo mật khác nhau. Vì vậy inventory chỉ ghi “API v1” là chưa đủ để tìm các đường cũ còn mở.

Không nên lấy version database hay SDK làm bằng chứng endpoint đã được nâng cấp bảo mật. Bằng chứng phải liên kết tới route/host thực tế, build đang chạy, policy có hiệu lực và bộ kiểm tra phù hợp.

API version cũng không phải nhãn mức tin cậy. Một request chọn v2 vẫn phải được xác thực và phân quyền. Client được quyền chọn contract được hỗ trợ, không được dùng version để chọn một bộ kiểm tra dễ hơn.

## 3. Giữ bất biến bảo mật qua các contract

Một nền tảng có thể thay hình dạng response giữa v1 và v2:

```json
{
  "id": "course-17",
  "title": "Java nền tảng",
  "teacherName": "Lan"
}
```

```json
{
  "courseId": "course-17",
  "title": "Java nền tảng",
  "instructor": {
    "displayName": "Lan"
  }
}
```

Sự khác nhau về cấu trúc có thể được xử lý bằng adapter theo contract. Nhưng các invariant sau không được mất đi khi request dùng v1:

| Invariant | Ý nghĩa đối với mọi contract còn phục vụ |
| --- | --- |
| Phạm vi tenant | Người của tenant A không xem hoặc sửa dữ liệu riêng của tenant B |
| Quyền đối tượng | Chỉ người có quyền mới xem tài liệu chưa công bố hoặc sửa khóa học |
| Quyền theo field | Một response không công bố field nội bộ chỉ vì contract cũ từng trả entity rộng |
| Quyền thao tác | Học viên không gọi được hành động quản trị qua route cũ |
| Miền đầu vào | Dữ liệu không mở rộng quyền ghi hoặc tài nguyên vượt policy đã chốt |
| Xác thực token | Mọi adapter thực thi đúng issuer, audience, hiệu lực và policy token của endpoint |

Các contract có thể sử dụng scope hoặc loại credential khác nếu được thiết kế có chủ đích. Tuy nhiên sự khác nhau phải được ghi trong policy và chứng minh không tạo đường vượt quyền. Không dùng cùng một nhãn “v1 tương thích” để bỏ kiểm tra bảo mật bắt buộc.

Một sửa lỗi ngăn lộ dữ liệu có thể làm client cũ không còn nhận được field trước đây. Cần phân loại đó là khắc phục quyền công bố, không mặc định bảo tồn hành vi sai như một cam kết tương thích. Đội sản phẩm và an toàn thông tin phải chọn cách sửa, chuyển đổi hoặc ngừng phục vụ đường bị ảnh hưởng trong thời hạn xử lý rủi ro đã chốt.

## 4. Chọn version bằng một hợp đồng rõ ràng

### 4.1. Các cách biểu diễn thường gặp

| Cách chọn | Ví dụ | Điểm cần đặc tả |
| --- | --- | --- |
| Path | `/api/v2/courses` | Gateway và backend phải ánh xạ cùng contract |
| Header riêng | `Api-Version: 2` | Thiếu, lặp hoặc giá trị không hỗ trợ được xử lý ra sao? |
| Media type | `Accept: application/vnd.example.course+json;version=2` | Quy tắc negotiation và cache variation |
| Query parameter | `?api-version=2` | Parsing thống nhất, nhận diện log và cache |

Không có một lựa chọn tự động làm API an toàn hơn trong mọi kiến trúc. Chọn cách đội vận hành có thể cấu hình, quan sát và kiểm chứng nhất quán. Các header/media type ở bảng là ví dụ contract của ứng dụng, không phải một cơ chế versioning bắt buộc của HTTP.

Trong tình huống của bài, hệ thống chọn path làm nguồn version duy nhất. Nếu client đồng thời gửi `Api-Version` hoặc query `api-version`, request bị từ chối theo contract để tránh hai cách diễn giải. Một sản phẩm có thể chọn quy tắc khác, nhưng phải công bố thứ tự ưu tiên và kiểm tra các trường hợp mâu thuẫn.

### 4.2. Không đoán hoặc tự hạ version

Nếu nhận `/api/v9/courses` khi chỉ hỗ trợ v1 và v2, server không được âm thầm gọi v1. Nếu thiếu version, cần route mặc định được công bố rõ hoặc trả lỗi theo contract. Không mặc định “latest” là một contract ổn định, vì một deployment có thể thay đổi ý nghĩa của nó.

SDK cũng không nên tự quay về v1 khi v2 trả lỗi phân quyền hoặc lỗi validation. Fallback đó có thể biến khác biệt kiểm soát giữa các version thành một đường downgrade. Nếu có migration fallback thực sự cần thiết, phải giới hạn loại lỗi, thao tác và thời gian theo một policy riêng.

### 4.3. Gateway và backend không được hiểu hai version khác nhau

Những yếu tố cần kiểm tra gồm path rewrite, URL decoding, dấu gạch chéo, phân biệt chữ hoa/thường, header lặp và alias route. Không nhất thiết mọi đầu vào lạ đều được chấp nhận; điều cần bảo đảm là tầng kiểm tra và tầng xử lý thống nhất về contract cuối cùng hoặc cùng từ chối request mơ hồ.

Nếu gateway gắn metadata nội bộ như `Resolved-Api-Contract`, phải loại bỏ giá trị cùng tên từ request bên ngoài và xác thực nguồn metadata trong kênh nội bộ. Không tin một header mà client có thể tự đặt rồi dùng nó để bỏ bước resolve version.

Định danh contract đã resolve nên được giữ trong request context của server, được adapter sử dụng và xuất hiện trong telemetry. Không để mỗi lớp tự đọc lại raw header/path rồi quyết định một lần khác.

### 4.4. Version qua header phải xét cache

Nếu representation phụ thuộc `Accept` hoặc một request header khác, policy cache phải phân biệt đúng biến thể; `Vary` mô tả những request header ảnh hưởng tới việc chọn response. `Vary` không thay phân quyền hoặc tự làm một cache được phép chia sẻ dữ liệu riêng. [RFC 9110: Vary](https://www.rfc-editor.org/rfc/rfc9110.html#name-vary).

Trong ví dụ hồ sơ cá nhân, có thể chọn không cho shared cache lưu response. Với danh mục công khai, cần cache key phân biệt contract và các chiều variation thực sự được sử dụng. Kiểm tra việc chọn contract ở backend mà bỏ qua CDN vẫn có thể trả nhầm schema hoặc dữ liệu cho client.

## 5. Vòng đời phải phân biệt thông báo và thực thi

Một vòng đời mẫu có thể là:

```text
Draft / Preview
→ Supported
→ Deprecated
→ Retired
→ Removed
```

| Trạng thái | Ý nghĩa trong policy mẫu | Gate cần có |
| --- | --- | --- |
| Draft / Preview | Contract đang thử nghiệm cho tập client đã xác định | Owner, phạm vi dữ liệu và mạng, kiểm soát nền tảng |
| Supported | Phục vụ theo cam kết chính thức | Sửa lỗi, kiểm tra bảo mật và theo dõi consumer |
| Deprecated | Vẫn phục vụ nhưng đã có kế hoạch chuyển đổi | Ngày deprecation, migration guide, sunset và owner |
| Retired | Không xử lý nghiệp vụ của contract cũ | Chặn dispatch trên mọi đường có thể tới service |
| Removed | Route/code/tài nguyên cũ đã được dọn theo kế hoạch | Bằng chứng không còn exposure và không mất khả năng điều tra cần thiết |

“Deprecated” không có nghĩa “an toàn để bỏ vá lỗi”. Chừng nào endpoint còn xử lý nghiệp vụ hoặc dữ liệu thật, nó vẫn phải có kiểm soát tương ứng với rủi ro đó.

“Retired” có thể còn một route trả error contract cố định để giúp client chuyển đổi. “Removed” có thể làm route không còn tồn tại. Hai trạng thái cần được phân biệt trong inventory và tiêu chí kiểm tra, thay vì coi xóa tài liệu là đã xóa bề mặt truy cập.

Preview cũng cần bảo vệ. Một host thử nghiệm kết nối dữ liệu thật hoặc có đường truy cập tới service thật không thể dựa vào việc “không công bố URL” làm kiểm soát truy cập.

## 6. Inventory phải chỉ ra nơi contract đang chạy

Một entry inventory mẫu có thể chứa các thông tin sau; đây là nội dung minh họa, không phải file cần tạo:

```yaml
contract: courses-v1
owner: course-platform-team
environment: production
audience: authenticated-learning-clients
publicRoute: /api/v1/courses
backendAdapter: course-v1-adapter
status: DEPRECATED
deprecatedAt: '2026-11-01T00:00:00Z'
sunsetAt: '2027-09-30T00:00:00Z'
replacement: courses-v2
dataClassification: tenant-scoped-learning-data
securityPolicy: course-access-policy
migrationOwner: client-integration-team
```

Khi áp dụng trong sản phẩm, cần liên kết entry này tới host thực tế, gateway route, deployment và revision policy. Cùng một contract có thể xuất hiện ở nhiều vùng triển khai hoặc host đối tác; mỗi exposure cần được đối soát.

Không lấy riêng tài liệu OpenAPI làm inventory vận hành. Một route đã bị bỏ khỏi tài liệu vẫn có thể còn ở reverse proxy, load balancer, host cũ hoặc service nội bộ có ingress ngoài dự kiến. Inventory cần được so sánh với nguồn triển khai và quan sát lưu lượng phù hợp.

Đội vận hành cũng cần biết consumer nào còn dùng v1. Có thể dùng định danh ứng dụng đã xác thực và version SDK được khai báo theo contract, nhưng không xem header `User-Agent` do client gửi là bằng chứng danh tính. Consumer chưa nhận diện được phải xuất hiện như một khoảng trống cần xử lý, không được tự xem là không có người dùng.

## 7. Ví dụ Java: resolve và gate vòng đời một lần

Ví dụ Java 17 sau minh họa policy path-only cho v1 và v2. Clock được truyền vào để quy tắc theo thời gian có thể được kiểm chứng tại ranh giới. Code không triển khai authentication, authorization hay HTTP routing; các phần đó vẫn bắt buộc trong ứng dụng sử dụng policy này.

```java
import java.time.Clock;
import java.time.Instant;
import java.util.Map;
import java.util.Objects;

public final class ApiVersionPolicy {
    public enum Contract { V1, V2 }

    public record SupportWindow(Instant deprecatedAt, Instant sunsetAt) {
        public SupportWindow {
            if (sunsetAt != null && deprecatedAt == null) {
                throw new IllegalArgumentException("Sunset needs a deprecation date");
            }
            if (sunsetAt != null && sunsetAt.isBefore(deprecatedAt)) {
                throw new IllegalArgumentException("Sunset precedes deprecation");
            }
        }
    }

    public record Decision(
            Contract contract,
            boolean deprecated,
            Instant deprecatedAt,
            Instant sunsetAt
    ) {}

    public static final class Rejected extends RuntimeException {
        private final int status;
        private final String code;

        public Rejected(int status, String code) {
            super(code);
            this.status = status;
            this.code = code;
        }

        public int status() { return status; }
        public String code() { return code; }
    }

    private final Clock clock;
    private final Map<Contract, SupportWindow> windows;

    public ApiVersionPolicy(Clock clock, Map<Contract, SupportWindow> windows) {
        this.clock = Objects.requireNonNull(clock);
        this.windows = Map.copyOf(windows);
    }

    public Decision resolve(
            String pathVersion,
            boolean hasAlternativeVersionSelector
    ) {
        if (hasAlternativeVersionSelector) {
            throw new Rejected(400, "AMBIGUOUS_API_VERSION");
        }
        if (pathVersion == null) {
            throw new Rejected(400, "API_VERSION_REQUIRED");
        }

        Contract contract = switch (pathVersion) {
            case "v1" -> Contract.V1;
            case "v2" -> Contract.V2;
            default -> throw new Rejected(404, "API_VERSION_UNSUPPORTED");
        };

        SupportWindow window = windows.get(contract);
        if (window == null) {
            throw new Rejected(404, "API_VERSION_UNSUPPORTED");
        }

        Instant now = clock.instant();
        if (window.sunsetAt() != null && !now.isBefore(window.sunsetAt())) {
            throw new Rejected(410, "API_VERSION_RETIRED");
        }

        boolean deprecated = window.deprecatedAt() != null
                && !now.isBefore(window.deprecatedAt());
        return new Decision(
                contract, deprecated, window.deprecatedAt(), window.sunsetAt()
        );
    }

    public static ApiVersionPolicy example(Clock clock) {
        return new ApiVersionPolicy(clock, Map.of(
                Contract.V1, new SupportWindow(
                        Instant.parse("2026-11-01T00:00:00Z"),
                        Instant.parse("2027-09-30T00:00:00Z")
                ),
                Contract.V2, new SupportWindow(null, null)
        ));
    }
}
```

`pathVersion` là token do router xác định sau quy tắc chuẩn hóa đã chốt, không phải một chuỗi client được tùy ý gán vào context. `hasAlternativeVersionSelector` phải được tính đúng từ các nguồn selector bị cấm theo contract; không lấy một boolean do client tự khai báo.

Trong ví dụ, unsupported version trả `404` và version đã retired trả `410`. Đây là error policy của tình huống. `410 Gone` biểu thị tài nguyên không còn sẵn có và tình trạng có tính lâu dài; không phải mọi API đều buộc dùng cùng cách công bố route đã dừng. [RFC 9110: 410 Gone](https://www.rfc-editor.org/rfc/rfc9110.html#name-410-gone).

Quyết định trả về chỉ xác định contract còn được dispatch. Sau đó request vẫn phải đi qua xác thực, phân quyền và validation của thao tác. Adapter v1 và v2 nên chuyển sang cùng các command/policy domain cho những invariant chung, rồi dựng response DTO theo contract tương ứng.

Clock của hệ thống triển khai phải được vận hành nhất quán; một timestamp trong code không tự bảo đảm mọi node ngừng cùng lúc. Registry mẫu cũng không tự phát hiện endpoint ở host cũ: cần inventory, routing và kiểm tra exposure thực tế để hoàn tất yêu cầu retirement.

## 8. Thông báo deprecation và sunset đúng ý nghĩa

Một response của contract v1 trong ví dụ có thể công bố:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store
Deprecation: @1793491200
Sunset: Thu, 30 Sep 2027 00:00:00 GMT
Link: </docs/api/courses-v1-migration>; rel="deprecation"; type="text/html"
```

`Deprecation` theo RFC 9745 dùng Structured Field Date, dạng `@` theo sau giá trị timestamp giây. Nó cho biết thời điểm resource đã hoặc sẽ deprecated. Link relation `deprecation` có thể trỏ tới tài liệu giải thích. Bản thân thông báo deprecation không thay đổi hành vi resource. [RFC 9745: Deprecation response header](https://www.rfc-editor.org/rfc/rfc9745.html).

`Sunset` dùng HTTP-date và cho biết thời điểm resource được kỳ vọng không còn đáp ứng. Đây là thông tin để client lập kế hoạch, không phải một cơ chế tự ngắt service. Thời điểm sunset không được sớm hơn thời điểm deprecation theo quan hệ được RFC 9745 quy định. [RFC 8594: Sunset](https://www.rfc-editor.org/rfc/rfc8594.html), [RFC 9745: Sunset](https://www.rfc-editor.org/rfc/rfc9745.html#section-4).

Trong ví dụ, deprecation bắt đầu lúc `2026-11-01T00:00:00Z` và retirement được chốt lúc `2027-09-30T00:00:00Z`. Cần chú ý hai header dùng hai kiểu biểu diễn thời gian khác nhau; không gửi một chuỗi ngày HTTP vào `Deprecation` chỉ vì `Sunset` dùng định dạng đó.

Đội API phải định nghĩa phạm vi thông báo. Header trên một endpoint có áp dụng cả contract hay chỉ resource đang truy cập? Nếu chính sách áp dụng cho toàn bộ v1, migration guide và inventory phải nói rõ, đồng thời các route liên quan cần công bố thông tin nhất quán.

Không đưa token, khóa API hoặc định danh dữ liệu cá nhân vào URL tài liệu migration. Nếu tài liệu dành cho đối tác đã xác thực, việc truy cập tài liệu có kiểm soát riêng; URL trong header không phải kênh cấp credential.

Sau sunset, API có thể trả error contract cố định:

```http
HTTP/1.1 410 Gone
Content-Type: application/json
Cache-Control: no-store

{
  "code": "API_VERSION_RETIRED",
  "migrationGuide": "/docs/api/courses-v1-migration"
}
```

Cache policy ở ví dụ ngăn lưu response retirement ngoài dự kiến trong quá trình chuyển đổi. Policy thực tế cần được chọn cùng hành vi phục hồi và quyền công bố thông tin; không dựa vào một response lỗi để mặc định mọi cache sẽ xử lý đúng ý đội vận hành.

## 9. Migration phải bảo toàn quyền và ý nghĩa nghiệp vụ

### 9.1. Bản đồ thay đổi cần vượt ra ngoài tên field

Một migration guide hữu ích cần nêu route, schema, mã lỗi, cách phân trang, tính idempotent và các quy tắc quyền liên quan. Chỉ hướng dẫn đổi `/v1` thành `/v2` chưa đủ nếu cách chọn tài nguyên hoặc ý nghĩa field đã thay đổi.

Ví dụ:

| Hạng mục | v1 | v2 | Điểm cần kiểm chứng khi chuyển |
| --- | --- | --- | --- |
| ID khóa học | `id` | `courseId` | Giữ đúng định danh, không đổi tài nguyên ngoài ý muốn |
| Giảng viên | `teacherName` | `instructor.displayName` | Không bổ sung email riêng qua object mới |
| Phân trang | Chỉ số trang | Cursor | Cursor không tạo đường đọc ngoài tenant hoặc ngoài bộ lọc được cấp |
| Cập nhật | Một payload cũ | Command mới có trường rõ | Không nới quyền ghi bằng adapter tương thích |
| Lỗi validation | Dạng lỗi cũ | Dạng lỗi có code ổn định | Client không retry vô hạn hoặc fallback sang version cũ |

Nếu v1 từng cho sửa field mà client không thực sự có quyền, migration không được mô phỏng lại hành vi đó bên trong adapter v2 để giữ “tương thích”. Cần tách yêu cầu sửa lỗi bảo mật khỏi yêu cầu hỗ trợ client chuyển cấu trúc dữ liệu.

### 9.2. Định tuyến thử nghiệm không được gây tác dụng phụ hai lần

Có thể so sánh response của hai adapter trong môi trường thử hoặc bằng cơ chế shadow phù hợp. Nhưng không nhân đôi request ghi thật chỉ để xem v1 và v2 có cho kết quả giống nhau. Một lần đăng ký khóa học, phát chứng chỉ hoặc gửi email có thể tạo tác dụng phụ không thể giải quyết bằng so sánh JSON.

Nếu migration thật sự cần hai đường ghi, thiết kế phải nêu cơ chế idempotency, quyền thực thi, giao dịch và đối soát. API contract version không tự tạo một namespace chống lặp; việc client retry cùng ý định qua hai contract cần được xét theo nghiệp vụ.

Đối với đọc dữ liệu nhạy cảm, shadow traffic cũng là một luồng dữ liệu. Không gửi bản sao production chứa thông tin học viên tới một host preview chỉ vì host đó phục vụ v2.

### 9.3. Không chuyển hướng ngầm request ghi sang contract khác

Một redirect không biến payload v1 thành command v2 và không giải quyết khác biệt quyền. Client có thể xử lý redirect, retry hoặc credential theo cách khác nhau. Với thao tác ghi đã retired, error contract cùng migration guide thường dễ kiểm soát hơn một chuyển hướng tự động không có cam kết tương thích.

Nếu sản phẩm quyết định duy trì adapter tương thích, adapter phải có owner, thời hạn và bộ kiểm tra bảo mật riêng trong inventory. Không gọi nó là “chỉ một proxy” để bỏ qua trách nhiệm đối với contract cũ.

## 10. Retirement cần gate kỹ thuật và bằng chứng vận hành

Một kế hoạch ngừng v1 phải xác định ít nhất bốn nhóm việc: consumer đã được thông báo, route đã bị chặn, đường backend không còn phục vụ contract cũ và tài nguyên cũ được dọn theo phạm vi. Những việc này không được suy ra chỉ từ ngày tháng trên tài liệu.

### 10.1. Trước thời điểm dừng

- Xác nhận inventory các host, route, alias, gateway và adapter của v1.
- Kiểm tra replacement phục vụ đúng quyền và nghiệp vụ cho các consumer cần chuyển.
- Chốt cách xử lý consumer chưa chuyển, bao gồm owner và rủi ro được đánh giá.
- Phân phối cấu hình gate tới các node trước deadline; theo dõi revision và đồng hồ vận hành.
- Chốt policy cho request đang xử lý và job đã được nhận trước sunset.

Policy mẫu của bài là không dispatch request v1 mới từ thời điểm sunset trở đi. Request đã được chấp nhận trước thời điểm đó có thể hoàn tất theo timeout và policy nghiệp vụ đã chốt. Điều này khác với yêu cầu hủy mọi giao dịch đúng tại một thời khắc; nếu cần cách thứ hai, phải thiết kế riêng để tránh trạng thái nửa chừng.

### 10.2. Tại và sau thời điểm dừng

Không chỉ kiểm tra URL chính. Cần xác minh các đường tới contract v1 đã được inventory: host cũ, alias, route nội bộ có thể bị gọi từ nguồn ngoài policy, vùng triển khai khác và đường đi trực tiếp tới backend nếu kiến trúc cho phép kiểm tra.

Một gate chỉ ở gateway không đủ nếu backend vẫn có ingress ngoài kiểm soát. Ngược lại, backend trả đúng lỗi nhưng một gateway cũ vẫn phục vụ một build khác cũng chưa hoàn tất retirement.

Sau khi chặn nghiệp vụ, tiếp tục quan sát các request v1 bị từ chối để phát hiện consumer bỏ sót hoặc retry storm. Số request v1 chưa về zero không tự có nghĩa gate thất bại; cần phân biệt request bị chặn với request còn thực sự dispatch vào handler cũ.

### 10.3. Rollback không được vô tình hồi sinh endpoint cũ

Rollback build ứng dụng có thể mang lại router hoặc adapter cũ. Vì vậy revision lifecycle và gate retired cần được bảo toàn hoặc được kiểm tra như một điều kiện trước khi đưa build rollback vào phục vụ.

Nếu phục hồi v1 là một quyết định nghiệp vụ thực sự, phải đánh giá lại kiểm soát, owner, thời hạn và consumer, thay vì coi đó là tác dụng phụ chấp nhận được của việc khôi phục build. Một backup deployment tồn tại không đồng nghĩa nó được phép nhận traffic.

Không xóa dữ liệu nghiệp vụ chỉ vì contract bị retired. API lifecycle, thời hạn lưu dữ liệu, audit và database migration là các quyết định khác nhau. Việc dọn route/code phải giữ đúng phạm vi đã được phê duyệt của kế hoạch.

## 11. Quan sát contract thực sự được phục vụ

Telemetry hữu ích cần phân biệt ít nhất version client yêu cầu, contract server đã resolve và kết quả gate. Nếu chỉ ghi raw URL, một path rewrite sai có thể bị bỏ sót; nếu chỉ ghi contract cuối cùng, khó điều tra request mơ hồ đã đến từ nguồn nào.

Một sự kiện mẫu đã giới hạn dữ liệu:

```json
{
  "event": "API_CONTRACT_REJECTED",
  "requestedContract": "v1",
  "resolvedContract": "courses-v1",
  "reasonCode": "RETIRED",
  "policyRevision": "course-contract-policy-4",
  "consumerRef": "authenticated-client-reference",
  "correlationId": "request-correlation-reference"
}
```

Không log Authorization header, API key hoặc body chứa dữ liệu học viên để đo usage theo version. Định danh consumer cần tuân policy dữ liệu của hệ thống. Nếu client chưa được xác thực, có thể ghi trạng thái chưa nhận diện thay vì tự tin cậy một header tên client.

Metrics nên dùng tập nhãn contract hữu hạn trong registry. Không lấy chuỗi version tùy ý do client gửi làm label không giới hạn; các giá trị không hỗ trợ có thể gom thành nhóm `unsupported` và lưu chi tiết đã giới hạn ở kênh điều tra phù hợp.

Các chỉ số cần giải thích được gồm: request được phục vụ theo contract, request bị chặn vì retired, consumer còn dùng deprecated contract, chênh lệch revision giữa node, và dispatch bất ngờ tới handler retired. Mỗi cảnh báo phải có owner và hành động vận hành tương ứng.

## 12. Bộ yêu cầu bảo mật có thể nghiệm thu

| ID | Yêu cầu mẫu | Bằng chứng nghiệm thu |
| --- | --- | --- |
| SR-VER-01 | Mọi contract/host/route được triển khai có entry inventory, owner, audience và trạng thái lifecycle trước khi nhận traffic | Đối soát inventory với nguồn route và deployment |
| SR-VER-02 | Version được resolve đúng một lần theo contract công bố; thiếu, không hỗ trợ và mâu thuẫn có hành vi rõ | Ca selector thiếu/lạ/lặp/mâu thuẫn qua đường HTTP thật |
| SR-VER-03 | Không fallback sang contract khác vì lỗi xác thực, phân quyền hoặc validation | Kiểm tra gateway, adapter và SDK với các lỗi này |
| SR-VER-04 | Mọi contract còn phục vụ giữ các invariant tenant, object, field và thao tác đã chốt | Ma trận kiểm tra bảo mật chạy theo từng contract |
| SR-VER-05 | Từng deprecated contract có replacement hoặc kế hoạch kết thúc, owner migration và thời điểm liên quan | Hồ sơ lifecycle và consumer mapping |
| SR-VER-06 | Thông tin deprecation/sunset dùng cú pháp đúng và nhất quán với lifecycle registry | Readback header của từng route trong phạm vi |
| SR-VER-07 | Từ sunset, request mới của contract retired không dispatch vào handler nghiệp vụ | Ca ranh giới thời gian và bằng chứng trace/handler |
| SR-VER-08 | Gate retirement áp dụng trên mọi exposure đã inventory, không chỉ hostname chính | Kiểm tra route/host/region/alias theo danh mục |
| SR-VER-09 | Cache không trả representation sai contract hoặc chia sẻ dữ liệu trái policy | Ca biến thể header/path và phân tách người dùng |
| SR-VER-10 | Rollback deployment không tự mở lại contract retired | Diễn tập rollback và đối chiếu revision/gate |
| SR-VER-11 | Migration không lặp tác dụng phụ hoặc mở rộng quyền do adapter tương thích | Ca ghi/retry/idempotency và kiểm tra command domain |
| SR-VER-12 | Telemetry ghi được contract đã resolve, lifecycle decision và revision mà không log credential | Kiểm tra sự kiện và giới hạn nhãn metrics |

Trong tình huống đơn giản có thể chốt tối đa hai contract của cùng một nhóm API đồng thời ở trạng thái supported/deprecated. Đây là giới hạn quản trị mẫu để làm rõ chi phí hỗ trợ, không phải một con số an toàn phổ quát. Nếu cần nhiều contract hơn, phải có capacity, owner và kế hoạch xử lý tương ứng.

Yêu cầu thời hạn vá lỗi cần liên kết tới policy rủi ro của tổ chức và bao phủ toàn bộ contract còn phục vụ. Không viết riêng một cam kết chỉ cho version mới nhất rồi bỏ các đường cũ đang tiếp xúc dữ liệu thật.

## 13. Thiết kế tiêu chí kiểm thử

Phần này mô tả cách xác minh một triển khai sản phẩm; không khẳng định những kiểm thử dưới đây đã được chạy trong bài học.

### 13.1. Resolve và lifecycle

| Ca | Đầu vào/điều kiện | Kỳ vọng theo ví dụ |
| --- | --- | --- |
| V1 | Path `v1`, trước deprecation | Resolve v1 nếu vẫn nằm trong registry; áp dụng toàn bộ kiểm soát nghiệp vụ |
| V2 | Path `v1`, từ deprecation nhưng trước sunset | Còn phục vụ theo policy, metadata migration đúng |
| V3 | Path `v1`, đúng thời điểm sunset | Trả lỗi retired, không gọi handler v1 |
| V4 | Path `v1`, sau sunset | Tiếp tục bị chặn, không fallback v2 |
| V5 | Path `v9` | Unsupported theo error contract, không đoán version |
| V6 | Thiếu version | Hành vi API_VERSION_REQUIRED của ví dụ |
| V7 | Có path và thêm selector header/query | Từ chối theo policy path-only |
| V8 | Nguồn metadata nội bộ bị client giả mạo | Không đổi contract hoặc bỏ qua bước gate |
| V9 | Rollback build sau retirement | Gate vẫn chặn request v1 mới |
| V10 | Một host/alias cũ trong inventory | Không còn đường phục vụ nghiệp vụ v1 ngoài policy |

Để kiểm tra V2–V4 trong unit test, truyền `Clock.fixed` trước, đúng và sau mốc sunset thay vì chỉnh đồng hồ máy production. Trong kiểm tra tích hợp, dùng môi trường và cấu hình thời gian được kiểm soát, đồng thời quan sát số lần handler thực sự được gọi.

V3 cần kiểm tra điều kiện bao gồm dấu bằng. Nếu chỉ dùng phép so sánh “sau sunset”, request đúng tại mốc có thể bị xử lý khác contract đã công bố. Ngoài kiểm tra logic, vận hành phải quan sát clock/configuration của các node để đánh giá hệ thống phân tán thật.

### 13.2. Ma trận bất biến qua v1 và v2

Chuẩn bị hai tenant, tài khoản học viên, giảng viên và quản trị trong phạm vi tương ứng. Với từng contract còn phục vụ, kiểm tra:

- Một actor không đọc hoặc sửa khóa học riêng của tenant khác.
- Người không có quyền không xem tài liệu chưa công bố.
- Response không xuất trường riêng của giảng viên ngoài contract và quyền được cấp.
- Endpoint ghi không nhận thêm field nhạy cảm từ một DTO cũ rộng hơn.
- Credential sai issuer, audience hoặc hết hiệu lực không được một adapter cũ chấp nhận ngoài policy.
- Lỗi của contract mới không khiến SDK tự chuyển sang contract cũ.

Các version không nhất thiết trả JSON giống nhau. Tiêu chí chung là quyền và trạng thái nghiệp vụ đúng; tiêu chí riêng của từng version là schema và ngữ nghĩa contract. Không gộp hai loại tiêu chí thành một phép so sánh nguyên văn response.

### 13.3. Gateway, cache và deployment

Kiểm tra chỉ gọi trực tiếp service không bao phủ path rewrite hoặc cache của gateway. Cần request đi qua đường client thực sự sử dụng và xác minh contract đã resolve ở server khớp với lựa chọn được chấp nhận ở biên.

Nếu dùng version qua header, xen kẽ các request của hai contract để phát hiện cache trả representation nhầm. Với dữ liệu riêng, kiểm tra thêm phân tách người dùng theo policy cache. Cùng lúc, cần chứng minh phiên bản được chọn không làm bỏ auth middleware hoặc quota tương ứng.

Đối với retirement, một response `410` từ URL chính là bằng chứng cần nhưng chưa đủ. Cần đối soát mọi exposure và xác nhận không có handler v1 tiếp tục xử lý request mới sau deadline. Nếu metrics chỉ cho biết vẫn có request tới v1, phải tách request bị gate chặn khỏi request được dispatch thành công.

### 13.4. Migration và request đang xử lý

Kiểm tra một request được chấp nhận ngay trước sunset và một request đến tại mốc. Kết quả phải phù hợp policy inflight đã chốt, không tự suy ra từ việc node có còn process đang chạy hay không.

Với tác vụ bất đồng bộ, phân biệt API contract dùng để nhận request với format event/command trong queue. Event schema không tự retired cùng một route HTTP; cần policy xử lý công việc đã được chấp nhận và các kiểm tra quyền nghiệp vụ thích hợp khi thực thi.

## 14. Những quyết định dễ để lại đường cũ ngoài kiểm soát

**Chỉ bỏ v1 khỏi OpenAPI.** Tài liệu không phải router. Endpoint có thể vẫn chạy qua host hoặc adapter cũ.

**Chỉ sửa kiểm soát ở v2.** Nếu cùng dữ liệu còn truy cập được qua v1 với quyền yếu hơn, bề mặt rủi ro chưa được xử lý đầy đủ.

**Gọi mọi thay đổi là backward-compatible.** Thêm một field response có thể làm lộ dữ liệu; thêm một field request có thể mở quyền ghi. Tương thích cú pháp chưa nói hết tác động bảo mật.

**Đặt sunset header nhưng không có gate.** Header thông báo kế hoạch; cơ chế routing/lifecycle mới ngăn dispatch sau deadline.

**Tin rằng client chính thức đã nâng cấp thì v1 không còn ai dùng.** Consumer đối tác, mobile cũ và job định kỳ có thể có lịch nâng cấp khác. Cần usage có định danh và kế hoạch xử lý phần chưa nhận diện.

**Dùng `/latest` như một version cố định.** Client có thể nhận contract mới sau một deployment dù không đổi request. Nếu route này tồn tại, phải công bố rõ cam kết và không dùng nó để bỏ kiểm tra compatibility.

**Để rollback khôi phục mọi route cũ.** Khôi phục phần mềm phải giữ trạng thái retired hoặc trải qua quyết định mở lại có chủ đích.

**Xem môi trường preview là ngoại lệ bảo mật.** Nếu nó có dữ liệu hoặc kết nối thật, các kiểm soát tương ứng vẫn cần được áp dụng và inventory phải ghi rõ exposure đó.

## 15. Bài tập vận dụng

Một nền tảng đang có API v1 trên host chính, một host mobile cũ và một adapter dành cho đối tác. API v2 đổi cấu trúc khóa học, bổ sung kiểm tra field-level và dự kiến thay v1. Hiện chỉ host chính có thông báo deprecation.

Hãy thiết kế kế hoạch với các đầu ra sau:

1. Inventory liên kết contract, host, route, consumer, owner và policy revision cho cả ba exposure.
2. Ma trận invariant bảo mật phải được giữ trên mọi đường còn phục vụ trong thời gian chuyển đổi.
3. Quy tắc chọn version, hành vi khi thiếu/mâu thuẫn và cách chặn fallback trái policy.
4. Mốc deprecation/sunset cùng cách phát header đúng cú pháp và phạm vi thông báo.
5. Gate retirement, policy request inflight và bằng chứng handler v1 không còn nhận request mới.
6. Một ca rollback, một ca cache và một ca migration request ghi chứng minh không mở lại quyền hoặc lặp tác dụng phụ.

Kết quả cần chứng minh được contract nào còn được phục vụ, ở đâu và dưới bộ kiểm soát nào. API versioning an toàn là quản lý được toàn bộ vòng đời của những đường truy cập đó, từ khi xuất hiện đến khi không còn xử lý nghiệp vụ.
