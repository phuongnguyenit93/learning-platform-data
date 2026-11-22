# Khảo sát hành vi, phụ thuộc và đường chạy quan trọng

Bạn được giao sửa một lỗi trong hệ thống quản lý đơn hàng đã tồn tại nhiều năm. Ticket chỉ có một câu: “Một số đơn đã thanh toán vẫn bị đánh dấu chưa hoàn tất”. Bạn tìm thấy phương thức `completeOrder`, nhưng nó chỉ cập nhật trạng thái. Trước đó có worker xử lý thanh toán, listener nhận sự kiện và job đồng bộ chạy định kỳ. Chưa rõ thành phần nào thực sự quyết định trạng thái cuối cùng, dữ liệu được ghi ở đâu và hệ thống bên ngoài có tham gia hay không.

Nếu sửa ngay phương thức đầu tiên có tên gần giống ticket, bạn có thể chỉ xử lý triệu chứng. Thay đổi có thể bỏ sót một đường chạy khác, phá retry hoặc làm sai dữ liệu ở nhánh không được nhìn thấy trong test hiện có.

Khi làm việc với mã hiện hữu, bước đầu tiên thường không phải viết lại hay refactor. Đó là **khảo sát hành vi, phụ thuộc và những đường chạy quan trọng đủ để hiểu nơi thay đổi sẽ tác động**. Khảo sát có mục tiêu giúp giảm phỏng đoán, nhận ra ranh giới thật của hệ thống và chọn cách xác minh phù hợp.

Trong chương **Mã hiện hữu** thuộc module `CODE_QUALITY_FUNDAMENTALS`, việc hiểu hệ thống đang chạy ra sao là nền tảng để giữ mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Mã hiện hữu thường chứa quyết định lịch sử, hợp đồng ngầm và phụ thuộc không thể thấy chỉ từ tên lớp. Cần kết hợp đọc mã, test, cấu hình, lịch sử thay đổi và quan sát runtime để tạo một mô hình đủ chính xác cho công việc trước mắt.

Sau bài học, bạn có thể:

- Xác định câu hỏi và phạm vi khảo sát trước khi đọc code.
- Lần theo entry point từ HTTP, message, scheduler hoặc CLI tới kết quả và tác dụng phụ.
- Phân biệt phụ thuộc trực tiếp, phụ thuộc runtime, cấu hình và phụ thuộc dữ liệu.
- Tìm đường chạy quan trọng theo tác động nghiệp vụ, tần suất, rủi ro và khả năng phục hồi.
- Dùng test hiện có, log, trace và database schema để kiểm chứng giả thuyết.
- Viết characterization test ghi nhận hành vi hiện tại trước khi thay đổi.
- Tạo bản đồ luồng và danh sách câu hỏi còn mở mà không cố mô tả toàn bộ repository.
- Chọn bước thay đổi nhỏ có thể xác minh và giảm rủi ro.

## 1. Khảo sát bắt đầu từ một câu hỏi cụ thể

Một repository có thể có hàng nghìn file. Đọc tuần tự từ thư mục gốc thường tiêu tốn thời gian mà chưa chắc giúp trả lời vấn đề cần giải quyết. Hãy bắt đầu bằng câu hỏi có phạm vi rõ.

Ví dụ thay vì “Tìm hiểu module checkout”, hãy đặt câu hỏi:

- Khi người mua xác nhận đơn, thành phần nào nhận request đầu tiên?
- Phí giao hàng được tính ở đâu và dựa trên dữ liệu nào?
- Đơn được ghi trước hay sau khi gọi cổng thanh toán?
- Nếu cổng thanh toán timeout, trạng thái đơn và lần retry tiếp theo ra sao?
- Những consumer nào đọc trạng thái đơn?
- Test nào bảo vệ điều kiện “đã thanh toán” và “đã hoàn tiền”?

Mỗi câu hỏi định hướng một loại bằng chứng. Entry point cần xem controller hoặc listener; thứ tự tác dụng phụ cần đọc service và transaction; trạng thái sau timeout có thể cần xem adapter, retry policy, event handler, log hoặc trace.

### Phạm vi khảo sát cần có ranh giới

Trước khi mở file, ghi ngắn:

| Thành phần | Ví dụ |
| --- | --- |
| Vấn đề quan sát | Một số đơn đã thanh toán nhưng trạng thái chưa hoàn tất |
| Hành vi cần hiểu | Luồng xác nhận thanh toán và cập nhật đơn |
| Điểm bắt đầu dự kiến | Webhook thanh toán, message consumer, job đồng bộ |
| Kết quả cần xác minh | Trạng thái lưu trong database và phản hồi API |
| Hệ thống liên quan | Payment provider, message broker, database |
| Ngoài phạm vi hiện tại | Giao diện hiển thị lịch sử đơn, trừ khi ảnh hưởng trạng thái |

Phạm vi có thể mở rộng khi bằng chứng cho thấy một phụ thuộc ngoài phạm vi đang tác động trực tiếp. Nhưng mỗi lần mở rộng nên gắn với một câu hỏi cụ thể, tránh biến khảo sát thành việc đọc cả hệ thống không có điểm dừng.

## 2. Bắt đầu từ hành vi quan sát được, không chỉ từ tên lớp

Tên lớp, package và method giúp tìm điểm vào, nhưng chúng không phải bằng chứng cuối cùng về hành vi.

