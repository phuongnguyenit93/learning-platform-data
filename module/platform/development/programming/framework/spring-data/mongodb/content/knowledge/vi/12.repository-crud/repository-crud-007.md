# Optional, collection rỗng và lỗi kết quả không duy nhất

## 1. Một truy vấn có thể trả về 0, 1 hoặc nhiều document

Trong **Spring Data MongoDB**, repository giúp ứng dụng Java thực hiện CRUD trên collection mà không phải tự viết mọi thao tác với `MongoTemplate`. Tuy nhiên, một phương thức repository không chỉ mô tả **điều kiện tìm kiếm**: **kiểu trả về** còn thể hiện kỳ vọng về **số lượng kết quả**.

Giả sử hệ thống quản lý người dùng có các thao tác:

- Lấy tài khoản theo `_id`: tối đa một document vì `_id` được MongoDB bảo đảm duy nhất trong collection.
- Lấy tài khoản theo email đã chuẩn hóa: nghiệp vụ yêu cầu tối đa một tài khoản cho mỗi email.
- Tìm người dùng theo biệt danh: nhiều tài khoản có thể cùng biệt danh.
- Liệt kê người dùng đang hoạt động: có thể không có ai, hoặc có rất nhiều người.

Nếu một method khai báo `Optional<User> findByNickname(...)` trong khi biệt danh được phép trùng, phương thức đang hứa hẹn một kết quả duy nhất mà dữ liệu không bảo đảm. Đây là nguồn gốc của lỗi **`IncorrectResultSizeDataAccessException`** trong các phương thức truy vấn yêu cầu một kết quả.

Bài học thuộc chương **Repository CRUD** của module **SPRING_DATA_MONGODB**, trong đó Spring Data được dùng để kết nối, ánh xạ document và truy vấn MongoDB bằng repository hoặc `MongoTemplate`. Ta sẽ tập trung vào bốn quyết định: **chọn đúng kiểu trả về, xử lý kết quả rỗng, bảo vệ tính duy nhất và phân biệt hợp đồng repository với hành vi của template/reactive API**.

## 2. Kiểu trả về là một hợp đồng cardinality

*Cardinality* là số lượng bản ghi khớp với điều kiện truy vấn. Khi thiết kế method, cần biết số lượng hợp lệ theo nghiệp vụ, chứ không chỉ nhìn vài bản ghi hiện tại.

| Kiểu trả về của method | Không có kết quả | Một kết quả | Nhiều kết quả khớp |
| --- | --- | --- | --- |
| `Optional<T>`, truy vấn một kết quả | `Optional.empty()` | `Optional.of(entity)` | Lỗi kích thước kết quả đối với truy vấn single-result không giới hạn |
| `T`, truy vấn một kết quả | Có thể là `null` hoặc ngoại lệ khi bật ràng buộc non-null tùy cấu hình | `entity` | Lỗi kích thước kết quả đối với truy vấn single-result không giới hạn |
| `List<T>` / `Collection<T>` | Collection rỗng, không phải `null` | Collection một phần tử | Collection nhiều phần tử |
| `Page<T>` | Trang rỗng | Trang chứa phần tử | Trang chứa tối đa page size, cùng metadata phân trang |
| `Slice<T>` | Slice rỗng | Slice chứa phần tử | Slice giới hạn theo pageable, có thông tin còn trang sau |
| `boolean existsBy...` | `false` | `true` | `true`; không trả dữ liệu document |
| `long countBy...` | `0` | `1` | Số lượng document khớp điều kiện |
| `Mono<T>` trong repository reactive | Hoàn tất mà không phát giá trị | Phát một giá trị rồi hoàn tất | Hợp đồng một kết quả; cách thực thi phải được kiểm thử, không dùng để liệt kê nhiều bản ghi |
| `Flux<T>` | Hoàn tất mà không phát phần tử | Phát một phần tử | Phát nhiều phần tử |

Các dòng trên nói về **method repository có ý định trả một kết quả**. Method giới hạn rõ bằng `First`/`Top` là trường hợp khác: nó chủ đích chỉ lấy một document trong tập có thể nhiều phần tử. Cách truy vấn được triển khai bằng `MongoTemplate` cũng cần được xét riêng.

### 2.1. Không tìm thấy không phải là lỗi hệ thống

Một `Optional.empty()` có thể hoàn toàn bình thường: ID không tồn tại, người dùng chưa đăng ký hoặc bộ lọc chưa khớp document nào. Tương tự, `List.of()` về mặt ý nghĩa là kết quả hợp lệ của thao tác tìm kiếm khi có 0 bản ghi.

Nên phân biệt:

1. **Không có dữ liệu:** truy vấn thực hiện thành công, nhưng trả 0 document.
2. **Có dữ liệu nhưng không duy nhất:** nhiều document khớp khi hợp đồng đòi tối đa một.
3. **Lỗi truy cập MongoDB:** timeout, mất kết nối, xác thực thất bại, lỗi mapping hoặc lệnh bị từ chối.

Ba tình huống này cần nhánh xử lý khác nhau. Không nên gom tất cả thành `null` hoặc HTTP 404.

### 2.2. Optional không kiểm tra tính duy nhất của dữ liệu

`Optional<T>` là một wrapper cho **sự hiện diện hoặc vắng mặt** của một giá trị trong Java. Nó **không tạo unique index**, không kiểm soát quy tắc nghiệp vụ và không tự ngăn hai document cùng email được ghi.

