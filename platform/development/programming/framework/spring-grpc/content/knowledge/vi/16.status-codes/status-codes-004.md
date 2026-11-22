# INVALID_ARGUMENT

Trong gRPC, **`INVALID_ARGUMENT` là status code số `3`**, dùng khi request chứa tham số không hợp lệ theo hợp đồng của method. Lỗi này xuất phát từ dữ liệu hoặc cách client gọi: định dạng sai, giá trị ngoài miền cho phép, field không được cung cấp theo quy ước hoặc tổ hợp field mâu thuẫn. Nếu client gửi lại nguyên request mà không sửa dữ liệu, kết quả thường vẫn thất bại.

Trong **SPRING_GRPC**, server nhận message Protobuf đã được giải mã rồi mới kiểm tra quy tắc đầu vào ở handler hoặc lớp ứng dụng. Protobuf định nghĩa kiểu dữ liệu và cấu trúc wire, nhưng không tự diễn đạt mọi quy tắc nghiệp vụ. Vì vậy, cần xác định validation nằm ở đâu, lỗi nào ánh xạ thành `INVALID_ARGUMENT`, cách trả thông tin field an toàn và cách client sửa request.

## 1. Ý nghĩa của INVALID_ARGUMENT

`INVALID_ARGUMENT` có giá trị số **3**. Status này phù hợp khi một hoặc nhiều argument do client cung cấp không hợp lệ **bất kể trạng thái hiện tại của hệ thống**.

Ví dụ:

- `quantity` phải lớn hơn 0 nhưng client gửi 0 hoặc số âm.
- `email` không đúng định dạng mà contract chấp nhận.
- Một chuỗi định danh rỗng hoặc sai cú pháp.
- Khoảng thời gian có `start_time` sau `end_time`.
- Một tổ hợp field mâu thuẫn, chẳng hạn chọn loại thanh toán là `CARD` nhưng không cung cấp token thẻ theo contract.
- Giá trị enum không được API hỗ trợ hoặc nằm ngoài tập giá trị mà method cho phép.

| Góc nhìn | Ý nghĩa |
| --- | --- |
| Client | Request cần được sửa trước khi gửi lại |
| Server | Không nên thực hiện nghiệp vụ với input vi phạm contract |
| gRPC runtime | Kết thúc RPC với status `INVALID_ARGUMENT` |
| Nghiệp vụ | Request không vượt qua kiểm tra đầu vào; chưa khẳng định hệ thống có hay không có tài nguyên |

`INVALID_ARGUMENT` không phải lỗi kết nối và cũng không phải lỗi xác thực danh tính. Nó cho biết dữ liệu đầu vào của method không hợp lệ.

## 2. Protobuf định nghĩa cấu trúc, ứng dụng định nghĩa nhiều quy tắc validation

Ví dụ contract kiểm tra tồn kho:

```protobuf
syntax = "proto3";

package commerce.inventory.v1;

message CheckStockRequest {
  string sku = 1;
  int32 quantity = 2;
}

message CheckStockReply {
  bool available = 1;
  int32 remaining = 2;
}

service InventoryService {
  rpc CheckStock(CheckStockRequest) returns (CheckStockReply);
}
```

Schema cho biết `sku` là chuỗi và `quantity` là số nguyên 32-bit. Nhưng schema này chưa tự diễn đạt rằng:

- `sku` không được rỗng.
- `sku` phải theo quy tắc định danh của hệ thống.
- `quantity` phải lớn hơn 0.
- Một request chỉ được yêu cầu tối đa một số lượng nhất định.

Những điều kiện đó thuộc contract ở cấp ứng dụng và cần được kiểm tra rõ ràng.

### 2.1. Chú ý giá trị mặc định của proto3

Với scalar field thông thường trong proto3, nếu client không gửi field thì server có thể nhận giá trị mặc định, ví dụ chuỗi rỗng hoặc số 0. Vì thế, server không phải lúc nào cũng phân biệt được “client không gửi” và “client gửi giá trị mặc định”.

Nếu cần phân biệt hai trường hợp, hãy cân nhắc `optional`, `oneof` hoặc một kiểu wrapper phù hợp với schema. Ví dụ:

```protobuf
message UpdateProfileRequest {
  string user_id = 1;
  optional string display_name = 2;
}
```

