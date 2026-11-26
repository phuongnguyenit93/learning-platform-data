# Phạm vi thao tác repository/template có kích hoạt callback

## 1. Mục tiêu và phạm vi

Trong chương **Vòng đời và callback** của module **Spring Data Commons**, bài này trả lời câu hỏi: một thao tác truy cập dữ liệu cụ thể có thực sự đi qua entity callback hay không?

Sau bài học, bạn cần có khả năng:

- Phân loại thao tác lưu entity, đọc entity và cập nhật trực tiếp bằng query.
- Giải thích vì sao repository và template đều có thể đi qua callback.
- Nhận diện các đường bypass khi dùng modifying query, custom mapper hoặc driver trực tiếp.
- Phân biệt callback của lần ghi với callback phát sinh từ một lần đọc kiểm tra.
- Xác minh phạm vi theo store, loại kết quả và API đồng bộ/reactive.

Nguyên tắc quan trọng là **callback gắn với đường xử lý của store**, không gắn tự động với mọi phương thức có tên `save`, `update`, `find` hoặc `delete`.

Spring Data Commons cung cấp cơ chế callback, còn module store quyết định checkpoint và cách gọi. Tài liệu [Entity Callbacks](https://docs.spring.io/spring-data/commons/reference/entity-callbacks.html) mô tả việc tích hợp callback theo loại entity và sự tách biệt giữa API đồng bộ với reactive.

## 2. Lần theo đường thực thi thay vì chỉ nhìn tên phương thức

Một đường ghi entity thường có hình dạng:

```text
repository.save(entity)
    -> implementation của repository
    -> thao tác entity của store
    -> BeforeConvert
    -> mapping dữ liệu ghi
    -> BeforeSave
    -> driver ghi dữ liệu
    -> AfterSave
```

Template có thể đi thẳng vào phần giữa của đường xử lý này:

```text
template.save(entity)
    -> thao tác entity của store
    -> cùng các checkpoint được module hỗ trợ
```

Do đó, “chỉ repository mới kích hoạt callback” là cách hiểu sai. Đồng thời, cũng không được kết luận “mọi lời gọi template đều kích hoạt callback”, vì template còn có API count, update theo query hoặc truy cập collection.

Một đường cập nhật khác có thể là:

```text
template.update(query, updateDefinition)
    -> ánh xạ tên trường và giá trị của query/update
    -> driver thực hiện update
    -> trả số bản ghi bị ảnh hưởng
```

Đường này không nhất thiết có một entity đầy đủ để truyền qua các callback ghi.

Việc sử dụng mapping metadata hoặc custom converter khi xử lý giá trị query cũng không chứng minh rằng `EntityCallback` đã được gọi. Chuyển đổi kiểu và vòng đời entity là hai cơ chế khác nhau.

## 3. Phân loại thao tác trước khi lập bảng callback

| Nhóm thao tác | Dữ liệu đầu vào hoặc đầu ra | Callback cần xem xét |
| --- | --- | --- |
| Ghi một entity qua API được store hỗ trợ | Domain object để chuyển thành dữ liệu ghi | BeforeConvert, BeforeSave, AfterSave |
| Đọc và materialize domain object | Entity được dựng từ document/row | AfterConvert |
| Count hoặc exists chuẩn của store | Số lượng hoặc boolean | Không có entity tương ứng để chạy callback đọc theo từng bản ghi |
| Update bằng query và tập giá trị cập nhật | Predicate cùng Update/SQL | Không tự có chuỗi callback ghi entity |
| Delete | Entity, id hoặc predicate tùy API | Cơ chế delete riêng theo store |
| Projection, DTO hoặc scalar | Kiểu kết quả có thể khác domain type | Phụ thuộc mapping và type thực tế |
| Bulk/batch | Nhiều operation, có thể thuộc nhiều nhóm trên | Phải phân loại từng operation |
| Native driver hoặc truy cập SQL trực tiếp | Dữ liệu thấp hơn tầng entity | Không tự đi qua hạ tầng callback entity của Spring Data |

Bảng này là cách đặt câu hỏi, không phải cam kết rằng tất cả store có cùng tập callback.

Cũng cần phân biệt count được database tính với việc ứng dụng tải entity rồi gọi `list.size()`. Trường hợp thứ hai đã có một lần đọc entity và có thể đã chạy callback đọc trước khi đếm trong bộ nhớ.

## 4. MongoDB: repository và template có những đường nào?

Các ví dụ dưới đây xét entity domain và callback MongoDB đồng bộ đã được đăng ký vào hạ tầng thực tế.

| Thao tác | Phạm vi callback cần kỳ vọng |
| --- | --- |
| `MongoRepository.save(entity)` theo implementation chuẩn | Chuỗi callback ghi của đường lưu entity |
| `MongoTemplate.insert(entity)` hoặc `save(entity)` | Các checkpoint ghi mà template tích hợp |
| `findById` hoặc `findOne` có kết quả được materialize thành domain object | AfterConvert cho object đọc được và callback có type phù hợp |
| `findAll` trả domain objects | Callback đọc ở quá trình materialize các kết quả |
| `count`, `exists` chuẩn | Không chạy AfterConvert cho từng document chỉ để tính số hoặc boolean |
| `updateFirst`, `updateMulti` với Query và UpdateDefinition | Không có chuỗi BeforeConvert/BeforeSave/AfterSave của một entity save |
| Native `MongoCollection` | Không tự gọi entity callback của Spring Data |
| Aggregation hoặc projection | Kiểm tra loại kết quả và đường mapping cụ thể |

Tài liệu [MongoDB Lifecycle Events và Entity Callbacks](https://docs.spring.io/spring-data/mongodb/reference/mongodb/lifecycle-events.html) mô tả các checkpoint của quá trình ghi và materialize dữ liệu.

Đối với `updateFirst` và `updateMulti`, mã nguồn `MongoTemplate` nhánh 4.5.x cho thấy đường ánh xạ query/update rồi gọi driver, khác với chuỗi lưu entity. Xem [MongoTemplate 4.5.x](https://github.com/spring-projects/spring-data-mongodb/blob/4.5.x/spring-data-mongodb/src/main/java/org/springframework/data/mongodb/core/MongoTemplate.java).

### 4.1. Có entityClass chưa có nghĩa có entity instance

Lời gọi:

```java
template.updateFirst(query, update, Customer.class);
```

có tham số `Customer.class` để xác định metadata, collection và cách ánh xạ. Nó không có nghĩa framework phải đọc từng `Customer` từ database rồi gọi callback trước khi update.

Đây là sự khác biệt giữa **biết kiểu entity** và **thực hiện vòng đời của một entity instance**.

### 4.2. Không lấy callback đọc làm bằng chứng callback ghi

Nếu thực hiện:

```text
updateFirst(...)
findById(...)
```

thì callback đọc quan sát được ở bước sau không chứng minh bước update đã chạy callback ghi.

Tương tự, một API kết hợp cập nhật và trả object có thể có bước mapping kết quả. Cần tách câu hỏi “có materialize kết quả không?” khỏi câu hỏi “có dùng chuỗi save entity không?”.

### 4.3. Delete cần được xem riêng

Không sử dụng `BeforeSave` làm callback “trước mọi thay đổi database”, bao gồm cả xóa.

Một store có thể cung cấp sự kiện xóa theo query hoặc callback delete theo aggregate. Việc có `BeforeDeleteEvent` trong một API không chứng minh rằng mọi interface callback delete của store khác cũng được hỗ trợ.

## 5. Bulk không phải một loại vòng đời duy nhất

Có hai cách suy luận cần tránh:

```text
bulk -> luôn bỏ qua mọi callback
bulk -> luôn chạy callback như save từng entity
```

Cần phân biệt operation bên trong batch.

Ví dụ cụ thể: implementation `DefaultBulkOperations` của MongoDB nhánh 4.5.x có gọi callback cho đường insert/replace có source object, trong khi đường update/upsert bằng query dùng write model khác. Xem [DefaultBulkOperations 4.5.x](https://github.com/spring-projects/spring-data-mongodb/blob/4.5.x/spring-data-mongodb/src/main/java/org/springframework/data/mongodb/core/DefaultBulkOperations.java).

Vì vậy, khi khảo sát một batch, hãy ghi rõ:

| Thành phần trong batch | Câu hỏi cần trả lời |
| --- | --- |
| Insert domain object | Có BeforeConvert và callback ghi phù hợp không? |
| Replace bằng domain object | Replacement có được xử lý qua entity callback không? |
| Update bằng Query/Update | Có source entity hay chỉ có mô tả cập nhật? |
| Remove bằng query | Có cơ chế delete nào, và dữ liệu nào được cung cấp? |

Thời điểm callback cũng có thể khác với suy nghĩ “tất cả chỉ chạy khi execute”: ở implementation được dẫn, xử lý trước chuyển đổi của insert có thể xảy ra lúc thêm operation.

Khi batch lỗi một phần, cần xem kết quả và luồng lỗi thực tế trước khi suy ra số callback sau ghi.

`BulkOperations` còn có những giới hạn khác với thao tác đơn lẻ, chẳng hạn các tính năng cần kết quả riêng cho từng operation. Xem [BulkOperations API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/BulkOperations.html). Không chọn bulk chỉ dựa trên hình thức gọi ít phương thức hơn.

## 6. JDBC: aggregate operation và query trực tiếp

Spring Data JDBC có vòng đời của aggregate root trong những thao tác được hỗ trợ.

| Đường thao tác | Phạm vi cần xét |
| --- | --- |
| Repository save hoặc `JdbcAggregateTemplate` lưu aggregate | Các callback của quá trình lưu aggregate |
| Đọc aggregate bằng mapping mặc định | Callback sau khi dựng aggregate |
| SELECT trong `@Query` dùng mapping mặc định | Có thể tham gia callback đọc theo đường mapping của module |
| `@Modifying` với UPDATE/DELETE | Thực thi trực tiếp, không có entity callback tương ứng |
| Custom RowMapper hoặc ResultSetExtractor theo cơ chế tùy biến query | Không tự giữ nguyên chuỗi callback/event mặc định |
| Truy cập trực tiếp bằng JdbcTemplate | Không tự trở thành aggregate lifecycle operation |

Tài liệu [JDBC Lifecycle Events](https://docs.spring.io/spring-data/relational/reference/jdbc/events.html) xác định callback/event theo aggregate root và phân biệt các đường lưu/xóa với query method.

### 6.1. Không hiểu nhầm câu “query không có callback”

Cần nói rõ loại callback và loại query:

- SELECT có materialize aggregate qua mapping được hỗ trợ có thể đi qua callback đọc.
- UPDATE/DELETE trực tiếp không có nghĩa từng aggregate bị ảnh hưởng được tải lên để chạy callback ghi/xóa.
- Một query trả số lượng không materialize đầy đủ các aggregate được đếm.

Vì vậy, không được dùng giới hạn của modifying query để kết luận mọi `@Query` SELECT đều bỏ qua `AfterConvert`.

### 6.2. Custom mapper thay đổi trách nhiệm của đường đọc

Spring Data JDBC cho phép custom `RowMapper` hoặc `ResultSetExtractor`. Tài liệu nêu rằng sử dụng những cơ chế tùy biến này cho query sẽ vô hiệu chuỗi entity callbacks và lifecycle events mặc định của mapping kết quả; custom mapping có thể tự tích hợp nếu cần.

Ngoài ra, modifying query chạy trực tiếp trên database, nên auditing không tự cập nhật các trường nếu query không xử lý chúng. Xem [JDBC Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html).

Điểm cần rút ra là: giữ kiểu trả về `Customer` không đủ để chứng minh vẫn giữ cùng pipeline mapping. Cách tạo ra object đó cũng quyết định callback có được gọi hay không.

## 7. R2DBC: phân biệt thao tác entity với modifying query

R2DBC sử dụng entity callbacks reactive, gồm các checkpoint trước chuyển đổi, trước lưu, sau lưu và sau khi đọc entity. Xem [R2DBC EntityCallbacks](https://docs.spring.io/spring-data/relational/reference/r2dbc/entity-callbacks.html).

Hai cách cập nhật cần được phân biệt:

```text
Cập nhật từ entity:
entity -> callback trước chuyển đổi/lưu -> ghi -> callback sau lưu

Cập nhật theo query:
query + tập giá trị cập nhật -> SQL UPDATE -> số row bị ảnh hưởng
```

Một phương thức repository sử dụng `@Modifying` và `@Query` không tự materialize những entity bị ảnh hưởng.

Ví dụ khai báo cho một repository R2DBC đã có model và schema tương ứng:

```java
import reactor.core.publisher.Mono;

import org.springframework.data.r2dbc.repository.Modifying;
import org.springframework.data.r2dbc.repository.Query;
import org.springframework.data.repository.query.Param;

@Modifying
@Query("UPDATE customers SET name = :name WHERE id = :id")
Mono<Integer> renameDirectly(
        @Param("id") Long id,
        @Param("name") String name);
```

Đây là khai báo phương thức bên trong interface repository. Số trả về là số row bị ảnh hưởng, không phải các entity đã đi qua callback.

Tài liệu [R2DBC Modifying Queries](https://docs.spring.io/spring-data/relational/reference/r2dbc/query-methods.html#r2dbc.modifying-queries) nêu rõ modifying query không gọi events/callbacks; trường auditing cũng không tự được cập nhật nếu query không cập nhật chúng.

### 7.1. Publisher chưa được subscribe chưa chứng minh đã thực hiện thao tác

Với API R2DBC, các statement thực sự được gửi khi publisher được subscribe. Xem [Persisting Entities](https://docs.spring.io/spring-data/relational/reference/r2dbc/entity-persistence.html).

Một phép kiểm tra chỉ tạo publisher rồi đọc bộ đếm callback có thể chưa đi qua operation nào.

Khi kiểm tra, phải chờ pipeline hoàn thành hoặc quan sát lỗi của nó. Không thêm `subscribe()` riêng bên trong callback để làm bộ đếm “có vẻ chạy”, vì như vậy có thể tách công việc khỏi pipeline persistence.

### 7.2. Đúng loại callback

Callback MongoDB đồng bộ không chạy thay cho callback của `ReactiveMongoTemplate`. Callback JDBC đồng bộ cũng không thay thế callback của R2DBC dù cùng thao tác với một database quan hệ.

Khi callback không chạy, kiểm tra package/interface và kiểu API trước khi kết luận store đã bỏ qua checkpoint.

## 8. Kết quả query ảnh hưởng đến phạm vi callback đọc

### 8.1. Domain object và kết quả scalar

Đọc một entity qua mapper mặc định khác với đọc một số hoặc boolean:

```text
SELECT các cột để dựng Customer
    -> có domain object để xét callback đọc

SELECT COUNT(...)
    -> kết quả số
    -> không có từng Customer để chạy AfterConvert
```

Không xem `AfterConvert<Customer>` như một bộ lọc tự động áp dụng vào mọi phép đếm hoặc kiểm tra tồn tại.

Nếu kiểm soát phạm vi tenant hoặc điều kiện truy cập dữ liệu là yêu cầu của query, chúng cần được thể hiện trong đường truy vấn phù hợp. Sửa object sau khi đọc không thay thế điều kiện của count/exists.

### 8.2. DTO và projection

Một callback có generic type `Customer` không tự áp dụng cho mọi DTO chứa một số thuộc tính giống `Customer`.

Với projection, cần xác định:

- Store dựng domain object trước hay map trực tiếp sang kiểu kết quả?
- Callback được gọi với object có kiểu gì?
- Generic type của callback có tương thích với object đó không?
- Custom mapping có thay đổi hành vi mặc định không?

Không khẳng định mọi projection đều chạy hoặc đều bỏ qua callback. Cần kiểm tra đúng loại projection và implementation.

### 8.3. Pagination và stream

Một `Page<Customer>` có thể được tạo từ query lấy nội dung và query count. Callback đọc của entity không tự chạy cho các row chỉ được count.

Với `Slice`, stream hoặc reactive query, có thể có đọc thêm, prefetch hay hủy luồng. Vì vậy, số object cuối cùng được người dùng nhìn thấy không phải lúc nào cũng đủ để suy ra số lần materialize.

Đặt phép quan sát ở đúng tầng callback nếu mục tiêu là đo số lần callback chạy, thay vì suy luận từ số phần tử hiển thị.

## 9. Ví dụ MongoDB: đếm callback theo từng operation

Ví dụ sau dùng Java 17 trở lên. Nó dành cho môi trường thực hành riêng đã cấu hình MongoDB, repository và component scanning. Các lớp là những khai báo riêng trong cùng package.

Mục tiêu là quan sát **đường thực thi**, không tạo một cơ chế giám sát production.

### 9.1. Model và repository

```java
package com.example.callbackscope;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("callback_customers")
public record CallbackCustomer(
        @Id String id,
        String name) {
}
```

```java
package com.example.callbackscope;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface CallbackCustomerRepository
        extends MongoRepository<CallbackCustomer, String> {
}
```

### 9.2. Probe có generic type rõ ràng

```java
package com.example.callbackscope;

import java.util.concurrent.atomic.AtomicInteger;

import org.bson.Document;
import org.springframework.data.mongodb.core.mapping.event.AfterConvertCallback;
import org.springframework.data.mongodb.core.mapping.event.AfterSaveCallback;
import org.springframework.data.mongodb.core.mapping.event.BeforeConvertCallback;
import org.springframework.data.mongodb.core.mapping.event.BeforeSaveCallback;
import org.springframework.stereotype.Component;

@Component
public class CallbackProbe
        implements BeforeConvertCallback<CallbackCustomer>,
                   BeforeSaveCallback<CallbackCustomer>,
                   AfterSaveCallback<CallbackCustomer>,
                   AfterConvertCallback<CallbackCustomer> {

    private final AtomicInteger beforeConvert = new AtomicInteger();
    private final AtomicInteger beforeSave = new AtomicInteger();
    private final AtomicInteger afterSave = new AtomicInteger();
    private final AtomicInteger afterConvert = new AtomicInteger();

    @Override
    public CallbackCustomer onBeforeConvert(
            CallbackCustomer entity, String collection) {

        beforeConvert.incrementAndGet();

        String name = entity.name();

        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                    "name must not be blank");
        }

        return new CallbackCustomer(entity.id(), name.strip());
    }

    @Override
    public CallbackCustomer onBeforeSave(
            CallbackCustomer entity,
            Document document,
            String collection) {

        beforeSave.incrementAndGet();
        return entity;
    }

    @Override
    public CallbackCustomer onAfterSave(
            CallbackCustomer entity,
            Document document,
            String collection) {

        afterSave.incrementAndGet();
        return entity;
    }

    @Override
    public CallbackCustomer onAfterConvert(
            CallbackCustomer entity,
            Document document,
            String collection) {

        afterConvert.incrementAndGet();
        return entity;
    }

    public Counts snapshot() {
        return new Counts(
                beforeConvert.get(),
                beforeSave.get(),
                afterSave.get(),
                afterConvert.get());
    }

    public void reset() {
        beforeConvert.set(0);
        beforeSave.set(0);
        afterSave.set(0);
        afterConvert.set(0);
    }

    public record Counts(
            int beforeConvert,
            int beforeSave,
            int afterSave,
            int afterConvert) {
    }
}
```

Bộ đếm dùng `AtomicInteger` để tránh mất cập nhật đơn lẻ. Tuy nhiên, `reset` và `snapshot` không tạo một phép đo nhất quán cho nhiều operation đang chạy đồng thời. Kịch bản dưới đây cần chạy tuần tự, không có lưu lượng khác dùng cùng probe.

### 9.3. Thực hiện mỗi đường thao tác riêng

Đoạn sau giả định đã nhận được các bean `repository`, `template` và `probe` tương ứng:

```java
import java.util.Objects;

import org.bson.Document;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

// 1. Lưu entity.
probe.reset();

CallbackCustomer saved = repository.save(
        new CallbackCustomer("scope-demo-1", "  An  "));

System.out.println(probe.snapshot());

// 2. Đọc một entity đang tồn tại.
probe.reset();

repository.findById(saved.id()).orElseThrow();

System.out.println(probe.snapshot());

// 3. Count và exists.
probe.reset();

repository.count();
repository.existsById(saved.id());

System.out.println(probe.snapshot());

// 4. Update trực tiếp theo query.
probe.reset();

Query byId = Query.query(
        Criteria.where("id").is(saved.id()));

template.updateFirst(
        byId,
        new Update().set("name", "  Binh  "),
        CallbackCustomer.class);

System.out.println(probe.snapshot());

// 5. Quan sát document thô, không đọc qua entity mapper.
Document raw = Objects.requireNonNull(
        template.getCollection("callback_customers")
                .find(new Document("_id", saved.id()))
                .first());

System.out.println(raw.getString("name"));
System.out.println(probe.snapshot());
```

Id `scope-demo-1` được chọn dưới dạng chuỗi không có định dạng ObjectId, để phép đọc bằng driver thô không phải tự chuyển kiểu định danh.

Trong điều kiện các operation thành công, một callback bean như trên và không có operation phát sinh thêm, kết quả mong đợi:

| Bước | BeforeConvert | BeforeSave | AfterSave | AfterConvert |
| --- | --- | --- | --- | --- |
| Save một entity | 1 | 1 | 1 | 0 |
| FindById có một kết quả | 0 | 0 | 0 | 1 |
| Count và exists chuẩn | 0 | 0 | 0 | 0 |
| UpdateFirst theo query | 0 | 0 | 0 | 0 |
| Đọc document bằng driver thô, tiếp sau bước update | Vẫn 0 | Vẫn 0 | Vẫn 0 | Vẫn 0 |

Giá trị `name` trong document thô sau update được kỳ vọng giữ khoảng trắng ở hai đầu: `"  Binh  "`. Callback chuẩn hóa của đường save đã không xử lý lần update trực tiếp này.

Đây là lý do phải kiểm tra cả callback lẫn dữ liệu thật. Chỉ thấy database có giá trị mới chưa chứng minh cơ chế chuẩn hóa hoặc auditing đã chạy.

Các con số trong bảng là kỳ vọng của kịch bản giới hạn trên, không phải cam kết đúng một lần cho mọi operation, mọi phiên bản hoặc mọi cấu hình.

## 10. Repository fragment và template tự tạo có thể đổi phạm vi

Một phương thức trong repository fragment có thể:

```text
A. Gọi template.save(entity)
B. Gọi template.updateFirst(query, update, Type.class)
C. Gọi trực tiếp driver
```

Cả ba đều có thể được gọi từ cùng một repository interface, nhưng không có cùng đường callback.

Nếu refactor từ A sang B để giảm số lần đọc/ghi, cần xem đó là thay đổi về hành vi lifecycle, ngoài thay đổi hiệu năng.

Template được tạo thủ công cũng cần được nối với callback infrastructure phù hợp. Callback là bean trong một context không tự chứng minh mọi template tự tạo đều nhìn thấy nó.

Khi dùng nhiều database hoặc nhiều template, ghi rõ operation đang chạy qua instance nào. Một probe hoạt động với template chính chưa xác minh được template còn lại.

## 11. Điều kiện để callback có cơ hội chạy

Có thể lần theo chuỗi điều kiện:

```text
Đúng store và đúng API đồng bộ/reactive?
    -> callback đã đăng ký với hạ tầng đang dùng?
    -> generic type phù hợp với object thực tế?
    -> operation có đi qua checkpoint?
    -> luồng đã thực sự được thực thi?
    -> có kết quả/entity để xử lý ở checkpoint đó?
```

Một callback đọc không chạy khi không có entity được trả về không nhất thiết là lỗi. Một callback sau ghi không chạy nếu lỗi đã chặn operation trước đó cũng không đồng nghĩa callback bị mất đăng ký.

Không xem tên lifecycle event giống tên callback là bằng chứng thay thế. Event listener và entity callback có cơ chế tích hợp khác nhau; cấu hình publication của events cần được phân biệt với cấu hình callbacks.

## 12. Hệ quả đối với auditing, validation và bất biến dữ liệu

Nếu một quy tắc chỉ nằm trong callback, phạm vi bảo vệ của nó là những đường thực thi thực sự gọi callback đó.

Ví dụ:

- Callback chuẩn hóa tên chạy với save entity nhưng có thể bị bỏ qua bởi update theo query.
- Auditing được tích hợp qua callback không tự cập nhật timestamp ở modifying query.
- Kiểm tra trong AfterConvert không thay đổi predicate của count hoặc exists.
- Native driver có thể ghi dữ liệu mà callback Spring Data không quan sát được.

Khi cần dùng cả entity save và update trực tiếp, có thể tổ chức quy tắc như sau:

1. Đặt quy tắc nghiệp vụ dùng chung trong thành phần phù hợp.
2. Áp dụng nó tường minh ở những đường cập nhật không có callback.
3. Dùng ràng buộc database cho điều kiện cần được bảo vệ ở cấp lưu trữ.
4. Kiểm tra các đường dữ liệu khác nhau bằng kịch bản tích hợp tương ứng.

Không khắc phục bằng cách tự gọi tùy tiện một callback rồi cho rằng đã tái tạo toàn bộ pipeline của store. Callback có thể phụ thuộc checkpoint, thứ tự, entity trả về và biểu diễn dữ liệu mà hạ tầng chuẩn bị.

Cũng không dùng AfterSave như bằng chứng transaction đã commit hoặc như một cam kết gửi thông báo đúng một lần. Retry, subscription lặp lại và luồng lỗi có thể làm thay đổi số lần thực thi.

## 13. Lập bảng phạm vi cho ứng dụng thực tế

Một bảng hữu ích cần chỉ ra API và đường mapping cụ thể:

| Operation thực tế | Store/API | Có entity instance không? | Checkpoint dự kiến | Bằng chứng cần thu thập |
| --- | --- | --- | --- | --- |
| Lưu khách hàng | Repository save chuẩn | Có | Callback ghi | Probe và dữ liệu thô |
| Đổi tên bằng query | Template update | Không có entity đầy đủ để lưu | Không dùng chuỗi save entity | Probe riêng cho update |
| Đọc chi tiết | Query trả domain type | Có khi tìm thấy | Callback đọc phù hợp | Type kết quả và probe |
| Đếm kết quả | Count query | Không materialize từng entity | Không có callback đọc cho từng bản ghi | Count path riêng |
| Import theo batch | Bulk operation cụ thể | Tùy từng model | Theo insert/replace/update | Kiểm tra từng nhánh và phiên bản |
| SQL với custom mapper | JDBC query tùy biến | Do mapper tạo | Không mặc định giữ lifecycle chuẩn | Hợp đồng custom mapper |

Trước khi xác nhận một dòng, ghi rõ phiên bản store và callback đang quan sát. Nếu kết luận dựa vào implementation, cần giữ phạm vi phiên bản của kết luận đó.

## 14. Bài thực hành

Chọn một store đang sử dụng và thực hiện:

1. Liệt kê các operation repository, template và native API mà ứng dụng thật sự gọi.
2. Nhóm chúng theo entity operation, query trực tiếp, đọc domain object và kết quả scalar.
3. Đăng ký probe callback có generic type rõ ràng.
4. Kiểm tra từng operation riêng, không trộn lần ghi với lần đọc xác minh.
5. Với reactive API, chờ publisher hoàn thành trước khi đọc kết quả quan sát.
6. Kiểm tra một đường bypass có chủ đích và giải thích cách quy tắc nghiệp vụ được bảo vệ ở đường đó.
7. Nếu dùng bulk, custom mapper hoặc projection, thêm kịch bản riêng cho đúng loại operation/kết quả.

Bài thực hành đạt yêu cầu khi bạn mô tả được **đường thực thi**, **checkpoint có hoặc không được gọi**, **kiểu object đi qua callback** và **ảnh hưởng lên dữ liệu thật**, thay vì chỉ dựa vào tên repository hoặc template.
