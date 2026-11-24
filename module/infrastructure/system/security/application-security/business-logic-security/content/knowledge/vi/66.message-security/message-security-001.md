# Message producer trust

## 1. Vì sao phải xác định producer nào được phép phát message?

Trong hệ thống bất đồng bộ, consumer thường nhận một message rồi thay đổi dữ liệu: xác nhận thanh toán, giữ hàng, cấp quyền, cộng điểm hoặc gửi báo cáo. **Message producer trust** là cách xác định nguồn phát có được tin cậy để đưa ra loại thông tin hoặc yêu cầu đó hay không, trong đúng phạm vi nghiệp vụ.

Nếu consumer nhận message `payment.capture_confirmed` rồi chuyển đơn hàng sang đã thanh toán, ai phát được message này có thể tác động trực tiếp đến việc giao hàng. Một lỗi cấp quyền publish vì thế có thể trở thành lỗ hổng cho phép nhận hàng mà chưa trả tiền.

Không thể kết luận một message đáng tin chỉ vì:

- Nó có JSON đúng schema.
- Nó nằm trong topic có tên `internal.payments`.
- Nó chứa `producer: payment-service`.
- Nó đi qua mạng nội bộ hoặc một kết nối có mã hóa.
- Nó có chữ ký hợp lệ của một khóa mà hệ thống chưa xác định đúng quyền.
- Producer được xác thực nhưng đang gửi loại sự kiện nằm ngoài trách nhiệm của nó.

Tin cậy producer là một quyết định có phạm vi. Cần biết **nguồn nào được quyền khẳng định điều gì, cho tenant và tài nguyên nào, dựa trên bằng chứng nào**.

## 2. Phân biệt xác thực nguồn, quyền phát và tính đúng nghiệp vụ

| Lớp kiểm tra | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Xác thực nguồn | Thành phần gửi hoặc ký thực sự là ai? | Kết nối của workload thanh toán hay một client tự khai tên? |
| Quyền phát | Nguồn đó được phát loại message này vào đường đi này không? | Dịch vụ báo cáo có bị cấm phát sự kiện thanh toán không? |
| Phạm vi | Nguồn được phát cho tenant, môi trường và miền tài nguyên nào? | Khóa thử nghiệm không được tạo tác động production |
| Tính toàn vẹn | Nội dung được xử lý có đúng là nội dung đã được bảo vệ không? | Amount, currency và order ID không bị sửa giữa chừng |
| Quyền và bằng chứng nghiệp vụ | Nội dung có đủ căn cứ để tạo tác động không? | Capture có thuộc đúng đơn, đúng tài khoản nhận và đủ số tiền không? |
| Tính mới và chống trùng | Message cũ hoặc bản sao có được xử lý lại không? | Một capture không được dùng để trả cho hai đơn |

Xác thực producer không chứng minh mọi field của message đều đúng. Producer có thể có bug, hiểu sai dữ liệu từ bên ngoài, bị cấp quyền quá rộng hoặc bị chiếm quyền.

Consumer vẫn phải giữ bất biến tại ranh giới của mình. Điều đó không nhất thiết nghĩa là gọi đồng bộ lại producer cho mọi message; có thể dùng hợp đồng sự kiện, dữ liệu đối chiếu và ràng buộc bền vững phù hợp. Nhưng không được biến “nguồn đã xác thực” thành “bỏ mọi kiểm tra nghiệp vụ”.

### 2.1. Command và event có căn cứ quyền khác nhau

| Loại | Ý nghĩa | Kiểm tra quan trọng |
| --- | --- | --- |
| Command | Yêu cầu một thành phần thực hiện hành động | Ai được yêu cầu, trên đối tượng nào, theo trạng thái và hạn mức nào? |
| Event | Khẳng định một sự kiện đã xảy ra trong miền nghiệp vụ | Ai có thẩm quyền xác nhận sự kiện, bằng chứng nào và version nào? |

`refund.requested` không chứng minh tiền đã hoàn. `payment.authorized` không tự đồng nghĩa tiền đã được capture. Một tên message không được dùng để nhảy qua các bước nghiệp vụ mà ý nghĩa của nó chưa bao phủ.

Nếu hệ thống dùng event `payment.capture_confirmed`, cần định nghĩa đó là xác nhận capture theo hợp đồng thanh toán cụ thể. Không diễn giải nó thành bảo đảm không bao giờ có tranh chấp, hoàn tiền hoặc điều chỉnh về sau.

## 3. Lần theo chuỗi nguồn gốc thay vì tin một field producer

Một luồng có thể gồm nhiều thành phần:

~~~mermaid
flowchart LR
    U[Người dùng] --> API[Payment API]
    P[Hệ thống thanh toán ngoài] --> API
    API --> DB[(Dữ liệu thanh toán và outbox)]
    DB --> R[Outbox relay]
    R --> B[Broker]
    B --> C[Order consumer]
    C --> O[(Đơn hàng, inbox và audit)]
~~~

Danh tính cần phân biệt:

- **Initiating actor:** người hoặc quy trình khởi tạo thao tác ban đầu.
- **Business issuer:** miền có thẩm quyền khẳng định sự kiện, ví dụ dịch vụ thanh toán.
- **Transport publisher:** thành phần thực sự kết nối và publish vào broker, có thể là relay.
- **Execution principal:** danh tính kỹ thuật của consumer thực thi thay đổi.

Trong ví dụ, khách hàng khởi tạo thanh toán nhưng không có quyền tự xác nhận đã capture. Relay vận chuyển sự kiện nhưng không mặc nhiên là nơi quyết định thanh toán đã hợp lệ.

### 3.1. Field tự khai không phải danh tính đã xác minh

Message sau không chứng minh nó đến từ dịch vụ thanh toán:

~~~json
{
  "producer": "payment-service",
  "event_type": "payment.capture_confirmed",
  "tenant_id": "tenant-a",
  "payload": {
    "order_id": "order-781",
    "amount_minor": 250000,
    "currency": "VND"
  }
}
~~~

