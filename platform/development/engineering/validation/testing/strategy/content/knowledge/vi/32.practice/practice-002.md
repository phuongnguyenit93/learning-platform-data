# Lập danh mục rủi ro cùng mức ưu tiên và người theo dõi

Kiểm thử luôn diễn ra trong điều kiện có bất định. Yêu cầu có thể chưa rõ, thay đổi có thể làm ảnh hưởng đến thành phần khác, môi trường có thể không sẵn sàng, dữ liệu có thể không đại diện và một số lỗi chỉ xuất hiện dưới tải hoặc trong tình huống hiếm. Nếu nhóm chỉ lập danh sách test case mà không ghi nhận những điều có thể cản trở mục tiêu chất lượng, nhóm sẽ khó biết nên kiểm tra điều gì trước, cần ai xử lý và rủi ro nào phải được đưa lên cấp quyết định.

Danh mục rủi ro (risk register) là hồ sơ tập trung ghi lại các sự kiện không chắc chắn có thể ảnh hưởng đến mục tiêu kiểm thử hoặc chất lượng sản phẩm. Danh mục giúp mô tả rủi ro bằng ngôn ngữ có thể hành động, đánh giá mức ưu tiên, chỉ định người chịu trách nhiệm theo dõi, xác định biện pháp ứng phó và cập nhật trạng thái theo bằng chứng mới.

Một danh mục hữu ích không phải bảng liệt kê thật nhiều điều đáng lo. Mỗi mục cần chỉ ra điều kiện có thể kích hoạt, sự kiện có thể xảy ra, hậu quả, mức ưu tiên, owner, hành động và thời điểm xem xét. Nhóm cần duy trì danh mục trong suốt vòng đời phát triển và phát hành, thay vì chỉ tạo một lần khi bắt đầu dự án.

## 1. Hiểu rủi ro trong hoạt động kiểm thử

Rủi ro (risk) là một sự kiện hoặc điều kiện chưa chắc chắn mà nếu xảy ra có thể ảnh hưởng đến mục tiêu. Tác động có thể tích cực hoặc tiêu cực; trong quản lý kiểm thử, danh mục thường tập trung vào rủi ro tiêu cực như lỗi nghiêm trọng lọt production, thiếu bằng chứng, chậm phát hành, mất dữ liệu hoặc không đáp ứng yêu cầu.

Cần phân biệt rủi ro với vấn đề đã xảy ra:

- **Rủi ro:** sự kiện có thể xảy ra trong tương lai, xác suất và tác động còn bất định.
- **Vấn đề (issue):** sự kiện hoặc trở ngại đã xảy ra và cần xử lý ngay.
- **Giả định (assumption):** điều đang được xem là đúng để lập kế hoạch nhưng chưa được xác minh đầy đủ.
- **Phụ thuộc (dependency):** điều kiện, nhóm, hệ thống hoặc quyết định mà công việc đang dựa vào.
- **Hạn chế (constraint):** giới hạn đã biết như ngân sách, thời gian, quyền truy cập hoặc năng lực hạ tầng.

Ví dụ, “sandbox thanh toán có thể ngừng hoạt động trong đợt kiểm thử” là rủi ro. Khi sandbox đã ngừng hoạt động và nhóm không thể chạy test, đó là issue. “Nhà cung cấp sẽ duy trì sandbox trong suốt tuần” là giả định. “Nhóm kiểm thử phụ thuộc vào đội thanh toán để cấp tài khoản sandbox” là dependency.

Một issue có thể tạo ra rủi ro mới. Ví dụ, môi trường đã bị chậm cấp phát; nếu thời gian kiểm thử bị rút ngắn, nhóm có thể bỏ lỡ kiểm tra hồi quy trước release. Khi đó cần xử lý issue môi trường và ghi nhận rủi ro phát sinh nếu nó còn ảnh hưởng đến mục tiêu tương lai.

### Rủi ro trong chiến lược kiểm thử

Rủi ro có thể xuất hiện ở nhiều lớp:

- **Rủi ro sản phẩm:** lỗi nghiệp vụ, sai dữ liệu, lỗi phân quyền, mất tính nhất quán hoặc suy giảm hiệu năng.
- **Rủi ro yêu cầu:** tiêu chí chấp nhận mơ hồ, yêu cầu thay đổi hoặc quy tắc nghiệp vụ chưa được thống nhất.
- **Rủi ro kiểm thử:** thiếu test, test không đáng tin, độ bao phủ thấp hoặc dữ liệu không đại diện.
- **Rủi ro môi trường:** môi trường không sẵn sàng, cấu hình khác production hoặc phụ thuộc không ổn định.
- **Rủi ro nguồn lực:** thiếu kỹ năng, thiếu người, thời gian không đủ hoặc owner không sẵn sàng.
- **Rủi ro tích hợp:** hợp đồng API sai lệch, message mất/trùng, timeout hoặc phiên bản dịch vụ không tương thích.
- **Rủi ro vận hành:** thiếu log, cảnh báo, backup, rollback hoặc người trực hỗ trợ.
- **Rủi ro bảo mật và tuân thủ:** lộ dữ liệu, quyền truy cập sai, lưu trữ không phù hợp hoặc thiếu bằng chứng bắt buộc.

Không phải mọi rủi ro đều thuộc trách nhiệm riêng của QA. Nhóm kiểm thử có trách nhiệm phát hiện, phân tích và cung cấp bằng chứng; owner của rủi ro có thể thuộc sản phẩm, kỹ thuật, vận hành, bảo mật hoặc một nhóm phụ thuộc.

## 2. Mục tiêu và phạm vi của risk register

Danh mục rủi ro cần hỗ trợ các quyết định cụ thể:

1. Xác định vùng nào cần kiểm thử sâu hoặc sớm hơn.
2. Phân bổ thời gian, nhân lực và môi trường theo mức rủi ro.
3. Theo dõi điều kiện có thể làm chậm hoặc ngăn kiểm thử.
4. Làm rõ ai chịu trách nhiệm xử lý và ai có quyền chấp nhận rủi ro còn lại.
5. Cung cấp căn cứ cho quyết định release, rollout, hoãn hoặc giảm phạm vi.
6. Theo dõi hiệu quả của biện pháp giảm thiểu.
7. Lưu dấu vết quyết định để có thể xem lại sau sự cố hoặc audit.

Phạm vi của danh mục phải phù hợp với cấp quản lý. Một dự án có thể có risk register tổng thể, trong đó liên kết đến danh mục chi tiết của từng dịch vụ hoặc từng hoạt động kiểm thử. Tránh tạo nhiều bảng độc lập không có quy tắc đồng bộ, vì cùng một rủi ro có thể bị đánh giá khác nhau hoặc không ai theo dõi.

### Rủi ro sản phẩm và rủi ro dự án

Hai nhóm này liên quan nhưng cần được nhận diện riêng:

