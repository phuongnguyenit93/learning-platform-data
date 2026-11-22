# Rà soát khoảng trống hoặc trùng lặp giữa các nhóm phụ trách

Khi một sản phẩm được phát triển bởi nhiều nhóm, mỗi nhóm thường hiểu rõ phần việc của mình nhưng chưa chắc đã nhìn thấy toàn bộ luồng từ đầu đến cuối. Một nhóm có thể cho rằng nhóm khác đang kiểm tra một tích hợp; nhóm kia lại cho rằng phần đó nằm ngoài phạm vi. Ngược lại, hai nhóm có thể cùng duy trì những bộ kiểm thử gần như giống nhau, nhưng kết quả vẫn không phát hiện được lỗi tại ranh giới giữa hai thành phần.

Vì vậy, rà soát phạm vi giữa các nhóm là hoạt động cần thiết để tìm ra **điều chưa có ai chịu trách nhiệm kiểm tra, điều đang được kiểm tra nhiều lần mà không tạo thêm giá trị, và phần giao tiếp cần phối hợp rõ ràng**. Mục tiêu là bảo đảm rủi ro quan trọng có người phụ trách và có bằng chứng phù hợp, đồng thời giữ lại những phần kiểm thử chồng lấp có chủ đích.

## 1. Khoảng trống và trùng lặp trong phạm vi kiểm thử

### 1.1. Khoảng trống kiểm thử

Khoảng trống xuất hiện khi một yêu cầu, rủi ro, thành phần, luồng nghiệp vụ hoặc điều kiện quan trọng không được bao phủ bởi hoạt động kiểm thử phù hợp. Khoảng trống cũng có thể tồn tại khi một nhóm đã chạy kiểm thử nhưng không có người chịu trách nhiệm đánh giá kết quả hoặc xử lý lỗi.

Một số biểu hiện thường gặp:

- Một chức năng hoặc quy tắc nghiệp vụ không được liệt kê trong phạm vi của bất kỳ nhóm nào.
- Hai nhóm đều giả định nhóm còn lại kiểm thử API, sự kiện hoặc bước bàn giao dữ liệu.
- Kiểm thử chỉ bao gồm luồng thành công, bỏ qua timeout, dữ liệu không hợp lệ, quyền truy cập hoặc thao tác lặp.
- Một thuộc tính chất lượng như hiệu năng, bảo mật, khả năng phục hồi hoặc khả năng tiếp cận chưa có kế hoạch kiểm tra.
- Môi trường, dữ liệu kiểm thử hoặc dịch vụ phụ thuộc chưa có người chuẩn bị và xác nhận.
- Không có chủ sở hữu chịu trách nhiệm khi kiểm thử tích hợp thất bại.
- Một thay đổi được kiểm thử ở cấp thành phần nhưng chưa đánh giá tác động đến luồng người dùng hoặc vận hành.

Khoảng trống không chỉ là thiếu test case. Đó có thể là thiếu cơ sở kiểm thử, thiếu oracle, thiếu dữ liệu, thiếu môi trường, thiếu người quyết định hoặc thiếu bằng chứng để kết luận.

### 1.2. Trùng lặp kiểm thử

Trùng lặp xảy ra khi nhiều nhóm thực hiện các hoạt động có nội dung và mục tiêu gần như giống nhau mà không có lý do rõ ràng. Ví dụ, hai nhóm cùng duy trì một kịch bản đầu cuối, cùng dùng một bộ dữ liệu và cùng xác minh một điều kiện, nhưng không chia sẻ kết quả hoặc trách nhiệm bảo trì.

Trùng lặp không phải lúc nào cũng xấu. Có thể cần kiểm tra cùng một hành vi ở nhiều cấp hoặc từ nhiều góc nhìn để tăng độ tin cậy. Vấn đề cần xử lý là phần lặp lại không bổ sung độ bao phủ, tính độc lập, khả năng chẩn đoán hay bằng chứng có ích.

