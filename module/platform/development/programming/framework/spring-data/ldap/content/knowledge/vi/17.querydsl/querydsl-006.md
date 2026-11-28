# Giới hạn biểu thức và đối chiếu hỗ trợ theo phiên bản thư viện

Khi lập trình với **Querydsl**, bạn có thể quen với việc viết điều kiện có kiểu Java như `person.surname.eq("Nguyen")`, ghép bằng `and`/`or` và truyền biểu thức cho một repository. Tuy nhiên, **Spring Data LDAP** truy vấn một dịch vụ thư mục LDAP, không phải cơ sở dữ liệu SQL. Directory thực thi **LDAP filter** trong một **base DN**, **search scope** và dưới quyền **LDAP bind account**. Vì vậy, **một biểu thức Querydsl hợp lệ trong Java chưa chắc có thể thực thi trực tiếp trên Spring Data LDAP**.

Trong chương **Querydsl**, bài này tập trung vào chủ đề **“Giới hạn biểu thức và đối chiếu hỗ trợ theo phiên bản thư viện”**. Người học sẽ phân biệt khả năng biểu diễn của Querydsl Core, hỗ trợ thực tế của repository/translator trong Spring Data LDAP và khả năng của LDAP server; thiết lập quy trình xác minh theo phiên bản; lựa chọn fallback bằng `LdapTemplate`; đồng thời kiểm soát LDAP injection, phạm vi DN, schema, phân quyền, hiệu năng và kiểm thử.

**Nguyên tắc:** không lấy ví dụ `QuerydslPredicateExecutor` từ Spring Data JPA làm bằng chứng Spring Data LDAP có hỗ trợ tương đương. Chỉ tuyên bố một toán tử được hỗ trợ khi **API, implementation, phiên bản và integration test** cùng xác nhận.

## 1. Phân biệt ba tầng khả năng

Một yêu cầu tìm người có họ Nguyen **hoặc** tên An đi qua ba tầng khác nhau:

```text
Nghiệp vụ: surname = Nguyen OR givenName = An
                      │
                      ▼
Querydsl Predicate / BooleanExpression
   (biểu diễn cây điều kiện trong Java)
                      │
                      ▼
Tầng Querydsl-to-LDAP integration nếu có
   (dịch property, operator, escaping)
                      │
                      ▼
LDAP search: base + scope + filter + attributes
                      │
                      ▼
Directory server: schema + ACL + matching rule
                      │
                      ▼
Java DTO / ODM entity
```

- **Tầng 1 – Querydsl Core:** cho phép tạo đối tượng biểu diễn điều kiện kiểu Java, ví dụ equality, conjunction hoặc disjunction. Nó không tự tạo LDAP request.
- **Tầng 2 – Spring Data LDAP hoặc adapter:** cần có **translator/executor thực sự** nhận predicate và tạo LDAP filter. Sự xuất hiện của `com.querydsl.core.types.Predicate` trong classpath không chứng minh đã có translator LDAP.
- **Tầng 3 – LDAP server:** cần hỗ trợ matching rule cho attribute, search scope, result controls và quyền ACL; không phải toán tử nào cũng có ngữ nghĩa giống Java/SQL.

Mỗi tầng có **phiên bản và contract riêng**. Một predicate compile được chưa xác minh hai tầng còn lại.

### Mô hình directory trong bài

```text
dc=example,dc=org             ← naming context
├── ou=people
│   ├── uid=u1001
│   ├── uid=u1002
│   └── uid=u1003
├── ou=groups
│   └── cn=developers
└── ou=service-accounts
    └── cn=svc-reader
```

LDIF cho một người:

```ldif
dn: uid=u1001,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: u1001
cn: An Nguyen
sn: Nguyen
givenName: An
mail: an@example.org
```

Khi dùng Spring Data LDAP, thuộc tính Java `surname` có thể ánh xạ sang LDAP attribute `sn` qua ODM. DN định vị entry, còn `objectClass`/schema quy định cấu trúc và matching rule. Tầng Querydsl phải được kiểm chứng có đọc đúng metadata này hay không.

## 2. Biểu thức Querydsl và LDAP filter là hai dạng khác nhau

Đoạn sau **chỉ minh họa cú pháp Querydsl AST**, giả định project đã cấu hình Q-type hợp lệ. Nó **không** phải bằng chứng về LDAP integration:

```java
import com.querydsl.core.types.dsl.BooleanExpression;

// QDirectoryPerson là Q-type phải được project sinh hoặc khai báo.
QDirectoryPerson person = QDirectoryPerson.directoryPerson;

BooleanExpression desired =
        person.surname.eq("Nguyen")
              .or(person.givenName.eq("An"));
```

Ý nghĩa tương ứng trong cú pháp LDAP là:

```ldap
(|(sn=Nguyen)(givenName=An))
```

Để dịch đúng, translator cần biết:

1. `surname` trong Java phải thành **`sn`** khi hỏi LDAP.
2. `or` phải thành nhóm `(|(...)(...))`, giữ đúng ngoặc lồng nhau.
3. Giá trị phải được **escape theo RFC 4515** (không nối chuỗi thô).
4. Search phải giữ đúng **base DN, scope**, attribute allowlist và account được phép.
5. Kết quả LDAP phải ánh xạ về DTO/entity theo object class và schema.
6. Một toán tử không hỗ trợ phải gây lỗi rõ ràng, **không bị bỏ qua**.

Việc Querydsl Core có method `eq` hoặc `or` không chứng minh LDAP repository có con đường thực thi cho chúng.

## 3. Sai lầm phổ biến khi suy diễn tính năng

| Khẳng định chưa kiểm chứng | Vấn đề | Cách xử lý |
|---|---|---|
| “Spring Data hỗ trợ Querydsl, chắc LDAP cũng vậy” | Các Spring Data store modules có khả năng khác nhau | Kiểm tra riêng Spring Data LDAP theo bản đang dùng |
| “Thêm `querydsl-core` là chạy được” | Core cung cấp biểu thức, không tự cung cấp LDAP translator | Xác nhận adapter/repository executor |
| “Có `QuerydslPredicateExecutor` trên classpath” | Interface chung không bảo đảm LDAP factory triển khai | Kiểm tra implementation và khởi tạo bean |
| “Sinh được Q-type là đã tích hợp” | Annotation processing khác query execution | Chạy integration test với LDAP search thật |
| “Toán tử dùng được trong JPA thì dùng được trong LDAP” | LDAP không phải SQL, không có JOIN/regex tổng quát | Lập capability matrix riêng |
| “Mock trả kết quả đúng là đủ” | Mock không kiểm tra filter, scope, schema hoặc ACL | Test trên directory tương thích |

**Đặc biệt:** `QuerydslPredicateExecutor` tồn tại trong hệ sinh thái Spring Data không đồng nghĩa mọi `LdapRepository` đều có implementation cho `Predicate`. Không nên thêm interface vào repository chỉ để code compile.

## 4. Đối chiếu chính xác theo phiên bản thư viện

Trước khi viết một phép lọc dựa trên Querydsl, lập bảng **phiên bản thực tế đã resolve**:

| Thành phần | Thông tin phải có | Điều cần xác minh |
|---|---|---|
| JDK | Major version | Runtime, annotation processing, TLS |
| Spring Boot | Version + BOM | Bộ dependency do Boot quản lý |
| Spring Data LDAP | Artifact/version thực tế | API repository và hỗ trợ predicate |
| Spring LDAP Core | Artifact/version thực tế | `LdapTemplate`, `LdapQueryBuilder`, filter classes |
| Spring Data Commons | Version được kéo vào | Các repository interfaces chung |
| Querydsl Core | Group/artifact/version | `Predicate` và AST operators |
| Querydsl APT | Processor/config thực tế | Q-types cho model được sinh ra |
| LDAP translator | Class/adapter và version **cụ thể** | Có dịch predicate tới LDAP không? |
| LDAP server | Product, version, schema | Matching rule, indexes, ACL |
| LDAP controls | RootDSE `supportedControl` | Paging, sort, server-specific feature |

Với mỗi project phải điền **giá trị đã quan sát**, không đoán từ tên module. Querydsl có thể tồn tại dưới group/fork hoặc biến thể khác nhau; processor và runtime phải phù hợp.

### Lệnh tham khảo cho người học

Các lệnh sau là **ví dụ hướng dẫn**, không phải những lệnh đã chạy để xác nhận project này:

```bash
# Gradle
./gradlew dependencyInsight \
  --dependency spring-data-ldap \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency querydsl-core \
  --configuration compileClasspath
```

```bash
# Maven
mvn dependency:tree -Dincludes=org.springframework.data:spring-data-ldap
mvn dependency:tree -Dincludes=com.querydsl:querydsl-core
```

Nếu project dùng group ID khác, phải điều chỉnh lệnh theo khai báo thực tế. Kiểm tra thêm annotation processor path; việc sinh Q-type không tự chứng minh đã tích hợp query execution.

## 5. Quy trình kiểm chứng hỗ trợ Querydsl trên Spring Data LDAP

Để tuyên bố “toán tử X đã hoạt động”, cần bằng chứng ở cả **compile time, runtime và directory**:

1. **Tra cứu tài liệu đúng phiên bản:** Spring Data LDAP reference, Javadoc, Spring LDAP API và Querydsl Core, không chỉ Spring Data JPA.
2. **Xác định executor:** module/adapter nào thực sự nhận Querydsl `Predicate`? Có API công khai và implementation LDAP không?
3. **Xác minh repository factory:** khởi tạo Spring context, kiểm tra implementation method đã có, không chỉ compile interface.
4. **Chạy một predicate tối thiểu:** equality trên một property có mapping khác tên LDAP attribute.
5. **Đối chiếu LDAP request:** kiểm tra base, scope, filter, requested attributes và identity của connection.
6. **Thử operator tổ hợp:** AND, OR, NOT, null/presence, substring, dữ liệu đa trị và ký tự cần escape.
7. **Thử giới hạn:** pagination, sorting, size/time limit, referral, permission denied, unsupported operator.
8. **Ghi kết quả theo tổ hợp version:** gồm thư viện, server, schema, ngày test và kết quả.

Dùng các trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| **SUPPORTED** | Có API/implementation và integration test thực thi thành công |
| **UNSUPPORTED** | Có bằng chứng module/translator không hỗ trợ |
| **UNKNOWN** | Chưa đủ bằng chứng; không được mặc định dùng |
| **FALLBACK** | Có hướng thực thi khác được kiểm chứng qua `LdapTemplate` |

**Không chuyển UNKNOWN thành SUPPORTED** chỉ vì một `BooleanExpression` được tạo thành công.

## 6. Ma trận giới hạn biểu thức LDAP cần thử

Bảng này là **ma trận thẩm định**, không phải tuyên bố mọi toán tử đều được Spring Data LDAP/Querydsl hỗ trợ:

| Ý định | LDAP filter hoặc cơ chế tương ứng | Ràng buộc cần kiểm chứng |
|---|---|---|
| Equality | `(sn=Nguyen)` | Attribute mapping, equality rule |
| AND | `(&(sn=Nguyen)(givenName=An))` | Translator giữ đủ nhánh |
| OR | `(|(sn=Nguyen)(givenName=An))` | Nhóm ngoặc và thứ tự ưu tiên |
| NOT | `(!(sn=Nguyen))` | Phủ định đúng một nhóm |
| Có thuộc tính | `(mail=*)` | Presence không phải Java not-null |
| Khác giá trị | `(!(mail=blocked@example.org))` | Thêm presence nếu bắt buộc có mail |
| Prefix/substring | LDAP substring filter | Wildcard, escaping, matching rule/index |
| Greater-or-equal | `(modifyTimestamp>=...)` | ORDERING rule + quyền trên attribute |
| IN | OR của nhiều equality | Giới hạn số nhánh, performance |
| Multi-valued member | `(member=DN)` | DN syntax/matching rule, nhiều giá trị |
| Null/absence | `(!(mail=*))` | Không đồng nhất với semantics SQL NULL |
| JOIN hoặc subquery | Không có SQL JOIN chung trong LDAP search | Cần truy vấn bổ sung, giới hạn quyền và tải |
| Regex tổng quát | Không có regex filter chuẩn di động | Chỉ dùng extension cụ thể đã xác minh |
| Sorting | Server-side sort control khi hỗ trợ | RootDSE control, consistency |
| Paging | Paged results control khi hỗ trợ | Cookie, limits, behavior khi thay đổi dữ liệu |
| Aggregation | Không có SQL GROUP BY chung | Xử lý ở tầng khác với quota dữ liệu |

Nếu một Querydsl operator dịch được trên database khác, phải **test lại độc lập** trên LDAP. Ví dụ `containsIgnoreCase` có thể có ý nghĩa khác do LDAP matching rule, chứ không dựa vào phép lowercase Java.

## 7. Phép AND/OR/NOT và nhóm ngoặc phải được bảo toàn

Giả sử nghiệp vụ muốn **(họ Nguyen hoặc tên An) và có email và email không bị chặn**.

```text
A = sn equals Nguyen
B = givenName equals An
C = mail equals blocked@example.org

(A OR B) AND PRESENT(mail) AND NOT(C)
```

LDAP filter đúng:

```ldap
(&(|(sn=Nguyen)(givenName=An))(mail=*)(!(mail=blocked@example.org)))
```

Filter không tương đương:

```ldap
(|(sn=Nguyen)(&(givenName=An)(mail=*)(!(mail=blocked@example.org))))
```

Filter thứ hai tương ứng **A OR (B AND PRESENT(mail) AND NOT C)**. Nó có thể trả entry có họ Nguyen nhưng mail bị chặn hoặc không tồn tại.

| UID | `sn` | `givenName` | `mail` | Có khớp yêu cầu gốc? |
|---|---|---|---|---|
| u1001 | Nguyen | An | an@example.org | Có |
| u1002 | Nguyen | Binh | blocked@example.org | **Không** |
| u1003 | Tran | An | an.tran@example.org | Có |
| u1004 | Nguyen | Chi | *không có* | **Không** |
| u1005 | Le | Binh | le@example.org | Không |

