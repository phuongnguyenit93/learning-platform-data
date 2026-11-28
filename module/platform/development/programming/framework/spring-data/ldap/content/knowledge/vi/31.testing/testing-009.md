# Kiểm thử cập nhật, đổi DN, xóa và phục hồi khi lỗi

## 1. Vì sao CRUD LDAP cần kiểm thử theo ngữ nghĩa directory?

Trong **Spring Data LDAP**, repository và `LdapTemplate` giúp ứng dụng ánh xạ entry LDAP thành object Java và thực hiện create, update, rename hoặc delete. Nhưng directory có những quy tắc khác với cơ sở dữ liệu quan hệ: entry nằm trong cây DN, schema quyết định `objectClass` và attribute hợp lệ, một số quan hệ được lưu dưới dạng DN trong attribute, và server không mặc định cung cấp transaction ACID cho nhiều entry.

Một unit test chỉ xác minh service gọi `ldapTemplate.update()` hoặc `repository.deleteById()` chưa chứng minh dữ liệu directory thay đổi đúng. Cần kiểm thử với LDAP server thật hoặc một test directory có schema và hành vi gần với môi trường triển khai.

Ví dụ một quy trình đổi username của Alice có thể gồm:

~~~text
1. Đọc uid=alice,ou=people,...
2. Đổi mail và thuộc tính uid
3. Di chuyển entry sang uid=alice.nguyen,ou=people,...
4. Cập nhật group references
5. Ghi operation hoàn tất
~~~

Nếu bước 3 thành công trên LDAP server nhưng client mất kết nối trước khi nhận response, ứng dụng không biết rename đã được áp dụng hay chưa. Nếu bước 4 thất bại, directory có thể đã đổi DN nhưng một số group vẫn trỏ tới DN cũ. Một test chỉ kiểm tra exception được ném ra sẽ bỏ qua trạng thái dữ liệu thực tế.

Bài học này xây dựng chiến lược kiểm thử cho ba nhóm thao tác:

- **Update:** thay đổi attribute, giữ nguyên những attribute ngoài phạm vi.
- **Rename/move:** đổi RDN hoặc parent bằng LDAP ModifyDN, xác minh DN cũ/mới và các reference.
- **Delete:** xóa đúng entry, xử lý child entries và quan hệ tham chiếu.
- **Recovery:** mô phỏng lỗi trước/sau khi server áp dụng thao tác, đọc lại trạng thái và tiếp tục hoặc bù trừ an toàn.

Sau bài này, người học có thể:

1. Tạo fixture LDAP cô lập cho mỗi test.
2. Kiểm thử update và xác minh attribute không liên quan được bảo toàn.
3. Kiểm thử rename bằng `LdapTemplate.rename` và xác minh DN cũ không còn.
4. Kiểm tra hành vi reference theo đúng LDAP vendor.
5. Kiểm thử delete với entry có child hoặc reference.
6. Mô phỏng lỗi một phần và kết quả ghi không xác định.
7. Thiết kế operation journal, reconciliation và compensation.
8. Kiểm thử retry idempotent, phục hồi sau restart và cạnh tranh đồng thời.

> **Nguyên tắc:** Kiểm thử cả trạng thái directory sau thao tác và trạng thái ứng dụng sau khi xử lý lỗi. Với LDAP, một exception không chứng minh thao tác chưa được áp dụng.

## 2. Phân biệt các loại kiểm thử

Một bộ kiểm thử tốt kết hợp unit test, integration test và fault-injection test.

| Loại test | Thành phần kiểm tra | Ví dụ |
| --- | --- | --- |
| Unit test | Logic nghiệp vụ và phân loại lỗi | Update service chọn đúng operation; lỗi timeout chuyển sang trạng thái cần reconcile |
| Adapter test | Mapping giữa domain và Spring LDAP | ODM tạo đúng DN, attribute và objectClass |
| Integration test | Ứng dụng giao tiếp với LDAP server | Update mail, rename DN, delete entry |
| Vendor compatibility test | Hành vi phụ thuộc directory | Referential integrity, schema, subtree delete, ACL |
| Fault-injection test | Lỗi tại ranh giới giữa client/server/store | Server đã rename nhưng response bị mất |
| Recovery test | Khôi phục từ operation journal | Restart worker và tiếp tục operation chưa hoàn tất |
| Concurrency test | Nhiều worker thay đổi cùng entry | Stale update không ghi đè trạng thái mới |

Unit test với mock rất hữu ích để xác minh nhánh logic, nhưng không thay thế integration test. Mock không biết LDAP server có từ chối `objectClass`, có cho rename subtree hay tự cập nhật DN reference hay không.

### 2.1. Chọn test directory phù hợp

Có thể dùng:

- LDAP server embedded trong test process nếu cần chạy nhanh.
- Testcontainers với đúng loại LDAP server được triển khai.
- LDAP server dùng chung trong môi trường CI riêng, có namespace/OU cô lập và dữ liệu được reset.

Nếu production dùng OpenLDAP, Active Directory hoặc một vendor directory khác, hãy có một nhóm integration test trên đúng loại server. Một embedded server khác vendor không thể chứng minh ACL, schema extension, referential integrity hoặc password policy giống production.

Không chạy test xóa, đổi DN hoặc fault injection trên directory production.

## 3. Tạo fixture LDAP có thể lặp lại

### 3.1. Cấu trúc dữ liệu kiểm thử

Một fixture nhỏ có thể gồm:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=alice
│   └── uid=bob
└── ou=groups
    └── cn=engineering
~~~

LDIF minh họa:

~~~ldif
dn: dc=example,dc=org
objectClass: top
objectClass: domain
dc: example

dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: ou=groups,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: groups

dn: uid=alice,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: alice
cn: Alice Nguyen
sn: Nguyen
mail: alice@example.org
employeeNumber: E-1001

dn: uid=bob,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: bob
cn: Bob Tran
sn: Tran
mail: bob@example.org
employeeNumber: E-1002

dn: cn=engineering,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: engineering
member: uid=alice,ou=people,dc=example,dc=org
member: uid=bob,ou=people,dc=example,dc=org
~~~

Fixture dùng `groupOfNames` nên cần ít nhất một giá trị `member` theo schema chuẩn. Nếu test xóa member cuối cùng, server có thể từ chối vì entry group sẽ không còn thỏa MUST attribute.

Nếu ứng dụng dùng `groupOfUniqueNames`, hãy dùng `uniqueMember` và DN value đúng schema. Không dùng lẫn `member` với `uniqueMember`.

