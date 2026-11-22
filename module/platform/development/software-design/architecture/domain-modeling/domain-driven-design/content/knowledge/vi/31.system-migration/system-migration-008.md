# Đo hiệu quả qua khả năng hiểu mô hình và chi phí thay đổi nghiệp vụ

Một hệ thống được tổ chức theo Domain-Driven Design (DDD) không thành công chỉ vì có nhiều bounded context, Aggregate, Value Object hay Domain Event. Những cấu trúc đó chỉ có giá trị khi giúp đội phát triển hiểu đúng nghiệp vụ, tìm được nơi sở hữu quy tắc và thực hiện thay đổi với ít công sức phối hợp, ít lỗi và thời gian hợp lý hơn.

Khi đánh giá một chương trình chuyển đổi hệ thống hoặc tái cấu trúc theo DDD, cần đo hai kết quả quan trọng: **khả năng hiểu mô hình nghiệp vụ** và **chi phí thay đổi nghiệp vụ**. Khả năng hiểu mô hình cho biết người phát triển có thể giải thích ngôn ngữ, quy tắc, ownership và luồng nghiệp vụ đến đâu. Chi phí thay đổi cho biết cần bao nhiêu thời gian, công sức, phối hợp và sửa lỗi để đưa một yêu cầu nghiệp vụ từ lúc được hiểu đến khi vận hành an toàn.

Không có một chỉ số đơn lẻ đại diện đầy đủ cho hai kết quả này. Số bounded context, số class, độ phủ test hay số dòng code có thể mô tả một phần cấu trúc nhưng không chứng minh hệ thống dễ hiểu hoặc dễ thay đổi. Bài học này trình bày cách thiết lập baseline, chọn chỉ số định lượng và định tính, đánh giá bằng nhiệm vụ thực tế, theo dõi chi phí thay đổi theo vòng đời và dùng kết quả để điều chỉnh chiến lược DDD.

## 1. Đo kết quả thay vì đếm cấu trúc

DDD cung cấp các công cụ để xây dựng mô hình và ranh giới: ubiquitous language, subdomain, bounded context, Context Map, Entity, Value Object, Aggregate, Repository và Domain Event. Việc áp dụng một pattern không tự động tạo ra kết quả tốt.

Ví dụ:

- Tách một ứng dụng thành 12 service không chứng minh ownership đã rõ.
- Tạo 40 Aggregate không chứng minh invariant được bảo vệ đúng.
- Có event cho mọi thao tác CRUD không chứng minh các context giao tiếp theo ngôn ngữ nghiệp vụ.
- Độ phủ unit test cao không chứng minh một thay đổi liên context có thể được thực hiện an toàn.
- Một module có ít dependency không có nghĩa người mới hiểu được quy tắc của nó.

Vì vậy, hãy đặt câu hỏi về kết quả quan sát được:

- Một developer mới có giải thích đúng quy trình nghiệp vụ mà không cần hỏi quá nhiều người không?
- Họ có tìm được context sở hữu quy tắc cần thay đổi không?
- Một yêu cầu có phạm vi rõ cần chạm vào bao nhiêu module và team?
- Từ lúc yêu cầu đủ rõ đến khi thay đổi được phát hành mất bao lâu?
- Bao nhiêu công sức dành cho điều tra, phối hợp, sửa lại và xử lý lỗi sau phát hành?
- Sau thay đổi, hệ thống có giữ được invariant và contract giữa các context không?

Đó là những câu hỏi gắn trực tiếp với mục tiêu của thiết kế dễ hiểu và dễ tiến hóa.

## 2. Hai nhóm kết quả cần đo

### 2.1. Khả năng hiểu mô hình nghiệp vụ

Khả năng hiểu mô hình là mức độ một người có thể đọc, giải thích và sử dụng mô hình để đưa ra quyết định kỹ thuật đúng. Nó gồm nhiều năng lực:

- Hiểu thuật ngữ trong ubiquitous language và dùng chúng nhất quán.
- Phân biệt các khái niệm giống tên nhưng khác nghĩa giữa các bounded context.
- Xác định context sở hữu dữ liệu và quy tắc.
- Giải thích invariant của Aggregate và vì sao hành vi được đặt tại đó.
- Lần theo command, event và luồng xử lý xuyên context.
- Dự đoán tác động của một thay đổi nghiệp vụ.
- Tìm được tài liệu, code và người chịu trách nhiệm khi cần làm rõ.

### 2.2. Chi phí thay đổi nghiệp vụ

