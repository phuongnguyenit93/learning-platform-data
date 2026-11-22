# Field authorization: phân quyền đọc và thay đổi từng trường dữ liệu

Trong chương **Authorization Rules**, field authorization là việc quyết định một chủ thể được đọc hoặc thay đổi những trường nào của một đối tượng cụ thể, trong ngữ cảnh và trạng thái nghiệp vụ hiện tại. Quyền truy cập một đơn hàng không có nghĩa được xem giá vốn, sửa đơn giá hay tự đánh dấu đơn đã thanh toán.

Trong module bảo vệ logic nghiệp vụ, phân quyền theo trường giúp ngăn sửa giá, thay chủ sở hữu, giả bằng chứng phê duyệt và làm lộ dữ liệu nội bộ. Cơ chế này phải kết hợp với quyền theo đối tượng, state machine, business invariants và transaction; một danh sách trường được phép ở giao diện không đủ bảo vệ dữ liệu phía máy chủ.

Bài học dùng ví dụ đơn hàng. Các quy tắc trong ví dụ được lựa chọn để minh họa cách thiết kế, không phải quy tắc mặc định cho mọi hệ thống bán hàng.

Sau bài này, bạn có thể:

- Phân biệt quyền trên đối tượng, quyền theo trường và kiểm tra giá trị đầu vào.
- Thiết kế hợp đồng đọc và ghi chỉ chứa dữ liệu người gọi được phép sử dụng.
- Ngăn mass assignment và cập nhật trái phép qua thuộc tính lồng nhau hoặc patch.
- Bảo vệ trường nhạy cảm trên API đọc, tìm kiếm, xuất dữ liệu và cache.
- Kiểm thử quyền theo ma trận chủ thể, đối tượng, trường và thao tác.

## 1. Được sửa đơn hàng không có nghĩa được sửa mọi thuộc tính

Giả sử một khách hàng được phép đổi ghi chú của đơn nháp. Họ gửi thêm các trường:

```http
PATCH /orders/o-123
Content-Type: application/json

{
  "customerNote": "Giao trong giờ hành chính",
  "unitPrice": 1,
  "total": 1,
  "paymentStatus": "PAID",
  "customerId": "customer-other",
  "tenantId": "tenant-other"
}
```

Nếu máy chủ lấy toàn bộ body rồi gán vào entity, việc kiểm tra “đơn này thuộc khách hàng hiện tại” có thể vẫn vượt qua trước khi các trường chủ sở hữu bị thay đổi. Sau đó đối tượng được lưu với giá, trạng thái hoặc phạm vi tổ chức do client quyết định.

Đây là một dạng mass assignment: dữ liệu người gọi không được phép điều khiển bị đưa vào mô hình lưu trữ thông qua cơ chế ánh xạ quá rộng. Tuy nhiên, field authorization rộng hơn việc chống mass assignment; nó còn bao gồm quyền đọc, quyền theo trạng thái và quyền dùng thuộc tính trong các phép truy vấn.

Một trường hợp khác xảy ra ở chiều đọc:

```json
{
  "id": "o-123",
  "total": 1200000,
  "internalCost": 600000,
  "fraudScore": 82,
  "internalInvestigationNote": "Thông tin chỉ dành cho nhóm xử lý"
}
```

Khách hàng có thể được xem đơn nhưng không được xem những trường nội bộ này. Ẩn chúng bằng CSS không thay đổi việc API đã gửi dữ liệu tới client.

## 2. Ba câu hỏi khác nhau cần được kiểm tra

| Lớp kiểm tra | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Quyền theo đối tượng | Chủ thể có được thao tác trên đối tượng này không? | Khách hàng chỉ sửa đơn của mình trong đúng tenant |
| Quyền theo trường | Trong thao tác đó, được đọc hoặc đổi trường nào? | Được đổi ghi chú nhưng không đổi `paymentStatus` |
| Validation và invariant | Giá trị và tổ hợp sau thay đổi có hợp lệ không? | Ghi chú không vượt giới hạn; tổng tiền khớp các dòng hàng |

Một đơn giá bằng `1` có thể hợp lệ về kiểu và khoảng giá trị kỹ thuật, nhưng khách hàng vẫn không có quyền đặt đơn giá. Ngược lại, người được sửa ghi chú vẫn có thể gửi một chuỗi quá dài và bị từ chối validation.

Có thể diễn đạt chính sách bằng hai quyết định độc lập:

```text
canRead(actor, object, field, context)

canWrite(actor, object, field, operation, proposedValue, context)
```

