# Xác định thành phần kiểm tra trực tiếp và thành phần chỉ kiểm chứng qua hợp đồng

Trong một hệ thống gồm nhiều dịch vụ, thư viện và nền tảng bên ngoài, nhóm kiểm thử cần xác định rõ phần nào phải được kiểm tra trực tiếp và phần nào nên được xác minh thông qua hợp đồng giao tiếp. Quyết định này giúp tập trung kiểm thử vào logic mà nhóm chịu trách nhiệm, đồng thời kiểm soát rủi ro tại ranh giới giữa các thành phần.

Kiểm tra trực tiếp một thành phần nghĩa là chủ động kiểm tra hành vi của chính thành phần đó trong phạm vi nhóm có thể kiểm soát: đầu vào, trạng thái, xử lý, đầu ra và các trường hợp lỗi. Kiểm chứng qua hợp đồng nghĩa là xác minh các bên giao tiếp tuân thủ những quy tắc đã thống nhất về giao diện và hành vi quan sát được, chẳng hạn cấu trúc thông điệp, kiểu dữ liệu, mã phản hồi, ý nghĩa trường và cách xử lý lỗi.

Đây là quyết định về phạm vi và trách nhiệm kiểm thử. Một hợp đồng tốt giúp kiểm tra tương thích giữa các thành phần, nhưng không tự chứng minh toàn bộ hệ thống tích hợp hoạt động đúng. Với các rủi ro quan trọng mà hợp đồng không thể mô tả hoặc kiểm chứng, nhóm vẫn cần kiểm thử tích hợp, kiểm thử trên môi trường thử nghiệm hoặc kiểm tra đầu cuối có chọn lọc.

## 1. Hiểu ranh giới thành phần trong hệ thống

Thành phần (component) là một đơn vị có trách nhiệm tương đối rõ trong kiến trúc, ví dụ một lớp, mô-đun, thư viện, dịch vụ, bộ chuyển đổi tích hợp, cơ sở dữ liệu hoặc hệ thống bên ngoài. Một thành phần thường cộng tác với các thành phần khác thông qua giao diện:

- Gọi hàm hoặc phương thức trong cùng tiến trình.
- Gửi yêu cầu HTTP/gRPC và nhận phản hồi.
- Gửi hoặc nhận thông điệp qua hàng đợi hay luồng sự kiện.
- Đọc và ghi dữ liệu qua cơ sở dữ liệu hoặc kho lưu trữ.
- Gọi API của nhà cung cấp bên thứ ba.

Ranh giới kiểm thử là điểm mà tại đó nhóm xác định trách nhiệm của thành phần đang được kiểm tra và cách các cộng tác viên được biểu diễn. Trong một kiểm thử đơn vị, ranh giới có thể bao quanh một lớp hoặc hàm. Trong kiểm thử dịch vụ, ranh giới có thể bao quanh một API và các thành phần nội bộ mà nhóm muốn xác minh cùng nhau.

Cần phân biệt ba vai trò:

- **Thành phần đang kiểm tra (SUT — System Under Test):** thành phần mà kiểm thử muốn đưa ra kết luận về hành vi.
- **Cộng tác viên (collaborator):** thành phần mà SUT sử dụng để hoàn thành công việc, ví dụ kho dữ liệu, dịch vụ định giá hoặc cổng thanh toán.
- **Hợp đồng (contract):** tập hợp quy tắc mà các bên giao tiếp phải tuân thủ. Hợp đồng có thể mô tả cấu trúc, giao thức và ngữ nghĩa của tương tác.

Ví dụ, `CheckoutService` có thể là SUT. Nó gọi `InventoryClient` để giữ hàng và `PaymentClient` để tạo thanh toán. Nhóm có thể kiểm tra trực tiếp quy tắc tính tổng tiền và chuyển trạng thái đơn hàng trong `CheckoutService`, đồng thời xác minh các yêu cầu gửi đến dịch vụ kho và cổng thanh toán tuân thủ hợp đồng tương ứng.

