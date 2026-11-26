# MappingContext và tập kiểu miền được quản lý

## 1. MappingContext quản lý điều gì?

Để đọc hoặc ghi một đối tượng miền, hạ tầng Spring Data cần biết những thông tin như:

- Kiểu miền có những thuộc tính nào.
- Thuộc tính nào là định danh hoặc phiên bản.
- Thuộc tính nào không được lưu.
- Một thuộc tính có trỏ đến kiểu miền khác hay không.
- Tên thuộc tính Java được ánh xạ theo quy tắc nào của store.

`MappingContext` là abstraction của Spring Data Commons cung cấp điểm truy cập đến **metadata ánh xạ** của các kiểu miền.

Nó quản lý mô tả của kiểu, không phải danh sách các bản ghi đã lưu. Ví dụ:

~~~text
Metadata của CustomerDocument:
    id          -> thuộc tính định danh
    displayName -> thuộc tính được ánh xạ
    address     -> thuộc tính có kiểu Address

Dữ liệu khách hàng:
    khách hàng A
    khách hàng B
    khách hàng C
~~~

Hai phần trên khác nhau. Có metadata của `CustomerDocument` không chứng minh store đang có khách hàng nào. Xóa toàn bộ dữ liệu cũng không có nghĩa metadata của kiểu đó biến mất.

Sau bài học, bạn có thể:

- Giải thích vai trò của `MappingContext`, `PersistentEntity` và `PersistentProperty`.
- Phân biệt tập kiểu đầu vào với những metadata đã được context đăng ký.
- Đọc metadata mà không nhầm tên thuộc tính với tên field lưu trữ.
- Hiểu việc khám phá kiểu lồng nhau và khởi tạo metadata khi được yêu cầu.
- Chọn đúng context của store thay vì coi mọi mapping context là tương đương.

## 2. Ba abstraction phối hợp với nhau

Các abstraction chính nằm trong những package sau:

~~~java
import org.springframework.data.mapping.PersistentEntity;
import org.springframework.data.mapping.PersistentProperty;
import org.springframework.data.mapping.context.MappingContext;
~~~

| Abstraction | Mô tả | Ví dụ |
| --- | --- | --- |
| `MappingContext` | Registry và điểm truy cập metadata của các kiểu miền | Context biết metadata của Customer và Address |
| `PersistentEntity` | Metadata của một kiểu miền | Kiểu Java, thuộc tính ID, danh sách thuộc tính |
| `PersistentProperty` | Metadata của một thuộc tính | Tên, kiểu dữ liệu, vai trò ID, quan hệ với kiểu khác |

Từ “entity” trong `PersistentEntity` là tên abstraction metadata của Spring Data. Nó không mặc nhiên có nghĩa một kiểu được gắn `jakarta.persistence.Entity` hoặc luôn có một bảng/collection riêng.

~~~mermaid
flowchart LR
    C["MappingContext của store"] --> E["PersistentEntity của Customer"]
    E --> I["PersistentProperty: id"]
    E --> N["PersistentProperty: displayName"]
    E --> A["PersistentProperty: address"]
    A --> AE["Metadata Address khi cần theo quy tắc store"]
~~~

### 2.1. Vì sao MappingContext có hai tham số kiểu?

Về cấu trúc, context liên kết một loại entity metadata với một loại property metadata:

~~~java
MappingContext<E, P>
~~~

Trong đó `E` là một kiểu `PersistentEntity` phù hợp, còn `P` là kiểu `PersistentProperty` mà entity đó sử dụng.

Đây là cách mỗi module mở rộng hợp đồng Commons bằng metadata riêng. Ví dụ, một property metadata của MongoDB có thể cung cấp thông tin tên field trong tài liệu mà interface Commons không mô tả bằng một API duy nhất cho mọi store.

Khi chỉ đọc thông tin chung, có thể làm việc với `MappingContext<?, ?>`. Khi cần chi tiết của MongoDB, relational hoặc JPA, dùng kiểu metadata tương ứng với store đó.

### 2.2. Metadata không thay thế converter

Mapping context mô tả mô hình để các thành phần khác sử dụng. Converter, truy vấn, auditing hoặc những hạ tầng liên quan có thể dựa vào metadata này.

Không suy ra rằng chỉ gọi `getPersistentEntity` sẽ:

- Đọc một bản ghi theo ID.
- Chuyển một document thành đối tượng hoàn chỉnh.
- Lưu đối tượng xuống store.
- Tạo bảng hoặc xác nhận schema đã tồn tại.

Các thao tác đó thuộc những thành phần khác. Việc đăng ký metadata cũng có thể gắn với lifecycle và sự kiện của hạ tầng; không nên xem mọi lời gọi lookup là một hàm thuần không làm thay đổi registry.

## 3. Phân biệt với các loại context khác

| Khái niệm | Quản lý chủ yếu | Không nên hiểu thành |
| --- | --- | --- |
| Spring `ApplicationContext` | Bean, dependency và vòng đời thành phần | Registry chỉ dành cho thuộc tính domain |
| Spring Data `MappingContext` | Metadata của kiểu miền và thuộc tính | Danh sách instance đang được theo dõi |
| JPA persistence context | Trạng thái các entity instance trong một đơn vị làm việc | Tập mô tả metadata dùng chung của Commons |
| JPA metamodel | Mô hình ánh xạ của persistence unit do JPA provider cung cấp | Một tập dữ liệu truy vấn được từ store |

Một Spring Data module có thể kết nối các lớp này, nhưng chúng không đồng nhất.

Ví dụ, một `Customer` đang được JPA theo dõi thay đổi là chuyện của persistence context. Việc hạ tầng biết `Customer` có thuộc tính ID nào là chuyện metadata.

“Tập kiểu được quản lý” trong bài nói về các **kiểu và metadata ánh xạ**, không phải trạng thái managed/detached của một entity instance JPA.

## 4. Tập kiểu đầu vào và tập metadata đã biết

Có hai tập cần phân biệt:

1. Các kiểu được cung cấp cho quá trình khởi tạo mapping.
2. Các kiểu mà context đã có metadata tại một thời điểm.

Hai tập không nhất thiết bằng nhau.

### 4.1. Tập kiểu đầu vào đến từ đâu?

Tùy module và cấu hình, đầu vào có thể được xác định từ:

- Quá trình quét domain trong những package đã cấu hình.
- Annotation nhận diện kiểu persistent của store.
- Một danh sách kiểu được cung cấp chủ động.
- Cấu hình và metadata của provider mà module tích hợp.

Spring Data Commons có abstraction `ManagedTypes` để biểu diễn một tập kiểu được cung cấp cho hạ tầng:

~~~java
import org.springframework.data.domain.ManagedTypes;

ManagedTypes types = ManagedTypes.from(
        CustomerDocument.class);
~~~

Đoạn này chỉ tạo đầu vào kiểu Java; nó chưa đọc dữ liệu và chưa tự tạo một mapping context.

Các API cấu hình cụ thể phụ thuộc module và phiên bản đang dùng. Trong ví dụ MongoDB ở phần sau, đầu vào này được chuyển cho `MongoMappingContext` thông qua `setManagedTypes`.

### 4.2. Các kiểu liên quan có thể được khám phá thêm

Giả sử `CustomerDocument` có thuộc tính `Address address`. Store có thể cần metadata của `Address` để ánh xạ giá trị lồng nhau.

Do đó:

~~~text
Đầu vào ban đầu:
    CustomerDocument

Trong quá trình xây dựng metadata:
    CustomerDocument
    Address nếu được mô hình và quy tắc store yêu cầu
~~~

`Address` không nhất thiết là một aggregate root hoặc có collection riêng. Nó có thể chỉ là một đối tượng được nhúng.

Ngược lại, các kiểu đơn giản như chuỗi hoặc số không nhất thiết được đăng ký thành một `PersistentEntity` riêng. Bộ phân loại simple type và custom conversion có ảnh hưởng đến cách phân tích này.

### 4.3. Tập metadata có thể thay đổi khi lookup

Với nhiều implementation dựa trên `AbstractMappingContext`, lookup một kiểu chưa biết có thể dẫn tới việc tạo và đăng ký metadata khi kiểu đó đủ điều kiện.

Vì vậy, thứ tự:

~~~text
liệt kê metadata
lookup một kiểu mới
liệt kê metadata lần nữa
~~~

có thể cho hai danh sách khác nhau.

Không dùng một danh sách quan sát được tại thời điểm đầu để kết luận rằng context sẽ không bao giờ biết thêm kiểu nào. Cũng không hiểu đầu vào ban đầu là một whitelist tuyệt đối trong mọi chế độ.

