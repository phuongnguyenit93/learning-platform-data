# Thiết kế `equals` và `hashCode` theo vòng đời định danh

Trong Java, `equals(Object)` xác định hai đối tượng có được xem là bằng nhau hay không; `hashCode()` giúp `HashMap`, `HashSet` và các cấu trúc băm tìm đúng phần tử. Với **JPA entity**, thiết kế hai phương thức này khó hơn các lớp Java thông thường vì định danh của một entity có thể **chưa tồn tại lúc tạo đối tượng, được sinh khi persist/flush, và tiếp tục tồn tại khi entity detached**. Ngoài ra, cùng một hàng trong cơ sở dữ liệu có thể xuất hiện dưới các đối tượng Java khác nhau hoặc dưới proxy của ORM.

Câu hỏi cốt lõi không phải “viết `equals` thế nào cho ngắn?” mà là:

> Khi một entity đi từ trạng thái mới tạo đến được lưu, tách khỏi persistence context rồi được tải lại, **điều gì khiến ta kết luận hai đối tượng biểu diễn cùng một thực thể**, và kết luận đó ảnh hưởng thế nào tới các collection dùng hash?

Bài này sử dụng Jakarta Persistence (JPA), ví dụ với Hibernate khi cần nói cụ thể về proxy. Những nguyên tắc về hợp đồng `equals`/`hashCode` thuộc Java; cách tạo ID và vận hành proxy còn phụ thuộc cách cấu hình JPA provider.

## 1. Phân biệt ba loại “giống nhau”

Giả sử hai giao dịch đọc cùng một sản phẩm có khóa chính `id = 42`:

```java
Product a = entityManager1.find(Product.class, 42L);
Product b = entityManager2.find(Product.class, 42L);

System.out.println(a == b);           // Thường là false: hai Java object
System.out.println(a.getId());         // 42
System.out.println(b.getId());         // 42
```

Có ba cách diễn giải:

| Khái niệm | Cách nhận biết | Ý nghĩa |
|---|---|---|
| **Reference identity** | `a == b` | Hai biến cùng trỏ tới một đối tượng Java trong bộ nhớ. |
| **Persistence identity** | Cùng loại entity, cùng khóa chính trong phạm vi dữ liệu thích hợp | Hai đối tượng mô tả cùng một hàng của database. |
| **Business/value equality** | Trùng thuộc tính mang ý nghĩa nghiệp vụ, chẳng hạn mã quốc gia bất biến | Hai đối tượng được coi như cùng một giá trị theo quy tắc miền dữ liệu. |

JPA thường đảm bảo **identity map trong cùng một persistence context**: khi tìm lại cùng một entity bằng cùng định danh, ứng dụng thường nhận lại cùng managed instance. Nhưng điều đó **không đồng nghĩa** các persistence context, phiên làm việc hoặc lần tải khác nhau sẽ trả về cùng Java object.

Một entity có thể dùng `equals` theo database ID, theo khóa nghiệp vụ bất biến, hoặc chỉ dùng tính đồng nhất tham chiếu mặc định. **Cả ba có thể đúng trong những phạm vi khác nhau**, miễn là thiết kế nhất quán với cách dùng entity.

## 2. Hợp đồng `equals` và `hashCode` của Java

### 2.1. Những quy tắc bắt buộc

Với các đối tượng `x`, `y`, `z` không bị thay đổi những trường dùng cho so sánh trong thời gian quan sát:

1. **Phản xạ (reflexive):** `x.equals(x)` phải là `true`.
2. **Đối xứng (symmetric):** `x.equals(y)` và `y.equals(x)` cho cùng kết quả.
3. **Bắc cầu (transitive):** nếu `x.equals(y)` và `y.equals(z)`, thì `x.equals(z)`.
4. **Nhất quán (consistent):** kết quả không thay đổi khi các thông tin quyết định tính bằng nhau không đổi.
5. **Với `null`:** `x.equals(null)` là `false`.
6. **Quan hệ với hash:** nếu `x.equals(y)` là `true`, thì **`x.hashCode() == y.hashCode()`**. Chiều ngược lại không bắt buộc: hai đối tượng có thể trùng hash nhưng không bằng nhau.

Ví dụ, `HashSet` dùng mã hash để xác định vùng lưu trữ rồi mới dùng `equals` để so sánh. Đổi hash của một phần tử **sau khi đã thêm vào Set** có thể làm `contains`/`remove` không tìm lại được phần tử đó.

### 2.2. Vì sao entity dễ vi phạm trong thực tế?

Java object thông thường có thể có ID ngay từ lúc khởi tạo. Với JPA, ID thường là `null` khi entity còn mới:

```java
Product product = new Product("Notebook");
System.out.println(product.getId()); // null trước khi JPA cấp ID
```

