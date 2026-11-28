# Tạo nhóm và cập nhật thành viên bằng thay đổi chọn lọc

Trong LDAP, nhóm thường được lưu như một **entry** có các thuộc tính đa giá trị chứa DN của từng thành viên. Một thao tác “thêm Minh vào nhóm Engineering” chỉ cần **bổ sung đúng một giá trị của thuộc tính `member`**; thao tác “bỏ Lan khỏi nhóm” chỉ cần **xóa đúng một giá trị**. Nếu ứng dụng thay thế toàn bộ danh sách thành viên để thực hiện những việc nhỏ này, thay đổi của người khác có thể bị ghi đè và các thuộc tính không liên quan có thể bị ảnh hưởng.

Bài thực hành thuộc chương **Thực hành** của `SPRING_DATA_LDAP`. Bạn sẽ tạo nhóm `groupOfNames`, dùng Spring Data LDAP và `LdapTemplate` quản lý entry trong cây thư mục, thực hiện **LDAP Modify với `ADD_ATTRIBUTE`/`REMOVE_ATTRIBUTE`**, thiết kế API an toàn và kiểm thử trên directory có schema/ACL thật.

## 1. Đầu ra mong muốn

Sau khi hoàn thành, bạn có thể:

- Phân biệt entry **người dùng** `inetOrgPerson` với entry **nhóm** `groupOfNames` và hiểu ý nghĩa của `member`, DN, RDN, `objectClass`.
- Tạo một nhóm hợp lệ với `cn` và thành viên đầu tiên; không cố tạo `groupOfNames` rỗng.
- Bổ sung, xóa **một thành viên cụ thể** bằng LDAP Modify, không gọi `REPLACE_ATTRIBUTE` cho toàn bộ danh sách.
- Tạo DN bằng `LdapNameBuilder`; giữ **DN đầy đủ** cho giá trị `member` dù `ContextSource` dùng base DN tương đối.
- Giải quyết thêm trùng, thành viên không tồn tại, xóa thành viên cuối, quyền ACL và yêu cầu gửi lặp.
- Đóng gói logic trong service và API Java, sau đó dùng LDIF/`ldapsearch` xác minh thay đổi.
- Nhận diện giới hạn của đọc-rồi-ghi trong môi trường nhiều request đồng thời và vai trò của kiểm thử tích hợp.

Giả định môi trường có Java 17+, Spring Boot tương thích với Spring Data LDAP và LDAP server hỗ trợ schema `inetOrgPerson`, `groupOfNames`. Các DN và tên miền `example.org` chỉ là dữ liệu minh họa.

## 2. Bài toán và cây LDAP

Một hệ thống nội bộ có hai người dùng `lan` và `minh` dưới `ou=people`. Người quản lý muốn tạo nhóm `engineering` với thành viên đầu tiên là Lan, sau đó thêm Minh rồi bỏ Lan.

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=minh
└── ou=groups
    └── cn=engineering
~~~

DN đầy đủ:

~~~text
uid=lan,ou=people,dc=example,dc=org
uid=minh,ou=people,dc=example,dc=org
cn=engineering,ou=groups,dc=example,dc=org
~~~

Ở đây:

| Khái niệm | Trong bài lab | Vai trò |
| --- | --- | --- |
| DN người dùng | `uid=lan,ou=people,dc=example,dc=org` | Định danh entry thành viên. |
| DN nhóm | `cn=engineering,ou=groups,dc=example,dc=org` | Định danh entry sẽ thay đổi. |
| RDN nhóm | `cn=engineering` | Thành phần tên nhóm trực tiếp dưới `ou=groups`. |
| `objectClass` nhóm | `groupOfNames` | Xác định schema yêu cầu `cn` và `member`. |
| `member` | DN đầy đủ của người dùng | Thuộc tính đa giá trị dùng để biểu diễn thành viên. |

Mục tiêu sau từng bước:

| Thao tác | Giá trị `member` kỳ vọng |
| --- | --- |
| Tạo nhóm với Lan | `uid=lan,ou=people,dc=example,dc=org` |
| Thêm Minh | DN của Lan **và** DN của Minh |
| Xóa Lan | Chỉ còn DN của Minh |
| Gửi lại yêu cầu thêm Minh | Không tạo thêm bản ghi hoặc giá trị trùng |
| Cố xóa Minh (thành viên cuối) | Từ chối theo quy tắc nhóm `groupOfNames` |

## 3. Chọn đúng objectClass và thuộc tính thành viên

Theo RFC 4519, `groupOfNames` là **STRUCTURAL object class** kế thừa `top` và có yêu cầu:

~~~text
objectClass: top
objectClass: groupOfNames

MUST: cn, member
MAY:  description, owner, ou, o, seeAlso, businessCategory, ...
~~~

Nó yêu cầu **ít nhất một giá trị `member`**. LDAP thường không chấp nhận `groupOfNames` có `cn` nhưng không có bất kỳ `member` nào, vì điều đó vi phạm schema. Nếu nghiệp vụ thực sự cần nhóm rỗng, phải chọn mô hình/extension hỗ trợ và kiểm tra schema server; không chèn một DN giả chỉ để lách schema mà không có chính sách rõ ràng.

Các mô hình nhóm khác:

| Object class | Thuộc tính thành viên | Điểm phân biệt |
| --- | --- | --- |
| `groupOfNames` | `member` | Mỗi giá trị là DN; `cn` và `member` bắt buộc. |
| `groupOfUniqueNames` | `uniqueMember` | Theo schema riêng, hỗ trợ cú pháp Name and Optional UID; không thể thay tên thuộc tính tùy tiện. |
| `posixGroup` | `memberUid` (trong nhiều triển khai) | Thường là mã đăng nhập, **không phải DN**; phụ thuộc schema POSIX của server. |

