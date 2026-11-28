# Tích hợp khả năng thực thi predicate vào Repository

Trong **SPRING_DATA_LDAP**, ứng dụng Java dùng Spring Data LDAP để truy cập dịch vụ thư mục LDAP theo mô hình repository, ánh xạ entry có DN (*Distinguished Name*), `objectClass` và các thuộc tính LDAP sang đối tượng Java. Với truy vấn đơn giản, phương thức như `findByUid(...)` thường đã đủ. Nhưng khi màn hình tìm kiếm có nhiều điều kiện tùy chọn — chẳng hạn tên đăng nhập, họ, email và nhóm — số lượng phương thức repository có thể tăng nhanh.

**Querydsl** cho phép biểu diễn điều kiện dưới dạng **predicate có kiểm tra kiểu tại thời điểm biên dịch**. Spring Data LDAP hỗ trợ tích hợp Querydsl bằng `QuerydslPredicateExecutor<T>`: repository nhận đối tượng `com.querydsl.core.types.Predicate` thay vì bắt ứng dụng phải ghép chuỗi LDAP filter thủ công.

Mục tiêu bài học:

- Biết điều kiện và giới hạn để bật Querydsl cho **Spring Data LDAP**, không nhầm với Querydsl JPA/SQL.
- Tạo `QPersonEntry` bằng `LdapAnnotationProcessor` từ entity ODM có `@Entry`.
- Cho repository kế thừa cả `LdapRepository<PersonEntry>` và `QuerydslPredicateExecutor<PersonEntry>`.
- Thực thi `findAll(predicate)`, `findOne(predicate)`, `count(predicate)` và `exists(predicate)`.
- Xây predicate động an toàn, hiểu phạm vi DN/filter/ACL, tránh giả định sai về paging, sorting hoặc join.
- Kiểm thử tích hợp trên LDAP directory thật và chẩn đoán sự cố thiếu Q-type.

## 1. Vì sao cần predicate trong repository?

Giả sử người dùng tìm nhân viên theo:

```text
uid      = lan             (có thể bỏ trống)
surname  = Nguyen          (có thể bỏ trống)
mail     = lan@example.org (có thể bỏ trống)
```

Nếu định nghĩa mỗi tổ hợp là một derived query method, interface nhanh chóng trở nên khó bảo trì:

```java
List<PersonEntry> findByUid(String uid);
List<PersonEntry> findBySurname(String surname);
List<PersonEntry> findByEmail(String email);
List<PersonEntry> findByUidAndSurname(String uid, String surname);
List<PersonEntry> findBySurnameAndEmail(String surname, String email);
List<PersonEntry> findByUidAndSurnameAndEmail(
        String uid, String surname, String email);
```

Với Querydsl, ứng dụng tạo **một predicate** từ những điều kiện đã được người dùng cung cấp rồi truyền vào một phương thức thực thi chung:

```text
Input đã validate
       |
       v
QPersonEntry (metamodel sinh tự động)
       |
       v
Predicate: uid = "lan" AND surname = "Nguyen"
       |
       v
PersonRepository.findAll(predicate)
       |
       v
Spring Data LDAP Querydsl executor
       |
       v
LDAP search: base DN + scope + filter
       |
       v
Directory entries -> ODM mapping -> PersonEntry
```

Điều quan trọng: **predicate không phải DN**, không tự mở một kết nối LDAP và cũng không đại diện cho một câu SQL. Nó là điều kiện trên **thuộc tính Java của entity ODM**, sau đó được hạ tầng LDAP dịch thành truy vấn tương ứng với khả năng backend.

## 2. Ba thành phần của tích hợp Querydsl

Spring Data LDAP cung cấp ba phần liên quan:

| Thành phần | Vai trò | Có cần viết tay không? |
|---|---|---|
| `LdapAnnotationProcessor` | Annotation processor tạo `Q...` metamodel từ entity được đánh dấu `@Entry`/ODM | **Không** tự viết Q-class; cấu hình build để sinh |
| `QuerydslLdapQuery` | Hạ tầng tạo/thực thi truy vấn Querydsl theo LDAP | Thường không cần khởi tạo trực tiếp khi dùng repository |
| `QuerydslLdapPredicateExecutor` | Implementation phía Spring Data LDAP cho `QuerydslPredicateExecutor<T>` | Framework ghép vào repository; không nên tự xây thủ công trong use case thông thường |

Ví dụ cấu trúc:

```text
src/main/java/com/example/ldap/
  PersonEntry.java               <- entity ODM @Entry
  PersonRepository.java          <- LdapRepository + QuerydslPredicateExecutor
  PersonSearchService.java       <- xây Predicate và gọi Repository

build/generated/sources/annotationProcessor/java/main/
  com/example/ldap/QPersonEntry.java <- sinh bởi LdapAnnotationProcessor
```

Vị trí output có thể khác theo Maven, Gradle, IDE và phiên bản build tool. **Không đặt `QPersonEntry` viết tay vào source tree** để che lỗi annotation processing: Q-type phải được tạo lại khi model thay đổi.

