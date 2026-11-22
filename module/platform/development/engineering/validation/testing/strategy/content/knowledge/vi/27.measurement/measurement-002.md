# Theo dõi bao phủ yêu cầu, rủi ro và hành trình quan trọng

Một bộ kiểm thử có thể chạy hàng nghìn test và đạt tỷ lệ pass rất cao nhưng vẫn bỏ sót một yêu cầu quan trọng, một rủi ro nghiêm trọng hoặc một bước trong hành trình người dùng. Số lượng test và tỷ lệ pass chỉ cho biết một phần hoạt động kiểm thử; chúng không tự chứng minh rằng những điều cần bảo vệ đã được kiểm tra đầy đủ.

Để đánh giá mức độ bảo vệ của sản phẩm, nhóm cần theo dõi bao phủ trên ba góc nhìn liên kết với nhau: **yêu cầu cần đáp ứng, rủi ro cần kiểm soát và hành trình quan trọng cần hoàn thành**. Mỗi góc nhìn trả lời một câu hỏi khác nhau. Bao phủ yêu cầu cho biết điều gì đã được kiểm tra; bao phủ rủi ro cho biết các tình huống có thể gây thiệt hại đã được xử lý đến đâu; bao phủ hành trình cho biết người dùng có thể hoàn thành công việc xuyên qua các thành phần hay không.

Theo dõi ba góc nhìn cùng nhau giúp nhóm phát hiện khoảng trống trước phát hành, ưu tiên kiểm thử theo tác động và giải thích rõ phạm vi bằng chứng khi đưa ra quyết định chất lượng.

## 1. Ba góc nhìn bao phủ cần theo dõi

### 1.1. Bao phủ yêu cầu (requirements coverage)

Bao phủ yêu cầu đo mức độ các yêu cầu, tiêu chí chấp nhận hoặc quy tắc nghiệp vụ được liên kết với kiểm thử có bằng chứng phù hợp.

Ví dụ:

- Yêu cầu đăng nhập bằng mật khẩu hợp lệ được kiểm tra.
- Quy tắc khóa tài khoản sau nhiều lần đăng nhập sai được kiểm tra.
- Yêu cầu người dùng chỉ xem được đơn hàng thuộc tenant của mình được kiểm tra.
- Quy tắc tính phí vận chuyển tại đúng ngưỡng được kiểm tra.

Một yêu cầu được liên kết với test chưa chắc đã được kiểm tra thành công. Cần phân biệt có test được thiết kế, test đã thực thi, test đã đạt và bằng chứng còn hiệu lực.

### 1.2. Bao phủ rủi ro (risk coverage)

Bao phủ rủi ro cho biết các rủi ro đã nhận diện có biện pháp kiểm soát và bằng chứng kiểm thử phù hợp hay chưa.

Rủi ro có thể là:

- Người dùng không có quyền truy cập dữ liệu nhạy cảm.
- Giao dịch bị ghi nhận hai lần khi callback được gửi lặp.
- Hệ thống không xử lý được tải cao điểm.
- Dữ liệu bị mất khi migration thất bại.
- Dịch vụ thanh toán gián đoạn khiến đơn hàng rơi vào trạng thái không nhất quán.
- Người dùng không thể hoàn thành thao tác quan trọng bằng bàn phím hoặc công nghệ hỗ trợ.

Không phải mọi rủi ro đều có thể được bao phủ bằng một test case đơn lẻ. Một rủi ro có thể cần nhiều biện pháp: kiểm thử âm, phân tích bảo mật, kiểm thử tải, giám sát vận hành, backup/restore hoặc quy trình phục hồi.

### 1.3. Bao phủ hành trình quan trọng (critical journey coverage)

Bao phủ hành trình đo mức độ các luồng công việc có giá trị cao của người dùng hoặc hệ thống được kiểm tra từ đầu đến cuối, bao gồm các bước, chuyển trạng thái và điểm tích hợp quan trọng.

Ví dụ hành trình mua hàng:

1. Người dùng đăng nhập.
2. Tìm và xem sản phẩm.
3. Thêm sản phẩm vào giỏ.
4. Áp dụng ưu đãi.
5. Tạo đơn hàng.
6. Thanh toán.
7. Nhận xác nhận và theo dõi trạng thái đơn.

Một test riêng cho API tạo đơn không chứng minh toàn bộ hành trình mua hàng hoạt động. Hành trình có thể thất bại ở bước đăng nhập, cập nhật tồn kho, callback thanh toán hoặc gửi xác nhận.

### 1.4. Vì sao phải kết hợp cả ba?

| Góc nhìn | Câu hỏi chính | Khoảng trống có thể phát hiện |
|---|---|---|
| Yêu cầu | Các quy tắc và tiêu chí chấp nhận đã được kiểm tra chưa? | Yêu cầu chưa có test hoặc bằng chứng đã lỗi thời |
| Rủi ro | Những tình huống có hậu quả lớn đã được kiểm soát chưa? | Rủi ro nghiêm trọng chưa có biện pháp hoặc kiểm tra đủ mạnh |
| Hành trình | Người dùng và hệ thống có hoàn thành luồng quan trọng không? | Các bước riêng lẻ đạt nhưng tích hợp xuyên suốt thất bại |

Ba góc nhìn có liên hệ nhưng không thay thế nhau. Một yêu cầu có thể liên quan nhiều rủi ro; một rủi ro có thể ảnh hưởng nhiều hành trình; một hành trình có thể thực hiện nhiều yêu cầu. Cần giữ các mối liên kết này để phân tích tác động khi yêu cầu hoặc kiến trúc thay đổi.

