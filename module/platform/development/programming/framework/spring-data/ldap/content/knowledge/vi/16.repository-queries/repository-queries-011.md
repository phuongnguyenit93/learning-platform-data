# Kiểm tra tính hợp lệ của phương thức truy vấn khi khởi động

Một nhóm phát triển thêm phương thức `findByMailAddress(String email)` vào `PersonRepository`. Ứng dụng biên dịch thành công, nhưng khi Spring khởi tạo repository, context dừng với lỗi cho biết entity `Person` không có property `mailAddress`. Trong LDAP, attribute `mail` vẫn tồn tại và có dữ liệu; vấn đề nằm ở chỗ derived query dùng **tên property Java**, không dùng trực tiếp tên LDAP attribute. Một lỗi khác thường gặp là viết sai `findBySurname` thành `findBySurnmae`: lỗi này có thể được phát hiện ngay khi repository được tạo, trước khi có request HTTP đầu tiên.

Spring Data LDAP phân tích các phương thức truy vấn trong repository để tạo query tương ứng. Khi repository được khởi tạo theo chế độ eager mặc định, framework có thể kiểm tra cấu trúc tên phương thức, phân giải property trên entity và phát hiện nhiều lỗi định nghĩa ngay trong giai đoạn khởi động. Nhờ vậy, lỗi lập trình được phát hiện trước khi ứng dụng nhận lưu lượng thật.

Trong chương **Truy vấn Repository** của module **SPRING_DATA_LDAP**, bài này giải thích vòng đời tạo repository, các lớp kiểm tra query method, cách đọc lỗi khởi tạo, chiến lược tìm query và cách viết test để xác nhận repository được tạo thành công. Bài cũng phân biệt lỗi có thể phát hiện từ metadata Java với lỗi chỉ có thể phát hiện khi query thực sự được gửi tới LDAP server.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả thời điểm Spring Data LDAP phân tích query method và tạo repository proxy.
2. Phân biệt tên property Java với tên LDAP attribute được ánh xạ bằng ODM.
3. Đọc cấu trúc `find...By...`, điều kiện `And`/`Or`, toán tử và property path.
4. Phát hiện các lỗi thường gặp như sai property, sai tên method, nhầm `findById` và dùng toán tử không được LDAP hỗ trợ.
5. Hiểu `CREATE`, `USE_DECLARED_QUERY` và `CREATE_IF_NOT_FOUND`.
6. Phân biệt kiểm tra metadata lúc khởi động với kiểm tra filter, schema, ACL và matching rule trên server.
7. Viết test để fail fast khi repository có phương thức truy vấn không hợp lệ.
8. Chẩn đoán exception gốc khi Spring báo lỗi tạo repository.

## 2. Vì sao kiểm tra query method ngay lúc khởi động?

Một query method được khai báo bằng Java interface:

~~~java
public interface PersonRepository extends LdapRepository<Person> {

    List<Person> findBySurname(String surname);

    Optional<Person> findByEmployeeNumber(String employeeNumber);
}
~~~

Spring Data phải hiểu tên method để biết:

- `find` là thao tác truy vấn.
- `By` đánh dấu vị trí bắt đầu phần điều kiện.
- `Surname` là property cần tìm trong domain class.
- Kiểu trả về `List<Person>` hoặc `Optional<Person>` mô tả cách nhận kết quả.
- Tham số method cung cấp giá trị cho các điều kiện.

Nếu `Surname` không phải property của `Person`, framework không thể tạo query đúng. Đây là lỗi định nghĩa repository, không phải lỗi dữ liệu LDAP. Để lỗi này chỉ xuất hiện khi người dùng gọi endpoint lần đầu sẽ khiến thời gian phát hiện và xử lý sự cố dài hơn.

### 2.1. Ba giai đoạn cần phân biệt

~~~mermaid
flowchart TD
    A["Spring quét package repository"] --> B["Tạo LdapRepositoryFactoryBean"]
    B --> C["Khởi tạo repository factory/proxy"]
    C --> D["Tìm query cho từng method"]
    D --> E["Phân tích tên method và property Java"]
    E --> F{"Metadata và query definition hợp lệ?"}
    F -- "Không" --> G["Lỗi tạo repository<br/>ApplicationContext không khởi động"]
    F -- "Có" --> H["Repository proxy sẵn sàng"]
    H --> I["Ứng dụng gọi query method"]
    I --> J["Tạo filter và gửi LDAP request"]
    J --> K{"LDAP server chấp nhận?"}
    K -- "Không" --> L["Lỗi runtime: filter, schema, ACL, TLS..."]
    K -- "Có" --> M["Map kết quả thành entity"]
~~~

