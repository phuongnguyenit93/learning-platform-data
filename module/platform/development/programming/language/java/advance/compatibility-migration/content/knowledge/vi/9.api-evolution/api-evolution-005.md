# Quản lý thay đổi null, ngoại lệ, thứ tự kết quả và tác dụng phụ

## 1. Tiến hóa API không chỉ là thay đổi chữ ký phương thức

Khi nâng cấp Java, framework hoặc một thư viện, nhóm phát triển thường bắt đầu bằng việc kiểm tra những vấn đề dễ nhìn thấy: class có còn tồn tại không, method có đổi tham số hoặc kiểu trả về không, dependency có gây lỗi liên kết không, và source có biên dịch lại được không. Tuy nhiên, một API có thể **giữ nguyên chữ ký và vẫn phá vỡ hợp đồng với bên sử dụng**.

Ví dụ, phương thức:

```java
List<Order> findOrders(String customerId);
```

có thể giữ nguyên khai báo qua hai phiên bản nhưng thay đổi cách hoạt động:

- Trước đây chấp nhận `null` và coi đó là yêu cầu lấy tất cả đơn hàng; phiên bản mới ném `NullPointerException`.
- Trước đây không có kết quả thì trả danh sách rỗng; phiên bản mới trả `null`.
- Trước đây ném `IllegalArgumentException` nếu mã khách hàng sai; phiên bản mới trả danh sách rỗng.
- Trước đây trả kết quả theo thời gian tạo tăng dần; phiên bản mới không bảo đảm thứ tự.
- Trước đây chỉ đọc dữ liệu; phiên bản mới cập nhật trường `lastAccessedAt` mỗi lần gọi.

Tất cả thay đổi trên đều có thể không làm thay đổi JVM method descriptor. Bytecode client cũ vẫn liên kết, nhưng kết quả, nhánh xử lý lỗi, khả năng lặp lại và dữ liệu hệ thống có thể khác đi. Đó là bài toán **behavioral compatibility (tương thích hành vi)** trong tiến hóa API.

Trong ngữ cảnh Java Advance Compatibility Migration, việc quản lý bốn loại hợp đồng sau đặc biệt quan trọng:

1. **Null contract:** API nhận `null` hay không, trả `null` khi nào, phân biệt `null` với giá trị rỗng hoặc vắng mặt ra sao.
2. **Exception contract:** API báo lỗi bằng loại exception nào, khi nào phát sinh, có giữ nguyên nguyên nhân và có cho phép retry hay không.
3. **Ordering contract:** API có bảo đảm thứ tự kết quả, thứ tự xử lý hoặc thứ tự phát sự kiện không.
4. **Side-effect contract:** lời gọi có làm thay đổi trạng thái, phát sự kiện, ghi log, tạo tài nguyên hoặc tác động tới dịch vụ khác không; tác dụng phụ xảy ra mấy lần và lúc nào.

Không nên mặc định rằng tất cả hành vi hiện tại đều là hợp đồng bất biến. Nhưng trước khi thay đổi, phải xác định bên sử dụng đang dựa vào điều gì, hành vi nào đã được tài liệu hóa và điều gì cần duy trì để rollout an toàn.

## 2. Phân biệt tương thích nguồn, nhị phân và hành vi

| Chiều tương thích | Câu hỏi chính | Ví dụ rủi ro |
| --- | --- | --- |
| Source compatibility | Mã Java cũ có biên dịch lại với API mới không? | Đổi `List<T>` thành `Optional<List<T>>` làm call site phải sửa |
| Binary compatibility | Bytecode cũ có liên kết với implementation mới không? | Xóa method cũ có thể gây `NoSuchMethodError` |
| Behavioral compatibility | Một lời gọi hợp lệ có còn giữ kết quả và tác động quan sát được đã cam kết không? | Method vẫn trả `List<T>` nhưng đổi thứ tự hoặc trả `null` |
| Data/protocol compatibility | Dữ liệu và thông điệp giữa các phiên bản có còn được hiểu thống nhất không? | Serializer bỏ trường, đổi ý nghĩa `null`, thay thứ tự ưu tiên |
| Operational compatibility | Cách chạy và quan sát hệ thống có còn phù hợp yêu cầu không? | Một method đọc bắt đầu phát nhiều request hoặc tạo tải nền |

Ví dụ hai triển khai dưới đây có cùng chữ ký:

```java
// API phiên bản A
public List<String> names() {
    return List.of();
}

// API phiên bản B
public List<String> names() {
    return null;
}
```

Không có thay đổi tên method, tham số hoặc kiểu trả về. Tuy nhiên, client:

```java
for (String name : api.names()) {
    System.out.println(name);
}
```

chạy bình thường với phiên bản A và có thể ném `NullPointerException` với phiên bản B. Chỉ dùng API diff ở mức chữ ký là không đủ; cần contract test cho những gì consumer quan sát.

Một thay đổi còn có thể tạo **phá vỡ ngầm**: không có exception, nhưng hệ thống trả dữ liệu khác hoặc phát sinh cập nhật không mong muốn. Những trường hợp như sai thứ tự pagination, thay đổi ý nghĩa trạng thái vắng mặt và side effect lặp lại thường khó phát hiện hơn lỗi compile.

## 3. Xác định hợp đồng trước khi sửa

Để quản lý API một cách nhất quán, mô tả hành vi thành bốn nhóm có thể kiểm chứng:

| Thành phần | Điều cần ghi nhận | Ví dụ |
| --- | --- | --- |
| Preconditions | Điều kiện hợp lệ của input, kể cả `null` | `customerId` phải khác `null` và không blank |
| Postconditions | Kiểu và ý nghĩa của kết quả, kể cả trường hợp không tìm thấy | Không tìm thấy trả list rỗng, không trả `null` |
| Error semantics | Ngoại lệ, lỗi nghiệp vụ, retryability và ngữ cảnh | Invalid input -> `IllegalArgumentException`; lỗi hạ tầng -> `RepositoryException` |
| Ordering & effects | Thứ tự kết quả, trạng thái bị thay đổi, sự kiện phát ra | Sort theo `createdAt` rồi `id`; thao tác đọc không ghi dữ liệu |

Ví dụ một mô tả hợp đồng rõ hơn chữ ký:

```text
findOrders(customerId):
  Input:
    customerId: non-null, non-blank
  Success:
    returns non-null, immutable snapshot list
    if no matches: empty list
    order by createdAt ASC, id ASC
  Errors:
    IllegalArgumentException for invalid customerId
    RepositoryException for storage failure
  Side effects:
    no database writes
    no business events
    may emit metrics/logs
```

Không nhất thiết viết tài liệu theo định dạng này cho mọi method nhỏ. Với API public, shared library, service contract hoặc luồng nghiệp vụ quan trọng, việc mô tả rõ giúp review và so sánh trước/sau nâng cấp.

Phải xem xét cả **hợp đồng được tài liệu hóa** và **giả định thực tế của consumer**. Một thứ tự kết quả chưa từng được hứa hẹn có thể vẫn đang được consumer sử dụng. Khi thay đổi, có thể cần thông báo và migration plan dù implementation cũ không có cam kết chính thức.

## 4. Thay đổi cách chấp nhận `null` ở đầu vào

### 4.1. Từ chấp nhận `null` sang từ chối `null`

