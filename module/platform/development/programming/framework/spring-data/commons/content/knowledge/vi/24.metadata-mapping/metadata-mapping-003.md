# PersistentProperty, Association và mối quan hệ thuộc tính

Trong mô hình ánh xạ của Spring Data, một thuộc tính không chỉ có tên và kiểu Java. Framework còn cần biết thuộc tính thuộc kiểu miền nào, có phải định danh hoặc phiên bản không, chứa một giá trị hay nhiều giá trị, và có đại diện cho một liên kết được module lưu trữ nhận diện hay không.

`PersistentProperty` mô tả **metadata của một thuộc tính**. `Association` mô tả **metadata liên kết giữa các phía thuộc tính theo mô hình của module**. Chúng không chứa dữ liệu của một bản ghi và không tự quyết định toàn bộ cách tải, lưu hoặc truy vấn quan hệ.

Bài học thuộc chương **Metadata ánh xạ** của **SPRING_DATA_COMMONS**. Mục tiêu là hiểu các abstraction dùng chung để đọc metadata đúng ngữ nghĩa, đồng thời tôn trọng cách từng store ánh xạ đối tượng, collection, map và tham chiếu.

Sau bài học, bạn có thể:

- Phân biệt `PersistentEntity`, `PersistentProperty` và `Association`.
- Đọc metadata tên, chủ sở hữu, kiểu và các vai trò đặc biệt của thuộc tính.
- Phân biệt thuộc tính phức hợp, object nhúng và liên kết được module nhận diện.
- Giải thích vì sao collection hoặc một trường tên `customerId` chưa đủ để kết luận có association.
- Thiết kế công cụ đọc metadata có xét generic type, vòng tham chiếu và khác biệt giữa các store.

## 1. Ba lớp metadata cần tách biệt

| Abstraction | Câu hỏi chính |
|---|---|
| `PersistentEntity` | Kiểu miền này được mô tả và ánh xạ như thế nào? |
| `PersistentProperty` | Một thuộc tính của kiểu miền có những đặc điểm gì? |
| `Association` | Một liên kết được mô hình metadata mô tả qua các thuộc tính ra sao? |

Ví dụ một đơn hàng có:

~~~text
PurchaseOrder
  id
  orderNumber
  shippingAddress
  items
  customer
~~~

Ở mức dữ liệu, một đối tượng `PurchaseOrder` có giá trị cụ thể cho các trường trên.

Ở mức metadata:

~~~text
PersistentEntity của PurchaseOrder
        |
        +--> PersistentProperty của id
        +--> PersistentProperty của orderNumber
        +--> PersistentProperty của shippingAddress
        +--> PersistentProperty của items
        +--> PersistentProperty của customer
                    |
                    +--> Association nếu module nhận diện
                         đây là thuộc tính liên kết
~~~

Việc `shippingAddress` hoặc `items` chứa kiểu miền khác không tự chứng minh chúng có cùng ngữ nghĩa association với `customer`.

### 1.1. Metadata và giá trị là hai loại thông tin khác nhau

| Thông tin | Metadata hay dữ liệu? |
|---|---|
| Tên thuộc tính là `orderNumber` | Metadata |
| Kiểu Java là `String` | Metadata |
| Giá trị là `"ORD-2026-001"` | Dữ liệu |
| Thuộc tính được nhận diện là định danh | Metadata |
| Khách hàng được tham chiếu có id `"C01"` | Dữ liệu |
| Module nhận diện thuộc tính là association | Metadata |

Cùng một `PersistentProperty` có thể dùng để mô tả nhiều đối tượng đơn hàng khác nhau. Nó không đại diện riêng cho trường của một bản ghi cụ thể.

## 2. PersistentProperty mô tả những gì?

Kiểu này nằm trong package:

~~~java
org.springframework.data.mapping.PersistentProperty
~~~

Nó dùng generic tự tham chiếu theo dạng:

~~~java
PersistentProperty<P extends PersistentProperty<P>>
~~~

Cấu trúc này cho phép module định nghĩa một loại property riêng rồi giữ kiểu đó nhất quán trong entity metadata, association và các API liên quan.

Ví dụ module MongoDB có `MongoPersistentProperty`. Đây là metadata thuộc tính được mở rộng với thông tin của MongoDB, không phải một lớp dữ liệu miền khác.

Một số phương thức quan trọng:

| Nhóm | API tiêu biểu | Ý nghĩa |
|---|---|---|
| Nhận diện | `getName()`, `getOwner()` | Tên thuộc tính và entity metadata chứa nó |
| Kiểu | `getType()`, `getTypeInformation()` | Kiểu Java và mô tả kiểu có thêm thông tin generic |
| Container | `isCollectionLike()`, `isArray()`, `isMap()` | Đặc điểm của kiểu chứa dữ liệu |
| Thành phần | `getComponentType()`, `getMapValueType()` | Kiểu phần tử hoặc giá trị map khi xác định được |
| Vai trò | `isIdProperty()`, `isVersionProperty()` | Thuộc tính định danh hoặc phiên bản |
| Liên kết | `isAssociation()`, `getAssociation()` | Có phải liên kết được module nhận diện và metadata liên quan |
| Persistence | `isTransient()`, `isWritable()` | Vai trò trong ánh xạ và khả năng ghi theo metadata |
| Annotation | `findAnnotation(...)` | Đọc annotation theo quy tắc của property implementation |

Các thông tin như field, getter, setter hoặc cách truy cập cũng có thể được metadata cung cấp. Không nên giả định mọi property đều chỉ tương ứng với một field có thể sửa trực tiếp.

### 2.1. Owner là kiểu đang chứa thuộc tính

Nếu đang xét `PurchaseOrder.customer`:

~~~text
property.getName()        -> customer
property.getOwner()       -> metadata của PurchaseOrder
property.getType()        -> Customer
~~~

Owner không phải kiểu đích của tham chiếu. Nó là entity metadata chứa property đang xét.

Phân biệt này quan trọng khi xây tên đường dẫn, đọc annotation hoặc xác định nơi khai báo quy tắc ánh xạ.

### 2.2. Vai trò định danh và phiên bản không suy từ tên một cách chung

Không viết công cụ metadata theo quy tắc:

~~~text
Tên bằng "id" thì chắc chắn là định danh.
Tên bằng "version" thì chắc chắn là phiên bản.
~~~

Module có quy ước và annotation riêng. Hãy dùng metadata `isIdProperty()` hoặc `isVersionProperty()` của module đã cấu hình.

Ngược lại, một trường tên `customerId` có thể chỉ là một giá trị tham chiếu do ứng dụng quản lý, không phải định danh của chính entity đang xét.

## 3. Kiểu Java, generic type và kiểu phần tử

Giả sử mô hình có:

~~~java
private Address shippingAddress;
private List<LineItem> items;
private Map<String, Address> contactsByRole;
~~~

Cần đọc chúng ở hai mức:

| Thuộc tính | Kiểu chứa | Kiểu dữ liệu cần quan tâm thêm |
|---|---|---|
| `shippingAddress` | `Address` | Chính kiểu Address |
| `items` | `List` | Phần tử LineItem |
| `contactsByRole` | `Map` | Khóa String và giá trị Address |

Chỉ đọc `getType()` của `items` sẽ thấy kiểu container, chưa đủ để duyệt metadata của `LineItem`.

`getTypeInformation()` giữ mô tả kiểu phong phú hơn. Với collection, có thể dùng thông tin phần tử; với map, cần xem riêng kiểu giá trị thay vì mặc định dùng cùng một quy tắc như list.

Ví dụ đọc mô tả:

~~~java
import org.springframework.data.mapping.PersistentProperty;

public static void printProperty(PersistentProperty<?> property) {
    String owner = property.getOwner().getType().getSimpleName();

    System.out.println(owner + "." + property.getName());
    System.out.println("type=" + property.getType().getName());
    System.out.println(
        "typeInformation=" + property.getTypeInformation()
    );
    System.out.println("collectionLike=" + property.isCollectionLike());
    System.out.println("map=" + property.isMap());

    if (property.isMap()) {
        System.out.println(
            "mapValueType=" + property.getMapValueType()
        );
    } else if (property.isCollectionLike() || property.isArray()) {
        System.out.println(
            "componentType=" + property.getComponentType()
        );
    }

    System.out.println("id=" + property.isIdProperty());
    System.out.println("version=" + property.isVersionProperty());
    System.out.println("association=" + property.isAssociation());
}
~~~

Đoạn mã chỉ đọc metadata. Nó không đọc hoặc thay đổi dữ liệu của bất kỳ đơn hàng nào.

### 3.1. Không giả định generic type luôn xác định được

Raw type như:

~~~java
private List items;
~~~

làm mất thông tin phần tử so với `List<LineItem>`.

Các chuỗi kế thừa generic cũng có thể cần metadata trong đúng ngữ cảnh kiểu chủ sở hữu để giải quyết type variable.

