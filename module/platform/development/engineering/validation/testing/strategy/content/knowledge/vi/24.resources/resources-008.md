# Dành năng lực cho kiểm tra lại, hồi quy và thay đổi đột xuất

**Chương:** Nguồn lực  
**Phạm vi module:** `VALIDATION_TESTING_STRATEGY`

Nhóm kiểm thử thường phải xử lý đồng thời nhiều loại công việc: kiểm tra lại lỗi sau khi được sửa, chạy hồi quy để phát hiện ảnh hưởng ngoài dự kiến, xác minh thay đổi mới và phản ứng với sự cố hoặc yêu cầu phát sinh. Nếu toàn bộ năng lực đã được phân bổ cho kế hoạch kiểm thử ban đầu, nhóm sẽ khó tiếp nhận công việc đột xuất. Nếu giữ quá nhiều thời gian trống để chờ phát sinh, năng lực có thể bị sử dụng kém hiệu quả.

Dành năng lực là hoạt động lập kế hoạch và điều chỉnh thời gian, con người, môi trường, dữ liệu và công cụ để các hoạt động kiểm thử quan trọng có thể được thực hiện đúng thời điểm. Việc phân bổ cần tính đến tính không chắc chắn của lỗi, số vòng sửa và kiểm tra lại, phạm vi hồi quy, mức độ thay đổi trong chu kỳ và các công việc ngoài kế hoạch.

Bài học này trình bày cách phân biệt các loại công việc, ước lượng tải kiểm thử, xây dựng phần dự phòng, ưu tiên theo rủi ro, điều phối nhân lực và môi trường, cũng như điều chỉnh kế hoạch khi có thay đổi đột xuất. Mục tiêu là giúp nhóm duy trì khả năng kiểm tra có chất lượng mà vẫn đáp ứng tiến độ và nghĩa vụ phát hành.

Sau bài học, người học có thể:

- Phân biệt kiểm tra lại (retesting), kiểm thử hồi quy và kiểm thử thay đổi mới.
- Ước lượng năng lực thực tế sau khi trừ các hoạt động không trực tiếp tạo test execution.
- Dự báo công sức cho retest, regression và xử lý thay đổi đột xuất.
- Dành phần dự phòng dựa trên dữ liệu lịch sử và mức độ bất định.
- Ưu tiên công việc theo rủi ro, tác động, thời hạn và phụ thuộc.
- Điều phối nhân lực, môi trường, dữ liệu và chuyên gia hỗ trợ.
- Theo dõi tải, WIP, thời gian chờ và mức sử dụng dự phòng.
- Điều chỉnh kế hoạch minh bạch khi phát sinh công việc ngoài dự kiến.

## 1. Ba nhóm công việc cần được bảo đảm năng lực

Các nhóm công việc có mục tiêu và đặc điểm khác nhau. Nếu gộp tất cả vào một con số “giờ kiểm thử”, nhóm sẽ khó dự báo và khó giải thích vì sao kế hoạch bị quá tải.

### 1.1. Kiểm tra lại sau khi sửa lỗi (retesting)

Retesting xác minh một lỗi cụ thể đã được sửa và hành vi gây lỗi không còn xuất hiện trong điều kiện đã xác định. Công việc thường gồm:

- Đọc lại báo cáo lỗi và điều kiện tái hiện.
- Xác nhận bản sửa đã được triển khai vào đúng build/môi trường.
- Chuẩn bị dữ liệu và trạng thái cần thiết.
- Chạy lại ca đã thất bại hoặc ca tái hiện lỗi.
- Kiểm tra bằng chứng và xác nhận kết quả.
- Mở lại lỗi nếu vấn đề vẫn tồn tại hoặc phát sinh sai lệch khác.

Một lỗi có thể cần nhiều vòng retest nếu bản sửa chưa hoàn chỉnh, môi trường chưa sẵn sàng hoặc lỗi chỉ xuất hiện trong một cấu hình cụ thể. Vì vậy, không nên dự toán retest bằng cách giả định mỗi lỗi chỉ cần chạy lại đúng một lần.

### 1.2. Kiểm thử hồi quy (regression testing)

Regression xác minh thay đổi không làm hỏng hành vi đã hoạt động trước đó. Phạm vi có thể bao gồm:

- Các chức năng trực tiếp liên quan đến vùng thay đổi.
- Thành phần phụ thuộc và consumer của API/event đã sửa.
- Luồng nghiệp vụ có sử dụng dữ liệu hoặc logic dùng chung.
- Ca kiểm thử gắn với rủi ro cao và lỗi lịch sử.
- Bộ smoke hoặc release gate bắt buộc.

Regression có thể chạy ở nhiều tầng: unit, integration, API, system và E2E. Mỗi tầng có chi phí, thời gian và độ bao phủ khác nhau. Kế hoạch cần xác định rõ tập hồi quy nào phải chạy cho mỗi loại thay đổi.

### 1.3. Thay đổi và công việc đột xuất

Thay đổi đột xuất là công việc không được dự kiến đầy đủ trong kế hoạch ban đầu nhưng cần được xem xét trong chu kỳ hiện tại. Ví dụ:

- Bản sửa nóng cho lỗi nghiêm trọng.
- Thay đổi yêu cầu hoặc cấu hình sát thời điểm phát hành.
- Nâng cấp thư viện, chứng thư hoặc endpoint đối tác.
- Phát hiện lỗi mới trong UAT hoặc production.
- Yêu cầu kiểm tra thêm do rủi ro hoặc kết quả kiểm toán.
- Môi trường kiểm thử bị gián đoạn và cần xác minh lại sau phục hồi.

Không phải mọi yêu cầu đột xuất đều phải chen vào ngay lập tức. Nhóm cần đánh giá mức khẩn cấp, tác động nếu trì hoãn, công sức và công việc nào sẽ bị ảnh hưởng khi tiếp nhận.

### 1.4. Phân biệt mục tiêu và đầu ra

