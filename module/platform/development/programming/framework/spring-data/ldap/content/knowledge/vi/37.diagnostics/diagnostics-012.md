# Kiểm thử chạy đúng nhưng khác hành vi Active Directory hoặc OpenLDAP thật

Một bài kiểm thử Spring Data LDAP có thể chạy xanh trên embedded LDAP nhưng thất bại khi kết nối **Microsoft Active Directory (AD DS/AD LDS)** hoặc **OpenLDAP**. Nguyên nhân thường không nằm ở cú pháp Java: mỗi directory có schema, naming context, matching rule, attribute, control, ACL, password policy và cách cấu hình riêng. Embedded server thường chỉ mô phỏng một phần hành vi LDAP cần thiết cho unit test.

Trong module **SPRING_DATA_LDAP**, ứng dụng làm việc với DN, objectClass, schema, repository, LdapTemplate, filter và kết nối directory. Vì vậy, kiểm thử cần xác minh cả contract LDAP chung lẫn behavior của sản phẩm/version thực tế. Bài thuộc chương **Chẩn đoán**, tập trung vào chủ đề **“Kiểm thử chạy đúng nhưng khác hành vi Active Directory hoặc OpenLDAP thật”**. Nội dung trình bày cách phân tầng test, khám phá RootDSE, so sánh schema và filter, kiểm thử group/account state, multivalued attributes, paging, TLS, referrals, ACL và cách lưu diagnostic đủ để tái hiện lỗi.

> **Nguyên tắc:** embedded LDAP chứng minh code xử lý được một mô hình LDAP tối thiểu. Nó không chứng minh ứng dụng tương thích với AD hoặc OpenLDAP. Những hành vi phụ thuộc server phải được kiểm thử trên đúng product, version, schema, cấu hình và quyền kết nối.

## 1. Vì sao test xanh nhưng chạy thật lại lỗi?

Một embedded directory có thể chấp nhận fixture và query rất đơn giản:

```ldap
dn: uid=linh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@example.org
```

Bộ fixture này có thể đủ cho một repository method tìm theo UID. Nhưng khi chuyển sang AD DS, entry người dùng có thể được biểu diễn bằng class user, thuộc tính sAMAccountName, userPrincipalName, userAccountControl, objectGUID và memberOf. Khi chuyển sang OpenLDAP, class inetOrgPerson có thể dùng được, nhưng memberOf có thể chỉ xuất hiện khi administrator bật overlay tương ứng.

Các khác biệt thường gặp:

- Test dùng uid, production dùng sAMAccountName hoặc UPN.
- Test giả định mọi server đều có memberOf.
- Test giả định group membership luôn bao gồm primary group và nested group.
- Test đọc toàn bộ member nhưng AD trả range từng phần.
- Test giả định paging/sort control luôn có sẵn.
- Test chạy bằng root/admin account, production chạy bằng service account có ACL hạn chế.
- Test bỏ qua TLS, hostname verification và referral.
- Test giả định objectClass hoặc matching rule giống nhau.
- Test không kiểm tra binary attribute như objectGUID/objectSid.
- Test không phản ánh password policy hoặc account state của server thật.

Một test xanh chỉ có giá trị trong phạm vi những behavior mà môi trường test thực sự mô phỏng.

## 2. Phân tầng kiểm thử để biết test nào đang chứng minh điều gì

Nên chia test thành các tầng độc lập:

| Tầng | Môi trường | Mục tiêu |
|---|---|---|
| Unit test | Không cần LDAP | Kiểm tra filter builder, mapper, normalization, policy và exception mapping |
| ODM/repository test | Embedded LDAP | Kiểm tra @Entry, DN mapping, CRUD cơ bản, query method phổ thông |
| LDAP integration test | OpenLDAP thật | Kiểm tra schema, ACL, controls, overlay và hành vi OpenLDAP |
| Directory compatibility test | AD DS hoặc AD LDS thật | Kiểm tra schema Microsoft, bind, group, account state, controls, range retrieval |
| Environment acceptance | Topology gần production | Kiểm tra TLS, DNS, referral, replication, service account và quyền thật |

Không cần chạy mọi test trên mọi pull request. Có thể chạy unit/embedded ở mỗi commit, OpenLDAP integration trong CI và AD compatibility suite theo lịch hoặc trước release. Tuy nhiên, release cần có bằng chứng từ đúng loại directory mà hệ thống triển khai.

## 3. Xác định chính xác directory đang được kiểm thử

Đừng chỉ ghi “LDAP server”. Hãy ghi rõ:

- Product: Active Directory Domain Services, Active Directory Lightweight Directory Services hay OpenLDAP.
- Version/build.
- Server role và topology: domain controller, Global Catalog, AD LDS instance, standalone OpenLDAP hoặc replica.
- TLS mode và endpoint logical.
- Base DN/naming context.
- Schema extensions đã cài.
- Overlay/plugin đang bật.
- Controls và SASL mechanisms được hỗ trợ.
- Service account và ACL được dùng trong test.

AD DS và AD LDS không hoàn toàn giống nhau. AD LDS cung cấp directory service kiểu LDAP nhưng không có toàn bộ semantics domain của AD DS. Tương tự, hai OpenLDAP server có thể khác nhau vì schema, overlay, ACL, backend, module và cấu hình cn=config.

Một test report chỉ ghi “AD” hoặc “OpenLDAP” là chưa đủ để tái hiện lỗi.

## 4. Khám phá RootDSE trước khi chạy test

