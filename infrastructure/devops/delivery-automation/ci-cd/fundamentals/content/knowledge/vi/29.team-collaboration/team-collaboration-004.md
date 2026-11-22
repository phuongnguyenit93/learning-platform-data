# Rà soát thay đổi nhỏ để giảm thời gian chờ tích hợp

Trong CI/CD, code có thể được build và test tự động nhưng vẫn nằm nhiều giờ hoặc nhiều ngày trong một pull request chưa được review. Khi nhiều nhánh sống lâu cùng thay đổi một khu vực, nhóm phải xử lý merge conflict, tích hợp muộn và phát hiện lỗi tương tác ở thời điểm gần release. Thời gian chờ review vì thế trở thành một phần đáng kể của lead time.

Một cách cải thiện là chia công việc thành các thay đổi nhỏ, có mục tiêu rõ, review được độc lập và tích hợp thường xuyên. Thay đổi nhỏ giúp reviewer hiểu phạm vi nhanh, tác giả nhận feedback sớm và CI kiểm tra từng bước. Tuy nhiên, “nhỏ” không chỉ có nghĩa là ít dòng code. Một thay đổi nhỏ cần có ranh giới nghiệp vụ hợp lý, hành vi có thể giải thích, test phù hợp và rủi ro có thể đánh giá.

Rà soát thay đổi nhỏ là một thực hành phối hợp nhóm: tác giả chuẩn bị thay đổi dễ hiểu; reviewer phản hồi đúng trọng tâm; CI cung cấp feedback nhanh; nhóm giới hạn công việc đang làm và tích hợp thường xuyên. Mục tiêu là giảm thời gian chờ và chi phí phối hợp trong khi vẫn giữ chất lượng kỹ thuật, bảo mật và khả năng truy vết của release.

## 1. Vì sao thời gian chờ tích hợp tăng?

Một thay đổi thường đi qua các trạng thái: đang phát triển, chờ review, đang được review, chờ CI, cần sửa, được duyệt, chờ merge và đã tích hợp. Nếu một trạng thái chờ kéo dài, công việc phía sau bị dồn lại.

Các nguyên nhân phổ biến:

- Pull request quá lớn, reviewer phải đọc nhiều file và hiểu nhiều quyết định cùng lúc.
- PR trộn refactor, đổi behavior, format và cập nhật dependency không liên quan.
- Không có reviewer owner hoặc người được yêu cầu review đang quá tải.
- PR thiếu mô tả, test evidence hoặc cách kiểm tra nên reviewer phải hỏi lại.
- CI chạy lâu, queue runner dài hoặc phải chạy lại toàn bộ pipeline sau mỗi sửa đổi nhỏ.
- Nhiều PR cùng sửa một file hoặc API nên phụ thuộc và conflict tăng.
- Nhóm giữ branch lâu, chỉ merge gần cuối sprint hoặc trước release.
- Review comment không rõ blocking hay chỉ là gợi ý, dẫn đến vòng trao đổi kéo dài.
- Tác giả không theo dõi feedback hoặc reviewer không có cam kết thời gian phản hồi.

Không phải mọi thời gian chờ đều là lãng phí. Một thay đổi ảnh hưởng dữ liệu, quyền truy cập hoặc production cần review sâu và approval phù hợp. Điều cần giảm là thời gian chờ không tạo thêm bằng chứng hoặc giảm rủi ro.

## 2. Thế nào là một thay đổi nhỏ?

Một thay đổi nhỏ có thể được hiểu qua bốn đặc điểm:

1. **Phạm vi hẹp:** giải quyết một mục tiêu chính, không gom nhiều công việc độc lập.
2. **Dễ hiểu:** reviewer có thể nắm bối cảnh, ý định và tác động trong một lần đọc hợp lý.
3. **Có thể kiểm chứng:** test, static analysis hoặc bằng chứng thủ công cho biết hành vi đúng.
4. **Có thể tích hợp an toàn:** thay đổi không để hệ thống ở trạng thái trung gian nguy hiểm khi merge.

Số dòng diff là tín hiệu tham khảo, không phải thước đo duy nhất. Một thay đổi 30 dòng có thể rất khó review nếu sửa authorization hoặc transaction boundary. Một thay đổi 400 dòng sinh tự động có thể dễ kiểm tra nếu output được tạo từ schema đã review và không chứa logic thủ công phức tạp.

Khi đánh giá kích thước PR, hãy nhìn cả số file, số khái niệm thay đổi, số dependency bị ảnh hưởng, độ phức tạp của behavior và lượng context cần hiểu. Nếu reviewer phải chuyển qua nhiều module để xác định ý nghĩa của một thay đổi, hãy cân nhắc tách hoặc bổ sung sơ đồ/giải thích.

## 3. Chia theo lát cắt dọc thay vì chỉ chia theo tầng kỹ thuật

Một cách chia việc thường gặp là tạo một PR cho database, một PR cho backend và một PR cho frontend. Cách này có thể phù hợp khi thay đổi schema độc lập, nhưng đôi khi mỗi PR không tạo ra behavior có thể kiểm chứng và các phần phải chờ nhau.

Vertical slicing chia theo một phần nhỏ của hành trình nghiệp vụ, đi qua các tầng cần thiết để tạo ra một kết quả có thể kiểm tra. Ví dụ tính năng hiển thị lịch sử đơn hàng có thể được chia:

- Lát 1: API trả về lịch sử tối thiểu và test contract.
- Lát 2: UI hiển thị danh sách với dữ liệu hiện có.
- Lát 3: bổ sung phân trang và xử lý trạng thái rỗng.
- Lát 4: bổ sung bộ lọc theo thời gian.

Mỗi lát có thể merge và deploy sau khi đạt điều kiện, trong khi feature flag giữ tính năng chưa sẵn sàng ở trạng thái tắt. Cách chia này tạo feedback sớm từ CI và review, thay vì chờ toàn bộ feature hoàn tất.

Không nên ép mọi thay đổi thành vertical slice nếu công việc thực sự là nền tảng kỹ thuật hoặc migration. Khi đó, chia theo bước tương thích và có điểm kiểm tra rõ ràng.

## 4. Tách refactor khỏi thay đổi behavior

Khi một PR vừa đổi behavior vừa đổi cấu trúc lớn, reviewer khó phân biệt lỗi do logic mới hay do refactor. Tách hai mục tiêu giúp review tập trung hơn:

1. PR đầu tiên refactor hoặc tạo abstraction nhưng giữ behavior hiện tại; test phải chứng minh kết quả không đổi.
2. PR tiếp theo thay đổi behavior qua abstraction mới; diff thể hiện rõ logic nghiệp vụ.
3. PR cuối dọn code cũ hoặc abstraction tạm thời sau khi migration ổn định.

Ví dụ, khi chuyển từ legacy pricing engine sang engine mới, có thể đưa interface/router vào trước, rồi thêm implementation mới sau. Nếu cần chuyển dần, dùng feature flag và giữ fallback trong thời gian tương thích.

Tuy nhiên, không nên tách máy móc khi refactor và behavior phụ thuộc chặt chẽ hoặc tạo trạng thái trung gian không compile. Mỗi PR vẫn phải build được, test được và có ý nghĩa review độc lập.

## 5. Tránh PR khổng lồ và branch sống lâu

PR lớn làm tăng chi phí nhận thức. Reviewer phải nhớ nhiều quyết định, nhiều file và nhiều tương tác; một comment có thể ảnh hưởng đến nhiều phần khác. Nếu cần sửa một điểm, tác giả có thể phải rebase hoặc chạy lại CI cho toàn bộ diff.

Branch sống lâu còn tạo ra divergence: nhánh chính tiếp tục thay đổi trong khi branch feature giữ snapshot cũ. Khi merge, conflict có thể xuất hiện ở cả cú pháp lẫn semantics. Hai thay đổi riêng lẻ có thể pass test nhưng khi tích hợp lại phát sinh lỗi.

Các biện pháp:

- Merge vào mainline thường xuyên theo các lát nhỏ.
- Dùng feature flag để ẩn behavior chưa sẵn sàng.
- Chia migration lớn thành các bước tương thích.
- Tránh giữ một branch tích hợp cho toàn bộ sprint.
- Nếu PR phải lớn vì lý do chính đáng, chia thành các commit/section có thứ tự và cung cấp hướng dẫn review.
- Tạo PR draft sớm để xin feedback về thiết kế trước khi hoàn thiện toàn bộ code.

Không đặt giới hạn dòng cứng cho mọi PR. Có thể dùng ngưỡng cảnh báo để khuyến khích tác giả xem lại phạm vi, nhưng cần cho phép ngoại lệ có giải thích.

## 6. Một PR tốt cần cung cấp gì?

Reviewer không nên phải suy đoán vì sao thay đổi tồn tại. PR description nên có:

- **Problem:** vấn đề hoặc yêu cầu đang được giải quyết.
- **Approach:** cách tiếp cận và lý do chọn.
- **Scope:** phần nào được thay đổi và phần nào nằm ngoài phạm vi.
- **Behavior:** hành vi trước/sau hoặc ví dụ input/output.
- **Tests:** test đã chạy, kết quả và giới hạn chưa kiểm tra.
- **Risk:** tác động đến API, database, security, performance hoặc vận hành.
- **Rollout:** feature flag, migration, config hoặc cách bật nếu có.
- **Evidence:** screenshot, test report, trace, benchmark hoặc link liên quan khi hữu ích.

Mẫu mô tả:

~~~markdown
## Vấn đề
Người dùng không thấy trạng thái giao hàng trong trang chi tiết đơn hàng.

## Thay đổi
- Bổ sung field deliveryStatus trong response.
- Hiển thị trạng thái trong trang chi tiết.
- Giữ field mới ở dạng optional để client cũ tương thích.

## Kiểm thử
- Unit tests: passed
- API contract tests: passed
- UI component tests: passed

## Rủi ro và rollout
- Không thay đổi schema database.
- UI mới được che bằng feature flag delivery-status-ui.
- Có thể tắt flag nếu phát hiện lỗi hiển thị.

## Reviewer cần chú ý
- Semantics của trạng thái khi đơn chưa được bàn giao cho đơn vị vận chuyển.
~~~

Đây là cấu trúc gợi ý. Không cần tạo tài liệu dài cho một sửa lỗi nhỏ; hãy cung cấp đúng lượng context để reviewer đưa ra quyết định.

## 7. Giữ PR tập trung vào một mục tiêu

