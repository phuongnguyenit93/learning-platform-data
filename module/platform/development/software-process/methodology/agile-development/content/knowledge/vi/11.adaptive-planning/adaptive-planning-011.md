# Duy trì khả năng dự đoán mà không cố định mọi chi tiết từ đầu

Một nhóm phát triển được yêu cầu trả lời: **“Khi nào nền tảng học trực tuyến có thể ra mắt tính năng đăng ký khóa học mới?”** Người quản lý muốn có thời điểm để phối hợp truyền thông, hỗ trợ và vận hành. Nếu đội trả lời “Agile nên không cần kế hoạch”, các bên khó chuẩn bị. Nhưng nếu đội hứa ngay một ngày chính xác và danh sách 40 tính năng chưa được làm rõ, kế hoạch dễ trở thành một chuỗi cam kết không có căn cứ: khi phát hiện khó khăn về thanh toán, quyền truy cập hoặc nhu cầu học viên, đội sẽ phải lựa chọn giữa che giấu rủi ro, giảm chất lượng hoặc lỡ hẹn.

**Kế hoạch thích ứng** đưa ra một lựa chọn khác: giữ **mục tiêu, ranh giới, nhịp kiểm tra và cách dự báo minh bạch**, trong khi cho phép thay đổi những chi tiết chưa đủ bằng chứng. Đội lập kế hoạch đủ để phối hợp và ra quyết định, xây sản phẩm theo từng phần có thể sử dụng, so sánh dự báo với kết quả thực tế và cập nhật lựa chọn khi xuất hiện thông tin mới.

Trong module **AGILE_DEVELOPMENT**, cách tư duy này kết nối trực tiếp với giá trị và nguyên tắc Agile: ưu tiên phản hồi sớm, giao phần mềm tăng dần và cải tiến liên tục. User story và Product Backlog giúp thể hiện những lựa chọn có thể điều chỉnh; Scrum dùng Product Goal, Sprint Goal, Increment và các nhịp kiểm tra; Kanban dùng dữ liệu dòng công việc để dự báo; XP và các thực hành kỹ thuật giữ khả năng giao phần mềm thường xuyên mà không đánh đổi chất lượng.

> **Thông điệp trọng tâm:** Agile không loại bỏ tính dự đoán. Agile tìm cách tạo **dự báo có căn cứ, đủ hữu ích cho quyết định và được cập nhật khi thực tế thay đổi**, thay vì nhầm một bản kế hoạch chi tiết ban đầu với sự chắc chắn.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **mục tiêu**, **kế hoạch**, **dự báo**, **cam kết**, **phạm vi**, **mốc thời gian** và **độ tin cậy**.
2. Giải thích vì sao việc chi tiết hóa toàn bộ tương lai quá sớm có thể gây tiến độ ảo, trong khi không lập kế hoạch lại gây thiếu phối hợp.
3. Áp dụng **lập kế hoạch cuốn chiếu (rolling-wave planning)**: phần gần đủ chi tiết để thực hiện, phần xa ở mức định hướng và giả thuyết.
4. Xây dựng dự báo ngắn hạn và trung hạn dựa trên mục tiêu, backlog được làm rõ, năng lực thực tế, phụ thuộc, rủi ro và bằng chứng từ Increment.
5. Sử dụng throughput, cycle time, work item age, WIP và Service Level Expectation (SLE) của dòng công việc đúng ngữ cảnh; biết giới hạn của việc dùng velocity hay story point.
6. Giao tiếp dự báo bằng **phạm vi, điều kiện, mức bất định và mốc xem lại**, không hứa một con số chắc chắn từ dữ liệu thiếu.
7. Điều chỉnh thứ tự ưu tiên, phạm vi hoặc thời điểm một cách có trách nhiệm, đồng thời bảo vệ chất lượng, an toàn và các nghĩa vụ bắt buộc.

## 1. Dự đoán không đồng nghĩa với đóng băng kế hoạch

Trong phát triển phần mềm, người liên quan cần dự đoán để lập ngân sách, phối hợp đội khác, chuẩn bị truyền thông, đáp ứng hợp đồng và xử lý rủi ro. Nhu cầu đó là hợp lý. Điều chưa hợp lý là giả định **mọi yêu cầu, phụ thuộc, tốc độ và hành vi người dùng đều đã biết chắc ở thời điểm dự án bắt đầu**.

### 1.1. Sáu khái niệm cần tách riêng

| Khái niệm | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| **Mục tiêu (goal)** | Chúng ta muốn đạt thay đổi có ý nghĩa nào? | Người học có thể tự đăng ký và bắt đầu một khóa học |
| **Phạm vi (scope)** | Những khả năng/hạng mục nào sẽ được bao gồm? | Đăng ký khóa miễn phí, theo dõi trạng thái, thanh toán một phương thức |
| **Kế hoạch (plan)** | Chúng ta định phối hợp và hành động thế nào? | Làm rõ luồng, tạo lát cắt, kiểm chứng tích hợp, phát hành từng phần |
| **Dự báo (forecast)** | Dựa trên thông tin hiện tại, những khả năng nào có thể hoàn tất trong khoảng nào? | Với năng lực và các giả định đã nêu, dự kiến hoàn tất nhóm hạng mục trong một khoảng tuần |
| **Cam kết (commitment)** | Điều gì các bên thực sự nhận trách nhiệm duy trì hoặc đạt theo thỏa thuận? | Không hạ tiêu chuẩn an toàn; kiểm tra tiến triển theo nhịp; trong Scrum duy trì sự tập trung vào Sprint Goal |
| **Bằng chứng tiến triển (evidence)** | Điều gì đã hoạt động, được kiểm tra hoặc quan sát thực tế? | Một Increment đạt Definition of Done và được học viên dùng thử |

Một dự báo là **thông tin hỗ trợ quyết định**, không phải sự bảo đảm chắc chắn. Một cam kết cũng cần rõ **đối tượng của cam kết**. Có sự khác biệt lớn giữa “đội cam kết minh bạch rủi ro, ưu tiên mục tiêu và duy trì chuẩn chất lượng” với “đội bảo đảm hoàn tất mọi tính năng chưa được làm rõ đúng ngày X bất kể điều gì xảy ra”.

### 1.2. Những thứ nên ổn định và những thứ có thể thay đổi

| Thường cần đủ ổn định để phối hợp | Có thể thay đổi khi có thông tin mới |
|---|---|
| Vấn đề người dùng và mục tiêu sản phẩm hiện tại | Chi tiết giao diện, cách tổ chức thao tác |
| Các nghĩa vụ pháp lý, an toàn, bảo mật và chất lượng bắt buộc | Thứ tự một số Product Backlog Items |
| Vai trò, quyền ra quyết định và cơ chế phối hợp | Phương án kỹ thuật chưa được kiểm chứng |
| Mốc bắt buộc hoặc giới hạn ngân sách **nếu có thật** | Phạm vi các khả năng chưa thiết yếu |
| Nhịp xem lại dự báo và quy tắc công khai rủi ro | Số lượng tính năng trong một bản phát hành |
| Định nghĩa một kết quả được coi là đã kiểm chứng | Giả thuyết và cách đo khi phát hiện bất cập |

Không phải mục tiêu sản phẩm bất biến. Khi dữ liệu cho thấy mục tiêu ban đầu không còn đúng, Product Owner và những người có thẩm quyền cần đánh giá lại. Tuy nhiên, **đổi mục tiêu mỗi ngày** sẽ phá vỡ khả năng tập trung không kém việc cố định mọi chi tiết ngay từ đầu.

### 1.3. Vì sao một kế hoạch “rất chi tiết” có thể ít đáng tin?

Một lịch trình nêu “ngày 3 viết toàn bộ API, ngày 8 hoàn thành UI, ngày 12 kiểm thử, ngày 15 phát hành” trông chính xác. Nhưng độ chi tiết không tạo thêm kiến thức nếu nhóm chưa biết API đối tác có khả dụng, bộ dữ liệu có hợp lệ, và người dùng có cần chính luồng đã thiết kế hay không.

Khi thông tin đầu vào thiếu, lịch trình chính xác đến từng ngày chỉ biểu đạt **một giả định chưa được công bố**. Một bản dự báo có khoảng, kèm rủi ro và mốc kiểm tra, thường hữu ích hơn cho việc đưa ra quyết định.

Điểm quan trọng không phải tránh mọi lịch trình: việc đặt lịch triển khai, kiểm thử, phối hợp đào tạo có thể rất cụ thể khi thời điểm gần và bằng chứng đã đủ. **Độ chi tiết nên tăng theo độ gần và mức chắc chắn**, không tăng đồng đều cho mọi tháng trong tương lai.

## 2. Bất định là điều cần quản lý, không phải điều cần che giấu

Khi phát triển sản phẩm, có nhiều loại câu hỏi chưa được trả lời:

- **Nhu cầu:** Người dùng thực sự cần hành vi nào? Giải pháp dự kiến có giúp họ không?
- **Phạm vi nghiệp vụ:** Trường hợp nào bắt buộc, trường hợp nào là cải tiến để sau?
- **Kỹ thuật:** Kiến trúc, thư viện, hiệu năng hoặc tích hợp có đáp ứng được không?
- **Dữ liệu:** Chất lượng, quyền sở hữu và khả năng chuyển đổi dữ liệu hiện tại ra sao?
- **Phụ thuộc:** Đội khác, nhà cung cấp, phê duyệt hoặc môi trường thử có sẵn đúng thời điểm không?
- **Năng lực:** Nhóm có bao nhiêu thời gian thực tế sau hỗ trợ sản xuất, nghỉ phép, bảo trì và xử lý sự cố?
- **Vận hành:** Có thể triển khai, quan sát, khôi phục và hỗ trợ phần mềm an toàn không?
- **Bối cảnh:** Quy định, thị trường, người dùng và ưu tiên tổ chức có đang thay đổi không?

Đội không nhất thiết phải loại bỏ toàn bộ bất định trước khi làm. **Đội cần phát hiện bất định đủ sớm để chọn bước giảm rủi ro có hiệu quả.**

### 2.1. Ba phản ứng khác nhau với bất định