Vì vậy, công cụ đọc metadata phải xử lý trường hợp không xác định được kiểu phần tử hoặc kiểu giá trị. Không tự gán `Object` rồi suy ra đó là một entity có đầy đủ thuộc tính để duyệt.

## 4. Association không đồng nghĩa mọi object lồng nhau

Một thuộc tính có thể liên quan đến kiểu miền khác theo nhiều cách:

1. Chứa một object được nhúng vào bản ghi hiện tại.
2. Chứa collection các giá trị được lưu cùng aggregate.
3. Chứa một mã định danh do ứng dụng dùng để tra cứu.
4. Chứa một tham chiếu được module nhận diện và ánh xạ bằng cơ chế riêng.
5. Đại diện một quan hệ theo mô hình store.

`isAssociation()` trả lời theo quy tắc của property implementation, không chỉ theo việc kiểu Java là một class do ứng dụng định nghĩa.

### 4.1. Thuộc tính phức hợp khác liên kết được nhận diện

Trong một store tài liệu:

~~~java
private Address shippingAddress;
~~~

có thể được lưu như object nhúng. Framework có thể cần metadata của Address để ánh xạ các thuộc tính con, nhưng điều đó không buộc property phải có `isAssociation() == true`.

Ngược lại, một thuộc tính tham chiếu có annotation của module có thể được nhận diện là association.

Do đó:

~~~text
Có kiểu miền lồng nhau
        không tự suy ra
Là association của module
~~~

Tương tự, “entity” trong API metadata Commons không được hiểu tự động là “lớp có annotation @Entity của JPA”. Cách nhận diện persistent type và simple type phụ thuộc mapping context, converter và module.

## 5. Ví dụ cụ thể với MongoDB mapping metadata

Ví dụ này chọn Spring Data MongoDB để có một mapping context cụ thể. Nó không thiết lập quy tắc chung rằng mọi module đều phân loại thuộc tính giống MongoDB.

### 5.1. Mô hình minh họa

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.DBRef;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document("purchase_orders")
public class PurchaseOrder {

    @Id
    private String id;

    @Version
    private Long version;

    @Field("order_no")
    private String orderNumber;

    private Address shippingAddress;

    private List<LineItem> items;

    private String[] tags;

    private Map<String, Address> contactsByRole;

    @DBRef
    private Customer customer;

    private String customerId;

    @Transient
    private BigDecimal displayTotal;
}
~~~

Các kiểu liên quan:

~~~java
public class Address {
    private String city;
    private String postalCode;
}
~~~

~~~java
import java.math.BigDecimal;

public class LineItem {
    private String sku;
    private Integer quantity;
    private BigDecimal unitPrice;
}
~~~

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("customers")
public class Customer {
    @Id
    private String id;

    private String displayName;
}
~~~

Mã chỉ trình bày các field phục vụ phân tích metadata. MongoDB mapping có thể dùng field access; không cần thêm getter/setter chỉ để các ví dụ đọc metadata dưới đây nhìn thấy thuộc tính.

Giả định không có custom converter làm thay đổi cách ánh xạ Address, LineItem hoặc Customer trong ví dụ.

### 5.2. Phân loại theo ý nghĩa lưu trữ

| Thuộc tính | Ý nghĩa trong ví dụ |
|---|---|
| `id` | Định danh do metadata module nhận diện |
| `version` | Thuộc tính phiên bản |
| `orderNumber` | Thuộc tính chuỗi, có tên trường lưu trữ khác tên Java |
| `shippingAddress` | Object nhúng |
| `items` | Collection các giá trị được ánh xạ bên trong tài liệu |
| `tags` | Mảng giá trị chuỗi |
| `contactsByRole` | Map có giá trị là object Address |
| `customer` | Tham chiếu được đánh dấu bằng `@DBRef` |
| `customerId` | Một giá trị chuỗi; tên trường không tự tạo association |
| `displayTotal` | Thuộc tính bị loại khỏi lưu trữ bởi `@Transient` |

Với cấu hình ánh xạ thông thường của ví dụ, `customer` là association được module nhận diện qua `@DBRef`. Các object nhúng và collection giá trị không tự trở thành association chỉ vì chúng chứa kiểu do ứng dụng định nghĩa.

Tên `customerId` không tự tạo ràng buộc khóa ngoại, không tự tra cứu Customer và không tự đồng bộ với `customer`.

Trong mô hình thực tế, chỉ nên giữ cả hai trường nếu ứng dụng có hợp đồng rõ về vai trò của chúng. Bài dùng cả hai để minh họa khác biệt metadata.

### 5.3. Đọc property từ mapping context

