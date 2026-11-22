# Phục hồi rebase sai và phối hợp khi cần cập nhật nhánh đã chia sẻ

Rebase giúp sắp xếp lại lịch sử commit bằng cách phát lại các commit trên một nền khác. Vì thao tác này tạo commit mới với hash mới, rebase có thể làm thay đổi lịch sử của nhánh. Nếu chọn sai nhánh nền, sai phạm vi commit hoặc xử lý conflict không đúng, cần biết cách quay lại trạng thái trước đó. Khi nhánh đã được push và có người khác sử dụng, việc phục hồi còn cần phối hợp để không làm mất commit của đồng đội.

Bài học này trình bày hai tình huống khác nhau: **rebase đang chạy và cần hủy**, hoặc **rebase đã hoàn tất nhưng kết quả sai**. Sau đó, bài học hướng dẫn cách xử lý khi lịch sử đã được chia sẻ trên remote, cách dùng reflog và nhánh cứu hộ, cũng như cách đồng bộ lại máy của các thành viên sau khi nhánh được viết lại.

## 1. Vì sao có thể phục hồi rebase?

Rebase không sửa nội dung commit cũ tại chỗ. Git tạo các commit mới dựa trên nội dung thay đổi của từng commit và lần lượt áp dụng chúng lên commit nền mới. Do đó, hash của các commit được phát lại thường thay đổi.

Ví dụ, ban đầu nhánh tính năng có lịch sử:

~~~text
A---B---C  main
     \
      D---E  feature/report
~~~

Bạn muốn đặt nhánh tính năng lên trên commit mới của `main`, nhưng vô tình rebase lên nhầm nhánh hoặc nhầm commit. Sau rebase, lịch sử có thể thành:

~~~text
A---B---C---D'---E'  feature/report
~~~

Các commit `D'` và `E'` có nội dung tương tự `D` và `E`, nhưng là commit mới. Nếu kết quả không đúng, cần xác định commit mà nhánh trỏ tới trước khi rebase và quyết định có nên đưa nhánh về commit đó hay không.

Git lưu lịch sử di chuyển của các tham chiếu cục bộ trong **reflog**. Đây thường là nơi tốt nhất để tìm lại vị trí cũ của nhánh. Ngoài ra, Git có thể ghi vị trí trước thao tác vào `ORIG_HEAD`, nhưng giá trị này có thể bị lệnh khác ghi đè.

## 2. Trước khi phục hồi: xác định trạng thái hiện tại

Đừng vội chạy `reset --hard` hoặc force push. Trước tiên, kiểm tra repository và xác định rebase đang ở trạng thái nào:

~~~bash
git status
git branch --show-current
git log --oneline --decorate --graph -12
~~~

Các câu hỏi cần trả lời:

- Có thông báo cho biết rebase đang diễn ra không?
- Bạn đang đứng trên đúng nhánh cần phục hồi không?
- Rebase đã hoàn tất hay đang dừng ở conflict?
- Những commit nào đã được tạo lại?
- Nhánh đã được push lên remote chưa?
- Có ai khác đã fetch, checkout hoặc tạo commit dựa trên lịch sử mới không?
- Working tree có thay đổi chưa commit hoặc file chưa được theo dõi cần giữ không?

Nếu rebase còn đang diễn ra, cách xử lý khác với trường hợp rebase đã hoàn tất. Nếu nhánh đã được chia sẻ, cần xem xét tác động lên đồng đội trước khi viết lại remote.

## 3. Hủy rebase khi thao tác vẫn đang diễn ra

Khi rebase gặp conflict, Git tạm dừng và chờ bạn giải quyết từng commit. Nếu nhận ra đã chọn sai nhánh nền, sai phạm vi hoặc không muốn tiếp tục, có thể hủy tiến trình:

~~~bash
git rebase --abort
~~~

Lệnh này kết thúc rebase đang chạy và đưa nhánh về trạng thái trước khi bắt đầu rebase. Sau đó kiểm tra:

~~~bash
git status
git log --oneline --decorate --graph -12
~~~

Nếu mục tiêu là hủy hoàn toàn thao tác rebase, `--abort` là lựa chọn thông thường.

### Phân biệt continue, skip, abort và quit

| Lệnh | Tác dụng |
|---|---|
| `git rebase --continue` | Tiếp tục phát lại commit sau khi đã giải quyết conflict và stage file |
| `git rebase --skip` | Bỏ qua commit đang được phát lại; chỉ dùng khi chủ động không cần thay đổi của commit đó |
| `git rebase --abort` | Hủy rebase và đưa nhánh về trạng thái trước khi bắt đầu |
| `git rebase --quit` | Xóa trạng thái điều khiển rebase nhưng giữ nguyên HEAD, index và working tree hiện tại |

`--quit` không giống `--abort`. Lệnh quit không khôi phục nhánh về điểm ban đầu; nó chỉ dừng cơ chế theo dõi tiến trình rebase và để nguyên trạng thái hiện tại. Vì vậy, khi phát hiện rebase sai và muốn quay lại điểm xuất phát, thường không nên chọn `--quit`.

Nếu đang xử lý conflict và có chỉnh sửa thủ công cần giữ, hãy sao lưu trước khi hủy. Sau `--abort`, xác minh lại working tree và các thay đổi trước đó.

## 4. Tìm commit trước rebase bằng reflog

Nếu rebase đã hoàn tất, `git rebase --abort` không còn áp dụng. Lúc này, cần tìm lại vị trí trước rebase trong reflog.

Xem lịch sử di chuyển của HEAD:

~~~bash
git reflog --date=iso
~~~

Hoặc xem riêng lịch sử của nhánh:

~~~bash
git reflog show feature/report --date=iso
~~~

Kết quả minh họa:

~~~text
8ab31c2 HEAD@{2026-11-17 10:42:10 +0700}: rebase (finish): returning to refs/heads/feature/report
8ab31c2 HEAD@{2026-11-17 10:42:10 +0700}: rebase (pick): Add report export
51d92ef HEAD@{2026-11-17 10:41:52 +0700}: rebase (pick): Add report filters
c7a10bd HEAD@{2026-11-17 10:40:03 +0700}: rebase (start): checkout main
d4f6e20 HEAD@{2026-11-17 10:35:22 +0700}: commit: Add report export
a6b8c91 HEAD@{2026-11-17 10:20:14 +0700}: commit: Add report filters
~~~

Trong ví dụ, `d4f6e20` là vị trí nhánh trước khi rebase bắt đầu. Các dòng reflog và hash thực tế trên máy bạn sẽ khác.

Để xem một commit có đúng là điểm cần phục hồi hay không:

~~~bash
git show --stat d4f6e20
git show --oneline --no-patch d4f6e20
~~~

Hãy kiểm tra cả commit cha, nội dung và thời điểm. Không chọn commit chỉ vì nó nằm ngay trước một dòng có chữ `rebase`; hãy xác nhận đó là tip của nhánh trước thao tác.

### ORIG_HEAD có thể giúp gì?

Một số thao tác như merge, reset và rebase ghi lại vị trí trước đó trong `ORIG_HEAD`. Có thể kiểm tra:

~~~bash
git show --oneline --no-patch ORIG_HEAD
~~~

Nếu commit đó đúng với tip trước rebase, nó có thể giúp phục hồi nhanh. Tuy nhiên, `ORIG_HEAD` có thể bị lệnh khác ghi đè. Reflog thường cung cấp nhiều mốc hơn, nên hãy đối chiếu thay vì phụ thuộc duy nhất vào `ORIG_HEAD`.

### Reflog có giới hạn gì?

Reflog ghi nhận thay đổi của các tham chiếu trong repository local. Nó không phải lịch sử được đồng bộ tự động lên remote và không đảm bảo tồn tại mãi mãi. Các entry có thể hết hạn theo cấu hình và các commit không còn được tham chiếu có thể bị garbage collection dọn sau đó.

