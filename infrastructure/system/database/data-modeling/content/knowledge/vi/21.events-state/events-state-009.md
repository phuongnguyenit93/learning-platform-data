# Tiến hóa cấu trúc sự kiện và cách hiểu dữ liệu cũ

## 1. Vấn đề: mã ứng dụng thay đổi nhưng sự kiện lịch sử vẫn tồn tại

Hãy hình dung hệ thống thuê thiết bị đã lưu sự kiện `DepositCaptured` từ năm trước. Khi đó payload chỉ có số tiền, loại tiền và mã giao dịch. Sau này, nhóm phát triển muốn bổ sung kênh thanh toán, đổi tên trường của nhà cung cấp và tách thông tin về các khoản hoàn. Một phiên bản ứng dụng mới cần đọc lại **toàn bộ lịch sử** để dựng trạng thái hợp đồng hoặc xây lại báo cáo.

Nếu mã mới chỉ hiểu JSON mới, replay có thể thất bại. Nếu âm thầm diễn giải dữ liệu cũ như dữ liệu mới, hệ thống có thể **đọc được nhưng tính sai**, một lỗi nguy hiểm hơn cả lỗi parse. Ngược lại, việc giữ mã cũ mãi mãi cũng làm dữ liệu khó tiến hóa.

Trong mô hình dữ liệu dựa trên sự kiện, thiết kế tốt phải trả lời:

1. **Sự kiện cũ có cấu trúc nào?** Những trường nào có mặt, kiểu dữ liệu và đơn vị của chúng là gì?
2. **Sự kiện cũ có ý nghĩa gì tại lúc ghi?** “Đã thanh toán” là đã yêu cầu thu, đã được ngân hàng chấp nhận hay đã quyết toán?
3. **Ứng dụng mới đọc dữ liệu cũ thế nào?** Dùng bộ đọc nhiều phiên bản, upcaster, migration hay projection riêng?
4. **Có thể thay đổi gì mà không làm hỏng consumer?** Phân biệt hợp đồng nội bộ và thông điệp công bố ra ngoài.
5. **Kiểm chứng thế nào?** Replay phải có kết quả dự kiến, không phát sinh side effect và không thay đổi lịch sử âm thầm.

Đây là năng lực quan trọng của **data modeling**: biến yêu cầu nghiệp vụ thành hợp đồng dữ liệu có tên, kiểu, ràng buộc, khóa và vòng đời rõ ràng; không xem JSON là một khối dữ liệu không cần quản trị schema.

## 2. Tách bốn loại phiên bản thường bị nhầm lẫn

Trong hệ dùng event sourcing hoặc event log, một số giá trị cùng được gọi là “version” nhưng có trách nhiệm khác nhau:

| Khái niệm | Dùng để làm gì? | Ví dụ |
| --- | --- | --- |
| **Stream version** | Đánh số thứ tự những event đã được chấp nhận trong **một aggregate stream**. | Sự kiện thứ 37 của hợp đồng `RENT-204`. |
| **Event schema version** | Chỉ cách giải mã và diễn giải **cấu trúc của một event type**. | `DepositCaptured` phiên bản payload 1 hoặc 2. |
| **Reducer/state-model version** | Chỉ quy tắc biến chuỗi event thành state. | Logic tính số dư `rental-state-v3`. |
| **Projection/contract version** | Chỉ định nghĩa dữ liệu đọc hoặc hợp đồng công bố cho consumer. | `daily_cashflow_v2` hoặc `DepositCapturedPublic.v2`. |

Chúng **không tăng cùng nhau**. Một aggregate ở stream version 100 có thể chứa event schema v1, v2 và v3; một projection v2 có thể được dựng từ chính các event đó với cách tính được phê duyệt. Đổi schema của một event không nhất thiết làm tăng version của toàn bộ read model, nhưng cũng không được mặc định là không ảnh hưởng.

Ví dụ envelope của event tại vị trí 37:

~~~json
{
  "event_id": "7e6066df-9a60-43f1-87de-4f7e2eb803cc",
  "aggregate_type": "Rental",
  "aggregate_id": "RENT-204",
  "stream_version": 37,
  "event_type": "DepositCaptured",
  "event_schema_version": 1,
  "occurred_at": "2026-02-18T03:05:00Z",
  "recorded_at": "2026-02-18T03:05:03Z",
  "payload": {
    "amount_minor": 200000,
    "currency": "VND",
    "provider_tx_id": "GW-811"
  }
}
~~~

`stream_version = 37` là vị trí trong luồng `Rental`; `event_schema_version = 1` cho biết phải áp dụng định nghĩa v1 của `DepositCaptured`. `occurred_at` là thời điểm nghiệp vụ theo nguồn được xác nhận, còn `recorded_at` là lúc hệ thống lưu event. Cả hai là thời điểm, **không phải phiên bản**.

## 3. Tiến hóa cấu trúc khác với thay đổi ý nghĩa nghiệp vụ

Thay đổi **schema** thường liên quan tên trường, kiểu dữ liệu, trường bắt buộc/tùy chọn, enum, cách lồng đối tượng hoặc đơn vị. Thay đổi **ngữ nghĩa** là thay đổi điều mà một sự kiện hay trường **thực sự khẳng định**.

| Thay đổi đề xuất | Phân loại | Mức rủi ro |
| --- | --- | --- |
| Bổ sung `payment_channel` tùy chọn vào `DepositCaptured`. | Thay đổi cấu trúc bổ sung. | Thường quản lý được nếu reader cũ cho phép trường mới. |
| Đổi `provider_tx_id` thành `provider_reference` với **cùng ý nghĩa**. | Đổi tên cấu trúc. | Cần mapping/alias hoặc phiên bản mới. |
| Đổi `amount_minor` từ số nguyên sang chuỗi có dấu phân cách. | Thay đổi kiểu. | Có thể phá reader, index và phép tính. |
| Đổi tiền từ **đơn vị nhỏ nhất** sang **đơn vị lớn** nhưng giữ tên trường. | Thay đổi ngữ nghĩa/đơn vị. | Rất nguy hiểm; cùng giá trị có thể mang số tiền khác. |
| Đổi `PaymentRequested` thành `PaymentCaptured` mà không có xác nhận từ nhà cung cấp. | Thay đổi ý nghĩa sự kiện. | Không hợp lệ nếu coi yêu cầu là đã thu tiền. |
| Thêm một giá trị enum `PARTIALLY_REFUNDED`. | Mở rộng tập giá trị hợp lệ. | Consumer switch exhaustiveness có thể lỗi hoặc bỏ qua. |
| Tách `RentalClosed` thành `EquipmentReturned` và `FinanciallySettled`. | Thay đổi ranh giới sự thật nghiệp vụ. | Cần quy tắc migration/diễn giải cũ, không chỉ đổi field. |

