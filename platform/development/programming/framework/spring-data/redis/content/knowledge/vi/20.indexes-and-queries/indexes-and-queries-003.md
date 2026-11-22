# Chỉ mục thuộc tính lồng nhau và thuộc tính tham chiếu trong Spring Data Redis

Trong Spring Data Redis Repository, entity Java thường được lưu thành Redis Hash, còn các truy vấn tìm entity theo thuộc tính được hỗ trợ bằng **secondary index** (chỉ mục phụ). Cơ chế này đặc biệt cần hiểu đúng khi mô hình có quan hệ giữa các đối tượng:

- **Đối tượng lồng nhau (embedded/nested object):** thuộc tính của đối tượng con được lưu cùng Redis Hash của entity cha, chẳng hạn `person.address.city`. Spring Data Redis có thể lập chỉ mục cho thuộc tính con.
- **Đối tượng được tham chiếu bằng `@Reference`:** entity cha chỉ lưu địa chỉ Redis key của entity khác, chẳng hạn `person.employer` trỏ đến `companies:c-9`. Spring Data Redis **không** đi theo tham chiếu để tạo chỉ mục từ các thuộc tính của entity đích.

Đây là ranh giới thiết kế quan trọng: một đường dẫn Java như `person.employer.name` có vẻ giống `person.address.city`, nhưng cách lưu trữ và cách lập chỉ mục của chúng khác nhau.

## 1. Secondary index của Redis Repository là gì?

Redis không có bảng SQL và không tự động tạo B-tree cho mọi trường trong Hash. Spring Data Redis Repository sử dụng các cấu trúc dữ liệu Redis, chủ yếu là **Set**, để duy trì danh sách ID có cùng giá trị thuộc tính.

Ví dụ hai người cùng ở Hà Nội:

```text
people:p-100
  id             = p-100
  displayName    = Mai
  address.city   = HaNoi

people:p-101
  id             = p-101
  displayName    = Binh
  address.city   = HaNoi
```

Nếu `address.city` được đánh chỉ mục, hạ tầng repository tạo/duy trì một Set về mặt ý nghĩa:

```redis
SADD people:address.city:HaNoi p-100
SADD people:address.city:HaNoi p-101
```

Khi truy vấn người có `address.city = "HaNoi"`, Spring Data Redis có thể đọc Set chứa ID rồi tải những Hash tương ứng. Truy vấn không cần quét toàn bộ `people:*`. Tên key minh họa theo quy ước mặc định; các lựa chọn keyspace, mapping và serializer có thể ảnh hưởng biểu diễn thực tế.

| Thành phần | Vai trò |
|---|---|
| `people` | Keyspace của entity `Person` |
| `people:p-100` | Redis Hash của một entity `Person` |
| `address.city` | Property path từ entity cha đến thuộc tính con |
| `people:address.city:HaNoi` | Redis Set chứa những ID phù hợp với giá trị được lập chỉ mục |
| `p-100` trong Set | ID của entity, không phải bản sao toàn bộ Hash |

Việc thêm `@Indexed` có ý nghĩa với **lần ghi qua hạ tầng repository**, không khiến Redis tự tìm tất cả Hash có sẵn và tạo lại chỉ mục lịch sử.

## 2. Lập chỉ mục thuộc tính của đối tượng lồng nhau

### 2.1. Khai báo entity và value object

Giả sử ứng dụng quản lý hồ sơ người dùng và địa chỉ liên hệ. `Address` chỉ là một phần của hồ sơ, không tồn tại độc lập bằng Redis key riêng.

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("people")
public class Person {

    @Id
    private String id;
    private String displayName;
    private Address address;

    protected Person() {
    }

    public Person(String id, String displayName, Address address) {
        this.id = id;
        this.displayName = displayName;
        this.address = address;
    }

    public String getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public Address getAddress() {
        return address;
    }

    public void changeAddress(Address address) {
        this.address = address;
    }
}
```

Trong lớp `Address`, đánh dấu **trường cần tìm kiếm** bằng `@Indexed`:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.index.Indexed;

public class Address {

    @Indexed
    private String city;
    private String country;

    protected Address() {
    }

    public Address(String city, String country) {
        this.city = city;
        this.country = country;
    }

    public String getCity() {
        return city;
    }

    public String getCountry() {
        return country;
    }
}
```

`Address` ở đây không cần `@RedisHash` và `@Id`: nó là đối tượng lồng trong `Person`. Annotation `@Indexed` trên `Address.city` khiến hạ tầng tìm được đường dẫn **`address.city`** khi duyệt cấu trúc của `Person`.