| Tình huống | Phản ứng phù hợp | Ví dụ |
|---|---|---|
| Một điều chưa rõ có thể hỏi và quyết định nhanh | Làm rõ với người có kiến thức hoặc quyền quyết định | Chính sách hết hạn của liên kết xác minh |
| Chưa rõ do vấn đề có quá nhiều trường hợp | Chia phạm vi và chọn lát cắt nhỏ | Hỗ trợ ghi danh khóa miễn phí trước nhiều phương thức trả phí, nếu đúng nhu cầu |
| Chưa rõ do rủi ro kỹ thuật hoặc thị trường | Làm thử nghiệm có thời hạn và tiêu chí học tập | Spike tích hợp sandbox của cổng thanh toán; quan sát người dùng với prototype |

Một **spike** có thể giảm bất định nhưng không tự động là Increment sản phẩm đạt Definition of Done. Nếu chỉ kiểm tra API sandbox, đừng báo rằng toàn bộ thanh toán thực tế đã sẵn sàng.

### 2.2. Rủi ro phải gắn với tác động và quyết định

Thay vì ghi “rủi ro tích hợp: cao”, hãy ghi:

> **Giả định:** Đối tác thanh toán gửi trạng thái giao dịch đủ tin cậy để cấp quyền truy cập.  
> **Điều chưa rõ:** Cách đối tác xử lý callback lặp và giao dịch đang chờ.  
> **Hệ quả:** Không thể khẳng định trạng thái thanh toán hoặc dự báo hoàn tất luồng trả phí.  
> **Hành động:** Thử nghiệm sandbox có thời hạn, kiểm tra idempotency và trường hợp lỗi.  
> **Mốc xem lại:** Sau khi có kết quả thử nghiệm và quyết định tích hợp.

Rủi ro được diễn đạt như vậy giúp quyết định nên **làm rõ, điều chỉnh phạm vi, tạo phương án thay thế hay cập nhật dự báo**.

## 3. Lập kế hoạch cuốn chiếu: gần chi tiết, xa linh hoạt

**Rolling-wave planning** là cách lập kế hoạch theo nhiều chân trời. Những việc gần và tương đối chắc chắn được mô tả đủ để thực hiện; những việc xa chỉ giữ mục tiêu, khả năng mong muốn, phụ thuộc và giả thuyết. Khi thời gian trôi và có bằng chứng mới, nhóm làm rõ dần phần tiếp theo.

~~~mermaid
flowchart LR
    A["Định hướng sản phẩm\nMục tiêu và giả thuyết"] --> B["Kế hoạch trung hạn\nKhả năng và mốc kiểm tra"]
    B --> C["Kế hoạch gần\nBacklog đã làm rõ"]
    C --> D["Thực hiện, kiểm thử\nIncrement đạt chất lượng"]
    D --> E["Phản hồi và dữ liệu\nTiến triển thực"]
    E -. "Cập nhật ưu tiên, dự báo" .-> B
    E -. "Điều chỉnh Product Backlog" .-> C
    E -. "Kiểm chứng giả thuyết" .-> A
~~~

### 3.1. Ba chân trời minh họa

| Chân trời | Nội dung nên rõ | Nội dung có thể để mở | Cách kiểm tra |
|---|---|---|---|
| **Gần: vài ngày đến một Sprint hoặc một chu kỳ kéo việc** | Mục tiêu trước mắt, lát cắt có thể hoàn tất, AC, DoD, phụ thuộc cần xử lý, cách kiểm chứng | Chi tiết kỹ thuật chỉ được biết trong khi làm; kế hoạch tác vụ có thể điều chỉnh | Daily Scrum/kiểm tra luồng, kiểm thử, Increment |
| **Trung hạn: nhiều Sprint hoặc một số tuần tới** | Các khả năng ưu tiên, rủi ro, dự báo phạm vi/thời điểm, mốc phối hợp | Thứ tự chính xác và chi tiết của các khả năng chưa được làm rõ | Review sản phẩm, dữ liệu throughput/cycle time, xem lại roadmap |
| **Xa: một quý hoặc hơn tùy sản phẩm** | Kết quả mong muốn, các hướng đầu tư, ràng buộc và giả thuyết cần kiểm chứng | Danh sách tính năng đầy đủ, ước lượng chính xác, thiết kế kỹ thuật chi tiết | Mốc kiểm tra chiến lược, kết quả sử dụng và thông tin thị trường |

Các khoảng thời gian trên **chỉ để minh họa**. Một hệ thống có chu kỳ kiểm định dài có thể cần chân trời gần khác đội triển khai web hằng ngày. Không được nhầm “kế hoạch xa ở mức tổng quan” với “không phối hợp các phụ thuộc dài hạn”. Những nghĩa vụ hoặc phụ thuộc có thời gian chuẩn bị dài phải được nhận diện sớm.

### 3.2. Chỉ làm rõ sâu những hạng mục có khả năng được chọn

Product Backlog có thể chứa:

1. Một số hạng mục ở gần đã có user story, AC, phụ thuộc và cách kiểm chứng.
2. Những khả năng trung hạn mới có mô tả vấn đề, giá trị, độ lớn sơ bộ và rủi ro.
3. Các ý tưởng xa chỉ có giả thuyết, chưa cần đặc tả mọi trường hợp biên.

Càng gần thời điểm chọn thực hiện, đội càng cần xác định hành vi, phân nhỏ theo **lát cắt dọc** và xem khả năng đạt DoD. Khi ưu tiên thay đổi, những ý tưởng chưa được đầu tư phân tích quá nhiều ít gây lãng phí hơn.

### 3.3. Một roadmap định hướng theo kết quả thay vì khóa danh sách tính năng

| Giai đoạn minh họa | Kết quả/khả năng cần đạt | Điều hiện được dự kiến | Điều còn mở |
|---|---|---|---|
| **Hiện tại** | Học viên đăng ký khóa miễn phí và vào bài đầu tiên được | Hoàn thiện luồng end-to-end và kiểm thử phân quyền | Những cải tiến giao diện nhỏ theo phản hồi |
| **Tiếp theo** | Học viên trả phí nhìn thấy trạng thái giao dịch rõ, đúng và an toàn | Tích hợp một phương thức thanh toán và xử lý trạng thái thiết yếu | Phương thức tiếp theo; cách trình bày các trường hợp hiếm |
| **Về sau** | Người học tự giải quyết các tình huống đăng ký phức tạp | Nghiên cứu hoàn tiền, điều chỉnh đăng ký, hỗ trợ tự phục vụ | Giải pháp và thứ tự cụ thể phụ thuộc dữ liệu sử dụng |

Roadmap này giúp người liên quan biết **hướng đi và điểm cần phối hợp**, nhưng tránh ngụ ý rằng mọi tính năng xa đã được cam kết vào một ngày nhất định. Khi một mốc thời gian là bắt buộc, phải nêu rõ đó là **ràng buộc**, rồi đánh giá phạm vi khả thi và rủi ro tương ứng.

## 4. Từ đầu ra và mục tiêu đến một kế hoạch có thể kiểm chứng

Một đội có thể dự báo rất chính xác về số ticket đóng nhưng vẫn không biết người dùng đã làm được gì. Vì thế, kế hoạch cần nối hai dạng bằng chứng:

- **Đầu ra / năng lực hoàn tất:** Increment thực sự đạt DoD, có thể kiểm tra, sử dụng và tích hợp.
- **Kết quả / outcome:** người dùng có thực sự hoàn thành công việc tốt hơn sau khi phần mềm được đưa vào bối cảnh phù hợp không?

Ví dụ: nhóm muốn giảm khó khăn khi người dùng mới bắt đầu học. Đội chọn lát cắt “học viên truy cập được bài đầu sau đăng ký”, rồi theo dõi tỷ lệ người học tự bắt đầu được. Nếu chức năng hoạt động đúng nhưng người dùng vẫn không tìm thấy bài, nhóm có bằng chứng để đổi ưu tiên; một kế hoạch đã cố định mọi màn hình từ đầu sẽ làm việc điều chỉnh tốn kém hơn.

### 4.1. Mục tiêu và lựa chọn trong Scrum

Trong Scrum, ba commitment gắn với các artifact:

| Artifact | Commitment | Vai trò với lập kế hoạch thích ứng |
|---|---|---|
| **Product Backlog** | **Product Goal** | Định hướng dài hạn cho lựa chọn sản phẩm và thứ tự backlog |
| **Sprint Backlog** | **Sprint Goal** | Giữ một mục tiêu chung của Sprint khi Developers điều chỉnh kế hoạch triển khai |
| **Increment** | **Definition of Done** | Đảm bảo phần hoàn tất đạt tiêu chuẩn chất lượng và có thể kiểm tra |

**Sprint Goal không phải danh sách ticket bất biến.** Trong Sprint Planning, Scrum Team xác định Sprint Goal, Developers lựa chọn các Product Backlog Items và xây kế hoạch. Khi có thông tin mới, Developers có thể điều chỉnh Sprint Backlog, trao đổi và thương lượng phạm vi với Product Owner khi phù hợp, trong khi vẫn giữ sự tập trung vào Sprint Goal và không hạ DoD.

**Product Goal** không phải lời hứa rằng mọi tính năng trên roadmap sẽ được xây. Product Backlog được tiếp tục làm rõ và sắp xếp khi có thông tin mới; Product Owner chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý backlog hiệu quả.

### 4.2. Sự khác biệt giữa kế hoạch Sprint và dự báo release

| Kế hoạch trong Sprint | Dự báo release/trung hạn |
|---|---|
| Tập trung vào Sprint Goal và khả năng hoàn tất trong Sprint | Tập trung vào những khả năng có thể giao trong một khoảng thời gian và các rủi ro liên quan |
| Developers nắm kế hoạch thực hiện, được điều chỉnh khi học thêm | Cần phối hợp Product Owner, Developers và bên phụ thuộc; chịu ảnh hưởng thông tin mới |
| Có DoD và Increment làm bằng chứng hoàn tất | Dựa trên Increment đã giao, dữ liệu dòng công việc, phạm vi và bất định |
| Không biến mọi task thành lời hứa cố định | Không biến một ngày dự báo thành bảo đảm tuyệt đối khi phạm vi chưa chắc |