**Quy tắc quan trọng:** tăng `event_schema_version` có thể làm mã đọc hiểu một biểu diễn mới, nhưng **không tự hợp pháp hóa việc đổi nghĩa**. Nếu tiêu chí “thanh toán thành công” đã thay từ “đã gửi yêu cầu” sang “provider xác nhận capture”, những bản ghi cũ không được tự động coi là các lần capture thực.

### Cần định nghĩa từng sự kiện bằng một câu đầy đủ

Ví dụ hợp đồng event:

> `DepositCaptured`: nhà cung cấp thanh toán có thẩm quyền đã xác nhận khoản tiền cọc được thu thành công với mã giao dịch duy nhất, giá trị và tiền tệ được lưu tại thời điểm xác nhận.

Định nghĩa này phải đi cùng **điểm chốt sự thật**, nguồn xác nhận, quy tắc chống trùng và schema trường. Nếu trong lịch sử, event cũ được phát ngay khi gửi lệnh thu tiền, hai cách gọi tuy giống tên nhưng có ý nghĩa khác nhau. Cần phân loại hoặc diễn giải các bản ghi đó theo sự thật đã biết, không biến chúng thành thành công bằng một phép đổi tên.

## 4. Tương thích ngược, tương thích xuôi và phạm vi hợp đồng

Có hai phép thử phổ biến:

- **Backward compatibility (theo định nghĩa reader):** reader **mới** có thể đọc dữ liệu được writer **cũ** ghi.
- **Forward compatibility:** reader **cũ** có thể đọc dữ liệu do writer **mới** ghi.
- **Full compatibility:** cả hai chiều đáp ứng quy tắc đã chọn.

Tên gọi và cách kiểm tra của từng schema registry/framework có thể khác; luôn đọc quy ước cụ thể của công cụ. Ở đây dùng định nghĩa reader/writer nói trên để làm rõ bài toán.

Giả sử v1 có `amount_minor` và `currency`. v2 thêm `payment_channel`:

~~~json
{
  "amount_minor": 200000,
  "currency": "VND",
  "payment_channel": "BANK_TRANSFER"
}
~~~

Để reader v2 hiểu event cũ, cần có cách xử lý **trường không tồn tại**. Trong ví dụ, `payment_channel = null` hoặc `UNKNOWN` có thể phù hợp nếu nghiệp vụ cho phép một trạng thái “không biết”. **Không được mặc định `BANK_TRANSFER`** nếu sự kiện cũ không chứa bằng chứng.

Để reader v1 hiểu event mới, nó phải **chấp nhận và bỏ qua** trường bổ sung, hoặc hệ thống cần cung cấp một biểu diễn v1 riêng. Một reader v1 được cấu hình từ chối mọi trường lạ sẽ không forward compatible dù thay đổi chỉ là “thêm trường”.

| Cách đổi schema | Reader mới đọc event cũ | Reader cũ đọc event mới | Điều kiện cần chú ý |
| --- | --- | --- | --- |
| Thêm trường tùy chọn | Thường có thể. | Chỉ nếu bỏ qua/cho phép trường lạ. | Giá trị thiếu phải mang nghĩa hợp lệ. |
| Thêm trường bắt buộc không có default hợp lệ | Thường lỗi. | Tùy cách reader kiểm tra. | Không bịa default để hợp thức hóa dữ liệu. |
| Xóa trường | Reader mới phải không cần trường đó hoặc có adapter. | Reader cũ có thể thiếu dữ liệu cần thiết. | Kiểm tra consumer và read model. |
| Đổi tên trường | Cần alias/mapping hoặc version mới. | Cần mapping ngược nếu vẫn phải phục vụ cũ. | Giữ chính xác nghĩa, đơn vị. |
| Đổi kiểu/đơn vị | Cần chuyển đổi được chứng minh. | Có thể không parse/diễn giải đúng. | Vấn đề còn nằm ở số học/precision. |
| Thêm enum value | Reader mới thường hỗ trợ. | Reader cũ có thể gặp giá trị không biết. | Phải có policy cho unknown enum. |
| Đổi nghĩa event | Không được chỉ xử lý như schema rename. | Không được chỉ xử lý như schema rename. | Cần hợp đồng nghiệp vụ và kế hoạch migration. |

**Không có “thay đổi thêm trường nào cũng an toàn” một cách tuyệt đối.** Kết quả phụ thuộc kiểu serialization (JSON, Avro, Protobuf...), chính sách required/default, chế độ validation, cách consumer parse và cam kết của hợp đồng.

## 5. Ví dụ xuyên suốt: tiến hóa `DepositCaptured` từ v1 sang v2

Giả sử hợp đồng v1 đã được xác nhận:

~~~json
{
  "event_type": "DepositCaptured",
  "event_schema_version": 1,
  "payload": {
    "amount_minor": 200000,
    "currency": "VND",
    "provider_tx_id": "GW-811"
  }
}
~~~

Yêu cầu nghiệp vụ mới muốn:

- Tên rõ ràng hơn: `provider_reference` thay cho `provider_tx_id`.
- Ghi kênh thanh toán `payment_channel`, nhưng **event lịch sử có thể không có thông tin này**.
- Giữ nguyên định nghĩa “tiền đã được capture thành công”, số tiền nguyên đơn vị nhỏ nhất, mã tiền ISO phù hợp.
- Không thay đổi ID và thứ tự của event trong stream.