Việc đánh dấu `Address.city` không tự tạo một entity riêng để truy vấn bằng `AddressRepository`. Kết quả truy vấn vẫn là các `Person` sở hữu đối tượng con đó.

### 2.2. Repository với truy vấn trên đường dẫn lồng nhau

```java
import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface PersonRepository extends CrudRepository<Person, String> {

    // Tên phương thức đi qua Person.address.city.
    List<Person> findByAddressCity(String city);

    // Dấu _ chỉ rõ ranh giới của đường dẫn lồng nhau.
    List<Person> findByAddress_City(String city);
}
```

Đây là **derived query**: Spring Data phân tích tên phương thức, xác định property path và sử dụng secondary index đã khai báo để lấy các ID. Trong trường hợp có tên thuộc tính gây nhập nhằng, chẳng hạn entity đồng thời có `addressCity` và `address.city`, dấu gạch dưới `_` giúp chỉ rõ rằng truy vấn phải đi qua `address` đến `city`.

Chỉ dùng một trong hai kiểu tên phương thức trong mã thực tế nếu chúng có cùng ý nghĩa; ví dụ để người học thấy cách biểu diễn đường dẫn. Đặc biệt, khả năng phân tích tên property path **không đồng nghĩa** mọi quan hệ đều có thể lập chỉ mục: giới hạn của `@Reference` sẽ được giải thích sau.

### 2.3. Lưu và truy vấn

```java
Person mai = new Person(
        "p-100",
        "Mai",
        new Address("HaNoi", "VietNam")
);

Person binh = new Person(
        "p-101",
        "Binh",
        new Address("HaNoi", "VietNam")
);

Person an = new Person(
        "p-102",
        "An",
        new Address("DaNang", "VietNam")
);

personRepository.save(mai);
personRepository.save(binh);
personRepository.save(an);

List<Person> inHaNoi = personRepository.findByAddress_City("HaNoi");
// Dự kiến chứa Person p-100 và p-101, không yêu cầu thứ tự cụ thể.
```

Trên Redis CLI, có thể quan sát:

```redis
TYPE people:p-100
# hash

HGET people:p-100 address.city
# "HaNoi" (cách trình bày ví dụ)

TYPE people:address.city:HaNoi
# set

SMEMBERS people:address.city:HaNoi
# p-100, p-101 (Set không bảo đảm thứ tự)
```

Một entity có `address == null` hoặc `address.city == null` không đóng góp phần tử vào Set chỉ mục cho giá trị thành phố tương ứng. Redis Set cũng không biểu diễn trực tiếp một truy vấn `IS NULL` giống cơ sở dữ liệu quan hệ.

## 3. Đường đi của dữ liệu và vòng đời chỉ mục

Với dữ liệu được ghi qua Spring Data Redis Repository, quá trình có thể hình dung:

```text
personRepository.save(person)
       |
       v
Đọc @RedisHash, @Id và metadata của thuộc tính
       |
       +--> MappingRedisConverter
       |        |
       |        v
       |    Redis Hash people:p-100
       |    address.city = HaNoi
       |
       +--> Xác định @Indexed trên Address.city
                |
                v
            Cập nhật Redis Set
            people:address.city:HaNoi += p-100
```

Khi gọi `save` lần nữa sau khi thay đổi thành phố, repository cập nhật các cấu trúc chỉ mục tương ứng với trạng thái của entity. Về mặt ý nghĩa:

```redis
# Giá trị trước đó:
SREM people:address.city:HaNoi p-100

# Giá trị mới:
SADD people:address.city:Hue p-100
```

Đây là sơ đồ logic, không phải một cam kết về thứ tự lệnh nội bộ mà phiên bản Spring Data cụ thể gửi đến Redis. Hạ tầng còn có các cấu trúc theo dõi chỉ mục để phục vụ việc xóa/cập nhật.

### Một thay đổi đúng về nghiệp vụ

```java
Person person = personRepository.findById("p-100")
        .orElseThrow();

person.changeAddress(new Address("Hue", "VietNam"));
personRepository.save(person);

List<Person> inHue = personRepository.findByAddress_City("Hue");
```

Việc sửa một đối tượng Java trong bộ nhớ không tự ghi thay đổi vào Redis. Cần lưu lại qua repository hoặc dùng API cập nhật có hỗ trợ duy trì chỉ mục. Tự chạy `HSET people:p-100 address.city Hue` sẽ thay đổi Hash nhưng **không tự cập nhật** secondary index do repository quản lý.

