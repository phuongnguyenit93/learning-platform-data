# Privacy impact assessment — Chuyển tác động quyền riêng tư thành yêu cầu có thể kiểm chứng

## 1. Vì sao hệ thống an toàn vẫn có thể gây tác động quyền riêng tư?

Một ứng dụng chấm công mã hóa database, dùng TLS và phân quyền truy cập đúng thiết kế. Tuy nhiên, ứng dụng thu vị trí của nhân viên liên tục, kể cả ngoài giờ làm việc; quản lý có thể dùng lịch sử đó để suy đoán sinh hoạt cá nhân.

Không nhất thiết có lỗ hổng bảo mật hay tài khoản bị chiếm quyền trong tình huống này. Tác động đến quyền riêng tư có thể xuất phát từ chính chức năng được thiết kế và quyền truy cập được cấp hợp lệ.

**Privacy impact assessment**, thường viết tắt là PIA, là hoạt động đánh giá có cấu trúc nhằm hiểu việc xử lý dữ liệu ảnh hưởng đến con người như thế nào, xác định phương án giảm tác động và đưa ra quyết định có căn cứ trước hoặc trong vòng đời triển khai.

Trong module về yêu cầu bảo mật, kết quả cần đi xa hơn một bản nhận xét “có rủi ro”. PIA phải giúp tạo ra chuỗi truy vết:

```text
Mục tiêu nghiệp vụ
    -> hoạt động xử lý dữ liệu
    -> tác động có thể xảy ra với con người
    -> quyết định thiết kế và kiểm soát
    -> yêu cầu đo được
    -> bằng chứng kiểm thử
    -> rủi ro còn lại và quyết định triển khai
```

Mục tiêu học tập của bài:

- Xác định phạm vi PIA từ hoạt động xử lý thay vì chỉ từ danh sách database.
- Phân biệt rủi ro quyền riêng tư với rủi ro bảo mật thông tin.
- Phân tích tính cần thiết, mức độ tương xứng và các phương án ít tác động hơn.
- Viết kịch bản tác động có người chịu ảnh hưởng, nguyên nhân và hậu quả cụ thể.
- Chuyển biện pháp dự kiến thành yêu cầu có chủ sở hữu và oracle kiểm thử.
- Phân biệt rủi ro dự kiến giảm với rủi ro đã được giảm bằng bằng chứng.
- Duy trì đánh giá khi mục đích, dữ liệu, nhà cung cấp hoặc kiến trúc thay đổi.

Bài học trình bày phương pháp đặc tả sản phẩm và kỹ thuật. Tên tài liệu, điều kiện phải thực hiện đánh giá, quy trình tham vấn và thẩm quyền quyết định có thể khác nhau giữa tổ chức hoặc bối cảnh áp dụng. Những yêu cầu phụ thuộc chính sách và khu vực phải được xác nhận thành đầu vào dự án; không suy từ việc có một tài liệu mang tên PIA rằng hệ thống đã hoàn thành mọi nghĩa vụ liên quan.

## 2. Phân biệt PIA với những hoạt động gần nhau

| Hoạt động | Câu hỏi trọng tâm | Đầu ra thường cần |
|---|---|---|
| Threat modeling | Tác nhân hoặc điều kiện nào làm hệ thống vi phạm mục tiêu an toàn? | Kịch bản đe dọa, ranh giới tin cậy và kiểm soát |
| Đánh giá bảo mật | Kiểm soát bảo mật có được thiết kế và triển khai đúng không? | Phát hiện, bằng chứng và yêu cầu khắc phục |
| PIA | Hoạt động xử lý có thể ảnh hưởng đến con người như thế nào và nên thay đổi gì? | Phân tích tác động, phương án, yêu cầu và quyết định |
| Rà soát chính sách áp dụng | Những điều kiện hoặc giới hạn nào chi phối hoạt động xử lý? | Yêu cầu và quyết định chính sách đã được xác nhận |
| Kiểm thử chức năng | Hệ thống có thực hiện đúng hợp đồng đã đặc tả không? | Kết quả theo oracle và phạm vi bao phủ |
| Thông báo quyền riêng tư | Người liên quan cần nhận thông tin gì, ở thời điểm nào? | Nội dung, điểm cung cấp và bằng chứng phù hợp |

Các hoạt động này dùng chung thông tin nhưng không thay thế nhau.

Mã hóa làm giảm một số nguy cơ lộ dữ liệu. Nó không tự chứng minh việc thu thập liên tục là cần thiết. Một thông báo đầy đủ có thể cải thiện minh bạch, nhưng không tự làm cho mọi mục đích xử lý trở nên phù hợp. Một người đã bấm đồng ý cũng không xóa bỏ yêu cầu về phân quyền, độ chính xác hoặc giới hạn lưu giữ.

Trong một số tổ chức, thuật ngữ DPIA được dùng cho một quy trình có điều kiện và yêu cầu cụ thể. Khi gặp tên này, cần kiểm tra định nghĩa áp dụng của dự án thay vì mặc định PIA và DPIA luôn đồng nhất hoặc luôn khác nhau theo một công thức chung.

## 3. Sàng lọc thời điểm cần đánh giá và mức độ đào sâu

PIA nên được bắt đầu khi còn có thể thay đổi phương án, không đợi đến lúc mọi bảng dữ liệu và hợp đồng tích hợp đã cố định.

Một bước sàng lọc có thể hỏi:

- Có mục đích mới hoặc cách sử dụng mới đối với dữ liệu đã có không?
- Có theo dõi hành vi, vị trí hoặc liên kết hoạt động qua nhiều bối cảnh không?
- Có dữ liệu có khả năng gây tổn hại lớn nếu bị dùng sai hoặc suy luận thêm không?
- Có nhóm người khó từ chối, khó hiểu thông tin hoặc khó phản đối quyết định không?
- Có đánh giá, xếp hạng hoặc quyết định làm thay đổi cơ hội của một người không?
- Có chia sẻ cho bên mới, mở rộng phạm vi truy cập hoặc đổi nơi xử lý không?
- Có tăng quy mô, thời gian lưu hoặc khả năng liên kết dữ liệu không?
- Có công nghệ mới đối với tổ chức hoặc thiếu bằng chứng về hành vi của một thành phần không?
- Có khiếu nại, sự cố hoặc phát hiện cho thấy giả định cũ không còn đúng không?

Đây là các tín hiệu phân tích, không phải một danh sách tự động quyết định nghĩa vụ pháp lý.

Đầu ra sàng lọc cần có lý do, phạm vi, người chịu trách nhiệm và những điều còn chưa biết. Không chỉ lưu một checkbox “không cần PIA”.

Quy mô đánh giá phải phù hợp tác động. Thay màu nút không nhất thiết cần cùng quy trình với thêm theo dõi vị trí. Tuy nhiên, một thay đổi giao diện nhỏ có thể có tác động lớn nếu nó làm người dùng khó từ chối một mục đích mới.

## 4. Chốt phạm vi, mục tiêu và người chịu ảnh hưởng

### 4.1. Mục tiêu nghiệp vụ phải đủ cụ thể để kiểm tra tính cần thiết

Mục tiêu “nâng cao hiệu quả” quá rộng để quyết định có nên thu vị trí chính xác.

Một mục tiêu rõ hơn:

> Xác nhận một nhân viên thực hiện thao tác chấm công cho ca được giao tại điểm làm việc được phép, trong khoảng thời gian của ca.

Mục tiêu này cho phép hỏi liệu có cần lịch sử di chuyển cả ngày hay không. Nếu tổ chức muốn đánh giá năng suất, đó là một mục đích khác cần được mô tả và đánh giá riêng.

Không dùng một tên mục đích chung để gộp chấm công, điều phối, quảng cáo nội bộ và xếp hạng hành vi thành cùng một nhu cầu.

### 4.2. Phạm vi tối thiểu của một bản đánh giá

| Thành phần | Nội dung cần xác định |
|---|---|
| Chức năng | Luồng, API, job và cấu hình nào đang được đánh giá |
| Phiên bản | Build hoặc revision kiến trúc và chính sách tương ứng |
| Nhóm người | Nhân viên, khách hàng, người không có tài khoản hoặc người xuất hiện trong tài liệu |
| Dữ liệu | Dữ liệu cung cấp trực tiếp, quan sát, suy luận và dẫn xuất |
| Bên tham gia | Đội vận hành, đối tác, nhà cung cấp và người được xem kết quả |
| Mục đích | Mỗi hoạt động phục vụ mục tiêu nào |
| Địa điểm và môi trường | Thiết bị, dịch vụ, nơi lưu và nơi xử lý thuộc phạm vi |
| Vòng đời | Thu thập, sử dụng, chia sẻ, lưu, xóa, backup và phục hồi |
| Ngoài phạm vi | Những phần chưa đánh giá và lý do; không che giấu phụ thuộc liên quan |
| Giả định | Điều đang được coi là đúng và nguồn xác nhận |
| Chủ sở hữu | Ai cung cấp thông tin, thực hiện thay đổi và quyết định |

Phạm vi phải bao gồm dữ liệu dẫn xuất. Một cờ “có mặt tại địa điểm” vẫn có thể là dữ liệu liên quan đến cá nhân dù không lưu tọa độ đầy đủ.

### 4.3. Người chịu tác động không chỉ là người dùng tài khoản

Một tài liệu hỗ trợ có thể chứa thông tin của đồng nghiệp hoặc khách hàng. Một ứng dụng vị trí có thể làm lộ nơi ở của người dùng và quan hệ với người khác.

Cần xác định nhóm chịu ảnh hưởng trực tiếp và gián tiếp. Không mặc định người thao tác trên giao diện có thể đại diện cho mọi người xuất hiện trong dữ liệu.

## 5. Vẽ luồng dữ liệu đủ để thấy nơi tạo ra tác động

Một sơ đồ cho case chấm công giả định:

```text
Thiết bị của nhân viên
    | thao tác chấm công, dữ liệu thiết bị, thông tin vị trí theo thiết kế
    v
API chấm công
    |                         |
    v                         v
Database nghiệp vụ       Log / trace / queue
    |
    +--> Màn hình quản lý
    |
    +--> Báo cáo hoặc dịch vụ phân tích
    |
    +--> Backup --> môi trường khôi phục
```

Sơ đồ này mới là điểm bắt đầu. Với từng mũi tên, cần hỏi:

- Field nào thực sự được gửi, không chỉ field được mô tả trong tài liệu?
- Ai có thể đọc hoặc sửa?
- Bên nhận có dùng dữ liệu cho mục đích khác không?
- Có cache, bản sao, file tạm hoặc bảng lịch sử không?
- Dữ liệu có bị đưa vào log khi request lỗi không?
- Job retry có kéo dài thời gian giữ dữ liệu hoặc gửi lại cho bên ngoài không?
- Khi xóa ở hệ thống chính, những bản sao nào còn tồn tại?
- Restore có đưa dữ liệu hết hạn quay lại phục vụ không?

SDK, thư viện quan sát và công cụ hỗ trợ là thành phần của luồng xử lý nếu chúng nhận dữ liệu. Không loại chúng khỏi PIA vì không nằm trong database chính.

Một phép biến đổi như băm ID, thay tên bằng mã hoặc bỏ một số field không tự chứng minh dữ liệu không còn liên quan đến cá nhân. Cần đánh giá khả năng liên kết, dữ liệu phụ trợ và ngữ cảnh của bên có thể truy cập.

