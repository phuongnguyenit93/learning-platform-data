# Lịch sử tuyến chính với --first-parent và cách đọc commit hợp nhất

Khi xem lịch sử của một nhánh tích hợp như main, toàn bộ commit từ mọi nhánh tính năng có thể khiến đồ thị trở nên dài và khó theo dõi. Git cung cấp tùy chọn **--first-parent** để đi theo tuyến chính của lịch sử: bắt đầu từ commit đang xem, đi ngược qua parent thứ nhất của mỗi commit và không rẽ sang các parent còn lại của merge commit.

Cách xem này giúp trả lời câu hỏi: nhánh chính đã nhận những thay đổi tích hợp nào, theo thứ tự nào? Nó đặc biệt hữu ích với quy trình nhóm thường merge pull request vào main hoặc release branch. Để hiểu đầy đủ nội dung của một lần tích hợp, bạn vẫn cần biết cách đọc parent của merge commit và xem diff của merge so với từng parent.

## 1. Lịch sử Git là đồ thị commit

Mỗi commit lưu thông tin về snapshot của dự án và tham chiếu đến commit cha (parent). Một commit thông thường có một parent; commit đầu tiên của repository không có parent. Merge commit thường có từ hai parent trở lên.

Ví dụ, nhánh feature được tạo từ main, phát triển hai commit rồi được merge vào main:

~~~text
X (main) has parents: M1, F2
M1 -> A
F2 -> F1 -> A
~~~ 

Trong mô tả quan hệ parent:

- A là commit nền chung.
- M1 là commit được tạo trên main sau khi nhánh feature tách ra.
- F1 và F2 là các commit riêng trên feature/search.
- X là merge commit đưa feature/search vào main.

Merge commit X có thứ tự parent:

1. Parent thứ nhất là M1, tip của nhánh hiện tại trước khi merge.
2. Parent thứ hai là F2, tip của nhánh được merge vào.

Thứ tự này có ý nghĩa khi xem lịch sử. Ký hiệu X^1 tham chiếu parent thứ nhất; X^2 tham chiếu parent thứ hai.

## 2. --first-parent đi theo tuyến chính như thế nào?

Khi chạy:

~~~bash
git log --first-parent
~~~

Git bắt đầu ở HEAD và đi ngược lịch sử. Với commit thông thường, nó đi đến parent duy nhất. Khi gặp merge commit, Git chỉ đi tiếp theo parent thứ nhất. Các nhánh phụ được nối vào qua parent thứ hai hoặc các parent tiếp theo không được duyệt từ merge đó.

Với đồ thị ở phần trước, kết quả tuyến chính gồm:

~~~text
X  Merge feature/search
|
M1 Main: update roadmap
|
A  Initial commit
~~~

Các commit F1 và F2 không xuất hiện trong tuyến first-parent vì chúng nằm trên nhánh phụ được nhập qua parent thứ hai của X. Merge commit X vẫn xuất hiện, nên người đọc biết có một lần tích hợp đã diễn ra.

**--first-parent chỉ thay đổi cách duyệt lịch sử khi xem log.** Nó không sửa commit, không đổi parent, không tạo branch và không viết lại lịch sử repository.

## 3. So sánh lịch sử đầy đủ và lịch sử tuyến chính

Trong repository có nhiều nhánh được merge, hai cách xem trả lời hai câu hỏi khác nhau:

| Cách xem | Nội dung | Phù hợp khi |
|---|---|---|
| git log | Các commit reachable theo đồ thị parent từ ref được chọn | Điều tra chi tiết thay đổi và nguồn gốc commit |
| git log --first-parent | Chỉ các commit trên chuỗi parent thứ nhất, gồm cả merge commit | Theo dõi tiến trình tích hợp của main hoặc release |
| git log --first-parent --merges | Chỉ merge commit trên tuyến chính | Xem các lần tích hợp nhánh |
| git log --first-parent --no-merges | Commit không phải merge trên tuyến chính | Xem các commit được tạo trực tiếp trên tuyến chính hoặc được đưa vào bằng fast-forward/rebase |

