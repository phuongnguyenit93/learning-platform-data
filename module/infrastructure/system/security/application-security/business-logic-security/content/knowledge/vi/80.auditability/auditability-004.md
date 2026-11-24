# Before and after values: Giá trị trước và sau trong audit nghiệp vụ

## 1. Mục tiêu và phạm vi

**Before and after values** là các giá trị mô tả trạng thái của dữ liệu ngay trước và sau một thay đổi nghiệp vụ được xác định. Khi được thu thập đúng, chúng giúp trả lời: đối tượng nào đã thay đổi, trường nào thay đổi, từ giá trị gì sang giá trị gì, ai thực hiện và thay đổi đó thuộc quyết định nào.

Trong chương **Auditability** của module `SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY`, mục tiêu không chỉ là tìm một dòng log có chữ “thành công”. Cần có bằng chứng đủ để phát hiện và giải thích việc sửa giá, thay quyền, thay đổi đối tượng ngoài phạm vi, bỏ qua phê duyệt hoặc áp dụng lại một yêu cầu cũ.

Bài học tập trung vào cách chọn, lấy và bảo vệ giá trị trước/sau. Audit ghi lại kết quả của kiểm soát nghiệp vụ; nó không thay thế việc kiểm tra quyền theo đối tượng, business invariants, state machine, transaction hoặc idempotency.

Sau bài học, bạn cần có khả năng:

- Phân biệt dữ liệu client yêu cầu với dữ liệu thực sự đã được hệ thống chấp nhận và commit.
- Chọn snapshot hoặc delta phù hợp với câu hỏi điều tra.
- Giữ đúng ý nghĩa của null, trường không có, số tiền, tập hợp và dữ liệu bị che.
- Thu thập before/after nhất quán khi có cập nhật đồng thời, retry hoặc rollback.
- Giải thích một thay đổi trong quan hệ với actor, revision, chính sách và trạng thái nghiệp vụ.
- Thiết kế kiểm thử để audit không khẳng định một thay đổi chưa xảy ra hoặc làm lộ bí mật.

## 2. Trước và sau là trước và sau sự kiện nào?

### 2.1. Phải xác định ranh giới nghiệp vụ

Giả sử một khách hàng đổi số lượng của một dòng hàng trong đơn nháp từ 2 thành 3. Với command được chấp nhận, một bộ before/after có thể mô tả:

```text
Đối tượng: order-731, tenant-demo
Command: CHANGE_DRAFT_ITEM_QUANTITY
Revision trước: 41
Revision sau: 42

items[item-5].quantity: 2 -> 3
total_amount: 240000 VND -> 360000 VND
```

Ví dụ giả định đơn chỉ có một dòng hàng, đơn giá 120000 VND, chưa có thuế, phí hay chiết khấu. Đơn giá do máy chủ xác định theo quy tắc của đơn; client không được tự gửi một tổng tiền để hệ thống tin là đúng.

“Trước” là trạng thái có thẩm quyền được dùng làm đầu vào cho chuyển đổi revision 41. “Sau” là trạng thái được lưu bởi chuyển đổi đó ở revision 42. Đây không phải trạng thái lúc người dùng mở trang vài phút trước hoặc trạng thái mới nhất khi hệ thống thu thập log đọc lại sau đó.

### 2.2. Tách dữ liệu yêu cầu, dự kiến và đã áp dụng

| Loại dữ liệu | Ý nghĩa | Có được gọi là kết quả đã áp dụng không? |
| --- | --- | --- |
| Giá trị client gửi | Mong muốn hoặc dữ liệu khai báo của caller | Không; có thể giả mạo hoặc không hợp lệ |
| Giá trị dự kiến | Kết quả tính toán trước khi transaction hoàn tất | Không; còn có thể bị từ chối hoặc rollback |
| Trạng thái đã commit | Thay đổi bền vững tại ranh giới dữ liệu được định nghĩa | Có, trong đúng phạm vi đó |
| Trạng thái tại hệ thống nhận | Kết quả một consumer hoặc dịch vụ ngoài đã ghi nhận | Chỉ khi có bằng chứng tương ứng từ hệ thống nhận |
| Trạng thái hiện tại khi điều tra | Trạng thái có thể đã qua nhiều thay đổi tiếp theo | Không thay thế trạng thái sau của một sự kiện lịch sử |

Một request gửi `role=ADMIN` chưa có nghĩa quyền đã đổi thành admin. Một sự kiện nội bộ ghi “đã yêu cầu hoàn tiền” chưa có nghĩa nhà cung cấp đã hoàn tiền. Audit phải ghi đúng tầng quyết định và kết quả mà nó quan sát được.

### 2.3. Không dùng client làm nguồn cho before

Client có thể gửi cả `oldPrice` và `newPrice`. Không được dùng `oldPrice` đó làm bằng chứng về trạng thái trước: caller có thể sửa nó, dữ liệu có thể đã cũ hoặc thuộc một đối tượng khác.

Client có thể gửi `expected_revision` để kiểm tra xung đột. Máy chủ vẫn phải đọc hoặc đối chiếu trạng thái có thẩm quyền. Revision kỳ vọng là một điều kiện của command, không phải một snapshot đã được tin cậy.

## 3. Chọn phạm vi dữ liệu cần ghi

### 3.1. Snapshot đầy đủ và delta có mục tiêu khác nhau

**Snapshot** ghi trạng thái được chọn ở một thời điểm. **Delta** chỉ ghi các khác biệt giữa hai trạng thái trong phạm vi theo dõi.

