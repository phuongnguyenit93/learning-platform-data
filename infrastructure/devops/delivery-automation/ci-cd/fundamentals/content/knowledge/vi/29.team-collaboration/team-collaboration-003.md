# Ưu tiên sửa nhánh chính hoặc pipeline hỏng

## 1. Vì sao nhánh chính và pipeline hỏng cần được ưu tiên?

Nhánh chính (main branch, thường là main hoặc trunk) là điểm tích hợp chung của nhóm. Developer lấy mã từ nhánh này để bắt đầu công việc, pull request dựa vào nó để kiểm tra khả năng tích hợp, và pipeline thường dùng nó làm nguồn tạo artifact hoặc phát hành. Nếu nhánh chính không build được, test bắt buộc liên tục thất bại hoặc pipeline không thể chạy, nhiều người có thể bị chặn cùng lúc.

Một lỗi ở nhánh tính năng thường giới hạn trong phạm vi một thay đổi hoặc một nhóm nhỏ. Một lỗi ở nhánh chính hoặc pipeline dùng chung có thể ảnh hưởng tới mọi pull request, mọi nhóm phụ thuộc và cả khả năng phát hành khẩn cấp. Vì vậy, khi hai loại công việc cạnh tranh nguồn lực, khôi phục khả năng tích hợp chung thường có giá trị cao hơn tiếp tục tối ưu một tính năng riêng lẻ.

Ưu tiên sửa nhánh chính hoặc pipeline hỏng không có nghĩa mọi lỗi đều phải dừng toàn bộ hoạt động. Nhóm cần xác định phạm vi, tác động, nguyên nhân và cách khôi phục nhanh nhất mà vẫn giữ chất lượng. Có khi hành động đúng là revert commit vừa merge; có khi cần sửa runner, registry hoặc credential; có khi chỉ một test flaky cần được cô lập có thời hạn.

Mục tiêu là đưa hệ thống về trạng thái mà thay đổi mới có thể được tích hợp, kiểm tra và phát hành một cách đáng tin cậy.

## 2. Phân biệt main branch broken và CI platform broken

Hai tình huống có biểu hiện giống nhau là pipeline đỏ nhưng cách xử lý khác nhau.

| Tình huống | Dấu hiệu | Hướng xử lý ban đầu |
|---|---|---|
| Main branch broken do code | Build/test thất bại sau một commit hoặc merge cụ thể; lỗi tái hiện được | Xác định commit gây lỗi, revert hoặc sửa code |
| Pipeline definition broken | Nhiều job không được tạo, cú pháp workflow sai, dependency giữa stage sai | Sửa pipeline-as-code và xác minh bằng pipeline nhỏ |
| Runner/platform failure | Job không được assign, runner offline, executor lỗi hoặc workspace hỏng | Khôi phục runner/control plane, không sửa source để che lỗi |
| Dependency outage | Registry, package repository, cloud API hoặc test database không khả dụng | Xác minh dependency, giảm retry, áp dụng workaround có kiểm soát |
| Test instability | Test lúc pass lúc fail trên cùng revision | Xác định flaky test, cô lập có thời hạn và mở issue sửa gốc |
| Policy/configuration failure | Credential, permission, branch protection hoặc environment lock sai | Khôi phục policy/config đúng và kiểm tra audit |

Trước khi thay đổi code, hãy kiểm tra xem lỗi có xảy ra trên nhiều branch/repository hoặc nhiều runner pool hay không. Nếu mọi job bắt đầu thất bại cùng thời điểm sau khi runner image được cập nhật, khả năng cao nguyên nhân nằm ở nền tảng. Nếu chỉ một commit mới làm test cụ thể thất bại và lỗi tái hiện trên môi trường ổn định, khả năng cao nguyên nhân nằm ở code.

Không gán lỗi nền tảng thành lỗi ứng dụng chỉ vì pipeline trả trạng thái failed. Phân loại sai sẽ làm nhóm mất thời gian sửa nhầm nơi và có thể tạo thêm commit không cần thiết vào nhánh chính.

## 3. Ưu tiên theo mức độ ảnh hưởng

Khi nhiều vấn đề cùng xảy ra, nhóm nên ưu tiên theo phạm vi và mức độ cản trở:

1. **Nhánh chính không build/test được:** chặn tích hợp và có thể làm mọi pull request dựa trên revision lỗi.
2. **Pipeline dùng chung không hoạt động:** ngăn xác minh thay đổi, publish artifact hoặc deploy.
3. **Security/quality gate bị vô hiệu hoặc báo sai:** có thể cho phép thay đổi không an toàn đi qua hoặc chặn mọi thay đổi hợp lệ.
4. **Production/release pipeline bị hỏng:** ảnh hưởng khả năng khắc phục sự cố và phát hành.
5. **Một nhóm job hoặc runner pool bị lỗi:** ảnh hưởng một phần developer/workload.
6. **Một pipeline hoặc test riêng lẻ bị lỗi:** phạm vi nhỏ hơn, xử lý theo owner và mức tác động.

Thứ tự trên là hướng dẫn khởi đầu, không phải luật cứng. Một lỗ hổng bảo mật nghiêm trọng hoặc sự cố production có thể cần ưu tiên cao hơn lỗi build của main. Hãy đánh giá theo tác động thực tế, thời gian, số nhóm bị chặn và rủi ro nếu trì hoãn.

## 4. Dùng severity và phạm vi để điều phối

Một cách đơn giản là phân loại sự cố theo severity:

| Mức | Phạm vi/tác động | Phản ứng |
|---|---|---|
| SEV-1 | Main branch không thể tích hợp trên diện rộng, CI dùng chung ngừng hoạt động, release khẩn cấp bị chặn hoặc có nguy cơ bảo mật nghiêm trọng | Kích hoạt incident coordination, tập trung người phù hợp và cập nhật thường xuyên |
| SEV-2 | Một pool, pipeline quan trọng hoặc nhóm lớn bị ảnh hưởng; có workaround nhưng năng suất giảm mạnh | Chỉ định owner xử lý, theo dõi tiến độ và thông báo nhóm liên quan |
| SEV-3 | Một job/test hoặc một dự án bị ảnh hưởng, có workaround rõ | Giao owner, xử lý theo SLA/priority thông thường |
| SEV-4 | Vấn đề nhỏ, không chặn công việc chính | Đưa vào backlog và xử lý theo kế hoạch |

Tên mức severity và thời gian phản hồi phải phù hợp quy trình của tổ chức. Không nên tự đặt một cam kết thời gian chung nếu chưa có SLO hoặc on-call policy. Quan trọng là cùng một mức phải có ý nghĩa nhất quán và dẫn tới hành động cụ thể.

## 5. Quy trình phản ứng trong những phút đầu

Khi phát hiện main hoặc pipeline dùng chung bị hỏng:

1. Xác nhận lỗi và thời điểm bắt đầu; tránh dựa vào một notification chưa được kiểm chứng.
2. Xác định phạm vi: main, pull request, một repository, nhiều repository, một runner pool hay toàn CI.
3. Ghi nhận commit, pipeline run, job, stage, runner và dependency liên quan.
4. Chỉ định một người điều phối và một owner kỹ thuật cho từng nhánh điều tra.
5. Thông báo ngắn gọn rằng nhánh chính/pipeline đang gặp sự cố, nêu workaround nếu đã xác minh.
6. Tạm dừng các thay đổi có thể làm phạm vi sự cố rộng hơn nếu cần.
7. Chọn hành động phục hồi có rủi ro thấp và thời gian ngắn nhất.
8. Xác minh main và pipeline bằng một lần chạy đầy đủ trước khi thông báo đã phục hồi.

Không để nhiều người cùng sửa một file pipeline hoặc cùng push các commit sửa main mà không điều phối. Chia việc theo hướng độc lập: một người xác định nguyên nhân, một người kiểm tra runner/dependency, một người chuẩn bị revert hoặc fix, một người cập nhật trạng thái cho nhóm.

## 6. Bảo vệ nhánh chính để sự cố không lan rộng

Branch protection là lớp kiểm soát giúp hạn chế thay đổi không được xác minh đi vào nhánh chính. Tùy nền tảng, chính sách có thể gồm:

- Yêu cầu pull request thay vì push trực tiếp.
- Bắt buộc các status check quan trọng phải pass.
- Yêu cầu review từ owner hoặc nhóm có trách nhiệm.
- Chặn force push và xóa nhánh chính.
- Yêu cầu branch phải cập nhật với base branch trước khi merge.
- Dùng CODEOWNERS hoặc cơ chế tương đương cho pipeline, release config và policy.
- Giới hạn quyền bypass và ghi audit cho mọi lần bypass.

Không nên tắt branch protection chỉ để merge nhanh một bản sửa nếu chưa đánh giá rủi ro. Với tình huống khẩn cấp, nếu quy trình cho phép bypass, cần có người chịu trách nhiệm, lý do, phạm vi, thời hạn và bước xác minh sau đó. Bypass không nên trở thành đường đi mặc định cho mọi sửa chữa.

## 7. Khi nào nên revert thay vì sửa tiếp trên main?

Revert là cách đưa thay đổi gây lỗi ra khỏi nhánh chính bằng một commit mới đảo ngược tác động của commit trước. Đây thường là lựa chọn phù hợp khi:

- Có commit mới liên quan rõ ràng tới lỗi.
- Chưa xác định được cách sửa an toàn trong thời gian ngắn.
- Thay đổi vừa merge làm main không build hoặc test bắt buộc thất bại.
- Có thể đảo ngược mà không làm hỏng migration hoặc dữ liệu đã phát sinh.
- Mục tiêu trước mắt là khôi phục khả năng tích hợp cho cả nhóm.

Revert thường dễ truy vết hơn viết lại lịch sử bằng reset/force push trên nhánh dùng chung. Nó tạo một commit mới và giữ nguyên lịch sử đã được chia sẻ.

Không nên revert mù khi lỗi thực chất đến từ runner, registry hoặc dependency. Cũng không nên revert một migration phá hủy dữ liệu nếu thao tác đảo ngược có thể làm mất dữ liệu hợp lệ. Trước khi revert, xác định tác động tới schema, event, config, side effect và release đã triển khai.

## 8. Quy trình revert an toàn

Một quy trình thông thường:

1. Xác định commit hoặc merge commit gây lỗi bằng log, pipeline và phạm vi thay đổi.
2. Kiểm tra các commit tiếp theo có phụ thuộc vào thay đổi đó không.
3. Đánh giá migration, config, API/event contract và dữ liệu đã được ghi.
4. Tạo revert commit trên nhánh sửa chữa hoặc pull request khẩn cấp.
5. Chạy build, test và các gate cần thiết trong phạm vi có thể.
6. Review nhanh bởi người có thẩm quyền theo quy trình.
7. Merge revert vào main.
8. Chạy lại pipeline đầy đủ và xác minh trạng thái main.
9. Thông báo main đã phục hồi và ghi nhận follow-up để sửa nguyên nhân gốc.

Ví dụ revert một commit thường:

~~~bash
git log --oneline -10
git revert <commit-sha>
git push origin HEAD:refs/heads/fix/restore-main
~~~

Đây là ví dụ minh họa; thao tác push cần tuân theo quy trình branch/PR của repository. Với merge commit, Git cần biết mainline parent:

~~~bash
git revert -m 1 <merge-commit-sha>
~~~

Tham số -m 1 giả định parent thứ nhất là nhánh chính trước khi merge. Cần kiểm tra cấu trúc merge commit trước khi dùng. Revert một merge commit có thể ảnh hưởng tới các commit đi kèm; nếu sau này muốn merge lại thay đổi đã revert, cần hiểu cách Git ghi nhận lịch sử và có thể cần revert chính revert commit.

## 9. Khi nào nên sửa nóng (hotfix) thay vì revert?

Hotfix có thể phù hợp khi:

- Nguyên nhân đã rõ và sửa đổi nhỏ, có thể kiểm thử nhanh.
- Revert gây mất một thay đổi cần thiết hoặc tạo trạng thái không tương thích.
- Có lỗi bảo mật hoặc dữ liệu cần bản sửa trực tiếp.
- Một dependency/config sai có thể được sửa độc lập.
- Nhóm đã có test tái hiện lỗi và cách xác minh fix.

