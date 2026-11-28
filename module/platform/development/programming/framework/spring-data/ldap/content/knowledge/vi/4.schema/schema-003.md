# Quan hệ kế thừa giữa các object class

> **Chương:** Schema  
> **Phạm vi:** SPRING_DATA_LDAP — truy cập LDAP bằng Spring Data LDAP, ánh xạ entry trong cây thư mục thành đối tượng Java, truy vấn bằng `LdapRepository`/`LdapTemplate` và thực hiện CRUD theo schema của directory server.

Trong LDAP, một entry không chỉ có tên và giá trị thuộc tính; nó còn khai báo một hoặc nhiều giá trị `objectClass` để cho biết entry thuộc những loại đối tượng nào. Các **object class** có thể **kế thừa** nhau: lớp con nhận lại những thuộc tính bắt buộc và được phép của lớp cha, rồi bổ sung quy tắc riêng. Điều này giúp nhiều loại entry dùng chung các định nghĩa tiêu chuẩn mà không phải lặp lại toàn bộ cấu trúc.

Ví dụ, một tài khoản nhân viên có thể thuộc lớp `inetOrgPerson`, kế thừa `organizationalPerson`, tiếp đến `person` và `top`. Vì `person` yêu cầu `cn` và `sn`, entry kiểu `inetOrgPerson` vẫn phải đáp ứng những yêu cầu này, dù phần định nghĩa riêng của `inetOrgPerson` không lặp lại chúng.

Hiểu quan hệ kế thừa giúp giải thích **vì sao server từ chối một entry thiếu thuộc tính**, **vì sao không thể ghép tùy ý hai structural object class** và **vì sao annotation `@Entry` trong Java phải nhất quán với schema LDAP đã triển khai**.

## 1. Phân biệt object class, attribute type và entry

Ba khái niệm liên quan nhưng đảm nhiệm các vai trò khác nhau:

| Khái niệm | Câu hỏi mà nó trả lời | Ví dụ |
|---|---|---|
| **Attribute type** | Thuộc tính tên gì, có cú pháp và quy tắc so khớp nào? | `cn`, `sn`, `uid`, `mail` |
| **Object class** | Entry thuộc loại nào, bắt buộc và được phép có thuộc tính gì? | `person`, `inetOrgPerson`, `groupOfNames` |
| **Entry** | Bản ghi cụ thể chứa các giá trị nào và nằm ở đâu trong DIT? | `uid=lan,ou=people,dc=example,dc=org` |

Một entry thường có thuộc tính **đa giá trị** `objectClass`:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Tran Thi Lan
sn: Tran
mail: lan@example.org
~~~

Các dòng `objectClass` ở đây là **giá trị dữ liệu của entry**. Chúng không phải câu lệnh tạo schema. Directory server phải có sẵn định nghĩa các class tương ứng, đồng thời có thể áp dụng các ràng buộc bổ sung từ chính sách hoặc schema được cài trên server.

Cần phân biệt:

- `objectClass` (số ít) là **attribute của entry**, dùng để khai báo các lớp áp dụng cho entry.
- `objectClasses` (số nhiều) là **attribute trong subschema entry** chứa các định nghĩa object class của directory.
- `objectClasses` trong `@Entry(objectClasses = {...})` là **tham số annotation Java** dùng cho ánh xạ, không có chức năng tự tạo object class trên server.

## 2. Quan hệ kế thừa được khai báo bằng SUP

Trong schema LDAP, mỗi object class có một tên/OID và có thể tham chiếu lớp cha bằng **`SUP`** (superior object class). Ví dụ rút gọn theo cách biểu diễn định nghĩa schema:

~~~text
( 2.5.6.6 NAME 'person'
  SUP top
  STRUCTURAL
  MUST ( sn $ cn )
  MAY ( userPassword $ telephoneNumber $ seeAlso $ description ) )
~~~

Định nghĩa trên có nghĩa:

- `2.5.6.6` là OID của lớp `person`.
- `NAME 'person'` cung cấp tên dễ đọc.
- `SUP top` nói `person` kế thừa từ `top`.
- `STRUCTURAL` xác định đây là lớp cấu trúc.
- `MUST ( sn $ cn )` yêu cầu entry có surname và common name.
- `MAY (...)` cho phép các thuộc tính được liệt kê, nhưng không bắt buộc phải có.

**Lớp con kế thừa toàn bộ các ràng buộc thuộc tính từ lớp cha.** Vì vậy, để biết entry thuộc lớp `inetOrgPerson` cần những gì, không chỉ đọc định nghĩa `inetOrgPerson`; phải đi theo các `SUP` và tổng hợp thuộc tính của toàn bộ chuỗi kế thừa.

Sơ đồ lớp thông dụng theo RFC:

~~~mermaid
flowchart TD
    TOP["top<br/>ABSTRACT"]
    PERSON["person<br/>STRUCTURAL<br/>MUST: cn, sn"]
    ORG["organizationalPerson<br/>STRUCTURAL<br/>bổ sung thuộc tính tổ chức"]
    INET["inetOrgPerson<br/>STRUCTURAL<br/>bổ sung uid, mail..."]
    TOP --> PERSON
    PERSON --> ORG
    ORG --> INET