| Cách ghi | Điểm hữu ích | Điều phải xử lý |
| --- | --- | --- |
| Snapshot trước/sau của toàn đối tượng | Dễ xem bối cảnh nếu đối tượng nhỏ | Dễ chứa bí mật, dữ liệu thừa hoặc dữ liệu ngoài quyền |
| Delta theo danh sách trường nghiệp vụ | Dễ thấy thay đổi quan trọng, ít dữ liệu hơn | Phải biết cách hiểu path, kiểu dữ liệu và phần bối cảnh |
| Delta kết hợp bối cảnh chọn lọc | Cân bằng khả năng giải thích và lượng dữ liệu | Cần quy tắc rõ về trường thay đổi và trường bối cảnh |
| Chỉ ghi mô tả dạng văn bản | Thuận tiện để đọc nhanh | Khó đối chiếu tự động; có thể thiếu giá trị hoặc gây hiểu nhầm |

Không có yêu cầu phải serialize toàn bộ entity. Với bài toán đổi số lượng, delta có thể ghi số lượng và tổng tiền, kèm trạng thái đơn, tiền tệ và phiên bản chính sách làm bối cảnh.

### 3.2. Dùng danh sách trường được phép ghi

Xây dựng một mô hình audit riêng với các trường có ý nghĩa nghiệp vụ. Với mỗi trường, xác định:

- Khi nào cần ghi thay đổi của nó.
- Kiểu dữ liệu và cách so sánh.
- Mức hiển thị: rõ, che hoặc tham chiếu kho có kiểm soát.
- Ai được đọc và thời hạn lưu theo chính sách.
- Trường đó là dữ liệu đầu vào, dữ liệu suy ra hay bối cảnh.

Không dùng reflection hoặc serializer mặc định để đẩy mọi thuộc tính của entity vào log. Khi lập trình viên thêm một trường bí mật vào entity, cách làm đó có thể khiến bí mật tự xuất hiện trong audit mà không qua quyết định thiết kế nào.

Danh sách trường cũng phải được quản lý khi mô hình nghiệp vụ thay đổi. Một trường mới như `approval_owner` không được biến mất khỏi bằng chứng chỉ vì bộ mapper cũ chưa biết đến nó.

### 3.3. Ghi cả thay đổi suy ra quan trọng

Đổi số lượng có thể làm tổng tiền thay đổi. Đổi số tiền đề nghị có thể làm phê duyệt cũ mất hiệu lực. Đổi người sở hữu có thể làm quyền truy cập thay đổi.

Chỉ ghi trường client gửi sẽ bỏ sót hậu quả do máy chủ tính toán. Cần ghi những thay đổi suy ra quan trọng đối với invariant, đồng thời phân biệt rõ chúng với trường được yêu cầu sửa.

Ngược lại, không cần biến các khác biệt không liên quan, như thời gian refresh cache, thành thay đổi nghiệp vụ của đơn hàng.

## 4. Ví dụ cấu trúc sự kiện before/after

### 4.1. Sự kiện thay đổi số lượng đã được chấp nhận

Ví dụ sau dùng delta đã chọn lọc. Các ID đều là dữ liệu minh họa; tên trường và phiên bản schema do hệ thống quy định.

```json
{
  "schema_version": 1,
  "event_id": "audit-event-904",
  "event_type": "ORDER_QUANTITY_CHANGED",
  "outcome": "APPLIED",
  "tenant_id": "tenant-demo",
  "aggregate": {
    "type": "ORDER",
    "id": "order-731",
    "previous_revision": 41,
    "new_revision": 42
  },
  "actor": {
    "actor_ref": "customer-82",
    "binding_method": "AUTHENTICATED_ACCOUNT"
  },
  "command_id": "command-772",
  "correlation_ref": "flow-218",
  "source": "order-service",
  "policy_ref": "draft-order-quantity-policy@3",
  "recorded_at": "2026-10-05T09:00:00.120Z",
  "context": {
    "order_state": "DRAFT",
    "currency": "VND",
    "pricing_revision": "price-7"
  },
  "changes": [
    {
      "path": "items[item-5].quantity",
      "value_type": "integer",
      "before": 2,
      "after": 3
    },
    {
      "path": "total_amount",
      "value_type": "decimal",
      "before": "240000",
      "after": "360000"
    }
  ]
}
```

`APPLIED` mô tả thay đổi đơn hàng trong transaction nguồn. Nó không có nghĩa đơn đã thanh toán, hàng đã được giữ trong kho hoặc mọi consumer đã cập nhật xong.

Sự kiện được tạo bởi máy chủ từ trạng thái đã kiểm chứng. Không nhận nguyên một object audit do client gửi rồi coi các trường actor, revision và outcome là bằng chứng đáng tin.

### 4.2. Các định danh có vai trò khác nhau

- `event_id` định danh sự kiện để nhận diện giao trùng.
- `command_id` liên kết các lần thử thuộc một command nghiệp vụ.
- `correlation_ref` liên kết một luồng có thể gồm nhiều command.
- ID đối tượng cùng tenant xác định phạm vi dữ liệu bị thay đổi.
- Revision chỉ ra vị trí của thay đổi trong lịch sử của đối tượng.

Không dùng một correlation ID chung để kết luận mọi thay đổi thuộc cùng một transaction. Cũng không coi việc biết ID khó đoán là quyền xem sự kiện audit.

### 4.3. Nguồn actor phải rõ ràng

Actor phải lấy từ ngữ cảnh xác thực hoặc danh tính dịch vụ được kiểm chứng. Nếu một nhân viên thao tác thay khách hàng, ghi riêng người thực hiện và chủ thể được đại diện, kèm tham chiếu quyền đại diện khi cần.

