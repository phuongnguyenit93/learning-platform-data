# Kết hợp lập trình cặp, rà soát mã và chia sẻ kiến thức

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích mục đích và điểm khác nhau giữa **lập trình cặp (pair programming)**, **rà soát mã (code review)** và **chia sẻ kiến thức (knowledge sharing)** trong phát triển phần mềm Agile.
2. Thực hành vai trò **driver – navigator**, chuyển vai, đặt câu hỏi, kết hợp kiểm thử và thiết kế trong một phiên pairing trực tiếp hoặc từ xa.
3. Thiết kế quy trình **pull request/code review** giúp phát hiện rủi ro và cải thiện code mà không tạo hàng chờ hoặc trở thành công cụ phê bình cá nhân.
4. Chọn đúng hình thức hợp tác cho từng tình huống: ghép cặp, review bất đồng bộ, walkthrough, mentoring, ensemble programming hoặc tài liệu quyết định ngắn.
5. Chuyển kiến thức quan trọng từ hiểu biết riêng của một người thành **năng lực chung của đội**, tránh điểm nghẽn phụ thuộc cá nhân.
6. Đánh giá hiệu quả bằng dữ liệu chất lượng, khả năng giao hàng và mức phân tán hiểu biết, thay vì đếm số comment hoặc số giờ ngồi cùng nhau.

## 1. Vì sao phải kết hợp ba thực hành?

Trong một đội Agile, tốc độ viết code của từng cá nhân không bảo đảm đội giao được phần mềm **dùng được, an toàn và dễ thay đổi**. Code có thể chạy trên máy tác giả nhưng chưa đáp ứng quy tắc nghiệp vụ; người khác không hiểu cách sửa; hoặc pull request nằm chờ nhiều ngày làm tăng thời gian giao giá trị.

Ba thực hành hỗ trợ những điểm khác nhau:

| Thực hành | Câu hỏi trọng tâm | Giá trị thường mang lại |
| --- | --- | --- |
| **Pair programming** | Trong lúc tạo giải pháp, làm sao hai người suy nghĩ và kiểm chứng cùng nhau? | Phản hồi ngay, làm rõ giả định, học trực tiếp và giảm lỗi được phát hiện quá muộn. |
| **Code review** | Trước khi tích hợp/phát hành theo chính sách, thay đổi đã đúng, rõ và an toàn chưa? | Cái nhìn độc lập, phát hiện rủi ro, bảo vệ chuẩn kỹ thuật, truyền kiến thức qua thay đổi cụ thể. |
| **Knowledge sharing** | Sau công việc này, đội có cùng hiểu biết để tiếp tục và hỗ trợ hệ thống không? | Giảm phụ thuộc cá nhân, nâng khả năng phối hợp, onboarding và duy trì sản phẩm. |

**Không phải ba bước máy móc bắt buộc cho mọi dòng code**. Có công việc nên pair trước khi viết vì nghiệp vụ khó; có thay đổi nhỏ chỉ cần review ngắn; có quyết định kiến trúc cần thảo luận, ghi lại và truyền đạt rộng hơn một PR.

### Ví dụ mở đầu

Đội nền tảng học trực tuyến triển khai tính năng **“Tiếp tục học”**:

- Developer A biết API tiến độ nhưng chưa hiểu đầy đủ quy tắc quyền truy cập.
- Developer B hiểu luồng xác thực và các lỗi liên quan nhiều tài khoản.
- Tester C đã thấy lỗi gửi lại request làm tiến độ bị ghi trùng.
- Các thành viên còn lại thường chỉ biết kết quả cuối cùng qua một pull request dài.

Nếu A viết hết code một mình và B chỉ duyệt vội sau ba ngày, lỗi phân quyền có thể được phát hiện quá muộn. Nếu A và B **pair ở phần nhiều bất định**, C cung cấp **ví dụ kiểm chứng**, sau đó một reviewer khác đánh giá **thay đổi và tác động tích hợp**, đội có nhiều cơ hội bắt lỗi sớm và học quy tắc. Một buổi walkthrough ngắn sau đó giúp người trực vận hành cũng hiểu điểm rủi ro.

> Mục tiêu không phải tăng số người chạm vào mỗi dòng code, mà là **đưa đúng kiến thức, phản hồi và trách nhiệm chất lượng đến đúng thời điểm**.

## 2. Cơ chế bổ sung: phản hồi trong lúc làm, sau khi làm và qua thời gian

~~~mermaid
flowchart TD
    A["Nhu cầu + ví dụ + rủi ro"] --> B["Cùng làm rõ: sản phẩm, developer, tester"]
    B --> C["Pair có chọn lọc: thiết kế + code + test"]
    C --> D["CI: build và kiểm thử tự động"]
    D --> E["Code review theo chính sách"]
    E --> F{"Đạt chất lượng và tích hợp?"}
    F -- "Chưa" --> C
    F -- "Đạt" --> G["Increment sử dụng được theo DoD"]
    G --> H["Walkthrough, tài liệu quyết định, phản hồi thực tế"]
    H --> I["Đội cập nhật cách làm và kiến thức chung"]
    I --> B
~~~

Sơ đồ là một **vòng phản hồi minh họa**, không bắt buộc tất cả item đều phải qua buổi pair, buổi walkthrough hoặc cuộc họp riêng. Có những kiểm tra CI có thể chạy trước, trong và sau review; có thể có review trong lúc pair; và việc chia sẻ kiến thức diễn ra xuyên suốt chứ không chỉ sau khi Done.

### Ba chiều của phản hồi

1. **Phản hồi tức thì** khi pair: người cùng làm nhìn thấy sai giả định, tên gọi mơ hồ hoặc thiếu test ngay lúc quyết định hình thành.
2. **Phản hồi độc lập** khi review: một người không bị cuốn vào từng quyết định nhỏ có thể hỏi về hành vi, tính tương thích, bảo mật và rủi ro hệ thống.
3. **Phản hồi dài hạn** qua chia sẻ kiến thức: đội hiểu vì sao giải pháp được chọn, biết vận hành và thay đổi tiếp mà không phải hỏi đúng một chuyên gia.

Không có cơ chế nào thay thế hoàn toàn hai cơ chế còn lại trong mọi bối cảnh. Pairing không tự chứng minh chất lượng; review không tự biến kiến thức thành kỹ năng; tài liệu không thay được việc kiểm chứng trên sản phẩm thật.

## 3. Lập trình cặp là gì?

**Pair programming** là cách hai người cộng tác chặt chẽ trên **một vấn đề và một dòng công việc**, cùng chịu trách nhiệm tìm hiểu, thiết kế, thực hiện và kiểm chứng kết quả. Hai người có thể ở cùng một máy hoặc kết nối từ xa qua chia sẻ màn hình và công cụ phù hợp.

Một cách tổ chức phổ biến:

- **Driver:** thao tác bàn phím, viết test/code hoặc thực hiện thay đổi đang được bàn bạc.
- **Navigator:** quan sát ở mức ý định, kiểm tra giả định, trường hợp biên và hướng thiết kế; đặt câu hỏi, xem điều gì cần làm tiếp.
- **Đổi vai:** để cả hai cùng tham gia điều khiển và suy nghĩ, tránh một người gõ suốt còn người kia chỉ nhìn.

Driver và navigator **không phải chức danh cố định**. Trong một phiên hiệu quả, hai người liên tục trao đổi, thử giả thuyết, phản biện tôn trọng và điều chỉnh cách làm.

### Pair programming khác gì?

| Tình huống | Có phải pairing hiệu quả không? | Lý do |
| --- | --- | --- |
| Hai người cùng suy nghĩ về một test, một người gõ, người kia kiểm tra rủi ro, rồi đổi vai | Có | Cùng chịu trách nhiệm và phản hồi liên tục. |
| Một người code, người kia mở cửa sổ khác và xử lý ticket riêng | Không đúng nghĩa | Không có chú ý chung hoặc phản hồi đủ kịp thời. |
| Chuyên gia đọc hướng dẫn dài, người mới ngồi nhìn và không được thử | Chủ yếu là trình diễn | Có thể hữu ích cho onboarding nhưng cần tăng tương tác nếu gọi là pairing. |
| Hai người cùng gỡ lỗi sản xuất với quyền thực hiện rõ và kiểm chứng giả thuyết | Có thể | Nếu cùng tập trung một vấn đề, trao đổi quyết định và xử lý an toàn. |
| Một người xem PR của người kia vào ngày hôm sau | Thường là code review | Phản hồi bất đồng bộ sau khi phần lớn code đã viết. |
| Ba đến năm người cùng thiết kế và viết một lát cắt quan trọng | Có thể là ensemble/mob programming | Là hình thức cộng tác rộng hơn, chi phí phối hợp cao hơn. |

Pairing **không bắt buộc hai người có cùng trình độ**, nhưng cả hai cần có cơ hội đóng góp. Người có nhiều kinh nghiệm không nên dùng phiên pair như một cách kiểm soát cá nhân.