Trong bài này, dùng **`groupOfNames` + `member`** từ đầu đến cuối. `memberOf` trên entry người dùng **không được LDAP chuẩn tự động bảo đảm**; nó có thể là thuộc tính tính toán/overlay của một directory. Hãy đọc nhóm để xác định danh sách thành viên, trừ khi đã xác minh cơ chế `memberOf` của server.

### Vì sao phải lưu DN đầy đủ?

Nếu `spring.ldap.base` là `dc=example,dc=org`, Spring có thể dùng **DN tương đối** khi truy cập entry nhóm, chẳng hạn `cn=engineering,ou=groups`. Nhưng giá trị thuộc tính `member` phải là **DN của đối tượng được tham chiếu trong directory**, ví dụ:

~~~ldif
member: uid=lan,ou=people,dc=example,dc=org
~~~

Chỉ lưu `member: uid=lan` thường không tham chiếu tới người dùng mong muốn. Đừng nhầm **DN dùng tìm entry** (có thể tương đối theo context) với **giá trị của thuộc tính member** (cần DN đầy đủ).

## 4. Chuẩn bị fixture LDIF

Giả sử naming context `dc=example,dc=org` đã được tạo. Nạp một fixture có người dùng và hai nhánh OU như sau:

~~~ldif
dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: ou=groups,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: groups

dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Thi Lan
sn: Nguyen
mail: lan@example.org

dn: uid=minh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: minh
cn: Tran Van Minh
sn: Tran
mail: minh@example.org
~~~

**Chưa tạo `cn=engineering` trong fixture này**; bài tập sẽ tạo nhóm qua `LdapTemplate`. Để làm lại bài từ đầu, hãy xóa đúng nhóm thử nghiệm hoặc tạo directory lab sạch. Không chạy thao tác Create/Modify/Delete với hồ sơ nhân sự thật.

Cần tài khoản service cho ứng dụng có quyền đọc người dùng, tìm nhóm, tạo nhóm và sửa `member` dưới `ou=groups`. Quyền được kiểm tra bởi ACL server; không mặc định tài khoản có quyền đọc cũng có quyền ghi.

## 5. Cấu hình Spring Boot và kết nối LDAP

Thêm `spring-boot-starter-data-ldap` và `spring-boot-starter-web`; thêm `spring-boot-starter-validation` nếu muốn dùng `@Valid`. Sử dụng BOM quản lý phiên bản của Spring Boot để đồng bộ Spring Data LDAP và Spring LDAP.

`application.yml`:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=svc-group-manager,ou=service,dc=example,dc=org
    password: "${LDAP_BIND_PASSWORD}"
~~~

- `spring.ldap.base` đặt gốc để các lệnh `LdapTemplate` dùng DN tương đối.
- `spring.ldap.username` là tài khoản **dịch vụ** thực hiện thao tác LDAP, không phải danh tính người gọi HTTP.
- Mật khẩu lấy từ secret môi trường `LDAP_BIND_PASSWORD`, không ghi cứng vào source.
- Dùng LDAPS hoặc StartTLS **hoàn tất trước Simple Bind**, kiểm tra chứng chỉ và hostname. Ví dụ này dùng LDAPS.
- Nếu triển khai API, xác thực/phân quyền người gọi HTTP bằng cơ chế riêng, ví dụ Spring Security.

### Luồng dữ liệu

~~~mermaid
flowchart LR
    A["REST Client: groupId, uid"] --> B["DTO + Validation"]
    B --> C["GroupMembershipService"]
    C --> D["Xây DN bằng LdapNameBuilder"]
    D --> E["LdapTemplate.bind / modifyAttributes"]
    E --> F["LDAP: cn=engineering"]
    F --> G["Schema + ACL"]
    H["ldapsearch kiểm chứng"] --> F
~~~

## 6. Thiết kế API và DTO theo ý định nghiệp vụ

Một giao diện REST đơn giản:

| HTTP request | Ý nghĩa | Phản hồi thành công |
| --- | --- | --- |
| `POST /api/v1/groups` | Tạo nhóm với thành viên đầu tiên. | `201 Created` |
| `PUT /api/v1/groups/{groupId}/members/{uid}` | Bảo đảm người dùng thuộc nhóm. | `204 No Content` |
| `DELETE /api/v1/groups/{groupId}/members/{uid}` | Bảo đảm người dùng không còn thuộc nhóm. | `204 No Content`, ngoại trừ xóa thành viên cuối. |

Ví dụ tạo nhóm:

~~~http
POST /api/v1/groups
Content-Type: application/json

{
  "groupId": "engineering",
  "firstMemberUid": "lan"
}
~~~

Client chỉ được gửi tên nhóm và mã người dùng, **không gửi DN, `objectClass` hay toàn bộ giá trị `member`**. Service chịu trách nhiệm chọn OU và biến UID thành DN.

`api/CreateGroupRequest.java`:

~~~java
package com.example.directory.api;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

public record CreateGroupRequest(
        @NotBlank
        @Pattern(regexp = "[a-z][a-z0-9-]{1,31}")
        String groupId,

        @NotBlank
        @Pattern(regexp = "[a-z][a-z0-9._-]{1,31}")
        String firstMemberUid
) {}
~~~

Regex là **quy ước của bài lab**, không phải giới hạn chung của mọi LDAP DN. `@Valid` giúp kiểm tra HTTP request; service vẫn phải validate vì nó có thể được gọi từ scheduler, command hoặc test không đi qua controller.

