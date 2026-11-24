# Thiết kế đơn giản theo nhu cầu đã được hiểu

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích ý nghĩa của **Simple Design** trong **Extreme Programming (XP)**: xây giải pháp đơn giản nhất **đáp ứng yêu cầu hiện đã được hiểu và các ràng buộc chất lượng bắt buộc**.
2. Phân biệt **đơn giản** với **sơ sài**, phân biệt nguyên tắc **YAGNI** với việc bỏ qua những rủi ro cần xử lý ngay.
3. Sử dụng bốn quy tắc thiết kế đơn giản thường được diễn đạt theo tư tưởng XP: kiểm thử đạt, bộc lộ ý định, tránh trùng lặp tri thức và giữ ít thành phần không cần thiết.
4. Kết hợp **test-first/TDD, refactoring, tích hợp liên tục, phản hồi sớm** để cải tiến cấu trúc code khi yêu cầu được làm rõ.
5. Đưa ra quyết định phù hợp khi cân nhắc abstraction, interface, framework, tối ưu hiệu năng, kiến trúc tương lai và các phụ thuộc khó đảo ngược.
6. Xây dựng một lát cắt tính năng có giá trị, thiết kế đủ đơn giản để kiểm chứng, đồng thời giữ an toàn dữ liệu, bảo mật và khả năng vận hành.

## 1. Bài toán: thiết kế quá nhiều trước khi thực sự biết cần gì

Giả sử một đội phát triển nền tảng học trực tuyến nhận user story:

> **Là** học viên đã đăng nhập, **tôi muốn** mở lại bài học hợp lệ gần nhất **để** không phải tự tìm bài đã dừng.

Một cách tiếp cận là dành nhiều tuần thiết kế một **Learning Progress Orchestration Platform** tổng quát cho mọi loại nội dung, nhiều nhà cung cấp lưu trữ, đồng bộ ngoại tuyến, gợi ý bài bằng trí tuệ nhân tạo và quản lý hàng chục chính sách xung đột. Những khả năng này có thể hữu ích trong tương lai, nhưng **chưa có bằng chứng** rằng chúng cần cho story hiện tại.

Một cách khác là hỏi:

- Với lát cắt sắp giao, **hành vi nào** thật sự phải đúng?
- Dữ liệu, API và quyền truy cập hiện có cho phép gì?
- Điều gì **đã rõ**, điều gì mới là **giả định**?
- Có rủi ro chất lượng hoặc kiến trúc nào **khó sửa về sau** nên xử lý ngay?
- Đâu là thiết kế **nhỏ, dễ hiểu, có thể kiểm chứng và thay đổi** nhất đáp ứng các điều kiện đó?

Đây là tinh thần của **Simple Design** trong XP: **làm đủ tốt cho hiện tại, duy trì khả năng thay đổi cho tương lai**.

> Thiết kế đơn giản không có nghĩa là viết ít code bằng mọi giá. Nó có nghĩa không tạo thêm cấu trúc, hành vi và sự phức tạp **khi chưa có lý do thực tế**, nhưng vẫn đáp ứng nhu cầu và chất lượng đã biết.

Nếu làm đúng, đội có thể cung cấp một Increment dùng được, nhận phản hồi sớm rồi phát triển hệ thống theo những điều đã học. Nếu làm sai thành “cứ code tạm trước”, đội sẽ tích lũy lỗi, phụ thuộc cứng và nợ kỹ thuật.

## 2. Vị trí của Simple Design trong Extreme Programming

**Extreme Programming (XP)** là một cách tiếp cận Agile nhấn mạnh phản hồi nhanh và những thực hành kỹ thuật giúp thay đổi phần mềm an toàn. XP thường được gắn với các giá trị **giao tiếp, đơn giản, phản hồi, can đảm và tôn trọng**.

Simple Design không hoạt động đơn lẻ:

| Thực hành XP | Hỗ trợ thiết kế đơn giản như thế nào? | Tình huống minh họa |
| --- | --- | --- |
| **Small releases / incremental delivery** | Giao lát cắt nhỏ để sớm xác minh giả định, tránh thiết kế cho nhiều khả năng chưa dùng. | Đầu tiên mở đúng bài gần nhất khi có mạng, chưa giải quyết toàn bộ offline. |
| **Test-Driven Development (TDD)** | Bắt đầu từ hành vi mong đợi, chỉ viết phần code cần để đạt test rồi refactor. | Viết test cho quy tắc “chọn bài mới nhất còn quyền”. |
| **Refactoring** | Cải thiện cấu trúc mà không chủ ý thay đổi hành vi quan sát được. | Tách điều kiện lọc quyền thành một hàm rõ nghĩa sau khi test đã bảo vệ. |
| **Continuous Integration (CI)** | Phát hiện sai lệch khi thay đổi nhỏ được tích hợp thường xuyên. | Mỗi thay đổi luồng tiến độ chạy test liên quan. |
| **Pair programming** | Hai người cùng xem giả định, tên gọi, tình huống biên và thiết kế. | Một người đề xuất interface mới, người kia hỏi có biến thể thực tế nào cần nó. |
| **Collective code ownership** | Đội cùng chịu trách nhiệm cải tiến code, giảm rào cản “chỉ một người dám sửa”. | Người thấy trùng quy tắc có thể refactor an toàn cùng test. |
| **Customer collaboration và feedback** | Làm rõ điều người dùng thực sự cần, tránh thiết kế theo sở thích kỹ thuật. | Product Owner xác nhận “gần nhất” theo bản ghi hợp lệ. |
| **Sustainable pace** | Tránh sửa chữa vội, thiếu test vì làm việc kéo dài quá mức. | Giữ nhịp refactor/test và giao tăng dần. |

Các thực hành này tăng cường lẫn nhau. Chỉ nhắc “YAGNI” nhưng không có test, không tích hợp thường xuyên và không chừa không gian refactor sẽ khiến việc đổi hướng trở nên đắt đỏ.

### Quan hệ với Scrum và Kanban

- **Scrum** giúp đội tập trung vào Product Goal, Sprint Goal và Increment đáp ứng Definition of Done. Simple Design hỗ trợ Developers tạo ra Increment phù hợp mà không mang theo cấu trúc chưa cần.
- **Kanban** giúp nhìn WIP, thời gian chờ, cycle time và lỗi lặp lại. Thiết kế đơn giản, test tốt và thay đổi nhỏ có thể giảm thời gian review/tích hợp, nhưng tác động cần được đo thay vì mặc nhiên cho là có.
- **XP** cung cấp các thực hành kỹ thuật và hợp tác để thay đổi phần mềm đáng tin cậy.

Không bắt buộc dùng Scrum, Kanban và XP đồng thời. Điều quan trọng là chọn cơ chế phù hợp với loại công việc, cách nhận phản hồi và mức rủi ro.

## 3. Thế nào là “nhu cầu đã được hiểu”?

Từ “đã được hiểu” **không đồng nghĩa** mọi yêu cầu tương lai đều đã được đặc tả. Nó chỉ điều đội đã đủ căn cứ xác nhận **để đưa ra quyết định thiết kế cho lát cắt hiện tại**.

Ví dụ với tính năng “Tiếp tục học”:

| Mức độ hiểu biết | Nội dung | Hành động phù hợp |
| --- | --- | --- |
| **Đã xác nhận** | Học viên chỉ thấy tiến độ của tài khoản mình, chỉ mở nội dung còn quyền. | Thiết kế và test phân quyền ngay. |
| **Đã xác nhận** | Lát cắt đầu cần mở **bài học gần nhất**, chưa cần vị trí video từng giây. | Tập trung vào định danh bài, chưa xây engine đồng bộ thời gian phát. |
| **Giả định cần kiểm tra** | API hiện có trả dữ liệu tiến độ theo thứ tự ổn định. | Làm contract/integration test hoặc spike ngắn. |
| **Câu hỏi nghiệp vụ mở** | Nếu hai bản ghi có cùng thời điểm xác nhận, chọn bản nào? | Đưa ví dụ để Product Owner hoặc người có thẩm quyền chốt quy tắc. |
| **Ý tưởng xa hơn** | Xem offline trên mọi thiết bị, đồng bộ ghi chú và video. | Giữ trong backlog/hoạt động khám phá; chưa biến thành framework bắt buộc của lát cắt đầu. |
| **Ràng buộc đã biết** | Thay đổi phải không làm lộ dữ liệu, không làm hỏng tiến độ hiện có. | Đưa vào thiết kế, kiểm thử và Definition of Done áp dụng. |

### Nhu cầu không chỉ là tính năng

Điều đã biết còn có thể gồm **phi chức năng**:

- Quyền truy cập, bảo vệ dữ liệu cá nhân, khả năng kiểm toán.
- Tính nhất quán khi ghi dữ liệu hoặc xử lý yêu cầu gửi lại.
- Giới hạn hiệu năng theo thiết bị, số người dùng và tải đã xác nhận.
- Khả năng truy cập cho người dùng có nhu cầu hỗ trợ.
- Khôi phục khi triển khai thất bại, di chuyển dữ liệu an toàn.
- Nghĩa vụ hợp đồng, tuân thủ hoặc API đối tác.

