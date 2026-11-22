# Chẩn đoán `PropertyReferenceException` và tên thuộc tính không hợp lệ trong Spring Data JPA

Khi tạo repository method như `findByEmail(...)`, Spring Data JPA không tìm cột tên `email` trong database trước. Nó **phân tích tên phương thức thành đường dẫn thuộc tính (property path) trên Java entity**. Nếu không tìm thấy đường dẫn phù hợp, ứng dụng có thể báo `PropertyReferenceException`: một dấu hiệu điển hình của lỗi đặt tên thuộc tính trong derived query, khai báo sắp xếp hoặc thành phần khác dựa trên property path.

Bài này giúp bạn đọc lỗi đúng chỗ, phân biệt **Java property với tên cột SQL**, hiểu parser xử lý camelCase và thuộc tính lồng nhau, rồi sửa và kiểm thử phương thức Spring Data JPA đúng cách. Ví dụ sử dụng Java 17+, Spring Boot 3.x, Spring Data JPA 3.x và `jakarta.persistence`; các lớp Spring trong ví dụ cần dependency Spring Boot/Spring Data và database, không phải chương trình Java thuần chỉ biên dịch bằng `javac`.

## 1. `PropertyReferenceException` là gì?

`PropertyReferenceException` xuất hiện khi Spring Data cố tạo một `PropertyPath` nhưng không phân giải được một phần đường dẫn trên **kiểu Java đang xét**. Nó không chứng minh bảng/cột SQL bị thiếu và thường xảy ra **trước khi câu SQL có cơ hội chạy**.

Ví dụ sơ đồ:

```text
Repository method: findByEmail(String email)
                           |
                           v
         Phân tích phần sau "By": Email
                           |
                           v
     Kiểm tra Java entity Customer có property "email"?
                           |
                KHÔNG: chỉ có "emailAddress"
                           |
                           v
               PropertyReferenceException
```

Một thông báo lỗi minh họa (chữ và cách bọc exception có thể khác theo phiên bản):

```text
No property 'email' found for type 'Customer'
```

Khi tạo Spring repository proxy, lỗi có thể nằm sâu trong chuỗi `BeanCreationException` → `QueryCreationException` → `PropertyReferenceException`. Đừng chỉ sửa bean được nêu ở đầu stack trace; hãy đi đến **`Caused by` sâu nhất có ích** và tìm:

- **Tên property không tìm thấy**: ví dụ `email`.
- **Kiểu Java đang xét**: ví dụ `Customer`, hoặc `Address` nếu lỗi nằm trong đường dẫn lồng nhau.
- **Phương thức repository** đang được tạo hoặc thực thi: ví dụ `findByEmail`.
- **Đường dẫn đã phân giải được**: nếu có, giúp biết parser đã đi đúng đến đâu.

Trong Spring Data Commons 3.x (thường đi với Spring Boot 3.x), class này ở `org.springframework.data.mapping.PropertyReferenceException`. API Spring Data Commons 4.x có thay đổi vị trí package sang `org.springframework.data.core.PropertyReferenceException`. Vì vậy nếu cần import trực tiếp trong test hoặc mã xử lý lỗi, **tra API đúng phiên bản dependency**; đừng sao chép import từ một phiên bản khác.

## 2. Derived query khớp với property của entity, không phải cột database

Xét entity `Customer` có thuộc tính:

```java
@Column(name = "email_address")
private String emailAddress;
```

Ở đây có **hai tên với hai mục đích khác nhau**:

| Tên | Thuộc lớp nào? | Dùng ở đâu? |
|---|---|---|
| `emailAddress` | Java entity property | `findByEmailAddress`, `Sort.by("emailAddress")`, JPQL `c.emailAddress` |
| `email_address` | Cột database do `@Column` ánh xạ | SQL/native query; không dùng làm phần tên derived method |
| `email` | Không tồn tại trên entity ví dụ | `findByEmail` là sai nếu parser phải suy diễn thuộc tính này |

**Sai:**

```java
List<Customer> findByEmail(String email);       // Không có property email
List<Customer> findByEmail_address(String mail); // "_" không có nghĩa nối vào tên cột SQL
```

**Đúng:**

```java
List<Customer> findByEmailAddress(String emailAddress);
```

Nếu entity có property `lastName`, tên phương thức phải phản ánh chính xác camelCase là `findByLastName`. `findByLastname` thường được hiểu thành property `lastname`; đó là một tên khác với `lastName`. Đừng dựa vào việc database dùng tên `last_name` hoặc naming strategy đã đổi cột để suy ra phần `By...`.