Một client có quyền publish rộng có thể tự tạo toàn bộ JSON này.

Nguồn đáng tin phải đến từ cơ chế được kiểm chứng, ví dụ:

- Danh tính kết nối được broker xác thực, kết hợp ACL chặt trên đường publish.
- Metadata do hạ tầng đáng tin cung cấp và bảo vệ, tách khỏi header do client tự gửi.
- Chữ ký/MAC được xác minh bằng khóa đã được cấu hình với đúng issuer, mục đích và phạm vi.
- Một đường relay hoặc connector được giới hạn và có nguồn dữ liệu đầu vào được bảo vệ.

Không giả định consumer luôn nhận được danh tính publisher từ broker. Nếu giao diện consumer không cung cấp bằng chứng đó, cần dựa vào mô hình kiểm soát đường publish hoặc cơ chế nguồn gốc khác được thiết kế rõ.

### 3.2. Relay và connector là một phần của ranh giới tin cậy

Nếu mọi dịch vụ dùng chung relay và relay được publish vào mọi topic, cần kiểm soát nguồn dữ liệu mà relay đọc, ánh xạ miền nguồn với destination, và khả năng giả mạo issuer.

Ví dụ, một hàng trong outbox của dịch vụ báo cáo không được phép chọn destination thanh toán chỉ bằng cách sửa cột `topic`.

Nếu relay ký mọi payload bằng một khóa chung rồi điền issuer từ nội dung tự khai, chữ ký chỉ chứng minh relay đã ký dữ liệu đó. Nó chưa chứng minh miền thanh toán đã xác nhận capture.

Nếu yêu cầu bảo vệ từ issuer đến consumer, cơ chế ký phải gắn được với issuer có thẩm quyền và dữ liệu mà issuer đã chấp nhận. Cần xác định relay có được phép sửa nội dung, ký thay hay chỉ chuyển tiếp.

## 4. Giới hạn quyền producer theo hợp đồng nghiệp vụ

### 4.1. Ma trận quyền phát minh họa

| Nguồn | Message được phép | Message không được phép chỉ vì cùng hệ thống |
| --- | --- | --- |
| Miền đơn hàng | `order.created`, `order.cancelled` theo hợp đồng | `payment.capture_confirmed` |
| Miền thanh toán | Sự kiện capture đã được kiểm chứng trong phạm vi tài khoản được quản lý | Thay đổi giá sản phẩm hoặc cấp quyền quản trị |
| Dịch vụ báo cáo | Trạng thái tạo/xuất báo cáo được phép | Sự kiện hoàn tiền hoặc tăng số dư |
| Bộ điều phối hoàn tiền | Command yêu cầu xử lý hoàn theo phê duyệt | Khẳng định hoàn tiền thành công khi chưa có xác nhận |
| Client người dùng | Yêu cầu qua API công khai có kiểm soát | Publish trực tiếp sự kiện nội bộ có thẩm quyền |

ACL ở broker có thể giới hạn topic/queue hoặc đường định tuyến. Nếu nhiều loại sự kiện nằm chung một topic, consumer vẫn cần xác minh loại nào thuộc quyền của nguồn tương ứng.

Một topic tên chung như `business-events` không nên trở thành nơi mọi producer đều có quyền khẳng định mọi sự kiện.

### 4.2. Nguyên tắc cấp quyền hẹp

- Dùng danh tính riêng cho workload và môi trường theo phạm vi cần thiết.
- Chỉ cấp publish/consume/manage theo nhu cầu; quyền phát không mặc nhiên kèm quyền đọc hoặc quản trị broker.
- Hạn chế wildcard và credential dùng chung làm mất khả năng phân biệt nguồn.
- Ràng buộc publisher với loại message, nguồn dữ liệu và destination được phép.
- Quản lý vòng đời credential, xoay vòng và thu hồi khi workload không còn được tin.
- Kiểm soát cả công cụ replay, connector, batch job và đường vận hành thủ công.

Nếu một producer được phép phục vụ nhiều tenant, phải có ràng buộc tenant trong dữ liệu và bằng chứng nghiệp vụ. Không cần tạo credential riêng cho từng tenant trong mọi kiến trúc, nhưng cũng không được xem field tenant tự khai là đủ.

### 4.3. Phân tách môi trường và mục đích sử dụng khóa

Message thử nghiệm không được tạo tác động production. Cần tách danh tính, quyền, cấu hình broker và khóa theo mô hình môi trường đã chọn.

Khi dùng khóa ký, liên kết khóa với issuer, môi trường, loại message và mục đích. Một khóa dùng để ký báo cáo không tự có quyền xác nhận thanh toán.

Quyền trên khóa cũng quan trọng như bản thân thuật toán. Nếu nhiều dịch vụ có thể dùng cùng một khóa để ký bất kỳ sự kiện nào, consumer sẽ khó xác định miền nào thực sự đưa ra khẳng định.

## 5. Envelope phải ràng buộc nguồn với đúng nội dung

Một envelope minh họa:

~~~json
{
  "schema_version": 1,
  "event_id": "evt-capture-102",
  "event_type": "payment.capture_confirmed",
  "issuer": "payment-service",
  "audience": "order-service",
  "environment": "production",
  "tenant_id": "tenant-a",
  "occurred_at": "2026-11-22T03:10:15Z",
  "correlation_id": "checkout-91",
  "causation_id": "payment-attempt-7",
  "initiating_actor_id": "customer-42",
  "payload": {
    "provider": "provider-a",
    "merchant_account_id": "merchant-12",
    "capture_id": "capture-531",
    "payment_intent_id": "intent-618",
    "order_id": "order-781",
    "amount_minor": 250000,
    "currency": "VND",
    "payment_version": 4
  }
}
~~~

Đây chỉ là dữ liệu envelope, chưa bao gồm bằng chứng xác thực hoặc chữ ký. Các field `issuer`, `environment` và `tenant_id` phải được đối chiếu với nguồn đã xác minh.

