# Cô lập dữ liệu và quyền thao tác theo nhánh thư mục

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Thiết kế Directory Information Tree (DIT) theo các nhánh dữ liệu có ranh giới quản trị và bảo mật rõ ràng.
2. Phân biệt phạm vi truy vấn do client chọn với quyền truy cập do LDAP server thực thi.
3. Xác định authorization identity của một LDAP operation và hiểu tác động của bind account dùng chung.
4. Phân quyền riêng cho search, read, compare, authenticate, add, modify, delete và Modify DN.
5. Viết policy subtree/attribute ACL theo nguyên tắc least privilege trên OpenLDAP và hiểu mô hình DACL của Active Directory.
6. Cấu hình Spring LDAP để dùng đúng ContextSource/LdapTemplate và tránh vô tình nâng quyền qua service account.
7. Kiểm tra quyền trên cả entry, attribute, parent và các DN-valued reference.
8. Xây dựng integration test âm tính để chứng minh một principal không thể đọc hoặc thay đổi nhánh ngoài phạm vi.

Bài thuộc chương **Bảo mật dữ liệu** của module SPRING_DATA_LDAP. Module giúp ứng dụng Java truy cập dịch vụ thư mục LDAP qua Spring Data LDAP repository, ánh xạ entry phân cấp sang object Java, hiểu DN, objectClass, schema, truy vấn repository/LdapTemplate, CRUD, filter an toàn, bảo mật kết nối và kiểm thử với directory.

Trong LDAP, cấu trúc DIT thường được dùng để phân chia dữ liệu theo đơn vị quản trị, ứng dụng, tenant hoặc loại đối tượng. Cấu trúc đó giúp định tuyến truy vấn và tổ chức quyền. Tuy nhiên, chỉ đặt entry vào OU riêng chưa tạo ra ranh giới bảo mật. LDAP server phải kiểm tra authorization identity và ACL trên từng operation. Ứng dụng cũng cần xác thực người gọi, xác định nhánh mà họ được phép thao tác và dùng credential có quyền tối thiểu.

## 1. Cô lập dữ liệu bằng cấu trúc nhánh DIT

LDAP lưu entry theo cây. Một DN xác định vị trí của entry; các entry nằm dưới cùng một ancestor tạo thành subtree.

### 1.1. Ví dụ cây dữ liệu theo đơn vị

Một tổ chức có thể tách dữ liệu nhân sự theo đơn vị:

```text
dc=example,dc=org
├── ou=people
│   ├── ou=engineering
│   │   ├── uid=emp-1001
│   │   └── uid=emp-1002
│   ├── ou=finance
│   │   └── uid=emp-2001
│   └── ou=human-resources
│       └── uid=emp-3001
├── ou=groups
│   ├── cn=engineering-readers
│   └── cn=hr-operators
└── ou=service-accounts
    ├── uid=app-engineering
    ├── uid=app-finance
    └── uid=app-hr
```

DN của một entry Engineering:

```text
uid=emp-1001,ou=engineering,ou=people,dc=example,dc=org
```

DN của entry Finance:

```text
uid=emp-2001,ou=finance,ou=people,dc=example,dc=org
```

Cấu trúc này cho phép đặt policy trên subtree Engineering và Finance riêng. Một service account phục vụ Engineering có thể được cấp quyền trên nhánh Engineering mà không cần quyền đọc toàn bộ people subtree.

### 1.2. Chọn nhánh theo ranh giới ổn định

Một nhánh nên đại diện cho boundary có ý nghĩa về quyền, vòng đời hoặc quản trị.

| Nhánh | Dữ liệu | Boundary có thể áp dụng |
| --- | --- | --- |
| ou=engineering | Nhân sự Engineering | Ứng dụng kỹ thuật, quản lý đơn vị |
| ou=finance | Nhân sự Finance | Ứng dụng tài chính, kiểm soát dữ liệu |
| ou=human-resources | Hồ sơ HR | Nhóm nhân sự được ủy quyền |
| ou=service-accounts | Identity của ứng dụng | Quản trị credential riêng |
| ou=groups | Group và membership | Quản lý group theo phạm vi |

Tránh tạo OU theo mọi thay đổi nhỏ như tên dự án, ca làm hoặc trạng thái tạm thời. Nếu dữ liệu thường xuyên di chuyển giữa các OU, DN và DN-valued reference cũng thay đổi theo. Một boundary tốt cần đủ ổn định để ACL không phải chỉnh sửa liên tục.

### 1.3. Subtree là phạm vi dữ liệu, không tự động là phạm vi quyền

Giả sử ứng dụng gửi search với base:

```text
ou=engineering,ou=people,dc=example,dc=org
```

và scope là SUBTREE. Search thông thường chỉ duyệt nhánh Engineering. Nhưng nếu bind identity có quyền đọc toàn bộ directory, một lỗi trong code có thể đổi base thành:

```text
ou=people,dc=example,dc=org
```

LDAP server vẫn có thể trả về cả Engineering, Finance và HR. Search base là lựa chọn của client; ACL mới là policy mà server thực thi.

Do đó cần hai lớp độc lập:

- Ứng dụng giới hạn operation vào nhánh được phép theo nghiệp vụ.
- LDAP server từ chối operation nằm ngoài quyền của authorization identity.

Nếu chỉ có lớp đầu tiên, lỗi lập trình hoặc endpoint bị lạm dụng có thể vượt qua ranh giới. Nếu chỉ có ACL mà ứng dụng không kiểm tra quyền theo người dùng cuối, service account có thể thực hiện hành động vượt quyền nghiệp vụ bên trong subtree mà nó được cấp.

### 1.4. Cô lập theo naming context hoặc subtree?

| Mô hình | Đặc điểm | Khi phù hợp |
| --- | --- | --- |
| Subtree riêng trong một naming context | Nhiều OU dùng chung suffix, schema và server | Các đơn vị có chung hạ tầng nhưng cần ACL khác nhau |
| Naming context riêng | Mỗi partition có suffix/database riêng | Cần backup, replication, delegation hoặc lifecycle độc lập |
| Directory/server riêng | Tách endpoint và hạ tầng | Cần isolation vận hành mạnh hoặc yêu cầu compliance đặc thù |

Subtree ACL có thể đủ cho nhiều ứng dụng nội bộ. Naming context riêng không tự thay thế ACL và application authorization. Directory riêng tăng mức cách ly nhưng kéo theo vận hành, replication, monitoring và credential riêng.

