# Chuyển phát hiện có giá trị thành hồi quy phù hợp

## Mục tiêu bài học

Kiểm thử thủ công và kiểm thử khám phá giúp nhóm phát hiện những hành vi bất thường mà kịch bản đã viết sẵn có thể chưa bao phủ. Một phát hiện có giá trị có thể là lỗi chức năng, sai lệch dữ liệu, vấn đề bảo mật, khó khăn trong quy trình người dùng hoặc một giả định thiết kế không đúng. Sau khi xử lý phát hiện, nhóm cần quyết định có nên biến nó thành kiểm tra hồi quy hay không, và nếu có thì đặt kiểm tra ở tầng nào.

Trong chiến lược VALIDATION_TESTING_STRATEGY, hồi quy phù hợp giúp bảo vệ sản phẩm khỏi việc lặp lại lỗi đã biết mà không làm bộ kiểm thử phình to hoặc mong manh. Không phải mọi thao tác trong một phiên khám phá đều cần được tự động hóa. Điều cần giữ lại là bằng chứng có giá trị: hành vi sai đã quan sát, điều kiện gây ra nó, quy tắc cần bảo vệ và cách phát hiện lỗi tái diễn với chi phí hợp lý.

Sau bài học, người học có thể:

- Phân biệt phát hiện, lỗi đã xác nhận, rủi ro và đề xuất cải tiến.
- Ghi nhận đủ bối cảnh để tái hiện và điều tra một phát hiện.
- Xác định nguyên nhân và hành vi cần được bảo vệ sau khi sửa.
- Chọn mức kiểm thử hồi quy phù hợp với nguyên nhân và ranh giới bị ảnh hưởng.
- Viết kiểm tra ổn định, có ý nghĩa và ít phụ thuộc vào chi tiết triển khai.
- Quyết định khi nào nên tự động hóa, giữ kiểm tra thủ công hoặc chỉ theo dõi rủi ro.
- Quản lý bộ hồi quy để duy trì giá trị qua các lần thay đổi sản phẩm.

## 1. Từ phát hiện khám phá đến tài sản kiểm thử

Kiểm thử khám phá (exploratory testing) kết hợp việc học hỏi về sản phẩm, thiết kế kiểm tra và thực thi kiểm tra trong cùng một hoạt động. Người kiểm thử quan sát hành vi, hình thành giả thuyết, thử các điều kiện khác nhau và điều chỉnh hướng kiểm tra dựa trên bằng chứng mới.

Một phiên khám phá có thể phát hiện:

- Hành vi vi phạm yêu cầu hoặc quy tắc nghiệp vụ.
- Trường hợp biên mà đặc tả chưa mô tả rõ.
- Tương tác giữa nhiều chức năng tạo ra trạng thái không hợp lệ.
- Vấn đề về quyền truy cập, dữ liệu hoặc bảo mật.
- Khó khăn khiến người dùng hiểu sai trạng thái hoặc không hoàn thành nhiệm vụ.
- Giả định về môi trường, cấu hình hoặc phụ thuộc không đúng.
- Một rủi ro tiềm ẩn cần được điều tra thêm dù chưa tái hiện được lỗi.

Không nên chuyển thẳng mọi bước thao tác trong phiên khám phá thành test case. Một chuỗi thao tác dài có thể chỉ là cách người kiểm thử tìm ra nguyên nhân. Bộ hồi quy cần bảo vệ hành vi quan trọng và điều kiện gây lỗi, không nhất thiết phải tái tạo nguyên xi toàn bộ hành trình khám phá.

Một phát hiện chỉ trở thành kiểm tra hồi quy hữu ích khi nhóm hiểu điều gì cần được bảo vệ và có cách xác định rõ kết quả đúng. Nếu chưa rõ hành vi mong đợi, trước tiên cần làm rõ yêu cầu hoặc quyết định nghiệp vụ.

## 2. Phân loại phát hiện trước khi tạo hồi quy

Phát hiện trong kiểm thử thủ công không phải lúc nào cũng là lỗi phần mềm. Phân loại đúng giúp chọn hành động và tránh tạo kiểm tra dựa trên một giả định sai.