- **Product risk:** nguy cơ sản phẩm không đáp ứng nhu cầu, yêu cầu hoặc thuộc tính chất lượng.
- **Project/test execution risk:** nguy cơ hoạt động kiểm thử không hoàn thành đúng phạm vi, thời gian, chi phí hoặc chất lượng bằng chứng.

Ví dụ:

- Rủi ro sản phẩm: tính tiền sai khi áp dụng đồng thời mã giảm giá và thuế.
- Rủi ro thực thi: không có dữ liệu sandbox để kiểm tra hoàn tiền trước release.

Rủi ro thực thi có thể khiến nhóm không phát hiện được rủi ro sản phẩm. Danh mục nên liên kết hai mục này để người ra quyết định hiểu tác động dây chuyền.

## 3. Nhận diện rủi ro có hệ thống

Rủi ro thường bị bỏ sót khi nhóm chỉ hỏi “có thể có lỗi gì?” mà không xem xét bối cảnh, thay đổi và phụ thuộc. Nên kết hợp nhiều kỹ thuật nhận diện.

### Phân tích yêu cầu và luồng nghiệp vụ

Đọc yêu cầu, tiêu chí chấp nhận, quy tắc nghiệp vụ, user journey và trường hợp ngoại lệ. Tìm các điểm:

- Quy tắc chưa rõ hoặc có nhiều cách hiểu.
- Luồng có giao dịch tiền, dữ liệu quan trọng hoặc thao tác không thể hoàn tác.
- Nhánh xử lý lỗi, retry, timeout và hủy.
- Quyền truy cập theo vai trò, tenant hoặc tổ chức.
- Hành vi khi dữ liệu thiếu, trùng, cũ hoặc không hợp lệ.
- Tình huống nhiều người dùng thao tác đồng thời.

Ví dụ, luồng chuyển tiền cần xem xét số dư, giới hạn, retry, idempotency, đối soát và trạng thái giao dịch không xác định. Một test chỉ kiểm tra phản hồi thành công không đủ để phản ánh toàn bộ rủi ro.

### Phân tích kiến trúc và thay đổi

Dùng sơ đồ thành phần, luồng dữ liệu, API contract, event flow, database schema và danh sách dependency. Tập trung vào:

- Thành phần mới hoặc vừa được tái cấu trúc.
- Ranh giới giữa các dịch vụ.
- Điểm tích hợp với nhà cung cấp bên ngoài.
- Thay đổi schema, migration hoặc cache.
- Hệ thống có trạng thái dùng chung.
- Điểm lỗi đơn (single point of failure).
- Các đường đi dữ liệu nhạy cảm.
- Khả năng khôi phục sau lỗi.

Một thay đổi nhỏ ở API có thể ảnh hưởng nhiều consumer. Cần xác định ai đang phụ thuộc và test nào chứng minh tương thích.

### Dùng lịch sử defect và incident

Xem lại lỗi đã xảy ra, lỗi lọt production, ticket hỗ trợ, post-incident review và các lần rollback. Tìm mẫu lặp:

- Loại lỗi nào xuất hiện thường xuyên?
- Thành phần nào có nhiều defect nghiêm trọng?
- Lỗi thường xuất hiện ở môi trường hoặc phiên bản nào?
- Test nào từng bỏ sót lỗi?
- Biện pháp khắc phục trước đây có còn hiệu quả?
- Có sự cố do thiếu monitoring hoặc rollback không?

Lịch sử là đầu vào quan trọng, nhưng không phải dự báo chắc chắn. Kiến trúc và mức sử dụng có thể đã thay đổi nên cần kiểm tra lại tính liên quan.

### Workshop và phỏng vấn

Mời các vai trò có góc nhìn khác nhau như product owner, developer, tester, architect, SRE, security và support. Có thể dùng câu hỏi:

- Điều gì có thể khiến release không đạt mục tiêu?
- Nếu giả định quan trọng nhất sai thì chuyện gì xảy ra?
- Thành phần nào khó kiểm thử hoặc khó khôi phục?
- Thay đổi nào có tác động rộng nhất?
- Người dùng có thể gặp hậu quả gì nếu lỗi xảy ra?
- Bằng chứng nào hiện chưa có?
- Điều gì khiến nhóm không phát hiện lỗi trước production?

Ghi lại ý kiến, sau đó chuẩn hóa thành rủi ro có điều kiện và hậu quả cụ thể. Không biến mọi ý kiến thành một risk item riêng nếu chúng mô tả cùng một sự kiện.

### Kỹ thuật hỗ trợ

Có thể dùng checklist, brainstorming, assumption analysis, failure mode and effects analysis (FMEA), threat modeling, bow-tie analysis hoặc phân tích dependency. Kỹ thuật được chọn cần phù hợp quy mô và mức độ rủi ro. Với một thay đổi nhỏ, checklist và review có thể đủ; với hệ thống xử lý dữ liệu nhạy cảm hoặc giao dịch quan trọng, cần phân tích chuyên sâu hơn.

## 4. Viết phát biểu rủi ro rõ ràng

Một risk item tốt mô tả sự kiện chưa chắc chắn và hậu quả nếu nó xảy ra. Cấu trúc dễ dùng:

> Do [nguyên nhân hoặc điều kiện], trong [bối cảnh], có thể xảy ra [sự kiện không mong muốn], dẫn đến [hậu quả đối với mục tiêu].

Ví dụ:

> Do migration thay đổi kiểu dữ liệu của cột trạng thái nhưng chưa được thử trên bản sao dữ liệu có kích thước gần production, khi triển khai có thể xảy ra lỗi chuyển đổi hoặc khóa bảng kéo dài, dẫn đến gián đoạn dịch vụ và chậm phát hành.

Phát biểu này cho biết nguyên nhân, tình huống, sự kiện và hậu quả. Nhóm có thể tiếp tục xác định biện pháp như rehearsal migration, đo thời gian khóa, backup/restore và kế hoạch rollback.

### Tránh mô tả mơ hồ

Các câu sau chưa đủ cụ thể:

- “Có rủi ro về database.”
- “Có thể bị chậm.”
- “Cần test kỹ hơn.”
- “Môi trường không tốt.”
- “API có vấn đề.”

Hãy chuyển thành câu có điều kiện và hậu quả:

- “Do consumer chưa xử lý message trùng, khi broker redeliver sau timeout, cùng một đơn hàng có thể bị ghi nhận hai lần.”
- “Do staging dùng cấu hình cache khác production, lỗi stale data có thể không xuất hiện trong kiểm thử trước release.”
- “Do chỉ có một người biết cấu hình runner, khi người đó vắng mặt nhóm có thể không khôi phục được pipeline trong thời gian cần thiết.”

### Một rủi ro cho mỗi sự kiện chính

Không gom nhiều sự kiện độc lập vào một dòng như “database, API và bảo mật đều có thể lỗi”. Mỗi sự kiện có nguyên nhân, hậu quả, owner và biện pháp khác nhau. Tách chúng để có thể ưu tiên và giao trách nhiệm cụ thể.

