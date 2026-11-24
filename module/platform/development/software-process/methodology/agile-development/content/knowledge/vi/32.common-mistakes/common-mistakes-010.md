# Dồn kiểm thử và tích hợp sang cuối kỳ hoặc nhóm khác

Cuối Sprint, một nhóm phát triển nền tảng học trực tuyến thông báo: “Chúng tôi đã hoàn thành 12 story; chỉ còn chờ QA kiểm thử và nhóm tích hợp ghép hệ thống.” Hai ngày sau, tester phát hiện trạng thái **“Đã lưu tiến độ”** xuất hiện khi máy chủ mới chỉ nhận yêu cầu chứ chưa xác nhận dữ liệu được ghi. Một API khác trả tiến độ của sai tài khoản trong trường hợp hiếm. Các nhánh mã đã thay đổi nhiều ngày, hợp đồng giữa ứng dụng và dịch vụ tiến độ không thống nhất. Sprint Review đến gần, cả nhóm phải sửa gấp, kiểm thử lại và xin lùi phát hành.

Vấn đề không nằm ở việc tester phát hiện lỗi. **Lỗi được phát hiện là thông tin cần thiết**. Vấn đề nằm ở cách tổ chức khiến phản hồi về **hành vi, chất lượng và khả năng tích hợp** chỉ đến khi công việc đã được báo “xong”, còn trách nhiệm giải quyết lại bị chuyển từ nhóm này sang nhóm khác.

**Dồn kiểm thử và tích hợp sang cuối kỳ hoặc “ném qua tường” cho một nhóm khác là phản mẫu Agile**: làm các phần riêng lẻ trước, chờ tới cuối mới hỏi liệu chúng có cùng tạo được một Increment đúng và đáng tin cậy hay không. Hệ quả thường là chậm học, tăng làm lại, nhiều hàng đợi, chất lượng không nhất quán và mất khả năng giao sản phẩm tăng dần.

Bài thuộc chương **Sai lầm thường gặp** của mô-đun **AGILE_DEVELOPMENT**. Mục tiêu của mô-đun là hiểu các giá trị và nguyên tắc Agile để phát triển phần mềm thích ứng qua phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục; thực hành user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc để chọn cách phối hợp phù hợp. Ở đây, ta sẽ dùng các công cụ đó để thay đổi **thời điểm nhận phản hồi và trách nhiệm chất lượng**, thay vì chỉ cố tăng tốc một bước cuối.

**Sau bài học, người học có thể:**

- Nhận diện dấu hiệu **“dev done, QA pending”, “ready for integration”, “code complete”** nhưng phần mềm chưa thực sự Done.
- Phân tích chi phí của **phản hồi muộn**, chuyển giao giữa nhóm và các lô thay đổi lớn.
- Phân biệt **kiểm thử, đảm bảo chất lượng, tích hợp, Definition of Done, Increment và phát hành**.
- Tổ chức kiểm chứng **trước, trong và sau khi phát triển một lát cắt**, thay vì chờ “giai đoạn kiểm thử”.
- Áp dụng **ví dụ nghiệp vụ, TDD/BDD, CI, contract test, integration test, exploratory test và quan sát sau phát hành** theo rủi ro.
- Hiểu vai trò của **tester chuyên môn, Developers, Product Owner, Scrum Master và đội nền tảng** mà không chuyển trách nhiệm chất lượng hoàn toàn sang người khác.
- Thiết kế **cơ chế phối hợp giữa frontend, backend, dữ liệu, vận hành và bảo mật** để tạo Increment tích hợp sớm.
- Dùng **WIP, Work Item Age, cycle time, throughput, thời gian chờ, lỗi lọt và độ tin cậy** để chọn cải tiến có bằng chứng.
- Lập kế hoạch thay đổi nhỏ, có guardrails, và kiểm tra tác động qua nhiều vòng thay vì áp dụng nghi thức hình thức.

## 1. Biểu hiện của sai lầm: “hoàn thành phát triển” nhưng chưa dùng được

Những câu dưới đây thường là dấu hiệu một **cửa kiểm thử/tích hợp muộn** đang tách chất lượng khỏi dòng phát triển:

- “Dev đã xong, giờ giao QA.”
- “Chúng ta sẽ kiểm thử tích hợp trong tuần cuối.”
- “Backend và frontend đều xong phần của mình; chỉ chờ ghép.”
- “Story đạt 100% code nhưng môi trường test đang bận.”
- “Tester chưa nhận nên lỗi không thuộc nhóm phát triển.”
- “CI xanh, phần nghiệp vụ để UAT xác nhận sau.”
- “Lỗi production là trách nhiệm đội vận hành; đội feature đã bàn giao.”
- “Chúng ta ghi Done trước, bug mở ticket Sprint sau.”

Không phải mọi câu “chờ kiểm thử” đều chứng minh có vấn đề. Một số kiểm tra độc lập, kiểm toán hoặc xác nhận theo quy định có thể bắt buộc. **Điểm nguy hiểm là xem công việc chưa đạt chất lượng, chưa tích hợp hoặc chưa kiểm chứng hành vi như đã hoàn thành**, rồi chuyển toàn bộ rủi ro và trách nhiệm cho bước sau.

### Minh họa hai luồng

~~~mermaid
flowchart TD
    subgraph A["Phản mẫu: phản hồi dồn cuối kỳ"]
      A1["Phân tích hàng loạt"] --> A2["Code hàng loạt"]
      A2 --> A3["Hàng đợi QA"]
      A3 --> A4["Tích hợp muộn"]
      A4 --> A5["Phát hiện lỗi / sửa gấp"]
      A5 --> A6["Kiểm thử lại / lùi giao"]
    end
    subgraph B["Dòng phản hồi ngắn"]
      B1["Một lát cắt có giá trị + ví dụ"] --> B2["Test phù hợp và phát triển phần nhỏ"]
      B2 --> B3["CI / tích hợp thường xuyên"]
      B3 --> B4["Khám phá lỗi và đạt DoD"]
      B4 --> B5["Increment dùng được + phản hồi"]
      B5 --> B1
    end
~~~

**Khác biệt không nằm ở việc có QA hay không có QA.** Luồng thứ hai vẫn cần chuyên môn kiểm thử và các kiểm tra phù hợp, nhưng phản hồi xuất hiện **trong quá trình phát triển**, khi chi phí hiểu và sửa sai thường thấp hơn.

## 2. Vì sao kiểm thử muộn làm vòng học hỏi dài ra?

Kiểm thử có thể trả lời những câu hỏi **người dùng cần gì**, **mã có xử lý đúng không**, **các phần có hoạt động cùng nhau không** và **có tạo ra tác dụng phụ nguy hiểm không**. Nếu các câu hỏi này chỉ được đặt vào cuối kỳ, nhóm có thể xây nhiều thay đổi **dựa trên cùng một giả định sai**.

### Vòng phản hồi muộn dẫn đến làm lại

Giả sử một nhóm hiểu rằng HTTP 202 từ dịch vụ tiến độ nghĩa là **đã lưu bền vững**. Trên thực tế, 202 chỉ nghĩa là **đã chấp nhận xử lý bất đồng bộ**. Nếu không kiểm chứng hợp đồng sớm:

1. Backend xây API theo nghĩa “accepted”.
2. Frontend hiện “Đã lưu” ngay sau HTTP 202.
3. Mobile lưu trạng thái cục bộ dựa trên thông báo.
4. Bộ kiểm thử cuối kỳ mới so dữ liệu thực và phát hiện sự khác biệt.
5. Ba thành phần và dữ liệu kiểm thử đều phải điều chỉnh.

Khi vấn đề được phát hiện ở bước 1–2, số lựa chọn cần thay đổi có thể ít hơn. **Không có một hệ số chi phí sửa lỗi cố định cho mọi dự án**; tuy nhiên, càng nhiều thành phần phụ thuộc vào một giả định sai, khả năng làm lại và điều phối thường càng lớn.

### Những chi phí thường bị bỏ sót

| Chi phí | Biểu hiện |
| --- | --- |
| **Thời gian chờ** | Story nằm ở “Ready for QA” nhiều ngày |
| **Chuyển ngữ cảnh** | Developer phải quay lại mã viết từ đầu Sprint để sửa |
| **Làm lại dây chuyền** | Sửa hợp đồng kéo theo UI, API, test và dữ liệu |
| **Xung đột nhánh mã** | Nhiều thay đổi lớn chỉ được merge cùng lúc |
| **Môi trường dùng chung** | Nhóm phải xếp hàng để tích hợp |
| **Đánh giá sai tiến độ** | Báo code-complete như sản phẩm đã Done |
| **Rủi ro phát hành** | Ít thời gian kiểm chứng và xử lý lỗi nghiêm trọng |
| **Gánh nặng con người** | QA và vận hành bị dồn việc, Developers sửa gấp cuối kỳ |
| **Phản hồi người dùng muộn** | Tính năng không thể thử với người dùng khi chưa đạt chất lượng |

### Độ dài phản hồi khác độ dài Sprint

Một nhóm có Sprint hai tuần nhưng mỗi thay đổi chỉ tích hợp vào ngày cuối **vẫn có vòng phản hồi kỹ thuật dài gần hai tuần**. Một nhóm khác có thể nhận phản hồi build và contract trong vài phút, phản hồi tích hợp vài lần mỗi ngày, và phản hồi sản phẩm sau những lát cắt đủ điều kiện.

**Agile không có nghĩa mọi kiểm tra phải hoàn tất tức thì.** Nó có nghĩa chủ động **rút ngắn những vòng phản hồi cần thiết**, đưa những rủi ro lớn ra ánh sáng sớm và không che việc chưa hoàn thành.

## 3. Phân biệt các khái niệm thường bị nhập làm một

| Khái niệm | Ý nghĩa | Không đồng nghĩa |
| --- | --- | --- |
| **Coding completed** | Phần thay đổi mã dự kiến đã được viết | Hành vi đúng, tích hợp, DoD hoặc giá trị |
| **Testing** | Thu thập thông tin và kiểm chứng giả định, hành vi, rủi ro bằng nhiều kỹ thuật | Chỉ thao tác trên UI cuối kỳ |
| **Quality assurance (QA)** | Các hoạt động có hệ thống hỗ trợ chất lượng xuyên vòng đời | Một người hoặc phòng ban chịu toàn bộ trách nhiệm chất lượng |
| **Integration** | Các thành phần, hợp đồng, dữ liệu và hành vi phối hợp được kiểm tra | Chỉ merge Git thành công |
| **Verification** | Kiểm tra có đáp ứng tiêu chí/quy định/đặc tả phù hợp không | Tự chứng minh đó là tính năng người dùng cần |
| **Validation** | Tìm hiểu giải pháp có phù hợp nhu cầu, ngữ cảnh sử dụng không | Chỉ chạy bộ unit test |
| **Definition of Done (DoD)** | Mô tả chính thức trạng thái chất lượng cần đạt để công việc thuộc Increment | Danh sách task đã viết xong |
| **Increment** | Bước tiến cụ thể hướng Product Goal, usable và đáp ứng DoD trong Scrum | Mã riêng lẻ chưa tích hợp |
| **Deployment** | Đưa thay đổi tới một môi trường | Mọi người dùng đều thấy tính năng |
| **Release/exposure** | Làm khả năng sẵn cho người dùng mục tiêu theo điều kiện | Outcome đã đạt |
| **Outcome** | Thay đổi hữu ích trong trải nghiệm/hành vi hoặc kết quả người dùng | Số test, số PR hoặc số lần deploy |

**Kiểm thử không phải một trạm cuối chuyền.** Nó có thể bắt đầu từ câu hỏi nghiệp vụ, ví dụ chấp nhận và phân tích rủi ro, tiếp tục cùng mã và tích hợp, rồi bổ sung quan sát trong điều kiện sử dụng thật.

## 4. Scrum: Increment và Definition of Done không cho phép “Done giả”

Theo **Scrum Guide 2020**, Scrum Team gồm Product Owner, Scrum Master và Developers, không có sub-team hoặc cấp bậc nội bộ; toàn Scrum Team cùng chịu trách nhiệm tạo **Increment có giá trị, hữu ích** mỗi Sprint. Developers chịu trách nhiệm chất lượng thông qua **Definition of Done**.

### Khi nào một Product Backlog Item được xem là Done?

Trong Scrum, phần việc không đáp ứng DoD **không phải một phần của Increment đã hoàn thành**. Nếu chưa đạt DoD, công việc không thể được trình bày như đã hoàn tất trong Sprint Review; nó quay lại Product Backlog để được xem xét sau. Cần phân biệt **công việc đã thực hiện** với **phần Increment thực sự đạt chất lượng**.

### DoD có thể bao gồm điều gì?

Một **ví dụ minh họa**, không phải DoD chuẩn cố định của mọi sản phẩm:

~~~text
Một lát cắt khôi phục tiến độ được Done khi:
  - Ví dụ chấp nhận nghiệp vụ quan trọng đã được xác nhận.
  - Mã, kiểm thử và review kỹ thuật phù hợp đã hoàn tất.
  - CI và test liên quan đạt, không có lỗi chặn chưa giải quyết.
  - API, quyền tài khoản và dữ liệu đã được kiểm chứng tích hợp.
  - Không báo "đã lưu" khi mới có yêu cầu chưa xác nhận.
  - Các yêu cầu bảo mật, riêng tư, hiệu năng liên quan được đáp ứng.
  - Có khả năng quan sát và xử lý lỗi phù hợp mức rủi ro.
  - Increment sử dụng được và phù hợp tiêu chuẩn chung của sản phẩm.
~~~

Một tổ chức có thể có tiêu chuẩn bắt buộc riêng. Nếu nhiều Scrum Team cùng phát triển **một sản phẩm**, họ phải cùng tuân thủ **một Definition of Done cho sản phẩm đó**. Không thể để một team coi “code merged” là Done còn team khác yêu cầu kiểm thử tích hợp để bảo vệ cùng một Increment.

### Ba hiểu lầm cần tránh

1. **“DoD chỉ do QA ký”:** Kiểm thử chuyên môn rất quan trọng, nhưng accountability tạo Increment đạt chất lượng không thể chỉ chuyển hết cho tester.
2. **“Chờ UAT sau Sprint cũng tính Done”:** Nếu một kiểm chứng là điều kiện của DoD, phần chưa đạt không thể coi đã Done. Một quy trình phê duyệt ngoài DoD có thể tồn tại tùy bối cảnh, nhưng cần minh bạch ranh giới và rủi ro.
3. **“Sprint Review là cửa phát hành”:** Scrum Guide nêu Increment có thể được giao cho stakeholder trước khi Sprint kết thúc; Sprint Review không phải cổng bắt buộc để phát hành.

**DoD không phải một rào cản được đặt ở cuối để dồn hết công việc kiểm tra.** Nó là **tiêu chuẩn được hiện thực liên tục**, giúp một Increment không phải chờ “đợt làm sạch” cuối kỳ mới dùng được.

## 5. Trách nhiệm chất lượng chung không xóa chuyên môn kiểm thử

Phản mẫu “dev code, QA test, Ops chịu production” thường tạo cảm giác **mỗi nhóm có thể hoàn thành trách nhiệm bằng cách chuyển artifact sang nhóm khác**.

### Phân công theo chuyên môn khác chuyển giao trách nhiệm