Biểu diễn v2:

~~~json
{
  "event_type": "DepositCaptured",
  "event_schema_version": 2,
  "payload": {
    "amount_minor": 200000,
    "currency": "VND",
    "provider_reference": "GW-811",
    "payment_channel": "BANK_TRANSFER"
  }
}
~~~

Chính sách diễn giải phải ghi rõ rằng `provider_tx_id` v1 và `provider_reference` v2 **chỉ là hai tên của cùng loại định danh**. Nếu v1 thực tế là “ID yêu cầu”, còn v2 là “ID giao dịch đã quyết toán”, chúng **không thể** được đổi tên đơn giản.

Đối với event v1 không biết kênh thanh toán, biểu diễn chuẩn trong bộ nhớ có thể là:

~~~json
{
  "amount_minor": 200000,
  "currency": "VND",
  "provider_reference": "GW-811",
  "payment_channel": null
}
~~~

`null` ở đây có nghĩa **không có thông tin trong nguồn lịch sử**, không có nghĩa thanh toán không sử dụng kênh nào. Một dashboard theo kênh phải có nhóm “không xác định”, thay vì âm thầm gán toàn bộ dữ liệu cũ vào một kênh và làm sai thống kê.

### Khi nào không được upcast tự động?

Giả sử hệ thống từng có event `PaymentRecorded.v1` với payload:

~~~json
{
  "amount": 200000,
  "status": "SUCCESS"
}
~~~

Không có tài liệu nói `amount` là đồng hay xu, `SUCCESS` là ngân hàng xác nhận hay chỉ hệ thống nhận request. Việc đổi nó thẳng thành `DepositCaptured.v2` là **đoán ý nghĩa**. Cách xử lý phù hợp hơn là:

1. Khôi phục hợp đồng v1, code/biên bản và dữ liệu đối soát có thẩm quyền trong phạm vi được phép.
2. Nếu có thể xác minh ý nghĩa, viết quy tắc chuyển đổi **có tài liệu và ca kiểm thử**.
3. Nếu không xác minh được, giữ trạng thái legacy/unknown có ý nghĩa rõ; các chỉ số nhạy cảm phải tách nhóm hoặc yêu cầu đối soát thủ công.
4. Nếu cần điều chỉnh nghiệp vụ sau khi có bằng chứng mới, ghi một **correction/confirmation event** phù hợp, thay vì sửa âm thầm lịch sử nguồn.

**Không được bịa giờ, đơn vị, người thực hiện, giao dịch hay nguồn xác nhận** chỉ để làm payload cũ khớp schema mới.

## 6. Upcasting: chuyển biểu diễn cũ thành dạng đọc chuẩn

**Upcaster** là hàm chuyển event có phiên bản cũ sang dạng biểu diễn mới dùng trong bộ nhớ. Nó thường nằm tại ranh giới đọc event store trước khi gửi event cho reducer/projector.

~~~mermaid
flowchart LR
    ES[("Event store: event thô bất biến")] --> D["Giải mã theo event_type + schema_version"]
    D --> U["Upcaster v1 → v2 (nếu cần)"]
    U --> V["Kiểm tra hợp đồng biểu diễn chuẩn"]
    V --> R["Reducer / projector"]
    R --> S[("State / read model")]
~~~

Điểm quan trọng là **upcaster không cần cập nhật dữ liệu thô đã lưu**. Event gốc vẫn có `event_schema_version = 1`, giúp bảo tồn lịch sử và kiểm tra cách diễn giải. Cơ chế chuyển đổi chỉ xảy ra khi đọc.

### Ví dụ logic upcaster

~~~text
upcast_DepositCaptured(event):
    require event.type == "DepositCaptured"

    if event.schema_version == 1:
        require event.payload.amount_minor is a valid integer >= 0
        require event.payload.currency is a supported currency code
        require event.payload.provider_tx_id is non-empty

        return CanonicalDepositCaptured(
            amount_minor = event.payload.amount_minor,
            currency = event.payload.currency,
            provider_reference = event.payload.provider_tx_id,
            payment_channel = UNKNOWN
        )

    if event.schema_version == 2:
        validate v2 fields, types and business constraints
        return CanonicalDepositCaptured(
            amount_minor = event.payload.amount_minor,
            currency = event.payload.currency,
            provider_reference = event.payload.provider_reference,
            payment_channel = event.payload.payment_channel or UNKNOWN
        )

    fail with UnsupportedEventVersion
~~~

Mã giả này dùng `UNKNOWN` như **giá trị thể hiện thiếu thông tin** trong canonical model; khi triển khai cần quy ước rõ `UNKNOWN`, `null` và chuỗi rỗng khác nhau thế nào.

### Các tính chất cần giữ

- **Tất định:** cùng event v1 và cùng phiên bản upcaster luôn tạo cùng biểu diễn chuẩn.
- **Không side effect:** không thu/hoàn tiền, gửi email hoặc append event mới trong quá trình replay.
- **Không phụ thuộc dữ liệu dễ biến đổi:** không lấy bảng phí hiện tại hoặc tên kênh thanh toán hiện tại để viết lại sự thật năm trước.
- **Không làm mất định danh:** giữ `event_id`, `aggregate_id`, `stream_version`, `occurred_at`; nếu tạo metadata diễn giải mới, phải phân biệt với metadata gốc.
- **Không bỏ qua version lạ:** fail có kiểm soát và quan sát được; bỏ qua im lặng event có tác động tới số dư sẽ khiến state sai.
- **Có thể xâu chuỗi:** khi có v1 → v2 → v3, có thể áp dụng chuỗi chuyển đổi hoặc chuyển trực tiếp sang canonical model, nhưng phải kiểm thử cả đường đi và giới hạn vòng đời.