Không ghi mọi hành động là `system` chỉ vì chúng đi qua backend. Với tác vụ nền, có thể cần cả danh tính worker thực thi và command/actor khởi tạo. Những thông tin này không tự chứng minh quyền hợp lệ; chúng giúp đối chiếu quyết định kiểm tra quyền đã diễn ra.

Không đưa access token, cookie phiên hoặc khóa idempotency chứa dữ liệu riêng tư vào sự kiện để làm định danh. Có thể dùng reference nội bộ được thiết kế cho audit.

## 5. Giữ đúng ý nghĩa của giá trị

### 5.1. Null, không có trường và không biết là ba việc khác nhau

Trong cập nhật từng phần, trường không xuất hiện có thể mang nghĩa giữ nguyên; trường xuất hiện với null có thể mang nghĩa xóa giá trị, nếu hợp đồng cho phép. Không tự ánh xạ cả hai thành cùng một hành động.

Đối với bằng chứng, còn cần phân biệt việc không ghi dữ liệu vì chính sách với việc dữ liệu thực sự không tồn tại.

| Tình huống | Ý nghĩa cần giữ |
| --- | --- |
| Trường không có trong đối tượng | Không tồn tại theo mô hình tại thời điểm đó |
| Trường có giá trị null | Tồn tại nhưng không có giá trị theo quy ước của trường |
| Trường không có trong request | Thường không yêu cầu sửa, tùy hợp đồng cập nhật |
| Giá trị được che trong audit | Có dữ liệu nhưng người đọc không được thấy nội dung |
| Không thu thập được giá trị lịch sử | Không đủ bằng chứng; không được tự điền null |

Nếu audit phải biểu diễn các trường hợp này, có thể dùng envelope tường minh:

```text
before:
    presence = VALUE
    disclosure = REDACTED
after:
    presence = NULL
    disclosure = CLEAR
changed = true
change_kind = CLEARED
```

Các nhãn là quy ước minh họa. Hệ thống cần định nghĩa ý nghĩa của chúng trong schema, kể cả `UNKNOWN` cho lịch sử không đủ dữ liệu nếu cần. Không để người đọc hiểu một trường bị che là một giá trị null thực sự. `CLEARED` ở đây là bỏ giá trị nhưng vẫn giữ trường với null; xóa hẳn trường cần biểu diễn trạng thái không tồn tại riêng.

### 5.2. Tiền tệ, độ chính xác và đơn vị

Số tiền phải đi cùng tiền tệ hoặc đơn vị đủ rõ. Với ví dụ đơn hàng, `240000` và `360000` là giá trị thập phân chính xác bằng VND; không dùng số dấu phẩy động để tính chênh lệch tiền.

Có thể dùng chuỗi thập phân có quy tắc hoặc số nguyên theo đơn vị nhỏ nhất đã định nghĩa. Cần thống nhất cách làm tròn, scale và cách diễn giải. Không đổi từ đơn vị đồng sang đơn vị nghìn đồng mà vẫn giữ nguyên tên trường và schema.

Nếu tiền tệ thay đổi, phải ghi chính thay đổi tiền tệ và cách xác định giá trị tương ứng. Không thể giải thích chênh lệch giữa `100 USD` và `100 VND` chỉ bằng việc hai chuỗi số đều là `100`.

### 5.3. So sánh theo ngữ nghĩa của trường

Một tập quyền có thể cần so sánh không phụ thuộc thứ tự. Một danh sách các bước duyệt lại có thể phụ thuộc thứ tự. Chuỗi tên có thể được chuẩn hóa khoảng trắng; mã phân biệt hoa thường thì không được tự đổi cách so sánh.

Với tập quyền, delta `added` và `removed` thường giúp thấy rõ việc cấp hoặc thu hồi. Với dòng hàng, path nên dùng ID dòng ổn định, không chỉ vị trí mảng: xóa phần tử đầu không được khiến mọi dòng phía sau bị báo thành đổi sản phẩm.

Không tính diff chỉ bằng hai chuỗi JSON bất kỳ. Thứ tự thuộc tính hoặc cách biểu diễn số có thể làm xuất hiện khác biệt hình thức, trong khi một phép chuẩn hóa quá mạnh có thể che mất khác biệt nghiệp vụ.

### 5.4. Phân biệt không thay đổi với thay đổi bị che

Hai địa chỉ email khác nhau có thể cùng hiển thị thành `***@example.test`. Nếu che trước rồi so sánh, hệ thống có thể kết luận sai rằng không có thay đổi.

Xác định thay đổi từ dữ liệu được phép xử lý trong miền nghiệp vụ, sau đó áp dụng quy tắc hiển thị. Audit có thể ghi `changed=true`, loại thay đổi và reference bằng chứng được bảo vệ, dù phần hiển thị trước/sau giống nhau.

Tên trường, loại thay đổi và việc một giá trị tồn tại cũng có thể nhạy cảm. Chính sách cần kiểm soát cả metadata, không chỉ nội dung trong trường `value`.

## 6. Thu thập nhất quán với transaction

### 6.1. Trình tự thực hiện

Một luồng thay đổi số lượng có thể được tổ chức như sau:

```text
Xác thực caller; xác định tenant từ ngữ cảnh đáng tin cậy
Kiểm tra hình dạng request và định danh command

BEGIN TRANSACTION
    Phối hợp trên đơn hàng bằng khóa hoặc optimistic version
    Đọc đơn trong đúng tenant
    Kiểm tra quyền theo đối tượng và điều kiện truy cập hiện tại

    Tra kết quả idempotency trong đúng phạm vi
    Nếu command đã được áp dụng:
        Kiểm tra fingerprint phù hợp
        Trả kết quả đã lưu; không sửa đơn lần nữa

    Kiểm tra expected_revision, trạng thái DRAFT và invariant
    Chụp immutable snapshot của các giá trị before cần thiết

    Áp dụng quantity được cho phép
    Tính lại tổng tiền từ dữ liệu giá có thẩm quyền
    Kiểm tra các invariant sau khi tính
    Lưu đơn và tăng revision
    Lấy giá trị after phản ánh kết quả được lưu

    Tạo delta nghiệp vụ theo danh sách trường đã định nghĩa
    Ghi audit event hoặc audit outbox trong cùng transaction
    Ghi kết quả command
COMMIT

Trả kết quả; publisher chuyển sự kiện đã commit tới kho audit
```

Đây là giả mã về trách nhiệm, không phải hướng dẫn mặc định cho một ORM hay mức isolation cụ thể. Cơ chế khóa/version, ràng buộc dữ liệu và phạm vi transaction phải thực sự ngăn các cập nhật cạnh tranh làm sai before/after.

### 6.2. Snapshot before phải độc lập với object sẽ bị sửa

Một lỗi thường gặp là giữ hai biến cùng trỏ tới một entity:

```text
before = order
order.quantity = 3
after = order
```

Lúc serialize, cả `before` và `after` có thể đã là object sau sửa. Kết quả là audit cho thấy `3 -> 3`, trong khi cơ sở dữ liệu từng có giá trị 2.

Chụp các giá trị cần thiết thành snapshot bất biến trước khi sửa. Không trông chờ serializer chạy muộn sẽ tự nhớ lại dữ liệu cũ. Snapshot cũng không được vô tình kéo thêm quan hệ chứa dữ liệu ngoài phạm vi audit.

### 6.3. After phải phản ánh dữ liệu được lưu

Validation, chuẩn hóa, tính toán hoặc cơ chế ở cơ sở dữ liệu có thể làm giá trị lưu khác với request hay entity trước khi ghi. Nếu thiết kế có các bước như vậy, phải lấy after sau bước tạo giá trị cuối cùng theo cơ chế của hệ thống.

Ví dụ, tổng tiền do máy chủ tính lại là 360000, dù client gửi kèm `total_amount=1`. Trường không được phép sửa có thể bị từ chối hoặc xử lý theo hợp đồng; audit không được báo `240000 -> 1` như một thay đổi đã áp dụng nếu cơ sở dữ liệu chưa bao giờ chấp nhận nó.

Việc lấy after trong transaction vẫn phải gắn với kết quả commit. Nếu transaction thất bại sau đó, không công bố event đó như một thay đổi đã áp dụng.

### 6.4. Không mở một transaction log độc lập rồi coi là nguyên tử

Nếu cập nhật đơn commit nhưng ghi audit thất bại, lịch sử sẽ có khoảng trống. Nếu audit commit trước nhưng thay đổi đơn rollback, lịch sử sẽ khẳng định một việc chưa xảy ra.

Với thao tác mà chính sách yêu cầu luôn có bằng chứng bền vững, có thể ghi event hoặc outbox cùng transaction dữ liệu. Khi không ghi được bản ghi bắt buộc này, thao tác không được công bố là hoàn tất theo hợp đồng đó.

Kho audit tập trung có thể chưa nhận event ngay. Outbox bền vững giúp giữ ý định chuyển sự kiện, còn publisher cần retry, giám sát tồn đọng và đối chiếu. Không gọi một lệnh gửi log bất đồng bộ từ bộ nhớ là tương đương với audit outbox.

## 7. Cập nhật đồng thời và thứ tự lịch sử

### 7.1. Before sai có thể tạo ra một lịch sử trông hợp lý

Giả sử hai request đều đọc quantity bằng 2 và revision bằng 41:

```text
A muốn đổi 2 -> 3
B muốn đổi 2 -> 4
```

Nếu cả hai cùng ghi mà không phối hợp, trạng thái cuối có thể là 4, trong khi audit cho thấy hai thay đổi độc lập đều bắt đầu ở 2. Người điều tra không biết B đã ghi đè A hay hai thay đổi thuộc các nhánh khác nhau.

Với optimistic version được thực thi đúng, chỉ một cập nhật dựa trên revision 41 được chấp nhận. Request còn lại nhận xung đột; nếu cần thay đổi tiếp, caller phải dùng ngữ cảnh mới theo hợp đồng. Một lần áp dụng B hợp lệ sau A sẽ ghi `3 -> 4` và revision `42 -> 43`.

Nếu dùng khóa, dữ liệu before phải là dữ liệu có thẩm quyền trong khoảng phối hợp đó. Chỉ thêm một cột `version` nhưng không kiểm tra khi ghi không giải quyết được lost update.

### 7.2. Không sắp lịch sử chỉ bằng timestamp

Timestamp hữu ích để điều tra, nhưng có thể trùng, đến muộn hoặc phản ánh thời điểm khác nhau giữa các hệ thống. Revision theo đối tượng giúp xác định thứ tự thay đổi được nguồn chấp nhận.

Consumer nhận event revision 43 trước revision 42 không được tự sửa dữ liệu của event cũ để tạo ra một chuỗi đẹp. Cần giữ định danh gốc, nhận diện khoảng trống và có cơ chế đối chiếu với nguồn.

Revision liên tục của một đối tượng chỉ cho biết thứ tự trong hợp đồng của đối tượng đó. Nếu audit chỉ ghi một tập loại thay đổi, các khoảng nhảy revision chưa chắc là mất event. Schema và chính sách phải nói rõ tập thay đổi được theo dõi.

### 7.3. Không đọc lại sau commit để đoán after của event cũ