## 6. Thu thập bằng chứng và ý kiến mà không tạo thêm rủi ro

Đầu vào có thể đến từ:

- Mô tả nghiệp vụ và kiến trúc.
- Danh mục dữ liệu, cấu hình triển khai và quyền truy cập.
- Quan sát request trên môi trường kiểm soát.
- Chính sách lưu giữ và quy trình phục hồi.
- Điều kiện sử dụng dịch vụ, cấu hình và khả năng của nhà cung cấp.
- Phỏng vấn đội sản phẩm, vận hành, hỗ trợ và người đại diện phù hợp của nhóm chịu tác động.
- Sự cố, phản ánh và bằng chứng kiểm thử liên quan.

Tách rõ **được tuyên bố**, **được cấu hình** và **đã được quan sát**. Một nhà cung cấp nói hỗ trợ tắt lưu payload không chứng minh tenant của dự án đã bật đúng cấu hình.

Việc lấy ý kiến cần phù hợp quan hệ giữa các bên. Trong môi trường lao động, một câu trả lời “không có vấn đề” trước mặt quản lý không tự chứng minh mọi nhân viên có thể bày tỏ lo ngại tự do.

Không cần thu lịch sử vị trí thật của cả tổ chức để chứng minh theo dõi vị trí có rủi ro. Có thể dùng dữ liệu tổng hợp, ví dụ đã giảm nhận diện và các phương pháp tham vấn ít thu thập hơn.

Bản ghi phỏng vấn hoặc phản ánh có thể tự chứa dữ liệu nhạy cảm. Cần giới hạn người đọc, thời gian giữ và mức chi tiết trước khi đưa vào hồ sơ đánh giá.

## 7. Kiểm tra tính cần thiết và mức độ tương xứng

### 7.1. Ba câu hỏi cần trả lời riêng

1. **Mục tiêu có cụ thể và được xác nhận không?** Không đánh giá một hoạt động thu thập chỉ bằng khẩu hiệu chung.
2. **Dữ liệu hoặc cách xử lý này có cần cho mục tiêu đó không?** Cần chỉ ra đóng góp thực tế, không chỉ sự thuận tiện cho đội phát triển.
3. **Có phương án đạt mục tiêu với tác động thấp hơn không?** So sánh cả hiệu quả, rủi ro bảo mật, trải nghiệm và chi phí.

Chi phí triển khai là một yếu tố, nhưng không nên dùng “đã có SDK này” như bằng chứng rằng mọi dữ liệu SDK thu đều cần thiết.

### 7.2. So sánh phương án trước khi thêm kiểm soát

| Phương án giả định | Giá trị đối với chấm công | Tác động cần xem xét | Bằng chứng cần có |
|---|---|---|---|
| Thu vị trí liên tục cả ngày | Có nhiều thông tin hơn mục tiêu hiện tại | Theo dõi ngoài bối cảnh làm việc, suy luận sinh hoạt | Lý do cần thiết và mục đích riêng nếu vẫn đề xuất |
| Thu vị trí tại thao tác chấm công | Gắn với một sự kiện cụ thể | Vẫn có thể lộ điểm hiện diện chính xác | Nhu cầu độ chính xác và kiểm tra không thu nền |
| Xử lý vị trí trên thiết bị, gửi kết quả phù hợp | Giảm dữ liệu vị trí phía server | Kết quả vẫn liên quan cá nhân; client có thể bị sửa | Đánh giá độ tin cậy, giả mạo và dữ liệu thực gửi |
| Mã hoặc thiết bị xác nhận tại địa điểm | Có thể giảm nhu cầu GPS | Có nguy cơ chia sẻ mã, replay hoặc khó tiếp cận | Threat model và kiểm thử hiệu quả chống gian lận |
| Quy trình hỗ trợ thủ công có kiểm soát | Phục vụ tình huống ngoại lệ | Tăng thao tác, có thể phát sinh dữ liệu phụ | Khối lượng, tính công bằng và quyền truy cập |

Phương án ít thu thập hơn không mặc nhiên đáp ứng mọi mục tiêu chống gian lận. Nếu server chỉ tin cờ “đúng địa điểm” do client gửi, cần xử lý rủi ro giả mạo riêng.

Ngược lại, phát hiện một phương án có rủi ro giả mạo không tự chứng minh theo dõi liên tục là phương án duy nhất. Cần tiếp tục so sánh mức xác minh thực sự cần thiết với tác động của các lựa chọn.

### 7.3. Không dùng thông báo để thay thế giảm dữ liệu

Thông báo “chúng tôi thu vị trí cả ngày” giúp mô tả hành vi, nhưng không làm mất câu hỏi về tính cần thiết. Cần xem có thể bỏ thu thập, giảm độ chính xác, giảm tần suất hoặc giới hạn thời gian trước khi chỉ bổ sung nội dung giải thích.

## 8. Viết kịch bản tác động thay vì chỉ liệt kê tên rủi ro

Một kịch bản đủ dùng có thể theo cấu trúc:

> Vì điều kiện hoặc thiết kế X, tác nhân hoặc quy trình Y có thể thực hiện Z đối với dữ liệu D, ảnh hưởng đến nhóm G và gây hậu quả H.

Ví dụ:

> Vì báo cáo chấm công cho phép quản lý xem tọa độ chính xác của toàn bộ nhân viên trong nhiều tháng, người có quyền báo cáo có thể suy luận địa điểm sinh hoạt ngoài nhu cầu xác nhận ca làm việc, gây mất kiểm soát thông tin cá nhân và nguy cơ bị theo dõi đối với nhân viên.

Kịch bản này chỉ ra dữ liệu, quyền, thời gian, người chịu tác động và hậu quả. Nó giúp chọn biện pháp cụ thể hơn câu “có rủi ro quyền riêng tư”.

