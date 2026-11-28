# Xây dựng lớp thích nghi thay vì buộc mọi máy chủ có cùng hành vi

**Spring Data LDAP** cung cấp mô hình repository và Object-Directory Mapping (ODM) để làm việc với LDAP entry qua Java object. Tuy nhiên, LDAP server trong thực tế có thể khác nhau về schema, giới hạn search, paging, controls, referral, xác thực, cách biểu diễn membership và các extension riêng của nhà cung cấp.

Một ứng dụng cần kết nối OpenLDAP, Microsoft Active Directory, 389 Directory Server hoặc một directory service do nhà cung cấp khác triển khai không nên giả định rằng mọi server đều hỗ trợ cùng tính năng hoặc trả cùng kết quả. Cách tiếp cận bền vững là xây dựng **lớp thích nghi (adapter layer)**: nghiệp vụ gọi một hợp đồng ổn định; adapter chọn cách truy cập phù hợp với capability và profile đã được kiểm thử của từng directory.

Mục tiêu không phải che giấu mọi khác biệt. Mục tiêu là đưa khác biệt vào một vị trí có thể cấu hình, kiểm thử, quan sát và thay thế, đồng thời giữ các quy tắc nghiệp vụ độc lập với chi tiết của LDAP vendor.

Sau bài học, bạn có thể:

- Phân biệt phần được chuẩn hóa bởi LDAP RFC với hành vi riêng của directory server.
- Khám phá root DSE, naming context, schema và các control/extension được hỗ trợ.
- Thiết kế port và adapter cho Spring Data LDAP.
- Dùng profile/capability để chọn paging, membership, referral và các chiến lược đặc thù.
- Xử lý giới hạn search, multi-valued attribute và kết quả không đầy đủ.
- Tách cấu hình theo môi trường mà không rải nhánh điều kiện theo tên vendor trong service nghiệp vụ.
- Xây dựng contract test và integration test cho từng loại server.

## 1. Vì sao không thể giả định mọi LDAP server giống nhau?

LDAP chuẩn hóa giao thức trao đổi, mô hình entry, DN, filter, operation và cơ chế mở rộng. Chuẩn không buộc mọi sản phẩm phải triển khai tất cả extension tùy chọn, cùng schema, cùng chính sách giới hạn hoặc cùng mô hình dữ liệu ứng dụng.

Ví dụ:

- Một server có thể hỗ trợ paged results control; server khác có thể không hỗ trợ.
- Một server có thể giới hạn số entry trả về theo từng search; server khác còn giới hạn số giá trị của một attribute đa trị.
- Active Directory hỗ trợ range retrieval cho attribute đa trị như member; client có thể chỉ nhận một phần giá trị trong mỗi response.
- OpenLDAP cho phép cấu hình soft limit, hard limit, unchecked limit và giới hạn riêng cho paged search.
- Hai directory có thể cùng hỗ trợ groupOfNames, nhưng dữ liệu membership thực tế có thể nằm trong member, uniqueMember, memberOf hoặc một cấu trúc riêng.
- Referral có thể được follow tự động ở một môi trường, nhưng bị ignore hoặc trả về lỗi partial result ở môi trường khác.
- TLS, SASL, bind DN, password policy, operational attributes và schema tùy chỉnh cũng có thể khác nhau.

### 1.1. Ba lớp khác biệt

| Lớp | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Khác biệt giao thức/capability | Control paging, assertion, DirSync, extended operation | Khám phá capability, kiểm tra OID và chọn chiến lược |
| Khác biệt mô hình dữ liệu | Base DN, objectClass, attribute name, syntax, membership | Profile schema và mapper riêng |
| Khác biệt vận hành/chính sách | Size/time limit, idle timeout, referral, TLS, quyền | Cấu hình theo môi trường và kiểm thử vận hành |

Một số khác biệt là giới hạn do quản trị viên đặt, không phải đặc tính cố định của vendor. Ví dụ MaxPageSize trong Active Directory có thể được cấu hình; không nên coi một con số mặc định là hợp đồng bất biến.

### 1.2. Phân biệt chuẩn và extension

| Cơ chế | Nguồn | Ghi chú |
| --- | --- | --- |
| LDAP Search, Add, Modify, Delete, ModifyDN | RFC 4511 | Operation nền tảng |
| DN, objectClass, schema, root DSE | RFC 4512 | Mô hình thông tin và khám phá server |
| LDAP filter | RFC 4515 | Cú pháp filter |
| Paged Results Control | RFC 2696 | Control chuẩn để lấy search theo trang |
| Assertion Control | RFC 4528 | Control chuẩn để gắn điều kiện vào operation |
| Modify-Increment | RFC 4525 | Extension chuẩn tùy chọn |
| DirSync, range retrieval, matching rule riêng | Microsoft AD DS/AD LDS | Extension đặc thù Active Directory |
| Overlays, limits, syncrepl | OpenLDAP | Tính năng và cấu hình riêng của OpenLDAP |

Đừng gọi một extension vendor là “LDAP chuẩn”. Ngược lại, cũng đừng tự viết lại một tính năng đã có chuẩn chỉ vì một server cụ thể triển khai nó khác.

## 2. Nguyên tắc thiết kế lớp thích nghi

Một lớp thích nghi tốt có các đặc điểm:

1. **Nghiệp vụ phụ thuộc vào interface nội bộ**, không phụ thuộc trực tiếp vào LdapTemplate, JNDI control hoặc OID của vendor.
2. **Adapter chịu trách nhiệm chuyển đổi** từ mô hình nghiệp vụ sang DN, filter, attribute và operation LDAP.
3. **Profile khai báo khác biệt đã biết** như base DN, schema mapping, paging strategy và referral policy.
4. **Capability discovery xác minh khả năng của server**, không chỉ đoán từ tên sản phẩm.
5. **Không giả định một feature có sẵn chỉ vì server nhận kết nối thành công.**
6. **Không che lỗi partial result** bằng cách trả một danh sách trông có vẻ đầy đủ.
7. **Khác biệt không thể chuẩn hóa phải được biểu diễn rõ** trong API nội bộ, ví dụ cursor, partial result hoặc unsupported operation.

### 2.1. Kiến trúc đề xuất

```text
                    Application services
                            |
                            v
                     DirectoryPort
                 (hợp đồng nghiệp vụ)
                            |
                            v
                    Adapter selector
                            |
             +--------------+--------------+
             |              |              |
             v              v              v
       OpenLDAP adapter  AD adapter   Generic adapter
             |              |              |
             +--------------+--------------+
                            |
                   Spring LDAP / JNDI
                            |
                            v
                    LDAP directory
```

Profile và capability đi cùng adapter:

```text
Server endpoint
      |
      v
Root DSE / schema probe
      |
      v
Discovered capabilities
      |
      +------ Explicit deployment profile
      |
      v
Validated DirectoryProfile
      |
      v
Adapter strategy selection
```

### 2.2. Interface nghiệp vụ nên nói ngôn ngữ nghiệp vụ

Không để service nghiệp vụ nhận Attributes, DirContext, Control, OID hoặc filter LDAP:

```java
public interface DirectoryPort {

    Optional<Person> findPersonByUid(String uid);

    SearchPage<Person> searchPeople(PersonCriteria criteria,
                                    DirectoryCursor cursor);

    void replacePrimaryEmail(PersonId personId, EmailAddress email);

    Set<PersonId> findDirectGroupMembers(GroupId groupId);
}
```

Interface mô tả hành động mà ứng dụng cần. Adapter chịu trách nhiệm:

- Chọn base DN.
- Chọn attribute name theo schema.
- Tạo filter an toàn.
- Chọn search scope và giới hạn.
- Gửi control nếu server hỗ trợ.
- Chuyển LDAP result code thành lỗi miền nghiệp vụ.
- Chuyển entry sang domain object.

Không trả LdapQuery, Name, Attributes hoặc NamingException ra ngoài adapter nếu không có lý do rõ ràng.

### 2.3. Interface kết quả phải biểu diễn paging và partial result