### 3.2. Base DN và relative DN

Nếu `ContextSource.base` là `dc=example,dc=org`, code Spring LDAP thường làm việc với DN tương đối như:

~~~java
Name aliceDn = LdapNameBuilder.newInstance("ou=people")
    .add("uid", "alice")
    .build();
~~~

DN đầy đủ trên directory là:

~~~text
uid=alice,ou=people,dc=example,dc=org
~~~

Cần thống nhất test dùng relative DN hay full DN. Tránh nối suffix base DN hai lần. Dùng `LdapNameBuilder` hoặc `LdapName`, không tự tách DN bằng dấu phẩy vì giá trị RDN có thể chứa ký tự được escape.

### 3.3. Cô lập dữ liệu giữa các test

Có hai chiến lược phổ biến:

**Reset directory cho mỗi test class**

- Nạp LDIF ban đầu.
- Chạy test tuần tự.
- Xóa và nạp lại fixture sau mỗi test hoặc mỗi class.

Cách này đơn giản, nhưng không phù hợp nếu test chạy song song trên cùng directory.

**Tạo namespace riêng cho mỗi test**

- Tạo OU có suffix ngẫu nhiên hoặc test ID.
- Tạo users/groups bên dưới OU đó.
- Chạy test trong subtree riêng.
- Xóa subtree trong teardown theo thứ tự leaf trước parent.

Cách này hỗ trợ chạy song song tốt hơn. Tuy nhiên, schema và ACL ở parent vẫn được dùng chung, vì vậy không được thay đổi cấu hình server toàn cục trong từng test song song.

Không dùng UID cố định như `alice` trên một LDAP server dùng chung nếu nhiều test suite có thể chạy cùng lúc.

## 4. Cấu hình integration test

### 4.1. Khởi tạo ứng dụng với test directory

Có thể dùng `@SpringBootTest` để kiểm tra wiring thật của `LdapTemplate`, ODM và repository:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("ldap-test")
class DirectoryCrudIntegrationTest {
    // Inject LdapTemplate, repository và service.
}
~~~

Profile `ldap-test` cần trỏ tới một LDAP server dùng riêng cho test. Endpoint và credential nên đến từ test fixture/container hoặc CI secret; không dùng credential production.

Với Testcontainers, hãy khởi động LDAP container trước khi Spring tạo `ContextSource`, rồi truyền mapped host/port vào test properties. Cấu hình image, bootstrap LDIF, TLS và schema phụ thuộc image/server được chọn; kiểm thử phải đợi LDAP server sẵn sàng trước khi nạp fixture.

Không chỉ kiểm tra container đã mở port. Hãy thực hiện một bind hoặc Search health check để xác nhận directory đã nạp schema và bootstrap entries.

### 4.2. Fixture helper

Một helper test có thể cung cấp các thao tác:

~~~java
interface DirectoryFixture {
    void reset();
    void loadPeopleAndGroups();
    void createPerson(String uid, String cn, String sn, String mail);
    boolean exists(Name dn);
    PersonSnapshot readPerson(Name dn);
    void removeTestSubtree();
}
~~~

Đây là abstraction của test suite. Phần triển khai dùng LDIF loader hoặc `LdapTemplate` để chuẩn bị dữ liệu. Test nên gọi helper để mô tả ý định, không lặp lại nhiều đoạn bootstrap LDAP ở mọi method.

### 4.3. Entity ODM minh họa

~~~java
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.DnAttribute;
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
    @DnAttribute("uid")
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

Entity phải khớp objectClass và schema trên test server. Nếu entity dùng `@DnAttribute`, nhớ kiểm tra field RDN có được ODM ánh xạ thành LDAP attribute theo cấu hình annotation hay không. Fixture cần chứa đủ MUST attributes như `cn` và `sn` của `inetOrgPerson`.

## 5. Kiểm thử update attribute

### 5.1. Xác minh đúng attribute được thay đổi

Một test update không nên chỉ assert method trả về thành công. Hãy đọc lại entry từ LDAP server và kiểm tra:

- Attribute được yêu cầu thay đổi có giá trị mới.
- DN không đổi nếu nghiệp vụ chỉ sửa attribute.
- Các attribute ngoài phạm vi vẫn giữ nguyên.
- Không phát sinh attribute ngoài dự kiến.
- Entry vẫn có objectClass hợp lệ.

Ví dụ service:

~~~java
public PersonEntry updateEmail(Name dn, String newEmail) {
    PersonEntry person =
        ldapTemplate.findByDn(dn, PersonEntry.class);

    person.setEmail(newEmail);
    ldapTemplate.update(person);

    return ldapTemplate.findByDn(dn, PersonEntry.class);
}
~~~

Integration test:

~~~java
@Test
void updateEmailChangesOnlyRequestedValue() {
    Name dn = personDn("alice");

    PersonEntry before =
        ldapTemplate.findByDn(dn, PersonEntry.class);

    PersonEntry updated =
        personService.updateEmail(dn, "alice.new@example.org");

    assertThat(updated.getEmail())
        .isEqualTo("alice.new@example.org");
    assertThat(updated.getUid()).isEqualTo(before.getUid());
    assertThat(updated.getCommonName())
        .isEqualTo(before.getCommonName());
    assertThat(updated.getSurname()).isEqualTo(before.getSurname());
    assertThat(updated.getDn()).isEqualTo(before.getDn());
}
~~~

Test đọc lại từ directory sau update. Không chỉ assert object trong RAM vì object có thể chứa giá trị mới trong khi LDAP Modify thất bại.

### 5.2. Kiểm tra attribute đa trị

Với `member` hoặc `uniqueMember`, test cần xác minh semantics add/remove:

1. Đọc group hiện tại.
2. Thêm một DN member.
3. Update.
4. Đọc lại group và xác minh member mới xuất hiện.
5. Xóa một member.
6. Update và xác minh member đó không còn.
7. Kiểm tra schema vẫn hợp lệ.

Không so sánh chuỗi DN bằng `split(",")`. Dùng `Name`/`LdapName` để so sánh cấu trúc DN.

### 5.3. Kiểm thử null và empty semantics

Một field Java có thể ở trạng thái:

- `null`: không có giá trị trong object.
- Chuỗi rỗng: `""`.
- Collection rỗng: không có phần tử.
- Collection có giá trị.

Không mặc định các trạng thái này có cùng nghĩa khi ODM update. Tùy mapper và cách server lưu attribute, giá trị null/rỗng có thể dẫn tới xóa attribute, bỏ qua field hoặc lỗi syntax.