| Hiện tượng | Có phải vấn đề không? | Cách đánh giá |
|---|---|---|
| Hai nhóm cùng kiểm tra hợp đồng API, một nhóm ở phía cung cấp và một nhóm ở phía sử dụng | Thường không | Hai góc nhìn độc lập có thể phát hiện sai lệch khác nhau; cần thống nhất hợp đồng và chia sẻ kết quả. |
| Kiểm thử đơn vị, tích hợp và đầu cuối cùng xác minh một quy tắc quan trọng | Thường không | Mỗi cấp phát hiện một loại lỗi; cần bảo đảm mục tiêu và giá trị của từng cấp rõ ràng. |
| Hai nhóm duy trì cùng một kịch bản đầu cuối, cùng dữ liệu và cùng oracle | Có thể là vấn đề | Xác định liệu có mục tiêu độc lập hay chỉ làm tăng chi phí bảo trì. |
| Hai nhóm dùng expected result khác nhau cho cùng một quy tắc | Có | Đây là xung đột nguồn xác nhận; cần người có thẩm quyền thống nhất. |
| Nhiều nhóm cùng chạy kiểm thử tải trên một môi trường mà không điều phối | Có thể là vấn đề | Hoạt động có thể gây nhiễu kết quả hoặc cạnh tranh tài nguyên. |
| Một nhóm kiểm tra chức năng, nhóm khác kiểm tra bảo mật của cùng luồng | Thường không | Phạm vi khác nhau dù đối tượng có thể trùng nhau. |

### 1.3. Trùng lặp có chủ đích và trùng lặp lãng phí

Hãy đánh giá phần chồng lấp theo mục tiêu, phương pháp, dữ liệu, mức độ độc lập và cách sử dụng kết quả.

Trùng lặp có chủ đích có thể phục vụ:

- **Phòng vệ nhiều lớp:** kiểm tra cùng một quy tắc ở đơn vị, tích hợp và đầu cuối để phát hiện lỗi ở các ranh giới khác nhau.
- **Xác minh độc lập:** một nhóm kiểm tra độc lập đánh giá lại kết quả có rủi ro cao.
- **Góc nhìn nhà cung cấp và người sử dụng:** cả hai phía xác minh rằng hợp đồng giao tiếp được tuân thủ.
- **Khác biệt môi trường hoặc nền tảng:** cùng một chức năng cần được kiểm tra trên các cấu hình hoặc thiết bị khác nhau.
- **Khả năng phục hồi:** kiểm tra lại hành vi sau khi khôi phục, chuyển vùng hoặc triển khai phiên bản mới.

Trùng lặp lãng phí thường có các dấu hiệu: cùng một điều kiện và oracle, cùng cách thực hiện, không có yêu cầu độc lập, không ai sử dụng kết quả riêng biệt, và việc sửa một test case buộc nhiều nhóm sửa bản sao giống nhau.

## 2. Đơn vị cần rà soát giữa các nhóm

Không nên chỉ so sánh danh sách test case theo tên. Hai test case có tên khác nhau vẫn có thể kiểm tra cùng một điều kiện; hai test case có tên gần giống nhau có thể kiểm tra những rủi ro khác nhau.

Nên lập bản đồ phạm vi theo các chiều sau:

| Chiều rà soát | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Yêu cầu và quy tắc | Quy tắc hoặc tiêu chí chấp nhận nào cần được xác minh? | Tính tổng tiền, quyền hủy đơn |
| Luồng nghiệp vụ | Những bước nào tạo thành hành trình người dùng? | Tạo đơn, thanh toán, giao hàng, hoàn tiền |
| Thành phần và dịch vụ | Thành phần nào được kiểm tra và bởi nhóm nào? | Order Service, Payment Service |
| Giao diện tích hợp | Ai kiểm tra hợp đồng và hành vi tại ranh giới? | REST API, event, webhook, message queue |
| Dữ liệu | Ai kiểm tra schema, mapping, tính toàn vẹn và dữ liệu biên? | Bảng đơn hàng, mã giao dịch |
| Thuộc tính chất lượng | Ai kiểm tra hiệu năng, bảo mật, độ tin cậy và khả năng sử dụng? | Tải đồng thời, phân quyền, phục hồi |
| Điều kiện và trạng thái | Trường hợp bình thường, lỗi, biên và chuyển trạng thái nào đã được bao phủ? | Timeout, callback lặp, phiên hết hạn |
| Môi trường và cấu hình | Ai chuẩn bị và xác nhận cấu hình, feature flag, dịch vụ giả lập? | Sandbox thanh toán, cấu hình vùng |
| Bằng chứng và quyết định | Ai đánh giá kết quả, phân loại lỗi và chấp nhận rủi ro còn lại? | Báo cáo kiểm thử, phê duyệt phát hành |