Không phải server nào cũng trả kết quả theo cùng một cơ chế. Dùng một kiểu kết quả nội bộ:

```java
public final class SearchPage<T> {

    private final List<T> items;
    private final DirectoryCursor nextCursor;
    private final boolean complete;
    private final String diagnosticCode;

    public SearchPage(List<T> items,
                      DirectoryCursor nextCursor,
                      boolean complete,
                      String diagnosticCode) {
        this.items = List.copyOf(items);
        this.nextCursor = nextCursor;
        this.complete = complete;
        this.diagnosticCode = diagnosticCode;
    }

    public List<T> getItems() {
        return items;
    }

    public Optional<DirectoryCursor> getNextCursor() {
        return Optional.ofNullable(nextCursor);
    }

    public boolean isComplete() {
        return complete;
    }

    public Optional<String> getDiagnosticCode() {
        return Optional.ofNullable(diagnosticCode);
    }
}
```

Nếu một referral chưa được xử lý hoặc server trả size limit, adapter không được tự đánh dấu complete=true. Ứng dụng phải biết kết quả là đầy đủ hay chỉ là một phần.

Cursor nên là token opaque đối với service. Đừng để controller hoặc client HTTP tự phân tích LDAP cookie. Cookie có thể gắn với connection, search context hoặc session của server.

## 3. Khám phá server trước khi chọn adapter

Không nên nhận diện server chỉ bằng cách kiểm tra hostname có chứa chữ ad, ldap hoặc openldap. Hostname không chứng minh server là sản phẩm nào; proxy và load balancer còn có thể đứng trước nhiều backend khác nhau.

LDAP cung cấp **root DSE** để client khám phá thông tin server. RFC 4512 định nghĩa các attribute quan trọng:

| Root DSE attribute | Ý nghĩa |
| --- | --- |
| namingContexts | Các naming context server master hoặc shadow |
| supportedLDAPVersion | Phiên bản LDAP server hỗ trợ |
| supportedControl | OID của request control được server nhận diện |
| supportedExtension | OID của extended operation được server nhận diện |
| supportedFeatures | OID của các feature tùy chọn được server công bố |
| supportedSASLMechanisms | SASL mechanism server nhận diện/hỗ trợ |
| subschemaSubentry | DN của subschema entry liên quan tới root DSE nếu có |
| altServer | URI của server thay thế nếu server công bố |

Các giá trị có thể phụ thuộc session và danh tính đã bind. Attribute vận hành của root DSE phải được yêu cầu rõ ràng; chúng không tự xuất hiện trong mọi search. RFC 4512 cũng cảnh báo không nên mặc định subschema được root DSE trỏ tới là schema áp dụng cho mọi entry trong server.

### 3.1. Đọc root DSE bằng JNDI

Để đọc root DSE, context phải được tạo với base DN rỗng. Nếu ContextSource đang cấu hình base là dc=example,dc=org, DN rỗng tương đối với context có thể trỏ tới base nghiệp vụ, không còn là root DSE.

Vì vậy, nên dùng một ContextSource riêng cho capability probe với base rỗng:

```java
@Bean
LdapContextSource rootDseContextSource(DirectoryProperties properties) {
    LdapContextSource source = new LdapContextSource();
    source.setUrl(properties.url());
    source.setBase("");
    source.setUserDn(properties.bindDn());
    source.setPassword(properties.password());
    source.setPooled(false);
    return source;
}
```

Thực hiện search ở base rỗng, scope OBJECT:

```java
Set<String> readRootDseAttributeNames(
        LdapTemplate rootDseTemplate) {

    return rootDseTemplate.executeReadOnly(context -> {
        SearchControls controls = new SearchControls();
        controls.setSearchScope(SearchControls.OBJECT_SCOPE);
        controls.setReturningAttributes(new String[] {
                "namingContexts",
                "supportedLDAPVersion",
                "supportedControl",
                "supportedExtension",
                "supportedFeatures",
                "supportedSASLMechanisms",
                "subschemaSubentry"
        });

        NamingEnumeration<SearchResult> results =
                context.search("", "(objectClass=*)", controls);

        if (!results.hasMore()) {
            return Set.of();
        }

        Attributes attributes = results.next().getAttributes();
        Set<String> names = new HashSet<>();
        NamingEnumeration<? extends Attribute> all = attributes.getAll();
        while (all.hasMore()) {
            names.add(all.next().getID());
        }
        return Set.copyOf(names);
    });
}
```

Đoạn mã trên minh họa thao tác root DSE và tên attribute có mặt. Khi triển khai capability probe thực tế, cần đọc từng giá trị attribute, đóng NamingEnumeration trong finally hoặc dùng helper quản lý tài nguyên, và xử lý trường hợp server không cho principal đọc một số attribute vận hành.

### 3.2. Đọc danh sách control OID

supportedControl chứa OID của request control server nhận diện. Ví dụ:

| Control | OID | Mục đích |
| --- | --- | --- |
| Simple Paged Results | 1.2.840.113556.1.4.319 | Paged search theo RFC 2696 |
| Assertion Control | 1.3.6.1.1.12 | Conditional operation theo RFC 4528 |
| Server Side Sort | 1.2.840.113556.1.4.473 | Sort kết quả trên server trong AD |
| Range retrieval của AD | 1.2.840.113556.1.4.802 | Khả năng range retrieval attribute đa trị trong AD |

Các OID trong bảng không có cùng nguồn chuẩn. Paged Results và Assertion Control là LDAP controls được chuẩn hóa; các control có tiền tố Microsoft là extension riêng của AD.

Đừng nhầm:

- supportedControl: request controls.
- supportedExtension: extended operations.
- supportedFeatures: elective features.

Không phải mọi response control đều cần xuất hiện trong supportedControl. Root DSE là tín hiệu discovery, không phải chứng nhận mọi edge case của feature đã hoạt động đúng.

### 3.3. Đọc schema qua subschemaSubentry

Schema LDAP mô tả:

- Attribute type, OID, syntax, equality/ordering/substring matching rule.
- Object class, loại structural/auxiliary/abstract và attribute MUST/MAY.
- Matching rule và các schema element khác.

Quy trình:

1. Đọc subschemaSubentry từ root DSE hoặc từ entry thuộc naming context cần kiểm tra.
2. Truy vấn DN subschema đó với scope OBJECT.
3. Yêu cầu các attribute như attributeTypes, objectClasses, matchingRules, matchingRuleUse, ldapSyntaxes.
4. So sánh schema thực tế với schema mà entity ODM mong đợi.
5. Ghi nhận schema version/fingerprint trong deployment report nếu hệ thống cần phát hiện drift.

Ví dụ truy vấn:

```java
Attributes schema = schemaTemplate.lookup(
        subschemaDn,
        new String[] {
                "attributeTypes",
                "objectClasses",
                "matchingRules",
                "matchingRuleUse",
                "ldapSyntaxes"
        });
```

Không phải server nào cũng cho phép đọc schema. Một số server có nhiều naming context hoặc partition với schema/extension khác nhau. Đừng lấy schema của root DSE rồi kết luận mọi partition có cùng định nghĩa.

### 3.4. Discovery có giới hạn và có cache

Không nên probe root DSE và schema trên mọi request. Thay vào đó:

- Probe khi ứng dụng khởi động hoặc khi endpoint thay đổi.
- Cache kết quả theo logical directory/endpoint.
- Gắn thời gian hết hạn hoặc version để refresh khi cần.
- Chỉ yêu cầu attribute cần thiết.
- Không log toàn bộ schema hoặc thông tin nội bộ nhạy cảm.
- Nếu capability quan trọng nhưng không xác định được, fail startup hoặc vô hiệu hóa feature theo policy.

## 4. Capability và profile là hai nguồn thông tin khác nhau

**Capability** trả lời: server công bố hoặc đã chứng minh hỗ trợ điều gì?

**Profile** trả lời: ứng dụng được triển khai với schema, naming convention, policy và lựa chọn adapter nào?

Ví dụ:

```java
public final class DirectoryCapabilities {

    private final Set<String> controls;
    private final Set<String> extensions;
    private final Set<String> features;
    private final Set<String> saslMechanisms;

    public DirectoryCapabilities(Set<String> controls,
                                 Set<String> extensions,
                                 Set<String> features,
                                 Set<String> saslMechanisms) {
        this.controls = Set.copyOf(controls);
        this.extensions = Set.copyOf(extensions);
        this.features = Set.copyOf(features);
        this.saslMechanisms = Set.copyOf(saslMechanisms);
    }

    public boolean supportsControl(String oid) {
        return controls.contains(oid);
    }

    public boolean supportsExtension(String oid) {
        return extensions.contains(oid);
    }
}
```

Profile có thể mô tả cách ứng dụng muốn sử dụng server:

```java
public enum PagingMode {
    RFC2696,
    CLIENT_SIDE_LIMITED,
    UNSUPPORTED
}

public enum MultiValueRetrievalMode {
    STANDARD,
    ACTIVE_DIRECTORY_RANGE,
    UNSUPPORTED
}

public enum ReferralMode {
    IGNORE,
    FOLLOW,
    THROW
}

public final class DirectoryProfile {

    private final String id;
    private final String baseDn;
    private final String personObjectClass;
    private final String uidAttribute;
    private final String emailAttribute;
    private final String groupMemberAttribute;
    private final PagingMode pagingMode;
    private final MultiValueRetrievalMode multiValueRetrievalMode;
    private final ReferralMode referralMode;
    private final int preferredPageSize;

    // Constructor, getters and validation omitted for brevity.
}
```

PagingMode chỉ điều khiển phân trang entry của search. MultiValueRetrievalMode là lựa chọn riêng cho việc đọc các attribute đa trị có thể bị giới hạn, ví dụ range retrieval của Active Directory. Không gộp hai chế độ này: một group có thể được tìm thấy qua paged search nhưng vẫn cần nhiều request range để đọc hết attribute member của chính entry đó.

Capability và profile phải được kiểm tra chéo:

| Tình huống | Hành động |
| --- | --- |
| Profile yêu cầu control nhưng root DSE không công bố | Fail startup hoặc vô hiệu hóa feature theo policy |
| Root DSE công bố control nhưng profile không bật | Không tự động dùng control |
| Control có mặt nhưng integration test thất bại | Đánh dấu feature unsupported trong profile |
| Root DSE không đọc được | Dùng profile đã được phê duyệt và test; không đoán |
| Schema thực tế không khớp profile | Fail startup hoặc đưa instance vào trạng thái không ready |

Không tự động bật feature chỉ vì OID xuất hiện. Một server có thể công bố control nhưng vẫn có giới hạn quyền, giới hạn session, lỗi cấu hình hoặc khác biệt phiên bản.

## 5. Profile theo directory thay vì nhánh if vendor

Một anti-pattern:

```java
if (serverName.contains("AD")) {
    // Dùng cách A
} else if (serverName.contains("OpenLDAP")) {
    // Dùng cách B
} else {
    // Cách mặc định
}
```

Vấn đề:

- Chuỗi tên có thể thay đổi hoặc bị proxy che.
- Một vendor có nhiều phiên bản và cấu hình khác nhau.
- Một server có thể bật/tắt extension.
- Cùng một product có thể dùng schema khác nhau giữa các tổ chức.
- Logic vendor lan vào service nghiệp vụ và khó kiểm thử.

Thay bằng cấu hình rõ ràng:

```yaml
app:
  directory:
    id: employee-directory
    adapter: active-directory
    base-dn: DC=corp,DC=example,DC=com
    schema:
      person-object-class: user
      uid-attribute: sAMAccountName
      email-attribute: mail
      group-object-class: group
      group-member-attribute: member
    paging:
      mode: RFC2696
      page-size: 500
    referrals:
      mode: IGNORE
```

Đây là ví dụ profile ứng dụng tự định nghĩa, không phải cấu hình Spring Boot LDAP có sẵn. Giá trị phải được quản trị viên xác nhận theo directory thực tế.

Profile OpenLDAP có thể khác:

```yaml
app:
  directory:
    id: staff-directory
    adapter: openldap
    base-dn: dc=example,dc=org
    schema:
      person-object-class: inetOrgPerson
      uid-attribute: uid
      email-attribute: mail
      group-object-class: groupOfNames
      group-member-attribute: member
    paging:
      mode: RFC2696
      page-size: 300
    referrals:
      mode: THROW
```

Không nên copy hai profile này vào production mà chưa đối chiếu schema, ACL, server limits và test.

## 6. Ví dụ khác biệt giữa Active Directory và OpenLDAP

Hai sản phẩm có thể phục vụ cùng một nghiệp vụ nhưng mô hình dữ liệu và vận hành không giống nhau.

| Khía cạnh | Active Directory | OpenLDAP |
| --- | --- | --- |
| Naming context | Thường có domain naming context như DC=corp,DC=example,DC=com; còn có configuration/schema/application NC | Naming context được cấu hình theo suffix/database, ví dụ dc=example,dc=org |
| User schema phổ biến | user, sAMAccountName, userPrincipalName, mail, objectGUID | inetOrgPerson, uid, cn, sn, mail |
| Group schema phổ biến | group, member, memberOf, primaryGroupID | groupOfNames, groupOfUniqueNames, member, uniqueMember tùy schema |
| Membership | DN link attributes; một số semantics đặc thù AD | Phụ thuộc objectClass/schema và overlay được cấu hình |
| Large search | MaxPageSize, paged control và các policy khác | Soft/hard size/time limits, paged result limits, unchecked limits |
| Attribute đa trị lớn | Range retrieval có thể cần cho member | Thường cần kiểm tra server limit và cách trả attribute |
| Controls | Nhiều Microsoft-specific controls như DirSync, range retrieval, VLV, tree delete | Hỗ trợ theo build/module/config; không mặc định có cùng control |
| Schema mở rộng | Schema forest và các extension AD | Schema được cấu hình qua schema files/config backend |
| Tính năng vận hành | Replication AD, Global Catalog, DC site, query policy | Syncrepl, overlays, database/backend và per-database limits |

Đây là các mẫu phổ biến, không phải danh sách tuyệt đối. OpenLDAP có thể nạp schema tương thích AD; AD LDS có thể dùng schema ứng dụng; một tổ chức có thể thay đổi objectClass và attribute theo nhu cầu.

### 6.1. Không dùng tên attribute làm hợp đồng nghiệp vụ

Nghiệp vụ cần một khái niệm PersonId, EmailAddress, GroupId. Adapter mới biết nó được lưu trong:

- uid hay sAMAccountName.
- mail hay attribute tùy chỉnh.
- DN hay objectGUID.

Nếu domain object mang trực tiếp tên attribute vendor, thay đổi directory sẽ lan khắp code.

### 6.2. Định danh bền vững

DN là tên định vị entry trong DIT; DN có thể thay đổi khi rename/move. Đối với một số directory, có thể dùng identifier ổn định như:

- entryUUID trong các server hỗ trợ.
- objectGUID trong Active Directory.
- Một business identifier bất biến do ứng dụng quản lý.

Adapter chuyển identifier về một PersonId nội bộ. Không giả định entryUUID và objectGUID là cùng attribute hoặc có cùng binary/string representation.

Nếu cần hỗ trợ nhiều server, phải xác định nguồn định danh và uniqueness scope. Identifier chỉ unique trong một naming context chưa chắc unique trên toàn hệ thống nhiều directory.

## 7. Schema adapter: ánh xạ attribute và objectClass

Spring LDAP ODM dùng annotation như @Entry, @Id, @Attribute, @DnAttribute để ánh xạ entity. ODM không tự làm cho schema của các vendor trở nên giống nhau.

Ví dụ entity Java không nên mang giả định một server duy nhất:

```java
public final class Person {

    private PersonId id;
    private String username;
    private String displayName;
    private EmailAddress email;

    // Constructor and accessors omitted.
}
```