Không nên dùng first-parent thay cho lịch sử đầy đủ trong mọi tình huống. Khi cần biết feature branch đã chứa những commit nào, vì sao một dòng code xuất hiện hoặc commit nào đã giới thiệu lỗi, hãy xem cả đồ thị và lịch sử của nhánh phụ.

## 4. Tạo repository thực hành có merge commit

Tạo một repository riêng để các lệnh không ảnh hưởng dự án đang làm:

~~~bash
mkdir first-parent-lab
cd first-parent-lab
git init --initial-branch=main

git config user.name "Git Learner"
git config user.email "learner@example.test"

printf '# Project\n' > README.md
git add README.md
git commit -m "Initial project"
~~~

Kiểm tra commit nền:

~~~bash
git status --short
git log --oneline --decorate -1
~~~

Working tree cần sạch trước khi tạo nhánh. Bài thực hành giả định Git hỗ trợ lệnh git switch; nếu phiên bản cũ hơn, có thể dùng git checkout tương đương.

## 5. Tạo nhánh feature và thêm hai commit

Tạo nhánh tính năng:

~~~bash
git switch -c feature/search
~~~

Tạo commit đầu tiên:

~~~bash
printf 'Search API: v1\n' > search.md
git add search.md
git commit -m "Add search API notes"
~~~

Tạo commit thứ hai:

~~~bash
printf 'Search API: v2\nPagination: enabled\n' > search.md
git add search.md
git commit -m "Document search pagination"
~~~

Kiểm tra nhánh:

~~~bash
git log --oneline --decorate -3
~~~

Nhánh feature/search hiện có hai commit sau commit nền. Các commit này chưa nằm trên tuyến chính main.

## 6. Tạo một commit riêng trên main

Quay về main:

~~~bash
git switch main
~~~

Thêm một thay đổi riêng trên main:

~~~bash
printf 'Next milestone: search integration\n' > ROADMAP.md
git add ROADMAP.md
git commit -m "Update project roadmap"
~~~

Hai nhánh đã phân kỳ: main có commit roadmap, còn feature/search có hai commit tài liệu tìm kiếm. Xem toàn bộ đồ thị:

~~~bash
git log --graph --oneline --decorate --all
~~~

Bạn sẽ thấy hai nhánh cùng xuất phát từ commit Initial project. Đến thời điểm này chưa có merge commit.

## 7. Tạo merge commit để giữ dấu mốc tích hợp

Đang ở main, merge feature/search với --no-ff:

~~~bash
git merge --no-ff feature/search -m "Merge feature/search"
~~~

Vì hai nhánh đã phân kỳ, Git cần kết hợp lịch sử của cả hai. Tùy chọn --no-ff yêu cầu tạo merge commit ngay cả trong tình huống có thể fast-forward. Trong bài này, merge commit được tạo tự nhiên vì main đã có commit riêng sau khi nhánh feature tách ra.

Kiểm tra đồ thị:

~~~bash
git log --graph --oneline --decorate --all
~~~

Quan hệ parent khái niệm sau merge:

~~~text
X (HEAD -> main): parents M1, F2
M1 -> A
F2 -> F1 -> A
~~~

X là merge commit. Parent thứ nhất là M1 vì main là nhánh đang checkout khi chạy merge. Parent thứ hai là F2 vì feature/search là nhánh được merge vào.

## 8. Đọc tuyến chính với --first-parent

Chạy:

~~~bash
git log --first-parent --oneline --decorate main
~~~

Kết quả sẽ có dạng:

~~~text
* X (HEAD -> main) Merge feature/search
* M1 Update project roadmap
* A Initial project
~~~

Vì lệnh chỉ duyệt parent thứ nhất, danh sách commit của tuyến chính là một chuỗi tuyến tính. Các commit F1 và F2 không được in ra trong kết quả này. Để quan sát cả nhánh phụ và các đường nối, bỏ --first-parent:

~~~bash
git log --graph --oneline --decorate main
~~~

Danh sách first-parent chỉ chứa X, M1 và A. F1 và F2 không được duyệt qua parent thứ hai của X.

So sánh với log đầy đủ:

~~~bash
git log --oneline --decorate main
~~~

Log đầy đủ có thể chứa X, F2, F1, M1 và A vì tất cả đều reachable từ main thông qua các parent của merge commit.

## 9. Chỉ xem các lần tích hợp trên tuyến chính

Để xem merge commit trên main:

~~~bash
git log --first-parent --merges --oneline --decorate main
~~~

Lệnh này hữu ích khi muốn tổng hợp pull request hoặc feature đã được tích hợp bằng merge commit. Kết quả trong lab gồm Merge feature/search.

Để xem các commit không phải merge trên tuyến chính:

~~~bash
git log --first-parent --no-merges --oneline --decorate main
~~~

Kết quả gồm commit trực tiếp trên tuyến main như Update project roadmap và Initial project. Các commit F1, F2 không được liệt kê bởi chúng nằm sau parent thứ hai của merge commit.

Có thể xem thêm tác giả và ngày:

~~~bash
git log --first-parent --format="%h %ad %an %s" --date=short main
~~~

Khi viết báo cáo phát hành, định dạng gọn này giúp nhìn thứ tự tích hợp cùng người tạo commit và ngày tạo.

## 10. Xác định parent của merge commit

Một merge commit không chỉ là commit có subject bắt đầu bằng chữ Merge. Hãy đọc metadata để xác định parent thực tế:

~~~bash
# Hiển thị metadata và các parent của HEAD
git show --no-patch --pretty=raw HEAD

# In OID của parent thứ nhất và thứ hai
git rev-parse HEAD^1
git rev-parse HEAD^2

# Xem commit cùng các parent trên một dòng
git log -1 --format="%H%n%P%n%s" HEAD
~~~

Trong output của git show --pretty=raw, trường parent xuất hiện theo thứ tự. Parent đầu tiên là tuyến mà merge được thực hiện trên đó; các parent tiếp theo là những tip được nhập vào.

Các cách viết revision hữu ích:

| Cú pháp | Ý nghĩa |
|---|---|
| HEAD^1 | Parent thứ nhất của HEAD |
| HEAD^2 | Parent thứ hai của HEAD |
| HEAD^ | Viết tắt của HEAD^1 |
| HEAD~1 | Đi lên một parent thứ nhất |
| HEAD~2 | Đi lên hai bước theo chuỗi parent thứ nhất |
| HEAD^2~1 | Từ parent thứ hai, đi lên một parent thứ nhất của commit đó |

Với merge commit, HEAD~1 và HEAD^1 cùng chỉ parent thứ nhất. HEAD~2 tiếp tục đi theo parent thứ nhất của parent thứ nhất, không phải parent thứ hai của merge.

## 11. Xem merge commit thay đổi gì so với từng parent

Một câu hỏi quan trọng khi review merge là: merge commit đã đưa thêm điều gì vào tuyến chính so với trạng thái main trước đó?

So sánh kết quả merge với parent thứ nhất:

~~~bash
git diff HEAD^1 HEAD
~~~

Diff này thể hiện nội dung của merge result so với main ngay trước merge. Nó thường là cách hữu ích để xem những thay đổi được đưa vào main.

So sánh kết quả merge với parent thứ hai:

~~~bash
git diff HEAD^2 HEAD
~~~

Diff này cho thấy kết quả cuối cùng khác nhánh feature được merge vào như thế nào. Nó có thể bao gồm các thay đổi vốn đã có trên main và những quyết định giải quyết conflict.

Nên giới hạn theo đường dẫn khi cần:

~~~bash
git diff HEAD^1 HEAD -- src/
git diff HEAD^2 HEAD -- src/
~~~

Nếu cần OID merge cụ thể thay vì HEAD hiện tại, thay HEAD bằng OID hoặc tên ref của merge commit.

## 12. Ba cách đọc diff của merge commit

Merge commit có nhiều parent nên diff có một số cách trình bày khác nhau:

| Cách xem | Lệnh | Mục đích |
|---|---|---|
| So với parent thứ nhất | git diff M^1 M | Xem nội dung merge đưa vào nhánh hiện tại |
| So với từng parent | git show -m M | Hiển thị diff riêng của merge commit so với mỗi parent |
| Combined diff | git show --cc M | Hiển thị dạng kết hợp để nhận ra phần kết quả khác biệt so với các parent |
| Re-merge diff | git show --remerge-diff M | So sánh kết quả merge đã commit với kết quả merge tự động được tái tạo, hữu ích để xem phần giải quyết conflict thủ công |

Thay M bằng OID merge commit cần kiểm tra.

### Diff so với parent thứ nhất

~~~bash
git diff M^1 M
~~~

Đây thường là góc nhìn trực tiếp nhất khi review những gì được tích hợp vào main. Nếu merge chỉ thêm nội dung từ feature mà không có conflict, phần diff thường gần với nội dung feature đã đóng góp.

### Diff riêng cho mỗi parent với -m

~~~bash
git show -m --format=fuller M
~~~

Tùy chọn -m yêu cầu hiển thị diff của merge commit riêng biệt so với từng parent. Điều này tạo ra nhiều góc nhìn; đừng cộng số dòng của các diff đó như thể chúng là những thay đổi độc lập.

### Combined diff với --cc

~~~bash
git show --cc M
~~~

Combined diff dùng định dạng nhiều cột, thường có hunk header bắt đầu bằng @@@. Nó được thiết kế để thể hiện kết quả merge so với nhiều parent cùng lúc. Một số đường dẫn chỉ khác một parent có thể không xuất hiện trong combined diff; khi cần kiểm tra toàn bộ nội dung tích hợp, hãy xem diff so với parent thứ nhất hoặc dùng -m.

### Re-merge diff

~~~bash
git show --remerge-diff M
~~~

Trên phiên bản Git hỗ trợ tùy chọn này, Git tái tạo kết quả merge từ các parent rồi so sánh với merge result đã được commit. Phần khác biệt giúp review những quyết định giải quyết conflict thủ công. Kết quả phụ thuộc merge strategy và khả năng tái tạo của Git; nếu merge tự động đã tạo đúng nội dung cuối cùng, re-merge diff có thể không có thay đổi.

## 13. --first-parent khác các tùy chọn duyệt và sắp xếp khác

Một số tùy chọn log trông tương tự nhưng giải quyết câu hỏi khác:

| Tùy chọn | Tác dụng |
|---|---|
| --first-parent | Khi gặp merge, chỉ duyệt parent thứ nhất |
| --all | Bắt đầu duyệt từ tất cả refs được Git biết đến |
| --merges | Chỉ chọn merge commit |
| --no-merges | Loại merge commit khỏi kết quả |
| --ancestry-path | Giới hạn vào các commit nằm trên đường tổ tiên giữa hai đầu mốc đã chọn |
| --topo-order | Sắp xếp để commit con không xuất hiện trước commit cha trong đồ thị |
| --date-order | Ưu tiên ngày commit nhưng vẫn giữ ràng buộc cha/con |
| --graph | Vẽ đường nối giữa các commit trong đồ thị |

--topo-order và --date-order thay đổi thứ tự trình bày, không thay thế quy tắc chọn parent của --first-parent. --ancestry-path cũng không đồng nghĩa với first-parent: nó lọc theo quan hệ tổ tiên giữa hai điểm, trong khi first-parent chọn một cạnh cụ thể khi đi qua merge.

Ví dụ:

~~~bash
# Xem tuyến chính của main, có đồ thị
git log --first-parent --graph --oneline main

# Xem mọi ref và đồ thị đầy đủ
git log --all --graph --oneline --decorate

# Xem merge commit trong lịch sử đầy đủ
git log --merges --oneline main
~~~

## 14. Ảnh hưởng của cách tích hợp nhánh

Lịch sử first-parent phụ thuộc cách nhóm tích hợp nhánh. Không phải workflow nào cũng tạo merge commit hai parent.