Hãy viết test rõ ràng cho từng hành vi mà service hỗ trợ. Nếu chỉ muốn thay một attribute cụ thể, cân nhắc `modifyAttributes` với `ModificationItem` thay vì dùng một object sparse như PATCH khi chưa định nghĩa semantics.

### 5.4. Kiểm thử lỗi schema và ACL

Tạo test riêng cho:

- Thiếu MUST attribute.
- Attribute không có trong schema.
- Giá trị sai syntax.
- Bind identity không có quyền Modify.
- Entry bị xóa hoặc đổi DN trước khi update.
- Server trả lỗi khi update một giá trị đa trị.

Kỳ vọng là service trả lỗi đã chuẩn hóa, không báo thành công giả và không thay đổi các attribute ngoài phạm vi.

## 6. Kiểm thử rename và move DN

### 6.1. Rename phải được kiểm tra bằng DN cũ và DN mới

Khi cần LDAP server thực hiện ModifyDN, gọi `LdapTemplate.rename(oldDn, newDn)`:

~~~java
public void renamePerson(Name oldDn, Name newDn) {
    ldapTemplate.rename(oldDn, newDn);
}
~~~

Test:

~~~java
@Test
void renameChangesEntryDn() {
    Name oldDn = personDn("alice");
    Name newDn = personDn("alice.nguyen");

    personService.renamePerson(oldDn, newDn);

    assertThat(directoryFixture.exists(oldDn)).isFalse();
    assertThat(directoryFixture.exists(newDn)).isTrue();

    PersonEntry moved =
        ldapTemplate.findByDn(newDn, PersonEntry.class);

    assertThat(moved.getUid()).isEqualTo("alice.nguyen");
    assertThat(moved.getCommonName()).isEqualTo("Alice Nguyen");
    assertThat(moved.getEmail()).isEqualTo("alice@example.org");
}
~~~

Test cần xác minh entry tại DN mới vẫn giữ các attribute không thuộc RDN. Nếu `uid` là RDN attribute, giá trị attribute sau rename phụ thuộc semantics của ModifyDN và lựa chọn `deleteOldRdn`; hãy xác minh giá trị mong đợi bằng test trên đúng server.

### 6.2. DN mới phải hợp lệ và không bị chiếm

Các trường hợp cần kiểm thử:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| DN mới chưa tồn tại | Rename thành công nếu ACL/schema hợp lệ |
| DN mới đã tồn tại | Server từ chối; entry cũ vẫn còn |
| Parent DN mới không tồn tại | Server từ chối |
| RDN mới vi phạm schema/naming rule | Server từ chối |
| Caller không có quyền ModifyDN | Access denied |
| Entry cũ không tồn tại | Không báo rename thành công |
| Rename qua naming context không hỗ trợ | Xử lý theo giới hạn server/protocol |

Một preflight `exists(newDn)` không loại bỏ race condition. Entry khác có thể được tạo sau khi kiểm tra và trước ModifyDN. Server vẫn là nơi quyết định collision cuối cùng.

### 6.3. Rename và ODM update là hai đường đi khác nhau

Nếu field được đánh dấu `@DnAttribute` thay đổi, ODM `update` có thể thực hiện unbind entry cũ rồi bind entry mới. Điều đó khác với server-side LDAP ModifyDN.

Vì vậy, test phải gọi đúng API theo yêu cầu:

- Test ODM update khi muốn kiểm tra semantics unbind/bind của mapping.
- Test `LdapTemplate.rename` khi muốn kiểm tra LDAP ModifyDN.
- Không dùng kết quả của một loại operation để kết luận loại còn lại có hành vi giống nhau.

Đặc biệt, referential integrity, operational attributes và audit log có thể khác nhau giữa hai đường đi.

### 6.4. Kiểm thử group references sau rename

Nếu group lưu DN thành viên trong `member` hoặc `uniqueMember`, cần xác minh trạng thái sau rename:

~~~text
Trước rename:
member: uid=alice,ou=people,dc=example,dc=org

Sau rename:
member: uid=alice.nguyen,ou=people,dc=example,dc=org
~~~

Hành vi cập nhật reference phụ thuộc LDAP server và cấu hình referential integrity/linked attributes. Không giả định mọi directory đều tự cập nhật.

Integration test nên:

1. Tạo group có member trỏ tới Alice.
2. Rename Alice bằng API được chọn.
3. Đọc lại group.
4. Assert reference cũ còn hay đã được thay theo policy.
5. Nếu ứng dụng quản lý reference, gọi workflow cập nhật và xác minh mọi group liên quan.
6. Kiểm tra không còn dangling reference ngoài phạm vi cho phép.

Với Active Directory, linked attributes như `member`/`memberOf` có semantics riêng. Với OpenLDAP, hành vi có thể phụ thuộc overlay như `refint`. Test phải dùng đúng server và cấu hình tương ứng.

## 7. Kiểm thử delete

### 7.1. Xác minh đúng entry đã bị xóa

Ví dụ:

~~~java
public void deletePerson(Name dn) {
    PersonEntry person =
        ldapTemplate.findByDn(dn, PersonEntry.class);

    ldapTemplate.delete(person);
}
~~~

Test:

~~~java
@Test
void deleteRemovesOnlyTargetEntry() {
    Name aliceDn = personDn("alice");
    Name bobDn = personDn("bob");

    personService.deletePerson(aliceDn);

    assertThat(directoryFixture.exists(aliceDn)).isFalse();
    assertThat(directoryFixture.exists(bobDn)).isTrue();
}
~~~

Không chỉ assert service không ném exception. Đọc lại directory để xác minh entry mục tiêu đã biến mất và entry không liên quan vẫn tồn tại.

### 7.2. Delete parent có child

LDAP thường từ chối xóa entry có child. Tạo fixture:

~~~text
ou=people,dc=example,dc=org
└── uid=alice,ou=people,dc=example,dc=org
~~~

Test xóa OU khi Alice còn tồn tại và xác minh server từ chối theo semantics của nó. Sau đó xóa Alice, rồi xóa OU.

Không giả định `delete(parent)` tự cascade như ORM quan hệ. Nếu service hỗ trợ xóa subtree, test phải xác minh thứ tự child-first và phạm vi được phép xóa.

### 7.3. Delete entry đang được tham chiếu

Trước khi xóa Alice, group có thể còn:

~~~ldif
dn: cn=engineering,ou=groups,dc=example,dc=org
member: uid=alice,ou=people,dc=example,dc=org
~~~

Tạo test để xác định server xử lý reference thế nào:

- Xóa Alice có bị từ chối không?
- Server có tự loại reference không?
- Reference cũ có còn trong group không?
- Overlay/linked attribute có được bật không?

Nếu ứng dụng quản lý references, workflow phải xóa hoặc thay references trước, rồi mới delete entry. Nếu một bước thất bại, operation cần được đánh dấu partial và có reconciliation.

### 7.4. Delete phải kiểm tra stable identity

DN có thể được tái sử dụng. Giả sử Alice bị xóa, sau đó một tài khoản khác được tạo tại cùng DN. Nếu worker retry delete chỉ dựa vào DN cũ, nó có thể xóa nhầm entry mới.

Trước khi retry hoặc phục hồi delete, kiểm tra stable ID như `entryUUID`, `objectGUID` hoặc khóa nghiệp vụ đáng tin cậy. Chỉ tiếp tục nếu entry hiện tại vẫn là đối tượng mà operation ban đầu nhắm tới.

## 8. Phục hồi khi thao tác LDAP thất bại

### 8.1. LDAP không cung cấp transaction cho chuỗi thao tác tùy ý

Một quy trình có thể gồm:

~~~text
Update attributes
    |
Rename entry
    |
Update group references
    |
Write operation completed
~~~

Nếu rename thành công nhưng cập nhật group references thất bại, directory đang ở trạng thái một phần. `@Transactional` của database ứng dụng không tự rollback các thao tác LDAP đã commit.

Vì vậy, workflow cần lưu ý định và tiến độ của từng bước. Đây thường là một **saga/compensation workflow** hoặc quy trình roll-forward có reconciliation.

### 8.2. Operation journal

Một record operation có thể gồm:

| Trường | Ý nghĩa |
| --- | --- |
| `operationId` | ID duy nhất cho lần thay đổi |
| `sourceId` | LDAP directory/partition |
| `stableEntryId` | Định danh đối tượng ổn định |
| `oldDn` | DN trước thao tác |
| `newDn` | DN đích nếu rename |
| `operationType` | UPDATE, RENAME hoặc DELETE |
| `status` | Trạng thái workflow |
| `step` | Bước đang thực hiện |
| `attemptCount` | Số lần thử |
| `lastErrorCode` | Mã lỗi chuẩn hóa |
| `createdAt`, `updatedAt` | Thời điểm ghi journal |

Các trạng thái tham khảo:

~~~text
PENDING
APPLYING
VERIFY_REQUIRED
APPLIED
COMPENSATION_PENDING
COMPENSATED
FAILED_FINAL
~~~

Journal phải được ghi bền vững trước khi bắt đầu thao tác LDAP. Không chỉ giữ operation state trong biến Java hoặc HTTP session.

### 8.3. Phân biệt lỗi chắc chắn chưa áp dụng và kết quả chưa xác định

Không phải mọi lỗi đều có cùng ý nghĩa:

- Validation lỗi trước khi gửi request: operation chưa được gửi tới server.
- LDAP trả result code từ chối rõ ràng: server báo operation thất bại theo response.
- Client timeout hoặc `CommunicationException` sau khi gửi request: server có thể đã áp dụng operation nhưng response bị mất.

Với trường hợp cuối, không retry mù quáng. Chuyển operation sang `VERIFY_REQUIRED`, đọc lại directory và so sánh trạng thái với ý định ban đầu.

### 8.4. Read-back để phân giải kết quả rename chưa xác định

Giả sử client gửi rename từ `oldDn` sang `newDn` rồi mất kết nối.

| Trạng thái đọc lại | Cách diễn giải ban đầu |
| --- | --- |
| Old DN tồn tại với đúng stable ID; new DN không tồn tại | Rename có thể chưa được áp dụng; có thể retry sau khi kiểm tra collision/ACL |
| Old DN không tồn tại; new DN tồn tại với đúng stable ID | Rename đã được áp dụng; có thể tiếp tục bước references |
| Old DN và new DN đều tồn tại | Có thể có entry khác tại DN đích hoặc state cạnh tranh; cần đối soát |
| Cả hai đều không tồn tại | Có thể entry bị xóa, move lần nữa hoặc đang đọc replica chưa hội tụ; cần nguồn có thẩm quyền |
| DN đích tồn tại nhưng stable ID khác | Không được coi là thành công; không ghi đè entry đó |

Không chỉ kiểm tra DN tồn tại. Cần xác minh stable ID để tránh nhầm một entry khác đã được tạo tại DN đích.

### 8.5. Read-back sau update chưa xác định

Nếu update mail timeout:

1. Đọc lại entry theo stable ID hoặc DN hiện tại.
2. So sánh mail với giá trị mong muốn.
3. Nếu đã bằng giá trị đích, đánh dấu bước update đã áp dụng.
4. Nếu vẫn là giá trị cũ và version chưa thay đổi, có thể retry theo policy.
5. Nếu có giá trị thứ ba, một writer khác có thể đã thay đổi; áp dụng conflict policy thay vì ghi đè mù quáng.

Nếu directory có version/revision phù hợp, dùng nó để phát hiện concurrent modification. `modifyTimestamp` không phải lúc nào cũng là version duy nhất hoặc thứ tự toàn cục qua replica.

### 8.6. Read-back sau delete chưa xác định

Nếu client mất response khi delete:

- Nếu DN không còn tồn tại và operation journal xác nhận stable ID mục tiêu, delete có thể được coi là đã áp dụng.
- Nếu DN vẫn tồn tại với cùng stable ID, có thể retry sau khi kiểm tra quyền và trạng thái.
- Nếu DN tồn tại với stable ID khác, tuyệt đối không xóa entry đó theo operation cũ.
- Nếu kết quả đọc không nhất quán do replica, chờ/re-read từ nguồn có thẩm quyền theo policy.

Một lookup trả `not found` trên một replica không nhất thiết chứng minh mọi replica đã hội tụ. Với delete quan trọng, cần xác định read endpoint và replication consistency cần thiết.

## 9. Compensation và roll-forward

### 9.1. Compensation không phải rollback nguyên tử

Giả sử workflow:

1. Cập nhật mail.
2. Rename DN.
3. Cập nhật group references.

Nếu bước 3 thất bại, có hai hướng:

**Roll-forward**

- Giữ DN mới.
- Retry cập nhật references.
- Reconcile những group còn trỏ DN cũ.
- Chỉ hoàn tất khi postcondition được thỏa.

