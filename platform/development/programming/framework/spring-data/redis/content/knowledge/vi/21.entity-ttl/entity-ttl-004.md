# Tương tác giữa save, cập nhật thực thể và thời hạn sống trong Spring Data Redis

## 1. TTL của thực thể: vì sao thao tác save có thể thay đổi thời điểm hết hạn?

Trong Spring Data Redis, ta thường lưu một **thực thể** (*entity*) dưới dạng Redis Hash thông qua repository. Các thực thể như phiên đăng nhập tạm, giỏ hàng chưa thanh toán, bản nháp đơn hàng hoặc mã xác thực không nên tồn tại vô hạn. Redis hỗ trợ **TTL (*Time To Live*)** để key tự hết hạn sau một khoảng thời gian.

Tuy nhiên, TTL không chỉ là thuộc tính được đặt một lần khi tạo dữ liệu. Khi ứng dụng gọi `save`, cập nhật thực thể, chỉnh sửa một trường trong Redis hoặc ghi lại cùng ID, **thời hạn sống có thể được giữ nguyên, được đặt lại hoặc bị loại bỏ**, tùy API và cách cấu hình TTL.

Ví dụ:

```text
09:00  Tạo bản nháp có TTL 10 phút → dự kiến hết hạn lúc 09:10
09:06  Người dùng sửa nội dung và ứng dụng gọi save(...)
09:10  Bản nháp có hết hạn hay chưa?
```

Câu trả lời phụ thuộc vào chính sách mong muốn:

- **TTL trượt (*sliding expiration*):** hoạt động mới được phép gia hạn; bản nháp có thể hết hạn lúc 09:16.
- **TTL cố định theo thời điểm tạo (*absolute/fixed deadline*):** dù có chỉnh sửa lúc 09:06, bản nháp vẫn hết hạn gần 09:10.
- **Chỉ cập nhật dữ liệu, không đổi thời hạn:** cần dùng đường cập nhật phù hợp để giữ TTL còn lại của Redis key.

Bài học đi vào quan hệ giữa `CrudRepository.save`, `@RedisHash(timeToLive = ...)`, `@TimeToLive`, cập nhật một phần và lệnh TTL của Redis. Mục tiêu là chọn được hành vi hết hạn có chủ đích, đồng thời tránh việc vô tình làm sống lại hoặc kéo dài dữ liệu.

## 2. Redis TTL hoạt động trên key, không hoạt động trên từng field

Trong Redis, TTL gắn với **toàn bộ key**. Nếu entity được ánh xạ thành một hash có key `demo:draft:d-1001`, các field `title`, `content` và `ownerId` có chung một thời điểm hết hạn của key.

```text
Key: demo:draft:d-1001
Type: hash

  id       → d-1001
  title    → Bản nháp thanh toán
  content  → Nội dung đang soạn
  ownerId  → user-42

TTL của cả key: 600 giây
```

Vì vậy, nếu bản nháp hết hạn thì không chỉ field `content` bị mất: toàn bộ key không còn được đọc như trước.

Các lệnh Redis thường dùng:

| Lệnh | Ý nghĩa |
|---|---|
| `EXPIRE key seconds` | Đặt hoặc thay đổi thời hạn sống của key theo giây |
| `PEXPIRE key milliseconds` | Đặt TTL theo mili giây |
| `TTL key` | Đọc số giây sống còn lại |
| `PTTL key` | Đọc số mili giây sống còn lại |
| `PERSIST key` | Gỡ trạng thái hết hạn, để key tồn tại cho đến khi bị xóa theo cách khác |
| `DEL key` / `UNLINK key` | Xóa key, không phụ thuộc TTL |

Ý nghĩa kết quả của `TTL`:

- Giá trị **từ 0 trở lên**: key có thời hạn, con số là lượng thời gian còn lại tính bằng giây.
- **`-1`**: key tồn tại nhưng không có thời hạn hết hạn.
- **`-2`**: key không còn tồn tại.

Ví dụ thử trên Redis CLI:

```redis
HSET demo:draft:d-1001 title "Bản nháp"
EXPIRE demo:draft:d-1001 600
TTL demo:draft:d-1001
```

Nếu `TTL` vừa được đặt, kết quả sẽ gần 600 giây rồi giảm dần. Redis không hứa rằng key bị loại bỏ chính xác ở thời điểm từng mili giây, nhưng sau khi hết hạn, các thao tác đọc sẽ không còn xem key đó là dữ liệu hợp lệ.

**Phân biệt TTL với thời gian nghiệp vụ:** TTL là cơ chế vòng đời lưu trữ. Các quy tắc như “đơn hàng không được thanh toán sau 10 phút” có thể cần thêm trường `expiresAt` và xác nhận hạn ở tầng nghiệp vụ; chỉ dựa vào một sự kiện key expired để kích hoạt hành động quan trọng là chưa đủ.

## 3. Khai báo TTL cố định bằng @RedisHash

Spring Data Redis Repository hỗ trợ đặt TTL mặc định của thực thể bằng `@RedisHash(timeToLive = ...)`.

**`OrderDraft.java`**

```java
package com.example.demo.redis;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash(value = "demo:draft", timeToLive = 600)
public class OrderDraft {

    @Id
    private String id;

    private String ownerId;

    private String content;

    public OrderDraft() {
    }

    public OrderDraft(String id, String ownerId, String content) {
        this.id = id;
        this.ownerId = ownerId;
        this.content = content;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getOwnerId() {
        return ownerId;
    }

    public void setOwnerId(String ownerId) {
        this.ownerId = ownerId;
    }

    public String getContent() {
        return content;
    }

    public void setContent(String content) {
        this.content = content;
    }
}
```

Ý nghĩa:

- `@RedisHash(value = "demo:draft")`: keyspace của thực thể.
- `timeToLive = 600`: TTL mặc định **600 giây**, tương đương 10 phút, khi repository persist thực thể với chính sách này.
- `@Id`: định danh; ví dụ ID `d-1001` ánh xạ đến key `demo:draft:d-1001`.
- Các thuộc tính bình thường như `content` không tự có TTL riêng.