## 4. Khi nào pairing đáng đầu tư?

Pairing dùng thêm sự chú ý đồng thời của hai người, vì vậy nên chọn theo **giá trị phản hồi và chi phí rủi ro**, thay vì áp đặt 100% thời gian cho mọi đội.

| Hoàn cảnh | Vì sao pairing có thể hữu ích | Điều nên kiểm tra |
| --- | --- | --- |
| Logic nghiệp vụ nhiều ngoại lệ | Hai góc nhìn giúp phát hiện trường hợp thiếu trước khi code nhiều. | Ví dụ và tiêu chí chấp nhận đã đủ rõ chưa? |
| Thay đổi liên quan bảo mật, dữ liệu, giao dịch | Dễ phát hiện giả định sai với hậu quả lớn. | Có cần review độc lập hoặc phê duyệt chính thức bổ sung không? |
| Một người là chuyên gia duy nhất của module | Truyền hiểu biết qua công việc thực, giảm bus factor. | Người thứ hai có trực tiếp thực hành và giải thích được không? |
| Onboarding developer mới | Học cách chạy test, CI, kiến trúc, conventions nhanh hơn qua tương tác. | Có phân chia vai phù hợp và lộ trình tăng tự chủ không? |
| Bug khó tái hiện hoặc hệ thống lạ | Tách vai quan sát giả thuyết và thao tác thử. | Có dữ liệu, môi trường và quyền truy cập an toàn không? |
| Thiết kế API tích hợp nhiều thành phần | Hai bên kiểm tra hợp đồng và ranh giới. | Có cần thêm product/tester hoặc người sở hữu API đối tác không? |
| Refactoring có nhiều ràng buộc | Dễ giữ hành vi hiện có và tránh tạo abstraction dư. | Test có bảo vệ thay đổi không? |

### Khi chưa chắc pairing phù hợp

- Một chỉnh sửa tài liệu rất nhỏ, ít rủi ro và đã có tiêu chuẩn rõ.
- Hai người không có cùng múi giờ hoặc không thể có phiên chú ý chung; review bất đồng bộ có thể hiệu quả hơn.
- Công việc cần thời gian nghiên cứu độc lập trước; có thể **nghiên cứu riêng – đồng bộ ngắn – thực hiện cùng**.
- Phiên pair liên tục khiến một thành viên mệt mỏi hoặc không có không gian suy nghĩ; nên điều chỉnh thời lượng và nhịp.

Một đội có thể **pair theo rủi ro**: ví dụ phần phân quyền hoặc migration được pair; chỉnh nhãn đơn giản được review ngắn. Đây là **chính sách ví dụ**, không phải quy tắc XP bắt buộc.

## 5. Cách tổ chức một phiên pair có mục tiêu

Một phiên pairing nên có **mục đích, giới hạn và bằng chứng kết quả**, thay vì “hai người cùng ngồi cho đến khi hết giờ”.

### Trước phiên

1. **Chốt câu hỏi:** Cần làm hành vi gì hoặc giảm bất định nào?
2. **Đọc ngữ cảnh:** User story, tiêu chí chấp nhận, DoD/chính sách chất lượng và ràng buộc dữ liệu.
3. **Chọn người bổ sung góc nhìn:** Không nhất thiết “senior + junior”; có thể là developer biết API với developer hiểu phân quyền.
4. **Kiểm tra môi trường:** Test chạy được, quyền truy cập phù hợp, không chia sẻ bí mật qua công cụ không được phép.
5. **Chốt khung thời gian ban đầu:** Ví dụ 45–60 phút rồi nghỉ/đánh giá; đây chỉ là cách tổ chức tham khảo.

### Trong phiên

1. Nêu **hành vi kỳ vọng** bằng một ví dụ cụ thể.
2. Driver viết một bước nhỏ, navigator quan sát cả điều đang làm và rủi ro còn thiếu.
3. Hai người **nói rõ ý định**, đặt câu hỏi thay vì tự sửa code người khác.
4. Đổi vai theo mốc tự nhiên: sau một test, sau một thay đổi nhỏ hoặc khi người kia cần kiểm tra giả thuyết.
5. Chạy test sớm và thường xuyên, không đợi viết hết luồng.
6. Khi có quyết định vượt phạm vi, ghi lại câu hỏi cần xác nhận với Product Owner/Tester hoặc người chịu trách nhiệm.

### Kết thúc phiên

- Code/test nào đã hoàn thành, trạng thái CI và DoD đến đâu?
- Còn rủi ro, giả định hoặc câu hỏi gì?
- Có quyết định kiến trúc/nghiệp vụ nào cần truyền cho đội?
- Người còn lại có thể tiếp tục một phần việc **mà không cần chuyên gia luôn kèm** không?
- Bước tiếp theo nên là review độc lập, chạy test tích hợp, thêm ví dụ hay tạo tài liệu ngắn?

Không cần lập biên bản dài. Một PR rõ ngữ cảnh, test và vài câu ghi quyết định thường đủ cho thay đổi nhỏ.

## 6. Driver – navigator: kỹ thuật giao tiếp cụ thể

### Ví dụ trao đổi tốt

> **Driver:** “Tôi sẽ lọc những bản ghi tiến độ có tài khoản trùng với người đang đăng nhập.”
>
> **Navigator:** “Nếu khóa học vừa bị thu hồi quyền thì bản ghi đó vẫn được chọn à? Chúng ta cần test trường hợp nào?”
>
> **Driver:** “Đúng, tôi đang thiếu điều kiện quyền học. Mình viết test trước rồi bổ sung.”
>
> **Navigator:** “Sau test này mình đổi vai nhé. Tôi sẽ thử cách đặt tên để người đọc thấy rõ chính sách.”

### Ví dụ cần điều chỉnh

> **Người nhiều kinh nghiệm:** “Sai rồi, đưa chuột đây. Làm như tôi bảo.”
>
> **Người còn lại:** “Vâng.”

Vấn đề không phải chỉ là thái độ khó chịu: cách này **giảm cơ hội bộc lộ suy luận**, khiến người ít kinh nghiệm không dám nêu rủi ro, và làm mục tiêu chia sẻ kiến thức thất bại.

### Một số kỹ năng hữu ích

- **Nói về code, không định danh con người:** “Trường hợp lỗi này chưa được kiểm tra”, không nói “Bạn luôn bất cẩn”.
- **Hỏi mở:** “Điều gì xảy ra khi request gửi lại?” tốt hơn “Bạn biết thế này là sai không?”.
- **Tranh luận bằng ví dụ và test:** Nếu hai người hiểu quy tắc khác nhau, tạo ví dụ rồi xác minh với người có thẩm quyền.
- **Đổi vai chủ động:** Người mới nên có cơ hội driver, người nhiều kinh nghiệm có thể làm navigator.
- **Cho không gian suy nghĩ:** Không cần nói liên tục; những khoảng im lặng ngắn để đọc test hoặc suy luận là bình thường.
- **Tôn trọng khả năng tập trung và tiếp cận:** Hỗ trợ phóng to màn hình, bàn phím, công cụ chia sẻ và nhịp nghỉ phù hợp.

**Pairing là cộng tác chuyên môn, không phải giám sát trực tiếp năng suất của một người.**

## 7. Kết hợp pairing với TDD và thiết kế đơn giản

**Test-Driven Development (TDD)** thường dùng vòng **Red – Green – Refactor**: viết test cho hành vi, viết phần code đủ để test đạt, rồi cải thiện cấu trúc mà giữ nguyên hành vi.

Pairing có thể chia vai tự nhiên:

| Pha | Driver thường làm | Navigator thường tập trung |
| --- | --- | --- |
| **Red** | Viết test cho một trường hợp quan trọng. | Câu hỏi về ý nghĩa nghiệp vụ, dữ liệu biên, lỗi an toàn. |
| **Green** | Viết thay đổi nhỏ để test đạt. | Tránh phức tạp không cần, nhận diện phụ thuộc, kiểm tra ranh giới. |
| **Refactor** | Đổi tên, tách hàm hoặc loại trùng lặp có kiểm soát. | Xác nhận hành vi giữ nguyên, code bộc lộ ý định, test hồi quy. |
| **Tích hợp** | Chạy build, test, chuẩn bị PR theo chính sách. | Kiểm tra tác động liên module, DoD, thông tin cần truyền cho reviewer. |

### Ví dụ cùng chọn một test

Story: “Học viên chỉ mở được bài gần nhất mà tài khoản còn quyền truy cập.”

Driver đề xuất test **“chọn bản ghi mới nhất”**. Navigator lưu ý: “Bản ghi mới nhất có thể thuộc khóa đã hết quyền”. Cả hai thống nhất viết test:

> **Given** học viên có bài 3 của khóa X lúc 9 giờ, còn quyền, và bài 8 của khóa Y lúc 10 giờ, đã hết quyền; **when** chọn bài tiếp tục; **then** trả bài 3 của X.

