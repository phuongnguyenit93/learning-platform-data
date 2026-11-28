# Chọn kiểu kết quả đơn hoặc tập hợp và xử lý sai số lượng

Trong chương **Truy vấn Repository** của **SPRING_DATA_LDAP**, một phương thức repository không chỉ mô tả điều kiện tìm kiếm mà còn công bố **hợp đồng về số lượng entry có thể trả về**. Khi tìm một nhân viên theo UID, ứng dụng thường mong đợi không có hoặc đúng một entry. Khi tìm người trong một phòng ban, ứng dụng có thể mong đợi không có, một hoặc nhiều entry. Chọn **Optional<Person>** hay **List<Person>** vì thế là quyết định về tính đúng đắn của nghiệp vụ, không chỉ là sở thích cú pháp Java.

Ví dụ, **uid** có thể được quy ước duy nhất trong nhánh **ou=people**. Nếu truy vấn theo UID trả về hai entry, đó là dấu hiệu dữ liệu hoặc phạm vi tìm kiếm có vấn đề. Nếu repository trả **List<Person>** rồi code lấy phần tử đầu tiên, ứng dụng có thể âm thầm chọn nhầm người. Ngược lại, nếu truy vấn theo **departmentNumber** dùng **Optional<Person>**, một phòng ban có nhiều nhân viên sẽ làm phát sinh lỗi sai số lượng.

Spring Data LDAP cung cấp các kiểu trả về quen thuộc của Spring Data và các phương thức LDAP riêng như **LdapRepository.findOne(LdapQuery)** và **findAll(LdapQuery)**. Kiểu trả về đơn biểu thị tối đa một entry; kiểu tập hợp biểu thị không hoặc nhiều entry. Khi một truy vấn đơn khớp nhiều entry, Spring Data báo **IncorrectResultSizeDataAccessException** thay vì tự chọn một entry bất kỳ.

**Mục tiêu:** hiểu cardinality của truy vấn LDAP; chọn **Optional<T>**, **T** hay **List<T>** đúng với nghiệp vụ; phân biệt không tìm thấy với trùng lặp và lỗi directory; xử lý **IncorrectResultSizeDataAccessException**; dùng **findOne**/**findAll** với **LdapQuery**; xác định phạm vi uniqueness theo base DN và scope; tránh che lỗi bằng **First**/**Top**; và kiểm thử đủ trường hợp 0, 1, nhiều entry cùng các lỗi Search.

## 1. Cardinality là số entry khớp truy vấn

Cardinality mô tả số entry mà một LDAP Search khớp trong **base DN, scope và filter đã chọn**:

| Cardinality | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **0** | Không có entry khớp trong phạm vi truy vấn | UID lan không tồn tại dưới ou=people |
| **1** | Có đúng một entry khớp | Chỉ một nhân viên có UID lan trong nhánh people |
| **Nhiều hơn 1** | Có từ hai entry trở lên khớp | Hai OU con chứa entry có cùng UID lan |

Đây là số **entry**, không phải số giá trị attribute. Một entry có thể có nhiều giá trị **mail**, **telephoneNumber** hoặc **member**; điều đó không làm số entry của Search tăng lên. Ngược lại, hai entry khác DN cùng khớp **(mail=shared@example.org)** là cardinality bằng hai dù mỗi entry chỉ có một giá trị mail.

### 1.1. Cùng một filter có thể có cardinality khác nhau theo base/scope

Giả sử directory có:

~~~ldif
dn: uid=lan,ou=engineering,ou=people,dc=example,dc=org
objectClass: top
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen

dn: uid=lan,ou=contractors,ou=people,dc=example,dc=org
objectClass: top
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen (Contractor)
~~~

Filter **(uid=lan)** không tự bảo đảm duy nhất:

- Search base **ou=engineering,ou=people,...** với scope subtree có thể trả một entry.
- Search base **ou=people,...** với scope subtree có thể trả hai entry.
- Search base **dc=example,dc=org** với scope subtree có thể trả thêm entry từ các nhánh khác.

Vì vậy, khi nói “UID là duy nhất”, phải nói rõ **duy nhất trong naming context/base DN nào và theo quy tắc nào**.

### 1.2. Repository không tự tạo ràng buộc uniqueness cho attribute

Kiểu trả về **Optional<Person>** không biến LDAP attribute thành unique constraint. Nó nói rằng code mong đợi tối đa một entry và Spring Data sẽ báo lỗi nếu truy vấn thực tế trả nhiều entry.

Tính duy nhất cần được bảo đảm bởi thiết kế directory/provisioning hoặc quy tắc nghiệp vụ, ví dụ:

- Chỉ cấp UID duy nhất trong toàn bộ ou=people.
- Tách tenant bằng các naming context riêng.
- Tìm theo cả UID và tenant/OU.
- Dùng DN hoặc định danh ổn định khi nghiệp vụ cần xác định một entry cụ thể.
- Có quy trình phát hiện và sửa dữ liệu trùng.

Không dựa vào việc “trước giờ Search chỉ trả một kết quả” để coi uniqueness đã được bảo đảm.

## 2. Chọn kiểu trả về theo hợp đồng nghiệp vụ

Ba lựa chọn thường gặp:

| Kiểu trả về | Khi không có entry | Khi có một entry | Khi có nhiều entry |
| --- | --- | --- | --- |
| **T** | Trả null | Trả entity | Ném IncorrectResultSizeDataAccessException |
| **Optional<T>** | Optional.empty() | Optional.of(entity) | Ném IncorrectResultSizeDataAccessException |
| **List<T>** | Danh sách rỗng | Danh sách một phần tử | Danh sách nhiều phần tử |

