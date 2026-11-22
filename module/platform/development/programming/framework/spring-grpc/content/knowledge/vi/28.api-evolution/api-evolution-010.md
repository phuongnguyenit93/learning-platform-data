# Kiểm thử client cũ với server mới

## 1. Mục tiêu

Trong Spring gRPC, client và server thường được build, phát hành và triển khai độc lập. Server có thể được nâng cấp trước để hỗ trợ field hoặc behavior mới trong khi nhiều client vẫn chạy generated code từ contract cũ. Một thay đổi Protobuf có vẻ additive vẫn có thể làm client cũ lỗi ở runtime hoặc nhận kết quả khác với điều nó mong đợi.

**Kiểm thử client cũ với server mới** xác minh một client được build từ schema và generated code cũ vẫn gọi được server đã nâng cấp, qua transport gRPC thật, với request, response, status và semantics tương thích. Đây là kiểm thử quan trọng trước khi rollout server mới rộng rãi.

Sau bài học, bạn có thể:

- Dựng một client fixture từ phiên bản Protobuf cũ đã phát hành.
- Gọi server Spring gRPC mới qua channel và generated stub cũ.
- Kiểm tra full method path, request cũ và default của field mới.
- Xác minh client cũ xử lý response có field mới hoặc enum value mới.
- Phân biệt wire compatibility với runtime và behavioral compatibility.
- Kiểm thử status, deadline, authorization và regression của method cũ.
- Thiết kế CI để không vô tình regenerate client cũ bằng schema mới.

## 2. Tình huống cần kiểm thử

Giả sử Catalog đã phát hành contract v1:

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

Client cũ đã được build từ schema này. Sau đó server được nâng cấp để hỗ trợ giới hạn trang và token:

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
  optional int32 page_size = 2;
  string page_token = 3;
}

