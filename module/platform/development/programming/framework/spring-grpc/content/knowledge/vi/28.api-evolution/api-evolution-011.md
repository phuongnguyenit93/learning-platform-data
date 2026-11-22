# Kiểm thử server cũ với client mới

## 1. Mục tiêu

Trong hệ thống Spring gRPC, client và server thường được build và triển khai độc lập. Một client mới có thể được phát hành trước khi toàn bộ server đã nâng cấp, hoặc một service mới có thể vô tình kết nối tới replica cũ trong rolling deployment. Khi đó, client mới phải giao tiếp với server chỉ hiểu contract cũ.

**Kiểm thử server cũ với client mới** xác minh một client được sinh từ schema mới vẫn có hành vi an toàn khi gọi server được build từ schema cũ. Đây là chiều tương thích quan trọng khi client có thể được triển khai độc lập, khi load balancer còn replica cũ hoặc khi rollback server xảy ra sau khi client mới đã phát hành.

Điểm cần kiểm tra không chỉ là request có parse được. Server cũ có thể bỏ qua field mới, xử lý request theo default cũ và trả response thành công nhưng không thực hiện semantics mà client mới yêu cầu. Vì vậy bài kiểm thử phải xác minh cả wire behavior lẫn kết quả nghiệp vụ.

Sau bài học, bạn có thể:

- Dựng server fixture từ schema/generated artifact cũ đã phát hành.
- Gọi server cũ bằng generated client mới qua transport gRPC thật.
- Kiểm tra request field mới bị server cũ bỏ qua và đánh giá tác động.
- Kiểm tra response thiếu field mới được client mới diễn giải như thế nào.
- Xử lý enum value, oneof alternative và RPC method mới mà server cũ chưa biết.
- Thiết kế capability detection, fallback và rollout an toàn.
- Đưa kiểm thử old-server/new-client vào CI trước khi phát hành client.

## 2. Tình huống kiểm thử

Giả sử Catalog v1 chỉ hỗ trợ query:

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

Client mới được sinh từ schema đã thêm category và pagination:

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
  string category = 2;
  optional int32 page_size = 3;
  string page_token = 4;
}