`Optional<User> findByEmailKey(String emailKey)` chỉ có hợp đồng hợp lý nếu dữ liệu được thiết kế để truy vấn trả tối đa một kết quả. Muốn bảo đảm điều đó, cần cả quy tắc ghi dữ liệu lẫn ràng buộc tương ứng trong MongoDB.

## 3. Ví dụ domain: người dùng, email và biệt danh

Giả sử collection `app_users` lưu:

```javascript
{
  _id: "user-101",
  emailKey: "lan@example.com",
  nickname: "luna",
  status: "ACTIVE",
  createdAt: ISODate("2026-11-20T08:00:00Z")
}
```

`emailKey` là giá trị đã chuẩn hóa theo quy tắc ứng dụng. Trong ví dụ, mỗi emailKey cần duy nhất, trong khi `nickname` được phép trùng.

### 3.1. Entity

```java
package example.users;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.Indexed;
import org.springframework.data.mongodb.core.mapping.Document;

enum UserStatus {
    ACTIVE,
    INACTIVE
}

@Document(collection = "app_users")
public class AppUser {

    @Id
    private String id;

    @Indexed(unique = true)
    private String emailKey;

    private String nickname;

    private UserStatus status;

    private Instant createdAt;

    public AppUser() {
    }

    public AppUser(
            String id,
            String emailKey,
            String nickname,
            UserStatus status,
            Instant createdAt) {
        this.id = id;
        this.emailKey = emailKey;
        this.nickname = nickname;
        this.status = status;
        this.createdAt = createdAt;
    }

    public String getId() {
        return id;
    }

    public String getEmailKey() {
        return emailKey;
    }

    public String getNickname() {
        return nickname;
    }

    public UserStatus getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
```

`@Indexed(unique = true)` thể hiện mong muốn tạo unique index trong metadata Spring Data. Tuy nhiên, **không mặc định suy ra index đã tồn tại trên MongoDB**: tự động tạo index còn phụ thuộc cấu hình và phiên bản Spring Data MongoDB. Trước khi dựa vào tính duy nhất, phải xác minh index trên collection thật hoặc tạo bằng migration/index management.

### 3.2. Repository

```java
package example.users;

import java.util.List;
import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface AppUserRepository
        extends MongoRepository<AppUser, String> {

    // Hợp đồng tối đa một kết quả theo emailKey.
    Optional<AppUser> findByEmailKey(String emailKey);

    // Cố ý dùng để thấy rủi ro: nickname KHÔNG duy nhất.
    Optional<AppUser> findByNickname(String nickname);

    // Danh sách có thể không có phần tử nào.
    List<AppUser> findAllByStatus(UserStatus status);

    // Liệt kê đầy đủ những người dùng cùng biệt danh.
    List<AppUser> findAllByNicknameOrderByCreatedAtDescIdDesc(
        String nickname
    );

    // Chỉ lấy một document theo thứ tự có chủ đích.
    Optional<AppUser> findFirstByNicknameOrderByCreatedAtDescIdDesc(
        String nickname
    );

    boolean existsByEmailKey(String emailKey);

    long countByNickname(String nickname);
}
```

Những tên method trên minh họa **query derivation**: Spring Data phân tích tên method để tạo điều kiện truy vấn. `findByNickname` thể hiện kỳ vọng lấy một entity, còn `findAllByNickname...` thể hiện nhu cầu lấy nhiều entity. `findFirstByNickname...` giới hạn kết quả và chỉ hợp lý khi bài toán thật sự cần *một đại diện được chọn theo thứ tự*.

## 4. Optional trong CRUD: xử lý vắng mặt rõ ràng

### 4.1. findById trả Optional

`MongoRepository` kế thừa các thao tác CRUD và cung cấp `findById(ID)` trả về `Optional<T>`.

```java
Optional<AppUser> found = repository.findById("user-101");

if (found.isPresent()) {
    AppUser user = found.get();
    System.out.println(user.getEmailKey());
} else {
    System.out.println("Không tìm thấy người dùng");
}
```

Cách viết `isPresent()` rồi `get()` hợp lệ, nhưng trong service thực tế thường rõ hơn khi dùng `map`, `orElseGet` hoặc `orElseThrow`:

```java
AppUser user = repository.findById(id)
    .orElseThrow(() -> new UserNotFoundException(id));
```

Ngoại lệ domain có thể được khai báo:

```java
package example.users;

public class UserNotFoundException extends RuntimeException {
    public UserNotFoundException(String id) {
        super("Không tìm thấy người dùng: " + id);
    }
}
```

Đoạn code trên tách ý nghĩa nghiệp vụ “người dùng không tồn tại” khỏi lỗi MongoDB. Ở tầng HTTP, ứng dụng có thể chuyển `UserNotFoundException` thành **404 Not Found**.

### 4.2. Không lạm dụng Optional.get()

```java
// Không an toàn nếu ID không tồn tại:
AppUser user = repository.findById(id).get();
```

Khi Optional rỗng, `get()` ném `NoSuchElementException`. Đây không phải lỗi MongoDB và có thể bị handler mặc định trả thành lỗi server khó hiểu. Hãy quyết định rõ ứng dụng phải làm gì khi không có kết quả.

### 4.3. Không dùng null hoặc placeholder để thay Optional

Ví dụ dễ gây sai nghĩa:

