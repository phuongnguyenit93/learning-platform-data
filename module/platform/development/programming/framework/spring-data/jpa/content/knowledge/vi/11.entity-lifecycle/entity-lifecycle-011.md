# Thiết kế equals, hashCode, toString và sử dụng Lombok an toàn với Entity

Entity JPA là object có vòng đời persistence: có thể mới tạo, đang được quản lý, đã flush, detached hoặc được nạp qua proxy. Vì vậy, các phương thức equals(), hashCode() và toString() cần được thiết kế theo identity và vòng đời của entity. Cách sinh tự động phù hợp với DTO hoặc value object có thể gây lỗi khi áp dụng nguyên xi cho entity, đặc biệt khi dùng khóa chính được database cấp, quan hệ hai chiều và lazy loading.

Bài học này giải thích hợp đồng equality của Java, sự khác nhau giữa object identity và entity identity, cách chọn khóa so sánh, ảnh hưởng của HashSet/HashMap, proxy Hibernate, đệ quy và lazy loading trong toString(), cùng cách dùng Lombok có kiểm soát. Ví dụ dùng Customer, Student và Order để minh họa.

## 1. Ba phương thức này có vai trò gì?

Java cung cấp ba phương thức cơ bản từ Object:

- **equals(Object)** xác định khi nào hai object được xem là bằng nhau về mặt logic.
- **hashCode()** tạo giá trị hash được dùng bởi HashSet, HashMap và các cấu trúc dựa trên hash.
- **toString()** tạo biểu diễn dạng chuỗi để debug, log hoặc hiển thị thông tin.

Mặc định, Object.equals() so sánh identity: hai biến chỉ bằng nhau nếu cùng tham chiếu đến đúng một object trong bộ nhớ. Object.hashCode() cũng gắn với identity của object theo hợp đồng của Java; không được hiểu nó là ID database.

Với entity JPA, hai object Java khác nhau có thể đại diện cho cùng một hàng database. Ví dụ, một Customer được tải trong persistence context thứ nhất và cùng Customer đó được tải trong persistence context khác. Hai object có thể có cùng khóa chính nhưng khác tham chiếu.

Bạn cần quyết định khái niệm equality mà domain yêu cầu: cùng object, cùng entity database hay cùng giá trị nghiệp vụ. Không có một cách triển khai duy nhất đúng cho mọi entity.

## 2. Hợp đồng equals() và hashCode()

Java yêu cầu equals() tuân theo các tính chất:

1. **Phản xạ**: object phải bằng chính nó.
2. **Đối xứng**: nếu a.equals(b) là true thì b.equals(a) cũng phải là true.
3. **Bắc cầu**: nếu a bằng b và b bằng c thì a phải bằng c.
4. **Nhất quán**: kết quả phải ổn định khi các thông tin dùng để so sánh không thay đổi.
5. **Không-null**: a.equals(null) phải là false.

Hợp đồng hashCode():

- Nếu hai object bằng nhau theo equals(), chúng bắt buộc có cùng hashCode().
- Hai object không bằng nhau có thể có cùng hashCode(); va chạm là điều được phép.
- Khi thông tin dùng trong equals() không thay đổi, hashCode() phải giữ nguyên trong suốt quá trình ứng dụng sử dụng object.

Quy tắc thứ nhất rất quan trọng với entity: không được viết equals() so sánh ID nhưng hashCode() lại dựa trên tên hoặc địa chỉ. Hai object bằng nhau phải có hashCode giống nhau.

## 3. Object identity và entity identity

Xét hai trường hợp:

~~~java
Customer first = entityManager.find(Customer.class, 10L);
Customer second = anotherEntityManager.find(Customer.class, 10L);
~~~

Nếu cả hai truy vấn trả về cùng một hàng, first và second có thể là hai object Java riêng biệt nhưng cùng đại diện cho Customer có ID 10.

Trong cùng một persistence context, JPA duy trì identity của entity được quản lý: cùng entity type và primary key thường được biểu diễn bằng cùng một managed instance trong context đó. Khi chuyển sang persistence context khác hoặc đọc entity ở trạng thái detached, bạn có thể gặp một object khác đại diện cho cùng hàng.

Điều này ảnh hưởng đến:

- So sánh entity giữa hai transaction.
- Dùng entity trong Set hoặc làm key của Map.
- Gộp dữ liệu từ nhiều repository hoặc persistence context.
- Kiểm tra quan hệ trong domain.
- Xử lý entity sau khi serialize/deserialize hoặc qua tầng API.

Trước khi override equals(), hãy xác định ứng dụng có thật sự cần equality theo entity identity hay chỉ cần so sánh cùng instance trong một transaction. Nếu không có nhu cầu so sánh hai instance khác nhau, giữ implementation mặc định của Object có thể là lựa chọn đơn giản và an toàn.

## 4. Chọn chiến lược equality cho entity

Có ba chiến lược thường gặp.

### 4.1. Giữ equality mặc định theo object identity

Không override equals() và hashCode(). Hai tham chiếu chỉ bằng nhau khi cùng là một object.

Phù hợp khi:

- Entity chủ yếu được sử dụng trong một persistence context.
- Ứng dụng không cần so sánh detached instance với managed instance.
- Quan hệ được xử lý bằng ID hoặc repository query.
- Không cần loại trùng entity qua Set dựa trên ID.

Ưu điểm là không phải giải quyết ID chưa được cấp, proxy hay mutable business key. Hạn chế là hai object đại diện cho cùng hàng database vẫn không bằng nhau theo equals().

### 4.2. Equality dựa trên khóa chính

Hai entity cùng loại được xem là bằng nhau khi cả hai đã có cùng primary key khác null.

Quy tắc quan trọng:

- Nếu hai object là cùng tham chiếu, trả về true.
- Nếu một trong hai chưa có ID, hai object khác tham chiếu không được xem là bằng nhau.
- Nếu cả hai có ID, so sánh ID sau khi xác định cùng entity type.
- hashCode phải ổn định trước và sau khi database cấp ID.

Cách này phù hợp khi ID là định danh của entity và ứng dụng cần so sánh các instance đại diện cho cùng hàng.

### 4.3. Equality dựa trên natural/business key

Hai entity bằng nhau khi một khóa nghiệp vụ ổn định giống nhau, ví dụ mã quốc gia ISO hoặc mã sản phẩm được xác định duy nhất.

Khóa dùng cho equality cần:

- Có giá trị ngay khi tạo object.
- Không thay đổi trong vòng đời entity.
- Duy nhất theo phạm vi nghiệp vụ.
- Không phụ thuộc vào quan hệ hoặc collection.
- Có quy tắc chuẩn hóa rõ ràng, ví dụ chữ hoa/thường hoặc khoảng trắng.

Email có thể không phải natural key tốt nếu người dùng được phép đổi email. Tên hiển thị, địa chỉ hoặc trạng thái cũng thường là dữ liệu mutable, không nên dùng làm khóa equality.

Nếu dùng business key, database vẫn cần UNIQUE constraint để bảo vệ tính duy nhất trước các transaction đồng thời.

## 5. Vấn đề đặc biệt với ID được database sinh tự động

Giả sử entity mới chưa có ID:

~~~java
Customer customer = new Customer("An");
Set<Customer> customers = new HashSet<>();

customers.add(customer);
entityManager.persist(customer);
entityManager.flush();
~~~

Database có thể cấp ID trong quá trình persist hoặc flush, tùy chiến lược sinh ID. Nếu hashCode() dựa trực tiếp trên ID, giá trị hash có thể đổi sau khi object đã được đưa vào HashSet.

HashSet chọn bucket dựa trên hashCode tại thời điểm add. Khi hashCode đổi, các lời gọi contains() hoặc remove() có thể không tìm thấy object trong bucket ban đầu:

~~~java
customers.contains(customer); // Có thể trả về false nếu hashCode đã đổi.
~~~

Đây là lỗi thực tế, dù object vẫn nằm trong Set.

Có hai hướng giải quyết:

- Dùng một business key bất biến, đã có từ lúc tạo entity, cho cả equals() và hashCode().
- Nếu equality dựa trên generated ID, dùng hashCode ổn định theo entity class thay vì theo giá trị ID.

Không dùng ID null làm giá trị chung để kết luận hai entity mới bằng nhau. Hai Customer mới chưa được lưu là hai entity khác nhau dù cả hai đều có id = null.

## 6. Ví dụ equality theo generated ID, có xét Hibernate proxy

