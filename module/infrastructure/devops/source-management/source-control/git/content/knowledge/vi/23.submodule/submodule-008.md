# Phát hiện submodule bẩn, commit chưa công bố và xung đột gitlink

Khi làm việc với Git submodule, kho cha (superproject) chỉ ghi nhận commit cụ thể mà mỗi submodule đang được ghim. Những file được sửa bên trong submodule thuộc working tree của repository con; các commit mới cũng thuộc lịch sử của repository con. Vì vậy, một dòng `modified: libs/shared-utils` trong kho cha có thể biểu thị nhiều tình huống khác nhau: file con bị sửa, có file chưa được theo dõi, submodule đang ở commit khác với gitlink đã ghi nhận, hoặc có xung đột khi hai nhánh kho cha chọn hai commit con khác nhau.

Cần phân biệt các trạng thái này trước khi commit, chuyển nhánh hoặc hoàn tất merge/rebase. Nếu chỉ stage đường dẫn submodule ở kho cha mà chưa xử lý nội dung trong repository con, thay đổi file con có thể vẫn chưa được lưu thành commit. Ngược lại, nếu commit của submodule chưa được push tới remote mà đồng đội có thể truy cập, họ có thể nhận được gitlink nhưng không tải được commit được tham chiếu.

## 1. Ba loại trạng thái cần phân biệt

Có ba nhóm vấn đề thường gặp:

| Trạng thái | Điều gì đã thay đổi? | Nơi cần xử lý |
|---|---|---|
| Submodule bẩn (dirty) | File tracked bị sửa hoặc có file untracked bên trong submodule | Working tree/index của repository con |
| Commit chưa công bố | Submodule có commit local chưa được đẩy lên remote mà nhóm sử dụng | Branch/ref và remote của repository con |
| Xung đột gitlink | Hai phía của superproject yêu cầu hai commit khác nhau cho cùng một submodule | Index của superproject và lịch sử repository con |

Ba trạng thái có thể cùng xuất hiện. Ví dụ, bạn sửa file trong submodule, commit trên branch local nhưng chưa push, rồi đồng đội đồng thời cập nhật gitlink ở nhánh khác của superproject. Khi merge, kho cha có thể báo xung đột gitlink trong khi repository con vẫn còn commit chưa công bố hoặc file chưa commit.

Hãy kiểm tra từng repository theo đúng phạm vi. Lệnh chạy trong superproject cho biết trạng thái gitlink; lệnh chạy bên trong submodule cho biết trạng thái file và commit của repository con.

## 2. Phát hiện submodule bẩn từ kho cha

Bắt đầu bằng trạng thái tổng thể:

```bash
git status
git status --short --ignore-submodules=none
```

Tùy trạng thái bên trong submodule, Git có thể hiển thị những mô tả như:

- `modified content`: có nội dung file tracked bên trong submodule thay đổi.
- `untracked content`: có file chưa được theo dõi bên trong submodule.
- `new commits`: HEAD của submodule khác commit mà superproject đang ghi nhận.

Nếu cấu hình ignore submodule đang che một số thay đổi, `--ignore-submodules=none` yêu cầu lệnh status xét tất cả thay đổi. Đây là lựa chọn hữu ích khi cần chẩn đoán thay vì chỉ xem trạng thái đã được lọc.

Kiểm tra cấu hình ignore của từng submodule nếu trạng thái có vẻ không đầy đủ:

```bash
git config -f .gitmodules --get-regexp '^submodule\..*\.ignore$'
git config --show-origin --get-regexp '^submodule\..*\.ignore$'
```

Các giá trị thường gặp là `none` (xét cả file tracked và untracked), `untracked` (bỏ qua file untracked), `dirty` (bỏ qua thay đổi trong working tree nhưng vẫn có thể báo commit pointer khác) và `all` (bỏ qua mọi thay đổi submodule trong status/diff). Cấu hình local trong `.git/config` có thể ghi đè giá trị từ `.gitmodules`; dùng `--ignore-submodules=none` khi cần buộc status hiển thị thay đổi.