## 2. Khi nào nên kiểm tra trực tiếp một thành phần?

Ưu tiên kiểm tra trực tiếp khi nhóm sở hữu mã nguồn, kiểm soát được cách triển khai hoặc cần xác nhận logic nội bộ của thành phần. Các câu hỏi thường gặp gồm:

- Với cùng đầu vào và trạng thái ban đầu, thành phần có tạo ra kết quả đúng không?
- Quy tắc nghiệp vụ, phép tính, quyết định và chuyển trạng thái có chính xác không?
- Các giá trị biên, dữ liệu không hợp lệ và trường hợp ngoại lệ có được xử lý đúng không?
- Khi cộng tác viên thất bại, thành phần có giữ được bất biến dữ liệu và đưa ra hành vi phục hồi phù hợp không?
- Thay đổi trong thành phần có làm hỏng hành vi đã được xác nhận trước đó không?

Kiểm tra trực tiếp thường phù hợp với:

1. **Logic nghiệp vụ do nhóm sở hữu:** tính giá, áp dụng giảm giá, kiểm tra điều kiện, phân quyền ở cấp ứng dụng và chuyển trạng thái.
2. **Quy tắc điều phối:** thứ tự gọi dịch vụ, quyết định thử lại, xử lý timeout, chống gửi lặp và bù trừ giao dịch.
3. **Bộ chuyển đổi hoặc adapter do nhóm viết:** ánh xạ mô hình nội bộ sang yêu cầu bên ngoài, phân tích phản hồi và chuyển lỗi thành kiểu lỗi của ứng dụng.
4. **Xử lý dữ liệu nội bộ:** xác thực, chuẩn hóa, chuyển đổi, lọc và kiểm tra bất biến.
5. **Tích hợp với hạ tầng mà nhóm kiểm soát:** truy vấn, transaction, migration hoặc hành vi lưu trữ cần được xác minh với công nghệ thật trong môi trường kiểm thử.

Kiểm thử trực tiếp không nhất thiết có nghĩa là phải kiểm tra mọi chi tiết triển khai. Nên xác minh hành vi quan sát được và các bất biến quan trọng. Nếu kiểm thử phụ thuộc quá nhiều vào cấu trúc nội bộ, thay đổi cách tổ chức mã có thể làm kiểm thử hỏng dù hành vi vẫn đúng.

## 3. Khi nào nên kiểm chứng qua hợp đồng?

Kiểm chứng qua hợp đồng phù hợp khi thành phần giao tiếp với một bên khác qua giao diện đã xác định, đặc biệt khi nhóm không sở hữu hoặc không kiểm soát phần triển khai của bên kia. Mục tiêu là xác nhận hai bên hiểu giao diện theo cùng một cách.

Các tình huống thường phù hợp:

- Dịch vụ do một nhóm khác sở hữu và phát hành độc lập.
- API của nhà cung cấp bên thứ ba như thanh toán, định danh, vận chuyển hoặc gửi thông báo.
- Thông điệp trao đổi qua broker, event bus hoặc hàng đợi giữa các dịch vụ.
- Thư viện hoặc nền tảng được tích hợp qua một giao diện công khai và có phiên bản.
- Nhiều ứng dụng hoặc dịch vụ cần tương thích với cùng một schema hay giao thức.

Hợp đồng nên mô tả những gì bên gọi được phép gửi, những gì bên cung cấp phải trả về và ý nghĩa của từng trường hợp. Tùy giao diện, hợp đồng có thể bao gồm:

- Địa chỉ, phương thức, tên thao tác hoặc loại thông điệp.
- Tên trường, kiểu dữ liệu, định dạng, trường bắt buộc và trường có thể vắng mặt.
- Quy tắc xác thực và ràng buộc giá trị.
- Mã trạng thái, cấu trúc phản hồi và ý nghĩa lỗi.
- Cơ chế xác thực, quyền truy cập và các header cần thiết.
- Quy tắc tương thích phiên bản, trường mở rộng và cách xử lý dữ liệu chưa biết.
- Ngữ nghĩa của thao tác như tính lặp an toàn, thứ tự thông điệp, xác nhận nhận tin hoặc cách thử lại nếu các bên đã thống nhất.