Một Sprint Review giúp kiểm tra Increment và trao đổi cách thích ứng. Nó có thể dẫn đến thay đổi Product Backlog hoặc dự báo release; Sprint Review **không phải cổng phê duyệt bắt buộc để phát hành** một Increment đã đạt DoD.

### 4.3. Ngăn kế hoạch biến thành “tiến độ ảo”

Giả sử nhóm báo cáo:

> UI 100%, API 90%, database 100%, kiểm thử tích hợp 20%.

Không có phép trung bình đáng tin nào bảo đảm người dùng đã hoàn tất được một tác vụ cụ thể. Thay vào đó:

> **Đã đạt DoD:** học viên xem được khóa miễn phí và ghi danh thành công.  
> **Đang làm:** trạng thái thanh toán trả phí chưa được xác nhận end-to-end.  
> **Rủi ro:** callback đối tác chưa được kiểm chứng.  
> **Bước kiểm tra tiếp:** thử giao dịch sandbox theo các trường hợp thành công, thất bại và lặp.  
> **Ảnh hưởng tới dự báo:** phần trả phí còn phụ thuộc kết quả tích hợp; phạm vi release sẽ được xem lại sau thử nghiệm.

Thông tin này giúp người liên quan ra quyết định hơn một tỷ lệ hoàn thành gộp từ các bộ phận.

## 5. Điều gì làm dự báo đáng tin hơn?

Một dự báo cần xuất phát từ **bằng chứng, các giả định và định nghĩa rõ về đơn vị công việc**.

### 5.1. Xác định đối tượng dự báo

Trước khi tính toán, hỏi:

- Dự báo **một item**, **một nhóm khả năng**, hay **một mục tiêu sản phẩm**?
- “Hoàn tất” nghĩa là đạt DoD, triển khai lên staging, phát hành có kiểm soát hay đạt kết quả sử dụng?
- Phạm vi có bao nhiêu item và đã được phân nhỏ đến mức tương đối đồng nhất chưa?
- Dữ liệu lịch sử có cùng loại công việc, cùng định nghĩa điểm bắt đầu/kết thúc và quy trình không?
- Năng lực đội và những phụ thuộc lớn có tương đồng với giai đoạn trước không?

Không thể dùng tốc độ đóng ticket của một đội làm lời hứa cho nhóm khác khi cách chia công việc và bối cảnh khác nhau.

### 5.2. Dùng lịch sử thực tế, không chỉ kỳ vọng năng lực

Hãy nhìn **phần mềm thực sự hoàn tất** qua nhiều chu kỳ, không chỉ số giờ làm dự kiến hay story point được đăng ký ban đầu. Một đội có thể làm việc nhiều nhưng thường xuyên đợi phê duyệt; năng lực khả dụng để giao Increment vì vậy thấp hơn tổng giờ lao động.

Điều cần xem:

1. Số lượng item tương đối so sánh được đã hoàn tất theo các kỳ.
2. Thời gian từ khi item bắt đầu đến khi hoàn tất.
3. Mức WIP và thời gian item đang mở.
4. Công việc ngoài kế hoạch: hỗ trợ sản xuất, lỗi khẩn, trực vận hành.
5. Biến động nhân sự, công nghệ, ràng buộc hoặc cách chia item.
6. Mức độ ảnh hưởng của sự cố và chất lượng sau phát hành.

### 5.3. Công khai giả định của dự báo

Ví dụ:

> “Dự báo này dựa trên những item đã được chia nhỏ tương tự các item hoàn tất sáu tuần gần nhất. Nó giả định đội giữ tương đối cùng năng lực, không xuất hiện một tích hợp chưa có môi trường thử và các kiểm soát chất lượng không thay đổi. Chúng ta sẽ cập nhật khi kiểm tra được thanh toán sandbox.”

Nếu một giả định trọng yếu mất hiệu lực, dự báo phải được xem lại. **Việc cập nhật dự báo sau bằng chứng mới là một hành động đúng**, không phải tự động là thất bại của quá trình lập kế hoạch.

## 6. Kanban và các thước đo dòng công việc hỗ trợ dự báo

Kanban giúp nhìn công việc như một hệ thống có trạng thái, chính sách rõ và giới hạn công việc đang thực hiện (WIP) khi phù hợp. Trong Kanban Guide, những thước đo dòng công việc tối thiểu gồm **WIP, throughput, work item age và cycle time**. Chúng có ý nghĩa khác nhau.

| Chỉ số | Ý nghĩa | Dùng để quyết định gì? | Nguy cơ hiểu sai |
|---|---|---|---|
| **WIP — Work in Progress** | Số item đã bắt đầu nhưng chưa hoàn tất tại một thời điểm | Có đang mở quá nhiều việc? Có cần tập trung hoàn tất thay vì bắt đầu thêm? | Giảm WIP đến mức làm luồng không hoạt động; bỏ qua loại công việc |
| **Throughput** | Số item hoàn tất trong một khoảng thời gian | Dự báo lượng công việc một đội/dòng công việc có thể hoàn tất trong các kỳ tiếp theo | Chia ticket nhỏ giả tạo để tăng số lượng; so các item không tương đồng |
| **Cycle time** | Thời gian từ lúc một item bắt đầu đến khi hoàn tất theo định nghĩa workflow | Thấy phân phối thời gian xử lý, hỗ trợ dự báo thời gian hoàn tất item | Báo mỗi giá trị trung bình như một lời hứa; không nêu điểm bắt đầu/kết thúc |
| **Work item age** | Thời gian một item hiện tại đã ở trong hệ thống kể từ khi bắt đầu | Phát hiện việc mở quá lâu, hỗ trợ xử lý nguy cơ trễ sớm | Xem item lâu tuổi là lỗi cá nhân thay vì xem điểm chặn |

Ngoài ra, một số đội theo dõi **lead time** từ lúc yêu cầu được tiếp nhận đến lúc có kết quả, giúp nhìn cả thời gian chờ trước khi bắt đầu. Thuật ngữ phải gắn với điểm đo đã thống nhất; đừng trộn lead time với cycle time rồi so sánh mà không giải thích.

### 6.1. Ví dụ dự báo bằng throughput

Giả sử một nhóm duy trì luồng công việc tương đối ổn định, các item được chia nhỏ theo chuẩn nhất quán và trong sáu tuần trước đã hoàn tất:

| Tuần | Item đạt chính sách hoàn tất |
|---|---:|
| 1 | 4 |
| 2 | 5 |
| 3 | 3 |
| 4 | 6 |
| 5 | 4 |
| 6 | 5 |
| **Tổng** | **27** |

Throughput trung bình của ví dụ này:

\[
\frac{27 \text{ item}}{6 \text{ tuần}} = 4{,}5 \text{ item/tuần}
\]

Nếu backlog của một nhóm khả năng cần dự báo còn **24 item tương đối so sánh được**, phép chia đơn giản là:

\[
\frac{24}{4{,}5} \approx 5{,}33 \text{ tuần}
\]

Con số **5,33 tuần không phải lời hứa hoặc một khoảng tin cậy thống kê**. Nó chỉ là một ước tính thô từ trung bình lịch sử. Nếu tương lai có tuần tương tự mức 3 item, 24 item sẽ cần khoảng 8 tuần; nếu đều tương tự mức 6 item, khoảng 4 tuần. **4–8 tuần ở đây là kịch bản minh họa dựa trên các tốc độ đã quan sát, không phải khoảng xác suất đã được chứng minh.**

Đặc biệt cần xem:

- 24 item có cùng cách chia với dữ liệu lịch sử không?
- Các item thanh toán mới có rủi ro lớn hơn các item UI cũ không?
- Có công việc khẩn hoặc phụ thuộc ngoài làm thay đổi throughput không?
- Một phần item có thể bị loại khỏi phạm vi sau phản hồi không?
- Tất cả item được tính là hoàn tất khi đạt chính sách chất lượng nhất quán chứ?

Nếu những điều kiện khác biệt đáng kể, hãy phân loại công việc hoặc cập nhật mô hình thay vì dự báo bằng một trung bình duy nhất.

### 6.2. Dự báo theo kịch bản thay vì một ngày duy nhất

Một bản báo cáo có thể trình bày:

| Kịch bản | Giả định minh họa | 24 item sẽ mất khoảng bao lâu? |
|---|---|---|
| **Dòng công việc thuận lợi** | Năng lực ổn định ở mức 6 item/tuần | Khoảng 4 tuần |
| **Tham chiếu theo trung bình lịch sử** | Trung bình 4,5 item/tuần | Khoảng 5–6 tuần |
| **Dòng công việc bị hạn chế** | Năng lực chỉ ở mức 3 item/tuần | Khoảng 8 tuần |

Các kịch bản này không đại diện cho xác suất “chắc chắn” hoặc “85%”. Chúng chỉ cho phép trao đổi rủi ro: để chuẩn bị triển khai trong năm tuần, đội cần giảm phạm vi, tháo phụ thuộc, tăng khả năng hoàn tất hoặc chấp nhận rủi ro lịch trình cao hơn? Quyết định thuộc người có thẩm quyền sau khi hiểu các giả định.

### 6.3. Dự báo xác suất khi có dữ liệu phù hợp

Nếu có nhiều mẫu lịch sử tương đối ổn định, một đội có thể sử dụng **mô phỏng Monte Carlo**: lấy mẫu throughput từ phân phối lịch sử, cộng dồn các tuần giả lập tới khi đủ số item, lặp lại nhiều lần để thu được phân phối thời gian hoàn tất.

Pseudocode minh họa:

~~~text
historical_weekly_throughput = [4, 5, 3, 6, 4, 5]
remaining_items = 24
trial_results = []

repeat many_trials:
    done = 0
    weeks = 0

    while done < remaining_items:
        sample = randomly_select_from(historical_weekly_throughput)
        done = done + sample
        weeks = weeks + 1

    trial_results.append(weeks)

summarize_percentiles(trial_results)
report_assumptions_and_date_of_next_update()
~~~

Đây là **pseudocode mô tả ý tưởng**, không phải một mô hình đã được hiệu chỉnh và không có kết quả xác suất cụ thể được tính trong bài. Việc lấy mẫu lịch sử giả định dữ liệu đại diện cho tương lai và các tuần có thể mô phỏng theo cách đó. Với chỉ sáu tuần dữ liệu, kết quả có thể rất thiếu ổn định. Mô phỏng không tự giải quyết phụ thuộc chưa kiểm chứng, backlog không đồng nhất, thay đổi quy trình hoặc những sự kiện hiếm có tác động lớn.

