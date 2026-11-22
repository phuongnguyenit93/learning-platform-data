# Cho rằng có máy chủ CI đồng nghĩa đã thực hành tích hợp liên tục

Một nhóm có thể cài đặt Jenkins, GitHub Actions, GitLab CI hoặc một nền tảng CI khác, tạo pipeline và nhìn thấy job chạy sau mỗi lần push. Điều đó chứng minh nhóm đã có công cụ tự động hóa. Nó chưa đủ để kết luận nhóm đang thực hành tích hợp liên tục (Continuous Integration - CI).

CI là một cách làm việc của cả nhóm: các thay đổi nhỏ được tích hợp thường xuyên vào một nhánh chung, mỗi lần tích hợp đều được xác minh tự động, và nhóm xử lý ngay khi luồng chính bị hỏng. Máy chủ CI hỗ trợ thực hiện và cung cấp phản hồi cho quy trình đó. Nếu nhóm vẫn giữ các nhánh riêng trong nhiều tuần, chỉ tích hợp vào cuối sprint, chạy test theo lịch hoặc bỏ qua build đỏ, máy chủ CI có thể hoạt động rất đều nhưng rủi ro tích hợp vẫn còn nguyên.

Trong CI/CD, cần phân biệt **có hệ thống chạy pipeline** với **có thói quen tích hợp liên tục**. Bài học này giải thích các dấu hiệu của sự khác biệt và cách tổ chức công việc để CI thực sự giảm rủi ro tích hợp.

## 1. Máy chủ CI làm gì và CI yêu cầu điều gì?

Máy chủ CI nhận sự kiện từ hệ thống quản lý mã nguồn, cấp môi trường chạy job, thực thi các lệnh build và test, lưu log, tạo artifact và báo kết quả. Nó có thể chạy rất nhiều loại workflow, kể cả những workflow không tạo ra thực hành CI đúng nghĩa.

Ví dụ, một nhóm cấu hình pipeline chạy lúc 2 giờ sáng mỗi ngày. Pipeline checkout nhánh chính, build và chạy test. Nếu pipeline đỏ, nhóm xem log vào sáng hôm sau. Đây là tự động hóa build theo lịch. Nó hữu ích, nhưng phản hồi không gắn sát với từng thay đổi và nhiều commit có thể đã được đưa vào nhánh chính trước khi lỗi được phát hiện.

Ngược lại, một nhóm thực hành CI sẽ đưa thay đổi vào nhánh chung với tần suất cao, thường nhiều lần trong ngày khi công việc cho phép. Mỗi lần tích hợp kích hoạt một tập kiểm tra tự động đủ tin cậy. Kết quả được trả về sớm để người tạo thay đổi và cả nhóm biết nhánh chung còn hoạt động hay không.

| Có máy chủ CI | Thực hành CI |
| --- | --- |
| Có cấu hình job và runner | Có quy ước tích hợp thường xuyên vào nhánh chung |
| Pipeline có thể chạy theo lịch hoặc khi có sự kiện | Mỗi lần tích hợp đều kích hoạt xác minh phù hợp |
| Job có thể chạy trên một nhánh riêng lâu dài | Nhóm giữ khoảng cách giữa nhánh làm việc và nhánh chung ngắn |
| Kết quả đỏ có thể được để lại cho lần sau | Nhóm ưu tiên khôi phục nhánh chung ngay khi build bị hỏng |
| Thành công được hiểu là job đã chạy xong | Thành công nghĩa là thay đổi đã được tích hợp và vượt qua các điều kiện chất lượng đã định |
| Có thể chỉ kiểm tra một phần mã nguồn | Kiểm tra được thực hiện trên trạng thái tích hợp mà nhóm sẽ cùng phát triển |

Máy chủ CI là một thành phần kỹ thuật. CI còn bao gồm cách chia nhỏ công việc, cách quản lý nhánh, trách nhiệm sửa lỗi, chất lượng kiểm thử và kỷ luật giữ nhánh chung ở trạng thái có thể tích hợp.

## 2. Tích hợp thường xuyên vào nhánh chung

Tích hợp liên tục yêu cầu các thành viên đưa thay đổi vào một đường phát triển chung với tần suất đủ cao để phát hiện xung đột khi phạm vi thay đổi còn nhỏ. Nhánh chung thường là main hoặc trunk, được bảo vệ bằng kiểm tra và quy tắc merge.

Nếu mỗi người làm trên một nhánh riêng trong nhiều tuần, các thay đổi có thể cùng sửa một API, schema hoặc cấu hình nhưng không nhìn thấy tác động của nhau. Khi merge, nhóm phải xử lý xung đột cú pháp lẫn xung đột hành vi. Một test có thể đã xanh trên nhánh riêng nhưng thất bại khi kết hợp với thay đổi của người khác.