Khi ứng dụng gọi `persist` rồi nhà cung cấp JPA hoàn tất thao tác sinh khóa, ID trở thành một giá trị, ví dụ `42`. **Thời điểm chính xác** phụ thuộc chiến lược sinh khóa và provider: `IDENTITY` thường cần INSERT để biết ID, `SEQUENCE` có thể cấp ID trước khi INSERT, còn UUID có thể được cấp bằng cơ chế khác. Không nên lập luận rằng ID chắc chắn xuất hiện ngay sau `persist()` hay chỉ xuất hiện khi commit.

Nếu `hashCode` tính trực tiếp từ ID, đối tượng **đổi vị trí băm ngay trong vòng đời bình thường**. Đây là một lỗi thiết kế phổ biến khi entity được đưa vào collection trước khi lưu.

## 3. Vòng đời JPA ảnh hưởng đến equality như thế nào?

| Trạng thái/tình huống | Entity và ID | Hệ quả đối với `equals`/`hashCode` |
|---|---|---|
| **Transient/new** | Mới tạo bằng `new`; ID sinh tự động thường chưa có (`null`) | Không nên coi hai entity cùng `null` ID là bằng nhau. |
| **Managed trước khi sinh khóa xong** | Được persistence context theo dõi; ID có thể còn `null` tùy chiến lược | Hash phải ổn định nếu entity đã là phần tử `HashSet`. |
| **Managed sau khi có ID** | Có định danh được JPA biết | Có thể so sánh database identity giữa các bản thể hiện. |
| **Detached** | Không còn được context theo dõi, ID thường vẫn được giữ | Một object detached và một object managed có thể biểu diễn cùng hàng. |
| **`merge`** | JPA trả về managed instance; đối tượng truyền vào vẫn là detached | Hai Java object khác nhau có thể cần được xem là cùng entity. |
| **Removed** | Entity được đánh dấu xóa; ID không nhất thiết bị xóa khỏi object | Equality theo ID vẫn có thể trả về true, dù trạng thái tồn tại ở database đã thay đổi. |
| **Proxy/lazy reference** | ORM dùng đối tượng đại diện, có thể là subclass được sinh runtime | `getClass()` và việc đọc thuộc tính phải xét hành vi proxy. |

Vòng đời được minh họa bằng một luồng thường gặp:

```text
new Product()                 persist()               detach()/close()
    |                             |                         |
    v                             v                         v
TRANSIENT ---------------> MANAGED (có thể sinh ID) ------> DETACHED
                                ^                              |
                                |                         merge() trả về
                                +------------------------- managed instance

getReference()/lazy relationship có thể dùng proxy để đại diện entity
```

Các chuyển trạng thái **không đảm bảo giữ nguyên Java object** qua nhiều persistence context. Vì vậy, nếu nghiệp vụ cần so sánh các bản thể hiện từ nhiều phiên làm việc, giữ `Object.equals` mặc định có thể không đáp ứng được.

## 4. Hai lỗi thường gặp với ID tự sinh

### 4.1. Lỗi thứ nhất: hai entity mới đều có ID bằng `null`

Một cách viết dễ gặp:

```java
@Override
public boolean equals(Object other) {
    if (!(other instanceof Product p)) {
        return false;
    }
    return Objects.equals(this.id, p.id);
}
```

Giả sử hai sản phẩm chưa được lưu:

```java
Product first = new Product("A");
Product second = new Product("B");

// first.id == null và second.id == null
System.out.println(first.equals(second)); // true: kết quả không mong muốn
```

`Objects.equals(null, null)` trả về `true`. Nhưng hai entity mới được tạo riêng biệt **chưa có bằng chứng rằng chúng là một bản ghi duy nhất**. Nếu dùng kiểu equality theo khóa chính, quy tắc thường cần là:

- Cùng một tham chiếu Java thì bằng nhau.
- Hai tham chiếu khác nhau chỉ bằng nhau nếu **cả hai thuộc cùng loại entity thích hợp và ID đã có giá trị, lại bằng nhau**.
- Hai entity riêng biệt có `id == null` không bằng nhau.

### 4.2. Lỗi thứ hai: hash thay đổi khi có ID

Một cách triển khai sai khi ID được sinh sau lúc tạo entity:

```java
@Override
public int hashCode() {
    return Objects.hashCode(id);
}
```

Tình huống:

```java
Product product = new Product("A");
Set<Product> products = new HashSet<>();

products.add(product);      // Hash dựa trên id = null

entityManager.persist(product);
entityManager.flush();      // Minh họa thời điểm ID đã được tạo

System.out.println(products.contains(product));
// Có thể false nếu hash sau khi sinh ID khác hash lúc add.
```

`HashSet` không tự chuyển phần tử sang bucket mới khi giá trị dùng tính hash thay đổi. Dù `equals` xử lý ID rất cẩn thận, **hashCode biến động vẫn gây lỗi collection**.

Không nên giải quyết bằng việc chỉ gọi `remove` rồi `add` sau mỗi lần persist: cách đó tạo thêm nghĩa vụ khó bảo đảm, nhất là khi entity được nhiều collection hoặc map sử dụng.

## 5. Mẫu thiết kế với ID được JPA sinh

Một chiến lược phổ biến là **so sánh ID chỉ sau khi ID khác null**, đồng thời trả về **hash không phụ thuộc ID**, ổn định trong vòng đời entity.