```java
// Tránh trả một tài khoản giả khi không tìm thấy:
AppUser user = repository.findById(id)
    .orElse(new AppUser("unknown", "none", "guest",
        UserStatus.INACTIVE, java.time.Instant.EPOCH));
```

Nếu kết quả giả bị lưu lại hoặc trả về client, ứng dụng có thể hiểu sai rằng tài khoản đó tồn tại. Với dữ liệu bắt buộc, dùng `orElseThrow`; với dữ liệu tùy chọn, giữ `Optional` đến ranh giới phù hợp hoặc dùng DTO biểu diễn trạng thái vắng mặt.

**Phân biệt hai tầng:** `Optional<AppUser>` có giá trị khi tồn tại document; điều đó **không bảo đảm** `user.getNickname()` hay các trường tùy chọn bên trong document khác null.

## 5. Collection rỗng: kết quả hợp lệ của truy vấn nhiều bản ghi

Giả sử chưa có tài khoản `INACTIVE`:

```java
List<AppUser> inactive =
    repository.findAllByStatus(UserStatus.INACTIVE);

System.out.println(inactive.isEmpty()); // true
System.out.println(inactive.size());    // 0
```

Với query repository trả collection, Spring Data trả một collection rỗng khi không có kết quả; không cần viết nhánh `if (inactive == null)` cho repository method có hợp đồng chuẩn.

### 5.1. HTTP thường nên biểu diễn danh sách rỗng bằng []

Một endpoint tìm kiếm:

```java
import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/users")
class UserSearchController {
    private final AppUserRepository repository;

    UserSearchController(AppUserRepository repository) {
        this.repository = repository;
    }

    @GetMapping
    ResponseEntity<List<AppUser>> search(
            @RequestParam UserStatus status) {
        return ResponseEntity.ok(repository.findAllByStatus(status));
    }
}
```

Nếu chưa có user khớp, HTTP có thể trả:

```json
[]
```

Với danh sách tìm kiếm, **200 OK cùng []** thường là hợp đồng dễ sử dụng: truy vấn thành công và có 0 phần tử. Một API có thể quy định khác, nhưng đừng mặc định dùng 404 chỉ vì một truy vấn danh sách không tìm ra hàng nào. `404` phù hợp hơn khi **tài nguyên đơn** theo ID không tồn tại.

Ví dụ trả entity trực tiếp chỉ nhằm minh họa collection; ứng dụng sản xuất nên cân nhắc DTO và chính sách ẩn các trường không được phép xuất hiện trong HTTP response.

### 5.2. Danh sách lớn cần phân trang

Không vì `findAllByStatus` trả `List` mà nên tải hàng triệu tài khoản vào RAM:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

Page<AppUser> findAllByStatus(UserStatus status, Pageable pageable);
```

Phương thức trên là **một khai báo bổ sung trong repository**, không phải code Java đứng độc lập ngoài interface. Khi gọi:

```java
var pageable = org.springframework.data.domain.PageRequest.of(
    0, 20,
    org.springframework.data.domain.Sort.by(
        org.springframework.data.domain.Sort.Order.desc("createdAt"),
        org.springframework.data.domain.Sort.Order.desc("id")
    )
);

Page<AppUser> page = repository.findAllByStatus(
    UserStatus.ACTIVE, pageable
);

List<AppUser> content = page.getContent();
boolean emptyPage = page.isEmpty();
```

`Page` có metadata như tổng số phần tử/trang; tùy truy vấn, việc tính tổng có chi phí bổ sung. Nếu chỉ cần biết còn trang sau và không cần tổng số, cân nhắc `Slice`. Cần sort ổn định, index phù hợp và chiến lược phân trang thích hợp khi dữ liệu lớn.

## 6. Lỗi kết quả không duy nhất phát sinh khi nào?

Giả sử collection có hai tài khoản cùng biệt danh:

```javascript
db.app_users.insertMany([
  {
    _id: "user-201",
    emailKey: "mai@example.com",
    nickname: "luna",
    status: "ACTIVE",
    createdAt: ISODate("2026-11-20T09:00:00Z")
  },
  {
    _id: "user-202",
    emailKey: "linh@example.com",
    nickname: "luna",
    status: "ACTIVE",
    createdAt: ISODate("2026-11-20T09:05:00Z")
  }
]);
```

Đây là dữ liệu hợp lệ vì biệt danh **không được yêu cầu duy nhất**. Nhưng method sau lại yêu cầu một entity duy nhất:

```java
Optional<AppUser> user = repository.findByNickname("luna");
```

Theo hợp đồng single-result query của Spring Data, nhiều kết quả khớp có thể dẫn tới:

```text
org.springframework.dao.IncorrectResultSizeDataAccessException
```

Đây là nhóm ngoại lệ thuộc **Spring DataAccessException hierarchy**. Cần phân biệt nó với `NoSuchElementException` khi gọi `Optional.get()` trên Optional rỗng, và với `DuplicateKeyException` khi lệnh ghi vi phạm unique index.

### 6.1. Vì sao Optional không cứu được trường hợp nhiều kết quả?

`Optional` chỉ biểu diễn “có hoặc không có **một** object”. Nó không chứa được danh sách hai object. Khi query trả hơn một document mà method không có giới hạn lấy một kết quả, repository không thể quyết định tự nhiên chọn document nào mà vẫn giữ đúng hợp đồng.

Nếu nghiệp vụ cho phép trùng biệt danh, sửa hợp đồng thành:

```java
List<AppUser> users =
    repository.findAllByNicknameOrderByCreatedAtDescIdDesc("luna");
