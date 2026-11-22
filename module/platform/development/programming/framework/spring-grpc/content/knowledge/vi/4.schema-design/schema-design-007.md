# Thêm field mới mà không phá client cũ trong Spring gRPC

Một dịch vụ gRPC thường có nhiều phiên bản client cùng hoạt động: ứng dụng web được cập nhật nhanh, ứng dụng di động có thể nằm trên thiết bị nhiều tháng, còn đối tác tích hợp có lịch phát hành riêng. Vì vậy, thêm một field vào file Protocol Buffers không chỉ là sửa schema rồi sinh lại Java. Cần bảo đảm server mới vẫn hiểu request cũ và client cũ vẫn xử lý được response mới.

Nguyên tắc cốt lõi: **cấp field number mới, giữ nguyên ý nghĩa các field đã phát hành và xác định hành vi khi field mới vắng mặt**. Tương thích ở tầng wire là điều kiện cần; validation nghiệp vụ và thứ tự triển khai cũng phải tương thích.

Bài này tập trung vào việc mở rộng một hợp đồng Spring gRPC đang được sử dụng. Ví dụ xuyên suốt là RPC **GetProduct**: ta thêm tùy chọn ngôn ngữ vào request và mô tả ngắn vào response, rồi xem client/server cũ và mới diễn giải dữ liệu ra sao.

## 1. Bài toán: nhiều phiên bản cùng gọi một RPC

Phiên bản đầu của dịch vụ danh mục có hợp đồng:

```proto
syntax = "proto3";

package shop.catalog.v1;

option java_package = "com.myshop.grpc.catalog.v1";
option java_multiple_files = true;

service CatalogService {
  rpc GetProduct(GetProductRequest) returns (GetProductResponse);
}

message GetProductRequest {
  string product_id = 1;
}

message Product {
  string product_id = 1;
  string display_name = 2;
}

message GetProductResponse {
  Product product = 1;
}
```

Sau khi client v1 đã phát hành, nhóm muốn hỗ trợ ngôn ngữ hiển thị và mô tả ngắn. Hợp đồng mở rộng có thể thêm:

```proto
message GetProductRequest {
  string product_id = 1;
  optional string locale = 2;
}

message Product {
  string product_id = 1;
  string display_name = 2;
  string short_description = 3;
}
```

Trong ví dụ này, **locale** là tùy chọn; nếu client cũ không gửi, server dùng ngôn ngữ mặc định đã công bố. **short_description** là field bổ sung trong response; client cũ không cần truy cập field này để tiếp tục hiển thị ID và tên sản phẩm.

Đây thường là mở rộng tương thích ở tầng protobuf binary. Nhưng nếu server mới yêu cầu locale khác rỗng ngay khi triển khai, client v1 sẽ bị từ chối. Nếu client mới phụ thuộc vào short_description nhưng request lại được chuyển tới server cũ, client có thể nhận kết quả thiếu dữ liệu. **Thêm field an toàn đòi hỏi cả cách xử lý khi field vắng mặt và cách triển khai các phiên bản.**

## 2. Tương thích có nhiều hướng

Khi nói một thay đổi schema tương thích, hãy xác định cặp client/server nào cần tiếp tục hoạt động:

| Tình huống | Hành vi protobuf binary thường gặp | Điều phải bảo đảm |
| --- | --- | --- |
| **Client cũ → server mới** | Client không gửi field mới; server đọc giá trị mặc định hoặc trạng thái absent nếu field có presence | Server mới có fallback an toàn cho request cũ |
| **Client mới → server cũ** | Server cũ không biết field mới và thường bỏ qua field lạ | Client mới không được giả định server cũ đã áp dụng field đó |
| **Server mới → client cũ** | Client cũ đọc các field đã biết và bỏ qua field response chưa biết | Client cũ vẫn hoạt động khi field bổ sung không được sử dụng |
| **Server cũ → client mới** | Client mới thấy field mới vắng mặt | Client mới có fallback hoặc tránh gọi tính năng chưa được server hỗ trợ |

Trong bài này:

- **Backward compatibility:** server mới tiếp tục chấp nhận request từ client cũ.
- **Forward compatibility:** client cũ tiếp tục xử lý response từ server mới.

