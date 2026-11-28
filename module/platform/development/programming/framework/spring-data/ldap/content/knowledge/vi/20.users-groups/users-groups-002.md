# Mô hình nhóm với groupOfNames và groupOfUniqueNames

## Mục tiêu bài học

LDAP lưu người dùng và nhóm trong một cây các **entry** có **distinguished name (DN)**. Ở module **SPRING_DATA_LDAP**, chúng ta dùng Spring Data LDAP để ánh xạ entry sang đối tượng Java, khai thác repository hoặc **LdapTemplate** để tìm kiếm và thay đổi dữ liệu. Khi cần quản lý thành viên của một nhóm, phải hiểu trước cách LDAP biểu diễn nhóm bằng **objectClass** và thuộc tính tham chiếu đến DN của thành viên.

Bài này tập trung vào hai lớp nhóm phổ biến trong LDAP schema chuẩn: **groupOfNames** và **groupOfUniqueNames**. Học xong, bạn có thể:

- Phân biệt thuộc tính **member** của groupOfNames và **uniqueMember** của groupOfUniqueNames.
- Tạo LDIF hợp lệ, hiểu vì sao nhóm thường phải có ít nhất một thành viên theo schema.
- Dùng **LdapTemplate** để tạo nhóm, thêm/xóa thành viên và tìm các nhóm chứa một người dùng.
- Hiểu vị trí của Spring Data LDAP repository, DN tương đối so với base DN và DN đầy đủ lưu trong thuộc tính thành viên.
- Xử lý an toàn bộ lọc LDAP, thay đổi DN của người dùng, giới hạn tham chiếu và kiểm thử trên directory thật.

## 1. Người dùng và nhóm trong cây LDAP

Ví dụ một directory của tổ chức có cây:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=an
│   ├── uid=binh
│   └── uid=chi
└── ou=groups
    ├── cn=backend
    └── cn=approvers
~~~

DN đầy đủ của người dùng An là **uid=an,ou=people,dc=example,dc=org**. DN đầy đủ của nhóm backend là **cn=backend,ou=groups,dc=example,dc=org**.

Một entry nhóm thông thường không chứa bản sao hồ sơ của từng người dùng. Thay vào đó, nó chứa các **giá trị DN** trỏ đến entry của các thành viên. Mô hình này giúp phân biệt rõ:

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| **DN của nhóm** | cn=backend,ou=groups,dc=example,dc=org | Định danh chính entry nhóm |
| **cn của nhóm** | backend | Tên nhóm; thường là một phần RDN |
| **DN của người dùng** | uid=an,ou=people,dc=example,dc=org | Định danh entry thành viên |
| **member hoặc uniqueMember** | DN của An | Thuộc tính tham chiếu thành viên trong nhóm |

Trong các thao tác LdapTemplate, nếu ứng dụng cấu hình **base DN = dc=example,dc=org**, DN dùng để xác định **entry nhóm** thường là **cn=backend,ou=groups** (tương đối với base). Nhưng **giá trị member/uniqueMember** trong entry nhóm là một DN tham chiếu, thường biểu diễn bằng **DN đầy đủ**, gồm cả **dc=example,dc=org**.

Phân biệt hai kiểu DN này rất quan trọng: nếu nhầm DN tương đối của thao tác với DN đầy đủ của thành viên, ứng dụng có thể lưu sai tham chiếu hoặc tìm kiếm không khớp.

## 2. Hai object class nhóm trong schema

### 2.1. groupOfNames

**groupOfNames** là một **STRUCTURAL object class** dùng để biểu diễn một nhóm các DN. Theo schema phổ biến được chuẩn hóa trong RFC 4519, lớp này kế thừa **top**, yêu cầu:

- **cn (MUST):** tên nhóm.
- **member (MUST):** một hoặc nhiều giá trị DN đại diện thành viên.

Các thuộc tính bổ sung được phép có có thể gồm **description**, **owner**, **ou**, **seeAlso**, **businessCategory** và một số thuộc tính khác do schema quy định.

Ví dụ LDIF:

~~~ldif
dn: cn=backend,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: backend
description: Nhom phat trien dich vu backend
member: uid=an,ou=people,dc=example,dc=org
member: uid=binh,ou=people,dc=example,dc=org
~~~

Hai dòng **member** cùng tên thuộc tính tạo thành một thuộc tính LDAP đa giá trị, chứa hai DN. Đó là hai giá trị của **member**, không phải hai thuộc tính với tên khác nhau.