| Loại phát hiện | Dấu hiệu | Hướng xử lý |
|---|---|---|
| Lỗi đã xác nhận | Hành vi thực tế khác yêu cầu, tiêu chí chấp nhận hoặc hợp đồng đã thống nhất. | Ghi lỗi, điều tra nguyên nhân, sửa và đánh giá kiểm thử hồi quy. |
| Thiếu hoặc mơ hồ về yêu cầu | Không có căn cứ đủ rõ để xác định hành vi mong đợi. | Làm rõ với chủ sở hữu nghiệp vụ; cập nhật yêu cầu trước khi kết luận. |
| Cải tiến sản phẩm | Sản phẩm đáp ứng cam kết nhưng có cơ hội tạo trải nghiệm hoặc giá trị tốt hơn. | Ghi backlog cải tiến và xác định chỉ số giá trị; kiểm thử thay đổi khi triển khai. |
| Rủi ro tiềm ẩn | Chưa tái hiện được lỗi nhưng có điều kiện dễ gây hậu quả hoặc bằng chứng đáng lo ngại. | Điều tra, thử nghiệm bổ sung, bổ sung giám sát hoặc kiểm soát phù hợp. |
| Vấn đề môi trường hoặc dữ liệu | Kết quả bị ảnh hưởng bởi cấu hình, tài khoản, dữ liệu hoặc dịch vụ kiểm thử. | Khắc phục môi trường, tái hiện trong điều kiện hợp lệ và đánh giá lại. |
| Hành vi mong đợi | Kết quả khác kỳ vọng chủ quan của người kiểm thử nhưng phù hợp với quy tắc đã thống nhất. | Ghi nhận cách giải thích hoặc cải thiện tài liệu nếu người dùng dễ hiểu nhầm. |

Một vấn đề có thể thay đổi phân loại khi có thêm bằng chứng. Ví dụ, ban đầu người kiểm thử cho rằng một trạng thái đơn hàng là lỗi; sau khi trao đổi, nhóm phát hiện yêu cầu chưa định nghĩa trạng thái đó. Cần làm rõ quy tắc trước khi viết test để tránh biến hành vi chưa được quyết định thành một cam kết giả.

## 3. Ghi nhận phát hiện đủ để tái hiện

Một phát hiện khó tái hiện thường khó điều tra và khó chuyển thành hồi quy. Ghi nhận tốt cần cho người khác biết điều kiện nào tạo ra hành vi, hành vi nào đã quan sát và hành vi nào cần xảy ra.

Thông tin tối thiểu nên có:

- **Đối tượng:** chức năng, thành phần, API hoặc luồng nghiệp vụ liên quan.
- **Phiên bản:** build, commit hoặc phiên bản sản phẩm.
- **Môi trường:** hệ điều hành, trình duyệt, thiết bị, cấu hình, dịch vụ phụ thuộc.
- **Điều kiện ban đầu:** vai trò, quyền, trạng thái dữ liệu, feature flag và trạng thái phiên.
- **Dữ liệu:** đầu vào, giá trị biên, mã tham chiếu và cách tạo dữ liệu.
- **Các bước tái hiện:** thao tác ngắn, rõ, có thể lặp lại.
- **Kết quả mong đợi:** căn cứ từ yêu cầu, quy tắc nghiệp vụ hoặc hợp đồng.
- **Kết quả thực tế:** điều gì đã xảy ra, tần suất và điều kiện thất bại.
- **Bằng chứng:** log, ảnh, video, request/response đã loại bỏ bí mật, mã giao dịch hoặc dấu thời gian.
- **Tác động:** người dùng, dữ liệu, nghiệp vụ và mức độ nghiêm trọng.

Có thể dùng mẫu sau:

~~~text
Mã phát hiện:
Chức năng/luồng:
Phiên bản và môi trường:
Vai trò/quyền:
Điều kiện ban đầu:
Dữ liệu:
Các bước tái hiện:
Kết quả mong đợi và căn cứ:
Kết quả thực tế:
Tần suất tái hiện:
Bằng chứng:
Tác động và mức ưu tiên:
Giả thuyết nguyên nhân:
~~~

Không ghi mật khẩu, token, khóa bí mật hoặc dữ liệu cá nhân không cần thiết vào báo cáo. Dùng dữ liệu tổng hợp hoặc mã tham chiếu an toàn để người khác có thể tái hiện.

## 4. Xác nhận lỗi và điều tra nguyên nhân

Trước khi viết kiểm tra hồi quy, nhóm cần hiểu lỗi xảy ra ở đâu và vì sao. Nếu chỉ kiểm tra đúng chuỗi thao tác dẫn đến lỗi nhưng không hiểu điều kiện kích hoạt, bài kiểm tra có thể bảo vệ sai tầng hoặc bỏ qua những biến thể quan trọng.

### 4.1. Tái hiện có kiểm soát