Với entity áp dụng **field access**, Spring Data/JPA nhìn các thuộc tính persistent gắn trên field; với **property access** thông qua getter, mô hình thuộc tính phải khớp getter/metadata được JPA nhận diện. Kiểm tra cả `@Access`, `@MappedSuperclass`, `@Embedded` và tên getter nếu dự án có cách ánh xạ khác với field thông thường. Một field chỉ có trong DTO/record trả về API, nhưng không thuộc entity domain mà repository quản lý, **không phải** property hợp lệ để tạo derived query trên entity đó.

## 3. Tên phương thức được phân tích như thế nào?

Một derived method thông dụng có dạng:

```text
find...By<Property><Operator>And<Property>OrderBy<Property><Direction>
```

Trong đó `find`/`read`/`get` là nhóm chủ đề; `By` ngăn giữa phần mô tả và điều kiện; sau `By` là property path kết hợp từ khóa truy vấn như `Containing`, `Between`, `IsNull`, `And`, `Or`, `IgnoreCase`, `OrderBy...Asc/Desc`. Danh sách từ khóa được hỗ trợ phụ thuộc module, nên đọc phần tài liệu dành cho Spring Data JPA.

Ví dụ hợp lệ nếu `Customer` có `emailAddress` và `lastName`:

```java
List<Customer> findByEmailAddress(String emailAddress);
List<Customer> findByLastNameAndEmailAddress(String lastName, String emailAddress);
List<Customer> findByLastNameContainingIgnoreCase(String part);
List<Customer> findByLastNameOrderByEmailAddressAsc(String lastName);
```

Phân tích cụ thể:

- `findByLastNameAndEmailAddress` tìm property `lastName` và `emailAddress`, kết hợp điều kiện AND.
- `findByLastNameContainingIgnoreCase` tìm `lastName`; `Containing` và `IgnoreCase` là keyword, **không** phải các field `containing` hay `ignoreCase`.
- `findByLastNameOrderByEmailAddressAsc` dùng `lastName` để lọc và `emailAddress` để sắp xếp; `Asc` là hướng sắp xếp.

Nếu tên field thực tế là `familyName`, thay đổi keyword không giúp: phải dùng `findByFamilyName...` hoặc đổi ánh xạ/domain model hợp lý. Một lỗi chỉ xuất hiện sau khi đổi tên property thường là **repository chưa được refactor đồng bộ**.

### Khi nào parser kiểm tra tên property?

Mặc định, Spring Data JPA thường tạo/kiểm tra derived queries khi khởi tạo repository bean trong lúc ứng dụng bootstrap. Vì vậy một method sai có thể làm cả `ApplicationContext` không khởi động dù chưa gọi API nào. Nếu cấu hình repository bootstrap là `LAZY` hoặc có cơ chế khởi tạo chậm, lỗi có thể chỉ xuất hiện khi repository được sử dụng; `DEFERRED` cũng thay đổi thời điểm kiểm tra. **Thời điểm phát lỗi không quyết định nguyên nhân**.

Các lỗi trong `Sort`/`Pageable` được truyền động khi gọi repository cũng có thể chỉ xuất hiện lúc thực thi request. Vì thế cần ghi lại **method, domain type và thao tác đang chạy**, thay vì mặc định mọi `PropertyReferenceException` xảy ra lúc startup.

## 4. Property lồng nhau và dấu gạch dưới `_`

Spring Data hỗ trợ đi qua quan hệ hoặc embedded object, chẳng hạn:

```text
Customer
  ├── emailAddress: String
  ├── lastName: String
  ├── address: Address
  │      └── zipCode: String
  └── addressZip: String
```

Nếu muốn tìm theo `customer.address.zipCode`, bạn có thể viết:

```java
List<Customer> findByAddress_ZipCode(String zipCode);
```

Dấu `_` là **ký tự phân tách đường dẫn rõ ràng** của parser. Nó hữu ích vì camelCase có thể mơ hồ:

- Khi thấy `AddressZipCode`, parser trước tiên tìm một property trực tiếp `addressZipCode`.
- Nếu không có, nó thử tách các nhóm camelCase từ phải sang trái, chẳng hạn `AddressZip` + `Code`, rồi `Address` + `ZipCode`.
- Nếu entity đã có `addressZip` kiểu `String`, parser có thể chọn `addressZip` rồi cố lấy tiếp property `code` từ `String`, dẫn đến lỗi dù `address.zipCode` vẫn tồn tại.
- `findByAddress_ZipCode` buộc parser đi qua `address` rồi `zipCode`, tránh nhầm với `addressZip`.