Hotfix không nên trở thành lý do bỏ qua review, test hoặc audit. Tối thiểu cần xác định phạm vi, test hồi quy liên quan, review phù hợp và pipeline xác minh sau merge. Nếu không thể chạy đầy đủ suite do nền tảng CI đang hỏng, phải có kế hoạch kiểm tra thay thế, người chấp thuận rủi ro và bước chạy lại đầy đủ sau khi CI được khôi phục.

Một lựa chọn khác là revert trước để khôi phục main, rồi phát triển hotfix riêng trên branch mới. Cách này tách mục tiêu phục hồi nhanh khỏi công việc sửa nguyên nhân gốc.

## 10. Khi pipeline hỏng do cấu hình hoặc nền tảng

Nếu nhiều commit/repository cùng thất bại ở một bước giống nhau, hãy kiểm tra pipeline service trước khi thay đổi source:

- Scheduler có tạo và assign job không?
- Runner agent có online, đủ label và đúng version không?
- Runner image vừa được nâng cấp hay thay đổi dependency hệ thống không?
- Secret/identity có hết hạn hoặc bị thay policy không?
- Registry/package repository có lỗi, throttling hoặc certificate issue không?
- Artifact store có quota, permission hoặc network issue không?
- Workflow template hoặc shared action vừa thay đổi không?
- Concurrency limit/resource lock có làm job chờ vô hạn không?

Hành động phục hồi có thể là rollback runner image, khôi phục shared workflow template, cấp lại credential theo quy trình, sửa quota hoặc tạm chuyển job sang pool ổn định. Mọi thay đổi nền tảng cần được ghi lại và xác minh trên một pipeline đại diện trước khi mở rộng.

Không chỉnh sửa từng repository để né một lỗi nền tảng dùng chung nếu có thể sửa tại nguồn. Workaround theo repository có thể tạo cấu hình lệch và tăng chi phí bảo trì.

## 11. Xử lý flaky test mà không che giấu lỗi

Flaky test là test có kết quả không ổn định trên cùng revision và điều kiện tương đương. Nó có thể làm main trông như bị hỏng dù code không thay đổi, nhưng cũng có thể che lỗi thật nếu nhóm liên tục rerun đến khi pass.

Khi nghi ngờ flaky test:

1. Kiểm tra lịch sử pass/fail theo test, runner, OS và thời điểm.
2. Rerun có giới hạn để xác định tính không ổn định; lưu mọi kết quả.
3. Xác định phụ thuộc thời gian, thứ tự, dữ liệu dùng chung, network hoặc concurrency.
4. Tạo issue có owner và thời hạn sửa.
5. Nếu phải quarantine test, làm rõ test nào bị bỏ qua, phạm vi ảnh hưởng và thời hạn.
6. Giữ các gate khác và không biến toàn bộ suite thành non-blocking.
7. Khôi phục test vào gate bắt buộc sau khi sửa và xác minh ổn định.

Quarantine có thời hạn là biện pháp giảm tắc nghẽn, không phải kết quả cuối. Nếu test liên quan bảo mật, dữ liệu hoặc luồng nghiệp vụ trọng yếu, cần biện pháp kiểm soát thay thế trước khi cho phép merge.

## 12. Khi nào cần tạm dừng merge?

Merge freeze là việc tạm dừng hoặc giới hạn merge vào main trong lúc xử lý sự cố. Nó có thể hữu ích khi:

- Main đang ở trạng thái không build/test được.
- Một pipeline gate dùng chung không thể xác minh thay đổi.
- Nhiều commit liên tiếp có thể làm khó xác định nguyên nhân.
- Một migration hoặc thay đổi nền tảng đang ở trạng thái không nhất quán.
- Nhóm cần giữ main ổn định để tạo hotfix hoặc rollback.

Freeze nên có phạm vi và thời hạn rõ. Có thể chỉ đóng merge với một nhóm file, một repository hoặc một loại thay đổi. Các pull request độc lập và an toàn vẫn có thể được xử lý nếu gate phù hợp còn hoạt động.

Khi cần freeze toàn bộ, thông báo lý do, người quyết định, điều kiện mở lại và cách xử lý PR đang chờ. Tránh freeze không thời hạn hoặc để developer tự suy đoán trạng thái.

## 13. Mở lại merge sau khi phục hồi