Ở chế độ khởi tạo repository eager, bước phân tích query method diễn ra khi Spring tạo repository bean. Một lỗi property có thể làm `ApplicationContext` không hoàn tất khởi động.

Sau đó, khi ứng dụng thực sự gọi method, Spring LDAP mới thực hiện search trên directory. Lúc này server mới có thể xác nhận các vấn đề như attribute có tồn tại trong schema hay không, matching rule có phù hợp không, bind account có quyền search không và base DN có hợp lệ không.

**Khởi động thành công không có nghĩa mọi truy vấn đã được LDAP server kiểm chứng.** Đây là hai lớp kiểm tra khác nhau và cần hai loại test khác nhau.

## 3. Query method dùng property Java, không dùng tên LDAP attribute

Đây là nguồn lỗi phổ biến nhất.

Giả sử entity được ánh xạ như sau:

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
        })
public class Person {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String username;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String emailAddress;

    @Attribute(name = "employeeNumber")
    private String employeeNumber;

    // Constructor, getter và setter theo yêu cầu của ODM.
}
~~~

Tên property Java và tên LDAP attribute:

| Property Java | LDAP attribute |
| --- | --- |
| `dn` | DN của entry, được đánh dấu bằng `@Id`. |
| `username` | `uid`. |
| `surname` | `sn`. |
| `emailAddress` | `mail`. |
| `employeeNumber` | `employeeNumber`. |

Repository đúng:

~~~java
import java.util.List;
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository extends LdapRepository<Person> {

    List<Person> findBySurname(String surname);

    List<Person> findByEmailAddress(String emailAddress);

    Optional<Person> findByEmployeeNumber(String employeeNumber);
}
~~~

`findByEmailAddress` hợp lệ vì `emailAddress` là property Java. ODM ánh xạ property này tới LDAP attribute `mail`.

Phương thức sau sai nếu entity không có property Java tên `mail`:

~~~java
// Sai nếu Person chỉ có property emailAddress được ánh xạ tới LDAP "mail".
List<Person> findByMail(String mail);
~~~

LDAP server có attribute `mail` không giúp query method hợp lệ. Spring Data phân tích property theo metadata domain class trước khi tạo filter. Hãy giữ tên property Java nhất quán và dùng `@Attribute(name = "...")` để khai báo tên attribute trong directory.

### 3.1. `@Entry`, `@Attribute` và `@Id` phải nhất quán

Spring LDAP ODM dùng bộ annotation của Spring LDAP:

- `@Entry` mô tả object class và base DN của entity.
- `@Attribute` ánh xạ property Java tới tên LDAP attribute.
- `@Id` đánh dấu property chứa DN.

Spring Data LDAP yêu cầu entity ODM có DN làm ID; kiểu ID repository mặc định là `javax.naming.Name`. Dùng `org.springframework.ldap.odm.annotations.Id`, không dùng nhầm `org.springframework.data.annotation.Id`.

Nếu entity chưa được ODM ánh xạ đúng, lỗi có thể xảy ra trong quá trình tạo mapping metadata hoặc repository, dù tên query method có vẻ đúng.

## 4. Cách Spring phân tích tên phương thức

Một derived query thường có hai phần:

~~~text
find...By<Property><Operator><Property><Operator>...
~~~

Phần đứng trước `By` mô tả loại thao tác và có thể chứa phần tên gợi nhớ. Phần sau `By` mô tả predicate thực sự.

Ví dụ:

~~~java
List<Person> findBySurnameAndEmailAddress(
        String surname,
        String emailAddress);

List<Person> findBySurnameOrUsername(
        String surname,
        String username);
~~~

Framework phân tích:

- `findBySurnameAndEmailAddress`: hai điều kiện kết hợp AND.
- `findBySurnameOrUsername`: hai điều kiện kết hợp OR.

Mỗi property trong predicate phải được phân giải trên domain class. Nếu một property không tồn tại, query derivation thất bại.

### 4.1. Các từ khóa Spring Data LDAP hỗ trợ

Tài liệu Spring Data LDAP liệt kê một tập từ khóa riêng cho query method. Không nên mặc định mọi từ khóa của Spring Data JPA hoặc Spring Data Commons đều có thể dùng trong LDAP.