Một số implementation có chế độ nghiêm ngặt hoặc quy tắc hạn chế việc tiếp nhận kiểu chưa biết. Cần xác định hành vi theo context được dùng, thay vì gán một quy tắc chung cho toàn bộ Spring Data.

## 5. Các thao tác quan trọng trên MappingContext

| Thao tác | Ý nghĩa |
| --- | --- |
| `getPersistentEntities()` | Lấy các metadata entity mà context cung cấp tại thời điểm gọi |
| `getManagedTypes()` | Lấy tập thông tin kiểu mà context quản lý theo hợp đồng của nó |
| `getPersistentEntity(type)` | Yêu cầu metadata của một kiểu; có thể không có kết quả |
| `getRequiredPersistentEntity(type)` | Yêu cầu metadata bắt buộc; lỗi nếu không có |
| `getPersistentPropertyPath(path, type)` | Phân giải đường dẫn thuộc tính theo mô hình metadata |

### 5.1. Lookup thông thường và lookup bắt buộc

~~~java
PersistentEntity<?, ?> entity =
        context.getPersistentEntity(CustomerDocument.class);

if (entity != null) {
    System.out.println(entity.getType().getName());
}
~~~

Ở đây `context` có kiểu `MappingContext<?, ?>`. Phải xử lý trường hợp không có metadata, chẳng hạn kiểu không được context xem là một persistent entity.

Nếu thiết kế của thành phần yêu cầu chắc chắn có metadata:

~~~java
PersistentEntity<?, ?> entity =
        context.getRequiredPersistentEntity(
                CustomerDocument.class);
~~~

Hợp đồng `getRequiredPersistentEntity` báo lỗi `MappingException` khi không tìm được metadata cần thiết. Nó không phải phép kiểm tra sự tồn tại của một khách hàng trong cơ sở dữ liệu.

Đừng dùng lookup bắt buộc để “thử xem kiểu nào cũng được”, rồi bắt mọi lỗi và coi đó là không có dữ liệu nghiệp vụ.

### 5.2. ManagedTypes và getManagedTypes không phải cùng một đối tượng

| Thành phần | Vai trò |
| --- | --- |
| `ManagedTypes` | Abstraction đầu vào chứa các lớp Java cho quá trình cấu hình |
| `MappingContext.getManagedTypes()` | Thông tin kiểu được context quản lý, biểu diễn bằng `TypeInformation` |

Không suy ra hai thành phần có cùng tên gợi ý thì cùng kiểu trả về hoặc cùng vòng đời.

Danh sách context quản lý cũng không phải danh sách bean của Spring, danh sách repository hoặc danh sách bảng/collection vật lý.

### 5.3. Không dựa vào thứ tự trả về của registry

Registry metadata không phải bảng xếp hạng các kiểu. Nếu cần báo cáo ổn định, tự sắp xếp tên kiểu khi hiển thị.

Không dùng “phần tử đầu tiên trong context” để chọn domain cho một thành phần generic. Domain cần được xác định từ hợp đồng hoặc cấu hình rõ ràng.

## 6. Ví dụ domain với MongoDB

Phần này dùng MongoDB để minh họa vì metadata của store thể hiện rõ sự khác nhau giữa tên thuộc tính Java và tên field tài liệu.

Mỗi kiểu `public` dưới đây đặt trong một file Java riêng khi áp dụng vào ứng dụng. Ví dụ giả định bộ thư viện Spring Data MongoDB/Commons tương thích với các API được dùng.

### 6.1. Kiểu lồng Address

~~~java
import org.springframework.data.mongodb.core.mapping.Field;

public class Address {

    @Field("city_name")
    private String city;

    private String street;

    public Address() {
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }

    public String getStreet() {
        return street;
    }

    public void setStreet(String street) {
        this.street = street;
    }
}
~~~

### 6.2. CustomerDocument

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "customers")
public class CustomerDocument {

    @Id
    private String id;

    @Field("full_name")
    private String displayName;

    private Address address;

    @Version
    private Long version;

    @Transient
    private String temporaryLabel;

    public CustomerDocument() {
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }

    public Long getVersion() {
        return version;
    }

    public void setVersion(Long version) {
        this.version = version;
    }

    public String getTemporaryLabel() {
        return temporaryLabel;
    }

    public void setTemporaryLabel(String temporaryLabel) {
        this.temporaryLabel = temporaryLabel;
    }
}
~~~

