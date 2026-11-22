# Chuyển một đoạn lịch sử bằng git rebase --onto

Trong quá trình phát triển, một nhánh tính năng đôi khi được tạo từ một nhánh khác thay vì từ main. Sau đó, kế hoạch có thể thay đổi: bạn muốn chuyển phần commit riêng của nhánh tính năng sang một nền mới. Lệnh **git rebase --onto** cho phép chọn một tập commit theo một mốc giới hạn rồi phát lại tập commit đó trên một điểm đích khác.

Điểm đặc biệt của **--onto** là nó tách hai ý nghĩa: **commit nào cần phát lại** và **phát lại chúng ở đâu**. Hiểu rõ hai tham số này giúp bạn chuyển đúng phần lịch sử, tránh mang theo các commit không thuộc phạm vi công việc.

Sau bài này, bạn có thể:

- Đọc và giải thích cú pháp git rebase --onto.
- Xác định tập commit sẽ được chọn từ một nhánh.
- Chuyển nhánh tính năng từ nền cũ sang nền mới.
- Tách các commit riêng khỏi một nhánh phụ thuộc.
- Kiểm tra lịch sử trước và sau khi rebase.
- Xử lý conflict, khôi phục thao tác và phối hợp khi nhánh đã được chia sẻ.

## 1. Cú pháp và ý nghĩa của từng tham số

Cú pháp tổng quát:

~~~bash
git rebase --onto NEWBASE UPSTREAM [BRANCH]
~~~

| Tham số | Ý nghĩa |
| --- | --- |
| NEWBASE | Commit hoặc nhánh đích mà các commit được chọn sẽ được phát lại lên trên. |
| UPSTREAM | Mốc giới hạn để xác định commit nào thuộc phần cần phát lại. Các commit có thể đi tới từ upstream sẽ bị loại khỏi tập được chọn. |
| BRANCH | Nhánh cần rebase. Nếu bỏ qua, Git dùng nhánh hiện tại. |

Có thể hình dung thao tác như sau:

1. Xác định các commit có thể đi tới từ BRANCH.
2. Loại các commit đã có thể đi tới từ UPSTREAM.
3. Phát lại các commit còn lại theo thứ tự phù hợp, bắt đầu từ NEWBASE.
4. Cập nhật nhánh đích tới commit mới sau khi quá trình hoàn tất.

Với lịch sử tuyến tính đơn giản, tập commit được chọn tương ứng với khoảng UPSTREAM..BRANCH.

Điều này không có nghĩa UPSTREAM và NEWBASE phải là cùng một nhánh. Trái lại, khả năng chọn mốc giới hạn riêng và điểm đích riêng là lý do --onto hữu ích.

Nếu chỉ định BRANCH, Git chuyển sang nhánh đó trước khi rebase. Nếu không chỉ định, lệnh tác động lên nhánh đang checkout:

~~~bash
# Rebase nhánh feature/ui lên main, dùng feature/auth làm mốc giới hạn
git rebase --onto main feature/auth feature/ui

# Tương đương về mục tiêu nếu đã checkout feature/ui
git switch feature/ui
git rebase --onto main feature/auth
~~~

Tên UPSTREAM trong cú pháp này là tham số giới hạn của thao tác, không nhất thiết là upstream tracking được cấu hình bằng git branch --set-upstream-to.

## 2. Vì sao cần tách mốc giới hạn và điểm đích

Giả sử nhóm có nhánh feature/auth xây dựng chức năng xác thực. Trong lúc chờ nhánh đó hoàn thành, bạn tạo feature/ui dựa trên nó để phát triển giao diện. Sau đó, nhóm quyết định phần giao diện cần chuyển sang main độc lập, không mang toàn bộ commit xác thực vào.

Lịch sử minh họa:

~~~text
A---B---C---D             main
     \
      F1---F2---F3        feature/auth
                     \
                      U1---U2  feature/ui
~~~

Trong ví dụ này:

- feature/auth có các commit F1, F2, F3.
- feature/ui được tạo từ tip feature/auth sau F3 và có các commit U1, U2.
- main đã tiến tới D.
- Bạn muốn giữ U1 và U2, bỏ phần phụ thuộc vào các commit F1, F2, F3 và đặt phần giao diện lên đầu main.

Chạy:

~~~bash
git rebase --onto main feature/auth feature/ui
~~~

Git chọn các commit có trong feature/ui nhưng không có trong feature/auth, tức U1 và U2 trong lịch sử đơn giản này. Sau đó, Git phát lại chúng trên main:

~~~text
A---B---C---D---U1'---U2'  feature/ui
            ^
            main
     \
      F1---F2---F3         feature/auth
~~~

Các commit U1' và U2' là commit mới. Nhánh feature/auth vẫn giữ lịch sử cũ. Nhánh feature/ui sau thao tác trỏ tới lịch sử mới trên main.

Đây là một cách tách nhánh con khỏi nhánh phụ thuộc. Tuy nhiên, hãy xác nhận mã giao diện không còn cần các API hoặc thay đổi chỉ tồn tại trong feature/auth. Rebase có thể áp dụng patch thành công nhưng ứng dụng vẫn lỗi vì dependency đã bị loại khỏi nền mới.

## 3. Chuẩn bị trước khi chạy rebase --onto

Rebase viết lại commit, vì vậy cần hiểu rõ trạng thái repository và tập commit sắp được chuyển. Trước hết, kiểm tra working tree:

~~~bash
git status --short --branch
~~~

Nếu còn thay đổi chưa commit, hãy quyết định lưu chúng bằng commit hoặc stash theo quy trình phù hợp. Không bắt đầu rebase khi bạn chưa biết các chỉnh sửa đang nằm ở working tree hay staging area.

Tiếp theo, cập nhật thông tin remote nếu điểm đích là nhánh trên remote:

~~~bash
git fetch origin
~~~

Tạo nhánh dự phòng để giữ lại vị trí cũ:

~~~bash
git branch backup/feature-ui-before-onto feature/ui
~~~

Nhánh dự phòng chỉ tạo thêm một tham chiếu tới commit hiện tại; nó không sao chép toàn bộ repository. Nếu cần quay lại hoặc so sánh lịch sử cũ, bạn vẫn có thể truy cập commit thông qua nhánh này.

Kiểm tra đồ thị và tập commit dự kiến:

~~~bash
git log --oneline --graph --decorate --all
git log --oneline --reverse feature/auth..feature/ui
git merge-base feature/auth feature/ui
~~~

Lệnh git log --reverse feature/auth..feature/ui hiển thị các commit được chọn theo thứ tự cũ đến mới trong ví dụ tuyến tính. Hãy đọc từng commit và xác nhận chúng đều thuộc phần việc muốn chuyển.

Nếu muốn xác nhận feature/auth là tổ tiên của feature/ui, có thể kiểm tra:

~~~bash
git merge-base --is-ancestor feature/auth feature/ui
~~~

Lệnh trả mã thoát 0 khi feature/auth là tổ tiên của feature/ui; mã khác 0 có nghĩa quan hệ tổ tiên không đúng hoặc không thể xác nhận. Điều này hữu ích khi bạn kỳ vọng một nhánh được tạo từ nhánh kia. Nếu lịch sử đã có merge hoặc nhiều nhánh tổ tiên, hãy xem đồ thị thay vì chỉ dựa vào một giả định tuyến tính.

## 4. Ví dụ đầy đủ: chuyển nhánh con sang main

Giả sử feature/ui được phát triển dựa trên feature/auth, nhưng hiện tại cần chuyển các commit riêng của giao diện lên origin/main.

~~~bash
# 1. Kiểm tra trạng thái và nhánh
git status --short --branch
git branch -vv

# 2. Cập nhật tham chiếu remote
git fetch origin

# 3. Giữ một tham chiếu tới lịch sử cũ
git branch backup/feature-ui-before-onto feature/ui

# 4. Xem các commit sẽ được chuyển
git log --oneline --reverse feature/auth..feature/ui

# 5. Chuyển phần commit riêng của feature/ui lên origin/main
git rebase --onto origin/main feature/auth feature/ui

# 6. Xem lịch sử sau khi chuyển
git log --oneline --graph --decorate --all -n 25
~~~

Trong lệnh ở bước 5:

- origin/main là điểm đích mới.
- feature/auth là mốc giới hạn; commit đã có trong nhánh này không được phát lại.
- feature/ui là nhánh được thay đổi.

Nếu không có conflict và các patch áp dụng sạch, Git hoàn tất rebase và di chuyển feature/ui tới commit mới. Nếu có conflict, xử lý theo quy trình ở phần sau.

## 5. Dùng --onto để loại một phần lịch sử phụ thuộc

Một trường hợp khác là nhánh B được tạo từ nhánh A, nhưng bạn chỉ muốn giữ những commit B tự bổ sung. Khi đó, nhánh A có thể đóng vai trò mốc giới hạn:

~~~bash
git rebase --onto main feature/A feature/B
~~~

Lệnh lấy các commit thuộc feature/B mà không thuộc lịch sử feature/A, rồi phát lại lên main. Đây là cách loại phần commit được kế thừa từ nhánh A khỏi lịch sử mới của B.

Không nên nhầm thao tác này với việc xóa commit khỏi mọi nhánh. Các commit bị loại khỏi lịch sử mới của feature/B vẫn có thể được giữ bởi feature/A, nhánh dự phòng, tag hoặc tham chiếu khác. Rebase di chuyển nhánh được chọn; nó không tự xóa mọi đối tượng cũ khỏi repository.

Trước khi loại dependency, hãy kiểm tra:

- Các commit riêng của nhánh B có thực sự độc lập với thay đổi trong A không?
- Code có tham chiếu class, hàm, schema hoặc cấu hình chỉ tồn tại trong A không?
- Test và build có chạy được trên nền main mới không?
- Có commit nào của B đã được người khác sử dụng hoặc chia sẻ không?

Nếu các commit B cần thay đổi trong A, việc loại A có thể khiến mã nguồn không biên dịch hoặc hành vi không đúng. Khi đó, cần tách dependency thành phần dùng chung, giữ lại commit cần thiết hoặc chọn một nền khác có chứa dependency.

## 6. Dùng --onto để thay đổi nền của một nhánh

Mẫu tổng quát thường dùng:

~~~bash
git rebase --onto NEW-BASE OLD-BASE TOPIC-BRANCH
~~~

Ví dụ nhánh feature/export ban đầu được tạo từ release/1.x, nhưng nhóm quyết định chuyển phần phát triển mới sang main:

~~~bash
git fetch origin
git branch backup/export-before-move feature/export
git log --oneline --reverse release/1.x..feature/export
git rebase --onto origin/main release/1.x feature/export
~~~

Git chọn commit của feature/export không có trong lịch sử release/1.x rồi phát lại trên origin/main. Đây là thao tác đổi nền (transplant) một tập commit.

Lệnh chỉ đúng khi release/1.x là mốc giới hạn phù hợp với lịch sử mà bạn muốn giữ lại. Nếu nhánh export chứa commit từ nhiều nguồn hoặc merge phức tạp, tập commit được chọn có thể rộng hơn dự kiến. Hãy kiểm tra git log, git merge-base và đồ thị trước khi chạy.

## 7. Phân biệt rebase --onto với rebase thông thường

Rebase thông thường:

~~~bash
git rebase origin/main
~~~

Khi đang ở nhánh feature/export, lệnh trên dùng upstream làm cả mốc xác định commit cần phát lại và nền mới. Git lấy commit riêng của nhánh hiện tại so với origin/main, rồi phát lại chúng trên origin/main.

Rebase với --onto:

~~~bash
git rebase --onto origin/main release/1.x feature/export
~~~

Ở đây, mốc giới hạn là release/1.x, còn nền mới là origin/main. Hai tham số này có thể khác nhau. Khả năng tách chúng ra cho phép chuyển một phần lịch sử được chọn sang một nền mới mà rebase thông thường không diễn đạt trực tiếp.

| Câu hỏi | Rebase thông thường | Rebase --onto |
| --- | --- | --- |
| Commit nào được phát lại? | Commit riêng của nhánh so với upstream. | Commit riêng của branch so với mốc upstream được chỉ định. |
| Phát lại lên đâu? | Chính upstream đó. | Newbase riêng, có thể khác upstream. |
| Trường hợp tiêu biểu | Cập nhật nhánh tính năng lên main mới. | Chuyển nhánh con khỏi nhánh phụ thuộc hoặc đổi nền giữa hai nhánh khác nhau. |

## 8. Rebase có merge commit và tùy chọn --rebase-merges

Mặc định, rebase thường phát lại lịch sử theo dạng tuyến tính và có thể không giữ cấu trúc merge commit ban đầu. Nếu nhánh có các merge commit quan trọng, hãy xem xét tùy chọn:

~~~bash
git rebase --rebase-merges --onto main feature/auth feature/ui
~~~

--rebase-merges yêu cầu Git cố gắng tái tạo cấu trúc merge trong lịch sử được phát lại. Các merge commit được tạo lại có mã định danh mới và quá trình này vẫn có thể phát sinh conflict. Không nên bật tùy chọn chỉ vì đồ thị có nhiều nhánh; trước hết hãy xác định merge commit có mang ý nghĩa tích hợp cần giữ hay không.