Nếu sử dụng mức phân vị, phải trình bày đúng:

> “Theo mô hình và giả định hiện tại, khoảng N tuần là mốc mà mô phỏng cho thấy X% kịch bản hoàn tất trong hoặc trước đó.”

Không nên diễn đạt nó thành “chắc chắn sẽ hoàn tất” hoặc che giấu giả định đầu vào. Khi dữ liệu không đủ, **dự báo theo kịch bản, khoảng rộng và mốc xem lại rõ** có thể trung thực hơn.

### 6.4. SLE là kỳ vọng dịch vụ, không phải cam kết mọi item đúng hạn

Một **Service Level Expectation (SLE)** trong Kanban là dự báo về thời gian một item đi qua workflow, thường được thể hiện dưới dạng **khoảng thời gian và xác suất**. Ví dụ minh họa:

> “Theo dữ liệu lịch sử hiện tại, khoảng 85% item thuộc loại được theo dõi hoàn tất trong vòng 8 ngày kể từ khi bắt đầu.”

Đây **không phải chuẩn Kanban bắt buộc** và không phải lời hứa mọi item sẽ hoàn tất trước ngày thứ tám. Con số phải được xác lập từ dữ liệu và định nghĩa workflow của đội. Nếu chỉ một vài item tương đối đồng nhất được quan sát, SLE chưa thể xem là ổn định.

Khi một item đang mở được 7 ngày và gần mốc SLE 8 ngày, nhóm có thể chủ động kiểm tra phụ thuộc, phối hợp gỡ chặn hoặc điều chỉnh dự báo. **Work item age** giúp hành động trước khi việc trễ trở thành sự đã rồi.

### 6.5. Phân biệt dự báo cho một item và một tập item

- **Dự báo một item:** thường nhìn phân phối cycle time, work item age và loại công việc.
- **Dự báo hoàn tất một nhóm item:** thường nhìn throughput, số item còn lại, WIP và các phụ thuộc.
- **Dự báo outcome:** cần thêm dữ liệu sử dụng, thử nghiệm sản phẩm và độ trễ phản hồi; không thể suy ra trực tiếp từ số ticket.

Một nhóm có throughput cao không nhất thiết tạo nhiều giá trị hơn nếu item được chia nhỏ tùy tiện hoặc phát sinh lỗi khiến người dùng không hoàn thành tác vụ.

## 7. Velocity và story point: hỗ trợ đối thoại, không phải thước đo giá trị

Một số Scrum Team dùng **story point** để ước lượng độ lớn tương đối và **velocity** để xem lượng điểm đã hoàn tất trong các Sprint trước. Đây là những thực hành có thể hữu ích, **không phải artifact, metric hoặc commitment bắt buộc của Scrum Guide**.

Ví dụ, nếu một đội thường hoàn tất 18–24 điểm theo cách ước lượng riêng của họ, thông tin đó có thể hỗ trợ thảo luận về phạm vi Sprint tiếp theo. Nhưng:

1. Một điểm của đội A không tương đương một điểm của đội B.
2. Đổi thang điểm hoặc chia item nhỏ hơn có thể thay đổi velocity mà không đổi giá trị.
3. Story point không tự phản ánh thời gian chờ do phụ thuộc.
4. Một Sprint có nhiều sự cố sản xuất có thể làm giảm lượng công việc sản phẩm hoàn tất.
5. Đạt nhiều điểm không chứng minh Increment có ích hoặc outcome đã cải thiện.

**Không dùng velocity làm KPI xếp hạng con người hoặc làm lý do ép đội tăng số điểm qua từng Sprint.** Nếu muốn dự báo, đội cần hiểu cách ước lượng, loại công việc và năng lực thực tế của chính mình. Có thể kết hợp các quan sát về throughput/cycle time để kiểm tra dự báo, nhưng đừng trộn các đơn vị khác nhau như thể chúng tương đương.

## 8. Khi một mốc thời gian thực sự cố định

Không phải mọi ngày phát hành đều linh hoạt. Có những ngày được xác định bởi hợp đồng, sự kiện, kỳ khai giảng, quy định hoặc việc dừng hỗ trợ một hệ thống cũ. Agile không phải lý do bỏ qua những ràng buộc ấy.

### 8.1. Phân biệt “ngày cố định” và “mọi phạm vi cố định”

Giả sử một trường cần mở ghi danh trước ngày khai giảng. Thời điểm là điều kiện có thật. Nhóm có thể đánh giá:

- **Bắt buộc có:** người học có thể ghi danh hợp lệ, xác nhận quyền truy cập và biết trạng thái của mình.
- **Có thể lùi nếu chưa thiết yếu:** bộ gợi ý khóa học nâng cao, giao diện tùy biến sâu, báo cáo phân tích phức tạp.
- **Không được cắt:** kiểm soát bảo mật, tính đúng đắn dữ liệu, các nghĩa vụ và tiêu chuẩn chất lượng bắt buộc.
- **Có thể triển khai giới hạn:** nhóm học viên đầu tiên hoặc một kênh được hỗ trợ, nếu phù hợp pháp lý và khả năng vận hành.

Một ngày cố định có thể dẫn đến **phạm vi tối thiểu có ích và an toàn**, không đồng nghĩa “mọi yêu cầu ban đầu cũng phải cố định”.

### 8.2. Tam giác đánh đổi cần được công khai

| Thành phần | Câu hỏi ra quyết định |
|---|---|
| **Thời điểm** | Có ngày bắt buộc không? Nếu thay đổi, hệ quả hợp đồng/tổ chức là gì? |
| **Phạm vi** | Những khả năng nào tạo ra giá trị cốt lõi, những biến thể nào có thể để sau? |
| **Năng lực và chi phí** | Có thể tăng hỗ trợ hoặc tháo phụ thuộc thế nào mà không gây quá tải? |
| **Chất lượng/an toàn** | Những chuẩn nào không được hạ? |
| **Độ tin cậy** | Dự báo còn bất định nào và mức rủi ro nào được chấp nhận? |

Không nên xem **chất lượng, bảo mật hoặc an toàn** là “nút vặn” để bù trễ tiến độ. Tăng thêm người vào một giai đoạn muộn cũng không bảo đảm nhanh hơn vì cần thời gian phối hợp, onboarding và chia sẻ bối cảnh.

### 8.3. Cách trình bày khi ngày có thể cố định nhưng phạm vi cần thương lượng

> “Chúng ta giữ ngày khai giảng làm mốc điều phối. Phạm vi tối thiểu bắt buộc là đăng ký và vào bài học đầu đúng quyền. Các chức năng báo cáo nâng cao chưa được cam kết vào mốc đó. Dự báo hiện còn phụ thuộc kết quả kiểm chứng thanh toán; chúng ta sẽ xem lại sau mốc tích hợp. DoD và kiểm soát bảo mật không bị giảm.”

Cách trình bày này giúp người có thẩm quyền **thực sự ra quyết định về phạm vi và rủi ro**, thay vì chỉ nhận một lịch trình đẹp nhưng thiếu dữ liệu.

### 8.4. Nếu cả ngày, phạm vi và ngân sách đều bị khóa

Khi ba ràng buộc lớn đều được giữ cứng trong lúc tồn tại bất định đáng kể, đội không thể biến một dự báo thiếu cơ sở thành chắc chắn. Phải công khai các hệ quả có thể xảy ra, thương lượng nguồn lực/phạm vi hoặc thay đổi phương án, đánh giá lại khả năng đáp ứng nghĩa vụ và đề xuất mốc kiểm chứng sớm.

Nếu ràng buộc thực sự không thể thay đổi, cần đưa ra quyết định minh bạch về **khả năng thực hiện và các phương án dự phòng**. Không nên dùng khẩu hiệu “Agile sẽ xử lý được” để thay thế phân tích rủi ro.

## 9. Giảm rủi ro lịch trình bằng giao phần mềm nhỏ và chất lượng cao

Một kế hoạch chỉ dựa vào các nhiệm vụ chưa tích hợp dễ để phần lớn rủi ro tập trung vào cuối. Khi nhóm tạo Increment nhỏ và thường xuyên, những giả định kỹ thuật và nghiệp vụ được kiểm chứng sớm hơn.

### 9.1. Chia theo lát cắt dọc

Thay vì:

~~~text
Tuần 1: Hoàn thành toàn bộ UI
Tuần 2: Hoàn thành toàn bộ API
Tuần 3: Hoàn thành database
Tuần 4: Tích hợp và kiểm thử toàn bộ
~~~

Có thể cân nhắc:

~~~text
Lát cắt 1: Đăng ký khóa miễn phí -> có quyền vào bài đầu
           (UI + API + dữ liệu + kiểm thử)

Lát cắt 2: Xem trạng thái đăng ký và lỗi thiết yếu
           (UI + API + dữ liệu + kiểm thử)

Lát cắt 3: Giao dịch một phương thức thanh toán được hỗ trợ
           (kiểm chứng tích hợp + nghiệp vụ + an toàn)

Lát cắt 4: Mở rộng phương thức và các biến thể có giá trị
           (sau khi học từ các lát cắt trước)
~~~

Phần đầu có thể cung cấp một hành vi sử dụng thực sự, không phải bộ màn hình chỉ demo bằng dữ liệu giả. Những rủi ro bắt buộc của lát cắt hiện tại vẫn phải được xử lý; không “chia nhỏ” bằng cách chuyển kiểm thử bảo mật hoặc lỗi nghiêm trọng sang giai đoạn sau.

### 9.2. XP và năng lực thay đổi an toàn

Những thực hành như tích hợp liên tục, kiểm thử tự động phù hợp, TDD khi có ích, refactoring và phát hành nhỏ giúp giảm nguy cơ mỗi điều chỉnh yêu cầu lại phá vỡ sản phẩm. Đội không cần đợi cuối tháng mới biết một thay đổi có thể tích hợp hay không.