message SearchResponse {
  repeated string product_ids = 1;
  string next_page_token = 2;
}
```

Full method path vẫn là:

```text
/catalog.v1.CatalogService/Search
```

Client cũ gửi field query ở tag 1. Server mới parse được request; hai field mới không xuất hiện trong bytes và phải được xử lý theo default tương thích. Response server mới có thể chứa tag 2 mà client cũ chưa biết; parser cũ phải đọc được các field nó hiểu và bỏ qua field lạ một cách an toàn.

Kiểm thử cần chứng minh cả hai chiều: **old request → new server** và **new response → old client**.

## 3. Những điều cần giữ nguyên

### Full method path

gRPC định tuyến theo package, service và method name. Thêm field vào message không đổi path nếu các tên này giữ nguyên. Nếu server mới đổi package thành catalog.v2 hoặc đổi tên service/method, client cũ vẫn gọi path v1 và có thể nhận UNIMPLEMENTED.

### Field number và wire type

Client cũ gửi field number đã biết. Server mới phải tiếp tục diễn giải field đó theo wire type và semantics đã công bố. Không tái sử dụng field number đã xóa; reserve số và tên trong schema mới.

Không xem việc hai kiểu cùng dùng wire type là đủ để đổi kiểu an toàn. Ví dụ int32 và int64 đều dùng varint nhưng khác miền giá trị; int32 và sint32 đều có wire type varint nhưng cách mã hóa số âm khác nhau. Thay kiểu hoặc ý nghĩa field cần được đánh giá riêng.

### Default khi field mới vắng mặt

Request cũ không thể gửi field mà nó chưa được sinh ra. Server mới phải xử lý absence:

- Scalar implicit presence trả giá trị mặc định của Protobuf.
- Scalar optional có thể dùng hasX() để biết field không được gửi.
- Message field có presence; server có thể kiểm tra hasX().
- Repeated/map vắng mặt được nhìn như collection rỗng.

Nếu page_size mới là optional, server có thể dùng default nghiệp vụ 25 khi hasPageSize() là false. Không bắt buộc caller cũ phải gửi field mới.

### Response field mới

Client cũ parse response mới sẽ không có accessor cho field mới. Nó chỉ sử dụng các field đã biết. Unknown fields thường được giữ trong UnknownFieldSet của Protobuf Java và có thể được bảo toàn khi parse rồi serialize lại, nhưng ứng dụng không nên dựa vào việc client cũ hiểu hoặc thực thi semantics của field mới.

## 4. Đóng băng generated client cũ

Đây là điều kiện quan trọng nhất của test. Nếu CI regenerate client fixture từ schema mới, bài test không còn kiểm tra client cũ.

Một fixture đáng tin cậy nên:

1. Lấy file proto từ tag/release thực sự đã phát hành.
2. Dùng đúng generated Java artifact cũ hoặc sinh lại bằng đúng compiler/plugin version cũ đã pin.
3. Không cập nhật source proto của fixture khi server schema mới thay đổi.
4. Lưu version và commit/release nguồn của fixture để test có thể tái lập.
5. Xác nhận classpath của fixture dùng runtime tương thích với generated code cũ.

Có hai cách tổ chức phổ biến:

| Cách tổ chức | Khi phù hợp | Lưu ý |
|---|---|---|
| Module fixture riêng | Monorepo có thể build nhiều module | Đóng gói generated client cũ thành artifact test-only |
| Process riêng | Muốn mô phỏng deployment độc lập sát production | Chạy client cũ với classpath và runtime cũ của nó |

Nếu hai schema có cùng Protobuf package và service name, tránh đưa hai bản generated source có cùng Java fully qualified class name vào một source set. Có thể build fixture cũ thành module/artifact riêng, dùng Java package riêng nhưng giữ nguyên Protobuf package/service/method để full method path vẫn giống; hoặc chạy client cũ trong process riêng. Java package không quyết định gRPC method path.

Nếu mục tiêu là kiểm tra đúng binary client đã phát hành, ưu tiên chạy process riêng với đúng JAR và runtime dependency cũ. Đổi riêng `java_package` sang package test-only giúp viết in-process test thuận tiện mà không đổi wire path, nhưng fixture đó không còn là binary Java artifact nguyên bản; hãy xem nó là kiểm thử wire/generated-shape bổ sung, không thay thế kiểm thử artifact thật.

Không dùng client mới rồi chỉ xóa field mới khỏi request để giả lập client cũ. Cách đó không kiểm tra generated API, parser và runtime thật của phiên bản client cũ.

## 5. Runtime của hai phía không cần cùng phiên bản

Client và server là hai tiến trình độc lập. Client cũ có thể dùng Protobuf Java runtime và gRPC Java runtime của release cũ; server mới có thể dùng runtime mới hơn. Hai phía giao tiếp qua wire protocol, không chia sẻ Java classpath.

Điều cần bảo đảm:

- Generated client cũ tương thích với runtime trong process client cũ.
- Generated server mới tương thích với runtime trong process server mới.
- Cả hai phía tuân thủ cùng wire contract và gRPC protocol.
- TLS, compression, message size và các transport setting được hỗ trợ ở cả hai phía.

Không cần ép server mới dùng cùng version thư viện Java với client cũ chỉ vì chúng giao tiếp với nhau. Nhưng nếu nhét cả hai bộ generated code vào cùng một process test, phải quản lý classpath và tên class để tránh xung đột.

## 6. Chạy client cũ tới Spring gRPC server mới

Test phải khởi động server Spring thật với service implementation mới. Client fixture dùng blocking hoặc async stub được sinh từ schema cũ.

Ví dụ phần gọi từ test:

```java
ManagedChannel channel = ManagedChannelBuilder
        .forAddress("localhost", serverPort)
        .usePlaintext()
        .build();

try {
    var oldStub =
            dev.example.catalog.legacy.CatalogServiceGrpc
                    .newBlockingStub(channel)
                    .withDeadlineAfter(2, TimeUnit.SECONDS);

    var oldRequest =
            dev.example.catalog.legacy.SearchRequest.newBuilder()
                    .setQuery("keyboard")
                    .build();

    var oldResponse = oldStub.search(oldRequest);

    assertFalse(oldResponse.getProductIdsList().isEmpty());
} finally {
    channel.shutdown();
    if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
        channel.shutdownNow();
    }
}
```

Ví dụ giả định generated client cũ được đóng gói trong package test-only riêng, nhưng schema của nó vẫn dùng package/service/method cũ nên full method path trùng với server. serverPort phải là cổng thực tế của Spring gRPC test server; cấu hình cổng ngẫu nhiên và cách lấy port phụ thuộc starter/version đang dùng. Không tự khởi động thêm một server cạnh server do Spring quản lý.

Package `dev.example.catalog.legacy` trong ví dụ là package fixture được cô lập để tránh trùng class với generated server. Nếu dùng đúng artifact cũ có cùng fully qualified class name với generated server mới, chạy client ở process riêng thay vì đổi package của artifact đã phát hành.

Trong integration test, dùng transport thật và service bean thật. Có thể mock repository hoặc external dependency phía sau application service, nhưng không mock stub hay bỏ qua gRPC server registration nếu mục tiêu là kiểm tra tương thích transport.

## 7. Kiểm thử request cũ và default mới

Server mới có thể nhận request cũ không có page_size. Handler phải áp dụng default tương thích:

```java
int pageSize = request.hasPageSize()
        ? request.getPageSize()
        : LEGACY_DEFAULT_PAGE_SIZE;