### 5.1. Ví dụ cho entity không tham gia hệ kế thừa JPA

```java
package com.example.shop.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Product() {
        // JPA cần constructor không tham số.
    }

    public Product(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof Product that)) {
            return false;
        }

        Long currentId = getId();
        return currentId != null && currentId.equals(that.getId());
    }

    @Override
    public int hashCode() {
        return Product.class.hashCode();
    }
}
```

Giải thích từng quyết định:

- `this == other` giữ tính phản xạ, cả khi ID vẫn là `null`.
- `instanceof Product` chấp nhận đối tượng proxy kế thừa `Product` trong mô hình proxy subclass thông dụng của Hibernate.
- `currentId != null` ngăn hai entity transient khác nhau bị coi là bằng nhau.
- `getId()` biểu đạt việc lấy khóa từ entity, thay vì truy cập thẳng field trên đối tượng đối diện; điều này quan trọng khi đối diện là proxy chưa được khởi tạo.
- `Product.class.hashCode()` không đổi khi ID chuyển từ `null` sang giá trị được sinh. Hai `Product` khác nhau có thể trùng hash; **được phép** theo hợp đồng Java.

Mẫu trên **giả định `Product` không có entity subclass được so sánh chung**. Trong hệ kế thừa JPA, `instanceof` có thể quá rộng; cần quyết định chính sách phân biệt loại entity trước khi áp dụng.

Nếu so sánh một entity đã lưu với entity được tải từ persistence context khác, cả hai có cùng ID hợp lệ thì `equals` trả về true. Nếu hai entity đều chưa có ID và khác tham chiếu, `equals` trả về false.

### 5.2. Tính chất ổn định của hash

Giả sử `product` được thêm vào Set khi còn transient:

```java
Product product = new Product("A");
Set<Product> products = new HashSet<>();

products.add(product);

int beforePersist = product.hashCode();

entityManager.persist(product);
entityManager.flush();

int afterPersist = product.hashCode();

System.out.println(beforePersist == afterPersist); // true
System.out.println(products.contains(product));    // true
```

Trong ví dụ, giá trị hash luôn là hash của literal class `Product.class`, không phụ thuộc trường `id` hay `name`. Đây là **lý do dùng hash cố định theo loại entity**, không phải cách tăng tốc: nhiều object `Product` sẽ có cùng hash và phải kiểm tra `equals` nhiều hơn.

**Đánh đổi:** với collection băm rất lớn gồm nhiều phần tử cùng loại, hash cố định có thể làm hiệu năng suy giảm đáng kể do va chạm. Khi cần index hàng chục/ngàn đối tượng theo khóa, thường tốt hơn dùng `Map<Long, Product>` theo ID đã ổn định hoặc cấu trúc dữ liệu chuyên biệt, thay vì đưa toàn bộ entity vào `HashSet` theo mẫu trên.

### 5.3. Mẫu này không xóa mọi rủi ro của mutable equality

Hash ổn định giúp phần tử không “lạc bucket” khi ID xuất hiện. Tuy vậy, **quan hệ equality của entity vẫn thay đổi** từ “chưa có định danh nên khác nhau” sang “có cùng ID nên bằng nhau”. Vì thế, không nên thiết kế logic nghiệp vụ phụ thuộc vào việc thành viên của Set tự phản ánh những thay đổi định danh giữa các object khác nhau.

Ví dụ, tránh trộn trong cùng Set các object detached, managed, proxy cùng đại diện một hàng rồi kỳ vọng Set có thể sửa chữa mọi trường hợp trùng lặp nếu ID hoặc loại entity thay đổi. Khi cần khóa ổn định cho cấu trúc băm, ưu tiên **giá trị định danh bất biến** hơn bản thân entity.

## 6. Chọn khóa nghiệp vụ bất biến (natural key)

### 6.1. Khi nào natural key phù hợp?

Đôi khi entity có một thuộc tính nghiệp vụ **thật sự duy nhất và không đổi từ lúc tạo đến lúc xóa**, chẳng hạn mã quốc gia ISO trong phạm vi đã xác định hoặc mã danh mục bất biến được cấp ngay khi khởi tạo. Khi đó, `equals` và `hashCode` có thể dựa trên khóa nghiệp vụ, không cần đợi ID do database sinh.

Natural key nên thỏa mãn:

1. Có giá trị ngay khi đối tượng trở thành một entity hợp lệ.
2. Không đổi trong suốt vòng đời ứng dụng; không có setter hoặc luồng đổi giá trị.
3. Duy nhất trong đúng phạm vi nhận diện entity (ví dụ toàn hệ thống hoặc theo tenant).
4. Có quy tắc chuẩn hóa rõ: chữ hoa/thường, khoảng trắng, dấu, Unicode...
5. Được cơ sở dữ liệu ràng buộc bằng `UNIQUE` hoặc khóa tương ứng, không chỉ kiểm tra ở Java.

### 6.2. Ví dụ mã quốc gia không đổi