| Trường | Vai trò | Điều không được suy diễn |
| --- | --- | --- |
| `event_id` | Định danh ổn định cho sự kiện và các lần chuyển phát lại | ID duy nhất không chứng minh nguồn có quyền |
| `event_type` | Chọn hợp đồng và ý nghĩa nghiệp vụ | Client không có quyền phát chỉ vì biết tên type |
| `issuer` | Khẳng định miền phát sự kiện | Phải khớp bằng chứng nguồn, không tự xác thực |
| `audience` | Giới hạn bên nhận theo hợp đồng | Cần kiểm tra, không chỉ lưu vào log |
| `tenant_id` | Phân vùng nghiệp vụ | Phải khớp tài nguyên và tài khoản thanh toán |
| `occurred_at` | Thời gian nguồn cho rằng sự kiện xảy ra | Không đủ để chống replay hoặc chứng minh thứ tự tuyệt đối |
| `initiating_actor_id` | Liên kết người khởi tạo | Không biến khách hàng thành người có quyền xác nhận capture |
| `capture_id` | Định danh tác động thanh toán bên ngoài | Cần xác định phạm vi duy nhất theo provider/tài khoản |
| `payment_version` | Hỗ trợ diễn giải trạng thái và thứ tự | Chỉ hữu ích nếu hợp đồng định nghĩa cách dùng version |

### 5.1. Kiểm tra schema trước khi diễn giải nghiệp vụ

Giới hạn kích thước, độ sâu cấu trúc, số phần tử và độ dài chuỗi trước khi xử lý tài nguyên lớn. Chỉ chấp nhận schema/type được hỗ trợ, với kiểu dữ liệu và phạm vi giá trị rõ ràng.

Đặc biệt cần thống nhất cách xử lý field trùng tên, trường lạ, số tiền và giá trị mặc định. Nếu bộ xác minh và bộ xử lý diễn giải cùng một JSON theo hai cách khác nhau, việc bảo vệ byte không đủ bảo vệ ý nghĩa mà ứng dụng sử dụng.

Không deserialize message thành class bất kỳ do payload chỉ định. Dùng ánh xạ type–schema được phép, rồi xử lý thành cấu trúc dữ liệu đã biết.

Nếu hỗ trợ mở rộng schema, field mới không được âm thầm làm rộng quyền. Ví dụ, một flag `skipApproval` chưa được hỗ trợ phải không có khả năng điều khiển consumer.

### 5.2. Hợp đồng nguồn cần được xác định ngoài message

Consumer cần có chính sách tin cậy được quản lý độc lập, chẳng hạn:

~~~text
issuer: payment-service
allowed_type: payment.capture_confirmed
allowed_environment: production
intended_audience: order-service
allowed_publish_path: đường sự kiện thanh toán đã cấu hình
tenant_scope: theo ánh xạ merchant và dữ liệu thanh toán
schema_versions: tập phiên bản được hỗ trợ
proof: cơ chế nguồn đã cấu hình
~~~

Không cho message tự bổ sung issuer vào danh sách đáng tin, tự mở rộng tenant scope hoặc yêu cầu bỏ kiểm tra chữ ký.

## 6. Producer chỉ phát điều nó thực sự có căn cứ xác nhận

### 6.1. Đầu vào từ bên ngoài chưa phải sự kiện nội bộ đáng tin

Nếu payment service nhận một callback rồi phát `payment.capture_confirmed`, cần kiểm tra callback theo hợp đồng của hệ thống thanh toán. Các kiểm tra có thể gồm nguồn, tính toàn vẹn, loại sự kiện, tài khoản merchant, giao dịch tham chiếu, trạng thái và chống trùng.

Không dùng một endpoint mà client gửi `paid: true` để tạo sự kiện xác nhận capture. Tương tự, redirect trình duyệt về trang “thanh toán thành công” không tự là bằng chứng hệ thống đã nhận đủ xác nhận thanh toán.

Nếu cần đối chiếu với dịch vụ thanh toán ngoài, phải dùng tham chiếu và danh tính merchant đúng phạm vi. Chi tiết xác minh phụ thuộc tích hợp cụ thể; không thay bằng việc tin mọi request có header tên “payment-provider”.

### 6.2. Ghi trạng thái và outbox cùng transaction

Nếu producer phát sự kiện trước commit dữ liệu của nó:

~~~text
Phát payment.capture_confirmed.
Transaction ghi nhận capture gặp lỗi và rollback.
Order consumer vẫn chuyển đơn sang PAID.
~~~

Nếu producer commit trước rồi publish trực tiếp, tiến trình có thể chết giữa hai lần ghi và làm mất sự kiện.

Transactional outbox giúp gắn trạng thái nghiệp vụ nội bộ với ý định phát sự kiện bền vững. Relay chỉ đọc dữ liệu đã commit, có thể retry chuyển cùng event ID.

Outbox không tự chứng minh dữ liệu đầu vào đúng. Nó bảo vệ sự nhất quán giữa bản ghi nghiệp vụ và sự kiện của producer; nguồn và bất biến vẫn phải được kiểm tra trước khi ghi.

### 6.3. Quyền của người dùng không tự chuyển thành quyền issuer

Một khách hàng có quyền tạo đơn hoặc bắt đầu thanh toán không có quyền khẳng định giao dịch đã thành công. Một nhân viên hỗ trợ được xem giao dịch cũng chưa chắc có quyền yêu cầu hoàn tiền.

Nếu producer nhận command do người dùng khởi tạo, nó cần giữ actor, subject nếu có, căn cứ quyền và quyết định nghiệp vụ. Chỉ phát sự kiện kết quả khi trạng thái tương ứng thực sự được chấp nhận theo quy trình.

Đây là điểm dễ xuất hiện confused deputy: một service có quyền phát message nhạy cảm bị một bên ít quyền hơn điều khiển để phát thay. Phòng vệ phải nằm ở API đầu vào, logic producer và kiểm tra consumer, thay vì chỉ đặt mật khẩu cho broker.

## 7. Chọn cơ chế bảo vệ theo ranh giới tin cậy

### 7.1. Bảo vệ từng chặng và bảo vệ từ nguồn đến consumer