| Chủ thể | Đóng góp đặc thù | Điều không nên giả định |
| --- | --- | --- |
| **Product Owner** | Làm rõ giá trị, Product Backlog và trao đổi tình huống nghiệp vụ với stakeholder | Product Owner phải viết tất cả test hoặc phê duyệt mọi commit |
| **Developers** | Thiết kế, code, test, tích hợp, vận hành theo năng lực cần để tạo Increment đạt DoD | Chỉ cần viết mã, phần còn lại không thuộc trách nhiệm của mình |
| **Tester / quality specialist** | Phân tích rủi ro, thiết kế thử nghiệm, kiểm thử khám phá, kiểm tra tính đúng và hỗ trợ chất lượng | Người duy nhất “sở hữu” chất lượng hoặc phải chờ mã hoàn tất mới làm việc |
| **Scrum Master** | Hỗ trợ Scrum và giúp Scrum Team cải thiện hiệu quả, loại bỏ trở ngại phù hợp | Người chỉ định task, người “săn” tester hoặc người ký chất lượng |
| **Platform / SRE / Ops** | Hạ tầng, pipeline, quan sát, độ tin cậy và hỗ trợ khả năng tự phục vụ | Nơi nhận trách nhiệm về tất cả lỗi tính năng sau bàn giao |
| **Security / privacy specialist** | Quy định an toàn, threat modeling, kiểm chứng rủi ro chuyên sâu | Có thể bỏ qua kiểm soát bắt buộc để đạt Sprint Goal |
| **Stakeholder / người dùng** | Xác nhận nhu cầu, phản hồi giá trị và trường hợp thực tế | Là lớp test thay thế kiểm thử kỹ thuật |

Trong Scrum, những người có chuyên môn kiểm thử **vẫn có thể là Developers trong Scrum Team**, vì “Developers” là một accountability, không đồng nghĩa chỉ người viết code. Điều quan trọng là nhóm **có đủ kỹ năng cần thiết để tạo Increment đạt DoD** và hợp tác xuyên chuyên môn.

### Một hội thoại tốt hơn ở đầu story

Thay vì:

> Developer: “Khi tôi code xong sẽ đưa tester xác nhận.”

Thử:

> Product Owner: “Người học được phép nhìn thấy trạng thái ‘Đã lưu’ khi nào?”
>
> Tester: “Ta cần thử mất mạng sau khi request được nhận nhưng trước khi lưu bền vững.”
>
> Developer: “Vậy hợp đồng API phải phân biệt accepted và confirmed. Tôi sẽ thêm ví dụ/contract test trước khi ghép UI.”

**Người kiểm thử tham gia sớm không làm giảm chuyên môn của họ**. Trái lại, họ có cơ hội chuyển từ chỉ bắt lỗi cuối kỳ sang **giảm rủi ro ngay khi quyết định được hình thành**.

## 6. Vì sao “ném qua tường” tạo hàng đợi và mất bối cảnh?

Một workflow có thể được mô tả:

~~~text
Ready for Dev -> In Dev -> Ready for QA -> In QA
    -> Ready for Integration -> In Integration
    -> Ready for Release -> Done
~~~

Nhiều cột **không tự chứng minh** có vấn đề. Nếu mỗi bước là trạng thái thực và minh bạch, bảng có thể giúp nhận biết hàng đợi. Phản mẫu xảy ra khi mọi người **tối ưu bước của mình** mà không quan tâm **thời gian hạng mục chờ tới khi dùng được**.

### Hai chỉ số khác nhau

- **Thời gian xử lý (active time):** Có người thực sự kiểm tra, phát triển hoặc tích hợp hạng mục.
- **Thời gian trôi qua (elapsed time):** Kể cả lúc hạng mục nằm trong hàng đợi và blocked.

Ví dụ giả định tuần tự:

| Giai đoạn | Xử lý (ngày) | Chờ (ngày) |
| --- | ---: | ---: |
| Làm rõ ví dụ | 1 | 0 |
| Chờ bắt đầu phát triển | 0 | 2 |
| Phát triển | 3 | 0 |
| Chờ QA | 0 | 5 |
| Kiểm thử và báo lỗi | 2 | 0 |
| Chờ tích hợp | 0 | 4 |
| Tích hợp/sửa tương thích | 2 | 0 |
| Kiểm chứng phát hành | 1 | 0 |
| **Tổng** | **9** | **11** |

Theo giả định cùng dùng **ngày lịch** và không có các bước song song, lead time từ bắt đầu ranh giới đo đến bước cuối là:

\[
9 + 11 = 20\ \text{ngày}.
\]

Tỷ lệ thời gian xử lý so với tổng thời gian:

\[
\frac{9}{20}\times100\%=45\%.
\]

**45% là flow efficiency trong mô hình thời gian minh họa**, không có nghĩa mọi Developer chỉ làm việc 45% thời gian. Phần chờ thuộc về **hạng mục trong hệ thống**, không trực tiếp đo sự bận rộn của con người.

Nếu nhóm tối ưu code từ ba còn hai ngày nhưng vẫn phải chờ QA và tích hợp chín ngày, lead time chỉ giảm từ 20 xuống **19 ngày**. Giảm những hàng đợi phù hợp có thể tác động mạnh hơn.

### Lỗi quay ngược làm chi phí tăng

Khi tester báo lỗi, Developer phải:

1. Tìm lại bối cảnh của mã viết nhiều ngày trước.
2. Tái hiện trên một môi trường có thể khác môi trường phát triển.
3. Kiểm tra những thay đổi mới đã merge từ thời điểm đó.
4. Sửa mã, test, hợp đồng hoặc dữ liệu.
5. Đẩy hạng mục quay lại bước review/QA/tích hợp.

Mỗi vòng lặp này **tăng Work Item Age**, làm hỏng dự báo và có thể khiến nhiều hạng mục khác bị chặn. **Giảm số lần chuyển giao không có nghĩa bỏ kiểm soát độc lập cần thiết**; nó nghĩa **đưa các câu hỏi và bằng chứng chất lượng vào công việc liên tục**.

## 7. Chia lát cắt dọc để kiểm chứng thay vì hoàn thành từng lớp

Một chức năng người dùng thường liên quan giao diện, xử lý nghiệp vụ, lưu trữ và các hệ thống liên quan. Nếu chia công việc theo lớp kỹ thuật, các phần có thể được báo Done riêng lẻ nhưng **đường người dùng chưa hoạt động**.

### Chia ngang và chia dọc

| Cách chia | Ví dụ | Tín hiệu học hỏi |
| --- | --- | --- |
| **Theo thành phần (ngang)** | Sprint 1 toàn bộ backend; Sprint 2 toàn bộ UI; Sprint 3 tích hợp/test | Ít cơ hội thử hành trình thật cho tới cuối |
| **Theo hành vi (dọc)** | Lát cắt 1: học viên lưu và khôi phục một bước có xác nhận; lát cắt 2: xử lý mất mạng; lát cắt 3: đồng bộ trường hợp phức tạp | Mỗi lát cắt có thể tích hợp/kiểm chứng theo DoD |
| **Spike có giới hạn** | Thử cơ chế lưu bền vững và hợp đồng trả lời | Giảm bất định nhưng không tự là Increment người dùng |

**Lát cắt dọc không có nghĩa làm phiên bản đầu không an toàn.** Một lát cắt nhỏ vẫn phải tuân thủ kiểm soát tài khoản, quyền truy cập, tính đúng dữ liệu và những điều kiện chất lượng đang áp dụng.

### Một đường chia hợp lý

~~~text
Product Goal:
  Học viên tiếp tục học đúng nơi đã dừng.

LÁT CẮT 1:
  Khi học viên A hoàn thành bước 4, trạng thái lưu
  được xác nhận; quay lại cùng tài khoản thì thấy bước 4.

LÁT CẮT 2:
  Khi API chưa xác nhận, UI không tuyên bố "Đã lưu".
  Người học được thông báo trạng thái đang đồng bộ hợp lý.

LÁT CẮT 3:
  Xử lý phản hồi đến muộn, retry và mạng không ổn định.

CHƯA MẶC ĐỊNH:
  Offline đa thiết bị hoặc migration toàn bộ hệ thống
  nếu chưa có nhu cầu/rủi ro được xác nhận.
~~~

Nếu tình huống retry hoặc quyền truy cập là điều kiện tối thiểu để lát cắt đầu **an toàn**, phải đưa chúng vào chất lượng của lát cắt đầu, không hoãn để trình diễn cho kịp.

### Khi phải phụ thuộc nhóm khác

Một lát cắt có thể đi qua nhiều nhóm. Khi ấy cần:

- Cùng hiểu **hành vi end-to-end và Definition of Done** áp dụng.
- Xác định **hợp đồng có thể kiểm chứng sớm**, không chỉ hứa “API sẽ sẵn sàng”.
- Làm rõ điểm tích hợp, môi trường và đường kiểm thử.
- Theo dõi **lát cắt tới khi dùng được**, không cộng task Done cục bộ thành giá trị.

## 8. Ví dụ nghiệp vụ trước khi code: tránh sửa lại tiêu chí chấp nhận

**Example Mapping** hoặc một cuộc trao đổi theo tinh thần **Three Amigos** (góc nhìn nghiệp vụ, phát triển, kiểm thử) giúp nhóm tìm khác biệt trong cách hiểu trước khi đầu tư quá nhiều mã.

### Một ví dụ hành vi

| Loại | Nội dung |
| --- | --- |
| **Story** | Học viên quay lại đúng tiến độ đã lưu |
| **Rule 1** | Chỉ nói “Đã lưu” khi có xác nhận hợp lệ |
| **Example** | HTTP 202 chỉ nhận xử lý → UI đang đồng bộ, không báo thành công |
| **Rule 2** | Truy cập tiến độ theo đúng tài khoản có quyền |
| **Example** | A đã học bước 4, B không được đọc tiến độ riêng của A |
| **Question** | Một phản hồi cũ đến sau phản hồi mới thì xử lý thứ tự thế nào? |
| **Risk** | Người học đóng trình duyệt sau thông báo thành công giả |

### Diễn đạt bằng Given–When–Then

~~~gherkin
Feature: Lưu và khôi phục tiến độ đáng tin cậy

  Scenario: Chỉ thông báo thành công sau khi đã xác nhận lưu
    Given học viên A hoàn thành bước 4
    And dịch vụ mới xác nhận đã tiếp nhận yêu cầu lưu
    When giao diện hiển thị trạng thái
    Then giao diện không được hiện "Đã lưu thành công"

  Scenario: Quay lại đúng vị trí đã xác nhận
    Given tiến độ bước 4 của học viên A đã được lưu và xác nhận
    When học viên A mở lại cùng bài học
    Then giao diện khôi phục vị trí phù hợp với bước 4

  Scenario: Không truy cập dữ liệu của người khác
    Given học viên A có tiến độ riêng
    When học viên B cố đọc tiến độ của học viên A
    Then hệ thống từ chối truy cập trái phép
~~~

Các ví dụ này **không tự động là toàn bộ acceptance criteria**; Product Owner và những người hiểu nghiệp vụ cần làm rõ ý nghĩa, trong khi Developers và tester xem xét thêm lỗi, bảo mật, tính đồng thời và tích hợp. Mục tiêu của ví dụ là **đưa bất định ra trước khi mã nhiều thành phần cùng dựa vào giả định sai**.

## 9. Test-Driven Development: phản hồi về thiết kế và hành vi trong lúc phát triển

**Test-Driven Development (TDD)** là thực hành phát triển bằng những vòng kiểm thử và thay đổi mã nhỏ. Một mô tả thường dùng là **Red – Green – Refactor**:

1. **Red:** Viết một kiểm thử nhỏ mô tả hành vi mong muốn; xác nhận nó thất bại vì hành vi chưa có.
2. **Green:** Viết phần mã vừa đủ để kiểm thử đi qua.
3. **Refactor:** Cải thiện cấu trúc mà vẫn giữ hành vi đã được bảo vệ bằng kiểm thử.
4. Tiếp tục với một hành vi nhỏ khác.

~~~mermaid
flowchart LR
  A["Ví dụ/hành vi nhỏ"] --> B["Red: test fail đúng lý do"]
  B --> C["Green: hiện thực tối thiểu"]
  C --> D["Refactor: đơn giản hóa"]
  D --> E["Chạy các test liên quan"]
  E --> A
~~~

### Ví dụ kiểm thử giả mã

~~~java
// Minh họa ý tưởng; không phải chương trình chạy độc lập.
@Test
void acceptedRequestMustNotBeDisplayedAsPersisted() {
    SaveResponse response = new SaveResponse(SaveStatus.ACCEPTED);

    String message = progressPresenter.messageFor(response);

    assertNotEquals("Đã lưu thành công", message);
    assertEquals("Đang đồng bộ", message);
}
~~~

Kiểm thử trên có thể bảo vệ logic hiển thị cục bộ. Nó **chưa chứng minh** dịch vụ có thật sự lưu dữ liệu, và chưa kiểm tra việc tài khoản B có thể truy cập tiến độ của A. Vì vậy, **TDD ở mức đơn vị không thay thế contract/integration/security tests**.

### Những hiểu lầm về TDD

- **“TDD = viết test cho đủ coverage.”** Không. TDD còn là cách nhận phản hồi về thiết kế và hành vi khi mã còn nhỏ.
- **“Mọi code đều phải viết cùng một loại test trước.”** Hãy chọn điểm kiểm chứng phù hợp; những phần khó tái hiện có thể cần spike hoặc chiến lược khác.
- **“Test luôn xanh nên sản phẩm đúng.”** Test có thể kiểm tra sai yêu cầu, thiếu trường hợp hoặc dùng mock không đúng hợp đồng thật.
- **“Refactor là việc sau khi giao xong.”** Refactoring có kiểm soát là một phần giúp giữ chi phí thay đổi thấp trong quá trình phát triển.

TDD hữu ích khi nhóm **có ví dụ đủ rõ và có thể kiểm chứng tự động ở lớp phù hợp**, không phải một nghi thức cần áp đặt mù quáng để “được coi là Agile”.

## 10. BDD và kiểm thử chấp nhận: kéo phản hồi nghiệp vụ về gần quyết định

**Behavior-Driven Development (BDD)** nhấn mạnh làm rõ hành vi dựa trên ví dụ và ngôn ngữ dùng chung. Kiểm thử chấp nhận hỗ trợ nhóm kiểm tra giải pháp có đáp ứng quy tắc/tiêu chí đã thống nhất.

### Một vòng trao đổi thực dụng

~~~text
Product Owner mô tả vấn đề người học
     |
     v
Tester hỏi những trường hợp biên và rủi ro
     |
     v
Developers hỏi hợp đồng và tính khả thi
     |
     v
Các bên viết ví dụ có thể kiểm chứng
     |
     v
Nhóm tạo lát cắt, kiểm thử trong lúc xây
     |
     v
Xem Increment thật và cập nhật hiểu biết
~~~

**Không phải mọi câu Given–When–Then đều cần tự động hóa nguyên văn**. Một bảng ví dụ giúp hiểu chung có thể tạo giá trị dù chưa biến thành một file chạy được. Khi tự động hóa, chọn những hành vi có ích, ổn định và có chi phí duy trì hợp lý.

### Phân biệt làm rõ trước và “ký UAT cuối kỳ”

| Làm rõ xuyên suốt | UAT chỉ xuất hiện cuối kỳ |
| --- | --- |
| Các bên đặt câu hỏi trước quyết định thiết kế | Phát hiện hiểu sai sau khi mọi lớp đã viết |
| Ví dụ thay đổi được khi có phản hồi có căn cứ | Cố ép chấp nhận danh sách yêu cầu cũ |
| Increment được kiểm tra từng lát cắt | Chờ gom chức năng để kiểm một lần |
| Người dùng/stakeholder phản hồi nhiều thời điểm phù hợp | “Ký biên bản” mới được coi là có trao đổi |

