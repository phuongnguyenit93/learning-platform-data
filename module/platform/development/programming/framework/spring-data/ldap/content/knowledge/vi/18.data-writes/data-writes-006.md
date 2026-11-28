# Dùng DirContextAdapter để xác định thay đổi thuộc tính

## 1. Bài toán: cập nhật một vài field mà không ghi lại cả entry

Trong module **SPRING_DATA_LDAP**, chúng ta làm việc với directory thông qua **Spring Data LDAP** (repository, Object-Directory Mapping) và **Spring LDAP** (`LdapTemplate`, `DirContextOperations`). Mỗi entry nằm tại một **DN** (*distinguished name*), chứa các thuộc tính được quy định bởi `objectClass` và schema. Khi sửa một người dùng, ứng dụng thường chỉ muốn thay email, thêm một số điện thoại hoặc gỡ một giá trị mô tả — **không** muốn vô tình thay các attribute khác.

Giả sử entry:

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
telephoneNumber: +84 28 5555 0101
telephoneNumber: +84 90 1111 2222
description: Nhân viên kỹ thuật
```

Một màn hình chỉ cho sửa `mail` và thêm số điện thoại. Nếu service tự dựng lại cả entry từ DTO chưa đầy đủ hoặc dùng `REPLACE_ATTRIBUTE` cho toàn bộ tập số điện thoại, nó có thể xóa thông tin đang có.

**`DirContextAdapter`** giúp giải quyết trường hợp cập nhật một entry đã đọc: nó giữ **trạng thái thuộc tính ban đầu**, cho phép setter/add/remove thay đổi trạng thái **trong bộ nhớ**, rồi cung cấp danh sách `ModificationItem[]` mô tả phần thay đổi cần gửi tới LDAP server. `LdapTemplate.modifyAttributes(DirContextOperations)` có thể sử dụng chính danh sách này để thực hiện một LDAP **ModifyRequest**.

### Mục tiêu

Sau bài học, người học có thể:

1. Giải thích vai trò của `DirContextAdapter`, `DirContextOperations` và `AttributeModificationsAware`.
2. Phân biệt **trạng thái ban đầu**, **trạng thái đã chỉnh trong Java** và **trạng thái đã ghi trên server**.
3. Dùng `lookupContext`, `setAttributeValue`, `setAttributeValues`, `addAttributeValue` và `removeAttributeValue` đúng mục đích.
4. Quan sát `getModificationItems()`/`getNamesOfModifiedAttributes()` mà không làm lộ dữ liệu nhạy cảm.
5. Gọi `modifyAttributes(context)` **một lần** để ghi các thay đổi được xác định, hoặc chủ động dùng `ModificationItem[]` khi cần.
6. Xử lý attribute đa trị, null, schema, quyền ghi, dữ liệu bị ẩn, race condition và retry an toàn.
7. Viết integration test với một LDAP directory thực để chứng minh chỉ những field cần thiết bị thay đổi.

## 2. Cơ chế nhận biết thay đổi: từ snapshot tới ModificationItem

`DirContextAdapter` thuộc `org.springframework.ldap.core`. Theo tài liệu Spring LDAP, khi ở **update mode**, nó theo dõi các thay đổi so với những attribute được khởi tạo từ kết quả LDAP lookup/search và cung cấp `getModificationItems()`.

```text
LDAP server
  uid=linh,ou=people,dc=example,dc=org
  mail = linh@example.org
  telephoneNumber = {A, B}
           |
           | ldapTemplate.lookupContext(dn)
           v
DirContextAdapter / DirContextOperations
  trạng thái gốc  : mail=old, phone={A,B}
  trạng thái hiện : mail=old, phone={A,B}
           |
           | setAttributeValue("mail", "new")
           | addAttributeValue("telephoneNumber", "C")
           v
DirContextAdapter (CHỈ Ở JAVA)
  trạng thái gốc  : mail=old, phone={A,B}
  trạng thái hiện : mail=new, phone={A,B,C}
           |
           | getModificationItems()
           v
ModificationItem[] (delta cần ghi)
           |
           | ldapTemplate.modifyAttributes(context)
           v
LDAP server: một yêu cầu Modify tới DN đích
```

Ba điểm quan trọng:

- **Getter/setter không tự gửi request Modify.** Đọc context và thay một field chỉ chỉnh trạng thái object Java cho đến khi gọi phương thức ghi.
- **`getModificationItems()` cũng không tự ghi.** Nó tạo mô tả những thay đổi đang được adapter theo dõi.
- **`modifyAttributes(context)` mới yêu cầu server cập nhật.** Server có thể từ chối vì ACL, schema, dữ liệu đã thay đổi hoặc lỗi kết nối.

Đây là một loại **dirty tracking** ở tầng LDAP, nhưng **không phải** cơ chế persistence context và `flush()` của Hibernate/JPA. Không giả định Spring Data LDAP có session cache hay transaction ACID cho nhiều thao tác như một ORM quan hệ.

### 2.1. Vì sao có thể tạo delta thay vì toàn bộ entry?

`DirContextAdapter` có thể phân biệt:

| Trạng thái gốc | Yêu cầu trong code | Ý định sau cùng |
| --- | --- | --- |
| `mail=old@example.org` | `setAttributeValue("mail","new@example.org")` | Thay giá trị email. |
| Không có `description` | `setAttributeValue("description","Đã đối chiếu")` | Thêm attribute. |
| `telephoneNumber={A,B}` | `addAttributeValue("telephoneNumber","C")` | Thêm một giá trị, giữ A/B. |
| `telephoneNumber={A,B,C}` | `removeAttributeValue("telephoneNumber","B")` | Gỡ giá trị B, giữ A/C. |
| `description=A` | Đặt thành trạng thái không còn attribute | Xóa attribute nếu schema cho phép. |
| `cn=...` | Không sửa | Không chủ động đưa `cn` vào thay đổi. |

Đây là bảng **ý định và trạng thái cuối**, không phải bảo đảm rằng mỗi hàng luôn trở thành đúng **một** mã JNDI cố định. Adapter tính delta dựa trên bản gốc, tập giá trị, cách so sánh và cấu hình phiên bản; khi cần biết chính xác request, đọc `ModificationItem[]` thực tế.

## 3. Những interface và class liên quan

| Thành phần | Vị trí | Công dụng |
| --- | --- | --- |
| `DirContextAdapter` | `org.springframework.ldap.core` | Implementation của `DirContextOperations`; hỗ trợ đọc/sửa attribute và tính delta. |
| `DirContextOperations` | `org.springframework.ldap.core` | Interface thao tác trên entry, có DN và các phương thức truy cập/sửa attribute. |
| `AttributeModificationsAware` | `org.springframework.ldap.core` | Contract cung cấp `getModificationItems()` cho object có khả năng báo những thay đổi. |
| `LdapDataEntry` | `org.springframework.ldap.core` hoặc package được phiên bản API công bố | Các thao tác chung: get/set/add/remove attribute values. |
| `LdapTemplate` | `org.springframework.ldap.core` | `lookupContext(Name)`, `modifyAttributes(DirContextOperations)` hoặc `modifyAttributes(Name, ModificationItem[])`. |
| `ModificationItem` | `javax.naming.directory` | Mỗi mục gồm operation code và `Attribute` cho LDAP Modify. |
| `BasicAttribute` | `javax.naming.directory` | Đóng gói tên thuộc tính và một/nhiều giá trị. |
| `LdapNameBuilder` | `org.springframework.ldap.support` | Dựng DN theo RDN, không nối chuỗi tùy tiện. |

`DirContextAdapter` không thay thế các loại exception của JNDI hoặc ACL phía server. Nó cũng không thay đổi định nghĩa `SINGLE-VALUE` của attribute trong schema LDAP.

### 3.1. Đọc từ server thường đưa adapter vào update mode

Luồng thường dùng:

```java
Name dn = LdapNameBuilder.newInstance("ou=people")
    .add("uid", "linh")
    .build();