Hợp đồng có thể được thể hiện bằng OpenAPI cho HTTP API, AsyncAPI hoặc schema cho thông điệp bất đồng bộ, IDL cho gRPC, schema dữ liệu, tài liệu giao diện hoặc bộ kiểm thử hợp đồng. Tài liệu chỉ hữu ích khi được duy trì đồng bộ với hành vi thực tế và có cơ chế xác minh.

## 4. Phân biệt kiểm thử hợp đồng với kiểm thử dùng mock

Mock, stub và fake là các đối tượng thay thế được dùng để kiểm soát cộng tác viên trong một kiểm thử. Chúng giúp tạo phản hồi xác định, mô phỏng lỗi và kiểm tra cách SUT phản ứng. Tuy nhiên, việc một mock trả về dữ liệu mà kiểm thử mong đợi không chứng minh dịch vụ thật sẽ trả về dữ liệu đó.

Ví dụ, kiểm thử `CheckoutService` có thể dùng mock `PaymentClient` để mô phỏng thanh toán thành công, bị từ chối hoặc timeout. Kiểm thử này cho biết `CheckoutService` xử lý từng tình huống ra sao. Nó không xác minh API của nhà cung cấp thanh toán có thực sự dùng đúng tên trường, mã phản hồi hoặc quy tắc lỗi hay không.

Kiểm thử hợp đồng bổ sung bằng chứng ở ranh giới giao tiếp:

- **Phía consumer (bên sử dụng):** xác định các tương tác mà consumer thực sự cần và xác minh client gửi yêu cầu, đọc phản hồi theo hợp đồng.
- **Phía provider (bên cung cấp):** xác minh phiên bản provider có thể đáp ứng các tương tác và quy tắc được công bố trong hợp đồng.

Trong mô hình consumer-driven contract, consumer ghi lại những tương tác quan trọng mà nó phụ thuộc. Hợp đồng được chia sẻ với provider; provider chạy kiểm thử xác minh hợp đồng trên phiên bản của mình. Kết quả giúp phát hiện thay đổi không tương thích trước khi các bên triển khai độc lập.

Mock có thể được sinh từ hợp đồng để kiểm thử consumer. Tuy nhiên, kiểm thử chỉ xác nhận mock phù hợp với hợp đồng chưa đủ chứng minh provider thật cũng tuân thủ. Cần có bước xác minh ở phía provider hoặc, nếu không có quyền truy cập provider, cần nêu rõ giới hạn và bổ sung kiểm tra phù hợp.

## 5. Chọn phạm vi theo quyền sở hữu và rủi ro

Không nên quyết định chỉ dựa vào tên gọi “nội bộ” hay “bên ngoài”. Cần xem xét quyền sở hữu, khả năng kiểm soát, mức độ quan trọng và loại bằng chứng cần có.

| Câu hỏi | Nếu câu trả lời là có | Hướng kiểm thử thường phù hợp |
| --- | --- | --- |
| Nhóm có sở hữu và thay đổi được logic của thành phần không? | Có thể xác định hành vi nội bộ và sửa khi phát hiện sai lệch | Kiểm tra trực tiếp logic và các trường hợp biên |
| Thành phần có giao tiếp với bên khác qua giao diện ổn định không? | Có thể mô tả yêu cầu và cam kết tại ranh giới | Kiểm chứng hợp đồng ở phía consumer và provider khi có thể |
| Nhóm không kiểm soát được triển khai của bên cung cấp? | Không thể kiểm tra nội bộ hoặc sửa mã của bên đó | Kiểm tra cách sử dụng hợp đồng, adapter và tương tác trên sandbox khi cần |
| Rủi ro phụ thuộc vào hành vi nhiều thành phần cùng lúc? | Hợp đồng riêng lẻ không thể chứng minh luồng kết hợp | Bổ sung kiểm thử tích hợp hoặc đầu cuối có chọn lọc |
| Hạ tầng có ngữ nghĩa riêng mà hợp đồng API không mô tả đủ? | Có thể có rủi ro về transaction, thứ tự, độ bền hoặc tính nhất quán | Kiểm thử tích hợp với hạ tầng thật trong môi trường kiểm thử |