Hai đặc tính này không tự động xuất hiện chỉ vì file proto biên dịch thành công. Validation, logic nghiệp vụ, ProtoJSON và rollout cũng ảnh hưởng đến kết quả.

### Unknown field không có nghĩa là đã được xử lý

Client mới có thể gửi:

```text
GetProductRequest {
  product_id: "P-100"
  locale: "vi-VN"
}
```

Nếu request tới server cũ chưa có field locale, parser binary protobuf thường bỏ qua field number 2 vì schema server không biết nó. RPC vẫn có thể trả **OK**, nhưng server **không hề sử dụng** vi-VN. Client không thể suy ra từ status OK rằng ngôn ngữ đã được áp dụng.

Đặc biệt, nếu field mới ảnh hưởng giá, quyền truy cập, thuế hoặc trạng thái giao dịch, việc bị server cũ bỏ qua có thể làm kết quả sai. Hãy triển khai server hỗ trợ trước khi client phụ thuộc vào field đó.

## 3. Field number là định danh trên wire

Protocol Buffers mã hóa mỗi field bằng một key gồm **field number** và **wire type**. Tên product_id giúp người đọc schema và mã sinh dễ hiểu, nhưng không được truyền như tên thuộc tính trong binary protobuf. Khi giải mã, runtime dùng field number để xác định trường.

Khi thêm field:

1. Cấp một field number mới, chưa từng dùng trong message đó.
2. Giữ nguyên field number và kiểu của mọi field đã phát hành.
3. Không đổi số field cũ để sắp xếp lại schema.
4. Không dùng lại số hoặc tên đã xóa; đánh dấu bằng reserved.
5. Không dựa vào việc hai kiểu có cùng wire type để tự kết luận chúng tương thích về ngữ nghĩa.

Ví dụ:

```proto
message Product {
  string product_id = 1;
  string display_name = 2;
  string short_description = 3; // Field mới, số chưa từng dùng.
}
```

Client v1 chỉ biết field 1 và 2. Khi nhận field 3 trong binary response, runtime cũ có thể bỏ qua field chưa biết; ứng dụng cũ vẫn đọc được ID và tên sản phẩm. Client mới khi nói chuyện với server cũ sẽ thấy field 3 vắng mặt và phải xử lý giá trị mặc định.

Field number từ 1 đến 15 có encoding key nhỏ hơn, thường tiết kiệm byte hơn cho field xuất hiện thường xuyên. Có thể ưu tiên dải này khi thiết kế schema mới, nhưng **không bao giờ đổi số field đã phát hành chỉ để tối ưu kích thước**.

### Xóa field thì phải giữ chỗ

Nếu field số 3 từng là short_description rồi bị xóa, bảo vệ cả số và tên:

```proto
message Product {
  reserved 3;
  reserved "short_description";

  string product_id = 1;
  string display_name = 2;
}
```

Không xóa khai báo cũ rồi gán số 3 cho manufacturer_id. Payload được lưu từ phiên bản trước có thể chứa tag 3; nếu tái sử dụng, dữ liệu cũ có thể bị diễn giải thành ý nghĩa mới.

## 4. Chọn presence và fallback cho field mới

Với locale, có thể dùng scalar thường nếu chuỗi rỗng và vắng mặt có cùng ý nghĩa:

```proto
message GetProductRequest {
  string product_id = 1;
  string locale = 2;
}
```

Trong proto3, scalar string thông thường không có presence riêng; khi không được gửi, getter trả chuỗi rỗng. Server định nghĩa chuỗi rỗng là dùng locale mặc định.

Nếu cần phân biệt “không gửi” với “chủ ý gửi chuỗi rỗng”, dùng optional:

```proto
message GetProductRequest {
  string product_id = 1;
  optional string locale = 2;
}
```

Java code sinh ra có thể kiểm tra:

```java
String locale;
if (!request.hasLocale()) {
    // Client cũ hoặc client mới không yêu cầu locale cụ thể.
    locale = resolveDefaultLocale(request.getProductId());
} else {
    // Nếu đã gửi, kiểm tra cả chuỗi rỗng và định dạng.
    locale = normalizeAndValidateLocale(request.getLocale());
}
```

Nếu client gửi chuỗi rỗng, hasLocale() là true; server có thể từ chối bằng INVALID_ARGUMENT hoặc định nghĩa ý nghĩa riêng. Quy tắc đó phải được ghi trong hợp đồng.