Với field có presence, server có thể kiểm tra `hasDisplayName()` để phân biệt không cung cấp field với cung cấp chuỗi rỗng. Dù dùng presence hay không, vẫn cần xác định semantics rõ trong contract.

### 2.2. Không nhầm parse error với validation error

Protobuf parser kiểm tra wire format và khả năng giải mã message. Nếu byte stream sai định dạng, lỗi có thể xảy ra trước khi handler nhận được request. `INVALID_ARGUMENT` thường được dùng cho message hợp lệ về cấu trúc nhưng chứa giá trị hoặc tổ hợp field không hợp lệ theo quy tắc method.

Nói cách khác:

- **Parse/transport failure:** dữ liệu không thể được giải mã hoặc luồng truyền có lỗi.
- **Validation failure:** server đã nhận được request message, nhưng giá trị trong message vi phạm quy tắc đầu vào.

## 3. Phân biệt INVALID_ARGUMENT với các status dễ nhầm

Lựa chọn status đúng giúp client biết phải sửa request, kiểm tra trạng thái tài nguyên hay xác thực quyền.

| Status | Khi nào phù hợp | Ví dụ |
| --- | --- | --- |
| `INVALID_ARGUMENT` | Tham số sai bất kể trạng thái hệ thống | `quantity = 0` trong method yêu cầu số lượng dương |
| `FAILED_PRECONDITION` | Hệ thống chưa ở trạng thái cần thiết để thực hiện thao tác | Tài khoản đang bị khóa nên không thể rút tiền |
| `OUT_OF_RANGE` | Giá trị hợp lệ nói chung nhưng vượt phạm vi hợp lệ cho thao tác hiện tại | Đọc tiếp sau offset cuối cùng của một tập dữ liệu hữu hạn |
| `NOT_FOUND` | Tài nguyên được yêu cầu không tồn tại | Không có sản phẩm với SKU hợp lệ đã gửi |
| `PERMISSION_DENIED` | Người gọi không có quyền thực hiện thao tác | User không được xem đơn hàng của người khác |
| `UNAUTHENTICATED` | Không xác định được danh tính người gọi | Token thiếu hoặc hết hạn |
| `ALREADY_EXISTS` | Tạo tài nguyên trùng với tài nguyên đã tồn tại | Tạo user với email đã được đăng ký |

### 3.1. INVALID_ARGUMENT và FAILED_PRECONDITION

Đây là khác biệt quan trọng:

- `INVALID_ARGUMENT`: request sai, dù hệ thống đang ở trạng thái nào.
- `FAILED_PRECONDITION`: request có thể hợp lệ, nhưng trạng thái hiện tại của hệ thống không cho phép thực hiện.

Ví dụ, `quantity = -2` luôn sai đối với thao tác đặt hàng, nên dùng `INVALID_ARGUMENT`. Còn `quantity = 2` hợp lệ nhưng kho đang đóng để kiểm kê, có thể dùng `FAILED_PRECONDITION` nếu contract quy định đây là trạng thái ngăn thao tác.

### 3.2. INVALID_ARGUMENT và OUT_OF_RANGE

`OUT_OF_RANGE` phù hợp khi giá trị nằm ngoài phạm vi cho phép của thao tác, nhất là các API có khái niệm phạm vi hoặc cursor. Nếu field sai về định dạng hay vi phạm quy tắc đầu vào chung, `INVALID_ARGUMENT` thường rõ hơn. Cần chọn theo semantics của method, không chỉ dựa trên tên exception Java.

### 3.3. INVALID_ARGUMENT và NOT_FOUND

Một SKU đúng định dạng nhưng không tồn tại có thể là `NOT_FOUND`. Một SKU chứa ký tự hoặc cấu trúc bị cấm là `INVALID_ARGUMENT`. Trường hợp “không tìm thấy” có phải lỗi hay kết quả bình thường còn phụ thuộc hợp đồng method.

## 4. Validation nên diễn ra ở đâu trong Spring gRPC?

Một luồng xử lý thường có các ranh giới:

```text
gRPC runtime
    |
    v
Protobuf request đã parse
    |
    v
gRPC handler / adapter
    |  Kiểm tra cấu trúc và quy tắc API
    v
Spring application service
    |  Kiểm tra invariant và quy tắc nghiệp vụ
    v
Repository / database
```

Có thể chia validation thành ba nhóm:

| Nhóm | Ví dụ | Nơi phù hợp |
| --- | --- | --- |
| Quy tắc hình thức của API | Field bắt buộc theo contract, độ dài, định dạng, quantity dương | Handler/adapter hoặc validator chuyên cho request |
| Quy tắc miền nghiệp vụ | Tổng số lượng trong giới hạn đặt hàng, các field có quan hệ hợp lệ | Spring application/domain service |
| Ràng buộc dữ liệu bền vững | Unique constraint, foreign key, trạng thái bản ghi khi cập nhật đồng thời | Database và application service; chuyển lỗi sang status phù hợp |

Validation ở client giúp phản hồi sớm và cải thiện trải nghiệm, nhưng **server vẫn phải xác thực lại**. Client có thể cũ, bị lỗi hoặc cố tình gửi dữ liệu không hợp lệ.

Không nên đặt mọi quy tắc vào interceptor. Interceptor phù hợp cho logic dùng chung như authentication, metadata, tracing hoặc policy xuyên method. Validation phụ thuộc schema và ngữ nghĩa của từng method thường nên nằm ở adapter/validator hoặc lớp nghiệp vụ tương ứng.

## 5. Ví dụ ánh xạ validation thành INVALID_ARGUMENT

Một handler có thể kiểm tra request trước khi gọi business service:

```java
@Override
public void checkStock(
        CheckStockRequest request,
        StreamObserver<CheckStockReply> observer) {

    if (request.getSku().isBlank()) {
        observer.onError(Status.INVALID_ARGUMENT
            .withDescription("sku không được để trống")
            .asRuntimeException());
        return;
    }

    if (request.getQuantity() <= 0) {
        observer.onError(Status.INVALID_ARGUMENT
            .withDescription("quantity phải lớn hơn 0")
            .asRuntimeException());
        return;
    }

    int remaining = inventoryQuery.remaining(request.getSku());
    CheckStockReply reply = CheckStockReply.newBuilder()
        .setAvailable(remaining >= request.getQuantity())
        .setRemaining(remaining)
        .build();

    observer.onNext(reply);
    observer.onCompleted();
}
```

Ví dụ giả định `inventoryQuery` là Spring bean đã được inject. Khi request sai, handler gọi `onError(...)` rồi `return`; không tiếp tục gọi nghiệp vụ hoặc phát response. Khi request hợp lệ, kết quả `available = false` vẫn có thể trả với status `OK`.

Trong ứng dụng lớn, nên tránh lặp các đoạn kiểm tra ở nhiều handler. Có thể tạo validator theo request type hoặc application command để quy tắc nhất quán và dễ unit test.

### 5.1. Tách request Protobuf khỏi command nghiệp vụ

Một cách tổ chức là chuyển message Protobuf sang command nội bộ rồi kiểm tra command:

```java
public record CheckStockCommand(String sku, int quantity) {}

public CheckStockCommand toCommand(CheckStockRequest request) {
    return new CheckStockCommand(request.getSku(), request.getQuantity());
}
```

Sau đó application service có thể dùng Bean Validation hoặc validator miền nghiệp vụ. Ví dụ dưới đây minh họa ý tưởng, không phải annotation cần đặt trực tiếp lên generated Protobuf class:

```java
public record ReserveStockCommand(
    @NotBlank String sku,
    @Positive int quantity
) {}
```

Nếu dùng Jakarta Bean Validation, ứng dụng gọi validator hoặc tích hợp validation ở application boundary, rồi chuyển các constraint violations thành status `INVALID_ARGUMENT`. Không nên sửa file Java được sinh từ proto để thêm annotation, vì code generation có thể ghi đè và generated message có semantics riêng.

## 6. Trả chi tiết lỗi field cho client

Một description chung như “Request không hợp lệ” có thể chưa đủ để client biết field nào cần sửa. Với hệ thống cần phản hồi nhiều lỗi cùng lúc, có thể dùng **richer error model** của Google RPC, chẳng hạn `google.rpc.BadRequest` chứa danh sách `FieldViolation`.

Ví dụ về nội dung logic:

```text
grpc-status: INVALID_ARGUMENT
grpc-message: Request không hợp lệ

BadRequest:
  field_violations:
    - field: "sku"
      description: "không được để trống"
    - field: "quantity"
      description: "phải lớn hơn 0"
```