Quyết định ghi có thể phụ thuộc loại thao tác: đặt giá trị, xóa giá trị, thêm phần tử hoặc thay một quan hệ. Việc được đọc một trường không tự cấp quyền sửa; việc được gửi một bí mật mới cũng không nhất thiết cho phép đọc lại bí mật đã lưu.

Các dữ liệu dùng để quyết định quyền phải đến từ ngữ cảnh xác thực và đối tượng có thẩm quyền. Không kiểm tra quyền dựa trên `tenantId`, `ownerId` hoặc trạng thái mà chính request đang muốn thay đổi.

## 3. Ví dụ chính sách trường của đơn hàng

Giả sử hệ thống có các quy tắc:

- Khách hàng đọc thông tin phù hợp trên đơn của mình.
- Khách hàng chỉ sửa ghi chú và địa chỉ giao hàng khi đơn còn `DRAFT`.
- Thay số lượng là một hành động riêng trên dòng hàng, buộc tính lại giá và điều kiện liên quan.
- Đơn giá, tổng tiền và mức giảm thực tế do máy chủ tính từ dữ liệu và quy tắc áp dụng.
- Nhân sự nghiệp vụ được đọc hoặc ghi dữ liệu nội bộ trong đúng phạm vi được giao.
- Trạng thái thanh toán chỉ thay đổi qua luồng xử lý thanh toán được xác thực.

| Trường | Quyền đọc trong ví dụ | Quyền ghi trong ví dụ |
| --- | --- | --- |
| `id`, `state`, `version` | Chủ thể được đọc đơn | Không cập nhật tự do; version đầu vào là điều kiện so sánh |
| `customerNote` | Khách sở hữu và nhân sự hỗ trợ có quyền trên đơn | Khách sở hữu khi `DRAFT`; nhân sự theo lệnh nghiệp vụ riêng nếu được cấp quyền |
| `shippingAddress` | Khách sở hữu và bộ phận cần dữ liệu giao hàng | Khách sở hữu khi `DRAFT`, sau khi kiểm tra địa chỉ |
| `items[].quantity` | Chủ thể được đọc các dòng hàng tương ứng | Qua lệnh đổi số lượng, có kiểm tra dòng hàng và tính lại nghiệp vụ |
| `items[].unitPrice`, `total`, `discountAmount` | Khách được xem giá áp dụng cho đơn của mình | Máy chủ tính; không nhận trực tiếp qua patch của khách |
| `couponCode` đề xuất | Theo hợp đồng của thao tác áp mã | Client có thể đề xuất mã; máy chủ quyết định tính hợp lệ và mức giảm |
| `paymentStatus` | Khách được xem trạng thái thanh toán phù hợp | Chỉ luồng thanh toán có thẩm quyền |
| `internalCost` | Nhóm tài chính có quyền với đơn | Quy trình dữ liệu giá vốn có kiểm soát, không qua patch đơn chung |
| `fraudScore`, ghi chú điều tra | Nhóm xử lý rủi ro có phạm vi phù hợp | Luồng đánh giá hoặc điều tra được cấp quyền |
| `tenantId`, `customerId` | Chỉ trả khi cần cho hợp đồng và được phép | Máy chủ xác định hoặc hành động quản trị riêng có điều kiện |

Các quy tắc này là theo ngữ cảnh. Một danh sách tĩnh “trường này sửa được” không đủ nếu trường chỉ sửa được khi đối tượng còn nháp, thuộc đúng khách hàng và chưa bị thay đổi phiên bản.

Đừng coi vai trò nhân viên là quyền sửa mọi trường. Người hỗ trợ giao hàng không mặc nhiên được sửa giá hoặc đánh dấu đã thanh toán.

## 4. Thiết kế đầu vào theo tập trường cho phép

Một cách bảo vệ cơ bản là tách mô hình lưu trữ khỏi mô hình lệnh đầu vào:

```text
Entity Order
  chứa trạng thái, chủ sở hữu, giá, thanh toán và dữ liệu nội bộ

CustomerDraftPatch
  chỉ chứa ghi chú, địa chỉ và điều kiện phiên bản
```

Không bind trực tiếp body của client vào entity rồi mới cố gắng khôi phục các trường cấm. Trong khoảng giữa, giá trị đã gán có thể bị validation, listener hoặc mã nghiệp vụ sử dụng.

Không nên sao chép toàn bộ body rồi xóa vài trường nguy hiểm. Khi entity được bổ sung `approvedBy`, `riskOverride` hoặc một quan hệ mới, danh sách cấm rất dễ bị thiếu. Tập trường cho phép cần được định nghĩa rõ cho từng lệnh.

Một yêu cầu sửa ghi chú có thể chỉ cần:

```http
PATCH /orders/o-123/customer-details
Content-Type: application/json

{
  "expectedVersion": 7,
  "customerNote": "Gọi trước khi giao"
}
```

Hợp đồng phải quyết định cách xử lý trường lạ hoặc trường chỉ đọc. Với API lệnh cần phản hồi rõ, có thể từ chối toàn bộ payload chứa trường không được hỗ trợ, trước khi cập nhật. Không áp dụng một phần mà không thông báo, khiến client tưởng mọi trường đã được chấp nhận.

Tập trường đầu vào vẫn chưa thay thế quyền theo đối tượng và trạng thái. Cùng một DTO hợp lệ không cho phép khách A sửa đơn của khách B hoặc sửa đơn đã chuyển sang bước không được phép.

## 5. Phân biệt trường không gửi với trường được đặt thành null

Trong một bản cập nhật từng phần, ba ý định có thể khác nhau:

```text
không gửi customerNote  → giữ nguyên
gửi customerNote = ""   → đặt chuỗi rỗng nếu hợp đồng cho phép
gửi customerNote = null → xóa giá trị nếu hợp đồng cho phép
```

Nếu DTO chỉ có một trường nullable, máy chủ có thể không biết người dùng không gửi hay chủ động muốn xóa. Điều này đặc biệt nguy hiểm với thuộc tính có ý nghĩa bảo vệ như người nhận, phạm vi quyền hoặc dữ liệu định danh.

Một kiểu nội bộ có thể biểu diễn sự hiện diện:

```java
record PatchField<T>(boolean present, T value) {
    static <T> PatchField<T> absent() {
        return new PatchField<>(false, null);
    }

    static <T> PatchField<T> supplied(T value) {
        return new PatchField<>(true, value);
    }
}

record AddressInput(
        String recipientName,
        String street,
        String city,
        String countryCode) {
}

record CustomerDraftPatch(
        long expectedVersion,
        PatchField<String> customerNote,
        PatchField<AddressInput> shippingAddress) {
}
```

Ví dụ dùng record của Java 16 trở lên. Bộ phân tích đầu vào phải tạo đúng `absent` hoặc `supplied` theo dữ liệu thật; đoạn mã không tự cấu hình một thư viện JSON.

Nếu địa chỉ bắt buộc, lệnh gửi `shippingAddress = null` phải bị từ chối dù khách được sửa địa chỉ. Quyền ghi một trường không có nghĩa mọi phép xóa hoặc mọi giá trị của trường đều hợp lệ.

`expectedVersion` là phiên bản người dùng đã xem, không phải giá trị version mới mà client được quyền ghi vào cơ sở dữ liệu.

## 6. Minh họa Java: kiểm tra quyền trên tập trường được yêu cầu

Đoạn mã sau chỉ áp dụng cho endpoint sửa ghi chú và địa chỉ đơn nháp của khách hàng. Dữ liệu actor được dựng từ ngữ cảnh đã xác thực; dữ liệu order được tải từ máy chủ.

```java
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

enum OrderState {
    DRAFT, SUBMITTED, FULFILLING, COMPLETED, CANCELLED
}

enum OrderField {
    CUSTOMER_NOTE,
    SHIPPING_ADDRESS,
    ITEM_QUANTITY,
    UNIT_PRICE,
    TOTAL,
    PAYMENT_STATUS,
    TENANT_ID,
    CUSTOMER_ID,
    INTERNAL_COST,
    FRAUD_SCORE
}

enum Capability {
    EDIT_OWN_DRAFT_CUSTOMER_DETAILS
}

record CustomerActor(
        UUID tenantId,
        UUID customerId,
        Set<Capability> capabilities) {
}

record OrderAccessView(
        UUID tenantId,
        UUID customerId,
        OrderState state) {
}

final class CustomerFieldPolicy {
    private static final Set<OrderField> WRITABLE = Set.of(
            OrderField.CUSTOMER_NOTE,
            OrderField.SHIPPING_ADDRESS);

    private CustomerFieldPolicy() {
    }

    static void requireWritable(
            CustomerActor actor,
            OrderAccessView order,
            Set<OrderField> requestedFields) {
        Objects.requireNonNull(actor);
        Objects.requireNonNull(order);
        Set<OrderField> requested = Set.copyOf(requestedFields);

        require(Objects.requireNonNull(actor.tenantId())
                .equals(order.tenantId()));
        require(Objects.requireNonNull(actor.customerId())
                .equals(order.customerId()));
        require(actor.capabilities().contains(
                Capability.EDIT_OWN_DRAFT_CUSTOMER_DETAILS));
        require(order.state() == OrderState.DRAFT);
        require(WRITABLE.containsAll(requested));
    }

    private static void require(boolean allowed) {
        if (!allowed) {
            throw new SecurityException("Field update is not allowed");
        }
    }
}
```