Chi phí thay đổi không chỉ là thời gian sửa code. Nó gồm toàn bộ nỗ lực cần để biến một yêu cầu thành kết quả được phát hành và vận hành ổn định:

- Làm rõ yêu cầu và khám phá mô hình.
- Tìm vị trí sở hữu quy tắc.
- Thiết kế và thực hiện thay đổi.
- Cập nhật contract, migration hoặc dữ liệu.
- Phối hợp giữa developer, team và chuyên gia nghiệp vụ.
- Viết/chạy test, review và xử lý CI.
- Triển khai, theo dõi, khắc phục và làm lại khi có lỗi.

Hai nhóm kết quả liên quan nhưng không đồng nhất. Mô hình dễ hiểu có thể giúp giảm chi phí điều tra, nhưng chi phí thay đổi còn phụ thuộc kiến trúc triển khai, quy trình release, dữ liệu và hệ thống bên ngoài.

## 3. Thiết lập baseline trước khi chuyển đổi

Không thể kết luận một chương trình DDD cải thiện hệ thống nếu không biết trạng thái ban đầu. Trước khi tái cấu trúc, hãy thu thập baseline từ một giai đoạn đủ đại diện.

Baseline nên bao gồm:

- Một tập yêu cầu nghiệp vụ đã hoàn thành gần đây, có mức độ phức tạp tương đối rõ.
- Thời gian từ lúc yêu cầu sẵn sàng đến production.
- Effort theo hoạt động: phân tích, tìm hiểu, code, test, review, phối hợp, sửa lỗi.
- Số module/service/team bị ảnh hưởng.
- Số lần phải sửa lại vì hiểu sai nghiệp vụ hoặc bỏ sót dependency.
- Defect và incident có liên quan đến thay đổi.
- Kết quả một số bài đánh giá khả năng hiểu mô hình.
- Mức độ đầy đủ của glossary, context map, invariant và ownership documentation.

Không cần đo mọi thứ trong toàn bộ codebase ngay từ đầu. Chọn một vài luồng nghiệp vụ quan trọng và một tập thay đổi đủ đa dạng để có thể so sánh về sau.

### 3.1. Chọn giai đoạn baseline hợp lý

Một tuần có thể quá ngắn nếu hệ thống phát hành theo chu kỳ tháng; một năm có thể quá dài và chứa nhiều thay đổi tổ chức. Chọn khoảng thời gian phản ánh nhịp làm việc thực tế, ví dụ vài chu kỳ release hoặc một quý, tùy quy mô.

Ghi lại những yếu tố có thể làm sai lệch kết quả: thay đổi nhân sự, nâng cấp nền tảng, thay quy trình review, giảm tải công việc, mùa cao điểm hoặc thay đổi mức độ phức tạp của yêu cầu.

### 3.2. Không so sánh các yêu cầu khác độ khó

Một thay đổi sửa nhãn giao diện không thể so sánh trực tiếp với thay đổi chính sách hoàn tiền xuyên Payment, Sales và Fulfillment. Phân loại yêu cầu theo độ phức tạp, phạm vi, mức độ rủi ro và số context liên quan trước khi so sánh.

## 4. Đo khả năng hiểu mô hình bằng nhiệm vụ thực tế

Khảo sát “bạn thấy code có dễ hiểu không?” có thể cung cấp cảm nhận nhưng thường không đủ để đánh giá năng lực hiểu mô hình. Một cách đáng tin cậy hơn là giao các nhiệm vụ có đáp án hoặc rubric rõ.

Ví dụ nhiệm vụ:

1. Giải thích khi nào một Order được xác nhận và ai có quyền quyết định.
2. Xác định context sở hữu lượng hàng khả dụng và reservation.
3. Tìm invariant ngăn một đơn đặt vượt số lượng có thể giữ.
4. Vẽ luồng từ `ReserveStock` đến `StockReserved` và nơi cập nhật trạng thái đơn.
5. Chỉ ra nơi cần thay đổi khi chính sách hủy đơn thay đổi.
6. Giải thích khác biệt giữa `Customer` trong Sales và Customer Support nếu hai context có mô hình riêng.

Ghi lại thời gian hoàn thành, độ chính xác, số lần cần trợ giúp và số lần phải đọc lại code/tài liệu. Không chỉ đo tốc độ; một câu trả lời nhanh nhưng sai ownership là kết quả xấu.

### 4.1. Rubric chấm khả năng hiểu

Có thể dùng thang điểm 0–4 cho từng nhiệm vụ:

| Điểm | Mô tả |
|---|---|
| 0 | Không xác định được khái niệm hoặc đưa ra giải thích sai cơ bản |
| 1 | Nhận ra một số thuật ngữ nhưng nhầm ownership hoặc quy tắc chính |
| 2 | Giải thích được luồng cơ bản nhưng bỏ sót điều kiện hoặc ngoại lệ quan trọng |
| 3 | Giải thích đúng thuật ngữ, ownership, invariant và luồng chính |
| 4 | Ngoài mức 3, còn dự đoán được tác động của thay đổi và chỉ ra các rủi ro/ngoại lệ liên quan |

Rubric phải được điều chỉnh theo nhiệm vụ. Ví dụ, bài kiểm tra Aggregate không nên yêu cầu người làm nhớ tên package; nó cần kiểm tra họ hiểu invariant và trách nhiệm nghiệp vụ.

### 4.2. Dùng cả người mới và người có kinh nghiệm

Người đã làm dự án nhiều năm có thể trả lời tốt nhờ kiến thức tích lũy dù mô hình khó hiểu. Hãy phân biệt:

- Người mới với module hoặc bounded context.
- Người đã làm việc lâu trong vùng đó.
- Người đến từ context khác nhưng cần tích hợp.

Thời gian onboarding và mức độ phụ thuộc vào người nắm kiến thức độc quyền là tín hiệu quan trọng. Tuy nhiên, không dùng kết quả để xếp hạng cá nhân; mục tiêu là tìm chỗ mô hình và tài liệu chưa đủ rõ.

## 5. Chỉ số định lượng cho khả năng hiểu mô hình

Một số chỉ số có thể thu thập:

| Chỉ số | Cách đo | Ý nghĩa |
|---|---|---|
| Task comprehension score | Điểm rubric trên nhiệm vụ nghiệp vụ | Mức chính xác khi giải thích mô hình |
| Time to locate rule | Thời gian tìm đúng nơi sở hữu quy tắc | Khả năng định vị ownership |
| Onboarding time | Thời gian để người mới hoàn thành một nhiệm vụ có phạm vi | Khả năng tiếp cận mô hình |
| Clarification count | Số lần phải hỏi người khác để hoàn thành nhiệm vụ | Mức phụ thuộc vào tri thức ngầm |
| Wrong-owner rate | Tỷ lệ nhiệm vụ ban đầu xác định sai context/module owner | Độ rõ của ranh giới |
| Rework due to misunderstanding | Effort sửa lại do hiểu sai domain | Chất lượng hiểu biết ban đầu |

Các chỉ số nên được xem theo nhóm và xu hướng, không dùng một lần đo để kết luận. Một yêu cầu mới hoặc người thực hiện chưa quen công nghệ có thể làm thời gian tăng dù mô hình không thay đổi.

## 6. Đo chi phí thay đổi nghiệp vụ

Để hiểu chi phí thay đổi, hãy đo cả elapsed time và effort. Hai khái niệm này trả lời câu hỏi khác nhau.

- **Elapsed time:** thời gian lịch từ mốc bắt đầu đến mốc hoàn thành.
- **Effort:** tổng thời gian con người thực sự làm việc cho thay đổi.

Một thay đổi có thể mất 10 ngày lịch nhưng chỉ 2 ngày công vì phải chờ phê duyệt hoặc lịch release. Một thay đổi khác mất 3 ngày lịch và gần 3 ngày công vì implementation phức tạp. Nếu chỉ đo lead time, không biết chi phí đến từ chờ đợi hay công việc thực tế.

### 6.1. Các thành phần effort

Ghi effort theo nhóm:

- Discovery và làm rõ nghiệp vụ.
- Tìm hiểu code và dependency.
- Thiết kế domain model và contract.
- Implementation.
- Unit, integration, contract và acceptance testing.
- Review, sửa review và CI.
- Phối hợp team hoặc nhà cung cấp.
- Migration, rollout và theo dõi.
- Rework và xử lý defect sau phát hành.

Không nhất thiết phải tracking đến từng phút. Một phân loại nhất quán theo giờ hoặc ngày công thường hữu ích hơn một hệ thống timesheet quá chi tiết nhưng thiếu tin cậy.

### 6.2. Change lead time

Chọn mốc bắt đầu và kết thúc nhất quán. Ví dụ:

\[
LeadTime = ProductionAt - ReadyForDevelopmentAt
\]

Trong đó `ReadyForDevelopmentAt` là lúc yêu cầu đã đủ thông tin để bắt đầu thực hiện, còn `ProductionAt` là thời điểm thay đổi sẵn sàng cho người dùng production. Nếu tổ chức muốn đo từ lúc yêu cầu được đề xuất, hãy ghi thêm một chỉ số khác; không trộn hai định nghĩa.