```java
package com.example.catalog.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.util.Locale;
import java.util.Objects;

@Entity
@Table(name = "countries")
public class Country {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "iso_code", nullable = false,
            unique = true, updatable = false, length = 2)
    private String isoCode;

    protected Country() {
        // JPA khởi tạo rồi nạp các trường.
    }

    public Country(String isoCode) {
        this.isoCode = Objects.requireNonNull(isoCode)
                              .trim()
                              .toUpperCase(Locale.ROOT);
    }

    public String getIsoCode() {
        return isoCode;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof Country that)) {
            return false;
        }
        return getIsoCode() != null
                && getIsoCode().equals(that.getIsoCode());
    }

    @Override
    public int hashCode() {
        return Objects.hashCode(getIsoCode());
    }
}
```

Một `Country("VN")` và một `Country("vn")` được chuẩn hóa về cùng mã, nên có thể bằng nhau **ngay khi còn transient**, trong khi ID database vẫn khác null hoặc chưa có. Điều này đúng **nếu nghiệp vụ thực sự xem chúng là cùng một quốc gia**.

Cẩn trọng:

- `updatable = false` là hướng dẫn ghi cột của JPA, **không đủ** để ngăn mã ứng dụng thay đổi field qua reflection, SQL ngoài JPA hay các con đường khác. Cần giữ bất biến ở tầng miền dữ liệu và schema.
- Nếu mã có thể được đổi tên, tái sử dụng, cấp lại hoặc mang ý nghĩa khác theo thời gian, nó **không phải khóa equality tốt**.
- Với proxy chưa được khởi tạo, truy cập `getIsoCode()` có thể buộc ORM thực hiện SELECT; nếu session đã đóng, thao tác có thể thất bại. Equality dựa trên natural key không miễn nhiễm với lazy loading.
- Nếu mã chỉ duy nhất **trong tenant**, so sánh mỗi `isoCode` là sai: hai bản ghi thuộc hai tenant khác nhau có thể có cùng mã. Cần bao gồm định danh tenant ổn định, hoặc dùng một khóa được bảo đảm duy nhất trong phạm vi ứng dụng.

Trong Hibernate, `@NaturalId` có thể hỗ trợ mapping/tra cứu natural ID; đây là **tính năng riêng Hibernate**, không phải điều kiện bắt buộc để Java `equals` hoạt động. Việc gắn `@NaturalId` cũng **không tự thay thế** quy tắc equals/hashCode hoặc ràng buộc dữ liệu ở CSDL.

### 6.3. Khi nào không nên dùng natural key?

Những trường thường **không phù hợp** làm natural key nếu có thể thay đổi:

- Email, số điện thoại, tên đăng nhập trong hệ thống cho phép đổi.
- Tên sản phẩm, trạng thái đơn hàng, địa chỉ, số lượng.
- Giá tiền, ngày sửa gần nhất, tổng tiền tính toán.
- Một tập hợp quan hệ như `Set<OrderLine>`, đặc biệt nếu dùng lazy loading.

Các giá trị này có thể thay đổi ngay khi entity đang ở trong `HashSet` hoặc đang là key của `HashMap`, dẫn đến cùng vấn đề hash bất ổn như ID được sinh sau khi persist.

## 7. ID được cấp ổn định từ lúc tạo object

Một lựa chọn khác là **tự cấp định danh bất biến trước khi entity được sử dụng**, ví dụ UUID tạo trong constructor, rồi dùng nó để tính equality/hash. Đây là **assigned identifier**, khác với việc provider cấp ID sau khi gọi `persist`.

```java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.util.Objects;
import java.util.UUID;

@Entity
@Table(name = "shipments")
public class Shipment {

    @Id
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    protected Shipment() {
        // Constructor cho JPA; ID sẽ được nạp từ DB.
    }

    public Shipment(String reference) {
        this.id = UUID.randomUUID();
        this.reference = Objects.requireNonNull(reference);
    }

    @Column(name = "reference", nullable = false)
    private String reference;

    public UUID getId() {
        return id;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof Shipment that)) return false;

        UUID currentId = getId();
        return currentId != null && currentId.equals(that.getId());
    }

    @Override
    public int hashCode() {
        return Objects.hashCode(getId());
    }
}
```

Ở đây, constructor nghiệp vụ thiết lập ID **trước khi object xuất hiện trong collection**. Vì ID không được thay đổi sau đó, hash theo ID có thể ổn định từ transient đến detached. Constructor không tham số chỉ dành cho JPA khởi tạo đối tượng và hydrate field; không đưa một entity chưa được nạp ID vào collection.

Phải phân biệt với:

```java
@Id
@GeneratedValue(strategy = GenerationType.UUID)
private UUID id;
```

`@GeneratedValue(strategy = UUID)` là cách nhờ JPA provider tạo ID; **không bảo đảm ID đã tồn tại ngay khi constructor người dùng chạy**. Nếu dùng generated ID thì vẫn phải xét giai đoạn `null` trước persist và độ ổn định của `hashCode`.