**Lưu ý phiên bản:** class `QuerydslLdapRepository` (implementation nguyên khối trước đây) đã được đánh dấu **deprecated** trong API Spring Data LDAP hiện đại; hạ tầng mới dùng fragment `QuerydslLdapPredicateExecutor`. Bạn chỉ cần khai báo đúng **hai interface** trên repository, không chọn class implementation deprecated làm repository base class.

## 3. Chuẩn bị entity LDAP ODM

Trước khi dùng Querydsl, đối tượng domain phải ánh xạ được sang LDAP entry. Giả sử directory có:

```ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
sn: Nguyen
mail: lan@example.org
```

Định nghĩa entity:

**`PersonEntry.java`**

```java
package com.example.ldap;

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
public class PersonEntry {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String uid;

    @Attribute(name = "cn")
    private String displayName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String email;

    public PersonEntry() {}

    public Name getDn() { return dn; }
    public void setDn(Name dn) { this.dn = dn; }

    public String getUid() { return uid; }
    public void setUid(String uid) { this.uid = uid; }

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getSurname() { return surname; }
    public void setSurname(String surname) { this.surname = surname; }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
}
```

Các điểm cần hiểu:

- `@Entry` khai báo nhánh và loại objectClass mà ODM sẽ dùng để tìm/ánh xạ entry.
- `@Id` chứa DN của entry theo hợp đồng ODM; với `LdapRepository<T>`, loại ID mặc định là `javax.naming.Name`, **không** phải `Long` hay `String`.
- `@Attribute(name="sn")` ánh xạ thuộc tính LDAP `sn` vào **property Java** `surname`. Khi dùng Q-type, lập trình viên tham chiếu `q.surname`, không tự đoán sẽ có `q.sn`.
- Một entity có thể có nhiều thuộc tính tùy chọn. Đừng cho rằng mọi entry đều có `mail` hoặc tài khoản bind được đọc tất cả thuộc tính.
- `@Entry(base="ou=people")` kết hợp với base của `ContextSource` cần được kiểm tra để tránh nhầm DN tương đối/đầy đủ.

**Không dùng `@Entity` của JPA** để thay `@Entry`, cũng không đưa `javax.persistence.Query`/`JPAQuery` vào luồng xử lý LDAP. Querydsl chỉ cung cấp biểu thức truy vấn chung; **backend LDAP** mới quyết định điều gì có thể thực thi.

## 4. Bật annotation processing để sinh Q-type

Spring Data LDAP không tự bật `LdapAnnotationProcessor` trong mọi dự án. Nếu chỉ thêm `QuerydslPredicateExecutor` mà chưa có Q-type, code `QPersonEntry.personEntry` sẽ không biên dịch.

### 4.1. Minh họa cấu hình Gradle (Groovy DSL)

Thêm dependency cần thiết và đăng ký processor:

**`build.gradle` — đoạn cấu hình minh họa**

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-ldap'

    // Phiên bản Querydsl phải tương thích với Spring Data/Boot đang dùng.
    implementation "com.querydsl:querydsl-core:${querydslVersion}"
    annotationProcessor "com.querydsl:querydsl-apt:${querydslVersion}:jakarta"
    annotationProcessor 'org.springframework.data:spring-data-ldap'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += [
        '-processor',
        'org.springframework.data.ldap.repository.support.LdapAnnotationProcessor'
    ]
}
```

`querydslVersion` phải được khai báo trong build và tương thích với **BOM/dependency management** của project. Ví dụ dùng tọa độ `com.querydsl` để minh họa; Spring Data Commons hiện cũng đề cập **OpenFeign Querydsl fork** với group `io.github.openfeign.querydsl` và mức hỗ trợ theo phiên bản. **Không phối hợp** artifact Querydsl gốc và fork một cách tùy tiện; hãy dùng một bộ dependency/annotation processor thống nhất, kiểm tra dependency tree và tài liệu của phiên bản đang triển khai.

Một số phiên bản/hướng dẫn có classifier `jakarta` cho các artifact Querydsl. Trên môi trường cụ thể, kiểm tra **artifact được phát hành thực sự** và classpath annotation processor; `querydsl-core`, `querydsl-apt` có thể không có cùng tập classifier. Đoạn trên cố tình không chốt phiên bản vì đề bài không cung cấp build file dự án.

Nếu dùng Maven, nguyên tắc tương tự: khai báo Querydsl runtime + annotation processor và cấu hình `maven-compiler-plugin` với:

```text
org.springframework.data.ldap.repository.support.LdapAnnotationProcessor
```

Trong một dự án đã có các processor khác (Lombok, MapStruct, v.v.), lưu ý `-processor` có thể **chỉ định danh sách processor cần chạy**; đừng vô tình vô hiệu hóa các processor đang sử dụng. Phải điều chỉnh đầy đủ danh sách hoặc cơ chế discovery để build vẫn hoạt động.

### 4.2. Kết quả mong đợi của APT

Sau khi build/compile **ở môi trường dự án của bạn**, compiler sẽ sinh một class tương tự:

```java
// Ví dụ hình thức — QPersonEntry do Querydsl sinh; KHÔNG viết tay.
package com.example.ldap;