Một test chỉ có u1001 không phân biệt được hai filter trên. Khi kiểm thử translator, **tạo dữ liệu mà hai cách đặt ngoặc phải trả kết quả khác nhau**.

## 8. Phủ định, NULL và thuộc tính đa trị

LDAP filter `(!(mail=blocked@example.org))` là **phủ định phép equality**, không hẳn giống điều kiện `mail != ...` trong SQL hoặc Java. Nếu `mail` vắng mặt, entry vẫn có thể khớp phủ định theo ngữ nghĩa LDAP thông dụng.

Nếu nghiệp vụ yêu cầu có email, cần:

```ldap
(&(mail=*)(!(mail=blocked@example.org)))
```

Lưu ý:

- `mail` có thể là thuộc tính tùy chọn theo schema, không phải mọi entry đều có.
- Directory có thể hạn chế đọc/search attribute bằng ACL, ảnh hưởng kết quả.
- `isNotNull` của Querydsl (nếu operator này được hỗ trợ trong adapter) chưa chắc tự dịch thành `(mail=*)`: phải xác minh.
- Với thuộc tính đa trị như `member`, filter `(member=DN)` hỏi có **giá trị nào** khớp DN, không phải join bảng quan hệ.
- Một biểu thức phủ định trên `member` cần kiểm thử rõ semantics, đặc biệt khi group không có member hoặc attribute bị ẩn.

Không tự chuyển bộ lọc `!=` sang một chuỗi LDAP tùy ý; dùng filter builder và test các ca attribute thiếu.

## 9. Schema và matching rule giới hạn biểu thức

LDAP server thực thi equality, substring và ordering theo **attribute syntax và matching rule**, không phải toán tử Java. Một vài tình huống:

| Attribute | Điều cần kiểm tra |
|---|---|
| `uid`, `sn`, `cn` | Equality rule, case sensitivity, Unicode normalization |
| `mail` | Có/thiếu giá trị, matching rule, ACL |
| `modifyTimestamp` | Operational attribute, GeneralizedTime ordering, indexing |
| `member` | DN syntax, multivalue, DN equality |
| `objectClass` | Inheritance và schema |
| `objectGUID` (AD) | Kiểu binary, encoding; không ép `String` tùy ý |

Ví dụ `(modifyTimestamp>=20261126100000Z)` chỉ có ý nghĩa nếu server hỗ trợ **ordering matching rule** phù hợp và service account được phép tìm. Querydsl có operator greater-or-equal **không tạo ra matching rule còn thiếu**.

Các matching rule đặc thù hoặc LDAP controls do server cung cấp cũng **không tự xuất hiện** trong Querydsl translator. Nếu cần, ứng dụng phải có adapter được kiểm thử và ghi rõ tính phụ thuộc sản phẩm.

## 10. Fallback kiểm chứng được bằng Spring LDAP filter builder

Khi Querydsl integration chưa được chứng minh cho phiên bản đang dùng, có thể truy vấn bằng `LdapTemplate` và filter builder của Spring LDAP. Ví dụ xây **(sn = Nguyen hoặc givenName = An) và có mail, mail khác giá trị chặn**, tìm đúng các entry con trực tiếp của `ou=people`.

```java
import java.util.List;
import javax.naming.NamingException;
import javax.naming.directory.Attribute;
import javax.naming.directory.Attributes;

import org.springframework.ldap.core.AttributesMapper;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.ldap.filter.AndFilter;
import org.springframework.ldap.filter.EqualsFilter;
import org.springframework.ldap.filter.NotFilter;
import org.springframework.ldap.filter.OrFilter;
import org.springframework.ldap.filter.PresentFilter;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.SearchScope;

import static org.springframework.ldap.query.LdapQueryBuilder.query;

public final class PeopleSearch {
    private final LdapTemplate ldapTemplate;

    public record PersonHit(String uid, String cn, String mail) {}

    public PeopleSearch(LdapTemplate readOnlyTemplate) {
        this.ldapTemplate = readOnlyTemplate;
    }

    public List<PersonHit> search(
            String surname, String givenName, String excludedMail) {

        if (surname == null || surname.isBlank()
                || givenName == null || givenName.isBlank()
                || excludedMail == null || excludedMail.isBlank()) {
            throw new IllegalArgumentException("Required search values missing");
        }

        OrFilter names = new OrFilter();
        names.or(new EqualsFilter("sn", surname));
        names.or(new EqualsFilter("givenName", givenName));

        AndFilter all = new AndFilter();
        all.and(new EqualsFilter("objectClass", "inetOrgPerson"));
        all.and(names);
        all.and(new PresentFilter("mail"));
        all.and(new NotFilter(
                new EqualsFilter("mail", excludedMail)));

        LdapQuery request = query()
                .base("ou=people")
                .searchScope(SearchScope.ONELEVEL)
                .timeLimit(2000)
                .countLimit(101)
                .attributes("uid", "cn", "mail")
                .filter(all);

        AttributesMapper<PersonHit> mapper = attrs ->
                new PersonHit(
                        text(attrs, "uid"),
                        text(attrs, "cn"),
                        text(attrs, "mail"));

        return ldapTemplate.search(request, mapper);
    }

    private static String text(Attributes attrs, String field)
            throws NamingException {
        Attribute a = attrs.get(field);
        return a == null ? null : (String) a.get();
    }
}
```