API cũ:

```java
public List<User> search(String department) {
    if (department == null) {
        return allUsers();
    }
    return usersIn(department);
}
```

API mới:

```java
public List<User> search(String department) {
    Objects.requireNonNull(department, "department");
    return usersIn(department);
}
```

Chữ ký không đổi, nhưng consumer từng gọi `search(null)` để lấy tất cả sẽ bị lỗi. Không thể coi đây là refactor vô hại. Trước khi thay đổi phải:

1. Tìm những call site có thể truyền `null`, kể cả dữ liệu từ deserialization, mapping và reflection.
2. Xác định ý nghĩa cũ của `null`: “không lọc”, “không xác định”, “dùng mặc định” hay “không hợp lệ”.
3. Chọn API thay thế mang ý nghĩa rõ, chẳng hạn `findAll()` và `findByDepartment(String)`.
4. Quyết định giai đoạn tương thích: giữ hành vi cũ có cảnh báo hay tạo method mới và deprecate method cũ.
5. Kiểm thử cả lời gọi trực tiếp lẫn request đi qua controller/service boundary.

Ví dụ chuyển tiếp:

```java
public List<User> findAll() {
    return repository.loadAll();
}

public List<User> findByDepartment(String department) {
    Objects.requireNonNull(department, "department");
    return repository.loadByDepartment(department);
}

/** @deprecated Use findAll() or findByDepartment(...). */
@Deprecated
public List<User> search(String department) {
    return department == null ? findAll() : findByDepartment(department);
}
```

Giữ API cũ giúp client đã biên dịch tiếp tục hoạt động trong khi nhóm chuyển từng consumer. Chỉ loại bỏ method cũ theo lộ trình hỗ trợ đã thống nhất.

### 4.2. `null` không đồng nghĩa với chuỗi rỗng, tập rỗng hoặc field bị thiếu

Trong nhiều API, các trạng thái có ý nghĩa khác nhau:

- Tham số `null`: không được cung cấp hoặc chưa biết.
- Chuỗi `""`: có giá trị nhưng độ dài bằng không.
- Chuỗi chỉ chứa khoảng trắng: có nội dung nhưng không phù hợp ràng buộc nghiệp vụ.
- Collection rỗng: có danh sách, số phần tử bằng không.
- Field **vắng mặt** trong JSON: client không gửi trường; có thể có ý nghĩa “giữ nguyên giá trị cũ” trong PATCH.
- Field JSON có giá trị `null`: client chủ động yêu cầu xóa giá trị, hoặc biểu diễn một trạng thái chưa có dữ liệu.

Ví dụ trong update API:

```json
{"displayName": null}
```

không nhất thiết tương đương:

```json
{}
```

Nếu endpoint xử lý partial update, quy tắc “field absent = không đổi” và “field null = xóa” cần được định nghĩa rõ. Khi đổi serializer, DTO, validation hoặc mapping library, nguy cơ mất phân biệt giữa hai trạng thái này đặc biệt cao.

### 4.3. Overload và `null` literal

Thêm overload có thể làm call site với `null` không còn biên dịch:

```java
void send(String value) { }
void send(Integer value) { }

// send(null); // Mơ hồ: String và Integer không có quan hệ subtype.
```

Một method trước đây chỉ nhận `String` có thể được gọi bằng `null` mà không mơ hồ. Khi thư viện thêm overload nhận `Integer`, mã nguồn consumer biên dịch lại có thể báo ambiguous method call, dù bytecode client cũ vẫn tham chiếu method có descriptor `(Ljava/lang/String;)V`.

Đây là ví dụ thay đổi API có thể làm source compatibility và behavioral compatibility khác nhau. Nếu ý nghĩa của hai overload quá gần, cân nhắc tên method rõ hơn thay vì bắt consumer cast `null` khắp nơi.

## 5. Thay đổi cách biểu diễn vắng mặt ở đầu ra

### 5.1. Trả `null` so với trả collection rỗng

Hai trạng thái có thể được client xử lý khác nhau:

```java
List<Order> orders = service.findOrders(customerId);

if (orders == null) {
    // Có thể hiểu: chưa truy vấn được, dữ liệu chưa biết, hoặc API legacy.
} else if (orders.isEmpty()) {
    // Đã truy vấn thành công và xác nhận không có kết quả.
}
```

Thay `null` bằng list rỗng thường là thiết kế thuận tiện hơn nếu cả hai đều có cùng ý nghĩa “không có kết quả”. Nhưng không thể thay đổi máy móc nếu consumer đang phân biệt “chưa có dữ liệu” với “dữ liệu rỗng”.

Ngược lại, thay một list rỗng thành `null` có thể phá client đang lặp, gọi `size()`, dùng Stream API hoặc serialize trực tiếp.

Khi chuyển đổi, nên ghi rõ:

- API cam kết luôn trả non-null hay không.
- Empty collection biểu diễn trạng thái gì.
- Giá trị trả về có mutable hay immutable.
- Có thể chứa phần tử `null` không.
- Kết quả là snapshot hay view được cập nhật theo trạng thái nguồn.

Ví dụ, `Collections.emptyList()`, `List.of()` và một `ArrayList` rỗng đều không chứa phần tử nhưng khác nhau về khả năng chỉnh sửa. Chuyển sang `List.of()` có thể gây `UnsupportedOperationException` ở consumer từng `add()` vào kết quả. Đây cũng là thay đổi hành vi dù không liên quan trực tiếp đến `null`.

### 5.2. Chuyển từ nullable return sang `Optional<T>`

API cũ:

```java
public User findById(String id) {
    return repository.getOrNull(id);
}
```

API mới:

```java
public Optional<User> findById(String id) {
    return Optional.ofNullable(repository.getOrNull(id));
}
```

Việc đổi kiểu trả về từ `User` thành `Optional<User>` là thay đổi chữ ký nguồn và descriptor nhị phân. Không nên sửa trực tiếp một method public được consumer cũ sử dụng nếu mục tiêu là giữ tương thích. Có thể thêm API mới:

```java
public Optional<User> findOptional(String id) {
    return Optional.ofNullable(repository.getOrNull(id));
}

/** @deprecated Use findOptional(String). */
@Deprecated
public User findById(String id) {
    return findOptional(id).orElse(null);
}
```

Nhờ vậy, client cũ dùng `findById(String)` vẫn nhận đúng hợp đồng nullable. Client mới dùng `findOptional(String)` với ý nghĩa vắng mặt được biểu diễn tường minh. Sau khi consumer chuyển đổi, method cũ có thể được xem xét loại bỏ ở một mốc phát hành phù hợp.

### 5.3. `Optional` không phải lời giải mặc định cho mọi kiểu vắng mặt

`Optional<T>` phù hợp nhất với nhiều API có nghĩa “có hoặc không có một giá trị”. Nó không tự biểu diễn đầy đủ:

- Không tìm thấy so với không có quyền truy cập.
- Không có dữ liệu so với truy vấn lỗi.
- Chưa nạp dữ liệu so với dữ liệu đã nạp và rỗng.
- Không tồn tại so với đã bị xóa.

Với những trạng thái nghiệp vụ khác nhau, có thể cần result type chuyên biệt:

```java
sealed interface LookupResult
        permits Found, NotFound, Forbidden {
}

record Found(User user) implements LookupResult {
}

record NotFound() implements LookupResult {
}

record Forbidden() implements LookupResult {
}
```