TLS hoặc mTLS bảo vệ kết nối theo phạm vi của chặng đó. Sau khi broker, relay hoặc một dịch vụ trung gian nhận dữ liệu, cần xét riêng quyền đọc, sửa và phát lại của thành phần đó.

Chữ ký hoặc MAC ở cấp message có thể giữ bằng chứng về nội dung qua các chặng, nhưng phải có hợp đồng xác minh đúng. Không phải kiến trúc nào cũng cần ký mọi event: một đường publish được kiểm soát chặt có thể đáp ứng mô hình đe dọa đã chọn. Cần nêu rõ thành phần nào được tin và hành vi nào cần phát hiện.

### 7.2. Nếu dùng chữ ký hoặc MAC

Các yêu cầu thiết kế gồm:

- Ràng buộc loại message, issuer, audience, môi trường, tenant và payload cần bảo vệ.
- Dùng thuật toán và định dạng đã được lựa chọn trong cấu hình tin cậy; không để message tự chọn một chế độ yếu hơn.
- Ánh xạ key ID tới khóa và quyền issuer đã được quản lý từ trước.
- Không tải khóa từ một URL tùy ý do message cung cấp.
- Xác minh đúng chuỗi byte hoặc biểu diễn chuẩn đã được hợp đồng quy định.
- Đảm bảo bộ xử lý nghiệp vụ sử dụng chính nội dung đã được xác minh, không một bản payload khác.
- Quản lý quyền truy cập khóa, xoay vòng, thu hồi và xử lý khóa nghi bị lộ.

Không tự viết thuật toán mật mã trong code nghiệp vụ. Nếu chọn ký trực tiếp chuỗi byte, relay phải giữ nguyên phần byte được bảo vệ. Nếu chọn biểu diễn chuẩn hóa, cả bên ký lẫn bên xác minh phải tuân theo cùng quy tắc.

Một digest không có khóa chỉ hỗ trợ so sánh dữ liệu, không xác thực người phát: bên sửa message có thể tính lại digest. Chữ ký không tự mã hóa dữ liệu. Với MAC dùng bí mật chung, các bên biết bí mật có thể tạo MAC; không diễn giải nó thành bằng chứng chỉ một producer duy nhất có thể phát.

### 7.3. Header và routing cũng phải được ràng buộc phù hợp

Nếu chữ ký chỉ bao phủ payload nhưng `event_type` ở header có thể bị sửa, một payload có thể bị đưa sang handler khác. Nếu audience hoặc tenant nằm ngoài phần bảo vệ, kẻ tấn công có thể thử chuyển nguyên payload sang ngữ cảnh khác.

Metadata định tuyến từ broker có thể dùng làm bằng chứng trong một mô hình tin cậy cụ thể, nhưng phải phân biệt metadata do broker xác lập với header mà publisher tự đặt. Các thành phần này cần khớp với chính sách consumer và envelope đã xác minh.

### 7.4. Chữ ký hợp lệ vẫn có thể là message cũ

Một message đã ký có thể bị phát lại. Timestamp hoặc thời hạn có thể giới hạn một số kiểu replay, nhưng chống tác động trùng cần định danh và trạng thái bền vững.

Với event mô tả sự kiện lịch sử, quy tắc tuổi message phải tính đến downtime và khôi phục dữ liệu. Từ chối mọi event cũ có thể làm mất nghiệp vụ hợp lệ. Cần phân biệt:

- Event lịch sử được chuyển lại theo quy trình khôi phục có kiểm soát.
- Command có thời hạn cấp quyền đã hết.
- Một tác động đã được xử lý đang bị yêu cầu lặp lại.

Không đổi event ID hoặc làm mới timestamp chỉ để vượt cơ chế chống replay. Nếu dùng một envelope vận chuyển mới, vẫn giữ định danh sự kiện và tác động nghiệp vụ gốc.

### 7.5. Xoay vòng và thu hồi khóa

Xoay vòng khóa cần có quy tắc xác minh message đang chờ và message lịch sử. Không chỉ thay khóa rồi làm hỏng toàn bộ backlog, cũng không chấp nhận mọi khóa cũ vô thời hạn.

Khi nghi khóa bị lộ, sự kiện có chữ ký đúng vẫn có thể đã bị giả mạo. Cần xác định phạm vi ảnh hưởng, chính sách cách ly hoặc đối chiếu lại bằng chứng nghiệp vụ, và cơ chế chặn tác động mới.

Việc message đã có chữ ký không loại bỏ nhu cầu thu hồi độ tin cậy của producer.

## 8. Consumer xác minh nguồn trước khi tạo tác động

### 8.1. Thứ tự xử lý

Một trình tự tổng quát:

1. Giới hạn kích thước và đọc metadata tối thiểu theo định dạng được hỗ trợ.
2. Xác minh bằng chứng nguồn và tính toàn vẹn theo cơ chế đã chọn.
3. Parse và kiểm tra schema của chính nội dung đã được xác minh.
4. Đối chiếu issuer, type, audience, môi trường, đường publish và phạm vi nguồn.
5. Kiểm tra tenant, quan hệ tài nguyên, bằng chứng và trạng thái nghiệp vụ.
6. Ghi inbox/chống trùng, tác động nghiệp vụ và audit/outbox trong transaction thích hợp.
7. Chỉ xác nhận xử lý với broker sau khi kết quả cần thiết đã được ghi bền vững.

Một số bước có thể được tổ chức khác tùy cơ chế nguồn, nhưng không được tạo tác động nghiệp vụ trước khi hoàn tất các kiểm tra bắt buộc.

Message không xác minh được nguồn không nên đi vào handler như thể nó là một command hợp lệ rồi mới “ghi cảnh báo”.

### 8.2. Ví dụ: chỉ xác nhận thanh toán cho capture phù hợp

Giả định ví dụ chỉ hỗ trợ một capture đủ toàn bộ số tiền cho mỗi đơn. Trường hợp trả nhiều phần, thừa tiền, nhiều capture hoặc điều chỉnh cần hợp đồng và state machine riêng.