Không cần thêm optional cho mọi field chỉ vì muốn “bắt buộc” hơn. Ví dụ product_id là scalar thường nhưng server vẫn có thể từ chối chuỗi rỗng:

```java
if (request.getProductId().isBlank()) {
    throw Status.INVALID_ARGUMENT
            .withDescription("product_id must not be blank")
            .asRuntimeException();
}
```

Điều này từ chối cả request cũ không có product_id lẫn request gửi chuỗi rỗng, nếu hai trường hợp có cùng ý nghĩa nghiệp vụ.

### Field mới trong response

Thêm short_description = 3 vào Product không buộc client cũ phải thay đổi:

```proto
message Product {
  string product_id = 1;
  string display_name = 2;
  string short_description = 3;
}
```

Client v1 không có getShortDescription(), nhưng vẫn đọc ID và tên. Client mới gọi server cũ sẽ thấy field 3 vắng mặt; getter trả chuỗi rỗng. Nếu mô tả chỉ là cải thiện giao diện, client có thể ẩn phần mô tả. Nếu tính năng không thể hoạt động khi field vắng mặt, client cần biết server có hỗ trợ tính năng đó trước khi phụ thuộc vào nó.

## 5. Những thay đổi dễ bị coi nhầm là tương thích

| Thay đổi | Đánh giá | Lý do |
| --- | --- | --- |
| Thêm field mới với số mới và fallback an toàn | Thường tương thích với binary protobuf | Client cũ không gửi/không đọc field mới |
| Đổi tên field, giữ số và kiểu | Có thể tương thích binary nhưng ảnh hưởng mã nguồn và JSON | Accessor Java, khóa JSON mặc định và descriptor đổi |
| Đổi field number đã phát hành | Không tương thích | Dữ liệu cũ có thể bị giải mã thành field khác |
| Đổi kiểu field hiện có | Rủi ro cao, thường không tương thích về ngữ nghĩa | Wire type có thể đổi; ngay cả khi giống nhau, cách diễn giải có thể khác |
| Tái sử dụng số hoặc tên field đã xóa | Không an toàn | Client lưu dữ liệu cũ có thể diễn giải sai |
| Thêm nhánh vào oneof đã phát hành | Cần đánh giá riêng | Client cũ có thể thấy oneof như chưa chọn nhánh nào khi server gửi nhánh mới |
| Thêm enum value | Cần kiểm tra consumer cũ | Client cũ có thể nhận giá trị enum chưa biết |

**Không đổi int32 thành int64 chỉ vì cả hai thường dùng varint.** Miền giá trị và hành vi ứng dụng khác nhau. Không đổi string thành bytes chỉ vì cùng wire type length-delimited. Khi kiểu hoặc ngữ nghĩa thay đổi, thêm field mới hoặc tạo API phiên bản mới thường an toàn hơn.

### Enum value mới

Giả sử thêm PRODUCT_STATUS_ARCHIVED = 4 vào enum response. Client cũ có thể nhận số 4 nhưng không có hằng enum tương ứng. Trong Java proto3, getter enum có thể trả UNRECOGNIZED, còn getter số nguyên giữ giá trị:

```java
ProductStatus status = response.getStatus();
int rawValue = response.getStatusValue();

if (status == ProductStatus.UNRECOGNIZED) {
    // Không tự suy diễn trạng thái mới thành ACTIVE hoặc DELETED.
    handleUnknownStatus(rawValue);
}
```

Không thêm enum value mới nếu client cũ sẽ đưa ra quyết định nguy hiểm khi gặp trạng thái không nhận diện. Hãy thiết kế nhánh mặc định an toàn và kiểm thử với mã sinh cũ.

### Mở rộng oneof

Giả sử schema đã phát hành:

```proto
message PaymentMethod {
  oneof method {
    CardPayment card = 1;
    BankTransfer bank_transfer = 2;
  }
}
```

Server mới thêm nhánh wallet = 3. Khi server gửi nhánh này, client cũ chỉ biết card và bank_transfer; nó có thể nhìn thấy getMethodCase() như chưa chọn nhánh nào. Nếu logic cũ coi NOT_SET là thanh toán thẻ hoặc xử lý mặc định nguy hiểm, hành vi sẽ sai.