Không thể loại các điều này khỏi thiết kế chỉ vì chúng “không xuất hiện trong một câu user story”. **Đơn giản là đáp ứng đúng các điều cần đạt**, không phải chỉ đáp ứng luồng lý tưởng.

## 4. Simple Design khác thiết kế sơ sài ở đâu?

| Thiết kế đơn giản có chủ đích | Thiết kế sơ sài hoặc cẩu thả |
| --- | --- |
| Đáp ứng các yêu cầu và ràng buộc **đã được xác nhận**. | Chỉ giải quyết một ví dụ đẹp nhất và bỏ ngoại lệ quan trọng. |
| Có test và bằng chứng rằng các hành vi cần thiết hoạt động. | “Tôi chạy thử bằng tay thấy được” rồi bỏ qua hồi quy. |
| Cấu trúc nhỏ, tên rõ, dễ hiểu và dễ thay đổi. | Dồn nhiều quy tắc vào một hàm bí hiểm để giảm số dòng. |
| Chưa tạo abstraction không có người dùng thực tế. | Không phân tách ngay cả khi hai trách nhiệm độc lập đã làm code khó sửa. |
| Bảo vệ dữ liệu, phân quyền và chất lượng thiết yếu ngay từ đầu. | Hoãn quyền truy cập hoặc kiểm thử dữ liệu đến “Sprint sau”. |
| Có thể tiến hóa qua thay đổi nhỏ và refactor an toàn. | Chồng các bản vá mà không bao giờ trả nợ thiết kế. |
| Ghi giả định, rủi ro và điểm đánh giá lại. | Không ai biết vì sao code được viết như vậy. |

Một lớp **rất ngắn nhưng có điều kiện rối, tên biến mơ hồ, không test** không hẳn đơn giản. Ngược lại, một thành phần có thêm kiểm tra phân quyền, logging và kiểm thử có thể dài hơn nhưng là **thiết kế đơn giản nhất để đáp ứng chất lượng thực tế**.

## 5. YAGNI: chưa cần thì đừng xây

**YAGNI** là viết tắt của **You Aren't Gonna Need It**: đừng triển khai khả năng chỉ vì nghĩ **có thể một ngày nào đó sẽ cần**. Trong XP, điều này giúp tránh đầu tư sớm vào những giả định dễ sai.

### Ví dụ thiết kế sớm quá mức

Story hiện tại chỉ cần mở bài gần nhất. Một kiến trúc đề xuất gồm:

~~~text
LearningProgressEngine
  +-- ProgressProviderFactory
  +-- MultiCloudProgressStrategyRegistry
  +-- OfflineConflictPolicyPlugin
  +-- VideoSecondLevelSyncAdapter
  +-- FutureContentTypeResolver
  +-- ProgressWorkflowDSL
  +-- ResumeRecommendationOptimizer
~~~

Nếu chưa có yêu cầu thực tế cho đa nhà cung cấp, đa loại nội dung hoặc đồng bộ offline, những lớp này làm tăng:

- Số khái niệm mà developer/tester phải hiểu.
- Số nhánh, cấu hình và trường hợp cần kiểm thử.
- Chi phí tích hợp và gỡ lỗi.
- Rủi ro chọn sai abstraction trước khi biết biến thể thực tế.
- Chi phí duy trì API nội bộ chỉ để đáp ứng một dự đoán.

Một thiết kế đơn giản hơn có thể là:

~~~text
ResumeController
  -> ResumeService
       -> ProgressRepository hiện có
       -> Kiểm tra quyền học qua dịch vụ hiện có
       -> Chọn tiến độ hợp lệ gần nhất
~~~

**Đây cũng chỉ là sơ đồ minh họa.** Nếu hệ thống đã có một service phù hợp, không cần tạo thêm cả ba lớp mới. Nếu có ràng buộc giao dịch hoặc tích hợp phức tạp đã xác nhận, phải biểu diễn nó trong thiết kế.

### YAGNI không có nghĩa là...

- Bỏ thiết kế bảo mật hoặc phân quyền vì “chưa có yêu cầu UI”.
- Không làm test hoặc bỏ Definition of Done để viết code nhanh.
- Trì hoãn một thay đổi migration khó đảo ngược đã biết rõ.
- Từ chối mọi abstraction, interface hoặc tối ưu dù đã có nhu cầu và bằng chứng.
- Không ghi nhận các câu hỏi mở và giả định quan trọng.
- Luôn chọn giải pháp nhanh nhất trong hôm nay bất kể tổng chi phí thay đổi.

### Câu hỏi quyết định

Trước khi thêm một thành phần “phòng tương lai”, hãy hỏi:

> “**Hiện tại** có hành vi, rủi ro hoặc quyết định đã xác nhận nào buộc chúng ta cần thành phần này không? Nếu chưa, chi phí bổ sung về sau là gì và khả năng thay đổi sau này có thực sự khó không?”

Nếu phần bổ sung rất rẻ sau này, dễ đảo ngược và hiện không tạo giá trị, YAGNI thường ủng hộ **chưa làm**. Nếu quyết định liên quan mã hóa dữ liệu, hợp đồng đối tác hoặc schema khó di chuyển, nghiên cứu sớm có thể hợp lý.

## 6. Bốn quy tắc thiết kế đơn giản như một công cụ rà soát

Một cách diễn đạt quen thuộc của **bốn quy tắc thiết kế đơn giản** trong truyền thống XP là:

1. **Các bài kiểm thử cần thiết đều đạt** (*passes tests*).
2. **Code bộc lộ rõ ý định** (*reveals intention*).
3. **Không có trùng lặp không cần thiết** (*no duplication*).
4. **Số thành phần không nhiều hơn mức cần thiết** (*fewest elements*).

Các phiên bản diễn đạt và thứ tự có thể khác nhau trong tài liệu/thực hành; đây là **các nguyên tắc suy nghĩ**, không phải một thuật toán chấm điểm chính xác.

### 6.1. Tests pass: đúng hành vi trước

Đội có một tập kiểm thử phản ánh hành vi và rủi ro quan trọng. Test xanh cung cấp **bằng chứng có giới hạn** rằng phần đã được kiểm tra đáp ứng mong đợi, chứ không chứng minh hệ thống không còn lỗi.

Ví dụ với “Tiếp tục học”, các trường hợp phải được cân nhắc gồm:

- Một bài hợp lệ: mở đúng bài.
- Nhiều bài: chọn bài hợp lệ gần nhất theo quy tắc đã chốt.
- Bài thuộc tài khoản khác: không được lộ dữ liệu.
- Khóa đã hết quyền: không mở nội dung trái quyền.
- Không có dữ liệu: hiển thị trạng thái phù hợp.
- Dịch vụ lỗi hoặc dữ liệu xung đột: xử lý theo chính sách đã xác nhận.

### 6.2. Reveals intention: tên và cấu trúc nói được “vì sao”

So sánh:

~~~java
// Khó hiểu: các tên không bộc lộ quy tắc
boolean ok(Progress p, String a, Set<String> s) {
    return p.accountId().equals(a) && s.contains(p.courseId());
}
~~~

Với:

~~~java
// Rõ nghĩa hơn trong ngữ cảnh lọc tiến độ
boolean belongsToCurrentAccountAndAccessibleCourse(
        Progress progress,
        String currentAccountId,
        Set<String> accessibleCourseIds) {
    return progress.accountId().equals(currentAccountId)
            && accessibleCourseIds.contains(progress.courseId());
}
~~~

Không phải mọi biểu thức đều cần một phương thức dài như trên; đôi khi tên predicate, kiểu dữ liệu hoặc hàm nhỏ đã đủ. Mục tiêu là người đọc hiểu **quy tắc nghiệp vụ** mà không phải lần theo hàng loạt lớp.

### 6.3. No duplication: loại bỏ trùng lặp tri thức

Hai đoạn code giống nhau về cú pháp chưa chắc chứa **cùng một quy tắc**. Ví dụ hai màn hình có kiểm tra dữ liệu trông giống nhau nhưng theo hai chính sách nghiệp vụ khác nhau: gộp vội vào một hàm tổng quát có thể tạo **sự phụ thuộc sai**.

Ngược lại, nếu ba nơi phải dùng cùng quy tắc **“chỉ tài khoản đang đăng nhập xem tiến độ của chính mình”**, cần xem xét đặt chính sách tại nơi có thẩm quyền và dùng lại đúng cách, thay vì chép ba biểu thức dễ lệch nhau.

**Tránh cả hai cực đoan:**

- Trùng lặp quy tắc bắt buộc làm các nơi hành xử khác nhau.
- Abstraction hóa quá sớm chỉ vì hai đoạn code trông giống nhau.

### 6.4. Fewest elements: không thêm khái niệm nếu không cần

Không có lý do để tạo một **ProviderFactory**, **StrategyRegistry** và **AbstractResumeManager** cho duy nhất một nguồn dữ liệu cố định nếu việc dùng chúng không mang lợi ích hiện tại.