Assigned identifier mang theo trách nhiệm đảm bảo tính duy nhất, không thay ID, cấu hình column/schema phù hợp với loại UUID và xử lý nếu có xung đột hiếm gặp. Không phải entity nào cũng nên chọn UUID chỉ để đơn giản hóa `equals`.

## 8. Proxy, `getClass()` và hệ kế thừa entity

### 8.1. Vì sao `getClass()` dễ gây bất ngờ?

Hibernate thường dùng proxy khi truy xuất quan hệ lazy hoặc gọi `getReference`. Proxy có thể là một subclass được tạo runtime:

```text
Product                      Product$HibernateProxy$...
   ^                                     |
   |-------------------------------------+
      proxy kế thừa Product
```

Khi đó:

```java
managedProduct.getClass() == proxyProduct.getClass()
```

có thể là `false` dù cả hai đại diện cùng hàng. Nếu `equals` bắt buộc `getClass() == other.getClass()`, hai bản thể hiện có thể bị xem là khác nhau. Dùng `instanceof Product` thường tương thích hơn với proxy kế thừa `Product`, nhưng chỉ an toàn khi chính sách equality của hệ phân cấp cho phép.

Một số Hibernate API có thể tìm “persistent class” của proxy. Tuy nhiên, phương pháp như `Hibernate.getClass(proxy)` có thể khởi tạo proxy trong các phiên bản/ngữ cảnh nhất định; nếu chỉ để tính equality, việc này có thể gây truy vấn hoặc lỗi ngoài session. Không nên xem mọi API xác định class là hoàn toàn miễn phí.

### 8.2. Cạm bẫy với inheritance

Giả sử:

```java
@Entity
@Inheritance(strategy = InheritanceType.TABLE_PER_CLASS)
public abstract class Payment {
    @Id
    private Long id;
}

@Entity
public class CardPayment extends Payment {
}

@Entity
public class CashPayment extends Payment {
}
```

Nếu `Payment.equals` chỉ kiểm tra `other instanceof Payment` và `id`, một `CardPayment(id=7)` và một `CashPayment(id=7)` có thể bị coi là bằng nhau dù chúng là **hai loại/thực thể khác nhau** nếu cách cấp khóa cho phép trùng giá trị. Ngay cả khi ID toàn hệ thống là duy nhất, business semantics vẫn cần quyết định liệu các subtype có nên được so sánh chung hay không.

Khi có entity inheritance, phải xác định rõ:

- Equality phân biệt **concrete persistent entity type** hay dùng toàn bộ hierarchy như một loại?
- ID có duy nhất xuyên suốt hierarchy không, hay chỉ duy nhất theo bảng/subtype?
- Proxy có biểu diễn đúng concrete type khi chưa initialize không?
- Liệu subclass có override `equals` và phá vỡ tính đối xứng/bắc cầu của base class không?

Một chiến lược theo **concrete persistent class + non-null ID** thường phù hợp khi các subtype là các loại entity độc lập. Nhưng cách xác định concrete persistent class dưới proxy **phụ thuộc provider**, đặc biệt với quan hệ đa hình; không nên áp dụng một utility chung bằng `getClass()` hay `instanceof` khi chưa định nghĩa rõ chính sách.

Nếu dự án dùng riêng Hibernate và biết proxy liên quan, có thể tham khảo cách truy xuất metadata qua `HibernateProxy`:

```java
import org.hibernate.proxy.HibernateProxy;

static Class<?> persistentClass(Object object) {
    if (object instanceof HibernateProxy proxy) {
        return proxy.getHibernateLazyInitializer().getPersistentClass();
    }
    return object.getClass();
}
```

Đây là **ví dụ API riêng Hibernate**, không thuộc Jakarta Persistence chuẩn. Trong một số ánh xạ đa hình, proxy có thể được tạo theo kiểu được khai báo ở association trước khi biết subtype thực, nên giá trị class cần được hiểu theo bối cảnh. Nếu dùng cách này, `equals` và `hashCode` phải **cùng dựa trên một chính sách phân loại** và không được vô tình gây truy vấn lazy hoặc bất đối xứng.

### 8.3. Tránh đọc trực tiếp field của proxy trong `equals`

Với proxy chưa được khởi tạo, mã kiểu:

```java
return id != null && id.equals(((Product) other).id);
```

có thể đọc field chưa hydrate trong proxy, khiến equality sai ngay cả khi proxy biết ID của hàng. Mã sử dụng getter `getId()` thường phù hợp hơn, vì proxy/provider có đường lấy identifier riêng. Tuy nhiên, khả năng lấy ID mà không initialize cũng phụ thuộc provider, mapping và chế độ tuân thủ proxy; tránh dựa vào giả định không bao giờ có SQL.

**Không thêm `final` cho entity class chỉ để cố định equals/hashCode** khi ứng dụng cần proxy subclass: trong nhiều cấu hình ORM, class final hoặc những method final có thể hạn chế khả năng tạo proxy/intercept.

## 9. `merge`, detached và managed: so sánh sau nhiều phiên làm việc