### 6.3. Change effort

\[
TotalEffort = Discovery + Design + Implementation + Verification + Release + Rework
\]

Các thành phần phải tránh tính trùng. Nếu nhiều người làm song song, tổng effort có thể lớn hơn elapsed time. Cần lưu cả hai khi muốn hiểu chi phí phối hợp.

## 7. Đo phạm vi ảnh hưởng của thay đổi

Một thiết kế có ranh giới tốt thường giúp thay đổi tập trung ở nơi sở hữu quy tắc. Có thể theo dõi:

- Số bounded context/module cần sửa.
- Số service/repository/schema bị chạm tới.
- Số contract phải thay đổi.
- Số team cần phối hợp.
- Số deployment hoặc release phải đồng bộ.
- Số consumer bị ảnh hưởng.
- Số bước migration dữ liệu cần thực hiện.

Có thể gọi tập hợp này là *change impact radius*. Đây là chỉ số mô tả phạm vi, không phải kết luận rằng thay đổi càng ít module luôn càng tốt. Một yêu cầu thực sự xuyên nhiều context thì việc chạm nhiều context là đúng. Điều cần quan sát là các thay đổi lan rộng không cần thiết vì consumer phụ thuộc vào chi tiết nội bộ.

### 7.1. Ví dụ

Thay đổi quy tắc tính phí giao hàng có thể hợp lý khi tập trung ở Shipping/Pricing context và contract kết quả được Sales sử dụng. Nếu phải sửa trực tiếp Entity của Sales, Inventory và Payment chỉ vì các module dùng chung một `OrderEntity`, đây là dấu hiệu ownership và shared model cần xem lại.

### 7.2. Phân biệt phạm vi cần thiết và phạm vi do coupling

Trong review sau thay đổi, ghi rõ module nào bị tác động vì yêu cầu nghiệp vụ thật sự, module nào bị tác động vì dependency kỹ thuật. Chỉ số impact radius cần đi kèm phân tích nguyên nhân, nếu không nó có thể khuyến khích gom mọi thứ vào một module để giảm số lượng thay đổi bề ngoài.

## 8. Đo chất lượng thay đổi sau khi phát hành

Một thay đổi ít effort nhưng tạo nhiều defect không phải là thay đổi rẻ. Chi phí cần được đánh giá đến khi thay đổi ổn định.

Các chỉ số liên quan:

- **Change failure rate:** tỷ lệ thay đổi dẫn đến rollback, hotfix hoặc incident theo định nghĩa thống nhất.
- **Escaped defects:** lỗi được phát hiện sau khi qua các tầng kiểm thử trước production.
- **Regression count:** số lỗi làm hỏng hành vi vốn đã hoạt động.
- **Rework effort:** công sức sửa lại sau review, test hoặc production.
- **Recovery time:** thời gian khôi phục khi thay đổi gây sự cố.
- **Support/operation cost:** công sức hỗ trợ vận hành phát sinh do thay đổi.

Không quy mọi incident cho DDD hoặc kiến trúc. Phân loại nguyên nhân: hiểu sai nghiệp vụ, thiếu invariant, contract không tương thích, dữ liệu migration, lỗi triển khai, cấu hình hoặc phụ thuộc ngoài.

## 9. Chỉ số từ DDD: hữu ích nhưng không phải mục tiêu tự thân

Một số đặc điểm cấu trúc có thể hỗ trợ giải thích kết quả:

| Đặc điểm | Có thể quan sát | Cần tránh kết luận vội |
|---|---|---|
| Bounded Context | Ownership, glossary, contract, dependency | Nhiều context không có nghĩa mô hình tốt hơn |
| Aggregate | Invariant, transaction boundary, hành vi công khai | Nhiều Aggregate không chứng minh invariant đúng |
| Ubiquitous Language | Mức nhất quán thuật ngữ giữa tài liệu, code và trao đổi | Tên class tiếng Anh không chứng minh có ngôn ngữ chung |
| Context Map | Quan hệ, upstream/downstream, ACL, integration contract | Sơ đồ đẹp không chứng minh contract đang được tuân thủ |
| Domain Event | Event có ngữ nghĩa, consumer và lifecycle | Số event nhiều không đồng nghĩa coupling thấp |
| Module cohesion | Tập trung trách nhiệm, lý do thay đổi | Ít package hoặc class không tự chứng minh cohesion cao |
| Dependency graph | Cycle, dependency direction, public surface | Chỉ số static không phản ánh hết semantic coupling |