message SearchResponse {
  repeated string product_ids = 1;
  string next_page_token = 2;
}
```

Full method path vẫn giống nhau:

```text
/catalog.v1.CatalogService/Search
```

Client mới có thể tạo request với category và page_size, nhưng server cũ chỉ biết query. Với Protobuf binary, parser cũ thường đọc field đã biết và giữ field lạ trong unknown fields; application code cũ không có accessor để dùng category hoặc page_size. Server có thể trả response bình thường theo cách tìm kiếm v1.

Client mới parse được response v1, nhưng field next_page_token không có trong bytes. Giá trị của field mới sẽ là default; nếu là optional scalar, presence sẽ là false. Do đó client không được mặc định rằng response thành công đồng nghĩa server đã hỗ trợ pagination.

## 3. Phân biệt wire compatibility và feature compatibility

| Câu hỏi | Wire compatibility | Feature/behavior compatibility |
|---|---|---|
| Request có parse được không? | Có thể có | Chưa đủ kết luận |
| Server có hiểu field mới không? | Không được bảo đảm | Phải xác minh |
| Server có thực hiện semantics mới không? | Không được bảo đảm | Phải xác minh |
| Client có parse response cũ không? | Thường có nếu thay đổi additive | Chưa chắc đáp ứng yêu cầu nghiệp vụ |
| Method mới có được server cũ đăng ký không? | Không nếu server chưa có method | Thường nhận UNIMPLEMENTED |

Một thay đổi additive trong schema có thể cho phép client mới gửi request tới server cũ mà không lỗi parse. Nhưng server cũ không tự động thực hiện tính năng mới. Nếu client cần pagination chính xác, category filter hoặc một quy tắc bảo mật mới, việc field bị bỏ qua có thể gây kết quả sai hoặc lộ dữ liệu ngoài dự kiến.

Hãy phân loại từng thay đổi trước khi viết test:

- **Field tùy chọn mới:** server cũ có thể bỏ qua; client phải biết server có hỗ trợ hay không.
- **Response field mới:** server cũ không gửi; client mới phải xử lý absence.
- **Enum value mới:** server cũ có thể parse numeric value trong proto3 nhưng code cũ không biết ý nghĩa.
- **Oneof alternative mới:** server cũ có thể thấy oneof chưa được set.
- **RPC method mới:** server cũ không có handler và thường trả UNIMPLEMENTED.
- **Package/service/method đổi tên:** full method path đổi, client mới gọi path mới mà server cũ không đăng ký.

## 4. Server cũ xử lý request có unknown fields

Với Protobuf binary, field được nhận diện bằng field number và wire type. Nếu parser gặp field number không có trong schema cũ, Protobuf runtime thường lưu nó như unknown field thay vì coi đó là lỗi.

Điều này cho phép một message mới có thêm field vẫn được parse bởi code cũ, với điều kiện các field cũ giữ nguyên field number và wire type. Tuy nhiên:

- Handler cũ chỉ nhìn thấy field được định nghĩa trong generated code cũ.
- Unknown field không tự kích hoạt logic mới.
- Nếu server chuyển message thành domain object rồi tạo message khác, unknown field có thể không được giữ qua bước chuyển đổi.
- Gateway/proxy hoặc custom parser có thể có quy tắc riêng; cần kiểm thử đường đi thực tế.
- Không được tái sử dụng field number đã xóa cho một ý nghĩa khác.

Ví dụ client mới gửi:

```java
var request = NewSearchRequest.newBuilder()
        .setQuery("keyboard")
        .setCategory("electronics")
        .setPageSize(10)
        .build();
```

Server cũ chỉ có generated class với query:

```java
LegacySearchRequest legacyRequest =
        LegacySearchRequest.parseFrom(request.toByteArray());

assertEquals("keyboard", legacyRequest.getQuery());
assertTrue(legacyRequest.getUnknownFields()
        .hasField(2));
assertTrue(legacyRequest.getUnknownFields()
        .hasField(3));
```

Ví dụ dùng hai message class từ schema cũ và mới trong test fixture. Trong ứng dụng thực tế, client và server là hai process; test trên chỉ minh họa parser behavior. Unknown fields được giữ trong message Protobuf nếu message đó được parse và serialize lại trực tiếp, nhưng application không thể thực hiện category filter chỉ từ một field mà generated code cũ không định nghĩa.

## 5. Rủi ro khi server cũ âm thầm bỏ qua field mới

Đây là lỗi khó phát hiện nhất. Client gửi request thành công, server trả status OK, nhưng kết quả không đáp ứng lựa chọn mới.

Ví dụ:

- Client gửi category = electronics; server cũ tìm trên mọi category.
- Client gửi page_size = 10; server cũ trả toàn bộ danh sách theo giới hạn cũ.
- Client gửi sort_order = NEWEST; server cũ vẫn sort theo relevance.
- Client gửi include_archived = false; server cũ dùng policy mặc định khác.

Không nên suy ra feature support từ status OK. Status chỉ cho biết RPC đã hoàn tất theo logic server hiện tại.

Client mới cần một trong các cơ chế sau trước khi phụ thuộc vào field mới:

1. **Capability check:** hỏi server qua một RPC ổn định mà cả server cũ và mới đều biết, nếu capability contract đã được triển khai trước đó.
2. **Versioned endpoint/routing:** định tuyến client mới tới fleet chắc chắn hỗ trợ contract cần dùng.
3. **Feature rollout có kiểm soát:** chỉ bật feature sau khi server rollout hoàn tất và đã xác minh toàn bộ replica.
4. **Semantics fallback:** dùng cách gọi cũ khi tương đương nghiệp vụ và có thể chứng minh kết quả an toàn.

Metadata như x-api-version không tự tạo capability. Server cũ có thể bỏ qua metadata lạ; client không được coi việc gửi header là bằng chứng server đã đọc hoặc chấp nhận version đó.

## 6. Client mới đọc response từ server cũ

Server cũ chỉ trả các field đã biết:

```java
LegacySearchResponse response =
        LegacySearchResponse.newBuilder()
                .addProductIds("product-1")
                .addProductIds("product-2")
                .build();