Ví dụ, nếu lỗi xác minh email khiến người dùng không thể đăng ký, một bộ kiểm thử hồi quy hợp lý giúp nhóm sửa nhanh nhưng vẫn kiểm tra rằng liên kết hết hạn, yêu cầu lặp và quyền truy cập không bị sai.

**Năng lực kỹ thuật tốt không tự quyết định giá trị sản phẩm**, nhưng nó giảm chi phí thử nghiệm, nhận phản hồi và thay đổi kế hoạch khi cần.

### 9.3. Chia nhỏ nhưng vẫn giữ tính đúng đắn

Một phần luồng thanh toán không được báo “hoạt động được” khi:

- Trạng thái thành công chỉ được giả lập ở giao diện.
- Quyền học được cấp trước khi có xác nhận đáng tin.
- Callback lặp có thể tạo giao dịch hoặc quyền trùng không hợp lệ.
- Lỗi dịch vụ bị che thành thông báo thành công.
- Dữ liệu tài khoản có thể bị truy cập trái quyền.

Nếu chỉ có prototype hoặc kiểm chứng sandbox, hãy mô tả đúng **bằng chứng và giới hạn**. Dự báo release sản xuất phải dựa trên điều kiện thực sự cần đạt trước khi cung cấp cho người dùng.

## 10. Theo dõi kế hoạch bằng vòng phản hồi và mốc quyết định

Kế hoạch thích ứng cần **cơ chế cập nhật**, không chỉ lời tuyên bố “sẽ linh hoạt”.

~~~mermaid
flowchart TD
    A["Mục tiêu và dự báo hiện tại"] --> B["Chọn lát cắt hoặc thử nghiệm"]
    B --> C["Phát triển, tích hợp, kiểm thử"]
    C --> D["Increment / bằng chứng kiểm chứng"]
    D --> E["Dữ liệu dòng công việc và phản hồi người dùng"]
    E --> F{"Giả định còn đúng?"}
    F -->|Có| G["Cập nhật forecast, tiếp tục ưu tiên"]
    F -->|Không / chưa rõ| H["Xem lại phạm vi, rủi ro hoặc phương án"]
    H --> I["Quyết định mới và mốc kiểm tra"]
    G --> A
    I --> A
~~~

### 10.1. Mỗi lần xem lại cần trả lời câu gì?

1. **Đã thực sự hoàn tất gì?** Increment nào đạt DoD, khả năng nào đang dùng được?
2. **Điều gì mới được học?** Từ người dùng, môi trường kỹ thuật hoặc phụ thuộc?
3. **Giả định của dự báo có đổi không?** Phạm vi, throughput, nhân lực, chất lượng hoặc độ phức tạp?
4. **Độ bất định hiện ở đâu?** Phần nào đáng để thử trước khi tiếp tục dự báo chi tiết?
5. **Có quyết định nào phải đổi?** Thứ tự backlog, lát cắt, mốc kiểm tra, cách triển khai hay chiến lược release?
6. **Ai có quyền quyết định và ai cần biết?** Product Owner, Developers, vận hành, khách hàng, pháp lý, tổ chức?

Một buổi review chỉ có dashboard và không tạo quyết định mới có thể chưa tận dụng được phản hồi. Tuy nhiên, **giữ nguyên kế hoạch có chủ đích sau khi kiểm tra** cũng là một quyết định hợp lệ.

### 10.2. Dự báo thay đổi theo nhịp nào?

Không cần cập nhật mọi giờ khi không có dữ liệu mới. Có thể đặt nhịp:

- **Hằng ngày hoặc theo luồng:** kiểm tra item bị chặn, work item age, WIP và tiến triển hướng tới mục tiêu ngắn hạn.
- **Sau Sprint hoặc chu kỳ phù hợp:** kiểm tra Increment, throughput/cycle time, rủi ro và điều học được.
- **Theo mốc phụ thuộc:** cập nhật ngay khi đối tác phê duyệt, thử tích hợp hoàn tất hoặc rủi ro lớn xuất hiện.
- **Theo nhịp sản phẩm/kinh doanh:** xem lại roadmap, mục tiêu và những thay đổi ảnh hưởng kế hoạch truyền thông, vận hành hoặc hợp đồng.

Nhịp phải phù hợp với tốc độ biến động thông tin. Không cập nhật khi giả định lớn đã thay đổi sẽ khiến dự báo cũ mất giá trị; cập nhật liên tục khi chưa có thông tin mới sẽ chỉ tạo nhiễu.

## 11. Tình huống xuyên suốt: dự báo ra mắt luồng đăng ký khóa học

> **Tình huống và tất cả số liệu trong phần này là giả định để luyện phân tích.** Chúng không phải dữ liệu lịch sử của một đội thực tế, cũng không phải chuẩn hay cam kết cho sản phẩm cụ thể.

Một nền tảng học trực tuyến có kế hoạch mở kỳ học mới trong **8 tuần**. Các bộ phận truyền thông, hỗ trợ và vận hành cần biết phạm vi tính năng đăng ký có thể chuẩn bị. Ban đầu stakeholder yêu cầu **40 hạng mục**: đăng ký khóa miễn phí, nhiều phương thức thanh toán, hóa đơn, mã giảm giá, hoàn tiền, gợi ý khóa học, dashboard quản trị và các tiện ích khác.

### 11.1. Cách lập kế hoạch cố định mọi thứ từ đầu

Nhóm chia 40 item cho tám tuần, nói “mỗi tuần hoàn thành năm item”. Các item chưa đồng nhất: đổi nhãn nút có thể chỉ mất ít thời gian, trong khi thanh toán qua đối tác có nhiều trường hợp và phụ thuộc. Không có bằng chứng đội hoàn tất năm item tương tự mỗi tuần.

Kế hoạch này gặp ba vấn đề:

1. **Dự báo không gắn với năng lực thực tế**, dùng một phép chia đều cho những việc không tương đương.
2. **Phạm vi chứa nhiều yêu cầu chưa làm rõ**, chưa biết những gì là bắt buộc cho ngày khai giảng.
3. **Phụ thuộc thanh toán và phân quyền chưa được kiểm chứng**, có thể làm dồn rủi ro vào cuối kỳ.

Nếu đội bảo vệ con số “40 item” bằng mọi giá, họ có thể chuyển ticket sang Done dù chưa tích hợp hoặc bỏ qua những ràng buộc an toàn. Cách làm đó không tạo tính dự đoán thực.

### 11.2. Cách tiếp cận thích ứng: xác định kết quả tối thiểu

Nhóm làm việc với Product Owner, Developers, QA, vận hành, hỗ trợ và người có thẩm quyền liên quan để xác định:

> **Kết quả tối thiểu cho ngày khai giảng:** học viên đủ điều kiện có thể tự đăng ký một khóa được hỗ trợ, biết trạng thái của mình và truy cập đúng nội dung khi điều kiện ghi danh/thanh toán hợp lệ.

Nhóm chia các khả năng:

| Phân nhóm | Ví dụ | Vai trò trong kế hoạch |
|---|---|---|
| **Bắt buộc theo mục tiêu và an toàn** | Tạo ghi danh đúng quyền, trạng thái rõ, tích hợp tin cậy, xử lý lỗi thiết yếu, kiểm soát bảo mật | Không thể cắt nếu muốn tuyên bố luồng này hoạt động được |
| **Quan trọng nhưng có thể thương lượng phạm vi** | Một số phương thức thanh toán phụ, tìm kiếm nâng cao, báo cáo bổ sung | Chọn theo giá trị và năng lực sau khi kiểm chứng phần cốt lõi |
| **Nên nghiên cứu hoặc thử sớm** | Callback đối tác, cấp quyền sau thanh toán, chất lượng dữ liệu hiện tại | Giảm bất định chi phối dự báo |
| **Có thể để giai đoạn sau** | Dashboard phong phú, gợi ý cá nhân hóa, biến thể hiếm không thiết yếu | Không làm chậm kết quả tối thiểu chỉ vì đã nằm trong danh sách ban đầu |

**Chú ý:** Nếu phương thức thanh toán cụ thể được bắt buộc theo hợp đồng, không thể tùy ý đẩy nó sang “để sau”. Phân loại phải dựa trên ràng buộc thật, không chỉ mong muốn đơn giản hóa.

### 11.3. Lập kế hoạch gần và xa khác nhau

| Khoảng thời gian minh họa | Kế hoạch | Bằng chứng/mốc quyết định |
|---|---|---|
| **Tuần 1–2** | Hoàn tất một lát cắt ghi danh hoặc khảo sát khả năng tích hợp trọng yếu; làm rõ AC, quyền truy cập và DoD | Increment kiểm chứng được hoặc kết quả spike có giới hạn rõ |
| **Tuần 3–4** | Ưu tiên luồng trạng thái đăng ký và tích hợp thanh toán ở phạm vi được lựa chọn | Kết quả thử giao dịch, lỗi lặp, tình huống thất bại, dữ liệu dòng công việc |
| **Tuần 5–6** | Hoàn thiện các khả năng bắt buộc còn thiếu, kiểm thử xuyên suốt, xử lý điểm chặn và chuẩn bị vận hành | Increment có thể sử dụng, kiểm tra an toàn và phương án triển khai |
| **Tuần 7–8** | Dựa trên thực tế, chọn phần mở rộng còn khả thi và phát hành/chuẩn bị hỗ trợ | Dự báo cập nhật, mức sẵn sàng theo mục tiêu, điều kiện ra quyết định cuối |

Bảng này là **một kế hoạch định hướng**, không phải lời cam kết rằng tích hợp thanh toán chắc chắn hoàn tất đúng tuần bốn. Khi có thông tin mới, nhóm cập nhật phạm vi, thứ tự và các mốc dự báo; nếu rủi ro an toàn chưa giải quyết, không tuyên bố đã sẵn sàng chỉ vì đến tuần tám.

### 11.4. Dùng dữ liệu để xem lại phạm vi

Giả sử đội nhìn sáu tuần làm việc tương tự gần nhất và thấy throughput **4, 5, 3, 6, 4, 5 item/tuần**. Trong backlog, có **24 item tương đối nhỏ và so sánh được** cần hoàn tất theo mục tiêu lựa chọn; những item chưa làm rõ hoặc tích hợp không tương đồng được xử lý riêng.

Đội có thể nói:

> “Với 24 item có độ lớn tương tự dữ liệu lịch sử, phép tính trung bình cho kết quả khoảng 5–6 tuần. Nhưng throughput đã biến động từ 3 đến 6 item/tuần và các phụ thuộc chưa chắc. Chúng ta sẽ theo dõi các kịch bản khoảng 4–8 tuần như một trao đổi rủi ro ban đầu, không phải khoảng tin cậy. Đặc biệt, dự báo cho thanh toán sẽ được cập nhật sau kiểm chứng tích hợp.”

Khi tiến độ thực tế cho thấy thời gian có thể không đủ, Product Owner phối hợp với những người có quyền liên quan **đổi thứ tự hoặc giảm phạm vi không thiết yếu**, thay vì giảm DoD. Nếu các khả năng cốt lõi vẫn không có điều kiện hoàn tất an toàn trước mốc, tổ chức cần **ra quyết định về phương án dự phòng**.

### 11.5. Giả sử sau hai tuần xuất hiện phản hồi mới

Khi thử nghiệm với học viên, đội phát hiện nhiều người không biết mình đã đăng ký thành công do trạng thái chờ thanh toán khó hiểu. Đồng thời, đối tác thanh toán trả về callback lặp trong một số trường hợp. Hai thông tin này làm thay đổi kế hoạch:

- **Ưu tiên sớm** cách biểu thị trạng thái chính xác và cơ chế xử lý callback lặp.
- **Để sau** dashboard phân tích nâng cao chưa hỗ trợ trực tiếp trải nghiệm đăng ký.
- **Cập nhật forecast** theo công việc mới được làm rõ và rủi ro tích hợp đã biết.
- **Điều chỉnh kế hoạch kiểm chứng** trước khi tuyên bố luồng thanh toán có thể dùng.

Đội không thất bại vì backlog khác danh sách ngày đầu. Ngược lại, chính phản hồi sớm đã giúp đội nhìn thấy điều cần ưu tiên để đạt mục tiêu thực tế.

### 11.6. Cách báo cáo cho những bên cần phối hợp

> **Mốc điều phối:** mở kỳ học mới sau 8 tuần (mốc giả định).  
> **Mục tiêu:** học viên tự ghi danh và vào bài đầu an toàn, với trạng thái đúng.  
> **Đã kiểm chứng:** khả năng ghi danh cơ bản trên môi trường tích hợp, đạt DoD theo phạm vi được mô tả.  
> **Rủi ro còn mở:** xử lý callback thanh toán và trường hợp lỗi; có quyết định sau kết quả tích hợp.  
> **Dự báo:** những hạng mục tương đồng có phạm vi hoàn tất được ước tính theo throughput; phần rủi ro cao được trình bày riêng.  
> **Phạm vi đang thương lượng:** dashboard nâng cao và một số tiện ích không thiết yếu.  
> **Việc bên liên quan cần quyết định:** chấp thuận ưu tiên chất lượng luồng đăng ký so với các tiện ích; xác nhận phương án dự phòng nếu đối tác không sẵn sàng.  
> **Mốc cập nhật:** sau thử nghiệm callback và lần kiểm tra Increment kế tiếp.

Một báo cáo như vậy giúp truyền thông và vận hành chuẩn bị đúng thực tế hơn một dòng “dự án hoàn thành 75%” không giải thích phần còn thiếu.

## 12. Quản trị thay đổi mà không làm mất trách nhiệm

Cho phép thích ứng không đồng nghĩa mọi yêu cầu mới được thêm tự do hoặc Sprint Goal thay đổi theo từng ý kiến. Cần một **cơ chế quyết định thay đổi**.

### 12.1. Một câu hỏi ưu tiên trước khi thêm phạm vi

Khi stakeholder yêu cầu thêm một báo cáo trong khi nhóm đang hoàn tất luồng đăng ký, hãy hỏi:

1. Yêu cầu mới giải quyết vấn đề nào, bằng chứng hiện có là gì?
2. Nó có phục vụ Product Goal hoặc mục tiêu giai đoạn hơn hạng mục đang làm không?
3. Có ràng buộc pháp lý, sự cố nghiêm trọng hay chi phí chậm trễ thật sự nào không?
4. Nếu chọn yêu cầu mới, **hạng mục nào bị lùi, giảm phạm vi hoặc dừng**?
5. Mức bất định và phụ thuộc của yêu cầu mới đã được làm rõ chưa?
6. Ai có quyền quyết định ưu tiên; ai phải được thông báo về hệ quả?

Nếu không trả lời câu 4, tổ chức dễ rơi vào **cộng dồn phạm vi**: mọi yêu cầu đều “quan trọng nhất”, trong khi năng lực và thời gian hữu hạn.

### 12.2. Quyết định trong Scrum

Product Owner chịu trách nhiệm sắp thứ tự và làm rõ Product Backlog hướng tới Product Goal. Developers chịu trách nhiệm lập kế hoạch, duy trì chất lượng và điều chỉnh công việc nhằm hướng tới Sprint Goal. Khi xuất hiện việc mới, nhóm trao đổi theo mục tiêu, phạm vi, rủi ro và trách nhiệm tương ứng.

Không nên:

- Tự đưa mọi yêu cầu mới vào Sprint mà không xét Sprint Goal.
- Ép Developers giữ nguyên danh sách task nếu họ phát hiện một phương án tốt hơn để đạt mục tiêu.
- Giảm DoD để báo hoàn thành trước ngày đã công bố.
- Dùng Sprint Review như buổi phê duyệt bắt buộc trước khi Increment được phép phát hành.

### 12.3. Quyết định trong Kanban

Nhóm xác định chính sách bổ sung yêu cầu (replenishment), ưu tiên, loại công việc và WIP phù hợp. Khi xuất hiện sự cố khẩn, cần cơ chế xử lý rõ và công khai tác động tới các item đang mở.

Một yêu cầu được làm rõ tốt không có nghĩa phải kéo ngay vào hệ thống nếu WIP đang cao. Đôi khi **hoàn tất item bị chặn** giúp dự báo ổn định hơn mở thêm một item “dễ làm”.

### 12.4. Khi cần thay đổi ngày hoặc mục tiêu

Nếu bằng chứng mới cho thấy không thể đáp ứng phạm vi cốt lõi vào ngày dự kiến, hãy:

1. Công khai bằng chứng và giả định bị thay đổi.
2. Nêu những phương án còn khả thi, tác động và rủi ro tương ứng.
3. Xác định ràng buộc nào không thể thương lượng.
4. Đưa quyết định tới vai trò có thẩm quyền; không để nhân sự kỹ thuật tự nhận trách nhiệm vượt phạm vi.
5. Cập nhật roadmap, forecast, kế hoạch truyền thông và vận hành.
6. Đặt mốc kiểm tra tiếp theo và trách nhiệm thu bằng chứng.

Chất lượng của lập kế hoạch được thể hiện ở **mức độ sớm và rõ của việc phát hiện, xử lý sai lệch**, không chỉ ở việc giữ nguyên một ngày bất chấp thực tế.

## 13. Những ngộ nhận cần tránh

### Ngộ nhận 1: “Agile là không có kế hoạch”

Thiếu kế hoạch khiến nhóm không biết mục tiêu, không phối hợp phụ thuộc và không thể giúp khách hàng chuẩn bị. Agile cần kế hoạch nhưng xem nó như **giả thuyết về đường đi**, được cập nhật từ thực nghiệm.

**Thay thế:** Giữ mục tiêu, nhịp kiểm tra, phạm vi và dự báo ở độ chi tiết phù hợp với khoảng thời gian.

### Ngộ nhận 2: “Lập kế hoạch chi tiết đến từng ngày khiến dự báo chính xác”

Khi công việc còn bất định, nhiều con số chi tiết chỉ tăng vẻ chắc chắn, không tăng dữ liệu.

**Thay thế:** Nêu khoảng và kịch bản có giả định; làm rõ phần gần, dùng thử nghiệm để giảm rủi ro phần xa.

### Ngộ nhận 3: “Đã dự báo một ngày thì không được đổi”

Một dự báo không cập nhật khi phạm vi hoặc phụ thuộc thay đổi là thông tin lỗi thời. Nhưng thay đổi vô cớ cũng phá vỡ niềm tin.

**Thay thế:** Đặt mốc xem lại, ghi nguyên nhân và thông báo tác động khi cập nhật.

### Ngộ nhận 4: “Sprint commitment nghĩa là đóng toàn bộ ticket đã chọn”

Scrum Guide gắn commitment của Sprint Backlog với **Sprint Goal**. Developers có thể điều chỉnh kế hoạch khi học thêm để đạt mục tiêu, trong khi giữ DoD. Không nên gọi danh sách chi tiết của Sprint là phạm vi bất biến.

**Thay thế:** Dùng Sprint Goal làm điểm tập trung; làm minh bạch những gì đã đạt và chưa đạt.

### Ngộ nhận 5: “Velocity tăng thì release chắc chắn sớm hơn”

Velocity phụ thuộc cách ước lượng và chia item. Đổi thang điểm, thêm ticket nhỏ hoặc làm nhiều việc song song có thể làm số tăng mà không tạo Increment hữu ích.

**Thay thế:** Kiểm tra Increment đạt DoD, throughput/cycle time theo đơn vị tương đối so sánh được và kết quả sử dụng.

### Ngộ nhận 6: “Monte Carlo cho biết chính xác ngày phát hành”

Mô phỏng cho phân phối kết quả theo mô hình và dữ liệu đầu vào. Nó có thể bỏ sót thay đổi phạm vi, phụ thuộc, độ lớn item hoặc những sự cố ngoài mẫu lịch sử.

**Thay thế:** Nêu giả định, nguồn dữ liệu, thời kỳ áp dụng, xác suất theo mô hình và các điều kiện cần cập nhật.

### Ngộ nhận 7: “Có ngày cố định thì phải chốt mọi tính năng”

Khi ngày là ràng buộc, thường cần tách **phần tối thiểu bắt buộc** khỏi các tiện ích có thể ưu tiên sau. Không nên cắt các yêu cầu chất lượng hoặc nghĩa vụ bắt buộc.

**Thay thế:** Giữ ngày làm đầu vào ra quyết định, thương lượng phạm vi và chuẩn bị phương án dự phòng khi cần.