| Cách tích hợp | Hình dạng lịch sử | Điều first-parent thể hiện |
|---|---|---|
| Merge commit | Một commit có nhiều parent | Hiển thị merge commit và đi tiếp theo parent thứ nhất; commit ở nhánh phụ không được duyệt từ parent thứ hai |
| Fast-forward | Ref main tiến thẳng đến commit của feature | Các commit feature trở thành chuỗi parent thứ nhất của main và xuất hiện trong first-parent log |
| Squash merge | Một commit mới trên main, thường có một parent | Hiển thị commit squash; các commit gốc của feature không trở thành parent của commit squash |
| Rebase rồi fast-forward | Commit feature được tạo lại trên nền main mới | First-parent hiển thị chuỗi commit đã rebase như lịch sử tuyến tính |
| Octopus merge | Merge commit có nhiều hơn hai parent | First-parent chỉ đi theo parent thứ nhất và bỏ qua các parent còn lại khi duyệt |

### Fast-forward

Nếu main chưa có commit riêng sau khi feature tách ra, main có thể là tổ tiên của feature. Khi merge, Git chỉ di chuyển ref main đến tip feature:

~~~bash
git merge feature/search
~~~

Không có merge commit mới. Các commit feature giờ nằm trực tiếp trên chuỗi parent thứ nhất của main, vì vậy first-parent log sẽ hiển thị chúng. Nếu muốn giữ dấu mốc tích hợp dù có thể fast-forward, dùng --no-ff.

### Squash merge

Squash merge tạo một commit mới chứa tổng thay đổi của nhánh feature nhưng không giữ các commit feature làm parent:

~~~bash
git merge --squash feature/search
git commit -m "Add search feature"
~~~

First-parent log hiển thị commit Add search feature như một commit tuyến chính thông thường. Nó không thể hiện rằng commit đó đã tổng hợp F1 và F2, trừ khi thông điệp, metadata hoặc quy ước liên kết pull request cung cấp thông tin.

### Rebase

Rebase tạo lại các commit feature trên một base mới. Nếu sau đó fast-forward main đến tip feature, các commit đã rebase trở thành chuỗi tuyến chính. OID của commit được tạo lại khác OID cũ vì parent đã thay đổi.

First-parent log phản ánh topology sau rebase, không tự phục hồi cấu trúc nhánh ban đầu. Nếu cần điều tra lịch sử trước rebase, có thể phải xem refs còn tồn tại, reflog hoặc bản sao repository khác.

## 15. Khi nào nên dùng lịch sử first-parent?

First-parent hữu ích khi:

- Theo dõi những mốc tích hợp vào main hoặc release branch.
- Viết release note dựa trên các merge commit.
- Xem lịch sử tuyến chính mà không bị nhiều commit chi tiết của feature branch làm dài output.
- Xác định thứ tự các đợt tích hợp và commit được tạo trực tiếp trên tuyến chính.
- Kiểm tra nhanh merge commit nào cần review sâu hơn.

Không nên chỉ dùng first-parent khi:

- Truy tìm dòng code hoặc commit đã giới thiệu bug.
- Xem toàn bộ đóng góp của một feature branch.
- Điều tra conflict hoặc quyết định sửa code trong merge.
- Phân tích lịch sử đã được rebase hoặc squash.
- Kiểm tra commit của các nhánh chưa được tích hợp vào tuyến chính.

Một quy trình tốt là bắt đầu bằng first-parent để hiểu các mốc tích hợp, sau đó mở rộng sang full history và diff của merge commit khi có câu hỏi cụ thể.

## 16. Quy trình review một merge commit

Khi cần kiểm tra một lần tích hợp vào main, có thể làm theo thứ tự:

1. Xem các merge commit trên tuyến chính:

   ~~~bash
   git log --first-parent --merges --oneline --decorate main
   ~~~

2. Chọn merge commit M và đọc metadata, đặc biệt thứ tự parent:

   ~~~bash
   git show --no-patch --pretty=raw M
   ~~~

3. Xác định nhánh hiện tại trước merge và tip nhánh được nhập:

   ~~~bash
   git rev-parse M^1
   git rev-parse M^2
   ~~~

4. Xem nội dung được đưa vào tuyến chính:

   ~~~bash
   git diff M^1 M
   ~~~