Một upcaster chỉ nên làm việc với **cấu trúc/ý nghĩa đã được chứng minh**. Nếu v2 bổ sung một dữ kiện bắt buộc để ra quyết định tài chính mà v1 không có, upcaster không thể tạo ra sự thật mới. Cần điều chỉnh mô hình đọc, thu thập bằng chứng bổ sung có kiểm soát, hoặc chấp nhận rằng một số truy vấn lịch sử không có đủ dữ liệu.

## 7. Đọc nhiều phiên bản trực tiếp hay dùng upcaster?

Có hai cách phổ biến để ứng dụng đọc sự kiện cũ:

**Cách A — version-specific readers:** mỗi phiên bản event có decoder và handler riêng; reducer có thể xử lý v1 và v2 với các nhánh điều kiện.

**Cách B — canonical representation/upcasting:** decoder đọc event đúng schema gốc, sau đó chuyển các version cũ sang một kiểu sự kiện chuẩn trước khi reducer xử lý.

| Tiêu chí | Reader theo từng version | Upcaster sang dạng chuẩn |
| --- | --- | --- |
| Vị trí xử lý khác biệt | Trong từng handler. | Tại ranh giới đọc event. |
| Độ phức tạp reducer | Có thể tăng theo số version. | Thường đơn giản hơn khi đã chuẩn hóa. |
| Khả năng giữ đúng lịch sử | Tốt nếu mọi handler được duy trì. | Tốt nếu conversion đúng nghĩa, không bịa dữ kiện. |
| Nguy cơ | Logic tính rải rác, khác nhau giữa projection. | Chuẩn hóa sai làm mọi consumer cùng hiểu sai. |
| Phù hợp | Ít version, khác biệt nghiệp vụ có chủ ý. | Nhiều thay đổi cấu trúc có ánh xạ hợp lệ. |

Có thể dùng **kết hợp**: upcast những khác biệt thuần kỹ thuật, còn xử lý **ngữ nghĩa khác nhau** bằng kiểu event hoặc handler riêng. Không ép mọi sự kiện cũ vào một canonical event nếu điều đó làm mất dấu khác biệt nghiệp vụ.

### Ví dụ trong Java: canonical type an toàn

Một thiết kế theo Java có thể dùng kiểu dữ liệu riêng cho sự kiện đã được chuẩn hóa:

~~~java
record DepositCapturedCanonical(
    long amountMinor,
    String currency,
    String providerReference,
    String paymentChannel // null means unknown in this contract
) {}

final class DepositCapturedUpcaster {
    static DepositCapturedCanonical fromV1(
            long amountMinor,
            String currency,
            String providerTxId
    ) {
        if (amountMinor < 0
                || currency == null || currency.isBlank()
                || providerTxId == null || providerTxId.isBlank()) {
            throw new IllegalArgumentException("Invalid historical event");
        }
        return new DepositCapturedCanonical(
                amountMinor, currency, providerTxId, null);
    }

    static DepositCapturedCanonical fromV2(
            long amountMinor,
            String currency,
            String providerReference,
            String paymentChannel
    ) {
        if (amountMinor < 0
                || currency == null || currency.isBlank()
                || providerReference == null || providerReference.isBlank()) {
            throw new IllegalArgumentException("Invalid event");
        }
        return new DepositCapturedCanonical(
                amountMinor, currency, providerReference, paymentChannel);
    }
}
~~~

Đây là ví dụ **phần chuyển đổi sau khi dữ liệu đã được deserialize**, không phải toàn bộ serializer, validator hay event store. Ứng dụng thực tế phải kiểm tra thêm loại tiền được hỗ trợ, độ lớn số tiền, quyền hạn và các bất biến nghiệp vụ. `null` cho kênh thanh toán cũ chỉ được dùng nếu định nghĩa canonical type cho phép “không biết”.

## 8. Không đổi ý nghĩa lịch sử khi replay bằng mã mới

Trong event sourcing, trạng thái được tính bằng cách áp dụng event theo thứ tự stream. Khi nâng cấp chương trình, **cùng event gốc** có thể đi qua reducer mới. Có hai mục tiêu cần phân biệt:

- **Khôi phục trạng thái theo đúng quyết định/tính toán lịch sử:** cần các quy tắc và dữ kiện đã từng được dùng hoặc cơ chế tương thích tương đương.
- **Tạo một góc nhìn mới theo định nghĩa đã cập nhật:** có thể xây projection mới từ event cũ, nhưng phải công bố rằng **quy tắc tính và ý nghĩa chỉ số đã thay đổi**.

Ví dụ năm trước, dashboard tính `gross_captured` là tổng sự kiện capture. Nay đội tài chính muốn `net_cashflow = captured - refunded`. Không nên thay tên trường `revenue` ở dashboard cũ rồi để người dùng mặc định hai số cùng nghĩa. Tạo hoặc version hóa projection, định nghĩa chính sách về hoàn một phần, ngày nghiệp vụ và đơn vị tiền.

### Thay đổi ý nghĩa event có thể cần event type mới

Giả sử trước đây `RentalReturned` được phát khi khách **bấm nút yêu cầu trả**, nhưng nay quy trình chỉ công nhận “trả xong” sau **nghiệm thu tại kho**. Hai điểm chốt khác nhau:

- Lịch sử cũ `RentalReturned` thực chất là **ReturnRequested** theo định nghĩa cũ.
- Sự kiện mới nên là **EquipmentReturnAccepted** sau bằng chứng nghiệm thu.

Không nên upcast mọi `RentalReturned.v1` sang `EquipmentReturnAccepted.v2`, vì không có bằng chứng đã nghiệm thu. Có thể giữ handler legacy, ánh xạ sang `ReturnRequestedLegacy` trong mô hình phân tích, hoặc ghi event xác nhận mới sau đối soát nếu nghiệp vụ yêu cầu. Đó là **tiến hóa cách hiểu miền**, không phải đổi tên JSON thông thường.

### Dữ liệu đến muộn và thời điểm hồi tố