Consumer cần đối chiếu:

| Điều kiện | Bất biến được bảo vệ |
| --- | --- |
| Nguồn có quyền phát xác nhận capture | Dịch vụ khác không tự tuyên bố đã thanh toán |
| Tenant và merchant khớp tham chiếu thanh toán của đơn | Không dùng tiền của tenant khác |
| Payment intent khớp order và phiên bản phải thanh toán | Không chuyển bằng chứng giữa các đơn |
| Amount và currency khớp nghĩa vụ đã chốt | Không trả thiếu hoặc dùng sai đồng tiền |
| Capture chưa được áp dụng cho đơn khác | Một giao dịch không tài trợ nhiều đơn |
| Trạng thái đơn cho phép xác nhận thanh toán | Không nhảy qua state machine hoặc tự mở lại đơn đã hủy |
| Kết quả được ghi nguyên tử | Không có inbox hoàn tất mà đơn chưa đổi hoặc ngược lại |

Quyền issuer và dữ liệu đối chiếu phải được lấy từ nguồn tin cậy phù hợp. Một dòng trong payload tự khai `verified: true` không đáp ứng các điều kiện trên.

### 8.3. Pseudocode Java

Mã giả sau không gắn với API của broker hoặc framework cụ thể. Giả định order, tham chiếu thanh toán, inbox, bảng áp dụng capture và audit/outbox cùng nằm trong cơ sở dữ liệu tham gia transaction.

~~~java
void onPaymentMessage(RawDelivery raw, TrustedTransportContext transport) {
    // verify() có giới hạn đầu vào và trả đúng byte đã được bảo vệ.
    VerifiedMessage verified = sourceVerifier.verify(raw, transport);

    PaymentCaptureEvent event = schemas.parseVerifiedCapture(verified);

    producerPolicy.requireAllowed(
            verified.source(),
            event.issuer(),
            event.eventType(),
            event.audience(),
            event.environment(),
            event.tenantId());

    database.transaction(tx -> {
        InboxClaim claim = inbox.claimOrLoad(
                tx,
                event.issuer(),
                event.eventId(),
                verified.contentDigest());

        if (claim.isCompleted()) {
            // Cùng ID nhưng nội dung khác phải bị coi là xung đột.
            claim.requireSameDigest(verified.contentDigest());
            return;
        }

        Order order = orders.lockForUpdate(
                tx, event.tenantId(), event.orderId());

        PaymentReference reference = paymentReferences.requireForOrder(
                tx, event.tenantId(), order.id(), event.paymentIntentId());

        reference.requireMatchesSourceAndCapture(event, verified.source());
        reference.requireExpectedAmountAndCurrency(order, event);

        CaptureApplication existing = captureApplications.find(
                tx,
                event.provider(),
                event.merchantAccountId(),
                event.captureId());

        if (existing != null) {
            existing.requireSameBusinessEffect(order, event);
            inbox.complete(tx, claim, existing.operationId());
            return;
        }

        order.requireWaitingForPayment();

        // Có unique constraint theo phạm vi định danh capture của hợp đồng.
        CaptureApplication application =
                captureApplications.insert(tx, order, event);

        order.markPaid(application.operationId());
        orders.save(tx, order);

        auditOutbox.append(
                tx, OrderPaymentConfirmed.from(order, event, verified.source()));

        inbox.complete(tx, claim, application.operationId());
    });

    // Chỉ chạy sau khi transaction đã commit.
    raw.acknowledge();
}
~~~

Các điểm cần giữ:

- `VerifiedMessage` là kết quả từ một cơ chế xác minh có căn cứ, không phải wrapper tạo ra chỉ vì JSON có field issuer.
- `producerPolicy` so khớp danh tính đã xác minh với khẳng định trong envelope và chính sách quyền nguồn.
- `contentDigest` dùng để phát hiện nội dung khác dưới cùng event ID, không thay thế xác thực nguồn.
- Claim inbox và áp dụng capture có ràng buộc duy nhất. Cần xử lý cạnh tranh, lỗi unique và rollback đúng ngữ nghĩa của cơ sở dữ liệu.
- Nhánh capture đã tồn tại chỉ được coi là bản sao khi cùng tác động: đúng đơn, tenant, số tiền, đồng tiền và các ràng buộc cần thiết.
- Một capture đã áp dụng cho đơn khác là xung đột cần chặn và điều tra.
- Nếu đơn đã trả bằng capture khác, không tự bỏ qua capture mới như bản sao; cần quy trình xác định đó là giao dịch thêm hay dữ liệu bất thường.
- Nếu transaction rollback, không ACK như thành công. Lỗi tạm thời, lỗi chính sách và message cần cách ly phải có đường xử lý riêng.

Bảng tham chiếu thanh toán trong ví dụ phải được tạo theo quy trình đáng tin và gắn với đơn. Nếu nó chỉ sao chép nguyên dữ liệu từ chính message đang xét, việc “đối chiếu” sẽ không tạo thêm bảo đảm.

### 8.4. Chống trùng ở hai mức

Inbox thường khử trùng theo định danh sự kiện, ví dụ `issuer + event_id`. Phạm vi ID phải được hợp đồng quy định và được đưa vào khóa đầy đủ.

Bất biến capture dùng một định danh tác động như `provider + merchant_account_id + capture_id`, tùy phạm vi duy nhất thực tế. Một producer có bug có thể phát hai event ID khác nhau cho cùng capture; inbox theo event ID sẽ không nhận ra đó là cùng tác động.

Ví dụ ràng buộc minh họa:

~~~sql
CREATE UNIQUE INDEX uq_capture_application
ON capture_application (
    provider,
    merchant_account_id,
    capture_id
);
~~~

Ràng buộc này chỉ phù hợp nếu bộ ba thực sự duy nhất trong hợp đồng tích hợp. Nếu định danh còn phụ thuộc môi trường hoặc không gian khác, cần đưa phạm vi đó vào mô hình.

Các ràng buộc và thay đổi đơn phải cùng transaction. Một unique constraint ghi sau lời gọi tạo tác động ở hệ thống ngoài không tự hoàn tác tác động ngoài đã xảy ra.