Mỗi LDAP server có RootDSE ở base DN rỗng. RootDSE có thể cung cấp thông tin naming context và capability của server.

Các thuộc tính thường hữu ích:

| RootDSE attribute | Mục đích |
|---|---|
| namingContexts | Naming context server phục vụ |
| defaultNamingContext | Domain naming context mặc định trong AD DS |
| configurationNamingContext | Configuration partition trong AD |
| schemaNamingContext | Schema partition trong AD |
| supportedLDAPVersion | Phiên bản LDAP protocol được hỗ trợ |
| supportedControl | OID của controls server công bố hỗ trợ |
| supportedExtension | Extended operation server công bố hỗ trợ |
| supportedSASLMechanisms | SASL mechanisms server công bố |
| vendorName, vendorVersion | Thông tin vendor/version nếu server cung cấp |

Ví dụ truy vấn RootDSE bằng ldapsearch:

```bash
ldapsearch -LLL -x \
  -H ldaps://directory.example.org:636 \
  -s base -b "" "(objectClass=*)" \
  namingContexts defaultNamingContext \
  supportedLDAPVersion supportedControl \
  supportedExtension supportedSASLMechanisms \
  vendorName vendorVersion
```

Một số thuộc tính có thể không tồn tại hoặc bị ẩn theo server/configuration. Đừng giả định RootDSE của mọi server có cùng tập field. Trong AD, defaultNamingContext và supportedControl giúp xác định domain context và các control như paged results; OpenLDAP có thể trả namingContexts cùng capability theo cấu hình.

Không log toàn bộ RootDSE ra log công khai. Hostname, naming context và capability có thể tiết lộ topology nội bộ.

## 5. Phân biệt AD DS, AD LDS và OpenLDAP

| Đặc điểm | AD DS | AD LDS | OpenLDAP |
|---|---|---|---|
| Mục đích | Directory cho domain/forest Windows | Directory LDAP cho ứng dụng, không yêu cầu domain controller | Directory server tổng quát, cấu hình theo tổ chức |
| Naming context | Domain, Configuration, Schema và các partition khác | Application directory partition và cấu hình/schema | Suffix/database do administrator cấu hình |
| User object | Thường dùng class hierarchy của user | Schema và class phụ thuộc instance | Thường dùng schema như inetOrgPerson, account hoặc custom |
| Login attribute | Có thể dùng DN, UPN, sAMAccountName tùy bind flow | Phụ thuộc schema/configuration | Thường là DN hoặc attribute được ứng dụng resolve |
| Group membership | member, memberOf, primaryGroupID, nested group semantics | Một số AD attributes có khác biệt với AD DS | groupOfNames, groupOfUniqueNames, overlay hoặc custom schema |
| Account state | userAccountControl, computed attributes và policy domain | Có các attribute AD LDS riêng | Có thể dùng ppolicy overlay hoặc schema/custom attribute |
| Binary identity | objectGUID, objectSid | Có thể có AD-specific attributes | Thường gặp entryUUID |
| Controls | Bộ controls Microsoft và LDAP controls hỗ trợ | Có khác biệt theo version | Controls phụ thuộc build/configuration/module |

Không viết một test duy nhất rồi giả định cả ba loại server có cùng schema và semantics. Hãy xác định sản phẩm triển khai thực tế; nếu ứng dụng tuyên bố hỗ trợ nhiều loại directory, mỗi loại cần compatibility suite riêng.

## 6. Schema và objectClass là nguyên nhân phổ biến nhất

LDAP server chỉ chấp nhận attribute và objectClass phù hợp schema đang được nạp. Một embedded server có thể cho phép fixture đơn giản hoặc schema mở rộng, trong khi production từ chối entry vì:

- Attribute chưa được định nghĩa.
- Attribute có syntax khác.
- Attribute single-valued nhưng fixture gửi nhiều giá trị.
- Entry thiếu MUST attribute.
- Entry chứa objectClass structural không tương thích.
- Attribute không được phép sửa (NO-USER-MODIFICATION).
- Giá trị vi phạm matching rule hoặc constraint.
- Schema custom chưa được cài trên một node.

### Ví dụ hai mô hình user khác nhau

OpenLDAP thường có thể dùng inetOrgPerson:

```ldap
dn: uid=linh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@example.org
```

AD DS thường biểu diễn một domain user với hierarchy như top, person, organizationalPerson, user; các thuộc tính đăng nhập thường là sAMAccountName hoặc userPrincipalName:

```text
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: user
sAMAccountName: linh
userPrincipalName: linh@example.org
cn: Linh Nguyen
sn: Nguyen
```

Đây là ví dụ mô tả schema, không phải LDIF portable để import trực tiếp. AD có các required attributes, naming rules và provisioning semantics riêng; OpenLDAP cần schema/module phù hợp. Hãy tạo fixture theo schema server, rồi map về cùng domain DTO ở tầng ứng dụng.

### Kiểm thử schema có chủ đích

- Thử create entry đầy đủ MUST attributes.
- Thử thiếu từng required attribute và xác minh lỗi server.
- Thử sai syntax, multi-value và objectClass combination.
- Thử modify attribute read-only hoặc operational.
- Xác minh schema extension đã cài trên mọi node.
- Không dùng quyền root để che lỗi ACL hoặc schema policy.

## 7. objectClass và objectCategory trong Active Directory