```

Client mới parse response bytes:

```java
NewSearchResponse response =
        NewSearchResponse.parseFrom(
                legacyResponse.toByteArray());

assertEquals(2, response.getProductIdsCount());
assertEquals("", response.getNextPageToken());
```

Nếu next_page_token là string implicit-presence, getter trả chuỗi rỗng khi field không có. Nếu field được khai báo optional, client có thể kiểm tra hasNextPageToken() để phân biệt absent với explicit empty.

Client phải định nghĩa rõ ý nghĩa của response thiếu field mới:

- Nếu absence nghĩa là không có trang tiếp theo, có thể kết thúc pagination.
- Nếu feature bắt buộc server trả token, absence phải được coi là server chưa hỗ trợ hoặc response không hợp lệ.
- Không tự tạo token giả hoặc lặp lại cùng request vô hạn.
- Không chuyển một response cũ thành response mới với semantics không được bảo đảm.

Với field số hoặc boolean, giá trị default có thể trông giống một giá trị nghiệp vụ hợp lệ. Dùng explicit presence khi client cần phân biệt “server không gửi” với “server gửi giá trị 0/false”.

## 7. Enum mới và oneof mới

### Enum value mới

Proto3 dùng open enum semantics. Khi server cũ nhận numeric enum value mà generated code cũ chưa biết, runtime có thể giữ numeric value; getter enum trong Java trả UNRECOGNIZED và getter numeric cho phép đọc giá trị thô. Nhưng business logic cũ có thể:

- Chuyển mọi giá trị không biết thành UNSPECIFIED.
- Rơi vào nhánh default của switch.
- Trả INVALID_ARGUMENT dù wire parser đã đọc được.
- Áp dụng hành vi cũ không tương đương với lựa chọn mới.

Vì vậy, không gửi enum value mới tới server cũ nếu server phải thực hiện semantics của giá trị đó. Chỉ bật sau capability check hoặc routing tới server đã hỗ trợ.

### Oneof alternative mới

Giả sử client mới thêm một alternative vào oneof. Server cũ không biết field mới đó; khi parse, oneof cũ có thể có trạng thái NOT_SET. Nếu handler cũ hiểu NOT_SET là một lựa chọn mặc định, request có thể được xử lý theo nhánh khác mà không báo lỗi.

Test phải xác minh client mới không gửi alternative mới tới server cũ trước khi capability được xác nhận. Không chỉ kiểm tra request serialize thành công.

## 8. Gọi RPC method mới tới server cũ

Nếu client mới gọi method mà server cũ chưa đăng ký, gRPC thường trả:

```text
UNIMPLEMENTED
```

Ví dụ client stub đã có:

```java
var response = newStub.getRecommendations(request);
```

nhưng server cũ chỉ đăng ký Search. Server không có handler cho full method path mới và call kết thúc với UNIMPLEMENTED.

Client có thể fallback sang method cũ nếu method cũ cung cấp kết quả tương đương. Fallback phải:

- Có điều kiện rõ ràng, không áp dụng cho mọi status.
- Chỉ thực hiện khi method cũ vẫn được hỗ trợ.
- Giữ semantics, authorization và giới hạn dữ liệu.
- Có metric để biết fallback đang xảy ra.
- Có thời hạn hoặc điều kiện gỡ bỏ.

Không fallback tự động với UNAVAILABLE, DEADLINE_EXCEEDED hoặc PERMISSION_DENIED. Các status này có nguyên nhân khác; retry/fallback mù có thể tạo side effect trùng hoặc che giấu sự cố.

## 9. Capability detection và version routing

Một cách chắc chắn là server cung cấp capability RPC đã tồn tại từ trước:

```proto
message GetCapabilitiesRequest {}

