# Phân biệt ADD_ATTRIBUTE, REPLACE_ATTRIBUTE và REMOVE_ATTRIBUTE

## 1. Mục tiêu của bài học

Trong **Spring Data LDAP**, dữ liệu người dùng, nhóm và các đối tượng thư mục được lưu dưới dạng **entry** trong cây LDAP. Mỗi entry có **distinguished name (DN)**, các giá trị `objectClass` và tập **attribute** phải tuân theo schema của directory. Một attribute có thể chứa **một hoặc nhiều giá trị**, khác với cách thường hình dung một cột scalar trong bảng SQL.

Khi ghi dữ liệu bằng **Spring LDAP `LdapTemplate`** hoặc JNDI, ba hằng của `javax.naming.directory.DirContext` quyết định ý nghĩa thay đổi:

- `ADD_ATTRIBUTE`: thêm một attribute hoặc bổ sung những giá trị mới, **không xóa những giá trị hiện có**.
- `REPLACE_ATTRIBUTE`: **thay toàn bộ tập giá trị** của attribute bằng tập giá trị được gửi.
- `REMOVE_ATTRIBUTE`: bỏ các giá trị được chỉ định, hoặc **xóa toàn attribute** nếu không chỉ định giá trị nào.

Ở mức giao thức LDAP (RFC 4511), ba ý nghĩa tương ứng là các phép `add`, `replace` và `delete` **trong một ModifyRequest**. `REMOVE_ATTRIBUTE` không phải thao tác `DeleteRequest` xóa cả entry.

Sau bài này, người học có thể phân biệt kết quả của ba thao tác trên attribute đơn trị và đa trị; viết `ModificationItem[]` để cập nhật entry; hiểu lỗi trùng giá trị, giá trị không tồn tại, schema và ACL; cập nhật thành viên nhóm an toàn; so sánh sửa attribute trực tiếp với `LdapRepository.save`; kiểm thử trạng thái trước/sau trên LDAP server thật.

## 2. Dữ liệu mẫu và một nguyên tắc quan trọng

Giả sử Spring Boot kết nối directory:

```yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
```

Directory có cấu trúc:

```text
dc=example,dc=org                     <- base DN của ContextSource
├── ou=people
│   ├── uid=linh
│   ├── uid=an
│   └── uid=minh
└── ou=groups
    └── cn=developers
```

Entry người dùng:

```ldif
dn: uid=linh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@example.org
description: Nhân viên kỹ thuật
```

Entry nhóm có **nhiều giá trị `member`**:

```ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=linh,ou=people,dc=example,dc=org
member: uid=an,ou=people,dc=example,dc=org
```

**Cảnh báo cốt lõi:** nếu nhóm đang chứa Linh và An mà bạn dùng `REPLACE_ATTRIBUTE` với giá trị `uid=minh,...`, server có thể xóa membership của cả Linh lẫn An. Thao tác đúng để **chỉ thêm Minh** là `ADD_ATTRIBUTE`.

Các DN truyền vào `LdapTemplate` trong ví dụ là DN **tương đối với base**: `uid=linh,ou=people` hoặc `cn=developers,ou=groups`. Nhưng giá trị của `groupOfNames.member` là **DN đầy đủ** như `uid=linh,ou=people,dc=example,dc=org`. Không được cộng lặp base DN trong lời gọi `LdapTemplate`.

## 3. Bảng so sánh ngữ nghĩa

Giả sử một attribute `description` đang có hai giá trị `{A, B}`, schema cho phép đa trị và không có cập nhật đồng thời:

| Mong muốn | JNDI operation | Giá trị gửi | Trạng thái sau ghi |
| --- | --- | --- | --- |
| Thêm một giá trị | `ADD_ATTRIBUTE` | `C` | `{A, B, C}` |
| Thay toàn bộ bằng một giá trị | `REPLACE_ATTRIBUTE` | `C` | `{C}` |
| Thay toàn bộ bằng hai giá trị | `REPLACE_ATTRIBUTE` | `C, D` | `{C, D}` |
| Xóa riêng B | `REMOVE_ATTRIBUTE` | `B` | `{A}` |
| Xóa cả attribute | `REMOVE_ATTRIBUTE` | Không có giá trị | Attribute không còn tồn tại |
| Thay bằng tập rỗng | `REPLACE_ATTRIBUTE` | Không có giá trị | Attribute không còn tồn tại |

Nếu attribute **chưa tồn tại**:

| Thao tác | Kết quả thông thường |
| --- | --- |
| `ADD_ATTRIBUTE` với giá trị hợp lệ | Tạo attribute và thêm giá trị. |
| `REPLACE_ATTRIBUTE` với giá trị hợp lệ | Tạo attribute với tập giá trị mới. |
| `REMOVE_ATTRIBUTE` với một hoặc nhiều giá trị | Server có thể trả lỗi `noSuchAttribute`. |
| `REMOVE_ATTRIBUTE` không có giá trị | Server có thể trả lỗi `noSuchAttribute` vì không có attribute để xóa. |

Nếu attribute đã tồn tại, **ADD trùng giá trị** thường bị từ chối với `attributeOrValueExists`. Nếu **REMOVE một giá trị chưa có**, server thường trả `noSuchAttribute`. Việc hai giá trị có được xem là trùng phụ thuộc vào **matching rule của attribute trong schema**, không chỉ `String.equals` phía Java.