public class QPersonEntry /* extends EntityPathBase<PersonEntry> */ {
    // Các path tương ứng với property Java của PersonEntry.
    // QPersonEntry.personEntry.uid
    // QPersonEntry.personEntry.surname
    // QPersonEntry.personEntry.email
}
```

Tên static instance thường là `QPersonEntry.personEntry`. Cách Q-type được sinh và danh sách path chính xác phụ thuộc metadata entity, processor và build. Hãy **mở generated sources** để xác minh sau khi compile; đừng tạo giả một Q-type rồi đánh giá rằng tích hợp đã hoàn tất.

Nếu Q-type chưa xuất hiện, kiểm tra lần lượt:

1. Entity có `@Entry` của Spring LDAP ODM hay không?
2. `spring-data-ldap` có nằm trong annotation processor classpath không?
3. Querydsl APT và dependency của nó có tương thích với phiên bản Java/Boot không?
4. Processor `LdapAnnotationProcessor` có thực sự được compiler gọi không?
5. IDE có đánh dấu thư mục generated sources là source root không?
6. Lần compile sau khi đổi entity có thực sự tái tạo Q-type không?

**Không cần chạy JPA annotation processor** để tạo Q-class cho entity LDAP. Processor được sử dụng ở đây là `org.springframework.data.ldap.repository.support.LdapAnnotationProcessor`.

## 5. Khai báo Repository thực thi predicate

Chỉ cần mở rộng hai interface:

**`PersonRepository.java`**

```java
package com.example.ldap;

import org.springframework.data.ldap.repository.LdapRepository;
import org.springframework.data.querydsl.QuerydslPredicateExecutor;

public interface PersonRepository
        extends LdapRepository<PersonEntry>,
                QuerydslPredicateExecutor<PersonEntry> {

    // Các derived finder vẫn có thể khai báo ở đây.
    // Ví dụ: List<PersonEntry> findByUid(String uid);
}
```

Điểm quan trọng:

- `LdapRepository<PersonEntry>` có **một type parameter**, entity ODM. Không khai báo `LdapRepository<PersonEntry, Name>`.
- `QuerydslPredicateExecutor<PersonEntry>` bổ sung các API nhận `Predicate`.
- Spring Data tạo repository proxy và nối phần thực thi Querydsl vào repository khi dependency/metamodel/LDAP infrastructure đã được cấu hình đúng.
- Không cần người dùng tự triển khai `findAll(Predicate)` bằng cách parse expression và nối chuỗi filter.
- Entity vẫn cần một `@Id` kiểu `Name`; repository có cùng các giới hạn schema, base DN và quyền truy cập như các query LDAP thông thường.

Thông thường project Spring Boot tự nhận các repository trong package được scan. Khi cần cấu hình rõ:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.ldap.repository.config.EnableLdapRepositories;

@Configuration
@EnableLdapRepositories(basePackageClasses = PersonRepository.class)
public class DirectoryRepositoryConfiguration {
}
```

Chỉ bật cấu hình rõ ràng này nếu cần; tránh trùng repository scan với một cấu hình `@EnableLdapRepositories` khác. Nếu đang có nhiều `LdapTemplate` hoặc `ContextSource`, bảo đảm repository được nối tới **đúng** directory và base đã dự định.

### 5.1. Những phương thức cần nhớ

| API | Ý nghĩa | Rủi ro/ngữ nghĩa cần xác nhận |
|---|---|---|
| `findAll(Predicate)` | Trả mọi entry phù hợp trong phạm vi repository | Có thể nhiều entry và tốn tài nguyên |
| `findOne(Predicate)` | Tìm đúng một entry phù hợp | 0 entry -> `Optional.empty()`; nhiều hơn một có thể báo lỗi không duy nhất |
| `count(Predicate)` | Đếm entry phù hợp | Không tự giới hạn kết quả hay đảm bảo hiệu năng rẻ |
| `exists(Predicate)` | Kiểm tra có entry phù hợp không | Không có tính khóa; trạng thái có thể đổi sau phép kiểm tra |

`findAll(Predicate)` trên interface `QuerydslPredicateExecutor` có thể được khai báo trả `Iterable<T>` dù implementation LDAP trả một danh sách. Để code tương thích với chữ ký public interface, hãy khai báo:

```java
Iterable<PersonEntry> results = repository.findAll(predicate);
```

Không gán trực tiếp vào `List<PersonEntry>` nếu interface compile-time chỉ hứa `Iterable<PersonEntry>`. Có thể dùng `ListQuerydslPredicateExecutor` nếu phiên bản hỗ trợ và nhu cầu cần rõ `List`, nhưng phải kiểm tra khả năng của repository LDAP trước khi thay interface.

## 6. Thực thi predicate đơn giản