## 7. Xây DN tương đối và DN đầy đủ

`LdapNameBuilder` hỗ trợ xây DN theo cấu trúc, tránh ghép chuỗi từ giá trị chưa tin cậy.

~~~java
import javax.naming.Name;
import org.springframework.ldap.support.LdapNameBuilder;

// DN tương đối với base dc=example,dc=org:
Name groupRelativeDn = LdapNameBuilder
        .newInstance("ou=groups")
        .add("cn", "engineering")
        .build();

// DN đầy đủ dùng làm giá trị member:
Name memberFullDn = LdapNameBuilder
        .newInstance("dc=example,dc=org")
        .add("ou", "people")
        .add("uid", "lan")
        .build();
~~~

Kết quả:

~~~text
groupRelativeDn = cn=engineering,ou=groups
memberFullDn    = uid=lan,ou=people,dc=example,dc=org
~~~

Khi thực thi `ldapTemplate.bind(groupRelativeDn, ...)`, Spring LDAP giải quyết entry tương đối với base cấu hình. Ngược lại, `memberFullDn.toString()` là một **giá trị thuộc tính** phải chứa đầy đủ các thành phần DN.

**Filter escaping và DN escaping khác nhau:** dùng `LdapNameBuilder` cho DN, `LdapQueryBuilder` cho bộ lọc. Không nối chuỗi `"cn=" + groupId + ",ou=groups"` hoặc `"(uid=" + userInput + ")"` từ HTTP request.

## 8. Vì sao cần ModificationItem thay vì ghi đè danh sách?

Một nhóm sau khi tạo:

~~~ldif
dn: cn=engineering,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: engineering
member: uid=lan,ou=people,dc=example,dc=org
~~~

Khi thêm Minh, chỉ cần:

~~~text
ADD_ATTRIBUTE member = uid=minh,ou=people,dc=example,dc=org
~~~

Sau khi thêm, entry có cả Lan và Minh.

Khi bỏ Lan, chỉ cần:

~~~text
REMOVE_ATTRIBUTE member = uid=lan,ou=people,dc=example,dc=org
~~~

Sau khi xóa, entry vẫn có Minh.

### So sánh ba cách cập nhật

| Cách | Tác động tới `member` | Phù hợp khi nào? |
| --- | --- | --- |
| `ADD_ATTRIBUTE` với một DN | Thêm **một giá trị** vào thuộc tính đa giá trị. | Thêm một người vào nhóm. |
| `REMOVE_ATTRIBUTE` với một DN | Xóa **đúng giá trị đó**. | Bỏ một người khỏi nhóm. |
| `REPLACE_ATTRIBUTE` với cả danh sách | Thay toàn bộ tập giá trị bằng danh sách mới. | Chỉ khi nghiệp vụ có ý định thay cả nhóm và đã kiểm soát cạnh tranh. |

Đừng dùng `REPLACE_ATTRIBUTE` khi chỉ muốn thêm hoặc xóa một thành viên. Cách đọc tất cả `member`, sửa một phần tử trong Java rồi ghi đè toàn bộ có thể **mất cập nhật** từ một request khác xen giữa.

Các phép Modify riêng lẻ được server xử lý như **một thao tác LDAP Modify**, nhưng nhiều thao tác Search + Modify khác nhau không tự trở thành giao dịch nhiều bước có isolation.

## 9. Cài đặt GroupMembershipService với LdapTemplate

Đoạn service sau chứa các bước chính: xây DN, kiểm tra entry người dùng, tạo nhóm, đọc `member`, thêm và xóa có chọn lọc. Mã được viết cho Spring Boot 3+ và Spring LDAP với `LdapTemplate` hỗ trợ `bind`, `lookup` và `modifyAttributes`.

`service/GroupMembershipService.java`:

~~~java
package com.example.directory.service;

import java.util.ArrayList;
import java.util.List;
import java.util.regex.Pattern;

