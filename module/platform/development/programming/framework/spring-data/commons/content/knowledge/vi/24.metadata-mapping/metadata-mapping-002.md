# PersistentEntity và metadata của một kiểu miền

Một framework truy cập dữ liệu cần biết nhiều hơn tên lớp Java: thuộc tính nào được lưu, thuộc tính nào là định danh, thuộc tính nào chứa version và cách tạo hoặc truy cập một đối tượng domain. Spring Data Commons cung cấp `PersistentEntity` để biểu diễn metadata của một kiểu miền trong hệ thống ánh xạ.

`PersistentEntity` mô tả **kiểu dữ liệu**, không phải một bản ghi cụ thể. Hai đối tượng Customer khác ID có thể được xử lý bằng cùng metadata Customer trong một mapping context. Cách tên thuộc tính được chuyển thành tên field, collection hoặc cấu trúc lưu trữ vẫn thuộc module cụ thể.

## 1. Mục tiêu và phạm vi

Sau bài này, bạn có thể:

- Phân biệt domain object, kiểu domain và metadata PersistentEntity.
- Lấy metadata từ MappingContext phù hợp.
- Tra cứu thuộc tính persistent, ID và version.
- Hiểu vai trò của metadata tạo instance, identifier accessor và property accessor.
- Giải thích vì sao metadata Commons không thay thế toàn bộ mô hình ánh xạ của mọi kho.
- Tránh đồng nhất metadata trong bộ nhớ với schema hoặc trạng thái tồn tại trong cơ sở dữ liệu.

Các ví dụ đầu dùng abstraction Commons. Một phần minh họa MongoDB được tách riêng để cho thấy module có thể bổ sung metadata về tên lưu trữ.

Bài không giả định mọi ứng dụng Spring Data đều công bố cùng một bean MappingContext hoặc dùng chung một implementation PersistentEntity. Đặc biệt, không đồng nhất mô hình này với metamodel riêng của một provider JPA.

## 2. Ba đối tượng dễ bị nhầm

| Thành phần | Ví dụ | Mô tả điều gì? |
| --- | --- | --- |
| Kiểu Java | Customer.class | Lớp domain |
| Instance domain | Một Customer có ID C101 | Giá trị của một đối tượng cụ thể |
| Metadata persistent | PersistentEntity của Customer | Quy tắc và cấu trúc ánh xạ cho kiểu đó |

Từ metadata ID, framework biết thuộc tính nào là định danh. Muốn biết giá trị ID của một Customer cụ thể, framework vẫn phải đọc instance đó.

Tương tự:

- Metadata version xác định thuộc tính version.
- Giá trị version nằm trên từng instance.
- Metadata constructor hoặc factory mô tả cách tạo instance.
- Việc tạo một instance còn cần dữ liệu đầu vào và cơ chế instantiation phù hợp.

Tên PersistentEntity không có nghĩa mỗi bản ghi trong kho có một đối tượng metadata riêng.

## 3. MappingContext, PersistentEntity và PersistentProperty

Quan hệ khái niệm:

```text
MappingContext của module
        |
        +--> PersistentEntity<Customer, ...>
                   |
                   +--> metadata thuộc tính id
                   +--> metadata thuộc tính displayName
                   +--> metadata thuộc tính version
                   +--> thông tin tạo và truy cập instance
```

Ba vai trò chính:

| Abstraction | Trách nhiệm |
| --- | --- |
| MappingContext | Quản lý và cung cấp metadata của các kiểu trong một hệ ánh xạ |
| PersistentEntity | Metadata ở cấp kiểu domain |
| PersistentProperty | Metadata ở cấp thuộc tính |

PersistentEntity có dạng generic:

```java
public interface PersistentEntity<
        T,
        P extends PersistentProperty<P>
> extends Iterable<P> {
    // Các phương thức metadata.
}
```

T là kiểu domain. P là loại metadata thuộc tính mà implementation đó sử dụng.