~~~

Một LDAP server có thể hỗ trợ thêm class của nhà cung cấp hoặc của tổ chức; đó là lý do phải kiểm tra **schema đang chạy trên server thực tế**, thay vì giả định mọi directory có cùng một hệ thống class.

## 3. Ba nhóm object class và quy tắc kế thừa

LDAP phân object class thành **ABSTRACT**, **STRUCTURAL** và **AUXILIARY**.

| Nhóm | Vai trò | Kế thừa hợp lệ theo mô hình schema | Ví dụ |
|---|---|---|---|
| **ABSTRACT** | Định nghĩa nền tảng để lớp khác phát triển | Từ abstract class | `top` |
| **STRUCTURAL** | Xác định loại cấu trúc chính của entry | Từ structural hoặc abstract phù hợp | `person`, `inetOrgPerson`, `groupOfNames` |
| **AUXILIARY** | Bổ sung các thuộc tính/khả năng cho entry có lớp cấu trúc | Từ auxiliary hoặc abstract phù hợp | `simpleSecurityObject` ở những server hỗ trợ schema tương ứng |

**ABSTRACT:** `top` là lớp nền cho nhiều object class. Không thể chỉ khai báo một entry nghiệp vụ với mỗi `top` rồi kỳ vọng nó trở thành một người dùng hoặc nhóm hợp lệ. Entry thông thường cần lớp cấu trúc thích hợp.

**STRUCTURAL:** entry phải có một **chuỗi kế thừa structural object class** nhất quán. Ví dụ `person → organizationalPerson → inetOrgPerson` tạo thành một chuỗi. Không thể tùy tiện gộp `inetOrgPerson` và `groupOfNames` thành hai nhánh structural độc lập của cùng một entry.

**AUXILIARY:** lớp phụ trợ bổ sung những thuộc tính/đặc tính được schema cho phép; nó không thay thế nhu cầu về lớp structural. Directory server có thể áp dụng thêm **DIT content rule** hoặc chính sách riêng để quyết định lớp auxiliary nào được dùng cho một entry structural cụ thể.

> **Ghi nhớ:** Kế thừa không có nghĩa “cứ thêm mọi lớp vào `objectClass` là entry sẽ hợp lệ”. Server kiểm tra cả loại lớp, quan hệ `SUP`, tập thuộc tính, syntax và các ràng buộc cây/thư mục khác.

## 4. Ví dụ xuyên suốt: top → person → organizationalPerson → inetOrgPerson

Chuỗi chuẩn để biểu diễn người dùng:

~~~text
top
  └── person
        └── organizationalPerson
              └── inetOrgPerson
~~~

### Lớp top

`top` là abstract object class cơ sở. Định nghĩa tiêu chuẩn của nó có yêu cầu đối với thuộc tính `objectClass`, vốn dùng để xác định các class của entry.

### Lớp person

`person` là structural class kế thừa `top` và yêu cầu:

- `cn`: common name, tên phổ biến/hiển thị.
- `sn`: surname, họ/tên họ theo mục đích schema.

`person` cũng cho phép các thuộc tính như `telephoneNumber`, `description` và `userPassword` trong mô hình tiêu chuẩn. Việc được **cho phép** không có nghĩa ứng dụng cần lưu tất cả các thuộc tính đó.

### Lớp organizationalPerson

`organizationalPerson` kế thừa `person`, bổ sung các thuộc tính phù hợp với bối cảnh tổ chức, ví dụ `title`, `ou` và một số thông tin liên quan. Vì là lớp con, entry vẫn phải có `cn` và `sn`.

### Lớp inetOrgPerson

`inetOrgPerson` kế thừa `organizationalPerson`, mở rộng mô hình người dùng trong môi trường ứng dụng mạng. Các thuộc tính như `uid`, `mail` hoặc `employeeNumber` thường được phép bởi định nghĩa `inetOrgPerson`.

| Lớp trong chuỗi | Kiểu lớp | Quan hệ `SUP` | Ràng buộc tiêu biểu được áp dụng |
|---|---|---|---|
| `top` | ABSTRACT | Không có trong chuỗi này | Có `objectClass` |
| `person` | STRUCTURAL | `top` | `cn`, `sn` là MUST |
| `organizationalPerson` | STRUCTURAL | `person` | Giữ `cn`/`sn`; thêm thuộc tính tổ chức |
| `inetOrgPerson` | STRUCTURAL | `organizationalPerson` | Giữ mọi MUST từ cha; thêm thuộc tính như `uid`/`mail` |

Khi mô hình Java sử dụng `inetOrgPerson`, người học cần đọc **đầy đủ chuỗi này** để biết các thuộc tính bắt buộc. Không đủ nếu chỉ nhìn vào những `@Attribute` hiện có trong Java entity.

## 5. MUST/MAY được kế thừa như thế nào?

Có thể hiểu các ràng buộc thuộc tính bằng phép hợp tập hợp:

~~~text
MUST hiệu lực của lớp C
  = MUST khai báo tại C
  + MUST kế thừa từ các lớp cha của C

MAY hiệu lực của lớp C
  = MAY khai báo tại C
  + MAY kế thừa từ các lớp cha của C
~~~

Việc dùng dấu `+` ở đây biểu diễn hợp tập hợp, **không phải** phép cộng số học. Những class khác cùng áp dụng cho entry, đặc biệt auxiliary class, cũng có thể bổ sung thuộc tính bắt buộc/được phép theo quy tắc schema.

Ví dụ `inetOrgPerson`:

| Thuộc tính | Nguồn hoặc lý do hợp lệ | Bắt buộc? |
|---|---|---|
| `objectClass` | Từ lớp cơ sở `top` | Có theo mô hình object class |
| `cn` | `person` | Có |
| `sn` | `person` | Có |
| `title` | Thuộc tính tổ chức trong chuỗi lớp cha | Không |
| `uid` | Được `inetOrgPerson` cho phép | Không theo MUST của `inetOrgPerson`, nhưng cần nếu dùng `uid` làm RDN |
| `mail` | Được `inetOrgPerson` cho phép | Không |
| `employeeNumber` | Được `inetOrgPerson` cho phép | Không |

**Phân biệt “được phép” với “hợp lệ”:** một giá trị `mail` có thể được class cho phép nhưng vẫn phải phù hợp với attribute syntax, matching rule và các chính sách khác. Một `uid` được phép dùng nhưng không mặc nhiên duy nhất trên toàn thư mục; DN cần được xác định và quản lý riêng.

Một thuộc tính khai báo `MAY` bởi lớp cha **không mất đi quyền sử dụng** khi entry được ánh xạ thành lớp con. Tương tự, một thuộc tính `MUST` từ lớp cha **không trở thành tùy chọn** chỉ vì lớp con không nhắc lại nó.

### Ví dụ entry hợp lệ

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Tran Thi Lan
sn: Tran
title: Software Engineer
mail: lan@example.org
~~~

Entry này biểu diễn một người dùng với lớp cấu trúc cụ thể nhất là `inetOrgPerson`. Trong cấu trúc cây ví dụ, `uid` vừa là attribute được class cho phép, vừa là thuộc tính dùng trong Relative Distinguished Name (RDN) `uid=lan`.

### Ví dụ thiếu MUST

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Tran Thi Lan
mail: lan@example.org
~~~

Entry này thiếu `sn`. Dù `inetOrgPerson` không lặp lại `MUST sn` trong chính định nghĩa của nó, server thực thi schema vẫn kiểm tra yêu cầu được kế thừa từ `person` và có thể từ chối Add với `objectClassViolation (65)`.

### Ví dụ thuộc tính không được cho phép

Nếu một entry chỉ khai báo `person` và `top` nhưng chứa `mail`, schema tiêu chuẩn của `person` không tự cho phép thuộc tính `mail`. Server có thể từ chối vì thuộc tính này nằm ngoài các lớp áp dụng. Giải pháp là chọn lớp phù hợp với mục đích dữ liệu, không phải thêm thuộc tính vào Java rồi kỳ vọng server tự nới schema.

## 6. Vì sao một entry không thể có hai structural class độc lập?

Mỗi entry LDAP thông thường phải phù hợp với một **chuỗi kế thừa structural**. Nếu một entry dùng:

~~~text
top
├── person
│   └── organizationalPerson
│       └── inetOrgPerson
└── groupOfNames
~~~

thì `inetOrgPerson` và `groupOfNames` thuộc hai nhánh structural không nằm trên cùng một chuỗi kế thừa. Ghép chúng vào cùng entry chỉ để nhận thuộc tính `member` không phải cách định nghĩa dữ liệu hợp lệ.

Ví dụ **không hợp lệ về cấu trúc**:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
objectClass: groupOfNames
uid: lan
cn: Tran Thi Lan
sn: Tran
member: uid=binh,ou=people,dc=example,dc=org
~~~

`groupOfNames` cũng là structural class (kế thừa `top`), chứ không phải một “bộ thuộc tính thêm cho người dùng”. Server sẽ kiểm tra tính nhất quán của structural chain và có thể từ chối thay đổi với lỗi liên quan đến object class.

### Mô hình đúng: người và nhóm là hai entry khác nhau

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Tran Thi Lan
sn: Tran

dn: cn=developers,ou=groups,dc=example,dc=org
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=lan,ou=people,dc=example,dc=org
~~~

Nhóm chứa **tham chiếu tới DN** của thành viên qua `member`. Điều đó khác với việc trộn hai structural class trên cùng entry.

Lưu ý: cú pháp DN của `member` chưa tự bảo đảm entry thành viên luôn tồn tại. Tính toàn vẹn tham chiếu và cập nhật `member` khi user đổi DN phụ thuộc chức năng server hoặc quy trình nghiệp vụ.

## 7. Auxiliary object class: mở rộng theo cách hợp lệ