Kiểm thử chấp nhận độc lập theo hợp đồng, luật hoặc quy định **vẫn có thể cần thiết**. Nhưng tổ chức nên **xác định điều kiện sớm và dùng kết quả xuyên vòng đời**, thay vì coi bước phê duyệt cuối là nơi đầu tiên phát hiện sai hiểu.

## 11. Continuous Integration: tích hợp thường xuyên, phát hiện lỗi khi còn nhỏ

**Continuous Integration (CI)** là thực hành tích hợp thay đổi thường xuyên vào một nhánh chung hoặc trạng thái tích hợp dùng chung, với **build và các kiểm tra tự động** giúp nhận biết thay đổi không tương thích sớm. Mục tiêu là tránh tồn tại nhiều thay đổi chưa được kiểm chứng trong thời gian dài.

### Phản mẫu khi nhánh sống quá lâu

~~~text
Nhánh A: sửa API tiến độ trong 9 ngày -------\
Nhánh B: đổi màn hình trong 8 ngày ------------> Ghép cuối Sprint
Nhánh C: migration dữ liệu trong 6 ngày ------/
                                             |
                                             v
                                  Xung đột, test fail, sửa gấp
~~~

### Vòng CI tốt hơn

~~~mermaid
flowchart LR
  A["Thay đổi nhỏ"] --> B["Review/test phù hợp"]
  B --> C["Tích hợp thường xuyên"]
  C --> D["Build + unit/contract/integration checks"]
  D --> E{"Kết quả"}
  E -->|"Pass"| F["Trạng thái tích hợp sẵn cho lát cắt tiếp"]
  E -->|"Fail"| G["Sửa sớm / phục hồi pipeline"]
  G --> B
  F --> A
~~~

### CI cần những điều kiện gì?

- Mã được tích hợp **với nhịp đủ thường xuyên** để phát hiện sai lệch trước khi tích tụ.
- Build/test có **kết quả rõ, tái hiện được và dễ chẩn đoán**.
- Khi pipeline đỏ, nhóm **ưu tiên khôi phục tín hiệu** thay vì bỏ qua hàng ngày.
- Có chính sách review/phê duyệt theo rủi ro mà **không kéo hàng đợi vô ích**.
- Kiểm thử phù hợp **hợp đồng API, migration, phân quyền và hành vi quan trọng**, không chỉ build thành công.
- Tránh để kiểm thử flaky tạo **báo động giả liên tục** khiến nhóm mất niềm tin vào CI.

### Hai nhầm lẫn thường gặp

1. **“Có CI server = đang thực hành CI.”** Nếu mỗi người chỉ merge một nhánh khổng lồ cuối tháng, công cụ không tạo vòng phản hồi ngắn.
2. **“CI xanh = đã đủ để phát hành.”** CI chỉ chứng minh **những kiểm tra thật sự chạy và được diễn giải đúng**. Rủi ro chưa được kiểm tra vẫn tồn tại.

### Trunk-based và các nhánh tính năng

Trunk-based development là một lựa chọn giúp giảm thời gian mã sống tách khỏi trạng thái tích hợp chung. Một nhóm vẫn có thể dùng nhánh ngắn, review mã và CI hiệu quả nếu **thay đổi nhỏ, sớm được kiểm chứng và thường xuyên được tích hợp**. Không cần bắt mọi dự án dùng một chiến lược Git giống hệt nhau để xử lý sai lầm kiểm thử muộn.

## 12. Chiến lược kiểm thử nhiều lớp: phản hồi nhanh và đủ chiều sâu

“Shift-left” không có nghĩa đẩy **mọi loại kiểm thử UI** sang trước khi có UI. Mỗi loại kiểm chứng có **đối tượng, tốc độ và chi phí bảo trì** khác nhau.

| Lớp/thực hành | Câu hỏi chính | Thời điểm phù hợp | Giới hạn |
| --- | --- | --- | --- |
| **Static analysis / lint / type check** | Mã có vi phạm quy tắc cú pháp, kiểu, pattern nguy hiểm? | Khi viết mã, trên CI | Không hiểu đầy đủ nghiệp vụ |
| **Unit test** | Quy tắc hoặc hàm nhỏ có đúng? | Trong phát triển, rất thường xuyên | Mock có thể không phản ánh hệ khác |
| **Component test** | Một module/service làm đúng hợp đồng vào/ra? | Trong phát triển và CI | Chưa chứng minh hành trình đa service |
| **API/contract test** | Producer và consumer có thống nhất hợp đồng? | Khi thiết kế và thay đổi ranh giới | Không thay kiểm chứng giá trị người dùng |
| **Integration test** | Các thành phần/dữ liệu phối hợp đúng? | Sớm, trong CI hoặc môi trường tương ứng | Có thể chậm, dữ liệu môi trường phức tạp |
| **End-to-end test** | Hành trình người dùng quan trọng hoạt động xuyên lớp? | Từng lát cắt, theo rủi ro | Chậm và dễ flaky nếu quá nhiều |
| **Exploratory testing** | Có hành vi bất ngờ, hiểu nhầm, rủi ro chưa nghĩ tới? | Trong lát cắt và trước/sau phát hành phù hợp | Cần chuyên môn, ghi nhận bài học |
| **Performance/reliability test** | Độ trễ, tải, timeout, phục hồi có phù hợp? | Sớm cho rủi ro chính, kiểm chứng lại khi thay đổi | Không thể giả định môi trường test giống production |
| **Security/privacy test** | Phân quyền, dữ liệu, cấu hình, lỗ hổng có được bảo vệ? | Ngay từ mô hình rủi ro, liên tục | Tự động hóa không thay đánh giá chuyên sâu |
| **Operational validation** | Quan sát, rollout, rollback/roll-forward, cảnh báo hoạt động? | Trước và trong phát hành | Không thay kiểm thử chức năng |
| **User validation** | Giải pháp có giúp người dùng đạt outcome? | Từ prototype tới sử dụng thật | Không thay chất lượng kỹ thuật |

### Test pyramid là gợi ý, không phải chỉ tiêu hình học

Một mô hình phổ biến khuyên dùng **nhiều kiểm thử nhanh, ổn định ở lớp thấp** và **ít kiểm thử end-to-end thật sự quan trọng**. Nhưng không tồn tại tỷ lệ cố định như “70/20/10” đúng cho mọi hệ thống.

Sản phẩm có nhiều dữ liệu và hợp đồng tích hợp có thể cần contract/integration tests mạnh; UI phức tạp có thể cần một số kiểm chứng ở giao diện; hệ thống điều khiển thiết bị có thể yêu cầu mô phỏng/hardware tests. **Chọn theo đặc điểm rủi ro và tốc độ phản hồi**, không theo biểu đồ trang trí.

### Tại sao không tự động hóa mọi thao tác UI?

Nếu mỗi lần sửa một nút nhỏ khiến hàng trăm UI test chập chờn, pipeline sẽ chậm và bị bỏ qua. Có thể:

- Bảo vệ nhiều quy tắc bằng unit/component tests.
- Dùng contract tests để bắt sai lệch API.
- Chỉ giữ **hành trình người dùng quan trọng** ở lớp end-to-end.
- Dành không gian cho **exploratory testing**, usability và rủi ro mới.

## 13. Contract testing: phát hiện sai nghĩa giữa các nhóm trước khi tích hợp lớn

Trong hệ thống nhiều service, **API hợp kiểu dữ liệu chưa chắc hợp nghĩa nghiệp vụ**. Ví dụ cả frontend và backend đều thấy trường:

~~~json
{
  "status": "accepted",
  "requestId": "illustrative-request"
}
~~~

Nếu frontend hiểu **accepted = persisted**, còn backend hiểu **accepted = queued**, hệ thống có thể vượt qua kiểm thử schema nhưng vẫn làm người học hiểu sai rằng tiến độ đã an toàn.

### Cần kiểm tra cả schema lẫn semantics

| Câu hỏi | Ví dụ |
| --- | --- |
| **Định dạng** | Trường status có những giá trị nào? |
| **Ngữ nghĩa** | accepted, processing, persisted, failed có nghĩa gì? |
| **Thứ tự** | Phản hồi cũ đến muộn có thể ghi đè tiến độ mới? |
| **Lỗi** | Timeout và retry có gây ghi trùng hoặc báo thành công giả? |
| **Phân quyền** | Request có thể đọc dữ liệu của tài khoản khác không? |
| **Tương thích phiên bản** | Client cũ có xử lý được status mới? |
| **Khả năng phục hồi** | Khi service tạm mất kết nối, client nhận trạng thái nào? |

### Một chu trình hợp đồng liên nhóm

1. Người phát triển và người sử dụng API làm rõ **ví dụ nghiệp vụ** trước thay đổi.
2. Hợp đồng và giả định về lỗi, version, quyền được viết **dưới dạng kiểm chứng được**.
3. Producer và consumer chạy kiểm tra phù hợp **trong CI** của các bên.
4. Thay đổi phá tương thích phải có **chiến lược chuyển đổi**.
5. Một lát cắt quan trọng vẫn được thử **end-to-end** để kiểm tra hành vi thực.

**Contract tests không chứng minh dữ liệu được lưu bền vững chỉ vì payload đúng**. Phải có kiểm chứng tích hợp hoặc vận hành cho điều kiện chất lượng đó.

## 14. Môi trường và dữ liệu kiểm thử: giải quyết nút thắt mà không bỏ an toàn

Một số nhóm biết cần tích hợp sớm nhưng bị giới hạn bởi **một môi trường staging dùng chung**. Mỗi nhóm phải đăng ký lịch, đợi dữ liệu mẫu, tránh làm hỏng cấu hình của nhau. Họ vẫn có thể gặp anti-pattern kiểm thử muộn dù Developer và tester muốn cải tiến.

### Ba nguyên nhân cần phân biệt

| Nguyên nhân | Biểu hiện | Hướng thử |
| --- | --- | --- |
| **Môi trường khan hiếm** | Chờ staging nhiều ngày | Tăng khả năng tạo môi trường thử độc lập, dùng container/test fixture khi khả thi |
| **Dữ liệu không ổn định** | Test chỉ chạy với dữ liệu thủ công hoặc tài khoản dùng chung | Fixture tái tạo, dữ liệu giả, dọn dữ liệu an toàn |
| **Hợp đồng chưa rõ** | Dùng môi trường thật rồi vẫn không biết output nào đúng | Example Mapping, contract test và câu hỏi nghiệp vụ |

### Test doubles và giả lập có giới hạn

**Mock, stub, fake hoặc service virtualization** có thể giúp kiểm tra một phần hành vi khi dịch vụ thật chưa sẵn sàng. Nhưng nếu giả lập phản ánh **hợp đồng sai**, nhóm sẽ có “test xanh giả” và lỗi chỉ xuất hiện khi tích hợp thật.

Để giảm rủi ro:

- Dựa giả lập trên hợp đồng được kiểm chứng, không chỉ kỳ vọng riêng một nhóm.
- Có kiểm tra với **thành phần thật** ở tần suất phù hợp.
- Không dùng dữ liệu production nhạy cảm nếu không có quyền và bảo vệ phù hợp.
- Kiểm tra migration, phiên bản và lỗi mạng khi liên quan.
- Ghi rõ **lớp rủi ro mà môi trường chưa thể mô phỏng**.

### Không cắt môi trường tích hợp thật hoàn toàn

Mục tiêu là **giảm hàng đợi không cần thiết**, không bỏ xác nhận tương thích khi phần mềm thật chạy cùng nhau. Một sản phẩm liên quan tiền, dữ liệu nhạy cảm hoặc quyền truy cập vẫn có thể cần nhiều tầng kiểm chứng; cần **bắt đầu sớm và quản lý mức rủi ro**, không đợi cuối kỳ mới chuẩn bị.

## 15. Pipeline kiểm chứng tối thiểu theo thay đổi nhỏ

Một pipeline có thể phát triển theo nhu cầu, không cần xây “nền tảng CI/CD hoàn hảo” trước khi cải tiến. Ví dụ sau chỉ mang tính **mô tả logic**, không phải cấu hình của công cụ cụ thể:

~~~yaml
# Pseudo pipeline minh họa, cần điều chỉnh theo sản phẩm.
on_small_change:
  - compile_and_static_checks
  - run_fast_unit_tests
  - run_relevant_component_tests
  - verify_api_contracts
  - check_dependency_and_security_rules

on_integration_state:
  - verify_database_migration_compatibility
  - run_selected_integration_tests
  - run_key_end_to_end_journeys
  - publish_quality_and_build_results

before_or_during_controlled_release:
  - review_remaining_risks_and_required_approvals
  - verify_observability_and_recovery_plan
  - check_operational_and_privacy_guardrails
  - observe_critical_user_journeys
~~~

### Cách chọn thứ tự đầu tư

1. Bắt đầu bằng **một hành vi có rủi ro thật** và test đáng tin cho nó.
2. Đưa kiểm tra đó vào **lần thay đổi nhỏ**, không chỉ chạy khi chuẩn bị release.
3. Giảm các lỗi giả, dữ liệu test không ổn định và thời gian phản hồi bất hợp lý.
4. Khi nhiều lỗi lặp ở một ranh giới, bổ sung **contract/integration tests** phù hợp.
5. Bảo vệ điều kiện release và vận hành, không suy từ pipeline xanh rằng mọi rủi ro đã được kiểm tra.

### Khi pipeline đỏ

Không nên nói “cứ merge trước, cuối Sprint sửa tất cả” rồi gọi đó là CI. Cần một **chính sách minh bạch**: xác định mức nghiêm trọng, người hỗ trợ, ưu tiên sửa, hành vi được phép khi hệ thống kiểm tra gặp sự cố và cách giữ thông tin cho mọi nhóm.

Một test flaky có thể cần được phân loại, điều tra và cô lập có kiểm soát, nhưng **xóa test âm thầm** để dashboard xanh có thể bỏ mất cảnh báo quan trọng.

## 16. Kiểm thử khám phá: không để automation biến thành sự tự tin sai

**Exploratory testing** kết hợp học về sản phẩm, thiết kế thử nghiệm và thực hiện kiểm thử trong cùng quá trình. Nó đặc biệt hữu ích khi có **hành vi bất ngờ, trải nghiệm khó mô hình hóa hoặc giả định chưa được kiểm chứng**.

### Những câu hỏi một tester có thể khám phá sớm

- Người học đang ở bước 4, mạng chập chờn và đóng tab ngay sau thông báo. Dữ liệu thực còn nguyên không?
- Khi thiết bị gửi hai yêu cầu lưu gần như đồng thời, phản hồi đến ngược thứ tự thì trạng thái nào thắng?
- Giao diện “Đang đồng bộ” có làm người học tưởng hệ thống bị treo không?
- Một tài khoản bị thu hồi quyền truy cập có còn xem được tiến độ cũ qua cache không?
- Khi dịch vụ đáp ứng chậm, nút “Tiếp tục” có tạo nhiều thao tác trùng?
- Dữ liệu bài học có ký tự đặc biệt, bài quá dài hoặc phiên bản cũ thì có bị hỏng không?

### Một exploratory testing charter ngắn

~~~text
MỤC TIÊU:
  Khám phá khả năng lưu/khôi phục tiến độ khi mạng thiếu ổn định.

PHẠM VI:
  Một học viên, cùng tài khoản, phiên bài học hợp lệ.

RỦI RO ƯU TIÊN:
  Báo lưu thành công giả, mất tiến độ và sai quyền.