```

Với request được sinh từ schema mới, unit test có thể kiểm tra cả hai trạng thái:

```java
var absent = SearchRequest.newBuilder()
        .setQuery("keyboard")
        .build();

assertFalse(absent.hasPageSize());

var explicitZero = SearchRequest.newBuilder()
        .setQuery("keyboard")
        .setPageSize(0)
        .build();

assertTrue(explicitZero.hasPageSize());
```

Integration test client cũ chứng minh server nhận request thiếu field mới và chọn default đã công bố. Chỉ test builder mới tạo request absent chưa đủ vì nó không chứng minh old generated client thật sự gửi wire payload như kỳ vọng.

Không để server mới trả INVALID_ARGUMENT chỉ vì page_size absent nếu client cũ không thể biết field đó. Nếu nghiệp vụ mới cần input bắt buộc, hãy giữ một default tương thích, thêm method mới hoặc version hóa contract.

## 8. Kiểm thử response mới với parser cũ

Server mới có thể trả thêm next_page_token. Client cũ không có getter cho field này, nhưng phải parse thành công và vẫn đọc product_ids:

```java
var response = oldStub.search(oldRequest);

assertEquals(
        List.of("product-1", "product-2"),
        response.getProductIdsList());
```

Để xác minh server thực sự phát field mới, có thể dùng client mới trong một test riêng hoặc kiểm tra bytes response bằng parser mới. Không thể yêu cầu generated client cũ đọc accessor chưa tồn tại.

Một test wire độc lập có thể xác minh:

1. Server mới tạo response với field cũ và field mới.
2. Serialize response thành bytes.
3. Parser generated cũ đọc bytes thành công.
4. Field cũ giữ đúng giá trị.
5. Parser mới đọc được field mới.

Unknown field không nên được dùng làm cơ chế truyền semantics bắt buộc cho client cũ. Client cũ sẽ không biết phải làm gì với field đó.

## 9. Enum value mới và giả định của client cũ

Nếu server mới trả enum numeric value mà client cũ chưa biết, generated Java Protobuf thường biểu diễn getter enum là UNRECOGNIZED; accessor numeric như getStatusValue() có thể cho phép đọc raw value. Code client cũ phải xử lý trường hợp này thay vì giả định enum chỉ có các giá trị đã biết.

Ví dụ schema cũ:

```proto
enum OrderState {
  ORDER_STATE_UNSPECIFIED = 0;
  ORDER_STATE_PENDING = 1;
  ORDER_STATE_COMPLETED = 2;
}
```

Server mới thêm:

```proto
enum OrderState {
  ORDER_STATE_UNSPECIFIED = 0;
  ORDER_STATE_PENDING = 1;
  ORDER_STATE_COMPLETED = 2;
  ORDER_STATE_ON_HOLD = 3;
}
```

Client cũ nhận numeric value 3 có thể trả enum constant UNRECOGNIZED. Nếu code cũ dùng switch và mặc định coi mọi giá trị ngoài danh sách là lỗi không thể phục hồi, response mới có thể gây lỗi nghiệp vụ dù wire parse thành công.

Vì vậy, trước khi server bắt đầu trả enum value mới, xác minh mọi client cũ liên quan có hành vi fallback an toàn. Với trạng thái quan trọng, có thể giữ response legacy mapping hoặc chỉ bật enum mới sau khi caller đã nâng cấp.

## 10. Kiểm thử method path và service registration

Client cũ gọi full method path được tạo từ Protobuf package, service và method. Test nên xác minh path này vẫn tồn tại trên server mới.

Các tình huống:

| Thay đổi server | Kết quả đối với client cũ |
|---|---|
| Thêm field vào request/response, giữ package/service/method | Path không đổi; có thể tương thích wire |
| Thêm method mới, giữ method cũ | Client cũ tiếp tục gọi method cũ |
| Đổi Protobuf package | Full method path đổi; client cũ có thể nhận UNIMPLEMENTED |
| Đổi service name | Full method path đổi |
| Đổi method name | Full method path đổi |
| Xóa handler cũ | Client cũ có thể nhận UNIMPLEMENTED |

Không chỉ kiểm tra generated descriptor ở compile time. Hãy gọi qua server Spring đã khởi động để chứng minh bean được đăng ký và route thực sự tồn tại.

## 11. Kiểm thử status, deadline và authorization

Compatibility không chỉ là nhận được response thành công. Client cũ có thể phụ thuộc vào status và metadata mà server cũ đã trả.

Kiểm thử tối thiểu:

- Request sai định dạng vẫn trả status đã cam kết, thường là INVALID_ARGUMENT.
- Resource không tồn tại vẫn có mapping status ổn định.
- Caller thiếu quyền vẫn nhận PERMISSION_DENIED hoặc UNAUTHENTICATED đúng trường hợp.
- Deadline ngắn vẫn kết thúc theo contract; server không tiếp tục side effect ngoài ý muốn sau cancellation.
- Client cũ không gửi metadata version mới vẫn được xử lý theo default legacy.
- Response metadata/trailers mới không làm parser cũ lỗi.

Không thay đổi status sang một loại khác chỉ vì server implementation được refactor. Caller có thể phân nhánh theo status, retry hoặc hiển thị thông báo dựa vào nó.

## 12. Kiểm thử behavioral regression

Một request cũ có thể được parse hoàn hảo nhưng server mới vẫn trả kết quả khác. Cần có characterization test cho semantics cũ:

| Hành vi | Điều cần xác minh |
|---|---|
| Default | Field mới absent vẫn dùng default cũ |
| Ordering | Thứ tự kết quả không đổi nếu contract cũ đã cam kết |
| Empty result | Danh sách rỗng vẫn có status và shape như trước |
| Pagination | Không tự áp dụng token/page semantics mới cho caller cũ |
| Validation | Request hợp lệ theo v1 không bị từ chối bởi rule chỉ dành cho v2 |
| Idempotency | Retry request cũ không tạo side effect trùng |
| Authorization | Không mở rộng hoặc thu hẹp quyền ngoài kế hoạch |

Nếu server mới thay đổi default sort hoặc validation cho tất cả caller, test client cũ sẽ phát hiện regression mà schema diff không thể chỉ ra.

## 13. Tổ chức test trong CI

Một pipeline có thể chia thành các lớp:

1. **Proto compatibility check:** kiểm tra thay đổi schema, field number, wire type và method path.
2. **Old client fixture build:** build artifact client cũ từ proto đã đóng băng hoặc dùng binary artifact đã phát hành.
3. **New server build:** sinh code từ schema mới và build Spring gRPC application.
4. **Integration test:** khởi động server mới, gọi bằng generated stub cũ.
5. **Behavioral regression:** xác minh default, response, status và side effect cũ.
6. **Mixed-version matrix:** kiểm tra các tổ hợp client/server cần hỗ trợ trong rollout.
7. **Release gate:** không phát hành server mới nếu old-client test bắt buộc thất bại.

Đừng lấy proto cũ từ thư mục hiện tại rồi chạy code generation bằng plugin mới và gọi nó là client cũ. Fixture cần đại diện cho artifact đã được phát hành. Nếu phải regenerate, pin chính xác schema và toolchain cũ, lưu provenance và kiểm tra generated diff.

Một test client cũ chạy trong cùng JVM với server mới là đủ nếu generated class không xung đột và runtime từng phía được quản lý rõ. Nếu không, chạy client fixture trong process riêng qua localhost/container để tái hiện classpath và runtime độc lập.

## 14. Ma trận kiểm thử

| Client | Server | Mục tiêu |
|---|---|---|
| Cũ | Cũ | Baseline trước nâng cấp |
| Cũ | Mới | Bài kiểm thử trọng tâm: old client/new server |
| Mới | Mới | Xác minh contract mới |
| Mới | Cũ | Xác minh field/method mới được xử lý theo kế hoạch, thường là unknown field hoặc UNIMPLEMENTED |

Đối với rollout server trước client, cặp cũ/mới đặc biệt quan trọng. Client cũ phải tiếp tục hoạt động trên server mới trong toàn bộ support window. Nếu client mới cũng cần chạy trên server cũ, đó là một bài compatibility ngược riêng và phải có test riêng.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Test pass nhưng không phải client cũ | Fixture được regenerate từ schema mới | Đóng băng artifact/proto và toolchain cũ |
| Client cũ nhận UNIMPLEMENTED | Server đổi package/service/method hoặc bỏ handler | Giữ full method path và handler cũ |
| Client cũ parse response thất bại | Thay đổi wire type hoặc payload không tương thích | Kiểm tra field number/wire type và schema history |
| Client cũ đọc field mới thành default | Server kỳ vọng caller hiểu field mới | Giữ default legacy; không bắt caller cũ gửi field mới |
| Kết quả thay đổi dù wire parse thành công | Server đổi default hoặc semantics | Thêm behavioral regression tests |
| Client cũ không xử lý enum mới | Switch logic giả định enum exhaustive | Có nhánh UNRECOGNIZED/fallback hoặc giữ mapping cũ |
| Class generated trùng nhau trong test | Hai schema cùng Java package/class name | Tách module, Java package hoặc process |
| Test phụ thuộc port cố định | Nhiều test chạy song song hoặc port bị chiếm | Dùng cổng ngẫu nhiên và lấy port từ test server |
| Runtime mismatch trong fixture | Generated code cũ dùng sai runtime trong process test | Pin runtime tương ứng hoặc chạy process riêng |
| Unit test pass nhưng server không route | Chỉ mock handler/stub | Chạy Spring gRPC server integration test |

## 16. Bài tập thực hành

**Tình huống:** Client Catalog v1 đã được phát hành rộng rãi. Server mới thêm optional page_size và next_page_token nhưng vẫn giữ RPC Search. Một số client cũ không thể nâng cấp trong tháng này.

Hãy thực hiện:

1. Lấy đúng proto/generated artifact v1 đã phát hành và đóng băng làm old-client fixture.
2. Build Spring gRPC server mới từ schema có field page_size và next_page_token.
3. Xác minh Protobuf package, service name, method name và full method path không đổi.
4. Khởi động server mới trên cổng test ngẫu nhiên; gọi bằng blocking stub cũ qua ManagedChannel thật.
5. Xác minh server xử lý request thiếu page_size bằng default tương thích.
6. Xác minh client cũ đọc được product_ids dù response có next_page_token mới.
7. Kiểm thử status, deadline, authorization, ordering và empty-result behavior của v1.
8. Nếu server mới thêm enum value, kiểm thử client cũ nhận UNRECOGNIZED và xử lý an toàn.
9. Chạy baseline client cũ/server cũ và client cũ/server mới trong CI; lưu kết quả như release gate.
10. Chỉ rollout server sau khi old-client integration và behavioral regression tests pass.

**Tiêu chí hoàn thành:** fixture thực sự dùng generated code cũ; client gọi server Spring mới qua transport thật; request cũ được xử lý với default đúng; response mới parse được; method path, status và semantics cũ được giữ; CI có thể tái lập kiểm thử.

## 17. Ghi nhớ

Kiểm thử client cũ với server mới phải dùng generated client artifact thực sự cũ, không regenerate fixture từ schema mới. Giữ Protobuf package/service/method để full method path không đổi; server mới phải xử lý field mới absent bằng default tương thích và client cũ phải parse response có unknown field. Kiểm tra enum mới, status, deadline, authorization và behavioral regression, không chỉ serialize/parse. Runtime Java của client và server có thể khác phiên bản vì chúng giao tiếp qua wire, nhưng generated code phải tương thích với runtime trong chính process của nó. Một Spring gRPC integration test qua channel thật, kết hợp fixture cũ được đóng băng, là release gate đáng tin cậy trước khi rollout server mới.