Một PR tập trung thường trả lời được một câu hỏi chính: thay đổi này giải quyết điều gì? Tránh gom các việc sau vào cùng PR nếu chúng có thể review và phát hành độc lập:

- Format lại toàn bộ repository.
- Rename package hoặc file hàng loạt.
- Nâng cấp dependency không liên quan.
- Refactor nhiều module.
- Thay đổi business rule.
- Sửa pipeline hoặc permission không liên quan đến feature.
- Cập nhật tài liệu của các chủ đề khác.

Nếu một thay đổi phụ là điều kiện bắt buộc cho thay đổi chính, hãy nêu dependency và thứ tự merge. Nếu không, tách ra để reviewer có thể approve phần độc lập trước.

Các thay đổi generated file cần ghi rõ source schema/tool và cách tái tạo. Không trộn generated output với chỉnh sửa thủ công mà không có quy trình xác minh.

## 8. Dùng Draft PR để nhận feedback sớm

Draft PR hữu ích khi tác giả muốn chia sẻ hướng thiết kế trước khi code hoàn chỉnh. Reviewer có thể phản hồi về API, boundary, naming, data model hoặc cách rollout trước khi tác giả đầu tư vào implementation chi tiết.

Một draft tốt nên cho biết:

- Vấn đề và mục tiêu.
- Thiết kế đang cân nhắc.
- Phần đã hoàn thành và phần còn thiếu.
- Câu hỏi cụ thể cần reviewer góp ý.
- Những test chưa chạy và lý do.

Draft không nên được coi là ready-to-merge. Khi chuyển sang trạng thái review chính thức, tác giả cần xác nhận diff đã cập nhật, test evidence mới và các comment trước đó đã được xử lý hoặc đánh dấu rõ.

Feedback sớm có giá trị nhất khi thay đổi còn dễ điều chỉnh. Đừng chờ đến khi PR đã có hàng trăm dòng mới hỏi reviewer liệu kiến trúc có phù hợp không.

## 9. Chọn reviewer theo ownership và loại rủi ro

Reviewer phù hợp là người hiểu phần code hoặc rủi ro đang thay đổi. Có thể cần nhiều góc nhìn:

| Loại thay đổi | Reviewer phù hợp |
|---|---|
| Business logic của service | Service owner hoặc maintainer |
| API/schema contract | API owner và consumer đại diện |
| Database migration | Database owner hoặc người hiểu vận hành dữ liệu |
| Authentication/authorization | Security owner hoặc reviewer có chuyên môn |
| CI workflow/runner/secret | Platform/DevOps owner |
| UI behavior/accessibility | Frontend maintainer hoặc UX/accessibility reviewer |
| Performance-critical path | Owner của workload và người có thể đánh giá benchmark |

CODEOWNERS hoặc cơ chế tương đương có thể tự động đề xuất reviewer theo đường dẫn. Nhưng ownership file cần được cập nhật khi team thay đổi; nếu không, PR sẽ liên tục được gửi đến người không còn phụ trách.

Không yêu cầu quá nhiều reviewer cho mọi PR. Một reviewer hiểu phần code có thể đủ cho thay đổi rủi ro thấp; thay đổi ảnh hưởng security, dữ liệu hoặc production có thể cần approval bổ sung theo policy.

## 10. Chia tải review và có người dự phòng

Nếu mọi PR đều được gửi đến một senior engineer, người đó trở thành bottleneck. Nhóm cần phân bổ review theo năng lực, ownership và tải hiện tại.

Thực hành hữu ích:

- Duy trì danh sách primary và backup reviewer cho mỗi khu vực.
- Luân phiên review trong nhóm để chia sẻ kiến thức.
- Giới hạn số PR đang chờ review trên mỗi reviewer.
- Dùng reviewer chuyên môn cho thay đổi rủi ro cao, không dùng họ làm gate cho mọi thay đổi nhỏ.
- Cho phép reviewer chuyển yêu cầu đến owner phù hợp kèm lý do và context.
- Theo dõi tải review để phát hiện một cá nhân trở thành nút thắt.

Reviewer dự phòng cần có đủ context và quyền truy cập. Không giao review chỉ để tăng số người; reviewer không hiểu phần code có thể tạo thêm vòng hỏi đáp mà không tăng chất lượng.

## 11. Cam kết thời gian phản hồi review

Review SLA giúp tác giả biết khi nào có phản hồi và giúp nhóm phát hiện hàng chờ bị tắc. SLA nên nói rõ thời gian làm việc, loại thay đổi và mức ưu tiên.

Ví dụ thỏa thuận nội bộ:

| Mức ưu tiên | First response mục tiêu | Cách xử lý |
|---|---|---|
| Production fix khẩn cấp | Theo incident/on-call policy | Gọi trực tiếp người có trách nhiệm và ghi audit |
| Thay đổi rủi ro cao | Trong ngày làm việc | Chọn reviewer chuyên môn và dành thời gian review |
| PR thông thường | Trong một ngày làm việc | Reviewer acknowledge hoặc chuyển owner |
| Draft xin ý kiến thiết kế | Theo lịch đã hẹn | Feedback vào câu hỏi thiết kế cụ thể |