Ví dụ:

- Developer A thay đổi cách tính giá và cập nhật unit test trên nhánh A.
- Developer B đổi cấu trúc dữ liệu đơn hàng trên nhánh B.
- Cả hai nhánh đều build và test thành công khi chạy riêng.
- Khi hai thay đổi được merge gần nhau, mã tính giá sử dụng trường đã bị đổi tên và integration test thất bại.

Pipeline đã làm đúng phần việc được giao: xác minh từng trạng thái mà nó nhận được. Vấn đề nằm ở việc hai thay đổi chỉ được tích hợp muộn. CI giảm rủi ro bằng cách rút ngắn khoảng thời gian giữa các lần tích hợp và kiểm tra trạng thái kết hợp sớm hơn.

Thực hành thường dùng là nhánh ngắn hạn, pull request nhỏ và merge thường xuyên. Feature flag có thể giúp đưa mã chưa sẵn sàng cho người dùng vào nhánh chung mà chưa bật hành vi mới. Cờ tính năng cần có chủ sở hữu, quy tắc bật/tắt và kế hoạch dọn dẹp để không trở thành một dạng nhánh dài hạn ẩn.

Không có một con số cứng áp dụng cho mọi nhóm. Mục tiêu thực tế là thay đổi đủ nhỏ để review, build và sửa lỗi nhanh; thời gian tồn tại của nhánh ngắn; và nhóm không tích lũy một đợt tích hợp lớn vào cuối sprint hoặc trước ngày phát hành.

## 3. Mỗi lần tích hợp phải được xác minh tự động

Một thay đổi chỉ được coi là tích hợp an toàn khi trạng thái mã nguồn sau khi kết hợp đã được kiểm tra. Pipeline nên chạy trên đúng commit hoặc merge result sẽ đi vào nhánh chung.

Một tập kiểm tra cơ bản thường gồm:

1. Kiểm tra format, lint và cấu hình.
2. Compile hoặc build để phát hiện lỗi cú pháp, kiểu dữ liệu và dependency.
3. Chạy unit test cho logic thay đổi và các thành phần liên quan.
4. Chạy các kiểm tra tĩnh, dependency hoặc secret phù hợp với chính sách.
5. Chạy contract hoặc integration test cần thiết cho ranh giới bị ảnh hưởng.
6. Lưu log, báo cáo và metadata của lần chạy để truy vết.

Không phải mọi loại kiểm thử đều cần chạy trong vài giây. Các kiểm thử end-to-end lớn, kiểm thử hiệu năng hoặc môi trường chuyên dụng có thể chạy ở giai đoạn sau hoặc theo lịch. Tuy nhiên, nhóm cần xác định rõ cổng nào bắt buộc trước khi merge và trước khi phát hành. Một pipeline chỉ chạy format rồi báo xanh không thể đại diện cho chất lượng của toàn bộ thay đổi nếu dự án cần các kiểm tra khác.

Điều quan trọng là pipeline xác minh trạng thái sẽ được tích hợp. Nếu CI chỉ chạy trên commit của nhánh pull request nhưng không kiểm tra kết quả kết hợp với nhánh đích, hai pull request riêng lẻ có thể cùng xanh rồi tạo ra một merge result bị lỗi. Có thể dùng merge queue, merged-results pipeline hoặc cơ chế tương đương để xác minh trạng thái kết hợp ngay trước khi merge.

Ví dụ cấu hình khái niệm:

~~~yaml
# Pseudo configuration: tên trường tùy nền tảng CI.
triggers:
  - pull_request_to: main
  - push_to: main

validation:
  - format_and_lint
  - compile
  - unit_tests
  - static_and_secret_checks
  - affected_contract_tests

merge_policy:
  require_successful_validation: true
  require_review: true
  validate_merge_result: true
~~~

Đây là ví dụ mô tả ý tưởng. Khi triển khai, cần ánh xạ sang cú pháp và khả năng thực tế của nền tảng CI đang dùng.

## 4. Giữ nhánh chung luôn có thể tích hợp

Nhánh chung là điểm tham chiếu để cả nhóm tiếp tục phát triển. Khi build hoặc kiểm tra bắt buộc trên nhánh này bị hỏng, nhóm cần xem đó là công việc ưu tiên.

Một quy tắc vận hành hữu ích:

- Không tiếp tục merge thay đổi mới khi nhánh chung đang đỏ, trừ khi có quy trình ngoại lệ rõ ràng.
- Xác định commit và thay đổi gần nhất có khả năng gây lỗi.
- Sửa lỗi ngay hoặc revert thay đổi nếu việc sửa cần nhiều thời gian.
- Chạy lại tập kiểm tra liên quan để xác nhận nhánh chung đã phục hồi.
- Ghi nhận nguyên nhân nếu lỗi đến từ hạ tầng, test flaky hoặc cấu hình pipeline.

Nếu nhóm để build đỏ kéo dài, các kết quả thất bại mới khó phân biệt với lỗi đã tồn tại. Developer cũng không thể tin rằng nhánh chung là nền tảng ổn định để bắt đầu công việc mới. Nhiều nhóm có thể đặt quy ước “dừng và sửa” để mọi người cùng hỗ trợ khôi phục pipeline.

Build đỏ không phải lúc nào cũng do mã nguồn. Runner có thể hết dung lượng, registry không sẵn sàng hoặc secret bị cấu hình sai. Dù nguyên nhân là gì, nhóm vẫn cần khôi phục khả năng xác minh. Hãy phân loại lỗi và chỉ retry lỗi tạm thời theo chính sách có giới hạn; không đánh dấu xanh thủ công khi chưa có bằng chứng.

## 5. Phản hồi phải nhanh và có thể hành động

CI chỉ giúp giảm thời gian sửa lỗi nếu kết quả đến đủ sớm và chỉ rõ nơi cần xử lý. Nếu một thay đổi phải chờ hàng giờ mới nhận được phản hồi, người viết có thể đã chuyển sang công việc khác và mất ngữ cảnh.

Để rút ngắn phản hồi:

- Đặt kiểm tra nhanh, rẻ và có khả năng phát hiện lỗi cao ở đầu pipeline.
- Chạy song song các job độc lập khi tài nguyên cho phép.
- Dùng cache có khóa phù hợp và giữ khả năng clean build.
- Giữ unit test nhỏ, ổn định và cô lập.
- Chia test lớn thành shard dựa trên thời gian chạy thực tế.
- Đo queue time riêng với execution time để biết chậm do thiếu runner hay do công việc.

Thông báo lỗi cần có link đến log, tên job, commit và thông tin test thất bại. Log nên chỉ ra lệnh nào chạy, phiên bản toolchain nào được dùng và artifact nào đã tạo. Không ghi token, mật khẩu hoặc nội dung secret.

Tốc độ không được đánh đổi bằng cách bỏ cổng chất lượng cần thiết. Nếu integration test đang quá chậm, hãy tối ưu dữ liệu, môi trường hoặc cách phân chia test; không nên xóa test chỉ để đạt mục tiêu thời gian mà không đánh giá rủi ro.

## 6. Kiểm thử ổn định và môi trường tái tạo được

Một pipeline chạy mỗi commit nhưng cho kết quả ngẫu nhiên sẽ làm giảm niềm tin của nhóm. Test flaky có thể khiến developer chạy lại job nhiều lần cho tới khi xanh, trong khi lỗi thật vẫn chưa được xử lý.

Hãy kiểm soát các nguồn biến động thường gặp:

- Dữ liệu test dùng chung giữa các job hoặc không được dọn dẹp.
- Test phụ thuộc thứ tự hoặc trạng thái từ lần chạy trước.
- Timeout không phù hợp với tải và điều kiện môi trường.
- Dịch vụ phụ thuộc không được cô lập hoặc không có health check.
- Dependency và toolchain thay đổi ngoài dự kiến.
- Test song song ghi vào cùng tài nguyên.

Khóa dependency, cố định phiên bản runtime và build tool, tạo dữ liệu riêng cho mỗi lần chạy và ghi lại cấu hình môi trường. Pipeline cần có khả năng build sạch, không phụ thuộc vào cache cũ hoặc trạng thái còn sót lại trên runner.

Nếu một test flaky, ghi nhận tỷ lệ lỗi, bước tái hiện và chủ sở hữu sửa. Có thể chạy lại để thu thập bằng chứng về lỗi hạ tầng, nhưng không được biến một lần retry thành kết quả xanh hợp lệ mà bỏ qua lần thất bại ban đầu. Cổng chất lượng phải phản ánh đúng mức độ tin cậy của kiểm tra.

## 7. Tách CI khỏi triển khai liên tục

CI và Continuous Delivery/Continuous Deployment có quan hệ nhưng không đồng nghĩa. CI tập trung vào việc tích hợp và xác minh thay đổi thường xuyên. Continuous Delivery mở rộng quy trình để phần mềm luôn ở trạng thái có thể phát hành; việc triển khai production có thể cần phê duyệt. Continuous Deployment tự động đưa thay đổi đủ điều kiện tới production theo chính sách.