Trong AD, objectClass có thể chứa nhiều class trong hierarchy. objectCategory là thuộc tính đơn biểu diễn class cụ thể hơn và thường phù hợp cho type matching trong một số search.

Ví dụ filter AD:

```ldap
(&(objectCategory=person)(objectClass=user)(sAMAccountName=linh))
```

Một filter OpenLDAP phổ biến với inetOrgPerson:

```ldap
(&(objectClass=inetOrgPerson)(uid=linh))
```

Không dùng filter AD trên OpenLDAP rồi kết luận LdapTemplate bị lỗi nếu schema OpenLDAP không có objectCategory hoặc sAMAccountName. Cũng không thay mọi filter AD bằng objectClass=inetOrgPerson nếu directory AD thật đang lưu domain users theo class user.

Tạo DirectoryQueryStrategy hoặc adapter theo product/schema. Không rải tên attribute theo vendor khắp controller và business service.

## 8. Attribute name, syntax và matching rule

LDAP attribute description thường được so khớp không phân biệt hoa thường theo quy tắc protocol, nhưng **matching semantics của giá trị** phụ thuộc syntax và matching rule của attribute.

Những khác biệt có thể gặp:

- Case-ignore string so với case-exact string.
- Equality matching và substring matching.
- Ordering matching rule cho so sánh lớn/nhỏ.
- DN matching so với string equality.
- Binary syntax so với text.
- Generalized Time, integer và numeric string.
- Attribute có nhiều giá trị.

Ví dụ, test so sánh UID bằng Java equalsIgnoreCase() có thể không phản ánh matching rule mà directory server thực thi. Hãy kiểm thử filter trên server thật với các giá trị khác hoa thường, Unicode, dấu cách và ký tự đặc biệt.

Không tự chuẩn hóa lowercase mọi attribute. Chuẩn hóa theo contract của field và matching rule thực tế.

## 9. LDAP filter và DN escaping là hai việc khác nhau

Một lỗi thường gặp là dùng cùng một hàm escape cho LDAP search filter và Distinguished Name.

- **Filter escaping** theo RFC 4515 xử lý các ký tự như *, (, ), backslash và NUL trong assertion value.
- **DN escaping** theo RFC 4514 xử lý cách biểu diễn RDN, ví dụ dấu phẩy, dấu cộng, dấu nháy, backslash, dấu cách đầu/cuối và ký tự đặc biệt.
- Hai context có grammar khác nhau; không dùng kết quả escape filter làm DN hoặc ngược lại.

Dùng Spring LDAP EqualsFilter, LikeFilter hoặc API filter phù hợp để encode assertion value. Dùng LdapName/Rdn để parse và dựng DN; tránh nối chuỗi DN bằng input trực tiếp.

Test cần bao gồm:

```text
Normal:       linh
Filter chars: a*(b)\c
DN value:     Nguyen, Linh
Unicode:      Nguyễn Văn Ánh
Leading/trailing spaces
```

Xác minh filter vẫn là một assertion đúng cấu trúc và DN parse về cùng RDN mong đợi. Không chỉ assert chuỗi filter chứa ký tự đã escape; hãy thực hiện search trên server và kiểm tra entry thực sự được tìm.

## 10. Matching rule mở rộng riêng của Active Directory

AD hỗ trợ một số extensible matching rule OID không phải filter portable giữa mọi LDAP server:

| OID | Tên | Ý nghĩa |
|---|---|---|
| 1.2.840.113556.1.4.803 | LDAP_MATCHING_RULE_BIT_AND | Các bit được chỉ định đều phải có |
| 1.2.840.113556.1.4.804 | LDAP_MATCHING_RULE_BIT_OR | Có ít nhất một bit được chỉ định |
| 1.2.840.113556.1.4.1941 | LDAP_MATCHING_RULE_IN_CHAIN | Duyệt quan hệ DN theo chuỗi ancestry/link |

Ví dụ AD tìm user bị disable theo bit trong userAccountControl:

```ldap
(&(objectCategory=person)(objectClass=user)
  (userAccountControl:1.2.840.113556.1.4.803:=2))
```

Ví dụ tìm thành viên group theo nested membership:

```ldap
(member:1.2.840.113556.1.4.1941:=CN=Engineering,OU=Groups,DC=example,DC=org)
```

Những filter này phụ thuộc AD DS/AD LDS version và không được mặc định có trong OpenLDAP. Đặt chúng trong adapter AD, kiểm tra version/capability và viết integration test trên đúng server. Không đưa OID vendor-specific vào repository method dùng chung nếu module cần hỗ trợ nhiều directory.

## 11. Group membership không đồng nhất giữa AD và OpenLDAP

### Active Directory

- Group entry thường có attribute member chứa DN của thành viên.
- User có memberOf cho các group backlink trong phạm vi semantics của AD.
- memberOf không bao gồm primary group của user; primary group được biểu diễn bằng primaryGroupID.
- Nested group membership cần được xử lý theo semantics AD, có thể dùng matching rule in-chain nếu version hỗ trợ.
- Group scope/type (global, universal, domain local; security/distribution) ảnh hưởng cách membership được sử dụng.

### OpenLDAP

- Có thể dùng groupOfNames với member, hoặc groupOfUniqueNames với uniqueMember.
- memberOf không phải thuộc tính mặc định được đảm bảo cho mọi cấu hình. OpenLDAP có memberof overlay để duy trì backlink khi membership thay đổi.
- memberOf từ overlay có thể là operational attribute và cần yêu cầu rõ trong search attribute list.
- Overlay chỉ hoạt động khi được nạp và cấu hình trên database phù hợp.