Có thể dùng quy trình sau để xác định phạm vi:

1. **Lập bản đồ thành phần:** liệt kê các thành phần tham gia vào luồng nghiệp vụ, chủ sở hữu, giao diện và phụ thuộc.
2. **Chọn thành phần chịu trách nhiệm:** xác định nơi chứa logic hoặc quyết định cần xác minh. Thành phần này là đối tượng kiểm tra trực tiếp.
3. **Xác định ranh giới giao tiếp:** với mỗi cộng tác viên, ghi lại giao thức, schema, phiên bản và ngữ nghĩa quan trọng.
4. **Đánh giá quyền kiểm soát:** xác định nhóm có thể chạy mã provider, thay đổi cấu hình, truy cập sandbox hay chỉ sử dụng tài liệu công khai.
5. **Liên kết rủi ro với bằng chứng:** chọn kiểm thử trực tiếp cho logic sở hữu, kiểm thử hợp đồng cho giao tiếp và kiểm thử tích hợp cho rủi ro xuyên ranh giới.
6. **Ghi rõ phần chưa xác minh:** liệt kê giao diện chưa có hợp đồng, provider chưa xác minh hoặc hành vi chỉ được kiểm tra trong môi trường giả lập.

## 6. Ví dụ: phân chia phạm vi kiểm thử cho luồng thanh toán

Giả sử một cửa hàng trực tuyến có các thành phần sau:

- `CheckoutService`: tính tổng tiền, điều phối quy trình đặt hàng và cập nhật trạng thái đơn.
- `PaymentAdapter`: chuyển đổi mô hình thanh toán nội bộ thành yêu cầu của cổng thanh toán.
- `Payment Provider`: dịch vụ thanh toán do công ty bên ngoài vận hành.
- `OrderRepository`: lưu đơn hàng và trạng thái giao dịch vào cơ sở dữ liệu do nhóm quản lý.
- `Notification Provider`: dịch vụ gửi email hoặc tin nhắn do nhà cung cấp vận hành.

Phạm vi có thể được chia như sau:

| Thành phần | Quyền sở hữu | Kiểm tra trực tiếp | Kiểm chứng qua hợp đồng hoặc tích hợp |
| --- | --- | --- | --- |
| `CheckoutService` | Nhóm cửa hàng | Tính tiền, áp dụng ưu đãi, chuyển trạng thái, xử lý thành công/thất bại/timeout, quyết định thử lại | Dùng client thay thế để mô phỏng các phản hồi đã định nghĩa; xác minh hợp đồng của các client riêng biệt |
| `PaymentAdapter` | Nhóm cửa hàng | Ánh xạ số tiền, tiền tệ, mã đơn, khóa idempotency; phân tích phản hồi và chuyển lỗi | Kiểm tra yêu cầu/phản hồi theo hợp đồng của Payment Provider; dùng sandbox cho luồng quan trọng nếu được cung cấp |
| `Payment Provider` | Bên thứ ba | Không kiểm tra trực tiếp logic nội bộ của nhà cung cấp | Xác minh theo tài liệu/hợp đồng công khai; sandbox hoặc kiểm tra tích hợp có giới hạn; theo dõi thay đổi và lỗi khi vận hành |
| `OrderRepository` và cơ sở dữ liệu | Nhóm cửa hàng kiểm soát mã và môi trường kiểm thử | Kiểm tra logic truy vấn, ánh xạ và quy tắc lưu trữ | Kiểm thử tích hợp với cơ sở dữ liệu thật để xác minh transaction, constraint, migration và tính nhất quán |
| `Notification Provider` | Bên thứ ba | Kiểm tra trực tiếp adapter gửi thông báo và cách ứng dụng xử lý lỗi | Xác minh schema, xác thực, mã phản hồi và ngữ nghĩa gửi theo hợp đồng; sandbox để kiểm tra luồng nếu rủi ro yêu cầu |

