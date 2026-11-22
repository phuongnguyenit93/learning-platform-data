# Hiểu các nút stage, sync, publish và discard trong công cụ

Các công cụ Git có giao diện đồ họa thường đặt những nút như **Stage**, **Sync**, **Publish Branch** và **Discard Changes** ở vị trí dễ thấy. Chúng giúp bạn thao tác nhanh mà không cần nhớ mọi lệnh Git, nhưng mỗi nút tác động đến một phần khác nhau của repository. Nếu nhầm lẫn, bạn có thể đẩy nhầm nhánh lên remote, kéo thay đổi chưa sẵn sàng hoặc làm mất nội dung đang sửa.

Bài này giải thích bốn thao tác theo trạng thái thật của Git: stage đưa thay đổi vào index để chuẩn bị commit; publish đưa branch local lên remote lần đầu và thiết lập upstream; sync trao đổi commit giữa local và remote; discard loại bỏ thay đổi chưa commit. Bạn sẽ học cách đọc giao diện, kiểm tra trạng thái trước khi bấm, hiểu điều gì xảy ra sau thao tác và khôi phục khi gặp lỗi.

Bài thuộc chương **Công cụ và tích hợp** của module **SOURCE_CONTROL_GIT**. Module hướng dẫn Git từ working tree, staging area, commit và lịch sử đến branch, merge, rebase, remote và tag; đồng thời rèn cách cộng tác qua nhánh, giải quyết xung đột, truy tìm thay đổi và khôi phục thao tác sai mà vẫn bảo toàn lịch sử quan trọng. Hiểu các nút trong IDE giúp bạn áp dụng đúng quy trình Git khi làm việc bằng giao diện đồ họa.

## 1. Bốn nút này tác động đến đâu?

Một cách dễ nhớ là phân biệt ba vùng dữ liệu và hai nơi lưu trữ:

- **Working tree:** các file bạn đang mở và chỉnh sửa.
- **Index / staging area:** phiên bản file đã chọn để đưa vào commit tiếp theo.
- **Local repository:** các commit đã được tạo trên máy.
- **Remote repository:** repository trên máy chủ như GitHub, GitLab hoặc máy chủ Git nội bộ.

| Nút trong công cụ | Tác động chính | Lệnh Git thường tương ứng |
|---|---|---|
| Stage | Chọn thay đổi từ working tree đưa vào index | <code>git add</code> |
| Publish Branch | Đẩy branch local mới lên remote và thiết lập upstream | <code>git push -u</code> |
| Sync | Trao đổi commit giữa branch local và upstream; thường pull rồi push | <code>git pull</code> và <code>git push</code> |
| Discard Changes | Loại bỏ thay đổi chưa commit ở file được chọn | Thường liên quan <code>git restore</code>; file untracked có thể cần thao tác riêng |

Các nút có thể có tên hoặc hành vi chi tiết khác nhau giữa VS Code, GitHub Desktop, Visual Studio và IDE JetBrains. Hãy đọc phần mô tả hoặc xác nhận trong hộp thoại của công cụ trước khi thực hiện, nhất là với thao tác discard và sync.

## 2. Stage: chọn nội dung cho commit tiếp theo

Khi bạn sửa file, thay đổi xuất hiện trong working tree. Git chưa tự đưa mọi thay đổi đó vào commit. Stage là bước chọn nội dung sẽ được ghi vào snapshot kế tiếp.

Ví dụ, bạn sửa file:

~~~text
src/PaymentService.java
README.md
~~~

Trong cửa sổ Source Control của VS Code, các file chưa stage thường xuất hiện trong nhóm **Changes**. Khi stage một file, công cụ chuyển file đó sang nhóm **Staged Changes**. Ở GitHub Desktop, thao tác tương tự thường là chọn checkbox bên cạnh file. Trong JetBrains IDE, bạn có thể chọn file hoặc từng phần thay đổi trong cửa sổ Commit.

Lệnh tương ứng:

~~~bash
git add src/PaymentService.java
~~~

Lệnh này stage toàn bộ thay đổi hiện có của file. Sau đó kiểm tra:

~~~bash
git status
git diff --staged
~~~

<code>git status</code> cho biết file nào đã stage và file nào còn thay đổi chưa stage. <code>git diff --staged</code> hiển thị chính xác nội dung đã chọn cho commit.

### Stage không tạo commit

Stage chỉ cập nhật index. Nó không tạo commit, không gửi dữ liệu lên remote và không làm thay đổi lịch sử. Bạn vẫn cần commit sau khi kiểm tra nội dung:

~~~bash
git commit -m "Add payment retry handling"
~~~

Trong giao diện, sau khi stage, bạn thường thấy nút Commit hoặc ô nhập commit message. Chỉ commit khi đã xem diff staged và thông điệp mô tả đúng mục đích thay đổi.

## 3. Stage toàn bộ file và stage từng phần

### Stage một file

Chọn file cần đưa vào commit, hoặc dùng:

~~~bash
git add src/PaymentService.java
~~~

Đây là lựa chọn phù hợp khi file chứa một thay đổi có cùng mục đích.

### Stage tất cả thay đổi

Nút **Stage All Changes** hoặc thao tác tương tự thường đưa toàn bộ thay đổi được công cụ nhận diện vào index. Lệnh phổ biến:

~~~bash
git add -A
~~~

Lệnh này cập nhật index cho các file được thêm, sửa và xóa trong phạm vi repository. Trước khi dùng, kiểm tra danh sách file vì một file debug, log hoặc cấu hình local có thể bị stage nhầm.

### Stage từng hunk hoặc từng dòng

Một file đôi khi chứa nhiều thay đổi độc lập. Ví dụ bạn vừa sửa logic thanh toán, vừa thêm một đoạn log tạm. Nếu stage toàn bộ file, cả hai thay đổi sẽ cùng nằm trong commit.

Các công cụ thường hỗ trợ stage từng hunk hoặc từng dòng. Trong terminal, có thể dùng:

~~~bash
git add -p src/PaymentService.java
~~~

Git hiển thị từng nhóm thay đổi và hỏi bạn chọn stage hay bỏ qua. Một số phím thường gặp trong chế độ tương tác:

| Phím | Ý nghĩa |
|---|---|
| <code>y</code> | Stage hunk hiện tại |
| <code>n</code> | Bỏ qua hunk hiện tại |
| <code>s</code> | Chia hunk thành các phần nhỏ hơn nếu có thể |
| <code>e</code> | Chỉnh patch thủ công |
| <code>q</code> | Thoát |

Trong giao diện đồ họa, chọn các dòng hoặc hunk cần stage rồi xác nhận. Sau đó kiểm tra:

~~~bash
git diff
git diff --staged
~~~

Lệnh đầu cho thấy thay đổi còn trong working tree; lệnh sau cho thấy nội dung sẽ được commit. Một file có thể đồng thời có phần đã stage và phần chưa stage.

## 4. Unstage: đưa thay đổi ra khỏi index

Nếu stage nhầm file hoặc hunk, bạn có thể unstage để đưa thay đổi ra khỏi index. Nội dung trong working tree vẫn còn.

Trong VS Code, thao tác thường có tên **Unstage Changes** hoặc biểu tượng dấu trừ cạnh file staged. Trong GitHub Desktop, bỏ chọn checkbox của file. JetBrains có thể cung cấp thao tác Unstage hoặc bỏ chọn file trong Commit tool window.

Lệnh:

~~~bash
git restore --staged src/PaymentService.java
~~~

Lệnh này đưa trạng thái index của file về phiên bản trong HEAD. Nó không xóa nội dung đang sửa trong working tree.

Kiểm tra:

~~~bash
git status
git diff
git diff --staged
~~~

Nếu file không còn thay đổi đã stage nhưng vẫn còn thay đổi chưa stage, nội dung bạn đang sửa vẫn an toàn. Đây là điểm khác biệt quan trọng giữa **Unstage** và **Discard**.

## 5. Commit: lưu snapshot local