```text
Trước: {A, B}
          |
          +-- ADD C ---------> {A, B, C}
          |
          +-- REPLACE C -----> {C}
          |
          +-- REMOVE B ------> {A}
          |
          +-- REMOVE all ----> không còn attribute
```

Trạng thái “attribute không tồn tại” khác với “attribute chứa chuỗi rỗng”. Tùy schema, chuỗi rỗng có thể không hợp lệ, trong khi request replace/delete với **tập giá trị rỗng** là yêu cầu xóa attribute ở mức LDAP Modify.

## 4. Các lớp Java cần biết

JNDI cung cấp những lớp nền tảng sau:

| API | Package | Nhiệm vụ |
| --- | --- | --- |
| `DirContext` | `javax.naming.directory` | Hằng `ADD_ATTRIBUTE`, `REPLACE_ATTRIBUTE`, `REMOVE_ATTRIBUTE` và `modifyAttributes`. |
| `ModificationItem` | `javax.naming.directory` | Mô tả một thao tác cùng một `Attribute`. |
| `Attribute` | `javax.naming.directory` | Tên attribute và tập giá trị, có thể đa trị. |
| `BasicAttribute` | `javax.naming.directory` | Implementation thường dùng để tạo dữ liệu cho `ModificationItem`. |
| `LdapTemplate` | `org.springframework.ldap.core` | Chạy thao tác trên `ContextSource`, quản lý context và chuyển đổi exception. |
| `LdapNameBuilder` | `org.springframework.ldap.support` | Dựng DN theo RDN, xử lý ký tự đặc biệt an toàn. |

Một yêu cầu cập nhật email bằng JNDI:

```java
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

// ctx là DirContext đã kết nối, có base phù hợp.
ModificationItem[] changes = {
    new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        new BasicAttribute("mail", "linh.new@example.org")
    )
};
ctx.modifyAttributes("uid=linh,ou=people", changes);
```

Tương đương bằng Spring LDAP:

```java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

void updateMail(LdapTemplate template) {
    Name dn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "linh")
        .build();

    ModificationItem item = new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        new BasicAttribute("mail", "linh.new@example.org")
    );
    template.modifyAttributes(dn, new ModificationItem[] {item});
}
```

`new BasicAttribute(...)` chỉ dựng đối tượng Java; không tác động lên LDAP cho đến khi `modifyAttributes(...)` được thực hiện. Giá trị các hằng `DirContext` là chi tiết của API JNDI, **không phải** mã operation byte-level của LDAP; provider có nhiệm vụ ánh xạ đúng chúng.

## 5. ADD_ATTRIBUTE — thêm mà không làm mất giá trị cũ

### 5.1. Thêm một thuộc tính mới

Nếu Linh chưa có `telephoneNumber`:

```java
ModificationItem addPhone = new ModificationItem(
    DirContext.ADD_ATTRIBUTE,
    new BasicAttribute("telephoneNumber", "+84-28-5555-0101")
);
ldapTemplate.modifyAttributes(userDn, new ModificationItem[] {addPhone});
```

Sau khi server chấp nhận, entry có thêm `telephoneNumber`. Nếu attribute đã có giá trị và **cho phép nhiều giá trị**, ADD sẽ bổ sung thay vì thay thế chúng.

Với attribute được định nghĩa `SINGLE-VALUE`, việc ADD giá trị thứ hai có thể bị từ chối. Nên đọc schema LDAP server; không suy ra số lượng giá trị tối đa chỉ từ kiểu `String` của field trong ODM entity.

### 5.2. Thêm một giá trị member vào groupOfNames

Giả sử nhóm `developers` đang có Linh và An; cần thêm Minh mà không ảnh hưởng hai người cũ:

```java
import javax.naming.Name;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.support.LdapNameBuilder;

Name groupDn = LdapNameBuilder.newInstance("ou=groups")
    .add("cn", "developers")
    .build();

Name fullMemberDn = LdapNameBuilder.newInstance("dc=example,dc=org")
    .add("ou", "people")
    .add("uid", "minh")
    .build();

ModificationItem addMember = new ModificationItem(
    DirContext.ADD_ATTRIBUTE,
    new BasicAttribute("member", fullMemberDn.toString())
);
ldapTemplate.modifyAttributes(
    groupDn, new ModificationItem[] {addMember}
);
```

Kết quả mong đợi:

```ldif
dn: cn=developers,ou=groups,dc=example,dc=org
member: uid=linh,ou=people,dc=example,dc=org
member: uid=an,ou=people,dc=example,dc=org
member: uid=minh,ou=people,dc=example,dc=org
```

Nếu `member` đã chứa Minh, server thường báo lỗi `attributeOrValueExists` (LDAP result code `20`); không nên giả định ADD lặp lại sẽ là thao tác rỗng thành công.

### 5.3. Các lỗi có thể gặp với ADD

| Tình huống | Kết quả có thể xảy ra |
| --- | --- |
| Giá trị đã có | `attributeOrValueExists`. |
| Thuộc tính chỉ cho một giá trị nhưng ADD giá trị thứ hai | Vi phạm schema/constraint. |
| Thuộc tính không được object class cho phép | `objectClassViolation` hoặc lỗi schema tương ứng. |
| Tên thuộc tính chưa được định nghĩa | `undefinedAttributeType`. |
| Giá trị không đúng syntax | `invalidAttributeSyntax`. |
| Bind account không được phép sửa | `insufficientAccessRights`. |
| DN entry không tồn tại | `noSuchObject`. |