Với lookup tùy chọn theo một định danh được kỳ vọng duy nhất, **Optional<T>** thường là lựa chọn dễ đọc nhất. Với truy vấn danh sách, dùng **List<T>**. Tránh dùng **T** nullable nếu không có lý do tương thích cụ thể, vì caller phải tự nhớ kiểm tra null.

### 2.1. Optional<T>: không có hoặc tối đa một entry

Ví dụ:

~~~java
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository
        extends LdapRepository<PersonEntry> {

    Optional<PersonEntry> findByLoginName(String loginName);
}
~~~

Hợp đồng của phương thức:

- Không tìm thấy entry: **Optional.empty()**.
- Tìm thấy đúng một entry: Optional chứa entity.
- Có nhiều entry khớp: **IncorrectResultSizeDataAccessException**.

Đây là lựa chọn phù hợp nếu loginName phải xác định tối đa một người trong phạm vi repository. Optional biểu đạt trường hợp “không có” tường minh và giúp caller không vô tình dereference null.

### 2.2. T: một entity hoặc null

Ví dụ:

~~~java
public interface LegacyPersonRepository
        extends LdapRepository<PersonEntry> {

    PersonEntry findByLoginName(String loginName);
}
~~~

Kiểu T có cùng giả định cardinality tối đa một:

- Không có entry: trả null.
- Có một entry: trả entity.
- Nhiều entry: ném **IncorrectResultSizeDataAccessException**.

Caller phải kiểm tra:

~~~java
PersonEntry person = repository.findByLoginName(loginName);
if (person == null) {
    // Không tìm thấy.
}
~~~

Với code mới, ưu tiên Optional<T> để thể hiện trường hợp vắng mặt ngay trong chữ ký method. Không dùng primitive hoặc wrapper kiểu số/boolean để biểu diễn một entity đơn nếu mục đích thật sự là tìm entry.

### 2.3. List<T>: không có hoặc nhiều entry

Ví dụ:

~~~java
import java.util.List;

public interface PersonRepository
        extends LdapRepository<PersonEntry> {

    List<PersonEntry> findByDepartmentNumber(String departmentNumber);
}
~~~

Hợp đồng:

- Không có entry: danh sách rỗng.
- Có một entry: danh sách có một phần tử.
- Có nhiều entry: danh sách chứa các entry khớp.

Đây là lựa chọn đúng cho truy vấn theo phòng ban, nhóm, trạng thái hoặc một thuộc tính không có ràng buộc duy nhất.

Không trả null để biểu diễn “không có kết quả” cho một method collection. Caller nên nhận danh sách rỗng và xử lý bằng **isEmpty()**.

## 3. Ví dụ entity và repository hoàn chỉnh

Một entity đơn giản:

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
public class PersonEntry {
    @Id
    private Name dn;

    @Attribute(name = "uid")
    private String loginName;

    @Attribute(name = "cn")
    private String commonName;

    @Attribute(name = "sn")
    private String surname;

    @Attribute(name = "mail")
    private String email;

    @Attribute(name = "departmentNumber")
    private String departmentNumber;

    public PersonEntry() {}

    public Name getDn() {
        return dn;
    }

    public String getLoginName() {
        return loginName;
    }

    public String getCommonName() {
        return commonName;
    }

    public String getEmail() {
        return email;
    }

    public String getDepartmentNumber() {
        return departmentNumber;
    }
}
~~~

Repository khai báo hai hợp đồng khác nhau:

~~~java
import java.util.List;
import java.util.Optional;
import org.springframework.data.ldap.repository.LdapRepository;

public interface PersonRepository
        extends LdapRepository<PersonEntry> {

    // loginName được quy ước duy nhất trong phạm vi people.
    Optional<PersonEntry> findByLoginName(String loginName);

    // Một phòng ban có thể có nhiều nhân viên.
    List<PersonEntry> findByDepartmentNumber(String departmentNumber);

    // Email có thể dùng chung trong dữ liệu import cũ.
    List<PersonEntry> findByEmail(String email);
}
~~~

Tên property trong method là tên property Java của entity. Mapping **@Attribute(name = "uid")** liên kết **loginName** với attribute LDAP **uid**; method **findByLoginName** không đòi hỏi schema LDAP phải có attribute tên loginName.

Đây là một hợp đồng thiết kế minh họa. Nếu hệ thống thực tế cho phép email duy nhất, có thể chọn Optional<PersonEntry> cho email sau khi đã có quy tắc uniqueness và dữ liệu được kiểm soát. Đừng suy ra cardinality chỉ từ tên attribute.

## 4. LdapRepository.findOne và findAll

Ngoài derived query methods, **LdapRepository** có các phương thức LDAP-specific nhận **LdapQuery**:

- **findOne(LdapQuery)**: trả **Optional<T>**, kỳ vọng tối đa một entry; nếu nhiều entry khớp thì ném **IncorrectResultSizeDataAccessException**.
- **findAll(LdapQuery)**: trả **List<T>** chứa các entry khớp.

Ví dụ:

~~~java
import java.util.List;
import java.util.Optional;
import org.springframework.ldap.query.LdapQuery;
import org.springframework.ldap.query.LdapQueryBuilder;
import org.springframework.ldap.query.SearchScope;

LdapQuery query = LdapQueryBuilder.query()
    .base("ou=people")
    .searchScope(SearchScope.SUBTREE)
    .where("objectClass").is("inetOrgPerson")
    .and("uid").is("lan");

Optional<PersonEntry> one = personRepository.findOne(query);
List<PersonEntry> all = personRepository.findAll(query);
~~~

Hai lời gọi minh họa hai hợp đồng khác nhau. Không cần chạy cả hai cho cùng một request trong production; chọn một theo nhu cầu nghiệp vụ.

### 4.1. Dùng findOne khi nhiều kết quả là lỗi dữ liệu