## 2. Phân biệt bao phủ với các chỉ số kiểm thử khác

Không nên đồng nhất bao phủ yêu cầu với code coverage hoặc tỷ lệ test pass.

| Chỉ số | Đo điều gì? | Không chứng minh điều gì? |
|---|---|---|
| Requirements coverage | Yêu cầu có được liên kết với kiểm thử và bằng chứng không? | Mã nguồn đã thực thi hết mọi nhánh hay chưa |
| Risk coverage | Rủi ro có biện pháp kiểm soát và bằng chứng phù hợp không? | Rủi ro đã biến mất hoàn toàn |
| Journey coverage | Các hành trình và bước quan trọng có được xác minh không? | Mọi biến thể người dùng đều hoạt động |
| Code/line coverage | Dòng hoặc câu lệnh nào được thực thi? | Kết quả nghiệp vụ có được assertion đúng hay không |
| Branch coverage | Các nhánh quyết định nào đã được đi qua? | Tất cả yêu cầu và rủi ro đã được kiểm tra |
| Test pass rate | Tỷ lệ lần chạy test đạt trong một phạm vi và thời điểm | Phạm vi test có đầy đủ hoặc test có đúng không |
| Defect escape rate | Lỗi được phát hiện sau một điểm kiểm soát hoặc trong production | Toàn bộ rủi ro chưa phát hiện đã được biết |

Ví dụ, line coverage đạt 95% vẫn có thể bỏ sót yêu cầu phân quyền cho tenant. Test pass rate 100% cũng có thể chỉ phản ánh một suite nhỏ không bao gồm hành trình thanh toán. Vì vậy, báo cáo cần đặt chỉ số bao phủ trong bối cảnh mục tiêu và phạm vi.

## 3. Xây dựng mô hình truy vết

Để theo dõi bao phủ, nhóm cần một mô hình liên kết giữa yêu cầu, rủi ro, hành trình, test và bằng chứng.

### 3.1. Các thực thể cần quản lý

| Thực thể | Nội dung |
|---|---|
| Requirement | Mã yêu cầu, mô tả, phiên bản, tiêu chí chấp nhận và owner |
| Risk | Mã rủi ro, nguyên nhân, tình huống, tác động, khả năng và mức ưu tiên |
| Journey | Mã hành trình, người dùng/tác nhân, mục tiêu và mức độ quan trọng |
| Journey step | Bước, trạng thái trước/sau, thành phần và điều kiện chuyển tiếp |
| Test case | Mã test, mục tiêu, dữ liệu, tiền điều kiện và kết quả mong đợi |
| Test run | Lần chạy, build, môi trường, dữ liệu, thời gian và kết quả |
| Evidence | Báo cáo, log, trace, ảnh, metric hoặc biên bản kiểm tra |
| Defect | Lỗi liên quan, mức độ, trạng thái và test hồi quy |
| Release | Phiên bản được đánh giá và tập bằng chứng dùng cho quyết định |

Mỗi thực thể nên có định danh ổn định. Không dùng tên hiển thị làm khóa duy nhất vì tên có thể thay đổi hoặc trùng nhau.

### 3.2. Quan hệ truy vết

Một mô hình đơn giản:

~~~mermaid
flowchart TD
    R["Yêu cầu"]
    K["Rủi ro"]
    J["Hành trình"]
    T["Test case"]
    X["Test run"]
    E["Bằng chứng"]
    D["Defect"]
    L["Release"]
    R --> T
    R --> K
    R --> J
    K --> T
    J --> T
    T --> X --> E
    X --> D
    E --> L
~~~

Một test case có thể liên kết nhiều yêu cầu, rủi ro hoặc hành trình nếu thực sự kiểm tra các mục tiêu đó. Tuy nhiên, không nên gắn test vào quá nhiều mục chỉ để làm tỷ lệ bao phủ tăng. Mỗi liên kết cần có lý do và tiêu chí xác minh rõ ràng.

### 3.3. Truy vết hai chiều

- **Forward traceability:** từ yêu cầu hoặc rủi ro đi đến test, lần chạy và bằng chứng. Dùng để xác định mục tiêu nào chưa được kiểm tra.
- **Backward traceability:** từ test hoặc bằng chứng quay về yêu cầu, rủi ro hoặc hành trình được bảo vệ. Dùng để phát hiện test không còn mục tiêu, test trùng lặp hoặc test không có căn cứ.

Truy vết hai chiều đặc biệt hữu ích khi yêu cầu thay đổi, một test bị xóa hoặc một lỗi production cần được liên kết với khoảng trống kiểm thử.

## 4. Xác định phạm vi và chất lượng dữ liệu truy vết

### 4.1. Xác định nguồn yêu cầu

Yêu cầu có thể đến từ:

- Tài liệu nghiệp vụ và user story.
- Tiêu chí chấp nhận của feature.
- API contract và schema.
- Yêu cầu phi chức năng và SLO.
- Chính sách bảo mật, quyền riêng tư và tuân thủ.
- Quy tắc dữ liệu, migration và vận hành.
- Cam kết với khách hàng hoặc nhà cung cấp.

Nhóm cần thống nhất nguồn nào là bản có thẩm quyền, cách quản lý phiên bản và ai có quyền thay đổi. Nếu có nhiều nguồn mâu thuẫn, phải giải quyết trước khi tính bao phủ.