Các lỗi chính xác có thể khác giữa các server/provider. Không giải quyết lỗi schema bằng cách “thử REPLACE thay ADD” nếu chưa hiểu yêu cầu nghiệp vụ; cách đó có thể xóa dữ liệu cũ.

## 6. REPLACE_ATTRIBUTE — thay *toàn bộ* tập giá trị

### 6.1. Đổi email theo yêu cầu nghiệp vụ

```java
ModificationItem replaceMail = new ModificationItem(
    DirContext.REPLACE_ATTRIBUTE,
    new BasicAttribute("mail", "linh.new@example.org")
);
ldapTemplate.modifyAttributes(
    userDn, new ModificationItem[] {replaceMail}
);
```

Tập giá trị `mail` sau thao tác được thay bằng `{"linh.new@example.org"}`. Nếu trước đó có hai giá trị email, **cả hai đều bị xóa**. Đoạn mã ví dụ muốn giữ một email theo quy tắc ứng dụng; điều này **không đồng nghĩa** LDAP schema của mọi server xác định `mail` là attribute đơn trị.

Khi attribute chưa có, `REPLACE_ATTRIBUTE` với tập giá trị khác rỗng thường tạo attribute mới (nếu schema cho phép).

### 6.2. Thay bằng nhiều giá trị

```java
import javax.naming.directory.Attribute;
import javax.naming.directory.BasicAttribute;

Attribute descriptions = new BasicAttribute("description");
descriptions.add("Đã xác nhận thông tin");
descriptions.add("Phụ trách nhóm kỹ thuật");

ModificationItem replaceDescriptions = new ModificationItem(
    DirContext.REPLACE_ATTRIBUTE, descriptions
);
ldapTemplate.modifyAttributes(
    userDn, new ModificationItem[] {replaceDescriptions}
);
```

Tập `description` cũ bị thay bằng **chính hai giá trị** trong `descriptions`. Các giá trị cũ không có trong yêu cầu sẽ biến mất.

### 6.3. Bẫy với attribute member

Đoạn sau **sai** nếu mục đích là thêm Minh:

```java
// CẢNH BÁO: thay thế tất cả member bằng một người!
ModificationItem wrong = new ModificationItem(
    DirContext.REPLACE_ATTRIBUTE,
    new BasicAttribute(
        "member",
        "uid=minh,ou=people,dc=example,dc=org"
    )
);
ldapTemplate.modifyAttributes(groupDn, new ModificationItem[] {wrong});
```

Khi được server chấp nhận, group sẽ **chỉ còn Minh**. Nếu nghiệp vụ là “thêm đúng một DN”, dùng `ADD_ATTRIBUTE`. Nếu là “gỡ đúng một DN”, dùng `REMOVE_ATTRIBUTE`.

Đặc biệt, không nên đọc tất cả member vào một danh sách Java, thêm người mới rồi `REPLACE_ATTRIBUTE` toàn bộ danh sách trong hệ có nhiều client cùng sửa: dữ liệu người khác vừa thêm có thể bị ghi đè (*lost update*).

### 6.4. REPLACE với tập giá trị rỗng

Theo LDAP Modify, replace một attribute bằng **không giá trị** có nghĩa **xóa attribute**:

```java
ModificationItem clearDescription = new ModificationItem(
    DirContext.REPLACE_ATTRIBUTE,
    new BasicAttribute("description") // không có value
);
ldapTemplate.modifyAttributes(
    userDn, new ModificationItem[] {clearDescription}
);
```

Đây **không phải** cách gán chuỗi rỗng `""`. Với attribute bắt buộc như `cn` hoặc `sn` của `person`, request này thường bị schema từ chối vì sẽ khiến entry không hợp lệ.

## 7. REMOVE_ATTRIBUTE — xóa một số giá trị hoặc cả attribute

### 7.1. Xóa một giá trị cụ thể

Nhóm `developers` đang có Linh, An và Minh; cần gỡ riêng Minh:

```java
ModificationItem removeMember = new ModificationItem(
    DirContext.REMOVE_ATTRIBUTE,
    new BasicAttribute(
        "member",
        "uid=minh,ou=people,dc=example,dc=org"
    )
);
ldapTemplate.modifyAttributes(
    groupDn, new ModificationItem[] {removeMember}
);
```

Chỉ giá trị tương ứng với DN Minh bị xóa; giá trị của Linh và An được giữ lại. Dùng `REMOVE_ATTRIBUTE` với một giá trị là lựa chọn đúng cho nghiệp vụ “thu hồi membership của một người”.

### 7.2. Xóa toàn bộ một thuộc tính

```java
ModificationItem removeAllDescriptions = new ModificationItem(
    DirContext.REMOVE_ATTRIBUTE,
    new BasicAttribute("description") // không có value
);
ldapTemplate.modifyAttributes(
    userDn, new ModificationItem[] {removeAllDescriptions}
);
```