Nhưng một interface có thể hợp lý khi:

- Có **hai cách triển khai thực sự** cần thay đổi hoặc kiểm chứng.
- Hợp đồng giữa hai hệ thống/nhóm đã tồn tại, cần ranh giới ổn định.
- Có yêu cầu thử nghiệm hoặc thay thế phụ thuộc ngoài đã xác nhận.
- Một boundary kiến trúc thật sự giúp bảo vệ module quan trọng khỏi biến động bên ngoài.

Nguyên tắc là **ít thành phần cần thiết nhất**, không phải “càng ít class càng tốt”. Gộp mọi thứ vào một God Class có thể giảm số class nhưng tăng độ phức tạp thực tế.

## 7. Quy trình thiết kế đơn giản bắt đầu từ user story

Một workflow có thể dùng cho từng lát cắt:

1. **Hiểu kết quả người dùng:** Ai cần gì, vì sao?
2. **Làm rõ bằng ví dụ:** Các trường hợp thành công, ranh giới, không có dữ liệu, lỗi quan trọng.
3. **Phân biệt điều chắc và giả định:** API, dữ liệu, quyền, tính nhất quán, phụ thuộc.
4. **Xác định ràng buộc chất lượng:** Bảo mật, hiệu năng có căn cứ, DoD, vận hành, khả năng rollback.
5. **Chọn thiết kế nhỏ nhất đáp ứng được:** Tận dụng thành phần hiện có, chưa xây những lựa chọn tương lai không cần.
6. **Viết kiểm thử và triển khai từng hành vi:** Dùng TDD khi phù hợp; tích hợp thường xuyên.
7. **Refactor khi test bảo vệ hành vi:** Sửa tên, tách trách nhiệm, loại bỏ trùng lặp tri thức.
8. **Giao Increment và lấy phản hồi:** Xem người dùng có đạt kết quả không, cập nhật backlog.
9. **Tiến hóa thiết kế khi có nhu cầu mới:** Không giữ nguyên cấu trúc cũ bằng mọi giá.

~~~mermaid
flowchart TD
    A["User story + kết quả cần tạo"] --> B["Ví dụ + tiêu chí chấp nhận"]
    B --> C["Kiểm tra rủi ro, ràng buộc và giả định"]
    C --> D{"Đủ hiểu biết để thiết kế lát cắt?"}
    D -- "Chưa" --> E["Trao đổi hoặc spike có giới hạn"]
    E --> C
    D -- "Rồi" --> F["Thiết kế nhỏ nhất đáp ứng hiện tại"]
    F --> G["Test trước / code nhỏ / refactor"]
    G --> H["CI + kiểm chứng tích hợp + DoD"]
    H --> I{"Đáp ứng nhu cầu và chất lượng?"}
    I -- "Chưa" --> G
    I -- "Rồi" --> J["Increment + phản hồi"]
    J --> K["Nhu cầu mới được xác nhận"]
    K --> B
~~~

Đây là **chu trình thực hành**, không phải quy định XP bắt buộc tổ chức họp hoặc ghi tài liệu riêng cho từng mũi tên. Với lỗi nhỏ có hành vi đã rõ, vòng lặp có thể diễn ra rất nhanh; với dữ liệu nhạy cảm hoặc hợp đồng đối tác, có thể cần thêm bằng chứng và kiểm soát.

## 8. Ví dụ xuyên suốt: chọn bài học gần nhất bằng thiết kế đơn giản

### 8.1. Chốt phạm vi đầu tiên

Story:

> **Là** học viên đã đăng nhập, **tôi muốn** mở bài học hợp lệ gần nhất **để** tiếp tục mà không mất công tìm lại.

Giả sử Product Owner và đội xác nhận các quy tắc **cho ví dụ học tập**:

1. Chỉ tính tiến độ thuộc tài khoản đang đăng nhập.
2. Chỉ tính bài thuộc các khóa học tài khoản **hiện còn quyền**.
3. Chọn bản ghi có thời điểm lưu đã được máy chủ xác nhận **mới nhất** trong các bản ghi hợp lệ.
4. Nếu không có bản ghi hợp lệ, trả kết quả **không có bài để tiếp tục**.
5. Khi hai bản ghi có cùng thời điểm, quy tắc ưu tiên **chưa được quyết định**; cần đưa ra ví dụ và làm rõ trước khi phần xử lý đó được giao.

Trong sản phẩm thực tế, việc xác thực tài khoản và quyền học phải được kiểm tra ở **ranh giới có thẩm quyền**; code chọn tiến độ dưới đây chỉ minh họa một phần logic nghiệp vụ, không thể thay thế bảo mật dịch vụ.

### 8.2. Thiết kế dễ hiểu trước khi có nhu cầu tổng quát hóa

Ta có thể mô tả một đối tượng tiến độ và một hàm chọn:

~~~java
import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.Set;

record Progress(
        String accountId,
        String courseId,
        String lessonId,
        Instant savedAt) {
}

final class ResumeSelector {
    Optional<Progress> latestAccessible(
            String currentAccountId,
            Set<String> accessibleCourseIds,
            List<Progress> progressRecords) {

        return progressRecords.stream()
                .filter(p -> p.accountId().equals(currentAccountId))
                .filter(p -> accessibleCourseIds.contains(p.courseId()))
                .max(Comparator.comparing(Progress::savedAt));
    }
}
~~~

**Vì sao đây là một điểm bắt đầu đơn giản?**

- Hành vi hiện tại có thể diễn đạt ngắn: lọc theo chủ tài khoản, lọc quyền rồi chọn thời điểm mới nhất.
- Không có **StrategyFactory**, **PolicyRegistry** hoặc khả năng offline chưa cần.
- Trả về **Optional** để biểu diễn trường hợp không có bản ghi hợp lệ.
- Có thể kiểm thử logic thuần mà không cần khởi động toàn bộ ứng dụng.

**Những giới hạn phải nói rõ:**

- **currentAccountId** phải lấy từ ngữ cảnh xác thực phía server, không tin tham số tài khoản do client tùy ý khai báo.
- **accessibleCourseIds** phải được cung cấp bởi nguồn quyền có thẩm quyền và được kiểm tra ở thời điểm cần thiết; logic này không tự bảo vệ endpoint khỏi truy vấn trái quyền.
- Ví dụ giả định các trường không null và dữ liệu được chuẩn hóa. Dữ liệu không hợp lệ phải có chính sách xử lý phù hợp.
- Nếu hai bản ghi có cùng **savedAt**, hàm **max** với comparator hiện tại không xác định một quy tắc nghiệp vụ ưu tiên minh bạch; cần bổ sung khi quy tắc được xác nhận.
- Nếu dữ liệu lớn, truy vấn/bộ lọc phù hợp có thể cần được thực hiện ở tầng lưu trữ để tránh tải toàn bộ tiến độ vào bộ nhớ; đó là **quyết định có căn cứ về tải và kiến trúc**.

Điều quan trọng không phải mẫu code này “là tối ưu”, mà là **mỗi cấu trúc đều có lý do từ nhu cầu đã biết**.

### 8.3. Kiểm thử những hành vi cốt lõi

Ví dụ JUnit 5, giả sử **Progress** và **ResumeSelector** ở cùng phạm vi truy cập phù hợp:

~~~java
import org.junit.jupiter.api.Test;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import static org.junit.jupiter.api.Assertions.assertEquals;

class ResumeSelectorTest {
    private final ResumeSelector selector = new ResumeSelector();

    @Test
    void choosesLatestAccessibleProgressForCurrentAccount() {
        var older = new Progress(
                "A", "X", "lesson-2", Instant.parse("2026-01-01T09:00:00Z"));
        var newer = new Progress(
                "A", "X", "lesson-4", Instant.parse("2026-01-01T10:00:00Z"));
        var otherAccount = new Progress(
                "B", "X", "lesson-9", Instant.parse("2026-01-01T11:00:00Z"));

        assertEquals(
                Optional.of(newer),
                selector.latestAccessible(
                        "A", Set.of("X"),
                        List.of(older, newer, otherAccount)));
    }

    @Test
    void excludesCoursesWithoutCurrentAccess() {
        var accessible = new Progress(
                "A", "X", "lesson-2", Instant.parse("2026-01-01T09:00:00Z"));
        var restricted = new Progress(
                "A", "Y", "lesson-9", Instant.parse("2026-01-01T11:00:00Z"));

        assertEquals(
                Optional.of(accessible),
                selector.latestAccessible(
                        "A", Set.of("X"), List.of(accessible, restricted)));
    }

    @Test
    void returnsEmptyWhenNoProgressIsEligible() {
        assertEquals(
                Optional.empty(),
                selector.latestAccessible("A", Set.of("X"), List.of()));
    }
}
~~~

Ba test giúp xác nhận **một phần** hành vi, không phải toàn bộ chất lượng sản phẩm. Cần thêm kiểm thử API, session, phân quyền phía server, lỗi lưu trữ, hiệu năng và tương tác với hệ thống thật theo rủi ro và Definition of Done.