```

Nếu nghiệp vụ muốn **tài khoản được tạo gần đây nhất**, khai báo giới hạn và sort:

```java
Optional<AppUser> latest =
    repository.findFirstByNicknameOrderByCreatedAtDescIdDesc("luna");
```

`findFirstBy...` chủ động chọn tối đa một kết quả. Nó **không chứng minh dữ liệu duy nhất** và có thể che giấu bản ghi trùng nếu ứng dụng thực sự đòi uniqueness. Sort theo `createdAt` và `id` làm tiêu chí lựa chọn rõ ràng khi nhiều document có timestamp giống nhau.

### 6.2. Đừng chữa lỗi bằng cách luôn bắt và bỏ qua exception

```java
// Không nên làm nếu nghiệp vụ đòi duy nhất:
try {
    return repository.findByEmailKey(emailKey);
} catch (IncorrectResultSizeDataAccessException ex) {
    return Optional.empty();
}
```

Đoạn này biến **dữ liệu vi phạm bất biến** thành “không tìm thấy”, có thể làm che giấu trùng tài khoản hoặc lỗi dữ liệu lịch sử. Nếu email phải duy nhất, cần tìm nguyên nhân, xử lý các bản ghi trùng và tạo ràng buộc ở database.

Một số ứng dụng có thể chuyển lỗi dữ liệu không nhất quán thành phản hồi nghiệp vụ riêng. Nhưng luôn phải lưu tín hiệu quan sát (log/metrics có kiểm soát) và kế hoạch khắc phục, không biến nó thành kết quả rỗng giả.

## 7. Bảo đảm kết quả duy nhất bằng dữ liệu và index

### 7.1. _id có unique index sẵn

MongoDB có unique index trên trường `_id` của collection. Do đó `repository.findById(id)` về bản chất trả tối đa một document; khi nó rỗng, nguyên nhân phổ biến là không có khóa tương ứng.

Với thuộc tính khác như email, MongoDB **không tự bảo đảm duy nhất** trừ khi có ràng buộc/index tương ứng. Annotation `@Indexed(unique = true)` chỉ là metadata; cần xác minh index đã được tạo.

```javascript
db.app_users.createIndex(
  { emailKey: 1 },
  { unique: true, name: "uk_app_users_emailKey" }
);

db.app_users.getIndexes();
```

Nếu collection đã có dữ liệu trùng `emailKey`, lệnh tạo unique index sẽ thất bại. Phải xử lý dữ liệu trùng theo quy tắc nghiệp vụ trước khi áp đặt ràng buộc.

### 7.2. Chuẩn hóa dữ liệu trước khi xác định duy nhất

Hai chuỗi `"Lan@Example.com"` và `"lan@example.com"` có thể được xử lý thành hai khóa khác nhau nếu ứng dụng chưa có quy tắc chuẩn hóa. Ví dụ đơn giản:

```java
import java.util.Locale;

String normalizeEmailKey(String input) {
    return input.trim().toLowerCase(Locale.ROOT);
}
```

Đây là **quy ước khóa tra cứu riêng của ứng dụng**, không phải bộ quy tắc chuẩn hóa email đầy đủ cho mọi hệ thống. Cần xác định chính xác chính sách phân biệt chữ hoa/thường, ký tự Unicode, phần domain/local-part và tính hợp lệ email theo sản phẩm.

Một lựa chọn khác là MongoDB collation để so sánh không phân biệt hoa/thường, nhưng **query cần sử dụng collation tương thích với index** nếu muốn tận dụng index đó. Không kết hợp ngẫu nhiên nhiều cách chuẩn hóa khiến hai nơi hiểu “bằng nhau” theo quy tắc khác nhau.

### 7.3. Unique index và giá trị null hoặc missing

Với **single-field unique index** thông thường, các document có field thiếu hoặc BSON null cũng liên quan đến unique key null. Điều này có thể khiến tạo index thất bại khi có nhiều document thiếu email.

Vì vậy với `emailKey`, tốt nhất xác định rõ trường này có bắt buộc hay không:

- Nếu bắt buộc: xác thực đầu vào, tạo giá trị chuẩn hóa và ghi theo quy ước trước khi unique index.
- Nếu tùy chọn: thiết kế **partial unique index** hoặc mô hình khóa riêng phù hợp với policy, rồi kiểm thử dữ liệu null/missing và truy vấn.

Không nên thêm `sparse` hoặc `partialFilterExpression` chỉ để “index chạy được” mà không hiểu tác động đến các document thiếu/null và quy tắc duy nhất.

### 7.4. Kiểm kê dữ liệu trùng trước khi tạo index

```javascript
db.app_users.aggregate([
  { $match: { emailKey: { $type: "string" } } },
  {
    $group: {
      _id: "$emailKey",
      occurrences: { $sum: 1 }
    }
  },
  { $match: { occurrences: { $gt: 1 } } },
  { $sort: { occurrences: -1 } }
]);
```

Aggregation này tìm giá trị `emailKey` trùng nhau theo **đúng giá trị chuỗi đã lưu**, không tự chuẩn hóa các biến thể. Nếu bản ghi cũ có emailKey chưa chuẩn hóa, cần đối chiếu theo policy trước khi kết luận không có trùng logic. Với collection lớn, thao tác `$group` có thể tiêu tốn tài nguyên; nên kiểm soát thời điểm và tài nguyên vận hành.

### 7.5. existsBy không thay thế unique index

Một đoạn code thường gặp:

```java
if (!repository.existsByEmailKey(emailKey)) {
    repository.save(newUser);
}
```

Hai request đồng thời có thể cùng thấy `false` rồi cùng thực hiện `save`. Đây là **race condition kiểu check-then-act**. Nếu tính duy nhất là bắt buộc, unique index của MongoDB mới là hàng rào cuối cùng. Ứng dụng xử lý lỗi ghi trùng (ví dụ `DuplicateKeyException`) và quy định response phù hợp, thường là **409 Conflict** cho hành động tạo tài nguyên bị trùng.

Transaction không thay thế unique index khi mục tiêu là bảo đảm một khóa duy nhất trên dữ liệu.

## 8. MongoTemplate: findOne khác với yêu cầu duy nhất nghiêm ngặt

`MongoTemplate` cho phép viết query trực tiếp, ví dụ:

```java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(
    Criteria.where("nickname").is("luna")
);