KỸ THUẬT:
  Ngắt mạng, retry, đóng/mở tab, thay đổi thứ tự phản hồi.

BẰNG CHỨNG:
  Thời điểm request, response, trạng thái dữ liệu,
  ảnh/ghi chú tái hiện bằng dữ liệu thử an toàn.

ĐẦU RA:
  Điều quan sát được, giả thuyết, lỗi cần xử lý,
  trường hợp nên bổ sung kiểm thử tự động.
~~~

Không cần đợi có toàn bộ sản phẩm mới khám phá. Với một lát cắt nhỏ đã chạy được, tester và Developers có thể **thử cùng nhau**, phát hiện khoảng trống và biến những lỗi lặp lại thành kiểm chứng hồi quy phù hợp.

**Exploratory testing không phải giải pháp thay thế cho mọi kiểm thử tự động**; nếu phải thao tác thủ công hàng trăm lần cho cùng quy tắc ổn định, tổ chức đang tiêu tốn thời gian phản hồi và dễ bỏ sót lỗi lặp.

## 17. Chất lượng phi chức năng: không để hiệu năng, dữ liệu và bảo mật xuất hiện cuối kỳ

Một hệ thống có thể vượt qua test chức năng khi chỉ có một người dùng, rồi lỗi khi chịu tải, mất mạng hoặc gặp dữ liệu nhạy cảm. **Non-functional requirements** như độ trễ, khả năng mở rộng, tính an toàn, khả năng phục hồi và khả năng tiếp cận cần được xem theo rủi ro **ngay từ lúc thiết kế lát cắt**, không chỉ trong một “giai đoạn NFR” ở cuối.

| Rủi ro | Câu hỏi nên đặt sớm | Kiểm chứng phù hợp |
| --- | --- | --- |
| **Bảo mật/phân quyền** | A có thể đọc tiến độ của B không? | Threat modeling, test phân quyền, kiểm tra cấu hình |
| **Tính đúng dữ liệu** | Thế nào là “đã lưu bền vững”? | Test đọc lại, idempotency, xử lý timeout và ghi trùng |
| **Hiệu năng** | Tỷ lệ yêu cầu đúng và nhanh ở tải điển hình/cực trị? | Test tải theo ngưỡng có lý do, SLI phù hợp |
| **Độ tin cậy** | Dịch vụ bị gián đoạn thì trải nghiệm ra sao? | Fault injection có kiểm soát, retry/timeout test |
| **Khả năng phục hồi** | Khi release có lỗi, có thể khôi phục an toàn không? | Diễn tập rollback/roll-forward, backup/restore phù hợp |
| **Khả năng tiếp cận** | Người dùng bàn phím, screen reader có thể tiếp tục bài? | Kiểm thử tương tác và công cụ hỗ trợ phù hợp |
| **Quyền riêng tư** | Telemetry hoặc môi trường test có chứa dữ liệu không được phép? | Phân quyền, dữ liệu giả, kiểm tra lưu giữ và mục đích |
| **Tương thích phiên bản** | Client cũ còn hoạt động khi schema/API đổi không? | Contract và migration tests |

### Performance không chỉ là “chạy tải một lần cuối quý”

Nếu một query mới làm thời gian đọc tiến độ tăng đáng kể, test tích hợp với lượng dữ liệu đại diện có thể phát hiện sớm. Test tải diện rộng vẫn có thể cần giai đoạn chuẩn bị riêng, nhưng nên **xác định ngưỡng, dữ liệu và môi trường từ đầu**.

### Tránh làm hại dữ liệu thật khi thử

Không dùng một thí nghiệm fault injection tùy tiện trên production hoặc một migration chưa có phương án phục hồi chỉ để “kiểm thử sớm”. Những hoạt động rủi ro cần **môi trường, quyền, kiểm soát và quy trình phê duyệt phù hợp**. Phát hiện sớm không có nghĩa thử mọi điều trên khách hàng thật.

## 18. Shift-left và shift-right bổ sung nhau

**Shift-left testing** nhấn mạnh đặt câu hỏi, kiểm tra và ngăn lỗi **sớm hơn** trong vòng đời phát triển. **Shift-right** nhấn mạnh quan sát, xác nhận giả thuyết, độ tin cậy và trải nghiệm **trong điều kiện sử dụng thực**, có kiểm soát.

~~~text
Ý tưởng / nhu cầu
   |  Example Mapping, threat modeling, quy tắc chất lượng
   v
Thiết kế lát cắt
   |  Acceptance examples, contract, test-first
   v
Phát triển
   |  TDD, static checks, unit/component tests, review
   v
Tích hợp
   |  CI, contract/integration/end-to-end tests, exploratory
   v
Increment đạt DoD
   |  Quyết định release theo chính sách
   v
Tiếp xúc người dùng
   |  SLI/SLO, telemetry an toàn, canary, phản hồi support
   v
Học và điều chỉnh Product Backlog / kỹ thuật / cách làm
~~~

### Hai lỗi suy luận

- **“Có giám sát production nên có thể bớt kiểm thử trước release.”** Không đúng khi điều đó khiến người dùng chịu rủi ro chưa được kiểm soát. Quan sát sau phát hành **không thay DoD và kiểm tra an toàn**.
- **“Test trước nhiều rồi nên không cần xem sản phẩm sau release.”** Không đúng vì test không thể mô phỏng đầy đủ hành vi, tải, thiết bị và nhu cầu người dùng.

### Một vòng học có ích

Giả sử monitoring phát hiện tỷ lệ lỗi khôi phục cao ở mạng yếu. Nhóm:

1. Bảo vệ người dùng theo quy trình vận hành.
2. Điều tra và tái hiện bằng dữ liệu thử.
3. Sửa thiết kế và thêm kiểm thử hồi quy ở lớp phù hợp.
4. Tích hợp và xác minh trong CI.
5. Phát hành có kiểm soát, tiếp tục xem guardrail và outcome.

Như vậy, **bài học shift-right quay trở lại làm mạnh shift-left**, thay vì chỉ mở ticket cho một nhóm khác xử lý.

## 19. Tách deploy, release và outcome mà vẫn bảo vệ chất lượng

**Continuous Delivery** hướng đến trạng thái phần mềm có thể được phát hành một cách đáng tin cậy, thường nhờ tự động hóa build/test/deployment và giảm lô. **Continuous Deployment** là một bước xa hơn: những thay đổi đủ điều kiện có thể được triển khai vào production tự động theo chính sách. Hai khái niệm **không giống nhau**.

### Ba mốc khác nhau

| Mốc | Điều có thể khẳng định | Điều chưa được chứng minh |
| --- | --- | --- |
| **Đã deploy** | Mã/cấu hình được đưa lên một môi trường | Người dùng đã thấy tính năng |
| **Đã release/expose** | Người dùng mục tiêu có thể tiếp xúc | Hành vi đúng trong mọi trường hợp hoặc đạt outcome |
| **Đã có feedback/outcome** | Có dữ liệu hoặc nhận xét sau sử dụng | Toàn bộ thay đổi do tính năng gây ra nếu không có phương pháp phù hợp |

### Feature flags không chữa được mọi rủi ro

Feature flag có thể giúp tách việc **đưa mã lên môi trường** khỏi **bật tính năng cho người dùng**, hỗ trợ thử theo nhóm nhỏ và giảm phạm vi tác động. Nhưng:

- Tắt flag không tự **khôi phục dữ liệu đã ghi sai**.
- Flag tồn tại quá lâu gây nhiều nhánh hành vi khó kiểm chứng.
- Cần kiểm tra trạng thái **bật/tắt**, quyền truy cập, rollback và tương thích.
- Không dùng flag để “tạm cho qua” tính đúng dữ liệu hoặc rủi ro bảo mật.

### Release an toàn cần gì?

Một lựa chọn theo bối cảnh có thể bao gồm **phát hành nhỏ, canary, giám sát SLI, điều kiện dừng, backup/restore hoặc roll-forward**, cùng quy trình ứng phó sự cố. Không phải tổ chức nào cũng cần một hình thức rollout y hệt nhau. Điểm chung là **không phó mặc rủi ro cho nhóm vận hành ở cuối chuỗi**.

## 20. Lỗi được phát hiện là phản hồi; đừng biến nó thành vũ khí trách nhiệm

Khi QA báo lỗi vào cuối kỳ, một phản ứng thường thấy là “Tester làm chậm release”. Nhưng nếu tester phát hiện lỗi có thật, **việc đưa tin không gây ra lỗi**. Cần xem:

- Vì sao giả định sai tồn tại từ lúc làm rõ yêu cầu?
- Vì sao unit/contract/integration tests chưa phát hiện?
- Có phải môi trường thử quá muộn hoặc không đáng tin?
- Có chính sách nào khiến nhóm không thể làm việc với tester sớm?
- Vì sao story được báo “xong” trước khi đạt DoD?

### Bug triage không thay thế phòng ngừa

| Việc cần quyết định | Ví dụ |
| --- | --- |
| **Mức nghiêm trọng** | Mất tiến độ hoặc truy cập trái phép nguy hiểm hơn lỗi căn lề |
| **Ảnh hưởng người dùng** | Bao nhiêu người đủ điều kiện bị tác động, điều kiện tái hiện |
| **Tính cấp bách** | Có cần dừng rollout hoặc xử lý incident ngay? |
| **Nguyên nhân hệ thống** | Hợp đồng mơ hồ, test thiếu, môi trường/CI bất ổn |
| **Kiểm chứng sửa lỗi** | Test hồi quy phù hợp và kiểm tra end-to-end khi cần |
| **Phòng ngừa** | Sửa ví dụ nghiệp vụ, contract test, DoD, chính sách phối hợp |

Một lỗi nghiêm trọng được phát hiện trong production cần **ứng phó theo quy trình sự cố**, không chờ Sprint Planning kế tiếp mới cho phép xem. Những lỗi ít nghiêm trọng hơn có thể được Product Owner và Developers xem cùng Product Backlog, rủi ro và năng lực.

### Tránh KPI số bug cá nhân

Nếu thưởng “không có bug được phát hiện”, mọi người có động lực **không ghi lỗi**. Chất lượng cần được nhìn qua **tác động, mức nghiêm trọng, độ phủ rủi ro, khả năng phát hiện và phục hồi**, thay vì số lỗi từng người “gây ra” theo suy luận thiếu căn cứ.

## 21. Scrum events giúp kiểm tra chất lượng liên tục như thế nào?

Scrum không quy định mọi nhóm phải dùng TDD hay một công cụ CI cụ thể. Nhưng các Scrum events có thể tạo nhịp kiểm tra và thích ứng **chất lượng gắn với Sprint Goal và Increment**, thay vì kéo kiểm thử về cuối.

| Scrum event | Thảo luận có ích | Phản mẫu cần tránh |
| --- | --- | --- |
| **Sprint Planning** | Chọn Sprint Goal, làm rõ PBI, năng lực kiểm thử/tích hợp, rủi ro DoD | Tính code time riêng và quên test/integration capacity |
| **Daily Scrum** | Developers kiểm tra tiến độ hướng Sprint Goal, blocker, hạng mục chờ QA/tích hợp | Báo mỗi người đã code bao nhiêu |
| **Sprint Review** | Kiểm tra Increment thật, phản hồi người dùng, dữ liệu chất lượng và Product Goal | Trình diễn bản chưa đạt DoD như Increment hoàn tất |
| **Sprint Retrospective** | Xem lỗi phát hiện muộn, hàng đợi, chất lượng CI, thử cải tiến | Đổ lỗi nhóm QA hoặc ghi action không thực hiện |

### Sprint Backlog phải phản ánh công việc tạo Done

Nếu Developers chỉ lên kế hoạch code, không tính kiểm chứng hợp đồng, dữ liệu, tích hợp và DoD, Sprint Backlog **không thể hiện đầy đủ con đường đạt Sprint Goal**. Nhóm có thể chia công việc sao cho test/CI và hỗ trợ tester diễn ra **trong quá trình phát triển**.

### Daily Scrum không phải phiên báo cáo với QA manager

Nhìn một lát cắt bị chờ kiểm thử đã ba ngày, Developers có thể điều chỉnh kế hoạch:

> “Thay vì mở PBI mới, chúng ta cùng hoàn tất fixture dữ liệu và test tích hợp cho hạng mục gần Done.”

Đó là hành động thích ứng phù hợp. Không có quy định rằng mọi lỗi phải được giải quyết **trong 15 phút Daily Scrum**; trao đổi sâu có thể tiếp tục sau event với người phù hợp, nhưng kết quả ảnh hưởng Sprint Backlog cần được minh bạch.

### Review không tạo “cửa kiểm thử cuối”

Nếu Sprint Review diễn ra vào chiều cuối Sprint, nhóm **không được đợi đến sáng hôm đó mới kiểm chứng Increment**. Phát hành có thể xảy ra trước Review khi đáp ứng các điều kiện phù hợp; Review dùng để kiểm tra kết quả và thích ứng Product Backlog.

## 22. Kanban: làm lộ và giảm hàng đợi QA/tích hợp

Kanban giúp quan sát **trạng thái, hàng đợi và công việc đang già đi**, không chỉ số card đã bắt đầu. Khi QA là điểm nghẽn, điều nguy hiểm không nhất thiết là “tester ít người”, mà có thể là **nhiều việc đổ vào QA cùng lúc, test data không ổn định hoặc phụ thuộc chưa được giải quyết**.

### Một ví dụ bảng có hàng đợi rõ

~~~text
Ready | In Development | Waiting for Verification | Verifying
      |                 |                          |
      v                 v                          v
   Integrated / Meets DoD -----------------------> Done

Blocked markers và Work Item Age vẫn hiện trên card.
~~~

Tên cột cụ thể không quan trọng bằng **chính sách rõ về khi nào chuyển, ai hỗ trợ và Done nghĩa là gì**. Không làm biến mất hạng mục khỏi WIP chỉ vì “đã giao qua QA”.

### Chính sách thử khi hàng đợi phình ra

1. Nhìn **Work Item Age** của việc chờ xác minh và nguy cơ theo SLE.
2. Chọn **giúp hoàn tất hạng mục gần Done** khi có người đủ năng lực.
3. Hạn chế kéo thêm việc code mới nếu hệ thống đã tồn kho quá nhiều.
4. Tháo vấn đề gốc: fixture, quyền môi trường, tiêu chí mơ hồ, thiết kế API khó kiểm.
5. Tạo **kiểm tra nhanh phù hợp** để giảm khối lượng lặp thủ công.
6. Quan sát chất lượng và throughput qua vài kỳ để biết thay đổi có tác dụng không.

**Giới hạn WIP không phải lời hứa tăng năng suất lập tức**. Nếu bottleneck do chính sách phê duyệt hoặc chuyên gia chỉ có một người, giảm việc mới có thể làm chờ dễ thấy hơn nhưng vẫn cần **cải tiến điều kiện tổ chức**.

### SLE và Work Item Age

Một SLE có thể mô tả kỳ vọng dựa trên dữ liệu, ví dụ:

> “Khoảng 85% lát cắt tương tự hoàn tất trong 12 ngày từ Started tới Done theo workflow hiện tại.”

Đây là **một kỳ vọng có điều kiện**, không bảo đảm mọi story xong trong 12 ngày. Hạng mục đang mở với Work Item Age **14 ngày** cần được chú ý ngay, không đợi Done mới tính cycle time.

## 23. Đo cải tiến mà không tự làm đẹp con số