Các chỉ số cấu trúc là leading indicators hoặc bằng chứng giải thích. Kết quả quan trọng vẫn là người phát triển hiểu mô hình và thực hiện thay đổi nghiệp vụ tốt hơn.

## 10. Xây dựng bộ đo cân bằng

Không nên dùng một KPI duy nhất. Có thể tạo một bảng đo gồm bốn góc nhìn:

1. **Understanding:** người phát triển hiểu domain model và ownership.
2. **Change flow:** thay đổi được thực hiện nhanh và ít phối hợp hơn.
3. **Quality:** thay đổi giữ invariant và ít tạo lỗi.
4. **Sustainability:** mô hình, tài liệu và kiến thức có thể được duy trì qua thay đổi nhân sự.

Ví dụ bộ chỉ số:

| Góc nhìn | Chỉ số chính | Chỉ số bổ trợ |
|---|---|---|
| Understanding | Task comprehension score | Time to locate rule, onboarding time |
| Change flow | Median lead time, total effort | Impact radius, coordination effort |
| Quality | Change failure rate | Escaped defects, rework effort |
| Sustainability | Wrong-owner rate, knowledge concentration | Documentation freshness, bus factor signals |

Không cần đo tất cả cùng lúc. Chọn 1–3 chỉ số chính cho mỗi giai đoạn và giữ định nghĩa ổn định đủ lâu để so sánh.

## 11. Đánh giá trước và sau chuyển đổi

Một cách thực tế là chọn các luồng nghiệp vụ có mức độ quan trọng cao, đo baseline, thực hiện chuyển đổi theo từng phần rồi đo lại trên các loại thay đổi tương đương.

Quy trình:

1. Chọn một capability hoặc bounded context có pain point rõ.
2. Thu thập 5–10 thay đổi gần đây nếu dữ liệu sẵn có; phân loại theo độ phức tạp.
3. Đo task comprehension trên cùng một bộ nhiệm vụ hoặc bộ tương đương.
4. Ghi elapsed time, effort, impact radius, rework và defect.
5. Làm rõ mục tiêu của thay đổi kiến trúc, ví dụ ownership tồn kho hoặc chính sách refund.
6. Chuyển đổi theo từng bước, giữ lại các định nghĩa đo lường.
7. Sau khi mô hình và quy trình ổn định, đo trên các thay đổi mới có độ phức tạp tương đương.
8. Phân tích chênh lệch và nguyên nhân, không chỉ so sánh số trung bình.

Nếu có thể, dùng một capability tương tự chưa chuyển đổi làm nhóm so sánh tạm thời. Tuy nhiên, hai capability có thể khác nhau về team, dữ liệu và độ phức tạp; cần ghi nhận các khác biệt thay vì tuyên bố quan hệ nhân quả chắc chắn.

## 12. Ví dụ: đo thay đổi chính sách hủy đơn

Giả sử hệ thống cũ có logic hủy đơn nằm rải rác trong Order Service, Inventory Service và Payment Service. Một thay đổi chính sách mới yêu cầu:

- Đơn chưa thanh toán có thể hủy và giải phóng hàng.
- Đơn đã authorize nhưng chưa capture phải void authorization.
- Đơn đã capture cần refund theo điều kiện thời hạn.
- Shipment đã bàn giao cho carrier cần chuyển sang quy trình return.

Trước chuyển đổi, đội phát triển mất thời gian tìm logic ở nhiều nơi, gọi các owner để xác nhận trạng thái và thường bỏ sót nhánh refund hoặc shipment.

Sau khi làm rõ bounded context:

- Sales sở hữu trạng thái và chính sách vòng đời Order.
- Inventory sở hữu Reservation và hành vi release.
- Payment sở hữu authorization, capture và refund.
- Fulfillment sở hữu Shipment và return.
- Một process manager điều phối các bước khi cần.

Đội có thể đo:

| Chỉ số | Trước | Sau | Cách diễn giải |
|---|---:|---:|---|
| Thời gian tìm nơi sở hữu quy tắc | 3 giờ | 45 phút | Ownership rõ hơn nếu nhiệm vụ tương đương |
| Số module bị sửa | 7 | 4 | Giảm tác động kỹ thuật ngoài phạm vi; vẫn cần xem các context thực sự liên quan |
| Effort làm rõ nghiệp vụ | 10 giờ | 5 giờ | Glossary và trạng thái rõ hơn có thể giảm hỏi lại |
| Rework do bỏ sót nhánh | 8 giờ | 2 giờ | Cần theo dõi qua nhiều thay đổi để xác nhận xu hướng |
| Lead time | 12 ngày | 8 ngày | Chỉ so sánh khi độ phức tạp và release process tương đương |