Một phương thức tên `markPaid` có thể chỉ cập nhật một cột. Trạng thái thanh toán thực tế có thể được quyết định bởi webhook đã xác thực, kết quả truy vấn đối soát hoặc một workflow nhiều bước. Tương tự, một controller tên `OrderController` có thể ủy quyền toàn bộ logic cho application service và không chứa quy tắc nghiệp vụ nào.

Hãy mô tả hành vi bằng những yếu tố quan sát được:

- **Đầu vào:** request, message, command, lịch chạy hoặc thao tác người dùng.
- **Điều kiện:** xác thực, quyền, trạng thái hiện tại, dữ liệu cấu hình.
- **Quyết định:** quy tắc nghiệp vụ được áp dụng.
- **Tác dụng phụ:** ghi database, phát event, gọi HTTP, gửi email, cập nhật cache.
- **Đầu ra:** response, message tiếp theo, trạng thái được lưu hoặc lỗi.
- **Thời điểm:** ngay trong request, bất đồng bộ hay theo lịch.

Ví dụ một mô tả có ích:

```text
Khi nhận webhook thanh toán:
1. Xác minh chữ ký và mã giao dịch.
2. Tìm đơn theo mã tham chiếu.
3. Kiểm tra trạng thái hiện tại và tính lặp của sự kiện.
4. Ghi nhận giao dịch thanh toán.
5. Chuyển đơn sang trạng thái đã thanh toán.
6. Phát sự kiện cho quy trình giao hàng.
7. Trả phản hồi cho nhà cung cấp.
```

Đây là **giả thuyết luồng** để điều tra. Chỉ đánh dấu một bước là đã xác nhận sau khi tìm thấy bằng chứng từ code, test, cấu hình hoặc quan sát phù hợp.

## 3. Tìm entry point và lần theo luồng chính

Entry point là nơi một luồng công việc đi vào ứng dụng. Trong hệ thống Java, nó có thể là:

- HTTP controller hoặc endpoint của framework.
- Message listener/consumer.
- Scheduler hoặc job định kỳ.
- CLI command hoặc tác vụ quản trị.
- Callback/webhook từ hệ thống bên ngoài.
- Event handler nội bộ.
- Listener trong ứng dụng desktop hoặc batch processor.

Một cách tìm là bắt đầu từ route, tên event hoặc tên job trong yêu cầu. Sau đó lần theo lời gọi đến lớp nghiệp vụ và adapter.

Ví dụ luồng HTTP:

```text
HTTP request
    |
    v
OrderController
    |
    v
ConfirmOrderService
    |
    +----> OrderRepository
    |
    +----> PaymentGateway
    |
    +----> EventPublisher
    |
    v
HTTP response
```

Sơ đồ này chỉ là dạng khái quát. Luồng thật có thể phát event trước khi transaction commit, gọi payment gateway qua một worker, hoặc trả response trước khi công việc nền hoàn tất. Cần kiểm tra thứ tự và ranh giới thực tế.

### Tìm điểm bắt đầu bằng công cụ tìm kiếm code

Có thể dùng tìm kiếm theo route, annotation, tên event hoặc tên phương thức. Ví dụ các lệnh Git/rg minh họa:

```text
rg -n "ConfirmOrder|confirmOrder|/orders/.*/confirm" src
rg -n "@PostMapping|@KafkaListener|@Scheduled" src
rg -n "PaymentSucceeded|OrderPaid" src
```

Tên annotation và framework thực tế có thể khác. Hãy tìm theo biểu tượng cụ thể đã xuất hiện trong yêu cầu hoặc cấu hình dự án. Nếu tìm thấy nhiều entry point, đừng mặc định chúng cùng gọi một service; kiểm tra từng đường.

### Lần theo lời gọi tới điểm kết thúc

Từ entry point, ghi nhận:

1. Method được gọi trực tiếp.
2. Method nào chứa quyết định nghiệp vụ.
3. Adapter nào thực hiện I/O.
4. Dữ liệu nào được trả về hoặc lưu lại.
5. Công việc nào tiếp tục bất đồng bộ.
6. Lỗi được truyền lên, chuyển đổi, retry hay nuốt.

Không cần chép toàn bộ call graph. Hãy ghi những nút làm thay đổi trạng thái, quyết định quyền, tính tiền hoặc điều phối phụ thuộc.

## 4. Theo dõi dữ liệu qua các ranh giới

Một luồng gọi cho biết thành phần nào gọi thành phần nào; **luồng dữ liệu** cho biết thông tin nào được truyền, biến đổi và lưu ở đâu.

Với một trường như `paymentStatus`, hãy hỏi:

- Giá trị ban đầu đến từ request, message hay database?
- Ai được phép thay đổi?
- Có mapping giữa enum Java, mã database và trạng thái provider không?
- Có default value hoặc fallback không?
- Giá trị có được cache hoặc sao chép sang bảng khác không?
- Những consumer nào đọc giá trị?
- Có migration hoặc dữ liệu cũ mang trạng thái không còn được tạo mới không?

Ví dụ:

```text
Provider event: "captured"
       |
       v
Webhook DTO
       |
       v
PaymentStatusMapper
       |
       v
PaymentRecord.status = CAPTURED
       |
       v
OrderStatePolicy
       |
       v
Order.status = PAID
       |
       +----> Outbox event
       |
       +----> Query API
```

Một provider status có thể được map thành trạng thái nội bộ khác. Không nên tìm và thay chuỗi "captured" ở mọi nơi trước khi biết mapping và ý nghĩa từng trạng thái.

### Phân biệt nguồn sự thật với bản sao