Điểm dễ nhầm: nhóm này **không lưu danh sách uid đơn thuần** như **an, binh**. Giá trị thành viên là DN để chỉ đúng vị trí entry trong cây.

### 2.2. groupOfUniqueNames

**groupOfUniqueNames** cũng là **STRUCTURAL object class** dùng để mô tả nhóm, nhưng dùng thuộc tính:

- **cn (MUST):** tên nhóm.
- **uniqueMember (MUST):** một hoặc nhiều giá trị theo cú pháp **Name And Optional UID** (DN và phần UID tùy chọn).

Ví dụ thông thường, chỉ sử dụng DN:

~~~ldif
dn: cn=approvers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfUniqueNames
cn: approvers
description: Nhom phe duyet thay doi
uniqueMember: uid=chi,ou=people,dc=example,dc=org
uniqueMember: uid=an,ou=people,dc=example,dc=org
~~~

Giá trị **uniqueMember** có thể chỉ gồm một DN như ví dụ. Cú pháp **Name And Optional UID** còn có dạng DN cộng một phần **UID tùy chọn** được biểu diễn bằng bit string theo quy tắc LDAP. Phần này nhằm giúp phân biệt danh tính entry trong tình huống một DN có thể được tái sử dụng cho entry khác.

**UID tùy chọn trong uniqueMember không đồng nghĩa với thuộc tính uid của người dùng.** Spring Data LDAP không tự động lấy **uid=an** để thêm phần UID tùy chọn vào mọi giá trị **uniqueMember**. Cách dùng phổ biến vẫn là giá trị DN đơn thuần; nếu muốn khai thác phần UID tùy chọn, phải xác nhận khả năng hỗ trợ và quy ước của directory.

### 2.3. So sánh trực tiếp

| Tiêu chí | groupOfNames | groupOfUniqueNames |
| --- | --- | --- |
| Loại object class | STRUCTURAL | STRUCTURAL |
| Thuộc tính thành viên bắt buộc | **member** | **uniqueMember** |
| Cú pháp giá trị thành viên | **Distinguished Name** | **Name And Optional UID** |
| Có thể lưu nhiều thành viên | Có | Có |
| Bắt buộc có **cn** | Có | Có |
| Có thể tạo nhóm không thành viên theo class chuẩn? | Không; **member** là MUST | Không; **uniqueMember** là MUST |
| Có tự sinh thuộc tính **memberOf** trên người dùng? | Không | Không |
| Có bảo đảm DN tham chiếu luôn tồn tại và tự cập nhật khi rename? | Không; tùy server/chính sách | Không; tùy server/chính sách |

Hai class này đều thuộc loại **STRUCTURAL** và không nằm trên cùng một chuỗi kế thừa. Vì thế, **không nên gắn cả groupOfNames lẫn groupOfUniqueNames vào cùng một entry** như cách kết hợp STRUCTURAL và AUXILIARY. Chúng là hai mô hình nhóm riêng; chọn một kiểu phù hợp với directory và quy ước của ứng dụng.

Tên **uniqueMember** cũng không có nghĩa LDAP sẽ bảo đảm mỗi tài khoản chỉ thuộc một nhóm, chỉ được có một bản ghi nhóm trên toàn cây, hoặc tự sửa mọi tham chiếu khi tài khoản đổi DN. Trùng lặp giá trị trong cùng thuộc tính được xử lý theo matching rule của directory, nhưng **tính toàn vẹn tham chiếu** là vấn đề riêng.

## 3. Schema quyết định nhóm có hợp lệ hay không

Schema chuẩn định nghĩa những thuộc tính nào bắt buộc và những giá trị nào hợp lệ. Với **groupOfNames**:

~~~text
objectClass: groupOfNames
MUST: cn, member
~~~

Với **groupOfUniqueNames**:

~~~text
objectClass: groupOfUniqueNames
MUST: cn, uniqueMember
~~~

Ví dụ sau nhìn có vẻ là một nhóm, nhưng **không hợp lệ** nếu dùng nguyên schema groupOfNames thông thường:

~~~ldif
dn: cn=empty-team,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: empty-team
~~~

Entry thiếu **member**. Server thường từ chối thao tác Add với lỗi **objectClassViolation (65)**. Tương tự, nếu một nhóm groupOfUniqueNames chưa có **uniqueMember**, yêu cầu schema chưa được đáp ứng.

Những cách thiết kế cho trường hợp nhóm chưa có người dùng:

1. **Chưa tạo entry nhóm** cho đến khi có thành viên đầu tiên.
2. **Chọn một class nhóm khác** mà schema cho phép nhóm rỗng (nếu directory hỗ trợ và phù hợp yêu cầu); không gọi nhầm đó là groupOfNames.
3. **Định nghĩa thành viên khởi tạo có thật** theo quy tắc nghiệp vụ, chẳng hạn một tài khoản dịch vụ được phép tham gia. Không thêm DN giả chỉ để vượt qua ràng buộc schema nếu quy trình cấp quyền sử dụng thông tin thành viên.

Không nên xóa giá trị **member cuối cùng** của groupOfNames rồi kỳ vọng directory giữ lại một nhóm rỗng: thao tác Modify có thể bị server từ chối vì vi phạm MUST. Cần xác định chính sách ứng dụng trước khi xóa thành viên cuối.

## 4. Các quan hệ nhóm cần phân biệt

### 4.1. Nhóm lưu thành viên, không phải thành viên lưu nhóm

Trong ví dụ chuẩn, nguồn dữ liệu trực tiếp của quan hệ thành viên là thuộc tính trên **entry nhóm**:

~~~text
cn=backend,ou=groups,...
  member: uid=an,ou=people,...
  member: uid=binh,ou=people,...
~~~

Không được mặc định rằng entry **uid=an** sẽ có **memberOf: cn=backend,...**. Một số directory (hoặc plugin như memberOf overlay) có thể tính thuộc tính ngược **memberOf**, nhưng đây là khả năng triển khai, không phải đặc điểm tất yếu của mọi groupOfNames/groupOfUniqueNames. Ở nhiều server, **memberOf** là thuộc tính vận hành hoặc được quản lý riêng, có thể không trả về nếu không yêu cầu đúng cách.

Để tìm các nhóm chứa một DN cụ thể, cách phù hợp và có thể kiểm soát rõ ràng là **tìm trong nhánh nhóm theo member hoặc uniqueMember**.

### 4.2. Nhóm lồng nhau và quyền hiệu lực

Một thuộc tính thành viên kiểu DN về mặt dữ liệu có thể trỏ tới entry nhóm khác nếu mô hình và chính sách directory cho phép. Ví dụ:

~~~ldif
dn: cn=engineering,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: engineering
member: cn=backend,ou=groups,dc=example,dc=org
~~~

Nhưng từ đó **không thể tự kết luận** An là thành viên trực tiếp của engineering hoặc An tự động có mọi quyền cấp cho engineering. Quy tắc duyệt nhóm lồng nhau, chống chu trình và tính quyền hiệu lực phụ thuộc hệ thống xác thực/ủy quyền và directory server.

Khi ứng dụng cần nhóm lồng nhau, phải quy định rõ **thành viên trực tiếp** và **thành viên suy diễn**, mức sâu được phép, xử lý vòng lặp và giới hạn truy vấn. Đặc biệt không dùng kết quả tìm nhóm một cấp để đại diện mọi quyền mà người dùng có.

### 4.3. Tham chiếu DN không phải khóa ngoại SQL

Trong một số directory, server có thể nhận một giá trị **member** trỏ tới DN chưa tồn tại; việc kiểm tra hay tự sửa tham chiếu khi rename/delete phụ thuộc plugin, overlay và chính sách sản phẩm. Vì vậy:

- Khi **tạo nhóm**, ứng dụng nên kiểm tra DN người dùng mục tiêu tồn tại và có đúng loại entry.
- Khi **đổi DN người dùng**, kiểm tra cơ chế cập nhật tham chiếu nhóm; có thể cần sửa các giá trị **member/uniqueMember**.
- Khi **xóa người dùng**, phải xác định chính sách gỡ người dùng khỏi nhóm hoặc giữ lịch sử phù hợp; tránh để tham chiếu cũ tác động sai tới tài khoản mới dùng lại DN.

Trong trường hợp giá trị **uniqueMember** có phần optional UID, matching rule và quy tắc cập nhật còn cần được xác nhận với server đích. Không tùy ý thay chuỗi **uniqueMember** bằng một giá trị chỉ chứa **uid**.

## 5. Chuẩn bị Spring Data LDAP và kết nối

Trong dự án Spring Boot, có thể dùng starter:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
}
~~~

Ví dụ cấu hình cho directory thử nghiệm có hỗ trợ LDAPS:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: uid=svc-app,ou=service-accounts,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

**base** xác định gốc thao tác, còn **username** là DN dùng để bind/xác thực. Tài khoản ứng dụng phải có ACL tối thiểu cần thiết trên **ou=groups**, và quyền đọc cần thiết trên **ou=people**. Sử dụng LDAPS hoặc StartTLS có **kiểm tra chứng chỉ/hostname hợp lệ**, không tắt TLS verification để tránh lỗi cấu hình.