Để xem trạng thái commit được ghim và trạng thái khởi tạo:

```bash
git submodule status --recursive
```

Ký hiệu đầu dòng thường có ý nghĩa:

| Ký hiệu | Ý nghĩa |
|---|---|
| Dấu cách | Submodule đang ở commit được superproject ghi nhận |
| `-` | Submodule chưa được khởi tạo |
| `+` | HEAD hiện tại khác commit được superproject ghi nhận |
| `U` | Gitlink đang có xung đột chưa được giải quyết |

Lệnh này hữu ích để kiểm tra commit pointer, nhưng không thay thế `git status` bên trong từng submodule để phát hiện file đã sửa hoặc untracked.

Có thể xem thay đổi commit của submodule theo dạng log:

```bash
git diff --submodule=log
git diff --cached --submodule=log
```

Lệnh đầu xem khác biệt gitlink chưa stage; lệnh thứ hai xem khác biệt đã stage trong index của superproject. Các lệnh này giúp biết những commit con nào đã được thêm hoặc bỏ giữa hai mốc.

## 3. Kiểm tra chi tiết bên trong từng submodule

Dùng `git -C` để chạy lệnh trong repository con mà không cần chuyển terminal:

```bash
git -C libs/shared-utils status
git -C libs/shared-utils status --short --untracked-files=all
git -C libs/shared-utils branch -vv
git -C libs/shared-utils log --oneline --decorate -8
```

Các lệnh trả lời những câu hỏi khác nhau:

- `status`: có file modified, staged hoặc untracked hay không?
- `status --short --untracked-files=all`: liệt kê cụ thể từng file, kể cả file untracked nằm sâu trong thư mục.
- `branch -vv`: branch hiện tại đang theo dõi remote-tracking branch nào và có ahead/behind hay không?
- `log`: các commit gần nhất mà HEAD của submodule đang trỏ tới là gì?

Nếu repository có nhiều submodule, có thể chạy status trong tất cả submodule đã được khởi tạo:

```bash
git submodule foreach --recursive 'git status --short --branch'
```

Lệnh `foreach` chạy câu lệnh trong từng submodule; `--recursive` đi tiếp vào các submodule lồng nhau. Nó không tự khởi tạo những submodule chưa được init. Nếu cần kiểm tra một submodule cụ thể, dùng `git -C <path>` để giới hạn phạm vi.

Một lưu ý quan trọng: superproject không lưu các thay đổi file bên trong submodule. Nó chỉ lưu gitlink tới commit con. Do đó, `git add libs/shared-utils` ở kho cha không stage từng file đã sửa trong `libs/shared-utils`; các file đó phải được xử lý trong repository con trước.

## 4. Phân biệt file đã sửa, file untracked và commit mới

Ví dụ trạng thái trong submodule:

```text
 M src/parser.java
?? tmp/debug-output.txt
```

- `M` cho biết file tracked đã sửa.
- `??` cho biết file chưa được theo dõi.

Nếu có commit local mới, `git status` có thể sạch dù superproject vẫn báo submodule có `new commits`. Đây không phải file dirty; đó là HEAD của repository con đã tiến tới commit khác với gitlink.

Ví dụ:

```text
Superproject expects:  a1b2c3d
Submodule HEAD:        e4f5a6b
```

Có thể xem commit pointer mà superproject ghi nhận:

```bash
git ls-tree HEAD libs/shared-utils
git ls-files --stage -- libs/shared-utils
```

`git ls-tree` xem gitlink trong commit hiện tại của kho cha; `git ls-files --stage` xem mục tương ứng trong index. Với gitlink, mode thường là `160000`.

Để so sánh commit đang checkout bên trong submodule:

```bash
git -C libs/shared-utils rev-parse HEAD
git -C libs/shared-utils status --short
```

Nếu HEAD khác gitlink nhưng repository con không có file sửa, thay đổi ở kho cha có thể đơn giản là cập nhật phiên bản dependency. Nếu file bên trong còn dirty, cần xử lý những file đó trước khi quyết định có ghi nhận commit pointer mới hay không.