Database có thể lưu trạng thái giao dịch và trạng thái đơn riêng. Cache, search index và read model có thể giữ bản sao để truy vấn nhanh. Khi điều tra lỗi, cần biết:

- Nơi nào là nguồn sự thật cho trạng thái thanh toán?
- Read model được cập nhật đồng bộ hay bất đồng bộ?
- Có độ trễ nhất quán được chấp nhận không?
- Nếu event bị xử lý hai lần, bản sao có bị cập nhật sai không?
- Có cơ chế rebuild hoặc đối soát khi dữ liệu lệch không?

Một màn hình hiển thị trạng thái cũ chưa chắc database nguồn đã sai. Có thể read model hoặc cache chưa được cập nhật. Khảo sát cần lần từ nơi quan sát được vấn đề tới nguồn dữ liệu và đường đồng bộ.

## 5. Lập bản đồ phụ thuộc theo loại

Không phải mọi phụ thuộc đều hiện thành một lời gọi phương thức. Một bản đồ có ích nên phân biệt ít nhất bốn loại:

| Loại phụ thuộc | Ví dụ | Cách xác minh |
| --- | --- | --- |
| **Mã nguồn trực tiếp** | Service gọi repository hoặc policy | IDE navigation, tìm reference, call hierarchy |
| **Runtime/điều phối** | Listener được framework đăng ký, bean được inject | Annotation, configuration, dependency injection wiring |
| **Cấu hình/môi trường** | URL payment provider, feature flag, timeout | Config file, environment binding, deployment configuration được phép xem |
| **Dữ liệu/tích hợp** | Schema, message topic, API contract, shared table | Migration, DTO/schema, consumer/producer, integration test |

Một service có thể không import trực tiếp lớp provider nhưng vẫn phụ thuộc provider qua interface và cấu hình wiring. Nếu chỉ xem import, ta bỏ sót phụ thuộc runtime.

### Phụ thuộc trực tiếp và phụ thuộc gián tiếp

```text
CheckoutService
    |
    +----> PaymentGateway (interface)
                 |
                 v
           HttpPaymentGateway
                 |
                 v
           Payment Provider API
```

`CheckoutService` phụ thuộc trực tiếp vào hợp đồng `PaymentGateway`. Hành vi runtime còn phụ thuộc adapter được cấu hình là `HttpPaymentGateway`, URL, credentials, timeout và phiên bản API của provider.

Cần ghi rõ **điều đã xác nhận** và **điều còn suy đoán**. Chỉ nhìn interface không chứng minh production đang dùng adapter nào.

### Dùng tìm kiếm và navigation có mục tiêu

Một số thao tác hữu ích:

- Tìm nơi khai báo interface và mọi implementation.
- Tìm nơi constructor nhận interface đó.
- Tìm configuration hoặc factory tạo implementation.
- Tìm nơi publish và consume cùng event/topic.
- Tìm tên bảng, cột hoặc query được đọc/ghi.
- Tìm test cấu hình adapter và contract.

Nếu có nhiều implementation cho test, local và production, hãy xác định profile hoặc điều kiện chọn. Đừng coi một fake trong test là cấu hình chạy production.

## 6. Phân biệt dependency với data ownership

Một lớp có thể phụ thuộc vào repository nhưng không sở hữu dữ liệu mà repository lưu. Một service có thể nhận một object mutable nhưng không nên giữ nó sau khi request kết thúc.

Khi đọc một field hoặc tham số, hãy hỏi:

- Ai tạo giá trị?
- Ai được quyền sửa?
- Ai đảm bảo tính hợp lệ?
- Vòng đời của dữ liệu là request, transaction, process hay lâu dài?
- Có sao chép dữ liệu giữa các thành phần không?
- Ai chịu trách nhiệm đồng bộ khi có nhiều luồng hoặc instance?

Ví dụ `OrderRepository` là dependency của `ConfirmOrderService`. Bản ghi đơn hàng là dữ liệu miền được lưu bền vững. Cache trạng thái đơn có thể là bản sao. Ba thứ có liên hệ nhưng không phải cùng một khái niệm.

Nếu nhiều service trực tiếp cập nhật cùng một bảng mà không có hợp đồng rõ, đó là tín hiệu cần xem lại ownership và transaction. Tuy nhiên, không nên kết luận repository pattern đang bị vi phạm chỉ vì có nhiều query; có thể hệ thống dùng một mô hình persistence khác có chủ đích.

## 7. Tìm đường chạy quan trọng theo tác động

Không phải mọi đường chạy đều có mức quan trọng như nhau. Một endpoint health check được gọi thường xuyên có thể đơn giản và ít tác động nghiệp vụ. Một luồng hoàn tiền hiếm khi chạy có thể ảnh hưởng trực tiếp tới tiền và dữ liệu kế toán.

Để chọn đường cần khảo sát sâu, kết hợp các chiều:

- **Tác động nghiệp vụ:** ảnh hưởng tới tiền, quyền, dữ liệu, đơn hàng hoặc cam kết với khách hàng.
- **Tần suất:** được gọi bao nhiêu lần, vào thời điểm nào, theo burst hay theo lịch.
- **Rủi ro lỗi:** hậu quả khi sai, khả năng phát hiện và phục hồi.
- **Độ phức tạp phụ thuộc:** số hệ thống, queue, transaction và trạng thái liên quan.
- **Khả năng thay đổi:** có roadmap, ticket hoặc thay đổi thường xuyên không.
- **Khả năng quan sát:** có log, trace, metric và test để xác nhận không.