Tham số P cho phép một module bổ sung thông tin riêng. Ví dụ, thuộc tính của kho tài liệu có thể cung cấp tên field được lưu; một module khác có mô hình tên cột hoặc quan hệ riêng.

Đây là dạng khai báo rút gọn để minh họa ràng buộc kiểu; interface thực tế còn cung cấp các phương thức metadata.

## 4. Domain minh họa bằng annotation Commons

Giả sử module đang dùng nhận diện các annotation ID, version và transient của Commons theo cấu hình tương ứng:

```java
package com.example.customer;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.annotation.Version;

public class Customer {

    @Id
    private String id;

    private String displayName;

    @Version
    private Long version;

    @Transient
    private String displayLabel;

    public Customer() {
    }

    public Customer(
            String id,
            String displayName,
            Long version) {
        this.id = id;
        this.displayName = displayName;
        this.version = version;
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

    public Long getVersion() {
        return version;
    }

    public void setVersion(Long version) {
        this.version = version;
    }

    public String getDisplayLabel() {
        return displayLabel;
    }

    public void setDisplayLabel(String displayLabel) {
        this.displayLabel = displayLabel;
    }
}
```

Với quy tắc ánh xạ đã nêu, metadata mong đợi có:

- Kiểu domain là Customer.
- Thuộc tính ID là id.
- Thuộc tính version là version.
- displayName là thuộc tính persistent thông thường.
- displayLabel không thuộc tập thuộc tính được lưu vì được đánh dấu transient.

Đây là cách diễn giải của hệ ánh xạ đang xét. Không thay annotation ID của JPA bằng annotation Commons một cách máy móc: module và provider có quy tắc nhận diện riêng.

## 5. Lấy metadata từ đúng MappingContext

Một thành phần hạ tầng có thể nhận MappingContext từ cấu hình của module:

```java
import org.springframework.data.mapping.PersistentEntity;
import org.springframework.data.mapping.context.MappingContext;

public final class EntityMetadataLookup {

    private final MappingContext<?, ?> mappingContext;

    public EntityMetadataLookup(
            MappingContext<?, ?> mappingContext) {
        this.mappingContext = mappingContext;
    }

    public PersistentEntity<?, ?> requiredEntity(
            Class<?> domainType) {
        return mappingContext.getRequiredPersistentEntity(
            domainType
        );
    }
}
```

MappingContext<?, ?> phù hợp khi chỉ cần các khả năng chung và chưa cần API riêng của metadata thuộc tính.

Lời gọi:

```java
PersistentEntity<?, ?> entity =
    metadataLookup.requiredEntity(Customer.class);
```

Giả định metadataLookup đã được tạo với mapping context đúng. Một ứng dụng có nhiều module hoặc nhiều context cần lựa chọn dependency tường minh; chỉ autowire theo một kiểu chung chưa chắc xác định được context mong muốn.

### 5.1. Biến thể thường và biến thể required

Hai nhóm API có hợp đồng khác nhau:

| API | Ý nghĩa |
| --- | --- |
| getPersistentEntity(...) | Tra cứu metadata, có thể không nhận được entity phù hợp |
| getRequiredPersistentEntity(...) | Yêu cầu phải có metadata; báo lỗi khi không cung cấp được |

Một số context có thể tạo hoặc đăng ký metadata khi tra cứu. Không suy từ việc kiểu chưa xuất hiện trong tập metadata đã biết rằng nó chắc chắn không thể được ánh xạ.

Nếu thiếu metadata là tình huống hợp lệ, xử lý kết quả tra cứu thường theo hợp đồng của API. Nếu thành phần chỉ hoạt động với domain đã ánh xạ, biến thể required giúp thể hiện tiền điều kiện đó.

### 5.2. Không tự dựng metadata rời để thay thế cấu hình thật

Tự tạo một đối tượng metadata cơ sở từ Class chưa bảo đảm đã áp dụng naming strategy, converter, cấu hình loại đơn giản hay quy tắc annotation của module.