Sau khi A commit revision 42, B có thể commit revision 43 trước lúc tác vụ log của A đọc lại đơn. Nếu tác vụ đó lấy trạng thái mới nhất, audit A sẽ sai dù mọi request nghiệp vụ đều thành công.

Cần lưu payload hoặc snapshot có revision ngay tại transaction của A, rồi chuyển bản ghi đó tới kho audit. Publisher không được thay payload lịch sử bằng trạng thái hiện tại lúc gửi.

## 8. Retry, từ chối, rollback và kết quả chưa rõ

### 8.1. Tách command khỏi từng lần gọi

Một command được retry vì mất phản hồi không được tạo thêm thay đổi chỉ để có một dòng audit mới. Idempotency cần ràng buộc đúng actor/phạm vi, payload quan trọng và kết quả command.

Nếu command đổi quantity đã commit revision 42, retry cùng command có thể trả kết quả cũ. Nó không áp dụng lại như một lệnh tăng thêm số lượng, không tạo revision mới và không tạo event nghiệp vụ giả thứ hai.

Có thể audit từng attempt để điều tra hành vi lạm dụng. Khi ấy, attempt event phải liên kết với command/event gốc và thể hiện rõ đó là retry, không phải một lần thay đổi mới.

### 8.2. Không tạo after giả cho request bị từ chối

| Kết quả | Cách diễn giải before/after |
| --- | --- |
| `APPLIED` | Có thay đổi được commit trong ranh giới đã nêu |
| `NO_CHANGE` | Command hợp lệ nhưng không tạo thay đổi theo ngữ nghĩa đã định nghĩa |
| `REJECTED` | Điều kiện hoặc quyền không đạt; không có after mới được áp dụng |
| `ROLLED_BACK` | Thay đổi dự kiến không trở thành kết quả commit |
| `UNKNOWN` | Thành phần quan sát chưa xác định được kết quả; cần đối chiếu |

Các tên outcome là ví dụ, không phải chuẩn bắt buộc. Điều quan trọng là không gộp mọi trường hợp vào “thành công” hoặc “thất bại” rồi suy diễn dữ liệu đã thay đổi thế nào.

Một attempt bị từ chối có thể ghi hành động được yêu cầu và lý do ở mức được phép. Không cần đọc toàn bộ giá trị hiện có của đối tượng ngoài quyền chỉ để điền before. Cũng không được trả các giá trị đó trong phản hồi lỗi.

### 8.3. Audit từ chối có ranh giới lưu khác

Nếu ghi attempt audit bên trong transaction sẽ rollback, bản ghi đó cũng có thể mất. Nếu sản phẩm cần giữ các lần tấn công bị từ chối, phải có đường ghi phù hợp, được bảo vệ và có hành vi lỗi rõ ràng.

Bản ghi ngoài transaction này chỉ được khẳng định điều đã quan sát về attempt. Nó không được dùng làm bằng chứng rằng thay đổi dữ liệu đã commit.

Với command không thay đổi giá trị nhưng có ý nghĩa xác nhận hoặc chuyển bước nghiệp vụ, vẫn có thể cần event riêng. Không mặc định “delta rỗng” đồng nghĩa “không có sự kiện nghiệp vụ”.

### 8.4. Mất phản hồi không đồng nghĩa rollback

Một tiến trình có thể dừng sau commit nhưng trước khi trả kết quả. Thành phần gọi chỉ biết timeout; trạng thái nguồn và audit outbox có thể đã được lưu đầy đủ.

Cần đối chiếu theo command ID hoặc operation reference. Không ghi chắc chắn `ROLLED_BACK` chỉ từ timeout và không tự chạy một command mới trước khi giải quyết kết quả chưa rõ theo hợp đồng.

## 9. Bảo vệ dữ liệu trước/sau

### 9.1. Giá trị cũ cũng là dữ liệu cần bảo vệ

Audit có thể giữ một email cũ, địa chỉ cũ hoặc quyền cũ sau khi dữ liệu chính đã đổi. Việc không còn thấy chúng ở hồ sơ hiện tại không làm chúng tự biến mất khỏi log, bản export, backup hoặc kho phân tích.

Không ghi mật khẩu, access token, refresh token, cookie phiên, khóa API hoặc bí mật xác thực vào before/after. Với đổi mật khẩu, bằng chứng có thể là “thông tin xác thực đã đổi”, actor, phương thức xác nhận và thời điểm; không cần giá trị mật khẩu cũ/mới hay hash mật khẩu trong audit.

### 9.2. Che, tham chiếu và kiểm soát quyền

Với dữ liệu riêng tư cần cho một mục tiêu bằng chứng cụ thể, có thể dùng:

- Giá trị đã che đủ cho công việc thông thường.
- Reference tới bằng chứng chi tiết trong kho có quyền riêng.
- Mã hóa theo thiết kế quản lý khóa và thời hạn của kho.
- Một biểu diễn chỉ cho biết có thay đổi mà không tiết lộ nội dung.

Không phải dữ liệu nào cũng cần giữ bản rõ ở nơi khác. Chỉ tạo reference đến kho chi tiết nếu có nhu cầu được xác định; reference không tự làm dữ liệu an toàn nếu ai biết ID cũng tải được.

Quyền đọc audit phải xét tenant, loại đối tượng, nhiệm vụ và mức chi tiết. Người được sửa một trường hồ sơ hiện tại chưa chắc được đọc toàn bộ lịch sử của trường đó. Người xem audit tổng hợp cũng chưa chắc có quyền mở bằng chứng chi tiết.

### 9.3. Hash không tự làm giá trị trở thành vô danh