## 5. Phát hiện commit submodule chưa được công bố

Commit local chưa được công bố là commit chưa có trên remote mà nhóm dự định sử dụng để lấy submodule. Trước tiên, cập nhật remote-tracking refs trong repository con:

```bash
git -C libs/shared-utils fetch --all --prune
```

Lệnh fetch chỉ cập nhật thông tin remote-tracking và object trong repository con; nó không tự thay đổi working tree hoặc gitlink của superproject.

Kiểm tra branch và upstream:

```bash
git -C libs/shared-utils branch -vv
```

Nếu branch hiện tại có upstream, xem các commit local chưa có ở upstream:

```bash
git -C libs/shared-utils log --oneline '@{upstream}..HEAD'
```

Mỗi commit được liệt kê là reachable từ HEAD nhưng không reachable từ upstream được chỉ định. Nếu không có upstream, Git không thể tự suy ra branch remote mà bạn muốn dùng để công bố; hãy xác định đúng remote và branch trước khi so sánh.

Có thể xem số commit ahead/behind:

```bash
git -C libs/shared-utils rev-list --left-right --count '@{upstream}...HEAD'
```

Số thứ nhất là commit chỉ có ở upstream (local đang behind); số thứ hai là commit chỉ có ở HEAD (local đang ahead). Kết quả `0 2` nghĩa là branch local có hai commit chưa có trong upstream và không thiếu commit nào so với upstream.

Nếu muốn xem các commit reachable từ HEAD nhưng chưa reachable từ bất kỳ remote-tracking branch nào:

```bash
git -C libs/shared-utils log --oneline HEAD --not --remotes
```

Đây là phép kiểm tra rộng; commit có thể đã tồn tại ở một remote khác hoặc branch khác mà nhóm không dùng. Vì vậy, khi nói “chưa công bố”, hãy xác định remote/branch đích cụ thể, không chỉ dựa vào việc commit có xuất hiện trong một remote-tracking ref bất kỳ hay không.

Để xem remote branch nào đã chứa một commit cụ thể:

```bash
git -C libs/shared-utils branch -r --contains <commit-oid>
```

Nếu không có branch nào được liệt kê, commit hiện không reachable từ các remote-tracking branch đã fetch. Điều đó vẫn chưa chứng minh commit không tồn tại trên mọi server hoặc ref ẩn; hãy kiểm tra đúng remote mà nhóm dùng.

Nếu cần kiểm tra khả năng push mà chưa cập nhật remote, có thể dùng `git push --dry-run` với remote và refspec rõ ràng. Ví dụ:

```bash
git -C libs/shared-utils push --dry-run origin HEAD:refs/heads/fix/parser-edge-case
```

Dry-run giúp kiểm tra thao tác dự kiến, nhưng không thay thế việc xác nhận commit có được đồng đội truy cập qua đúng remote/branch hay không.

## 6. Xử lý submodule bẩn trước khi chuyển nhánh hoặc commit kho cha

Nếu file bên trong submodule đã sửa, hãy quyết định giữ, commit, stash hoặc loại bỏ thay đổi trong chính repository con.

**Nếu thay đổi cần được giữ và chia sẻ**, commit trong submodule:

Trước khi chuyển branch, kiểm tra và bảo toàn mọi thay đổi đang có. Nếu branch làm việc chưa tồn tại, tạo branch mới; nếu đã tồn tại, chuyển sang branch đó.

```bash
git -C libs/shared-utils status
# Chỉ chạy lệnh này nếu branch chưa tồn tại
git -C libs/shared-utils switch -c fix/parser-edge-case
git -C libs/shared-utils add src/parser.java
git -C libs/shared-utils commit -m "Fix parser edge case"
```

Sau đó push commit con lên remote dùng chung:

```bash
git -C libs/shared-utils push -u origin fix/parser-edge-case
```

Cuối cùng, quay lại superproject và ghi nhận gitlink mới:

```bash
git add -- libs/shared-utils
git diff --cached --submodule=log
git status
```

