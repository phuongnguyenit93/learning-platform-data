# Quyền sở hữu nhánh và nguyên tắc không viết lại lịch sử đã chia sẻ

Khi nhiều người cùng làm việc trên một repository, Git cho phép mỗi người phát triển trên nhánh riêng rồi tích hợp thay đổi vào nhánh chung. Tuy nhiên, nếu nhiều người cùng cập nhật một nhánh mà không có quy ước rõ ràng, họ có thể ghi đè công việc của nhau hoặc làm mất các commit mà đồng đội đang dựa vào. Một nguyên tắc cộng tác quan trọng là **mỗi nhánh phải có người hoặc vai trò chịu trách nhiệm rõ ràng, và không viết lại lịch sử đã được chia sẻ nếu chưa có sự phối hợp của tất cả người liên quan**.

Bài này thuộc chương **Cộng tác bằng Git** của module **SOURCE_CONTROL_GIT**. Module hướng dẫn Git từ working tree, staging area, commit và lịch sử đến branch, merge, rebase, remote và tag; đồng thời rèn cách cộng tác qua nhánh, giải quyết xung đột, truy tìm thay đổi và khôi phục thao tác sai mà vẫn bảo toàn lịch sử quan trọng. Quy ước về quyền sở hữu nhánh và lịch sử chung giúp nhóm phối hợp an toàn khi push, pull, review, merge và hoàn tác thay đổi.

## 1. Vì sao nhóm cần quy ước quyền sở hữu nhánh?

Trong Git, branch về cơ bản là một tham chiếu có tên trỏ đến một commit. Mỗi lần tạo commit trên nhánh hiện tại, tham chiếu của nhánh được cập nhật để trỏ đến commit mới. Git không tự hiểu ai là chủ sở hữu của nhánh và cũng không tự ngăn hai người cùng push lên một nhánh.

Điều đó có nghĩa là quyền sở hữu nhánh là **quy ước làm việc của nhóm**, được hỗ trợ bằng quyền truy cập, quy trình review và branch protection trên máy chủ. Nếu nhóm không thống nhất ai chịu trách nhiệm cập nhật một nhánh, hai người có thể cùng tạo lịch sử riêng rồi push trong những thời điểm khác nhau. Một lần push bị từ chối có thể chỉ là dấu hiệu remote đã tiến lên; một lần force push thiếu phối hợp có thể làm các commit của người khác biến mất khỏi đầu nhánh mà họ đang theo dõi.

Quy ước quyền sở hữu giúp trả lời các câu hỏi thực tế:

- Ai quyết định phạm vi và mục đích của nhánh?
- Ai được phép push trực tiếp, merge hoặc xóa nhánh?
- Ai phải thông báo khi cần rebase hoặc thay đổi lịch sử?
- Ai chịu trách nhiệm xử lý khi nhánh có commit lỗi hoặc bị push nhầm?
- Khi nhánh không còn cần thiết, ai xác nhận việc đóng và xóa nhánh?

Một nhánh có thể có nhiều người đóng góp, nhưng nên có một người hoặc một vai trò chịu trách nhiệm điều phối. Quyền sở hữu rõ ràng không có nghĩa người đó làm toàn bộ công việc; nó có nghĩa nhóm biết ai đang giữ trách nhiệm cập nhật và thông báo trạng thái của nhánh.

## 2. Phân biệt nhánh local, remote-tracking và nhánh trên máy chủ

Trước khi thiết lập quyền sở hữu, cần hiểu các loại nhánh:

| Loại tham chiếu | Ví dụ | Ý nghĩa |
|---|---|---|
| Nhánh local | <code>feature/payment</code> | Tham chiếu trong bản clone hiện tại, được cập nhật khi tạo commit hoặc thao tác nhánh local |
| Remote-tracking branch | <code>origin/feature/payment</code> | Bản tham chiếu local ghi nhận vị trí nhánh trên remote sau lần fetch gần nhất |
| Nhánh trên máy chủ | Nhánh <code>feature/payment</code> trong repository trên máy chủ <code>origin</code> | Tham chiếu thực tế mà các thành viên cùng truy cập và cập nhật qua push |

