# existsById, count và ý nghĩa kiểm tra trước khi ghi

## 1. Tình huống: kiểm tra trước rồi mới tạo bản ghi

Trong chương **Repository CRUD** của **Spring Data MongoDB**, hai thao tác thường xuất hiện trước một lệnh ghi là `existsById(...)` và `count()`. Ví dụ một dịch vụ đăng ký thành viên cần trả lời:

- Mã đăng ký `reg-101` đã có trong MongoDB chưa?
- Hiện có bao nhiêu đăng ký ở trạng thái `ACTIVE`?
- Nếu mã chưa tồn tại, liệu có thể gọi `save(...)` để chắc chắn tạo một bản ghi mới?
- Nếu số bản ghi hiện tại nhỏ hơn hạn mức, liệu có thể cho thêm một đăng ký mới?

Hai câu hỏi đầu có thể giải quyết bằng phương thức repository; hai câu sau liên quan đến **tính đúng đắn khi nhiều yêu cầu chạy đồng thời**. Một kết quả đọc phản ánh dữ liệu tại thời điểm thực thi truy vấn, nhưng **không khóa dữ liệu cho lần ghi diễn ra sau đó**.

Mục tiêu của bài:

1. Hiểu `existsById`, `count`, các phương thức đếm theo điều kiện và chi phí truy vấn.
2. Biết khi nào kiểm tra trước khi ghi là hữu ích và khi nào nó tạo cảm giác an toàn giả.
3. Phân biệt `save`, `insert`, unique index và cập nhật có điều kiện.
4. Áp dụng optimistic locking, compare-and-set và reservation để bảo vệ bất biến nghiệp vụ.
5. Kiểm thử những tình huống trùng khóa, ghi đồng thời và đếm sai khi chạy song song.

Các ví dụ dùng Java 17+, Spring Boot 3.x, Spring Data MongoDB 4.x, MongoDB Java Sync Driver và một database MongoDB thực. Cách ánh xạ ID, xử lý version và câu lệnh driver cụ thể cần được xác minh theo phiên bản của dự án.

## 2. Repository cung cấp những phép kiểm tra nào?

`MongoRepository<T, ID>` kế thừa các thao tác CRUD cơ bản từ Spring Data repository infrastructure. Với một repository quản lý entity `Registration`, ta có thể dùng:

| Phương thức | Câu hỏi trả lời | Kiểu kết quả | Giới hạn ý nghĩa |
|---|---|---|---|
| `existsById(id)` | Có document với ID này tại thời điểm truy vấn không? | `boolean` | Không bảo đảm ID sẽ vẫn tồn tại hoặc còn trống ở lần ghi sau |
| `count()` | Có bao nhiêu document trong phạm vi repository? | `long` | Không phải lệnh đặt chỗ hoặc khóa hạn mức |
| `countByStatus(status)` | Có bao nhiêu document thỏa điều kiện? | `long` | Kết quả có thể thay đổi ngay sau khi đếm |
| `existsByEmailKey(emailKey)` | Có document thỏa business key này không? | `boolean` | Không thay thế unique index |
| `findById(id)` | Lấy nội dung một document theo ID | `Optional<T>` | Đọc dữ liệu nhiều hơn khi chỉ cần tồn tại |
| `findAllById(ids)` | Tải nhiều document theo tập ID | `Iterable<T>` | Không dùng thay cho count/existence khi không cần dữ liệu |

Trong một ứng dụng thông thường, `existsById` có thể được thực thi thành truy vấn kiểm tra tồn tại ở MongoDB; `count` có thể được thực thi bằng cơ chế đếm tài liệu phù hợp với phiên bản Spring Data/driver. Không nên dựa vào giả định cố định rằng mọi phiên bản đều tạo đúng một lệnh BSON cụ thể; dùng MongoDB command monitoring, profiler hoặc test truy vấn thực tế để xác minh khi cần tối ưu.

Vì `_id` có unique index mặc định, kiểm tra tồn tại **theo ID** thường có đường truy cập hiệu quả. Với `countByStatus` hoặc `existsByEmailKey`, hiệu năng phụ thuộc index và số tài liệu cần kiểm tra.

## 3. Mô hình Java và repository làm ví dụ

Giả sử mỗi đăng ký có ID do ứng dụng cấp, email đã chuẩn hóa và trạng thái đăng ký. Chọn `@MongoId(FieldType.STRING)` để bảo đảm ID Java dạng chuỗi được ghi đúng kiểu **BSON String**, kể cả khi nội dung trông giống chuỗi ObjectId.

**Registration.java**

~~~java
package com.example.registration;

import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "registrations")
public class Registration {
    @MongoId(FieldType.STRING)
    private String id;

    @Version
    private Long version;