**Hệ quả:** Có thể thấy field trong Hash có giá trị mới nhưng derived query vẫn tìm theo giá trị cũ nếu ứng dụng thay dữ liệu trực tiếp bằng Redis CLI hoặc `RedisTemplate.opsForHash()` mà bỏ qua cơ chế index maintenance.

## 4. Lập chỉ mục nhiều cấp, danh sách và Map

### 4.1. Nested property nhiều cấp

Với cấu trúc:

```text
Person
  └── address
        └── geo
              └── regionCode
```

Nếu `regionCode` được đánh dấu `@Indexed` và những đối tượng trên đường dẫn là đối tượng nhúng có thể mapping, tên chỉ mục thường phản ánh property path, chẳng hạn:

```text
people:address.geo.regionCode:R1
```

Không cần đánh dấu `@Indexed` ở mọi cấp cha. Annotation gắn vào thuộc tính đích cần lập chỉ mục; hạ tầng xét đường dẫn từ root entity tới thuộc tính ấy.

### 4.2. Danh sách đối tượng lồng nhau

Ví dụ một `Person` có nhiều địa chỉ:

```java
@RedisHash("people")
public class Person {
    @Id String id;
    List<Address> addresses;
}

public class Address {
    @Indexed String city;
}
```

Cấu hình index cho đường dẫn danh sách có thể dùng **programmatic indexing**, chẳng hạn `addresses.city`. Spring Data Redis mô tả dạng key ý nghĩa như:

```text
people:addresses.city:HaNoi  -> Set các Person ID có địa chỉ ở HaNoi
```

Vì một person có thể có nhiều `Address`, một ID có thể tham gia các Set theo nhiều thành phố. Đây là ngữ nghĩa **tồn tại một phần tử phù hợp** ở cấp đối tượng root, chứ không có kết quả phân trang theo từng địa chỉ con.

Cần phân biệt: khả năng **tạo index** trên thuộc tính của collection không có nghĩa mọi kiểu derived query hoặc Query by Example đều hỗ trợ tự động duyệt collection. Nếu cần truy vấn collection phức tạp, cân nhắc thiết kế chỉ mục và cách truy xuất ID riêng.

### 4.3. Map và tên key động

Ví dụ `Map<String, String> attributes` có dữ liệu:

```java
attributes.put("tier", "gold");
attributes.put("locale", "vi");
```

Spring Data Redis có thể cấu hình index theo một phần tử Map hoặc đường dẫn bên trong giá trị Map. Khi đó, biểu diễn chỉ mục có thể tương tự:

```text
people:attributes.tier:gold
people:attributes.locale:vi
```

Không nên hiểu rằng một `@Indexed` đặt tùy ý lên bản thân `Map` bảo đảm tất cả key động đều được lập chỉ mục theo mọi kiểu truy vấn. Với Map và List, nên cấu hình rõ property path hoặc chỉ mục tùy chỉnh và xác minh cơ chế truy vấn mong muốn dựa trên API/phiên bản đang dùng.

### 4.4. Cấu hình index bằng Java thay vì annotation

Spring Data Redis cho phép khai báo index không cần sửa lớp domain, thông qua `IndexConfiguration` và `SimpleIndexDefinition`:

```java
import java.util.List;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.index.IndexConfiguration;
import org.springframework.data.redis.core.index.IndexDefinition;
import org.springframework.data.redis.core.index.SimpleIndexDefinition;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@Configuration
@EnableRedisRepositories(indexConfiguration = PersonIndexConfiguration.class)
public class RedisRepositoryConfiguration {
}

class PersonIndexConfiguration extends IndexConfiguration {

    @Override
    protected Iterable<IndexDefinition> initialConfiguration() {
        return List.of(
                new SimpleIndexDefinition("people", "address.city"),
                new SimpleIndexDefinition("people", "addresses.city")
        );
    }
}
```

Ví dụ trình bày cách chỉ rõ keyspace `people` và property path. Nếu đã có `@Indexed` cho cùng đường dẫn, không cần khai báo trùng lặp chỉ để tạo cùng một index. Với Map, Collection và đường dẫn phức tạp, cấu hình programmatic giúp kiểm soát các property path mà mô hình thực sự cần tra cứu.

## 5. Thuộc tính tham chiếu với @Reference là một trường hợp khác

`@Reference` đại diện cho **liên kết tới một entity Redis khác**, không phải nhúng mọi thuộc tính của entity đích vào Hash của entity nguồn.

Giả sử mỗi `Person` làm việc tại một `Company`:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("companies")
public class Company {

    @Id
    private String id;
    private String name;
    private String region;

    protected Company() {
    }