Ngược lại, không chia nhỏ một rủi ro thành nhiều dòng chỉ khác cách diễn đạt nếu chúng có cùng nguyên nhân, hậu quả, owner và kế hoạch ứng phó. Có thể dùng liên kết giữa các rủi ro khi chúng tạo thành chuỗi phụ thuộc.

## 5. Xác định nguyên nhân, sự kiện và hậu quả

Phân tích rủi ro cần tách ba phần:

- **Nguyên nhân (cause):** điều kiện hoặc điểm yếu làm sự kiện có khả năng xảy ra.
- **Sự kiện (event):** điều không mong muốn có thể xảy ra.
- **Hậu quả (consequence):** tác động lên người dùng, sản phẩm hoặc mục tiêu dự án.

Ví dụ về luồng webhook thanh toán:

| Thành phần | Mô tả |
|---|---|
| Nguyên nhân | Hệ thống chưa có cơ chế idempotency cho callback |
| Sự kiện | Nhà cung cấp gửi lại webhook và hệ thống xử lý lặp |
| Hậu quả | Đơn hàng hoặc giao dịch bị cập nhật hai lần, cần đối soát và hoàn tác |

Từ phân tích này, nhóm có thể xác định test cần có: gửi cùng event nhiều lần, gửi event đến trễ, thay đổi thứ tự, timeout khi xử lý và kiểm tra trạng thái cuối.

### Xác định phạm vi ảnh hưởng

Hậu quả không chỉ là “test fail”. Hãy xem tác động đến:

- Người dùng và hành trình nghiệp vụ.
- Tính đúng đắn, toàn vẹn và bảo mật dữ liệu.
- Tài chính, thanh toán và đối soát.
- Tính sẵn sàng và hiệu năng dịch vụ.
- Khả năng vận hành, điều tra và khôi phục.
- Cam kết hợp đồng, SLA hoặc quy định.
- Mốc phát hành, chi phí và uy tín.

Nêu hậu quả cụ thể giúp người ra quyết định hiểu vì sao rủi ro cần được ưu tiên.

## 6. Chấm điểm khả năng xảy ra và tác động

Một cách thực tế để xếp hạng rủi ro là đánh giá khả năng xảy ra (likelihood) và mức tác động (impact). Có thể dùng thang định tính 1–5 hoặc thấp/vừa/cao. Điều quan trọng là định nghĩa tiêu chí, dùng nhất quán và ghi căn cứ.

### Ví dụ thang khả năng xảy ra

| Điểm | Mức | Hướng dẫn đánh giá |
|---:|---|---|
| 1 | Rất thấp | Hiếm gặp; chưa có tín hiệu gần đây; có nhiều kiểm soát hiệu quả |
| 2 | Thấp | Có thể xảy ra nhưng ít khả năng trong điều kiện hiện tại |
| 3 | Trung bình | Có tiền lệ hoặc điều kiện kích hoạt tương đối phổ biến |
| 4 | Cao | Đã xảy ra nhiều lần hoặc điểm yếu hiện hữu làm khả năng tăng rõ |
| 5 | Rất cao | Gần như chắc chắn nếu không có hành động; đã có tín hiệu trực tiếp |

Các mô tả cần được điều chỉnh theo dữ liệu của tổ chức. Nếu có dữ liệu tần suất, có thể quy định khoảng xác suất theo thời gian hoặc mỗi release, nhưng không nên đưa ra con số giả chính xác khi không có dữ liệu.

### Ví dụ thang tác động

| Điểm | Mức | Hướng dẫn đánh giá |
|---:|---|---|
| 1 | Không đáng kể | Ảnh hưởng nhỏ, dễ phát hiện và khôi phục; không tác động mục tiêu chính |
| 2 | Thấp | Ảnh hưởng giới hạn, có workaround đơn giản |
| 3 | Trung bình | Ảnh hưởng một nhóm người dùng hoặc một phần chức năng; cần xử lý có kế hoạch |
| 4 | Cao | Gián đoạn chức năng quan trọng, mất dữ liệu có thể khôi phục hoặc chậm release đáng kể |
| 5 | Rất cao | Ảnh hưởng nghiêm trọng đến dữ liệu, tài chính, bảo mật, tuân thủ hoặc hoạt động cốt lõi |

Không nên chỉ dùng một thang tác động chung nếu tổ chức cần phân biệt tác động tài chính, an toàn, bảo mật, vận hành và uy tín. Có thể ghi nhiều chiều tác động và lấy mức cao nhất theo quy tắc đã thống nhất.

### Tính điểm rủi ro

Một cách xếp hạng đơn giản:

\[
Risk\ Score = Likelihood \times Impact
\]

Với thang 1–5, điểm nằm trong khoảng 1 đến 25. Ví dụ, likelihood 4 và impact 5 cho điểm 20.

Điểm số giúp sắp xếp và thảo luận, không phải xác suất chính xác hay quyết định tự động. Một rủi ro impact 5 với likelihood 1 vẫn có thể cần escalation nếu hậu quả liên quan đến bảo mật, dữ liệu hoặc yêu cầu bắt buộc. Nhóm cần quy định các trường hợp override theo mức nghiêm trọng.

### Ví dụ phân vùng ưu tiên

| Điểm | Mức ưu tiên gợi ý | Hành động |
|---:|---|---|
| 1–4 | Thấp | Theo dõi theo lịch, giữ biện pháp hiện có |
| 5–9 | Trung bình | Xác định owner và hành động phù hợp |
| 10–16 | Cao | Có kế hoạch giảm thiểu, thời hạn và rà soát thường xuyên |
| 17–25 | Rất cao | Escalate sớm, xem xét điều kiện release hoặc biện pháp khẩn cấp |

Ngưỡng trên chỉ là ví dụ. Mỗi tổ chức cần hiệu chỉnh theo risk appetite, loại sản phẩm và hậu quả có thể xảy ra. Không nên dùng điểm số để thay thế thảo luận chuyên môn.

## 7. Bổ sung yếu tố khẩn cấp và khả năng phát hiện

Likelihood và impact là nền tảng, nhưng một số rủi ro cần ưu tiên dựa trên yếu tố khác.

### Mức khẩn cấp (urgency)

Urgency phản ánh thời gian còn lại trước khi rủi ro có thể xảy ra hoặc trước khi cần hành động. Một rủi ro có điểm trung bình nhưng release chỉ còn một ngày có thể cần ưu tiên ngay hơn rủi ro cao chưa có mốc kích hoạt trong vài tháng.

Có thể ghi:

- Ngày dự kiến xảy ra sự kiện hoặc thời điểm phơi nhiễm.
- Hạn chót cần hoàn tất biện pháp.
- Số ngày còn lại.
- Mốc quyết định bị ảnh hưởng.

### Khả năng phát hiện (detectability)

Khả năng phát hiện cho biết nhóm có thể nhận ra rủi ro hoặc hậu quả đủ sớm hay không. Nếu không có log, metric hoặc cảnh báo, tác động có thể kéo dài trước khi được nhận ra.