`requestedFields` phải được suy ra từ sự hiện diện thực tế của các trường đầu vào sau bước kiểm tra schema. Không cho client gửi một danh sách “tôi chỉ sửa ghi chú” trong khi mapper vẫn áp dụng các thuộc tính khác của body.

Hàm không kiểm tra nội dung địa chỉ, độ dài ghi chú, version hoặc transaction. Những trách nhiệm đó vẫn cần ở luồng thực thi. Với nhân sự nội bộ, dùng chính sách và lệnh phù hợp riêng; không bỏ kiểm tra bằng một nhánh `if admin then allow all`.

Tập cho phép không chứa `ITEM_QUANTITY` vì ví dụ sử dụng lệnh đổi số lượng riêng. Điều đó không khẳng định trường này vĩnh viễn không sửa được; nó xác định rõ endpoint nào chịu trách nhiệm kiểm tra và tính lại hệ quả.

## 7. Dữ liệu lồng nhau và quan hệ cũng cần phân quyền

Cho phép sửa `shippingAddress` không có nghĩa cho phép mọi thuộc tính phía dưới:

```json
{
  "shippingAddress": {
    "street": "Đường mới",
    "verifiedBy": "staff-9",
    "riskExempt": true,
    "customerId": "customer-other"
  }
}
```

Mô hình địa chỉ đầu vào phải chỉ chứa các giá trị người dùng được đề xuất. Những cờ xác minh và quan hệ chủ sở hữu do máy chủ quản lý không được xuất hiện trong lệnh sửa thông thường.

Nếu client chọn `savedAddressId`, máy chủ phải xác minh địa chỉ đó thuộc phạm vi được dùng cho đơn. Quyền sửa một trường tham chiếu không cấp quyền gắn bất kỳ đối tượng nào biết ID vào đơn.

Tương tự, với dòng hàng:

```http
POST /orders/o-123/items/item-7/change-quantity
```

Máy chủ cần kiểm tra `item-7` thực sự thuộc `o-123`, đúng tenant, được sửa trong trạng thái hiện tại và không vượt các quy tắc số lượng. Không chỉ xác thực riêng đơn và riêng dòng hàng rồi bỏ qua quan hệ giữa chúng.

Thay toàn bộ một mảng có thể ngầm xóa hoặc sửa các phần tử và trường không xuất hiện trực tiếp trong payload. Hợp đồng cần kiểm tra toàn bộ hệ quả hoặc dùng lệnh theo ID ổn định thay vì cho phép thay một cấu trúc entity tùy ý.

## 8. Patch tổng quát cần kiểm tra từng phép toán

Nếu API hỗ trợ danh sách phép patch như `add`, `replace`, `remove`, `copy`, `move` hoặc `test`, quyền không chỉ là danh sách đường dẫn đích.

| Phép toán | Điều cần kiểm tra |
| --- | --- |
| `add`, `replace` | Quyền ghi ở đích, kiểu dữ liệu, giá trị và hệ quả lên cấu trúc |
| `remove` | Quyền xóa và invariant sau khi trường hoặc phần tử biến mất |
| `copy` | Quyền đọc nguồn và ghi đích; không cho sao chép trường bí mật ra trường công khai |
| `move` | Quyền đọc và loại bỏ ở nguồn, quyền ghi đích, cùng các ràng buộc quan hệ |
| `test` | Quyền đọc hoặc kiểm tra thông tin tương ứng; kết quả đúng/sai có thể làm lộ dữ liệu |

Ví dụ nguy hiểm:

```json
[
  {
    "op": "copy",
    "from": "/internalInvestigationNote",
    "path": "/customerNote"
  }
]
```

Chỉ kiểm tra khách được ghi `/customerNote` sẽ bỏ sót việc đọc nguồn nội bộ. Tương tự, `test` trên một trường nhạy cảm có thể trở thành cách đoán giá trị dù phản hồi không trả trực tiếp trường đó.

Đường dẫn cần được phân tích theo đúng cú pháp và chuyển về biểu diễn thống nhất. Không kiểm tra bằng `startsWith("/shippingAddress")` vì một tên trường khác hoặc một đường dẫn được giải mã khác nhau giữa các lớp có thể không có cùng ý nghĩa. Các ký hiệu escape của đường dẫn và cách tham chiếu mảng phải được xử lý nhất quán.