Một bảng ưu tiên khảo sát:

| Luồng | Tần suất | Tác động khi sai | Phụ thuộc | Ưu tiên điều tra |
| --- | --- | --- | --- | --- |
| Xem danh sách đơn | Cao | Trung bình | Database, cache | Theo dõi hiệu năng và phân quyền |
| Xác nhận thanh toán | Trung bình | Cao | Provider, DB, event | Cao |
| Hoàn tiền | Thấp | Rất cao | Provider, DB, kế toán | Cao |
| Xuất báo cáo cũ | Thấp | Thấp–trung bình | DB, file storage | Theo yêu cầu thay đổi |
| Health check | Rất cao | Thấp nếu chỉ đọc trạng thái | Runtime, dependency probe | Đảm bảo nhẹ và không tạo tải |

Các mức trong bảng là ví dụ định tính. Một luồng có thể cần ưu tiên cao vì rủi ro dù tần suất thấp. Không dùng tần suất đơn độc để xếp hạng.

### “Đường chạy quan trọng” có hai nghĩa cần làm rõ

Trong khảo sát hệ thống, cụm này có thể chỉ:

1. **Đường nghiệp vụ quan trọng:** một hành trình có tác động lớn nếu sai, như thanh toán hoặc cấp quyền.
2. **Đường thực thi quan trọng:** chuỗi lời gọi và phụ thuộc thực sự được kích hoạt khi một hành vi diễn ra.

Hai góc nhìn cần kết hợp. Một hành trình thanh toán quan trọng nhưng chưa biết entry point thì chưa đủ để sửa. Một call path dài nhưng không nằm trên luồng có tác động lớn có thể chưa cần ưu tiên.

## 8. Tìm các nhánh lỗi và đường chạy không thành công

Chỉ khảo sát happy path thường bỏ sót phần rủi ro nhất của hệ thống hiện hữu.

Với mỗi phụ thuộc, hãy hỏi:

- Timeout xảy ra ở đâu?
- Exception được truyền lên hay chuyển thành kết quả?
- Có retry không, số lần và khoảng chờ ra sao?
- Thao tác có idempotent không?
- Nếu process dừng giữa hai bước, dữ liệu còn ở trạng thái nào?
- Có transaction bao quanh những thao tác nào?
- Có dead-letter queue hoặc cơ chế replay không?
- Người vận hành biết lỗi qua metric, log hoặc alert nào?

Ví dụ:

```text
Xác nhận thanh toán
      |
      v
Gọi provider
      |
      +----> Thành công ----> Ghi PaymentRecord
      |                          |
      |                          v
      |                     Đánh dấu Order PAID
      |                          |
      |                          v
      |                     Phát OrderPaid
      |
      +----> Timeout -----> Kết quả chưa rõ
                                 |
                                 v
                         Đối soát hoặc retry an toàn
```

Timeout không luôn có nghĩa provider chưa xử lý. Provider có thể đã thu tiền nhưng response bị mất trên mạng. Nếu ứng dụng retry một thao tác không idempotent, có thể tạo giao dịch trùng.

Đường lỗi vì thế cần được khảo sát cùng với trạng thái lưu và hợp đồng provider. Không được giả định “exception nghĩa là không có side effect”.

## 9. Đọc test như tài liệu về hành vi hiện tại

Test hiện có thường là nguồn thông tin hữu ích, đặc biệt khi tài liệu hệ thống đã lỗi thời. Hãy tìm:

- Unit test cho policy hoặc service.
- Integration test cho repository, transaction và adapter.
- Contract test giữa producer và consumer.
- Test cho trạng thái và chuyển trạng thái.
- Test lỗi, timeout, retry và duplicate event.
- Fixture hoặc test data thể hiện dữ liệu cũ.

Test cho biết tác giả trước đây **đã chọn xác nhận điều gì**. Nó không nhất thiết bao phủ mọi hành vi hiện tại, và một test có thể đang ghi nhận một bug cũ.

Khi đọc test, hãy tách ba câu hỏi:

1. Test đang xác nhận quy tắc nào?
2. Quy tắc đó đến từ yêu cầu hay chỉ từ cách code đang hoạt động?
3. Có nhánh quan trọng nào chưa được test?

Một test có tên `shouldReturnSuccess` nhưng không assert trạng thái lưu, event phát ra hoặc tác dụng phụ có thể cung cấp ít thông tin hơn tên gọi gợi ý.

### Chạy test có mục tiêu

Khi khảo sát, ưu tiên test liên quan tới đường chạy thay đổi. Nếu chưa biết build command, cấu trúc test hoặc trạng thái môi trường, đừng tự suy ra rằng toàn bộ test đã chạy. Ghi chính xác lệnh và kết quả nếu có thực thi.

Một test thất bại trước khi sửa không phải bằng chứng thay đổi mới gây lỗi. Cần xác định baseline, môi trường, fixture và tính ổn định của test.

## 10. Characterization test: ghi nhận hành vi trước khi thay đổi

Với mã cũ thiếu đặc tả, **characterization test** ghi lại hành vi đang quan sát được ở những tình huống quan trọng. Nó giúp người sửa biết một refactor có làm thay đổi kết quả hay không.

Ví dụ một policy hiện tại:

```java
final class LegacyShippingPolicy {
    long fee(long subtotalVnd, boolean vip) {
        if (vip || subtotalVnd > 500_000L) {
            return 0L;
        }
        return 25_000L;
    }
}
```

