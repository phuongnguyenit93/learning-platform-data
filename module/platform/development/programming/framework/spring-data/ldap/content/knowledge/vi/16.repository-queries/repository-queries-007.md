# Khai báo bộ lọc bằng @Query

Trong **Spring Data LDAP**, một **LdapRepository** thường tìm các entry LDAP bằng phương thức suy diễn từ tên như **findByUid(...)** hoặc **findByCommonName(...)**. Cơ chế này thuận tiện cho điều kiện đơn giản, nhưng có trường hợp ứng dụng cần một bộ lọc LDAP rõ ràng: tìm theo **uid hoặc mail**, chỉ lấy người có một attribute hiện diện, loại trừ entry bị đánh dấu một trạng thái nhất định, hoặc giới hạn truy vấn vào một nhánh **DN** cụ thể. Khi đó, annotation **org.springframework.data.ldap.repository.Query** cho phép khai báo **LDAP search filter** trực tiếp trên phương thức repository.

Bài học thuộc chương **Truy vấn Repository** của module **SPRING_DATA_LDAP**: truy cập dịch vụ thư mục LDAP bằng repository và ánh xạ các entry phân cấp sang Java object. Nội dung bao gồm cú pháp filter LDAP, **@Query** và tham số **:name / ?0**, tìm kiếm **AND/OR/NOT**, **presence/substring**, các tùy chọn **base/searchScope/countLimit/timeLimit**, escape input để tránh **LDAP filter injection**, những giới hạn so với **Spring Data JPA**, thao tác tương đương bằng **LdapTemplate**, xác minh với **ldapsearch** và kiểm thử tích hợp trên directory.

> **Điểm phải nhớ:** **@Query của Spring Data LDAP không chứa SQL, JPQL hoặc câu lệnh MongoDB JSON.** Giá trị của annotation là một **LDAP search filter** theo cú pháp LDAP, ví dụ **(&(objectClass=inetOrgPerson)(uid=:uid))**. Bộ lọc này không thay thế **DN**, quyền **ACL**, schema hoặc các bước xác thực kết nối.

## 1. @Query giải quyết vấn đề gì?

Giả sử người dùng được biểu diễn bằng LDAP entry:

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@lab.example
description: Engineer
~~~

Ứng dụng muốn lấy entry có **uid=linh**. Với repository method suy diễn:

~~~java
Optional<DirectoryPerson> findByUid(String uid);
~~~

Spring Data LDAP có thể tạo truy vấn theo property **uid** được ánh xạ. Nhưng nếu người gọi nhập một identifier có thể là uid **hoặc** email, filter cần điều kiện OR:

~~~text
(&(objectClass=inetOrgPerson)(|(uid=linh)(mail=linh)))
~~~

Đọc từ trong ra ngoài:

| Thành phần | Ý nghĩa |
| --- | --- |
| **(objectClass=inetOrgPerson)** | Entry phải là loại inetOrgPerson theo matching của directory |
| **(uid=linh)** | Attribute uid khớp giá trị linh |
| **(mail=linh)** | Attribute mail khớp giá trị linh |
| **(| A B)** | OR: A hoặc B đúng |
| **(& A B)** | AND: tất cả điều kiện đúng |

Với **@Query**, phương thức repository có thể khai báo filter một cách minh bạch, có tên và có tham số. Điều đó giúp code review kiểm tra chính xác **đang search attribute nào**, thay vì suy đoán toàn bộ filter từ một tên phương thức dài.

~~~mermaid
flowchart TD
    A["Service gọi repository method"] --> B["@Query: filter template + method args"]
    B --> C["Spring Data LDAP bind tham số"]
    C --> D["LdapTemplate / ContextSource"]
    D --> E["LDAP SearchRequest: base + scope + filter + limits"]
    E --> F["LDAP server: schema/index/ACL"]
    F --> G["SearchResultEntry"]
    G --> H["Spring LDAP ODM ánh xạ thành DirectoryPerson"]
~~~

Khác với **LdapTemplate**, repository tự trả entity đã được ODM ánh xạ; nhưng **@Query không cho phép bỏ qua schema/ACL** và không tự biến LDAP thành một cơ sở dữ liệu quan hệ.

## 2. Phân biệt LDAP filter, DN và objectClass

Một LDAP SearchRequest thường cần những tham số độc lập:

| Tham số | Ví dụ | Mục đích |
| --- | --- | --- |
| **Server / connection** | ldaps://ldap.lab.example:636 | Chọn directory, TLS và bind identity |
| **Base DN** | ou=people,dc=lab,dc=example | Nơi bắt đầu tìm trong cây thư mục |
| **Scope** | SUBTREE | Tìm tại base và các entry hậu duệ |
| **Filter** | (&(objectClass=inetOrgPerson)(uid=linh)) | Chọn entry thỏa điều kiện |
| **Attributes** | uid,cn,mail | Những thuộc tính muốn nhận |
| **Size/time limit** | 100 entry / 3000 ms | Giới hạn tài nguyên tìm kiếm |

Một filter **không chứa đường dẫn DN** theo cách SQL có tên bảng. Đây là hai lớp khác nhau:

~~~text
DN:
  uid=linh,ou=people,dc=lab,dc=example

Search base:
  ou=people,dc=lab,dc=example

Search filter:
  (&(objectClass=inetOrgPerson)(uid=linh))
~~~

Nếu search base quá hẹp, ví dụ **ou=contractors** thay cho **ou=people**, kết quả vẫn rỗng dù filter chính xác. Nếu tài khoản bind không có quyền **search/read**, server có thể ẩn entry hoặc một số attribute. **@Query chỉ kiểm soát phần khai báo search**, không tự cấp quyền truy cập.

### 2.1. Dùng objectClass để giới hạn loại entry

Một nhánh LDAP có thể chứa **person**, **groupOfNames**, **organizationalUnit** và những lớp do tổ chức định nghĩa. Khi tìm người dùng, thêm **(objectClass=inetOrgPerson)** giúp filter rõ mục đích và tránh vô tình nhận một loại entry khác có chung attribute **cn**.

Tùy server, thuộc tính objectClass có quy tắc matching không phân biệt chữ hoa/chữ thường. Tuy nhiên, **không suy diễn toàn bộ attribute LDAP đều case-insensitive**: matching rule của từng attribute được schema quyết định.

## 3. Dữ liệu và cấu hình chuẩn bị cho bài

Ví dụ sử dụng directory lab:

~~~text
dc=lab,dc=example
├── ou=people
│   ├── uid=linh
│   ├── uid=an
│   └── uid=binh
└── ou=groups
    └── cn=developers
~~~

Tập entry mẫu trong **ou=people**:

~~~ldif
dn: uid=linh,ou=people,dc=lab,dc=example
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: linh
cn: Linh Nguyen
sn: Nguyen
mail: linh@lab.example
description: Engineer

dn: uid=an,ou=people,dc=lab,dc=example
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: an
cn: An Tran
sn: Tran
mail: an@lab.example
description: Engineer

dn: uid=binh,ou=people,dc=lab,dc=example
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: binh
cn: Binh Le
sn: Le
description: Intern
~~~

Nhóm thử nghiệm (tùy chọn cho phần filter thành viên):

~~~ldif
dn: cn=developers,ou=groups,dc=lab,dc=example
objectClass: top
objectClass: groupOfNames
cn: developers
member: uid=linh,ou=people,dc=lab,dc=example
member: uid=an,ou=people,dc=lab,dc=example
~~~

**Lưu ý:** Các suffix và OU cha phải được tạo trước; không import lại entry đã tồn tại. **groupOfNames** thường yêu cầu ít nhất một **member**, nên LDIF mẫu đã có hai thành viên. Ví dụ dùng dữ liệu giả, không đưa mật khẩu, DN người dùng thật hoặc bản sao production vào repository học tập.

Một cách kết nối ứng dụng Spring Boot:

~~~yaml
spring:
  ldap:
    urls: "ldaps://ldap.lab.example:636"
    base: "dc=lab,dc=example"
    username: "uid=reader,ou=services,dc=lab,dc=example"
    password: "${LDAP_BIND_PASSWORD}"
    base-environment:
      "[com.sun.jndi.ldap.connect.timeout]": "3000"
      "[com.sun.jndi.ldap.read.timeout]": "5000"
~~~

Tài khoản **reader** phải được tạo và cấp quyền read/search trong lab; server phải có chứng chỉ TLS được JVM tin cậy. **ContextSource base** là **dc=lab,dc=example**, do đó **ou=people** trong cấu hình search base của Spring LDAP thường là DN tương đối với suffix này.

### 3.1. Entity Spring LDAP ODM

~~~java
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

    @Attribute(name = "description")
    private String description;

    // No-args constructor, getters và setters được lược bỏ.
}
~~~

Các quy tắc ODM đáng nhớ:

- **@Entry** mô tả base và tập objectClass của entry mà Java class ánh xạ.
- **@Id** trong Spring LDAP là **DN**, có kiểu **javax.naming.Name**, không phải số Long theo JPA.
- **@Attribute(name = "cn")** ánh xạ Java field **commonName** sang LDAP attribute **cn**. Filter **@Query** dùng **tên LDAP attribute** trong filter, không phải tên Java field.
- LDAP có schema: **cn** và **sn** thường là MUST của person; attribute như **mail** có thể vắng.
- Không đặt field Java tùy ý vào ODM mà không kiểm tra objectClass/MUST/MAY/ACL.

### 3.2. Repository đúng package annotation

~~~java
import java.util.List;
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;
import org.springframework.data.ldap.repository.Query;
import org.springframework.data.repository.query.Param;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {

    Optional<DirectoryPerson> findByUid(String uid);

    @Query("(&(objectClass=inetOrgPerson)(mail=:email))")
    List<DirectoryPerson> findByEmail(
        @Param("email") String email
    );
}
~~~

Đúng annotation ở đây là **org.springframework.data.ldap.repository.Query**, **không phải org.springframework.data.jpa.repository.Query** và cũng không phải một annotation SQL khác. **LdapRepository** chỉ nhận tham số generic **entity class**; kiểu ID LDAP là **javax.naming.Name** qua mapping ODM.

## 4. Khai báo @Query với tham số theo tên

Cú pháp cơ bản:

~~~java
@Query("(&(objectClass=inetOrgPerson)(uid=:uid))")
Optional<DirectoryPerson> findOneByUidFilter(
    @Param("uid") String uid
);
~~~

Đoạn mã là phương thức nằm bên trong **DirectoryPersonRepository**. Khi gọi:

~~~java
Optional<DirectoryPerson> person =
    repository.findOneByUidFilter("linh");
~~~

Spring Data LDAP lấy **:uid** trong filter template, lấy giá trị tương ứng từ tham số method, mã hóa giá trị được bind trực tiếp và tạo filter search. Với input **linh**, filter hiệu dụng có dạng:

~~~ldap
(&(objectClass=inetOrgPerson)(uid=linh))
~~~

**@Param("uid")** giúp ràng buộc minh bạch, không phụ thuộc Java compiler có giữ tên tham số qua tùy chọn **-parameters** hay không. Dùng tên tham số có ý nghĩa giúp tránh lỗi khi refactor method.

### 4.1. Tìm một người theo uid hoặc mail

~~~java
@Query(
    "(&(objectClass=inetOrgPerson)(|(uid=:identity)(mail=:identity)))"
)
List<DirectoryPerson> findByUidOrEmail(
    @Param("identity") String identity
);
~~~

Đây là **AND** giữa loại object với một nhóm **OR**:

~~~text
(&
  (objectClass=inetOrgPerson)
  (|
    (uid=linh)
    (mail=linh)
  )
)
~~~

Hai lần xuất hiện **:identity** dùng cùng một giá trị. Nếu directory có nhiều entry cùng mail hoặc uid không được bảo đảm duy nhất trong phạm vi search, truy vấn có thể trả **nhiều kết quả**; vì thế **List** hợp lý hơn khi chưa có một ràng buộc duy nhất đã được server bảo đảm.

**Cảnh báo authentication:** Không coi tìm thấy một entry theo mail hoặc uid đồng nghĩa danh tính người gọi đã được xác thực. Authentication cần cơ chế bind/password/Spring Security LDAP và kiểm tra quyền riêng.

### 4.2. Hai tham số có tên khác nhau

~~~java
@Query(
    "(&(objectClass=inetOrgPerson)(sn=:surname)(description=:role))"
)
List<DirectoryPerson> findBySurnameAndRole(
    @Param("surname") String surname,
    @Param("role") String role
);
~~~

Với **surname = Nguyen**, **role = Engineer**, truy vấn yêu cầu đồng thời **sn=Nguyen** và **description=Engineer**. **description** vốn là attribute mô tả tự do, không mặc nhiên đại diện cho “role” có semantics phân quyền; ví dụ chỉ minh họa cách bind hai điều kiện. Nếu bài toán thực là phân quyền, cần schema/attribute phù hợp và hệ thống authorization riêng.

## 5. Tham số theo vị trí ?0, ?1

Spring Data LDAP hỗ trợ vị trí **zero-based**:

~~~java
@Query(
    "(&(objectClass=inetOrgPerson)(sn=?0)(description=?1))"
)
List<DirectoryPerson> findBySurnameAndDescription(
    String surname,
    String description
);
~~~

| Placeholder | Tham số Java |
| --- | --- |
| **?0** | Tham số thứ nhất: surname |
| **?1** | Tham số thứ hai: description |
| **?2** | Tham số thứ ba, nếu có |

Đây không phải cú pháp **?1 = tham số thứ nhất** thường thấy trong một số ngữ cảnh JPQL. **Spring Data LDAP @Query dùng ?0 bắt đầu từ 0**, theo tài liệu chính thức.

Về lâu dài, một method có nhiều tham số positional dễ sai sau khi đổi thứ tự argument, nhất là khi các trường đều có kiểu String. Nên ưu tiên **:surname**, **:role** cùng **@Param** khi filter có nhiều điều kiện.

### 5.1. Không nối trực tiếp input vào annotation

Annotation Java phải là giá trị tĩnh tại thời điểm biên dịch; không thể tạo biểu thức filter bằng cách nối string runtime bên trong annotation như:

~~~java
// Không hợp lệ/không đúng cách làm:
// @Query("(uid=" + userInput + ")")
~~~

Phần filter tĩnh nằm trong **@Query**; input động đi vào **method arguments**. Khi điều kiện hoặc tên attribute phải thay đổi phức tạp theo runtime, dùng **LdapQueryBuilder** hoặc custom repository/service thay vì cố chèn mọi thứ vào một chuỗi annotation.

## 6. Cú pháp bộ lọc LDAP cần nắm trước khi dùng @Query

LDAP filter theo RFC 4515 có cú pháp ngoặc tròn, toán tử so sánh và các nhóm logic. Các ví dụ:

| Filter | Ý nghĩa | Trường hợp |
| --- | --- | --- |
| **(uid=linh)** | Equality: uid bằng linh | Tra cứu login |
| **(mail=*)** | Presence: có attribute mail | Tìm entry có email |
| **(!(mail=*))** | NOT: không có mail | Tìm entry thiếu email |
| **(cn=Lin*)** | Substring: bắt đầu bằng Lin | Tìm tên theo prefix |
| **(cn=*Nguyen)** | Substring: kết thúc bằng Nguyen | Tìm theo suffix |
| **(cn=*inh*)** | Substring: chứa inh | Tìm theo chuỗi con |
| **(&(sn=Nguyen)(mail=*))** | AND hai điều kiện | Họ Nguyen có email |
| **(\|(uid=linh)(uid=an))** | OR hai điều kiện | uid là linh hoặc an |
| **(!(description=Intern))** | NOT một điều kiện | Không mang giá trị Intern |
| **(employeeNumber>=1000)** | Greater-or-equal nếu syntax/matching rule hỗ trợ | So sánh theo attribute schema |
| **(cn~=Linh)** | Approximate match, nếu server hỗ trợ | Phụ thuộc matching rule server |

Đối với filter ghép, **không đặt dấu cách tùy ý vào cấu trúc điều kiện** nếu chưa hiểu cách parser của server xử lý. Một biểu thức dễ đọc khi xuống dòng trong tài liệu thường phải viết thành một **chuỗi liên tiếp** trong annotation Java.

**Phụ thuộc schema:** Không phải attribute nào cũng hỗ trợ ordering **>=**, **<=** hoặc approximate match **~=**. Ví dụ **mail** có matching rule khác **entryUUID**, **objectGUID** hoặc thuộc tính Integer. Không suy rằng dấu **>=** luôn mang nghĩa số học nếu syntax/matching rule thực tế khác.

### 6.1. AND, OR, NOT kết hợp đúng cách

Tìm người **có mail** nhưng **không có description=Intern**:

~~~java
@Query(
    "(&(objectClass=inetOrgPerson)(mail=*)(!(description=Intern)))"
)
List<DirectoryPerson> findPeopleWithMailExcludingInterns();
~~~

Tìm người có **uid hoặc mail** trùng một input và có **sn=Nguyen**:

~~~java
@Query(
    "(&(objectClass=inetOrgPerson)(sn=Nguyen)"
  + "(|(uid=:identity)(mail=:identity)))"
)
List<DirectoryPerson> findNguyenByUidOrMail(
    @Param("identity") String identity
);
~~~

Java compiler nối hai string literals ở trên thành một filter. Dấu **+** này chỉ nối **các hằng chuỗi trong source**, không nối input người dùng, nên không tạo filter injection.

### 6.2. Trường hợp thiếu attribute khác attribute rỗng