Trước khi thao tác, cần tồn tại **dc=example,dc=org**, **ou=people** và **ou=groups**, ví dụ cấu trúc nhánh nhóm:

~~~ldif
dn: ou=groups,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: groups
~~~

LDIF này chỉ thêm nhánh **ou=groups** nếu nó chưa có. Việc khởi tạo base/suffix và **ou=people** tùy hệ thống LDAP cụ thể; không nhập trùng các entry đã có.

## 6. Thao tác nhóm bằng LdapTemplate

**LdapTemplate** là cách trực tiếp để biểu diễn cả hai loại nhóm khi thao tác với thuộc tính LDAP đa giá trị. Đoạn mã dưới đây dùng Java 17+, **LdapTemplate**, **LdapNameBuilder** và **LdapQueryBuilder**.

Để minh họa hai object class trong cùng một service, ta dùng enum ánh xạ **kiểu nhóm ↔ objectClass ↔ thuộc tính thành viên**:

~~~java
package org.example.directory;

import java.util.ArrayList;
import java.util.List;
import javax.naming.Name;
import javax.naming.NamingEnumeration;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Service
public class GroupDirectoryService {
    private static final String LDAP_BASE = "dc=example,dc=org";
    private static final String GROUPS_BASE = "ou=groups";

    public enum GroupType {
        NAMES("groupOfNames", "member"),
        UNIQUE_NAMES("groupOfUniqueNames", "uniqueMember");

        private final String objectClass;
        private final String memberAttribute;

        GroupType(String objectClass, String memberAttribute) {
            this.objectClass = objectClass;
            this.memberAttribute = memberAttribute;
        }
    }

    private final LdapTemplate ldapTemplate;

    public GroupDirectoryService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    // Tạo nhóm, có thành viên khởi tạo để thỏa mãn MUST.
    public void createGroup(String cn, String firstUid, GroupType type) {
        Name dn = groupDn(cn);
        String memberDn = fullUserDn(firstUid);

        Attributes attributes = new BasicAttributes(true);
        BasicAttribute classes = new BasicAttribute("objectClass");
        classes.add("top");
        classes.add(type.objectClass);
        attributes.put(classes);
        attributes.put("cn", cn);
        attributes.put(type.memberAttribute, memberDn);

        ldapTemplate.bind(dn, null, attributes);
    }

    // Thêm một DN thành viên vào thuộc tính đa giá trị.
    public void addMember(String cn, String uid, GroupType type) {
        ldapTemplate.modifyAttributes(
                groupDn(cn),
                new ModificationItem[] {
                    new ModificationItem(
                        DirContext.ADD_ATTRIBUTE,
                        new BasicAttribute(
                            type.memberAttribute, fullUserDn(uid)))
                }
        );
    }

    // Xóa một giá trị thành viên, không xóa cả thuộc tính.
    public void removeMember(String cn, String uid, GroupType type) {
        ldapTemplate.modifyAttributes(
                groupDn(cn),
                new ModificationItem[] {
                    new ModificationItem(
                        DirContext.REMOVE_ATTRIBUTE,
                        new BasicAttribute(
                            type.memberAttribute, fullUserDn(uid)))
                }
        );
    }

    // Đọc toàn bộ DN thành viên; giữ nguyên các giá trị được lưu.
    public List<String> listMemberDns(String cn, GroupType type) {
        return ldapTemplate.lookup(
            groupDn(cn),
            (AttributesMapper<List<String>>) attributes -> {
                Attribute members = attributes.get(type.memberAttribute);
                List<String> result = new ArrayList<>();
                if (members == null) {
                    return result;
                }
                NamingEnumeration<?> values = members.getAll();
                try {
                    while (values.hasMore()) {
                        result.add((String) values.next());
                    }
                } finally {
                    values.close();
                }
                return result;
            }
        );
    }

    // Tìm các nhóm chứa một DN người dùng, chỉ xét thành viên trực tiếp.
    public List<String> findDirectGroupNames(String uid, GroupType type) {
        String memberDn = fullUserDn(uid);
        return ldapTemplate.search(
                query().base(GROUPS_BASE)
                    .where("objectClass").is(type.objectClass)
                    .and(type.memberAttribute).is(memberDn),
                (AttributesMapper<String>) attrs ->
                    (String) attrs.get("cn").get()
        );
    }

