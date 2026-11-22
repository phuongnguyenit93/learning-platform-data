# Phân biệt thời gian thực hiện với thời gian chờ

Một pipeline CI/CD hoàn thành trong 40 phút chưa cho biết đội ngũ đã thực sự làm việc trong 40 phút. Có thể build và kiểm thử chỉ mất 12 phút, còn lại là thời gian runner nằm trong hàng đợi, môi trường chưa sẵn sàng hoặc bản phát hành đang chờ người phê duyệt. Cũng có trường hợp pipeline báo trạng thái đang chạy trong 20 phút, nhưng phần lớn khoảng thời gian đó là chờ dịch vụ bên ngoài phản hồi.

Muốn cải thiện tốc độ giao phần mềm, cần tách **thời gian thực hiện** khỏi **thời gian chờ**. Hai số đo này trả lời hai câu hỏi khác nhau:

- Thời gian thực hiện cho biết công việc cần bao lâu để hoàn thành khi tài nguyên hoặc người phụ trách đã bắt đầu xử lý.
- Thời gian chờ cho biết công việc bị giữ lại bao lâu trước khi bước tiếp theo có thể bắt đầu hoặc trước khi có quyết định cần thiết.

Nếu chỉ nhìn tổng thời lượng pipeline, ta khó biết nên tối ưu build, tăng năng lực runner, cải thiện quy trình phê duyệt hay xử lý một phụ thuộc bên ngoài.

## 1. Các khái niệm cần phân biệt

### Thời gian trôi qua

**Thời gian trôi qua** (elapsed time) là khoảng thời gian thực tế giữa một mốc bắt đầu và một mốc kết thúc đã chọn:

\[
T_{\text{elapsed}} = t_{\text{end}} - t_{\text{start}}
\]

Trong luồng giao phần mềm, mốc bắt đầu có thể là lúc commit được đẩy lên, lúc pull request được mở, lúc thay đổi được merge hoặc lúc pipeline bắt đầu. Mốc kết thúc có thể là lúc artifact được tạo, lúc triển khai hoàn tất hoặc lúc xác minh sau triển khai thành công.

Không có một cặp mốc duy nhất phù hợp cho mọi câu hỏi. Ví dụ, thời gian từ lúc mở pull request đến lúc merge phản ánh một phần quy trình review; thời gian từ lúc commit đến khi production được xác minh phản ánh luồng giao hàng rộng hơn. Khi so sánh các nhóm hoặc các lần chạy, phải dùng cùng một định nghĩa về điểm bắt đầu và điểm kết thúc.

### Thời gian thực hiện

**Thời gian thực hiện** (execution time hoặc process time) là khoảng thời gian một công việc đang được xử lý thực sự. Tác nhân xử lý có thể là máy hoặc con người:

- Runner đang biên dịch mã nguồn.
- Tiến trình kiểm thử đang chạy các test.
- Công cụ triển khai đang cập nhật dịch vụ.
- Kỹ sư đang đọc thay đổi, kiểm tra bằng chứng và đưa ra quyết định phê duyệt.

Đối với pipeline, thời gian một job ở trạng thái running chỉ cho biết job đã được khởi chạy và chưa kết thúc. Nó không đảm bảo toàn bộ thời gian đó là thời gian thực thi hữu ích. Một tiến trình có thể đang ngủ, chờ khóa, chờ API, chờ rate limit hoặc chờ một dịch vụ khác. Nếu telemetry chưa phân biệt được các khoảng này, nên ghi nhận là **thời lượng chạy của job**, chưa vội gọi toàn bộ là thời gian thực hiện.

### Thời gian chờ

**Thời gian chờ** (waiting time) là khoảng thời gian công việc đã sẵn sàng hoặc đang cần một điều kiện tiếp theo, nhưng chưa được xử lý vì phải đợi tài nguyên, phụ thuộc, lịch hoặc quyết định.

Các trường hợp thường gặp trong CI/CD:

| Tình huống | Phân loại thường dùng | Dấu hiệu cần ghi nhận |
|---|---|---|
| Job đã được tạo nhưng chưa có runner | Chờ tài nguyên | Thời điểm job sẵn sàng và thời điểm runner nhận job |
| Test đã đủ điều kiện chạy nhưng phải đợi worker | Chờ hàng đợi | Thời điểm dependency hoàn tất và thời điểm test bắt đầu |
| Pull request chờ reviewer | Chờ người xử lý | Thời điểm yêu cầu review và thời điểm reviewer bắt đầu |
| Bản phát hành chờ phê duyệt production | Chờ quyết định | Thời điểm yêu cầu, bắt đầu review và thời điểm quyết định |
| Môi trường triển khai đang được cấp phát | Chờ môi trường | Thời điểm yêu cầu và thời điểm môi trường sẵn sàng |
| Job chờ khóa môi trường dùng chung | Chờ điều phối | Thời điểm yêu cầu khóa và thời điểm lấy được khóa |
| Tiến trình chờ API hoặc giới hạn tốc độ | Chờ phụ thuộc bên ngoài | Thời gian gửi yêu cầu, nhận phản hồi và các lần retry |

Một số khoảng thời gian có thể chứa cả chờ và thực hiện. Ví dụ, 30 phút từ lúc yêu cầu phê duyệt đến lúc có quyết định có thể gồm 25 phút chờ reviewer và 5 phút reviewer kiểm tra. Nếu chỉ lưu thời điểm yêu cầu và thời điểm quyết định, ta chỉ biết **độ trễ phê duyệt** là 30 phút; chưa đủ bằng chứng để kết luận cả 30 phút đều là thời gian chờ.

### Thời gian chờ khác với thời gian thực hiện của con người

Không nên xem mọi khoảng thời gian không có CPU hoạt động là thời gian chờ của toàn bộ quy trình. Review mã nguồn, phân tích kết quả kiểm thử và phê duyệt phát hành là công việc có giá trị, dù không tiêu thụ nhiều tài nguyên máy.

Khi đo quy trình có người tham gia, hãy tách ít nhất hai mốc:

1. Thời điểm công việc được giao hoặc yêu cầu được gửi.
2. Thời điểm người phụ trách thực sự bắt đầu xử lý.
3. Thời điểm người phụ trách hoàn tất và đưa ra quyết định.

Khoảng từ mốc 1 đến mốc 2 là thời gian chờ người xử lý. Khoảng từ mốc 2 đến mốc 3 là thời gian thực hiện của người xử lý. Nếu hệ thống không thu thập được mốc 2, hãy báo cáo độ trễ đầu-cuối của bước đó và ghi rõ giới hạn dữ liệu.

## 2. Ví dụ: đọc thời gian của một luồng CI/CD

Giả sử một commit được đưa vào pipeline lúc 09:00. Bản triển khai chỉ được xem là hoàn tất sau khi bước xác minh production kết thúc lúc 10:18. Pipeline có các khoảng thời gian sau:

| Khoảng thời gian | Hoạt động | Loại thời gian | Thời lượng |
|---|---|---:|---:|
| 09:00–09:10 | Job chờ runner | Chờ | 10 phút |
| 09:10–09:18 | Build artifact | Thực hiện | 8 phút |
| 09:18–09:23 | Job kiểm thử chờ worker | Chờ | 5 phút |
| 09:23–09:38 | Chạy kiểm thử tự động | Thực hiện | 15 phút |
| 09:38–10:03 | Chờ reviewer bắt đầu xử lý yêu cầu phê duyệt | Chờ | 25 phút |
| 10:03–10:08 | Reviewer kiểm tra bằng chứng và phê duyệt | Thực hiện | 5 phút |
| 10:08–10:13 | Triển khai lên production | Thực hiện | 5 phút |
| 10:13–10:18 | Xác minh sau triển khai | Thực hiện | 5 phút |
| **Tổng** | **Commit đến khi xác minh thành công** | **Thời gian trôi qua** | **78 phút** |

Trong ví dụ này:

\[
T_{\text{execution}} = 8 + 15 + 5 + 5 + 5 = 38 \text{ phút}
\]

\[
T_{\text{waiting}} = 10 + 5 + 25 = 40 \text{ phút}
\]

\[
T_{\text{elapsed}} = 38 + 40 = 78 \text{ phút}
\]