**Chỉ số tốt giúp nhóm quyết định nên sửa điều gì**. Một dashboard có thể đẹp giả nếu đổi cách đếm, đóng ticket trước kiểm thử hoặc chuyển thời gian chờ sang nhóm khác.

### Bộ tín hiệu cân bằng

| Góc nhìn | Chỉ số/câu hỏi | Cần đọc cùng |
| --- | --- | --- |
| **Flow** | End-to-end lead time, cycle time distribution | Ranh giới Started/Done, loại story |
| **Work in Progress** | WIP, Work Item Age, thời gian blocked | Hạng mục đang mở, nguyên nhân chờ |
| **Delivery** | Throughput lát cắt đạt DoD, thời gian tới release | Không cộng task cục bộ thành outcome |
| **Quality** | Defect escape, mức nghiêm trọng, rework | Exposure, cách báo lỗi, thay đổi test |
| **Integration** | Lỗi hợp đồng, build break, chờ môi trường | Test flaky, số thay đổi, tần suất CI |
| **Reliability** | SLI/SLO, incident, recovery time | Mức ảnh hưởng và chính sách an toàn |
| **Outcome** | Người học tiếp tục đúng tiến độ | Cohort, thời gian quan sát, telemetry |
| **Sustainability** | Việc ngoài giờ, gián đoạn và tải trực | Không dùng KPI cá nhân hoặc dữ liệu riêng tư |

### Ví dụ tính flow cơ bản

Trong một kỳ, năm lát cắt đạt DoD với cycle time:

\[
4,\ 5,\ 6,\ 7,\ 18\ \text{ngày}.
\]

- Mean = \((4+5+6+7+18)/5 = 8\) ngày.
- Median = **6 ngày**.
- Có một lát cắt mất **18 ngày** cần điều tra vì có thể liên quan tích hợp muộn.

Đội còn hai hạng mục **đang mở 20 và 23 ngày**. Chúng **không nằm trong mean của lát cắt đã Done** nhưng phải xuất hiện qua **Work Item Age, WIP và blocked status**.

### Dự báo có điều kiện

Nếu thông lượng toàn luồng trung bình là 5 lát cắt/tuần trong kỳ quan sát và các lát cắt **tương đối tương đồng**, đội có thể dùng dữ liệu phân phối để xây dự báo. Nhưng **không nên lấy một trung bình vài tuần để cam kết ngày chính xác** khi loại việc, công suất hoặc phụ thuộc thay đổi.

### Little's Law và các điều kiện

Với hệ thống có ranh giới đo nhất quán, quan sát đủ dài và gần trạng thái ổn định:

\[
\text{WIP trung bình}
=\text{Throughput trung bình}\times\text{Cycle time trung bình}.
\]

Ví dụ WIP trung bình **15 lát cắt**, throughput **3 lát cắt/tuần**, tương ứng cycle time trung bình **5 tuần** theo điều kiện nói trên. Nếu WIP xuống 9 và throughput **thực sự vẫn 3/tuần**, quan hệ tương ứng **3 tuần**.

**Không được suy ra** chỉ đặt WIP limit = 9 là tự động có throughput 3/tuần hoặc mọi lát cắt sẽ hoàn tất sau ba tuần. Không dùng công thức khi WIP đo task còn throughput đo story, hoặc chu kỳ và đơn vị thời gian không tương thích.

## 24. Khi nhiều nhóm cùng làm sản phẩm: tích hợp là trách nhiệm của dòng giá trị

Trong hệ thống lớn, công việc có thể trải qua các nhóm **ứng dụng, API, dữ liệu, bảo mật và nền tảng**. Khi mỗi nhóm coi phần của mình là Done mà không có ai xác nhận hành trình toàn sản phẩm, lỗi tích hợp sẽ xuất hiện ở cuối.

### Phụ thuộc liên nhóm không chỉ là vấn đề lịch họp

| Phụ thuộc | Rủi ro kiểm thử muộn | Cách giảm sớm |
| --- | --- | --- |
| **API consumer/producer** | Client và server hiểu khác status hoặc lỗi | Hợp đồng có ví dụ, contract tests trong CI |
| **Schema dữ liệu** | Client cũ không đọc được bản ghi sau migration | Versioning, expand–migrate–contract, kiểm thử tương thích |
| **Auth và phân quyền** | Hành vi chạy riêng nhưng lộ tiến độ người khác | Test end-to-end theo quyền và security review phù hợp |
| **Môi trường tích hợp** | Một hàng đợi nhiều ngày | Self-service/test containers khi khả thi, fixture rõ |
| **Chuyên gia khan hiếm** | Tester/DBA duy nhất phải kiểm mọi thay đổi | Pairing, mentoring, tự động hóa kiểm tra lặp |
| **Phê duyệt bắt buộc** | Một kiểm tra quan trọng chỉ biết ở ngày cuối | Làm rõ tiêu chí sớm, đưa kiểm tra đủ điều kiện vào workflow |
| **Đối tác ngoài** | Contract thay đổi hoặc sandbox không giống production | Test contract, version và kịch bản lỗi, dự báo phụ thuộc |

### Khi cùng một sản phẩm trong Scrum

Nếu nhiều Scrum Team phát triển **một sản phẩm**, Scrum Guide 2020 yêu cầu chia sẻ **một Product Goal, một Product Backlog, một Product Owner và một Definition of Done**. Các Scrum Team cần **cùng tạo Increment tích hợp, có thể dùng được**.

Một bảng cho thấy nhóm A có “API Done”, nhóm B “UI Done”, nhóm C “Data Done” vẫn **chưa chứng minh hành trình khôi phục tiến độ Done**. Hãy theo dõi **một lát cắt xuyên nhóm** từ lúc được bắt đầu tới khi đáp ứng tiêu chuẩn sản phẩm chung.

### Đừng phản ứng bằng cách thêm một ban kiểm thử cuối

Một “integration team” hoặc “release team” chuyên môn có thể cung cấp dịch vụ hữu ích. Nhưng nếu tất cả nhóm đều phải xếp hàng và **chuyển trách nhiệm lỗi sang đó**, vấn đề trở thành nút thắt mới.

Giải pháp có thể kết hợp:

1. **Hợp đồng rõ** để nhiều thay đổi được kiểm chứng trước khi tới môi trường tích hợp chung.
2. **Trách nhiệm tích hợp của người thực hiện thay đổi**, có chuyên gia hỗ trợ đúng điểm cần.
3. **Thử end-to-end theo lát cắt**, không chờ gom cả chương trình.
4. **Chính sách WIP và ưu tiên xử lý blocker chung**.
5. **Đường escalation có người có quyền**, thay vì thêm cuộc họp chỉ để đọc ticket.

## 25. Những nguyên nhân tổ chức khiến phản mẫu tái xuất hiện

Có lúc nhóm **biết** nên kiểm thử sớm nhưng không có quyền hoặc điều kiện làm. Chỉ đào tạo TDD hay yêu cầu “QA phải sớm hơn” sẽ không đủ nếu cơ chế quản trị vẫn giữ lối giao việc theo dây chuyền.

### Các nguyên nhân điển hình

| Nguyên nhân | Cách nó tạo QA/tích hợp muộn | Thay đổi cấp hệ thống cần xem |
| --- | --- | --- |
| **Thưởng theo output từng phòng** | Dev được chấm số code xong, tester chấm số bug tìm thấy | Đo kết quả toàn luồng và chất lượng, không lập giải đấu |
| **Chia việc theo tầng kỹ thuật** | Mỗi user story phải qua nhiều team | Lát cắt dọc, ghép cặp ranh giới, xem cấu trúc đội |
| **QA như cổng cuối độc lập tuyệt đối** | Tester chỉ được tham gia khi code đã “đóng” | Mời test specialist từ đầu; giữ kiểm soát độc lập khi thực sự cần |
| **Môi trường dùng chung khan hiếm** | Test tích hợp xếp hàng | Đầu tư test data, môi trường tự phục vụ và hợp đồng |
| **Quyền release mơ hồ** | Code xong chờ ký nhiều lớp | Rõ thẩm quyền, mức rủi ro và kiểm soát bắt buộc |
| **Năng lực luôn được sử dụng 100%** | Không có người hỗ trợ test và sửa lỗi | Quản lý WIP, năng lực dự phòng cho rủi ro và cải tiến |
| **Roadmap chi tiết bất biến** | Không dám giảm phạm vi khi rủi ro lộ | Product Goal, backlog thích ứng và ra quyết định theo giá trị |
| **Nợ kỹ thuật/CI yếu** | Tích hợp chậm, test khó chạy | Đầu tư kỹ thuật theo mức tác động, không “làm sau nếu rảnh” |
| **Báo cáo phạt lỗi** | Người làm việc ngại đưa tin xấu | Khuyến khích phản hồi trung thực, xem nguyên nhân hệ thống |
| **Phụ thuộc một chuyên gia** | Hàng đợi thẩm định kéo dài | Pairing, kiểm thử tự động, chia sẻ hiểu biết |

### Phân biệt quyền của nhóm và quyền tổ chức

**Developers** có thể chọn cách kiểm thử, chia lát cắt, ghép cặp và review mã trong phạm vi ràng buộc hiện có. **Product Owner** chịu trách nhiệm thứ tự Product Backlog theo giá trị. **Lãnh đạo hoặc người có quyền về môi trường/phê duyệt/bảo mật** cần xử lý những rào cản nhóm không thể tự thay đổi.

Nếu mọi action trong Retrospective là “tester phải cố gắng nhanh hơn” nhưng staging vẫn đóng, tổ chức đang **đặt trách nhiệm sai nơi có quyền hành động**.

### Khi nào cần giữ kiểm chứng độc lập?

Có những sản phẩm cần **kiểm toán, xác nhận bảo mật, đánh giá an toàn hoặc người phê duyệt độc lập** theo hợp đồng hoặc quy định. Những bước đó không tự là anti-pattern. Cần:

- Nêu điều kiện và bằng chứng **từ lúc lên kế hoạch**.
- Tự động hóa hoặc chuẩn bị sớm những phần phù hợp.
- Phân loại mức rủi ro và quy định **ai được ra quyết định**.
- Không đợi đến sát phát hành mới phát hiện **một điều kiện bắt buộc chưa thể đáp ứng**.
- Giữ minh bạch giữa **Increment đã đạt DoD** và **các điều kiện release hoặc chứng nhận khác** khi thực sự tách biệt.

## 26. Case study: từ “bàn giao QA cuối Sprint” sang kiểm chứng từng lát cắt

### 26.1. Bối cảnh

Một Scrum Team phát triển chức năng **lưu và khôi phục tiến độ học**. Thành viên có chuyên môn frontend, backend, kiểm thử và vận hành, nhưng đang làm theo chuỗi:

~~~text
Product Owner viết yêu cầu lớn
        |
        v
Backend xây toàn bộ API
        |
        v
Frontend xây toàn bộ UI
        |
        v
QA nhận đợt lớn cuối Sprint
        |
        v
Nhóm tích hợp kiểm thử trên staging
        |
        v
Phát hiện sai nghĩa "đã lưu", quyền truy cập và retry
        |
        v
Quay lại sửa / chờ release
~~~

Sprint dài hai tuần. Các ticket backend và frontend thường được báo “dev done” trước khi kiểm chứng tích hợp. Khi QA nhận đợt lớn, nhiều trường hợp cần hỏi lại PO nhưng PO đang ở cuộc họp lập kế hoạch giai đoạn tiếp theo. Môi trường staging dùng chung chỉ được mở vào cuối kỳ.

### 26.2. Vấn đề được đưa ra Retrospective

Thay vì kết luận “QA làm chậm”, nhóm viết:

> “Những lát cắt lưu tiến độ thường có nhiều ngày nằm chờ trước kiểm thử và tích hợp; các giả định sai về trạng thái lưu, retry và quyền tài khoản chỉ được phát hiện khi thay đổi đã lan sang nhiều thành phần.”

Nhóm phân biệt:

- **Quan sát:** PBI có Work Item Age cao ở hàng đợi QA; số lỗi liên quan hợp đồng xuất hiện cuối kỳ.
- **Giả thuyết:** Hợp đồng chưa được làm rõ sớm và test chỉ chạy sau khi code các lớp hoàn tất.
- **Rào cản:** Môi trường tích hợp cần quyền do nhóm nền tảng quản lý; nhóm sản phẩm không có khả năng tự tạo fixture đủ an toàn.
- **Guardrail:** Không được báo lưu thành công giả, làm mất tiến độ hoặc lộ dữ liệu người học.

### 26.3. Chọn một lát cắt nhỏ, đủ chất lượng

Nhóm và Product Owner thống nhất:

> “Khi học viên A hoàn thành bước 4, hệ thống chỉ xác nhận thành công khi tiến độ được lưu hợp lệ; khi A quay lại, bước 4 được khôi phục, và tài khoản khác không thể đọc dữ liệu của A.”

Nhóm **chưa** triển khai offline đa thiết bị cho toàn bộ khóa học. Nhưng **quyền truy cập, lỗi trạng thái lưu và tính đúng dữ liệu** là điều kiện tối thiểu của lát cắt, không bị cắt khỏi DoD.

### 26.4. Trước khi code: ví dụ và hợp đồng

Product Owner, tester và Developers cùng xem:

1. Phân biệt **accepted / processing / persisted / failed**.
2. Khi HTTP 202 nhưng chưa persisted, UI thể hiện gì?
3. Nếu timeout xảy ra, client có được retry an toàn?
4. Khi response đến ngược thứ tự, dữ liệu tiến độ nào hợp lệ?
5. Người học bị thu hồi quyền có còn nhìn được tiến độ qua cache?

Những câu hỏi chưa rõ có người chịu trách nhiệm làm rõ. Nhóm tạo **acceptance examples và contract tests** ở các ranh giới có rủi ro cao, trước khi viết toàn bộ UI và service.

### 26.5. Trong phát triển: test và tích hợp tăng dần

- Developers viết một phần nhỏ, có unit/component tests theo rủi ro.
- API và client cùng dựa trên **ngữ nghĩa hợp đồng** có kiểm chứng.
- CI chạy thường xuyên, không chờ cuối Sprint.
- Tester khám phá trường hợp mạng yếu ngay khi lát cắt đầu hoạt động.
- Nhóm dùng fixture an toàn; phụ thuộc staging được đưa tới người có quyền để giảm hàng đợi.
- Mọi người hỗ trợ hoàn tất hạng mục gần Done trước khi kéo thêm PBI khác.

**Chuyên gia kiểm thử vẫn thực hiện kiểm tra chuyên sâu**. Thay đổi ở đây là họ **tham gia tạo thông tin chất lượng từ đầu**, và Developers không coi công việc đã xong khi mới chuyển sang QA.

### 26.6. Sprint Review: kiểm tra Increment, không trình chiếu trạng thái giả

Nhóm chỉ giới thiệu phần thực sự **đạt DoD** như Increment đã hoàn thành, kèm điều kiện release và phản hồi người dùng hiện có. Stakeholder thử thao tác lưu/khôi phục với tài khoản mẫu và đưa thêm câu hỏi về trải nghiệm mạng yếu. Product Owner xem xét điều chỉnh Product Backlog theo giá trị và rủi ro.

Nếu một PBI chưa đạt DoD vì tích hợp thất bại, nhóm ghi **chưa Done**. Đó là minh bạch để điều chỉnh, không phải “QA khiến Sprint thất bại”.

### 26.7. Số liệu hai giai đoạn giả định

Giả sử sau vài vòng thử, nhóm có dữ liệu các lát cắt **cùng loại, cùng ranh giới đo**:

| Tín hiệu | Trước | Sau | Diễn giải thận trọng |
| --- | ---: | ---: | --- |
| Lead time từ Started tới Increment đạt DoD, điển hình minh họa | 20 ngày | 13 ngày | Có dấu hiệu giảm thời gian tới chất lượng dùng được |
| Thời gian chờ QA trong lát cắt mẫu | 5 ngày | 2 ngày | Phản hồi sớm và lô nhỏ có thể giúp giảm chờ |
| Thời gian chờ tích hợp trong lát cắt mẫu | 4 ngày | 1 ngày | Hợp đồng/fixture và hỗ trợ nền tảng có thể giúp |
| WIP trung bình | 14 PBI | 9 PBI | Ít việc dở hơn; cần xem loại việc |
| Lỗi hợp đồng được phát hiện muộn trong kỳ | 8 | 3 | Xem độ nghiêm trọng và số thay đổi |
| Lỗi hậu phát hành mức trung bình trở lên | 7 | 4 | Cần xem mức tiếp xúc người dùng |
| Sự cố hỗ trợ ngoài giờ | 5 | 3 | Có dấu hiệu tốt hơn, chưa kết luận nhân quả |

Ví dụ trước đó có **9 ngày xử lý + 11 ngày chờ = 20 ngày**. Nếu nhóm giảm chờ QA từ 5 còn 2 và chờ tích hợp từ 4 còn 1, giữ các bước khác giả định không đổi:

\[
20 - (5-2) - (4-1)=14\ \text{ngày}.
\]

Nếu đồng thời giảm thêm **1 ngày chờ bắt đầu** hoặc một nút thắt tương đương, lead time thành **13 ngày**. **Con số 13 trong bảng giả định bao gồm cải tiến bổ sung đó**, không chỉ hai thay đổi QA/tích hợp. Mọi giả định phải được ghi để tránh kể chuyện số liệu sai.

**Không thể khẳng định tất cả cải thiện do TDD, CI hay thay cấu trúc đội** chỉ từ bảng trước/sau. Có thể cùng lúc quy mô story, nhân sự, loại lỗi hoặc tần suất release thay đổi.

### 26.8. Rủi ro mới sau cải tiến

Nhóm nhận thấy số end-to-end test bắt đầu tăng nhanh, pipeline chậm và có flaky tests. Nếu tiếp tục thêm test UI cho mọi trường hợp, nhóm có thể **tái tạo hàng đợi mới ngay trong CI**.

Họ quyết định:

- Giữ end-to-end tests cho hành trình quan trọng.
- Chuyển các quy tắc ổn định có thể kiểm tra nhanh xuống lớp unit/component/contract.
- Điều tra flaky test thay vì bỏ qua.
- Duy trì exploratory testing và kiểm chứng trên môi trường phù hợp.
- Tiếp tục đo thời gian phản hồi CI và lỗi lọt hậu phát hành.

**Cải tiến Agile không kết thúc khi tìm được một công thức.** Nhóm cần kiểm tra cơ chế mới còn hữu ích khi sản phẩm và điều kiện thay đổi.

### 26.9. Bài học từ case study

1. **Định nghĩa lại Done** từ “code đã bàn giao” thành một Increment đạt chất lượng.
2. **Giảm lô** để feedback nghiệp vụ và kỹ thuật xuất hiện khi thay đổi còn nhỏ.
3. **Đưa tester vào lúc làm rõ**, không đợi giao mã.
4. **Tích hợp nhiều lần** và bảo vệ pipeline.
5. **Giải quyết rào cản ngoài team** thay vì yêu cầu nhóm “cố gắng hơn”.
6. **Đo end-to-end** và giữ các guardrail chất lượng, bảo mật, vận hành.
7. **Đánh giá theo thời gian và bối cảnh**, không ép mọi chỉ số phải đẹp ngay Sprint tiếp theo.

## 27. Một lộ trình cải tiến nhỏ theo vòng phản hồi

Không cần chờ xây “test automation platform” hoàn chỉnh mới thay đổi được anti-pattern. Nhóm có thể tiến hành **từng thử nghiệm có giả thuyết**, nhưng không phá các tiêu chuẩn chất lượng hiện hành.

### Bước 1 — Xác định công việc chưa thật sự Done

Chọn vài lát cắt có rủi ro thực, xác định:

- Điểm bắt đầu/kết thúc **lead time và cycle time**.
- Thời gian chờ QA, chờ môi trường, chờ quyết định và tích hợp.
- Definition of Done và điều kiện release liên quan.
- Các lỗi phát hiện muộn, mức nghiêm trọng, tác động tới người dùng.
- Hạng mục **đang mở nhưng đã già đi**.

Nếu trước đây nhóm chỉ ghi “dev done”, **đừng gán đó là Done theo DoD** trong báo cáo mới. Ghi lại sự thay đổi định nghĩa để so sánh không sai.

### Bước 2 — Chọn một điểm nghẽn có thể kiểm chứng

Ví dụ:

> “Nhiều story chờ QA do yêu cầu nghiệp vụ không rõ và tester chỉ xem khi backend/frontend đều code xong.”

Không chọn mục tiêu chung chung “tăng chất lượng 50%” nếu không biết chất lượng là gì, đo thế nào hoặc rủi ro nào cần ưu tiên.

### Bước 3 — Viết giả thuyết và guardrails

~~~text
GIẢ THUYẾT:
  Nếu PO, tester và Developers thống nhất acceptance examples
  trước khi code, rồi chạy contract/integration tests khi mỗi lát
  cắt còn nhỏ, thời gian chờ và số vòng sửa muộn sẽ giảm.

THAY ĐỔI:
  Thử với hai lát cắt lưu/khôi phục tiến độ.

CHỈ SỐ CHÍNH:
  Cycle time từ Started tới DoD và thời gian blocked QA/tích hợp.

CHỈ SỐ CHẨN ĐOÁN:
  Số lần sửa vì hiểu sai hợp đồng, Work Item Age,
  thời gian CI và lỗi phát hiện muộn.

GUARDRAILS:
  Lỗi mất dữ liệu, sai quyền truy cập, lỗi nghiêm trọng,
  tải on-call và giờ làm ngoài kế hoạch.

XEM LẠI:
  Sau khi đủ lát cắt hoàn thành qua workflow mới.
~~~

### Bước 4 — Thay đổi cơ chế làm việc, không chỉ công cụ

Các thử nghiệm có thể gồm:

1. **Làm rõ story với tester sớm**: Ví dụ nghiệp vụ và rủi ro trước khi triển khai.
2. **Chia lát cắt dọc**: Mỗi phần có hành vi có thể tích hợp và kiểm chứng.
3. **Duy trì CI xanh có ý nghĩa**: Kiểm tra nhanh khi thay đổi còn nhỏ.
4. **Pairing tại điểm rủi ro cao**: Developer, tester và người hiểu API xem cùng trường hợp khó.
5. **Giảm WIP**: Ưu tiên hoàn tất hạng mục đang dở thay vì mở nhiều PBI.
6. **Gỡ phụ thuộc test environment**: Xác định người có quyền cấp môi trường hoặc triển khai fixture.

Không thực hiện tất cả thay đổi cùng lúc nếu không đủ năng lực và dữ liệu để hiểu tác dụng. Tuy nhiên, một **gói nhỏ các thay đổi bổ trợ** như ví dụ nghiệp vụ + contract test + CI có thể cần đi cùng nhau mới giải quyết được một ranh giới cụ thể.

### Bước 5 — Kiểm tra trong công việc thật

- Tester có thể kiểm thử **lát cắt nhỏ đang hoạt động** chứ không nhận lô lớn không?
- Developers có xử lý lỗi và ý kiến ngay trong workflow không?
- Bảng công việc có giữ card đang chờ QA/tích hợp trong WIP không?
- Các test mới có thực sự phát hiện lỗi hay chỉ chạy xanh?
- Product Owner có hiểu phần Increment nào đã đạt DoD không?
- Có ai đang phải làm ngoài giờ để duy trì cải tiến không?

### Bước 6 — Tổng kết có điều kiện

| Kết quả | Quyết định có thể phù hợp |
| --- | --- |
| Flow cải thiện, lỗi không tăng, guardrails đạt | Duy trì và mở rộng có điều kiện |
| Flow chưa cải thiện nhưng lỗi tích hợp được phát hiện sớm hơn | Giữ phần có ích, điều tra nút thắt mới |
| Pipeline chậm/flaky nghiêm trọng | Sửa chiến lược test và dữ liệu, không bỏ kiểm tra an toàn |
| Outcome người dùng chưa thay đổi | Kiểm tra exposure, giải pháp sản phẩm và cửa sổ đo |
| Lỗi dữ liệu nghiêm trọng tăng | Dừng/thu hẹp thay đổi rủi ro theo quy trình, khắc phục trước |
| QA vẫn chờ vì chính sách ngoài nhóm | Đưa rào cản tới người có quyền, không đổ lỗi tester |
| Dữ liệu quá ít hoặc không tương đương | Ghi “chưa đủ bằng chứng”, tiếp tục quan sát có giới hạn |

### Bước 7 — Đưa học hỏi vào cách vận hành thường ngày

Một thay đổi có ích cần có **chính sách hoặc cách làm được mọi người hiểu**, người duy trì, khả năng hỗ trợ thành viên mới và mốc xem lại. Không nên chỉ thực hiện “test sớm” trong tháng có coach đến, rồi quay về handoff cuối kỳ ngay khi chương trình kết thúc.

## 28. Những giải pháp tưởng đúng nhưng dễ tạo sai lầm mới

### 28.1. “Tuyển thêm tester là đủ”

Nếu hàng đợi bắt nguồn từ **yêu cầu mơ hồ, hợp đồng sai và lô code lớn**, thêm người test có thể tăng năng lực phát hiện nhưng không giải quyết **nguyên nhân tạo lỗi**. Có trường hợp cần bổ sung chuyên môn kiểm thử thật; nên quyết định dựa trên **loại rủi ro, thời gian chờ và năng lực thực**, không mặc định tăng hoặc cắt nhân sự.

### 28.2. “Tự động hóa 100% kiểm thử”

Không phải mọi kiểm chứng đều tự động hóa được hoặc đáng tự động hóa. Một hệ kiểm thử UI quá lớn có thể gây **flaky test, thời gian chạy chậm và chi phí bảo trì**. Dùng chiến lược nhiều lớp và giữ hoạt động khám phá, usability, đánh giá an toàn phù hợp.

### 28.3. “Dev tự test hết, không cần tester”

Chất lượng chung không làm biến mất chuyên môn kiểm thử. Một tester có thể giúp phát hiện giả định không được Developer nhìn thấy, đánh giá rủi ro và thiết kế thử nghiệm khó. Loại bỏ tiếng nói độc lập có thể **làm giảm độ sâu kiểm chứng**, đặc biệt ở sản phẩm rủi ro cao.

### 28.4. “QA phải sign-off mọi thay đổi ở phút cuối”

Một kiểm soát độc lập có lý do có thể cần thiết, nhưng **không nên biến người ký thành nơi đầu tiên nhìn thấy tính năng**. Mời người kiểm tra và tiêu chuẩn vào sớm, tạo bằng chứng dần, phân loại rủi ro và minh bạch ai có quyền cho phép phát hành.

### 28.5. “CI xanh thì đóng story”

CI chỉ kiểm tra những điều đã thiết kế và chạy được. Story có thể thiếu acceptance criteria, kiểm thử phân quyền hoặc kiểm chứng dữ liệu thực. **DoD và khả năng sử dụng Increment** mới là ranh giới chất lượng cần xét trong Scrum.

### 28.6. “Để bug ở Sprint sau cho đẹp burndown”

Nếu lỗi làm story **không đáp ứng DoD**, không nên báo story Done rồi tạo bug để dời rủi ro. Với lỗi được phát hiện **sau khi Increment đã đạt DoD**, Product Owner và Developers đánh giá mức nghiêm trọng, ảnh hưởng, ưu tiên và hành động phù hợp; không có quy tắc “mọi bug chỉ thuộc Sprint sau” khi đang có incident nghiêm trọng.

### 28.7. “Mọi thứ phải release ngay khi pass unit tests”

Agile không có nghĩa bỏ an toàn. Release cần đáp ứng các kiểm soát liên quan **dữ liệu, khả năng phục hồi, độ tin cậy, tương thích và quyền truy cập**. Có thể phát hành tăng dần, nhưng chọn mức kiểm tra theo rủi ro.

### 28.8. “Đóng hết trạng thái Waiting là cải tiến”

Nếu nhóm xóa cột “Waiting for QA” nhưng công việc vẫn đợi trong inbox hoặc ngoài bảng, flow metrics sẽ đẹp giả. Cần **giảm thời gian chờ thật** và giữ ranh giới Started/Done nhất quán.

### 28.9. “Bắt QA tham gia mọi cuộc họp”

Không phải mọi cuộc họp đều tạo thêm chất lượng. Cần đúng người trong **những đối thoại rủi ro cao**, tài liệu ví dụ rõ và đường tiếp cận thông tin; không tiêu tốn toàn bộ thời gian tester vào status meeting.

### 28.10. “Chờ tích hợp đủ tất cả story mới thử”

Tích hợp nhiều thay đổi lớn cùng lúc khó xác định nguyên nhân và có thể kéo dài sửa lỗi. Hãy kiểm chứng **một lát cắt dọc đã đủ điều kiện**, dùng contract tests, CI và môi trường phù hợp.

### 28.11. “Mọi lỗi QA là trách nhiệm QA”

Tester phát hiện lỗi **không làm tester trở thành tác giả của lỗi**. Chất lượng là thuộc tính của sản phẩm và hệ thống làm việc; trách nhiệm khắc phục cần được xử lý theo kỹ năng, quyền và mức rủi ro, không theo người báo tin.

### 28.12. “Đặt WIP limit rồi tự nhiên nhanh”

WIP limit giúp nhìn và điều phối công việc, nhưng không sửa **hợp đồng mơ hồ, thiếu test data hoặc môi trường quá khan hiếm**. Cần kết hợp phát hiện nút thắt và thử cải tiến nguyên nhân.

### 28.13. “Chỉ shift-left; production không cần theo dõi”

Người dùng thật có điều kiện mạng, tải, dữ liệu và hành vi không tái hiện hoàn toàn ở test. **Shift-right** giúp quan sát và mang bài học trở lại quy trình phát triển; nó không thay guardrails trước release.

### 28.14. “Một test pass chứng minh mọi biến thể”

Một scenario khôi phục thành công không chứng minh logic retry, permission, concurrent updates và backup/restore. Phải có **mô hình rủi ro và lớp test phù hợp**, không cố chạy nhiều lần cùng một kịch bản để thay độ bao phủ hành vi.

### 28.15. “Mỗi team xong task là sản phẩm Done”

Khi nhiều Scrum Team cùng phát triển một sản phẩm, họ cần **Increment tích hợp và DoD chung**. Hoàn thành từng lớp nhưng chưa thể dùng là **đầu ra cục bộ**, không phải giá trị end-to-end.

### 28.16. “Nếu test phát hiện lỗi sớm thì số bug phải luôn giảm”

Số bug ghi nhận có thể **tăng ngắn hạn** khi nhóm phát hiện/ghi chép trung thực hơn. Cần xem mức nghiêm trọng, thời điểm phát hiện, độ tin cậy và tác động người dùng, không kết luận chất lượng xấu chỉ từ tổng bug.

### 28.17. “Tạo đội tích hợp trung tâm để nhóm khác được tập trung code”