Sau khi stage và kiểm tra nội dung, bạn tạo commit. Commit ghi lại snapshot từ index vào lịch sử local.

Trong công cụ đồ họa:

1. Mở danh sách Staged Changes hoặc danh sách file được chọn để commit.
2. Kiểm tra diff.
3. Nhập commit message ngắn gọn, nêu mục đích thay đổi.
4. Nhấn Commit.

Lệnh tương ứng:

~~~bash
git diff --staged
git commit -m "Fix payment timeout handling"
~~~

Commit chỉ lưu vào repository local. Branch local tiến lên commit mới, nhưng remote chưa thay đổi cho đến khi push hoặc sync.

Nếu công cụ cung cấp lựa chọn **Commit and Push** hoặc **Commit and Sync**, hãy hiểu đó là nhiều thao tác nối tiếp: tạo commit local trước, rồi mới gửi commit lên remote. Đừng giả định chỉ bấm Commit là đồng nghiệp đã nhìn thấy thay đổi.

## 6. Publish Branch: lần đầu chia sẻ branch local

Khi bạn tạo branch mới trên máy:

~~~bash
git switch -c feature/payment-retry
~~~

Branch này mới chỉ tồn tại trong local repository. Remote chưa có branch tương ứng. Công cụ như VS Code có thể hiển thị nút **Publish Branch**; GitHub Desktop thường hiển thị **Publish branch** hoặc nút tương đương.

Publish thường thực hiện hai việc:

1. Push commit của branch local lên remote.
2. Thiết lập upstream để branch local biết nó theo dõi branch remote nào.

Lệnh tương ứng:

~~~bash
git push -u origin feature/payment-retry
~~~

Trong đó:

- <code>origin</code> là tên remote.
- <code>feature/payment-retry</code> là branch local cần chia sẻ.
- <code>-u</code> hoặc <code>--set-upstream</code> thiết lập upstream tracking.

Sau khi publish, kiểm tra:

~~~bash
git branch -vv
git branch -r
git status -sb
~~~

Bạn thường sẽ thấy branch local theo dõi <code>origin/feature/payment-retry</code>. Từ những lần sau, lệnh push hoặc pull trên branch đó có thể tự xác định upstream nếu cấu hình phù hợp.

### Publish không phải là tạo Pull Request

Publish Branch đưa branch lên remote. Nó không tự động có nghĩa là đã tạo Pull Request hoặc Merge Request. Một số nền tảng gợi ý tạo PR sau khi publish, nhưng đó là bước cộng tác riêng.

Sau khi publish, bạn có thể mở trang repository và tạo Pull Request/Merge Request theo quy trình của nhóm.

### Chọn đúng remote trước khi publish

Nếu repository có nhiều remote, ví dụ <code>origin</code> là fork của bạn và <code>upstream</code> là repository gốc, hãy xác nhận branch sẽ được đẩy đến đâu:

~~~bash
git remote -v
git branch -vv
~~~

Không publish vào repository gốc nếu bạn chỉ có quyền làm việc qua fork hoặc nhóm yêu cầu tạo branch ở remote khác.

## 7. Push khác Publish ở điểm nào?

Hai thao tác đều gửi commit từ local lên remote, nhưng ngữ cảnh thường khác nhau:

| Thao tác | Trường hợp |
|---|---|
| Publish Branch | Branch local chưa có upstream hoặc chưa tồn tại trên remote; công cụ giúp tạo branch remote và liên kết tracking |
| Push | Branch đã được publish hoặc đã có upstream; gửi các commit local mới lên branch remote tương ứng |

Ví dụ sau khi branch đã được publish, bạn tạo commit mới:

~~~bash
git add src/PaymentService.java
git commit -m "Add retry limit"
git push
~~~

Lệnh <code>git push</code> gửi commit mới lên upstream. Nếu branch chưa có upstream, Git có thể yêu cầu chỉ định remote và branch hoặc thiết lập tracking.

## 8. Sync: đồng bộ branch local với remote