Một email hoặc số điện thoại dễ đoán có thể bị thử đối chiếu với hash. Không dùng hash không khóa như một cách mặc định để công khai dữ liệu nhạy cảm trong audit.

Nếu thiết kế cần một cơ chế đối chiếu bảo vệ nội dung, phải xác định mô hình đe dọa, cách quản lý khóa nếu áp dụng và quyền truy cập metadata. Cơ chế đối chiếu cũng không thay thế bằng chứng về actor hay tính hợp lệ của quyết định nghiệp vụ.

### 9.4. Coi giá trị được ghi là dữ liệu không đáng tin để hiển thị

Tên sản phẩm, lý do điều chỉnh hoặc chuỗi do caller nhập có thể chứa xuống dòng, dấu phân cách hoặc nội dung giống một bản ghi log khác. Dùng cấu trúc sự kiện và encoding phù hợp; khi hiển thị trong trình duyệt phải xử lý như dữ liệu, không thực thi như HTML.

Không đưa raw request body hoặc toàn bộ exception context vào log dự phòng khi serializer audit lỗi. Đường xử lý lỗi cũng phải tuân thủ danh sách dữ liệu được phép ghi.

## 10. Liên hệ với invariant và phê duyệt

### 10.1. Audit phải giúp giải thích quyết định

Một delta `discount: 0 -> 90%` cho biết có thay đổi lớn, nhưng chưa cho biết thay đổi có đúng quyền và đúng chính sách không. Cần liên kết với actor, trạng thái đối tượng, policy version và approval reference nếu thao tác yêu cầu phê duyệt.

Audit hỗ trợ trả lời các câu hỏi như:

- Actor có quyền sửa đúng đơn hàng trong đúng tenant không?
- Đơn có ở trạng thái cho phép sửa không?
- Giá hoặc tổng tiền có được tính từ nguồn đúng không?
- Giá trị sau có vượt giới hạn hoặc làm mất điều kiện phê duyệt cũ không?
- Command có bị áp dụng nhiều lần không?

Việc ghi các câu trả lời hoặc reference cần thiết không đồng nghĩa các điều kiện đã được kiểm tra. Hệ thống thực thi phải thực sự từ chối thao tác không hợp lệ.

### 10.2. Phê duyệt phải gắn với nội dung được duyệt

Giả sử một người phê duyệt đã chấp nhận số tiền 500000 ở revision 8. Sau đó caller đổi số tiền thành 5000000 nhưng giữ `approved=true`.

Chỉ ghi `amount: 500000 -> 5000000` chưa đủ để bảo vệ quy trình. Invariant phải yêu cầu phê duyệt gắn với đúng nội dung/revision hoặc điều kiện tương đương. Khi sửa dữ liệu ảnh hưởng quyết định, hệ thống phải vô hiệu hóa hoặc đánh giá lại phê duyệt theo state machine.

Before/after khi đó cần phản ánh cả thay đổi số tiền và trạng thái/phạm vi phê duyệt quan trọng. Không chỉ audit trường caller yêu cầu sửa rồi để hậu quả đối với phê duyệt trở nên vô hình.

### 10.3. Kết quả audit không sửa được một quyết định sai

Một bản ghi đầy đủ vẫn có thể ghi lại một thay đổi trái phép. Audit giúp phát hiện, đối chiếu và điều tra; nó không biến việc bỏ kiểm tra quyền thành chấp nhận được.

Nếu điều tra thấy event đã ghi sai, giữ sự kiện gốc theo chính sách và thêm bản đính chính có liên kết. Không âm thầm thay before/after cũ để lịch sử trông khớp với trạng thái hiện tại.

## 11. Nhiều đối tượng và tác động ngoài hệ thống

### 11.1. Một command có thể làm thay đổi nhiều đối tượng

Khi một command cập nhật đơn hàng và bản ghi giữ hàng, cần xác định chúng có nằm trong cùng transaction hay không. Có thể ghi event cho từng đối tượng và liên kết bằng command/transaction reference thích hợp.

Before/after của đơn không tự chứng minh tồn kho đã đổi. Nếu hai thay đổi nằm ở hai dịch vụ khác nhau, không mô tả chúng như một snapshot nguyên tử toàn hệ thống khi thiết kế không cung cấp bảo đảm đó.

Một thay đổi bù sau đó cũng là một thay đổi mới. Ghi giá trị thực tế trước/sau của lần bù; không xóa event ban đầu rồi nói rằng chưa có gì xảy ra.

### 11.2. Trạng thái nội bộ khác với kết quả từ nhà cung cấp

Trong luồng hoàn tiền, có thể có các mốc: tạo yêu cầu, chấp nhận nội bộ, gửi nhà cung cấp, nhà cung cấp xác nhận và đối soát kết quả. Mỗi mốc cần outcome và nguồn bằng chứng đúng với nó.

Nếu đã gửi nhưng mất phản hồi, không tự ghi số tiền “đã hoàn” bằng số tiền “đã yêu cầu”. Dùng operation reference để kiểm tra và chống tác động trùng theo hợp đồng của luồng.

Khi kết quả ngoài đến muộn, ghi một sự kiện mới với reference và thời gian liên quan. Không sửa event “đã gửi yêu cầu” thành “đã hoàn tiền” như thể mọi việc xảy ra cùng lúc.

### 11.3. Batch không được che kết quả từng phần

Một tác vụ sửa 1000 hồ sơ có thể chỉ cập nhật thành công một phần nếu thiết kế cho phép. Một dòng “batch thành công” không đủ giải thích before/after của từng đối tượng.

Cần liên kết kết quả từng đối tượng, revision và lỗi theo hợp đồng. Không ghi mọi phần tử có cùng before hoặc after chỉ vì request batch chứa cùng một giá trị đích.