Vì vậy, hãy phục hồi càng sớm càng tốt khi phát hiện lỗi. Reflog trên máy của một thành viên cũng có thể là nguồn tìm lại commit nếu máy khác đã mất tham chiếu đó, miễn là commit vẫn còn trong repository của họ.

## 5. Tạo nhánh cứu hộ trước khi reset

Trước khi di chuyển nhánh, hãy tạo một nhánh mới để giữ lại trạng thái hiện tại. Nhánh cứu hộ là một tham chiếu tới commit, giúp bạn có thể quay lại trạng thái vừa kiểm tra nếu chọn nhầm điểm phục hồi.

Giả sử bạn cần phục hồi nhánh `feature/report`:

~~~bash
git switch feature/report
git branch rescue/feature-report-after-rebase HEAD
~~~

Tên `rescue/feature-report-after-rebase` chỉ là ví dụ; hãy chọn tên chưa tồn tại và dễ nhận diện.

Nếu working tree có thay đổi chưa commit hoặc file chưa được theo dõi, lưu chúng trước:

~~~bash
git status
git stash push -u -m "before recovering feature/report rebase"
~~~

Tùy chọn `-u` đưa cả file chưa được theo dõi vào stash. Nó không bao gồm file bị ignore; nếu cần giữ cả file ignore, cần cân nhắc `-a` và kiểm tra nội dung trước. Không dùng stash như bản sao lưu duy nhất cho dữ liệu quan trọng.

Sau khi đã có nhánh cứu hộ và lưu các thay đổi cần thiết, xác nhận lại commit phục hồi bằng reflog và `git show`.

## 6. Đưa nhánh local về trạng thái trước rebase

Khi đã xác định chắc chắn commit cũ, có thể đưa nhánh local về đó:

~~~bash
git switch feature/report
git reset --hard d4f6e20
~~~

Lệnh `reset --hard` cập nhật HEAD, index và working tree theo commit được chỉ định. Nó có thể loại bỏ thay đổi chưa commit trong working tree. Chỉ thực hiện sau khi đã kiểm tra và lưu mọi nội dung cần giữ.

Xác minh:

~~~bash
git status
git log --oneline --decorate --graph -12
~~~

Nếu đã tạo stash, xem danh sách và áp dụng lại khi phù hợp:

~~~bash
git stash list
git stash apply stash@{0}
~~~

Dùng `apply` để giữ stash lại trong danh sách cho tới khi xác minh nội dung được phục hồi. Khi đã chắc chắn các thay đổi được áp dụng đầy đủ, mới cân nhắc xóa stash bằng `git stash drop`.

Nhánh cứu hộ vẫn giữ commit sau rebase. Nếu phát hiện đã chọn nhầm commit cũ, bạn có thể chuyển lại nhánh cứu hộ hoặc tạo một nhánh khác từ commit đó để tiếp tục kiểm tra.

## 7. Nếu không tìm thấy commit trong reflog

Trước hết, xem cả reflog của HEAD và các nhánh:

~~~bash
git reflog --all --date=iso
~~~

Kiểm tra `ORIG_HEAD` và các nhánh cứu hộ hoặc nhánh tạm đã tạo trước đó. Hỏi đồng đội xem repository local của họ có còn commit cũ không; mỗi bản clone có reflog riêng.

Trong trường hợp không còn tham chiếu rõ ràng, `git fsck` có thể tìm các đối tượng commit không còn được tham chiếu:

~~~bash
git fsck --no-reflogs --unreachable
~~~

Nếu tìm thấy một commit đáng chú ý, xem nội dung bằng:

~~~bash
git show --stat <commit-id>
~~~

Chỉ sau khi xác nhận đúng commit mới tạo nhánh cứu hộ:

~~~bash
git branch rescue/recovered-report <commit-id>
~~~

Đây là phương án cuối cùng, không phải bảo đảm phục hồi. Nếu commit đã bị garbage collection loại bỏ và không còn trong bản clone hay bản sao lưu nào, Git có thể không còn dữ liệu để khôi phục.

