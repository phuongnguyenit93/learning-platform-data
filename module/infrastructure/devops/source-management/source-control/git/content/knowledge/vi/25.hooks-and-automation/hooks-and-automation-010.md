# Ngăn hook tự sửa lịch sử hoặc tạo tác dụng phụ ngoài ý muốn

Git hook là chương trình được Git gọi tại một thời điểm trong quy trình như commit, checkout, merge, rebase hoặc push. Hook có thể kiểm tra dữ liệu, chuẩn bị thông điệp hoặc thực hiện một tác vụ tự động. Tuy nhiên, hook chạy bằng quyền của người dùng và có thể gọi các lệnh shell hoặc Git khác. Nếu script không được giới hạn rõ ràng, một thao tác tưởng như đơn giản như `git commit` có thể vô tình sửa index, thay đổi working tree, tạo commit lồng nhau, viết lại lịch sử hoặc gọi một dịch vụ bên ngoài.

Một hook an toàn cần có phạm vi nhỏ, hành vi dễ dự đoán và có thể chạy lặp lại. Với phần lớn kiểm tra trước commit, hãy ưu tiên đọc dữ liệu và báo lỗi. Nếu cần tự động sửa tệp hoặc cập nhật metadata, phải xác định chính xác dữ liệu được phép thay đổi, thông báo cho người dùng và để họ xem lại kết quả.

## 1. Hook không phải sandbox

Git gọi hook như một chương trình thông thường. Hook có thể đọc và ghi tệp, gọi lệnh hệ điều hành, chạy Git, truy cập mạng hoặc tác động đến công cụ bên ngoài nếu môi trường cho phép. Git không tự động giới hạn hook chỉ được đọc repository hay chỉ được sửa một phần dữ liệu.

Một hook có thể tạo ra nhiều loại tác dụng phụ:

| Phạm vi | Ví dụ tác dụng phụ |
|---|---|
| Working tree | Formatter ghi lại tệp, script xóa tệp tạm hoặc thay đổi cấu hình |
| Index (staging area) | `git add`, `git reset` hoặc lệnh cập nhật index làm thay đổi nội dung sẽ được commit |
| Lịch sử và refs | Tạo commit mới, amend, reset nhánh, rebase hoặc cập nhật ref |
| Repository khác | Chạy lệnh Git với nhầm `GIT_DIR`, `GIT_WORK_TREE` hoặc index của repository hiện tại |
| Hệ thống bên ngoài | Gửi thông báo, cập nhật ticket, gọi API, upload artifact hoặc triển khai ứng dụng |
| Môi trường máy | Sửa Git config, cài công cụ, thay đổi biến môi trường hoặc ghi vào thư mục dùng chung |

Hook không có cơ chế giao dịch tự động để hoàn tác tất cả các tác dụng phụ nếu một bước sau đó thất bại. Ví dụ, nếu hook đã gửi thông báo đến hệ thống bên ngoài rồi một hook khác từ chối commit, Git không thể thu hồi thông báo đó.

## 2. Nguyên tắc thiết kế hook an toàn

Trước khi viết hook, hãy xác định rõ mục đích và giới hạn của nó. Những nguyên tắc sau giúp tránh thay đổi ngoài ý muốn:

1. **Ưu tiên kiểm tra chỉ đọc:** dùng `git status`, `git diff`, `git diff --cached`, `git rev-parse` hoặc `git log` để thu thập thông tin. Không sửa dữ liệu nếu mục tiêu chỉ là xác thực.
2. **Giới hạn phạm vi:** chỉ xử lý các đường dẫn hoặc thông điệp liên quan đến thao tác hiện tại. Không quét và thay đổi toàn bộ repository khi không cần.
3. **Không tự viết lại lịch sử:** tránh `git commit`, `git commit --amend`, `git reset`, `git rebase`, `git merge`, `git cherry-pick`, `git update-ref` hoặc force-push trong hook commit thông thường.
4. **Không tự thay đổi nhánh:** tránh `git checkout`, `git switch`, xóa nhánh hoặc thay đổi HEAD khi Git đang thực hiện một thao tác khác.
5. **Không stage hàng loạt:** tránh `git add -A` hoặc `git add .` trong hook vì có thể đưa cả thay đổi không liên quan vào commit.
6. **Thiết kế có thể chạy lặp lại:** cùng một đầu vào không nên tạo ra nhiều thay đổi hoặc gửi nhiều tác động phụ không cần thiết.
7. **Thông báo rõ ràng:** nếu hook từ chối hoặc sửa nội dung, hãy nói chính xác tệp nào và lý do nào khiến thao tác bị dừng.
8. **Tách kiểm tra khỏi triển khai:** không deploy, phát hành hoặc cập nhật dịch vụ dùng chung chỉ vì một commit local vừa được tạo.