Trong một số công cụ, nút **Sync Changes** kết hợp lấy commit mới từ remote và gửi commit local lên remote. Ở VS Code, thao tác Sync Changes thường thực hiện pull rồi push cho branch hiện tại. GitHub Desktop có thể thể hiện thành các nút Fetch origin, Pull origin và Push origin riêng.

Sync thường bao gồm hai hướng:

- **Pull:** lấy và tích hợp commit mới từ upstream vào branch local.
- **Push:** gửi commit local chưa có trên upstream lên remote.

Sơ đồ khái quát:

~~~text
Remote branch (origin/feature)
             |
             | pull / fetch + integrate
             v
        Local branch
             |
             | push
             v
Remote branch (origin/feature)
~~~

Trước khi sync, kiểm tra branch và trạng thái:

~~~bash
git branch --show-current
git status -sb
git branch -vv
~~~

Bạn cần biết mình đang ở branch nào, có thay đổi chưa commit không và upstream là branch nào. Nếu công cụ cho xem số commit ahead/behind, hãy đọc thông tin đó trước khi bấm.

### Sync không đồng nghĩa với stage hoặc commit

Sync trao đổi commit giữa local và remote. Nó không tự động đưa mọi thay đổi chưa stage vào index hoặc tạo commit cho chúng. Nhiều công cụ yêu cầu working tree sạch trước khi pull hoặc có thể cảnh báo rằng cần commit/stash thay đổi.

Nếu có file đang sửa dở, hãy quyết định rõ:

- Commit thay đổi nếu chúng đã sẵn sàng.
- Stage một phần và commit phần đó nếu thay đổi độc lập.
- Stash thay đổi tạm thời nếu cần pull trước.

Ví dụ:

~~~bash
git stash push -m "WIP before sync"
git pull
git stash pop
~~~

Stash có thể phát sinh conflict khi áp dụng lại. Kiểm tra trạng thái sau mỗi bước và không xóa stash cho đến khi xác nhận thay đổi đã được khôi phục an toàn.

## 9. Sync có thể dùng merge hoặc rebase

Pull gồm việc fetch commit mới rồi tích hợp chúng vào branch hiện tại. Cách tích hợp phụ thuộc cấu hình và tùy chọn:

- Merge tạo merge commit khi cần kết hợp hai lịch sử.
- Rebase phát lại commit local trên nền commit mới từ upstream.
- Fast-forward chỉ di chuyển branch nếu lịch sử local có thể tiến thẳng đến commit mới.

Các cấu hình thường ảnh hưởng:

~~~bash
git config --get pull.rebase
git config --get pull.ff
~~~

Bạn cũng có thể chọn rõ cho một lần:

~~~bash
git pull --rebase
~~~

hoặc:

~~~bash
git pull --no-rebase
~~~

Giao diện đồ họa có thể lấy cấu hình Git hiện tại hoặc cung cấp lựa chọn riêng. Khi nhóm có quy ước merge/rebase, hãy giữ cách làm thống nhất. Nếu chưa rõ, hỏi người quản lý repository trước khi thay đổi cấu hình pull toàn cục.

## 10. Khi Sync báo conflict

Nếu local và remote cùng sửa một vùng, quá trình tích hợp có thể phát sinh conflict. Công cụ thường hiển thị danh sách file xung đột và mở merge editor.

Quy trình xử lý:

1. Đọc tên file bị conflict.
2. Mở merge editor hoặc công cụ giải quyết xung đột.
3. So sánh các phía và tạo nội dung kết quả.
4. Lưu file.
5. Stage file đã giải quyết.
6. Tiếp tục merge hoặc rebase theo thông báo của Git.

Kiểm tra trạng thái:

~~~bash
git status
~~~

Nếu đang merge:

~~~bash
git add <resolved-file>
git merge --continue
~~~

Nếu đang rebase:

~~~bash
git add <resolved-file>
git rebase --continue
~~~

Không bấm Sync lặp lại khi tiến trình trước còn đang dở. Hãy hoàn tất hoặc hủy thao tác tích hợp hiện tại trước.

## 11. Discard Changes: loại bỏ thay đổi chưa commit