    // Xóa hẳn entry nhóm; chỉ thực hiện theo chính sách ứng dụng.
    public void deleteGroup(String cn) {
        ldapTemplate.unbind(groupDn(cn));
    }

    private static Name groupDn(String cn) {
        validateId(cn, "cn");
        return LdapNameBuilder.newInstance(GROUPS_BASE)
                .add("cn", cn).build();
    }

    private static String fullUserDn(String uid) {
        validateId(uid, "uid");
        return LdapNameBuilder.newInstance(LDAP_BASE)
                .add("ou", "people")
                .add("uid", uid)
                .build().toString();
    }

    private static void validateId(String id, String name) {
        if (id == null || !id.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException(name + " không hợp lệ");
        }
    }
}
~~~

Trong ví dụ, **groupDn** tạo DN *tương đối* với base đã cấu hình, còn **fullUserDn** trả về DN *đầy đủ* được ghi trong member/uniqueMember. Các quy tắc validation giới hạn **cn/uid** để minh họa; dự án thực tế có thể hỗ trợ tên Unicode hoặc ký tự khác, nhưng vẫn phải tạo DN bằng API có escaping đúng.

### 6.1. Tạo nhóm

~~~java
groupService.createGroup(
    "backend",
    "an",
    GroupDirectoryService.GroupType.NAMES
);

groupService.createGroup(
    "approvers",
    "chi",
    GroupDirectoryService.GroupType.UNIQUE_NAMES
);
~~~

Lệnh đầu tạo **groupOfNames** với thuộc tính **member** ban đầu; lệnh sau tạo **groupOfUniqueNames** với **uniqueMember** ban đầu. Giả định **an** và **chi** đã tồn tại. Code chủ động sử dụng DN từ uid, nhưng **chưa tự kiểm tra sự tồn tại của người dùng**, vì tính toàn vẹn tham chiếu là chính sách tùy directory.

Nếu tạo nhóm có **cn** trùng DN đã tồn tại, **bind** sẽ gặp lỗi xung đột entry. Lỗi này không phải tín hiệu để ghi đè nhóm cũ. Ứng dụng cần kiểm tra quyền tạo nhóm và xử lý trường hợp đồng thời nhiều tác vụ cùng tạo một DN.

### 6.2. Thêm thành viên bằng ADD_ATTRIBUTE

~~~java
groupService.addMember(
    "backend", "binh",
    GroupDirectoryService.GroupType.NAMES
);
~~~

**DirContext.ADD_ATTRIBUTE** thêm một giá trị **member** vào thuộc tính đa giá trị. Đây là cách thay đổi một thành viên mà không ghi đè toàn bộ danh sách. Server có thể từ chối nếu giá trị đó đã có theo matching rule hoặc tài khoản không đủ quyền.

Không nên cập nhật membership bằng **REPLACE_ATTRIBUTE** với danh sách vừa đọc từ trước nếu chỉ muốn thêm một thành viên: giữa lúc đọc và lúc ghi, client khác có thể đã thêm người; ghi đè sẽ làm mất thay đổi của họ.

### 6.3. Xóa thành viên bằng REMOVE_ATTRIBUTE

~~~java
groupService.removeMember(
    "backend", "binh",
    GroupDirectoryService.GroupType.NAMES
);
~~~

**DirContext.REMOVE_ATTRIBUTE** kèm giá trị cụ thể sẽ yêu cầu xóa **đúng giá trị DN đó**. Nếu thuộc tính chứa nhiều DN, các giá trị còn lại vẫn được giữ. Đừng dùng một **BasicAttribute("member")** không kèm giá trị nếu mục đích chỉ là xóa một thành viên; yêu cầu đó có thể được hiểu là xóa toàn bộ thuộc tính.

Nếu Binh là thành viên cuối cùng, nhóm groupOfNames sẽ thiếu **member** sau thay đổi; server thường từ chối theo ràng buộc MUST. Ứng dụng nên hiển thị thông báo rõ ràng và xử lý quy trình “xóa thành viên cuối” theo chính sách đã chọn.

### 6.4. Đọc thành viên và tìm nhóm

~~~java
List<String> members = groupService.listMemberDns(
    "backend", GroupDirectoryService.GroupType.NAMES);

List<String> groups = groupService.findDirectGroupNames(
    "an", GroupDirectoryService.GroupType.NAMES);
~~~

Phương thức đọc trả về **danh sách các DN đã lưu**, không biến chúng thành user object. Nếu giao diện cần tên hoặc email, cần **lookup/search** các entry người dùng tương ứng. Việc lookup có thể thất bại nếu DN tham chiếu đã bị xóa hoặc ACL chặn đọc.