Repository:

**`OrderDraftRepository.java`**

```java
package com.example.demo.redis;

import org.springframework.data.repository.CrudRepository;

public interface OrderDraftRepository
        extends CrudRepository<OrderDraft, String> {
}
```

Khi Spring Data Redis Repository được kích hoạt, ứng dụng có thể gọi:

```java
OrderDraft draft = new OrderDraft(
        "d-1001",
        "user-42",
        "Nội dung bản nháp"
);

repository.save(draft);
```

Repository ánh xạ đối tượng sang Redis và thiết lập thời hạn sống cho key theo cấu hình entity.

### Save lại có đặt TTL mới không?

**Với thực thể có TTL cố định từ `@RedisHash(timeToLive = 600)`, một lần `save` lại thường áp dụng lại khoảng thời gian 600 giây**, nên thời điểm hết hạn được tính lại từ lần lưu đó.

Ví dụ trong môi trường không có tác vụ khác thay đổi key:

```text
09:00:00  save(draft)          TTL gần 600s  → hết hạn khoảng 09:10
09:06:00  sửa content
09:06:01  save(draft)          TTL gần 600s  → hết hạn khoảng 09:16
09:10:00  key vẫn còn
09:16:01  key có thể đã hết hạn
```

Đây là hành vi phù hợp nếu quy ước là **mỗi lần lưu lại thực thể sẽ gia hạn thời gian tồn tại**.

Nó không phù hợp nếu deadline phải luôn cố định kể từ lúc tạo đơn. Khi đó cần chọn thiết kế khác, thay vì mong đợi `save` tự giữ TTL còn lại của lần ghi trước.

## 4. TTL linh hoạt theo từng thực thể với @TimeToLive

Nếu mỗi bản ghi cần một TTL khác nhau, Spring Data Redis hỗ trợ annotation `@TimeToLive` trên một thuộc tính số hoặc một phương thức.

Ví dụ bản nháp có TTL do nghiệp vụ quyết định:

**`VariableTtlDraft.java`**

```java
package com.example.demo.redis;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.TimeToLive;

@RedisHash("demo:variable-draft")
public class VariableTtlDraft {

    @Id
    private String id;

    private String content;

    @TimeToLive
    private Long ttlSeconds;

    public VariableTtlDraft() {
    }

    public VariableTtlDraft(
            String id,
            String content,
            Long ttlSeconds
    ) {
        this.id = id;
        this.content = content;
        this.ttlSeconds = ttlSeconds;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getContent() {
        return content;
    }

    public void setContent(String content) {
        this.content = content;
    }

    public Long getTtlSeconds() {
        return ttlSeconds;
    }

    public void setTtlSeconds(Long ttlSeconds) {
        this.ttlSeconds = ttlSeconds;
    }
}
```

Repository của entity này:

```java
package com.example.demo.redis;

import org.springframework.data.repository.CrudRepository;

public interface VariableTtlDraftRepository
        extends CrudRepository<VariableTtlDraft, String> {
}
```

Lưu một bản nháp sống 5 phút:

```java
VariableTtlDraft draft = new VariableTtlDraft(
        "d-2001",
        "Nội dung được lưu tạm",
        300L
);

variableTtlDraftRepository.save(draft);
```

Với `@TimeToLive` trên thuộc tính số, giá trị được dùng để xác định thời gian tồn tại. Đơn vị mặc định là **giây**; nếu cần chỉ định tường minh, các phiên bản Spring Data Redis hỗ trợ:

```java
import java.util.concurrent.TimeUnit;
import org.springframework.data.redis.core.TimeToLive;

@TimeToLive(unit = TimeUnit.SECONDS)
private Long ttlSeconds;
```

Không khai báo `@TimeToLive` đồng thời trên **cả property và getter method** của cùng entity. Hai cách này là lựa chọn thay thế nhau, vì nếu cùng xuất hiện sẽ gây cấu hình TTL mâu thuẫn.

### TTL từ thuộc tính và TTL từ annotation lớp khác nhau ở đâu?

| Cách cấu hình | Đặc điểm | Trường hợp nên dùng |
|---|---|---|
| `@RedisHash(timeToLive = 600)` | TTL cố định cho lớp entity mỗi lần persist | Mọi bản nháp có cùng chính sách gia hạn khi save |
| `@TimeToLive private Long ttlSeconds` | TTL lấy từ giá trị động của từng đối tượng | Mỗi bản nháp có thời hạn khác nhau |
| `@TimeToLive` trên method | TTL được tính khi cần từ kết quả method | Chính sách sống phụ thuộc logic của entity |
| Dùng Redis `EXPIRE` chủ động | Điều khiển TTL ngoài repository | Cần thay đổi thời hạn theo một thao tác riêng, phải hiểu tương tác với lần save kế tiếp |

Để tránh nhầm lẫn, các ví dụ trong bài sử dụng `@RedisHash(timeToLive = ...)` **hoặc** `@TimeToLive` cho từng entity, thay vì kết hợp cả hai thành một chính sách khó quan sát.

## 5. Điểm dễ nhầm: đọc entity có @TimeToLive rồi lưu lại

Annotation `@TimeToLive` trên **property** có một hành vi quan trọng: khi repository đọc entity từ Redis, Spring Data có thể nạp vào property đó **TTL thực tế còn lại của key**, bằng cách đọc TTL hoặc PTTL.

Giả sử ta tạo entity:

```java
variableTtlDraftRepository.save(
        new VariableTtlDraft("d-2001", "Bản nháp", 300L)
);
```

Sau khoảng 120 giây:

```java
VariableTtlDraft loaded =
        variableTtlDraftRepository.findById("d-2001")
                .orElseThrow();

System.out.println(loaded.getTtlSeconds());
```