## 2. Xác định ai đang thực hiện LDAP operation

LDAP server đánh giá quyền dựa trên authorization identity của kết nối/operation. Trong ứng dụng Spring, identity này thường là bind DN cấu hình trong ContextSource.

### 2.1. Service account làm thay người dùng cuối

Một ứng dụng thường bind bằng service account:

```text
uid=app-engineering,ou=service-accounts,dc=example,dc=org
```

Sau đó ứng dụng tìm hồ sơ theo user đang đăng nhập. Từ góc nhìn LDAP server, các operation đó đều do `uid=app-engineering` thực hiện. Server không tự biết request ban đầu đến từ Alice hay Bob.

Điều này có hệ quả:

- ACL chỉ giới hạn service account, không phân biệt end user.
- Nếu service account có quyền đọc mọi hồ sơ, bug ở application service có thể làm lộ mọi hồ sơ trong phạm vi đó.
- Application authorization phải kiểm tra actor, resource và use case trước khi gọi LDAP.
- Audit cần ghi cả actor của ứng dụng lẫn bind identity LDAP.

Nếu cần LDAP server phân quyền theo từng người dùng cuối, có thể bind bằng credential người dùng hoặc dùng cơ chế proxy authorization/SASL phù hợp với server. Đây là lựa chọn kiến trúc riêng; không được truyền password người dùng qua các tầng không cần thiết hoặc giả định mọi LDAP server hỗ trợ cùng một proxy authorization extension.

### 2.2. Tách service account theo nhánh và vai trò

Thay vì một account quản trị có quyền rộng, có thể tạo:

| Bind identity | Nhánh được phép | Vai trò |
| --- | --- | --- |
| uid=app-engineering-reader | Engineering | Search/read thuộc tính danh bạ |
| uid=app-engineering-writer | Engineering | Cập nhật các thuộc tính được cho phép |
| uid=app-finance-reader | Finance | Search/read dữ liệu Finance được duyệt |
| uid=app-hr-operator | HR | Thao tác HR theo policy |
| uid=directory-provisioner | Nhánh provisioning được giao | Tạo entry và cấu trúc OU |

Một service account không nên có quyền quản trị directory chỉ vì ứng dụng cần một vài thao tác ghi. Nếu đọc và ghi có mức rủi ro khác nhau, tách identity read-only và writer giúp giới hạn tác động khi credential bị lộ.

### 2.3. Không dùng root/admin identity trong ứng dụng thông thường

OpenLDAP có root DN cấu hình cho database; root DN được miễn kiểm tra ACL thông thường trên database đó. Active Directory cũng có các identity quản trị đặc quyền.

Không dùng các identity này làm credential của ứng dụng. Khi app bind bằng root/admin, ACL subtree không còn tạo ra isolation như mong muốn.

Credential quản trị chỉ nên dùng trong provisioning hoặc maintenance workflow có kiểm soát, audit, secret rotation và thời hạn phù hợp.

### 2.4. Authentication và authorization là hai việc khác nhau

- **Authentication:** xác minh principal có biết credential hoặc đáp ứng cơ chế bind không.
- **Authorization:** xác định principal được làm gì trên entry/attribute nào.

Một user bind thành công không có nghĩa user được quyền search toàn directory, đọc mọi attribute hoặc sửa entry khác. Ngược lại, application login thành công cũng không có nghĩa service account LDAP được cấp quyền phù hợp.

## 3. Phân quyền theo operation và attribute

Quyền trên một nhánh không phải một cờ read/write duy nhất. LDAP có nhiều operation với yêu cầu access khác nhau.

### 3.1. Ma trận operation

| Operation | Quyền cần xem xét | Ví dụ policy |
| --- | --- | --- |
| Bind/authenticate | Quyền xác thực theo cơ chế server | User được phép kiểm tra credential của chính mình |
| Search | Quyền search trên attribute dùng trong filter; quyền đọc attribute trả về | Reader được tìm theo uid và đọc cn/mail |
| Compare | Quyền compare trên attribute được kiểm tra | Cho phép xác minh một assertion cụ thể |
| Lookup/read | Quyền đọc entry và attribute | Danh bạ đọc tên/email |
| Add | Quyền tạo child dưới parent và ghi attribute hợp lệ | Provisioner tạo user trong OU được giao |
| Modify | Quyền thay đổi từng attribute | Writer đổi telephoneNumber |
| Delete | Quyền xóa entry và quyền liên quan trên parent/children | Deprovisioner xóa entry thuộc phạm vi |
| Modify DN | Quyền rename/move entry và thao tác trên parent nguồn/đích | Operator move trong subtree được duyệt |

Tên quyền và cách server đánh giá có khác biệt. Không nên suy ra rằng quyền modify trên attribute tự động cho phép Add/Delete/Modify DN.

### 3.2. Search và read là hai quyền riêng

Một search có thể cần:

1. Search permission trên attribute được dùng trong filter.
2. Read permission trên các attribute được trả về.

Ví dụ ứng dụng tìm user bằng employeeNumber nhưng chỉ trả cn và mail. Directory có thể cho phép search employeeNumber mà không cho đọc giá trị employeeNumber trong kết quả. Điều này hữu ích khi attribute dùng để định tuyến/tìm kiếm nhưng không cần hiển thị cho caller.

Với OpenLDAP, các access level như search và read có quan hệ phân cấp; cần kiểm tra chính xác quyền hiệu lực của rule. Đừng cấp read rộng nếu use case chỉ cần search.

### 3.3. Attribute-level ACL

Một entry person có thể chứa:

```ldif
dn: uid=emp-1001,ou=engineering,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: emp-1001
cn: Alice Nguyen
sn: Nguyen
mail: alice@example.org
telephoneNumber: +84-28-5550-0101
employeeNumber: E1001
userPassword: {SSHA}...
```

Ứng dụng danh bạ có thể chỉ cần uid, cn, mail và telephoneNumber. Ứng dụng HR mới được đọc employeeNumber. userPassword không nên được đọc như dữ liệu thông thường.

Thiết kế policy theo nhu cầu:

- Reader danh bạ: search/read cn, mail, telephoneNumber và uid.
- HR reader: đọc employeeNumber trên nhánh được giao.
- Writer: chỉ modify telephoneNumber hoặc một nhóm attribute cụ thể.
- Password self-service: dùng luồng đổi mật khẩu riêng với quyền phù hợp.
- Provisioner: add/delete theo OU được giao.