Nếu ứng dụng cần một người theo login name:

~~~java
public PersonEntry requireUniquePerson(String loginName) {
    LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .where("objectClass").is("inetOrgPerson")
        .and("uid").is(loginName);

    return personRepository.findOne(query)
        .orElseThrow(() ->
            new PersonNotFoundException(loginName)
        );
}
~~~

Trường hợp:

- Không có entry: orElseThrow chuyển thành lỗi nghiệp vụ not-found.
- Có một entry: trả entity.
- Có nhiều entry: findOne ném IncorrectResultSizeDataAccessException; không chạy tới orElseThrow.

Đừng bắt ngoại lệ sai số lượng rồi trả Optional.empty(). Làm như vậy biến lỗi dữ liệu trùng thành “không tìm thấy”, che mất nguyên nhân thật.

### 4.2. Dùng findAll khi nhiều kết quả là bình thường

~~~java
public List<PersonEntry> findPeopleInDepartment(String departmentNumber) {
    LdapQuery query = LdapQueryBuilder.query()
        .base("ou=people")
        .searchScope(SearchScope.SUBTREE)
        .where("objectClass").is("inetOrgPerson")
        .and("departmentNumber").is(departmentNumber);

    return personRepository.findAll(query);
}
~~~

Không có nhân viên trong phòng ban sẽ trả danh sách rỗng. Có một hoặc nhiều nhân viên đều là kết quả hợp lệ.

## 5. Xử lý ba trường hợp 0, 1 và nhiều entry

Một số use case cần phân biệt rõ:

- Không tồn tại.
- Tồn tại duy nhất.
- Dữ liệu bị trùng và cần điều tra.

Với lookup định danh, dùng **findOne** là cách trực tiếp:

~~~java
import org.springframework.dao.IncorrectResultSizeDataAccessException;

public PersonEntry lookupUniqueLogin(String loginName) {
    try {
        return personRepository.findOne(buildLoginQuery(loginName))
            .orElse(null);
    } catch (IncorrectResultSizeDataAccessException ex) {
        throw new DuplicateDirectoryIdentityException(
            "Login name is not unique in the configured search scope",
            ex
        );
    }
}
~~~

Trong ví dụ:

- null chỉ được trả khi Search thành công nhưng không có entry.
- Một entry được trả khi duy nhất.
- Nhiều entry trở thành lỗi miền riêng **DuplicateDirectoryIdentityException**.
- Lỗi kết nối, TLS, Bind, ACL hoặc timeout tiếp tục được xử lý như lỗi dependency; không đổi thành not-found.

Tên exception miền là ví dụ do ứng dụng định nghĩa. Có thể dùng trực tiếp IncorrectResultSizeDataAccessException ở tầng service nếu không cần abstraction riêng.

### 5.1. Khi cần tự phân loại số lượng

Nếu cần lấy danh sách để hiển thị hoặc ghi audit số lượng khớp, dùng findAll:

~~~java
List<PersonEntry> matches =
    personRepository.findAll(buildLoginQuery(loginName));

if (matches.isEmpty()) {
    // 0 entry
} else if (matches.size() == 1) {
    // Đúng 1 entry
    PersonEntry person = matches.get(0);
} else {
    // Nhiều entry: dữ liệu ambiguous
}
~~~

Đây là cách dễ hiểu nhưng có thể tải toàn bộ kết quả nếu phạm vi truy vấn quá rộng. Với dữ liệu lớn, thu hẹp base/scope/filter và dùng giới hạn Search đã được kiểm chứng với server/provider. Nếu server báo size limit hoặc kết quả partial, không được coi danh sách nhận được là toàn bộ cardinality.

### 5.2. Giới hạn hai kết quả để phát hiện trùng

Về mặt logic, nếu mục tiêu chỉ là phân biệt 0, 1 hay “ít nhất 2”, chỉ cần tối đa hai entry:

~~~java
LdapQuery query = LdapQueryBuilder.query()
    .base("ou=people")
    .searchScope(SearchScope.SUBTREE)
    .countLimit(2)
    .where("objectClass").is("inetOrgPerson")
    .and("uid").is(loginName);
~~~

**countLimit(2)** yêu cầu giới hạn số entry được trả về. Cần kiểm tra hành vi **SizeLimitExceededException**/partial result của Spring LDAP, JNDI provider và LDAP server đang triển khai. Nếu giới hạn bị chạm và provider báo lỗi kèm partial result, phải xử lý theo contract đó; không bắt lỗi rồi giả định đã có danh sách đầy đủ.

Với phần lớn lookup đơn, **findOne(LdapQuery)** đã biểu đạt đúng ý định và báo lỗi nếu nhiều entry khớp. Chỉ tự dùng countLimit khi cần kiểm soát chi phí Search và đã xác minh semantics trên server thực tế.

## 6. Không tìm thấy khác với lỗi truy vấn

**Optional.empty()** hoặc danh sách rỗng chỉ có ý nghĩa khi Search hoàn tất thành công và không có entry khớp trong phạm vi truy vấn.

| Tình huống | Có phải “không tìm thấy” không? | Cách xử lý |
| --- | --- | --- |
| Search thành công, 0 entry | Có | Trả empty/NotFound theo contract |
| Search thành công, 1 entry | Không | Trả entity |
| Search thành công, nhiều entry với kiểu đơn | Không | Xử lý duplicate/cardinality violation |
| Service Bind thất bại | Không | Xử lý credential/dependency |
| TLS handshake thất bại | Không | Xử lý certificate/transport |
| Search timeout | Không | Dependency timeout |
| Base DN không tồn tại | Không nhất thiết | Cấu hình base hoặc directory topology sai |
| ACL từ chối Search | Không | Quyền service account không đủ |
| Server trả size limit/partial result | Không thể kết luận | Xử lý partial/limit rõ ràng |
| Referral chưa được xử lý | Không thể kết luận toàn cây | Xác định referral policy/topology |