Các nguyên tắc này đặc biệt quan trọng với hook được kích hoạt tự động trong lúc merge, rebase, cherry-pick hoặc amend, vì những thao tác đó có thể gọi lại một số hook theo cách người dùng không dự đoán.

## 3. Tránh tạo commit lồng nhau và vòng lặp hook

Một lỗi nguy hiểm là gọi `git commit` từ hook được kích hoạt bởi chính lệnh `git commit`. Ví dụ, `pre-commit` chạy một script rồi script đó lại chạy `git commit`. Lệnh commit thứ hai có thể gọi `pre-commit` lần nữa, dẫn đến đệ quy hoặc tạo chuỗi commit ngoài dự kiến.

Không đặt các lệnh sau trong hook commit thông thường:

```sh
# Các ví dụ không an toàn trong hook commit
git commit -m "automatic follow-up"
git commit --amend --no-edit
git reset --hard
git rebase main
git push --force
```

Các lệnh trên có thể tạo commit lồng nhau, thay đổi HEAD, loại bỏ thay đổi trong working tree hoặc ghi đè lịch sử remote. Nếu cần một commit tự động, hãy thực hiện bằng một lệnh hoặc workflow riêng do người dùng chủ động chạy, có đầu vào và kết quả rõ ràng. Không biến hook kiểm tra thành một tác nhân tự quyết định thay đổi lịch sử.

Nếu một quy trình đặc biệt bắt buộc phải tạo commit từ automation, hãy thiết kế nó thành bước riêng, có kiểm tra trạng thái trước và sau, khóa chống chạy đồng thời, giới hạn ref đích và cơ chế review. Không dựa vào việc tự tắt hook một cách âm thầm để tránh đệ quy; việc bỏ qua hook phải được tài liệu hóa và chỉ áp dụng cho đúng lệnh cần thiết.

## 4. Bảo vệ index và working tree

Khi chạy `git commit`, nội dung trong index là phần được đưa vào commit. Working tree có thể chứa các chỉnh sửa mới hơn chưa được stage. Vì vậy, hook cần phân biệt hai vùng này.

```bash
# Nội dung đã stage, dự kiến được commit
git diff --cached

# Nội dung trong working tree chưa stage
git diff

# Trạng thái tổng quát
git status --short
```

Ví dụ, một lập trình viên stage `src/app.js`, sau đó tiếp tục sửa thêm file đó. Index chứa phiên bản thứ nhất, working tree chứa phiên bản thứ hai. Nếu hook chạy formatter trên working tree rồi không cập nhật index, commit vẫn chứa phiên bản đã stage trước formatter. Ngược lại, nếu hook gọi `git add -A`, nó có thể vô tình stage cả thay đổi khác mà người dùng chưa định commit.

### Ưu tiên formatter ở chế độ kiểm tra

Nếu công cụ hỗ trợ chế độ check, hãy dùng chế độ đó trong hook:

```sh
#!/bin/sh
set -eu

# Chỉ kiểm tra định dạng của các tệp theo quy tắc dự án.
# Công cụ phải chạy ở chế độ check và không ghi lại tệp.
npm run format:check
```

Lệnh minh họa cần được thay bằng script thực tế của dự án. Mục tiêu là báo lỗi định dạng mà không tự sửa tệp hoặc index trong lúc commit.

### Nếu cần tự động sửa định dạng

Tốt nhất cung cấp lệnh riêng như `npm run format` để người dùng chủ động chạy trước khi stage. Sau khi formatter thay đổi tệp, người dùng xem diff, stage đúng các đường dẫn và kiểm tra lại:

```bash
npm run format
git diff
git add src/app.js
git diff --cached
```

Nếu nhóm quyết định tự sửa trong hook, cần quy định rõ hook sẽ sửa working tree hay index. Chỉ cập nhật đúng những tệp đã chọn; không dùng `git add -A`. Sau khi sửa, thông báo cho người dùng và bảo đảm họ có thể xem `git diff` cùng `git diff --cached` trước khi tiếp tục.

### Không làm mất phần chưa stage

Hook không nên dùng `git checkout -- .`, `git restore .`, `git reset --hard` hoặc `git clean -fd` để tạo working tree sạch. Các lệnh này có thể xóa công việc của người dùng. Nếu một công cụ cần môi trường sạch, hãy dùng một bản clone hoặc worktree tạm riêng, rồi dọn đúng thư mục tạm do chính workflow tạo ra.