Đơn vị rà soát hữu ích nhất thường là **rủi ro hoặc điều kiện cần xác minh**, gắn với yêu cầu và đối tượng kiểm thử. Từ đó mới xác định test case nào đáp ứng điều kiện, chạy ở cấp nào và nhóm nào chịu trách nhiệm.

## 3. Chuẩn bị bản đồ phạm vi của từng nhóm

Trước buổi rà soát, mỗi nhóm nên cung cấp một bản mô tả phạm vi có cấu trúc chung. Tối thiểu cần có:

- Mục tiêu và ranh giới trách nhiệm của nhóm.
- Các yêu cầu, luồng nghiệp vụ, dịch vụ, API, dữ liệu và cấu hình phụ trách.
- Rủi ro quan trọng và thuộc tính chất lượng cần kiểm tra.
- Các cấp độ kiểm thử đang thực hiện: đơn vị, thành phần, hợp đồng, tích hợp, hệ thống, đầu cuối hoặc chấp nhận.
- Điều kiện kiểm thử gồm luồng thành công, lỗi, biên, quyền truy cập và trạng thái đặc biệt.
- Bộ test case, kiểm thử tự động, kiểm thử thăm dò và bằng chứng được tạo ra.
- Nguồn xác nhận kết quả mong đợi và phiên bản đang sử dụng.
- Môi trường, dữ liệu, công cụ và dịch vụ phụ thuộc.
- Người thực hiện, người chịu trách nhiệm cuối cùng và nhóm phối hợp.
- Các phần ngoài phạm vi cùng lý do loại trừ và nhóm nhận bàn giao nếu có.

Các nhóm cần dùng định danh chung cho yêu cầu, API, sự kiện, dịch vụ và luồng nghiệp vụ. Nếu mỗi nhóm dùng tên riêng, việc đối chiếu sẽ khó phát hiện hai bản ghi đang nói về cùng một đối tượng.

Không cần thu thập mọi test case ngay từ đầu. Có thể bắt đầu bằng danh sách yêu cầu, rủi ro, đối tượng và trách nhiệm, sau đó mở rộng đến các trường hợp cụ thể ở vùng có rủi ro hoặc chồng lấp cao.

## 4. Lập ma trận trách nhiệm và độ bao phủ

Ma trận giúp nhìn thấy khoảng trống và giao nhau giữa các nhóm. Hàng có thể là yêu cầu, rủi ro, luồng hoặc giao diện; cột là nhóm chịu trách nhiệm. Trong mỗi ô, ghi vai trò và hoạt động cụ thể thay vì chỉ đánh dấu có hoặc không.

Ví dụ ký hiệu:

- **A — Accountable:** nhóm hoặc vai trò chịu trách nhiệm cuối cùng để phạm vi được kiểm tra và có kết luận.
- **R — Responsible:** nhóm trực tiếp thiết kế hoặc thực hiện hoạt động kiểm thử.
- **S — Supporting:** nhóm hỗ trợ môi trường, dữ liệu, chuyên môn hoặc dịch vụ phụ thuộc.
- **I — Informed:** nhóm cần nhận thông tin về kết quả hoặc thay đổi.
- **—:** chưa có trách nhiệm hoặc hoạt động được xác định.

Một ví dụ minh họa:

| Rủi ro hoặc điều kiện | Nhóm Đơn hàng | Nhóm Thanh toán | Nhóm Nền tảng | Nhóm Vận hành |
|---|---|---|---|---|
| Tạo đơn hợp lệ và lưu trạng thái ban đầu | A/R: kiểm thử đơn hàng | I | S: môi trường | I |
| API tạo giao dịch thanh toán | S: kiểm tra dữ liệu đơn | A/R: kiểm thử API và quy tắc giao dịch | S: sandbox | I |
| Callback thanh toán đến lặp | A/R: chuyển trạng thái đơn idempotent | R: xử lý callback và khóa giao dịch | S: message broker | I |
| Mất kết nối hoặc timeout nhà cung cấp | R: xác minh trạng thái đơn | A/R: xử lý timeout và đối soát | S: mô phỏng lỗi mạng | S: giám sát |
| Khôi phục dịch vụ và cảnh báo | S: xác minh luồng nghiệp vụ sau phục hồi | S: xác minh giao dịch sau phục hồi | R: nền tảng khôi phục | A/R: runbook và cảnh báo |