Một nhóm có thể thực hành CI tốt nhưng chưa tự động triển khai production. Ngược lại, có thể có job deploy tự động nhưng vẫn tích hợp mã nguồn theo đợt lớn, khiến nhóm chưa thực sự có CI.

Luồng tổng quát:

~~~mermaid
flowchart TD
    A[Thay đổi nhỏ] --> B[Tích hợp vào nhánh chung]
    B --> C[CI build và kiểm tra tự động]
    C --> D{Các cổng CI đạt?}
    D -->|Không| E[Sửa hoặc revert, giữ nhánh chung xanh]
    E --> B
    D -->|Có| F[Artifact bất biến và metadata]
    F --> G[Trạng thái sẵn sàng phát hành]
    G --> H{Chính sách phát hành}
    H -->|Có phê duyệt| I[Continuous Delivery]
    H -->|Tự động theo chính sách| J[Continuous Deployment]
~~~

CI tạo nền tảng tin cậy cho các bước phát hành. Artifact nên được build một lần, định danh bằng version hoặc digest và promote qua môi trường. Không build lại một artifact khác cho production rồi giả định nó giống bản đã được kiểm tra.

## 8. Ví dụ: hai nhóm có cùng máy chủ CI nhưng cách làm khác nhau

### Nhóm A: tự động hóa nhưng tích hợp theo đợt

Nhóm A có máy chủ CI và pipeline chạy khi push. Tuy nhiên, mỗi developer giữ nhánh riêng trong hai tuần. Pull request lớn, thường chứa nhiều thay đổi. Pipeline chạy unit test trên từng nhánh, nhưng không xác minh merge result. Khi đến cuối sprint, nhiều pull request được merge liên tiếp và integration test bắt đầu thất bại. Nhóm dành vài ngày giải quyết xung đột và sửa lỗi kết hợp.

Nhóm này có CI server và build tự động, nhưng khoảng cách tích hợp vẫn dài. Phần lớn rủi ro chỉ xuất hiện khi các nhánh gặp nhau.

### Nhóm B: tích hợp thường xuyên

Nhóm B chia công việc thành thay đổi nhỏ, giữ nhánh ngắn hạn và merge thường xuyên. Mỗi pull request có review, pipeline chạy trên merge result và các kiểm tra bắt buộc. Khi main bị đỏ, nhóm dừng merge, sửa hoặc revert rồi xác minh lại. Test chậm được tổ chức riêng nhưng vẫn là cổng trước release khi chính sách yêu cầu.

Nhóm B dùng cùng loại máy chủ CI, nhưng thực hành CI tốt hơn vì cách tổ chức công việc tạo ra vòng phản hồi ngắn và trạng thái tích hợp được kiểm tra liên tục.

### Cách chuyển từ A sang B

1. Đo thời gian tồn tại của branch, kích thước pull request và thời gian từ commit tới phản hồi.
2. Chia thay đổi lớn thành phần nhỏ có thể merge độc lập.
3. Bảo vệ nhánh chung bằng review và required checks.
4. Bật kiểm tra merge result hoặc merge queue nếu nền tảng hỗ trợ.
5. Đặt quy tắc xử lý ngay khi main bị đỏ.
6. Theo dõi test flaky, queue time và tỷ lệ sửa lỗi sau merge.

Không cần thay nền tảng CI để bắt đầu thay đổi cách làm. Có thể cải thiện thực hành trước, rồi đầu tư thêm runner, cache hoặc công cụ khi dữ liệu cho thấy nút thắt thực sự.

## 9. Đo xem nhóm có thực sự tích hợp liên tục không

Đừng đánh giá CI chỉ bằng số lượng pipeline hoặc tỷ lệ job chạy thành công. Hãy theo dõi cả hành vi tích hợp và chất lượng phản hồi.

| Chỉ số | Câu hỏi cần trả lời | Dấu hiệu cần chú ý |
| --- | --- | --- |
| Tần suất tích hợp vào nhánh chung | Thay đổi được tích hợp thường xuyên đến đâu? | Nhiều ngày hoặc nhiều tuần không có tích hợp |
| Thời gian sống của branch | Công việc nằm ngoài nhánh chung bao lâu? | Branch dài hạn và pull request lớn |
| Thời gian phản hồi CI | Sau khi tạo thay đổi, mất bao lâu để có kết quả? | Queue hoặc test khiến phản hồi đến quá muộn |
| Tỷ lệ build xanh trên main | Nhánh chung có thường ở trạng thái tốt không? | Build đỏ kéo dài hoặc lỗi bị bỏ qua |
| Tỷ lệ lỗi phát hiện sau merge | Có bao nhiêu lỗi chỉ xuất hiện khi thay đổi đã tích hợp? | Xung đột tích hợp và thiếu test liên quan |
| Tỷ lệ test flaky | Kết quả có lặp lại ổn định không? | Developer thường xuyên rerun để có màu xanh |
| Thời gian khôi phục build | Khi main hỏng, mất bao lâu để trở lại trạng thái tốt? | Không có người chịu trách nhiệm hoặc lỗi tồn tại lâu |