message GetCapabilitiesResponse {
  repeated string capabilities = 1;
}

service CatalogService {
  rpc Search(SearchRequest) returns (SearchResponse);
  rpc GetCapabilities(GetCapabilitiesRequest)
      returns (GetCapabilitiesResponse);
}
```

Nếu GetCapabilities đã có trong contract cũ, server cũ có thể trả danh sách capability legacy; server mới trả thêm pagination hoặc category-filter. Client mới gọi RPC này trước khi bật tính năng mới.

Nếu RPC capability chỉ được thêm trong phiên bản mới, server cũ cũng không biết method đó và sẽ trả UNIMPLEMENTED. Khi đó cần một cơ chế discovery ngoài band đã được thiết lập, endpoint versioned hoặc cấu hình rollout.

Server reflection có thể giúp khám phá service/method descriptor nếu được bật và được phép truy cập, nhưng không chứng minh server hỗ trợ đúng semantics hay capability nghiệp vụ. Reflection cũng không phải lúc nào được bật trong production.

Một capability response nên mô tả tính năng có thể sử dụng trên endpoint cụ thể. Nếu load balancer phân phối request tới nhiều replica có khả năng khác nhau, discovery phải phản ánh toàn bộ route hoặc hệ thống phải bảo đảm routing theo capability. Không để một replica mới trả capability v2 rồi client sau đó bị route tới replica cũ.

## 10. Thiết kế client mới có fallback an toàn

Gateway có thể kiểm tra capability rồi chọn call phù hợp:

```java
public SearchResult search(SearchCriteria criteria) {
    Capabilities capabilities = capabilityProvider.forTarget();

    if (capabilities.supports("category-filter")) {
        return callSearchWithCategory(criteria);
    }

    if (criteria.requiresCategoryFilter()) {
        throw new UnsupportedOperationException(
                "Target server does not support category filtering");
    }

    return callLegacySearch(criteria);
}
```

Đây là khung minh họa; capability provider cần cache theo target/endpoint, có expiry và xử lý refresh khi fleet thay đổi. Không cache capability vô thời hạn vì server có thể được nâng cấp hoặc rollback.

Nếu server cũ không hỗ trợ capability discovery, client có thể được cấu hình rõ là chỉ dùng contract legacy cho endpoint đó. Tránh thử mọi method mới rồi bắt lỗi để dò capability trên từng request; cách đó tăng latency và tạo nhiều lỗi có chủ đích trong telemetry.

Fallback chỉ hợp lệ khi client có thể biểu diễn yêu cầu bằng API cũ mà không mất semantics quan trọng. Nếu filter category là yêu cầu bắt buộc, gọi Search v1 không có filter rồi tự lọc ở client chỉ an toàn khi client có đủ dữ liệu, quyền truy cập và dữ liệu trả về không bị giới hạn trước khi lọc.

## 11. Dựng old-server fixture đúng cách

Test chỉ có giá trị khi server fixture thực sự được build từ contract cũ:

1. Lấy proto và generated server artifact từ release/tag cũ đã phát hành.
2. Pin đúng protoc, gRPC Java plugin và runtime của server cũ.
3. Không regenerate server fixture bằng schema mới.
4. Khởi chạy server cũ trong process riêng nếu class name hoặc runtime xung đột với server mới.
5. Dùng client generated mới trong process test khác hoặc module fixture độc lập.
6. Kết nối qua localhost/container bằng gRPC channel thật.
7. Ghi lại version, commit và checksum artifact để fixture tái lập được.

Nếu test chạy cả old server và new client trong cùng JVM, generated class có thể trùng fully qualified name. Đổi Java package trong fixture giúp cô lập class nhưng không còn đại diện chính xác cho binary artifact đã phát hành. Với kiểm thử deployment fidelity, ưu tiên process riêng và đúng artifact/runtime cũ.

## 12. Integration test old server/new client

Một bài test cơ bản gọi method cũ còn tồn tại:

```java
ManagedChannel channel = ManagedChannelBuilder
        .forAddress("localhost", oldServerPort)
        .usePlaintext()
        .build();