Các số liệu trên chỉ là ví dụ minh họa, không phải chuẩn benchmark. Kết luận cần dựa trên dữ liệu thật của tổ chức và được điều chỉnh theo thay đổi về team, quy trình, công nghệ hoặc mức độ yêu cầu.

## 13. Đo chi phí phối hợp giữa các team

DDD có thể làm rõ ranh giới và trách nhiệm, nhưng nếu Context Map hoặc contract không tốt, các team vẫn phải phối hợp quá nhiều.

Có thể đo:

- Số team tham gia một thay đổi.
- Số lần chờ quyết định hoặc chờ review từ team khác.
- Thời gian chờ contract hoặc schema được cập nhật.
- Số lần phải tổ chức họp để xác định owner.
- Số thay đổi yêu cầu release đồng bộ.
- Effort xử lý dependency breaking.

Một thay đổi xuyên nhiều context không phải lúc nào cũng là dấu hiệu thiết kế kém. Điều cần giảm là chi phí phối hợp không tạo giá trị: chờ người biết code, tranh luận ownership không có tài liệu, hoặc phải sửa consumer vì provider thay đổi implementation nội bộ.

### 13.1. Liên hệ với Conway's Law

Ranh giới phần mềm và cách tổ chức team thường ảnh hưởng lẫn nhau. Nếu một capability cần quyết định từ nhiều nhóm nhưng không có owner rõ, chi phí phối hợp có thể cao dù code được chia thành module. Đo lường nên xem cả cấu trúc kỹ thuật lẫn luồng giao tiếp và quyền quyết định của tổ chức.

## 14. Đo mức độ phụ thuộc vào tri thức cá nhân

Một hệ thống khó hiểu thường có một số người nắm phần lớn tri thức không được ghi lại. Có thể quan sát:

- Tỷ lệ nhiệm vụ cần một hoặc vài cá nhân cụ thể trợ giúp.
- Số module không có owner hoặc backup owner rõ.
- Tỷ lệ quy tắc quan trọng không có glossary/specification.
- Thời gian người khác cần để hoàn thành nhiệm vụ mà không có tác giả ban đầu.
- Số lần thay đổi bị chặn vì người hiểu hệ thống không sẵn sàng.

Không dùng các chỉ số này để đổ lỗi cho cá nhân hoặc ép mọi người viết tài liệu hình thức. Chúng chỉ ra rủi ro tri thức tập trung và nơi cần cải thiện mô hình, pairing, documentation hoặc ownership.

## 15. Đo chất lượng ubiquitous language và tài liệu mô hình

Ubiquitous Language có giá trị khi cùng một thuật ngữ được dùng nhất quán trong trao đổi, tài liệu và code, đồng thời có nghĩa rõ trong một bounded context.

Có thể kiểm tra:

- Một thuật ngữ có định nghĩa và ví dụ nghiệp vụ không?
- Code dùng tên phản ánh thuật ngữ đó hay dùng tên kỹ thuật chung chung?
- Các team có đang dùng cùng một từ cho các khái niệm khác nhau không?
- Người mới có phân biệt được các nghĩa theo context không?
- Khi thuật ngữ thay đổi, tài liệu và code có được cập nhật cùng nhau không?

Một glossary tốt không cần dài. Nó cần giúp người đọc phân biệt khái niệm dễ nhầm và tìm đúng nơi có thẩm quyền. Tài liệu nên được đặt gần code hoặc có liên kết đến module sở hữu để tránh lỗi thời.

### 15.1. Freshness của tài liệu

Có thể đo tỷ lệ tài liệu quan trọng đã được review sau thay đổi mô hình, nhưng không nên chỉ đo số trang. Một trang ngắn có sơ đồ và invariant chính xác có thể hữu ích hơn một tài liệu dài nhưng không được cập nhật.

## 16. Phân tích phân phối, không chỉ số trung bình

Lead time và effort thường có phân phối lệch: phần lớn thay đổi nhỏ hoàn thành nhanh, nhưng một số thay đổi lớn kéo dài nhiều tuần. Số trung bình có thể bị một vài ngoại lệ chi phối.

Nên xem:

- Median (trung vị).
- Percentile 75 hoặc 90.
- Phân bố theo loại yêu cầu và độ phức tạp.
- Xu hướng theo tháng/quý.
- Outlier và nguyên nhân cụ thể.

