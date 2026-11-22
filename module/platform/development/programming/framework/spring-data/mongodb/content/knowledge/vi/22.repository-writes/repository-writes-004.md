# Phạm vi tất cả document khớp và giới hạn từ khóa phân trang

> **Chương:** Ghi qua repository  
> **Module:** `SPRING_DATA_MONGODB` — kết nối, ánh xạ document và thao tác MongoDB qua `MongoTemplate` hoặc repository; thực hành thiết kế truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu.  
> **Mục tiêu:** Hiểu phạm vi ghi của phương thức repository có `@Update`; phân biệt việc chọn document bằng tên phương thức với việc giới hạn kết quả đọc; nhận diện rằng `Top`, `First` và phân trang **không giới hạn số document được cập nhật**; xây giải pháp an toàn khi nghiệp vụ chỉ muốn sửa N document; kiểm tra số document thực sự thay đổi và xử lý cạnh tranh ghi.

## 1. Vấn đề: `findTop2...` có chắc chỉ sửa hai document?

Giả sử hệ thống có 50 đơn hàng đang ở trạng thái `NEW`. Bạn muốn chỉ chuyển **hai đơn hàng đầu tiên** sang `REVIEW`. Phương thức repository dưới đây trông có vẻ đúng:

~~~java
@Update("{ '$set': { 'state': 'REVIEW' } }")
long findTop2ByState(String state);
~~~

Một người quen với derived query để **đọc** có thể suy luận:

> `Top2` nghĩa là chỉ lấy hai kết quả, nên chỉ hai document bị sửa.

**Suy luận này sai đối với repository update methods của Spring Data MongoDB.** Tài liệu chính thức quy định thao tác `@Update` được áp dụng cho **tất cả document khớp điều kiện truy vấn**; không thể thu hẹp phạm vi cập nhật bằng keyword giới hạn như `Top`/`First` hay bằng phân trang.

Với 50 document `state = NEW`, lời gọi trên có thể cập nhật **cả 50 document**, không phải hai. Giá trị `long` được trả về là số document **đã sửa đổi**, không phải số kết quả đọc được của một trang.

### 1.1. Quy tắc trọng tâm

| Cách truy vấn | `Top/First/Pageable` có giới hạn phạm vi không? | Kiểu tác động |
| --- | --- | --- |
| Derived finder `findTop2ByState(...)` trả `List<OrderDocument>` | **Có**, giới hạn kết quả đọc | Đọc tối đa hai document |
| Derived finder `findByState(..., Pageable)` trả `Page<OrderDocument>` | **Có**, phân trang kết quả đọc | Đọc một cửa sổ document |
| `@Update` đặt trên `findTop2ByState(...)` trả `long` | **Không**, phạm vi update vẫn là tất cả document khớp | Ghi nhiều document |
| `@Update` với ý định dùng `Pageable` để hạn chế N | **Không hỗ trợ dùng phân trang để giới hạn update** | Không dùng làm cơ chế bảo vệ ghi |
| `MongoTemplate.updateFirst(...)` / fluent `.first()` | **Có**, cập nhật tối đa một document | Ghi một document |
| `MongoTemplate.updateMulti(...)` / fluent `.all()` | Cập nhật tất cả document khớp | Ghi nhiều document |

Khác biệt nằm ở **loại thao tác thực thi**, không chỉ tên phương thức. `Top2` là cú pháp giới hạn kết quả cho **finder**; với `@Update`, bộ thực thi update dùng predicate để xác định tập document rồi thực hiện cập nhật trên **toàn bộ tập phù hợp**.

~~~mermaid
flowchart TD
    M["Tên phương thức findTop2ByState"] --> A{"Có @Update?"}
    A -->|Không| R["Truy vấn đọc với giới hạn 2"]
    A -->|Có| U["Lấy predicate: state = NEW"]
    U --> W["Áp update lên tất cả document khớp"]
    W --> N["Trả số document đã sửa"]
~~~

**Kết luận ngắn:** Đừng dùng `Top`/`First`/`Pageable` làm hàng rào an toàn để giới hạn một thao tác `@Update`.

## 2. Tạo dữ liệu mẫu để kiểm chứng

### 2.1. Collection thực hành

Mở `mongosh` và chọn **database học tập biệt lập**; không thực hiện những ví dụ ghi trong bài trên môi trường production:

~~~javascript
use spring_data_mongodb_lab

const orders = db.orders_repository_writes_demo_004;

orders.insertMany([
  {
    _id: "o401",
    tenantId: "t01",
    state: "NEW",
    attempts: 0,
    createdAt: ISODate("2026-10-01T08:00:00Z")
  },
  {
    _id: "o402",
    tenantId: "t01",
    state: "NEW",
    attempts: 1,
    createdAt: ISODate("2026-10-02T08:00:00Z")
  },
  {
    _id: "o403",
    tenantId: "t01",
    state: "NEW",
    attempts: 2,
    createdAt: ISODate("2026-10-03T08:00:00Z")
  },
  {
    _id: "o404",
    tenantId: "t01",
    state: "PAID",
    attempts: 0,
    createdAt: ISODate("2026-10-04T08:00:00Z")
  },
  {
    _id: "o405",
    tenantId: "t02",
    state: "NEW",
    attempts: 0,
    createdAt: ISODate("2026-10-05T08:00:00Z")
  },
  {
    _id: "o406",
    tenantId: "t01",
    state: "CANCELLED",
    attempts: 0,
    createdAt: ISODate("2026-10-06T08:00:00Z")
  }
]);

orders.createIndex({
  tenantId: 1,
  state: 1,
  createdAt: 1,
  _id: 1
});
~~~

Trước khi chạy bất kỳ update nào, tập document có ý nghĩa:

| ID | Tenant | State | Attempts | Có khớp `tenant=t01, state=NEW`? |
| --- | --- | --- | ---: | --- |
| `o401` | t01 | NEW | 0 | Có |
| `o402` | t01 | NEW | 1 | Có |
| `o403` | t01 | NEW | 2 | Có |
| `o404` | t01 | PAID | 0 | Không |
| `o405` | t02 | NEW | 0 | Không |
| `o406` | t01 | CANCELLED | 0 | Không |

Có **ba** order khớp `tenantId = "t01"` và `state = "NEW"`. Dù thêm tên `Top2` vào một phương thức update repository, kết quả mong đợi vẫn là **ba** document bị cập nhật trong tình huống đổi tất cả từ NEW sang REVIEW.

**Lưu ý fixture:** `_id` cố định; chạy lại `insertMany` khi đã có document sẽ báo duplicate key. Các ví dụ update trong những mục khác nhau được xem là **các kịch bản độc lập trên dữ liệu ban đầu**. Hãy dùng collection test mới, hoặc reset có kiểm soát các ID bạn sở hữu, thay vì thực thi tuần tự tất cả ví dụ rồi so với cùng một kết quả kỳ vọng.

### 2.2. Entity Java

Các class trong ví dụ thuộc package `com.example.repositorywrites`, mỗi class đặt trong file tương ứng:

~~~java
// OrderDocument.java
package com.example.repositorywrites;

import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders_repository_writes_demo_004")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;

    private String tenantId;
    private String state;
    private int attempts;
    private Instant createdAt;

    protected OrderDocument() { }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getState() { return state; }
    public int getAttempts() { return attempts; }
    public Instant getCreatedAt() { return createdAt; }
}
~~~

`@MongoId(FieldType.STRING)` giữ `_id` là BSON string, phù hợp với dữ liệu ví dụ. Class không khai báo `@Version` ở phần cốt lõi để số `modifiedCount` phản ánh rõ tác động của `$set`/`$inc`; bài sẽ phân tích `@Version` và optimistic locking ở mục riêng.