Các thông tin cần phân biệt:

| Thành phần | Ý nghĩa |
| --- | --- |
| `CustomerDocument` | Kiểu domain được đánh dấu cho MongoDB |
| `customers` | Collection được khai báo cho domain này |
| `displayName` | Tên thuộc tính Java |
| `full_name` | Tên field lưu trữ được khai báo cho thuộc tính |
| `address.city` | Đường dẫn thuộc tính domain |
| `version` | Thuộc tính mang vai trò phiên bản |
| `temporaryLabel` | Thuộc tính không được lưu theo annotation transient của Spring Data |

Metadata mô tả vai trò phiên bản không có nghĩa chỉ việc tạo metadata đã tăng version hay thực hiện optimistic locking. Hành vi đó thuộc luồng đọc/ghi mà store hỗ trợ.

## 7. Khởi tạo một context độc lập để quan sát metadata

Có thể dùng đoạn minh họa sau khi các lớp domain ở phần trước đã có trong dự án:

~~~java
import org.springframework.data.domain.ManagedTypes;
import org.springframework.data.mongodb.core.mapping.MongoMappingContext;

public class MappingContextDemo {

    public static void main(String[] args) throws Exception {
        ManagedTypes inputTypes =
                ManagedTypes.from(CustomerDocument.class);

        MongoMappingContext context =
                new MongoMappingContext();

        context.setManagedTypes(inputTypes);
        context.afterPropertiesSet();

        context.getPersistentEntities().stream()
                .map(entity -> entity.getType().getName())
                .sorted()
                .forEach(System.out::println);
    }
}
~~~

Đoạn này tạo và khởi tạo một context metadata MongoDB độc lập. Nó không tạo `MongoClient`, `MongoTemplate` hoặc repository và không thực hiện thao tác đọc/ghi tài liệu.

Đầu vào công bố `CustomerDocument`. Trong quá trình phân tích, context có thể đăng ký thêm kiểu liên quan theo quy tắc mapping, chẳng hạn `Address` trong mô hình lồng nhau.

Không lấy một con số entity cố định trong ví dụ để làm hợp đồng cho mọi dự án. Domain, quy tắc simple type, conversion và những lookup đã thực hiện có thể ảnh hưởng tập metadata.

### 7.1. Đây là ví dụ quan sát, không phải cách thay context của ứng dụng

Trong một ứng dụng Spring Data đang được cấu hình, context thường đã có:

- Tập kiểu đầu vào được xác định bởi hạ tầng.
- Quy tắc đặt tên của store.
- Thông tin simple type và conversion liên quan.
- Cấu hình annotation và các thành phần lifecycle.

Tạo một context mới bằng `new` không bảo đảm tái tạo toàn bộ cấu hình đó. Nếu thành phần ứng dụng cần biết mapping thực sự mà converter hoặc repository đang dùng, nên lấy đúng bean context được cấu hình cho store ấy.

### 7.2. Cấu hình trước khi khởi tạo metadata

Những thiết lập ảnh hưởng cách phân tích kiểu nên được chuẩn bị trước khi context xây dựng metadata. Không coi việc thay cấu hình sau khi một kiểu đã được đăng ký là cách tự động tái tạo toàn bộ metadata cũ.

Đặc biệt, khi custom conversion làm một value object được xử lý như một giá trị đơn giản, hạ tầng cần nhận đúng cấu hình tương ứng. Một context thử nghiệm thiếu cấu hình đó có thể phân tích kiểu khác với context của ứng dụng.

## 8. Đọc metadata bằng hợp đồng Commons

Nếu chỉ cần tên kiểu và thông tin thuộc tính chung, không nhất thiết phụ thuộc vào MongoDB.

~~~java
import java.util.Objects;
import org.springframework.data.mapping.PersistentEntity;
import org.springframework.data.mapping.PersistentProperty;
import org.springframework.data.mapping.context.MappingContext;

public final class MappingMetadataPrinter {

    private MappingMetadataPrinter() {
    }

    public static void printTypes(
            MappingContext<?, ?> context) {

        Objects.requireNonNull(context, "context");

        context.getPersistentEntities().stream()
                .map(entity -> entity.getType().getName())
                .sorted()
                .forEach(System.out::println);
    }