Theo LDAP Modify, **REMOVE không chỉ định value** nghĩa là **xóa toàn attribute**. Nếu attribute không tồn tại, server có thể báo `noSuchAttribute`. Nếu attribute bắt buộc theo schema, việc xóa cũng có thể bị từ chối.

### 7.3. Gỡ giá trị không tồn tại

Nếu nhóm hiện không còn Minh, yêu cầu REMOVE DN Minh không được giao thức bảo đảm là no-op. Server thường báo `noSuchAttribute` (result code `16`).

Để triển khai chức năng “đảm bảo người này không thuộc nhóm”, service có thể:

1. Đọc/kiểm tra membership hiện tại.
2. Nếu chưa có, coi trạng thái nghiệp vụ đã đạt.
3. Nếu có, gửi REMOVE cho đúng DN.
4. Nếu mất kết nối sau yêu cầu, đọc lại trạng thái trước khi retry.

**Read-before-write không cung cấp isolation**: request khác có thể sửa nhóm ngay sau bước đọc. Với hệ nhiều client, phải phân tích điều kiện tranh chấp và quyền ghi.

### 7.4. Cẩn thận với giá trị cuối cùng của group

Theo schema `groupOfNames`, attribute `member` là bắt buộc. Nếu cố xóa **thành viên cuối** mà để entry không còn `member`, server có thể trả `objectClassViolation`. Một số loại nhóm hoặc schema riêng có thể cho phép nhóm rỗng, nhưng không được giả định điều đó cho mọi LDAP directory.

## 8. Chọn thao tác đúng theo yêu cầu nghiệp vụ

| Nhu cầu | Thao tác phù hợp | Lý do |
| --- | --- | --- |
| Bổ sung số điện thoại, giữ số cũ (nếu đa trị) | `ADD_ATTRIBUTE` | Không đụng các giá trị hiện có. |
| Đổi toàn bộ tập số điện thoại | `REPLACE_ATTRIBUTE` | Đưa về tập giá trị mới. |
| Gỡ riêng một số điện thoại | `REMOVE_ATTRIBUTE` + value | Giữ các số khác. |
| Thêm một user vào nhóm | `ADD_ATTRIBUTE` + DN user | Giữ các member cũ. |
| Gỡ một user khỏi nhóm | `REMOVE_ATTRIBUTE` + DN user | Chỉ bỏ membership mục tiêu. |
| Đặt lại tất cả member theo danh sách chuẩn | `REPLACE_ATTRIBUTE` + các DN | Có chủ đích thay toàn bộ; cần kiểm soát đồng thời. |
| Bỏ thuộc tính tùy chọn | `REMOVE_ATTRIBUTE` không value | Xóa toàn attribute. |
| Bỏ thuộc tính bằng replace rỗng | `REPLACE_ATTRIBUTE` không value | Cũng xóa attribute theo LDAP Modify. |
| Xóa toàn bộ người dùng/entry | `LdapTemplate.unbind` hoặc repository delete | Không dùng `REMOVE_ATTRIBUTE`. |

**Quy tắc thiết kế:** khi bài toán chỉ thay đổi **một giá trị trong một tập đa trị**, hãy dùng ADD/REMOVE đúng giá trị thay vì REPLACE toàn tập.

## 9. Triển khai service Spring LDAP

Đây là ví dụ có thể đặt trong project Spring Boot dùng Java 17 và `spring-boot-starter-data-ldap`. `ContextSource` được cấu hình với base `dc=example,dc=org`:

```java
package com.example.directory;

import java.util.Objects;
import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class DirectoryAttributeService {
    private final LdapTemplate ldapTemplate;

    public DirectoryAttributeService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    private Name userDn(String uid) {
        return LdapNameBuilder.newInstance("ou=people")
            .add("uid", Objects.requireNonNull(uid))
            .build();
    }

    private Name groupDn(String cn) {
        return LdapNameBuilder.newInstance("ou=groups")
            .add("cn", Objects.requireNonNull(cn))
            .build();
    }

    private Name fullUserDn(String uid) {
        return LdapNameBuilder.newInstance("dc=example,dc=org")
            .add("ou", "people")
            .add("uid", Objects.requireNonNull(uid))
            .build();
    }

    public void addPhone(String uid, String phone) {
        modify(userDn(uid), DirContext.ADD_ATTRIBUTE,
            new BasicAttribute("telephoneNumber", phone));
    }

    public void replaceMail(String uid, String email) {
        modify(userDn(uid), DirContext.REPLACE_ATTRIBUTE,
            new BasicAttribute("mail", email));
    }

    public void removePhone(String uid, String phone) {
        modify(userDn(uid), DirContext.REMOVE_ATTRIBUTE,
            new BasicAttribute("telephoneNumber", phone));
    }

    public void removeAllDescriptions(String uid) {
        modify(userDn(uid), DirContext.REMOVE_ATTRIBUTE,
            new BasicAttribute("description"));
    }

    public void addGroupMember(String group, String uid) {
        modify(groupDn(group), DirContext.ADD_ATTRIBUTE,
            new BasicAttribute("member", fullUserDn(uid).toString()));
    }

    public void removeGroupMember(String group, String uid) {
        modify(groupDn(group), DirContext.REMOVE_ATTRIBUTE,
            new BasicAttribute("member", fullUserDn(uid).toString()));
    }

    private void modify(Name dn, int operation, Attribute values) {
        ModificationItem item = new ModificationItem(operation, values);
        ldapTemplate.modifyAttributes(dn, new ModificationItem[] {item});
    }
}
```