Ví dụ dùng cú pháp hiện đại của Java; khi áp dụng cần dùng JDK/toolchain hỗ trợ những tính năng ngôn ngữ tương ứng.

Đừng dùng `Optional.empty()` để che lỗi database hoặc network nếu hợp đồng cũ phân biệt thất bại với không tìm thấy. Khi đó client có thể cho rằng thao tác thành công nhưng dữ liệu thật bị mất khả năng truy cập.

## 6. Nullability annotations, validation và giới hạn của chúng

Một số codebase khai báo annotation như `@Nullable`, `@NonNull` hoặc `@NotNull` để diễn đạt hợp đồng. Annotation có thể phục vụ static analysis, IDE hoặc validation framework, nhưng hành vi phụ thuộc vào bộ annotation và công cụ sử dụng.

Ví dụ minh họa:

```java
public User findById(String id) {
    Objects.requireNonNull(id, "id");
    return repository.find(id);
}
```

Lệnh `Objects.requireNonNull` tạo kiểm tra runtime và ném `NullPointerException` khi tham số là `null`. Ngược lại, chỉ thêm một annotation non-null chưa chắc khiến runtime tự kiểm tra điều kiện đó.

Cần phân biệt:

1. **Static contract:** IDE hoặc analyzer cảnh báo khi truyền giá trị có thể `null`.
2. **Runtime validation:** code hoặc framework thật sự kiểm tra giá trị đầu vào.
3. **Serialization/transport behavior:** field bị thiếu, field bằng `null` và giá trị mặc định được ánh xạ ra sao.

Khi nâng framework validation, đừng giả định annotation không đổi là hành vi không đổi. Cấu hình bật/tắt validator, thứ tự kiểm tra và cách ánh xạ exception có thể thay đổi.

### 6.1. Thời điểm phát sinh lỗi cũng là hợp đồng

Hai triển khai:

```java
public void submit(String id) {
    Objects.requireNonNull(id, "id");
    queue.enqueue(id);
}
```

và:

```java
public void submit(String id) {
    queue.enqueue(id);
    Objects.requireNonNull(id, "id");
}
```

đều có thể ném `NullPointerException` khi `id` là `null`, nhưng triển khai sau có thể đã gửi một thông điệp vào queue trước khi báo lỗi. Vì thế, khi thay đổi cách validation `null`, phải kiểm tra thứ tự và tác dụng phụ, không chỉ loại exception.

## 7. Exception contract: loại lỗi, thời điểm và khả năng phục hồi

Một API có thể báo thất bại bằng:

- Checked exception, chẳng hạn `IOException`.
- Unchecked exception, chẳng hạn `IllegalArgumentException`, `IllegalStateException` hoặc một exception nghiệp vụ.
- Result object biểu diễn thành công/thất bại.
- `Optional.empty()` nếu hợp đồng định nghĩa “không có giá trị” không phải là lỗi.
- Completion bất đồng bộ thất bại, ví dụ `CompletableFuture` hoàn tất exceptional.
- Trả mã lỗi trong response hoặc thông điệp khi API đi qua HTTP/message boundary.

Đổi hình thức báo lỗi làm thay đổi cách client retry, rollback, ghi log và thông báo cho người dùng.

### 7.1. Checked exception và source compatibility

Phiên bản cũ:

```java
public byte[] load(String path) throws IOException {
    return Files.readAllBytes(Path.of(path));
}
```

Phiên bản mới:

```java
public byte[] load(String path) {
    try {
        return Files.readAllBytes(Path.of(path));
    } catch (IOException ex) {
        throw new UncheckedIOException(ex);
    }
}
```

Chữ ký JVM của method `load(String)` không chứa danh sách `throws`. Vì vậy, chỉ thay khai báo checked exception không tự thay đổi method descriptor. Tuy nhiên, khi biên dịch lại source:

- Client có thể không còn được phép dùng một `catch` bắt checked exception mà compiler biết chắc không thể phát sinh trong phần `try`.
- Client có thể cần thay logic retry/rollback nếu exception mới là unchecked.
- Exception bị bọc trong `UncheckedIOException` có thể bị interceptor hoặc exception handler xử lý khác.

Tình huống ngược lại, thêm `throws IOException` vào API, có thể bắt consumer mới phải bắt hoặc khai báo tiếp exception dù bytecode của method vẫn có cùng descriptor.

### 7.2. Exception type không chỉ là thông báo

Giả sử client:

```java
try {
    repository.save(order);
} catch (DuplicateOrderException ex) {
    return Result.alreadyExists();
} catch (TransientStorageException ex) {
    return Result.retryLater();
}
```

Nếu framework mới gộp cả hai tình huống thành `RepositoryException`, client không còn biết khi nào được retry, khi nào phải trả kết quả nghiệp vụ khác. Dù method vẫn cùng chữ ký, exception translation đã thay đổi hành vi của toàn hệ thống.

Khi đổi exception mapping, cần xác định:

| Chiều | Cần giữ hoặc công bố |
| --- | --- |
| Loại exception | Checked, unchecked, class hierarchy, subtype cụ thể |
| Điều kiện phát sinh | Input không hợp lệ, không tìm thấy, conflict, timeout, hạ tầng |
| Thời điểm | Trước side effect, giữa transaction hay sau khi ghi thành công |
| Nguyên nhân | `getCause()` và context có được giữ lại không |
| Retryability | Có an toàn khi gọi lại không, cần backoff/idempotency key không |
| Quan sát | Log, metrics, trace, HTTP status, error code có còn nhất quán không |
| Transaction | Exception có khiến transaction rollback theo policy không |

### 7.3. Đừng vô tình nuốt exception

Ví dụ nguy hiểm:

```java
public Optional<User> find(String id) {
    try {
        return Optional.ofNullable(repository.find(id));
    } catch (Exception ex) {
        return Optional.empty();
    }
}
```

Code này gộp “không tìm thấy user” với lỗi kết nối, lỗi serialization và những lỗi bất ngờ. Consumer có thể hiểu `Optional.empty()` là tra cứu thành công nhưng không có dữ liệu.

Nếu cần dịch exception qua một boundary, hãy bắt loại cụ thể và giữ ngữ nghĩa:

```java
public Optional<User> find(String id) {
    try {
        return Optional.ofNullable(repository.find(id));
    } catch (StorageTimeoutException ex) {
        throw new UserLookupUnavailableException("Lookup timed out", ex);
    }
}
```

Ví dụ giả định các exception nghiệp vụ đã được định nghĩa. Quan trọng là exception mới có mục đích rõ và giữ lại nguyên nhân, không biến lỗi hạ tầng thành trạng thái vắng mặt.

## 8. Exception trong API bất đồng bộ và lazy

### 8.1. Thay đổi từ đồng bộ sang bất đồng bộ

Hai API:

```java
User fetch(String id);
CompletableFuture<User> fetchAsync(String id);
```

khác nhau không chỉ ở kiểu trả về:

- Lỗi của `fetch` có thể được ném ngay trong lời gọi.
- Lỗi từ thao tác bất đồng bộ thường được biểu diễn bằng future hoàn tất exceptional.
- Client chờ bằng `join()` có thể quan sát `CompletionException` bọc nguyên nhân.
- Client chờ bằng `get()` có thể nhận `ExecutionException`.
- Thread thực thi, cancellation và thời điểm side effect có thể khác.