Không mở merge chỉ vì một commit sửa chữa đã được merge hoặc một job đơn lẻ đã xanh. Điều kiện mở lại cần được định nghĩa:

- Main build thành công từ revision hiện tại.
- Required checks quan trọng chạy và pass.
- Pipeline template và runner pool liên quan hoạt động ổn định.
- Artifact/report được upload và truy xuất nếu workflow yêu cầu.
- Không còn trạng thái deployment hoặc migration dang dở ảnh hưởng tới main.
- Các test được quarantine có owner, expiry và biện pháp thay thế.
- Nhóm đã thông báo rõ merge được phép trở lại.

Với pipeline có nhiều stage, nên chạy ít nhất một pipeline end-to-end đại diện từ checkout tới test/artifact. Nếu sự cố ảnh hưởng nhiều runner pool hoặc nhiều repository, xác minh trên từng pool/phạm vi liên quan trước khi tuyên bố phục hồi toàn diện.

## 14. Phân vai để tránh nhiều người sửa cùng một chỗ

Trong sự cố ảnh hưởng nhiều nhóm, phân vai rõ giúp giảm trùng lặp và xung đột:

| Vai trò | Trách nhiệm |
|---|---|
| Incident coordinator | Xác định ưu tiên, phân công, theo dõi trạng thái và điều phối thông tin |
| Main branch owner | Đánh giá commit gây lỗi, chọn revert/hotfix và xác minh main |
| CI platform owner | Điều tra scheduler, runner, template, artifact và dependency |
| Test owner | Phân tích test failure/flakiness và xác định phạm vi test thay thế |
| Release owner | Đánh giá tác động tới artifact, deploy, môi trường và release đang chạy |
| Communicator | Cập nhật developer, nhóm phụ thuộc và stakeholder theo nhịp thống nhất |

Một người có thể đảm nhiệm nhiều vai trò trong nhóm nhỏ, nhưng cần nói rõ ai đang quyết định và ai đang thực hiện. Mỗi hành động nên có một owner chịu trách nhiệm kết thúc, tránh trạng thái mọi người cùng xem nhưng không ai xử lý đến cùng.

## 15. Kênh và nhịp cập nhật trong sự cố

Thông tin trong sự cố nên ngắn, có cấu trúc và tập trung vào điều người khác cần biết:

- Trạng thái hiện tại: main/pipeline đang lỗi ở đâu.
- Phạm vi: repository, pool, nhóm hoặc stage nào bị ảnh hưởng.
- Tác động: merge, test, release hay deploy đang bị chặn.
- Owner: ai đang điều tra hoặc sửa.
- Hành động đang thực hiện: revert, hotfix, runner recovery hay freeze.
- Workaround: cách làm tạm thời đã được xác minh.
- Mốc cập nhật tiếp theo: khi nào nhóm sẽ có thông tin mới.

Ví dụ thông báo:

~~~text
CI incident: main branch checks đang thất bại ở integration-test.
Phạm vi: repository order-service; các job unit test vẫn hoạt động.
Tác động: tạm dừng merge vào main trong lúc xác minh.
Owner: service owner điều tra commit gần nhất; CI platform kiểm tra database runner.
Workaround: tiếp tục làm việc trên feature branch, chưa tự bypass required check.
Cập nhật tiếp theo: sau khi có kết quả phân loại nguyên nhân.
~~~

Không đưa secret, token, payload khách hàng hoặc log nhạy cảm vào kênh chung. Dùng link có phân quyền tới incident record và log đã được xử lý.

## 16. Giữ nhịp làm việc và giảm context switching

Sự cố main/pipeline thường kéo nhiều developer khỏi công việc đang làm. Điều phối tốt cần giới hạn số người bị gián đoạn:

- Chỉ gọi người có kiến thức cần thiết vào nhóm xử lý trực tiếp.
- Giao các nhánh điều tra độc lập cho owner cụ thể.
- Yêu cầu người không trực tiếp xử lý tiếp tục công việc không phụ thuộc main nếu phù hợp.
- Ghi lại giả thuyết đã thử và kết quả để tránh lặp lại.
- Dùng một incident timeline chung.
- Hạn chế nhiều lần thử sửa nhỏ liên tiếp mà không có giả thuyết và tiêu chí kiểm tra.
- Sau khi phục hồi, chuyển điều tra dài hạn sang follow-up task có owner.