Giá trị `ttlSeconds` đọc ra có thể chỉ còn khoảng **180 giây**. Đây không phải TTL ban đầu 300 giây được lưu cố định như một thông tin lịch sử, mà là **thời gian sống còn lại** tại lúc đọc.

Nếu ngay sau đó sửa nội dung:

```java
loaded.setContent("Đã cập nhật nội dung");
variableTtlDraftRepository.save(loaded);
```

thì lần `save` sử dụng giá trị TTL trên đối tượng. Nếu giá trị đó vẫn là khoảng 180 giây, key tiếp tục có thời hạn gần 180 giây từ lúc lưu; nó **không tự động quay lại 300 giây** chỉ vì phương thức là `save`.

### Hai ý định nghiệp vụ khác nhau

**Ý định A — không gia hạn khi chỉ sửa nội dung:**

```java
VariableTtlDraft loaded =
        variableTtlDraftRepository.findById("d-2001")
                .orElseThrow();

loaded.setContent("Chỉnh sửa nhưng không gia hạn cố ý");
variableTtlDraftRepository.save(loaded);
```

Property TTL được đọc từ Redis giúp giữ thời hạn tương đối gần với deadline cũ. Tuy nhiên, đây **không phải bảo đảm giữ deadline chính xác**: thời gian trôi qua giữa lúc đọc và lúc ghi, làm tròn đơn vị TTL và các bản ghi đồng thời vẫn tạo sai khác. Với deadline chính xác, hãy lưu thời điểm `expiresAt` độc lập và áp dụng cơ chế kiểm soát tương ứng.

**Ý định B — mỗi lần sửa sẽ gia hạn đủ 5 phút:**

```java
VariableTtlDraft loaded =
        variableTtlDraftRepository.findById("d-2001")
                .orElseThrow();

loaded.setContent("Chỉnh sửa và gia hạn");
loaded.setTtlSeconds(300L);

variableTtlDraftRepository.save(loaded);
```

Ở đây, ta **chủ động đặt lại property TTL** trước khi gọi `save`. TTL mới được xác định rõ ràng bằng 300 giây.

**Bài học thực tế:** khi dùng `@TimeToLive` trên property, không nên gọi `save` trên entity vừa đọc mà không quan tâm giá trị property TTL; giá trị ấy có thể là **TTL còn lại**, không còn là cấu hình lúc entity được tạo.

## 6. So sánh save, cập nhật trực tiếp và lệnh Redis đối với TTL

Redis có quy tắc TTL riêng cho từng loại thao tác. Những thao tác thay đổi dữ liệu của **cùng một key** không nhất thiết làm mất TTL.

Ví dụ, với key có TTL 600 giây:

```redis
HSET demo:draft:d-1001 content "Bản cũ"
EXPIRE demo:draft:d-1001 600
TTL demo:draft:d-1001
```

Sửa một field bằng lệnh `HSET`:

```redis
HSET demo:draft:d-1001 content "Bản mới"
TTL demo:draft:d-1001
```

`HSET` thông thường **giữ TTL đang chạy của key**: nó không tự đặt lại 600 giây và cũng không tự làm key trở thành không có thời hạn.

So sánh:

| Thao tác | Hành vi TTL cần hiểu |
|---|---|
| `repository.save(entity)`, entity có TTL cố định 600 giây | Repository persist và áp dụng chính sách TTL của entity; thường tạo lại cửa sổ 600 giây |
| `repository.save(entity)`, entity có property `@TimeToLive` | Áp dụng giá trị TTL hiện có trên đối tượng (có thể là TTL còn lại sau khi đọc) |
| `HSET key field value` | Thường giữ nguyên TTL của key đã tồn tại |
| `EXPIRE key 300` | Thay TTL của key thành khoảng 300 giây kể từ lúc gọi |
| `PERSIST key` | Gỡ thời hạn hết hạn |
| `DEL key` / `UNLINK key` | Xóa key ngay hoặc theo cơ chế giải phóng bộ nhớ của Redis |
| `SET key value` thông thường | Ghi đè nội dung key và thường xóa TTL cũ, trừ khi dùng tùy chọn giữ TTL phù hợp; đồng thời có thể đổi kiểu dữ liệu |
| Thực thể tự hết hạn | Redis loại bỏ key chính; `findById` sau đó không còn tìm thấy |

**Không dùng `SET` để cập nhật Redis Hash của repository.** `SET` ghi một giá trị string lên key có thể thay thế hash, làm repository không đọc đúng entity. Khi cần sửa field bằng thao tác Redis cấp thấp, `HSET` là lệnh cùng kiểu dữ liệu, nhưng vẫn có vấn đề về đồng bộ chỉ mục và metadata do repository quản lý.

### Vì sao repository.save khác với HSET?

Redis Repository vận hành ở **cấp thực thể**, gồm mapping, ghi dữ liệu, xử lý TTL và có thể cập nhật chỉ mục. `HSET` chỉ là thao tác Redis cấp trường. Vì vậy, dù cả hai đều có thể làm thay đổi một field trong hash, tác động đến TTL và cấu trúc phụ trợ không mặc nhiên giống nhau.

Nếu dự án đang dùng repository để quản lý entity và index, nên thống nhất đường cập nhật chính thức cho những thay đổi có ý nghĩa nghiệp vụ.

## 7. Cập nhật toàn bộ bằng save và cập nhật từng phần bằng PartialUpdate

Với repository, mô hình đơn giản nhất là:

```java
OrderDraft draft = repository.findById("d-1001")
        .orElseThrow();

draft.setContent("Nội dung cập nhật");
repository.save(draft);
```

Đây là thao tác **đọc, sửa đối tượng, rồi lưu lại**. Nếu dùng `@RedisHash(timeToLive = 600)`, lần `save` sẽ tương tác với TTL theo chính sách 600 giây của entity.

Trong một số tình huống, chỉ muốn sửa vài thuộc tính mà **không viết lại toàn bộ entity**. Spring Data Redis có `PartialUpdate` để khai báo các thay đổi ở cấp thuộc tính.