Nếu migration chuyển một API từ synchronous sang asynchronous, cần định nghĩa lại nơi xử lý lỗi và transaction boundary. Không thể chỉ sửa kiểu trả về rồi giữ nguyên giả định về exception.

### 8.2. Lazy evaluation có thể dời thời điểm lỗi

Ví dụ:

```java
Stream<Order> orders = repository.streamOrders();
```

Việc tạo `Stream` có thể chưa thực hiện mọi bước đọc dữ liệu. Lỗi có thể chỉ xuất hiện khi gọi terminal operation:

```java
List<Order> result = orders.toList();
```

Trong một migration từ `List<Order>` sang `Stream<Order>`, lỗi có thể chuyển từ thời điểm gọi repository sang thời điểm tiêu thụ stream. Phải xác định ai chịu trách nhiệm đóng tài nguyên, transaction còn mở hay không và có được tiêu thụ stream nhiều lần không.

Đặc biệt, thay kết quả eager bằng lazy có thể làm các side effect và exception xuất hiện muộn hơn, sau khi scope tài nguyên hoặc transaction đã kết thúc.

### 8.3. Giữ nguyên trạng thái interrupt và cancellation

Không nên dịch mọi exception thành một loại generic rồi làm mất tín hiệu `InterruptedException` hoặc cancellation. Khi code bắt `InterruptedException` trong một boundary không thể khai báo lại, một lựa chọn phổ biến là khôi phục interruption status:

```java
try {
    worker.await();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new OperationCancelledException("Interrupted", ex);
}
```

Cách xử lý thực tế phụ thuộc hợp đồng API và cơ chế concurrency của ứng dụng. Điều quan trọng là migration không âm thầm biến tác vụ đã hủy thành trạng thái thành công hoặc retry vô hạn.

## 9. Thứ tự kết quả là một phần của hợp đồng

Một kết quả chứa đúng phần tử nhưng sai thứ tự vẫn có thể làm hỏng nghiệp vụ:

- Trang đầu tiên của pagination lấy những bản ghi khác trước đây.
- Batch processor xử lý bước sau trước bước trước.
- Rule engine chạy rule ưu tiên thấp trước rule ưu tiên cao.
- Giao diện hiển thị dữ liệu không ổn định giữa các lần refresh.
- Test hoặc consumer so sánh dữ liệu theo thứ tự cố định.
- Chữ ký số, hash hoặc cache key phụ thuộc biểu diễn có thứ tự thay đổi.

Do đó, cần phân biệt:

1. **Tập phần tử:** có đủ dữ liệu đúng không?
2. **Thứ tự của phần tử:** có cam kết thứ tự không và sort theo tiêu chí nào?
3. **Tính ổn định khi giá trị bằng nhau:** nếu hai phần tử bằng nhau theo comparator, có tie-breaker không?
4. **Thứ tự xử lý:** callback, event hay tác dụng phụ có xảy ra theo thứ tự đó không?

### 9.1. `List` không tự hứa một thứ tự nghiệp vụ

`List` bảo toàn thứ tự các phần tử trong collection. Nhưng chữ ký `List<Order> findOrders()` không cho biết list có được sắp theo thời gian, id hay ưu tiên. Nếu implementation cũ dùng query có `ORDER BY` còn implementation mới không dùng, cả hai đều trả `List` hợp lệ nhưng khác contract hành vi.

Để rõ ràng, cần tài liệu hóa:

```text
findOrders():
  returns orders sorted by createdAt DESC, id ASC
```

Nếu không có cam kết thứ tự, ghi rõ “ordering unspecified” và tránh viết consumer dựa trên một thứ tự quan sát tình cờ.

### 9.2. Collection khác nhau có quy tắc iteration khác nhau

| Cấu trúc | Đặc điểm liên quan thứ tự |
| --- | --- |
| `ArrayList` | Bảo toàn vị trí phần tử theo thao tác thêm/sửa |
| `LinkedHashSet` | Thường duy trì thứ tự chèn |
| `TreeSet` | Sắp theo natural ordering hoặc comparator |
| `HashSet` | Không cam kết iteration order |
| `LinkedHashMap` | Có thứ tự theo insertion hoặc access tùy cấu hình |
| `TreeMap` | Sắp theo khóa |
| `HashMap` | Không cam kết iteration order |

Không được lấy thứ tự quan sát được trong một lần chạy `HashMap` hoặc `HashSet` làm hợp đồng ổn định. Thay JDK, số phần tử hoặc cách hash/resize có thể khiến thứ tự khác đi mà vẫn đúng theo API của collection.

### 9.3. Sắp xếp theo comparator có tie-breaker

Ví dụ cần sắp đơn hàng theo ngày tạo giảm dần:

```java
Comparator<Order> orderComparator =
        Comparator.comparing(Order::createdAt)
                .reversed()
                .thenComparing(Order::id);

orders.sort(orderComparator);
```

Nếu nhiều đơn có cùng `createdAt`, `id` giúp tạo thứ tự xác định, miễn là `id` phù hợp và ổn định. Nếu bỏ tie-breaker, hai lần tải dữ liệu từ nguồn khác thứ tự đầu vào có thể tạo kết quả khác nhau dù cùng tiêu chí chính.

Khi thêm tie-breaker, cần phân biệt:

- Đây là làm rõ một hợp đồng vốn chỉ cam kết sort theo `createdAt` hay là thay đổi thứ tự đã được công bố?
- Consumer có dựa vào tính ổn định tương đối của các phần tử bằng nhau không?
- `null` trong khóa sort được xử lý thế nào?
- Locale/collation và timezone có ảnh hưởng tới so sánh không?

`Comparator.nullsFirst(...)` hoặc `nullsLast(...)` có thể định nghĩa rõ thứ tự cho key nullable; hãy chọn theo hợp đồng chứ không chỉ để tránh `NullPointerException`.

## 10. Stream API, song song hóa và encounter order

### 10.1. Encounter order không phải lúc nào cũng tồn tại

Stream có thể có **encounter order** nếu nguồn hoặc một phép biến đổi xác định thứ tự. Ví dụ stream từ `List` có encounter order, trong khi stream từ `HashSet` không bảo đảm như vậy.

```java
List<String> names = List.of("An", "Binh", "Chi");

List<String> result = names.stream()
        .map(String::toUpperCase)
        .toList();
```

Với stream có thứ tự, `toList()` giữ encounter order trong kết quả. Tuy nhiên, nếu đổi nguồn sang một collection unordered, không nên mong đợi cùng thứ tự chỉ vì pipeline nhìn tương tự.

### 10.2. `forEach` và `forEachOrdered`

```java
names.parallelStream().forEach(System.out::println);
```

Trong parallel stream, `forEach` không bảo đảm thực hiện side effect theo encounter order. Nếu cần thứ tự quan sát được:

```java
names.parallelStream().forEachOrdered(System.out::println);
```

`forEachOrdered` duy trì encounter order nếu stream có order đó, nhưng có thể làm giảm lợi ích song song và không biến mọi side effect thành thread-safe. Trước khi chuyển stream từ tuần tự sang song song, cần xem có consumer nào dựa trên thứ tự callback hoặc trạng thái mutable được chia sẻ không.

