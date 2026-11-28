# Kiểm soát việc làm lộ mật khẩu và thuộc tính nhạy cảm

## 1. Vì sao ánh xạ kết quả LDAP là một ranh giới bảo mật?

Trong **Spring Data LDAP**, ứng dụng truy vấn directory bằng repository hoặc `LdapTemplate`, rồi ánh xạ entry LDAP thành object Java. Các object này có thể đi tiếp qua service, cache, log, message queue, API response hoặc hệ thống phân tích. Nếu ánh xạ quá nhiều thuộc tính, một truy vấn danh bạ tưởng như vô hại có thể đưa dữ liệu bí mật vào những nơi không có quyền xem dữ liệu đó.

Ví dụ, một entry người dùng có thể chứa:

~~~ldif
dn: uid=alice,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
sn: Nguyen
mail: alice@example.org
telephoneNumber: +84 28 1234 5678
employeeNumber: E-1042
userPassword: {SSHA}...
~~~

Một màn hình danh bạ có thể chỉ cần `uid`, `cn` và `mail`. Nếu Search yêu cầu toàn bộ attributes, hoặc entity Java khai báo cả `userPassword`, dữ liệu nhạy cảm có thể được tải vào heap, vô tình serialize thành JSON, ghi vào log hoặc được cache.

Bài học này tập trung vào việc **chỉ đọc, ánh xạ và công bố đúng dữ liệu cần thiết**. Cần phân biệt rõ:

- **Bind credential:** mật khẩu mà ứng dụng dùng để bind vào LDAP, thường được cấu hình trong `ContextSource` hoặc secret store. Nó không phải một attribute mà ứng dụng cần Search để đăng nhập.
- **`userPassword`:** attribute có thể lưu password verifier/hash trong entry LDAP. Đây vẫn là dữ liệu xác thực nhạy cảm và ứng dụng danh bạ không nên đọc.
- **Thuộc tính cá nhân và phân quyền:** email, số điện thoại, mã nhân viên, nhóm, manager, certificate, ảnh và custom attributes có thể nhạy cảm theo mục đích sử dụng.
- **DN và filter:** có thể chứa tên đăng nhập, đơn vị hoặc dữ liệu cá nhân; chúng cũng cần được bảo vệ trong log và trace.

Sau bài này, người học có thể:

1. Thiết kế Search projection bằng allow-list thuộc tính.
2. Phân biệt bind password với attribute `userPassword`.
3. Ánh xạ LDAP entry vào ODM entity và DTO an toàn.
4. Kết hợp quyền LDAP tối thiểu với kiểm soát ở tầng ứng dụng.
5. Tránh rò rỉ qua log, exception, API response, cache và export.
6. Kiểm thử để chứng minh thuộc tính nhạy cảm không đi qua ranh giới không được phép.

> **Nguyên tắc:** Không tải một thuộc tính nhạy cảm chỉ vì nó tồn tại trong directory. Chỉ yêu cầu các attribute được nghiệp vụ cho phép, ánh xạ vào kiểu dữ liệu tối thiểu và kiểm tra quyền trước khi trả kết quả ra ngoài.

## 2. Phân loại dữ liệu trong LDAP

Không phải mọi attribute đều có cùng mức độ nhạy cảm. Trước khi viết mapper, hãy lập danh sách dữ liệu và mục đích sử dụng.

| Nhóm dữ liệu | Ví dụ | Rủi ro khi làm lộ |
| --- | --- | --- |
| Định danh tài khoản | `uid`, DN, `entryUUID`, `objectGUID` | Liên kết danh tính giữa hệ thống, dò tìm tài khoản |
| Thông tin hiển thị | `cn`, `displayName`, `sn` | PII, có thể bị lạm dụng để nhận diện |
| Liên hệ | `mail`, `telephoneNumber`, `mobile` | Spam, phishing, xâm phạm riêng tư |
| Thông tin tổ chức | `employeeNumber`, `departmentNumber`, `manager`, `title` | Lộ cấu trúc tổ chức và thông tin nhân sự |
| Phân quyền | `memberOf`, `member`, role/custom group attributes | Lộ quyền, nhóm đặc quyền và quan hệ truy cập |
| Xác thực | `userPassword`, password verifier, credential metadata | Tấn công offline, chiếm tài khoản |
| Bí mật ứng dụng | API key, token, custom secret attributes | Truy cập trái phép vào dịch vụ khác |
| Dữ liệu nhị phân | `jpegPhoto`, certificate, key material | Lộ ảnh, danh tính chứng thư hoặc khóa |
| Operational metadata | `createTimestamp`, `modifyTimestamp`, `entryUUID` | Lộ lịch sử hoặc dấu vết nội bộ nếu công bố rộng |