Kiểm tra đồ thị trước và sau:

~~~bash
git log --graph --oneline --decorate --all
~~~

Nếu cấu trúc lịch sử phức tạp, hãy thực hiện trên nhánh dự phòng hoặc trong một bản sao làm việc phù hợp trước khi áp dụng lên nhánh đang được nhiều người sử dụng.

## 9. Xử lý conflict trong quá trình rebase

Khi một commit được phát lại nhưng không thể áp dụng tự động, Git dừng và thông báo tệp xung đột. Kiểm tra trạng thái:

~~~bash
git status
git diff
~~~

Mở các tệp được báo conflict, đọc vùng xung đột và tạo nội dung cuối cùng phù hợp với mục tiêu của thay đổi. Sau khi sửa từng tệp:

~~~bash
git add path/to/file
git rebase --continue
~~~

Git tiếp tục phát lại các commit còn lại. Có thể cần lặp lại quá trình sửa, stage và continue nhiều lần.

Nếu commit hiện tại không còn cần thiết hoặc patch của nó đã được đưa vào nền mới theo cách tương đương, có thể bỏ qua commit đó:

~~~bash
git rebase --skip
~~~

Chỉ dùng --skip sau khi xác nhận phần thay đổi của commit không còn cần thiết. Lệnh này bỏ commit đang được phát lại khỏi lịch sử mới.

Nếu muốn hủy toàn bộ quá trình và quay về trạng thái trước khi bắt đầu rebase:

~~~bash
git rebase --abort
~~~

Abort là lựa chọn khi bạn nhận ra mốc giới hạn hoặc điểm đích đã chọn sai, conflict quá phức tạp, hoặc muốn chuẩn bị lại trước khi thử lần nữa. Nhánh dự phòng vẫn hữu ích để đối chiếu nếu cần.

## 10. Kiểm tra chất lượng sau khi chuyển lịch sử

Rebase thành công chỉ chứng minh Git đã tạo được lịch sử mới; nó không chứng minh chức năng vẫn đúng. Hãy kiểm tra cả đồ thị commit, nội dung thay đổi và hành vi của dự án.

~~~bash
# Xem lịch sử mới
git log --oneline --graph --decorate --all -n 30

# So sánh chuỗi commit cũ và mới
git range-diff feature/auth..backup/feature-ui-before-onto origin/main..feature/ui

# Xem thay đổi của nhánh so với nền mới
git diff origin/main...feature/ui

# Kiểm tra trạng thái repository
git status --short --branch
~~~

git range-diff giúp đối chiếu các chuỗi commit trước và sau khi viết lại, hữu ích để phát hiện commit bị thiếu, thay đổi patch ngoài dự kiến hoặc commit được sắp xếp lại. Các range phải đại diện đúng cho chuỗi commit cũ và mới của ví dụ đang làm.

Sau đó chạy các kiểm tra của dự án, chẳng hạn unit test, integration test, build hoặc kiểm tra tài liệu. Với một nhánh được tách khỏi dependency, hãy đặc biệt kiểm tra các thành phần mà trước đây nhánh phụ thuộc cung cấp.

Khi đã xác nhận nhánh mới đúng, bạn có thể giữ nhánh dự phòng thêm một thời gian theo chính sách nhóm. Chỉ xóa nó khi không còn cần đối chiếu hoặc khôi phục.

## 11. Chia sẻ nhánh đã rebase

Rebase tạo commit mới nên mã định danh của các commit được phát lại thay đổi. Nếu nhánh chưa từng push hoặc chưa được người khác dùng, push thông thường thường đủ:

~~~bash
git push -u origin feature/ui
~~~

Nếu nhánh đã được push trước khi rebase, remote vẫn giữ các commit cũ. Push thông thường có thể bị từ chối do non-fast-forward. Với nhánh cá nhân mà nhóm cho phép viết lại lịch sử, có thể cập nhật bằng:

~~~bash
git push --force-with-lease origin feature/ui
~~~

--force-with-lease kiểm tra vị trí remote có còn như kỳ vọng trước khi cập nhật cưỡng bức. Nếu đồng đội đã push thêm commit sau lần bạn fetch, Git có thể từ chối để tránh ghi đè thay đổi mới. Hãy fetch, kiểm tra và phối hợp trước khi thử lại.

