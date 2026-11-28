# Thay đổi trường @DnAttribute và hành vi cập nhật ODM

Một entry LDAP được nhận diện bằng **Distinguished Name (DN)**, không phải bằng một khóa số như bản ghi trong cơ sở dữ liệu quan hệ. Khi Java entity dùng `@DnAttribute` để đưa một trường vào DN, thay đổi trường đó có thể **thay đổi vị trí hoặc tên của entry trong cây LDAP**, chứ không chỉ sửa một thuộc tính bình thường.

Điểm đáng chú ý trong **Spring LDAP Object-Directory Mapping (ODM)** là phương thức `LdapTemplate.update(Object)` có hai nhánh xử lý khác nhau:

- Nếu DN của entity **không thay đổi**, ODM đọc trạng thái hiện có rồi tính các thay đổi thuộc tính để gọi `modifyAttributes`.
- Nếu DN **được tính lại khác với `@Id` cũ**, tài liệu API mô tả hành vi **`unbind` entry cũ rồi `bind` entry mới**, không phải một thao tác LDAP Modify DN nguyên tử.

Điều này ảnh hưởng trực tiếp đến độ an toàn của chức năng đổi username, chuyển OU và sửa dữ liệu được các nhóm tham chiếu.

Bài học thuộc chương **Đổi tên và di chuyển** của mô-đun `SPRING_DATA_LDAP`. Bạn sẽ xem sự tương tác giữa `@Entry(base)`, `@DnAttribute`, `@Id`, Spring Data LDAP repository, `LdapTemplate` và LDAP server; so sánh cập nhật ODM với thao tác `rename` tường minh; rồi kiểm thử dữ liệu, schema, ACL và tính nhất quán của các DN tham chiếu.

## 1. Mục tiêu

Sau bài học, bạn có thể:

1. Phân biệt **thay đổi thuộc tính** và **thay đổi DN/RDN** trong LDAP.
2. Giải thích vai trò của `@Entry(base)`, `@Id`, `@DnAttribute(index=...)`, `@Attribute` và `@Transient` khi ODM ánh xạ entry.
3. Dự đoán khi nào `LdapTemplate.update(entity)` dùng `modifyAttributes`, khi nào đi vào nhánh **unbind/bind**.
4. Hiểu vì sao thay đổi `@DnAttribute` có thể gây mất dữ liệu/tham chiếu nếu áp dụng không kiểm soát.
5. Sử dụng `LdapTemplate.rename(oldDn, newDn)` khi muốn yêu cầu LDAP Modify DN một cách tường minh.
6. Thiết kế use case đổi username/chuyển OU với validation, phân quyền, kiểm tra tên đích, kiểm tra nhóm và audit.
7. Xây kiểm thử tích hợp chứng minh DN thật trên LDAP đã thay đổi đúng, không chỉ kiểm tra field Java.
8. Phân biệt khả năng của ODM với khả năng và giới hạn riêng của directory server.

## 2. Bối cảnh: một nhân viên và một nhóm

Giả sử directory có cây:

~~~text
dc=example,dc=org
├── ou=people
│   ├── uid=lan
│   └── uid=minh
├── ou=staff
└── ou=groups
    └── cn=engineering
~~~

Entry Lan ban đầu:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Nguyen Thi Lan
sn: Nguyen
mail: lan@example.org
title: Backend Developer
~~~

Nhóm tham chiếu Lan bằng DN đầy đủ:

~~~ldif
dn: cn=engineering,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: engineering
member: uid=lan,ou=people,dc=example,dc=org
member: uid=minh,ou=people,dc=example,dc=org
~~~

Bài toán đặt ra:

- **Sửa chức danh** từ `Backend Developer` thành `Senior Backend Developer`: DN **không đổi**.
- **Đổi username** từ `lan` thành `lan.nguyen`: RDN thay đổi từ `uid=lan` sang `uid=lan.nguyen`.
- **Chuyển OU** từ `ou=people` sang `ou=staff`: parent DN thay đổi.
- Trong cả hai trường hợp đổi DN, giá trị `member` trong nhóm có thể vẫn trỏ tới **DN cũ** nếu server không có cơ chế cập nhật tham chiếu.

Một ứng dụng Java chỉ quan sát `person.getUid()` sẽ không nắm được toàn bộ hệ quả này.

## 3. Phân biệt RDN, DN, thuộc tính và base

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| `spring.ldap.base` | `dc=example,dc=org` | Gốc của các thao tác tương đối qua `ContextSource`. |
| `@Entry(base)` | `ou=people` | Gốc của loại entity khi ODM **tính DN**. |
| RDN | `uid=lan` | Thành phần định danh trực tiếp dưới entry cha. |
| DN tương đối với context | `uid=lan,ou=people` | Thường là `Name` mà `LdapTemplate` dùng trong cấu hình đã đặt base. |
| DN đầy đủ | `uid=lan,ou=people,dc=example,dc=org` | Tên phân biệt trong toàn bộ directory. |
| `uid` là thuộc tính entry | `uid: lan` | Giá trị thuộc tính LDAP; có thể đồng thời được chọn làm RDN. |
| `@Id Name` | `uid=lan,ou=people` | Danh tính của entity được ánh xạ, không phải khóa tự tăng. |

Với ví dụ:

~~~text
uid=lan,ou=people,dc=example,dc=org
  │         │           │
  │         │           └── ContextSource base
  │         └────────────── @Entry(base)
  └──────────────────────── RDN từ @DnAttribute(uid)
~~~

**RDN được đặt bên trái DN**, parent nằm về bên phải. Việc thay `uid` trong một entry có RDN `uid=lan` không đồng nghĩa server sẽ tự đổi tên entry, nếu chỉ gửi LDAP Modify thuộc tính. Với LDAP, thay tên thường cần **Modify DN** hoặc một cơ chế ODM được thiết kế để chuyển entry.

## 4. Mapping đúng vai trò các annotation

Ví dụ Spring Boot đã kết nối tới directory bằng `spring.ldap.base=dc=example,dc=org`:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
    base: dc=example,dc=org
    username: cn=svc-directory-writer,ou=service,dc=example,dc=org
    password: "${LDAP_BIND_PASSWORD}"
~~~

Cấu hình LDAP phải đi cùng TLS hợp lệ và ACL đủ để thực hiện các thao tác ghi đã được phê duyệt.