### 10.3. `sorted()` và `unordered()`

`Stream.sorted()` có thể tạo thứ tự theo comparator. Với stream có encounter order, phép sort ổn định; với stream unordered, không có cùng cam kết về vị trí tương đối của các phần tử bằng nhau. Dùng comparator có tie-breaker nếu cần kết quả xác định.

`unordered()` cho phép pipeline bỏ yêu cầu encounter order ở các bước tiếp theo. Nó có thể giúp tối ưu một số thao tác song song, nhưng không phù hợp nếu đầu ra là một API cam kết thứ tự.

Đặc biệt, `findFirst()` và `findAny()` có ý nghĩa khác nhau: `findFirst()` tôn trọng encounter order khi có, còn `findAny()` được phép chọn một phần tử bất kỳ. Đổi giữa hai phương thức vì tối ưu hiệu năng có thể thay đổi kết quả quan sát được.

## 11. Thứ tự dữ liệu từ database, pagination và phân trang

Một truy vấn SQL không có `ORDER BY` không cam kết thứ tự dòng. Thứ tự từng quan sát được có thể thay đổi khi nâng driver, database, index hoặc query planner.

Ví dụ chưa đủ cho pagination:

```sql
SELECT id, created_at, total
FROM orders
LIMIT 20 OFFSET 20;
```

Ví dụ có thứ tự rõ:

```sql
SELECT id, created_at, total
FROM orders
ORDER BY created_at DESC, id ASC
LIMIT 20 OFFSET 20;
```

Nếu `created_at` không unique, thêm `id` làm tie-breaker giúp thứ tự xác định hơn. Dù vậy, offset pagination vẫn có thể cho dữ liệu trùng hoặc bỏ sót giữa các request nếu bản ghi được thêm/xóa đồng thời. Khi cần nhất quán cao, hãy xem xét snapshot hoặc keyset pagination theo hợp đồng sản phẩm.

Thay đổi ORM/framework có thể vô tình làm query trước đây có sort trở thành query không sort. Khi API công bố thứ tự, hãy kiểm tra kết quả ở mức integration test với nhiều bản ghi có cùng khóa chính của comparator và có thay đổi đồng thời nếu phù hợp.

### 11.1. JSON object order khác JSON array order

Khi thay serializer, cần phân biệt thứ tự thuộc hợp đồng hay chỉ là cách trình bày. Thứ tự phần tử trong **array** thường có ý nghĩa; thứ tự key của **JSON object** thường không nên được consumer coi là thông tin nghiệp vụ trừ khi một protocol riêng định nghĩa yêu cầu cụ thể.

Nếu dùng JSON string để tạo chữ ký hoặc hash, phải có quy tắc canonicalization hoặc serializing xác định; không nên phụ thuộc vào iteration order tình cờ của `Map`.

## 12. Tác dụng phụ: một method đã làm gì ngoài việc trả giá trị?

Side effect là thay đổi trạng thái hoặc hoạt động quan sát được ngoài giá trị trả về, chẳng hạn:

- Ghi/cập nhật/xóa dữ liệu database.
- Thay đổi cache hoặc in-memory mutable state.
- Phát event lên queue, message broker hoặc event bus.
- Gửi request HTTP, email hoặc webhook.
- Sinh ID, lấy thời gian hiện tại, tạo file, khóa hoặc mở tài nguyên.
- Ghi audit, metric, log hoặc trace.
- Gọi callback của consumer, kích hoạt lazy loading hoặc background task.

Không phải mọi side effect đều xấu. Nhưng consumer cần biết tác dụng phụ **có tồn tại không**, xảy ra **trước hay sau khi trả kết quả**, có thể xảy ra **bao nhiêu lần**, trong **transaction** nào và có thể **phục hồi** khi lỗi hay không.

### 12.1. Đổi từ read-only sang read-and-write

API cũ:

```java
public User getUser(String id) {
    return repository.findById(id);
}
```

API mới:

```java
public User getUser(String id) {
    User user = repository.findById(id);
    repository.updateLastAccessed(id, Instant.now());
    return user;
}
```

Chữ ký không đổi, nhưng lời gọi đọc giờ tạo database write. Hậu quả có thể gồm tăng tải, cần quyền ghi mới, lock/transaction phát sinh, replication lag, audit event, và test trước đây dùng read-only transaction bị lỗi.

Nếu muốn thêm tracking, có thể tạo một method có tên nói rõ tác dụng phụ hoặc đặt hoạt động đó ở boundary phù hợp. Nếu vẫn giữ tên cũ, phải công bố và kiểm thử side effect như một phần hợp đồng mới.

### 12.2. Thứ tự tác dụng phụ thay đổi

So sánh:

```java
public void createOrder(Order order) {
    repository.save(order);
    publisher.publish(new OrderCreated(order.id()));
}
```

với:

```java
public void createOrder(Order order) {
    publisher.publish(new OrderCreated(order.id()));
    repository.save(order);
}
```

Hai phiên bản cùng chữ ký và cùng hai thao tác, nhưng nếu `save` thất bại, phiên bản thứ hai có thể đã phát sự kiện cho đơn hàng không tồn tại. Ngay cả cách thứ nhất cũng có nguy cơ sự kiện bị phát sai tương quan với transaction nếu publish xảy ra trước commit. Khi cần tính nhất quán, hãy dùng chiến lược phù hợp như transactional outbox, idempotent consumer hoặc event phát sau commit theo thiết kế được kiểm chứng.

### 12.3. Đổi số lần callback được gọi

Giả sử API:

```java
void process(Item item, Consumer<Item> callback);
```

trước đây gọi callback đúng một lần. Sau khi thêm retry, callback có thể được gọi nhiều lần. Nếu consumer callback gửi email hoặc trừ tiền, kết quả có thể nghiêm trọng dù API vẫn nhận cùng `Consumer<Item>`.

Hợp đồng nên nêu ít nhất:

- Gọi callback 0, 1 hay nhiều lần.
- Có thể gọi lại sau thất bại không.
- Callback chạy trên thread nào.
- Có bảo đảm thứ tự giữa các callback không.
- Có thể thực thi đồng thời không.
- Exception từ callback được propagate, log, retry hay bỏ qua.

Không nên dùng một callback có side effect không idempotent trong cơ chế retry mà không có bảo vệ chống thực hiện lặp.

## 13. Idempotency, retry và transaction

### 13.1. Idempotency là thuộc tính hành vi, không phải kiểu trả về

Một thao tác idempotent có thể được gọi lặp mà tác động cuối cùng tương đương một lần gọi, trong phạm vi hợp đồng đã định. Đặt trạng thái thành một giá trị thường dễ idempotent hơn thao tác tăng giá trị:

```java
account.setStatus("ACTIVE"); // Có thể idempotent về trạng thái cuối.
account.incrementPoints(10); // Thường không idempotent.
```

Việc log hoặc ghi metric nhiều lần vẫn có thể là side effect quan sát được; cần xác định rõ **mức idempotency nào** mà hệ thống cam kết (business state, external event, billing, audit).

Thay API từ không retry sang tự retry có thể làm tăng số lần ghi, gửi request hoặc phát event. Nếu consumer đã có retry ở bên ngoài, hai lớp retry kết hợp có thể tạo amplification.

