# Callback `execute` để dùng `MongoDatabase` hoặc `MongoCollection`

> **Chương:** MongoTemplate  
> **Module:** `SPRING_DATA_MONGODB` — kết nối, ánh xạ document và thao tác MongoDB qua `MongoTemplate` hoặc repository; thực hành truy vấn, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng.  
> **Mục tiêu:** Biết khi nào cần truy cập MongoDB Java Driver trực tiếp, sử dụng đúng các overload `MongoTemplate.execute(...)`, phân biệt `DbCallback` với `CollectionCallback`, quản lý cursor/tài nguyên, hiểu ranh giới mapping và transaction, và kiểm thử thao tác raw BSON an toàn.

## 1. Vì sao `MongoTemplate` có callback `execute`?

Phần lớn thao tác thông thường có thể diễn đạt bằng `MongoRepository` hoặc `MongoTemplate`:

~~~java
// Truy vấn theo entity và các property Java.
template.find(
    Query.query(Criteria.where("state").is("PAID")),
    OrderDocument.class
);
~~~

Nhưng đôi khi ứng dụng cần một tính năng thấp hơn hoặc một API cụ thể của **MongoDB Java Driver**: xem metadata index, chạy command, đặt các tùy chọn driver chuyên biệt, truy cập `MongoCollection<Document>` hay làm việc với cấu trúc BSON mà chưa có ánh xạ entity thuận tiện.

`MongoTemplate.execute(...)` cho phép đặt thao tác driver trong một **callback** nhận đối tượng do Spring Data cung cấp:

- `DbCallback<T>` nhận `com.mongodb.client.MongoDatabase`.
- `CollectionCallback<T>` nhận `com.mongodb.client.MongoCollection<org.bson.Document>`.

Spring Data chịu trách nhiệm chọn database/collection theo cấu hình của template và cung cấp lối đi nhất quán cho các thao tác thấp tầng, bao gồm việc dịch các lỗi MongoDB phù hợp sang hệ thống `DataAccessException` của Spring.

~~~mermaid
flowchart TD
    A["Application service"] --> B["MongoTemplate / MongoOperations"]
    B --> C{"Cần thao tác gì?"}
    C -->|CRUD theo domain| D["find / insert / update / remove"]
    C -->|MongoDatabase| E["execute(DbCallback<T>)"]
    C -->|MongoCollection| F["execute(CollectionCallback<T>)"]
    D --> G["MongoDB driver"]
    E --> G
    F --> G
    G --> H[("MongoDB")]
~~~

**Điểm quan trọng:** callback `execute` là **điểm vào driver**, không phải một giao dịch tự động, cũng không phải cách để ép driver tự hiểu mọi annotation mapping của entity. Truy cập raw driver đem lại linh hoạt nhưng yêu cầu bạn kiểm soát BSON, ID, tài nguyên và tác động ghi một cách tường minh.

## 2. Ba overload chính cần nhớ

Những chữ ký phổ biến của `MongoOperations` trong Spring Data MongoDB:

~~~java
<T> T execute(DbCallback<T> action);

<T> T execute(
    Class<?> entityClass,
    CollectionCallback<T> action
);

<T> T execute(
    String collectionName,
    CollectionCallback<T> action
);
~~~

| Overload | Đối tượng callback nhận | Nên dùng khi | Cách xác định đích |
| --- | --- | --- | --- |
| `execute(DbCallback<T>)` | `MongoDatabase` | Xem database, chạy command, quản lý metadata cấp database | Database được `MongoTemplate` cấu hình |
| `execute(OrderDocument.class, CollectionCallback<T>)` | `MongoCollection<Document>` | Thao tác raw trên collection tương ứng entity | Mapping `@Document` và naming strategy |
| `execute("orders_execute_demo_008", CollectionCallback<T>)` | `MongoCollection<Document>` | Biết chính xác tên collection | Chuỗi tên collection đưa vào |

`T` là **kiểu kết quả của callback**: `Long`, `Boolean`, `Document`, `List<Document>`, `UpdateResult` hoặc DTO kết quả do ứng dụng tự tạo. Callback có thể trả `null` nếu nghiệp vụ cho phép, vì vậy đừng tự động unbox `Long`/`Boolean` mà không kiểm soát tình huống null.

Hai dạng `execute` nhận collection không giống nhau về cách chọn collection. Khi có annotation `@Document(collection = "...")`, truyền `Class` thường giúp tránh hard-code tên collection; khi xử lý collection hệ thống hoặc dữ liệu chưa có entity, truyền tên tường minh có thể phù hợp hơn.

### 2.1. Các import cần thiết

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.DbCallback;
import org.springframework.data.mongodb.core.CollectionCallback;
~~~

Các đoạn ví dụ dùng API **driver đồng bộ** trong `MongoTemplate`. Đừng trộn `com.mongodb.client.MongoCollection` với `com.mongodb.reactivestreams.client.MongoCollection` của reactive driver: hai kiểu này không cùng phương thức thực thi.

## 3. Chuẩn bị collection và entity minh họa

### 3.1. Bộ dữ liệu riêng cho bài thực hành

Trên `mongosh` kết nối với **database học tập biệt lập**, tạo dữ liệu thử:

~~~javascript
use spring_data_mongodb_lab

const orders = db.orders_execute_demo_008;

orders.insertMany([
  {
    _id: "o801",
    tenant_id: "t01",
    state_code: "PAID",
    amount_vnd: 150000,
    version: NumberLong(0)
  },
  {
    _id: "o802",
    tenant_id: "t01",
    state_code: "NEW",
    amount_vnd: 300000,
    version: NumberLong(0)
  },
  {
    _id: "o803",
    tenant_id: "t02",
    state_code: "PAID",
    amount_vnd: 500000,
    version: NumberLong(0)
  },
  {
    _id: "o804",
    tenant_id: "t01",
    state_code: "CANCELLED",
    amount_vnd: 90000,
    version: NumberLong(0)
  }
]);