Adapter có thể dùng mapper theo profile:

```java
public interface PersonEntryMapper {

    Person toDomain(Attributes attributes, Name dn)
            throws NamingException;

    Attributes toAttributes(Person person);
}
```

Với một schema:

```text
uid: lan
cn: Nguyen Thi Lan
mail: lan@example.org
objectClass: inetOrgPerson
```

Với schema khác:

```text
sAMAccountName: lan
displayName: Nguyen Thi Lan
mail: lan@example.org
objectClass: user
```

Domain vẫn nhận cùng Person; adapter xử lý khác biệt.

### 7.1. Tên attribute không phải lúc nào cũng đủ để suy ra semantics

Hai attribute cùng tên có thể khác:

- Syntax.
- Equality matching rule.
- Case sensitivity.
- Single-valued hay multi-valued.
- Read/write permission.
- Operational hay user attribute.
- Link/backlink behavior.

Ví dụ memberOf trong một directory có thể là backlink được server tính; trong server khác có thể là attribute được ứng dụng ghi hoặc overlay quản lý. Không được mặc định mọi memberOf có semantics giống nhau.

### 7.2. Kiểm tra objectClass và MUST/MAY

Trước khi tạo entry, adapter cần biết objectClass yêu cầu attribute nào:

- MUST: attribute bắt buộc.
- MAY: attribute tùy chọn.
- Structural object class quyết định loại entry.
- Auxiliary object class có thể bổ sung attribute.

Nếu một server yêu cầu sn nhưng ứng dụng chỉ gửi cn, Add có thể bị từ chối với objectClass violation hoặc constraint violation.

Không nên tạo một entry tối thiểu theo schema server A rồi gửi sang server B mà không validate profile.

### 7.3. Attribute đa trị

LDAP attribute có thể chứa một hoặc nhiều giá trị. Đừng ánh xạ mọi attribute sang String đơn nếu schema cho phép multi-value.

Ví dụ:

```java
private Set<String> mailAliases;
private Set<PersonId> directMembers;
```

Khi ghi, xác định semantics:

- Replace toàn bộ tập giá trị.
- Thêm một giá trị.
- Xóa một giá trị.
- Xóa toàn attribute.

Không thay ADD_ATTRIBUTE bằng REPLACE_ATTRIBUTE chỉ để tránh duplicate; thao tác Replace có thể ghi đè giá trị mà một ứng dụng khác vừa thêm.

## 8. Membership adapter cho các kiểu group khác nhau

Một API nghiệp vụ có thể cần:

```java
Set<PersonId> findDirectGroupMembers(GroupId groupId);
```

Nhưng cách lưu membership khác nhau:

| Kiểu | Attribute phổ biến | Ý nghĩa |
| --- | --- | --- |
| groupOfNames | member | DN của member; schema thường yêu cầu tối thiểu một member |
| groupOfUniqueNames | uniqueMember | DN kèm NameAndOptionalUID |
| Active Directory group | member | Forward link tới member; có semantics link riêng |
| AD primary group | primaryGroupID ở user | Không nhất thiết xuất hiện trong member |
| Nested group | Group chứa DN của group khác | Cần quyết định direct hay transitive membership |

Nếu API trả direct membership, không tự động mở rộng nested group. Nếu nghiệp vụ yêu cầu effective membership, adapter phải dùng chiến lược được kiểm thử theo server.

### 8.1. Active Directory matching rule in chain

Active Directory hỗ trợ matching rule in chain với OID:

```text
1.2.840.113556.1.4.1941
```

Matching rule này có thể được dùng trong filter để tìm quan hệ DN theo chuỗi liên kết, ví dụ nested group membership. Đây là extension AD; không đưa filter này vào adapter generic.

Không tìm OID này trong supportedControl: đây là matching rule dùng trong extensibleMatch filter, không phải request control. Microsoft ghi rõ matching rules được server hỗ trợ không có attribute root DSE chung để liệt kê. Vì vậy, hãy khai báo feature trong profile AD đã kiểm thử và xác minh bằng behavior test trên đúng Windows Server/AD LDS version.

Profile phải chỉ rõ:

- Feature có được bật không.
- Server/phiên bản đã kiểm thử.
- Query có giới hạn scope và timeout không.
- Kết quả là direct membership hay transitive membership.

Với server không hỗ trợ matching rule đó, adapter có thể duyệt nested groups ở client theo thuật toán có chống cycle, giới hạn depth và giới hạn số entry. Không được silently đổi nghĩa của API.

### 8.2. Primary group trong AD

Trong AD, membership của primary group được biểu diễn qua primaryGroupID của user và RID của group; không thể giả định chỉ đọc attribute member là thấy toàn bộ effective membership.

Nếu nghiệp vụ cần effective membership:

- Đọc primaryGroupID và ánh xạ RID theo domain SID.
- Xử lý group link member riêng.
- Quyết định có tính nested group hay không.
- Kiểm thử trên domain thật với các group policy tương ứng.

Nếu nghiệp vụ chỉ cần direct link membership, đặt tên method và tài liệu cho rõ.

## 9. Search limits: không phải server nào cũng giới hạn giống nhau

Client có thể đặt:

- Search time limit.
- Search count limit.
- Scope.
- Returning attributes.

Server vẫn có thể áp dụng hard limit thấp hơn yêu cầu client. Kết quả có thể kết thúc bằng sizeLimitExceeded, timeLimitExceeded hoặc adminLimitExceeded.

Không được:

- Coi số entry đã nhận là tổng số entry nếu server báo limit.
- Tăng page size vô hạn khi bị từ chối.
- Retry cùng một search nặng mà không đổi filter/scope.
- Bỏ qua lỗi partial result rồi đánh dấu job đồng bộ hoàn tất.

### 9.1. OpenLDAP limits

OpenLDAP có thể cấu hình:

- Global soft/hard size limit.
- Global soft/hard time limit.
- size.unchecked để giới hạn số candidate phải xét sau index lookup.
- size.pr để giới hạn page size.
- size.prtotal để giới hạn tổng số entry trong một paged search.
- Per-database và per-user/group limits.

Điểm quan trọng: bật paged results không có nghĩa bỏ qua mọi hard limit. OpenLDAP có thể áp dụng hard size limit cho tổng số kết quả của paged search và thêm các limit riêng.

### 9.2. Active Directory policies

Microsoft AD DS công bố các LDAP policy như:

| Policy | Ý nghĩa |
| --- | --- |
| MaxPageSize | Số object tối đa trong một search result; search lớn hơn cần paged search control |
| MaxQueryDuration | Thời gian tối đa cho một search hoặc batched extended operation |
| MaxValRange | Số giá trị tối đa của một attribute đa trị có thể lấy trong một request |
| MaxResultSetsPerConn | Số paged search result set server giữ tối ưu trên một connection |
| MaxConnIdleTime | Thời gian connection idle trước khi server đóng |
| MaxConnections | Giới hạn connection đồng thời |

Microsoft tài liệu hóa giá trị mặc định cho từng Windows Server release và cho phép quản trị viên cấu hình query policy. Vì vậy, profile phải được kiểm tra theo forest/domain/controller thực tế; đừng hardcode mặc định thành quy tắc bất biến.

### 9.3. Xử lý result code theo domain error

Không để controller hiểu NamingException hoặc LDAP numeric result code.

Adapter có thể chuyển đổi:

| LDAP result/exception | Domain error gợi ý |
| --- | --- |
| sizeLimitExceeded | DirectoryResultLimitExceeded |
| timeLimitExceeded | DirectoryQueryTimedOut |
| adminLimitExceeded | DirectoryPolicyLimitExceeded |
| unavailableCriticalExtension | DirectoryFeatureUnavailable |
| insufficientAccessRights | DirectoryAccessDenied |
| noSuchObject | DirectoryEntryNotFound |
| entryAlreadyExists | DirectoryEntryConflict |
| invalidAttributeSyntax | DirectoryDataRejected |
| CommunicationException | DirectoryUnavailable hoặc DirectoryOutcomeUnknown tùy operation |