**Giải thích ranh giới:**

1. Tên LDAP attribute `sn`, `givenName`, `mail` cố định trong code.
2. Giá trị đến từ người gọi được đưa vào `EqualsFilter`, không chèn raw LDAP filter.
3. `OrFilter` nằm trong `AndFilter` nên cấu trúc ngoặc rõ ràng.
4. `PresentFilter` diễn đạt chính xác yêu cầu email phải tồn tại.
5. Context base giả định `dc=example,dc=org`, search base `ou=people` là tương đối.
6. `ONELEVEL` chỉ tìm entry ngay dưới OU (theo cấu trúc bài tập).
7. Chỉ yêu cầu ba thuộc tính và một kết quả DTO nhỏ; **không dùng tài khoản admin**.
8. `countLimit`/`timeLimit` là yêu cầu giới hạn gửi đến LDAP; **không có nghĩa mọi server trả đủ rồi kết thúc êm**, phải xử lý lỗi giới hạn/cắt cụt.

Ví dụ là **Spring LDAP filter builder**, không phải Querydsl integration. Đó là chủ ý: chọn cơ chế đã kiểm chứng thay vì coi một tầng dịch chưa rõ là an toàn.

## 11. Repository và ODM độc lập với khả năng Querydsl

Một entity Spring LDAP ODM có thể như sau:

```java
import javax.naming.Name;
import org.springframework.ldap.odm.annotations.Attribute;
import org.springframework.ldap.odm.annotations.Entry;
import org.springframework.ldap.odm.annotations.Id;

@Entry(
    base = "ou=people",
    objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"}
)
public class DirectoryPerson {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "givenName")
    private String givenName;

    public DirectoryPerson() {}
    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }
    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }
    public String getSurname() { return surname; }
    public void setSurname(String surname) { this.surname = surname; }
    public String getGivenName() { return givenName; }
    public void setGivenName(String givenName) {
        this.givenName = givenName;
    }
}
```

Repository có thể khai báo query cố định:

```java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;

public interface DirectoryPersonRepository
        extends LdapRepository<DirectoryPerson> {

    List<DirectoryPerson> findBySurnameAndGivenName(
            String surname, String givenName);
}
```

**Điểm cần tách bạch:**

- `@Entry`, `@Id Name` và `@Attribute` thuộc cơ chế ODM.
- `LdapRepository` là abstraction repository của Spring Data LDAP.
- Query method `findBySurnameAndGivenName` **không chứng minh** Querydsl có translator/executor cho LDAP.
- Nếu muốn thêm `QuerydslPredicateExecutor`, phải xác minh **repository factory LDAP phiên bản đang cài** thực sự hỗ trợ contract đó.
- Các thao tác `save`, `delete`, `LdapTemplate.modifyAttributes` vẫn chịu ACL, schema và DN; khả năng predicate không liên quan đến cấp quyền ghi.

Không trộn lẫn **Q-type của Querydsl** với **LDAP ODM metadata**: hai hệ thống metadata có thể cùng mô tả Java model nhưng không tự động thay thế nhau.

## 12. Thiết kế capability contract để tránh fallback nguy hiểm

Nếu sản phẩm cần DSL truy vấn nâng cao, thay vì nhận raw `Predicate` tùy ý, hãy định nghĩa một **SearchSpec** có field/operator được duyệt:

```java
import java.util.List;

public record PersonSearchSpec(
        String surname,
        List<String> employeeTypes,
        boolean requireMail,
        String excludedMail
) {}
```

Policy:

| Field | Operator hợp lệ | LDAP attribute |
|---|---|---|
| `surname` | EQUALS | `sn` |
| `employeeTypes` | OR equality, tối đa vài giá trị allowlist | `employeeType` |
| `requireMail` | PRESENT | `mail` |
| `excludedMail` | NOT equality **kèm presence** | `mail` |
| Object class | Cố định, không nhận từ client | `inetOrgPerson` |
| Base/scope | Cố định theo cấu hình | Không nhận raw DN từ client |

Khi toán tử không hỗ trợ:

- **Fail fast** với lỗi rõ ràng; không loại bỏ nhánh predicate mà vẫn trả kết quả.
- Không âm thầm tải toàn bộ directory rồi lọc trong RAM.
- Không chuyển `ONELEVEL` thành `SUBTREE` chỉ để “tìm đủ”.
- Không tự thay reader account bằng tài khoản có quyền cao hơn.
- Không cho raw attribute name, DN hoặc LDAP filter đi qua request bên ngoài.

Một dự án có thể tự viết adapter có contract giới hạn:

```java
public interface AllowedPredicateTranslator<P> {
    // Predicate nào không thuộc capability set phải bị từ chối.
    org.springframework.ldap.filter.Filter translate(P predicate);
}
```

Interface này là **minh họa do ứng dụng tự thiết kế**, **không phải API có sẵn của Spring Data LDAP**. Nếu dùng Querydsl `Predicate` làm P, adapter phải parse đúng AST và mapping field/operator; không dùng `predicate.toString()` để xây filter.

## 13. Version compatibility: cách ra quyết định khi nâng cấp

Khi nâng Spring Boot, Spring Data LDAP hoặc Querydsl, cần chạy lại capability suite thay vì chỉ sửa số version:

| Mục kiểm tra | Trước nâng cấp | Sau nâng cấp |
|---|---|---|
| Resolution | Bộ artifact/version đã chạy | Bộ artifact/version mới |
| Q-type generation | Annotation processor hợp lệ | Q-types mới sinh đúng? |
| Repository startup | Bean/repository khởi tạo | Có lỗi method/implementation không? |
| Equality/AND/OR/NOT | Bộ kết quả đã được xác minh | Cùng semantics và filter? |
| Property mapping | `surname` → `sn` | Vẫn đúng metadata? |
| Escape | Input chứa `*`, `(`, `)`, backslash | Vẫn không làm thay đổi AST filter? |
| Null/multivalue | Có test attribute thiếu/đa trị | Vẫn đúng hành vi? |
| Base/scope/limit | Giá trị được cố định | Không mở rộng phạm vi? |
| TLS và bind | Truststore, principal | Không làm giảm bảo mật/đổi credential? |
| Performance | p95/ops, quota server | Không có regression ngoài ngưỡng? |

Một thay đổi Querydsl processor có thể làm Q-type không sinh được; thay đổi repository factory có thể khiến method chưa được implement. **Compiler pass khác integration test pass.**

### Nhật ký khả năng nên có

Mỗi phép thử ghi: tên operator, version Spring Data LDAP/Spring LDAP/Querydsl, server product/version, DN base/scope, filter mong đợi, trạng thái SUPPORTED/UNSUPPORTED/UNKNOWN, bằng chứng test và ngày kiểm chứng.

Nhờ vậy team không lặp lại sai lầm “có thể làm trong Querydsl Core” thành “đã hoạt động trên LDAP production”.

## 14. Hiệu năng: dịch được chưa chắc nên dùng

Ngay cả khi biểu thức được dịch chính xác sang LDAP filter, nó có thể quá tốn tài nguyên:

| Loại query | Rủi ro | Hướng kiểm soát |
|---|---|---|
| OR hàng trăm điều kiện | Filter dài, tăng tải CPU/network | Giới hạn nhánh/độ sâu, batch có kiểm soát |
| NOT trên toàn OU | Trả gần hết entry | Bắt buộc điều kiện dương chọn lọc |
| Substring bắt đầu wildcard | Index khó sử dụng | Đánh giá index/semantics và UX |
| Query member theo nhiều group | N+1 LDAP lookup | Đo số operations, giới hạn và cache hợp lý |
| Không có server sort control | Thứ tự không ổn định | Kiểm tra `supportedControl`/đổi yêu cầu |
| Paged results thiếu kiểm chứng | Thiếu entry hoặc kết quả không nhất quán | Kiểm tra paging cookie, limits, retry |
| Client-side filtering | Đọc nhiều dữ liệu hơn nhu cầu | Không làm fallback âm thầm |

Đo p50/p95/p99 latency, số LDAP search thực tế, số entry/attribute trả về, lỗi size/time limit, pool wait, TLS bind và mức độ lỗi operator unsupported. **DSL type-safe không đồng nghĩa query hiệu quả.**

## 15. Bảo mật và phòng chống LDAP injection

Một số ký tự có ý nghĩa đặc biệt trong LDAP filter gồm `*`, `(`, `)`, backslash và NUL. Ví dụ input:

```text
Nguyen*)(uid=*)
```

Không làm:

```java
// Sai: đầu vào có thể thay đổi cú pháp filter.
String rawFilter = "(sn=" + userInput + ")";
```

Dùng builder:

```java
import org.springframework.ldap.filter.EqualsFilter;

String encoded =
        new EqualsFilter("sn", userInput).encode();
```

Ví dụ filter tương đương sau khi escape:

```ldap
(sn=Nguyen\2a\29\28uid=\2a\29)
```

Ngay cả khi một Querydsl translator đã được chứng minh hỗ trợ equality, vẫn phải kiểm thử nó **escape giá trị đúng** với dấu sao, ngoặc, backslash, Unicode và input bất thường.

Những lớp bảo vệ độc lập:

1. **LDAPS/StartTLS** và xác minh chứng chỉ server, không fallback SIMPLE bind cleartext.
2. **Bind account chỉ đọc** với ACL chỉ tới entry/attribute được duyệt.
3. **Authorization của API** trước khi trả dữ liệu từ directory.
4. **Base/scope cố định** theo identity/tenant đáng tin, không cho raw DN từ client.
5. **Filter và DN escaping đúng loại:** `EqualsFilter` cho filter, `LdapNameBuilder` cho RDN.
6. **Attribute allowlist**, requested attributes tối thiểu, log không chứa secret và dữ liệu cá nhân không cần thiết.
7. **Fail closed** khi predicate không được hỗ trợ; tuyệt đối không lặng lẽ bỏ điều kiện lọc.

## 16. Test matrix: bằng chứng theo từng phép toán

| Test | Thiết lập | Kỳ vọng |
|---|---|---|
| Repository startup | Khai báo integration Querydsl nếu có | Method thực sự implement; không lỗi bean |
| Equality | `sn=Nguyen` | Khớp entry phù hợp |
| Java property mapping | `surname` khác LDAP `sn` | Translator dùng đúng `sn` |
| AND/OR | Bộ entry có cả hai/chỉ một/không điều kiện | Đúng tập UID |
| Group parentheses | `(A OR B) AND C` vs `A OR (B AND C)` | Phân biệt được |
| NOT + absent attribute | Có entry thiếu `mail` | Đúng semantics presence và phủ định |
| Escaping | Input `Nguyen*)(uid=*)` | Không mở rộng filter |
| Substring | Input dấu `*` và ký tự Unicode | Chỉ pass nếu translator/server hỗ trợ |
| Ordering | `modifyTimestamp>=...` | Chỉ pass khi schema/matching rule hỗ trợ |
| Multivalue | Group có nhiều `member` | Không mất/nhầm giá trị |
| Scope | Entry dưới OU khác hoặc OU con | Không vượt phạm vi |
| Unsupported predicate | Regex/join nếu chưa hỗ trợ | Báo lỗi, không bỏ nhánh |
| Size/time limit | Nhiều kết quả hơn limit | Không coi danh sách cắt là đầy đủ |
| Paging/sort | Server control nếu dùng | Hoạt động đúng, không suy tự động |
| ACL/TLS | Bind thiếu quyền/chứng chỉ sai | Fail closed; checkpoint/query không thay đổi |
| Upgrade | Bộ version trước/sau | Kết quả/filter/latency tương đương |

**Unit test escape cho fallback:**

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.springframework.ldap.filter.EqualsFilter;

