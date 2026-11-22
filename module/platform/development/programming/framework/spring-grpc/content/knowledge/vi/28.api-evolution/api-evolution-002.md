# Thêm field tùy chọn

## 1. Mục tiêu

Khi một gRPC API cần thêm khả năng mới, cách mở rộng thường an toàn là thêm field vào Protobuf request và để caller cũ tiếp tục gửi message như trước. Server mới phải xử lý được cả trường hợp caller mới gửi field lẫn trường hợp caller cũ không biết field đó.

Trong proto3, từ khóa `optional` còn giải quyết một vấn đề khác: phân biệt **field không được gửi** với **field được gửi rõ ràng nhưng mang giá trị mặc định**. Điều này đặc biệt quan trọng với update API, nơi `false`, `0` hoặc chuỗi rỗng có thể là một yêu cầu cập nhật hợp lệ.

Sau bài học, bạn có thể:

- Thêm scalar field tùy chọn vào message request proto3.
- Phân biệt implicit presence và explicit presence.
- Dùng `hasX()`, getter và `clearX()` trong Java generated code.
- Chọn default phù hợp khi caller cũ không gửi field.
- Thiết kế update semantics để phân biệt bỏ qua và xóa/đặt giá trị mặc định.
- Xử lý đúng message, repeated, map, enum và oneof.
- Kiểm thử request từ client cũ và client mới trong quá trình rollout.

## 2. Thêm field mà vẫn giữ caller cũ

Giả sử Catalog API ban đầu chỉ tìm kiếm theo query:

```proto
syntax = "proto3";

package catalog.v1;
option java_package = "dev.example.catalog.v1";
option java_multiple_files = true;

service CatalogService {
  rpc Search(SearchRequest) returns (SearchResponse);
}

message SearchRequest {
  string query = 1;
}

message SearchResponse {
  repeated string product_ids = 1;
}
```

Ta muốn bổ sung giới hạn số kết quả. Thêm field với số tag chưa dùng:

```proto
message SearchRequest {
  string query = 1;
  optional int32 page_size = 2;
}
```

Khi server mới nhận request:

- Client cũ chỉ biết `query = 1`, nên không gửi `page_size`. Server mới phải có hành vi mặc định tương thích.
- Client mới có thể gửi `page_size = 20`. Server mới sử dụng giá trị đó.
- Server cũ không biết tag `2`; nó có thể bỏ qua field mới khi parse. Request vẫn có thể được xử lý theo hành vi cũ, nhưng server cũ không thực hiện giới hạn trang mới.

Thêm field là một thay đổi schema tương đối an toàn ở tầng wire khi tag mới chưa từng được dùng và kiểu dữ liệu được chọn phù hợp. Điều đó không tự động bảo đảm tính năng mới hoạt động trên server cũ.

## 3. Implicit presence và explicit presence

### Scalar không có optional

Proto3 scalar thông thường dùng *implicit presence*:

```proto
message UpdatePreferencesRequest {
  bool email_enabled = 1;
  int32 daily_limit = 2;
  string display_name = 3;
}
```

Trong generated Java:

```java
boolean enabled = request.getEmailEnabled();
int limit = request.getDailyLimit();
String name = request.getDisplayName();
```

Nếu field không được gửi, getter trả giá trị mặc định của kiểu:

| Kiểu | Giá trị mặc định |
|---|---|
| `bool` | `false` |
| Số nguyên | `0` |
| Số thực | `0.0` |
| `string` | `""` |
| `bytes` | `ByteString.EMPTY` |
| Enum | Giá trị enum có số `0` |

Vấn đề là server không thể phân biệt field absent với field được caller đặt tường minh thành đúng giá trị mặc định. Ví dụ, `false` có thể nghĩa là “người dùng muốn tắt email”, hoặc chỉ là “client cũ không gửi field này”.

### Scalar có optional

Khai báo presence tường minh:

```proto
message UpdatePreferencesRequest {
  optional bool email_enabled = 1;
  optional int32 daily_limit = 2;
  optional string display_name = 3;
}
```

Generated Java cung cấp phương thức kiểm tra presence:

```java
if (request.hasEmailEnabled()) {
    boolean enabled = request.getEmailEnabled();
}

if (request.hasDailyLimit()) {
    int limit = request.getDailyLimit();
}
```

`hasEmailEnabled()` trả `false` khi field vắng mặt và `true` khi field đã được đặt, kể cả khi giá trị là `false`. Tương tự, `hasDailyLimit()` vẫn trả `true` nếu caller chủ động đặt `0`.

| Trạng thái caller gửi | `hasEmailEnabled()` | `getEmailEnabled()` |
|---|---:|---:|
| Không gửi field | `false` | `false` |
| Gửi `false` | `true` | `false` |
| Gửi `true` | `true` | `true` |

Getter vẫn trả default khi field absent. Vì vậy, nếu logic cần biết caller có gửi field hay không, hãy kiểm tra `hasX()` trước khi đọc giá trị.

## 4. Presence được biểu diễn thế nào trong Java?

Với proto3 optional, generated Java builder cung cấp setter, getter, presence check và clear:

```java
UpdatePreferencesRequest request =
        UpdatePreferencesRequest.newBuilder()
                .setEmailEnabled(false)
                .setDailyLimit(0)
                .build();

assertTrue(request.hasEmailEnabled());
assertFalse(request.getEmailEnabled());

assertTrue(request.hasDailyLimit());
assertEquals(0, request.getDailyLimit());
```

Nếu bỏ field khỏi builder hoặc gọi `clearX()`, presence trở về absent:

```java
UpdatePreferencesRequest request =
        UpdatePreferencesRequest.newBuilder()
                .setEmailEnabled(true)
                .clearEmailEnabled()
                .build();

assertFalse(request.hasEmailEnabled());
```

Về wire format, field optional được đặt tường minh có thể được serialize ngay cả khi mang giá trị mặc định. Field absent thì không được gửi. Đây là khác biệt giúp parser phía server khôi phục presence.

Tên phương thức Java được sinh theo quy tắc Protobuf; hãy kiểm tra generated source khi schema có tên đặc biệt hoặc xung đột tên.

## 5. Chọn default khi field vắng mặt

`optional` cho biết field có được đặt hay không; nó không tự định nghĩa nghiệp vụ khi field absent. Server phải quyết định default rõ ràng.

Với `SearchRequest.page_size`, có thể dùng:

```java
private static final int DEFAULT_PAGE_SIZE = 25;
private static final int MAX_PAGE_SIZE = 100;

int pageSize = request.hasPageSize()
        ? request.getPageSize()
        : DEFAULT_PAGE_SIZE;

if (pageSize < 1 || pageSize > MAX_PAGE_SIZE) {
    throw Status.INVALID_ARGUMENT
            .withDescription("page_size must be between 1 and 100")
            .asRuntimeException();
}
```

Khi client cũ không gửi `page_size`, server dùng `25`. Khi client mới gửi `0`, server nhìn thấy presence và từ chối giá trị không hợp lệ. Nếu không dùng `optional`, cả hai trường hợp đều có thể cho getter trả `0`, khiến server không phân biệt được.

Default mới phải giữ semantics cũ. Ví dụ, nếu trước đây Search trả tối đa 25 kết quả, thêm `page_size` không nên khiến request cũ bất ngờ trả toàn bộ dữ liệu. Có thể chọn default phù hợp với giới hạn cũ và công bố giới hạn tối đa.

### Phân biệt default của Protobuf và default nghiệp vụ

- **Protobuf default:** giá trị getter trả khi scalar implicit/optional absent, như `0`, `false`, `""`.
- **Business default:** hành vi server chọn khi caller không cung cấp field, như page size 25 hoặc locale mặc định.