### 8.4. Tại sao chưa tạo interface?

Nếu hiện chỉ có một cách chọn tiến độ và một nguồn dữ liệu, chưa có lý do bắt buộc để tạo:

~~~text
IResumeSelector
  -> AbstractResumeSelector
      -> DefaultResumeSelector
          -> ProgressPolicyFactory
~~~

Một lớp **ResumeSelector** rõ ràng có thể là đủ. Khi thực sự có yêu cầu “đề xuất bài chưa học” hoặc “đồng bộ phiên bản theo nhiều thiết bị”, nhóm mới đánh giá **điểm biến thiên** và chỗ đặt abstraction phù hợp.

### 8.5. Không cứng nhắc giữ thiết kế đơn giản ban đầu

Nếu sau thử nghiệm người dùng xác nhận:

- Bài học dạng video cần vị trí phát được đồng bộ.
- PDF chỉ cần ghi trang đã đọc.
- Tiến độ được cập nhật từ hai thiết bị và phải xử lý phiên bản.

Khi đó có **những khác biệt nghiệp vụ thực tế**. Nhóm có thể tách các chính sách đã được xác nhận, bổ sung lớp hoặc interface có ý nghĩa và refactor với test đang bảo vệ hành vi cũ. YAGNI **không phải lời cấm tiến hóa kiến trúc**.

## 9. TDD giúp thiết kế dựa trên hành vi thay vì dự đoán

**Test-Driven Development (TDD)** thường được thực hành theo vòng:

1. **Red:** Viết một kiểm thử nhỏ cho hành vi mong muốn; thấy test thất bại vì hành vi chưa có.
2. **Green:** Viết lượng code tối thiểu **đúng và đủ** để test đạt.
3. **Refactor:** Cải thiện cấu trúc mà vẫn giữ hành vi, chạy test lại.

~~~mermaid
flowchart LR
    R["RED: một test hành vi nhỏ thất bại"] --> G["GREEN: code đơn giản để test đạt"]
    G --> F["REFACTOR: làm rõ, loại trùng lặp, giữ hành vi"]
    F --> N["Kiểm tra và chọn ví dụ tiếp theo"]
    N --> R
~~~

### Ví dụ đi từng bước

Với **ResumeSelector**:

**Vòng 1:** Test “không có tiến độ thì trả empty”. Code có thể chỉ cần trả **Optional.empty()**. Đây là hành vi nhỏ đầu tiên, chưa đủ toàn bộ yêu cầu.

**Vòng 2:** Test “một bản ghi hợp lệ thì chọn bản ghi đó”. Bổ sung logic lọc đơn giản.

**Vòng 3:** Test “hai bản ghi hợp lệ có thời điểm khác nhau thì chọn mới hơn”. Thêm phép so sánh **savedAt**.

**Vòng 4:** Test “bản ghi mới hơn của tài khoản B không ảnh hưởng A”. Bổ sung điều kiện tài khoản.

**Vòng 5:** Test “khóa đã hết quyền bị loại”. Bổ sung điều kiện quyền truy cập.

**Vòng 6:** Refactor tên hàm, nhóm các điều kiện hợp lý, loại đoạn trùng lặp và chạy lại test.

Đây là một trình tự minh họa. Trong dự án thực, thứ tự test nên xét mức rủi ro; quy tắc **không lộ dữ liệu tài khoản khác** cần được kiểm tra sớm, không đợi sản phẩm chạy đến cuối Sprint.

### TDD không đồng nghĩa “chỉ cần unit test”

TDD giúp cải thiện thiết kế của một phần logic, nhưng:

- Không tự xác nhận nhu cầu người dùng là đúng.
- Không tự kiểm tra quyền truy cập ở tầng API hoặc chính sách dữ liệu.
- Không chứng minh hiệu năng khi có tải cao.
- Không thay thế kiểm thử tích hợp, thăm dò, khả năng sử dụng hoặc kiểm tra bảo mật.

Vì vậy, hãy dùng TDD **kết hợp tiêu chí chấp nhận, DoD và phản hồi từ increment thực tế**.

## 10. Refactoring: cải thiện cấu trúc khi có bằng chứng

**Refactoring** là thay đổi cấu trúc bên trong code mà **không cố ý thay đổi hành vi quan sát được**. Nó là phần quan trọng giúp thiết kế đơn giản không biến thành tích lũy bản vá.

### Khi nào refactor?

- Một tên hàm hoặc biến không còn biểu thị đúng ý nghĩa nghiệp vụ.
- Hai nơi đã xuất hiện **cùng một quy tắc** và bắt đầu lệch nhau.
- Một hàm đang có nhiều trách nhiệm độc lập.
- Logic có nhiều nhánh gây khó kiểm thử.
- Phụ thuộc bên ngoài làm code khó thay đổi hoặc khó kiểm chứng.
- Thêm một yêu cầu thực tế khiến cấu trúc hiện tại không còn rõ.

### Cách refactor an toàn

1. Bảo đảm hiểu **hành vi hiện tại**, bổ sung characterization test nếu code cũ thiếu test.
2. Chọn một thay đổi nhỏ như **rename**, **extract method** hoặc tách trách nhiệm.
3. Chạy test liên quan và kiểm tra tích hợp phù hợp sau thay đổi.
4. Giữ nhịp commit nhỏ, code review rõ ý định và tích hợp sớm.
5. Nếu phát hiện thay đổi hành vi nghiệp vụ, **tách khỏi refactor thuần túy** và xác nhận yêu cầu.

### Ví dụ phân biệt refactor và thay đổi tính năng

| Thao tác | Có phải refactor thuần túy? | Giải thích |
| --- | --- | --- |
| Đổi tên hàm **getLatest** thành **latestAccessible** và sửa các chỗ gọi, hành vi không đổi | Có thể | Tăng khả năng bộc lộ ý định. |
| Tách phép lọc quyền thành một hàm dùng chung nhưng vẫn cùng chính sách | Có thể | Cần test chứng minh hành vi không đổi. |
| Thay điều kiện “chọn mới nhất theo savedAt” bằng “chọn lessonId lớn nhất” | Không | Thay quy tắc chọn bài. |
| Bổ sung xử lý xung đột đồng bộ theo version mới | Không thuần túy | Có hành vi/điều kiện nghiệp vụ mới. |
| Bỏ kiểm tra quyền truy cập để code ngắn hơn | Không và không an toàn | Làm thay đổi hành vi và tăng rủi ro lộ dữ liệu. |

### Refactor liên tục không có nghĩa sửa mọi thứ

Đội cần cân nhắc chi phí và rủi ro. Một cấu trúc hơi dư nhưng ổn định có thể chưa cần thay nếu không cản trở mục tiêu; ngược lại, một điểm trùng quy tắc phân quyền dễ gây lỗi nghiêm trọng cần được xử lý sớm.

## 11. “Đơn giản nhất” không phải “ít dòng code nhất”

Người mới học XP đôi khi tìm cách nén mọi logic thành một biểu thức hoặc một lớp lớn. Đó có thể là **tối ưu số ký tự**, không phải tối ưu khả năng hiểu và thay đổi.

### Ví dụ biểu thức ngắn nhưng khó duy trì

~~~java
return all.stream().filter(p -> p.accountId().equals(a) &&
        c.contains(p.courseId()) && p.savedAt() != null)
        .max(Comparator.comparing(Progress::savedAt));
~~~

Đoạn này có thể đủ ngắn nhưng đặt nhiều quy tắc trong một biểu thức, và một số điều kiện có thể cần xử lý lỗi riêng. Nếu yêu cầu và test chưa rõ, viết gọn không làm tăng tính đúng đắn.

Khi logic lớn lên, nhóm có thể dùng một **hàm hoặc đối tượng nghiệp vụ đặt tên rõ** cho chính sách đã được xác nhận. Không nên lập tức tạo cả hệ thống Rule Engine.

### Tư duy đánh giá cấu trúc

Hỏi:

1. Người khác có hiểu hành vi mà không phải giải mã tên biến?
2. Có điểm nào buộc sửa nhiều nơi vì cùng một quy tắc đã bị sao chép?
3. Có lớp/interface nào chỉ chuyển tiếp một lời gọi mà không bảo vệ ranh giới hoặc mô tả vai trò thực sự?
4. Thay một yêu cầu hiện đã biết có cần sửa hàng chục chỗ không?
5. Đội có thể kiểm thử logic độc lập và kiểm chứng hệ thống tích hợp không?

Đơn giản là **ít gánh nặng nhận thức và ít phụ thuộc không cần thiết** trong khi hành vi vẫn đúng, không phải code ngắn nhất.

## 12. Quyết định khi nào cần abstraction

**Abstraction** có ích khi mô tả một ý nghĩa chung hoặc ranh giới thay đổi đã được xác nhận. Nó trở thành chi phí khi chỉ dựa trên dự đoán.

### Tình huống 1 — Chỉ một implementation thực tế