    private String emailKey;
    private String status;

    protected Registration() {
        // Phục vụ materialization qua Spring Data.
    }

    public Registration(String id, String emailKey, String status) {
        this.id = id;
        this.emailKey = emailKey;
        this.status = status;
    }

    public String getId() { return id; }
    public Long getVersion() { return version; }
    public String getEmailKey() { return emailKey; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
}
~~~

**RegistrationRepository.java**

~~~java
package com.example.registration;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface RegistrationRepository
        extends MongoRepository<Registration, String> {

    long countByStatus(String status);

    boolean existsByEmailKey(String emailKey);
}
~~~

Với starter `spring-boot-starter-data-mongodb`, cấu hình URI và package scanning phù hợp, Spring Data tạo implementation cho repository ở runtime. Tầng nghiệp vụ có thể inject interface mà không viết class triển khai CRUD.

Một document minh họa sau khi được lưu:

~~~json
{
  "_id": "reg-101",
  "version": 0,
  "emailKey": "lan@example.test",
  "status": "ACTIVE"
}
~~~

Giá trị version khởi tạo và metadata khác có thể phụ thuộc đường ghi và cách Spring Data ánh xạ; hình dạng trên chỉ minh họa. `@Version` được dùng ở phần xử lý cập nhật đồng thời, không phải công cụ thay thế định danh.

### 3.1. Truy vấn số lượng và trạng thái tồn tại

~~~java
package com.example.registration;

import org.springframework.stereotype.Service;

@Service
public class RegistrationReadService {
    private final RegistrationRepository registrations;

    public RegistrationReadService(RegistrationRepository registrations) {
        this.registrations = registrations;
    }

    public boolean hasRegistration(String id) {
        return registrations.existsById(id);
    }

    public long totalRegistrations() {
        return registrations.count();
    }

    public long activeRegistrations() {
        return registrations.countByStatus("ACTIVE");
    }
}
~~~

`existsById("reg-101")` trả về `true` nếu truy vấn thấy document tương ứng, `false` nếu không. `count()` đếm document trong collection liên quan, **không** cộng số phần tử trong mỗi document. `countByStatus("ACTIVE")` giới hạn theo giá trị field `status`. Nếu một số đăng ký mang trạng thái `DELETED` hoặc `INACTIVE`, chúng vẫn nằm trong `count()` trừ khi đã bị xóa vật lý; điều này ảnh hưởng trực tiếp tới cách đặt tên và định nghĩa thống kê.

## 4. Kiểm tra trước khi ghi: vấn đề TOCTOU

Mã dưới đây thường có vẻ hợp lý:

~~~java
public Registration createIfAbsent(Registration input) {
    if (registrationRepository.existsById(input.getId())) {
        throw new IllegalStateException("ID đã được sử dụng");
    }
    return registrationRepository.save(input);
}
~~~

Tuy nhiên, **không nên dùng mẫu trên để bảo đảm tính duy nhất**. Nó có hai vấn đề:

1. `existsById` và `save` là hai thao tác riêng. Một request khác có thể ghi document sau khi ta kiểm tra nhưng trước khi ta lưu.
2. `save` có ý nghĩa **lưu trạng thái entity**, có thể thực hiện insert hoặc update tùy ID, metadata version và trạng thái tồn tại. Nó không phải API diễn đạt rõ “chỉ tạo mới, từ chối nếu khóa đã có”.

Giả sử hai request A và B cùng muốn tạo `reg-101`:

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant DB as MongoDB
    participant B as Request B
    A->>DB: existsById("reg-101")
    DB-->>A: false
    B->>DB: existsById("reg-101")
    DB-->>B: false
    A->>DB: Ghi reg-101
    DB-->>A: thành công
    B->>DB: Ghi reg-101
    DB-->>B: trùng khóa hoặc xung đột cập nhật
~~~

Thứ tự cụ thể và lỗi trả về phụ thuộc lệnh ghi cuối cùng, schema và optimistic locking. Điểm bất biến: **cả A và B có thể cùng đọc thấy “chưa tồn tại”**. Đây là lỗi *time-of-check to time-of-use* (**TOCTOU**).

Một phép kiểm tra trước không tạo transaction hoặc khóa tự động, kể cả khi code Java trông tuần tự trong mỗi request. Trong hệ thống chạy nhiều instance, dùng `synchronized` trên một object Java cũng không giải quyết tranh chấp giữa các process.

### Khi kiểm tra trước vẫn có giá trị

- **Trải nghiệm người dùng:** cảnh báo sớm mã hoặc email đã có trước khi gửi form; kết quả chỉ có tính tham khảo.
- **Tránh tác vụ tốn kém:** kiểm tra trước để giảm khả năng phải xử lý các bước không cần thiết, miễn vẫn có bảo vệ tại thời điểm ghi.
- **Quan sát và phân nhánh:** đếm số bản ghi hiện tại để hiển thị dashboard hoặc quyết định cách trình bày.
- **Thao tác chỉ đọc:** endpoint kiểm tra sự tồn tại hoặc trả về tổng số khi độ mới của số liệu không phải ràng buộc tuyệt đối.

Nếu kết quả là điều kiện quyết định **không được vi phạm** (khóa duy nhất, hạn mức đăng ký, trừ tồn kho, chuyển trạng thái đúng một lần), phải chuyển kiểm tra vào **bất biến được bảo vệ ở phía database** hoặc quy trình transaction/đồng bộ phù hợp.

## 5. Tạo mới an toàn: insert và unique index

Khi muốn “tạo document mới, thất bại nếu ID đã tồn tại”, `MongoTemplate.insert(...)` diễn đạt ý định rõ ràng hơn `save(...)`:

~~~java
package com.example.registration;

import java.util.Locale;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class RegistrationCreateService {
    private final MongoTemplate mongo;

    public RegistrationCreateService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public Registration create(
            String id, String email, String initialStatus) {
        String emailKey = canonicalEmail(email);
        Registration registration =
                new Registration(id, emailKey, initialStatus);

        // MongoDB từ chối insert nếu _id đã tồn tại.
        return mongo.insert(registration);
    }

    private static String canonicalEmail(String email) {
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("Email không được rỗng");
        }
        return email.trim().toLowerCase(Locale.ROOT);
    }
}
~~~