## 12. Tính toàn vẹn và khả năng sử dụng lịch sử

### 12.1. Hạn chế sửa lịch sử tùy ý

Phân tách quyền thay đổi dữ liệu nghiệp vụ, ghi audit, đọc audit và thực hiện quy trình lưu trữ/dọn dữ liệu. Các luồng quản trị, import và sửa dữ liệu đặc biệt cũng cần cơ chế giữ bằng chứng phù hợp; không tạo một đường sửa trực tiếp bỏ qua toàn bộ audit.

Mô hình ghi nối tiếp và kiểm soát lưu trữ có thể giảm khả năng sửa lịch sử mà không để lại dấu vết. Checksum, chữ ký hoặc chuỗi băm có thể hỗ trợ kiểm tra tính toàn vẹn khi có điểm tin cậy và quản lý khóa/metadata phù hợp.

Không khẳng định checksum chứng minh dữ liệu ban đầu là đúng. Nếu một người có thể sửa cả event và giá trị kiểm tra mà không có kiểm soát độc lập, khả năng phát hiện sửa đổi bị hạn chế.

### 12.2. Schema và quy tắc phải có phiên bản

Bằng chứng lịch sử cần giữ được ý nghĩa khi tên trường, kiểu dữ liệu hoặc trạng thái nghiệp vụ thay đổi. Schema version, định nghĩa trường và reference chính sách giúp đọc lại một event mà không áp nghĩa của phiên bản hiện tại vào quá khứ.

Nếu field `limit` từng tính theo ngày nhưng nay tính theo tháng, cùng một giá trị số không có cùng ý nghĩa. Migration không được tự viết lại lịch sử như thể quy tắc mới đã tồn tại ở thời điểm event cũ.

### 12.3. Không tự suy ra toàn bộ trạng thái chỉ từ delta còn sót lại

Delta chỉ ghi một phần thay đổi. Muốn dựng lại trạng thái lịch sử cần baseline, tập event đủ theo hợp đồng, thứ tự và quy tắc áp dụng thích hợp.

Nếu baseline bị dọn hoặc thiếu một khoảng event, phải nói rõ giới hạn bằng chứng. Không lấy giá trị hiện tại rồi chạy ngược một số delta không đầy đủ để kết luận chắc chắn về quá khứ.

Thời hạn lưu của audit, reference chi tiết, artifact chính sách và backup cần được phối hợp theo nhu cầu của sản phẩm. Việc giữ một event nhưng làm mất toàn bộ nội dung mà nó tham chiếu có thể khiến event không còn trả lời được câu hỏi dự kiến.

## 13. Ca điều tra: số lượng bị ghi đè hay bị áp dụng trùng?

### 13.1. Tình huống

Khách hàng phản ánh số lượng của dòng `item-5` từng là 2 nhưng cuối cùng là 4. Có nhiều command và các lần retry trong cùng một luồng.

| Thứ tự nghiệp vụ | Bằng chứng | Ý nghĩa |
| --- | --- | --- |
| Revision 41 | Snapshot đủ tin cậy: quantity bằng 2 | Điểm bắt đầu của khoảng đang xét |
| Command A commit revision 42 | `2 -> 3`, actor và policy reference rõ | Một thay đổi được áp dụng |
| Retry A | Tham chiếu kết quả A, không có revision mới | Không phải tăng số lượng lần nữa |
| B dùng expected revision 41 | Bị từ chối do xung đột | Không có after mới được áp dụng bởi lần thử này |
| Command C dựa trên revision 42 | `3 -> 4`, commit revision 43 | Một thay đổi mới trên trạng thái mới |
| Kho audit nhận event 43 trước 42 | Metadata nhận khác thứ tự revision | Độ trễ truyền không phải thứ tự quyết định nghiệp vụ |

### 13.2. Cách đánh giá

Đối chiếu tenant, đối tượng, command, actor, outcome và revision trước khi nhìn timestamp. Kiểm tra delta từ nguồn đã commit, không dùng request payload để điền phần thiếu của lịch sử.

Nếu chỉ có các delta `2 -> 3` và `2 -> 4` đều được đánh dấu applied, cần điều tra cơ chế phối hợp hoặc việc lấy before. Chưa thể tự kết luận có gian lận: có thể là lost update, snapshot cũ, sai mapper hoặc cách định nghĩa revision không rõ.

Nếu cùng command A tạo hai revision, kiểm tra idempotency và ràng buộc duy nhất. Nếu revision đúng nhưng audit A có after bằng 4, kiểm tra tác vụ log có đọc lại trạng thái quá muộn không.

Nếu delta số lượng đúng nhưng tổng tiền vẫn là 240000, kiểm tra invariant và việc ghi trường suy ra. Một lịch sử có nhiều event không đồng nghĩa dữ liệu nghiệp vụ nhất quán.

### 13.3. Giới hạn kết luận

Bộ before/after giúp giải thích thay đổi đã quan sát. Nó không tự chứng minh người dùng ngoài đời đã chủ động thực hiện, thiết bị không bị chiếm quyền hoặc mọi tác động ngoài hệ thống đều thành công.

Mức kết luận phải tương xứng với nguồn actor, chất lượng snapshot, độ đầy đủ của lịch sử và tính toàn vẹn của kho bằng chứng.

## 14. Kiểm thử các tình huống lạm dụng và lỗi thu thập

