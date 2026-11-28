# Đổi DN người dùng và xử lý các tham chiếu liên quan

## Mục tiêu bài thực hành

Trong **SPRING_DATA_LDAP**, ứng dụng Java truy cập directory bằng **Spring Data LDAP repository** và **LdapTemplate**. Mỗi entry có **DN** xác định vị trí trong cây, tuân theo **objectClass/schema** và có thể được entry khác tham chiếu bằng những thuộc tính như **member** hoặc **manager**.

Ở bài lab này, bạn sẽ chuyển người dùng **An** từ nhánh **ou=employees** sang **ou=alumni**, sau đó xác minh các nhóm đang tham chiếu An. Bạn sẽ chạy cùng một bài thực hành trong hai cấu hình directory: **có cơ chế referential integrity** và **không có cơ chế tự cập nhật**. Cuối cùng, bạn xây một bước sửa reference có điều kiện để xử lý trường hợp ứng dụng chịu trách nhiệm cập nhật.

Bài thực hành thuộc chương **Thực hành** và tập trung vào một quy trình end-to-end. Không giả định mọi LDAP server đều tự cập nhật mọi giá trị có hình thức giống DN; kết quả phải được kiểm tra trên đúng server và cấu hình đang chạy.

Sau khi hoàn thành, bạn có thể:

- Tìm DN thật của user theo thuộc tính **uid**, thay vì đoán DN từ username.
- Thực hiện **LDAP Modify DN** bằng **LdapTemplate.rename** với DN tương đối so với ContextSource base.
- Tìm các **groupOfNames.member** đang tham chiếu DN cũ.
- Phân biệt kết quả khi **OpenLDAP refint overlay** bật và khi overlay tắt.
- Sửa reference bằng một LDAP Modify có điều kiện khi ứng dụng chịu trách nhiệm cập nhật.
- Xác minh dữ liệu không tự cập nhật như **description**, database và cache.
- Viết integration test cho DN mới, DN cũ, group membership, retry và trạng thái chưa xác định.

## 1. Bài toán và tiêu chí hoàn thành

Directory test có người dùng An tại:

~~~text
uid=an,ou=employees,ou=people,dc=example,dc=org
~~~

Hai nhóm **backend** và **reviewers** đều có An trong thuộc tính **member**. Yêu cầu nghiệp vụ là chuyển An tới:

~~~text
uid=an,ou=alumni,ou=people,dc=example,dc=org
~~~

Sau thao tác, cần xác minh:

1. Entry An tồn tại ở **DN mới** và DN cũ không còn.
2. Mỗi group reference được cập nhật đúng theo khả năng server hoặc được ứng dụng sửa theo chính sách đã chọn.
3. Một thuộc tính văn bản chứa chuỗi giống DN không bị nhầm là DN reference.
4. Database/cache ngoài LDAP được đồng bộ riêng; không cho rằng LDAP server đã cập nhật chúng.
5. Không có bước nào thêm hoặc xóa membership ngoài ý muốn.

> **Quy tắc an toàn:** chạy trên LDAP directory test cô lập, dùng tài khoản test được cấp quyền, LDAPS/StartTLS xác minh chứng chỉ và dữ liệu giả. Không thực hành rename, sửa ACL hoặc xóa entry trên directory production.

## 2. Chuẩn bị môi trường

Ví dụ sử dụng Java 17+, Spring Boot 3.x và dependency tương thích được quản lý bởi Spring Boot:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-ldap")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Cấu hình ứng dụng:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap-test.example.org:636
    base: dc=example,dc=org
    username: uid=svc-directory,ou=service-accounts,dc=example,dc=org
    password: ${LDAP_BIND_PASSWORD}
~~~

JVM phải tin CA của LDAP test và hostname phải khớp certificate SAN. Nếu môi trường test dùng StartTLS, cần cấu hình nâng cấp kết nối và xác minh chứng chỉ đúng cách; chỉ đổi URL từ ldap sang ldaps hoặc ngược lại không thay thế việc kiểm tra TLS.

Tài khoản dịch vụ trong lab cần quyền:

- Đọc **ou=people** và **ou=groups**.
- Rename user từ **ou=employees** sang **ou=alumni**.
- Đọc thuộc tính **member** của các group test.
- Nếu chạy chế độ application-managed repair, được thêm/xóa giá trị **member** trên các group test.

Không cấp quyền ghi toàn bộ directory nếu chỉ cần thử hai OU và một số group.

### 2.1. Cấu trúc package gợi ý