Ví dụ entity có property `@TimeToLive` như `VariableTtlDraft`:

```java
import org.springframework.data.redis.core.PartialUpdate;
import org.springframework.data.redis.core.RedisKeyValueTemplate;

// redisKeyValueTemplate được Spring inject:
PartialUpdate<VariableTtlDraft> update =
        new PartialUpdate<>("d-2001", VariableTtlDraft.class)
                .set("content", "Nội dung chỉnh sửa");

redisKeyValueTemplate.update(update);
```

Lệnh này cập nhật thuộc tính `content` theo API partial update, không cần đọc toàn bộ entity ở tầng service.

### Khi muốn cập nhật TTL có chủ đích

`PartialUpdate` hỗ trợ tùy chọn `refreshTtl(true)`:

```java
PartialUpdate<VariableTtlDraft> update =
        new PartialUpdate<>("d-2001", VariableTtlDraft.class)
                .set("ttlSeconds", 600L)
                .refreshTtl(true);

redisKeyValueTemplate.update(update);
```

Ý nghĩa: thay đổi property TTL và yêu cầu cập nhật **thời hạn hết hạn phía Redis server** theo giá trị mới. Đây là cách diễn đạt rõ hơn việc gia hạn TTL khi sử dụng cơ chế partial update.

Có thể cập nhật dữ liệu và TTL trong một lần gọi:

```java
PartialUpdate<VariableTtlDraft> update =
        new PartialUpdate<>("d-2001", VariableTtlDraft.class)
                .set("content", "Bản nháp đã được chỉnh sửa")
                .set("ttlSeconds", 900L)
                .refreshTtl(true);

redisKeyValueTemplate.update(update);
```

**Lưu ý:** `refreshTtl(true)` là một quyết định rõ ràng yêu cầu làm mới thời gian hết hạn, không phải tùy chọn nên bật cho mọi cập nhật. Khi chỉ thay đổi field và muốn giữ deadline đang chạy, không được vô tình đặt lại TTL. Cũng cần phân biệt API partial update của `RedisKeyValueTemplate` với `CrudRepository.save`; hai luồng lưu dữ liệu có mục đích và cách tương tác TTL khác nhau.

### Khi nào cần cẩn trọng với partial update?

- Field cần cập nhật có `@Indexed` thì phải tính đến thay đổi secondary index; nên dùng đúng API mapping hỗ trợ thay vì `HSET` thủ công.
- Cập nhật thuộc tính lồng nhau, map hoặc collection có thể cần thêm lần đọc hoặc thao tác Redis; không mặc định partial update luôn nhanh hơn.
- Nếu một key đã hết hạn trước lúc cập nhật, tác vụ cần quyết định **có được phép tạo lại key hay không**; không giả định mọi lệnh cập nhật sẽ tự từ chối key không còn tồn tại.
- Các phiên bản Spring Data Redis có thể có chi tiết hành vi khác nhau; ứng dụng cần dựa vào phiên bản thư viện đang sử dụng khi chọn API TTL.

## 8. Thiết kế chính sách TTL: gia hạn khi save hay giữ deadline?

Cùng một thực thể nhưng hai chính sách hết hạn dẫn đến hai thiết kế khác nhau.

### 8.1. Sliding TTL: người dùng còn hoạt động thì vẫn còn bản nháp

Giả sử mỗi lần người dùng chỉnh sửa cần gia hạn thêm 10 phút.

```text
Tạo lúc 09:00 → hết hạn 09:10
Sửa lúc 09:06 → hết hạn 09:16
Sửa lúc 09:13 → hết hạn 09:23
```

Với mục tiêu này, entity có `@RedisHash(timeToLive = 600)` hoặc một property `@TimeToLive` được gán lại 600 trước khi lưu có thể phù hợp.

**Ví dụ service với TTL cố định:**

```java
package com.example.demo.service;

import com.example.demo.redis.OrderDraft;
import com.example.demo.redis.OrderDraftRepository;
import org.springframework.stereotype.Service;

@Service
public class DraftEditor {

    private final OrderDraftRepository repository;

    public DraftEditor(OrderDraftRepository repository) {
        this.repository = repository;
    }

    public OrderDraft updateContent(String id, String content) {
        OrderDraft draft = repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Draft not found")
                );

        draft.setContent(content);

        // Với @RedisHash(timeToLive = 600),
        // lần save áp dụng lại chính sách TTL.
        return repository.save(draft);
    }
}
```

Điều cần hiểu: gọi `save` nhiều lần trên cùng entity không chỉ có thể gây chi phí ghi dữ liệu; nó còn thay đổi vòng đời của key. Nếu hệ thống gọi `save` từ một job đồng bộ thường xuyên, bản nháp có thể tồn tại lâu hơn mong muốn dù người dùng đã ngừng hoạt động.

### 8.2. Absolute deadline: hết hạn theo một mốc bất biến

Ví dụ, một mã xác thực chỉ có hiệu lực đến 09:10, bất kể có bao nhiêu lần cập nhật thông tin phụ.

Có thể lưu thời điểm hết hạn như một giá trị nghiệp vụ, chẳng hạn `expiresAt`, và mỗi lần cần persist lại thì **tính TTL từ thời điểm hiện tại đến deadline**. Ý tưởng:

```text
expiresAt = 09:10:00

09:00:00  TTL xấp xỉ 600s
09:06:00  TTL xấp xỉ 240s
09:09:30  TTL xấp xỉ  30s
09:10:01  Đã quá hạn: từ chối cập nhật
```

Một entity dùng `@TimeToLive` có thể thêm thuộc tính `expiresAt`:

```java
@RedisHash("demo:fixed-deadline-draft")
public class DeadlineDraft {

    @Id
    private String id;

    private String content;

    private Instant expiresAt;

    @TimeToLive
    private Long ttlSeconds;

    // Constructor, getter và setter phù hợp.
}
```

Trong service, trước khi lưu có thể dùng `Clock` được inject:

```java
Instant now = clock.instant();
Duration remaining = Duration.between(now, draft.getExpiresAt());

if (remaining.isZero() || remaining.isNegative()) {
    throw new IllegalStateException("Draft đã hết hạn");
}

long ttlSeconds = remaining.getSeconds();

if (ttlSeconds < 1L) {
    throw new IllegalStateException("Draft sắp/hết hạn theo đơn vị giây");
}

draft.setTtlSeconds(ttlSeconds);
repository.save(draft);
```

Ở ví dụ này cần import `java.time.Clock`, `java.time.Duration` và `java.time.Instant`. Đây là **phác thảo logic service**, giả định `draft` đã được lấy từ nguồn tin cậy và `clock` đã được cung cấp. Với yêu cầu hạn chính xác đến mili giây, cần lựa chọn đơn vị và chính sách làm tròn phù hợp.

**Quan trọng:** việc tính thời gian còn lại rồi `save` không phải thao tác nguyên tử với đồng hồ và Redis. Nếu tác vụ ghi có thể bị trì hoãn hoặc chạy đồng thời, cần thêm cơ chế kiểm tra deadline/phiên bản ngay tại điểm ghi phù hợp với yêu cầu nghiệp vụ. Đối với mã xác thực, deadline phải tiếp tục được kiểm tra khi xác minh mã, kể cả khi key còn tồn tại trong Redis.

### 8.3. Không gia hạn khi cập nhật thông tin phụ

Ví dụ chỉ cần ghi số lần xử lý hoặc cập nhật một trường kỹ thuật nhưng giữ TTL của key. Có thể cân nhắc `PartialUpdate` không yêu cầu refresh TTL hoặc thao tác Redis Hash phù hợp khi đã kiểm soát index và mapping.

Đừng dùng `repository.save` trên entity có TTL cố định nếu mục đích là giữ **chính xác** thời điểm hết hạn hiện tại: một lần lưu lại có thể áp dụng chính sách TTL và gia hạn key.

## 9. Thí nghiệm đọc TTL trước và sau khi save

Có thể xem TTL bằng `StringRedisTemplate` trong môi trường thử nghiệm. Đoạn mã chỉ đọc TTL, không trực tiếp sửa hash do repository quản lý.

```java
package com.example.demo.service;

import java.util.concurrent.TimeUnit;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class DraftTtlInspector {

    private final StringRedisTemplate redis;

    public DraftTtlInspector(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long remainingSeconds(String draftId) {
        String key = "demo:draft:" + draftId;
        return redis.getExpire(key, TimeUnit.SECONDS);
    }
}
```

Ví dụ một chuỗi thao tác:

```java
OrderDraft draft = repository.save(
        new OrderDraft("d-1001", "user-42", "Lần đầu")
);

Long ttl1 = inspector.remainingSeconds("d-1001");
// Gần 600 giây ngay sau save.

draft.setContent("Lần thứ hai");
repository.save(draft);

Long ttl2 = inspector.remainingSeconds("d-1001");
// Gần 600 giây sau save lại theo TTL cố định.
```

Nếu muốn nhìn rõ việc giảm TTL rồi tăng lại, cần **quan sát hai lần ở những thời điểm thực sự cách nhau**; gọi liên tiếp có thể cho kết quả trông giống nhau. Không nên dùng giá trị `TTL == 600` làm điều kiện kiểm tra tuyệt đối vì thời gian thực thi, kết nối mạng và việc Redis làm tròn khiến số giây nhận được có thể khác một chút.

### Kiểm tra bằng Redis CLI

Sau khi repository lưu ID `d-1001`:

```redis
TYPE demo:draft:d-1001
HGETALL demo:draft:d-1001
TTL demo:draft:d-1001
PTTL demo:draft:d-1001
```

Để quan sát chính sách gia hạn, ghi nhận thời điểm/TTL, thực hiện một lần `save` thông qua ứng dụng, sau đó đọc `TTL` lại.

Cần phân biệt hai nguồn dữ liệu:

- **TTL server** lấy bằng `TTL` hoặc `PTTL` là trạng thái hiện tại của Redis key.
- **Property `@TimeToLive`** nằm trong đối tượng Java có thể phản ánh TTL vừa đọc ở một thời điểm trước đó.

Nếu cần quyết định có nên cho phép sửa dữ liệu khi gần hết hạn, đọc riêng TTL một lần không bảo đảm key còn tồn tại đến lúc ghi tiếp. Thiết kế điều kiện ghi cần tính đến thay đổi đồng thời.

## 10. Điều gì xảy ra khi save một thực thể đã hết TTL?

Giả sử:

```text
09:00  save(entity id = d-1001)
09:10  Redis hết hạn key demo:draft:d-1001
09:12  Một worker còn giữ đối tượng Java cũ và gọi save(...)
```

Một lời gọi `repository.save(entity)` thông thường là thao tác **lưu theo ID**. Nếu key đã bị xóa vì TTL, repository có thể **tạo lại key** và áp dụng TTL của entity như với lần lưu mới.

Đây là tình huống quan trọng với dữ liệu có hạn sử dụng nghiêm ngặt:

- Người dùng lưu trang đang mở sau khi session hết hạn.
- Worker xử lý chậm ghi kết quả của một tác vụ đã quá deadline.
- Một bản nháp hoặc mã xác nhận đã hết hạn bị hồi sinh do cập nhật muộn.
- Hai tác vụ giữ các phiên bản khác nhau của một đối tượng và lần save sau làm key quay lại.

**Repository.save không có nghĩa “chỉ cập nhật nếu key vẫn còn tồn tại và chưa hết hạn”.**

### Giải pháp khi không được phép hồi sinh dữ liệu

Có thể áp dụng một hoặc nhiều biện pháp:

1. Phân biệt luồng **tạo mới** và luồng **cập nhật hợp lệ** ở service. Khi sửa, trước tiên đọc entity và từ chối nếu không còn tồn tại.
2. Lưu `expiresAt` ở nguồn tin cậy và kiểm tra deadline của nghiệp vụ.
3. Nếu yêu cầu tuyệt đối không ghi lại sau khi hết hạn và có khả năng cạnh tranh đồng thời, dùng thao tác có điều kiện **nguyên tử tại Redis** theo thiết kế riêng (ví dụ Lua script/Redis Function) thay cho chuỗi “EXISTS rồi SAVE” tách biệt.
4. Dùng version/token hoặc trạng thái job để loại bỏ kết quả từ tác vụ cũ.

Chỉ kiểm tra `existsById` rồi gọi `save` **không đủ để đảm bảo nguyên tử**: key có thể hết hạn giữa hai lệnh. Tùy mức độ quan trọng, một cache bản nháp cho phép tạo lại có thể chấp nhận được; mã xác thực hoặc giao dịch tài chính thì cần quy tắc chặt hơn.

## 11. TTL và cập nhật đồng thời

Xét tình huống hai worker cùng đọc một entity có TTL 300 giây:

```text
09:00  Entity tồn tại, TTL 300s
09:01  Worker A đọc entity (TTL còn gần 240s)
09:02  Worker B đọc entity (TTL còn gần 180s)
09:03  Worker B đặt TTL mới 300s rồi save
09:04  Worker A save bản cũ với ttlSeconds gần 240s
```

Lần lưu cuối có thể **ghi đè dữ liệu và thay đổi TTL** theo giá trị trên đối tượng của Worker A. Thứ tự ghi thực tế quan trọng hơn thời điểm đọc. Dù cùng một Redis key, hai worker vẫn có thể gặp lỗi *lost update*.

Một biến thể khác:

- Worker A chỉ muốn sửa `content`.
- Worker B muốn thu ngắn hạn dùng xuống 60 giây.
- Nếu A lưu lại entity với TTL cũ sau B, hạn mới từ B có thể bị thay đổi ngoài ý muốn.

Các cách hạn chế:

| Tình huống | Hướng tiếp cận |
|---|---|
| Dữ liệu chỉ là cache, mất cập nhật có thể chấp nhận | Quy ước lần ghi cuối thắng, đặt TTL theo chính sách rõ |
| Cập nhật trường độc lập | Dùng API partial update phù hợp, tránh ghi cả entity khi không cần |
| TTL do một thành phần sở hữu | Tách quyền thay đổi TTL; chỉ thành phần đó được gia hạn hoặc rút ngắn |
| Không được ghi sau deadline | Kiểm tra và ghi có điều kiện nguyên tử ở phía Redis hoặc kho dữ liệu chính |
| Cần tránh lost update | Áp dụng cơ chế version/điều kiện ghi được hỗ trợ theo thiết kế riêng |
| Nhiều service dùng chung keyspace | Chuẩn hóa model, serialization, TTL và phương thức ghi |

`@Transactional` của Spring không tự bảo đảm rằng hai lời gọi repository từ các worker khác nhau sẽ tránh lost update hoặc xử lý deadline chính xác. Hành vi giao dịch Redis cần cấu hình rõ và vẫn phải xét tới tính nhất quán của nhiều key phụ trợ.

## 12. TTL, secondary index và sự kiện hết hạn

Khi dùng Spring Data Redis Repository, ngoài hash chính còn có thể tồn tại các khóa hỗ trợ index và metadata. Ví dụ:

```java
import org.springframework.data.redis.core.index.Indexed;

@Indexed
private String ownerId;
```

Chỉ mục này hỗ trợ truy vấn theo `ownerId`, nhưng **hết TTL của hash chính không đồng nghĩa Redis tự xóa từng thành viên trong secondary index**.

Spring Data Redis có cơ chế nghe sự kiện hết hạn để xử lý vòng đời entity, bao gồm việc dọn những tham chiếu còn sót trong index.

### RedisKeyExpiredEvent và listener

Khi cấu hình phù hợp, repository sử dụng Redis keyspace notifications và listener để nhận sự kiện key hết hạn. Spring Data Redis có thể phát `RedisKeyExpiredEvent` để phần khác của ứng dụng biết entity đã hết hạn.

Một cấu hình repository tường minh có thể đặt chế độ listener:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.RedisKeyValueAdapter.EnableKeyspaceEvents;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@Configuration
@EnableRedisRepositories(
        basePackages = "com.example.demo.redis",
        enableKeyspaceEvents = EnableKeyspaceEvents.ON_STARTUP
)
public class RedisRepositoryConfiguration {
}
```

Đây là ví dụ khi chọn cấu hình repository thủ công. Nếu Spring Boot đã cấu hình repository phù hợp, không nên thêm một cấu hình chồng lặp mà không có nhu cầu.

**Giới hạn quan trọng:**

- Redis Pub/Sub **không lưu bền vững** những sự kiện đã phát. Nếu không có listener phù hợp vào lúc key hết hạn, sự kiện có thể bị bỏ lỡ.
- Một số dịch vụ Redis được quản lý không cho ứng dụng thay đổi `notify-keyspace-events` bằng `CONFIG`; cần cấu hình và phân quyền theo môi trường.
- Listener có thể khởi động khi ứng dụng bắt đầu hoặc trì hoãn đến khi entity có TTL được thêm vào; cần hiểu chế độ đang dùng.
- Nếu sự kiện hết hạn bị bỏ lỡ, secondary index có thể còn tham chiếu đến entity không còn tồn tại.

### Shadow copy (*phantom copy*)

Để phát sự kiện có nội dung entity sau khi key chính hết hạn, Spring Data Redis có thể lưu một bản sao tạm có thời gian hết hạn muộn hơn bản gốc. Theo cơ chế mô tả trong tài liệu tham khảo, bản sao này thường tồn tại thêm khoảng **5 phút** sau thời điểm hết hạn của bản gốc.

Hệ quả: ngay cả sau khi entity chính hết hạn, có thể vẫn thấy **khóa phụ và một phần bộ nhớ** liên quan trong Redis. Đây không nhất thiết là lỗi rò rỉ; cần phân biệt dữ liệu chính, index và bản sao hỗ trợ sự kiện.

Nếu không cần dữ liệu entity trong sự kiện hết hạn, có thể cân nhắc cấu hình tắt `shadowCopy` theo khả năng phiên bản Spring Data Redis đang sử dụng. Khi tắt bản sao, sự kiện hết hạn có thể chỉ có thông tin ID/key; phải cân nhắc nhu cầu xử lý nghiệp vụ.

### Không coi sự kiện expired là hẹn giờ nghiệp vụ tin cậy tuyệt đối

Expiration event giúp phản ứng với vòng đời dữ liệu, nhưng không thay thế các cơ chế cần bảo đảm:

- Không bỏ sót một nhiệm vụ phải xử lý.
- Xử lý đúng một lần.
- Thực hiện công việc đúng vào một thời điểm có cam kết.
- Duy trì trạng thái nhất quán giữa Redis và nhiều hệ thống khác.

Với các yêu cầu đó, cần deadline nghiệp vụ và một cơ chế hàng đợi/job có thể truy vết, chạy lại hoặc xác nhận kết quả.

## 13. Kiểm soát trạng thái TTL trong ứng dụng

Một service thường muốn phân biệt ba trạng thái:

```text
TTL = -2      Key không tồn tại
TTL = -1      Key tồn tại nhưng không hết hạn
TTL >= 0      Key có hạn và còn N giây
```

Ví dụ cách đọc TTL:

```java
Long ttl = stringRedisTemplate.getExpire(
        "demo:draft:d-1001",
        java.util.concurrent.TimeUnit.SECONDS
);