Với write, timeout có thể tạo outcome không xác định. Adapter cần phân biệt DirectoryUnavailable trước khi gửi với DirectoryOutcomeUnknown sau khi request có thể đã tới server.

## 10. Paging strategy và cookie

Paged Results Control theo RFC 2696 dùng cookie để tiếp tục search ở trang sau. Client gửi page size và cookie nhận được từ response trước.

### 10.1. Paged results không giống offset/limit

| Offset pagination | LDAP paged results |
| --- | --- |
| Client gửi offset và page size | Client gửi page size và opaque cookie |
| Có thể nhảy tới trang bất kỳ | Thường phải đi tiếp theo cookie |
| Offset có thể gây scan lớn | Server duy trì trạng thái/cursor theo implementation |
| Không gắn với LDAP connection | Cookie có thể gắn với connection/search state |

Không tự giải mã hoặc tạo cookie LDAP. Lưu cookie như dữ liệu opaque.

### 10.2. Spring LDAP hỗ trợ paging qua DirContextProcessor

Spring LDAP cung cấp DirContextProcessor để gắn request control trước search và đọc response control sau search.

Trong Spring LDAP 4.2, lớp được tài liệu hóa là:

```java
PagedResultsControlExchangeDirContextProcessor
```

Ví dụ:

```java
SearchControls controls = new SearchControls();
controls.setSearchScope(SearchControls.SUBTREE_SCOPE);
controls.setReturningAttributes(new String[] {"uid", "cn", "mail"});

PagedResultsControlExchangeDirContextProcessor processor =
        new PagedResultsControlExchangeDirContextProcessor(300);

List<Person> all = SingleContextSource.doWithSingleContext(
        contextSource,
        operations -> {
            List<Person> collected = new ArrayList<>();
            do {
                List<Person> page = operations.search(
                        "ou=people",
                        "(objectClass=inetOrgPerson)",
                        controls,
                        personMapper,
                        processor);
                collected.addAll(page);
            } while (processor.hasMore());

            return collected;
        });
```

Để cookie tiếp tục hợp lệ, các lần gọi paged search cần dùng cùng underlying connection. Spring LDAP khuyến nghị SingleContextSource hoặc một transaction context thích hợp với ContextSourceTransactionManager và TransactionAwareContextSourceProxy.

Không tạo một PagedResultsControlExchangeDirContextProcessor mới cho từng trang rồi bỏ cookie cũ.

### 10.3. Không giả định server hỗ trợ paged results

Trước khi dùng:

1. Kiểm tra OID 1.2.840.113556.1.4.319 trong supportedControl.
2. Kiểm tra quyền của bind principal.
3. Gửi page size vừa phải.
4. Kiểm tra response control có cookie hợp lệ.
5. Xử lý trường hợp server trả unsupported critical extension.
6. Đo tổng số entry và tổng thời gian.

Nếu server không hỗ trợ paging, profile có thể chọn client-side giới hạn nhỏ hoặc trả lỗi feature unavailable. Không tải toàn bộ DIT vào memory rồi cắt thành trang ở application nếu tập dữ liệu lớn.

### 10.4. Cookie không nên lộ ra client HTTP

LDAP cookie có thể gắn với connection, server state và thời gian sống. Nếu API cần pagination nhiều request:

- Lưu cursor ở server-side cache có TTL.
- Hoặc mã hóa/sign cursor chứa profile, search criteria hash, cookie và session identity.
- Không cho client sửa filter/base DN trong khi tái sử dụng cookie.
- Không chuyển cookie sang server khác nếu server không bảo đảm portability.
- Xử lý cursor hết hạn bằng response rõ ràng.

### 10.5. AD range retrieval cho attribute đa trị

Paged results phân trang **entry**. Nó không giải quyết việc một entry có hàng nghìn giá trị trong một attribute.

Active Directory có thể trả attribute theo range, ví dụ:

```text
member;range=0-1499
member;range=1500-2999
member;range=3000-*
```

Client phải:

1. Yêu cầu attribute với range phù hợp.
2. Đọc tên attribute thực tế server trả về.
3. Phân tích lower/upper range.
4. Tiếp tục yêu cầu range kế tiếp cho đến khi server trả dấu sao ở upper bound.
5. Kiểm tra entry có bị thay đổi giữa các request không nếu cần consistency.

Không giả định request member luôn trả toàn bộ member của group. Microsoft mô tả MaxValRange là policy riêng và range retrieval là cơ chế nhiều request.

## 11. Controls và extensions: bọc sau strategy

Spring LDAP cho phép xử lý control bằng DirContextProcessor:

- preProcess: thêm request control vào LdapContext.
- postProcess: đọc response control.

Ví dụ khung:

```java
public final class CapabilityControlProcessor
        implements DirContextProcessor {

    @Override
    public void preProcess(DirContext context)
            throws NamingException {
        if (!(context instanceof LdapContext ldapContext)) {
            throw new IllegalArgumentException(
                    "LDAPv3 controls require an LdapContext");
        }

        Control[] existing = ldapContext.getRequestControls();
        // Build a new array and preserve controls required by other layers.
        // Add the profile-selected request control here.
        ldapContext.setRequestControls(existing);
    }

    @Override
    public void postProcess(DirContext context)
            throws NamingException {
        if (!(context instanceof LdapContext ldapContext)) {
            throw new IllegalArgumentException(
                    "LDAPv3 controls require an LdapContext");
        }

        Control[] responseControls = ldapContext.getResponseControls();
        // Parse only the response controls this strategy understands.
    }
}
```

Đây là khung minh họa; khi triển khai phải thêm control cụ thể, xử lý criticality, preserve/restore control cũ và kiểm tra response. Spring LDAP có AbstractRequestControlDirContextProcessor để tránh tự viết toàn bộ logic gắn control.

### 11.1. Criticality là quyết định nghiệp vụ

LDAP control có thể được gửi với cờ critical:

- Critical: nếu server không hỗ trợ hoặc không áp dụng được, operation phải thất bại.
- Non-critical: server có thể bỏ qua control và vẫn thực hiện operation.

Nếu feature bắt buộc để bảo đảm tính đúng đắn, ví dụ assertion để tránh lost update, không được gửi non-critical rồi giả định server đã kiểm tra assertion.

### 11.2. Không giữ state processor dùng chung giữa request

Processor paging thường giữ cookie và state của lần search. Không đăng ký một instance mutable dùng chung toàn singleton adapter cho nhiều request đồng thời.

Tạo processor theo từng search/session, giữ trong scope phù hợp và không chia sẻ cookie giữa principal hoặc tenant.

### 11.3. Không để OID rò ra service

Service nên gọi:

```java
directoryPort.searchPeople(criteria, cursor);
```

Adapter mới quyết định có dùng paged results, sort, assertion, VLV hoặc control vendor-specific. Không để business service tự dựng BasicControl với OID Microsoft.

## 12. Referral và partial result

Một search có thể gặp referral tới directory/server khác. Spring LDAP ContextSource hỗ trợ policy:

- ignore
- follow
- throw

Chọn policy theo trust boundary:

| Policy | Hành vi | Rủi ro |
| --- | --- | --- |
| ignore | Không tự động follow | Có thể chỉ nhận một phần kết quả |
| follow | JNDI provider tự follow referral | Credential, TLS và host đích phải được kiểm soát |
| throw | Đưa referral exception cho ứng dụng | Cần logic xử lý riêng |

Nếu bật follow:

- Allowlist referral host.
- Xác minh TLS certificate và hostname.
- Xác định credential có được gửi sang endpoint đích không.
- Giới hạn hop và thời gian.
- Kiểm tra base DN và quyền tại directory đích.

Lưu ý: JNDI/Spring LDAP với referral mode follow sẽ tự động theo referral; setReferral("follow") không tự thực thi hostname allowlist. Nếu bắt buộc giới hạn host, phải kiểm soát bằng referral handler tùy chỉnh hoặc network egress policy tương ứng. Nếu chưa có lớp kiểm soát này, dùng throw và xử lý referral sau khi xác minh URL.