**Nếu thay đổi chưa sẵn sàng commit**, có thể stash bên trong submodule:

```bash
git -C libs/shared-utils stash push -u -m "WIP before switching task"
```

Tùy chọn `-u` đưa cả file untracked vào stash. Nó không bao gồm file ignored; nếu cần bảo toàn cả file ignored, hãy xem xét kỹ trước khi dùng `-a`. Sau đó xác minh:

```bash
git -C libs/shared-utils status
git -C libs/shared-utils stash list
```

Khi cần phục hồi:

```bash
git -C libs/shared-utils stash pop
```

Nếu muốn giữ stash cho tới khi đã kiểm tra kết quả, dùng `git stash apply` trước rồi xóa stash sau. Nếu có xung đột khi khôi phục, xử lý trong repository con như một conflict thông thường.

**Nếu file không cần giữ**, chỉ xóa sau khi xác minh đúng đường dẫn và nội dung. Tránh chạy `git reset --hard` hoặc `git clean -fdx` một cách máy móc trong submodule: các lệnh đó có thể xóa thay đổi local, file untracked hoặc file ignored mà bạn vẫn cần.

## 7. Vì sao superproject phát sinh xung đột gitlink?

Gitlink là một mục trong tree/index của kho cha trỏ tới commit của submodule. Khi hai nhánh superproject cùng thay đổi gitlink của một đường dẫn sang hai commit khác nhau, merge có thể không tự chọn được phiên bản.

Ví dụ, hai nhánh bắt đầu từ gitlink `S0`:

```text
                  S1  (nhánh feature)
                 /
Superproject: A
                 \
                  S2  (nhánh release)

S0 = commit submodule chung trước khi tách nhánh
```

Nhánh feature cập nhật submodule tới `S1`; nhánh release cập nhật tới `S2`. Khi merge hai nhánh superproject, Git cần quyết định gitlink cuối cùng trỏ tới commit nào.

Nếu một commit là tổ tiên của commit còn lại, Git có thể fast-forward gitlink tới commit hậu duệ. Nếu hai phía phân kỳ, Git chỉ tự chọn được khi tìm thấy một commit merge phù hợp đã kết hợp cả hai lịch sử; nếu không, Git có thể báo:

```text
Failed to merge submodule libs/shared-utils
CONFLICT (submodule): Merge conflict in libs/shared-utils
```

Đây là xung đột ở cấp commit pointer. Git không thể tự hợp nhất file bên trong repository con chỉ bằng cách trộn hai mã commit. Bạn cần chọn một commit phù hợp hoặc tạo một commit merge trong chính submodule rồi ghi nhận gitlink mới ở kho cha.

## 8. Xác định các phía của xung đột gitlink

Trong superproject, xem trạng thái:

```bash
git status
git diff --name-only --diff-filter=U
```

Sau đó xem các stage trong index:

```bash
git ls-files -u -- libs/shared-utils
```

Kết quả có thể giống:

```text
160000 <base-oid>   1    libs/shared-utils
160000 <ours-oid>   2    libs/shared-utils
160000 <theirs-oid> 3    libs/shared-utils
```

Ý nghĩa:

| Stage | Ý nghĩa |
|---|---|
| 1 | Gitlink ở base chung trước khi hai nhánh thay đổi |
| 2 | Gitlink từ phía ours của thao tác merge |
| 3 | Gitlink từ phía theirs của thao tác merge |

Mode `160000` xác nhận đây là gitlink. Các OID là commit của repository con, không phải blob hay tree file của superproject. Vì vậy, không thể dùng `git show :2:libs/shared-utils` như khi đọc một file văn bản thông thường; hãy lấy OID từ `git ls-files -u` rồi kiểm tra commit trong repository con.

Tùy loại conflict, không phải lúc nào cũng có đủ cả stage 1, 2 và 3. Ví dụ, nếu submodule được thêm độc lập ở cả hai phía thì có thể không có base stage; nếu một phía xóa đường dẫn thì stage tương ứng có thể vắng mặt.