AppUser first = mongoTemplate.findOne(query, AppUser.class);
```

`findOne` tập trung vào việc lấy **một document** khớp query và không phải công cụ chứng minh rằng **chỉ một document tồn tại**. Không dùng nó thay thế việc kiểm tra uniqueness khi ứng dụng cần phát hiện bản ghi trùng. Nếu không có điều kiện sort, document được chọn cũng có thể không phản ánh một thứ tự nghiệp vụ ổn định.

### 8.1. Kiểm tra tối đa một kết quả bằng find và limit(2)

Khi chưa thể đặt unique index hoặc cần phát hiện dữ liệu lỗi trong quá trình chuyển đổi, có thể kiểm tra:

```java
import java.util.List;
import java.util.Optional;
import org.springframework.dao.IncorrectResultSizeDataAccessException;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public Optional<AppUser> findUniqueNickname(
        MongoTemplate mongoTemplate, String nickname) {

    Query query = Query.query(
        Criteria.where("nickname").is(nickname)
    );
    query.limit(2);

    List<AppUser> matches =
        mongoTemplate.find(query, AppUser.class);

    if (matches.size() > 1) {
        throw new IncorrectResultSizeDataAccessException(1, matches.size());
    }

    return matches.stream().findFirst();
}
```

Giới hạn hai kết quả đủ để phát hiện “nhiều hơn một” mà không tải cả collection. Tuy nhiên, phép kiểm tra này là **ảnh chụp của một thời điểm**; nếu hệ thống đang ghi đồng thời, nó không bảo đảm tính duy nhất lâu dài. Unique index vẫn là giải pháp dữ liệu khi có ràng buộc duy nhất nghiệp vụ.

### 8.2. Đọc một document không đồng nghĩa cập nhật một document

`findOne`, `findFirst` và `limit(1)` là quyết định của **đường đọc**. Nếu muốn cập nhật chính xác một document, cần xác định khóa hoặc tiêu chí rõ ràng, dùng thao tác phù hợp như `updateFirst` hoặc repository save với ID đã biết. Khi nhiều request cùng cập nhật, cân nhắc optimistic locking bằng `@Version` hoặc điều kiện update; đây là vấn đề đồng thời riêng với cardinality của truy vấn.

## 9. Reactive repository: Mono.empty() và Flux rỗng

Khi dùng Spring Data MongoDB reactive, ý nghĩa về **0 hay nhiều document** được biểu diễn bằng publisher:

```java
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ReactiveAppUserRepository
        extends ReactiveMongoRepository<AppUser, String> {

    Mono<AppUser> findByEmailKey(String emailKey);

    Flux<AppUser> findAllByStatus(UserStatus status);

    Flux<AppUser> findAllByNickname(String nickname);

    Mono<AppUser> findFirstByNicknameOrderByCreatedAtDescIdDesc(
        String nickname
    );
}
```

- `Mono<AppUser>` có thể phát một user rồi hoàn tất, hoặc hoàn tất mà không phát phần tử khi không tìm thấy.
- `Flux<AppUser>` có thể phát 0, 1 hoặc nhiều user; khi không có kết quả, nó chỉ phát tín hiệu hoàn tất.
- Lỗi MongoDB, lỗi mapping hoặc lỗi cardinality theo hợp đồng của method sẽ đi qua tín hiệu lỗi, không phải một object `Optional.empty()`.

**Lưu ý về tính duy nhất:** Không biến `Mono` thành một biện pháp ràng buộc database. Với truy vấn có thể khớp nhiều bản ghi, nên trả `Flux`; nếu muốn đúng một kết quả, dùng query/method được thiết kế và kiểm thử để phát hiện trường hợp dư kết quả, đồng thời dùng unique index khi nghiệp vụ yêu cầu.

### 9.1. Mono.empty() → HTTP 404 hoặc lỗi domain

```java
import reactor.core.publisher.Mono;

Mono<AppUser> requiredUser = reactiveRepository.findById(id)
    .switchIfEmpty(Mono.error(new UserNotFoundException(id)));
```

`switchIfEmpty` chỉ chạy nếu publisher hoàn tất **không có phần tử**. Nó không bắt mọi lỗi rồi chuyển thành không tìm thấy; lỗi kết nối hay lỗi dữ liệu vẫn đi theo đường lỗi ban đầu.

Trong controller WebFlux:

```java
import org.springframework.http.ResponseEntity;
import reactor.core.publisher.Mono;