| Công việc | Câu hỏi chính | Đầu ra |
|---|---|---|
| Retesting | Lỗi cụ thể đã được sửa chưa? | Kết quả tái hiện, bằng chứng và trạng thái lỗi |
| Regression | Thay đổi có làm hỏng hành vi liên quan khác không? | Phạm vi hồi quy đã chạy, kết quả và rủi ro còn lại |
| Kiểm tra thay đổi mới | Hành vi mới đáp ứng yêu cầu và không tạo rủi ro không chấp nhận được không? | Bằng chứng xác minh yêu cầu mới và tác động liên quan |
| Công việc đột xuất | Rủi ro mới cần phản ứng thế nào và ảnh hưởng kế hoạch ra sao? | Quyết định ưu tiên, phạm vi kiểm tra và kế hoạch điều chỉnh |

Retesting thành công không thay thế regression. Một lỗi có thể được sửa đúng tại vị trí tái hiện nhưng bản sửa vẫn ảnh hưởng đến luồng khác.

## 2. Xác định năng lực thực tế của nhóm

Tổng số giờ làm việc theo lịch không phải toàn bộ thời gian có thể dành cho kiểm thử. Nhóm còn họp, lập kế hoạch, review, hỗ trợ phát triển, xử lý môi trường, đào tạo và nghỉ phép.

### 2.1. Tính năng lực khả dụng

Một mô hình đơn giản:

\[
\text{Năng lực khả dụng} = \text{Tổng giờ theo lịch} - \text{Giờ vắng mặt} - \text{Giờ hoạt động chung}
\]

Ví dụ, nhóm có 5 người, mỗi người có 40 giờ làm việc trong tuần:

- Tổng giờ theo lịch: \(5 \times 40 = 200\) giờ.
- Nghỉ phép, ngày nghỉ hoặc thời gian không sẵn sàng: 16 giờ.
- Họp, planning, review, hỗ trợ chung và đào tạo: 34 giờ.

Năng lực còn lại cho công việc chuyên môn là:

\[
200 - 16 - 34 = 150\text{ giờ}
\]

Con số 150 giờ vẫn cần được phân bổ cho thiết kế test, chuẩn bị dữ liệu, thực thi, phân tích kết quả, retest, regression và các hoạt động khác. Không nên coi toàn bộ là thời gian chạy test.

### 2.2. Tách thời gian thực thi và thời gian xử lý kết quả

Một ca kiểm thử có thể chạy tự động trong vài phút nhưng vẫn cần người xem kết quả, xác minh log và phân loại thất bại. Với kiểm thử thủ công, thời gian thao tác có thể nhỏ hơn thời gian chuẩn bị và ghi nhận.

Khi ước lượng, nên tách:

- Chuẩn bị môi trường và dữ liệu.
- Đọc yêu cầu, phân tích thay đổi và thiết kế phạm vi.
- Thực thi test và quan sát hành vi.
- Phân tích thất bại, thu thập bằng chứng và báo cáo.
- Retest sau sửa lỗi.
- Regression bổ sung hoặc mở rộng.
- Điều phối, trao đổi và cập nhật trạng thái.

Việc tách các loại thời gian giúp nhận ra điểm nghẽn. Nếu phần lớn năng lực dành cho điều tra lỗi môi trường, tăng số người chạy test có thể không giải quyết được vấn đề.

### 2.3. Dùng dữ liệu thực tế để hiệu chỉnh

Ước lượng ban đầu nên được cập nhật từ dữ liệu của các chu kỳ trước:

- Số lỗi được chuyển sang kiểm thử mỗi tuần.
- Số vòng retest trung bình theo loại lỗi.
- Tỷ lệ bản sửa không đạt lần đầu.
- Thời gian regression theo phạm vi và tầng.
- Số thay đổi đột xuất và công sức xử lý.
- Thời gian chờ build, môi trường, dữ liệu hoặc người hỗ trợ.
- Số giờ phân tích flaky test và lỗi không tái hiện.

Không nên dùng một tỷ lệ cố định cho mọi dự án. Hệ thống mới, hệ thống tích hợp nhiều đối tác và sản phẩm ổn định lâu năm có mức bất định khác nhau.

## 3. Dự báo tải retesting

Retesting thường có thể ước lượng từ số lỗi dự kiến được sửa, mức độ phức tạp, số cấu hình cần xác minh và xác suất phải kiểm tra lại nhiều vòng.

### 3.1. Ước lượng theo loại lỗi

Phân loại lỗi theo đặc tính ảnh hưởng đến công sức:

| Loại lỗi | Công việc retest thường cần |
|---|---|
| Lỗi giao diện đơn giản | Tái hiện thao tác, xác minh màn hình và trình duyệt liên quan |
| Lỗi quy tắc nghiệp vụ | Kiểm tra dữ liệu, điều kiện biên và kết quả tính toán |
| Lỗi API/hợp đồng | Xác minh request/response, mã lỗi, quyền và consumer |
| Lỗi dữ liệu/transaction | Chuẩn bị dữ liệu, xác minh lưu/đọc lại và trạng thái sau lỗi |
| Lỗi concurrency/bất đồng bộ | Tạo điều kiện cạnh tranh, kiểm tra nhiều lần và phân tích trace |
| Lỗi bảo mật/phân quyền | Chuẩn bị danh tính/role, xác minh quyền được phép và bị từ chối |
| Lỗi môi trường/triển khai | Kiểm tra cấu hình, readiness, health check và luồng sau phục hồi |

Loại lỗi chỉ là cơ sở ước lượng. Phạm vi thật còn phụ thuộc mức nghiêm trọng, số nền tảng và chất lượng bằng chứng từ người sửa.

### 3.2. Tính đến số vòng retest

Nếu một lỗi thường cần nhiều hơn một lần kiểm tra, có thể ước lượng công sức kỳ vọng:

\[
E(H_{retest}) = N_{defect} \times H_{per\ round} \times E(Rounds)
\]

Trong đó:

- \(N_{defect}\): số lỗi dự kiến cần retest.
- \(H_{per\ round}\): giờ trung bình cho một vòng kiểm tra.
- \(E(Rounds)\): số vòng trung bình kỳ vọng, lấy từ dữ liệu lịch sử.

Ví dụ, nhóm dự kiến nhận 18 lỗi, mỗi vòng retest tốn trung bình 0,75 giờ và lịch sử cho thấy trung bình 1,4 vòng mỗi lỗi:

\[
18 \times 0,75 \times 1,4 = 18,9\text{ giờ}
\]

Đây là giá trị kỳ vọng để lập kế hoạch, không có nghĩa mỗi lỗi chắc chắn cần 1,4 lần. Một số lỗi đạt ngay, một số cần nhiều vòng. Với lỗi rủi ro cao, cần có dự phòng riêng thay vì chỉ dựa trên trung bình.

### 3.3. Tránh tính trùng retest và regression

Một ca tái hiện lỗi có thể đồng thời là một phần của regression suite. Khi lập kế hoạch, cần phân biệt mục tiêu và ghi nhận thời gian một lần thực thi ở đâu để không cộng hai lần. Tuy nhiên, nếu sau retest cần chạy thêm tập hồi quy rộng hơn, phần công sức bổ sung phải được tính riêng.

### 3.4. Yêu cầu đầu vào để retest hiệu quả

Người sửa lỗi nên cung cấp:

- Build hoặc commit chứa bản sửa.
- Mô tả nguyên nhân và thay đổi chính.
- Điều kiện tái hiện ban đầu.
- Dữ liệu, cấu hình hoặc feature flag liên quan.
- Kết quả mong đợi sau sửa.
- Rủi ro phụ hoặc thành phần có thể bị ảnh hưởng.

Thiếu thông tin có thể làm tăng thời gian điều tra. Nhóm nên ghi nhận thời gian chờ và yêu cầu bổ sung thay vì âm thầm tính toàn bộ vào thời gian thực thi test.

## 4. Dự báo tải regression

Regression phụ thuộc vào phạm vi thay đổi, mức rủi ro, số tầng kiểm thử và thời gian chạy. Một thay đổi nhỏ ở thư viện dùng chung có thể cần phạm vi rộng; một thay đổi lớn nhưng cô lập có thể cần tập kiểm tra tập trung.

### 4.1. Phân tầng tập hồi quy

Có thể tổ chức thành các nhóm:

- **Smoke:** xác nhận hệ thống khởi động và các luồng tối thiểu hoạt động.
- **Fast regression:** unit, API và integration test có phản hồi nhanh.
- **Risk-focused regression:** ca liên quan vùng thay đổi, rủi ro cao và lỗi lịch sử.
- **Full regression:** phạm vi rộng trên các luồng, vai trò, cấu hình và tích hợp.
- **Specialized regression:** hiệu năng, bảo mật, phục hồi, tương thích hoặc các kiểm tra chuyên biệt.

Mỗi nhóm cần có tiêu chí vào, thời gian dự kiến, môi trường và người chịu trách nhiệm. Không nên chỉ dựa vào tên suite mà không đo thời gian và phạm vi thật.

### 4.2. Ước lượng theo thành phần

Với mỗi thay đổi, xác định:

1. Thành phần được sửa trực tiếp.
2. Thành phần gọi hoặc được gọi bởi phần thay đổi.
3. Dữ liệu, schema, event và API có liên quan.
4. Luồng nghiệp vụ sử dụng các thành phần đó.
5. Lỗi lịch sử hoặc rủi ro nghiêm trọng trong vùng tác động.
6. Các ca bắt buộc theo chính sách phát hành.

Sau đó, ước lượng công sức theo từng tầng. Ví dụ, 30 phút chạy unit suite không đồng nghĩa tổng công sức regression chỉ là 30 phút nếu cần chuẩn bị môi trường tích hợp và phân tích kết quả E2E.

### 4.3. Tính chi phí của regression tự động

Với test tự động, cần tính:

- Thời gian runner thực thi.
- Chi phí môi trường và dịch vụ.
- Thời gian theo dõi, phân loại kết quả và xử lý flaky test.
- Thời gian chuẩn bị dữ liệu và cleanup.
- Thời gian phân tích thất bại và retest.

Không quy đổi toàn bộ thời gian máy chạy thành giờ nhân lực. Nhưng nếu runner hoặc môi trường là tài nguyên khan hiếm, thời gian sử dụng vẫn cần được tính trong kế hoạch năng lực.

### 4.4. Xác định phạm vi bắt buộc và phạm vi có thể điều chỉnh

Một số kiểm tra cần luôn chạy trước phát hành, ví dụ kiểm tra bảo mật hoặc tính toàn vẹn dữ liệu có hậu quả nghiêm trọng. Phần còn lại có thể được chọn theo vùng thay đổi và lịch sử lỗi.

Nếu cần thu hẹp regression vì thời gian, phải ghi rõ:

- Ca nào đã chạy.
- Ca nào bị hoãn hoặc bỏ qua.
- Lý do và bằng chứng cho quyết định.
- Rủi ro còn lại.
- Người có thẩm quyền chấp nhận rủi ro.

Không báo cáo “regression passed” nếu chỉ chạy một tập con mà không nêu phạm vi.

## 5. Dành năng lực cho thay đổi đột xuất

Thay đổi đột xuất khó dự báo chính xác. Cách quản lý phù hợp là dùng dữ liệu lịch sử, dành một phần năng lực có giới hạn và có quy tắc tiếp nhận rõ ràng.

### 5.1. Phân loại mức khẩn cấp

Có thể phân loại:

| Mức | Đặc điểm | Ví dụ phản ứng |
|---|---|---|
| P0 - Khẩn cấp | Sự cố nghiêm trọng, rủi ro an toàn/dữ liệu/tài chính hoặc phát hành bị chặn | Tổ chức phản ứng ngay, xác định kiểm tra tối thiểu bắt buộc và người quyết định |
| P1 - Cao | Lỗi ảnh hưởng luồng chính hoặc thay đổi bắt buộc trong chu kỳ | Đánh giá trong ngày, điều chỉnh kế hoạch và phân bổ người phù hợp |
| P2 - Bình thường | Yêu cầu mới có tác động giới hạn, có thể sắp xếp trong chu kỳ | Xếp vào backlog và xử lý theo năng lực còn lại |
| P3 - Thấp | Cải tiến hoặc yêu cầu chưa có thời hạn gần | Đưa vào kế hoạch kế tiếp hoặc khi có năng lực |

Tên mức và thời gian phản ứng cần được thống nhất với quy trình của tổ chức. Không nên tự động coi mọi yêu cầu đến từ quản lý hoặc khách hàng là P0.