- Dùng đúng phiên bản và điều kiện gần với lúc phát hiện.
- Thử lặp lại để xác định lỗi luôn xảy ra hay chỉ xuất hiện không ổn định.
- Thay đổi từng yếu tố để tìm điều kiện cần thiết.
- Thử dữ liệu đại diện, giá trị biên và trạng thái liên quan.
- Xác nhận lỗi còn xảy ra trên build chưa sửa.
- Ghi nhận kết quả khi loại bỏ hoặc thay đổi một điều kiện.

Nếu lỗi không thể tái hiện, không nên tạo một test tự động dựa trên giả thuyết chưa được xác nhận. Có thể tiếp tục thu thập log, tăng quan sát, kiểm tra dữ liệu hoặc giữ một hoạt động kiểm tra có mục tiêu cho đến khi có đủ bằng chứng.

### 4.2. Tìm nguyên nhân thay vì chỉ ghi biểu hiện

Ví dụ, người kiểm thử phát hiện đơn hàng bị tạo hai lần khi nhấn nút thanh toán nhiều lần trong lúc mạng chậm. Biểu hiện là hai đơn hàng; nguyên nhân có thể nằm ở:

- Giao diện không khóa thao tác khi gửi yêu cầu.
- API không xử lý idempotency key.
- Backend xử lý đồng thời hai request mà không có ràng buộc chống trùng.
- Timeout khiến client gửi lại yêu cầu dù giao dịch đầu đã được xử lý.
- Cơ chế retry hoặc hàng đợi tạo thông điệp lặp.

Mỗi nguyên nhân dẫn đến phạm vi kiểm tra khác nhau. Nếu nguyên nhân nằm ở backend, chỉ thêm E2E kiểm tra nút bấm có thể không đủ để bảo vệ tính duy nhất của giao dịch. Cần kiểm tra ở tầng dịch vụ hoặc tích hợp nơi có thể xác minh trạng thái lưu trữ và xử lý đồng thời.

### 4.3. Phân biệt retest và regression test

- **Kiểm thử lại (retesting):** chạy lại trường hợp đã thất bại để xác nhận lỗi cụ thể đã được khắc phục.
- **Kiểm thử hồi quy (regression testing):** kiểm tra rằng thay đổi không làm hỏng hành vi đã hoạt động trước đó, bao gồm hành vi liên quan và các luồng có nguy cơ bị ảnh hưởng.

Một trường hợp có thể vừa là retest vừa được giữ lại làm regression test lâu dài. Tuy nhiên, mục tiêu khác nhau: retest xác nhận bản sửa hiện tại; regression bảo vệ sản phẩm khỏi việc lỗi tái diễn trong các thay đổi tương lai.

## 5. Chọn tầng hồi quy phù hợp

Một nguyên tắc hữu ích là đặt kiểm tra ở tầng thấp nhất có thể tái hiện nguyên nhân và cung cấp bằng chứng đáng tin cậy. Không phải lúc nào cũng cần tự động hóa toàn bộ hành trình người dùng nơi lỗi được phát hiện.

| Nơi phát hiện hoặc loại nguyên nhân | Tầng hồi quy thường phù hợp | Ví dụ |
|---|---|---|
| Quy tắc tính toán hoặc điều kiện logic | Unit test | Làm tròn thuế sai ở giá trị biên. |
| Trạng thái và hành vi của một thành phần | Component test | Nút gửi không chuyển sang trạng thái chờ khi request đang chạy. |
| Hợp đồng request/response hoặc mã lỗi | API/contract test | API đổi trường status khiến consumer xử lý sai. |
| Truy vấn, transaction hoặc migration | Integration test với cơ sở dữ liệu thật hoặc tương đương | Giao dịch rollback không đầy đủ khi lưu đơn hàng thất bại. |
| Tương tác giữa dịch vụ | Contract/integration test | Dịch vụ thanh toán và đơn hàng không thống nhất trạng thái giao dịch. |
| Luồng người dùng xuyên nhiều thành phần | E2E test | Người dùng hoàn tất thanh toán nhưng không thấy xác nhận. |
| Hiển thị, khả năng truy cập hoặc cảm nhận sử dụng | Kiểm tra giao diện tự động kết hợp kiểm tra thủ công phù hợp | Nội dung bị cắt trên màn hình nhỏ hoặc thao tác bàn phím không hoạt động. |
| Điều kiện môi trường hoặc vận hành | Kiểm tra cấu hình, smoke test, monitoring hoặc diễn tập | Cảnh báo không được kích hoạt khi dịch vụ phụ thuộc ngừng phản hồi. |