Lưu ý:

- Các method của service chọn **mã operation cố định theo nghiệp vụ**, không nhận tùy ý tên attribute/mã operation từ HTTP client.
- `userDn` và `groupDn` là DN tương đối với base của `ContextSource`. `fullUserDn` chỉ được dùng làm **giá trị attribute `member`** trong ví dụ.
- `Objects.requireNonNull` chỉ chặn null, **không** thay thế validation độ dài, format, tên UID, email/phone hay quyền người gọi.
- Thao tác này chỉ sửa entry **đã tồn tại**; nó không tạo user/group mới. Nếu DN không tồn tại, cần xử lý lỗi thay vì tự động tạo entry.
- Trong production, dùng LDAPS/StartTLS và xác minh chứng chỉ, bind account quyền tối thiểu, không log secret/giá trị nhạy cảm.

### 9.1. Gộp nhiều thay đổi trong một ModifyRequest

Để thay email và thêm điện thoại trong cùng một request LDAP của một user:

```java
ModificationItem[] changes = {
    new ModificationItem(
        DirContext.REPLACE_ATTRIBUTE,
        new BasicAttribute("mail", "linh.new@example.org")
    ),
    new ModificationItem(
        DirContext.ADD_ATTRIBUTE,
        new BasicAttribute("telephoneNumber", "+84-28-5555-0101")
    )
};
ldapTemplate.modifyAttributes(userDn, changes);
```

**Theo RFC 4511, các thay đổi trong một LDAP ModifyRequest được áp dụng theo thứ tự và như một thao tác nguyên tử trên entry đó.** Nếu một thay đổi bị server từ chối, toàn bộ request phải thất bại; không chấp nhận tình trạng chỉ áp dụng một nửa danh sách.

Ngược lại, **hai lời gọi `modifyAttributes(...)` riêng biệt** không tạo transaction ACID xuyên nhiều request; thao tác đầu tiên có thể đã ghi xong trước khi thao tác thứ hai lỗi. `@Transactional` JDBC cũng không tự rollback LDAP.

### 9.2. Thứ tự thay đổi có ý nghĩa

Với cùng attribute, thứ tự `ADD`, `REMOVE`, `REPLACE` trong một request có thể ảnh hưởng tới kết quả hoặc việc server chấp nhận. Nếu muốn thay toàn bộ tập một cách rõ ràng, `REPLACE_ATTRIBUTE` thường diễn đạt đúng hơn tổ hợp remove/add. Nhưng nếu chỉ thêm/gỡ một thành viên, **không** dùng REPLACE thay cho ADD/REMOVE.

## 10. Phân biệt với ODM và LDAP Repository

Spring Data LDAP cung cấp ODM:

```java
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
public class DirectoryPerson {
    @Id
    private Name dn;

    @DnAttribute(value = "uid", index = 0)
    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String email;

    public DirectoryPerson() {}
    // Bổ sung getters/setters trong project thực tế.
}
```

Repository:

```java
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {
    Optional<DirectoryPerson> findByUid(String uid);
}
```

Gọi `repository.findByUid("linh")` rồi sửa `email` và `repository.save(person)` phù hợp với CRUD **entity**. Tuy nhiên, không nên mặc định một lần `save` trên entity chứa danh sách member sẽ tự biết chỉ gửi `ADD_ATTRIBUTE` cho một DN mà không ảnh hưởng những giá trị khác. Cần hiểu mapping và cách framework xử lý thay đổi.

| `LdapRepository.save(entity)` | `LdapTemplate.modifyAttributes(dn, changes)` |
| --- | --- |
| Làm việc với object Java do ODM ánh xạ. | Làm việc trực tiếp với một hay nhiều `ModificationItem`. |
| Ít code khi CRUD người dùng hoặc metadata đơn giản. | Kiểm soát chính xác loại thay đổi và các giá trị liên quan. |
| Định danh bằng `@Id Name` và `@DnAttribute`. | Tự xác định DN đích, thường bằng `LdapNameBuilder`. |
| Cần cân nhắc mapping field nhiều giá trị. | Phù hợp ADD/REMOVE một giá trị trong attribute đa trị. |
| Không tự tạo transaction ACID giữa nhiều entry. | Một ModifyRequest nguyên tử trên entry đích, không bao trùm request khác. |

Spring LDAP cũng cung cấp `DirContextOperations` để làm việc với entry và các thay đổi:

```java
import javax.naming.Name;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;

void updateEmail(LdapTemplate template, Name dn, String newMail) {
    DirContextOperations entry = template.lookupContext(dn);
    entry.setAttributeValue("mail", newMail);
    template.modifyAttributes(entry);
}
```

`DirContextOperations` không phải `javax.naming.directory.DirContext` thuần; nó là abstraction Spring giúp truy cập thuộc tính và ghi nhận thay đổi. Khi yêu cầu chính xác “chỉ thêm/gỡ một giá trị” trong group hoặc attribute đa trị, dùng `ModificationItem[]` tường minh thường dễ kiểm soát.

## 11. Lỗi server, xử lý ngoại lệ và retry