### 5.2. Dành phần dự phòng (capacity buffer)

Buffer là năng lực chưa phân bổ cứng cho kế hoạch thông thường, được giữ để xử lý biến động đã biết là có thể xảy ra. Buffer có thể được tính theo giờ, tỷ lệ năng lực hoặc một số ngày công.

Ví dụ, nhóm có 150 giờ khả dụng mỗi tuần và dựa trên dữ liệu trước đó dành 15% cho việc đột xuất:

\[
150 \times 15\% = 22,5\text{ giờ dự phòng}
\]

Phần năng lực có thể lập kế hoạch trước là:

\[
150 - 22,5 = 127,5\text{ giờ}
\]

Tỷ lệ 15% chỉ là ví dụ. Nhóm cần hiệu chỉnh theo mức biến động, giai đoạn phát hành, số lỗi trung bình, mức trưởng thành của sản phẩm và lịch sử công việc khẩn cấp.

### 5.3. Dùng dữ liệu để đặt buffer

Có thể xem xét:

- Tổng giờ công đột xuất trong các chu kỳ gần đây.
- Tỷ lệ thời gian dành cho retest ngoài dự kiến.
- Số lỗi nghiêm trọng xuất hiện sau khi code freeze.
- Mức độ thay đổi yêu cầu và tích hợp đối tác.
- Độ biến động giữa các tuần, không chỉ giá trị trung bình.
- Giai đoạn hiện tại: đầu sprint, trước release hay sau triển khai.

Nếu tải đột xuất thường tập trung trước release, buffer có thể được phân bổ khác giữa đầu và cuối chu kỳ. Một tỷ lệ cố định cho cả dự án có thể không phản ánh đúng thời điểm rủi ro.

### 5.4. Buffer không phải thời gian nhàn rỗi

Khi không có yêu cầu khẩn cấp, nhóm có thể dùng phần dự phòng cho công việc có thể tạm dừng hoặc tạo giá trị dài hạn:

- Rà soát và cải thiện dữ liệu test.
- Giảm flaky test hoặc rút ngắn suite.
- Bổ sung test cho lỗi lịch sử.
- Tự động hóa kiểm tra lặp lại.
- Cập nhật tài liệu, môi trường và runbook.
- Kiểm tra chất lượng báo cáo và khả năng truy vết.

Những công việc này nên được chọn sao cho có thể tạm dừng khi buffer được kích hoạt. Không nên dùng toàn bộ buffer cho nhiệm vụ có cam kết thời hạn cứng rồi vẫn coi đó là năng lực dự phòng.

## 6. Xây dựng mô hình phân bổ năng lực

Sau khi xác định năng lực khả dụng, nhóm phân chia theo các loại công việc và rà soát định kỳ.

### 6.1. Phân bổ theo danh mục công việc

Một cấu trúc tham khảo:

| Danh mục | Mục đích | Cách ước lượng |
|---|---|---|
| Kiểm thử thay đổi theo kế hoạch | Xác minh tính năng mới và yêu cầu đã cam kết | Story, task, test design và effort dự kiến |
| Retesting | Xác minh lỗi sau sửa | Số lỗi × thời gian mỗi vòng × số vòng kỳ vọng |
| Regression | Xác minh không phát sinh lỗi liên quan | Phạm vi thay đổi × suite × thời gian xử lý kết quả |
| Công việc đột xuất | Sự cố, hotfix, thay đổi khẩn | Buffer dựa trên lịch sử và mức bất định |
| Cải thiện chất lượng | Giảm flaky, dữ liệu, framework và tài liệu | Phần năng lực có thể tạm dừng hoặc mục tiêu riêng |

Không có tỷ lệ chuẩn cho mọi nhóm. Phân bổ phải dựa trên dữ liệu, mức rủi ro và mục tiêu chu kỳ.

### 6.2. Ví dụ phân bổ theo tuần

Giả sử năng lực khả dụng sau khi trừ hoạt động chung là 150 giờ. Nhóm quyết định lập kế hoạch như sau:

| Danh mục | Giờ dự kiến | Tỷ lệ |
|---|---:|---:|
| Kiểm thử thay đổi theo kế hoạch | 72 | 48% |
| Retesting | 24 | 16% |
| Regression | 24 | 16% |
| Buffer cho công việc đột xuất | 22,5 | 15% |
| Cải thiện chất lượng có thể tạm dừng | 7,5 | 5% |
| **Tổng** | **150** | **100%** |

Đây là kế hoạch minh họa. Khi công việc đột xuất không dùng hết buffer, nhóm có thể chuyển phần còn lại sang cải thiện chất lượng hoặc backlog đã sẵn sàng. Khi buffer không đủ, cần đánh giá lại phạm vi và thời hạn thay vì âm thầm kéo dài giờ làm.

### 6.3. Lập kế hoạch theo vai trò và kỹ năng

Tổng số giờ có thể đủ nhưng nhóm vẫn thiếu năng lực nếu chỉ một người hiểu kiểm thử bảo mật, migration hoặc tích hợp đối tác. Cần phân bổ theo kỹ năng:

- Người thiết kế và phân tích kiểm thử.
- Người kiểm thử API, tích hợp và dữ liệu.
- Người kiểm thử UI/E2E hoặc thiết bị.
- Người phụ trách tự động hóa và pipeline.
- Chuyên gia nghiệp vụ hoặc người phê duyệt kết quả.
- Người vận hành môi trường và dịch vụ phụ thuộc.

Không nên giả định mọi thành viên có thể thay thế nhau hoàn toàn. Kế hoạch cần xác định người dự phòng, chia sẻ kiến thức và thời gian hỗ trợ từ nhóm khác.

### 6.4. Phân bổ năng lực môi trường và công cụ

Năng lực không chỉ là giờ con người. Một nhóm có thể bị chặn bởi:

- Số runner hoặc thiết bị kiểm thử.
- Môi trường tích hợp dùng chung.
- Tài khoản sandbox và quota API.
- Dữ liệu lớn hoặc thời gian reset database.
- Cổng triển khai và cửa sổ bảo trì.
- Chứng thư, quyền truy cập hoặc người phê duyệt.