Mono<ResponseEntity<AppUser>> response =
    reactiveRepository.findById(id)
        .map(ResponseEntity::ok)
        .defaultIfEmpty(ResponseEntity.notFound().build());
```

### 9.2. Flux rỗng và collectList()

```java
import java.util.List;
import reactor.core.publisher.Mono;

Mono<List<AppUser>> users = reactiveRepository
    .findAllByStatus(UserStatus.INACTIVE)
    .collectList();
```

Nếu `Flux` nguồn không phát bản ghi nào, `collectList()` phát **một List rỗng**, không phải `Mono.empty()`. Cách này phù hợp tập kết quả nhỏ hoặc đã được giới hạn; với tập lớn nên dùng pagination/streaming để tránh gom quá nhiều dữ liệu vào bộ nhớ.

**Không gọi `block()` hoặc `subscribe()` tùy tiện trong service WebFlux** để chuyển một pipeline thành xử lý đồng bộ hoặc tách khỏi vòng đời request. Tốt hơn hãy trả về `Mono`/`Flux` cho tầng gọi và tổ chức xử lý lỗi trong pipeline.

### 9.3. Nếu cần kiểm tra đúng một phần tử trong Flux

Reactor có toán tử `single()` khi luồng phải phát **đúng một phần tử**: nó phát lỗi nếu nguồn rỗng hoặc có nhiều hơn một phần tử. `singleOrEmpty()` cho phép 0 hoặc 1 phần tử và báo lỗi khi có nhiều hơn một.

```java
Mono<AppUser> zeroOrOne =
    reactiveRepository.findAllByNickname("luna")
        .singleOrEmpty();
```

Ví dụ kiểm tra cardinality trên luồng, nhưng vẫn **không thay thế unique index**. Với MongoDB query có thể khớp nhiều phần tử, cân nhắc hạn chế số document được lấy khi chỉ cần phát hiện bản ghi thứ hai để tiết kiệm tài nguyên.

## 10. Phân biệt loại ngoại lệ và phản hồi HTTP

| Tình huống | Dấu hiệu | Cách ứng dụng thường xử lý |
| --- | --- | --- |
| Không có user theo ID | `Optional.empty()` hoặc `Mono.empty()` | 404 nếu endpoint lấy tài nguyên đơn |
| Không có bản ghi phù hợp với danh sách | `List.isEmpty()` hoặc `Flux` hoàn tất rỗng | 200 với `[]` cho API danh sách |
| Nhiều bản ghi trong truy vấn single-result | `IncorrectResultSizeDataAccessException` hoặc lỗi cardinality theo API | Kiểm tra hợp đồng method, dữ liệu trùng, index; không coi là “không tìm thấy” |
| Thêm user trùng unique index | `DuplicateKeyException` / lỗi ghi trùng được Spring dịch | 409 Conflict nếu phù hợp hợp đồng HTTP; giải thích khóa trùng |
| Gọi `Optional.get()` khi empty | `NoSuchElementException` | Sửa code xử lý Optional; đây không phải lỗi MongoDB |
| Không kết nối được database | Ngoại lệ truy cập dữ liệu/driver | Quan sát, retry có kiểm soát nếu an toàn, trả lỗi dịch vụ phù hợp |
| Mapping BSON không khớp entity | Exception chuyển đổi/ánh xạ | Kiểm tra schema cũ, converter, kiểu BSON; sửa dữ liệu hoặc mapping |

HTTP status là quyết định của API, không được Spring Data tự áp đặt cho mọi repository method. Ví dụ một controller có thể chủ động ánh xạ `Optional.empty()` thành 404, hoặc trả đối tượng đại diện cho trạng thái chưa tồn tại trong một workflow riêng.

### 10.1. Một lỗi 500 không đủ để kết luận MongoDB hỏng

Nếu controller gọi `repository.findByNickname("luna")` rồi ném `IncorrectResultSizeDataAccessException` vì hai nickname trùng nhau, MongoDB **vẫn hoạt động**. Vấn đề là dữ liệu không khớp với hợp đồng truy vấn.

Trình tự điều tra hợp lý:

1. Kiểm tra method trả `Optional<T>`, `T` hay `List<T>`.
2. Chạy truy vấn tương đương trên MongoDB để xem số kết quả thật.
3. Xác nhận trường đó có bắt buộc duy nhất hay không.
4. Nếu bắt buộc, kiểm tra unique index thực tế và lịch sử ghi dữ liệu.
5. Nếu không bắt buộc, đổi hợp đồng method sang collection hoặc dùng `First/Top` với sort có chủ đích.

## 11. Kiểm thử repository: phải kiểm tra cả ba cardinality

Một bài kiểm thử chỉ có trường hợp “có đúng một document” dễ bỏ sót lỗi thiết kế. Nên chuẩn bị **0, 1 và 2 bản ghi** cho cùng một điều kiện.

### 11.1. Test đơn giản cho Optional và collection rỗng

Giả sử `AppUserRepository` đã được Spring Data tạo trong context và có một MongoDB test sẵn sàng:

```java
package example.users;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;

@DataMongoTest
class AppUserRepositoryCardinalityTest {

    @Autowired
    AppUserRepository repository;

