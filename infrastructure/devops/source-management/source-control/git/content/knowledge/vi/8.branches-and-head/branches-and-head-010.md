# Xóa nhánh an toàn và ý nghĩa của -d so với -D

Branch trong Git là một ref trỏ đến commit đầu nhánh. Khi một nhánh feature đã được tích hợp, bạn thường xóa branch để danh sách nhánh gọn hơn. Lệnh `git branch -d` là lựa chọn an toàn vì Git kiểm tra branch đã được merge vào nơi tham chiếu phù hợp hay chưa. Tùy chọn `-D` buộc xóa branch ngay cả khi Git phát hiện commit chưa được merge.

Khác biệt này rất quan trọng: xóa branch chỉ xóa ref mang tên branch, không lập tức xóa các commit mà branch từng trỏ tới. Tuy vậy, nếu commit chỉ còn được giữ bởi branch vừa xóa, chúng có thể trở thành unreachable và cuối cùng bị dọn bởi garbage collection. Hãy xác minh lịch sử và lưu branch/tag cứu hộ trước khi dùng thao tác force.

## 1. Branch là ref trỏ đến commit

Một branch local như `feature/payment` thường được lưu dưới ref `refs/heads/feature/payment`. Ref này trỏ đến commit đầu nhánh. Khi tạo commit mới trên branch, Git cập nhật ref để trỏ đến commit mới.

Ví dụ:

```text
A---B---C---D  main
     \
      E---F    feature/payment
```

Trong ví dụ, `main` trỏ đến D và `feature/payment` trỏ đến F. Các commit A và B là lịch sử chung; E và F chỉ reachable từ feature nếu không có ref khác giữ chúng.

Khi xóa `feature/payment`, Git gỡ ref trỏ đến F. Các object commit E và F chưa nhất thiết bị xóa ngay; chúng có thể vẫn được giữ bởi reflog, tag, branch khác hoặc ref khác. Nếu không còn đường tham chiếu nào giữ chúng, chúng có thể bị thu gom sau này.

Xem branch local:

```bash
git branch
git branch -vv
```

`git branch` liệt kê branch local và đánh dấu branch hiện tại bằng `*`. `-vv` bổ sung upstream và trạng thái ahead/behind theo dữ liệu remote-tracking hiện có.

## 2. Xóa nhánh an toàn bằng git branch -d

Cú pháp:

```bash
git branch -d <branch-name>
```

Ví dụ:

```bash
git branch -d feature/payment
```

`-d` là viết tắt của `--delete`. Git chỉ xóa branch nếu tip của branch đã được merge đầy đủ vào upstream của branch đó. Nếu branch không cấu hình upstream, Git kiểm tra branch đã được merge vào `HEAD` hiện tại hay chưa.

Nếu điều kiện đạt, Git xóa ref branch. Nếu còn commit chưa được merge theo tiêu chí đó, Git từ chối và báo branch chưa được merge. Đây là cơ chế bảo vệ để bạn không vô tình bỏ mất tham chiếu cuối cùng tới các commit đang làm dở.

Ví dụ khi feature đã được merge vào `main`:

```bash
git switch main
git branch --merged main
git branch -d feature/payment
```

Chuyển sang `main` trước khi xóa feature cũng giúp bạn không cố xóa branch đang checkout. Lệnh `git branch -d` không xóa file trong working tree của branch hiện tại; nó xóa ref branch được chỉ định sau khi kiểm tra điều kiện merge.

## 3. -d kiểm tra đã merge vào đâu?

Một điểm dễ nhầm là `git branch -d feature` không phải lúc nào cũng chỉ kiểm tra branch hiện tại. Git dùng upstream được cấu hình cho branch cần xóa; nếu branch không có upstream, Git dùng `HEAD` hiện tại.

Ví dụ branch local `feature/payment` theo dõi `origin/feature/payment`. Khi xóa bằng `git branch -d feature/payment`, Git kiểm tra commit của feature đã reachable từ upstream `origin/feature/payment` hay chưa. Nếu không có upstream, nó kiểm tra reachable từ `HEAD`.