### 3.4. Attribute có thể nhiều giá trị

Các attribute LDAP như telephoneNumber hoặc member có thể chứa nhiều giá trị theo schema. Một quyền write trên attribute có thể cho phép thay đổi cả tập giá trị, tùy server và operation. Nếu chỉ muốn thêm hoặc xóa một value, ứng dụng cần dùng Modify operation phù hợp và ACL vẫn có thể chỉ kiểm soát ở cấp attribute, không phải từng value.

Không coi việc gửi một ModificationItem nhỏ là ranh giới bảo mật. Client có thể tự tạo operation khác; server ACL mới là nơi giới hạn quyền.

### 3.5. Password attribute có policy riêng

Với OpenLDAP, userPassword thường được bảo vệ để user có thể authenticate nhưng không đọc verifier như attribute thông thường. Một rule thường gặp là cho anonymous có auth access để kiểm tra bind và cho self có quyền thay đổi password, nhưng policy thực tế phải theo deployment.

Không trả userPassword qua AttributesMapper, ODM projection, debug log hoặc REST response. Không dùng quyền read toàn entry cho một luồng chỉ cần xác thực.

## 4. OpenLDAP ACL: target, who và access level

OpenLDAP cung cấp ACL trong cấu hình slapd. Một access directive xác định target entry/attribute và các principal cùng mức quyền.

### 4.1. Cấu trúc một access directive

Dạng khái quát:

```text
access to <what>
    by <who> <access>
    by <who> <access>
    by * <access>
```

- `what` chọn entry hoặc attribute được bảo vệ, ví dụ DN subtree.
- `who` chọn authorization identity, group hoặc self/anonymous.
- `access` xác định mức quyền như auth, compare, search, read, write hoặc manage.
- Các directive được xét theo thứ tự cấu hình; rule cụ thể phải được đặt trước rule tổng quát phù hợp.

OpenLDAP ACL có nhiều loại target, selector và control clause. Các ví dụ dưới đây là mẫu định hướng policy, cần kiểm tra cú pháp theo phiên bản và cách cấu hình slapd.conf hoặc cn=config của server.

### 4.2. ACL chỉ đọc cho một nhánh

Ví dụ cho phép service account danh bạ đọc một số thuộc tính Engineering:

```text
access to dn.subtree="ou=engineering,ou=people,dc=example,dc=org"
    attrs=uid,cn,mail
    by dn.exact="uid=app-engineering-reader,ou=service-accounts,dc=example,dc=org" read
    by dn.exact="uid=app-engineering-writer,ou=service-accounts,dc=example,dc=org" read
    by * none
```

Rule này áp dụng trên subtree Engineering và các attribute được liệt kê. Principal khác không được cấp quyền theo rule này.

Nếu cần dùng employeeNumber trong filter nhưng không muốn trả giá trị cho caller, có thể cấp search riêng cho attribute đó và read cho nhóm attribute hiển thị. Ví dụ:

```text
access to dn.subtree="ou=engineering,ou=people,dc=example,dc=org"
    attrs=employeeNumber
    by dn.exact="uid=app-engineering-reader,ou=service-accounts,dc=example,dc=org" search
    by dn.exact="uid=app-hr-reader,ou=service-accounts,dc=example,dc=org" read
    by * none
```

Kết quả thực tế phụ thuộc ACL tổng thể và thứ tự directive. Hãy test filter có dùng employeeNumber và test trả employeeNumber trong attributes list bằng từng bind identity.

### 4.3. Tách quyền đọc và ghi

Có thể tạo rule riêng cho writer:

```text
access to dn.subtree="ou=engineering,ou=people,dc=example,dc=org"
    attrs=telephoneNumber
    by dn.exact="uid=app-engineering-writer,ou=service-accounts,dc=example,dc=org" write
    by dn.exact="uid=app-engineering-reader,ou=service-accounts,dc=example,dc=org" read
    by * none
```

Rule này giới hạn write ở telephoneNumber. Nếu writer cần đọc các attribute khác, cấp read ở rule phù hợp. Không thêm write vào toàn subtree nếu use case chỉ sửa số điện thoại.

### 4.4. Chặn password read và cho phép auth/change theo policy

Một ví dụ phổ biến cho userPassword:

```text
access to attrs=userPassword
    by self write
    by anonymous auth
    by * none
```

Rule minh họa này cho phép principal xác thực bằng cách bind và user thay đổi password của chính mình theo quyền self. Nó không cho ứng dụng đọc password verifier.

Nếu có password reset do HR/helpdesk thực hiện, hãy thiết kế group/operator và quyền reset riêng theo server; không cấp read userPassword. Một số directory có extended operation hoặc policy riêng cho password change, vì vậy không sao chép rule OpenLDAP sang sản phẩm khác.

### 4.5. Quyền Add/Delete trên parent và children

Add/Delete có thể cần quyền trên parent entry hoặc pseudo-attribute children, ngoài quyền trên các attribute của entry mới/xóa. Ví dụ, việc tạo user dưới OU Engineering có thể cần writer/provisioner được phép tạo child dưới OU đó.

Vì vậy, test riêng:

- Add entry dưới parent được phép.
- Add entry dưới parent khác.
- Delete entry trong nhánh được phép.
- Delete entry trong nhánh khác.
- Xóa entry có child hoặc reference.
- Tạo entry với objectClass/attribute không hợp lệ.

Không kết luận Add/Delete được phép chỉ vì writer có write trên cn/mail/telephoneNumber.

### 4.6. Thứ tự ACL và rule tổng quát

OpenLDAP đánh giá access directive theo thứ tự; rule đầu tiên khớp target sẽ được dùng để đánh giá các by clause tương ứng. Nếu một rule rộng xuất hiện trước rule bảo vệ attribute nhạy cảm, rule nhạy cảm phía sau có thể không được xét.

Ví dụ, nếu có rule write toàn bộ subtree đứng trước rule employeeNumber chỉ cho HR đọc, writer có thể nhận quyền không mong muốn. Đặt rule attribute nhạy cảm và rule cụ thể trước rule subtree tổng quát, rồi test effective access bằng chính service account.

Cũng cần xem xét `by * none` và các control clause như break/continue/stop khi policy phức tạp. Không sửa ACL production chỉ bằng cách chèn thêm một rule mà chưa đọc toàn bộ thứ tự rule hiện có.