Test ghi nhận hành vi hiện tại:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class LegacyShippingPolicyCharacterizationTest {
    private final LegacyShippingPolicy policy =
            new LegacyShippingPolicy();

    @Test
    void recordsCurrentBoundaryBehavior() {
        assertEquals(25_000L, policy.fee(499_999L, false));
        assertEquals(25_000L, policy.fee(500_000L, false));
        assertEquals(0L, policy.fee(500_001L, false));
        assertEquals(0L, policy.fee(100_000L, true));
    }
}
```

Test cho thấy implementation hiện tại **không miễn phí ở đúng 500.000 VND**. Đây là mô tả hành vi hiện tại, không khẳng định hành vi đó đúng với chính sách sản phẩm.

Nếu yêu cầu mới nói đúng ngưỡng cũng được miễn phí, hãy cập nhật test thành test chức năng cho hành vi mong muốn trong thay đổi riêng. Đừng giữ characterization test như luật bất biến khi đã xác nhận hành vi cũ là bug.

### Khi nào characterization test có thể ghi nhận điều không mong muốn?

Có thể test phải ghi nhận một hành vi hiện hữu mà nhóm chưa biết là bug hay contract. Trong trường hợp đó, đặt tên test và ghi chú rõ nó đang “characterize” behavior, rồi xác nhận với chủ sở hữu nghiệp vụ trước khi biến nó thành hợp đồng dài hạn.

Không nên chụp lại mọi bug trong mã cũ thành test vĩnh viễn. Mục tiêu là tạo điểm tựa cho thay đổi, không đóng băng mọi hành vi ngẫu nhiên.

## 11. Dùng log, metric và trace để kiểm chứng luồng runtime

Đọc source cho biết code có thể làm gì; log, metric và trace giúp biết **đường nào thực sự đã chạy** trong một môi trường cụ thể.

### Log

Log hữu ích có thể cho biết:

- Request hoặc event đã tới service nào.
- Correlation ID/trace ID nào liên kết các bước.
- Kết quả mapping trạng thái.
- Lỗi phụ thuộc và retry.
- Kết quả transaction hoặc số bản ghi bị ảnh hưởng, nếu được ghi an toàn.

Không nên log toàn bộ payload, token, dữ liệu thanh toán hoặc thông tin cá nhân chỉ để “hiểu luồng”. Dùng định danh tương quan và trường dữ liệu tối thiểu theo chính sách bảo mật.

### Metric

Metric có thể chỉ ra:

- Số request/event theo loại.
- Tỷ lệ thành công/lỗi/timeout.
- Thời gian xử lý và phân vị.
- Số retry, duplicate event và queue lag.
- Tỷ lệ trạng thái đơn bị treo hoặc cần đối soát.
- Connection pool, worker và backlog.

Metric thường tổng hợp nên không đủ để giải thích một giao dịch cụ thể. Chúng giúp nhận diện mẫu và chọn nơi đào sâu.

### Trace

Distributed trace có thể liên kết các span qua controller, service, database và HTTP client. Khi đọc trace, xác định:

- Span nào là cha/con?
- Thời gian chờ hay thời gian CPU?
- Có lời gọi bất đồng bộ hoặc message mới không?
- Có span bị thiếu do instrumentation không?
- Trace sampling có bỏ sót một số request không?

Trace không phải bản đồ đầy đủ mọi đường chạy. Một trace chỉ thể hiện một lần thực thi cụ thể; cần so sánh nhiều mẫu, gồm cả thành công và thất bại.

## 12. Kiểm tra transaction, thứ tự side effect và tính nhất quán

Một luồng có thể gọi ba thành phần nhưng thứ tự thực hiện quyết định dữ liệu cuối cùng.

Ví dụ:

```java
store.save(order);
eventPublisher.publish(new OrderCreated(order.id()));
emailSender.sendConfirmation(order);
```

Cần hỏi:

- `save` có commit trước khi publish không?
- `publish` là đồng bộ hay chỉ ghi vào outbox?
- Nếu email lỗi, đơn có bị rollback không?
- Nếu event publish thành công nhưng transaction DB rollback, consumer sẽ thấy gì?
- Nếu retry toàn bộ method, event hoặc email có bị gửi trùng không?

Chỉ nhìn thứ tự các dòng chưa đủ biết ranh giới transaction. Cần xem annotation/configuration, transaction manager, outbox implementation, broker acknowledgment và test tích hợp.

### Một bảng ghi nhận thứ tự và kết quả lỗi

| Bước | Tác dụng phụ | Nếu bước này lỗi |
| --- | --- | --- |
| Lưu đơn | Ghi DB | Không phát event nếu chưa có đơn hợp lệ |
| Phát event | Gửi message hoặc ghi outbox | Cần xác định transaction và retry |
| Gửi email | Gọi dịch vụ ngoài | Đơn có thể đã tồn tại; không được tạo đơn mới khi retry mù |

Bảng này là khung câu hỏi, không phải khẳng định mọi hệ thống phải dùng thứ tự đó. Một hệ thống có outbox có thể ghi đơn và event trong cùng transaction, rồi worker gửi event sau commit.

## 13. Dùng schema và migration để hiểu hợp đồng dữ liệu

Database thường chứa các quyết định lịch sử không còn thấy trong code mới:

- Cột nullable nhưng code mới giả định không null.
- Enum lưu bằng chuỗi cũ.
- Bảng có nhiều bản ghi trùng do thiếu unique constraint.
- Trigger hoặc stored procedure tạo thêm tác dụng phụ.
- Index phản ánh cách truy vấn quan trọng.
- Migration cũ cho biết cách schema đã tiến hóa.

Khi điều tra một đường chạy ghi dữ liệu, hãy xác định:

1. Bảng và cột được đọc/ghi.
2. Khóa chính, unique constraint và foreign key.
3. Nullable/default value.
4. Transaction và isolation level có liên quan.
5. Index phục vụ query chính.
6. Migration thay đổi schema theo thời gian.
7. Stored procedure/trigger nếu ứng dụng sử dụng.

Không nên chỉ dựa vào entity Java để kết luận schema thật. ORM mapping, migration và database đang chạy có thể khác nhau nếu môi trường bị lệch phiên bản.

### Dữ liệu cũ có thể làm lộ nhánh không còn được tạo mới

Code mới có thể chỉ tạo ba trạng thái, nhưng database cũ còn chứa `LEGACY_PENDING`. Code hiện tại có thể có fallback hoặc bỏ qua giá trị này. Khi sửa mapping, cần xem dữ liệu đang tồn tại và consumer đọc nó, không chỉ test object mới tạo.

Nếu cần dữ liệu production để xác minh, chỉ dùng quyền truy cập được phép và phương pháp bảo vệ dữ liệu. Không sao chép dữ liệu nhạy cảm vào log hoặc fixture.

## 14. Khảo sát phụ thuộc ngoài: timeout, retry, quota và contract

Một adapter HTTP có thể chỉ có một method `capturePayment`, nhưng hành vi phụ thuộc nhiều điều:

- URL và phiên bản API.
- Authentication/signature.
- Timeout kết nối và timeout toàn request.
- Retry policy và backoff.
- Idempotency key.
- Mapping HTTP status và payload lỗi.
- Rate limit/quota.
- Thay đổi contract từ provider.

Hãy tìm nơi cấu hình các yếu tố đó, không chỉ đọc method gọi HTTP. Nếu dùng SDK, xem phiên bản và cấu hình client. Nếu retry được cấu hình ở cả SDK, service và gateway, tổng số lần gọi có thể lớn hơn dự kiến.

### Hợp đồng ngoài có thể rộng hơn interface Java

```java
interface PaymentGateway {
    PaymentResult capture(
            String paymentReference,
            long amountVnd,
            String idempotencyKey
    );
}
```

Chữ ký Java chưa nói rõ:

- Cùng key được gọi lại có trả cùng kết quả không?
- Timeout có thể xảy ra sau khi provider đã thu tiền không?
- `PaymentResult` có thể là pending không?
- Lỗi nào có thể retry?
- Có yêu cầu đối soát không?

Những điều này phải được tìm trong tài liệu contract, adapter, test hoặc quan sát tích hợp. Đừng suy ra semantics chỉ từ tên method.

## 15. Vẽ bản đồ khảo sát đủ dùng

Một bản đồ tốt không cần mô tả mọi class. Nó cần làm rõ các điểm quan trọng và phần chưa biết.

Ví dụ:

```text
                    [Payment Provider]
                           |
                      webhook
                           |
                           v