Remote-tracking branch không phải là nhánh trên máy chủ và cũng không phải một khóa sở hữu. Nó là thông tin local được Git cập nhật qua <code>git fetch</code>. Vì vậy, trước khi kết luận remote đã thay đổi hay chưa, hãy fetch dữ liệu mới:

~~~bash
git fetch origin
git branch -vv
git branch -r
~~~

Nếu <code>feature/payment</code> đang theo dõi <code>origin/feature/payment</code>, điều đó cho biết nhánh local có cấu hình upstream. Nó không chứng minh chỉ có một người đang làm việc trên nhánh đó. Nhóm vẫn cần thỏa thuận người phụ trách và cách phối hợp.

## 3. Mô hình quyền sở hữu nhánh thường dùng

Không có một mô hình duy nhất phù hợp với mọi nhóm. Điều quan trọng là quy ước phải dễ hiểu, được áp dụng nhất quán và phù hợp với tốc độ phát triển của dự án.

### Nhánh tính năng do một người phụ trách

Đây là mô hình đơn giản cho nhóm nhỏ hoặc công việc có phạm vi rõ ràng. Người phụ trách tạo nhánh từ nhánh nền, phát triển và push nhánh đó. Đồng đội có thể review hoặc đóng góp theo thỏa thuận, nhưng người phụ trách điều phối việc tích hợp.

Ví dụ:

~~~bash
git switch main
git pull --ff-only
git switch -c feature/payment-validation

# Thực hiện thay đổi, sau đó tạo commit
git add src/
git commit -m "feat: validate payment requests"

# Đẩy nhánh lên remote và thiết lập upstream
git push -u origin feature/payment-validation
~~~

Nhánh có thể được chia sẻ để review, nhưng người phụ trách cần thông báo trước khi thực hiện thao tác làm thay đổi lịch sử đã push.

### Nhánh tích hợp do maintainer phụ trách

Với nhánh dùng chung như <code>main</code>, <code>develop</code> hoặc nhánh release, maintainer thường chịu trách nhiệm tích hợp các thay đổi. Thành viên phát triển trên nhánh tính năng và gửi pull request hoặc merge request. Maintainer kiểm tra review, CI, chính sách bảo vệ nhánh và thực hiện merge.

Trong mô hình này, nhiều người có thể tạo commit trên các nhánh riêng, nhưng chỉ một nhóm vai trò được phép cập nhật trực tiếp nhánh tích hợp. Điều đó làm giảm nguy cơ vô tình ghi đè lịch sử chung.

### Nhánh cộng tác có nhiều người cùng cập nhật

Một số công việc cần nhiều người cùng sửa trên một nhánh, chẳng hạn nhánh tích hợp ngắn hạn cho một đợt phát hành. Khi đó, nhóm cần chỉ định người điều phối, thống nhất cách lấy thay đổi mới nhất và tránh viết lại commit mà người khác đã lấy về.

Nhóm có thể thống nhất:

- Người điều phối nhánh chịu trách nhiệm thông báo trước khi merge hoặc thay đổi lịch sử.
- Mọi thành viên fetch thường xuyên để biết remote đã tiến lên.
- Mỗi commit có mục đích rõ ràng và không chứa thay đổi ngoài phạm vi.
- Không force push nếu chưa có sự đồng thuận và kế hoạch khôi phục.
- Khi nhánh hoàn tất, maintainer xác nhận kết quả rồi đóng hoặc xóa nhánh theo quy trình.

## 4. Lịch sử đã chia sẻ là gì?

Git lưu lịch sử dưới dạng đồ thị commit. Mỗi commit chứa nội dung snapshot và thông tin liên kết đến commit cha. Khi một commit đã được push lên nhánh remote, người khác có thể fetch nó, tạo nhánh từ nó, merge nó hoặc dựa vào nó để tiếp tục phát triển.