### 13.2. Dùng idempotency key khi phù hợp

Ví dụ một command:

```java
PaymentResult charge(
        String requestId,
        String accountId,
        BigDecimal amount);
```

Nếu `requestId` được định nghĩa là idempotency key, implementation có thể ghi nhận request đã xử lý để tránh charge trùng khi client retry. Tuy nhiên, chỉ thêm tham số `requestId` vào chữ ký không bảo đảm idempotency; hệ thống cần thiết kế lưu trạng thái, kiểm tra cạnh tranh và replay kết quả.

Khi migration, kiểm thử nhiều lần gọi cùng key, gọi khác key và xử lý lỗi trước/sau commit để xác nhận behavior.

### 13.3. Exception và transaction rollback

Các framework transaction có quy tắc riêng về trường hợp nào gây rollback. Trong một số cấu hình phổ biến, unchecked exception có thể mặc định gây rollback còn checked exception không nhất thiết; điều này phụ thuộc framework, annotation và cấu hình.

Vì vậy, đổi từ `IOException` sang `UncheckedIOException` hoặc đổi cách exception được bọc có thể làm transaction rollback theo cách khác, dù dữ liệu đầu vào và method signature không đổi. Khi nâng framework cần kiểm tra transaction policy thật, không suy đoán bằng tên exception.

### 13.4. Không giả định “thất bại” nghĩa là “chưa có side effect”

Một request có thể ghi database thành công nhưng timeout trước khi response tới client. Consumer thấy exception và retry, tạo khả năng ghi trùng. Tương tự, một transaction có thể rollback dữ liệu nhưng email hoặc event ngoài transaction đã được gửi.

API nên định nghĩa rõ:

- Kết quả nào xác nhận commit đã hoàn tất.
- Lỗi nào cho phép retry tự động.
- Có cách kiểm tra trạng thái request bằng correlation/idempotency key không.
- Những side effect nào nằm ngoài transaction.
- Cách khôi phục hoặc bù trừ khi lỗi giữa các bước.

## 14. Thay đổi tác dụng phụ khi dùng cache, lazy loading và stream

### 14.1. Cache ảnh hưởng đến số lần truy cập nguồn

Một method trước đây truy vấn database mỗi lần được gọi, sau migration dùng cache, có thể giữ nguyên giá trị trả về trong test đơn giản. Nhưng behavior thay đổi:

- Độ mới dữ liệu có thể khác.
- Callback/metric gắn với mỗi lần truy vấn nguồn có thể ít hơn.
- Lỗi storage có thể xuất hiện muộn hoặc bị che khi cache hit.
- Side effect phụ thuộc việc load dữ liệu có thể không xảy ra trong mọi lời gọi.

Cần định nghĩa freshness, invalidation, TTL và mức nhất quán. Không nên coi cache “chỉ là tối ưu” khi consumer dựa vào dữ liệu mới ngay sau khi ghi.

### 14.2. Lazy loading có thể dời side effect

Nếu method chuyển từ trả `List<T>` đã nạp sang `Stream<T>` lười thực thi, phần đọc database và exception có thể xảy ra trong terminal operation. Consumer cần biết lifetime tài nguyên và ai đóng stream, đặc biệt với stream gắn với connection/result set.

Trường hợp chuyển sang reactive stream, subscription có thể kích hoạt việc thực hiện. Nếu mỗi subscription gọi lại nguồn, việc subscribe hai lần có thể tạo hai lần side effect. Cần tài liệu hóa semantics của API thay vì giả định publisher/future/stream là thay thế trực tiếp cho list eager.

### 14.3. `parallelStream()` và shared mutable state

Ví dụ không an toàn:

```java
List<String> output = new ArrayList<>();

items.parallelStream()
        .map(Item::name)
        .forEach(output::add);
```

`ArrayList` không được đồng bộ cho concurrent writes; kết quả có thể sai hoặc không ổn định. Với bài toán tạo danh sách, nên ưu tiên phép thu thập mà stream framework quản lý:

```java
List<String> output = items.parallelStream()
        .map(Item::name)
        .toList();
```

Ví dụ này giúp tránh mutating shared list trong `forEach`. Nếu cần side effect bên ngoài, phải xác định concurrency contract và cách đồng bộ hoặc tách xử lý.

## 15. Ví dụ tổng hợp: tiến hóa API tìm kiếm đơn hàng

Giả sử phiên bản cũ có contract ngầm:

```java
public List<Order> search(String customerId) {
    if (customerId == null) {
        return null;
    }
    List<Order> results = repository.findByCustomer(customerId);
    return results; // Repository cũ trả theo thứ tự createdAt tăng dần.
}
```

Trong phiên bản mới, nhóm muốn:

1. Bắt buộc `customerId` khác `null`.
2. Không có kết quả thì trả list rỗng.
3. Trả theo `createdAt` giảm dần.
4. Ném `OrderLookupException` khi storage lỗi, thay vì exception gốc.
5. Ghi audit event mỗi lần tìm kiếm.

Nếu thực hiện đồng thời nhưng vẫn giữ tên và chữ ký `search(String)`, các consumer cũ có thể:

- Dùng `null` như cách biểu diễn yêu cầu chưa chọn khách hàng.
- Phân biệt `null` với list rỗng.
- Dùng phần tử đầu tiên như đơn hàng cũ nhất.
- Chỉ bắt exception của repository cũ.
- Gọi `search` trong đường code phải read-only và không muốn phát audit event.

Đây là năm breaking changes về behavior dù method descriptor vẫn tương thích.

### 15.1. Một phương án API mới tách biệt

Thay vì đổi âm thầm method cũ, có thể giới thiệu API có tên/hợp đồng mới:

```java
public List<Order> findRecentOrders(String customerId) {
    Objects.requireNonNull(customerId, "customerId");
    if (customerId.isBlank()) {
        throw new IllegalArgumentException("customerId is blank");
    }

    List<Order> result;
    try {
        result = repository.findByCustomer(customerId);
    } catch (StorageException ex) {
        throw new OrderLookupException("Cannot query orders", ex);
    }

    return result.stream()
            .sorted(Comparator
                    .comparing(Order::createdAt)
                    .reversed()
                    .thenComparing(Order::id))
            .toList();
}
```

Ví dụ giả định các type nghiệp vụ và repository đã có. Phương thức mới trả non-null list đã sort và không tự phát audit event. Nếu sản phẩm thực sự yêu cầu audit, nên xác định ở boundary nào phải ghi audit và cách bảo đảm giao dịch/không ghi trùng; không tự chèn thêm ở mọi truy vấn chỉ vì migration.

### 15.2. Giữ adapter cho consumer cũ

```java
/** @deprecated Legacy nullable lookup; migrate to findRecentOrders(). */
@Deprecated
public List<Order> search(String customerId) {
    if (customerId == null) {
        return null;
    }
    return repository.findByCustomerInLegacyOrder(customerId);
}
```

Adapter phải thật sự giữ contract cũ trong giai đoạn hỗ trợ. Nếu repository mới không còn cung cấp legacy ordering, có thể cần sort rõ theo comparator cũ. Không dùng method mới rồi hy vọng các tác động phụ như null/exception/order vẫn giống trước.

### 15.3. Chuyển consumer theo từng nhóm