Các mốc trên chỉ là ví dụ. Nhóm nên đặt SLA theo múi giờ, giờ làm việc và mức độ ảnh hưởng thực tế. First response không nhất thiết là approve; nó có thể là xác nhận đã nhận review, nêu thời gian dự kiến hoặc yêu cầu bổ sung thông tin.

Không dùng SLA để ép reviewer bỏ qua kiểm tra cần thiết. Nếu review cần thêm thời gian, reviewer nên cập nhật trạng thái và lý do để tác giả có thể điều chỉnh kế hoạch.

## 12. Phân biệt blocking comment và non-blocking comment

Comment cần thể hiện mức độ ảnh hưởng:

- **Blocking:** vấn đề cần sửa hoặc có quyết định rõ trước khi merge, ví dụ lỗi correctness, security, data loss, contract break hoặc test bắt buộc thất bại.
- **Non-blocking suggestion:** cải thiện có ích nhưng không bắt buộc cho PR hiện tại, ví dụ naming preference hoặc refactor nhỏ.
- **Question:** cần tác giả giải thích ý định hoặc behavior.
- **Nit:** chi tiết nhỏ về style/format không ảnh hưởng correctness.

Reviewer nên ghi rõ comment có chặn merge hay không. Tác giả không cần đoán liệu một gợi ý có phải yêu cầu bắt buộc. Nếu một concern có thể tạo rủi ro đáng kể, hãy giải thích tình huống và hậu quả thay vì chỉ viết “please change”.

Một thread được resolve không tự động có nghĩa vấn đề đã được giải quyết. Tác giả và reviewer cần xác nhận thay đổi hoặc lý do không áp dụng. Với comment blocking được giải quyết bằng quyết định khác, ghi lại rationale để lần sau có thể hiểu.

## 13. Viết review comment có thể hành động

Comment tốt nêu vị trí, vấn đề, tình huống và hướng xử lý hoặc câu hỏi. Ví dụ:

~~~text
Blocking: request có thể được gửi lại sau timeout trong khi lần đầu đã commit.
Nếu handler không kiểm tra idempotency key, một đơn hàng có thể bị tạo hai lần.
Đề nghị thêm test cho trường hợp retry cùng key trước khi merge.
~~~

Comment kém hữu ích:

~~~text
This is wrong. Fix it.
~~~

Tập trung vào code và tác động, không đánh giá năng lực hoặc ý định của tác giả. Nếu có nhiều cách giải quyết, nêu tiêu chí cần đạt và để tác giả chọn implementation phù hợp.

Reviewer cũng nên phân biệt lỗi chắc chắn với câu hỏi. Dùng “Tôi chưa hiểu trường hợp...” khi cần giải thích, thay vì kết luận rằng code sai khi chưa có đủ context.

## 14. Review theo rủi ro, không chỉ theo số dòng

Một review hiệu quả ưu tiên các rủi ro có thể gây hậu quả lớn:

1. Correctness và business invariant.
2. Security, authorization và secret handling.
3. Data integrity, transaction và migration compatibility.
4. API/event contract và backward compatibility.
5. Concurrency, retry và idempotency.
6. Performance, resource usage và failure behavior.
7. Observability, rollback và vận hành.
8. Readability, maintainability và style.

Thứ tự có thể thay đổi theo hệ thống. Với một thay đổi pipeline, quyền token và trust boundary có thể quan trọng hơn style. Với migration dữ liệu, lock duration, backfill và rollback cần được review trước naming.

Không biến review thành kiểm tra từng dấu phẩy nếu formatter/linter đã tự động hóa. Hãy để máy kiểm tra quy tắc cơ học và dành thời gian con người cho semantics, thiết kế và rủi ro.

## 15. Checklist review ngắn gọn

Reviewer có thể dùng checklist theo loại thay đổi:

- [ ] PR giải quyết đúng một mục tiêu chính và mô tả được lý do.
- [ ] Diff có phạm vi hợp lý; file generated/refactor phụ được giải thích.
- [ ] Behavior mới và behavior cũ được hiểu rõ.
- [ ] Test bao phủ happy path, edge case và failure path quan trọng.
- [ ] API/schema/event không phá consumer đang được hỗ trợ.
- [ ] Authorization và validation vẫn được kiểm tra ở server.
- [ ] Không có secret, token hoặc dữ liệu nhạy cảm trong diff/log.
- [ ] Retry, timeout và side effect có semantics rõ khi liên quan.
- [ ] Migration có thứ tự rollout và phương án rollback/recovery.
- [ ] Metric/log/trace đủ để quan sát thay đổi.
- [ ] Rollout/feature flag có owner và fallback nếu cần.
- [ ] CI evidence thuộc đúng commit/artifact đang review.

Không phải PR nào cũng cần mọi mục. Tác giả và reviewer nên chọn checklist phù hợp với loại thay đổi, nhưng không bỏ qua các gate bắt buộc theo policy.

## 16. Để CI cung cấp feedback nhanh

Review bị chậm nếu mỗi lần sửa một dòng, tác giả phải chờ pipeline 40 phút mới biết lỗi lint. Hãy sắp xếp kiểm tra từ nhanh đến chậm và thất bại sớm:

1. Format, lint và static checks.
2. Unit tests.
3. Build/compile.
4. Component hoặc contract tests.
5. Integration tests.
6. Security/dependency scans.
7. E2E, performance hoặc environment tests.