Không nên dựa vào Protobuf default để ngầm định business default. Viết rõ nhánh absent giúp người đọc thấy server đang duy trì hành vi nào cho caller cũ.

## 6. optional đặc biệt hữu ích cho update request

Với API tạo mới, absent có thể dùng default. Với API cập nhật, absent thường có nghĩa **không thay đổi field**. Giá trị mặc định được gửi tường minh có thể là lệnh cập nhật hợp lệ.

Ví dụ:

```proto
message UpdateAccountRequest {
  string account_id = 1;
  optional bool notifications_enabled = 2;
  optional string display_name = 3;
  optional int32 daily_limit = 4;
}
```

Server chỉ cập nhật field caller thực sự gửi:

```java
Account account = repository.findById(request.getAccountId())
        .orElseThrow(() -> new AccountNotFoundException());

if (request.hasNotificationsEnabled()) {
    account.setNotificationsEnabled(
            request.getNotificationsEnabled());
}

if (request.hasDisplayName()) {
    account.setDisplayName(request.getDisplayName());
}

if (request.hasDailyLimit()) {
    int value = request.getDailyLimit();
    if (value < 0 || value > MAX_DAILY_LIMIT) {
        throw Status.INVALID_ARGUMENT
                .withDescription("daily_limit is out of range")
                .asRuntimeException();
    }
    account.setDailyLimit(value);
}

repository.save(account);
```

Ý nghĩa:

| Request | Kết quả cập nhật |
|---|---|
| `notifications_enabled` absent | Giữ nguyên trạng thái hiện tại |
| `notifications_enabled = false` | Tắt notifications |
| `display_name` absent | Giữ tên hiện tại |
| `display_name = ""` | Đặt tên rỗng nếu business rule cho phép; nếu không, trả validation error |
| `daily_limit = 0` | Đặt limit bằng 0 nếu nghiệp vụ cho phép |

Đây là lý do không nên dùng scalar implicit presence cho update API nếu cần phân biệt “không gửi” và “đặt về giá trị mặc định”.

## 7. Các loại field khác có presence ra sao?

Không phải field nào cũng dùng từ khóa `optional`.

| Loại field | Presence trong proto3 | Cách xử lý |
|---|---|---|
| Scalar không `optional` | Implicit; không phân biệt absent với default | Dùng khi default đủ để biểu diễn semantics |
| Scalar có `optional` | Explicit | Dùng `hasX()` để phân biệt absent/default |
| Message field | Có presence vốn có | Dùng `hasX()`; không cần thêm `optional` |
| `oneof` member | Có presence qua case/member check | Dùng `getChoiceCase()` hoặc API tương ứng |
| `repeated` | Không có presence | Empty và absent đều là collection rỗng |
| `map` | Không có presence | Empty và absent đều là map rỗng |

### Message field

Message field trong proto3 đã có explicit presence:

```proto
message SearchRequest {
  SearchOptions options = 1;
}

message SearchOptions {
  bool include_archived = 1;
}
```

Java có thể kiểm tra:

```java
if (request.hasOptions()) {
    boolean includeArchived =
            request.getOptions().getIncludeArchived();
}
```

`hasOptions()` phân biệt message absent với một `SearchOptions` message hiện diện nhưng chứa các giá trị mặc định.

### Repeated và map

Repeated/map không có `hasX()`:

```proto
message UpdateLabelsRequest {
  repeated string labels = 1;
  map<string, string> attributes = 2;
}
```

Getter trả collection rỗng khi không có phần tử. Nếu update API cần phân biệt “không gửi để giữ nguyên” với “gửi collection rỗng để xóa hết”, dùng `FieldMask` hoặc bọc collection trong một message có presence:

```proto
message StringList {
  repeated string values = 1;
}

message UpdateLabelsRequest {
  StringList labels = 1;
}
```

Vì `labels` là message field, `hasLabels()` phân biệt absent với message hiện diện có `values` rỗng. Phải định nghĩa semantics rõ: absent là giữ nguyên, present-empty là xóa toàn bộ.