### 4.1. Entity người dùng một RDN

`DirectoryPerson.java`:

~~~java
package com.example.directory.model;

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

    @Attribute(name = "title")
    private String title;

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }

    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }

    public String getCommonName() { return commonName; }
    public void setCommonName(String commonName) {
        this.commonName = commonName;
    }

    public String getSurname() { return surname; }
    public void setSurname(String surname) {
        this.surname = surname;
    }

    public String getEmail() { return email; }
    public void setEmail(String email) {
        this.email = email;
    }

    public String getTitle() { return title; }
    public void setTitle(String title) {
        this.title = title;
    }
}
~~~

Ở đây:

- `@Entry` mô tả tập `objectClass` và `base` của entity.
- `@Id` chứa DN của entry. Trường này phải có kiểu dẫn xuất từ `javax.naming.Name`.
- `@DnAttribute` đọc thành phần `uid` từ DN và tham gia **tính DN** khi đã khai báo `index`.
- `@Attribute(name="uid")` bảo đảm `uid` cũng là thuộc tính directory, không chỉ nằm trong tên.
- `cn` và `sn` là thuộc tính bắt buộc do `inetOrgPerson` kế thừa từ `person`.

**Giới hạn kiểu dữ liệu:** trường có `@DnAttribute` phải là `String` theo Spring LDAP ODM. Không khai báo `Name` hoặc `List<String>` cho một trường dùng trực tiếp với annotation này.

### 4.2. Index phải đầy đủ để tự tính DN

Khi một entity có nhiều trường `@DnAttribute`, tất cả các trường được dùng để **tự tính DN** phải khai báo `index`. Nếu chỉ dùng `@DnAttribute(value="uid")` mà không có index, trường vẫn có thể được trích xuất từ DN khi đọc, nhưng không nên kỳ vọng ODM có đủ thông tin để tính DN/move entry khi cập nhật.

Khi dùng một RDN `uid` sát `@Entry(base="ou=people")`, `index=0` là trường hợp đơn giản nhất.

### 4.3. @DnAttribute không tự biến trường thành transient

Theo tài liệu ODM, trường Java **mặc định vẫn được ánh xạ thành thuộc tính LDAP** dù có `@DnAttribute`. Nếu một trường chỉ dùng để tính đường dẫn (ví dụ OU tổ chức) và **không muốn lưu thành thuộc tính của entry**, có thể thêm `@Transient`.

Đừng coi `@DnAttribute` là cơ chế đánh dấu “chỉ đọc”: nếu ứng dụng cho sửa trường này rồi gọi `update`, tên entry có thể thay đổi.

## 5. Luồng đọc entity và giữ DN ban đầu

Đọc entry qua `LdapTemplate`:

~~~java
import javax.naming.Name;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

Name oldDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "lan")
        .build();

DirectoryPerson person =
        ldapTemplate.findByDn(oldDn, DirectoryPerson.class);
~~~

Trong cấu hình đã cho, `oldDn` là DN **tương đối** `uid=lan,ou=people`. Trên entity sau khi ODM ánh xạ:

~~~text
person.getDn()  = uid=lan,ou=people
person.getUid() = lan
person.getTitle() = Backend Developer
~~~

`@Id` biểu diễn **DN đã đọc được**, là cơ sở để ODM nhận biết tên cũ khi tính lại DN từ các trường có `@DnAttribute`.

Điểm cần nhớ: khi muốn kiểm chứng quá trình đổi tên, hãy giữ lại `oldDn` trong biến **riêng** trước lúc sửa entity. Sau `update` thành công, ODM có thể cập nhật giá trị `@Id` trên đối tượng truyền vào; chỉ kiểm tra `person.getDn()` sau lời gọi không cho biết trạng thái tên ban đầu.

## 6. Trường hợp A: sửa thuộc tính không tham gia DN

Ví dụ chỉ sửa chức danh:

~~~java
DirectoryPerson person =
        ldapTemplate.findByDn(oldDn, DirectoryPerson.class);

person.setTitle("Senior Backend Developer");
ldapTemplate.update(person);
~~~

`uid` và các `@DnAttribute` khác không thay đổi. DN được tính từ entity vẫn là `uid=lan,ou=people`.

Theo Javadoc `LdapOperations.update(Object)`, khi DN tính được **không khác** `@Id`, ODM:

1. Đọc trạng thái entry hiện tại từ LDAP.
2. So sánh dữ liệu Java đã ánh xạ với các thuộc tính hiện có.
3. Tính `ModificationItem` phù hợp.
4. Gọi `modifyAttributes(...)` để sửa các thuộc tính.

Kết quả kỳ vọng:

~~~text
DN trước: uid=lan,ou=people,dc=example,dc=org
DN sau:   uid=lan,ou=people,dc=example,dc=org

title trước: Backend Developer
title sau:   Senior Backend Developer
~~~

**Đây là sửa thuộc tính, không phải rename.** Việc ghi có thể vẫn thất bại vì schema/ACL hoặc xung đột thay đổi đồng thời. Đừng mặc định mọi thuộc tính không có trong entity đều được bảo toàn trong mọi chiến lược mapping; cần kiểm thử trên phiên bản framework và directory thực tế.

## 7. Trường hợp B: thay đổi @DnAttribute trên entity đã tải

Đây là trọng tâm của bài.

~~~java
Name originalDn = LdapNameBuilder
        .newInstance("ou=people")
        .add("uid", "lan")
        .build();

DirectoryPerson person =
        ldapTemplate.findByDn(originalDn, DirectoryPerson.class);

// Chỉ dùng để THÍ NGHIỆM trên directory test.
person.setUid("lan.nguyen");
ldapTemplate.update(person);
~~~

Với `@Entry(base="ou=people")` và `@DnAttribute(index=0)`:

~~~text
@Id trước:         uid=lan,ou=people
DN tính mới:       uid=lan.nguyen,ou=people
DN đầy đủ sau:     uid=lan.nguyen,ou=people,dc=example,dc=org
~~~

### 7.1. Chính xác ODM làm gì?

Tài liệu tham khảo nói rằng ODM có thể **tự xử lý việc di chuyển entry** khi trường tham gia DN thay đổi. Nhưng cần đọc rõ Javadoc của `LdapTemplate.update(Object)`:

- Nếu `@Id` **đã có** và **DN tính được khác `@Id`**, nhánh này được mô tả là **`unbind(oldDn)` rồi `bind(newEntry)`**.
- Nếu tên **không đổi**, dùng so sánh thuộc tính và `modifyAttributes(...)`.
- Nếu DN được tính/đổi trong quá trình thực thi, giá trị `@Id` trên object có thể được cập nhật.

**Không đánh đồng “ODM tự move” với LDAP ModifyDN/Rename nguyên tử.** `unbind + bind` về mặt ngữ nghĩa là **xóa entry cũ, rồi tạo entry mới**. Hai request đó có thể có hậu quả khác một LDAP Modify DN.

~~~mermaid
sequenceDiagram
    autonumber
    participant S as Service
    participant O as LdapTemplate.update(entity)
    participant D as LDAP Server
    S->>O: Entity có @Id cũ, uid mới
    O->>O: Tính DN mới từ @DnAttribute(index)
    alt DN cũ == DN mới
        O->>D: Đọc trạng thái hiện tại
        O->>D: Modify attributes
    else DN cũ khác DN mới
        O->>D: Unbind / Delete DN cũ
        D-->>O: Xóa thành công hoặc lỗi
        O->>D: Bind / Add entry tại DN mới
        D-->>O: Add thành công hoặc lỗi
    end
    O-->>S: Hoàn tất / exception
~~~

Sơ đồ trên là **mô hình hành vi mô tả trong Javadoc**, không phải cam kết rằng mọi thư viện hoặc repository khác đều gọi đúng cùng chuỗi method ở mọi phiên bản. Khi dùng Spring Data LDAP repository, cần xác nhận cụ thể nó chuyển thao tác `save` thành đường gọi ODM nào trong phiên bản đang sử dụng.

### 7.2. Vì sao unbind + bind rủi ro?

| Rủi ro | Hệ quả có thể xảy ra |
| --- | --- |
| Xóa thành công, tạo lại thất bại | DN cũ không còn, DN mới cũng chưa có; có thể cần khôi phục từ backup. |
| Entry có operational attributes | Thuộc tính do server quản lý, metadata và các giá trị không ánh xạ có thể không được tái tạo giống ban đầu. |
| `groupOfNames.member` tham chiếu DN cũ | Nhóm có thể giữ giá trị tham chiếu không còn đúng. |
| Entry có các entry con | Xóa entry cha có con thường bị directory từ chối (ví dụ `notAllowedOnNonLeaf`). |
| Server yêu cầu ACL khác cho Delete và Add | Có quyền sửa thuộc tính nhưng không có quyền xóa/tạo lại. |
| Cơ chế audit/replication | Có thể quan sát một Delete và Add thay vì một Rename, phát sinh sự kiện riêng. |
| Hai request đồng thời | Không có isolation cho toàn chuỗi thao tác; yêu cầu khác có thể xen giữa. |
| Bảo toàn thuộc tính chưa được ODM map | Không bảo đảm mọi attribute còn lại được giữ nguyên. |

**Quan trọng:** đây không phải lỗi “`@DnAttribute` không hoạt động”. ODM có thể thực hiện đúng thiết kế của nó nhưng **không đáp ứng yêu cầu bảo toàn định danh và dữ liệu** của nghiệp vụ.

### 7.3. Hành vi lỗi cần kiểm chứng

Ví dụ `uid=lan.nguyen,ou=people` đã tồn tại. Khi gọi `update` cho `uid=lan` đổi sang tên đó, bạn có thể nhận lỗi trùng tên đích. **Không được giả định DN cũ vẫn nguyên vẹn sau mọi kiểu lỗi**, bởi nhánh tài liệu mô tả có bước xóa trước bước tạo.

Do đó, không nên dùng automatic ODM move như phương án mặc định cho một tài khoản quan trọng có nhóm, ACL, audit, mật khẩu hoặc metadata do server quản lý.

## 8. Trường hợp C: chủ động dùng LDAP Modify DN qua rename

Nếu use case thực sự là **đổi RDN hoặc chuyển entry**, API `LdapTemplate.rename(oldDn, newDn)` yêu cầu LDAP server thực hiện thao tác **Modify DN / Rename** tương ứng, thay vì ép ứng dụng làm Delete rồi Add.

~~~java
import javax.naming.Name;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class DirectoryRenamer {

    private final LdapTemplate ldapTemplate;

    public DirectoryRenamer(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void renameUid(String oldUid, String newUid) {
        validateUid(oldUid);
        validateUid(newUid);

        Name oldDn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", oldUid)
                .build();

        Name newDn = LdapNameBuilder.newInstance("ou=people")
                .add("uid", newUid)
                .build();

        if (oldDn.equals(newDn)) {
            return;
        }

        // Chỉ thực hiện sau khi đã xác thực/phân quyền yêu cầu.
        ldapTemplate.rename(oldDn, newDn);
    }

    private static void validateUid(String uid) {
        if (uid == null
                || !uid.matches("[a-z][a-z0-9._-]{2,31}")) {
            throw new IllegalArgumentException("Invalid uid");
        }
    }
}
~~~

**Hai DN trong ví dụ tương đối với `spring.ldap.base=dc=example,dc=org`.** Để đổi username, service không cần nhận DN tùy ý từ HTTP client. Nó chỉ nhận `oldUid` và `newUid` theo quy ước nghiệp vụ rồi xây DN dưới nhánh cố định.

### 8.1. Điểm mạnh và giới hạn của rename

| Tiêu chí | `LdapTemplate.rename` | ODM `update` khi DN tính lại khác |
| --- | --- | --- |
| Ý định operation | Chuyển/đổi tên một entry qua LDAP Modify DN. | ODM định vị lại entity theo DN tính được. |
| Hành vi Javadoc nêu rõ | Move entry tới DN mới. | `unbind(old)` rồi `bind(new)`. |
| Có thể bảo toàn entry/metadata do server quản lý | Thường phù hợp hơn cho rename thực sự, tùy directory. | Có nguy cơ metadata bị tạo lại/mất. |
| Tên đích đã tồn tại | Server có thể trả conflict. | Bước Add sau Delete có thể lỗi; cần xử lý hậu quả. |
| Tham chiếu nhóm | Không mặc định được mọi server tự cập nhật. | Không mặc định được tự cập nhật. |
| Parent/ACL/naming context | Cần quyền và support của server. | Cần quyền Delete/Add và schema tương ứng. |
| Transaction nhiều bước | Bản thân Rename là một LDAP operation, nhưng quy trình cập nhật nhóm sau đó không tự nguyên tử. | Chuỗi Delete/Add riêng, không đảm bảo nguyên tử. |

**Không phải mọi LDAP server đều cho Move giữa các naming context hoặc các directory khác nhau.** Nếu rename từ `dc=example,dc=org` sang một suffix của server khác, có thể cần cơ chế migration liên hệ thống thay vì một `rename`.

### 8.2. Vấn đề RDN cũ và thuộc tính uid

Trong LDAP Modify DN, việc **giữ hay xóa giá trị RDN cũ** phụ thuộc trường `deleteOldRDN` của yêu cầu và cách client/server hỗ trợ. `LdapTemplate.rename` không cung cấp thông qua ví dụ trên một tham số `deleteOldRDN` riêng.

Vì thế sau Rename phải đọc lại `uid` và DN để xác minh:

- DN mới có đúng `uid=lan.nguyen` không?
- Thuộc tính `uid` có chứa giá trị mới không?
- Giá trị cũ `lan` có còn không, và điều đó có phù hợp chính sách hay không?
- `@DnAttribute` trên entity đọc lại có giá trị nào nếu attribute đa giá trị?

Không tự khẳng định rename luôn loại bỏ mọi giá trị cũ trong tất cả directory. Nếu nghiệp vụ yêu cầu một username duy nhất, cần xác định rõ cơ chế Modify DN, schema và hành vi của server đích.

## 9. Đồng bộ entity Java sau rename

Khi bạn gọi `ldapTemplate.rename(oldDn,newDn)` **trực tiếp**, đối tượng Java đang giữ trước đó không tự nhiên biết entry đã được đổi tên. Cách đơn giản là **đọc lại entity theo DN mới**.

~~~java
Name oldDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "lan")
        .build();