Không dùng ignore-partial-result như một cách làm cho search trông thành công. Spring LDAP có tùy chọn bỏ qua PartialResultException, nhưng kết quả có thể không đầy đủ. Chỉ dùng khi nghiệp vụ chấp nhận partial data và adapter biểu diễn rõ trạng thái này.

## 13. TLS và xác thực theo profile

Không phải server nào cũng dùng cùng bind mechanism:

- SIMPLE bind trên TLS.
- SASL mechanism như GSSAPI/Kerberos.
- EXTERNAL qua client certificate.
- Proxy authorization hoặc cơ chế xác thực riêng.

Spring LDAP hỗ trợ DirContextAuthenticationStrategy và các strategy TLS. ContextSource cho phép cấu hình referral, base, nhiều URL failover và environment properties.

### 13.1. Profile không được làm yếu bảo mật

Không tạo fallback kiểu:

```text
LDAPS thất bại
   -> thử LDAP clear-text
```

Một adapter không được tự hạ cấp TLS hoặc tắt hostname verification để tương thích với server. Nếu TLS/certificate không đúng, đó là lỗi cấu hình hoặc trust cần sửa.

### 13.2. AuthenticationSource và pooling

Spring LDAP PoolingContextSource giả định các context trong cùng pool có môi trường/principal nhất quán. Không dùng pool service account cố định để tái sử dụng context cho nhiều credential người dùng.

Nếu mỗi request xác thực bằng username/password riêng:

- Dùng luồng bind/authentication phù hợp.
- Không chia sẻ context đã bind giữa các principal.
- Xem xét pool theo identity nếu có thiết kế an toàn và được hỗ trợ.
- Không log credential hoặc đưa password vào metric label.

### 13.3. Multi-URL không đồng nghĩa cùng một directory

Spring LDAP cho phép nhiều URL để failover. Chỉ dùng khi các endpoint là các node/replica của cùng logical directory hoặc có contract tương thích đã được xác minh.

Không gộp hai directory độc lập vào cùng danh sách URL nếu chúng có naming context, schema, ACL hoặc dữ liệu khác nhau. Cần hai ContextSource và hai adapter riêng.

## 14. Tách nhiều directory trong cùng ứng dụng

Một ứng dụng có thể đọc nhân viên từ AD nhưng đọc danh bạ đối tác từ OpenLDAP. Không nên ép hai nguồn thành một profile duy nhất.

```text
Application service
       |
       +---- EmployeeDirectoryPort
       |          |
       |          v
       |      ActiveDirectoryAdapter
       |
       +---- PartnerDirectoryPort
                  |
                  v
             OpenLdapAdapter
```

Mỗi adapter có:

- ContextSource riêng.
- Base DN riêng.
- Credentials/secret riêng.
- TLS trust và timeout riêng.
- Schema mapping riêng.
- Capability/profile riêng.
- Pool và metrics riêng.

Nếu cùng một nghiệp vụ cần kết hợp hai nguồn, service orchestration quyết định nguồn nào là authoritative cho từng field. Không chọn server ngẫu nhiên theo URL.

## 15. Cấu hình Spring LDAP theo adapter

Spring LDAP có LdapContextSource, LdapTemplate, LdapClient và repository support. Có thể dùng nhiều bean với qualifier:

```java
import java.util.Locale;

@Configuration
public class DirectoryConfiguration {

    @Bean
    @Qualifier("employeeContextSource")
    LdapContextSource employeeContextSource(
            EmployeeDirectoryProperties properties) {
        LdapContextSource source = new LdapContextSource();
        source.setUrl(properties.url());
        source.setBase(properties.baseDn());
        source.setUserDn(properties.bindDn());
        source.setPassword(properties.password());
        source.setReferral(properties.referralMode().name().toLowerCase(Locale.ROOT));
        return source;
    }

    @Bean
    @Qualifier("employeeLdapTemplate")
    LdapTemplate employeeLdapTemplate(
            @Qualifier("employeeContextSource")
            ContextSource contextSource) {
        return new LdapTemplate(contextSource);
    }

    @Bean
    @Qualifier("partnerContextSource")
    LdapContextSource partnerContextSource(
            PartnerDirectoryProperties properties) {
        LdapContextSource source = new LdapContextSource();
        source.setUrl(properties.url());
        source.setBase(properties.baseDn());
        source.setUserDn(properties.bindDn());
        source.setPassword(properties.password());
        source.setReferral(properties.referralMode().name().toLowerCase(Locale.ROOT));
        return source;
    }

    @Bean
    @Qualifier("partnerLdapTemplate")
    LdapTemplate partnerLdapTemplate(
            @Qualifier("partnerContextSource")
            ContextSource contextSource) {
        return new LdapTemplate(contextSource);
    }
}
```

Đoạn mã là cấu hình minh họa. Trong ứng dụng thật, bind password phải đến từ secret manager/configuration bảo mật; không đặt literal trong source hoặc YAML được commit.

### 15.1. LdapTemplate và LdapClient

Trong Spring LDAP 4.2:

- LdapTemplate hỗ trợ ODM và các thao tác LDAP quen thuộc.
- LdapClient cung cấp API fluent cho bind/search/modify/unbind/authenticate và hỗ trợ Stream.
- LdapClient hiện chưa hỗ trợ ODM.
- Cả hai có thể cùng tồn tại nếu ứng dụng cần mapping ODM và operation LDAP thủ công.

Không nên viết lại repository layer chỉ để đổi API. Chọn API theo nhu cầu mapping và control processing.

### 15.2. Repository nên nằm sau port

Repository có thể thuận tiện cho CRUD entity, nhưng service không cần biết repository dùng schema nào. Tạo adapter implement DirectoryPort, inject Spring Data LDAP repository bên trong adapter.

Nếu hai server dùng objectClass khác nhau, có thể có entity ODM khác nhau:

```text
Person domain model
       |
       +---- ActiveDirectoryPersonEntry
       |
       +---- OpenLdapPersonEntry
```

Adapter chuyển từng entity về cùng domain model.

## 16. Filter, DN và escaping trong adapter

Các server có thể hỗ trợ cùng filter syntax nhưng schema/matching rule khác nhau. Adapter phải:

- Dùng LdapQueryBuilder hoặc filter encoder.
- Không nối chuỗi input người dùng vào filter.
- Phân biệt escape filter value và escape DN component.
- Chỉ cho phép attribute name lấy từ profile đã kiểm tra.
- Giới hạn base DN ở server-side.
- Dùng matching rule riêng chỉ trong adapter tương ứng.

Ví dụ tìm người theo UID:

```java
LdapQuery query = LdapQueryBuilder.query()
        .base(profile.getPeopleBase())
        .where(profile.getUidAttribute())
        .is(uid);

return ldapTemplate.search(query, personMapper);
```

profile.getUidAttribute() phải là tên attribute được cấu hình và validate lúc startup, không lấy trực tiếp từ request HTTP. Giá trị uid đi qua builder để được encode phù hợp.

### 16.1. DN có base riêng

Spring LDAP ContextSource có thể cấu hình base DN; các DN truyền vào và nhận về thường là relative với base đó.

Với nhiều directory:

- Không dùng chung base DN.
- Không nối chuỗi DN bằng dấu phẩy thủ công.
- Dùng LdapName/Name và LdapUtils để xử lý DN.
- Chuyển full DN và relative DN ở ranh giới adapter một cách nhất quán.

### 16.2. Matching rule khác nhau

Một server có thể so sánh case-insensitive cho attribute cụ thể; server khác có matching rule khác. Không tự lower-case tất cả giá trị trước khi ghi hoặc query.

Nếu nghiệp vụ yêu cầu equality theo chuẩn cụ thể:

- Xác định matching rule của attribute trong schema.
- Kiểm tra server có hỗ trợ matching rule cần dùng.
- Dùng matching rule OID/descriptor trong adapter nếu cần.
- Kiểm thử Unicode, khoảng trắng, normalization và case.