Một Search trả rỗng không chứng minh entry chắc chắn không tồn tại ở mọi nơi trong directory. Entry có thể nằm ngoài base DN, ngoài scope, ở naming context khác hoặc bị ACL che khuất.

### 6.1. Không bắt mọi exception rồi trả empty

Tránh:

~~~java
public Optional<PersonEntry> findSafely(String uid) {
    try {
        return repository.findByLoginName(uid);
    } catch (Exception ex) {
        return Optional.empty();
    }
}
~~~

Code này biến timeout, TLS failure, Bind failure, ACL denial và duplicate result thành “không tìm thấy”. Caller không thể phân biệt người dùng không tồn tại với directory đang lỗi.

Hãy bắt đúng exception ở đúng tầng. Chỉ chuyển lỗi sai cardinality thành duplicate-data error; chỉ chuyển kết quả Search thành công nhưng rỗng thành not-found.

## 7. Chọn kiểu trả về theo use case

| Use case | Kiểu trả về gợi ý | Lý do |
| --- | --- | --- |
| Tra cứu một người bằng login name duy nhất | **Optional<PersonEntry>** | 0 hoặc 1; duplicate phải phát hiện |
| Yêu cầu một entry bắt buộc phải có | **Optional<PersonEntry>** ở repository | Tách truy cập dữ liệu khỏi quy tắc bắt buộc của use case |
| Liệt kê nhân viên theo phòng ban | **List<PersonEntry>** | 0..N là bình thường |
| Tìm các group chứa một member | **List<GroupEntry>** | Một user có thể thuộc nhiều group |
| Tra cứu email có thể dùng chung | **List<PersonEntry>** | Không giả định email unique |
| Kiểm tra có ít nhất một entry | **boolean/exists query** nếu được store hỗ trợ | Không cần tải entity |
| Đếm số entry | **kiểu số/count query** nếu được store hỗ trợ | Không cần map toàn bộ entity |
| Lấy một kết quả có thứ tự theo nghiệp vụ | **kiểu đơn kết hợp limit/order rõ ràng** | Chỉ dùng khi “đầu tiên” có nghĩa nghiệp vụ |

Không chọn Optional chỉ vì API controller mong muốn một object. Trước tiên xác định dữ liệu LDAP có thể có bao nhiêu entry khớp.

## 8. First/Top không giống kiểm tra uniqueness

Spring Data có các từ khóa giới hạn như **First** và **Top** trong tên query method. Ví dụ:

~~~java
List<PersonEntry> findTop2ByDepartmentNumber(
    String departmentNumber
);
~~~

Các từ khóa này giới hạn số kết quả được lấy. Chúng hữu ích khi nghiệp vụ chỉ cần một tập con có giới hạn, nhưng **không chứng minh dữ liệu duy nhất**.

### 8.1. Vì sao findFirstByUid có thể che dữ liệu trùng?

Giả sử có hai entry:

~~~text
uid=lan,ou=engineering,ou=people,dc=example,dc=org
uid=lan,ou=contractors,ou=people,dc=example,dc=org
~~~

Nếu dùng **findFirstByLoginName("lan")**, ứng dụng chỉ lấy một kết quả đầu tiên theo cách truy vấn/provider xử lý. Nếu không có thứ tự được xác định, không nên giả định entry nào sẽ đứng đầu. Dù có thứ tự, method vẫn che việc có nhiều entry cùng UID.

Với login identity, cách đúng thường là:

- Dùng Optional<PersonEntry> hoặc findOne(query).
- Để duplicate làm phát sinh IncorrectResultSizeDataAccessException.
- Sửa dữ liệu hoặc thu hẹp phạm vi bằng tenant/base DN hợp lệ.

### 8.2. Khi nào First/Top hợp lý?

Ví dụ nghiệp vụ cần tối đa ba nhân viên mới nhất trong một phòng ban:

~~~java
List<PersonEntry> findTop3ByDepartmentNumberOrderByCreateTimestampDesc(
    String departmentNumber
);
~~~

Ý định ở đây là lấy một tập con có giới hạn, không phải chứng minh phòng ban chỉ có ba người. Cần kiểm tra property createTimestamp, khả năng sắp xếp và cú pháp derived query được Spring Data LDAP version đang dùng hỗ trợ. Không dựa vào thứ tự mặc định của LDAP Search; nếu thứ tự quan trọng, phải khai báo thứ tự và xác minh store support.

## 9. exists/count không thay thế truy vấn đơn khi cần entity

Một số repository infrastructure hỗ trợ các subject như **exists…By** và **count…By**. Ví dụ khái niệm:

~~~java
boolean existsByLoginName(String loginName);
long countByDepartmentNumber(String departmentNumber);
~~~

Ý nghĩa:

- exists trả lời có ít nhất một entry hay không.
- count trả lời số lượng entry theo truy vấn.

Chúng không trả entity và không tự chứng minh “đúng một entry” nếu caller chỉ kiểm tra boolean. Nếu existsByLoginName trả true, có thể có một hoặc nhiều entry.

Không nên viết hai truy vấn riêng existsByUid(uid) rồi findByUid(uid) nếu mục tiêu là lấy entity. Giữa hai truy vấn, directory có thể thay đổi; thêm một round trip cũng làm tăng latency. Dùng một truy vấn có hợp đồng cardinality phù hợp.

Store-specific support cho từng subject keyword có thể thay đổi theo phiên bản. Đối chiếu tài liệu Spring Data LDAP đúng phiên bản trước khi dùng exists, count, Top, First, Distinct hoặc các kiểu wrapper khác.