~~~text
org.example.directory
├── DirectoryApplication.java
├── entry
│   └── PersonEntry.java
├── repository
│   └── PersonRepository.java
└── service
    ├── DirectoryIdentityResolver.java
    ├── DirectoryMoveService.java
    ├── GroupReferenceFinder.java
    └── GroupMemberRepairService.java
~~~

Trong lab này, **LdapTemplate** thực hiện Modify DN và reference repair. Repository minh họa việc tìm entry theo thuộc tính **uid**, đồng thời cho thấy **@Id** giữ DN chứ không phải username.

## 3. Tạo dữ liệu LDAP thử nghiệm

Nạp fixture sau vào directory test có schema phù hợp. Không nạp lại suffix hoặc OU nếu chúng đã tồn tại:

~~~ldif
dn: dc=example,dc=org
objectClass: top
objectClass: domain
dc: example

dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: ou=employees,ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: employees

dn: ou=alumni,ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: alumni

dn: ou=groups,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: groups

dn: uid=an,ou=employees,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Tran
sn: Tran
mail: an@example.org

dn: uid=binh,ou=employees,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: binh
cn: Binh Le
sn: Le
mail: binh@example.org

dn: cn=backend,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: backend
member: uid=an,ou=employees,ou=people,dc=example,dc=org
member: uid=binh,ou=employees,ou=people,dc=example,dc=org
description: Legacy text mentions uid=an,ou=employees,ou=people,dc=example,dc=org

dn: cn=reviewers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: reviewers
member: uid=an,ou=employees,ou=people,dc=example,dc=org
member: uid=binh,ou=employees,ou=people,dc=example,dc=org
~~~

Hai group đều có hai member để khi sửa một reference, **groupOfNames** vẫn còn ít nhất một giá trị **member**. Trường **description** chứa chuỗi nhìn giống DN nhưng có cú pháp **Directory String**; server không được kỳ vọng tự cập nhật nội dung này như một DN-valued attribute.

### 3.1. Kiểm tra dữ liệu trước khi chạy

Từ máy có **ldapsearch**, truy vấn người dùng:

~~~bash
ldapsearch -LLL -x -H ldaps://ldap-test.example.org:636 \
  -D "uid=svc-directory,ou=service-accounts,dc=example,dc=org" -W \
  -b "ou=employees,ou=people,dc=example,dc=org" -s sub \
  "(&(objectClass=inetOrgPerson)(uid=an))" dn uid cn
~~~

Truy vấn nhóm:

~~~bash
ldapsearch -LLL -x -H ldaps://ldap-test.example.org:636 \
  -D "uid=svc-directory,ou=service-accounts,dc=example,dc=org" -W \
  -b "ou=groups,dc=example,dc=org" -s sub \
  "(objectClass=groupOfNames)" dn cn member description
~~~

Baseline cần có đúng một entry An tại DN cũ, hai group chứa DN An và DN Binh, đồng thời **description** của backend còn chuỗi cũ. Nếu fixture đã chạy trước đó, reset bằng quy trình test được kiểm soát trước khi bắt đầu.

## 4. Ánh xạ entry và repository

Domain object:

~~~java
package org.example.directory.entry;

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

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String email;

    public PersonEntry() {}
    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }
    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }
    public String getCommonName() { return commonName; }
    public void setCommonName(String commonName) {
        this.commonName = commonName;
    }
    public String getSurname() { return surname; }
    public void setSurname(String surname) { this.surname = surname; }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
}
~~~

Repository:

~~~java
package org.example.directory.repository;

import java.util.List;
import org.example.directory.entry.PersonEntry;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<PersonEntry> {
    List<PersonEntry> findByUid(String uid);
}
~~~

**@Id Name dn** giữ DN thực tế của entry. **findByUid("an")** tìm theo thuộc tính **uid**, không giả định DN bắt đầu bằng **uid=an**. Fixture này dùng RDN uid, nhưng ứng dụng không nên dựa vào điều đó nếu directory có thể dùng RDN cn.

## 5. Bước 1 — Phân giải DN thật của người dùng

Tạo resolver dùng **search theo uid** và yêu cầu kết quả duy nhất:

~~~java
package org.example.directory.service;

import java.util.List;
import javax.naming.Name;

import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Service;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Service
public class DirectoryIdentityResolver {
    private final LdapTemplate ldapTemplate;