Khi entry đã có structural class như `inetOrgPerson` nhưng cần thêm một nhóm thuộc tính từ schema khác, LDAP cung cấp **AUXILIARY object class**. Lớp auxiliary có thể được khai báo cùng lớp structural hợp lệ, nếu server cho phép theo schema và DIT content rule.

Ví dụ khái niệm:

~~~text
top (ABSTRACT)
└── person (STRUCTURAL)
    └── organizationalPerson (STRUCTURAL)
        └── inetOrgPerson (STRUCTURAL)

appBadgeAttributes (AUXILIARY, do tổ chức định nghĩa)
    └── có thể bổ sung appBadgeId nếu schema cho phép
~~~

Tên `appBadgeAttributes` và `appBadgeId` chỉ là **minh họa**; chúng không phải class/attribute tiêu chuẩn đã được cài sẵn. Để dùng thật, quản trị viên directory phải đăng ký OID phù hợp, định nghĩa attribute type và auxiliary class, triển khai schema đúng cách, rồi xác nhận server cho phép lớp phụ trợ đó trên entry cần dùng.

Khi một auxiliary class có thêm `MUST`, các thuộc tính bắt buộc của nó cũng trở thành yêu cầu đối với entry áp dụng class đó. AUXILIARY không đồng nghĩa với “mọi thuộc tính của nó đều là MAY”.

**Không dùng việc thêm `extensibleObject` như một lối tắt mặc định** để bỏ qua thiết kế schema. Một số directory hỗ trợ class phụ trợ này, nhưng việc mở rộng quá rộng có thể làm mất tính nhất quán và tính tương tác. Trước tiên hãy tìm object class tiêu chuẩn phù hợp; chỉ định nghĩa extension khi có nhu cầu dữ liệu rõ ràng.

## 8. Kế thừa object class không phải kế thừa class Java

Người học Java có thể thấy sơ đồ `person → inetOrgPerson` giống `class Child extends Parent`. Hai cơ chế có điểm tương đồng về ý tưởng tái sử dụng, nhưng không phải một thứ:

| LDAP object class inheritance | Java class inheritance |
|---|---|
| Được định nghĩa và kiểm tra bởi directory schema | Được trình biên dịch/JVM và các thư viện sử dụng |
| Quy định thuộc tính MUST/MAY, kiểu structural/auxiliary | Quy định field, method, interface và hành vi Java |
| Entry có `objectClass` đa giá trị | Object Java có một kiểu runtime và hệ thống phân cấp Java |
| Có thể mở rộng entry bằng auxiliary class phù hợp | Có thể dùng interface/composition và kế thừa Java |
| Thay đổi schema phải triển khai trên directory server | Thay đổi class Java cần build/deploy ứng dụng |

**Điểm mấu chốt:** tạo `class Employee extends Person` trong Java **không** tạo ra một object class LDAP tên `Employee`. Đổi `@Entry(objectClasses = ...)` cũng **không** làm LDAP server tự tạo class mới. Cần giữ hai mô hình nhất quán một cách chủ động.

Khi ánh xạ lớp Java cho một entry, ứng dụng cần xem entity là một biểu diễn của **LDAP entry hiện có**, với schema được directory quản lý.

## 9. Ánh xạ chuỗi kế thừa trong Spring Data LDAP

Ví dụ entity người dùng:

~~~java
import javax.naming.Name;

import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {
        "top",
        "person",
        "organizationalPerson",
        "inetOrgPerson"
    }
)
public class DirectoryPerson {

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

    public DirectoryPerson() {
    }

    // Bổ sung getter/setter tương ứng với nhu cầu mapping.
}
~~~

Ở đây:

- `@Entry(base = "ou=people")` đặt nhánh ánh xạ entity theo base của `ContextSource`.
- `@Entry(objectClasses = {...})` ghi rõ bộ class mà entity dự kiến sử dụng; gồm structural chain `top → person → organizationalPerson → inetOrgPerson`.
- `@Id` ánh xạ DN của entry; DN xác định vị trí trong cây thư mục.
- `@Attribute(name = "cn")` và `@Attribute(name = "sn")` tương ứng hai thuộc tính bắt buộc kế thừa từ `person`.
- `@Attribute(name = "uid")` và `@Attribute(name = "mail")` ánh xạ các thuộc tính được `inetOrgPerson` cho phép.

Ví dụ chỉ tập trung vào ánh xạ object class; khi triển khai, cần hoàn thiện accessor, xây dựng DN đúng quy tắc và xử lý các tình huống dữ liệu vắng mặt phù hợp với thư viện/phiên bản đang dùng.

### Repository làm việc với entry có class tương ứng

~~~java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {

    List<DirectoryPerson> findByUid(String uid);

    List<DirectoryPerson> findBySurname(String surname);
}
~~~

Tên `findBySurname` là tên field Java `surname`, còn `@Attribute(name = "sn")` xác định tên attribute LDAP tương ứng. Repository dùng metadata ODM và context cấu hình để xây dựng thao tác LDAP.

Nếu một entry đang chỉ có `person` nhưng ứng dụng khai báo mapping `inetOrgPerson`, cần kiểm tra cách repository lọc object class và cách dữ liệu được đọc/ghi. Không được giả định mọi entry có `cn` và `sn` đều là `inetOrgPerson`.