    public static void printProperties(
            MappingContext<?, ?> context,
            Class<?> domainType) {

        Objects.requireNonNull(context, "context");
        Objects.requireNonNull(domainType, "domainType");

        PersistentEntity<?, ?> entity =
                context.getRequiredPersistentEntity(domainType);

        for (PersistentProperty<?> property : entity) {
            System.out.printf(
                    "%s: type=%s, id=%s%n",
                    property.getName(),
                    property.getType().getName(),
                    property.isIdProperty());
        }
    }
}
~~~

Có thể gọi:

~~~java
MappingMetadataPrinter.printTypes(context);

MappingMetadataPrinter.printProperties(
        context,
        CustomerDocument.class);
~~~

Utility này chỉ đọc phần metadata Commons. Nó không giả định mỗi property đều có một tên cột SQL hoặc tên field MongoDB qua cùng một phương thức.

### 8.1. Metadata property không chỉ là reflection thô

Không thay việc duyệt `PersistentEntity` bằng `getDeclaredFields()` rồi mặc định kết quả tương đương.

Quy tắc persistence có thể liên quan đến:

- Thuộc tính kế thừa.
- Field hoặc accessor.
- Annotation transient.
- ID và version.
- Association và cấu trúc lồng nhau.
- Quy tắc riêng của module.

Context cung cấp metadata đã được diễn giải theo các quy tắc mapping tương ứng, thay vì chỉ liệt kê những field khai báo trực tiếp trong một lớp Java.

### 8.2. Không mặc định mọi PersistentEntity đều có ID

Kiểu aggregate root thường cần định danh, nhưng một kiểu lồng nhau như `Address` có thể không có thuộc tính ID riêng.

Khi viết công cụ dùng chung, xử lý trường hợp thiếu ID:

~~~java
PersistentEntity<?, ?> entity =
        context.getRequiredPersistentEntity(Address.class);

PersistentProperty<?> idProperty = entity.getIdProperty();

if (idProperty == null) {
    System.out.println("Kiểu này không có thuộc tính ID riêng");
} else {
    System.out.println(idProperty.getName());
}
~~~

Đoạn này giả định context có thể cung cấp metadata `Address` theo mô hình đang dùng. Không biến “không có ID” của một kiểu nhúng thành lỗi chung cho mọi metadata.

Việc có ID cũng không chứng minh đối tượng đã được lưu hoặc bản ghi tương ứng còn tồn tại. Đó là thông tin khác với mô tả cấu trúc của kiểu.

## 9. Đọc chi tiết thuộc store một cách rõ ràng

Với context MongoDB trong ví dụ:

~~~java
import org.springframework.data.mongodb.core.mapping.MongoPersistentEntity;
import org.springframework.data.mongodb.core.mapping.MongoPersistentProperty;

MongoPersistentEntity<?> entity =
        context.getRequiredPersistentEntity(
                CustomerDocument.class);

MongoPersistentProperty displayName =
        entity.getPersistentProperty("displayName");

if (displayName == null) {
    throw new IllegalStateException(
            "Thiếu metadata của displayName");
}

System.out.println(displayName.getName());
System.out.println(displayName.getFieldName());
System.out.println(entity.getCollection());
~~~

Theo các annotation đã khai báo, thông tin mong đợi là:

~~~text
displayName
full_name
customers
~~~

Các phương thức `getFieldName()` và `getCollection()` ở đây là khả năng của metadata MongoDB, không phải một giao diện lưu trữ thống nhất cho mọi `PersistentProperty` hay `PersistentEntity`.

### 9.1. Tên thuộc tính và tên field có hai vai trò

Khi tra property bằng metadata domain:

~~~java
entity.getPersistentProperty("displayName");
~~~

khóa tra là tên thuộc tính Java. Không thay bằng `"full_name"` rồi mặc định đây là cùng một lookup.

Khi cần làm việc với biểu diễn lưu trữ MongoDB, dùng metadata và thành phần ánh xạ của MongoDB. Những API truy vấn khác nhau có thể nhận tên domain hoặc cú pháp lưu trữ theo hợp đồng riêng; cần xác định đúng lớp đang thao tác.

### 9.2. Annotation đúng namespace là một phần của mô hình

`org.springframework.data.annotation.Transient` trong ví dụ được dùng theo quy tắc Spring Data MongoDB. Một annotation có cùng tên đơn giản ở namespace khác không tự có cùng ý nghĩa đối với mọi module.