**(!(mail=*))** là tìm entry **không có attribute mail** (trong phạm vi dữ liệu server có thể dùng để đánh giá filter). Nó không tương đương một chuỗi JSON **mail: ""**, SQL **mail IS NULL** trong mọi hệ thống hoặc một Java Optional.empty() đã giải thích quyền ACL. LDAP attribute rỗng, attribute bị ẩn và attribute không tồn tại là những trường hợp cần phân biệt theo schema/provider.

## 7. @Query với base, searchScope, countLimit và timeLimit

Javadoc của **org.springframework.data.ldap.repository.Query** hiện có các phần tử:

| Phần tử | Kiểu | Mặc định | Ý nghĩa |
| --- | --- | --- | --- |
| **value** | String | Chuỗi rỗng | LDAP filter template |
| **base** | String | **""** | Search base dùng trong LdapQueryBuilder, hỗ trợ parameter binding |
| **searchScope** | SearchScope | **SUBTREE** | OBJECT, ONELEVEL hoặc SUBTREE |
| **countLimit** | int | **0** | Giới hạn số entry, 0 là không giới hạn ở tầng này |
| **timeLimit** | int | **0** | Giới hạn thời gian Search tính bằng mili giây, 0 là không giới hạn ở tầng này |

Ví dụ giới hạn query theo nhánh và tài nguyên:

~~~java
import org.springframework.ldap.query.SearchScope;

@Query(
    value = "(&(objectClass=inetOrgPerson)(description=:role))",
    base = "ou=people",
    searchScope = SearchScope.SUBTREE,
    countLimit = 100,
    timeLimit = 3000
)
List<DirectoryPerson> findPeopleByRoleUnderPeople(
    @Param("role") String role
);
~~~

Đặt các method trên trong **DirectoryPersonRepository**, import **SearchScope** vào cùng file. Với ContextSource base **dc=lab,dc=example**, ý định của **base="ou=people"** là tìm dưới nhánh **ou=people,dc=lab,dc=example**. Vì **@Entry(base="ou=people")** cũng mô tả phạm vi entity, hãy kiểm chứng **search base thực tế** của repository trên phiên bản Spring Data LDAP đang dùng; đừng vô tình cộng suffix hoặc nhánh **ou=people** hai lần qua nhiều lớp config.

**Không dùng @Query(base = ...) với một DN nhận thẳng từ HTTP request** mà không xác minh base được phép. Search base là phạm vi truy cập, không phải bộ lọc tùy ý được người dùng cuối toàn quyền định nghĩa.

### 7.1. OBJECT, ONELEVEL, SUBTREE

Giả sử cây:

~~~text
dc=lab,dc=example
└── ou=people
    ├── uid=linh
    └── ou=contractors
        └── uid=mai
~~~

Nếu base là **ou=people**:

| Scope | Có thể xem xét entry nào? |
| --- | --- |
| **OBJECT** | Chỉ chính entry **ou=people** |
| **ONELEVEL** | Các entry con trực tiếp như **uid=linh** và **ou=contractors** |
| **SUBTREE** | Entry base cùng mọi hậu duệ, bao gồm **uid=mai** |

Trong ví dụ filter **(objectClass=inetOrgPerson)**, entry OU không thỏa dù nằm trong scope. Chọn ONELEVEL có thể giúp ngăn truy vấn quét sâu hơn mức yêu cầu, nhưng nếu người dùng được chuyển OU con thì câu search ONELEVEL không còn tìm thấy họ.

### 7.2. countLimit không phải phân trang

**countLimit=100** chỉ đặt giới hạn số entry mà tìm kiếm có thể trả về; nó **không cung cấp page 1/page 2**, không tự sort theo uid và không hứa kết quả là 100 entry đầu theo một thứ tự cố định. Khi server hoặc client chạm size limit, có thể nhận **sizeLimitExceeded**, trả tập không đầy đủ hoặc hành vi phụ thuộc provider.

Hướng dẫn Spring Data LDAP nói rõ **paging và sorting không được hỗ trợ cho Spring LDAP repositories** theo cùng cơ chế của các store quan hệ. Nếu cần **LDAP paged results control**, hãy kiểm tra **LdapTemplate/JNDI LDAP Controls** hoặc một LDAP client phù hợp với server, thay vì gắn thêm **Pageable/Sort** rồi mặc định thành LDAP paging.

### 7.3. timeLimit không giống kết nối timeout

| Giới hạn | Được cấu hình ở đâu | Điều nó giới hạn |
| --- | --- | --- |
| **@Query(timeLimit=3000)** | Annotation method | Thời gian Search ở tầng LDAP query |
| **com.sun.jndi.ldap.connect.timeout** | JNDI environment | Thời gian mở TCP/đợi native pool trong một số trường hợp |
| **com.sun.jndi.ldap.read.timeout** | JNDI environment | Thời gian chờ phản hồi LDAP |
| **HTTP/job deadline** | API/application | Thời gian tổng của một nghiệp vụ |

Một request có thể mất thêm thời gian vì chờ mượn pool, DNS/TLS, retry hoặc nhiều query. **@Query timeLimit không phải hard timeout cho toàn HTTP request**.

### 7.4. @Query không có tùy chọn attributes

Javadoc annotation ở phiên bản tham khảo có **value, base, searchScope, countLimit, timeLimit**, **không có thuộc tính attributes** để chỉ định danh sách attribute trả về. Khi cần **projection chỉ lấy cn/mail**, mapping tùy chỉnh hoặc control đặc biệt, **LdapTemplate** với **LdapQueryBuilder.attributes("cn","mail")** có thể phù hợp hơn.

## 8. Escape filter: tránh LDAP injection khi bind tham số

LDAP filter có các ký tự cú pháp đặc biệt. Nếu ghép input từ HTTP vào một filter:

~~~java
// Sai: không đưa input chưa escape trực tiếp vào LDAP filter.
String dangerousFilter = "(uid=" + userSuppliedUid + ")";
~~~

Một người dùng có thể gửi chuỗi chứa các ký tự đóng ngoặc, wildcard hoặc toán tử LDAP, từ đó thay đổi ý nghĩa filter, làm search quá rộng hoặc gây lỗi parse. Đây là **LDAP filter injection**, khác với **SQL injection** nhưng cùng thuộc lớp lỗi đưa input không tin cậy vào cú pháp truy vấn.

Với **@Query** và tham số được bind trực tiếp:

~~~java
@Query("(&(objectClass=inetOrgPerson)(uid=:uid))")
List<DirectoryPerson> findMatchingUid(
    @Param("uid") String uid
);
~~~

Spring Data LDAP thực hiện **parameter encoding** đối với String-based queries. Theo tài liệu chính thức, cơ chế mặc định escape những ký tự đặc biệt theo quy tắc LDAP filter (tài liệu lịch sử nhắc **RFC 2254**; cú pháp LDAP filter chuẩn hóa hiện nay được mô tả trong **RFC 4515**).

### 8.1. Các ký tự đặc biệt quan trọng

| Ký tự trong giá trị | Escape dạng octet trong filter |
| --- | --- |
| Dấu sao **\*** | **\2a** |
| Mở ngoặc **(** | **\28** |
| Đóng ngoặc **)** | **\29** |
| Backslash **\** | **\5c** |
| Byte NUL | **\00** |

Ví dụ giá trị input là một chuỗi chứa dấu sao:

~~~text
Input mong muốn so khớp CHÍNH XÁC:
  linh*

Giá trị trong LDAP equality filter sau escape:
  (uid=linh\2a)
~~~

Trong filter cuối, **\2a** biểu diễn ký tự dấu sao như một phần của **giá trị**, không phải wildcard. Nếu thay bằng **(uid=linh*)**, filter có ý nghĩa **prefix search** và có thể trả nhiều tài khoản.

**Đừng tự escape hai lần.** Nếu ứng dụng chuyển input thành chuỗi đã escape bằng tay rồi truyền qua **@Query** với parameter binding mặc định, encoder có thể escape chính backslash lần nữa, khiến filter tìm sai giá trị. Hãy chọn một đường mã hóa rõ ràng và kiểm thử.

### 8.2. Escaping filter khác escaping DN

Hai ví dụ dễ nhầm:

~~~text
LDAP filter:
  (uid=linh\2a)

LDAP distinguished name:
  uid=linh\,an,ou=people,dc=lab,dc=example
~~~

**LDAP filter** theo RFC 4515, còn **DN/RDN** tuân theo RFC 4514. Khi cần dựng DN từ input, dùng **javax.naming.ldap.LdapName** và **Rdn**; không dùng chuỗi đã filter-escape để tạo RDN. Khi tìm kiếm trong **@Query**, giữ riêng **base DN** và filter value.

### 8.3. Filter an toàn không thay thế authorization

Một người dùng hợp lệ có thể nhập uid/email của người khác. Dù tất cả ký tự được escape, filter vẫn có thể trả entry mà tài khoản bind được phép đọc. Vì vậy:

- Xác minh **người gọi API được phép tra cứu dữ liệu nào**.
- Cấp **LDAP ACL** tối thiểu cho bind identity của ứng dụng.
- Tránh trả các attribute nhạy cảm hơn nhu cầu nghiệp vụ.
- Không dùng kết quả search để tự động kết luận đã xác thực danh tính.
- Đặt **base, scope, count/time limits** để giảm truy vấn quá rộng.

## 9. Wildcard và substring: đâu là cấu trúc tĩnh, đâu là dữ liệu?

LDAP dùng dấu **\*** trong filter để tạo substring search. Vì encoder mặc định escape dấu sao bên trong **giá trị tham số**, việc đưa chuỗi **"Lin*"** vào **(cn=:name)** thường tìm **tên có dấu sao thật**, chứ không phải tất cả tên bắt đầu bằng Lin.

### 9.1. Đưa wildcard cố định vào filter template

Nếu yêu cầu nghiệp vụ là tìm tên **bắt đầu bằng tiền tố** do người dùng nhập, có thể giữ wildcard **cố định trong @Query**:

~~~java
@Query("(&(objectClass=inetOrgPerson)(cn=:prefix*))")
List<DirectoryPerson> findByCommonNamePrefix(
    @Param("prefix") String prefix
);
~~~

Nếu người dùng nhập **Lin**, filter mong muốn có dạng:

~~~text
(&(objectClass=inetOrgPerson)(cn=Lin*))
~~~

Nếu họ nhập **Lin***, dấu sao trong phần **:prefix** phải được escape như một ký tự của giá trị, còn dấu sao cuối **ngoài placeholder** vẫn là wildcard do lập trình viên kiểm soát. Cần kiểm thử bằng server hoặc repository integration test để xác nhận cú pháp binding và kết quả trong phiên bản Spring Data LDAP đang dùng.

Tương tự có thể dùng biểu thức dạng **(cn=*:part*)** để mô tả contains search, nhưng nên cân nhắc hiệu năng vì wildcard đầu thường làm directory khó sử dụng index thông thường.

**Không biến một ô search tổng quát thành truy vấn unrestricted.** Nếu prefix rỗng, filter có thể trở thành presence query **(cn=*)**; đặt độ dài tối thiểu và giới hạn số kết quả ở tầng service.

### 9.2. @LdapEncode và LdapEncoder.LikeEncoder

Từ các phiên bản Spring Data LDAP hỗ trợ annotation **@LdapEncode** (theo Javadoc **Since 3.5**), có thể thay cách encode của **một tham số được bind trực tiếp**. Spring Data LDAP cung cấp chiến lược **LdapEncoder.LikeEncoder** giữ lại dấu sao làm wildcard trong khi vẫn xử lý các ký tự cần escape khác.

~~~java
import org.springframework.data.ldap.repository.LdapEncode;
import org.springframework.data.ldap.repository.LdapEncoder;

@Query("(&(objectClass=inetOrgPerson)(cn=:pattern))")
List<DirectoryPerson> findByApprovedNamePattern(
    @Param("pattern")
    @LdapEncode(LdapEncoder.LikeEncoder.class)
    String pattern
);
~~~

Giả sử **pattern = "Lin*"**, filter có thể trở thành **(cn=Lin*)** theo ngữ nghĩa like. Tuy nhiên **LikeEncoder giữ wildcard có chủ đích**, nên **pattern** không còn là một exact-match input thông thường. Không nhận pattern tùy ý chưa kiểm soát từ HTTP rồi dùng nó để quét toàn directory. Chỉ cho phép một cú pháp search được mô tả rõ (ví dụ prefix dài ít nhất 2–3 ký tự, một wildcard ở cuối) và thêm giới hạn số bản ghi.

**@LdapEncode chỉ áp dụng cho tham số được bind trực tiếp vào query method.** Nó **không tự áp dụng cho derived queries** và **không tự áp dụng cho các giá trị lấy qua SpEL hoặc property placeholders**. Trong dự án Spring Data LDAP cũ, cần xác nhận version có annotation này trước khi dùng.

### 9.3. Trường hợp tốt hơn nên dùng LdapQueryBuilder

Nếu người dùng lựa chọn **exact**, **prefix**, **contains** ở runtime, đừng dùng một chuỗi @Query cố gắng mang mọi trường hợp bằng wildcard do client tự cung cấp. Dùng service/implementation riêng với **LdapQueryBuilder** và API được thiết kế cho kiểu filter đang cần:

~~~java
import java.util.List;
import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class PersonSearchService {
    private final LdapTemplate ldapTemplate;

    public PersonSearchService(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    public List<String> findExactUids(String uid) {
        return ldapTemplate.search(
            query().base("ou=people")
                   .attributes("uid")
                   .where("objectClass").is("inetOrgPerson")
                   .and("uid").is(uid),
            (AttributesMapper<String>) attrs ->
                (String) attrs.get("uid").get()
        );
    }
}
~~~

Đây là **exact match** và dùng builder xử lý giá trị. Với prefix/wildcard, chọn API like phù hợp sau khi validate pattern. Không gọi **query().filter(hardcodedUserString)** nếu chuỗi filter được ghép từ HTTP input: overload nhận filter raw không tự escape giá trị.

## 10. SpEL và property placeholders: khả năng mạnh nhưng rủi ro khác

Spring Data LDAP hỗ trợ **Value Expressions** trong @Query, gồm **SpEL** và **Spring property placeholders**. Các cú pháp này có thể hữu ích khi cần đọc thông tin người dùng hiện tại hoặc điều kiện từ cấu hình.

Ví dụ về mặt cú pháp (chỉ để minh họa):

~~~java
// Giá trị lấy từ SpEL không được tự động escape giống :uid.
@Query("(&(objectClass=inetOrgPerson)(uid=?#{[0]}))")
List<DirectoryPerson> unsafeSpelBinding(String uid);
~~~

Nếu **uid** đến từ nguồn không tin cậy, cách này có nguy cơ đưa các ký tự cú pháp LDAP vào filter vì **kết quả SpEL không tự được escape theo RFC 2254/4515**. Dù có gắn **@LdapEncode** lên method parameter, annotation này không xử lý các biểu thức SpEL.

Mẫu nên dùng:

~~~java
@Query("(&(objectClass=inetOrgPerson)(uid=:uid))")
List<DirectoryPerson> safeDirectBinding(
    @Param("uid") String uid
);
~~~

### 10.1. Property placeholder cũng cần xem là dữ liệu đầu vào

Một ví dụ property placeholder theo cách Spring Data LDAP hỗ trợ:

~~~java
// Minh họa cú pháp: giá trị 'stage' từ config không tự được filter-escape.
@Query("(&(objectClass=inetOrgPerson)(uid=?0)(description=:?${directory.stage:dev}))")
List<DirectoryPerson> findInConfiguredStage(String uid);
~~~

Đoạn này chỉ minh họa cú pháp. **description** là attribute tự do, không phải trường môi trường chuẩn; nếu dùng làm giai đoạn trong hệ thống thật, cần có quy tắc schema/dữ liệu riêng. Quan trọng hơn, **giá trị chèn từ configuration property không tự được encode**. Chỉ dùng khi nguồn cấu hình đã được kiểm soát hoặc đã được escape đúng ngữ cảnh.

### 10.2. Đừng dùng SpEL để dựng tên attribute từ request

Ví dụ rủi ro về mặt thiết kế:

~~~text
Input HTTP:
  field = arbitraryAttribute
  value = arbitraryValue

Ý định:
  tạo filter (field=value) bằng SpEL không có whitelist
~~~

Tên attribute cũng là một phần của cú pháp filter, không thể an toàn chỉ bằng escape giá trị. Nếu nghiệp vụ cho phép chọn field, hãy ánh xạ **một danh sách field được phép** như **uid**, **cn**, **mail** sang tên LDAP attribute cố định trong code, sau đó bind value đúng cách. Với truy vấn quá động, dùng một custom repository/LDAP query builder được kiểm tra chặt chẽ.

### 10.3. Thứ tự ưu tiên khi chọn cách bind

| Nhu cầu | Phương án | Lý do |
| --- | --- | --- |
| Exact equality từ HTTP input | **:name** hoặc **?0** | Encoding tự động cho bound values |
| Prefix cố định | Wildcard tĩnh trong @Query + bound value | Người dùng không điều khiển cấu trúc filter |
| Wildcard do người dùng chủ động chọn | **@LdapEncode(LikeEncoder)** + validation nghiêm ngặt | Chỉ khi nghiệp vụ thật cần pattern |
| Giá trị từ SpEL/property | Escape/validate bằng cơ chế rõ ràng | Không tự encode như direct binding |
| Filter và field runtime nhiều lựa chọn | **LdapQueryBuilder/custom repository** | Dễ whitelist, test và giới hạn hơn |

## 11. Query theo thành viên nhóm LDAP

Không phải mọi entry là một **inetOrgPerson**. Một LDAP group thường có **objectClass=groupOfNames** và attribute đa trị **member** lưu **DN đầy đủ** của các thành viên.

Ví dụ entity nhóm:

~~~java
import java.util.Set;
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=groups",
    objectClasses = {"top", "groupOfNames"}
)
public class DirectoryGroup {
    @Id
    private Name dn;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "member")
    private Set<Name> memberDns;

    // Constructor không tham số, getter/setter được lược bỏ.
}
~~~