Trong domain thực tế, cũng cần kiểm soát tenant/authorization ở **service**. Việc tồn tại trường `tenantId` không khiến Spring Data tự chèn tenant vào mọi query.

## 3. `@Update` tạo phương thức ghi qua repository

Spring Data MongoDB hỗ trợ khai báo cập nhật ngay trên repository bằng annotation `org.springframework.data.mongodb.repository.Update`.

### 3.1. Repository hoàn chỉnh

~~~java
// OrderRepository.java
package com.example.repositorywrites;

import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;
import org.springframework.data.mongodb.repository.Update;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    // Derived finder thuần đọc: Top2 thực sự giới hạn kết quả đọc.
    List<OrderDocument>
        findTop2ByTenantIdAndStateOrderByCreatedAtAscIdAsc(
            String tenantId, String state
        );

    Page<OrderDocument> findByTenantIdAndState(
        String tenantId, String state, Pageable pageable
    );

    // Derived UPDATE: mọi document khớp tenantId và state
    // đều được tăng attempts, không cần đọc entity trước.
    @Update("{ '$inc': { 'attempts': ?2 } }")
    long findAndIncreaseAttemptsByTenantIdAndState(
        String tenantId, String state, int amount
    );

    // Cú pháp dễ gây hiểu lầm: Top2 KHÔNG giới hạn update.
    @Update("{ '$set': { 'state': ?2 } }")
    long findTop2ByTenantIdAndState(
        String tenantId, String currentState, String nextState
    );

    // Tên bắt đầu bằng update cần @Query khai báo predicate.
    @Query("{ 'tenantId': ?0, 'state': ?1 }")
    @Update("{ '$set': { 'state': ?2 } }")
    long updateAllByTenantAndState(
        String tenantId, String currentState, String nextState
    );
}
~~~

Ở interface này:

- `findTop2ByTenantIdAndStateOrderByCreatedAtAscIdAsc` **không có `@Update`**: đây là finder thật sự, chỉ đọc hai document theo thứ tự được quy định.
- `findAndIncreaseAttemptsByTenantIdAndState` có `@Update`: phần `ByTenantIdAndState` tạo predicate; expression `$inc` xác định việc ghi.
- `findTop2ByTenantIdAndState` có `@Update`: dù tên chứa `Top2`, nó vẫn cập nhật **mọi** document khớp.
- `updateAllByTenantAndState` dùng cả `@Query` và `@Update`: filter được chỉ rõ bằng JSON thay vì suy diễn từ tiền tố `update`.

### 3.2. Vì sao tên method cập nhật vẫn bắt đầu bằng `find`?

Trong Spring Data MongoDB, một update method **dựa trên query suy diễn** dùng phần tên `find...By...` để hình thành predicate. Tài liệu chính thức nêu một phương thức bắt đầu bằng `update...`, ví dụ `updateAllByLastname(...)`, chỉ hợp lệ khi kết hợp với `@Query` chỉ rõ điều kiện.

~~~java
// Đúng: suy diễn điều kiện theo derived-query prefix find.
@Update("{ '$inc': { 'attempts': 1 } }")
long findAndIncrementAttemptsByState(String state);

// Đúng: tự cung cấp điều kiện, có thể dùng tên updateAllBy...
@Query("{ 'state': ?0 }")
@Update("{ '$inc': { 'attempts': 1 } }")
long updateAllByState(String state);

// Không nên chỉ đặt tên rồi mong framework tự suy diễn update:
// long updateAllByState(String state);
~~~

Trong repository thật, cần tránh khai báo hai method trùng tên và trùng tham số. Đoạn trên là minh họa quy tắc đặt tên; bạn có thể thêm các method này vào `OrderRepository` nếu không gây xung đột với những method đã có.

### 3.3. `@Update` định nghĩa update, không định nghĩa trang kết quả

~~~java
@Update("{ '$inc': { 'attempts': ?2 } }")
long findAndIncreaseAttemptsByTenantIdAndState(
    String tenantId,
    String state,
    int amount
);
~~~

Gọi:

~~~java
long modified = repository
    .findAndIncreaseAttemptsByTenantIdAndState(
        "t01", "NEW", 1
    );
// Với dữ liệu gốc: modified == 3.
~~~

Predicate BSON tương ứng về ý nghĩa:

~~~javascript
{ tenantId: "t01", state: "NEW" }
~~~

Update BSON:

~~~javascript
{ $inc: { attempts: 1 } }
~~~

Do đó cả `o401`, `o402` và `o403` được tăng `attempts` thêm một. Không có một bước `findTop2` hoặc `PageRequest` nào trong method này để chọn tập con.

## 4. Bẫy `Top` và `First` khi phương thức có `@Update`

### 4.1. Truy vấn đọc với `Top2`

~~~java
List<OrderDocument> earliest = repository
    .findTop2ByTenantIdAndStateOrderByCreatedAtAscIdAsc(
        "t01", "NEW"
    );

// Trên dữ liệu gốc: o401, o402.
~~~

Đây là truy vấn **đọc**; `Top2` thực sự giới hạn số entity trả về. `OrderByCreatedAtAscIdAsc` tạo thứ tự ổn định để hai document đầu tiên có nghĩa xác định.

### 4.2. Cập nhật với `Top2`

~~~java
long modified = repository.findTop2ByTenantIdAndState(
    "t01",
    "NEW",
    "REVIEW"
);

// Kết quả trên dữ liệu gốc: modified == 3, KHÔNG phải 2.
~~~

Điều kiện được suy diễn là `tenantId = t01` và `state = NEW`. Không có giới hạn hai document áp dụng cho thao tác ghi. Sau lời gọi, trạng thái của `o401`, `o402` và `o403` đều thành `REVIEW`.

**Tại sao nguy hiểm?** Nếu bạn đặt tên `findTop100By...` để “giới hạn an toàn 100 bản ghi” trong một công cụ vận hành nhưng thực tế có 1.000.000 document khớp, lệnh `@Update` có thể cập nhật toàn bộ một triệu document đó.

### 4.3. `First` cũng không giới hạn phạm vi

~~~java
// Minh họa bẫy; chỉ thêm vào repository ở môi trường test.
@Update("{ '$set': { 'state': 'REVIEW' } }")
long findFirstByTenantIdAndState(String tenantId, String state);
~~~

Với `@Update`, `First` không bảo đảm “chỉ sửa một document đầu tiên”. Tài liệu chính thức nói rằng **limiting keywords không giới hạn phạm vi cập nhật**. Nếu cần sửa tối đa một document, chọn API có semantics thật sự là **single-document update**, chẳng hạn `MongoTemplate.updateFirst` hoặc fluent `.first()`.

### 4.4. Không đánh đồng tên method với hành vi terminal operation

Một tên như `findFirstBy...` không tự chuyển cơ chế thực thi thành MongoDB `updateOne()` khi gắn `@Update`. Hãy xem method declaration **cùng các annotation** và hợp đồng trả về, không chỉ đọc tên tiếng Anh.

Khi review code, nên đánh dấu những phương thức `@Update` chứa `Top`, `First`, `Page`, `Limited` hoặc `Recent` trong tên. Nếu thật sự muốn giới hạn, cần thay đổi **chiến lược thực thi**, không chỉ đổi tên.

## 5. `Pageable`, `Page`, `Slice` và `Limit` có giới hạn update không?

### 5.1. Phân trang trên finder

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Page<OrderDocument> page = repository.findByTenantIdAndState(
    "t01",
    "NEW",
    PageRequest.of(
        0,
        2,
        Sort.by(Sort.Order.asc("createdAt"),
                Sort.Order.asc("id"))
    )
);

// page.getContent(): o401, o402.
// page.getTotalElements(): 3, khi dữ liệu không đổi.
~~~