Giả định `mappingContext` là `MongoMappingContext` đã được cấu hình trong ứng dụng:

~~~java
import org.springframework.data.mongodb.core.mapping.MongoPersistentEntity;
import org.springframework.data.mongodb.core.mapping.MongoPersistentProperty;

MongoPersistentEntity<?> entity =
    mappingContext.getRequiredPersistentEntity(PurchaseOrder.class);

MongoPersistentProperty orderNumber =
    entity.getRequiredPersistentProperty("orderNumber");

MongoPersistentProperty items =
    entity.getRequiredPersistentProperty("items");

MongoPersistentProperty customer =
    entity.getRequiredPersistentProperty("customer");

printProperty(orderNumber);
printProperty(items);
printProperty(customer);
~~~

`printProperty` là helper ở mục 3.

Các quan sát đáng chú ý:

- Tên property Java vẫn là `orderNumber`, dù tên trường lưu là `order_no`.
- `items` có kiểu container và có thông tin phần tử LineItem.
- `customer` có kiểu Customer và được module nhận diện là association.
- Metadata owner của cả ba property là PurchaseOrder.

`getRequiredPersistentProperty` thích hợp khi tên thuộc tính là một yêu cầu chắc chắn của công cụ; nếu không có, phương thức sẽ báo lỗi theo hợp đồng thay vì trả về một property giả định.

Khi tên đầu vào có thể không tồn tại, dùng `getPersistentProperty(...)` rồi xử lý trường hợp không có metadata.

### 5.4. Thuộc tính transient có thể không nằm trong tập metadata được đăng ký

Không kỳ vọng mọi field Java đều xuất hiện như một property có thể duyệt trong `PersistentEntity`.

Ví dụ:

~~~java
MongoPersistentProperty displayTotal =
    entity.getPersistentProperty("displayTotal");
~~~

Module có thể loại thuộc tính transient khỏi tập persistent property được đăng ký, nên kết quả lookup có thể không có.

`isTransient()` là một phần hợp đồng property metadata; điều đó không đồng nghĩa một vòng duyệt persistent properties nhất định sẽ luôn trả cả những property transient.

Vì vậy, không viết logic kiểm tra thành công theo kiểu “phải tìm thấy displayTotal rồi cờ transient mới được phép true”. Hãy kiểm tra cả việc thuộc tính có nằm trong tập metadata mà API đang cung cấp hay không.

## 6. Đọc Association mà không gán nhầm ngữ nghĩa

`Association<P>` nằm trong package `org.springframework.data.mapping`.

Có thể lấy nó từ property đã được module nhận diện là association:

~~~java
import org.springframework.data.mapping.Association;
import org.springframework.data.mapping.PersistentProperty;

Association<?> association = customer.getAssociation();

if (association != null) {
    printAssociationSide("inverse", association.getInverse());
    printAssociationSide("obverse", association.getObverse());
}
~~~

Helper:

~~~java
public static void printAssociationSide(
        String side,
        PersistentProperty<?> property) {

    if (property == null) {
        System.out.println(side + "=không có metadata phía này");
        return;
    }

    System.out.println(
        side + "="
            + property.getOwner().getType().getSimpleName()
            + "."
            + property.getName()
    );
}
~~~

Helper kiểm tra null ở từng phía để không giả định lúc nào cũng có metadata đối ứng.

Các tên `getInverse()` và `getObverse()` là tên trong abstraction association. Không dùng chúng để suy ngay ra owning side, `mappedBy`, khóa ngoại hoặc quy tắc cascade của JPA.

Cần đọc ý nghĩa mà implementation module gắn cho các phía. Một liên kết một chiều không bắt buộc có một property đối ứng trên kiểu đích.

### 6.1. Association liên kết metadata, không chứa đối tượng Customer

Một `Association` không phải:

- Customer đã được tải từ database.
- Một cursor dùng để truy xuất Customer.
- Một join SQL được thực thi ngay khi gọi getter metadata.
- Một quy tắc cascade chung của mọi store.

Đọc association chỉ giúp hiểu mô hình ánh xạ. Cách chuyển tham chiếu thành dữ liệu và thời điểm truy xuất phụ thuộc converter, reference resolver, repository hoặc cơ chế của module.

### 6.2. Có association không tự sinh quan hệ hai chiều

Nếu PurchaseOrder tham chiếu Customer, không suy ra Customer tự có collection các đơn hàng.

Muốn có chiều truy cập ngược, mô hình hoặc truy vấn phải được thiết kế tương ứng. Ngay cả khi có hai property ở hai phía, dữ liệu cũng không tự được đồng bộ chỉ vì metadata mô tả được liên kết.