Một ví dụ điển hình:

```java
// em1 và em2 là hai EntityManager khác nhau.
// Product có ID được JPA cấp và equals theo non-null ID.

Product detached;
EntityManager em1 = emf.createEntityManager();
try {
    detached = em1.find(Product.class, 42L);
} finally {
    em1.close(); // detached sau khi context đóng
}

EntityManager em2 = emf.createEntityManager();
try {
    em2.getTransaction().begin();
    Product managed = em2.merge(detached);

    System.out.println(detached == managed);      // Có thể false
    System.out.println(detached.equals(managed)); // true nếu cùng ID và type
    em2.getTransaction().commit();
} finally {
    em2.close();
}
```

`merge(detached)` **trả về bản thể hiện managed** sau khi hợp nhất trạng thái; nó không biến chính đối tượng truyền vào thành managed. Trong cùng context, managed entity tương ứng có thể đã tồn tại. Bởi vậy, reference identity không phải cách đáng tin cậy để nối logic giữa detached DTO/view model với managed entity.

Cần phân biệt **hai loại câu hỏi**:

- “Hai đối tượng có cùng database identity không?” → equality theo ID có thể hữu ích.
- “Hai đối tượng có cùng nội dung/trạng thái tại thời điểm này không?” → hãy so sánh field được chọn, DTO hoặc version; cùng ID không có nghĩa thuộc tính đã cập nhật giống nhau.

Ví dụ, bản detached cũ có `name = "Old"` và bản managed mới có `name = "New"` vẫn có thể bằng nhau theo ID, vì chúng đại diện **cùng hàng**, dù dữ liệu quan sát đã khác. Nếu muốn phát hiện xung đột ghi đồng thời, sử dụng `@Version` và cơ chế optimistic locking thích hợp; `equals` không giải quyết xung đột cập nhật.

## 10. ID ghép và value objects

### 10.1. Khác biệt giữa equality của entity và khóa chính ghép

Với `@EmbeddedId` hoặc `@IdClass`, **lớp biểu diễn composite primary key** cần có `equals` và `hashCode` theo **các thành phần khóa**. Đây là hợp đồng cho **giá trị khóa**, khác với entity có generated ID chuyển từ null sang non-null.

Ví dụ khóa của một dòng đơn hàng gồm `orderId` và `lineNumber`:

```java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class OrderLineId implements Serializable {

    @Column(name = "order_id")
    private Long orderId;

    @Column(name = "line_number")
    private Integer lineNumber;

    protected OrderLineId() {
    }

    public OrderLineId(Long orderId, Integer lineNumber) {
        this.orderId = Objects.requireNonNull(orderId);
        this.lineNumber = Objects.requireNonNull(lineNumber);
    }

    public Long getOrderId() {
        return orderId;
    }

    public Integer getLineNumber() {
        return lineNumber;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof OrderLineId that)) return false;

        return Objects.equals(orderId, that.orderId)
            && Objects.equals(lineNumber, that.lineNumber);
    }

    @Override
    public int hashCode() {
        return Objects.hash(orderId, lineNumber);
    }
}
```

Có thể dùng trong một entity:

```java
@Entity
@Table(name = "order_lines")
public class OrderLine {

    @EmbeddedId
    private OrderLineId id;

    // Những trường nghiệp vụ khác ...
}
```

Ở đây, hai `OrderLineId(42L, 1)` có cùng value và hash. Các thành phần của khóa cần **ổn định khi đối tượng được dùng làm key**; không thay `orderId` hoặc `lineNumber` sau khi chèn vào `HashMap`. Nếu JPA sử dụng `@MapsId` để ghép khóa từ quan hệ cha, hãy cẩn thận với thời điểm ID cha được cấp; khóa ghép có thể chưa đầy đủ lúc entity con còn transient.

Trong mô hình `@IdClass`, lớp khóa cũng cần triển khai equality/hash dựa trên các thuộc tính ID tương ứng và tuân thủ yêu cầu về key class. Với value objects `@Embeddable` khác, value equality cũng thường hợp lý nếu các trường quyết định giá trị được định nghĩa rõ.

### 10.2. Tránh lấy cả quan hệ entity làm hash của khóa

Một khóa có `orderId` kiểu `Long` ổn định, dễ hiểu hơn việc dùng đối tượng `Order` đầy đủ với thuộc tính và quan hệ có thể lazy. Nếu `hashCode` của key đi sâu vào `order.getLines()` hoặc các entity liên quan, nó có thể kích hoạt tải dữ liệu, vòng lặp quan hệ, thậm chí `StackOverflowError`.

Khi entity con có khóa ghép và quan hệ cha, hãy phân biệt **giá trị khóa** với **object graph**. Chỉ dùng các phần tử định danh thực sự cần thiết để so sánh khóa.

## 11. Những cách triển khai nên tránh