## 8. Phân biệt nhánh local và nhánh đã chia sẻ

Một nhánh chỉ tồn tại trong repository local thường có thể được sửa lịch sử linh hoạt hơn, miễn là bạn đã bảo toàn công việc cần thiết. Khi nhánh được push lên remote và người khác dựa vào nó, nhánh đó đã trở thành một phần của quy trình cộng tác.

Hãy phân biệt ba tình huống:

| Tình huống | Cách xử lý thường phù hợp |
|---|---|
| Rebase sai, chưa push | Dùng reflog tìm tip cũ, tạo nhánh cứu hộ và phục hồi local |
| Đã push nhánh riêng, chưa ai dựa vào lịch sử mới | Thông báo nếu có người theo dõi, kiểm tra remote rồi cập nhật bằng lease khi thật sự cần |
| Nhánh đã được nhiều người dùng hoặc commit đã được tích hợp | Ưu tiên giữ lịch sử và tạo commit sửa bằng revert; chỉ viết lại lịch sử khi có kế hoạch phối hợp rõ ràng |

Force push lên nhánh đã chia sẻ có thể làm các máy khác giữ lịch sử cũ trong khi remote đã chuyển sang lịch sử mới. Nếu đồng đội tiếp tục push dựa trên tip cũ, họ có thể gặp non-fast-forward, tạo merge commit ngoài ý muốn hoặc làm xuất hiện lại các commit đã bị thay thế.

Không phải mọi rebase sai đều cần force push. Nếu thay đổi đã được công bố và có người khác sử dụng, giữ lịch sử và tạo commit sửa thường ít gây gián đoạn hơn.

## 9. Lập kế hoạch trước khi viết lại nhánh chia sẻ

Nếu nhóm quyết định phải thay thế lịch sử của một nhánh đã push, maintainer và những người đang làm trên nhánh đó cần thống nhất trước.

Một kế hoạch phối hợp nên xác định:

1. **Phạm vi**: nhánh remote nào sẽ được viết lại và vì sao.
2. **Người thực hiện**: một người chịu trách nhiệm cập nhật remote để tránh hai lần force push cạnh tranh.
3. **Thời điểm**: khoảng thời gian các thành viên tạm dừng push lên nhánh đó.
4. **Điểm khôi phục**: lưu hash tip cũ và tạo nhánh cứu hộ nếu cần.
5. **Tip mới**: xác định commit sẽ trở thành đầu nhánh sau rebase.
6. **Cách đồng bộ lại**: hướng dẫn các thành viên fetch, so sánh và chuyển công việc riêng lên lịch sử mới.

Trước khi thay đổi, lấy trạng thái remote mới nhất:

~~~bash
git fetch origin
git rev-parse origin/feature/report
~~~

Ghi lại hash được trả về. Đây là tip remote mà bạn đã kiểm tra và đồng ý thay thế. Cũng có thể xem lịch sử:

~~~bash
git log --oneline --graph --decorate origin/feature/report -12
~~~

Không bắt đầu viết lại nếu remote đã có commit mới mà bạn chưa xem xét. Nếu phát hiện đồng đội vừa push, dừng lại để xác định cách giữ commit đó.

## 10. Cập nhật nhánh remote bằng force-with-lease

Push thông thường chỉ chấp nhận cập nhật fast-forward. Rebase tạo commit mới, nên khi muốn thay thế lịch sử cũ trên remote, có thể cần cập nhật cưỡng bức.

Ưu tiên `--force-with-lease` thay cho `--force`:

~~~bash
git push --force-with-lease origin feature/report
~~~

Git kiểm tra rằng ref remote vẫn ở giá trị mà repository local kỳ vọng, thường dựa trên remote-tracking branch. Nếu remote đã thay đổi kể từ lần fetch hoặc kể từ khi giá trị theo dõi được cập nhật, push có thể bị từ chối. Đây là cơ chế bảo vệ khỏi việc vô tình ghi đè commit mới của người khác.