    public DirectoryIdentityResolver(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public Name findUniqueDnByUid(String uid) {
        if (uid == null || !uid.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("uid không hợp lệ");
        }

        List<Name> dns = ldapTemplate.search(
                query()
                    .base("ou=people")
                    .searchScope(SearchScope.SUBTREE)
                    .attributes("uid")
                    .countLimit(10)
                    .timeLimit(2000)
                    .where("objectClass").is("inetOrgPerson")
                    .and("uid").is(uid),
                (ContextMapper<Name>) context ->
                    ((DirContextOperations) context).getDn());

        if (dns.isEmpty()) {
            throw new IllegalArgumentException(
                    "Không tìm thấy user trong phạm vi được phép");
        }
        if (dns.size() != 1) {
            throw new IllegalStateException(
                    "uid không duy nhất trong search base");
        }
        return dns.get(0);
    }
}
~~~

**Vì sao phải tìm DN thật?** Tên đăng nhập và RDN không phải một. Nếu sau này An có DN **cn=An Tran,ou=employees,...** nhưng vẫn có **uid: an**, tự dựng **uid=an,...** sẽ sai. Resolver cũng từ chối khi có nhiều kết quả, thay vì chọn phần tử đầu tiên.

**Giới hạn của ví dụ:** countLimit 10 và timeLimit 2.000 ms là ngân sách lab, không chứng minh search đầy đủ khi server có giới hạn/referral. Trong production, nếu search bị cắt hoặc partial result, phải phân loại lỗi và không kết luận username duy nhất.

## 6. Bước 2 — Tạo thao tác chuyển OU bằng LdapTemplate

Với fixture đã thống nhất user dùng RDN uid, tạo service:

~~~java
package org.example.directory.service;

import javax.naming.Name;
import javax.naming.ldap.LdapName;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class DirectoryMoveService {
    private final DirectoryIdentityResolver resolver;
    private final LdapTemplate ldapTemplate;

    public DirectoryMoveService(
            DirectoryIdentityResolver resolver,
            LdapTemplate ldapTemplate) {
        this.resolver = resolver;
        this.ldapTemplate = ldapTemplate;
    }

    public MoveResult moveEmployeeToAlumni(String uid) {
        Name oldDn = resolver.findUniqueDnByUid(uid);

        Name expectedOldDn = LdapNameBuilder
                .newInstance("ou=employees,ou=people")
                .add("uid", uid)
                .build();

        if (!new LdapName(oldDn.toString()).equals(
                new LdapName(expectedOldDn.toString()))) {
            throw new IllegalStateException(
                    "User không nằm ở nhánh employees theo naming policy");
        }

        Name newDn = LdapNameBuilder
                .newInstance("ou=alumni,ou=people")
                .add("uid", uid)
                .build();

        if (entryExists(newDn)) {
            throw new IllegalStateException(
                    "DN đích đã tồn tại; cần xử lý conflict");
        }

        ldapTemplate.rename(oldDn, newDn);
        return new MoveResult(oldDn, newDn);
    }

    private boolean entryExists(Name dn) {
        try {
            ldapTemplate.lookup(
                    dn,
                    (AttributesMapper<String>) attrs ->
                            attrs.get("uid") == null
                                    ? null
                                    : attrs.get("uid").get().toString());
            return true;
        } catch (org.springframework.ldap.NameNotFoundException ex) {
            return false;
        }
    }

    public record MoveResult(Name oldDn, Name newDn) {}
}
~~~

Hai DN truyền cho **rename** là DN tương đối với ContextSource base **dc=example,dc=org**. DN đầy đủ dùng trong thuộc tính **member** sẽ có thêm suffix. **LdapNameBuilder** xử lý cú pháp DN/escaping; nó không xác nhận entry tồn tại hoặc caller có quyền move.

**Kiểm tra DN đích trước rename chỉ là preflight.** Client khác vẫn có thể tạo DN đích giữa lúc kiểm tra và lúc server thực hiện rename. Server phải kiểm tra uniqueness; nếu có xung đột, xử lý lỗi và không ghi đè.

Nếu uid không phải RDN hoặc user có thể nằm trong nhánh khác, không dùng phép dựng newDn này. Hãy lấy RDN thực tế từ DN đã phân giải và chỉ cho phép parent đích nằm trong allowlist nghiệp vụ.

### 6.1. Chạy bước move

Từ service/controller nội bộ đã được phân quyền:

~~~java
DirectoryMoveService.MoveResult result =
        directoryMoveService.moveEmployeeToAlumni("an");

System.out.println("Old DN: " + result.oldDn());
System.out.println("New DN: " + result.newDn());
~~~

DN tương đối mong đợi:

~~~text
Old: uid=an,ou=employees,ou=people
New: uid=an,ou=alumni,ou=people
~~~

Không đưa thao tác này thành API công khai cho caller tùy ý chọn OU. Move có thể làm thay đổi policy, scope tìm kiếm và quyền được cấp qua nhóm.

## 7. Bước 3 — Tìm các group đang tham chiếu DN cũ

Tạo service tìm group theo giá trị **member**:

~~~java
package org.example.directory.service;

import java.util.List;
import javax.naming.Name;

import org.springframework.ldap.core.ContextMapper;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.SearchScope;
import org.springframework.stereotype.Service;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

@Service
public class GroupReferenceFinder {
    private final LdapTemplate ldapTemplate;