Tương tự, không chuyển nguyên một bộ annotation MongoDB sang entity JPA rồi kỳ vọng metadata JPA đọc chúng như nhau.

Commons cung cấp abstraction; mỗi module diễn giải những annotation và cấu hình mà nó hỗ trợ.

## 10. Phân giải đường dẫn thuộc tính lồng nhau

Để đi từ `CustomerDocument` qua `address` đến `city`:

~~~java
var path = context.getPersistentPropertyPath(
        "address.city",
        CustomerDocument.class);

System.out.println(path.toDotPath());
System.out.println(path.getLeafProperty().getName());
System.out.println(path.getLeafProperty().getFieldName());
~~~

Đoạn dùng `var` yêu cầu Java 10 trở lên. Theo mô hình MongoDB đã khai báo, các thông tin mong đợi là:

~~~text
address.city
city
city_name
~~~

Đường dẫn đầu vào là đường dẫn thuộc tính domain, không phải một đường dẫn vật lý được đoán từ annotation.

Các bước về mặt ý nghĩa:

1. Tìm metadata của `CustomerDocument`.
2. Xác định property `address`.
3. Đi vào metadata kiểu `Address` theo quy tắc mapping.
4. Xác định property `city`.

### 10.1. Lookup property trực tiếp khác với phân giải path

`entity.getPersistentProperty("displayName")` tìm một property trên entity metadata.

`context.getPersistentPropertyPath("address.city", CustomerDocument.class)` phân giải một chuỗi qua nhiều property.

Không coi một chuỗi có dấu chấm truyền vào lookup property trực tiếp là thay thế mặc định cho API phân giải đường dẫn.

### 10.2. Không tự suy ra mọi đường dẫn lưu trữ bằng cách ghép chuỗi

Trong mô hình đơn giản, tên field lồng nhau có vẻ dễ nối. Nhưng naming strategy, association, cấu trúc tài liệu hoặc conversion có thể làm cách biểu diễn khác đi.

Nếu cần chuyển một điều kiện domain sang truy vấn thực tế, dùng mapper/converter/query API đúng store. `PersistentPropertyPath` giúp hiểu và xác nhận đường dẫn domain; nó không tự trở thành một ngôn ngữ truy vấn chung cho mọi nguồn dữ liệu.

Một đường dẫn sai phải được xem là lỗi mô hình hoặc yêu cầu, không được âm thầm chuyển thành “không có bản ghi”.

## 11. Dùng context được cấu hình trong ứng dụng

Với một ứng dụng MongoDB đã đăng ký bean tương ứng, một thành phần kiểm tra metadata có thể nhận context qua constructor:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.data.mongodb.core.mapping.MongoMappingContext;

@Component
public class CustomerMetadataInspector {

    private final MongoMappingContext mappingContext;

    public CustomerMetadataInspector(
            MongoMappingContext mappingContext) {
        this.mappingContext = mappingContext;
    }

    public String displayNameStorageField() {
        var entity = mappingContext.getRequiredPersistentEntity(
                CustomerDocument.class);

        var property = entity.getPersistentProperty("displayName");

        if (property == null) {
            throw new IllegalStateException(
                    "Thiếu metadata của displayName");
        }

        return property.getFieldName();
    }
}
~~~

Thành phần này chủ động phụ thuộc metadata MongoDB vì nó hỏi tên field lưu trữ MongoDB. Nếu chỉ in tên kiểu và property, utility Commons ở phần trước là đủ.

Nếu ứng dụng có nhiều context hoặc nhiều cấu hình nguồn dữ liệu, phải chọn đúng bean phù hợp. Không lấy context đầu tiên tìm thấy rồi coi nó là nguồn metadata của toàn bộ hệ thống.

### 11.1. Không dùng context MongoDB thay cho context JPA

Spring Data JPA có cách tích hợp metadata với metamodel của JPA provider. Một context JPA không được khởi tạo hay diễn giải mô hình giống hệt context MongoDB trong ví dụ.

Tương tự, các module relational hoặc document khác có metadata, naming và conversion riêng.

Tái sử dụng một công cụ introspection theo hợp đồng Commons là hợp lý. Tái sử dụng cấu hình store cụ thể mà không kiểm tra ý nghĩa của nó thì không bảo đảm đúng.

## 12. Hiểu đúng ranh giới tập kiểu được quản lý

### 12.1. Không phải toàn bộ classpath