Một commit được xem là **đã chia sẻ** khi có khả năng người khác hoặc hệ thống khác đã sử dụng nó làm cơ sở. Ví dụ:

- Commit đã được push lên nhánh remote mà đồng đội đang theo dõi.
- Commit nằm trong nhánh chung như <code>main</code>, <code>develop</code> hoặc release.
- Commit đã được dùng làm nền cho nhánh khác, pull request, pipeline phát hành hoặc bản build cần truy vết.
- Commit đã được người khác fetch hoặc checkout, dù nhánh remote sau đó không còn trỏ trực tiếp đến commit đó.

Không phải lúc nào bạn cũng biết ai đã fetch một commit. Vì vậy, quy tắc an toàn là coi commit đã push lên nhánh dùng chung là lịch sử đã chia sẻ. Việc nhánh chỉ mang tên cá nhân không tự động chứng minh commit là riêng tư; nếu người khác đã dựa vào commit đó, thay đổi lịch sử vẫn có thể gây ảnh hưởng.

## 5. Vì sao viết lại lịch sử có thể gây rắc rối?

Các thao tác như <code>git commit --amend</code>, <code>git rebase</code> và <code>git reset</code> có thể làm thay đổi vị trí hoặc danh tính của commit. Khi nội dung, commit cha, tác giả, thời điểm hoặc thông điệp thay đổi, Git thường tạo commit mới với mã hash khác.

Ví dụ, một thành viên đã push commit <code>A</code> lên nhánh:

~~~text
P---A   origin/feature/report
~~~

Đồng đội fetch và tạo commit <code>B</code> dựa trên <code>A</code>:

~~~text
P---A---B   colleague/feature/report
     \
      (A đã được dùng làm nền)
~~~

Nếu người đầu tiên rebase hoặc reset để thay <code>A</code> bằng commit mới <code>A'</code>, lịch sử trên remote có thể trở thành:

~~~text
P---A'   origin/feature/report
~~~

Nhánh của đồng đội vẫn chứa lịch sử cũ:

~~~text
P---A---B   colleague/feature/report
 \
  A'       origin/feature/report
~~~

Hai bên không còn cùng một chuỗi tổ tiên. Khi đồng đội push hoặc pull, Git có thể báo non-fast-forward, yêu cầu tích hợp hai dòng lịch sử hoặc tạo ra commit trùng lặp về mặt nội dung. Nếu người đầu tiên dùng force push, tham chiếu remote có thể bỏ qua <code>A</code>, dù commit đó vẫn tồn tại trong bản clone của đồng đội.

Điểm quan trọng: force push di chuyển tham chiếu trên máy chủ. Nó không xóa ngay mọi bản sao commit trong tất cả máy của mọi người, nhưng làm cho lịch sử công khai của nhánh thay đổi và khiến các bản clone đang dựa vào lịch sử cũ phải được xử lý lại.

## 6. Quy tắc trước và sau khi chia sẻ commit

Quy tắc thực hành có thể tóm tắt như sau:

| Trạng thái commit | Thao tác thường an toàn | Điều cần tránh |
|---|---|---|
| Chỉ tồn tại local, chưa ai dùng | Amend, rebase tương tác, reset để sắp xếp hoặc sửa commit | Mất dữ liệu local do reset hoặc restore không kiểm tra |
| Đã push lên nhánh cá nhân nhưng đã xác nhận không ai dựa vào | Có thể phối hợp để sửa lịch sử nếu nhóm cho phép | Tự ý force push vì cho rằng nhánh mang tên cá nhân |
| Đã push lên nhánh nhiều người cùng dùng | Tạo commit mới để sửa hoặc hoàn tác | Rebase, amend, reset rồi force push mà không phối hợp |
| Đã tích hợp vào nhánh chính hoặc phát hành | Ưu tiên revert và tạo thay đổi sửa tiếp theo | Viết lại lịch sử đã được phát hành hoặc các nhánh khác dựa vào |

### Khi commit còn riêng tư