Hàm canonicalization chỉ là **quy ước ví dụ**, không phải quy tắc chuẩn hóa email phổ quát. Trong ứng dụng thật phải xác định rõ chính sách Unicode, case sensitivity, giới hạn định dạng và tình huống hai địa chỉ có thực sự cùng identity hay không.

MongoDB có unique index trên `_id` theo mặc định, nên hai lệnh `insert` cùng ID không thể đồng thời tạo hai document thành công trong cùng collection. Spring Data thường chuyển lỗi khóa trùng thành `DuplicateKeyException`. Tầng HTTP có thể ánh xạ trường hợp này thành **409 Conflict**, nhưng cần phân biệt loại xung đột trong nghiệp vụ thay vì để lỗi database lộ trực tiếp ra client.

### 5.1. Business key cần unique index riêng

ID khác nhau vẫn có thể cùng email:

~~~json
{ "_id": "reg-101", "emailKey": "lan@example.test", "status": "ACTIVE" }
{ "_id": "reg-102", "emailKey": "lan@example.test", "status": "ACTIVE" }
~~~

Nếu nghiệp vụ yêu cầu **mỗi emailKey chỉ có một đăng ký**, tạo unique index trên trường đó:

~~~javascript
db.registrations.createIndex(
  { emailKey: 1 },
  { unique: true, name: "uq_registrations_email_key" }
);
~~~

`existsByEmailKey(emailKey)` chỉ kiểm tra, còn **unique index** là ràng buộc được MongoDB thực thi khi ghi. Nếu dữ liệu đã có duplicate, phải xử lý trước khi tạo index. Khi có multi-tenant, có thể cần unique index ghép (`tenantId`, `emailKey`); phải xác định rõ phạm vi duy nhất theo nghiệp vụ.

Với field tùy chọn hoặc field có giá trị `null`/thiếu, unique index cần được thiết kế cẩn thận, có thể dùng **partial index** nếu chỉ yêu cầu duy nhất cho các document thỏa điều kiện. Không nên tạo index unique chỉ để “an toàn hơn” mà chưa xác định semantics của dữ liệu thiếu.

### 5.2. Có cần existsById trước insert không?

Không cần để bảo đảm ID duy nhất. Có thể chủ động kiểm tra để trả lỗi sớm, nhưng **insert/unique index vẫn là lớp bảo vệ cuối**:

~~~java
// Một kiểm tra gợi ý cho UX, có thể bỏ.
if (repository.existsById(id)) {
    return "Mã có vẻ đã được sử dụng";
}

// Trạng thái có thể đã thay đổi: vẫn phải chấp nhận DuplicateKeyException.
mongo.insert(new Registration(id, emailKey, "ACTIVE"));
~~~

Nếu request gửi đi lặp sau khi client timeout, việc nhận duplicate không đủ để biết **yêu cầu cũ đã thành công hay là xung đột với người khác**. Khi cần idempotent create, định nghĩa idempotency key, nội dung request canonical, chính sách trả lại kết quả và thời gian lưu khóa phù hợp.

## 6. save, insert và cập nhật theo ID