Repository với filter có điều kiện member:

~~~java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;
import org.springframework.data.ldap.repository.Query;
import org.springframework.data.repository.query.Param;

public interface DirectoryGroupRepository
        extends LdapRepository<DirectoryGroup> {

    @Query(
        value = "(&(objectClass=groupOfNames)(member=:memberDn))",
        base = "ou=groups"
    )
    List<DirectoryGroup> findContainingMember(
        @Param("memberDn") String memberDn
    );
}
~~~

Input ví dụ:

~~~text
uid=linh,ou=people,dc=lab,dc=example
~~~

**member** nhận DN, không phải chỉ **linh** hoặc **uid=linh**. Dùng **LdapName/Rdn** để dựng DN từ các phần động, sau đó truyền dạng chuỗi vào tham số bound của filter. LDAP server quyết định matching rule cho **member** (thường là DN syntax/matching rule), vì vậy cách biểu diễn/chuẩn hóa DN cần được thử trên server thực.

### 11.1. Đừng nhầm group lookup với xác thực hoặc phân quyền

Tìm thấy entry nhóm chứa một DN không tự chứng minh người gọi HTTP đang đăng nhập bằng entry đó. Trong hệ thống authorization cần xem **identity mapping**, **nested groups**, nhóm động, replication, tình trạng tài khoản và chính sách kiểm tra quyền riêng.

Nếu nhóm dùng objectClass khác như **groupOfUniqueNames**, **posixGroup** hoặc AD **group** với thuộc tính/semantics khác, filter ở trên không áp dụng máy móc. Cần kiểm tra **schema của server** và cách nhóm được tổ chức trước khi viết @Query.

### 11.2. Nested group không tự được duyệt đệ quy

Filter **(member=DN)** trên **groupOfNames** kiểm tra một giá trị member theo server matching. Nó **không tự đi theo toàn bộ nested groups** và không bảo đảm AD transitive membership. Những LDAP matching rule mở rộng của AD (nếu dùng) cần filter riêng và phải kiểm thử đúng server, không áp dụng chúng cho OpenLDAP mặc định.

## 12. So sánh @Query, derived query và LdapTemplate

| Trường hợp | Derived repository method | **@Query** | **LdapTemplate** |
| --- | --- | --- | --- |
| Equality đơn giản theo uid | Tốt | Dùng được | Dùng được |
| Filter AND/OR/NOT lồng nhau | Có thể tên method dài/khó đọc | **Rõ ràng** | Rõ ràng bằng builder |
| Tìm member theo DN | Có thể tùy mapping property | Tốt khi filter cố định | Tốt |
| Chọn filter/field theo runtime | Không linh hoạt | Hạn chế vì annotation tĩnh | **Phù hợp hơn** |
| Chỉ nhận một số LDAP attributes | Phụ thuộc mapping/projection support | Annotation không có **attributes** option | **LdapQueryBuilder.attributes** |
| SearchControls/LDAP controls đặc biệt | Hạn chế | Một số thuộc tính search scope/limits | Linh hoạt hơn qua API và JNDI |
| Mapping thành entity ODM | Có | Có | Có thể qua mapper/ODM |
| Escaping input bình thường | Theo query derivation | Có cho direct-bound string params | Có với query builder/bound params |
| Điều kiện lấy từ SpEL/property | Tùy implementation | **Cần escape thủ công** | Chọn API an toàn ngay trong code |

**Ví dụ cùng ý định qua ba cách:**

~~~java
// 1. Derived query: khai báo trong repository.
List<DirectoryPerson> findByUid(String uid);

// 2. @Query: khai báo filter rõ ràng trong repository.
@Query("(&(objectClass=inetOrgPerson)(uid=:uid))")
List<DirectoryPerson> findByUidUsingFilter(
    @Param("uid") String uid
);
~~~

~~~java
// 3. LdapTemplate: method trong service có field ldapTemplate.
List<String> uids = ldapTemplate.search(
    query().base("ou=people")
           .attributes("uid")
           .where("objectClass").is("inetOrgPerson")
           .and("uid").is(uid),
    (org.springframework.ldap.core.AttributesMapper<String>)
        attrs -> (String) attrs.get("uid").get()
);
~~~

Ví dụ LdapTemplate cần import static **org.springframework.ldap.query.LdapQueryBuilder.query** và **java.util.List**. Nó trả **List<String>** thay vì entity, vì mapper chỉ lấy uid. Hai repository examples được đặt trong một interface đã import **@Query**, **@Param** và entity.

Chọn API theo yêu cầu thực:

- Nếu chỉ cần exact match đơn giản theo field entity: derived query thường dễ hiểu nhất.
- Nếu filter cố định phức tạp và cần tái sử dụng qua một method: **@Query** làm rõ mục đích.
- Nếu cần tạo điều kiện theo runtime, giới hạn attribute, search controls hoặc mapping tùy biến: **LdapTemplate** phù hợp.

### 12.1. Không dùng @Query như SQL UPDATE/DELETE

**@Query** ở đây dành cho **LDAP search query**, không phải câu lệnh **UPDATE ... SET ...**. Với CRUD LDAP:

- Thêm entry: **repository.save(...)** khi entity mới hoặc **LdapTemplate.bind(...)**.
- Sửa attribute: **repository.save(...)**, **LdapTemplate.modifyAttributes(...)**, tùy nghiệp vụ.
- Đổi DN: **LdapTemplate.rename(...)** hoặc thao tác ModifyDN tương ứng.
- Xóa entry: **repository.delete(...)** hoặc **LdapTemplate.unbind(...)**.

Các thao tác này phải tuân **schema**, **ACL**, **DN** và concurrency của directory. Một **@Query** lọc đúng người không tự tạo điều kiện update nguyên tử cho **save** sau đó.

## 13. Kết quả repository: List, Optional và tính duy nhất

Một phương thức @Query có thể trả **List<DirectoryPerson>** khi dự kiến nhiều entry, hoặc **Optional<DirectoryPerson>** khi nghiệp vụ/truy vấn được thiết kế cho tối đa một kết quả.

~~~java
@Query("(&(objectClass=inetOrgPerson)(uid=:uid))")
Optional<DirectoryPerson> findOneByUid(
    @Param("uid") String uid
);

@Query("(&(objectClass=inetOrgPerson)(description=:role))")
List<DirectoryPerson> findAllByRole(
    @Param("role") String role
);
~~~

Không có bảo đảm chung rằng **uid** hoặc **mail** là duy nhất trên tất cả OU/naming contexts nếu tổ chức chưa áp quy tắc riêng. Nếu method khai báo một kết quả nhưng filter thực tế trả nhiều entry, Spring Data có thể báo **IncorrectResultSizeDataAccessException** hoặc một exception tương đương thay vì tự chọn bản ghi đầu tiên.

**Không dựa vào thứ tự List** khi LDAP server không có sort control cụ thể; kết quả Search không mặc nhiên được sắp xếp theo uid, DN hoặc thời điểm tạo. Không dùng **list.get(0)** để quyết định danh tính đăng nhập nếu filter có thể khớp nhiều entry.

### 13.1. Dùng countLimit chỉ để bảo vệ tài nguyên, không để chứng minh unique

Một truy vấn giới hạn **countLimit=1** có thể chỉ trả một entry ngay cả khi thực tế có nhiều entry thỏa filter. Vì thế **không dùng countLimit=1** như một cơ chế phát hiện UID/email bị trùng.

Nếu nghiệp vụ cần uniqueness:

1. Giới hạn search base đúng vùng có quy tắc duy nhất.
2. Dùng schema/naming constraint hoặc cơ chế authoritative identity của directory nếu có.
3. Trong tình huống chưa chắc chắn, tìm đủ để phân biệt **0/1/nhiều** trước khi chọn.
4. Không biến “tìm thấy một entry” thành bảo đảm rằng nó là entry duy nhất.

### 13.2. Khi tìm kiếm trả rỗng

Một **List rỗng** có thể có nhiều nguyên nhân:

- Filter đúng nhưng dữ liệu không tồn tại.
- Base DN sai nhánh hoặc searchScope không bao phủ entry.
- ACL của bind account không cho nhìn thấy entry/attribute.
- Query dùng tên **Java field** thay cho tên **LDAP attribute** (ví dụ **commonName** thay vì **cn**).
- Tham số bị encode khác kỳ vọng (ví dụ wildcard từ input bị escape đúng thành dấu sao literal).
- Query chạy trên replica chưa đồng bộ hoặc một LDAP server khác.

Vì thế khi lỗi cần chẩn đoán, luôn ghi lại **endpoint logic, base, scope, tên filter/template, trạng thái ACL** và mã lỗi được phép công bố; không lập tức kết luận không có người dùng chỉ vì một query trả 0 kết quả.