DirContextOperations context = ldapTemplate.lookupContext(dn);
context.setAttributeValue("mail", "linh.new@example.org");
ldapTemplate.modifyAttributes(context);
```

`lookupContext` với object factory mặc định của Spring LDAP trả một `DirContextOperations` được hỗ trợ bởi `DirContextAdapter`. Adapter đã nhận **DN** và trạng thái attribute từ lookup, nên có đủ thông tin để lập delta.

Nếu dùng `new DirContextAdapter(...)` để tạo object thủ công, **đừng mặc định** object đó đã ở update mode hoặc có snapshot của entry đang tồn tại. Một adapter chưa được khởi tạo đúng DN/trạng thái/mode không thể thay thế việc lookup entry trước khi cập nhật. Phân biệt rõ:

- **Tạo entry mới:** dựng adapter mới, thiết lập đầy đủ `objectClass`/attribute rồi `bind`.
- **Sửa entry đang có:** `lookupContext` trước, đổi các field cần thiết rồi `modifyAttributes`.

### 3.2. DN là tên entry, không phải một field dữ liệu tùy ý

Trong ví dụ, Spring Boot cấu hình `base=dc=example,dc=org`; vì vậy DN truyền cho `LdapTemplate` là `uid=linh,ou=people`. `uid=linh` là một **RDN** của entry; đổi UID có thể đòi hỏi thao tác **Modify DN/rename**, không chỉ thay attribute `uid`.

Không sử dụng dirty tracking như cách “di chuyển entry sang OU khác”. Một thao tác rename/move trong LDAP có semantics riêng và có thể ảnh hưởng các DN được nhóm hoặc hệ thống ngoài tham chiếu.

## 4. Cấu hình thực hành Spring Boot và LDAP

Giả sử dùng **Java 17**, Spring Boot có starter LDAP và một directory thử nghiệm đã cấu hình `dc=example,dc=org`. Chỉ thực hiện thao tác ghi lên directory **test**, không chạy các ví dụ sửa/xóa trên dữ liệu thật.

Maven:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-ldap</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Cấu hình `application.yml` minh họa:

```yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: dc=example,dc=org
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
```

Chú ý:

- `ldap.example.org` là tên ví dụ, không phải endpoint thật.
- `LDAP_BIND_PASSWORD` phải đến từ môi trường/secret manager, không hard-code hoặc commit vào Git.
- Cần **LDAPS/StartTLS** cùng xác minh chứng chỉ server và cấu hình truststore đúng; URL `ldaps` chỉ hữu ích khi TLS được xác minh thành công.
- Bind account chỉ nên có quyền đọc/ghi những attribute, OU và entry mà ứng dụng thực sự cần.
- Người dùng HTTP được phép gọi endpoint không đồng nghĩa tài khoản bind LDAP có mọi quyền; phân quyền ở cả hai tầng.

### 4.1. Đọc DN tương đối và DN đầy đủ

```text
ContextSource base:
  dc=example,dc=org

DN truyền vào lookupContext:
  uid=linh,ou=people

DN đầy đủ trên server:
  uid=linh,ou=people,dc=example,dc=org
```

Nếu đưa full DN vào `lookupContext` khi base đã chứa `dc=example,dc=org`, có thể tạo lỗi **lặp base** và dẫn tới `NameNotFoundException`. Dùng `LdapNameBuilder` để tránh lỗi RDN/escape.

## 5. Ví dụ tối thiểu: xem thay đổi trước khi ghi

Một cách học rõ cơ chế là **lấy entry → chỉnh attribute → xem delta → ghi → đọc lại**.

```java
package com.example.directory;

import javax.naming.Name;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

public final class MailUpdateExample {
    private final LdapTemplate ldapTemplate;