### 4.7. slapd.conf và cn=config

Ví dụ ACL dạng `access to ...` ở trên minh họa cách đọc policy. Với OpenLDAP dùng dynamic configuration, ACL được lưu qua attribute `olcAccess` trong cấu hình `cn=config`, thường ở dạng LDIF và có thứ tự index.

Cú pháp, quoting và cách thay đổi rule khác với `slapd.conf`. Không dán nguyên block slapd.conf vào olcAccess. Thay đổi ACL cần backup cấu hình, review thứ tự, apply trong môi trường test và xác minh quyền sau khi reload.

## 5. Active Directory: DACL, OU inheritance và property rights

Active Directory Domain Services dùng security descriptor và Discretionary Access Control List (DACL) để kiểm soát quyền trên object.

### 5.1. Phân quyền theo OU

Một cách tổ chức:

- Tạo nhóm bảo mật Engineering Directory Readers.
- Tạo nhóm Engineering Directory Writers.
- Đưa service account tương ứng vào các nhóm.
- Gán quyền trên OU Engineering.
- Để các ACE cần thiết kế thừa xuống object con.
- Không cấp quyền tương tự trên OU Finance/HR.

Reader có thể cần List Contents và Read Properties để duyệt/đọc entry. Writer có thể chỉ cần Write Property cho một số attribute. Provisioning cần Create Child trên parent; deprovisioning cần Delete Child hoặc quyền xóa phù hợp. Quyền Modify DN/move phải được kiểm tra trên object nguồn và parent đích.

### 5.2. Dùng object-specific ACE

Không nên cấp GenericAll hoặc Full Control cho application service account chỉ để cập nhật một vài thuộc tính.

Thay vào đó:

- Cấp Read Property cho các property cần đọc.
- Cấp Write Property cho telephoneNumber nếu writer chỉ cập nhật số điện thoại.
- Cấp Create Child cho đúng object class trên OU nếu service cần tạo entry.
- Cấp Delete Child/quyền delete phù hợp nếu service cần xóa.
- Cấp extended right riêng nếu cần reset password hoặc thao tác đặc biệt.
- Giới hạn inheritance scope vào object class/OU liên quan.

Tên quyền chính xác và cách cấu hình ACE phụ thuộc công cụ quản trị, object class và property set. Dùng Effective Access/Security tab hoặc công cụ quản trị tương đương để xác minh quyền hiệu lực.

### 5.3. Inheritance và explicit ACE

DACL có thể chứa ACE được khai báo trực tiếp và ACE kế thừa từ parent. Một OU có thể chặn inheritance hoặc có ACE đặc biệt khiến quyền hiệu lực khác với dự kiến.

Khi thiết kế:

1. Xem security descriptor của OU gốc và OU con.
2. Kiểm tra inheritance flags và object-specific scope.
3. Xác minh group membership của service account.
4. Kiểm tra quyền hiệu lực trên một object thật.
5. Thử thao tác bằng bind identity ứng dụng.

Không dựa vào một ảnh chụp ACL của OU gốc để kết luận mọi object con có cùng quyền.

### 5.4. Không dùng deny ACE để vá một allow quá rộng

Deny ACE có thể tương tác phức tạp với explicit/inherited ACE, group membership và canonical ordering. Cách dễ kiểm soát hơn thường là cấp allow tối thiểu cho security group đúng phạm vi và loại bỏ allow rộng không cần thiết.

Nếu phải dùng deny, cần hiểu thứ tự ACE, inheritance và tác động lên mọi group mà identity thuộc về; test effective access trước khi triển khai.

## 6. Tích hợp ACL với Spring LDAP

Spring LDAP cung cấp API kết nối và thao tác directory; nó không thay thế ACL engine của LDAP server. Mọi thao tác qua LdapTemplate được thực thi dưới identity mà ContextSource dùng để bind.

### 6.1. Cấu hình ContextSource với identity chuyên biệt

Ví dụ ứng dụng Engineering dùng một bind identity riêng. Base của ContextSource là naming context chung; query base giới hạn nhánh Engineering.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.core.ContextSource;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class EngineeringDirectoryConfiguration {

    @Bean
    ContextSource engineeringContextSource(
            DirectorySecrets secrets) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl("ldaps://ldap.example.org:636");
        source.setBase("dc=example,dc=org");
        source.setUserDn(
            "uid=app-engineering-reader,ou=service-accounts,dc=example,dc=org"
        );
        source.setPassword(secrets.engineeringReaderPassword());
        return source;
    }

    @Bean
    LdapTemplate engineeringLdapTemplate(
            @Qualifier("engineeringContextSource")
            ContextSource contextSource) {
        return new LdapTemplate(contextSource);
    }
}
```

Đây là ví dụ cấu hình Spring. Trong production, endpoint và secret lấy từ configuration/secret manager; không hardcode hoặc log password. Nếu dùng reader identity, các thao tác write phải đi qua template/identity writer riêng và vẫn được server ACL giới hạn.

`setUserDn` phải nhận full DN tính từ root của LDAP tree, kể cả khi ContextSource đã cấu hình base. Base chỉ làm cho DN dùng trong các operation của LdapTemplate trở thành tương đối. Vì vậy ví dụ đặt bind DN đầy đủ, còn search/query base có thể là DN tương đối bên dưới `dc=example,dc=org`.

### 6.2. Không thay đổi bind identity hoặc base DN theo request

Không làm:

```java
// KHÔNG AN TOÀN: thay đổi shared ContextSource trong khi nhiều request dùng nó.
contextSource.setUserDn(requestUserDn);
contextSource.setPassword(requestPassword);
contextSource.setBase(requestBaseDn);
```

ContextSource thường được chia sẻ giữa nhiều thread và có thể làm việc cùng connection pool. Thay đổi identity/base trên singleton có thể khiến request đồng thời dùng nhầm cấu hình hoặc connection đã bind bằng identity khác.

Cấu hình một ContextSource/LdapTemplate bất biến cho từng security identity/branch policy. Nếu cần routing, chọn bean đã cấu hình trước qua registry/facade; không mutate bean dùng chung.

### 6.3. Một template cho reader, một template cho writer

Ví dụ:

```java
@Bean
LdapTemplate engineeringReaderTemplate(
        @Qualifier("engineeringReaderContextSource")
        ContextSource source) {
    return new LdapTemplate(source);
}