| Phương pháp | Ý nghĩa nghiệp vụ nên gắn | Trường hợp cần thận trọng |
|---|---|---|
| `MongoTemplate.insert(entity)` | Tạo document mới | Duplicate ID hoặc unique business key sẽ bị từ chối |
| `MongoRepository.save(entity)` | Lưu entity mới hoặc đã tồn tại | Không dùng như thao tác create-only; chú ý `@Version` |
| `MongoTemplate.updateFirst(query, update, Type.class)` | Cập nhật document khi điều kiện thỏa | Kiểm tra `matchedCount`, điều kiện trạng thái và version |
| `MongoTemplate.findAndModify(...)` | Đọc và cập nhật một document trong một thao tác | Cần điều kiện đúng và đọc giá trị trả về theo semantics mong muốn |
| `MongoTemplate.remove(query, Type.class)` | Xóa document theo điều kiện | `deletedCount` cho biết có document được xóa tại lúc thực thi |

Trong ví dụ `Registration` có `@Version`, quá trình `save` một entity đã đọc có thể sử dụng optimistic locking, phát hiện version đã đổi và ném `OptimisticLockingFailureException`. Đây là cơ chế hỗ trợ cập nhật an toàn cho entity, nhưng chỉ phát huy đúng khi **mọi đường ghi liên quan tôn trọng version**.

Ví dụ:

~~~java
package com.example.registration;

import org.springframework.stereotype.Service;

@Service
public class RegistrationStatusService {
    private final RegistrationRepository registrations;

    public RegistrationStatusService(RegistrationRepository registrations) {
        this.registrations = registrations;
    }

    public Registration activate(String id) {
        Registration current = registrations.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Không có đăng ký"));

        current.setStatus("ACTIVE");
        return registrations.save(current);
    }
}
~~~

Trong luồng cạnh tranh, hai request có thể cùng đọc version `3`, nhưng chỉ một lệnh save dựa trên version đó được chấp nhận; request còn lại cần xử lý optimistic locking và quyết định thử lại hay báo xung đột. Thử lại **không** có nghĩa ghi đè mù: cần đọc lại và đánh giá nghiệp vụ trên dữ liệu mới.

## 7. Kiểm tra và ghi trong cùng một lệnh: compare-and-set

Nếu mục tiêu là “chỉ chuyển `PENDING` sang `CONFIRMED` một lần”, ta có thể đặt điều kiện **ngay trong lệnh update** thay vì gọi `existsById` rồi `save`:

~~~java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public boolean confirmIfPending(
        MongoTemplate mongo, String id, long expectedVersion) {
    Query query = Query.query(
            Criteria.where("id").is(id)
                    .and("status").is("PENDING")
                    .and("version").is(expectedVersion));

    Update update = new Update()
            .set("status", "CONFIRMED")
            .inc("version", 1);

    UpdateResult result = mongo.updateFirst(
            query, update, Registration.class);
    return result.getMatchedCount() == 1;
}
~~~

Đoạn code này minh họa phương thức trong một lớp ứng dụng, nhận `MongoTemplate` để dễ kiểm thử. Vì truy vấn được chạy với `Registration.class`, Spring Data ánh xạ property `id` sang BSON `_id` và xử lý thông tin mapping phù hợp.

**Tại sao an toàn hơn?** Việc so sánh ID, trạng thái, version và thay đổi trên **một document** được MongoDB thực thi trong một thao tác nguyên tử. Nếu A chuyển thành `CONFIRMED` trước, B không còn tìm thấy document thỏa `status = PENDING` và version cũ nữa.

Giải thích kết quả:

- `matchedCount == 1`: có một document thỏa điều kiện vào lúc MongoDB thực thi lệnh cập nhật.
- `matchedCount == 0`: ID có thể không tồn tại, trạng thái đã đổi hoặc version không còn khớp. Nếu API cần phân biệt nguyên nhân, thực hiện truy vấn bổ sung **để giải thích kết quả**, chứ không dùng nó để bảo vệ lần ghi đã qua.
- `modifiedCount` có thể dùng khi cần biết có bao nhiêu document thực sự đổi giá trị. Đừng mặc định mọi trường hợp `modifiedCount = 0` nghĩa là ID không tồn tại.

Do ví dụ dùng `@Version`, lệnh update chủ động tăng `version` để các thao tác `save` sau đó phát hiện thay đổi. Khi tự viết update có điều kiện, cần thống nhất cơ chế version với các đường ghi khác; nếu lệnh ghi bỏ qua version hoặc sửa BSON trực tiếp, optimistic locking của repository có thể không bảo vệ đầy đủ.

### 7.1. Xóa có điều kiện thay cho kiểm tra rồi xóa

Nếu cần xóa **chỉ khi đang PENDING**, có thể dùng:

~~~java
import com.mongodb.client.result.DeleteResult;

public boolean deleteIfPending(MongoTemplate mongo, String id) {
    Query query = Query.query(
            Criteria.where("id").is(id)
                    .and("status").is("PENDING"));
    DeleteResult deleted = mongo.remove(query, Registration.class);
    return deleted.getDeletedCount() == 1;
}
~~~

Việc đặt điều kiện vào lệnh remove tránh khoảng trống giữa `existsById` và `deleteById`. Nếu hành vi xóa còn phụ thuộc version, thêm điều kiện version kỳ vọng. Với yêu cầu lưu lịch sử/audit, cân nhắc soft-delete bằng update trạng thái có điều kiện thay vì xóa vật lý.

## 8. Vì sao count không bảo vệ được hạn mức?

Giả sử hệ thống cho phép tối đa **100 đăng ký đang ACTIVE**. Mã dưới đây không đủ an toàn khi chạy đồng thời:

~~~java
if (registrations.countByStatus("ACTIVE") < 100) {
    registrations.save(
            new Registration(newId, emailKey, "ACTIVE"));
}
~~~

Khi có 99 đăng ký, hai request cùng đếm được `99`, rồi cả hai đều tạo mới. Cuối cùng số đăng ký có thể là `101`. Đọc số lượng và chèn document là hai thao tác riêng, và unique `_id` không giúp ngăn vượt hạn mức **toàn collection**.

Ngay cả khi chọn read concern mạnh hơn, một chuỗi `count → insert` riêng lẻ vẫn không tự biến thành thao tác **kiểm tra và giữ suất** nguyên tử. Transaction nhiều document cũng cần phân tích xung đột thực tế; nếu chỉ đọc cùng một tập document rồi ghi **hai document khác nhau**, không nên tự tin rằng mọi race condition đã được loại bỏ.

### 8.1. Dùng một document quota làm điểm đồng bộ

Một thiết kế là lưu **số suất còn lại** trong một document quota, rồi trừ suất **có điều kiện** trên chính document đó:

~~~json
{
  "_id": "registration-limit",
  "remaining": 1
}
~~~

**RegistrationQuota.java**

~~~java
package com.example.registration;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "registration_quotas")
public class RegistrationQuota {
    @MongoId(FieldType.STRING)
    private String id;
    private long remaining;

    protected RegistrationQuota() {}

    public String getId() { return id; }
    public long getRemaining() { return remaining; }
}
~~~

**Hàm đặt chỗ một suất:**

~~~java
import org.springframework.data.mongodb.core.FindAndModifyOptions;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public boolean reserveOne(MongoTemplate mongo, String quotaId) {
    Query query = Query.query(
            Criteria.where("id").is(quotaId)
                    .and("remaining").gt(0));
    Update decrement = new Update().inc("remaining", -1);

    RegistrationQuota result = mongo.findAndModify(
            query,
            decrement,
            FindAndModifyOptions.options().returnNew(true),
            RegistrationQuota.class);
    return result != null;
}
~~~

Hai request cùng thấy một suất còn lại không thể **cùng** trừ từ 1 xuống 0 bằng điều kiện `remaining > 0` trên cùng document: một request thành công và request kia không khớp điều kiện. Đây là cách bảo vệ **bất biến trên document quota**.

Tuy nhiên, **giữ suất và tạo registration là hai document khác nhau**. Nếu đặt chỗ thành công nhưng tạo đăng ký thất bại, suất có thể bị giữ sai. Khi nghiệp vụ cần nhất quán giữa quota và đăng ký, phải thiết kế quy trình:

- Transaction MongoDB nhiều document trên topology hỗ trợ, cùng `MongoTransactionManager` hoặc session tương ứng và xử lý retry đúng cách; **hoặc**
- Reservation có ID, trạng thái, thời hạn, cơ chế hoàn tác/đối soát và tính idempotent được định nghĩa rõ.

Không xem đoạn `reserveOne` đơn lẻ như một quy trình đăng ký trọn vẹn. Một document quota dùng chung cũng có thể trở thành điểm tranh chấp khi tải cao; cần đo thông lượng và cân nhắc phân vùng quota theo miền nghiệp vụ.

### 8.2. Khi nào dùng count cho hạn mức?

`countByStatus` phù hợp **hiển thị độ sử dụng, dự báo, cảnh báo gần đầy**. Nó cũng có thể là một phép sàng lọc sớm nếu hệ thống chấp nhận kiểm tra thừa. Nhưng khi số 100 là ràng buộc **không được vượt**, việc thực thi giới hạn phải thuộc một cơ chế ghi có điều kiện hoặc quản lý tài nguyên được thiết kế để chịu cạnh tranh.