[HTTP Gateway] --> [PaymentWebhookController]
                           |
                           v
                  [PaymentEventHandler]
                     |           |
                     v           v
              [PaymentStore] [OrderRepository]
                     |           |
                     +-----+-----+
                           |
                           v
                   [OrderStatePolicy]
                           |
                           v
                     [Outbox Writer]
                           |
                           v
                     [Message Broker]
                           |
                           v
                 [Fulfillment Consumer]
```

Bên cạnh sơ đồ, ghi chú:

- Đường nét liền: đã xác nhận bằng code hoặc trace.
- Đường nét đứt: giả thuyết hoặc phụ thuộc chưa xác nhận.
- Nút có nhãn riêng: nơi ghi trạng thái, quyết định quyền hoặc gọi hệ thống ngoài.
- Mỗi cạnh nên có tên dữ liệu hoặc event khi điều đó giúp hiểu.

Không cần tô màu nếu sơ đồ chỉ có vài thành phần. Điều quan trọng là **không trình bày giả thuyết như kiến trúc đã xác nhận**.

### Một bản đồ có thể có nhiều mức

- **Mức hệ thống:** service, database, broker, provider.
- **Mức ứng dụng:** controller/listener, application service, domain policy, adapter.
- **Mức dữ liệu:** input, mapping, trạng thái, event, output.
- **Mức vận hành:** retry, timeout, scheduler, queue, alert.

Chỉ đi sâu mức cần thiết cho câu hỏi đang giải quyết.

## 16. Ghi lại phát hiện theo mức độ chắc chắn

Một ghi chú khảo sát có thể chia thành:

| Nhận định | Trạng thái | Bằng chứng cần giữ |
| --- | --- | --- |
| Webhook đi vào `PaymentWebhookController` | Đã xác nhận | Route/handler và test tương ứng |
| Handler gọi `ConfirmPaymentService` | Đã xác nhận | Call site |
| Production đang dùng `HttpPaymentGateway` | Cần xác minh | Wiring/profile triển khai |
| Retry xảy ra sau timeout | Giả thuyết | Client config, log/trace hoặc integration test |
| Event được publish sau commit | Chưa rõ | Transaction/outbox implementation |
| Read model cập nhật bất đồng bộ | Cần xác minh | Consumer và metric lag |

Dùng nhãn như **đã xác nhận**, **giả thuyết**, **chưa rõ** giúp người khác biết đâu là dữ kiện và đâu là suy luận.

Không nên ghi một sơ đồ đẹp rồi bỏ mất nguồn. Gắn đường dẫn file, tên test, tên metric hoặc ID trace đã được phép chia sẻ để người sau có thể xác minh lại.

### Ghi lại cả điều chưa tìm thấy

Ví dụ:

- Chưa tìm được test cho webhook duplicate.
- Chưa xác nhận timeout có hủy tác vụ đang chạy hay không.
- Chưa biết provider có idempotency guarantee trong phiên bản API hiện tại.
- Chưa xác định trạng thái nào là nguồn sự thật cho báo cáo.

Đây là kết quả hữu ích. Nó giúp kế hoạch tiếp theo tập trung vào **khoảng trống kiến thức có ảnh hưởng đến quyết định**, thay vì tiếp tục tìm kiếm không định hướng.

## 17. Tránh các bẫy khi đọc mã hiện hữu

**Đọc từ file đầu tiên đến file cuối cùng.** Cách này không ưu tiên đường chạy liên quan; bắt đầu từ hành vi cần hiểu và lần theo bằng chứng.

**Tin tên lớp và tên method.** Tên có thể lỗi thời hoặc quá chung; xác nhận bằng call site, test và runtime.

**Chỉ đọc happy path.** Timeout, duplicate message, rollback và retry thường là nơi rủi ro thực sự xuất hiện.

**Chỉ xem controller.** Logic có thể nằm trong listener, scheduler, consumer hoặc stored procedure.

**Chỉ xem interface.** Wiring runtime, profile và cấu hình có thể chọn implementation khác.

**Chỉ dựa vào test hiện có.** Test có thể thiếu nhánh hoặc đóng băng bug; phân biệt hành vi hiện tại với hành vi mong muốn.

**Chỉ dựa vào log.** Log có thể thiếu, sampling hoặc ghi sai mức; kết hợp code, trace, metric và test.

**Coi mọi dependency là cùng mức rủi ro.** Một helper thuần túy khác với payment provider hoặc database dùng chung.

**Tạo sơ đồ quá chi tiết.** Bản đồ hàng trăm node nhanh chóng lỗi thời; giữ phần liên quan đến câu hỏi và các ranh giới quan trọng.

**Bỏ qua dữ liệu cũ.** Schema, enum và record lịch sử có thể làm lộ các nhánh không xuất hiện trong dữ liệu test mới.

**Sửa ngay khi vừa tìm thấy một code smell.** Ghi nhận và xác định mối liên hệ với vấn đề trước; đừng mở rộng phạm vi ngoài yêu cầu.

**Coi một lần trace là toàn bộ hành vi.** Trace thể hiện một lần thực thi; cần xét biến thể thành công, lỗi và tải khác nhau.

## 18. Quy trình khảo sát thực tế theo từng bước

Một quy trình vừa đủ có thể gồm:

### Bước 1 — Chốt câu hỏi và tác động

Viết hành vi đang sai, người dùng/thành phần bị ảnh hưởng và kết quả mong muốn. Xác định phần nào chưa thuộc phạm vi.

### Bước 2 — Tìm entry point

Tìm route, listener, scheduler, event hoặc command có liên quan. Liệt kê nhiều entry point nếu cùng tác động đến trạng thái.

### Bước 3 — Lần theo luồng dữ liệu

Theo input qua validation, mapping, policy, repository và output. Ghi nguồn sự thật, trạng thái suy ra và dữ liệu sao chép.

### Bước 4 — Lập bản đồ phụ thuộc

Ghi code dependency, runtime wiring, config, database, broker và provider. Xác nhận implementation đang dùng nếu điều đó ảnh hưởng kết luận.

### Bước 5 — Xác định đường quan trọng và nhánh lỗi

Theo dõi happy path cùng timeout, retry, duplicate, exception, rollback và tác vụ bất đồng bộ. Xếp ưu tiên theo tác động và rủi ro.

### Bước 6 — Đọc test và quan sát runtime

Tìm test đặc tả, integration test, log, metric và trace. Ghi rõ bằng chứng nào xác nhận điều gì và giới hạn của nó.

### Bước 7 — Ghi giả thuyết và khoảng trống

Tách dữ kiện đã xác nhận khỏi điều chưa rõ. Chọn những câu hỏi nếu được trả lời sẽ thay đổi quyết định sửa code.

### Bước 8 — Đề xuất thay đổi nhỏ có thể xác minh

Nêu file/ranh giới dự kiến, test cần thêm, side effect cần giữ và rủi ro còn lại. Chỉ mở rộng phạm vi khi bằng chứng mới cho thấy cần thiết.

### Bước 9 — Cập nhật bản đồ sau khi hiểu thêm

Nếu phát hiện luồng khác, ghi lý do cập nhật. Bản đồ là công cụ làm việc, không phải tài liệu bất biến cần hoàn hảo trước khi bắt đầu.

## 19. Mẫu ghi chú khảo sát cho một ticket

```markdown
# Khảo sát: [mô tả vấn đề]

