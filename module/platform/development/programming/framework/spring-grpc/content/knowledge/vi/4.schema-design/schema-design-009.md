# Thay đổi enum an toàn

Enum giúp hợp đồng gRPC giới hạn một trường vào tập giá trị có tên rõ ràng, chẳng hạn phương thức thanh toán hoặc trạng thái đơn hàng. Khi hệ thống đã có client và server chạy ở nhiều phiên bản, thêm, đổi tên hay xóa một enum value có thể ảnh hưởng đến mã Java sinh ra, dữ liệu protobuf binary và ProtoJSON theo những cách khác nhau.

Với **Spring gRPC**, cần thiết kế enum sao cho phiên bản mới có thể mở rộng mà client cũ không hiểu nhầm giá trị. Bài này tập trung vào quy tắc số enum, giá trị mặc định proto3, xử lý giá trị chưa biết trong Java, đổi tên bằng alias, xóa bằng reserved và triển khai theo từng phiên bản.

## 1. Bắt đầu bằng giá trị zero có ý nghĩa rõ ràng

Trong proto3, enum phải có giá trị đầu tiên bằng 0. Nên dành giá trị này cho trạng thái chưa được chọn, thường đặt tên có hậu tố UNSPECIFIED:

```proto
syntax = "proto3";

package shop.payment.v1;

option java_package = "com.myshop.grpc.payment.v1";
option java_multiple_files = true;

enum PaymentMethod {
  PAYMENT_METHOD_UNSPECIFIED = 0;
  PAYMENT_METHOD_CARD = 1;
  PAYMENT_METHOD_BANK_TRANSFER = 2;
}

message PayOrderRequest {
  string order_id = 1;
  PaymentMethod payment_method = 2;
}
```

Nếu client không gửi payment_method, getter proto3 trả về giá trị zero, tức PAYMENT_METHOD_UNSPECIFIED. Điều này giúp server nhận ra request chưa chọn phương thức thanh toán. Không nên gán CARD = 0: khi client quên gửi field, server có thể vô tình xử lý như khách hàng đã chọn thanh toán thẻ.

**Enum không tự bắt buộc nghiệp vụ.** Nếu thao tác cần một phương thức thanh toán cụ thể, server phải từ chối UNSPECIFIED bằng validation. Nếu cần phân biệt “không gửi field” với “cố ý gửi UNSPECIFIED”, khai báo field là optional PaymentMethod payment_method = 2; và kiểm tra presence bằng hasPaymentMethod().

## 2. Thêm enum value: wire thường tương thích, hành vi chưa chắc

Giả sử phiên bản v1 chỉ hỗ trợ thẻ và chuyển khoản. Sau đó hệ thống bổ sung ví điện tử:

```proto
enum PaymentMethod {
  PAYMENT_METHOD_UNSPECIFIED = 0;
  PAYMENT_METHOD_CARD = 1;
  PAYMENT_METHOD_BANK_TRANSFER = 2;
  PAYMENT_METHOD_WALLET = 3; // Giá trị mới
}
```

Enum được mã hóa bằng **số**, không phải tên symbolic. Do đó, thêm số 3 thường không làm thay đổi cách giải mã các giá trị 0, 1, 2 hiện có. Tuy nhiên, client v1 không có tên PAYMENT_METHOD_WALLET; nếu server v2 trả số 3, client cũ phải xử lý giá trị chưa biết.

Proto3 dùng enum theo mô hình open enum: giá trị số chưa biết có thể được giữ trong field. Với Java generated code, getter enum thường trả UNRECOGNIZED, còn getter số nguyên giữ giá trị gốc:

```java
PaymentMethod method = response.getPaymentMethod();
int rawValue = response.getPaymentMethodValue();

if (method == PaymentMethod.UNRECOGNIZED) {
    // Không gán giá trị mới thành CARD hoặc BANK_TRANSFER.
    logUnknownPaymentMethod(rawValue);
    showUnsupportedPaymentOption();
}
```

Đừng nhầm UNSPECIFIED với UNRECOGNIZED:

| Trường hợp | Ý nghĩa |
| --- | --- |
| PAYMENT_METHOD_UNSPECIFIED (số 0) | Giá trị mặc định hoặc client chủ động chọn trạng thái chưa xác định |
| UNRECOGNIZED | Client hiện tại không có tên enum tương ứng với số nhận được |
| getPaymentMethodValue() | Số nguyên thực tế, hữu ích để log, chẩn đoán hoặc chuyển tiếp |

### Rủi ro khác nhau theo chiều gọi