Xem upstream:

```bash
git branch -vv
git config --get branch.feature/payment.remote
git config --get branch.feature/payment.merge
```

Hai lệnh `git config` minh họa nơi cấu hình remote và nhánh upstream cho branch. Nếu branch chưa có upstream, lệnh có thể không trả kết quả.

Vì upstream thường là remote-tracking ref local, hãy fetch trước khi dựa vào trạng thái mới nhất của remote:

```bash
git fetch --all --prune
git branch -vv
```

Nếu upstream đã bị xóa trên remote và remote-tracking ref đã được prune, branch local có thể không còn upstream hợp lệ. Trong trường hợp đó, hãy xác định rõ commit đích cần kiểm tra và dùng `git branch --merged <target>` hoặc `git merge-base --is-ancestor` để xác minh.

## 4. Xem những nhánh đã merge bằng --merged

Trước khi xóa, hãy liệt kê các branch đã được merge vào một commit cụ thể:

```bash
git branch --merged main
```

Lệnh hiển thị các branch có tip reachable từ `main`. Không truyền revision thì Git mặc định dùng `HEAD` hiện tại:

```bash
git branch --merged
```

Chỉ hiển thị branch chưa được merge vào mốc đã chọn:

```bash
git branch --no-merged main
```

Các lệnh này hữu ích để rà soát trước khi dọn branch. Hãy đọc tên từng branch và kiểm tra quy ước của nhóm trước khi xóa; branch release, branch bảo trì hoặc branch dùng để lưu mốc quan trọng có thể cần giữ lại dù đã merge.

Ví dụ quy trình:

```bash
git fetch origin
git branch --merged main
git branch --no-merged main
```

Nếu `main` là đích tích hợp của nhóm, danh sách `--merged main` cho biết các branch local đã có tip reachable từ `main`. Tuy nhiên, tiêu chí này không chứng minh rằng mọi thay đổi từng có trên branch đã được giữ nguyên về mặt nội dung nếu nhóm dùng squash merge hoặc cherry-pick.

## 5. Kiểm tra quan hệ tổ tiên bằng merge-base

Bạn có thể kiểm tra một branch có phải tổ tiên của branch đích hay không:

```bash
git merge-base --is-ancestor feature/payment main
```

Mã thoát `0` nghĩa là tip của `feature/payment` là tổ tiên của `main`, tức commit đó đã reachable từ `main`. Mã thoát khác `0` nghĩa là điều kiện tổ tiên không đúng (hoặc có lỗi cần xem xét).

Đây là phép kiểm tra rõ ràng khi muốn xác nhận branch đã được tích hợp theo quan hệ commit ancestry:

```bash
if git merge-base --is-ancestor feature/payment main; then
    echo "feature/payment is merged into main"
else
    echo "feature/payment is not an ancestor of main"
fi
```

Trên PowerShell, bạn có thể kiểm tra `$LASTEXITCODE` sau lệnh Git để biết kết quả. Đừng chỉ nhìn thông báo merge trên giao diện hosting; hãy hiểu branch đích nào đang được dùng làm tiêu chí.

## 6. Vì sao git branch -d có thể từ chối sau squash merge hoặc cherry-pick?

`git branch -d` kiểm tra quan hệ reachable trong đồ thị commit. Nó không so sánh nội dung patch để suy luận rằng thay đổi đã được tích hợp bằng cách khác.

### Squash merge

Khi dùng squash merge, nền tảng hoặc lệnh Git tạo một commit mới chứa tổng thay đổi của feature nhưng không giữ các commit gốc của feature làm tổ tiên của commit mới.

```text
          F1---F2  feature
         /
A---B---S        main
```

`S` chứa nội dung gộp từ F1 và F2, nhưng F1 và F2 không phải tổ tiên của S. Vì vậy `git branch -d feature` có thể từ chối dù pull request đã được squash merge thành công.

### Cherry-pick

