# PersistentEntity, IsNewStrategy và triển khai đặc thù store

Trong chương **Phát hiện trạng thái** của **SPRING_DATA_COMMONS**, bài này giải thích các thành phần hạ tầng phối hợp để trả lời câu hỏi: một đối tượng có được xem là mới hay không?

Trọng tâm không chỉ là kiểm tra ID null. Ta cần biết metadata đến từ đâu, chiến lược nào được chọn, thành phần repository nào sử dụng kết quả và module lưu trữ chuyển quyết định đó thành thao tác gì. Hiểu đường đi này giúp chẩn đoán các trường hợp ID đã được gán nhưng đối tượng vẫn mới, version làm thay đổi kết quả hoặc một tùy biến không có hiệu lực.

## 1. Ba lớp trách nhiệm cần phân biệt

| Lớp trách nhiệm | Thành phần tiêu biểu | Câu hỏi được trả lời |
| --- | --- | --- |
| Mô tả mô hình persistence | MappingContext, PersistentEntity, PersistentProperty | Kiểu miền có những thuộc tính nào, ID và version ở đâu? |
| Quyết định trạng thái | IsNewStrategy, Persistable hoặc logic của EntityInformation | Với instance hiện tại, nên phân loại mới hay không mới? |
| Thực hiện lưu | Repository, template, JPA provider hoặc driver | Dùng kết quả đó để thực hiện thao tác lưu nào? |

`PersistentEntity` là metadata của một kiểu miền, không phải bản ghi đang nằm trong cơ sở dữ liệu. Một metadata có thể được dùng để đánh giá nhiều instance của cùng kiểu.

`IsNewStrategy` là hợp đồng cho một phép đánh giá. Kết quả của nó không phải bằng chứng rằng hệ thống vừa truy vấn kho và xác nhận bản ghi chưa tồn tại.

`EntityInformation` là abstraction phục vụ repository. Tùy module, nó có thể dựa trên `PersistentEntity` hoặc một nguồn metadata khác, chẳng hạn JPA metamodel.

Không mặc định mọi repository đi qua cùng một chuỗi class nội bộ chỉ vì cùng kế thừa `CrudRepository`.

## 2. PersistentEntity cung cấp những thông tin gì?

Các API hữu ích cho việc đọc trạng thái gồm:

| API | Mục đích |
| --- | --- |
| `getType()` | Kiểu miền mà metadata mô tả |
| `hasIdProperty()`, `getIdProperty()` | Xác định thuộc tính định danh |
| `hasVersionProperty()`, `getVersionProperty()` | Xác định thuộc tính version |
| `getIdentifierAccessor(bean)` | Đọc định danh của instance |
| `getPropertyAccessor(bean)` | Truy cập giá trị thuộc tính theo mô hình mapping |
| `isNew(bean)` | Đánh giá trạng thái mới theo metadata và implementation tương ứng |

Các hợp đồng này được mô tả tại [PersistentEntity API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/mapping/PersistentEntity.html).

Metadata và dữ liệu instance phải phù hợp với nhau. Không lấy metadata của `Customer` để đánh giá một `Order`, dù cả hai đều có field tên `id`.

Cũng không nên tự viết reflection chỉ tìm field tên `id`. Metadata của module có thể nhận diện định danh qua annotation, getter, quy ước riêng hoặc một dạng ánh xạ đặc thù.

Một component generic nên nhận kiểu miền rõ ràng hoặc sử dụng context đã xác định đúng kiểu miền. Chỉ gọi `candidate.getClass()` có thể không phù hợp khi đối tượng là proxy hoặc một kiểu con được tạo lúc chạy.

## 3. IsNewStrategy là hợp đồng đánh giá, không phải cơ chế đăng ký toàn cục

API cốt lõi có dạng:

~~~java
package org.springframework.data.support;

public interface IsNewStrategy {

    boolean isNew(Object entity);
}
~~~

Đối tượng đầu vào phải khác null. Hợp đồng này được mô tả tại [IsNewStrategy API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/support/IsNewStrategy.html).

Interface không tự quy định:

- Cách chọn một strategy từ application context.
- Thứ tự ưu tiên giữa mọi bean cùng kiểu.
- Cách sinh ID.
- Cách thực hiện insert, update hoặc upsert.
- Cách kiểm tra bản ghi có tồn tại.