Một tập kịch bản ban đầu:

| ID | Điều kiện và sự kiện | Người chịu tác động | Hậu quả có thể xảy ra |
|---|---|---|---|
| PR-01 | Thu nền làm hình thành lịch sử vị trí ngoài ca | Nhân viên | Lộ sinh hoạt, bị theo dõi hoặc mất cảm giác tự chủ |
| PR-02 | Quyền báo cáo cho phép suy luận quá mức | Nhân viên | Dữ liệu bị dùng để đánh giá không phù hợp mục đích ban đầu |
| PR-03 | Vị trí hoặc thời gian sai nhưng hệ thống tự coi là vắng mặt | Người chấm công | Mất quyền lợi hoặc phải giải trình một quyết định sai |
| PR-04 | Log lỗi ghi toàn bộ request chứa vị trí | Nhân viên | Phạm vi truy cập thực tế rộng hơn thiết kế nghiệp vụ |
| PR-05 | Dịch vụ phân tích liên kết định danh qua nhiều nguồn | Nhân viên và người liên quan | Tạo hồ sơ ngoài bối cảnh họ biết hoặc dự đoán |
| PR-06 | Restore đưa dữ liệu đã hết hạn quay lại màn hình | Nhân viên | Thời gian tiếp cận dữ liệu vượt chính sách |
| PR-07 | Quy trình ngoại lệ buộc gửi thêm thông tin riêng tư không cần thiết | Người gặp lỗi hoặc thiếu thiết bị | Chịu gánh nặng và mức thu thập lớn hơn nhóm khác |

Không phải kịch bản nào cũng cần kẻ tấn công. Một chính sách quản lý, thuật toán nghiệp vụ hoặc cấu hình mặc định cũng có thể tạo ra tác động.

Cũng cần phân biệt ảnh hưởng đến tổ chức và ảnh hưởng đến con người. Chi phí xử lý khiếu nại là vấn đề của tổ chức; việc người lao động bị đánh giá sai, mất cơ hội hoặc bị lộ vị trí là tác động đối với họ. PIA không nên chỉ chấm điểm theo thiệt hại tài chính của doanh nghiệp.

## 9. Ước lượng rủi ro với giả định và độ bất định

### 9.1. Phân biệt ba trạng thái rủi ro

- **Rủi ro ban đầu:** dựa trên phương án trước các biện pháp bổ sung đang được đề xuất, có nêu những kiểm soát đã tồn tại.
- **Rủi ro còn lại dự kiến:** ước lượng nếu các biện pháp dự kiến được triển khai và hoạt động như giả định.
- **Rủi ro còn lại đã được đánh giá bằng bằng chứng:** dựa trên thiết kế thực tế và kết quả xác minh trong phạm vi đã kiểm tra.

Không ghi biện pháp “sẽ làm” rồi chuyển ngay rủi ro sang trạng thái đã xử lý.

### 9.2. Ví dụ thang điểm nội bộ

Một tổ chức có thể dùng thang thứ bậc 1–4:

| Điểm | Khả năng xảy ra | Mức tác động đối với con người |
|---|---|---|
| 1 | Khó xảy ra trong điều kiện đã xác định, có kiểm soát và bằng chứng hỗ trợ | Bất tiện hạn chế, phạm vi nhỏ, có thể khắc phục nhanh |
| 2 | Có thể xảy ra trong một số tình huống thực tế | Mất kiểm soát hoặc thiệt hại có giới hạn, cần can thiệp để khắc phục |
| 3 | Có đường xảy ra rõ hoặc tần suất tiếp xúc đáng kể | Thiệt hại nghiêm trọng về cơ hội, tài chính, danh dự hoặc quyền tự chủ |
| 4 | Dễ xảy ra hoặc khó kiểm soát trong phương án hiện tại | Hậu quả rất nghiêm trọng, kéo dài, khó đảo ngược hoặc liên quan an toàn cá nhân |

Các mô tả phải được tổ chức hiệu chỉnh theo bối cảnh. Không coi bảng này là một chuẩn bắt buộc.

Có thể dùng R = L × I để ưu tiên nội bộ. Tuy nhiên, đây là phép tính trên thang thứ bậc, không phải xác suất nhân tổn thất định lượng. Điểm giảm từ 16 xuống 4 không chứng minh rủi ro thực tế đã giảm 75%.

Nếu không có đủ thông tin về một nhà cung cấp, không tự đặt L = 1. Ghi nhận chưa biết, giả định đang dùng và bằng chứng cần thu thập.

### 9.3. Tránh để điểm thấp che khuất hậu quả nghiêm trọng

Một kịch bản gây nguy cơ theo dõi có thể có I = 4. Sau giới hạn truy cập, đội đánh giá dự kiến L giảm từ 3 xuống 1, nên R từ 12 xuống 4. Hậu quả vẫn nghiêm trọng nếu xảy ra.

Quy tắc ra quyết định có thể yêu cầu mọi kịch bản I = 4 được rà soát riêng, dù điểm tổng thấp. Các giới hạn bắt buộc theo chính sách cũng không được bỏ qua chỉ vì tích số nằm dưới một ngưỡng.

Đánh giá cần ghi cả số người có thể bị ảnh hưởng, nhóm có khả năng chịu tác động cao hơn, khả năng phát hiện, khả năng khắc phục và mức độ tin cậy của ước lượng. Không gom mọi khía cạnh vào một con số rồi mất phần giải thích.

## 10. Chọn biện pháp theo nguyên nhân gây tác động

Ưu tiên xem xét việc tránh hoặc giảm xử lý trước khi chỉ thêm lớp bảo vệ cho dữ liệu đã thu.