Không force push nhánh dùng chung hoặc nhánh mà người khác đang dựa vào nếu chưa có thỏa thuận rõ ràng. Với main, release và nhánh tích hợp, hãy tuân thủ quy tắc bảo vệ nhánh của repository.

## 12. Một checklist thực hành

~~~bash
# Xác nhận trạng thái ban đầu
git status --short --branch

# Cập nhật remote nếu điểm đích nằm trên remote
git fetch origin

# Giữ lại vị trí nhánh trước khi viết lại
git branch backup/topic-before-onto topic

# Xem tập commit sẽ chuyển
git log --oneline --reverse old-base..topic

# Chuyển các commit riêng từ topic sang new-base
git rebase --onto new-base old-base topic

# Nếu có conflict: sửa tệp, stage, tiếp tục
git status
git add path/to/resolved-file
git rebase --continue

# Xem lịch sử và so sánh chuỗi commit
git log --oneline --graph --decorate --all
git range-diff old-base..backup/topic new-base..topic

# Chạy kiểm tra dự án rồi chia sẻ theo chính sách nhóm
git status --short --branch
git push
~~~

Thay old-base, new-base, topic và đường dẫn tệp bằng tên thực tế. Nếu nhánh đã được chia sẻ và việc rebase được nhóm cho phép, thống nhất trước cách cập nhật remote; nếu không, cân nhắc merge hoặc tạo nhánh mới thay vì viết lại lịch sử chung.

## 13. Những lỗi dễ mắc khi dùng --onto

### Đảo nhầm newbase và upstream

Hai tham số có vai trò khác nhau. Newbase là nơi commit mới sẽ được phát lại; upstream là mốc giới hạn để xác định commit cần chọn. Nếu đảo chúng, Git có thể tạo lịch sử khác hẳn mục tiêu. Hãy đọc lại lệnh theo câu hỏi: “Tôi muốn giữ commit nào, và đặt chúng lên đâu?”

### Chọn mốc upstream quá cũ hoặc quá mới

Nếu mốc giới hạn quá cũ, tập commit được chọn có thể chứa cả thay đổi không thuộc nhánh cần chuyển. Nếu mốc quá mới, một số commit mong muốn có thể bị loại vì đã nằm trong lịch sử của upstream. Kiểm tra danh sách bằng git log --reverse upstream..branch trước khi rebase.

### Cho rằng rebase chỉ thay đổi vị trí con trỏ

Rebase phát lại commit và tạo mã commit mới. Các chữ ký commit, thông tin thời gian và quan hệ cha có thể thay đổi. Nếu nhánh đã chia sẻ, điều này ảnh hưởng tới người khác.

### Bỏ qua dependency của commit

Một commit có thể dựa vào class, API, cấu hình hoặc schema từ nhánh bị loại khỏi lịch sử mới. Rebase có thể thành công nhưng build/test thất bại. Hãy kiểm tra dependency và chạy test sau khi chuyển.

### Dùng --skip để làm cho rebase chạy tiếp

Skip bỏ commit hiện tại khỏi lịch sử mới. Nếu chưa hiểu patch của commit, bạn có thể vô tình bỏ chức năng cần thiết. Chỉ skip khi đã xác nhận thay đổi dư thừa hoặc không còn cần.

## 14. Ghi nhớ

- git rebase --onto NEWBASE UPSTREAM BRANCH tách điểm đích khỏi mốc chọn commit.
- Tập commit được chọn là các commit reachable từ branch nhưng không reachable từ upstream.
- Với lịch sử tuyến tính, có thể xem trước tập đó bằng git log --reverse upstream..branch.
- Dùng --onto để đổi nền hoặc tách nhánh con khỏi một nhánh phụ thuộc.
- Tạo nhánh dự phòng và kiểm tra working tree trước khi viết lại lịch sử.
- Giải quyết conflict bằng sửa tệp, git add và git rebase --continue; dùng --abort để hủy hoặc --skip để bỏ commit hiện tại khi có chủ đích.
- Dùng git range-diff, log, diff và test để xác minh lịch sử mới.
- Phối hợp trước khi cập nhật cưỡng bức một nhánh đã chia sẻ; ưu tiên --force-with-lease khi chính sách cho phép.

git rebase --onto là công cụ để chuyển đúng một phần lịch sử tới nền mới. Khi xác định chính xác mốc giới hạn, điểm đích và các commit cần giữ, bạn có thể tổ chức lại quan hệ phụ thuộc giữa các nhánh mà vẫn kiểm soát được nội dung và lịch sử của công việc.