Consumer mới chuyển sang `findRecentOrders` cần sửa giả định về input, empty result, exception và order. Với audit event, cần quyết định một API riêng hoặc lớp orchestration chủ động ghi audit theo quy trình. Sau khi tất cả consumer đã chuyển và hết thời hạn hỗ trợ, method `search` cũ có thể được xem xét loại bỏ trong release có thông báo rõ.

## 16. Kiểm thử hợp đồng hành vi bằng JUnit

Nên viết test trước khi migration để ghi lại behavior quan trọng. Test về **hợp đồng** khác test về chi tiết implementation: nó xác minh điều consumer dựa vào, không khóa cứng mọi dòng code nội bộ.

### 16.1. Null và empty contract

Ví dụ JUnit 5 với API mới:

```java
@Test
void rejectsNullCustomerId() {
    assertThrows(
            NullPointerException.class,
            () -> service.findRecentOrders(null));
}

@Test
void returnsEmptyNonNullListWhenNoOrders() {
    List<Order> result = service.findRecentOrders("customer-404");

    assertNotNull(result);
    assertTrue(result.isEmpty());
}
```

Nếu hợp đồng chọn `IllegalArgumentException` thay vì `NullPointerException`, test phải phản ánh lựa chọn đó. Cả hai không tương đương đối với consumer bắt exception cụ thể.

### 16.2. Exception translation

```java
@Test
void preservesStorageFailureAsCause() {
    StorageException failure =
            new StorageException("database unavailable");
    when(repository.findByCustomer("customer-1"))
            .thenThrow(failure);

    OrderLookupException actual = assertThrows(
            OrderLookupException.class,
            () -> service.findRecentOrders("customer-1"));

    assertSame(failure, actual.getCause());
}
```

Đây là pseudocode theo phong cách JUnit 5 và Mockito; tên exception và mock setup tùy codebase. Kiểm thử nguyên nhân giúp tránh mất diagnostic context khi đổi framework.

### 16.3. Ordering và tie-breaker

```java
@Test
void sortsByCreatedAtDescendingThenIdAscending() {
    List<Order> result = service.findRecentOrders("customer-1");

    assertEquals(
            List.of("order-c", "order-a", "order-b"),
            result.stream().map(Order::id).toList());
}
```

Test cần có fixture tạo dữ liệu phù hợp (nhiều đơn có cùng timestamp, id xác định). Nếu chỉ có một đơn, test không thể phát hiện regression về ordering.

### 16.4. Không có side effect ngoài hợp đồng

```java
@Test
void searchingDoesNotWriteOrPublishBusinessEvents() {
    service.findRecentOrders("customer-1");

    verify(repository, never()).save(any());
    verify(eventPublisher, never()).publish(any());
}
```

Test tương tự có thể kiểm tra thao tác đúng một lần:

```java
verify(eventPublisher, times(1)).publish(any(OrderCreated.class));
```

Các test tương tác nên dùng ở boundary quan trọng; không cần mock mọi internal method. Với DB transaction và message broker, integration test hoặc test qua contract boundary có giá trị cao hơn một mock-only test vì nó kiểm tra thời điểm commit và khả năng xảy ra duplicate.

### 16.5. Kiểm thử với artifact cũ và mới

Nếu vẫn phải hỗ trợ client đã biên dịch, hãy lưu một bộ consumer contract test build theo API cũ rồi chạy với implementation mới. Đừng chỉ biên dịch lại test từ source cũ với API mới; làm vậy có thể bỏ sót lỗi binary linkage. Song song, chạy bộ test của consumer mới để xác nhận hợp đồng mới.

Ngoài deterministic unit tests, có thể dùng property-based hoặc metamorphic tests cho các tính chất:

- Kết quả non-null với mọi input hợp lệ.
- Sort theo comparator đã công bố.
- Hai lần gọi cùng idempotency key không tạo hai bản ghi nghiệp vụ.
- Invalid input không tạo side effect.
- Retryable failure giữ nguyên cause/error code và không làm tăng số lần side effect ngoài contract.

Với concurrency, dùng test có kiểm soát thời gian và scheduler khi có thể; không lấy một lần chạy thành công làm bằng chứng chắc chắn về thread safety.

## 17. Quy trình quản lý thay đổi API trong migration

### Bước 1: Lập baseline hợp đồng

Ghi nhận chữ ký, nullability, các exception có thể quan sát, thứ tự dữ liệu, side effects, số lần gọi callback, retry và transaction semantics. Lưu test hiện có cùng phiên bản JDK, framework, dependency và runtime.

### Bước 2: Xác định consumer và mức phụ thuộc

Tìm consumer đang dùng API: mã Java, reflection, REST/JSON client, message consumer, batch job và công cụ gọi tự động. Kiểm tra nơi đang dựa vào `null`, loại exception, phần tử đầu tiên hay việc gọi method chỉ đọc.

### Bước 3: Phân loại thay đổi

| Thay đổi | Rủi ro cần đánh giá | Cách chuyển đổi thường dùng |
| --- | --- | --- |
| Chấp nhận `null` -> từ chối `null` | Client cũ ném exception | Method mới, validation ở boundary, adapter legacy |
| Trả `null` -> empty collection | Consumer phân biệt “không biết” với “rỗng” | Result type rõ nghĩa, deprecation |
| Nullable `T` -> `Optional<T>` | Source/binary signature đổi | Method mới có tên khác, giữ method cũ |
| Checked -> unchecked exception | Catch/retry/rollback khác | Exception adapter, tài liệu hóa error mapping |
| Exception -> empty result | Mất phân biệt lỗi với không tìm thấy | Giữ lỗi hạ tầng, dùng result type đa trạng thái |
| Sort tăng -> giảm | Phân trang và logic consumer đổi | API có tên/param rõ, contract test |
| Collection có thứ tự -> unordered | Kết quả không xác định | Duy trì sort hoặc công bố breaking change |
| Read-only -> write/event | Quyền, tải, transaction, duplicate | Tách command/query hoặc orchestration rõ |
| Sync -> async/lazy | Thời điểm lỗi, lifecycle, thread | API mới, test async/cancellation/resource |

### Bước 4: Chọn chiến lược giữ tương thích

Có thể chọn:

1. **Giữ hợp đồng cũ:** sửa implementation để vẫn bảo toàn behavior đã công bố.
2. **API bổ sung:** giữ method cũ và thêm method có tên/hợp đồng mới.
3. **Adapter có thời hạn:** chuyển giữa representation cũ và mới, có owner và mốc gỡ bỏ.
4. **Version hóa API:** tạo endpoint/interface/schema thế hệ mới khi thay đổi rộng hoặc liên quan nhiều hệ thống.
5. **Breaking release có kế hoạch:** công bố, tài liệu migration, consumer inventory và rollout/rollback.

Không có một cách áp dụng cho mọi API. Với thay đổi bảo mật bắt buộc từ chối input nguy hiểm, có thể phải thay hành vi cũ ngay; khi đó cần ghi rõ đây là breaking behavioral change và cung cấp hướng xử lý cho consumer.

### Bước 5: Viết test bảo vệ hợp đồng

Ưu tiên test null/empty, exception mapping, thứ tự dữ liệu và số lần side effect. Với API cross-service, dùng contract/integration tests và trường hợp có nhiều phiên bản producer–consumer chạy đồng thời.

### Bước 6: Phát hành và theo dõi