## Hành vi quan sát được
- Triệu chứng:
- Điều kiện xuất hiện:
- Kết quả mong đợi:

## Phạm vi
- Entry point:
- Thành phần liên quan:
- Ngoài phạm vi hiện tại:

## Luồng chính đã xác nhận
1. ...
2. ...
3. ...

## Dữ liệu và trạng thái
- Nguồn đầu vào:
- Nơi lưu nguồn sự thật:
- Bản sao/cache/read model:
- Quy tắc chuyển trạng thái:

## Phụ thuộc
- Mã nguồn:
- Runtime wiring:
- Cấu hình:
- Database/broker/provider:

## Đường lỗi cần hiểu
- Timeout:
- Retry/duplicate:
- Transaction/rollback:
- Tác vụ bất đồng bộ:

## Bằng chứng
- Source:
- Tests:
- Logs/metrics/traces:
- Schema/migrations:

## Giả thuyết và điều chưa rõ
- Đã xác nhận:
- Giả thuyết:
- Chưa rõ:
- Người/nhóm cần xác nhận:

## Đề xuất bước tiếp
- Thay đổi nhỏ:
- Test cần có:
- Rủi ro và cách xác minh:
```

Không cần điền mọi mục cho mọi ticket. Mẫu giúp tránh bỏ sót các câu hỏi quan trọng khi đường chạy liên quan nhiều hệ thống.

## 20. Bài tập tình huống

### Tình huống A — Trạng thái đơn không đồng nhất

API chi tiết đơn hiển thị `PENDING`, trong khi cổng thanh toán báo giao dịch đã capture. Hệ thống có webhook, job đối soát và consumer cập nhật read model.

Hãy tìm các entry point, nguồn sự thật của trạng thái thanh toán, đường cập nhật order và read model. Bằng chứng nào giúp phân biệt lỗi ở database nguồn với độ trễ đồng bộ?

### Tình huống B — Timeout nhưng khách đã bị trừ tiền

Request capture timeout. Client retry và một số khách bị thu tiền hai lần.

Hãy lần theo idempotency key từ controller đến provider, xác định retry ở những tầng nào, trạng thái nào được lưu và cần kiểm tra contract gì. Nêu các câu hỏi cần trả lời trước khi sửa.

### Tình huống C — Một event có nhiều consumer

Event `OrderPaid` được publish bởi checkout và được consume bởi fulfillment, email và analytics. Một consumer xử lý trùng event.

Hãy vẽ producer/consumer map, tìm acknowledgment và retry policy, xác định consumer nào có side effect và test nào cần có cho duplicate event.

### Tình huống D — Test unit qua nhưng production sai

Unit test cho `PaymentStatusMapper` đều qua, nhưng production dùng implementation khác theo profile. Hãy lần từ interface đến wiring runtime, profile/configuration và adapter thực tế. Bạn cần bằng chứng nào để xác nhận implementation được deploy?

### Tình huống E — Dữ liệu cũ có trạng thái không còn dùng

Code mới chỉ biết `PENDING`, `PAID`, `CANCELLED`, nhưng database còn nhiều bản ghi `LEGACY_PENDING`. Hãy khảo sát migration, mapper, query filter, báo cáo và consumer. Cần kiểm tra dữ liệu nào trước khi xóa nhánh cũ?

### Tình huống F — Job định kỳ và API cùng cập nhật

API hủy đơn và scheduler tự động hủy đơn quá hạn có thể chạy cùng lúc. Hãy xác định entry point, trạng thái đọc/ghi, transaction và cơ chế chống cập nhật cạnh tranh. Những integration test nào mô tả đúng hành vi mong muốn?

### Tình huống G — Một ticket nhỏ mở rộng thành khảo sát lớn

Bạn bắt đầu sửa một điều kiện ở `OrderService`, nhưng phát hiện stored procedure, trigger và message consumer cũng cập nhật trạng thái. Hãy quyết định phạm vi khảo sát tiếp theo dựa trên câu hỏi nào; ghi rõ điều gì cần xác nhận trước khi thay đổi và phần nào có thể để ngoài phạm vi.

Với mỗi tình huống, trả lời theo chuỗi: **hành vi cần hiểu → entry point → luồng dữ liệu → phụ thuộc → đường thành công/lỗi → bằng chứng → giả thuyết còn lại → bước tiếp theo**.

## 21. Ghi nhớ

Khảo sát mã hiện hữu không phải là đọc hết repository. Đó là quá trình tạo một mô hình đủ chính xác về **hành vi, dữ liệu, phụ thuộc và các đường chạy quan trọng** để đưa ra thay đổi an toàn.

- Bắt đầu từ một câu hỏi và hành vi quan sát được; giới hạn phạm vi theo tác động.
- Tìm tất cả entry point liên quan, không chỉ controller hoặc method có tên gần ticket.
- Lần theo dữ liệu từ đầu vào đến nơi lưu và các consumer đọc lại.
- Phân biệt dependency trực tiếp, runtime wiring, cấu hình và contract dữ liệu.
- Xem cả đường thành công lẫn timeout, retry, duplicate, rollback và bất đồng bộ.
- Dùng test, log, metric, trace, schema và migration như các nguồn bằng chứng bổ sung.
- Characterization test ghi nhận hành vi hiện tại; cần phân biệt nó với hành vi nghiệp vụ mong muốn.
- Ghi rõ điều đã xác nhận, giả thuyết và câu hỏi chưa trả lời; không biến suy luận thành sự thật.
- Ưu tiên khảo sát theo tác động nghiệp vụ, rủi ro và khả năng thay đổi.
- Chọn bước sửa nhỏ có thể kiểm chứng, giữ bất biến và ranh giới side effect.

Khi hiểu được **đường chạy nào thực sự quyết định kết quả, dữ liệu đến từ đâu, phụ thuộc nào có thể thất bại và bằng chứng nào xác nhận hành vi**, bạn có thể thay đổi mã hiện hữu với ít phỏng đoán hơn và bảo vệ tốt hơn những phần đang hoạt động.