Ví dụ median lead time giảm nhưng p90 tăng có thể cho thấy thay đổi nhỏ dễ hơn, còn thay đổi phức tạp vẫn bị mắc ở dependency hoặc migration. Chỉ nhìn median sẽ bỏ lỡ vấn đề đó.

## 17. Tránh gaming và các chỉ số gây hiểu lầm

Khi một chỉ số trở thành mục tiêu cứng, đội có thể tối ưu con số thay vì kết quả thực.

Các ví dụ cần tránh:

- Giảm số module bị sửa bằng cách gom mọi logic vào một module lớn.
- Giảm lead time bằng cách chia yêu cầu thành nhiều ticket nhỏ nhưng bỏ qua phần tích hợp cuối.
- Tăng điểm comprehension bằng câu hỏi kiểm tra thuật ngữ mà không kiểm tra khả năng áp dụng.
- Tăng coverage bằng test ít assertion hoặc test lặp lại implementation.
- Giảm số defect được ghi nhận bằng cách phân loại lại incident.
- Giảm số lần phối hợp bằng cách bỏ qua owner và tự sửa dữ liệu context khác.

Biện pháp:

- Kết hợp chỉ số định lượng với review định tính.
- Dùng nhiều chỉ số cân bằng, không thưởng theo một con số đơn lẻ.
- Giữ định nghĩa đo lường ổn định và minh bạch.
- Kiểm tra chất lượng kết quả sau phát hành.
- Xem xét các ngoại lệ và yêu cầu phức tạp riêng.
- Dùng dữ liệu để cải thiện hệ thống, không xếp hạng cá nhân.

## 18. Xác định mục tiêu cải thiện có thể kiểm chứng

Mục tiêu nên mô tả kết quả và khoảng thời gian đánh giá, không yêu cầu một kiến trúc cụ thể chỉ để đạt con số.

Ví dụ mục tiêu:

- Người mới có thể xác định đúng context sở hữu ba quy tắc cốt lõi trong vòng 30 phút với rubric đạt ít nhất mức 3.
- Giảm median thời gian tìm vị trí quy tắc từ 90 phút xuống dưới 45 phút trên nhóm nhiệm vụ tương đương.
- Giảm effort rework do hiểu sai policy trong hai quý liên tiếp.
- Tăng tỷ lệ thay đổi chỉ cần sửa các module thực sự sở hữu hành vi.
- Giảm số release đồng bộ không cần thiết giữa các context.
- Không làm tăng change failure rate trong khi giảm lead time.

Các ngưỡng số cần được đặt sau baseline. Nếu không có baseline, hãy dùng giai đoạn đầu để đo và xác định mục tiêu thực tế.

## 19. Kế hoạch đo lường theo giai đoạn chuyển đổi

| Giai đoạn | Câu hỏi | Bằng chứng cần thu thập |
|---|---|---|
| Khám phá | Đội có hiểu đúng domain và pain point không? | Glossary, context map, task comprehension baseline |
| Thiết kế | Ownership và invariant có rõ không? | Aggregate rules, decision records, contract boundaries |
| Thử nghiệm | Một thay đổi có được khoanh vùng tốt hơn không? | Impact radius, effort, lead time, rework |
| Mở rộng | Kết quả có lặp lại ở nhiều capability không? | Xu hướng theo nhóm thay đổi, team và context |
| Vận hành | Hệ thống có dễ duy trì sau release không? | Change failure, incident, recovery, onboarding |
| Tối ưu | Ranh giới nào cần điều chỉnh? | Outlier, dependency graph, wrong-owner rate, feedback |

Không nên chờ đến khi toàn bộ hệ thống chuyển đổi xong mới đo. Đo theo từng capability giúp phát hiện sớm một ranh giới không phù hợp và điều chỉnh trước khi nhân rộng.

## 20. Ví dụ dashboard đo lường

Một dashboard có thể gồm các nhóm sau:

```text
UNDERSTANDING
  Task comprehension score:       3.2 / 4
  Median time to locate rule:     42 min
  Wrong-owner rate:               12%

CHANGE FLOW
  Median change lead time:        7.5 days
  P90 change lead time:           19 days
  Median engineering effort:      3.0 person-days
  Median impact radius:           2 modules

QUALITY
  Change failure rate:            6%
  Rework due to domain mismatch:   8 person-hours / change
  Escaped domain defects:         2 / quarter

SUSTAINABILITY
  Critical rules with owner:      92%
  Contexts with current glossary:  85%
  Tasks blocked by knowledge gap:  3 / quarter
```