Nếu commit chỉ nằm trong local và chưa được người khác sử dụng, bạn có thể chỉnh sửa lịch sử để làm commit gọn, rõ ràng hơn:

~~~bash
# Sửa thông điệp hoặc bổ sung nội dung vào commit gần nhất
git commit --amend

# Sắp xếp, gộp hoặc chỉnh sửa các commit local gần đây
git rebase -i HEAD~3

# Đưa nhánh local trở lại commit trước đó, giữ thay đổi trong working tree
git reset --mixed HEAD~1
~~~

Chỉ dùng các thao tác này khi đã hiểu trạng thái working tree và index. <code>git reset --hard</code> có thể loại bỏ thay đổi chưa commit trong working tree và index; không dùng nếu chưa chắc dữ liệu cần giữ đã được sao lưu.

### Khi commit đã được chia sẻ

Nếu commit đã nằm trên nhánh chung, hãy giữ lịch sử hiện tại và thêm commit mới để sửa vấn đề. Ví dụ, nếu commit trước đó tạo lỗi, sửa mã nguồn rồi tạo commit khắc phục:

~~~bash
git add src/
git commit -m "fix: handle empty payment response"
git push
~~~

Nếu cần đảo ngược tác động của một commit đã chia sẻ, dùng <code>git revert</code>:

~~~bash
git revert <commit-hash>
git push
~~~

<code>git revert</code> tạo commit mới áp dụng thay đổi ngược với commit được chọn. Commit cũ vẫn nằm trong lịch sử, nên các bản clone đã fetch commit cũ vẫn có thể tích hợp lịch sử một cách nhất quán.

Với merge commit, cần xác định parent chính muốn giữ làm mainline. Lệnh có thể có dạng:

~~~bash
git revert -m 1 <merge-commit-hash>
~~~

Không chọn <code>-m 1</code> theo thói quen nếu chưa kiểm tra thứ tự parent và kết quả mong muốn. Revert merge commit có ảnh hưởng đến cách Git xử lý các lần merge sau; hãy review diff được tạo và phối hợp với maintainer trước khi push.

## 7. Phân biệt amend, rebase, reset, revert và force push

Các lệnh này giải quyết vấn đề khác nhau. Hiểu đúng chúng giúp chọn cách sửa phù hợp với trạng thái chia sẻ của commit.

| Lệnh | Tác dụng chính | Phù hợp khi |
|---|---|---|
| <code>git commit --amend</code> | Thay commit gần nhất bằng một commit mới | Commit chưa chia sẻ hoặc đã có thỏa thuận viết lại |
| <code>git rebase</code> | Phát lại commit trên nền mới, tạo lịch sử commit mới | Nhánh riêng chưa chia sẻ hoặc nhóm đã phối hợp |
| <code>git reset</code> | Di chuyển nhánh hiện tại và có thể cập nhật index/working tree tùy chế độ | Chỉnh sửa lịch sử local chưa chia sẻ |
| <code>git revert</code> | Tạo commit mới đảo ngược thay đổi của commit cũ | Hoàn tác thay đổi đã chia sẻ |
| <code>git push --force</code> | Buộc cập nhật ref remote theo lịch sử local | Chỉ trong tình huống được phép, có kế hoạch và phối hợp rõ ràng |
| <code>git push --force-with-lease</code> | Force push có điều kiện dựa trên giá trị ref remote mong đợi | Giảm nguy cơ ghi đè cập nhật mới chưa biết, khi việc viết lại đã được nhóm cho phép |

### Vì sao force-with-lease không thay thế việc phối hợp?

<code>git push --force-with-lease</code> kiểm tra rằng ref trên remote vẫn ở giá trị mà client đang kỳ vọng trước khi cập nhật. Điều này giúp tránh ghi đè một thay đổi mới trên remote mà bạn chưa biết đến, chẳng hạn đồng đội vừa push thêm commit sau lần fetch gần nhất.