Với finder, `Pageable` cung cấp `offset`, `limit` và `sort` cho truy vấn đọc. `Page` còn mang metadata tổng số, có thể cần count query. `Slice` dùng khi chỉ cần biết còn trang tiếp; cả hai vẫn là **cơ chế tiêu thụ kết quả đọc**.

### 5.2. Không áp `Pageable` như một quota ghi

Đối với repository `@Update`:

> Không thể hạn chế số document được cập nhật bằng cách “truyền một trang” hoặc dùng từ khóa giới hạn.

Do đó không viết workflow kiểu “truyền `PageRequest.of(0, 10)` vào update method để chắc chắn chỉ sửa 10 bản ghi”. Tùy chữ ký và phiên bản framework, tổ hợp tham số/kiểu trả về có thể bị từ chối hoặc không được hỗ trợ theo cách bạn dự tính; **dù method được nhận, điều đó không biến phân trang thành giới hạn update an toàn**.

~~~java
// Cách suy luận SAI, không dùng làm hợp đồng an toàn:
// @Update("{ '$set': { 'state': 'REVIEW' } }")
// long findByTenantIdAndState(
//     String tenantId, String state, Pageable pageable);
//
// Không được kỳ vọng pageable giới hạn số document ghi.
~~~

`Pageable`, `Sort`, keyword `Top`/`First` và tham số `Limit` là những công cụ rất hữu ích **cho query method đọc**. Không áp dụng hợp đồng của chúng sang repository update method nếu tài liệu update đã nêu giới hạn riêng.

### 5.3. Tại sao không trả `Page<OrderDocument>` từ update method?

Một lệnh update thường không đọc lại và materialize toàn bộ những entity vừa được sửa. Với `@Update`, kiểu trả về được hỗ trợ là `void` hoặc **kiểu số** cho số document đã sửa. Nó không phải truy vấn trả `Page<OrderDocument>`.

Nếu API muốn trả cả danh sách những order vừa chuyển trạng thái, phải thiết kế **bước đọc hoặc thao tác find-and-update phù hợp**, đồng thời lưu ý dữ liệu có thể thay đổi giữa lúc ghi và đọc.

## 6. Giá trị trả về: số document **modified**, không phải tập ID

Repository update method có thể trả `void`:

~~~java
@Update("{ '$set': { 'state': 'REVIEW' } }")
void findAndMarkReviewByTenantIdAndState(
    String tenantId, String state
);
~~~

hoặc trả `long`:

~~~java
@Update("{ '$set': { 'state': 'REVIEW' } }")
long findAndMarkReviewCountByTenantIdAndState(
    String tenantId, String state
);
~~~

Theo hợp đồng Spring Data MongoDB, kiểu số biểu diễn **số document được sửa đổi**. Với `@Update` dạng `$inc`, mọi document có kiểu số hợp lệ và khớp filter đều thay đổi; số trả về thường trùng với số document khớp trong fixture.

Tuy nhiên, **matched ≠ modified** trong MongoDB:

~~~javascript
// Document o404 đã có state: "PAID".
orders.updateOne(
  { _id: "o404" },
  { $set: { state: "PAID" } }
);
// matchedCount = 1; modifiedCount = 0.
~~~

Vì vậy:

- Giá trị `0` từ một repository update số không tự phân biệt “không có document khớp” với “có document khớp nhưng BSON không thay đổi”.
- Giá trị `3` không cho biết danh sách ID đã sửa, thứ tự sửa hoặc tổng số phần tử mảng bị ảnh hưởng.
- Nếu entity có `@Version` và thao tác mapped auto-increment version, có thể có thay đổi version ngay cả khi phép `$set` nhắc lại giá trị cũ; cần kiểm tra hành vi thực tế với phiên bản Spring Data đang dùng.
- Với write concern không xác nhận, không nên dựa vào số đếm để khẳng định kết quả nghiệp vụ.

### 6.1. Khi cần cả matchedCount và modifiedCount

Sử dụng `MongoTemplate` để nhận `UpdateResult`:

~~~java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

UpdateResult result = template.updateMulti(
    Query.query(
        Criteria.where("tenantId").is("t01")
            .and("state").is("NEW")
    ),
    new Update().set("state", "REVIEW"),
    OrderDocument.class
);

if (!result.wasAcknowledged()) {
    throw new IllegalStateException("Write was not acknowledged");
}

long matched = result.getMatchedCount();
long modified = result.getModifiedCount();
~~~

`MongoTemplate.updateMulti` cũng cập nhật **tất cả document khớp** và trả metadata chi tiết hơn; nó không tự giới hạn N nếu bạn không tự xây chiến lược chọn tập con.

## 7. Kết hợp `@Query` và `@Update` để kiểm soát phạm vi

Tất cả document khớp filter đều là đích cập nhật, vì vậy **viết filter chính xác** quan trọng hơn nhiều so với một keyword giới hạn trong tên.

### 7.1. Truy vấn suy diễn từ property

~~~java
@Update("{ '$inc': { 'attempts': ?2 } }")
long findAndIncreaseAttemptsByTenantIdAndState(
    String tenantId,
    String state,
    int increment
);
~~~

Spring Data suy diễn điều kiện từ `TenantIdAndState`; `?2` lấy tham số thứ ba của method, với chỉ số tham số bắt đầu từ 0.

### 7.2. Truy vấn tường minh bằng `@Query`

~~~java
@Query("{ 'tenantId': ?0, 'state': ?1 }")
@Update("{ '$set': { 'state': ?2 } }")
long updateAllByTenantAndState(
    String tenantId,
    String previousState,
    String nextState
);
~~~

Ở đây tên bắt đầu `updateAllBy...` được phép nhờ `@Query` tường minh. `@Query` xác định **document nào khớp**; `@Update` xác định **thao tác ghi**.

Trong cả hai trường hợp, nếu query khớp 3 order thì update tác động đến **3 order** chứ không phải một trang được suy ra từ tên method.

### 7.3. Tại sao phải đưa tenant vào filter?

Trên fixture, `state=NEW` có bốn order: `o401`, `o402`, `o403`, `o405`. Nếu method chỉ lọc trạng thái:

~~~java
@Update("{ '$set': { 'state': 'REVIEW' } }")
long findAndMarkByState(String state);
~~~

thì lời gọi `findAndMarkByState("NEW")` có thể sửa cả order `o405` thuộc tenant `t02`. Thêm `Top2` **không bảo vệ** khỏi tình huống này.

Đối với hệ thống nhiều tenant, tenant phải được lấy/kiểm chứng từ ngữ cảnh người dùng đã xác thực và **gắn vào mọi predicate ghi**. Đừng coi `tenantId` do client tùy ý cung cấp là đủ bảo đảm phân quyền.

### 7.4. Một điều kiện trạng thái cũng giúp tránh ghi đè

Nếu chỉ order `NEW` được phép chuyển sang `REVIEW`, hãy đưa `state=NEW` vào filter thay vì đọc trạng thái trước rồi update sau:

~~~javascript
orders.updateMany(
  { tenantId: "t01", state: "NEW" },
  { $set: { state: "REVIEW" } }
);
~~~

MongoDB đánh giá điều kiện khi thực thi cập nhật; đối với mỗi document, thao tác ghi được thực hiện nguyên tử. Một client đã chuyển `o402` sang trạng thái khác trước lúc update sẽ không còn khớp `state=NEW`. Điều này không biến cả tập update thành một transaction nguyên tử, nhưng ngăn ghi sai trên từng document ở thời điểm update.

## 8. `@Update` với tham số, SpEL và aggregation pipeline

### 8.1. Binding giá trị trực tiếp