Mức độ nhạy cảm phụ thuộc chính sách tổ chức, schema và ngữ cảnh. Ví dụ `mail` có thể được hiển thị trong danh bạ nội bộ nhưng không được công khai trên API internet; `memberOf` có thể là dữ liệu cần thiết cho một dịch vụ phân quyền nhưng không phù hợp để trả về cho màn hình hồ sơ.

### 2.1. `userPassword` không phải bind password

Hai khái niệm này thường bị nhầm:

- Khi ứng dụng kết nối LDAP, nó gửi bind DN và credential tới directory server qua cơ chế bind. Spring LDAP lấy credential từ cấu hình `ContextSource` hoặc một nguồn xác thực được thiết kế riêng.
- Attribute `userPassword` thuộc entry LDAP và có thể chứa password verifier/hash do directory quản lý. Nó không phải giá trị mà ứng dụng cần đọc để kiểm tra mật khẩu người dùng.

Đăng nhập người dùng nên dùng **LDAP bind/authentication flow** hoặc cơ chế xác thực của Spring Security phù hợp. Không Search `userPassword`, không so sánh mật khẩu do người dùng nhập với hash lấy từ directory và không ghi giá trị này ra log.

Một số directory không cho phép đọc `userPassword` đối với bind identity thông thường; một số môi trường quản trị có thể cấp quyền đọc. Việc server từ chối không làm cho attribute này bớt nhạy cảm. Hãy cấu hình ACL để tài khoản ứng dụng không có quyền đọc password verifier nếu nghiệp vụ không cần.

### 2.2. TLS bảo vệ đường truyền, không bảo vệ mọi nơi sau khi nhận dữ liệu

LDAPS hoặc StartTLS bảo vệ dữ liệu khi truyền giữa client và directory nếu certificate, hostname và trust chain được xác minh đúng. TLS không ngăn ứng dụng:

- Đọc quá nhiều attributes.
- Serialize dữ liệu nhạy cảm thành response.
- Ghi password/hash vào log.
- Đưa dữ liệu vào cache hoặc queue không phù hợp.
- Cho một service account quyền truy cập vượt nhu cầu.

Bảo mật cần nhiều lớp: **ACL ở LDAP, projection ở Search, mapping an toàn, kiểm soát service/API và quản lý log/cache**.

## 3. Chỉ yêu cầu các attributes được phép

### 3.1. Vì sao không nên Search toàn bộ attributes?

Trong JNDI `SearchControls`, danh sách returning attributes quyết định các thuộc tính được trả trong kết quả Search. Nếu không chỉ định danh sách cụ thể, provider có thể yêu cầu các user attributes theo mặc định. Dùng wildcard như `*` để lấy tất cả user attributes hoặc `+` để lấy operational attributes sẽ mở rộng dữ liệu nhận được.

Không dùng các cấu hình sau cho màn hình danh bạ thông thường:

~~~java
controls.setReturningAttributes(null); // Có thể yêu cầu tất cả user attributes.
controls.setReturningAttributes(new String[] {"*"}); // Tất cả user attributes.
controls.setReturningAttributes(new String[] {"*", "+"}); // Cả user và operational attributes.
~~~

Hãy dùng **allow-list** theo đúng nhu cầu:

~~~java
SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setReturningAttributes(
    new String[] {"uid", "cn", "mail"}
);
controls.setReturningObjFlag(false);
~~~

Danh sách trên chỉ yêu cầu `uid`, `cn` và `mail`. Không đưa `userPassword`, token hoặc custom secret attribute vào projection.

Nếu cần operational attribute như `entryUUID` để đồng bộ nội bộ, hãy yêu cầu rõ ràng và giữ nó trong luồng nội bộ. Không tự động đưa mọi operational attributes vào API response.

### 3.2. Projection là lớp giảm thiểu dữ liệu, ACL vẫn là lớp bắt buộc

Allow-list phía client giảm dữ liệu được tải về và giảm nguy cơ mapper vô tình sử dụng attribute ngoài ý muốn. Nhưng nó không thay thế quyền truy cập ở server:

- Nếu client có quyền đọc `userPassword`, một code path khác có thể vô tình yêu cầu nó.
- Nếu một endpoint mới thêm attribute vào projection, ACL quá rộng sẽ cho phép đọc ngay.
- Nếu credential bị lộ, attacker có thể dùng nó từ một client khác.

Vì vậy, bind identity của ứng dụng chỉ nên có quyền đọc những attribute/nhánh cần thiết. Với secret như `userPassword`, nên deny read cho tài khoản danh bạ và chỉ cấp quyền thay đổi password theo quy trình riêng nếu có nhu cầu.

### 3.3. Chọn attribute name từ cấu hình tin cậy

Giá trị assertion trong LDAP filter cần được escape, nhưng tên attribute cũng phải được kiểm soát. Không nhận tên attribute tùy ý từ request rồi nối vào SearchControls hoặc filter:

~~~java
// Không an toàn: caller tự chọn attribute cần đọc.
String attributeName = request.getParameter("attribute");
controls.setReturningAttributes(new String[] {attributeName});
~~~

Thay vào đó, định nghĩa projection theo use case:

~~~java
enum PersonProjection {
    DIRECTORY_CARD,
    INTERNAL_SYNC,
    AUTHORIZATION_CHECK
}
~~~

Mỗi projection có allow-list riêng trong code và được review. Người gọi API chọn một use case được phép, không tự quyết định đọc `userPassword`, `memberOf` hoặc custom attributes.

## 4. Ánh xạ an toàn bằng AttributesMapper và ContextMapper

### 4.1. Tạo DTO chỉ chứa dữ liệu cần công bố

Ví dụ màn hình danh bạ cần tên, UID và email:

~~~java
public record PersonCard(
    String uid,
    String displayName,
    String email
) {}
~~~

DTO này không có field DN, password, group membership, employee number hoặc raw LDAP attributes. Nếu một use case khác cần stable ID nội bộ, hãy tạo kiểu dữ liệu nội bộ riêng thay vì mở rộng DTO công khai cho mọi người dùng.

### 4.2. Search với projection và ContextMapper

~~~java
import java.util.List;

import javax.naming.directory.SearchControls;

import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;

public List<PersonCard> findDirectoryCards(
        LdapTemplate ldapTemplate,
        String departmentNumber) {

    AndFilter filter = new AndFilter();
    filter.and(new EqualsFilter("objectClass", "inetOrgPerson"));
    filter.and(new EqualsFilter("departmentNumber", departmentNumber));

    SearchControls controls = new SearchControls();
    controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
    controls.setReturningAttributes(
        new String[] {"uid", "cn", "mail"}
    );
    controls.setReturningObjFlag(false);

    return ldapTemplate.search(
        "ou=people",
        filter.encode(),
        controls,
        (ContextMapper<PersonCard>) context -> {
            DirContextOperations entry =
                (DirContextOperations) context;

            return new PersonCard(
                entry.getStringAttribute("uid"),
                entry.getStringAttribute("cn"),
                entry.getStringAttribute("mail")
            );
        }
    );
}
~~~

Ví dụ minh họa một truy vấn danh bạ:

- Filter được dựng bằng `AndFilter` và `EqualsFilter`; giá trị phòng ban được encode theo LDAP filter syntax.
- Search chỉ yêu cầu `uid`, `cn`, `mail`.
- Mapper chỉ đọc ba attribute trong allow-list.
- DTO không mang theo `Attributes`, `DirContextOperations` hay password verifier.

Nếu kết quả lớn, overload trả về `List<PersonCard>` vẫn tích lũy toàn bộ DTO trong heap. Khi đó dùng callback và batch giới hạn như bài về duyệt kết quả; nguyên tắc allow-list vẫn giữ nguyên.

### 4.3. AttributesMapper cũng cần allow-list

Nếu chỉ cần attributes mà không cần DN/context:

~~~java
import org.springframework.ldap.core.AttributesMapper;

List<PersonCard> cards = ldapTemplate.search(
    "ou=people",
    filter.encode(),
    controls,
    (AttributesMapper<PersonCard>) attributes ->
        new PersonCard(
            stringValue(attributes, "uid"),
            stringValue(attributes, "cn"),
            stringValue(attributes, "mail")
        )
);
~~~

Helper:

~~~java
import javax.naming.NamingException;
import javax.naming.directory.Attributes;

private static String stringValue(
        Attributes attributes,
        String name) throws NamingException {

    var attribute = attributes.get(name);
    return attribute == null
        ? null
        : String.valueOf(attribute.get());
}
~~~

Không viết mapper tổng quát sao chép tất cả attribute thành `Map<String, Object>` rồi trả cho controller. Cách đó khiến mọi attribute mới được thêm vào schema có thể tự động đi vào response mà không qua review bảo mật.

### 4.4. Không trả raw JNDI/Spring LDAP object

Tránh trả trực tiếp các kiểu:

- `Attributes`
- `SearchResult`
- `DirContextOperations`
- `DirContextAdapter`
- `LdapEntryIdentification` nếu API không cần định danh nội bộ
- Entity ODM có field nội bộ không phù hợp với caller

Các object này phản ánh dữ liệu và cấu trúc directory. Chúng có thể chứa thêm attributes hoặc metadata mà API không nên công bố. Map sang DTO chuyên biệt trước khi đi qua ranh giới service/controller.

## 5. ODM entity và Spring Data LDAP Repository

### 5.1. Entity chỉ ánh xạ những thuộc tính được nghiệp vụ cho phép

Ví dụ entity cho luồng đọc danh bạ:

~~~java
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
    }
)
public class PersonEntry {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "mail")
    private String email;

    public PersonEntry() {}

    public Name getDn() { return dn; }
    public String getUid() { return uid; }
    public String getCommonName() { return commonName; }
    public String getEmail() { return email; }
}
~~~