    public GroupReferenceFinder(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<Name> findGroupsByMemberDn(String fullMemberDn) {
        return ldapTemplate.search(
                query()
                    .base("ou=groups")
                    .searchScope(SearchScope.SUBTREE)
                    .attributes("cn")
                    .countLimit(500)
                    .timeLimit(2000)
                    .where("objectClass").is("groupOfNames")
                    .and("member").is(fullMemberDn),
                (ContextMapper<Name>) context ->
                    ((DirContextOperations) context).getDn());
    }
}
~~~

Tính DN đầy đủ của An trước và sau:

~~~java
Name oldFullDn = LdapNameBuilder
        .newInstance("dc=example,dc=org")
        .add("ou", "people")
        .add("ou", "employees")
        .add("uid", "an")
        .build();

Name newFullDn = LdapNameBuilder
        .newInstance("dc=example,dc=org")
        .add("ou", "people")
        .add("ou", "alumni")
        .add("uid", "an")
        .build();

List<Name> oldReferences =
        groupReferenceFinder.findGroupsByMemberDn(oldFullDn.toString());
List<Name> newReferences =
        groupReferenceFinder.findGroupsByMemberDn(newFullDn.toString());
~~~

Với fixture ban đầu, **oldReferences** phải có backend và reviewers, còn **newReferences** rỗng.

**member** chứa DN đầy đủ; **groupDn** mà ContextMapper trả về là DN tương đối theo base của ContextSource. Không cắt suffix khỏi giá trị member hoặc nối suffix lần nữa vào DN trả về từ mapper.

## 8. Bước 4 — Chạy hai chế độ server và so sánh kết quả

Đây là phần trọng tâm của bài lab. Reset fixture về baseline trước mỗi lượt.

### Chế độ A: server có referential integrity

Với OpenLDAP, quản trị viên test có thể cấu hình **slapo-refint** cho các thuộc tính DN cần theo dõi, ví dụ:

~~~text
overlay refint
refint_attributes member manager owner seeAlso
~~~

Đây là ví dụ cấu hình server-side, không đặt trong application.yml. Overlay phải được cài đặt/bật đúng backend và phiên bản. Chỉ khai báo thuộc tính có cú pháp DN phù hợp. **uniqueMember** có cú pháp Name And Optional UID; không thêm vào danh sách trên nếu chưa xác minh hỗ trợ cụ thể.

Chạy **moveEmployeeToAlumni("an")**, rồi tìm group theo DN cũ và DN mới.

| Kiểm tra | Kết quả kỳ vọng khi refint quản lý member |
| --- | --- |
| Entry tại old DN | Không còn |
| Entry tại new DN | Có đúng một entry An |
| Group chứa old DN | Không còn reference cũ trong phạm vi được quản lý |
| Group chứa new DN | Backend và reviewers vẫn có membership theo fixture |
| Description | Vẫn giữ chuỗi DN cũ vì đây là Directory String |

**Đừng chỉ nhìn response của rename.** Đọc lại member trên từng group. Nếu plugin cập nhật bất đồng bộ hoặc replication có độ trễ, dùng deadline hữu hạn và kiểm tra đúng endpoint; ghi nhận trạng thái chưa đồng bộ nếu hết thời gian.

### Chế độ B: server không có referential integrity

Tắt overlay/plugin trong một directory test riêng, reset fixture rồi chạy lại move.

Kết quả có thể:

| Kiểm tra | Kết quả có thể gặp |
| --- | --- |
| Entry tại old DN | Không còn |
| Entry tại new DN | Có |
| Backend.member | Vẫn chứa old DN |
| Reviewers.member | Vẫn chứa old DN |
| Backend.description | Vẫn chứa chuỗi DN cũ |

Đây là lúc ứng dụng phải quyết định ai sở hữu việc cập nhật tham chiếu. Nếu server không tự sửa member, workflow có thể gọi repair service ở bước tiếp theo. Description vẫn không nên tự động sửa vì chỉ là chuỗi văn bản, không phải một liên kết DN theo schema.

### 8.1. Không trộn hai cơ chế trong một lượt test

Nếu server đã tự sửa member, đừng tiếp tục chạy **REMOVE old DN + ADD new DN** một cách vô điều kiện. Lệnh remove có thể báo **noSuchAttribute (16)**, lệnh add có thể báo **attributeOrValueExists (20)**, hoặc có thể ghi đè thay đổi đồng thời.

Quy trình đúng:

1. Rename entry.
2. Đọc actual reference.
3. Nếu đã đúng, ghi nhận **SERVER_UPDATED** và không sửa lại.
4. Nếu reference còn stale và ứng dụng có trách nhiệm repair, thực hiện sửa có điều kiện.
5. Nếu dữ liệu mâu thuẫn/không đọc được, dừng tự động và yêu cầu reconciliation.

## 9. Bước 5 — Sửa group reference khi ứng dụng chịu trách nhiệm

Đối với OpenLDAP test không bật refint, tạo service sửa một group tại một thời điểm:

~~~java
package org.example.directory.service;

import java.util.ArrayList;
import java.util.List;
import javax.naming.Name;
import javax.naming.ldap.LdapName;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Service;

@Service
public class GroupMemberRepairService {
    private final LdapTemplate ldapTemplate;