### Test phải phân biệt direct và nested membership

Fixture nên có:

- User trực tiếp thuộc Group A.
- Group A là thành viên của Group B.
- User thuộc primary group (nếu test AD DS).
- User không thuộc group nào.
- Entry bị xóa hoặc rename khi đang được tham chiếu.

Không assert rằng memberOf trả toàn bộ group hiệu lực trên cả hai server. Xác định business rule cần direct membership hay transitive membership, sau đó triển khai strategy tương ứng.

## 12. Kiểm thử memberOf overlay trên OpenLDAP

OpenLDAP documentation mô tả memberof overlay cập nhật attribute backlink khi membership attribute (thường là member) của group thay đổi. Cấu hình này không tự xuất hiện chỉ vì server là OpenLDAP.

Trong integration test:

1. Xác minh overlay đã được nạp cho database test.
2. Tạo groupOfNames với attribute member.
3. Tạo user entry.
4. Add user DN vào group.
5. Search user và yêu cầu attribute memberOf.
6. Xóa hoặc thay đổi membership.
7. Search lại và xác minh backlink được cập nhật.
8. Chạy test bằng bind identity có ACL tương ứng.

Nếu overlay không được cài, test phải báo rõ prerequisite thiếu hoặc bỏ qua suite có điều kiện; không sửa code ứng dụng để giả định server có overlay.

## 13. Account state khác nhau giữa AD và OpenLDAP

Không có một thuộc tính LDAP portable biểu diễn toàn bộ trạng thái tài khoản trên mọi directory.

### Active Directory

Một số attribute thường gặp:

- userAccountControl: các bit cấu hình account, gồm account disabled và nhiều flag khác.
- lockoutTime: thời điểm lockout được ghi nhận.
- msDS-User-Account-Control-Computed: các bit computed như lockout/password expired trong AD DS theo semantics server.
- pwdLastSet, accountExpires, badPwdCount và các attribute khác có thể liên quan policy.

Không đọc userAccountControl như một enum đơn giản. Đây là bit field; account disabled không đồng nghĩa account locked. Lockout có semantics theo policy và computed state, không nên suy luận chỉ từ một attribute thô.

### OpenLDAP

Nếu dùng Password Policy overlay, server có thể cung cấp các operational attributes như:

- pwdAccountLockedTime.
- pwdChangedTime.
- pwdFailureTime.
- pwdReset.
- pwdGraceUseTime.

Sự hiện diện và behavior phụ thuộc ppolicy overlay, policy được áp dụng và quyền đọc. Nếu không cấu hình ppolicy, các thuộc tính này có thể không tồn tại.

### Thiết kế adapter

Tạo một abstraction ở tầng ứng dụng:

```java
public enum DirectoryFlag {
    TRUE,
    FALSE,
    UNKNOWN
}

public record DirectoryAccountState(
        DirectoryFlag enabled,
        DirectoryFlag locked,
        DirectoryFlag passwordExpired,
        DirectoryFlag mustChangePassword
) {}

public interface AccountStateReader {
    DirectoryAccountState readAccountState(String userDn);
}
```

Triển khai adapter AD và OpenLDAP riêng. Nếu server không cung cấp đủ dữ liệu, trả trạng thái UNKNOWN/không xác định hoặc dùng flow xác minh phù hợp; đừng mặc định mọi field thiếu là false.

Test từng trạng thái bằng fixture hoặc policy thật. Với lockout/password expiry, cần phân biệt giá trị được persist với giá trị computed tại thời điểm đọc.

## 14. Password attribute và password change không portable

AD và OpenLDAP có mô hình password khác nhau:

- OpenLDAP thường lưu userPassword theo password scheme được cấu hình; Password Policy overlay có thể điều khiển expiry, quality và lockout.
- AD DS sử dụng unicodePwd với các yêu cầu đặc thù về secure channel và encoding; thao tác thay đổi password không phải một repository.save() thông thường.
- Password change có thể cần LDAP Password Modify extended operation hoặc cơ chế vendor-specific được hỗ trợ.
- ACL, TLS và policy server quyết định thao tác có được phép hay không.

Không đọc password hash để tự xác thực. Không log password hoặc bind credentials. Không viết test giả định một update attribute password thông thường sẽ chạy trên cả hai server.

Tách password change thành adapter có contract riêng và test trên directory đích. Test failure cases gồm TLS không hợp lệ, thiếu quyền, password policy reject và credential cũ không đúng.

## 15. Binary identity: objectGUID, objectSid và entryUUID

Không giả định identity attribute của directory đều là String:

| Attribute | Thường gặp ở | Kiểu/ý nghĩa |
|---|---|---|
| objectGUID | AD DS/AD LDS | Binary GUID 16 byte |
| objectSid | AD DS security principal | Binary SID |
| entryUUID | OpenLDAP | UUID theo schema/server |
| entryCSN | OpenLDAP replication metadata | CSN, không phải user ID chung |

AD objectGUID là binary; chuyển byte sang UUID cần tuân thủ byte order của các field GUID. Không dùng new String(bytes) hoặc UUID.nameUUIDFromBytes() để diễn giải GUID của AD.

Test cần:

- Đọc raw bytes và kiểm tra length/syntax.
- Chuyển đổi bằng adapter đã được kiểm chứng.
- Round-trip so sánh với tool/vendor output.
- Không giả định entryUUID có cùng representation hoặc lifecycle với objectGUID.
- Không dùng DN làm identity bất biến nếu entry có thể rename/move.