Name newDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "lan.nguyen")
        .build();

ldapTemplate.rename(oldDn, newDn);

DirectoryPerson moved =
        ldapTemplate.findByDn(newDn, DirectoryPerson.class);

// DTO/logic tiếp theo lấy từ entry vừa đọc lại:
String currentUid = moved.getUid();
Name currentDn = moved.getDn();
~~~

**Không** giữ một `DirectoryPerson` cũ trong cache rồi gọi `update` sau rename mà không kiểm tra lại `@Id`. Một entity cũ có thể vẫn mang DN nguồn và làm phát sinh lỗi `NameNotFound` hoặc một nhánh cập nhật không mong muốn.

Đồng thời phải đánh giá những bộ nhớ đệm, event và hệ thống ngoài LDAP nào lưu DN như một khóa. Rename một entry không làm Java reference trong các service khác tự thay đổi.

## 10. Thay đổi nhiều trường @DnAttribute để di chuyển giữa OU

Giả sử directory có cây:

~~~text
dc=example,dc=org
└── ou=people
    ├── ou=engineering
    │   └── uid=lan
    └── ou=sales
        └── uid=mai
~~~

Nếu entity cần mô tả **hai thành phần nằm dưới `ou=people`**, dùng index:

~~~java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.DnAttribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;
import org.springframework.ldap.odm.annotations.Transient;

@Entry(
    base = "ou=people",
    objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
    }
)
public class DepartmentPerson {

    @Id
    private Name dn;

    @DnAttribute(value = "ou", index = 0)
    @Transient
    private String department;

    @DnAttribute(value = "uid", index = 1)
    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String cn;

    @Attribute(name = "sn")
    private String sn;

    // Thêm constructor/getter/setter trong project thật.
}
~~~

Giải thích thứ tự:

~~~text
uid=lan,ou=engineering,ou=people,dc=example,dc=org
   |           |               |
   |           |               +-- @Entry(base), rồi ContextSource.base
   |           +------------------ @DnAttribute(index=0): gần base
   +------------------------------ @DnAttribute(index=1): xa base hơn
~~~

Nếu `department` đổi từ `engineering` thành `sales`, DN tính được thay từ:

~~~text
uid=lan,ou=engineering,ou=people
~~~

sang:

~~~text
uid=lan,ou=sales,ou=people
~~~

**Chỉ thay field `department` trong Java không tự tạo OU mới** và không đảm bảo Move thành công. OU đích phải tồn tại; tài khoản service cần quyền thao tác ở nhánh nguồn/đích; schema và cấu hình server phải cho phép Move. Nếu `ldapTemplate.update(departmentPerson)` được dùng, cần tính tới **nhánh unbind/bind** như mục 7.

Trong dự án quản trị directory, nên tách use case **“sửa thông tin phòng ban”** (thuộc tính nghiệp vụ) khỏi **“chuyển entry sang OU khác”** (di chuyển DN). Hai điều này không nên bị liên kết vô tình chỉ vì chọn `department` làm `@DnAttribute`.

## 11. Lựa chọn: để ODM tính DN hay đặt DN tường minh?

### Lựa chọn A: ODM tự tính từ @DnAttribute

Phù hợp khi:

- DN có cấu trúc ổn định.
- Mọi thành phần đã được ánh xạ `@DnAttribute(index=...)` đầy đủ.
- Use case chấp nhận hành vi và rủi ro của ODM `update`.
- Có integration test cho trường hợp DN đổi và DN không đổi.

Không phù hợp nếu bạn bắt buộc bảo toàn nguyên entry và không chấp nhận đường xử lý Delete/Add khi tên thay đổi.

### Lựa chọn B: gán @Id Name tường minh

~~~java
Name relativeDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "lan")
        .build();

DirectoryPerson person = new DirectoryPerson();
person.setDn(relativeDn);
person.setUid("lan");
// ... gán cn, sn ...
~~~

Khi `@Id` đã được gán, create/update có thể sử dụng DN đó. Nhưng **không thể suy ra rằng sửa `uid` sẽ không động tới DN** nếu class vẫn có `@DnAttribute(index=...)` và đường `update` so sánh DN được tính với `@Id`.

**Không tự sửa `@Id` thành DN mới trước khi update để “lừa” ODM**: điều đó làm mất thông tin tên gốc và có thể khiến thao tác nhắm vào entry sai hoặc báo không tìm thấy. Nếu muốn đổi tên thật sự, gọi `rename(old,new)` với cả hai tên rồi đọc lại.