`stream_version` xác định thứ tự đã được hệ thống chấp nhận trong một stream; `occurred_at` phản ánh lúc sự việc diễn ra theo nguồn xác nhận, `recorded_at` là lúc lưu. Event về sự việc đã xảy ra hôm qua có thể được append hôm nay với version mới. Khi replay aggregate, không đảo thứ tự stream dựa trên timestamp. Nếu cần “hệ thống biết gì ở thời điểm X” và “thực tế có hiệu lực lúc X theo chứng cứ hiện có”, phải định nghĩa các chiều thời gian riêng, có thể cần mô hình bitemporal.

## 9. Event store vật lý và cách gắn hợp đồng schema

Trong PostgreSQL, có thể lưu envelope có kiểu rõ và payload `JSONB`. Cách này linh hoạt nhưng **không tự kiểm chứng cấu trúc của mọi phiên bản event**.

~~~sql
CREATE TABLE event_stream (
    tenant_id        UUID NOT NULL,
    aggregate_type   VARCHAR(80) NOT NULL,
    aggregate_id     VARCHAR(100) NOT NULL,
    current_version  BIGINT NOT NULL DEFAULT 0
                     CHECK (current_version >= 0),
    PRIMARY KEY (tenant_id, aggregate_type, aggregate_id)
);

CREATE TABLE domain_event (
    event_id             UUID PRIMARY KEY,
    tenant_id            UUID NOT NULL,
    aggregate_type       VARCHAR(80) NOT NULL,
    aggregate_id         VARCHAR(100) NOT NULL,
    stream_version       BIGINT NOT NULL CHECK (stream_version > 0),
    event_type           VARCHAR(120) NOT NULL,
    event_schema_version SMALLINT NOT NULL
                         CHECK (event_schema_version > 0),
    occurred_at          TIMESTAMPTZ NOT NULL,
    recorded_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload              JSONB NOT NULL
                         CHECK (jsonb_typeof(payload) = 'object'),
    FOREIGN KEY (tenant_id, aggregate_type, aggregate_id)
        REFERENCES event_stream
            (tenant_id, aggregate_type, aggregate_id),
    UNIQUE (tenant_id, aggregate_type, aggregate_id, stream_version)
);

CREATE INDEX ix_domain_event_type_version
    ON domain_event (event_type, event_schema_version);
~~~

**Giải thích:**

- Khóa `(tenant_id, aggregate_type, aggregate_id)` xác định stream trong hệ đa tenant.
- `UNIQUE(tenant_id, aggregate_type, aggregate_id, stream_version)` bảo vệ một vị trí duy nhất mỗi stream; ứng dụng phải bảo đảm append có expected-version/transaction để giữ lịch sử liên tiếp, không chấp nhận quyết định trên state lỗi thời.
- `(event_type, event_schema_version)` xác định bộ decoder và contract cần dùng. Không thể chỉ dựa vào thứ tự stream để suy schema.
- `CHECK(jsonb_typeof(payload) = 'object')` không chứng minh trường `amount_minor` có mặt, là integer, có đơn vị đúng hay `provider_reference` không rỗng. Cần validation theo contract/version trước khi append và khi đọc.
- Chỉ mục theo loại/version hữu ích khi kiểm kê những event còn ở phiên bản cũ; phải cân đối chi phí ghi, kích thước dữ liệu và các truy vấn thực tế trước khi triển khai.

### Có nên thêm bảng quản lý schema?

Có thể dùng **schema registry** hoặc danh mục contract được version hóa (tại code/artifact, metadata store hay hệ thống schema chuyên dụng). Thông tin cần quản trị gồm:

| Trường hợp đồng | Ví dụ |
| --- | --- |
| Định danh | `event_type = DepositCaptured`, `schema_version = 2`. |
| Format | JSON Schema, Avro schema, Protobuf schema hoặc codec được công bố. |
| Các trường bắt buộc | `amount_minor`, `currency`, `provider_reference`. |
| Quy tắc dữ liệu | Số tiền, loại tiền, ID, enum, đơn vị và quan hệ giữa trường. |
| Ngữ nghĩa | Điều kiện event được phát, nguồn có thẩm quyền, thời điểm sử dụng. |
| Chính sách tương thích | Reader/writer nào còn được hỗ trợ; điều gì bị coi là breaking change. |
| Retention/riêng tư | Trường nào nhạy cảm, thời hạn lưu và chính sách redaction. |

Schema registry chỉ giúp quản trị **hình thức và một phần tương thích**; nó không tự biết `PaymentCaptured` trong nghiệp vụ có nghĩa là tiền đã vào tài khoản hay chưa. Vì vậy định nghĩa event và các bất biến cần được tài liệu hóa cùng schema.

### Điều gì xảy ra khi cần thay kiểu lưu trữ?

Một event store quan hệ có thể tạo read model dạng document, đồ thị hoặc bảng phân tích. Đổi cấu trúc bảng hay đường truyền không được âm thầm đổi payload của event lịch sử. Với tài liệu JSON, cần version hóa cấu trúc và validation tương tự; với kho phân tích, cần thống nhất ngày nghiệp vụ, khóa dedup và quy tắc điền thiếu. Chọn công nghệ theo yêu cầu truy vấn, tính nhất quán và chi phí vận hành, không dùng “schema-on-read” như lý do bỏ qua hợp đồng dữ liệu.

## 10. Tiến hóa domain event và integration event không giống nhau

**Domain event** là sự thật được định nghĩa trong ranh giới nghiệp vụ nguồn; hợp đồng của nó phục vụ quyết định và replay nội bộ. **Integration event** là thông điệp được công bố cho hệ thống khác; nó có người dùng và vòng đời tương thích riêng.

Một domain event `DepositCaptured.v2` có thể tạo ra integration event `RentalDepositReceived.v1` cho hệ thống CRM. Hai event có thể dùng tên, payload và version khác nhau:

~~~mermaid
flowchart LR
    C["Command thành công"] --> D["Domain event DepositCaptured.v2"]
    D --> E[("Event store nguồn")]
    D --> O["Outbox/mapper hợp đồng công bố"]
    O --> I["Integration event RentalDepositReceived.v1"]
    I --> N["Consumer: CRM"]
    I --> A["Consumer: Analytics"]
