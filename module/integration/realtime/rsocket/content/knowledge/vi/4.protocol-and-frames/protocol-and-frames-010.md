# Frame EXT, cờ IGNORE và cách xử lý phần mở rộng chưa hỗ trợ

RSocket định nghĩa các frame chuẩn để thiết lập kết nối, khởi tạo request, truyền payload, điều tiết luồng và báo lỗi. Khi một ứng dụng cần truyền thêm thông tin hoặc mở rộng hành vi giao thức, frame chuẩn có thể chưa đủ. **EXT (Extension) frame** cung cấp một điểm mở rộng có định danh để hai phía trao đổi dữ liệu theo một hợp đồng do extension quy định.

Điểm cần thiết kế cẩn thận là khả năng tương thích giữa các phiên bản. Một client mới có thể gửi extension mà server cũ chưa biết. Cờ **IGNORE** cho biết frame đó có thể được bỏ qua hay là yêu cầu mà bên nhận phải hiểu. Chọn đúng cờ giúp ứng dụng bổ sung tính năng mà không vô tình làm hỏng kết nối của các peer cũ.

## 1. EXT là gì và dùng khi nào?

EXT là frame có mã loại `0x3F`. Nó mang một **Extended Type** để xác định ý nghĩa của phần mở rộng, cùng phần metadata và/hoặc data theo định dạng mà extension đó quy định.

EXT không phải mô hình tương tác thứ năm bên cạnh Request-Response, Fire-and-Forget, Request-Stream và Request-Channel. Nó là một loại frame ở tầng giao thức. Extension có thể gắn với toàn bộ kết nối hoặc với một stream, tùy theo Stream ID và hợp đồng của extension.

Một số trường hợp có thể cân nhắc extension:

- Truyền một chỉ thị điều khiển riêng mà hai implementation đã thống nhất.
- Bổ sung thông tin phục vụ một tính năng giao thức chưa có frame chuẩn tương ứng.
- Truyền gợi ý tùy chọn để peer mới tận dụng, trong khi peer cũ vẫn có thể tiếp tục hoạt động.

Không nên tạo EXT chỉ để thay thế metadata định tuyến, xác thực hoặc dữ liệu nghiệp vụ thông thường đã có cơ chế phù hợp. Hãy dùng extension khi cần một loại thông điệp ở tầng giao thức có định danh và ngữ nghĩa rõ ràng.

## 2. Cấu trúc của EXT frame

Một EXT frame có cấu trúc tổng quát như sau:

```text
  0                   1                   2                   3
  0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 |0|                         Stream ID                           |
 +-----------+-+-+---------------+-------------------------------+
 | Frame Type |I|M|     Flags     |                               |
 +-------------------------------+-------------------------------+
 |0|                     Extended Type                            |
 +---------------------------------------------------------------+
 |              Metadata Length (nếu có)                          |
 +---------------------------------------------------------------+
 |                 Metadata (nếu có)                              |
 +---------------------------------------------------------------+
 |                 Data (nếu có)                                  |
 +---------------------------------------------------------------+
```

Các trường quan trọng:

| Trường | Ý nghĩa |
|---|---|
| `Stream ID` | `0` chỉ phạm vi toàn kết nối; giá trị khác `0` gắn frame với một stream. |
| `Frame Type` | Luôn là `0x3F` đối với EXT. |
| `I` (Ignore) | Cho biết frame có thể được bỏ qua nếu bên nhận không hiểu hay không. |
| `M` (Metadata) | Cho biết frame có metadata. |
| `Extended Type` | Mã định danh extension, là số unsigned 31-bit và MUST lớn hơn `0`. |
| `Metadata` | Phần metadata tùy chọn, được diễn giải theo hợp đồng của extension. |
| `Data` | Phần dữ liệu tùy chọn, được diễn giải theo hợp đồng của extension. |

Các trường số được mã hóa theo thứ tự byte big-endian. Bit cao nhất của trường Extended Type được dành riêng; giá trị định danh hợp lệ nằm trong phạm vi 31-bit và không được bằng `0`.

### 2.1. Stream ID xác định phạm vi

Stream ID bằng `0` biểu thị thao tác ở phạm vi kết nối. Ví dụ, extension có thể thông báo một khả năng hoặc trạng thái áp dụng cho toàn bộ phiên RSocket. Stream ID khác `0` gắn extension với một stream cụ thể, chẳng hạn bổ sung điều khiển hoặc thông tin cho phiên trao đổi dữ liệu đó.

Hợp đồng của từng Extended Type phải quy định rõ frame được phép dùng ở phạm vi nào. Receiver cần kiểm tra Stream ID trước khi chuyển frame đến handler. Một extension dành cho kết nối không nên bị xử lý như một thông điệp nghiệp vụ của stream, và ngược lại.