### Lựa chọn C: định danh bất biến, thay thông tin hiển thị

Nếu nghiệp vụ cho phép, chọn một định danh ổn định làm RDN (`uid` được quản lý và không đổi) và chỉ cập nhật `cn`, `displayName`, `title` hoặc `mail`. Ví dụ người dùng đổi họ tên nhưng không đổi `uid`.

Đây thường là lựa chọn đơn giản nhất để tránh rủi ro DN tham chiếu từ nhóm và ứng dụng khác. Tuy nhiên định danh bất biến cần được thiết kế từ đầu, không tự động phát sinh từ LDAP schema.

## 12. Repository.save có giống LdapTemplate.update không?

Spring Data LDAP thường dùng:

~~~java
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {
}
~~~

và:

~~~java
DirectoryPerson person = repository.findById(oldDn)
        .orElseThrow();

person.setTitle("Senior Backend Developer");
repository.save(person);
~~~

Lưu ý hai lớp API:

- **Spring LDAP ODM** định nghĩa `LdapTemplate.create/update/delete` và logic tính DN.
- **Spring Data LDAP repository** cung cấp `save/findById/delete` với chiến lược xác định entity mới hay đã tồn tại của chính repository.

Không được suy luận rằng `repository.save(entity)` **luôn** giống hệt `ldapTemplate.update(entity)` trong mọi trường hợp/phiên bản. Cần kiểm tra bằng integration test và tài liệu đúng phiên bản, đặc biệt khi `@Id` là null, khi đang thay đổi `@DnAttribute` hoặc khi repository chạy qua template do ứng dụng tự khai báo.

Với use case Rename/Move có chính sách nghiêm ngặt, một service tường minh gọi `LdapTemplate.rename` thường dễ kiểm toán hơn việc dựa vào tác dụng phụ của `save` trên một trường định danh.

## 13. Rủi ro với nhóm, DN references và ACL

Nhóm LDAP có thể chứa:

~~~ldif
dn: cn=engineering,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: engineering
member: uid=lan,ou=people,dc=example,dc=org
member: uid=minh,ou=people,dc=example,dc=org
~~~

Sau khi Lan đổi DN thành `uid=lan.nguyen,ou=people,dc=example,dc=org`, thuộc tính `member` **có thể vẫn chứa DN cũ**.

### 13.1. Directory có tự sửa member không?

Không nên giả định. Một số LDAP server có **referential integrity overlay/plugin** cập nhật DN trong các thuộc tính tham chiếu khi entry được rename/delete. Những server khác không có hoặc cấu hình chưa bật.

Do đó cần:

1. Kiểm tra cấu hình directory trong môi trường triển khai thực tế.
2. Thực hiện Rename trên fixture test.
3. Đọc lại nhóm để kiểm tra giá trị `member`.
4. Nếu server không cập nhật tự động, thiết kế quy trình cập nhật tham chiếu và đối soát sau sự cố.
5. Đánh giá các nhóm, ACL và hệ thống bên ngoài lưu DN theo cách riêng.

**Đừng viết một thao tác Modify thay toàn bộ danh sách `member` chỉ để thay DN của một người.** Hãy dùng thay đổi có chọn lọc hoặc quy trình server-side được phê duyệt, đồng thời đánh giá race condition.

### 13.2. Quyền đổi tên khác quyền sửa thuộc tính

Tài khoản LDAP có thể được phép sửa `title` nhưng không được:

- Đổi RDN `uid`.
- Move entry sang OU mới.
- Tạo entry tại parent đích.
- Xóa entry dưới parent nguồn.
- Sửa các nhóm tham chiếu.

Các ACL này tùy directory và có thể có điều kiện riêng theo subtree. Kiểm thử bằng **chính Bind DN mà ứng dụng dùng**, không chỉ admin account. Nếu nhận `insufficientAccessRights (50)`, không nâng quyền một cách tùy tiện để làm test “xanh”.

## 14. Thiết kế API đổi username riêng biệt

Không nên cho phép client gửi một `DirectoryPerson` chứa `dn`, `objectClass` và các trường nhạy cảm rồi tự lưu entity. Use case đổi RDN có ý nghĩa khác cập nhật hồ sơ thông thường.

### 14.1. DTO cho yêu cầu đổi tên

`RenameUidRequest.java`:

~~~java
package com.example.directory.api;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

public record RenameUidRequest(
        @NotBlank
        @Pattern(regexp = "[a-z][a-z0-9._-]{2,31}")
        String newUid
) {}
~~~

Tài khoản được đổi nằm trong path hoặc service context đã được xác thực. **Không** nhận DN mới, parent OU hoặc `objectClass` từ client nếu đây chỉ là nghiệp vụ đổi username dưới `ou=people`.

### 14.2. Service kiểm soát trước và sau Rename

~~~java
package com.example.directory.service;

import javax.naming.Name;

import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class RenameUidService {

    private final LdapTemplate ldapTemplate;

    public RenameUidService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public DirectoryPerson rename(String oldUid, String newUid) {
        validateUid(oldUid);
        validateUid(newUid);

        // Trước bước này, tầng security phải phê duyệt actor và
        // mục tiêu. Nếu cần, kiểm tra nhóm và chính sách liên quan.
        Name oldDn = dnFor(oldUid);
        Name newDn = dnFor(newUid);

        if (oldDn.equals(newDn)) {
            return ldapTemplate.findByDn(oldDn, DirectoryPerson.class);
        }

        // Đường chuyển DN tường minh (LDAP Modify DN):
        ldapTemplate.rename(oldDn, newDn);

        // Không dùng entity cũ có @Id cũ sau Rename.
        // Đọc lại để xác nhận dữ liệu server thực sự trả về.
        return ldapTemplate.findByDn(newDn, DirectoryPerson.class);
    }

    private static Name dnFor(String uid) {
        return LdapNameBuilder.newInstance("ou=people")
                .add("uid", uid)
                .build();
    }

    private static void validateUid(String uid) {
        if (uid == null
                || !uid.matches("[a-z][a-z0-9._-]{2,31}")) {
            throw new IllegalArgumentException("Invalid uid");
        }
    }
}
~~~

**Ví dụ này chưa tự động cập nhật nhóm** và chưa bao gồm cơ chế khóa/đối soát. Nó chỉ minh họa việc chọn Modify DN một cách có chủ đích và đọc lại entity đúng tên. Trong ứng dụng thật cần bổ sung authorization, kiểm tra conflict, audit, quy trình tham chiếu và xử lý thất bại.