Ma trận này chỉ là ví dụ. Khi áp dụng, cần chỉ định một vai trò chịu trách nhiệm cuối cùng cho từng kết quả hoặc rủi ro quan trọng. Với giao diện liên nhóm, có thể có nhiều nhóm cùng thực hiện kiểm thử, nhưng phải có một đầu mối điều phối và quy định rõ bằng chứng mà mỗi bên cung cấp.

Nếu một hàng chỉ có dấu gạch ngang, đó là tín hiệu cần điều tra khoảng trống. Nếu một hàng có nhiều A mà không phân định quyết định, có thể tồn tại xung đột trách nhiệm. Nếu có nhiều R, hãy kiểm tra xem các hoạt động có mục tiêu bổ sung hay chỉ là bản sao.

## 5. Cách phát hiện khoảng trống

Có thể phát hiện khoảng trống bằng cách rà soát ma trận theo từng câu hỏi:

### 5.1. Rà soát theo yêu cầu và rủi ro

Với mỗi yêu cầu quan trọng, kiểm tra xem đã có:

- Điều kiện hoặc tình huống cần xác minh.
- Nguồn xác nhận kết quả mong đợi có hiệu lực.
- Nhóm chịu trách nhiệm thực hiện và đánh giá.
- Dữ liệu, môi trường và phụ thuộc cần thiết.
- Bằng chứng đủ để kết luận.

Nếu thiếu một trong các yếu tố này, ghi rõ loại khoảng trống. Ví dụ, yêu cầu có test case nhưng không có oracle thì chưa thể kết luận đạt hay không đạt.

### 5.2. Rà soát ranh giới giữa các nhóm

Những lỗi khó phát hiện thường nằm tại nơi dữ liệu hoặc trạng thái chuyển từ nhóm này sang nhóm khác. Hãy xem xét:

- Ai tạo dữ liệu và ai xác nhận dữ liệu đã nhận?
- Ai chịu trách nhiệm hợp đồng API hoặc sự kiện?
- Ai kiểm tra timeout, retry, thứ tự thông điệp và xử lý trùng?
- Ai kiểm tra trạng thái khi một bên thành công nhưng bên kia thất bại?
- Ai xác nhận việc rollback, bù trừ hoặc đối soát?
- Ai điều tra lỗi khi log và trace nằm ở nhiều hệ thống?

Một thành phần có thể được kiểm tra tốt trong phạm vi nội bộ nhưng vẫn lỗi khi tích hợp. Do đó, phải có hoạt động kiểm thử tại ranh giới và thống nhất cách phối hợp khi thất bại.

### 5.3. Rà soát các điều kiện bị bỏ quên

Đối chiếu phạm vi với các nhóm tình huống sau:

- Giá trị rỗng, thiếu trường, sai kiểu và dữ liệu ngoài miền hợp lệ.
- Giá trị tối thiểu, tối đa, sát ngưỡng và trường hợp làm tròn.
- Người dùng không đủ quyền, vai trò đặc biệt và phiên hết hạn.
- Timeout, mất kết nối, retry, callback hoặc thông điệp lặp.
- Xử lý đồng thời, tranh chấp cập nhật và thứ tự sự kiện khác nhau.
- Dữ liệu cũ, dữ liệu không nhất quán và migration.
- Tải cao, cạn tài nguyên, gián đoạn và khôi phục.
- Cấu hình khác nhau giữa môi trường, vùng triển khai hoặc phiên bản.
- Log, audit, cảnh báo và quy trình vận hành sau sự cố.

Không phải mọi trường hợp đều cần áp dụng cho mọi sản phẩm. Nhóm cần ghi nhận lý do ưu tiên hoặc loại trừ dựa trên rủi ro.

## 6. Cách phát hiện và xử lý trùng lặp

Để xác định hai hoạt động có thực sự trùng lặp, hãy so sánh ít nhất sáu yếu tố:

1. Mục tiêu hoặc rủi ro được kiểm tra.
2. Điều kiện đầu vào và trạng thái ban đầu.
3. Kết quả mong đợi và nguồn oracle.
4. Cấp độ, phương pháp và môi trường thực hiện.
5. Bằng chứng tạo ra và người sử dụng kết quả.
6. Mức độ độc lập và khả năng phát hiện lỗi khác nhau.

Hai test case chỉ trùng tên hoặc cùng chạm vào một API chưa đủ để kết luận lãng phí. Chúng có thể kiểm tra quyền khác nhau, dữ liệu khác nhau hoặc lỗi ở hai phía của hợp đồng.

Khi xác định trùng lặp không cần thiết, có thể chọn một trong các cách:

- **Hợp nhất:** duy trì một trường hợp kiểm thử và chia sẻ kết quả cho các nhóm liên quan.
- **Phân tách theo mục tiêu:** giữ các trường hợp có giá trị khác nhau nhưng làm rõ mục tiêu, điều kiện và chủ sở hữu.
- **Chuyển cấp kiểm thử:** chuyển kiểm tra chi tiết về cấp đơn vị hoặc API; giữ một số luồng đầu cuối đại diện để xác minh tích hợp.
- **Chia sẻ thành phần dùng chung:** tái sử dụng fixture, dữ liệu, thư viện hoặc bước chuẩn bị, đồng thời giữ các khẳng định riêng cần thiết.
- **Ngừng bản sao:** khi đã xác nhận một hoạt động khác cung cấp cùng bằng chứng và không cần xác minh độc lập.

Trước khi bỏ một kiểm thử, cần xác minh rằng nó không bảo vệ một rủi ro riêng, một nền tảng riêng hoặc một yêu cầu kiểm soát độc lập. Ghi lại lý do và người phê duyệt thay đổi phạm vi.

## 7. Quy trình tổ chức buổi rà soát liên nhóm

Một vòng rà soát có thể thực hiện theo các bước:

### Bước 1: Chốt ranh giới và mục tiêu

Xác định sản phẩm, luồng, phiên bản hoặc thay đổi cần rà soát. Thống nhất nhóm tham gia và mức độ chi tiết. Bắt đầu từ rủi ro quan trọng, không cần đưa toàn bộ test case của sản phẩm vào một buổi họp.

### Bước 2: Thu thập bản đồ phạm vi

Mỗi nhóm chuẩn bị danh sách yêu cầu, đối tượng, rủi ro, hoạt động kiểm thử, oracle, bằng chứng, người phụ trách và phần loại trừ. Dùng định danh chung và ghi rõ phiên bản.

### Bước 3: Ghép các bản đồ

Đối chiếu các dòng theo yêu cầu, luồng, giao diện, dữ liệu và rủi ro. Đánh dấu:

- Chưa có nhóm hoặc hoạt động kiểm thử.
- Có nhiều nhóm phụ trách nhưng chưa rõ ai quyết định.
- Có nhiều hoạt động giống nhau chưa rõ giá trị bổ sung.
- Có ranh giới chưa có kiểm thử tích hợp hoặc hợp đồng.
- Có khác biệt về oracle, dữ liệu hoặc môi trường.

### Bước 4: Phân loại và đánh giá tác động

Phân biệt khoảng trống thật, trùng lặp có chủ đích, trùng lặp lãng phí và khác biệt do phạm vi. Ước lượng tác động nếu bỏ sót, khả năng xảy ra, độ khó phát hiện và chi phí khắc phục sau phát hành.

### Bước 5: Thống nhất quyền sở hữu và phương án

Chỉ định nhóm chịu trách nhiệm cuối cùng, nhóm thực hiện, nhóm hỗ trợ và người cần được thông báo. Với giao diện liên nhóm, thống nhất hợp đồng, dữ liệu, môi trường, cách tái hiện lỗi và đầu mối xử lý.

### Bước 6: Ghi nhận hành động

Mỗi vấn đề cần có mô tả, mức ưu tiên, người phụ trách, thời hạn, kết quả mong đợi và liên kết đến yêu cầu hoặc test case. Nếu giữ lại phần chồng lấp, ghi rõ lý do.

### Bước 7: Xác minh sau điều chỉnh

Sau khi cập nhật phạm vi, chạy hoặc kiểm tra bằng chứng liên quan. Xác nhận khoảng trống đã được bao phủ, bản sao không cần thiết đã được xử lý và các nhóm vẫn nhận được thông tin cần thiết.