Nếu lỗi chỉ xuất hiện khi nhiều thành phần phối hợp, cần kiểm tra tại ranh giới tương tác. Nếu lỗi nằm trong một hàm thuần, unit test thường nhanh và dễ chẩn đoán hơn. Nếu lỗi là vấn đề thị giác hoặc trải nghiệm, một assertion kỹ thuật đơn giản có thể không đủ để bảo vệ chất lượng.

### 5.1. Khi nào nên giữ E2E?

Giữ E2E khi chính hành trình xuyên hệ thống là điều cần bảo vệ, ví dụ:

- Luồng đăng nhập và xác thực đa yếu tố.
- Tạo và thanh toán đơn hàng.
- Phê duyệt yêu cầu qua nhiều vai trò.
- Luồng nhập dữ liệu và xác nhận kết quả trên giao diện.
- Một lỗi tích hợp trước đây chỉ có thể phát hiện đáng tin cậy qua hành trình đầy đủ.

Nếu nguyên nhân có thể được kiểm tra ổn định ở unit hoặc API test, hãy bổ sung kiểm tra ở tầng đó. Có thể giữ một E2E đại diện cho hành trình quan trọng thay vì nhân bản mọi biến thể ở tầng giao diện.

## 6. Chuyển phát hiện thành kiểm tra hồi quy

Quy trình chuyển đổi có thể gồm các bước sau.

### Bước 1: Chọn phát hiện đáng giữ lại

Đánh giá mức độ nghiêm trọng, khả năng tái diễn, phạm vi ảnh hưởng và giá trị phòng ngừa. Lỗi bảo mật, mất dữ liệu, sai giao dịch, phân quyền sai hoặc lỗi ở luồng cốt lõi thường cần được bảo vệ lâu dài. Một phát hiện nhỏ, đơn lẻ hoặc phụ thuộc môi trường tạm thời có thể cần cách xử lý khác.

### Bước 2: Xác định khẳng định cần bảo vệ

Viết thành một câu có thể đánh giá, ví dụ:

- Cùng một yêu cầu thanh toán được gửi lại với cùng idempotency key không tạo giao dịch trùng.
- Người dùng không có quyền không thể xem hồ sơ thuộc tenant khác.
- Khi giao dịch lưu thất bại, dữ liệu liên quan được rollback nhất quán.
- Tổng tiền đơn hàng luôn tuân thủ quy tắc làm tròn đã phê duyệt.

Khẳng định nên mô tả hành vi quan sát được, không mô tả tên hàm hoặc thứ tự gọi nội bộ trừ khi đó là hợp đồng cần bảo vệ.

### Bước 3: Xác định điều kiện tối thiểu để tái hiện

Rút gọn các bước khám phá thành dữ liệu và trạng thái cần thiết. Loại bỏ thao tác không liên quan. Nếu lỗi cần một chuỗi sự kiện dài, giữ lại những bước tạo ra trạng thái kích hoạt và ghi rõ lý do.

### Bước 4: Chọn tầng và loại kiểm tra

Chọn unit, component, API, contract, integration, E2E hoặc thủ công theo nơi có thể xác minh khẳng định. Xem xét độ ổn định, thời gian chạy, khả năng chẩn đoán và môi trường cần thiết.

### Bước 5: Tạo kiểm tra thất bại trước khi sửa nếu có thể

Khi điều kiện cho phép, thêm kiểm tra trên phiên bản chưa sửa và xác nhận nó thất bại vì đúng lỗi cần bảo vệ. Sau đó chạy trên bản sửa và xác nhận đạt. Cách làm này giúp chứng minh test thực sự phát hiện lỗi, không chỉ chạy qua tình cờ.

Với lỗi không thể tái hiện ổn định, lỗi chỉ xuất hiện trên môi trường đặc biệt hoặc phát hiện bảo mật cần kiểm tra chuyên môn, không nên cố ép tạo một test tự động không đáng tin cậy. Có thể dùng kiểm tra thủ công có hướng dẫn, kiểm tra cấu hình, giám sát hoặc diễn tập.

### Bước 6: Kiểm tra tác động hồi quy

Chạy các kiểm tra liên quan đến luồng lân cận, dữ liệu dùng chung và thành phần phụ thuộc. Nếu sửa một quy tắc tính toán, cần kiểm tra các loại giao dịch khác; nếu sửa quyền truy cập, cần kiểm tra cả trường hợp được phép và bị từ chối.

### Bước 7: Gắn vào đúng bộ và lịch chạy