orders.createIndex(
  { tenant_id: 1, state_code: 1 },
  { name: "tenant_state_idx" }
);
~~~

Chỉ chạy đoạn `insertMany` trên collection test chưa có các ID này, vì MongoDB sẽ báo duplicate key khi lặp lại. Các ví dụ đọc phía dưới giả định fixture **chưa bị thay đổi** bởi các ví dụ update.

Với dữ liệu gốc: có 4 order; tenant `t01` có 3 order; tenant `t01` và trạng thái `PAID` có đúng 1 order (`o801`).

### 3.2. Entity Java dùng tên property khác tên BSON

~~~java
// OrderDocument.java
package com.example.templatecallback;

import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders_execute_demo_008")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("state_code")
    private String state;

    @Field("amount_vnd")
    private long amountVnd;

    @Version
    private Long version;

    protected OrderDocument() { }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getState() { return state; }
    public long getAmountVnd() { return amountVnd; }
    public Long getVersion() { return version; }
}
~~~

Đây là dụng ý của ví dụ: **Java property** tên `tenantId`, `state`, `amountVnd`; **BSON field** tên `tenant_id`, `state_code`, `amount_vnd`. Các thao tác `MongoTemplate.find(Query, OrderDocument.class)` dùng metadata mapping để chuyển đường dẫn property, còn raw driver trong callback cần bạn tự dùng **tên BSON thực tế**.

Với `@MongoId(FieldType.STRING)`, giá trị `_id` được giữ dạng BSON string, tránh một số khác biệt với `@Id String` khi chuỗi trông như ObjectId.

## 4. `DbCallback<T>`: truy cập `MongoDatabase`

### 4.1. Lấy tên database đã được cấu hình

~~~java
import org.springframework.data.mongodb.core.DbCallback;

String dbName = template.execute(
    (DbCallback<String>) db -> db.getName()
);
~~~

Trong đó `template` là `MongoTemplate` đã được inject. `db` mang kiểu `MongoDatabase`; `db.getName()` trả tên database mà template đang thao tác, không cần tự tạo một kết nối mới.

Một tình huống hữu ích là chẩn đoán lỗi “không tìm thấy document”: trước khi sửa query, hãy xác minh chương trình thực sự đang dùng **database nào**. Tuy nhiên đừng trả tên database, URI hoặc thông tin kết nối nhạy cảm trực tiếp ra API công khai.

### 4.2. Chạy lệnh kiểm tra kết nối bằng `runCommand`

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.DbCallback;

Document reply = template.execute(
    (DbCallback<Document>) db ->
        db.runCommand(new Document("ping", 1))
);

Number ok = reply.get("ok", Number.class);
boolean healthy = ok != null && ok.doubleValue() == 1.0;
~~~

`ping` là lệnh MongoDB cấp database, nên `DbCallback` phù hợp hơn `CollectionCallback`. Phản hồi là `Document` BSON thô, không phải entity/domain object. Trong thực tế nên dùng hệ thống health check/Actuator phù hợp thay vì chạy `ping` trên mọi request HTTP.

### 4.3. Liệt kê collection trong một database

~~~java
import java.util.ArrayList;
import java.util.List;
import org.springframework.data.mongodb.core.DbCallback;

List<String> names = template.execute(
    (DbCallback<List<String>>) db ->
        db.listCollectionNames().into(new ArrayList<>())
);
~~~

Trong ví dụ, driver được gọi qua `MongoDatabase`. Việc liệt kê toàn bộ collection có thể cần quyền và không nên phát hành tên collection cho khách hàng cuối. Với hệ thống nhiều tenant hoặc nhiều database, cần đặc biệt kiểm soát database đang được template trỏ tới.

### 4.4. Khi cần lấy một collection từ DbCallback

~~~java
Long count = template.execute(
    (DbCallback<Long>) db ->
        db.getCollection("orders_execute_demo_008")
            .countDocuments(new Document("tenant_id", "t01"))
);
~~~

Cách này hợp lệ, nhưng nếu chỉ thao tác với **một collection xác định**, `CollectionCallback` thường rõ ràng hơn: template chọn collection cho bạn, code không phải gọi `db.getCollection(...)` và có thể tận dụng overload theo entity class.

**Không nhầm:** `DbCallback` cho truy cập database đang cấu hình, nhưng không cho phép tự do đọc mọi database/collection nếu MongoDB account không có quyền. Giới hạn quyền vẫn được server thực thi.

## 5. `CollectionCallback<T>`: truy cập `MongoCollection<Document>`

### 5.1. Đếm document theo điều kiện BSON

~~~java
import com.mongodb.client.model.Filters;
import org.springframework.data.mongodb.core.CollectionCallback;

Long tenantCount = template.execute(
    "orders_execute_demo_008",
    (CollectionCallback<Long>) collection ->
        collection.countDocuments(
            Filters.eq("tenant_id", "t01")
        )
);
// Dữ liệu gốc: tenantCount == 3.
~~~

Overload nhận tên collection truyền cho callback một `MongoCollection<Document>` của driver. Code không dùng `Query` hay `Criteria` của Spring Data mà dùng `Filters` của driver.

### 5.2. Chọn collection thông qua entity class

~~~java
Long paidForTenant = template.execute(
    OrderDocument.class,
    (CollectionCallback<Long>) collection ->
        collection.countDocuments(
            Filters.and(
                Filters.eq("tenant_id", "t01"),
                Filters.eq("state_code", "PAID")
            )
        )
);
// Dữ liệu gốc: paidForTenant == 1.
~~~