@Bean
LdapTemplate engineeringWriterTemplate(
        @Qualifier("engineeringWriterContextSource")
        ContextSource source) {
    return new LdapTemplate(source);
}
```

Application service chỉ inject writer vào component cần thay đổi dữ liệu. Các query/report component chỉ có reader template.

Phân tách bean giúp tránh vô tình gọi write bằng identity rộng hơn trong code đọc. Nhưng tên bean không phải security boundary; server ACL phải xác minh quyền của bind DN tương ứng.

### 6.4. Repository và base DN

Spring Data LDAP repository thường dùng một LdapTemplate cụ thể được cấu hình khi tạo repository proxy. Nếu entity có `@Entry(base = "ou=engineering")`, base này là một phần mapping/query configuration tương đối với ContextSource base.

Không tự động coi `@Entry(base=...)` là ACL. Nếu template bind bằng identity có quyền toàn directory, repository vẫn có thể được cấu hình hoặc gọi theo cách khác để truy cập ngoài nhánh. Hãy dùng ACL server để giới hạn identity và kiểm tra base DN thực tế trong integration test.

Với các nhánh có policy khác nhau, có thể cấu hình repository package/template riêng hoặc dùng application facade chọn template đã cấu hình. Không đổi ContextSource base/credential theo request.

### 6.5. Ứng dụng dùng service account phải tự authorize end user

Nếu mọi request đều bind bằng `app-engineering-writer`, LDAP server chỉ thấy service account này. Trước mỗi thao tác, application service cần xác minh actor có quyền:

- Đọc resource đó.
- Sửa đúng attribute.
- Xóa entry hoặc thay đổi group membership.
- Thực hiện rename/move nếu use case cho phép.

Không cho controller nhận trực tiếp ModificationItem, DN đích hoặc LDAP filter tùy ý từ client. Hãy cung cấp method domain cụ thể như `updateTelephoneNumber(personId, value)` và tự resolve DN trong nhánh được phép.

## 7. Kiểm tra DN và DN-valued reference

DN xác định vị trí entry, nhưng giá trị DN trong một attribute không tự tạo ra quan hệ quyền an toàn.

### 7.1. Không kiểm tra subtree bằng string prefix

Không viết:

```java
if (requestedDn.toString().startsWith(branchBaseDn)) {
    // Cho phép truy cập
}
```

String prefix có thể sai do thứ tự RDN, escaping, dấu phẩy trong value hoặc cách biểu diễn tương đương của DN. Một chuỗi bắt đầu bằng text giống base chưa chắc là descendant của DN đó.

Cách tốt hơn:

- Nhận stable local ID từ API thay vì full DN.
- Tạo hoặc resolve DN từ branch configuration đã được kiểm soát.
- Nếu bắt buộc nhận DN, parse thành LdapName và so sánh cấu trúc RDN bằng logic đã được kiểm thử.
- Dù application check pass, vẫn dựa vào server ACL để chặn operation ngoài quyền.

### 7.2. Group membership có thể tạo liên kết chéo nhánh

Ví dụ group Engineering:

```ldif
dn: cn=engineering-readers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: engineering-readers
member: uid=emp-1001,ou=engineering,ou=people,dc=example,dc=org
```

Khi thêm member, application nên resolve person ID trong branch Engineering và xác minh group thuộc cùng boundary. Không nhận DN member bất kỳ từ request.

Nếu cho phép cross-branch membership, phải có policy explicit, kiểm tra quyền trên cả group lẫn member và audit mối quan hệ đó. ACL cho phép sửa attribute member không nhất thiết kiểm tra giá trị DN trỏ tới object có cùng branch hay không.

### 7.3. Manager, owner và reference khác

Các attribute như manager, owner, member, uniqueMember hoặc custom DN-valued attribute có thể chứa DN. Khi target entry bị rename/move, reference có thể cần cập nhật theo server/overlay hoặc application workflow.

Cần xác định:

- Attribute nào là DN-valued.
- Server có referential integrity/link semantics hay không.
- Ai được sửa reference.
- Có cho reference qua nhánh hay không.
- Rename/delete xử lý reference cũ như thế nào.
- Có cần lưu stable ID song song để resolve DN mới không.

Không giả định mọi server tự cập nhật mọi DN-valued attribute.

## 8. Add, Modify, Delete và Modify DN trong boundary

Một policy subtree cần xét từng operation cụ thể.

### 8.1. Add entry

Khi tạo user dưới OU Engineering:

```text
uid=emp-4001,ou=engineering,ou=people,dc=example,dc=org
```

Application cần tính DN từ branch configuration và stable ID. Server cần kiểm tra quyền trên parent/children và các attribute/objectClass của entry mới.

Không nhận parentDn tùy ý từ request. Nếu application service account có quyền add trên toàn directory, lỗi ở controller có thể tạo entry trong OU Finance.

### 8.2. Modify attribute

Một writer chỉ cần đổi telephoneNumber:

- Resolve user theo stable ID trong branch.
- Validate giá trị theo business rule.
- Gửi modification chỉ cho telephoneNumber.
- Server ACL kiểm tra quyền write trên attribute.
- Đọc lại để xác minh thay đổi.

Việc code chỉ gửi một ModificationItem không thay thế ACL. Một endpoint khác có thể gửi modification khác nếu credential có quyền rộng.

### 8.3. Delete entry

Delete có thể cần quyền trên entry và parent/children tùy server. Trước khi xóa, application cần xác minh ownership, lifecycle, child entries và DN references.

Không dùng một account có quyền delete toàn bộ directory cho tác vụ deprovision của một nhánh. Nếu cần xóa subtree, tách thành workflow quản trị riêng có approval/audit và giới hạn DN đích.

### 8.4. Rename/move

Modify DN có thể đổi RDN hoặc chuyển entry sang parent khác. Một user có quyền modify attribute chưa chắc được phép rename/move.

Nếu move được phép trong cùng branch:

- Xác minh DN nguồn thuộc branch.
- Tính DN đích từ parent allowlist.
- Xác minh DN đích vẫn trong branch.
- Xác minh parent mới tồn tại.
- Kiểm tra quyền server trên source và destination parent.
- Cập nhật DN-valued references theo policy.
- Audit stable ID và DN trước/sau.

Không cho application identity move entry sang branch khác chỉ vì request cung cấp `newSuperior` hợp lệ về cú pháp.

## 9. Search base, alias và referral

Search scope giúp ứng dụng tìm đúng vùng dữ liệu nhưng cần xem xét các cơ chế có thể mở rộng phạm vi.

### 9.1. Base và scope

LDAP search có ba scope thường dùng:

| Scope | Phạm vi |
| --- | --- |
| BASE | Chỉ entry tại base DN |
| ONELEVEL | Entry con trực tiếp |
| SUBTREE | Base và toàn bộ descendant |

Ứng dụng nên chọn base hẹp nhất và scope đủ cho use case. Tuy nhiên, đây là tối ưu và defense-in-depth phía client; ACL server vẫn phải giới hạn authorization identity.

### 9.2. Alias dereferencing

Nếu directory có alias, search có thể dereference alias tùy cấu hình. Alias có thể trỏ tới entry ngoài nhánh mà caller nghĩ mình đang tìm.

Đối với dữ liệu nhạy cảm:

- Xác định alias policy.
- Không bật dereference rộng nếu use case không cần.
- Test alias trỏ ngoài branch.
- Đảm bảo ACL trên target vẫn được server thực thi.

### 9.3. Referral

Referral có thể chuyển client sang endpoint hoặc naming context khác. Nếu client tự động follow referral, cần kiểm soát target, TLS, credential và trust boundary.

Không follow mọi referral từ dữ liệu directory mà không allowlist. Một referral có thể làm operation đi tới server khác với policy/identity khác. Khi tenant/branch isolation quan trọng, xác định rõ referral policy và kiểm thử trường hợp referral ngoài phạm vi.

## 10. Connection pool và credential isolation

Connection pool là nơi dễ gây lỗi nếu ứng dụng có nhiều bind identity.

### 10.1. Pool phải gắn với identity

Nếu Engineering reader và Engineering writer dùng credential khác nhau, connection pool không được trộn connection của hai identity. Tương tự, Finance và HR không dùng chung pool nếu ACL dựa trên bind DN khác nhau.

Nguyên tắc:

- ContextSource/pool được cấu hình cho một security identity rõ ràng.
- Không thay user DN/password trên ContextSource đang chạy.
- Không tái sử dụng authenticated context của identity này cho identity khác.
- Xoay vòng secret theo lifecycle rõ ràng.
- Đóng pool/context khi identity bị thu hồi.
- Giới hạn tổng connection và kiểm soát idle/validation timeout.

### 10.2. Không dùng pooling nếu chưa hiểu authentication model

Một số pool giữ connection đã bind. Nếu ứng dụng kỳ vọng bind theo end user nhưng pool được cấu hình với service account, mọi operation thực tế có thể dùng service account. Ngược lại, nếu pool tái sử dụng context giữa identity khác nhau, quyền có thể bị nhầm.

Trước khi bật pooling:

1. Xác định connection được bind bằng identity nào.
2. Xác định connection có được tái bind không.
3. Xác định pool key có bao gồm principal/credential hay không.
4. Test hai identity có quyền khác nhau chạy đồng thời.
5. Kiểm tra behavior khi credential rotate/revoke.

### 10.3. Tách reader và writer ở tầng code

Có thể tạo hai bean với qualifier riêng:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.ldap.core.LdapTemplate;

public final class EmployeeLookupService {

    private final LdapTemplate reader;

    public EmployeeLookupService(
            @Qualifier("engineeringReaderTemplate")
            LdapTemplate reader) {
        this.reader = reader;
    }
}

public final class EmployeeUpdateService {

    private final LdapTemplate writer;

    public EmployeeUpdateService(
            @Qualifier("engineeringWriterTemplate")
            LdapTemplate writer) {
        this.writer = writer;
    }
}
```