| Trường hợp | LDAP result code thường gặp | Nguyên nhân/hướng xử lý |
| --- | --- | --- |
| `ADD` trùng giá trị | `20 — attributeOrValueExists` | Kiểm tra dữ liệu, không retry vô hạn. |
| `REMOVE` giá trị không có | `16 — noSuchAttribute` | Kiểm tra trạng thái hiện tại và ý định nghiệp vụ. |
| Xóa `cn`/`sn` bắt buộc | `65 — objectClassViolation` | Schema yêu cầu attribute; không được xóa tùy tiện. |
| Attribute chưa được định nghĩa | `17 — undefinedAttributeType` | Kiểm tra tên attribute và schema. |
| Giá trị sai cú pháp | `21 — invalidAttributeSyntax` | Kiểm tra định dạng theo server. |
| Vi phạm constraint | `19 — constraintViolation` | Kiểm tra single-valued, matching rule và ràng buộc. |
| Bind account thiếu quyền sửa | `50 — insufficientAccessRights` | Kiểm tra ACL đúng account, không tự nâng quyền. |
| DN không tồn tại | `32 — noSuchObject` | Kiểm tra base DN, RDN và entry đã tạo chưa. |
| Mất kết nối khi modify | Có thể không có result code | Xác minh server đã thực hiện thao tác chưa rồi mới retry. |

JNDI có thể ném các exception như `javax.naming.directory.AttributeInUseException`, `javax.naming.directory.NoSuchAttributeException` hoặc `javax.naming.directory.SchemaViolationException`. `LdapTemplate` thường chuyển checked `javax.naming.NamingException` thành runtime exception trong hệ `org.springframework.ldap`. Vì vậy, khi catch lỗi từ Spring LDAP phải quan tâm **package** và chuỗi `cause`, không chỉ tên lớp đơn giản.

Ví dụ:

```java
try {
    ldapTemplate.modifyAttributes(dn, changes);
} catch (org.springframework.ldap.NoPermissionException ex) {
    // Lỗi quyền truy cập, không phải user không tồn tại.
    throw ex;
} catch (org.springframework.ldap.CommunicationException ex) {
    // Server có thể đã thực hiện thao tác trước khi mất phản hồi.
    throw ex;
} catch (org.springframework.ldap.NamingException ex) {
    // Giữ nguyên cause để điều tra lỗi schema/giá trị.
    throw ex;
}
```

### Retry và idempotency

`ADD_ATTRIBUTE`/`REMOVE_ATTRIBUTE` không nhất thiết idempotent về mặt phản hồi:

- ADD lần hai có thể báo trùng sau khi lần đầu thực ra đã thành công.
- REMOVE lần hai có thể báo không có giá trị sau khi lần đầu đã xóa.
- REPLACE cùng tập giá trị có thể cho cùng trạng thái cuối, nhưng **không an toàn khi có cập nhật đồng thời** nếu ghi đè thay đổi mới của người khác.

Khi mạng hoặc TLS lỗi ngay sau `modifyAttributes`, không kết luận request chắc chắn thất bại. Kiểm tra lại trạng thái LDAP với quyền đọc phù hợp; dùng retry có giới hạn và đối soát theo **trạng thái nghiệp vụ mong muốn** thay vì lặp vô hạn cùng operation.

## 12. Đồng thời, atomicity và bảo toàn dữ liệu

### 12.1. Một ModifyRequest khác với nhiều lời gọi modify

```text
modifyAttributes(userDn, [
    REPLACE mail,
    ADD telephoneNumber
])
        |
        +-- một LDAP ModifyRequest: nguyên tử trên entry đó

modifyAttributes(userDn, [REPLACE mail]);  // request 1
modifyAttributes(groupDn, [ADD member]);   // request 2
        |
        +-- KHÔNG có atomicity/rollback mặc định xuyên hai request
```

Ngay cả khi hai `ModificationItem` nằm trong cùng request, đừng suy diễn rằng transaction đó bao gồm SQL hoặc HTTP call. Các nghiệp vụ cập nhật người dùng rồi cập nhật nhóm có thể cần cơ chế bù trừ hoặc phục hồi nếu một bước đã thành công mà bước còn lại lỗi.

### 12.2. Rủi ro lost update của REPLACE_ATTRIBUTE

```text
Ban đầu: member = {Linh, An}

A đọc tập {Linh, An}, dự định gỡ An
B ADD member Minh          -> {Linh, An, Minh}
A REPLACE bằng {Linh}      -> {Linh}

Minh bị mất dù yêu cầu A chỉ muốn gỡ An.
```

Để chỉ gỡ An, A nên gửi `REMOVE_ATTRIBUTE(member, DN_An)`. Cách này tránh việc ghi đè nguyên tập do đã đọc cũ, nhưng vẫn phải tính tới quyền, schema, các request khác và trạng thái cuối sau lỗi.

Khi cần cập nhật có điều kiện kiểu “chỉ ghi nếu không ai sửa từ lúc đọc”, phải đánh giá LDAP controls hoặc cơ chế kiểm tra/serialization được **server cụ thể** hỗ trợ. `ModificationItem[]` không tự mang lại mức isolation như transaction SQL.

## 13. Kiểm thử trên một directory thật