## 8. Ưu tiên xử lý theo rủi ro

Không phải mọi khoảng trống hoặc trùng lặp đều cần xử lý ngay. Hãy ưu tiên dựa trên tác động và chi phí.

| Mức ưu tiên | Dấu hiệu | Hành động gợi ý |
|---|---|---|
| Rất cao | Không có owner cho rủi ro có thể gây mất dữ liệu, sai giao dịch, lộ thông tin, vi phạm quy định hoặc gián đoạn nghiêm trọng | Chỉ định owner và hoạt động xác minh trước mốc phát hành liên quan |
| Cao | Thiếu kiểm thử tại ranh giới dịch vụ quan trọng, thiếu xử lý lỗi hoặc nhiều nhóm dùng oracle mâu thuẫn | Tổ chức phối hợp liên nhóm, chốt hợp đồng và bằng chứng |
| Trung bình | Trùng lặp đáng kể làm chậm pipeline hoặc tăng chi phí bảo trì nhưng rủi ro vẫn có kiểm soát | Lập kế hoạch hợp nhất hoặc phân tách theo mục tiêu |
| Thấp | Chồng lấp nhỏ, có thể giải thích và không ảnh hưởng đáng kể đến thời gian hoặc độ tin cậy | Ghi nhận lý do, theo dõi trong lần rà soát tiếp theo |

Một cách xếp hạng đơn giản là đánh giá khả năng xảy ra và mức độ ảnh hưởng, sau đó bổ sung độ khó phát hiện, phạm vi lan truyền và chi phí khắc phục. Không nên dùng một điểm số duy nhất để thay thế thảo luận chuyên môn; rủi ro bảo mật, an toàn hoặc tuân thủ có thể cần tiêu chí bắt buộc riêng.

## 9. Ví dụ: rà soát phạm vi giữa các nhóm trong luồng đặt hàng

Giả sử một nền tảng thương mại điện tử có bốn nhóm: Đơn hàng, Thanh toán, Nền tảng và Vận hành. Luồng chính gồm tạo đơn, tạo giao dịch, nhận callback, cập nhật trạng thái đơn và gửi thông báo.

### 9.1. Phát hiện khoảng trống

Trong buổi rà soát, nhóm Đơn hàng cho biết họ kiểm tra trạng thái đơn khi nhận callback thành công. Nhóm Thanh toán cho biết họ kiểm tra gửi giao dịch và nhận phản hồi từ nhà cung cấp. Tuy nhiên, chưa có nhóm nào xác minh trường hợp callback đến hai lần sau khi mạng bị gián đoạn.

Đây là khoảng trống tại ranh giới:

- Nhóm Thanh toán cần kiểm tra việc xác minh callback, mã giao dịch và chống xử lý lặp.
- Nhóm Đơn hàng cần kiểm tra chuyển trạng thái đơn một cách idempotent.
- Hai nhóm cần một kiểm thử tích hợp để xác nhận cùng một callback không tạo hai lần ghi nhận hoặc gửi thông báo trùng.
- Nhóm Nền tảng hỗ trợ mô phỏng việc gửi lại thông điệp và quan sát hàng đợi.
- Nhóm Vận hành xác nhận log, cảnh báo và khả năng điều tra khi trạng thái không đồng bộ.

Nhóm cần chỉ định đầu mối chịu trách nhiệm kết luận cho toàn bộ luồng và quy định bằng chứng mà từng nhóm cung cấp.

### 9.2. Phát hiện trùng lặp

Nhóm Đơn hàng và Thanh toán đều có một bộ kiểm thử đầu cuối từ tạo đơn đến hiển thị thanh toán thành công. Cả hai bộ đều dùng cùng môi trường, cùng dữ liệu và cùng xác minh một trạng thái cuối.

Sau khi so sánh, nhóm quyết định:

- Nhóm Đơn hàng duy trì kiểm thử đơn vị cho quy tắc và chuyển trạng thái đơn.
- Nhóm Thanh toán duy trì kiểm thử API, callback, timeout và idempotency.
- Hai nhóm cùng sở hữu kiểm thử hợp đồng và tích hợp tại ranh giới, với người điều phối được chỉ định.
- Pipeline chung duy trì một số luồng đầu cuối đại diện để xác minh hành trình người dùng.
- Các bộ kiểm thử đầu cuối trùng hoàn toàn được hợp nhất; kết quả vẫn được chia sẻ cho cả hai nhóm.