Khi Q-type đã được tạo, có thể dùng:

**`PersonSearchService.java`**

```java
package com.example.ldap;

import com.querydsl.core.types.Predicate;
import org.springframework.stereotype.Service;

@Service
public class PersonSearchService {
    private final PersonRepository repository;

    public PersonSearchService(PersonRepository repository) {
        this.repository = repository;
    }

    public Iterable<PersonEntry> findByUidAndSurname(
            String uid, String surname) {

        if (uid == null || uid.isBlank() ||
                surname == null || surname.isBlank()) {
            throw new IllegalArgumentException(
                    "uid và surname không được rỗng");
        }

        QPersonEntry person = QPersonEntry.personEntry;
        Predicate predicate = person.uid.eq(uid)
                .and(person.surname.eq(surname));

        return repository.findAll(predicate);
    }

    public boolean hasEmail(String email) {
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("email không được rỗng");
        }

        QPersonEntry person = QPersonEntry.personEntry;
        return repository.exists(person.email.eq(email));
    }
}
```

Trong `QPersonEntry`, `uid`, `surname` và `email` là **property Java** của `PersonEntry`. Spring Data LDAP liên hệ property đó với các thuộc tính LDAP `uid`, `sn` và `mail` thông qua metadata ODM. Vì vậy:

```text
person.uid.eq("lan")         -> điều kiện trên thuộc tính LDAP uid
person.surname.eq("Nguyen")  -> điều kiện trên thuộc tính LDAP sn
person.email.eq("lan@...")   -> điều kiện trên thuộc tính LDAP mail
```

Giá trị `"lan"` là dữ liệu tìm kiếm, không phải tên DN hay tên thuộc tính LDAP tự động. Querydsl tạo biểu thức; lớp chuyển đổi LDAP quyết định cách mã hóa thành filter thực tế. Vẫn phải kiểm thử các ký tự đặc biệt, hỗ trợ operator và ranh giới ACL trên directory mục tiêu.

Không giả định Predicate tự làm thay đổi scope sang toàn bộ directory. Tập entry được truy cập còn phụ thuộc `@Entry(base=...)`, `ContextSource.base`, search scope và cấu hình repository.

## 7. Predicate động cho màn hình tìm kiếm

Sức mạnh của Querydsl thể hiện rõ khi các điều kiện là tùy chọn. Có thể dùng `com.querydsl.core.BooleanBuilder` để ghép `AND` theo input.

**`PersonCriteria.java`**

```java
package com.example.ldap;

public record PersonCriteria(
        String uid,
        String surname,
        String email
) {}
```

**`PersonSearchService.java` — thêm phương thức**

```java
import com.querydsl.core.BooleanBuilder;

public Iterable<PersonEntry> search(PersonCriteria criteria) {
    if (criteria == null) {
        throw new IllegalArgumentException("criteria không được null");
    }

    QPersonEntry person = QPersonEntry.personEntry;
    BooleanBuilder builder = new BooleanBuilder();

    if (hasText(criteria.uid())) {
        builder.and(person.uid.eq(criteria.uid().trim()));
    }
    if (hasText(criteria.surname())) {
        builder.and(person.surname.eq(criteria.surname().trim()));
    }
    if (hasText(criteria.email())) {
        builder.and(person.email.eq(criteria.email().trim()));
    }

    if (!builder.hasValue()) {
        throw new IllegalArgumentException(
                "Phải cung cấp ít nhất một điều kiện tìm kiếm");
    }
    return repository.findAll(builder);
}

private static boolean hasText(String value) {
    return value != null && !value.isBlank();
}
```

Đoạn trên là **một phương thức thêm vào class `PersonSearchService`**, không phải một class Java độc lập. Nó giới hạn những thuộc tính mà client có thể lọc bằng cách **lập trình viên chọn path cho phép**, thay vì nhận một trường query bất kỳ và tạo biểu thức từ tên do client cung cấp.

Quyết định `trim()` là một **quy tắc nghiệp vụ** của ví dụ; nếu thuộc tính LDAP cho phép khoảng trắng đầu/cuối có ý nghĩa, đừng thay đổi giá trị nhập như vậy. Với `uid`, thường nên validate cú pháp login name theo chính sách của tổ chức.

### 7.1. AND, OR và các nhóm điều kiện

Querydsl có thể biểu diễn:

```java
QPersonEntry person = QPersonEntry.personEntry;

// Nhóm có họ Nguyen hoặc Tran.
Predicate bySurname = person.surname.eq("Nguyen")
        .or(person.surname.eq("Tran"));

// Chỉ những người có email nội bộ trong hai nhóm họ trên.
Predicate finalPredicate = person.email.eq("lan@example.org")
        .and(bySurname);
```

Về ý nghĩa, predicate cuối là:

```text
mail = lan@example.org
AND
(sn = Nguyen OR sn = Tran)
```

