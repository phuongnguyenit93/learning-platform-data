# User directory

## 1. User directory là gì?

**User directory** là danh bạ có cấu trúc để lưu, tra cứu và quản lý những bản ghi đại diện cho người dùng trong một phạm vi danh tính. Nó cung cấp thông tin như định danh tài khoản, tên hiển thị, trạng thái, liên kết danh tính bên ngoài, thuộc tính tổ chức và những quan hệ mà hệ thống được thiết kế quản lý.

Ví dụ, một ứng dụng cần trả lời:

~~~text
Tài khoản U-81 là ai trong hệ thống?
Danh tính vừa đăng nhập ánh xạ đến tài khoản nào?
Tài khoản còn được sử dụng không?
Tên hiển thị hiện tại là gì?
Người dùng thuộc nhóm hoặc tổ chức nào?
Thông tin này do nguồn nào quản lý?
~~~

User directory cung cấp một phần dữ liệu để trả lời các câu hỏi đó. Tuy nhiên, tìm thấy một bản ghi không chứng minh người gọi sở hữu tài khoản, và tài khoản tồn tại không tự trao quyền trên mọi tài nguyên.

Trong nền tảng IAM, directory liên quan đến xác thực, SSO, cấp phát tài khoản, vòng đời danh tính, nhóm, RBAC/ABAC và kiểm toán. Một directory được thiết kế rõ giúp các ứng dụng liên kết dữ liệu với cùng một danh tính mà không phụ thuộc vào tên hoặc email có thể thay đổi.

Sau bài này, người học có thể:

- Phân biệt directory, identity store, credential store, identity provider và kho quyền.
- Thiết kế bản ghi người dùng với định danh ổn định và nguồn thuộc tính rõ ràng.
- Ánh xạ danh tính ngoài vào tài khoản nội bộ mà không tự gộp tài khoản theo email.
- Mô hình hóa trạng thái tài khoản, membership tenant và group membership.
- Giải thích luồng tra cứu khi đăng nhập và luồng cấp phát khi dữ liệu thay đổi.
- Nhận diện rủi ro từ tìm kiếm, đồng bộ, xóa tài khoản và dữ liệu directory bị cũ.

## 2. Vị trí của directory trong kiến trúc IAM

### 2.1. Các trách nhiệm có thể cùng nằm trong một sản phẩm

| Thành phần hoặc trách nhiệm | Câu hỏi chính |
| --- | --- |
| User directory | Bản ghi tài khoản và thuộc tính được quản lý là gì? |
| Identity store | Những danh tính và dữ liệu liên quan được lưu ở đâu, theo mô hình nào? |
| Credential store | Bằng chứng xác thực hoặc dữ liệu kiểm chứng được bảo vệ như thế nào? |
| Identity provider — IdP | Ai đang đăng nhập và hệ thống phát biểu điều gì về lần đăng nhập đó? |
| Provisioning service | Tài khoản và quan hệ cần được tạo, sửa, vô hiệu hóa ở đâu? |
| Authorization service/store | Chủ thể được thực hiện hành động nào, trên phạm vi nào? |
| Business database | Đơn hàng, dự án, hồ sơ nghiệp vụ và quan hệ sở hữu nằm ở đâu? |

Đây là cách phân biệt trách nhiệm logic. Một sản phẩm có thể cung cấp nhiều trách nhiệm, hoặc một ứng dụng nhỏ có thể triển khai chúng trong cùng cơ sở dữ liệu.

Điều quan trọng là biết ai có quyền ghi dữ liệu nào và thành phần nào thực sự kiểm tra điều kiện. Không nên dựa vào tên sản phẩm để kết luận rằng mọi yêu cầu IAM đã được đáp ứng.

### 2.2. Directory có thể chứa dữ liệu liên quan đến xác thực

Một số directory lưu thông tin credential hoặc hỗ trợ giao thức xác thực. Một số directory khác chỉ lưu hồ sơ và liên kết đến IdP bên ngoài.

Vì vậy, không nên phát biểu rằng directory luôn chỉ chứa hồ sơ, cũng không nên giả định mọi directory tự cung cấp OAuth/OIDC, MFA hoặc quản lý phiên.

API trả hồ sơ người dùng không được trả password, dữ liệu kiểm chứng password, secret MFA, recovery code hay credential dịch vụ chỉ vì chúng cùng được lưu trong một sản phẩm directory.

### 2.3. Sơ đồ trách nhiệm minh họa

~~~mermaid
flowchart LR
    A[Nguồn nhân sự hoặc quản trị tài khoản] --> B[Provisioning và đối soát]
    B --> C[User directory]
    C --> D[IdP hoặc thành phần ánh xạ danh tính]
    D --> E[Ứng dụng nhận danh tính đã xác minh]
    C --> F[Thuộc tính và quan hệ được phép đọc]
    F --> G[Policy phân quyền]
    E --> G
    G --> H[Tài nguyên nghiệp vụ]
~~~

Sơ đồ mô tả một cách tổ chức có thể có. Không phải mọi lần đăng nhập đều cần gọi trực tiếp directory, và không phải mọi thuộc tính quyền đều thuộc directory.

## 3. Directory entry không đồng nghĩa với một con người duy nhất

### 3.1. Phân biệt người thật, tài khoản và danh tính bên ngoài

Một con người có thể có:

~~~text
Một tài khoản làm việc thông thường.
Một tài khoản quản trị riêng.
Một tài khoản cộng tác viên trong hệ thống khác.
Nhiều danh tính liên kết dùng để đăng nhập.
~~~

Ngược lại, một directory có thể lưu nhiều loại entry ngoài người dùng, chẳng hạn nhóm hoặc các đối tượng phục vụ quản trị. Workload identity cũng có thể nằm trong một kho danh tính liên quan nhưng cần lifecycle và chính sách riêng.

Không dùng một tài khoản người dùng chung cho nhiều người chỉ để giảm số bản ghi. Nếu nhiều người dùng chung credential, việc xác định ai thực hiện thao tác và thu hồi quyền theo từng người trở nên khó kiểm soát.

### 3.2. Tách lớp tài khoản khỏi quan hệ tổ chức

Ví dụ:

~~~text
Person reference P-17
    -> tài khoản thông thường U-81
    -> tài khoản quản trị U-92

U-81
    -> membership tenant T-A
    -> membership tenant T-B
~~~

`Person reference` là tùy chọn nếu hệ thống có nhu cầu quản lý quan hệ con người–tài khoản. Không phải mọi ứng dụng đều cần hoặc được phép thu thập thêm dữ liệu để liên kết con người xuyên hệ thống.

Ngay cả khi hai tài khoản cùng thuộc một người, quyền của chúng không nên tự động gộp. Một tài khoản quản trị tách biệt có thể được yêu cầu dùng credential và quy trình truy cập khác.

## 4. Định danh ổn định là nền tảng của directory

### 4.1. Chọn khóa liên kết không phụ thuộc nhãn hiển thị

Một bản ghi người dùng giả định:

~~~json
{
  "userId": "U-81",
  "loginName": "alice",
  "displayName": "Nguyễn An",
  "primaryEmail": "an@example.test",
  "accountState": "ACTIVE",
  "version": 7
}
~~~

`U-81` chỉ là ký hiệu minh họa cho một ID nội bộ bất biến. Ứng dụng thật có thể dùng UUID hoặc định danh khác có hợp đồng tương ứng.

| Trường | Mục đích | Có phù hợp làm khóa liên kết lâu dài không? |
| --- | --- | --- |
| `userId` bất biến | Tham chiếu tài khoản nội bộ | Phù hợp nếu không bị tái cấp ngoài hợp đồng |
| `displayName` | Hiển thị | Không; có thể trùng và thay đổi |
| `loginName` | Nhập khi đăng nhập hoặc tìm kiếm | Phụ thuộc namespace và chính sách đổi/tái sử dụng |
| Email | Liên hệ hoặc một cách đăng nhập | Không nên mặc định là khóa bất biến |
| Employee number | Liên kết nguồn nhân sự | Phụ thuộc nguồn, namespace và chính sách tái sử dụng |
| Directory path hoặc DN | Địa chỉ/vị trí entry trong directory tương ứng | Không nên mặc định là định danh bất biến |

Nếu Alice đổi email, quan hệ sở hữu dự án vẫn nên trỏ đến cùng `userId`. Không chuyển dự án cho người mới chỉ vì người mới được cấp lại địa chỉ email cũ.

### 4.2. Định danh luôn có phạm vi

Hai directory khác nhau có thể cùng có `userId = 1001`. Khi tích hợp, có thể cần khóa:

~~~text
(directoryId, sourceUserId)
~~~

Ứng dụng cũng có thể ánh xạ khóa nguồn đó sang một `internalUserId` duy nhất của mình.

Tính duy nhất phải được xác định trong namespace cụ thể. Không dùng `username = admin` để nhận diện cùng một tài khoản giữa mọi hệ thống.

### 4.3. Danh tính OIDC cần giữ đúng cặp issuer–subject