### Oneof

Các member của `oneof` có presence và loại trừ lẫn nhau:

```proto
message SearchFilter {
  oneof filter {
    string category = 1;
    int64 seller_id = 2;
  }
}
```

Java generated code cung cấp enum case, chẳng hạn `getFilterCase()`. Nếu không member nào được đặt, case là `FILTER_NOT_SET`. Không thể đặt đồng thời category và seller ID trong cùng oneof.

## 8. Enum optional và giá trị UNSPECIFIED

Enum thường khai báo giá trị `0` làm giá trị mặc định:

```proto
enum SortOrder {
  SORT_ORDER_UNSPECIFIED = 0;
  SORT_ORDER_RELEVANCE = 1;
  SORT_ORDER_NEWEST = 2;
}

message SearchRequest {
  optional SortOrder sort_order = 4;
}
```

Với `optional`, server phân biệt:

- Absent: caller không cung cấp lựa chọn sắp xếp; server áp dụng business default.
- Present với `SORT_ORDER_UNSPECIFIED`: caller gửi rõ enum value `0`; server có thể áp dụng quy tắc riêng hoặc trả validation error.
- Present với `SORT_ORDER_NEWEST`: caller chọn sắp xếp mới nhất.

Nếu không cần phân biệt absent và `UNSPECIFIED`, có thể dùng enum scalar không optional và xem `UNSPECIFIED` là yêu cầu dùng default. Điều quan trọng là contract phải nói rõ.

## 9. Thêm optional field trong quá trình rollout

Khi client và server được deploy độc lập, triển khai theo thứ tự:

1. **Thêm field vào schema:** chọn tag mới chưa từng dùng; giữ nguyên các field hiện có.
2. **Deploy server hỗ trợ field:** server mới đọc field khi có và áp dụng default tương thích khi absent.
3. **Kiểm thử client cũ:** xác nhận request thiếu field vẫn được chấp nhận và kết quả không đổi.
4. **Xác nhận toàn bộ server instance đã nâng cấp:** tránh gửi client mới tới server chưa hỗ trợ semantics mới.
5. **Deploy client mới:** chỉ gửi field khi server target đã hỗ trợ.
6. **Quan sát:** đo tỷ lệ request có field, giá trị không hợp lệ và caller còn dùng phiên bản cũ.

Client mới gửi field tới server cũ có thể được parse thành công vì server cũ bỏ qua unknown field. Nhưng tính năng dựa trên field mới sẽ không được thực hiện. Wire compatibility không thay thế capability negotiation hoặc rollout có thứ tự.

Khi field không còn cần thiết, xóa nó theo quy trình migration và reserve cả số tag lẫn tên. Không bao giờ tái sử dụng field number đã công bố.

## 10. Kiểm thử presence và compatibility

### Unit test generated message

```java
SearchRequest absent = SearchRequest.newBuilder()
        .setQuery("keyboard")
        .build();

assertFalse(absent.hasPageSize());
assertEquals(0, absent.getPageSize());

SearchRequest explicitZero = SearchRequest.newBuilder()
        .setQuery("keyboard")
        .setPageSize(0)
        .build();

assertTrue(explicitZero.hasPageSize());
assertEquals(0, explicitZero.getPageSize());
```

Test này chứng minh `hasPageSize()` phân biệt absent với explicit zero. Getter ở cả hai trường hợp đều trả `0`, nên chỉ kiểm tra getter là chưa đủ.

### Kiểm thử serialize/parse

```java
SearchRequest original = SearchRequest.newBuilder()
        .setQuery("keyboard")
        .setPageSize(0)
        .build();

SearchRequest parsed = SearchRequest.parseFrom(
        original.toByteArray());

assertTrue(parsed.hasPageSize());
assertEquals(0, parsed.getPageSize());
```

Kiểm thử thêm request absent để xác nhận `hasPageSize()` vẫn false sau round trip.