### 6.3. Association không tự bảo đảm toàn vẹn tham chiếu

Trong ví dụ `@DBRef`, metadata không tạo ra một ràng buộc khóa ngoại quan hệ theo nghĩa SQL. Nếu dữ liệu đích không tồn tại, cách xử lý thuộc về module và thiết kế ứng dụng.

Không suy từ cờ association rằng framework sẽ tự lưu Customer mới khi lưu PurchaseOrder, tự xóa các đơn liên quan hoặc tự duy trì toàn bộ đồ thị đối tượng.

## 7. Ba trường hợp null cần phân biệt

| Trường hợp | Ý nghĩa |
|---|---|
| Lookup property không có kết quả | Không có property metadata tương ứng trong entity metadata đang dùng |
| `property.getAssociation()` không có kết quả | Không có association metadata cho property đó theo implementation |
| Giá trị `order.customer` là null | Một đối tượng dữ liệu cụ thể không có giá trị Customer |

Một property có association metadata vẫn có thể mang giá trị null trong một đối tượng cụ thể.

Ngược lại, một property không phải association vẫn có thể chứa object Address với nhiều giá trị con.

Đừng dùng sự có mặt của dữ liệu để tự thay đổi phân loại metadata trong mỗi bản ghi.

## 8. Metadata không phải API đọc giá trị tại một instance

Để đọc giá trị, cần một đối tượng dữ liệu và cơ chế truy cập tương ứng.

Abstraction liên quan là `PersistentPropertyAccessor`. Ví dụ helper generic:

~~~java
import org.springframework.data.mapping.PersistentEntity;
import org.springframework.data.mapping.PersistentProperty;

public static <T, P extends PersistentProperty<P>> Object readValue(
        PersistentEntity<T, P> entity,
        P property,
        T instance) {

    return entity.getPropertyAccessor(instance)
        .getProperty(property);
}
~~~

Ở đây:

- `entity` và `property` mô tả mô hình.
- `instance` là đối tượng dữ liệu cụ thể.
- Accessor đọc giá trị theo cơ chế truy cập được hỗ trợ.

Không tự chuyển `property.getName()` thành thao tác reflection vào private field khi framework đã có accessor phù hợp.

Với mô hình bất biến, thao tác thay đổi thuộc tính có thể cần constructor hoặc cơ chế tạo lại đối tượng. Cờ `isWritable()` không nên được hiểu thành “có thể tùy ý sửa mọi object bằng reflection”.

Cũng cần tách việc thay giá trị trong một object khỏi việc lưu giá trị đó về store. Metadata và accessor không tự thay thế một thao tác persistence.

## 9. Collection, map và số lượng liên kết là các trục khác nhau

Cần phân loại một property theo nhiều câu hỏi độc lập:

| Câu hỏi | Ví dụ thông tin |
|---|---|
| Kiểu chứa là gì? | Một giá trị, mảng, collection hay map |
| Kiểu giá trị bên trong là gì? | String, LineItem, Address hoặc Customer |
| Module có nhận diện association không? | Có/Không theo quy tắc ánh xạ |
| Dữ liệu được lưu theo cấu trúc nào? | Nhúng, tham chiếu hoặc cấu trúc khác |
| Vòng đời dữ liệu do ai quản lý? | Aggregate, entity riêng hoặc quy tắc ứng dụng |

So sánh:

~~~java
private List<LineItem> items;
~~~

với:

~~~java
@DBRef
private List<Customer> reviewers;
~~~

Cả hai đều chứa nhiều phần tử. Nhưng trong ví dụ MongoDB, một bên có thể là danh sách giá trị nhúng, bên còn lại là danh sách tham chiếu được module nhận diện.

Cờ `isCollectionLike()` không thay thế `isAssociation()`. Cả hai cũng không tự cho biết:

- Có tải dữ liệu theo kiểu lazy hay không.
- Có tự lưu hoặc xóa phần tử liên quan không.
- Có ràng buộc duy nhất hoặc bắt buộc hay không.
- Có cần join hoặc truy vấn riêng khi đọc không.

Với map, còn có phân biệt khóa map và giá trị map. Không nên coi mọi key động là một property Java được khai báo tĩnh.

## 10. Từ property đơn đến đường dẫn thuộc tính

Một đường dẫn như:

~~~text
shippingAddress.city
~~~

gồm nhiều property:

~~~text
PurchaseOrder.shippingAddress
Address.city
~~~

Để hiểu đầy đủ, cần:

1. Tìm metadata của `shippingAddress` trong owner PurchaseOrder.
2. Xác định kiểu giá trị mà property mô tả.
3. Lấy metadata phù hợp của Address nếu context hỗ trợ.
4. Tìm property `city` trong Address.

Một property đơn không tự chứa toàn bộ ý nghĩa của mọi đường dẫn đi qua nó.

### 10.1. Tên đường dẫn Java khác đường dẫn lưu trữ

Trong ví dụ:

~~~text
Tên Java: orderNumber
Tên lưu: order_no
~~~

Công cụ metadata chung nên giữ rõ hai vai trò. Metadata module có thể bổ sung tên trường, cột hoặc thông tin lưu trữ tương ứng.

Không thay tên Java bằng tên lưu rồi dùng tùy tiện cho mọi API repository. Derived query, projection, sort hoặc matcher có quy tắc tiếp nhận đường dẫn riêng.

### 10.2. Đi qua collection cần ngữ nghĩa truy vấn

Đường dẫn hình dung:

~~~text
items.sku
~~~

không chỉ là đọc một field trên một object duy nhất. Nó đi qua nhiều LineItem.

Một truy vấn cần quy định điều gì được yêu cầu:

- Có ít nhất một phần tử có sku khớp?
- Tất cả phần tử đều phải khớp?
- Hai điều kiện phải cùng đúng trên một phần tử hay có thể đúng ở hai phần tử khác nhau?

Metadata giúp biết đã đi qua collection; nó không tự chọn các lượng từ truy vấn thay ứng dụng.

Ví dụ:

~~~text
items có sku = A
AND items có quantity > 10
~~~

có thể cần yêu cầu “cùng một LineItem”. Chỉ duyệt được hai đường dẫn metadata không chứng minh API truy vấn đã diễn đạt đúng ràng buộc đó.

### 10.3. Đi qua map cần xử lý khóa động

Với:

~~~java
Map<String, Address> contactsByRole;
~~~

metadata biết giá trị map là Address, nhưng không tự biết dữ liệu hiện có những khóa nào như `billing` hay `shipping`.

Cách truy cập một khóa cụ thể trong truy vấn phụ thuộc store. Đừng tự ghép dấu chấm rồi cho rằng mọi backend sẽ hiểu như nhau.

## 11. Duyệt đồ thị metadata mà không bị vòng lặp

Một công cụ tạo báo cáo metadata có thể muốn duyệt tất cả kiểu liên quan.

Nhưng mô hình có thể chứa vòng:

~~~text
PurchaseOrder -> Customer -> PurchaseOrder -> ...
~~~

Nếu cứ gặp kiểu phức hợp là đệ quy tiếp, công cụ có thể lặp vô hạn.

Một thiết kế cần xác định:

- Duyệt cấu trúc nhúng hay cả tham chiếu?
- Có theo association sang kiểu đích không?
- Dừng ở simple type theo cấu hình nào?
- Giới hạn độ sâu là bao nhiêu?
- Cách nhận diện một kiểu hoặc đường đi đã gặp?

### 11.1. Mục đích báo cáo quyết định cách đánh dấu đã thăm

Có hai mục đích khác nhau:

| Mục đích | Cách xử lý cần cân nhắc |
|---|---|
| Lập danh sách các kiểu trong đồ thị | Có thể đánh dấu toàn cục các kiểu đã gặp |
| Liệt kê mọi đường dẫn từ một root | Cần giữ ngữ cảnh đường đi và chặn vòng trên nhánh hiện tại |

Nếu PurchaseOrder có cả `shippingAddress` và `billingAddress`, việc đánh dấu Address đã thăm toàn cục ngay sau nhánh đầu có thể làm mất các đường dẫn ở nhánh thứ hai.

Ngược lại, nếu chỉ cần danh sách kiểu, lặp lại mọi property của Address cho từng đường đi có thể không cần thiết.

Với mô hình generic, khóa nhận diện chỉ bằng `Class<?>` đôi khi không giữ đủ khác biệt kiểu. Khi cần phân biệt các ngữ cảnh generic, hãy dùng thông tin kiểu phù hợp từ metadata.

### 11.2. Nhận diện cấu trúc lưu trữ trước khi đệ quy

Không phải mọi kiểu Java phức tạp đều nên bị mở ra thành cây property.

Một kiểu giá trị như Money có thể được converter lưu thành biểu diễn đơn giản. Khi đó, công cụ phải theo cấu hình mapping/conversion thực tế thay vì chỉ thấy đây là một class có nhiều field.