| Từ khóa | Ví dụ | Ý nghĩa filter |
| --- | --- | --- |
| Không có toán tử | `findBySurname(String value)` | `(surname=value)` |
| `And` | `findBySurnameAndUsername(...)` | Hai điều kiện cùng đúng. |
| `Or` | `findBySurnameOrUsername(...)` | Một trong hai điều kiện đúng. |
| `StartingWith` | `findBySurnameStartingWith(String prefix)` | `(surname=prefix*)` |
| `EndingWith` | `findBySurnameEndingWith(String suffix)` | `(surname=*suffix)` |
| `Containing` | `findBySurnameContaining(String part)` | `(surname=*part*)` |
| `Like` | `findBySurnameLike(String value)` | So khớp theo biểu thức Like của Spring LDAP. |
| `NotLike` / `IsNotLike` | `findBySurnameNotLike(String value)` | Phủ định điều kiện Like. |
| `Not` | `findBySurnameNot(String value)` | Phủ định giá trị so khớp. |
| `IsNull` / `Null` | `findByEmailAddressNull()` | Attribute không hiện diện. |
| `IsNotNull` / `NotNull` | `findByEmailAddressNotNull()` | Attribute hiện diện. |
| `LessThanEqual` | `findByAgeLessThanEqual(Integer age)` | So sánh nhỏ hơn hoặc bằng theo matching rule của LDAP. |
| `GreaterThanEqual` | `findByAgeGreaterThanEqual(Integer age)` | So sánh lớn hơn hoặc bằng theo matching rule của LDAP. |

Tên method phải viết đúng cấu trúc từ khóa. Ví dụ `findBySurnameStartingWith` dùng property `surname` và toán tử `StartingWith`; `findByStartingWith` sẽ bị phân tích khác và không đại diện cho property `surname`.

`LessThanEqual` và `GreaterThanEqual` còn phụ thuộc cú pháp attribute và matching rule của schema server. Việc method được parse không chứng minh server có matching rule phù hợp cho attribute đó.

### 4.2. Không suy rộng từ từ khóa của JPA sang LDAP

Spring Data Commons có thể hiểu thêm nhiều từ khóa như `Between`, `In`, `IgnoreCase`, `OrderBy` hoặc tham số `Pageable`. Điều đó không có nghĩa Spring Data LDAP hỗ trợ tất cả các khả năng này. Tài liệu Spring Data LDAP nêu rõ paging và sorting không được hỗ trợ cho repository do đặc thù giao thức LDAP. Hãy chỉ dùng các predicate được tài liệu query methods của Spring Data LDAP liệt kê và kiểm thử trên server mục tiêu.

### 4.3. Kiểm tra số lượng tham số

Mỗi điều kiện cần tham số phải có giá trị tương ứng:

~~~java
// Hai property, hai tham số.
List<Person> findBySurnameAndUsername(
        String surname,
        String username);

// Predicate kiểm tra sự hiện diện, không cần tham số.
List<Person> findByEmailAddressNotNull();
~~~

Khai báo sai:

~~~java
// Sai: predicate có hai property nhưng chỉ có một tham số.
List<Person> findBySurnameAndUsername(String surname);
~~~

Spring Data có thể phát hiện lỗi cấu trúc tham số trong quá trình tạo query method hoặc khi chuẩn bị query, tùy loại query và phiên bản. Hãy xem nguyên nhân sâu nhất trong exception thay vì chỉ nhìn dòng `BeanCreationException` ngoài cùng.

### 4.4. Property path lồng nhau và dấu gạch dưới

Spring Data Commons cho phép phân giải property path lồng nhau. Ví dụ:

~~~java
List<Person> findByAddressZipCode(String zipCode);
~~~

Framework thử tìm property trực tiếp `addressZipCode`; nếu không có, nó có thể phân tách thành `address.zipCode`. Khi tên property tạo ra nhiều cách hiểu, dùng dấu gạch dưới để đánh dấu ranh giới:

~~~java
List<Person> findByAddress_ZipCode(String zipCode);
~~~

Đường dẫn này chỉ hợp lệ khi domain class thực sự có `address.zipCode` và mapping của ứng dụng hỗ trợ mô hình đó. **Cấu trúc OU/DN trong LDAP không tự động trở thành property path lồng nhau trong Java.**

Để tránh nhập nhằng, dùng camelCase chuẩn cho property Java và dấu gạch dưới trong method name chỉ khi cần phân định rõ các đoạn property.

## 5. Những tên method đặc biệt dễ gây nhầm lẫn

### 5.1. `findById` là phương thức dành riêng cho ID repository

Với Spring Data LDAP, ID của entity là DN (`javax.naming.Name`). Vì vậy:

~~~java
Optional<Person> findById(Name dn);
~~~

là phương thức kế thừa/được dành riêng để tìm theo ID DN. Nó không mặc nhiên có nghĩa là tìm property Java tên `id`.

Nếu entity có thêm property Java tên `id` và bạn muốn tìm theo property đó, dùng một phần mô tả trước `By` để tránh trùng tên dành riêng:

~~~java
Optional<Person> findPersonById(String id);
~~~

Tương tự, những method dành riêng như `existsById` và `deleteById` nhắm tới ID repository. Hãy đọc chữ ký method kế thừa trước khi tạo derived query trùng tên.

### 5.2. Từ khóa trong phần mô tả không phải property