Ví dụ, khi `Payment Provider` trả về timeout, `CheckoutService` phải giữ trạng thái giao dịch chưa xác định và tránh tạo thanh toán mới một cách mù quáng. Có thể kiểm tra trực tiếp quyết định này bằng một client giả lập. Đồng thời, hợp đồng cần làm rõ cách nhận diện yêu cầu, khả năng gửi lại an toàn, mã phản hồi và cách truy vấn trạng thái nếu nhà cung cấp hỗ trợ. Một kiểm thử sandbox có thể xác minh luồng thực tế, nhưng vẫn cần ghi nhận giới hạn của môi trường sandbox so với production.

Với `OrderRepository`, một mock có thể xác nhận `CheckoutService` yêu cầu lưu trạng thái. Nhưng mock không thể chứng minh cơ sở dữ liệu thực thi transaction hoặc constraint đúng. Vì nhóm kiểm soát môi trường cơ sở dữ liệu, cần kiểm thử tích hợp với công nghệ thật cho những rủi ro này.

## 7. Ví dụ về nội dung hợp đồng API

Giả sử ứng dụng cần gọi thao tác tạo thanh toán. Hợp đồng minh họa có thể quy định:

```yaml
operation: createPayment
method: POST
path: /payments
request:
  headers:
    Idempotency-Key: required string
  body:
    orderId: required string
    amount: required integer
    currency: required string
responses:
  201:
    body:
      paymentId: required string
      status: required enum [pending, authorized]
  400:
    meaning: request is invalid
  409:
    meaning: request conflicts with an existing operation
  503:
    meaning: provider is temporarily unavailable
```

Đây chỉ là ví dụ về hình thức mô tả, không phải hợp đồng thực tế của một nhà cung cấp cụ thể. Khi áp dụng, hai bên cần thống nhất đơn vị tiền, quy tắc làm tròn, cách biểu diễn trạng thái, ý nghĩa từng mã lỗi và điều kiện gửi lại yêu cầu.

Một bộ kiểm thử hợp đồng nên kiểm tra ít nhất:

- Yêu cầu hợp lệ có đủ trường bắt buộc, đúng kiểu và định dạng.
- Các trường không hợp lệ hoặc bị thiếu được xử lý theo quy tắc đã thống nhất.
- Phản hồi thành công có cấu trúc và ý nghĩa đúng.
- Phản hồi lỗi được ánh xạ đúng, không làm mất thông tin cần thiết để xử lý.
- Trường mở rộng hoặc trường không được consumer nhận biết được xử lý tương thích theo quy tắc.
- Hành vi gửi lặp, timeout và truy vấn trạng thái tuân thủ ngữ nghĩa đã cam kết, nếu các hành vi này nằm trong hợp đồng.

Kiểm tra schema đơn thuần có thể xác nhận kiểu dữ liệu nhưng không luôn xác nhận ngữ nghĩa nghiệp vụ. Ví dụ, `amount` là số nguyên vẫn chưa đủ để biết đơn vị là đồng hay xu. Hợp đồng cần mô tả đơn vị và quy tắc diễn giải.

## 8. Hợp đồng cho giao tiếp bất đồng bộ

Với hàng đợi và sự kiện, bên gửi và bên nhận không gọi nhau trực tiếp nhưng vẫn phụ thuộc vào cấu trúc và ngữ nghĩa thông điệp. Hợp đồng sự kiện nên xác định:

- Tên sự kiện và phiên bản schema.
- Trường định danh, thời điểm phát sinh và thực thể liên quan.
- Trường bắt buộc, kiểu dữ liệu, đơn vị và quy tắc tương thích.
- Ý nghĩa của từng trạng thái và điều kiện phát sự kiện.
- Quy tắc xử lý sự kiện trùng lặp, thứ tự, thử lại và thông điệp lỗi nếu hệ thống cam kết các hành vi đó.

Ví dụ, `OrderPaid` có thể chứa `eventId`, `orderId`, `paidAt`, `amount` và `currency`. Consumer cần kiểm chứng rằng nó chấp nhận đúng schema và xử lý sự kiện theo ngữ nghĩa đã thống nhất. Producer cần xác minh thông điệp phát ra phù hợp hợp đồng. Nếu thứ tự sự kiện hoặc gửi ít nhất một lần là đặc tính của nền tảng, nhóm cũng cần kiểm thử hành vi xử lý trùng và sai thứ tự ở consumer.

Kiểm thử schema sự kiện không tự xác minh broker đã lưu bền thông điệp, phân phối đúng cấu hình hoặc bảo đảm thứ tự như kỳ vọng. Những thuộc tính phụ thuộc vào nền tảng cần được kiểm tra bằng tích hợp phù hợp.

## 9. Những giới hạn của kiểm chứng qua hợp đồng

Hợp đồng tạo ra một ranh giới rõ và có thể kiểm tra tự động, nhưng chỉ bao phủ những điều đã được mô tả. Các giới hạn quan trọng gồm:

- **Không chứng minh logic nội bộ của provider:** hợp đồng cho biết provider đáp ứng giao diện đã công bố, không cho biết thuật toán bên trong có tối ưu hoặc không có lỗi khác.
- **Không chứng minh toàn bộ luồng liên hệ thống:** từng API có thể tuân thủ hợp đồng nhưng chuỗi nhiều lời gọi vẫn có thể thất bại do cấu hình, thứ tự hoặc trạng thái dùng chung.
- **Không bao phủ mọi điều kiện vận hành:** độ trễ, mất mạng, giới hạn lưu lượng, hết hạn chứng thư, vùng triển khai và sự cố hạ tầng có thể cần kiểm thử riêng.
- **Không đảm bảo dữ liệu production giống dữ liệu kiểm thử:** dữ liệu thực có thể có quy mô, phân bố và trường hợp bất thường khác.
- **Có thể lỗi thời:** hợp đồng cũ hoặc không được xác minh trong quy trình phát hành sẽ tạo cảm giác an toàn sai.
- **Có thể thiếu ngữ nghĩa:** schema đúng kiểu vẫn có thể diễn giải sai đơn vị, múi giờ, trạng thái hoặc quy tắc nghiệp vụ.

Với nhà cung cấp bên thứ ba, nhóm thường không thể chạy bộ kiểm thử phía provider trên hệ thống production. Khi đó, cần kết hợp tài liệu chính thức, kiểm thử adapter, sandbox, kiểm tra tương thích theo phiên bản, giám sát và quy trình xử lý thay đổi. Báo cáo phải nói rõ phần nào đã được xác minh trực tiếp và phần nào dựa trên cam kết của nhà cung cấp.

## 10. Những lỗi thường gặp khi phân chia phạm vi

- **Kiểm tra trực tiếp phần không sở hữu:** cố kiểm thử nội bộ dịch vụ bên thứ ba dù không có mã nguồn hoặc quyền kiểm soát, dẫn tới kết luận vượt quá bằng chứng.
- **Chỉ dùng mock và gọi đó là kiểm thử hợp đồng:** mock trả về phản hồi do nhóm định nghĩa không chứng minh provider thật tuân thủ giao diện.
- **Chỉ kiểm tra schema:** bỏ qua ngữ nghĩa trường, quy tắc lỗi, phiên bản và hành vi gửi lại.
- **Bỏ qua adapter của chính nhóm:** cho rằng provider có hợp đồng là đủ, trong khi mã ánh xạ và xử lý lỗi của consumer vẫn có thể sai.
- **Không kiểm tra hạ tầng thật:** dùng mock cho cơ sở dữ liệu hoặc broker rồi kết luận transaction, độ bền và thứ tự đã được xác minh.
- **Lặp lại cùng một kiểm thử ở mọi tầng:** làm tăng thời gian chạy và chi phí bảo trì mà không bổ sung bằng chứng mới.
- **Không ghi rõ giới hạn:** báo cáo “tích hợp thành công” dù chỉ chạy với mock hoặc sandbox mà không nêu điều kiện.