Discard là thao tác có tính phá hủy đối với nội dung đang sửa. Khi chọn **Discard Changes**, công cụ thường yêu cầu Git bỏ thay đổi ở file được chọn và đưa file về trạng thái đã lưu trong Git. Một số công cụ còn hỗ trợ discard file untracked hoặc xóa file mới chưa được theo dõi.

Trước khi discard, hãy xem diff và tự hỏi liệu có phần nội dung nào cần giữ lại hay không. Nếu chưa chắc, hãy tạo bản sao, stash hoặc commit tạm trước.

Với thay đổi chưa stage, lệnh tương ứng là:

~~~bash
git restore -- src/PaymentService.java
~~~

Lệnh này khôi phục working tree của file theo index hiện tại. Những thay đổi chưa stage trong file sẽ bị loại bỏ.

### Discard thay đổi đã stage

Nếu file đã stage, trước tiên đưa nó ra khỏi index:

~~~bash
git restore --staged -- src/PaymentService.java
~~~

Lệnh này giữ nội dung working tree. Nếu muốn loại bỏ luôn phần đang sửa trong working tree:

~~~bash
git restore --worktree -- src/PaymentService.java
~~~

Hai lệnh trên tách riêng hai việc: unstage và khôi phục working tree. Nếu muốn đưa cả index và working tree của file về HEAD trong một lần:

~~~bash
git restore --source=HEAD --staged --worktree -- src/PaymentService.java
~~~

Hãy chỉ định đúng đường dẫn. Trước khi chạy, có thể dùng:

~~~bash
git status
git diff
git diff --staged
~~~

### Discard file mới chưa được theo dõi

File untracked chưa nằm trong index và không có phiên bản trong HEAD để <code>git restore</code> khôi phục. Một số giao diện có lệnh xóa file untracked riêng.

Trong terminal, kiểm tra trước những gì sẽ bị xóa:

~~~bash
git clean -n
~~~

Chỉ khi danh sách đúng với ý định mới xóa file untracked:

~~~bash
git clean -f -- path/to/untracked-file
~~~

Đối với thư mục untracked, cần tùy chọn đệ quy phù hợp như <code>-d</code>. Lệnh clean có thể xóa dữ liệu không thể lấy lại từ Git; luôn xem kết quả dry-run trước và không dùng phạm vi rộng khi chưa hiểu.

## 12. Discard không phải là Undo commit

Discard dành cho thay đổi chưa commit trong working tree hoặc index. Nếu thay đổi đã được commit, discard không phải cách để xóa commit khỏi lịch sử.

Để tạo commit mới đảo ngược một commit đã chia sẻ, thường dùng:

~~~bash
git revert <commit>
~~~

Revert giữ lịch sử và tạo commit mới đảo ngược thay đổi. Nếu commit chưa chia sẻ và bạn cần sửa lịch sử local, có các công cụ như reset hoặc interactive rebase, nhưng phải cân nhắc ảnh hưởng đến commit con và người khác.

Không nhầm:

| Mục tiêu | Thao tác phù hợp |
|---|---|
| Bỏ thay đổi chưa stage | Discard / <code>git restore</code> |
| Bỏ trạng thái stage nhưng giữ nội dung sửa | Unstage / <code>git restore --staged</code> |
| Bỏ cả nội dung stage và chưa stage của một file | Restore cả index và working tree từ HEAD |
| Xóa file untracked | Discard untracked trong GUI hoặc <code>git clean</code> sau dry-run |
| Đảo ngược commit đã chia sẻ | <code>git revert</code> |
| Di chuyển branch local về commit khác | <code>git reset</code> khi hiểu rõ tác động |

## 13. Đọc trạng thái trong giao diện trước khi thao tác

Tên nhóm hoặc màu sắc có thể khác giữa các công cụ, nhưng bạn thường cần xác định:

- **Changes:** file đã sửa nhưng chưa stage.
- **Staged Changes:** file hoặc hunk đã nằm trong index.
- **Untracked:** file mới Git chưa theo dõi.
- **Outgoing / Ahead:** local có commit chưa được push.
- **Incoming / Behind:** remote có commit local chưa tích hợp.
- **Conflicts:** file đang ở trạng thái unmerged.