Cấu trúc này giúp code dễ review. Tuy nhiên, nếu cả hai bean cùng bind bằng một identity có quyền write rộng, việc đặt tên reader/writer không giảm quyền thật. Credential và ACL phải khớp với vai trò.

## 11. Audit và quan sát quyền truy cập

ACL có thể từ chối operation mà không giải thích đầy đủ ngữ cảnh nghiệp vụ. Application log và LDAP server log cần bổ sung cho nhau.

### 11.1. Trường audit nên có

| Trường | Mục đích |
| --- | --- |
| Actor ứng dụng | Người dùng hoặc workload khởi tạo request |
| Authorization identity LDAP | Bind DN/service account đã thực hiện operation |
| Branch key | Nhánh dữ liệu được yêu cầu |
| Resource stable ID | Đối tượng được thao tác |
| Operation | Search, lookup, add, modify, delete, Modify DN |
| Attribute names | Attribute được đọc/ghi, không nhất thiết log value |
| Decision | Allowed, denied, not found, limit, error |
| Result code/category | Phân biệt insufficient access, schema, conflict, timeout |
| Correlation ID | Nối request với LDAP server log |
| Latency | Theo dõi độ trễ theo branch/operation |

Không log password, token, bind credential hoặc toàn bộ attribute values. DN có thể chứa dữ liệu cá nhân; chỉ log raw DN khi policy cho phép. Ưu tiên stable ID và branch key.

### 11.2. Phát hiện hành vi vượt nhánh

Theo dõi:

- Service account Engineering search DN trong Finance/HR.
- Tỷ lệ insufficientAccessRights tăng bất thường.
- Application query base khác branch base đã đăng ký.
- Writer sửa attribute ngoài allowlist.
- Reader thực hiện Add/Modify/Delete.
- Referral chuyển sang endpoint không được tin cậy.
- Bind identity không khớp template/branch được chọn.
- Connection pool trả kết quả có branch không tương ứng.

Alert nên gắn với actor, bind DN, operation và branch key. Tránh log raw filter có dữ liệu người dùng nếu không cần.

## 12. Kiểm thử ACL theo nhánh thư mục

Unit test kiểm tra application authorization là cần thiết nhưng không chứng minh ACL server hoạt động. Phải có integration test với directory thật hoặc test server tương thích ACL và bind bằng đúng identity.

### 12.1. Fixture hai nhánh

Ví dụ dữ liệu:

```ldif
dn: dc=example,dc=org
objectClass: top
objectClass: domain
dc: example

dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: ou=engineering,ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: engineering

dn: uid=emp-1001,ou=engineering,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: emp-1001
cn: Alice Nguyen
sn: Nguyen
mail: alice@example.org
telephoneNumber: +84-28-5550-0101
employeeNumber: E1001

dn: ou=finance,ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: finance

dn: uid=emp-2001,ou=finance,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: emp-2001
cn: Bob Tran
sn: Tran
mail: bob@example.org
telephoneNumber: +84-28-5550-0201
employeeNumber: F2001
```

