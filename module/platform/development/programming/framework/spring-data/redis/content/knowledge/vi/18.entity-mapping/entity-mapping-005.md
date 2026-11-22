# Ánh xạ collection, map và đường dẫn thuộc tính trong Spring Data Redis

Khi lưu một thực thể Java vào Redis thông qua **Spring Data Redis Repositories**, ứng dụng thường không phải tự chuyển từng thuộc tính thành lệnh `HSET`. Spring Data Redis dùng cơ chế **object mapping** để chuyển đối tượng và các thuộc tính lồng nhau thành dữ liệu Redis có thể lưu và đọc lại. Với `List`, `Set`, `Map` và đối tượng lồng nhau, điểm quan trọng là hiểu **đường dẫn thuộc tính** (*property path*): cách một trường con được biểu diễn bằng tên field trong Redis Hash.

Bài này tập trung vào ánh xạ thực thể qua `@RedisHash`, `@Id`, `RedisRepository` và `MappingRedisConverter`, đồng thời phân biệt nó với việc thao tác trực tiếp các cấu trúc Redis List, Set, Hash hay JSON.

## 1. Mô hình lưu thực thể: một key Redis Hash, nhiều field

Giả sử ứng dụng có một sản phẩm với mã `p-100`, tên hiển thị, danh sách biến thể, tập nhãn và thông số kỹ thuật. Trong Java, đây là một **object graph**: thực thể gốc chứa những thuộc tính đơn giản, các collection và các object con. Với kiểu ánh xạ Redis repository thông thường, Spring Data Redis lưu thực thể gốc dưới một key như:

```text
products:p-100
```

Giá trị tại key này là một **Redis Hash**: mỗi thuộc tính được chuyển thành một hoặc nhiều cặp `field -> value`.

```text
Redis key: products:p-100
Redis type: hash

name                              -> "Bàn học"
origin.city                       -> "Hà Nội"
origin.country                    -> "VN"
variants.[0].sku                  -> "DESK-BLACK"
variants.[0].stock                -> "12"
variants.[1].sku                  -> "DESK-WHITE"
variants.[1].stock                -> "7"
specifications.[material]         -> "wood"
specifications.[widthCm]          -> "120"
tags.[0]                          -> "furniture"
tags.[1]                          -> "workspace"
```

Đây là **minh họa dạng field path** thường gặp, không phải cam kết về thứ tự hiển thị hoặc biểu diễn byte chính xác của mọi cấu hình serializer. Redis Hash không bảo đảm thứ tự field khi `HGETALL`; các field kỹ thuật như `_class`, `id` hoặc thông tin phục vụ mapping có thể xuất hiện tùy mô hình và cấu hình. Với `Set`, vị trí chỉ số minh họa không nên được coi là thứ tự ổn định.

Điểm cốt lõi: một Java `List` nằm trong entity **không mặc nhiên trở thành Redis List**; một `Set<String>` trong entity **không mặc nhiên trở thành Redis Set**. Chúng có thể được trải thành các field của **cùng một Redis Hash** do cơ chế repository mapping quản lý.

### 1.1. Ba cấp đường dẫn

| Dạng thuộc tính Java | Ví dụ đường dẫn trong Redis Hash | Ý nghĩa |
|---|---|---|
| Giá trị đơn | `name` | Field trực tiếp của thực thể |
| Object lồng nhau | `origin.city` | Thuộc tính `city` bên trong `origin` |
| Collection theo vị trí | `variants.[0].sku` | `sku` của phần tử ở vị trí `0` trong `variants` |
| Map theo khóa | `specifications.[material]` | Giá trị ứng với khóa `"material"` |
| Map chứa object | `offices.[hanoi].city` | `city` trong object nằm ở map key `"hanoi"` |
| Collection các giá trị đơn | `photoUrls.[1]` | Phần tử ở vị trí `1` trong danh sách |

Các đoạn nối bằng dấu chấm diễn tả chiều sâu của cấu trúc Java. Cặp ngoặc vuông `[...]` diễn tả **phần tử collection** hoặc **khóa map**. Không nên coi chuỗi này là cú pháp truy vấn đặc biệt của Redis: với lệnh `HGET`, toàn bộ `variants.[0].sku` chỉ là **tên một hash field**.