Thời gian thực hiện chiếm khoảng 48,7% tổng thời gian; thời gian chờ chiếm khoảng 51,3%. Phần chờ lớn nhất là 25 phút trước khi reviewer bắt đầu xử lý. Nếu chỉ tối ưu build nhanh hơn 2 phút, tổng thời gian giao hàng giảm khoảng 2 phút. Nếu giảm được thời gian chờ review mà vẫn giữ nguyên chất lượng kiểm soát, tác động có thể lớn hơn.

Ví dụ này giả định các khoảng thời gian nối tiếp nhau, không chồng lấn và đã có mốc reviewer bắt đầu xử lý. Trong dữ liệu thực tế, cần xác minh các giả định này trước khi cộng thời lượng.

### Cách diễn giải tỷ lệ

Có thể dùng tỷ lệ hiệu quả luồng (flow efficiency) để quan sát phần thời gian trôi qua được dùng cho việc thực hiện:

\[
\text{Flow efficiency} =
\frac{T_{\text{execution}}}{T_{\text{elapsed}}} \times 100\%
\]

Với ví dụ trên, tỷ lệ này xấp xỉ 48,7%. Đây là chỉ báo để tìm điểm nghẽn, không phải mục tiêu cần tối đa hóa bằng mọi giá. Một cổng kiểm thử bảo mật hoặc phê duyệt rủi ro có thể cần thời gian để bảo vệ hệ thống. Mục tiêu là loại bỏ thời gian chờ không cần thiết, làm rõ thời gian xử lý có chủ đích và giữ được mức bảo đảm cần thiết.

## 3. Đo lường từ sự kiện thay vì ước lượng

Muốn tách hai loại thời gian, mỗi bước cần có các mốc sự kiện đủ rõ. Với một job tự động, tối thiểu nên lưu:

- Thời điểm bước đã sẵn sàng để chạy.
- Thời điểm runner hoặc tiến trình thực sự bắt đầu.
- Thời điểm bước kết thúc.
- Kết quả, mã lần chạy và nguyên nhân thất bại nếu có.

Ví dụ một bản ghi cho bước build:

~~~json
{
  "run_id": "pipeline-2026-11-18-001",
  "commit_sha": "a1b2c3d4",
  "stage": "build",
  "ready_at": "2026-11-18T09:00:00+07:00",
  "started_at": "2026-11-18T09:10:00+07:00",
  "finished_at": "2026-11-18T09:18:00+07:00",
  "outcome": "success"
}
~~~

Từ bản ghi này:

- Thời gian chờ trước khi chạy = started_at trừ ready_at = 10 phút.
- Thời lượng bước chạy = finished_at trừ started_at = 8 phút.

Với cổng phê duyệt, nên lưu thêm mốc người xử lý bắt đầu review:

~~~json
{
  "stage": "production-approval",
  "requested_at": "2026-11-18T09:38:00+07:00",
  "review_started_at": "2026-11-18T10:03:00+07:00",
  "decided_at": "2026-11-18T10:08:00+07:00",
  "decision": "approved"
}
~~~

Nhờ vậy có thể tách 25 phút chờ reviewer và 5 phút xử lý review. Nếu chỉ có requested_at và decided_at, hãy ghi nhận 30 phút là độ trễ phê duyệt. Không nên tự suy ra thời gian thực hiện của reviewer từ khoảng thời gian đó.

### Quy trình đo thực tế

**Bước 1: Chọn ranh giới của luồng.** Xác định rõ đang đo từ commit, pull request, merge hay lúc pipeline bắt đầu; kết thúc ở artifact, triển khai hay xác minh production. Chọn ranh giới theo câu hỏi cần trả lời và giữ nhất quán qua các lần đo.

**Bước 2: Gắn định danh xuyên suốt.** Dùng run ID, commit SHA, artifact ID và môi trường để liên kết sự kiện từ hệ thống quản lý mã nguồn, CI, kho artifact, hệ thống triển khai và công cụ xác minh. Nếu thiếu định danh chung, các mốc thời gian có thể bị ghép nhầm giữa những lần chạy khác nhau.