## 9. Hiệu năng của existsById và count

### 9.1. Kiểm tra theo _id

`existsById` thường là một cách diễn đạt gọn và hiệu quả khi chỉ cần biết có document hay không. Với `_id` có index, truy vấn không cần tải cả một object lớn chỉ để kiểm tra hiện diện. Nhưng vẫn có chi phí kết nối, round trip và đọc trên server; nếu gọi lặp hàng nghìn lần trong vòng lặp, tổng chi phí có thể đáng kể.

Nếu cần biết sự tồn tại của nhiều ID, có thể gom ID và truy vấn điều kiện `_id: { $in: [...] }` với batch có kích thước giới hạn. Khi chỉ cần đếm số ID khớp, hãy chọn đúng query theo tập ID; không lấy toàn collection về bộ nhớ.

### 9.2. count toàn collection và count theo điều kiện

`count()` trả về số lượng dạng `long`, không phải phép ước lượng chi phí bằng không. Việc đếm chính xác có thể tốn tài nguyên tùy kích thước collection, điều kiện, index, phiên bản MongoDB và topology. Với filter trên `status`, cân nhắc index:

~~~javascript
db.registrations.createIndex({ status: 1 });
~~~

Sau đó kiểm tra bằng:

~~~javascript
db.registrations.find({ status: "ACTIVE" })
  .explain("executionStats");
~~~

`explain` của truy vấn tìm kiếm giúp xem index/keys/docs examined; với lệnh đếm, cần kiểm tra kế hoạch đếm cụ thể tương ứng trong môi trường thực tế. Nếu lọc theo nhiều field và sort, chọn index dựa trên workload, không tự tạo index cho mọi property.

### 9.3. Đếm ước lượng khi chỉ cần dashboard

Khi chỉ cần số liệu xấp xỉ **toàn collection**, MongoDB Java Driver có API `estimatedDocumentCount()` dựa trên metadata thay vì đếm chính xác từng document:

~~~java
long estimate = mongoTemplate
        .getCollection("registrations")
        .estimatedDocumentCount();
~~~

`estimatedDocumentCount()` **không nhận bộ lọc `status`**, và số ước lượng có thể khác số thực tế, đặc biệt quanh thao tác ghi/xóa hoặc những tình huống quản lý metadata/topology cụ thể. Không dùng số ước lượng làm hạn mức, quyết định thanh toán, thống kê cần chính xác theo điều kiện hay bảo vệ uniqueness.

### 9.4. Cấu hình đọc và các instance phân tán

Kết quả `existsById`/`count` còn phụ thuộc vào đường đọc, read preference, read concern và replication lag. Đọc từ secondary có thể thấy dữ liệu chậm hơn primary tùy cấu hình. Một phép đọc theo `_id` là nhanh không đồng nghĩa “đã có sự thật mới nhất” trong mọi topology.

Vì vậy, việc kiểm tra trước để bảo vệ một lệnh ghi càng không đáng tin nếu các thao tác đọc/ghi có khả năng quan sát những phiên bản dữ liệu khác nhau. Hãy gắn bất biến vào câu lệnh ghi và cấu hình nhất quán phù hợp thay vì dựa vào hai phép đọc/ghi rời rạc.

## 10. Reactive repository có khác về bảo đảm không?

Nếu sử dụng `ReactiveMongoRepository` và `ReactiveMongoTemplate`, kiểu kết quả trở thành publisher:

~~~java
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;

public interface ReactiveRegistrationRepository
        extends ReactiveMongoRepository<Registration, String> {
}
~~~

~~~java
Mono<Boolean> existing = reactiveRegistrations.existsById("reg-101");
Mono<Long> total = reactiveRegistrations.count();
~~~

Ở ví dụ thứ hai, `reactiveRegistrations` là biến được inject có kiểu `ReactiveRegistrationRepository`, và cần import `reactor.core.publisher.Mono`. Publisher chỉ thực thi khi được subscribe theo ngữ cảnh reactive thích hợp.

**Non-blocking không biến chuỗi `existsById → save` thành thao tác nguyên tử.** Race condition vẫn tồn tại khi nhiều subscriber hoặc request hoạt động đồng thời. Với nghiệp vụ cần nhất quán, dùng API cập nhật có điều kiện/transaction reactive đúng cách và tránh chặn event-loop bằng driver đồng bộ.

## 11. Kiểm thử bằng MongoDB thực

Unit test mock `existsById` rồi kiểm tra xem code có gọi `save` sẽ không phát hiện **lỗi TOCTOU** hoặc hành vi unique index. Cần integration test với MongoDB thực, ví dụ qua Testcontainers. Trong Spring Boot 3.x, `@DataMongoTest` hỗ trợ test slice MongoDB mapping/repository, nhưng **không tự khởi động MongoDB server**.