import javax.naming.Name;
import javax.naming.NamingEnumeration;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import javax.naming.ldap.LdapName;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.ldap.AttributeInUseException;
import org.springframework.ldap.NoSuchAttributeException;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class GroupMembershipService {

    private static final Pattern GROUP_ID =
            Pattern.compile("[a-z][a-z0-9-]{1,31}");
    private static final Pattern USER_ID =
            Pattern.compile("[a-z][a-z0-9._-]{1,31}");

    private final LdapTemplate ldapTemplate;
    private final String baseDn;

    public GroupMembershipService(
            LdapTemplate ldapTemplate,
            @Value("${spring.ldap.base}") String baseDn) {
        this.ldapTemplate = ldapTemplate;
        this.baseDn = baseDn;
    }

    public void createGroup(String groupId, String firstMemberUid) {
        validateIds(groupId, firstMemberUid);
        requireUser(firstMemberUid);

        Attributes attrs = new BasicAttributes(true);
        BasicAttribute classes = new BasicAttribute("objectClass");
        classes.add("top");
        classes.add("groupOfNames");
        attrs.put(classes);
        attrs.put("cn", groupId);
        attrs.put("member", fullUserDn(firstMemberUid).toString());

        // Tạo entry: gọi bind của LdapTemplate (không phải BindRequest
        // dùng để xác thực kết nối LDAP).
        ldapTemplate.bind(relativeGroupDn(groupId), null, attrs);
    }

    public void addMember(String groupId, String uid) {
        validateIds(groupId, uid);
        requireUser(uid);

        Name groupDn = relativeGroupDn(groupId);
        Name memberDn = fullUserDn(uid);

        // PUT có ý nghĩa "bảo đảm tồn tại": nếu đã có thì không ghi.
        if (members(groupDn).contains(memberDn)) {
            return;
        }

        ModificationItem addOne = new ModificationItem(
                DirContext.ADD_ATTRIBUTE,
                new BasicAttribute("member", memberDn.toString()));

        try {
            ldapTemplate.modifyAttributes(
                    groupDn, new ModificationItem[] { addOne });
        } catch (AttributeInUseException duplicate) {
            // Giải quyết cuộc đua: request khác vừa thêm cùng DN.
            if (!members(groupDn).contains(memberDn)) {
                throw duplicate;
            }
        }
    }

    public void removeMember(String groupId, String uid) {
        validateIds(groupId, uid);

        Name groupDn = relativeGroupDn(groupId);
        Name memberDn = fullUserDn(uid);
        List<Name> current = members(groupDn);

        // DELETE idempotent: không có thành viên thì không cần thay đổi.
        if (!current.contains(memberDn)) {
            return;
        }

        // groupOfNames phải còn ít nhất một member.
        if (current.size() == 1) {
            throw new LastMemberNotAllowed();
        }

        ModificationItem removeOne = new ModificationItem(
                DirContext.REMOVE_ATTRIBUTE,
                new BasicAttribute("member", memberDn.toString()));

        try {
            ldapTemplate.modifyAttributes(
                    groupDn, new ModificationItem[] { removeOne });
        } catch (NoSuchAttributeException missing) {
            // Request khác vừa xóa cùng DN: kiểm tra lại trạng thái.
            if (members(groupDn).contains(memberDn)) {
                throw missing;
            }
        }
    }

    // Dùng DN tương đối vì ContextSource đã có baseDn.
    private Name relativeGroupDn(String groupId) {
        return LdapNameBuilder.newInstance("ou=groups")
                .add("cn", groupId)
                .build();
    }

    private Name relativeUserDn(String uid) {
        return LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();
    }

    // Giá trị thuộc tính member PHẢI chứa DN đầy đủ.
    private Name fullUserDn(String uid) {
        return LdapNameBuilder.newInstance(baseDn)
                .add("ou", "people")
                .add("uid", uid)
                .build();
    }

    private void requireUser(String uid) {
        // Schema member dạng DN thường không tự đảm bảo entry tồn tại.
        ldapTemplate.lookup(
                relativeUserDn(uid),
                new String[] { "uid" },
                (AttributesMapper<String>) attrs -> {
                    Attribute attr = attrs.get("uid");
                    if (attr == null) {
                        throw new IllegalStateException(
                                "Cannot read uid of member entry");
                    }
                    return attr.get().toString();
                });
    }

    private List<Name> members(Name groupDn) {
        return ldapTemplate.lookup(
                groupDn,
                new String[] { "member" },
                (AttributesMapper<List<Name>>) attrs -> {
                    Attribute member = attrs.get("member");
                    if (member == null) {
                        // Không coi ACL che giấu member là nhóm rỗng.
                        throw new IllegalStateException(
                                "Cannot read group members");
                    }

                    List<Name> names = new ArrayList<>();
                    NamingEnumeration<?> values = member.getAll();
                    try {
                        while (values.hasMore()) {
                            names.add(new LdapName(
                                    values.next().toString()));
                        }
                    } finally {
                        values.close();
                    }
                    return names;
                });
    }

    private static void validateIds(String groupId, String uid) {
        if (groupId == null || !GROUP_ID.matcher(groupId).matches()
                || uid == null || !USER_ID.matcher(uid).matches()) {
            throw new IllegalArgumentException(
                    "Invalid groupId or uid");
        }
    }

    public static class LastMemberNotAllowed
            extends RuntimeException {
    }
}
~~~

### Giải thích những quyết định trong code

1. **Entry nhóm và entry người dùng khác DN:** `relativeGroupDn` dùng `ou=groups`; `relativeUserDn` dùng `ou=people`. Cả hai tương đối theo `spring.ldap.base`.
2. **`fullUserDn` dùng cho thuộc tính `member`:** DN không bị cắt mất `dc=example,dc=org`.
3. **`requireUser` chỉ xác nhận entry được nhìn thấy:** khi thiếu entry, `LdapTemplate.lookup` phát sinh ngoại lệ tương ứng; application có thể ánh xạ thành 404. Khi ACL không cho đọc `uid`, code báo lỗi thay vì khẳng định user không tồn tại.
4. **Create có một thành viên ngay từ đầu:** đáp ứng `MUST member` của `groupOfNames`.
5. **Add và Remove gửi một `ModificationItem`:** không thay thế cả thuộc tính đa giá trị.
6. **`members(...)` dùng `LdapName`:** so sánh theo cấu trúc DN thay vì so sánh nguyên chuỗi có thể khác cách biểu diễn ký tự.
7. **Idempotency ở mức mục tiêu:** gửi lặp PUT hoặc DELETE thường không thay đổi kết quả đã đạt; nếu gặp đua ghi trùng, xử lý riêng kết quả LDAP.
8. **Không có transaction nhiều bước tự động:** kiểm tra user tồn tại, đọc member và Modify là các request khác nhau. Người khác có thể thay đổi directory giữa các request.

**Giới hạn quan trọng:** `members` phải được Bind DN của service account phép đọc thuộc tính `member`. Nếu ACL ẩn một phần giá trị, phép kiểm tra “thành viên cuối” có thể không chính xác; phải thực thi quyền quản lý nhóm bằng tài khoản được phép nhìn thấy toàn bộ nhóm và **để server xác minh schema** ở bước Modify.