~~~java
@Update("{ '$inc': { 'attempts': ?2 } }")
long findAndIncreaseAttemptsByTenantIdAndState(
    String tenantId, String state, int amount
);
~~~

`?2` được bind từ tham số Java `amount`. Không tự chèn trực tiếp chuỗi input người dùng vào JSON query/update bằng phép nối string, vì sẽ tạo rủi ro cú pháp, sai kiểu dữ liệu và mất kiểm soát lệnh.

### 8.2. Dùng SpEL khi thật sự cần

Spring Data MongoDB hỗ trợ tham số SpEL trong `@Update`, ví dụ tương đương:

~~~java
@Update("{ '$inc': { 'attempts': ?#{[2]} } }")
long findAndIncreaseUsingExpressionByTenantIdAndState(
    String tenantId, String state, int amount
);
~~~

SpEL làm expression linh hoạt hơn nhưng cũng có thể làm phương thức khó review. Nếu chỉ cần bind một tham số đơn giản, `?2` dễ đọc và dễ kiểm thử hơn.

### 8.3. Repository update pipeline

Đối với logic tính giá trị mới từ giá trị cũ, `@Update` có thuộc tính `pipeline`:

~~~java
@Update(pipeline = {
    "{ '$set': { 'attempts': { '$add': [ '$attempts', ?2 ] } } }"
})
long findAndRecalculateAttemptsByTenantIdAndState(
    String tenantId, String state, int amount
);
~~~

Ở đây MongoDB tính `attempts + amount` cho **mỗi document khớp**. Aggregation pipeline update không thay đổi quy tắc phạm vi: nó vẫn áp dụng lên **tất cả document** mà query method chọn.

Khi sử dụng pipeline, cần kiểm tra phiên bản MongoDB hỗ trợ, kiểu BSON đầu vào và quy tắc xử lý missing/null; một giá trị `attempts` không phải số có thể làm expression lỗi. Với phép tăng số đơn giản, `$inc` thường ngắn gọn hơn.

### 8.4. Không tự phát sinh lifecycle events

Tài liệu Spring Data MongoDB nêu rõ: **repository update methods không phát sinh persistence/mapping lifecycle events**. Vì vậy:

- Không giả định `BeforeConvertCallback`, `BeforeSaveCallback` hoặc listener tự chạy giống luồng lưu một entity.
- Không dùng `@Update` làm đường tắt cho logic audit/validation hiện chỉ được cài trong entity callbacks.
- Nếu cần ghi audit/outbox, thiết kế thao tác riêng với transaction hay cơ chế bảo đảm phù hợp.

`@Update` là thao tác **cập nhật document theo query**, không phải “tải tất cả entity, gọi setter, rồi `repository.saveAll`”.

## 9. Khi thực sự chỉ muốn cập nhật tối đa một document

Nếu mục tiêu là “sửa **bất kỳ một** order NEW thỏa tenant”, dùng `MongoTemplate.updateFirst(...)`:

~~~java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

UpdateResult result = template.updateFirst(
    Query.query(
        Criteria.where("tenantId").is("t01")
            .and("state").is("NEW")
    ),
    new Update().set("state", "REVIEW"),
    OrderDocument.class
);
~~~

`updateFirst` sửa tối đa **một document**, nhưng nếu filter khớp nhiều document, **không nên đoán đó là document nào**. Khi cần đúng một ID, thêm điều kiện `id`:

~~~java
Query byIdAndState = Query.query(
    Criteria.where("id").is("o401")
        .and("tenantId").is("t01")
        .and("state").is("NEW")
);

UpdateResult result = template.updateFirst(
    byIdAndState,
    new Update().set("state", "REVIEW"),
    OrderDocument.class
);
~~~

### 9.1. Fluent API với `first()` và `all()`

~~~java
// Tối đa một document:
UpdateResult one = template.update(OrderDocument.class)
    .matching(
        Criteria.where("tenantId").is("t01")
            .and("state").is("NEW")
    )
    .apply(new Update().set("state", "REVIEW"))
    .first();

// Mọi document khớp:
UpdateResult many = template.update(OrderDocument.class)
    .matching(
        Criteria.where("tenantId").is("t01")
            .and("state").is("NEW")
    )
    .apply(new Update().set("state", "REVIEW"))
    .all();
~~~

Hai đoạn trên là **hai nhánh so sánh độc lập**, không chạy nối tiếp trên cùng fixture rồi kỳ vọng nhánh thứ hai vẫn thấy các order NEW. `first()` và `all()` là **terminal operation của fluent API**, thật sự quyết định phạm vi một/nhiều document; chúng khác với keyword `First` được đặt trong tên repository method `@Update`.

### 9.2. Muốn chọn document cũ nhất bằng sort

Yêu cầu “claim order NEW cũ nhất” không chỉ là update một document bất kỳ. Với MongoDB server **trước 8.0**, `MongoTemplate.updateFirst` không hỗ trợ áp dụng sort để chọn document; dùng `findAndModify`:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.FindAndModifyOptions;

Query oldest = Query.query(
    Criteria.where("tenantId").is("t01")
        .and("state").is("NEW")
);
oldest.with(Sort.by(
    Sort.Order.asc("createdAt"),
    Sort.Order.asc("id")
));

OrderDocument claimed = template.findAndModify(
    oldest,
    new Update().set("state", "PROCESSING"),
    FindAndModifyOptions.options().returnNew(true),
    OrderDocument.class
);
~~~

Trên fixture ban đầu, `o401` là order NEW cũ nhất của t01. `findAndModify` tìm-và-sửa một document trong **cùng thao tác**, giảm race giữa bước đọc document đầu tiên rồi ghi sau. Thêm `id` làm tie-breaker khi nhiều document có cùng `createdAt`.

Lưu ý: các phiên bản MongoDB mới hơn có khả năng hỗ trợ sắp xếp cho một số thao tác update one; khi triển khai thực tế, xác nhận phiên bản driver, server và Spring Data. `findAndModify` vẫn hữu ích khi cần trả về document trước/sau update.

## 10. Khi nghiệp vụ chỉ cho phép sửa N document

Ví dụ cụ thể:

> Trong một lần chạy job, chỉ chọn **2 order NEW cũ nhất** của tenant t01 để chuyển sang REVIEW.

Repository `@Update` không có một tùy chọn “limit 2” an toàn cho nghiệp vụ này. Có hai mô hình phổ biến.

### 10.1. Cách A: đọc N ID, sau đó cập nhật tập ID đó

Bước 1 — dùng finder có `Top2`, **chỉ để chọn ID**:

~~~java
List<OrderDocument> selected = repository
    .findTop2ByTenantIdAndStateOrderByCreatedAtAscIdAsc(
        "t01", "NEW"
    );

List<String> ids = selected.stream()
    .map(OrderDocument::getId)
    .toList();
// Dữ liệu gốc: ["o401", "o402"].
~~~

Bước 2 — xây **query ghi với `id IN (...)`**:

~~~java
if (!ids.isEmpty()) {
    Query selectedIds = Query.query(
        Criteria.where("id").in(ids)
            .and("tenantId").is("t01")
            .and("state").is("NEW")
    );

    UpdateResult result = template.updateMulti(
        selectedIds,
        new Update().set("state", "REVIEW"),
        OrderDocument.class
    );

    long modified = result.getModifiedCount();
    // Trên fixture bất biến: modified == 2.
}
~~~

Điểm mấu chốt: giới hạn N được thực hiện ở **bước chọn ID**, và bước ghi bị ràng buộc vào **đúng các ID đã chọn**. Không chỉ truyền `Pageable` vào phương thức `@Update` rồi tin rằng server giới hạn số cập nhật.

#### Có thể tiếp tục ghi qua repository không?