Đây là cách biểu diễn minh họa; để gửi error details trong Java cần dùng các thư viện/protobuf types tương ứng và đóng gói detail vào status theo API đang dùng.

Khi trả chi tiết validation:

- Dùng tên field theo contract, không dùng tên cột database hoặc tên class nội bộ.
- Không trả giá trị nhạy cảm mà client đã gửi.
- Có thể trả nhiều lỗi field trong một response để client sửa cùng lúc.
- Giữ message ổn định và có thể được máy đọc; không dựa vào việc client parse câu văn tự do.
- Nếu hệ thống có localization, cân nhắc mã lỗi ổn định và để client hiển thị nội dung theo ngôn ngữ.

Với lỗi đơn giản, `Status.INVALID_ARGUMENT.withDescription(...)` có thể đủ. Chỉ cần richer error details khi client thực sự cần field-level feedback hoặc machine-readable validation.

## 7. Client nên xử lý INVALID_ARGUMENT như thế nào?

Với blocking stub, client có thể bắt `StatusRuntimeException`:

```java
try {
    CheckStockReply reply = inventoryStub.checkStock(request);
    // Xử lý kết quả nghiệp vụ.
} catch (StatusRuntimeException ex) {
    if (ex.getStatus().getCode() == Status.Code.INVALID_ARGUMENT) {
        // Hiển thị hoặc ghi nhận lỗi đầu vào; không retry nguyên request.
    } else {
        // Xử lý các status khác theo policy.
    }
}
```

Client cần:

1. Xác định method và request nào bị từ chối.
2. Đọc status và error details nếu có.
3. Liên kết lỗi với field trong form hoặc dữ liệu nguồn.
4. Sửa input trước khi gửi lại.
5. Tránh tự động retry nguyên request không thay đổi.

Không nên hiển thị trực tiếp mọi `grpc-message` cho người dùng cuối. Message có thể được viết cho developer hoặc chứa thông tin không phù hợp với UI. Hãy dùng mã lỗi/field violation đã được quy định trong contract và ánh xạ sang thông báo phù hợp.

### 7.1. INVALID_ARGUMENT thường không nên retry

Khác `UNAVAILABLE`, `INVALID_ARGUMENT` thường không phải lỗi tạm thời. Retry cùng payload thường trả cùng lỗi và chỉ làm tăng tải. Retry chỉ có ý nghĩa sau khi dữ liệu được sửa hoặc khi client thay đổi request theo thông tin validation.

## 8. Những trường hợp không nên dùng INVALID_ARGUMENT

| Tình huống | Status hoặc cách biểu diễn phù hợp hơn |
| --- | --- |
| Token thiếu hoặc không hợp lệ | `UNAUTHENTICATED` |
| Danh tính hợp lệ nhưng không có quyền | `PERMISSION_DENIED` |
| SKU đúng định dạng nhưng không tồn tại | `NOT_FOUND` hoặc response theo contract |
| Tài khoản bị khóa nên không thể chuyển tiền | `FAILED_PRECONDITION` |
| Cursor hợp lệ về kiểu nhưng vượt cuối tập kết quả | Có thể là `OUT_OF_RANGE` |
| Xung đột cập nhật đồng thời | `ABORTED` |
| Database tạm thời không truy cập được | `UNAVAILABLE` nếu semantics phù hợp |
| Lỗi bất ngờ trong server | `INTERNAL` hoặc status khác theo nguyên nhân |

Đặc biệt, không dùng `INVALID_ARGUMENT` để che lỗi authorization. Việc client không được quyền xem tài nguyên là vấn đề danh tính/quyền, không phải dữ liệu request sai.

## 9. Kiểm thử INVALID_ARGUMENT

Một bộ test nên bao phủ cả ranh giới API và nghiệp vụ:

| Kịch bản | Điều cần xác minh |
| --- | --- |
| `sku` rỗng | Client nhận `INVALID_ARGUMENT`; business service không bị gọi |
| `quantity = 0` hoặc âm | Status đúng và description/field detail phù hợp |
| `sku` sai định dạng | Validator trả lỗi ổn định |
| Request hợp lệ nhưng không đủ hàng | Response `available = false`, status `OK` |
| SKU hợp lệ nhưng không tồn tại | Status/response theo contract, không nhầm với invalid syntax |
| Token thiếu | `UNAUTHENTICATED`, không phải `INVALID_ARGUMENT` |
| User không có quyền | `PERMISSION_DENIED` |
| Nhiều field sai | Client nhận đầy đủ field violations nếu contract hỗ trợ |
| Generated code được cập nhật | Validation vẫn chạy sau code generation, không phụ thuộc sửa generated source |