Đội đang dùng một **ProgressRepository** hiện có và chỉ một chính sách chọn bài. Nếu thiết kế hiện tại đơn giản, thêm **ProgressRepositoryProviderFactory** và **SelectorStrategyFactory** khó tạo giá trị.

**Hướng ưu tiên:** Dùng thành phần sẵn có, đặt tên rõ và giữ kiểm thử.

### Tình huống 2 — Có hai nguồn thật sự cần hỗ trợ

Sản phẩm phải đọc tiến độ từ hệ thống cũ và hệ thống mới trong giai đoạn migration. Đây là nhu cầu thực tế có điều kiện rõ.

**Có thể cân nhắc** một interface mô tả hành vi đọc tiến độ thống nhất, với hai adapter. Cần thiết kế chuyển đổi dữ liệu, kiểm thử hợp đồng và chiến lược khôi phục; không chỉ tạo interface cho đẹp kiến trúc.

### Tình huống 3 — Hai quy tắc trông giống nhau nhưng nghĩa khác

Một quy tắc chọn **bài gần nhất đã xem**, quy tắc khác chọn **bài được gợi ý học tiếp**. Cả hai có thể lọc và sắp xếp dữ liệu, nhưng mục tiêu khác nhau.

**Không nên** vội gộp vào một “GenericProgressSelectionEngine” với 20 tham số tùy chọn. Có thể giữ hai hàm rõ nghĩa cho đến khi xuất hiện phần tri thức chung thật sự.

### Tình huống 4 — Biên kiến trúc khó đảo ngược

Nếu ứng dụng sẽ xử lý dữ liệu cá nhân giữa các tổ chức khác nhau, cần có ranh giới quyền truy cập, kiểm toán và cách cô lập dữ liệu **đã được xác nhận**. Một adapter hoặc service boundary ở đây có thể là thiết kế **cần thiết ngay**, không phải overengineering.

### Bảng quyết định nhanh

| Câu hỏi | Nghiêng về giữ đơn giản | Nghiêng về tạo abstraction có chủ đích |
| --- | --- | --- |
| Đã có nhiều biến thể thật sự? | Chỉ một trường hợp, biến thể còn là ý tưởng | Có ít nhất hai biến thể được xác nhận, cần đổi/chọn theo chính sách |
| Biến thể có cùng **ý nghĩa nghiệp vụ**? | Chỉ giống cú pháp, mục tiêu khác nhau | Cùng một hợp đồng hành vi |
| Có test bảo vệ trước khi tách? | Chưa, cần đặc tả hành vi và kiểm chứng | Có test có ý nghĩa cho hợp đồng và các biến thể |
| Ranh giới có khó đổi về sau? | Dễ bổ sung khi xuất hiện yêu cầu | Dữ liệu, hệ thống ngoài, nghĩa vụ hoặc migration có rủi ro cao |
| Lợi ích hiện tại có rõ? | Chỉ nêu “sẽ mở rộng trong tương lai” | Giảm phụ thuộc/cải thiện test hoặc đáp ứng nhu cầu đang tồn tại |

## 13. Thiết kế đơn giản và lựa chọn kiến trúc khó đảo ngược

YAGNI đặc biệt hữu ích với **quyết định dễ đổi**, nhưng cần thận trọng khi lựa chọn làm ảnh hưởng lâu dài tới dữ liệu, vận hành hoặc giao tiếp giữa hệ thống.

### Phân loại quyết định

| Quyết định | Khả năng đảo ngược điển hình | Cách tiếp cận |
| --- | --- | --- |
| Đổi tên hàm hoặc chia nhỏ module nội bộ có test | Tương đối dễ | Quyết định đơn giản, refactor khi có nhu cầu. |
| Chọn vị trí hiển thị nút qua một thử nghiệm UI | Thường dễ | Làm lát cắt nhỏ và lấy phản hồi nhanh. |
| Đổi công nghệ lưu trữ cho dữ liệu quan trọng | Có thể khó và tốn kém | Nghiên cứu migration, sao lưu, rollback và rủi ro từ sớm. |
| Công bố API công khai cho nhiều đối tác | Khó đổi vì có người dùng ngoài | Làm rõ hợp đồng, tương thích và cơ chế phiên bản. |
| Lựa chọn mô hình phân quyền hoặc lưu dữ liệu nhạy cảm | Rủi ro cao | Đưa bảo mật, tuân thủ và thử nghiệm vào thiết kế từ đầu. |
| Đưa mọi logic vào một thư viện tương lai chưa có consumer | Thường là lựa chọn có thể hoãn | Áp dụng YAGNI; đợi nhu cầu và điểm biến thiên rõ. |

### Sơ đồ tư duy quyết định

~~~mermaid
flowchart TD
    A["Có đề xuất thêm tầng/kiểu/khả năng mới"] --> B{"Đã có nhu cầu hoặc ràng buộc được xác nhận?"}
    B -- "Có" --> C["Chọn thiết kế nhỏ nhất đáp ứng điều kiện đó"]
    B -- "Chưa" --> D{"Nếu hoãn, thay đổi sau này có khó đảo ngược hoặc nguy hiểm?"}
    D -- "Không" --> E["Hoãn, ghi giả định, giữ thiết kế gọn"]
    D -- "Có" --> F["Khám phá rủi ro và bằng chứng trước quyết định"]
    F --> C
    C --> G["Test, tích hợp, xem chất lượng và phản hồi"]
    E --> G
~~~

Không phải mọi quyết định sẽ rơi vào “có/không” rõ ràng. Nếu bất định lớn, một **spike có giới hạn** hoặc nguyên mẫu an toàn có thể giúp thay cho tranh luận cảm tính.

## 14. Thiết kế đơn giản gắn với kiểm soát chất lượng

Một số đội nhầm “simple” với “tránh quy trình và test”. Trong sản phẩm thật, những kiểm soát cần thiết giúp giữ thiết kế dễ thay đổi mà không tạo rủi ro khó xử lý.

### 14.1. Bảo mật và phân quyền

Đối với tiến độ học:

- Danh tính tài khoản cần đến từ **cơ chế xác thực có thẩm quyền**.
- Quyền truy cập không chỉ được kiểm tra bằng việc ẩn nút ở giao diện.
- Các truy vấn phải tránh lộ dữ liệu của tài khoản/tenant khác.
- Cần kiểm chứng cả trường hợp chuyển tài khoản trên cùng thiết bị.

**Đơn giản** là có một chính sách quyền rõ và test đáng tin, không phải bỏ nó khỏi lát cắt đầu.

### 14.2. Tính toàn vẹn dữ liệu và gửi yêu cầu lặp

Khi user story thật sự có ghi tiến độ hoặc đồng bộ, phải hỏi:

- Nếu request được gửi lại do mất mạng, có gây ghi trùng không?
- Hai thiết bị cùng cập nhật, quy tắc xung đột được quyết định thế nào?
- “Đã lưu” có nghĩa là máy chủ đã xác nhận hay mới nằm trong bộ nhớ client?
- Có cách khôi phục sau lỗi ghi dữ liệu không?

Không cần thiết kế engine xung đột cho mọi trường hợp tương lai, nhưng **không được giả vờ dữ liệu đã an toàn** nếu luồng hiện tại có nguy cơ ghi sai.

### 14.3. Hiệu năng và khả năng mở rộng

**Không tối ưu trước khi có căn cứ** khác với **bỏ qua dấu hiệu hiệu năng đã biết**. Hàm lọc một danh sách tiến độ trong bộ nhớ có thể ổn cho ví dụ nhỏ; với hàng triệu bản ghi, cần đo tải, thiết kế truy vấn/index hoặc phân trang phù hợp.

Đừng đặt một ngưỡng giả như “mọi API dưới 50 ms” nếu không có yêu cầu, cách đo và dữ liệu nền. Nhưng nếu SLO, hợp đồng hoặc khả năng sử dụng đã được xác nhận, nó phải được xem ngay trong thiết kế và kiểm thử.

### 14.4. Khả năng vận hành và thay đổi an toàn

Một giải pháp nhỏ vẫn nên có những điều kiện phù hợp:

- Tín hiệu lỗi đủ để chẩn đoán, không log dữ liệu nhạy cảm trái chính sách.
- Cách triển khai hoặc rollback được xem xét theo rủi ro.
- Test tích hợp và hồi quy quan trọng chạy khi thay đổi.
- Tài liệu/hợp đồng được cập nhật khi có thay đổi ảnh hưởng bên khác.

**Definition of Done** trong Scrum hoặc chính sách chất lượng của đội giúp xác định ngưỡng thực tế. Không dùng sự đơn giản làm lý do để đặt trạng thái Done khi phần mềm chưa an toàn.

## 15. Ví dụ tiếp theo: khi có yêu cầu mới thật sự

Sau khi lát cắt “Tiếp tục học” được dùng, đội nhận được phản hồi mới:

> “Học viên trên điện thoại muốn tiếp tục đúng **vị trí video** đã dừng, kể cả khi đã xem trên laptop.”