Ví dụ:

~~~java
List<Person> findActivePeopleBySurname(String surname);
~~~

`ActivePeople` nằm giữa `find` và `By`, chỉ là phần mô tả tên method. Predicate vẫn chỉ chứa property `surname`.

Để thêm điều kiện trạng thái, phải khai báo property và toán tử trong predicate:

~~~java
List<Person> findBySurnameAndEmploymentStatus(
        String surname,
        String employmentStatus);
~~~

Điều này chỉ hợp lệ nếu entity có property `employmentStatus` được ánh xạ phù hợp với LDAP schema.

## 6. Chiến lược tìm query khi tạo repository

Spring Data LDAP có ba chiến lược `QueryLookupStrategy`:

| Chiến lược | Hành vi |
| --- | --- |
| `CREATE` | Luôn tạo query bằng cách phân tích tên method. |
| `USE_DECLARED_QUERY` | Tìm query được khai báo sẵn; nếu không tìm thấy query cho method thì repository khởi tạo thất bại. |
| `CREATE_IF_NOT_FOUND` | Tìm query khai báo trước, nếu không có thì tạo query từ tên method. Đây là mặc định. |

Khai báo chiến lược:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.repository.query.QueryLookupStrategy;
import org.springframework.data.ldap.repository.config.EnableLdapRepositories;

@Configuration
@EnableLdapRepositories(
        basePackageClasses = PersonRepository.class,
        queryLookupStrategy =
                QueryLookupStrategy.Key.CREATE_IF_NOT_FOUND)
class LdapRepositoryConfiguration {
}
~~~

Thông thường có thể giữ mặc định `CREATE_IF_NOT_FOUND`. Khi đó, method có `@Query` hoặc named query sẽ dùng query khai báo; method không có query khai báo sẽ được phân tích từ tên.

Nếu chọn `USE_DECLARED_QUERY`, mọi query method phải có query khai báo tương ứng. Thiếu query là lỗi cấu hình được phát hiện khi repository khởi tạo. Đây là cách buộc nhóm phát triển khai báo query tường minh, nhưng cần bảo đảm tất cả method đã có `@Query` hoặc named query được cấu hình.

### 6.1. Query khai báo bằng `@Query`

Ví dụ:

~~~java
import java.util.List;
import org.springframework.data.ldap.repository.LdapRepository;
import org.springframework.data.ldap.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends LdapRepository<Person> {

    @Query("(&(objectClass=inetOrgPerson)(mail=:emailAddress))")
    List<Person> findPeopleByMailFilter(
            @Param("emailAddress") String emailAddress);
}
~~~

`@Query` dùng LDAP filter được khai báo trực tiếp. Spring Data LDAP hỗ trợ tham số đặt tên với cú pháp `:emailAddress` và tham số theo vị trí như `?0`. Tham số đặt tên giúp giảm nhầm lẫn khi refactor chữ ký method.

Nếu dùng `USE_DECLARED_QUERY`, query method này có khai báo rõ ràng. Nếu query method không có `@Query` hoặc named query tương ứng, repository không thể tạo thành công theo chiến lược đó.

### 6.2. Kiểm tra encoding tham số

Spring Data LDAP mã hóa tham số của query dạng chuỗi theo quy tắc LDAP filter (tài liệu Spring Data LDAP mô tả theo RFC 2254). Có thể chọn encoder riêng bằng `@LdapEncode` cho từng tham số.

Ví dụ:

~~~java
import java.util.List;
import org.springframework.data.ldap.repository.LdapEncode;
import org.springframework.data.ldap.repository.Query;
import org.springframework.data.repository.query.Param;

@Query("(&(objectClass=inetOrgPerson)(mail=:emailAddress))")
List<Person> findByMailWithCustomEncoding(
        @LdapEncode(MyMailEncoder.class)
        @Param("emailAddress") String emailAddress);
~~~

`MyMailEncoder` là encoder do ứng dụng định nghĩa theo ngữ cảnh filter cần dùng. Không sao chép ví dụ này mà chưa xác định rõ encoding mong muốn.

Một điểm quan trọng: `@LdapEncode` áp dụng cho tham số của query method; nó không tự áp dụng cho derived query, SpEL expression hoặc property placeholder. Giá trị được cung cấp từ SpEL/property placeholder không tự động escape theo RFC 2254. Nếu dùng các cơ chế đó, phải chủ động bảo đảm encoding đúng và kiểm thử với các ký tự đặc biệt như `*`, `(`, `)`, dấu gạch chéo ngược và NUL.

### 6.3. Query method hợp lệ không đồng nghĩa filter đã được LDAP server chấp nhận

`@Query` có thể được tạo thành query method hợp lệ từ góc nhìn metadata Java nhưng filter vẫn có thể:

- Thiếu hoặc thừa dấu ngoặc.
- Dùng attribute không tồn tại trong schema.
- Dùng matching rule không được server hỗ trợ.
- Tìm sai naming context hoặc base DN.
- Bị từ chối do ACL hoặc quyền của bind account.

Startup không chứng minh server chấp nhận filter string hay schema. Hãy kiểm thử các query khai báo trên directory test đúng loại server/version mà ứng dụng sẽ triển khai. Việc Spring tạo được repository proxy không thay thế integration test.

## 7. Spring kiểm tra query method vào thời điểm nào?

Spring Data LDAP kích hoạt repository bằng `@EnableLdapRepositories` hoặc XML namespace. Cấu hình này quét package, phát hiện repository interface và đăng ký `LdapRepositoryFactoryBean` cho mỗi repository. Factory bean triển khai `InitializingBean`; khi khởi tạo, nó tạo repository factory và repository proxy theo vòng đời Spring Data.

Với singleton bean được khởi tạo eager mặc định, việc tạo repository xảy ra trong lúc `ApplicationContext` khởi động. Query method được phân giải ở giai đoạn tạo repository, nên lỗi property trong derived query có thể làm startup thất bại.

### 7.1. Cấu hình eager và lazy

Trong Spring, singleton bean thông thường được tạo eager. Nếu repository bean được đánh dấu lazy hoặc ứng dụng bật lazy initialization toàn cục, việc tạo repository có thể bị trì hoãn tới lần đầu bean được yêu cầu hoặc sử dụng. Khi đó lỗi query method có thể xuất hiện muộn hơn.

Không nên bật lazy chỉ để làm startup nhanh hơn rồi cho rằng các query method đã được kiểm tra. Nếu mục tiêu là fail fast, hãy bảo đảm repository được tạo trong test/startup validation.

Lưu ý riêng cho LDAP: `@EnableLdapRepositories` hiện cung cấp `queryLookupStrategy`, package scanning, `ldapTemplateRef` và các thuộc tính repository khác; API này **không có thuộc tính `bootstrapMode` như `@EnableJpaRepositories`**. Không sao chép cấu hình `bootstrapMode` từ ví dụ Spring Data JPA sang Spring Data LDAP.

### 7.2. Những gì được kiểm tra ở startup

Thông thường, quá trình tạo repository có thể phát hiện:

- Repository interface không được cấu hình/scan đúng.
- Không tìm được `LdapTemplate` hoặc bean phụ thuộc cần thiết.
- Entity ODM hoặc metadata ID không hợp lệ.
- Tên query method không thể phân tích.
- Property path không tồn tại trong domain class.
- Query lookup strategy không tìm được declared query theo cấu hình.
- Một số lỗi cấu trúc method/parameter khi query được tạo.

### 7.3. Những gì cần kiểm thử khi gửi query tới LDAP

Startup không chứng minh:

- LDAP server đang chạy và có thể kết nối.
- TLS certificate và hostname hợp lệ.
- Base DN và naming context tồn tại.
- LDAP attribute được khai báo trong schema server.
- `objectClass` và matching rule phù hợp.
- Bind account có quyền search/read.
- Filter `@Query` được server chấp nhận.
- Referral, size limit, time limit và kết quả mapping hoạt động như mong đợi.

Đây là lý do cần cả **repository bootstrap test** và **LDAP integration test**.

## 8. Chẩn đoán lỗi khởi tạo repository

Lỗi ngoài cùng thường là `BeanCreationException` hoặc lỗi phụ thuộc bean. Hãy tìm exception sâu nhất liên quan đến repository/query method.

| Dấu hiệu | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `No property 'surnmae' found for type 'Person'` | Gõ sai property Java. | Sửa method thành `findBySurname`. |
| `No property 'mail' found for type 'Person'` | Dùng LDAP attribute name thay cho Java property. | Dùng `findByEmailAddress` nếu property `emailAddress` được ánh xạ tới `mail`. |
| `No property 'department' found for type 'Person'` | Entity không có property hoặc path được mô tả. | Kiểm tra entity và đường dẫn property thực tế. |
| Property path bị phân giải sai | Tên camelCase nhập nhằng với một property khác. | Dùng `_` để xác định ranh giới, ví dụ `findByAddress_ZipCode`. |
| `findById` tìm sai dữ liệu | Nhầm method dành riêng cho ID DN với property `id`. | Dùng `findPersonById` cho property Java tên `id`. |
| Query không có declared definition | Chọn `USE_DECLARED_QUERY` nhưng method thiếu `@Query`/named query. | Khai báo query hoặc dùng chiến lược phù hợp. |
| Filter bị từ chối lúc thực thi | `@Query` sai cú pháp hoặc filter không phù hợp server. | Kiểm thử filter trên LDAP test server; xem result code. |
| Lỗi filter/schema từ LDAP server | Attribute không tồn tại, matching rule không phù hợp hoặc filter không hợp lệ. | Kiểm tra schema, tên attribute và diagnostic của server. |
| `InsufficientAccessRights` | Bind account thiếu quyền. | Kiểm tra ACL, không sửa tên method để che lỗi quyền. |