### Ma trận tương thích

| Client | Server | Điều cần xác minh |
|---|---|---|
| Cũ | Mới | Field absent dùng default cũ; không bị validation bắt buộc |
| Mới | Mới | Giá trị optional được áp dụng đúng |
| Mới | Cũ | Server cũ bỏ qua field mới; client có fallback nếu feature chưa có |
| Cũ | Cũ | Hành vi nền không thay đổi |

Các test nghiệp vụ nên bao gồm absent, explicit default, giá trị hợp lệ, giá trị ngoài miền, và xung đột với field cũ nếu đang migration.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không biết caller có gửi `false` hay không | Scalar implicit presence | Đổi sang `optional bool` nếu cần explicit presence |
| Request cũ bị từ chối sau deploy | Server mới bắt buộc field vừa thêm | Giữ field tùy chọn và xử lý absent |
| Server áp dụng sai default | Nhầm Protobuf default với business default | Viết rõ nhánh absent và default nghiệp vụ |
| Không phân biệt collection absent và empty | `repeated`/`map` không có presence | Dùng FieldMask hoặc wrapper message |
| Update không thể xóa field về `false`/`0` | Logic chỉ cập nhật khi getter khác default | Dùng `hasX()` |
| Client mới tưởng server cũ đã áp dụng field | Server cũ bỏ qua unknown field | Rollout server trước hoặc capability routing |
| `hasX()` không tồn tại trong Java | Field không có explicit presence hoặc code sinh từ schema cũ | Kiểm tra `optional`, plugin/protoc và generated source |
| Field mới làm thay đổi kết quả request cũ | Business default không tương thích | Giữ hành vi cũ khi field absent |

## 12. Bài tập thực hành

**Tình huống:** Profile API có request cập nhật `display_name` và `notifications_enabled`. Client cũ chỉ gửi `user_id`; client mới cần đổi tên hoặc tắt notifications. Nếu server dùng scalar proto3 implicit presence, nó có thể ghi đè dữ liệu hiện tại bằng `""` hoặc `false` khi client cũ không gửi các field đó.

Hãy thực hiện:

1. Thêm `optional string display_name` và `optional bool notifications_enabled` với tag mới, giữ nguyên `user_id`.
2. Sinh lại Java code và xác minh có `hasDisplayName()` cùng `hasNotificationsEnabled()`.
3. Viết server chỉ cập nhật field có presence; kiểm tra validation cho chuỗi rỗng theo business rule.
4. Kiểm thử client cũ chỉ gửi `user_id`; dữ liệu hiện tại phải được giữ nguyên.
5. Kiểm thử client mới gửi `notifications_enabled = false`; server phải lưu false thay vì bỏ qua.
6. Kiểm thử field absent và explicit default qua serialize/parse.
7. Với một repeated field cần hỗ trợ lệnh xóa hết, thiết kế wrapper message hoặc FieldMask và định nghĩa semantics.
8. Chạy ma trận old/new client-server trước khi bật client mới trong production.

**Tiêu chí hoàn thành:** server phân biệt được absent với explicit default, giữ đúng dữ liệu khi caller cũ không gửi field, áp dụng được `false`/`0`/chuỗi rỗng khi caller chủ động gửi và không phá caller trong rollout.

## 13. Ghi nhớ

Trong proto3, thêm field mới bằng tag chưa dùng và xử lý trường hợp absent với default tương thích giúp mở rộng request an toàn. Dùng `optional` cho scalar khi cần explicit presence: `hasX()` phân biệt field không gửi với field được đặt thành `false`, `0` hoặc `""`. Message field vốn đã có presence; repeated/map thì không, nên cần FieldMask hoặc wrapper message nếu phải phân biệt absent với empty. Trong Java server, cập nhật field dựa trên `hasX()`, kiểm thử cả wire lẫn semantics và deploy server hỗ trợ trước khi client phụ thuộc vào field mới.