~~~

Tách hai hợp đồng có một số lợi ích:

- Cho phép đổi cách lưu trong domain mà không buộc CRM cập nhật ngay.
- Loại bỏ trường nội bộ hoặc thông tin nhạy cảm khỏi payload công bố.
- Phát thông điệp ở **mốc nghiệp vụ đủ chắc chắn**, không vội công bố trạng thái trung gian.
- Cho phép version/policy tương thích riêng cho consumer.

Một thay đổi domain event không nhất thiết làm thay đổi integration event; ngược lại, có thể tạo integration event v2 vì consumer cần thêm trường, dù domain event không đổi. Nếu phải đồng thời phục vụ consumer cũ và mới, có thể dùng **dual publishing theo hợp đồng** (hai loại thông điệp có version rõ) trong thời gian chuyển đổi. Phải xác định rằng chúng mô tả **cùng một sự việc**, để consumer không tính hai lần.

Khi phát qua broker/outbox, cần idempotency, retry, khả năng message đến muộn và cách phân biệt ID của domain event với message ID. Việc thay version không tự bảo đảm gửi đúng một lần xuyên suốt mọi hệ thống.

## 11. Chiến lược triển khai thay đổi schema an toàn

Một kế hoạch có kiểm soát nên bắt đầu từ **kiểm kê dữ liệu và consumer hiện hữu** trước khi đổi writer.

### Giai đoạn A — Khảo sát và thiết kế hợp đồng

1. Liệt kê các event type và version thực tế trong event store; đếm số bản ghi từng version và khoảng thời gian xuất hiện.
2. Xác định consumer: command state loader, projector, báo cáo, integration mapper, bộ tái tạo dữ liệu, công cụ vận hành.
3. Thu thập **mẫu event lịch sử thực** cho v1, gồm cả trường thiếu, giá trị khác thường và các ca đã từng sửa sai.
4. Đề xuất v2 với **schema và định nghĩa ngữ nghĩa**; phân loại breaking/additive và dữ kiện nào không thể suy ra từ v1.
5. Viết mapping/upcaster hoặc xử lý riêng v1; định nghĩa kiểm tra bất biến và cách đối chiếu.

### Giai đoạn B — Triển khai reader trước writer (khi phù hợp)

1. Triển khai reader có thể hiểu **cả v1 và v2** hoặc chuyển v1 sang dạng chuẩn an toàn.
2. Chạy thử replay trên dữ liệu mẫu; kiểm tra state cuối, tiền tệ, số tiền, timestamp và các mốc nghiệp vụ.
3. Đảm bảo các projector/consumer quan trọng đã tương thích. Với consumer bên ngoài, thống nhất lịch chuyển đổi và cơ chế giữ hợp đồng v1 nếu cần.
4. Chỉ sau đó cho writer phát event schema v2; tiếp tục theo dõi tỷ lệ lỗi giải mã, version không hỗ trợ và độ trễ projection.

Thứ tự “reader trước writer” giúp giảm rủi ro trong kiến trúc có thể triển khai tách rời, nhưng không phải quy tắc đủ cho mọi thay đổi. Một số hệ thống cần **dual write/dual publish**, cờ tính năng hoặc cô lập consumer; việc giữ hai hợp đồng phải có chiến lược dedup và thời hạn kết thúc rõ.

### Giai đoạn C — Xây lại read model khi cần

Nếu thay đổi schema chỉ bổ sung trường không ảnh hưởng logic cũ, có thể không cần rebuild projection. Nếu logic tính state hoặc KPI được thay đổi, nên:

1. Tạo projection mới có tên/version rõ ràng thay vì ghi đè trực tiếp bảng đang phục vụ.
2. Replay lịch sử bằng reader có hỗ trợ event cũ.
3. Bắt kịp sự kiện mới qua nguồn có cursor/checkpoint an toàn theo **thứ tự commit**; không suy từ ID được cấp trước commit mà mặc định đã không bỏ sót.
4. Kiểm chứng độc lập với bất biến và dữ liệu nguồn.
5. Chuyển luồng đọc sang projection mới có kiểm soát, giữ khả năng rollback khi cần.

Nếu snapshot aggregate đang lưu state theo reducer cũ, nó có thể **không dùng được** cho logic mới. Hãy quyết định migrate snapshot với chứng minh tương đương hoặc bỏ ảnh cũ và replay từ event nguồn, rồi tạo snapshot mới.

### Giai đoạn D — Loại bỏ dần hỗ trợ cũ khi thực sự an toàn

Không xóa decoder v1 chỉ vì writer đã ngừng phát v1. Nếu event v1 vẫn còn trong kho, một lần rebuild hoặc mở aggregate lâu không hoạt động vẫn có thể cần đọc nó. Chỉ bỏ hỗ trợ khi:

- Đã có migration bền vững và được kiểm chứng, hoặc dữ liệu v1 không còn trong phạm vi phải đọc theo chính sách.
- Mọi consumer, snapshot và projection liên quan đã được xử lý.
- Đã có kế hoạch backup/rollback và chứng minh không mất khả năng hiểu lịch sử cần giữ.

## 12. Kiểm chứng đúng dữ liệu cũ, không chỉ đúng JSON mới

Bộ kiểm thử nên bao phủ **dữ liệu lịch sử** và **hành vi nghiệp vụ**.