Vì vậy, một bean có kiểu `IsNewStrategy` chỉ là một bean cho đến khi thành phần có trách nhiệm thực sự sử dụng nó.

Ví dụ ý tưởng cấu hình:

~~~java
// Chỉ khai báo một bean không chứng minh repository sẽ dùng nó:
//
// @Bean
// IsNewStrategy customRule() {
//     return entity -> true;
// }
~~~

Ngoài việc thiếu điểm tích hợp, quy tắc luôn trả true còn có thể làm đối tượng đã lưu tiếp tục bị xử lý như mới. Một tùy biến phải giải quyết cả việc gắn vào đường thực thi và vòng đời giá trị trạng thái.

Strategy nên đánh giá dựa trên đầu vào và cấu hình đã xác định. Không lưu kết quả của instance trước vào một field rồi dùng lại cho instance sau.

## 4. Đường lựa chọn trong BasicPersistentEntity

`BasicPersistentEntity` là một implementation nền tảng cho metadata. Nó cung cấp điểm mở rộng protected `getFallbackIsNewStrategy()`. Xem [BasicPersistentEntity API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/mapping/model/BasicPersistentEntity.html).

Đối chiếu mã nguồn Commons **4.1.0**, đường lựa chọn có thể diễn giải:

~~~text
PersistentEntity.isNew(candidate)
  → kiểm tra candidate phù hợp
  → lấy strategy của metadata
      → nếu kiểu miền triển khai Persistable:
            delegate tới Persistable.isNew()
      → nếu không:
            dùng fallback strategy
  → đánh giá candidate hiện tại
~~~