### Trường hợp cạnh tranh khi xóa thành viên cuối

Giả sử nhóm có hai thành viên A, B. Request 1 đọc hai giá trị rồi định xóa A; request 2 cũng đọc hai giá trị rồi định xóa B. Cả hai điều kiện `size > 1` đều đúng ở thời điểm đọc. Tuy vậy, khi một request xóa thành công, request còn lại có thể bị server từ chối do xóa giá trị `member` cuối cùng vi phạm schema.

Vì thế **kiểm tra trong Java giúp phản hồi dễ hiểu, còn schema server là lớp bảo vệ cuối cùng**. Không thể dùng vòng đọc-rồi-xóa như một “khóa” đảm bảo phân tách đồng thời. Hãy bắt/ánh xạ lỗi `objectClassViolation` thành trạng thái xung đột phù hợp và kiểm thử đồng thời.

## 10. Tạo controller và xử lý lỗi HTTP

`web/GroupController.java`:

~~~java
package com.example.directory.web;

import java.net.URI;

import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.example.directory.api.CreateGroupRequest;
import com.example.directory.service.GroupMembershipService;

@RestController
@RequestMapping("/api/v1/groups")
public class GroupController {

    private final GroupMembershipService groups;

    public GroupController(GroupMembershipService groups) {
        this.groups = groups;
    }

    @PostMapping
    public ResponseEntity<Void> create(
            @Valid @RequestBody CreateGroupRequest request) {
        groups.createGroup(
                request.groupId(), request.firstMemberUid());
        URI location = URI.create(
                "/api/v1/groups/" + request.groupId());
        return ResponseEntity.created(location).build();
    }

    @PutMapping("/{groupId}/members/{uid}")
    public ResponseEntity<Void> add(
            @PathVariable String groupId,
            @PathVariable String uid) {
        groups.addMember(groupId, uid);
        return ResponseEntity.noContent().build();
    }

    @DeleteMapping("/{groupId}/members/{uid}")
    public ResponseEntity<Void> remove(
            @PathVariable String groupId,
            @PathVariable String uid) {
        groups.removeMember(groupId, uid);
        return ResponseEntity.noContent().build();
    }
}
~~~

Controller nhận **ID nghiệp vụ**, không nhận `memberDn` tùy ý. Những API thay đổi nhóm phải nằm sau lớp HTTP authentication/authorization: ví dụ chỉ người quản trị một nhóm mới được thêm/xóa thành viên của nhóm đó.

Chú ý `@Valid` chỉ áp dụng cho record của POST; hai path variable của PUT/DELETE đã được service kiểm tra bằng regex. Client không thể chọn trực tiếp `ou=admins` hay subtree tùy ý.

### Quy ước mã lỗi gợi ý

| Lỗi | HTTP | Cách xử lý |
| --- | --- | --- |
| Tạo nhóm hợp lệ | 201 | Có Location trỏ đến nhóm vừa tạo. |
| PUT/DELETE hoàn tất hoặc đã ở trạng thái mong muốn | 204 | Không cần body. |
| ID không đúng quy tắc | 400 | Từ chối trước khi xây DN. |
| Người dùng hoặc nhóm không tồn tại | 404 | Ánh xạ `NameNotFoundException` theo use case. |
| Tạo nhóm trùng DN | 409 | Ánh xạ `NameAlreadyBoundException`. |
| Xóa thành viên cuối | 409 | Ánh xạ `LastMemberNotAllowed` hoặc lỗi schema tương ứng. |
| Lỗi quyền LDAP | 403 hoặc mã nghiệp vụ phù hợp | Ghi log nội bộ, không tiết lộ DN/ACL nhạy cảm. |
| Timeout, không kết nối được directory | 503 | Không trả sai thành viên là “không có”. |

Lớp `@RestControllerAdvice` của dự án nên ánh xạ các exception cụ thể theo hợp đồng API. Không trả nguyên LDAP exception/message chứa DN dịch vụ, trace hoặc thông tin nhạy cảm cho client.

## 11. Kiểm chứng bằng ldapsearch và ldapmodify

Có thể quan sát kết quả độc lập với Java bằng CLI LDAP. Các lệnh dùng **LDAPS**, yêu cầu certificate hợp lệ và tùy môi trường phải cấu hình CA tin cậy.

Đọc nhóm:

~~~bash
ldapsearch -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-group-manager,ou=service,dc=example,dc=org" -W \
  -b "cn=engineering,ou=groups,dc=example,dc=org" -s base \
  "(objectClass=groupOfNames)" \
  dn objectClass cn member
~~~

Sau khi tạo nhóm, chỉ có `member` của Lan. Sau khi PUT thêm Minh, có **hai giá trị `member`**.

### LDIF thay đổi chọn lọc: thêm một thành viên

Một file thay đổi LDAP Modify có nội dung:

~~~ldif
dn: cn=engineering,ou=groups,dc=example,dc=org
changetype: modify
add: member
member: uid=minh,ou=people,dc=example,dc=org
-
~~~

Đây là tương đương ở mức giao thức với `DirContext.ADD_ATTRIBUTE` dành cho giá trị cụ thể. Khi dùng `ldapmodify`, bạn có thể nạp LDIF này bằng tài khoản có quyền sửa nhóm; chỉ nạp **một lần** khi entry chưa có Minh, nếu không server có thể báo giá trị đã tồn tại.

### LDIF thay đổi chọn lọc: xóa một thành viên

~~~ldif
dn: cn=engineering,ou=groups,dc=example,dc=org
changetype: modify
delete: member
member: uid=lan,ou=people,dc=example,dc=org
-
~~~