Cần phân biệt:

- Khả năng phát hiện lỗi trước release bằng test.
- Khả năng phát hiện sự cố sau release bằng monitoring.
- Khả năng xác định nguyên nhân khi đã xảy ra.
- Khả năng phát hiện dữ liệu bị sai hoặc thiếu.

Có thể ghi riêng detectability theo thang định tính. Nếu tổ chức dùng FMEA và điểm RPN, phải giải thích quy tắc và tránh cộng hoặc nhân nhiều điểm theo cách không được chuẩn hóa.

### Tốc độ tăng rủi ro

Một số rủi ro tăng nhanh khi điều kiện thay đổi, ví dụ số lượng giao dịch tăng, thời hạn chứng chỉ sắp hết hoặc dependency chuẩn bị ngừng hỗ trợ. Ghi risk velocity hoặc xu hướng giúp xác định rủi ro nào cần xử lý sớm ngay cả khi điểm hiện tại chưa cao.

## 8. Xác định mức ưu tiên và quy tắc escalation

Mức ưu tiên nên thể hiện thứ tự hành động, không chỉ điểm số. Một quy tắc đơn giản có thể kết hợp:

- Risk score.
- Mức nghiêm trọng đặc biệt.
- Urgency và thời điểm phơi nhiễm.
- Khả năng phát hiện và khôi phục.
- Yêu cầu hợp đồng, pháp lý hoặc chính sách.
- Mức độ phụ thuộc với các rủi ro khác.
- Khả năng giảm thiểu trong thời gian còn lại.

### Ví dụ phân loại

- **P0 – Khẩn cấp:** có thể gây hậu quả nghiêm trọng hoặc vi phạm điều kiện bắt buộc; cần escalation ngay và quyết định trước khi tiếp tục.
- **P1 – Cao:** ảnh hưởng lớn đến luồng trọng yếu hoặc mốc phát hành; cần owner, kế hoạch giảm thiểu và hạn xử lý gần.
- **P2 – Trung bình:** có thể ảnh hưởng một phần chức năng hoặc phạm vi kiểm thử; cần theo dõi và xử lý theo kế hoạch.
- **P3 – Thấp:** tác động nhỏ, có workaround và khả năng khôi phục tốt; theo dõi theo lịch.

Định nghĩa P0–P3 phải phù hợp quy trình của tổ chức. Nếu tổ chức dùng Critical/High/Medium/Low thì giữ một bộ nhãn thống nhất trên dashboard và báo cáo.

### Khi nào cần escalation?

Escalate khi:

- Rủi ro vượt ngưỡng chấp nhận của nhóm.
- Owner không có thẩm quyền hoặc nguồn lực để xử lý.
- Biện pháp giảm thiểu không đạt hoặc quá hạn.
- Rủi ro ảnh hưởng nhiều nhóm hoặc nhiều dịch vụ.
- Rủi ro có thể vi phạm yêu cầu bắt buộc.
- Rủi ro có thể làm thay đổi quyết định phát hành.
- Rủi ro tăng nhanh hoặc điều kiện kích hoạt đã xuất hiện.

Bản escalation cần nêu sự kiện, hậu quả, mức ưu tiên, bằng chứng, lựa chọn, người cần quyết định và thời điểm cần quyết định. Không chỉ gửi một điểm số mà không có bối cảnh.

## 9. Chỉ định người theo dõi rủi ro

Mỗi rủi ro cần một risk owner rõ ràng. Risk owner chịu trách nhiệm bảo đảm rủi ro được hiểu, theo dõi, cập nhật và đưa ra quyết định hoặc escalation đúng lúc. Owner không nhất thiết tự thực hiện mọi hành động kỹ thuật.

Cần phân biệt:

- **Risk owner:** chịu trách nhiệm tổng thể về việc theo dõi và quản lý rủi ro.
- **Action owner:** người thực hiện một hành động giảm thiểu cụ thể.
- **Issue owner:** người xử lý vấn đề đã xảy ra.
- **Decision owner/approver:** người có thẩm quyền chấp nhận rủi ro còn lại hoặc quyết định dừng/tiếp tục.
- **Reviewer:** người cung cấp đánh giá độc lập hoặc chuyên môn.

Một rủi ro có thể có một risk owner và nhiều action owner. Tuy nhiên, không nên để trường owner ghi chung “QA/Dev team” mà không có cá nhân hoặc vai trò chịu trách nhiệm điều phối.

### Chọn owner phù hợp

Owner nên có:

- Hiểu biết về nguyên nhân và hậu quả.
- Khả năng tiếp cận dữ liệu và nhóm liên quan.
- Thẩm quyền điều phối hành động hoặc biết cách escalation.
- Thời gian theo dõi đến khi rủi ro được đóng hoặc chấp nhận.
- Khả năng cập nhật trạng thái và bằng chứng.

Ví dụ:

| Rủi ro | Risk owner phù hợp | Action owner có thể là |
|---|---|---|
| Migration có thể gây mất dữ liệu | Database/service owner | DBA, developer, QA |
| Thiếu test quyền truy cập | Security owner | Security engineer, test engineer |
| Sandbox không ổn định | Owner tích hợp bên ngoài | Platform engineer, vendor contact |
| Pipeline không đủ năng lực chạy ma trận | CI/platform owner | DevOps, test automation engineer |
| Yêu cầu nghiệp vụ chưa thống nhất | Product owner | Business analyst, product specialist |

### Owner vắng mặt hoặc thay đổi vai trò

Danh mục cần có cơ chế bàn giao. Khi owner rời dự án hoặc không còn phụ trách, người quản lý phải chỉ định owner mới và ghi ngày chuyển giao. Không để rủi ro tồn tại với owner đã không còn quyền truy cập hoặc không còn tham gia dự án.

## 10. Thiết kế cấu trúc risk register

Danh mục cần đủ trường để theo dõi và ra quyết định, nhưng không nên quá phức tạp khiến nhóm ngừng cập nhật. Có thể bắt đầu với các trường cốt lõi và bổ sung theo nhu cầu.

### Các trường cốt lõi

| Trường | Mục đích |
|---|---|
| Risk ID | Mã định danh duy nhất |
| Title | Tên ngắn gọn, dễ tìm |
| Risk statement | Nguyên nhân, sự kiện và hậu quả |
| Category | Nhóm rủi ro |
| Date identified | Ngày nhận diện |
| Likelihood | Khả năng xảy ra |
| Impact | Mức tác động |
| Risk score | Điểm theo quy tắc đã thống nhất |
| Priority | P0/P1/P2/P3 hoặc nhãn tương đương |
| Risk owner | Người chịu trách nhiệm theo dõi |
| Action owner | Người thực hiện từng hành động |
| Mitigation | Biện pháp giảm thiểu |
| Due date | Hạn hoàn thành hành động |
| Trigger/indicator | Dấu hiệu rủi ro đang tăng hoặc đã xảy ra |
| Status | Trạng thái hiện tại |
| Residual risk | Mức rủi ro còn lại sau biện pháp |
| Last reviewed | Ngày cập nhật gần nhất |
| Evidence/reference | Ticket, test, incident, log hoặc quyết định liên quan |