| Kiểm thử | Mục tiêu | Dấu hiệu lỗi |
| --- | --- | --- |
| **Contract v1/v2** | Mỗi event parse theo đúng schema đã ghi. | Reader mới từ chối event v1 hợp lệ. |
| **Missing fields** | Trường mới không có trong event cũ được biểu diễn đúng. | Tự điền một kênh thanh toán không có bằng chứng. |
| **Rename/units** | Mapping giữ nguyên giá trị và ý nghĩa. | 200.000 VND bị nhân/chia 100 không có quy tắc. |
| **Unknown version/enum** | Lỗi rõ và được quan sát. | Bỏ qua event thay đổi số dư. |
| **Replay equivalence** | Reducer mới trên dữ liệu có nghĩa không đổi tạo state dự kiến. | Số dư hoặc trạng thái đổi vì upcaster sai. |
| **Legacy semantics** | Event có nghĩa cũ được nhận diện riêng. | `PaymentRequested` bị coi là `PaymentCaptured`. |
| **Correction/reversal** | Tham chiếu, số tiền điều chỉnh và thứ tự hợp lệ. | Đảo hai lần cùng nghĩa vụ hoặc bỏ mất correction. |
| **Snapshot compatibility** | Nạp snapshot + tail bằng reducer tương thích. | State khác replay đầy đủ ở cùng version. |
| **Cross-service contract** | Consumer cũ/mới nhận đúng sự kiện công bố. | Dual publish làm tăng doanh thu hai lần. |
| **Privacy/retention** | Trường nhạy cảm không rò vào integration payload. | Event công bố nguyên đối tượng nội bộ. |

### Golden fixtures và replay test

Dùng tập **golden fixtures** đã được ẩn danh/hợp lệ hóa từ event thực tế, bao gồm:

- Stream ngắn chỉ có v1.
- Stream chuyển tiếp từ v1 sang v2.
- Event tùy chọn thiếu trường, enum legacy và ID nguồn khác định dạng mới.
- Stream có correction hồi tố, hoàn một phần, nhiều lần thu/hoàn.
- Stream đã có snapshot được tạo bằng reducer cũ.

Với từng mẫu, ghi rõ **kết quả dự kiến được nghiệp vụ xác nhận**: trạng thái, tổng tiền, đồng tiền, mốc thời gian và những thông tin vẫn ở trạng thái “không biết”. Không chỉ snapshot JSON đầu ra rồi coi mọi thay đổi là bug; khi mục đích là sửa logic projection, cần kiểm chứng với sự thật nguồn và định nghĩa mới, không ép kết quả bằng bản sai cũ.

Một ví dụ test logic:

~~~text
given event DepositCaptured.v1:
    amount_minor = 200000
    currency = VND
    provider_tx_id = GW-811

when decoded and upcasted by reader v2

then canonical.amount_minor == 200000
and  canonical.currency == VND
and  canonical.provider_reference == GW-811
and  canonical.payment_channel == UNKNOWN
and  event_id / stream_version remain unchanged
and  no network or database writes occur
~~~

**Test lịch sử không được phát side effect.** Chạy replay phải không gọi API thanh toán, không gửi email, không viết lại event store. Kiểm tra sự khác biệt giữa trạng thái dựng từ event và read model hiện hữu, đồng thời tính đến khả năng read model cũ đã có bug.

## 13. Khi nào nên migrate event gốc và khi nào không?

Một số đội cân nhắc chuyển đổi toàn bộ event v1 thành v2 trong kho lưu trữ để bỏ code cũ. Cách này có thể phù hợp trong dự án migration được kiểm soát, nhưng **khác với upcasting khi đọc** và có rủi ro lớn:

| Phương án | Ưu điểm | Giới hạn/cảnh báo |
| --- | --- | --- |
| **Giữ event gốc + upcast khi đọc** | Bảo tồn dấu vết, dễ rollback reader, không rewrite toàn lịch sử. | Giữ code chuyển đổi, tốn CPU khi replay lớn; cần test lâu dài. |
| **Giữ event gốc + đọc nhiều version** | Bám sát ngữ nghĩa từng version; ít ép ánh xạ. | Reducer/projector phức tạp theo số version. |
| **Materialize canonical copy** | Đọc nhanh, giảm chi phí chuyển đổi lặp ở một số read path. | Copy phải có lineage/ID nguồn, kiểm soát sync; không thay thế event gốc mà không quyết định rõ. |
| **Rewrite/migrate event store** | Có thể chuẩn hóa dữ liệu vật lý và bỏ biểu diễn cũ. | Rủi ro phá audit, signature, checksum, thứ tự, replication và khả năng diễn giải; cần quy trình kiểm chứng cực kỳ chặt. |

**Không sửa âm thầm payload v1 thành v2 rồi giữ nguyên `event_id`/timestamp** như thể chưa từng thay đổi. Nếu phải rewrite để đáp ứng yêu cầu pháp lý hoặc sửa hỏng dữ liệu, phải tách quy trình quản trị: backup, hồ sơ mapping, phạm vi ảnh hưởng, kiểm chứng dữ liệu, cập nhật snapshot/projection và chính sách truy vết nguồn. Nếu là **sự thật nghiệp vụ đã được công nhận nhưng sau đó phát hiện sai**, thường cần **correction event** phù hợp thay vì sửa lịch sử không dấu vết.

**Quyền riêng tư là ràng buộc riêng:** nguyên tắc append-only không cho phép giữ thông tin cá nhân vô thời hạn nếu không phù hợp pháp lý/chính sách. Định danh tham chiếu, tách dữ liệu nhạy cảm, phân quyền, retention, mã hóa và xóa/ẩn danh có kiểm soát nên được thiết kế từ đầu; một số cách xử lý có thể làm giới hạn khả năng replay và phải được công bố.