### 4.2. Chia yêu cầu thành đơn vị có thể kiểm chứng

Một yêu cầu quá lớn như "hệ thống phải an toàn" không thể truy vết hiệu quả. Hãy phân rã thành tiêu chí có thể xác minh:

- Người dùng không có quyền không thể đọc tài nguyên của tenant khác.
- Token hết hạn bị từ chối.
- Callback thanh toán trùng không tạo thêm giao dịch.
- 95% request tìm kiếm hoàn tất trong ngưỡng latency ở workload xác định.
- Người dùng có thể hoàn thành đăng nhập bằng bàn phím.

Mỗi đơn vị cần có điều kiện, kết quả mong đợi và phạm vi áp dụng. Không phân rã quá nhỏ đến mức mỗi chi tiết triển khai trở thành một yêu cầu riêng không có giá trị nghiệp vụ.

### 4.3. Xác định yêu cầu ngoài phạm vi

Một số yêu cầu có thể không áp dụng cho một module hoặc release. Ghi rõ trạng thái Not Applicable (N/A), lý do, phạm vi và người xác nhận. Không loại một yêu cầu khỏi mẫu số chỉ vì chưa có test.

### 4.4. Quản lý thay đổi

Khi yêu cầu thay đổi:

1. Tạo hoặc cập nhật định danh và phiên bản yêu cầu.
2. Xác định rủi ro và hành trình bị ảnh hưởng.
3. Đánh giá test hiện tại có còn đúng không.
4. Thêm, sửa hoặc loại liên kết có căn cứ.
5. Chạy lại các kiểm tra liên quan.
6. Cập nhật báo cáo cho release đang xét.

Không dùng bằng chứng của phiên bản cũ để chứng minh phiên bản mới đã được kiểm tra nếu chưa đánh giá tác động.

## 5. Theo dõi bao phủ yêu cầu

### 5.1. Ma trận truy vết yêu cầu

Ma trận truy vết yêu cầu (Requirements Traceability Matrix — RTM) thể hiện mối quan hệ giữa yêu cầu và test.

| Requirement ID | Tiêu chí | Test liên kết | Trạng thái bằng chứng | Ghi chú |
|---|---|---|---|---|
| REQ-LOGIN-01 | Đăng nhập bằng thông tin hợp lệ | TC-LOGIN-01 | Passed | Build và run đã ghi |
| REQ-LOGIN-02 | Từ chối mật khẩu sai | TC-LOGIN-02 | Passed | Có kiểm tra thông báo |
| REQ-AUTH-03 | Không truy cập tenant khác | TC-AUTH-08, TC-AUTH-09 | Not Run | Chưa chạy kiểm thử âm |
| REQ-ORDER-04 | Không tạo đơn trùng khi retry | TC-ORDER-12 | Failed | Cần điều tra idempotency |

Đây là ví dụ minh họa. Một ma trận thực tế nên liên kết đến hệ thống quản lý yêu cầu, test management, CI và kho bằng chứng thay vì sao chép thủ công nhiều nơi.

### 5.2. Trạng thái bao phủ

Nên tách trạng thái thiết kế và trạng thái thực thi:

| Trạng thái | Ý nghĩa |
|---|---|
| Unmapped | Chưa có test liên kết |
| Planned | Đã xác định cách kiểm tra nhưng chưa hoàn tất test |
| Implemented | Test đã được xây dựng và review |
| Executed | Test đã chạy, chưa xét kết quả |
| Passed | Test chạy đạt trên phiên bản và môi trường được xác định |
| Failed | Test chạy và phát hiện sai lệch |
| Blocked | Không thể chạy vì môi trường, dữ liệu hoặc phụ thuộc |
| Not Applicable | Có lý do được xác nhận là không áp dụng |
| Deprecated | Yêu cầu hoặc test đã bị thay thế, không còn dùng cho phạm vi hiện tại |

Trạng thái "Implemented" không đồng nghĩa "Passed". Một test được viết nhưng chưa chạy không phải bằng chứng thực thi. Một test pass ở build trước cũng không tự động chứng minh build hiện tại đạt.

### 5.3. Công thức bao phủ yêu cầu

Có thể tính tỷ lệ yêu cầu có ít nhất một test được liên kết:

\[
\text{Mapped Requirement Coverage} =
\frac{\text{Số yêu cầu trong phạm vi có test hợp lệ}}
{\text{Tổng số yêu cầu áp dụng trong phạm vi}}
\times 100\%
\]

Chỉ số này đo mức độ thiết kế truy vết, chưa đo việc test đã chạy hoặc đạt.

Một chỉ số khác đo tỷ lệ yêu cầu có bằng chứng thực thi đạt:

\[
\text{Passed Requirement Coverage} =
\frac{\text{Số yêu cầu có bằng chứng test đạt còn hiệu lực}}
{\text{Tổng số yêu cầu áp dụng trong phạm vi}}
\times 100\%
\]

Khi một yêu cầu cần nhiều test để kiểm tra các điều kiện khác nhau, cần định nghĩa quy tắc hoàn thành. Ví dụ, yêu cầu phân quyền có thể cần test cho vai trò được phép, vai trò bị từ chối, tenant khác và trạng thái tài nguyên. Chỉ một test pass không nhất thiết đủ.

### 5.4. Tránh đếm trùng