| Tình huống | Điều phải kiểm chứng |
| --- | --- |
| Đổi quantity hợp lệ | Before từ trạng thái nguồn; after và tổng tiền đúng revision đã commit |
| Client giả `oldQuantity` | Không dùng giá trị giả làm before có thẩm quyền |
| Client tự gửi tổng tiền hoặc đơn giá trái phép | Không áp dụng ngoài hợp đồng; audit không khẳng định giá trị giả đã được lưu |
| Sửa order của tenant khác | Từ chối; không lộ before/after của đối tượng ngoài quyền |
| Đơn không ở trạng thái cho phép sửa | Không có event applied cho chuyển đổi bị cấm |
| Hai cập nhật cùng expected revision | Chỉ các chuyển đổi được cơ chế cạnh tranh cho phép mới được áp dụng |
| Entity before bị sửa qua cùng reference | Snapshot vẫn giữ được giá trị cũ thực sự |
| Chuẩn hóa hoặc tính lại ở bước lưu | After phản ánh giá trị được lưu, không phải request hay object cũ |
| Transaction rollback sau khi tạo delta | Không xuất hiện event applied cho dữ liệu chưa commit |
| Không ghi được audit/outbox bắt buộc | Hành vi transaction đúng với hợp đồng, không âm thầm bỏ bằng chứng |
| Commit xong nhưng mất phản hồi | Retry đối chiếu command; không tạo thay đổi nghiệp vụ lần nữa |
| Cùng command key nhưng đổi payload quan trọng | Xử lý xung đột; không dùng kết quả của một payload cho payload khác |
| Publisher giao trùng hoặc đảo thứ tự | Giữ event gốc; nhận diện trùng và thứ tự theo hợp đồng |
| Request bỏ trường so với gửi null | Không nhầm giữ nguyên với xóa giá trị |
| Thay đổi giá trị nhạy cảm có cùng phần đã che | Vẫn nhận diện thay đổi, không lộ bản rõ |
| Đổi tập quyền chỉ khác thứ tự phần tử | Không tạo delta giả nếu mô hình coi đó là một tập |
| Xóa một dòng ở đầu danh sách | Các dòng còn lại được nhận diện bằng ID ổn định |
| Đổi số tiền cần phê duyệt lại | Ghi cả hậu quả đối với approval; invariant được thực thi |
| Chuỗi có xuống dòng hoặc nội dung HTML | Không giả thêm bản ghi và không thực thi nội dung trong giao diện audit |
| Lỗi serializer hoặc exception | Không fallback sang log toàn bộ entity/request chứa bí mật |
| Command hợp lệ nhưng không đổi giá trị | Outcome đúng; không tạo delta giả hoặc bỏ sót sự kiện xác nhận quan trọng |
| Batch thành công từng phần | Kết quả và before/after riêng đúng cho từng đối tượng |
| Thiếu baseline hoặc mất khoảng lịch sử | Không tuyên bố dựng lại đầy đủ trạng thái quá khứ |
| Truy cập audit/export ngoài phạm vi | Kiểm tra quyền và dữ liệu được trả ở đúng mức chi tiết |

Với mỗi ca, kiểm tra cả dữ liệu cuối cùng, revision, command result và event/outbox liên quan. Chỉ kiểm tra mã HTTP hoặc tìm một dòng log không đủ để phát hiện cập nhật trùng và bằng chứng sai.

Với cạnh tranh, dùng điểm đồng bộ để đặt các lần đọc, ghi và commit vào thứ tự cần kiểm chứng. Với lỗi transaction, chủ động gây lỗi tại ranh giới có ý nghĩa. Các kiểm thử này phải kiểm tra invariant và kết quả quan sát được, thay vì chỉ xác nhận hàm ghi log đã được gọi.

## 15. Câu hỏi tự kiểm tra

**Có thể dùng `oldValue` client gửi làm before không?**

Không. Nó chỉ là dữ liệu khai báo. Before của thay đổi phải đến từ trạng thái có thẩm quyền và được lấy trong cơ chế phối hợp phù hợp với lần cập nhật.

**Vì sao không đọc lại đối tượng sau commit rồi tạo event?**

Một command khác có thể đã thay đổi đối tượng. Giá trị mới nhất không nhất thiết là after của command đang audit. Cần giữ payload hoặc snapshot có revision của chính lần thay đổi đó.

**Audit event nên chứa mọi trường của entity không?**

Không mặc định như vậy. Chọn trường phục vụ mục tiêu bằng chứng, ghi các hậu quả nghiệp vụ quan trọng và áp dụng chính sách dữ liệu cho từng trường.

**Hai giá trị đã che giống nhau có nghĩa không có thay đổi không?**

Không. Phải xác định thay đổi theo ngữ nghĩa trước khi áp dụng cách hiển thị, rồi ghi metadata hoặc reference phù hợp mà không làm lộ nội dung.

**Event có before/after đầy đủ có chứng minh thay đổi hợp lệ không?**

Chưa đủ. Cần đối chiếu quyền đối tượng, trạng thái, chính sách, phê duyệt và các invariant. Audit không thực thi thay những điều kiện đó.

**Retry có cần một event thay đổi mới không?**

Không nếu chỉ đang nhận lại kết quả của cùng command đã áp dụng. Có thể ghi attempt riêng, nhưng phải phân biệt nó với một chuyển đổi nghiệp vụ mới.

**Một event applied có nghĩa mọi hệ thống đều đã thay đổi không?**

Chỉ có nghĩa trong ranh giới mà event xác định. Kết quả ở consumer hoặc nhà cung cấp ngoài cần bằng chứng riêng, cùng reference để đối chiếu.

**Nếu thiếu giá trị lịch sử, có thể điền null cho đủ cặp không?**

Không. Phải biểu diễn thiếu bằng chứng hoặc unknown theo schema. Null là một giá trị có ý nghĩa, không phải chỗ điền thay cho điều hệ thống không biết.

