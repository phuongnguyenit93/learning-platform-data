# Unique identifier

## 1. Định danh duy nhất giải quyết vấn đề gì trong IAM?

**Unique identifier** là giá trị giúp hệ thống phân biệt một đối tượng với các đối tượng khác trong **một phạm vi định danh đã được xác định**.

Trong directory và identity store, đối tượng đó có thể là tài khoản người dùng, nhóm, membership, liên kết danh tính ngoài hoặc credential. Không phải mọi chuỗi trông giống ID đều mang cùng ý nghĩa.

Ví dụ:

~~~text
userId = U-81
displayName = Nguyễn An
email = an@example.test
~~~

`userId` trả lời “đây là tài khoản nào?”. Tên và email phục vụ những mục đích khác. Nếu email đổi, quyền sở hữu dự án và lịch sử thao tác vẫn cần trỏ đến đúng tài khoản.

Trong IAM, một lỗi liên kết ID có thể làm:

- Gắn người đăng nhập vào tài khoản của người khác.
- Chuyển quyền cũ sang tài khoản mới nhận lại cùng email hoặc username.
- Trộn người dùng giữa tenant hoặc directory.
- Làm audit không còn xác định được chủ thể đã thao tác.
- Khôi phục quyền đã thu hồi khi dữ liệu được nhập lại.

Vì vậy, thiết kế ID không chỉ là chọn kiểu dữ liệu cho khóa chính. Nó còn bao gồm namespace, vòng đời, cách cấp, quyền thay đổi và cách dùng để tra cứu.

Sau bài này, người học có thể:

1. Xác định phạm vi duy nhất của một ID và phân biệt ID với tên đăng nhập.
2. Giải thích tính bất biến và không tái cấp trong vòng đời tài khoản.
3. Ánh xạ ID giữa directory, IdP và ứng dụng theo đúng namespace.
4. So sánh ID tuần tự, UUID và ID sinh từ dữ liệu.
5. Thiết kế ràng buộc lưu trữ, parse và xử lý xung đột.
6. Nhận diện những trường hợp ID hợp lệ vẫn không chứng minh quyền truy cập.

## 2. Những thuộc tính không được đánh đồng

| Thuộc tính | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Duy nhất — unique | Hai đối tượng khác nhau có được cấp cùng giá trị trong cùng namespace không? | Hai account không cùng `userId` |
| Bất biến — immutable | ID có đổi khi cùng đối tượng đổi hồ sơ không? | Đổi email không đổi `userId` |
| Không tái cấp — non-reassignable | ID của đối tượng cũ có được trao cho đối tượng mới không? | Account mới không nhận lại ID đã đóng |
| Opaque | Bên dùng có cần diễn giải cấu trúc bên trong không? | Client chỉ lưu và gửi lại ID |
| Khó đoán | Người ngoài có dễ suy ra ID tiếp theo không? | ID ngẫu nhiên so với sequence |
| Có thẩm quyền | Giá trị có đến từ bên được phép cấp/xác nhận không? | Server cấp ID theo hợp đồng |
| Đủ quyền | Chủ thể có được thao tác với đối tượng được định danh không? | Có ID đơn hàng vẫn phải xét quyền |

Một ID tuần tự có thể duy nhất và bất biến nhưng dễ đoán. Một chuỗi ngẫu nhiên có thể khó đoán nhưng vẫn bị cấp trùng nếu bộ sinh lỗi. Một email duy nhất ở thời điểm hiện tại có thể được tái cấp cho người khác trong tương lai.

Không nên dùng một từ “unique” để thay cho tất cả các bảo đảm trên.

Trong bài, hệ thống minh họa chọn `localUserId` do server cấp, ổn định suốt vòng đời tài khoản và không tái cấp cho tài khoản khác. Đây là hợp đồng của ID nội bộ, không phải lời khẳng định về mọi trường do một provider bất kỳ trả về.

## 3. Duy nhất trong namespace nào?

### 3.1. Một giá trị riêng lẻ có thể chưa đủ

Hai directory có thể có:

~~~text
Directory D-A: userId = 1001
Directory D-B: userId = 1001
~~~

Không có lỗi nếu mỗi bên chỉ bảo đảm ID duy nhất trong directory của mình. Khi ứng dụng dùng chung dữ liệu từ cả hai, cần giữ namespace:

~~~text
(D-A, 1001)
(D-B, 1001)
~~~

Tương tự, mã thành viên `42` có thể tồn tại trong nhiều tenant. Tùy hợp đồng, khóa có thể là:

~~~text
(tenantId, localMemberId)
~~~

Nếu ID nội bộ đã duy nhất toàn ứng dụng thì không nhất thiết cần tenant trong khóa để phân biệt tài khoản. Nhưng tenant vẫn có thể là điều kiện bắt buộc trong policy truy cập.

### 3.2. Phạm vi theo loại đối tượng

`userId = X` và `groupId = X` không nhất thiết là va chạm nếu hai loại dùng namespace khác nhau. Tuy nhiên, một cache chỉ dùng khóa `X` có thể nhầm hai đối tượng.

Có thể biểu diễn khóa tham chiếu theo:

~~~text
resourceType + namespace + resourceId
~~~

