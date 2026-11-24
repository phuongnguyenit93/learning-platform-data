# Đánh giá chất lượng của kết quả thay vì chỉ đếm số bài kiểm thử

Một nhóm phát triển nền tảng học trực tuyến có bảng báo cáo trông rất ấn tượng: **1.250 automated tests**, **98% test pass** và số ca kiểm thử tăng đều mỗi Sprint. Trong Sprint Review, nhóm vui mừng nói rằng chất lượng đã cao hơn tháng trước. Nhưng khi người học thanh toán và chuyển sang bài đầu tiên, một số tài khoản vẫn không được cấp quyền; ở giờ cao điểm, trang đăng ký phản hồi chậm; khi nhà cung cấp gửi callback trùng, hệ thống đôi khi tạo hai ghi nhận giao dịch. Bộ test chủ yếu kiểm tra các hàm nhỏ với dữ liệu giả, nhiều test bỏ qua trường hợp lỗi, và các phép kiểm tra tích hợp có lúc bị tắt vì thường xuyên thất bại.

Ở tình huống này, **số test lớn không đủ để kết luận sản phẩm có chất lượng tốt**. Test là công cụ tạo **bằng chứng về một số đặc tính của phần mềm trong những điều kiện xác định**, không phải chính chất lượng người dùng nhận được. Ngược lại, một đội có ít test hơn nhưng kiểm tra đúng rủi ro, tích hợp thường xuyên và quan sát kết quả vận hành có thể hiểu rõ chất lượng hơn — dù vẫn cần thận trọng vì ít test cũng có thể là thiếu bảo vệ.

Vấn đề của bài không phải **“đếm test là vô ích”**. Số test, tần suất chạy, tỷ lệ pass và độ bao phủ có thể giúp quản lý bộ kiểm thử. Nhưng cần phân biệt:

- **Hoạt động và đầu ra của kiểm thử:** đã viết/chạy bao nhiêu test, chạy trong bao lâu?
- **Bằng chứng kiểm chứng:** hành vi, rủi ro và điều kiện chất lượng nào thực sự được kiểm tra, trên phiên bản và môi trường nào?
- **Chất lượng của kết quả:** người dùng có hoàn thành công việc **đúng, an toàn, tin cậy và thuận tiện** không?
- **Khả năng duy trì chất lượng:** khi yêu cầu đổi, đội có phát hiện lỗi sớm và tiếp tục giao phần mềm tốt một cách bền vững không?

Bài thuộc chương **Chất lượng liên tục** của module **AGILE_DEVELOPMENT**, gắn với việc hiểu giá trị và nguyên tắc Agile, nhận phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục. Các ví dụ kết nối user story, Product Backlog, Scrum, Kanban, XP và các phép đo dòng công việc để nhóm chọn cách xây dựng, kiểm chứng và theo dõi chất lượng phù hợp với rủi ro thật.

> **Thông điệp cốt lõi:** Đừng hỏi duy nhất “Có bao nhiêu test?”. Hãy hỏi **“Những điều quan trọng nào đã được kiểm chứng, rủi ro nào vẫn còn, người dùng có thực sự đạt mục tiêu và chúng ta có thể duy trì chất lượng khi tiếp tục thay đổi không?”**

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **test count, test pass rate, test coverage** với bằng chứng về **tính đúng đắn, độ tin cậy, bảo mật, khả năng sử dụng, hiệu năng và kết quả người dùng**.
2. Diễn giải giới hạn của các số đo phổ biến: nhiều test không đồng nghĩa đủ kịch bản; **100% code coverage** không đồng nghĩa không có lỗi; test pass trên mock không chứng minh tích hợp thật.
3. Xây chiến lược kiểm thử theo **rủi ro và hành trình người dùng**, kết hợp static checks, unit tests, API/contract, integration, end-to-end, exploratory, bảo mật, accessibility và hiệu năng khi phù hợp.
4. Liên kết **nhu cầu → acceptance criteria → kiểm thử → bằng chứng → Definition of Done → phản hồi/outcome**, không đồng nhất các khái niệm.
5. Dùng các chỉ số như escaped defects, incident severity, reliability, user task success, flaky tests, thời gian phản hồi CI và flow metrics để phát hiện vấn đề thay vì xếp hạng cá nhân.
6. Phân tích một báo cáo trước–sau khi số test tăng nhưng chất lượng sản phẩm không tăng; tránh kết luận sai do cách đếm, mẫu đo hoặc thay đổi đồng thời.
7. Thiết kế một **quality scorecard có guardrails**, một kế hoạch cải tiến có giả thuyết và một mẫu quyết định phát hành dựa trên bằng chứng.
8. Áp dụng các nguyên tắc với tình huống thanh toán–ghi danh khóa học và phối hợp thực hành Scrum, Kanban, XP.

## 1. Chất lượng là khả năng đáp ứng nhu cầu và rủi ro trong bối cảnh thật

Một phần mềm có chất lượng không chỉ “chạy không lỗi” ở một máy tính. Chất lượng phụ thuộc **người dùng nào**, **việc họ muốn làm**, **điều kiện sử dụng** và **những ràng buộc bắt buộc**.

Đối với nền tảng học trực tuyến, hãy xét hành trình:

~~~text
Tìm khóa -> Xem thông tin -> Đăng ký/thanh toán
-> Nhận quyền hợp lệ -> Vào bài đầu -> Tiếp tục học
~~~

Nếu giao diện đẹp nhưng quyền truy cập bị cấp sai, hệ thống không đạt chất lượng cần thiết. Nếu bảo mật đúng nhưng người học không hiểu trạng thái giao dịch và bỏ dở đăng ký, vẫn có vấn đề chất lượng trải nghiệm. Nếu người học vào bài được ở môi trường thử nhưng dịch vụ lỗi dưới tải thực, chất lượng vận hành chưa đạt.

### 1.1. Các chiều chất lượng nên được xem

| Chiều chất lượng | Câu hỏi thực tế | Ví dụ trên nền tảng học |
|---|---|---|
| **Đúng chức năng** | Hệ thống làm đúng điều đã cam kết và các ngoại lệ liên quan không? | Ghi danh đúng khóa, cấp quyền theo kết quả thanh toán hợp lệ |
| **Độ tin cậy/khả dụng** | Người dùng có sử dụng được trong điều kiện đã công bố không? | Luồng vào bài không thường xuyên trả lỗi khi có nhiều người truy cập |
| **Bảo mật và riêng tư** | Dữ liệu và quyền có được bảo vệ không? | Học viên B không đọc được đơn của A |
| **Hiệu năng** | Phản hồi có phù hợp nhu cầu và điều kiện tải không? | Trang ghi danh tải trong ngưỡng đã thống nhất dưới tải đại diện |
| **Khả năng sử dụng** | Người dùng có hiểu và hoàn tất tác vụ không? | Biết trạng thái thanh toán và bước tiếp theo |
| **Khả năng truy cập (accessibility)** | Người có nhu cầu hỗ trợ có thể thực hiện tác vụ phù hợp không? | Nút đăng ký dùng được bằng bàn phím, trạng thái được truyền đạt đầy đủ |
| **Tính tương thích** | Thành phần, trình duyệt, thiết bị và tích hợp có làm việc cùng nhau không? | Web/mobile sử dụng đúng API, callback đối tác được xử lý |
| **Khả năng bảo trì/thay đổi** | Đội có sửa/tích hợp yêu cầu mới an toàn không? | Thêm phương thức thanh toán không làm sai logic cấp quyền |
| **Khả năng vận hành và khôi phục** | Có nhận biết, điều tra và phục hồi sau lỗi không? | Phát hiện giao dịch kẹt, xử lý reconciliation đúng quyền |

Các nhãn trên là **cách nhóm hóa để học**, không phải tuyên bố mọi sản phẩm phải có cùng một bảng điểm. Với sản phẩm chứa dữ liệu nhạy cảm hoặc xử lý tiền, bảo mật và tính toàn vẹn là những ràng buộc quan trọng; với ứng dụng dùng ngoài trời hoặc thiết bị hỗ trợ, các thuộc tính khác có thể quyết định khả năng sử dụng.

### 1.2. Chất lượng của kết quả và chất lượng của quá trình có liên quan nhưng khác nhau

- **Chất lượng kết quả:** phần mềm giúp người dùng hoàn tất tác vụ chính xác, an toàn và đáng tin trong phạm vi phù hợp.
- **Chất lượng quá trình phát triển:** nhóm làm rõ yêu cầu, kiểm thử, tích hợp, review, khôi phục và học từ phản hồi đủ hiệu quả để tiếp tục tạo kết quả tốt.

Quy trình có nhiều bước kiểm tra **không tự bảo đảm** sản phẩm tốt nếu các bước kiểm tra sai thứ cần kiểm tra. Ngược lại, một bản phát hành tình cờ không phát hiện lỗi lớn **không chứng minh** quy trình có khả năng duy trì chất lượng nhiều vòng.

### 1.3. Chất lượng là khái niệm có điều kiện

Phát biểu “tính năng đã được kiểm tra toàn diện” rất dễ gây hiểu nhầm. Nên thay bằng phát biểu kiểm chứng được:

> “Trên build B, trong môi trường tích hợp E, chúng tôi đã chạy các test cho giao dịch thành công, chờ, thất bại, callback lặp và phân quyền; các test được chỉ định đều đạt. Chưa có bằng chứng đủ cho tải cao điểm của kỳ khai giảng và một trường hợp downtime của đối tác. Hai rủi ro này còn mở trước khi quyết định mở rộng.”

Phát biểu này giúp người ra quyết định hiểu **phạm vi bằng chứng và khoảng trống**, thay vì nghe một tỷ lệ pass rồi mặc định không còn rủi ro.

## 2. Vì sao đếm số test dễ tạo cảm giác an toàn giả?

**Test count** là số ca kiểm thử được lưu, chạy hoặc báo cáo theo định nghĩa nhất quán. Nó có thể hữu ích cho quản trị công cụ và bộ test. Tuy nhiên, mỗi test có thể khác nhau rất lớn về **mục tiêu, độ sâu, mức độc lập, khả năng phát hiện lỗi và mức liên quan tới rủi ro**.

### 2.1. Một nghìn test có thể kiểm tra cùng một điều

Giả sử bộ kiểm thử có:

- 700 test kiểm tra định dạng chuỗi và các hàm mapping.
- 250 test với cùng luồng giả lập thanh toán thành công.
- 40 test đọc/ghi cơ sở dữ liệu bằng dữ liệu đơn giản.
- 10 test API trường hợp thành công, không có kiểm tra tài khoản khác hoặc callback lặp.

Tổng cộng là **1.000 test**, nhưng không thể kết luận đã kiểm chứng rủi ro chính của luồng cấp quyền. Nếu một lỗi xảy ra khi callback gửi hai lần hoặc hai request đồng thời, nhiều test trong danh sách có thể **không phát hiện được**.