| Loại quyết định | Ví dụ trong case chấm công | Giới hạn cần nêu |
|---|---|---|
| Bỏ hoạt động không cần | Không thu vị trí ngoài thao tác được xác định | Cần kiểm tra SDK và dịch vụ nền thực tế |
| Giảm dữ liệu | Không gửi tọa độ đầy đủ nếu kết quả ít chi tiết hơn đủ dùng | Phải xác minh hiệu quả nghiệp vụ và chống giả mạo |
| Giới hạn mục đích | Không dùng dữ liệu chấm công để tự tạo xếp hạng hành vi | Cần ràng buộc quyền, pipeline và quản trị thay đổi |
| Giới hạn truy cập | Quản lý chỉ thấy nhóm được phân công và thông tin cần thiết | Quyền export, hỗ trợ và job nền cũng cần kiểm tra |
| Giảm lưu giữ | Dùng chính sách có mốc và job thực thi rõ ràng | Backup, lịch sử và restore có vòng đời riêng |
| Tăng minh bạch | Giải thích thời điểm thu và cách xử lý ngoại lệ | Không thay thế tính cần thiết hoặc phân quyền |
| Cải thiện độ chính xác | Không tự suy “vắng mặt” khi nguồn vị trí lỗi | Cần quy trình đối chiếu và sửa sai có kiểm soát |
| Giảm hậu quả | Có kênh phản hồi và xem xét quyết định | Phải đo được thời gian xử lý và tính khả dụng |
| Bảo vệ dữ liệu | Mã hóa, kiểm soát log và tách quyền | Không tự ngăn việc sử dụng hợp lệ nhưng quá mức |

Một biện pháp phát hiện không giống biện pháp ngăn chặn. Audit có thể giúp phát hiện truy cập bất thường sau đó, nhưng không bảo đảm dữ liệu chưa bị người có quyền nhìn thấy.

Hợp đồng với nhà cung cấp cũng cần gắn với cấu hình, quyền và bằng chứng. Một điều khoản không giữ payload không đủ nếu SDK hoặc service account vẫn gửi và lưu payload theo mặc định khác.

## 11. Chuyển kết quả PIA thành yêu cầu kỹ thuật

### 11.1. Mỗi yêu cầu phải trả lời được cách nghiệm thu

Mẫu diễn đạt:

> Trong phạm vi X và điều kiện Y, thành phần Z phải thực hiện hành vi A; trường hợp lỗi phải thực hiện B; bằng chứng C cho phép đánh giá.

Một bộ yêu cầu dẫn xuất minh họa:

| ID | Yêu cầu | Rủi ro liên quan | Oracle kiểm thử |
|---|---|---|---|
| PRV-LOC-01 | Client chính thức không yêu cầu hoặc gửi vị trí ngoài thao tác chấm công thuộc phạm vi đã chốt | PR-01 | Quan sát quyền thiết bị, tác vụ nền và request khi ngoài ca, mở app, retry |
| PRV-DATA-01 | API chỉ nhận tập field được phép; field vị trí ngoài schema bị từ chối mà không log giá trị | PR-01, PR-04 | Request có field dư bị chặn; log không chứa marker của field |
| PRV-ACCESS-01 | Màn hình và API báo cáo chỉ trả dữ liệu trong nhóm được phân công; export áp dụng cùng policy | PR-02 | Ma trận vai trò, nhóm và tenant, bao gồm truy vấn trực tiếp endpoint |
| PRV-PURPOSE-01 | Pipeline chấm công không tự chuyển dữ liệu sang mục đích phân tích mới khi chưa qua quy trình thay đổi | PR-02, PR-05 | Kiểm tra đích gửi, quyền job, cấu hình và feature flag |
| PRV-ACCURACY-01 | Lỗi nguồn xác minh tạo trạng thái cần xem xét, không tự chuyển thành kết luận vắng mặt | PR-03 | Fault injection tại nguồn dữ liệu và đối chiếu trạng thái nghiệp vụ |
| PRV-LOG-01 | Log, trace và dead-letter queue không chứa vị trí đầy đủ hoặc payload nhạy cảm bị loại | PR-04 | Marker tổng hợp không xuất hiện trong các kênh bị cấm |
| PRV-RET-01 | Expiry được tính từ mốc trong policy đã chốt; dữ liệu hết hạn không còn phục vụ luồng hoạt động | PR-06 | Fixture qua biên thời gian, job dọn và kiểm tra API đọc |
| PRV-RESTORE-01 | Môi trường restore phải áp dụng lại trạng thái xóa và hết hạn trước khi mở đường phục vụ | PR-06 | Restore fixture cũ không làm bản ghi hết hạn xuất hiện trở lại |
| PRV-EXCEPTION-01 | Quy trình xử lý lỗi có phương án không yêu cầu gửi lịch sử vị trí ngoài phạm vi cần thiết | PR-07 | Thử tình huống mất quyền vị trí, mất mạng và thiếu thiết bị |

Các yêu cầu này là minh họa; không khẳng định dự án thực đã chọn một kiến trúc vị trí cụ thể.

Nếu chọn phương án xử lý trên thiết bị và chỉ gửi kết quả, cần thêm yêu cầu bảo mật cho độ tin cậy của kết quả. Không dùng mục tiêu giảm dữ liệu để bỏ qua kiểm tra giả mạo client.

### 11.2. Đưa ngưỡng vào đúng chính sách và môi trường

“Xóa sớm” hoặc “xử lý khiếu nại nhanh” không phải tiêu chí đo được. Cần chốt mốc, thời hạn, phạm vi và ngoại lệ.

Ví dụ kiểm thử retention có thể dùng một policy riêng của fixture với thời hạn 7 ngày để chứng minh phép tính và job hoạt động. Điều đó không quyết định thời hạn giữ hồ sơ chấm công của sản phẩm thật.