Tương tự, theo association sang một entity khác là lựa chọn của công cụ; nó không có cùng ý nghĩa với mở rộng object nhúng bên trong cùng tài liệu hoặc aggregate.

### 11.3. Phác thảo thuật toán

~~~text
describe(property, path, ancestors):
    xuất tên, owner, kiểu và các cờ metadata

    nếu property là association:
        xuất metadata liên kết
        quyết định có theo sang kiểu liên quan hay không

    xác định kiểu giá trị:
        map -> xét kiểu giá trị map
        collection/array -> xét kiểu phần tử
        còn lại -> xét kiểu property

    nếu kiểu chưa xác định, là simple type hoặc đạt giới hạn:
        dừng

    nếu kiểu tạo vòng trên đường đi hiện tại:
        ghi nhận vòng và dừng nhánh

    lấy persistent entity từ context đã cấu hình
    duyệt các property theo hợp đồng API của entity đó
~~~

Đây là thuật toán mô tả, không phải cam kết rằng một API Commons duy nhất có thể suy ra mọi kiểu lưu trữ và vòng đời của mọi store.

Khi dùng callback duyệt property và callback duyệt association, cần đọc hợp đồng của API tương ứng. Không cộng hai kết quả một cách máy móc rồi cho rằng chúng luôn là hai tập độc lập trong mọi cách truy xuất metadata.

## 12. Mapping context phải phù hợp môi trường thực tế

Metadata có ý nghĩa trong context đã tạo nó.

Một context được cấu hình bởi ứng dụng có thể biết:

- Các kiểu được nhận diện là persistent type.
- Những kiểu được coi là simple type.
- Quy tắc đặt tên và annotation của module.
- Thông tin generic và các đặc điểm ánh xạ liên quan.
- Cấu hình cần phối hợp với conversion của module.

Nếu công cụ tự tạo một context khác rồi bỏ qua các cấu hình đó, kết quả có thể lệch với cách ứng dụng thực sự đọc và ghi dữ liệu.

Ví dụ, ứng dụng có converter đặc biệt cho Address nhưng công cụ lại đệ quy vào các field của Address theo giả định mặc định. Báo cáo khi đó có thể mô tả cấu trúc không tương ứng với dữ liệu lưu.

Đọc metadata trong context phù hợp thường hữu ích hơn tự quét `getDeclaredFields()` rồi đoán mọi quy tắc.

## 13. Không áp dụng nguyên vẹn mô hình của một store sang store khác

| Ngữ cảnh | Điểm cần phân biệt |
|---|---|
| MongoDB | Object nhúng và tham chiếu như DBRef có cách ánh xạ riêng |
| JDBC/R2DBC | Cấu trúc aggregate, bảng con và tham chiếu định danh có quy tắc của module |
| JPA | Quan hệ và entity metadata gắn với metamodel, mapping và provider JPA |
| Công cụ dùng Commons | Chỉ có thể dựa vào phần hợp đồng chung mà implementation thực sự cung cấp |

Ví dụ JPA có các khái niệm `@ManyToOne`, `@OneToMany`, owning side và `mappedBy`. Không lấy kết quả `Association` của một context MongoDB để giải thích thay cho các khái niệm đó.

Cũng không mặc định mọi module JPA đều cung cấp cùng một mapping context với mô hình property giống MongoDB. Một số nhu cầu metadata JPA đi qua metamodel và các abstraction riêng của module/provider.

Điều có thể dùng chung là cách đặt câu hỏi: owner là ai, property có kiểu gì, container chứa gì, module nhận diện vai trò nào và cơ chế store nào chịu trách nhiệm thực thi.

## 14. Ứng dụng thực tế của metadata thuộc tính

Một số công cụ có thể tận dụng `PersistentProperty` và `Association`:

| Công cụ | Giá trị của metadata | Giới hạn cần giữ rõ |
|---|---|---|
| Báo cáo cấu trúc mô hình | Liệt kê owner, tên, kiểu và vai trò | Không phải bản sao schema database đầy đủ |
| Công cụ chẩn đoán ánh xạ | So sánh tên Java, annotation và metadata module | Cần dùng context thực tế |
| Xây đường dẫn thuộc tính | Biết các bước chuyển kiểu và container | Chưa chứng minh một query API hỗ trợ đường dẫn đó |
| Hỗ trợ kiểm tra quy tắc chung | Nhận diện id, version và đặc điểm property | Không tự thay thế validation nghiệp vụ |
| Công cụ đọc/ghi object | Kết hợp metadata với property accessor | Không tự lưu dữ liệu xuống store |
| Tạo biểu diễn dữ liệu | Biết kiểu và liên kết để chọn cách trình bày | Cần hợp đồng serialization và vòng tham chiếu riêng |