Hoặc dùng kiểu dữ liệu riêng trong code, chẳng hạn `UserId` và `GroupId`.

Một prefix như `usr_` hoặc `grp_` hỗ trợ nhận diện định dạng. Nó không tự chứng minh người gọi được phép truy cập loại tài nguyên đó.

### 3.3. Phạm vi môi trường và nguồn cấp

ID từ môi trường thử nghiệm không tự được chấp nhận trong production. Hai hệ thống sao chép dữ liệu có thể mang cùng ID nhưng thuộc miền tin cậy khác nhau.

Khi nhận ID từ bên ngoài, cần biết:

~~~text
Bên cấp là ai?
Phạm vi duy nhất của bên đó là gì?
ID thuộc loại đối tượng nào?
ID được dùng trong môi trường nào?
Hợp đồng so sánh và vòng đời là gì?
~~~

Một chuỗi UUID đúng cú pháp không trả lời được những câu hỏi này.

## 4. Định danh ổn định khác với alias có thể thay đổi

### 4.1. Email và username

Email có thể đổi khi người dùng đổi tên, chuyển miền hoặc chuyển tổ chức. Username có thể được đổi theo quy trình sản phẩm hoặc được cấp lại sau khi tài khoản cũ đóng.

Một luồng nguy hiểm:

~~~text
1. Alice có email an@example.test và sở hữu tài nguyên R.
2. Alice rời tổ chức; account cũ bị đóng.
3. Bob được cấp lại an@example.test.
4. Ứng dụng tìm owner của R chỉ bằng email.
5. Bob bị nhận nhầm thành chủ thể cũ.
~~~

Nếu R tham chiếu `localUserId` ổn định của Alice, việc email được tái cấp không tự chuyển R cho Bob.

Có thể vẫn dùng email để liên hệ hoặc làm một cách đăng nhập theo chính sách. Điều cần tránh là mặc định nó cũng là khóa liên kết bất biến.

### 4.2. Mã nhân viên và tên tổ chức

Employee number có thể có ý nghĩa trong một hệ thống nhân sự cụ thể. Khi tích hợp nhiều nguồn, có thể cần:

~~~text
(hrSystemId, employeeNumber)
~~~

Ngay cả khi mã không trùng trong một nguồn hiện tại, vẫn phải biết nguồn có tái cấp nó hay không và nó định danh con người, hợp đồng lao động hay hồ sơ nhân sự.

Tên công ty, tên tenant và tên nhóm thường là nhãn hiển thị. Không nên dùng việc đổi nhãn làm cách đổi đối tượng được tham chiếu.

### 4.3. Địa chỉ entry trong directory