Đây là tương đương `DirContext.REMOVE_ATTRIBUTE` với **một giá trị**. **Không xóa cả thuộc tính `member`** của nhóm `groupOfNames` vì thuộc tính này bắt buộc. Khi chỉ còn Lan, phải thêm một thành viên hợp lệ trước khi bỏ Lan, hoặc chuyển quy trình thành xóa cả nhóm nếu nghiệp vụ cho phép.

### Lệnh đọc lại sau thay đổi

~~~bash
ldapsearch -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-group-manager,ou=service,dc=example,dc=org" -W \
  -b "ou=groups,dc=example,dc=org" -s one \
  "(&(objectClass=groupOfNames)(cn=engineering))" \
  dn cn member
~~~

Đừng dựa vào thứ tự in ra của các giá trị `member`: LDAP không mặc định đảm bảo thứ tự giá trị của một thuộc tính đa trị. So sánh **tập DN**, không so sánh chuỗi kết quả theo vị trí.

## 12. Kiểm thử tích hợp với directory thật

Unit test/mock có thể kiểm tra code gọi `modifyAttributes` với đúng `ModificationItem`, nhưng chỉ server LDAP thật/nhúng có schema tương ứng mới xác minh được lỗi `objectClassViolation`, quy tắc DN matching và ACL.

Một kế hoạch kiểm thử thực tế:

1. Khởi tạo test directory có `dc=example,dc=org`, `ou=people`, `ou=groups` và hai người dùng có DN xác định.
2. Cấu hình `spring.ldap.base` và service account có quyền ghi nhóm trong phạm vi thử nghiệm.
3. Gọi `createGroup("engineering","lan")`, đọc lại nhóm, xác nhận đúng một thành viên.
4. Gọi `addMember("engineering","minh")`, xác nhận nhóm có cả Lan và Minh.
5. Gọi lại `addMember("engineering","minh")`, xác nhận không có giá trị trùng và không lỗi.
6. Gọi `removeMember("engineering","lan")`, xác nhận chỉ còn Minh.
7. Gọi lại `removeMember("engineering","lan")`, xác nhận trạng thái không đổi.
8. Gọi `removeMember("engineering","minh")`, kỳ vọng từ chối vì nhóm sẽ rỗng.
9. Kiểm tra các thuộc tính khác (`cn`, `description`, `objectClass`) không bị biến đổi bởi thay đổi thành viên.
10. Dọn nhóm thử nghiệm sau test; không xóa OU/dữ liệu chia sẻ.

### Mẫu test JUnit 5

Ví dụ bên dưới tập trung xác minh luồng tạo/thêm/bỏ và giả định mỗi test dùng directory riêng hoặc có fixture được reset:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.HashSet;
import java.util.Set;

import javax.naming.directory.Attribute;
import javax.naming.NamingEnumeration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;

@SpringBootTest
class GroupMembershipIntegrationTest {

    @Autowired GroupMembershipService service;
    @Autowired LdapTemplate ldapTemplate;

    private Set<String> memberDns(String groupId) {
        return ldapTemplate.lookup(
                "cn=" + groupId + ",ou=groups",
                new String[] { "member" },
                (AttributesMapper<Set<String>>) attrs -> {
                    Set<String> result = new HashSet<>();
                    Attribute member = attrs.get("member");
                    NamingEnumeration<?> values = member.getAll();
                    try {
                        while (values.hasMore()) {
                            result.add(values.next().toString());
                        }
                    } finally {
                        values.close();
                    }
                    return result;
                });
    }

    @Test
    void selectivelyModifiesOnlyRequestedMembers() {
        service.createGroup("engineering", "lan");
        String lan = "uid=lan,ou=people,dc=example,dc=org";
        String minh = "uid=minh,ou=people,dc=example,dc=org";

        assertEquals(Set.of(lan), memberDns("engineering"));

        service.addMember("engineering", "minh");
        service.addMember("engineering", "minh");
        assertEquals(Set.of(lan, minh), memberDns("engineering"));

        service.removeMember("engineering", "lan");
        service.removeMember("engineering", "lan");
        assertEquals(Set.of(minh), memberDns("engineering"));

        assertThrows(
                GroupMembershipService.LastMemberNotAllowed.class,
                () -> service.removeMember("engineering", "minh"));

        assertEquals(Set.of(minh), memberDns("engineering"));
    }
}
~~~

Trong test, `groupId` là hằng số do test kiểm soát; với code production **không nối chuỗi DN từ đầu vào request** như helper đơn giản trong test. Test nên tạo và xóa fixture qua setup/teardown, hoặc dùng tên nhóm khác nhau giữa các lần chạy để tránh `Already exists`.

