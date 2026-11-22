# Thủ công và khám phá: Đánh giá mức bao phủ khám phá và thông tin còn thiếu

## 1. Vì sao phải đánh giá mức bao phủ của kiểm thử khám phá?

Kiểm thử khám phá (exploratory testing) là hoạt động đồng thời học hỏi về sản phẩm, thiết kế thử nghiệm và thực hiện kiểm tra dựa trên thông tin vừa thu được. Người kiểm thử không chỉ chạy lại một danh sách bước cố định; họ đặt câu hỏi, hình thành giả thuyết, thử các điều kiện khác nhau, quan sát phản hồi và điều chỉnh hướng khám phá.

Tính linh hoạt này giúp phát hiện vấn đề mà kịch bản định sẵn có thể bỏ sót. Tuy nhiên, nếu không ghi lại phạm vi và kết quả, nhóm khó biết:

- Những hành trình, quy tắc, vai trò và trạng thái nào đã được khảo sát?
- Khu vực nào mới chỉ được chạm tới, khu vực nào đã được thử sâu?
- Những điều kiện quan trọng nào chưa được kiểm tra?
- Có điểm nào chưa thể kết luận vì thiếu yêu cầu, dữ liệu, quyền hoặc môi trường?
- Phiên khám phá tiếp theo nên tập trung vào đâu để giảm rủi ro?

Trong **VALIDATION_TESTING_STRATEGY**, đánh giá mức bao phủ khám phá giúp biến hoạt động thủ công linh hoạt thành nguồn bằng chứng có thể truy vết. Mục tiêu không phải ép mọi phiên khám phá thành một bộ kịch bản cứng hoặc tạo ra một tỷ lệ phần trăm duy nhất. Mục tiêu là mô tả trung thực phần đã khảo sát, chất lượng bằng chứng và khoảng trống còn lại.

Một báo cáo tốt cần phân biệt rõ “đã thử và không thấy lỗi”, “đã thử và có phát hiện”, “chưa thử” và “chưa thể thử”. Bốn trạng thái này có ý nghĩa khác nhau đối với quyết định chất lượng.

## 2. Hiểu đúng về coverage trong exploratory testing

### 2.1. Coverage không chỉ là số lượng test đã chạy

Trong kiểm thử tự động, nhóm có thể theo dõi số test pass, line coverage hoặc branch coverage. Những chỉ số này hữu ích trong phạm vi của chúng, nhưng không phản ánh đầy đủ mức độ khảo sát hành vi và rủi ro trong exploratory testing.

Một phiên có thể chạy nhiều thao tác nhưng chỉ lặp lại cùng một đường đi. Một phiên khác có thể chỉ có ít thao tác nhưng kiểm tra được một quy tắc nghiệp vụ quan trọng ở các trạng thái, vai trò và điều kiện lỗi khác nhau. Số thao tác hoặc thời lượng không tự nói lên chất lượng bao phủ.

Coverage trong khám phá cần trả lời: **phạm vi nào đã được khảo sát, ở mức sâu nào, với điều kiện nào và bằng chứng nào?**

### 2.2. Phân biệt các loại coverage

| Loại coverage | Điều được theo dõi | Ví dụ |
| --- | --- | --- |
| Code coverage | Dòng lệnh, nhánh hoặc điều kiện mã đã được thực thi | Branch coverage của module tính phí |
| Requirement coverage | Yêu cầu hoặc tiêu chí chấp nhận đã được xác nhận | Quy tắc hủy lịch trong hạn |
| Workflow coverage | Hành trình và bước nghiệp vụ đã được khảo sát | Tạo, thanh toán, tra cứu và hủy lịch |
| Risk coverage | Rủi ro và chế độ lỗi đã được điều tra | Callback lặp, đặt trùng, truy cập sai quyền |
| State/transition coverage | Trạng thái và chuyển tiếp đã được thử | PENDING sang CONFIRMED hoặc CANCELLED |
| Data coverage | Nhóm dữ liệu, giá trị biên và chất lượng dữ liệu đã được thử | Dữ liệu thiếu, trùng, rất lớn hoặc sai định dạng |
| Role/permission coverage | Vai trò và ranh giới quyền đã được khảo sát | Người dùng thường, quản trị viên, người thuộc tenant khác |
| Environment/platform coverage | Môi trường, thiết bị, trình duyệt hoặc cấu hình đã được thử | Mobile, desktop, timezone và feature flag |
| Integration coverage | Các ranh giới và phụ thuộc đã được khảo sát | API thanh toán, queue, email provider |