Tuy nhiên, lệnh này không thể biết đồng đội đã fetch commit cũ, tạo nhánh từ nó hoặc dùng nó trong pull request hay chưa. Nếu remote vẫn ở giá trị mong đợi nhưng người khác đã dựa vào lịch sử đó, force-with-lease vẫn có thể thay đổi nhánh khiến công việc của họ cần được phục hồi hoặc tích hợp lại.

Vì vậy:

- Ưu tiên không viết lại lịch sử nhánh dùng chung.
- Nếu có lý do chính đáng để viết lại, thông báo cho tất cả người liên quan và thống nhất thời điểm.
- Yêu cầu mọi người dừng push trong khoảng thời gian thay đổi.
- Fetch và xác nhận ref remote trước khi thao tác.
- Dùng <code>--force-with-lease</code> thay cho <code>--force</code> nếu chính sách cho phép force update.
- Sau thao tác, thông báo commit mới và hướng dẫn đồng đội đồng bộ lại nhánh của họ.

Force-with-lease là lớp bảo vệ kỹ thuật bổ sung, không phải cơ chế thay thế quy trình cộng tác.

## 8. Quy trình làm việc với nhánh tính năng

Một quy trình dễ áp dụng là mỗi công việc có nhánh riêng, người phụ trách rõ ràng và chỉ tích hợp vào nhánh chung sau review:

~~~mermaid
flowchart TD
    A["Maintainer cập nhật main"] --> B["Người phụ trách tạo feature branch"]
    B --> C["Commit các thay đổi nhỏ, có mục đích"]
    C --> D["Push nhánh và mở pull request"]
    D --> E["Review và chạy kiểm tra"]
    E --> F{"Đạt yêu cầu?"}
    F -->|"Chưa"| G["Người phụ trách sửa và push commit mới"]
    G --> D
    F -->|"Đạt"| H["Maintainer tích hợp vào main"]
    H --> I["Đóng pull request và dọn nhánh"]
~~~

Ví dụ các lệnh cơ bản:

~~~bash
# Cập nhật nhánh nền theo cách fast-forward
git switch main
git fetch origin
git pull --ff-only origin main

# Tạo nhánh riêng cho công việc
git switch -c feature/customer-export

# Sau khi sửa mã nguồn
git status
git add src/
git diff --staged
git commit -m "feat: export customer records"

# Đẩy nhánh lên remote
git push -u origin feature/customer-export
~~~

Trong quá trình review, nếu cần sửa, người phụ trách có thể thêm commit mới rồi push tiếp. Nếu nhóm yêu cầu lịch sử nhánh gọn trước khi merge, hãy xác định rõ nhánh có ai khác đang dùng không. Chỉ rebase hoặc squash trên nhánh đã chia sẻ khi mọi người đồng ý và biết cách đồng bộ lại.

Sau khi pull request được tích hợp, maintainer xác nhận nhánh không còn cần thiết rồi xóa nhánh theo chính sách của repository. Việc xóa nhánh không đồng nghĩa xóa commit đã được tích hợp; commit vẫn thuộc lịch sử của nhánh đích.

## 9. Thiết lập quy tắc bảo vệ nhánh chung

Git local không có cơ chế phân quyền chủ sở hữu nhánh giữa các thành viên. Máy chủ Git như GitHub, GitLab hoặc Bitbucket có thể cung cấp branch protection hoặc ruleset để thực thi một phần quy ước.

Các chính sách thường dùng:

- Chặn push trực tiếp vào nhánh chính.
- Yêu cầu pull request hoặc merge request trước khi tích hợp.
- Yêu cầu ít nhất một hoặc nhiều lượt review.
- Bắt buộc CI, test hoặc kiểm tra bảo mật đạt trước khi merge.
- Hạn chế force push và xóa nhánh đối với nhánh quan trọng.
- Chỉ cho maintainer hoặc nhóm được chỉ định quyền merge.
- Yêu cầu cập nhật nhánh với nhánh nền trước khi merge nếu dự án cần.