5. Nếu merge có xử lý conflict, xem thêm từng parent hoặc re-merge diff:

   ~~~bash
   git show -m M
   git show --remerge-diff M
   ~~~

6. Khi cần hiểu lịch sử feature, xem các commit reachable từ parent thứ hai:

   ~~~bash
   git log --oneline M^1..M^2
   ~~~

7. Chạy test hoặc kiểm tra liên quan đến thay đổi đã tích hợp.

Lệnh re-merge diff cần phiên bản Git có hỗ trợ. Nếu không có, dùng diff so với từng parent và kiểm tra lịch sử feature để hiểu kết quả.

## 17. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
|---|---|
| --first-parent chỉ hiển thị commit không phải merge | Không. Nó hiển thị merge commit trên tuyến chính, rồi đi tiếp theo parent thứ nhất. |
| --first-parent làm mất commit nhánh phụ | Không. Nó chỉ không duyệt các parent phụ trong lần xem log đó; commit vẫn còn trong đồ thị nếu có ref hoặc object giữ lại. |
| Parent thứ nhất luôn là commit mới nhất theo thời gian | Không. Parent thứ nhất là parent theo thứ tự được ghi trong merge commit, thường là tip của nhánh đang merge vào. |
| Parent thứ hai luôn là feature branch | Với merge hai nhánh thông thường, parent thứ hai là tip được merge vào; merge nhiều nhánh có thể có thêm parent. |
| HEAD~2 là parent thứ hai của merge | Không. Dấu ~ luôn đi theo chuỗi parent thứ nhất; dùng ^2 để chọn parent thứ hai. |
| Mọi merge đều tạo merge commit | Không. Fast-forward chỉ di chuyển ref; squash tạo một commit thường; rebase thay đổi topology trước khi tích hợp. |
| Combined diff luôn hiển thị mọi thay đổi từ mọi parent | Không. Combined diff có quy tắc hiển thị riêng; xem diff với parent thứ nhất hoặc -m để kiểm tra đầy đủ hơn. |
| First-parent cho biết đầy đủ lịch sử phát triển feature | Không. Nó tập trung vào tuyến tích hợp; cần full history để xem các commit trên nhánh phụ. |

## 18. Tự kiểm tra

1. **--first-parent làm gì khi gặp merge commit?**
   - Chỉ đi tiếp theo parent thứ nhất và không duyệt parent phụ từ merge đó.
2. **Merge commit trên main thường có parent thứ nhất là commit nào?**
   - Tip của main ngay trước khi merge.
3. **Lệnh nào chỉ xem merge commit trên tuyến chính?**
   - git log --first-parent --merges.
4. **Làm sao xem nội dung merge result so với main trước merge?**
   - git diff M^1 M.
5. **HEAD~2 khác HEAD^2 như thế nào?**
   - HEAD~2 đi hai bước theo parent thứ nhất; HEAD^2 chọn parent thứ hai trực tiếp.
6. **Squash merge xuất hiện thế nào trong first-parent log?**
   - Như một commit tuyến chính thông thường; các commit gốc của feature không phải parent của commit squash.
7. **Vì sao cần xem full history sau khi first-parent đã cho thấy merge commit?**
   - Để biết các commit chi tiết trên nhánh phụ, nguồn gốc thay đổi và cách feature được phát triển.
8. **Lệnh nào giúp xem phần giải quyết conflict khác với kết quả merge tự động?**
   - git show --remerge-diff M trên phiên bản Git hỗ trợ.

## Kết luận

--first-parent là góc nhìn tập trung vào tuyến tích hợp của một nhánh. Nó giữ lại merge commit làm dấu mốc, sau đó chỉ đi theo parent thứ nhất để tạo lịch sử dễ đọc cho main hoặc release branch. Muốn hiểu merge commit, hãy kiểm tra thứ tự parent bằng git show --pretty=raw, dùng M^1 và M^2 để phân biệt hai phía, rồi xem diff so với parent thứ nhất, từng parent hoặc combined/re-merge diff. Luôn kết hợp first-parent với full history khi cần truy tìm chi tiết, vì fast-forward, squash và rebase tạo ra topology khác nhau.