### Ngộ nhận 8: “Cắt nhỏ story là tự động giảm rủi ro”

Nhiều story nhỏ có thể vẫn phụ thuộc vào một tích hợp chưa kiểm chứng hoặc mỗi story chỉ là một tầng kỹ thuật không dùng riêng được.

**Thay thế:** Chia lát cắt xuyên suốt theo hành vi hoặc giả thuyết, giữ kiểm soát rủi ro thiết yếu và tạo Increment thực sự kiểm tra được.

### Ngộ nhận 9: “Làm nhiều việc song song giúp hoàn tất sớm”

WIP cao có thể làm tăng chuyển ngữ cảnh, thời gian chờ và số hạng mục chưa được kiểm chứng. Bắt đầu nhiều không có nghĩa hoàn tất nhiều.

**Thay thế:** Quản lý WIP theo chính sách, chú ý work item age, ưu tiên tháo chặn và hoàn tất công việc.

### Ngộ nhận 10: “Dự báo chỉ thuộc trách nhiệm quản lý”

Product Owner hiểu giá trị và thứ tự backlog; Developers hiểu năng lực, độ lớn và rủi ro kỹ thuật; vận hành hoặc bên phụ thuộc có thông tin khác. Một dự báo chỉ dựa trên kỳ vọng của một bên thường thiếu căn cứ.

**Thay thế:** Kết hợp các góc nhìn, giữ rõ quyền quyết định và các điều kiện của dự báo.

### Ngộ nhận 11: “Đã đạt DoD nghĩa là outcome chắc chắn đạt”

Increment đạt DoD chứng minh một khả năng phần mềm đã hoàn tất theo tiêu chuẩn chất lượng, không chứng minh người dùng thích hoặc sử dụng hiệu quả.

**Thay thế:** Theo dõi phản hồi và kết quả sử dụng; cập nhật Product Backlog khi giả thuyết giá trị không đúng.

### Ngộ nhận 12: “Mỗi thay đổi kế hoạch là một thất bại”

Có những thay đổi phản ánh việc đội học sớm và tránh đầu tư vào giải pháp sai. Cũng có thay đổi do thiếu phối hợp hoặc quyết định yếu, cần cải tiến. Không thể kết luận chỉ từ việc kế hoạch khác ban đầu.

**Thay thế:** Phân tích lý do, bằng chứng, tác động và điều đội đã làm để cải thiện dự báo hoặc quyết định.

## 14. Một mẫu báo cáo dự báo minh bạch

Mẫu ngắn dưới đây phù hợp cho báo cáo tiến độ liên quan tới một mục tiêu hoặc release. Có thể giảm số trường khi công việc đơn giản.

~~~text
MUC TIEU / DOI TUONG:
  [Nguoi dung can lam duoc dieu gi?]

MOC CAN PHOI HOP:
  [Ngay bat buoc hay ngay du bao?]

PHAM VI:
  Bat buoc:
  Co the thuong luong:
  Chua du ro:

DA KIEM CHUNG:
  [Increment da dat DoD, moi truong, hanh vi duoc kiem tra]

DU BAO HIEN TAI:
  [Khoang thoi gian / pham vi du kien / muc tin cay neu co mo hinh]

DU LIEU CO SO:
  [Throughput / cycle time / nang luc / thoi ky / dinh nghia Done]

GIA DINH:
  [Quy mo backlog, phu thuoc, nang luc, chat luong]

RUI RO VA DIEM CHAN:
  [Tac dong, nguoi phu trach, han xu ly / moc xem lai]

QUYET DINH CAN THUC HIEN:
  [Uu tien, dieu chinh pham vi, chon phuong an, can tham van ai]

MOC CAP NHAT:
  [Khi nao / sau bang chung gi]
~~~

### 14.1. Ba cách viết dự báo cần phân biệt

| Cách viết | Đánh giá | Cách cải thiện |
|---|---|---|
| “Chắc chắn xong toàn bộ ngày 30.” | Dễ gây hiểu nhầm nếu phạm vi và rủi ro chưa đủ căn cứ | Nói rõ tính chất cam kết hay forecast, phạm vi và điều kiện |
| “Không biết lúc nào xong vì Agile luôn thay đổi.” | Không giúp bên liên quan phối hợp | Trình bày phần đã biết, kịch bản, công việc giảm bất định và mốc xem lại |
| “Theo dữ liệu hiện tại, nhóm khả năng A có thể hoàn tất trong khoảng được dự báo; riêng tích hợp B phụ thuộc thử nghiệm ngày X. Chúng tôi sẽ cập nhật sau khi có kết quả.” | Dễ kiểm tra, minh bạch bất định và có thể hành động | Duy trì bằng chứng, tránh thể hiện xác suất khi chưa có mô hình phù hợp |

Đừng dùng chỉ số xác suất như “90%” nếu chỉ là cảm giác hoặc lời trấn an. Nếu sử dụng xác suất từ mô hình, cần công khai mô hình và giới hạn áp dụng.

## 15. Một quy trình triển khai trong bốn tuần

Một đội thường xuyên hứa ngày chính xác nhưng liên tục đổi kế hoạch có thể thử cách cải tiến nhỏ sau:

| Tuần | Mục tiêu thực hành | Việc làm | Bằng chứng mong đợi |
|---|---|---|---|
| **1 — Hiểu hệ thống hiện tại** | Tách mục tiêu, ngày bắt buộc, phạm vi và năng lực thực | Chọn một luồng quan trọng; xem item đã hoàn tất, WIP, cycle time, phụ thuộc và sự cố | Định nghĩa Done, dữ liệu dòng công việc có bối cảnh, danh sách bất định chính |
| **2 — Làm rõ và chia nhỏ** | Tạo phạm vi có thể dự báo hơn | Refinement những item gần, chia lát cắt dọc, đặt AC/DoD, kiểm tra rủi ro trọng yếu | Một nhóm hạng mục có thể lựa chọn, mốc thử nghiệm và giả định rõ |
| **3 — Dự báo và thực nghiệm** | Thử dự báo dựa trên dữ liệu, tạo Increment thật | Dự báo theo kịch bản hoặc dữ liệu lịch sử, ưu tiên hoàn tất lát cắt và thử phụ thuộc | Increment đã kiểm tra, chênh lệch giữa dự báo và thực tế, bài học |
| **4 — Cập nhật và giao tiếp** | Thiết lập nhịp điều chỉnh đáng tin | Xem số liệu, phản hồi, phụ thuộc; đổi thứ tự/phạm vi khi cần; công khai forecast mới | Một báo cáo dự báo có điều kiện, người ra quyết định và mốc cập nhật |

Đừng kỳ vọng chỉ bốn tuần có thể tạo dữ liệu lịch sử đủ mạnh cho xác suất thống kê. Mục đích giai đoạn đầu là **làm rõ định nghĩa, thu dữ liệu nhất quán và cải thiện cách nói về bất định**. Độ tin cậy của mô hình được đánh giá dần theo thời gian.

## 16. Bài tập vận dụng

### Bài tập A — Phân biệt kế hoạch, dự báo và cam kết

Một nhóm nói:

1. “Trong hai tuần tiếp theo, chúng ta tập trung để học viên xác minh email và vào được khóa đã đăng ký.”
2. “Chúng ta sẽ ưu tiên tích hợp, viết kiểm thử và xử lý các lỗi quan trọng trước khi làm giao diện bổ sung.”
3. “Dựa trên dữ liệu hiện tại, nhóm các hạng mục còn lại có thể cần khoảng năm đến tám tuần.”
4. “Chúng ta sẽ không bỏ các kiểm tra bảo mật áp dụng để giữ ngày phát hành.”

**Yêu cầu:** Xác định mục tiêu, kế hoạch, dự báo và cam kết về chất lượng trong các câu trên. Câu nào cần thêm giả định?

<details>
<summary>Gợi ý</summary>

Câu 1 nêu mục tiêu ngắn hạn; câu 2 nêu kế hoạch thực hiện; câu 3 là dự báo cần làm rõ loại item, dữ liệu, phạm vi và giả định; câu 4 là cam kết về chất lượng và ranh giới. Một mục tiêu trong Scrum có thể được thể hiện qua Sprint Goal, nhưng không tự đồng nghĩa mọi backlog item đều bắt buộc hoàn tất.

</details>

### Bài tập B — Dự báo bằng dữ liệu throughput

Một đội có throughput lịch sử theo tuần là **4, 5, 3, 6, 4, 5 item**. Có **24 item** tương đối so sánh được còn cần hoàn tất.

**Yêu cầu:** Tính trung bình lịch sử, thời gian ước tính thô theo trung bình và hai kịch bản nếu tương lai hoàn tất khoảng 3 hoặc 6 item/tuần. Vì sao không thể gọi những con số này là cam kết hoặc khoảng tin cậy thống kê?

<details>
<summary>Gợi ý</summary>

Tổng 27 item trong 6 tuần, trung bình 4,5 item/tuần. Phép chia 24/4,5 ≈ 5,33 tuần. Nếu tốc độ duy trì 3 item/tuần sẽ cần khoảng 8 tuần; nếu 6 item/tuần sẽ cần khoảng 4 tuần. Kết quả chỉ là các kịch bản theo giả định throughput và item tương đồng, chưa có phân phối xác suất đáng tin; phụ thuộc, năng lực và phạm vi có thể thay đổi.

</details>

### Bài tập C — Một mốc bắt buộc, nhiều tính năng mong muốn

Một đơn vị đào tạo phải mở đăng ký vào ngày khai giảng. Stakeholders yêu cầu 20 tính năng, trong đó có phân quyền học viên, đăng ký khóa miễn phí, thanh toán, gợi ý khóa học và dashboard đẹp.

**Yêu cầu:** Đề xuất cách xác định phạm vi tối thiểu có ích và an toàn, các mục có thể thương lượng, rủi ro cần kiểm chứng sớm và cách báo cáo nếu tiến độ không đủ.

<details>
<summary>Gợi ý</summary>