### 15.1. Không vội mở rộng toàn bộ kiến trúc

Trước tiên cần hỏi:

- Loại nội dung nào có vị trí phát: video, podcast, bài đọc?
- Thiết bị nào nằm trong phạm vi ưu tiên?
- Vị trí được xác nhận như thế nào, độ chính xác cần thiết là gì?
- Khi hai thiết bị cập nhật cùng lúc, người dùng mong điều gì?
- Những yêu cầu về bản quyền và dữ liệu đã biết?

Lát cắt đầu có thể chỉ hỗ trợ **video trên hai loại thiết bị được xác nhận**, chưa cần offline hay mọi loại nội dung.

### 15.2. Tiến hóa khi có biến thể thật

Ban đầu, **ResumeSelector** chọn **bài**. Yêu cầu mới cần chính sách về **vị trí trong video**. Đội có thể:

1. Thêm test cho vị trí phát đã xác nhận của một video.
2. Thử contract API của hệ thống phát video.
3. Xây logic lưu và đọc vị trí tối thiểu.
4. Bảo đảm những bài không phải video vẫn hoạt động.
5. Khi có hai luồng thật sự khác nhau, cân nhắc tách chính sách theo **loại tiến độ** thay vì thêm vô số điều kiện vào một hàm.

Nếu sau vài lần thay đổi code xuất hiện ba triển khai **thực sự** dùng chung hợp đồng, đó mới là dữ liệu để tạo abstraction phù hợp.

### 15.3. Nguyên tắc “làm lại đúng lúc”

Không nên giữ một thiết kế cũ chỉ vì “chúng ta đã chọn đơn giản”. Thiết kế đơn giản theo nhu cầu đã biết **phải tiến hóa** khi nhu cầu đổi. Lúc đó test và refactoring giúp thay đổi có kiểm soát, tránh nợ kỹ thuật phát triển thành một hệ thống không ai muốn sửa.

## 16. Thảo luận chi phí: thiết kế trước hay trả chi phí sau?

Không có quy tắc rằng **mọi chi phí thiết kế sớm đều lãng phí** hay **mọi khoản hoãn đều rẻ**. Quyết định nên xét xác suất sử dụng, hậu quả khi sai và mức độ dễ thay đổi.

### Một ma trận suy nghĩ định tính

| Nhu cầu tương lai | Chi phí thay đổi về sau | Phương án thường hợp lý |
| --- | --- | --- |
| Chưa được xác nhận | Dễ thêm sau, ít ảnh hưởng dữ liệu | **YAGNI:** chưa triển khai, ghi giả định. |
| Đã được xác nhận | Dễ thay đổi | Làm lát cắt nhỏ đúng thời điểm, không cần framework tổng quát. |
| Chưa chắc nhưng rủi ro nếu sai rất cao | Khó đảo ngược | **Khám phá sớm:** spike, kiểm chứng, chuẩn bị biện pháp an toàn; không nhất thiết xây toàn bộ. |
| Đã bắt buộc theo hợp đồng/tuân thủ | Khó hoặc tốn chi phí đổi | Thiết kế và kiểm tra ràng buộc ngay từ đầu. |

### Ví dụ hai hướng đối lập

**Quá thiết kế:** Tạo lớp **OfflineConflictResolutionStrategyFactory** trước khi có người dùng offline, chỉ vì kiến trúc có vẻ “đẹp”.

**Thiếu thiết kế:** Để mọi request đọc tiến độ theo **accountId do client gửi**, rồi tính chuyện phân quyền ở Sprint sau. Đây là sai lầm về bảo mật, không phải YAGNI.

**Cân bằng:** Chỉ xây luồng mở bài gần nhất nhưng kiểm tra danh tính và quyền truy cập có thẩm quyền, test các ca quan trọng, giữ ranh giới dữ liệu đủ để có thể phát triển an toàn.

## 17. Các “mùi thiết kế” cần quan sát

Một số dấu hiệu gợi ý code đang phức tạp hơn mức cần thiết:

| Dấu hiệu | Câu hỏi cần hỏi | Hướng xử lý có thể thử |
| --- | --- | --- |
| Nhiều interface chỉ có một implementation và không có ranh giới thật | Vì sao cần interface này **ngay bây giờ**? | Bỏ tầng trung gian không mang giá trị nếu không ảnh hưởng hợp đồng. |
| Factory tạo một đối tượng cố định | Có biến thể cấu hình thực tế nào không? | Khởi tạo trực tiếp hoặc dùng cơ chế DI hiện có nếu phù hợp. |
| Nhiều tham số boolean điều khiển cùng một hàm | Có phải đang gộp các quy tắc nghiệp vụ khác nhau? | Tách hàm/tên theo ý nghĩa đã xác nhận. |
| Hai nơi chép cùng logic phân quyền | Có nguy cơ lệch chính sách và lỗi dữ liệu không? | Đưa quy tắc về nơi có thẩm quyền, thêm test. |
| Một hàm vừa đọc DB, kiểm tra quyền, tính điểm, gửi email và vẽ UI | Có nhiều lý do thay đổi không liên quan? | Tách theo trách nhiệm với kiểm thử và biên rõ. |
| API nội bộ có hàng chục tùy chọn chưa dùng | Các tùy chọn có người dùng thật không? | Thu hẹp contract hiện tại; xem tương thích trước khi xóa. |
| “Refactor” làm thay đổi hành vi người dùng | Có cần quyết định sản phẩm và test chấp nhận mới không? | Tách refactor khỏi thay đổi tính năng. |
| Code rất ngắn nhưng khó hiểu | Tên gọi, hàm và kiểu dữ liệu có rõ ý định không? | Tối ưu khả năng đọc, không tối ưu số ký tự. |
| Ít test, nhiều sửa nóng | Có cơ chế bảo vệ khi tiến hóa thiết kế không? | Viết characterization/integration test rồi refactor dần. |

Một **code smell** là tín hiệu để điều tra, không phải chứng cứ chắc chắn rằng thiết kế sai. Một lớp có interface vẫn có thể đúng vì nghĩa vụ tương thích hoặc ranh giới bảo mật; xem bối cảnh trước khi xóa.

## 18. Tình huống thực tế: hai cách triển khai cùng một story

### Bối cảnh

Một Scrum Team có Sprint Goal:

> “Học viên có thể mở lại đúng bài học hợp lệ gần nhất từ trang chủ trên thiết bị thường dùng.”

Các yêu cầu hiện đã hiểu: một tài khoản được xác thực, tiến độ do dịch vụ hiện có cung cấp, quyền học phải được kiểm tra, giao diện cần xử lý không có dữ liệu và lỗi đọc.

### Phương án A — Thiết kế dự đoán quá xa

Đội dành phần lớn Sprint để thiết kế:

- Bộ chọn nhà cung cấp tiến độ có thể cắm plugin.
- Engine quy tắc tiến độ cho video, PDF, bài kiểm tra, nội dung offline và tương lai.
- Lớp ánh xạ dữ liệu tổng quát có nhiều cấp kế thừa.
- Bộ cấu hình cho hai mươi biến thể chưa tồn tại.

Đến cuối Sprint, các lớp đã code và unit test riêng nhưng **chưa có luồng người dùng tích hợp đạt DoD**. Team chỉ có thể trình bày sơ đồ kiến trúc.

**Vấn đề:** Công việc chưa tạo được Increment usable phục vụ Sprint Goal. Thiết kế có thể sai khi người dùng thực sự cho phản hồi.

### Phương án B — Thiết kế đơn giản theo nhu cầu đã biết

Đội:

1. Trao đổi ba ví dụ nghiệp vụ chính, ca phân quyền và lỗi quan trọng.
2. Xác minh contract của API tiến độ hiện có.
3. Tạo logic chọn bài hợp lệ nhỏ và test trước các quy tắc.
4. Tích hợp UI–API–dữ liệu, bảo vệ phân quyền phía server.
5. Chạy test hồi quy, kiểm tra thông báo lỗi, đáp ứng DoD.
6. Cho một nhóm người dùng thử và quan sát khả năng tìm lại bài.

Kết quả có thể là **một Increment sớm**. Khi phản hồi cho thấy người học cần vị trí video, nhóm tiếp tục làm rõ và mở rộng đúng phần cần.

### Đánh giá công bằng

Không thể khẳng định phương án B **luôn** tốt hơn nếu môi trường thật có một hợp đồng bắt buộc cho nhiều loại nội dung hoặc migration khó đảo ngược ngay trong Sprint. Trong bối cảnh đã nêu, **không có bằng chứng cho các biến thể xa**, nên B phù hợp hơn với ý định Agile và XP.

| Tiêu chí | Phương án A | Phương án B |
| --- | --- | --- |
| Đáp ứng nhu cầu hiện được xác nhận | Chưa có luồng tích hợp | Tập trung giao luồng dùng được |
| Cơ hội nhận phản hồi | Muộn, chủ yếu từ sơ đồ | Sớm, từ sản phẩm hoạt động |
| Chi phí cấu trúc chưa được chứng minh | Cao | Thấp hơn |
| Kiểm soát bảo mật và chất lượng | Có nguy cơ bị trì hoãn nếu không tích hợp | Đưa vào lát cắt và DoD |
| Tiềm năng phát triển tiếp | Có nhiều extension point nhưng chưa chắc đúng | Có test và refactoring để tiến hóa khi nhu cầu rõ |