Spring Data Commons có `QueryCreationException` để biểu diễn lỗi không thể tạo query từ một method. Lỗi này có thể được bọc bởi exception tạo bean của Spring. Với lỗi property, thông báo thường nêu property không tìm thấy và domain type tương ứng.

### 8.1. Quy trình đọc stack trace

1. Tìm repository interface và method có tên trong thông báo.
2. Đọc property đầu tiên bị báo không tìm thấy.
3. So sánh với property Java trong entity ODM, không so sánh trực tiếp với LDAP attribute name.
4. Kiểm tra `@Attribute(name = "...")` và `@Id`.
5. Kiểm tra phần sau `By`, `And`, `Or`, operator và số tham số.
6. Kiểm tra query lookup strategy nếu lỗi nói không tìm được declared query.
7. Nếu repository đã khởi tạo nhưng method lỗi khi gọi, kiểm tra filter, base DN, schema, ACL và directory server.

Không bắt mọi exception rồi bỏ qua để ứng dụng tiếp tục khởi động. Một repository không được tạo có thể khiến service phụ thuộc bị thiếu và làm request lỗi muộn hơn.

## 9. Ví dụ sửa lỗi từ đầu đến cuối

Entity:

~~~java
@Entry(base = "ou=people", objectClasses = {
        "top", "person", "organizationalPerson", "inetOrgPerson"
})
public class Person {

    @Id
    private Name dn;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String emailAddress;

    @Attribute(name = "uid")
    private String username;
}
~~~

Repository có lỗi:

~~~java
public interface PersonRepository extends LdapRepository<Person> {

    List<Person> findBySurnmae(String surname);

    List<Person> findByMail(String mail);
}
~~~

Có hai vấn đề:

1. `Surnmae` bị gõ sai; property Java là `surname`.
2. `mail` là LDAP attribute được ánh xạ từ property Java `emailAddress`, không phải property Java trong entity.

Sửa:

~~~java
public interface PersonRepository extends LdapRepository<Person> {

    List<Person> findBySurname(String surname);

    List<Person> findByEmailAddress(String emailAddress);

    List<Person> findBySurnameAndUsername(
            String surname,
            String username);
}
~~~

Khi Spring tạo repository, nó có thể phân giải các property `surname`, `emailAddress` và `username` trên domain class. Nếu metadata đúng, repository proxy được tạo. Khi gọi `findByEmailAddress`, ODM sử dụng mapping `emailAddress` sang LDAP attribute `mail`.

Nếu query vẫn trả lỗi khi thực thi, hãy kiểm tra entry thực tế có `objectClass` phù hợp, attribute `mail` có trong schema và base `ou=people` có đúng với naming context của server.

## 10. Viết test để phát hiện lỗi trước khi triển khai

Nên chia test thành hai nhóm: kiểm tra repository có thể được tạo và kiểm tra query thực sự hoạt động với directory.

### 10.1. Repository bootstrap test

Một test Spring context đơn giản:

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class PersonRepositoryBootstrapTest {

    @Autowired
    private PersonRepository personRepository;

    @Test
    void repositoryIsCreatedWithValidQueryMethods() {
        assertNotNull(personRepository);
    }
}
~~~

Với repository singleton eager theo cấu hình mặc định, Spring phải tạo được repository trước khi test chạy. Nếu một derived query chứa property sai, context có thể thất bại ngay ở bước khởi tạo, khiến test không chạy tới assertion.

Test này kiểm tra cấu trúc và metadata repository. Nó không bắt buộc thực hiện LDAP search. Tuy nhiên, nếu ứng dụng bật lazy initialization hoặc repository được đánh dấu lazy, chỉ inject bean có thể chưa kích hoạt tạo repository thực tế. Trong test fail-fast, hãy dùng cấu hình eager và tránh lazy initialization toàn cục.

### 10.2. Kiểm thử repository có method sai

Có thể tạo một repository interface riêng trong test fixture với method cố ý sai:

~~~java
interface BrokenPersonRepository extends LdapRepository<Person> {

    List<Person> findBySurnmae(String surname);
}
~~~

Đăng ký riêng interface này trong một test application context. Kỳ vọng context khởi tạo thất bại và root cause chỉ ra property `surnmae` không tồn tại trên `Person`. Không đưa repository cố ý sai vào package scan của ứng dụng production.