Đầu tiên xác nhận đúng đối tượng và hành vi tối thiểu để mở đăng ký, nghĩa vụ pháp lý, quyền truy cập và quy tắc thanh toán thực tế. Tách những khả năng bắt buộc khỏi gợi ý, dashboard và tiện ích không thiết yếu. Thử rủi ro phụ thuộc thanh toán/quyền truy cập sớm. Nếu khả năng cốt lõi không an toàn hoặc chưa đạt DoD, công khai mức sẵn sàng, đưa ra phương án giảm phạm vi/đổi cách triển khai/mốc phối hợp hoặc dự phòng cho người có thẩm quyền quyết định; không báo thành công giả.

</details>

### Bài tập D — Sprint Goal và thay đổi phạm vi

Scrum Team đặt Sprint Goal: “Người dùng có thể theo dõi trạng thái xác minh tài khoản rõ ràng”. Giữa Sprint, một stakeholder yêu cầu thêm báo cáo quản trị, trong khi Developers phát hiện lỗi trạng thái “Đã xác minh” hiển thị sai.

**Yêu cầu:** Nhóm nên ra quyết định thế nào để giữ khả năng thích ứng và trách nhiệm?

<details>
<summary>Gợi ý</summary>

Developers tập trung xử lý lỗi ảnh hưởng trực tiếp Sprint Goal và chất lượng Increment; trao đổi tác động với Product Owner. Product Owner cân nhắc giá trị, ưu tiên của yêu cầu báo cáo và khả năng đưa vào Product Backlog để xem sau. Nếu báo cáo là nghĩa vụ khẩn, cần đánh giá ràng buộc và thương lượng phạm vi/ưu tiên có thẩm quyền. Sprint Backlog có thể điều chỉnh; Sprint Goal và DoD không nên bị hạ chỉ để đóng thêm ticket.

</details>

### Bài tập E — Dự báo dựa trên dữ liệu không còn đại diện

Đội bảo trì thường hoàn tất khoảng năm bug nhỏ mỗi tuần. Sắp tới đội phải di chuyển dữ liệu cho một hệ thống lớn chưa từng xử lý. Quản lý yêu cầu dùng tốc độ năm bug/tuần để dự báo số ngày migration.

**Yêu cầu:** Vì sao phép dự báo này thiếu căn cứ? Những bước nào có thể giúp tạo dự báo thực tế hơn?

<details>
<summary>Gợi ý</summary>

Bug nhỏ và migration lớn khác đơn vị, loại rủi ro và phụ thuộc; throughput của bug không suy ra tốc độ migration. Nên làm rõ yêu cầu toàn vẹn dữ liệu, downtime, rollback, quyền truy cập, phụ thuộc; thử migration trên tập dữ liệu đại diện trong môi trường phù hợp; chia thành các lát cắt kiểm chứng an toàn; đo thời gian và lỗi thực tế rồi cập nhật kịch bản. Nếu chưa có dữ liệu, cần công khai bất định thay vì tạo một con số chính xác giả.

</details>

### Bài tập F — SLE và work item age

Một nhóm có SLE minh họa: “85% item thuộc loại đang đo hoàn tất trong 8 ngày sau khi bắt đầu”. Một item đã mở 7 ngày và đang chờ phê duyệt từ đội khác.

**Yêu cầu:** Nên diễn giải SLE thế nào? Nhóm cần làm gì ngay và có được kết luận item chắc chắn trễ không?

<details>
<summary>Gợi ý</summary>

SLE là một kỳ vọng xác suất từ hệ thống được đo, không phải thời hạn đảm bảo cho từng item. Item đã gần mốc 8 ngày nên nhóm cần kiểm tra age, lý do chờ, phối hợp với bên phê duyệt và xem các lựa chọn để hoàn tất hoặc cập nhật dự báo. Không có cơ sở tuyên bố chắc chắn item sẽ trễ; cũng không nên phớt lờ vì “vẫn chưa tới ngày thứ tám”.

</details>

### Bài tập G — Một dự báo bị thay đổi sau phản hồi

Đội đang dự báo hoàn tất một luồng đăng ký trong sáu tuần. Sau thử nghiệm, họ phát hiện nhiều người dùng cần hiển thị rõ trạng thái chờ, trong khi tính năng gợi ý khóa ít được quan tâm.

**Yêu cầu:** Đội nên giữ nguyên backlog vì đã ước lượng xong hay nên điều chỉnh? Cần báo cáo gì để stakeholder tin tưởng?

<details>
<summary>Gợi ý</summary>

Đội nên xem lại thứ tự dựa trên mục tiêu và bằng chứng, ưu tiên giải quyết trạng thái chờ nếu đó là trở ngại chính, cân nhắc lùi tính năng gợi ý. Báo cáo cần nêu điều mới học, Increment đã hoàn tất, ảnh hưởng tới phạm vi/dự báo, giả định còn lại, người có thẩm quyền quyết định và mốc kiểm tra tiếp. Việc thay đổi có căn cứ có thể tăng tính đáng tin hơn cố giữ một dự báo lỗi thời.

</details>

## 17. Checklist đánh giá một kế hoạch thích ứng

Hãy dùng các câu hỏi sau trong planning, review hoặc khi chuẩn bị một release:

1. Người dùng cần đạt kết quả gì và làm sao biết mục tiêu vẫn còn giá trị?
2. Có phân biệt rõ **ngày bắt buộc**, **ngày dự báo** và **mốc xem lại** không?
3. Phần nào trong backlog là **bắt buộc**, phần nào có thể thương lượng?
4. Những hạng mục gần được chọn đã đủ rõ về hành vi, độ lớn, phụ thuộc và DoD chưa?
5. Những hạng mục xa có đang bị mô tả quá chi tiết so với thông tin hiện có không?
6. Dự báo dựa trên dữ liệu hoàn tất thực tế hay chỉ mong muốn của người quản lý?
7. Đơn vị item, định nghĩa Done và điểm đo cycle time/throughput đã nhất quán chưa?
8. Có đang dùng velocity/story point để so năng suất giữa đội hoặc cá nhân không?
9. Mức bất định của phụ thuộc ngoài, kỹ thuật, dữ liệu và năng lực đã được công khai chưa?
10. Những rủi ro lớn có **bước kiểm chứng sớm** và người phụ trách rõ không?
11. Có giới hạn WIP và chú ý các item già tuổi hoặc bị chặn lâu không?
12. Một lát cắt hoàn tất có thực sự tạo được hành vi sản phẩm kiểm chứng được không?
13. Đội có đang giữ chất lượng và bảo mật khi điều chỉnh phạm vi để đạt ngày quan trọng không?
14. Nếu outcome không cải thiện, Product Backlog hoặc giả thuyết sản phẩm có thể đổi không?
15. Mỗi bản forecast có nêu giả định, dữ liệu, phạm vi, rủi ro và mốc cập nhật không?
16. Những người cần quyết định đã biết các lựa chọn cùng tác động, thay vì chỉ nhận tỷ lệ tiến độ không?
17. Khi ràng buộc không thể đáp ứng, tổ chức có phương án dự phòng hoặc cơ chế quyết định kịp thời không?
18. Sau mỗi lần so sánh dự báo và thực tế, đội có chọn một cải tiến cụ thể cho cách lập kế hoạch không?

Nếu chưa trả lời được hết, đừng lập thêm hàng loạt biểu mẫu. Hãy chọn **một giả định đang chi phối dự báo** và thiết kế cách kiểm chứng sớm nhất có ích. Dần dần, dữ liệu và thói quen kiểm tra thực tế sẽ giúp dự báo có giá trị hơn.

## 18. Ghi nhớ

- **Agile không có nghĩa là không lập kế hoạch.** Đội cần một hướng đi rõ, nhưng kế hoạch phải được cập nhật khi thực tế cung cấp thông tin mới.
- **Dự báo khác cam kết.** Dự báo hỗ trợ quyết định theo dữ liệu và giả định hiện tại; cam kết cần nêu rõ điều gì nằm trong trách nhiệm và quyền kiểm soát của các bên.
- **Lập kế hoạch cuốn chiếu giúp cân bằng chi tiết và bất định:** phần gần rõ để thực hiện, phần xa đủ định hướng, làm rõ dần khi đến gần và có bằng chứng.
- **Product Goal, Sprint Goal và DoD trong Scrum phục vụ những mục đích khác nhau.** Sprint Goal tạo sự tập trung khi điều chỉnh kế hoạch; DoD bảo vệ chất lượng; Product Backlog liên tục được làm rõ và sắp ưu tiên.
- **Kanban cung cấp thông tin thực nghiệm cho dự báo.** Throughput, cycle time, WIP, work item age và SLE hữu ích khi định nghĩa và phạm vi tương đồng; không chỉ dùng một con số trung bình hoặc điểm ước lượng.
- **Ngày cố định không bắt buộc mọi chi tiết cũng cố định.** Có thể thương lượng phạm vi, thứ tự và cách triển khai, nhưng không được che giấu rủi ro hoặc hạ chuẩn an toàn bắt buộc.
- **Increment nhỏ, kiểm thử đáng tin và phản hồi sớm giúp dự báo cải thiện.** Một dự báo được cập nhật có căn cứ đáng tin hơn một lời hứa không đổi bất chấp bằng chứng.

Khi ai đó hỏi “**Bao giờ xong?**”, câu trả lời hữu ích không chỉ là một ngày. Hãy trả lời: **“Xong khả năng nào, theo tiêu chuẩn gì, dựa trên dữ liệu và giả định nào, có những kịch bản nào, và khi nào chúng ta sẽ kiểm tra lại dự báo?”** Đó là cách duy trì khả năng dự đoán mà không cần cố định mọi chi tiết từ đầu.

## Tài liệu tham khảo định hướng

- [Manifesto for Agile Software Development](https://agilemanifesto.org/): coi trọng phản hồi thay đổi và phần mềm hoạt động được.
- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html): hoan nghênh thay đổi yêu cầu, giao phần mềm thường xuyên và hợp tác liên tục.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html): Product Goal, Sprint Goal, Definition of Done, Product Backlog refinement, Sprint Planning và Sprint Review.
- [The Kanban Guide](https://kanbanguides.org/the-kanban-guide/): WIP, work item age, cycle time, throughput và Service Level Expectation.
- [Agile Alliance — Glossary](https://agilealliance.org/agile101/agile-glossary/): thuật ngữ Agile, lập kế hoạch, user story và các thực hành có liên quan.