Phương thức tìm nhóm sử dụng **LdapQueryBuilder** để tạo điều kiện tương đương:

~~~ldap
(&(objectClass=groupOfNames)(member=uid=an,ou=people,dc=example,dc=org))
~~~

LdapQueryBuilder chịu trách nhiệm escape cú pháp filter khi chuyển giá trị DN thành điều kiện tìm kiếm. Chuỗi trên mô tả logic truy vấn; biểu diễn chuỗi thực tế sau escaping có thể khác. Kết quả là **nhóm chứa DN được chỉ định trực tiếp**, không bao gồm mọi nhóm lồng nhau.

Với **groupOfUniqueNames**, thay điều kiện thành **objectClass=groupOfUniqueNames** và **uniqueMember=DN**. Nếu một giá trị uniqueMember thực sự sử dụng optional UID, cần kiểm chứng matching rule và cách tìm kiếm theo DN tại server; đừng tự diễn giải chuỗi phức hợp này bằng phép so sánh text tùy tiện.

## 7. Ánh xạ nhóm bằng Spring Data LDAP repository

Trong trường hợp ứng dụng chủ yếu CRUD nhóm theo đối tượng Java, có thể dùng **Spring Data LDAP Object-Directory Mapping (ODM)**. Với groupOfNames:

~~~java
package org.example.directory;

import java.util.Set;
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=groups",
    objectClasses = {"top", "groupOfNames"}
)
public class GroupOfNamesEntry {
    @Id
    private Name dn;

    @Attribute(name = "cn")
    private String cn;

    @Attribute(name = "member")
    private Set<String> memberDns;

    public GroupOfNamesEntry() {}

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }
    public String getCn() { return cn; }
    public void setCn(String cn) { this.cn = cn; }
    public Set<String> getMemberDns() { return memberDns; }
    public void setMemberDns(Set<String> memberDns) {
        this.memberDns = memberDns;
    }
}
~~~

Repository tương ứng:

~~~java
package org.example.directory;

import org.springframework.data.ldap.repository.LdapRepository;

public interface GroupOfNamesRepository
        extends LdapRepository<GroupOfNamesEntry> {
}
~~~

**@Entry** mô tả objectClass sẽ ánh xạ, **@Id** là DN của entry và **@Attribute(name = "member")** ánh xạ thuộc tính đa giá trị sang tập các chuỗi DN. Trường **memberDns** cần chứa DN theo cú pháp LDAP hợp lệ; class Java không tạo schema mới và không tự bảo đảm tham chiếu tồn tại.

Để ánh xạ **groupOfUniqueNames**, nên dùng một entry class với **objectClasses = {"top", "groupOfUniqueNames"}** và **@Attribute(name = "uniqueMember")**. Nếu ứng dụng dùng phần UID tùy chọn của uniqueMember, cần cân nhắc mapper/chuyển đổi phù hợp thay vì giả định mọi giá trị chỉ là một DN thông thường.

Khi cần thêm/xóa một thành viên, **LdapTemplate.modifyAttributes** thường biểu đạt ý định rõ hơn so với việc đọc toàn bộ Set rồi save lại, nhất là khi nhiều tác vụ cùng thay đổi nhóm. Repository và LdapTemplate có thể dùng chung trong một ứng dụng; chọn cách theo ngữ nghĩa thao tác và yêu cầu nhất quán.

## 8. Lỗi thường gặp và giới hạn nghiệp vụ

| Tình huống | Dấu hiệu hoặc nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Tạo groupOfNames không member | **objectClassViolation (65)** do thiếu thuộc tính MUST | Tạo khi có thành viên thật hoặc chọn schema hỗ trợ nhóm rỗng |
| Tạo groupOfUniqueNames với member | Sai tên thuộc tính yêu cầu; thiếu **uniqueMember** | Dùng đúng class và thuộc tính tương ứng |
| Đưa cả hai class vào một entry | Hai STRUCTURAL class không cùng chuỗi kế thừa | Chọn một class nhóm làm cấu trúc cốt lõi |
| Thêm một DN đã có trong nhóm | Server có thể trả **attributeOrValueExists (20)** | Kiểm tra trạng thái sau lỗi; không tự ghi đè toàn bộ danh sách |
| Xóa thành viên cuối | Nhóm thiếu thuộc tính MUST | Thông báo hoặc áp dụng chính sách xóa nhóm |
| Tìm theo uid nhưng member chứa DN | Không khớp vì membership lưu DN | Dựng DN đầy đủ và tìm theo đúng member/uniqueMember |
| user DN bị đổi hoặc bị xóa | Tham chiếu có thể cũ, tùy khả năng referential integrity của server | Đối soát và cập nhật membership theo quy trình |
| Nhóm không hiển thị ở memberOf | Directory không hỗ trợ hoặc không trả về memberOf | Tìm trực tiếp trong nhánh nhóm |
| bind DN thiếu quyền | **insufficientAccessRights (50)** | Kiểm tra ACL và quyền cụ thể trên nhánh nhóm |
| LDAP server không truy cập được | Lỗi kết nối/TLS/xác thực | Kiểm tra chứng chỉ, timeout, credentials và trạng thái directory |