Các chỉ số cần được xem cùng bối cảnh. Tăng số lần merge không tự động cải thiện chất lượng nếu thay đổi không được kiểm tra. Giảm thời gian pipeline cũng không có ý nghĩa nếu test quan trọng bị bỏ. Hãy dùng số liệu để tìm nút thắt và cải thiện quy trình, không biến chúng thành mục tiêu khiến nhóm tối ưu sai hành vi.

## 10. Những hiểu lầm thường gặp

| Hiểu lầm | Vì sao sai | Cách nhìn đúng |
| --- | --- | --- |
| Có Jenkins hoặc GitHub Actions là đã có CI | Công cụ chỉ chạy workflow; nhóm vẫn có thể tích hợp rất muộn | Đánh giá tần suất tích hợp, kiểm tra trên nhánh chung và cách xử lý build đỏ |
| Pipeline chạy mỗi đêm là đủ | Nhiều thay đổi có thể tích lũy trước khi lỗi được phát hiện | Kích hoạt xác minh theo từng lần tích hợp |
| Mỗi nhánh riêng đều xanh nên merge chắc chắn xanh | Hai thay đổi riêng lẻ có thể xung đột khi kết hợp | Kiểm tra merge result và tích hợp thường xuyên |
| CI chỉ cần compile thành công | Build không chứng minh logic và hợp đồng hoạt động đúng | Chọn tập test và cổng chất lượng phù hợp |
| Test flaky có thể rerun tới khi xanh | Kết quả xanh ngẫu nhiên che giấu độ tin cậy thấp | Ghi nhận flaky và sửa nguyên nhân |
| Nhánh main đỏ có thể để cuối sprint xử lý | Các thay đổi sau đó dựa trên nền tảng không đáng tin cậy | Ưu tiên khôi phục main ngay |
| CI phải tự deploy production mới được gọi là CI | CI và các hình thức delivery/deployment là các năng lực liên quan nhưng khác nhau | Đo chất lượng tích hợp riêng với tự động hóa phát hành |
| Càng nhiều job càng chứng minh CI trưởng thành | Số lượng job không phản ánh chất lượng hay vòng phản hồi | Đo kết quả, độ ổn định, tần suất tích hợp và thời gian phục hồi |

## 11. Checklist thực hành CI

Hãy dùng checklist này để đánh giá quy trình hiện tại:

- [ ] Nhóm có một nhánh chung được bảo vệ và dùng làm nền tảng tích hợp.
- [ ] Thay đổi được chia nhỏ và đưa vào nhánh chung thường xuyên.
- [ ] Nhánh làm việc có vòng đời ngắn; pull request đủ nhỏ để review và sửa nhanh.
- [ ] Mỗi lần tích hợp kích hoạt build và các kiểm tra tự động cần thiết.
- [ ] Pipeline xác minh đúng trạng thái sẽ được merge, bao gồm merge result khi cần.
- [ ] Các cổng bắt buộc được thực thi trước khi merge hoặc phát hành.
- [ ] Nhánh chung được giữ ở trạng thái xanh; build hỏng được ưu tiên sửa hoặc revert.
- [ ] Log và thông báo giúp xác định commit, job, test và nguyên nhân lỗi.
- [ ] Dependency, toolchain và môi trường có thể tái tạo; clean build vẫn thành công.
- [ ] Test flaky được đo lường và có người chịu trách nhiệm xử lý.
- [ ] Artifact được định danh bất biến và có thể truy vết về commit cùng pipeline run.
- [ ] Nhóm theo dõi tần suất tích hợp, thời gian phản hồi, tỷ lệ main xanh và thời gian khôi phục.

Máy chủ CI giúp tự động hóa việc kiểm tra, nhưng thực hành tích hợp liên tục chỉ hình thành khi nhóm tích hợp thay đổi thường xuyên, kiểm tra trạng thái kết hợp và phản hồi nhanh với lỗi. Hãy đánh giá CI bằng khả năng giữ nhánh chung luôn có thể phát triển và phát hành, thay vì chỉ bằng việc pipeline có chạy hay không.