## 10. @Query cũng phải khai báo đúng cardinality

Khi derived query không đủ biểu đạt, **@Query** cho phép viết LDAP filter:

~~~java
import java.util.List;
import java.util.Optional;
import org.springframework.data.ldap.repository.Query;

public interface PersonRepository
        extends LdapRepository<PersonEntry> {

    @Query("(&(objectClass=inetOrgPerson)(uid=:uid))")
    Optional<PersonEntry> findUniqueByUid(String uid);

    @Query("(&(objectClass=inetOrgPerson)(departmentNumber=:department))")
    List<PersonEntry> findPeopleByDepartment(String department);
}
~~~

Filter giống nhau vẫn có thể trả về 0, 1 hoặc nhiều entry. Kiểu trả về quyết định cách framework xử lý cardinality:

- Optional<PersonEntry>: tối đa một; nhiều hơn một là lỗi.
- List<PersonEntry>: 0..N.

### 10.1. Named và positional parameters

Spring Data LDAP hỗ trợ named parameters có tiền tố **:** và positional parameters dạng **?0**, **?1**, … trong **@Query**. Named parameters thường dễ đọc hơn khi method có nhiều tham số:

~~~java
@Query("(&(objectClass=inetOrgPerson)(uid=:uid)(mail=:email))")
Optional<PersonEntry> findByUidAndEmail(
    String uid,
    String email
);
~~~

Đảm bảo parameter name được nhận diện theo cấu hình build/runtime phù hợp. Nếu cần chỉ định tên tham số tường minh, dùng cơ chế **@Param** theo phiên bản Spring Data Commons đang dùng.

### 10.2. Parameter encoding và SpEL

Theo tài liệu Spring Data LDAP:

- Tham số của string-based @Query được encode theo RFC 2254.
- Có thể chỉ định encoder riêng bằng @LdapEncode cho tham số cần encoding tùy chỉnh.
- @LdapEncode không áp dụng cho derived queries hoặc Value Expressions.
- Giá trị đưa vào qua SpEL/property placeholders không tự được encode theo RFC 2254; phải bảo đảm escape đúng, ví dụ dùng LdapEncoder phù hợp.

Không nối raw username/email vào filter string. Cú pháp filter LDAP và DN có quy tắc escaping riêng; encoding filter không phải DN escaping.

## 11. Phạm vi tìm kiếm quyết định uniqueness

Để hiểu một method đơn có hợp lý không, phải kiểm tra:

1. @Entry.base hoặc base search được cấu hình.
2. Search scope: OBJECT, ONELEVEL hay SUBTREE.
3. Điều kiện objectClass và các filter criteria.
4. Naming context/tenant mà repository đang truy cập.
5. Quy tắc uniqueness do directory/provisioning bảo đảm.

Ví dụ:

~~~text
Base:  ou=people,dc=example,dc=org
Scope: SUBTREE
Filter: (&(objectClass=inetOrgPerson)(uid=lan))
~~~

Optional<PersonEntry> chỉ đúng nếu trong toàn subtree đó có tối đa một entry có UID lan. Nếu UID chỉ unique trong từng OU, query này có thể trả nhiều entry. Khi đó, cần thêm tiêu chí OU/tenant hoặc đổi base DN theo context đã xác thực.

### 11.1. Không dùng filter để che namespace sai

Nếu ứng dụng tìm theo UID trong nhiều tenant nhưng không thêm tenant/base context, việc chuyển sang findFirstByUid không sửa được mô hình dữ liệu. Nó chỉ che sự mơ hồ.

Hãy chọn một trong các chiến lược:

- Repository/ContextSource riêng cho từng naming context.
- Base DN được xác định từ tenant context đã được xác thực.
- Filter thêm thuộc tính namespace/tenant nếu schema hỗ trợ.
- Định danh duy nhất toàn directory được provisioning kiểm soát.

Không để client tùy ý gửi base DN hoặc raw filter để chọn phạm vi directory.

### 11.2. Matching rule và giá trị trùng

Hai giá trị nhìn giống nhau bằng mắt chưa chắc được server so khớp như nhau; matching rule của attribute schema quyết định semantics. Ví dụ, attribute có thể dùng case-ignore equality, case-exact equality hoặc matching rule chuyên biệt.

Không tự lowercase/trim giá trị để “đảm bảo unique” nếu chưa xác định matching rule. Query cardinality là cardinality theo kết quả server trả về, không phải số chuỗi khác nhau theo phép so sánh Java tự đặt.

## 12. Cardinality và dữ liệu đa trị

LDAP có thể lưu nhiều giá trị trong một attribute:

~~~ldif
dn: uid=lan,ou=people,dc=example,dc=org
objectClass: top
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen
mail: lan@example.org
mail: lan.nguyen@example.org
~~~

Đây vẫn là **một entry**. Nếu Search (uid=lan) trả entry này, cardinality là một, dù attribute mail có hai giá trị.

Ngược lại:

~~~ldif
dn: uid=lan,ou=engineering,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
uid: lan

dn: uid=lan,ou=contractors,ou=people,dc=example,dc=org
objectClass: inetOrgPerson
uid: lan
~~~

Đây là hai entry khác nhau cùng khớp UID. Kiểu trả về đơn sẽ phát hiện lỗi cardinality.

Khi map attribute đa trị sang collection trong entity, cần kiểm tra kiểu field và khả năng mapping của Spring LDAP ODM đang dùng. Không suy ra collection field có nghĩa repository method phải trả List<Entity>.

## 13. Xử lý IncorrectResultSizeDataAccessException

**IncorrectResultSizeDataAccessException** báo rằng operation mong đợi một số lượng kết quả nhất định nhưng thực tế không đáp ứng. Với query method đơn, trường hợp thường gặp là nhiều hơn một entry.