## 2. Tạo thực thể có `List`, `Set`, `Map` và object lồng nhau

Ví dụ dưới đây dùng các POJO thông thường. Mỗi lớp có constructor không tham số và phương thức truy cập để Spring Data có thể tạo, đọc và ghi dữ liệu.

```java
package com.example.catalog;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("products")
public class Product {

    @Id
    private String id;

    private String name;

    private Origin origin;

    private List<Variant> variants = new ArrayList<>();

    private Map<String, String> specifications = new LinkedHashMap<>();

    private Set<String> tags = new LinkedHashSet<>();

    public Product() {
    }

    public Product(String id, String name) {
        this.id = id;
        this.name = name;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public Origin getOrigin() { return origin; }
    public void setOrigin(Origin origin) { this.origin = origin; }

    public List<Variant> getVariants() { return variants; }
    public void setVariants(List<Variant> variants) { this.variants = variants; }

    public Map<String, String> getSpecifications() { return specifications; }
    public void setSpecifications(Map<String, String> specifications) {
        this.specifications = specifications;
    }

    public Set<String> getTags() { return tags; }
    public void setTags(Set<String> tags) { this.tags = tags; }
}
```

Đối tượng lồng nhau:

```java
package com.example.catalog;

public class Origin {

    private String city;
    private String country;

    public Origin() {
    }

    public Origin(String city, String country) {
        this.city = city;
        this.country = country;
    }

    public String getCity() { return city; }
    public void setCity(String city) { this.city = city; }

    public String getCountry() { return country; }
    public void setCountry(String country) { this.country = country; }
}
```

Phần tử của `List<Variant>`:

```java
package com.example.catalog;

public class Variant {

    private String sku;
    private int stock;

    public Variant() {
    }

    public Variant(String sku, int stock) {
        this.sku = sku;
        this.stock = stock;
    }

    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }

    public int getStock() { return stock; }
    public void setStock(int stock) { this.stock = stock; }
}
```

Repository:

```java
package com.example.catalog;

import org.springframework.data.repository.CrudRepository;

public interface ProductRepository extends CrudRepository<Product, String> {
}
```

Ví dụ ghi một thực thể:

```java
Product product = new Product("p-100", "Bàn học");
product.setOrigin(new Origin("Hà Nội", "VN"));

product.getVariants().add(new Variant("DESK-BLACK", 12));
product.getVariants().add(new Variant("DESK-WHITE", 7));

product.getSpecifications().put("material", "wood");
product.getSpecifications().put("widthCm", "120");

product.getTags().add("furniture");
product.getTags().add("workspace");

productRepository.save(product);

Product loaded = productRepository.findById("p-100")
        .orElseThrow();

System.out.println(loaded.getVariants().get(0).getSku());
System.out.println(loaded.getSpecifications().get("material"));
System.out.println(loaded.getOrigin().getCity());
```

Giả định ứng dụng đã cấu hình kết nối Redis và bật Spring Data Redis repositories (qua cấu hình Spring Boot phù hợp hoặc `@EnableRedisRepositories`). Lời gọi `save` chuyển cả đồ thị thuộc tính theo cấu hình converter đang dùng; `findById` tạo lại đối tượng Java từ dữ liệu trong Redis.

## 3. Ánh xạ object lồng nhau bằng dấu chấm

Với thuộc tính object không được đánh dấu tham chiếu riêng, Spring Data Redis thường **flatten** các thuộc tính đơn giản của object con thành nhiều hash field:

```java
product.setOrigin(new Origin("Hà Nội", "VN"));
```

Biểu diễn logic:

```text
origin.city    -> Hà Nội
origin.country -> VN
```

Khi đọc lại, converter dùng các đường dẫn này để tái tạo `Origin` rồi gán cho `Product.origin`.

Cách hiểu:

```text
Product
└── origin
    ├── city     -> origin.city
    └── country  -> origin.country
```

Dấu chấm thể hiện đường đi từ thuộc tính cha đến thuộc tính con, **không phải** một phép nối mang ý nghĩa truy cập động như `product.origin.city` trong runtime của Redis. Redis chỉ lưu tên field dưới dạng byte và giá trị tương ứng.

Một số khác biệt đáng lưu ý:

- **Flatten object:** các thuộc tính con nằm trực tiếp trong Redis Hash của thực thể gốc.
- **Lưu JSON nguyên khối:** nếu cấu hình converter tùy biến để ghi một object thành chuỗi JSON, Redis có thể chỉ có một field chứa nội dung JSON; không còn các field con `origin.city`.
- **Lưu tham chiếu:** nếu dùng cơ chế `@Reference`, thuộc tính đó có thể lưu thông tin tham chiếu tới key của object khác thay vì trải toàn bộ field của object bên trong hash hiện tại.

Vì vậy, những tên field ở đây mô tả cách ánh xạ thông thường của **Spring Data Redis object mapping**. Với converter riêng, tên field và cách mã hóa có thể khác.

## 4. Ánh xạ `List` và mảng: đường dẫn chứa chỉ số

`List` là collection có thứ tự. Khi một danh sách được trải thành các field trong Redis Hash, mỗi phần tử thường mang một chỉ số:

```java
List<Variant> variants = List.of(
    new Variant("DESK-BLACK", 12),
    new Variant("DESK-WHITE", 7)
);
```

Biểu diễn logic:

```text
variants.[0].sku   -> DESK-BLACK
variants.[0].stock -> 12
variants.[1].sku   -> DESK-WHITE
variants.[1].stock -> 7
```

Đường dẫn `variants.[0].stock` có thể phân tích thành:

1. `variants`: thuộc tính collection trên `Product`.
2. `[0]`: phần tử đầu tiên.
3. `stock`: thuộc tính của phần tử đó.

Với danh sách đơn giản:

```java
private List<String> photoUrls;
```

Biểu diễn logic:

```text
photoUrls.[0] -> https://example.org/images/1.jpg
photoUrls.[1] -> https://example.org/images/2.jpg
```

Cần lưu ý rằng **chỉ số là vị trí**, không phải danh tính bất biến của phần tử. Nếu thêm một phần tử vào đầu list, phần tử từng ở `[0]` sẽ chuyển sang `[1]` khi toàn bộ thực thể được ghi lại.

### 4.1. Vì sao không dùng ngay `LPUSH`?

Redis hỗ trợ cấu trúc List native với các lệnh `LPUSH`, `RPUSH`, `LRANGE`, `LSET`... Nhưng đoạn mã:

```java
product.getVariants().add(new Variant("DESK-RED", 3));
productRepository.save(product);
```

là thao tác trên **Java collection trong một entity Redis Hash**. Nó không tương đương với:

```redis
RPUSH products:p-100 "DESK-RED"
```

Lệnh `RPUSH` đòi hỏi key đang là Redis List; key `products:p-100` trong ví dụ đã là Redis Hash, nên có thể nhận lỗi `WRONGTYPE`.

Nếu nghiệp vụ cần thường xuyên thêm/xóa phần tử từ đầu hoặc cuối, truy xuất đoạn danh sách dài, hoặc thực hiện thao tác nguyên tử từng phần tử mà không ghi lại entity, hãy cân nhắc **mô hình Redis List riêng** được quản lý bằng `ListOperations`, thay vì giả định rằng `List` trong `@RedisHash` sử dụng các lệnh List native.

## 5. Ánh xạ `Set`: chứa phần tử không trùng nhau nhưng không có thứ tự nghiệp vụ

Java `Set` biểu diễn tập hợp các phần tử không trùng theo quy tắc equality. Ví dụ:

```java
Set<String> tags = new LinkedHashSet<>();
tags.add("workspace");
tags.add("furniture");
```

Object mapper có thể ánh xạ các phần tử theo một cách biểu diễn dạng collection trong hash, ví dụ:

```text
tags.[0] -> workspace
tags.[1] -> furniture
```

Không nên gán ý nghĩa nghiệp vụ cho `[0]`, `[1]` khi nguồn là `Set`. `HashSet` không có hợp đồng thứ tự phần tử; ngay cả khi dùng `LinkedHashSet`, cách biểu diễn trên Redis không phải một API bảo đảm vị trí phần tử giống Java List trong mọi lần ghi.

Phân biệt hai khái niệm:

| Java `Set` bên trong `@RedisHash` | Redis Set native |
|---|---|
| Là thuộc tính của thực thể, được converter ánh xạ khi lưu entity | Là kiểu dữ liệu Redis độc lập tại một key |
| Thường được đọc/ghi cùng thực thể bằng repository | Được thao tác bằng `SADD`, `SREM`, `SMEMBERS`... |
| Không nên dùng field path `[n]` như ID ổn định | Phù hợp cho membership check, thêm/xóa thành viên ở server |
| TTL của entity áp dụng cho key chứa thực thể | TTL của key Redis Set áp dụng cho toàn bộ set |

Nếu chỉ cần lưu danh sách nhãn như một phần của sản phẩm, `Set<String>` trong entity là lựa chọn tự nhiên. Nếu cần hàng triệu phép kiểm tra thành viên bằng `SISMEMBER` và cập nhật từng phần tử, mô hình Redis Set riêng có thể thích hợp hơn.

## 6. Ánh xạ `Map`: đường dẫn chứa khóa trong dấu ngoặc vuông

Khác `List`, `Map` tra cứu theo **khóa**. Spring Data Redis sử dụng giá trị khóa map trong đường dẫn của field:

```java
Map<String, String> specifications = new LinkedHashMap<>();
specifications.put("material", "wood");
specifications.put("widthCm", "120");
```

Biểu diễn logic:

```text
specifications.[material] -> wood
specifications.[widthCm]  -> 120
```

`[material]` ở đây là **tên khóa**, không phải chỉ số. Hai map có cùng dữ liệu nhưng thứ tự thêm phần tử khác nhau vẫn được hiểu theo khóa map chứ không theo vị trí.

### 6.1. Map chứa object

Với `Map<String, Address>`, đường dẫn cần thể hiện cả **tên map key** và **thuộc tính của giá trị**:

```java
public class Address {
    private String city;
    private String street;

    public Address() { }

    public Address(String city, String street) {
        this.city = city;
        this.street = street;
    }

    public String getCity() { return city; }
    public void setCity(String city) { this.city = city; }

    public String getStreet() { return street; }
    public void setStreet(String street) { this.street = street; }
}
```

Giả sử `Customer` có trường:

```java
private Map<String, Address> addresses;
```

Và dữ liệu:

```java
addresses.put("home", new Address("Đà Nẵng", "Nguyễn Văn Linh"));
addresses.put("office", new Address("Hà Nội", "Trần Duy Hưng"));
```

Biểu diễn logic:

```text
addresses.[home].city      -> Đà Nẵng
addresses.[home].street    -> Nguyễn Văn Linh
addresses.[office].city    -> Hà Nội
addresses.[office].street  -> Trần Duy Hưng
```

Đây là đường dẫn nhiều cấp:

```text
Customer
└── addresses (Map)
    ├── ["home"] (Address)
    │   ├── city   -> addresses.[home].city
    │   └── street -> addresses.[home].street
    └── ["office"] (Address)
        ├── city   -> addresses.[office].city
        └── street -> addresses.[office].street
```

### 6.2. Map với khóa phức tạp

Đường dẫn field trong Redis Hash cần được tạo thành dạng chuỗi/byte. Vì vậy, ví dụ `Map<String, ...>` với các khóa đơn giản như `"home"`, `"office"`, `"material"` thường dễ hiểu, dễ kiểm tra hơn.

Nếu dùng `Map<UUID, ...>`, `Map<Enum, ...>` hay kiểu khóa tùy biến, cần bảo đảm converter có cách chuyển **map key** phù hợp và đối xứng khi ghi/đọc. Tránh mặc định rằng mọi kiểu object Java đều biến thành field name hợp lệ mà không cần conversion.

Đồng thời, các ký tự đặc biệt trong tên map key (ví dụ dấu chấm, dấu ngoặc vuông) có thể làm đường dẫn khó đọc hoặc tương tác bất ngờ với quy tắc biểu diễn path của mapper. Với dữ liệu đầu vào tùy ý, nên quy định cách mã hóa khóa ổn định hoặc sử dụng converter phù hợp, rồi kiểm tra round-trip bằng chính cấu hình đang triển khai.

## 7. Đọc đường dẫn từ Redis CLI

Sau khi `productRepository.save(product)` lưu ví dụ sản phẩm, có thể kiểm tra Redis bằng:

```redis
TYPE products:p-100
HGETALL products:p-100
HGET products:p-100 "name"
HGET products:p-100 "origin.city"
HGET products:p-100 "variants.[0].sku"
HGET products:p-100 "specifications.[material]"
```

`HGET` lấy một field có tên **chính xác**. Redis server không tự hiểu rằng `"variants.[0].sku"` nghĩa là đi vào phần tử thứ 0 của danh sách Java; tên này do **mapper tạo ra trước khi ghi**.

Nếu thử:

```redis
HGET products:p-100 "variants"
```

không có gì bảo đảm Redis sẽ trả cả danh sách. Với mô hình flatten, dữ liệu nằm trong nhiều field `variants.[0].*`, `variants.[1].*` thay vì một field chung tên `variants`.

Tương tự, `HGETALL` hiển thị field và value ở dạng Redis lưu, thường là byte được CLI diễn giải thành văn bản. Sự hiện diện của `_class`, cách serialize số, ngày tháng hay các đối tượng tùy biến có thể khác theo converter/serializer. Dùng dữ liệu quan sát được trên instance và phiên bản đang chạy để xác định biểu diễn thực tế.

## 8. Đường dẫn thuộc tính là quy ước ánh xạ, không phải ngôn ngữ truy vấn

Có ba loại “đường dẫn” thường bị nhầm:

1. **Java property access:** `product.getVariants().get(0).getSku()`.
2. **Redis Hash field name:** `"variants.[0].sku"`.
3. **Truy vấn repository:** các phương thức như `findByName(...)`, có thể cần cơ chế index tùy thuộc kiểu truy vấn.

Chúng liên quan nhưng **không tương đương**. Ví dụ, không thể mặc định rằng:

```java
interface ProductRepository extends CrudRepository<Product, String> {
    // Không có bảo đảm đây là truy vấn map/list tùy ý chỉ nhờ tên hàm:
    // List<Product> findBySpecificationsMaterial(String material);
}
```

sẽ tự động tìm theo `specifications.[material]` chỉ vì field đó tồn tại trong Redis Hash. Redis repository không cung cấp SQL hoặc JSONPath trên mọi field hash. Những truy vấn thứ cấp cần dựa trên khả năng query derivation và index được Spring Data Redis hỗ trợ; không nên suy diễn khả năng query từ cách converter flatten field.

Nếu cần tìm kiếm phức tạp theo phần tử của map/list, hãy lựa chọn mô hình chỉ mục phù hợp, giữ một index riêng hoặc dùng công nghệ tìm kiếm tương ứng. `@Indexed` có thể hữu ích với những thuộc tính được hỗ trợ, nhưng không biến toàn bộ object graph thành cấu trúc truy vấn đa chiều.

## 9. Cập nhật một phần tử và ghi lại thực thể

Sau khi đọc entity, thay đổi Java object **chưa đồng nghĩa** Redis đã cập nhật:

```java
Product product = productRepository.findById("p-100")
    .orElseThrow();

product.getVariants().get(0).setStock(15);
product.getSpecifications().put("material", "bamboo");

productRepository.save(product);
```

Ở cấp ứng dụng, thao tác này đọc object, sửa hai vị trí rồi **save lại entity**. Spring Data Redis chịu trách nhiệm chuyển object sang biểu diễn hash.

Không nên tự pha trộn:

```redis
HSET products:p-100 "variants.[0].stock" 15
```

với `productRepository.save(...)` mà không thiết kế rõ ai là bên sở hữu dữ liệu. Một lần `save` sau đó có thể ghi lại giá trị từ bản object cũ, ghi đè cập nhật trực tiếp; ngược lại, sửa field bằng CLI không tự đồng bộ các index hoặc siêu dữ liệu do repository quản lý.

Đối với hai request đồng thời:

```text
Request A                     Request B
---------                     ---------
Đọc Product (stock=12)       Đọc Product (stock=12)
Đặt stock=13                 Đặt stock=11
save(Product)                save(Product)
```