class EscapedLdapFilterTest {
    @Test
    void specialCharsRemainLiteralValues() {
        String encoded =
                new EqualsFilter("sn", "Nguyen*)(uid=*)").encode();

        assertTrue(encoded.contains("\\2a"));
        assertTrue(encoded.contains("\\29"));
        assertTrue(encoded.contains("\\28"));
        assertFalse(encoded.contains(")(uid=*)"));
    }
}
```

Test unit này không chứng minh tích hợp Querydsl, schema hay ACL. Phải có **integration test với LDAP test server** dùng cùng base/scope và loại tài khoản bind như dự kiến. Khi so kết quả, so **tập UID/DN**, không dựa vào thứ tự entry nếu không có sorting control.

## 17. Tình huống xử lý unsupported operator

Một developer đề xuất `person.commonName.containsIgnoreCase(...)`.

Trình tự đánh giá:

1. **Xác định yêu cầu:** equality, prefix hay substring? Case-insensitive theo quy tắc nào?
2. **Kiểm tra Querydsl AST:** operator có được biểu diễn trong model/processor đang dùng?
3. **Kiểm tra LDAP translator:** adapter thực sự hỗ trợ node/operator đó chứ?
4. **Kiểm tra server:** schema có substring matching rule, index và ACL tương ứng?
5. **Giới hạn kết quả:** base/ONELEVEL/SUBTREE, max count, timeout, paging.
6. **Kiểm thử injection:** input có `*` phải được coi là dữ liệu literal khi yêu cầu.
7. **Quyết định:** supported và test pass → dùng; còn unknown/unsupported → chuyển sang `LdapTemplate` với logic được hỗ trợ hoặc trả lỗi nghiệp vụ.

Không lấy toàn bộ `ou=people` về bộ nhớ chỉ để mô phỏng regex hoặc substring nếu chưa được phép. Một thông báo “filter chưa được hỗ trợ” rõ ràng sẽ an toàn hơn một truy vấn rộng bị chạy âm thầm.

## 18. Bài tập thực hành và câu hỏi tự kiểm

Một đội có Spring Boot + Spring Data LDAP + Querydsl trong build nhưng **chưa xác định được executor** chuyển Querydsl predicate sang LDAP. Directory có các entry trong `ou=people,dc=example,dc=org`. API cần tìm **(sn=Nguyen OR givenName=An) AND có mail AND NOT mail=blocked@example.org**.

Trả lời các câu hỏi:

1. Vì sao `BooleanExpression` compile không bảo đảm Spring Data LDAP đã hỗ trợ Querydsl?
2. Viết filter LDAP có đủ ngoặc cho biểu thức yêu cầu.
3. Dùng những entry nào để test khác biệt giữa `(A OR B) AND C` và `A OR (B AND C)`?
4. Vì sao filter `(!(mail=blocked@example.org))` chưa đủ nếu buộc có email?
5. Những artifact/version nào phải xác minh trước khi chọn `QuerydslPredicateExecutor`?
6. Nếu không có translator, giải pháp `LdapTemplate` nào diễn đạt AND/OR/NOT rõ ràng?
7. Vì sao `regex`, `JOIN` hoặc `containsIgnoreCase` không thể suy từ Querydsl Core ra hỗ trợ trên LDAP?
8. Kiểm thử escape `Nguyen*)(uid=*)` cần chứng minh điều gì?
9. Nếu LDAP server trả size-limit error hoặc thiếu quyền, hệ thống có được coi đó là “không có dữ liệu” không?
10. Sau nâng cấp version, cần đối chiếu những kết quả và metric nào?

**Đáp án định hướng:** cú pháp đúng là `(&(|(sn=Nguyen)(givenName=An))(mail=*)(!(mail=blocked@example.org)))`. Chỉ xác nhận Querydsl support khi có executor thật và test ở LDAP server. Nếu không, dùng `LdapTemplate` + `AndFilter`/`OrFilter`/`NotFilter`/`PresentFilter`/`EqualsFilter`; cố định base/scope và ACL. Unsupported operator phải bị từ chối, không tự bỏ điều kiện.

## 19. Checklist và tổng kết

Trước khi bàn giao khả năng Querydsl cho một ứng dụng Spring Data LDAP:

- [ ] Đã phân biệt **Querydsl AST**, **Spring Data LDAP repository/adapter** và **directory server**.
- [ ] Đã xác minh version thực của Spring Boot, Spring Data LDAP, Spring LDAP Core, Commons, Querydsl Core/APT.
- [ ] Có bằng chứng LDAP repository factory/executor hỗ trợ predicate nếu sử dụng.
- [ ] Có capability matrix cho từng operator và trạng thái SUPPORTED/UNSUPPORTED/UNKNOWN.
- [ ] Có test property→attribute, filter escaping, AND/OR/NOT, null/presence và multi-valued.
- [ ] Kiểm tra base DN, scope, objectClass/schema, matching rules, ACL và TLS.
- [ ] Unsupported predicate **fail fast**, không silent drop, không full scan rồi filter client-side.
- [ ] Có fallback qua `LdapTemplate`/filter builder với ngữ nghĩa rõ ràng.
- [ ] Có kiểm thử paging/sort/size limit và hiệu năng nếu triển khai.
- [ ] Có integration test trên directory/test server tương thích và regression test sau nâng cấp.

### Nguồn kỹ thuật cần đối chiếu theo version

- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/).
- [Spring LDAP Reference](https://docs.spring.io/spring-ldap/reference/).
- [Spring Data Commons Reference](https://docs.spring.io/spring-data/commons/reference/).
- [Querydsl](https://querydsl.com/).
- [RFC 4515 – LDAP String Representation of Search Filters](https://www.rfc-editor.org/rfc/rfc4515).
- [RFC 4511 – LDAP Protocol](https://www.rfc-editor.org/rfc/rfc4511).

**Kết luận:** giới hạn quan trọng của Querydsl trong Spring Data LDAP là **khả năng chuyển đúng biểu thức Java thành LDAP filter ở tổ hợp phiên bản đang dùng**, không chỉ khả năng viết operator trong Querydsl Core. Hãy xác minh translator, repository integration, schema/matching rule và phạm vi quyền trên directory. Khi chưa có bằng chứng, dùng `LdapTemplate` và filter builder an toàn, giữ nguyên base/scope/ACL và kiểm thử trực tiếp với server.