Spring Data dùng `@Document(collection = "orders_execute_demo_008")` để tìm collection phù hợp. Đây là một lợi ích của overload theo class. Tuy nhiên **bên trong callback vẫn là API raw driver**, nên `"state_code"` là tên BSON thực, chứ không phải property Java `"state"`.

### 5.3. Lấy một document thô

~~~java
import org.bson.Document;
import com.mongodb.client.model.Filters;

Document raw = template.execute(
    OrderDocument.class,
    collection ->
        collection.find(Filters.eq("_id", "o801")).first()
);

if (raw != null) {
    String stateCode = raw.getString("state_code"); // "PAID".
    String tenant = raw.getString("tenant_id");     // "t01".
}
~~~

`first()` có thể trả `null` nếu không có document. Đừng giả định các field đều hiện diện hoặc đúng kiểu, nhất là khi dữ liệu đến từ các version schema khác nhau. Nếu cần entity Java, ưu tiên `MongoTemplate.findById("o801", OrderDocument.class)` để converter tự map.

### 5.4. Chỉ lấy một vài trường với driver projection

~~~java
import java.util.ArrayList;
import java.util.List;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import org.bson.Document;

List<Document> summaries = template.execute(
    "orders_execute_demo_008",
    collection -> collection
        .find(Filters.eq("tenant_id", "t01"))
        .projection(Projections.include(
            "_id", "state_code", "amount_vnd"
        ))
        .limit(10)
        .into(new ArrayList<>())
);
~~~

`Projections.include(...)` yêu cầu MongoDB chỉ trả các trường được chọn, giảm payload so với lấy toàn bộ document. Ở driver, `_id` thường được trả mặc định trừ khi bị exclude; ở ví dụ này ta include tường minh để rõ hợp đồng kết quả. Đây là thao tác **BSON field projection**, không phải một interface projection của Spring Data.

**Giới hạn:** nếu callback trả một danh sách rất lớn, `into(new ArrayList<>())` sẽ vật chất hóa toàn bộ kết quả trong bộ nhớ. Hãy giới hạn số phần tử hoặc xử lý bằng cursor trong callback.

## 6. Ghi dữ liệu qua callback: linh hoạt nhưng phải tự giữ quy tắc mapping

### 6.1. Cập nhật một field bằng driver

~~~java
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;

UpdateResult result = template.execute(
    OrderDocument.class,
    collection -> collection.updateOne(
        Filters.and(
            Filters.eq("_id", "o802"),
            Filters.eq("tenant_id", "t01"),
            Filters.eq("state_code", "NEW")
        ),
        Updates.set("state_code", "PAID")
    )
);

if (result != null && result.wasAcknowledged()) {
    long matched = result.getMatchedCount();
    long modified = result.getModifiedCount();
    // Trên dữ liệu gốc: matched=1, modified=1.
}
~~~

Đây là thao tác **ghi thật**: chỉ thực hiện trên dữ liệu thử nghiệm. Nếu lặp lại, `state_code` của `o802` không còn là `NEW` và `matchedCount` có thể bằng 0. Tùy write concern, các phương thức lấy số lượng chỉ hợp lệ khi server xác nhận kết quả.

### 6.2. Raw driver không tự áp dụng mapping của entity

Trong `OrderDocument`, Java property `state` ánh xạ sang BSON `state_code`. So sánh:

~~~java
// Spring Data: Criteria dùng property Java.
template.updateFirst(
    Query.query(Criteria.where("id").is("o802")),
    new Update().set("state", "PAID"),
    OrderDocument.class
);

// Driver callback: filter/update dùng tên BSON thực tế.
template.execute(OrderDocument.class, collection ->
    collection.updateOne(
        Filters.eq("_id", "o802"),
        Updates.set("state_code", "PAID")
    )
);
~~~

Nếu dùng nhầm `Updates.set("state", "PAID")` trong callback, driver có thể tạo một **trường BSON mới tên state** thay vì sửa `state_code`. Entity Spring Data vẫn đọc thuộc tính `state` từ `state_code`; dữ liệu phát sinh hai field mang ý nghĩa tương tự sẽ gây khó chẩn đoán.

Các thao tác `collection.insertOne(new Document(...))`, `updateOne` hay `deleteMany` là API driver. Chúng **không tự chạy chu trình convert entity, auditing, entity callbacks và mapping events của `MongoTemplate.save/insert`**. Nếu ứng dụng dựa vào những chức năng này, callback raw không phải cách thay thế không đổi hành vi.

### 6.3. `@Version` không tự được kiểm soát khi raw update

Entity ở mục 3 có:

~~~java
@Version
private Long version;
~~~

Khi thao tác qua Spring Data mapping phù hợp, `@Version` dùng để phát hiện cập nhật/xóa dựa trên một entity đã cũ. Nhưng ở lệnh driver raw:

~~~java
collection.updateOne(
    Filters.eq("_id", "o802"),
    Updates.set("state_code", "PAID")
);
~~~

không có điều kiện hay phép tăng `version` nào được thêm tự động. Nếu raw writer thay đổi dữ liệu mà không tăng version, một luồng Spring Data đang giữ entity cũ có thể **không phát hiện** thay đổi đó qua optimistic locking.

Nếu buộc dùng driver raw cho một entity có version, hãy áp dụng chính sách phiên bản **một cách tường minh**, ví dụ điều kiện `_id + version` và tăng version nguyên tử:

~~~java
import com.mongodb.client.result.UpdateResult;
import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Updates.*;

long expectedVersion = 0L; // Trong thực tế lấy từ dữ liệu đã đọc.

UpdateResult changed = template.execute(
    OrderDocument.class,
    collection -> collection.updateOne(
        and(
            eq("_id", "o802"),
            eq("version", expectedVersion),
            eq("state_code", "NEW")
        ),
        combine(
            set("state_code", "PAID"),
            inc("version", 1L)
        )
    )
);