Có thể khai báo một phương thức `@Query` + `@Update` chỉ nhận những ID đã chọn:

~~~java
// Thêm vào OrderRepository nếu cần giữ API ghi qua repository.
@Query("{ 'tenantId': ?0, 'state': ?1, '_id': { '$in': ?2 } }")
@Update("{ '$set': { 'state': ?3 } }")
long updateSelectedIds(
    String tenantId,
    String currentState,
    List<String> selectedIds,
    String nextState
);
~~~

Sử dụng:

~~~java
if (!ids.isEmpty()) {
    long modified = repository.updateSelectedIds(
        "t01", "NEW", ids, "REVIEW"
    );
}
~~~

Trong cách này, thao tác `@Update` vẫn cập nhật **tất cả document khớp filter**, nhưng **filter đã được giới hạn vào danh sách ID cụ thể**. Chính tập ID làm thu hẹp tập kết quả, không phải keyword `Top2` trên update method.

#### Giới hạn của cách A: race giữa đọc và ghi

Chọn ID rồi cập nhật là **hai thao tác khác nhau**:

1. Ở lúc đọc, `o401` và `o402` là hai order NEW cũ nhất.
2. Trước lúc update, writer khác có thể chuyển `o401` sang PAID, hoặc chèn order NEW mới cũ hơn.
3. Query update có `state=NEW` sẽ không sửa `o401` đã đổi trạng thái.
4. Kết quả có thể chỉ sửa **một** order, và không tự chọn order khác bù vào.

Đây là hành vi có thể chấp nhận nếu mục tiêu là “chỉ tác động những order đã được xét chọn”. Nó **không** đảm bảo “luôn claim đúng N order chưa được worker khác lấy” dưới cạnh tranh cao.

Nếu nghiệp vụ cần atomicity theo cả tập hoặc yêu cầu chọn N mới nhất tại một snapshot, phải thiết kế transaction/điều kiện nhất quán phù hợp.

### 10.2. Cách B: lặp `findAndModify` để claim từng document

Với queue xử lý công việc, cách phổ biến là claim **mỗi document bằng một thao tác nguyên tử**:

~~~java
package com.example.repositorywrites;

import java.util.ArrayList;
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.FindAndModifyOptions;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;

@Service
public class OrderClaimService {
    private final MongoTemplate template;

    public OrderClaimService(MongoTemplate template) {
        this.template = template;
    }

    public List<OrderDocument> claimOldest(String tenantId, int limit) {
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("limit must be 1..100");
        }

        List<OrderDocument> claimed = new ArrayList<>();

        for (int i = 0; i < limit; i++) {
            Query query = Query.query(
                Criteria.where("tenantId").is(tenantId)
                    .and("state").is("NEW")
            );
            query.with(Sort.by(
                Sort.Order.asc("createdAt"),
                Sort.Order.asc("id")
            ));

            OrderDocument next = template.findAndModify(
                query,
                new Update().set("state", "PROCESSING"),
                FindAndModifyOptions.options().returnNew(true),
                OrderDocument.class
            );

            if (next == null) {
                break; // Không còn order NEW để claim.
            }
            claimed.add(next);
        }
        return List.copyOf(claimed);
    }
}
~~~

Trong một lần chạy với fixture ban đầu, gọi `claimOldest("t01", 2)` trả `o401` và `o402` đã chuyển sang PROCESSING; `o403` còn NEW.

**Ưu điểm:** điều kiện `state=NEW` và thao tác chuyển trạng thái được thực hiện cùng lúc trên **từng document**. Khi hai worker cùng claim, document đã chuyển sang PROCESSING không còn khớp `state=NEW` của worker còn lại. Đây là mô hình phù hợp hơn cho **claim job** so với “tải trang rồi ghi lại”.

**Giới hạn:** một vòng lặp N lần không tự tạo một transaction nguyên tử cho cả N document. Nếu giữa vòng lặp xảy ra lỗi, những document đã claim trước có thể vẫn giữ trạng thái PROCESSING. Cần timeout/reclaim/lease hoặc retry theo thiết kế queue; transaction là quyết định riêng.

### 10.3. So sánh hai cách giới hạn N

| Tiêu chí | Chọn ID rồi `updateMulti` | Lặp `findAndModify` |
| --- | --- | --- |
| Số document tối đa | Không vượt số ID đã chọn | Không vượt số lần lặp |
| Số round-trip | Một lần đọc + một lần ghi chính | Tối đa N lần tìm-và-sửa |
| Điều kiện trạng thái kiểm tra khi ghi | Có nếu thêm vào query update | Có trong mỗi thao tác atomic |
| Khi một order đổi trạng thái trước lúc ghi | Có thể sửa ít hơn N | Có thể claim order phù hợp tiếp theo |
| Có trả document vừa được sửa? | Cần truy vấn riêng/thiết kế thêm | `findAndModify` có thể trả document |
| Nhiều document all-or-nothing? | Không mặc định | Không mặc định |
| Phù hợp | Batch cập nhật tập đã chọn | Worker queue/claim từng job |

Đừng tối ưu số round-trip bằng cách bỏ kiểm soát điều kiện nghiệp vụ. Với job lớn, có thể dùng batching, checkpoint, index, transaction hoặc cơ chế queue chuyên dụng tùy yêu cầu.

## 11. `@Version` không tự giới hạn phạm vi và không tự bảo vệ mọi thao tác

Giả sử entity có thêm:

~~~java
import org.springframework.data.annotation.Version;

@Version
private Long version;
~~~

`@Version` dùng để hỗ trợ optimistic locking trong các thao tác entity-aware phù hợp. Nhưng một repository update method vẫn là **query update** tác động lên tập document khớp.

### 11.1. Ba việc cần phân biệt

1. **Phạm vi:** query chọn document nào, ví dụ `tenantId=t01 AND state=NEW`.
2. **Version bump:** Spring Data có thể tự tăng version khi mapped update không chỉ định version trong update definition.
3. **Optimistic check:** muốn bảo vệ một phiên bản mà người dùng đã đọc, query phải chứa **giá trị version kỳ vọng**.

Auto-increment version không biến `findTop2By...` thành update tối đa hai document. Nó cũng không bảo đảm query đã có điều kiện version mà client mong muốn.

### 11.2. Ví dụ kiểm tra version kỳ vọng bằng `MongoTemplate`

Với một entity có `@Version`, giả sử order `o401` đang ở version 3:

~~~java
Query query = Query.query(
    Criteria.where("id").is("o401")
        .and("tenantId").is("t01")
        .and("state").is("NEW")
        .and("version").is(3L)
);

UpdateResult result = template.updateFirst(
    query,
    new Update().set("state", "REVIEW"),
    VersionedOrderDocument.class
);

if (result.getMatchedCount() == 0) {
    throw new IllegalStateException(
        "Order missing, changed state, or stale version"
    );
}
~~~

`VersionedOrderDocument` là **biến thể entity minh họa có `@Version` và mapping collection tương ứng**, không phải class đã được định nghĩa ở mục 2.2. Đoạn này tập trung giải thích filter optimistic locking; khi áp dụng cần khai báo entity thật và chuẩn bị fixture có version.

Nếu bạn đã giữ một entity có version 3 từ trước, việc cập nhật bằng query chỉ chứa `_id` **không thể biết** bạn muốn bảo vệ version 3. Trường hợp cập nhật từng aggregate có version, dùng `repository.save(entity)` hoặc lệnh cập nhật có điều kiện version theo thiết kế.

### 11.3. Repository update không chạy entity callback

Không dựa vào `@BeforeSave`/entity callback để tự kiểm tra version, audit hay quyền truy cập cho `@Update`. Tài liệu chính thức nói repository update methods không phát sinh lifecycle events. Các quy tắc quan trọng phải nằm trong filter, update hoặc service/transaction được test.