    public Company(String id, String name, String region) {
        this.id = id;
        this.name = name;
        this.region = region;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getRegion() {
        return region;
    }
}
```

Entity nguồn:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Reference;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("people")
public class Person {

    @Id
    private String id;
    private String displayName;

    @Reference
    private Company employer;

    protected Person() {
    }

    public Person(String id, String displayName, Company employer) {
        this.id = id;
        this.displayName = displayName;
        this.employer = employer;
    }
}
```

Sau khi `Company` đã được lưu, `Person` có thể lưu **địa chỉ key** của công ty thay vì sao chép `name`, `region` vào Hash của person:

```text
Redis Hash companies:c-9
    id      = c-9
    name    = Example Logistics
    region  = central

Redis Hash people:p-100
    id          = p-100
    displayName = Mai
    employer    = companies:c-9
```

Khi đọc `Person`, Spring Data Redis có thể giải tham chiếu để dựng lại `employer` thành một `Company`. Nhưng lúc lưu `Person`, Spring Data **không tự động lưu thay đổi trong Company**. Công ty phải được lưu bằng repository riêng.

### Điều không được hỗ trợ tự động

Giả sử trong `Company` có:

```java
@Indexed
private String region;
```

Index này có thể phục vụ truy vấn **trên `Company`** theo `region` nếu Company được lưu đúng qua hạ tầng repository. Nhưng nó **không** trở thành index dành cho `Person` trên `employer.region`.

Một phương thức `PersonRepository.findByEmployerRegion("central")` không được hỗ trợ như truy vấn đi xuyên `@Reference` chỉ vì `Company.region` có `@Indexed`. Spring Data Redis không thực hiện phép JOIN qua Redis key tham chiếu khi duy trì secondary index của root entity.

**Quy tắc:** *Indexes cannot be resolved on References.* Đây là giới hạn được nêu trực tiếp trong tài liệu Spring Data Redis về secondary index và reference.

| Kiểu quan hệ | Dữ liệu lưu trong Hash của Person | Có thể tự lập index theo thuộc tính con? |
|---|---|---|
| `Address address` (nhúng) | `address.city = HaNoi` | Có, nếu cấu hình đúng `@Indexed`/IndexDefinition |
| `@Reference Company employer` | `employer = companies:c-9` | Không tự đi qua `employer.region` hay `employer.name` |
| `String employerId` có `@Indexed` | `employerId = c-9` | Có, vì đây là thuộc tính trực tiếp của Person |

## 6. Cách hỗ trợ truy vấn theo entity tham chiếu

Không thể dùng index trên thuộc tính entity đích như một JOIN tự động. Thay vào đó có vài phương án, tùy nhu cầu.

### 6.1. Lưu thêm ID đã chuẩn hóa trên entity nguồn

Nếu nghiệp vụ cần tìm tất cả nhân viên của công ty theo ID, thêm một **trường chỉ mục trực tiếp** vào `Person`:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Reference;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("people")
public class Person {

    @Id
    private String id;
    private String displayName;

    @Reference
    private Company employer;

    @Indexed
    private String employerId;

    protected Person() {
    }

    public Person(String id, String displayName, Company employer) {
        this.id = id;
        this.displayName = displayName;
        assignEmployer(employer);
    }