Mục đích của test là chứng minh pipeline bootstrap phát hiện lỗi property. Không cần gọi method trên LDAP server để kiểm tra lỗi này.

### 10.3. LDAP integration test

Dùng LDAP server test/embedded directory hoặc Testcontainers với fixture do test quản lý. Nạp một entry:

~~~ldif
dn: uid=lan.nguyen,ou=people,dc=example,dc=com
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan.nguyen
sn: Nguyen
mail: lan.nguyen@example.com
~~~

Sau đó gọi repository:

~~~java
@Test
void derivedQueryUsesMappedLdapAttribute() {
    List<Person> result =
            personRepository.findByEmailAddress("lan.nguyen@example.com");

    assertEquals(1, result.size());
    assertEquals("lan.nguyen", result.get(0).getUsername());
}
~~~

Test này kiểm tra đồng thời:

- Repository method đã được parse.
- Property Java `emailAddress` được ánh xạ sang LDAP attribute `mail`.
- Base DN và scope tìm kiếm phù hợp.
- Server chấp nhận filter và bind account có quyền.
- Kết quả LDAP được map thành `Person`.

Với `@Query`, cần có integration test tương tự để xác minh filter khai báo. Nếu dùng ký tự đặc biệt, kiểm tra thêm encoding tham số và không dùng dữ liệu production.

### 10.4. Ma trận kiểm thử đề xuất

| Loại kiểm tra | Trường hợp | Kết quả mong đợi |
| --- | --- | --- |
| Bootstrap | Property Java hợp lệ. | Repository được tạo. |
| Bootstrap | Property bị gõ sai. | Context thất bại, báo property không tồn tại. |
| Bootstrap | Property LDAP attribute khác tên Java property. | Method phải dùng tên property Java. |
| Bootstrap | `findById` trùng tên method dành riêng. | Query nhắm ID DN; không nhầm với property `id`. |
| Bootstrap | `USE_DECLARED_QUERY` nhưng method thiếu query khai báo. | Repository khởi tạo thất bại. |
| Bootstrap | Property path nhập nhằng. | Dùng `_` để xác định ranh giới. |
| Integration | Attribute tồn tại và ACL cho phép. | Query trả entry đúng. |
| Integration | Attribute không tồn tại trong schema. | Server trả lỗi hoặc không match theo server. |
| Integration | Bind account thiếu quyền. | Search bị từ chối hoặc kết quả bị giới hạn theo ACL. |
| Integration | Filter `@Query` không hợp lệ. | Query thất bại khi thực thi. |
| Integration | Ký tự đặc biệt trong tham số. | Giá trị được encode đúng, không mở rộng filter ngoài ý muốn. |
| Integration | Base DN không tồn tại. | Kết quả/lỗi theo server; không giả định startup đã kiểm tra base. |

## 11. Checklist review trước khi merge

- [ ] Repository interface nằm trong package được `@EnableLdapRepositories` scan.
- [ ] Repository extends `LdapRepository<Entity>` hoặc kiểu repository phù hợp.
- [ ] Entity được ánh xạ bằng Spring LDAP ODM (`@Entry`, `@Attribute`, `@Id`).
- [ ] ID của entity là DN kiểu `javax.naming.Name`.
- [ ] Mọi property trong derived query đều tồn tại trên Java domain class.
- [ ] Tên method dùng Java property, không dùng nhầm LDAP attribute name.
- [ ] Phần `By`, `And`, `Or` và operator viết đúng.
- [ ] Số lượng và kiểu tham số khớp predicate.
- [ ] `findById` được hiểu là truy vấn theo ID DN.
- [ ] Không dùng các toán tử chung của JPA mà Spring Data LDAP không hỗ trợ.
- [ ] Không kỳ vọng paging/sorting repository như các store khác.
- [ ] `queryLookupStrategy` phù hợp với việc dùng derived query hay declared query.
- [ ] `@Query` có named/positional binding rõ ràng và encoding được kiểm thử.
- [ ] Repository bootstrap test chạy với cấu hình eager.
- [ ] LDAP integration test xác minh filter, schema, ACL, base DN và mapping.

## 12. Bài tập tình huống

Một ứng dụng quản lý nhân viên có entity:

~~~java
@Entry(base = "ou=employees",
       objectClasses = {"top", "person", "organizationalPerson", "inetOrgPerson"})
public class Employee {

    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String username;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String emailAddress;

    @Attribute(name = "employeeNumber")
    private String employeeNumber;
}
~~~

Repository:

~~~java
public interface EmployeeRepository extends LdapRepository<Employee> {

    List<Employee> findBySn(String surname);

    List<Employee> findByEmail(String email);

    Optional<Employee> findById(String id);