Một nhóm xử lý nhỏ, được điều phối rõ ràng, thường hiệu quả hơn việc kéo toàn bộ team vào cùng một cuộc trao đổi kỹ thuật.

## 17. Kiểm soát thay đổi trong thời gian main bị hỏng

Trong khi main chưa ổn định, mỗi commit mới có thể làm khó việc xác định nguyên nhân. Nhóm có thể áp dụng:

- Tạm ngừng merge thay đổi không khẩn cấp.
- Chỉ cho phép revert hoặc hotfix đã được owner xác nhận.
- Giữ nguyên runner image/template trong lúc điều tra nếu chúng chưa được xác định là nguyên nhân.
- Ghi lại mọi thay đổi cấu hình, quota, secret hoặc permission.
- Không thực hiện nhiều thay đổi độc lập trên cùng môi trường cùng lúc.
- Dùng branch sửa chữa riêng và pull request có phạm vi nhỏ.
- Khi cần bypass, lưu người thực hiện, lý do, revision và bước kiểm tra bù.

Không nên khóa mọi hoạt động mà không cần thiết. Nếu main bị hỏng do một test và pipeline lint/build vẫn đáng tin cậy, có thể tiếp tục các công việc không phụ thuộc gate bị lỗi theo policy rõ ràng. Điều quan trọng là không trình bày trạng thái đó như một main hoàn toàn xanh.

## 18. Quy trình khôi phục main branch theo từng bước

~~~mermaid
flowchart TD
    A[Detect main or shared pipeline failure] --> B[Confirm scope and impact]
    B --> C[Classify source, pipeline, runner or dependency]
    C --> D[Assign incident and technical owners]
    D --> E{Main integrity at risk?}
    E -- Yes --> F[Freeze or restrict merges]
    E -- No --> G[Keep unaffected work moving]
    F --> H{Known safe revert?}
    G --> H
    H -- Yes --> I[Revert offending change]
    H -- No --> J[Prepare reviewed hotfix or platform repair]
    I --> K[Run required validation]
    J --> K
    K --> L{Main and pipeline healthy?}
    L -- No --> M[Continue investigation / recovery]
    M --> K
    L -- Yes --> N[Reopen merge and communicate]
    N --> O[Root cause and follow-up]
~~~

Quy trình có thể lặp lại nếu lần sửa đầu chưa giải quyết được lỗi. Mỗi vòng cần có giả thuyết, thay đổi nhỏ, bằng chứng kiểm tra và quyết định tiếp theo. Tránh thay nhiều thành phần cùng lúc vì sẽ khó biết hành động nào thực sự khôi phục hệ thống.

## 19. Ví dụ: main hỏng sau khi merge thay đổi dependency

Giả sử một pull request nâng version thư viện HTTP. Sau khi merge, unit test vẫn pass nhưng integration test trên main thất bại do cách xử lý TLS thay đổi. Các pull request khác cũng bị block vì required check dùng chung.

Nhóm xử lý:

1. Coordinator xác nhận lỗi chỉ xuất hiện sau merge commit và tập trung ở integration-test.
2. Main owner kiểm tra commit và xác nhận có thể revert mà không ảnh hưởng migration/dữ liệu.
3. Test owner tạo test tái hiện để bảo đảm lỗi được hiểu.
4. Release owner kiểm tra artifact từ revision lỗi đã được publish/deploy chưa.
5. Nhóm merge revert commit, không force-push lịch sử main.
6. Chạy lại pipeline đầy đủ, xác minh integration test và artifact stage.
7. Thông báo mở lại merge khi required checks hoạt động.
8. Tạo follow-up để cập nhật dependency trong branch riêng với compatibility test.

Nếu artifact lỗi đã được deploy production, nhóm cần đánh giá riêng rollback release và dữ liệu/runtime state. Khôi phục main không tự động khôi phục production.

## 20. Ví dụ: runner pool hỏng nhưng main code vẫn đúng

Giả sử hàng loạt pipeline Linux bắt đầu fail ở bước checkout với lỗi disk full. Job trên Windows vẫn chạy; pipeline trên Linux thất bại bất kể commit.