## 5. Giữ hook kiểm tra thông điệp ở phạm vi hẹp

`prepare-commit-msg` có thể sửa file thông điệp commit, còn `commit-msg` có thể kiểm tra và từ chối thông điệp. Đây là các vị trí dễ gây bất ngờ nếu hook tự viết lại nội dung người dùng vừa nhập.

Với `prepare-commit-msg`, chỉ thêm thông tin có quy tắc rõ ràng, chẳng hạn ticket ID nếu chưa có. Trước khi thêm, kiểm tra nội dung hiện tại để tránh thêm trùng khi hook được gọi lại. Không âm thầm thay thế subject hoặc xóa phần nội dung do người dùng viết.

Với `commit-msg`, ưu tiên đọc file và kiểm tra:

```sh
#!/bin/sh
set -eu

message_file=$1
subject=$(sed -n '1p' "$message_file")

if [ -z "$subject" ]; then
    echo "Commit bị từ chối: subject không được để trống."
    exit 1
fi

exit 0
```

Ví dụ này chỉ kiểm tra dòng đầu tiên và không sửa thông điệp. Nếu không đạt quy tắc, hook trả mã khác `0` để người dùng tự chỉnh sửa. Cách làm này giữ quyền quyết định nội dung ở người tạo commit.

## 6. Tránh tác dụng phụ bên ngoài trong hook local

Không nên dùng hook local để tự động triển khai production, phát hành package, gửi email cho khách hàng, thay đổi ticket trạng thái cuối cùng hoặc ghi dữ liệu không thể đảo ngược vào hệ thống bên ngoài. Hook local có thể chạy khi commit còn chưa được push, hoặc khi người dùng tạo commit tạm rồi amend/rebase lại.

Ví dụ, `post-commit` chạy sau khi commit đã được tạo trong repository local. Nó không chứng minh commit đã được push, review hay tích hợp vào nhánh chính. Nếu hook `post-commit` gọi API triển khai, ứng dụng có thể được triển khai từ một commit chưa được chia sẻ hoặc chưa qua kiểm tra.

Hãy chọn vị trí automation phù hợp:

| Mục tiêu | Vị trí phù hợp hơn |
|---|---|
| Kiểm tra nhanh mã nguồn trước commit | Client-side `pre-commit` |
| Kiểm tra quy ước thông điệp | Client-side `commit-msg` và kiểm tra lại trong CI |
| Chạy test đầy đủ cho pull request | CI sau khi push hoặc tạo pull request |
| Triển khai sau khi thay đổi được chấp thuận và tích hợp | CI/CD theo sự kiện trên nhánh hoặc tag được bảo vệ |
| Phản ứng với ref được cập nhật trên máy chủ Git tự quản lý | Server-side hook như `post-receive` hoặc cơ chế tương đương của nền tảng |
| Gửi thông báo local cho chính người phát triển | Hook local, nếu tác dụng phụ có thể lặp lại và không ảnh hưởng trạng thái dùng chung |

Các tác vụ bên ngoài nên có cơ chế idempotency, log, retry và cách xử lý lỗi riêng. Nếu một thông báo hoặc API call thất bại sau commit, hãy ghi nhận để xử lý lại; không cố viết lại commit chỉ để lặp lại tác vụ bên ngoài.

## 7. Hiểu đúng các hook chạy sau thao tác

Các hook có tiền tố `post-` thường chạy sau khi thao tác chính đã hoàn tất. Chúng phù hợp cho thông báo hoặc đồng bộ metadata, nhưng lỗi của chúng không tự động hoàn tác thao tác vừa hoàn thành.

| Hook | Khi nào chạy | Lưu ý an toàn |
|---|---|---|
| `post-commit` | Sau khi tạo commit | Không thể từ chối hoặc hủy commit đã tạo; không nên tự amend commit lần nữa |
| `post-merge` | Sau khi merge hoàn tất | Tránh tự checkout, reset hoặc tạo merge khác |
| `post-checkout` | Sau khi checkout hoặc switch thành công | Không tự chuyển nhánh lần nữa; có thể được gọi khi tạo worktree |
| `post-rewrite` | Sau khi commit được viết lại, ví dụ amend hoặc rebase | Nhận ánh xạ commit cũ/mới; dùng để đồng bộ metadata có kiểm soát, không khởi động thêm một lần rewrite |