Các giá trị là dữ liệu giả định để minh họa bố cục. Dashboard thực tế cần ghi rõ kỳ đo, mẫu số, nguồn dữ liệu và định nghĩa từng chỉ số. Không nên hiển thị một tỷ lệ mà không cho biết có bao nhiêu thay đổi được tính.

## 21. Những sai lầm khi đánh giá hiệu quả DDD

| Sai lầm | Vì sao gây hiểu lầm | Cách làm tốt hơn |
|---|---|---|
| Đếm số bounded context | Số lượng không thể hiện chất lượng ownership | Đo khả năng xác định owner và hiểu contract |
| Đếm Aggregate/Domain Event | Khuyến khích tạo cấu trúc quá mức | Đo invariant và hành vi được bảo vệ |
| Dùng số dòng code làm chi phí | Không phản ánh điều tra, phối hợp và rủi ro | Đo effort theo hoạt động và elapsed time |
| Chỉ đo lead time | Không phân biệt chờ đợi với effort | Đo cả elapsed time và person-effort |
| Chỉ hỏi cảm nhận developer | Cảm nhận không luôn phản ánh độ chính xác | Dùng task thực tế và rubric |
| So sánh yêu cầu khác độ khó | Kết quả bị nhiễu | Phân loại và so sánh nhóm tương đương |
| Dùng coverage làm đại diện chất lượng | Test có thể không bảo vệ đúng invariant | Đo defect, contract và kết quả nghiệp vụ |
| Gắn mọi cải thiện cho DDD | Có thể do team/process/tool thay đổi | Ghi yếu tố gây nhiễu và dùng nhóm so sánh khi phù hợp |
| Dùng KPI để xếp hạng cá nhân | Làm sai lệch hành vi và giảm chia sẻ kiến thức | Dùng số liệu để cải thiện hệ thống và teamwork |

## 22. Checklist đo hiệu quả chuyển đổi

- [ ] Mục tiêu đo gắn với khả năng hiểu mô hình và chi phí thay đổi.
- [ ] Có baseline trước khi thay đổi.
- [ ] Yêu cầu được phân nhóm theo độ phức tạp và phạm vi.
- [ ] Nhiệm vụ đánh giá hiểu mô hình có đáp án/rubric rõ.
- [ ] Đo cả thời gian tìm quy tắc và độ chính xác ownership.
- [ ] Đo elapsed time và effort riêng biệt.
- [ ] Ghi impact radius và phân biệt tác động cần thiết với coupling không cần thiết.
- [ ] Theo dõi rework, defect, change failure và recovery.
- [ ] Có góc nhìn về onboarding và phụ thuộc vào tri thức cá nhân.
- [ ] Chỉ số DDD cấu trúc được dùng làm bằng chứng hỗ trợ, không làm mục tiêu tự thân.
- [ ] Dữ liệu có kỳ đo, mẫu số, nguồn và định nghĩa nhất quán.
- [ ] Phân tích median, percentile và outlier thay vì chỉ dùng average.
- [ ] Xem xét yếu tố gây nhiễu như thay đổi team, công nghệ và release process.
- [ ] Không dùng KPI để thưởng/phạt cá nhân hoặc khuyến khích gaming.
- [ ] Có chu kỳ review để điều chỉnh ranh giới và cách làm.

## 23. Kết nối với các khái niệm DDD khác

Khả năng hiểu mô hình phụ thuộc vào ubiquitous language, bounded context, Context Map và cách các invariant được thể hiện trong Aggregate/Value Object. Chi phí thay đổi phụ thuộc vào ownership, cohesion, coupling, public contract, Domain Event, ACL và cách các context phối hợp qua use case hoặc Saga.

Đo lường không thay thế việc khám phá domain cùng chuyên gia. Nó cung cấp bằng chứng để biết mô hình đang giúp đội phát triển hay đang tạo thêm ceremony. Khi người phát triển xác định đúng nơi sở hữu quy tắc, giải thích được luồng nghiệp vụ và thực hiện thay đổi với ít effort/rework hơn mà chất lượng vẫn ổn định, đó là dấu hiệu thực tế cho thấy thiết kế đang hỗ trợ khả năng tiến hóa.

Một chương trình DDD tốt không cần chứng minh thành công bằng số lượng pattern đã triển khai. Nó cần chứng minh bằng khả năng hiểu đúng nghiệp vụ, thay đổi đúng nơi, kiểm soát tác động và duy trì chất lượng qua nhiều lần phát hành. Hãy đo các kết quả đó theo thời gian, xem cả dữ liệu định lượng lẫn bằng chứng định tính, rồi điều chỉnh ranh giới dựa trên điều đội ngũ thực sự học được.