- **Client mới → server cũ:** client gửi WALLET = 3; server cũ không biết ý nghĩa đó. Proto3 Java có thể biểu diễn số này là UNRECOGNIZED; handler cũ phải từ chối hoặc xử lý theo chính sách rõ ràng. Không được mặc định chuyển sang thẻ.
- **Server mới → client cũ:** server trả WALLET = 3; client cũ có thể nhận UNRECOGNIZED. Ứng dụng cần nhánh dự phòng an toàn thay vì crash hoặc đưa ra quyết định sai.
- **Client mới → server mới:** cả hai hiểu giá trị mới, nhưng server vẫn phải kiểm tra quyền và điều kiện nghiệp vụ.

Vì vậy, “thêm enum value tương thích binary” không có nghĩa mọi phiên bản ứng dụng đều hỗ trợ tính năng đó.

## 3. Xử lý enum chưa biết trong Java Spring gRPC

Ở phía server, không nên dùng nhánh mặc định để biến giá trị lạ thành một phương thức hợp lệ. Ví dụ handler có thể kiểm tra giá trị trước khi xử lý:

```java
PaymentMethod method = request.getPaymentMethod();

if (method == PaymentMethod.PAYMENT_METHOD_UNSPECIFIED) {
    observer.onError(Status.INVALID_ARGUMENT
            .withDescription("payment_method must be selected")
            .asRuntimeException());
    return;
}

if (method == PaymentMethod.UNRECOGNIZED) {
    int rawValue = request.getPaymentMethodValue();
    observer.onError(Status.INVALID_ARGUMENT
            .withDescription("unsupported payment_method value: " + rawValue)
            .asRuntimeException());
    return;
}

switch (method) {
    case PAYMENT_METHOD_CARD:
        paymentService.payByCard(request);
        break;
    case PAYMENT_METHOD_BANK_TRANSFER:
        paymentService.payByBankTransfer(request);
        break;
    default:
        observer.onError(Status.INVALID_ARGUMENT
                .withDescription("unsupported payment method")
                .asRuntimeException());
        return;
}
```

Đây là phần minh họa validation và dispatch; trong handler thực tế, paymentService là dependency của ứng dụng và cần ánh xạ lỗi nghiệp vụ nhất quán sang gRPC status. Điểm quan trọng là kiểm tra cả UNSPECIFIED và UNRECOGNIZED trước khi chạy logic.

Ở phía client, khi đọc enum từ response, hãy quyết định cách hiển thị hoặc thông báo tính năng chưa được hỗ trợ. Nếu số enum được dùng trong log hoặc hệ thống trung gian, lấy giá trị bằng getPaymentMethodValue(); không gọi phương thức lấy số trên UNRECOGNIZED, vì enum sentinel này không đại diện một số nghiệp vụ cụ thể.

## 4. Đổi tên enum value: số giữ nguyên nhưng tên vẫn là hợp đồng

Giả sử tên PAYMENT_METHOD_BANK_TRANSFER cần đổi thành PAYMENT_METHOD_WIRE_TRANSFER. Nếu giữ nguyên số 2, protobuf binary vẫn truyền cùng một số. Tuy nhiên, việc đổi tên ảnh hưởng:

- Mã nguồn Java: hằng enum cũ không còn trong generated API mới, nên code tham chiếu tên cũ có thể không biên dịch.
- ProtoJSON: enum thường được biểu diễn bằng tên symbolic; JSON client gửi tên cũ hoặc mong đợi tên cũ có thể bị ảnh hưởng.
- Descriptor, tài liệu schema và các công cụ dùng tên enum: chúng sẽ thấy tên mới.

Không nên đổi tên trực tiếp nếu client JSON hoặc code Java bên ngoài đang phụ thuộc tên cũ. Một giai đoạn chuyển tiếp có thể dùng alias:

```proto
enum PaymentMethod {
  option allow_alias = true;

  PAYMENT_METHOD_UNSPECIFIED = 0;
  PAYMENT_METHOD_CARD = 1;
  PAYMENT_METHOD_BANK_TRANSFER = 2 [deprecated = true];
  PAYMENT_METHOD_WIRE_TRANSFER = 2;
}
```

allow_alias = true cho phép hai tên cùng ánh xạ tới một số. Đây là công cụ chuyển đổi, không phải giải pháp tự động cho mọi client:

- Protobuf binary chỉ mang số 2; client cũ vẫn nhận diện số đó bằng tên cũ trong generated code.
- Trong ProtoJSON và TextFormat, tên được serialize cho một số alias phụ thuộc vào **tên xuất hiện đầu tiên** trong enum declaration. Đổi thứ tự có thể làm thay đổi chuỗi JSON được phát ra.
- Java generated enum cũng ánh xạ số về một hằng đại diện; không nên giả định client mới sẽ luôn nhận được alias thứ hai khi parse số.
- deprecated = true chỉ cảnh báo người dùng schema; không tự di chuyển client hoặc xóa tên cũ.

Nếu API có ProtoJSON, hãy kiểm tra chính xác chuỗi được serialize/parse trước khi thay đổi thứ tự alias. Với client đa ngôn ngữ, giữ tên cũ trong giai đoạn tương thích và chỉ loại bỏ sau khi đã xác nhận consumer chuyển đổi. Nếu không thể duy trì hành vi JSON cũ, cân nhắc endpoint hoặc phiên bản API mới.

## 5. Xóa enum value bằng reserved

Khi một enum value đã phát hành không còn được dùng, không tái sử dụng số hoặc tên đó:

```proto
enum PaymentMethod {
  PAYMENT_METHOD_UNSPECIFIED = 0;
  PAYMENT_METHOD_CARD = 1;

  reserved 2;
  reserved "PAYMENT_METHOD_BANK_TRANSFER";
}
```

reserved cho enum có hai dạng:

- reserved 2; giữ lại số enum đã xóa.
- reserved "PAYMENT_METHOD_BANK_TRANSFER"; giữ lại tên đã xóa.

Nên reserve cả số và tên. Nếu chỉ xóa khai báo rồi gán số 2 cho PAYMENT_METHOD_WALLET, client cũ hoặc dữ liệu lưu từ trước có thể hiểu một giao dịch chuyển khoản thành thanh toán ví. Đây là lỗi ngữ nghĩa nguy hiểm dù parser vẫn đọc được payload.

Có thể reserve một dải số từ 4 đến 7; hai đầu mút đều được tính. Chỉ reserve các số thực sự đã dùng hoặc cần bảo vệ, không reserve trùng với value còn tồn tại.

## 6. ProtoJSON cần được kiểm tra riêng

Trong protobuf binary, enum được truyền bằng số. Trong ProtoJSON, enum mặc định được biểu diễn bằng tên:

```json
{
  "paymentMethod": "PAYMENT_METHOD_CARD"
}
```

Một số mapping/parser ProtoJSON cũng hỗ trợ biểu diễn enum bằng số nguyên, nhưng không nên dựa vào điều đó để bỏ qua việc kiểm thử client JSON. Đặc biệt:

- Đổi tên enum value có thể làm JSON client gửi tên cũ không parse được theo schema mới.
- Alias có thể giữ nhiều tên đầu vào, nhưng tên đầu tiên được dùng khi serialize.
- Giá trị enum số chưa biết có thể được giữ khi dùng dạng số; tên symbolic không biết thường không thể được ánh xạ nếu schema không khai báo tên đó.
- JSON gateway hoặc thư viện JSON thông thường có thể có chính sách unknown key/value khác ProtoJSON chuẩn.

Nếu Spring gRPC service chỉ trao đổi protobuf binary giữa các stub đã sinh mã, rủi ro JSON có thể không nằm trên đường gọi chính. Nhưng nếu có HTTP transcoding, REST gateway, file JSON cấu hình hoặc event JSON, hãy coi đó là một bề mặt hợp đồng riêng.

## 7. Triển khai enum mới theo từng giai đoạn

Khi thêm PAYMENT_METHOD_WALLET, trình tự an toàn thường là:

1. **Cập nhật schema và server trước.** Server mới nhận biết giá trị mới nhưng chưa bật client gửi nó. Server cũ trong fleet vẫn có thể từ chối giá trị này.
2. **Triển khai toàn bộ instance server.** Xác nhận không còn instance cũ nhận request chứa enum value mới; nếu cần, định tuyến theo capability hoặc phiên bản.
3. **Cập nhật client có nhánh unknown an toàn.** Client cũ không được crash hoặc chọn nhầm phương thức khi nhận enum mới.
4. **Bật tính năng theo kiểm soát.** Chỉ cho client gửi giá trị mới khi server đích đã hỗ trợ; dùng feature flag hoặc capability negotiation nếu rollout phân tán.
5. **Theo dõi và chuyển đổi.** Đo tỷ lệ request bị từ chối do enum chưa biết, số client còn dùng tên cũ và lỗi ProtoJSON nếu có.

Không nên bật enum mới trên client trong khi load balancer vẫn phân phối request tới server cũ. Với một request thanh toán, việc server cũ bỏ qua hoặc từ chối phương thức mới phải được xử lý có chủ đích; không thể coi đó là lỗi retry thông thường nếu thao tác có thể đã tạo trạng thái thanh toán.