Không phải mọi chiều đều cần áp dụng cho mọi tính năng. Chọn chiều coverage dựa trên rủi ro, mục tiêu sản phẩm và cách hệ thống hoạt động.

### 2.3. Phân biệt đã khảo sát với đã chứng minh

Trong khám phá, người kiểm thử có thể mở một màn hình, thử vài dữ liệu và không quan sát thấy lỗi. Điều đó chỉ chứng minh những thao tác và điều kiện cụ thể đã được thực hiện.

Không nên suy rộng:

- Đã mở trang không có nghĩa đã kiểm tra mọi trạng thái của trang.
- Đã thử một vai trò không có nghĩa đã kiểm tra ma trận phân quyền.
- Đã thực hiện một giao dịch thành công không có nghĩa đã xác nhận timeout, retry và callback lặp.
- Không thấy lỗi trong phiên khám phá không có nghĩa khu vực đó không còn rủi ro.

Hãy ghi rõ mức khảo sát và điều kiện. Khi bằng chứng chưa đủ để kết luận, đánh dấu khoảng trống thay vì nâng mức coverage bằng suy đoán.

## 3. Xây dựng bản đồ phạm vi khám phá

### 3.1. Bắt đầu từ mục tiêu, hành trình và rủi ro

Trước phiên khám phá, xác định:

1. Khả năng hoặc hành trình nào đang được khảo sát?
2. Người dùng hoặc vai trò nào sử dụng khả năng đó?
3. Kết quả nghiệp vụ nào cần được xác nhận?
4. Rủi ro nào có thể gây hậu quả lớn?
5. Những thay đổi gần đây hoặc khu vực có lịch sử lỗi là gì?
6. Có giới hạn nào về môi trường, dữ liệu hoặc phụ thuộc?

Mục tiêu nên cụ thể. “Khám phá trang đặt lịch” quá rộng; “khám phá cách trang đặt lịch phản ứng khi khung giờ hết chỗ trong lúc người dùng đang xác nhận” tạo ra một hướng điều tra rõ hơn.

### 3.2. Chọn các chiều cần theo dõi

Một bản đồ đơn giản có thể sử dụng các chiều sau:

- **Chức năng:** tính năng hoặc thành phần cần khảo sát.
- **Hành trình:** đường đi của người dùng từ điểm bắt đầu đến kết quả.
- **Vai trò:** danh tính, quyền và loại người dùng.
- **Trạng thái:** trạng thái ban đầu, chuyển tiếp và trạng thái kết thúc.
- **Dữ liệu:** giá trị thường gặp, biên, bất thường và dữ liệu lịch sử.
- **Điều kiện vận hành:** thời gian, tải, mạng, timeout và phụ thuộc.
- **Nền tảng:** trình duyệt, thiết bị, hệ điều hành, locale hoặc cấu hình.
- **Rủi ro:** hậu quả, khả năng xảy ra và khả năng phát hiện.

Không cần tạo ma trận lớn cho mọi tổ hợp. Chọn những chiều làm thay đổi hành vi hoặc mức rủi ro. Với các chiều có nhiều giá trị, có thể nhóm theo phân vùng tương đương hoặc chọn các tổ hợp đại diện.

### 3.3. Dùng trạng thái coverage có ý nghĩa

Có thể dùng một thang mô tả nhất quán:

| Trạng thái | Ý nghĩa | Bằng chứng tối thiểu |
| --- | --- | --- |
| Chưa khảo sát | Chưa có hoạt động khám phá cho phạm vi này | Có thể ghi lý do hoặc mức ưu tiên |
| Đã chạm tới | Đã xem hoặc thao tác sơ bộ nhưng chưa kiểm tra có chủ đích | Ghi hành động và giới hạn |
| Đã khảo sát một phần | Đã thử một số điều kiện hoặc đường đi nhưng còn khoảng trống rõ | Ghi điều kiện đã thử và điều chưa thử |
| Đã khảo sát theo mục tiêu | Đã thực hiện charter, xem xét kết quả và ghi bằng chứng theo phạm vi đã định | Ghi charter, dữ liệu, môi trường, kết quả và ghi chú |
| Cần khảo sát lại | Có thay đổi, phát hiện mới hoặc bằng chứng cho thấy kết quả cũ không còn đại diện | Ghi nguyên nhân và phạm vi bị ảnh hưởng |
| Bị chặn | Không thể khảo sát do thiếu điều kiện, quyền, dữ liệu hoặc phụ thuộc | Ghi blocker, tác động và người cần hỗ trợ |