Entity này không khai báo field `userPassword`, token hay custom secret attribute. Việc không khai báo field giúp giảm khả năng các giá trị đó được map vào object theo cấu hình ODM thông thường.

Tuy nhiên, đây không thay thế ACL hoặc Search projection. Nếu entity được dùng ở nhiều use case khác nhau, cần xem xét field nào thật sự cần thiết trong từng luồng và tránh dùng một entity quá rộng cho mọi API.

### 5.2. Repository không phải ranh giới API

Ví dụ:

~~~java
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository
        extends LdapRepository<PersonEntry> {
}
~~~

Service có thể gọi repository, sau đó map entity sang response DTO:

~~~java
public PersonCard toCard(PersonEntry person) {
    return new PersonCard(
        person.getUid(),
        person.getCommonName(),
        person.getEmail()
    );
}
~~~

Không trả trực tiếp entity ODM ra REST controller chỉ vì entity có thể serialize thành JSON. Entity phục vụ persistence/mapping; response DTO phục vụ hợp đồng API. Hai kiểu dữ liệu có mục đích và vòng đời khác nhau.

### 5.3. Cẩn thận khi mở rộng entity

Một thay đổi schema có thể thêm thuộc tính như `mobile`, `manager` hoặc `memberOf`. Không tự động thêm các field này vào entity danh bạ chỉ vì chúng có sẵn.

Trước khi thêm một `@Attribute`, hãy xác định:

1. Use case nào cần attribute?
2. Ai được phép đọc?
3. Attribute có PII, dữ liệu phân quyền hoặc bí mật không?
4. Nó có được trả ra API hay chỉ dùng nội bộ?
5. Nó có được cache, log hoặc export không?
6. Có cần kiểm thử ACL và response serialization không?

Không thêm `@Attribute(name = "userPassword")` vào entity dùng chung. Nếu hệ thống cần thay password, hãy dùng một command riêng với quyền Modify phù hợp; không đọc password verifier để thực hiện nghiệp vụ.

## 6. Dùng LDAP bind để xác thực, không Search password

### 6.1. Luồng xác thực

Mật khẩu người dùng được xác minh bằng LDAP bind hoặc cơ chế authentication được thiết kế cho directory:

~~~mermaid
sequenceDiagram
    participant U as User
    participant A as Application / Authentication
    participant L as LDAP server
    U->>A: Username + password qua TLS
    A->>L: Bind với danh tính người dùng
    L-->>A: Bind success / invalid credentials
    A-->>U: Kết quả xác thực
~~~

Ứng dụng không cần đọc `userPassword`. Directory server chịu trách nhiệm xác minh credential theo password policy và cơ chế lưu trữ của nó.

Một số mô hình dùng bind service account để tìm DN người dùng trước, sau đó bind bằng DN người dùng và password vừa nhận. Dù dùng mô hình nào:

- Không log password người dùng.
- Không lưu password trong session, cache hoặc job progress.
- Không đưa password vào LDAP filter.
- Không trả password verifier trong response.
- Không dùng tài khoản quản trị để bind thay người dùng rồi kết luận credential người dùng hợp lệ.

### 6.2. Bind credential của service account

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  ldap:
    urls: "${LDAP_URL:ldaps://ldap.example.org:636}"
    base: "${LDAP_BASE_DN:dc=example,dc=org}"
    username: "${LDAP_BIND_DN}"
    password: "${LDAP_BIND_PASSWORD}"
~~~

Các giá trị nhạy cảm được inject từ secret manager hoặc cơ chế cấu hình an toàn của môi trường triển khai. Không commit password thật vào Git, không in toàn bộ configuration properties khi debug và không đưa credential vào exception message.

Nếu cần nhiều mức quyền, có thể tách bind identity cho:

- Search danh bạ.
- Đồng bộ nội bộ.
- Thay đổi password hoặc thuộc tính quản trị.

Mỗi identity chỉ có quyền cần thiết. Không dùng một tài khoản có quyền đọc mọi attribute và ghi mọi entry cho toàn bộ ứng dụng.

### 6.3. Thay đổi password là một command riêng

Nếu ứng dụng có chức năng đổi password, đó là một nghiệp vụ ghi riêng:

- Xác thực người yêu cầu và quyền đổi password.
- Gửi thay đổi qua LDAPS/StartTLS với certificate được xác minh.
- Dùng operation/API phù hợp với password policy của directory.
- Không đọc lại `userPassword` để xác minh.
- Không log giá trị cũ/mới, password verifier hoặc payload Modify.
- Chỉ trả kết quả thành công/thất bại đã được chuẩn hóa.

Cách server lưu password (hash scheme, salt, policy, history, expiration) phụ thuộc directory. Không tự tạo một giá trị hash rồi ghi vào `userPassword` nếu chưa xác nhận format và password policy của server.