## 17. Operational attributes và timestamps

Các server có thể cung cấp:

- createTimestamp, modifyTimestamp.
- creatorsName, modifiersName.
- AD whenCreated, whenChanged, uSNChanged, objectGUID.
- OpenLDAP entryUUID, entryCSN.

Tên và semantics không giống nhau:

| Mục tiêu | AD thường gặp | OpenLDAP thường gặp |
| --- | --- | --- |
| Identifier ổn định | objectGUID | entryUUID |
| Thời điểm tạo | whenCreated | createTimestamp |
| Thời điểm sửa | whenChanged | modifyTimestamp |
| Change sequence | uSNChanged | entryCSN |

Đây là ví dụ phổ biến, không phải ánh xạ tương đương tuyệt đối. uSNChanged có scope và semantics theo domain controller; entryCSN liên quan replication state của OpenLDAP. Không so sánh hai giá trị như một global version chung.

Operational attributes thường không được trả về nếu client không yêu cầu rõ ràng. Adapter phải yêu cầu attribute cần thiết và có quyền đọc.

## 18. Referral, replication và consistency

Một server có thể là replica hoặc shadow copy. RFC 4512 mô tả server cache/shadow có thể trả kết quả search từ bản sao nhưng referral hoặc liên hệ server khác khi nhận modification.

Vì vậy:

- Search thành công không chứng minh write được gửi tới cùng nơi.
- Read-after-write có thể bị ảnh hưởng bởi replication lag.
- Multi-URL failover có thể chuyển sang replica có trạng thái khác.
- Adapter cần biết operation nào yêu cầu authoritative read/write.

Với dữ liệu phân quyền, membership hoặc trạng thái nhạy cảm, không sử dụng replica stale nếu nghiệp vụ yêu cầu consistency mới nhất.

## 19. Capability discovery không thay thế contract test

Root DSE cho biết server công bố những gì. Nó không xác minh mọi hành vi.

Ví dụ:

- Server công bố paged results nhưng page cookie hết hạn sớm hơn dự kiến.
- Server công bố sort control nhưng giới hạn sort key hoặc memory.
- Schema có attribute nhưng ACL không cho service account đọc.
- supportedSASLMechanisms thay đổi theo trạng thái session.
- Referral được follow nhưng server đích có TLS trust khác.

Vì vậy cần hai lớp:

1. **Discovery test:** đọc root DSE, schema, controls và feature OID.
2. **Behavior test:** thực hiện operation nhỏ để xác minh hành vi, quyền và semantics.

Không chạy probe ghi dữ liệu lên production chỉ để khám phá capability. Dùng read-only operation hoặc fixture test có kiểm soát.

## 20. Contract test cho adapter

Tạo một bộ test dùng chung cho DirectoryPort. Mỗi adapter phải vượt qua cùng hợp đồng nghiệp vụ:

| Contract | Điều cần xác minh |
| --- | --- |
| Find person | Tìm đúng person theo business identifier |
| Search people | Filter, scope, paging và completeness đúng |
| Replace email | Chỉ cập nhật attribute email |
| Add group membership | Không tạo duplicate hoặc làm mất member hiện tại |
| Delete membership | Chỉ xóa membership mong muốn |
| Missing entry | Chuyển thành domain not-found nhất quán |
| Access denied | Chuyển thành domain access denied |
| Schema violation | Không retry mù quáng |
| Size/time limit | Không đánh dấu kết quả partial là complete |
| Referral | Hành vi đúng profile |
| Unicode DN/value | Đọc và ghi chính xác |
| Multi-valued attribute | Không mất giá trị khi đọc/ghi |

### 20.1. Test riêng cho capability

- Root DSE không có supportedControl.
- Root DSE chỉ trả một phần attribute do ACL.
- Paged control được công bố nhưng operation bị từ chối.
- Referral trả partial result.
- Schema subentry khác nhau theo naming context.
- Server không công bố vendor name.
- Server thay đổi capability sau upgrade.

### 20.2. Test riêng cho paging

- Kết quả có ít hơn một page.
- Kết quả đúng một page.
- Kết quả nhiều page.
- Cookie null báo hết trang.
- Cookie hết hạn.
- Dùng nhầm connection giữa hai page.
- Server không hỗ trợ paging.
- Paged search đạt total size limit.
- Caller dừng giữa chừng và giải phóng connection.

### 20.3. Test cho Active Directory range retrieval

- Attribute có ít hơn một range.
- Attribute có đúng một range.
- Attribute có nhiều range.
- Response dùng range=...-*.
- Group bị sửa giữa các lần lấy range.
- Service account không có quyền đọc một số giá trị.
- Không lặp vô hạn khi server trả range bất thường.

### 20.4. Test cho OpenLDAP limits

- Soft limit bị chạm.
- Hard limit bị chạm.
- size.unchecked chặn query không dùng index.
- Paged search bị size.prtotal giới hạn.
- Principal khác nhau có policy khác nhau.
- Referral/overlay làm kết quả thay đổi.

## 21. Observability cho từng adapter

Metric cần phân biệt logical directory và operation:

```text
directory=employee, operation=search-person, result=success
directory=employee, operation=search-person, result=size-limit
directory=partner, operation=lookup-contact, result=not-found
directory=employee, feature=paged-results, state=enabled
directory=employee, feature=range-retrieval, state=enabled
```

Theo dõi:

- Latency p50/p95/p99 theo operation.
- Success/error/partial result rate.
- LDAP result code và exception category.
- Số page và tổng entry được đọc.
- Paging cookie expired/rejected count.
- Range retrieval round trips.
- Pool active/idle/waiters.
- Referral follow/throw/ignore count.
- Capability probe success/failure.
- Schema fingerprint/version drift.

Không dùng full DN, UID, email, filter hoặc cookie làm metric label. Dữ liệu đó có cardinality cao và có thể chứa thông tin cá nhân hoặc token nội bộ.

## 22. Quản lý thay đổi khi nâng cấp server

Nâng cấp directory server có thể thay đổi:

- Supported controls/features.
- Schema extension.
- Default query policy.
- TLS/certificate.
- SASL mechanism.
- Referral behavior.
- Replication behavior.
- Attribute range/paging behavior.

Pipeline release nên:

1. Chạy discovery test với server version mới.
2. So sánh root DSE capability.
3. So sánh schema fingerprint.
4. Chạy contract test cho adapter.
5. Chạy load test search/paging.
6. Kiểm tra query policy và limits.
7. Kiểm tra read-after-write/replication.
8. Chỉ chuyển traffic sau khi profile được xác nhận.

Không tự động đổi adapter chỉ vì server version string thay đổi. Profile mới phải được kiểm thử và phê duyệt.

## 23. Những anti-pattern cần tránh

| Anti-pattern | Hậu quả | Cách sửa |
| --- | --- | --- |
| Rải điều kiện theo vendor trong service | Khó kiểm thử và khó nâng cấp | Profile + adapter strategy |
| Coi mọi server hỗ trợ paged results | Search thất bại hoặc thiếu dữ liệu | Capability probe và behavior test |
| Dùng một page size rất lớn | Vượt hard limit, tăng tải | Page size cấu hình và đo thực tế |
| Cắt danh sách ở client sau khi tải toàn bộ | Tốn memory và network | Server-side paging hoặc giới hạn rõ |
| Coi member trả đầy đủ mọi group member | Bỏ sót giá trị khi AD range retrieval | Range strategy |
| Coi memberOf luôn authoritative | Sai effective membership | Profile schema và semantics |
| Bỏ qua PartialResultException mặc định | Đồng bộ thiếu dữ liệu | Biểu diễn partial result |
| Follow mọi referral | Credential/TLS bị gửi tới host ngoài ý muốn | Allowlist và referral policy |
| Dùng chung ContextSource cho hai directory | Sai base, credential, schema | Bean và adapter riêng |
| Đọc root DSE qua context có base nghiệp vụ | Nhầm base entry với root DSE | Dedicated empty-base ContextSource |
| Dùng root DSE schema cho mọi naming context | Mapping sai partition | Discover subschema theo context |
| Bật control non-critical dù nghiệp vụ cần nó | Server bỏ qua control nhưng app vẫn tưởng thành công | Critical control và capability validation |
| Dùng mutable processor singleton | Cookie/state bị chia sẻ giữa request | Processor theo search/session |
| Hardcode default limit của vendor | Hỏng sau thay policy/version | Đọc policy và kiểm thử |
| Để OID vendor lọt vào domain model | Nghiệp vụ phụ thuộc server | OID nằm trong adapter |
| Dùng operational attribute như global version | Sai consistency/replication | Semantics riêng theo server |

