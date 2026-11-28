# Scope trong OAuth và OpenID Connect

## 1. Scope diễn tả phạm vi truy cập

**Scope** là các giá trị dùng để mô tả phạm vi truy cập mà client yêu cầu và phạm vi của access token được cấp. Authorization server định nghĩa ý nghĩa các giá trị đó trong hệ thống. Client gửi một yêu cầu scope không có nghĩa yêu cầu đã được chấp thuận. [RFC 6749, mục 3.3](https://www.rfc-editor.org/rfc/rfc6749.html#section-3.3).

Giả sử một nền tảng học tập đặt ra các scope sau. Đây là quy ước minh họa, không phải tên scope chuẩn của OAuth:

| Scope | Ý nghĩa do nền tảng định nghĩa |
|---|---|
| `courses.read` | Cho phép client thực hiện chức năng đọc khóa học trong giới hạn chính sách |
| `courses.write` | Cho phép thực hiện chức năng sửa nội dung khóa học |
| `grades.read` | Cho phép thực hiện chức năng đọc điểm |
| `grades.publish` | Cho phép thực hiện chức năng công bố điểm |

Cổng học viên chỉ hiển thị khóa học không cần xin `grades.publish`. Giảng viên có chức năng công bố điểm cũng không có nghĩa mọi ứng dụng mà giảng viên đăng nhập đều nên được cấp scope đó.

Scope giúp tách hai câu hỏi: **người dùng có những quyền gì trong tổ chức** và **ứng dụng này đang được sử dụng phạm vi truy cập nào**. Một lần đăng nhập thành công chưa trả lời đầy đủ cả hai câu hỏi.

## 2. Cú pháp không tự tạo ra quan hệ quyền

Tham số `scope` chứa các chuỗi phân biệt hoa thường, ngăn cách bằng dấu cách; thứ tự không có ý nghĩa. Khi bỏ tham số này, server sử dụng mặc định đã định nghĩa hoặc từ chối theo quy tắc giao thức. [RFC 6749, mục 3.3](https://www.rfc-editor.org/rfc/rfc6749.html#section-3.3).

```text
scope=courses.read grades.read
```

Khi đưa vào URL, giá trị cần được mã hóa đúng, chẳng hạn:

```text
scope=courses.read%20grades.read
```

Các tên dưới đây không nên bị ứng dụng tự suy diễn thành quyền giống nhau:

| Giá trị | Điều cần xác định trong hợp đồng của API |
|---|---|
| `courses.read` và `Courses.Read` | Có phải hai giá trị khác nhau? Không tự đổi chữ hoa thành chữ thường |
| `courses.write` | Có bao gồm đọc không? Chỉ có nếu chính sách định nghĩa như vậy |
| `courses.*` | Dấu `*` có được hỗ trợ không? Không coi là wildcard chỉ vì trông giống mẫu quyền |
| `courses.read,grades.read` | Không coi dấu phẩy là dấu phân cách hai scope |

Ví dụ lỗi triển khai: chương trình kiểm tra xem chuỗi scope có chứa chữ `read` hay không. Token với scope `courses.read.archived` có thể bị nhầm là có `courses.read`. Cách kiểm tra phải dựa trên **phần tử scope chính xác** đã được phân tích theo định dạng của hệ thống.

## 3. Phân biệt scope đăng ký, yêu cầu, được cấp và được thực thi

Một thiết kế IAM dễ kiểm soát cần ghi rõ bốn lớp sau:

| Lớp trong ví dụ nền tảng học tập | Dữ liệu thể hiện |
|---|---|
| Client được cấu hình có thể xin gì | Danh sách được quản trị viên duyệt cho ứng dụng |
| Client đang yêu cầu gì | Tham số `scope` của giao dịch xin quyền |
| Token thực sự được cấp gì | Scope gắn với access token sau quyết định cấp quyền |
| API chấp nhận thao tác nào | Kiểm tra token, scope và chính sách tài nguyên ở phía server |

Nếu scope được cấp khác scope yêu cầu, authorization server phải trả tham số `scope` để client biết phạm vi thực tế. [RFC 6749, mục 3.3](https://www.rfc-editor.org/rfc/rfc6749.html#section-3.3).

Ví dụ một giao dịch chỉ dành cho API khóa học:

```text
Client yêu cầu: courses.read courses.write
Token được cấp: courses.read
```

Phản hồi token minh họa:

```json
{
  "access_token": "<access-token>",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "courses.read"
}
```

Client cần xử lý trường hợp thiếu quyền sửa: ẩn hoặc vô hiệu hóa chức năng tương ứng và giải thích phù hợp cho người dùng. Tuy nhiên, quyết định của giao diện chỉ hỗ trợ trải nghiệm; API vẫn phải kiểm tra khi có yêu cầu sửa được gửi trực tiếp.

Trong thiết kế minh họa này, việc cấp scope xét cả nhu cầu chức năng, cấu hình client, người dùng và chính sách. Không triển khai quy tắc “client gửi tên quyền nào thì token có quyền đó”. Màn hình đồng ý cũng không được biến thành cách cấp thêm quyền nghiệp vụ mà người dùng vốn không có.

## 4. Scope khác audience và khác role

**Audience hoặc tài nguyên đích** trả lời token dành cho dịch vụ nào; **scope** diễn tả phạm vi truy cập được yêu cầu ở dịch vụ đó. Khi hệ thống hỗ trợ Resource Indicators, client có thể dùng tham số `resource` để chỉ tài nguyên đích. [RFC 8707, mục 1–2](https://www.rfc-editor.org/rfc/rfc8707.html#section-2).

Ví dụ:

```text
Tài nguyên đích: https://api.learning.example.com
Scope: courses.read
```

Một API tài chính không được chấp nhận token này chỉ vì nó cũng sử dụng tên scope `courses.read` trong một cấu hình nào đó. Cần kiểm tra token có dành cho chính API tiếp nhận hay không, rồi mới diễn giải quyền theo hợp đồng của API.

Role thể hiện vai trò như `LEARNER`, `INSTRUCTOR` hoặc `ACADEMIC_ADMIN` trong chính sách của nền tảng. Trong một JWT access token, scope và các thuộc tính phân quyền khác như role có thể là những claim riêng, không phải một loại dữ liệu duy nhất. [RFC 9068, mục 2.2.3](https://www.rfc-editor.org/rfc/rfc9068.html#section-2.2.3).

Xét ba trường hợp của cùng một nền tảng:

- Giảng viên dùng ứng dụng đọc khóa học: role có thể là `INSTRUCTOR`, nhưng token của ứng dụng chỉ có `courses.read`.
- Ứng dụng có token với `grades.publish`: API vẫn phải xác định chủ thể có được công bố điểm của lớp cụ thể hay không.
- Tác vụ đồng bộ chạy bằng danh tính workload: scope của tác vụ không phải bằng chứng rằng một giảng viên đang hiện diện.

Việc ánh xạ role sang scope có thể được thiết kế trong IAM, nhưng phải là quy tắc được xác định và kiểm soát. Không tự suy ra rằng scope tên `admin` mang cùng ý nghĩa ở mọi API.

## 5. API lấy scope từ đâu và kiểm tra như thế nào?

Một số hệ thống dùng JWT access token có claim `scope`. Với profile RFC 9068, các scope trong claim này phải có ý nghĩa đối với tài nguyên được chỉ ra ở `aud`. API cần xác minh token theo profile trước khi tin các claim. [RFC 9068, mục 2.2.3 và 4](https://www.rfc-editor.org/rfc/rfc9068.html#section-4).

Không phải access token nào cũng là JWT để API tự giải mã. Với cơ chế introspection được hỗ trợ, resource server hỏi authorization server về trạng thái và metadata của token; phản hồi có thể chứa `active`, `scope` và các trường liên quan. Phải dùng kết quả từ kênh introspection đã xác thực, không tin một JSON tự gửi từ client. [RFC 7662, mục 2](https://www.rfc-editor.org/rfc/rfc7662.html#section-2).

Mã giả sau mô tả chính sách của API khóa học, không phải API của một thư viện cụ thể:

```text
context = accessTokenVerifier.verify(
    request.authorization,
    expectedIssuer,
    expectedAudience
)

grantedScopes = context.trustedScopes

if "courses.read" not in grantedScopes:
    rejectInsufficientScope()

course = courseRepository.load(courseId)

if not policy.canReadCourse(context.subject, course, context.tenant):
    rejectResourceAccess()

return course.allowedViewFor(context.subject)
```

Ở đây, kiểm tra scope chưa đủ để kết luận được đọc mọi khóa học. API còn xét khóa học có thuộc tenant phù hợp và người dùng có thuộc nhóm được xem hay không. Hai người dùng cùng scope `courses.read` vẫn có thể nhận kết quả khác nhau cho cùng một mã khóa học.

Không nhận một header tự khai như `X-Scopes: grades.publish` để thay thế phạm vi của token đã được xác minh. Một service trung gian muốn truyền ngữ cảnh quyền cho service khác cần có cơ chế tin cậy được thiết kế rõ, không chỉ đổi vị trí của chuỗi dữ liệu.

## 6. Scope OIDC còn dùng để yêu cầu thông tin danh tính

OIDC yêu cầu scope `openid`; các scope như `profile` và `email` yêu cầu những nhóm claim danh tính. `offline_access` yêu cầu khả năng lấy refresh token để truy cập khi người dùng không hiện diện, với điều kiện cấp quyền tương ứng. [OpenID Connect Core, mục 3.1.2.1, 5.4 và 11](https://openid.net/specs/openid-connect-core-1_0.html#ScopeClaims).

| Scope | Mục đích |
|---|---|
| `openid` | Xác định yêu cầu OpenID Connect |
| `profile` | Yêu cầu nhóm thông tin hồ sơ |
| `email` | Yêu cầu claim `email` và `email_verified` |
| `offline_access` | Yêu cầu truy cập khi người dùng không hiện diện theo điều kiện OIDC |

Các claim được yêu cầu không được bảo đảm luôn đầy đủ. `offline_access` cũng không bảo đảm luôn được cấp refresh token; OIDC quy định điều kiện consent và luồng có trả authorization code. Refresh token còn có thể được cấp trong các ngữ cảnh khác. [OpenID Connect Core, mục 5.4 và 11](https://openid.net/specs/openid-connect-core-1_0.html#OfflineAccess).

Ví dụ cấu hình nhu cầu của cổng học tập:

```text
openid profile email courses.read
```

Ba giá trị đầu phục vụ chức năng đăng nhập và thông tin danh tính theo OIDC. `courses.read` là quyền API do nền tảng minh họa định nghĩa. Scope `email` không cho phép gửi email hàng loạt, sửa email của mọi tài khoản hoặc đọc điểm thi. Không dùng việc nhận được email đã xác minh để suy ra quyền quản trị.

## 7. Thiếu scope khác với token không hợp lệ

Theo cơ chế Bearer, `insufficient_scope` thể hiện token thiếu phạm vi cần thiết, thường đi với HTTP 403; resource server có thể thông báo scope cần thiết. `invalid_token` thường đi với HTTP 401 cho token không hợp lệ, chẳng hạn đã hết hạn. [RFC 6750, mục 3.1](https://www.rfc-editor.org/rfc/rfc6750.html#section-3.1).

Ví dụ phản hồi khi thao tác công bố điểm đòi hỏi một scope mà token không có:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="grades.publish"
```

Client không nên liên tục refresh token rồi gửi lại cùng yêu cầu nếu phạm vi cấp quyền vẫn không đổi. Với ứng dụng minh họa, cách xử lý là xác định chức năng có thực sự cần thiết, kiểm tra ứng dụng được phép xin scope đó và bắt đầu quy trình xin quyền phù hợp nếu chính sách cho phép.

Ngược lại, nếu người dùng không có quyền công bố điểm của lớp đó, xin lại cùng scope không sửa được vấn đề. Đây là lý do cần phân biệt lỗi về token, lỗi về phạm vi của token và quyết định chính sách trên tài nguyên cụ thể.

## 8. Thiết kế scope theo nguyên tắc ít quyền nhất

Quyền của access token nên được giới hạn ở mức tối thiểu cần cho ứng dụng hoặc tình huống sử dụng. Việc giới hạn này cũng giúp giảm hậu quả khi token bị lộ. [RFC 9700, mục 2.3](https://www.rfc-editor.org/rfc/rfc9700.html#section-2.3).

Với nền tảng học tập, có thể thiết kế danh mục scope theo các quyết định cụ thể:

| Quyết định | Ví dụ áp dụng |
|---|---|
| Tách đọc và sửa khi nhu cầu khác nhau | Cổng học viên không xin `courses.write` |
| Tách thao tác nhạy cảm | Công bố điểm có `grades.publish`, không gộp vào một scope `all` |
| Giữ tên ổn định, mô tả rõ | Nêu rõ `grades.read` vẫn chịu chính sách lớp và tenant |
| Có người chịu trách nhiệm | Nhóm quản lý điểm phê duyệt ý nghĩa và thay đổi của `grades.publish` |
| Rà soát khi chức năng thay đổi | Bỏ yêu cầu quyền xuất dữ liệu nếu ứng dụng đã ngừng chức năng xuất |

Tránh vừa tạo một scope cho mọi bản ghi, vừa bỏ hết kiểm tra đối tượng ở API. Ví dụ nền tảng có hàng triệu lớp học không nhất thiết cần hàng triệu tên scope để phân biệt lớp; có thể giữ scope theo chức năng rồi xét lớp cụ thể bằng chính sách tài nguyên.

Khi một nhân viên chuyển bộ phận, cần xem hiệu lực quyền và token đang tồn tại theo thiết kế của hệ thống. Không giả định việc sửa role tự sửa nội dung mọi JWT access token đã phát hành. Thời hạn token, cách kiểm tra quyền hiện tại và cơ chế thu hồi phải được phối hợp với yêu cầu của chức năng.

## 9. Tự kiểm tra bằng tình huống

Mai là giảng viên lớp A. Ứng dụng di động của Mai có token dành cho API học tập với scope `courses.read grades.read`.

1. Mai có thể dùng token đó công bố điểm lớp A không? Không, token không có `grades.publish`; quyền nghiệp vụ của Mai không tự thêm scope vào token.
2. Token có `grades.read` thì đọc được điểm của lớp B không? Chưa thể kết luận; API phải kiểm tra quyền của Mai với lớp B.
3. Đổi chuỗi scope trong bộ nhớ ứng dụng có tăng quyền không? Không; API phải dựa trên token hoặc metadata tin cậy đã xác minh.
4. Xin thêm scope `email` có khắc phục lỗi công bố điểm không? Không; scope đó phục vụ thông tin danh tính theo OIDC, không phải quyền công bố điểm của nền tảng.
5. Thay token dành cho API học tập bằng token dành cho một API khác có được không? API phải từ chối token không dành cho nó, dù tên scope trông giống nhau.

Khi phân tích một yêu cầu truy cập, hãy lần lượt xác định token có hợp lệ và đúng tài nguyên đích không, scope thực tế có đáp ứng chức năng không, rồi chính sách có cho phép thao tác trên đúng đối tượng không. Cách kiểm tra này nối phạm vi OAuth/OIDC với phân quyền nghiệp vụ trong IAM.