Không dùng vị trí mảng làm bằng chứng sở hữu một phần tử. Với mảng có thể thay đổi đồng thời, cần version và quan hệ ID để bảo đảm thao tác đang áp dụng lên đúng dòng hàng đã được kiểm tra.

Có thể áp dụng patch lên một bản ứng viên trong bộ nhớ để kiểm tra hệ quả cuối cùng, nhưng vẫn phải xác minh từng phép toán. Chỉ so sánh trạng thái trước–sau sẽ bỏ sót phép `test` làm lộ dữ liệu hoặc chuỗi thao tác có truy cập nguồn cấm rồi khôi phục kết quả.

## 9. Phân quyền đọc bằng mô hình phản hồi rõ ràng

Không trả trực tiếp entity lưu trữ với hy vọng client chỉ đọc những trường giao diện cần. Một mô hình phản hồi cho khách có thể chỉ chứa:

```java
record CustomerOrderResponse(
        UUID id,
        String state,
        long totalMinor,
        String currency,
        String customerNote,
        long version) {
}
```

Mapper lấy dữ liệu đã được phép đọc để tạo DTO này. Không có `internalCost`, `fraudScore` hoặc ghi chú điều tra trong kiểu phản hồi của khách. Các endpoint nghiệp vụ nội bộ dùng projection phù hợp với quyền của nhân sự và phạm vi đối tượng.

Tách mô hình đầu vào và đầu ra. Một trường được trả cho khách như `total` vẫn có thể hoàn toàn không được khách ghi. Dùng cùng một DTO hai chiều dễ làm quyền đọc vô tình trở thành quyền sửa.

Nếu hỗ trợ `fields=id,total,internalCost`, tập được yêu cầu chỉ là đề xuất của client. Máy chủ phải đối chiếu với tập đọc được, rồi từ chối hoặc trả tập hợp lệ theo hợp đồng rõ ràng. Không đưa thuộc tính vào response chỉ vì client biết tên trường.

Với API truy vấn linh hoạt, kiểm tra cả các trường lồng nhau, quan hệ mở rộng và từng đối tượng được tải. Quyền đọc node đơn hàng không tự cấp quyền xem mọi node khách hàng, giao dịch hoặc ghi chú mà nó liên kết tới.

Việc bỏ hẳn một trường, trả `null` hoặc trả một giá trị đã che cần được quy định theo ngữ nghĩa của API. Không để client hiểu `null` là dữ liệu thật trong khi thực tế người gọi không có quyền đọc.

## 10. Lọc, sắp xếp và tổng hợp cũng có thể làm lộ trường

Ẩn `internalCost` khỏi JSON chưa đủ nếu khách được tự gửi:

```http
GET /orders?internalCostLessThan=700000
GET /orders?sort=internalCost
```

Sự xuất hiện của một đơn trong kết quả, thứ tự của nó hoặc tổng số bản ghi có thể tiết lộ thông tin về giá vốn. Một API có thể vô tình cung cấp kênh đoán thuộc tính dù không bao giờ trả thuộc tính đó.

Cần chính sách riêng cho các phép sử dụng:

- Trường được phép đưa vào bộ lọc hoặc điều kiện tìm kiếm.
- Trường được phép dùng để sắp xếp.
- Trường được phép nhóm, tính tổng, đếm theo nhóm hoặc đưa vào báo cáo.
- Dữ liệu được phép tác động tới gợi ý và kết quả xác thực trả cho client.

Các phép truy vấn nội bộ có thể dùng trường ẩn khi chủ thể có quyền phù hợp. Vấn đề là không để người không có quyền tự điều khiển một phép truy vấn trở thành công cụ suy luận dữ liệu.

Metadata cũng cần được xét. `totalCount`, thông báo lỗi chi tiết, giá trị `ETag` hoặc thời điểm sửa đổi có thể tiết lộ rằng dữ liệu ẩn đã tồn tại hoặc thay đổi. Hệ thống nên đánh giá những tín hiệu đó theo hợp đồng phản hồi và mức nhạy cảm, thay vì mặc định mọi metadata đều vô hại.

## 11. Ghi dữ liệu trong cùng ranh giới với kiểm tra quyền

Một luồng cập nhật an toàn có thể thực hiện:

```text
xác thực chủ thể và cấu trúc lệnh
chuẩn hóa tên trường và xác định tập trường thật sự được yêu cầu
từ chối thuộc tính không được hỗ trợ hoặc payload mơ hồ

BEGIN TRANSACTION
  tải đơn trong phạm vi tenant đã được xác minh
  bảo vệ phiên bản bằng khóa hoặc cập nhật có điều kiện
  kiểm tra quyền theo đối tượng từ dữ liệu đã lưu
  kiểm tra trạng thái và quyền trên từng trường, từng phép toán
  kiểm tra giá trị và các quan hệ được tham chiếu
  tạo trạng thái ứng viên chỉ từ các thay đổi được phép
  tính lại giá trị do máy chủ quản lý nếu hành động yêu cầu
  kiểm tra business invariants
  lưu đúng các thuộc tính được phép và tăng version
  ghi audit, outbox hoặc kết quả idempotency khi cần
COMMIT

tạo phản hồi theo quyền đọc, không serialize toàn bộ entity
```

Ví dụ SQL cho lệnh chỉ đổi ghi chú:

```sql
UPDATE orders
SET customer_note = :validated_note,
    version = version + 1
WHERE id = :order_id
  AND tenant_id = :authorized_tenant_id
  AND customer_id = :authenticated_customer_id
  AND state = 'DRAFT'
  AND version = :expected_version;
```

Câu lệnh không có chỗ để client ghi `total`, `tenant_id` hoặc `payment_status`. Phải kiểm tra số hàng tác động: không cập nhật hàng nào không phải thành công và không tự cho biết chính xác đối tượng không tồn tại, khác quyền hay đã đổi trạng thái.

SQL này không thay thế toàn bộ policy. Nó minh họa việc ràng buộc cập nhật với đối tượng và phiên bản đã xét. Các điều kiện quyền khác cần được kiểm tra theo nguồn có thẩm quyền và yêu cầu nhất quán của hệ thống.

Với cập nhật ghi chú không được gửi, không chạy câu lệnh đặt ghi chú thành null. Bộ thực thi lệnh phải giữ đúng sự khác nhau giữa không yêu cầu thay đổi và yêu cầu xóa.

## 12. Business invariants vượt ra ngoài một trường được phép

Giả sử khách được đổi `items[].quantity`. Sau khi đổi từ một sản phẩm thành mười sản phẩm, hệ thống phải tính lại tổng tiền, điều kiện giảm giá, phí liên quan và các ràng buộc tài nguyên theo nghiệp vụ.

Không nhận đồng thời `quantity = 10` và `total = 1000` rồi coi chúng là một cặp hợp lệ vì cả hai đúng kiểu số. Một trường đầu vào có thể là ý định, còn trường khác là kết quả máy chủ phải tự tính.

Tương tự:

- Đổi địa chỉ có thể ảnh hưởng vùng giao, phí vận chuyển hoặc điều kiện áp dụng giá.
- Đổi tài khoản nhận trên một đề nghị chi có thể làm mất hiệu lực phê duyệt cũ.
- Đổi đơn vị của đối tượng có thể làm thay đổi người được phép duyệt.
- Đổi quyền của người dùng có thể tạo tổ hợp quyền bị cấm dù từng quyền riêng lẻ được biết đến.

Nếu thay đổi ảnh hưởng nội dung đã duyệt hoặc đã chốt, phải chặn ở trạng thái hiện tại hoặc đi qua một quy trình sửa đổi có đánh giá lại. Cho phép sửa trường nhưng giữ mọi bằng chứng cũ có thể trở thành đường vòng nghiệp vụ.

Vì vậy, field authorization xác định phạm vi một chủ thể được đề xuất thay đổi. Service nghiệp vụ còn phải xác định hệ quả, dữ liệu phụ thuộc và điều kiện commit toàn bộ thay đổi.

## 13. Các đường đọc và ghi ngoài endpoint chính

Chính sách phải theo dữ liệu qua các đường có thể truy cập nó:

| Đường truy cập | Điều cần bảo vệ |
| --- | --- |
| API danh sách và API chi tiết | Cùng giới hạn đối tượng và trường phù hợp |
| Xuất CSV hoặc báo cáo | Không xuất cột ẩn chỉ vì người dùng có quyền xem màn hình |
| Tác vụ xuất bất đồng bộ | Xác định quyền ở lúc tạo, lúc chạy và lúc tải theo chính sách; bảo vệ tệp kết quả |
| Email, thông báo, webhook | Chỉ gửi dữ liệu mà người nhận hoặc hệ thống nhận được phép biết |
| API hàng loạt | Kiểm tra từng đối tượng và trường; quy định rõ tính nguyên tử hoặc kết quả từng mục |
| Công cụ quản trị và import | Không để một mapper tổng quát bỏ qua quyền trường và invariant |
| Audit và log | Không ghi toàn bộ giá trị bí mật chỉ để giải thích thay đổi |
| Worker hoặc consumer | Không coi service account là quyền sửa mọi thuộc tính |