    public MailUpdateExample(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public void changeMail(String uid, String newMail) {
        Name dn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", uid)
            .build();

        // 1. Nhận snapshot ban đầu và DN từ LDAP.
        DirContextOperations context = ldapTemplate.lookupContext(dn);

        // 2. Chỉnh object Java, CHƯA ghi lên server.
        context.setAttributeValue("mail", newMail);

        // 3. Xem metadata về những thay đổi dự kiến.
        ModificationItem[] changes = context.getModificationItems();
        for (ModificationItem change : changes) {
            System.out.println(
                "op=" + change.getModificationOp()
                + ", attribute=" + change.getAttribute().getID()
            );
        }

        // 4. Chỉ ghi nếu thật sự có thay đổi.
        if (changes.length > 0) {
            ldapTemplate.modifyAttributes(context);
        }
    }
}
```

Giải thích:

1. `lookupContext` nhận entry hiện có. Không dùng `new DirContextAdapter()` để giả làm snapshot trước khi sửa.
2. `setAttributeValue` thay giá trị attribute **trong object**.
3. `getModificationItems()` cho biết delta dưới dạng `ModificationItem[]` gồm mã thao tác và attribute liên quan.
4. `modifyAttributes(context)` lấy DN và delta từ context, rồi gửi **một yêu cầu Modify** đến server nếu có thay đổi.

**Không ghi cả giá trị `change.getAttribute()` vào log**: thay đổi có thể chứa email, số điện thoại, DN nhóm hoặc dữ liệu nhạy cảm. Trong hệ thống thật, chỉ log tên attribute được phép, loại thao tác, request ID và trạng thái, đồng thời kiểm soát dữ liệu cá nhân.

**Không gọi cả hai kiểu ghi cho cùng delta:**

```java
// ĐÚNG: chọn MỘT đường ghi.
ldapTemplate.modifyAttributes(context);

// HOẶC (không dùng đồng thời với dòng trên):
ldapTemplate.modifyAttributes(dn, context.getModificationItems());
```

Nếu gọi cả hai, ứng dụng gửi thao tác lặp lại: `ADD_ATTRIBUTE` có thể gặp giá trị trùng, `REMOVE_ATTRIBUTE` có thể gặp giá trị đã bị xóa hoặc tạo race condition không cần thiết.

## 6. setAttributeValue: thay một giá trị, không phải “append”

`setAttributeValue(String, Object)` có ý nghĩa thiết lập giá trị thuộc tính trong context. Ví dụ:

```java
DirContextOperations context = ldapTemplate.lookupContext(userDn);

String before = context.getStringAttribute("mail");
context.setAttributeValue("mail", "linh.new@example.org");

ModificationItem[] changes = context.getModificationItems();
// Xem op/attribute ID rồi quyết định ghi.
ldapTemplate.modifyAttributes(context);
```

Với một attribute được ứng dụng xử lý như đơn trị, đây là cách đơn giản để cập nhật. Tuy nhiên:

- `mail` trong directory không nhất thiết có `SINGLE-VALUE` ở schema của mọi server; nghiệp vụ có một email chính **không tự sửa cardinality**.
- Nếu một attribute đang có **nhiều giá trị**, dùng `setAttributeValue` là ý định đưa về một giá trị, có nguy cơ làm mất các giá trị khác.
- Nếu input `newMail` không hợp lệ, server có thể báo `invalidAttributeSyntax` hoặc `constraintViolation`. Phải validate ở tầng API/service trước khi sửa.
- Nếu có actor khác sửa email sau lúc lookup, việc gửi Modify của mình vẫn có thể ghi đè giá trị mới của họ. Dirty tracking không tự tạo optimistic locking.

### 6.1. Trạng thái ban đầu và trạng thái hiện tại

Một phép gán có thể làm thay đổi context **ngay lập tức ở Java**:

```java
DirContextOperations ctx = ldapTemplate.lookupContext(userDn);

String originalMail = ctx.getStringAttribute("mail");
ctx.setAttributeValue("mail", "new@example.org");
String localMail = ctx.getStringAttribute("mail");

// localMail là giá trị hiện tại trong adapter;
// điều đó KHÔNG chứng minh server đã ghi.
```

Nếu `modifyAttributes(ctx)` lỗi, context vẫn có thể chứa giá trị mong muốn trong bộ nhớ. **Đọc lại LDAP bằng một lookup mới** để xác minh trạng thái server; không dùng getter trên context vừa thất bại làm bằng chứng ghi thành công.

### 6.2. Null, giá trị vắng mặt và PATCH semantics

Một REST PATCH thường cần phân biệt ba tình huống:

| Yêu cầu HTTP | Ý định | Cách xử lý |
| --- | --- | --- |
| Không có field `description` | Giữ nguyên giá trị cũ. | Không gọi setter cho field này. |
| Có `description` mới | Thay giá trị/tập mô tả theo contract. | Gọi setter tương ứng rồi kiểm tra delta. |
| Yêu cầu xóa `description` | Xóa attribute tùy chọn. | Dùng thao tác xóa rõ ràng theo API và schema. |

Đừng ánh xạ field **không xuất hiện trong JSON** thành `null` rồi tự động gọi `setAttributeValue` cho mọi field: rất dễ biến “không đổi” thành “xóa”. Cần mô hình request có thông tin **field nào được gửi**, hoặc endpoint chuyên biệt cho hành động xóa.

Một attribute bắt buộc theo `objectClass` như `cn` hoặc `sn` của `person` không thể bị xóa nếu kết quả làm entry không hợp lệ. Việc một Java setter nhận null không có nghĩa LDAP server sẽ chấp nhận.

## 7. setAttributeValues và thứ tự của attribute đa trị

Một LDAP attribute có thể chứa nhiều giá trị, ví dụ:

```ldif
telephoneNumber: +84 28 5555 0101
telephoneNumber: +84 90 1111 2222
```

Nếu muốn **thay toàn bộ tập**:

```java
DirContextOperations context = ldapTemplate.lookupContext(userDn);

context.setAttributeValues("telephoneNumber", new String[] {
    "+84 28 5555 0101",
    "+84 90 3333 4444"
});

ModificationItem[] changes = context.getModificationItems();
ldapTemplate.modifyAttributes(context);
```

Sau thao tác thành công, tập mong muốn chứa hai giá trị mới được cung cấp. Số `+84 90 1111 2222` cũ **không được giữ** nếu không nằm trong tập mới.

### 7.1. Không có thứ tự nghiệp vụ mặc định

LDAP multi-valued attributes về cơ bản có ngữ nghĩa tập, không bảo đảm thứ tự ổn định. Nếu một lần đọc trả `{A, B}`, lần sau có thể quan sát `{B, A}` mà dữ liệu không thay đổi về mặt ý nghĩa.

Spring LDAP cung cấp overload cho `setAttributeValues` có tham số `orderMatters`:

```java
context.setAttributeValues(
    "telephoneNumber",
    new String[] {"+84 28 5555 0101", "+84 90 1111 2222"},
    false // Đổi thứ tự đơn thuần không mang nghĩa thay đổi.
);
```

Nếu bật `orderMatters=true`, adapter có thể coi thứ tự input là có ý nghĩa khi xác định delta, nhưng **không biến directory thành bộ lưu danh sách có thứ tự**. Chỉ dùng khi schema/ứng dụng có contract cụ thể về giá trị và thứ tự, rồi kiểm chứng trên LDAP server thực tế.

### 7.2. Chỉ cần thêm một giá trị? Đừng replace tất cả

```text
Trước: phone={A,B}

Mong muốn: thêm C
  addAttributeValue(..., C)      -> {A,B,C}

Không đúng ý định:
  setAttributeValues(..., {C})   -> {C}
                                     A/B có thể bị mất
```

Trong môi trường nhiều service cùng sửa, việc đọc toàn bộ tập rồi replace còn có thể ghi đè giá trị mới mà người khác vừa thêm. Với yêu cầu chỉ thêm/xóa một giá trị, ưu tiên các API thể hiện **thao tác theo giá trị**.

## 8. addAttributeValue và removeAttributeValue

`DirContextOperations` cung cấp:

```java
DirContextOperations context = ldapTemplate.lookupContext(userDn);

context.addAttributeValue(
    "telephoneNumber", "+84 90 3333 4444"
);

context.removeAttributeValue(
    "telephoneNumber", "+84 90 1111 2222"
);

ModificationItem[] changes = context.getModificationItems();
ldapTemplate.modifyAttributes(context);
```

Ý định của đoạn code:

- Giữ `+84 28 5555 0101` (nếu đang tồn tại).
- Thêm `+84 90 3333 4444`.
- Gỡ `+84 90 1111 2222`.
- Không thay đổi những attribute khác như `sn`, `cn` và `objectClass`.

**Lưu ý:** Adapter có thể tạo các mục `ADD_ATTRIBUTE`/`REMOVE_ATTRIBUTE` riêng cho một số giá trị thay đổi, nhưng việc sinh chính xác delta phụ thuộc dữ liệu gốc và cơ chế so sánh; không bảo đảm mỗi lời gọi `addAttributeValue` luôn tương ứng đúng một phần tử trong `getModificationItems()`. Hãy kiểm tra những thao tác được tạo trên phiên bản Spring LDAP thực tế.

### 8.1. Giá trị trùng và equality matching rule

LDAP không phải Java `List` chấp nhận bản sao vô hạn. Server sử dụng **matching rule** của attribute để quyết định hai giá trị có tương đương. Một số field được so sánh không phân biệt hoa/thường hoặc có chuẩn hóa khác.

- `addAttributeValue(...)` hoạt động trên trạng thái Java hiện có và có tùy chọn xử lý duplicate.
- Server vẫn là nơi xác nhận cuối cùng: có thể trả `attributeOrValueExists` nếu một giá trị tương đương đã tồn tại.
- Nếu remove một giá trị mà server không còn có, có thể nhận `noSuchAttribute`.
- Nếu attribute được định nghĩa `SINGLE-VALUE`, thêm giá trị thứ hai có thể bị từ chối theo schema.

Đừng suy ra thành công từ việc context trong bộ nhớ đã thêm giá trị. Chỉ request Modify được server chấp nhận mới có hiệu lực.

### 8.2. Ví dụ member của nhóm

Giả sử entry:

```ldif
dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=linh,ou=people,dc=example,dc=org
member: uid=an,ou=people,dc=example,dc=org
```

Muốn thêm Minh:

```java
Name groupDn = LdapNameBuilder.newInstance("ou=groups")
    .add("cn", "developers")
    .build();

Name fullMemberDn = LdapNameBuilder
    .newInstance("dc=example,dc=org")
    .add("ou", "people")
    .add("uid", "minh")
    .build();

DirContextOperations group = ldapTemplate.lookupContext(groupDn);
group.addAttributeValue("member", fullMemberDn.toString());
ldapTemplate.modifyAttributes(group);
```

`groupDn` là DN tương đối với `ContextSource.base`, còn `member` là thuộc tính chứa **DN đầy đủ**. `LdapNameBuilder` giúp dựng DN không sai escape khi giá trị UID có dấu phẩy, dấu cộng hoặc ký tự đặc biệt.

Đây là ví dụ về **cập nhật một giá trị** của tập đa trị. Nếu dùng `setAttributeValue("member", fullMemberDn.toString())` trong ngữ cảnh này, bạn có thể thay hết các member cũ.

**Cẩn trọng với concurrency:** khi không cần đọc dữ liệu khác và mục tiêu chỉ là thêm một member, một `ModificationItem(ADD_ATTRIBUTE, member)` gửi trực tiếp thường tránh được khoảng thời gian lookup-then-modify; xem mục 11.

## 9. Tự quan sát getModificationItems và tên thuộc tính đã thay đổi

Hai API đáng chú ý:

- `getModificationItems()`: trả mảng `ModificationItem[]` mô tả những thay đổi dự kiến.
- `getNamesOfModifiedAttributes()`: ở `DirContextAdapter`, trả tên những attribute được xác định là đã sửa.

Ví dụ chỉ in metadata phục vụ kiểm thử:

```java
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;
import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.core.DirContextOperations;

DirContextOperations context = ldapTemplate.lookupContext(userDn);
context.setAttributeValue("mail", "new@example.org");
context.addAttributeValue("telephoneNumber", "+84 90 3333 4444");

ModificationItem[] items = context.getModificationItems();
for (ModificationItem item : items) {
    String action = switch (item.getModificationOp()) {
        case DirContext.ADD_ATTRIBUTE -> "ADD";
        case DirContext.REPLACE_ATTRIBUTE -> "REPLACE";
        case DirContext.REMOVE_ATTRIBUTE -> "REMOVE";
        default -> "UNKNOWN";
    };
    System.out.printf("%s %s%n", action, item.getAttribute().getID());
}

if (context instanceof DirContextAdapter adapter) {
    String[] names = adapter.getNamesOfModifiedAttributes();
    // Chỉ dùng names cho audit/metrics đã được giới hạn dữ liệu.
}
```

**Không cần đoán** rằng `setAttributeValue` chắc chắn sinh `REPLACE_ATTRIBUTE` khi attribute ban đầu không tồn tại; trong trường hợp đó, adapter có thể chọn một thay đổi tương đương để thêm attribute. Điều quan trọng là **trạng thái nghiệp vụ cuối** và request hợp lệ, không phải đoán mã operation chỉ từ tên setter.

### 9.1. Xác minh “không đổi gì”

```java
DirContextOperations context = ldapTemplate.lookupContext(userDn);
ModificationItem[] baseline = context.getModificationItems();
// Với context vừa lookup và chưa sửa, baseline thường rỗng.

String existing = context.getStringAttribute("mail");
context.setAttributeValue("mail", existing);

ModificationItem[] afterSameValue = context.getModificationItems();
// Với những thuộc tính có so sánh rõ ràng, thường không phát sinh
// thay đổi thực sự; kiểm thử trên phiên bản/framework/schema cụ thể.
```

Không phụ thuộc hoàn toàn vào con số delta trong một trường hợp có matching rule đặc biệt, giá trị binary hoặc thứ tự không ổn định. Nếu nghiệp vụ không cần update, có thể so sánh/validate dữ liệu trước khi gọi setter để giảm thay đổi không cần thiết.

### 9.2. Không dùng getModificationItems để xác nhận ghi thành công

```text
getModificationItems() = kế hoạch ghi (in-memory)
modifyAttributes(...)  = yêu cầu server thực hiện
lookupContext(...) mới = quan sát trạng thái đã ghi
```

Đây là ba giai đoạn khác nhau. Nếu một lệnh Modify lỗi vì ACL, getModificationItems vẫn có thể mô tả đúng kế hoạch nhưng server không được cập nhật.

## 10. Update mode và phương thức update() của adapter

`DirContextAdapter` có trạng thái **update mode**. Với đối tượng nhận qua `lookupContext` mặc định, hạ tầng Spring LDAP đã xử lý việc khởi tạo để theo dõi thay đổi.

Một số API có thể gây nhầm:

| API | Ý nghĩa | Không nên nhầm với |
| --- | --- | --- |
| `setUpdateMode(true)` | Chuyển adapter sang chế độ theo dõi cập nhật, khi khởi tạo thủ công phù hợp. | Một lệnh gửi dữ liệu tới LDAP. |
| `getModificationItems()` | Lấy mảng thay đổi kể từ trạng thái nền. | Commit trên server. |
| `update()` trên adapter | Cập nhật snapshot/nền **trong object** từ trạng thái hiện tại và quên các modification đang theo dõi. | `ldapTemplate.modifyAttributes(...)`. |
| `ldapTemplate.modifyAttributes(context)` | Gửi delta tới LDAP server. | Gọi `context.update()`. |
| `ldapTemplate.bind(context)` | **Tạo entry** mới từ context đã thiết lập DN/attributes. | Cập nhật entry cũ. |

**Bẫy đặc biệt:** gọi `context.update()` trước `ldapTemplate.modifyAttributes(context)` có thể làm **mất danh sách thay đổi đang chờ**. Theo Javadoc, `update()` khiến snapshot nội bộ được đồng bộ với trạng thái hiện tại và `getModificationItems()` trở thành rỗng; nó **không** thực hiện LDAP Modify.

```java
DirContextOperations context = ldapTemplate.lookupContext(userDn);
context.setAttributeValue("mail", "new@example.org");

// KHÔNG gọi context.update() ở đây để "lưu".
// context.update();      // chỉ reset trạng thái trong bộ nhớ!

ldapTemplate.modifyAttributes(context);
```

Khi muốn sửa tiếp trong vòng đời dài, nên tạo **lookup mới** sau khi ghi để nhận trạng thái server hiện tại, thay vì giả định adapter giữ đồng bộ vĩnh viễn với các thay đổi từ người khác.

### 10.1. Tạo mới bằng DirContextAdapter khác với cập nhật

Khi chưa tồn tại entry, có thể dựng context mới và bind:

```java
import javax.naming.Name;
import org.springframework.ldap.core.DirContextAdapter;
import org.springframework.ldap.support.LdapNameBuilder;

Name newDn = LdapNameBuilder.newInstance("ou=people")
    .add("uid", "lab-user")
    .build();

DirContextAdapter fresh = new DirContextAdapter(newDn);
fresh.setAttributeValues("objectClass", new String[] {
    "top", "person", "organizationalPerson", "inetOrgPerson"
});
fresh.setAttributeValue("uid", "lab-user");
fresh.setAttributeValue("cn", "Lab User");
fresh.setAttributeValue("sn", "User");

ldapTemplate.bind(fresh); // Tạo entry, không phải Modify.
```

Chỉ chạy trên directory test có OU phù hợp và account có quyền tạo entry. `bind` yêu cầu DN/`objectClass`/attribute hợp lệ theo schema; nếu DN đã tồn tại sẽ bị từ chối. Không dùng `bind` thay `modifyAttributes` để “ghi đè” entry.

## 11. So sánh adapter với ModificationItem[] thủ công

Có hai cách cập nhật LDAP thường gặp:

### 11.1. Adapter: đọc, chỉnh object, lấy delta

```java
DirContextOperations ctx = ldapTemplate.lookupContext(userDn);
ctx.addAttributeValue("telephoneNumber", "+84 90 3333 4444");
ldapTemplate.modifyAttributes(ctx);
```

Ưu điểm:

- Phù hợp khi service đã phải đọc entry để hiển thị hoặc tính nhiều thay đổi.
- Không phải tự dựng từng `BasicAttribute` và `ModificationItem`.
- Có thể quan sát tên các attribute dự kiến thay đổi.
- Tránh đưa vào Modify những field không cần chỉnh nếu code chỉ dùng setter cho field liên quan.

Đổi lại, phải hiểu trạng thái gốc của context, null/attribute vắng, update mode, cách tính delta và vấn đề đồng thời giữa **lookup** và **modify**.

### 11.2. ModificationItem: tác động trực tiếp, không cần lookup

```java
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.DirContext;
import javax.naming.directory.ModificationItem;

ModificationItem addPhone = new ModificationItem(
    DirContext.ADD_ATTRIBUTE,
    new BasicAttribute("telephoneNumber", "+84 90 3333 4444")
);

ldapTemplate.modifyAttributes(
    userDn, new ModificationItem[] {addPhone}
);
```

Ưu điểm:

- Diễn đạt rất rõ “chỉ thêm giá trị này” hoặc “chỉ xóa giá trị này”.
- Không cần đọc toàn bộ entry trước; giảm request và khoảng thời gian dễ gặp **lost update**.
- Có thể dùng khi operational attribute không được đọc qua `lookupContext` nhưng policy thật sự cho phép sửa nó.

Giới hạn:

- Developer phải chọn chính xác operation và bộ giá trị.
- Nếu giá trị đã tồn tại, ADD có thể trả `attributeOrValueExists`.
- Nếu giá trị không tồn tại, REMOVE có thể trả `noSuchAttribute`.
- Vẫn cần kiểm tra schema, DN, ACL, input escaping và trạng thái không rõ sau timeout.

### 11.3. Bảng quyết định

| Nhu cầu | Ưu tiên | Lý do |
| --- | --- | --- |
| Cập nhật vài field đơn giản sau khi đọc hồ sơ | `DirContextAdapter`/`DirContextOperations` | Tính delta từ dữ liệu đã đọc. |
| Chỉ thêm một số điện thoại, không cần giá trị cũ | `ModificationItem(ADD_ATTRIBUTE, ...)` | Không cần lookup; ý định rõ ràng. |
| Chỉ gỡ một DN khỏi tập `member` | `ModificationItem(REMOVE_ATTRIBUTE, ...)` | Ít nguy cơ replace toàn tập thành viên. |
| Chỉnh nhiều field của cùng một entry trong một lượt | Adapter + `modifyAttributes(context)` hoặc một mảng `ModificationItem[]` | Có thể gửi một LDAP ModifyRequest. |
| Thay toàn bộ tập giá trị theo hợp đồng API | `setAttributeValues` hoặc `REPLACE_ATTRIBUTE` | Phải chấp nhận mất những giá trị cũ ngoài tập mới. |
| Tạo một entry mới | `bind`/repository tạo mới | Không phải Dirty update của entry đã tồn tại. |
| Đổi DN/RDN/OU | `rename`/Modify DN (với policy) | Không phải chỉ update attribute bình thường. |

## 12. Điểm mù khi một attribute không được đọc

Một điểm đặc biệt quan trọng của `DirContextAdapter`: **nó xác định delta dựa trên những attribute có trong snapshot ban đầu của nó**. Theo FAQ của Spring LDAP, các **operational attributes** thường **không được trả về trừ khi yêu cầu đích danh**.

Nếu adapter không có attribute trong dữ liệu lookup, lời gọi:

```java
DirContextOperations context = ldapTemplate.lookupContext(userDn);
context.removeAttributeValue("someOperationalAttribute", "value");
ldapTemplate.modifyAttributes(context);
```

có thể **không tạo thay đổi có ý nghĩa**, bởi adapter không biết giá trị đó đã hiện diện ở server. Điều tương tự có thể xảy ra với attribute không được trả vì projection hoặc ACL.

### 12.1. Không coi snapshot thiếu attribute là bằng chứng server không có dữ liệu

Giả sử server có `telephoneNumber={A,B}` nhưng bind account chỉ được đọc `cn`. Nếu adapter quan sát `telephoneNumber` như **vắng mặt**, nó không thể tính delta chính xác dựa trên tập thật của server. Đây không phải lỗi của dirty tracking mà là **giới hạn thông tin đầu vào**.

Những nguyên nhân cần phân biệt:

| Hiện tượng | Khả năng | Cách kiểm tra |
| --- | --- | --- |
| `getStringAttributes("telephoneNumber")==null` | Không có attribute, bị ACL ẩn hoặc lookup chỉ lấy projection hẹp. | So sánh quyền và projection với tài khoản test đủ quyền. |
| Operational field không xuất hiện | Theo mặc định, server không trả operational attributes. | Yêu cầu tên attr cụ thể bằng API hỗ trợ. |
| `getModificationItems()` rỗng sau remove | Context không có giá trị cần xóa hoặc thao tác không tạo delta. | Kiểm tra trạng thái gốc và ACL, không giả định server đã sửa. |
| Lookup thành công nhưng Modify bị từ chối | Quyền read và quyền write khác nhau. | Kiểm tra ACL server, không tự đổi sang admin bind. |

### 12.2. Hai hướng xử lý được Spring LDAP đề cập

1. **Đọc đúng những attribute cần thiết** qua overload lookup/search cho phép truyền danh sách attribute, rồi dùng `ContextMapper` trả `DirContextAdapter` hoặc `DirContextOperations` hợp lệ để xác định delta.
2. **Gửi `ModificationItem[]` thủ công** khi có yêu cầu sửa theo giá trị cụ thể, không cần snapshot đầy đủ và account có quyền hợp lệ.

Ví dụ hướng thứ hai:

```java
ModificationItem change = new ModificationItem(
    DirContext.REMOVE_ATTRIBUTE,
    new BasicAttribute("description", "Một ghi chú cũ")
);
ldapTemplate.modifyAttributes(userDn, new ModificationItem[] {change});
```

Không dùng ví dụ này để sửa thuộc tính operational do server quản lý như `createTimestamp` hoặc `entryUUID` — dù có yêu cầu đích danh, chúng thường không cho user modification. “Không đọc được” cũng **không** phải lý do để cấp quyền ghi quá rộng.

## 13. Tầng service: viết đúng PATCH semantics

Một service nên có phương thức **chuyên biệt** cho loại thay đổi được phép, thay vì đưa raw tên attribute và operation code từ HTTP request vào LDAP.

```java
package com.example.directory;

import java.util.Objects;
import javax.naming.Name;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;
import org.springframework.stereotype.Service;

@Service
public class DirectoryContactService {
    private final LdapTemplate ldapTemplate;