Các con số ahead/behind phụ thuộc lần fetch gần nhất. Nếu chưa fetch, công cụ có thể chưa biết remote vừa có commit mới. Một số giao diện thực hiện fetch khi mở cửa sổ đồng bộ hoặc khi bạn bấm nút kiểm tra cập nhật.

Để xác minh bằng terminal:

~~~bash
git status -sb
git branch -vv
git diff
git diff --staged
git log --oneline --decorate --graph --all -12
~~~

Những lệnh này giúp bạn xác nhận trạng thái thay vì chỉ dựa vào biểu tượng hoặc màu sắc trong IDE.

## 14. Ví dụ một vòng làm việc bằng giao diện

Giả sử bạn cần sửa lỗi timeout trong dịch vụ thanh toán và chia sẻ branch với nhóm.

**Bước 1: tạo branch làm việc**

Trong giao diện, chọn branch hiện tại rồi tạo branch mới, ví dụ <code>fix/payment-timeout</code>. Lệnh tương ứng:

~~~bash
git switch -c fix/payment-timeout
~~~

**Bước 2: chỉnh sửa và stage**

Thay đổi file dịch vụ, thêm test. Trong Source Control, xem từng diff rồi stage các file liên quan. Nếu một file có nhiều thay đổi độc lập, stage từng hunk.

**Bước 3: commit**

Nhập message như <code>Fix payment timeout handling</code> rồi commit. Kiểm tra commit đã xuất hiện trong lịch sử local.

**Bước 4: publish branch**

Nhấn Publish Branch hoặc chạy:

~~~bash
git push -u origin fix/payment-timeout
~~~

**Bước 5: tiếp tục làm việc và sync**

Khi có commit mới từ đồng đội hoặc remote, fetch/pull theo quy trình của nhóm. Giải quyết conflict nếu có. Sau khi local branch đã tích hợp đúng lịch sử, push commit mới lên remote.

**Bước 6: dọn thay đổi không cần thiết**

Nếu có log debug chưa commit, xem diff và discard đúng file hoặc hunk. Nếu còn cần giữ lại để làm sau, stash hoặc lưu bản sao thay vì discard.

## 15. Cùng một thao tác có thể mang nhãn khác nhau

Các công cụ không dùng chung một bộ nhãn bắt buộc. Bảng dưới đây mô tả tên thường gặp, không phải cam kết giao diện của mọi phiên bản:

| Ý định | VS Code | GitHub Desktop | IDE JetBrains |
|---|---|---|---|
| Stage file | Stage Changes / dấu cộng | Checkbox file | Chọn file trong Commit tool window |
| Unstage file | Unstage Changes / dấu trừ | Bỏ chọn checkbox | Bỏ chọn hoặc Unstage |
| Stage một phần | Stage Selected Ranges | Chọn dòng/hunk nếu phiên bản hỗ trợ | Chọn từng phần trong diff |
| Publish branch | Publish Branch | Publish branch | Push branch mới, thiết lập upstream |
| Sync | Sync Changes | Fetch/Pull/Push origin | Update Project và Push, tùy cấu hình |
| Discard | Discard Changes | Discard Changes | Rollback hoặc Revert local changes |

Nếu không chắc một nút sẽ làm gì, mở menu ngữ cảnh hoặc xem tooltip/help của đúng phiên bản công cụ. Đặc biệt, **Rollback**, **Revert**, **Reset** và **Discard** có thể mang ý nghĩa khác nhau tùy IDE.