### Các trường bổ sung

Tùy bối cảnh, có thể thêm:

- Sản phẩm, release, dịch vụ hoặc thành phần bị ảnh hưởng.
- Mục tiêu chất lượng hoặc yêu cầu liên quan.
- Mức urgency và detectability.
- Risk appetite hoặc ngưỡng chấp nhận.
- Contingency plan và rollback.
- Ngày xem xét tiếp theo.
- Người chấp nhận rủi ro.
- Ngày chấp nhận và thời hạn hiệu lực.
- Risk dependency hoặc nhóm rủi ro liên quan.
- Lịch sử thay đổi điểm số và trạng thái.

### Mã định danh ổn định

Dùng ID như RISK-001 hoặc PRJ-R-014 để tham chiếu trong test plan, defect, release report và cuộc họp. Không tái sử dụng ID của rủi ro đã đóng cho một rủi ro mới. Nếu rủi ro được gộp hoặc tách, giữ liên kết đến các ID cũ để bảo toàn lịch sử.

## 11. Quản lý trạng thái của rủi ro

Trạng thái cần phản ánh vòng đời thực tế. Một bộ trạng thái có thể gồm:

| Trạng thái | Ý nghĩa |
|---|---|
| Identified | Đã ghi nhận, cần phân tích |
| Assessing | Đang đánh giá khả năng, tác động và ưu tiên |
| Open | Đã có owner và kế hoạch theo dõi |
| Mitigating | Các hành động giảm thiểu đang được thực hiện |
| Monitoring | Biện pháp đã áp dụng, tiếp tục theo dõi chỉ báo |
| Accepted | Người có thẩm quyền chấp nhận rủi ro còn lại trong phạm vi xác định |
| Escalated | Đã chuyển lên cấp quyết định cao hơn |
| Closed | Điều kiện rủi ro không còn hoặc đã được xử lý theo tiêu chí đóng |
| Occurred/Issue | Sự kiện đã xảy ra và cần quản lý như issue |

Tổ chức có thể dùng tên trạng thái khác. Điều quan trọng là định nghĩa điều kiện chuyển trạng thái và không dùng “Closed” chỉ vì ticket hành động đã hoàn tất nếu rủi ro vẫn còn.

### Khi rủi ro trở thành issue

Khi sự kiện xảy ra, cập nhật trạng thái và tạo issue/incident liên quan. Giữ lại risk record để truy vết nguồn gốc, đánh giá liệu biện pháp đã thất bại và ghi nhận bài học. Không xóa rủi ro khỏi danh mục vì nó đã xảy ra.

### Điều kiện đóng

Một rủi ro có thể được đóng khi:

- Nguyên nhân đã được loại bỏ hoặc sự kiện không còn khả thi trong phạm vi.
- Bằng chứng xác nhận biện pháp đã giảm rủi ro đến mức được chấp nhận.
- Phạm vi sản phẩm hoặc điều kiện áp dụng đã thay đổi.
- Rủi ro được thay thế bằng một hồ sơ khác có liên kết đầy đủ.
- Owner và người có thẩm quyền đã đồng ý theo quy trình.

Ghi rõ lý do đóng và bằng chứng. Một rủi ro “accepted” không giống “closed”; nó vẫn tồn tại nhưng được chấp nhận trong điều kiện và thời hạn nhất định.

## 12. Lập kế hoạch ứng phó và giảm thiểu

Sau khi đánh giá, nhóm chọn cách ứng phó phù hợp. Các chiến lược thường dùng gồm:

- **Avoid – tránh:** thay đổi phạm vi, thiết kế hoặc cách triển khai để loại bỏ điều kiện gây rủi ro.
- **Mitigate/reduce – giảm thiểu:** giảm khả năng xảy ra hoặc giảm tác động.
- **Transfer/share – chuyển giao hoặc chia sẻ:** phân bổ một phần trách nhiệm hoặc hậu quả qua hợp đồng, bảo hiểm hoặc dịch vụ chuyên môn; trách nhiệm quản trị vẫn cần được theo dõi.
- **Accept – chấp nhận:** quyết định giữ rủi ro trong giới hạn cho phép, có owner và kế hoạch ứng phó.
- **Contingency – dự phòng:** chuẩn bị hành động nếu sự kiện xảy ra.

### Tránh rủi ro

Ví dụ, nếu một tính năng mới chưa đủ bằng chứng và có thể ảnh hưởng dữ liệu, nhóm có thể tắt feature flag hoặc hoãn triển khai tính năng đó. Cần xác định tác động kinh doanh và người có quyền thay đổi phạm vi.

### Giảm khả năng xảy ra

Ví dụ:

- Bổ sung test contract và integration.
- Rehearsal migration trên bản sao dữ liệu đại diện.
- Cải thiện cô lập test data.
- Thêm kiểm tra quyền truy cập.
- Cố định phiên bản dependency.
- Tự động hóa smoke test và readiness check.

### Giảm tác động

Ví dụ:

- Canary rollout hoặc giới hạn tỷ lệ người dùng ban đầu.
- Feature flag và kill switch.
- Backup/restore đã được diễn tập.
- Rate limit, circuit breaker và retry có giới hạn.
- Monitoring, alert và runbook.
- Rollback hoặc forward-fix có kiểm chứng.

### Chuyển giao hoặc chia sẻ

Hợp đồng với nhà cung cấp có thể quy định SLA, hỗ trợ sự cố và trách nhiệm xử lý. Tuy vậy, việc thuê dịch vụ không làm biến mất trách nhiệm của tổ chức đối với dữ liệu, trải nghiệm người dùng và quyết định phát hành.

### Chấp nhận có kiểm soát

Chấp nhận rủi ro cần ghi:

- Rủi ro còn lại và bằng chứng.
- Lý do chấp nhận.
- Người có thẩm quyền.
- Phạm vi sản phẩm hoặc release.
- Ngày quyết định và ngày hết hiệu lực.
- Biện pháp giám sát và ứng phó.
- Điều kiện phải xem xét lại.

Không nên để một owner tự chấp nhận rủi ro vượt thẩm quyền, đặc biệt khi liên quan bảo mật, dữ liệu, pháp lý hoặc cam kết khách hàng.

## 13. Đánh giá rủi ro còn lại và hiệu quả biện pháp

Biện pháp giảm thiểu không bảo đảm rủi ro biến mất. Sau khi áp dụng, đánh giá lại likelihood và impact để xác định residual risk (rủi ro còn lại).

Ví dụ, trước khi thêm idempotency, khả năng xử lý webhook trùng có thể được đánh giá cao. Sau khi triển khai idempotency và test các trường hợp redelivery, likelihood giảm. Tuy nhiên, nếu chưa kiểm tra khả năng phục hồi khi database gián đoạn, vẫn còn một phần rủi ro cần theo dõi.