Một bộ test có giá trị cần nhìn **những hành vi và rủi ro khác nhau được kiểm chứng**, không chỉ số lượng phương thức \`@Test\`.

### 2.2. Thêm test không bảo đảm tăng khả năng phát hiện lỗi

Ví dụ:

~~~java
@Test
void statusIsSuccess() {
    assertEquals("SUCCESS", "SUCCESS");
}
~~~

Đây là một test pass nhưng hầu như **không kiểm tra sản phẩm**. Ngược lại:

~~~java
@Test
void pendingPaymentMustNotGrantAccess() {
    PaymentResult result = paymentService.process(
        paymentEvent("order-17", "PENDING")
    );

    assertFalse(result.accessGranted());
}
~~~

Test thứ hai có ý nghĩa hơn nếu \`paymentService\` là implementation thật hoặc một đơn vị được cấu hình đúng, test thực sự thực thi quy tắc liên quan và assertion có khả năng thất bại khi triển khai sai. Tuy nhiên, **chỉ một unit test cũng không đủ chứng minh hệ thống thanh toán an toàn**, vì xác thực callback, database, phân quyền và trạng thái đồng thời còn cần kiểm tra ở lớp phù hợp.

### 2.3. Test pass rate đo điều gì?

Một cách tính:

\[
\text{Pass rate} =
\frac{\text{Số test báo đạt}}{\text{Số test được tính là đã thực thi}}
\times 100\%
\]

Giả sử 990 test đạt trong số 1.000 test được tính là thực thi:

\[
\text{Pass rate} = \frac{990}{1000}\times100\% = 99\%
\]

**99% không có nghĩa sản phẩm đúng 99%.** Chỉ số chưa nói:

- Có bao nhiêu test bị **skip, quarantine hoặc không được chọn chạy**?
- Mười test thất bại liên quan tới hành vi nào và mức nghiêm trọng ra sao?
- Những rủi ro quan trọng chưa có test nào?
- Test chạy trên build, dữ liệu, cấu hình và môi trường nào?
- Test pass vì behavior đúng hay vì assertion yếu/mock sai?
- Test có ổn định đủ để tin một lần pass không?

**Một test phân quyền quan trọng thất bại có thể là lý do chặn phát hành**, dù 999 test còn lại đạt. Không được lấy trung bình số test để làm “phiếu bầu” vượt qua rủi ro không chấp nhận.

### 2.4. Tỷ lệ pass có thể tăng theo những cách không làm chất lượng tăng

| Cách “cải thiện” con số | Tác hại có thể có |
|---|---|
| Loại khỏi suite các test thường thất bại nhưng chưa điều tra | Chỉ số đẹp hơn, rủi ro bị che |
| Chỉ chạy unit tests mà ngừng integration tests | Pass nhanh hơn, phát hiện lỗi liên hệ thành phần kém hơn |
| Chia một test thành nhiều test tương tự | Test count tăng, nội dung kiểm chứng không tăng tương ứng |
| Dùng mock trả kết quả cố định cho mọi trường hợp | Test dễ pass nhưng ít phản ánh tích hợp hoặc điều kiện lỗi |
| Sửa assertion cho phù hợp hành vi sai | Test pass nhưng hợp đồng nghiệp vụ bị vi phạm |
| Đánh dấu test quan trọng \`@Disabled\` rồi quên mở lại | Dashboard không phản ánh vùng thiếu kiểm chứng |
| Chỉ báo test pass của lần chạy thành công cuối | Che các lần thất bại không được giải thích |

Đây là những **cơ chế tạo động lực sai** khi tổ chức dùng số test hoặc pass rate làm KPI thưởng/phạt.

### 2.5. Số test có ích ở đâu?

Không cần cấm đếm test. Nó có thể giúp:

- Ước lượng thời gian chạy của một suite.
- Phát hiện một nhóm test bị mất do cấu hình.
- Phân bố đầu tư giữa các lớp test.
- Theo dõi mức bảo trì và các test bị skip/quarantine.
- Kiểm tra liệu một change có bổ sung regression test sau khi tìm được bug không.

Nhưng cần **gắn số đếm với mục tiêu quản trị suite**, không dùng làm kết luận trực tiếp về chất lượng sản phẩm.

## 3. Phân biệt test coverage với sự đầy đủ của bằng chứng

Từ **“coverage”** có thể chỉ nhiều loại:

- **Code coverage:** phần code hoặc nhánh code được thực thi trong một lần chạy test.
- **Requirement/acceptance coverage:** điều kiện nghiệp vụ hoặc ví dụ quan trọng được liên kết với test nào.
- **Risk coverage:** những nguy cơ có ảnh hưởng lớn được kiểm chứng bằng phương pháp nào.
- **Configuration/platform coverage:** các trình duyệt, thiết bị, hệ điều hành, môi trường hoặc tổ hợp cấu hình nào được kiểm tra.
- **Data/behavior coverage:** những loại đầu vào, trạng thái, biên, lỗi và cách tương tác nào đã được xem xét.

Những khái niệm này không thể thay thế cho nhau.

### 3.1. Code coverage không phải correctness

Một cách diễn giải **line coverage**:

\[
\text{Line coverage} =
\frac{\text{Số dòng có thể thực thi đã được chạy qua}}
{\text{Tổng dòng có thể thực thi trong phạm vi đo}}
\times 100\%
\]

**Branch coverage** xét các nhánh điều khiển đã được thực thi; nó thường bộc lộ một số khoảng trống mà line coverage không thấy. Tuy nhiên, dù chỉ số cao, test có thể vẫn thiếu assertion hoặc thiếu điều kiện đầu vào có ý nghĩa.

Ví dụ:

~~~java
public boolean canAccessCourse(boolean paymentConfirmed,
                               boolean accountSuspended) {
    return paymentConfirmed || !accountSuspended; // Quy tắc giả định sai.
}
~~~

Nếu yêu cầu nghiệp vụ là **chỉ cấp quyền khi giao dịch hợp lệ và tài khoản không bị đình chỉ**, biểu thức đúng trong mô hình đơn giản này phải là:

~~~java
return paymentConfirmed && !accountSuspended;
~~~

Một test chỉ thực thi hàm mà **không so sánh với kết quả mong đợi đúng** vẫn có thể làm dòng code được bao phủ. Do đó **coverage đo phần được chạy qua, không bảo đảm hành vi đã được kiểm chứng đúng**.

Hàm trên còn là mô hình minh họa, **không phải thuật toán phân quyền production**: hệ thống thật cần xét chủ sở hữu, quyền theo khóa, nguồn trạng thái đáng tin, lỗi/đơn trùng và các quy tắc khác.

### 3.2. 100% coverage vẫn có thể bỏ sót gì?

Ngay cả khi toàn bộ dòng hoặc nhánh trong một hàm đã được chạy, có thể còn:

1. **Sai yêu cầu:** test xác nhận một hành vi sai nhưng cả team đều tưởng đúng.
2. **Thiếu assertion:** test gọi phương thức rồi chỉ kiểm tra không ném exception.
3. **Thiếu trạng thái/dữ liệu:** tài khoản B, callback lặp, dữ liệu cũ, giao dịch lỗi.
4. **Thiếu cạnh tranh đồng thời:** hai request cấp quyền cùng lúc.
5. **Thiếu tích hợp:** database, message broker, dịch vụ ngoài, transaction.
6. **Thiếu điều kiện vận hành:** timeout, mất mạng, tải cao, rollback.
7. **Thiếu phi chức năng:** bảo mật, accessibility, hiệu năng.
8. **Thiếu outcome:** người dùng không hiểu chức năng dù code đúng AC.

Vì vậy **coverage cao có thể là tín hiệu hữu ích để tìm chỗ chưa chạy**, nhưng không phải giấy chứng nhận không có lỗi.

### 3.3. Requirement và risk coverage có thể hữu ích hơn một tỷ lệ tổng

Giả sử luồng đăng ký khóa trả phí có các điều kiện:

| Rủi ro hoặc hành vi | Mức tác động | Cách kiểm chứng phù hợp | Tình trạng bằng chứng |
|---|---|---|---|
| Giao dịch chờ không cấp quyền học | Cao | Unit/API và integration test với trạng thái chờ | Đã chạy trên build B |
| Callback thành công hợp lệ cấp quyền đúng một lần | Cao | API/integration, thử gửi lặp và kiểm tra database | Đã chạy, còn cần kiểm tra cạnh tranh |
| Học viên B không đọc được đơn của A | Rất cao | Security/API test với nhiều identity | Chưa có kết quả trên build B |
| Giao dịch thất bại hiển thị đúng bước tiếp | Trung bình–cao | Acceptance + exploratory test | Đã thử, thông điệp gây hiểu nhầm |
| Trang ghi danh đạt ngưỡng tải đã thống nhất | Cao vào kỳ khai giảng | Performance test với dữ liệu và tải đại diện | Chưa chạy ở mức tải mục tiêu |
| Người học hiểu trạng thái và tự vào bài | Cao cho outcome | Usability observation + product analytics | Chỉ có dữ liệu nhóm thử nhỏ |

Bảng này **không cố gắng cộng một phần trăm “chất lượng tổng”**. Nó làm rõ **điều gì đã có bằng chứng và rủi ro nào còn mở** để đưa ra quyết định phù hợp.

### 3.4. Mutation testing là một tín hiệu bổ sung, không phải lời phán quyết

**Mutation testing** tạo những thay đổi nhỏ có chủ đích trong code (ví dụ đổi \`&&\` thành \`||\`, hoặc đổi toán tử so sánh) rồi kiểm tra test suite có phát hiện được hay không. Nếu test fail khi code bị đổi sai, mutation đó được xem là bị “kill”. Chỉ số có thể gợi ý **khả năng phát hiện một số loại sai lệch logic** của test suite.

Ví dụ:

- Chuyển \`paymentConfirmed && !accountSuspended\` thành \`paymentConfirmed || !accountSuspended\`.
- Nếu test không thất bại, có thể suite chưa kiểm tra trường hợp cần phân biệt.

Nhưng không nên dùng mutation score như **tỷ lệ chất lượng sản phẩm**:

- Có mutation tương đương không làm đổi hành vi.
- Công cụ chỉ tạo một số loại lỗi giả.
- Test có thể phát hiện mutation nhưng vẫn bỏ sót tích hợp/bảo mật.
- Chạy mutation toàn hệ thống có chi phí lớn.
- Điểm số có thể bị tối ưu để đạt “mục tiêu” thay vì bảo vệ rủi ro.

Hãy dùng nó chọn lọc cho **vùng logic quan trọng** khi chi phí hợp lý.

## 4. Chất lượng kết quả: từ yêu cầu đến bằng chứng và kết quả người dùng

Một cách tổ chức thông tin hữu ích:

~~~mermaid
flowchart LR
    A["Vấn đề và mục tiêu người dùng"] --> B["User story / PBI"]
    B --> C["Acceptance criteria + thuộc tính chất lượng"]
    C --> D["Test và hoạt động kiểm chứng"]
    D --> E["Bằng chứng trên build/môi trường cụ thể"]
    E --> F["Increment đáp ứng DoD và điều kiện phát hành"]
    F --> G["Người dùng thực hiện tác vụ"]
    G --> H["Outcome, lỗi, phản hồi và quan sát"]
    H -. "Học và đổi ưu tiên" .-> A
~~~

Không có mũi tên nào tự động chứng minh mũi tên kế tiếp:

- Có **acceptance criteria** chưa có nghĩa đã viết/chạy test.
- Test pass chưa chứng minh **Definition of Done**.
- Increment đạt DoD chưa chứng minh người dùng **hiểu và thích** sản phẩm.
- Người dùng hoàn tất một tác vụ trong nhóm thử chưa bảo đảm cả sản phẩm hoạt động tốt dưới mọi điều kiện.

### 4.1. Phân biệt các khái niệm

| Khái niệm | Câu hỏi trả lời | Ví dụ |
|---|---|---|
| **User need / Product Goal** | Người dùng cần đạt gì và vì sao? | Học viên mua khóa và vào bài đầu mà không cần liên hệ hỗ trợ |
| **User story/PBI** | Năng lực nhỏ nào tạo tiến triển tới mục tiêu? | Hiển thị trạng thái đơn và cấp quyền theo xác nhận hợp lệ |
| **Acceptance criteria (AC)** | Những điều kiện nghiệp vụ nào phải đúng? | Trạng thái PENDING không được cấp quyền |
| **Acceptance test** | Tình huống nào kiểm chứng AC, kết quả mong đợi ra sao? | Giả lập PENDING, đọc API và kiểm tra quyền |
| **Kết quả test/evidence** | Test đã chạy trên bản nào, thực tế ra sao? | Run #42, build B, trạng thái pass/fail và log đã xử lý an toàn |
| **Definition of Done (DoD)** | Khi nào Increment được xem là hoàn tất theo tiêu chuẩn chất lượng? | Tích hợp, test áp dụng, phân quyền, khả năng truy cập và các điều kiện chung |
| **Release decision** | Có đủ điều kiện cung cấp cho đối tượng sử dụng nào chưa? | Phát hành giới hạn sau kiểm tra an toàn và vận hành |
| **Outcome** | Người dùng có đạt mục tiêu sau khi sử dụng không? | Tỷ lệ học viên hợp lệ vào bài đầu tăng mà không tăng sự cố |

Trong Scrum, **Definition of Done là commitment gắn với Increment**. Increment phải đáp ứng DoD để được xem là Done; không dùng Sprint Review làm cổng nghiệm thu bắt buộc mới được phát hành. **Acceptance criteria và DoD không đồng nghĩa nhau**: AC thường cụ thể cho một PBI; DoD bảo vệ những tiêu chuẩn chất lượng chung của Increment.

### 4.2. Verification và validation khác nhau

**Verification** quan tâm giải pháp có đáp ứng yêu cầu/đặc tả đã thống nhất không. **Validation** quan tâm giải pháp có đáp ứng nhu cầu trong bối cảnh sử dụng không.

Ví dụ:

- Verification: trang đơn hàng hiện chính xác nhãn “Đang xử lý” khi trạng thái từ nguồn tin cậy là PENDING.
- Validation: người học có hiểu “Đang xử lý” là cần làm gì tiếp theo, có quay lại đúng nơi và không bỏ dở hành trình không?

Hai câu hỏi đều cần thiết. Một UI có thể đúng theo AC nhưng vẫn gây nhầm lẫn; ngược lại, người dùng thích một flow không có nghĩa flow đó an toàn với dữ liệu tài chính.

### 4.3. Kiểm thử không tự phát hiện yêu cầu sai

Nếu Product Owner và nhóm thống nhất nhầm rằng **chỉ cần nhấn nút Pay là giao dịch thành công**, test suite có thể pass hoàn hảo cho hành vi sai. Chất lượng liên tục cần **trao đổi sớm với người hiểu nghiệp vụ, ví dụ thực tế và phản hồi người dùng** để tránh tự động hóa những giả định lỗi.

XP và các thực hành như **Three Amigos**, **Specification by Example** hoặc **BDD** có thể giúp điều này. Nhưng một kịch bản Given–When–Then mới được viết vẫn là **đặc tả bằng ví dụ**, không phải bằng chứng test đã thực thi.

## 5. Kiểm thử theo rủi ro: đặt nỗ lực vào chỗ ảnh hưởng lớn

Một đội không có vô hạn nhân lực, dữ liệu và thời gian. **Risk-based testing** giúp chọn những hoạt động kiểm chứng có lợi nhất đối với tác động người dùng và khả năng lỗi, thay vì chia đều nỗ lực theo số dòng code hoặc bắt mọi chức năng có cùng số test.

### 5.1. Hiểu rủi ro trước khi đếm test

Một cách tư duy đơn giản:

\[
\text{Rủi ro dự kiến}\approx
\text{Khả năng xảy ra}\times
\text{Mức tác động}
\]

Đây là **heuristic để so sánh**, không phải công thức định lượng đầy đủ. Khả năng xảy ra thường khó ước lượng chính xác; một số tác động như vi phạm an toàn, lộ dữ liệu hoặc nghĩa vụ pháp lý **không được xem là có thể chấp nhận chỉ vì xác suất thấp**.

Đánh giá rủi ro nên xem thêm:

- **Mức tiếp xúc:** bao nhiêu người dùng hoặc dữ liệu bị ảnh hưởng?
- **Khả năng phát hiện:** nếu lỗi xảy ra, hệ thống có biết sớm không?
- **Khả năng khôi phục:** có rollback hoặc sửa dữ liệu an toàn không?
- **Tính khó đảo ngược:** có lan sang đối tác hoặc dữ liệu đã phát hành không?
- **Chi phí chậm trễ:** nếu chưa kiểm chứng, sản phẩm có thể giao an toàn không?

### 5.2. Ví dụ bản đồ rủi ro cho đăng ký khóa

| Khu vực | Sai hỏng có thể có | Tác động | Chiến lược kiểm chứng ưu tiên |
|---|---|---|---|
| **Phân quyền** | B xem được đơn hoặc khóa trả phí của A | Rất cao | API/security tests nhiều identity, kiểm tra server-side, review rủi ro |
| **Thanh toán** | Callback trùng tạo quyền/hóa đơn sai | Rất cao | Unit/integration/concurrency tests, ràng buộc dữ liệu, thử sự kiện lỗi |
| **Trạng thái giao dịch** | PENDING bị gọi SUCCESS | Cao | AC, API/integration tests, exploratory UI |
| **Hiệu năng giờ khai giảng** | API đăng ký timeout dưới tải | Cao | Test tải đại diện, SLI latency/error, kế hoạch phục hồi |
| **Khả năng truy cập** | Không thể đăng ký chỉ bằng bàn phím | Cao với người cần hỗ trợ | Automated accessibility checks và manual assistive-technology testing phù hợp |
| **Bố cục phụ** | Khoảng cách chữ hơi lệch | Thường thấp hơn, tùy ngữ cảnh | Visual review/exploratory test theo tiêu chuẩn thương hiệu |
| **Tài liệu hỗ trợ** | Thông báo không rõ bước tiếp theo | Trung bình–cao tùy mức bỏ dở | Usability observation, hỗ trợ và thử nghiệm nội dung |

Không xem bảng là quy định rằng lỗi UI luôn ít quan trọng: trong sản phẩm hỗ trợ người khiếm thị, một lỗi khả năng truy cập có thể **ngăn hoàn toàn tác vụ trọng yếu**. Tác động phải theo người dùng và bối cảnh thực.

### 5.3. Kiểm tra “đường hạnh phúc” và “đường thất bại”

Một hành trình đăng ký thường có:

1. Thành công: yêu cầu hợp lệ, trạng thái đáng tin, cấp quyền đúng.
2. Không thành công: thiếu thông tin, từ chối thanh toán, quyền không hợp lệ.
3. Đang chờ: trạng thái chưa xác nhận; không báo thành công giả.
4. Gửi lại: người dùng bấm hai lần hoặc đối tác gửi callback trùng.
5. Đồng thời: hai request hoặc hai sự kiện cùng cập nhật một đơn.
6. Phụ thuộc lỗi: timeout, mất kết nối, trạng thái không nhất quán.
7. Dữ liệu cũ: bản ghi từ phiên bản trước hoặc migration.
8. Người dùng khác: truy cập trái quyền, session hết hạn.
9. Điều kiện tải: nhiều học viên đăng ký gần cùng lúc.
10. Khả năng dùng được: thông báo, điều hướng, hỗ trợ bàn phím và thiết bị phù hợp.

Số lượng test nên là **hệ quả của chiến lược kiểm chứng những rủi ro này**, không phải mục tiêu đặt trước kiểu “mỗi PBI phải có đúng 20 test”.

## 6. Chọn lớp kiểm chứng phù hợp: không phải test nào cũng làm cùng một việc

Một chiến lược chất lượng tốt phối hợp nhiều nguồn bằng chứng. Không có một “kim tự tháp test chuẩn” áp dụng giống nhau cho mọi sản phẩm; tỷ lệ unit/API/E2E tùy kiến trúc, độ ổn định và rủi ro.

| Hoạt động | Điều kiểm chứng tốt | Những điều nó **không** đủ chứng minh |
|---|---|---|
| **Static analysis, type/lint/dependency checks** | Một số lỗi cú pháp, cấu trúc, phụ thuộc hoặc quy tắc coding/security | Hành vi nghiệp vụ và kết quả người dùng |
| **Unit tests** | Logic nhỏ, quy tắc biên, xử lý trạng thái dễ cô lập | Tích hợp database, mạng, quyền và cấu hình production |
| **API/contract tests** | Hợp đồng đầu vào/đầu ra, auth, mã lỗi, tương thích consumer/provider | Luồng người dùng hoặc nhất quán đa hệ thống trọn vẹn |
| **Integration tests** | Thành phần thực tương tác, DB/queue/transaction hoặc service giả lập có chủ đích | Mọi tình huống của đối tác/production nếu môi trường khác nhiều |
| **End-to-end tests** | Hành trình quan trọng qua UI/API/data | Mọi lỗi biên, hiệu năng, bảo mật hoặc điều kiện hiếm |
| **Exploratory testing** | Ngộ nhận, hành vi bất ngờ, sai UX và lỗ hổng giữa test script | Không phải bằng chứng hoàn tất thống kê; cần ghi lại quan sát |
| **Security testing/review** | Các nguy cơ xác thực, phân quyền, dữ liệu, cấu hình | Không chỉ dựa vào quét tự động để khẳng định an toàn |
| **Performance/load/resilience testing** | Latency, thông lượng, hành vi dưới tải/failure theo kịch bản | Người dùng thấy giao diện dễ hiểu hay mục tiêu có giá trị |
| **Accessibility testing** | Khả năng dùng bằng bàn phím, nhãn, trạng thái và công nghệ hỗ trợ | Một điểm số automated scan không bao phủ mọi trở ngại |
| **Production observability/feedback** | Hành vi thật, sự cố, độ trễ, tỷ lệ thành công, phản hồi người dùng | Không thay thế pre-release tests và trách nhiệm an toàn |

### 6.1. “Shift left” không có nghĩa chuyển toàn bộ kiểm thử cho Developers

**Shift left** là đưa hoạt động làm rõ và phát hiện lỗi đến sớm hơn: hỏi ví dụ nghiệp vụ trước khi viết code, kiểm tra rủi ro ngay ở refinement, chạy test từ lúc commit và tích hợp thường xuyên.

Điều này có thể làm nhiều người cùng chịu trách nhiệm **tạo chất lượng**. Nhưng không có nghĩa loại bỏ chuyên môn kiểm thử, bảo mật, accessibility hoặc review độc lập khi cần.

### 6.2. “Shift right” không có nghĩa bỏ test trước release

Quan sát production, feature flags, canary rollout hoặc telemetry có thể giúp nhìn hành vi thực sau phát hành. Tuy nhiên:

- Không thử nghiệm rủi ro chưa kiểm soát trực tiếp trên người dùng thật khi có thể gây hại.
- Không coi production monitoring là cách thay cho kiểm tra phân quyền hoặc tính toàn vẹn dữ liệu.
- Cần có cơ chế giảm ảnh hưởng, phát hiện và khôi phục thích hợp.
- Theo dõi outcome cần tôn trọng chính sách dữ liệu và quyền riêng tư.

**Chất lượng liên tục bao gồm cả trước và sau phát hành**, với điều kiện bảo vệ phù hợp.

### 6.3. Chất lượng test quan trọng hơn việc test ở lớp nào nổi bật

Một unit test mạnh có thể ngăn lỗi tính lãi/thanh toán sai; một E2E test yếu chỉ bấm qua màn hình mà không xác minh quyền có thể tạo cảm giác an toàn giả.

Hãy hỏi với mỗi test quan trọng:

1. Nó bảo vệ **quy tắc hoặc rủi ro** nào?
2. Nếu code sai, test có **thật sự thất bại** không?
3. Nó có chạy trên **dữ liệu và môi trường** đủ đại diện cho kết luận không?
4. Khi fail, có chỉ rõ lỗi hay tạo nhiều tín hiệu nhiễu?
5. Khi hành vi đổi hợp lệ, có dễ cập nhật mà không xóa bảo vệ quan trọng không?

### 6.4. Test suite có thời gian chạy nhanh không phải bằng chứng mạnh hay yếu tự thân

Một pipeline nhanh và tin cậy giúp phản hồi sớm, nhưng nếu nó chỉ kiểm tra format code, nó chưa bảo vệ hành trình người dùng. Một pipeline rất chậm có thể chứa nhiều test trùng lặp hoặc flaky, làm giảm khả năng sử dụng kết quả.

Nhóm có thể tổ chức:

- Các kiểm tra nhanh thường xuyên ở commit/pull request.
- Các kiểm tra tích hợp theo build hoặc điểm thay đổi phù hợp.
- Các kiểm tra tải/bảo mật/accessibility chuyên biệt theo rủi ro hoặc mốc phát hành.
- Quan sát vận hành và kiểm tra sau deploy khi có điều kiện.

**Phải công bố điều kiện nào là gate bắt buộc**, điều nào là kiểm tra bổ sung và cách xử lý khi thiếu bằng chứng; đừng để test bị bỏ qua âm thầm nhưng báo release đã “full pass”.

## 7. Khi test suite chính nó không đáng tin: flaky, skipped và dữ liệu giả

Một bộ test thất bại ngẫu nhiên có thể khiến nhóm:

- Chạy lại nhiều lần cho tới lúc xanh.
- Bỏ qua lỗi thật vì “chắc lại flaky”.
- Tắt test tích hợp để pipeline nhanh.
- Mất thời gian điều tra tín hiệu nhiễu, khiến phát hiện lỗi thật chậm hơn.

### 7.1. Flaky test là gì?

Một **flaky test** cho kết quả khác nhau trong những điều kiện được kỳ vọng tương đương, không phải vì có thay đổi hợp lệ của hành vi. Nguyên nhân có thể gồm:

- Phụ thuộc thời gian hoặc thứ tự chạy.
- Dữ liệu dùng chung chưa reset.
- Race condition trong test/implementation.
- Môi trường hoặc service giả lập không ổn định.
- Chờ bằng thời gian cố định thay vì chờ điều kiện.
- Network, resource hoặc cấu hình khác biệt không được quản lý.

Lưu ý: một test chạy không ổn định cũng có thể đang **phát hiện race condition thật của sản phẩm**. Không nên gắn nhãn flaky rồi bỏ nếu chưa điều tra.

### 7.2. Một số phép đo để quản lý suite

| Tín hiệu | Cách hiểu | Cảnh báo |
|---|---|---|
| **Số test bị skip/quarantine** | Mức kiểm chứng bị tạm loại khỏi đường chạy | Đặc biệt quan trọng nếu test bảo vệ hành vi có rủi ro cao |
| **Tần suất test không ổn định** | Những test nào thường fail rồi pass lại không rõ nguyên nhân | Phải giữ điều kiện chạy và nguyên nhân, không chỉ “retry thành công” |
| **Thời gian phản hồi CI** | Developer nhận tín hiệu sau commit trong bao lâu? | Nhanh nhưng thiếu rủi ro hoặc chậm nhưng trùng lặp đều cần cải tiến |
| **Tỷ lệ run không đạt vì môi trường** | Tính đáng tin của hạ tầng test | Phân biệt lỗi môi trường với lỗi sản phẩm dựa trên bằng chứng |
| **Thời gian sửa test hỏng** | Suite có được duy trì như tài sản kỹ thuật không? | Không tối ưu bằng cách xóa test quan trọng |
| **Tình trạng dữ liệu test** | Có đủ tình huống, tách tài khoản, migration và concurrency không? | Nhiều dữ liệu giả lý tưởng có thể bỏ sót production reality |

### 7.3. Chính sách khi test quan trọng fail

Một quy trình minh họa:

1. Lưu **build, run, test, môi trường, dữ liệu và log cần thiết** (không để lộ bí mật).
2. Kiểm tra fail có tái hiện được không và có thay đổi liên quan.
3. Phân loại sơ bộ **lỗi sản phẩm, test, môi trường hay chưa rõ**; đừng vội mặc định flaky.
4. Nếu test là **quality gate** liên quan rủi ro quan trọng, không bypass chỉ để ra release.
5. Nếu phải quarantine, ghi rủi ro, người phụ trách, phương án kiểm chứng thay thế, mốc sửa và phạm vi release bị ảnh hưởng.
6. Sửa nguyên nhân, thêm bảo vệ thích hợp và xem lại tính đáng tin của suite.

Đây là chính sách ví dụ, không phải tiêu chuẩn bắt buộc cho mọi đội. Nếu có sự cố nghiêm trọng và cần hotfix, cần xử lý theo cơ chế có thẩm quyền, giữ các điều kiện an toàn cần thiết và công bố giới hạn chứng cứ.

## 8. Đo chất lượng sản phẩm từ kết quả, sự cố và trải nghiệm thực

Để không lẫn giữa **“đã kiểm tra nhiều”** và **“sản phẩm đủ tốt”**, đội cần nhìn những tín hiệu ngoài test suite. Một chỉ số tốt phải có **định nghĩa, ranh giới, nguồn dữ liệu, cách phân tích và hành động tiếp theo**.

### 8.1. Chọn chỉ số gắn với hành trình người dùng

Đối với luồng ghi danh khóa học, các tín hiệu có thể gồm:

| Chỉ số | Cách hiểu minh họa | Điều kiện cần nói rõ |
|---|---|---|
| **Tỷ lệ hoàn tất đăng ký hợp lệ** | Số phiên/học viên hợp lệ hoàn tất đăng ký chia cho tổng số bắt đầu đủ điều kiện | Định nghĩa bắt đầu/hoàn tất; loại giao dịch không đủ điều kiện; thiết bị/kênh |
| **Tỷ lệ truy cập bài đầu thành công** | Người học đủ điều kiện vào được bài đầu theo trạng thái quyền thực | Cửa sổ thời gian tính sau ghi danh, nguồn kiểm chứng quyền |
| **Tỷ lệ lỗi API quan trọng** | Tỷ lệ request thất bại theo quy tắc kỹ thuật/dịch vụ | Không gộp 4xx hợp lệ với lỗi server/logic; xét endpoint và tải |
| **Độ trễ tác vụ quan trọng** | Thời gian để nhận phản hồi phù hợp khi đăng ký/vào bài | Xem phân phối (ví dụ p95), không chỉ trung bình |
| **Sự cố người dùng chịu ảnh hưởng** | Số hoặc tỷ lệ người dùng gặp gián đoạn đã xác nhận | Mức độ nghiêm trọng, thời gian, số người bị ảnh hưởng |
| **Lỗi thoát ra production** | Defects được xác nhận sau phát hành | Chất lượng phát hiện, mức độ sử dụng, thời gian quan sát |
| **Khả năng phục hồi** | Mất bao lâu để khôi phục sau sự cố | Điểm bắt đầu/kết thúc sự cố; mức độ và trách nhiệm |
| **Yêu cầu hỗ trợ theo chủ đề** | Người dùng vẫn gặp trở ngại gì sau khi phát hành? | Số người dùng, cách phân loại và kênh hỗ trợ |
| **Khả năng truy cập/khả năng dùng được** | Người dùng mục tiêu có hoàn tất tác vụ với nhu cầu hỗ trợ phù hợp không? | Cách thử, đối tượng thử, hạn chế của kiểm tra tự động |

Không phải mọi đội cần theo dõi tất cả các số liệu mỗi ngày. Hãy chọn **điều có thể giúp ra quyết định** tương ứng với rủi ro và mục tiêu sản phẩm.

### 8.2. Định nghĩa mẫu số để không hiểu sai tỷ lệ

Giả sử hệ thống ghi nhận:

- 1.000 phiên bắt đầu quy trình thanh toán.
- 100 phiên của người dùng không đủ điều kiện hoặc dữ liệu thử nội bộ.
- 810 phiên đủ điều kiện hoàn tất tới bước quyền học được cấp đúng.

Nếu mục tiêu là **tỷ lệ hoàn tất trong các phiên đủ điều kiện**, phép tính minh họa là:

\[
\text{Completion rate}
= \frac{810}{1000-100}\times100\% = 90\%
\]

Nhưng cần làm rõ:

- Một người thử ba lần có được tính ba phiên không?
- Trạng thái “đã thanh toán” có đồng nghĩa “đã được cấp quyền đúng” không?
- Có loại các lần mất kết nối khỏi mẫu số một cách có lý do không?
- Người dùng di chuyển qua web/mobile có làm sự kiện bị đếm hai lần không?
- Dữ liệu có đủ quyền sử dụng và bảo vệ riêng tư không?

**Thay cách xác định mẫu số giữa hai Sprint có thể làm tỷ lệ tăng mà không có cải thiện nào trong sản phẩm.** Vì vậy cần công bố metric contract trước khi so sánh.

### 8.3. Đo lỗi production với mức độ ảnh hưởng

“Có 12 bug sau release” không đủ cho quyết định. Có thể gồm mười lỗi hiển thị ít ảnh hưởng, một lỗi đăng nhập khiến mọi học viên ngừng học và một lỗi phân quyền làm lộ dữ liệu. Gộp tất cả thành một số dễ che rủi ro.

Một bản ghi sự cố chất lượng nên gồm:

1. **Hành vi sai thực tế** và điều kiện xảy ra.
2. **Nhóm người dùng/dữ liệu chịu ảnh hưởng**.
3. **Mức nghiêm trọng theo chính sách tổ chức**.
4. **Thời điểm bắt đầu, phát hiện, giảm ảnh hưởng, khôi phục**.
5. **Bằng chứng và giới hạn điều tra**.
6. **Nguyên nhân hệ thống có thể cải tiến**: thiếu AC, thiếu test, môi trường khác, thiết kế dữ liệu, monitoring hoặc phối hợp.
7. **Hành động phòng ngừa có thể kiểm chứng**, không chỉ “nhắc Developers cẩn thận”.

Không có hệ thống phân loại Severity P0–P3 chung bắt buộc cho mọi đội. Nếu dùng các nhãn ấy, cần định nghĩa nội bộ, không tự suy luận mức độ chỉ từ số ký tự trong bug title.

### 8.4. Escaped defects và giới hạn của “defect escape rate”

**Escaped defect** là lỗi lọt qua những hoạt động phát hiện/kiểm chứng trước đó và được xác nhận sau khi sản phẩm được cung cấp tới phạm vi sử dụng tương ứng. Có thể theo dõi số lỗi theo mức độ nghiêm trọng hoặc một tỷ lệ như:

\[
\text{Defect escape ratio}
= \frac{\text{Lỗi được phát hiện sau release}}
{\text{Lỗi phát hiện trước release + lỗi sau release}}
\times100\%
\]

Ví dụ giả định: 24 lỗi được xác nhận trước release và 6 lỗi được xác nhận trong cửa sổ theo dõi sau release:

\[
\frac{6}{24+6}\times100\%=20\%
\]

**20% không phải “sản phẩm sai 20%”.** Chỉ số phụ thuộc cường độ kiểm thử, cách định nghĩa bug, cửa sổ thời gian, mức sử dụng thật, độ nghiêm trọng, bản phát hành được theo dõi và khả năng phát hiện. Một đội có nhiều người dùng hơn có thể phát hiện nhiều lỗi hơn dù chất lượng không nhất thiết thấp hơn.

Đặc biệt, **không nên giảm escaped defects bằng cách gây khó cho việc báo lỗi**. Hãy khuyến khích ghi nhận trung thực, sửa nguyên nhân và đánh giá tỷ lệ cùng mức nghiêm trọng/tác động.

### 8.5. SLI, SLO và error budget

Trong vận hành dịch vụ, có thể định nghĩa:

- **SLI (Service Level Indicator):** phép đo mức dịch vụ thật, ví dụ tỷ lệ request xem bài được xử lý thành công theo định nghĩa rõ.
- **SLO (Service Level Objective):** mức mục tiêu của SLI trong một cửa sổ thời gian.
- **Error budget:** phần không đạt được phép trong mục tiêu SLO, dùng để cân bằng thay đổi và độ tin cậy theo chính sách.

**Ví dụ minh họa, không phải chuẩn phổ quát:** mục tiêu có ít nhất **99,9% request xem bài hợp lệ được phục vụ thành công trong 30 ngày**, theo một phép đo xác định. Nếu có 100.000 request hợp lệ trong cửa sổ đó, ngân sách tương ứng là tối đa **100 request không đạt**, theo định nghĩa phép đo và không xét những phức tạp khác.

\[
100\,000\times(1-0{,}999)=100
\]

Đây chỉ là cách tính một tỷ lệ minh họa. Một request có thể ảnh hưởng nhiều người hoặc một sự cố bảo mật có thể không được giải thích thỏa đáng bằng error budget. **Không lấy error budget để cho phép vi phạm pháp lý hoặc rủi ro an toàn không chấp nhận được.**

### 8.6. Độ trễ: đừng chỉ nhìn trung bình

Giả sử thời gian phản hồi API ghi danh (mili giây) trong một nhóm nhỏ là:

~~~text
180, 210, 190, 220, 195, 205, 200, 230, 240, 2100
~~~

Chín request đầu khá nhanh, nhưng request cuối mất hơn hai giây. Trung bình:

\[
\overline{T}=\frac{180+210+190+220+195+205+200+230+240+2100}{10}
=397\text{ ms}
\]

**397 ms không diễn tả tốt trải nghiệm của nhóm request chậm**. Với dữ liệu đủ đại diện, đội có thể xem p95/p99 và phân tích điều kiện tải, endpoint, môi trường và người dùng bị ảnh hưởng. Với mẫu chỉ 10 giá trị, suy luận percentile dài hạn chưa đáng tin; mục đích ví dụ là nhắc rằng **phân phối quan trọng hơn một số trung bình**.

### 8.7. Outcome không được thay bằng output

Tạo được một màn hình thông báo lỗi là **output**. Người học hiểu nguyên nhân, không nhập lại thông tin sai nhiều lần và có thể hoàn tất ghi danh là **outcome**.

Những chỉ số outcome có thể gồm:

- Tỷ lệ người học tự hoàn tất một hành trình hợp lệ.
- Tỷ lệ học viên vào bài đầu trong một khoảng thời gian phù hợp sau khi được cấp quyền.
- Số người cần hỗ trợ vì trạng thái mơ hồ, xét cùng lượng người dùng và cách phân loại.
- Thời gian người học mất để thực hiện tác vụ trong nghiên cứu usability.
- Tỷ lệ người dùng gặp lỗi ảnh hưởng tới khả năng tiếp tục học.

Các chỉ số này có yếu tố sản phẩm, nghiệp vụ, thiết kế và bối cảnh; **không phải tất cả cải thiện đều do kiểm thử**. Kiểm thử là một phần của hệ thống bảo đảm chất lượng.

## 9. Bộ chỉ số chất lượng cân bằng: không biến thành một “điểm số tổng”

Một cách dễ áp dụng là duy trì **quality scorecard** với ít chỉ số theo các nhóm:

| Nhóm | Tín hiệu ví dụ | Mục đích quyết định |
|---|---|---|
| **Outcome** | Tỷ lệ ghi danh và vào bài đầu đúng quyền | Người dùng có đạt mục tiêu sản phẩm không? |
| **Correctness và risk coverage** | Những AC/luồng rủi ro cao có test và bằng chứng trên build hiện tại | Điều kiện quan trọng nào chưa được kiểm chứng? |
| **Reliability/operations** | SLI/SLO, sự cố theo severity, thời gian khôi phục | Có cần dừng mở rộng hoặc cải thiện khả năng vận hành không? |
| **Suite health** | Test bị skip/quarantine, flaky, thời gian CI | Bằng chứng từ test có đáng tin và đủ nhanh không? |
| **Flow và khả năng sửa** | WIP, work item age, cycle time, lỗi hồi quy | Đội có hoàn tất thay đổi an toàn và đều không? |
| **Uncertainty/decision** | Các rủi ro chưa xác minh, phụ thuộc và người có quyền quyết định | Việc gì phải kiểm tra hoặc xử lý trước release? |

### 9.1. Vì sao không chỉ cộng điểm?

Giả sử tạo thang điểm:

~~~text
Coverage 90/100
Test pass 99/100
Velocity 85/100
Bao mat 20/100
Trung binh: 73,5/100
~~~

Kết luận “chất lượng 73,5% nên phát hành được” là **không có cơ sở**. Bảo mật nghiêm trọng không thể bù bằng nhiều test pass, và velocity cũng không đo chất lượng trực tiếp.

Thay vì một tổng điểm:

1. **Guardrails:** điều nào không được vi phạm, ví dụ lỗi phân quyền đã xác nhận phải được xử lý trước phạm vi phát hành tương ứng.
2. **Readiness evidence:** những vùng rủi ro quan trọng đã được kiểm chứng ở mức nào?
3. **Trend:** độ tin cậy, thời gian phản hồi, lỗi và outcome thay đổi ra sao qua các giai đoạn so sánh được?
4. **Trade-off có thẩm quyền:** còn bất định nào có thể chấp nhận, cần giảm phạm vi hay dời mốc?

Một scorecard nên làm **lộ rủi ro**, không trộn rủi ro lớn với hoạt động ít quan trọng thành một con số đẹp.

### 9.2. Guardrail khác mục tiêu cải tiến

**Guardrail:** “Không phát hành một luồng thanh toán có lỗi cấp quyền trái phép đã được xác nhận.” Đây không phải mục tiêu tối ưu từng Sprint.

**Mục tiêu cải tiến:** “Giảm thời gian đến khi biết một thay đổi tích hợp gây hồi quy.” Có thể thử CI, test data và phối hợp sớm, rồi đo.

**Kỳ vọng dịch vụ:** “Phần lớn request hợp lệ phục vụ trong ngưỡng chất lượng đã công bố.” Cần dữ liệu tải và mức ưu tiên.

Sự phân biệt này ngăn việc giảm chất lượng bắt buộc để tối ưu chỉ số khác.

### 9.3. Một scorecard minh họa

| Tín hiệu | Trạng thái giả định | Điều cần làm |
|---|---|---|
| Unit/API checks | Hầu hết đạt, hai integration tests đang bị quarantine | Điều tra nguyên nhân; công bố rủi ro bao phủ bị mất |
| Phân quyền đơn hàng | Chưa có evidence trên build mới nhất | Chặn/giới hạn phạm vi liên quan theo chính sách; chạy kiểm tra phù hợp |
| Giao dịch lặp | Test API pass, concurrency chưa kiểm tra | Bổ sung kịch bản và kiểm tra ràng buộc dữ liệu |
| Luồng ghi danh | Có test end-to-end trên staging | Kiểm tra chênh lệch staging–production và trường hợp tải |
| Reliability | Tỷ lệ lỗi tăng ở thời điểm cao điểm | Phân tích nguyên nhân và khả năng phục hồi |
| Outcome | Người học còn cần hỗ trợ vì trạng thái không rõ | Khảo sát/quan sát, làm rõ thông điệp |

**Đọc bảng từ hàng rủi ro nghiêm trọng**, không từ số test nhiều nhất.

## 10. Ví dụ hành vi thanh toán: ít kịch bản có ý nghĩa hơn hàng trăm test giống nhau

Một user story:

> **Là học viên thanh toán khóa học, tôi muốn hệ thống xác nhận đúng trạng thái và chỉ cấp quyền khi giao dịch hợp lệ, để không mất tiền hoặc bị chặn học sai.**

Product Owner, Developers và người có chuyên môn kiểm thử thảo luận những điều kiện cần đúng trước khi code.

### 10.1. Acceptance criteria minh họa

| Mã | Điều kiện chấp nhận |
|---|---|
| AC-01 | Giao dịch chưa được xác nhận thành công từ nguồn tin cậy không được xem là hoàn tất và không cấp quyền sai. |
| AC-02 | Giao dịch hợp lệ được gắn đúng đơn/người dùng/khóa và cấp quyền theo quy tắc đã thống nhất. |
| AC-03 | Callback lặp không tạo giao dịch, quyền học hoặc tác dụng phụ trùng sai. |
| AC-04 | Giao dịch thất bại/hết hạn có trạng thái rõ, không báo thành công giả. |
| AC-05 | Người dùng khác không thể truy cập hoặc sửa đơn của học viên. |
| AC-06 | Khi đối tác timeout hoặc sự kiện đến muộn, trạng thái được xử lý an toàn theo chính sách. |
| AC-07 | Bằng chứng kiểm chứng gắn đúng build và điều kiện chạy. |

Lưu ý AC-07 gần với **chính sách bằng chứng/DoD** hơn là hành vi người dùng; trong một Product Backlog thật có thể để nó trong điều kiện kiểm tra chung thay vì viết như AC của từng story. Việc đặt nó ở bảng giúp nhấn mạnh **không được nhầm kịch bản viết ra với test đã chạy**.

### 10.2. Gherkin giúp làm rõ trường hợp quan trọng

~~~gherkin
Feature: Xac nhan giao dich va cap quyen hoc

  Scenario: Giao dich dang cho khong cap quyen som
    Given don D cua hoc vien A dang cho thanh toan
    And nguon trang thai dang tin chua xac nhan thanh cong
    When A xem trang thai don D
    Then he thong hien thi trang thai dang xu ly
    And A chua duoc cap quyen hoc theo don D

  Scenario: Callback hop le duoc gui lai
    Given don D da duoc xac nhan thanh cong
    And quyen hoc da duoc cap dung mot lan
    When doi tac gui lai su kien thanh cong cho cung giao dich
    Then he thong khong tao quyen hoc trung sai
    And khong tao giao dich trung sai

  Scenario: Tai khoan khac khong doc duoc don
    Given don D thuoc tai khoan A
    And hoc vien B da dang nhap
    When B yeu cau xem chi tiet don D
    Then he thong tu choi theo chinh sach phan quyen
    And khong tiet lo du lieu rieng cua A

  Scenario: Timeout khong duoc thong bao thanh cong gia
    Given yeu cau xac nhan giao dich dang cho ket qua
    When dich vu doi tac het thoi gian phan hoi
    Then he thong khong bao da thanh toan neu chua co xac nhan hop le
    And trang thai duoc xu ly theo quy tac da thong nhat
~~~

Đây là **đặc tả bằng ví dụ**. Để trở thành evidence cần triển khai bước test, nguồn dữ liệu, xác thực sự kiện và assertion trên thành phần thật phù hợp. Gherkin không tự kiểm chứng transaction, race condition, security hoặc khả năng phục hồi.

### 10.3. Một unit test giúp bảo vệ một quy tắc, nhưng còn giới hạn

~~~java
@Test
void pendingPaymentDoesNotGrantAccess() {
    PaymentDecision decision = policy.decide(
        PaymentStatus.PENDING,
        AccountStatus.ACTIVE
    );

    assertFalse(decision.shouldGrantAccess());
}
~~~

Test này có thể bảo vệ logic của \`policy\` nếu dữ liệu, setup và assertion hợp lệ. Nhưng cần kiểm tra thêm:

- Dữ liệu trạng thái đến từ nguồn đáng tin.
- Event thuộc đúng đơn/người dùng.
- Cập nhật trạng thái và quyền học có tính nguyên tử/nhất quán cần thiết.
- Callback bị gửi lặp hoặc đồng thời không tạo dữ liệu sai.
- Quyền đọc API được thực thi server-side.
- Khi mạng/DB/đối tác lỗi, hệ thống không báo kết quả giả.

Tăng số unit test quanh \`policy\` từ 40 lên 100 **không tự thay thế** kiểm tra những rủi ro tích hợp đó.

### 10.4. Test concurrency cần xác minh trạng thái bền vững

Ví dụ hành vi giả định:

~~~text
GIVEN don D chua cap quyen
WHEN hai callback thanh cong hop le cua cung mot giao dich
     duoc xu ly gan nhu dong thoi
THEN du lieu don va quyen hoc chi chuyen mot lan theo quy tac
AND khong tao ban ghi trung sai
AND cac tac dung phu quan trong phu hop chinh sach
~~~

Đây là kịch bản khó được bảo vệ chỉ bằng mock trả SUCCESS. Đội có thể cần test với database, unique constraints, transaction và cơ chế xử lý idempotency thực. Nếu có hệ thống nhắn tin hoặc đối tác, cần xem retry, sự kiện lặp và mất kết nối.

**Đừng chuyển mọi trường hợp vào E2E UI test**: xác minh dữ liệu và cạnh tranh đồng thời ở lớp API/integration phù hợp thường đáng tin hơn; giữ một số E2E quan trọng để kiểm tra hành trình.

### 10.5. Kiểm chứng trải nghiệm không thay bằng integration test

Học viên có thể thấy nhãn **“Đang xử lý”** chính xác về kỹ thuật nhưng vẫn không biết:

- Có cần thanh toán lại không?
- Bao lâu nên kiểm tra lại?
- Làm sao nhận trợ giúp?
- Nếu giao dịch đã trừ tiền nhưng chưa hiện quyền thì làm gì?

Những câu hỏi cần **trao đổi nghiệp vụ, thử nội dung thông báo và quan sát người dùng**, ngoài logic trạng thái. Đây là nơi validation bổ sung cho verification.

### 10.6. Đo chất lượng của bản giao

Sau khi xây lát cắt:

| Câu hỏi | Bằng chứng muốn có |
|---|---|
| AC quan trọng có đúng không? | Test run và review kết quả trên build cụ thể |
| Phân quyền có an toàn trong phạm vi kiểm tra không? | Security/API tests nhiều tài khoản, kết quả rà soát phù hợp |
| Callback lặp có gây dữ liệu sai không? | Integration/concurrency tests và ràng buộc database |
| Cần kiểm tra hiệu năng mức nào? | Ngưỡng và tải đại diện theo mục tiêu đã thống nhất |
| Test suite có đáng tin không? | Không bỏ ngầm các gate quan trọng, xử lý flaky có chứng cứ |
| Increment đã Done theo Scrum chưa? | Đủ toàn bộ DoD áp dụng |
| Người dùng đã nhận được kết quả chưa? | Phản hồi thử nghiệm/production phù hợp; outcome và sự cố |

Một bộ evidence tốt nói **đã xác minh điều gì và còn điều gì chưa biết**. Nó không cần tuyên bố rằng “mọi trường hợp đều hoàn hảo”.

## 11. Tình huống xuyên suốt: nhóm có 1.250 test nhưng học viên vẫn không vào được bài

> **Toàn bộ số liệu dưới đây là giả định để học cách phân tích**, không phải dữ liệu của một đội thực tế hay ngưỡng đánh giá chuẩn.

Một nhóm gồm Product Owner, năm Developers, một chuyên gia QA và người phụ trách vận hành phát triển luồng **thanh toán → ghi danh → cấp quyền → xem bài đầu**. Nhóm dùng Sprint hai tuần và Scrum Guide 2020, có Product Goal về tỷ lệ học viên hoàn tất hành trình đăng ký.

Trước đây, nhóm bị đánh giá theo “test count tăng mỗi Sprint”. Nhiều test được tạo ở mức unit, kiểm tra mapping và trạng thái giả; rủi ro DB concurrency và xác thực callback chưa được kiểm tra. Một số integration tests thất bại ngẫu nhiên nên bị quarantine mà chưa có kế hoạch sửa.

### 11.1. Bảng số liệu trước thay đổi

| Chỉ số giả định | Giá trị báo cáo | Điều còn thiếu |
|---|---:|---|
| Test được lưu trong suite | 1.250 | Những test nào thực sự kiểm tra hành vi quan trọng? |
| Test được chọn chạy trong CI chính | 1.150 | 100 test còn lại ở đâu, vì sao không chạy? |
| Test pass trong lượt chạy cuối | 1.138 | 12 fail liên quan gì, có bị bỏ qua/quarantine không? |
| Line coverage | 91% | Kiểm tra assertion, nhánh và rủi ro tích hợp thế nào? |
| Lỗi nghiêm trọng sau release gần nhất | 2 | Ảnh hưởng người dùng, mức nghiêm trọng và cách xử lý? |
| Tỷ lệ học viên đủ điều kiện vào bài đầu thành công | 88% | Định nghĩa, mẫu số, phân đoạn và điều kiện đo? |
| Thời gian trả lời API ghi danh | Chỉ có trung bình | Độ trễ tail và giờ cao điểm thế nào? |

Tỷ lệ pass của những test **được chọn chạy** là:

\[
\frac{1138}{1150}\times100\%\approx98{,}96\%
\]

Đây **không phải 98,96% của tất cả 1.250 test**, càng không phải 98,96% chất lượng phần mềm. Việc 100 test không tham gia lượt CI chính cần được làm rõ thay vì giấu trong mẫu số.

### 11.2. Nhóm đi từ đếm test sang bản đồ rủi ro

Trong phiên cùng Product Owner, Developers, QA và vận hành, nhóm liệt kê các rủi ro:

| Hành vi/rủi ro | Test hiện có | Khoảng trống |
|---|---|---|
| Giao dịch thành công | Nhiều unit tests với mock | Chưa kiểm tra đầy đủ nguồn xác thực/đối chiếu giao dịch thật |
| Giao dịch đang chờ | Một số test mapping | Chưa kiểm tra cấp quyền end-to-end |
| Callback lặp và đồng thời | Hầu như không có | Thiếu integration/concurrency tests và kiểm tra dữ liệu |
| Tài khoản B xem đơn của A | Có test ẩn nút trên UI | Chưa có API authz tests server-side |
| Giờ khai giảng tải cao | Chưa có kịch bản đại diện | Không biết p95/p99 và điểm nghẽn |
| Người học hiểu trạng thái | Có test chuỗi thông báo | Chưa có quan sát người dùng và outcome |
| Khi đối tác ngừng trả lời | Một test timeout giả lập | Chưa kiểm tra reconciliation/khôi phục theo chính sách |

Không cần đặt mục tiêu “thêm 500 test”. Nhóm chọn **kiểm tra rủi ro có ảnh hưởng lớn nhất** và xác định gate nào cần bảo vệ Increment.

### 11.3. Quyết định cải tiến theo từng lát cắt

1. **Làm rõ quy tắc:** Product Owner xác nhận khi nào đơn được xem là thành công và học viên được cấp quyền.
2. **Bảo vệ API:** Developers và QA tạo test nhiều identity, xác minh quyền truy cập ở server.
3. **Sửa tính đúng đắn giao dịch:** kiểm tra idempotency, transaction và ràng buộc dữ liệu trên callback lặp.
4. **Tăng tin cậy CI:** điều tra các test flaky; không tắt test quan trọng mà không ghi rủi ro và điều kiện thay thế.
5. **Kiểm tra tải:** chọn ngưỡng phù hợp với kỳ khai giảng và chạy test representative workload.
6. **Quan sát hành trình:** đo tỷ lệ người học đủ điều kiện vào bài, phân đoạn theo thiết bị/trạng thái và nhận phản hồi.
7. **Bảo vệ DoD:** không gọi PBI Done khi thiếu kiểm chứng bắt buộc, kể cả khi test count đạt mục tiêu.

### 11.4. So sánh hai Sprint theo cách có bối cảnh

Giả sử sau một thời gian thử nghiệm, nhóm ghi nhận:

| Chỉ số giả định | Giai đoạn trước | Giai đoạn sau |
|---|---:|---:|
| Test được lưu trong suite | 1.250 | 1.180 |
| Test đang bị quarantine | 24 | 4 |
| Luồng rủi ro cao có test và evidence phù hợp | 4/8 | 7/8 |
| Lỗi nghiêm trọng sau release trong cửa sổ so sánh | 2 | 0 |
| Tỷ lệ học viên đủ điều kiện vào bài đầu | 88% | 94% |
| Cycle time trung vị của những item tương đồng | 8 ngày | 6 ngày |
| Rủi ro chưa kiểm chứng | Phân quyền API, callback đồng thời, tải cao | Tải cao ở cấu hình triển khai mở rộng |

Không nên tuyên bố rằng **việc giảm 70 test đã gây ra cải thiện**. Nhóm đồng thời sửa logic, môi trường, cách đo và thông điệp; dữ liệu có thể chưa đủ để khẳng định quan hệ nhân quả. Kết luận đáng tin hơn là **nhóm có bằng chứng chất lượng hữu ích hơn**, một số tín hiệu sản phẩm tốt lên và vẫn còn rủi ro cần xử lý trước mở rộng.

Điểm quan trọng: **test count giảm không tự động là xấu**, cũng như tăng không tự động là tốt. Đội đã loại bớt trùng lặp hoặc sửa suite yếu, nhưng phải chứng minh những bảo vệ quan trọng vẫn còn.

### 11.5. Quyết định phát hành theo phạm vi

Giả sử bản đang chuẩn bị mở rộng cho toàn bộ học viên nhưng bài kiểm tra tải cao điểm chưa đạt điều kiện chất lượng đã thống nhất. Các bên có thể:

- Hoãn mở rộng cho tới khi kiểm tra và xử lý điểm nghẽn.
- Phát hành cho nhóm nhỏ đã được phê duyệt, với monitoring và ngưỡng ngừng phù hợp nếu rủi ro chấp nhận được.
- Điều chỉnh phạm vi hoặc hạ tầng thay vì hạ chuẩn an toàn.
- Cập nhật dự báo và người có quyền quyết định nếu rủi ro vượt thẩm quyền đội.

Không thể chỉ nói **“1.180 tests pass nên cứ mở cho tất cả”** khi điều kiện quan trọng chưa được chứng minh. Ngược lại, nếu còn một test thẩm mỹ không ảnh hưởng phạm vi sản phẩm đang release, đội nên đánh giá theo rủi ro và chính sách chứ không nhất thiết coi mọi fail là có mức tác động giống nhau.

### 11.6. Khi Product Owner hỏi “vậy còn KPI của QA?”

Nhóm có thể chuyển cuộc trao đổi:

> **Không tối ưu:** “QA đã tạo bao nhiêu test mỗi Sprint?”
>
> **Có ý nghĩa hơn:** “Những rủi ro có tác động lớn được phát hiện hoặc ngăn sớm đến mức nào? Test/evidence có đáng tin không? Các Increment có đạt DoD không? Người dùng có ít gặp lỗi nghiêm trọng và hoàn thành tác vụ tốt hơn không? Những trở ngại nào cần đội hoặc tổ chức hỗ trợ?”

QA không phải người duy nhất chịu trách nhiệm chất lượng. **Product Owner làm rõ giá trị và ưu tiên; Developers tạo Increment đáp ứng DoD; người có chuyên môn kiểm thử, bảo mật, vận hành và người dùng cùng đóng góp bằng chứng.**

Đánh giá chất lượng theo kết quả của **hệ thống cộng tác**, không biến mọi defect sau release thành lỗi cá nhân của tester cuối cùng chạm vào thẻ.

## 12. Scrum, Kanban và XP: cơ chế hỗ trợ chất lượng liên tục

### 12.1. Scrum: Increment đạt DoD thay vì “đã viết nhiều test”

Scrum dựa trên **minh bạch, kiểm tra và thích ứng**. Theo Scrum Guide 2020:

- **Developers** chịu trách nhiệm tạo mọi khía cạnh của Increment có thể sử dụng và đáp ứng DoD, điều chỉnh kế hoạch để đạt Sprint Goal.
- **Product Owner** chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý Product Backlog hiệu quả.
- **Scrum Master** chịu trách nhiệm về hiệu quả Scrum Team và giúp Scrum được hiểu, áp dụng.
- **Product Goal, Sprint Goal và Definition of Done** là các commitments của ba artifacts.
- **Sprint Review** là dịp kiểm tra kết quả Sprint cùng stakeholders và thích ứng, không phải chỉ lễ báo cáo % test.
- **Sprint Retrospective** là dịp cải thiện chất lượng và hiệu quả, không phải chỉ đếm lỗi.

Nếu có một PBI với 80 tests pass nhưng chưa đáp ứng DoD, **nó không thuộc Increment Done**. Nếu một PBI ít test nhưng đã được kiểm chứng đủ các điều kiện/rủi ro áp dụng, nó có thể Done theo chính sách; vẫn cần xem người dùng có nhận giá trị và có nên phát hành hay không.

### 12.2. Kanban: dòng công việc kiểm chứng không được trở thành hàng chờ vô hình

Một đội có 20 ticket “Dev Complete” và 15 ticket “Waiting for QA” có thể báo nhiều output, nhưng ít item thực sự hoàn tất. Theo tư duy Kanban:

- **Definition of Workflow** nêu điểm bắt đầu, kết thúc, trạng thái và chính sách di chuyển.
- **WIP control** giúp không bắt đầu quá nhiều khi kiểm chứng/tích hợp đang nghẽn.
- Item bị blocked vẫn được tính WIP trong ranh giới đã xác định.
- **WIP, throughput, work item age, cycle time** cho thấy luồng đang chuyển đến Done như thế nào.
- **SLE** mô tả kỳ vọng thời gian hoàn tất với thời gian và xác suất; nó không phải bảo đảm mỗi item đúng hạn.

Kanban không tự bảo đảm sản phẩm đúng; nó giúp nhìn thấy **công việc kiểm chứng chưa xong** để nhóm hỗ trợ hoàn tất thay vì đẩy việc sang hàng đợi khác rồi báo thành công.

### 12.3. XP: kiểm thử và refactoring để chất lượng không bị hoãn cuối

Những thực hành thường gắn với Extreme Programming như **TDD, continuous integration, refactoring, pair programming, simple design, small releases và khách hàng tham gia thường xuyên** giúp:

- Làm rõ yêu cầu qua ví dụ trước khi triển khai.
- Bảo vệ hành vi khi refactor và thay đổi code.
- Phát hiện lỗi tích hợp sớm, khi phạm vi thay đổi còn nhỏ.
- Chia phần mềm thành lát cắt có thể kiểm chứng, tránh batch lớn.
- Nhận phản hồi nghiệp vụ nhanh và đổi ưu tiên dựa trên học tập.

**TDD không thay thế integration, security, usability hoặc operations testing.** Nhưng một vòng kiểm thử tốt cho từng hành vi có thể là nền tảng giúp Developers thay đổi an toàn và giữ nhịp giao hàng bền vững.

### 12.4. Chất lượng và khả năng giao hàng không phải hai mục tiêu hoàn toàn tách rời

Khi thiếu chất lượng liên tục:

~~~text
Code nhiều -> chờ kiểm thử -> phát hiện lỗi lớn
-> làm lại -> trễ release -> thêm WIP -> tiếp tục lỗi
~~~

Khi đầu tư có chủ đích:

~~~text
Làm rõ rủi ro -> chia lát cắt -> test/tích hợp sớm
-> kiểm chứng chất lượng -> Increment Done
-> phản hồi người dùng -> cải tiến
~~~

Không phải lúc nào thêm kiểm thử cũng **ngay lập tức** tăng throughput. Đầu tư chất lượng có thể làm một Sprint gần hoàn tất ít item hơn, nhưng giảm rủi ro và chi phí làm lại ở các chu kỳ sau. Cần đánh giá trên **cửa sổ phù hợp** với loại công việc và so cùng outcome/chất lượng.

## 13. Một quy trình chín bước để đánh giá chất lượng theo kết quả

Đội có thể bắt đầu với **một hành trình hoặc luồng có rủi ro rõ**, không cần xây dashboard chất lượng lớn trước khi hiểu mục tiêu sản phẩm. Quy trình dưới đây là gợi ý thực hành, không phải framework bắt buộc của Scrum, Kanban hoặc XP.

### Bước 1 — Chọn kết quả quan trọng với người dùng

Thay vì “tăng 20% số test”, hãy nêu:

> “Học viên đủ điều kiện đăng ký thành công và vào bài đầu đúng quyền, với trạng thái rõ ràng và ít gặp sự cố trong kỳ khai giảng.”

Làm rõ:

- Người dùng mục tiêu là ai?
- Khi nào coi tác vụ thành công?
- Hành vi nào có thể gây hại hoặc vi phạm nghĩa vụ?
- Có điều kiện tải, thiết bị, trợ năng và kênh nào quan trọng?

### Bước 2 — Liệt kê điều kiện chất lượng và rủi ro

Chọn cả **hành vi đúng** và **hậu quả nếu sai**. Đối với thanh toán: trạng thái giao dịch, cấp quyền, idempotency, phân quyền, timeout, tải và UX. Với khóa học miễn phí: ghi danh trùng, quyền truy cập và tính bền vững của dữ liệu.

Không cần ghi “kiểm tra mọi thứ”. Hãy ưu tiên dựa trên tác động, mức tiếp xúc, tính dễ phát hiện/khôi phục và điều kiện bắt buộc.

### Bước 3 — Viết acceptance examples và guardrails

Trao đổi giữa người chịu trách nhiệm sản phẩm, Developers, người có chuyên môn kiểm thử và vai trò cần thiết (bảo mật, accessibility, vận hành):

~~~text
CASE: Giao dich dang cho
GIVEN trang thai chua duoc xac nhan hop le
WHEN hoc vien mo chi tiet don hang
THEN khong hien thanh cong gia
AND khong cap quyen hoc sai

GUARDRAIL:
  Khong release luong thanh toan voi loi cap quyen trai phep
  da duoc xac nhan va chua duoc kiem soat theo chinh sach.
~~~

Tách **những điều nghiệp vụ cụ thể** khỏi **chất lượng chung của Increment** và những quy định không được hạ.

### Bước 4 — Chọn hoạt động kiểm chứng phù hợp

Với mỗi rủi ro, hỏi: cần kiểm tra ở **logic**, **API**, **database**, **hệ thống tích hợp**, **UI**, **môi trường tải**, **trợ năng** hay **production**?

Ưu tiên kiểm tra tại mức **đáng tin và hiệu quả nhất để phát hiện sai lệch**, rồi dùng một số test xuyên suốt để bảo vệ luồng thật. Đừng chuyển tất cả vào E2E nếu có thể kiểm tra rõ hơn ở API/integration; cũng đừng chỉ dựa unit tests khi rủi ro nằm ở giao tiếp giữa thành phần.

### Bước 5 — Xác lập DoD và điều kiện release

Ghi rõ:

- Khi nào PBI/Increment được xem Done theo tiêu chuẩn chung?
- Những bằng chứng nào phải có trên build hiện tại?
- Những rủi ro nào cần phê duyệt hoặc kiểm soát trước khi cung cấp?
- Có thể phát hành từng nhóm người dùng trong điều kiện nào?
- Ai có quyền quyết định trường hợp ngoại lệ?

Không lấy việc **đủ 100 test** thay cho kiểm chứng đúng các điều kiện ấy.

### Bước 6 — Đo một đường cơ sở có định nghĩa nhất quán

Trước khi cải tiến, ghi:

- Tỷ lệ tác vụ hoàn tất và cách tính mẫu số.
- Lỗi/sự cố đã xác nhận theo mức độ và cửa sổ thời gian.
- Trạng thái các vùng rủi ro chưa được kiểm chứng.
- Chất lượng test suite: skipped, flaky, quarantine.
- Cycle time/WIP hoặc thời gian từ thay đổi tới bằng chứng tích hợp.
- Điều kiện môi trường và quy mô sử dụng.

Nếu chưa có dữ liệu đủ tin cậy, ghi **“chưa đo được”** và cải thiện khả năng thu thập, không tạo số ước đoán như dữ liệu thật.

### Bước 7 — Thử một thay đổi có giả thuyết

Ví dụ:

> “Chúng tôi cho rằng bổ sung integration/concurrency tests cho callback và sửa cơ chế idempotency sẽ giảm lỗi cấp quyền trùng sau release, đồng thời giúp phát hiện sai lệch trước khi mở rộng.”

Để kiểm tra, cần nêu:

1. Hành động cụ thể và phạm vi nhỏ.
2. Những rủi ro hoặc item chịu tác động.
3. Bằng chứng test và chất lượng vận hành được xem.
4. Guardrails không hạ.
5. Thời điểm hoặc điều kiện xem lại.

### Bước 8 — Quan sát cả trong và sau release

Trước release: test đúng build, test environment, integration, security, performance và DoD áp dụng.

Sau release: SLI, sự cố, hỗ trợ, người dùng hoàn tất tác vụ, regression, mức sử dụng theo cohort và hành vi chưa dự đoán. Chỉ mở rộng theo cách có kiểm soát và với quyền quyết định phù hợp.

**Không thử một khả năng có rủi ro chưa kiểm soát lên người dùng thật chỉ để thu dữ liệu nhanh.**

### Bước 9 — Quyết định giữ, sửa, dừng hoặc mở rộng

Đội hỏi:

- Kết quả nào tốt lên, kết quả nào không?
- Có thay đổi đồng thời nào khiến kết luận nhân quả chưa chắc?
- Các bài kiểm thử có đáng tin hơn không?
- Số lượng hoặc severity của sự cố có thay đổi?
- Người dùng có hoàn thành tác vụ tốt hơn không?
- Có nợ kỹ thuật hoặc công việc bị chặn cần tháo gỡ?

Từ đó quyết định tiếp tục đầu tư, thay phương pháp kiểm chứng, sửa workflow hoặc điều chỉnh ưu tiên sản phẩm. **Chất lượng liên tục là chu kỳ ra quyết định, không phải một báo cáo số test cuối Sprint.**

## 14. Những phản mẫu cần tránh khi đo chất lượng

### Phản mẫu 1 — Đặt KPI số lượng test cho mỗi Developer hoặc tester

**Dấu hiệu:** ai tạo nhiều test hơn được coi là làm chất lượng tốt hơn.

**Nguy cơ:** chia nhỏ test vô nghĩa, ưu tiên dễ đếm thay vì rủi ro, che chất lượng assertion.

**Thay thế:** đánh giá khả năng phát hiện/ngăn sai lệch ở vùng rủi ro, độ tin cậy của suite, sự cộng tác và kết quả người dùng ở mức đội.

### Phản mẫu 2 — Xem pass rate là tỷ lệ sản phẩm đúng

**Dấu hiệu:** “98% test pass nghĩa là chất lượng 98%”.

**Nguy cơ:** test không bao phủ yêu cầu, skipped/quarantine bị bỏ ngoài mẫu số.

**Thay thế:** nêu phạm vi test, build/môi trường, vùng chưa kiểm chứng và mức nghiêm trọng của fail.

### Phản mẫu 3 — 100% code coverage là mục tiêu tuyệt đối

**Dấu hiệu:** thêm test không có assertion có nghĩa chỉ để lấp coverage.

**Nguy cơ:** tối ưu chỉ số nhưng thiếu các điều kiện nghiệp vụ và tích hợp.

**Thay thế:** dùng coverage tìm khoảng trống, xem risk/requirement coverage, test quality và kiểm chứng ở các lớp phù hợp.

### Phản mẫu 4 — Bỏ test đỏ khỏi CI rồi báo toàn bộ đã xanh

**Dấu hiệu:** integration tests bị disable nhiều tháng nhưng Release Notes nói “all checks passed”.

**Nguy cơ:** sự cố bị che; người có thẩm quyền ra quyết định trên bằng chứng sai.

**Thay thế:** công bố skipped/quarantine, ghi rủi ro, kế hoạch sửa và chính sách gate.

### Phản mẫu 5 — Mọi lỗi đều có cùng trọng số

**Dấu hiệu:** sửa ba lỗi căn lề được xem “năng suất” cao hơn sửa một lỗ hổng quyền truy cập.

**Nguy cơ:** rủi ro nghiêm trọng không được ưu tiên đúng.

**Thay thế:** phân loại theo ảnh hưởng người dùng, mức độ, khả năng phát hiện/khôi phục và nghĩa vụ.

### Phản mẫu 6 — Chỉ kiểm thử “happy path”

**Dấu hiệu:** thanh toán thành công hoạt động nhưng timeout, PENDING, callback lặp và tài khoản khác chưa được thử.

**Nguy cơ:** sản phẩm lỗi khi gặp điều kiện thông thường của thế giới thật.

**Thay thế:** tạo ví dụ cho trạng thái lỗi, biên, quyền, đồng thời và phụ thuộc theo rủi ro.

### Phản mẫu 7 — Viết Given–When–Then rồi xem như đã có bằng chứng

**Dấu hiệu:** nhiều file Gherkin nhưng chưa có kết quả chạy trên build tích hợp.

**Nguy cơ:** nhầm đặc tả với kiểm chứng.

**Thay thế:** liên kết test execution, dữ liệu, môi trường, kết quả và rủi ro còn mở.

### Phản mẫu 8 — Đồng nhất acceptance test pass với DoD

**Dấu hiệu:** UI đúng một ví dụ nhưng chưa được tích hợp an toàn vẫn chuyển Done.

**Nguy cơ:** Increment chưa dùng được, lỗi phát hiện cuối Sprint.

**Thay thế:** phân biệt AC, tests và DoD; không gọi PBI chưa đạt DoD là phần Increment Done trong Scrum.

### Phản mẫu 9 — Chỉ giao trách nhiệm chất lượng cho QA

**Dấu hiệu:** Developers chuyển “code complete”, QA cuối Sprint phải bắt mọi lỗi.

**Nguy cơ:** hàng chờ dài, phát hiện muộn, đổ lỗi cá nhân.

**Thay thế:** Product Owner làm rõ giá trị, Developers tạo chất lượng trong Increment, chuyên gia kiểm thử/bảo mật/vận hành cùng hỗ trợ từ sớm.

### Phản mẫu 10 — Giảm test suite để chạy nhanh mà không phân tích rủi ro

**Dấu hiệu:** xóa toàn bộ test tích hợp vì pipeline chậm.

**Nguy cơ:** latency CI giảm nhưng lỗi production tăng.

**Thay thế:** tối ưu test data, hạ tầng, phân tầng chạy, loại trùng lặp không cần; giữ các gate có rủi ro cao.

### Phản mẫu 11 — Đo defect escape bằng cách hạn chế báo lỗi

**Dấu hiệu:** yêu cầu hỗ trợ khó mở ticket, lỗi được gọi là “feature request” để thống kê đẹp.

**Nguy cơ:** mất tín hiệu người dùng và cơ hội học.

**Thay thế:** định nghĩa bug, cửa sổ đo và severity nhất quán; khuyến khích báo lỗi trung thực.

### Phản mẫu 12 — Dùng production làm nơi thử lỗi an toàn quan trọng

**Dấu hiệu:** “Có monitoring rồi, không cần kiểm tra phân quyền trước”.

**Nguy cơ:** lỗi gây hậu quả thực trước khi bị phát hiện.

**Thay thế:** kiểm tra rủi ro phù hợp trước release, triển khai có kiểm soát, quan sát và khôi phục đúng chính sách.

### Phản mẫu 13 — Tất cả test phải tự động hóa

**Dấu hiệu:** bỏ thử nghiệm khả năng dùng/accessibility vì không thể biến thành một assertion đơn giản.

**Nguy cơ:** bỏ sót vấn đề trải nghiệm và tác vụ người dùng.

**Thay thế:** tự động hóa những phần lặp lại, có logic rõ; bổ sung exploratory, usability, security/manual testing nơi cần.

### Phản mẫu 14 — Chỉ nhìn trung bình latency

**Dấu hiệu:** latency trung bình đẹp dù một nhóm người dùng chờ rất lâu.

**Nguy cơ:** không phát hiện tail latency, phân đoạn hoặc giờ cao điểm.

**Thay thế:** xem phân phối, cohort, tải, lỗi và mục tiêu dịch vụ theo bối cảnh.

### Phản mẫu 15 — Trộn nhiều metric thành điểm chất lượng duy nhất

**Dấu hiệu:** cộng test pass, coverage và velocity để cho “85% quality”.

**Nguy cơ:** rủi ro không chấp nhận được bị bù bằng hoạt động ít ảnh hưởng.

**Thay thế:** dùng guardrails, bảng evidence và xu hướng theo chiều chất lượng; quyết định trong thẩm quyền phù hợp.

### Phản mẫu 16 — Coi nhiều test sau sửa bug là đủ ngăn tái diễn

**Dấu hiệu:** thêm một regression test nhưng không tìm nguyên nhân dữ liệu, quy trình, thiết kế hoặc môi trường.

**Nguy cơ:** cùng loại lỗi tiếp tục xuất hiện ở nơi khác.

**Thay thế:** kết hợp test phòng ngừa với cải thiện code, hợp đồng, observability và workflow theo kết quả điều tra.

### Phản mẫu 17 — Không định nghĩa mẫu số trước khi so sánh

**Dấu hiệu:** báo conversion tăng nhưng giai đoạn mới đã loại các phiên lỗi khỏi mẫu số.

**Nguy cơ:** nhầm thay đổi cách đo với cải thiện sản phẩm.

**Thay thế:** có metric contract về tập đối tượng, sự kiện, loại trừ và cửa sổ thời gian.

### Phản mẫu 18 — Dùng một kỳ không có lỗi để khẳng định chất lượng hoàn hảo

**Dấu hiệu:** hai tuần không có incident được coi là bằng chứng “không còn bug”.

**Nguy cơ:** người dùng ít, chức năng chưa được dùng hoặc monitoring thiếu cũng có thể khiến lỗi không được phát hiện.

**Thay thế:** đọc độ tin cậy cùng mức sử dụng, các vùng chưa kiểm chứng, rủi ro tiềm tàng và dữ liệu trong nhiều điều kiện.

### Phản mẫu 19 — Thưởng cho việc “không phát hiện lỗi”

**Dấu hiệu:** đội bị đánh giá kém nếu tìm nhiều bug trong Sprint.

**Nguy cơ:** ngại báo lỗi sớm, cuối cùng bug lọt production.

**Thay thế:** khuyến khích minh bạch, phát hiện và sửa nguyên nhân sớm; đánh giá mức độ rủi ro và kết quả sản phẩm thay vì số lỗi gắn với cá nhân.

### Phản mẫu 20 — Chỉ cải tiến test mà không cải tiến cách hiểu yêu cầu

**Dấu hiệu:** test suite chạy ổn nhưng chức năng vẫn giải quyết sai nhu cầu.

**Nguy cơ:** tự động hóa việc làm đúng một sản phẩm sai.

**Thay thế:** Product Owner, Developers và testers trao đổi ví dụ nghiệp vụ; kiểm tra outcome qua người dùng, điều chỉnh backlog theo học tập.

## 15. Mẫu thực hành: từ rủi ro tới bằng chứng

### 15.1. Mẫu quality risk card

~~~text
TEN LUONG / PBI:
  [Vi du: Thanh toan khoa hoc va vao bai dau]

NGUOI DUNG / MUC TIEU:
  [Ai can lam duoc gi?]

RUI RO CAN KIEM CHUNG:
  [Sai giao dich, cap quyen, timeout, performance, usability...]

MUC TAC DONG / NHOM BI ANH HUONG:
  [Khong chi la muc severity; ghi pham vi va dieu kien]

AC / HANH VI CAN DUNG:
  AC-01:
  AC-02:
  AC-03:

PHUONG PHAP KIEM CHUNG:
  [Unit, API, contract, integration, E2E, manual, security, performance...]

BUILD / MOI TRUONG / DU LIEU:
  [Phien ban, config, tai, data set, co che ghi bang chung]

KET QUA DA CO:
  [Run, log da bao ve du lieu, ket qua, nguoi kiem chung]

CHUA CO BANG CHUNG:
  [Rui ro con mo va anh huong]

DOD / DIEU KIEN RELEASE:
  [Phan biet Increment Done va phat hanh cho ai]

NGUOI CO QUYEN QUYET DINH:
  [San pham, ky thuat, bao mat, van hanh neu can]

TRIGGER XEM LAI:
  [Khi co data/load/bug/release moi]
~~~

Không cần mở một biểu mẫu đầy đủ cho mọi bug nhỏ. Mục đích là tránh việc **bằng chứng tồn tại rải rác mà không ai biết có kiểm tra đúng rủi ro chưa**.

### 15.2. Mẫu metric contract để so sánh kết quả

~~~text
TEN CHI SO:
  Ty le hoc vien du dieu kien vao bai dau thanh cong

MUC DICH:
  Danh gia luong dang ky va quyen hoc co tao ket qua nguoi dung khong

DINH NGHIA TU SO:
  So hoc vien/phien hop le da vao duoc bai dau trong cua so duoc chon

DINH NGHIA MAU SO:
  So hoc vien/phien hop le da bat dau luong theo dinh nghia

LOAI TRU:
  Tai khoan noi bo, data test, truong hop khong du dieu kien
  [Neu loai tru, phai co ly do va nhat quan]

CUA SO THOI GIAN:
  [Sau ghi danh bao lau? Khoang ngay nao?]

PHAN DOAN:
  [Khoa mien phi/tra phi, web/mobile, trinh duyet, khu vuc neu phu hop]

NGUON DU LIEU:
  [Event/DB/log/data collection; chinh sach bao ve du lieu]

GIOI HAN:
  [Mat event, nhieu phien mot nguoi, bieu do khong phan anh feedback dinh tinh]

GUARDRAILS:
  [Khong duoc tang ti le bang cach an loi, loai nhom nguoi dung kho]

MOC XEM LAI:
  [Sau ban phat hanh/du lieu/cohort moi]
~~~

Khi định nghĩa thay đổi, ghi **phiên bản metric** hoặc chú thích rõ để tránh so sánh các số không cùng nghĩa.

### 15.3. Mẫu release evidence brief

~~~text
PHAM VI RELEASE:
  [Luon/nhom tinh nang, doi tuong nguoi dung]

BUILD VA MOI TRUONG:
  [Commit/tag, config, mo truong test, du lieu dung]

TINH NANG DA HOAN TAT:
  [Increment dat DoD, hanh vi AC co bang chung]

BANG CHUNG CHAT LUONG:
  [Test runs, security, performance, accessibility, operational checks]

TINH TRANG TEST SUITE:
  [Pass/fail, skipped/quarantine, flaky, gate bi anh huong]

RUI RO CON MO:
  [Tiep xuc, muc tac dong, kha nang phat hien/khac phuc]

GUARDRAILS / PHE DUYET:
  [Dieu kien khong duoc vuot, nguoi co tham quyen]

KE HOACH PHAT HANH:
  [Pham vi dau, monitoring, nguong dung, recovery]

TIN HIEU SAU RELEASE:
  [SLI, loi, outcome, ho tro, thoi diem danh gia]

QUYET DINH:
  [Phat hanh / gioi han / hoan lai / can bang chung bo sung]
~~~

Mẫu không biến mọi Sprint Review thành cuộc họp phê duyệt kỹ thuật. Nó chỉ làm rõ **điều gì thực sự được biết** khi có quyết định cung cấp phần mềm, nhất là với thay đổi nhiều rủi ro.

### 15.4. Mẫu retrospective cho chất lượng

Một Sprint Retrospective có thể chọn **một điểm yếu lặp lại**, ví dụ:

> “Ba PBI liên tiếp có logic đúng ở unit tests nhưng lỗi khi dùng database thật. Chúng ta sẽ bổ sung integration test fixture đáng tin cho một luồng thay đổi thường xuyên, đo thời gian phát hiện hồi quy và số defect ở vùng đó qua hai hoặc ba Sprint. Không đặt mục tiêu tổng số test tăng.”

Mẫu quyết định:

~~~text
HIEU TUONG:
  [Loi nao xuat hien lap? Tai diem nao trong workflow?]

BANG CHUNG:
  [Su co, item age, test run, release, feedback]

GIA THUYET NGUYEN NHAN:
  [Yeu cau mo ho / test data / CI / design / phu thuoc...]

THAY DOI NHO:
  [Mot viec co the thu va đo duoc]

DIEU KHONG DUOC DANH DOI:
  [DoD, an toan, du lieu, chat luong thiet yeu]

TIN HIEU XEM LAI:
  [Thoi gian phat hien loi, do on dinh CI, defect escape, outcome]

NGUOI PHU TRACH / MOC:
  [Vai tro, su kien, khoang thoi gian de danh gia]

QUYET DINH SAU THU:
  [Giu, sua, mo rong, dung]
~~~

Đây là cải tiến **hệ thống**, không phải cuộc họp để hỏi “ai đã viết lỗi đó?”.

## 16. Workshop 90 phút: chuyển từ “thêm test” sang “đúng rủi ro”

Nhóm có thể làm workshop với Product Owner, Developers, tester, người phụ trách vận hành và chuyên gia cần thiết. Thời lượng chỉ minh họa; không phải Scrum event hoặc nghi thức XP bắt buộc.

| Thời lượng | Hoạt động | Sản phẩm đầu ra |
|---|---|---|
| **0–10 phút** | Chọn một hành trình có giá trị và vấn đề đã quan sát | Phát biểu outcome và nhóm người dùng |
| **10–25 phút** | Liệt kê các tình huống thành công, lỗi, quyền, tải, khả năng dùng được | Bản đồ rủi ro và mức tác động |
| **25–40 phút** | Đối chiếu test hiện có, môi trường và bằng chứng | Các khoảng trống; không chỉ số lượng test |
| **40–55 phút** | Chọn kiểm chứng ở từng lớp và xác định guardrails | Chiến lược kiểm thử theo rủi ro |
| **55–70 phút** | Xử lý tình huống “pipeline xanh nhưng lỗi production” | Phương án điều tra, release decision và ưu tiên |
| **70–80 phút** | Thiết kế scorecard với metric contract | Ít chỉ số có định nghĩa và người dùng |
| **80–90 phút** | Thống nhất một thử nghiệm nhỏ và mốc xem lại | Giả thuyết, trách nhiệm và cách kiểm tra kết quả |

### 16.1. Các thẻ vai trò

**Product Owner:** “Học viên đã thanh toán đôi khi không vào được bài, nhưng đội báo 99% test pass. Tôi muốn biết có nên mở rộng cho đợt khai giảng không. Hãy cho tôi rủi ro và lựa chọn, không chỉ số test.”

**Developer:** “Bộ unit tests chạy nhanh nhưng mock luôn trả SUCCESS. Có dấu hiệu callback lặp và tranh chấp ghi dữ liệu. Tôi có thể đưa ra kế hoạch kiểm chứng/ràng buộc dữ liệu.”

**Tester:** “Hai test security quan trọng chưa có bằng chứng trên build hiện tại; bộ E2E bị flaky. Tôi cần phân biệt lỗi hệ thống với lỗi test và đề xuất gate phù hợp.”

**Vận hành:** “Tải giờ cao điểm khác staging; cần định nghĩa SLI, monitoring và phương án giảm ảnh hưởng/khôi phục.”

**Người học/người dùng:** “Trang đơn hiển thị ‘Đang xử lý’ nhưng tôi không biết khi nào được vào bài hoặc có cần thanh toán lại không.”

### 16.2. Tình huống bổ sung giữa workshop

Người hướng dẫn đưa thông tin mới:

> “Có một test truy cập trái quyền thất bại trên build mới. Nhưng 1.249 test khác pass, nhóm marketing muốn phát hành ngay.”

Người tham gia cần làm rõ:

- Test thất bại có thể là lỗi sản phẩm hay test/môi trường? Cần bằng chứng gì?
- Tác động nếu quyền truy cập sai là gì? Ai có thẩm quyền quyết định?
- Có thể cô lập/hoãn phạm vi mà vẫn bảo đảm an toàn không?
- Kết quả test suite có được báo trung thực không?
- Khi nào quyết định phát hành có thể được xem lại?

**Đáp án không thể đơn giản là “99,9% pass nên cho qua”.** Cũng không phải mọi fail đều có mức nguy hiểm giống nhau. Phải xét bản chất rủi ro, trạng thái chứng cứ và guardrails.

### 16.3. Tiêu chí quan sát workshop

Đội làm tốt khi:

1. Nêu rõ **người dùng cần hoàn tất việc gì**.
2. Ưu tiên những rủi ro **có tác động thật**, không chỉ vùng code dễ test.
3. Nêu test nào phù hợp ở **lớp kiểm chứng nào** và vì sao.
4. Có bằng chứng theo build và môi trường thay vì chỉ bảng số lượng.
5. Phân biệt DoD, acceptance và release decision.
6. Nêu rủi ro còn mở trung thực.
7. Có ít chỉ số outcome/quality/flow với định nghĩa rõ.
8. Chọn một thay đổi có thể thử và xem lại thay vì thêm mục tiêu test count tùy ý.

## 17. Bài tập vận dụng

### Bài tập A — Bộ test lớn nhưng sai chỗ

Một nhóm có **2.000 unit tests** kiểm tra validation và mapping. Họ chưa có test kiểm tra phân quyền API, callback thanh toán lặp hay timeout của nhà cung cấp. Lãnh đạo nói “đã có hai nghìn test nên không cần kiểm tra thêm”.

**Yêu cầu:** Phản biện lập luận; nêu ba rủi ro cần ưu tiên và một chiến lược kiểm chứng cụ thể.

<details>
<summary>Gợi ý đáp án</summary>

Test count cho biết số ca test, không nói những rủi ro quan trọng được bao phủ. Nhóm cần kiểm tra server-side authorization bằng các tài khoản khác nhau; dùng integration/concurrency tests với DB để xác minh callback lặp và cấp quyền đúng một lần; thử timeout, trạng thái PENDING và khả năng phục hồi theo chính sách. Có thể bổ sung acceptance examples và E2E cho hành trình đầu-cuối. Cần xem build/môi trường, kết quả thực, DoD và outcome người học thay vì chỉ đếm test.

</details>

### Bài tập B — Tính pass rate và tìm điểm mù

Báo cáo cho biết:

- Có **1.200 test** trong repository.
- CI chọn chạy **1.080 test**.
- Trong đó **1.058 pass**, **22 fail**.
- Một số test không chạy là kiểm tra bảo mật ở môi trường chuyên biệt.

**Yêu cầu:** Tính pass rate của lượt CI đã chọn, giải thích vì sao không được nói “sản phẩm đúng X%”, và nêu bốn thông tin cần bổ sung.

<details>
<summary>Gợi ý đáp án</summary>

Pass rate của lượt chạy là \(1058/1080\times100\%\approx97{,}96\%\). Nó không phải tỷ lệ sản phẩm đúng vì suite có phạm vi giới hạn, 120 test không được chạy trong lượt này và 22 fail có thể thuộc các mức tác động rất khác nhau. Cần biết test nào không chạy và lý do; nội dung/mức nghiêm trọng của fail; build/môi trường/data; các hành vi quan trọng chưa kiểm chứng; độ tin cậy suite; kết quả rủi ro sản phẩm và DoD.

</details>

### Bài tập C — Coverage 100% nhưng một quy tắc sai

Đội có **100% line coverage** cho hàm xét quyền vào khóa. Tuy nhiên, logic dùng:

~~~java
return paymentConfirmed || !accountSuspended;
~~~

Trong khi yêu cầu là phải **có xác nhận thanh toán hợp lệ và tài khoản không bị đình chỉ**.

**Yêu cầu:** Vì sao line coverage không phát hiện sai? Hãy viết bảng tối thiểu ba trường hợp đầu vào và đầu ra đúng.

<details>
<summary>Gợi ý đáp án</summary>

Coverage chỉ cho biết dòng được chạy qua, không bảo đảm assertion về kết quả mong đợi. Với mô hình đơn giản, logic đúng là \`paymentConfirmed && !accountSuspended\`. Các trường hợp cần kiểm tra:

| paymentConfirmed | accountSuspended | Quyền mong đợi |
|---|---|---|
| true | false | Cho phép |
| true | true | Từ chối |
| false | false | Từ chối |
| false | true | Từ chối |

Trong sản phẩm thật phải kiểm tra thêm quyền sở hữu, khóa học, nguồn xác nhận và điều kiện nghiệp vụ khác. Một unit test của hàm trên chưa thể thay thế kiểm tra phân quyền API và dữ liệu.

</details>

### Bài tập D — Một test bảo mật fail giữa 999 test pass

Lượt CI cuối có 999 test pass và 1 test thất bại: tài khoản B có thể truy cập chi tiết đơn hàng của A. Product Owner hỏi có thể phát hành vì tỷ lệ pass là 99,9% không.

**Yêu cầu:** Bạn đề xuất quyết định nào và cần xác minh gì trước khi kết luận?

<details>
<summary>Gợi ý đáp án</summary>

Không dùng trung bình pass rate để bù một lỗi phân quyền nghiêm trọng. Trước hết xác minh test có phản ánh lỗi sản phẩm thật, môi trường, tài khoản và quyền dữ liệu; nếu lỗi đã xác nhận, xử lý theo guardrail và chính sách release, không phát hành phạm vi có rủi ro chưa được kiểm soát. Đội có thể sửa lỗi, kiểm tra regression hoặc giới hạn/hoãn phạm vi có thẩm quyền nếu an toàn và quy định cho phép. Báo cáo trung thực những test đã chạy và rủi ro còn mở.

</details>

### Bài tập E — Tính defect escape ratio

Một release có **27 lỗi được xác nhận trước release** và **3 lỗi được xác nhận sau release** trong cửa sổ theo dõi nhất quán. Release tiếp theo có 42 lỗi trước và 2 lỗi sau.

**Yêu cầu:** Tính tỷ lệ theo công thức trong bài. Có thể kết luận release thứ hai tốt hơn chỉ từ tỷ lệ này không?

<details>
<summary>Gợi ý đáp án</summary>

Release 1: \(3/(27+3)\times100\%=10\%\). Release 2: \(2/(42+2)\times100\%\approx4{,}55\%\). Tỷ lệ release 2 thấp hơn trong định nghĩa này, nhưng không đủ kết luận chất lượng tổng tốt hơn. Cần xem mức nghiêm trọng, lượng người dùng, mức sử dụng, loại công việc, năng lực phát hiện trước release, mức tin cậy của báo lỗi và cửa sổ thời gian. Một lỗi sau release liên quan lộ dữ liệu có thể quan trọng hơn nhiều lỗi UI.

</details>

### Bài tập F — Tỷ lệ hoàn tất tăng vì thay mẫu số

Giai đoạn trước:

- 1.000 phiên bắt đầu ghi danh.
- 850 phiên hoàn tất.

Giai đoạn sau:

- 1.000 phiên bắt đầu.
- 100 phiên gặp lỗi bị loại khỏi báo cáo.
- 810 phiên hoàn tất.

Báo cáo mới công bố **90%** so với **85%** trước đó.

**Yêu cầu:** Phân tích cách thay mẫu số làm kết quả trông tốt lên và đề xuất metric contract.

<details>
<summary>Gợi ý đáp án</summary>

Giai đoạn trước \(850/1000=85\%\). Giai đoạn sau báo \(810/900=90\%\) vì loại 100 phiên lỗi; nếu các phiên đó vẫn thuộc đối tượng đủ điều kiện và là trải nghiệm lỗi thật, phép so sánh đồng nhất sẽ là \(810/1000=81\%\). Không được loại chúng chỉ để làm số đẹp. Cần thống nhất sự kiện bắt đầu/kết thúc, tập người dùng đủ điều kiện, trường hợp loại trừ hợp lý, cửa sổ và cách đếm trùng, đồng thời ghi khi định nghĩa thay đổi. Cần điều tra nguyên nhân 100 phiên lỗi trước khi kết luận.

</details>

### Bài tập G — Test flaky hay bug cạnh tranh?

Một integration test kiểm tra cấp quyền đúng một lần khi nhận hai callback đồng thời. Test fail khoảng một trong mười lần trên CI, pass trên máy Developers. Nhóm muốn gắn \`@Disabled\` và chạy lại cho tới lúc pipeline xanh.

**Yêu cầu:** Tại sao hành động đó rủi ro? Đề xuất kế hoạch điều tra.

<details>
<summary>Gợi ý đáp án</summary>

Test không ổn định có thể là race condition thật trong code hoặc dữ liệu, không chỉ lỗi suite. Cần lưu kết quả, cấu hình, timing, transaction, dữ liệu và concurrency; thử tái hiện có kiểm soát, kiểm tra idempotency, khóa/ràng buộc DB, tính nguyên tử và setup/cleanup của test. Nếu phải quarantine tạm, ghi rủi ro và phương án kiểm chứng thay thế với người có thẩm quyền, không âm thầm bỏ quality gate. Pipeline xanh sau retry không chứng minh không có bug.

</details>

### Bài tập H — Chọn bộ kiểm thử theo rủi ro

Đội chỉ có nguồn lực để bổ sung **ba hoạt động kiểm chứng** trong Sprint. Backlog có: thay biểu tượng khóa, sửa luật phân quyền, thêm phương thức thanh toán mới, đổi cỡ chữ trang chủ, thay retry khi nhà cung cấp timeout.

**Yêu cầu:** Đề xuất ba hoạt động được ưu tiên, giải thích rủi ro và lý do không chỉ chọn những test dễ viết.

<details>
<summary>Gợi ý đáp án</summary>

Một lựa chọn hợp lý: (1) API/security tests phân quyền với nhiều tài khoản; (2) contract/integration tests cho phương thức thanh toán mới, gồm trạng thái và nguồn xác thực; (3) failure/retry/idempotency integration tests cho timeout và callback lặp. Cần xem tính bắt buộc của từng phạm vi và ràng buộc release; các thay đổi UI vẫn phải được kiểm tra theo DoD nhưng không nên ưu tiên số lượng test dễ viết khi rủi ro giao dịch và dữ liệu lớn hơn.

</details>

### Bài tập I — Đánh giá scorecard trước release

Một bản phát hành có:

| Tín hiệu | Kết quả |
|---|---|
| 1.400 test pass | Có |
| Một security test phân quyền chưa chạy trên build mới | Có |
| Trạng thái PENDING đạt AC trên staging | Có |
| Test tải kỳ khai giảng | Chưa có |
| Môi trường vận hành có cảnh báo | Có |
| Đã thử với một nhóm học viên nhỏ | Có |

**Yêu cầu:** Có thể phê duyệt mở rộng ngay cho toàn bộ học viên chỉ từ bảng này không? Cần hành động nào?

<details>
<summary>Gợi ý đáp án</summary>

Không đủ. Cần xác định rủi ro phân quyền và điều kiện tải nào là guardrails của phạm vi dự kiến; chạy/đánh giá kiểm tra chưa có, công bố điều kiện môi trường và dữ liệu thực. Nếu cần, hoãn hoặc giới hạn rollout có kiểm soát theo chính sách và thẩm quyền, không để số test pass bù các khoảng trống. Đội cũng cần đánh giá DoD, khả năng khôi phục, sự cố và kết quả thử người dùng. Có thể phát hành các phần không chịu rủi ro theo phê duyệt phù hợp, nhưng không mặc định mở rộng toàn bộ.

</details>

### Bài tập J — Scrum, Kanban và XP cùng bảo vệ chất lượng

Một Scrum Team có Sprint Goal rõ nhưng cuối mỗi Sprint luôn có bảy PBI “Dev Complete” chờ QA. Đội có TDD cho code mới, nhưng integration tests chỉ được chạy trước release một lần. Người quản lý đề nghị thêm mục tiêu “mỗi Developer viết 30 unit tests”.

**Yêu cầu:** Hãy đề xuất thay đổi có căn cứ từ ba cách tiếp cận.

<details>
<summary>Gợi ý đáp án</summary>

Scrum: làm rõ DoD, không tính PBI chưa đạt DoD là Increment; dùng Daily Scrum và Retrospective để điều chỉnh kế hoạch/quy trình theo Sprint Goal, phối hợp test sớm. Kanban: trực quan hóa bước verification, kiểm soát WIP, xem work item age và kéo việc theo năng lực hạ nguồn. XP: duy trì TDD và thêm CI/integration tests phù hợp, làm thay đổi nhỏ và refactor có test bảo vệ. Đo Increment Done, lỗi, thời gian chờ và outcome chứ không giao KPI test count theo người.

</details>

### Bài tập K — Acceptance test xanh nhưng người học vẫn cần hỗ trợ

Tất cả tests về nhãn trạng thái thanh toán đạt: khi PENDING hiện “Đang xử lý”. Nhưng số người học liên hệ hỗ trợ về việc “khi nào được vào khóa?” vẫn cao.

**Yêu cầu:** Phân biệt verification và validation, đề xuất một thí nghiệm và cách đo.

<details>
<summary>Gợi ý đáp án</summary>

Verification xác nhận UI hiển thị nhãn đúng theo AC trong điều kiện test; validation cho thấy thông điệp có thể chưa giúp người học hiểu bước tiếp theo. Có thể thử nội dung bổ sung về thời điểm kiểm tra và cách liên hệ hỗ trợ với nhóm người dùng phù hợp, quan sát khả năng hoàn tất tác vụ và tỷ lệ yêu cầu hỗ trợ theo mẫu số người dùng. Giữ nguyên tính đúng đắn trạng thái và quyền học; không sử dụng UX experiment để bỏ kiểm tra thanh toán.

</details>

### Bài tập L — Quan hệ nhân quả khi nhiều thứ đổi cùng lúc

Sau khi đội bổ sung integration tests, họ đồng thời nâng database, thay cách đo conversion và triển khai lại UX. Lỗi production giảm và conversion tăng trong hai tuần.

**Yêu cầu:** Có thể tuyên bố “integration tests đã làm conversion tăng” không? Nêu cách diễn giải thận trọng và bước tiếp theo.

<details>
<summary>Gợi ý đáp án</summary>

Chưa thể kết luận quan hệ nhân quả vì nhiều biến đổi xảy ra cùng lúc, cách đo conversion cũng thay đổi và thời gian quan sát ngắn. Có thể nói “gói thay đổi cho tín hiệu tích cực trong giai đoạn này; chúng ta cần xác minh metric contract và theo dõi thêm”. Tiếp tục xem sự cố theo mức độ, outcome theo cohort, rủi ro được kiểm chứng và chất lượng test; nếu cần, thiết kế thí nghiệm/so sánh phù hợp với an toàn và khả năng phân đoạn, không suy luận từ hai điểm dữ liệu.

</details>

## 18. Checklist tự đánh giá chất lượng kết quả

Hãy chọn một **hành trình người dùng thực tế** và trả lời bằng bằng chứng thay vì cảm giác “đã có nhiều test”:

1. Đội có biết **người dùng cần đạt kết quả gì** và tại sao quan trọng không?
2. Có định nghĩa tác vụ **thành công/thất bại** theo nguồn dữ liệu đáng tin không?
3. Test suite hiện kiểm tra những **hành vi và rủi ro cụ thể nào**?
4. Có phân biệt số test được lưu, được chọn chạy, bị skip/quarantine và thực sự pass không?
5. Test quan trọng có assertion có khả năng thất bại khi implementation sai không?
6. Coverage có được dùng để tìm khoảng trống thay vì làm tỷ lệ chất lượng tổng không?
7. Có những AC quan trọng chưa có test hoặc bằng chứng phù hợp không?
8. Các trường hợp lỗi, biên, lặp, đồng thời và tài khoản khác đã được xem xét theo rủi ro chưa?
9. Test trên mock có được bổ sung bằng integration/contract tests khi cần không?
10. Hệ thống có kiểm chứng quyền ở server-side, không chỉ ẩn UI không?
11. Test data và môi trường có đủ đại diện cho phạm vi kết luận không?
12. Có quản lý phiên bản build, môi trường, kết quả chạy và giới hạn test evidence không?
13. Test thất bại có được điều tra và công bố thay vì chạy lại cho tới lúc xanh không?
14. Các test bị quarantine có người chịu trách nhiệm, rủi ro và mốc sửa không?
15. Chất lượng pipeline được xem qua tính ổn định, độ nhanh và khả năng phát hiện hồi quy không?
16. Có phân biệt acceptance criteria/test với Definition of Done không?
17. Một PBI chưa đạt DoD có được giữ ngoài Increment Done trong Scrum không?
18. Đội có kiểm tra khả năng dùng được, accessibility, hiệu năng và bảo mật theo điều kiện sản phẩm không?
19. Có đo độ tin cậy/sự cố production theo mức ảnh hưởng thật không?
20. Chỉ số lỗi sau release có nêu định nghĩa, cửa sổ, mức sử dụng và severity không?
21. Có một hoặc vài chỉ số outcome người dùng đi cùng metric kỹ thuật không?
22. Các tỷ lệ có cùng tử số/mẫu số, điều kiện loại trừ và cửa sổ khi so sánh không?
23. Độ trễ có được nhìn qua phân phối và tải thay vì chỉ trung bình không?
24. Những rủi ro không chấp nhận được có guardrails rõ không?
25. Nếu chất lượng chưa đủ, có thể chọn giảm phạm vi hoặc thay đổi cách triển khai thay vì hạ chuẩn không?
26. Người có thẩm quyền có đủ thông tin để quyết định release theo phạm vi không?
27. Kanban/WIP có giúp tránh hàng chờ “Dev Complete chờ QA” vô hạn không?
28. TDD, CI, refactoring có được chọn để bảo vệ thay đổi hay chỉ để đạt điểm số công cụ không?
29. Sprint Review/feedback có dùng Increment thật và dữ liệu người dùng không?
30. Retrospective có đưa ra một cải tiến chất lượng nhỏ có thể đo/quan sát không?
31. Nhóm có khuyến khích báo lỗi sớm và trung thực thay vì thưởng cho số lỗi bằng không không?
32. Nếu số test giảm nhưng bằng chứng quan trọng tốt hơn, nhóm có biết đánh giá đúng không?
33. Nếu số test tăng nhưng lỗi người dùng vẫn tăng, nhóm có điều tra rủi ro và nguyên nhân không?
34. Có đang nhầm một giai đoạn chưa thấy lỗi với bằng chứng mọi trường hợp đều đúng không?
35. Những thay đổi quy trình có được xem lại theo outcome, rủi ro, chất lượng và khả năng giao hàng bền vững không?

Nếu nhiều câu trả lời chưa rõ, hãy bắt đầu từ **một luồng có rủi ro hoặc đau đớn rõ nhất**. Liệt kê ba điều có thể đi sai và hậu quả, tìm test/evidence hiện có, bổ sung một cách kiểm chứng phù hợp, rồi xem thay đổi có cải thiện chất lượng thực hay không. **Không cần bắt đầu bằng mục tiêu thêm hàng trăm test.**

## 19. Tổng kết

- **Test count đo số test, không đo trực tiếp chất lượng sản phẩm.** Mỗi test có độ sâu, phạm vi, assertion và khả năng phát hiện lỗi khác nhau.
- **Pass rate cần đúng mẫu số và bối cảnh.** Một test bảo mật thất bại có thể quan trọng hơn hàng nghìn test thành công; test bị skip, quarantine hoặc không chạy phải được công bố.
- **Code coverage không đồng nghĩa correctness.** Ngay cả 100% line/branch coverage cũng có thể bỏ sót yêu cầu sai, lỗi tích hợp, quyền, cạnh tranh, hiệu năng hoặc trải nghiệm.
- **Đánh giá chất lượng theo nhiều chiều:** tính đúng đắn, tin cậy, bảo mật, khả năng truy cập, hiệu năng, khả năng sử dụng và vận hành tùy bối cảnh.
- **Liên kết nhu cầu → AC → kiểm thử → evidence → DoD → outcome.** Các mắt xích hỗ trợ nhau nhưng không thể đánh đồng.
- **Kiểm thử theo rủi ro** để đặt công sức vào hành vi và hậu quả quan trọng, không phân bổ chỉ dựa trên số dòng code hoặc mục tiêu test count.
- **Dùng nhiều lớp bằng chứng**: unit, API, integration, E2E, exploratory, security, accessibility, performance và production observation khi phù hợp.
- **Bộ test phải đáng tin.** Flaky, skipped, test data yếu hoặc mock không thực tế có thể làm tín hiệu sai; CI nhanh chỉ có giá trị khi kiểm tra đúng điều cần kiểm tra.
- **Quality scorecard nên có guardrails.** Không cộng coverage, test pass và velocity thành một “tỷ lệ chất lượng” có thể bù một lỗ hổng nghiêm trọng.
- **Scrum bảo vệ Increment và DoD; Kanban làm rõ dòng công việc chưa hoàn tất; XP giúp tạo kiểm thử và tích hợp thường xuyên.** Các cơ chế đều hướng tới phản hồi sớm và chất lượng bền vững.
- **Đo kết quả người dùng và vận hành**, đồng thời cẩn trọng với mẫu số, cohort, severity, điều kiện môi trường và những thay đổi đồng thời khi so sánh trước–sau.
- **Chất lượng liên tục là học và cải tiến theo bằng chứng**, không phải một cuộc thi số test mỗi Sprint.

Trước một lần phát hành, câu hỏi tốt không phải:

> “Chúng ta đã viết thêm được bao nhiêu bài kiểm thử?”

Mà là:

> **“Người dùng cần hoàn thành điều gì, những rủi ro có tác động lớn đã được kiểm chứng trên phiên bản nào, điều gì còn chưa biết, chất lượng tối thiểu đã được giữ và kết quả sử dụng thực tế cho thấy chúng ta nên cải tiến điều gì tiếp?”**

Khi trả lời được những câu hỏi ấy với bằng chứng cụ thể, đội đã chuyển từ **đếm hoạt động kiểm thử** sang **đánh giá chất lượng của kết quả**.

## Tài liệu tham khảo định hướng

- [Manifesto for Agile Software Development](https://agilemanifesto.org/): giá trị phần mềm hoạt động được, hợp tác khách hàng và phản hồi thay đổi.
- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html): chú trọng chất lượng kỹ thuật và thiết kế tốt, giao sản phẩm thường xuyên và cải tiến liên tục.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html): Scrum accountabilities, Increment và Definition of Done; Sprint Review, Sprint Retrospective và minh bạch–kiểm tra–thích ứng.
- [The Kanban Guide](https://kanbanguides.org/the-kanban-guide/): Definition of Workflow, kiểm soát WIP, SLE, throughput, cycle time và work item age.
- **Kent Beck — _Test-Driven Development: By Example_**: vòng Red–Green–Refactor và cách dùng test làm phản hồi cho thiết kế.
- **Lisa Crispin & Janet Gregory — _Agile Testing: A Practical Guide for Testers and Agile Teams_**: cộng tác chất lượng, kiểm thử trong Agile và những chiến lược kiểm chứng nhiều góc nhìn.
- [Cucumber — Gherkin Reference](https://cucumber.io/docs/gherkin/reference/): ví dụ Given–When–Then trong specification by example/BDD; cần có thực thi và bằng chứng riêng.
- [Google SRE Book — Service Level Objectives](https://sre.google/sre-book/service-level-objectives/): SLI, SLO và thực hành quản lý độ tin cậy dịch vụ.
- [DORA](https://dora.dev/): nghiên cứu và hướng dẫn về năng lực giao phần mềm, chất lượng thay đổi và vận hành tin cậy.
- [W3C Web Accessibility Initiative (WAI)](https://www.w3.org/WAI/): hướng dẫn thiết kế và kiểm tra khả năng truy cập của ứng dụng web.
- [OWASP Web Security Testing Guide](https://owasp.org/www-project-web-security-testing-guide/): các lĩnh vực và kỹ thuật kiểm tra bảo mật ứng dụng web theo rủi ro.
- [ISTQB](https://www.istqb.org/): thuật ngữ và kiến thức nền về kiểm thử, cách thiết kế hoạt động kiểm chứng và quản lý chất lượng.