Trong LDAP, DN không phải định danh ổn định: một đối tượng có thể đổi tên và một DN có thể được dùng cho đối tượng khác sau đó. RFC 4530 mô tả `entryUUID` do server cấp để phân biệt đối tượng và tìm lại sau rename. [Nguồn: RFC 4530, mục 1](https://www.rfc-editor.org/rfc/rfc4530.html#section-1).

Cần dùng thuộc tính ổn định mà directory thực sự cung cấp theo hợp đồng, không mặc định mọi sản phẩm có cùng thuộc tính hoặc biểu diễn.

Một thay đổi DN của cùng entry khác với việc xóa entry rồi tạo đối tượng mới có cùng DN. Chỉ so sánh chuỗi đường dẫn sẽ không đủ để phân biệt hai tình huống.

## 5. Ánh xạ định danh giữa các hệ thống

### 5.1. ID nội bộ và ID bên ngoài có vai trò khác nhau

Ứng dụng có thể quản lý:

~~~text
localUserId:
    Do ứng dụng cấp, dùng làm tham chiếu nội bộ.

externalIdentityKey:
    Định danh tài khoản ở một provider/nguồn cụ thể.

sourceRecordKey:
    Khóa bản ghi của hệ thống cấp phát hoặc nhân sự.
~~~

Không cần buộc tất cả có cùng giá trị. Một bảng ánh xạ cho phép ứng dụng giữ ID nội bộ trong khi cách đăng nhập hoặc nguồn tích hợp thay đổi có kiểm soát.

Ví dụ:

~~~text
(provider P-1, subject S-81) -> local user U-81
(provider P-2, subject Z-27) -> local user U-81
~~~

Hai liên kết chỉ hợp lệ nếu được tạo qua quy trình có đủ bằng chứng. Không tự gộp chỉ vì hai provider trả cùng email.

### 5.2. Cặp issuer–subject trong OpenID Connect

OpenID Connect quy định `sub` được diễn giải trong phạm vi `iss`; cặp này là cơ sở định danh ổn định người dùng theo hợp đồng của issuer. Không thay nó bằng email hoặc tên hiển thị. [Nguồn: OpenID Connect Core, mục 5.7](https://openid.net/specs/openid-connect-core-1_0.html#ClaimStability).

Ứng dụng có thể dùng `providerId` nội bộ đại diện cho một cấu hình issuer/client tin cậy. Cấu hình phải giữ đúng ngữ nghĩa của subject, kể cả khi provider dùng subject pairwise.

Không tự đổi issuer đứng sau cùng `providerId` rồi coi các chuỗi subject cũ vẫn chỉ đúng đối tượng. Thay đổi miền tin cậy là một migration liên kết, không chỉ thay URL cấu hình.

Subject đã lấy từ một token chưa xác minh vẫn là dữ liệu chưa được tin cậy. Tính duy nhất của ID không thay thế kiểm tra giao thức xác thực.

### 5.3. `id` và `externalId` trong SCIM

SCIM phân biệt `id` do service provider cấp với `externalId` do provisioning client quản lý. `id` phải ổn định và không tái cấp; `externalId` được diễn giải trong phạm vi provisioning domain tương ứng. [Nguồn: RFC 7643, mục 3.1](https://www.rfc-editor.org/rfc/rfc7643.html#section-3.1).

Ví dụ:

~~~text
HR source:
    sourceRecordId = EMP-17

SCIM application:
    id = user-81
    externalId = EMP-17
~~~

Không mặc định `EMP-17` duy nhất trên mọi connector hoặc mọi hệ thống HR. Cũng không để client tự chỉ định `id` của tài khoản đã tồn tại để chiếm liên kết.

### 5.4. Khóa ghép cần biểu diễn không nhập nhằng

Nếu ghép các thành phần bằng một dấu phân cách mà chính thành phần cũng có thể chứa, hai bộ giá trị khác nhau có thể tạo cùng chuỗi.

~~~text
(namespace = a:b, subject = c)
(namespace = a,   subject = b:c)
~~~

Cả hai đều có thể thành `a:b:c` nếu nối tùy ý.

Nên dùng tuple trong cơ sở dữ liệu hoặc một định dạng encoding có hợp đồng rõ ràng. Không tự nối chuỗi rồi coi kết quả chắc chắn là khóa duy nhất.

## 6. Chọn cách cấp ID

### 6.1. Các chiến lược thường gặp

| Chiến lược | Điểm hữu ích | Điều phải kiểm soát |
| --- | --- | --- |
| Sequence/số tăng dần | Dễ cấp qua một kho có điều phối | Namespace, nhiều node, restore và tính dễ đoán |
| UUID ngẫu nhiên | Hỗ trợ cấp phân tán với xác suất va chạm rất thấp khi triển khai đúng | Nguồn ngẫu nhiên, ràng buộc unique và xử lý lỗi |
| ID có thành phần thời gian | Có thể hỗ trợ bố trí dữ liệu theo thời gian | Đồng hồ, trạng thái bộ sinh và thông tin thời gian bị lộ |
| ID xác định từ dữ liệu đầu vào | Cùng đầu vào có thể tạo cùng kết quả theo thuật toán | Namespace, dữ liệu thay đổi, va chạm và lộ liên hệ |
| ID do nguồn bên ngoài cấp | Giữ liên kết với directory/provider | Phạm vi, tính bất biến và độ tin cậy của nguồn |

Không có chiến lược nào tự giải quyết tất cả các yêu cầu IAM. Chọn cách cấp sau khi đã xác định hợp đồng vòng đời và namespace.

### 6.2. UUIDv4 và UUIDv7

UUID là giá trị 128 bit. RFC 9562 mô tả UUIDv4 dựa trên số ngẫu nhiên/giả ngẫu nhiên và UUIDv7 có thành phần thời gian Unix theo millisecond ở phần đầu. [Nguồn: RFC 9562, mục 5.4 và 5.7](https://www.rfc-editor.org/rfc/rfc9562.html#section-5.4).

UUIDv4 phù hợp với ví dụ cấp ID nội bộ ngẫu nhiên của bài. UUIDv7 có thể hữu ích khi cần đặc tính sắp xếp theo thời gian, nhưng không nên coi timestamp bên trong nó là thời điểm nghiệp vụ đã được xác minh hoặc một thứ tự commit toàn cục.

Với mọi bộ sinh có trạng thái hoặc phụ thuộc đồng hồ, cần kiểm tra hành vi khi nhiều node chạy đồng thời, đồng hồ lùi, tiến trình khởi động lại hoặc dữ liệu được phục hồi. Không chỉ kiểm tra định dạng đầu ra.

### 6.3. Không sinh ID tài khoản từ tên/email chỉ vì thuận tiện

Những cách sau không thể hiện tốt hợp đồng tài khoản bất biến:

~~~text
userId = lowercase(email)
userId = hashCode(displayName)
userId = timestamp hiện tại
~~~

Email và tên có thể thay đổi. Hash hữu hạn có thể va chạm. Timestamp có thể trùng giữa các request hoặc node.

Băm email thành một chuỗi khó đọc cũng không tự làm nó vô danh hoặc thành khóa bất biến. Nếu miền giá trị dễ đoán, người khác có thể thử các đầu vào; thay email vẫn tạo vấn đề liên kết theo cùng hợp đồng sinh đó.

## 7. Xác suất va chạm và ràng buộc thực thi

UUIDv4 có 122 bit dành cho thành phần ngẫu nhiên sau khi dành bit version/variant theo định dạng. [Nguồn: RFC 9562, mục 5.4](https://www.rfc-editor.org/rfc/rfc9562.html#section-5.4).

Nếu giả sử các giá trị được sinh độc lập và phân bố đều trên `N = 2^122` khả năng, với `n` nhỏ so với căn bậc hai của `N`, xấp xỉ birthday cho xác suất có va chạm là:

~~~text
p ≈ n(n - 1) / (2N)
~~~

Với `n = 1.000.000.000`:

~~~text
N ≈ 5,3169 × 10^36
p ≈ 9,4 × 10^-20
~~~

Đây là tính toán dưới giả thiết lý tưởng, không phải bảo đảm rằng mọi triển khai thực tế đều có xác suất đó. Seed lỗi, bộ sinh bị sao chép sai, cắt ngắn giá trị, lỗi serialize hoặc import trùng có thể làm hỏng giả thiết.

Vì vậy, kho dữ liệu vẫn cần primary key/unique constraint theo namespace đã định nghĩa.

Đặc biệt, nếu insert ID mới bị xung đột, không được tự trả về account đang mang ID đó như thể nó là người dùng vừa tạo. Va chạm kỹ thuật và “đây là cùng tài khoản” là hai kết luận khác nhau.

## 8. Biết ID không đồng nghĩa có quyền

Một API:

~~~http
GET /api/users/0f8fad5b-d9cb-469f-a165-70867728950e
~~~

vẫn phải kiểm tra người gọi được đọc account nào và được đọc trường nào.

OWASP mô tả BOLA là lỗi khi API không kiểm tra quyền trên đối tượng được tham chiếu. ID có thể là số, UUID hoặc chuỗi khác; đổi định dạng ID không thay thế kiểm tra quyền. [Nguồn: OWASP — API1:2023](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/).

Một ID khó đoán có thể giảm khả năng dò tuần tự. Nó vẫn có thể xuất hiện trong URL, email, log hoặc dữ liệu được chia sẻ.

Không dùng `userId` làm password, token khôi phục hoặc secret API chỉ vì giá trị trông ngẫu nhiên. Credential/capability cần hợp đồng riêng về người được cấp, quyền, thời hạn, lưu trữ và thu hồi.

Trong hệ thống nhiều tenant:

~~~text
ID duy nhất toàn ứng dụng
    không có nghĩa
được phép bỏ điều kiện tenant hoặc membership.
~~~

## 9. Ví dụ Java: kiểu ID nội bộ và khóa danh tính ngoài

### 9.1. Hợp đồng của ví dụ

Ứng dụng minh họa chọn:

~~~text
LocalUserId:
    Server cấp UUIDv4.
    API nhận dạng văn bản UUID đủ 36 ký tự.
    Có thể nhận chữ hex hoa hoặc thường.
    Khi xuất ra, dùng biểu diễn chuẩn từ UUID.toString().
    Không trim hoặc tự sửa một chuỗi sai cấu trúc.
    Không dùng kiểu này để parse mọi ID của provider bên ngoài.
~~~

Java 17 cung cấp `UUID.randomUUID()` để tạo UUIDv4 bằng bộ sinh giả ngẫu nhiên mạnh về mật mã. [Nguồn: Java SE 17 — UUID.randomUUID](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/UUID.html#randomUUID()).

Đây là lựa chọn cho ID nội bộ của ví dụ. Một hệ thống đã dùng UUIDv7 hoặc định dạng khác cần hợp đồng tương ứng; không áp dụng điều kiện version 4 một cách tùy tiện cho dữ liệu hiện có.

~~~java
import java.util.Objects;
import java.util.UUID;
import java.util.regex.Pattern;

final class Identifiers {
    private static final Pattern UUID_TEXT = Pattern.compile(
        "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
        + "[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        + "[0-9a-fA-F]{12}"
    );

    record LocalUserId(UUID value) {
        LocalUserId {
            Objects.requireNonNull(value);

            if (value.version() != 4 || value.variant() != 2) {
                throw new IllegalArgumentException(
                    "Expected a UUIDv4 local user identifier"
                );
            }
        }

        static LocalUserId create() {
            return new LocalUserId(UUID.randomUUID());
        }

        static LocalUserId parse(String raw) {
            if (raw == null || !UUID_TEXT.matcher(raw).matches()) {
                throw new IllegalArgumentException(
                    "Invalid local user identifier syntax"
                );
            }

            return new LocalUserId(UUID.fromString(raw));
        }

        @Override
        public String toString() {
            return value.toString();
        }
    }

    record ExternalIdentityKey(
        String providerId,
        String subject
    ) {
        ExternalIdentityKey {
            Objects.requireNonNull(providerId);
            Objects.requireNonNull(subject);

            if (providerId.isEmpty() || subject.isEmpty()) {
                throw new IllegalArgumentException(
                    "External identity key cannot be empty"
                );
            }
        }
    }
}
~~~

`ExternalIdentityKey` giữ nguyên chuỗi subject. Việc xác minh provider, subject và quyền liên kết phải diễn ra trong luồng riêng; constructor không làm nhiệm vụ xác thực.

### 9.2. Những điều code có và không bảo đảm

Code hỗ trợ:

- Giữ ID nội bộ dưới dạng `UUID` thay vì chuỗi tùy ý trong domain.
- Tách ID tài khoản với khóa danh tính ngoài.
- Kiểm tra cấu trúc trước khi parse.
- Áp dụng đúng version/variant do hợp đồng ví dụ chọn.
- Chuẩn hóa đầu ra của ID nội bộ theo một cách nhất quán.

Code không chứng minh:

~~~text
ID đã được cấp cho một user record.
User record đó còn hoạt động.
ID thuộc tenant người gọi được truy cập.
Người gọi kiểm soát danh tính được tham chiếu.
Nguồn cấp ID bên ngoài là đáng tin cậy.
Hai hệ thống đang nói về cùng một con người.
~~~

Những điều đó cần tra cứu và policy tương ứng.

Nếu cần ngăn truyền nhầm ID giữa các loại, có thể tạo thêm các kiểu `TenantId`, `GroupId` hoặc `CredentialId` theo hợp đồng riêng. Không dùng một kiểu UUID chung rồi chỉ dựa vào tên tham số để chống mọi nhầm lẫn.

### 9.3. `hashCode()` không phải unique identifier

Java `hashCode()` phục vụ các cấu trúc như hash table. Hai giá trị khác nhau có thể có cùng hash code mà vẫn không `equals`.

Không lưu `userId.hashCode()` thay cho ID, không cắt UUID xuống vài ký tự chỉ để tiết kiệm và không suy ra quyền từ một giá trị hash. Nếu rút ngắn không gian giá trị, hợp đồng và xác suất va chạm đã thay đổi.

## 10. Lưu trữ và ràng buộc duy nhất

### 10.1. Ràng buộc theo đúng khóa logic

Một schema SQL minh họa:

~~~sql
CREATE TABLE local_users (
    user_id VARCHAR(36) PRIMARY KEY,
    display_name VARCHAR(200) NOT NULL,
    account_state VARCHAR(16) NOT NULL
);

CREATE TABLE external_identity_links (
    provider_namespace VARCHAR(128) NOT NULL,
    external_subject VARCHAR(255) NOT NULL,
    local_user_id VARCHAR(36) NOT NULL,
    link_state VARCHAR(16) NOT NULL,
    PRIMARY KEY (provider_namespace, external_subject),
    FOREIGN KEY (local_user_id) REFERENCES local_users(user_id)
);

CREATE TABLE projects (
    project_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    owner_user_id VARCHAR(36) NOT NULL,
    FOREIGN KEY (owner_user_id) REFERENCES local_users(user_id)
);
~~~

Schema chỉ minh họa định danh và tham chiếu. Các bảng tenant/provider, quyền, lifecycle, audit và ràng buộc nghiệp vụ chưa được liệt kê đầy đủ.

ID nội bộ được lưu bằng biểu diễn chuẩn thống nhất. Với ID bên ngoài, kiểu dữ liệu và collation cần giữ đúng ngữ nghĩa nguồn. Một unique constraint so sánh không phân biệt hoa/thường có thể không phù hợp với subject cần phân biệt.

Không để hệ quản trị tự cắt ngắn ID dài vượt cột rồi coi chuỗi đã cắt là hợp lệ. Giới hạn độ dài, cách báo lỗi và khả năng tương thích nguồn cần được kiểm tra trước khi nhận dữ liệu.

### 10.2. Tham chiếu tài nguyên đến ID, không đến email

Khi đổi email:

~~~text
local_users.user_id vẫn giữ nguyên.
projects.owner_user_id vẫn giữ nguyên.
Thông tin liên hệ được cập nhật theo use case riêng.
~~~

Việc sửa nhãn không làm thay đổi chủ thể được cấp quyền.

Foreign key hỗ trợ toàn vẹn tham chiếu. Nó không kiểm tra người đang gọi có quyền sửa project, không bảo đảm owner có membership phù hợp và không chứng minh account đang hoạt động.

### 10.3. Kiểm tra rồi insert chưa đủ chống trùng

Hai tiến trình có thể cùng chạy:

~~~text
A: kiểm tra external key chưa tồn tại.
B: kiểm tra external key chưa tồn tại.
A: tạo tài khoản.
B: tạo tài khoản.
~~~

Nếu không có ràng buộc atomic tại kho dữ liệu, cả hai có thể tạo kết quả trái hợp đồng.

Cần để primary key/unique constraint hoặc cơ chế tương đương chốt tính duy nhất. Kiểm tra trước có thể hỗ trợ trải nghiệm, nhưng không thay thế ràng buộc trong tình huống đồng thời.

## 11. Cấp phát, retry và xử lý xung đột

### 11.1. Một luồng tạo account có kiểm soát

Với một external key đã được xác minh và đủ điều kiện cấp phát:

~~~text
1. Tra liên kết hiện tại theo đúng namespace + subject.
2. Nếu có, xử lý tài khoản đó theo trạng thái và policy.
3. Nếu chưa có, sinh LocalUserId mới.
4. Trong transaction:
       tạo local user;
       tạo external identity link;
       tạo những dữ liệu khởi tạo thuộc cùng đơn vị atomic.
5. Commit.
6. Chỉ trả kết quả đã commit.
~~~

Luồng này vẫn cần chính sách quyết định ai được cấp phát account và thuộc tenant nào. Một subject hợp lệ ở một provider không tự có quyền gia nhập mọi tenant.

### 11.2. Phân loại đúng nguyên nhân xung đột

| Xung đột | Ý nghĩa có thể có | Hướng xử lý theo hợp đồng |
| --- | --- | --- |
| Trùng `localUserId` vừa sinh | Va chạm hoặc lỗi bộ sinh/import | Rollback; kiểm tra và retry có giới hạn khi phù hợp |
| Trùng external key | Request khác có thể vừa liên kết cùng danh tính | Rollback phần tạo; đọc lại đúng key và kiểm tra kết quả |
| Email hoặc login name vi phạm policy riêng | Xung đột alias, không chứng minh cùng account | Xử lý theo quy trình alias/liên kết |
| Sai khóa ngoại hoặc schema | Lỗi dữ liệu/cấu hình/nghiệp vụ | Báo lỗi phù hợp; không retry như va chạm ngẫu nhiên |

Không bắt mọi lỗi unique rồi trả account tìm được bằng bất kỳ trường nào trùng.

Đặc biệt:

~~~text
Trùng ID ngẫu nhiên
    không được tự diễn giải thành
được quyền dùng account đang giữ ID đó.
~~~

Nếu retry ID sinh mới, cần giới hạn lượt và theo dõi lỗi. Va chạm lặp lại có thể là dấu hiệu lỗi triển khai, không phải một tình huống nên lặp vô hạn.

### 11.3. Idempotency không đồng nghĩa cùng một con người

Một request cấp phát được gửi lại nên không tạo thêm tài khoản ngoài hợp đồng. Có thể dùng source record key hoặc idempotency key phù hợp.

Nhưng:

~~~text
Cùng email -> cùng con người
Cùng con người -> cùng tài khoản
Cùng tài khoản -> có mọi quyền của các lần cấp phát
~~~

đều không phải những phép suy diễn tự động hợp lệ.

Idempotency key cũng cần phạm vi thao tác, bên gọi và dữ liệu yêu cầu tương ứng. Không để một key từ tenant hoặc actor khác làm trả nhầm kết quả ngoài quyền.

## 12. Parse, serialize và so sánh qua API

### 12.1. Một ID phải giữ nguyên ý nghĩa qua mọi tầng

Đường đi có thể là:

~~~text
Database -> Java -> JSON -> JavaScript -> URL -> Java -> Database
~~~

Nếu một tầng đổi kiểu, cắt ngắn hoặc normalize ngoài hợp đồng, cùng một ID có thể bị biến thành giá trị khác.

Với ID số nguyên lớn, JSON number có thể hợp lệ về cú pháp nhưng một consumer không giữ chính xác giá trị. RFC 8259 nêu khoảng số nguyên có khả năng tương tác chính xác phổ biến là từ `-(2^53)+1` đến `(2^53)-1`. [Nguồn: RFC 8259, mục 6](https://www.rfc-editor.org/rfc/rfc8259.html#section-6).

Một lựa chọn cho ID lớn là trao đổi dưới dạng chuỗi theo hợp đồng API:

~~~json
{
  "userId": "9007199254740993"
}
~~~

Không chuyển chuỗi đó sang kiểu số trung gian nếu việc chuyển có thể mất chính xác.

### 12.2. Canonicalization phải theo loại ID

Trong ví dụ LocalUserId, hai biểu diễn hex hoa/thường được parse thành cùng giá trị UUID rồi xuất bằng một dạng chuẩn.

Với opaque subject, không được tự áp dụng cùng quy tắc. Những thao tác như:

~~~text
trim
lowercase
bỏ dấu
Unicode normalization
bỏ số 0 đầu
bỏ dấu phân cách
~~~

có thể làm hai ID khác nhau trở thành một hoặc làm ID không còn khớp nguồn.

Tên đăng nhập hướng đến con người có thể có quy tắc chuẩn hóa riêng. Đừng áp dụng quy tắc đó một cách ngầm định cho khóa danh tính máy cấp.

Nếu một giá trị tham gia chữ ký, MAC hoặc một giao thức định dạng cụ thể, cách chuẩn hóa phải tuân theo chính giao thức đó. Không tự thay đổi chuỗi rồi kỳ vọng cơ chế xác minh vẫn giữ nguyên ý nghĩa.

### 12.3. Đừng dùng tính có thứ tự làm bằng chứng nghiệp vụ

ID tuần tự hoặc có thành phần thời gian có thể hỗ trợ một số thao tác lưu trữ. Tuy nhiên:

~~~text
ID lớn hơn
    không tự chứng minh
quyền mới hơn, phiên bản mới hơn hoặc transaction commit sau.
~~~

Nếu cần `createdAt`, version, sequence của event stream hoặc thứ tự transaction, hãy có dữ liệu và hợp đồng tương ứng. Không suy ra tất cả từ ID tài khoản.

## 13. Không tái cấp ID trong vòng đời tài khoản

### 13.1. Rename không tạo tài khoản mới

Những thay đổi sau thường không đòi hỏi đổi ID của cùng account:

~~~text
Đổi tên hiển thị.
Đổi email liên hệ.
Đổi username theo chính sách.
Chuyển OU trong directory.
Thêm một phương thức đăng nhập được xác minh.
~~~

Cần cập nhật alias hoặc mapping theo use case, giữ tham chiếu ổn định.

### 13.2. Delete rồi tạo mới không phải rename

Nếu account cũ đã kết thúc và account mới được tạo, không cấp lại ID cũ chỉ vì tên hoặc email giống nhau.

Các hệ thống khác có thể vẫn giữ:

- Quyền sở hữu tài nguyên.
- Grant hoặc group membership.
- Event lịch sử.
- Audit.
- Cache hoặc credential còn tồn tại.
- Liên kết trong bản sao dữ liệu.

Tái cấp ID có thể làm những tham chiếu cũ trỏ sang chủ thể mới.

### 13.3. Tombstone không nhất thiết giữ nguyên toàn bộ hồ sơ

Hệ thống có thể giữ thông tin tối thiểu để nhận biết ID đã được cấp và trạng thái kết thúc, theo chính sách dữ liệu của mình.

Mục tiêu là tránh dùng lại ID sai hợp đồng và giữ tính đúng của tham chiếu cần thiết. Không mặc định phải giữ mọi dữ liệu cá nhân vô thời hạn.

Nếu dùng sequence, chỉ dựa vào ID lớn nhất đang còn trong bảng có thể không đủ để biết mọi ID từng được cấp. Bản ghi bị xóa và hệ thống bên ngoài vẫn có thể giữ tham chiếu cũ.

### 13.4. Phục hồi backup phải xét miền ID đã phát hành

Backup cũ có thể không biết những ID đã được cấp sau thời điểm chụp. Phục hồi bộ đếm hoặc trạng thái generator cũng có thể làm xuất hiện giá trị đã dùng.

Cần thiết kế việc phục hồi cùng với các hệ thống nhận ID, cơ chế reservation/tombstone và khả năng replay dữ liệu. Không chỉ xác nhận rằng bảng sau restore không có hai hàng trùng.

Với bộ sinh ngẫu nhiên, vẫn cần kiểm tra quy trình nhân bản trạng thái, import và cấp lại dữ liệu. Không dùng xác suất lý tưởng để bỏ qua toàn bộ quy trình khôi phục.

## 14. Migration, liên kết và gộp tài khoản

### 14.1. Đổi khóa vật lý không bắt buộc đổi định danh công khai

Một hệ thống có thể đổi kiểu khóa chính trong cơ sở dữ liệu nhưng vẫn giữ public ID hoặc external mapping ổn định qua một lớp ánh xạ.

Cần phân biệt:

~~~text
Đổi cách lưu ID.
Đổi ID được công bố.
Đổi đối tượng mà ID tham chiếu.
~~~

Ba việc có rủi ro và điều kiện nghiệm thu khác nhau.

### 14.2. Migration cần bảng ánh xạ và kiểm tra toàn vẹn

Một kế hoạch minh họa:

~~~text
1. Xác định namespace và định danh nguồn/đích.
2. Tạo ánh xạ old key -> new key.
3. Phát hiện trùng hoặc nhập nhằng trước khi áp dụng.
4. Chuyển các tham chiếu được cấp quyền migration.
5. Xác minh foreign key, mapping và trạng thái account.
6. Xử lý cache, event và consumer theo hợp đồng tương thích.
7. Giữ đường truy vết hoặc rollback phù hợp trong phạm vi cho phép.
~~~

Không tự chọn một account làm “đúng” rồi ghi đè account khác khi phát hiện cùng email hoặc khóa bị chuẩn hóa trùng.

Nếu có ID từ nhiều directory, khóa nguồn trong bảng migration phải bao gồm namespace. `oldId = 1001` riêng lẻ có thể nhập nhằng.

### 14.3. Gộp account là thay đổi quyền nhạy cảm

Hai account được cho là cùng một người vẫn có thể có các mục đích khác nhau, chẳng hạn account thường và account quản trị.

Khi gộp hoặc liên kết, cần xác định:

- Ai có thẩm quyền cho phép?
- Bằng chứng nào chứng minh quan hệ?
- Account nào còn là đối tượng hoạt động?
- Quyền, tài nguyên và phiên cũ được xử lý ra sao?
- Audit lịch sử được diễn giải thế nào?
- Có được gộp các grant không, hay phải xét lại từng loại?

Không lấy hợp của mọi quyền một cách mặc định. Cũng không sửa audit cũ thành như thể account đích đã thực hiện mọi hành động trước đây.

Một alias cho ID cũ có thể hỗ trợ tương thích, nhưng phải có policy rõ ràng. Nó không được vô tình trở thành đường truy cập để account mới kế thừa mọi quyền ngoài ý định migration.

## 15. ID, quyền riêng tư và khả năng quan sát

### 15.1. ID opaque vẫn có thể liên kết hoạt động

Một UUID không chứa tên người dùng vẫn có thể giúp liên kết log, request và dữ liệu nếu cùng giá trị được dùng rộng rãi.

Không nên suy ra “không có tên/email trong ID” nghĩa là mọi việc công khai ID đều không có tác động. Cần xem ID cho phép bên nhận ghép dữ liệu gì.

Nếu sản phẩm cần giảm liên kết giữa các ứng dụng, có thể cần định danh khác theo miền sử dụng cùng một mapping nội bộ có kiểm soát. Không tự gửi ID nội bộ toàn nền tảng cho mọi bên thứ ba nếu họ chỉ cần một tham chiếu riêng.

### 15.2. Không nhúng dữ liệu nhạy cảm để dễ đọc

Những dạng như:

~~~text
ngày-sinh + mã-nhân-viên
email + tên-công-ty
mã-tenant + chức-danh-quản-trị
~~~

có thể làm lộ thông tin hoặc gắn ID vào dữ liệu dễ thay đổi.

Một prefix phục vụ loại tài nguyên có thể hữu ích nếu không chứa dữ liệu không cần công khai. Cần phân biệt nhãn kỹ thuật với thông tin cá nhân hoặc quyền.

### 15.3. Audit dùng ID ổn định và đúng loại

Một event có thể ghi:

~~~text
actorUserId
actorWorkloadId nếu có
targetResourceType
targetNamespace
targetResourceId
tenantId nếu thao tác có phạm vi tenant
action
outcome
requestId
occurredAt
~~~

Không ghi `sessionId` vào trường `actorUserId` chỉ vì cả hai trông giống UUID. Một tài khoản có thể có nhiều session và credential; vòng đời của chúng không giống nhau.

ID là dữ liệu hỗ trợ truy vết, không phải lý do để log token, password hoặc secret liên quan.

## 16. Ma trận kiểm thử

Theo hợp đồng LocalUserId của ví dụ:

| Tình huống | Kỳ vọng |
| --- | --- |
| UUIDv4 đúng cấu trúc và variant | Parse thành LocalUserId |
| Cùng UUID với hex hoa/thường | Cùng giá trị nội bộ, xuất theo một dạng chuẩn |
| Chuỗi có khoảng trắng đầu/cuối | Bị từ chối theo profile ví dụ |
| Chuỗi thiếu ký tự hoặc sai vị trí dấu phân cách | Bị từ chối |
| UUID version khác với profile v4 nội bộ | Bị từ chối; không áp dụng quy tắc này cho ID nguồn ngoài |
| ID parse hợp lệ nhưng không có user record | Không coi là account tồn tại |
| Hai directory trả cùng local source ID | Khóa có namespace vẫn phân biệt |
| Cùng subject nhưng issuer/provider khác | Không tự ánh xạ cùng account |
| Hai tuple có thể trùng khi nối bằng dấu hai chấm | Encoding/khóa ghép không được nhập nhằng |
| Email đổi nhưng account vẫn là cùng đối tượng | LocalUserId và tham chiếu giữ nguyên |
| Email/DN được cấp cho account mới | Không kế thừa mapping hoặc tài nguyên cũ |
| Hai request cấp phát đồng thời cùng external key | Ràng buộc unique chốt một mapping theo hợp đồng |
| Va chạm LocalUserId mới sinh | Không trả account đang mang ID đó như account mới |
| Retry provisioning sau timeout | Không tạo trùng hoặc chiếm liên kết ngoài quyền |
| ID số vượt phạm vi chính xác của consumer | Giá trị qua API giữ nguyên theo hợp đồng chuỗi |
| ID nhóm được truyền vào vị trí ID user | Kiểu/tra cứu/policy phù hợp ngăn nhầm loại |
| Request có ID hợp lệ nhưng sai tenant/quyền | Bị chặn bởi policy |
| Restore hoặc migration có khóa cũ trùng | Phát hiện và xử lý trước khi làm sai liên kết |

Cần kiểm tra cả những thuộc tính khó thấy qua unit test đơn lẻ:

1. Unique constraint có đúng namespace và ngữ nghĩa so sánh không?
2. Có tầng nào cắt ngắn, lowercase hoặc chuyển kiểu ngoài hợp đồng không?
3. Cache key có bao gồm loại tài nguyên và namespace cần thiết không?
4. Luồng xử lý unique violation có phân biệt va chạm ID với idempotency không?
5. Xóa/tạo mới hoặc nhập lại dữ liệu có tái cấp ID đã phát hành không?
6. Migration có giữ được owner, membership, identity mapping và audit không?
7. Endpoint có xét quyền trên đối tượng sau khi parse ID không?

Ma trận là hướng dẫn để xây dựng kiểm thử, không phải báo cáo rằng đoạn Java hoặc schema trong bài đã được chạy trên một hệ thống thật.

## 17. Bài tập vận dụng

Một nền tảng dự án đang dùng email làm khóa người dùng. Nó cần tích hợp hai directory, hỗ trợ nhiều tenant và cho phép người dùng đổi email.

Hãy thiết kế:

- ID nội bộ ổn định của account.
- Namespace cho mỗi nguồn danh tính.
- Khóa ánh xạ từ danh tính nguồn sang account.
- Cách lưu alias email/username mà không dùng chúng thay ID.
- Foreign key của project owner và group membership.
- Quy trình tạo mới, retry và xử lý xung đột.
- Cách phân biệt rename với delete rồi tạo lại.
- Kế hoạch migration tham chiếu đang lưu bằng email.
- Kiểm tra quyền khi một request cung cấp ID người dùng khác.
- Xử lý audit và dữ liệu đã phát hành sau khi account đóng.

Một thiết kế đủ rõ phải trả lời được: **ID này định danh đối tượng nào, do ai cấp, duy nhất trong phạm vi nào, được giữ ổn định đến khi nào và có được trao lại cho đối tượng khác không?**