Thứ tự thực tế phụ thuộc dependency graph. Một số scan có thể chạy song song với test; build có thể cần trước test. Điều quan trọng là kiểm tra nhanh cung cấp tín hiệu sớm và gate bắt buộc không bị bỏ qua.

Tối ưu thời gian CI bằng dependency cache có khóa chính xác, test selection đáng tin, runner capacity phù hợp và artifact reuse. Không giảm thời gian bằng cách bỏ test quan trọng hoặc dùng cache không invalidation đúng.

## 17. Phân biệt feedback nhanh với feedback không đáng tin

Feedback nhanh chỉ hữu ích nếu nó đúng với commit và artifact hiện tại. Các nguồn false confidence gồm:

- Test dùng cache cũ hoặc dependency không khớp lockfile.
- Job bị skip nhưng pipeline vẫn báo xanh do điều kiện sai.
- Test report thuộc attempt/commit khác.
- CI chạy trên merge base cũ trong khi target branch đã thay đổi.
- Retry flaky test thành công nhưng lần đầu thất bại không được lưu.
- Scan không chạy vì timeout nhưng bị coi như pass.

Mỗi check cần có trạng thái rõ: passed, failed, skipped, cancelled, timed out hoặc inconclusive. Gate bắt buộc bị skip/timeout phải được xử lý theo policy, không mặc nhiên pass.

## 18. Giảm WIP để tăng tốc độ hoàn thành

WIP (*Work in Progress*) là số lượng công việc đang được làm nhưng chưa hoàn tất. Khi một người mở nhiều PR cùng lúc, họ phải chuyển context giữa các thay đổi; reviewer cũng nhận nhiều yêu cầu hơn khả năng xử lý. Kết quả là hàng đợi review dài dù nhóm có vẻ rất bận.

Giới hạn WIP giúp nhóm ưu tiên hoàn thành và tích hợp công việc đang mở trước khi bắt đầu thêm việc mới. Ví dụ, một developer có thể ưu tiên đưa PR đang chờ review qua merge thay vì mở thêm hai nhánh feature khác.

Little’s Law mô tả quan hệ giữa lượng công việc đang nằm trong hệ thống, throughput và thời gian hoàn thành:

~~~text
WIP = Throughput x Cycle Time
~~~

Nếu throughput không đổi, WIP cao thường đi kèm cycle time dài hơn. Công thức là mô hình cho hệ thống ổn định; không nên dùng như phép dự đoán chính xác cho từng PR. Nó giúp nhóm hiểu vì sao tăng số việc bắt đầu không nhất thiết làm tăng số việc hoàn thành.

Khi review queue tăng, nhóm nên giúp xử lý hàng đợi, không tiếp tục mở thêm việc mới theo phản xạ.

## 19. Giảm batch size và tích hợp thường xuyên

Batch size là lượng thay đổi được gom vào một lần review/merge/release. Batch lớn làm tăng số tương tác cần kiểm tra và thời gian phản hồi. Batch nhỏ tạo feedback nhanh và giúp xác định nguyên nhân khi CI fail.

Để giảm batch size:

- Chia feature thành behavior increment có thể test.
- Tách refactor cơ học khỏi thay đổi logic.
- Dùng feature flag để merge code chưa công bố.
- Giữ branch ngắn ngày và đồng bộ mainline thường xuyên.
- Merge PR độc lập ngay khi đạt gate thay vì đợi cả feature hoàn thành.
- Tự động hóa format, lint, test và metadata.

Batch nhỏ không có nghĩa chia một thay đổi thành hàng chục PR phụ thuộc chặt chẽ, mỗi PR không build được. Một chuỗi PR chỉ hiệu quả khi từng bước có thể review, kiểm tra và merge theo thứ tự đã xác định.

## 20. Trunk-based development và branch ngắn ngày

Trunk-based development khuyến khích developer tích hợp thay đổi nhỏ vào nhánh chính thường xuyên. Nhánh làm việc thường ngắn ngày; feature chưa sẵn sàng được bảo vệ bằng flag hoặc abstraction.

Lợi ích:

- Giảm divergence và merge conflict.
- Phát hiện lỗi tích hợp sớm.
- Giữ mainline ở trạng thái có thể build/test.
- Dễ xác định commit gây lỗi hơn vì mỗi batch nhỏ.
- Hỗ trợ release thường xuyên và progressive delivery.

Điều kiện cần:

- CI nhanh và đáng tin.
- Branch protection và required checks rõ.
- Feature flag có lifecycle/cleanup.
- Migration/API thay đổi theo hướng tương thích.
- Nhóm có kỷ luật review và tích hợp liên tục.

Trunk-based không có nghĩa merge code chưa kiểm tra hoặc bỏ qua review. Nó yêu cầu thay đổi nhỏ, test tự động và feedback nhanh để mainline luôn có thể sử dụng.

## 21. Merge queue và kiểm tra trên trạng thái tích hợp mới nhất

Khi nhiều PR cùng chờ merge vào main, một PR có thể pass trên trạng thái branch cũ nhưng fail khi kết hợp với PR vừa merge trước đó. Merge queue giúp kiểm tra thay đổi trên một trạng thái tích hợp dự kiến trước khi cập nhật target branch.

Luồng khái niệm:

~~~mermaid
flowchart TD
    A[PR passes required checks] --> B[Approved and enters merge queue]
    B --> C[Create candidate merge group]
    C --> D[Run required checks on candidate]
    D --> E{Candidate passes?}
    E -->|Yes| F[Merge into target branch]
    E -->|No| G[Remove or rebase affected PRs]
    G --> H[Author fixes or updates PR]
    H --> A
~~~

Merge queue hữu ích khi repository có nhiều contributor và PR được merge liên tục. Nó không thay thế review; nó kiểm tra trạng thái tích hợp sau review. Cần cấu hình required checks nhất quán giữa PR và merge group, nếu không pipeline có thể chạy khác nhau ở hai ngữ cảnh.

Nếu repository chưa có merge queue, nhóm có thể dùng merge train hoặc quy trình serialize merge phù hợp. Không nên để nhiều người tự merge cùng lúc khi branch protection không bảo đảm cập nhật an toàn.

## 22. Stacked PR cho thay đổi phụ thuộc

Stacked PR là chuỗi thay đổi trong đó PR sau xây trên PR trước. Kỹ thuật này giúp review từng lớp nhỏ khi một feature có dependency rõ.

Ví dụ:

~~~text
main
  └── PR A: introduce pricing interface
        └── PR B: add new pricing implementation
              └── PR C: route eligible tenants to new implementation
                    └── PR D: remove legacy implementation
~~~

Ưu điểm là mỗi PR có phạm vi hẹp. Nhược điểm là PR sau phụ thuộc vào PR trước; nếu PR A đổi nhiều, các PR phía trên phải rebase và CI có thể chạy lại. Reviewer cần biết base branch của từng PR và thứ tự merge.

Chỉ dùng stacked PR khi dependency thực sự có ý nghĩa. Nếu mọi PR đều phụ thuộc vào một nhánh feature dài, nhóm có thể tái tạo vấn đề branch sống lâu dưới hình thức khác.

## 23. Feature flag giúp merge sớm nhưng cần tương thích

Feature flag cho phép merge code mới trong khi giữ behavior mới ở trạng thái off. Đây là công cụ hữu ích cho trunk-based development và vertical slicing.

Khi dùng flag:

- Default off cho feature chưa sẵn sàng.
- Code path off phải tiếp tục hoạt động và có test.
- Code path on cần test độc lập.
- Không dùng flag thay authorization.
- Schema/API/event cần tương thích với phiên bản cũ.
- Flag có owner, rollout plan và expiry/review date.
- Khi feature ổn định, xóa nhánh cũ và flag tạm thời.

Không merge một PR chỉ vì code được che bằng flag nếu nó vẫn làm ứng dụng không compile, khởi động lỗi hoặc tạo side effect khi flag off. Flag che behavior; nó không che lỗi build hoặc mọi rủi ro khởi tạo.

## 24. Review thay đổi API, schema và migration theo trình tự

Một PR nhỏ vẫn có thể gây ảnh hưởng lớn nếu thay đổi contract. Khi nhiều phiên bản cùng chạy, hãy review thứ tự:

1. Expand: thêm field/table/endpoint theo cách không phá code hiện tại.
2. Deploy reader tương thích với dữ liệu cũ và mới.
3. Chuyển writer hoặc producer sang format mới.
4. Backfill và kiểm tra dữ liệu.
5. Theo dõi consumer, queue và client cũ.
6. Contract: loại bỏ cấu trúc cũ trong một release sau khi hết dependency/rollback window.

Review cần xem xét code cũ có chạy được trên schema mới không, code mới có đọc được dữ liệu cũ không, event backlog có chứa payload cũ không và rollback có còn an toàn không.

Nếu migration có lock hoặc backfill lớn, tách phần thay đổi schema, job migration và code sử dụng schema mới thành các bước có thể quan sát. Không gộp tất cả vào một PR khổng lồ rồi hy vọng deployment diễn ra nguyên tử.

## 25. Review security và CI workflow

Thay đổi pipeline có thể cấp quyền cho code chạy trong CI. PR sửa workflow, action, runner label, secret mapping hoặc deployment permission cần được review như một thay đổi hạ tầng có đặc quyền.

Reviewer nên kiểm tra:

- Permission của token có tối thiểu không?
- Pull request từ fork có thể truy cập secret hoặc runner đặc quyền không?
- Action/plugin có được pin và đến từ nguồn tin cậy không?
- OIDC trust policy có giới hạn repository/workflow/environment không?
- Artifact được tạo và tiêu thụ có liên kết bằng digest không?
- Log có thể làm lộ secret không?
- Approval có gắn với đúng artifact/plan không?
- Workflow có thể chạy script không tin cậy trong context có quyền cao không?

Không dùng số dòng nhỏ làm lý do bỏ qua security review. Một thay đổi một dòng có thể mở quyền write toàn repository hoặc cho phép deploy production.

## 26. Xử lý CI flaky mà không che lỗi

Flaky test làm giảm niềm tin vào pipeline và tăng thời gian chờ. Retry có thể giúp phân biệt lỗi tạm thời, nhưng không nên biến test thất bại thành pass mà không giữ lại bằng chứng.

Nên:

- Ghi rõ attempt và kết quả từng lần.
- Tách flaky classification khỏi pass/fail cuối.
- Theo dõi test có tỷ lệ retry cao.
- Lưu seed, environment và report để tái hiện.
- Gán owner và deadline sửa flaky test.
- Dùng quarantine có thời hạn nếu test không thể chặn release ngay, kèm policy và telemetry.