| Cách làm | Vấn đề | Cách suy nghĩ thay thế |
|---|---|---|
| `Objects.equals(id, other.id)` mà không xử lý `null` | Hai entity transient khác nhau cùng ID null bị xem là bằng nhau | Nếu equality theo ID: cùng reference hoặc ID khác null và bằng nhau |
| `hashCode() = id.hashCode()` với generated ID | Hash đổi từ trước sang sau khi sinh ID | Hash ổn định theo loại entity, hoặc cấp ID bất biến từ lúc tạo |
| Dùng tất cả field trong `equals` | Field có thể mutable; lazy association có thể phát sinh truy vấn hoặc vòng lặp | Chọn khóa identity hoặc business key bất biến |
| Dùng `getClass()` trực tiếp với proxy | Proxy subclass có class runtime khác entity thật | Xác định chiến lược proxy và entity hierarchy |
| Dùng `instanceof` trong mọi entity hierarchy | Subtype khác nhau có thể bị xem là bằng nhau nếu ID trùng | Xác định loại thực thể và phạm vi duy nhất của ID |
| Dựa vào `@Id` rồi tin rằng `equals` tự đúng | Annotation chỉ khai báo persistence ID, không sinh `equals` của Java | Triển khai equality có chủ đích nếu ứng dụng cần |
| Dùng `@Data` của Lombok cho mọi entity | Có thể sinh equals/hash/toString theo field/quan hệ, phát sinh SQL và vòng lặp | Chỉ sinh method đã xem xét; viết equals/hash rõ ràng |
| `@EqualsAndHashCode(of = "id")` trực tiếp với generated ID | Có thể gặp cả vấn đề `null` và hash thay đổi | Kiểm tra hợp đồng trước khi chọn annotation tự sinh |
| So sánh các entity bằng mọi quan hệ `@OneToMany` | Quan hệ thay đổi, có thể lazy, và dễ đệ quy | So sánh ID hoặc key ổn định, để logic so nội dung ở nơi khác |
| Cho entity làm key của `Map` ở mọi nơi | Khóa có thể sinh muộn, phụ thuộc proxy/type/tenant | Dùng ID/DTO/key bất biến làm key khi phù hợp |

### 11.1. Đặc biệt chú ý Lombok

Một entity có:

```java
@Data
@Entity
class Order {
    @Id
    @GeneratedValue
    private Long id;

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines;
}
```

có thể nhận `equals`, `hashCode` và `toString` được sinh theo nhiều thuộc tính, bao gồm association, tùy cấu hình Lombok. Điều này có thể dẫn đến:

- Tải collection lazy chỉ vì framework/log gọi `toString` hoặc collection gọi `hashCode`.
- Lặp vô hạn khi `Order` tham chiếu `OrderLine`, còn `OrderLine` tham chiếu ngược lại `Order`.
- Hash thay đổi khi thêm/xóa dòng hàng hoặc khi ID được sinh.

Có thể dùng riêng `@Getter`/`@Setter` có kiểm soát và tự định nghĩa equality theo nguyên tắc của entity. Không nên kết luận “annotation nào cũng xấu”; vấn đề là **quy tắc được sinh có phù hợp với vòng đời entity hay không**.

## 12. Khi nào giữ `equals`/`hashCode` mặc định là hợp lý?

Không phải tất cả entity đều bắt buộc override. Mặc định từ `Object` biểu diễn **reference identity**:

```java
Product a = entityManager.find(Product.class, 42L);
Product b = entityManager.find(Product.class, 42L);

// Trong cùng persistence context, thường là cùng managed instance.
System.out.println(a == b); // true
```

Nếu entity chỉ được thao tác **trong một persistence context**, không làm phần tử Set hay Map key theo database identity, và ứng dụng không so sánh detached/managed từ các context khác nhau, việc giữ cách mặc định có thể đơn giản và an toàn.

Tuy vậy, khi dùng `Set<Entity>` để biểu diễn quan hệ nghiệp vụ, trả entity từ API rồi trộn vào collection, hoặc hợp nhất nhiều nguồn dữ liệu, reference identity thường quá yếu. Khi đó hãy chọn một chính sách equality trước khi entity được phổ biến trong mã ứng dụng.

Một điểm cần nhận thức: định danh “cùng lớp, cùng ID” còn phụ thuộc **phạm vi database**. Nếu cùng một class `Product` được ánh xạ sang hai tenant/schema/database có thể cùng ID `42`, chỉ so sánh `Product.class` và `42` sẽ coi hai bản ghi độc lập là bằng nhau. Trong kiến trúc đa tenant, cần thiết kế định danh duy nhất theo phạm vi dùng object, hoặc tránh trộn entity khác tenant khi chưa có ngữ nghĩa equality phù hợp.

## 13. Cách lựa chọn chiến lược theo nhu cầu