Phân tích:

- So sánh lỗi trên nhiều repository và revision.
- Kiểm tra disk free/inode và workspace cleanup của runner pool.
- Xác định một runner image mới không còn cleanup cache cũ.
- Cô lập pool bị ảnh hưởng hoặc ngừng cấp job mới vào pool đó.
- Chuyển job phù hợp sang pool dự phòng nếu có.
- Sửa image/cleanup policy, tạo runner mới và chạy pipeline đại diện.
- Xác minh queue wait, checkout success và artifact upload trước khi đưa pool trở lại.

Trong trường hợp này, revert code ứng dụng sẽ không giải quyết lỗi. Nhóm cần khôi phục runner platform và giữ main code nguyên vẹn.

## 21. Xử lý khi required check không thể chạy

Một số tình huống CI outage làm required status check không thể hoàn tất. Tùy nền tảng, PR có thể bị pending hoặc bị block. Đây là cơ chế bảo vệ, không phải lỗi cần bỏ qua ngay.

Trước khi xem xét bypass:

- Xác định check nào không chạy và vì sao.
- Xem có check thay thế tương đương đã được tin cậy hay không.
- Đánh giá loại thay đổi và mức rủi ro.
- Kiểm tra có thể khôi phục check trong thời gian hợp lý không.
- Nếu policy cho phép ngoại lệ, yêu cầu người có thẩm quyền, lý do, phạm vi và audit record.
- Ghi rõ kiểm tra bù bắt buộc sau khi CI trở lại.

Không nên đặt một status check giả luôn pass để mở khóa merge. Cách đó làm mất ý nghĩa branch protection và có thể để lại cấu hình nguy hiểm sau incident.

## 22. Theo dõi thời gian phục hồi và chất lượng xử lý

Để cải thiện quy trình, ghi nhận:

- Time to detect: thời gian từ lúc lỗi bắt đầu tới lúc nhóm phát hiện.
- Time to acknowledge: thời gian tới khi có owner nhận xử lý.
- Time to classify: thời gian xác định lỗi thuộc code, pipeline, runner hay dependency.
- Time to restore main: thời gian main trở lại trạng thái tích hợp được.
- Time to restore CI: thời gian pipeline dùng chung hoạt động ổn định.
- Blocked developer time: thời gian hoặc số người bị chặn công việc.
- Reopen rate: tỷ lệ sự cố tái diễn sau khi tuyên bố phục hồi.
- Follow-up completion: tỷ lệ hành động ngăn tái diễn được hoàn thành.

Không nên tối ưu time to restore bằng cách bỏ qua kiểm tra bắt buộc. Một lần mở main quá sớm rồi phải freeze lần nữa có thể làm tổng thời gian gián đoạn dài hơn và giảm niềm tin của nhóm.

## 23. Sau phục hồi: tìm nguyên nhân gốc và ngăn tái diễn

Sau khi main và pipeline ổn định, nhóm nên chuyển từ phản ứng sang cải thiện:

- Tái dựng timeline từ commit, pipeline run, runner event và deployment record.
- Xác định nguyên nhân gốc và các yếu tố góp phần.
- Phân biệt lỗi kỹ thuật với lỗ hổng quy trình hoặc thiếu quan sát.
- Bổ sung test tái hiện hoặc kiểm tra pipeline.
- Sửa runner image/template/shared workflow nếu liên quan.
- Bổ sung alert cho tín hiệu phát hiện sớm.
- Cải thiện branch protection hoặc ownership nếu cần.
- Cập nhật runbook, dependency policy và rollback plan.
- Giao owner và deadline cho từng action item.

Post-incident review nên tập trung vào hệ thống và quyết định, không đổ lỗi cá nhân. Mục tiêu là giảm xác suất tái diễn và rút ngắn thời gian phục hồi lần sau.