    @Test
    void missingByIdReturnsEmptyOptional() {
        String missingId = "missing-" + UUID.randomUUID();

        assertTrue(repository.findById(missingId).isEmpty());
    }

    @Test
    void singleEmailMatchIsPresent() {
        String suffix = UUID.randomUUID().toString();
        String email = "user-" + suffix + "@example.com";
        AppUser user = new AppUser(
            "id-" + suffix,
            email,
            "nickname-" + suffix,
            UserStatus.ACTIVE,
            Instant.parse("2026-11-20T09:00:00Z")
        );

        repository.save(user);

        var result = repository.findByEmailKey(email);
        assertTrue(result.isPresent());
        assertEquals(user.getId(), result.orElseThrow().getId());
    }

    @Test
    void absentNicknameReturnsEmptyCollection() {
        String nickname = "none-" + UUID.randomUUID();

        assertTrue(
            repository.findAllByNicknameOrderByCreatedAtDescIdDesc(
                nickname
            ).isEmpty()
        );
    }
}
```

Ví dụ đặt các class cùng package để Spring Data phát hiện repository/entity. `@DataMongoTest` cấu hình context test MongoDB nhưng **không tự bảo đảm MongoDB server sẽ được khởi chạy**: dự án có thể sử dụng Testcontainers hoặc instance kiểm thử đã cấu hình. Tên annotation/import có thể khác theo major version Spring Boot.

### 11.2. Test tình huống nhiều document cùng biệt danh

Thêm một method kiểm thử vào class trên:

```java
import org.springframework.dao.IncorrectResultSizeDataAccessException;

@Test
void nonUniqueNicknameViolatesSingleResultContract() {
    String suffix = UUID.randomUUID().toString();
    String nickname = "shared-" + suffix;

    repository.save(new AppUser(
        "u1-" + suffix,
        "a-" + suffix + "@example.com",
        nickname,
        UserStatus.ACTIVE,
        Instant.parse("2026-11-20T09:00:00Z")
    ));
    repository.save(new AppUser(
        "u2-" + suffix,
        "b-" + suffix + "@example.com",
        nickname,
        UserStatus.ACTIVE,
        Instant.parse("2026-11-20T09:05:00Z")
    ));

    assertEquals(
        2,
        repository.findAllByNicknameOrderByCreatedAtDescIdDesc(
            nickname
        ).size()
    );

    assertThrows(
        IncorrectResultSizeDataAccessException.class,
        () -> repository.findByNickname(nickname)
    );

    assertEquals(
        "u2-" + suffix,
        repository
            .findFirstByNicknameOrderByCreatedAtDescIdDesc(nickname)
            .orElseThrow()
            .getId()
    );
}
```

Trong Java thực tế, `import` phải đặt ở đầu file và method này nằm bên trong class test. Các ID/email được tạo riêng cho mỗi lần test để giảm nguy cơ đụng dữ liệu. Test này xác minh sự khác nhau giữa **query nhiều kết quả**, **single-result query** và **query giới hạn một bản ghi**.

### 11.3. Test unique index ở tầng MongoDB

Nếu emailKey bắt buộc duy nhất, cần test cả việc **MongoDB từ chối document thứ hai** có cùng khóa. Trước khi test, xác nhận unique index đã được tạo (theo migration, index management hoặc cấu hình bật tạo index).

```javascript
db.app_users.getIndexes();
```

Sau đó thử ghi hai document có cùng `emailKey`, nhưng khác `_id`. Kỳ vọng thao tác ghi thứ hai thất bại do duplicate key. Test phải chạy trên môi trường được phép chỉnh sửa dữ liệu thử; không nên dùng collection production.

Nếu không có unique index, việc gọi `repository.save` hai lần có thể thành công, dù `findByEmailKey` sau đó lỗi vì kết quả không duy nhất. Điều này cho thấy **phát hiện lỗi ở đường đọc thường quá muộn so với ngăn lỗi ở đường ghi**.

### 11.4. Kiểm thử reactive

Với Reactor Test:

```java
import reactor.test.StepVerifier;

StepVerifier.create(
    reactiveRepository.findById("missing-id")
).verifyComplete(); // Mono.empty