Với Hibernate, entity có thể được đại diện bởi proxy class để hỗ trợ lazy loading. So sánh getClass() trực tiếp giữa entity thật và proxy có thể cho kết quả khác vì proxy là subclass được tạo lúc chạy.

Ví dụ dưới đây dùng API Hibernate để lấy persistent class của proxy mà không cần khởi tạo proxy chỉ để xác định class:

~~~java
package example.domain;

import jakarta.persistence.*;
import org.hibernate.proxy.HibernateProxy;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    private static Class<?> persistentClass(Object entity) {
        if (entity instanceof HibernateProxy proxy) {
            return proxy.getHibernateLazyInitializer()
                .getPersistentClass();
        }
        return entity.getClass();
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }

        if (other == null
                || persistentClass(this) != persistentClass(other)) {
            return false;
        }

        Customer that = (Customer) other;
        return id != null && id.equals(that.getId());
    }

    @Override
    public int hashCode() {
        return persistentClass(this).hashCode();
    }
}
~~~

Giải thích:

- this == other xử lý trường hợp cùng một object, kể cả khi entity còn transient và ID null.
- persistentClass() lấy lớp entity thực tế nếu object là Hibernate proxy.
- Hai object khác nhau chỉ bằng nhau khi cùng persistent class và ID hiện tại khác null.
- hashCode() chỉ dựa trên persistent class, vì vậy không đổi khi ID được cấp.

Đây là cách triển khai phụ thuộc Hibernate. Nếu dùng JPA provider khác, cần thay phần nhận diện proxy theo API của provider hoặc chọn chiến lược equality phù hợp với môi trường. Nếu dùng entity inheritance, phải xác định rõ các lớp con có được xem là cùng loại equality hay không; ví dụ trên yêu cầu persistent class khớp chính xác.

Hash code theo class tạo ra va chạm giữa nhiều entity cùng loại. Điều đó vẫn đúng theo hợp đồng Java, nhưng có thể giảm hiệu năng của HashSet/HashMap nếu một collection chứa số lượng rất lớn entity cùng class. Nếu có business key bất biến, equality và hashCode theo business key thường cho phân bố tốt hơn.

## 7. Vì sao không dùng toàn bộ field của entity trong equals()?

Một cách triển khai thường gặp là so sánh tất cả field:

~~~java
return Objects.equals(name, that.name)
    && Objects.equals(email, that.email)
    && Objects.equals(orders, that.orders);
~~~

Cách này có nhiều vấn đề:

- Đổi tên hoặc email làm equality thay đổi.
- Collection quan hệ có thể được tải lazy khi equals() chạy.
- So sánh hai entity có thể kéo theo nhiều truy vấn database.
- Quan hệ hai chiều có thể tạo vòng lặp.
- Collection có thể thay đổi trong khi object đang nằm trong HashSet.
- Hai entity khác ID nhưng có cùng dữ liệu hiện tại có thể bị xem là một object.

Entity có identity và vòng đời riêng. Các field nghiệp vụ thường thay đổi theo thời gian; vì vậy không nên dùng tất cả field làm equality.

Tránh đưa vào equals()/hashCode():

- Collection như List, Set, Map của quan hệ.
- Quan hệ @OneToMany, @ManyToMany và các association khác.
- Field mutable như tên, địa chỉ, trạng thái hoặc số dư.
- Field có thể lazy load.
- Field kỹ thuật thay đổi theo thời gian như updatedAt hoặc version.

## 8. Lombok @Data nguy hiểm với Entity như thế nào?

Lombok @Data là annotation tổng hợp, tương đương việc yêu cầu Lombok sinh:

- @Getter cho các field.
- @Setter cho các field không final.
- @RequiredArgsConstructor.
- @ToString.
- @EqualsAndHashCode.

Với DTO đơn giản, cách này có thể tiện. Với entity JPA, các phương thức sinh tự động có thể bao gồm toàn bộ field, kể cả quan hệ và collection.

Ví dụ:

~~~java
@Data
@Entity
public class Student {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @ManyToMany
    private Set<Course> courses = new HashSet<>();
}
~~~

Đoạn mã này có thể gây ra các vấn đề:

1. equals() và hashCode() đưa id, name và courses vào equality. Khi name hoặc collection thay đổi, hashCode có thể đổi.
2. equals() có thể đi qua quan hệ lazy và kích hoạt truy vấn database.
3. Student.toString() có thể in courses; Course.toString() lại in students, tạo vòng lặp đệ quy.
4. toString() có thể tải hàng loạt entity chỉ để ghi log.
5. Setter tự sinh cho ID và collection cho phép code thay đổi trạng thái persistence tùy tiện.
6. Constructor do Lombok sinh có thể không đáp ứng constructor không tham số mà JPA cần nếu annotation được kết hợp thiếu cẩn thận.

Không dùng @Data cho entity có quan hệ persistence. Hãy chọn từng annotation theo mục đích.

## 9. Dùng Lombok an toàn cho getter, constructor và toString

Có thể dùng Lombok để giảm mã lặp mà vẫn kiểm soát field:

~~~java
package example.domain;

import jakarta.persistence.*;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.ToString;

import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "students")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@ToString(
    onlyExplicitlyIncluded = true,
    doNotUseGetters = true
)
public class Student {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @ToString.Include
    private Long id;

    @Column(nullable = false, length = 120)
    @ToString.Include
    private String name;

    @OneToMany(mappedBy = "student", fetch = FetchType.LAZY)
    @ToString.Exclude
    private List<Enrollment> enrollments = new ArrayList<>();

    public Student(String name) {
        this.name = name;
    }

    public void rename(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Name is required");
        }
        this.name = name;
    }
}
~~~

Ở đây:

- @Getter tạo getter cho các field.
- @NoArgsConstructor(access = AccessLevel.PROTECTED) tạo constructor không tham số có visibility phù hợp với JPA.
- Không tạo setter công khai hàng loạt; thay đổi trạng thái qua method nghiệp vụ như rename().
- @ToString(onlyExplicitlyIncluded = true) chỉ in field được đánh dấu @ToString.Include.
- doNotUseGetters = true yêu cầu Lombok đọc field trực tiếp trong toString().
- Quan hệ enrollments được loại khỏi biểu diễn chuỗi.

Vì chỉ dùng onlyExplicitlyIncluded, quan hệ chưa được đánh dấu Include sẽ không xuất hiện. @ToString.Exclude vẫn giúp thể hiện ý định rõ ràng nếu sau này annotation được đổi.

Chỉ đưa dữ liệu an toàn vào toString(). Không in password, token, secret, thông tin cá nhân nhạy cảm hoặc payload lớn. toString() phục vụ debug; nó không phải định dạng serialize API.

## 10. Dùng Lombok cho equals/hashCode khi có natural key bất biến

Nếu entity có một business key thực sự ổn định, Lombok có thể sinh equals/hashCode chỉ từ field được chỉ định.

Ví dụ Country có mã ISO hai ký tự:

~~~java
package example.domain;

import jakarta.persistence.*;
import lombok.EqualsAndHashCode;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.AccessLevel;
import lombok.ToString;

@Entity
@Table(name = "countries")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@EqualsAndHashCode(onlyExplicitlyIncluded = true)
@ToString(onlyExplicitlyIncluded = true, doNotUseGetters = true)
public class Country {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "iso_code", nullable = false, unique = true,
            updatable = false, length = 2)
    @EqualsAndHashCode.Include
    @ToString.Include
    private String isoCode;

    @Column(nullable = false, length = 100)
    @ToString.Include
    private String name;

    public Country(String isoCode, String name) {
        if (isoCode == null || !isoCode.matches("[A-Z]{2}")) {
            throw new IllegalArgumentException("Invalid ISO code");
        }
        this.isoCode = isoCode;
        this.name = name;
    }
}
~~~

Lombok chỉ đưa isoCode vào equals/hashCode vì field được đánh dấu @EqualsAndHashCode.Include và class bật onlyExplicitlyIncluded. ID, name và quan hệ không tham gia equality.

Điều kiện để cách này an toàn:

- isoCode được đặt ngay khi tạo object.
- isoCode không thay đổi sau khi object được dùng trong collection.
- Database có unique constraint.
- Quy tắc chuẩn hóa mã được áp dụng thống nhất.
- Kiểm thử equality với proxy và inheritance nếu ứng dụng dùng Hibernate proxy hoặc entity hierarchy.

Nếu business key có thể null hoặc thay đổi, đừng dùng cách này. Với entity dùng generated ID, ưu tiên implementation equals/hashCode có chủ đích như phần trước.

## 11. Lombok @EqualsAndHashCode.Include và Exclude