## 12. Tính nguyên tử: một document khác nhiều document

MongoDB đảm bảo một thao tác ghi trên **một document** là nguyên tử. Nhưng một repository `@Update` có thể cập nhật nhiều document.

~~~text
Repository @Update:
  filter tenant=t01,state=NEW
       |
       +-- o401: cập nhật nguyên tử ở cấp document
       +-- o402: cập nhật nguyên tử ở cấp document
       +-- o403: cập nhật nguyên tử ở cấp document

Không đồng nghĩa o401+o402+o403 cùng commit/rollback như một transaction.
~~~

Vì vậy không suy luận:

> Một lời gọi Java `repository.findAndMark...()` chỉ chạy một lần nên toàn bộ 3 document thay đổi cùng lúc.

Nếu thao tác nhiều document bị gián đoạn, có thể có document đã ghi và document chưa ghi. Nếu yêu cầu all-or-nothing là bắt buộc, cần MongoDB transaction và cấu hình `MongoTransactionManager` phù hợp.

### 12.1. Ví dụ transaction qua service

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReviewBatchService {
    private final OrderRepository repository;

    public ReviewBatchService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public long markAllNewForTenant(String tenantId) {
        return repository.updateAllByTenantAndState(
            tenantId, "NEW", "REVIEW"
        );
    }
}
~~~

Ví dụ trên **chỉ hoạt động như transaction** khi hệ thống có `MongoTransactionManager` được cấu hình, template/repository cùng `MongoDatabaseFactory` và MongoDB chạy trên topology hỗ trợ transaction. Nếu không, chỉ gắn annotation không khiến mọi ghi thành all-or-nothing.

Lưu ý: transaction còn có chi phí lock, tài nguyên, thời gian và retry. Không mặc định bọc một lần cập nhật hàng triệu document trong một transaction dài chỉ vì repository method tác động trên nhiều document.

### 12.2. Idempotency và retry

~~~java
@Update("{ '$set': { 'state': 'REVIEW' } }")
long findAndMarkReviewByTenantIdAndState(
    String tenantId, String state
);

@Update("{ '$inc': { 'attempts': 1 } }")
long findAndIncreaseByTenantIdAndState(
    String tenantId, String state
);
~~~

Nếu cả hai lời gọi được retry sau timeout:

- `$set(state, REVIEW)` thường không đổi giá trị khi thực hiện lại cùng trạng thái (ngoại trừ version/audit hoặc điều kiện khác).
- `$inc(attempts,1)` **không idempotent**: thực hiện lại có thể tăng lần hai.

Khi lượng document khớp lớn, tác động trùng lặp của retry càng nghiêm trọng. Cần thiết kế điều kiện trạng thái, idempotency key hoặc dấu sự kiện/batch để tránh áp lại phép tăng hoặc trừ ngoài ý muốn.

## 13. Chọn index và đo tác động của update diện rộng

Với filter:

~~~javascript
{ tenantId: "t01", state: "NEW" }
~~~

index:

~~~javascript
orders.createIndex({
  tenantId: 1,
  state: 1,
  createdAt: 1,
  _id: 1
});
~~~

có thể hỗ trợ cả tìm document theo tenant/trạng thái và finder sắp xếp theo thời gian. Nhưng index **không làm `Top2` trên update method trở thành giới hạn N**.

### 13.1. Vì sao update nhiều document vẫn tốn kém?

- MongoDB phải tìm mọi document khớp filter.
- Mỗi document có thể phải cập nhật dữ liệu và những index liên quan.
- Write load có thể gây replication lag, contention và tăng độ trễ cho nghiệp vụ khác.
- `$inc` hay pipeline phức tạp có chi phí riêng trên mỗi document.
- Khi filter thiếu tenant hoặc trạng thái, số lượng tác động có thể tăng đột biến.

Nên theo dõi số document modified, thời gian ghi, độ trễ p95/p99, write conflicts, replication, chi phí I/O và sức khỏe collection/index.

### 13.2. Dự tính phạm vi trước khi ghi

~~~javascript
const filter = { tenantId: "t01", state: "NEW" };

const candidates = orders.countDocuments(filter);
print({ candidates });
// Fixture ban đầu: 3.
~~~

Đây là phép kiểm tra quy mô hữu ích trước khi ghi, **không phải cam kết** kết quả update sẽ đúng bằng count: document có thể thay đổi giữa phép đếm và phép cập nhật. Nếu muốn chống update quá số lượng cho phép, phải dùng chiến lược chọn ID/claim như mục 10, không chỉ:

~~~text
if (count <= 2) {
    repository.updateAllBy...();
}
~~~

Hai lệnh rời nhau có race condition. Với tác vụ rủi ro, cần hạn chế quyền truy cập, có dry-run/approval vận hành, ràng buộc lọc chính xác và audit/rollback strategy.

### 13.3. `explain` kiểm tra plan, không thay thế test update

~~~javascript
orders.find({ tenantId: "t01", state: "NEW" })
  .sort({ createdAt: 1, _id: 1 })
  .explain("executionStats");
~~~

Khi tìm hiểu index, xem `winningPlan`, `totalKeysExamined` và `totalDocsExamined`. Đây chỉ là phân tích **bước tìm ứng viên**, không phản ánh toàn bộ chi phí ghi. Dù query find có `limit(2)` và rất nhanh, lệnh `@Update` riêng **vẫn có thể sửa tất cả document khớp**.

## 14. Reactive repository: publisher không phải giới hạn phạm vi

Trong ứng dụng WebFlux, Spring Data MongoDB có `ReactiveMongoRepository`. Một update method kiểu reactive thường dùng publisher trả kết quả số:

~~~java
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import org.springframework.data.mongodb.repository.Update;
import reactor.core.publisher.Mono;

public interface ReactiveOrderRepository
        extends ReactiveMongoRepository<OrderDocument, String> {

    @Update("{ '$inc': { 'attempts': ?2 } }")
    Mono<Long> findAndIncreaseAttemptsByTenantIdAndState(
        String tenantId, String state, int amount
    );
}
~~~

Kết quả `Mono<Long>` được thực thi khi có subscriber; số phát ra biểu diễn số document modified theo hợp đồng update method. **Reactive không thay đổi ngữ nghĩa phạm vi**: mọi document khớp vẫn là mục tiêu.

Nếu muốn chỉ cập nhật một hoặc nhiều document có kiểm soát, dùng `ReactiveMongoTemplate`:

~~~java
Mono<com.mongodb.client.result.UpdateResult> one =
    reactiveTemplate.update(OrderDocument.class)
        .matching(
            Criteria.where("tenantId").is("t01")
                .and("state").is("NEW")
        )
        .apply(new Update().set("state", "REVIEW"))
        .first();

Mono<com.mongodb.client.result.UpdateResult> all =
    reactiveTemplate.update(OrderDocument.class)
        .matching(
            Criteria.where("tenantId").is("t01")
                .and("state").is("NEW")
        )
        .apply(new Update().set("state", "REVIEW"))
        .all();
~~~

Đây là hai nhánh **minh họa độc lập**, không nên subscribe nối tiếp trên một fixture rồi so cùng kết quả ban đầu. Trong reactive transaction, cần `ReactiveMongoTransactionManager`/`TransactionalOperator` phù hợp; không gọi `block()` trong event loop.

## 15. Integration test bắt buộc cho bẫy `Top2`

Nếu chỉ mock `OrderRepository` rồi trả `2`, test sẽ **không phát hiện** Spring Data thực sự gửi update rộng tới MongoDB. Cần integration test trên MongoDB thật (chẳng hạn Testcontainers) để kiểm chứng:

1. Có **ba** document cùng tenant/state khớp.
2. Phương thức `@Update` có tên `findTop2...` trả số sửa đổi **3**.
3. Sau thao tác, cả ba document đều đổi state.
4. Document thuộc tenant khác không đổi.
5. Finder `Top2` không có `@Update` thực sự chỉ trả hai document.

### 15.1. Test triển khai với `@DataMongoTest`

Ví dụ chạy trong một ứng dụng Spring Boot đã cấu hình **MongoDB test riêng**:

~~~java
package com.example.repositorywrites;

import static org.assertj.core.api.Assertions.assertThat;

import com.mongodb.client.model.Filters;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
class RepositoryUpdateScopeTest {
    @Autowired MongoTemplate template;
    @Autowired OrderRepository repository;

    @Test
    void topKeywordDoesNotLimitRepositoryUpdate() {
        List<String> ids = List.of(
            "fixture-rw004-a",
            "fixture-rw004-b",
            "fixture-rw004-c",
            "fixture-rw004-other"
        );

        var collection = template.getDb()
            .getCollection("orders_repository_writes_demo_004");

        collection.deleteMany(Filters.in("_id", ids));
        try {
            collection.insertMany(List.of(
                new Document("_id", ids.get(0))
                    .append("tenantId", "test-tenant-004")
                    .append("state", "NEW")
                    .append("attempts", 0),
                new Document("_id", ids.get(1))
                    .append("tenantId", "test-tenant-004")
                    .append("state", "NEW")
                    .append("attempts", 0),
                new Document("_id", ids.get(2))
                    .append("tenantId", "test-tenant-004")
                    .append("state", "NEW")
                    .append("attempts", 0),
                new Document("_id", ids.get(3))
                    .append("tenantId", "another-tenant-004")
                    .append("state", "NEW")
                    .append("attempts", 0)
            ));

            long modified = repository.findTop2ByTenantIdAndState(
                "test-tenant-004", "NEW", "REVIEW"
            );

            assertThat(modified).isEqualTo(3L);

            long reviewed = collection.countDocuments(
                Filters.and(
                    Filters.in("_id", ids.subList(0, 3)),
                    Filters.eq("state", "REVIEW")
                )
            );
            assertThat(reviewed).isEqualTo(3L);

            Document other = collection.find(
                Filters.eq("_id", ids.get(3))
            ).first();
            assertThat(other).isNotNull();
            assertThat(other.getString("state")).isEqualTo("NEW");
        } finally {
            collection.deleteMany(Filters.in("_id", ids));
        }
    }
}
~~~

Test tạo và dọn **đúng bốn ID fixture** trong database test biệt lập. Không dùng ID này chung với test khác đang chạy song song. Test chỉ xác nhận hành vi `@Update` trong kết hợp Spring Data MongoDB + MongoDB thật; nó không thay thế kiểm thử quyền tenant, transaction hoặc hiệu năng trên hàng triệu document.

### 15.2. Thêm test đối chứng finder `Top2`

Trước khi thay đổi state, hãy chèn ba document có cùng tenant/state nhưng khác `createdAt`, gọi:

~~~java
List<OrderDocument> two = repository
    .findTop2ByTenantIdAndStateOrderByCreatedAtAscIdAsc(
        "test-tenant-004", "NEW"
    );
assertThat(two).hasSize(2);
~~~

Đoạn này chỉ có ý nghĩa khi fixture đã khai báo `createdAt` hợp lệ và test chưa thực hiện update. Nếu chạy trên dữ liệu fixture mục 15.1 (thiếu `createdAt`), nó vẫn có thể giới hạn hai kết quả nhưng không minh họa được thứ tự theo ngày. Để test sort, bổ sung BSON Date vào từng document khi insert, dùng dữ liệu có timestamp khác nhau và kiểm tra đúng ID.

### 15.3. Ma trận test cho hệ thống thực

| Tình huống | Điều cần xác minh |
| --- | --- |
| Derived `@Update` không dùng `Top` | Mọi document khớp bị sửa |
| `@Update` có `Top2` | Vẫn sửa mọi document khớp, không phải hai |
| Finder `Top2` không có `@Update` | Chỉ đọc tối đa hai document |
| Finder nhận `Pageable` | Kết quả đọc đúng trang, không ảnh hưởng đến update riêng |
| Method update kiểu số | Trả số modified, không phải danh sách ID |
| Update không có document khớp | Không chèn mới; số sửa đổi bằng 0 |
| `@Query` + `@Update` | Filter chính xác theo tenant/state/ID |
| Chọn hai ID rồi update | Chỉ tập ID đó là ứng viên ghi |
| Giữa lúc chọn ID và update có thay đổi | Không sửa document không còn khớp trạng thái |
| `findAndModify` claim hai lần | Mỗi lần lấy một document, không claim trùng |
| `$inc` retry | Phát hiện nguy cơ áp update hai lần |
| Lifecycle callbacks | Không giả định callback entity chạy từ repository update |
| `@Version` | Không suy diễn optimistic lock từ một query thiếu version |
| Reactive `@Update` | Publisher được subscribe; phạm vi vẫn là all-match |

## 16. Những sai lầm thường gặp

| Triệu chứng / giả định | Vì sao sai | Hướng xử lý |
| --- | --- | --- |
| `findTop2...` có `@Update` chỉ sửa hai document | `Top2` giới hạn finder, không giới hạn repository update | Đọc hai ID rồi update theo ID, hoặc `findAndModify` từng record |
| `findFirst...` có `@Update` sẽ thành `updateOne` | Limiting keyword không thay cơ chế all-match update | Dùng `MongoTemplate.updateFirst`/fluent `first()` |
| Truyền `Pageable` sẽ hạn chế số update | Không hỗ trợ phân trang làm scope limiter của `@Update` | Không dựa vào `Pageable`; chuyển chiến lược ghi |
| `Page<OrderDocument>` là kết quả tự nhiên của `@Update` | Update trả `void` hoặc số modified, không tải một page entity | Tách read/write, chọn API phù hợp |
| Tên `updateAllBy...` tự tạo derived predicate | Tiền tố update không phải schema derived update mặc định | Thêm `@Query` tường minh cùng `@Update` |
| `long modified=0` có nghĩa không có document khớp | Có thể có document khớp nhưng không thay đổi | Dùng `MongoTemplate.UpdateResult` và kiểm dữ liệu |
| Bỏ tenant vì “chỉ update Top2” | Query có thể sửa document tenant khác | Gắn tenant được xác thực vào mọi predicate ghi |
| Gọi `repository.saveAll(...)` tương đương `@Update` | Save có mapping, callbacks/version semantics khác | Chọn API theo yêu cầu nhất quán và tác dụng phụ |
| `@Update` sẽ tự gọi entity audit callback | Repository update không phát persistence/mapping events | Tạo logic audit/transaction riêng |
| Có `@Version` nên mọi writer stale bị từ chối | Query update không biết version client đã xem nếu không ràng buộc | Dùng query có expected version hoặc save entity đúng cơ chế |
| Đếm trước bằng `countDocuments` đủ bảo đảm tối đa N | Có race giữa count và update | Chọn ID rồi update, hoặc atomic claim |
| Một repository method update nhiều document là transaction | Multi-update không tự tạo all-or-nothing | Cấu hình transaction hoặc chia batch với retry |
| Update không có index nhưng test nhỏ chạy nhanh | Workload lớn cần quét nhiều document | Thiết kế index, đo query plan và thời gian ghi |
| Reactive `Mono<Long>` chỉ có một kết quả nên sửa một document | Publisher một kết quả là **số modified**, không phải số document phạm vi | Kiểm filter/loại thao tác thực tế |

## 17. Quy trình review an toàn cho repository write methods