### 13.1. Xử lý ở service boundary

~~~java
import org.springframework.dao.IncorrectResultSizeDataAccessException;
import org.springframework.stereotype.Service;

@Service
public class PersonLookupService {
    private final PersonRepository repository;

    public PersonLookupService(PersonRepository repository) {
        this.repository = repository;
    }

    public PersonEntry getByLoginName(String loginName) {
        try {
            return repository.findByLoginName(loginName)
                .orElseThrow(() ->
                    new PersonNotFoundException(loginName)
                );
        } catch (IncorrectResultSizeDataAccessException ex) {
            throw new DuplicateDirectoryIdentityException(
                "Login name resolves to multiple LDAP entries",
                ex
            );
        }
    }
}
~~~

Tầng service chuyển lỗi persistence thành lỗi miền để API hoặc job có thể xử lý nhất quán. Không trả một entry bất kỳ khi có duplicate.

### 13.2. Không trả lỗi chi tiết cho người dùng cuối

Trong API công khai, tránh tiết lộ toàn bộ DN của các entry trùng hoặc thông tin cá nhân trong exception message. Có thể:

- Trả lỗi chung như “Không thể xác định duy nhất tài khoản”.
- Ghi log nội bộ có kiểm soát, kèm correlation ID.
- Gửi cảnh báo data quality cho đội vận hành.
- Ghi DN/identifier chi tiết trong audit channel được phân quyền, nếu chính sách cho phép.

Không log password, Bind credential hoặc toàn bộ attribute nhạy cảm để chẩn đoán duplicate.

### 13.3. Duplicate identity trong luồng authentication

Nếu UID đăng nhập khớp nhiều entry:

1. Không lấy entry đầu tiên.
2. Không thử Bind tuần tự với password người dùng trên tất cả entry.
3. Không tự chọn entry theo thứ tự server trả về.
4. Dừng luồng xác thực và ghi nhận lỗi cấu hình/dữ liệu.
5. Sửa uniqueness hoặc naming context.

Việc thử Bind trên nhiều DN có thể làm tăng lockout counter, tạo hành vi khác nhau giữa account và gây rò rỉ thông tin. Identity phải được resolve duy nhất trước khi xác thực.

## 14. Khi nào dùng Optional, khi nào dùng List?

Hãy hỏi theo thứ tự:

**Câu 1: Nghiệp vụ có cho phép nhiều entry khớp không?**

- Có: dùng List<T> hoặc collection type được store hỗ trợ.
- Không: chuyển sang câu 2.

**Câu 2: Không tìm thấy có phải kết quả bình thường không?**

- Có: dùng Optional<T>.
- Không: vẫn dùng Optional<T> ở repository rồi chuyển empty thành lỗi not-found ở service.

**Câu 3: Nếu có nhiều entry thì đó là lỗi hay chỉ cần lấy một entry theo thứ tự?**

- Là lỗi: dùng query đơn để framework báo duplicate.
- Chỉ cần một kết quả đầu tiên theo nghiệp vụ: dùng giới hạn/ordering rõ ràng và xác minh semantics store.

### 14.1. Bảng quyết định

| Nhu cầu | Kiểu trả về | Quy tắc |
| --- | --- | --- |
| Có thể không tồn tại, nhưng nếu có phải duy nhất | Optional<T> | Duplicate là lỗi |
| Bắt buộc phải tồn tại và phải duy nhất | Optional<T> ở repository | Service chuyển empty thành not-found |
| Có thể có nhiều entry, kể cả không có entry nào | List<T> | Empty list là hợp lệ |
| Chỉ cần biết có tồn tại không | boolean/exists nếu được hỗ trợ | Không dùng để lấy entity |
| Cần số lượng | long/count nếu được hỗ trợ | Không tự chứng minh identity duy nhất |
| Cần một tập con theo thứ tự | List<T> với limit/order | Không dùng để phát hiện duplicate toàn bộ |

## 15. Kiểm thử cardinality trên LDAP directory

Unit test mock repository có thể kiểm tra cách service xử lý Optional.empty() hoặc exception. Nhưng chỉ integration test mới chứng minh base DN, scope, schema, filter và server trả về cardinality như dự kiến.

### 15.1. Seed dữ liệu kiểm thử

~~~ldif
dn: dc=example,dc=org
objectClass: top
objectClass: domain
dc: example

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
departmentNumber: D01

dn: uid=nam,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: nam
cn: Nam Tran
sn: Tran
mail: nam@example.org
departmentNumber: D01

dn: uid=mai,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: mai
cn: Mai Pham
sn: Pham
mail: mai@example.org
departmentNumber: D02
~~~

Để test duplicate UID trong subtree, thêm một OU con và entry trùng:

~~~ldif
dn: ou=contractors,ou=people,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: contractors

dn: uid=lan,ou=contractors,ou=people,dc=example,dc=org
objectClass: top
objectClass: person
objectClass: organizationalPerson
objectClass: inetOrgPerson
uid: lan
cn: Lan Nguyen Contractor
sn: Nguyen
mail: lan.contractor@example.org
departmentNumber: D03
~~~

Test data này minh họa rằng cùng UID có thể duy nhất trong một nhánh hẹp nhưng trùng khi tìm trên subtree rộng hơn.

### 15.2. Ma trận kiểm thử