Lombok cung cấp hai cách kiểm soát field:

~~~java
@EqualsAndHashCode(onlyExplicitlyIncluded = true)
class Example {
    @EqualsAndHashCode.Include
    private String immutableCode;

    private String mutableName;

    @EqualsAndHashCode.Exclude
    private Set<RelatedEntity> relations;
}
~~~

- onlyExplicitlyIncluded = true khiến không field nào tham gia nếu không được đánh dấu Include.
- @EqualsAndHashCode.Include thêm field hoặc method được chọn vào equality.
- @EqualsAndHashCode.Exclude loại field khỏi equality theo cấu hình mặc định.

Với entity, cách onlyExplicitlyIncluded thường dễ review hơn vì field mới thêm sẽ không tự động tham gia equality.

Tuy nhiên, annotation này không tự giải quyết mọi vấn đề proxy. Lombok có cơ chế canEqual() để xử lý một số trường hợp kế thừa, nhưng cần kiểm tra class proxy, access strategy và cách getter được gọi. Với entity dùng generated ID hoặc có inheritance phức tạp, implementation thủ công thường cho phép kiểm soát rõ hơn.

Không dùng callSuper = true một cách máy móc. Nếu superclass chứa ID, trạng thái mutable hoặc collection, equality của entity con có thể bị ảnh hưởng ngoài ý muốn. Chỉ dùng khi superclass thực sự là phần định danh ổn định của domain và mô hình kế thừa đã được thiết kế cho equality.

## 12. Constructor, Builder và setter do Lombok sinh

JPA entity phải đáp ứng các yêu cầu constructor và proxy của JPA provider. Theo mô hình entity thông thường:

- Entity cần constructor không tham số có visibility public hoặc protected.
- Entity class không nên là final.
- Persistent fields và phương thức cần được provider truy cập không nên final nếu provider cần proxy/subclass.
- Không nên dùng @Value cho entity thông thường vì annotation này tạo class/field final và thiên về immutable value object.
- Nếu dùng @Builder, hãy khai báo constructor không tham số riêng để bảo đảm JPA có constructor cần thiết.
- Tránh builder cho entity có nhiều quan hệ bắt buộc nếu nó cho phép tạo object ở trạng thái không hợp lệ.
- Tránh setter công khai cho ID, version và association nếu thay đổi các field đó không được phép trong nghiệp vụ.

Ví dụ kết hợp Builder một cách có kiểm soát:

~~~java
@Entity
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, updatable = false)
    private String sku;

    @Column(nullable = false)
    private String name;

    public Product(String sku, String name) {
        this.sku = Objects.requireNonNull(sku);
        this.name = Objects.requireNonNull(name);
    }

    public static Product create(String sku, String name) {
        return new Product(sku, name);
    }
}
~~~

Ví dụ này dùng factory method thay vì cho phép builder gán mọi field. Nếu dự án thật sự cần builder, hãy giới hạn builder vào các thuộc tính đầu vào hợp lệ và giữ constructor JPA riêng.

## 13. toString() và lazy loading

Một entity có thể có quan hệ lazy:

~~~java
@OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
private List<Order> orders;
~~~

Nếu toString() in orders, khi gọi:

~~~java
log.debug("Customer: {}", customer);
~~~

Hibernate có thể cần tải collection. Điều đó dẫn đến:

- Truy vấn database bất ngờ khi ghi log.
- N+1 query nếu log trong vòng lặp.
- LazyInitializationException nếu persistence context đã đóng.
- Vòng lặp đệ quy nếu Order.toString() lại in Customer.
- Log quá lớn khi collection có nhiều phần tử.

Cách xử lý:

- Không đưa association vào toString().
- Dùng onlyExplicitlyIncluded và chỉ include scalar field nhỏ, an toàn.
- Nếu cần log quan hệ, log ID đã biết hoặc số lượng đã được tính trong transaction.
- Không gọi toString() để serialize entity thành JSON; dùng DTO và serializer có cấu hình rõ.
- Không dùng Lombok @Data cho entity có quan hệ.

toString() nên nhanh, có giới hạn và không làm phát sinh truy vấn ngoài dự kiến.

## 14. Kiểm thử equals/hashCode cho entity

Không chỉ kiểm tra một cặp object đơn giản. Hãy kiểm tra các trạng thái trong vòng đời.