Unit test validator giúp kiểm tra từng quy tắc nhanh. Integration test qua gRPC client/server xác minh status và error details thực sự được truyền tới client. Với Spring, có thể kiểm tra handler cùng application service trong test context hoặc dùng test server phù hợp.

## 10. Quan sát lỗi validation

`INVALID_ARGUMENT` có thể phản ánh client bug, SDK cũ, contract không rõ hoặc traffic cố tình gửi dữ liệu sai. Nên theo dõi:

- Số lượng và tỷ lệ `INVALID_ARGUMENT` theo service/method.
- Field nào thường vi phạm, nếu có thể ghi nhận mà không lưu giá trị nhạy cảm.
- Client/SDK version hoặc application class gây ra lỗi.
- Thay đổi tỷ lệ lỗi sau khi phát hành contract hoặc UI mới.
- Tỷ lệ request validation failure so với tổng RPC.

Không đưa giá trị `sku`, email, token hoặc nội dung request vào metric label. Dùng tên field và loại violation đã chuẩn hóa; nếu cần điều tra một request cụ thể, dùng trace/correlation ID và log được kiểm soát.

Tỷ lệ `INVALID_ARGUMENT` tăng đột ngột có thể chỉ ra client đang dùng schema/SDK không tương thích hoặc tài liệu contract gây hiểu nhầm. Đừng tự động xem đây là lỗi server availability; phân loại đúng giúp nhóm phụ trách biết cần sửa client, contract hay validation.

## 11. Checklist thiết kế validation cho gRPC method

Trước khi công bố method, hãy xác định:

1. **Field nào bắt buộc về mặt nghiệp vụ?** Phân biệt với default value của proto3.
2. **Định dạng và miền giá trị hợp lệ là gì?** Nêu rõ độ dài, range, pattern và quan hệ giữa các field.
3. **Validation thuộc lớp nào?** API adapter, domain/application service hay database constraint.
4. **Lỗi nào thực sự là INVALID_ARGUMENT?** Tách khỏi not found, permission và failed precondition.
5. **Client cần chi tiết đến mức nào?** Một description hay field violations có cấu trúc?
6. **Có lộ dữ liệu nhạy cảm không?** Không trả lại token hoặc payload riêng tư.
7. **Client sửa lỗi thế nào?** Có field mapping và mã lỗi ổn định không?
8. **Retry có hợp lý không?** Không retry nguyên request không thay đổi.
9. **Có test phân biệt các status gần nghĩa không?** Đảm bảo lỗi không bị gom nhầm.

## 12. Ghi nhớ

`INVALID_ARGUMENT` là gRPC status code `3`, dùng khi argument của request không hợp lệ theo contract của method. Nó phù hợp cho định dạng sai, field thiếu theo quy ước, giá trị ngoài miền hoặc tổ hợp field mâu thuẫn. Nó khác `FAILED_PRECONDITION` (trạng thái hệ thống chưa cho phép thao tác), `OUT_OF_RANGE` (vượt phạm vi thao tác), `NOT_FOUND` (không có tài nguyên) và status xác thực/phân quyền.

Trong Spring gRPC, Protobuf định nghĩa cấu trúc message; handler/validator và application service thực hiện validation; gRPC runtime chuyển status về client. Hãy trả lỗi field rõ ràng nhưng an toàn, giữ generated source nguyên bản và kiểm thử status qua client/server thật. Client nên sửa request thay vì retry nguyên payload. Validation được thiết kế đúng giúp API dễ tích hợp, giảm lỗi lặp và bảo vệ các lớp nghiệp vụ phía sau.

### Tài liệu tham khảo

- [gRPC – Status codes](https://grpc.io/docs/guides/status-codes/)
- [gRPC – Error handling](https://grpc.io/docs/guides/error/)
- [Protocol Buffers – Proto3 language guide](https://protobuf.dev/programming-guides/proto3/)
- [Google API – Error model](https://cloud.google.com/apis/design/errors)
- [Jakarta Bean Validation](https://jakarta.ee/specifications/bean-validation/)