    public GroupMemberRepairService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public enum RepairResult {
        ALREADY_UPDATED, REPAIRED, CONFLICT
    }

    public RepairResult replaceMemberIfStale(
            Name groupRelativeDn,
            Name oldFullDn,
            Name newFullDn) {

        DirContextOperations group =
                ldapTemplate.lookupContext(groupRelativeDn);
        String[] values = group.getStringAttributes("member");

        List<String> oldMatches = matchingValues(values, oldFullDn);
        List<String> newMatches = matchingValues(values, newFullDn);

        if (oldMatches.isEmpty() && !newMatches.isEmpty()) {
            return RepairResult.ALREADY_UPDATED;
        }
        if (oldMatches.size() != 1 || !newMatches.isEmpty()) {
            return RepairResult.CONFLICT;
        }

        // Thêm DN mới trước, sau đó gỡ DN cũ trong cùng Modify request.
        ModificationItem[] changes = {
            new ModificationItem(
                DirContext.ADD_ATTRIBUTE,
                new BasicAttribute("member", newFullDn.toString())),
            new ModificationItem(
                DirContext.REMOVE_ATTRIBUTE,
                new BasicAttribute("member", oldMatches.get(0)))
        };

        ldapTemplate.modifyAttributes(groupRelativeDn, changes);
        return RepairResult.REPAIRED;
    }