| ID | Dữ liệu/truy vấn | Kiểu trả về | Kỳ vọng |
| --- | --- | --- | --- |
| C01 | UID không tồn tại | Optional<Person> | Optional.empty() |
| C02 | UID có đúng một entry | Optional<Person> | Có entity |
| C03 | UID trùng hai entry trong scope | Optional<Person> | IncorrectResultSizeDataAccessException |
| C04 | UID không tồn tại | List<Person> | Danh sách rỗng |
| C05 | UID có một entry | List<Person> | Danh sách một phần tử |
| C06 | UID trùng hai entry | List<Person> | Danh sách hai entry |
| C07 | Department D01 | List<Person> | Hai nhân viên |
| C08 | Department không tồn tại | List<Person> | Danh sách rỗng |
| C09 | Base DN là engineering OU | Optional<Person> | Một entry nếu chỉ một entry trong nhánh |
| C10 | Base DN là people OU, scope subtree | Optional<Person> | Duplicate exception nếu UID trùng |
| C11 | Base DN hẹp, scope one-level | Optional<Person> | Không tìm entry ở OU con sâu hơn |
| C12 | Base DN hẹp, scope subtree | Optional<Person> | Tìm cả entry ở OU con |
| C13 | Email trùng | List<Person> | Trả đủ các entry khớp |
| C14 | Email được quy ước unique nhưng dữ liệu trùng | Optional<Person> | Duplicate exception |
| C15 | Attribute đa trị trên một entry | Optional<Person> | Vẫn chỉ một entry |
| C16 | Filter không khớp objectClass | Optional<Person> | Empty, nếu Search hoàn tất |
| C17 | Service Bind sai | Bất kỳ | Dependency/authentication exception, không phải empty |
| C18 | ACL từ chối Search | Bất kỳ | Access exception, không phải empty |
| C19 | Search timeout | Bất kỳ | Timeout/dependency exception |
| C20 | Size limit/partial result | List<Person> | Không coi partial là danh sách đầy đủ |
| C21 | Referral chưa xử lý | Bất kỳ | Không kết luận uniqueness toàn topology |
| C22 | Derived query theo property Java | Optional<Person> | Map đúng property tới LDAP attribute |
| C23 | findOne(LdapQuery) | Optional<Person> | 0/1; nhiều entry ném duplicate exception |
| C24 | findAll(LdapQuery) | List<Person> | 0..N entry |
| C25 | Query có Top/First | Collection có giới hạn | Không dùng để chứng minh uniqueness |
| C26 | Concurrent update/rename khi Search | Bất kỳ | Xử lý theo consistency/retry policy, không chọn entry ngẫu nhiên |

### 15.3. Test repository trả Optional

Ví dụ JUnit:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.dao.IncorrectResultSizeDataAccessException;

class PersonRepositoryCardinalityTest {
    private PersonRepository repository;

    @Test
    void returnsEmptyWhenNoEntryMatches() {
        assertTrue(repository.findByLoginName("missing").isEmpty());
    }

    @Test
    void returnsEntityWhenExactlyOneEntryMatches() {
        var result = repository.findByLoginName("nam");

        assertTrue(result.isPresent());
        assertEquals("nam", result.get().getLoginName());
    }

    @Test
    void rejectsMultipleMatchingEntries() {
        assertThrows(
            IncorrectResultSizeDataAccessException.class,
            () -> repository.findByLoginName("lan")
        );
    }
}
~~~

Đây là skeleton integration test. Cần cấu hình Spring context, repository bean, directory test và seed/cleanup data. Repository phải là bean thật để test query cardinality của Spring Data LDAP, không phải mock.

### 15.4. Test List không giả định duy nhất

~~~java
@Test
void returnsAllEntriesForDepartment() {
    var people = repository.findByDepartmentNumber("D01");

    assertEquals(2, people.size());
    assertTrue(
        people.stream().allMatch(
            person -> "D01".equals(person.getDepartmentNumber())
        )
    );
}
~~~

Kiểm tra số lượng và nội dung để chắc chắn method collection không âm thầm chỉ lấy một entry.

## 16. Các lỗi thiết kế thường gặp

| Anti-pattern | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng Optional<T> cho truy vấn phòng ban | Nhiều nhân viên gây exception | Dùng List<T> |
| Dùng List<T> cho lookup UID unique rồi lấy phần tử đầu | Che dữ liệu trùng | Dùng Optional<T>/findOne |
| Dùng T nullable mà không kiểm tra null | Null pointer hoặc xử lý vắng mặt không rõ | Ưu tiên Optional<T> |
| Bắt mọi exception rồi trả empty | Che TLS/Bind/ACL/timeout/duplicate | Chỉ chuyển đúng lỗi nghiệp vụ |
| Dùng findFirstByUid để né duplicate | Chọn entry không xác định, che data quality | Xác minh uniqueness và dùng single-result query |
| Coi existsByUid là bảo đảm duy nhất | Boolean không phân biệt 1 với N | Dùng single-result query |
| Coi count rồi lookup là một thao tác nguyên tử | Directory có thể đổi giữa hai query | Dùng query phù hợp và xử lý consistency |
| Không xác định base DN/scope | Cùng UID có thể trùng ở nhánh khác | Chốt phạm vi uniqueness |
| Nhầm nhiều giá trị mail với nhiều entry | Chọn sai kiểu trả về | Phân biệt attribute cardinality và entry cardinality |
| Coi Search rỗng là entry chắc chắn không tồn tại toàn directory | Có thể nằm ngoài base hoặc bị ACL che | Giải thích not-found theo query scope |
| Coi partial result là đầy đủ | Bỏ sót entry và kết luận sai uniqueness | Xử lý size/time limit/referral |
| Dùng Top1 trong authentication | Có thể xác thực nhầm identity | Duplicate phải fail closed |
| Không test duplicate | Lỗi chỉ xuất hiện khi dữ liệu thực tế trùng | Seed hai entry khớp và kiểm tra exception |

## 17. Checklist trước khi khai báo kiểu trả về