Khi phân tích cách ứng dụng thực sự ánh xạ domain, hãy dùng mapping context gắn với hệ ánh xạ đang hoạt động. Metadata thuộc một context khác có thể mô tả cùng lớp Java theo quy tắc khác.

## 6. Đọc thông tin ở cấp entity

Một số API thường dùng:

| API | Thông tin cung cấp |
| --- | --- |
| getType() | Class của domain |
| getName() | Tên entity theo metadata |
| getTypeInformation() | Thông tin kiểu dùng trong hệ thống ánh xạ |
| hasIdProperty() | Có thuộc tính được nhận diện là ID hay không |
| getIdProperty() | Metadata ID hoặc null nếu không có |
| getRequiredIdProperty() | Metadata ID, báo lỗi nếu không có |
| hasVersionProperty() | Có thuộc tính version hay không |
| getVersionProperty() | Metadata version hoặc null nếu không có |
| getPersistentProperty(name) | Metadata một thuộc tính persistent theo tên domain |
| getRequiredPersistentProperty(name) | Yêu cầu thuộc tính đó phải tồn tại |

getName không phải một hợp đồng chung trả về tên bảng hay collection. Tên lưu trữ thường được cung cấp bởi metadata chuyên biệt của module.

### 6.1. Duyệt thuộc tính

PersistentEntity có thể được duyệt như tập metadata thuộc tính:

```java
import org.springframework.data.mapping.PersistentEntity;
import org.springframework.data.mapping.PersistentProperty;

public final class EntityMetadataPrinter {

    private EntityMetadataPrinter() {
    }

    public static void print(PersistentEntity<?, ?> entity) {
        System.out.println(
            "Domain type: " + entity.getType().getName()
        );

        PersistentProperty<?> id =
            entity.getIdProperty();

        PersistentProperty<?> version =
            entity.getVersionProperty();

        System.out.println(
            "ID property: "
                + (id == null ? "(không có)" : id.getName())
        );

        System.out.println(
            "Version property: "
                + (version == null
                    ? "(không có)"
                    : version.getName())
        );

        for (PersistentProperty<?> property : entity) {
            System.out.println(
                property.getName()
                    + " : "
                    + property.getType().getName()
            );
        }
    }
}
```

Với domain minh họa và quy tắc ánh xạ đã nêu, có thể quan sát metadata id, displayName và version. Không dựa vào thứ tự vòng lặp để suy ra thứ tự cột, thứ tự constructor hoặc thứ tự thuộc tính trong JSON.

Thuộc tính transient không thuộc tập thuộc tính persistent trong ví dụ. Những loại đặc biệt như association còn có API metadata riêng; không coi một vòng lặp đơn giản là toàn bộ mô hình quan hệ của mọi module.

### 6.2. Tra cứu theo tên thuộc tính domain

```java
PersistentProperty<?> nameProperty =
    entity.getRequiredPersistentProperty("displayName");

System.out.println(nameProperty.getType());
```

Chuỗi displayName là tên thuộc tính Java trong hệ ánh xạ. Nó không tự đổi thành display_name chỉ vì kho sử dụng naming strategy như vậy.

Tương tự, tên ID không bắt buộc là id. Nếu một thuộc tính khác được module nhận diện là định danh, getIdProperty trả metadata thuộc tính đó.

Không tìm ID bằng cách quét cứng một field có tên id nếu mục tiêu là tuân theo mapping của ứng dụng.

## 7. Từ metadata ID đến giá trị ID của instance

Giả sử đã lấy metadata của Customer:

```java
Customer customer = new Customer(
    "C101",
    "An",
    0L
);

PersistentEntity<?, ?> entity =
    mappingContext.getRequiredPersistentEntity(
        Customer.class
    );

if (!entity.hasIdProperty()) {
    throw new IllegalStateException(
        "Kiểu domain chưa có metadata ID"
    );
}

String idPropertyName =
    entity.getRequiredIdProperty().getName();

Object idValue = entity
    .getIdentifierAccessor(customer)
    .getIdentifier();
```

Trong ví dụ:

```text
idPropertyName = "id"
idValue        = "C101"
```