Một test có thể liên kết nhiều yêu cầu, nhưng không nên cộng số liên kết để tính số yêu cầu đã bao phủ. Đơn vị của mẫu số phải là requirement ID duy nhất trong baseline. Nếu một yêu cầu được kiểm tra bởi nhiều test, yêu cầu chỉ được tính một lần khi đã đáp ứng quy tắc bằng chứng đã thống nhất.

## 6. Theo dõi bao phủ rủi ro

### 6.1. Tạo risk register phục vụ kiểm thử

Mỗi rủi ro cần có:

- Risk ID và mô tả tình huống.
- Tài sản, người dùng hoặc quy trình bị ảnh hưởng.
- Nguyên nhân và điều kiện kích hoạt.
- Khả năng xảy ra và mức tác động.
- Mức ưu tiên hoặc phân loại rủi ro.
- Biện pháp phòng ngừa, phát hiện và phục hồi.
- Test hoặc hoạt động xác minh.
- Owner, trạng thái và rủi ro còn lại.

Ví dụ:

| Risk ID | Tình huống | Mức ưu tiên | Biện pháp kiểm soát | Bằng chứng |
|---|---|---|---|---|
| R-AUTH-01 | Người dùng đọc dữ liệu tenant khác | Critical | Authorization test, negative test, audit | TC-AUTH-08/09 |
| R-PAY-02 | Callback lặp tạo giao dịch trùng | High | Idempotency test, reconciliation | TC-PAY-12, report |
| R-PERF-03 | Tìm kiếm quá chậm giờ cao điểm | High | Load test và SLO monitoring | PERF-SEARCH-01 |
| R-DATA-04 | Migration làm mất lịch sử đơn | High | Migration rehearsal, backup/restore | MIG-ORDER-03 |

### 6.2. Đánh giá mức độ bao phủ rủi ro

Không chỉ hỏi rủi ro có test hay không. Hãy đánh giá:

- Có biện pháp phòng ngừa hay không?
- Có test kích hoạt tình huống gây lỗi không?
- Có xác minh kết quả và bất biến quan trọng không?
- Có kiểm tra phát hiện và cảnh báo không?
- Có phương án phục hồi hoặc giảm tác động không?
- Bằng chứng có mới và áp dụng đúng phiên bản không?

Có thể dùng trạng thái:

- **Covered:** có biện pháp và bằng chứng phù hợp với mức rủi ro.
- **Partially covered:** có một phần kiểm soát nhưng còn thiếu tình huống hoặc bằng chứng.
- **Uncovered:** chưa có kiểm soát hoặc kiểm tra đủ căn cứ.
- **Accepted:** rủi ro còn lại được người có thẩm quyền chấp nhận theo quy trình.
- **Not applicable:** đã xác nhận rủi ro không áp dụng trong phạm vi cụ thể.

Trạng thái Accepted không nên được tính như Covered. Nó thể hiện quyết định quản trị rủi ro, không phải bằng chứng rằng kiểm soát đã hoạt động.

### 6.3. Ưu tiên theo mức độ rủi ro

Rủi ro nghiêm trọng cần nhiều bằng chứng hơn rủi ro thấp. Có thể dùng điểm ưu tiên dựa trên xác suất và tác động:

\[
\text{Risk Priority} = \text{Likelihood} \times \text{Impact}
\]

Nếu tổ chức có thang điểm chính thức, sử dụng thang đó. Điểm số hỗ trợ sắp xếp ưu tiên; không thay thế đánh giá chuyên môn, nghĩa vụ tuân thủ hoặc tiêu chí chặn.

### 6.4. Bao phủ có trọng số rủi ro

Một chỉ số tổng hợp có thể phản ánh tầm quan trọng khác nhau của từng rủi ro:

\[
\text{Risk-weighted Coverage} =
\frac{\sum_i w_i c_i}{\sum_i w_i}
\times 100\%
\]

Trong đó:

- \(w_i\) là trọng số của rủi ro \(i\), được xác định theo mức ưu tiên.
- \(c_i\) là mức bao phủ của rủi ro, có thể là 1 khi covered, một giá trị quy ước cho partially covered và 0 khi uncovered.

Nếu dùng giá trị phân số cho partially covered, cần định nghĩa tiêu chí rõ ràng để tránh chấm điểm chủ quan. Rủi ro Critical chưa được kiểm soát vẫn cần hiển thị riêng, dù điểm tổng cao.

## 7. Theo dõi bao phủ hành trình quan trọng

### 7.1. Xác định hành trình nào là quan trọng

Hành trình có thể được ưu tiên theo:

- Giá trị đối với người dùng hoặc doanh nghiệp.
- Tần suất sử dụng và số người bị ảnh hưởng.
- Tác động nếu thất bại.
- Mức độ phức tạp và số điểm tích hợp.
- Mức độ nhạy cảm của dữ liệu hoặc giao dịch.
- Nghĩa vụ hợp đồng hoặc tuân thủ.
- Lịch sử lỗi và sự cố.

Ví dụ: đăng nhập, đăng ký, tìm kiếm, mua hàng, thanh toán, hoàn tiền, quản lý quyền, xuất dữ liệu hoặc khôi phục tài khoản.

### 7.2. Phân rã hành trình

Với mỗi hành trình, ghi:

- Journey ID, mục tiêu và persona/tác nhân.
- Điều kiện bắt đầu và kết thúc.
- Các bước và trạng thái trung gian.
- Thành phần hoặc dịch vụ tham gia.
- Dữ liệu và quyền cần thiết.
- Nhánh thành công, nhánh lỗi và tình huống biên.
- Điểm tích hợp và phụ thuộc bên ngoài.
- Tiêu chí hoàn thành và kết quả mong đợi.