Các trạng thái này mô tả mức độ khảo sát, không phải đánh giá pass/fail của sản phẩm. Một phạm vi có thể “đã khảo sát theo mục tiêu” nhưng vẫn có defect; ngược lại, “chưa khảo sát” không có nghĩa chắc chắn có lỗi.

### 3.4. Ma trận coverage minh họa

Giả sử cần khám phá hành trình đặt lịch:

| Phạm vi | Vai trò / dữ liệu | Trạng thái coverage | Bằng chứng hoặc khoảng trống |
| --- | --- | --- | --- |
| Tìm khung giờ | Người dùng thường, khung giờ còn trống | Đã khảo sát theo mục tiêu | Kết quả tìm kiếm và bộ lọc đúng |
| Xác nhận lịch | Người dùng thường, khung giờ còn trống | Đã khảo sát một phần | Đã thử luồng thành công; chưa thử hai người xác nhận đồng thời |
| Thanh toán | Sandbox chấp nhận | Đã khảo sát theo mục tiêu | Giao dịch được liên kết với lịch |
| Callback thanh toán | Callback lặp hoặc đến trễ | Chưa khảo sát | Cần tạo dữ liệu và kịch bản sự kiện lặp |
| Hủy lịch | Người dùng đã thanh toán | Đã chạm tới | Đã xem giao diện; chưa xác nhận quy tắc hoàn tiền |
| Truy cập lịch | Người dùng khác chủ sở hữu | Bị chặn | Thiếu tài khoản có vai trò khác để kiểm tra |

Ma trận này cho thấy phạm vi đã được thử, nhưng cũng chỉ ra hai khoảng trống quan trọng: callback lặp và quy tắc hủy/hoàn tiền. Nhóm có thể ưu tiên phiên khám phá tiếp theo dựa trên mức rủi ro thay vì chỉ tiếp tục những bước dễ thực hiện.

## 4. Thiết kế charter cho phiên khám phá

### 4.1. Charter là mục tiêu điều tra

Charter mô tả câu hỏi hoặc rủi ro cần khảo sát, phạm vi và hướng thử nghiệm. Nó tạo trọng tâm nhưng vẫn cho phép người kiểm thử điều chỉnh khi học được thông tin mới.

Một charter nên có:

- **Mục tiêu:** điều cần hiểu hoặc xác nhận.
- **Phạm vi:** chức năng, hành trình, vai trò hoặc ranh giới.
- **Rủi ro/giả thuyết:** điều có thể sai và vì sao.
- **Hướng khám phá:** dữ liệu, trạng thái, thao tác hoặc điều kiện cần thử.
- **Giới hạn:** môi trường, tài khoản, dữ liệu và thời gian.
- **Bằng chứng:** thông tin cần lưu để đánh giá kết quả.

Ví dụ:

> Khám phá khả năng đặt trùng khung giờ khi hai người dùng xác nhận gần như đồng thời. Thử với hai tài khoản và cùng một tài nguyên, quan sát phản hồi của cả hai yêu cầu, trạng thái cuối của lịch và tính nhất quán của dữ liệu.

Charter này cụ thể hơn “test đặt lịch”, đồng thời để người kiểm thử tự chọn cách tạo tải đồng thời hoặc thay đổi thứ tự thao tác trong giới hạn môi trường.

### 4.2. Time-box và session-based testing

Một phiên khám phá có thể được giới hạn thời gian (time-box) để tập trung và tạo nhịp phản hồi. Session-based testing thường kết hợp:

- Charter đã thống nhất.
- Thời lượng phiên.
- Ghi chú về hành động, quan sát và câu hỏi phát sinh.
- Danh sách defect hoặc vấn đề cần điều tra.
- Debrief để xem xét coverage và thông tin còn thiếu.

Thời lượng là giới hạn tổ chức, không phải thước đo chất lượng. Một phiên dài không tự động có coverage tốt; một phiên ngắn có thể tạo ra phát hiện quan trọng nếu nhắm đúng rủi ro.

### 4.3. Điều chỉnh charter khi phát hiện thông tin mới

Khám phá có thể làm lộ ra hành vi ngoài dự kiến. Ví dụ, khi thử callback lặp, người kiểm thử nhận thấy hệ thống chỉ lỗi nếu callback đến sau khi tác vụ hết hạn. Có thể:

1. Ghi phát hiện ban đầu.
2. Cập nhật giả thuyết về nguyên nhân hoặc điều kiện.
3. Tách charter mới để điều tra thứ tự sự kiện.
4. Giữ liên kết giữa charter gốc và charter mới.
5. Cập nhật bản đồ coverage sau khi có bằng chứng.