Việc hợp nhất giảm thời gian chạy và công sức bảo trì nhưng vẫn giữ bằng chứng ở các cấp cần thiết. Nếu một nhóm cần kiểm thử độc lập vì yêu cầu kiểm soát, phần đó phải được ghi rõ và duy trì riêng.

### 9.3. Bản ghi kết quả rà soát

| Phát hiện | Phân loại | Owner | Hành động | Bằng chứng hoàn tất |
|---|---|---|---|---|
| Callback lặp chưa được kiểm tra xuyên suốt | Khoảng trống | Đầu mối tích hợp Đơn hàng–Thanh toán | Thêm kiểm thử callback lặp và trạng thái đơn | Một callback được gửi lại không tạo giao dịch hoặc thông báo trùng |
| Hai bộ E2E xác minh cùng luồng thành công | Trùng lặp lãng phí | Chủ sở hữu pipeline chung | Hợp nhất một luồng đại diện và chia sẻ kết quả | Một luồng chạy trong pipeline, cả hai nhóm truy cập được báo cáo |
| Chưa thống nhất nguồn chuẩn cho trạng thái thanh toán | Xung đột oracle | Chủ nghiệp vụ thanh toán | Chốt state model và hợp đồng callback | Tài liệu trạng thái được duyệt và test case liên kết đúng phiên bản |

## 10. Duy trì phạm vi sau mỗi thay đổi

Ma trận phạm vi không nên chỉ được lập một lần rồi bỏ quên. Cần xem xét lại khi:

- Thêm hoặc bỏ dịch vụ, API, sự kiện hoặc nhà cung cấp.
- Thay đổi quyền sở hữu nhóm hoặc ranh giới tổ chức.
- Có thay đổi lớn về kiến trúc, dữ liệu, luồng nghiệp vụ hoặc cấu hình.
- Thêm nền tảng, vùng triển khai hoặc loại người dùng.
- Xảy ra sự cố tại ranh giới giữa các nhóm.
- Bộ kiểm thử bị hợp nhất, chuyển cấp hoặc ngừng duy trì.
- Có thay đổi về chính sách, oracle hoặc tiêu chí phát hành.

Nên gắn hoạt động rà soát phạm vi với quy trình quản lý thay đổi và các mốc phát hành. Khi một nhóm bàn giao thành phần, cần bàn giao cả hợp đồng, giả định, test data, môi trường, lỗi đã biết, bằng chứng hiện có và người liên hệ.

## 11. Đo lường hiệu quả rà soát

Chỉ số nên giúp nhận diện rủi ro và cải thiện phối hợp:

- Số rủi ro quan trọng chưa có owner hoặc chưa có bằng chứng.
- Số giao diện liên nhóm chưa có kiểm thử hợp đồng hoặc tích hợp phù hợp.
- Số xung đột về expected result, dữ liệu chuẩn hoặc trách nhiệm.
- Số hoạt động trùng lặp đã được phân loại, hợp nhất hoặc giữ lại có lý do.
- Thời gian xử lý một khoảng trống từ lúc phát hiện đến lúc có owner và bằng chứng.
- Số lỗi sau phát hành bắt nguồn từ ranh giới hoặc giả định giữa các nhóm.
- Độ ổn định và thời gian chạy của bộ kiểm thử chung.

Không nên xem số lượng test case hoặc tỷ lệ trùng lặp thấp là mục tiêu độc lập. Một số trùng lặp có chủ đích làm tăng độ tin cậy; ngược lại, ma trận có vẻ đầy đủ vẫn có thể bỏ sót rủi ro nếu các hoạt động chỉ kiểm tra cùng một luồng thành công.

## 12. Những sai lầm thường gặp