Phân biệt:

- **Inherent risk:** mức rủi ro trước khi tính đến biện pháp kiểm soát.
- **Current risk:** mức rủi ro hiện tại với các kiểm soát đang vận hành.
- **Residual risk:** mức rủi ro còn lại sau các biện pháp đã thực hiện hoặc dự kiến theo cách định nghĩa của tổ chức.

Hãy nêu rõ tổ chức đang dùng khái niệm nào để tránh so sánh điểm số không cùng cơ sở.

### Đo hiệu quả của biện pháp

Một hành động được đánh dấu Done chưa chứng minh rủi ro đã giảm. Cần kiểm tra:

- Biện pháp đã được triển khai đúng chưa?
- Có test hoặc bằng chứng xác nhận hiệu quả không?
- Có chỉ số vận hành cho thấy thay đổi không?
- Có tình huống nào biện pháp không bao phủ?
- Rủi ro mới có phát sinh do biện pháp không?
- Owner và người chấp nhận có đồng ý với mức còn lại không?

Nếu điểm số không thay đổi, ghi lý do. Có thể biện pháp chỉ tăng khả năng phát hiện chứ không giảm xác suất xảy ra.

## 14. Liên kết rủi ro với chiến lược và hoạt động kiểm thử

Risk register cần liên kết với test plan, test case, defect, release criteria và báo cáo. Nhờ vậy, rủi ro không tồn tại như một bảng hành chính tách khỏi công việc hàng ngày.

### Liên kết với test design

Mỗi rủi ro quan trọng cần chỉ ra bằng chứng dự kiến:

| Rủi ro | Bằng chứng kiểm thử phù hợp |
|---|---|
| Tính tiền sai khi kết hợp khuyến mại và thuế | Unit/property tests, API tests với dữ liệu biên, kiểm tra đối soát |
| Webhook bị xử lý trùng | Integration test gửi event trùng, kiểm tra idempotency và trạng thái cuối |
| Người dùng truy cập dữ liệu tenant khác | Authorization test theo vai trò và tenant, negative API tests |
| Migration làm gián đoạn dịch vụ | Rehearsal migration, đo thời gian khóa, backup/restore và rollback test |
| Pipeline không chạy hết ma trận | CI capacity test, đo queue time và xác nhận job bắt buộc |
| Dữ liệu production bị lộ trong artifact | Review dữ liệu, secret scanning, kiểm soát quyền và retention |

Một rủi ro có thể cần nhiều loại bằng chứng. Test không phải biện pháp duy nhất; monitoring, code review, threat modeling, backup và operational readiness cũng có thể giảm rủi ro.

### Liên kết với yêu cầu và defect

Gắn risk ID với requirement, test ID và defect ID. Khi test phát hiện lỗi, nhóm biết rủi ro nào đã hiện thực hóa. Khi một rủi ro chưa có test liên quan, đó có thể là khoảng trống trong chiến lược kiểm thử.

### Dùng rủi ro để xác định phạm vi hồi quy

Sau một thay đổi, xác định rủi ro nào tăng hoặc xuất hiện mới. Chọn test regression dựa trên thành phần bị ảnh hưởng, dependency và hậu quả. Không cần chạy toàn bộ suite cho mọi thay đổi nếu có phân tích tác động đáng tin, nhưng các rủi ro nghiêm trọng cần giữ kiểm tra phù hợp.

## 15. Theo dõi rủi ro theo nhịp quản lý

Danh mục chỉ có giá trị khi được cập nhật thường xuyên. Nhóm nên có nhịp xem xét phù hợp với tốc độ thay đổi và giai đoạn dự án.

### Trong cuộc họp risk review

Mỗi rủi ro đang mở cần được xem xét theo các câu hỏi:

1. Điều kiện và sự kiện mô tả còn đúng không?
2. Likelihood, impact và priority có thay đổi không?
3. Trigger hoặc chỉ báo nào đã xuất hiện?
4. Hành động đã hoàn thành chưa và có bằng chứng không?
5. Owner có còn phù hợp và có đủ thẩm quyền không?
6. Hạn xử lý có còn khả thi không?
7. Rủi ro còn lại có chấp nhận được không?
8. Có cần escalation, thay đổi phạm vi hoặc quyết định release không?

Không cần dành thời gian như nhau cho mọi mục. Ưu tiên rủi ro P0/P1, rủi ro quá hạn, rủi ro có chỉ báo xấu và rủi ro mới xuất hiện.

### Tần suất gợi ý

- Hàng ngày trong giai đoạn release hoặc khi có rủi ro khẩn cấp.
- Hàng tuần trong dự án đang phát triển tích cực.
- Mỗi sprint hoặc mỗi milestone để đồng bộ với kế hoạch.
- Trước release candidate và trước quyết định phát hành.
- Ngay sau incident, thay đổi kiến trúc hoặc sự kiện kích hoạt lớn.

Tần suất cần dựa trên mức biến động. Không nên tạo cuộc họp dày đặc nếu không có quyết định cần đưa ra; có thể cập nhật bất đồng bộ và chỉ họp khi cần xử lý.

### Cập nhật theo sự kiện

Ngoài lịch, owner cần cập nhật khi:

- Một test quan trọng fail.
- Dependency bị gián đoạn.
- Một giả định bị chứng minh sai.
- Có thay đổi phạm vi hoặc release date.
- Một biện pháp giảm thiểu không hiệu quả.
- Xuất hiện defect hoặc incident mới.
- Một chỉ số vượt ngưỡng.
- Người owner hoặc action owner thay đổi.

## 16. Báo cáo danh mục và truyền đạt cho người ra quyết định

Báo cáo risk register cần phù hợp đối tượng. Nhóm kỹ thuật cần chi tiết nguyên nhân, test và biện pháp; lãnh đạo cần biết tác động, ưu tiên, lựa chọn và quyết định cần đưa ra.

### Báo cáo tổng quan

Có thể trình bày:

- Số rủi ro mở theo P0/P1/P2/P3.
- Rủi ro mới trong kỳ.
- Rủi ro tăng mức hoặc quá hạn.
- Rủi ro chưa có owner.
- Hành động giảm thiểu đang trễ.
- Rủi ro được chấp nhận và ngày hết hiệu lực.
- Rủi ro đã xảy ra thành issue.
- Các quyết định cần lãnh đạo hỗ trợ.

Không chỉ báo cáo số lượng. Một rủi ro P0 có thể quan trọng hơn hàng chục rủi ro P3. Báo cáo nên nêu tên và hậu quả của các rủi ro quan trọng nhất.

### Báo cáo cho release decision

Với mỗi rủi ro trọng yếu, cung cấp:

- Mô tả và điều kiện kích hoạt.
- Mức ưu tiên hiện tại và xu hướng.
- Bằng chứng kiểm thử hoặc kiểm soát.
- Biện pháp đã làm và hiệu quả.
- Rủi ro còn lại.
- Owner và người có thẩm quyền.
- Lựa chọn: tiếp tục, giảm rollout, bổ sung kiểm thử, hoãn hoặc không phát hành.
- Hạn chót cần quyết định.

Risk register hỗ trợ quyết định, nhưng không tự động quyết định release. Người có thẩm quyền phải hiểu phần rủi ro còn lại và chấp nhận theo chính sách.

## 17. Chỉ số đánh giá chất lượng quản lý rủi ro

Có thể theo dõi một số chỉ số để biết quy trình có hoạt động:

| Chỉ số | Cách hiểu |
|---|---|
| Risk owner coverage | Tỷ lệ rủi ro đang mở có owner rõ ràng |
| Risk review on-time | Tỷ lệ rủi ro được xem xét đúng lịch |
| Overdue mitigation actions | Số hành động giảm thiểu quá hạn |
| High-priority open risks | Số rủi ro ưu tiên cao chưa được xử lý |
| Risk age | Thời gian rủi ro tồn tại ở trạng thái mở |
| Escalation lead time | Thời gian từ lúc vượt ngưỡng đến khi được đưa ra quyết định |
| Mitigation effectiveness | Tỷ lệ biện pháp được xác minh có giảm rủi ro |
| Reopened risk rate | Tỷ lệ rủi ro đã đóng nhưng phải mở lại |
| Accepted risk expiry | Số rủi ro accepted sắp hết thời hạn |

Các chỉ số phải có định nghĩa và mẫu số rõ. Ví dụ, owner coverage có thể tính trên rủi ro mở trong kỳ; không tính các mục đã đóng nếu tổ chức không yêu cầu owner sau đóng.

Không nên dùng chỉ số để thưởng cho việc đóng nhiều rủi ro. Điều đó có thể khiến nhóm hạ mức, đổi trạng thái hoặc chấp nhận rủi ro quá dễ. Mục tiêu là hiểu và quản lý rủi ro thực chất.

## 18. Ví dụ thực hành: lập risk register cho release thanh toán

Giả sử một phiên bản mới thay đổi checkout, tích hợp cổng thanh toán và cập nhật schema đơn hàng. Nhóm tổ chức workshop với product owner, test lead, developer, security và SRE. Sau khi phân tích yêu cầu, kiến trúc và lịch sử incident, nhóm lập danh mục ban đầu:

| ID | Phát biểu rủi ro | L | I | Điểm | Ưu tiên | Risk owner |
|---|---|---:|---:|---:|---|---|
| R-01 | Do webhook có thể được gửi lại, nếu xử lý thiếu idempotency thì trạng thái đơn có thể bị cập nhật trùng | 4 | 5 | 20 | P0 | Payment service owner |
| R-02 | Do migration chưa được rehearsal trên dữ liệu đại diện, khi nâng cấp có thể khóa bảng lâu hoặc chuyển đổi thiếu dữ liệu | 3 | 5 | 15 | P1 | Database owner |
| R-03 | Do test quyền tenant chưa bao phủ API mới, người dùng có thể đọc dữ liệu đơn hàng của tenant khác | 3 | 5 | 15 | P0 | Security owner |
| R-04 | Do sandbox có quota và thời gian khả dụng biến động, nhóm có thể không hoàn thành kiểm thử tích hợp trước release | 4 | 3 | 12 | P1 | Integration owner |
| R-05 | Do runner CI có giới hạn song song, ma trận browser có thể hoàn tất muộn hơn cửa sổ release | 3 | 3 | 9 | P2 | CI platform owner |

L và I là điểm likelihood và impact theo thang đã định nghĩa. P0/P1/P2 là quyết định ưu tiên sau khi xem xét cả điểm số, hậu quả đặc biệt và thời điểm phát hành. Ví dụ R-03 được xếp P0 vì liên quan truy cập dữ liệu tenant, dù điểm số bằng R-02.

### Bước 1: xác định hành động

| ID | Hành động giảm thiểu | Action owner | Hạn |
|---|---|---|---|
| R-01 | Bổ sung idempotency key, test webhook trùng/đến trễ và xác minh trạng thái cuối | Payment developer + QA | Trước release candidate |
| R-02 | Rehearsal migration trên bản sao dữ liệu, đo thời gian khóa, thử restore | DBA + service developer | Trước khi duyệt release |
| R-03 | Thêm negative authorization tests theo tenant và review policy | Security engineer + API owner | Trước merge release branch |
| R-04 | Đặt lịch sandbox, tạo contract test và mock cho logic không phụ thuộc thật | Integration engineer | Trong sprint |
| R-05 | Ưu tiên job trọng yếu, giới hạn ma trận PR và chạy phần mở rộng theo lịch | CI platform engineer | Trước tuần release |

Risk owner vẫn chịu trách nhiệm theo dõi tổng thể. Action owner thực hiện từng việc và cung cấp bằng chứng.

### Bước 2: xác định chỉ báo và contingency

- R-01: số webhook trùng hoặc giao dịch có trạng thái không nhất quán; nếu phát hiện, dừng xử lý tự động liên quan và chạy đối soát.
- R-02: thời gian migration, lock duration và lỗi chuyển đổi; nếu vượt ngưỡng, hoãn rollout và dùng phương án restore đã diễn tập.
- R-03: bất kỳ truy cập chéo tenant nào đều kích hoạt escalation bảo mật và chặn release theo chính sách.
- R-04: sandbox không khả dụng vượt thời gian cho phép; chuyển sang test hợp đồng/mô phỏng cho phạm vi phù hợp và báo rõ khoảng trống tích hợp thật.
- R-05: queue time hoặc thời gian hoàn tất vượt ngưỡng; ưu tiên job bắt buộc và điều chỉnh lịch chạy.

### Bước 3: đánh giá lại sau giảm thiểu

Sau khi hành động hoàn tất, nhóm chạy test và xem bằng chứng. R-01 có thể giảm likelihood nếu idempotency đã được xác minh với event trùng và retry. R-02 vẫn có residual risk nếu rehearsal chỉ dùng tập dữ liệu nhỏ hơn production. R-04 có thể còn rủi ro tích hợp thật nếu sandbox chưa phục hồi.

Owner cập nhật điểm, trạng thái, bằng chứng và ngày xem xét. Người có thẩm quyền quyết định liệu rủi ro còn lại có chấp nhận được cho release hay cần hoãn.

## 19. Mẫu risk register có thể sử dụng

Có thể bắt đầu với bảng sau và điều chỉnh theo quy trình của nhóm:

~~~text
Risk ID:
Title:
Product / Release:
Category:
Date identified:

Risk statement:
Cause:
Uncertain event:
Potential consequence:

Likelihood (1-5):
Impact (1-5):
Risk score:
Urgency:
Detectability:
Priority:
Scoring rationale:

Risk owner:
Action owner(s):
Decision owner / approver:

Current controls:
Mitigation actions:
Contingency / rollback:
Trigger or warning indicator:

Target date:
Next review date:
Status:
Residual likelihood:
Residual impact:
Residual score:

Evidence / related requirements:
Related test IDs:
Related defects / incidents:
Decision and acceptance record:
Last updated:
~~~

Nếu dùng spreadsheet, nên thêm bộ lọc theo priority, owner, status, due date và category. Nếu dùng công cụ quản lý issue, mỗi risk item cần có ID ổn định, trường tùy chỉnh và liên kết giữa risk, action, defect và release.

### Ví dụ một bản ghi hoàn chỉnh

~~~text
Risk ID: R-01
Title: Webhook thanh toán có thể xử lý lặp
Product / Release: Checkout release
Category: Integration / Data integrity

Risk statement:
Do nhà cung cấp có thể gửi lại webhook sau timeout, nếu
dịch vụ không xử lý idempotent thì một giao dịch có thể
cập nhật trạng thái đơn hàng nhiều lần, dẫn đến đối soát sai.

Likelihood: 4 - Cao
Impact: 5 - Rất cao
Risk score: 20
Priority: P0

Risk owner: Payment service owner
Action owner: Payment developer
Decision owner: Release owner

Current controls:
Có log webhook và khóa giao dịch theo transaction ID.

Mitigation actions:
Bổ sung idempotency key; test event trùng, đến trễ,
sai thứ tự và retry sau timeout.

Contingency:
Tạm dừng consumer, đối soát giao dịch và chạy replay
sau khi xác minh dữ liệu.

Trigger:
Tỷ lệ webhook trùng hoặc trạng thái giao dịch không khớp
vượt ngưỡng vận hành.

Target date: Trước release candidate
Next review date: Tại buổi risk review tiếp theo
Status: Mitigating

Residual risk:
Chưa đánh giá; cần hoàn tất test tích hợp và review log.

Evidence:
Liên kết test report, defect và ticket triển khai.
~~~

Đây là ví dụ minh họa. Không dùng tên người hoặc dữ liệu nhạy cảm trong bản ghi chia sẻ rộng. Với rủi ro bảo mật, giới hạn quyền xem chi tiết khi cần thiết nhưng vẫn bảo đảm người có thẩm quyền truy cập được.

## 20. Những sai lầm thường gặp

- **Ghi rủi ro quá chung chung:** không biết sự kiện nào có thể xảy ra hoặc cần hành động gì.
- **Nhầm issue với risk:** vấn đề đã xảy ra không được xử lý như công việc đang chờ trong tương lai.
- **Chấm điểm theo cảm giác:** các thành viên hiểu thang điểm khác nhau và không có căn cứ.
- **Chỉ dùng điểm số:** bỏ qua hậu quả đặc biệt, urgency, khả năng phát hiện và yêu cầu bắt buộc.
- **Không có owner:** rủi ro tồn tại nhưng không ai theo dõi đến cùng.
- **Giao một owner cho cả danh sách không liên quan:** trách nhiệm bị phân tán và khó điều phối.
- **Nhầm risk owner với action owner:** người chịu trách nhiệm tổng thể và người thực hiện hành động không rõ.
- **Không có hạn và trigger:** không biết khi nào cần cập nhật hoặc escalation.
- **Chỉ ghi hành động, không ghi bằng chứng:** không xác định được biện pháp có hiệu quả không.
- **Đóng rủi ro khi ticket hoàn tất:** rủi ro còn lại vẫn tồn tại nhưng bị loại khỏi theo dõi.
- **Chấp nhận rủi ro không có thẩm quyền:** quyết định vượt phạm vi trách nhiệm của người ghi nhận.
- **Không đánh giá residual risk:** coi biện pháp đã triển khai là rủi ro đã biến mất.
- **Không liên kết với test và release:** danh mục trở thành tài liệu hành chính, không ảnh hưởng đến ưu tiên kiểm thử.
- **Không rà soát lại:** likelihood và impact cũ không còn phản ánh điều kiện hiện tại.
- **Tạo quá nhiều mục trùng lặp:** danh mục phình to và khó xác định rủi ro chính.
- **Chỉ báo cáo số lượng:** lãnh đạo không thấy hậu quả và quyết định cần đưa ra.

## 21. Danh sách kiểm tra khi lập và duy trì risk register

**Nhận diện và mô tả**

- Rủi ro có liên kết với mục tiêu, yêu cầu hoặc thành phần cụ thể không?
- Phát biểu có phân biệt nguyên nhân, sự kiện và hậu quả không?
- Rủi ro có bị nhầm với issue, assumption hoặc dependency không?
- Có xem xét lịch sử defect, incident, thay đổi và phụ thuộc không?
- Các rủi ro trùng lặp đã được hợp nhất hoặc liên kết chưa?

**Đánh giá và ưu tiên**

- Thang likelihood và impact có định nghĩa rõ không?
- Điểm số có căn cứ và cùng một quy tắc giữa các nhóm không?
- Urgency, detectability và thời điểm phơi nhiễm đã được xem xét chưa?
- Rủi ro nghiêm trọng hoặc bắt buộc có quy tắc override không?
- Mức ưu tiên có dẫn đến hành động và escalation cụ thể không?

**Owner và hành động**

- Mỗi rủi ro mở có một risk owner cụ thể không?
- Action owner có được phân công cho từng biện pháp không?
- Owner có đủ quyền, kỹ năng và thời gian theo dõi không?
- Có hạn hoàn thành, trigger và ngày review tiếp theo không?
- Có contingency hoặc rollback cho rủi ro quan trọng không?

**Theo dõi và quyết định**

- Trạng thái có phản ánh đúng vòng đời không?
- Bằng chứng thực hiện và hiệu quả giảm thiểu có được liên kết không?
- Residual risk đã được đánh giá lại chưa?
- Người chấp nhận rủi ro có đúng thẩm quyền không?
- Rủi ro quá hạn, tăng mức hoặc đã xảy ra có được escalation không?
- Risk register có liên kết với test plan, defect và release decision không?

## Kết luận

Risk register giúp nhóm kiểm thử biến những điều bất định thành thông tin có thể đánh giá, giao trách nhiệm và theo dõi. Mỗi rủi ro cần được mô tả bằng nguyên nhân, sự kiện và hậu quả; đánh giá theo thang likelihood và impact có định nghĩa; sau đó xếp ưu tiên dựa trên điểm số, mức nghiêm trọng, urgency và điều kiện thực tế. Một risk owner chịu trách nhiệm theo dõi tổng thể, còn action owner thực hiện biện pháp cụ thể. Danh mục cần ghi hạn, trigger, bằng chứng, trạng thái, residual risk và người có quyền chấp nhận. Khi được rà soát theo lịch và theo sự kiện, liên kết với test và release, risk register trở thành công cụ điều phối kiểm thử và hỗ trợ quyết định chất lượng có căn cứ.