1. **Xác định đối tượng kết quả:** một LDAP entry hay một tập hợp entry?
2. **Xác định cardinality nghiệp vụ:** 0..1, 1..1 hay 0..N?
3. **Chọn kiểu Java:** Optional<T> cho 0..1; List<T> cho 0..N.
4. **Xác định uniqueness scope:** base DN, scope, tenant và naming context.
5. **Kiểm tra schema/matching rule:** attribute có semantics equality nào?
6. **Phân biệt entry với multi-valued attribute:** nhiều mail không phải nhiều person.
7. **Quy định duplicate behavior:** exception, log/audit và remediation.
8. **Không che lỗi:** Search failure/partial không phải not-found.
9. **Dùng First/Top đúng mục đích:** giới hạn tập con, không chứng minh uniqueness.
10. **Kiểm tra store-specific support:** query keyword và wrapper return type theo version.
11. **Kiểm thử 0/1/N:** bao gồm duplicate trong subtree và base hẹp.
12. **Kiểm thử lỗi dependency:** Bind, ACL, TLS, timeout, referral và size limit.

## 18. Câu hỏi tự kiểm tra

1. **Cardinality của LDAP query là gì?** Số entry khớp filter trong base DN và scope đã chọn.
2. **Một entry có hai giá trị mail thì Search theo UID có cardinality bao nhiêu?** Một entry, nếu chỉ một entry khớp.
3. **Optional<T> biểu đạt điều gì?** Không có hoặc tối đa một entry; nhiều entry là sai cardinality.
4. **List<T> biểu đạt điều gì?** Không có, một hoặc nhiều entry; không có kết quả là danh sách rỗng.
5. **Kiểu T trả gì khi không có kết quả?** null; nhiều hơn một entry gây IncorrectResultSizeDataAccessException.
6. **LdapRepository.findOne(LdapQuery) trả kiểu gì?** Optional<T> và ném IncorrectResultSizeDataAccessException nếu nhiều entry khớp.
7. **LdapRepository.findAll(LdapQuery) trả kiểu gì?** List<T>.
8. **Optional.empty() có chứng minh directory khỏe không?** Chỉ khi Search đã hoàn tất thành công; lỗi dependency phải được ném riêng.
9. **Vì sao không lấy phần tử đầu của List khi tìm UID?** Vì có thể che dữ liệu trùng và chọn nhầm identity.
10. **findFirstByUid có chứng minh UID unique không?** Không; nó giới hạn kết quả.
11. **existsByUid có phân biệt một với nhiều entry không?** Không; nó chỉ trả lời có ít nhất một.
12. **Vì sao base DN/scope ảnh hưởng cardinality?** Search subtree rộng hơn có thể tìm thấy entry trùng ở OU khác.
13. **Duplicate trong query đơn được biểu diễn bằng exception nào?** IncorrectResultSizeDataAccessException.
14. **Có nên đổi duplicate exception thành not-found không?** Không; đó là lỗi dữ liệu/uniqueness, không phải không tồn tại.
15. **Khi nào dùng List cho email?** Khi email có thể được dùng chung hoặc chưa có ràng buộc uniqueness.
16. **Nếu nghiệp vụ bắt buộc đúng một entry thì nên làm gì khi Optional empty?** Service chuyển thành not-found/domain error; nếu duplicate thì xử lý riêng.
17. **Partial result có thể dùng để khẳng định uniqueness không?** Không; kết quả chưa đầy đủ không chứng minh số entry thực tế.
18. **Spring Data @Query parameters có được encode không?** String-based parameters được encode theo RFC 2254; SpEL/property placeholder cần tự bảo đảm escaping.
19. **Có thể dùng Top2 để phát hiện duplicate không?** Có thể giới hạn số kết quả để xem ít nhất hai, nhưng phải xác minh semantics size-limit/partial result của server/provider.
20. **Test quan trọng nhất cho Optional lookup là gì?** Seed hai entry cùng khớp trong scope và xác nhận query ném duplicate exception.

## Tài liệu tham khảo

- [Spring Data LDAP — Query Methods](https://docs.spring.io/spring-data/ldap/reference/ldap/query-methods.html)
- [Spring Data LDAP — LdapRepository API](https://docs.spring.io/spring-data/ldap/docs/current/api/org/springframework/data/ldap/repository/LdapRepository.html)
- [Spring Data LDAP — Repository Query Return Types](https://docs.spring.io/spring-data/ldap/reference/repositories/query-return-types-reference.html)
- [Spring Data LDAP — Repository Query Keywords](https://docs.spring.io/spring-data/ldap/reference/repositories/query-keywords-reference.html)
- [Spring LDAP — LdapQueryBuilder API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/query/LdapQueryBuilder.html)
- [Spring LDAP — Advanced LDAP Queries](https://docs.spring.io/spring-ldap/reference/query-builder-advanced.html)
- [Spring Data Commons — Null Handling of Repository Methods](https://docs.spring.io/spring-data/commons/reference/repositories/null-handling.html)

**Ghi nhớ:** Chọn kiểu trả về theo số entry mà nghiệp vụ cho phép. Optional<T> và T biểu đạt tối đa một entry; nhiều hơn một phải được phát hiện như lỗi cardinality. List<T> biểu đạt không hoặc nhiều entry, trong đó không có kết quả là danh sách rỗng. findOne(LdapQuery) và findAll(LdapQuery) cung cấp hai hợp đồng tương ứng trong LdapRepository. Hãy xác định uniqueness trong đúng base DN/scope, phân biệt số entry với số giá trị attribute, không dùng First/Top để che dữ liệu trùng và không đổi lỗi Search thành not-found. Kiểm thử 0, 1, nhiều entry cùng các lỗi ACL, TLS, timeout và partial result để repository trả đúng ý nghĩa mà ứng dụng cần.