### Ma trận kiểm thử mở rộng

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Tạo nhóm với thành viên hợp lệ | Có `cn`, chuỗi `objectClass` đúng, đúng một `member`. |
| Tạo nhóm với `firstMemberUid` không tồn tại | API lỗi rõ ràng; không tạo DN tham chiếu ngoài ý muốn. |
| Tạo nhóm thiếu `member` | LDAP server từ chối vì schema `groupOfNames`. |
| Tạo nhóm có DN đã tồn tại | Không ghi đè; trả conflict. |
| Thêm thành viên chưa có | Chỉ thêm một giá trị `member`. |
| Thêm thành viên đã có | PUT idempotent, kết quả không đổi. |
| Xóa một người trong nhóm nhiều thành viên | Chỉ bỏ đúng DN đã chọn. |
| Xóa người không thuộc nhóm | DELETE idempotent, kết quả không đổi. |
| Xóa thành viên cuối | Bị từ chối; nhóm vẫn có ít nhất một `member`. |
| PUT/DELETE đồng thời | Không làm mất cập nhật ngoài ý muốn; ghi nhận xung đột/schema exception và trạng thái thực. |
| Tài khoản thiếu quyền MODIFY | Bị ACL từ chối; không được tự tăng quyền. |
| LDAP mất kết nối | Không báo thành công giả; kiểm tra trạng thái trước khi retry. |
| Đổi DN của người dùng | Kiểm tra `member` có được cập nhật bởi referential-integrity overlay hay chưa. |
| Spring base DN không khớp | Bị lỗi tên hoặc trỏ sai nhánh; không tự sửa thành DN client gửi. |
| Ký tự đặc biệt trong ID | Validation chặn hoặc API DN builder escape đúng chuẩn. |
| Các thuộc tính khác của nhóm | Vẫn giữ nguyên sau từng Modify riêng lẻ. |

## 13. Các vấn đề với danh tính và thay đổi DN

Thuộc tính `member` chứa **DN**, không phải “mã tài khoản luôn bất biến”. Nếu người dùng `uid=lan` được chuyển sang OU khác hoặc đổi RDN, DN mới sẽ khác DN đã lưu trong nhóm.

Một số directory có cơ chế **referential integrity** để cập nhật DN tham chiếu khi Rename/Move/Delete; nhiều directory không tự làm điều đó theo mặc định. Vì vậy cần:

- Xác định chính sách đổi DN của người dùng.
- Kiểm tra LDAP server có overlay/tính năng cập nhật `member` hay không.
- Trước/sau Rename, xác minh nhóm trỏ tới DN hiện còn tồn tại.
- Nếu ứng dụng tự quản lý, xây quy trình cập nhật tham chiếu có đối soát và xử lý thất bại từng phần.

**Không giả định** kiểm tra `requireUser(...)` xong thì DN chắc chắn tồn tại tới khi Modify kết thúc. Người dùng có thể bị xóa/đổi DN giữa hai request; LDAP cơ bản không áp dụng khóa cho toàn bộ workflow Java.

## 14. Khi cần dùng repository hoặc ODM

Spring Data LDAP repository tiện để truy vấn/ánh xạ nhóm thành entity Java:

~~~java
import java.util.Set;
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=groups",
    objectClasses = { "top", "groupOfNames" }
)
public class DirectoryGroup {

    @Id
    private Name dn;

    @Attribute(name = "cn")
    private String name;

    @Attribute(name = "member")
    private Set<Name> members;

    // Getter/setter trong triển khai thực tế.
}
~~~

~~~java
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryGroupRepository
        extends LdapRepository<DirectoryGroup> {
}
~~~

Kiểu `Set<Name>` giúp biểu diễn `member` là tập DN, tránh coi nó như một chuỗi duy nhất. Spring LDAP ODM có khả năng ánh xạ DN, nhưng **hành vi ghi cập nhật cả tập** phụ thuộc đường gọi và mapping. Cần kiểm thử trên phiên bản thư viện và directory thực tế.

Với yêu cầu **“thêm/bỏ một DN”**, `LdapTemplate.modifyAttributes(Name, ModificationItem[])` vẫn là cách trực tiếp để diễn đạt ý định **chỉ thay đổi một giá trị**, thay vì tải entity có `members`, chỉnh `Set` rồi gọi `repository.save(...)` khi chưa kiểm soát concurrent writes.

Không cần dùng repository cho tất cả thao tác nếu `LdapTemplate` diễn đạt đúng nghiệp vụ hơn. Bạn có thể dùng repository cho đọc/tra cứu, còn service thực hiện Modify có chọn lọc bằng template.

## 15. Bảo mật, ACL và vận hành

Quản lý nhóm thường liên quan trực tiếp đến quyền truy cập ứng dụng. Vì thế ranh giới bảo mật cần rõ ràng:

- **Xác thực và phân quyền HTTP:** service LDAP Bind thành công chỉ xác thực **service account**, không xác thực người đang gọi REST API. Chỉ người có quyền quản lý nhóm mới được PUT/DELETE thành viên.
- **Phân quyền tại LDAP:** tài khoản dịch vụ chỉ nên có quyền đọc người dùng cần thiết và sửa `member` ở các nhóm được ủy quyền. Tránh cấp quyền quản trị toàn directory.
- **TLS:** dùng LDAPS/StartTLS đúng cách và kiểm tra chứng chỉ/hostname, không gửi mật khẩu Simple Bind qua plaintext.
- **Không nhận DN từ client:** app chọn base/OU và tạo DN bằng API DN builder, không cho sửa nhóm quản trị bằng cách thay `groupId` thành DN tùy ý.
- **Giới hạn Search:** nếu cần tìm người bằng `uid`, dùng `LdapQueryBuilder.where("uid").is(value)`, escape giá trị theo RFC 4515 và giới hạn base/scope.
- **Audit thay đổi nhóm:** log actor ứng dụng, ID yêu cầu, nhóm, UID, thao tác và kết quả; không log mật khẩu, token hoặc thuộc tính cá nhân không cần thiết.
- **Rate limit và chống lạm dụng:** tránh cho một client gọi Modify hàng loạt không kiểm soát.
- **Kiểm tra quyền đọc `member`:** service phải nhìn thấy đầy đủ thành viên nếu dùng logic phát hiện “thành viên cuối”. Nếu ACL không đủ, trả lỗi và dùng server schema làm lớp kiểm tra cuối.
- **Không dùng `@Transactional` như lời hứa ACID:** Spring LDAP compensating transaction (nếu cấu hình) chỉ cố hoàn tác, không mang lại isolation hay giao dịch phân tán chắc chắn.