if (changed == null || changed.getMatchedCount() != 1) {
    throw new IllegalStateException(
        "Order not found, state changed, or version conflict"
    );
}
~~~

Đoạn này là **một nhánh ví dụ thay thế**, không chạy ngay sau ví dụ đã chuyển `o802` sang PAID. Hãy chuẩn bị lại fixture nếu muốn thấy `matchedCount=1`. Dùng `inc("version", 1L)` phải phù hợp kiểu BSON `version` thực tế, và mọi writer khác cũng cần chung quy ước version.

## 7. Đọc cursor trong callback và quản lý tài nguyên

### 7.1. Tránh trả raw cursor ra ngoài callback

Một cursor của MongoDB driver liên quan tới tài nguyên kết nối/server cursor. Nếu callback trả thẳng `FindIterable` hoặc `MongoCursor` để caller sử dụng sau, vòng đời của truy vấn có thể tách khỏi vòng đời session/transaction và làm rò tài nguyên.

Hãy **tiêu thụ và đóng cursor bên trong callback** khi muốn kiểm soát dữ liệu thô:

~~~java
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import java.util.ArrayList;
import java.util.List;
import org.bson.Document;

List<Document> selected = template.execute(
    "orders_execute_demo_008",
    collection -> {
        List<Document> rows = new ArrayList<>();

        try (MongoCursor<Document> cursor = collection
                .find(Filters.eq("tenant_id", "t01"))
                .projection(Projections.include(
                    "_id", "state_code", "amount_vnd"
                ))
                .sort(Sorts.ascending("_id"))
                .limit(100)
                .iterator()) {

            while (cursor.hasNext()) {
                rows.add(cursor.next());
            }
        }

        return rows;
    }
);
~~~

`try-with-resources` đóng `MongoCursor` ngay cả khi có lỗi trong lúc duyệt. Giới hạn `100` chỉ là một ví dụ: nếu collection lớn, đừng tăng vô hạn limit; xử lý theo batch hoặc stream.

### 7.2. Khi nào dùng `MongoTemplate.stream`?

Nếu nghiệp vụ muốn đọc nhiều entity Java liên tiếp, `MongoTemplate.stream(Query, Class)` có thể phù hợp hơn vì vẫn dùng converter:

~~~java
import org.springframework.data.util.CloseableIterator;

Query query = Query.query(
    Criteria.where("tenantId").is("t01")
);

try (CloseableIterator<OrderDocument> cursor =
         template.stream(query, OrderDocument.class)) {

    while (cursor.hasNext()) {
        OrderDocument order = cursor.next();
        // Xử lý lần lượt các domain object.
    }
}
~~~

`stream` cũng cần đóng; không đồng nghĩa toàn bộ quá trình xử lý hàng triệu record có thể chạy mà không gặp timeout, lỗi mạng hoặc thay đổi dữ liệu đồng thời. Khi cần resume sau lỗi, thiết kế checkpoint theo khóa sắp xếp ổn định, retry và idempotency.

## 8. Xem metadata index và những thao tác driver chuyên biệt

### 8.1. Kiểm tra một index đã tồn tại

~~~java
import org.bson.Document;

Boolean hasIndex = template.execute(
    OrderDocument.class,
    collection -> {
        for (Document index : collection.listIndexes()) {
            if ("tenant_state_idx".equals(index.getString("name"))) {
                return true;
            }
        }
        return false;
    }
);
~~~

`listIndexes()` thuộc MongoDB Java Driver, trả metadata BSON. Đây là trường hợp hợp lý cho `CollectionCallback` nếu bạn cần kiểm tra tùy chọn index cụ thể mà API `MongoTemplate` mức cao không biểu diễn thuận tiện.

Đừng mặc định “index tồn tại với tên ấy” nghĩa là **định nghĩa index đúng**. Muốn kiểm chứng đầy đủ, kiểm tra thêm `key`, `unique`, `partialFilterExpression`, `collation` hoặc các option tương ứng theo yêu cầu nghiệp vụ.

### 8.2. Tạo index bằng driver

~~~java
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;

String name = template.execute(
    OrderDocument.class,
    collection -> collection.createIndex(
        Indexes.compoundIndex(
            Indexes.ascending("tenant_id"),
            Indexes.ascending("state_code")
        ),
        new IndexOptions().name("tenant_state_idx")
    )
);
~~~

Lệnh này **thay đổi metadata collection**; chỉ chạy trên môi trường thử nghiệm khi bạn biết index chưa tồn tại hoặc định nghĩa hiện tại tương thích. Tạo index production cần kế hoạch vận hành, đánh giá tải và kiểm tra dữ liệu (đặc biệt với unique index).

Với dự án thông thường, hãy cân nhắc `@Indexed`, `IndexOperations`/`IndexResolver` hoặc một migration có quản lý. Callback driver không phải con đường bắt buộc để tạo mọi index.

### 8.3. Command ở cấp database khác với CRUD trên collection

Một số command làm việc ở cấp database (`ping`, xem cấu hình, command quản trị được cấp quyền) nên `DbCallback` là lớp phù hợp. Không chạy command phá hủy collection/database chỉ vì `MongoDatabase` cho phép gọi `runCommand`; vẫn phải tuân thủ phân quyền và chính sách migration.

Nếu chỉ cần thực thi một MongoDB command từ Spring Data, `MongoTemplate.executeCommand(...)` là API mức cao khác đáng cân nhắc; nó không yêu cầu tự tạo `DbCallback`.

## 9. Phân biệt callback raw và query ánh xạ entity