Sau khi test bảo vệ hành vi, đội mới viết logic lọc quyền và chọn thời điểm. **Không cần kiến trúc plugin cho mọi loại nội dung tương lai** nếu phạm vi hiện tại chưa yêu cầu; nhưng phân quyền là ràng buộc đã biết, không thể áp dụng YAGNI để bỏ qua.

TDD và pairing **không tự thay thế** kiểm thử bảo mật phía dịch vụ, test tích hợp hoặc đánh giá quyền riêng tư. Chúng giúp phản hồi sớm hơn và nâng chất lượng thiết kế trong phạm vi có kiểm tra.

## 8. Code review là gì và để phục vụ điều gì?

**Code review** là quá trình người khác xem thay đổi code và ngữ cảnh liên quan để nhận diện vấn đề, kiểm chứng ý định và cải thiện tính dễ hiểu, an toàn, bảo trì hoặc tương thích.

Review có thể diễn ra:

- **Trực tiếp** trong pairing hoặc walkthrough.
- **Bất đồng bộ** qua pull request, diff và comment.
- **Có định hướng rủi ro** với chuyên gia liên quan như bảo mật, dữ liệu, vận hành.

Trong nhiều tổ chức, review trước merge là **chính sách chất lượng**; một số thay đổi còn đòi phê duyệt độc lập do quy định hoặc trách nhiệm quản trị. **Đã pair không tự động miễn review** nếu chính sách yêu cầu người phê duyệt độc lập.

### Review có mục tiêu gì?

| Mục tiêu | Câu hỏi ví dụ |
| --- | --- |
| **Tính đúng đắn** | Thay đổi có đáp ứng tiêu chí chấp nhận và trường hợp lỗi? |
| **An toàn và dữ liệu** | Có thể truy cập sai tài khoản, ghi trùng, lộ dữ liệu hoặc bỏ kiểm tra quyền? |
| **Tính tương thích** | API, schema, cấu hình và phần cũ có còn hoạt động? |
| **Khả năng bảo trì** | Tên, cấu trúc và trách nhiệm có rõ; có abstraction dư hoặc trùng quy tắc? |
| **Kiểm thử** | Test có kiểm chứng hành vi quan trọng và đủ tin cậy? |
| **Vận hành** | Có log, metric, rollout, rollback hoặc migration khi cần? |
| **Học hỏi** | Có quyết định nào mà đội nên biết để hỗ trợ hoặc phát triển tiếp? |

Review **không phải chỉ kiểm tra style**: những lỗi định dạng nên giao cho formatter/linter khi khả thi, dành sự chú ý của con người cho điều cần suy luận.

## 9. Chuẩn bị pull request dễ review

Một PR quá lớn, thiếu ngữ cảnh hoặc thiếu kiểm thử dễ làm thời gian chờ tăng, thậm chí reviewer bỏ sót rủi ro quan trọng.

### PR có thể tự giải thích

Một mô tả PR gọn có thể gồm:

~~~text
TIÊU ĐỀ: Chỉ hiển thị bài gần nhất mà học viên còn quyền truy cập

VÌ SAO:
  Học viên có thể nhìn thấy nút mở bài thuộc khóa đã hết quyền.

THAY ĐỔI:
  - Lọc tiến độ theo tài khoản xác thực hiện tại.
  - Loại khóa học hết quyền trước khi chọn bản ghi mới nhất.
  - Thêm trạng thái không có bài học hợp lệ.

KHÔNG BAO GỒM:
  - Đồng bộ vị trí video giữa thiết bị.
  - Tải nội dung offline.

KIỂM CHỨNG:
  - Test chọn bài hợp lệ và bản ghi hết quyền.
  - Test không lộ tiến độ của tài khoản khác.
  - CI/build và integration test liên quan đạt.

RỦI RO / CẦN REVIEW KỸ:
  - Cách tính quyền học khi khóa vừa bị thu hồi.
  - Tương thích với client cũ khi không có dữ liệu.

TRIỂN KHAI:
  - Không có migration; cần quan sát lỗi đọc tiến độ sau release.
~~~

Đây chỉ là **mẫu tham khảo**, không phải biểu mẫu phải điền đầy đủ cho một lỗi chính tả. Mức độ chi tiết nên tương ứng mức rủi ro.

### Giữ PR tập trung

- Một PR nên có **mục đích rõ**, tránh trộn refactor lớn không liên quan vào sửa lỗi khẩn.
- Đổi format hàng trăm dòng cùng logic nghiệp vụ thường làm diff khó đọc; cân nhắc tách khi an toàn.
- Bổ sung test cho rủi ro quan trọng và mô tả cách kiểm chứng.
- Chỉ nhờ đúng reviewer có kiến thức và quyền cần thiết, không ping cả tổ chức.
- Nếu PR phải lớn vì migration hoặc thay đổi giao diện diện rộng, **nêu rõ cách xem** và các phần rủi ro; không chia hình thức đến mức không kiểm chứng được tính tương thích.

**PR nhỏ hơn thường dễ review hơn**, nhưng đây là xu hướng cần thử và đo trong từng bối cảnh, không phải giới hạn số dòng bắt buộc.

## 10. Một quy trình code review có phản hồi nhanh

### Bước 1 — Tác giả tự kiểm tra

Trước khi mời review, tác giả đọc diff như người khác, chạy những kiểm thử liên quan và làm rõ thay đổi. Tránh đẩy trách nhiệm cơ bản sang reviewer.

### Bước 2 — Reviewer hiểu mục đích

Đọc user story, bug report, tiêu chí chấp nhận, mô tả PR và ràng buộc liên quan. Khi chưa hiểu *vì sao* thay đổi tồn tại, cần hỏi trước khi kết luận về kiến trúc.

### Bước 3 — Tập trung vào rủi ro trọng yếu

Xem dữ liệu, bảo mật, quyền, lỗi, trường hợp cạnh tranh, tích hợp và khả năng rollback trước; sau đó xem thiết kế, tên gọi và khả năng duy trì. Không để tranh luận dấu cách che một lỗi lộ dữ liệu.

### Bước 4 — Phản hồi cụ thể, tôn trọng

Đưa ra **vị trí, tình huống, hậu quả, đề xuất hoặc câu hỏi**; phân biệt vấn đề bắt buộc sửa với gợi ý có thể cân nhắc.

### Bước 5 — Tác giả phản hồi và sửa

Tác giả có thể đồng ý hoặc giải thích phương án khác bằng test và yêu cầu. Review không đòi mọi ý kiến chủ quan của reviewer phải được áp dụng.

### Bước 6 — Xác minh và kết luận theo chính sách

Kiểm tra thay đổi sau sửa, trạng thái CI, DoD và yêu cầu phê duyệt. Nếu còn bất đồng quan trọng, hỏi thêm người có thẩm quyền về nghiệp vụ/kỹ thuật thay vì để PR nằm vô thời hạn.

### Bước 7 — Truyền kiến thức quan trọng

Nếu PR phát hiện một quy tắc chưa biết hoặc quyết định có ảnh hưởng nhiều module, cập nhật test, tài liệu ngắn, ADR hoặc chia sẻ trong diễn đàn phù hợp.

**Approve không có nghĩa reviewer “bảo đảm toàn bộ hệ thống không lỗi”**. Nó xác nhận một mức kiểm tra trong phạm vi và trách nhiệm đã biết; chất lượng cần nhiều lớp bằng chứng.

## 11. Cách viết comment review hiệu quả

Một comment có ích nói **điều gì đáng quan tâm và vì sao**, đồng thời tôn trọng quyền lựa chọn giải pháp của người thực hiện.