Quan sát exception rate theo loại, số lượng retry, độ trễ, tần suất cập nhật database, số event, duplicate rate, kết quả phân trang và các chỉ số nghiệp vụ tương ứng. Với rollout canary, so sánh phiên bản cũ/mới bằng dữ liệu và traffic có thể đối chiếu.

### Bước 7: Gỡ lớp tương thích khi đủ điều kiện

Chỉ loại adapter và endpoint legacy sau khi xác nhận consumer không còn phụ thuộc, dữ liệu cần chuyển tiếp đã ổn định và chính sách hỗ trợ cho phép. Lưu migration guide và bằng chứng thực tế để phục vụ bảo trì các lần nâng cấp sau.

## 18. Phân biệt điều gì là hợp đồng, điều gì là chi tiết implementation

Không cần biến tất cả behavior của implementation thành cam kết công khai. Nếu API chỉ hứa “trả tập kết quả, không bảo đảm thứ tự”, việc đổi từ `HashSet` sang `TreeSet` có thể không vi phạm hợp đồng đã công bố. Tuy nhiên, trước khi đổi vẫn cần xem consumer thực tế có dựa vào order một cách không chính thức không, đặc biệt ở hệ thống đã triển khai lâu.

Các câu hỏi hữu ích khi review:

- API documentation đã nói rõ tình huống `null` chưa?
- Exception class và error code có được client dùng để quyết định retry hoặc hiển thị không?
- Thứ tự kết quả có được công bố hay được tái sử dụng để pagination không?
- Method tên `get/find/read` có bất ngờ làm write hoặc publish event không?
- Callback có thể được gọi nhiều lần, trên thread khác hoặc sau khi method trả về không?
- Thay đổi JDK/framework có đổi mặc định serializer, transaction manager, collection hoặc stream executor không?

Một nguyên tắc thiết kế tốt là **ghi rõ điều cần bảo đảm, tránh hứa ngầm điều không kiểm soát được**. Ví dụ, nếu thứ tự không thuộc hợp đồng, nói rõ “unspecified ordering”; nếu API có thể phát event, nêu điều kiện và bảo đảm phân phối thay vì dựa vào tên method.

## 19. Những sai lầm thường gặp

**Chỉ kiểm tra compile và runtime linkage.** Build xanh không bảo đảm `null`, exception, sorting hoặc side effects giữ nguyên. Phải kiểm tra hợp đồng hành vi quan trọng.

**Đổi nullable return thành empty list mà không phân tích ý nghĩa.** Nếu `null` nghĩa “chưa tải dữ liệu” còn list rỗng nghĩa “không có bản ghi”, việc gộp hai trạng thái sẽ làm mất thông tin.

**Cho rằng `@NonNull` tự thay đổi runtime behavior.** Annotation chỉ có tác dụng theo công cụ hoặc framework sử dụng; cần xác nhận validation thực sự được thực thi.

**Nuốt mọi exception rồi trả `Optional.empty()`.** Điều này biến lỗi hạ tầng thành trạng thái nghiệp vụ “không tìm thấy”, làm monitoring và retry sai.

**Đổi loại exception nhưng bỏ qua transaction policy.** Checked/unchecked translation có thể thay đổi rollback, đặc biệt khi framework dựa vào loại exception.

**Tin vào thứ tự `HashMap` hoặc kết quả SQL không `ORDER BY`.** Thứ tự quan sát trong một môi trường không phải bảo đảm cho môi trường khác.

**Thêm `parallelStream()` mà không xem side effect.** Thứ tự callback và thread safety có thể thay đổi; shared mutable state dễ bị race.

**Đổi read method thành write method mà không thông báo.** Client có thể đang gọi trong read-only transaction hoặc với quyền chỉ đọc.

**Bật retry mà không kiểm tra idempotency.** Timeout không chứng minh side effect chưa xảy ra; retry có thể nhân đôi thao tác.

**Dùng unit test mock-only để kết luận event/transaction an toàn.** Mock có thể xác nhận lời gọi nhưng không thể tự chứng minh thời điểm commit hoặc chính sách rollback thật.

**Gộp nhiều thay đổi behavior vào một release không có bằng chứng tách biệt.** Khi phát sinh regression sẽ khó biết lỗi do nullability, exception mapping, sorting hay side-effect change.

## 20. Checklist trước khi phê duyệt thay đổi

Đối với một API đã có consumer, trước khi phát hành nên có câu trả lời cho:

- [ ] Đã xác định mọi trường hợp input `null`, blank, missing và giá trị mặc định.
- [ ] Đã xác định result `null`, empty, optional và kiểu trạng thái không tìm thấy.
- [ ] Đã ghi loại exception, điều kiện phát sinh, cause, retryability và rollback policy.
- [ ] Đã kiểm tra exception đồng bộ, bất đồng bộ, cancellation và lazy evaluation khi liên quan.
- [ ] Đã xác định ordering contract, comparator, tie-breaker và nguồn dữ liệu.
- [ ] Không phụ thuộc iteration order không được collection/DB bảo đảm.
- [ ] Đã xác định side effects, thứ tự tác dụng phụ, số lần thực hiện và transaction boundary.
- [ ] Đã đánh giá idempotency khi thêm retry, queue hoặc callback nhiều lần.
- [ ] Đã xem tác động khi chuyển code tuần tự thành song song hoặc async.
- [ ] Đã kiểm tra behavior của serializer, validation và framework sau migration.
- [ ] Có test riêng cho null, empty, exception, order và effects ở các đường trọng yếu.
- [ ] Có test client cũ/implementation mới khi cam kết binary compatibility.
- [ ] Có adapter hoặc kế hoạch versioning nếu behavior mới không tương thích.
- [ ] Có danh sách consumer, người chịu trách nhiệm và kế hoạch rollout/rollback.
- [ ] Release notes ghi rõ breaking behavioral changes, không chỉ thay đổi method signature.
- [ ] Metrics/logs đủ để phát hiện lỗi sau rollout.

Checklist giúp đưa những thay đổi tưởng như “nội bộ” thành quyết định kỹ thuật có thể truy vết. Mức test và tài liệu cần tương xứng với độ ảnh hưởng của API; không nhất thiết áp dụng cùng mức nghiêm ngặt cho mọi helper method không public.

## 21. Kết luận

Trong tiến hóa API Java, thay đổi giá trị trả về hoặc tham số không phải rủi ro duy nhất. Một method có thể giữ nguyên chữ ký và liên kết hoàn toàn bình thường nhưng vẫn phá hợp đồng nếu chuyển cách xử lý `null`, đổi loại exception, bỏ bảo đảm thứ tự hoặc phát sinh tác dụng phụ mới.

Muốn migration an toàn, hãy nhìn API như một **hợp đồng quan sát được**: input nào hợp lệ, output nào biểu diễn điều gì, lỗi xuất hiện ra sao, kết quả có thứ tự nào và lời gọi làm thay đổi trạng thái gì. Ghi lại baseline, phân loại breaking change, cung cấp adapter hoặc API phiên bản mới khi cần, rồi kiểm thử null/empty, error semantics, ordering và side effects từ góc nhìn consumer. Cách tiếp cận này giúp tránh tình trạng “build thành công nhưng nghiệp vụ sai” khi nâng JDK, framework hoặc thư viện.