Không chỉ mô tả đường đi thành công. Các hành trình quan trọng thường cần kiểm tra timeout, retry, hết hạn phiên, dữ liệu không hợp lệ, quyền bị từ chối và phục hồi sau gián đoạn.

### 7.3. Bao phủ bước và chuyển trạng thái

Một hành trình có thể có đủ test cho từng bước riêng lẻ nhưng vẫn thất bại khi nối các bước. Vì vậy cần theo dõi:

- Bước đã có kiểm thử.
- Chuyển trạng thái đã được xác minh.
- Tích hợp giữa hai bước liên tiếp.
- Nhánh lỗi và cách phục hồi.
- Tính nhất quán dữ liệu xuyên suốt hành trình.
- Hành trình đã chạy từ đầu đến cuối trên phiên bản hiện tại.

Ví dụ, kiểm tra "tạo đơn thành công" và "gửi email thành công" riêng rẽ không chứng minh rằng sau khi thanh toán được xác nhận, đơn hàng chuyển đúng trạng thái và email chỉ được gửi một lần.

### 7.4. Công thức bao phủ hành trình

Một cách tính đơn giản:

\[
\text{Journey Coverage} =
\frac{\text{Số hành trình quan trọng có bằng chứng E2E đạt}}
{\text{Tổng số hành trình quan trọng áp dụng}}
\times 100\%
\]

Để phân tích sâu hơn, có thể tính bao phủ bước:

\[
\text{Step Coverage} =
\frac{\text{Số bước quan trọng có test và bằng chứng hợp lệ}}
{\text{Tổng số bước quan trọng áp dụng}}
\times 100\%
\]

Hai chỉ số này không thay thế nhau. Một hành trình chỉ được tính E2E covered khi đường đi và tiêu chí kết thúc đã được xác minh theo quy tắc. Step coverage cao vẫn có thể che giấu lỗi ở chuyển trạng thái hoặc tích hợp.

## 8. Kết hợp ba góc nhìn trong một ma trận

Ma trận kết hợp giúp nhìn thấy một test đang bảo vệ yêu cầu nào, rủi ro nào và hành trình nào.

Ví dụ cho một cửa hàng trực tuyến:

| Requirement | Risk | Journey | Test/evidence | Trạng thái |
|---|---|---|---|---|
| REQ-AUTH-01: chỉ chủ tài khoản xem giỏ | R-AUTH-01: lộ dữ liệu giữa tenant | J-CART-01: xem và cập nhật giỏ | TC-CART-08, run 245 | Passed |
| REQ-ORDER-02: không tạo đơn trùng | R-PAY-02: callback lặp | J-CHECKOUT-01: thanh toán | TC-PAY-12, run 246 | Failed |
| REQ-SEARCH-03: tìm kiếm trong ngưỡng | R-PERF-03: latency giờ cao điểm | J-SEARCH-01: tìm sản phẩm | PERF-SEARCH-01, run 220 | Passed |
| REQ-DATA-04: giữ lịch sử đơn sau migration | R-DATA-04: mất dữ liệu | J-ORDER-HISTORY-01 | MIG-ORDER-03 | Blocked |

Từ ma trận này, nhóm có thể thấy:

- Một test thất bại ảnh hưởng đồng thời yêu cầu, rủi ro và hành trình nào.
- Một rủi ro chưa có test có thể liên quan đến nhiều yêu cầu.
- Một hành trình quan trọng còn thiếu bằng chứng ở bước hoặc điểm tích hợp nào.
- Một thay đổi yêu cầu cần chạy lại test và hành trình nào.

Ma trận cần được tạo từ dữ liệu có cấu trúc hoặc liên kết giữa các hệ thống, tránh nhập lại thủ công nhiều lần gây sai lệch.

## 9. Đánh giá chất lượng bằng chứng

Không phải liên kết test nào cũng là bằng chứng đủ mạnh. Khi tính bao phủ, cần đánh giá chất lượng và tính hiện hành của bằng chứng.

### 9.1. Các thuộc tính của bằng chứng

- **Liên quan:** kiểm tra đúng yêu cầu, rủi ro hoặc hành trình.
- **Đủ điều kiện:** dữ liệu, môi trường và cấu hình phù hợp.
- **Có kết quả:** có trạng thái pass/fail/blocked rõ ràng.
- **Có thể truy vết:** liên kết với test ID, run ID, build và release.
- **Có thể tái lập:** lưu dữ liệu, bước chạy và cấu hình cần thiết.
- **Còn hiệu lực:** phù hợp với phiên bản yêu cầu và hệ thống đang đánh giá.
- **Đáng tin:** không bị nhiễu bởi flaky test, lỗi môi trường hoặc thao tác thủ công thiếu kiểm soát.

### 9.2. Độ mới của bằng chứng

Bằng chứng có thể trở nên lỗi thời khi:

- Yêu cầu hoặc tiêu chí chấp nhận thay đổi.
- Mã nguồn hoặc cấu hình thay đổi.
- API hoặc dependency được nâng phiên bản.
- Dataset thay đổi đáng kể.
- Môi trường test không còn đại diện.
- Một lỗi production cho thấy test hiện tại chưa kiểm tra đúng tình huống.