Fixture phải được nạp bằng administrator của test directory trước khi chạy ACL test. Sau đó, mọi test authorization phải bind bằng service account tương ứng, không dùng administrator.

### 12.2. Ma trận test theo identity

| Identity | Operation | Nhánh Engineering | Nhánh Finance |
| --- | --- | --- | --- |
| engineering-reader | Search/read cn, mail | Cho phép | Từ chối/không trả dữ liệu |
| engineering-reader | Modify telephoneNumber | Từ chối | Từ chối |
| engineering-writer | Read cn/mail | Cho phép nếu policy cấp | Từ chối |
| engineering-writer | Modify telephoneNumber | Cho phép | Từ chối |
| engineering-writer | Modify employeeNumber | Từ chối nếu không được cấp | Từ chối |
| finance-reader | Search/read cn, mail | Từ chối | Cho phép |
| finance-writer | Modify telephoneNumber | Từ chối | Cho phép theo policy |
| provisioner | Add dưới OU được giao | Cho phép | Từ chối nếu ngoài scope |
| engineering-writer | Delete/Modify DN | Theo policy riêng | Từ chối |

Kết quả từ server có thể là `insufficientAccessRights`, không có kết quả, hoặc một lỗi khác tùy ACL/server và cách operation được thực hiện. Test phải khẳng định dữ liệu không bị trả ra hoặc thay đổi ngoài phạm vi; không giả định mọi server luôn trả cùng một result code.

### 12.3. Test search filter và returning attributes

Với engineering-reader:

1. Search theo uid trong Engineering.
2. Search theo employeeNumber nếu được cấp search.
3. Yêu cầu trả employeeNumber trong attributes list.
4. Yêu cầu trả userPassword.
5. Search toàn bộ ou=people.
6. Thử lookup DN Finance.

Kiểm tra riêng search access và read access. Một search trả entry nhưng không có attribute nhạy cảm có thể là hành vi đúng theo ACL.

### 12.4. Test write theo attribute

Với engineering-writer:

- Modify telephoneNumber: được phép.
- Modify mail nếu không nằm trong allowlist: bị từ chối.
- Modify employeeNumber: bị từ chối.
- Add entry dưới Engineering: chỉ cho phép nếu writer có provisioning role.
- Add dưới Finance: bị từ chối.
- Delete entry: bị từ chối nếu không có delete role.
- Modify DN sang OU Finance: bị từ chối.
- Đọc lại entry sau mỗi operation thất bại để xác minh không có thay đổi một phần.

### 12.5. Test quyền trên parent

Test Add/Delete riêng vì server có thể kiểm tra quyền trên parent hoặc children:

- Add vào parent Engineering.
- Add vào parent Finance.
- Delete child dưới Engineering.
- Delete child dưới Finance.
- Delete OU chứa child.
- Tạo entry có objectClass không hợp lệ.
- Thử tạo DN đã tồn tại.

Không suy ra quyền tạo/xóa từ quyền modify attribute của entry hiện có.

### 12.6. Test concurrency và pool

Chạy song song:

- Request A bind bằng engineering-reader.
- Request B bind bằng finance-writer.
- Cả hai truy cập các entry có uid giống nhau ở hai branch.
- Lặp lại qua pool đã warm.
- Gây exception giữa operation để kiểm tra cleanup.
- Xoay vòng credential trong môi trường test và xác minh connection cũ không tiếp tục được dùng ngoài policy.

Kết quả phải luôn tương ứng với bind identity và branch đã chọn. Không có response nào trả nhầm entry do connection/context bị chia sẻ sai.

### 12.7. Test bằng identity thật, không dùng admin

Một integration test chỉ chạy với Directory Manager/root DN có thể đọc và sửa mọi entry, nên không kiểm chứng ACL. Test ACL cần:

1. Provision fixture bằng admin test.
2. Cấu hình ACL.
3. Bind riêng từng reader/writer/provisioner.
4. Chạy operation được phép.
5. Chạy operation ngoài quyền.
6. Đọc lại dữ liệu bằng auditor/test admin để xác minh không có thay đổi ngoài ý muốn.
7. Lưu result category và bind identity trong test report.

Nếu dùng OpenLDAP, hãy chạy trên phiên bản/cấu hình gần production, gồm cả ACL order và backend tương ứng. Nếu dùng Active Directory, test bằng domain identity và DACL thật trong test OU.

## 13. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Reader đọc được cả directory | Bind identity có quyền rộng hoặc dùng root/admin | Tạo identity theo nhánh và thu hẹp ACL |
| Search base đúng nhưng vẫn lộ nhánh khác | ACL server không giới hạn service account | Cấu hình ACL trên server và test full DN ngoài branch |
| Search không thấy entry dù bind thành công | Thiếu search access hoặc sai base/scope | Kiểm tra filter attribute, search ACL và base |
| Entry có mặt nhưng thiếu attribute | Có search nhưng không có read trên attribute | Cấp read đúng attribute nếu nghiệp vụ cho phép |
| Filter không tìm thấy dù biết entry tồn tại | Thiếu search permission trên attribute trong filter | Kiểm tra search access riêng |
| Compare thất bại | Không có compare permission hoặc attribute policy | Cấp compare đúng use case |
| User bind thành công nhưng không đọc được entry khác | Authentication không đồng nghĩa authorization | Thiết kế quyền riêng cho search/read |
| Writer sửa được password/employeeNumber | ACL attribute quá rộng hoặc rule order sai | Đặt rule nhạy cảm trước rule subtree tổng quát |
| Add/Delete bị từ chối | Thiếu quyền trên parent/children | Kiểm tra ACL parent và pseudo-attribute/operation |
| Modify DN vượt branch | Writer có quyền rename/move quá rộng | Giới hạn quyền và validate source/destination |
| ACL OpenLDAP không có hiệu lực như dự kiến | Rule tổng quát đứng trước rule cụ thể hoặc sai olcAccess order | Kiểm tra thứ tự và effective access |
| AD user có quyền ngoài dự kiến | ACE kế thừa hoặc group membership rộng | Kiểm tra effective DACL và inheritance |
| App reader vẫn ghi được | Reader bean dùng nhầm writer template/credential | Kiểm tra Qualifier, ContextSource và bind DN |
| Pool làm lẫn identity | Pool không tách theo bind credential | Tách pool/context theo security identity |
| Unit test pass nhưng ACL production lỗi | Test dùng mock hoặc admin identity | Integration test bằng bind identity thực |
| Log không truy được actor | Chỉ ghi DN hoặc result code | Ghi actor ứng dụng, bind identity, branch và correlation ID |