    public DirectoryContactService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public boolean changeEmail(String uid, String email) {
        Objects.requireNonNull(uid);
        Objects.requireNonNull(email);
        // Trong ứng dụng thực tế: validate email, quyền người gọi và UID.

        Name dn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", uid)
            .build();

        DirContextOperations ctx = ldapTemplate.lookupContext(dn);
        if (Objects.equals(ctx.getStringAttribute("mail"), email)) {
            return false; // Không có thay đổi nghiệp vụ cần ghi.
        }

        ctx.setAttributeValue("mail", email);
        if (ctx.getModificationItems().length == 0) {
            return false;
        }

        ldapTemplate.modifyAttributes(ctx);
        return true;
    }
}
```

**Giới hạn ví dụ:** `return true` nghĩa là phương thức `modifyAttributes` hoàn tất mà không ném ngoại lệ; nó không bảo đảm actor khác không sửa lại entry ngay sau đó. Nếu cần quyết định chặt theo trạng thái hiện tại, phải dùng cơ chế phù hợp với directory và nghiệp vụ.

### 13.1. DTO chỉ bao gồm field được phép sửa

Thay vì:

```text
PATCH /ldap/entries/{dn}
{
  "attributeName": "objectClass",
  "operation": "REPLACE_ATTRIBUTE",
  "value": "..."
}
```

thiết kế API:

```text
PATCH  /users/{uid}/contact-email
POST   /users/{uid}/phone-numbers
DELETE /users/{uid}/phone-numbers/{phoneId}
```

Tầng service giới hạn attribute được sửa: `mail`, `telephoneNumber`. Những thuộc tính như `objectClass`, `userPassword`, `member` của nhóm đặc quyền và DN/RDN cần quyền/luồng riêng. DTO validation và Spring Security bảo vệ HTTP, nhưng **LDAP ACL của bind account** vẫn là lớp bắt buộc.

### 13.2. Đổi DN không chỉ là sửa uid

Nếu RDN là `uid=linh`, việc thay `uid` trong adapter mà không đổi DN có thể làm entry không nhất quán hoặc bị schema/naming constraint từ chối. Khi nghiệp vụ đổi định danh, cần xem xét `LdapTemplate.rename(oldDn,newDn)`, tham chiếu nhóm và tác động hệ thống ngoài. Không dùng `setAttributeValue("uid", "...")` như giải pháp đổi DN tổng quát.

## 14. DirContextAdapter so với ODM repository

Spring Data LDAP ODM ánh xạ entry sang một Java entity:

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
    private String mail;

    public DirectoryPerson() {}
    // Bổ sung getters/setters cần thiết trong project thật.
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

| ODM/`LdapRepository.save(entity)` | `DirContextAdapter` + `LdapTemplate` |
| --- | --- |
| Làm việc chủ yếu với **entity Java** và annotation. | Làm việc với **entry context** và các attribute cụ thể. |
| Phù hợp nghiệp vụ CRUD tài liệu người dùng theo model. | Phù hợp quan sát delta hoặc sửa chính xác một số field. |
| Framework quyết định cách lưu từ mapping/trạng thái entity. | Có thể xem `getModificationItems()` trước khi ghi. |
| Cần kiểm soát mapping của field đa trị và DN. | Cần hiểu snapshot, update mode và cơ chế delta. |
| Không tự cấp quyền ghi mọi attribute. | Cũng không vượt qua schema hoặc LDAP ACL. |

Không coi repository là “cơ chế lưu SQL” có khả năng rollback mọi field/entry. **Cả hai cách đều dùng LDAP operations** và chịu ràng buộc của server. Với yêu cầu chỉ thêm một member của nhóm nhiều người, `ModificationItem(ADD_ATTRIBUTE)` trực tiếp có thể phù hợp hơn việc lưu lại nguyên tập.

## 15. Atomicity và cập nhật đồng thời

### 15.1. Một ModifyRequest được áp dụng nguyên tử

Theo RFC 4511, các modification trong **một** LDAP ModifyRequest được thực hiện theo thứ tự và như một thao tác nguyên tử đối với entry đó. `ldapTemplate.modifyAttributes(context)` có thể gửi các `ModificationItem` được adapter tính ra trong một yêu cầu như vậy.

```text
lookupContext(dn)
    |
set mail
add telephoneNumber
    |
getModificationItems() -> [các thay đổi cần ghi]
    |
modifyAttributes(context) -> một LDAP ModifyRequest
    |
server chấp nhận toàn bộ hoặc từ chối theo semantics Modify
```

Tuy nhiên, đây **không** phải transaction ACID xuyên:

- Hai lần gọi `modifyAttributes` khác nhau.
- Hai entry khác DN (ví dụ sửa người dùng rồi sửa nhóm).
- LDAP và SQL database.
- Một HTTP API rồi một message queue hoặc remote service khác.

Nếu nghiệp vụ cần nhiều hệ thống cùng nhất quán, thiết kế bù trừ/đối soát hoặc cơ chế transaction riêng được server hỗ trợ; không giả định `@Transactional` của JPA sẽ rollback LDAP.

### 15.2. Dirty tracking không ngăn lost update

```text
T0:  telephoneNumber={A,B}
T1:  Service X lookup -> snapshot {A,B}
T2:  Service Y ADD C  -> server {A,B,C}
T3:  Service X setAttributeValues({A,D})
T4:  X gửi Modify     -> có thể thay/ghi đè tập chứa C
```

Mặc dù X dùng `DirContextAdapter`, snapshot của X đã **cũ**. Nếu X thay toàn tập, Y có thể mất C. Để chỉ thêm D, dùng `addAttributeValue` hoặc `ModificationItem(ADD_ATTRIBUTE, D)`; tránh `REPLACE` toàn tập khi không cần.

Đối với yêu cầu “chỉ sửa nếu entry không đổi kể từ lúc đọc”, phải xem cơ chế assertion/conditional update hoặc concurrency control **thực sự được server hỗ trợ** và chính sách nghiệp vụ. `DirContextAdapter` **không tự bổ sung optimistic lock**.

### 15.3. Sau timeout không biết chắc server đã ghi hay chưa

Khi gọi `modifyAttributes(context)`, một lỗi mạng có thể xảy ra **sau khi server đã xử lý request** nhưng trước khi client nhận phản hồi. Do đó:

1. Ghi nhận lỗi là **trạng thái chưa xác định**, không tự kết luận “chưa ghi”.
2. Dùng kết nối hợp lệ để đọc lại entry.
3. So sánh trạng thái server với mục tiêu nghiệp vụ.
4. Chỉ retry khi cần, có giới hạn và lưu ý giá trị đã được thêm/xóa.

Sau một lần ghi, adapter cũ có thể không phản ánh các thay đổi từ actor khác; nên lấy context mới cho lần cập nhật tiếp theo.

## 16. Chẩn đoán lỗi khi dùng adapter

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Setter đã chạy nhưng LDAP không đổi | Chưa gọi `modifyAttributes`, hoặc delta rỗng. | Kiểm tra `getModificationItems()` và đường ghi. |
| `getModificationItems()` rỗng dù tưởng có thay đổi | Giá trị bằng trạng thái cũ; đã gọi `update()`; attribute không có trong snapshot; code sửa ngoài API được hỗ trợ. | Kiểm tra trình tự lookup/set/get, không gọi `update()` trước khi ghi. |
| Đọc lại object hiện tại thấy email mới nhưng server vẫn cũ | Getter của adapter đọc **trạng thái local**. | Dùng `lookupContext` mới để xác minh server. |
| Chỉ thêm một số nhưng số cũ biến mất | `setAttributeValue` hoặc `setAttributeValues` đã thay toàn tập. | Dùng `addAttributeValue` hoặc `ModificationItem ADD`. |
| Không xóa được một operational attribute | Lookup không yêu cầu/không được phép đọc attribute; một số attr không cho user modify. | Kiểm tra projection, schema, ACL; không cố sửa metadata do server quản lý. |
| `NameNotFoundException` | DN tương đối/base sai hoặc entry không tồn tại. | So sánh `ContextSource.base` và DN thực bằng `ldapsearch`. |
| `NoPermissionException` | Bind account không có quyền Modify. | Rà soát ACL tối thiểu, không dùng admin để né lỗi. |
| `SchemaViolationException` | Vi phạm `objectClass`, thiếu `MUST` hoặc vượt cardinality. | Kiểm tra schema và tập giá trị sau thay đổi. |
| `attributeOrValueExists` | ADD giá trị đã tồn tại. | Kiểm tra matching rule và trạng thái hiện có. |
| `noSuchAttribute` | REMOVE attribute/giá trị không tồn tại. | Xác nhận yêu cầu remove và giá trị thực trên server. |
| `CommunicationException` | TLS, DNS, timeout hoặc server unavailable. | Kiểm tra kênh truyền và trạng thái chưa xác định sau Modify. |
| Update sai entry | RDN/base bị lặp hoặc client xây DN bằng string không escape. | Dùng `LdapNameBuilder`, kiểm tra DN trước khi ghi. |

**Không** catch mọi `NamingException` rồi trả “không có thay đổi” hoặc “người dùng không tồn tại”. Nếu một Modify bị từ chối, hệ thống cần báo lỗi theo nguyên nhân và giữ cause cho việc chẩn đoán nội bộ; không trả raw LDAP diagnostic message chứa dữ liệu nhạy cảm ra API.

### 16.1. Những thay đổi nào có thể không được adapter quan sát?

- Attribute không được trả khi lookup, do ACL hoặc chỉ định projection.
- Operational attribute không được yêu cầu đích danh.
- Thay đổi xảy ra trên server **sau** thời điểm lookup.
- Những thay đổi thực hiện bằng JNDI API khác bên ngoài object adapter.
- Sửa trực tiếp cấu trúc nội bộ được trả từ getter thay vì dùng `setAttributeValue`, `addAttributeValue` hoặc `removeAttributeValue`, khi API không bảo đảm nhận biết cách sửa đó.

Vì vậy, dirty tracking của adapter là **cơ chế tính delta từ trạng thái mà nó biết**, không phải một hệ thống audit thay đổi toàn directory.

## 17. Integration test trên LDAP directory thực

Unit test với mock có thể chứng minh service gọi `modifyAttributes(context)` và không gọi khi delta rỗng. Tuy nhiên, **integration test** mới xác minh LDAP server thực sự hiểu Modify, schema, ACL và trạng thái thuộc tính sau ghi.

### 17.1. Ma trận kiểm thử

| Trường hợp | Thao tác | Kỳ vọng |
| --- | --- | --- |
| Context mới lookup chưa chỉnh | `getModificationItems()` | Mảng rỗng. |
| Đổi `mail` | `setAttributeValue` rồi lấy delta | Có thay đổi liên quan `mail`; server cập nhật khi Modify thành công. |
| Thêm một phone | `addAttributeValue` | Không mất phone cũ. |
| Gỡ một phone | `removeAttributeValue` | Phone khác được giữ. |
| Đặt tập phone mới | `setAttributeValues` | Tập trên server khớp tập mới, không phụ thuộc thứ tự. |
| Chỉnh local, chưa Modify | Getter trên adapter | Có giá trị mới, nhưng lookup mới từ server vẫn có giá trị cũ. |
| Gọi `update()` trước Modify | Kiểm tra delta | Adapter quên pending changes; không dùng để commit. |
| Attribute lookup không được trả | Remove giá trị bị ẩn | Không giả định có delta; kiểm tra projection/ACL. |
| Reader không có quyền write | `modifyAttributes` | Bị server từ chối. |
| Xóa field `MUST` | Gỡ `sn` cuối | Bị schema từ chối; entry không thay đổi một phần. |
| ADD giá trị trùng | Thêm lại phone hiện có | Server có thể từ chối, phải xử lý trạng thái. |
| Update concurrent | Hai client cùng chỉnh | Tài liệu hóa lost update và bảo vệ nếu cần. |

### 17.2. Ví dụ integration test: tính delta rồi đối chiếu trên server

Test JUnit 5 dưới đây giả định Spring Boot test profile kết nối tới directory **test**, có sẵn `ou=people` và bind account được phép tạo/sửa/xóa fixture. Không chạy trên directory production.

```java
package com.example.directory;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Arrays;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;
import javax.naming.Name;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;
import javax.naming.directory.BasicAttribute;
import javax.naming.directory.BasicAttributes;
import javax.naming.directory.ModificationItem;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ldap.core.DirContextOperations;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.support.LdapNameBuilder;

@SpringBootTest
class DirContextAdapterChangesIT {