    List<Employee> findByEmployeeNumberAndSurnmae(
            String employeeNumber,
            String surname);
}
~~~

Ứng dụng dừng khi khởi động với lỗi query creation. Nhóm phát triển cho rằng LDAP server bị lỗi vì `sn`, `mail` và `employeeNumber` đều có trong schema.

**Yêu cầu:**

1. Xác định những method nào đang dùng sai tên property Java.
2. Vì sao `sn` và `mail` có trong LDAP schema nhưng method `findBySn`/`findByEmail` vẫn có thể không hợp lệ?
3. `findById` nhắm tới property nào trong Spring Data LDAP?
4. Viết lại repository đúng theo entity đã cho.
5. Nếu muốn dùng filter tùy chỉnh trực tiếp trên LDAP attribute `mail`, có thể dùng annotation nào?
6. Nếu chọn `USE_DECLARED_QUERY`, điều gì xảy ra với method không có `@Query` hoặc named query?
7. Một repository bootstrap test chứng minh được điều gì? Nó không chứng minh được điều gì?
8. Cần những integration test nào để xác minh filter và mapping thực tế?
9. Nếu bật lazy initialization toàn cục, tại sao lỗi method có thể xuất hiện muộn?
10. Vì sao không nên sửa lỗi bằng cách bỏ qua exception tạo repository?

**Gợi ý đáp án:**

- Entity có property Java `surname`, `emailAddress`, `username` và `employeeNumber`; không có `sn` hay `email`.
- `@Attribute` ánh xạ property Java sang LDAP attribute. Derived query dùng tên property Java.
- `findById` là method dành riêng cho ID DN (`Name`), không phải property `id` thông thường.
- Repository đúng có thể dùng `findBySurname`, `findByEmailAddress`, `findByEmployeeNumberAndSurname`.
- `@Query` cho phép khai báo filter trực tiếp; tham số có thể đặt tên hoặc theo vị trí.
- `USE_DECLARED_QUERY` yêu cầu query khai báo cho method; thiếu query làm repository bootstrap thất bại.
- Bootstrap test xác minh repository/query metadata có thể được tạo; nó không chứng minh LDAP schema, ACL, TLS hoặc filter được server chấp nhận.
- Integration test phải chạy với directory test, fixture, base DN và bind identity tương ứng.
- Lazy initialization có thể dời thời điểm tạo repository tới lần sử dụng đầu tiên.
- Bỏ qua exception sẽ che lỗi cấu hình và đẩy sự cố tới thời điểm request thật.

## 13. Ghi nhớ

**Spring Data LDAP kiểm tra query method dựa trên domain metadata khi repository được tạo.** Derived query phải dùng tên property Java trong entity ODM; `@Attribute` mới ánh xạ property đó tới LDAP attribute. Khi repository được khởi tạo eager mặc định, lỗi property hoặc query definition có thể làm Spring context thất bại ngay khi startup.

`CREATE_IF_NOT_FOUND` là query lookup strategy mặc định; `CREATE` luôn derive từ tên method; `USE_DECLARED_QUERY` yêu cầu query khai báo. Hãy đọc exception gốc, sửa property path, tham số và mapping. Sau đó chạy LDAP integration test để xác minh filter, schema, ACL, base DN và matching rule trên server thật. Một repository proxy được tạo thành công mới xác nhận metadata query hợp lệ; nó chưa xác nhận directory sẽ thực thi truy vấn thành công.

### Tài liệu tham khảo

- [Spring Data LDAP — Query Methods](https://docs.spring.io/spring-data/ldap/reference/ldap/query-methods.html)
- [Spring Data LDAP — Defining Query Methods](https://docs.spring.io/spring-data/ldap/reference/repositories/query-methods-details.html)
- [Spring Data LDAP — Configuration](https://docs.spring.io/spring-data/ldap/reference/ldap/configuration.html)
- [Spring Data LDAP — EnableLdapRepositories API](https://docs.spring.io/spring-data/ldap/reference/api/java/org/springframework/data/ldap/repository/config/EnableLdapRepositories.html)
- [Spring Data LDAP — LdapRepositoryFactoryBean API](https://docs.spring.io/spring-data/ldap/reference/api/java/org/springframework/data/ldap/repository/support/LdapRepositoryFactoryBean.html)
- [Spring Data Commons — QueryCreationException API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/repository/query/QueryCreationException.html)
- [Spring Data Commons — PartTree source](https://github.com/spring-projects/spring-data-commons/blob/main/src/main/java/org/springframework/data/repository/query/parser/PartTree.java)
- [Spring LDAP — Object-Directory Mapping](https://docs.spring.io/spring-ldap/reference/odm.html)
- [RFC 4515 — LDAP Search Filter String Representation](https://www.rfc-editor.org/rfc/rfc4515)