### 11.1. Kiểm tra existence, count và duplicate key

~~~java
package com.example.registration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;

@DataMongoTest
class RegistrationRepositoryTest {
    @Autowired
    RegistrationRepository registrations;

    @Autowired
    MongoTemplate mongo;

    @BeforeEach
    void prepare() {
        registrations.deleteAll();
        mongo.indexOps(Registration.class).ensureIndex(
                new Index()
                        .on("emailKey", Sort.Direction.ASC)
                        .unique());
    }

    @Test
    void existenceAndCountsReflectSavedDocuments() {
        assertThat(registrations.existsById("reg-101")).isFalse();

        mongo.insert(new Registration(
                "reg-101", "lan@example.test", "ACTIVE"));
        mongo.insert(new Registration(
                "reg-102", "minh@example.test", "PENDING"));

        assertThat(registrations.existsById("reg-101")).isTrue();
        assertThat(registrations.count()).isEqualTo(2);
        assertThat(registrations.countByStatus("ACTIVE")).isEqualTo(1);
    }

    @Test
    void insertRejectsDuplicateBusinessKey() {
        mongo.insert(new Registration(
                "reg-101", "lan@example.test", "ACTIVE"));

        assertThatThrownBy(() -> mongo.insert(
                new Registration(
                        "reg-102", "lan@example.test", "ACTIVE")))
                .isInstanceOf(DuplicateKeyException.class);
    }
}
~~~

Index được tạo **tường minh trong test** vì annotation mapping hoặc cấu hình Boot không bảo đảm tự động tạo index ở mọi môi trường. Khi chạy test song song, cần dùng collection/database cô lập để thao tác `deleteAll()` không ảnh hưởng trường hợp khác. Với dữ liệu production đang tồn tại, không chạy đoạn chuẩn bị test này.

### 11.2. Những ca kiểm thử concurrency cần có

| Kịch bản | Kết quả cần chứng minh |
|---|---|
Hai luồng cùng insert `_id = reg-101` | Tối đa một document mới; lỗi trùng ID được xử lý có chủ đích |
Hai luồng insert ID khác nhau nhưng cùng `emailKey` | Unique index chặn trùng business key |
Hai request cùng `existsById = false` rồi insert | Chỉ thao tác ghi quyết định thành công; pre-check không bảo vệ |
Hai request cùng đọc `version = 3` rồi `save` | Một cập nhật có thể thành công, cập nhật cũ bị phát hiện nếu mọi đường ghi tôn trọng version |
Hai request `confirmIfPending` cùng version | Tối đa một lần chuyển trạng thái theo điều kiện |
Hai request cùng giữ suất quota còn 1 | Tối đa một request trừ suất thành công |
Giữ suất rồi insert thất bại | Có transaction/compensation/idempotency để không mất suất |
Đếm `ACTIVE` trong lúc ghi/xóa | Định nghĩa rõ thời điểm và giới hạn nhất quán của thống kê |
Xử lý lại cùng request sau timeout | Không tạo bản ghi trùng và có cách xác định kết quả trước đó |

Khi viết integration test cạnh tranh, dùng cơ chế đồng bộ để hai luồng cùng bắt đầu tại điểm kiểm tra/ghi và xác nhận trạng thái **sau khi cả hai hoàn thành**. Nếu test chỉ chạy tuần tự, nó không chứng minh được việc bảo vệ race condition.

### 11.3. Chẩn đoán hiệu năng

Để hiểu chi phí, quan sát:

- Số lệnh MongoDB và round trip của luồng `existsById → insert` so với `insert` trực tiếp.
- Thời gian `count()`/`countByStatus(...)` theo kích thước collection và index.
- Số `DuplicateKeyException`, `OptimisticLockingFailureException` và retry ở giờ cao điểm.
- `matchedCount`, `modifiedCount`, `deletedCount` của các lệnh ghi có điều kiện.
- Độ trễ p95/p99, connection pool, replication lag và query plan khi lượng truy cập lớn.

Đừng tối ưu bằng cách đổi API trước khi kiểm tra query, index, dữ liệu và đường đọc thực tế.

## 12. Các sai lầm phổ biến