Nếu business model cần một ID portable, hãy map server-specific identity vào một kiểu nội bộ đã chuẩn hóa và ghi rõ nguồn.

## 16. Attribute đa trị và range retrieval trên AD

Một entry có thể có hàng nghìn giá trị trong attribute như member. AD giới hạn số giá trị trả về trong một search response theo MaxValRange policy. Khi cần đọc hết, AD dùng **range retrieval**.

Ví dụ client yêu cầu:

```text
member;range=0-1499
```

Server có thể trả attribute description dạng:

```text
member;range=0-1499
```

Nếu còn giá trị, client yêu cầu range kế tiếp. Khi server trả range kết thúc bằng *, ví dụ member;range=1500-*, đó là dấu hiệu đã đến giá trị cuối. Range thực tế server trả có thể khác requested range theo giới hạn cấu hình.

Không giả định một lần Attributes.get("member") trên AD trả toàn bộ membership list. Với OpenLDAP, server behavior và size limit/overlay khác; không áp dụng cú pháp range AD vào OpenLDAP.

Tạo một MultiValueAttributeReader theo capability. Kiểm thử entry có ít hơn, bằng và nhiều hơn giới hạn range; kiểm tra cả attribute ID trả về và số giá trị thực tế. Không dùng một con số cố định như 1500 cho mọi forest/server.

## 17. Operational attributes và projection

Một search thường chỉ trả user attributes được yêu cầu. Operational attributes có thể cần yêu cầu riêng hoặc có quyền đọc riêng.

Ví dụ OpenLDAP memberOf overlay có thể là operational attribute; nếu mapper chỉ đọc uid, cn, mail, nó sẽ không xuất hiện dù entry có membership backlink.

Thay vì dùng wildcard trả mọi attribute:

- Chỉ định rõ projection cần thiết.
- Tách user attributes và operational attributes.
- Kiểm tra ACL cho từng attribute.
- Ghi nhận attribute không được trả do thiếu quyền hay do không tồn tại.
- Không map missing attribute thành một giá trị mặc định có thể thay đổi business meaning.

Trong LDAP search, * và + có semantics khác nhau: * yêu cầu user attributes; + yêu cầu operational attributes theo hỗ trợ server. Kiểm tra behavior của server và JNDI provider trước khi dựa vào chúng.

## 18. DN, naming context và base search khác nhau

Một ứng dụng có thể cấu hình base DN:

```text
ou=people,dc=example,dc=org
```

Nhưng AD DS có nhiều naming context, ví dụ domain, Configuration và Schema. OpenLDAP thường dùng suffix/database được cấu hình trong slapd. Một DN tồn tại ở server A có thể không nằm trong naming context của server B.

Các lỗi hay gặp:

- Dùng base DN của domain A khi kết nối DC của domain B.
- Dùng defaultNamingContext trong khi cần search application partition của AD LDS.
- Dùng Global Catalog rồi kỳ vọng mọi attribute đều có mặt; GC chỉ chứa partial attribute set cho một số naming context.
- Hard-code OU path trong test rồi dùng trên môi trường có OU khác.
- Dựng DN bằng cách nối chuỗi từ input có dấu phẩy hoặc ký tự đặc biệt.
- Nhầm relative base trong ContextSource với absolute DN.

Test cần kiểm tra base DN thực tế, naming context, search scope và kết quả khi base không tồn tại hoặc không được phép đọc.

## 19. Referral và topology

AD có thể trả referral khi search chạm naming context/domain khác hoặc khi client dùng endpoint không phù hợp. OpenLDAP cũng có thể cấu hình referral hoặc chaining/proxy backend.

Kiểm thử cần xác định:

- Referral chasing bật hay tắt.
- Client có credential để bind sang referral target không.
- TLS truststore có tin certificate của target không.
- Referral target có cùng security boundary không.
- Có nguy cơ gửi credential tới endpoint không được tin cậy không.
- Referral loop hoặc unreachable target được xử lý thế nào.

Không bật referral chasing toàn cục mà không xem xét security. Nếu application chỉ được phép đọc một naming context, referral không được làm mở rộng phạm vi truy cập.

AD Global Catalog (GC) có endpoint và attribute availability riêng. Khi ứng dụng dùng GC, test phải xác minh các attribute cần dùng có trong partial attribute set và search scope đúng forest/domain.

## 20. Paging, sort và server limits

Cả AD và OpenLDAP có thể hỗ trợ paged results control, nhưng capability, policy limit và cách quản trị khác nhau.

- Đọc supportedControl từ RootDSE để biết server công bố OID control.
- Xác minh page size thực tế, server-side size limit và cookie lifecycle.
- Dùng cùng connection nếu Spring LDAP processor yêu cầu.
- Không giả định countLimit tương đương paging.
- Không giả định sort control được hỗ trợ hoặc server luôn trả sorted result.
- Không coi estimate là total count chính xác.
- Test page cuối, cookie rỗng, timeout, cancellation và directory thay đổi giữa pages.

AD có thể áp dụng MaxPageSize/MaxValRange và các policy server khác. OpenLDAP có sizelimit, timelimit, limits theo identity và control/overlay tùy cấu hình. Không đưa giá trị mặc định từ một môi trường thành hằng số của ứng dụng.

## 21. TLS và bind behavior phải test trên server thật