Trước khi mở rộng oneof, hãy xác định client cũ có thể bỏ qua lựa chọn mới an toàn không, nhánh chưa biết có bị nhầm với trạng thái hợp lệ không và có cần RPC/response phiên bản mới hay không. oneof bảo đảm tối đa một nhánh theo schema đang dùng; nó không bảo đảm mọi phiên bản client đều biết các nhánh tương lai.

## 6. Binary protobuf và ProtoJSON có quy tắc khác nhau

Nguyên tắc unknown field ở trên áp dụng cho **protobuf binary**. Nếu API còn được truy cập qua JSON gateway, ProtoJSON hoặc client tự viết, cần kiểm tra riêng:

- Field mới trong JSON thường dùng tên lowerCamelCase, ví dụ shortDescription.
- Parser JSON của client cũ có thể từ chối khóa không biết, tùy thư viện và cấu hình. Không mặc định mọi JSON parser đều bỏ qua unknown key.
- Đổi tên field hoặc json_name có thể phá client JSON dù field number binary vẫn giữ nguyên.
- Với kiểu số 64-bit như int64, ProtoJSON ánh xạ thành chuỗi thập phân theo quy tắc chuẩn; không tự đổi thành JSON number rồi giả định mọi client hiểu giống nhau.
- Nếu dùng HTTP transcoding, kiểm tra route, body mapping và hành vi gateway khi field mới vắng mặt.

Vì vậy, khi nói “thêm field tương thích”, cần chỉ rõ loại client cần hỗ trợ: stub gRPC binary, dynamic protobuf, JSON gateway hay ứng dụng đọc schema qua reflection.

## 7. Triển khai server trước, client sau

Giả sử nhiều instance server nằm sau load balancer. Nếu client mới bắt đầu gửi locale trong lúc một số instance vẫn chạy server cũ, request có thể được xử lý khác nhau tùy instance. Một request tới server mới được bản địa hóa, request kế tiếp tới server cũ lại dùng ngôn ngữ mặc định.

Trình tự triển khai khuyến nghị:

1. **Thiết kế field và fallback.** Cấp số mới, xác định hành vi khi absent và giữ nguyên ngữ nghĩa field cũ.
2. **Triển khai server tương thích.** Tất cả instance nhận biết field mới; request thiếu field vẫn xử lý theo quy tắc cũ.
3. **Kiểm chứng fleet.** Xác nhận không còn instance server cũ nhận traffic của tính năng mới; theo dõi lỗi và tỷ lệ fallback.
4. **Triển khai client mới.** Client bắt đầu gửi field mới; chỉ bật hành vi phụ thuộc field khi biết server hỗ trợ.
5. **Đánh giá vòng đời API.** Nếu sau này phải bắt buộc field, công bố v2 hoặc endpoint mới khi v1 không thể giữ hành vi tương thích.

Server-first chỉ giải quyết rollout nếu mọi server instance đã được nâng cấp trước khi client phụ thuộc vào field. Trong môi trường nhiều vùng hoặc nhiều đối tác, có thể cần capability negotiation, routing theo phiên bản hoặc feature flag.

### Đừng dùng default giả để che dữ liệu thiếu

Nếu locale vắng mặt, default en-US có thể hợp lý nếu đó là quy ước đã có. Nhưng nếu field mới là tax_region và ảnh hưởng số tiền thuế, gán mặc định tùy tiện có thể làm sai hóa đơn. Khi không có cách suy ra an toàn, hãy giữ hành vi v1 bằng dữ liệu cũ, yêu cầu client chuyển sang v2 hoặc từ chối tính năng mới trên endpoint cũ. Tương thích không có nghĩa là chấp nhận một kết quả sai.

## 8. Ví dụ Java trong server Spring gRPC

Sau khi sinh mã Java từ schema mở rộng, GetProductRequest có hasLocale() và getLocale(). Handler có thể giữ hành vi cũ khi client không gửi field:

```java
package com.myshop.server.catalog;

import com.myshop.grpc.catalog.v1.CatalogServiceGrpc;
import com.myshop.grpc.catalog.v1.GetProductRequest;
import com.myshop.grpc.catalog.v1.GetProductResponse;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.grpc.server.service.GrpcService;

@GrpcService
public class CatalogGrpcEndpoint
        extends CatalogServiceGrpc.CatalogServiceImplBase {

    private final CatalogApplicationService catalog;

    public CatalogGrpcEndpoint(CatalogApplicationService catalog) {
        this.catalog = catalog;
    }

    @Override
    public void getProduct(
            GetProductRequest request,
            StreamObserver<GetProductResponse> observer) {
        if (request.getProductId().isBlank()) {
            observer.onError(Status.INVALID_ARGUMENT
                    .withDescription("product_id is required")
                    .asRuntimeException());
            return;
        }

        final String locale;
        if (!request.hasLocale()) {
            locale = catalog.defaultLocaleFor(request.getProductId());
        } else if (request.getLocale().isBlank()) {
            observer.onError(Status.INVALID_ARGUMENT
                    .withDescription("locale must not be blank when supplied")
                    .asRuntimeException());
            return;
        } else {
            locale = catalog.validateLocale(request.getLocale());
        }

        GetProductResponse response =
                catalog.getProduct(request.getProductId(), locale);
        observer.onNext(response);
        observer.onCompleted();
    }
}
```

CatalogApplicationService đại diện cho logic ứng dụng do dự án cung cấp. Ví dụ giả định nó trả lỗi nghiệp vụ phù hợp khi sản phẩm không tồn tại hoặc locale không được hỗ trợ; cách ánh xạ ngoại lệ sang gRPC status cần được triển khai nhất quán. Annotation @GrpcService và cấu hình server phải khớp phiên bản Spring gRPC đang dùng.

Điểm tương thích nằm ở nhánh !request.hasLocale(): client cũ không gửi field vẫn nhận hành vi mặc định. Không nên dùng getLocale().isBlank() làm kiểm tra duy nhất nếu presence mang ý nghĩa khác nhau.

## 9. Kiểm thử các tổ hợp client/server

Một test chỉ sinh mã từ schema mới rồi gọi server mới không chứng minh được tương thích. Cần kiểm tra các tổ hợp:

| Client | Server | Trường hợp | Kỳ vọng |
| --- | --- | --- | --- |
| v1 | v1 | Hành vi ban đầu | Giữ nguyên kết quả |
| v1 | mới | Request không có field mới | Server mới áp dụng fallback, không từ chối chỉ vì thiếu field |
| mới | mới | Field mới hợp lệ | Server áp dụng đúng field |
| mới | mới | Field mới sai định dạng | Server trả status validation phù hợp |
| mới | cũ | Request có field mới | Xác nhận server cũ có thể bỏ qua; client không giả định field đã được áp dụng |
| cũ | mới | Response có field mới | Client cũ đọc field cũ và tiếp tục hoạt động |
| cũ | mới | Enum/oneof branch mới | Unknown value không gây hành vi nguy hiểm |
| JSON cũ | gateway mới | Response có khóa JSON mới | Kiểm tra parser cũ và cấu hình ignore unknown field |

### Kiểm tra wire bằng fixture v1

Có thể lưu một request binary được tạo từ generated class của schema v1, sau đó parse bằng class v2:

```java
// oldRequest được tạo bằng generated class của schema v1.
byte[] bytesV1 = oldRequest.toByteArray();

// GetProductRequest này được sinh từ schema v2.
GetProductRequest parsedByV2 =
        GetProductRequest.parseFrom(bytesV1);

assertEquals("P-100", parsedByV2.getProductId());
assertFalse(parsedByV2.hasLocale());
```

Đây là kiểm tra wire-level tại message boundary. Test end-to-end còn cần gọi server mới bằng client v1 thực tế để xác nhận handler, validation, authentication và gRPC status cùng hoạt động như cam kết. Chiều ngược lại cũng cần kiểm tra client v2 gọi server cũ để xác nhận client không phụ thuộc vào field mà server cũ chưa hỗ trợ.

Các test nên bao gồm:

- Field mới absent, field mới có giá trị hợp lệ và field mới có giá trị mặc định được gửi rõ ràng.
- Client cũ parse response mới và tiếp tục sử dụng các field cũ.
- Client mới gặp server cũ; field bị bỏ qua không làm ứng dụng đưa ra quyết định sai.
- Nhiều instance server khác phiên bản cùng nhận traffic trong giai đoạn rollout.
- ProtoJSON/HTTP gateway nếu API có hỗ trợ JSON.
- Enum và oneof khi có giá trị/nhánh mới.