## 7. ACL và least privilege ở LDAP server

### 7.1. Quyền theo use case

Ví dụ ma trận quyền ở mức thiết kế:

| Bind identity | Đọc danh bạ | Đọc group membership | Đọc `userPassword` | Đổi password |
| --- | --- | --- | --- | --- |
| `app-directory-reader` | Các attribute được phép | Không hoặc chỉ phạm vi cần thiết | **Deny** | **Deny** |
| `app-sync-reader` | Attributes đồng bộ cần thiết | Theo hợp đồng đồng bộ | **Deny** | **Deny** |
| `app-password-writer` | Tối thiểu theo flow | Không | **Deny read** | Chỉ quyền Modify theo policy |
| Directory administrator | Theo nhiệm vụ quản trị | Theo nhiệm vụ quản trị | Chỉ khi thực sự cần và được kiểm soát | Theo quy trình quản trị |

Tên tài khoản chỉ là ví dụ. ACL thực tế có cú pháp khác nhau giữa OpenLDAP, Active Directory và directory vendor khác. Hãy kiểm thử bằng chính bind identity của ứng dụng thay vì chỉ kiểm tra bằng tài khoản quản trị.

### 7.2. Tách quyền đọc và quyền ghi

Một service chỉ hiển thị danh bạ không cần quyền Modify. Một service đồng bộ có thể cần đọc `entryUUID` hoặc các attribute nghiệp vụ nhưng không cần đọc password verifier.

Nếu chức năng đổi password dùng tài khoản riêng, cần xác định chính xác quyền Modify và cơ chế xác minh danh tính. Không cấp quyền đọc `userPassword` chỉ vì tài khoản đó có quyền thay đổi password.

### 7.3. Kiểm thử ACL ở server

Test tích hợp nên kiểm tra:

- Bind identity danh bạ đọc được `uid`, `cn`, `mail`.
- Identity đó không đọc được `userPassword`.
- Identity read-only không thể Modify/Delete entry.
- Identity ghi chỉ có quyền trên đúng subtree/attribute.
- Một endpoint mới thêm attribute nhạy cảm vào projection vẫn bị server ACL từ chối.

Tùy server, đọc attribute bị cấm có thể làm attribute bị ẩn, trả lỗi quyền hoặc trả Search result không có attribute. Test phải xác định hành vi được mong đợi của vendor và không suy diễn từ một server khác.

## 8. Bảo vệ dữ liệu qua API response

### 8.1. Response DTO là allow-list công khai

Ví dụ:

~~~java
public record PersonResponse(
    String username,
    String name,
    String email
) {}
~~~

Controller chỉ trả kiểu response:

~~~java
@GetMapping("/people/{uid}")
public PersonResponse getPerson(@PathVariable String uid) {
    PersonEntry entry = personService.findRequired(uid);

    return new PersonResponse(
        entry.getUid(),
        entry.getCommonName(),
        entry.getEmail()
    );
}
~~~

Trong thực tế cần thêm authorization ở service/controller để xác định caller được xem email hay không. Việc có field trong DTO không có nghĩa mọi người dùng đều được quyền nhận giá trị đó.

### 8.2. Không dựa riêng vào annotation serializer

Các annotation như `@JsonIgnore`, `@JsonView` hoặc `@JsonProperty(access = WRITE_ONLY)` có thể hỗ trợ serialization, nhưng không nên là lớp bảo vệ duy nhất:

- Code khác vẫn có thể đọc field.
- Một serializer hoặc message converter khác có thể không tuân theo annotation như mong muốn.
- Log `toString()` vẫn có thể in giá trị.
- Mapping sang event/cache có thể dùng object gốc.

Thiết kế an toàn hơn là **không đưa secret vào response model ngay từ đầu**. Dùng DTO riêng cho từng ranh giới và kiểm thử JSON serialization.

### 8.3. Phân quyền theo từng thuộc tính

Không phải mọi caller có cùng quyền xem mọi trường. Ví dụ:

| Caller | UID | Tên | Email | Điện thoại | Group membership |
| --- | --- | --- | --- | --- | --- |
| Nhân viên cùng tổ chức | Có | Có | Theo policy | Theo policy | Không mặc định |
| HR service | Có | Có | Theo nhiệm vụ | Theo nhiệm vụ | Không mặc định |
| Authorization service | Stable ID | Không cần | Không cần | Không cần | Chỉ nhóm cần kiểm tra |
| Public API | Theo thiết kế | Theo thiết kế | Thường hạn chế | Thường hạn chế | Không |

Có thể tạo các response model khác nhau hoặc áp dụng field-level authorization trong mapper. Tránh trả một object rộng rồi hy vọng frontend tự ẩn các field nhạy cảm.

## 9. Log, trace và exception không được trở thành kênh rò rỉ