Hook `post-rewrite` là điểm đặc biệt cần lưu ý: nó chạy sau một thao tác vốn đã viết lại commit. Nếu hook tiếp tục chạy `rebase`, `commit --amend` hoặc cập nhật ref thiếu kiểm soát, quy trình có thể lặp hoặc làm lịch sử khó truy vết. Hãy giới hạn nó vào tác vụ hậu xử lý được xác định rõ, chẳng hạn cập nhật tham chiếu phụ thuộc theo ánh xạ old/new commit.

## 8. Tránh nhầm repository và index qua biến môi trường

Git thiết lập một số biến môi trường khi chạy hook, chẳng hạn `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE` và `GIT_PREFIX`. Chúng giúp lệnh Git trong hook làm việc với repository và index đang thực hiện thao tác.

Nếu hook gọi Git trong một repository khác, các biến môi trường này có thể khiến lệnh tưởng rằng nó đang làm việc với repository hiện tại hoặc dùng nhầm index. Khi thực sự cần thao tác với repository khác, hãy chạy trong subshell và xóa các biến môi trường repository-local do Git cung cấp:

```sh
other_repo="../tools-repo"

(
    unset $(git rev-parse --local-env-vars)
    git -C "$other_repo" status --short
)
```

Ví dụ trên chỉ đọc trạng thái repository khác. Subshell giữ việc xóa biến môi trường trong phạm vi lệnh con, không làm thay đổi môi trường của phần còn lại trong hook. Chỉ dùng kỹ thuật này khi thật sự cần truy cập repository khác; với lệnh Git trong chính repository đang chạy hook, hãy giữ môi trường Git mà hook nhận được.

## 9. Giới hạn quyền thay đổi và kiểm soát đường dẫn

Hook xử lý tên tệp cần cẩn thận vì đường dẫn có thể chứa dấu cách, tab hoặc ký tự xuống dòng. Tránh tách danh sách đường dẫn bằng vòng lặp shell dựa trên khoảng trắng:

```sh
# Không an toàn với đường dẫn có khoảng trắng hoặc newline
for file in $(git diff --cached --name-only); do
    ...
done
```

Khi cần xử lý danh sách đường dẫn trong script POSIX, ưu tiên định dạng NUL và công cụ hỗ trợ NUL, chẳng hạn `git diff --cached --name-only -z`. Nếu script không thể xử lý tên đường dẫn an toàn, hãy giới hạn quy ước tên tệp hoặc dùng công cụ chuyên dụng thay vì đoán cách tách chuỗi.

Không ghép dữ liệu tên nhánh, tên tệp, commit message hoặc nội dung commit vào lệnh shell bằng cách nội suy không trích dẫn. Luôn quote biến và coi dữ liệu từ repository là dữ liệu đầu vào, không phải câu lệnh cần thực thi.

## 10. Kiểm thử hook trong môi trường tạm

Trước khi cài hook cho cả nhóm, kiểm tra nó trong repository thử nghiệm hoặc clone/worktree tạm. Một quy trình kiểm thử có thể gồm:

1. Tạo repository thử nghiệm với một vài tệp tracked và untracked.
2. Tạo thay đổi đã stage và thay đổi chưa stage trên cùng một tệp để kiểm tra hook có phân biệt hai vùng không.
3. Tạo tệp có dấu cách trong tên để kiểm tra cách xử lý đường dẫn.
4. Chạy hook với đầu vào hợp lệ, đầu vào không hợp lệ và trường hợp hook không tìm thấy dependency.
5. So sánh `git status`, `git diff`, `git diff --cached` và `git log` trước/sau để phát hiện thay đổi ngoài dự kiến.
6. Thử chạy lại hook để xác nhận nó không thêm trùng thông tin hoặc tạo thêm commit.
7. Thử các thao tác liên quan như amend, rebase hoặc merge nếu hook được gọi trong những luồng đó.

Có thể cấu hình thư mục hook riêng cho một lệnh thử bằng `core.hooksPath`:

```bash
git -c core.hooksPath=.githooks commit -m "test hook behavior"
```

Lệnh trên chỉ dùng cấu hình `core.hooksPath` cho lần gọi Git đó. Hãy chạy trong repository thử nghiệm có hook đã được xem xét, và bảo đảm nội dung commit thử không ảnh hưởng repository thật.

## 11. Xử lý khi hook đã tạo tác dụng phụ ngoài ý muốn

Nếu hook thay đổi working tree hoặc index, dừng các lệnh tiếp theo để xác định phần nào đã thay đổi:

```bash
git status --short
git diff
git diff --cached
git log --oneline -5
```