Khi không có tên cạnh tranh, `findByAddressZipCode` có thể được phân giải đúng; dấu `_` là công cụ làm rõ chỗ cắt, không bắt buộc cho mọi thuộc tính lồng nhau.

**Không dùng `_` để “viết giống tên cột”**. Với các property Java chứa dấu gạch dưới bất thường hoặc tên bắt đầu bằng `_`, Spring Data có quy tắc escaping/traversal riêng (ví dụ `__` trong một số đường dẫn). Cách dễ duy trì nhất là đặt tên thuộc tính Java theo camelCase tiêu chuẩn và giữ `@Column(name = "...")` cho tên SQL.

### Sai lớp đích của property lồng nhau

Giả sử `address` là kiểu `Address` và chỉ có `zipCode`, không có `postalNumber`:

```java
List<Customer> findByAddress_PostalNumber(String postalNumber); // Sai
```

Thông báo có thể nêu **`Address`** thay vì `Customer`, vì Spring Data đã tìm thấy `address` rồi thất bại ở `postalNumber`. Hãy mở class `Address` để tìm property thật sự; thêm `@Column(name = "postal_number")` trên một field khác **không tự tạo** một property Java tên `postalNumber` nếu field/getter đó không tồn tại.

## 5. Ví dụ hoàn chỉnh trong Spring Boot 3.x

Các file sau nằm cùng package `com.example.demo` của một dự án Spring Boot 3.x có `spring-boot-starter-data-jpa`, JDK 17+ và một datasource. Đây là mã nguồn từng file có thể biên dịch **trong dự án có dependency**; không chạy riêng lẻ bằng `javac` không có classpath Spring/Jakarta.

**`src/main/java/com/example/demo/Address.java`**

```java
package com.example.demo;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
public class Address {
    @Column(name = "zip_code")
    private String zipCode;

    protected Address() {
    }

    public Address(String zipCode) {
        this.zipCode = zipCode;
    }

    public String getZipCode() {
        return zipCode;
    }
}
```

**`src/main/java/com/example/demo/Customer.java`**

```java
package com.example.demo;

import jakarta.persistence.Column;
import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "email_address", nullable = false, unique = true)
    private String emailAddress;

    @Column(nullable = false)
    private String lastName;

    @Embedded
    private Address address;

    // Một property khác có tiền tố dễ gây nhầm với address.zipCode.
    private String addressZip;

    protected Customer() {
    }

    public Customer(String emailAddress, String lastName, String zipCode) {
        this.emailAddress = emailAddress;
        this.lastName = lastName;
        this.address = new Address(zipCode);
    }

    public Long getId() {
        return id;
    }

    public String getEmailAddress() {
        return emailAddress;
    }

    public String getLastName() {
        return lastName;
    }
}
```

**`src/main/java/com/example/demo/CustomerRepository.java`**

```java
package com.example.demo;

import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    List<Customer> findByEmailAddress(String emailAddress);

    List<Customer> findByLastName(String lastName);

    // Dấu "_" buộc đi qua address.zipCode.
    List<Customer> findByAddress_ZipCode(String zipCode);

    List<Customer> findByLastNameOrderByEmailAddressAsc(String lastName);
}
```

**Ví dụ lỗi: thêm vào repository những khai báo sau thì cần sửa trước khi khởi động ứng dụng:**

```java
// Không có field/getter "email" trên Customer.
List<Customer> findByEmail(String email);

// Không có property "createdAt" trên Customer.
List<Customer> findByLastNameOrderByCreatedAtDesc(String lastName);

// Dễ bị parser chọn "addressZip" rồi tìm sai "code".
List<Customer> findByAddressZipCode(String zipCode);
```

Ba dòng trên là **mã minh họa các cách khai báo sai**, không đặt vào cùng source file của ví dụ hoàn chỉnh. Với phương thức thứ ba, kết quả phụ thuộc tập property thực tế; chính vì `Customer` ở ví dụ có `addressZip`, cú pháp `AddressZipCode` là mơ hồ và `Address_ZipCode` an toàn hơn.

### Kiểm thử tên property đã sửa