Thời hạn nghiệp vụ thực tế phải được chủ sở hữu chính sách chốt; sau đó kiểm thử tính đúng của cấu hình, mốc thời gian, lịch sử, backup và điều kiện ngoại lệ tương ứng.

## 12. Lập sổ rủi ro và bộ hồ sơ có thể tái hiện

Một bản ghi rủi ro tối thiểu có thể gồm:

```text
riskId
assessmentId
processingActivity
systemRevision
affectedGroups
dataAndDerivedData
scenario
causesAndEnablingConditions
potentialHarms
existingControls
initialLikelihood
initialImpact
uncertainties
selectedMeasures
requirementIds
implementationOwner
evidenceReferences
verificationStatus
expectedResidualRisk
verifiedResidualRisk
decisionOwner
decisionAndConditions
reviewTriggers
```

Không cần điền điểm rủi ro đã xác minh khi chưa có bằng chứng. Có thể để trạng thái chờ và chỉ rõ ai cần cung cấp dữ liệu nào.

Một phần hồ sơ minh họa:

```yaml
assessmentId: PIA-ATTENDANCE-01
revision: 3
scope:
  feature: mobile-attendance
  systemRevision: candidate-build-7
  processingPurpose: confirm-assigned-shift-attendance
riskIds:
  - PR-01
  - PR-03
  - PR-06
requiredEvidence:
  - test-background-location-collection
  - test-verification-source-failure
  - test-retention-after-restore
decision:
  state: HOLD_PENDING_EVIDENCE
  condition: required-tests-not-yet-verified
```

Đây là ví dụ cấu trúc tài liệu, không phải kết quả đánh giá đã được thực hiện. Mã build, ca thử và quyết định trong ví dụ không đại diện cho bằng chứng của một hệ thống đang vận hành.

Hồ sơ nên cho phép người khác xác định nội dung và cấu hình nào đã được đánh giá. Một bản nhận xét không gắn revision có thể bị dùng lại cho một hệ thống đã thay đổi đáng kể.

## 13. Xác minh biện pháp và đánh giá rủi ro còn lại

### 13.1. Dùng cả kiểm tra thiết kế và kiểm tra hành vi

| Loại bằng chứng | Giá trị | Giới hạn |
|---|---|---|
| Sơ đồ và đặc tả | Thể hiện ý định, ranh giới và trách nhiệm | Không chứng minh triển khai thực tế |
| Cấu hình và policy | Cho biết quyền, đích gửi, thời hạn đang đặt | Có thể không bao phủ nhánh runtime hoặc mặc định SDK |
| Kiểm thử tích hợp | Quan sát luồng thực qua thành phần liên quan | Chỉ bao phủ dữ liệu, cấu hình và nhánh đã chạy |
| Kiểm thử lỗi | Phát hiện fallback, retry và trạng thái không mong muốn | Cần chứng minh điểm lỗi thực sự được kích hoạt |
| Diễn tập restore | Xác minh dữ liệu và chính sách sau khôi phục | Không tự bao phủ mọi mốc backup hoặc thế hệ cấu hình |
| Thử nghiệm với người dùng | Hiểu tác động của hành trình và khả năng phản hồi | Kết quả phụ thuộc mẫu và phương pháp |
| Giám sát sau triển khai | Phát hiện sai lệch và xu hướng thực tế | Không thay thế kiểm soát ngăn chặn trước đó |

Không chỉ kiểm tra đường thành công. Các nhánh lỗi thường tạo log payload, hàng đợi thất bại hoặc lưu tạm lâu hơn thiết kế.

### 13.2. Ma trận kiểm thử tối thiểu cho case minh họa

| Ca | Thao tác thử | Điều kiện đạt |
|---|---|---|
| TC-01 | Mở app ngoài ca và không thao tác chấm công | Không có yêu cầu vị trí hoặc gửi dữ liệu vị trí ngoài phạm vi được phép |
| TC-02 | Chấm công với schema đã chốt | Payload chỉ có dữ liệu cần thiết; đích nhận đúng cấu hình |
| TC-03 | Gửi field tọa độ không được phép qua API | Bị từ chối có kiểm soát, không ghi tọa độ vào log |
| TC-04 | Quản lý nhóm A yêu cầu dữ liệu nhóm B | API và export không trả dữ liệu ngoài quyền |
| TC-05 | Nguồn xác minh timeout hoặc sai định dạng | Tạo trạng thái cần xử lý, không kết luận bất lợi tự động ngoài hợp đồng |
| TC-06 | Retry sau mất mạng | Không mở rộng dữ liệu thu, không tạo bản sao ngoài vòng đời đã chốt |
| TC-07 | Job dọn gặp dữ liệu ở hai phía biên expiry | Xử lý theo policy và ngoại lệ, có bằng chứng hoàn tất |
| TC-08 | Restore backup chứa bản ghi đã hết hạn | Bản ghi không quay lại luồng hoạt động trước khi xử lý expiry |
| TC-09 | Tắt cấu hình chia sẻ cho dịch vụ phân tích | Không có đường gửi nền còn hoạt động ngoài cấu hình |
| TC-10 | Người dùng cần sửa kết quả hoặc dùng phương án ngoại lệ | Có hành trình khả dụng, đúng quyền và không thu thêm dữ liệu không cần |

Dữ liệu thử phải là dữ liệu tổng hợp thuộc môi trường kiểm soát. Không cần thu vị trí thật của nhân viên để chạy các ca này.

### 13.3. Cập nhật rủi ro bằng bằng chứng đúng phạm vi

Nếu TC-01 đạt trên Android nhưng chưa chạy trên nền tảng khác đang được hỗ trợ, không kết luận “mọi client không thu nền”.