### 8.5. Không biến mọi message thành thành công hoặc retry vô hạn

| Kết quả | Hướng xử lý |
| --- | --- |
| Nguồn không hợp lệ hoặc type vượt quyền | Từ chối/cách ly theo chính sách, không tạo tác động |
| Chữ ký hoặc nội dung không hợp lệ | Không xử lý nghiệp vụ; ghi nhận phù hợp để điều tra |
| Schema chưa hỗ trợ | Cách ly hoặc đưa vào quy trình nâng cấp có kiểm soát |
| Database tạm thời lỗi trước commit | Có thể retry cùng event ID |
| Cùng event ID, cùng nội dung, đã commit | Xác nhận bản sao, không lặp tác động |
| Cùng event ID nhưng nội dung khác | Chặn xung đột, không dùng kết quả cũ cho nội dung mới |
| Sai tenant, số tiền hoặc quan hệ thanh toán | Không chuyển đơn sang đã trả; đối chiếu theo chính sách |
| Trạng thái chưa đủ dữ liệu do đến sai thứ tự | Chờ/đối chiếu có giới hạn theo hợp đồng, không tự bịa trạng thái |

ACK sau khi cách ly bền vững và ACK sau khi nghiệp vụ thành công có ý nghĩa khác nhau. Cần ghi kết quả rõ để công việc chưa được chấp nhận không bị báo cáo là đã hoàn tất nghiệp vụ.

## 9. Message đến trễ, sai thứ tự và replay có kiểm soát

### 9.1. Nguồn hợp lệ không bảo đảm thứ tự nhận

Một event từ producer đúng có thể đến sau event mới hơn hoặc bị giao lại sau nhiều ngày. Không dùng riêng timestamp để ghi đè trạng thái hiện tại.

Ví dụ, xác nhận capture đến sau khi đơn đã hủy không có nghĩa consumer được tự mở lại đơn và giao hàng. Tiền có thể thực sự đã được capture, nhưng cần chuyển sang quy trình đối chiếu hoặc xử lý theo chính sách của đơn bị hủy.

Version chỉ hữu ích khi biết nó áp dụng cho aggregate nào và cách xử lý thiếu phiên bản. Hai service cùng dùng một con số version không có nghĩa các con số đó so sánh trực tiếp được với nhau.

### 9.2. Replay không được trở thành đường giả mạo issuer

Công cụ replay cần quyền theo nguồn, loại message, tenant và mục đích vận hành. Người có quyền chuyển lại message chưa chắc có quyền tạo một sự kiện nghiệp vụ mới.

Nếu bảo vệ message bằng chữ ký, nên giữ bằng chứng và nội dung gốc theo hợp đồng. Nếu dùng đường replay đáng tin khác, consumer cần biết nó đang tiếp nhận bản phát lại của nguồn nào và căn cứ xác minh đó là gì.

Không cho công cụ vận hành tự sửa `issuer`, amount hoặc order ID rồi dùng credential quản trị để khiến consumer coi như sự kiện gốc. Thay nội dung cần một quy trình tạo hoặc đính chính nghiệp vụ có thẩm quyền riêng.

Việc đưa message ra khỏi DLQ không tự làm nó hợp lệ. Replay vẫn phải đi qua các kiểm tra nguồn, schema, tenant, trạng thái và chống trùng phù hợp.

### 9.3. Giữ dữ liệu chống trùng đủ lâu

Thời hạn inbox cần xét khả năng message bị phát lại từ broker, DLQ, backup và công cụ vận hành. Nếu dấu vết hết hạn trước thời gian có thể replay, chỉ dựa vào inbox sẽ không bảo vệ được tác động.

Với tiền hoặc quyền truy cập, nên có ràng buộc nghiệp vụ bền vững theo operation hoặc giao dịch thực tế. Không xóa lịch sử capture khỏi đường kiểm tra rồi cho một event cũ đi qua như một khoản tiền mới.

Một lớp cache chống trùng ngắn hạn có thể tăng hiệu năng, nhưng không thay ràng buộc bền vững khi tác động đòi hỏi điều đó.

## 10. Khi producer bị chiếm quyền hoặc mất độ tin cậy

### 10.1. Giới hạn thiệt hại bằng quyền hẹp

Nếu một producer bị chiếm quyền, broker ACL và chữ ký vẫn có thể hoạt động đúng: kẻ tấn công đang dùng chính quyền hợp lệ của producer.

Phân quyền hẹp giúp giảm phạm vi ảnh hưởng:

- Dịch vụ báo cáo không phát được xác nhận thanh toán.
- Khóa của môi trường thử nghiệm không được chấp nhận trong production.
- Một nguồn chỉ được dùng tập merchant hoặc tenant đã cấp.
- Consumer không cho sự kiện vượt số tiền, quan hệ tài nguyên hay trạng thái được phép.
- Thay đổi trust policy và quyền publish được kiểm soát và audit.

Tuy nhiên, nếu payment issuer có toàn bộ quyền xác nhận một capture và bị chiếm quyền, nó có thể tạo một khẳng định giả khớp các tham chiếu mà consumer biết. Chữ ký và kiểm tra amount không tự phân biệt được khẳng định giả này với sự kiện thật.

Với tác động có rủi ro cao, có thể cần thêm căn cứ độc lập như đối chiếu ledger, kiểm tra trạng thái với hệ thống thanh toán hoặc một quy trình phê duyệt bổ sung. Chọn cơ chế theo mô hình đe dọa và yêu cầu nghiệp vụ, không giả định mọi sự kiện đều cần cùng mức kiểm tra.

### 10.2. Thu hồi cần bao phủ cả đường vận chuyển và message đang chờ

Một quy trình có thể gồm:

1. Chặn hoặc giới hạn publish mới của nguồn nghi bị chiếm quyền.
2. Thu hồi credential/khóa liên quan và cập nhật chính sách consumer.
3. Xác định message đang chờ, đang xử lý và đã tạo tác động.
4. Cách ly hoặc đối chiếu lại phạm vi message đáng ngờ theo chính sách.
5. Kiểm tra ledger, đơn hàng, cấp quyền và các tác động đã phát sinh.
6. Ghi lại quyết định cho phép tiếp tục, chặn hoặc đính chính.

Chỉ khóa kết nối mới không tự làm vô hiệu các message đã nằm trong broker. Chỉ dừng consumer cũng không giải quyết dữ liệu sai mà nó đã commit.

Khi có thao tác đang chạy, cần ngữ nghĩa rõ về mốc thu hồi. Nếu chính sách đòi hỏi chặn sát thời điểm commit, thiết kế cần version của chính sách hoặc cơ chế nhất quán thích hợp. Một kết quả allow được cache từ trước không tự đáp ứng yêu cầu đó.

### 10.3. Đính chính bằng sự kiện mới

Nếu một producer từng phát dữ liệu sai, không nên sửa âm thầm lịch sử đã phát. Có thể tạo sự kiện đính chính hoặc operation bù trừ theo hợp đồng, liên kết với sự kiện gốc và có thẩm quyền tương ứng.

Đính chính không đồng nghĩa mọi tác động có thể đảo ngược. Báo cáo đã gửi, hàng đã giao hoặc tiền đã chuyển cần quy trình xử lý nghiệp vụ riêng.

## 11. Audit phải phân biệt nguồn tự khai với nguồn đã xác minh

Thông tin hữu ích gồm:

| Nhóm | Trường minh họa |
| --- | --- |
| Liên kết | Event ID, operation ID, correlation ID và causation ID |
| Nguồn vận chuyển | Principal đã xác thực nếu có, đường publish và connector/relay |
| Bằng chứng | Cơ chế xác minh, key ID nếu có, kết quả và phiên bản trust policy |
| Nguồn nội dung | Claimed issuer, verified issuer và loại message |
| Phạm vi | Tenant đã xác minh, tài nguyên và định danh tác động |
| Kết quả | Từ chối, cách ly, bản sao, commit hoặc đang đối chiếu |
| Thực thi | Consumer, execution principal, thời điểm và mã lý do |

Với message chưa xác minh được nguồn, không ghi issuer tự khai vào trường “nguồn đã xác thực”. Tương tự, tenant trong payload chưa kiểm chứng không được dùng để trình bày rằng tenant đó thực sự phát sự kiện.

Không ghi secret, toàn bộ token, khóa hoặc dữ liệu thanh toán nhạy cảm vào log. Nếu cần giữ message để điều tra, dùng vùng lưu trữ có quyền truy cập và thời hạn phù hợp; dữ liệu không tin cậy phải được hiển thị an toàn.

Các tín hiệu cần xem xét:

- Một nguồn phát message type không thuộc quyền của nó.
- Cùng event ID xuất hiện với nội dung khác.
- Capture hoặc operation được dùng cho nhiều tài nguyên.
- Tăng đột biến các lỗi tenant, amount, currency hoặc merchant.
- Message từ môi trường khác hoặc key đã bị thu hồi.
- Nhiều message bị cách ly nhưng thiếu người xử lý và quy trình đối chiếu.
- Công cụ replay thay nội dung hoặc cố bỏ kiểm tra.
- Tác động nghiệp vụ không nối được với sự kiện và bằng chứng nguồn.

Audit của tác động thành công nên được gắn nguyên tử với thay đổi nghiệp vụ khi có thể. Audit cho message bị từ chối cần đường ghi phù hợp để không biến mất cùng transaction rollback.

## 12. Ví dụ xuyên suốt: nhận xác nhận thanh toán cho đơn hàng

Giả sử `order-781` thuộc `tenant-a`, phải thanh toán 250.000 VND qua một payment intent đã liên kết với merchant của tenant.

Luồng hợp lệ:

1. Payment service tiếp nhận và kiểm chứng kết quả capture theo tích hợp thanh toán.
2. Service ghi capture và outbox trong cùng transaction.
3. Relay phát `payment.capture_confirmed` qua đường được cấp quyền, giữ event ID và bằng chứng cần thiết.
4. Order consumer xác minh nguồn, type, môi trường, audience và schema.
5. Consumer đối chiếu tenant, merchant, intent, order, số tiền và đồng tiền.
6. Consumer ghi việc áp dụng capture, trạng thái đơn, inbox và audit/outbox trong transaction.
7. Sau commit, consumer ACK; nếu message bị giao lại, không tạo tác động mới.

Những nhánh phải bị chặn hoặc chuyển đối chiếu:

| Message nhận được | Xử lý mong đợi |
| --- | --- |
| Client tự publish JSON có issuer `payment-service` | Không tin field tự khai; chặn theo nguồn/quyền |
| Dịch vụ báo cáo phát sự kiện capture | Từ chối vì nguồn không có quyền phát type |
| Nguồn đúng nhưng amount chỉ 25.000 VND | Không đánh dấu đơn 250.000 VND đã trả |
| Capture thuộc merchant của tenant khác | Không áp dụng cho đơn |
| Đổi order ID trong một envelope được bảo vệ | Bằng chứng toàn vẹn không còn hợp lệ |
| Cùng capture được phát dưới event ID mới | Nhận diện cùng tác động hoặc chặn xung đột |
| Capture đã áp dụng cho đơn khác | Chặn, ghi bằng chứng và đối chiếu |
| Event đến khi đơn đã hủy | Không tự mở lại đơn; theo quy trình đối chiếu |
| Event hợp lệ nhưng nguồn vừa bị thu hồi độ tin cậy | Áp dụng chính sách xử lý message đang chờ, không tự mặc định cho phép |

Một message đúng nguồn, đúng số tiền và đúng capture có thể được chuyển nhiều lần. Kết quả cuối cần phản ánh một khoản thanh toán được áp dụng đúng một lần theo hợp đồng, cùng dấu vết đủ để giải thích nguồn và quyết định.

## 13. Kiểm thử niềm tin vào producer