Tại LDAP server, phép tìm kiếm cần được biểu diễn bằng **filter LDAP**, chẳng hạn `(&(...)(|(...)(...)))`, không phải `SELECT ... WHERE ...` của SQL. Không cố suy ra chính xác chuỗi filter từ `predicate.toString()`; chuỗi debug của Querydsl không nhất thiết là LDAP filter đã được gửi đi.

### 7.2. Những operator cần thử trên backend

| Querydsl expression | Mục tiêu | Ghi chú với LDAP |
|---|---|---|
| `path.eq(value)` | So khớp bằng | Bắt đầu bằng loại này để kiểm thử |
| `a.and(b)` | Kết hợp điều kiện | Thường tương đương ý nghĩa filter `&` |
| `a.or(b)` | Một trong các điều kiện | Thường tương đương ý nghĩa filter `|` |
| `path.startsWith(value)` | Tìm tiền tố | Cần xác minh cách chuyển sang LDAP substring filter và escape wildcard |
| `path.contains(value)` | Tìm chuỗi con | Có thể tốn kém; cần xác minh hỗ trợ/index của directory |
| `path.equalsIgnoreCase(value)` | So khớp không phân biệt hoa/thường | Đặc biệt phụ thuộc matching rule của LDAP attribute và mức hỗ trợ phép chuyển đổi |
| Toán tử JOIN/aggregate kiểu SQL | Kết hợp bảng hoặc GROUP BY | **Không** phải tính năng truy vấn LDAP chuẩn của repository |

Không mọi API của Querydsl hoặc mọi overload trên `QuerydslPredicateExecutor` đều có thể chuyển thành thao tác LDAP có semantics tương đương. **Hãy kiểm thử operator cụ thể** bằng dữ liệu LDAP mẫu và phiên bản thư viện đang dùng; nếu không được hỗ trợ, dùng `LdapQueryBuilder`/`LdapTemplate` với LDAP filter phù hợp hoặc điều chỉnh yêu cầu.

## 8. Phân biệt findOne, count, exists và findAll

### 8.1. findOne: yêu cầu duy nhất

```java
import java.util.Optional;

QPersonEntry person = QPersonEntry.personEntry;
Optional<PersonEntry> found =
        repository.findOne(person.uid.eq("lan"));
```

Phép tìm `uid=lan` **không bảo đảm chỉ có một entry** trong toàn bộ LDAP tree. Hai container `ou=employees` và `ou=contractors` có thể chứa người dùng mang cùng `uid`. Nếu kết quả nhiều hơn một, `findOne` có thể phát sinh ngoại lệ do không duy nhất; đừng bắt mọi exception và trả `Optional.empty()`.

Nếu nghiệp vụ chỉ cần một identity cụ thể, cân nhắc `findById(Name dn)` sau khi xác định **đúng DN**, hoặc giới hạn directory/tenant và bảo đảm uniqueness ở server.

### 8.2. count: đếm không đồng nghĩa với paging

```java
QPersonEntry person = QPersonEntry.personEntry;
long matching = repository.count(person.surname.eq("Nguyen"));
```

`count` phải dựa trên tập entry LDAP khớp điều kiện. Nó không có semantics của `COUNT(*)` được tối ưu trên một hệ SQL, cũng không được coi là miễn phí. Server size limit, ACL, referral, filter và phạm vi tìm kiếm ảnh hưởng kết quả thực tế. Với tác vụ kiểm kê cần đầy đủ, cần chứng minh directory đã cung cấp đủ phạm vi trước khi sử dụng số đếm.

### 8.3. exists: không dùng để khóa trạng thái

```java
boolean known = repository.exists(
        QPersonEntry.personEntry.email.eq("lan@example.org"));
```

`exists(predicate)` trả lời câu hỏi **“có entry khớp tại thời điểm tìm kiếm không?”**. Nó không tạo lock. Mẫu:

```text
exists(predicate) -> false
          [writer khác tạo entry]
save(entity)      -> có thể gặp DN trùng hoặc vi phạm quy tắc uniqueness
```

là TOCTOU (*time-of-check to time-of-use*). Nếu muốn bảo đảm DN chưa tồn tại, thao tác LDAP **Add** phải được server xử lý; nếu muốn uniqueness theo email/uid trên nhiều DN, cần chính sách uniqueness riêng, không chỉ `exists(...)`.

## 9. Paging, sorting và giới hạn thực tế của LDAP

Interface `QuerydslPredicateExecutor<T>` của Spring Data Commons có thể khai báo các overload cho `Sort`, `Pageable` và `OrderSpecifier<?>`. Nhưng tài liệu **Spring Data LDAP** nhấn mạnh rằng **paging và sorting không được hỗ trợ như một tính năng repository LDAP thông thường**. Vì vậy tránh dùng một ví dụ generic của JPA như thể nó chắc chắn làm việc trên LDAP:

```java
// KHÔNG suy luận rằng API này có paging/sorting thật trên LDAP:
// repository.findAll(predicate, PageRequest.of(0, 20));
// repository.findAll(predicate, Sort.by("surname"));
```