Khi lập kế hoạch, xác định thời gian đặt môi trường, thời gian chờ và thời gian cleanup. Nếu hai nhóm cần cùng một môi trường, phải có lịch và cơ chế ưu tiên.

## 7. Ước lượng công sức tổng hợp

Một mô hình dự báo có thể kết hợp công việc kế hoạch, retest, regression và buffer:

\[
H_{total} = H_{planned} + H_{retest} + H_{regression} + H_{unplanned} + H_{coordination}
\]

Trong đó các hạng mục phải được định nghĩa để tránh tính trùng. Nếu (H_{planned}) đã bao gồm regression, không cộng lại cùng giờ vào (H_{regression}). Tương tự, buffer là phần năng lực được giữ lại, còn (H_{unplanned}) là công việc thực tế sử dụng buffer; không cộng cả hai như hai loại nhu cầu độc lập.

### 7.1. Ví dụ dự báo một chu kỳ

Giả sử nhóm có 150 giờ khả dụng:

- Kiểm thử thay đổi theo kế hoạch: 70 giờ.
- Retest dự kiến: 18 giờ.
- Regression theo phạm vi hiện tại: 28 giờ.
- Điều phối, phân tích và báo cáo chưa được tính trong các mục trên: 8 giờ.
- Buffer cho việc đột xuất: 20 giờ.

Tổng phân bổ:

\[
70 + 18 + 28 + 8 + 20 = 144\text{ giờ}
\]

Nhóm còn 6 giờ linh hoạt. Nếu phát sinh hotfix cần thêm 12 giờ, có thể dùng 12 giờ từ buffer và còn 8 giờ dự phòng. Nếu có thêm một yêu cầu 15 giờ, tổng nhu cầu vượt năng lực. Nhóm cần thương lượng phạm vi, thời hạn hoặc hỗ trợ nguồn lực.

### 7.2. Dùng khoảng ước lượng

Với công việc bất định, có thể lập ba mức:

- **Lạc quan:** bản sửa rõ, dữ liệu sẵn sàng, test ổn định và không có lỗi mới.
- **Cơ sở:** có một vòng điều tra hoặc retest bổ sung.
- **Thận trọng:** nhiều vòng sửa, phạm vi hồi quy mở rộng hoặc môi trường bị gián đoạn.

Ví dụ retest 20 lỗi có thể cần 12–18 giờ ở kịch bản cơ sở và 25–30 giờ nếu nhiều lỗi không tái hiện hoặc cần nhiều cấu hình. Khoảng này giúp người quản lý hiểu rủi ro lịch trình.

### 7.3. Ước lượng theo throughput lịch sử

Nếu nhóm đã có dữ liệu ổn định, có thể dùng số lượng lỗi xử lý, số story hoàn tất hoặc giờ kiểm thử trung bình theo tuần để dự báo. Tuy nhiên, throughput chỉ có ý nghĩa khi định nghĩa công việc và điều kiện tương đối nhất quán.

Không dùng số ca test hoàn tất làm thước đo năng suất độc lập. Một ca đơn giản và một ca cần thiết lập nhiều hệ thống không có cùng công sức hoặc giá trị.

## 8. Ưu tiên khi năng lực không đủ

Khi nhu cầu vượt năng lực, nhóm cần ra quyết định dựa trên rủi ro và tác động. Không nên giải quyết bằng cách chia đều thời gian cho mọi yêu cầu.

### 8.1. Các tiêu chí ưu tiên

- Mức độ nghiêm trọng nếu lỗi lọt.
- Khả năng xảy ra hoặc tái diễn.
- Phạm vi người dùng, dữ liệu và hệ thống ảnh hưởng.
- Mức liên quan đến thay đổi hiện tại.
- Thời hạn phát hành hoặc nghĩa vụ hợp đồng.
- Khả năng phát hiện lỗi sớm bằng ca đang xét.
- Công sức, thời gian và phụ thuộc môi trường.
- Có phương án kiểm soát tạm thời hoặc kiểm tra thay thế không.

### 8.2. Ma trận quyết định

| Tình huống | Hướng xử lý |
|---|---|
| Lỗi nghiêm trọng, bản sửa ảnh hưởng giao dịch hoặc dữ liệu | Ưu tiên retest và regression liên quan trước khi phát hành |
| Thay đổi nhỏ, rủi ro thấp, có thể rollback | Chọn tập kiểm tra tập trung và ghi phạm vi còn lại |
| Lỗi bảo mật hoặc quyền truy cập | Giữ kiểm tra bắt buộc và yêu cầu người có thẩm quyền đánh giá |
| Môi trường không sẵn sàng | Ghi blocked, xử lý phụ thuộc và điều chỉnh lịch; không đánh dấu đạt |
| Yêu cầu mới không khẩn cấp | Đưa vào backlog và lập lịch theo năng lực |
| Nhiều công việc P0 cùng lúc | Kích hoạt cơ chế điều phối khẩn cấp và thương lượng phạm vi/nguồn lực |

### 8.3. Quy tắc không được hy sinh

Không nên bỏ qua các kiểm tra bảo vệ dữ liệu, quyền truy cập, an toàn hoặc yêu cầu bắt buộc chỉ để đạt một mốc thời gian. Nếu không thể hoàn tất, cần ghi nhận rủi ro và chuyển quyết định chấp nhận rủi ro cho đúng người có thẩm quyền.

### 8.4. Thu hẹp phạm vi có kiểm soát

Khi phải giảm phạm vi regression:

1. Giữ test bắt buộc và luồng rủi ro cao.
2. Giữ test trực tiếp vùng thay đổi và phụ thuộc gần.
3. Giữ ca liên quan lỗi lịch sử có cùng nguyên nhân.
4. Chuyển các ca ít liên quan sang bộ hồi quy mở rộng hoặc lịch chạy kế tiếp.
5. Ghi rõ ca chưa chạy và lý do.
6. Xác định người chấp nhận rủi ro và thời điểm hoàn tất phần còn lại.

Thu hẹp phạm vi là quyết định quản trị rủi ro, không phải cách thay đổi định nghĩa “đạt”.

## 9. Quản lý WIP và luồng công việc