## 24. Quy trình triển khai adapter mới

Khi cần hỗ trợ một directory server mới:

1. **Thu thập contract:** base DN, schema, objectClass, attribute, ACL và operation cần thiết.
2. **Khám phá capability:** root DSE, supportedControl, supportedExtension, supportedFeatures, SASL và subschema.
3. **Xác định khác biệt:** paging, limits, referrals, group membership, operational attributes, TLS và authentication.
4. **Tạo profile:** khai báo các giá trị cấu hình đã được xác minh.
5. **Implement adapter:** map domain model, query, write và error.
6. **Chọn strategy:** paging, range retrieval, membership, referral hoặc controls.
7. **Chạy contract tests:** cùng bộ test nghiệp vụ với adapter khác.
8. **Chạy behavior tests:** extension và giới hạn riêng của server.
9. **Bổ sung telemetry:** metrics/logs theo logical directory.
10. **Triển khai canary:** xác minh kết quả và latency trước khi chuyển toàn bộ traffic.

## 25. Bài tập tự luyện

**Câu 1.** Vì sao không nên chọn adapter chỉ bằng cách kiểm tra hostname có chứa AD?

*Gợi ý:* Hostname không chứng minh server, version, capability hoặc cấu hình schema.

**Câu 2.** Root DSE có thể cho biết những capability nào?

*Gợi ý:* namingContexts, supportedControl, supportedExtension, supportedFeatures, supportedLDAPVersion, supportedSASLMechanisms.

**Câu 3.** Nếu root DSE công bố paged results control, có thể bỏ integration test không?

*Gợi ý:* Không. Discovery chỉ là tín hiệu; cần test behavior, quyền, cookie và connection lifecycle.

**Câu 4.** Vì sao subschemaSubentry của root DSE không đủ để khẳng định schema của mọi naming context?

*Gợi ý:* RFC 4512 cảnh báo subschema được root DSE trỏ tới có thể chỉ điều khiển schema của root DSE.

**Câu 5.** Paged results và AD range retrieval khác nhau thế nào?

*Gợi ý:* Paged results phân trang entry; range retrieval chia các giá trị của một attribute đa trị.

**Câu 6.** Vì sao OpenLDAP paged search vẫn có thể bị hard size limit?

*Gợi ý:* size.prtotal và hard limit có thể giới hạn tổng số kết quả, không chỉ số entry mỗi page.

**Câu 7.** Vì sao không nên trả LDAP cookie trực tiếp cho client HTTP?

*Gợi ý:* Cookie có thể gắn với connection/server state; nên dùng opaque cursor được quản lý ở adapter.

**Câu 8.** Khi nào cần hai ContextSource trong cùng ứng dụng?

*Gợi ý:* Khi hai directory có endpoint, base DN, credentials, schema hoặc policy khác nhau.

**Câu 9.** Có nên dùng memberOf để tính effective membership trên mọi server không?

*Gợi ý:* Không. Attribute và semantics phụ thuộc schema/server; nested group và primary group có thể cần xử lý riêng.

**Câu 10.** Nếu server không hỗ trợ control bắt buộc để tránh lost update, adapter nên làm gì?

*Gợi ý:* Không âm thầm bỏ control; fail fast hoặc dùng chiến lược đã được chứng minh tương đương.

## 26. Ghi nhớ

- LDAP chuẩn hóa giao thức và mô hình dữ liệu nền, nhưng không buộc mọi server có cùng schema, extension, limit và policy.
- **Tách nghiệp vụ khỏi LDAP vendor:** dùng DirectoryPort, adapter và domain model ổn định.
- **Root DSE là điểm bắt đầu khám phá:** đọc naming context, supported controls/extensions/features và SASL.
- **Capability discovery không thay behavior test:** server công bố feature chưa bảo đảm mọi operation sẽ thành công trong context của ứng dụng.
- Profile chứa base DN, schema mapping, paging, referral, membership và các policy đã được kiểm thử.
- OpenLDAP có soft/hard limits, unchecked limit và giới hạn riêng cho paged results.
- Active Directory có MaxPageSize, MaxQueryDuration, MaxValRange và range retrieval cho attribute đa trị.
- Paged results phân trang entry; range retrieval phân trang giá trị trong một attribute.
- Spring LDAP dùng DirContextProcessor để gắn/đọc controls; paged results cần giữ cùng connection giữa các page.
- Không follow referral tùy ý hoặc bỏ qua partial result mà không biểu diễn kết quả chưa đầy đủ.
- Không dùng member, memberOf, objectGUID, entryUUID, uSNChanged hoặc entryCSN như thể có cùng semantics trên mọi server.
- Tách ContextSource, credentials, base DN, profile và pool khi ứng dụng dùng nhiều directory độc lập.
- Contract test phải chạy trên từng adapter; behavior test phải kiểm tra extension, limits, schema và ACL của server thực tế.

**Tài liệu tham khảo chính thức:**

- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): LDAP operations, controls, search result và referrals.
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): root DSE, namingContexts, supportedControl, supportedExtension, supportedFeatures và subschema discovery.
- [RFC 2696 — LDAP Control Extension for Simple Paged Results Manipulation](https://www.rfc-editor.org/rfc/rfc2696): paging cookie và paged search.
- [RFC 4528 — LDAP Assertion Control](https://www.rfc-editor.org/rfc/rfc4528): conditional operations.
- [Spring LDAP 4.2 — Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): ContextSource, referral, base DN, authentication strategy, LdapTemplate và LdapClient.
- [Spring LDAP 4.2 — Processing the DirContext](https://docs.spring.io/spring-ldap/reference/processing-the-dircontext.html): DirContextProcessor, controls và paged search.
- [Spring LDAP — PagedResultsControlExchangeDirContextProcessor API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/control/PagedResultsControlExchangeDirContextProcessor.html): processor cho paged results.
- [Microsoft MS-ADTS — LDAP Policies](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-adts/3f0137a1-63df-400c-bf97-e1040f055a99): MaxPageSize, MaxQueryDuration, MaxValRange và query policies theo Windows Server release.
- [Microsoft MS-ADTS — LDAP Extended Controls](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-adts/3c5e87db-4728-4f29-b164-01dd7d7391ea): control OID, gồm paged results, range retrieval và các extension AD.
- [Microsoft MS-ADTS — LDAP_SERVER_RANGE_OPTION_OID](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-adts/83fa0a7f-e3cb-48d9-be74-43c95f96ad45): range retrieval của attribute đa trị.
- [Microsoft — Search Filter Syntax](https://learn.microsoft.com/en-us/windows/win32/adsi/search-filter-syntax): matching rule OID, LDAP_MATCHING_RULE_IN_CHAIN và ví dụ truy vấn nested group.
- [Microsoft MS-ADTS — LDAP Matching Rules](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-adts/4e638665-f466-4597-93c4-12f2ebfabab5): các matching rule OID và phiên bản AD DS/AD LDS hỗ trợ.
- [OpenLDAP 2.6 Administrator's Guide — Limits](https://www.openldap.org/doc/admin26/limits.html): soft/hard limits, unchecked limits, per-database limits và paged result limits.
- [OpenLDAP 2.6 Administrator's Guide — Overlays](https://www.openldap.org/doc/admin26/overlays.html): overlay architecture và behavior tùy cấu hình.