    private static List<String> matchingValues(
            String[] values, Name expected) {
        List<String> matches = new ArrayList<>();
        if (values == null) {
            return matches;
        }
        for (String value : values) {
            try {
                if (new LdapName(value).equals(
                        new LdapName(expected.toString()))) {
                    matches.add(value);
                }
            } catch (javax.naming.InvalidNameException ex) {
                throw new IllegalStateException(
                        "Group chứa member DN sai cú pháp", ex);
            }
        }
        return matches;
    }
}
~~~

Một LDAP Modify request chứa nhiều modification trên **cùng entry** được server xử lý như một operation; nó không tạo transaction atomic giữa nhiều group. Hàm trên cũng không giải quyết race giữa lúc đọc group và lúc modify. Nếu server hỗ trợ assertion/precondition control, cân nhắc dùng để bảo vệ expected state; nếu không, xử lý noSuchAttribute, attributeOrValueExists và timeout bằng cách đọc lại actual state.

### 9.1. Chạy repair trên từng group đã tìm được

~~~java
for (Name groupDn : oldReferences) {
    GroupMemberRepairService.RepairResult result =
            repairService.replaceMemberIfStale(
                    groupDn, oldFullDn, newFullDn);

    if (result == GroupMemberRepairService.RepairResult.CONFLICT) {
        // Không tiếp tục tự sửa mù; ghi trạng thái cần đối soát.
        throw new IllegalStateException(
                "Group reference thay đổi đồng thời: " + groupDn);
    }
}
~~~

Đoạn code là bước thực hành có thể phát triển tiếp. Trong workflow production, không ném exception rồi bỏ mất tiến độ các group đã sửa. Hãy lưu checkpoint theo từng group với operationId, status, attempt count và kết quả xác minh; sau crash có thể tiếp tục mà không làm lại mù.

## 10. Bước 6 — Xác minh tham chiếu ngoài phạm vi LDAP

Trong fixture, description của backend chứa chuỗi:

~~~text
Legacy text mentions uid=an,ou=employees,ou=people,dc=example,dc=org
~~~

Sau khi rename, giá trị này vẫn giữ DN cũ. Đây là hành vi đúng vì server chỉ có thể duy trì những thuộc tính được định nghĩa và cấu hình như reference. Nếu ứng dụng muốn sửa description, phải có quy tắc nghiệp vụ riêng; không tự thay tất cả chuỗi có dạng DN.

Nếu database có:

~~~text
account.ldap_dn = uid=an,ou=employees,ou=people,dc=example,dc=org
~~~

LDAP server không thể sửa bản ghi SQL đó. Tương tự, Redis, search index, session, message queue và policy trong ứng dụng ngoài cần được đồng bộ qua **outbox/event hoặc reconciliation**.

| Nơi lưu dữ liệu | Ai chịu trách nhiệm? | Việc cần xác minh |
| --- | --- | --- |
| Entry DN | LDAP server | Entry ở DN mới, DN cũ không còn |
| groupOfNames.member | Server refint hoặc ứng dụng theo cấu hình | Old DN không còn; new DN xuất hiện đúng nhóm |
| manager/seeAlso | Server nếu attribute được quản lý, nếu không là ứng dụng | Kiểm tra từng attribute riêng |
| uniqueMember | Tùy schema/plugin/server | Không suy từ kết quả của member |
| posixGroup.memberUid | Chính sách username/application | Đây là username, không phải DN |
| description chứa chuỗi DN | Chủ sở hữu dữ liệu text | Giữ nguyên trừ khi có quy tắc riêng |
| SQL/cache | Ứng dụng | Outbox/event, invalidate cache, reconciliation |
| Group authorization | IAM/ứng dụng | Move có cần giữ hay thu hồi quyền? |

**Bảo toàn tham chiếu không đồng nghĩa bảo toàn đúng quyền.** Nếu An chuyển sang alumni vì nghỉ việc, membership trong backend có thể được giữ, nhưng membership trong production-admins có thể phải thu hồi. Hãy phân biệt **tính toàn vẹn dữ liệu** với **chính sách cấp quyền**.

## 11. Workflow thực hành và trạng thái phục hồi

Nếu lab chỉ có một lần rename trên directory test, có thể chạy trực tiếp. Với quy trình thật gồm LDAP, database và cache, hãy ghi một journal bền vững.

State machine tối thiểu:

~~~text
PREPARED
  -> LDAP_RENAME_APPLYING
  -> LDAP_RENAME_APPLIED
  -> REFERENCES_RECONCILING
  -> EXTERNAL_SYNC_PENDING
  -> COMPLETED

Nếu mất response sau rename:
  LDAP_RENAME_APPLYING -> OUTCOME_UNKNOWN
  OUTCOME_UNKNOWN -> đọc oldDn/newDn và đối chiếu identity
  -> LDAP_RENAME_APPLIED hoặc NEEDS_RECONCILIATION

Nếu reference sửa lỗi:
  REFERENCES_RECONCILING -> NEEDS_RECONCILIATION
~~~

Các trường journal nên gồm **operationId**, **idempotencyKey**, **directoryAlias**, old/new DN được bảo vệ, danh sách group dự kiến, trạng thái LDAP, trạng thái external sync, version, lease và retry budget. Không ghi password hoặc toàn bộ LDAP entry vào log.

**Nếu CommunicationException xảy ra sau rename, không retry vô điều kiện.** Server có thể đã chuyển entry. Khi kết nối phục hồi, đọc cả old DN và new DN, đối chiếu ID server-managed nếu có và kiểm tra group reference. Nếu trạng thái không rõ, dừng tự động để reconciliation.

## 12. Kiểm thử tích hợp

### 12.1. Test xác minh entry đã chuyển

~~~java
package org.example.directory;

import javax.naming.Name;

import org.example.directory.service.DirectoryMoveService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class DirectoryMoveIntegrationTest {
    @Autowired DirectoryMoveService moveService;
    @Autowired LdapTemplate ldapTemplate;

    @Test
    void movesAnToAlumni() {
        // Fixture seed test-move ở employees và bảo đảm
        // test-move chưa tồn tại ở alumni.
        String uid = "test-move";
        Name oldDn = LdapNameBuilder
                .newInstance("ou=employees,ou=people")
                .add("uid", uid).build();
        Name newDn = LdapNameBuilder
                .newInstance("ou=alumni,ou=people")
                .add("uid", uid).build();

        moveService.moveEmployeeToAlumni(uid);

        String actualUid = ldapTemplate.lookup(
                newDn,
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("uid").get());
        assertEquals(uid, actualUid);

        assertThrows(
                org.springframework.ldap.NameNotFoundException.class,
                () -> ldapTemplate.lookup(
                        oldDn,
                        (AttributesMapper<String>) attrs ->
                                (String) attrs.get("uid").get()));
    }
}
~~~

Test cần LDAP server thật, fixture riêng, tài khoản có quyền rename và TLS hợp lệ. Nó xác minh **entry DN**, không chứng minh refint hoạt động.

### 12.2. Test kiểm tra reference theo cấu hình server

Thực hiện các bước:

1. Seed An và hai group chứa oldFullDn.
2. Assert oldReferences có backend và reviewers.
3. Move An bằng DirectoryMoveService.
4. Trong thời hạn hữu hạn, đọc lại oldReferences và newReferences.
5. Với profile **refint-enabled**, assert oldReferences rỗng và newReferences chứa backend/reviewers.
6. Với profile **refint-disabled**, assert oldReferences còn các group fixture, gọi GroupMemberRepairService cho từng group, rồi xác minh oldReferences rỗng và newReferences có đủ group.
7. Assert description vẫn chứa chuỗi DN cũ.
8. Assert Binh vẫn còn trong cả hai nhóm.
9. Assert không có entry nào ngoài fixture bị thay đổi.

Không hardcode một kỳ vọng cho mọi server. Profile test phải khai báo rõ refint-enabled hay application-repair và trỏ tới đúng directory. Nếu plugin bất đồng bộ hoặc replication trễ, dùng polling có deadline; khi hết deadline, báo trạng thái thực tế và endpoint đã đọc.

### 12.3. Ma trận test cần hoàn thành

| Ca kiểm thử | Điều kiện | Kết quả cần đạt |
| --- | --- | --- |
| Tìm An theo uid | Có đúng một entry | Lấy đúng DN cũ |
| Username trùng | Có hai entry trong search base | Resolver từ chối ambiguity |
| Move thành công | DN đích trống, đủ ACL | Entry ở DN mới |
| DN đích đã tồn tại | Preflight hoặc server phát hiện conflict | Không overwrite |
| Refint bật | Server quản lý member | Group trỏ tới DN mới |
| Refint tắt | Server không sửa member | Ứng dụng phát hiện stale reference |
| Repair idempotent | Có new DN, không còn old DN | Trả ALREADY_UPDATED |
| Repair conflict | Có cả old/new hoặc thiếu cả hai | Không tự sửa; reconciliation |
| Description text | Chứa chuỗi giống DN | Không tự cập nhật |
| Move OU cha | Có descendants | Kiểm tra DN child và references |
| Mất response sau rename | Fault injection trên test | OUTCOME_UNKNOWN, đọc lại trước retry |
| Concurrent membership update | Client khác sửa group trong lúc repair | Không làm mất giá trị mới |
| ACL thiếu quyền | Service account thiếu rename/modify | Lỗi được phân loại đúng |
| GroupOfNames còn một member | Xóa reference cuối | Schema/policy được xử lý rõ |
| Cache/SQL cũ | Có bản ghi old DN | Event/outbox cập nhật và có checkpoint |
| Offboarding | Move An sang alumni | Membership và quyền theo IAM policy |

## 13. Sản phẩm cần nộp và tiêu chí đánh giá

### 13.1. Nhiệm vụ

Hoàn thành các phần sau trong ứng dụng Spring Boot thử nghiệm:

1. Tạo fixture directory gồm An, Binh, hai group backend/reviewers và description chứa chuỗi DN cũ.
2. Viết **DirectoryIdentityResolver** tìm user theo uid và từ chối kết quả không duy nhất.
3. Viết **DirectoryMoveService** chuyển An từ employees sang alumni bằng **LdapTemplate.rename**.
4. Viết **GroupReferenceFinder** tìm group có member trỏ tới DN cũ.
5. Chạy bài lab với refint bật, ghi nhận group nào server tự sửa.
6. Chạy lại với refint tắt trong directory test riêng, triển khai **GroupMemberRepairService** có kiểm tra actual state.
7. Xác minh description, database/cache mô phỏng và membership của Binh không bị sửa nhầm.
8. Viết integration test và tài liệu hóa server/version/overlay/plugin/ACL đã dùng.

### 13.2. Sản phẩm bàn giao

- Mã Java của resolver, move service, reference finder và repair service.
- LDIF fixture cùng hướng dẫn reset test data.
- Bảng kết quả cho **refint-enabled** và **refint-disabled**.
- Log đã che PII cho operationId, DN old/new ở dạng bảo vệ, số group được kiểm tra và kết quả.
- Integration tests cho entry, group references, conflict và timeout/unknown outcome.
- Một runbook ngắn cho trường hợp rename thành công nhưng references vẫn còn DN cũ.

### 13.3. Tiêu chí đánh giá

| Tiêu chí | Điểm |
| --- | ---: |
| Tìm DN thực tế và xử lý username không duy nhất | 15 |
| Rename đúng DN tương đối và không overwrite entry đích | 15 |
| Phân biệt kết quả theo refint server | 20 |
| Repair member có điều kiện, không làm mất membership khác | 20 |
| Kiểm tra dữ liệu text/DB/cache ngoài LDAP | 10 |
| Integration tests và xử lý outcome unknown | 15 |
| Bảo mật TLS, ACL, DN/filter escaping và log | 5 |
| **Tổng** | **100** |

## 14. Lỗi thường gặp trong bài lab

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Ghép chuỗi để tạo DN | Ký tự đặc biệt có thể làm sai cấu trúc RDN | Dùng LdapNameBuilder/LdapName |
| Truyền full DN vào template đã có base | Có thể lặp suffix | Dùng DN tương đối cho lookup/rename |
| Dùng username thay full DN trong member | Sai cú pháp và không xác định entry | Lưu DN đầy đủ theo schema |
| Cho rằng rename tự sửa mọi attribute | Refint phụ thuộc server và attribute | Đọc lại từng loại reference |
| Tự sửa group ngay sau rename | Có thể ghi trùng với plugin/server | Quan sát actual state trước |
| Chọn group đầu tiên khi search | Có thể bỏ sót references | Xử lý đủ kết quả/paging/limit |
| Dùng description làm reference | Đây là text, không có semantics DN | Quản lý bằng quy tắc ứng dụng |
| Sửa mọi group trong transaction giả định | LDAP không có atomic transaction đa-entry mặc định | Journal/checkpoint từng group |
| Xóa member cũ trước khi thêm member mới | Có thể vi phạm groupOfNames MUST member | Trong một Modify request, thêm mới rồi gỡ cũ |
| Retry rename sau timeout | Lần đầu có thể đã thành công | Đọc old/new DN và đối soát trước |
| Coi move sang alumni là thu hồi quyền | Membership có thể được giữ đúng theo refint | Thực hiện offboarding/IAM policy riêng |
| Tắt TLS verification để test | Che giấu lỗi trust/hostname | Sửa truststore/certificate test |

## 15. Tổng kết và câu hỏi tự đánh giá

Qua bài lab, bạn đã thực hiện **đổi DN người dùng** bằng Spring LDAP và kiểm tra các entry khác đang tham chiếu DN đó. Bạn đã so sánh hai cấu hình: server tự cập nhật một số reference attributes và server không có cơ chế đó. Khi cần ứng dụng sửa, bạn dùng **search trước, so sánh trạng thái, modify có điều kiện và đọc lại**, thay vì sửa mù hoặc giả định một transaction bao trùm nhiều group.

Điều quan trọng nhất là xác định **ai sở hữu từng loại tham chiếu**. Directory server có thể duy trì member theo plugin/linked attribute; nó không tự sửa description, SQL, Redis, session hoặc một LDAP server khác. Kết quả rename thành công cũng không tự chứng minh quyền của người dùng đã được cấp/thu hồi đúng theo nghiệp vụ.

**Câu hỏi tự đánh giá:**

1. Vì sao DirectoryIdentityResolver cần trả DN thật thay vì tự dựng từ uid?
2. Trong fixture, tại sao description giữ DN cũ sau rename mà không phải lỗi refint?
3. Khi server refint bật, tại sao application repair phải bỏ qua group đã được cập nhật?
4. Vì sao ADD newDn và REMOVE oldDn cần được xử lý có điều kiện?
5. Nếu group chỉ có An là member, điều gì xảy ra khi xóa reference và schema yêu cầu member?
6. Nếu CommunicationException xảy ra sau rename, bạn cần kiểm tra những gì trước khi retry?
7. Move An sang alumni nhưng giữ membership production-admins có thể gây rủi ro gì?
8. Những dữ liệu nào trong database/cache cần cập nhật riêng sau khi DN thay đổi?

### Tài liệu tham khảo

- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511) — Modify DN và Modify operations.
- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512) — DN, entry, attribute syntax và objectClass.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/) — LdapTemplate, LdapNameBuilder, query builder và LDAP operations.
- [Spring LDAP — LdapTemplate Javadoc](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html) — rename, search, lookup và modifyAttributes.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/) — ODM @Entry, @Id, @Attribute và repository.
- [OpenLDAP Administrator's Guide — Referential Integrity](https://www.openldap.org/doc/admin26/guide.html) — cấu hình và phạm vi refint overlay.
- [OpenLDAP slapo-refint(5)](https://man7.org/linux/man-pages/man5/slapo-refint.5.html) — refint_attributes, placeholder và giới hạn overlay.
- [Microsoft Learn — Group Objects](https://learn.microsoft.com/en-us/windows/win32/ad/group-objects) — linked membership attributes trong Active Directory.