## 14. Cấu hình Spring Boot và bật LDAP repositories

Với dự án Spring Boot có starter tương thích, dependency Maven minh họa:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-ldap</artifactId>
    </dependency>
</dependencies>
~~~

Tương đương trong Gradle Groovy:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-ldap'
}
~~~

Các ví dụ trên giả định dự án được quản lý bằng **Spring Boot BOM/Gradle dependency management** để chọn phiên bản tương thích; không tự thêm nhiều phiên bản Spring Data LDAP, Spring LDAP và Spring Framework khác nhau.

Spring Data LDAP repositories có thể được bật qua auto-configuration phù hợp hoặc **@EnableLdapRepositories** trong JavaConfig:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.ldap.repository.config.EnableLdapRepositories;

@Configuration(proxyBeanMethods = false)
@EnableLdapRepositories(
    basePackages = "org.example.directory.repository"
)
public class LdapRepositoryConfiguration {
}
~~~

Đây là ví dụ package giả định. Nếu Spring Boot đã tự phát hiện các repository và cấu hình bean thích hợp, không bật một lần scan trùng lặp vô ích. Cần có **LdapTemplate** được kết nối tới **ContextSource** với URL, base DN, bind identity và TLS đúng.

### 14.1. Nhiều LdapTemplate trong một ứng dụng

Nếu ứng dụng có hai directory (ví dụ **corporate AD** và **OpenLDAP lab**), đừng giả định một repository tự chọn đúng nguồn chỉ nhờ method **@Query** có filter đặc thù. **@Query** không chọn máy chủ LDAP; repository sử dụng **LdapTemplate** mà nó được cấu hình/đăng ký để dùng.

Với cấu hình thủ công:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.ldap.repository.config.EnableLdapRepositories;

@Configuration(proxyBeanMethods = false)
@EnableLdapRepositories(
    basePackages = "org.example.corp.repository",
    ldapTemplateRef = "corporateLdapTemplate"
)
class CorporateLdapRepositoryConfiguration {
}
~~~

Ví dụ này giả định **corporateLdapTemplate** đã được khai báo và trỏ tới đúng directory; không đủ để chạy nếu chưa cung cấp bean đó. Khi có nhiều template, cần tách phạm vi repository, credentials và search base rõ ràng. Filter đúng nhưng gửi tới nhầm LDAP server vẫn cho kết quả sai hoặc lỗi schema.

### 14.2. ContextSource base và @Entry/@Query base

Giả sử:

~~~text
ContextSource base: dc=lab,dc=example
Entity @Entry base: ou=people
Query @Query base: ou=people
Full LDAP search base cần quan sát: ou=people,dc=lab,dc=example
~~~

**Không truyền full DN một lần vào @Entry và thêm nó lần nữa qua ContextSource** nếu framework đã dùng đường dẫn tương đối. Khi thay đổi phiên bản Spring Data LDAP hoặc tổ chức lại repository, nên có integration test xác minh **base thật** của truy vấn thay vì chỉ tin cấu hình nhìn trên giấy. Một lỗi path có thể trả **noSuchObject (32)** hoặc một danh sách rỗng tùy API/chính sách xử lý.

## 15. Kiểm chứng filter bằng ldapsearch trước khi chạy Java

**ldapsearch** là công cụ tiện lợi để đối chiếu bộ lọc ở cấp giao thức LDAP. Nó không chạy Spring Data LDAP, nhưng giúp xác định liệu filter, DN, search scope và ACL có hợp lệ đối với directory hay không.

Chuẩn bị biến môi trường và nhập password tương tác:

~~~bash
export LDAP_URI='ldaps://ldap.lab.example:636'
export BASE_DN='dc=lab,dc=example'
export PEOPLE_DN='ou=people,dc=lab,dc=example'
export READER_DN='uid=reader,ou=services,dc=lab,dc=example'
~~~

Tìm một uid:

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$READER_DN" -W \
  -b "$PEOPLE_DN" -s sub \
  '(&(objectClass=inetOrgPerson)(uid=linh))' \
  dn uid cn sn mail
~~~

Tìm người có mail và không phải intern:

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$READER_DN" -W \
  -b "$PEOPLE_DN" -s sub \
  '(&(objectClass=inetOrgPerson)(mail=*)(!(description=Intern)))' \
  dn uid cn mail description
~~~

Tìm người có **uid hoặc mail** bằng một filter tĩnh:

~~~bash
ldapsearch -LLL -x -H "$LDAP_URI" \
  -D "$READER_DN" -W \
  -b "$PEOPLE_DN" -s sub \
  '(&(objectClass=inetOrgPerson)(|(uid=linh)(mail=linh@lab.example)))' \
  dn uid cn mail
~~~

Khi chuyển từ cú pháp annotation **:identity / ?0** sang công cụ **ldapsearch**, phải thay bằng **giá trị đã escape hợp lệ theo RFC 4515**; ldapsearch không biết gì về tham số Java của @Query.

### 15.1. Kiểm tra search scope tương đương

| @Query.searchScope | ldapsearch |
| --- | --- |
| **SearchScope.OBJECT** | **-s base** |
| **SearchScope.ONELEVEL** | **-s one** |
| **SearchScope.SUBTREE** | **-s sub** |

Ví dụ nếu một user nằm sâu trong **ou=contractors,ou=people**, **-s one** từ **ou=people** sẽ không xét user đó; **-s sub** có thể bao phủ nếu ACL cho phép.

### 15.2. Đối chiếu đúng tài khoản bind

Khi ldapsearch dưới quyền admin thấy dữ liệu nhưng repository dưới quyền reader trả rỗng, đó **không phải bằng chứng @Query bị sai**. Hãy chạy **ldapsearch cùng bind DN với ứng dụng**, cùng endpoint, base, scope, filter và attribute list; chỉ sau đó mới xem tới mapping Java.

Nếu LDAPS thất bại vì chứng chỉ không được tin cậy, sửa **truststore, CA và hostname**, không tắt xác minh TLS hoặc chuyển sang simple bind qua kết nối không mã hóa.

### 15.3. Lỗi thường gặp khi gõ filter trong shell

Nên đặt filter trong **dấu nháy đơn** ở Bash/PowerShell khi phù hợp để shell không tự xử lý **\***, dấu ngoặc hoặc ký tự đặc biệt. Với filter octet-escaped, cần giữ nguyên **backslash + hex digits**, không để shell diễn giải hoặc thay đổi dấu.

## 16. Viết integration test cho @Query

Một unit test mock repository chỉ xác minh service gọi đúng Java method; nó **không xác minh filter thực sự được Spring Data LDAP tạo ra**, cách encode tham số hay những quy tắc schema/ACL của server. Cần kiểm thử với LDAP nhúng hoặc directory lab có dữ liệu được kiểm soát.

### 16.1. Bộ dữ liệu fixture và giả định

Trước test, directory phải chứa ba user mẫu ở phần 3:

| uid | cn | sn | mail | description |
| --- | --- | --- | --- | --- |
| **linh** | Linh Nguyen | Nguyen | linh@lab.example | Engineer |
| **an** | An Tran | Tran | an@lab.example | Engineer |
| **binh** | Binh Le | Le | Không có | Intern |

Giả định:

- Server công bố schema **inetOrgPerson**, **person**, **organizationalPerson** và cho phép các attribute mẫu.
- **ou=people** có tồn tại và ContextSource base được cấu hình nhất quán.
- Reader có quyền **search/read** trên các entry/attribute cần kiểm tra.
- Không có các entry khác trùng uid trong test suffix; fixture được reset giữa các lượt.
- Test dùng **LDAPS** hoặc một directory nhúng có đặc điểm TLS rõ ràng.

### 16.2. JUnit 5: tìm đúng uid và OR

Giả sử repository khai báo:

~~~java
@Query("(&(objectClass=inetOrgPerson)(uid=:uid))")
List<DirectoryPerson> findMatchingUid(
    @Param("uid") String uid
);

@Query("(&(objectClass=inetOrgPerson)(|(uid=:identity)(mail=:identity)))")
List<DirectoryPerson> findByUidOrEmail(
    @Param("identity") String identity
);

@Query("(&(objectClass=inetOrgPerson)(!(mail=*)))")
List<DirectoryPerson> findWithoutMail();
~~~

Test có thể viết:

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class RepositoryQueryIntegrationTest {
    @Autowired
    DirectoryPersonRepository repository;

    @Test
    void findsOneUserByUid() {
        List<DirectoryPerson> persons =
            repository.findMatchingUid("linh");
        assertEquals(1, persons.size());
        assertEquals("linh", persons.get(0).getUid());
    }

    @Test
    void matchesUidOrEmail() {
        List<DirectoryPerson> persons =
            repository.findByUidOrEmail("linh@lab.example");
        assertEquals(1, persons.size());
        assertEquals("linh", persons.get(0).getUid());
    }

    @Test
    void findsPersonWithoutMail() {
        List<DirectoryPerson> persons =
            repository.findWithoutMail();
        assertTrue(
            persons.stream()
                .anyMatch(p -> "binh".equals(p.getUid()))
        );
    }
}
~~~