Nếu không thể quan sát lưu trữ phía nhà cung cấp, phải nêu giới hạn và bằng chứng thay thế được chấp nhận, hoặc giữ rủi ro chưa được xác minh. Không gộp phần chưa biết vào kết quả PASS.

Rủi ro còn lại phải liên kết tới bằng chứng và giả định. Khi một giả định không còn đúng, phần kết luận dựa trên nó cần được xem xét lại.

## 14. Ra quyết định triển khai và xử lý rủi ro còn lại

PIA hỗ trợ quyết định; người viết báo cáo không tự có thẩm quyền chấp nhận mọi tác động.

Các vai trò cần rõ:

| Vai trò | Trách nhiệm chính |
|---|---|
| Chủ sở hữu nghiệp vụ | Xác nhận mục tiêu, lựa chọn phương án và chịu trách nhiệm thay đổi nghiệp vụ |
| Chủ sở hữu kỹ thuật | Thiết kế, triển khai và cung cấp bằng chứng kiểm soát |
| Chuyên trách quyền riêng tư hoặc chính sách | Xác định yêu cầu áp dụng, rà tác động và điều kiện chuyển cấp |
| Nhóm bảo mật | Phân tích đe dọa, quyền truy cập và các kiểm soát an toàn |
| Nhóm kiểm thử | Xác minh hành vi theo oracle, nêu giới hạn bằng chứng |
| Bên có thẩm quyền quyết định | Ghi nhận quyết định trong phạm vi được giao và theo quy tắc chuyển cấp |

Có thể chọn triển khai, triển khai có điều kiện, trì hoãn, đổi thiết kế hoặc không thực hiện hoạt động xử lý. Điều kiện phải có người làm, hạn và tiêu chí đóng.

Không ghi “chấp nhận rủi ro” để thay thế một yêu cầu bắt buộc theo chính sách áp dụng hoặc thẩm quyền bên ngoài tổ chức. Việc chấp nhận cũng không chuyển hậu quả sang người dùng chỉ vì họ đã nhận thông báo.

Ví dụ điều kiện trước triển khai cho case này:

- Không còn thu nền ngoài phạm vi đã xác nhận.
- API, export và log đáp ứng yêu cầu giảm dữ liệu và truy cập.
- Đã kiểm chứng xử lý khi nguồn xác minh lỗi.
- Có policy retention được phê duyệt và bằng chứng restore tương ứng.
- Những kịch bản tác động nghiêm trọng đã được rà bởi vai trò có thẩm quyền.
- Bằng chứng còn thiếu được ghi rõ; không có kết luận dựa trên giả định đã bị bác bỏ.

Nếu quyết định trì hoãn tính năng mới, cần chỉ rõ phần bị trì hoãn và trạng thái chức năng hiện hữu. Không để một feature flag chỉ tắt giao diện trong khi job thu thập mới vẫn chạy.

## 15. Duy trì PIA trong vòng đời phát triển và vận hành

### 15.1. Các tín hiệu phải xem xét lại đánh giá

- Thêm mục đích hoặc dùng dữ liệu cho quyết định khác.
- Thêm field, dữ liệu suy luận hoặc liên kết nguồn dữ liệu.
- Thay đổi nhóm người, quy mô hoặc khả năng từ chối.
- Thêm SDK, nhà cung cấp, bên nhận hoặc nơi xử lý.
- Đổi quyền báo cáo, API export hoặc công cụ hỗ trợ.
- Tăng thời gian lưu hoặc đổi quy trình backup và restore.
- Có sự cố, khiếu nại hoặc số liệu cho thấy kiểm soát không hoạt động.
- Thay đổi chính sách áp dụng hoặc giả định quan trọng của thiết kế.

Một thay đổi như thêm cột định danh vào báo cáo có thể làm tăng khả năng liên kết dù không thu dữ liệu mới. Vì vậy, trigger không chỉ là “thêm trường đầu vào”.

### 15.2. Gắn với quy trình thay đổi có sẵn

Pull request hoặc đề xuất tính năng có thể yêu cầu mô tả tác động tới mục đích, dữ liệu, bên nhận và retention. Cấu hình triển khai cần liên kết tới revision PIA tương ứng khi mức rủi ro yêu cầu.

Trong vận hành, metric có thể đo lỗi job xóa, truy cập ngoài mẫu được phép, thay đổi đích gửi hoặc trạng thái kiểm soát. Không tạo thêm một kho dữ liệu hành vi chi tiết chỉ để chứng minh tổ chức có theo dõi quyền riêng tư.

Một lần rà định kỳ không thay thế việc phản ứng ngay khi có thay đổi đáng kể. Ngược lại, không cần tạo tài liệu mới hoàn toàn cho mọi thay đổi nhỏ; cần lưu quan hệ revision và lý do mức rà soát được chọn.

### 15.3. Bảo vệ chính hồ sơ đánh giá

PIA có thể chứa sơ đồ, điểm yếu, nhóm người dễ bị tác động và tình huống nhạy cảm. Cần quyền truy cập, lịch sử sửa và thời hạn lưu phù hợp.

Bản chia sẻ rộng có thể tóm tắt quyết định mà không kèm dữ liệu cá nhân hoặc chi tiết có thể hỗ trợ lạm dụng. Giảm nội dung nhạy cảm trong bản công bố không đồng nghĩa được phép che giấu vấn đề với các vai trò cần đánh giá.

## 16. Bộ yêu cầu cho quy trình PIA

Các mã dưới đây giúp biến việc đánh giá thành một quy trình có thể kiểm chứng. Chúng bổ sung cho yêu cầu sản phẩm dẫn xuất ở phần trước.