**Compensation**

- Đưa entry về DN cũ.
- Khôi phục attribute nếu cần.
- Phục hồi references theo trạng thái trước.
- Ghi rõ các bước bù đã thành công/thất bại.

Compensation là những LDAP operations mới. Nó cũng có thể thất bại và không xóa được lịch sử thao tác đã xảy ra. Vì vậy, cần journal và kiểm thử từng điểm lỗi của compensation.

### 9.2. Chọn roll-forward hay compensation

| Tình huống | Hướng thường phù hợp |
| --- | --- |
| Rename thành công, reference update tạm thời lỗi | Roll-forward và retry references |
| DN đích bị chiếm bởi entry khác | Dừng, reconcile và yêu cầu quyết định; không ghi đè |
| Attribute update sai nhưng DN chưa đổi | Compensation có thể khôi phục giá trị cũ nếu chưa có writer mới |
| Delete đã áp dụng và không có tombstone/backup | Thường không thể rollback bằng cách “undelete” đơn giản; cần recreate theo policy |
| Một phần references đã đổi | Có thể roll-forward phần còn lại hoặc bù ngược có journal |
| Stable ID không xác định được | Dừng tự động và chuyển xử lý thủ công |

Đừng chọn compensation chỉ vì một bước ném exception. Trước tiên phải xác định server đã áp dụng những bước nào.

### 9.3. Postcondition của workflow

Định nghĩa postcondition rõ ràng trước khi viết test. Ví dụ rename user:

- Entry có stable ID mục tiêu tồn tại tại `newDn`.
- Entry không còn ở `oldDn`.
- RDN attribute có giá trị đúng.
- Các group references theo policy đều trỏ tới DN mới.
- Không có entry khác bị thay đổi ngoài operation scope.
- Journal ghi `APPLIED` sau khi mọi điều kiện hoàn tất.

Một workflow chỉ được đánh dấu hoàn tất khi postcondition được kiểm tra thành công hoặc các ngoại lệ đã được lưu vào trạng thái cần xử lý theo policy.

## 10. Fault injection: mô phỏng lỗi tại đúng ranh giới

### 10.1. Đặt abstraction trước LDAP adapter

Để kiểm thử service mà không phải mock toàn bộ `LdapTemplate`, có thể định nghĩa port:

~~~java
import javax.naming.Name;

public interface DirectoryPort {
    PersonSnapshot read(Name dn);
    void updateMail(Name dn, String mail);
    void rename(Name oldDn, Name newDn);
    void delete(Name dn);
    boolean exists(Name dn);
}
~~~

Adapter production triển khai bằng `LdapTemplate`. Test có thể dùng adapter thật với LDAP server test hoặc một decorator có khả năng gây lỗi.

### 10.2. Lỗi trước và sau khi server áp dụng operation

Hai điểm lỗi cần phân biệt:

~~~text
Failure BEFORE delegate:
  caller gửi operation
  fault wrapper ném exception
  LDAP server chưa nhận operation

Failure AFTER delegate:
  wrapper gọi LDAP thành công
  LDAP server đã áp dụng operation
  wrapper ném exception giả lập response bị mất
~~~

Ví dụ decorator cho rename:

~~~java
public final class FailAfterRenamePort implements DirectoryPort {

    private final DirectoryPort delegate;

    public FailAfterRenamePort(DirectoryPort delegate) {
        this.delegate = delegate;
    }

    @Override
    public void rename(Name oldDn, Name newDn) {
        delegate.rename(oldDn, newDn);

        // Giả lập server đã rename nhưng client mất response.
        throw new SimulatedCommunicationFailure();
    }

    @Override
    public PersonSnapshot read(Name dn) {
        return delegate.read(dn);
    }

    @Override
    public void updateMail(Name dn, String mail) {
        delegate.updateMail(dn, mail);
    }

    @Override
    public void delete(Name dn) {
        delegate.delete(dn);
    }

    @Override
    public boolean exists(Name dn) {
        return delegate.exists(dn);
    }
}
~~~

`SimulatedCommunicationFailure` là exception test do ứng dụng định nghĩa. Decorator cố ý ném lỗi sau khi adapter thật hoàn tất rename để mô phỏng kết quả chưa xác định. Nó không thay thế test network fault trên môi trường tích hợp nếu cần kiểm tra TCP/TLS thực tế.

Exception test có thể là một unchecked exception đơn giản:

~~~java
public final class SimulatedCommunicationFailure
        extends RuntimeException {
}
~~~

### 10.3. Test recovery cho rename đã được áp dụng

~~~java
@Test
void reconcilesRenameWhenResponseIsLost() {
    Name oldDn = personDn("alice");
    Name newDn = personDn("alice.nguyen");

    DirectoryPort failingPort =
        new FailAfterRenamePort(realDirectoryPort);

    RenameService service =
        new RenameService(failingPort, operationStore);

    assertThatThrownBy(() ->
        service.rename("entry-1001", oldDn, newDn)
    ).isInstanceOf(SimulatedCommunicationFailure.class);

    // Operation cần ở trạng thái VERIFY_REQUIRED hoặc tương đương.
    assertThat(operationStore.statusFor("entry-1001"))
        .isEqualTo(OperationStatus.VERIFY_REQUIRED);

    // Reconciler dùng adapter thật đọc trạng thái directory.
    reconciler.verifyPendingOperations();

    assertThat(realDirectoryPort.exists(oldDn)).isFalse();
    assertThat(realDirectoryPort.exists(newDn)).isTrue();
    assertThat(operationStore.statusFor("entry-1001"))
        .isEqualTo(OperationStatus.APPLIED);
}
~~~

Test này giả định service không đánh dấu `FAILED_FINAL` ngay khi nhận exception không xác định. Nó phải ghi lại trạng thái cần verify. Reconciler sau đó đọc directory qua adapter thật và hoàn tất journal.

### 10.4. Test lỗi trước khi operation được áp dụng

Decorator có thể ném exception trước khi gọi delegate. Kỳ vọng:

- Old DN vẫn tồn tại.
- New DN không tồn tại.
- Operation không được đánh dấu `APPLIED`.
- Reconciler xác nhận operation chưa được áp dụng.
- Retry chỉ diễn ra khi target DN vẫn hợp lệ và stable ID vẫn khớp.

Hai kịch bản trước/sau delegate kiểm tra hai trạng thái khác nhau. Chỉ test một trong hai sẽ bỏ sót một loại lỗi quan trọng.