### Tìm kiếm bằng objectClass với LdapTemplate

~~~java
import java.util.List;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.query.LdapQuery;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public class DirectoryPersonSearch {

    private final LdapTemplate ldapTemplate;

    public DirectoryPersonSearch(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findNamesByUid(String uid) {
        LdapQuery ldapQuery = query()
                .base("ou=people")
                .attributes("cn")
                .where("objectClass").is("inetOrgPerson")
                .and("uid").is(uid);

        return ldapTemplate.search(
                ldapQuery,
                (AttributesMapper<String>) attrs ->
                        (String) attrs.get("cn").get()
        );
    }
}
~~~

Điều kiện `objectClass=inetOrgPerson` giới hạn kết quả về những entry được đánh dấu với class này. Vì `inetOrgPerson` kế thừa `person`, nó thỏa các ràng buộc của `person`. Tuy nhiên, một entry `person` thuần túy **không tự trở thành** `inetOrgPerson` và có thể bị loại bởi filter.

Dùng `LdapQueryBuilder` hoặc API filter của Spring LDAP khi đưa giá trị người dùng vào truy vấn; tránh tự nối chuỗi filter vì có thể tạo lỗi cú pháp hoặc LDAP injection. Cũng phải chọn search base và scope phù hợp với ranh giới dữ liệu, kiểm tra ACL của tài khoản bind.

## 10. Mối liên hệ giữa objectClass, DN và DIT

Các yếu tố thường được học cùng nhau nhưng có mục đích khác nhau:

| Yếu tố | Quy định |
|---|---|
| **Object class** | Những thuộc tính nào là MUST/MAY, kiểu structural/auxiliary |
| **Attribute type** | Cú pháp, tính đa giá trị và quy tắc so khớp của từng thuộc tính |
| **DN/RDN** | Entry được đặt tên thế nào và nằm dưới parent nào |
| **DIT/Name form** | Quy tắc cấu trúc cây và tên entry, nếu directory áp dụng |
| **ACL** | Người dùng hoặc service account được đọc/sửa những gì |

Ví dụ, `inetOrgPerson` cho phép `uid`, nhưng schema không mặc nhiên bắt mọi `inetOrgPerson` phải dùng `uid` làm RDN. Một hệ thống có thể dùng `cn=Tran Thi Lan,ou=people,...` hoặc `uid=lan,ou=people,...` nếu các quy tắc đặt tên cho phép và entry đáp ứng ràng buộc tương ứng.

Tương tự, một entry có đúng chuỗi object class vẫn có thể không được đặt dưới một nhánh bất kỳ nếu directory server áp dụng quy tắc DIT content/structure hoặc chính sách riêng. Việc class cho phép `mail` không có nghĩa tài khoản bind có quyền sửa `mail`.

## 11. Vì sao không nên đổi structural object class tùy tiện?

Giả sử hệ thống ban đầu có một entry `person`, sau đó muốn thay thành `inetOrgPerson`. Do `inetOrgPerson` là một **structural class cụ thể hơn**, đây không đơn giản là thêm một attribute `mail`.

Theo mô hình LDAP chuẩn, entry có **structural object class** được xác định khi tạo và không phải thuộc tính có thể thay đổi tùy ý bằng Modify. Directory server có thể từ chối việc thay structural chain sau khi entry đã tồn tại, kể cả khi lớp mới kế thừa lớp cũ. Trong những server hỗ trợ thuộc tính vận hành `structuralObjectClass`, server quản lý giá trị đó; ứng dụng không tự viết như một trường bình thường.

Nếu cần chuyển mô hình người dùng:

1. Xác định class hiện tại, class đích và toàn bộ MUST/MAY của hai chuỗi.
2. Kiểm tra liệu server cho phép thay đổi dạng đó hay không; không giả định có thể dùng `modifyAttributes` để đổi structural class.
3. Nếu không hỗ trợ, thiết kế **migration** có kiểm soát theo quy trình directory, bao gồm DN, thuộc tính, group membership, tham chiếu và quyền.
4. Sao lưu/dự phòng và thử nghiệm trên directory độc lập trước khi áp dụng dữ liệu thật.
5. Xác minh entry kết quả và các tham chiếu từ ứng dụng khác.

Việc thêm hoặc gỡ **auxiliary object class** có thể có quy tắc riêng và cũng phải được server cho phép. Không đồng nhất thao tác này với thay structural class.

**Tương tự đối với Java:** việc cập nhật `@Entry(objectClasses = {...})` rồi gọi `repository.save(...)` không thay thế kế hoạch migration schema/dữ liệu và có thể dẫn đến lỗi ghi.

## 12. Đọc schema thực tế trên directory server

Các tên object class phổ biến không đảm bảo định nghĩa giống nhau ở mọi triển khai. Để biết một lớp kế thừa từ đâu, hãy truy vấn **subschema entry** mà server công bố.

Quy trình cơ bản:

1. Kết nối bằng tài khoản có quyền đọc thông tin schema, ưu tiên LDAPS/StartTLS với chứng chỉ hợp lệ.
2. Đọc `subschemaSubentry` của một entry trong phạm vi cần tìm hiểu; giá trị này chỉ tới DN của subschema entry.
3. Đọc các thuộc tính `objectClasses` và `attributeTypes` trong subschema entry đó.
4. Tìm tên class đang dùng, lần theo `SUP` đến các lớp cha.
5. Tổng hợp MUST/MAY của toàn bộ chuỗi, đối chiếu syntax của attribute type và những quy tắc bổ sung nếu có.

Ví dụ lệnh `ldapsearch` để xem định nghĩa class của entry đã biết (đường dẫn và tài khoản chỉ là minh họa):

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -D "uid=svc-reader,ou=services,dc=example,dc=org" -W \
  -b "uid=lan,ou=people,dc=example,dc=org" \
  -s base "(objectClass=*)" objectClass subschemaSubentry
~~~

Sau khi có DN `subschemaSubentry` từ kết quả, có thể truy vấn base-scope tại DN này:

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -D "uid=svc-reader,ou=services,dc=example,dc=org" -W \
  -b "cn=schema" -s base \
  "(objectClass=*)" objectClasses attributeTypes
~~~

`cn=schema` trong lệnh thứ hai **chỉ là DN ví dụ**: phải thay bằng giá trị `subschemaSubentry` thực sự lấy được, không được mặc định mọi server cùng dùng DN này. Tùy quyền, server có thể không công bố một số định nghĩa hoặc dùng cách quản trị schema riêng. Trên Active Directory, mô hình class và attribute có thể khác OpenLDAP; không nên suy cấu trúc `inetOrgPerson` là mô hình đăng nhập mặc định của mọi server.

### Quan sát class của entry

Một số directory công bố `structuralObjectClass` dưới dạng thuộc tính vận hành. Có thể thử yêu cầu rõ thuộc tính này khi đọc entry:

~~~bash
ldapsearch -LLL -x \
  -H ldaps://ldap.example.org:636 \
  -D "uid=svc-reader,ou=services,dc=example,dc=org" -W \
  -b "uid=lan,ou=people,dc=example,dc=org" \
  -s base "(objectClass=*)" objectClass structuralObjectClass
~~~

Nếu thuộc tính không xuất hiện, chưa chắc class không tồn tại: có thể do cách server triển khai hoặc quyền đọc operational attributes.

## 13. Lỗi thường gặp khi dùng object class kế thừa

| Mã kết quả LDAP | Tình huống liên quan | Hướng kiểm tra |
|---|---|---|
| `objectClassViolation (65)` | Thiếu MUST được kế thừa, attribute không được phép, tổ hợp class sai | Đọc class hiện tại, `SUP`, MUST/MAY và nhóm structural |
| `undefinedAttributeType (17)` | Attribute không được schema định nghĩa | Kiểm tra chính tả và `attributeTypes` |
| `invalidAttributeSyntax (21)` | Giá trị không phù hợp syntax attribute type | Xem cú pháp của `uid`, DN, số, thời gian... |
| `namingViolation (64)` | Tên hoặc vị trí entry không hợp lệ với quy tắc đặt tên | Kiểm tra RDN, parent, name form/DIT rules |
| `objectClassModsProhibited (69)` | Server cấm sửa object class theo cách yêu cầu | Kiểm tra đổi structural chain và chính sách server |
| `insufficientAccessRights (50)` | Người gọi không có quyền đọc/ghi thuộc tính | Kiểm tra ACL, dù schema có thể cho phép thuộc tính |

Một lỗi không nhất thiết luôn có một mã duy nhất trên mọi server. Hãy đọc cả diagnostic message phía LDAP server khi có thể, nhưng không ghi password hoặc toàn bộ entry nhạy cảm vào log.

### Tình huống A: Thiếu thuộc tính bắt buộc ở lớp cha

Ứng dụng tạo `inetOrgPerson` chỉ với `uid` và `mail`. Vì `person` yêu cầu `cn` và `sn`, server có thể trả `objectClassViolation`. Hướng sửa là **bổ sung dữ liệu bắt buộc**, không xóa `person` khỏi danh sách class để lách ràng buộc.

### Tình huống B: Gắn structural class không cùng nhánh

Ứng dụng thêm `groupOfNames` vào entry `inetOrgPerson` chỉ vì muốn dùng thuộc tính `member`. Điều này sai mô hình structural class. Hướng sửa là tạo group entry riêng hoặc dùng auxiliary class hợp lệ theo schema nếu mục đích thực sự là mở rộng thuộc tính người dùng.

### Tình huống C: Java entity có field nhưng server chưa biết attribute

Ứng dụng thêm `@Attribute(name = "employeeBadge")` nhưng server không có attribute type `employeeBadge`. Việc thêm field Java không bổ sung schema; phải dùng thuộc tính chuẩn phù hợp hoặc triển khai schema extension có kiểm soát.

### Tình huống D: Update một structural class đã tồn tại

Một script sửa `objectClass: person` thành `objectClass: inetOrgPerson` trên entry cũ. Tùy server, thao tác có thể bị từ chối vì ràng buộc class cấu trúc. Không tự thử bằng dữ liệu production; phải khảo sát cơ chế migration được directory hỗ trợ.

## 14. Kế thừa object class và bảo mật truy vấn

Quan hệ class thường được sử dụng trong LDAP filter:

~~~text
(&(objectClass=inetOrgPerson)(uid=lan))
~~~

Filter này hỏi server tìm entry có class `inetOrgPerson` và `uid=lan` trong search base/scope đã chọn. Vì `objectClass` là thuộc tính của entry, filter không tự mở rộng base DN hay vượt qua ACL. Một directory có nhiều người cùng `uid=lan` ở các OU khác nhau vẫn có thể trả về nhiều kết quả.

Các thực hành cần thiết khi kết hợp schema với Spring Data LDAP:

- Chọn **search base** hẹp theo chức năng, ví dụ `ou=people` hoặc OU đã phân quyền cho tenant.
- Dùng `LdapQueryBuilder` để escape giá trị filter, tránh ghép trực tiếp đầu vào người dùng thành biểu thức LDAP.
- Kiểm tra schema để biết object class nào thực sự đại diện cho dữ liệu cần tìm.
- Dùng **LDAPS hoặc StartTLS** với xác minh chứng chỉ, đặc biệt khi bind bằng tài khoản có quyền đọc thông tin cá nhân.
- Giới hạn quyền của service account; schema cho phép một thuộc tính **không** có nghĩa mọi tài khoản được đọc hoặc sửa nó.
- Không nhầm object class với nhóm phân quyền. `groupOfNames` là loại entry nhóm; thành viên và quyền ứng dụng cần được xác định qua membership, ACL hoặc cơ chế phân quyền riêng.

Ví dụ, `objectClass=inetOrgPerson` chỉ xác nhận entry thuộc loại người dùng theo schema. Nó **không** khẳng định tài khoản có quyền quản trị, còn hoạt động hay đã xác thực được mật khẩu.

## 15. Kiểm thử tích hợp quan hệ kế thừa

Một unit test mock `LdapRepository` không thể chứng minh directory server thực thi đúng schema. Hãy tạo directory **kiểm thử độc lập** có schema tương đương môi trường mục tiêu và thực hiện Add/Search/Modify thật.

Các trường hợp nên kiểm tra:

| Kịch bản | Entry/thao tác | Kết quả mong đợi |
|---|---|---|
| Hợp lệ theo chuỗi `inetOrgPerson` | Có `cn`, `sn` và các thuộc tính đặt tên phù hợp | Add thành công nếu DN, ACL và các ràng buộc khác hợp lệ |
| Thiếu MUST kế thừa | Bỏ `sn` nhưng giữ `inetOrgPerson` | Server từ chối theo schema |
| Chỉ dùng lớp `person` | Có `cn` và `sn`, không thêm `mail` | Hợp lệ nếu DN/ACL cho phép |
| Thuộc tính ngoài class | Dùng `mail` trong entry chỉ có `person` | Server từ chối nếu không có class/rule nào khác cho phép |
| Hai structural class độc lập | Ghép `inetOrgPerson` với `groupOfNames` | Server từ chối |
| Filter class con | Tìm `(objectClass=inetOrgPerson)` | Trả entry đúng loại, không tự bao gồm mọi entry `person` |
| Auxiliary hợp lệ | Thêm class phụ trợ được cài và được phép | Thành công nếu đáp ứng MUST/DIT rule |
| Attribute chưa định nghĩa | Ghi `employeeBadge` khi schema chưa có | Server từ chối với lỗi schema |
| Sửa structural class | Modify chuỗi structural của entry đã có | Xác nhận hành vi cấm/giới hạn của directory server đang dùng |

Một quy trình kiểm thử mẫu:

1. Khởi tạo LDAP test và nạp class tiêu chuẩn cần dùng, tạo parent DN `dc=example,dc=org` và `ou=people`.
2. Tạo entry `inetOrgPerson` hợp lệ; gọi repository hoặc `LdapTemplate` tìm lại để xác nhận mapping.
3. Thử tạo entry thiếu `sn` và xác nhận thao tác bị từ chối.
4. Thử một entry `person` đơn giản và kiểm tra filter `objectClass=inetOrgPerson` không trả nó.
5. Thử ghép thêm `groupOfNames` vào cùng entry và xác minh lỗi phù hợp.
6. Ghi nhận lỗi từ server để đối chiếu với `objectClassViolation` hoặc mã khác được triển khai trả về.
7. Dọn dữ liệu thử nghiệm; không chạy các thử nghiệm cố tình vi phạm schema bằng tài khoản trên directory production.

Đặc biệt, hãy kiểm tra directory test có **schema checking được bật**. Nếu test server cho phép entry sai cấu trúc do cấu hình quá lỏng, bài test sẽ không đại diện cho production.

## 16. Những nhầm lẫn cần tránh

- **“Lớp con có thể bỏ thuộc tính MUST của lớp cha.”** Không. Các yêu cầu kế thừa vẫn có hiệu lực.
- **“Chỉ khai báo `inetOrgPerson` trong Java là đủ để tạo schema.”** Không. Server phải có định nghĩa class và các attribute type liên quan.
- **“`MAY` nghĩa là attribute luôn hợp lệ trong mọi giá trị.”** Không. Attribute type vẫn quyết định syntax và đặc tính giá trị.
- **“Thêm hai structural class sẽ nhận được tất cả trường của hai loại.”** Không. Chúng phải thuộc một chuỗi structural nhất quán.
- **“Auxiliary class không thể có thuộc tính MUST.”** Không. Auxiliary vẫn có thể yêu cầu thuộc tính.
- **“Mỗi field Java tương ứng một attribute hợp lệ.”** Không. Field Java chỉ là ánh xạ; directory server kiểm tra schema.
- **“`objectClass=person` là toàn bộ danh tính của entry người dùng.”** Không. Có thể có subclass, thuộc tính bổ sung và nhiều class áp dụng.
- **“Đổi structural class chỉ là một thao tác cập nhật thông thường.”** Không. Structural class thường được cố định khi entry được tạo, cần khảo sát migration.
- **“Có `objectClass=inetOrgPerson` tức là đăng nhập được và có quyền ứng dụng.”** Không. Credential, trạng thái tài khoản và quyền được xử lý bởi các cơ chế khác.

## 17. Bài tập thực hành

**Bối cảnh:** hệ thống nhân sự dùng Spring Data LDAP lưu tài khoản dưới `ou=people,dc=example,dc=org`. Trước đây nhóm chỉ biết `person`; nay muốn lưu `uid`, `mail` và tìm kiếm thông qua `LdapRepository`.

Thực hiện:

1. Vẽ lại chuỗi kế thừa `top → person → organizationalPerson → inetOrgPerson` và đánh dấu mỗi lớp ABSTRACT/STRUCTURAL.
2. Tra schema server để tìm `SUP`, `MUST` và `MAY` của `person` và `inetOrgPerson`.
3. Tạo LDIF cho nhân viên `uid=lan` với `cn`, `sn`, `uid` và `mail`.
4. Bỏ `sn`, thử Add vào directory test và giải thích vì sao lỗi.
5. Tạo entity `DirectoryPerson` với `@Entry`, `@Id` và `@Attribute` đúng schema.
6. Tạo `DirectoryPersonRepository.findByUid("lan")` và kiểm tra kết quả.
7. Tạo entry chỉ thuộc lớp `person`; chạy filter `(objectClass=inetOrgPerson)` rồi giải thích vì sao nó không thuộc kết quả.
8. Tạo `groupOfNames` riêng và tham chiếu DN của Lan qua `member`; chứng minh vì sao không thêm `groupOfNames` vào entry của Lan.
9. Viết ngắn kế hoạch nếu tương lai cần một attribute riêng `appBadgeId`: phải định nghĩa gì trong schema, dùng class phụ trợ hay thuộc tính đã có, cần kiểm thử gì trước khi triển khai?

**Tiêu chí hoàn thành:** người học giải thích được quan hệ `SUP`, tính hợp lệ của structural chain, sự kế thừa MUST/MAY và hệ quả của các quyết định schema với thao tác Java repository.

## 18. Ghi nhớ và tài liệu tham khảo

**Object class inheritance xác định cách một loại entry kế thừa ràng buộc từ loại cha.** Với `inetOrgPerson`, chuỗi `top → person → organizationalPerson → inetOrgPerson` giải thích vì sao `cn` và `sn` vẫn bắt buộc. Một entry không thể ghép tùy ý các structural class không cùng chuỗi; auxiliary class là cơ chế mở rộng khác và cũng phải tuân theo schema server.

Trong Spring Data LDAP, `@Entry`/`@Attribute` mô tả mapping ở ứng dụng; `LdapRepository` và `LdapTemplate` thực hiện truy vấn, CRUD; còn directory server chịu trách nhiệm kiểm tra schema và quyền truy cập. Khi có lỗi, hãy kiểm tra **objectClass → SUP → MUST/MAY → attribute syntax → DN/DIT → ACL** trước khi điều chỉnh entity hoặc bộ lọc.

Tài liệu nền tảng:

- [RFC 4512 — LDAP: Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512): định nghĩa object class, ba loại ABSTRACT/STRUCTURAL/AUXILIARY, quan hệ `SUP` và quy tắc schema.
- [RFC 4519 — LDAP: Schema for User Applications](https://www.rfc-editor.org/rfc/rfc4519): `top`, `person`, `organizationalPerson`, `groupOfNames` và các attribute type tiêu chuẩn.
- [RFC 2798 — Definition of the inetOrgPerson LDAP Object Class](https://www.rfc-editor.org/rfc/rfc2798): lớp `inetOrgPerson` và các thuộc tính mở rộng.
- [RFC 4517 — LDAP: Syntaxes and Matching Rules](https://www.rfc-editor.org/rfc/rfc4517): syntax và matching rule của attribute type.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): mapping entity và repository.
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/): `LdapTemplate`, `LdapQueryBuilder` và thao tác directory.