Đặt test ở pipeline phù hợp: pull request, sau hợp nhất, trước phát hành, theo lịch hoặc sau triển khai. Test nhanh và ổn định nên chạy thường xuyên; kiểm tra tốn môi trường hoặc cần dữ liệu đặc biệt có thể chạy theo mốc nhưng phải có lý do và điều kiện rõ.

### Bước 8: Lưu liên kết và bằng chứng

Liên kết test với mã phát hiện, yêu cầu, thay đổi sửa lỗi và tầng kiểm thử. Lưu cách tái hiện, dữ liệu, phiên bản, kết quả và người sở hữu để có thể xem lại sau này.

## 7. Viết kiểm tra hồi quy bền vững

Một kiểm tra hồi quy tốt phải phát hiện lỗi tái diễn mà không thất bại vì những thay đổi không liên quan.

### 7.1. Kiểm tra hành vi có ý nghĩa

Assertion cần xác minh kết quả quan sát được hoặc bất biến quan trọng. Tránh kiểm tra quá nhiều chi tiết triển khai như phương thức private được gọi bao nhiêu lần, thứ tự các lời gọi nội bộ hoặc cấu trúc dữ liệu tạm thời không thuộc hợp đồng.

Ví dụ, với lỗi tính phí, nên kiểm tra tổng tiền cuối cùng theo quy tắc đã thống nhất thay vì chỉ xác minh một hàm nội bộ được gọi. Với lỗi phân quyền, kiểm tra người dùng trái quyền nhận kết quả bị từ chối và không đọc được dữ liệu, không chỉ kiểm tra một nhánh code đã chạy.

### 7.2. Dùng dữ liệu tối thiểu nhưng đại diện

Chọn dữ liệu đủ kích hoạt điều kiện lỗi và thể hiện ranh giới quan trọng. Dữ liệu quá lớn hoặc chứa nhiều yếu tố không liên quan khiến test khó hiểu và khó bảo trì.

Dùng builder hoặc fixture khi cần tạo đối tượng phức tạp. Đặt tên dữ liệu theo mục đích, chẳng hạn accountWithoutPermission hoặc orderAtTaxThreshold, để người đọc hiểu điều kiện đang được bảo vệ.

### 7.3. Tránh phụ thuộc thứ tự và trạng thái dùng chung

Mỗi test nên tự chuẩn bị trạng thái cần thiết và dọn dẹp sau khi chạy. Không nên dựa vào test khác đã tạo dữ liệu hoặc thay đổi cấu hình. Nếu kiểm tra dùng chung tài nguyên, cần bảo đảm chạy song song không gây xung đột.

### 7.4. Kiểm soát thời gian và tính bất đồng bộ

Với lỗi liên quan đến hết hạn, retry hoặc tác vụ nền, dùng clock có thể điều khiển hoặc cơ chế chờ theo điều kiện khi phù hợp. Tránh sleep cố định và phụ thuộc vào thời gian mạng ngẫu nhiên. Nếu cần kiểm tra hành vi concurrency thật, cần môi trường và đồng bộ phù hợp thay vì chỉ mô phỏng tất cả bằng mock.

### 7.5. Xác minh test có thể phát hiện lỗi

Một test pass trên bản sửa chưa đủ chứng minh nó hữu ích. Nếu có thể, chạy test trên bản chưa sửa hoặc tạm thời đưa lại điều kiện lỗi để xác nhận test thất bại đúng lý do. Đây là kiểm tra sức mạnh phát hiện của test.

## 8. Ví dụ: chuyển lỗi thanh toán trùng thành hồi quy

Một người kiểm thử khám phá thấy rằng khi mạng chậm, nhấn nút Thanh toán hai lần có thể tạo hai giao dịch. Nhóm ghi nhận:

- Người dùng đã xác nhận đơn hàng.
- Request thanh toán đầu tiên được gửi nhưng phản hồi chậm.
- Người dùng nhấn lại nút.
- Hai giao dịch xuất hiện cho cùng một đơn hàng.
- Lỗi có thể gây thu tiền hai lần và cần đối soát thủ công.

Sau điều tra, nhóm xác định backend chưa xử lý idempotency key đúng cách. Hướng chuyển thành hồi quy:

1. **Khẳng định:** cùng một khóa idempotency và cùng một yêu cầu nghiệp vụ không tạo nhiều hơn một giao dịch.
2. **Tầng unit:** kiểm tra logic xử lý trạng thái và quy tắc nhận diện yêu cầu trùng nếu phần logic có thể cô lập.
3. **Tầng integration:** gửi đồng thời hoặc gửi lặp request đến dịch vụ với cùng khóa, xác minh chỉ có một giao dịch được ghi nhận.
4. **Tầng E2E:** giữ một hành trình đại diện xác nhận người dùng gửi lại khi chờ phản hồi không tạo thanh toán trùng.
5. **Bằng chứng:** kiểm tra số giao dịch, trạng thái đơn hàng và phản hồi trả về cho các request lặp.
6. **Pipeline:** chạy kiểm tra logic nhanh trên pull request và kiểm tra đồng thời ở integration pipeline phù hợp.

Không nên chỉ kiểm tra nút thanh toán bị vô hiệu hóa sau lần nhấn đầu tiên. Người dùng có thể gửi lại từ thiết bị khác, client có thể retry hoặc request có thể được phát lại. Bất biến chống giao dịch trùng cần được bảo vệ ở phía dịch vụ.

## 9. Ví dụ: chuyển phát hiện phân quyền thành hồi quy

Trong một phiên khám phá, người kiểm thử đăng nhập bằng tài khoản thuộc tenant A, sau đó thay mã hồ sơ trong URL và xem được dữ liệu của tenant B. Đây là phát hiện bảo mật nghiêm trọng.

Cách chuyển thành hồi quy:

- Xác định khẳng định: người dùng chỉ đọc hoặc thay đổi dữ liệu trong phạm vi tenant được cấp quyền.
- Tạo dữ liệu cho hai tenant độc lập.
- Kiểm tra ở service/API rằng người dùng tenant A không thể truy cập tài nguyên tenant B.
- Kiểm tra cả các hành động đọc, cập nhật, xóa và xuất dữ liệu nếu các hành động đó có trong phạm vi.
- Giữ một E2E đại diện để xác nhận giao diện không hiển thị dữ liệu ngoài quyền.
- Không chỉ kiểm tra mã HTTP; cần xác minh dữ liệu không bị trả về hoặc thay đổi.
- Chạy kiểm tra trong các pipeline bắt buộc và theo dõi các thay đổi ở middleware, truy vấn hoặc chính sách phân quyền.

Với lỗi bảo mật, test hồi quy là một lớp bảo vệ. Nhóm vẫn cần review bảo mật, kiểm thử quyền theo ma trận và kiểm tra các đường truy cập khác có thể dẫn đến cùng loại rủi ro.

## 10. Khi nào nên giữ kiểm tra thủ công?

Không phải mọi phát hiện đều chuyển tốt thành kiểm tra tự động. Có thể giữ hoạt động thủ công hoặc khám phá có mục tiêu khi:

- Kết quả cần đánh giá bằng mắt hoặc nhận định của con người, ví dụ bố cục, ngữ nghĩa nội dung hoặc mức dễ hiểu.
- Hành vi còn thay đổi nhanh và tiêu chí chưa ổn định.
- Tình huống hiếm, khó tạo môi trường tự động nhưng hậu quả đáng chú ý.
- Cần chuyên gia đánh giá bảo mật, khả năng tiếp cận hoặc nghiệp vụ.
- Tự động hóa có chi phí cao hơn giá trị phòng ngừa.
- Bằng chứng cần thu thập qua quan sát người dùng hoặc thử nghiệm trong bối cảnh thật.

Giữ thủ công không có nghĩa là kiểm tra tùy hứng. Hãy ghi mục tiêu, phạm vi, điều kiện, người thực hiện, tiêu chí, bằng chứng và tần suất. Có thể tạo checklist hoặc exploratory charter để hoạt động được lặp lại và đánh giá.

Một phát hiện về hiển thị có thể cần ảnh chụp chuẩn và kiểm tra thủ công trên thiết bị đại diện. Một lỗi API xác định được có thể được tự động hóa. Một rủi ro vận hành có thể cần diễn tập định kỳ. Hãy chọn cách bảo vệ phù hợp với bản chất của rủi ro.

## 11. Ưu tiên phát hiện nào cần hồi quy trước?

Khi có nhiều phát hiện, không thể tự động hóa tất cả ngay lập tức. Có thể xếp ưu tiên dựa trên:

| Yếu tố | Câu hỏi |
|---|---|
| Mức độ nghiêm trọng | Lỗi có thể gây mất dữ liệu, lộ thông tin, giao dịch sai hoặc gián đoạn dịch vụ không? |
| Tần suất và khả năng xảy ra | Điều kiện lỗi có thường gặp hoặc dễ xuất hiện lại không? |
| Phạm vi ảnh hưởng | Bao nhiêu người dùng, tenant, dịch vụ hoặc luồng nghiệp vụ bị ảnh hưởng? |
| Khả năng tái diễn | Nguyên nhân có thể bị kích hoạt bởi các thay đổi thường xuyên không? |
| Khả năng phát hiện | Có dễ nhận ra trước khi người dùng bị ảnh hưởng không? |
| Chi phí kiểm tra | Có thể tạo kiểm tra ổn định ở tầng phù hợp với chi phí hợp lý không? |
| Giá trị phòng ngừa | Test có bảo vệ một bất biến hoặc rủi ro quan trọng cho nhiều luồng không? |

Ưu tiên cao thường gồm lỗi nghiêm trọng, lỗi tái diễn, lỗi ở thành phần dùng chung, lỗi có nguyên nhân rõ và có thể tự động hóa ổn định. Tuy nhiên, một phát hiện ít gặp nhưng có hậu quả đặc biệt lớn vẫn có thể cần kiểm soát thủ công hoặc giám sát chuyên biệt dù chưa thể tạo regression test tự động.

## 12. Quản lý bộ kiểm thử hồi quy theo thời gian

Bộ hồi quy cần được xem như một tài sản sống. Khi sản phẩm thay đổi, một test có thể lỗi thời, trùng lặp hoặc không còn bảo vệ rủi ro hiện tại.

### 12.1. Truy vết nguồn gốc

Mỗi test quan trọng nên liên kết với một hoặc nhiều thông tin:

- Mã lỗi hoặc phát hiện ban đầu.
- Yêu cầu hoặc bất biến nghiệp vụ.
- Thành phần và phạm vi bị ảnh hưởng.
- Thay đổi sửa lỗi hoặc pull request.
- Tầng kiểm thử và vị trí trong pipeline.
- Người hoặc nhóm sở hữu.
- Dữ liệu, môi trường và điều kiện chạy.
- Lý do giữ lại test và rủi ro nó bảo vệ.

Truy vết giúp người bảo trì hiểu vì sao test tồn tại. Nếu không biết mục đích, nhóm có thể xóa nhầm một kiểm tra bảo vệ lỗi nghiêm trọng hoặc giữ mãi một test không còn giá trị.

### 12.2. Theo dõi test không ổn định

Flaky test có thể đạt hoặc thất bại không nhất quán dù mã nguồn không đổi. Cần ghi nhận tỷ lệ chạy lại, môi trường, thời gian và nguyên nhân. Không nên âm thầm bỏ qua kết quả thất bại hoặc tăng retry vô hạn để làm pipeline xanh.

Nếu cần cách ly tạm thời, phải có người phụ trách, lý do, phạm vi rủi ro, biện pháp kiểm soát thay thế và thời hạn khắc phục. Với kiểm tra bảo vệ rủi ro cao, cần cân nhắc biện pháp thủ công hoặc giám sát trong thời gian test được sửa.

### 12.3. Loại bỏ hoặc thay thế test

Có thể rà soát một test khi:

- Chức năng đã bị loại bỏ hoặc hợp đồng thay đổi.
- Test trùng lặp với kiểm tra khác có bằng chứng tương đương.
- Test kiểm tra chi tiết triển khai không còn ý nghĩa.
- Test luôn thất bại do môi trường và không phát hiện lỗi sản phẩm.
- Một kiểm tra ở tầng thấp hơn đã bảo vệ nguyên nhân ổn định hơn, trong khi hành trình E2E không còn cần thiết.

Trước khi xóa, kiểm tra rủi ro mà test đang bảo vệ và xác nhận có bằng chứng thay thế nếu cần. Không xóa test chỉ để giảm thời gian pipeline mà chưa đánh giá hậu quả.

## 13. Đo lường giá trị của hồi quy

Một số chỉ số có thể giúp đánh giá việc chuyển phát hiện thành hồi quy:

- **Tỷ lệ lỗi tái diễn:** số lỗi lặp lại cùng nguyên nhân hoặc cùng hành vi.
- **Lỗi lọt qua:** lỗi được phát hiện sau khi thay đổi đã đến môi trường cao hơn hoặc người dùng.
- **Thời gian phát hiện:** thời gian từ khi lỗi xuất hiện đến khi bộ kiểm thử phát hiện.
- **Thời gian chẩn đoán:** thời gian xác định nguyên nhân sau khi kiểm tra thất bại.
- **Tỷ lệ test không ổn định:** số lần kết quả thay đổi không do thay đổi sản phẩm.
- **Chi phí bảo trì:** thời gian sửa test, fixture, dữ liệu và môi trường.
- **Độ bao phủ rủi ro:** các bất biến và lỗi quan trọng đã có kiểm tra bảo vệ.