## 14. Bài thực hành

Một hệ thống Spring Data LDAP có ba nhánh Engineering, Finance và HR. Một ứng dụng danh bạ cần tìm user và đọc cn/mail trong Engineering. Một ứng dụng quản lý nhân sự cần đọc employeeNumber và cập nhật telephoneNumber trong HR. Hiện tại cả hai ứng dụng đều bind bằng một service account có quyền read/write toàn bộ ou=people.

**Câu A.** Vì sao việc mỗi ứng dụng dùng search base khác nhau chưa đủ để cô lập dữ liệu?

**Câu B.** Hãy đề xuất bind identity và quyền tối thiểu cho hai ứng dụng.

**Câu C.** Tại sao search permission và read permission cần được phân biệt?

**Câu D.** Nếu engineering-reader có quyền search employeeNumber nhưng không có read, ứng dụng có thể làm gì với attribute đó?

**Câu E.** Vì sao rule ACL attribute-specific cần đặt trước rule subtree tổng quát?

**Câu F.** Add/Delete có thể cần quyền nào trên parent ngoài quyền attribute?

**Câu G.** Vì sao không nên dùng root DN OpenLDAP hoặc Domain Admin cho ứng dụng?

**Câu H.** Làm sao kiểm tra writer chỉ sửa telephoneNumber?

**Câu I.** Nếu mọi request bind bằng service account, LDAP server có biết end user là Alice hay Bob không?

**Câu J.** Vì sao test ACL phải dùng bind identity riêng thay vì administrator?

### Gợi ý đáp án

- **A:** Base là phạm vi do client chọn; service account có quyền toàn people subtree vẫn có thể đổi base và đọc nhánh khác.
- **B:** engineering-reader chỉ search/read cn, mail và các attribute cần cho danh bạ; HR reader/writer tách riêng, chỉ có quyền đọc employeeNumber và modify telephoneNumber trong HR.
- **C:** Search kiểm soát attribute dùng trong filter; read kiểm soát giá trị trả về. Có thể cho phép tìm mà không tiết lộ giá trị.
- **D:** Có thể dùng employeeNumber trong filter nếu có search access, nhưng không được đọc giá trị đó trong kết quả.
- **E:** OpenLDAP xét ACL theo thứ tự; rule tổng quát trước có thể làm rule bảo vệ attribute nhạy cảm không được áp dụng.
- **F:** Quyền tạo/xóa child trên parent hoặc children access, tùy server và operation.
- **G:** Identity đặc quyền có thể bypass ACL hoặc có quyền rộng, làm mất tác dụng của least privilege.
- **H:** Cấp write chỉ trên telephoneNumber, thử modify các attribute khác và xác minh server từ chối; đọc lại entry để kiểm tra không đổi.
- **I:** Không. Server chỉ thấy bind identity của ứng dụng trừ khi dùng user bind hoặc cơ chế proxy authorization được hỗ trợ.
- **J:** Administrator có quyền rộng và có thể bypass ACL; test phải phản ánh chính quyền của ứng dụng production.

## 15. Ghi nhớ cốt lõi

- **Subtree tổ chức dữ liệu; ACL server thực thi ranh giới quyền.** Search base do client chọn không phải security boundary.
- Xác định rõ authorization identity mà LDAP server nhìn thấy; nếu mọi request dùng service account, server không tự phân biệt end user.
- Tách reader, writer và provisioner theo nhánh và nhiệm vụ; không dùng root/admin credential cho ứng dụng.
- Phân quyền search, read, compare, auth, add, modify, delete và Modify DN riêng theo use case.
- Kiểm soát cả attribute nhạy cảm và quyền trên parent/children cho Add/Delete.
- Với OpenLDAP, hiểu target, who, access level và thứ tự ACL; bảo vệ userPassword và đặt rule cụ thể trước rule tổng quát.
- Với Active Directory, kiểm tra DACL, object-specific ACE, inheritance và effective access.
- Spring LDAP chỉ gửi operation bằng identity của ContextSource; bean reader/writer phải dùng credential thật sự khác nhau nếu cần quyền khác nhau.
- Không mutate ContextSource hoặc chia sẻ pool giữa bind identity khác nhau.
- Kiểm tra DN-valued reference, alias, referral, rename/move và group membership trong cùng boundary.
- Integration test ACL bằng service account thật; không dùng administrator để kết luận isolation đã hoạt động.

## Tài liệu tham khảo

1. [RFC 4511 — Lightweight Directory Access Protocol: The Protocol](https://www.rfc-editor.org/rfc/rfc4511.html) — Bind, Search, Compare, Add, Modify, Delete và Modify DN operations.
2. [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512.html) — DIT, entry, naming context, schema và object class.
3. [RFC 4513 — LDAP: Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513.html) — authentication, bind và security considerations.
4. [RFC 4515 — LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515.html) — search filter syntax và assertion value escaping.
5. [OpenLDAP Administrator's Guide — Access Control](https://www.openldap.org/doc/admin26/access-control.html) — ACL target, authorization identity, access levels và rule ordering.
6. [OpenLDAP Administrator's Guide — Access Control Configuration](https://www.openldap.org/doc/admin26/slapdconf2.html) — access directives và cấu hình slapd/cn=config.
7. [Spring LDAP Reference — Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html) — ContextSource, bind identity và LdapTemplate.
8. [Spring LDAP — LdapContextSource API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/support/LdapContextSource.html) — cấu hình LDAP context source.
9. [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html) — các operation search, lookup, bind, modify và delete.
10. [Microsoft — Access Control and Authorization](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/plan/security-best-practices/active-directory-domain-services-security-best-practices) — bảo vệ Active Directory Domain Services.
11. [Microsoft — Access Control Lists](https://learn.microsoft.com/en-us/windows/win32/secauthz/access-control-lists) — DACL, ACE và mô hình quyền Windows.
12. [Microsoft — Security Descriptors](https://learn.microsoft.com/en-us/windows/win32/secauthz/security-descriptors) — owner, DACL, SACL và security descriptor.