Có thể xem lịch sử ở mỗi phía bằng:

```bash
git -C libs/shared-utils show --no-patch --oneline <ours-oid>
git -C libs/shared-utils show --no-patch --oneline <theirs-oid>
git -C libs/shared-utils merge-base <ours-oid> <theirs-oid>
```

Nếu commit chưa có trong object database của submodule, fetch từ remote tương ứng trước. Đừng giả định mọi OID trong index của superproject đều đã được tải vào repository con local.

## 9. Giải quyết gitlink conflict bằng cách chọn một phía

Nếu nhóm đã quyết định chỉ cần một trong hai commit, có thể checkout commit được chọn trong repository con rồi stage gitlink ở kho cha.

Ví dụ chọn commit từ phía ours:

Trước khi đổi HEAD của submodule, kiểm tra working tree con. Nếu có file modified hoặc untracked cần giữ, hãy commit hoặc stash chúng trước; việc checkout một OID khác có thể bị Git từ chối hoặc làm trạng thái khó kiểm soát.

```bash
git -C libs/shared-utils fetch --all
git -C libs/shared-utils status --short
# Chỉ tiếp tục khi working tree sạch hoặc thay đổi đã được bảo toàn
git -C libs/shared-utils switch --detach <ours-oid>

# Chạy kiểm tra cần thiết trong submodule
git -C libs/shared-utils status

# Quay lại superproject và stage gitlink đã chọn
git add -- libs/shared-utils
git status
git diff --cached --submodule=log
```

Nếu chọn phía theirs, thay `<ours-oid>` bằng `<theirs-oid>`. Việc chọn một phía chỉ quyết định commit pointer cuối cùng; nó không kết hợp các commit độc lập của phía còn lại. Hãy chắc chắn thay đổi bị bỏ không cần thiết hoặc đã được tích hợp ở nơi khác.

Sau khi stage, kiểm tra `git ls-files -u -- libs/shared-utils`. Nếu không còn output cho đường dẫn đó, các stage conflict đã được thay bằng gitlink đã chọn trong index.

## 10. Giải quyết bằng merge bên trong submodule

Nếu cả hai phía đều có thay đổi cần giữ, hãy hợp nhất lịch sử trong repository con.

Trước tiên, lấy các OID từ stage 2 và stage 3 của superproject, bảo đảm các commit có mặt trong submodule và working tree con sạch:

```bash
git -C libs/shared-utils fetch --all
git -C libs/shared-utils status
```

Tạo branch giải quyết conflict từ commit ours:

```bash
git -C libs/shared-utils switch -c resolve/shared-utils-gitlink <ours-oid>
```

Merge commit theirs vào branch đó:

```bash
git -C libs/shared-utils merge <theirs-oid>
```

Nếu merge bên trong submodule phát sinh conflict ở file, giải quyết như một repository Git thông thường:

```bash
git -C libs/shared-utils status
git -C libs/shared-utils add <resolved-file>
git -C libs/shared-utils commit
```

Nếu Git tự tạo merge commit, kiểm tra lịch sử và test của submodule. Sau khi có commit kết quả, push commit đó lên remote mà các thành viên khác có thể truy cập:

```bash
git -C libs/shared-utils push -u origin resolve/shared-utils-gitlink
```

Cuối cùng, ở superproject, stage gitlink trỏ tới commit merge mới:

```bash
git add -- libs/shared-utils
git diff --cached --submodule=log
git status
```

Commit kết quả trong superproject sẽ ghi nhận gitlink mới. Khi đồng đội lấy commit superproject, họ cũng phải có quyền truy cập commit con đã được push để submodule update có thể checkout được.

Nếu hai commit không cùng lịch sử hoặc không thể merge trực tiếp, đừng tạo một commit merge giả chỉ để hết conflict. Kiểm tra remote, branch và quan hệ tổ tiên; có thể cần lấy đúng repository hoặc phối hợp với nhóm duy trì submodule.

## 11. Hoàn tất merge/rebase ở superproject