### 9.1. Những dữ liệu không nên log

Không log:

- Bind password, password người dùng hoặc `userPassword`.
- Toàn bộ `Attributes`, `SearchResult`, `DirContextOperations`.
- Raw LDAP entry hoặc object ODM có field nhạy cảm.
- Full LDAP filter nếu filter chứa email, username, employee ID hoặc dữ liệu cá nhân.
- DN đầy đủ nếu DN chứa định danh cá nhân và không cần cho chẩn đoán.
- Request/response body có thông tin hồ sơ.
- Exception message chưa được kiểm tra có chứa filter, DN, credential hoặc attribute values không.

Ví dụ nguy hiểm:

~~~java
log.debug("LDAP attributes: {}", attributes);
log.debug("LDAP entry: {}", contextOperations);
log.warn("LDAP query failed, filter={}", filter, exception);
~~~

Các object có thể in ra nhiều giá trị hơn người viết dự kiến. Stack trace cũng có thể kèm message từ provider hoặc server.

### 9.2. Log metadata vận hành đã làm sạch

Có thể log:

~~~java
log.info(
    "LDAP lookup completed: operationId={}, resultCount={}, durationMs={}",
    operationId,
    resultCount,
    durationMs
);
~~~

Khi lỗi, ưu tiên log mã lỗi đã chuẩn hóa và correlation ID:

~~~java
log.warn(
    "LDAP lookup failed: operationId={}, errorCategory={}, exceptionType={}",
    operationId,
    safeErrorCategory,
    exception.getClass().getSimpleName()
);
~~~

Không đưa raw exception message vào log nếu chưa xác nhận nó không chứa dữ liệu nhạy cảm. Nếu cần stack trace để điều tra, hãy áp dụng bộ lọc/redaction và quyền truy cập log phù hợp. Không dùng DN/email làm metric label vì cardinality cao và có thể lộ PII.

### 9.3. Exception response không phản chiếu chi tiết LDAP

API nên trả lỗi tổng quát, ví dụ:

~~~json
{
  "code": "DIRECTORY_LOOKUP_FAILED",
  "message": "Không thể hoàn tất yêu cầu tra cứu.",
  "correlationId": "op-7f42"
}
~~~

Không trả raw `NamingException`, LDAP result diagnostic message, bind DN, server hostname nội bộ, filter hoặc attributes cho caller. Thông tin kỹ thuật chi tiết được giữ ở kênh vận hành có kiểm soát.

## 10. Cache, message queue và export

### 10.1. Cache chỉ lưu dữ liệu cần cho use case

Không cache password, password verifier, bind credential hoặc token xác thực. Với PII và group membership:

- Xác định mục đích và thời hạn cache.
- Giới hạn quyền đọc cache.
- Mã hóa at-rest khi chính sách yêu cầu.
- Có cơ chế invalidate khi entry hoặc membership thay đổi.
- Tránh cache toàn bộ LDAP entity nếu caller chỉ cần DTO nhỏ.
- Không dùng cache key chứa DN/username nhạy cảm nếu không cần.

Cache không phải lý do để giữ dữ liệu vượt quá mục đích ban đầu.

### 10.2. Message/event chỉ mang dữ liệu cần thiết

Khi phát event:

~~~java
public record PersonChangedEvent(
    String stableId,
    String username,
    String displayName,
    String changeType
) {}
~~~

Không serialize toàn bộ ODM entity vào queue. Consumer có thể có quyền thấp hơn producer và retention của message broker có thể dài. Nếu consumer cần dữ liệu khác, thiết kế event contract riêng hoặc để consumer truy vấn nguồn theo quyền của nó.

### 10.3. Export và báo cáo

Export CSV/Excel/JSON cần một projection riêng, được duyệt theo người nhận và mục đích. Không dùng `attributes=*` rồi ghi toàn bộ entry ra file. File export cần:

- Chỉ có cột được phê duyệt.
- Quyền truy cập và retention phù hợp.
- Audit người tạo/người tải.
- Mã hóa hoặc kênh truyền an toàn khi chứa PII.
- Xóa file tạm theo chính sách.
- Kiểm tra nội dung trước khi gửi ra ngoài.

## 11. Filter an toàn và bảo vệ dữ liệu tìm kiếm

### 11.1. Escape filter value

Giá trị filter có thể là dữ liệu cá nhân. Ngoài việc không log, cần chống LDAP filter injection:

~~~java
import org.springframework.ldap.filter.EqualsFilter;

EqualsFilter filter =
    new EqualsFilter("uid", requestedUid);

String encoded = filter.encode();
~~~

Không nối chuỗi:

~~~java
// Không an toàn.
String filter = "(uid=" + requestedUid + ")";
~~~

Các ký tự đặc biệt trong LDAP filter phải được escape theo RFC 4515. DN có quy tắc escape riêng theo RFC 4514; không dùng một hàm escape cho cả hai.