Trước khi approve một phương thức `@Update`, thực hiện:

1. **Xác định operator:** `$set`, `$inc`, `$push`, pipeline hay thao tác khác? Có idempotent không?
2. **Đọc predicate:** các property sau `By` hoặc JSON `@Query` sẽ khớp những document nào?
3. **Không tin limiting keyword:** `Top`, `First`, `Pageable` không giới hạn phạm vi của repository update.
4. **Rà soát tenant/authorization:** filter có đủ các ràng buộc quyền và phạm vi nghiệp vụ không?
5. **Đánh giá số lượng:** trên dữ liệu thực tế có thể khớp bao nhiêu document; có cần quota N không?
6. **Nếu cần N:** chọn ID rồi update có điều kiện, hoặc dùng `findAndModify` claim từng record.
7. **Xem kiểu trả về:** `void` hay số modified; khi cần matched/modified riêng, dùng `MongoTemplate.UpdateResult`.
8. **Kiểm tra version/audit:** thao tác query-based có bỏ qua callback hoặc thiếu expected version không?
9. **Đánh giá transaction/retry:** update nhiều document có thể bị gián đoạn; `$inc` không retry mù.
10. **Đo và test:** integration test với **nhiều document khớp hơn N trong tên method**, kiểm đúng số đã sửa và dữ liệu ngoài phạm vi không đổi.

## 18. Bài thực hành

Các bài dưới đây giả định collection `orders_repository_writes_demo_004` đang ở trạng thái ban đầu của mục 2. Từng bài là một kịch bản độc lập.

### Bài 1 — Đọc hay ghi?

Cho hai phương thức:

~~~java
List<OrderDocument> findTop2ByTenantIdAndStateOrderByCreatedAtAscIdAsc(
    String tenantId, String state
);

@Update("{ '$set': { 'state': 'REVIEW' } }")
long findTop2ByTenantIdAndState(
    String tenantId, String state
);
~~~

**Câu hỏi:** Với `("t01", "NEW")`, mỗi phương thức ảnh hưởng bao nhiêu order?

**Đáp án:** finder trả **hai** order `o401`, `o402`; update method sửa **cả ba** order `o401`, `o402`, `o403`. Tên `Top2` không giới hạn số document update.

### Bài 2 — `Pageable` có cứu được không?

Một developer thêm `PageRequest.of(0, 2)` vào phương thức update để đặt giới hạn an toàn. Có đúng không?

**Đáp án:** Không. Theo hợp đồng MongoDB repository update methods, pagination/limiting keywords **không dùng để giới hạn phạm vi update**. Dùng finder để chọn ID hoặc thao tác single-document update/claim riêng.

### Bài 3 — Đếm số document modified

Gọi:

~~~java
long modified = repository
    .findAndIncreaseAttemptsByTenantIdAndState(
        "t01", "NEW", 1
    );
~~~

**Đáp án:** Với fixture ban đầu, `modified=3`. `attempts` của `o401`, `o402`, `o403` lần lượt từ 0/1/2 thành 1/2/3; `o405` thuộc tenant khác không bị thay đổi.

### Bài 4 — Vì sao phải có `@Query`?

~~~java
@Query("{ 'tenantId': ?0, 'state': ?1 }")
@Update("{ '$set': { 'state': ?2 } }")
long updateAllByTenantAndState(
    String tenantId, String currentState, String nextState
);
~~~

**Đáp án:** `@Query` định nghĩa predicate vì tên method bắt đầu bằng `update`, không theo derived-query prefix `find`. `@Update` định nghĩa update operator. Mọi document khớp query đều là ứng viên sửa.

### Bài 5 — Chọn N order cũ nhất

Yêu cầu chỉ sửa hai order NEW cũ nhất của t01. Nêu hai lựa chọn.

**Đáp án tham khảo:** (1) Finder `Top2` theo `createdAt ASC, id ASC` để lấy ID, sau đó `updateMulti` với `id IN IDs`, tenant và state. (2) Lặp `findAndModify` với sort ổn định để claim từng document nguyên tử. Cả hai đều khác việc dùng `Top2` trực tiếp trên `@Update`.

### Bài 6 — Race giữa đọc và ghi

Bạn đã chọn `o401`/`o402`, nhưng một writer khác vừa chuyển `o401` từ NEW sang PAID. Query ghi nên có gì?

**Đáp án:** Giữ `id IN ["o401","o402"]` **và** `state=NEW` cùng tenant. Khi đó `o401` không bị ghi đè; có thể chỉ `o402` được sửa. Nếu workflow bắt buộc đủ hai order, thiết kế lại bằng atomic claim hoặc transaction tùy yêu cầu.

### Bài 7 — Retry `$inc`

Một update repository tăng `attempts` cho toàn bộ order NEW của t01, request bị timeout. Có nên retry ngay?

**Đáp án:** Không retry mù `$inc`. Lần đầu có thể đã cập nhật cả ba, lần sau có thể tăng thêm lần nữa. Cần idempotency/event marker hoặc điều kiện trạng thái đủ mạnh để biết thao tác đã áp dụng.

### Bài 8 — Bảo vệ tenant

Vì sao method `findTop2ByState("NEW")` gắn `@Update` không an toàn trong hệ thống nhiều tenant?

**Đáp án:** Vì nó có thể sửa **tất cả order NEW của mọi tenant**, không chỉ hai order hoặc tenant của người gọi. Thêm tenant được xác thực vào query, kiểm tra quyền và đừng dùng `Top2` thay cho filter bảo mật.

### Bài 9 — `@Version` và optimistic lock

Một client đã xem order tại version 3. Phương thức `@Update` chỉ lọc `_id`. Có bảo vệ chắc chắn client khỏi cập nhật stale không?

**Đáp án:** Không. Phải đưa version kỳ vọng vào predicate hoặc dùng cơ chế lưu entity có optimistic locking phù hợp; việc framework có thể tự tăng version không đồng nghĩa đã so sánh đúng version cũ.

### Bài 10 — Test tối thiểu phát hiện lỗi nguy hiểm

Muốn chứng minh `Top2` không giới hạn `@Update`, test phải tạo bao nhiêu document khớp?

**Đáp án:** **Hơn hai document**, ví dụ ba. Nếu test chỉ có đúng hai document, cả giả định sai “Top2 chỉ cập nhật hai” lẫn hành vi thực “cập nhật tất cả ba trở xuống” đều có thể cho kết quả như nhau và che giấu lỗi.

## Tài liệu tham khảo

- [Spring Data MongoDB — MongoDB-specific Data Manipulation Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/modifying-methods.html): hợp đồng `@Update`, mọi document khớp, không giới hạn bằng `Page`/limiting keywords, kiểu trả về số modified, cú pháp `@Query` + `@Update` và không phát lifecycle events.
- [Spring Data Commons — Defining Query Methods](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html): `Top`/`First`, `Pageable`, `Page`, `Slice`, `Limit` và cách derived finder giới hạn kết quả đọc.
- [Spring Data MongoDB — MongoDB-specific Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html): finder, derived query, phân trang và query parameters.
- [Spring Data MongoDB — Saving, Updating, and Removing Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): `updateFirst`, `updateMulti`, fluent `first()/all()`, `findAndModify`, version và `UpdateResult`.
- [Spring Data MongoDB — Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): session, `MongoTransactionManager` và phạm vi transaction.
- [MongoDB Manual — Update Documents](https://www.mongodb.com/docs/manual/tutorial/update-documents/): `updateOne`, `updateMany` và số document tác động.
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/): tính nguyên tử theo document, giới hạn multi-document writes và transaction.
- [MongoDB Manual — Indexing Strategies](https://www.mongodb.com/docs/manual/applications/indexes/): lựa chọn index theo filter và sort.