Không cho phép mọi test tự retry vô hạn. Nếu retry thành công, vẫn cần hiển thị lần đầu thất bại và ghi nhận độ tin cậy của test suite.

## 27. Đồng bộ review với trạng thái CI

Reviewer cần biết CI đang chạy trên commit nào. Nếu tác giả push commit mới sau khi review bắt đầu, kết quả cũ có thể không còn áp dụng.

Các thực hành:

- Hiển thị commit SHA được review và commit SHA của required checks.
- Reset approval khi thay đổi code quan trọng nếu policy yêu cầu.
- Re-run checks sau thay đổi ảnh hưởng behavior hoặc workflow.
- Dùng merge queue để kiểm tra candidate tích hợp mới nhất.
- Không merge khi required check đang pending, stale hoặc chạy trên revision khác.
- Ghi rõ test nào chạy trên từng attempt.

Không yêu cầu reviewer đọc lại toàn bộ PR sau mọi sửa đổi nhỏ. Tác giả có thể tóm tắt commit mới, comment nào đã được xử lý và phần diff thay đổi. Reviewer vẫn cần xác minh các vùng có tác động.

## 28. Handoff giữa tác giả và reviewer

Một vòng review hiệu quả cần trạng thái handoff rõ:

1. Tác giả mở PR và gán reviewer theo ownership.
2. Reviewer acknowledge hoặc thông báo thời gian dự kiến.
3. Reviewer để comment có phân loại blocking/non-blocking.
4. Tác giả trả lời từng thread, sửa code hoặc giải thích quyết định.
5. Tác giả đánh dấu PR ready và chỉ rõ commit mới.
6. Reviewer xác minh các blocking comment và required checks.
7. PR được approve và merge qua cơ chế bảo vệ.
8. Tác giả hoặc release owner xác minh thay đổi đã tích hợp.

Nếu reviewer không thể tiếp tục, hãy chuyển cho reviewer dự phòng kèm context và comment còn mở. Không để PR ở trạng thái “review requested” mà không ai nhận trách nhiệm.

## 29. Ví dụ thực tế: chia một feature checkout lớn

Giả sử nhóm muốn thêm phương thức thanh toán mới. Một PR lớn có thể đồng thời thêm bảng, API, UI, tích hợp nhà cung cấp, telemetry và rollout rule. Thay đổi như vậy khó review và khó xác định phần gây lỗi.

Có thể chia theo trình tự:

| PR | Phạm vi | Bằng chứng review |
|---|---|---|
| A | Thêm interface PaymentProvider và adapter cũ | Unit/contract tests chứng minh behavior cũ không đổi |
| B | Thêm adapter nhà cung cấp mới ở chế độ chưa bật | Tests với sandbox và error mapping |
| C | Thêm API capability tùy chọn | API contract tests, client cũ vẫn tương thích |
| D | Thêm UI sau feature flag mặc định off | Component/E2E tests cho flag on/off |
| E | Thêm telemetry và rollout targeting | Dashboard, privacy review và test assignment |
| F | Mở nội bộ rồi canary theo cohort | Operational guardrails và release evidence |
| G | Dọn adapter cũ nếu đã chuyển hoàn toàn | Test regression và xác minh không còn consumer |

Mỗi PR có thể merge khi độc lập an toàn. Nếu PR sau phụ thuộc PR trước, ghi rõ thứ tự hoặc dùng stacked PR. Artifact được build theo pipeline và promote theo digest; feature flag điều khiển thời điểm người dùng thấy phương thức mới.

## 30. Metrics để cải thiện review và integration flow

Đo lường giúp nhóm biết bottleneck nằm ở đâu. Một số metric hữu ích:

| Metric | Cách hiểu |
|---|---|
| PR size | Số dòng/file/khái niệm thay đổi; dùng để phát hiện batch lớn |
| Time to first review | Từ lúc PR ready đến phản hồi đầu tiên |
| Review cycle time | Thời gian từ review đầu đến approval/merge |
| PR age | Tuổi của PR chưa merge |
| Review queue depth | Số PR đang chờ reviewer |
| Time in changes requested | Thời gian tác giả xử lý feedback |
| CI feedback time | Thời gian từ push đến required checks có kết quả |
| Merge wait time | Thời gian từ approved đến tích hợp |
| Rework rate | Số vòng sửa hoặc tỷ lệ PR phải mở lại |
| Change failure rate | Tỷ lệ thay đổi gây incident/rollback theo định nghĩa tổ chức |
| Deployment frequency | Tần suất triển khai thay đổi có giá trị |

Không tối ưu một metric riêng lẻ. Nếu chỉ giảm PR size, nhóm có thể tạo quá nhiều PR phụ thuộc và tăng số lần handoff. Nếu chỉ giảm review time, chất lượng review có thể giảm. Nếu chỉ tăng deployment frequency, có thể tạo nhiều release nhỏ nhưng không có giá trị.

Đo theo nhóm và theo loại thay đổi, không dùng metric để xếp hạng cá nhân. Kết hợp thời gian chờ với chất lượng sau merge để tránh khuyến khích approve vội.

## 31. Thỏa thuận làm việc của nhóm