### 2.2. Metadata và Data

Cờ `M` chỉ nói rằng metadata có mặt; nó không mô tả ý nghĩa của metadata. Cách giải mã metadata và data thuộc về định dạng của extension cùng quy ước encoding hai bên đã thống nhất.

Khi frame mang cả metadata và data, metadata được đặt trước data và có trường Metadata Length 24-bit để xác định ranh giới. Nếu frame chỉ mang metadata, không cần trường độ dài metadata riêng. Nếu `M` không được bật, receiver không được tự diễn giải phần data như metadata.

Ví dụ, một extension có thể đặt phiên bản schema trong metadata và nội dung thông điệp trong data. Extension khác có thể chỉ dùng metadata. Những cách tổ chức này phải được ghi rõ trong đặc tả extension; không nên để mỗi implementation tự suy đoán.

## 3. Cờ IGNORE quyết định cách xử lý frame chưa biết

RSocket dành cờ `I` trong frame header cho khả năng mở rộng giao thức. Cờ này trả lời câu hỏi: *Nếu peer không hiểu frame này, peer có thể bỏ qua nó không?*

| Giá trị `I` | Ý nghĩa | Hành vi khi receiver không hiểu frame |
|---|---|---|
| `1` | Có thể bỏ qua (ignorable) | Receiver bỏ qua frame và tiếp tục xử lý các frame khác. |
| `0` | Không thể bỏ qua (non-ignorable) | Receiver không thể tiếp tục như thể frame đã được xử lý. Implementation MAY gửi `ERROR[CONNECTION_ERROR]` và đóng kết nối transport. |

Điểm khác biệt quan trọng là từ **MAY** trong đặc tả: với frame không hiểu và `I = 0`, implementation được phép gửi lỗi kết nối rồi đóng transport. Đây là hành vi xử lý lỗi được giao thức cho phép; không nên mô tả thành cam kết rằng mọi thư viện đều phải gửi đúng một phản hồi giống nhau trước khi đóng kết nối.

`I = 1` không có nghĩa receiver phải hiểu hoặc xử lý frame. Ngược lại, nó cho phép receiver bỏ qua frame khi không hỗ trợ extension. Sender phải chấp nhận rằng một peer cũ có thể không thực hiện tác dụng tùy chọn đó.

### 3.1. Khi nào nên đặt `I = 1`?

Đặt `I = 1` khi extension chỉ bổ sung hành vi có thể thiếu mà không làm sai kết quả nghiệp vụ cốt lõi. Ví dụ, một client mới gửi gợi ý hiển thị hoặc một thông tin tối ưu hóa cho server mới. Server cũ không hiểu extension vẫn có thể xử lý request chính theo cách thông thường.

Nếu receiver bỏ qua frame, sender không được giả định gợi ý đã được áp dụng. Nếu cần biết peer có hỗ trợ extension hay không, hãy trao đổi capability trước hoặc dùng một phản hồi ứng dụng riêng.

### 3.2. Khi nào nên đặt `I = 0`?

Đặt `I = 0` khi extension mang ý nghĩa bắt buộc để tiếp tục xử lý đúng. Ví dụ, một extension định nghĩa chế độ xử lý mà nếu bỏ qua sẽ khiến hai bên hiểu khác nhau về trạng thái hoặc kết quả của thao tác.

Trước khi gửi extension bắt buộc, ứng dụng nên xác nhận peer hỗ trợ Extended Type và phiên bản schema tương ứng. Nếu chưa có xác nhận, việc gửi frame `I = 0` có thể làm peer cũ phát sinh lỗi kết nối và đóng transport. Không dùng hành vi đóng kết nối như một cơ chế thương lượng tính năng thông thường.

## 4. Quy trình xử lý extension chưa hỗ trợ

Một receiver nên xử lý EXT theo thứ tự rõ ràng:

1. **Đọc và kiểm tra frame header:** xác nhận loại frame là EXT, đọc Stream ID, cờ `I`, cờ `M` và Extended Type. Kiểm tra độ dài và cấu trúc frame theo quy tắc framing.
2. **Tra cứu Extended Type:** tìm handler đã đăng ký cho mã extension. Không suy đoán handler từ tên class hoặc nội dung data.
3. **Nếu có handler:** kiểm tra phạm vi Stream ID, phiên bản schema, metadata và quyền thực hiện; sau đó mới giải mã và xử lý data.
4. **Nếu không có handler và `I = 1`:** bỏ qua toàn bộ extension frame. Có thể tăng metric hoặc ghi log ở mức phù hợp để theo dõi khả năng tương thích, nhưng không tạo tác dụng nghiệp vụ.
5. **Nếu không có handler và `I = 0`:** xem đây là phần mở rộng bắt buộc mà receiver chưa hỗ trợ. Theo đặc tả, implementation MAY gửi `ERROR[CONNECTION_ERROR]` với Stream ID `0` và đóng transport connection.