Không nên mở rộng phiên vô hạn theo mọi phát hiện. Nếu hướng mới có mục tiêu và bằng chứng riêng, hãy ghi thành nhiệm vụ hoặc charter tiếp theo.

## 5. Ghi nhận thông tin còn thiếu

Thông tin còn thiếu là phần dữ liệu hoặc hiểu biết cần có để đánh giá hành vi, chọn thử nghiệm hoặc kết luận về rủi ro. Nó không chỉ là một câu hỏi chưa trả lời; nó có thể là blocker kỹ thuật, thiếu oracle hoặc giả định chưa được xác minh.

### 5.1. Các loại khoảng trống thường gặp

| Loại khoảng trống | Biểu hiện | Ví dụ |
| --- | --- | --- |
| Yêu cầu chưa rõ | Không biết kết quả mong đợi trong một tình huống | Không rõ thanh toán timeout thì lịch được giữ hay giải phóng |
| Quy tắc nghiệp vụ thiếu | Chưa định nghĩa cách xử lý ngoại lệ | Không có chính sách cho hủy lịch sát giờ |
| Oracle chưa có | Không biết dựa vào đâu để kết luận đúng/sai | UI báo thành công nhưng chưa rõ trạng thái cuối nào phải được lưu |
| Dữ liệu không đủ | Không có dữ liệu hoặc danh tính để tạo điều kiện | Thiếu tài khoản thuộc tenant khác |
| Môi trường không đại diện | Không tái hiện được điều kiện cần khảo sát | Sandbox không hỗ trợ callback lặp |
| Phụ thuộc không sẵn sàng | Provider, queue hoặc dịch vụ khác không thể truy cập | Dịch vụ thông báo đang ngừng trong môi trường test |
| Thiếu khả năng quan sát | Không thể theo dõi trạng thái hoặc đường đi | Không có correlation ID giữa API và worker |
| Phạm vi chưa rõ | Không biết thành phần hoặc vai trò nào thuộc mục tiêu | Chưa xác định API quản trị có nằm trong phạm vi UAT |
| Thời gian/quyền bị giới hạn | Không thể thực hiện hoạt động cần thiết | Không có quyền tạo dữ liệu hoặc bật feature flag |

Phân loại đúng giúp giao vấn đề cho người có thể giải quyết. QA không thể tự quyết định chính sách hoàn tiền nếu chủ nghiệp vụ chưa định nghĩa; nhóm phát triển có thể cần bổ sung telemetry nếu không có bằng chứng runtime.

### 5.2. Ghi khoảng trống dưới dạng câu hỏi có thể hành động

Tránh ghi chung chung như “cần thêm thông tin về thanh toán”. Hãy ghi:

- Câu hỏi cụ thể cần trả lời.
- Vì sao câu trả lời ảnh hưởng đến kiểm thử hoặc quyết định.
- Phạm vi và rủi ro bị ảnh hưởng.
- Người hoặc nhóm có thể cung cấp thông tin.
- Bằng chứng hoặc quyết định cần nhận.
- Thời điểm cần có câu trả lời.

Ví dụ:

| Trường | Nội dung |
| --- | --- |
| Câu hỏi | Khi callback thành công đến sau khi thời hạn giữ khung giờ kết thúc, hệ thống phải xác nhận lịch hay đưa giao dịch vào đối soát? |
| Tác động | Không thể xác định oracle cho callback đến trễ; có nguy cơ xác nhận lịch đã được người khác đặt |
| Chủ sở hữu | Chủ sản phẩm đặt lịch và nhóm thanh toán |
| Bằng chứng cần có | Quy tắc nghiệp vụ được phê duyệt và trạng thái xử lý cuối |
| Ưu tiên | Cao vì ảnh hưởng lịch và giao dịch |
| Hành động tiếp theo | Làm rõ chính sách, cập nhật state model và tạo charter kiểm thử |

### 5.3. Phân biệt chưa biết với chưa kiểm tra

Hai loại này cần được ghi riêng:

- **Chưa biết:** thiếu thông tin để xác định hành vi đúng hoặc cách kiểm tra. Ví dụ, chưa có quy tắc xử lý callback đến trễ.
- **Chưa kiểm tra:** đã biết quy tắc nhưng chưa thực hiện thử nghiệm. Ví dụ, đã có chính sách nhưng chưa có tài khoản phù hợp để kiểm tra.

Nếu gộp chúng, nhóm có thể dành thời gian chạy test trong khi vẫn chưa biết oracle, hoặc tiếp tục hỏi nghiệp vụ dù chỉ cần chuẩn bị dữ liệu.

## 6. Đánh giá chiều sâu và chất lượng bằng chứng