StepVerifier.create(
    reactiveRepository.findAllByStatus(UserStatus.INACTIVE)
        .filter(user -> user.getNickname().startsWith("no-match-"))
).verifyComplete(); // Flux không phát phần tử phù hợp
```

Chú ý test thứ hai dựa vào giả định các document kiểm thử không có biệt danh bắt đầu bằng `no-match-`; trong bài test thực tế, dùng test database/fixture cô lập để bảo đảm điều kiện đó. Với query single-result theo trường không duy nhất, xác minh hành vi cụ thể của repository/driver/version đang dùng và không dựa vào `Mono` để thay thế ràng buộc uniqueness.

## 12. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| `findByNickname` trả `Optional` khi nickname có thể trùng | Exception hoặc hợp đồng cardinality sai | Dùng `List`/`Flux`, hoặc `First/Top` có sort nếu chỉ cần một |
| Mọi truy vấn rỗng đều trả 404 | API tìm kiếm không thể biểu diễn `[]` hợp lệ | Phân biệt tài nguyên đơn và tập kết quả |
| Dùng `Optional.get()` ngay | `NoSuchElementException` khi thiếu dữ liệu | `orElseThrow`, `map`, `ifPresent` hoặc nhánh xử lý rõ |
| Dùng `findFirst` để che dữ liệu vi phạm unique | Bỏ qua account trùng, lỗi nghiệp vụ vẫn tồn tại | Xử lý trùng và tạo unique index |
| Dùng `existsBy` trước `save` như hàng rào duy nhất | Hai request cùng tạo khóa giống nhau | Unique index + xử lý duplicate key |
| Chỉ khai báo `@Indexed(unique=true)` rồi mặc định đã an toàn | Auto index creation có thể đang tắt | Xem `getIndexes()`, tạo index bằng migration có kiểm soát |
| Dùng `findAll` rồi lấy `get(0)` | Lãng phí I/O và có thể vỡ khi danh sách rỗng | Chọn đúng truy vấn một phần tử hoặc xử lý danh sách |
| Tải danh sách rất lớn để chỉ kiểm tra trùng | Tăng bộ nhớ, thời gian truy vấn | Unique index hoặc `limit(2)` để phát hiện nhiều kết quả |
| Map mọi `DataAccessException` thành “không có dữ liệu” | Che timeout, mapping error và lỗi DB | Phân loại lỗi, quan sát và trả response đúng |
| Không kiểm thử 0 và 2 kết quả | Method trông đúng với dữ liệu demo, lỗi trong thực tế | Test đủ 0/1/2+ match và dữ liệu concurrent |

## 13. Bài tập thực hành

### Bài 1 — Thiết kế kiểu trả về

Với collection `books`, hãy chọn kiểu trả về Spring Data repository phù hợp:

1. Tìm sách theo `_id`.
2. Liệt kê sách theo tác giả, có thể không có cuốn nào.
3. Tìm đúng một ISBN có unique index.
4. Lấy cuốn sách mới nhất của một tác giả theo `publishedAt` và `_id`.
5. Kiểm tra tác giả có ít nhất một sách hay không.

Giải thích tại sao từng method nên dùng `Optional<T>`, `List<T>`, `Page<T>`, `boolean` hoặc `First/Top`.

### Bài 2 — Tạo tình huống không duy nhất

Tạo hai document user có cùng nickname và hai email khác nhau. Gọi `findByNickname`, `findAllByNickname...` và `findFirstByNickname...`. Ghi lại từng kết quả hoặc exception, rồi giải thích vì sao cả ba method không có cùng hợp đồng.

### Bài 3 — Thiết kế uniqueness đúng ở database

Chuẩn hóa `emailKey`, kiểm kê giá trị trùng, tạo unique index và thử hai request tạo tài khoản cùng email. Mô tả vì sao `existsByEmailKey` trước `save` không thể loại bỏ race condition. Thiết kế response HTTP cho trường hợp đã có email.

### Bài 4 — Template và repository

Viết `MongoTemplate.findOne` theo nickname, sau đó viết biến thể dùng `limit(2)` và kiểm tra số bản ghi. Đối chiếu với repository method `findByNickname` và giải thích sự khác nhau giữa “lấy một đại diện” và “bảo đảm chỉ có một kết quả”.

### Bài 5 — Reactive Mono/Flux

Viết `ReactiveMongoRepository` trả `Mono` cho truy vấn theo ID và `Flux` cho truy vấn nhiều kết quả. Dùng `StepVerifier` xác minh Mono/Flux rỗng, sau đó thực hành `switchIfEmpty` và `collectList`. Giải thích vì sao `collectList()` của một Flux rỗng không trả `Mono.empty()`.

### Câu hỏi tự kiểm tra

- Vì sao `Optional.empty()` và `IncorrectResultSizeDataAccessException` mang ý nghĩa khác nhau?
- Nếu `findById` trả empty, có cần coi đó là lỗi MongoDB hay không?
- Khi nào `findFirstBy...` là lựa chọn đúng và khi nào nó che lỗi dữ liệu?
- Tại sao unique index cần được tạo và xác minh trên collection thật?
- Vì sao kiểm tra `existsByEmailKey` rồi mới `save` vẫn có thể ghi trùng khi có concurrency?
- `MongoTemplate.findOne` có tự chứng minh kết quả duy nhất không?
- `Mono.empty()` và `Flux.empty()` khác nhau về hợp đồng tiêu thụ thế nào?

## Ghi nhớ

**`Optional<T>`** phù hợp với truy vấn mong đợi **0 hoặc 1 document**; **`List<T>`/`Flux<T>`** phù hợp với truy vấn có **0 đến nhiều document** và trả kết quả rỗng khi không khớp; còn truy vấn single-result không giới hạn có thể báo **`IncorrectResultSizeDataAccessException`** nếu dữ liệu trả nhiều hơn một. `First`/`Top` là giới hạn kết quả có chủ đích, không tạo ra tính duy nhất. Với khóa nghiệp vụ như email, cần **unique index thực sự trong MongoDB**, xử lý lỗi ghi trùng và kiểm thử đủ các trường hợp 0, 1, 2+ document. Chọn đúng kiểu trả về và phân biệt “không tìm thấy”, “không duy nhất” với “lỗi truy cập database” là nền tảng để xây CRUD đáng tin cậy trong Spring Data MongoDB.

## Tài liệu tham khảo

- [Spring Data MongoDB Reference — MongoDB Repositories](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/repositories.html)
- [Spring Data Commons — Repository Query Return Types](https://docs.spring.io/spring-data/commons/reference/repositories/query-return-types-reference.html)
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