Để tránh các lỗi này, mỗi kiểm thử nên trả lời rõ thành phần nào là SUT, cộng tác viên nào được thay thế, hợp đồng nào đang được xác minh, môi trường nào được dùng và rủi ro nào vẫn chưa được bao phủ.

## 11. Checklist xác định phạm vi

Trước khi hoàn thiện chiến lược kiểm thử cho một luồng, hãy kiểm tra:

- [ ] Đã liệt kê các thành phần và chủ sở hữu của chúng.
- [ ] Đã xác định thành phần chịu trách nhiệm cho từng quy tắc nghiệp vụ.
- [ ] Đã chọn các thành phần cần kiểm tra trực tiếp và xác định hành vi cần xác minh.
- [ ] Đã xác định ranh giới giao tiếp và hợp đồng tương ứng.
- [ ] Đã phân biệt kiểm thử dùng mock với kiểm thử hợp đồng thực sự.
- [ ] Đã xác định cách xác minh phía consumer và phía provider.
- [ ] Đã bổ sung kiểm thử tích hợp cho rủi ro không thể biểu diễn bằng hợp đồng.
- [ ] Đã ghi nhận giới hạn của sandbox, mock, tài liệu và môi trường.
- [ ] Đã xác định cách phát hiện thay đổi hợp đồng không tương thích trước khi triển khai.

## 12. Những điểm cần ghi nhớ

- Kiểm tra trực tiếp phù hợp với logic và hành vi mà nhóm sở hữu hoặc kiểm soát.
- Kiểm chứng qua hợp đồng phù hợp với ranh giới giao tiếp giữa các thành phần, đặc biệt khi provider do nhóm khác hoặc bên thứ ba quản lý.
- Mock giúp kiểm soát cộng tác viên trong kiểm thử consumer; nó không tự chứng minh provider thật tuân thủ hợp đồng.
- Hợp đồng cần mô tả cả cấu trúc lẫn ngữ nghĩa quan trọng như lỗi, đơn vị, trạng thái, tính lặp an toàn và phiên bản.
- Kiểm thử tích hợp vẫn cần thiết cho rủi ro xuyên nhiều thành phần hoặc phụ thuộc vào hạ tầng thật.
- Phạm vi kiểm thử phải nêu rõ bằng chứng đã có và phần chưa thể xác minh.

## Câu hỏi tự kiểm tra

1. Hãy phân biệt thành phần đang kiểm tra, cộng tác viên và hợp đồng giao tiếp.
2. Vì sao kiểm thử `CheckoutService` bằng mock `PaymentClient` không chứng minh cổng thanh toán bên ngoài tuân thủ API?
3. Một dịch vụ khác do nhóm nội bộ sở hữu và phát hành độc lập. Bạn sẽ kết hợp kiểm thử trực tiếp và kiểm thử hợp đồng như thế nào?
4. Khi nào cần kiểm thử tích hợp với cơ sở dữ liệu hoặc broker thật dù đã có hợp đồng giao diện?
5. Hãy chọn một luồng nghiệp vụ trong hệ thống của bạn, lập danh sách thành phần, chủ sở hữu, hành vi cần kiểm tra trực tiếp và hợp đồng cần xác minh.
6. Nếu nhà cung cấp bên thứ ba chỉ cung cấp sandbox và tài liệu API, báo cáo kiểm thử cần nêu những giới hạn bằng chứng nào?