Sau khi gitlink conflict đã được giải quyết và stage, kiểm tra toàn bộ trạng thái kho cha:

```bash
git status
git diff --cached --submodule=log
git diff --name-only --diff-filter=U
```

Nếu còn file khác ở trạng thái unmerged, giải quyết chúng theo quy trình phù hợp. Khi không còn conflict, tiếp tục đúng thao tác đang dừng:

```bash
# Nếu đang merge
git merge --continue

# Nếu đang rebase
git rebase --continue

# Nếu đang cherry-pick
git cherry-pick --continue
```

Sau khi thao tác hoàn tất, kiểm tra lại:

```bash
git status
git submodule status --recursive
git diff HEAD^ HEAD --submodule=log
```

Lệnh cuối xem thay đổi gitlink trong commit vừa tạo (điều chỉnh revision nếu thao tác tạo nhiều commit). Nếu commit superproject tham chiếu tới một commit submodule mới, hãy bảo đảm commit đó đã được push lên remote con trước khi push superproject.

## 12. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `git add <submodule-path>` sẽ stage các file con đã sửa | Nó cập nhật gitlink trong superproject; file con phải được stage/commit bên trong submodule |
| Submodule báo modified nghĩa là chỉ có file bị sửa | Có thể là file dirty, untracked content hoặc HEAD khác gitlink |
| `git submodule status` không có dấu `+` nghĩa là submodule sạch | Nó chủ yếu phản ánh commit pointer/init/conflict; vẫn cần kiểm tra `git -C <path> status` |
| Commit con local là đủ để đồng đội dùng được | Commit phải có trên remote mà đồng đội truy cập được |
| Gitlink conflict là conflict văn bản | Đây là xung đột giữa các OID commit; cần chọn pointer hoặc merge lịch sử ở repository con |
| Chỉ cần stage gitlink là đã giải quyết nội dung con | Stage gitlink không commit file dirty bên trong submodule |
| `git submodule update` luôn lấy commit mới nhất | Mặc định nó checkout commit được superproject ghim; `--remote` mới chủ động theo branch remote |
| Có thể bỏ qua trạng thái dirty bằng reset/clean | Các lệnh đó có thể làm mất công việc chưa được bảo toàn |

## 13. Checklist trước khi commit hoặc push superproject

Trước khi ghi nhận thay đổi submodule trong kho cha, hãy kiểm tra:

1. Submodule có được khởi tạo không? Dùng `git submodule status --recursive`.
2. Working tree con có file tracked đã sửa hoặc file untracked không? Dùng `git -C <path> status --short --untracked-files=all`.
3. HEAD con có khác gitlink mà superproject yêu cầu không? So sánh `git ls-tree HEAD <path>` với `git -C <path> rev-parse HEAD`.
4. Commit con mới có nằm trên remote/branch mà nhóm sử dụng không? Fetch và so sánh với upstream.
5. Nếu có conflict gitlink, đã xem stage 1/2/3 bằng `git ls-files -u` chưa?
6. Nếu cần merge hai lịch sử con, merge commit đã được push lên remote chưa?
7. Staged diff của superproject có trỏ đúng commit con không? Xem `git diff --cached --submodule=log`.
8. Mọi file conflict khác trong superproject đã được giải quyết chưa?

Các bước này giúp tránh commit một gitlink trỏ tới commit chưa được chia sẻ hoặc bỏ sót thay đổi file bên trong repository con.

## Kết luận

Hãy chẩn đoán submodule ở hai cấp: superproject cho biết commit pointer và xung đột gitlink; repository con cho biết file dirty, file untracked và commit local. Dùng `git status --ignore-submodules=none`, `git submodule status`, `git submodule foreach` và `git -C <path> status` để tìm trạng thái thực. Trước khi chia sẻ gitlink mới, push commit con lên remote phù hợp. Với xung đột gitlink, xem stage 1/2/3, chọn một commit nếu chỉ cần một phía hoặc tạo merge commit trong submodule nếu cần giữ cả hai lịch sử, rồi stage gitlink và hoàn tất thao tác ở kho cha.