File `src/test/java/com/example/demo/CustomerRepositoryTest.java`. Test này giả sử có `spring-boot-starter-test`, H2 (hoặc database kiểm thử tương đương) và một `@SpringBootApplication` trong package gốc thích hợp:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Sort;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

@DataJpaTest
class CustomerRepositoryTest {
    @Autowired
    private CustomerRepository repository;

    @Test
    void derivedQueriesResolveJavaPropertyPaths() {
        repository.saveAllAndFlush(List.of(
            new Customer("an@example.test", "Nguyen", "700000"),
            new Customer("binh@example.test", "Tran", "100000")
        ));

        assertEquals(1,
            repository.findByEmailAddress("an@example.test").size());

        assertEquals(1,
            repository.findByLastName("Nguyen").size());

        assertEquals("an@example.test",
            repository.findByAddress_ZipCode("700000")
                      .get(0).getEmailAddress());

        assertEquals("an@example.test",
            repository.findAll(Sort.by("emailAddress"))
                      .get(0).getEmailAddress());
    }
}
```

Kết quả mong đợi: test pass khi repository, entity và schema được cấu hình như trên. Không có `System.out.println` hay stdout cố định. Với dự án Maven thông thường, chạy bằng `./mvnw test` (Unix/macOS) hoặc `mvnw.cmd test` (Windows); với Gradle, `./gradlew test` hoặc `gradlew.bat test`. Lệnh chạy chính xác còn tùy build tool và cấu hình module của bạn.

Một lợi ích của `@DataJpaTest` là kiểm tra repository query parsing sớm, ngay cả trước khi truy vấn được gọi. Nếu chủ ý thêm một method sai như `findByEmail` vào `CustomerRepository`, context test có thể không khởi động và stack trace chỉ ra thuộc tính sai. Sau khi sửa method, chạy lại để xác nhận context tạo được và kết quả truy vấn đúng.

## 6. `Sort` và `Pageable` cũng dùng tên Java property

Lỗi tên property không chỉ nằm sau `By`. Ví dụ:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

// Hợp lệ vì Customer có property lastName:
var page = repository.findAll(
    PageRequest.of(0, 20, Sort.by("lastName"))
);

// Hợp lệ vì tên Java là emailAddress:
var customers = repository.findAll(Sort.by("emailAddress"));
```

Đây là **đoạn mã nằm trong phương thức đã có biến `repository`**, không phải chương trình chạy độc lập.

Ngược lại, với repository trên:

```java
// Sai: đây là tên cột SQL, không phải entity property.
repository.findAll(Sort.by("email_address"));

// Sai: Customer không có property createdAt.
repository.findAll(
    PageRequest.of(0, 20, Sort.by("createdAt"))
);
```

Các dòng sai có thể ném `PropertyReferenceException` hoặc lỗi liên quan khi query thực thi, tùy phiên bản và đường đi xử lý sort. Với nested property, Sort hỗ trợ đường dẫn như `Sort.by("address.zipCode")` khi provider có thể resolve path đó.

**Khi sort đến từ HTTP query string** (ví dụ `?sort=createdAt,desc`), không chuyển nguyên chuỗi tùy ý thành property JPA. Kiểm tra/giới hạn bằng danh sách property công khai mà API hỗ trợ, ánh xạ tên DTO như `"email"` sang property entity `"emailAddress"`, rồi mới tạo `Sort`. Điều này giúp tránh lỗi 500 không cần thiết và hạn chế tiết lộ cấu trúc nội bộ qua thông báo exception.

## 7. Phân biệt ba nhóm lỗi dễ bị nhầm

| Triệu chứng | Nhóm nguyên nhân thường gặp | Hướng tìm |
|---|---|---|
| `No property 'email' found for type 'Customer'` | Parser không tìm được Java property khi tạo `PropertyPath` | Kiểm tra entity, phần `By...`/`OrderBy...` và đường dẫn trong `Sort` |
| JPQL `@Query` báo semantic/path lỗi như không nhận `c.email` | Query viết tay tham chiếu thuộc tính sai | Kiểm tra chuỗi JPQL và tên property Java; lỗi không nhất thiết là `PropertyReferenceException` |
| SQL báo `column email_address does not exist` | Schema/migration hoặc mapping cột DB không khớp | Kiểm tra bảng, cột, migration, `@Column` và naming strategy |

**Chốt điểm mấu chốt:** lỗi `PropertyReferenceException` là vấn đề **đường dẫn Java property**. Đổi tên cột trong database chỉ có ích nếu nguyên nhân thật sự nằm ở schema. Không sửa nhầm migration khi log đang nói rõ "No property found for type".