Để kiểm soát rõ hơn, có thể ghi cụ thể hash remote đã kiểm tra:

~~~bash
git push --force-with-lease=refs/heads/feature/report:<expected-remote-sha> origin feature/report:refs/heads/feature/report
~~~

Thay `<expected-remote-sha>` bằng hash đã ghi lại trước khi viết lại lịch sử. Lệnh chỉ cập nhật nếu ref remote vẫn khớp giá trị kỳ vọng đó.

Không nên coi lease là thay thế cho phối hợp. Nó chỉ kiểm tra điều kiện của ref tại thời điểm cập nhật; nó không thông báo cho đồng đội, không xác nhận họ đã sao lưu và không đánh giá công việc local của họ.

Nếu push bị từ chối, đừng đổi ngay sang `--force`. Hãy fetch, xem commit mới trên remote, xác định ai đã cập nhật và tích hợp công việc đó trước khi thử lại.

## 11. Khi nào nên dùng revert thay vì force push?

Nếu commit đã được tích hợp vào nhánh chính, đã phát hành hoặc được nhiều nhánh khác sử dụng, viết lại lịch sử có thể làm phức tạp việc đồng bộ. Trong trường hợp này, `git revert` thường phù hợp hơn.

Ví dụ, tạo commit đảo ngược một commit đã công bố:

~~~bash
git switch main
git pull --ff-only
git revert <commit-id>
git push origin main
~~~

`git revert` tạo commit mới để đảo ngược thay đổi của commit được chỉ định. Lịch sử cũ vẫn còn, nên những người đã fetch hoặc xây dựng công việc dựa trên commit đó không phải xử lý một nhánh bị thay thế.

Nếu cần đảo ngược một merge commit, phải xác định parent chính và dùng tùy chọn `-m` đúng. Hãy kiểm tra hướng dẫn riêng về revert merge trước khi thực hiện.

Revert không làm biến mất commit sai khỏi lịch sử, nhưng ghi nhận rõ hành động sửa sai. Đó thường là điều mong muốn ở nhánh công khai hoặc nhánh phát hành.

## 12. Đồng bộ lại máy của đồng đội sau khi nhánh bị viết lại

Sau khi maintainer đã cập nhật remote thành công, các máy đã fetch lịch sử cũ cần đồng bộ lại có chủ đích. Không nên chạy `git pull` một cách máy móc: nếu local còn nhánh cũ, pull có thể cố gắng hợp nhất hai dòng lịch sử vốn đã được viết lại và tạo commit ngoài ý muốn.

Trước tiên, fetch và xem sự khác nhau:

~~~bash
git fetch origin
git log --oneline --left-right --graph feature/report...origin/feature/report
~~~

Dấu `<` và `>` trong kết quả giúp phân biệt commit chỉ có ở phía local và phía remote. Xác định xem local có commit riêng chưa được gửi hay không.

### Trường hợp local không có công việc riêng cần giữ

Nếu working tree sạch và nhánh local chỉ giữ lịch sử cũ đã bị thay thế, tạo bản sao rồi cập nhật local theo remote:

~~~bash
git switch feature/report
git branch rescue/feature-report-before-sync HEAD
git reset --hard origin/feature/report
~~~

Chỉ dùng `reset --hard` sau khi xác nhận không có thay đổi chưa commit hoặc đã lưu chúng. Nhánh cứu hộ giữ lại lịch sử cũ để có thể kiểm tra hoặc lấy lại commit.

### Trường hợp local có commit riêng chưa push

Không reset bỏ các commit đó. Trước tiên, tạo nhánh cứu hộ và xác định commit chung cuối cùng của lịch sử cũ, tức tip nhánh chia sẻ trước khi bị viết lại. Sau đó, nếu đã xác định chính xác ranh giới, có thể phát lại các commit riêng lên tip mới:

~~~bash
git status
git branch rescue/feature-report-local-work HEAD
git stash push -u -m "before resyncing feature/report"
git rebase --onto origin/feature/report <old-shared-tip> feature/report
~~~