Context không tự có metadata của mọi lớp trong mọi thư viện. Đầu vào, quá trình khám phá và quy tắc tiếp nhận kiểu quyết định những gì xuất hiện.

DTO trả về API, service, repository interface và lớp hạ tầng không mặc nhiên là persistent entity chỉ vì chúng nằm trong cùng dự án.

### 12.2. Không chỉ là danh sách aggregate root

Một context có thể biết kiểu lồng nhau phục vụ mapping. Ngược lại, một kiểu giá trị được converter xử lý như giá trị đơn giản có thể không cần metadata entity riêng.

Do đó, không dùng số lượng `PersistentEntity` để đếm số collection, số bảng hoặc số repository.

### 12.3. Không phải danh sách instance đang có trong bộ nhớ

Một nghìn đối tượng `CustomerDocument` vẫn chỉ sử dụng mô tả kiểu tương ứng. Registry không tạo một `PersistentEntity` metadata mới cho từng khách hàng.

Không lưu thông tin riêng của request vào metadata hoặc dùng metadata làm nơi giữ bản ghi đang xử lý.

### 12.4. Không phải cơ chế kiểm chứng schema thực tế

Annotation `@Field("full_name")` mô tả ý định ánh xạ. Nó không chứng minh mọi tài liệu hiện có đều mang field đó hoặc dữ liệu cũ đã được chuyển đổi.

Tương tự, có metadata JPA không tự bảo đảm schema ở database đã phù hợp với bản triển khai mới.

Khi cần kiểm chứng cấu trúc dữ liệu vật lý hoặc migration, phải dùng công cụ tương ứng. Mapping context cung cấp một phía của hợp đồng ánh xạ, không thay thế việc quản lý dữ liệu và schema.

### 12.5. Không đồng nhất TypeInformation với tên lớp đơn giản

`TypeInformation` giữ thông tin kiểu phục vụ phân tích mô hình, bao gồm những ngữ cảnh kiểu mà chỉ một tên lớp ngắn không thể biểu diễn đầy đủ.

Ngay cả khi chỉ làm báo cáo, nên dùng tên đầy đủ thay vì `getSimpleName()` làm định danh: hai package khác nhau có thể có lớp cùng tên.

Nếu xây công cụ metadata dùng lâu dài, giữ đối tượng thông tin kiểu hoặc định danh rõ ràng thay vì rút gọn quá sớm rồi làm mất thông tin.

## 13. Những tình huống cần nhận diện

| Tình huống | Cách hiểu phù hợp |
| --- | --- |
| Metadata được tạo nhưng database chưa có bản ghi | Bình thường; metadata và dữ liệu là hai lớp khác nhau |
| Context biết thêm Address ngoài kiểu đầu vào CustomerDocument | Có thể do phân tích kiểu lồng theo quy tắc store |
| Không có PersistentEntity cho một kiểu đơn giản | Không phải mọi kiểu đều cần entity metadata |
| Lookup làm danh sách metadata thay đổi | Implementation có thể khởi tạo metadata theo yêu cầu |
| Lookup bắt buộc thất bại | Thiếu metadata hoặc kiểu không được context chấp nhận; không phải kết quả “không tìm thấy khách hàng” |
| Property tên displayName có field full_name | Tên domain và tên lưu trữ được ánh xạ riêng |
| Address không có ID | Có thể là mô hình kiểu nhúng hợp lệ |
| Context tự tạo cho kết quả khác context ứng dụng | Có thể thiếu naming, conversion hoặc tập kiểu đầu vào tương ứng |
| Số metadata entity lớn hơn số repository | Context có thể chứa những kiểu phục vụ mapping không phải repository root |
| Cùng kiểu Java nhưng hai store diễn giải khác nhau | Mỗi module có annotation, metadata và quy tắc mapping riêng |

Các thông tin đầu ra trong bài là minh họa từ mô hình đã khai báo, không phải kết quả chạy trên một cấu hình store của dự án cụ thể.

Khi dùng `MappingContext`, hãy xác định rõ mình đang hỏi về kiểu nào, metadata của store nào và thời điểm nào trong quá trình khởi tạo. Tập kiểu đầu vào định hướng việc xây dựng mô hình; context cung cấp metadata đã biết hoặc có thể tạo theo chính sách của nó; dữ liệu thực tế vẫn được quản lý bởi những thành phần đọc/ghi riêng.