### 14.3. Controller dùng DTO, không dùng entity

~~~java
package com.example.directory.web;

import jakarta.validation.Valid;

import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/people")
public class PersonRenameController {

    private final RenameUidService service;

    public PersonRenameController(RenameUidService service) {
        this.service = service;
    }

    @PostMapping("/{oldUid}/rename")
    public void rename(
            @PathVariable String oldUid,
            @Valid @RequestBody RenameUidRequest request) {
        service.rename(oldUid, request.newUid());
    }
}
~~~

Endpoint đổi tên thường nên giới hạn cho quản trị viên hoặc người có quyền nghiệp vụ rõ ràng. Không thay username theo dữ liệu client mà thiếu kiểm tra ownership/quyền.

## 15. Thực hành với LDAP server thử nghiệm

Chuẩn bị một directory test có:

~~~text
dc=example,dc=org
├── ou=people
│   └── uid=lan
├── ou=staff
└── ou=groups
    └── cn=engineering
~~~

Các entry cha phải tồn tại, server có schema `inetOrgPerson` và `groupOfNames`. Tài khoản thử nghiệm cần quyền để thực hiện cả Modify, Delete/Add (nếu thử ODM update) và Rename trong nhánh thích hợp.

### 15.1. Xác minh trước thao tác

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -D "cn=svc-directory-writer,ou=service,dc=example,dc=org" -W \
  -b "uid=lan,ou=people,dc=example,dc=org" -s base \
  "(objectClass=inetOrgPerson)" \
  dn uid cn sn mail title
~~~

Dự kiến thấy Lan. `-W` yêu cầu nhập mật khẩu ở prompt, không đưa secret trực tiếp vào command.

### 15.2. Thử sửa title (DN không thay)

Gọi service dùng `ldapTemplate.update` sau khi chỉ thay `title`; đọc lại theo **DN cũ**. Kỳ vọng:

- DN vẫn `uid=lan,ou=people,dc=example,dc=org`.
- `title` đã thay đổi.
- `uid`, `cn` và `sn` vẫn phù hợp schema.
- Không tạo entry mới với DN khác.

### 15.3. Thử đổi uid bằng ODM trên fixture riêng

**Chỉ làm ở test directory.** Tạo một entry test khác (ví dụ `uid=demoodm01`), tải bằng `findByDn`, sửa `@DnAttribute(uid)` và gọi `ldapTemplate.update`. Đọc lại cả DN cũ và DN mới.

Để thấy rõ rủi ro, ghi nhận thêm:

- `entryUUID`/operational metadata trước và sau, nếu server cho quyền đọc.
- Mọi thuộc tính do một hệ thống khác quản lý mà entity ODM không map.
- Trạng thái `member` ở các nhóm tham chiếu.
- Log server cho thấy các LDAP operation nào thực sự được gửi.

Với phiên bản triển khai theo Javadoc `update(Object)` đã nêu, bạn có thể thấy **Delete/Add** chứ không phải Modify DN. Trường hợp tạo lại thất bại cần phương án recovery; không tiến hành thử phá lỗi trên dữ liệu thật.

### 15.4. Thử đổi uid bằng Modify DN

Để so sánh, tạo fixture khác `uid=demorename01`, sau đó gọi:

~~~java
Name oldDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "demorename01")
        .build();
Name newDn = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "demorename02")
        .build();

ldapTemplate.rename(oldDn, newDn);
~~~

Đọc lại DN đích và xem log server: kỳ vọng đường thực thi LDAP **Modify DN**. So sánh operational attributes, tham chiếu nhóm, quyền và kết quả với cách ODM `update`.

### 15.5. Thử chuyển OU

Với `uid=demomove01`:

~~~java
Name from = LdapNameBuilder.newInstance("ou=people")
        .add("uid", "demomove01")
        .build();

Name to = LdapNameBuilder.newInstance("ou=staff")
        .add("uid", "demomove01")
        .build();

ldapTemplate.rename(from, to);
~~~

Kết quả thành công phụ thuộc parent `ou=staff` đã tồn tại, quyền ACL ở cả hai nhánh và server cho Move trong cùng naming context. Test không được mặc định hỗ trợ Move giữa các server LDAP khác nhau.

## 16. Kiểm thử tích hợp theo hành vi thật

Các unit test dùng mock có thể chứng minh service gọi đúng `ldapTemplate.rename(...)` hoặc `ldapTemplate.update(...)`, nhưng **không** chứng minh LDAP server đã rename hay dữ liệu còn nguyên. Do đó cần integration test với directory thật/nhúng.

### 16.1. Test Rename chủ động

~~~java
import static org.junit.jupiter.api.Assertions.*;

import javax.naming.Name;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

@SpringBootTest
class RenameMoveIntegrationTest {

    @Autowired
    LdapTemplate ldapTemplate;

    @Test
    void explicitRenameMovesEntryToNewDn() {
        // Fixture uid=demorename01 được tạo trước mỗi test,
        // uid=demorename02 chưa tồn tại.
        Name from = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "demorename01")
                .build();
        Name to = LdapNameBuilder.newInstance("ou=people")
                .add("uid", "demorename02")
                .build();

        assertNotNull(
                ldapTemplate.findByDn(from, DirectoryPerson.class));

        ldapTemplate.rename(from, to);

        DirectoryPerson moved =
                ldapTemplate.findByDn(to, DirectoryPerson.class);

        assertNotNull(moved);
        assertEquals("demorename02", moved.getUid());
        assertEquals(to, moved.getDn());
        // Kiểm tra thêm DN nguồn bằng LDAP lookup/server search
        // và dọn fixture sau khi test.
    }
}
~~~

Với directory cụ thể, cần kiểm tra `uid` cũ có còn là giá trị phụ hay không. Nếu directory giữ cả hai giá trị và mapping `String` không biểu diễn đa trị, test cần bổ sung kiểm chứng ở tầng LDAP attribute.

**Yêu cầu fixture:** mỗi test phải độc lập và có setup/cleanup. Tránh chạy cùng ID cố định nhiều lần trên một directory chưa reset.

### 16.2. Ma trận cần có