### 6.1. Không đánh đồng thao tác với độ sâu

Một khu vực được coi là đã khảo sát sâu khi người kiểm thử đã xem xét các điều kiện phù hợp với mục tiêu, quan sát kết quả, thử các biến thể quan trọng và ghi lại giới hạn. Chỉ mở màn hình hoặc chạy một happy path không đủ để khẳng định độ sâu.

Có thể đánh giá chiều sâu theo các câu hỏi:

- Đã thử đường đi chính và các nhánh rủi ro quan trọng chưa?
- Đã thay đổi dữ liệu, vai trò hoặc trạng thái có thể làm thay đổi hành vi chưa?
- Đã kiểm tra trường hợp lỗi, biên, lặp, trễ hoặc gián đoạn phù hợp chưa?
- Có oracle đủ rõ để xác định kết quả đúng không?
- Có thể tái hiện kết quả bằng dữ liệu và điều kiện đã ghi không?
- Có bằng chứng đủ để phân biệt lỗi sản phẩm với lỗi môi trường hoặc phụ thuộc không?

### 6.2. Đánh giá độ tin cậy của bằng chứng

| Mức bằng chứng | Mô tả | Cách diễn giải |
| --- | --- | --- |
| Quan sát sơ bộ | Ghi nhận giao diện hoặc phản hồi nhưng chưa xác định oracle | Chỉ dùng để hình thành câu hỏi |
| Quan sát có điều kiện | Đã thực hiện hành động và ghi điều kiện nhưng bằng chứng kết quả còn hạn chế | Có thể chỉ ra hướng điều tra, chưa đủ kết luận rộng |
| Bằng chứng tái lập | Có charter, dữ liệu, môi trường, hành động và kết quả có thể lặp lại | Có thể dùng để xác nhận phạm vi cụ thể |
| Bằng chứng đối chiếu | Kết quả được xác nhận qua nhiều nguồn phù hợp, ví dụ API và trạng thái nghiệp vụ | Tăng độ tin cậy cho rủi ro quan trọng |

Không phải mọi khám phá đều cần nhiều nguồn bằng chứng. Hãy tăng mức đối chiếu khi hậu quả của kết luận sai cao hoặc khi nguồn quan sát ban đầu không đủ tin cậy.

### 6.3. Phân biệt phát hiện, nghi vấn và lỗi đã xác nhận

- **Phát hiện (finding):** quan sát bất thường cần được ghi lại và đánh giá.
- **Nghi vấn (suspicion):** dấu hiệu có thể là lỗi nhưng chưa đủ bằng chứng.
- **Defect đã xác nhận:** hành vi thực tế vi phạm yêu cầu, quy tắc hoặc thuộc tính đã được thống nhất.
- **Câu hỏi yêu cầu:** chưa có tiêu chí để quyết định hành vi là đúng hay sai.

Không nên biến mọi nghi vấn thành defect mà không kiểm tra; cũng không được bỏ qua một phát hiện có tác động lớn chỉ vì chưa tái hiện được ngay. Ghi rõ mức độ chắc chắn và bằng chứng đang thiếu.

## 7. Ưu tiên khoảng trống khám phá theo rủi ro

Không thể khám phá mọi tổ hợp trong thời gian hữu hạn. Hãy ưu tiên theo hậu quả, khả năng xảy ra, độ khó phát hiện và mức thiếu bằng chứng.

### 7.1. Các tín hiệu cần ưu tiên

- Luồng tạo doanh thu, giao dịch, quyền truy cập hoặc dữ liệu quan trọng.
- Thay đổi mới ở khu vực có lịch sử lỗi.
- Tích hợp với provider hoặc hệ thống không thuộc quyền kiểm soát của nhóm.
- Xử lý bất đồng bộ, concurrency, timeout, retry và event đến sai thứ tự.
- Vai trò hoặc tenant có quyền khác nhau.
- Điều kiện biên, dữ liệu hiếm hoặc dữ liệu lịch sử.
- Khu vực chưa có oracle hoặc thiếu telemetry.
- Những giả định quan trọng chưa được xác minh.

### 7.2. Ma trận ưu tiên khoảng trống

Có thể chấm từng khoảng trống theo tác động (I), khả năng xảy ra (L) và mức thiếu bằng chứng (G), mỗi yếu tố từ 1 đến 5:

\[
P = I \times L \times G
\]

Điểm này là công cụ sắp thứ tự, không phải xác suất. Nhóm cần thống nhất thang điểm và nâng ưu tiên cho các yêu cầu bắt buộc hoặc hậu quả nghiêm trọng.