WIP (Work in Progress) là số công việc đang được xử lý cùng lúc. Nếu mỗi người nhận quá nhiều lỗi, test case hoặc yêu cầu thay đổi, công việc có thể bị chuyển đổi ngữ cảnh liên tục và kéo dài thời gian hoàn tất.

### 9.1. Giới hạn công việc đang làm

Nhóm có thể đặt giới hạn WIP theo vai trò hoặc loại công việc. Ví dụ, mỗi người chỉ điều tra một lỗi phức tạp tại một thời điểm, trong khi một nhóm nhỏ phụ trách retest nhanh.

Giới hạn WIP giúp:

- Giảm chuyển đổi ngữ cảnh.
- Làm rõ điểm nghẽn.
- Tăng khả năng hoàn tất công việc đã bắt đầu.
- Giúp công việc khẩn cấp được tiếp nhận có chủ đích.
- Tránh mở quá nhiều test đang chờ môi trường hoặc dữ liệu.

Giới hạn WIP cần được điều chỉnh theo tính chất công việc. Không nên dùng một con số cứng cho mọi nhóm.

### 9.2. Trạng thái công việc rõ ràng

Một luồng đơn giản có thể gồm:

`Ready → In progress → Waiting for build/environment → Executing → Analyzing → Done`

Với lỗi, có thể thêm trạng thái `Awaiting fix` hoặc `Ready for retest`. Mỗi trạng thái cần có định nghĩa để phân biệt công việc đang tiêu tốn nhân lực với công việc đang chờ phụ thuộc.

### 9.3. Theo dõi thời gian chờ

Thời gian chờ build, môi trường, dữ liệu hoặc phản hồi của người phát triển có thể chiếm phần lớn lead time. Ghi nhận thời gian chờ giúp nhóm tìm nguyên nhân thay vì chỉ tăng số giờ thực thi.

Nếu tester chờ một build nhiều giờ, có thể cải thiện quy trình bàn giao hoặc build pipeline. Nếu môi trường dùng chung gây xếp hàng, cần điều phối lịch hoặc tăng khả năng môi trường.

### 9.4. Giữ buffer có người điều phối

Một phần dự phòng nên có người hoặc vai trò chịu trách nhiệm điều phối. Nếu mọi người tự lấy buffer cho các yêu cầu riêng, nhóm có thể không còn khả năng phản ứng với sự cố thật.

## 10. Điều phối giữa các vai trò và nhóm

Retest và regression thường cần phối hợp giữa kiểm thử, phát triển, vận hành, sản phẩm và chuyên gia nghiệp vụ.

### 10.1. Trách nhiệm của các bên

| Vai trò | Trách nhiệm liên quan đến năng lực |
|---|---|
| Test lead/QA lead | Dự báo tải, phân bổ, ưu tiên, theo dõi rủi ro và báo cáo thiếu năng lực |
| Tester | Ước lượng, thực thi, thu thập bằng chứng và cập nhật trạng thái |
| Developer | Cung cấp build, nguyên nhân sửa, dữ liệu và hỗ trợ điều tra |
| Product owner/BA | Làm rõ mức ưu tiên nghiệp vụ và tiêu chí chấp nhận |
| DevOps/SRE | Bảo đảm runner, môi trường, quyền và quan sát vận hành |
| Security/data specialist | Hỗ trợ kiểm tra chuyên môn và đánh giá rủi ro đặc thù |
| Release manager | Điều phối cổng phát hành và quyết định theo thẩm quyền |

### 10.2. Thỏa thuận thời gian bàn giao bản sửa

Retest chỉ bắt đầu hiệu quả khi có build đúng, mô tả bản sửa và môi trường sẵn sàng. Nhóm có thể thống nhất:

- Thông tin tối thiểu khi chuyển lỗi sang `Ready for retest`.
- Cách thông báo build chứa bản sửa.
- Thời gian phản hồi mục tiêu theo mức ưu tiên.
- Cơ chế báo khi bản sửa chưa triển khai đúng môi trường.
- Người hỗ trợ nếu lỗi không tái hiện hoặc cần log bổ sung.

### 10.3. Tránh phụ thuộc vào một cá nhân

Nếu chỉ một người có thể kiểm tra một hệ thống hoặc thiết bị, năng lực thực tế thấp hơn tổng giờ của nhóm. Cần chia sẻ runbook, dữ liệu, quyền cần thiết và đào tạo chéo. Với kiểm thử chuyên môn, có thể đặt lịch hỗ trợ trước thay vì giả định chuyên gia luôn sẵn sàng.

## 11. Điều chỉnh kế hoạch khi có thay đổi đột xuất

Khi một yêu cầu mới xuất hiện, nhóm cần đánh giá tác động lên kế hoạch hiện tại trước khi nhận cam kết.

### 11.1. Quy trình tiếp nhận

1. Ghi nhận yêu cầu và lý do phát sinh.
2. Xác định mức khẩn cấp, tác động và thời hạn.
3. Ước lượng phạm vi test, retest, regression và môi trường cần dùng.
4. Kiểm tra năng lực buffer còn lại.
5. Xác định công việc nào sẽ bị trì hoãn nếu tiếp nhận.
6. Thống nhất người quyết định và thông báo cho bên liên quan.
7. Cập nhật kế hoạch, người sở hữu và mốc thời gian.
8. Theo dõi kết quả và mức sử dụng buffer.

### 11.2. Ví dụ thay đổi khẩn cấp

Giả sử nhóm có 150 giờ khả dụng trong tuần, đã lập kế hoạch 130 giờ và còn 20 giờ buffer. Một hotfix liên quan đến quyền truy cập cần 14 giờ kiểm thử. Nhóm có thể tiếp nhận trong buffer và còn 6 giờ dự phòng.

Sau đó, một thay đổi tích hợp đối tác cần thêm 18 giờ. Tổng phần phát sinh là 32 giờ, vượt buffer 12 giờ. Nhóm cần chọn một trong các phương án:

- Hoãn công việc ít rủi ro đã được thống nhất.
- Giảm phạm vi kiểm thử có căn cứ, nhưng giữ các ca bắt buộc.
- Nhờ nhóm khác hỗ trợ nếu có năng lực và kiến thức phù hợp.
- Chuyển một phần công việc sang chu kỳ tiếp theo.
- Điều chỉnh thời hạn phát hành nếu rủi ro không thể chấp nhận.