LDAP không tự cung cấp transaction đa entry kiểu JDBC cho các thao tác trên. Nếu ứng dụng đồng thời tạo người dùng, thêm vào nhóm và ghi database, một lỗi ở giữa có thể để lại trạng thái một phần. Thiết kế quy trình đối soát/bù trừ riêng nếu nghiệp vụ yêu cầu toàn bộ các bước cùng đạt trạng thái mong đợi.

### 8.1. Bảo mật khi quản lý membership

- **Không xây filter bằng phép nối chuỗi** từ dữ liệu người dùng; dùng **LdapQueryBuilder** hoặc **Filter** của Spring LDAP để escape giá trị. Dùng **LdapNameBuilder** hoặc **LdapName/Rdn** để xây DN.
- **Giới hạn nhánh thao tác**: tài khoản được phép sửa nhóm ở **ou=groups** theo chính sách; không cho client truyền DN tùy ý rồi modify mọi entry trong directory.
- **Đặt quyền theo nghiệp vụ**: thao tác thêm người dùng vào nhóm cấp quyền cao cần xác thực và kiểm tra ủy quyền rõ ràng ở ứng dụng. ACL LDAP cũng nên giới hạn tài khoản dịch vụ.
- **Bảo mật kết nối** bằng LDAPS/StartTLS, kiểm tra certificate chain/hostname và không lưu bind password trong mã nguồn.
- **Ghi audit có chọn lọc**: actor, DN nhóm, DN người được thêm/xóa, thời gian, kết quả; tránh log thông tin đăng nhập hoặc thuộc tính bí mật.
- **Kiểm tra dữ liệu đích** trước khi sửa: DN thành viên thực sự là người dùng hoặc nhóm được phép, tránh cấp quyền cho đối tượng sai loại.

Không nên mặc định rằng mọi nhóm directory đều là nhóm quyền của ứng dụng. Nhóm có thể dùng để gửi mail, tổ chức nhân sự hoặc quản lý tài nguyên. Quy tắc cấp quyền phải diễn giải rõ các nhóm nào có ý nghĩa bảo mật và thành viên trực tiếp/gián tiếp được xử lý ra sao.

## 9. Kiểm thử với LDAP directory