| Khía cạnh | `MongoTemplate.find/update/insert` | `MongoTemplate.execute(... CollectionCallback)` |
| --- | --- | --- |
| Đầu vào thường dùng | Entity Java, `Query`/`Criteria`/`Update` | `MongoCollection<Document>`, BSON/filter driver |
| Tên field trong query | Theo property Java và mapping metadata | **Tên field BSON thật** |
| `@Field("state_code")` | Được converter/query mapper xử lý | Không tự chuyển `"state"` thành `"state_code"` |
| `@MongoId` / `@Id` | Có quy tắc ánh xạ ID | Tự truyền đúng kiểu BSON cho `_id` |
| Custom converters | Được sử dụng trong luồng mapping thích hợp | Không tự áp dụng khi thao tác raw `Document` |
| `@Version` | Có hỗ trợ kiểm soát ở các thao tác phù hợp | Tự quản lý điều kiện và tăng version |
| Auditing / entity callbacks | Hoạt động theo các thao tác entity tương ứng | Không tự chạy cho raw driver CRUD |
| Truy cập lệnh/tùy chọn driver đặc biệt | Có thể hạn chế bởi API mức cao | Linh hoạt hơn |
| Exception translation | Có | `execute` hỗ trợ dịch exception driver phù hợp |
| Transaction | Tham gia nếu cấu hình session/manager phù hợp | Có thể tham gia theo cơ chế session của `execute`, nhưng **không tự tạo transaction** |

### 9.1. Không phải mọi thao tác cần callback

Nếu chỉ cần:

~~~java
template.find(
    Query.query(Criteria.where("state").is("PAID")),
    OrderDocument.class
);
~~~

thì không cần đổi thành:

~~~java
template.execute(OrderDocument.class, collection ->
    collection.find(Filters.eq("state_code", "PAID"))
        .into(new java.util.ArrayList<>())
);
~~~

Cách thứ hai tăng trách nhiệm về BSON, mapping và tài nguyên; chỉ nên chọn khi cần khả năng driver cụ thể hoặc xử lý đặc biệt có lý do.

### 9.2. Không được coi `MongoCollection` là repository tự động

Thực thể Java có thể dùng cả `@Document`, `@Indexed`, `@Version`, converter và callback. Nhưng việc truyền `OrderDocument.class` vào `execute` **chỉ giúp template xác định collection**; nó không khiến mọi operation driver thô trên collection được “nâng cấp” thành thao tác Spring Data entity-aware.

Đây là khác biệt rất quan trọng khi bảo trì một codebase vừa dùng repository vừa có những tác vụ raw callback.

## 10. Exception translation và cách xử lý lỗi

MongoDB Java Driver phát sinh các exception theo hệ thống của driver, ví dụ kết nối thất bại, duplicate key, timeout hoặc quyền truy cập. Khi dùng `MongoTemplate.execute`, Spring Data cố gắng dịch các lỗi MongoDB phù hợp sang **Spring DataAccessException hierarchy** nhờ `MongoExceptionTranslator`.

Ví dụ một service có thể xử lý nhóm lỗi Spring:

~~~java
import org.springframework.dao.DataAccessException;
import org.springframework.dao.DuplicateKeyException;

try {
    template.execute("orders_execute_demo_008", collection -> {
        collection.insertOne(
            new Document("_id", "o801")
                .append("tenant_id", "t01")
                .append("state_code", "NEW")
        );
        return null;
    });
} catch (DuplicateKeyException duplicate) {
    // Đây là ca dự kiến nếu ID o801 đã tồn tại.
    // Tạo phản hồi nghiệp vụ thích hợp.
} catch (DataAccessException dataAccessFailure) {
    // Theo dõi log/metrics và phân loại lỗi database.
}
~~~

**Chỉ chạy ví dụ ghi trên database thử nghiệm.** Không phải mọi lỗi Java do callback tạo ra đều được dịch thành `DataAccessException`: chẳng hạn `NullPointerException` hoặc lỗi logic tùy biến vẫn có thể đi thẳng ra ngoài. Trong vận hành, nên giữ nguyên nguyên nhân gốc cho log/diagnostics, nhưng không lộ chi tiết kết nối hay dữ liệu nhạy cảm cho API public.

Không viết `catch (Exception)` rồi trả kết quả thành công giả. Nếu callback được dùng trong transaction, nuốt exception có thể gây commit trạng thái không đúng mong muốn.

## 11. Session và transaction: `execute` không có nghĩa là atomic

### 11.1. Một callback có thể chứa nhiều thao tác

~~~java
template.execute(
    "orders_execute_demo_008",
    collection -> {
        collection.updateOne(
            Filters.eq("_id", "o801"),
            Updates.set("state_code", "PAID")
        );
        collection.updateOne(
            Filters.eq("_id", "o802"),
            Updates.set("state_code", "PAID")
        );
        return null;
    }
);
~~~

Dù nằm trong **một lambda**, hai lệnh update trên **không tự có tính nguyên tử xuyên hai document**. Nếu lệnh thứ nhất hoàn thành và lệnh thứ hai lỗi, thay đổi thứ nhất có thể đã được commit.

MongoDB bảo đảm tính nguyên tử của một thao tác ghi trên một document; nhiều thao tác hoặc nhiều document cần transaction khi nghiệp vụ yêu cầu all-or-nothing.

### 11.2. Dùng `MongoTransactionManager` khi cần transaction