## 16. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không thấy nút Stage | File đang ở trạng thái staged, untracked hoặc công cụ đang hiển thị nhóm khác | Kiểm tra nhóm Changes, Staged Changes và trạng thái file |
| Commit không có nội dung mong muốn | Chưa stage file hoặc stage nhầm hunk | Xem <code>git diff --staged</code> trước commit |
| Publish Branch bị từ chối | Không có quyền push hoặc remote branch đã tồn tại với lịch sử khác | Kiểm tra remote, quyền và tên branch; không force push khi chưa rõ |
| Không thấy Publish sau khi tạo branch | Công cụ đã thiết lập upstream hoặc branch đã được publish | Kiểm tra <code>git branch -vv</code> |
| Sync yêu cầu commit/stash | Working tree có thay đổi chưa commit hoặc index chưa sạch | Kiểm tra diff, commit hoặc stash phần cần giữ |
| Sync báo non-fast-forward | Remote có commit mới hoặc lịch sử đã phân kỳ | Fetch, xem lịch sử và tích hợp bằng merge/rebase theo quy ước nhóm |
| Sync phát sinh conflict | Hai phía sửa cùng vùng hoặc file | Mở merge editor, giải quyết, stage và tiếp tục đúng tiến trình |
| Discard làm mất nội dung | Đã xác nhận bỏ thay đổi chưa lưu | Kiểm tra Local History, editor history, stash hoặc bản sao nếu công cụ có hỗ trợ; không đảm bảo luôn khôi phục được |
| File mới không xuất hiện trong Changes | File bị ignore hoặc đang nằm ngoài repository | Kiểm tra <code>git status --ignored</code> và quy tắc ignore |
| Đã push nhưng đồng đội chưa thấy branch | Push đến remote khác hoặc quyền/nhánh đích không đúng | Kiểm tra <code>git remote -v</code> và <code>git branch -vv</code> |

## 17. Checklist trước khi bấm nút

Trước khi **Stage**:

- Đọc diff và xác nhận đúng file.
- Kiểm tra không stage nhầm secret, log, file build hoặc thay đổi không liên quan.
- Nếu cần, stage từng hunk thay vì toàn bộ file.

Trước khi **Publish Branch**:

- Xác nhận branch hiện tại.
- Xác nhận remote đích và quyền push.
- Kiểm tra tên branch không trùng với branch khác có ý nghĩa khác.
- Xem commit nào sẽ được gửi lên remote.

Trước khi **Sync**:

- Xác nhận branch và upstream.
- Kiểm tra thay đổi chưa commit.
- Xem số commit ahead/behind và fetch nếu thông tin đã cũ.
- Biết nhóm đang dùng merge hay rebase.
- Chuẩn bị xử lý conflict nếu lịch sử đã phân kỳ.

Trước khi **Discard**:

- Xem diff của file hoặc hunk.
- Xác nhận nội dung đó không cần giữ.
- Nếu còn phân vân, stash hoặc tạo bản sao trước.
- Với file untracked, kiểm tra chính xác đường dẫn sẽ bị xóa.

## 18. Bài tập tự kiểm tra

Thực hành trong repository thử nghiệm:

1. Sửa hai file, stage một file và dùng <code>git status</code> để quan sát khác biệt.
2. Stage một hunk trong file có hai thay đổi độc lập.
3. Unstage file và xác nhận nội dung working tree vẫn còn.
4. Commit thay đổi đã stage và xác nhận commit chỉ chứa nội dung mong muốn.
5. Tạo branch mới, publish branch và kiểm tra upstream bằng <code>git branch -vv</code>.
6. Tạo một commit local rồi push; phân biệt Publish Branch với Push ở lần sau.
7. Tạo commit trên remote từ một clone khác, sau đó sync và quan sát pull tích hợp commit ra sao.
8. Tạo conflict có chủ đích trong repository thử nghiệm, giải quyết bằng merge editor rồi tiếp tục merge hoặc rebase.
9. Tạo một file untracked, xem cách công cụ hiển thị và kiểm tra dry-run trước khi xóa bằng Git.
10. Giải thích vì sao discard thay đổi chưa commit khác với revert commit đã chia sẻ.

Stage, publish, sync và discard là các thao tác nhỏ trong giao diện nhưng đại diện cho những thay đổi trạng thái khác nhau của Git. Khi kiểm tra index, branch, upstream và diff trước khi bấm, bạn có thể dùng IDE nhanh hơn mà vẫn kiểm soát được nội dung commit, dữ liệu gửi lên remote và thay đổi bị loại bỏ.