## 11. Kiểm thử idempotency và retry

### 11.1. Update lặp lại

Gọi update cùng một giá trị hai lần:

~~~java
@Test
void repeatingSameUpdateDoesNotChangeFinalState() {
    Name dn = personDn("alice");

    personService.updateEmail(dn, "alice.new@example.org");
    personService.updateEmail(dn, "alice.new@example.org");

    PersonEntry stored =
        ldapTemplate.findByDn(dn, PersonEntry.class);

    assertThat(stored.getEmail())
        .isEqualTo("alice.new@example.org");
}
~~~

Test xác minh trạng thái cuối, không khẳng định server chỉ nhận đúng một Modify request. LDAP operation có thể được gửi lại; mục tiêu là tác động nghiệp vụ không bị nhân đôi.

### 11.2. Rename lặp lại

Rename không nên luôn được gửi lại với old DN sau khi lần đầu đã thành công. Service cần phân giải:

- Stable ID đang ở old DN: có thể thực hiện rename.
- Stable ID đã ở new DN: coi operation đã áp dụng.
- New DN chứa stable ID khác: conflict.
- Stable ID không còn tìm thấy: reconcile hoặc fail theo policy.

Test gọi cùng operation ID nhiều lần và xác minh journal chỉ có một kết quả logic `APPLIED`, entry không bị tạo bản sao.

### 11.3. Delete lặp lại

Delete thường được thiết kế idempotent ở mức workflow:

- Nếu entry còn tồn tại với đúng stable ID, thực hiện delete.
- Nếu entry đã biến mất và journal xác nhận đúng đối tượng đã bị xóa, xem thao tác đã hoàn tất.
- Nếu DN đã được tái sử dụng bởi stable ID khác, không xóa entry mới.
- Nếu không xác định được danh tính, chuyển sang manual reconciliation.

Không biến mọi `NameNotFoundException` thành success mà không kiểm tra operation target. Có thể DN sai ngay từ đầu hoặc entry đã bị move.

### 11.4. Test crash sau LDAP write nhưng trước journal commit

Một điểm lỗi quan trọng:

~~~text
1. Ghi rename vào LDAP thành công
2. Process crash
3. Journal vẫn ở APPLYING
4. Process restart
5. Reconciler đọc old DN và new DN
6. Xác minh stable ID
7. Journal chuyển APPLIED hoặc tiếp tục retry
~~~

Đây là test chứng minh recovery dựa trên trạng thái bền vững thay vì biến trong RAM. Cần kiểm thử tương tự cho update, delete và reference modification.

## 12. Kiểm thử compensation và partial failure

### 12.1. Ma trận điểm lỗi

Với workflow update + rename + references:

| Điểm lỗi | Trạng thái directory có thể có | Kết quả recovery cần kiểm tra |
| --- | --- | --- |
| Trước update | Chưa thay đổi | Retry toàn workflow nếu operation còn hợp lệ |
| Sau update, trước rename | Attribute mới, DN cũ | Tiếp tục rename hoặc bù attribute theo policy |
| Sau rename, response bị mất | Có thể old hoặc new DN | Reconcile bằng stable ID |
| Sau rename, trước reference update | DN mới, references cũ | Roll-forward references hoặc compensation |
| Giữa nhiều group reference | Một phần group đã đổi | Reconcile từng group theo trạng thái hiện tại |
| Sau references, trước journal commit | Directory đã hoàn tất, journal chưa hoàn tất | Verify postcondition rồi đánh dấu APPLIED |
| Trong compensation | Trạng thái phục hồi một phần | Lưu compensation step và tiếp tục/reconcile |

### 12.2. Test roll-forward

Giả lập group reference update thứ hai thất bại:

1. Rename Alice thành công.
2. Reference group A được cập nhật.
3. Reference group B lỗi.
4. Journal chuyển `VERIFY_REQUIRED` hoặc `COMPENSATION_PENDING` theo workflow.
5. Reconciler tìm tất cả group references còn trỏ DN cũ.
6. Cập nhật group B.
7. Xác minh không còn reference cũ trong phạm vi quản lý.
8. Journal chuyển `APPLIED`.

Test phải xác minh cả group A và B, tránh chỉ kiểm tra operation journal.

### 12.3. Test compensation

Nếu policy yêu cầu đưa entry về trạng thái cũ:

1. Rename Alice về DN cũ nếu DN cũ còn trống.
2. Khôi phục attribute theo snapshot/version đã lưu.
3. Khôi phục references theo policy.
4. Xác minh postcondition của compensation.
5. Ghi journal `COMPENSATED`.

Nếu DN cũ đã được một entry khác chiếm, compensation không được ghi đè. Chuyển sang manual reconciliation và giữ nguyên bằng chứng operation.

### 12.4. Delete có thể không phục hồi được bằng rollback

Sau delete, entry có thể không còn trong directory. Tái tạo một entry cùng DN không đảm bảo khôi phục được:

- `entryUUID`/`objectGUID`.
- Operational timestamps.
- Password state/history.
- Server-side audit identity.
- References và replication metadata.

Nếu cần phục hồi delete, hãy định nghĩa backup/export hoặc tombstone strategy riêng. Test recreate phải xác minh semantics mà nghiệp vụ chấp nhận; không gọi đó là rollback nguyên tử.

## 13. Kiểm thử concurrency và stale data

### 13.1. Hai writer sửa cùng entry

Một test có thể tạo hai worker:

- Worker A đọc mail cũ.
- Worker B đọc cùng entry và cập nhật mail mới.
- Worker A ghi giá trị từ snapshot cũ.

Nếu không có version check hoặc serialization, A có thể ghi đè B. Hãy kiểm thử policy thực tế:

- Serialize update theo stable ID.
- So sánh source version trước khi ghi.
- Dùng lock/lease ở application layer.
- Re-read và báo conflict nếu entry đã thay đổi.

Không giả định LDAP cung cấp optimistic locking tự động cho mọi attribute. Nếu cần assertion có điều kiện, hãy xác định server hỗ trợ control/extension nào và viết integration test cho đúng vendor.

### 13.2. Hai rename cạnh tranh

Hai worker có thể cùng đổi Alice sang hai DN khác nhau. Test nên xác minh:

- Chỉ một operation thắng theo lock/serialization policy.
- Worker còn lại đọc lại stable ID và DN hiện tại.
- Không tạo entry duplicate.
- Không cập nhật references theo DN lỗi thời.
- Journal ghi rõ operation thắng và operation conflict.