### Phân biệt ba loại “xóa”

| Thao tác | Hành vi |
| --- | --- |
| `REMOVE_ATTRIBUTE` với một giá trị `member` | Bỏ đúng một người khỏi nhóm. |
| `REMOVE_ATTRIBUTE` không chỉ định giá trị | Có thể xóa **cả thuộc tính `member`**, vi phạm schema `groupOfNames`. |
| `LdapTemplate.unbind(groupDn)` | Xóa **toàn entry nhóm**; chỉ làm khi nghiệp vụ cho phép và ACL phù hợp. |

**Lưu ý tên `bind`/`unbind`:** ở API `LdapTemplate`, chúng là thao tác **tạo/xóa entry**; đừng nhầm với Bind/Unbind ở mức giao thức dùng để đăng nhập và kết thúc kết nối LDAP.

## 16. Bài tập mở rộng

**Bài 1 — Tạo nhóm thứ hai.** Tạo `qa-team` có thành viên đầu tiên là Minh. Kiểm tra mọi DN trong `member` đều đầy đủ và trỏ đúng entry dưới `ou=people`.

**Bài 2 — Xử lý HTTP 409.** Viết `@RestControllerAdvice` chuyển `LastMemberNotAllowed`, `NameAlreadyBoundException` và một số lỗi schema thành thông báo rõ ràng; bảo đảm không rò rỉ DN của tài khoản dịch vụ.

**Bài 3 — Xử lý Remove đồng thời.** Tạo nhóm có hai thành viên; chạy hai request xóa đồng thời và ghi nhận request nào bị directory từ chối. Không chấp nhận kết quả nhóm `groupOfNames` rỗng sau khi hai request kết thúc.

**Bài 4 — So sánh chiến lược cập nhật.** Viết một bản thử nghiệm dùng `REPLACE_ATTRIBUTE` để cập nhật toàn danh sách, một bản dùng `ADD_ATTRIBUTE`. Cho hai client cùng thêm hai người khác nhau và phân tích rủi ro mất cập nhật.

**Bài 5 — Tìm nhóm của một người.** Dùng `LdapQueryBuilder` xây filter chính xác `(member=<DN đầy đủ>)` theo DN được tạo từ uid, giới hạn base `ou=groups` và kiểm tra kết quả bằng service account được phép đọc.

**Bài 6 — Đổi DN và referential integrity.** Thử Rename user trong directory test rồi đọc lại `member`, đối chiếu với hành vi overlay/cấu hình thực của server. Đề xuất quy trình xử lý các nhóm trỏ đến DN không tồn tại.

## 17. Câu hỏi tự đánh giá

1. Vì sao tạo `groupOfNames` phải có `member` ngay từ lúc tạo?
2. `groupOfNames` khác `groupOfUniqueNames` ở tên thuộc tính thành viên thế nào?
3. Vì sao giá trị `member` phải là DN đầy đủ trong khi `LdapTemplate` có thể dùng DN tương đối?
4. `ADD_ATTRIBUTE` và `REPLACE_ATTRIBUTE` khác nhau thế nào khi hai request thêm thành viên cùng lúc?
5. Cần chỉ định gì cho `REMOVE_ATTRIBUTE` để chỉ bỏ một thành viên?
6. Khi xóa người cuối cùng, schema của `groupOfNames` yêu cầu điều gì?
7. Vì sao `memberOf` có thể không xuất hiện trên entry người dùng dù họ thuộc nhóm?
8. Đọc danh sách hiện tại rồi mới Modify có ngăn được hoàn toàn race condition không?
9. Vì sao PUT thêm thành viên phù hợp với thiết kế idempotent?
10. Làm sao kiểm chứng cập nhật thành viên không làm thay đổi `cn`, `objectClass` và `description`?
11. Nếu directory chặn Simple Bind không dùng TLS, ứng dụng phải thay đổi gì?
12. Khi nào nên dùng repository, khi nào nên dùng `LdapTemplate.modifyAttributes(...)`?

**Ghi nhớ:** chọn `groupOfNames` khi muốn biểu diễn nhóm bằng tập DN `member`; tạo nhóm với `cn` và ít nhất một `member`; cập nhật bằng **`ADD_ATTRIBUTE` hoặc `REMOVE_ATTRIBUTE` cho một DN cụ thể**. Hãy dùng DN builder, giới hạn ACL/TLS, kiểm tra thành viên cuối và kiểm thử cạnh tranh, vì cập nhật chọn lọc giúp giảm nguy cơ ghi đè nhưng không tự tạo giao dịch nhiều bước có isolation.

### Tài liệu tham khảo

- [RFC 4519 — LDAP: Schema for User Applications](https://www.rfc-editor.org/rfc/rfc4519): `groupOfNames`, `groupOfUniqueNames`, `member` và `uniqueMember`.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): Search/Modify và các thao tác LDAP.
- [RFC 4514 — LDAP: String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): DN và escaping DN.
- [RFC 4515 — LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515): cú pháp/escaping filter.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): `bind`, `lookup` và `modifyAttributes`.
- [Spring LDAP — Basic Usage](https://docs.spring.io/spring-ldap/reference/spring-ldap-basic-usage.html): tạo và sửa entry với LDAP.
- [Spring LDAP — Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): base LDAP path và `ContextSource`.
- [Spring LDAP — ODM](https://docs.spring.io/spring-ldap/reference/odm.html): ánh xạ entry nhóm và các giá trị DN.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): repository và tích hợp Java object.