~~~java
// MongoTransactionConfiguration.java
package com.example.templatecallback;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration(proxyBeanMethods = false)
public class MongoTransactionConfiguration {
    @Bean("mongoTransactionManager")
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
~~~

Trong service Spring:

~~~java
// RawOrderService.java
package com.example.templatecallback;

import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RawOrderService {
    private final MongoTemplate template;

    public RawOrderService(MongoTemplate template) {
        this.template = template;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void markTwoOrdersPaid() {
        template.execute(OrderDocument.class, collection -> {
            collection.updateOne(
                Filters.eq("_id", "o801"),
                Updates.set("state_code", "PAID")
            );
            collection.updateOne(
                Filters.eq("_id", "o802"),
                Updates.set("state_code", "PAID")
            );
            return null;
        });
    }
}
~~~

**Điều kiện áp dụng:** MongoDB phải hỗ trợ transaction (chẳng hạn replica set hoặc sharded cluster theo yêu cầu phiên bản), Spring phải có `MongoTransactionManager` và `MongoTemplate` phải sử dụng **cùng `MongoDatabaseFactory`** với manager. Callback chạy trong ngữ cảnh template được quản lý có thể nhận các đối tượng driver được **session-proxy** để các lệnh có session phù hợp. Lỗi nghiêm trọng làm transaction rollback khi exception được ném ra qua transaction boundary; cần test thực tế.

Trong ví dụ này, không nên tự khởi tạo thêm `MongoClient`/`ClientSession` trong callback hoặc gọi raw `template.getCollection(...)` ngoài cơ chế session rồi mặc nhiên cho rằng các thao tác đó thuộc transaction hiện tại.

### 11.3. `getCollection`/`getDb` và `execute` trong session

Tài liệu Spring Data phân biệt:

- Đối tượng collection/database được cung cấp **qua callback `execute`** có thể là proxy gắn với `ClientSession` của template trong phạm vi transaction/session.
- Các gateway lấy trực tiếp qua `MongoTemplate.getCollection(...)`/`getDb()` không nên mặc nhiên được coi là đã session-proxy; khi làm việc trực tiếp, bạn có thể phải truyền `ClientSession` tường minh theo đúng API driver.

Điều này không có nghĩa mọi call `execute` luôn ở trong transaction. **Phiên transaction phải được thiết lập trước** và đúng scope. Với `@Transactional` theo cơ chế proxy, self-invocation cũng cần được chú ý: gọi một method trong cùng bean không nhất thiết đi qua transaction proxy.

### 11.4. Không phải mọi operation đều hợp lệ trong transaction

MongoDB có những giới hạn về command, thao tác DDL, topology và transaction lifetime. Chẳng hạn không nên đưa việc thay đổi index/collection metadata vào luồng nghiệp vụ transaction nếu không hiểu ràng buộc của server. Việc callback có quyền gọi `createIndex` không bảo đảm command ấy phù hợp trong transaction hiện tại.

## 12. Reactive counterpart: `ReactiveMongoTemplate.execute`

Spring Data MongoDB cũng hỗ trợ callback tương tự trong API reactive:

~~~java
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
~~~

Trong reactive API:

- `execute(ReactiveDatabaseCallback<T>)` trả `Flux<T>`.
- `execute(Class<?>, ReactiveCollectionCallback<T>)` trả `Flux<T>`.
- `execute(String, ReactiveCollectionCallback<T>)` trả `Flux<T>`.

Ví dụ đếm document:

~~~java
Mono<Long> count = reactiveTemplate
    .execute("orders_execute_demo_008", collection ->
        Mono.from(collection.countDocuments(
            Filters.eq("tenant_id", "t01")
        ))
    )
    .next();
// count phát ra 3 nếu dữ liệu thử chưa thay đổi.
~~~

Trong đó `reactiveTemplate` là bean `ReactiveMongoTemplate`, và collection thuộc **reactive streams MongoDB driver**. Việc gọi `execute` chỉ tạo publisher; truy vấn được thực thi khi có subscriber. Không gọi `block()` trong event loop.

Đọc nhiều document:

~~~java
Flux<String> ids = reactiveTemplate.execute(
    OrderDocument.class,
    collection -> Flux.from(
        collection.find(Filters.eq("tenant_id", "t01"))
    ).map(doc -> doc.getString("_id"))
);
~~~

Reactive hỗ trợ composition/backpressure nhưng không biến truy vấn thiếu index thành nhanh hơn. Cần quản lý vòng đời publisher, transaction context (`ReactiveMongoTransactionManager`/`TransactionalOperator`) và việc xử lý lỗi; không chuyển một `MongoCollection` đồng bộ vào reactive chain rồi coi nó là non-blocking.

## 13. Cách tổ chức code để callback dễ bảo trì

Thay vì đặt các lambda raw rải rác trong controller, tạo một service/adapter tập trung:

~~~java
// RawOrderMetricsGateway.java
package com.example.templatecallback;

import com.mongodb.client.model.Filters;
import java.util.Objects;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Component;

@Component
public class RawOrderMetricsGateway {
    private final MongoTemplate template;

    public RawOrderMetricsGateway(MongoTemplate template) {
        this.template = template;
    }

    public long countPaidOrders(String tenantId) {
        Objects.requireNonNull(tenantId, "tenantId");

        Long count = template.execute(
            OrderDocument.class,
            collection -> collection.countDocuments(
                Filters.and(
                    Filters.eq("tenant_id", tenantId),
                    Filters.eq("state_code", "PAID")
                )
            )
        );

        return Objects.requireNonNull(
            count, "MongoDB count callback returned null"
        );
    }
}
~~~

Ưu điểm:

- Hạn chế nơi phải biết tên BSON `tenant_id`/`state_code`.
- Dễ thêm metric, kiểm tra đầu vào và test tích hợp.
- Có một vị trí để thay bằng `MongoTemplate.count(...)` nếu thao tác raw không còn cần thiết.
- Tách rõ quyền truy cập tenant khỏi callback cụ thể; **tenant ID phải được suy ra/xác thực theo người dùng ở tầng gọi**, không tin toàn bộ tham số do client gửi.

Nếu thao tác chỉ là `countDocuments` thông thường, `MongoTemplate.count` vốn đã đáp ứng tốt và có mapping. Service trên là một **ví dụ ranh giới raw driver**, không phải khuyến nghị luôn viết callback chỉ để đếm.

## 14. Kiểm thử callback trên MongoDB thực

Unit test mock `MongoTemplate.execute` có thể kiểm tra cách service xử lý kết quả, nhưng không xác nhận được mapping tên field, MongoDB filter/driver API và write concern. Vì thế nên dùng integration test có MongoDB thật/Testcontainers cho những thao tác raw quan trọng.

### 14.1. Ma trận test

| Ca kiểm thử | Điều cần xác minh |
| --- | --- |
| `execute(DbCallback)` lấy database | Đúng tên database cấu hình trong profile test |
| `execute(OrderDocument.class, ...)` | Chọn đúng collection theo `@Document` |
| Raw query `state_code` | Truy vấn đúng BSON alias, không dùng sai property Java `state` |
| `countDocuments` | Đếm đúng tenant và trạng thái |
| Raw update có điều kiện | `matchedCount`/`modifiedCount` đúng |
| `@Version` với raw writer | Không giả định version được tăng tự động |
| Exception translation | Duplicate key/driver failure được xử lý đúng nhóm lỗi theo cấu hình |
| Cursor iteration | Cursor đóng cả khi duyệt thành công và thất bại |
| Transaction hai document | Rollback khi có lỗi trong topology hỗ trợ |
| Reactive callback | Publisher được subscribe, kết quả/callback đúng |

### 14.2. Test đọc BSON theo đúng alias

Ví dụ kiểm thử sau dựa trên Spring Boot test có MongoDB riêng, không dùng collection của ứng dụng production:

~~~java
package com.example.templatecallback;

import static org.assertj.core.api.Assertions.assertThat;

import com.mongodb.client.model.Filters;
import java.util.Objects;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
class MongoTemplateExecuteCallbackTest {
    @Autowired MongoTemplate template;

    @Test
    void callbackUsesNativeBsonFieldNames() {
        String fixtureId = "fixture-execute-008";
        var collection = template.getDb()
            .getCollection("orders_execute_demo_008");

        collection.deleteOne(Filters.eq("_id", fixtureId));
        try {
            collection.insertOne(
                new Document("_id", fixtureId)
                    .append("tenant_id", "test-tenant")
                    .append("state_code", "PAID")
                    .append("amount_vnd", 123000)
            );

            Long matching = template.execute(
                OrderDocument.class,
                nativeCollection -> nativeCollection.countDocuments(
                    Filters.and(
                        Filters.eq("_id", fixtureId),
                        Filters.eq("tenant_id", "test-tenant"),
                        Filters.eq("state_code", "PAID")
                    )
                )
            );

            Long wrongAlias = template.execute(
                OrderDocument.class,
                nativeCollection -> nativeCollection.countDocuments(
                    Filters.and(
                        Filters.eq("_id", fixtureId),
                        Filters.eq("state", "PAID")
                    )
                )
            );

            assertThat(Objects.requireNonNull(matching))
                .isEqualTo(1L);
            assertThat(Objects.requireNonNull(wrongAlias))
                .isEqualTo(0L);
        } finally {
            collection.deleteOne(Filters.eq("_id", fixtureId));
        }
    }
}
~~~

Đoạn test này minh họa raw filter không tự áp dụng `@Field("state_code")`. Phần fixture tạo/xóa document thật theo ID xác định, vì vậy **chỉ chạy trên database test riêng**. Nó chưa kiểm tra transaction hay exception translation; đó là các test bổ sung riêng cần topology/cấu hình tương ứng.

### 14.3. Kiểm tra transaction rollback

Khi đã cấu hình `MongoTransactionManager` và MongoDB replica set cho test:

1. Chuẩn bị hai document thuộc test.
2. Bắt đầu method `@Transactional` qua Spring proxy.
3. Thực hiện callback cập nhật document thứ nhất, sau đó cố tình ném exception trước cập nhật thứ hai.
4. Xác nhận **document thứ nhất vẫn có giá trị ban đầu** sau rollback.
5. Dọn fixture và kiểm tra không còn tài nguyên/session tồn đọng.

Không dùng MongoDB standalone không hỗ trợ transaction rồi kết luận “callback không rollback”. Phải kiểm tra cơ chế transaction thật sự đã được bật và template sử dụng đúng factory.

## 15. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `execute(OrderDocument.class, ...)` truy cập collection sai | `@Document` hoặc naming strategy khác dự tính | Đối chiếu collection từ metadata và dữ liệu thật |
| Callback `find` trả rỗng dù `template.find` có dữ liệu | Raw filter dùng property Java thay vì field BSON, hoặc sai kiểu `_id` | Kiểm tra `@Field`, `@MongoId` và `mongosh` |
| Raw update tạo field mới ngoài ý muốn | `Updates.set("state", ...)` thay vì `"state_code"` | Kiểm tra document BSON trước/sau, dùng hằng số tên field |
| Raw update không tăng `version` | Driver không áp dụng `@Version` tự động | Thêm predicate/increment thủ công hoặc dùng mapped update |
| Callback tạo list rất lớn gây OOM | `find().into(new ArrayList<>())` không có limit | Dùng limit, batch, cursor hoặc `template.stream` |
| MongoCursor bị rò tài nguyên | Không đóng iterator, trả cursor ra ngoài callback | `try-with-resources`, hoàn tất xử lý trong callback |
| Lỗi driver xuất hiện không đúng nhóm như mong đợi | Không phải lỗi MongoDB được translator hỗ trợ, hoặc callback ném lỗi Java tùy biến | Xem nguyên nhân gốc và cấu hình exception translator |
| `execute` có hai update nhưng chỉ một thành công | Callback không tự tạo transaction | Cấu hình `MongoTransactionManager`/session hoặc bù trừ |
| Trong transaction nhưng raw call không cùng session | Lấy `MongoCollection` trực tiếp ngoài callback, sai factory hoặc sai transaction proxy | Dùng callback trong template/session đúng scope, integration test |
| Reactive callback không thay đổi dữ liệu | Publisher chưa được subscribe | Nối vào reactive chain hoặc dùng `StepVerifier` trong test |
| Index kiểm tra bằng tên tồn tại nhưng query vẫn chậm | Index definition/sort không phù hợp, điều kiện khác selectivity | Xem `listIndexes` đầy đủ và `explain("executionStats")` |
| Database name không như dự kiến | Active profile hoặc URI/database config khác | Dùng `DbCallback.getName` kiểm tra profile và kết nối |

## 16. Bài thực hành

Các bài bên dưới giả định collection `orders_execute_demo_008` ở mục 3 được nạp từ đầu. Mỗi bài ghi có thể làm thay đổi kết quả bài tiếp theo; nên chạy riêng trên môi trường thử nghiệm.

### Bài 1 — Chọn overload đúng

Bạn cần biết tên database ứng dụng đang kết nối. Dùng callback nào?

**Đáp án:** `DbCallback`, ví dụ:

~~~java
String dbName = template.execute(
    (DbCallback<String>) MongoDatabase::getName
);
~~~

Vì công việc thuộc **MongoDatabase**, không cần chọn một collection.

### Bài 2 — Đếm order trong một collection

Tìm số order của tenant `t01` có `state_code: "PAID"` bằng overload theo entity class.

**Đáp án:**

~~~java
Long count = template.execute(
    OrderDocument.class,
    collection -> collection.countDocuments(
        Filters.and(
            Filters.eq("tenant_id", "t01"),
            Filters.eq("state_code", "PAID")
        )
    )
);
// Trên dữ liệu gốc: 1.
~~~

### Bài 3 — Lý do query raw trả rỗng

Entity có `@Field("state_code") private String state;`. Callback viết `Filters.eq("state", "PAID")`. Vì sao không tìm thấy order?

**Đáp án:** callback dùng MongoDB driver trực tiếp, không ánh xạ tên property `state` sang `state_code`. Phải dùng `Filters.eq("state_code", "PAID")` hoặc quay lại `MongoTemplate.find(Query...)` để dùng mapping.

### Bài 4 — Kiểm tra optimistic locking

Một writer dùng `MongoTemplate.save(entity)` với `@Version`. Writer khác dùng `collection.updateOne(Filters.eq("_id", id), Updates.set("state_code", "PAID"))`. Rủi ro gì?

**Đáp án:** writer raw không tăng version và không kiểm tra version; mapped writer có thể không phát hiện thay đổi ngoài luồng. Giải pháp là thống nhất cách ghi hoặc thêm điều kiện version + `$inc` trong raw update.

### Bài 5 — Trả kết quả từ callback

Viết callback lấy số order tenant t01 mà không tải toàn bộ document:

~~~java
Long count = template.execute(
    "orders_execute_demo_008",
    collection -> collection.countDocuments(
        Filters.eq("tenant_id", "t01")
    )
);
~~~

**Giải thích:** dùng `countDocuments` của driver trực tiếp, không gọi `find().into(...)` rồi lấy `size()`. Với fixture gốc, kết quả là 3.

### Bài 6 — Hai update trong cùng lambda

Một callback gọi `updateOne` cho `o801` và `o802`, lệnh thứ hai lỗi. Có bảo đảm cả hai rollback không?

**Đáp án:** Không. Callback không tự tạo transaction. Khi yêu cầu atomic trên nhiều document, cấu hình MongoDB transaction theo topology phù hợp, manager/session đúng và kiểm thử rollback; nếu không dùng transaction, phải có chính sách bù trừ.

### Bài 7 — Reactive callback

`ReactiveMongoTemplate.execute("orders_execute_demo_008", ...)` trả gì và khi nào lệnh chạy?

**Đáp án:** Trả một `Flux<T>`; việc thực thi được hoãn đến lúc có subscriber. Với count là một kết quả duy nhất, có thể dùng `.next()` lấy `Mono<Long>`. Không dùng đồng bộ `MongoCollection` trong callback reactive.

## Tài liệu tham khảo

- [Spring Data MongoDB — Template API / Execute Callbacks](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-api.html): `DbCallback`, `CollectionCallback`, kết quả và dịch ngoại lệ.
- [Spring Data MongoDB — `MongoOperations` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/MongoOperations.html): chữ ký `execute(...)` và API command/query.
- [Spring Data MongoDB — `MongoTemplate` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/MongoTemplate.html): chi tiết overload và behavior.
- [Spring Data MongoDB — Sessions & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): session proxy, `MongoTransactionManager` và phạm vi giao dịch.
- [Spring Data MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html): metadata `@Field`, `@MongoId` và converter.
- [Spring Data MongoDB — Lifecycle Events](https://docs.spring.io/spring-data/mongodb/reference/mongodb/lifecycle-events.html): mapping callbacks/events khi thao tác theo entity.
- [Spring Data MongoDB — ReactiveMongoOperations API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ReactiveMongoOperations.html): reactive callback và `Flux<T>`.
- [MongoDB Java Driver — CRUD Fundamentals](https://www.mongodb.com/docs/drivers/java/sync/current/crud/): driver `MongoCollection`, `Filters`, `Updates` và result.
- [MongoDB Java Driver — Work with Indexes](https://www.mongodb.com/docs/drivers/java/sync/current/indexes/): `listIndexes`/`createIndex` và các tùy chọn index.