### 14.1. Test các tính chất cơ bản

Đây là các method test minh họa; cần đặt trong test class JUnit 5 có import và cấu hình test phù hợp:

~~~java
@Test
void equalsIsReflexiveAndNullSafe() {
    Customer customer = new Customer("An");

    assertEquals(customer, customer);
    assertNotEquals(customer, null);
}

@Test
void twoTransientEntitiesAreNotEqual() {
    Customer first = new Customer("An");
    Customer second = new Customer("An");

    assertNotEquals(first, second);
}
~~~

Test trên phù hợp với chiến lược generated ID: hai entity transient khác tham chiếu và chưa có ID không được xem là bằng nhau.

### 14.2. Test HashSet trước và sau khi persist

~~~java
@Test
void hashCodeRemainsStableAfterGeneratedIdIsAssigned() {
    Customer customer = new Customer("An");
    Set<Customer> customers = new HashSet<>();

    customers.add(customer);

    entityManager.persist(customer);
    entityManager.flush();

    assertTrue(customers.contains(customer));
}
~~~

Test này bắt lỗi hashCode thay đổi sau khi ID được database cấp.

### 14.3. Test hai instance đại diện cùng hàng

~~~java
@Test
void detachedAndReloadedInstancesCompareByIdentity() {
    Customer customer = new Customer("An");
    entityManager.persist(customer);
    entityManager.flush();

    Long id = customer.getId();
    entityManager.clear();

    Customer reloaded = entityManager.find(Customer.class, id);

    assertNotSame(customer, reloaded);
    assertEquals(customer, reloaded);
    assertEquals(customer.hashCode(), reloaded.hashCode());
}
~~~

Trong test thật, sau clear() object customer là detached; reloaded là instance mới trong persistence context hiện tại. Test xác minh equality dựa trên ID.

### 14.4. Test proxy và toString

Với Hibernate, thêm kiểm thử:

- So sánh entity đã tải với proxy lấy bằng getReference().
- Kiểm tra hai chiều: entity.equals(proxy) và proxy.equals(entity).
- Xác minh hashCode của proxy và entity thật tương thích.
- Kiểm tra toString() không duyệt collection quan hệ.
- Kiểm tra log/toString không làm phát sinh SQL ngoài dự kiến khi proxy chưa được khởi tạo.

Cách kiểm tra SQL có thể dùng Hibernate statistics hoặc datasource query counter trong integration test. Không chỉ dựa vào việc test không ném exception.

## 15. Những sai lầm thường gặp

**1. Dùng ID null để so sánh hai entity mới**

Hai entity transient khác nhau đều có ID null. Không được kết luận chúng bằng nhau chỉ vì null bằng null.

**2. hashCode() thay đổi sau persist**

Nếu hashCode dựa trên generated ID, object đã ở trong HashSet có thể không còn tìm thấy sau khi ID được cấp. Dùng business key bất biến hoặc hashCode ổn định theo entity class.

**3. So sánh getClass() trực tiếp với Hibernate proxy**

Proxy có thể là subclass của entity. So sánh class trực tiếp có thể khiến entity và proxy của cùng một hàng bị xem là khác nhau. Chọn cách xử lý proxy phù hợp với provider.

**4. Dùng toàn bộ field trong equals/hashCode**

Field mutable và quan hệ làm equality thay đổi, kéo theo truy vấn lazy và vòng lặp. Chỉ dùng định danh ổn định.

**5. Dùng @Data cho entity**

@EqualsAndHashCode và @ToString được sinh trên quá nhiều field; setter cũng có thể cho phép thay đổi ID hoặc quan hệ tùy tiện. Chọn annotation Lombok riêng lẻ.

**6. In collection quan hệ trong toString()**

Điều này có thể kích hoạt lazy loading, N+1 và recursion. Chỉ include scalar field có kiểm soát.

**7. Dùng @Value hoặc final entity**

Cấu trúc final không phù hợp với nhiều cơ chế proxy và yêu cầu entity thông thường của JPA. Dùng class entity có thể được provider quản lý và tạo proxy.

**8. Dùng mutable business key**

Nếu email hoặc tên có thể đổi mà lại nằm trong hashCode, object có thể mất vị trí trong HashSet. Chỉ dùng natural key bất biến.

**9. Quên kiểm tra inheritance**