| Tình huống | Gợi ý | Điều kiện cần giữ |
|---|---|---|
| Entity có ID do DB/provider sinh, phải so sánh detached/managed | Non-null ID equality + hash ổn định không phụ thuộc ID | Xử lý proxy, subtype, tenant đúng phạm vi |
| Entity có mã nghiệp vụ duy nhất và bất biến từ lúc tạo | Natural-key equality và hash theo key | Giá trị luôn có, chuẩn hóa ổn định, DB ràng buộc unique |
| Ứng dụng tự cấp UUID/ID bất biến ngay trong constructor | Equality/hash dựa trên assigned ID | ID không đổi, không sử dụng object chưa hoàn tất khởi tạo |
| Entity chỉ tồn tại trong một persistence context, không có yêu cầu so sánh xuyên context | Có thể giữ reference equality mặc định | Không kỳ vọng các instance tải lại từ context khác sẽ bằng nhau |
| Lớp primary key composite `@EmbeddedId`/`@IdClass` | Value equality/hash theo toàn bộ thành phần khóa | Thành phần khóa ổn định khi dùng làm key |
| Mô hình entity inheritance và lazy proxy phức tạp | Định nghĩa chính sách theo persistent type và ID có kiểm soát | Không phá symmetry/transitivity; không kích hoạt load ngoài ý muốn |
| Collection tra cứu cực lớn theo ID | `Map<Id, Entity>` với key bất biến | ID có giá trị, phạm vi key phù hợp và không đổi |

Một thứ tự ra quyết định dễ dùng:

1. **Cần so sánh hai instance từ persistence context khác nhau không?** Nếu không, cân nhắc giữ reference identity.
2. **Có business key hoàn toàn bất biến, duy nhất và có ngay khi tạo không?** Nếu có, natural-key equality là ứng viên.
3. **ID có được gán ổn định trước khi entity được sử dụng không?** Nếu có, có thể dùng ID làm cả equality và hash.
4. **ID được sinh sau khi entity được tạo?** Nếu cần override, dùng quy tắc non-null ID và hash ổn định; xét kỹ việc dùng collection.
5. **Có proxy, inheritance hoặc multi-tenancy không?** Xác định loại và phạm vi identity phù hợp trước khi nhân rộng mẫu cho mọi entity.

Đây là hướng dẫn lựa chọn, không phải công thức luôn đúng cho toàn bộ domain model. Đôi khi hai aggregate khác nhau cần hai chiến lược khác nhau, nhưng **trong cùng một loại entity, toàn bộ ứng dụng phải dùng quy tắc thống nhất**.

## 14. Tình huống thực hành để tự giải thích

### Tình huống A: Entity mới trong `HashSet`

Bạn tạo hai `Product`, mỗi object có `id == null`, rồi thêm cả hai vào `HashSet`. Sau đó một object được persist. Hãy trả lời:

- Nếu `equals` dùng `Objects.equals(id, other.id)`, Set có thể giữ được cả hai phần tử ngay từ đầu không?
- Nếu `hashCode` dựa trên ID, vì sao `contains(product)` có thể trả về false sau persist?
- Mẫu non-null ID + class-constant hash thay đổi kết quả nào? Có đánh đổi gì về hiệu năng?

### Tình huống B: Detached và merged

Một entity được load trong phiên A rồi tách khỏi context. Trong phiên B, cùng ID được tải lại hoặc hợp nhất bằng `merge`. Hãy giải thích vì sao `==` có thể false nhưng `equals` theo ID là true, và vì sao điều này **không có nghĩa nội dung hai object giống hệt nhau**.

### Tình huống C: Proxy

Một repository trả về entity đã khởi tạo; một association lazy trả về proxy cho cùng ID. So sánh `getClass()`, `instanceof` và getter `getId()`. Hãy dự đoán điểm nào có thể phát sinh hành vi khác khi dùng provider hoặc mapping khác.

### Tình huống D: Business key có thể thay đổi

Một entity `User` được so sánh theo email, nhưng ứng dụng cho phép sửa email. Nếu đưa user vào `HashMap<User, Permission>` rồi đổi email, điều gì xảy ra? Có nên dùng khóa email hay một định danh bất biến hơn?

### Tình huống E: Hai tenant

Hai database độc lập đều có `Product(id=10)`. Nếu đối tượng từ cả hai database đi vào cùng một batch xử lý, equality theo `Product.class + id` có còn phân biệt hai thực thể không? Cần giới hạn phạm vi collection hay đưa tenant identity vào cách biểu diễn khóa?

## 15. Ghi nhớ cốt lõi

**`equals` của JPA entity phải phản ánh khái niệm identity được chọn; `hashCode` phải tương thích với identity đó và ổn định khi entity được dùng trong cấu trúc băm.**

Với generated ID, hai entity mới khác nhau không nên bằng nhau chỉ vì cả hai có `id == null`, và không nên tính hash trực tiếp từ ID khi ID có thể xuất hiện sau khi thêm đối tượng vào Set. Với business key hoặc assigned ID, việc dùng key làm equality/hash chỉ phù hợp khi key thực sự **duy nhất, bất biến và đã có từ thời điểm sử dụng**.

Ngoài các quy tắc Java, ORM còn có proxy, persistence context, `merge`, entity inheritance và phạm vi database/tenant. Vì thế thiết kế tốt cần xét **toàn bộ vòng đời định danh**, không chỉ một thời điểm entity đã có ID.