| ID | Yêu cầu quy trình | Bằng chứng |
|---|---|---|
| PIA-01 | Sàng lọc được thực hiện khi có trigger và có lý do cho mức đánh giá được chọn | Bản sàng lọc, revision và người chịu trách nhiệm |
| PIA-02 | Phạm vi bao gồm mục đích, nhóm người, dữ liệu trực tiếp và dẫn xuất, bên nhận và vòng đời | Danh mục và sơ đồ được xác nhận |
| PIA-03 | Kịch bản rủi ro nêu điều kiện, hoạt động, người chịu tác động và hậu quả | Sổ rủi ro có mô tả nhân quả |
| PIA-04 | Phương án ít tác động hơn được xem xét cùng hiệu quả và rủi ro riêng | Bảng phương án và lý do lựa chọn |
| PIA-05 | Thang điểm, giả định, bất định và quy tắc chuyển cấp được ghi rõ | Phương pháp và bản chấm có giải thích |
| PIA-06 | Mỗi biện pháp được chọn có yêu cầu, người thực hiện và tiêu chí xác minh | Mapping risk–requirement–owner–test |
| PIA-07 | Biện pháp chưa triển khai không được ghi thành rủi ro đã được giảm bằng bằng chứng | Trạng thái triển khai, test và residual risk tách biệt |
| PIA-08 | Quyết định nêu phạm vi, điều kiện, thẩm quyền và bằng chứng còn thiếu | Bản quyết định cùng danh sách việc phải hoàn tất |
| PIA-09 | Thay đổi quan trọng kích hoạt xem xét lại thay vì tự dùng kết luận cũ | Lịch sử revision và trigger trong quy trình thay đổi |
| PIA-10 | Hồ sơ đánh giá và bằng chứng tuân theo nguyên tắc giảm dữ liệu và giới hạn truy cập | Schema hồ sơ, quyền và chính sách lưu giữ |

“Có file PIA” không phải oracle đủ. Cần kiểm tra hồ sơ có dẫn tới thay đổi thiết kế, bằng chứng và quyết định phù hợp với phiên bản đang triển khai hay không.

## 17. Những sai lầm làm đánh giá mất giá trị

| Sai lầm | Vì sao không đủ | Cách cải thiện |
|---|---|---|
| Chỉ liệt kê mã hóa và TLS | Bỏ qua thu thập quá mức, dùng sai mục đích và quyết định bất lợi | Phân tích tác động của hoạt động hợp lệ |
| Chỉ chấm rủi ro tài chính của công ty | Không phản ánh người chịu ảnh hưởng | Nêu nhóm người và hậu quả đối với họ |
| Chấm thấp vì chưa từng có sự cố | Thiếu sự cố không chứng minh khả năng thấp | Xem đường xảy ra, quyền và mức tiếp xúc thực tế |
| Ghi “đã thông báo” để đóng mọi rủi ro | Minh bạch không thay thế tính cần thiết và kiểm soát | Giảm xử lý và xác minh biện pháp theo nguyên nhân |
| Dùng dữ liệu băm như dữ liệu vô danh | Có thể vẫn liên kết hoặc dò lại | Đánh giá dữ liệu phụ trợ và khả năng nhận diện |
| Chấp nhận rủi ro bằng một checkbox | Không thể hiện phạm vi và thẩm quyền | Ghi quyết định, điều kiện và quy tắc chuyển cấp |
| Đánh giá sau khi hệ thống đã cố định | Khó so sánh phương án và tránh thu thập | Bắt đầu sớm, cập nhật theo revision |
| Đóng biện pháp khi ticket được giao | Giao việc chưa phải triển khai hoặc kiểm chứng | Gắn điều kiện đóng với bằng chứng |
| Không thử restore | Dữ liệu hết hạn có thể quay lại | Có ca phục hồi và áp dụng lại trạng thái vòng đời |
| Tạo log chi tiết để chứng minh giảm dữ liệu | Bằng chứng tự mở thêm kho dữ liệu nhạy cảm | Dùng marker tổng hợp và telemetry tối thiểu |

## 18. Bài tập xây một hồ sơ đánh giá có thể nghiệm thu

Một nền tảng đào tạo muốn ghi thời gian học, sự kiện tương tác và hình ảnh từ thiết bị để phát hiện bất thường. Nhóm quản lý muốn dùng cùng dữ liệu để xếp hạng nhân viên. Dữ liệu được gửi tới một dịch vụ phân tích, lưu vào kho báo cáo và sao lưu định kỳ.

Hãy thực hiện:

1. Tách các mục đích; chỉ rõ mục đích nào chưa có bằng chứng về tính cần thiết.
2. Xác định nhóm người chịu ảnh hưởng và những người có thể xuất hiện gián tiếp trong dữ liệu.
3. Vẽ luồng gồm thiết bị, API, SDK, log, báo cáo, nhà cung cấp và backup.
4. So sánh ít nhất ba phương án đạt mục tiêu với mức thu thập khác nhau.
5. Viết ít nhất năm kịch bản tác động, gồm một trường hợp không có kẻ tấn công và một trường hợp dữ liệu sai.
6. Chọn thang đánh giá, nêu bất định và quy tắc chuyển cấp cho tác động nghiêm trọng.
7. Chuyển ba biện pháp thành yêu cầu có oracle, điểm quan sát và chủ sở hữu.
8. Thiết kế ca kiểm thử cho phân quyền, log, retention và restore.
9. Viết một quyết định triển khai có điều kiện; không dùng bằng chứng chưa có như thể đã PASS.
10. Liệt kê các thay đổi hoặc sự kiện khiến kết luận phải được xem xét lại.

Hồ sơ cần cho phép một người không tham gia buổi thảo luận hiểu vì sao phương án được chọn, ai có thể chịu tác động, biện pháp nào đã được xác minh và điều gì vẫn còn chưa được giải quyết.