### Nếu dùng `@Query` thay cho derived query

Khi tên truy vấn quá dài hoặc khó đọc, có thể khai báo JPQL trực tiếp:

```java
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

// Thêm method này bên trong CustomerRepository.
@Query("""
       select c
       from Customer c
       where c.emailAddress = :value
       """)
List<Customer> searchEmailExplicitly(@Param("value") String value);
```

Với `@Query`, Spring Data dùng truy vấn khai báo thay vì suy diễn điều kiện từ tên method; **trong JPQL vẫn phải dùng `c.emailAddress`**. Nếu dùng native SQL (`nativeQuery = true`), cú pháp SQL dùng tên cột `email_address` theo schema thực tế. Hai hình thức có validator và các lỗi khác nhau; thêm `@Query` chỉ để né một lỗi typo đơn giản thường làm phương thức khó bảo trì hơn.

## 8. Một bẫy đặc biệt: `findById` có thể là method dự trữ

Một số method CRUD như `findById`, `existsById` và `deleteById` được xử lý theo định danh JPA, không giống query thường. Giả sử entity `User` có:

```java
@Id
private Long pk;  // Khóa chính thực sự

private Long id;  // Property nghiệp vụ khác, không phải khóa chính
```

Khi một repository kế thừa `CrudRepository`/`JpaRepository`, `findById(...)` nhắm đến `pk` được đánh dấu `@Id`; nó **không tự mang nghĩa** tìm theo field nghiệp vụ `id`. Để tìm theo field `id` không phải khóa chính, có thể dùng method mô tả rõ như `findUserById(Long id)` (khi signature tránh đụng method base) hoặc query khai báo.

Ví dụ này giúp giải thích tình huống method **không lỗi nhưng truy vấn sai ý định**; cần phân biệt với `PropertyReferenceException`. Đừng dùng tên `findById` để suy đoán rằng parser luôn lấy property `id`.

## 9. Quy trình chẩn đoán nhanh khi ứng dụng không khởi động

Giả sử log có `Could not create query for ... CustomerRepository.findByEmail(...)`. Hãy xử lý theo thứ tự:

1. **Đọc `Caused by` gốc**, tìm `No property ... found for type ...`. Ghi chính xác property bị lỗi và class mà parser đang xét. Nếu class là kiểu lồng nhau, tiếp tục từ class đó.
2. **Xác định repository domain**: generic `JpaRepository<Customer, Long>` phải khớp entity thật. Với repository dùng inheritance, method kế thừa có thể đang được phân tích trên một domain khác bạn tưởng.
3. **Đối chiếu thuộc tính Java** (field/getter, access type, `@Embedded`, `@MappedSuperclass`), cả chữ hoa/chữ thường và các đoạn camelCase. Đừng tra cột SQL làm nguồn tên method.
4. **Phân tách phần method name**: `find...By`, điều kiện, keyword như `Containing`/`Between`, rồi `OrderBy`. Một typo ở phần sort tĩnh cũng có thể gây lỗi khởi tạo.
5. **Xem nested path**: nếu có `address.zipCode` và property cạnh tranh `addressZip`, thêm `_` để đánh dấu chỗ đi xuống như `findByAddress_ZipCode`.
6. **Nếu query method đều đúng**, tìm `Sort`/`Pageable` được truyền động từ controller/service. Đổi `"email_address"` sang `"emailAddress"`, hoặc map input API sang whitelist phù hợp.
7. **Nếu dùng `@Query` hoặc named query**, xác định đang chạy JPQL hay native SQL và xem lỗi validator/provider. Không quy mọi lỗi query vào parser derived methods.
8. **Chạy `@DataJpaTest` và một phép thử theo dữ liệu thực**. Một test chỉ khởi động context bắt được nhiều lỗi tên method; test thực thi giúp kiểm tra filter, sort và đường dẫn lồng nhau.

Đừng "sửa" bằng cách xóa tất cả method truy vấn, tắt repository validation hoặc bắt exception rồi trả danh sách rỗng. Những cách đó che lỗi cấu hình, khiến truy vấn hoạt động sai khi triển khai.

## 10. Bảng trước–sau cho các lỗi phổ biến