Cherry-pick tạo commit mới trên branch đích. Commit mới có thể chứa patch tương đương với commit nguồn nhưng có parent và OID khác. Commit nguồn không tự trở thành tổ tiên của branch đích.

### Rebase

Rebase tạo lại commit trên nền mới. Các commit cũ có thể không còn reachable từ branch đích vì commit mới có OID khác. Tùy hướng rebase và branch nào được giữ, `-d` có thể vẫn từ chối.

Trong các trường hợp này, không nên lập tức chuyển sang `-D`. Trước tiên, xác minh thay đổi đã được tích hợp thực sự bằng pull request, patch, test hoặc `git log --cherry`/`git range-diff` khi phù hợp. Nếu xác nhận branch cũ không còn cần thiết và commit cần giữ đã có ở nơi khác, mới cân nhắc force delete.

## 7. Xóa cưỡng bức bằng git branch -D

Cú pháp:

```bash
git branch -D <branch-name>
```

`-D` là cách viết tắt của `--delete --force`. Nó yêu cầu Git xóa branch ngay cả khi branch chưa được merge theo kiểm tra an toàn của `-d`.

Ví dụ:

```bash
git branch -D experiment/old-parser
```

Lệnh này hữu ích khi bạn chủ động bỏ một nhánh thử nghiệm hoặc đã xác minh rằng các commit chưa merge không còn cần thiết. Nhưng `-D` không xác nhận nội dung branch đã được tích hợp và không tạo backup cho các commit riêng.

Trước khi dùng `-D`, kiểm tra các commit chỉ có trên branch:

```bash
git log --oneline main..experiment/old-parser
git log --graph --oneline --decorate main...experiment/old-parser
git branch -vv
```

Nếu có commit quan trọng, tạo ref cứu hộ trước:

```bash
git branch rescue/old-parser experiment/old-parser
```

Sau đó mới xóa branch gốc nếu vẫn cần:

```bash
git branch -D experiment/old-parser
```

Branch `rescue/old-parser` tiếp tục giữ các commit có thể chưa reachable từ nơi khác. Hãy đặt tên cứu hộ rõ ràng và xóa nó sau khi đã xác nhận không còn cần phục hồi.

## 8. Xóa branch hiện tại và branch đang dùng ở worktree khác

Git không cho xóa branch mà `HEAD` của worktree hiện tại đang checkout. Hãy chuyển sang branch khác trước:

```bash
git switch main
git branch -d feature/payment
```

Với linked worktree, một branch có thể đang được checkout ở worktree khác. Kiểm tra danh sách:

```bash
git worktree list
```

Nếu branch cần xóa đang được sử dụng trong một worktree khác, hãy chuyển worktree đó sang branch khác hoặc gỡ worktree theo quy trình phù hợp trước khi xóa branch. Không nên cố xóa ref khi còn một working tree đang dựa vào branch đó; `-D` không phải cách xử lý thay cho việc giải phóng worktree đang sử dụng.

Nếu worktree phụ không còn cần thiết, từ repository chính:

```bash
git worktree remove ../storefront-feature
```

Chỉ dùng `git worktree remove` khi đã xác nhận đường dẫn đúng và thay đổi trong worktree đó đã được lưu. Sau đó kiểm tra lại `git worktree list` rồi mới xóa branch.

## 9. Xóa nhiều branch local một cách có kiểm soát

Bạn có thể truyền nhiều tên branch cho một lệnh:

```bash
git branch -d feature/search feature/payment feature/profile
```

Git sẽ kiểm tra điều kiện an toàn cho từng branch. Nếu branch nào chưa được merge, lệnh có thể báo lỗi cho branch đó; hãy xem thông báo và kiểm tra riêng thay vì đổi tất cả sang `-D`.

Để rà soát các branch đã merge vào main:

```bash
git branch --merged main
```

Sau đó chọn rõ các branch feature cần xóa. Tránh chạy lệnh xóa dựa trên wildcard hoặc pipeline chưa xem trước, đặc biệt trong repository có branch release, maintenance hoặc branch của người khác.