    public void assignEmployer(Company employer) {
        if (employer == null || employer.getId() == null) {
            throw new IllegalArgumentException(
                    "Employer must be persisted and have an ID");
        }
        this.employer = employer;
        this.employerId = employer.getId();
    }
}
```

Repository:

```java
import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface PersonRepository extends CrudRepository<Person, String> {
    List<Person> findByEmployerId(String employerId);
}

public interface CompanyRepository extends CrudRepository<Company, String> {
}
```

Trình tự lưu:

```java
Company company = companyRepository.save(
        new Company("c-9", "Example Logistics", "central")
);

personRepository.save(new Person("p-100", "Mai", company));
personRepository.save(new Person("p-101", "Binh", company));

List<Person> employees = personRepository.findByEmployerId("c-9");
```

Hash và index về mặt ý nghĩa:

```text
people:p-100
  employer    = companies:c-9
  employerId  = c-9

people:p-101
  employer    = companies:c-9
  employerId  = c-9

people:employerId:c-9
  {p-100, p-101}
```

Trong mô hình này, `employer` phục vụ điều hướng liên kết khi tải entity; `employerId` phục vụ tra cứu bằng secondary index. Đây là **denormalization có chủ đích**, không phải hai nguồn sự thật độc lập: code phải cập nhật cùng lúc cả hai trường khi thay công ty.

Đổi tên công ty không cần đổi `employerId` trên Person vì ID vẫn ổn định. Ngược lại, khi `Person` chuyển từ `c-9` sang `c-10`, cần cập nhật tham chiếu và `employerId` rồi gọi `personRepository.save(person)` để duy trì chỉ mục.

### 6.2. Nếu cần truy vấn theo thuộc tính của công ty

Giả sử cần “tất cả Person làm việc tại Company có region = central”. Hai cách phổ biến:

**Cách A — Truy vấn qua hai bước:**

1. Lưu `Company.region` với `@Indexed` và dùng `CompanyRepository.findByRegion("central")` để tìm các công ty phù hợp.
2. Lấy ID của từng công ty và tra cứu `PersonRepository.findByEmployerId(companyId)`.
3. Gộp các Person ID/bản ghi phù hợp và xử lý trùng lặp, phân trang theo nhu cầu.

```text
Company.region = central
        |
        v
Index companies:region:central
        |
        v
Company IDs [c-9, c-12]
        |
        +--> people:employerId:c-9  --+
        |                             +--> Person IDs
        +--> people:employerId:c-12 --+
```

Đây là cách ứng dụng chủ động “join” ở tầng dịch vụ. Khi số công ty hoặc nhân viên lớn, phải cân nhắc số lượt đọc Redis và xử lý phân trang thay vì tải tất cả vào bộ nhớ.

**Cách B — Sao chép giá trị phục vụ truy vấn lên Person:**

```java
@Indexed
private String employerRegion;
```

Khi tạo hoặc chuyển công ty:

```java
person.employerRegion = company.getRegion();
personRepository.save(person);
```

Sau đó có thể dùng `findByEmployerRegion("central")` trên `PersonRepository`. Cách này giảm bước đọc danh sách công ty nhưng làm tăng trách nhiệm **đồng bộ dữ liệu**. Khi `Company.region` thay đổi, cần cập nhật `employerRegion` ở mọi Person liên quan; chỉ `companyRepository.save(company)` sẽ **không** cập nhật hộ các bản ghi Person.

Nên chọn cách A khi ưu tiên dữ liệu chuẩn hóa và số lượng liên kết có thể xử lý, chọn cách B khi cần truy vấn thường xuyên với độ trễ thấp và chấp nhận cơ chế đồng bộ/đồng nhất cuối cùng. Không nên để thuộc tính sao chép biến thành một giá trị có thể bị sửa tùy ý mà không có quy tắc.

### 6.3. Khi nào cần chỉ mục tự quản?

Với truy vấn nhiều chiều hoặc quan hệ lớn, có thể duy trì Set riêng, ví dụ `company:employees:c-9`, rồi cập nhật cùng nghiệp vụ. Tuy nhiên, các Set này do **ứng dụng sở hữu**. Spring Data Redis Repository không tự quản lý vòng đời cho chỉ mục ngoài hạ tầng của nó. Cần thiết kế đường thêm, đổi, xóa, dọn TTL, khôi phục chỉ mục và khả năng xử lý lỗi ghi từng bước.

Nếu yêu cầu thực chất là JOIN sâu, tìm kiếm văn bản, tổng hợp hoặc truy vấn quan hệ động, cần đánh giá xem Redis Repository secondary index có phù hợp hay nên sử dụng một hệ thống truy vấn khác.

## 7. Hành vi của truy vấn dựa trên Set

Với hai thuộc tính được đánh index, Spring Data Redis có thể phối hợp các Set:

```java
List<Person> findByAddress_CityAndEmployerId(
        String city, String employerId);
```

Về ý nghĩa, đây là giao của các tập ID:

```redis
SINTER people:address.city:HaNoi people:employerId:c-9
```

Nếu dùng điều kiện `Or`, có thể là hợp các Set (`SUNION`) phù hợp. Các method name được Spring Data hỗ trợ không biến Redis thành công cụ thực thi mọi biểu thức SQL: tính năng này dựa trên chỉ mục có sẵn, chủ yếu cho tìm khớp chính xác. Ví dụ `findByAddress_City("hanoi")` không mặc nhiên khớp với giá trị đã ghi `"HaNoi"` vì chuỗi phân biệt hoa/thường.

Đối với Query by Example, Spring Data Redis hỗ trợ một tập con tính năng, gồm đối chiếu chính xác theo thuộc tính đơn giản hoặc lồng nhau đã index. Các phép tìm theo association, collection và map-like property không được hỗ trợ tương tự cách truy vấn thuộc tính đơn giản; không nên mặc định QBE có thể duyệt `@Reference`.

Điểm cần phân biệt:

- **Khả năng định nghĩa property path:** framework nhận biết cấu trúc Java.
- **Khả năng tạo secondary index:** hạ tầng ghi một Set chứa ID theo đường dẫn được hỗ trợ.
- **Khả năng biểu đạt query:** derived query/QBE có giới hạn riêng đối với kiểu dữ liệu, bộ toán tử và association.

Ba khả năng này có liên quan nhưng không đồng nhất.

## 8. Quản lý vòng đời và tính nhất quán của chỉ mục

### 8.1. Save và delete qua repository

Secondary index của Redis Repository được cập nhật khi lưu entity và gỡ các thành viên tương ứng khi entity bị xóa qua hạ tầng repository. Nếu bạn thay đổi `address.city` hay `employerId`, hãy lưu lại entity bằng repository để cho phép cơ chế quản lý chỉ mục xử lý trạng thái cũ/mới.

Một số thao tác nên đặc biệt cẩn thận:

| Thao tác | Ảnh hưởng đến index |
|---|---|
| `personRepository.save(person)` | Hạ tầng repository duy trì index của Person |
| `personRepository.deleteById(id)` | Hạ tầng repository xử lý việc gỡ index của entity |
| `HSET people:p-100 address.city Hue` | Chỉ sửa Hash; index repository có nguy cơ lệch |
| `DEL people:p-100` bằng Redis CLI | Xóa Hash nhưng không tự thực thi đầy đủ logic cleanup index của repository |
| `companyRepository.save(company)` | Cập nhật index của Company; không tự đồng bộ trường sao chép trên Person |

Không phối hợp thay đổi những field được index bằng Redis CLI, template Hash thô và Repository trong cùng luồng nghiệp vụ mà thiếu cơ chế đồng bộ rõ ràng.

### 8.2. Dữ liệu đã lưu trước khi có @Indexed

Nếu hàng triệu entity tồn tại trước khi bạn thêm `@Indexed` vào `Address.city`, việc khởi động phiên bản ứng dụng mới **không tự động backfill mọi Redis Set**. Các entity được lưu lại sau đó mới được hạ tầng lập chỉ mục theo cấu hình đang dùng.

Cần kế hoạch migration hoặc rebuild rõ ràng:

1. Xác định toàn bộ root entity cần lập lại index bằng đường duyệt đáng tin cậy.
2. Tải entity và lưu lại qua repository với cấu hình index mới, hoặc dùng quy trình rebuild riêng được thiết kế có kiểm soát.
3. Quản lý tải Redis, số key lớn và các lần cập nhật đồng thời để tránh tái tạo index từ dữ liệu cũ.
4. Chỉ chuyển luồng truy vấn phụ thuộc index mới sau khi quá trình backfill/đồng bộ đã hoàn tất.

Với dữ liệu cache ngắn hạn có thể tái tạo, xóa và xây lại theo vòng đời ứng dụng đôi khi đơn giản hơn. Nhưng không xóa hàng loạt dữ liệu nghiệp vụ chỉ vì cần bổ sung index.

### 8.3. TTL và key hết hạn

Khi entity có TTL, Redis có thể xóa Hash tự động mà không có một lời gọi `repository.deleteById(...)`. Spring Data Redis sử dụng các thông báo keyspace expiration để phục vụ việc dọn tham chiếu chỉ mục còn sót lại. **Thông báo Redis Pub/Sub không được lưu bền**: nếu ứng dụng không chạy hoặc không nhận được sự kiện đúng lúc, index Set có thể giữ ID của Hash đã hết hạn.

Vì vậy:

- Không dùng `SMEMBERS` trên index Set như bằng chứng rằng mọi Hash tương ứng còn tồn tại.
- Quan tâm cấu hình keyspace notifications và lifecycle của listener nếu entity có `@TimeToLive` hoặc `@RedisHash(timeToLive = ...)`.
- Thiết kế cơ chế định kỳ phát hiện/dọn entry mồ côi hoặc rebuild index nếu nghiệp vụ yêu cầu độ chính xác cao.
- Không giả định TTL trên entity gốc sẽ tự làm từng member trong Set index hết hạn.

Việc index thỉnh thoảng chứa ID không còn hợp lệ là rủi ro vận hành, nhất là khi dùng raw Redis commands hoặc để mất expiration events. Tầng truy xuất entity cần xử lý trường hợp một ID trong index không còn Hash tương ứng.

### 8.4. Thay đổi entity được @Reference trỏ đến

Quan hệ tham chiếu là quan hệ giữa **hai Redis key**. Giả sử `Person.employer` trỏ `companies:c-9`:

- Xóa `companies:c-9` không bảo đảm mọi `Person` được cập nhật để xóa tham chiếu.
- Lưu lại `Company` không tự thay đổi các trường denormalized trên `Person`.
- Khi tải `Person`, cần có chiến lược xử lý tham chiếu đã mất, phù hợp với nghiệp vụ và cách mapper giải quyết missing referenced object.

Redis Repository không cung cấp ràng buộc khóa ngoại theo kiểu cơ sở dữ liệu quan hệ. Nếu cần bất biến “Person luôn trỏ tới Company tồn tại”, lớp dịch vụ phải thiết kế luồng ghi, xóa và khôi phục nhất quán.

## 9. Hiệu năng và giới hạn

### 9.1. Độ lớn và số lượng secondary index

Mỗi giá trị khác nhau của một thuộc tính index có thể làm phát sinh một Redis Set riêng. Với thuộc tính có độ phân tán cao (high cardinality) như token duy nhất của mỗi người dùng, việc đánh index có thể tạo rất nhiều key/Set và tăng chi phí bộ nhớ. Khi lưu hoặc xóa entity, repository còn cần duy trì các Set liên quan.

Nên ưu tiên index cho thuộc tính **thực sự nằm trong điều kiện lọc** và có lợi ích rõ ràng:

| Thuộc tính | Cân nhắc |
|---|---|
| `address.city` | Thường hữu ích nếu người dùng lọc theo thành phố |
| `employerId` | Hữu ích cho truy vấn nhân viên theo công ty |
| `employerRegion` (denormalized) | Có ích cho truy vấn lặp lại, nhưng tốn công đồng bộ |
| Mã phiên hoặc token hầu như duy nhất | Có thể không cần index phụ nếu đã có cách tra cứu theo key trực tiếp |
| Mọi field của Address | Tăng chi phí mà không có lợi nếu nghiệp vụ chỉ lọc theo city |

### 9.2. Chuỗi chỉ mục và chuẩn hóa

Các giá trị như `"HaNoi"`, `"hanoi"` và `"Hà Nội"` là ba giá trị khác nhau nếu được lập index nguyên trạng. Nếu nghiệp vụ muốn tìm không phân biệt chữ hoa, dấu hoặc cách viết, hãy định nghĩa rõ cách chuẩn hóa tại đường ghi và truy vấn. Một trường riêng như `normalizedCity` có `@Indexed` thường rõ ràng hơn việc âm thầm giả định Redis có phép so khớp ngôn ngữ tự nhiên.

### 9.3. Redis Cluster

Redis Set index và Redis Hash của entity có thể phân bố ở các hash slot khác nhau trong Cluster. Một số phép toán nhiều key như `SINTER` hoặc `SUNION` bị ràng buộc bởi quy tắc hash slot. Đừng mặc định cấu hình Redis Repository và driver hiện tại xử lý trơn tru mọi derived query ghép Set trên mọi kiểu cluster topology. Cần xác minh khả năng hỗ trợ của phiên bản Spring Data Redis, Redis server và driver; nếu thiết kế cần truy vấn giao/hợp phức tạp xuyên slot, cân nhắc chiến lược key/tag hoặc hệ thống truy vấn chuyên dụng.

## 10. Các lỗi dễ gặp khi truy vấn thuộc tính lồng nhau và tham chiếu

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| `findByAddress_City("HaNoi")` không trả dữ liệu | Chưa đánh index vào thuộc tính đích hoặc entity cũ chưa được ghi lại | Kiểm tra annotation/index config; chuẩn bị backfill nếu cần |
| `HGET` hiển thị city mới nhưng truy vấn vẫn trả dữ liệu cũ | Cập nhật trực tiếp Hash bằng `HSET` ngoài repository | Đưa cập nhật qua repository hoặc quy trình quản lý index |
| Query `findByEmployerRegion(...)` không hoạt động | `employer` là `@Reference`; chỉ mục không đi xuyên tham chiếu | Truy vấn hai bước hoặc thêm `@Indexed employerRegion` trên Person |
| Sửa `Company.region` nhưng Person vẫn thuộc index vùng cũ | Giá trị vùng được denormalize chưa cập nhật | Đồng bộ lại các Person khi Company đổi vùng |
| Index Set chứa Person ID không tải được | Key gốc hết TTL hoặc bị xóa thô; event cleanup có thể mất | Kiểm tra expiration events và kế hoạch dọn index |
| Giá trị `null` không được tìm bằng query index thường | Không có thành viên index cho giá trị null | Mô hình hóa giá trị trạng thái riêng nếu nghiệp vụ cần |
| Truy vấn theo collection/map bị từ chối | Khả năng query khác khả năng định nghĩa index | Thiết kế tra cứu ID riêng hoặc dùng truy vấn phù hợp |
| Tìm `"hanoi"` không khớp `"HaNoi"` | So sánh giá trị index là so khớp chính xác | Chuẩn hóa dữ liệu và query |
| Index có quá nhiều Set nhỏ | Thuộc tính có cardinality lớn hoặc đánh index quá rộng | Rà soát các điều kiện tìm kiếm thực sự cần |

### Quan sát dữ liệu bằng Redis CLI

```redis
# Kiểm tra một entity Hash
TYPE people:p-100
HGETALL people:p-100

# Kiểm tra Set chỉ mục của thuộc tính nhúng
TYPE people:address.city:HaNoi
SCARD people:address.city:HaNoi
SSCAN people:address.city:HaNoi 0

# Kiểm tra Set chỉ mục của khóa denormalized
SMEMBERS people:employerId:c-9

# Kiểm tra bản ghi công ty được tham chiếu
TYPE companies:c-9
HGETALL companies:c-9
```

Trong production, tránh dùng `KEYS people:*` trên keyspace lớn để kiểm tra index. Dùng `SCAN` có lọc pattern và các lệnh đọc theo key đã biết. Tên key minh họa phải được đối chiếu với keyspace và serializer của ứng dụng thực tế.

## 11. Bài tập tự thực hành

**Bài 1 — Embedded index:** Tạo hai `Person` có `Address.city = "HaNoi"` và một người ở `"Hue"`. Lưu bằng repository, kiểm tra Redis Set `people:address.city:HaNoi` và kết quả `findByAddress_City("HaNoi")`. Sau đó đổi một người sang `"Hue"` bằng `save` và quan sát các Set thay đổi.

**Bài 2 — Phân biệt @Reference:** Tạo một `Company` có `region = "central"`, lưu Person tham chiếu tới Company, rồi quan sát field `employer` trong Hash của Person. Giải thích vì sao `@Indexed Company.region` không tạo Set `people:employer.region:central`.

**Bài 3 — Denormalization:** Thêm `@Indexed employerId` và phương thức `findByEmployerId`. Lưu hai Person của cùng công ty, chuyển một người sang công ty khác, bảo đảm `employer` và `employerId` cùng được cập nhật.

**Bài 4 — Cân nhắc tính nhất quán:** Nếu người dùng muốn lọc Person theo `Company.region`, so sánh giải pháp truy vấn hai bước với lưu `employerRegion` trên Person về số lượt đọc, tốc độ tra cứu, chi phí cập nhật và xử lý khi Company đổi vùng.

## 12. Ghi nhớ các nguyên tắc thiết kế

1. **Thuộc tính nhúng** như `address.city` được mapping vào Hash của entity cha và có thể lập secondary index theo property path.
2. **Thuộc tính tham chiếu** như `employer.region` nằm trong Hash của entity khác. `@Reference` lưu key tham chiếu; Spring Data Redis không tự giải tham chiếu để lập index cho entity nguồn.
3. Để tìm root entity theo quan hệ, có thể **lưu một khóa tìm kiếm trực tiếp** như `@Indexed employerId` hoặc tổ chức truy vấn hai bước. Khi sao chép thuộc tính từ entity khác, phải tự quản lý tính nhất quán.
4. Secondary index của Redis Repository dùng Redis Set để tra cứu ID, không phải chỉ mục quan hệ hay JOIN tổng quát. Việc tạo index và việc hỗ trợ cú pháp query có những giới hạn riêng.
5. Duy trì index qua repository, chú ý backfill cho dữ liệu cũ và dọn index khi key hết hạn hoặc dữ liệu bị thay đổi ngoài repository.

## Tài liệu tham khảo

- [Spring Data Redis — Secondary Indexes](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/indexes.html): `@Indexed`, nested index, Map/List và `IndexConfiguration`; giới hạn với reference.
- [Spring Data Redis — Usage và Persisting References](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/usage.html): mô hình `@Reference`, cách lưu key của entity được tham chiếu, yêu cầu lưu riêng entity đích.
- [Spring Data Redis — Redis-specific Query Methods](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/queries.html): derived query dựa trên các Set index và điều kiện `And`/`Or`.
- [Spring Data Redis — Query by Example](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/query-by-example.html): hỗ trợ truy vấn chính xác theo thuộc tính đơn giản/lồng nhau và giới hạn với association/collection/map.
- [Spring Data Redis — Time To Live](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html): expiration events và lưu ý về dọn secondary index khi entity hết hạn.