Kiểm thử cần quan sát cả quyết định nguồn, dữ liệu nghiệp vụ, inbox, audit và hành vi xác nhận với broker.

| Tình huống | Kết quả cần kiểm chứng |
| --- | --- |
| Không có credential hoặc nguồn không hợp lệ | Không publish được hoặc không tạo tác động ở consumer theo ranh giới kiểm soát |
| Producer hợp lệ phát type vượt quyền | Bị chặn dù kết nối được xác thực |
| Tự khai issuer của service khác trong payload/header | Không trở thành danh tính đã xác minh |
| Relay đọc outbox không đúng miền rồi chọn destination nhạy cảm | Không vượt ánh xạ nguồn–destination đã cấp |
| Message thử nghiệm đi vào consumer production | Không tạo tác động production |
| Chữ ký hợp lệ nhưng key không được cấp cho type này | Không được coi là nguồn có thẩm quyền |
| Key ID không biết hoặc URL khóa tự khai | Không tải/tin khóa theo dữ liệu tùy ý từ message |
| Sửa amount, currency, tenant hoặc order ID được bảo vệ | Xác minh thất bại, không đổi dữ liệu nghiệp vụ |
| Sửa type/audience ngoài payload | Không chuyển được nội dung sang ngữ cảnh không được phép |
| Envelope chứa field trùng tên hoặc cấu trúc quá sâu | Từ chối theo quy tắc parse và giới hạn đã định nghĩa |
| Nguồn đúng nhưng tenant/merchant không khớp | Chặn theo quan hệ tài nguyên |
| Nguồn đúng nhưng số tiền thiếu hoặc sai đồng tiền | Không đánh dấu đơn đã thanh toán |
| Schema chưa được hỗ trợ | Cách ly có kiểm soát, không chọn handler theo phỏng đoán |
| Cùng event ID và cùng nội dung được giao nhiều lần | Một tác động; bản sao được nhận diện |
| Cùng event ID nhưng nội dung khác | Chặn xung đột, không dùng kết quả cũ cho nội dung mới |
| Khác event ID nhưng cùng capture | Không áp dụng tiền nhiều lần |
| Hai worker cùng xử lý capture | Unique constraint và transaction giữ đúng bất biến |
| Capture cùng lúc nhắm hai đơn | Tối đa một liên kết hợp lệ trong phạm vi capture đã định nghĩa |
| Transaction lỗi sau khi đổi đơn nhưng trước inbox/outbox | Rollback toàn bộ các thay đổi cùng transaction |
| Commit thành công rồi worker chết trước ACK | Retry nhận kết quả cũ, không tạo tác động mới |
| Event đến sau khi đơn đã hủy | Không tự mở lại trạng thái trái chính sách |
| Message cũ được replay sau khi cache hết hạn | Ràng buộc tác động bền vững vẫn ngăn thực hiện trùng |
| Replay từ DLQ dưới credential vận hành | Không bỏ kiểm tra nguồn và bất biến |
| Producer/key bị thu hồi khi có backlog | Các message đang chờ được xử lý theo chính sách thu hồi |
| Producer có quyền phát nhưng bị mô phỏng là nguồn gửi dữ liệu sai | Đo được các giới hạn consumer bảo vệ và phần còn phụ thuộc issuer |
| Lỗi tạm thời ở database | Retry có giới hạn với cùng định danh; không đổi lỗi thành thành công |
| Message bị từ chối | Không có tác động nghiệp vụ; có kết quả cách ly/audit theo chính sách |
| Luồng hợp lệ đầy đủ | Thực hiện đúng một tác động, có bằng chứng nguồn và liên kết audit |

Với kiểm thử quyền publish, dùng các danh tính khác nhau theo ma trận cấp quyền và thử cả đường relay, connector, công cụ replay. Chỉ mock hàm `isTrustedProducer()` trả false không chứng minh hạ tầng chặn đúng nguồn.

Với kiểm thử message có chữ ký, tạo dữ liệu đúng theo hợp đồng rồi sửa từng trường cần bảo vệ. Kiểm tra cả trường hợp chữ ký vẫn hợp lệ nhưng issuer, môi trường hoặc mục đích của khóa không được cấp quyền.

Với transaction và concurrency, tạo lỗi ở ranh giới trước commit, sau commit và trước ACK; dùng điểm đồng bộ để hai worker thực sự tranh chấp. Đọc dữ liệu đã commit từ một kết nối độc lập.

Không chỉ kiểm tra test âm. Một hệ thống từ chối mọi message có thể chặn giả mạo nhưng không phục vụ được nghiệp vụ. Cần chứng minh cả việc chấp nhận đúng nguồn, đúng bằng chứng và xử lý bản sao an toàn.

## 14. Tiêu chí hoàn thành thiết kế

Trước khi consumer cho phép message tạo tác động nhạy cảm, cần xác định được:

- Ai là issuer có thẩm quyền và ai chỉ vận chuyển dữ liệu?
- Cơ chế nào chứng minh nguồn thay vì tin tên tự khai?
- Mỗi nguồn được phát type nào, trong môi trường và phạm vi nào?
- Relay, connector và công cụ replay có thể thay đổi hay ký thay nội dung đến đâu?
- Những field nào được bảo vệ và bộ xử lý có dùng đúng nội dung đã xác minh không?
- Producer dựa vào bằng chứng nào để phát sự kiện kết quả?
- Consumer giữ bất biến nào về tenant, đối tượng, trạng thái, số tiền và quyền?
- Event ID và định danh tác động nghiệp vụ có được chống trùng riêng không?
- Tác động, inbox và audit/outbox có nhất quán khi lỗi hoặc cạnh tranh không?
- Thu hồi producer/khóa, message cũ và kết quả chưa rõ có quy trình xử lý không?

Niềm tin vào producer phải gắn với một khẳng định nghiệp vụ cụ thể. Khi nguồn, quyền phát, nội dung và bất biến được ràng buộc rõ, consumer có thể dùng message để phối hợp công việc mà không biến hàng đợi thành đường vòng vượt quyền hoặc tạo tác động trùng.