Năng lực tích hợp chuyên môn có thể hữu ích, nhưng một **đội tiếp nhận mọi thứ vào cuối kỳ** có nguy cơ tạo hàng đợi và trách nhiệm không rõ. Hãy tối ưu **sự hợp tác và khả năng tự kiểm chứng của các nhóm nguồn**, dùng chuyên gia hỗ trợ và giữ kiểm soát độc lập cần thiết.

## 29. Bài thực hành: chuyển kiểm thử muộn thành phản hồi liên tục

Tất cả số liệu và bối cảnh dưới đây đều **giả định**. Khi trả lời, hãy nêu **mục đích kiểm chứng, trách nhiệm, ranh giới Done, điều kiện an toàn và dấu hiệu học hỏi**. Không có một test pyramid hay công cụ CI bắt buộc cho mọi sản phẩm.

### Bài 1 — Phát hiện Done giả

Một Scrum Team báo 10 PBI hoàn thành. Trong đó:

- 4 PBI đã qua unit/contract/integration tests, đáp ứng toàn bộ DoD.
- 3 PBI mới merge mã, đang chờ tester xác minh hành vi quan trọng.
- 2 PBI kiểm thử chức năng đạt nhưng chưa kiểm chứng quyền truy cập là một phần DoD.
- 1 PBI chưa tích hợp được do thiếu dữ liệu thử.

**Yêu cầu:**

1. Có thể tính bao nhiêu PBI đã Done theo DoD nêu trên?
2. Vì sao “code completed” khác Increment đạt DoD?
3. Nên báo trạng thái những PBI còn lại thế nào trong Sprint Review?
4. Nêu một hành động trong Sprint tiếp theo để tránh tái diễn.

**Đáp án tham khảo:** **4 PBI** đáp ứng điều kiện đã cho. **6 PBI** còn lại không được báo Done theo DoD hiện hành. Cần minh bạch công việc chưa hoàn thành và tiếp tục xử lý theo Product Backlog, đồng thời đưa kiểm chứng vào workflow sớm hơn.

### Bài 2 — Tính thời gian chờ và flow efficiency

Một lát cắt có:

- Làm rõ: **1 ngày xử lý**.
- Chờ bắt đầu: **2 ngày**.
- Phát triển: **3 ngày xử lý**.
- Chờ QA: **5 ngày**.
- Kiểm thử: **2 ngày xử lý**.
- Chờ tích hợp: **4 ngày**.
- Tích hợp/sửa: **2 ngày xử lý**.
- Kiểm chứng phát hành: **1 ngày xử lý**.

**Yêu cầu:**

1. Tính tổng xử lý, tổng chờ và end-to-end lead time theo giả định tuần tự cùng đơn vị ngày lịch.
2. Tính tỷ lệ thời gian xử lý/tổng thời gian.
3. Nếu chỉ tối ưu thời gian phát triển giảm từ 3 còn 2 ngày, lead time mới?
4. Nếu thay vào đó giảm chờ QA từ 5 xuống 2 ngày và chờ tích hợp từ 4 xuống 1 ngày, lead time mới?
5. Vì sao không thể dùng tỷ lệ thời gian chờ để nói tester hoặc Developer “nhàn rỗi”?

**Đáp án tham khảo:** Xử lý **9 ngày**, chờ **11 ngày**, tổng **20 ngày**, flow efficiency **45%**. Chỉ giảm code → **19 ngày**. Giảm hai hàng đợi (3 + 3 ngày) → **14 ngày**, nếu những điều kiện khác không đổi. Đây là số đo hạng mục, không phải đo công sức của cá nhân.

### Bài 3 — Viết acceptance examples trước khi code

Product Owner nói: “Học viên quay lại đúng tiến độ đã lưu.” Backend nói “trả HTTP 202 là thành công”; frontend muốn hiện “Đã lưu”.

**Nhiệm vụ:**

- Nêu **hai cách hiểu** về từ “thành công”.
- Viết ít nhất ba scenario **Given–When–Then** cho xác nhận lưu, timeout và phân quyền.
- Xác định câu hỏi nào cần Product Owner/người hiểu nghiệp vụ làm rõ.
- Xác định câu hỏi kỹ thuật nào Developers cần thống nhất hợp đồng.
- Chọn ít nhất một scenario nên tự động hóa ở **lớp component/contract** và một scenario cần **kiểm chứng tích hợp**.

**Tiêu chí:** Không chỉ kiểm tra HTTP status; phải kiểm chứng **ý nghĩa trạng thái và dữ liệu**.

### Bài 4 — Thiết kế test strategy không quá phụ thuộc UI

Một nhóm có 300 UI tests chạy 90 phút, thường xuyên flaky. Họ gần như không có test cho API contract và quyền tài khoản.

**Yêu cầu:**

1. Những rủi ro nào đang bị kiểm chứng sai lớp?
2. Chọn ba quy tắc nên kiểm tra ở **unit/component/contract**.
3. Chọn hai hành trình end-to-end vẫn nên giữ.
4. Những trường hợp nào cần exploratory testing?
5. Thiết kế tín hiệu để biết pipeline **thật sự đáng tin hơn**, không chỉ ngắn hơn.

**Gợi ý:** Không xóa 290 tests chỉ để có màu xanh. Trước hết phân tích giá trị từng nhóm kiểm thử, chuyển lớp phù hợp, sửa flaky và giữ guardrails.

### Bài 5 — TDD: Red–Green–Refactor

Yêu cầu: Giao diện không được hiện “Đã lưu thành công” khi trạng thái trả về chỉ là **ACCEPTED**.

**Nhiệm vụ:**

- Viết một test nhỏ thể hiện hành vi chưa có.
- Nêu cách xác nhận **Red fail đúng lý do**.
- Viết mô tả hiện thực tối thiểu để test xanh.
- Nêu một refactoring không thay hành vi.
- Chỉ ra **hai loại rủi ro** test này chưa chứng minh và lớp test bổ sung.

**Gợi ý:** Test presenter đơn vị chưa chứng minh **persisted thật** hoặc **đúng quyền tài khoản**.

### Bài 6 — Thiết kế hợp đồng producer/consumer

Service trả:

~~~json
{"status":"accepted","requestId":"r-42"}
~~~

Frontend hiểu accepted = saved, backend hiểu accepted = queued.

**Yêu cầu:**

1. Mô tả lỗi ngữ nghĩa dù JSON hợp schema.
2. Đề xuất một contract có **pending/confirmed/failed** rõ ý nghĩa.
3. Định nghĩa những điều cần làm khi timeout, retry và response đến muộn.
4. Nêu một contract test và một integration test bổ trợ.
5. Chỉ ra ai cần tham gia quyết định khi quy tắc ảnh hưởng trực tiếp trải nghiệm người học.

### Bài 7 — Thiết kế một pipeline CI có giá trị

Nhóm đang merge nhánh vào ngày cuối Sprint rồi chạy build thủ công.

**Hãy lập kế hoạch ba bước cải thiện:**

1. Đưa những kiểm tra nào vào **mỗi thay đổi nhỏ**?
2. Những kiểm tra nào chạy ở **trạng thái tích hợp**?
3. Những kiểm tra rủi ro nào cần **trước/khi release**?
4. Khi pipeline đỏ hoặc flaky, nhóm nên làm gì?
5. Định nghĩa điều kiện để có thể nói **đã thực hành CI** thay vì chỉ có một server CI.

### Bài 8 — Quyết định khi môi trường tích hợp khan hiếm

Ba nhóm cùng chờ một staging environment. Hàng đợi trung bình bốn ngày và môi trường thường bị hỏng dữ liệu mẫu.

**Yêu cầu:**

- Phân loại vấn đề **hợp đồng, môi trường, dữ liệu**.
- Đề xuất fixture/mock/contract test có thể giúp giảm nhu cầu đợi staging.
- Nêu kiểm tra nào **vẫn cần chạy với thành phần thật**.
- Nêu cách bảo vệ dữ liệu học viên trong môi trường thử.
- Xác định một rào cản nhóm không tự tháo và người có quyền hỗ trợ.

**Tiêu chí:** Không đề xuất “dùng luôn dữ liệu sản xuất, sao chép đầy đủ về máy” để tiết kiệm thời gian nếu không có quyền/phương án bảo vệ phù hợp.

### Bài 9 — Kiểm thử phi chức năng từ đầu lát cắt

Một tính năng học trực tuyến hoạt động với một người dùng nhưng lỗi khi mạng yếu, chịu tải và tài khoản khác truy cập URL cũ.

**Nhiệm vụ:** Lập ma trận gồm:

| Rủi ro | Điều kiện mong đợi | Kiểm tra sớm | Kiểm tra tích hợp/vận hành |
| --- | --- | --- | --- |
| Mạng yếu | ... | ... | ... |
| Tải tăng | ... | ... | ... |
| Truy cập trái phép | ... | ... | ... |
| Dữ liệu bị ghi trùng | ... | ... | ... |
| Thiết bị không hỗ trợ chuột | ... | ... | ... |

**Điểm đánh giá:** Không coi bảo mật hoặc dữ liệu là “tính năng để Sprint sau” nếu nó là điều kiện an toàn của lát cắt hiện tại.

### Bài 10 — Đọc flow metrics cùng công việc chưa hoàn tất

Năm lát cắt Done có cycle time **4, 5, 6, 7, 18 ngày**. Hai hạng mục khác đang mở lần lượt **20 và 23 ngày**, chưa Done.

**Yêu cầu:**

- Tính mean và median của những lát cắt đã Done.
- Những hạng mục đang mở có được cộng trực tiếp vào cycle time Done không?
- Cần dùng phép đo nào để thấy chúng đang già đi?
- Nêu một hành động giúp hoàn tất thay vì mở thêm việc.
- Vì sao việc đổi Started từ “bắt đầu làm” thành “bắt đầu code” có thể khiến con số đẹp giả?

**Đáp án tham khảo:** Mean **8 ngày**, median **6 ngày**. Hai hạng mục chưa Done cần **Work Item Age**; không thể giả định chúng sẽ hoàn thành theo trung bình trong khi đang bị chặn.

### Bài 11 — Little's Law cho toàn workflow

Trong điều kiện hệ thống giả định gần ổn định:

- WIP trung bình **15 lát cắt**.
- Throughput trung bình **3 lát cắt/tuần**.

**Yêu cầu:**

1. Cycle time trung bình tương ứng?
2. Nếu WIP còn 9 và throughput **vẫn đúng 3/tuần**, cycle time tương ứng?
3. Nêu ít nhất ba điều kiện sử dụng phép tính.
4. Vì sao “đặt WIP limit = 9” không bảo đảm mọi lát cắt xong trong ba tuần?

**Đáp án tham khảo:** **5 tuần** và **3 tuần** theo điều kiện thống kê; không dùng để hứa thời gian một hạng mục cụ thể.

### Bài 12 — Scrum Planning và DoD khi QA tách nhóm

Một Sprint dài hai tuần. PO đã ưu tiên 12 PBI; QA chỉ có thể nhận công việc vào hai ngày cuối. Không có ai chịu trách nhiệm test automation.

**Thiết kế lại Sprint Planning**:

- Sprint Goal có giá trị người dùng là gì?
- Phạm vi nào có thể **đáp ứng DoD thật** với năng lực hiện tại?
- Những kỹ năng kiểm thử cần nằm ở đâu và ai hỗ trợ sớm?
- Những phụ thuộc nào cần lãnh đạo/nền tảng hỗ trợ?
- Công việc nào không nên chọn chỉ để “đủ velocity”?

**Gợi ý:** Không cam kết 12 PBI rồi báo Done giả. Chọn phạm vi có thể tạo Increment có giá trị; làm rõ cách thực hiện kiểm thử trước khi Sprint bắt đầu và thích ứng khi có thông tin mới.

### Bài 13 — Phân tích một lỗi lọt hậu phát hành

Người dùng báo tính năng lưu tiến độ đôi khi hiển thị thành công nhưng khi quay lại vị trí bị mất.

**Hãy xây một luồng xử lý**:

1. Xác định mức nghiêm trọng và bảo vệ người dùng.
2. Thu thập bằng chứng tái hiện mà không lộ dữ liệu riêng tư.
3. Đặt câu hỏi về hợp đồng accepted/persisted, retry, CI và test tích hợp.
4. Viết điều kiện kiểm chứng sửa lỗi, gồm một test hồi quy phù hợp.
5. Xem lại **điều gì cần đổi trong quy trình** để lỗi tương tự được phát hiện sớm.

**Tiêu chí:** Không kết luận “QA có lỗi vì không tìm thấy” trước khi điều tra hệ thống.

### Bài 14 — Thử nghiệm cải tiến trong hai Sprint

Nhóm có hàng đợi QA 5 ngày, chờ tích hợp 4 ngày, nhiều PBI chưa đạt DoD.

~~~text
VẤN ĐỀ:
  ...

BASELINE:
  ...

GIẢ THUYẾT:
  Nếu làm rõ acceptance examples và contract sớm,
  tích hợp thường xuyên và giảm WIP,
  thì thời gian chờ kiểm chứng sẽ giảm.

THỬ NGHIỆM:
  ...

TÍN HIỆU:
  Cycle time, Work Item Age, blocked time,
  lỗi hợp đồng, test stability, throughput đạt DoD.

GUARDRAILS:
  Lỗi dữ liệu, quyền truy cập, sự cố nghiêm trọng,
  việc ngoài giờ và nhịp bền vững.

XEM LẠI:
  ...
~~~

**Yêu cầu:** Điền các chỗ trống, xác định người có thẩm quyền, và mô tả quyết định **giữ/sửa/dừng** theo ít nhất hai kết quả khác nhau. Không được chỉ dùng số test đã viết để chứng minh thành công.

### Bài 15 — Xử lý tranh luận giữa Developer và tester

Một Developer nói “QA đang chặn release”, tester phản hồi “Tôi vừa tìm thấy lỗi phân quyền nghiêm trọng”. Product Owner muốn có demo cho stakeholder ngày mai.

**Yêu cầu:**

- Phân biệt **người phát hiện lỗi** và **nguồn gốc rủi ro**.
- Nêu bước xử lý an toàn ngay cho lỗi phân quyền.
- Đề xuất cách trao đổi Product Owner–Developers–tester phù hợp trách nhiệm.
- Nêu phần nào **không thể trình bày là Increment hoàn tất** nếu chưa đạt DoD.
- Đề xuất một thay đổi quy trình để rủi ro tương tự được phát hiện sớm hơn.

**Điểm đánh giá:** Không đổ lỗi tester, không ép bỏ kiểm soát để “kịp Review”, đồng thời vẫn nêu cách giữ minh bạch với stakeholder.

### Bài 16 — Phân biệt shift-left với shift-right

Nhóm đề xuất:

1. Viết acceptance examples trước phát triển.
2. Chạy unit/contract/integration tests khi thay đổi nhỏ.
3. Bỏ kiểm tra bảo mật trước phát hành vì đã có log production.
4. Phát hành có kiểm soát rồi theo dõi SLI, lỗi và trải nghiệm.
5. Sau incident, tạo kiểm thử hồi quy và chỉnh DoD khi cần.

**Nhiệm vụ:** Phân loại hoạt động shift-left, shift-right và **đề xuất không an toàn**. Giải thích vì sao phát hiện trong production là nguồn học nhưng không thể thay yêu cầu chất lượng bắt buộc trước đó.

### Bài 17 — Kiểm tra số liệu trước/sau không suy luận quá mức

Sau ba Sprint thay đổi workflow:

- Lead time điển hình của lát cắt tương tự **20 → 13 ngày**.
- Lỗi tích hợp phát hiện muộn **8 → 3**.
- Tỷ lệ người học khôi phục thành công **62% → 68%**.
- Có một chiến dịch nhắc học mới diễn ra cùng giai đoạn.

**Yêu cầu:**

1. Lead time giảm bao nhiêu ngày và phần trăm tương đối?
2. Outcome tăng bao nhiêu **điểm phần trăm**?
3. Có thể khẳng định CI làm outcome tăng không? Vì sao?
4. Những giới hạn mẫu, ranh giới dữ liệu và exposure cần kiểm tra?
5. Guardrail nào buộc nhóm dừng/thu hẹp thay đổi dù số chính cải thiện?

**Đáp án tham khảo:** Lead time giảm **7 ngày**, tương đối **35%** theo mốc 20; outcome tăng **6 điểm phần trăm**. Chưa có căn cứ quy kết mọi thay đổi cho CI vì nhiều yếu tố đồng thời, đặc biệt chiến dịch nhắc học.

### Bài 18 — Đánh giá một handoff bắt buộc có hợp lý không

Một phần mềm xử lý dữ liệu nhạy cảm cần **kiểm tra độc lập trước khi release** theo chính sách. Nhóm đề xuất bỏ toàn bộ bước đó vì “Agile không có phase”.

**Nhiệm vụ:**

- Nêu vì sao đề xuất trên có thể sai và rủi ro thế nào.
- Phân biệt phần **chuyên môn độc lập bắt buộc** với việc **phát hiện yêu cầu quá muộn**.
- Đề xuất cách đưa tiêu chí/kiểm tra vào đầu quá trình, tự động hóa những kiểm tra có thể.
- Thiết kế thời điểm phối hợp và bằng chứng để không xếp hàng toàn bộ việc đến ngày cuối.
- Nêu ai có quyền quyết định thay đổi chính sách.

**Gợi ý:** Agile không yêu cầu bỏ kiểm soát cần thiết; nó khuyến khích **tạo phản hồi sớm, giữ trách nhiệm rõ và giảm lãng phí không tạo an toàn**.

## 30. Checklist tránh dồn kiểm thử và tích hợp sang cuối kỳ

### A. Mục tiêu và Definition of Done

- [ ] Product Goal hoặc vấn đề người dùng **được hiểu rõ** trước khi chia công việc.
- [ ] Product Backlog Item đủ bối cảnh và có **ví dụ chấp nhận** cho hành vi quan trọng.
- [ ] Nhóm phân biệt **code completed, integrated, DoD, deployed, released và outcome**.
- [ ] Definition of Done bảo vệ **tính đúng nghiệp vụ, tích hợp và tiêu chuẩn chất lượng liên quan**.
- [ ] PBI **chưa đạt DoD không được báo Done**, dù mã đã merge và tester sắp kiểm.
- [ ] Nếu nhiều Scrum Team cùng một sản phẩm, họ dùng **DoD chung** theo Scrum.
- [ ] Điều kiện release hoặc chứng nhận độc lập được **minh bạch từ sớm**, không bị phát hiện phút cuối.
- [ ] Không sử dụng **Sprint Review như cổng duy nhất để kiểm thử hoặc phát hành**.

### B. Làm rõ và thiết kế lát cắt

- [ ] Những người hiểu nghiệp vụ, Developers và tester có **cơ hội đặt câu hỏi trước khi code quá nhiều**.
- [ ] Các ví dụ chính phân biệt rõ **accepted, processing, persisted và failed** khi liên quan.
- [ ] Có câu hỏi về **dữ liệu, quyền truy cập, lỗi mạng, retry và tính tương thích**.
- [ ] Hạng mục được chia thành **lát cắt có hành vi kiểm chứng được**, không chỉ theo tầng kỹ thuật.
- [ ] Mỗi lát cắt nhỏ vẫn tuân thủ **bảo mật và tính đúng dữ liệu tối thiểu**.
- [ ] Chưa mở rộng kiến trúc/khả năng chưa cần nếu không có nhu cầu hoặc rủi ro xác nhận.
- [ ] Các câu hỏi chưa rõ có **người và thời điểm giải quyết**, không âm thầm giả định.

### C. Kiểm thử trong quá trình phát triển

- [ ] Tester/chuyên gia chất lượng không chỉ nhận **đợt lớn sau khi code xong**.
- [ ] Developers chịu trách nhiệm **tạo Increment đáp ứng DoD**, không chỉ chuyển sang QA.
- [ ] Có kiểm tra tự động **nhanh, đáng tin** cho quy tắc quan trọng khi thay đổi nhỏ.
- [ ] TDD/BDD được chọn **theo giá trị và loại hành vi**, không chỉ để tăng số test.
- [ ] Unit/component tests bảo vệ quy tắc cục bộ; contract/integration tests bảo vệ **ranh giới thật**.
- [ ] Các hành trình end-to-end quan trọng được kiểm tra, nhưng **không nhân số UI tests vô hạn**.
- [ ] Có **exploratory testing** để phát hiện giả định chưa được automation nêu ra.
- [ ] Kiểm thử bảo mật, dữ liệu, hiệu năng, độ tin cậy và khả năng tiếp cận được xem **theo rủi ro từ sớm**.
- [ ] Flaky tests được điều tra; không âm thầm bỏ kiểm tra chỉ để pipeline xanh.

### D. Tích hợp và môi trường

- [ ] Các thay đổi được **tích hợp thường xuyên** và kiểm tra khi còn nhỏ.
- [ ] CI có build/test có ý nghĩa; pipeline đỏ được **phản ứng phù hợp**, không dồn tới cuối Sprint.
- [ ] Contract API có **ngữ nghĩa và tình huống lỗi** rõ, không chỉ schema.
- [ ] Có chính sách versioning/migration khi client, server hoặc dữ liệu chạy nhiều phiên bản.
- [ ] Test doubles/fixture **không tự thay thế kiểm chứng với thành phần thật**.
- [ ] Môi trường thử và dữ liệu mẫu an toàn có khả năng **tái tạo, truy cập và hỗ trợ phù hợp**.
- [ ] Hàng đợi QA/tích hợp được nhìn thấy bằng **WIP, Work Item Age và blocked status**.
- [ ] Không tính Done cục bộ của các nhóm như **Increment end-to-end đã xong**.
- [ ] Người có quyền về môi trường/nền tảng/phê duyệt có **đường xử lý blocker thật**.

### E. Phát hành, vận hành và phản hồi

- [ ] Deployment, release/exposure và outcome được **đo riêng đúng ranh giới**.
- [ ] Các guardrail về **dữ liệu, phân quyền, độ tin cậy và an toàn** không bị bỏ vì mục tiêu tốc độ.
- [ ] Feature flag hoặc canary có **điều kiện dừng và rủi ro đã xác định**, không bị coi là sửa được mọi lỗi.
- [ ] Monitoring/SLI và phản hồi support giúp phát hiện hành vi không thấy ở môi trường test.
- [ ] Sự cố nghiêm trọng được **xử lý ngay theo quy trình phù hợp**, không chờ Sprint tiếp theo.
- [ ] Bài học lỗi sau phát hành được chuyển thành **test hoặc cải tiến quy trình** nếu có ích.
- [ ] Tester, Developers và vận hành cùng chia sẻ **thông tin chất lượng**, không đổ lỗi cho người báo lỗi.

### F. Đo lường và cải tiến liên tục

- [ ] Cycle time, lead time, throughput và WIP có **đơn vị, ranh giới và cách đếm thống nhất**.
- [ ] Công việc **đang mở và già đi** không biến mất khỏi báo cáo chỉ vì chưa Done.
- [ ] Thời gian chờ QA/tích hợp và lỗi phát hiện muộn được xem **theo cơ chế**, không làm KPI phạt nhóm.
- [ ] Xem phân phối, độ biến thiên và việc khó, **không chỉ một trung bình**.
- [ ] So sánh trước/sau có ghi **loại công việc, thay đổi cách đo và yếu tố khác cùng lúc**.
- [ ] Có **baseline, giả thuyết, thay đổi, guardrail và mốc xem lại** cho cải tiến.
- [ ] Khi flow tốt hơn nhưng lỗi dữ liệu tăng, tổ chức **không tuyên bố thành công**.
- [ ] Không dùng **velocity, số bug từng người, commit, phút online** làm bảng xếp hạng năng suất.
- [ ] Tải on-call, làm ngoài giờ và khả năng tập trung được xem ở **mức hệ thống**.
- [ ] Cải tiến hữu ích được **duy trì trong công việc thường ngày**, không chỉ lúc có chương trình Agile.

## 31. Câu hỏi ôn tập

1. Vì sao “dev done, QA pending” có thể là dấu hiệu một PBI chưa thật sự Done?
2. Làm thế nào phân biệt **lỗi được phát hiện muộn** với lỗi “do QA gây ra”?
3. Phản hồi muộn làm tăng chuyển ngữ cảnh và làm lại qua những cơ chế nào?
4. Vì sao một Sprint ngắn chưa chắc đồng nghĩa vòng phản hồi kỹ thuật ngắn?
5. Testing, quality assurance, verification và validation khác nhau ra sao?
6. Mã đã merge, tích hợp kỹ thuật và Increment đáp ứng DoD khác nhau thế nào?
7. Definition of Done có vai trò gì trong Scrum?
8. Một PBI chưa đạt DoD có được coi là một phần Increment hoàn tất không?
9. Sprint Review có phải cổng bắt buộc để release Increment không?
10. Scrum Team có thể có tester chuyên môn không, và accountability của họ được hiểu thế nào?
11. Vì sao trách nhiệm chất lượng chung không đồng nghĩa loại bỏ tester?
12. Điều gì làm handoff giữa Developers và QA trở thành “ném qua tường”?
13. Trong ví dụ 9 ngày xử lý và 11 ngày chờ, tổng lead time và flow efficiency là bao nhiêu?
14. Tại sao flow efficiency không được dùng để kết luận số giờ làm việc của từng người?
15. Nếu chỉ giảm một ngày code nhưng giữ mọi hàng đợi, tác động tới lead time có thể ra sao?
16. Chia PBI theo lớp backend/frontend khác chia lát cắt dọc có giá trị ở điểm nào?
17. Vì sao một lát cắt nhỏ vẫn phải đáp ứng quyền truy cập và tính đúng dữ liệu?
18. Example Mapping giúp phát hiện những loại câu hỏi nào trước khi code?
19. Given–When–Then tạo ra lợi ích gì, và khi nào nó không đủ để chứng minh tính đúng?
20. TDD Red–Green–Refactor diễn ra như thế nào?
21. Vì sao một unit test presenter đúng chưa chứng minh dữ liệu đã lưu bền vững?
22. BDD và kiểm thử chấp nhận hỗ trợ hội thoại nghiệp vụ thế nào?
23. CI là thực hành gì, khác với chỉ có một CI server ra sao?
24. Nhánh mã sống nhiều ngày làm tăng rủi ro tích hợp cuối kỳ vì sao?
25. Vì sao CI xanh không tự động có nghĩa tính năng đã đủ điều kiện release?
26. Unit, component, contract, integration và end-to-end tests trả lời các câu hỏi khác nhau thế nào?
27. Tại sao test pyramid không nên biến thành tỷ lệ bắt buộc cho mọi hệ thống?
28. Khi nào UI test quá nhiều làm vòng phản hồi chậm và flaky?
29. Vì sao hợp đồng JSON đúng schema vẫn có thể sai ngữ nghĩa nghiệp vụ?
30. Các trạng thái accepted, processing, persisted và failed phải được định nghĩa thế nào để client không hiểu nhầm?
31. Contract tests có thể và không thể chứng minh điều gì?
32. Môi trường tích hợp dùng chung có thể tạo hàng đợi ra sao?
33. Test doubles và fixture giúp gì, và vì sao không thay kiểm chứng với thành phần thật?
34. Khi nào exploratory testing đặc biệt hữu ích?
35. Vì sao hiệu năng, bảo mật, dữ liệu và khả năng tiếp cận không nên đợi cuối Sprint mới được xem xét?
36. Shift-left và shift-right có bổ sung nhau không? Bằng cách nào?
37. Continuous Delivery và Continuous Deployment khác nhau ở đâu?
38. Deployment, release/exposure và outcome khác nhau như thế nào?
39. Vì sao tắt feature flag không tự khôi phục dữ liệu đã ghi sai?
40. Khi phát hiện lỗi phân quyền nghiêm trọng, nhóm cần làm gì thay vì đợi buổi triage kế tiếp?
41. Scrum Planning, Daily Scrum, Review và Retrospective hỗ trợ phản hồi chất lượng theo mục đích nào?
42. Kanban giúp nhìn thấy hàng đợi QA và tích hợp bằng những phép đo nào?
43. Work Item Age khác cycle time của những hạng mục đã Done ở điểm nào?
44. SLE là kỳ vọng kiểu gì, và tại sao không phải lời hứa cho từng story?
45. Little's Law nói gì và cần những điều kiện đo nào để diễn giải đúng?
46. Khi nhiều nhóm cùng một sản phẩm, Product Goal, Product Backlog, Product Owner và DoD cần được phối hợp ra sao?
47. Vì sao thêm một đội tích hợp chuyên trách ở cuối chuỗi có thể tạo nút thắt mới?
48. Những loại rào cản tổ chức nào khiến team không thể tự kiểm thử và tích hợp sớm?
49. Trong case study, việc accepted khác persisted đã gây ra rủi ro gì?
50. Tại sao cải tiến về CI có thể dẫn tới nhu cầu tiếp tục cải thiện chiến lược kiểm thử?
51. Trong ví dụ giảm chờ QA và tích hợp, vì sao lead time 13 ngày cần thêm một giả định giảm một ngày chờ khác?
52. Nếu flow tốt hơn nhưng lỗi sau phát hành tăng, đội nên quyết định thế nào?
53. Vì sao lỗi được báo cáo tăng đôi khi lại phản ánh khả năng phát hiện tốt hơn?
54. Những điều kiện nào cho thấy kiểm chứng độc lập là yêu cầu hợp lý chứ không phải phản mẫu?
55. Những tín hiệu nào giúp kết luận nhóm **đã thực sự chuyển từ kiểm thử/tích hợp cuối kỳ sang tạo Increment chất lượng liên tục**?

**Ghi nhớ:** **Agile không xem kiểm thử và tích hợp là phần việc được “bàn giao sau khi phát triển xong”.** Một lát cắt chỉ tạo Increment đáng tin cậy khi **hành vi, hợp đồng, dữ liệu, bảo mật và những tiêu chuẩn chất lượng liên quan được kiểm chứng đủ theo Definition of Done**. Hãy đưa người có chuyên môn kiểm thử vào lúc làm rõ yêu cầu, chia công việc theo hành vi có giá trị, phát triển và tích hợp thay đổi nhỏ với CI, chọn lớp test phù hợp, khám phá rủi ro liên tục và quan sát sản phẩm sau phát hành. **Chất lượng là trách nhiệm chung nhưng vẫn cần chuyên môn sâu và kiểm soát độc lập khi có lý do.** Dùng WIP, Work Item Age, thời gian chờ, cycle time, lỗi lọt và phản hồi người dùng để cải tiến nguyên nhân hệ thống, không quy lỗi cho người phát hiện vấn đề. Thành công không phải “code xong rồi đẩy QA thật nhanh”, mà là **người dùng nhận được giá trị đúng, an toàn và có thể kiểm chứng qua những vòng phản hồi ngắn, đều và bền vững**.