Để đoạn test biên dịch, entity cần **getUid()**, interface **DirectoryPersonRepository** cần khai báo các method đúng như phần trước, và ứng dụng phải có Spring Boot test dependencies cùng cấu hình directory lab. Đây là **mẫu integration test**, không phải bài test đã được chạy trên workspace của người học.

### 16.3. Test ký tự nguy hiểm không được biến thành wildcard

Một test quan trọng là đưa input chứa ký tự đặc biệt:

~~~java
@Test
void doesNotTreatAsteriskAsWildcardInUid() {
    // Cần dùng repository.findMatchingUid đã khai báo trong test class.
    List<DirectoryPerson> matches =
        repository.findMatchingUid("lin*");

    // Trong fixture không có uid chứa dấu sao literal.
    assertTrue(matches.isEmpty());
}
~~~

Nếu filter không escape, **(uid=lin*)** có thể khớp **linh**. Nếu filter encode đúng, dấu sao của input là literal và không khớp user fixture. Bài test giúp phát hiện một lỗi filter injection/wildcard expansion đơn giản.

Thêm một test với input chứa **(**, **)**, **backslash** để xác nhận filter không biến thành một cú pháp khác hoặc ném filter syntax error ngoài ý định.

### 16.4. Kiểm thử wildcard có kiểm soát

Với method **findByCommonNamePrefix("Lin")**, fixture dự kiến có user **Linh Nguyen**. Kiểm tra cả:

- Input **"Lin"** trả Linh.
- Input **"L*"** không cho phép người dùng tự nới wildcard nếu chính sách chỉ chấp nhận tiền tố literal.
- Input rỗng hoặc quá ngắn bị service từ chối trước truy vấn.
- **countLimit/timeLimit** thật sự được áp dụng theo version framework và provider.

Không chỉ assert rằng Spring context khởi tạo thành công. Cần có **LDAP search thật**, đối chiếu **DN và uid** trả về.

### 16.5. Test base/scope và ACL

Di chuyển tạm một user fixture vào **ou=contractors,ou=people**, sau đó:

1. Dùng **SearchScope.ONELEVEL** từ ou=people, kết quả không bao gồm user ở tầng sâu.
2. Dùng **SUBTREE**, kết quả có thể bao gồm user đó nếu ACL cho phép.
3. Chạy cùng filter dưới reader bị giới hạn quyền, xác minh hành vi thực thay vì giả định entry nào cũng hiển thị.
4. Đưa fixture trở lại hoặc dọn dữ liệu test để các case khác không phụ thuộc thứ tự.

**Không thực hiện di chuyển/xóa dữ liệu thật trong production** chỉ để kiểm tra scope.

## 17. Troubleshooting khi @Query trả sai hoặc không trả kết quả

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Query compile được nhưng trả rỗng | Base DN sai, scope không đủ sâu hoặc ACL che | Đối chiếu ldapsearch cùng bind DN |
| **@Query** không được sử dụng | Import sai package hoặc repository không được scan | Kiểm tra **org.springframework.data.ldap.repository.Query**, @EnableLdapRepositories |
| Có input đúng nhưng không khớp | Filter dùng tên field Java **commonName** thay vì LDAP attribute **cn** | Xem @Attribute và schema |
| Tên param không bind được | Sai **:email**, **@Param** hoặc cấu hình tên method param | Dùng @Param rõ tên và test bootstrap |
| Dùng **?1** cho tham số đầu tiên | LDAP @Query positional bắt đầu từ **?0** | Đánh lại index |
| Input **Lin*** không tìm prefix như kỳ vọng | Encoder mặc định escape dấu sao | Đưa wildcard tĩnh ra ngoài placeholder hoặc dùng LikeEncoder có kiểm soát |
| Kết quả SpEL làm filter sai/injection | SpEL output không tự escape | Chuyển sang direct parameter binding |
| Query về nhóm trả rỗng | Truyền uid thay vì full DN cho member hoặc sai objectClass | Kiểm tra schema/group type và DN syntax |
| Method yêu cầu một entry nhưng nhiều entry khớp | Không có uniqueness trong scope | Sửa contract và quy tắc uniqueness |
| **sizeLimitExceeded (4)** | Quá giới hạn phía client/server | Thu hẹp filter/base; xem index và limit |
| **timeLimitExceeded (3)** | Search quá lâu | Phân tích filter, index, scope, LDAP server capacity |
| **noSuchObject (32)** | Search base không tồn tại hoặc context base bị lặp | So sánh relative DN và full DN |
| **invalidCredentials (49)** | Bind sai | Kiểm tra secret và identity, không sửa filter |
| **insufficientAccessRights (50)** | Không đủ quyền search/read hoặc server policy | Kiểm tra ACL đúng bind |
| Query filter không hợp lệ | Sai dấu ngoặc hoặc matching operator | Kiểm tra theo RFC 4515, thử ldapsearch |
| Có kết quả LDAP nhưng mapper lỗi | Entry thiếu MUST/field hoặc objectClass khác | Kiểm tra @Entry/@Attribute, schema, DN |
| Query trên AD khác OpenLDAP | Attribute, matching rule hoặc schema khác | Viết test riêng theo server |
| Truy vấn nhìn thấy dữ liệu cũ | Đọc replica chưa đồng bộ | Kiểm tra endpoint và replication |

### 17.1. Quy trình chẩn đoán 8 bước

~~~mermaid
flowchart TD
    A["Repository @Query trả sai"] --> B["Kiểm tra package @Query và method args"]
    B --> C["Đối chiếu filter sau bind, tránh log dữ liệu nhạy cảm"]
    C --> D["Kiểm tra ContextSource URL/base/bind identity"]
    D --> E["ldapsearch cùng endpoint, base, scope và ACL"]
    E --> F{"Filter có khớp ở CLI không?"}
    F -->|Không| G["Sửa schema, filter, DN, scope, ACL hoặc dữ liệu"]
    F -->|Có| H["Kiểm tra @Entry/@Attribute mapping và version"]
    G --> I["Integration test regression"]
    H --> I
~~~

Thực hiện có thứ tự:

1. Kiểm tra **tên annotation/import**: @Query phải thuộc **Spring Data LDAP**.
2. Kiểm tra **số lượng/tên placeholder**, đặc biệt **:param** và **?0**.
3. Xác minh liệu tham số là **direct binding** hay **SpEL/property**; xử lý escaping tương ứng.
4. Kiểm tra **ContextSource base**, **@Entry base**, **@Query base**, searchScope và endpoint đang chạy.
5. Dùng **ldapsearch** với **cùng bind identity** của ứng dụng để cô lập filter/ACL.
6. Đối chiếu **objectClass**, tên attribute, matching rule và dữ liệu thật.
7. Kiểm tra **count/time limits, referral, read timeout, pool exhaustion** nếu kết quả lỗi/thiếu dữ liệu.
8. Thêm integration test xác nhận lỗi đã được sửa.

Không dùng cách “thử thêm quyền admin” hoặc tắt TLS validation để mặc định mọi LDAP query đều chạy. Những thay đổi đó che sai sót và tạo rủi ro bảo mật.

## 18. Hiệu năng, indexing và giới hạn khi vận hành

**@Query là filter search, không tự tạo LDAP index.** LDAP server phải đánh giá filter trên phạm vi DN/scope mà client yêu cầu; hiệu năng phụ thuộc cách server lưu dữ liệu, schema, index, cache và ACL.

### 18.1. Tránh quét cây quá rộng

Ví dụ:

~~~text
Search base: dc=lab,dc=example
Scope: SUBTREE
Filter: (cn=*an*)
~~~

Nếu directory rất lớn, filter substring có wildcard đầu có thể tiêu tốn nhiều tài nguyên, nhất là khi không có index substring phù hợp. Khi nghiệp vụ chỉ tìm người dùng, thu hẹp **base = ou=people**, thêm **objectClass=inetOrgPerson**, đặt count/time limits hợp lý và xem index trên attribute được dùng nhiều.

### 18.2. AND/OR có thể cần index khác nhau

Filter:

~~~text
(&(objectClass=inetOrgPerson)(|(uid=linh)(mail=linh@lab.example)))
~~~

có thể cần index thích hợp trên **uid**, **mail** và những điều kiện thường dùng, nhưng một cấu hình index cụ thể phải dựa trên khả năng và workload của **OpenLDAP hoặc Active Directory**. Không mặc định **tăng maxTotal pool** sẽ làm một search không có index nhanh hơn; đôi khi nó chỉ làm server chịu tải cao hơn.

### 18.3. Khi cần danh sách lớn

Các repository LDAP không cung cấp paging/sorting phổ quát như repository JPA. Nếu nghiệp vụ cần xuất **hàng chục nghìn entry**, cần lựa chọn cơ chế **paged results control** hoặc chiến lược đồng bộ chuyên dụng do server hỗ trợ, đồng thời kiểm soát:

- **ACL và thông tin cá nhân** được phép đọc.
- **LDAP paged results controls**/server-side limits thật sự hỗ trợ.
- **Search scope và filter** không lấy quá rộng.
- **Timeout** của toàn job và khả năng resume sau lỗi.
- **Chính sách đồng bộ replica**, tránh giả định dữ liệu toàn directory là snapshot transaction.
- **Tài nguyên JVM**: List tất cả entry cùng lúc có thể tốn bộ nhớ.

Đừng viết vòng lặp gọi **@Query(countLimit=100)** nhiều lần rồi giả định mỗi lần sẽ trả một “page tiếp theo”. Thiếu paging control/cookie, các lần search có thể chỉ trả cùng một tập kết quả hoặc có thứ tự khác nhau.

### 18.4. Pool và concurrent queries

Khi nhiều request cùng tìm kiếm, context được mượn qua **ContextSource/pool** của ứng dụng. Một filter quá chậm giữ connection lâu, tăng số **active** và **waiters**. Cần phối hợp tối ưu filter/index với cấu hình pool, **connect/read timeout**, request concurrency và giới hạn của LDAP server.

## 19. Bài tập thực hành

**Bài 1 — Đọc filter:** Phân tích từng dấu ngoặc trong:

~~~ldap
(&(objectClass=inetOrgPerson)(|(uid=linh)(mail=linh@lab.example)))
~~~

Giải thích đây là AND của những điều kiện nào và OR nằm ở đâu. Sau đó đổi filter để chỉ lấy entry có **mail**.

**Bài 2 — Named parameters:** Tạo repository method nhận **surname** và **description**, dùng **@Query** với hai tham số **@Param**. Test với **Nguyen/Engineer**, bảo đảm không vô tình tìm theo Java property **surname** thay vì LDAP attribute **sn**.

**Bài 3 — Positional parameters:** Viết lại Bài 2 bằng **?0**, **?1**. Cố ý đổi thứ tự hai tham số Java trong một bản test, quan sát vì sao positional binding khó bảo trì khi refactor.

**Bài 4 — Presence:** Khai báo filter tìm người có mail và một filter tìm người thiếu mail. Với fixture trên, so sánh Linh, An và Binh. Phân biệt attribute vắng mặt với entry bị ACL che.

**Bài 5 — Scope:** Tạo **ou=contractors** bên dưới **ou=people**, di chuyển một entry lab vào đó. So sánh **SearchScope.ONELEVEL** và **SUBTREE**; giải thích vì sao cùng một filter có thể cho số lượng kết quả khác nhau.

**Bài 6 — Injection:** Gọi một method **@Query("(uid=:uid)")** với input chứa **\***, **(**, **)** và **backslash**. Kiểm tra rằng query không bị biến thành filter logic khác. So sánh với một biểu thức nối chuỗi raw trong code test, nhưng **không triển khai phương án raw đó vào production**.

**Bài 7 — Wildcard:** Viết method tìm **cn** bắt đầu bằng một prefix. Quy định độ dài prefix tối thiểu, giữ wildcard trong filter template, kiểm tra dấu sao trong input không thể mở rộng phạm vi ngoài chính sách.

**Bài 8 — Membership:** Tạo groupOfNames trong lab, tìm các group chứa DN **uid=linh,...**. Thử truyền uid trần và giải thích sự khác nhau giữa member DN và uid.

**Bài 9 — Giới hạn:** Cấu hình **countLimit=2/timeLimit=3000**. Đặt dữ liệu nhiều hơn hai entry, xem hành vi của server, exception và lý do countLimit không tạo ra trang thứ hai.

**Bài 10 — LdapTemplate:** Chuyển một @Query cố định thành **LdapTemplate.search** dùng **LdapQueryBuilder**, chỉ yêu cầu **uid/cn** và trả DTO. Phân tích khi nào dùng API nào.

## 20. Câu hỏi ôn tập, tổng kết và tài liệu

### 20.1. Câu hỏi ôn tập

1. **@Query** của Spring Data LDAP khác **@Query** trong Spring Data JPA ở những điểm nào?
2. Vì sao LDAP filter và DN/search base là hai thành phần khác nhau của SearchRequest?
3. **:uid** và **?0** bind tham số theo cách nào? Tại sao **?0** là tham số đầu tiên?
4. Làm sao biểu diễn AND, OR, NOT và presence trong LDAP filter?
5. Vì sao **@Attribute(name="cn")** khiến filter nên dùng **cn** thay vì field Java **commonName**?
6. Khi người dùng nhập dấu sao trong tham số exact-match, encoder mặc định xử lý thế nào?
7. Tại sao **@LdapEncode(LikeEncoder)** phải đi cùng validation pattern?
8. Kết quả từ **SpEL/property placeholder** có được auto filter-escape không?
9. **base**, **searchScope**, **countLimit**, **timeLimit** của @Query kiểm soát những gì?
10. Vì sao **countLimit=10** không tạo ra một trang kết quả có thể phân trang?
11. Filter **(member=:dn)** cần uid trần hay DN đầy đủ của thành viên?
12. Khi cùng filter chạy được bằng ldapsearch nhưng @Query trả rỗng, nên kiểm tra những lớp nào?
13. Vì sao một repository query tìm thấy person không chứng minh caller đã được xác thực?
14. Khi nào nên dùng **LdapTemplate** thay vì ép mọi truy vấn vào @Query?

### 20.2. Tổng kết

**@Query** trong Spring Data LDAP cho phép đặt **LDAP search filter tĩnh** lên phương thức repository và bind **giá trị động** bằng **:namedParameter** hoặc **?0**. Filter dùng cú pháp LDAP như **(&...)**, **(|...)**, **(!...)**, equality, presence và substring — **không phải SQL/JPQL**. Annotation còn cung cấp **base**, **searchScope**, **countLimit** và **timeLimit**, nhưng những giá trị này không thay thế LDAP paging hoặc deadline tổng của ứng dụng.

**Đối với bảo mật**, hãy phân biệt **bound String params** được escape theo cú pháp filter với **SpEL/property placeholder values** không tự escape. Dấu sao do input cung cấp cần được xử lý đúng: exact match phải giữ nó là literal; wildcard search chỉ được bật khi có chủ ý, validation và giới hạn hợp lý. **@LdapEncode** có thể tùy chỉnh encoder trong những phiên bản hỗ trợ, nhưng không thay thế authorization hay ACL.

**Đối với vận hành**, luôn giới hạn search trong **DN/scope** đúng, kiểm tra **objectClass/schema**, thử filter bằng **ldapsearch** dưới đúng bind identity và xác minh qua **integration test**. Dùng derived method cho điều kiện đơn giản, **@Query** cho filter cố định phức tạp, và **LdapTemplate** khi cần thay đổi filter, attributes hoặc controls theo runtime.

### Tài liệu tham khảo

- [Spring Data LDAP — Query Methods](https://docs.spring.io/spring-data/ldap/reference/ldap/query-methods.html): **@Query**, named/positional binding, parameter encoding, **@LdapEncode**, SpEL và property placeholders.
- [Spring Data LDAP — @Query API](https://docs.spring.io/spring-data/ldap/reference/api/java/org/springframework/data/ldap/repository/Query.html): các phần tử **value/base/searchScope/countLimit/timeLimit**.
- [Spring Data LDAP — @LdapEncode API](https://docs.spring.io/spring-data/ldap/reference/api/java/org/springframework/data/ldap/repository/LdapEncode.html): tùy chọn encode từng tham số và các giới hạn.
- [Spring Data LDAP — LdapEncoder API](https://docs.spring.io/spring-data/ldap/reference/api/java/org/springframework/data/ldap/repository/LdapEncoder.html): encoder mặc định, LikeEncoder và NameEncoder.
- [Spring Data LDAP — Configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html): ODM, **LdapRepository**, **ldapTemplateRef** và giới hạn paging/sorting.
- [Spring LDAP — Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html): **LdapQueryBuilder**, filter criteria, search base/scope, hardcoded filter và escaping.
- [Spring LDAP — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html): **@Entry**, **@Attribute**, **@Id** và ánh xạ entry.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): phương thức search/lookup, resource management và mapper.
- [RFC 4515 — LDAP Search Filters](https://www.rfc-editor.org/rfc/rfc4515.html): cú pháp filter, substring/presence và escape octet.
- [RFC 4514 — LDAP Distinguished Names](https://www.rfc-editor.org/rfc/rfc4514.html): biểu diễn/escaping Distinguished Name.
- [RFC 4511 — LDAPv3 Protocol](https://www.rfc-editor.org/rfc/rfc4511.html): SearchRequest, SearchResult, giới hạn và result code.
- [RFC 4512 — LDAP Directory Information Models](https://www.rfc-editor.org/rfc/rfc4512.html): schema, objectClass, attributeTypes và DIT.