Kết quả cuối có thể phản ánh lần lưu sau cùng thay vì tổng hợp cả hai thay đổi. Object mapping không tự cung cấp hợp đồng “cộng/trừ tồn kho nguyên tử”. Nếu nghiệp vụ cần cập nhật đồng thời chính xác, hãy dùng một mô hình dữ liệu và thao tác nguyên tử phù hợp, chẳng hạn bộ đếm riêng với `INCRBY`, optimistic locking được thiết kế rõ ràng hoặc script Redis theo nhu cầu.

### 9.1. Thêm, xóa, sắp xếp lại phần tử

Với list:

```java
product.getVariants().add(new Variant("DESK-RED", 3));
product.getVariants().remove(0);
productRepository.save(product);
```

Việc xóa phần tử ở đầu khiến các vị trí `[0]`, `[1]` thay đổi. Không nên giữ đường dẫn như `"variants.[0].sku"` ở hệ thống ngoài để nhận diện một SKU lâu dài. Hãy dựa vào trường `sku` là định danh nghiệp vụ, hoặc tách biến thể thành những thực thể có ID nếu cần cập nhật, tìm kiếm và quản lý vòng đời riêng.

Với map:

```java
product.getSpecifications().remove("widthCm");
productRepository.save(product);
```

Sau khi cập nhật bằng repository, trạng thái mong muốn là bản đồ thuộc tính phản ánh map hiện tại. Tránh giả định rằng tự chỉnh sửa một field hash bằng tay có tác dụng tương đương với cập nhật cả entity và các cấu trúc phụ trợ.

## 10. `null`, collection rỗng và trường không có trong hash

Ba tình huống có thể có ý nghĩa khác nhau trong Java:

```java
product.setVariants(null);
product.setVariants(new ArrayList<>());
product.setVariants(List.of(new Variant("DESK-BLACK", 12)));
```

Trong Redis Hash được flatten, một collection **rỗng** có thể không tạo ra field mang chỉ số nào. `null` cũng có thể không có field được ghi. Do đó, không thể luôn phân biệt “chưa có dữ liệu”, “đã chủ động đặt rỗng” và “đã đặt null” chỉ bằng việc tìm các field `variants.[n]` trong hash. Giá trị sau khi đọc lại còn phụ thuộc constructor, kiểu property và converter đang dùng.

Nếu nghiệp vụ bắt buộc phân biệt ba trạng thái trên, hãy thiết kế tín hiệu riêng:

```java
private boolean variantsLoaded;
private List<Variant> variants = new ArrayList<>();
```

hoặc dùng một trạng thái rõ nghĩa như `NOT_LOADED`, `LOADED_EMPTY`, `LOADED_WITH_ITEMS` ở tầng domain. Đừng dựa vào sự có mặt của một path kỹ thuật khi domain cần biểu diễn trạng thái độc lập.

### 10.1. Giá trị `null` trong map

Một map có entry với value `null` cũng cần được cân nhắc riêng với việc map **không có key đó**. Tùy chính sách converter, cả hai có thể không tạo field tương ứng. Nếu hai trạng thái mang nghĩa khác nhau, nên dùng object giá trị với cờ trạng thái hoặc quy ước lưu rõ ràng.

## 11. Serialization và custom conversions thay đổi cấu trúc lưu

Spring Data Redis có lớp chuyển đổi như `MappingRedisConverter` để ghi và đọc các field theo metadata của domain type. Với những kiểu được xử lý như giá trị đơn (*simple value*), converter thường lưu dữ liệu dưới một field. Với object phức tạp, converter có thể đi sâu vào các thuộc tính để tạo nhiều property paths.

Tuy nhiên, một **custom converter** có thể quyết định chuyển cả đối tượng thành một field:

```text
Mặc định theo kiểu flatten:
  origin.city      -> Hà Nội
  origin.country   -> VN

Nếu custom converter mã hóa Origin thành một giá trị:
  origin           -> {"city":"Hà Nội","country":"VN"}
```

Khác biệt này kéo theo một số hệ quả:

- `HGET key "origin.city"` chỉ hữu ích nếu mapper thật sự tạo field đó.
- Một object chứa JSON bên trong hash không tự trở thành RedisJSON với JSONPath.
- Việc thay đổi converter sau khi đã lưu dữ liệu có thể gây vấn đề đọc ngược; khi đổi schema cần cân nhắc tương thích và migration.
- Nếu metadata kiểu (chẳng hạn `_class`) được dùng để phục hồi subtype, hãy tránh xóa/sửa tùy tiện bằng thao tác raw Redis.