## 10. Khi nào nên tạo v2?

Thêm field vào v1 thường phù hợp khi dữ liệu mới là tùy chọn hoặc có fallback an toàn, client cũ có thể bỏ qua response field mới và server cũ bỏ qua request field mới không gây sai dữ liệu.

Nên cân nhắc RPC hoặc package v2 khi:

- Field mới phải có mặt để thao tác đúng, nhưng client cũ không thể gửi và server không có cách suy ra an toàn.
- Một field hiện có đổi ý nghĩa, kiểu hoặc validation theo cách phá vỡ hành vi cũ.
- Client cũ không thể xử lý enum/oneof branch mới và không có fallback an toàn.
- Response mới có cấu trúc khác căn bản, không thể mở rộng mà không làm consumer hiểu sai.

Không cần tạo v2 cho mọi field mới. Versioning quá thường xuyên làm tăng số endpoint và chi phí vận hành. Hãy mở rộng v1 khi giữ được ngữ nghĩa; tạo phiên bản mới khi hợp đồng cũ không thể đáp ứng yêu cầu mà vẫn đúng.

## 11. Checklist review trước khi merge

- [ ] Field mới dùng số chưa từng được sử dụng trong message.
- [ ] Không đổi field number, kiểu hoặc ý nghĩa của field cũ.
- [ ] Nếu xóa field, đã reserved cả số và tên.
- [ ] Đã quyết định scalar thường hay optional dựa trên nhu cầu presence thực tế.
- [ ] Server mới có hành vi rõ ràng khi field vắng mặt.
- [ ] Không biến field mới thành bắt buộc trên RPC cũ nếu client cũ chưa thể gửi.
- [ ] Client mới có fallback khi server cũ trả response thiếu field.
- [ ] Enum và oneof mới đã được đánh giá với consumer cũ.
- [ ] ProtoJSON/HTTP gateway đã được kiểm tra riêng với binary protobuf.
- [ ] Rollout server-first có cách xác nhận mọi instance đã hỗ trợ trước khi bật client.
- [ ] Có test dùng fixture/stub cũ và mới, gồm absent, default và invalid.
- [ ] Metrics không ghi dữ liệu nhạy cảm nhưng đủ để theo dõi tỷ lệ client gửi field mới và lỗi tương thích.

**Tự kiểm tra**

**Câu 1.** Bạn thêm optional string locale = 2 vào request. Client v1 không gửi field này. Server v2 cần xử lý ra sao?

*Đáp án:* Kiểm tra hasLocale(). Khi absent, dùng fallback đã công bố hoặc hành vi cũ. Chỉ validate định dạng locale khi client thực sự gửi.

**Câu 2.** Client mới gửi locale đến server cũ và nhận OK. Có thể kết luận response được bản địa hóa không?

*Đáp án:* Không. Server cũ có thể bỏ qua field chưa biết. Cần triển khai server hỗ trợ trước và không bật client phụ thuộc tính năng khi còn server cũ trong fleet.

**Câu 3.** Bạn đã xóa field số 3. Có thể dùng lại số 3 cho một field mới không?

*Đáp án:* Không. Đánh dấu số 3 và tên cũ bằng reserved để tránh payload cũ bị diễn giải sai.

**Câu 4.** Một enum response được bổ sung giá trị mới. Client Java cũ nên làm gì khi nhận giá trị không nhận diện?

*Đáp án:* Xử lý nhánh UNRECOGNIZED hoặc giá trị số chưa biết theo chính sách an toàn; không tự gán sang trạng thái cũ có ý nghĩa khác.

**Câu 5.** Khi nào nên tạo shop.catalog.v2?

*Đáp án:* Khi không thể giữ hành vi đúng cho client v1 bằng field tùy chọn/fallback, hoặc thay đổi cấu trúc/ngữ nghĩa làm client cũ hiểu sai. Nếu chỉ bổ sung dữ liệu tùy chọn mà client cũ có thể bỏ qua an toàn, có thể tiếp tục mở rộng v1.

Thêm field an toàn không chỉ là giữ cho protoc biên dịch thành công. Cần giữ nguyên cách client cũ hiểu dữ liệu, xác định hành vi khi field vắng mặt và triển khai server hỗ trợ trước khi client phụ thuộc vào tính năng mới.