Implementation chọn strategy theo kiểu miền và giữ strategy đó để tái sử dụng; nó không giữ một boolean chung đại diện cho mọi instance. Có thể xem tại [mã nguồn BasicPersistentEntity 4.1.0](https://raw.githubusercontent.com/spring-projects/spring-data-commons/4.1.0/src/main/java/org/springframework/data/mapping/model/BasicPersistentEntity.java).

Điều này giải thích hai tình huống:

- Hai instance cùng kiểu có thể dùng chung một strategy nhưng nhận kết quả khác nhau.
- Override fallback không có nghĩa sẽ thay thế nhánh đã giao cho `Persistable`.

Ví dụ, cùng kiểu `Delivery`, instance A có version null còn instance B có version đã được gán. Việc metadata được tái sử dụng không làm B kế thừa kết quả mới của A.

Không thay đổi cấu trúc metadata đang được nhiều lời gọi sử dụng chỉ để tác động tới một lần lưu. Metadata nên được xây dựng qua cơ chế cấu hình của module trước khi phục vụ các thao tác bình thường.

## 5. Fallback dựa trên thuộc tính: chọn version hoặc ID

Trong implementation mặc định của Commons được đối chiếu ở trên, fallback ưu tiên thuộc tính version nếu có; nếu không có version thì dùng định danh.

Cần hiểu đúng chữ “fallback”:

~~~text
Có thuộc tính version?
  Có   → dùng version làm nguồn giá trị đánh giá
  Không → dùng ID làm nguồn giá trị đánh giá
~~~

Đây không phải quy tắc “version null thì thử thêm ID để xem có nên đổi kết quả hay không”. Khi version đã là nguồn được chọn, giá trị của nó quyết định trạng thái theo quy tắc của strategy đó.

Ví dụ cho nhánh metadata mặc định, không triển khai `Persistable`:

| Metadata và dữ liệu | Kết quả dự kiến |
| --- | --- |
| Không version, ID Long null | Mới |
| Không version, ID Long 0L | Không mới |
| Không version, ID primitive long 0 | Mới |
| Có version Long null, ID đã được gán | Mới |
| Có version Long 0L, ID đã được gán | Không mới |
| Có version primitive long 0, ID đã được gán | Mới |
| Có version Long 3L, ID null | Không mới theo version; chưa chứng minh dữ liệu hợp lệ |

Dòng cuối là một tình huống chẩn đoán có chủ đích. Một instance có ID null và version khác null có thể không hợp lệ để lưu, nhưng kết quả state detection không phải validation toàn bộ entity.

`PersistentEntityIsNewStrategy` là tên implementation nội bộ liên quan đến nhánh này trong mã Commons 4.1.0. Class có phạm vi package, vì vậy không viết mã ứng dụng import trực tiếp nó hoặc coi các factory nội bộ là API public. Xem [mã nguồn PersistentEntityIsNewStrategy 4.1.0](https://raw.githubusercontent.com/spring-projects/spring-data-commons/4.1.0/src/main/java/org/springframework/data/mapping/model/PersistentEntityIsNewStrategy.java).

Phần giải thích nội bộ được gắn phiên bản để không nhầm chi tiết class với hợp đồng mở rộng ổn định của mọi phiên bản Spring Data.

## 6. Nhánh Persistable: metadata giao quyết định cho đối tượng

Nếu kiểu miền triển khai `Persistable<ID>`, trạng thái có thể được lấy từ `isNew()` của chính đối tượng.

`PersistableIsNewStrategy` thực hiện việc delegate này. API cung cấp instance dùng chung `PersistableIsNewStrategy.INSTANCE`. Xem [PersistableIsNewStrategy API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/support/PersistableIsNewStrategy.html).

Ví dụ ở mức hợp đồng:

~~~java
import org.springframework.data.domain.Persistable;
import org.springframework.data.support.PersistableIsNewStrategy;

boolean inspectPersistable(Persistable<?> candidate) {
    return PersistableIsNewStrategy.INSTANCE.isNew(candidate);
}
~~~

Đoạn này không truy cập version để phủ quyết kết quả `candidate.isNew()`. Vì vậy, một đối tượng có ID khác null vẫn có thể trả true nếu nó chủ động quản lý trạng thái mới.

Trách nhiệm chuyển trạng thái phải được thiết kế đầy đủ:

| Mốc vòng đời | Điều cần xác định |
| --- | --- |
| Tạo đối tượng mới với ID gán trước | Vì sao isNew trả true? |
| Lưu thành công | Đối tượng dùng tiếp có còn bị xem là mới không? |
| Đọc lại từ kho | Trạng thái được phục hồi như thế nào? |
| Lưu thất bại hoặc transaction rollback | Có làm đối tượng trong bộ nhớ mang trạng thái sai không? |
| Sao chép đối tượng immutable | Bản sao giữ hay thay đổi trạng thái mới theo mục đích nào? |

Không mặc định annotation callback của JPA hoạt động với MongoDB hoặc JDBC. Đường chuyển trạng thái phải phù hợp module đang thực hiện lưu.

Không dùng `isNew()` để gửi thông báo, tăng số lần lưu hoặc thay đổi trạng thái mỗi lần được hỏi. Hạ tầng có thể đánh giá nhiều lần; một phép kiểm tra nên có kết quả nhất quán khi dữ liệu chưa thay đổi.

## 7. EntityInformation là cầu nối ở một số đường repository

`PersistentEntityInformation<T, ID>` sử dụng `PersistentEntity` để cung cấp thông tin cho repository. Trong mã Commons 4.1.0, phương thức `isNew(entity)` chuyển tiếp tới `persistentEntity.isNew(entity)`. Xem [mã nguồn PersistentEntityInformation](https://raw.githubusercontent.com/spring-projects/spring-data-commons/4.1.0/src/main/java/org/springframework/data/repository/core/support/PersistentEntityInformation.java).

Một đường có thể hình dung:

~~~text
Repository
  → EntityInformation.isNew(instance)
  → PersistentEntity.isNew(instance)
  → strategy của metadata
~~~

Đường này có thật trong các adapter dùng metadata chung, nhưng không phải bắt buộc đối với mọi repository implementation.

Ví dụ MongoDB có `MappingMongoEntityInformation` kế thừa `PersistentEntityInformation`, đồng thời bổ sung thông tin collection và version. Xem [MappingMongoEntityInformation API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/repository/support/MappingMongoEntityInformation.html).

Sự phân chia có ích khi debug:

- Kết quả sai ngay tại metadata: xem thuộc tính và strategy.
- Metadata cho kết quả đúng nhưng đường repository khác: xem adapter thực tế.
- Adapter cho kết quả đúng nhưng thao tác ghi thất bại: xem converter, transaction, version và ràng buộc của kho.

Không sửa policy ở tầng trên chỉ để che một ID hoặc version bị mapper truyền sai.

## 8. Ví dụ đọc metadata thực tế với MongoDB

Ví dụ sau dùng API public và Java record để trả kết quả chẩn đoán. Cần JDK hỗ trợ records và ứng dụng đã cấu hình Spring Data MongoDB.

### 8.1. Kiểu miền có ID được gán trước và version nullable

~~~java
package com.acme.shipping;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("deliveries")
public final class Delivery {

    @Id
    private final String id;

    @Version
    private final Long version;

    private final String destination;

    public Delivery(
            String id,
            Long version,
            String destination) {
        this.id = id;
        this.version = version;
        this.destination = destination;
    }

    public String getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getDestination() {
        return destination;
    }
}
~~~

Class không triển khai `Persistable`. Vì vậy ví dụ có thể quan sát ảnh hưởng của version qua metadata mặc định.

Constructor cần metadata tên tham số phù hợp để phục hồi đối tượng, chẳng hạn được biên dịch với `-parameters`. Annotation và kiểu thuộc tính phải đúng với mô hình thực sự được converter sử dụng.

### 8.2. Bộ đọc chẩn đoán dùng abstraction Commons

~~~java
package com.acme.shipping;

import java.util.Objects;

import org.springframework.data.mapping.PersistentEntity;
import org.springframework.data.mapping.PersistentProperty;

public final class StateProbe {

    private StateProbe() {
    }

    public static StateView inspect(
            PersistentEntity<?, ?> metadata,
            Object candidate) {

        Objects.requireNonNull(metadata, "metadata");
        Objects.requireNonNull(candidate, "candidate");

        if (!metadata.getType().isInstance(candidate)) {
            throw new IllegalArgumentException(
                    "Candidate does not match metadata type"
            );
        }

        PersistentProperty<?> idProperty =
                metadata.getRequiredIdProperty();

        PersistentProperty<?> versionProperty =
                metadata.getVersionProperty();

        Object idValue =
                metadata.getIdentifierAccessor(candidate).getIdentifier();

        Object versionValue = versionProperty == null
                ? null
                : metadata.getPropertyAccessor(candidate)
                        .getProperty(versionProperty);

        return new StateView(
                metadata.getType().getName(),
                metadata.getClass().getName(),
                idProperty.getName(),
                idProperty.getType().getName(),
                idValue,
                versionProperty == null ? null : versionProperty.getName(),
                versionProperty == null
                        ? null
                        : versionProperty.getType().getName(),
                versionValue,
                metadata.isNew(candidate)
        );
    }

    public record StateView(
            String domainType,
            String metadataImplementation,
            String idProperty,
            String idType,
            Object idValue,
            String versionProperty,
            String versionType,
            Object versionValue,
            boolean newEntity) {
    }
}
~~~

Probe cố ý gọi `getRequiredIdProperty()`: nó phục vụ aggregate có định danh được metadata nhận diện. Không diễn giải lỗi thiếu ID như một kết quả mặc định “entity mới”.

Bộ đọc trả cả tên thuộc tính và kiểu khai báo. Điều này giúp phân biệt `Long` với `long`, cũng như phát hiện việc ứng dụng đang kiểm tra nhầm metadata.

`newEntity` lấy từ `metadata.isNew(candidate)`; probe không tự viết lại công thức `id == null` rồi bỏ qua version hoặc `Persistable`.

### 8.3. Lấy metadata từ mapping context đang được cấu hình

~~~java
package com.acme.shipping;

import org.springframework.data.mongodb.core.mapping.MongoMappingContext;
import org.springframework.stereotype.Service;

@Service
public class MongoStateInspector {

    private final MongoMappingContext mappingContext;

    public MongoStateInspector(MongoMappingContext mappingContext) {
        this.mappingContext = mappingContext;
    }

    public StateProbe.StateView inspect(Delivery candidate) {
        return StateProbe.inspect(
                mappingContext.getRequiredPersistentEntity(Delivery.class),
                candidate
        );
    }
}
~~~

`MongoMappingContext` là mapping context của MongoDB, mặc định xây dựng metadata bằng các abstraction Mongo-specific. Xem [MongoMappingContext API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/mapping/MongoMappingContext.html).

Trong ứng dụng có nhiều cấu hình MongoDB, cần chọn đúng context mà converter và repository mục tiêu sử dụng. Nếu có nhiều bean cùng kiểu, cấu hình qualifier thích hợp.

Không tạo một `new MongoMappingContext()` riêng trong service rồi mặc định nó có đầy đủ custom conversions, quy tắc đặt tên và cấu hình giống đường lưu thật.

### 8.4. Những trường hợp quan sát được

~~~java
Delivery first = new Delivery("D-101", null, "Hà Nội");
Delivery stored = new Delivery("D-101", 2L, "Hà Nội");

StateProbe.StateView firstView = inspector.inspect(first);
StateProbe.StateView storedView = inspector.inspect(stored);
~~~

Với metadata mặc định của ví dụ:

| Đối tượng | ID | Version Long | newEntity dự kiến |
| --- | --- | --- | --- |
| first | D-101 | null | true |
| stored | D-101 | 2 | false |
| Một instance khác | D-101 | 0 | false |

Đây là các kỳ vọng từ hợp đồng và thiết kế, không phải kết quả chạy thử kèm bài.

Probe chỉ đọc metadata và trạng thái trong bộ nhớ. Nó chưa xác nhận document có tồn tại, chưa thực hiện insert và chưa chứng minh một lần save sẽ thành công.

## 9. Store bổ sung metadata và diễn giải kết quả theo cách riêng

### 9.1. MongoDB

`BasicMongoPersistentEntity` mở rộng `BasicPersistentEntity` và bổ sung metadata MongoDB như collection. Xem [BasicMongoPersistentEntity API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/mapping/BasicMongoPersistentEntity.html).

Khi repository dùng `MappingMongoEntityInformation`, thông tin trạng thái được nối với metadata qua adapter đã trình bày.

Sau quyết định trạng thái, thao tác MongoDB vẫn phải tuân theo ngữ nghĩa của API lưu, ID mapping, version và optimistic locking. Không suy rằng mọi kết quả không mới đều tương đương một lệnh update chắc chắn tác động một document đang tồn tại.

### 9.2. Spring Data JDBC

JDBC sử dụng metadata relational của aggregate để quyết định đường lưu. Aggregate mới đi theo đường insert; aggregate không mới đi theo đường cập nhật theo mô hình persistence của JDBC. Xem [Persisting Entities của Spring Data JDBC](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html).

Không cần ép đường JDBC phải đi qua `MappingMongoEntityInformation` hoặc một adapter giống MongoDB mới được coi là dùng abstraction Commons.

Các thao tác tường minh như insert và update của template có thể thể hiện ý định khác với save tự phân loại. Nếu đang debug đường insert tường minh, đừng mặc định thay đổi strategy sẽ đổi ý định của thao tác ấy.

### 9.3. Spring Data JPA

JPA có `JpaMetamodelEntityInformation` dựa trên JPA metamodel. Đây là một triển khai `EntityInformation` riêng, không phải yêu cầu mọi quyết định của JPA phải được thực hiện qua một `BasicPersistentEntity` do ứng dụng tự dựng. Xem [JpaMetamodelEntityInformation API](https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/support/JpaMetamodelEntityInformation.html).

Một khác biệt quan trọng là version primitive: JPA không dùng nó để phát hiện mới theo cùng cách version primitive bằng không ở nhánh Commons nêu trên, vì số không có thể là version đầu tiên sau insert.

Spring Data JPA mô tả chiến lược version/ID, `Persistable` và lựa chọn `persist` hoặc `merge` tại [Persisting Entities](https://docs.spring.io/spring-data/jpa/reference/jpa/entity-persistence.html).

Do đó, không dùng kết quả probe lấy từ MongoMappingContext để chứng minh repository JPA sẽ ra cùng quyết định.

## 10. Mở rộng strategy: phải chọn đúng điểm tích hợp

Trước khi viết hạ tầng tùy biến, cần xác định nhu cầu thật sự:

| Nhu cầu | Hướng cần đánh giá |
| --- | --- |
| ID được gán trước nhưng cần biết vòng đời mới | Persistable với cơ chế chuyển trạng thái phù hợp |
| Cần optimistic locking | Version cùng quy tắc vòng đời của module |
| Một use case luôn là insert | API insert tường minh nếu module hỗ trợ |
| Cần chính sách trạng thái cho một nhóm kiểu đặc biệt | Extension point của metadata hoặc repository factory |
| Chỉ cần hiểu vì sao kết quả hiện tại sai | Đọc metadata và đầu vào bằng probe |

Nếu mở rộng tuyến metadata kế thừa `BasicPersistentEntity`, điểm fallback là một phần cần xem xét. Tuy nhiên, một triển khai đầy đủ còn phải làm rõ:

1. Metadata tùy biến kế thừa đúng loại metadata của store để giữ collection, bảng và các thông tin đặc thù.
2. Mapping context thật tạo ra loại metadata tùy biến ấy.
3. Converter, template và repository thực sự dùng context được cấu hình.
4. Strategy giữ đúng ưu tiên của Persistable hoặc chủ động ghi rõ thay đổi mong muốn.
5. Chính sách được kiểm chứng cho cả tạo mới, đọc lại, cập nhật và rollback.

Đó là chuỗi tích hợp, không chỉ là một annotation `@Component`.

Với một store context có factory tạo metadata như `createPersistentEntity(...)`, cần đối chiếu chữ ký và cơ chế cấu hình của phiên bản đang sử dụng. Không sao chép một subclass từ module khác rồi bỏ qua kiểu persistent property và các cấu hình converter.

Với JPA, tài liệu mô tả hướng tùy biến `EntityInformation` thông qua repository factory. Override fallback của một metadata Commons độc lập không tự thay thế đường này.

## 11. Các lỗi dễ tạo khi tùy biến

### 11.1. Delegate vòng trở lại chính metadata

Nếu fallback strategy của metadata lại gọi:

~~~java
// Minh họa thiết kế có thể gây đệ quy nếu được cài làm
// fallback của chính metadata đó:
//
// candidate -> metadata.isNew(candidate)
~~~

thì đường gọi có thể trở thành:

~~~text
metadata.isNew
  → fallback
  → metadata.isNew
  → fallback
  → ...
~~~

Strategy fallback phải thực hiện quy tắc cần thiết hoặc delegate tới một strategy độc lập hợp lệ. Không gọi ngược vào chính điểm phân phối đã chọn nó.

### 11.2. Cache kết quả thay vì cache cách đánh giá

Một field dùng chung như `lastWasNew` không thể đại diện cho các instance khác nhau được xử lý đồng thời.

Metadata có thể tái sử dụng thông tin về thuộc tính nào cần đọc. Giá trị của thuộc tính vẫn phải được đọc từ candidate hiện tại.

### 11.3. Tự truy vấn tồn tại trong mỗi lần isNew

Một strategy có thể được viết để gọi `existsById`, nhưng điều đó thêm I/O vào phép đánh giá trạng thái và không loại bỏ cạnh tranh giữa thời điểm kiểm tra với thời điểm ghi.

Nếu hai luồng cùng thấy ID chưa tồn tại, cả hai vẫn có thể chọn insert. Ràng buộc khóa và chính sách xử lý lỗi vẫn cần thiết.

Một câu hỏi nghiệp vụ “cho phép tạo không?” có thể cần truy vấn, nhưng không vì vậy mà mọi phép đánh giá metadata nên âm thầm thực hiện truy vấn đó.

### 11.4. Gán nghĩa mới cho mọi kho bằng một boolean

`isNew = false` không bảo đảm bản ghi tồn tại và không có nghĩa chung “thực hiện đúng một câu UPDATE”.

Tương tự, `isNew = true` không bỏ qua khóa trùng, converter, validation hoặc transaction.

Nếu cần upsert, phải chọn API và khả năng hỗ trợ tương ứng, thay vì đổi strategy rồi coi upsert đã được cài đặt.

## 12. Metadata phải thống nhất với vòng đời của đối tượng

Một quyết định trạng thái có thể ảnh hưởng tới những hành vi khác ngoài nhánh ghi, chẳng hạn cách hạ tầng auditing phân biệt đối tượng tạo mới và đối tượng cập nhật.

Vì vậy, khi thay đổi policy cần xét:

- Instance trước lần lưu đầu.
- Instance trả về sau lưu.
- Instance được phục hồi khi đọc lại.
- Bản sao được tạo từ một instance đã lưu.
- Trường hợp một lần ghi thất bại hoặc transaction bị rollback.

Với immutable, không mặc định instance đầu vào đã được cập nhật ID hoặc version tại chỗ. Hãy dùng instance trả về từ API lưu và giữ thông tin trạng thái khi tạo bản sao theo mục đích nghiệp vụ.

Với một flag new do ứng dụng quản lý, không đặt flag về false chỉ vì phép đánh giá `isNew` vừa được gọi. Việc hỏi trạng thái không phải sự kiện lưu thành công.

Metadata đúng cũng không thay thế creator hoặc converter đúng. Nếu mapper bỏ mất version khi phục hồi, strategy có thể trả true theo đúng quy tắc nhưng trên dữ liệu instance sai.

Đây là lý do một lỗi “lưu lại thành tạo mới” cần được kiểm tra cả mapping lẫn state detection.

## 13. Chẩn đoán theo đường thực thi

Một lần điều tra nên trả lời lần lượt:

1. Repository hoặc template nào thực hiện thao tác?
2. Adapter EntityInformation nào có mặt, nếu đường đó sử dụng adapter?
3. Metadata đến từ mapping context nào?
4. Tên implementation metadata thực tế là gì?
5. ID và version được metadata nhận diện là những thuộc tính nào?
6. Kiểu miền có triển khai Persistable không?
7. Giá trị tại thời điểm đánh giá là gì?
8. Kết quả phân loại được module chuyển thành thao tác nào?

Không chỉ nhìn class miền trong source rồi suy rằng runtime dùng đúng annotation, đúng getter và đúng context.

Trong ứng dụng có nhiều kho, cần gắn mỗi phép quan sát với repository và context cụ thể. Một probe chạy đúng nhưng dùng context khác vẫn có thể tạo kết luận sai.

Việc truy vấn bằng derived query, Query by Example, phân trang hoặc projection không tự thay thế policy nhận diện mới. Tuy nhiên, nếu kết quả ánh xạ thiếu ID hoặc version cần thiết, instance nhận được có thể không phù hợp để lưu lại như một aggregate đầy đủ.

Một DTO cho hiển thị ít trường không nên được mặc định dùng như bản sao hoàn chỉnh của entity để đưa trở lại save.

## 14. Kế hoạch kiểm chứng và bài thực hành

Các tình huống dưới đây là kế hoạch cho người học, chưa phải kết quả chạy thử kèm bài:

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Cùng kiểu có version null và version đã gán | Dùng chung metadata nhưng kết quả theo từng instance |
| Có ID nhưng version null | Metadata mặc định chọn version như dự kiến |
| Có version primitive bằng không | Phân biệt quy tắc module với JPA |
| Kiểu triển khai Persistable | Quyết định được delegate đúng nhánh |
| Thêm một bean IsNewStrategy độc lập | Không nhầm việc có bean với việc đã tích hợp |
| Đổi fallback trong metadata tùy biến | Đường repository thật sử dụng metadata đó |
| Đọc lại sau lưu | ID, version và trạng thái mới được phục hồi đúng |
| Đối tượng immutable được lưu | Tiếp tục sử dụng instance sau cùng |
| Đánh giá nhiều instance đồng thời | Không lẫn trạng thái qua field của strategy |
| Bản ghi bị xóa ngoài luồng | Không nhầm trạng thái trong bộ nhớ với tồn tại trong kho |

Một kiểm tra đơn vị của strategy chỉ chứng minh quy tắc của strategy. Kiểm tra qua mapping context chứng minh thêm việc nhận diện thuộc tính. Kiểm tra tích hợp qua repository mới xác nhận chuỗi wiring và hành vi module.

Bài thực hành là dựng một báo cáo trạng thái cho ba trường hợp:

1. Một aggregate MongoDB có ID tự gán và version Long nullable.
2. Một aggregate JDBC dùng ID Long được kho cấp.
3. Một entity JPA có version primitive để quan sát điểm khác biệt của module.

Với từng trường hợp, ghi lại nguồn metadata, ID/version trước và sau lưu, kết quả nhận diện và thao tác persistence thực tế. Nếu cần tùy biến, chỉ rõ thành phần nào chọn strategy và cách chứng minh repository đang sử dụng policy đó.