Unit test có thể kiểm tra rằng service gửi đúng `ModificationItem[]`. Để chứng minh server thực sự thêm/xóa/thay thế giá trị, cần integration test trên LDAP server test có base `dc=example,dc=org`, nhánh `ou=people` và schema `inetOrgPerson`. Không chạy bài tập sửa/xóa này trên directory production.

### Ma trận test

| Dữ liệu trước | Thao tác | Kỳ vọng sau |
| --- | --- | --- |
| Không có `description` | ADD A | `{A}` |
| `description={A}` | ADD B | `{A,B}` |
| `description={A,B}` | ADD A | Lỗi trùng, trạng thái vẫn `{A,B}` |
| `description={A,B}` | REPLACE C | `{C}` |
| `description={A,B}` | REMOVE B | `{A}` |
| `description={A}` | REMOVE không giá trị | Không còn attribute |
| `description={A}` | REPLACE không giá trị | Không còn attribute |
| `description={A}` | REMOVE B | Server báo thiếu giá trị |
| `member={Linh,An}` | ADD Minh | Còn Linh, An và Minh |
| `member={Linh,An,Minh}` | REMOVE An | Còn Linh và Minh |
| `member={Linh,An}` | REPLACE Minh | Chỉ còn Minh |
| Entry `person` hợp lệ | REMOVE `sn` | Bị schema từ chối |
| Entry hợp lệ | Một ModifyRequest gồm REPLACE mail và ADD giá trị bị trùng | Toàn request thất bại; không sửa mail |

### Ví dụ integration test (JUnit 5)

Code dưới đây giả định kết nối tới directory test đã được cấu hình và `ou=people` tồn tại. Test tạo một UID ngẫu nhiên, kiểm chứng ADD/REMOVE/REPLACE rồi dọn entry.

```java
package com.example.directory;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import javax.naming.Name;
import javax.naming.NamingEnumeration;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

@SpringBootTest
class AttributeModificationIT {
    @Autowired private LdapTemplate ldap;

    @Test
    void addReplaceRemoveDescriptions() {
        String uid = "lab" + UUID.randomUUID().toString()
            .replace("-", "").substring(0, 10);
        Name dn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", uid).build();

        Attributes attrs = new BasicAttributes(true);
        Attribute classes = new BasicAttribute("objectClass");
        classes.add("top");
        classes.add("person");
        classes.add("organizationalPerson");
        classes.add("inetOrgPerson");
        attrs.put(classes);
        attrs.put("uid", uid);
        attrs.put("cn", "Test " + uid);
        attrs.put("sn", "Test");

        boolean created = false;
        try {
            ldap.bind(dn, null, attrs);
            created = true;

            apply(dn, DirContext.ADD_ATTRIBUTE,
                new BasicAttribute("description", "A"));
            apply(dn, DirContext.ADD_ATTRIBUTE,
                new BasicAttribute("description", "B"));
            assertThat(descriptions(dn))
                .containsExactlyInAnyOrder("A", "B");

            apply(dn, DirContext.REMOVE_ATTRIBUTE,
                new BasicAttribute("description", "B"));
            assertThat(descriptions(dn)).containsExactly("A");

            apply(dn, DirContext.REPLACE_ATTRIBUTE,
                new BasicAttribute("description", "C"));
            assertThat(descriptions(dn)).containsExactly("C");

            apply(dn, DirContext.REMOVE_ATTRIBUTE,
                new BasicAttribute("description"));
            assertThat(descriptions(dn)).isEmpty();
        } finally {
            if (created) {
                ldap.unbind(dn);
            }
        }
    }

    private void apply(Name dn, int operation, Attribute value) {
        ldap.modifyAttributes(dn, new ModificationItem[] {
            new ModificationItem(operation, value)
        });
    }

    private List<String> descriptions(Name dn) {
        return ldap.lookup(dn,
            (AttributesMapper<List<String>>) attrs -> {
                List<String> result = new ArrayList<>();
                Attribute attr = attrs.get("description");
                if (attr == null) return result;

                NamingEnumeration<?> values = attr.getAll();
                try {
                    while (values.hasMore()) {
                        result.add((String) values.next());
                    }
                } finally {
                    values.close();
                }
                return result;
            });
    }
}
```

Khi chạy test, cần bind account có quyền CRUD, OU và schema phù hợp. Nếu LDAP server mất kết nối ngay khi cleanup, entry test có thể còn sót lại: phải kiểm tra và dọn thủ công trên directory test. Đoạn ví dụ là tài liệu hướng dẫn, chưa được biên dịch/chạy trong bước biên soạn.

### Đối chiếu bằng ldapsearch

```bash
ldapsearch -x \
  -H "ldaps://ldap.example.org:636" \
  -D "cn=test-reader,dc=example,dc=org" -W \
  -b "uid=linh,ou=people,dc=example,dc=org" -s base \
  "(objectClass=*)" description mail telephoneNumber
```

`ldapsearch -b` ở đây nhận DN **đầy đủ**, còn `LdapTemplate` trong ví dụ nhận DN tương đối khi `ContextSource` có `base=dc=example,dc=org`. Đừng lặp base khi debug lỗi `NameNotFoundException`.

## 14. An toàn đầu vào và bảo mật ghi