## 14. Các sai lầm phổ biến khi tiến hóa sự kiện

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Chỉ kiểm tra JSON parse được | Reader có thể dùng sai đơn vị hoặc nghĩa nghiệp vụ. | Version schema và định nghĩa ngữ nghĩa cùng bất biến. |
| Dùng `stream_version` làm phiên bản payload | Decoder chọn sai schema. | Tách `stream_version` và `event_schema_version`. |
| Gán default “cho đẹp” khi v1 thiếu dữ kiện | Thống kê lịch sử sai một cách im lặng. | Dùng unknown hoặc đối soát nguồn đáng tin. |
| Đổi `Requested` thành `Completed` chỉ bằng rename | Biến ý định thành kết quả thành công. | Event type riêng, tiêu chí chấp nhận riêng. |
| Xóa decoder cũ khi writer đổi v2 | Replay/khôi phục stream cũ thất bại. | Giữ reader tương thích suốt vòng đời dữ liệu. |
| Upcaster gọi API hiện tại để điền trường cũ | Replay không tất định, có thể dùng dữ liệu đã đổi. | Chỉ dùng event và nguồn tham chiếu bất biến có version. |
| Upcaster bỏ qua event chưa biết | Mất số dư hoặc sai bất biến mà không báo lỗi. | Dừng/đưa vào luồng xử lý lỗi được kiểm soát. |
| Thêm enum mới mà không xét consumer switch | Consumer cũ gặp trường hợp không xử lý. | Kiểm thử tương thích và quy tắc unknown enum. |
| Rebuild từ snapshot cũ không tương thích | State được tính theo hai logic khác nhau. | Version reducer, migrate được chứng minh hoặc replay từ đầu. |
| Dual publish không có correlation/dedup | Consumer tính cùng nghiệp vụ hai lần. | Hợp đồng version, event/source ID và chính sách consumer. |
| Thay đổi KPI nhưng không đổi tên/version | Báo cáo hai thời kỳ khó so sánh. | Contract projection và mốc migration rõ ràng. |
| Chỉ kiểm thử dữ liệu mới | Hàng triệu event cũ lỗi khi deploy. | Golden fixtures và replay các stream lịch sử đa dạng. |

## 15. Bài tập: thiết kế lộ trình tiến hóa không mất nghĩa lịch sử

**Bối cảnh:** hệ thống quản lý giao hàng đã hoạt động nhiều năm. Event `DeliveryUpdated.v1` có payload:

~~~json
{
  "shipment_id": "SHP-204",
  "status": "DONE",
  "time": "2026-08-20 10:30",
  "operator": "EMP-17"
}
~~~

Nay nhóm nghiệp vụ muốn phân biệt: **tài xế thông báo giao**, **khách xác nhận nhận**, **giao thất bại** và **hàng được trả lại kho**. Hệ thống mới muốn event `DeliveryAttempted`, `DeliverySucceeded`, `DeliveryFailed`, `ReturnToWarehouseConfirmed`; các trường thời gian phải có múi giờ rõ và event được dùng cho báo cáo SLA.

### Yêu cầu

1. **Đọc lại định nghĩa cũ:** liệt kê những điều chưa biết từ `DeliveryUpdated.v1`. `DONE` có nghĩa tài xế bấm xong hay người nhận xác nhận? Chuỗi giờ thuộc múi giờ nào, có daylight saving hoặc thiết bị offline không? `operator` là người giao hay người nhập liệu?
2. **Xác định ranh giới nghiệp vụ:** mỗi event mới được phát khi nào, actor/subject/aggregate là ai, bằng chứng và nguồn xác nhận nào đủ?
3. **Phân loại migration:** trường nào có thể ánh xạ chắc chắn từ v1; trường nào không thể tự suy ra và cần giữ trạng thái legacy/unknown?
4. **Hợp đồng version:** thiết kế envelope chứa `event_id`, `aggregate_id`, `stream_version`, `event_type`, `event_schema_version`, `occurred_at`, `recorded_at`, cùng payload mới đủ nghĩa.
5. **Chọn chiến lược đọc:** viết upcaster cho các phép đổi cấu trúc an toàn; giữ reader riêng hoặc các trường legacy cho sự kiện mơ hồ về nghiệp vụ.
6. **Thiết kế projection mới:** tính tỷ lệ giao thành công theo số **lượt giao thực tế**, SLA theo thời điểm nghiệp vụ có nguồn đáng tin, và tỷ lệ event legacy không thể xác định. Không trộn “không biết” vào “giao thành công”.
7. **Lộ trình triển khai:** reader trước writer, mapping integration event, compatibility tests, rebuild song song, đối chiếu và chuyển nguồn đọc; nêu khi nào có thể ngừng hỗ trợ v1.
8. **Kiểm thử:** ít nhất một stream chỉ v1, một stream cả v1/v2, một lần giao thất bại rồi giao lại thành công, một event đến trễ, và một event không có thông tin múi giờ.
9. **Giới hạn:** nếu đơn vị vận chuyển cũ không còn cung cấp chứng cứ giao hàng, nêu rõ phần lịch sử nào không thể “nâng cấp” thành kết quả đã xác minh.

### Bảng kiểm kết quả

| Tiêu chí | Mô hình đạt khi |
| --- | --- |
| **Đúng nghĩa lịch sử** | Không biến `DONE` mơ hồ thành giao hàng được khách xác nhận nếu không có chứng cứ. |
| **Phiên bản rõ** | Version của stream, schema event và projection độc lập, có hợp đồng. |
| **Tương thích** | Reader mới hiểu các dạng cũ hợp lệ, unknown được xử lý có chủ đích. |
| **Dữ liệu không bịa** | Thời điểm, tiền tệ, actor, đơn vị và trạng thái thiếu thông tin được công bố rõ. |
| **Replay** | Cùng nguồn và quy tắc diễn giải cho cùng kết quả; không phát side effect. |
| **Triển khai an toàn** | Có kiểm thử history, rebuild, đối chiếu, cutover và rollback. |
| **Mô hình vật lý** | Khóa stream/version, index và ràng buộc phục vụ truy vấn và kiểm kê version thực tế. |

**Kết luận:** tiến hóa cấu trúc sự kiện không chỉ là “đổi JSON v1 thành JSON v2”. Đó là quá trình giữ **khả năng hiểu đúng những gì đã được hệ thống ghi nhận**, kiểm soát sự khác biệt giữa schema và ý nghĩa nghiệp vụ, và bảo đảm các consumer hiện tại/tương lai dùng lịch sử theo một hợp đồng có thể kiểm chứng. Khi dữ liệu cũ không đủ chứng cứ, lựa chọn đúng là thể hiện giới hạn, không bịa thêm sự thật. Từ nền tảng đó, event store, projection, document, quan hệ và hệ thống phân tích mới có thể tiến hóa mà vẫn đáng tin cậy.