Nên thực hiện integration test trên OpenLDAP hoặc directory thử nghiệm có schema tương ứng, base **dc=example,dc=org**, các nhánh **ou=people**/**ou=groups** và người dùng kiểm thử An, Binh, Chi. Cần xác nhận server hỗ trợ cả hai class, ACL phù hợp và các DN có thể được thao tác trong vùng test. LDAP nhúng đơn giản có thể không phản ánh đầy đủ schema/ACL thực tế.

Một công cụ LDAP client có thể dùng để kiểm tra nhóm:

~~~bash
ldapsearch -LLL -x -H ldaps://ldap.example.org:636 \
  -D "uid=svc-app,ou=service-accounts,dc=example,dc=org" -W \
  -b "ou=groups,dc=example,dc=org" \
  "(objectClass=groupOfNames)" dn cn member
~~~

Đổi filter thành **(objectClass=groupOfUniqueNames)** và yêu cầu thuộc tính **uniqueMember** để kiểm tra mô hình kia. Trong test tự động, không dùng thư mục sản xuất, không đưa mật khẩu vào lệnh và không tắt xác minh TLS.

| Ca kiểm thử | Thao tác | Kết quả cần xác minh |
| --- | --- | --- |
| Tạo groupOfNames | Tạo backend có member An | Entry có cn, objectClass và member hợp lệ |
| Tạo groupOfUniqueNames | Tạo approvers có uniqueMember Chi | Entry có cn, objectClass và uniqueMember hợp lệ |
| Thêm thành viên | Thêm Binh vào backend | Có thêm đúng một giá trị member, giá trị An giữ nguyên |
| Xóa một thành viên | Xóa Binh khi backend còn An | Chỉ DN Binh bị loại khỏi member |
| Xóa thành viên cuối | Cố xóa An khỏi backend | Server từ chối nếu schema yêu cầu member |
| Tìm nhóm trực tiếp | Tìm groupOfNames chứa An | Trả về backend; không tự tính nhóm lồng nhau |
| Tham chiếu không tồn tại | Dùng DN của tài khoản chưa có | Quan sát quy tắc referential integrity thực tế và validation ứng dụng |
| DN có ký tự đặc biệt | Dùng tên và uid có ký tự đặc biệt trong môi trường hỗ trợ | Builder/filter escape đúng; không mở rộng điều kiện tìm kiếm |
| Thiếu quyền ghi | Dùng bind DN chỉ có quyền đọc | Modify bị từ chối, membership không đổi |
| Concurrent update | Hai client cùng thêm/xóa thành viên | Không ghi đè cả danh sách, xử lý xung đột/đối soát |
| Rename/delete user | Thay đổi DN của An | Kiểm chứng tham chiếu nhóm có tự cập nhật hay phải sửa thủ công |

Mỗi bài kiểm thử nên seed dữ liệu và cleanup độc lập. Với JUnit, dùng assertion rõ ràng để so sánh **DN thành viên thực tế**, không chỉ kiểm tra rằng phương thức service không ném exception. Đọc lại entry qua một kết nối/lookup độc lập sau thao tác sẽ giúp phân biệt lỗi mapping với thay đổi chưa thật sự xảy ra trên server.

## 10. Câu hỏi tự luyện

1. Vì sao tạo groupOfNames chỉ có **cn** nhưng không có **member** thường bị từ chối? Điều đó khác gì với một class nhóm cho phép nhóm rỗng?
2. Hãy mô tả sự khác nhau giữa **DN của entry nhóm** và **DN lưu trong giá trị member** khi Spring LDAP đã cấu hình base DN.
3. Khi nào nên dùng **ADD_ATTRIBUTE/REMOVE_ATTRIBUTE** thay vì ghi đè toàn bộ thuộc tính **member**?
4. **uniqueMember** có gì khác **member** về cú pháp? Phần optional UID có phải giá trị của thuộc tính **uid** hay không?
5. Nếu người dùng đổi DN hoặc bị xóa, bạn cần kiểm tra những thành phần nào trước khi kết luận quyền thành viên nhóm đã được cập nhật?
6. Vì sao một người thuộc nhóm backend không nhất thiết tự động thuộc nhóm engineering, dù engineering chứa DN của backend?
7. Nếu ứng dụng chỉ có quyền sửa nhánh ou=groups, có nên cho người dùng đầu cuối nhập DN tùy ý vào API thêm thành viên không? Hãy nêu cách ràng buộc đầu vào và quyền.

## 11. Tổng kết

**groupOfNames** và **groupOfUniqueNames** là hai **STRUCTURAL object class** phổ biến để lưu nhóm LDAP. groupOfNames dùng thuộc tính đa giá trị **member** chứa DN; groupOfUniqueNames dùng **uniqueMember** với cú pháp **Name And Optional UID**. Cả hai thường yêu cầu **cn** và ít nhất một giá trị thành viên theo schema chuẩn. **memberOf**, nhóm lồng nhau và việc tự sửa DN tham chiếu khi người dùng đổi tên phụ thuộc directory cũng như logic ứng dụng.

Trong **Spring Data LDAP**, dùng repository khi cần ánh xạ nhóm sang Java, và dùng **LdapTemplate** với **ModificationItem** khi muốn thêm/xóa chính xác một giá trị thành viên. Luôn kiểm tra schema, DN đầy đủ, quyền thao tác, bộ lọc an toàn, TLS và kiểm thử trên directory có cấu hình gần với môi trường đích.

### Tài liệu tham khảo

- [RFC 4519 — LDAP: Schema for User Applications](https://www.rfc-editor.org/rfc/rfc4519) — định nghĩa **groupOfNames**, **groupOfUniqueNames**, **member**, **uniqueMember**.
- [RFC 4517 — LDAP: Syntaxes and Matching Rules](https://www.rfc-editor.org/rfc/rfc4517) — cú pháp DN và **Name And Optional UID**.
- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512) — object class, schema và ràng buộc entry.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/) — LdapTemplate, DN, truy vấn và cập nhật thuộc tính.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/) — repository và ánh xạ entry với Object-Directory Mapping.