Trong lệnh này, `<old-shared-tip>` là commit cuối cùng của nhánh chia sẻ cũ mà maintainer đã thay thế. Mốc đó phải nằm trong lịch sử của nhánh local; Git sẽ phát lại các commit nằm sau mốc đó lên trên nhánh remote mới. Nếu nhánh local chưa chứa tip cũ này, hãy xác định đúng điểm tách bằng đồ thị commit và `git merge-base`, hoặc chọn riêng commit của mình để cherry-pick. Không đoán mốc upstream.

Sau khi rebase thành công, kiểm tra và áp dụng lại stash nếu đã tạo:

~~~bash
git status
git stash list
git stash apply stash@{0}
~~~

Nếu rebase phát sinh conflict, giải quyết từng file, stage các file đã sửa và chạy `git rebase --continue`; chỉ áp dụng stash sau khi rebase kết thúc. Nếu không xác định được commit riêng hoặc ranh giới lịch sử, giữ nguyên nhánh cứu hộ và nhờ maintainer cùng kiểm tra trước khi tiếp tục.

Nếu không chắc commit nào thuộc lịch sử cũ và commit nào là công việc riêng, dừng lại để so sánh log hoặc nhờ maintainer hỗ trợ. Với một vài commit riêng biệt, có thể tạo nhánh mới từ remote rồi cherry-pick đúng các commit cần giữ. Tránh rebase toàn bộ lịch sử cũ lên nhánh mới vì có thể tạo lại các thay đổi đã được thay thế.

Sau khi đồng bộ, kiểm tra diff, chạy test và chỉ push khi chắc chắn nhánh mới không chứa commit trùng hoặc thay đổi ngoài ý muốn.

## 13. Quy trình phục hồi rebase sai trong thực tế

Giả sử bạn rebase nhầm nhánh `feature/report` lên `release/2.x` thay vì `main`, và rebase đã hoàn tất nhưng chưa push.

**Bước 1 — Kiểm tra trạng thái**

~~~bash
git status
git branch --show-current
git log --oneline --graph --decorate -12
~~~

**Bước 2 — Tìm tip cũ**

~~~bash
git reflog show feature/report --date=iso
git show ORIG_HEAD --oneline --no-patch
~~~

Xác định hash trước khi rebase bắt đầu và kiểm tra commit đó bằng `git show`.

**Bước 3 — Bảo toàn trạng thái hiện tại**

~~~bash
git branch rescue/feature-report-wrong-rebase HEAD
~~~

Nếu có thay đổi chưa commit, lưu bằng stash hoặc một bản sao phù hợp trước khi reset.

**Bước 4 — Khôi phục nhánh**

~~~bash
git reset --hard <commit-before-rebase>
~~~

**Bước 5 — Kiểm tra và tiếp tục đúng hướng**

~~~bash
git log --oneline --graph --decorate -12
git status
git rebase origin/main
~~~

Sau khi rebase đúng, kiểm tra diff và test trước khi push. Vì nhánh chưa được push, không cần cập nhật cưỡng bức remote.

Nếu nhánh đã được chia sẻ, dừng ở bước bảo toàn trạng thái và lập kế hoạch phối hợp tại các phần trước. Không tự force push trong khi đồng đội vẫn đang làm việc trên lịch sử cũ.

## 14. Những sai lầm cần tránh