**Điểm học:** “Thiết kế cho thay đổi” có thể có nghĩa **giữ code rõ, nhỏ và an toàn để sửa**, chứ không cần đoán đúng mọi biến thể tương lai.

## 19. Phối hợp người sản phẩm, developer và tester

Simple Design cần **thông tin đúng** về nhu cầu, chứ không chỉ kỹ năng viết code. Một cuộc trao đổi ngắn theo các góc nhìn **Product Owner/nghiệp vụ – Developer – Tester** có thể ngăn thiết kế sai từ đầu.

### Ví dụ đối thoại

> **Product Owner:** “Chúng ta muốn học viên mở lại bài gần nhất.”
>
> **Developer:** “Nếu bài mới nhất thuộc khóa đã hết quyền thì sao?”
>
> **Tester:** “Hãy thử ví dụ: tài khoản A có bài khóa X lúc 9 giờ còn quyền và bài khóa Y lúc 10 giờ đã hết quyền. Mục tiêu là gì?”
>
> **Product Owner:** “Chỉ đưa A tới bài mà A còn quyền. Nếu không có bài hợp lệ, hiển thị gợi ý bắt đầu khóa học.”
>
> **Developer:** “Vậy lát cắt này chưa cần engine gợi ý hoặc offline, nhưng cần kiểm tra quyền ở dịch vụ và test trường hợp hai khóa.”

Đầu ra hữu ích là **quy tắc đã được thống nhất, ví dụ kiểm chứng và giới hạn phạm vi**. Đây là cách giảm overengineering và tránh thiếu thiết kế vì hiểu sai nghiệp vụ.

### Khi nào cần hỏi tiếp?

Một số câu hỏi ảnh hưởng trực tiếp đến tính đúng đắn phải được giải quyết trước khi tính năng hoàn thành:

- Nếu hai bản ghi cùng thời điểm, ưu tiên thế nào?
- Nếu tài khoản đã bị thu hồi quyền ngay sau khi trang chủ tải, kiểm tra lại khi mở bài ra sao?
- API nào cung cấp danh tính và quyền đáng tin?
- Khi không đọc được tiến độ, giao diện cần hiển thị gì?
- Dữ liệu cá nhân phải được xử lý và lưu dấu thế nào theo chính sách?

Những câu hỏi về đồng bộ offline cho nhiều loại nội dung có thể chờ khi chưa nằm trong phạm vi hiện tại.

## 20. Thực hành theo chu trình ngắn trong một Sprint

Một kế hoạch thực hành có thể như sau:

| Mốc thực hiện minh họa | Hoạt động | Bằng chứng cần có |
| --- | --- | --- |
| Bắt đầu | Xác nhận user story, tiêu chí chấp nhận, rủi ro và phần không thuộc phạm vi | Ví dụ nghiệp vụ và quyết định rõ |
| Trước khi code nhiều | Contract test API và phác thảo một luồng xuyên suốt | Không bỏ sót phụ thuộc quan trọng |
| Các vòng nhỏ | Red–Green–Refactor cho từng quy tắc; pairing khi hữu ích | Test đạt, code rõ, không tạo tầng chưa cần |
| Trong Sprint | Merge nhỏ, CI, kiểm thử API/UI và quyền | Increment tích hợp không làm hỏng phần cũ |
| Trước khi gọi Done | Xem Definition of Done và các ràng buộc chất lượng | Phần mềm dùng được với hành vi đúng |
| Sau khi có Increment | Demo/nhận phản hồi sớm; kiểm tra Product Goal và Sprint Goal | Quyết định mở rộng hoặc thay đổi backlog |
| Retrospective | Đánh giá chờ review, lỗi tích hợp, thay đổi khó và giả định sai | Một cải tiến kỹ thuật/trao đổi có thể thử tiếp |

### Chỉ số nên theo dõi một cách tỉnh táo

- **Cycle time:** Lát cắt mất bao lâu từ bắt đầu đến Done? Có chờ review hoặc kiểm thử?
- **Work item age:** Việc nào đang già đi vì yêu cầu chưa rõ hoặc cấu trúc khó sửa?
- **Lỗi hồi quy và lỗi thoát ra sản xuất:** Thiết kế/test có giữ an toàn khi thay đổi không?
- **Thời gian từ ý tưởng đến phản hồi người dùng:** Có xác minh đúng nhu cầu đủ sớm không?
- **Số lần làm lại do hiểu sai yêu cầu:** Đối thoại và ví dụ có hiệu quả hơn không?

Không dùng **số class ít hơn**, **số dòng code giảm** hoặc **story point tăng** như bằng chứng tự động của thiết kế tốt. Chúng chỉ là số liệu kỹ thuật cần ngữ cảnh; **giá trị và chất lượng thực tế** mới là trọng tâm.

## 21. Sai lầm thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| **“Càng ít code càng đơn giản.”** | Code khó đọc, khó test, nhiều điều kiện ẩn. | Ưu tiên bộc lộ ý định, cấu trúc nhỏ và trách nhiệm rõ. |
| **“YAGNI nghĩa là bỏ qua lỗi biên.”** | Lộ dữ liệu, mất tiến độ hoặc sai giao dịch. | Giữ yêu cầu an toàn và chất lượng đã biết ở mọi lát cắt. |
| **“Phải có interface cho mọi class.”** | Tăng số loại và khả năng cấu hình chưa có người dùng. | Chỉ tạo boundary khi có hợp đồng/biến thể/rủi ro hiện tại. |
| **“Không cần refactor vì đã chọn Simple Design.”** | Cấu trúc đơn giản ban đầu trở thành đống vá sau thay đổi. | Refactor nhỏ, có test, khi nhu cầu được hiểu thêm. |
| **“Trùng vài dòng là phải tạo thư viện chung.”** | Gộp các quy tắc khác nghĩa và tạo phụ thuộc sai. | Tìm trùng lặp **tri thức** chứ không chỉ cú pháp. |
| **“Unit test xanh là đã Done.”** | Bỏ sót tích hợp, quyền truy cập và hành vi người dùng. | Kết hợp acceptance criteria, integration test và DoD. |
| **“Thiết kế mọi loại nội dung từ hôm nay.”** | Mất thời gian, tăng cấu trúc không có giá trị xác nhận. | Chia lát cắt, thử nhu cầu rồi mở rộng. |
| **“Đã ghi nhận nhu cầu tương lai thì phải triển khai sẵn.”** | Backlog bị biến thành hệ thống cấu hình khổng lồ. | Ghi giả định, chỉ nghiên cứu sớm điều khó đảo ngược. |
| **“Refactor là lúc đổi luôn quy tắc nghiệp vụ.”** | Khó phân biệt lỗi hồi quy với thay đổi chức năng. | Tách thay đổi hành vi và xác nhận tiêu chí riêng. |
| **“Thiết kế đơn giản nghĩa là không cần tài liệu.”** | Quyết định quan trọng và phụ thuộc không minh bạch. | Ghi ngắn gọn ranh giới, giả định, hợp đồng và lý do cần thiết. |
| **“Cứ đợi user phàn nàn rồi mới nghĩ bảo mật.”** | Hậu quả dữ liệu có thể không thể khắc phục. | Xử lý ràng buộc bảo mật/tuân thủ từ đầu. |
| **“Simple Design là quy tắc bất biến.”** | Đội cố giữ cấu trúc cũ dù nhu cầu mới đã rõ. | Tiến hóa thiết kế bằng test, refactor và phản hồi. |

## 22. Bài tập thực hành

### Bài tập 1 — Chọn thiết kế đơn giản hơn

Story: “Học viên có thể mở bài học hợp lệ gần nhất khi đăng nhập.”

Nhóm có hai đề xuất:

- **A:** Xây plugin framework cho nhiều nhà cung cấp dữ liệu tiến độ, video offline, gợi ý bài và AI.
- **B:** Sử dụng API hiện có, kiểm tra quyền phía server, chọn bài hợp lệ mới nhất và viết test cho các ca đã xác nhận.

**Yêu cầu:** Chọn phương án ban đầu phù hợp với những dữ kiện đã có, giải thích khi nào A hoặc một phần của A có thể trở nên hợp lý.

**Gợi ý:** Dựa vào nhu cầu hiện tại và rủi ro khó đảo ngược, không chỉ dựa vào số lượng lớp.

### Bài tập 2 — Nhận diện YAGNI và rủi ro không được hoãn

Hãy phân loại các đề xuất sau thành **cần ngay**, **cần xác minh trước**, hoặc **có thể hoãn**:

1. Kiểm tra tài khoản đang đăng nhập có quyền đọc tiến độ.
2. Hỗ trợ đồng bộ offline cho năm loại nội dung chưa có người dùng.
3. Kiểm tra cách API hiện tại xử lý dữ liệu trùng.
4. Tạo factory chọn một trong bảy database chưa có kế hoạch dùng.
5. Bổ sung kiểm thử không lộ dữ liệu tài khoản khác.
6. Khảo sát migration khi schema sản xuất sắp phải đổi theo hợp đồng.

**Gợi ý:** (1), (5) thuộc điều kiện an toàn hiện tại; (3), (6) có thể cần xác minh sớm; (2), (4) thường có thể hoãn nếu chưa có ràng buộc thật.

### Bài tập 3 — Áp dụng bốn quy tắc Simple Design

Giả sử một hàm Java dài 150 dòng:

- Gọi API lấy tiến độ, kiểm tra quyền, sắp xếp, tạo thông báo và ghi log.
- Có hai đoạn kiểm tra quyền giống nhau nhưng một đoạn thiếu điều kiện tenant.
- Biến được đặt tên **a**, **b**, **x**.
- Có ba interface chỉ có một implementation, chưa có biến thể thật.
- Test chỉ bao phủ một luồng happy path.

**Yêu cầu:** Đề xuất thứ tự cải tiến có kiểm soát theo các ý **test đạt, rõ ý định, tránh trùng lặp và bỏ cấu trúc chưa cần**. Chỉ rõ thay đổi nào là refactor và thay đổi nào đòi xác nhận nghiệp vụ/bảo mật.

**Gợi ý:** Cần xử lý rủi ro tenant và bổ sung test trước; không tái cấu trúc lớn khi chưa có bằng chứng hành vi.

### Bài tập 4 — Viết kiểm thử TDD trước

Với **ResumeSelector** trong bài, viết thêm ít nhất ba test cho:

- Có tiến độ mới hơn thuộc tài khoản khác.
- Khóa mới nhất đã hết quyền truy cập.
- Danh sách bản ghi trống.

**Yêu cầu nâng cao:** Đưa ra một ví dụ hai bản ghi **cùng thời điểm** và mô tả **câu hỏi nghiệp vụ cần làm rõ** trước khi chọn luật xử lý. Không tự thêm quy tắc ngẫu nhiên rồi coi là đúng yêu cầu.

### Bài tập 5 — Phân biệt refactor với thay đổi hành vi

Cho các thao tác:

A. Đổi tên hàm để rõ ý định, không đổi logic.

B. Chuyển từ chọn theo **savedAt** sang chọn theo **lessonId**.

C. Tách điều kiện lọc quyền thành hàm dùng chung, có test giữ nguyên hành vi.

D. Thêm xử lý xung đột cho hai thiết bị theo chính sách mới.

E. Xóa một interface không còn dùng, bảo đảm code gọi vẫn giữ nguyên hành vi.

**Yêu cầu:** Phân loại refactor hay thay đổi chức năng và nêu kiểm thử cần thiết.

**Gợi ý:** A, C, E có thể là refactor; B, D là thay đổi hành vi. Việc “có thể” phụ thuộc việc không vô tình đổi contract hoặc chính sách bảo mật.

### Bài tập 6 — Thiết kế cho tương lai nhưng không dự đoán quá mức

Hệ thống hiện chỉ hỗ trợ bài video. Tổ chức **đã ký hợp đồng** sẽ mở PDF và podcast trong một giai đoạn tới, nhưng quy tắc lưu tiến độ của từng loại chưa rõ.

**Yêu cầu:** Đề xuất việc cần nghiên cứu bây giờ, ranh giới kiến trúc nào đáng chuẩn bị và những phần nào nên đợi khi có ví dụ nghiệp vụ. Nêu ít nhất một quyết định **khó đảo ngược** và cách kiểm chứng.

**Gợi ý:** Có thể cần xem schema và contract về loại nội dung, nhưng chưa cần xây một rule engine đầy đủ nếu chưa biết các chính sách. Đặt timebox cho spike thay vì làm “framework tương lai” vô hạn.

### Bài tập 7 — Kiểm chứng bằng Increment thực

Hai đội cùng triển khai user story “Tiếp tục học”:

- Đội A có 12 lớp abstraction và 30 unit test nhưng chưa có luồng UI–API–dữ liệu chạy cùng nhau.
- Đội B có ít lớp hơn, test nghiệp vụ, kiểm thử phân quyền, CI đạt và luồng tích hợp đáp ứng DoD.

**Yêu cầu:** Nêu điều gì có thể kết luận và điều gì **chưa thể** kết luận về thiết kế dài hạn của hai đội. Đề xuất phản hồi cần lấy từ người dùng và tín hiệu kỹ thuật cần theo dõi.

**Gợi ý:** Increment usable và đạt DoD là bằng chứng về giá trị hiện tại. Không thể chỉ nhìn số lớp hoặc số test để kết luận toàn bộ khả năng mở rộng tương lai.

## 23. Checklist trước khi chọn thiết kế

Trước khi thêm lớp, interface hoặc một khả năng mới, đội có thể tự hỏi:

- [ ] Chúng ta đã hiểu **người dùng cần kết quả gì** và vì sao?
- [ ] Các ví dụ luồng chính, ngoại lệ và rủi ro trọng yếu đã được xác nhận?
- [ ] Đã phân biệt **yêu cầu hiện tại** với **ý tưởng tương lai** và giả định?
- [ ] Có thể tận dụng thành phần đã tồn tại thay vì tạo tầng mới?
- [ ] Mỗi abstraction/interface đề xuất có **lý do hiện tại** rõ ràng?
- [ ] Code có tên và cấu trúc giúp người khác hiểu ý định?
- [ ] Có trùng lặp **quy tắc nghiệp vụ** đáng loại bỏ không?
- [ ] Có đang gộp những quy tắc chỉ **giống cú pháp nhưng khác ý nghĩa** không?
- [ ] Thiết kế có thể được kiểm chứng bằng test và Increment tích hợp?
- [ ] Có ràng buộc bảo mật, quyền riêng tư, tính toàn vẹn dữ liệu, hiệu năng hoặc vận hành không được hoãn?
- [ ] Một quyết định khó đảo ngược có cần được khám phá trước khi bắt đầu code?
- [ ] Có cách refactor an toàn khi nhu cầu mới được xác nhận?
- [ ] TDD, CI, code review và phản hồi người dùng được áp dụng ở mức phù hợp?
- [ ] Thiết kế không tạo thêm quá nhiều tùy chọn hoặc điểm mở rộng chưa có người dùng?
- [ ] Có đang chọn **giải pháp nhỏ nhất đáp ứng hiện tại**, không phải chỉ ít ký tự nhất?
- [ ] Khi có thay đổi, nhóm có thể giải thích lý do và cập nhật cấu trúc thay vì chỉ thêm bản vá?

Checklist là công cụ thảo luận, không phải một cổng phê duyệt hình thức bắt buộc. Một thay đổi rất nhỏ có thể không cần hồ sơ kiến trúc; một migration dữ liệu lớn cần bằng chứng và kế hoạch an toàn chi tiết hơn.

## 24. Tổng kết

- **Simple Design trong XP** là thiết kế nhỏ, rõ ràng và đúng với **nhu cầu, rủi ro và chất lượng đã được hiểu**, đồng thời giữ khả năng phát triển khi có thông tin mới.
- **YAGNI** chống xây chức năng/abstraction vì dự đoán tương lai, **không chống** bảo mật, kiểm thử, dữ liệu chính xác hoặc ràng buộc bắt buộc hiện tại.
- **Bốn quy tắc tư duy hữu ích:** các test cần thiết đạt; code thể hiện ý định; loại bỏ trùng lặp tri thức; không có thành phần dư thừa.
- **TDD và refactoring** giúp code phát triển từ hành vi đã xác nhận qua những bước nhỏ; CI và kiểm thử tích hợp bảo vệ toàn bộ Increment.
- **Tránh cả overengineering lẫn underengineering:** Một framework khổng lồ chưa cần và một đoạn code ngắn nhưng lộ dữ liệu đều không phải thiết kế đơn giản tốt.
- **Thiết kế theo lát cắt giá trị:** Xây luồng dùng được, đáp ứng DoD, nhận phản hồi sớm rồi tiếp tục mở rộng khi nhu cầu thật sự xuất hiện.
- **Quyết định khó đảo ngược cần được đánh giá sớm**, nhất là schema, bảo mật, quyền riêng tư, API công khai và nghĩa vụ tuân thủ.
- **Giá trị của thiết kế thể hiện ở khả năng thay đổi an toàn và giao sản phẩm có ích**, không phải số lớp, số dòng code hay số lần nói “YAGNI”.

Khi phải chọn giữa một kiến trúc tổng quát cho hàng chục kịch bản tương lai và một thiết kế nhỏ cho lát cắt đang làm, hãy hỏi: **“Điều gì đã được xác nhận, điều gì chưa biết, và thiết kế nào ít phức tạp nhất mà vẫn giúp chúng ta giao giá trị an toàn và thay đổi được khi học thêm?”**