Một API cho phép client truyền tùy ý tên LDAP attribute và mã `ADD`/`REPLACE`/`REMOVE` là rủi ro: client có thể tìm cách sửa `objectClass`, membership nhạy cảm hoặc các thuộc tính không được phép. Thay vào đó, xây endpoint theo nghiệp vụ đã phê duyệt:

```text
PATCH  /users/{uid}/mail               -> REPLACE mail
POST   /users/{uid}/phone-numbers      -> ADD một telephoneNumber
DELETE /users/{uid}/phone-numbers/...  -> REMOVE một telephoneNumber
POST   /groups/{group}/members         -> ADD một DN vào member
DELETE /groups/{group}/members/{uid}   -> REMOVE một DN trong member
```

Tất cả endpoint cần xác thực, phân quyền, validation và giới hạn kích thước dữ liệu. Với DN, dùng `LdapNameBuilder` để escape RDN từ input; với truy vấn tìm kiếm, dùng `LdapQueryBuilder` để escape **LDAP filter**. Hai quy tắc escape không giống nhau.

```java
import static org.springframework.ldap.query.LdapQueryBuilder.query;

var findUid = query()
    .base("ou=people")
    .where("uid").is(userInput);
```

Không ghép filter bằng `"(uid=" + userInput + ")"`. Không ghi secret, toàn bộ DN nhạy cảm hoặc giá trị attribute cá nhân vào log không kiểm soát. Sử dụng LDAPS/StartTLS, xác minh chứng chỉ và tài khoản bind có quyền tối thiểu trên OU và attribute cần sửa.

### Checklist trước khi thực hiện thao tác ghi

- [ ] Đã xác định đúng entry DN và base DN.
- [ ] Đã đọc schema để biết attribute là đơn trị hay đa trị.
- [ ] Nếu chỉ muốn thêm một giá trị, đã chọn `ADD_ATTRIBUTE`.
- [ ] Nếu chỉ muốn xóa một giá trị, đã chọn `REMOVE_ATTRIBUTE` kèm chính giá trị đó.
- [ ] Nếu chọn `REPLACE_ATTRIBUTE`, đã chấp nhận việc **mọi giá trị cũ** bị thay thế.
- [ ] Nếu REMOVE/REPLACE không có value, đã hiểu nó có thể xóa **cả attribute**.
- [ ] Không xóa attribute bắt buộc bởi `objectClass`.
- [ ] Có xử lý lỗi trùng, thiếu giá trị, ACL, schema và mất kết nối.
- [ ] Có chiến lược kiểm tra sau lỗi/đồng thời và integration test trên directory riêng.

## 15. Bài tập thực hành

1. Cho `description={A,B,C}`. Viết `ModificationItem` để (a) thêm D, (b) gỡ B, (c) thay toàn bộ bằng `{X,Y}`, (d) xóa attribute. Dự đoán trạng thái sau từng thao tác.
2. Nhóm đang chứa Linh và An. Minh muốn tham gia, nhưng code dùng `REPLACE_ATTRIBUTE(member, DN_Minh)`. Hãy mô tả lỗi nghiệp vụ và viết lệnh đúng.
3. Giải thích khác biệt giữa `REMOVE_ATTRIBUTE(member, DN_Linh)` và `REMOVE_ATTRIBUTE(new BasicAttribute("member"))`.
4. Vì sao `REPLACE_ATTRIBUTE` với `new BasicAttribute("description")` không mang nghĩa “gán description thành chuỗi rỗng”?
5. Mô phỏng việc gọi ADD hai lần cho cùng một số điện thoại, đối chiếu ngoại lệ thực tế từ LDAP server và hướng xử lý retry.
6. Đặt trong cùng một `ModifyRequest` hai thay đổi: REPLACE `mail` và ADD một giá trị đã trùng. Kiểm chứng request bị từ chối nguyên tử, không để mail bị cập nhật một phần.
7. Dùng ODM/`LdapRepository` cập nhật `mail`, rồi dùng `LdapTemplate` chỉ thêm một giá trị `telephoneNumber`. So sánh mức kiểm soát thao tác.
8. Minh họa lost update khi A dùng REPLACE toàn bộ `member` còn B thêm membership bằng ADD trong lúc A đang xử lý.

## 16. Tài liệu tham khảo

- [RFC 4511 — Lightweight Directory Access Protocol (LDAP): The Protocol](https://www.rfc-editor.org/rfc/rfc4511): `Modify Operation`, add/delete/replace và nguyên tử của một request.
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): attribute, schema, single/multi-valued và `objectClass`.
- [Java SE 17 — DirContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/DirContext.html): ba hằng sửa attribute và `modifyAttributes`.
- [Java SE 17 — ModificationItem](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/ModificationItem.html): biểu diễn một thay đổi.
- [Java SE 17 — BasicAttribute](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/BasicAttribute.html): xây các giá trị attribute.
- [Spring LDAP — Reference](https://docs.spring.io/spring-ldap/reference/): `LdapTemplate`, `DirContextOperations`, xử lý DN và exception.
- [Spring Data LDAP — Reference](https://docs.spring.io/spring-data/ldap/reference/): ODM, `LdapRepository` và CRUD.
- [RFC 4514 — DN String Representation](https://www.rfc-editor.org/rfc/rfc4514) và [RFC 4515 — LDAP Filter String Representation](https://www.rfc-editor.org/rfc/rfc4515): phân biệt escaping DN và filter.