| Trước (sai hoặc mơ hồ) | Sau | Giải thích |
|---|---|---|
| `findByEmail` khi entity chỉ có `emailAddress` | `findByEmailAddress` | Sử dụng tên Java property thực |
| `findByEmail_address` vì SQL là `email_address` | `findByEmailAddress` | `_` là delimiter traversal, không mô tả tên cột |
| `findByLastname` khi field là `lastName` | `findByLastName` | Giữ đúng phân đoạn camelCase |
| `findByAddressZipCode` khi có cả `addressZip` | `findByAddress_ZipCode` | Buộc parser đi qua `address.zipCode` |
| `findByAddress_PostalNumber` khi `Address` chỉ có `zipCode` | `findByAddress_ZipCode` | Kiểm tra type của đoạn nested path |
| `findByLastNameOrderByCreatedAtDesc` khi không có `createdAt` | `findByLastNameOrderByEmailAddressAsc` | Cả phần sắp xếp tĩnh phải là property thật |
| `Sort.by("email_address")` | `Sort.by("emailAddress")` | Dynamic sort cũng dùng Java property |
| JPQL `c.email_address` | JPQL `c.emailAddress` | JPQL đi qua model JPA; native SQL mới dùng tên cột SQL |
| Tưởng `findById` tìm field nghiệp vụ `id` | `findUserById` hoặc query khai báo | `findById` có semantics truy cập khóa chính từ base repository |

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Entity có `@Column(name = "customer_name") private String displayName;`, method `findByCustomerName(...)` có hợp lệ không?

**Trả lời:** Không, nếu entity không có Java property `customerName`. Method đúng là `findByDisplayName(...)`; `customer_name` là tên cột SQL, không phải property.

**Câu 2.** Khi `Customer.address` là `Address` và `Address` có `zipCode`, có thể dùng `findByAddress_ZipCode` không?

**Trả lời:** Có. Dấu `_` xác định rõ đoạn đi qua `address` rồi `zipCode`, đặc biệt hữu ích nếu còn property `addressZip` khiến tên liền nhau mơ hồ.

**Câu 3.** Vì sao `findAll(Sort.by("lastUpdated"))` đôi khi chỉ lỗi khi người dùng gọi endpoint, dù ứng dụng khởi động bình thường?

**Trả lời:** `Sort` được tạo/truyền **khi thực thi**. Nếu entity không có `lastUpdated`, việc phân giải property sort có thể lỗi tại request, không phải ở khâu khởi tạo method repository.

**Câu 4.** Một JPQL `select c from Customer c where c.email_address = :x` hỏng có nhất thiết ném `PropertyReferenceException` không?

**Trả lời:** Không. Query viết tay được phân tích/kiểm tra qua tuyến JPQL/provider; lỗi thường thuộc semantic/query validation. Sửa thành `c.emailAddress` theo entity, hoặc dùng tên cột khi thực sự viết native SQL.

## 12. Ghi nhớ

- `PropertyReferenceException` chủ yếu báo **không tạo được `PropertyPath` trên Java domain type**; đọc phần `No property ... found for type ...` và repository method gây ra lỗi.
- Derived query, `OrderBy` và `Sort` dựa vào **property name** như `emailAddress`, `lastName`, không dựa vào `@Column(name = "...")`.
- Với property lồng nhau, `_` làm rõ ranh giới như `Address_ZipCode` và tránh ambiguity.
- Lỗi có thể xảy ra khi repository bootstrap hoặc khi xử lý sort động; thời điểm phát hiện phụ thuộc cấu hình và cách dùng.
- `@Query` thay thế việc suy diễn tên method nhưng vẫn phải viết đúng tên thuộc tính trong JPQL.
- Một test `@DataJpaTest` gọn đủ kiểm tra repository khởi tạo, sau đó thực thi các query/sort đặc trưng để khóa hành vi mong muốn.

## Tài liệu tham khảo

1. Spring Data JPA, *JPA Query Methods*: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
2. Spring Data Commons, *Defining Query Methods → Property Expressions và Reserved Method Names*: https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html
3. Spring Data JPA, *Repository Query Keywords*: https://docs.spring.io/spring-data/jpa/reference/repositories/query-keywords-reference.html
4. Spring Data Commons 3.5 API, `PropertyReferenceException`: https://docs.spring.io/spring-data/commons/docs/3.5.x/api/org/springframework/data/mapping/PropertyReferenceException.html
5. Spring Data Commons 4.x API, `PropertyReferenceException`: https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/core/PropertyReferenceException.html
6. Spring Data JPA, *Sorting*: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html#jpa.query-methods.sorting