Nên định nghĩa điều kiện cần chạy lại test theo loại thay đổi. Không phải mọi commit đều cần chạy lại toàn bộ test, nhưng một bằng chứng cũ không được mặc định còn hiệu lực khi đối tượng kiểm tra đã thay đổi đáng kể.

### 9.3. Bằng chứng thủ công và tự động

Bằng chứng thủ công có thể phù hợp với usability study, review thiết kế, kiểm tra thiết bị hoặc đánh giá chuyên gia. Cần lưu người thực hiện, ngày, phiên bản, điều kiện, kịch bản, quan sát và kết luận.

Bằng chứng tự động cần lưu cấu hình, test run, log và artifact. Tự động hóa không tự làm bằng chứng đáng tin nếu test không có assertion đúng, dữ liệu không đại diện hoặc môi trường sai.

## 10. Xây dựng dashboard bao phủ

Dashboard nên giúp người ra quyết định nhìn thấy khoảng trống và hành động cần làm, không chỉ hiển thị một tỷ lệ tổng.

### 10.1. Các chỉ số gợi ý

| Nhóm | Chỉ số | Cách sử dụng |
|---|---|---|
| Yêu cầu | Mapped requirement coverage | Tìm yêu cầu chưa có test |
| Yêu cầu | Passed requirement coverage | Xác định yêu cầu có bằng chứng đạt |
| Rủi ro | Risk-weighted coverage | Ưu tiên khoảng trống có tác động cao |
| Rủi ro | Số Critical/High uncovered | Làm rõ rủi ro chặn phát hành |
| Hành trình | Critical journey E2E coverage | Xác định hành trình chưa được xác minh xuyên suốt |
| Hành trình | Step/transition coverage | Tìm bước hoặc chuyển trạng thái bị bỏ sót |
| Bằng chứng | Evidence freshness | Tìm kết quả đã lỗi thời |
| Thực thi | Passed/failed/blocked test theo build | Đánh giá tình trạng lần chạy hiện tại |
| Quản trị | Số ngoại lệ và thời gian tồn tại | Theo dõi rủi ro được chấp nhận |
| Chất lượng | Defect escape theo yêu cầu/rủi ro/hành trình | Tìm điểm yếu trong chiến lược |

### 10.2. Bộ lọc cần có

- Release, build, branch hoặc phiên bản.
- Module, dịch vụ và thành phần.
- Mức ưu tiên hoặc mức rủi ro.
- Nhóm người dùng hoặc hành trình.
- Loại kiểm thử và môi trường.
- Owner và trạng thái bằng chứng.
- Thời gian chạy và độ mới.

Người xem cần có khả năng đi từ số tổng đến danh sách requirement, risk, journey, test và bằng chứng cụ thể.

### 10.3. Ví dụ biểu diễn

<table>
  <table-row>
    <table-cell width="34%">
      **Bao phủ yêu cầu có bằng chứng đạt**
      <title size="2xl" color="success" tabularNums>86%</title>
      <text color="secondary" size="xs">Ví dụ minh họa</text>
    </table-cell>
    <table-cell width="33%">
      **Rủi ro Critical chưa bao phủ**
      <title size="2xl" color="danger" tabularNums>2</title>
      <text color="secondary" size="xs">Cần xử lý trước release</text>
    </table-cell>
    <table-cell width="33%">
      **Hành trình quan trọng E2E đạt**
      <title size="2xl" tabularNums>4/5</title>
      <text color="secondary" size="xs">Một hành trình còn thiếu</text>
    </table-cell>
  </table-row>
</table>

Các con số minh họa cho thấy một tỷ lệ tổng tương đối cao vẫn có thể đi cùng khoảng trống nghiêm trọng. Dashboard cần làm nổi bật rủi ro Critical chưa bao phủ và hành trình quan trọng chưa được xác minh, thay vì chỉ nhấn mạnh phần trăm trung bình.

## 11. Phân tích khoảng trống và ưu tiên hành động

Khi thấy khoảng trống, không nên lập tức tạo thêm test. Trước tiên cần hiểu nguyên nhân:

- Yêu cầu chưa đủ rõ hoặc chưa có tiêu chí chấp nhận.
- Rủi ro chưa được nhận diện hoặc chưa có owner.
- Hành trình chưa được mô tả đầy đủ.
- Test chưa được thiết kế hoặc chưa được triển khai.
- Test có nhưng chưa chạy do môi trường hoặc dữ liệu.
- Test chạy nhưng thất bại.
- Bằng chứng cũ không còn phù hợp.
- Test liên kết sai mục tiêu hoặc không có assertion cần thiết.
- Rủi ro được chấp nhận nhưng chưa có biện pháp bù trừ.

### 11.1. Ưu tiên theo tác động

Có thể ưu tiên theo thứ tự:

1. Rủi ro Critical/High chưa có kiểm soát hoặc bằng chứng.
2. Hành trình có tác động trực tiếp đến giao dịch hoặc dữ liệu quan trọng chưa được xác minh.
3. Yêu cầu bắt buộc hoặc yêu cầu tuân thủ chưa có bằng chứng.
4. Test thất bại hoặc bị blocked trong phạm vi release.
5. Bằng chứng đã lỗi thời sau thay đổi.
6. Khoảng trống có tác động thấp hơn hoặc có thể xử lý trong chu kỳ tiếp theo.

Thứ tự cụ thể phải dựa trên chính sách rủi ro và quyết định release của tổ chức. Một yêu cầu pháp lý hoặc bảo mật bắt buộc có thể là điều kiện chặn bất kể điểm ưu tiên tổng.