Nếu muốn loại branch hiện tại và các branch nền tảng khỏi danh sách ứng viên, hãy đọc output và thực hiện từng tên branch rõ ràng. Tên branch có thể chứa dấu `/`; Git xem đó là thành phần của tên ref chứ không phải thư mục làm việc.

## 10. Xóa remote-tracking branch khác với xóa branch trên server

Branch local và remote-tracking branch là hai ref khác nhau. Ví dụ:

- `feature/payment`: branch local trong `refs/heads/`.
- `origin/feature/payment`: remote-tracking ref local trong `refs/remotes/origin/` ghi nhận trạng thái remote gần nhất.

Xóa remote-tracking ref local:

```bash
git branch -dr origin/feature/payment
```

Hoặc:

```bash
git branch -d -r origin/feature/payment
```

Thao tác này chỉ xóa ref remote-tracking trong clone hiện tại. Nó không gửi yêu cầu xóa branch trên server.

Để xóa branch thật trên remote:

```bash
git push origin --delete feature/payment
```

Sau khi branch bị xóa trên server, cập nhật và dọn remote-tracking refs trong clone:

```bash
git fetch --prune origin
```

`git remote prune origin` cũng có thể dọn remote-tracking refs không còn được remote công bố, nhưng không xóa branch local trong `refs/heads/`.

## 11. Xóa branch có làm mất commit không?

Xóa branch là xóa tên ref, không phải lệnh xóa trực tiếp từng commit object. Sau khi xóa, commit có thể vẫn được giữ bởi:

- Branch khác hoặc tag trỏ đến commit đó.
- Branch cứu hộ bạn vừa tạo.
- Reflog ghi lại vị trí ref từng trỏ tới, trong thời hạn lưu reflog.
- Ref khác hoặc object được tham chiếu từ lịch sử reachable.

Nếu không còn ref hoặc nguồn giữ nào, commit có thể trở thành unreachable. Git không nhất thiết xóa object ngay; garbage collection sẽ thu gom object theo chính sách và thời gian ân hạn. Tuy nhiên, không nên dựa vào reflog hoặc thời gian ân hạn như một bản backup lâu dài.

Nếu lỡ xóa branch và cần tìm lại commit, có thể xem reflog:

```bash
git reflog --all --date=local
```

Khi tìm được OID cần giữ, tạo lại branch:

```bash
git branch rescue/recovered-work <COMMIT_ID>
```

Khả năng phục hồi phụ thuộc object còn trong repository và chưa bị dọn. Nếu commit quan trọng, hãy tạo ref cứu hộ hoặc tag trước khi xóa branch.

## 12. Quy trình xóa branch an toàn

Trước khi xóa một branch feature, thực hiện theo thứ tự:

**Bước 1: Xác định branch và trạng thái làm việc**

```bash
git status --short
git branch -vv
git worktree list
```

Đảm bảo bạn đang ở đúng repository, branch mục tiêu không phải branch đang checkout và không bị worktree khác sử dụng.

**Bước 2: Cập nhật thông tin remote**

```bash
git fetch --all --prune
```

Điều này cập nhật remote-tracking refs trước khi kiểm tra upstream và lịch sử.

**Bước 3: Xem commit riêng của branch**

```bash
git log --oneline main..feature/payment
git log --graph --oneline --decorate main...feature/payment
```

Nếu có commit riêng, xác định chúng đã được tích hợp qua merge commit, squash merge hay cherry-pick chưa.

**Bước 4: Kiểm tra merge status**

```bash
git branch --merged main
git branch --no-merged main
git merge-base --is-ancestor feature/payment main
```

Chú ý: `--merged main` kiểm tra khả năng reachable từ `main`; còn `git branch -d` sử dụng upstream của branch hoặc `HEAD` nếu không có upstream. Hãy bảo đảm mốc kiểm tra phù hợp với mục đích xóa.

**Bước 5: Lưu commit cần giữ**

Nếu còn commit riêng có giá trị, tạo branch hoặc tag cứu hộ:

```bash
git branch rescue/payment-before-delete feature/payment
```

**Bước 6: Xóa bằng -d hoặc -D**

Nếu branch đã merge theo tiêu chí của Git:

```bash
git branch -d feature/payment
```

Chỉ khi đã xác minh các commit chưa merge không còn cần thiết hoặc đã được lưu ở nơi khác:

```bash
git branch -D experiment/old-parser
```

**Bước 7: Xác nhận**

```bash
git branch --list
git branch -vv
git log --oneline --decorate -5
```

Kiểm tra branch mục tiêu đã biến mất và branch chính vẫn trỏ đến commit mong muốn.

## 13. Các tình huống thường gặp

### Branch đã merge bằng merge commit

Nếu tip feature là tổ tiên của branch đích, `git branch -d` thường xóa được sau khi branch được kiểm tra theo upstream hoặc `HEAD`. Xác minh bằng `git merge-base --is-ancestor`.

### Pull request đã squash merge nhưng -d từ chối

Git có thể không xem commit gốc của feature là tổ tiên của main. Xác minh pull request đã merge, kiểm tra patch đã có trong main và lưu commit nếu cần. Sau đó mới cân nhắc `git branch -D`.

### Branch chưa merge nhưng đã lỗi thời

Xem các commit riêng bằng `git log main..branch`. Nếu đó là thử nghiệm bỏ dở, không cần giữ, bạn có thể dùng `-D` sau khi xác nhận không có nội dung cần cứu hộ. Nếu chưa chắc, tạo branch cứu hộ trước.

### Git báo branch đang được dùng ở worktree khác

Chạy `git worktree list`, chuyển branch hoặc gỡ worktree phụ theo đúng quy trình. Xóa branch sau khi không còn worktree nào checkout nó.

### Muốn xóa branch trên GitHub/GitLab hoặc server

`git branch -d` chỉ xóa branch local. Dùng `git push <remote> --delete <branch>` để gửi yêu cầu xóa branch remote, sau đó fetch/prune để cập nhật clone.

## 14. Bài tập thực hành

Trong repository thử nghiệm, tạo các branch sau từ `main`:

- `feature/merged`: có một commit và được merge vào `main` bằng merge commit.
- `feature/squashed`: có một commit được đưa vào `main` bằng squash merge hoặc mô phỏng bằng một commit mới chứa cùng thay đổi.
- `experiment/unmerged`: có ít nhất hai commit riêng chưa được tích hợp.

Thực hiện:

1. Chạy `git branch --merged main` và `git branch --no-merged main`; xác định branch nào xuất hiện trong từng danh sách.
2. Dùng `git merge-base --is-ancestor feature/merged main` để xác nhận quan hệ tổ tiên.
3. Thử `git branch -d feature/merged`; quan sát branch đã merge được xóa.
4. Thử `git branch -d feature/squashed`; giải thích vì sao Git có thể từ chối dù nội dung đã được squash vào main.
5. Dùng `git log main..experiment/unmerged` để liệt kê commit chưa được tích hợp.
6. Tạo branch cứu hộ `rescue/experiment` trỏ đến `experiment/unmerged`, sau đó dùng `git branch -D experiment/unmerged` trong repository thử nghiệm.
7. Xác nhận commit vẫn reachable qua branch cứu hộ và giải thích vì sao xóa branch không lập tức xóa object.
8. Tạo remote bare thử nghiệm, push branch lên remote, rồi phân biệt `git branch -dr origin/feature/demo` với `git push origin --delete feature/demo`.
9. Dùng `git worktree add` tạo worktree phụ checkout một branch, thử xóa branch đang được dùng và quan sát Git bảo vệ ref; sau đó giải phóng worktree và xóa branch theo quy trình.

Bạn hoàn thành bài tập khi giải thích được điều kiện an toàn của `-d`, rủi ro của `-D`, phân biệt xóa branch local với remote-tracking/remote branch và biết cách giữ commit quan trọng trước khi xóa ref.