### 11.2. Allow-list attribute name và filter structure

Không cho caller điều khiển:

- Tên attribute tùy ý.
- Base DN hoặc naming context bất kỳ.
- Search scope không giới hạn.
- Các filter clause đặc quyền.
- Projection có chứa password/token.

Hãy xây filter theo use case và kiểm tra input ở tầng service. Một filter đã encode vẫn có thể quá rộng hoặc tiết lộ dữ liệu nếu quyền và phạm vi truy vấn không được kiểm soát.

## 12. Kiểm thử để chứng minh không rò rỉ

### 12.1. Test projection không yêu cầu password

Trong integration test với LDAP server test, xác minh Search chỉ yêu cầu thuộc tính công khai:

~~~java
SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setReturningAttributes(
    new String[] {"uid", "cn", "mail"}
);
controls.setReturningObjFlag(false);
~~~

Đọc kết quả qua mapper và xác nhận object chỉ chứa các trường dự kiến. Không dựa vào việc server tự ẩn `userPassword`; projection cần đúng ngay cả khi server test cấp quyền rộng.

### 12.2. Test response không chứa secret

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;

import static org.assertj.core.api.Assertions.assertThat;

@Test
void publicResponseDoesNotExposeCredentialAttributes() throws Exception {
    PersonResponse response =
        new PersonResponse("alice", "Alice Nguyen", "alice@example.org");

    String json = new ObjectMapper().writeValueAsString(response);

    assertThat(json).doesNotContain(
        "userPassword",
        "password",
        "secret",
        "{SSHA}"
    );
}
~~~

Test này kiểm tra hợp đồng JSON của DTO. Trong test thực tế, không cần đặt password thật trong fixture; có thể dùng marker giả để xác nhận dữ liệu bí mật không xuất hiện ở response.

### 12.3. Test ACL với bind identity của ứng dụng

Dùng chính service account trong môi trường test:

1. Search `uid`, `cn`, `mail` thành công.
2. Search `userPassword` bị từ chối hoặc attribute không được trả theo ACL.
3. Modify/Delete bị từ chối với identity chỉ đọc.
4. Identity password writer chỉ có quyền thay đổi theo policy.
5. Một thuộc tính nhạy cảm mới thêm vào projection không thể được đọc nếu ACL chưa cấp quyền.

Kết quả cụ thể phụ thuộc server. Kiểm thử phải chạy với vendor/schema/ACL tương ứng, không suy ra từ embedded server khác.

### 12.4. Test log và exception redaction

Có thể dùng appender test để thu log trong các tình huống:

- Bind thất bại.
- Search không tìm thấy entry.
- ACL từ chối attribute.
- Directory timeout.
- Mapper ném lỗi.
- Downstream serialization thất bại.

Assert rằng log không chứa marker password, raw filter value, full DN nhạy cảm hoặc attribute values. Kiểm tra cả message lẫn throwable stack trace. Test này giúp phát hiện việc một thay đổi debug vô tình in object JNDI.

## 13. Checklist bảo mật trước production

**LDAP Search và mapping**

- [ ] Mọi Search có projection allow-list rõ ràng.
- [ ] Không dùng wildcard `*`, `+` hoặc returning attributes mặc định cho use case thông thường.
- [ ] Không yêu cầu `userPassword`, token hoặc custom secret attribute.
- [ ] Mapper chỉ đọc các attribute được phép.
- [ ] Không trả raw `Attributes`, `SearchResult` hoặc `DirContextOperations`.
- [ ] ODM entity không khai báo credential field dùng chung.

**Quyền và kết nối**

- [ ] Bind identity có quyền tối thiểu.
- [ ] ACL deny read cho password verifier với ứng dụng không cần quyền đó.
- [ ] Quyền Modify tách khỏi quyền Search khi phù hợp.
- [ ] LDAPS/StartTLS xác minh CA và hostname.
- [ ] Bind credentials lấy từ secret store, không commit hoặc log.

**API và observability**

- [ ] Controller trả DTO riêng, có field-level authorization.
- [ ] Log không chứa password, raw attributes, filter hoặc DN nhạy cảm.
- [ ] Exception response không phản chiếu diagnostic message.
- [ ] Cache/event/export chỉ chứa dữ liệu cần thiết.
- [ ] Metric không dùng PII làm label.
- [ ] Có test response, ACL và log redaction.