**Bước 3: Thu thập mốc thời gian ở từng bước.** Với job tự động, lưu thời điểm sẵn sàng, bắt đầu và kết thúc. Với review hoặc phê duyệt, lưu lúc yêu cầu được gửi, lúc người phụ trách bắt đầu và lúc quyết định được đưa ra. Dùng dấu thời gian có múi giờ rõ ràng và đồng bộ đồng hồ giữa các hệ thống.

**Bước 4: Gắn nguyên nhân cho thời gian chờ.** Phân loại theo hàng đợi runner, hàng đợi kiểm thử, review, phê duyệt, cấp phát môi trường, khóa dùng chung, phụ thuộc bên ngoài, lịch phát hành hoặc retry. Nhãn nguyên nhân giúp chuyển số liệu thành hành động cụ thể.

**Bước 5: Kiểm tra khoảng trống và chồng lấn.** Đảm bảo các khoảng thời gian thuộc cùng một luồng và cùng đơn vị đo. Nếu một khoảng chưa rõ nguyên nhân, giữ nó ở nhóm chưa phân loại thay vì gán tùy tiện vào thực hiện hoặc chờ. Nếu các job chạy song song, phân tích đường găng riêng.

**Bước 6: Theo dõi phân phối, không chỉ trung bình.** Báo cáo trung vị (p50) và các phân vị cao như p85 hoặc p95 cho thời gian giao hàng, thời gian chờ runner, thời gian review và thời gian triển khai. Trung bình có thể che khuất một nhóm nhỏ lần chạy bị chờ rất lâu.

## 4. Xử lý trường hợp job chạy song song

Trong pipeline có nhiều nhánh song song, tổng thời lượng của các job không bằng thời gian trôi qua của cả pipeline. Giả sử sau khi build, hai nhóm test chạy đồng thời:

- Nhóm test A chạy trong 12 phút.
- Nhóm test B chạy trong 9 phút.
- Bước tiếp theo chỉ được bắt đầu khi cả hai nhóm hoàn tất.

Thời gian trôi qua của đoạn song song là 12 phút, vì pipeline phải đợi nhánh lâu nhất. Tổng thời gian thực thi của runner là 21 job-phút. Hai số đo phục vụ hai mục đích khác nhau:

- **Thời gian theo đường găng** cho biết đoạn đó đóng góp bao nhiêu vào thời gian giao hàng.
- **Tổng thời gian thực thi của các job** cho biết lượng tài nguyên hoặc công việc máy đã tiêu thụ.

Không lấy 21 phút thực thi tổng hợp trừ khỏi 12 phút trôi qua để tính thời gian chờ; phép tính đó sai vì hai job chồng lấn. Khi phân tích luồng, xác định chuỗi phụ thuộc quyết định thời điểm bước cuối có thể tiếp tục. Khi phân tích chi phí hoặc năng lực runner, cộng thời lượng của từng job và báo cáo riêng.

Điều tương tự xảy ra khi nhiều pull request cùng chờ một môi trường tích hợp. Có thể một thay đổi không thực hiện công việc nào trong lúc chờ khóa, trong khi một thay đổi khác đang triển khai trên môi trường đó. Cần gắn sự kiện với đúng run ID và tài nguyên để tránh tính trùng hoặc gán nhầm thời gian.

## 5. Những khoảng chờ thường gặp và cách cải thiện