    @Autowired
    private LdapTemplate ldap;

    @Test
    void tracksThenWritesOnlyRequestedChanges() {
        String uid = "lab" + UUID.randomUUID()
            .toString().replace("-", "").substring(0, 10);
        Name dn = LdapNameBuilder.newInstance("ou=people")
            .add("uid", uid)
            .build();

        Attributes attributes = new BasicAttributes(true);
        Attribute classes = new BasicAttribute("objectClass");
        classes.add("top");
        classes.add("person");
        classes.add("organizationalPerson");
        classes.add("inetOrgPerson");
        attributes.put(classes);
        attributes.put("uid", uid);
        attributes.put("cn", "Lab " + uid);
        attributes.put("sn", "Test");
        attributes.put("mail", "old@example.org");
        attributes.put("telephoneNumber", "+84 28 5555 0101");

        boolean created = false;
        try {
            ldap.bind(dn, null, attributes);
            created = true;

            DirContextOperations context = ldap.lookupContext(dn);
            assertThat(context.getModificationItems()).isEmpty();

            context.setAttributeValue("mail", "new@example.org");
            context.addAttributeValue(
                "telephoneNumber", "+84 90 3333 4444");

            ModificationItem[] changes = context.getModificationItems();
            Set<String> modifiedAttributeNames = Arrays.stream(changes)
                .map(item -> item.getAttribute().getID().toLowerCase())
                .collect(Collectors.toSet());

            assertThat(modifiedAttributeNames)
                .contains("mail", "telephonenumber");

            // Chưa commit: server vẫn giữ email cũ.
            assertThat(ldap.lookupContext(dn)
                .getStringAttribute("mail")).isEqualTo("old@example.org");

            ldap.modifyAttributes(context);

            DirContextOperations after = ldap.lookupContext(dn);
            assertThat(after.getStringAttribute("mail"))
                .isEqualTo("new@example.org");
            assertThat(after.getStringAttributes("telephoneNumber"))
                .containsExactlyInAnyOrder(
                    "+84 28 5555 0101",
                    "+84 90 3333 4444"
                );
            assertThat(after.getStringAttribute("sn"))
                .isEqualTo("Test");
        } finally {
            if (created) {
                ldap.unbind(dn);
            }
        }
    }
}
```

Những điều test chứng minh trong một môi trường phù hợp:

- Adapter sau lookup có baseline; chỉnh một vài attribute tạo delta.
- **Trước Modify**, server chưa đổi.
- **Sau Modify**, email mới và hai số điện thoại được đọc lại từ server.
- `sn` không bị mất dù service không chủ động cập nhật nó.

Không kiểm tra thứ tự các `ModificationItem` hoặc số byte của request nếu framework không hứa hẹn contract đó. Kết quả phụ thuộc schema và ACL của LDAP server test; nếu `finally` bị lỗi network, cần dọn fixture bằng quy trình test riêng. Đoạn code ở đây là tài liệu tham khảo, chưa được build/chạy trong bước biên soạn.

### 17.3. Negative test và atomicity

Trên directory test, bổ sung các trường hợp:

1. Bind với account chỉ đọc; thử `modifyAttributes` rồi xác nhận server từ chối.
2. Gỡ toàn bộ `sn` của một entry `person`; xác nhận lỗi schema và entry giữ nguyên.
3. Gửi `ModificationItem[]` với hai thay đổi, một thay đổi không hợp lệ; kiểm tra tính nguyên tử của **một** LDAP ModifyRequest.
4. Cho hai client cùng đọc và cập nhật một attribute đa trị; ghi lại khi nào `REPLACE` toàn tập gây lost update.
5. Thử timeout/mất kết nối và cách đối soát trạng thái sau request.

Những bài kiểm thử này cần directory chuyên dụng, không đụng dữ liệu/nhóm của người thật.

## 18. Chẩn đoán bằng ldapsearch và quan sát request

Để xác minh trạng thái trên server sau khi ghi:

```bash
ldapsearch -x \
  -H "ldaps://ldap.example.org:636" \
  -D "uid=svc-reader,ou=service-accounts,dc=example,dc=org" -W \
  -b "uid=linh,ou=people,dc=example,dc=org" -s base \
  "(objectClass=*)" uid cn sn mail telephoneNumber
```

Ở đây `ldapsearch -b` dùng **DN đầy đủ**, còn `LdapTemplate.lookupContext` với `ContextSource.base=dc=example,dc=org` dùng DN tương đối.

Khi cần chẩn đoán sâu:

- So sánh giá trị trước/sau bằng `ldapsearch` với **chính principal** mà ứng dụng dùng.
- Xem tên attribute và mã operation trong `getModificationItems()`, không log toàn bộ giá trị nhạy cảm.
- Xác nhận schema `MUST`/`MAY` và `SINGLE-VALUE` nếu server từ chối.
- Kiểm tra `ContextSource.base`, escaping DN và filter nếu tìm sai entry.
- Xem LDAP server logs được phân quyền nếu cần chứng minh request Modify đã đến server.
- Với lỗi PKIX/TLS, xác minh truststore và hostname; không tắt certificate verification.

### 18.1. Những hành vi dễ làm dữ liệu sai

| Thói quen | Hậu quả | Thay thế |
| --- | --- | --- |
| Gọi `context.update()` để “lưu”. | Xóa pending delta nội bộ, không gửi LDAP Modify. | Gọi `ldapTemplate.modifyAttributes(context)`. |
| Sau setter thấy getter trả mới nên báo thành công. | Chỉ xác minh Java object. | Ghi rồi lookup lại khi cần đối soát. |
| Set mọi field từ DTO, kể cả null chưa được gửi. | Có thể xóa field ngoài ý định. | PATCH tri-state/allowlist. |
| Set một phone mới vào attribute đa trị. | Có thể thay hết phone cũ. | `addAttributeValue`/`ADD_ATTRIBUTE`. |
| Thay cả member group để thêm một DN. | Mất các thành viên khác, nhất là khi có concurrent write. | `addAttributeValue` hoặc `ADD_ATTRIBUTE` theo DN. |
| Bật quyền LDAP admin để sửa lỗi. | Tăng phạm vi thiệt hại khi ứng dụng có lỗi. | Cấp ACL tối thiểu và chẩn đoán schema. |
| Bỏ qua `PartialResultException`/lỗi search. | Snapshot có thể không đầy đủ. | Xử lý lỗi thay vì coi dữ liệu là chính xác. |
| Gọi `modifyAttributes(context)` và `modifyAttributes(dn, items)` liên tiếp. | Gửi thay đổi hai lần. | Chọn một đường ghi. |

## 19. Bài tập vận dụng

1. Với entry có `mail=old`, `telephoneNumber={A,B}` và `sn=Nguyen`, dùng `lookupContext`, đổi mail và thêm C. Trước khi ghi, mô tả dữ liệu nào nằm trong adapter và dữ liệu nào vẫn còn trên server.
2. Viết method trả **tên attribute dự kiến sửa** từ `getModificationItems()`. Vì sao không nên log toàn bộ giá trị?
3. So sánh `setAttributeValue("telephoneNumber","C")`, `setAttributeValues("telephoneNumber",{"A","C"})` và `addAttributeValue("telephoneNumber","C")` khi trạng thái trước là `{A,B}`.
4. Một lập trình viên gọi `context.update()` ngay sau setter rồi `modifyAttributes(context)`. Dự đoán kết quả, giải thích theo update mode và sửa code.
5. Thiết kế PATCH email có ba tình huống: field không gửi, field có giá trị mới, yêu cầu xóa field tùy chọn. Làm sao tránh vô tình xóa thông tin?
6. Tạo integration test với LDAP test xác nhận email trên server **chưa đổi trước Modify** và **đã đổi sau Modify**. Test cũng phải xác nhận `sn` vẫn nguyên.
7. Một attribute không xuất hiện trong `lookupContext` vì quyền read bị chặn. Phân tích vì sao `removeAttributeValue` có thể không tạo delta và khi nào dùng `ModificationItem[]` trực tiếp.
8. So sánh dirty tracking của `DirContextAdapter` với `LdapRepository.save(entity)`. Khi nào nên dùng explicit `ADD_ATTRIBUTE`?
9. Hai service cập nhật cùng tập `member`. Viết timeline minh họa lost update do `setAttributeValues` và cách dùng ADD/REMOVE theo giá trị để giảm rủi ro.
10. Phân biệt `getModificationItems()`, `ldapTemplate.modifyAttributes(context)` và `ldapTemplate.bind(context)`: cái nào chỉ tính toán, cái nào ghi, cái nào tạo mới?
11. Giải thích vì sao một ModifyRequest có thể nguyên tử nhưng nhiều ModifyRequest hoặc LDAP+SQL không tự thành transaction.
12. Nêu cách đối soát sau `CommunicationException` khi một phép ADD số điện thoại có thể đã được server thực hiện.

### Checklist trước khi bàn giao tính năng

- [ ] Đã xác định đúng DN tương đối so với `ContextSource.base`.
- [ ] `lookupContext` lấy đúng entry và đủ những attribute cần chỉnh.
- [ ] Có giải thích rõ update mode và trạng thái baseline của adapter.
- [ ] Setter/add/remove được gọi đúng ý định nghiệp vụ.
- [ ] Đã kiểm tra `getModificationItems()` hoặc tên field được sửa.
- [ ] Không gọi `update()` để thay cho Modify.
- [ ] Chỉ gọi **một** đường ghi cho cùng delta.
- [ ] Không dùng `REPLACE` toàn tập khi chỉ thêm/gỡ một giá trị.
- [ ] Schema `MUST`/`MAY`/`SINGLE-VALUE` và LDAP ACL đã được xem xét.
- [ ] Tránh ghi đè thay đổi đồng thời hoặc đã có chiến lược xử lý.
- [ ] Secret/TLS/filter/DN escaping được cấu hình và kiểm tra.
- [ ] Có integration test trên directory riêng, gồm positive/negative cases.
- [ ] Có xử lý retry sau lỗi chưa xác định trạng thái.

## 20. Tài liệu tham khảo

- [Spring LDAP — Simplifying Attribute Access and Manipulation with DirContextAdapter](https://docs.spring.io/spring-ldap/reference/dirobjectfactory.html): tạo `DirContextAdapter`, quản lý attribute, lấy modification và ghi qua LDAP.
- [Spring LDAP API — DirContextAdapter](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/DirContextAdapter.html): update mode, `getModificationItems()`, `getNamesOfModifiedAttributes()`, `update()` và các setters.
- [Spring LDAP API — LdapTemplate](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): `lookupContext`, `modifyAttributes(DirContextOperations)`, `bind` và những overload khác.
- [Spring LDAP FAQ — Operational Attributes](https://docs.spring.io/spring-ldap/reference/faq.html): trường hợp adapter không có operational attribute trong snapshot và phương án xử lý.
- [Spring LDAP API — LdapDataEntry](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/LdapDataEntry.html): `getStringAttributes`, `setAttributeValues`, `addAttributeValue`, `removeAttributeValue`.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): repository, ODM và CRUD trên directory.
- [RFC 4511 — LDAP Protocol](https://www.rfc-editor.org/rfc/rfc4511): LDAP ModifyRequest và tính nguyên tử của một request.
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): entry, attribute, `objectClass` và schema.
- [RFC 4514 — DN String Representation](https://www.rfc-editor.org/rfc/rfc4514) và [RFC 4515 — LDAP Search Filter](https://www.rfc-editor.org/rfc/rfc4515): escape an toàn cho DN và filter.
- [Java SE 17 — ModificationItem](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/ModificationItem.html) và [DirContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.naming/javax/naming/directory/DirContext.html): JNDI ADD/REPLACE/REMOVE semantics.