| Trường hợp | Kỳ vọng/điều cần xác minh |
| --- | --- |
| Sửa `title`, không đổi `@DnAttribute` | `update` đổi thuộc tính, DN giữ nguyên. |
| Sửa `uid` có `@DnAttribute(index=0)` | DN tính mới khác `@Id`; kiểm tra đường update và dữ liệu tồn tại. |
| `@DnAttribute` thiếu index | Không kỳ vọng ODM tự tính đầy đủ DN cho Move; kiểm thử hành vi phiên bản. |
| Thay `uid` nhưng đổi `@Id` thủ công trước update | Không xem là cách rename an toàn; phải phát hiện trạng thái không nhất quán. |
| Đổi uid tới DN đã tồn tại | Conflict; kiểm tra DN nguồn còn/mất theo operation thực tế và khôi phục nếu cần. |
| Rename chủ động tới tên mới | Entry được đọc tại DN đích; DN nguồn không còn. |
| Move sang OU chưa có | Operation thất bại; không tự tạo parent OU. |
| Move khác naming context/server | Kiểm tra giới hạn server; không mặc định thành công. |
| Rename khi không có quyền phù hợp | Trả lỗi ACL; không tăng quyền để test pass. |
| ODM update theo nhánh unbind/bind thiếu quyền Delete | Có thể thất bại dù quyền Modify tồn tại. |
| Đổi DN của entry có children | Kiểm tra hỗ trợ subtree, hành vi Rename và hạn chế Delete. |
| Nhóm tham chiếu DN nguồn | Đọc `groupOfNames.member` sau rename, không giả định auto-update. |
| Operational attributes | So sánh trước/sau; không mặc định Delete/Add bảo toàn metadata. |
| Đổi giá trị RDN cũ/mới | Kiểm tra `uid` trên server, khả năng đa trị và policy deleteOldRDN. |
| Hai request rename cùng lúc | Server xử lý conflict; service có chiến lược đối soát và không retry mù. |
| Lỗi mạng sau operation | Xác minh trạng thái LDAP trước khi retry, vì response có thể mất. |
| TLS lỗi chứng chỉ | Không hạ cấp sang LDAP plaintext. |
| Repository.save có entity đổi DN | Kiểm tra đúng nhánh thực thi ở phiên bản Spring Data LDAP. |

## 17. Xử lý lỗi và khôi phục có kiểm soát

Một số resultCode LDAP có thể xuất hiện trong Rename/Move hoặc ODM update:

| Mã/nhóm lỗi | Ý nghĩa thường gặp | Cách xử lý |
| --- | --- | --- |
| `noSuchObject (32)` | DN nguồn hoặc OU cha đích không tồn tại. | Xác định đúng DN, base và trạng thái hiện tại. |
| `invalidDNSyntax (34)` | DN/RDN không hợp lệ về cú pháp. | Xây DN bằng API chuẩn, kiểm tra input. |
| `insufficientAccessRights (50)` | Bind account thiếu quyền Modify DN hoặc Delete/Add. | Kiểm tra ACL cho đúng operation; không leo quyền. |
| `namingViolation (64)` | RDN/vị trí đích vi phạm quy tắc naming/schema. | Kiểm tra objectClass, parent và chính sách naming. |
| `objectClassViolation (65)` | Dữ liệu thiếu thuộc tính bắt buộc hoặc sai schema. | Kiểm tra `cn`/`sn` và các attribute. |
| `notAllowedOnNonLeaf (66)` | Delete entry có child bị cấm. | Không xóa subtree một cách tùy tiện. |
| `notAllowedOnRDN (67)` | Thay thuộc tính đang dùng trong RDN theo cách bị cấm. | Dùng Modify DN đúng use case. |
| `entryAlreadyExists (68)` | DN đích đã tồn tại. | Xử lý HTTP 409/xung đột, không ghi đè. |
| `affectsMultipleDSAs (71)` | Operation đi qua nhiều directory system agent. | Thiết kế migration/đối soát riêng. |
| TCP/TLS/timeout không có LDAPResult | Không biết server đã nhận operation hay chưa. | Kiểm tra trạng thái thực trước khi retry. |

Khi một Rename/Move hoặc chuỗi Delete/Add gặp lỗi **sau khi thao tác đầu đã có thể hoàn tất**, không thể chỉ dựa vào exception Java để khẳng định directory vẫn ở trạng thái ban đầu. Quy trình khôi phục nên:

1. Ghi request ID, DN nguồn/đích được phép log và mục đích nghiệp vụ.
2. Đọc lại DN nguồn và DN đích bằng tài khoản phù hợp.
3. Kiểm tra thuộc tính cần bảo toàn, operational attributes quan trọng và tham chiếu nhóm.
4. Phân biệt lỗi “chưa thực hiện” với lỗi “đã thực hiện nhưng response bị mất”.
5. Chỉ retry khi xác định operation còn cần thiết; bảo vệ khỏi xung đột.
6. Nếu dữ liệu sai lệch, dùng quy trình repair/backup được phê duyệt.
7. Không trả 200 hoặc thông báo “đổi tên thành công” khi chưa có bằng chứng.

## 18. Bảo mật và tính nhất quán nghiệp vụ

### 18.1. Không để người gọi HTTP chọn DN tùy ý

API nên nhận `oldUid`, `newUid` hoặc mã tổ chức đã được kiểm tra. Không cho client gửi trực tiếp:

~~~json
{
  "sourceDn": "uid=lan,ou=people,dc=example,dc=org",
  "targetDn": "uid=lan,ou=admins,dc=example,dc=org"
}
~~~

Một payload như vậy có thể cố đưa người dùng sang nhánh nhạy cảm. **Server** phải quyết định OU đích từ quy tắc nghiệp vụ và kiểm tra authorization; ACL LDAP là lớp kiểm soát bổ sung.

### 18.2. DN escaping khác LDAP filter escaping

- Dùng `LdapNameBuilder`/`LdapName` cho tên `uid=...`, theo quy tắc DN của RFC 4514.
- Dùng `LdapQueryBuilder` và `EqualsFilter` khi tìm entry theo UID từ request HTTP, theo RFC 4515.
- Không ghép DN/filter bằng chuỗi input không tin cậy; tránh injection và thao tác ngoài scope.

~~~java
LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is(inputUid);
~~~

### 18.3. Giới hạn quyền và bảo vệ kết nối