Ngay cả khi chữ ký method có trong interface, implementation LDAP có thể có giới hạn, bỏ qua một phần semantics hoặc ném lỗi tùy phiên bản. Không dựa vào overload đó cho nghiệp vụ cần thứ tự tuyệt đối hay phân trang chính xác trước khi đã kiểm thử end-to-end với directory/server cụ thể.

Nếu cần đọc tập kết quả lớn:

- Chọn base DN, search scope và filter đủ hẹp để giới hạn số entry.
- Với `LdapTemplate`, cân nhắc LDAP paged-results control hoặc server-side sort control **nếu** server/provider hỗ trợ; đây không đồng nghĩa với Spring Data repository `Pageable`.
- Chú ý giới hạn số kết quả, timeout, referral và các nguồn đọc/replica.
- Nếu phải phân trang phía ứng dụng, cần hiểu đó là cách xử lý trên tập đã tải, **không** phải LDAP server-side pagination.
- Xem xét quyền riêng tư/giới hạn tải trước khi cho phép predicate rỗng hoặc truy vấn toàn bộ `ou=people`.

**Không dùng** `findAll(predicate)` trên toàn directory chỉ để xem một trang 20 người dùng rồi phân trang trong Java: có thể tạo một truy vấn lớn, tốn bộ nhớ và vượt giới hạn LDAP server.

## 10. Querydsl không thay thế query scope và bảo mật

Một predicate `person.email.eq(input)` sử dụng path đã khai báo sẵn giúp giảm nhu cầu tự nối chuỗi filter. Tuy nhiên, **type safety không đồng nghĩa với authorization**:

1. Người dùng không được phép tùy ý tìm mọi thuộc tính trong directory. Chỉ expose các trường được duyệt, ví dụ `uid`, `surname`, `email`.
2. Repository phải dùng `ContextSource`/base DN đúng directory/tenant. Predicate không tự chọn context kết nối hoặc giới hạn nhánh dữ liệu theo quyền caller.
3. LDAP server vẫn phải cưỡng chế **ACL** khi trả entry và thuộc tính; đừng dùng filter ở tầng ứng dụng làm cơ chế quyền duy nhất.
4. Đầu vào tìm kiếm phải có giới hạn độ dài, số điều kiện và phạm vi. Đặc biệt tránh wildcard/substring query quá rộng khi không cần thiết.
5. Luôn phân biệt LDAP DN với giá trị thuộc tính: `uid=lan` trong filter không chứng minh DN là `uid=lan,ou=people,dc=example,dc=org`.
6. Không log password bind, thuộc tính nhạy cảm hoặc LDAP filter chứa dữ liệu cá nhân đầy đủ. Metric tags nên có cardinality thấp, không gắn email/DN người dùng.

Nếu expose `@QuerydslPredicate` trực tiếp ở HTTP controller, Spring Data Web có khả năng bind parameter của request sang predicate. Với LDAP, phải **cấu hình rõ whitelist/binding** và xác nhận rằng server/client không thể tìm các path nhạy cảm hoặc tạo truy vấn quá đắt. Một cách đơn giản và thường dễ kiểm soát hơn là nhận DTO tiêu chí ở service, validate rồi tự xây `BooleanBuilder` như mục 7.

**Lưu ý escaping:** Querydsl expression và backend LDAP chịu trách nhiệm chuyển giá trị thành filter; vẫn nên kiểm thử với input chứa `*`, `(`, `)`, `\` và NUL để chắc chắn không có LDAP filter injection hay thay đổi semantics. Không tự chuyển `predicate.toString()` thành raw filter cho `LdapTemplate.search(...)`.

## 11. So sánh các cách truy vấn trên Spring Data LDAP

| Cách | Phù hợp với | Ưu điểm | Hạn chế |
|---|---|---|---|
| Derived finder `findByUid(...)` | Một vài điều kiện cố định | Đơn giản, ít cấu hình | Nhiều tổ hợp làm phình interface |
| `@Query` trên repository | Filter LDAP đã biết cấu trúc | Có thể mô tả filter rõ | Gắn với chuỗi query và mapping tham số |
| `LdapRepository.findAll(LdapQuery)` | Cần chọn base, scope, attributes và filter linh hoạt | Dùng `LdapQueryBuilder` của Spring LDAP | Property name thường biểu diễn bằng chuỗi thuộc tính LDAP |
| `QuerydslPredicateExecutor` | Tạo điều kiện động từ Java model | Q-type giúp kiểm tra property khi compile | Cần annotation processing; chỉ áp dụng operator mà backend LDAP hỗ trợ |
| `LdapTemplate`/`LdapQueryBuilder` | Cần kiểm soát search controls, projection hoặc mapper tùy biến | Kiểm soát trực tiếp tìm kiếm LDAP | Code data-access chi tiết hơn |

**Quy tắc chọn:** nếu service chỉ có một điều kiện `uid`, không cần lắp Querydsl chỉ để viết `.eq(uid)`. Querydsl mang lại lợi ích rõ hơn khi có nhiều điều kiện tổ hợp, model thay đổi thường xuyên và team muốn type-safe expression dùng lại giữa nhiều service.

## 12. Kiểm thử tích hợp Repository predicate

Unit test kiểm tra `BooleanBuilder` có thể xác nhận logic ghép điều kiện, nhưng không chứng minh executor đã chuyển expression thành LDAP filter đúng. Cần kiểm thử trên một **LDAP directory test** có schema/ACL tương ứng.

### 12.1. Dữ liệu LDIF mẫu

```ldif
dn: ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
sn: Nguyen
mail: lan@example.org