| Comment kém hiệu quả | Comment tốt hơn | Lý do |
| --- | --- | --- |
| “Sai rồi.” | “Nếu khóa Y vừa hết quyền, hàm này có thể vẫn trả bài Y. Mình bổ sung test ca hết quyền trước khi merge được không?” | Có trường hợp cụ thể và hậu quả. |
| “Code dở quá.” | “Hàm hiện vừa xác thực, vừa chọn tiến độ, vừa tạo response. Tách phần chọn theo quy tắc có giúp test và đọc dễ hơn không?” | Thảo luận cấu trúc, không đánh giá con người. |
| “Phải dùng interface.” | “Đã có hai implementation cần thay thế ở đây chưa? Nếu mới một nguồn dữ liệu, liệu interface có tạo thêm tầng chưa cần?” | Nêu giả định để cùng đánh giá. |
| “Tôi không thích tên này.” | “Tên \`latestProgress\` chưa thể hiện điều kiện còn quyền; \`latestAccessibleProgress\` có rõ hơn không?” | Gắn góp ý với ý định. |
| “Tất cả phải sửa theo tôi.” | “Phần quyền truy cập này mình xem là bắt buộc; phần đặt tên chỉ là đề xuất, bạn cân nhắc theo convention nhé.” | Phân biệt mức độ rủi ro. |
| “LGTM” không đọc diff | “Đã xem luồng đọc tiến độ và test phân quyền, chưa kiểm tra migration vì PR không thay schema. CI hiện xanh theo pipeline.” | Minh bạch phạm vi review. |

### Nhãn mức độ góp ý (tùy chọn)

Một đội có thể dùng quy ước:

- **Blocker / Must fix:** Vấn đề đúng đắn, bảo mật, dữ liệu, tương thích hoặc chất lượng bắt buộc.
- **Question:** Chưa hiểu hoặc cần xác nhận giả định.
- **Suggestion:** Một cải tiến thiết kế có lợi nhưng có thể có phương án khác.
- **Nit:** Gợi ý nhỏ về tên hoặc style, không cản merge nếu chính sách không yêu cầu.

Không có hệ thống nhãn chuẩn bắt buộc. Điều quan trọng là **độ ưu tiên được truyền đạt rõ**. Những chuẩn tự động như formatter/linter nên được thiết lập để giảm comment nit lặp lại.

## 12. Review một thay đổi Java: từ ví dụ đến rủi ro

Giả sử API chọn bài học gần nhất đã được gọi sau khi người dùng đăng nhập. Đoạn code minh họa ban đầu:

~~~java
import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;

record Progress(String accountId, String courseId,
                String lessonId, Instant savedAt) {}

class ResumeService {
    Optional<Progress> latest(List<Progress> allProgress) {
        return allProgress.stream()
                .max(Comparator.comparing(Progress::savedAt));
    }
}
~~~

### Reviewer không nên chỉ nhận xét tên hàm

Các câu hỏi quan trọng hơn:

1. **Tài khoản nào?** Hàm chọn bản ghi trên *mọi* tài khoản, có nguy cơ trả dữ liệu của người khác.
2. **Quyền học còn hiệu lực không?** Bản ghi mới nhất có thể thuộc khóa người dùng không còn quyền.
3. **savedAt có đáng tin không?** Nếu null hoặc hai bản ghi cùng thời điểm, chính sách xử lý thế nào?
4. **Dữ liệu lấy từ đâu?** Nếu toàn bộ tiến độ của hệ thống rất lớn, tải hết vào bộ nhớ có hợp lý không?
5. **Kiểm thử ở đâu?** Test cho tài khoản khác, hết quyền, không có dữ liệu và lỗi API đã có chưa?
6. **Bảo vệ phía server?** Không được tin accountId hoặc danh sách quyền do client tự khai báo.

### Một phiên bản đơn giản hơn theo yêu cầu đã xác nhận

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.Set;

final class ResumeSelector {
    Optional<Progress> latestAccessible(
            String authenticatedAccountId,
            Set<String> accessibleCourseIds,
            List<Progress> records) {

        return records.stream()
                .filter(p -> authenticatedAccountId.equals(p.accountId()))
                .filter(p -> accessibleCourseIds.contains(p.courseId()))
                .max(Comparator.comparing(Progress::savedAt));
    }
}
~~~

**Lưu ý:** Đoạn code chỉ minh họa logic chọn trên dữ liệu **đã được xác minh nguồn gốc và quyền truy cập**; không phải giải pháp bảo mật hoàn chỉnh. Dịch vụ phải lấy danh tính từ ngữ cảnh xác thực phía server và thực thi phân quyền ở ranh giới thích hợp. Nếu dữ liệu rất lớn, cần thiết kế truy vấn phù hợp. Nếu có bản ghi trùng thời điểm hoặc dữ liệu không hợp lệ, phải làm rõ quy tắc trước khi tuyên bố tính năng hoàn thành.

### Review thông qua test

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.Set;

class ResumeSelectorTest {
    private final ResumeSelector selector = new ResumeSelector();

    @Test
    void ignoresOtherAccountsAndExpiredCourseAccess() {
        var eligible = new Progress("A", "X", "lesson-2",
                Instant.parse("2026-01-01T09:00:00Z"));
        var restricted = new Progress("A", "Y", "lesson-9",
                Instant.parse("2026-01-01T10:00:00Z"));
        var anotherAccount = new Progress("B", "X", "lesson-8",
                Instant.parse("2026-01-01T11:00:00Z"));

        assertEquals(Optional.of(eligible),
                selector.latestAccessible(
                        "A", Set.of("X"),
                        List.of(eligible, restricted, anotherAccount)));
    }

    @Test
    void returnsEmptyForNoEligibleProgress() {
        assertEquals(Optional.empty(),
                selector.latestAccessible(
                        "A", Set.of("X"), List.of()));
    }
}
~~~

Các test này kiểm chứng **một phần** hành vi của selector. Chúng **chưa** chứng minh API không lộ dữ liệu khi truy vấn trực tiếp, quyền được thu hồi giữa hai request hoặc xử lý lỗi hệ thống. Cần test tích hợp, bảo mật và chất lượng theo DoD.

### Pairing và review đóng vai trò khác nhau ra sao?

- **Pairing:** Hai người cùng đặt câu hỏi về tài khoản và quyền, viết test và lựa chọn thiết kế đơn giản.
- **Review độc lập:** Người khác nhìn tổng thể thay đổi, kiểm tra các ca chưa nghĩ tới, hợp đồng API, hiệu năng và chính sách chất lượng.
- **Chia sẻ kiến thức:** Đưa quy tắc **“chỉ chọn tiến độ của tài khoản hiện tại và khóa còn quyền”** vào tiêu chí chấp nhận, test và tài liệu chính sách phù hợp để người sau không phải đoán.

## 13. Tránh code review thành điểm nghẽn của dòng công việc

Review bảo vệ chất lượng nhưng cũng có thể kéo dài **cycle time** nếu PR bị dồn hoặc phụ thuộc một người duy nhất. Không nên “giải quyết” bằng cách bỏ review vô điều kiện; hãy cải tiến cách tạo và xử lý thay đổi.

### Dấu hiệu điểm nghẽn

- Nhiều PR chờ reviewer trong vài ngày.
- Người có quyền approve chỉ có một người, thường bận.
- PR lớn đến mức reviewer ngại bắt đầu.
- Comment được phản hồi chậm vì hai bên không thống nhất kỳ vọng.
- Tác giả mở thêm PR mới khi PR cũ còn đang chờ, làm WIP tăng.
- CI liên tục đỏ hoặc chậm, reviewer không biết nên xem phiên bản nào.

### Cách thử cải tiến

| Vấn đề | Thử nghiệm có thể áp dụng | Điều cần đo và bảo vệ |
| --- | --- | --- |
| PR quá lớn | Chia thay đổi thành lát cắt nhỏ, tập trung, dễ test | Thời gian chờ/review và tỷ lệ lỗi, không cắt vụn thành phần chưa dùng được |
| Reviewer bị quá tải | Dành năng lực review thường xuyên; pair hoặc swarm tại cột review | Work item age ở review, throughput, quá tải nhân sự |
| Một chuyên gia duyệt mọi thứ | Bổ sung người hiểu domain qua pairing/rotation có giám sát | Khả năng review độc lập và chất lượng phê duyệt |
| Quá nhiều comment style | Formatter/linter và chuẩn tên rõ ràng | Số vòng tranh luận về style, lỗi do automation |
| Hợp đồng API mơ hồ | Contract test và ví dụ liên chức năng trước khi viết quá nhiều | Lỗi tích hợp, thời gian chờ và làm lại |
| Reviewer không hiểu PR | Mô tả “why/what/how tested”, walkthrough ngắn cho phần rủi ro | Thời gian hiểu, vòng sửa, rủi ro bỏ sót |

### Ví dụ về WIP review

Đội đang có 3 PR ở “Chờ review”, 2 PR ở “Cần sửa”, cùng lúc một developer muốn mở tính năng mới. Nếu WIP đang là điểm nghẽn, hướng có thể thử là **hỗ trợ hoàn tất PR cũ**, pair để giải quyết comment hoặc chia PR tồn quá lớn. Điều này có thể cải thiện thời gian từ bắt đầu đến Done hơn là tăng số việc được khởi động.

**Không có giới hạn PR hoặc giờ phản hồi phổ quát.** Chính sách nên dựa trên độ khẩn, rủi ro, năng lực và dữ liệu thực tế.

## 14. Chia sẻ kiến thức là tạo năng lực, không chỉ tổ chức buổi trình bày

Một buổi chia sẻ có slide đẹp chưa chắc giúp người khác **tự sửa lỗi, review hoặc triển khai**. Chia sẻ kiến thức có giá trị khi hiểu biết quan trọng trở nên **truy cập được, thực hành được và kiểm chứng được**.

### Các mức kiến thức

| Mức | Ví dụ | Khả năng cần đạt |
| --- | --- | --- |
| **Nhận biết** | Biết có dịch vụ lưu tiến độ và người liên hệ | Tìm được điểm bắt đầu khi cần |
| **Hiểu** | Giải thích được quy tắc quyền và cách chọn bản ghi gần nhất | Review/đặt câu hỏi đúng |
| **Thực hành** | Chạy test, tái hiện lỗi, thay đổi một lát cắt nhỏ | Tự thực hiện có hỗ trợ phù hợp |
| **Làm chủ có trách nhiệm** | Chẩn đoán lỗi, sửa, kiểm thử, triển khai và hỗ trợ rollback | Không lệ thuộc chuyên gia duy nhất cho việc thông thường |
| **Dạy lại** | Hướng dẫn thành viên khác và cập nhật tài liệu/test khi thay đổi | Kiến thức tiếp tục lan tỏa |

Mục tiêu không phải mọi người đều thành chuyên gia về mọi lĩnh vực. Đội cần **đủ khả năng thay thế và cộng tác** trên những phần sản phẩm quan trọng, với trách nhiệm bảo mật và quyền truy cập phù hợp.

### Những vật mang kiến thức

- **Test rõ nghĩa:** Ví dụ hành vi, lỗi biên và ràng buộc được lưu dưới dạng thực thi.
- **Code dễ hiểu:** Tên miền nghiệp vụ, phân tách trách nhiệm, tránh abstraction chưa cần.
- **Pull request/issue:** Lý do thay đổi, rủi ro, cách kiểm chứng và quyết định quan trọng.
- **ADR (Architecture Decision Record):** Quyết định kiến trúc có ảnh hưởng, ngữ cảnh, lựa chọn, hệ quả, mốc xem lại.
- **Runbook:** Cách nhận biết, chẩn đoán và ứng phó với sự cố vận hành.
- **Ví dụ nghiệp vụ:** User story, acceptance criteria, Example Mapping, Gherkin hoặc tình huống minh họa.
- **Buổi thực hành:** Pairing, walkthrough, dojo hoặc diễn tập sự cố theo mức an toàn phù hợp.

Tài liệu và test cần **được cập nhật cùng thay đổi thật**. Một kho tài liệu không ai biết tìm ở đâu hoặc đã lỗi thời không giải quyết phụ thuộc cá nhân.

## 15. Kế hoạch chia sẻ kiến thức giảm phụ thuộc vào một người

**Knowledge silo** xảy ra khi chỉ một người hiểu một module, hợp đồng API hoặc quy trình release. Nếu người đó nghỉ, chuyển dự án hoặc bận xử lý việc khác, cả đội có thể bị chặn.

Một cách đánh giá đơn giản là hỏi:

> “Nếu ngày mai người đang phụ trách không có mặt, ai còn có thể **chẩn đoán, review, sửa và xác minh** thay đổi ở phần này một cách an toàn?”

### Ma trận kiến thức ví dụ

| Vùng sản phẩm | A | B | C | D | Rủi ro |
| --- | --- | --- | --- | --- | --- |
| Luồng “Tiếp tục học” | Tự chủ | Có thể sửa với hỗ trợ | Chỉ biết tổng quan | Chưa biết | Cần ít nhất một người nữa có thể review/sửa |
| Phân quyền khóa học | Tự chủ | Tự chủ | Có thể sửa với hỗ trợ | Chưa biết | Rủi ro vừa |
| CI và triển khai | Tự chủ | Chỉ biết tổng quan | Tự chủ | Có thể sửa với hỗ trợ | Có thể luân phiên |
| API đối tác tiến độ | Tự chủ | Chưa biết | Chỉ biết tổng quan | Chưa biết | Điểm phụ thuộc cao |

Đây là **ma trận năng lực để tự cải tiến**, không phải bảng chấm điểm cá nhân. Cần cho thành viên tham gia xác nhận cấp độ thay vì gán nhãn một chiều.

### Lộ trình giảm điểm nghẽn

1. Chọn một **khu vực rủi ro cao**: ít người hiểu, thay đổi thường xuyên hoặc tác động dữ liệu lớn.
2. Chọn một công việc nhỏ, thật, có tiêu chí Done rõ.
3. Pair người đang hiểu hệ thống với người muốn học, **người học driver** một phần.
4. Cho người học **review một PR liên quan** với hỗ trợ.
5. Ghi thêm một test, quy tắc hoặc runbook giúp tự chẩn đoán sau này.
6. Đổi người xử lý một việc tương tự ở lần sau, có review phù hợp.
7. Xem khả năng độc lập đã tăng chưa, không chỉ đếm số giờ mentoring.

### Bus factor không phải con số để tự hào

“Bus factor” thường dùng như hình ảnh về số người mà sự vắng mặt có thể khiến công việc nghiêm trọng bị dừng. Không cần tính một con số chính xác cho mọi module; điều quan trọng là **nhận diện tri thức và quyền vận hành đang tập trung nguy hiểm**, rồi có kế hoạch giảm rủi ro.

Không nên chia sẻ **mật khẩu, token hoặc quyền truy cập vượt vai trò** để làm cho “ai cũng vận hành được”. Kiến thức cần lan tỏa; quyền nhạy cảm vẫn phải theo kiểm soát truy cập và kiểm toán của tổ chức.

## 16. Chọn hình thức truyền kiến thức phù hợp

| Hình thức | Khi phù hợp | Rủi ro hoặc giới hạn |
| --- | --- | --- |
| **Pairing trên story thật** | Cần truyền kỹ năng thao tác, suy luận và hiểu code | Mất hiệu quả nếu người học chỉ quan sát |
| **PR review với giải thích** | Muốn lan tỏa lý do thay đổi trong chính ngữ cảnh code | Không thay được thực hành triển khai hoặc xử lý sự cố |
| **Walkthrough kỹ thuật ngắn** | Có quyết định/cấu trúc mới ảnh hưởng nhiều người | Buổi trình bày đơn lẻ có thể nhanh bị quên |
| **ADR ngắn** | Chọn kiến trúc khó đảo ngược, có đánh đổi đáng ghi | Trở nên lỗi thời nếu không gắn với thay đổi thực |
| **Runbook + diễn tập** | Hệ thống cần xử lý sự cố và khôi phục | Tài liệu chưa được thử có thể sai ở thời điểm khẩn |
| **Brown-bag / tech talk** | Giới thiệu khái niệm chung hoặc bài học từ sự cố | Dễ lan man nếu không có ví dụ/tác vụ áp dụng |
| **Ensemble/mob programming** | Quyết định rủi ro cao hoặc vấn đề cần nhiều kỹ năng | Tốn sự chú ý đồng thời; cần điều phối và giới hạn phạm vi |
| **Luân phiên người sở hữu công việc** | Giảm một người luôn làm/duyệt cùng module | Cần review, test và onboarding để luân phiên an toàn |
| **Ghi chép ví dụ nghiệp vụ** | Quy tắc thay đổi, nhiều nhóm có cách hiểu khác | Không thay xác nhận từ người có thẩm quyền nghiệp vụ |

### Chọn theo loại kiến thức

- **Kiến thức tường minh:** hợp đồng API, cấu hình, sơ đồ, mốc release — có thể ghi tài liệu và kiểm thử.
- **Kiến thức ngầm:** kinh nghiệm gỡ lỗi, cách đọc log, suy luận về dữ liệu — thường cần pairing, shadowing, diễn tập rồi để người học tự thực hiện.
- **Kiến thức ra quyết định:** vì sao chọn schema, rủi ro nào được chấp nhận — phù hợp với ADR, review và trao đổi giữa người có trách nhiệm.

Không nên tạo mọi loại tài liệu cho mọi story. Hãy ưu tiên **tri thức có giá trị tái sử dụng, khó suy ra từ code và có rủi ro nếu bị mất**.

## 17. Pairing từ xa và review bất đồng bộ

Các đội phân tán địa điểm hoặc múi giờ cần kết hợp **thời gian đồng bộ hạn chế** với truyền đạt ngữ cảnh rõ.

### Pairing từ xa

- Đảm bảo cả hai thấy cùng phiên bản code, test và kết quả chạy.
- Chọn công cụ chia sẻ màn hình/điều khiển được tổ chức cho phép, tránh vô tình hiển thị bí mật.
- Người navigator đọc trước tiêu chí chấp nhận và chuẩn bị câu hỏi; đừng dùng phần lớn thời gian xem tác giả cài môi trường.
- Đổi vai bằng cơ chế điều khiển có thể kiểm tra và phù hợp khả năng tiếp cận.
- Ghi lại quyết định ngắn để người khác ở múi giờ khác có thể tiếp tục.

### Review bất đồng bộ

- Tạo PR có **mục đích, phạm vi, bằng chứng kiểm thử**.
- Chia diff thành commit/lát cắt dễ kiểm tra nếu không làm mất ý nghĩa thay đổi.
- Xác định **thời gian đáp ứng kỳ vọng** theo rủi ro và năng lực, không coi reviewer phải luôn có mặt.
- Khi comment qua lại nhiều vòng mà vẫn bất đồng, đề nghị **cuộc trao đổi ngắn** rồi ghi kết luận vào PR.
- Có cách bàn giao review giữa múi giờ khi việc thực sự cần hoàn tất liên tục.

### Không để lệch múi giờ trở thành lệch thông tin

Ví dụ một reviewer ở múi giờ khác đặt câu hỏi “Nếu quyền truy cập bị thu hồi thì sao?”. Tác giả nên trả lời kèm test/đặc tả, thay vì chỉ nhắn “đã xử lý” trong một cuộc gọi mà những người sau không nhìn thấy.

## 18. Tình huống xuyên suốt: cả đội sửa lỗi tiến độ học

### 18.1. Bối cảnh

Product Goal là giúp học viên **tiếp tục học đáng tin cậy**. Một lỗi được phát hiện:

> Khi học viên đăng nhập trên máy đã dùng bởi tài khoản khác, giao diện có lúc hiển thị bài học gần nhất của người dùng trước.

Lỗi liên quan **quyền riêng tư và phân quyền**, vì vậy phải xử lý theo mức nghiêm trọng và chính sách sự cố áp dụng.

### 18.2. Trước khi code

Product Owner/người có thẩm quyền nghiệp vụ xác nhận:

- Tài khoản B không được thấy tiến độ riêng của A.
- Khi không có tiến độ hợp lệ, ứng dụng hiển thị trạng thái phù hợp.
- Nếu chưa thể xác minh danh tính/quyền, không hiển thị dữ liệu từ bộ nhớ đệm của tài khoản trước.

Developer A biết luồng tiến độ, Developer B hiểu bộ nhớ đệm và phiên đăng nhập, Tester C chuẩn bị các trường hợp kiểm chứng.

### 18.3. Pair để phát hiện giả định

Trong phiên pair:

1. Driver viết test cho tình huống đổi tài khoản trên cùng thiết bị.
2. Navigator nhận ra cache đang dùng khóa chỉ theo **deviceId**, không theo danh tính có thẩm quyền.
3. Hai người kiểm tra cách phân quyền ở phía server và chính sách vô hiệu hóa cache khi đổi tài khoản.
4. Họ điều chỉnh phạm vi sửa, chạy unit/integration test và ghi giả định còn mở về thời điểm hết phiên.

### 18.4. Review theo rủi ro

PR được gửi với:

- Mô tả cách tái hiện lỗi.
- Test A → đăng xuất → B → không thấy dữ liệu A.
- Thay đổi cache/luồng xác thực.
- Phân tích ảnh hưởng đến ứng dụng cũ và cách rollback.
- Tình trạng CI và kiểm thử tích hợp.

Reviewer độc lập hỏi thêm:

> “Nếu request đọc tiến độ của A đang chạy khi B vừa đăng nhập, response đến muộn có thể lại ghi vào cache của B không? Chúng ta đã test race condition này chưa?”

Đội phát hiện một trường hợp cạnh tranh chưa được tính đến và bổ sung cách kiểm soát phiên/phiên bản theo thiết kế phù hợp.

### 18.5. Chia sẻ kiến thức sau khắc phục

Đội cập nhật:

- Test hồi quy về **đổi tài khoản và response đến muộn**.
- Quy tắc cache được phân vùng theo danh tính/phiên và nguyên nhân của quyết định.
- Runbook nếu lỗi lặp lại, cách quan sát log mà không lộ dữ liệu.
- Một walkthrough ngắn về điểm tích hợp của cache với cơ chế xác thực.

Ở lần thay đổi sau, Developer D có thể tự tái hiện và sửa một lỗi liên quan, được review bởi B. Đó là tín hiệu **kiến thức đã được chuyển thành năng lực thực hành**, không chỉ thành tài liệu.

### 18.6. Điều gì có thể đánh giá?

Không cần gán công lao “hai người ngồi cùng nên giảm 40% lỗi” khi không có dữ liệu đủ tin cậy. Đội có thể quan sát:

- Lỗi hồi quy cùng loại có còn xuất hiện?
- Thời gian từ lúc bắt đầu sửa đến khi đạt DoD có thay đổi?
- Người ngoài A/B có thể hiểu và review module không?
- Review có phát hiện vấn đề mới sớm hay chỉ lặp lại điều đã thảo luận?
- Có phải đợi duy nhất một chuyên gia để xử lý sự cố hoặc phát hành không?

## 19. Kết hợp trong Sprint, Kanban và luồng kỹ thuật XP

### Trong Scrum

Scrum Team có Product Owner, Scrum Master và Developers; Developers chịu trách nhiệm tạo **Increment đáp ứng Definition of Done**. Pairing, review và chia sẻ kiến thức **không phải sự kiện Scrum bắt buộc riêng**, nhưng có thể hỗ trợ các trách nhiệm:

- **Sprint Planning:** Nhìn thấy năng lực và rủi ro tri thức tập trung; chọn lát cắt có thể hoàn thành.
- **Daily Scrum:** Developers phối hợp khi một item khó hoặc bị chặn; pair để xử lý việc đe dọa Sprint Goal.
- **Trong Sprint:** Code review và CI giúp giữ Increment tích hợp; không hạ DoD để kịp danh sách item.
- **Sprint Review:** Cho thấy sản phẩm thực sự đã đáp ứng DoD và học hỏi phản hồi khách hàng.
- **Sprint Retrospective:** Xem tình trạng review chờ lâu, lỗi lặp lại hoặc module chỉ một người hiểu; chọn một thử nghiệm cải tiến.

### Trong Kanban

Pairing và review là **hoạt động bên trong workflow**. Nếu cột Review bị nghẽn, đội có thể điều chỉnh WIP, dành năng lực review, pair để giải quyết nhanh thay vì mở thêm việc.

Quan sát:

- **WIP:** bao nhiêu item đã bắt đầu chưa Done?
- **Throughput:** bao nhiêu item hoàn tất trong một kỳ?
- **Cycle time:** item hoàn tất mất bao lâu từ mốc bắt đầu?
- **Work item age:** item đang mở đã chờ bao lâu?

Thử nghiệm pairing/review cần nhìn **kết quả hệ thống**, không chỉ thời gian từng người ngồi trước màn hình.

### Với XP

Pair programming thường được xem như một thực hành nổi bật của XP, hỗ trợ **collective code ownership, TDD, refactoring và tích hợp liên tục**. Kết hợp tốt giúp code dễ thay đổi và giảm rủi ro phụ thuộc một người; cần kiểm chứng tác động với sản phẩm cụ thể.

## 20. Đo hiệu quả mà không tối ưu sai chỉ số

### Các nhóm tín hiệu nên cân bằng

| Nhóm | Chỉ số/tín hiệu ví dụ | Giới hạn khi diễn giải |
| --- | --- | --- |
| **Dòng công việc** | Thời gian chờ review, cycle time, work item age, throughput | Có thể thay đổi do loại item, môi trường, phụ thuộc, cách chia story |
| **Chất lượng** | Lỗi production, lỗi hồi quy, mức độ nghiêm trọng, thời gian khôi phục | Số lỗi ít trong mẫu nhỏ không chứng minh an toàn tuyệt đối |
| **Kiến thức** | Số người có thể tự sửa/review module, khả năng trực vận hành, chất lượng runbook/test | Không nên ép mọi người đạt cùng mức hoặc biến thành xếp hạng |
| **Hợp tác** | Mức chủ động hỏi, chất lượng comment, thời gian giải quyết bất đồng | Khó đo bằng một con số; khảo sát cần tránh gây áp lực |
| **Giá trị sản phẩm** | Hành vi người dùng, thời gian tìm lại bài, tỷ lệ lỗi tiến độ | Outcome bị chi phối bởi nhiều yếu tố ngoài code |
| **Bền vững** | Khối lượng overtime, mức gián đoạn, khả năng tập trung và phản hồi đội | Tăng throughput do làm thêm giờ không phải cải tiến bền vững |

### Không dùng các thước đo dễ tạo động cơ sai

- **Số giờ pair** không chứng minh kiến thức đã lan tỏa.
- **Số comment review** không chứng minh phát hiện được rủi ro quan trọng.
- **Số PR được approve** không đo chất lượng độc lập.
- **Số dòng code** không đo đóng góp của driver hay navigator.
- **Số reviewer** nhiều hơn không tự động đồng nghĩa an toàn hơn; có thể làm trách nhiệm mờ đi.

Một cải tiến có giá trị khi có **phản hồi sớm hơn, chất lượng không giảm, ít việc bị chặn vì tri thức tập trung, và đội giao được Increment hữu ích**.

## 21. Thiết kế thử nghiệm kết hợp ba thực hành

### Giả thuyết

> “Nếu các story có rủi ro nghiệp vụ cao được pairing sớm, PR được chia nhỏ và review theo rủi ro, sau đó quyết định quan trọng được ghi lại trong test/ADR ngắn, thì thời gian chờ review và lỗi làm lại có thể giảm, đồng thời tăng số người tự hỗ trợ module.”

### Bối cảnh dữ liệu trước thử (giả định)

Trong bốn tuần:

- 18 PBI/bug hoàn thành.
- Một số PR chờ review lâu hơn thời gian code thực tế.
- Hai thay đổi bị mở lại do thiếu quy tắc phân quyền.
- Chỉ một người có thể tự sửa lỗi ở module tiến độ.

Không nên chỉ dựa vào các số này để kết luận pairing là giải pháp duy nhất; có thể còn vấn đề môi trường CI, cách xếp backlog hoặc phụ thuộc đội khác.

### Thử trong bốn tuần tiếp theo

| Thành phần | Quy ước thử |
| --- | --- |
| **Đối tượng** | Story thay đổi quyền truy cập, dữ liệu tiến độ hoặc hợp đồng API; các việc khác theo chính sách thông thường |
| **Pairing** | Ghép hai góc nhìn khác nhau trong đoạn có rủi ro cao, đổi vai, chốt test/giả định |
| **Code review** | PR có lý do, phạm vi, test và vùng rủi ro; reviewer theo chuyên môn và yêu cầu độc lập của tổ chức |
| **Chia sẻ kiến thức** | Cập nhật ít nhất một test/decision note/runbook khi xuất hiện quy tắc hoặc quyết định tái sử dụng |
| **Flow** | Quan sát thời gian chờ review, cycle time và tuổi item bị chặn |
| **Quality guardrail** | Không tăng lỗi dữ liệu nghiêm trọng, không hạ DoD hoặc giảm kiểm thử bắt buộc |
| **Knowledge signal** | Kiểm tra xem người thứ hai có tự chạy test, tái hiện lỗi và review thay đổi liên quan được không |
| **Điểm xem lại** | Sau bốn tuần hoặc sau đủ số item liên quan để có nhận định sơ bộ |

### Khi đánh giá

Hỏi:

1. Review có phản hồi nhanh hơn không? Có đổi cách đếm item/PR hay loại công việc không?
2. Những lỗi quan trọng có được phát hiện **trước khi merge** hơn không?
3. Pairing có giúp người ít biết module tự thực hiện bước tiếp theo không?
4. Có tăng quá nhiều thời gian phối hợp hoặc làm thành viên kiệt sức không?
5. Các tác động tích cực có thể do CI được cải thiện hoặc phụ thuộc được gỡ cùng kỳ không?
6. Nên giữ, giảm phạm vi, thay đổi cặp người hoặc chuyển một số nội dung sang review bất đồng bộ?

**Thử nghiệm trước/sau trên một đội không tự chứng minh quan hệ nhân quả.** Nó tạo bằng chứng thực tế để tiếp tục học, miễn bối cảnh và giới hạn được ghi rõ.

## 22. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| **Pairing là senior gõ, junior nhìn.** | Tri thức không được thực hành, phụ thuộc cá nhân còn nguyên | Cho người học driver, đổi vai và hỏi ý định |
| **Bắt buộc pair mọi task bất kể độ rủi ro** | Tốn chú ý, giảm tính linh hoạt | Chọn pairing theo loại việc, rủi ro và mục tiêu học |
| **Pairing thay mọi kiểm tra độc lập** | Bỏ sót nghĩa vụ review hoặc rủi ro góc nhìn chung | Giữ chính sách review/approval cần thiết |
| **Reviewer chỉ sửa style và sở thích cá nhân** | Chậm merge, bỏ qua tính đúng đắn | Dùng formatter, ưu tiên bảo mật, dữ liệu, behavior |
| **Comment công kích tác giả** | Giảm an toàn khi phát biểu, dễ che lỗi | Viết comment theo tình huống–hậu quả–đề xuất |
| **Approve ngay vì đã tin người viết** | Thiếu kiểm tra vùng rủi ro | Nêu phạm vi review, dựa trên test và thay đổi thực |
| **PR quá lớn rồi giao cho một reviewer** | Hàng chờ tăng, khó phát hiện lỗi | Chia lát cắt và có hướng dẫn review phần quan trọng |
| **Mọi PR phải chờ một chuyên gia duy nhất** | Điểm nghẽn và bus factor thấp | Rotation, pairing, đào tạo reviewer dự phòng |
| **Chia sẻ kiến thức bằng buổi nói chuyện không có thực hành** | Người nghe vẫn không tự sửa được | Cho người học chạy test, xử lý item thật có hỗ trợ |
| **Ghi tài liệu nhưng không cập nhật khi đổi code** | Kiến thức lỗi thời gây rủi ro | Gắn tài liệu/test/runbook với thay đổi liên quan |
| **Truyền quyền truy cập nhạy cảm để ai cũng làm được** | Rủi ro bảo mật và kiểm toán | Chia sẻ cách làm, giữ phân quyền theo vai trò |
| **Đo bằng số comment hoặc giờ pair** | Khuyến khích hoạt động hình thức | Đo năng lực, chất lượng, flow và outcome |
| **Bỏ test để PR được duyệt nhanh** | Tăng lỗi, làm lại và nguy cơ dữ liệu | Giữ DoD, CI và kiểm thử theo rủi ro |
| **Quá nhiều reviewer không rõ người chịu quyết định** | Review kéo dài, trách nhiệm mơ hồ | Chọn reviewer có vai trò phù hợp, chính sách approve rõ |
| **Không thảo luận lại khi review tranh cãi kéo dài** | Vòng comment vô tận | Trao đổi đồng bộ ngắn rồi ghi quyết định |
| **Tài liệu hóa mọi chi tiết nhỏ** | Nợ tài liệu, khó tìm nội dung quan trọng | Ưu tiên tri thức tái sử dụng, hợp đồng và quyết định khó suy từ code |

## 23. Bộ thực hành gợi ý cho một đội

Một đội muốn bắt đầu không cần ban hành hàng chục quy định. Có thể thử bộ tối thiểu:

### Trước khi bắt đầu story rủi ro

- Có ví dụ nghiệp vụ, tiêu chí chấp nhận, nguồn dữ liệu đáng tin và DoD.
- Chỉ rõ phần nào sẽ **pair**, phần nào cần reviewer chuyên môn hoặc phê duyệt độc lập.
- Nhìn rủi ro dependency, migration và lỗi khó đảo ngược.

### Trong khi thực hiện

- Pair ở đoạn không chắc chắn hoặc ảnh hưởng dữ liệu; đổi vai để hai người đều hiểu.
- Viết/chạy test nhỏ, tích hợp thường xuyên, không chờ cuối Sprint mới merge.
- Khi gặp quy tắc mới, xác nhận với người có thẩm quyền thay vì đoán.
- Tránh mở quá nhiều PR dang dở; ưu tiên hoàn tất lát cắt đang tiến tới Done.

### Trước khi merge

- Tác giả đọc lại diff, mô tả why/what/test/risk phù hợp.
- Reviewer đánh giá hành vi, rủi ro, test, tương thích và chất lượng.
- Các comment bắt buộc đã được xử lý hoặc có quyết định được ghi lại.
- CI và yêu cầu approve/DoD liên quan đạt; không có lỗ hổng bị che dưới nhãn “đã pair”.

### Sau khi có Increment

- Chia sẻ quyết định đáng nhớ dưới dạng **test, ADR hoặc runbook** ngắn.
- Người mới có cơ hội tự xử lý một thay đổi liên quan với review phù hợp.
- Tại Retrospective/flow review, xem thời gian chờ, lỗi làm lại và tri thức tập trung.

**Ưu tiên đơn giản và có mục đích**: mỗi thực hành phải giải quyết một loại rủi ro hoặc điểm nghẽn cụ thể.

## 24. Bài tập thực hành

### Bài tập 1 — Chọn hình thức cộng tác

Đội có bốn hạng mục:

1. Sửa một lỗi chính tả trong hướng dẫn người dùng đã có tiêu chuẩn rõ.
2. Thay logic phân quyền khi học viên đổi tài khoản trên cùng thiết bị.
3. Di chuyển dữ liệu tiến độ sang schema mới có ảnh hưởng client cũ.
4. Onboard developer mới vào module chỉ một chuyên gia hiểu.

**Yêu cầu:** Với từng hạng mục, chọn pairing, review bất đồng bộ, walkthrough, mentoring hoặc kết hợp; giải thích theo **mức rủi ro và mục tiêu học hỏi**.

**Gợi ý:** (2) và (3) thường đáng có trao đổi trực tiếp và kiểm tra độc lập; (4) cần người mới thực hành; (1) có thể đủ review rất nhẹ/automation theo chính sách.

### Bài tập 2 — Thực hành driver–navigator

Chọn một hàm đang xử lý tiến độ học. Trong một phiên ngắn:

1. Driver viết test cho tài khoản không được truy cập tiến độ của người khác.
2. Navigator đặt câu hỏi về dữ liệu, trường hợp biên và quyền phía server.
3. Đổi vai sau một vòng test.
4. Refactor tên hoặc cấu trúc nhỏ, chạy test lại.
5. Ghi một câu trả lời: **người thứ hai đã học được điều gì có thể tự làm lần sau?**

**Tiêu chí:** Cả hai thực sự tham gia, test phản ánh rủi ro và không sử dụng phiên pair để kiểm soát hoặc chấm điểm cá nhân.

### Bài tập 3 — Viết comment PR

PR có đoạn code:

~~~java
Optional<Progress> latest(List<Progress> progress) {
    return progress.stream()
            .max(Comparator.comparing(Progress::savedAt));
}
~~~

**Yêu cầu:** Viết ba comment review:

- Một **blocker** về quyền truy cập.
- Một **question** về trường hợp hai bản ghi có cùng thời điểm.
- Một **suggestion** về tên hàm hoặc cách test.

**Gợi ý:** Nêu tình huống và hậu quả, đừng chỉ nói “sai” hoặc “viết lại”. Không tự quyết quy tắc nghiệp vụ chưa được xác nhận.

### Bài tập 4 — Chuẩn bị một PR dễ review

Story: “Chỉ hiển thị bài gần nhất còn quyền truy cập.” Hãy viết mô tả PR tối đa 250 từ gồm mục đích, phạm vi, phần không gồm, thay đổi chính, cách kiểm thử và vùng rủi ro muốn reviewer tập trung.

**Gợi ý:** Reviewer cần biết vì sao thay đổi được làm và điều gì có thể gây hại, không cần đọc mọi dòng để đoán Product Goal.

### Bài tập 5 — Giảm hàng chờ review

Trong hai tuần, đội có 11 PR mở, 7 PR chờ review quá hai ngày làm việc, hai reviewer có nhiều việc vận hành và PR trung bình khá lớn. Đội vẫn tiếp tục bắt đầu story mới.

**Yêu cầu:** Viết giả thuyết về điểm nghẽn và một thử nghiệm kéo dài hai tuần. Chỉ rõ WIP, cách hỗ trợ review, chỉ số flow và guardrail chất lượng.

**Gợi ý:** Đo tuổi PR, cycle time item và lỗi; đừng đặt mục tiêu chỉ “approve nhiều hơn” nếu rủi ro bị bỏ qua.

### Bài tập 6 — Ma trận kiến thức và bus factor

Một đội có một developer duy nhất biết cách sửa API tiến độ và một người duy nhất biết pipeline release.

**Yêu cầu:** Lập kế hoạch bốn tuần để có người dự phòng thực hành được cả hai khu vực. Bao gồm pairing, review chéo, một thay đổi thật có test, runbook và một lần diễn tập an toàn.

**Gợi ý:** Chỉ xem thành công khi người học có thể giải thích, thực hiện và được review phù hợp; không trao thêm quyền truy cập nhạy cảm ngoài chính sách.

### Bài tập 7 — Khi pairing và review phát hiện hai vấn đề khác nhau

Trong phiên pair, đội phát hiện thiếu xử lý request gửi lại. Trong code review, người thứ ba phát hiện API đối tác có thể trả response muộn sau khi đổi tài khoản.

**Yêu cầu:** Phân biệt hai cơ chế phản hồi, đề xuất test và nơi lưu tri thức để tránh lỗi lặp lại. Giải thích vì sao không thể nói “đã pair nên reviewer không cần xem”.

### Bài tập 8 — Đánh giá thử nghiệm trước/sau

Trước thử: nhiều PR chờ review và chỉ một người hiểu module dữ liệu. Sau bốn tuần áp dụng pairing chọn lọc và PR nhỏ hơn, tuổi PR giảm, nhưng cùng kỳ đội cũng nâng cấp CI và có ít yêu cầu mới hơn.

**Yêu cầu:** Viết kết luận khoảng 150–200 từ, tách **quan sát thực tế**, **nguyên nhân chưa thể khẳng định**, **tín hiệu chất lượng** và **bước thử tiếp theo**.

**Gợi ý:** Không gán toàn bộ hiệu quả cho pairing; nhìn loại công việc, pipeline, reviewer và mức độ độc lập của thành viên.

### Bài tập 9 — Mô phỏng review phân quyền

Nhóm ba người đóng vai tác giả PR, reviewer và người phụ trách sản phẩm/test. Cho tình huống “Tài khoản B mở trang chủ trên thiết bị trước đó được A dùng”.

**Yêu cầu:** Tạo ba acceptance scenarios, hai câu hỏi review rủi ro cao, một kế hoạch kiểm thử tích hợp và một đoạn tài liệu ngắn giải thích quyết định cache/phiên đăng nhập.

**Tiêu chí:** Cần chứng minh được dữ liệu A không lộ cho B, xử lý response đến muộn, và chỉ gọi Increment Done khi đáp ứng chất lượng.

## 25. Checklist kết hợp pairing, review và chia sẻ kiến thức

- [ ] Mỗi thay đổi có **kết quả người dùng hoặc rủi ro sản phẩm** rõ?
- [ ] Đã xác định phần nào cần pairing và **vì sao**, thay vì áp dụng máy móc?
- [ ] Driver và navigator đều tham gia và có cơ hội đổi vai?
- [ ] Những giả định hoặc quy tắc nghiệp vụ mới được xác nhận đúng người có thẩm quyền?
- [ ] Có test kiểm chứng hành vi quan trọng và lỗi biên?
- [ ] Pairing không được dùng để kiểm soát, chấm điểm hoặc gây áp lực cá nhân?
- [ ] PR có mục đích, phạm vi, test và vùng rủi ro đủ rõ để review?
- [ ] Reviewer tập trung vào **tính đúng, dữ liệu, bảo mật, tương thích và DoD** trước style?
- [ ] Comment nêu tình huống, hậu quả và mức độ bắt buộc, không công kích tác giả?
- [ ] Những comment có thể tự động hóa đã được chuyển sang linter/formatter khi thích hợp?
- [ ] Khi review bất đồng kéo dài, có cách trao đổi trực tiếp và ghi lại quyết định?
- [ ] Các yêu cầu **review độc lập, code owner, kiểm toán hoặc phê duyệt** vẫn được tôn trọng?
- [ ] Đã xét tác động tới CI, test tích hợp, vận hành, rollout/rollback nếu liên quan?
- [ ] Những quyết định có giá trị được lưu trong test, tài liệu ngắn, ADR hoặc runbook đúng chỗ?
- [ ] Người thứ hai có thể **tự thực hành**, không chỉ nghe giới thiệu?
- [ ] Có kế hoạch giảm điểm phụ thuộc chuyên gia duy nhất ở khu vực quan trọng?
- [ ] Việc chia sẻ kiến thức không làm lộ bí mật hoặc cấp quyền vượt trách nhiệm?
- [ ] Đội xem cả WIP, thời gian chờ review, chất lượng và outcome, không chỉ đếm comment/giờ pair?
- [ ] Phản hồi người dùng và học hỏi được dùng để điều chỉnh cách phối hợp?
- [ ] Các thực hành có tạo **năng lực giao Increment an toàn, bền vững** hay chỉ thêm nghi thức?

Checklist phục vụ **trao đổi và cải tiến**. Một thay đổi nhỏ có thể không cần tất cả hình thức; thay đổi nhiều rủi ro cần những lớp kiểm tra bổ sung. Không biến checklist thành thủ tục để hoàn tất hình thức.

## 26. Tổng kết

- **Pair programming** tạo phản hồi và chia sẻ suy luận **ngay khi giải quyết vấn đề**; hiệu quả đến từ cùng chú ý, đổi vai, test và quyết định minh bạch, không từ hai người ngồi cạnh nhau.
- **Code review** bổ sung góc nhìn và trách nhiệm chất lượng; PR rõ mục đích, nhỏ hợp lý, phản hồi tôn trọng và kiểm tra vùng rủi ro giúp tránh review trở thành hàng chờ.
- **Knowledge sharing** có giá trị khi người khác **có thể áp dụng**: chạy test, chẩn đoán lỗi, review hoặc thực hiện thay đổi an toàn. Tài liệu, ADR, test và runbook hỗ trợ nhưng không thay trải nghiệm thực hành.
- **Ba thực hành bổ sung nhau nhưng không thay thế mọi cơ chế khác**: CI, kiểm thử tích hợp, yêu cầu phê duyệt độc lập và Definition of Done vẫn áp dụng theo bối cảnh.
- **Chọn hình thức theo nhu cầu:** Pair ở đoạn khó hoặc rủi ro; review cho góc nhìn độc lập; walkthrough/rotation để lan tỏa tri thức; dùng tự động hóa cho kiểm tra lặp lại.
- **Đánh giá bằng chất lượng, dòng công việc, kiến thức lan tỏa và giá trị**, không phải số giờ pair, số reviewer hay số comment.
- **Mục tiêu Agile là giao giá trị tăng dần một cách thích ứng và bền vững**. Cộng tác kỹ thuật tốt làm giảm chi phí phát hiện lỗi muộn và giảm nguy cơ chỉ một người có thể giữ hệ thống hoạt động.

Khi thấy một PR lớn đang chờ chuyên gia duy nhất duyệt trong khi nhóm liên tục mở việc mới, hãy hỏi: **“Ai cần cùng nhìn vào vấn đề này ngay bây giờ, cần phản hồi độc lập ở đâu, và làm thế nào để lần sau đội không còn phụ thuộc vào một người?”**