- Dùng **LDAPS** hoặc **StartTLS thiết lập xong trước Simple Bind**, kiểm tra CA/certificate và hostname.
- Credential LDAP service account phải qua secret manager/biến môi trường, không commit vào mã.
- Chia tài khoản Search/Modify với tài khoản có quyền Rename/Delete/Add nếu có thể.
- Không expose thông tin Bind DN, mật khẩu, ACL, stack trace hoặc dữ liệu cá nhân nhạy cảm trong response HTTP.
- Khi thay đổi DN ảnh hưởng nhóm/ACL, không mặc định tác động được đảo ngược bởi `@Transactional`.
- Spring LDAP **compensating transactions** nếu được cấu hình cũng chỉ cố gắng hoàn tác, không đem lại isolation/atomicity liên hệ thống.
- Nếu LDAP server sử dụng operational attributes (`entryUUID`, `createTimestamp`...), chỉ yêu cầu/ghi log những giá trị được phép; một số thuộc tính không được client sửa.

## 19. Bài tập củng cố

**Bài 1 – Phân tích hai nhánh update.** Với `uid=lan`, đổi `title` rồi gọi `ldapTemplate.update`. Sau đó đặt lại fixture, đổi `uid` rồi gọi `update`. Ghi lại các LDAP operation server thực sự nhận theo log test và giải thích khác biệt.

**Bài 2 – Kiểm chứng index.** Tạo entity có `@DnAttribute(value="uid", index=1)` và `@DnAttribute(value="ou", index=0)` với `@Entry(base="ou=people")`. Dự đoán DN khi department chuyển từ engineering sang sales. Giải thích vì sao parent OU phải tồn tại.

**Bài 3 – Cấu hình an toàn.** Viết `RenameUidRequest` và policy chỉ cho phép admin đổi `uid` trong `ou=people`. Khi HTTP client gửi OU đích lạ, API phải từ chối trước khi gọi LDAP.

**Bài 4 – So sánh Move.** Thử `LdapTemplate.rename` và `LdapTemplate.update` làm thay đổi DN ở hai fixture riêng. So sánh `entryUUID`/metadata, giá trị `uid` và tham chiếu nhóm. Nêu trường hợp Delete/Add có thể nguy hiểm hơn Modify DN.

**Bài 5 – Cạnh tranh.** Cho hai request cùng đổi `uid=lan` sang hai giá trị khác nhau. Thảo luận khả năng request thứ hai gặp `noSuchObject` hoặc conflict, và cách kiểm tra trạng thái trước khi retry.

**Bài 6 – Referentials.** Sau Rename, tìm các nhóm có `member` trỏ tới DN cũ. Đề xuất cách cập nhật có chọn lọc và kiểm thử referential integrity của directory test.

## 20. Câu hỏi tự ôn tập

1. Vì sao thay `title` không nhất thiết thay DN, còn thay `uid` có `@DnAttribute` thì có thể?
2. `@Id` giữ gì, và tại sao phải giữ bản sao `oldDn` trước khi sửa entity?
3. Vì sao mọi `@DnAttribute` dùng để tự tính DN đều cần index?
4. `@DnAttribute` có tự động bỏ qua việc lưu thuộc tính LDAP tương ứng không? Khi nào dùng `@Transient`?
5. Theo Javadoc `LdapTemplate.update(Object)`, hành vi khi DN tính mới khác `@Id` là gì?
6. Vì sao “ODM tự move” không được hiểu là “LDAP Modify DN nguyên tử”?
7. Vì sao Delete/Add có thể làm mất operational attributes hoặc thất bại giữa chừng?
8. `LdapTemplate.rename(oldDn,newDn)` có lợi ích gì khi muốn thực sự đổi tên entry?
9. Rename có mặc định cập nhật mọi giá trị `groupOfNames.member` trên mọi server không?
10. Vì sao cần đọc lại entity sau khi gọi `rename` tường minh?
11. Vì sao `repository.save` không nên được xem là phép Rename chắc chắn nếu chưa kiểm thử version?
12. Một entry có con bị ảnh hưởng thế nào nếu ODM di chuyển bằng đường Delete/Add?
13. Sau lỗi timeout, vì sao phải đọc lại DN nguồn/đích trước khi retry?
14. Tại sao không nên cho REST API nhận DN tùy ý từ client?
15. Với một hệ thống lớn, khi nào việc chọn ID bất biến làm RDN giúp giảm rủi ro?

**Ghi nhớ:** trường `@DnAttribute` không chỉ là dữ liệu Java; nó có thể định nghĩa **vị trí của entity trong LDAP**. `LdapTemplate.update(entity)` có thể đi vào nhánh **xóa entry cũ rồi tạo entry mới** khi DN tính lại khác `@Id`, trong khi `LdapTemplate.rename(oldDn,newDn)` chủ động thực hiện một LDAP Rename/Modify DN. Muốn đổi tên hoặc chuyển OU an toàn, hãy kiểm tra mapping, ACL, schema, tham chiếu nhóm, quyền và kết quả thực tế trên directory, thay vì chỉ đổi một field rồi gọi `save`.

### Tài liệu tham khảo

- [Spring LDAP – Object-Directory Mapping (ODM)](https://docs.spring.io/spring-ldap/reference/odm.html): `@DnAttribute`, `@Entry(base)`, `@Id` và DN được tính cho update.
- [Spring LDAP – LdapOperations API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapOperations.html): mô tả chính xác `update(Object)`, `rename` và `modifyAttributes`.
- [Spring LDAP – LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): Rename/Modify/ODM với LDAP.
- [Spring LDAP – DnAttribute Annotation API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/odm/annotations/DnAttribute.html): kiểu `String`, `index` và tính DN.
- [Spring LDAP – Basic Usage](https://docs.spring.io/spring-ldap/reference/spring-ldap-basic-usage.html): khác biệt giữa `rename`, `rebind` và `modifyAttributes`.
- [Spring Data LDAP – Reference](https://docs.spring.io/spring-data/ldap/reference/): repository và tích hợp ODM.
- [RFC 4511 – LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511): LDAP Modify DN, result codes và giới hạn giao thức.
- [RFC 4512 – LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): cấu trúc DIT, DN, schema và objectClass.
- [RFC 4514 – LDAP: String Representation of Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514): cú pháp DN/RDN và escaping.
- [RFC 4515 – LDAP: String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515): escaping filter trong truy vấn tìm entry.