Không nên chỉ đếm số test được thêm sau mỗi phiên khám phá. Một test tốt có thể bảo vệ một bất biến quan trọng qua nhiều lần thay đổi; nhiều test trùng lặp có thể tăng chi phí mà không tăng khả năng phát hiện.

Hãy xem xét cả chất lượng phát hiện, vị trí test trong pipeline và chi phí vận hành. Nếu lỗi liên tục chỉ được phát hiện ở E2E hoặc production, có thể cần thêm kiểm tra ở tầng thấp hơn hoặc cải thiện khả năng quan sát.

## 14. Những sai lầm thường gặp

- **Tự động hóa mọi thao tác khám phá:** biến các bước điều tra tạm thời thành test dài và khó bảo trì.
- **Chuyển phát hiện thành test trước khi làm rõ yêu cầu:** bảo vệ một hành vi chưa được thống nhất.
- **Chỉ kiểm tra đúng đường đi đã phát hiện:** bỏ qua các biến thể cùng nguyên nhân hoặc các luồng lân cận.
- **Đặt test sai tầng:** kiểm tra giao diện cho một quy tắc logic đơn giản hoặc dùng mock để khẳng định tích hợp thật.
- **Không xác nhận test thất bại trên phiên bản lỗi:** test có thể không thực sự phát hiện vấn đề.
- **Assertion quá yếu:** test chạy qua nhưng không xác minh bất biến quan trọng.
- **Assertion quá chặt vào chi tiết nội bộ:** test hỏng khi tái cấu trúc dù hành vi vẫn đúng.
- **Dữ liệu và trạng thái dùng chung:** kết quả phụ thuộc thứ tự chạy hoặc môi trường.
- **Không lưu liên kết phát hiện và test:** người khác không biết lý do kiểm tra tồn tại.
- **Giữ test lỗi thời vô thời hạn:** bộ hồi quy chậm, nhiều nhiễu và giảm niềm tin.
- **Bỏ qua kiểm tra thủ công có giá trị:** một số rủi ro cần quan sát, phán đoán hoặc đánh giá trong bối cảnh thật.

## 15. Checklist chuyển phát hiện thành hồi quy

- [ ] Phát hiện đã được phân loại là lỗi, rủi ro, thiếu yêu cầu hay cải tiến.
- [ ] Có căn cứ xác định hành vi mong đợi.
- [ ] Phiên bản, môi trường, vai trò, dữ liệu và bước tái hiện được ghi nhận.
- [ ] Lỗi được tái hiện hoặc mức độ bất định được ghi rõ.
- [ ] Nguyên nhân hoặc điều kiện kích hoạt đã được điều tra đủ để chọn tầng kiểm tra.
- [ ] Khẳng định cần bảo vệ được viết rõ và có thể đánh giá.
- [ ] Tầng kiểm thử phù hợp với nguyên nhân và ranh giới bị ảnh hưởng.
- [ ] Kiểm tra có thể phát hiện lỗi trên phiên bản chưa sửa khi điều kiện cho phép.
- [ ] Có kiểm thử hồi quy cho luồng lân cận và tác động liên quan.
- [ ] Dữ liệu, thời gian, môi trường và trạng thái được kiểm soát.
- [ ] Test có tên, assertion và thông điệp lỗi dễ hiểu.
- [ ] Test được đặt đúng pipeline và có người sở hữu.
- [ ] Phát hiện được liên kết với test, thay đổi và bằng chứng.
- [ ] Có kế hoạch bảo trì, xử lý flaky test và rà soát giá trị theo thời gian.

## Kết luận

Một phát hiện từ kiểm thử thủ công hoặc khám phá chỉ nên trở thành hồi quy khi nhóm hiểu hành vi cần bảo vệ, có căn cứ về kết quả mong đợi và chọn được cách kiểm tra đáng tin cậy. Hãy ghi nhận đủ điều kiện tái hiện, phân loại phát hiện, điều tra nguyên nhân và đặt kiểm tra ở tầng phù hợp. Tự động hóa những gì có thể kiểm tra ổn định; giữ hoạt động thủ công hoặc giám sát cho những rủi ro cần phán đoán và bối cảnh thực tế. Bộ hồi quy có giá trị khi mỗi kiểm tra bảo vệ một hành vi quan trọng, có thể chẩn đoán, tái lập và được duy trì theo vòng đời sản phẩm.