| Sai lầm | Hậu quả | Cách giải quyết |
|---|---|---|
Gọi `existsById` rồi `save` để bảo đảm chưa có ID | Race condition; có thể ghi đè hoặc xung đột | Dùng `insert` và unique `_id` cho tạo mới |
Gọi `existsByEmailKey` nhưng không có unique index | Hai request vẫn tạo cùng business key | Thêm unique index đúng namespace/phạm vi |
Xem `save` là “create-only” | Không biểu đạt rõ lỗi khi document đã tồn tại | Chọn `insert` cho thao tác chỉ tạo mới |
Đếm trước rồi thêm để áp hạn mức cứng | Hai request cùng được phép khi còn một suất | Conditional update trên quota, transaction hoặc reservation |
Xem `count()` luôn rất rẻ | Query tốn tài nguyên ở collection lớn | Kiểm tra index, plan và mục đích thống kê |
Dùng `estimatedDocumentCount` để quyết định hạn mức | Số ước lượng có thể lệch | Dùng cơ chế giữ suất/bất biến khi ghi |
Giả định một lần kiểm tra sẽ luôn đúng cho request sau | TOCTOU, eventual consistency hoặc replication lag | Đưa điều kiện vào thao tác ghi |
Đọc entity, sửa rồi `save` mà không quản lý version | Mất cập nhật của request khác | `@Version`/compare-and-set và retry có kiểm soát |
`modifiedCount = 0` được hiểu là “ID không tồn tại” | Phân loại lỗi sai | Kiểm tra `matchedCount` và điều kiện nghiệp vụ |
Tự động retry mọi lỗi trùng khóa | Có thể tạo vòng lặp hoặc trả kết quả sai | Phân biệt retryable/transient với xung đột nghiệp vụ |
Mock repository là bằng chứng đủ cho concurrency | Không thấy race/unique constraint | Test với MongoDB thật và nhiều luồng |

## 13. Bài tập vận dụng

**Bài 1 — Đọc đúng số liệu.** Tạo repository cho `Registration` với `existsById`, `count` và `countByStatus`. Lưu 2 đăng ký ACTIVE, 1 PENDING. Giải thích vì sao `count() == 3` còn `countByStatus("ACTIVE") == 2` và vì sao `count()` không phải phép đặt chỗ.

**Bài 2 — Bắt race condition.** Viết hai request cùng kiểm tra `existsById("reg-101")` rồi insert. Sử dụng barrier/latch trong integration test để cả hai cùng nhận kết quả `false` trước khi ghi. Bổ sung xử lý `DuplicateKeyException` và xác nhận collection chỉ có một `_id` đó.

**Bài 3 — Business key.** Yêu cầu một email chỉ có một đăng ký trong mỗi tenant. Thiết kế khóa chuẩn hóa, unique index (`tenantId`, `emailKey`), xử lý field thiếu và chính sách lỗi khi hai request cùng tạo.

**Bài 4 — So sánh insert/save.** Dùng `MongoTemplate.insert` tạo document, sau đó thử insert lại cùng ID. Dùng repository `save` để cập nhật document đã tải có `@Version`, rồi mô phỏng hai request cùng save một version cũ.

**Bài 5 — Hạn mức 100 suất.** Tạo document quota `remaining = 1`; gửi hai request đồng thời. Dùng `findAndModify` với `remaining > 0` để bảo đảm không âm. Đề xuất quy trình hoàn lại suất nếu bước tạo đăng ký thất bại.

**Bài 6 — Hiệu năng.** Với 100.000 đăng ký, đo `existsById`, `count()`, `countByStatus("ACTIVE")` và `estimatedDocumentCount()`. Kiểm tra index, p95 latency và độ chính xác số liệu trong lúc hệ thống đang ghi. Đề xuất cách dùng mỗi phép cho dashboard và nghiệp vụ.

## 14. Ghi nhớ

Trong **Spring Data MongoDB**, `existsById` trả lời **một ID có tồn tại tại thời điểm đọc hay không**, còn `count` và các phương thức `countBy...` trả lời **có bao nhiêu document thỏa điều kiện**. Chúng rất hữu ích cho kiểm tra, hiển thị số liệu và tối ưu đường đọc, nhưng **không làm cho lệnh ghi tiếp theo trở nên nguyên tử**.

Để **chỉ tạo mới**, dùng `insert` và unique index. Để **cập nhật nếu trạng thái/version còn khớp**, dùng `@Version` hoặc một thao tác cập nhật có điều kiện trên MongoDB. Để **giữ hạn mức cứng**, cần bất biến được bảo vệ tại lúc ghi, chẳng hạn document quota với `findAndModify`, cùng transaction hoặc cơ chế reservation đáng tin cậy khi có nhiều document.

Khi quyết định giữa kiểm tra trước và ghi trực tiếp, hãy ưu tiên **semantics nghiệp vụ, điều kiện đồng thời, khả năng idempotent, độ chính xác của thống kê và hiệu năng đo được**. Kiểm thử thực tế trên MongoDB có dữ liệu và mức cạnh tranh phù hợp mới cho thấy luồng xử lý có giữ được bất biến khi nhiều request chạy cùng lúc hay không.