Một working agreement ngắn có thể thống nhất:

- PR tập trung vào một mục tiêu và có mô tả đủ context.
- Tác giả tự kiểm tra diff, test và secret trước khi yêu cầu review.
- Reviewer được chọn theo ownership/risk và có backup.
- Reviewer acknowledge trong SLA đã thống nhất.
- Comment nêu rõ blocking hay suggestion.
- Tác giả phản hồi hoặc chuyển trạng thái khi cần thêm thời gian.
- Required checks phải thuộc đúng commit đang review.
- Merge qua branch protection/merge queue.
- Feature flag và migration có owner cùng cleanup plan.
- PR quá hạn có cơ chế escalation hoặc reassign.
- Nhóm ưu tiên hoàn thành WIP trước khi bắt đầu thêm việc.

Working agreement nên được điều chỉnh theo quy mô và giờ làm việc của nhóm. Một nhóm phân tán nhiều múi giờ cần asynchronous review và handoff rõ hơn một nhóm ngồi cùng văn phòng.

## 32. Anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách cải thiện |
|---|---|---|
| PR gom nhiều mục tiêu | Khó hiểu, review lâu và khó rollback riêng | Tách theo mục tiêu/lát cắt có thể kiểm chứng |
| Branch sống nhiều tuần | Divergence và conflict tăng | Merge nhỏ, thường xuyên vào mainline |
| Chờ feature hoàn chỉnh mới mở PR | Feedback đến muộn | Draft PR và vertical slicing |
| Giao mọi PR cho một senior | Reviewer thành bottleneck | Primary/backup ownership và chia tải |
| Comment không phân loại | Tác giả không biết điều gì chặn merge | Blocking, suggestion, question, nit |
| Review style thủ công | Tốn thời gian con người | Formatter/linter tự động |
| Approve trên commit cũ | Evidence không khớp code sẽ merge | Kiểm tra SHA và reset approval theo policy |
| Merge nhiều PR không kiểm tra tích hợp | Mainline có thể fail | Merge queue hoặc kiểm tra candidate |
| Dùng flag để bỏ qua compatibility | Tắt flag vẫn không phục hồi schema/data | Expand-contract và mixed-version tests |
| Retry flaky test đến khi xanh | Che giấu độ tin cậy thấp | Lưu attempt, quarantine có hạn và sửa root cause |
| Tối ưu số dòng PR bằng mọi giá | Tạo quá nhiều PR phụ thuộc | Tối ưu cognitive scope và cycle time |
| Đo thời gian review để phạt cá nhân | Reviewer có thể approve vội | Dùng metric để cải thiện flow ở cấp nhóm |

## 33. Checklist cho tác giả trước khi yêu cầu review

- [ ] PR có một mục tiêu chính và title mô tả đúng thay đổi.
- [ ] Mô tả vấn đề, cách tiếp cận, scope và risk.
- [ ] Diff không chứa format/refactor/dependency update không liên quan.
- [ ] Đã tự đọc lại diff và loại bỏ debug code.
- [ ] Test phù hợp đã chạy và evidence thuộc commit hiện tại.
- [ ] Không có secret, token hoặc dữ liệu cá nhân trong code/log.
- [ ] API/schema/event thay đổi có kế hoạch tương thích.
- [ ] Feature flag có default, fallback, owner và expiry nếu dùng.
- [ ] Migration có thứ tự rollout và recovery plan.
- [ ] Reviewer được chọn theo ownership và mức rủi ro.
- [ ] Câu hỏi cần reviewer chú ý được nêu rõ.

## 34. Checklist cho reviewer trước khi approve

- [ ] Hiểu mục tiêu và phạm vi PR.
- [ ] Kiểm tra correctness và business invariant.
- [ ] Kiểm tra security, authorization và secret handling.
- [ ] Kiểm tra data/API/event compatibility.
- [ ] Kiểm tra retry, concurrency và failure behavior nếu liên quan.
- [ ] Kiểm tra test evidence thuộc đúng commit.
- [ ] Kiểm tra migration, rollout, observability và rollback.
- [ ] Comment được phân loại rõ và có thể hành động.
- [ ] Blocking comment đã được giải quyết hoặc có quyết định được ghi lại.
- [ ] Required checks và branch protection đạt.
- [ ] Approval vẫn còn hiệu lực với revision chuẩn bị merge.

## 35. Kết luận

Rà soát thay đổi nhỏ giúp giảm thời gian chờ tích hợp khi mỗi PR có mục tiêu rõ, phạm vi dễ hiểu, test evidence đầy đủ và reviewer phù hợp. Vertical slicing, draft PR, branch ngắn ngày, feature flag và merge queue giúp nhóm tích hợp từng phần mà vẫn kiểm soát behavior và trạng thái mainline.

Tốc độ review không đến từ việc đọc lướt hoặc bỏ qua kiểm tra. Nó đến từ việc giảm batch size, phân bổ ownership, thống nhất SLA, tự động hóa kiểm tra cơ học và cung cấp feedback nhanh trên đúng commit. Khi nhóm giới hạn WIP, handoff rõ ràng và đo cả thời gian chờ lẫn chất lượng sau merge, thay đổi có thể đi từ ý tưởng đến tích hợp với ít vòng chờ hơn và rủi ro được kiểm soát.