Không nên mặc định nhóm sẽ hấp thụ phần vượt bằng làm thêm giờ. Làm thêm có thể là biện pháp ngắn hạn được phê duyệt, nhưng không thay thế kế hoạch năng lực bền vững.

### 11.3. Ghi nhận quyết định và trade-off

Mỗi lần thay đổi kế hoạch nên ghi:

- Công việc mới và lý do ưu tiên.
- Năng lực dự phòng đã dùng.
- Công việc bị hoãn hoặc thu hẹp.
- Kiểm tra bắt buộc vẫn được giữ.
- Rủi ro còn lại và người chấp nhận.
- Tác động đến mốc phát hành hoặc cam kết khác.

Ghi nhận giúp nhóm giải thích biến động tiến độ và cải thiện dự báo cho chu kỳ sau.

## 12. Theo dõi và cải thiện mô hình năng lực

Kế hoạch chỉ có giá trị khi được so sánh với thực tế. Nhóm nên theo dõi một số chỉ số để biết buffer có phù hợp và công việc có đang bị tắc nghẽn hay không.

### 12.1. Chỉ số về tải và dự báo

- **Năng lực khả dụng:** số giờ thực tế sau khi trừ vắng mặt và hoạt động chung.
- **Nhu cầu đã cam kết:** giờ dự kiến cho thay đổi, retest và regression.
- **Sai lệch ước lượng:** chênh lệch giữa giờ dự báo và giờ thực tế.
- **Tỷ lệ buffer sử dụng:** giờ công việc đột xuất chia cho buffer đã dành.
- **Tỷ lệ vượt buffer:** số chu kỳ nhu cầu đột xuất vượt năng lực dự phòng.
- **Tải theo vai trò:** mức sử dụng và thời gian chờ của từng kỹ năng khan hiếm.

### 12.2. Chỉ số về luồng công việc

- **Lead time:** thời gian từ lúc yêu cầu sẵn sàng đến khi hoàn tất.
- **Cycle time:** thời gian công việc thực sự ở trạng thái đang xử lý.
- **WIP:** số công việc đang mở.
- **Thời gian chờ:** thời gian chờ build, môi trường, dữ liệu hoặc người hỗ trợ.
- **Tỷ lệ retest đạt lần đầu:** tỷ lệ lỗi được xác minh đã sửa ở vòng retest đầu tiên.
- **Tỷ lệ mở lại:** tỷ lệ lỗi phải mở lại sau khi retest.
- **Thời gian regression:** thời gian hoàn tất tập hồi quy theo từng loại thay đổi.

### 12.3. Chỉ số về chất lượng

- Lỗi lọt sau phát hành và mức nghiêm trọng.
- Lỗi tái diễn có nguyên nhân tương tự.
- Tỷ lệ test flaky trong tập regression quan trọng.
- Tỷ lệ kiểm tra bắt buộc hoàn tất đúng hạn.
- Số rủi ro được chấp nhận do không đủ năng lực.

Không nên dùng số lỗi retest đạt lần đầu làm chỉ tiêu cá nhân. Tỷ lệ thấp có thể phản ánh bản sửa chưa tốt, nhưng cũng có thể do lỗi phức tạp hoặc điều kiện môi trường chưa ổn định. Chỉ số cần phục vụ cải thiện quy trình, không tạo động lực che giấu vấn đề.

### 12.4. Rà soát buffer định kỳ

Nếu buffer thường xuyên không đủ, xem lại tải đột xuất, mức dự phòng và quy trình thay đổi. Nếu buffer liên tục không được sử dụng, có thể giảm hoặc chuyển một phần sang cải thiện chất lượng. Cần xem cả độ biến động và các sự cố hiếm có hậu quả lớn, không chỉ trung bình.

## 13. Những sai lầm thường gặp

### 13.1. Phân bổ 100% năng lực cho kế hoạch

Kế hoạch không có dự phòng dễ bị vỡ khi lỗi hoặc thay đổi phát sinh. Hãy dành buffer phù hợp với dữ liệu và mức bất định.

### 13.2. Coi mọi lỗi cần một vòng retest

Một số lỗi cần nhiều vòng, nhiều cấu hình hoặc điều tra bổ sung. Dùng dữ liệu lịch sử và khoảng ước lượng thay vì giả định một lần duy nhất.

### 13.3. Gộp retest với regression

Retest xác minh bản sửa cho lỗi cụ thể; regression kiểm tra tác động rộng hơn. Gộp hai hoạt động có thể làm thiếu phạm vi hoặc tính sai công sức.

### 13.4. Dành buffer nhưng không có quy tắc kích hoạt

Nếu không xác định ai được dùng buffer và mức ưu tiên nào được phép chen vào, phần dự phòng có thể bị tiêu hết cho công việc thông thường.

### 13.5. Chỉ tính giờ con người

Runner, môi trường, sandbox, dữ liệu và thiết bị cũng là nguồn lực giới hạn. Bỏ qua chúng có thể khiến kế hoạch có đủ người nhưng không thể thực thi.

### 13.6. Đánh giá năng lực chỉ bằng số ca hoàn tất

Các ca có độ phức tạp và giá trị khác nhau. Cần theo dõi công sức, rủi ro, độ bao phủ, chất lượng bằng chứng và kết quả phát hiện lỗi.

### 13.7. Nhận mọi yêu cầu đột xuất mà không điều chỉnh

Tiếp nhận công việc mới nhưng không thay đổi phạm vi hoặc thời hạn làm tăng WIP và kéo dài mọi công việc. Mỗi yêu cầu cần có quyết định về trade-off.

### 13.8. Giữ người dự phòng nhưng không duy trì kỹ năng

Người được coi là backup nhưng không có quyền, dữ liệu hoặc kiến thức thực tế sẽ không thể hỗ trợ khi cần. Cần đào tạo chéo và thực hành định kỳ.

### 13.9. Dùng làm thêm giờ như năng lực mặc định