Trong OpenID Connect, `iss` và `sub` được dùng cùng nhau để định danh ổn định người dùng trong phạm vi issuer. Email, tên và những nhãn hiển thị không có cùng bảo đảm về tính duy nhất và ổn định. [Nguồn: OpenID Connect Core, mục 5.7](https://openid.net/specs/openid-connect-core-1_0.html#ClaimStability).

Một ánh xạ nội bộ có thể là:

~~~text
Trusted provider registry:
    providerId -> issuer và cấu hình xác minh

External identity mapping:
    (providerId, externalSubject) -> internalUserId
~~~

`providerId` phải được giải quyết từ quan hệ tin cậy của server sau khi xác minh giao thức, không phải một giá trị client tùy ý khai.

Không tự lowercase `sub` hoặc biến đổi issuer rồi coi kết quả chắc chắn tương đương. Cách so sánh và lưu khóa phải phù hợp hợp đồng của nguồn.

Với subject dạng pairwise, cùng một người có thể có subject khác giữa các ngữ cảnh client tương ứng. Nếu cần liên kết tài khoản, phải có bằng chứng và quy trình thích hợp, không đoán bằng email.

## 5. LDAP, directory tree và entry

### 5.1. Directory không bắt buộc phải dùng LDAP

User directory là một khái niệm chức năng. Nó có thể được triển khai bằng dịch vụ directory hỗ trợ LDAP, một dịch vụ đám mây, API chuyên dụng hoặc một mô hình dữ liệu trong ứng dụng.

LDAP mô tả giao thức và mô hình directory liên quan; nó không phải tên gọi chung cho mọi hệ thống quản lý người dùng.

Theo mô hình LDAP, directory entry là đơn vị thông tin có tên, chứa các thuộc tính. Các entry có thể được tổ chức trong Directory Information Tree — DIT; schema và object class quy định cấu trúc dữ liệu phù hợp. [Nguồn: RFC 4512, mục 2 và 4](https://www.rfc-editor.org/rfc/rfc4512.html#section-2).

### 5.2. Ví dụ cây tổ chức

~~~text
dc=example,dc=test
├── ou=people
│   ├── uid=alice
│   └── uid=bob
└── ou=groups
    ├── cn=engineering
    └── cn=helpdesk
~~~

Đây chỉ là bố cục minh họa. Tên thuộc tính, schema, cách đặt nhánh và cơ chế quản lý nhóm cần tuân theo directory thật.

Một DN như:

~~~text
uid=alice,ou=people,dc=example,dc=test
~~~

mô tả tên/vị trí entry trong mô hình đó. Không nên suy ra rằng thuộc nhánh `ou=people` hoặc `ou=engineering` tự trao quyền nghiệp vụ tương ứng.

### 5.3. Đổi tên hoặc chuyển nhánh không được làm mất liên kết

RFC 4530 giải thích rằng DN không phải định danh ổn định và định nghĩa `entryUUID` do server cấp để phân biệt đối tượng hoặc tìm lại đối tượng sau khi đổi tên. [Nguồn: RFC 4530, mục 1](https://www.rfc-editor.org/rfc/rfc4530.html#section-1).

Nếu directory cung cấp thuộc tính ổn định phù hợp, ứng dụng nên dùng hợp đồng đó để duy trì liên kết thay vì bám vào DN có thể đổi. Không mặc định mọi sản phẩm đều cung cấp cùng một thuộc tính hoặc cùng cách biểu diễn.

Khi đồng bộ, cần phân biệt:

~~~text
Cùng đối tượng, đổi tên/DN.
Đối tượng cũ bị xóa, đối tượng mới nhận lại tên/DN đó.
~~~

Hai tình huống có thể giống nhau nếu chỉ nhìn chuỗi tên, nhưng phải có kết quả liên kết khác nhau.

## 6. Schema của một user directory

### 6.1. Nhóm dữ liệu cần phân biệt

Một mô hình user record có thể được chia thành:

| Nhóm | Ví dụ | Điều cần xác định |
| --- | --- | --- |
| Định danh | `userId`, khóa nguồn | Phạm vi duy nhất, bất biến, không tái cấp |
| Hồ sơ | Tên, email liên hệ, ngôn ngữ | Ai được sửa và dùng để làm gì? |
| Trạng thái tài khoản | `ACTIVE`, `SUSPENDED` | Ý nghĩa và hệ thống nào phải thực thi |
| Liên kết bên ngoài | Provider và subject | Cách xác minh, tạo, hủy liên kết |
| Quan hệ tổ chức | Department, manager | Nguồn dữ liệu và độ mới |
| Quan hệ truy cập | Group, membership tenant | Phạm vi, trạng thái, nguồn có thẩm quyền |
| Metadata vận hành | Version, thời điểm cập nhật, nguồn đồng bộ | Xử lý đồng thời và truy vết |
| Dữ liệu xác thực | Tham chiếu credential hoặc dữ liệu được bảo vệ | Quyền truy cập và cơ chế chuyên biệt |

Bảng không yêu cầu mọi user record phải nhét tất cả dữ liệu vào một document. Các quan hệ có thể nằm ở bảng hoặc dịch vụ riêng.

### 6.2. Không biến một JSON hồ sơ thành kho quyền tùy ý

Một trường hồ sơ tự sửa như:

~~~json
{
  "displayName": "Alice",
  "jobTitle": "Administrator"
}
~~~

không được tự biến thành role quản trị.

Nếu muốn ánh xạ thuộc tính tổ chức sang quyền, policy cần chỉ rõ nguồn thuộc tính, giá trị hợp lệ, phạm vi và cách thay đổi có hiệu lực. Không cấp quyền vì một chuỗi hiển thị “trông giống” tên role.

Tương tự, endpoint sửa hồ sơ cá nhân không được bind mọi field từ request rồi cho người dùng tự đổi:

~~~text
accountState
tenantMemberships
privilegedGroups
externalIdentityLinks
sourceOwnership
~~~

Những thay đổi đó cần use case và quyền riêng.

### 6.3. Có hợp đồng ghi cho từng nhóm thuộc tính

Một ví dụ:

| Dữ liệu | Nguồn ghi được chấp nhận trong ví dụ |
| --- | --- |
| Employee number | Connector nhân sự đã xác minh |
| Tên hiển thị | Người dùng hoặc quản trị viên theo chính sách sản phẩm |
| Trạng thái tài khoản | Quy trình quản trị danh tính |
| Nhóm đặc quyền | Quy trình cấp quyền có phê duyệt tương ứng |
| Email liên hệ | Luồng thay đổi và xác minh theo chính sách |
| Provider/subject liên kết | Quy trình liên kết danh tính có xác minh |

Nếu HR và quản trị viên cùng ghi một thuộc tính, cần định nghĩa nguồn nào thắng và cách xử lý ngoại lệ. Quy tắc “lần ghi đến sau thắng” có thể làm mất một lệnh vô hiệu hóa hoặc quyền quản trị vừa điều chỉnh.

## 7. Bản ghi người dùng, group và tenant membership

### 7.1. Tài khoản hoạt động chưa đủ để vào một tenant

~~~text
User U-81:
    accountState = ACTIVE

Membership U-81 trong T-A:
    state = ACTIVE

Membership U-81 trong T-B:
    state = REVOKED
~~~

Với chính sách minh họa, U-81 có thể được xét tiếp quyền trong T-A nhưng không trong T-B. Không vô hiệu hóa toàn bộ tài khoản chỉ để biểu diễn việc rời một tenant nếu nghiệp vụ vẫn cần tài khoản ở tenant khác.

Ngược lại, nếu tài khoản bị đình chỉ toàn cục theo hợp đồng ứng dụng, membership active không được dùng làm cách vượt qua việc đình chỉ.

### 7.2. Group membership là dữ liệu để policy diễn giải

Một directory có thể quản lý nhóm phòng ban, nhóm phân phối thư, nhóm đồng bộ hoặc nhóm được dùng để cấp quyền. Không phải mọi nhóm đều là role.

Ví dụ ánh xạ có chủ đích:

~~~text
groupId G-17 trong directory D-1
    -> permission REPORT_READ trong tenant T-A
~~~

Không nên viết:

~~~text
Tên nhóm chứa chữ "admin"
    -> quyền quản trị toàn nền tảng
~~~

Tên nhóm có thể đổi hoặc trùng giữa các directory. Những nhóm được phép cấp quyền cần định danh và phạm vi rõ ràng.

Nếu hệ thống hỗ trợ nhóm lồng nhau hoặc nhóm tính động, cần biết cách giải quyết membership, giới hạn và thời điểm cập nhật. Không giả định kết quả “member of” ở mọi sản phẩm đều có cùng ngữ nghĩa.

### 7.3. OU, group, role và tenant không phải một khái niệm

Một OU có thể phục vụ tổ chức hoặc quản trị directory. Một group có thể phục vụ nhiều mục đích. Một role mô tả tập quyền trong policy. Một tenant là ranh giới khách hàng hoặc tổ chức theo ứng dụng.

Các khái niệm có thể liên hệ với nhau nhưng không được đồng nhất chỉ vì cùng mang tên “Engineering” hoặc “An Phú”.

## 8. SCIM như một cách trao đổi user record

SCIM cung cấp schema cho User, Group và các thuộc tính chung để trao đổi dữ liệu quản lý danh tính. Trong SCIM, `id` do service provider cấp có hợp đồng ổn định; `externalId` phục vụ liên kết do bên cấp phát quản lý, không phải bản sao mặc định của `id`. [Nguồn: RFC 7643, mục 3.1 và 4.1](https://www.rfc-editor.org/rfc/rfc7643.html#section-3.1).

Ví dụ rút gọn có chủ đích:

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User"
  ],
  "id": "user-81",
  "externalId": "hr-record-17",
  "userName": "alice@example.test",
  "displayName": "Nguyễn An",
  "active": true
}
~~~

Đây là dữ liệu minh họa, không phải bản ghi trích từ một directory thật.

`active` cần được diễn giải theo hợp đồng service provider và đường thực thi của ứng dụng. Không suy ra rằng một lần cập nhật trường đó tự thu hồi mọi phiên hoặc token ở mọi hệ thống.

SCIM phục vụ trao đổi/quản lý resource. Sự hiện diện của SCIM endpoint không tự cung cấp một luồng đăng nhập SSO; xác thực người dùng và cấp phát user record cần được thiết kế với trách nhiệm tương ứng.

## 9. Luồng đăng nhập có sử dụng directory

### 9.1. Xác thực rồi ánh xạ tài khoản

Một ứng dụng dùng IdP bên ngoài có thể thực hiện:

~~~text
1. Hoàn tất luồng xác thực và kiểm tra thông điệp theo giao thức.
2. Giải quyết provider từ cấu hình tin cậy.
3. Lấy subject đã được xác minh.
4. Tra liên kết provider + subject trong user directory.
5. Kiểm tra trạng thái tài khoản nội bộ.
6. Kiểm tra membership cho tenant được chọn.
7. Tạo ngữ cảnh danh tính ứng dụng.
8. Xét quyền theo hành động và tài nguyên.
~~~

Tra cứu directory là một bước trong luồng, không phải bằng chứng xác thực độc lập. Việc tìm thấy email trong danh bạ không cho phép server kết luận rằng người gọi sở hữu email đó.

Ứng dụng cũng cần có quy trình cho trường hợp không tìm thấy liên kết. Có thể từ chối, yêu cầu quản trị viên cấp phát hoặc chạy luồng just-in-time provisioning đã được cấu hình. Không tự tạo liên kết đến tài khoản có cùng email rồi kế thừa quyền.

### 9.2. Liên kết danh tính mới cần một use case riêng

Ví dụ, U-81 đã có một phương thức đăng nhập và muốn thêm provider khác. Luồng liên kết cần chứng minh người thực hiện có quyền quản lý U-81 và kiểm soát danh tính mới theo chính sách sản phẩm.

Một thông điệp từ provider hợp lệ vẫn chưa đủ để gắn nó vào tài khoản nội bộ do người gọi chỉ định tùy ý.

Những thao tác cần quản lý rõ:

~~~text
Tạo liên kết.
Vô hiệu hóa hoặc xóa liên kết.
Thay đổi provider có thẩm quyền.
Khôi phục quyền truy cập.
Xử lý một subject nguồn bị xóa rồi tạo lại.
~~~

Audit nên chỉ ra ai thực hiện và bằng chứng/luồng nào cho phép thay đổi. Không đưa toàn bộ token hoặc credential vào log.

## 10. Ví dụ Java: giải quyết tài khoản và membership

Ví dụ Java 17 dưới đây giả định danh tính ngoài đã được xác thực. `providerId` là định danh cấu hình server, không phải issuer tùy ý từ request.

`UserDirectory` có hợp đồng tra chính xác một liên kết còn được chấp nhận bằng provider và subject. Không tìm theo email làm dự phòng.

~~~java
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;

final class DirectoryIdentityResolver {
    enum AccountState {
        PENDING, ACTIVE, SUSPENDED, CLOSED
    }

    enum MembershipState {
        INVITED, ACTIVE, REVOKED
    }

    record VerifiedExternalIdentity(
        String providerId,
        String externalSubject
    ) {
        VerifiedExternalIdentity {
            Objects.requireNonNull(providerId);
            Objects.requireNonNull(externalSubject);
        }
    }

    record DirectoryUser(
        UUID userId,
        String displayName,
        AccountState state,
        long version
    ) {
        DirectoryUser {
            Objects.requireNonNull(userId);
            Objects.requireNonNull(displayName);
            Objects.requireNonNull(state);
        }
    }

    record Membership(
        UUID tenantId,
        UUID userId,
        MembershipState state,
        long version
    ) {
        Membership {
            Objects.requireNonNull(tenantId);
            Objects.requireNonNull(userId);
            Objects.requireNonNull(state);
        }
    }

    record ApplicationIdentity(
        UUID userId,
        UUID tenantId,
        String displayName,
        long directoryVersion,
        long membershipVersion
    ) {}

    interface UserDirectory {
        Optional<DirectoryUser> findByExternalIdentity(
            VerifiedExternalIdentity identity
        );
    }

    interface MembershipStore {
        Optional<Membership> find(UUID tenantId, UUID userId);
    }

    static final class Denied extends RuntimeException {
        Denied(String reason) {
            super(reason);
        }
    }

    private final UserDirectory directory;
    private final MembershipStore memberships;

    DirectoryIdentityResolver(
        UserDirectory directory,
        MembershipStore memberships
    ) {
        this.directory = Objects.requireNonNull(directory);
        this.memberships = Objects.requireNonNull(memberships);
    }

    ApplicationIdentity resolve(
        VerifiedExternalIdentity identity,
        UUID requestedTenantId
    ) {
        if (identity == null || requestedTenantId == null) {
            throw new Denied("MISSING_CONTEXT");
        }

        DirectoryUser user = directory
            .findByExternalIdentity(identity)
            .orElseThrow(() -> new Denied("ACCOUNT_UNAVAILABLE"));

        if (user.state() != AccountState.ACTIVE) {
            throw new Denied("ACCOUNT_UNAVAILABLE");
        }

        Membership membership = memberships
            .find(requestedTenantId, user.userId())
            .orElseThrow(() -> new Denied("NO_ACTIVE_MEMBERSHIP"));

        if (!requestedTenantId.equals(membership.tenantId())
                || !user.userId().equals(membership.userId())
                || membership.state() != MembershipState.ACTIVE) {
            throw new Denied("NO_ACTIVE_MEMBERSHIP");
        }

        return new ApplicationIdentity(
            user.userId(),
            membership.tenantId(),
            user.displayName(),
            user.version(),
            membership.version()
        );
    }
}
~~~

Kết quả `ApplicationIdentity` cho biết tài khoản nội bộ và tenant đã được giải quyết theo dữ liệu đầu vào. Nó chưa chứa kết luận rằng người dùng được sửa hay xóa một tài nguyên nghiệp vụ.

Một deployment có thể còn yêu cầu token ràng buộc tenant, tenant đang hoạt động, loại tài khoản phù hợp hoặc xác thực gần đây. Các điều kiện đó phải được kiểm tra trong luồng tương ứng; chúng không được tự suy ra từ ví dụ.

Tên kiểu `VerifiedExternalIdentity` không tự xác minh dữ liệu. Đường tạo giá trị này phải nằm sau bước kiểm tra giao thức và quan hệ tin cậy.

Nếu directory timeout, không nên coi đó là “không có tài khoản” rồi tạo tài khoản mới. Lỗi hạ tầng và kết quả tra cứu không tồn tại là hai trạng thái khác nhau.

Ví dụ dùng snapshot. Nó không tự bảo đảm thu hồi tức thì khi trạng thái thay đổi sau lúc đọc; kiểm tra độ mới và nhất quán cần được thiết kế theo hành động.

## 11. Mô hình dữ liệu SQL minh họa

### 11.1. Tách tài khoản, liên kết ngoài và membership

Một mô hình nội bộ tối giản:

~~~sql
CREATE TABLE directory_users (
    user_id VARCHAR(64) PRIMARY KEY,
    display_name VARCHAR(200) NOT NULL,
    account_state VARCHAR(16) NOT NULL,
    version BIGINT NOT NULL
);

CREATE TABLE external_identity_links (
    provider_id VARCHAR(64) NOT NULL,
    external_subject VARCHAR(255) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    link_state VARCHAR(16) NOT NULL,
    PRIMARY KEY (provider_id, external_subject),
    FOREIGN KEY (user_id) REFERENCES directory_users(user_id)
);

CREATE TABLE tenant_memberships (
    tenant_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    membership_state VARCHAR(16) NOT NULL,
    version BIGINT NOT NULL,
    PRIMARY KEY (tenant_id, user_id),
    FOREIGN KEY (user_id) REFERENCES directory_users(user_id)
);
~~~

Schema minh họa không bao gồm bảng catalog tenant/provider, role, credential hoặc audit. Kiểu dữ liệu, độ dài, chỉ mục và ràng buộc trạng thái cần điều chỉnh theo hệ thống thật.

Khóa `provider_id + external_subject` ngăn một danh tính nguồn được liên kết đồng thời vào nhiều tài khoản theo mô hình này. Việc xử lý xung đột phải rõ ràng; không ghi đè liên kết để “sửa lỗi đăng nhập”.

Cách so sánh khóa trong cơ sở dữ liệu phải giữ ngữ nghĩa định danh của nguồn. Nếu collation mặc định bỏ qua chữ hoa/thường trong khi subject yêu cầu phân biệt, một ràng buộc unique như trên có thể không thể hiện đúng hợp đồng. Cần chọn kiểu/collation hoặc cách lưu phù hợp.

Không tự thêm `UNIQUE(email)` rồi dùng nó thay cho identity mapping. Tính duy nhất và quyền tái sử dụng email là quyết định riêng của sản phẩm và nguồn.

### 11.2. Tra cứu theo danh tính ngoài đã xác minh

~~~sql
SELECT u.user_id, u.display_name, u.account_state, u.version
FROM external_identity_links l
JOIN directory_users u ON u.user_id = l.user_id
WHERE l.provider_id = :resolved_provider_id
  AND l.external_subject = :verified_subject
  AND l.link_state = 'ENABLED';
~~~

Hai tham số định danh phải đến từ luồng xác thực đã kiểm tra. Truy vấn tìm được tài khoản vẫn cần kiểm tra `account_state` trước khi tạo ngữ cảnh ứng dụng theo policy.

### 11.3. Directory API cũng cần quyền đọc

Ví dụ một API chỉ trả thành viên đang hoạt động của tenant, sau khi chủ thể gọi đã được xác minh quyền liệt kê:

~~~sql
SELECT u.user_id, u.display_name
FROM directory_users u
JOIN tenant_memberships m ON m.user_id = u.user_id
WHERE m.tenant_id = :verified_tenant_id
  AND m.membership_state = 'ACTIVE'
  AND u.account_state = 'ACTIVE';
~~~

Điều kiện join chỉ giới hạn tập người được trả; nó không tự xác minh quyền của người đang gọi API. Bước kiểm tra quyền liệt kê phải có trước đó.

Một API quản trị cần xem tài khoản bị đình chỉ có thể dùng điều kiện khác. Đó là hợp đồng riêng, không phải lý do bỏ mọi giới hạn tenant hoặc trả toàn bộ directory.

## 12. Vòng đời user record

### 12.1. Trạng thái phải có ý nghĩa thực thi

Một mô hình giả định:

~~~text
PENDING -> ACTIVE -> SUSPENDED
                -> CLOSED
~~~

Việc khôi phục từ `SUSPENDED` sang `ACTIVE` hoặc mở lại tài khoản đã đóng phải theo chính sách riêng. Không tự khôi phục chỉ vì một lần đăng nhập mới thành công tại IdP.

| Trạng thái ví dụ | Ý nghĩa trong ứng dụng minh họa |
| --- | --- |
| `PENDING` | Tài khoản chưa được phép dùng chức năng thông thường |
| `ACTIVE` | Có thể tiếp tục xét membership và quyền |
| `SUSPENDED` | Chặn sử dụng theo phạm vi đình chỉ |
| `CLOSED` | Tài khoản đã kết thúc theo quy trình của ứng dụng |

Đây không phải danh sách trạng thái chuẩn cho mọi directory. Một sản phẩm có thể tách tình trạng đăng nhập, hồ sơ, thuê bao và nguồn nhân sự thành các trường khác nhau.

### 12.2. Khóa credential tạm thời khác với kết thúc tài khoản

Một phương thức đăng nhập có thể bị khóa sau nhiều lần thất bại trong khi tài khoản còn tồn tại. Một người cũng có thể có nhiều phương thức đăng nhập.

Cần biết khóa đó áp dụng cho credential, luồng xác thực hay toàn bộ tài khoản. Không dùng một boolean không rõ nghĩa cho mọi tình huống rồi để các ứng dụng diễn giải khác nhau.

Tương tự, tài khoản HR đang làm việc không tự có nghĩa một lệnh đình chỉ truy cập tại ứng dụng phải bị xóa. Có thể cần những trạng thái độc lập và policy kết hợp chúng một cách có chủ đích.

### 12.3. Offboarding cần đi qua các hệ thống sử dụng danh tính

Một quy trình kết thúc quyền truy cập có thể gồm:

~~~text
Nguồn có thẩm quyền ghi nhận thay đổi.
Directory cập nhật trạng thái tài khoản.
Membership và grant được xử lý theo policy.
IdP/session/credential được xử lý theo khả năng và hợp đồng.
Ứng dụng và cache nhận thay đổi hoặc kiểm tra lại.
Job thay người dùng được dừng hoặc đánh giá lại theo quy tắc.
Audit ghi nhận kết quả và lỗi cần xử lý tiếp.
~~~

Không suy ra rằng xóa một entry sẽ tự thu hồi mọi access token đã cấp hoặc đăng xuất mọi ứng dụng. Các điểm thực thi có thể đang dùng snapshot.

Quy trình cần xác định độ trễ chấp nhận được và cách phát hiện bước chưa hoàn thành. Chỉ đổi nhãn “inactive” trên giao diện quản trị chưa chứng minh quyền đã ngừng ở các ứng dụng.

### 12.4. Xóa, giữ tham chiếu và tái tuyển dụng

Dữ liệu nghiệp vụ có thể cần giữ tham chiếu đến tác giả hoặc chủ thể đã thực hiện một thao tác. Không nên xóa user record theo cách làm lịch sử trỏ nhầm sang người khác.

Có thể dùng tombstone, một trạng thái đóng hoặc thông tin tối thiểu theo chính sách lưu trữ. Việc giữ/xóa dữ liệu cần tuân theo yêu cầu áp dụng của hệ thống; không mặc định phải giữ toàn bộ hồ sơ mãi mãi.

Khi một người quay lại tổ chức, cần quyết định đó là khôi phục cùng account hay tạo account mới. Không phục hồi toàn bộ đặc quyền cũ chỉ vì employee number hoặc email trùng.

Nếu account mới được tạo, ID cũ không được tái cấp theo cách làm tài nguyên, liên kết ngoài hoặc quyền cũ vô tình chuyển sang account mới.

## 13. Provisioning, đồng bộ và đối soát

### 13.1. Luồng ghi phải có nguồn có thẩm quyền

Một ví dụ:

~~~text
HR quản lý employee number và tình trạng lao động.
Directory quản lý account ID và trạng thái truy cập nội bộ.
Ứng dụng quản lý membership/role theo tenant.
Người dùng được sửa một số trường hồ sơ.
~~~

Đây là phân quyền theo thuộc tính và use case. Không nhất thiết một hệ thống là nguồn chuẩn duy nhất cho mọi thứ.

Nếu connector HR được quyền sửa display name và employee number, nó không tự có quyền cấp nhóm đặc quyền chỉ vì request cùng chứa user ID.

### 13.2. Chống tạo trùng và xử lý retry

Một lệnh cấp phát có thể được gửi lại do timeout hoặc kết nối gián đoạn. Nếu mỗi lần retry đều tạo account mới, một con người có thể nhận nhiều user ID và quan hệ quyền phân tán.

Cần có khóa liên kết nguồn và cơ chế idempotency phù hợp:

~~~text
(sourceSystemId, sourceRecordId) -> internalUserId
~~~

Không dùng email làm khóa chống trùng duy nhất nếu email có thể đổi hoặc được tái cấp.

Ràng buộc unique ở kho dữ liệu hỗ trợ xử lý hai request tạo đồng thời. Một lần kiểm tra “chưa tồn tại” rồi insert không có ràng buộc vẫn có thể tạo trùng khi nhiều worker chạy cùng lúc.

### 13.3. Không để snapshot cũ khôi phục trạng thái bị chặn

Ví dụ:

~~~text
T1: Directory có account ACTIVE, revision 10.
T2: Quản trị viên đình chỉ, revision 11.
T3: Một lượt đồng bộ cũ gửi lại ACTIVE từ snapshot trước T2.
~~~

Nếu mọi lần ghi đều được chấp nhận không xét nguồn và thứ tự, trạng thái cũ có thể ghi đè lệnh đình chỉ.

Cần hợp đồng về quyền ghi, version hoặc điều kiện cập nhật phù hợp. Những trường hợp xung đột giữa quản trị thủ công và đồng bộ phải được xử lý theo policy, không chỉ dựa vào thời điểm response đến.

### 13.4. Đối soát là phần bổ sung cho luồng thay đổi

Sự kiện hoặc đồng bộ tăng dần có thể bỏ sót bản ghi. Đối soát giúp tìm:

- Tài khoản còn hoạt động dù nguồn đã kết thúc.
- Tài khoản trùng hoặc liên kết nguồn bị lệch.
- Membership không còn hợp lệ.
- Tài khoản bị xóa ở nguồn nhưng vẫn còn trong một ứng dụng.
- Thay đổi chưa được áp dụng do lỗi từng phần.

Không tự xóa hàng loạt khi nguồn trả danh sách rỗng do timeout, lỗi phân trang hoặc quyền đọc bị thay đổi. Cần phân biệt một kết quả nghiệp vụ hợp lệ với lỗi lấy dữ liệu trước khi thực hiện đồng bộ phá hủy.

## 14. Bảo vệ thao tác tra cứu và sửa directory

### 14.1. Quyền tối thiểu theo dữ liệu và hành động

Một ứng dụng chỉ cần tra ID và tên hiển thị không nên có credential quản trị để sửa nhóm đặc quyền.

Có thể tách quyền:

~~~text
Đọc hồ sơ cơ bản.
Đọc thuộc tính tổ chức.
Đọc hoặc quản lý group membership.
Thay đổi trạng thái account.
Quản lý liên kết danh tính.
Quản lý credential.
~~~

Quyền trên mỗi loại dữ liệu có thể khác nhau theo chủ thể gọi và phạm vi tenant/directory.

Không trả “mọi thuộc tính” làm mặc định cho API hồ sơ. Một directory có thể chứa số điện thoại, thông tin quản lý, quan hệ tổ chức hoặc thuộc tính không cần cho người gọi.

### 14.2. Tham số hóa truy vấn và xử lý đúng cú pháp

Với SQL, sử dụng truy vấn tham số hóa cho giá trị tìm kiếm. Nếu cho phép chọn trường sắp xếp hoặc lọc, cần kiểm soát cấu trúc được phép; bind một giá trị không tự bảo vệ tên cột hoặc toàn bộ biểu thức do client gửi.

Với LDAP, giá trị đưa vào search filter và giá trị dùng trong DN có quy tắc escaping khác nhau. Cần dùng API/encoder phù hợp ngữ cảnh, không nối trực tiếp dữ liệu chưa tin cậy thành truy vấn. [Nguồn: OWASP — LDAP Injection Prevention](https://cheatsheetseries.owasp.org/cheatsheets/LDAP_Injection_Prevention_Cheat_Sheet.html).

Không sử dụng một hàm thay chuỗi tự viết rồi giả định nó đúng cho mọi cú pháp directory.

### 14.3. Tìm kiếm có thể làm lộ danh tính

Một endpoint tìm người dùng theo email có thể trở thành cách dò tài khoản, đọc danh sách nhân viên hoặc phát hiện một tổ chức đang dùng sản phẩm.

Cần định nghĩa:

- Ai được tìm kiếm trong namespace nào?
- Trả những trường nào?
- Có giới hạn số lượng, phân trang và tần suất phù hợp không?
- Lỗi công khai có tiết lộ thông tin ngoài quyền không?
- Người dùng có được xem các membership khác của người được tìm không?

Ẩn nút tìm kiếm trên giao diện không thay thế kiểm tra ở server.

Các luồng khôi phục tài khoản có thể cần phản hồi công khai hạn chế thông tin, trong khi công cụ quản trị nội bộ có hợp đồng khác. Không dùng cùng một endpoint có quyền rộng cho mọi đối tượng gọi.

### 14.4. Sửa hồ sơ phải dùng danh sách trường phù hợp

Một use case sửa tên hiển thị có thể chỉ nhận:

~~~java
record UpdateDisplayNameRequest(String displayName) {}
~~~

Server xác minh chủ thể được sửa tài khoản nào, kiểm tra dữ liệu và chỉ cập nhật trường cho phép.

Không nhận nguyên entity chứa role, state, tenant hoặc provider mapping rồi lưu toàn bộ. Một trường bị ẩn trong giao diện vẫn có thể được thêm thủ công vào request.

## 15. Khả dụng, cache và bản sao directory

### 15.1. Không phải mọi truy vấn cần cùng mức nhất quán

Hiển thị tên đồng nghiệp và quyết định tài khoản có được thực hiện hành động đặc quyền có yêu cầu khác nhau.

Một bản cache tên hiển thị hơi cũ có thể chấp nhận được theo sản phẩm. Bản cache `accountState = ACTIVE` sau khi tài khoản bị đình chỉ có thể làm sai quyền truy cập.

Cần đặt yêu cầu độ mới theo dữ liệu và hành động, không áp dụng một TTL chung chỉ vì tất cả cùng nằm trong user record.

### 15.2. Credential hợp lệ nhưng directory không truy cập được

Ứng dụng cần chính sách khi nguồn danh tính không phản hồi:

~~~text
Đang đọc hồ sơ hiển thị:
    Có thể dùng snapshot trong phạm vi hợp đồng.

Đang xác minh trạng thái cho thao tác cần dữ liệu mới:
    Không tự cho phép khi chưa xác minh được.

Đang cấp phát:
    Không coi timeout là kết quả "không tồn tại"
    rồi tạo account mới.
~~~

Nếu có ngoại lệ cho phép dùng dữ liệu cũ, nó cần phạm vi và thời hạn rõ ràng. Không tự kéo dài cache vô hạn khi directory tiếp tục lỗi.

### 15.3. Replication và phục hồi cần giữ đúng liên kết

Một bản sao có thể chưa nhận rename, trạng thái đình chỉ hoặc liên kết mới. Failover cũng không tự chứng minh bản sao được chọn có dữ liệu đủ mới.

Khi khôi phục backup, cần xử lý nguy cơ hồi sinh account, group membership hoặc liên kết đã bị thu hồi sau thời điểm backup.

Không chỉ kiểm tra số lượng user record sau phục hồi. Cần kiểm tra định danh ổn định, trạng thái quan trọng và quan hệ giữa các hệ thống sử dụng directory theo kế hoạch khôi phục.

## 16. Kiểm toán và vận hành

Những thay đổi thường cần dấu vết:

~~~text
Tạo hoặc đóng account.
Đình chỉ hoặc khôi phục.
Đổi tên đăng nhập/email theo chính sách.
Liên kết hoặc gỡ danh tính ngoài.
Thêm hoặc gỡ nhóm dùng để cấp quyền.
Thay đổi membership tenant.
Thay đổi nguồn quản lý hoặc xử lý xung đột đồng bộ.
~~~

Một audit event có thể ghi:

~~~text
actorId hoặc workloadId
targetUserId
directoryScope
tenantId nếu thao tác có phạm vi tenant
action
sourceSystem
previousVersion
newVersion
requestId
outcome
occurredAt
~~~

Không cần ghi credential hoặc nguyên hồ sơ để chứng minh thao tác xảy ra. Nếu cần lưu giá trị trước/sau, phải chọn trường và quyền truy cập audit theo mục đích.

Các chỉ số hữu ích có thể gồm:

- Số account mồ côi hoặc bị tạo trùng.
- Tỷ lệ lỗi provisioning và thời gian xử lý.
- Độ trễ áp dụng đình chỉ tại ứng dụng.
- Xung đột liên kết danh tính.
- Chênh lệch giữa nguồn và bản sao.
- Lượt tìm kiếm hoặc thay đổi đặc quyền bất thường.

Tài khoản dịch vụ truy cập directory cũng cần chủ sở hữu, credential được quản lý và quyền phù hợp. Một connector đồng bộ bị cấp quyền quá rộng có thể trở thành đường thay đổi danh tính ngoài ý muốn.

## 17. Ma trận kiểm thử

Chuẩn bị dữ liệu trong môi trường được phép:

~~~text
U-81:
    ACTIVE, có liên kết provider P-1 / subject S-81.
    Có membership ACTIVE ở T-A.
    Có membership REVOKED ở T-B.

U-92:
    SUSPENDED, có liên kết provider P-1 / subject S-92.

U-103:
    Tài khoản khác, có thể có tên hiển thị giống U-81.
~~~

| Tình huống | Kỳ vọng |
| --- | --- |
| Danh tính P-1/S-81 đã xác minh, chọn T-A | Giải quyết U-81 rồi tiếp tục xét quyền |
| P-1/S-81 chọn T-B | Bị chặn theo membership của ví dụ |
| Danh tính ánh xạ U-92 | Không tạo ngữ cảnh thông thường khi account bị đình chỉ |
| Provider khác phát subject cùng chuỗi S-81 | Không tự ánh xạ U-81 |
| Hai tài khoản có tên hiển thị giống nhau | Vẫn có định danh và quyền riêng |
| Email U-81 đổi | Quan hệ sở hữu vẫn trỏ U-81 |
| Email cũ được cấp cho người mới | Không kế thừa account hoặc tài nguyên U-81 |
| LDAP entry đổi DN nhưng giữ định danh đối tượng | Không tạo account nội bộ mới chỉ vì DN đổi |
| Entry cũ bị xóa, entry mới nhận lại DN | Không tự kế thừa liên kết cũ |
| Identity mapping chưa tồn tại | Theo luồng cấp phát đã định nghĩa, không tự nối bằng email |
| Hai request provisioning đồng thời | Không tạo trùng ngoài hợp đồng |
| Directory timeout | Không coi là account không tồn tại để tạo mới |
| Snapshot đồng bộ cũ đến sau lệnh đình chỉ | Không vô tình khôi phục truy cập |
| Client thêm accountState hoặc group đặc quyền vào request hồ sơ | Không sửa ngoài quyền use case |
| Người dùng thường gọi API tìm kiếm toàn directory | Bị giới hạn theo phạm vi và trường được phép |
| Replica chưa có lệnh đình chỉ | Hành vi tuân thủ chính sách độ mới đã công bố |
| Xóa account rồi tạo mới | Không tái sử dụng ID làm chuyển quyền ngoài ý muốn |
| Khôi phục backup cũ | Có quy trình xử lý quyền và trạng thái đã thay đổi sau backup |

Ngoài hàm resolver, cần kiểm tra đường thực thi thật:

1. Identity mapping nhận giá trị từ bước xác thực đã kiểm tra.
2. Cơ sở dữ liệu so sánh khóa đúng ngữ nghĩa nguồn.
3. Quyền đọc directory được kiểm tra trước khi trả kết quả tìm kiếm.
4. Endpoint hồ sơ không trả credential hoặc thuộc tính ngoài phạm vi.
5. Trạng thái đình chỉ thực sự được các điểm truy cập áp dụng theo hợp đồng.
6. Retry provisioning và xử lý lỗi từng phần không làm mất liên kết.
7. Thao tác từ chối không để lại thay đổi quyền trái phép.

Đây là ma trận hướng dẫn, không phải báo cáo rằng các đoạn mã trong bài đã được chạy trên một directory thật.

## 18. Ngộ nhận và bài tập vận dụng

| Ngộ nhận | Cách hiểu chính xác hơn |
| --- | --- |
| Directory là một bảng username/password | Nó có mô hình định danh, thuộc tính, quan hệ, lifecycle và quyền truy cập |
| Tìm được email là xác thực được người gọi | Lookup và xác thực là hai bước khác nhau |
| Email luôn là ID tốt nhất | Nó có thể đổi hoặc được tái cấp |
| Có user record là được vào mọi tenant | Còn phải kiểm tra trạng thái, membership và policy |
| Group nào cũng là role | Cần ánh xạ đúng mục đích và phạm vi |
| DN là ID bất biến | Đổi tên/chuyển nhánh hoặc tái sử dụng DN có thể làm sai liên kết |
| Có SCIM là đã có SSO | Cấp phát resource và xác thực là các trách nhiệm khác nhau |
| Xóa directory entry là thu hồi hết token | Cần cơ chế thực thi và thu hồi tại những hệ thống liên quan |
| Timeout nghĩa là không có account | Lỗi hạ tầng không phải kết quả nghiệp vụ không tồn tại |
| Restore đủ số user là đã phục hồi đúng | Cần kiểm tra định danh, trạng thái và các liên kết quyền |

Bài tập: thiết kế user directory cho một nền tảng dự án có nhân viên, cộng tác viên và quản trị viên dùng account riêng. Một người có thể tham gia nhiều tenant và có nhiều phương thức đăng nhập.

Hãy xác định:

- ID nội bộ nào bất biến và không được tái cấp?
- Các danh tính OIDC hoặc directory nguồn được ánh xạ thế nào?
- Email, username và DN có được thay đổi hoặc tái sử dụng không?
- Ai được sửa từng nhóm thuộc tính?
- Group nào được policy dùng để cấp quyền, trong phạm vi nào?
- Account state và membership state được kết hợp ra sao?
- Trường hợp chưa có account được cấp phát theo quy trình nào?
- Khi nghỉ việc, đình chỉ hoặc khôi phục backup, hệ thống chứng minh quyền được xử lý đúng bằng cách nào?

Một thiết kế đủ rõ phải theo được đường đi từ **bằng chứng đăng nhập**, qua **tài khoản có định danh ổn định**, đến **quan hệ và thuộc tính còn hiệu lực**, rồi mới đến **quyết định truy cập tài nguyên**.