### 11.2. Chọn hành động phù hợp

| Nguyên nhân | Hành động |
|---|---|
| Yêu cầu mơ hồ | Làm rõ với product/nghiệp vụ và cập nhật tiêu chí |
| Rủi ro chưa có kiểm soát | Threat/risk review, thiết kế biện pháp và test |
| Hành trình thiếu bước | Bổ sung mô hình journey và test chuyển trạng thái |
| Chưa có test | Thiết kế test theo rủi ro và tiêu chí chấp nhận |
| Test bị blocked | Sửa môi trường, dữ liệu hoặc phụ thuộc |
| Test thất bại | Tạo defect, điều tra nguyên nhân và xác minh bản sửa |
| Bằng chứng lỗi thời | Chạy lại test hoặc đánh giá tác động thay đổi |
| Liên kết sai | Sửa traceability và review lại mục tiêu test |
| Rủi ro được chấp nhận | Kiểm tra thời hạn, approver, mitigation và điều kiện đóng |

## 12. Ví dụ tổng hợp: cửa hàng trực tuyến

Giả sử một release thay đổi quy trình checkout, cập nhật tồn kho và tích hợp nhà cung cấp thanh toán. Nhóm xác định ba hành trình quan trọng:

- J-01: tìm kiếm và xem sản phẩm.
- J-02: tạo đơn và thanh toán.
- J-03: xem trạng thái và lịch sử đơn.

Các yêu cầu chính gồm quyền truy cập đơn hàng, tính đúng giá, không tạo giao dịch trùng, cập nhật tồn kho và hiển thị trạng thái chính xác. Các rủi ro chính gồm lộ dữ liệu tenant, callback lặp, overselling, timeout nhà cung cấp và mất lịch sử khi migration.

### 12.1. Liên kết yêu cầu, rủi ro và hành trình

| Yêu cầu | Rủi ro | Hành trình | Bằng chứng cần có |
|---|---|---|---|
| REQ-01: chỉ chủ đơn xem đơn | R-01: lộ dữ liệu | J-03 | Negative authorization test và audit |
| REQ-02: tổng tiền chính xác | R-02: tính sai giá/ưu đãi | J-02 | Boundary test và API/E2E |
| REQ-03: callback xử lý một lần | R-03: giao dịch trùng | J-02 | Retry/idempotency test |
| REQ-04: tồn kho không âm | R-04: overselling | J-02 | Concurrent purchase test |
| REQ-05: lịch sử không mất sau migration | R-05: mất dữ liệu | J-03 | Migration rehearsal và reconciliation |
| REQ-06: tìm kiếm đáp ứng SLO | R-06: latency cao điểm | J-01 | Load test với dataset đại diện |

### 12.2. Đọc kết quả

Giả sử:

- Tất cả yêu cầu đã có test liên kết.
- Một test callback lặp thất bại.
- Test concurrent purchase chưa chạy vì môi trường thiếu dữ liệu tồn kho.
- Hai hành trình J-01 và J-03 có E2E đạt; J-02 chưa đạt.
- Một rủi ro Critical về dữ liệu tenant đã có test nhưng bằng chứng thuộc build trước.

Mapped requirement coverage có thể là 100%, nhưng điều đó không có nghĩa release đã sẵn sàng. Passed requirement coverage thấp hơn vì test callback thất bại và một số bằng chứng không còn hiệu lực. Risk coverage còn khoảng trống ở test cạnh tranh tồn kho và bằng chứng phân quyền cũ. Journey coverage cũng chưa đầy đủ vì checkout chưa đạt E2E.

Nhóm cần ưu tiên sửa idempotency, chuẩn bị dữ liệu và chạy concurrent purchase test, đồng thời xác minh lại phân quyền trên build hiện tại. Dashboard phải thể hiện các trạng thái này rõ ràng để người ra quyết định không hiểu nhầm tỷ lệ đã ánh xạ là tỷ lệ chất lượng đạt.

## 13. Quản trị và trách nhiệm

Theo dõi bao phủ cần sự phối hợp giữa nhiều vai trò:

| Vai trò | Trách nhiệm |
|---|---|
| Product owner | Xác nhận yêu cầu, tiêu chí chấp nhận và mức quan trọng của hành trình |
| Risk/security owner | Nhận diện, đánh giá và theo dõi rủi ro |
| QA/test lead | Xây dựng mô hình bao phủ, kiểm tra liên kết và báo cáo khoảng trống |
| Developer/engineering | Duy trì test, xác minh kỹ thuật và liên kết với thay đổi mã |
| Performance/SRE | Cung cấp SLO, workload, metric và bằng chứng vận hành |
| UX/accessibility | Xác định nhóm người dùng, hành trình và tiêu chí trải nghiệm |
| Release manager | Xem xét bằng chứng, ngoại lệ và readiness |
| Tool/process owner | Duy trì hệ thống truy vết, dashboard và chất lượng dữ liệu |

Mỗi yêu cầu, rủi ro và hành trình quan trọng cần có owner. QA có thể điều phối đo lường nhưng không thể tự xác nhận thay product, security, performance hoặc UX đối với những quyết định thuộc chuyên môn của họ.

## 14. Nhịp rà soát bao phủ

Không nên chỉ cập nhật ma trận vào cuối dự án. Có thể tổ chức các nhịp:

- **Khi refinement:** kiểm tra yêu cầu mới đã có tiêu chí, rủi ro và hành trình liên quan.
- **Khi phát triển:** cập nhật liên kết test và trạng thái triển khai.
- **Khi PR:** xác minh test liên quan và tác động lên truy vết.
- **Sau tích hợp:** cập nhật bằng chứng chạy trên bản dựng tích hợp.
- **Trước phát hành:** rà soát khoảng trống yêu cầu, rủi ro và hành trình.
- **Sau production incident:** cập nhật risk register, test và mô hình bao phủ.
- **Định kỳ:** loại liên kết lỗi thời, test trùng và yêu cầu không còn áp dụng.

Tần suất cần phù hợp với tốc độ thay đổi. Hệ thống có nhiều release mỗi ngày cần cập nhật tự động theo build; hệ thống phát hành theo chu kỳ dài có thể có buổi rà soát chính thức trước release.

## 15. Những sai lầm thường gặp

- **Chỉ đo số lượng test:** không cho biết test bảo vệ yêu cầu hoặc rủi ro nào.
- **Coi có liên kết là đã bao phủ:** một test được gắn vào requirement nhưng chưa chạy hoặc không có assertion phù hợp.
- **Đồng nhất pass rate với coverage:** suite có thể pass nhưng phạm vi rất hẹp.
- **Bỏ qua rủi ro Critical:** điểm bao phủ tổng cao che giấu một khoảng trống nghiêm trọng.
- **Chỉ kiểm tra từng bước của hành trình:** bỏ sót lỗi tích hợp, chuyển trạng thái và tính nhất quán.
- **Tính test trùng nhiều lần:** làm tỷ lệ bao phủ cao giả tạo.
- **Không quản lý phiên bản yêu cầu:** dùng bằng chứng cũ cho tiêu chí đã thay đổi.
- **Xem Accepted là Covered:** nhầm quyết định chấp nhận rủi ro với bằng chứng kiểm soát.
- **Không phân biệt Blocked và Failed:** không xác định được cần sửa sản phẩm hay môi trường.
- **Chỉ duy trì ma trận thủ công:** dữ liệu nhanh chóng lỗi thời và không khớp với CI.
- **Tối ưu dashboard theo phần trăm:** khiến nhóm ưu tiên tăng số liên kết thay vì giảm rủi ro thực.
- **Không liên kết lỗi production với truy vết:** bỏ lỡ cơ hội cải thiện chiến lược kiểm thử.

## 16. Checklist theo dõi bao phủ

- [ ] Có baseline yêu cầu và định danh ổn định.
- [ ] Yêu cầu được phân rã thành tiêu chí có thể kiểm chứng.
- [ ] Rủi ro có mô tả, mức ưu tiên, owner và biện pháp kiểm soát.
- [ ] Hành trình quan trọng có mục tiêu, bước, trạng thái và nhánh lỗi.
- [ ] Test được liên kết với yêu cầu, rủi ro hoặc hành trình có lý do.
- [ ] Có truy vết hai chiều từ mục tiêu đến test và từ test về mục tiêu.
- [ ] Trạng thái mapped, implemented, executed, passed, failed và blocked được phân biệt.
- [ ] Công thức và mẫu số bao phủ được định nghĩa rõ.
- [ ] N/A và Accepted có lý do, owner và phê duyệt phù hợp.
- [ ] Bằng chứng gắn với build, môi trường, dữ liệu và phiên bản.
- [ ] Bằng chứng lỗi thời được nhận diện sau thay đổi.
- [ ] Rủi ro Critical/High chưa bao phủ được hiển thị riêng.
- [ ] Hành trình có kiểm tra bước, chuyển trạng thái và E2E.
- [ ] Dashboard cho phép drill-down đến test và bằng chứng.
- [ ] Khoảng trống có owner, hành động và thời hạn.
- [ ] Lỗi production được phản hồi vào risk register và test suite.

## 17. Quy trình duy trì mô hình bao phủ

~~~mermaid
flowchart TD
    A["Xác lập baseline yêu cầu"]
    B["Nhận diện và ưu tiên rủi ro"]
    C["Xác định hành trình quan trọng"]
    D["Liên kết yêu cầu, rủi ro, journey và test"]
    E["Thực thi test và thu thập bằng chứng"]
    F["Cập nhật trạng thái và độ mới"]
    G["Tổng hợp dashboard và tìm khoảng trống"]
    H{"Có khoảng trống quan trọng?"}
    I["Ưu tiên hành động theo tác động"]
    J["Khắc phục, bổ sung test hoặc xác minh lại"]
    K["Đánh giá readiness và lưu kết quả release"]
    L["Phản hồi từ production và thay đổi yêu cầu"]
    A --> B --> C --> D --> E --> F --> G --> H
    H -->|Có| I --> J --> E
    H -->|Không| K --> L
    L -. "Cập nhật baseline" .-> A
~~~

Theo dõi bao phủ yêu cầu, rủi ro và hành trình quan trọng giúp nhóm hiểu rõ phần nào của sản phẩm đã có bằng chứng và phần nào vẫn còn bất định. Khi mô hình truy vết hai chiều được duy trì, trạng thái thực thi được phân biệt rõ, bằng chứng gắn với phiên bản và khoảng trống được ưu tiên theo tác động, số liệu bao phủ sẽ hỗ trợ quyết định chất lượng thực tế thay vì chỉ tạo ra một tỷ lệ đẹp trên dashboard.