Branch protection giúp giảm thao tác nhầm, nhưng không thay thế giao tiếp. Một nhánh tính năng không được bảo vệ vẫn có thể chứa lịch sử mà đồng đội đang dựa vào. Nhóm phải giữ quy tắc không viết lại lịch sử đã chia sẻ ở mọi nhánh mà nhiều người hoặc hệ thống đang sử dụng.

## 10. Khi cần viết lại lịch sử đã chia sẻ

Có trường hợp nhóm buộc phải viết lại lịch sử, chẳng hạn phát hiện bí mật đã commit, cần loại bỏ dữ liệu nhạy cảm khỏi toàn bộ lịch sử hoặc sửa cấu trúc commit trước một đợt phát hành. Đây là công việc điều phối ở cấp repository, không phải thao tác cá nhân trên một nhánh đang dùng chung.

Trước khi thực hiện:

1. Xác định chính xác phạm vi ref bị ảnh hưởng: branch, tag, pull request, fork và các bản clone.
2. Thông báo cho người đóng góp và maintainer; chỉ định một người điều phối.
3. Tạm dừng push hoặc merge vào các ref liên quan.
4. Lưu lại các commit hash và trạng thái ref cần thiết để có thể đối chiếu hoặc phục hồi.
5. Thực hiện việc viết lại trong môi trường có thể kiểm tra, review kết quả và xác nhận không còn dữ liệu cần loại bỏ.
6. Cập nhật remote theo kế hoạch được duyệt, sau đó thông báo rõ commit/ref mới.
7. Hướng dẫn các thành viên đồng bộ lại bản clone; không để mỗi người tự đoán nên reset, rebase hay merge.

Nếu nguyên nhân là lộ token, mật khẩu hoặc khóa riêng, viết lại lịch sử không làm bí mật đó tự mất hiệu lực. Cần thu hồi hoặc xoay vòng thông tin xác thực ngay theo quy trình bảo mật, đồng thời xử lý lịch sử theo hướng dẫn của nền tảng lưu trữ.

Nếu một lần force push ngoài ý muốn đã làm nhánh remote lùi về lịch sử cũ:

- Dừng các lần push tiếp theo để tránh làm tình trạng khó phục hồi hơn.
- Thông báo maintainer và những người đang làm trên nhánh.
- Thu thập commit hash còn có trong các bản clone local hoặc tham chiếu mà nhóm lưu lại.
- Xác định chính xác commit nào cần khôi phục và kiểm tra các commit mới đã được tạo sau đó.
- Để maintainer phối hợp phục hồi ref rồi hướng dẫn từng thành viên tích hợp lại công việc.

Không chạy thêm một lệnh force push chỉ vì nghĩ rằng nó sẽ đưa nhánh trở lại trạng thái trước đó. Trước khi cập nhật ref, cần biết chính xác commit nào đang bị thiếu và ai đã tạo thay đổi dựa trên lịch sử hiện tại.

## 11. Các tình huống cộng tác thường gặp

| Tình huống | Cách xử lý nên chọn |
|---|---|
| Commit gần nhất sai thông điệp, chưa push | Dùng <code>git commit --amend</code> |
| Có nhiều commit nhỏ trên nhánh local riêng, chưa ai dùng | Có thể dùng <code>git rebase -i</code> để sắp xếp hoặc gộp |
| Đồng đội đã push thêm commit lên nhánh dùng chung | Fetch, xem lịch sử rồi tích hợp bằng merge hoặc rebase theo quy ước; không reset remote |
| Commit lỗi đã vào <code>main</code> | Tạo commit sửa lỗi hoặc dùng <code>git revert</code> |
| Muốn cập nhật nhánh tính năng theo <code>main</code> | Fetch rồi merge hoặc rebase theo chính sách của nhóm; xác nhận ai đang dùng nhánh |
| Nhánh cá nhân đã push nhưng có đồng đội tạo nhánh từ đó | Xem nhánh đã chia sẻ; phối hợp trước mọi thao tác viết lại |
| Nhánh release cần loại bỏ một thay đổi đã tích hợp | Làm theo quy trình release, thường tạo commit revert hoặc hotfix có review |