dn: uid=binh,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: binh
cn: Binh Tran
sn: Tran
mail: binh@example.org
```

Giả định `ContextSource.base=dc=example,dc=org` và repository tìm trong `ou=people`.

### 12.2. Ví dụ bài test

**`PersonPredicateIT.java`**

```java
package com.example.ldap;

import com.querydsl.core.types.Predicate;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class PersonPredicateIT {

    @Autowired
    PersonRepository repository;

    @Test
    void findAllUsesPredicateOnMappedProperties() {
        QPersonEntry person = QPersonEntry.personEntry;
        Predicate predicate = person.uid.eq("lan")
                .and(person.surname.eq("Nguyen"));

        Iterable<PersonEntry> matches = repository.findAll(predicate);
        int count = 0;
        for (PersonEntry entry : matches) {
            assertEquals("lan", entry.getUid());
            assertEquals("Nguyen", entry.getSurname());
            count++;
        }
        assertEquals(1, count);
    }

    @Test
    void existsReturnsFalseForMissingValue() {
        QPersonEntry person = QPersonEntry.personEntry;
        assertFalse(repository.exists(
                person.uid.eq("missing-user-123")));
    }

    @Test
    void countReturnsExpectedNumber() {
        QPersonEntry person = QPersonEntry.personEntry;
        assertEquals(1L, repository.count(
                person.surname.eq("Nguyen")));
    }
}
```

Điều kiện để ví dụ có ý nghĩa:

- `QPersonEntry` đã được tạo bởi APT **trước khi compile test**.
- Test directory thực sự có hai user như fixture, không chứa thêm dữ liệu có thể khớp.
- `PersonRepository` được Spring Boot tạo thành bean và nối đúng `ContextSource`.
- Tài khoản bind có quyền tìm/đọc những thuộc tính cần thiết.

Kiểm thử này không tự tạo LDAP test server; cần khởi động embedded/testcontainer directory hoặc cấp directory riêng trước khi chạy. Không chạy các test có thao tác tạo/xóa trên directory production.

### 12.3. Ma trận test cần bổ sung

| Test case | Mục tiêu |
|---|---|
| `uid.eq("lan")` | Tìm đúng một entry theo thuộc tính Java được ánh xạ |
| `surname.eq("Nguyen")` | Xác nhận `surname` map tới LDAP `sn` |
| `uid.eq(...).and(surname.eq(...))` | Kết hợp điều kiện AND |
| Hai điều kiện OR | Kết quả gồm đúng các entry của hai nhánh |
| Input có dấu `*` hoặc `(` | Xác minh ký tự special được coi là dữ liệu, không chèn filter |
| Predicate không có match | `findAll` rỗng, `exists` false, `count` bằng 0 |
| `findOne` với nhiều entry khớp | Phải xử lý đúng lỗi không duy nhất |
| Tài khoản bind thiếu quyền | Không coi ACL error là “không có người dùng” |
| Server size limit thấp | Không tuyên bố kết quả đầy đủ chỉ từ một lần query |
| Repository được scan sai package | Bean không tồn tại hoặc thiếu Querydsl executor |
| Xóa generated Q-class rồi compile | Build tạo lại Q-type bằng processor đã cấu hình |
| Sort/Pageable | Ghi nhận hành vi LDAP thực tế, không suy luận từ signature |

Nên đặt giới hạn số kết quả/timeout ở tầng LDAP phù hợp và test thêm trường hợp server trả referral hoặc `PartialResultException`. Nếu cần dữ liệu qua nhiều naming context, việc có predicate chính xác **không** bảo đảm toàn bộ cây LDAP đã được truy vấn.

## 13. Chẩn đoán lỗi tích hợp thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Compiler báo `cannot find symbol QPersonEntry` | Annotation processing chưa bật hoặc chưa chạy | Kiểm tra APT path, tên processor và generated sources |
| `NoClassDefFoundError` liên quan Querydsl | Runtime thiếu/thừa artifact, phiên bản xung đột | Căn chỉnh dependency/BOM, không trộn fork và bản gốc tùy tiện |
| Q-type thiếu property `surname` | Entity/processor chưa cập nhật hoặc property không được nhận diện | Kiểm tra `@Entry`, `@Attribute`, getters và build lại Q-type |
| Repository không khởi tạo được | Thiếu Querydsl/Spring Data LDAP cấu hình hoặc bean scan sai | Kiểm tra logs khởi động và `@EnableLdapRepositories` |
| `findAll` trả rỗng dù entry có tồn tại | Base DN/scope/ACL sai, filter không khớp hoặc mapping sai | Đối chiếu DN, property–attribute mapping và server |
| `findOne` báo không duy nhất | Có nhiều entry cùng giá trị property trong phạm vi tìm | Dùng DN, giới hạn base/tenant hoặc quy định uniqueness |
| Operator đặc biệt không được hỗ trợ | Querydsl expression vượt khả năng chuyển sang LDAP filter | Giới hạn operator, chuyển sang `LdapTemplate` khi cần |
| API paging/sorting không như mong đợi | Giới hạn Spring Data LDAP so với Commons/JPA | Dùng thiết kế pagination LDAP thực sự đã kiểm thử |
| Query chậm dù dùng type-safe Predicate | Filter thiếu index, scope rộng, quá nhiều entry | Phân tích directory index, search controls, network và tải |
| Client được lọc thuộc tính nhạy cảm | Không kiểm soát các path cho phép từ HTTP | Dùng DTO criteria, allowlist, LDAP ACL và audit |

Một predicate **biên dịch được** mới chứng minh property/path hợp lệ trong model Java. Điều đó **chưa chứng minh** LDAP server có index thích hợp, schema cho phép, tài khoản bind có ACL, hay dữ liệu kết quả đã đầy đủ.

## 14. Câu hỏi tự kiểm tra

1. Vì sao repository có nhiều bộ lọc tùy chọn thường hưởng lợi từ `QuerydslPredicateExecutor` hơn cách tạo hàng loạt `findBy...And...`?
2. `LdapAnnotationProcessor` làm gì? Vì sao chỉ thêm `querydsl-core` không đủ để sử dụng `QPersonEntry`?
3. `LdapRepository<PersonEntry>` cần bao nhiêu type parameter, và loại ID mặc định là gì?
4. Sự khác biệt giữa `@Attribute(name="sn")` và `QPersonEntry.personEntry.surname` là gì?
5. Viết predicate `uid="lan" AND surname="Nguyen"`, rồi nêu phương thức repository dùng để thực thi.
6. Phân biệt `findOne`, `findAll`, `count` và `exists` khi predicate có 0, 1 hoặc nhiều entry phù hợp.
7. Vì sao `exists(predicate)` rồi mới `save(...)` không loại bỏ race condition?
8. Tại sao không thể mặc định dùng `PageRequest` với repository LDAP như với JPA?
9. Vì sao type-safe predicate không thay thế được ACL, ranh giới tenant hoặc validation đầu vào?
10. Để chứng minh Querydsl đã chạy đúng trên directory, cần những integration test nào?

**Ghi nhớ:** tích hợp Querydsl vào Spring Data LDAP gồm ba việc: **entity ODM có `@Entry`**, **APT sinh Q-type bằng `LdapAnnotationProcessor`**, và **repository kế thừa `LdapRepository<T>` cùng `QuerydslPredicateExecutor<T>`**. Predicate giúp tổ hợp điều kiện theo property Java một cách type-safe, nhưng LDAP vẫn có DN/base/scope, objectClass/schema, ACL, giới hạn filter, paging và sorting riêng. Hãy dùng các executor method cơ bản, kiểm thử operator trên directory thực và tránh coi tính an toàn kiểu là bảo đảm an toàn quyền truy cập.

### Tài liệu tham khảo

- Spring Data LDAP — [Querydsl Support](https://docs.spring.io/spring-data/ldap/reference/ldap/querydsl.html): ba thành phần tích hợp `LdapAnnotationProcessor`, `QuerydslLdapQuery` và repository predicate.
- Spring Data LDAP — [Spring Data Extensions / Querydsl](https://docs.spring.io/spring-data/ldap/reference/repositories/core-extensions.html): `QuerydslPredicateExecutor`, tạo Q-type, cấu hình annotation processing.
- Spring Data LDAP — [Configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html): `@EnableLdapRepositories`, DN ID `Name`, giới hạn paging/sorting.
- Spring Data LDAP API — [`QuerydslLdapPredicateExecutor`](https://docs.spring.io/spring-data/ldap/docs/current/api/org/springframework/data/ldap/repository/support/QuerydslLdapPredicateExecutor.html): triển khai LDAP-specific của các phương thức Predicate.
- Spring Data LDAP API — [`LdapAnnotationProcessor`](https://docs.spring.io/spring-data/ldap/docs/current/api/org/springframework/data/ldap/repository/support/LdapAnnotationProcessor.html): annotation processor cho entity `@Entry`.
- Spring LDAP — [Repositories](https://docs.spring.io/spring-ldap/reference/repositories.html): mô hình repository/ODM và hạn chế so với datastore khác.
- IETF [RFC 4511 — LDAP: The Protocol](https://www.rfc-editor.org/rfc/rfc4511) và [RFC 4515 — Search Filters](https://www.rfc-editor.org/rfc/rfc4515): base/scope/filter và mã hóa giá trị tìm kiếm.