Hai giá trị có vai trò khác nhau:

- idPropertyName mô tả thuộc tính.
- idValue là giá trị trên đối tượng customer.

Nếu metadata có ID nhưng instance chưa được gán ID, identifier accessor có thể trả null. Có metadata định danh không bảo đảm mọi instance đều đã mang giá trị định danh.

Đối tượng truyền cho accessor phải phù hợp với kiểu metadata. Không lấy metadata của một domain rồi dùng để đọc một DTO hoặc một domain khác chỉ vì chúng cùng có field tên id.

## 8. Metadata version và nhận diện trạng thái mới

### 8.1. Version là thông tin để hạ tầng diễn giải

getVersionProperty cho biết thuộc tính nào được nhận diện là version. Nó không tự thực hiện:

- Đọc version từ kho.
- So sánh version khi cập nhật.
- Tăng version.
- Khóa bản ghi.

Những hành vi này thuộc implementation của module và đường thao tác lưu tương ứng. Đánh dấu một field bằng annotation version không đủ để kết luận mọi loại kho đều có cùng cơ chế optimistic locking.

### 8.2. isNew không phải truy vấn tồn tại

PersistentEntity có thể đánh giá trạng thái mới của một instance:

```java
boolean newState = entity.isNew(customer);
```

Đây là đánh giá theo chiến lược trạng thái của metadata, không phải lệnh kiểm tra có bản ghi tương ứng trong cơ sở dữ liệu hay chưa.

Một chiến lược có thể dựa vào ID, version hoặc hợp đồng trạng thái do domain cung cấp. Trong những implementation sử dụng chiến lược Commons ưu tiên version, một version nullable chưa có giá trị có thể biểu thị đối tượng mới ngay cả khi ID đã được gán.

Vì thế:

```text
ID khác null
    không tự chứng minh bản ghi tồn tại.

isNew trả false
    không tự chứng minh kho đang có bản ghi.

Có metadata version
    không tự chứng minh instance đã được lưu.
```

Repository hoặc module cũng có thể sử dụng abstraction entity information và chiến lược riêng cho quyết định lưu. Cần đối chiếu đường thực thi thực tế thay vì coi một quy tắc ID là hợp đồng chung của mọi repository.

## 9. Metadata tạo instance

Hệ ánh xạ cần biết constructor hoặc factory nào có thể tạo domain object. Các phiên bản API cung cấp metadata creator, chẳng hạn qua getInstanceCreatorMetadata, để mô tả vai trò này.

Cần phân biệt:

| Thành phần | Vai trò |
| --- | --- |
| Metadata creator | Mô tả cách tạo và các tham số liên quan |
| Giá trị đọc từ kho | Cung cấp dữ liệu để điền tham số |
| Cơ chế instantiation | Thực hiện việc gọi constructor hoặc factory |
| Property population | Điền các thuộc tính còn lại nếu mô hình yêu cầu |

Metadata creator không phải một Customer đã được tạo sẵn và không chứa dữ liệu của một bản ghi bất kỳ.

Khi domain có nhiều constructor hoặc dùng factory, cần theo quy tắc của module và phiên bản. Annotation như PersistenceCreator có thể tham gia lựa chọn trong các hệ ánh xạ hỗ trợ nó.

Không áp dụng máy móc quy tắc tạo instance của một module tài liệu cho entity do provider JPA quản lý. Đây là những cơ chế cần được phân biệt dù cùng nằm trong ứng dụng Spring.

## 10. Property accessor: dùng metadata để đọc hoặc ghi thuộc tính

Ngoài việc mô tả thuộc tính, PersistentEntity có thể cung cấp PersistentPropertyAccessor cho một instance.

Ví dụ tiện ích generic:

```java
import org.springframework.data.mapping.PersistentEntity;
import org.springframework.data.mapping.PersistentProperty;
import org.springframework.data.mapping.PersistentPropertyAccessor;

public final class MetadataPropertyAccess {

    private MetadataPropertyAccess() {
    }

    public static <
            T,
            P extends PersistentProperty<P>
    > T setDisplayName(
            PersistentEntity<T, P> entity,
            T bean,
            String value) {

        P property = entity.getRequiredPersistentProperty(
            "displayName"
        );

        PersistentPropertyAccessor<T> accessor =
            entity.getPropertyAccessor(bean);

        accessor.setProperty(property, value);

        return accessor.getBean();
    }
}
```

Ví dụ chỉ phù hợp với domain có thuộc tính displayName ghi được theo cơ chế accessor của implementation.

Có ba điểm quan trọng:

1. Metadata thuộc tính phải thuộc cùng entity với accessor.
2. Giá trị mới phải phù hợp với kiểu và cách ghi thuộc tính.
3. Ghi qua accessor không đồng nghĩa đã gọi repository.save hoặc cập nhật kho dữ liệu.

Trả về accessor.getBean giúp thành phần gọi nhận instance hiện tại mà accessor quản lý. Với một số mô hình bất biến và cơ chế copy/with hỗ trợ, việc cập nhật có thể tạo một instance thay thế; không nên luôn giả định bean ban đầu bị sửa tại chỗ.

Nếu một domain bất biến không có cơ chế ghi hoặc tái tạo phù hợp, không thể suy từ việc có metadata rằng mọi field đều sửa được. Accessor cũng không phải một đối tượng dùng chung để giữ trạng thái của nhiều instance qua nhiều request.

## 11. Ví dụ metadata chuyên biệt của MongoDB

Phần này chỉ minh họa module MongoDB, không phải API bắt buộc của Commons.

Domain:

```java
package com.example.customer;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "customer_profiles")
public class CustomerDocument {

    @Id
    private String customerCode;

    @Field("display_name")
    private String displayName;
}
```

Trong ví dụ metadata này, các field được hệ ánh xạ MongoDB nhận diện; không cần thêm getter chỉ để đọc metadata của chúng.

Đọc metadata từ MongoMappingContext mà ứng dụng đang sử dụng:

```java
import org.springframework.data.mongodb.core.mapping.MongoMappingContext;
import org.springframework.data.mongodb.core.mapping.MongoPersistentEntity;
import org.springframework.data.mongodb.core.mapping.MongoPersistentProperty;

public final class MongoMetadataPrinter {

    private MongoMetadataPrinter() {
    }

    public static void print(
            MongoMappingContext mappingContext) {

        MongoPersistentEntity<?> entity =
            mappingContext.getRequiredPersistentEntity(
                CustomerDocument.class
            );

        MongoPersistentProperty name =
            entity.getRequiredPersistentProperty(
                "displayName"
            );

        MongoPersistentProperty id =
            entity.getRequiredIdProperty();

        System.out.println(entity.getCollection());
        System.out.println(name.getName());
        System.out.println(name.getFieldName());
        System.out.println(id.getName());
        System.out.println(id.getFieldName());
    }
}
```

Với cấu hình minh họa, các giá trị tương ứng là:

```text
customer_profiles
displayName
display_name
customerCode
_id
```

Điều cần rút ra:

| Khái niệm | Giá trị trong ví dụ |
| --- | --- |
| Tên collection | customer_profiles |
| Tên thuộc tính Java | displayName |
| Tên field lưu trữ của thuộc tính đó | display_name |
| Tên thuộc tính ID trong Java | customerCode |
| Tên field ID trong MongoDB | _id |

Commons giúp tra cứu thuộc tính và vai trò ID. Metadata MongoDB bổ sung cách tên đó được biểu diễn trong kho.

Không ép kiểu metadata của module khác thành MongoPersistentEntity chỉ vì cùng mô tả một lớp Java. Muốn dùng API chuyên biệt, thành phần gọi phải biết mình đang làm việc với context và implementation phù hợp.

## 12. Metadata ánh xạ khác reflection thuần như thế nào?

Reflection trả lời các câu hỏi về cấu trúc Java. Metadata ánh xạ bổ sung cách hệ persistence diễn giải cấu trúc đó.