### Khi push bị từ chối vì non-fast-forward

Lỗi non-fast-forward thường có nghĩa nhánh remote đã tiến lên bằng một hoặc nhiều commit mà nhánh local chưa chứa. Đây là tín hiệu cần fetch và xem lịch sử:

~~~bash
git fetch origin
git log --oneline --graph --decorate --all -20
~~~

Nếu hai bên có commit riêng, hãy tích hợp theo quy ước của nhóm. Ví dụ dùng merge:

~~~bash
git switch feature/customer-export
git merge origin/feature/customer-export
~~~

Hoặc rebase nếu nhánh thuộc quyền điều phối của bạn và nhóm thống nhất cách làm:

~~~bash
git switch feature/customer-export
git rebase origin/feature/customer-export
~~~

Sau khi giải quyết xung đột và kiểm tra kết quả, push theo cách fast-forward thông thường. Đừng coi non-fast-forward là lý do mặc định để dùng <code>git push --force</code>; lỗi này thường bảo vệ commit đã có trên remote khỏi bị ghi đè.

## 12. Checklist quyền sở hữu nhánh cho nhóm

Trước khi bắt đầu một nhánh, hãy thống nhất:

- Tên nhánh và mục tiêu công việc.
- Người phụ trách hoặc maintainer chịu trách nhiệm điều phối.
- Ai được push trực tiếp và ai có quyền merge.
- Nhánh có được chia sẻ để nhiều người cùng commit hay chỉ dùng để review?
- Quy tắc cập nhật từ nhánh nền là merge hay rebase?
- Có cho phép viết lại lịch sử sau khi push không? Nếu có, cần ai đồng ý?
- Khi hoàn tất, ai đóng pull request và dọn nhánh?

Trước khi sửa lịch sử, tự kiểm tra:

- Commit có còn chỉ nằm trong local của mình không?
- Có ai đã fetch, checkout, tạo nhánh hoặc commit dựa trên nó không?
- Commit có nằm trong nhánh chung, tag, bản phát hành hoặc pipeline cần truy vết không?
- Có thể giải quyết bằng một commit mới hoặc revert không?
- Nếu bắt buộc viết lại, mọi người liên quan đã biết và đồng ý chưa?

Nếu chưa xác định được ai đang dùng lịch sử đó, hãy coi lịch sử đã chia sẻ và chọn cách sửa bằng commit mới.

## 13. Bài tập tự kiểm tra

Thực hành trong repository thử nghiệm với hai bản clone hoặc hai người dùng:

1. Tạo nhánh <code>feature/shared-demo</code>, commit một thay đổi rồi push lên remote.
2. Trong bản clone thứ hai, fetch và tạo một commit mới dựa trên nhánh đó.
3. Quay lại bản clone đầu tiên, thử amend commit đã push và quan sát vì sao hash commit thay đổi.
4. So sánh lịch sử hai bản clone bằng <code>git log --oneline --graph --decorate --all</code>.
5. Thử push theo cách thông thường và giải thích vì sao Git có thể từ chối non-fast-forward.
6. Khôi phục trạng thái cộng tác bằng merge hoặc rebase theo một quy ước đã chọn, không force push.
7. Tạo một commit lỗi trên nhánh thử nghiệm đã chia sẻ rồi dùng <code>git revert</code>. Quan sát commit cũ vẫn còn trong lịch sử.
8. Viết một quy ước ngắn cho nhóm: ai phụ trách nhánh, khi nào được rebase và cách thông báo trước khi thay đổi lịch sử đã push.

Khi nhóm biết rõ ai điều phối từng nhánh, phân biệt được commit riêng tư với commit đã chia sẻ và chọn revert thay cho viết lại lịch sử chung khi cần hoàn tác, việc cộng tác sẽ dễ dự đoán và phục hồi hơn. Đây là nền tảng để áp dụng pull request, review, merge và quy trình phát hành một cách nhất quán.