Làm thêm liên tục làm tăng mệt mỏi, lỗi thao tác và giảm chất lượng đánh giá. Nếu nhu cầu thường xuyên vượt năng lực, cần điều chỉnh phạm vi, lịch, quy trình hoặc nguồn lực.

## 14. Quy trình lập kế hoạch năng lực cho một chu kỳ

Nhóm có thể áp dụng trình tự sau ở đầu sprint, tuần hoặc giai đoạn phát hành:

1. **Xác định năng lực khả dụng:** tính theo người, vai trò, ngày nghỉ và hoạt động chung.
2. **Tập hợp nhu cầu kế hoạch:** thay đổi mới, test design, thực thi và kiểm tra chấp nhận.
3. **Dự báo retest:** dùng số lỗi dự kiến, công sức mỗi vòng và số vòng lịch sử.
4. **Dự báo regression:** phân tích vùng thay đổi, rủi ro, lịch sử lỗi và suite cần chạy.
5. **Đánh giá biến động:** xem hotfix, thay đổi yêu cầu, sự cố và lịch sử công việc đột xuất.
6. **Dành buffer:** xác định lượng giờ, phạm vi kích hoạt và người điều phối.
7. **Kiểm tra nguồn lực phi nhân sự:** runner, môi trường, dữ liệu, sandbox và thiết bị.
8. **Ưu tiên và giới hạn WIP:** giữ kiểm tra bắt buộc, chọn công việc có giá trị cao và xác định việc có thể hoãn.
9. **Thống nhất trade-off:** công khai công việc bị ảnh hưởng nếu có thay đổi khẩn.
10. **Theo dõi thực tế:** cập nhật tải, thời gian chờ, buffer và rủi ro.
11. **Rút kinh nghiệm:** so sánh dự báo với thực tế và điều chỉnh chu kỳ sau.

## 15. Mẫu bảng theo dõi năng lực

Nhóm có thể dùng một bảng đơn giản để theo dõi kế hoạch và thực tế:

| Danh mục | Năng lực phân bổ | Thực tế sử dụng | Chênh lệch | Ghi chú |
|---|---:|---:|---:|---|
| Thay đổi theo kế hoạch | 72 giờ |  |  |  |
| Retesting | 24 giờ |  |  |  |
| Regression | 24 giờ |  |  |  |
| Buffer đột xuất | 22,5 giờ |  |  |  |
| Cải thiện chất lượng | 7,5 giờ |  |  | Có thể tạm dừng khi buffer kích hoạt |
| **Tổng** | **150 giờ** |  |  |  |

Các con số chỉ là ví dụ. Bảng thực tế nên có thêm người sở hữu, mức ưu tiên, thời hạn, trạng thái, phụ thuộc và rủi ro còn lại. Cập nhật theo nhịp đủ ngắn để nhóm phát hiện sớm khi dự báo không còn đúng.

### 15.1. Mẫu ghi nhận công việc đột xuất

| Trường | Nội dung |
|---|---|
| Mã yêu cầu/lỗi | Định danh có thể truy vết |
| Mức ưu tiên | P0/P1/P2/P3 theo quy ước nhóm |
| Lý do | Sự cố, hotfix, yêu cầu mới hoặc thay đổi môi trường |
| Công sức ước lượng | Giờ/ngày theo vai trò và môi trường |
| Năng lực lấy từ | Buffer, công việc hoãn hoặc nguồn hỗ trợ bổ sung |
| Công việc bị ảnh hưởng | Phạm vi hoặc thời hạn phải điều chỉnh |
| Kiểm tra bắt buộc | Các ca không được bỏ qua |
| Rủi ro còn lại | Điều chưa thể xác minh trong thời gian hiện có |
| Người quyết định | Người có thẩm quyền chấp nhận trade-off |

## 16. Danh sách rà soát trước khi chốt phân bổ

Trước khi xác nhận kế hoạch kiểm thử cho một chu kỳ, hãy kiểm tra:

- [ ] Năng lực khả dụng đã trừ nghỉ phép và hoạt động chung.
- [ ] Thời gian thiết kế, chuẩn bị, thực thi, phân tích và báo cáo được tính đến.
- [ ] Retest được ước lượng theo số lỗi, độ phức tạp và số vòng kỳ vọng.
- [ ] Regression được chọn theo vùng thay đổi, rủi ro và lịch sử lỗi.
- [ ] Các kiểm tra bắt buộc được giữ trong kế hoạch.
- [ ] Công việc đột xuất có buffer và quy tắc kích hoạt rõ.
- [ ] Buffer được hiệu chỉnh từ dữ liệu lịch sử và mức bất định.
- [ ] Nguồn lực môi trường, runner, dữ liệu và quota được kiểm tra.
- [ ] Kỹ năng khan hiếm có người dự phòng và kế hoạch hỗ trợ.
- [ ] WIP và thời gian chờ được theo dõi.
- [ ] Có quy trình điều chỉnh khi nhu cầu vượt năng lực.
- [ ] Công việc bị hoãn và rủi ro còn lại được ghi nhận.
- [ ] Dữ liệu thực tế sẽ được dùng để hiệu chỉnh kế hoạch tiếp theo.

## 17. Kết luận

Dành năng lực cho retesting, regression và thay đổi đột xuất là một phần của quản lý rủi ro kiểm thử. Retesting xác minh bản sửa cho lỗi cụ thể; regression kiểm tra ảnh hưởng đến hành vi liên quan; công việc đột xuất cần một cơ chế tiếp nhận và điều chỉnh minh bạch. Ba nhóm này có đặc điểm và mức bất định khác nhau nên cần được dự báo riêng.

Nhóm cần tính năng lực thực tế, dùng dữ liệu lịch sử để ước lượng số vòng retest và phạm vi regression, dành buffer phù hợp, đồng thời quản lý cả con người lẫn môi trường và công cụ. Khi nhu cầu vượt năng lực, phải ưu tiên theo rủi ro, ghi rõ công việc bị ảnh hưởng và chuyển quyết định chấp nhận rủi ro cho đúng thẩm quyền. Việc so sánh dự báo với thực tế qua từng chu kỳ giúp mô hình phân bổ ngày càng sát hơn, giảm quá tải và bảo đảm các kiểm tra quan trọng có đủ nguồn lực.