| Câu hỏi | Reflection thuần | Metadata ánh xạ |
| --- | --- | --- |
| Lớp có field nào? | Có thể liệt kê field theo API reflection | Liệt kê các thuộc tính được mapping nhận diện |
| Thuộc tính nào là ID? | Cần tự viết quy tắc đọc annotation/convention | Dùng metadata ID đã được hệ ánh xạ xác định |
| Field nào không được lưu? | Phải tự áp dụng quy tắc | Theo quyết định transient và quy tắc của module |
| Tên field trong kho là gì? | Không tự biết naming strategy | Có thể lấy qua metadata chuyên biệt của module |
| Tạo và điền instance thế nào? | Cần tự xử lý constructor, field và method | Có mô hình creator và accessor phục vụ hạ tầng |

Không đồng nhất một persistent property với một field được lấy bằng getDeclaredFields. Hệ ánh xạ có thể xét accessor, kế thừa, annotation và các quy tắc khác.

Reflection vẫn là một công cụ mà implementation có thể sử dụng bên trong. Giá trị của metadata là tập trung hóa quyết định mapping thay vì để mỗi thành phần tự suy luận lại.

## 13. Metadata không phải schema và không phải dữ liệu trong kho

Có thể tạo hoặc tra cứu metadata của một domain trước khi có bất kỳ bản ghi nào.

Từ metadata, không thể tự kết luận:

- Bảng hoặc collection đã tồn tại.
- Schema thực tế đã khớp với cấu hình.
- Index đã được tạo.
- Một ID cụ thể đã tồn tại.
- Domain đang có bao nhiêu bản ghi.
- Một thay đổi đối tượng đã được lưu thành công.

Các thông tin đó cần cơ chế của kho, migration, quản lý schema hoặc truy vấn thực tế phù hợp.

Tương tự, thuộc tính được nhận diện là persistent không đồng nghĩa nó được phép hiển thị hay sửa qua mọi API. Nếu dùng metadata để xây form, bộ lọc hoặc công cụ quản trị, cần áp dụng hợp đồng thuộc tính mà ứng dụng chủ động công khai.

## 14. Chọn đúng context và quản lý metadata

### 14.1. Cùng kiểu Java, khác hệ ánh xạ

Một kiểu Java có thể được quan sát trong các context khác nhau. Naming strategy, quy tắc loại đơn giản, converter và annotation của module có thể làm metadata khác nhau.

Vì vậy, cache metadata chỉ theo Class ở một thành phần toàn cục có thể không đủ nếu ứng dụng dùng nhiều context. Nguồn context và cấu hình ánh xạ cũng là một phần ý nghĩa của metadata.

Dùng metadata từ đúng context còn quan trọng hơn việc có một đối tượng PersistentEntity không null.

### 14.2. Tái sử dụng context thay vì dựng lại cho từng request

Mapping context thường quản lý và tái sử dụng metadata. Không cần tạo một hệ ánh xạ mới cho mỗi thao tác đọc tên ID.

Tuy nhiên, metadata dùng chung không phải nơi giữ bean domain hiện tại, kết quả truy vấn hoặc tham số request. Accessor gắn với một instance cũng cần vòng đời phù hợp với thao tác đang thực hiện.

Không ép kiểu sang implementation nội bộ rồi sửa cấu trúc metadata đã được khởi tạo chỉ để phục vụ một request. Quy tắc mapping nên được cấu hình theo vòng đời của hạ tầng.

### 14.3. Dùng domain type thực tế của repository

Kiểu runtime của một đối tượng có thể là proxy hoặc lớp phát sinh. Khi đã biết domain type từ repository hay cấu hình, ưu tiên dùng thông tin đó để lấy metadata phù hợp.

Không mặc định bean.getClass luôn là kiểu domain mà mapping context cần. Việc nhận diện user class hoặc xử lý proxy phải theo khả năng của hạ tầng đang dùng.

### 14.4. Phân biệt thuộc tính trực tiếp và property path