| Khoảng trống | I | L | G | P | Hành động gợi ý |
| --- | ---: | ---: | ---: | ---: | --- |
| Callback thanh toán lặp | 5 | 3 | 5 | 75 | Ưu tiên charter về idempotency và trạng thái cuối |
| Hủy lịch sát giờ | 4 | 3 | 4 | 48 | Làm rõ quy tắc và thử các giá trị biên |
| Màu biểu tượng ở trang ít dùng | 1 | 2 | 2 | 4 | Đưa vào phiên khám phá giao diện khi có thay đổi |

Các điểm số chỉ minh họa cách so sánh. Đánh giá thực tế cần dựa trên dữ liệu sản phẩm, lịch sử lỗi và chính sách.

### 7.3. Quyết định bước tiếp theo

Mỗi khoảng trống nên dẫn đến một trong các hành động:

- Làm rõ yêu cầu hoặc quy tắc với chủ sở hữu nghiệp vụ.
- Chuẩn bị dữ liệu, tài khoản hoặc môi trường.
- Bổ sung khả năng quan sát hoặc oracle.
- Tạo charter khám phá có mục tiêu cụ thể.
- Tạo kiểm thử xác định hoặc regression test khi hành vi đã rõ.
- Chấp nhận rủi ro còn lại theo đúng thẩm quyền và ghi rõ giới hạn.

Không đóng khoảng trống chỉ bằng cách đổi trạng thái trong ma trận. Cần có câu trả lời, bằng chứng hoặc quyết định chấp nhận có trách nhiệm.

## 8. Quy trình thực hiện và cập nhật coverage

~~~mermaid
flowchart TD
    A["Xác định mục tiêu và rủi ro"] --> B["Chọn chiều coverage cần theo dõi"]
    B --> C["Tạo charter và chuẩn bị dữ liệu"]
    C --> D["Thực hiện khám phá, ghi quan sát"]
    D --> E["Debrief: phát hiện và đánh giá bằng chứng"]
    E --> F["Cập nhật bản đồ coverage"]
    F --> G{"Còn khoảng trống quan trọng?"}
    G -->|"Có"| H["Phân loại và ưu tiên khoảng trống"]
    H --> I["Làm rõ / chuẩn bị / tạo charter mới"]
    I --> C
    G -->|"Không"| J["Báo cáo phạm vi đã khảo sát<br/>và rủi ro còn lại"]
~~~

### 8.1. Trước phiên khám phá

- Xác định mục tiêu, charter và rủi ro.
- Chọn chiều coverage phù hợp.
- Chuẩn bị tài khoản, dữ liệu, môi trường và quyền.
- Xác định nguồn quan sát và cách lưu bằng chứng.
- Ghi các giả định và câu hỏi chưa có câu trả lời.

### 8.2. Trong phiên khám phá

- Ghi lại hành động, dữ liệu, trạng thái và kết quả đáng chú ý.
- Ghi giả thuyết, câu hỏi và thay đổi hướng khám phá.
- Lưu thông tin tái hiện lỗi: thời điểm, phiên bản, vai trò, request hoặc mã tham chiếu.
- Phân biệt phát hiện, nghi vấn và câu hỏi yêu cầu.
- Theo dõi charter có còn phù hợp với mục tiêu hay không.

### 8.3. Sau phiên khám phá

- Debrief kết quả với người liên quan khi cần.
- Cập nhật trạng thái coverage cho từng phạm vi.
- Ghi các điều kiện đã thử và giới hạn kết luận.
- Phân loại khoảng trống theo loại và mức ưu tiên.
- Tạo defect, câu hỏi, nhiệm vụ chuẩn bị hoặc charter tiếp theo.
- Liên kết phát hiện với yêu cầu, rủi ro và kiểm thử hồi quy nếu phù hợp.

## 9. Đo lường mà không tạo cảm giác coverage giả

### 9.1. Chỉ số hữu ích

Có thể theo dõi:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Phạm vi ưu tiên đã khảo sát | Tỷ lệ hoặc danh sách khu vực rủi ro cao đã có phiên khám phá với bằng chứng |
| Số khoảng trống quan trọng còn mở | Những điều kiện chưa thể xác nhận hoặc chưa được thử |
| Tỷ lệ khoảng trống được giải quyết | Khoảng trống đã có câu trả lời, bằng chứng hoặc quyết định được chấp nhận |
| Phát hiện theo loại rủi ro | Cho biết khám phá đang phát hiện vấn đề ở chức năng, dữ liệu, quyền, tích hợp hay môi trường |
| Khả năng tái lập finding | Mức độ đầy đủ của dữ liệu, bước và bằng chứng để người khác xác nhận |
| Thời gian từ phát hiện đến quyết định | Tốc độ làm rõ và xử lý vấn đề |
| Phạm vi cần khám phá lại | Các khu vực bị ảnh hưởng bởi thay đổi hoặc phát hiện mới |