Không nên tự sinh một API cập nhật mọi property chỉ vì metadata cho biết chúng tồn tại. Việc cho phép sửa thuộc tính nào thuộc hợp đồng ứng dụng; định danh, phiên bản và giá trị tính toán có vai trò khác nhau.

## 15. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `PersistentProperty` chứa giá trị của một bản ghi | Nó mô tả property; đọc giá trị cần instance và accessor |
| Owner của `PurchaseOrder.customer` là Customer | Owner là metadata PurchaseOrder |
| Mọi class lồng nhau đều là association | Object nhúng và association là các phân loại khác nhau |
| Mọi collection đều là liên kết tới entity riêng | Collection có thể chứa simple value hoặc giá trị nhúng |
| Trường tên `customerId` tự tạo tham chiếu | Cần quy tắc/annotation/module hoặc logic ứng dụng phù hợp |
| `getType()` đủ cho mọi generic type | Container và kiểu phần tử cần được phân biệt |
| Lookup property null nghĩa là dữ liệu null | Đó là việc không có metadata trong lookup hiện tại |
| Có association thì dữ liệu đích luôn tồn tại | Metadata không tự bảo đảm toàn vẹn tham chiếu |
| Có hai phía metadata thì dữ liệu tự đồng bộ | Vòng đời và đồng bộ phụ thuộc store và ứng dụng |
| Tên các phía association chính là owning/inverse JPA | Không được gán ngữ nghĩa đó một cách chung |
| Field transient luôn xuất hiện trong vòng duyệt | Module có thể loại khỏi tập persistent properties |
| Metadata duyệt được nghĩa là query hỗ trợ | Khả năng truy vấn còn phụ thuộc API và module |

## 16. Bài thực hành

### 16.1. Lập bảng property

Với mô hình MongoDB ở mục 5, đọc metadata và điền:

| Thuộc tính | Owner | Kiểu chứa | Kiểu phần tử/giá trị | Vai trò đặc biệt | Association? |
|---|---|---|---|---|---|
| id |  |  |  |  |  |
| orderNumber |  |  |  |  |  |
| shippingAddress |  |  |  |  |  |
| items |  |  |  |  |  |
| contactsByRole |  |  |  |  |  |
| customer |  |  |  |  |  |
| customerId |  |  |  |  |  |

Chỉ dùng metadata từ context để kết luận; không gán nhãn association theo tên trường.

### 16.2. Quan sát khác biệt giữa metadata và dữ liệu

Tạo hai đối tượng PurchaseOrder trong ứng dụng học tập:

- Một đối tượng có customer.
- Một đối tượng có customer bằng null.

Xác nhận property metadata của `customer` vẫn mô tả cùng một quy tắc ánh xạ. Sau đó dùng accessor phù hợp để quan sát hai giá trị khác nhau.

Bản thân việc đọc metadata không yêu cầu gọi repository để tải một customer.

### 16.3. Thay đổi mô hình có kiểm soát

Trong môi trường thực hành:

1. So sánh một thuộc tính Customer có `@DBRef` với một thuộc tính Customer được ánh xạ nhúng.
2. So sánh `List<LineItem>` với raw `List` và quan sát thông tin kiểu phần tử.
3. Thêm một thuộc tính Address thứ hai để kiểm tra thuật toán liệt kê đường dẫn không bỏ mất nhánh.
4. Tạo một vòng tham chiếu kiểu và xác nhận công cụ có điểm dừng.
5. Kiểm tra lookup của thuộc tính `@Transient` thay vì giả định nó phải xuất hiện.
6. Quan sát `orderNumber` so với tên lưu `order_no`.

### 16.4. Tự giải thích kết quả

Với mỗi quan sát, trả lời:

- Thông tin này thuộc metadata hay giá trị của một object?
- Kết luận dựa trên hợp đồng Commons hay quy tắc MongoDB?
- Có cần thông tin generic để hiểu đúng property không?
- Có đang suy ra quá nhiều về fetch, cascade hoặc truy vấn từ một cờ metadata không?

Một cách đọc metadata đáng tin cậy luôn tách các lớp: property mô tả thuộc tính, association mô tả liên kết mà module nhận diện, accessor làm việc với giá trị của instance và store quyết định cách persistence thực thi. Giữ rõ các lớp đó giúp sử dụng abstraction Spring Data Commons đúng với mô hình và khả năng của từng kho dữ liệu.