| Nguyên nhân | Câu hỏi chẩn đoán | Hướng cải thiện |
|---|---|---|
| Runner quá tải | Hàng đợi tăng vào giờ cao điểm hay với một loại job cụ thể? | Điều chỉnh concurrency, autoscaling, kích thước pool hoặc phân bổ runner theo loại workload |
| Job phụ thuộc chờ nhau | Bước nào đang chặn các bước phía sau? | Loại bỏ dependency không cần thiết, tách tác vụ độc lập và chạy song song có kiểm soát |
| Build hoặc test kéo dài | Thời gian thực thi tập trung ở bước nào? | Dùng cache đúng cách, build tăng dần, chia test hợp lý và tối ưu phần thực sự chậm |
| Review hoặc phê duyệt chậm | Yêu cầu nằm chờ bao lâu trước khi có người tiếp nhận? | Làm rõ người sở hữu, phân công reviewer dự phòng, cung cấp bằng chứng dễ kiểm tra và thống nhất thời hạn xử lý |
| Môi trường chưa sẵn sàng | Thời gian cấp phát hoặc cấu hình môi trường chiếm bao nhiêu? | Tự động hóa cấu hình, chuẩn hóa môi trường và tạo môi trường tạm thời khi phù hợp |
| Khóa môi trường dùng chung | Có nhiều pipeline tranh cùng một khóa không? | Thu hẹp phạm vi khóa, giảm thời gian giữ khóa và tránh tuần tự hóa các thay đổi độc lập |
| Dịch vụ bên ngoài chậm | Job đang xử lý hay đang đợi API, registry hoặc dịch vụ kiểm thử? | Theo dõi độ trễ phụ thuộc, dùng retry có giới hạn và backoff, bảo đảm thao tác có tính idempotent |
| Test không ổn định | Có lần chạy lại hoặc chờ xác nhận thủ công không? | Tìm và sửa nguyên nhân flaky test; nếu cách ly test, phải có người phụ trách và thời hạn xử lý rõ ràng |
| Chờ cửa sổ phát hành | Bản build đã sẵn sàng nhưng phải đợi lịch triển khai? | Điều chỉnh lịch và quy trình phát hành theo mức rủi ro; dùng progressive delivery khi phù hợp |

Không phải mọi thời gian chờ đều nên bị xóa. Kiểm thử, quét bảo mật, phê duyệt thay đổi có rủi ro và xác minh sau triển khai là những hoạt động bảo vệ chất lượng. Cải tiến nên tập trung vào việc giảm thời gian không tạo thêm bảo đảm, tăng khả năng chuẩn bị trước và đưa bằng chứng đến đúng người đúng lúc.

Ví dụ, nếu một bản phát hành chờ phê duyệt 25 phút vì reviewer chưa nhận được thông báo, có thể cải thiện định tuyến thông báo và phân công người dự phòng. Nếu reviewer cần 5 phút để kiểm tra bằng chứng, không nên đặt mục tiêu loại bỏ 5 phút đó bằng cách bỏ qua bước kiểm tra. Tương tự, giảm thời gian chờ runner bằng cách tăng concurrency cần đi kèm giới hạn tài nguyên và kiểm soát chi phí.

## 6. Các sai lầm khi đọc số liệu

### Coi toàn bộ thời lượng job là thời gian thực hiện

Trạng thái running có thể bao gồm thời gian ngủ, chờ API, chờ khóa hoặc retry. Hãy dùng log, trace và mốc sự kiện để phân biệt. Khi chưa đủ dữ liệu, đặt tên chỉ số là thời lượng job thay vì thời gian thực hiện.

### Cộng thời lượng các job song song như thể chúng chạy nối tiếp

Tổng job-phút phản ánh mức sử dụng tài nguyên. Thời gian giao hàng phụ thuộc vào đường găng của đồ thị phụ thuộc. Cần báo cáo hai chỉ số riêng.

### Dùng mốc bắt đầu và kết thúc không nhất quán

So sánh từ lúc merge đến lúc triển khai ở nhóm này với từ lúc mở pull request đến lúc triển khai ở nhóm khác sẽ tạo ra kết luận sai. Ghi rõ định nghĩa và giữ nguyên ranh giới trong dashboard.

### Chỉ nhìn số trung bình

Một vài lần chạy bị kẹt hàng giờ có thể bị che bởi nhiều lần chạy nhanh. Dùng p50 để hiểu trải nghiệm điển hình và p85 hoặc p95 để phát hiện đuôi phân phối dài.

### Coi mọi thời gian chờ là lãng phí

Thời gian chờ có thể phát sinh từ kiểm soát rủi ro, lịch phát hành hoặc phụ thuộc cần thiết. Trước khi rút ngắn một cổng, xác định mục đích kiểm soát, rủi ro mà nó ngăn chặn và bằng chứng thay thế nếu thay đổi quy trình.

### Bỏ qua lần chạy thất bại và retry