## 24. Những anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách cải thiện |
|---|---|---|
| Tiếp tục merge khi main đang không kiểm chứng được | Lỗi chồng lên nhau, khó xác định commit gây hỏng | Freeze hoặc giới hạn merge theo phạm vi |
| Revert mọi lỗi pipeline | Thay đổi source không liên quan bị đảo ngược | Phân loại code/platform/dependency trước |
| Force-push để xóa commit trên main | Lịch sử dùng chung bị viết lại, khó truy vết | Dùng revert commit theo policy |
| Sửa nóng mà không có test tái hiện | Có thể chỉ che triệu chứng | Tạo test hoặc bằng chứng tối thiểu trước/sau fix |
| Tắt required checks để merge nhanh | Mất kiểm soát chất lượng và audit | Dùng ngoại lệ có phạm vi, owner và kiểm tra bù |
| Nhiều người cùng sửa một pipeline | Xung đột và khó phối hợp | Phân vai, một owner tích hợp thay đổi |
| Rerun flaky test tới khi pass | Che lỗi và làm sai số liệu | Giới hạn retry, quarantine có hạn và sửa gốc |
| Restart toàn bộ runner khi CI chậm | Có thể tạo thêm tải và mất evidence | Điều tra scheduler, resource và dependency |
| Mở lại merge sau một job xanh | Bỏ sót stage hoặc pool còn lỗi | Chạy validation end-to-end theo phạm vi |
| Đóng incident mà không follow-up | Nguyên nhân gốc tiếp tục tồn tại | Action item có owner, deadline và review |

## 25. Checklist ưu tiên sửa main hoặc pipeline

Khi main hoặc pipeline dùng chung gặp sự cố, hãy kiểm tra:

- [ ] Lỗi đã được xác nhận và ghi nhận thời điểm bắt đầu.
- [ ] Phạm vi repository, branch, runner pool, stage và nhóm bị ảnh hưởng đã rõ.
- [ ] Nguyên nhân được phân loại sơ bộ: source, pipeline definition, runner, dependency hay policy.
- [ ] Có coordinator và owner kỹ thuật rõ ràng.
- [ ] Nhóm đã thông báo trạng thái, tác động và workaround đã xác minh.
- [ ] Quyết định freeze/giới hạn merge dựa trên rủi ro thực tế.
- [ ] Commit gây lỗi và dependency với các commit sau đã được kiểm tra.
- [ ] Revert/hotfix có đánh giá migration, dữ liệu, artifact và side effect.
- [ ] Required checks không bị vô hiệu tùy tiện; bypass nếu có được audit.
- [ ] Thay đổi sửa chữa có phạm vi nhỏ và có bằng chứng kiểm tra.
- [ ] Main build/test và pipeline end-to-end đại diện đã pass.
- [ ] Runner pool, artifact upload và status callback liên quan đã hoạt động.
- [ ] Nhóm đã thông báo điều kiện mở lại merge.
- [ ] Incident timeline và action item ngăn tái diễn được ghi nhận.

## 26. Nguyên tắc thực hành cốt lõi

1. Ưu tiên khôi phục khả năng tích hợp chung vì main và pipeline dùng chung ảnh hưởng tới nhiều nhóm.
2. Phân biệt lỗi code với lỗi pipeline, runner, dependency và policy trước khi sửa.
3. Đánh giá severity theo phạm vi, tác động người dùng và khả năng phát hành.
4. Chỉ định coordinator và owner; tránh nhiều người sửa cùng một nơi không điều phối.
5. Dùng revert để phục hồi nhanh khi thay đổi gây lỗi có thể đảo ngược an toàn.
6. Dùng hotfix khi nguyên nhân rõ, có test và có quy trình review phù hợp.
7. Bảo vệ main bằng branch protection; mọi bypass phải có lý do, phạm vi và audit.
8. Freeze merge có phạm vi, điều kiện mở lại và thông tin rõ ràng.
9. Xác minh main và pipeline end-to-end trước khi tuyên bố phục hồi.
10. Sau incident, bổ sung test, telemetry, runbook và action item để ngăn tái diễn.

Ưu tiên sửa nhánh chính hoặc pipeline hỏng là một quyết định điều phối để bảo vệ luồng làm việc chung. Khi nhóm phân loại đúng nguyên nhân, phân vai rõ, chọn revert hoặc hotfix có căn cứ và chỉ mở lại merge sau khi có bằng chứng, thời gian gián đoạn sẽ giảm mà chất lượng phát hành vẫn được duy trì.