Một test chạy embedded LDAP không chứng minh TLS production hoạt động. Với AD/OpenLDAP, cần xác minh:

- LDAPS hoặc StartTLS được cấu hình đúng.
- Certificate chain được trust.
- SAN/hostname khớp endpoint mà ứng dụng dùng.
- Client không tắt hostname verification.
- Truststore trong container/CI giống cấu hình deploy.
- Bind identity được server chấp nhận.
- Referral target có certificate hợp lệ.
- SASL mechanism có thực sự được hỗ trợ/cấu hình.

AD thường cung cấp LDAP qua 389 và LDAPS qua 636; Global Catalog có 3268/3269. OpenLDAP có thể cấu hình StartTLS và/hoặc LDAPS. Đây là port phổ biến, không phải bảo đảm endpoint của mọi tổ chức dùng port mặc định.

Test negative cases:

- Certificate hết hạn.
- Certificate chain không tin cậy.
- Hostname mismatch.
- StartTLS bị server từ chối.
- TLS protocol/cipher không tương thích.
- Service account password sai.
- Bind DN không tồn tại.
- Empty password bị gửi ngoài ý muốn.

Với simple bind, không gửi password rỗng. RFC 4513 định nghĩa unauthenticated simple bind behavior; ứng dụng nên reject credential rỗng trước khi gọi LDAP để tránh bind không xác thực bị hiểu nhầm là thành công.

## 22. Kiểm thử ACL bằng đúng service account

Nhiều integration test chạy bằng root DN hoặc Domain Admin nên mọi attribute đều đọc được. Production thường dùng service account có quyền tối thiểu.

Tạo các test identity:

- Bind identity chỉ được search/read OU nhân viên.
- Identity được đọc uid, cn, mail nhưng không được đọc attribute nhạy cảm.
- Identity có quyền ghi một nhóm attribute nhưng không có quyền đổi DN.
- Identity không được đọc OU khác.
- User bind identity cho authentication nếu ứng dụng dùng per-user bind.

Kiểm tra:

1. Search được trong base được cấp quyền.
2. Search ngoài base bị từ chối hoặc không trả entry theo ACL server.
3. Attribute bị che không được map thành dữ liệu giả.
4. Modify/delete thiếu quyền trả lỗi phù hợp.
5. Không fallback sang root bind khi service account bị từ chối.
6. Log không ghi credential hoặc full diagnostic nhạy cảm.

Nếu ứng dụng dùng service account đọc chung, ACL LDAP chỉ thấy identity của service account. Authorization theo người dùng cuối cần được thực hiện ở tầng ứng dụng.

## 23. Thiết kế test suite theo adapter và fixture riêng

Giữ một bộ **logical fixture** mô tả dữ liệu nghiệp vụ, rồi tạo LDIF riêng cho từng server:

```text
Logical fixture:
- person: uid=linh
- displayName: Linh Nguyen
- email: linh@example.org
- department: Engineering
- directGroup: Developers
- nestedGroup: Engineering
```

OpenLDAP fixture có thể dùng inetOrgPerson, groupOfNames, member và overlay nếu cần memberOf.

AD fixture có thể dùng user, group, sAMAccountName, userPrincipalName, member, memberOf và account flags phù hợp.

Không cố dùng một file LDIF y nguyên cho cả hai server. Việc mapping server-specific là phần cần kiểm thử, không phải điều cần che giấu.

Một layout test source có thể tổ chức theo capability:

```text
src/test/
  java/
    unit/
    ldap-common/
    ldap-openldap/
    ldap-ad/
  resources/
    ldap/
      common/
      openldap/
      ad-ds/
      ad-lds/
```

Cấu trúc chỉ là gợi ý; dùng naming convention phù hợp build hiện tại. Mục tiêu là nhìn vào test name có thể biết suite cần server nào và capability nào.

## 24. Dùng @DataLdapTest đúng mục đích

Spring Boot cung cấp @DataLdapTest để cấu hình test slice cho LDAP: có thể tạo embedded LDAP nếu dependency phù hợp, cấu hình LdapTemplate, scan ODM @Entry và repository.

Điều này hữu ích cho:

- Kiểm tra mapping cơ bản.
- Kiểm tra repository query method.
- Kiểm tra CRUD trên schema test.
- Kiểm tra service query builder với directory nhỏ.

Nhưng embedded LDAP không tự trở thành AD hoặc OpenLDAP thật. Khi test cần server thực, loại embedded auto-configuration và cung cấp ContextSource/connection properties tới server test.

Cấu hình test nên tách theo profile hoặc test class:

```properties
# application-test-openldap.properties
spring.ldap.urls=ldaps://openldap-test.example:636
spring.ldap.base=dc=example,dc=org
spring.ldap.username=cn=app-reader,ou=service,dc=example,dc=org
```

```properties
# application-test-ad.properties
spring.ldap.urls=ldaps://ad-test.example:636
spring.ldap.base=DC=example,DC=org
spring.ldap.username=CN=app-reader,OU=Service Accounts,DC=example,DC=org
```

Đây là cấu hình minh họa; property names và cách bind phụ thuộc Spring Boot/Spring LDAP version, và secret phải đến từ test secret manager/environment, không commit password vào repository.

## 25. Ma trận compatibility tối thiểu

Trước khi release, lập ma trận rõ:

| Behavior | Embedded LDAP | OpenLDAP thật | AD DS/AD LDS thật |
|---|---|---|---|
| ODM DN mapping | Có | Có | Có |
| Schema required attributes | Theo embedded schema | Theo schema được nạp | Theo schema Microsoft/extension |
| Query filter | Filter cơ bản | Matching rule/config thật | AD attributes/OID riêng |
| Group membership | Fixture đơn giản | Group schema/overlay | member, memberOf, primary/nested group |
| Account state | Thường mô phỏng | Ppolicy nếu cấu hình | UAC/computed attributes |
| Binary IDs | Tùy fixture | entryUUID | objectGUID, objectSid |
| Large multivalue | Thường ít | Theo limits | Range retrieval có thể cần |
| Paging | Tùy embedded | Control/config thật | Control và MaxPageSize |
| TLS | Có thể bỏ qua | Cert thật | Cert thật và endpoint AD |
| Referral | Thường không mô phỏng đủ | Cấu hình referral | Naming context/domain topology |
| ACL | Có thể đơn giản | ACL thật | DACL/attribute permissions |
| Replication | Thường không | Syncrepl/topology | Multi-DC/GC topology |

Không đánh dấu pass một cột nếu test chỉ chạy trên embedded LDAP.

## 26. Thu thập diagnostic có thể tái hiện

Khi test fail, ghi lại những thông tin không bí mật:

- Product/version của directory.
- Logical endpoint alias, TLS mode.
- Naming context/base DN đã chuẩn hóa.
- Search scope.
- Filter template đã redact assertion values nhạy cảm.
- Requested attributes.
- Control OID được gửi.
- Bind identity alias/role, không phải password.
- LDAP result code và exception class đã scrub.
- RootDSE capabilities cần thiết.
- Test fixture ID và server profile.
- Thời gian thực hiện, correlation ID.

Không ghi:

- Password hoặc service account secret.
- Raw bind request chứa credential.
- Raw access token.
- Full sensitive DN hoặc user data nếu không cần.
- Toàn bộ directory entry.
- Diagnostic string chưa scrub có thể chứa DN/hostname/username.

Diagnostic phải đủ để phân biệt lỗi schema, ACL, unsupported control, invalid credentials, referral và network/TLS.

## 27. Quy trình chẩn đoán khi embedded pass nhưng server thật fail

Làm theo thứ tự:

1. **Xác nhận endpoint:** product, version, AD DS/AD LDS, OpenLDAP, TLS và naming context.
2. **Đọc RootDSE:** kiểm tra base context, controls và SASL mechanisms cần dùng.
3. **Xác minh bind:** cùng identity/secret policy và TLS; không chạy bằng admin nếu production dùng service account.
4. **Chạy search thủ công:** dùng cùng base, scope, filter và attribute projection bằng ldapsearch hoặc công cụ quản trị tương ứng.
5. **Kiểm tra schema:** objectClass, required attribute, syntax, matching rule và overlay.
6. **Kiểm tra ACL:** từng OU và từng attribute.
7. **Kiểm tra server-specific behavior:** group, account state, range retrieval, paging, referral.
8. **So sánh JNDI/provider config:** referral, timeout, pooling, TLS và controls.
9. **Thu hẹp test:** một entry, một filter, một operation.
10. **Thêm regression test:** chạy trên product/version đã gây lỗi.

Không sửa filter theo phỏng đoán khi chưa xác định lỗi đến từ schema, ACL hay search base.

## 28. Các lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| objectClass=inetOrgPerson không tìm thấy AD user | AD objectClass/schema khác | Dùng filter adapter AD như objectCategory + user nếu đúng schema |
| memberOf rỗng trên OpenLDAP | Overlay chưa bật hoặc không request operational attribute | Kiểm tra memberof overlay và attribute projection |
| memberOf thiếu primary group trên AD | Semantics AD không bao gồm primary group | Kiểm tra primaryGroupID |
| Nested group không được tìm | Query chỉ kiểm tra direct membership | Xác minh rule in-chain hoặc expansion strategy |
| member thiếu giá trị trên AD | Range retrieval | Kiểm tra attribute description member;range=... |
| Search trả sizeLimitExceeded | Search rộng hoặc server limit | Base/filter/index/paging |
| Paged cookie không tiếp tục | Connection mới hoặc cookie hết hạn | Giữ connection và cookie sequence |
| Filter AD OID fail trên OpenLDAP | Matching rule vendor-specific | Dùng adapter theo server |
| Modify bị constraintViolation | Schema MUST/MAY hoặc syntax | Kiểm tra schema và required attrs |
| Modify bị insufficientAccessRights | Service account thiếu ACL | Kiểm tra quyền theo operation/attribute |
| TLS handshake fail | Trust chain, SAN, protocol hoặc endpoint | Kiểm tra certificate và hostname verification |
| Referral loop/timeout | Topology hoặc referral chasing | Kiểm tra referral target và credential |
| GUID mapping sai | Binary byte order bị xử lý như text | Viết adapter binary và round-trip test |
| Password update bị từ chối | AD/OpenLDAP password semantics khác nhau | Dùng password-change adapter theo server |
| Test pass bằng admin, fail production | ACL test không giống runtime | Chạy bằng service account thực tế |

## 29. Bài tập thực hành

Một ứng dụng quản lý nhân viên dùng Spring Data LDAP và tuyên bố hỗ trợ cả OpenLDAP lẫn AD DS. Embedded test hiện đang xanh, nhưng production có lỗi: tìm user được, group membership thiếu, và một số user có quá nhiều group khiến kết quả bị thiếu.