### 13.3. Delete cạnh tranh với update

Nếu delete và update chạy cùng lúc, kết quả phụ thuộc thứ tự server nhận operation. Ứng dụng cần policy theo stable ID và workflow state. Test nên bao gồm:

- Update hoàn tất trước delete.
- Delete hoàn tất trước update.
- Update nhận `NoSuchObject` sau delete.
- DN bị tái sử dụng sau delete.

Không cho phép worker retry update mù quáng trên DN đã thuộc về stable ID khác.

## 14. Kiểm thử ACL và bảo mật thao tác ghi

Chạy integration test bằng đúng bind identity của ứng dụng:

| Identity | Thao tác | Kỳ vọng |
| --- | --- | --- |
| Reader | Search entry | Được phép trong subtree được cấp |
| Reader | Modify attribute | Bị từ chối |
| Reader | ModifyDN | Bị từ chối |
| Reader | Delete | Bị từ chối |
| Writer | Update mail trong OU được cấp | Được phép |
| Writer | Rename sang OU ngoài phạm vi | Bị từ chối |
| Writer | Delete entry ngoài subtree | Bị từ chối |
| Writer | Add/Delete attribute bị cấm | Bị từ chối |

ACL và result code khác nhau theo server. Một số server ẩn entry hoặc attribute thay vì trả lỗi rõ ràng. Test phải assert hành vi được cấu hình cho vendor cụ thể.

Không dùng directory administrator cho mọi integration test rồi suy ra service account production có đủ hoặc thiếu quyền. Test bằng identity gần với production nhất.

## 15. Bộ test đề xuất

Ma trận dưới đây có thể dùng làm tiêu chí hoàn thành cho module CRUD/recovery:

| Nhóm | Kịch bản | Assertion quan trọng |
| --- | --- | --- |
| Update | Thay một attribute | Giá trị mới đúng, attribute khác giữ nguyên |
| Update | Null/empty/multivalue | Semantics đúng theo mapping |
| Update | Schema violation | Không báo thành công, trạng thái được giữ |
| Update | ACL deny | Không có thay đổi ngoài ý muốn |
| Rename | DN mới hợp lệ | Old DN mất, new DN có stable ID cũ |
| Rename | Target collision | Entry cũ vẫn còn, entry đích không bị ghi đè |
| Rename | Parent không tồn tại | Server từ chối, journal phản ánh failure |
| Rename | Group references | Hành vi đúng theo vendor/policy |
| Delete | Xóa leaf entry | Chỉ entry mục tiêu biến mất |
| Delete | Xóa parent có child | Server từ chối hoặc workflow xóa child-first |
| Delete | Entry đang được tham chiếu | Reference được xử lý theo policy |
| Recovery | Lỗi trước write | Directory không đổi, operation có thể retry |
| Recovery | Lỗi sau write | Reconciler nhận diện operation đã áp dụng |
| Recovery | Crash trước journal commit | Restart không tạo duplicate hoặc xóa nhầm |
| Recovery | Partial reference update | Tiếp tục hoặc compensation có kiểm tra |
| Idempotency | Gọi lại cùng operation ID | Một kết quả nghiệp vụ logic |
| Concurrency | Hai writer cùng update | Conflict policy được thực thi |
| Concurrency | Rename cạnh tranh | Không tạo duplicate, references không stale |
| Security | Reader thử ghi | Bị từ chối |
| Security | Writer vượt subtree | Bị từ chối |

Không cần mọi test chạy trong một class. Tách test nhanh, integration test server thật và test vendor compatibility để thời gian feedback hợp lý.

## 16. Tổ chức test và dọn dữ liệu

### 16.1. Không để test phụ thuộc thứ tự chạy

Mỗi test phải tự chuẩn bị fixture hoặc có namespace riêng. Không viết test B dựa vào test A đã rename Alice. JUnit có thể chạy test theo thứ tự khác hoặc song song.

### 16.2. Cleanup không được xóa nhầm dữ liệu

Teardown cần giới hạn trong subtree test. Nếu xóa subtree, duyệt descendants và xóa leaf trước parent. Không dùng filter quá rộng như `(objectClass=*)` trên base DN dùng chung.

Nếu cleanup thất bại, ghi rõ DN test còn sót và fail test suite hoặc đánh dấu fixture không sạch. Không âm thầm tiếp tục khiến test sau nhận dữ liệu cũ.

### 16.3. Test retry phải kiểm soát thời gian

Không dùng `Thread.sleep()` dài để chờ retry trong unit test. Inject `Clock`, scheduler hoặc retry policy để kiểm soát `nextAttemptAt`. Integration test có thể dùng timeout ngắn nhưng vẫn cần tránh phụ thuộc thời gian thực không ổn định.

### 16.4. Log và dữ liệu fixture

Dùng dữ liệu giả, không copy user/password thật từ production. Log test nên chứa operation ID và test namespace; tránh dump toàn bộ LDAP entry nếu fixture có PII hoặc credential marker.

## 17. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Chỉ mock `LdapTemplate` cho mọi test | Không kiểm tra schema, DN, ACL và server behavior | Bổ sung integration test LDAP |
| Chỉ assert service không ném exception | Không chứng minh directory đã thay đổi đúng | Read-back và assert postcondition |
| Dùng một LDAP server khác vendor rồi suy ra production | Bỏ sót referential integrity/ACL khác biệt | Test đúng vendor khi semantics quan trọng |
| So sánh DN bằng chuỗi tự tách dấu phẩy | Sai với RDN có escaped characters | Dùng `Name`/`LdapName` |
| Cho rằng ODM update luôn là ModifyDN | Nhầm unbind/bind với server-side rename | Test đúng API và semantics |
| Cho rằng rename tự cập nhật mọi DN reference | Dangling group references | Kiểm tra server overlay/linked attributes |
| Cho rằng delete cascade | Xóa parent thất bại hoặc còn orphan references | Xử lý child/reference rõ ràng |
| Retry sau timeout mà không read-back | Ghi lặp hoặc tác động lên entry khác | Reconcile theo stable ID |
| Xem `not found` luôn là delete thành công | Có thể DN sai hoặc entry đã move | Xác minh operation target |
| Compensation không có journal | Không thể tiếp tục khi bù trừ cũng lỗi | Ghi từng bước bền vững |
| Test chỉ lỗi trước operation | Bỏ sót trường hợp server đã áp dụng nhưng response mất | Fault inject cả trước và sau delegate |
| Test chỉ lỗi sau rename | Không kiểm tra trường hợp operation chưa được áp dụng | Kiểm tra cả hai phía ranh giới |
| Dùng UID cố định trong test chạy song song | Collision và test flaky | Namespace riêng hoặc reset cô lập |
| Xóa fixture parent trước child | Cleanup thất bại | Xóa leaf trước parent |
| Dùng admin identity cho mọi test | Không phát hiện thiếu quyền production | Test với bind identity thực tế |
| Dùng `sleep` để test retry | Test chậm và không ổn định | Inject clock/scheduler |