Nếu chỉ đo lần chạy thành công cuối cùng, số liệu sẽ bỏ qua thời gian đã mất do build lỗi, test flaky, rollback hoặc retry. Với trải nghiệm giao hàng, nên tính thời gian từ sự kiện bắt đầu của yêu cầu đến kết quả cuối cùng, đồng thời phân loại thời gian retry và thời gian phục hồi.

## 7. Thiết kế dashboard để tìm đúng điểm nghẽn

Một dashboard hữu ích nên cho phép đi từ tổng quan đến nguyên nhân:

| Nhóm chỉ số | Chỉ số nên theo dõi | Câu hỏi được trả lời |
|---|---|---|
| Luồng đầu-cuối | Thời gian từ commit đến triển khai đã xác minh; p50, p85, p95 | Thay đổi mất bao lâu để đến được người dùng? |
| Thực hiện | Thời lượng build, test, deploy và xác minh | Công việc nào thực sự mất nhiều thời gian xử lý? |
| Hàng đợi | Thời gian chờ runner, worker và khóa môi trường | Tài nguyên hoặc điều phối nào đang hạn chế luồng? |
| Con người | Thời gian chờ tiếp nhận review, thời gian review, độ trễ phê duyệt | Công việc bị chờ ở bước bàn giao hay cần nhiều thời gian kiểm tra? |
| Độ tin cậy | Tỷ lệ thất bại, số lần retry, thời gian phục hồi | Thời gian giao hàng bị kéo dài bởi sự cố nào? |
| Chất lượng sau phát hành | Tỷ lệ xác minh thành công, rollback và lỗi sau triển khai | Tốc độ có đi kèm chất lượng và khả năng phục hồi không? |

Nên lọc các chỉ số theo repository, loại pipeline, nhánh, môi trường, loại runner và thời điểm trong ngày. Một con số tổng hợp toàn hệ thống có thể che giấu việc chỉ một nhóm runner hoặc một môi trường đang bị quá tải.

Khi đọc dashboard, hãy đi theo thứ tự:

1. Xác nhận thời gian đầu-cuối có tăng hay không.
2. Xác định phần tăng đến từ thực hiện, chờ hay khoảng chưa phân loại.
3. Tìm stage và nguyên nhân có đóng góp lớn nhất trên đường găng.
4. Kiểm tra phân vị cao để biết vấn đề có lặp lại hay chỉ xuất hiện ở một số lần chạy.
5. Đề xuất thay đổi đúng nguyên nhân và theo dõi cả tốc độ, độ tin cậy lẫn chất lượng.

Ví dụ, nếu p50 ổn định nhưng p95 tăng mạnh, việc tăng tốc mọi build có thể không giải quyết được vấn đề. Hãy kiểm tra các đợt runner hết chỗ, môi trường dùng chung bị khóa lâu, phụ thuộc bên ngoài không ổn định hoặc các lần retry tập trung vào một số nhánh.

## 8. Quy tắc thực hành

- Luôn ghi rõ mốc bắt đầu, mốc kết thúc và đơn vị đo trước khi công bố một con số thời gian.
- Tách thời điểm công việc sẵn sàng, bắt đầu xử lý và hoàn tất; với bước có người tham gia, thu thập thời điểm người đó bắt đầu làm việc.
- Phân biệt thời gian chờ với độ trễ đầu-cuối khi dữ liệu chưa đủ để biết phần nào là công việc thực tế.
- Với pipeline song song, dùng đường găng để phân tích thời gian giao hàng và tổng job-phút để phân tích mức tiêu thụ tài nguyên.
- Gắn nguyên nhân cho các khoảng chờ lớn, sau đó cải thiện điểm nghẽn có tác động cao nhất.
- Giữ các cổng kiểm soát cần thiết; rút ngắn quy trình bằng tự động hóa, bằng chứng rõ ràng và điều phối tốt hơn.

Khi đã tách được thời gian thực hiện và thời gian chờ, đội ngũ có thể trả lời cụ thể vì sao một thay đổi mất nhiều thời gian để đến production. Điều đó giúp chọn đúng biện pháp: tối ưu phần mềm và pipeline khi xử lý chậm, tăng năng lực hoặc sửa điều phối khi phải chờ, và cải thiện độ tin cậy khi retry hoặc phục hồi đang kéo dài luồng giao hàng.