- **Chỉ so sánh tên test case:** dễ bỏ sót hai trường hợp cùng mục tiêu nhưng tên khác nhau, hoặc loại nhầm các trường hợp có mục tiêu riêng. Hãy so sánh điều kiện, oracle, phương pháp và bằng chứng.
- **Giả định phần giao nhau tự có người phụ trách:** các nhóm thường tập trung vào ranh giới của mình. Cần chỉ định đầu mối và kiểm thử cho mỗi giao diện quan trọng.
- **Xóa mọi kiểm thử trùng lặp:** có thể loại bỏ xác minh độc lập hoặc phòng vệ nhiều lớp. Trước khi hợp nhất, phải hiểu giá trị của từng hoạt động.
- **Chỉ đếm số lượng nhóm hoặc số lượng test:** số lượng không cho biết rủi ro đã được bao phủ hay chưa. Rà soát theo yêu cầu, điều kiện và bằng chứng.
- **Không thống nhất oracle:** hai nhóm có thể cùng chạy kiểm thử nhưng đưa ra kết luận trái ngược. Cần xác định nguồn có thẩm quyền và phiên bản.
- **Không ghi phần ngoài phạm vi:** phần loại trừ dễ bị hiểu nhầm là đã có nhóm khác kiểm tra. Ghi rõ lý do và người chấp nhận rủi ro.
- **Không cập nhật sau thay đổi:** ma trận nhanh chóng lỗi thời khi kiến trúc, nhóm hoặc phụ thuộc thay đổi. Gắn việc cập nhật với quy trình thay đổi.
- **Không theo dõi hành động sau buổi rà soát:** vấn đề được thảo luận nhưng không có owner, thời hạn và bằng chứng hoàn tất sẽ tiếp tục tồn tại.

## 13. Mẫu ghi nhận rà soát phạm vi

Có thể dùng mẫu sau cho từng phát hiện:

| Trường | Nội dung |
|---|---|
| Mã phát hiện | Định danh duy nhất |
| Yêu cầu, rủi ro hoặc giao diện | Phần cần được bao phủ |
| Các nhóm liên quan | Nhóm thực hiện, hỗ trợ và nhận kết quả |
| Mô tả hiện trạng | Hoạt động kiểm thử đang có và bằng chứng |
| Phân loại | Khoảng trống, trùng lặp lãng phí, trùng lặp có chủ đích, xung đột trách nhiệm hoặc xung đột oracle |
| Tác động và mức ưu tiên | Hậu quả nếu bỏ sót hoặc tiếp tục duy trì |
| Owner cuối cùng | Vai trò chịu trách nhiệm kết luận |
| Hành động | Bổ sung, hợp nhất, phân tách, chuyển cấp hoặc giữ lại |
| Thời hạn | Mốc cần hoàn tất |
| Bằng chứng đóng | Kết quả kiểm thử, hợp đồng, báo cáo hoặc phê duyệt |
| Trạng thái | Mới, đang xử lý, chờ xác nhận hoặc hoàn tất |

## 14. Luồng rà soát tổng thể

~~~mermaid
flowchart TD
    A["Thu thập phạm vi và rủi ro của từng nhóm"]
    B["Chuẩn hóa định danh yêu cầu, luồng, dịch vụ và giao diện"]
    C["Ghép ma trận trách nhiệm và bằng chứng"]
    D{"Có khoảng trống hoặc chồng lấp?"}
    E["Xác định khoảng trống<br/>Chưa có owner hoặc bằng chứng"]
    F["Đánh giá phần chồng lấp<br/>Có giá trị bổ sung hay chỉ lặp lại?"]
    G["Thống nhất owner, oracle và hoạt động"]
    H["Ghi hành động, thời hạn và bằng chứng đóng"]
    I["Xác minh phạm vi sau điều chỉnh"]
    J["Cập nhật ma trận khi có thay đổi"]
    A --> B --> C --> D
    D -->|Có| E
    D -->|Có| F
    D -->|Không| J
    E --> G
    F --> G
    G --> H --> I --> J
    J -. "Thay đổi mới hoặc sự cố" .-> A
~~~

Một lần rà soát có chất lượng phải tạo ra quyết định cụ thể: rủi ro nào cần được kiểm tra, nhóm nào chịu trách nhiệm, phần giao nhau nào cần phối hợp, phần trùng lặp nào được giữ lại hoặc hợp nhất, và bằng chứng nào xác nhận hành động đã hoàn tất. Khi những quyết định này được ghi nhận và cập nhật cùng thay đổi của sản phẩm, các nhóm có thể phối hợp ở ranh giới rõ ràng hơn và giảm nguy cơ bỏ sót chất lượng giữa các phần việc.