Nếu hook tạo commit hoặc thay đổi ref, kiểm tra lịch sử và reflog trước khi khôi phục:

```bash
git reflog --date=local -10
git show --stat --oneline HEAD
git branch -avv
```

Không chạy ngay `git reset --hard` hoặc `git clean` để xóa dấu vết. Những lệnh đó có thể xóa thay đổi hợp lệ của người dùng. Hãy sao lưu hoặc tạo ref giữ các commit cần thiết, xác định chính xác thao tác hook đã làm rồi mới chọn cách phục hồi phù hợp.

Nếu hook đã gọi dịch vụ bên ngoài, kiểm tra log và trạng thái dịch vụ đó. Một lệnh Git reset không thể hoàn tác email đã gửi, ticket đã cập nhật hoặc deployment đã thực hiện. Cần xử lý tác dụng phụ bên ngoài bằng quy trình bù trừ hoặc thao tác khôi phục của chính hệ thống đó.

## 12. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
|---|---|
| Hook chỉ có thể đọc repository | Hook là chương trình bình thường và có thể sửa tệp, index, refs hoặc gọi hệ thống bên ngoài. |
| `pre-commit` chạy formatter thì thay đổi chắc chắn nằm trong commit | Commit lấy nội dung từ index; formatter chỉ sửa working tree thì chưa cập nhật nội dung staged. |
| `git add -A` trong hook là cách an toàn để stage kết quả formatter | Lệnh này có thể stage cả thay đổi không liên quan mà người dùng chưa chọn. |
| Hook có thể chạy `git commit --amend` mà không ảnh hưởng lịch sử | Lệnh này tạo commit mới và có thể kích hoạt hook lặp lại; OID và lịch sử thay đổi. |
| `post-commit` có thể từ chối commit nếu deploy thất bại | Commit đã được tạo; hook hậu xử lý không thể hủy kết quả đó. |
| Hook local bảo đảm mọi thành viên đều chạy cùng kiểm tra | Hook có thể chưa được cài hoặc bị bỏ qua; chính sách bắt buộc cần kiểm tra ở CI hoặc server. |
| Chạy Git ở repository khác chỉ cần thêm `-C` | Biến môi trường Git của hook có thể còn trỏ đến repository hiện tại; cần xử lý chúng trong subshell khi chuyển repository. |
| Reset repository sẽ hoàn tác mọi tác dụng phụ của hook | Reset chỉ tác động đến trạng thái Git phù hợp; nó không thu hồi thông báo, API call hoặc thay đổi hệ thống bên ngoài. |

## 13. Tự kiểm tra

1. **Vì sao hook không nên tự chạy `git commit` trong một hook commit?**
   - Có thể kích hoạt hook lặp lại, tạo commit lồng nhau hoặc thay đổi lịch sử ngoài ý muốn.
2. **Vì sao `git add -A` trong hook có thể nguy hiểm?**
   - Nó có thể stage cả tệp và thay đổi không liên quan mà người dùng chưa chọn để commit.
3. **Nếu formatter chỉ sửa working tree, commit sẽ chứa phiên bản nào?**
   - Phiên bản đã nằm trong index, trừ khi hook hoặc người dùng cập nhật index sau đó.
4. **`post-commit` có thể hủy commit nếu tác vụ bên ngoài thất bại không?**
   - Không. Commit đã được tạo; tác vụ bên ngoài cần cơ chế retry hoặc bù trừ riêng.
5. **Vì sao cần xóa biến môi trường Git khi hook thao tác với repository khác?**
   - Để lệnh Git trong repository khác không vô tình dùng `GIT_DIR`, `GIT_WORK_TREE` hoặc `GIT_INDEX_FILE` của repository đang gọi hook.
6. **Nên đặt triển khai production ở đâu?**
   - Trong CI/CD hoặc quy trình server-side gắn với nhánh/tag đã được chấp thuận, không phải hook commit local.

## Kết luận

Hook chạy bằng quyền của người dùng và có thể tác động đến working tree, index, lịch sử Git hoặc hệ thống bên ngoài. Hãy thiết kế hook theo nguyên tắc chỉ đọc khi có thể, giới hạn đúng phạm vi, tránh commit hoặc viết lại lịch sử lồng nhau, không stage hàng loạt và không triển khai từ commit local. Kiểm thử trong repository tạm, kiểm tra trạng thái trước/sau và dùng CI hoặc server-side automation cho các tác vụ cần áp dụng thống nhất. Khi hook đã tạo tác dụng phụ, xác định riêng thay đổi trong Git và thay đổi ở hệ thống bên ngoài trước khi khôi phục.