## 18. Checklist trước khi phát hành workflow LDAP CRUD

**Fixture và môi trường**

- [ ] Test dùng directory riêng, không phải production.
- [ ] Schema/objectClass và ACL tương thích môi trường triển khai.
- [ ] Fixture có parent, child, group và references cần thiết.
- [ ] DN relative/full được thống nhất.
- [ ] Test data cô lập và cleanup leaf-first.

**Update, rename và delete**

- [ ] Update được read-back và xác minh attribute ngoài phạm vi được bảo toàn.
- [ ] Null/empty/multivalue semantics có test.
- [ ] Rename xác minh old DN, new DN và stable ID.
- [ ] Target collision và parent không tồn tại được kiểm thử.
- [ ] Group references được kiểm tra theo đúng server.
- [ ] Delete parent có child và delete entry được tham chiếu được kiểm thử.
- [ ] Delete retry kiểm tra stable ID trước khi thao tác.

**Recovery**

- [ ] Operation intent được lưu bền vững trước LDAP write.
- [ ] Fault injection có trường hợp lỗi trước và sau khi server áp dụng.
- [ ] Ambiguous outcome chuyển sang read-back/reconciliation.
- [ ] Retry idempotent theo operation ID và stable ID.
- [ ] Partial failure có roll-forward hoặc compensation rõ ràng.
- [ ] Compensation có thể resume nếu chính nó thất bại.
- [ ] Crash/restart test không phụ thuộc RAM state.

**Concurrency và bảo mật**

- [ ] Hai writer cạnh tranh được kiểm thử.
- [ ] Worker stale không ghi đè trạng thái mới.
- [ ] Reader không thể update/rename/delete.
- [ ] Writer chỉ thao tác trong subtree/attribute được cấp.
- [ ] Log không chứa credential hoặc raw sensitive entry.
- [ ] Test không dùng dữ liệu production.

## 19. Câu hỏi tự kiểm tra

1. Vì sao unit test mock `LdapTemplate` không đủ để xác minh CRUD LDAP?
2. Fixture LDIF cần những entry nào để test user, group và references?
3. Vì sao phải thống nhất relative DN và full DN trong test?
4. Test update cần xác minh những attribute nào ngoài giá trị vừa đổi?
5. Vì sao null và collection rỗng cần test riêng?
6. `LdapTemplate.rename` cần được xác minh bằng những điều kiện nào?
7. Làm sao chứng minh entry tại DN mới là cùng stable ID với entry cũ?
8. Vì sao rename collision phải xác minh entry cũ vẫn còn?
9. Referential integrity khác nhau thế nào giữa OpenLDAP và Active Directory?
10. Vì sao không giả định rename tự cập nhật `member` hoặc `uniqueMember`?
11. LDAP delete có cascade child entries không?
12. Vì sao DN có thể được tái sử dụng và ảnh hưởng đến retry delete?
13. `CommunicationException` sau write khác lỗi validation trước write như thế nào?
14. Read-back cần kiểm tra gì để phân giải rename chưa xác định?
15. Vì sao không thể coi `not found` là delete thành công trong mọi trường hợp?
16. Operation journal cần lưu những thông tin nào?
17. Compensation khác rollback transaction như thế nào?
18. Khi nào roll-forward phù hợp hơn compensation?
19. Fault injection sau delegate mô phỏng tình huống nào?
20. Vì sao cần test cả lỗi trước và sau khi server áp dụng operation?
21. Làm sao kiểm thử crash sau LDAP write nhưng trước journal commit?
22. Idempotency của update, rename và delete có điểm khác nhau nào?
23. Vì sao cần test hai writer cập nhật cùng entry?
24. Làm sao đảm bảo teardown không xóa dữ liệu ngoài namespace test?
25. Hãy thiết kế test chứng minh group references được khôi phục sau partial rename.

## 20. Tổng kết

Kiểm thử update, rename và delete trong Spring Data LDAP phải xác minh **trạng thái thực trên directory**. Với update, đọc lại entry và kiểm tra cả attribute mục tiêu lẫn những field cần được bảo toàn. Với rename, kiểm tra DN cũ, DN mới, stable ID và các reference. Với delete, xác minh đúng entry bị xóa, xử lý child entries và không xóa nhầm entry mới được tạo tại DN cũ.

Phục hồi cần được kiểm thử như một workflow riêng. LDAP operation có thể đã được áp dụng dù client nhận timeout hoặc `CommunicationException`; vì vậy, journal phải ghi ý định bền vững, reconciler phải đọc lại trạng thái theo stable ID và retry cần idempotent. Khi một chuỗi thao tác chỉ hoàn tất một phần, hệ thống chọn roll-forward hoặc compensation dựa trên trạng thái đã xác minh. Compensation là operation mới và cũng có thể thất bại.

Một bộ test có giá trị cần chạy với LDAP server phù hợp, fixture cô lập, ACL gần production và fault injection ở cả trước lẫn sau ranh giới ghi. Khi test kiểm tra postcondition, recovery sau restart, concurrency và reference semantics, ứng dụng có cơ sở đáng tin cậy để vận hành các thay đổi directory quan trọng.

### Tài liệu tham khảo

- [Spring LDAP Reference — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html).
- [Spring LDAP API — `LdapTemplate` and `LdapOperations`](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapOperations.html).
- [Spring LDAP Reference — Testing LDAP Code](https://docs.spring.io/spring-ldap/reference/testing.html).
- [Spring Data LDAP Reference — Repositories](https://docs.spring.io/spring-data/ldap/reference/repositories.html).
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/).
- [Testcontainers for Java — Documentation](https://java.testcontainers.org/).
- [RFC 4511 — LDAPv3 Protocol: Add, Modify, Delete and ModifyDN](https://www.rfc-editor.org/rfc/rfc4511).
- [RFC 4512 — LDAP Directory Information Models and Schema](https://www.rfc-editor.org/rfc/rfc4512).
- [RFC 4514 — String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514).