Đoạn mã giả sau minh họa nhánh xử lý chính. Đây là ví dụ về cấu trúc dispatch, không phải API cụ thể của Spring Boot hay một thư viện RSocket:

```java
void handleExtension(ExtensionFrame frame) {
    ExtensionHandler handler = registry.find(frame.extendedType());

    if (handler != null) {
        handler.validateScope(frame.streamId());
        handler.handle(frame.metadata(), frame.data());
        return;
    }

    if (frame.ignoreIfUnsupported()) {
        metrics.increment("rsocket.extension.ignored");
        return;
    }

    sendConnectionError("Unsupported mandatory extension");
    closeTransport();
}
```

Trong implementation thật, bước kiểm tra cấu trúc frame phải diễn ra trước khi gọi handler. `sendConnectionError` và `closeTransport` là thao tác minh họa; cách gọi cụ thể phụ thuộc vào thư viện RSocket đang dùng. Receiver cũng cần tránh gọi handler trước khi xác thực xong phạm vi stream và quyền truy cập.

## 5. Thương lượng capability và thiết kế định danh extension

EXT định nghĩa cách mang một Extended Type, nhưng không tự cung cấp một danh mục chung mô tả mọi extension của mọi ứng dụng. Hai peer phải chia sẻ hợp đồng cho từng mã định danh. RSocket SETUP có phần Setup Data để endpoint mô tả capability; ứng dụng cũng có thể thực hiện một bước trao đổi capability riêng sau khi kết nối được thiết lập.

Một hợp đồng extension nên xác định tối thiểu:

- **Mã Extended Type:** giá trị dương 31-bit, duy nhất trong phạm vi registry mà hai bên sử dụng.
- **Phạm vi:** chỉ dùng với Stream ID `0`, chỉ dùng trên stream, hay được phép ở cả hai phạm vi.
- **Ngữ nghĩa:** frame yêu cầu hành động gì, điều kiện nào làm frame hợp lệ và kết quả mong đợi là gì.
- **Schema và encoding:** cấu trúc metadata/data, charset hoặc codec, giới hạn kích thước và cách xử lý field không nhận diện.
- **Phiên bản:** cách nhận biết phiên bản schema, quy tắc tương thích ngược và cách nâng cấp.
- **Chính sách IGNORE:** extension là tùy chọn hay bắt buộc đối với từng luồng nghiệp vụ.
- **Bảo mật:** peer nào được phép gửi extension, quyền nào cần có và dữ liệu nào cần kiểm tra.

Không tái sử dụng một Extended Type cho một ý nghĩa không tương thích. Nếu thay đổi schema làm peer cũ hiểu sai nội dung, hãy cấp định danh mới hoặc thiết kế phiên bản schema có quy tắc tương thích rõ ràng. Việc chỉ tăng phiên bản trong data mà vẫn gửi `I = 1` không tự bảo đảm rằng peer cũ sẽ xử lý đúng.

Một cách tổ chức capability đơn giản là để client và server trao đổi danh sách mã extension cùng phiên bản được hỗ trợ trong bước handshake ở tầng ứng dụng. Trước khi gửi extension bắt buộc, sender kiểm tra danh sách đó. Extension tùy chọn vẫn có thể gửi với `I = 1` khi peer chưa hỗ trợ, nếu việc bỏ qua không làm sai nghiệp vụ.

## 6. Ví dụ lựa chọn cờ trong hệ thống có hai phiên bản

Giả sử phiên bản mới của một dịch vụ muốn gửi thêm một extension chứa gợi ý ưu tiên xử lý. Phiên bản cũ không biết mã extension này, nhưng vẫn hiểu request chuẩn.

- Nếu gợi ý chỉ giúp tối ưu, sender đặt `I = 1`. Server cũ bỏ qua EXT và tiếp tục xử lý request chính. Server mới có thể đọc gợi ý và áp dụng nếu chính sách cho phép.
- Nếu extension chứa thông tin bắt buộc để diễn giải request, sender đặt `I = 0`. Trước khi gửi, client cần xác nhận server hỗ trợ extension. Nếu không hỗ trợ, client phải dừng thao tác hoặc chọn một luồng tương thích đã được thiết kế.