| Sai lầm | Hậu quả | Cách làm phù hợp |
|---|---|---|
| Chạy `reset --hard` mà chưa kiểm tra working tree | Mất thay đổi chưa commit | Kiểm tra status, stash hoặc sao lưu trước |
| Chọn nhầm entry trong reflog | Quay về sai commit | Xem commit bằng `git show`, đối chiếu lịch sử và thời điểm |
| Nhầm `--quit` với `--abort` | Dừng tiến trình nhưng vẫn giữ trạng thái đang rebase | Dùng `--abort` khi muốn trở về trạng thái trước rebase |
| Dùng `--skip` để vượt conflict mà không xem patch | Bỏ mất thay đổi của commit đang phát lại | Chỉ skip khi chủ động loại bỏ commit đó |
| Force push lên nhánh dùng chung mà không báo trước | Làm các máy khác lệch lịch sử, có nguy cơ mất commit | Thống nhất thời điểm, backup và dùng lease |
| Chạy `git pull` ngay sau khi remote bị viết lại | Có thể tạo merge giữa lịch sử cũ và mới | Fetch, so sánh log và chọn cách đồng bộ |
| Rebase lại toàn bộ nhánh cũ của đồng đội | Có thể phát lại commit đã được thay thế hoặc tạo thay đổi trùng | Xác định ranh giới commit riêng và dùng `--onto` hoặc cherry-pick |
| Dùng revert để xử lý mọi trường hợp | Có thể tạo commit đảo ngược không cần thiết khi thay đổi chỉ ở local | Chọn phục hồi local hay giữ lịch sử công khai theo tình huống |

## 15. Checklist trước và sau khi phục hồi

Trước khi thao tác:

- [ ] Xác định rebase đang chạy hay đã hoàn tất.
- [ ] Xác nhận đúng repository và nhánh.
- [ ] Kiểm tra working tree và file chưa được theo dõi.
- [ ] Tìm commit trước rebase bằng reflog; kiểm tra `ORIG_HEAD` nếu hữu ích.
- [ ] Tạo nhánh cứu hộ cho trạng thái hiện tại.
- [ ] Xác định nhánh đã được push hoặc có người khác sử dụng chưa.

Nếu cần viết lại nhánh chia sẻ:

- [ ] Thông báo và thống nhất với các thành viên liên quan.
- [ ] Fetch và ghi lại hash tip remote hiện tại.
- [ ] Tạm dừng các lần push cạnh tranh trong thời gian cập nhật.
- [ ] Dùng `--force-with-lease` với giá trị kỳ vọng phù hợp.
- [ ] Nếu lease từ chối, kiểm tra commit mới thay vì chuyển sang `--force`.
- [ ] Hướng dẫn đồng đội fetch, so sánh và bảo toàn commit riêng.

Sau khi phục hồi:

- [ ] Kiểm tra `git status` và đồ thị commit.
- [ ] Xác nhận diff đúng với mục tiêu.
- [ ] Chạy test cần thiết.
- [ ] Giữ nhánh cứu hộ cho tới khi xác nhận không còn cần.
- [ ] Xác nhận remote và các máy liên quan đã đồng bộ đúng.

## 16. Những điểm cần ghi nhớ

- Nếu rebase còn chạy và bạn muốn hủy, dùng `git rebase --abort`.
- Nếu rebase đã hoàn tất, dùng reflog để tìm tip trước rebase; `ORIG_HEAD` chỉ là nguồn tham khảo bổ sung.
- Tạo nhánh cứu hộ trước khi reset để giữ trạng thái hiện tại.
- `git reset --hard` có thể xóa thay đổi chưa commit; phải kiểm tra và sao lưu trước.
- Rebase trên nhánh local chưa chia sẻ thường dễ phục hồi hơn nhánh đã được nhiều người sử dụng.
- Khi viết lại nhánh remote, thông báo trước, lưu hash cũ, tạm dừng push cạnh tranh và dùng `--force-with-lease`.
- Sau khi remote bị viết lại, đồng đội cần fetch và so sánh lịch sử; không pull hoặc reset một cách máy móc.
- Nếu commit đã được công bố rộng rãi hoặc tích hợp vào nhánh chính, `git revert` thường giữ lịch sử rõ ràng hơn force push.

Khôi phục rebase là việc xác định đúng mốc lịch sử và bảo toàn mọi công việc có giá trị trước khi di chuyển tham chiếu. Khi nhánh đã được chia sẻ, thành công còn phụ thuộc vào việc cả nhóm cùng hiểu lịch sử nào đang được giữ, lịch sử nào bị thay thế và cách từng máy đồng bộ lại an toàn.