## 14. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Search toàn bộ attributes | Dữ liệu nhạy cảm đi vào heap | Projection allow-list |
| Đưa `userPassword` vào ODM entity | Password verifier có thể đi qua nhiều tầng | Không đọc/không map credential |
| Dùng bind password để so sánh với `userPassword` | Sai mô hình xác thực, tăng rủi ro lộ hash | LDAP bind/authentication flow |
| Nghĩ TLS đủ bảo vệ dữ liệu | Secret vẫn có thể lộ trong log/response/cache | Bảo vệ toàn bộ data lifecycle |
| Trả trực tiếp ODM entity ra REST | Lộ field nội bộ khi entity mở rộng | Response DTO riêng |
| Serialize `Attributes` hoặc `SearchResult` | Lộ attributes không dự kiến | Map allow-list sang DTO |
| Dùng một service account admin cho mọi use case | Phạm vi thiệt hại lớn khi credential bị lộ | Least privilege và tách quyền |
| Dựa riêng vào `@JsonIgnore` | Kênh log/event khác vẫn có thể lộ field | Không đưa secret vào DTO |
| Log filter, DN và exception message | Lộ PII, cấu trúc directory hoặc dữ liệu xác thực | Log metadata đã làm sạch |
| Cache toàn bộ entry | Lưu PII/secret lâu hơn mục đích | Cache projection, TTL và ACL |
| Cho caller chọn attribute name | Có thể yêu cầu đọc field nhạy cảm | Projection allow-list theo use case |
| Dùng filter nối chuỗi | LDAP filter injection | Filter builder/encoder |
| Cấp quyền đọc `userPassword` cho password writer | Credential verifier có thể bị lộ | Quyền Modify riêng, deny read nếu không cần |
| Dùng embedded LDAP để kết luận ACL production | Hành vi vendor khác nhau | Test trên đúng directory/ACL |

## 15. Câu hỏi tự kiểm tra

1. Bind password khác attribute `userPassword` như thế nào?
2. Vì sao ứng dụng không nên Search `userPassword` để xác thực người dùng?
3. `SearchControls.setReturningAttributes` giúp giảm rủi ro nào?
4. Sự khác biệt giữa projection allow-list và LDAP ACL là gì?
5. Khi nào cần yêu cầu operational attribute như `entryUUID`?
6. Vì sao không dùng `*` hoặc `+` cho Search danh bạ thông thường?
7. `returningObjFlag=false` có thay thế ACL hay không?
8. Vì sao không nên trả `Attributes`, `SearchResult` hoặc `DirContextOperations` ra API?
9. ODM entity nên chứa những field nào?
10. Vì sao response DTO cần tách khỏi entity repository?
11. `@JsonIgnore` có đủ để bảo vệ secret trên mọi kênh không?
12. Service account đọc danh bạ nên có quyền Modify không?
13. Password writer có cần quyền đọc password verifier không?
14. TLS bảo vệ những gì và không bảo vệ những gì?
15. Vì sao không nên log raw LDAP filter hoặc DN?
16. Filter value và DN cần escape theo các quy tắc nào?
17. Làm thế nào để test response không chứa secret?
18. Vì sao ACL test phải dùng chính bind identity của ứng dụng?
19. Những rủi ro nào xuất hiện khi cache toàn bộ LDAP entity?
20. Khi schema thêm attribute nhạy cảm mới, quy trình review mapping nên thay đổi ra sao?

## 16. Tổng kết

Kiểm soát rò rỉ trong Spring Data LDAP bắt đầu từ **giảm thiểu dữ liệu tại Search**: chỉ yêu cầu attributes cần thiết, không lấy wildcard và không đọc password verifier cho nghiệp vụ danh bạ. `userPassword` khác với bind credential của `ContextSource`; xác thực người dùng phải đi qua LDAP bind/authentication flow thay vì đọc và so sánh hash.

Sau Search, mapper nên tạo DTO allow-list, ODM entity chỉ chứa field cần thiết và API không trả trực tiếp object JNDI hoặc entity persistence. LDAP ACL phải giới hạn quyền đọc/ghi của từng bind identity; TLS bảo vệ đường truyền nhưng không ngăn rò rỉ ở log, cache, event hay response. Filter, DN, exception và audit cần được làm sạch theo chính sách dữ liệu.

**Bảo mật không kết thúc ở câu lệnh Search.** Nó bao gồm toàn bộ đường đi từ directory tới heap, service, API, cache, queue, log và file export. Khi mỗi ranh giới có projection, quyền, DTO và test phù hợp, ứng dụng chỉ đưa đúng dữ liệu cần thiết tới đúng người nhận.

### Tài liệu tham khảo

- [Spring LDAP Reference — Basic Usage and LdapTemplate](https://docs.spring.io/spring-ldap/reference/basic-usage.html).
- [Spring LDAP Reference — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html).
- [Spring LDAP API — LdapTemplate](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html).
- [RFC 4511 — LDAPv3 Protocol: Search and Bind Operations](https://www.rfc-editor.org/rfc/rfc4511).
- [RFC 4515 — LDAP String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515).
- [RFC 4519 — LDAP Schema for User Applications (`userPassword`)](https://www.rfc-editor.org/rfc/rfc4519).
- [OWASP Cheat Sheet Series — Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html).
- [OWASP Cheat Sheet Series — Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).