Định dạng field path là **chi tiết lưu trữ của mapping**, không nên biến thành giao diện công khai giữa các service nếu có thể dùng repository/domain API. Khi thực sự cần tích hợp ở cấp hash field, phải chuẩn hóa schema và phiên bản của nó.

## 12. TTL, khóa phụ trợ và phạm vi hết hạn

Có thể thiết lập TTL cho toàn bộ thực thể Redis:

```java
@RedisHash(value = "products", timeToLive = 1800)
public class Product {
    // Các thuộc tính của entity...
}
```

Trong cách ánh xạ này, TTL áp dụng cho **key `products:<id>` chứa Redis Hash**. Điều đó có nghĩa `variants.[0].sku`, `origin.city` và `specifications.[material]` cùng biến mất khi key hết hạn; Spring Data Redis không tự tạo TTL độc lập cho từng thành viên Java List hoặc từng map entry chỉ vì chúng có đường dẫn riêng.

Một số phiên bản Redis mới có khả năng đặt thời hạn trên hash field, nhưng đó là một cơ chế Redis riêng và **không đồng nghĩa** annotation TTL trên `@RedisHash` tự động cấp thời hạn cho mỗi phần tử collection.

Ngoài key dữ liệu chính, repository có thể tạo thêm key phụ trợ để quản lý tập ID của thực thể, chỉ mục thứ cấp hoặc các thông tin liên quan. Vì vậy:

- Không giả định `KEYS products:*` chỉ gồm những Hash chứa một `Product`.
- Không xóa hàng loạt theo prefix nếu chưa hiểu những key phụ mà repository quản lý.
- Khi xóa entity, nên ưu tiên `productRepository.deleteById(id)` trong luồng do repository sở hữu để các cấu trúc liên quan được xử lý theo cơ chế repository.

## 13. Khi nào nên dùng repository mapping, khi nào dùng Redis native structure?

| Nhu cầu | Mô hình thường phù hợp |
|---|---|
| Lưu và lấy lại một object sản phẩm có một số thuộc tính lồng nhau | `@RedisHash` + repository |
| Lưu `List<Variant>` nhỏ như một phần trạng thái sản phẩm | Collection property trong entity |
| Thay đổi danh sách dài theo đầu/cuối rất thường xuyên | Redis List riêng với `ListOperations` |
| Thêm/xóa thành viên, kiểm tra có thuộc tập ở phía Redis | Redis Set riêng với `SetOperations` |
| Cập nhật một bộ đếm dùng đồng thời nhiều luồng | Redis String/counter riêng với lệnh nguyên tử |
| Tra cứu liên tục giá trị theo map key và cập nhật riêng từng entry | Redis Hash riêng với `HashOperations` |
| Tìm kiếm/lọc sâu theo nhiều thuộc tính và phần tử lồng nhau | Mô hình index hoặc giải pháp truy vấn phù hợp |
| Muốn mọi thuộc tính đi cùng một vòng đời, lưu và đọc dưới dạng một object | Repository mapping |

Nếu dùng `HashOperations` để lưu một map riêng:

```java
redisTemplate.opsForHash().put("product:specs:p-100", "material", "wood");
redisTemplate.opsForHash().put("product:specs:p-100", "widthCm", "120");
```

thì Redis Hash này có các field `"material"`, `"widthCm"` trực tiếp. Nó **không phải** cùng cơ chế với `Map<String, String> specifications` nằm bên trong entity `@RedisHash("products")`, nơi tên field có thể là `"specifications.[material]"`.

Hai mô hình đều dùng Redis Hash nhưng có **ranh giới dữ liệu và API khác nhau**. Không trộn lẫn chúng chỉ vì tên “hash” xuất hiện ở cả hai.

## 14. Ví dụ thực hành: kiểm tra một thực thể có đường dẫn lồng nhau

Tạo dữ liệu qua repository như phần 2, sau đó quan sát Redis:

```redis
TYPE products:p-100
HGETALL products:p-100
HGET products:p-100 "origin.city"
HGET products:p-100 "variants.[1].sku"
HGET products:p-100 "specifications.[material]"
```

Tiếp theo, cập nhật entity bằng Java:

```java
Product saved = productRepository.findById("p-100")
        .orElseThrow();

saved.getVariants().remove(0);
saved.getSpecifications().put("material", "bamboo");

productRepository.save(saved);
```

Quan sát lại:

```redis
HGETALL products:p-100
HGET products:p-100 "variants.[0].sku"
HGET products:p-100 "specifications.[material]"
```

Hãy chú ý rằng phần tử `"DESK-WHITE"` trước đó ở vị trí `[1]` nay có thể được ánh xạ ở `[0]`, còn giá trị map key `"material"` được đổi thành `"bamboo"`. Điều này minh họa **list truy cập theo vị trí**, còn **map truy cập theo khóa**.

Trường hợp field trong instance không khớp với ví dụ, trước tiên xem lại kiểu domain, serializer, custom conversions và phiên bản Spring Data Redis; không nên vội sửa field trực tiếp cho giống ví dụ.

## 15. Những lỗi thiết kế dễ gặp

**Nhầm Java List với Redis List.** Đọc `List<Variant>` trong entity rồi gọi `LRANGE products:p-100 0 -1` sẽ không hoạt động nếu key thực tế là Redis Hash. Xác định kiểu Redis bằng `TYPE` và chọn API tương ứng.

**Xem `[0]` của list hoặc set là ID vĩnh viễn.** Khi danh sách thêm/xóa/sắp xếp lại, chỉ số thay đổi. Tạo ID nghiệp vụ cho những phần tử cần định danh độc lập.

**Xem `"specifications.[material]"` là cú pháp query tự động.** Nó chỉ là hash field path do mapper sử dụng. Truy vấn theo giá trị cần index hoặc mô hình dữ liệu hỗ trợ.

**Cập nhật cùng dữ liệu qua cả repository lẫn raw `HSET`.** Dễ phát sinh ghi đè, sai lệch metadata và bỏ qua xử lý chỉ mục. Nên xác định một API chủ sở hữu vòng đời của key.

**Tin rằng collection rỗng và `null` luôn lưu khác nhau.** Khi dữ liệu được flatten, thiếu field không nhất thiết cho biết lý do. Biểu diễn trạng thái nghiệp vụ bằng thuộc tính riêng nếu cần.

**Đặt TTL cho entity rồi kỳ vọng mỗi map entry hết hạn riêng.** TTL của `@RedisHash` áp dụng cho key thực thể. Nếu mỗi thành viên có vòng đời riêng, hãy thiết kế key hoặc cơ chế hết hạn riêng.

**Đổi tên thuộc tính Java mà bỏ qua dữ liệu cũ.** Đổi `specifications` thành `details` có thể làm converter tìm đường dẫn mới, trong khi Redis còn những field với tên cũ. Cần kế hoạch tương thích hoặc migration.

## 16. Cách hình dung khi thiết kế entity

Có thể dùng quy tắc sau để đọc một đường dẫn như `orders.[0].attributes.[color]`:

```text
orders             -> thuộc tính collection
.[0]               -> phần tử thứ nhất
.attributes        -> thuộc tính map của phần tử
.[color]           -> giá trị ứng với key "color"
```

Trong Redis Hash, toàn chuỗi ấy là **một field name**. Trong Java, đó là kết quả đi qua nhiều cấp thuộc tính. Trong repository, converter có trách nhiệm nối hai thế giới này.

Khi làm việc với Spring Data Redis, hãy quyết định trước **đơn vị dữ liệu** nào cần được lưu, cập nhật và hết hạn cùng nhau. Nếu `Product` và các collection con thường được đọc/ghi như một khối, ánh xạ bằng repository rất thuận tiện. Nếu từng phần tử cần cập nhật nguyên tử, TTL riêng, tập lệnh Redis native hoặc query chuyên biệt, nên tách chúng thành key/kiểu dữ liệu riêng phù hợp với truy cập thực tế.

Đó là điểm then chốt của ánh xạ collection, map và đường dẫn thuộc tính: **Java quyết định cấu trúc đối tượng; Spring Data Redis quyết định cách chuyển cấu trúc đó thành Redis Hash; còn Redis thao tác trên key và hash field đã được lưu**, chứ không trực tiếp thực thi biểu thức truy cập thuộc tính của Java.