try {
    var newStub = NewCatalogServiceGrpc.newBlockingStub(channel)
            .withDeadlineAfter(2, TimeUnit.SECONDS);

    var request = NewSearchRequest.newBuilder()
            .setQuery("keyboard")
            .setCategory("electronics")
            .setPageSize(10)
            .build();

    var response = newStub.search(request);

    assertFalse(response.getProductIdsList().isEmpty());
    // Kiểm tra riêng server có thực sự áp dụng category/page size hay không.
} finally {
    channel.shutdown();
    if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
        channel.shutdownNow();
    }
}
```

Test này chỉ chứng minh RPC có thể hoàn tất và response parse được. Nó **không chứng minh** server cũ đã áp dụng category hoặc page_size. Muốn xác minh semantics, cần fixture dữ liệu có sản phẩm ở nhiều category và số lượng vượt giới hạn, sau đó xác nhận hành vi thực tế của server cũ đúng với điều client chấp nhận.

Nếu test yêu cầu server cũ phải lọc category nhưng schema v1 không có khái niệm đó, kết quả đúng là feature không được hỗ trợ. Test nên xác minh client không bật feature và không báo thành công giả.

## 13. Ma trận kiểm thử cần có

| Client | Server | Kết quả mong đợi |
|---|---|---|
| Cũ | Cũ | Baseline hoạt động |
| Mới, chỉ dùng field/method cũ | Cũ | Hoạt động theo semantics cũ |
| Mới gửi field request mới | Cũ | Server bỏ qua field; client không giả định feature được áp dụng |
| Mới đọc response field mới | Cũ | Field mới absent/default; client xử lý rõ |
| Mới gửi enum/oneof value mới | Cũ | Không bật nếu server chưa hỗ trợ; xác minh unknown behavior |
| Mới gọi RPC method mới | Cũ | UNIMPLEMENTED hoặc route/capability ngăn call |
| Mới | Mới | Feature mới hoạt động đúng |

Ngoài ma trận trên, kiểm tra:

- Status mapping và error trailers.
- Deadline, cancellation và retry.
- Authentication/authorization.
- Message size, compression và metadata.
- Idempotency nếu RPC có side effect.
- Client không cache capability quá thời hạn.
- Load balancer không trộn replica chưa hỗ trợ sau khi client bật feature.

## 14. CI và rollout gate

CI nên có một old-server fixture ổn định:

1. Build new client từ schema hiện tại.
2. Khởi chạy old server artifact đã đóng băng.
3. Gọi các RPC cũ bằng new stub qua transport thật.
4. Gửi field mới và xác minh server cũ bỏ qua theo wire behavior dự kiến.
5. Xác minh client diễn giải response thiếu field mới đúng cách.
6. Xác minh RPC mới trả UNIMPLEMENTED hoặc không được gọi khi capability thiếu.
7. Chạy behavioral tests cho các flow mà client tuyên bố hỗ trợ với server cũ.
8. Lưu test result và artifact version như release evidence.

Không dùng test mock server để thay thế old-server fixture. Mock thường không tái hiện parser, service registration, method path, runtime dependency hoặc hành vi unknown fields của generated code cũ.

Khi client mới bắt buộc một feature chỉ có server mới hỗ trợ, rollout server phải hoàn tất trước khi bật client feature. Có thể phát hành client mới trước nhưng để feature flag tắt; chỉ bật sau khi mọi target liên quan đã xác nhận capability.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| RPC trả OK nhưng filter mới không hoạt động | Server cũ bỏ qua request field mới | Capability check hoặc giữ feature tắt |
| Client mới nhận page token rỗng | Server cũ không gửi response field mới | Xử lý absence theo contract |
| Client gửi enum mới nhưng server chạy nhánh mặc định | Server cũ không hiểu semantics enum | Chỉ gửi sau capability confirmation |
| Oneof mới bị coi như NOT_SET | Server cũ không biết alternative mới | Không gửi alternative mới tới server cũ |
| RPC mới trả UNIMPLEMENTED | Server cũ chưa đăng ký method | Deploy server trước hoặc fallback có kiểm soát |
| Test pass nhưng server fixture đã mới | CI regenerate old fixture từ schema mới | Pin artifact/proto cũ và provenance |
| Capability check báo hỗ trợ nhưng request tới replica cũ | Discovery và load balancing không nhất quán | Route theo capability hoặc rollout toàn fleet |
| Fallback che lỗi server | Fallback mọi status hoặc không ghi metric | Chỉ fallback theo điều kiện, đo và đặt expiry |
| Client báo feature thành công dù server bỏ qua | Chỉ kiểm tra status OK | Kiểm tra selected capability và kết quả nghiệp vụ |

## 16. Bài tập thực hành

**Tình huống:** Catalog server v1 đã được triển khai ở một số môi trường. Client v2 được sinh từ schema có category filter, page_size và method GetRecommendations. Trong một giai đoạn, load balancer có thể đưa client tới server v1 hoặc v2.

Hãy thực hiện:

1. Đóng băng server v1 artifact cùng proto, generated code và runtime của release cũ.
2. Build client v2 từ schema mới và giữ runtime riêng tương thích với generated code client.
3. Chạy old server trong process riêng; gọi Search bằng client v2 qua ManagedChannel thật.
4. Gửi category/page_size và xác minh server v1 bỏ qua chúng; client không tuyên bố feature đã được áp dụng.
5. Xác minh response thiếu next_page_token được xử lý theo presence/default contract.
6. Gọi GetRecommendations tới server v1 và xác minh UNIMPLEMENTED; kiểm tra fallback nếu có semantics tương đương.
7. Kiểm thử enum/oneof value mới không được gửi khi capability chưa xác nhận.
8. Kiểm thử capability discovery qua endpoint ổn định hoặc cấu hình route; mô phỏng replica hỗn hợp.
9. Thêm old-server/new-client test vào CI release gate.
10. Chỉ bật feature v2 khi toàn bộ route đích đã hỗ trợ và metrics xác nhận selected capability.

**Tiêu chí hoàn thành:** server fixture thực sự là artifact cũ; client generated mới gọi qua transport thật; unknown request/response fields được hiểu đúng; feature mới không bị coi là thành công khi server bỏ qua; method mới và enum/oneof mới có xử lý rõ; rollout không gửi feature mới tới replica chưa hỗ trợ.

## 17. Ghi nhớ

Kiểm thử server cũ với client mới phải dùng server artifact thực sự cũ và generated client mới. Với field additive, server cũ có thể parse request rồi bỏ qua field chưa biết; response cũ không có field mới nên client mới nhận default hoặc absent. Điều này có thể tạo một RPC status OK nhưng không thực hiện feature mà client yêu cầu. Enum/oneof mới và RPC method mới còn có rủi ro riêng; method chưa đăng ký thường trả UNIMPLEMENTED. Hãy xác minh capability trước khi bật feature, giữ fallback có điều kiện, kiểm thử qua transport thật và dùng old-server fixture làm release gate. Nếu semantics mới bắt buộc server mới, deploy/route server hỗ trợ trước khi client phụ thuộc vào nó.