getPersistentProperty với một tên thuộc tính trực tiếp không phải bộ phân giải mọi chuỗi đường dẫn lồng nhau.

Nếu cần xử lý một đường dẫn như address.city, hãy dùng API property path phù hợp của hệ ánh xạ. Không suy rằng thêm dấu chấm vào tên luôn được tra cứu như một thuộc tính trực tiếp.

## 15. Chẩn đoán những nhầm lẫn thường gặp

| Hiện tượng | Điều cần kiểm tra |
| --- | --- |
| Không lấy được metadata domain | Đúng context chưa, kiểu có được context hỗ trợ không |
| Không có ID metadata dù Java có field id | Quy tắc nhận diện ID và annotation của module |
| Metadata có ID nhưng đọc giá trị nhận null | Giá trị ID trên instance đã được gán chưa |
| Tra cứu display_name không thấy thuộc tính | Đang dùng tên lưu trữ thay vì tên domain hay không |
| Một field không xuất hiện trong tập persistent properties | Transient, loại thuộc tính và quy tắc mapping |
| isNew không khớp suy luận chỉ dựa trên ID | Chiến lược version, ID hoặc trạng thái domain |
| Ép kiểu metadata thất bại | Có đang dùng implementation của một module khác không |
| Sửa qua accessor nhưng kho không đổi | Accessor không phải thao tác save |
| Đối tượng ban đầu không đổi sau cập nhật accessor | Cơ chế bất biến có thể trả instance thay thế; đọc getBean |
| Lỗi khi dùng metadata với một bean | Kiểu bean có phù hợp domain metadata và proxy không |

Với mỗi tình huống, tách ba câu hỏi:

1. Đang dùng metadata của kiểu nào và context nào?
2. Metadata đó nhận diện thuộc tính ra sao?
3. Instance hiện tại chứa giá trị gì và có thao tác lưu nào thực sự được thực hiện?

Ba câu hỏi này giúp tránh sửa sai tầng, chẳng hạn thay annotation khi thực tế chỉ chưa gán ID, hoặc gọi reflection thủ công khi vấn đề là chọn nhầm mapping context.

## 16. Bài tập tự kiểm tra

1. Một nghìn Customer có cần một nghìn PersistentEntity riêng trong cùng context không?
2. getIdProperty trả giá trị C101 hay metadata của thuộc tính ID?
3. Vì sao getName của PersistentEntity không nên được dùng như tên bảng một cách tổng quát?
4. Có metadata version có nghĩa version đã được đọc từ cơ sở dữ liệu chưa?
5. isNew trả false có chứng minh bản ghi đang tồn tại không?
6. Trong ví dụ MongoDB, vì sao tra cứu thuộc tính bằng displayName nhưng tên lưu trữ là display_name?
7. Sau khi gọi accessor.setProperty, có thể kết luận kho đã được cập nhật không?
8. Vì sao cùng Class nhưng khác MappingContext có thể không dùng chung metadata một cách tùy ý?

Gợi ý đáp án:

1. Không. Metadata mô tả kiểu, không phải từng bản ghi.
2. Metadata thuộc tính. Muốn lấy C101 cần đọc instance.
3. Tên lưu trữ thuộc quy tắc và API chuyên biệt của module.
4. Không. Metadata và giá trị là hai lớp thông tin khác nhau.
5. Không. Đó là đánh giá trạng thái theo chiến lược, không phải truy vấn tồn tại.
6. Một tên là thuộc tính domain, tên còn lại do annotation mapping của module quyết định.
7. Không. Cần thao tác persistence phù hợp để ghi dữ liệu.
8. Vì cấu hình naming, converter, quy tắc thuộc tính và module có thể khác nhau.

Nguyên tắc áp dụng là dùng PersistentEntity để hiểu cấu trúc persistent của một domain trong đúng hệ ánh xạ, rồi dùng accessor hoặc cơ chế module để làm việc với instance. Luôn giữ riêng metadata, giá trị đối tượng và trạng thái thực tế của kho dữ liệu.