Hãy xây compatibility suite:

1. Tạo logical fixture gồm một user, hai group trực tiếp, một nested group và một group rất lớn.
2. Tạo LDIF/seed riêng cho OpenLDAP và AD DS.
3. Với OpenLDAP, bật memberof overlay nếu ứng dụng cần backlink; test explicit request attribute.
4. Với AD, kiểm tra memberOf, primaryGroupID và nested membership semantics.
5. Tạo test range retrieval cho member vượt ngưỡng server cấu hình.
6. Kiểm tra filter user riêng theo schema từng server.
7. Đọc RootDSE và lưu product/version/capability trong test report.
8. Chạy bằng service account có ACL giống production.
9. Kiểm tra paging control, TLS và referral.
10. Kiểm tra binary identity mapping (objectGUID/entryUUID).
11. Kiểm tra account-state adapter theo từng server.
12. Thêm regression test cho mọi khác biệt đã tìm thấy.

**Câu hỏi tự đánh giá:**

- Vì sao @DataLdapTest xanh không chứng minh AD tương thích?
- Vì sao objectClass=inetOrgPerson không phải filter user portable?
- Tại sao memberOf trên OpenLDAP phụ thuộc overlay?
- Vì sao memberOf AD không bao gồm primary group?
- Khi nào AD range retrieval làm một attribute đa trị bị trả thiếu?
- Vì sao objectGUID không thể map bằng new String(byte[])?
- Vì sao cùng một service account cần được dùng trong integration test?
- Vì sao RootDSE supportedControl hữu ích trước khi test paging?
- Tại sao AD DS, AD LDS và OpenLDAP cần fixture riêng?

## 30. Checklist trước khi phát hành

- [ ] Đã ghi rõ directory product, version, role và topology được hỗ trợ.
- [ ] Đã tách unit, embedded, OpenLDAP và AD compatibility tests.
- [ ] Đã xác minh RootDSE, naming contexts và controls.
- [ ] Fixture được tạo theo schema từng server.
- [ ] Filter user/group được kiểm tra trên server thật.
- [ ] Filter escaping và DN escaping được test riêng.
- [ ] Matching rules vendor-specific nằm trong adapter riêng.
- [ ] Group direct/nested/primary membership có test rõ.
- [ ] OpenLDAP memberof overlay được xác minh nếu cần.
- [ ] AD memberOf và primaryGroupID được xử lý đúng.
- [ ] Account-state adapter không giả định attribute portable.
- [ ] Password change được tách theo server semantics.
- [ ] Binary identity được map và round-trip test.
- [ ] AD multivalued range retrieval được kiểm thử nếu cần.
- [ ] Operational attributes và projection được xác minh.
- [ ] Base DN, naming context và Global Catalog behavior được kiểm thử.
- [ ] Referral chasing được cấu hình và kiểm thử an toàn.
- [ ] Paging, size/time limit và server controls được xác minh.
- [ ] TLS certificate/hostname và bind identity được kiểm tra.
- [ ] ACL test dùng service account giống production.
- [ ] Diagnostic được scrub, không chứa secret/PII không cần thiết.
- [ ] Regression test chạy trên đúng product/version trước release.

### Tài liệu tham khảo

- [Spring Boot — Auto-configured Data LDAP Tests](https://docs.spring.io/spring-boot/4.1/reference/testing/spring-boot-applications.html) — @DataLdapTest, embedded LDAP và cách chuyển sang real LDAP server.
- [Microsoft Learn — objectCategory vs. objectClass](https://learn.microsoft.com/en-us/windows/win32/adsi/objectcategory-vs--objectclass) — semantics và type matching trong Active Directory.
- [Microsoft Learn — Search Filter Syntax](https://learn.microsoft.com/en-us/windows/win32/adsi/search-filter-syntax) — matching rule OID, bitwise filter và in-chain membership.
- [Microsoft Open Specifications — LDAP Matching Rules](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-adts/4e638665-f466-4597-93c4-12f2ebfabab5) — matching rule hỗ trợ theo AD version.
- [Microsoft Open Specifications — Range Retrieval of Attribute Values](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-adts/e27b48db-6f82-44cd-9038-2e54f790cc1f) — cách đọc attribute đa trị theo range.
- [Microsoft Open Specifications — memberOf](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-ada2/cc24555b-61c7-49a2-9748-167b8ce5a512) — primary group không được phản ánh trong memberOf.
- [Microsoft Learn — RootDSE](https://learn.microsoft.com/en-us/windows/win32/adsi/rootdse) — naming context và capability của directory server.
- [OpenLDAP Administrator's Guide — Overlays](https://www.openldap.org/doc/admin24/overlays.html) — memberof, proxy cache và overlay behavior.
- [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511) — LDAP operations, search, controls và result codes.
- [RFC 4514 — LDAP: String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514) — DN string escaping.
- [RFC 4515 — LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515) — filter assertion escaping.

**Kết luận:** embedded LDAP là tầng kiểm thử nhanh cho mapping và query cơ bản. Tương thích AD/OpenLDAP chỉ được chứng minh khi test chạy trên đúng server, schema, overlay, ACL, TLS và topology. Hãy khám phá RootDSE, dùng fixture riêng theo server, viết adapter cho attribute/matching rule đặc thù, kiểm thử group/account/range/paging và chạy bằng service account thực tế. Khi test report ghi rõ product/version và capability, lỗi khác biệt môi trường sẽ dễ tái hiện và xử lý hơn.