Entity cha và entity con có thể có cùng ID số học nhưng không nhất thiết cùng loại entity. Equality phải phản ánh chính sách kế thừa và persistent type.

## 16. Quy trình chọn và triển khai

Khi tạo entity mới, hãy quyết định theo trình tự:

1. Xác định có cần so sánh hai instance khác persistence context hay không.
2. Nếu không cần, cân nhắc giữ equals/hashCode mặc định.
3. Nếu cần, xác định entity identity dựa trên generated ID hay immutable business key.
4. Nếu dùng generated ID, xử lý ID null và hashCode ổn định sau persist.
5. Nếu dùng Hibernate proxy, kiểm tra persistent class thay vì so sánh class proxy trực tiếp.
6. Không đưa collection, association hoặc field mutable vào equality.
7. Tạo toString() chỉ với scalar field an toàn.
8. Dùng Lombok cho getter, constructor và toString có chọn lọc; tránh @Data.
9. Kiểm thử transient, persisted, detached, proxy và HashSet.
10. Review lại khi đổi entity inheritance, khóa chính hoặc business key.

## 17. Checklist tự đánh giá

- [ ] Tôi giải thích được hợp đồng equals() và hashCode().
- [ ] Tôi phân biệt object identity và entity identity.
- [ ] Tôi hiểu vì sao ID null không thể làm equality cho hai entity transient.
- [ ] Tôi biết hashCode dựa trên generated ID có thể phá HashSet sau persist.
- [ ] Tôi chọn được giữa default identity, generated ID và immutable business key.
- [ ] Tôi hiểu tác động của Hibernate proxy đến getClass().
- [ ] Tôi không đưa association hoặc collection vào equals/hashCode.
- [ ] Tôi hiểu vì sao @Data nguy hiểm với entity.
- [ ] Tôi dùng @Getter, constructor và @ToString có chọn lọc.
- [ ] Tôi loại lazy relationship và dữ liệu nhạy cảm khỏi toString().
- [ ] Tôi tránh @Value và final class cho entity JPA thông thường.
- [ ] Tôi có test HashSet trước/sau persist và test proxy.
- [ ] Tôi đã xác định equality cho entity inheritance.

## 18. Câu hỏi ôn tập

**1. Vì sao hai entity có cùng ID có thể không phải cùng một Java object?**

Vì chúng có thể được tải trong các persistence context khác nhau hoặc ở các thời điểm khác nhau. Mỗi context có thể tạo một instance riêng đại diện cho cùng hàng database.

**2. Vì sao không so sánh hai entity transient chỉ bằng ID?**

Vì cả hai thường có ID null. So sánh null với null sẽ khiến hai object mới không liên quan bị xem là bằng nhau.

**3. Vì sao hashCode theo generated ID có thể gây lỗi với HashSet?**

Vì ID được cấp sau khi object đã được thêm vào Set. HashCode thay đổi làm object nằm ở bucket cũ nhưng được tìm ở bucket mới.

**4. Vì sao @Data không phù hợp với entity có quan hệ?**

Vì Lombok sinh equals/hashCode và toString từ nhiều field, có thể kéo theo quan hệ lazy, vòng lặp, field mutable và thay đổi hash ngoài ý muốn.

**5. Có nên đưa collection @OneToMany vào toString() không?**

Không nên. Collection có thể lazy, rất lớn và liên kết ngược về entity hiện tại. In collection có thể gây truy vấn ngoài ý muốn, N+1 hoặc đệ quy.

**6. Khi nào Lombok @EqualsAndHashCode có thể an toàn?**

Khi chỉ include một business key bất biến, không null, duy nhất và được chuẩn hóa thống nhất; đồng thời đã kiểm tra proxy và inheritance của provider. Với generated ID, nên viết equality thủ công để kiểm soát vòng đời.

**7. Khi nào nên giữ equals/hashCode mặc định?**

Khi ứng dụng chỉ cần object identity trong một persistence context và không cần so sánh detached instance đại diện cùng hàng. Đây là lựa chọn hợp lệ và tránh nhiều phức tạp.

Thiết kế equality đúng giúp entity hoạt động ổn định qua các trạng thái transient, managed và detached. Dùng Lombok có chọn lọc giúp giảm mã lặp mà vẫn giữ được kiểm soát đối với identity, lazy loading và vòng đời persistence.