Nếu một thao tác hàng loạt gồm nhiều đơn ở các trạng thái khác nhau, việc được sửa đơn đầu tiên không cấp quyền cho cả lô. Trả kết quả riêng hoặc rollback cả lô theo hợp đồng, nhưng không được âm thầm cập nhật mục bị cấm.

Một service account nên được phép thực hiện loại lệnh cụ thể trong phạm vi phù hợp. Việc luồng thanh toán được cập nhật `paymentStatus` không đồng nghĩa nó được thay chủ sở hữu đơn hoặc sửa ghi chú điều tra.

## 14. Cache, che dữ liệu và lỗi phản hồi

### Cache theo đúng phạm vi quyền

Nếu phản hồi nội bộ chứa giá vốn được cache chỉ theo `orderId`, request sau từ khách hàng có thể nhận nhầm cùng nội dung. Cache cần phân biệt phạm vi tenant, đối tượng và ngữ cảnh quyền phù hợp, hoặc cache dữ liệu nội bộ rồi áp dụng projection an toàn cho từng lần trả.

Khi quyền hoặc chính sách thay đổi, cần quy tắc hết hạn hoặc vô hiệu hóa phù hợp. Một cache key có tên “private” không tự tạo ra bảo đảm phân quyền.

### Che dữ liệu ở phía máy chủ

Nếu người dùng chỉ được thấy một phần số điện thoại hoặc địa chỉ, máy chủ nên tạo đúng biểu diễn được phép. Gửi nguyên giá trị rồi che trên giao diện vẫn làm lộ dữ liệu qua mạng, công cụ phát triển và các client khác.

Che giá trị không tự bảo vệ khỏi mọi phép suy luận. Cần xét cả bộ lọc, tìm kiếm và các biến thể endpoint có thể trả bản đầy đủ.

### Lỗi không được trở thành API đọc bí mật

Thông báo validation hoặc xung đột có thể vô tình chứa entity đầy đủ, giá trị cũ hoặc lý do điều tra nội bộ. Lỗi trả cho client phải theo cùng nguyên tắc dữ liệu tối thiểu.

Có thể dùng mã lỗi ổn định để client xử lý trường không hỗ trợ hoặc thao tác không được phép. Không cần liệt kê các trường nội bộ nhạy cảm mà người gọi chưa được phép biết chỉ để giải thích một payload bị từ chối.

## 15. Kiểm thử theo ma trận chủ thể, đối tượng và trường

Trước hết, lập một ma trận gồm:

```text
chủ thể: khách sở hữu, khách khác, nhân viên đúng phạm vi, nhân viên khác phạm vi
đối tượng: cùng tenant, khác tenant, đúng hoặc sai quan hệ cha–con
trạng thái: DRAFT, SUBMITTED, đang thực hiện, đã kết thúc
thao tác: đọc, đặt giá trị, xóa, thêm phần tử, lọc, xuất dữ liệu
trường: công khai, người dùng được sửa, máy chủ quản lý, nội bộ nhạy cảm
```

Các ca ghi quan trọng:

| Ca kiểm thử | Kết quả cần giữ |
| --- | --- |
| Khách sửa ghi chú đơn nháp của mình | Chỉ ghi chú và version thay đổi theo lệnh |
| Cùng khách sửa ghi chú đơn đã chốt | Bị chặn theo trạng thái |
| Khách sửa đơn người khác hoặc tenant khác | Không thay đổi dữ liệu |
| Gửi thêm giá, tổng tiền, chủ sở hữu hoặc trạng thái thanh toán | Không trường cấm nào được áp dụng |
| Sửa địa chỉ kèm cờ xác minh lồng nhau | Không ghi bằng chứng xác minh giả |
| Dùng địa chỉ hoặc dòng hàng của đối tượng khác | Bị chặn theo quan hệ và quyền đối tượng |
| Bỏ trường, gửi null và gửi chuỗi rỗng | Có ngữ nghĩa khác nhau đúng hợp đồng |
| Payload có tên trùng, alias hoặc biểu diễn đường dẫn mơ hồ | Bị từ chối hoặc được phân tích thống nhất theo hợp đồng; không có lớp kiểm tra và lớp ghi hiểu khác nhau |
| Patch xóa trường bắt buộc | Không tạo trạng thái vi phạm invariant |
| Patch copy từ trường bí mật ra trường đọc được | Không làm lộ dữ liệu nguồn |
| Patch test trên trường không được đọc | Không cung cấp kết quả đoán giá trị trái phép |

Các ca đọc quan trọng:

- Response khách hàng không chứa giá vốn, điểm rủi ro hoặc ghi chú điều tra.
- API danh sách, chi tiết, mở rộng quan hệ và xuất dữ liệu cùng tôn trọng policy.
- Client yêu cầu cột nhạy cảm qua tham số chọn trường không được nhận cột đó.
- Filter, sort, aggregate và thông báo lỗi không trở thành đường đọc thuộc tính cấm.
- Phản hồi đã cache cho nhân viên không bị trả cho khách hàng hoặc tenant khác.
- Log, tệp xuất và webhook không chứa bản entity đầy đủ ngoài quyền người nhận.

Nên xác minh trực tiếp cấu trúc JSON và dữ liệu lưu sau request. Chỉ kiểm tra giao diện không hiển thị một cột hoặc API trả mã lỗi sẽ bỏ sót nhiều trường hợp.

## 16. Kiểm thử tranh chấp và theo dõi thay đổi quyền

Các ca tích hợp cần chú ý:

| Kịch bản | Kết quả cần giữ |
| --- | --- |
| Đơn chuyển khỏi `DRAFT` trong lúc khách đang sửa | Cập nhật cũ không vượt qua guard trạng thái hoặc version |
| Hai lần sửa cùng dựa trên một version | Không âm thầm ghi đè trái hợp đồng cập nhật |
| Đổi quan hệ sở hữu hoặc phạm vi trong lúc thao tác | Quyết định quyền không bị áp dụng nhầm lên trạng thái mới |
| Quyền nhân sự bị thu hồi trước một thao tác nhạy cảm | Hành vi khớp ranh giới hiệu lực quyền mà hệ thống quy định |
| Lệnh đổi số lượng bị lỗi sau khi chuẩn bị tính lại | Không để số lượng và tổng tiền lệch nhau sau commit |
| Retry một lệnh có tác dụng phụ | Không lặp hiệu ứng; nếu có idempotency thì dấu vân tay ràng buộc đúng đối tượng và lệnh |
| Tác vụ xuất chạy hoặc được tải sau khi quyền thay đổi | Áp dụng chính sách đã định, không để URL tệp trở thành quyền đọc vô thời hạn |

Đối với quyền phụ thuộc dữ liệu có thể thay đổi, cần chọn rõ cách đọc, version, khóa hoặc nguồn quyết định phù hợp. Một hàm `canEdit()` chạy trước transaction không tự bảo vệ khỏi thay đổi giữa kiểm tra và ghi.

Audit nên ghi chủ thể, đối tượng, loại lệnh, tên các trường thay đổi, phiên bản trước–sau và kết quả. Với dữ liệu nhạy cảm, ghi giá trị cũ–mới chỉ khi thật sự cần và trong nơi lưu có quyền truy cập phù hợp; không mặc định dump toàn bộ payload.

Các lần cố sửa trường máy chủ quản lý, truy cập thuộc tính nội bộ hoặc dùng quan hệ chéo tenant là tín hiệu có ích để điều tra. Chúng không thay thế quyết định từ chối tại thời điểm xử lý.

## 17. Cách áp dụng field authorization vào một API

1. Liệt kê các trường của đối tượng và phân loại theo ý nghĩa nghiệp vụ, nguồn quyết định và độ nhạy cảm.
2. Viết quyền đọc và quyền ghi riêng cho từng chủ thể, quan hệ đối tượng và trạng thái liên quan.
3. Tạo DTO hoặc lệnh đầu vào với tập trường cho phép; tách khỏi entity và response.
4. Quy định ngữ nghĩa không gửi, null, xóa, mảng và thuộc tính lồng nhau.
5. Kiểm tra schema, đường dẫn và từng phép toán trước khi áp dụng thay đổi vào dữ liệu có thể lưu.
6. Kiểm tra quyền trên dữ liệu có thẩm quyền, rồi validation, tính lại giá trị và kiểm tra invariant trong ranh giới nhất quán.
7. Tạo projection phản hồi phù hợp; mở rộng kiểm soát sang truy vấn, xuất dữ liệu, cache và các kênh thông báo.
8. Kiểm thử trường cấm, đối tượng sai, trạng thái sai, nội dung mơ hồ và cập nhật đồng thời.

Phân quyền theo trường bảo vệ ý nghĩa của từng thuộc tính: ai được biết, ai được đề xuất thay đổi và hệ thống nào có thẩm quyền xác lập giá trị. Khi các quyết định này được thực thi nhất quán cùng quyền theo đối tượng và invariant, một request hợp lệ về cấu trúc không thể tự trở thành quyền sửa mọi dữ liệu của đối tượng.