### 9.2. Tránh dùng chỉ số sai cách

Không nên:

- Đánh giá hiệu suất người kiểm thử chỉ bằng số lỗi tìm được.
- Dùng số giờ khám phá làm đại diện cho coverage.
- Coi mọi ô đã chạm tới là đã được xác nhận.
- Coi không có finding là bằng chứng không có lỗi.
- So sánh tỷ lệ coverage giữa các tính năng có độ phức tạp và rủi ro khác nhau mà không xét ngữ cảnh.
- Ép đạt 100% mọi chiều coverage dù không có ý nghĩa hoặc không khả thi.

Chỉ số cần giúp quyết định nơi khám phá tiếp theo và nơi cần cải thiện khả năng quan sát. Nó không nên khuyến khích tạo thao tác hoặc ghi nhận hình thức.

### 9.3. Báo cáo coverage theo phạm vi và giới hạn

Một báo cáo hữu ích nên trả lời:

1. Mục tiêu và charter nào đã được thực hiện?
2. Phạm vi, vai trò, dữ liệu và môi trường nào đã được khảo sát?
3. Các phát hiện và rủi ro quan trọng là gì?
4. Những điều kiện nào đã được thử và chưa được thử?
5. Khoảng trống nào còn mở, vì sao và ai chịu trách nhiệm?
6. Cần khám phá hoặc kiểm thử bổ sung ở đâu?
7. Có giới hạn nào khiến kết quả không thể suy rộng?

Thay vì chỉ ghi “coverage 80%”, hãy nêu rõ 8 trong 10 hành trình ưu tiên đã được khảo sát, hai hành trình còn lại bị chặn do thiếu quyền, cùng danh sách rủi ro và hành động tiếp theo.

## 10. Ví dụ áp dụng: khám phá quy trình đặt lịch

### 10.1. Mục tiêu khám phá

Đánh giá các rủi ro trong hành trình đặt, thanh toán, tra cứu và hủy lịch, đặc biệt là tính nhất quán khi có thao tác đồng thời hoặc sự kiện đến trễ.

### 10.2. Các charter gợi ý

| Charter | Hướng khám phá | Bằng chứng |
| --- | --- | --- |
| Tìm khung giờ | Bộ lọc, timezone, khung giờ sát thời điểm hiện tại và dữ liệu hết chỗ | Request/response, kết quả hiển thị và dữ liệu thời gian |
| Đặt đồng thời | Hai người dùng xác nhận cùng tài nguyên và khung giờ | Kết quả của hai yêu cầu, trạng thái lịch và bất biến không đặt trùng |
| Thanh toán chưa rõ kết quả | Timeout, callback trễ, callback lặp và người dùng tải lại trang | Mã giao dịch, trạng thái lịch, trace và đối soát |
| Hủy lịch | Hủy sát ngưỡng, lịch đã hủy, hoàn tiền và vai trò khác nhau | Kết quả quyết định, trạng thái cuối và yêu cầu hoàn tiền |
| Truy cập dữ liệu | Tài khoản khác chủ sở hữu, tenant khác và vai trò quản trị | Response, audit event và dữ liệu không bị lộ |

### 10.3. Ma trận coverage sau một đợt khám phá

| Chiều | Đã khảo sát | Còn thiếu | Mức ưu tiên |
| --- | --- | --- | --- |
| Hành trình thành công | Tìm, đặt và thanh toán sandbox | Đổi lịch | Trung bình |
| Trạng thái | CREATED, PENDING, CONFIRMED | EXPIRED và callback đến trễ | Cao |
| Vai trò | Người dùng thường | Quản trị viên và tenant khác | Cao |
| Dữ liệu | Khung giờ còn trống, dữ liệu hợp lệ | Dữ liệu trùng và biên thời gian | Cao |
| Tích hợp | Thanh toán thành công | Timeout, retry và callback lặp | Rất cao |
| Môi trường | Desktop browser | Mobile browser và timezone khác | Trung bình |

### 10.4. Kết luận và hành động

Sau đợt khám phá, nhóm có thể kết luận rằng hành trình thành công đã được khảo sát trong môi trường sandbox với một vai trò và một nền tảng. Tuy nhiên, chưa đủ bằng chứng cho xử lý callback lặp, trạng thái hết hạn và quyền truy cập giữa tenant.

Hành động tiếp theo:

1. Làm rõ quy tắc xử lý callback đến sau khi khung giờ hết hạn.
2. Chuẩn bị hai tài khoản thuộc tenant khác nhau.
3. Tạo charter kiểm tra event lặp và retry.
4. Bổ sung khả năng truy vết trạng thái thanh toán và lịch bằng correlation ID nếu đang thiếu.
5. Chạy lại khám phá trên mobile nếu đây là nền tảng nằm trong phạm vi phát hành.

Kết luận này hữu ích hơn một con số tổng hợp vì nó chỉ rõ bằng chứng hiện có, giới hạn và quyết định cần thực hiện.

## 11. Mẫu ghi nhận phiên khám phá và khoảng trống

### 11.1. Mẫu charter

~~~text
ID / tên phiên:
Mục tiêu:
Hành trình / chức năng:
Rủi ro hoặc giả thuyết:

Phạm vi:
- Vai trò:
- Trạng thái:
- Dữ liệu:
- Nền tảng / môi trường:
- Phụ thuộc:

Hướng khám phá:
Điều kiện giới hạn:
Thời lượng dự kiến:
Oracle / nguồn quan sát:
Bằng chứng cần lưu:
~~~

### 11.2. Mẫu ghi chú phiên

~~~text
Thời điểm:
Người thực hiện:
Phiên bản / môi trường:
Charter:

Hành động:
Dữ liệu và điều kiện:
Quan sát:
Kết quả mong đợi:
Kết quả thực tế:

Finding / nghi vấn:
Mức độ chắc chắn:
Bằng chứng / mã tham chiếu:
Câu hỏi phát sinh:
Hướng tiếp theo:
~~~

### 11.3. Mẫu khoảng trống thông tin

~~~text
ID khoảng trống:
Phạm vi / rủi ro liên quan:
Loại: yêu cầu / quy tắc / oracle / dữ liệu / môi trường / quyền / quan sát
Câu hỏi hoặc điều chưa biết:
Vì sao cần thông tin này:
Tác động nếu chưa giải quyết:
Chủ sở hữu:
Bằng chứng hoặc quyết định cần có:
Mức ưu tiên:
Hành động tiếp theo:
Trạng thái:
~~~

### 11.4. Mẫu báo cáo coverage khám phá

~~~text
Phiên bản / build:
Mục tiêu đợt khám phá:
Khoảng thời gian:
Các charter đã thực hiện:

Phạm vi đã khảo sát:
- Hành trình:
- Vai trò:
- Trạng thái:
- Dữ liệu:
- Môi trường / nền tảng:
- Tích hợp:

Phát hiện quan trọng:
Rủi ro đã có bằng chứng:
Khoảng trống còn mở:
Phạm vi bị chặn và lý do:
Giới hạn kết luận:
Đề xuất phiên tiếp theo:
Người chịu trách nhiệm:
~~~

## 12. Checklist đánh giá mức bao phủ khám phá

- [ ] Mục tiêu khám phá gắn với hành trình, yêu cầu hoặc rủi ro cụ thể.
- [ ] Các chiều coverage được chọn theo cách sản phẩm có thể phát sinh lỗi.
- [ ] Phân biệt rõ chưa khảo sát, đã chạm tới, khảo sát một phần, khảo sát theo mục tiêu và bị chặn.
- [ ] Mỗi phiên có charter và điều kiện giới hạn.
- [ ] Hành động, dữ liệu, môi trường và quan sát được ghi lại đủ để hiểu kết quả.
- [ ] Phát hiện, nghi vấn và câu hỏi yêu cầu được phân loại riêng.
- [ ] Khoảng trống có mô tả cụ thể, tác động, chủ sở hữu và hành động tiếp theo.
- [ ] Mức ưu tiên phản ánh hậu quả và thiếu hụt bằng chứng.
- [ ] Có debrief và cập nhật bản đồ coverage sau phiên.
- [ ] Thay đổi sản phẩm hoặc phát hiện mới kích hoạt đánh giá lại phạm vi.
- [ ] Báo cáo nêu rõ điều đã thử, chưa thử và giới hạn kết luận.
- [ ] Chỉ số coverage không được dùng thay cho đánh giá chất lượng bằng chứng.

Đánh giá mức bao phủ khám phá có giá trị khi nó cho biết nhóm đã học được gì, đã khảo sát đến đâu và còn thiếu thông tin nào để ra quyết định. Bản đồ coverage, charter, ghi chú phiên và danh sách khoảng trống giúp hoạt động khám phá duy trì tính linh hoạt mà vẫn có trọng tâm, bằng chứng và khả năng truy vết.