| Tình huống | Cờ đề xuất | Kết quả khi gặp peer cũ |
|---|---:|---|
| Gợi ý tối ưu, có thể bỏ qua | `I = 1` | Peer bỏ qua extension và xử lý phần nghiệp vụ còn lại. |
| Thông tin bắt buộc để hiểu thao tác | `I = 0` | Peer không hỗ trợ có thể trả lỗi kết nối và đóng transport. |
| Chưa biết peer hỗ trợ hay không, nhưng tính năng là bắt buộc | Chưa gửi EXT bắt buộc | Trao đổi capability hoặc chọn phương án tương thích trước. |

Ví dụ này cho thấy `IGNORE` là một quyết định về tương thích, không phải lựa chọn tùy ý để giảm lỗi. Sender phải hiểu chính xác điều gì sẽ xảy ra nếu frame bị bỏ qua.

## 7. Bảo mật và kiểm thử

EXT có thể mang dữ liệu điều khiển nên cần được kiểm tra như các dữ liệu đầu vào khác của giao thức:

- Xác thực peer và kiểm tra quyền gửi từng Extended Type. Một kết nối đã được xác thực không đồng nghĩa mọi extension đều được phép.
- Giới hạn kích thước metadata/data, kiểm tra độ dài trước khi cấp phát bộ nhớ và từ chối cấu trúc sai.
- Kiểm tra Stream ID, trạng thái stream và phiên bản schema trước khi thực thi hành động.
- Không coi `I = 1` là cơ chế bảo mật. Cờ này chỉ quyết định cách xử lý frame chưa được hiểu.
- Với extension có tác động thay đổi trạng thái, cân nhắc định danh chống lặp và kiểm soát replay theo yêu cầu nghiệp vụ.

Các ca kiểm thử quan trọng gồm:

1. EXT có Extended Type đã đăng ký được chuyển đến đúng handler.
2. EXT có Extended Type chưa biết và `I = 1` được bỏ qua; kết nối và các stream khác vẫn tiếp tục.
3. EXT có Extended Type chưa biết và `I = 0` đi vào nhánh lỗi kết nối; kiểm tra mã `CONNECTION_ERROR`, Stream ID `0` và hành vi đóng transport theo implementation.
4. Extended Type bằng `0`, metadata length sai, frame bị cắt cụt hoặc payload vượt giới hạn bị phát hiện ở bước validation.
5. Extension gửi trên sai phạm vi Stream ID hoặc với phiên bản schema không tương thích không được chuyển đến xử lý nghiệp vụ.
6. Hai phiên bản client/server khác nhau có thể trao đổi capability và xử lý đúng cả extension tùy chọn lẫn extension bắt buộc.

Nên có kiểm thử tương tác giữa các phiên bản implementation. Unit test cho registry không đủ để xác nhận rằng frame lỗi được mã hóa, gửi và xử lý đúng trên TCP hoặc WebSocket.

## 8. Những nhầm lẫn thường gặp

- **Nhầm `I` với `M`:** `I` quyết định có thể bỏ qua frame chưa hiểu; `M` báo metadata có mặt.
- **Cho rằng EXT tự định nghĩa schema:** EXT chỉ cung cấp mã Extended Type và cấu trúc frame chung. Schema và ý nghĩa data/metadata do extension quy định.
- **Đặt `I = 1` cho một thao tác bắt buộc:** peer cũ có thể bỏ qua frame, khiến sender tưởng hành động đã xảy ra trong khi thực tế chưa được xử lý.
- **Đặt `I = 0` mà không kiểm tra capability:** một frame bắt buộc chưa được hỗ trợ có thể khiến kết nối bị đóng.
- **Dùng Extended Type trùng cho hai ý nghĩa khác nhau:** hai implementation có thể giải mã cùng một mã theo hai hợp đồng không tương thích.
- **Coi IGNORE là xác nhận giao nhận:** receiver bỏ qua frame không gửi lại xác nhận rằng extension đã được hiểu hoặc thực thi.

## 9. Kết luận

EXT cho phép RSocket mang các phần mở rộng được định danh bằng Extended Type. Stream ID xác định phạm vi kết nối hoặc stream; cờ `M` cho biết metadata có mặt; cờ `I` xác định receiver có thể bỏ qua frame chưa hiểu hay không. Hãy dùng `I = 1` cho phần mở rộng thực sự tùy chọn và `I = 0` cho phần mở rộng bắt buộc, đồng thời trao đổi capability, quản lý schema, kiểm tra quyền và kiểm thử tương thích giữa các phiên bản trước khi đưa extension vào vận hành.

Tài liệu tham khảo: [RSocket Protocol – EXT (Extension) Frame và Handling Ignore Flag](https://rsocket.io/about/protocol/).