if (ttl == null) {
    throw new IllegalStateException("Không đọc được TTL");
}

if (ttl == -2L) {
    // Key không tồn tại: có thể đã bị xóa hoặc hết hạn.
} else if (ttl == -1L) {
    // Key đang tồn tại nhưng không có expiration.
} else {
    // Có TTL: ttl giây còn lại.
}
```

`StringRedisTemplate` thích hợp khi tên key là chuỗi thông thường và ứng dụng thực sự dùng keyspace tương ứng. Với template có serializer key riêng, phải kiểm tra cấu hình serializer trước khi tự ghép key đọc TTL.

### TTL bằng 0 có nghĩa gì?

`TTL` có độ phân giải giây, vì vậy một key có TTL dương rất nhỏ có thể trả về 0 dù nó chưa biến mất ở đúng thời điểm đọc. Khi cần quan sát chi tiết thời hạn, dùng `PTTL` để xem mili giây.

Không viết logic kiểu “`ttl == 0` thì chắc chắn Redis đã xóa key”. Trường hợp cần xác định có thể cập nhật hay không vẫn cần logic điều kiện ghi phù hợp.

### TTL do repository đặt và TTL thay bằng lệnh EXPIRE

Ví dụ:

```redis
EXPIRE demo:draft:d-1001 60
TTL demo:draft:d-1001
```

Nếu sau đó ứng dụng gọi `repository.save(draft)` với entity có `@RedisHash(timeToLive = 600)`, chính sách TTL của repository có thể đặt key lại gần 600 giây. Do đó, một thay đổi TTL thực hiện ngoài repository không nhất thiết được duy trì sau lần lưu entity kế tiếp.

Nếu muốn rút ngắn deadline vĩnh viễn, cần lưu **chính sách mới** ở nơi mà mọi lần cập nhật đều tôn trọng, thay vì chỉ gửi một lệnh `EXPIRE` đơn lẻ rồi tiếp tục cho các luồng `save` gia hạn.

## 14. Những sai lầm thường gặp

### Sai lầm 1: “Mọi cập nhật field đều làm TTL bắt đầu lại”

Không đúng. `HSET` lên một Redis Hash đang có expiration thường giữ TTL đang chạy. Ngược lại, `repository.save` có thể áp dụng lại chính sách TTL của entity. Hai API có mục đích khác nhau.

### Sai lầm 2: “@TimeToLive luôn chứa TTL ban đầu”

Không đúng khi annotation nằm trên property và entity được **đọc lại từ Redis**. Khi đọc, Spring Data Redis có thể điền TTL còn lại vào property đó. Muốn gia hạn đủ thời gian, hãy gán lại TTL mới với chủ đích trước khi lưu.

### Sai lầm 3: “Gọi save tức là chỉ cập nhật key đang tồn tại”

Không đúng. `save` có thể tạo mới hoặc tạo lại key theo ID. Nếu entity đã hết hạn, một đối tượng Java cũ vẫn có thể được lưu lại, trừ khi ứng dụng có điều kiện ngăn việc hồi sinh.

### Sai lầm 4: “Khi hash hết TTL, mọi index cũng biến mất cùng lúc”

Không bảo đảm. Redis không quản lý trực tiếp metadata secondary index của Spring Data. Việc dọn index còn phụ thuộc cơ chế repository và xử lý expiration event.

### Sai lầm 5: “Đọc TTL rồi save sẽ giữ nguyên deadline chính xác”

Không bảo đảm. Thời gian giữa hai thao tác, đơn vị làm tròn và cạnh tranh ghi đều có thể làm thay đổi kết quả. Nếu yêu cầu deadline cứng, phải lưu mốc thời gian và dùng cơ chế kiểm soát ghi phù hợp.

### Sai lầm 6: “PERSIST chỉ làm mới TTL”

`PERSIST` loại bỏ expiration hoàn toàn. Nếu một luồng vô tình gọi `PERSIST` cho dữ liệu đáng lẽ tồn tại vài phút, key có thể sống vô hạn cho đến khi được xóa. Cần phân biệt `PERSIST` với `EXPIRE`.

### Sai lầm 7: “Chỉ cần thêm TTL ở entity thì dữ liệu cũ tự hết hạn”

Thêm `@RedisHash(timeToLive = 600)` vào mã nguồn không bảo đảm các key cũ đã lưu mà **chưa được ghi lại qua repository** sẽ lập tức có TTL. Cần chiến lược migration, đặt TTL cho dữ liệu cũ hoặc chính sách dọn dữ liệu phù hợp.

## 15. Bảng quyết định cho các thao tác phổ biến

| Mục tiêu | Lựa chọn và lưu ý |
|---|---|
| Mọi bản ghi sống 10 phút kể từ lần `save` gần nhất | `@RedisHash(timeToLive = 600)` |
| Mỗi entity có TTL riêng | Property hoặc method `@TimeToLive` |
| Đọc entity rồi muốn gia hạn đủ 5 phút | Gán lại `ttlSeconds = 300L` trước khi lưu |
| Sửa nội dung nhưng không cố ý gia hạn | Xem xét `PartialUpdate` không refresh TTL; tránh re-save có TTL cố định nếu deadline phải giữ |
| Đổi riêng thời hạn theo TTL property | `PartialUpdate.set("ttlSeconds", ...)` kèm `refreshTtl(true)` khi dùng API này |
| Giữ hạn cứng kể từ khi tạo | Lưu `expiresAt` và tính TTL từ deadline; kiểm soát đồng thời khi cần |
| Ngăn cập nhật entity đã hết hạn | Kiểm soát ghi có điều kiện nguyên tử nếu tính chính xác là bắt buộc |
| Thực hiện thao tác sau khi key hết hạn | Xem xét keyspace notifications, nhưng dùng job bền vững nếu không được bỏ sót |
| Truy vấn theo secondary index sau khi hết hạn | Đảm bảo cấu hình xử lý expiration và có phương án dọn index lỗi thời |
| Thay TTL trực tiếp bằng `EXPIRE` | Dự liệu lần `save` tiếp theo có thể áp dụng lại TTL từ entity |

## 16. Câu hỏi luyện tập theo dòng thời gian

**Tình huống A.** Entity được gắn `@RedisHash(timeToLive = 600)`, lưu lúc 09:00 và save lại lúc 09:08. Khi không có tác vụ khác, khoảng thời gian hết hạn mới là lúc nào?

**Giải thích:** lần save lại áp dụng chính sách TTL 600 giây. Key thường có thời hạn gần 09:18, tức khoảng 10 phút sau lần save thứ hai.

**Tình huống B.** Entity dùng `@TimeToLive private Long ttlSeconds` được lưu với 600 giây. Sau 5 phút, repository đọc lại entity; property TTL gần 300. Ứng dụng không đổi property TTL mà gọi `save`.

**Giải thích:** lần save sử dụng giá trị TTL trên đối tượng, có thể gần 300 giây; nó không tự suy ra cần quay lại 600. Để gia hạn đủ 600 giây, phải gán lại `ttlSeconds`.

**Tình huống C.** Một Redis hash có TTL 100 giây, rồi cập nhật field bằng `HSET`. TTL sẽ về 600 giây?

**Giải thích:** `HSET` không tự dùng TTL annotation của Java; lệnh này thường giữ TTL của Redis key. Nó không tự gia hạn về 600.

**Tình huống D.** Một bản nháp hết hạn, nhưng worker giữ object cũ và gọi `repository.save`.

**Giải thích:** `save` có thể tạo lại key. Nếu nghiệp vụ cấm hành động này, cần điều kiện tạo/cập nhật và kiểm soát tại điểm ghi thay vì chỉ dựa vào TTL.

**Tình huống E.** Key chính hết hạn trong thời gian ứng dụng không chạy. Khi khởi động lại, query theo index vẫn xuất hiện dấu vết của ID cũ.

**Giải thích:** expiration event qua Redis Pub/Sub có thể bị bỏ lỡ, nên công việc dọn secondary index chưa hoàn tất. Cần kiểm tra listener và có chiến lược sửa chữa index.

**Tình huống F.** Một entity có hạn tuyệt đối đến 12:00; lúc 11:59:45 ứng dụng vẫn còn quyền chỉnh sửa. Đặt lại 600 giây TTL mỗi lần save có đúng?

**Giải thích:** không. Đặt lại 600 giây sẽ vượt quá deadline. Cần áp dụng phần TTL **còn lại đến 12:00** và từ chối mọi thao tác trái quy tắc sau deadline.

## 17. Gợi ý thực hành với hệ thống thật

Khi triển khai TTL cho entity của Spring Data Redis, nên thống nhất bốn quyết định trước khi viết service:

1. **TTL tính từ lúc nào?** Từ khi tạo, từ lần ghi gần nhất, từ hoạt động hợp lệ của người dùng hay từ một deadline nghiệp vụ?
2. **Ai được phép thay TTL?** Mọi lần `save`, chỉ một thao tác gia hạn, hay một service chuyên trách?
3. **Khi key hết hạn thì có được tạo lại cùng ID?** Nếu không, ứng dụng cần cơ chế chống ghi muộn, không chỉ kiểm tra tồn tại một lần.
4. **Có metadata/index hoặc công việc phụ thuộc sự kiện expire không?** Khi có, cần tính đến keyspace notifications, shadow copy, các sự kiện bị bỏ lỡ và phương án khôi phục.

Tập trung trả lời những câu hỏi đó giúp tránh hai nhóm lỗi đối lập: **dữ liệu hết hạn sớm làm mất trạng thái hợp lệ**, hoặc **dữ liệu bị gia hạn/hồi sinh ngoài ý muốn dẫn đến sai quy tắc nghiệp vụ**.

## Tài liệu tham khảo

- [Spring Data Redis — Time To Live](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html)
- [Spring Data Redis — Persisting Partial Updates](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/usage.html)
- [Spring Data Redis — PartialUpdate API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/PartialUpdate.html)
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
- [Redis — EXPIRE](https://redis.io/docs/latest/commands/expire/)
- [Redis — TTL](https://redis.io/docs/latest/commands/ttl/)
- [Redis — Keyspace notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/)