## 8. Kiểm thử schema và client cũ/mới

Các ca kiểm thử quan trọng:

| Trường hợp | Kỳ vọng |
| --- | --- |
| Không gửi enum trong proto3 | Server nhận UNSPECIFIED và từ chối nếu nghiệp vụ yêu cầu chọn |
| Gửi enum value đã biết | Server dispatch đúng phương thức |
| Gửi số enum chưa biết tới server cũ | Server nhận diện UNRECOGNIZED/giá trị số và xử lý theo chính sách, không tự chọn phương thức khác |
| Server mới trả enum value mới cho client cũ | Client cũ xử lý nhánh unknown an toàn |
| Đổi tên nhưng giữ số | Binary test có thể qua; kiểm tra riêng generated Java và ProtoJSON |
| Thêm alias | Xác minh tên JSON serialize, parse và enum Java đại diện |
| Xóa value | Compiler từ chối khai báo lại số/tên đã reserve |
| Rollout nhiều instance | Client chỉ gửi value mới khi mọi server nhận traffic đã hỗ trợ |

Ví dụ kiểm tra giá trị chưa biết ở mức message:

```java
// bytes được tạo từ một schema mới có PAYMENT_METHOD_WALLET = 3.
PayOrderRequest parsedByOldClient =
        PayOrderRequest.parseFrom(bytesFromNewClient);

assertEquals(
        PaymentMethod.UNRECOGNIZED,
        parsedByOldClient.getPaymentMethod());
assertEquals(3, parsedByOldClient.getPaymentMethodValue());
```

Đây chỉ là kiểm tra protobuf parsing. Test tích hợp còn phải xác minh handler Spring gRPC trả status phù hợp và không gọi nhầm domain service. Nếu có ProtoJSON, thêm fixture JSON chứa tên enum cũ, tên alias mới và giá trị số chưa biết.

## 9. Checklist trước khi sửa enum

- [ ] Giá trị 0 là UNSPECIFIED hoặc trạng thái mặc định an toàn.
- [ ] Không đổi số của enum value đã phát hành.
- [ ] Enum value mới có số chưa từng dùng và được đánh giá với client cũ.
- [ ] Handler Java xử lý UNSPECIFIED và UNRECOGNIZED rõ ràng.
- [ ] Không tự ánh xạ giá trị chưa biết sang một lựa chọn nghiệp vụ khác.
- [ ] Nếu đổi tên, đã đánh giá generated Java API, ProtoJSON và alias.
- [ ] Nếu xóa value, đã reserve cả số và tên.
- [ ] Rollout server/client có thứ tự và có cách kiểm chứng toàn bộ server instance.
- [ ] Có test binary với schema cũ/mới và test JSON nếu có gateway.

**Tự kiểm tra**

**Câu 1.** Vì sao enum proto3 nên có UNSPECIFIED = 0?

*Đáp án:* Field enum không được gửi sẽ đọc thành số 0. Giá trị này cần biểu diễn trạng thái chưa chọn, không được vô tình kích hoạt một hành động nghiệp vụ.

**Câu 2.** Server v2 thêm WALLET = 3; client v1 nhận response chứa số 3. Client Java nên xử lý ra sao?

*Đáp án:* Getter enum có thể trả UNRECOGNIZED; lấy số bằng getter ...Value() nếu cần log/chẩn đoán và hiển thị trạng thái không hỗ trợ. Không chuyển nó thành CARD hoặc BANK_TRANSFER.

**Câu 3.** Đổi tên enum value nhưng giữ nguyên số có hoàn toàn an toàn không?

*Đáp án:* Chỉ có thể giữ tương thích ở binary number. Generated Java symbol, descriptor và ProtoJSON name có thể đổi. Cần kiểm tra từng loại consumer và dùng giai đoạn alias nếu phù hợp.

**Câu 4.** Xóa enum value số 2 rồi dùng số 2 cho value mới có được không?

*Đáp án:* Không. Reserve số 2 và tên cũ để payload đã phát hành không bị hiểu thành ý nghĩa mới.

Enum là một phần của hợp đồng, không chỉ là danh sách hằng số trong Java. Hãy giữ số ổn định, dành giá trị zero cho trạng thái mặc định an toàn, chuẩn bị nhánh xử lý giá trị chưa biết và kiểm tra cả binary lẫn JSON. Như vậy, Spring gRPC có thể mở rộng tập lựa chọn mà không buộc mọi client phải nâng cấp cùng một thời điểm.
