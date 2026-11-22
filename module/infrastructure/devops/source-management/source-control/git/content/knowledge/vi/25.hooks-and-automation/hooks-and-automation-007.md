# Kiểm tra định dạng, thông điệp và bí mật trong luồng commit

Một commit tốt cần nhiều hơn một diff đúng về mặt kỹ thuật. File nên tuân theo định dạng của dự án, thông điệp commit phải giải thích rõ thay đổi và nội dung được đưa vào lịch sử không được chứa token, mật khẩu hoặc khóa bí mật. Git hooks cho phép tự động kiểm tra những điều này tại các thời điểm phù hợp trong luồng commit và push. Khi thiết kế đúng, các kiểm tra diễn ra sớm, đưa ra lỗi dễ hiểu và giúp nhóm giữ chất lượng lịch sử ổn định.

## 1. Luồng commit và vị trí phù hợp cho từng kiểm tra

Git cung cấp nhiều hook chạy ở những thời điểm khác nhau. Với việc kiểm tra định dạng, thông điệp và bí mật, các hook thường quan trọng nhất là:

| Hook | Thời điểm chạy | Kiểm tra phù hợp |
|---|---|---|
| `pre-commit` | Trước khi Git tạo commit | Định dạng, lint, test nhanh, quét bí mật trong nội dung staged |
| `prepare-commit-msg` | Sau khi Git chuẩn bị file thông điệp, trước khi mở editor | Thêm mẫu hoặc thông tin ngữ cảnh vào thông điệp |
| `commit-msg` | Sau khi thông điệp đã được chuẩn bị, trước khi tạo commit | Kiểm tra cấu trúc, quy ước và độ rõ ràng của thông điệp |
| `post-commit` | Sau khi commit thành công | Thông báo hoặc ghi nhận sự kiện; không thể chặn commit vừa tạo |
| `pre-push` | Trước khi Git gửi ref lên remote | Kiểm tra bổ sung, test rộng hơn hoặc quét trước khi chia sẻ |

Luồng đơn giản:

```text
git add
   |
   v
git commit
   |
   v
pre-commit  ---- lỗi? ----> dừng commit
   |
   v
prepare-commit-msg
   |
   v
người dùng xác nhận thông điệp
   |
   v
commit-msg  ---- lỗi? ----> dừng commit
   |
   v
tạo commit
   |
   v
post-commit
   |
   v
git push
   |
   v
pre-push    ---- lỗi? ----> dừng push
   |
   v
remote nhận cập nhật
```

`pre-commit` phù hợp với kiểm tra nội dung sẽ được commit; `commit-msg` phù hợp với kiểm tra thông điệp vì hook nhận đường dẫn tới file thông điệp làm đối số đầu tiên. Không nên dùng `post-commit` để ngăn commit vì hook này chỉ chạy sau khi commit đã được tạo.

## 2. Git tìm hook ở đâu?

Theo mặc định, hook nằm trong thư mục `hooks` của Git directory, thường là `.git/hooks/`. Git tạo một số file mẫu có đuôi `.sample`; các file mẫu này không tự chạy. Hook cần có tên đúng và quyền thực thi.

Kiểm tra đường dẫn hooks và cấu hình tùy chỉnh:

```bash
git rev-parse --git-path hooks
git config --show-origin --get core.hooksPath
```

Nếu `core.hooksPath` được cấu hình, Git sử dụng thư mục đó thay cho vị trí mặc định. Cách này hữu ích khi nhóm lưu hook trong repository, ví dụ `.githooks/`:

```bash
git config core.hooksPath .githooks
```

Sau đó có thể commit các script trong `.githooks/` để chia sẻ cùng dự án. Tuy nhiên, mỗi clone vẫn cần được cấu hình để dùng thư mục đó; việc clone repository không tự động kích hoạt hook được lưu trong source tree.

Trên hệ thống dùng shell, hook thường là script có shebang và quyền thực thi. Ví dụ:

```sh
#!/bin/sh
echo "Running pre-commit checks..."
```

Trong Git for Windows, Git Bash cung cấp môi trường shell để chạy hook dạng này. Nếu dùng công cụ quản lý hook như pre-commit hoặc Husky, hãy theo hướng dẫn cài đặt của công cụ và phiên bản đang dùng.

## 3. Kiểm tra định dạng trong `pre-commit`

Kiểm tra định dạng giúp phát hiện file không tuân theo quy tắc của dự án trước khi tạo commit. Có thể dùng formatter hoặc linter theo ngôn ngữ:

| Loại dự án | Lệnh kiểm tra ví dụ |
|---|---|
| JavaScript/TypeScript với Prettier | `npx prettier --check .` |
| Python với Ruff | `ruff format --check .` |
| Python với Black | `black --check .` |
| Go | `gofmt -d .` |
| Java với Maven Spotless | `mvn spotless:check` |

Các lệnh trên là ví dụ; hãy dùng formatter và cấu hình mà repository đã thống nhất. Một hook đơn giản có thể chạy kiểm tra toàn dự án:

```sh
#!/bin/sh
set -eu

npm run format:check
```

Lưu script với tên `pre-commit` trong thư mục hooks đang dùng và cấp quyền thực thi. Khi lệnh trả mã khác `0`, Git dừng commit để bạn sửa định dạng rồi thử lại.

Chạy kiểm tra toàn dự án dễ thiết lập nhưng có thể chậm trong repository lớn. Với dự án có nhiều file, nên chỉ kiểm tra các file liên quan tới commit.

## 4. Kiểm tra đúng nội dung đã stage

Một điểm quan trọng của Git là working tree và index có thể chứa hai phiên bản khác nhau của cùng một file. Commit lấy nội dung từ index, vì vậy kiểm tra chỉ working tree có thể không kiểm tra đúng phần sẽ được commit.

Ví dụ:

1. Bạn sửa `src/app.ts` và chạy `git add src/app.ts`.
2. Sau đó tiếp tục sửa file nhưng chưa chạy `git add` lần nữa.
3. Working tree hiện có phiên bản mới, còn index giữ phiên bản đã stage trước đó.
4. `git commit` sẽ ghi nội dung trong index.

Nếu formatter kiểm tra working tree, nó có thể báo file hiện tại đã đúng định dạng trong khi phiên bản staged vẫn chưa đúng. Vì vậy, hook cần kiểm tra đúng snapshot staged.

Một cách phổ biến là dùng `lint-staged` để chỉ chạy công cụ trên file đã stage. Ví dụ cấu hình trong `package.json`:

```json
{
  "lint-staged": {
    "*.{js,jsx,ts,tsx,json,md,css}": "prettier --write",
    "*.py": "ruff format"
  }
}
```

Sau đó hook `pre-commit` gọi:

```sh
#!/bin/sh
set -eu
npx --no-install lint-staged
```

`lint-staged` xác định các file staged, chạy công cụ tương ứng và cập nhật phần đã định dạng trở lại index theo workflow của nó. Nhờ vậy commit chứa phiên bản đã được định dạng.

Nếu không dùng công cụ tự stage, hãy chạy formatter ở chế độ kiểm tra như `prettier --check` hoặc `ruff format --check`, rồi yêu cầu người dùng sửa và stage lại. Không nên chạy formatter ghi file trên toàn working tree mà không xem xét các chỉnh sửa unstaged, vì thao tác đó có thể làm thay đổi cả công việc chưa định commit.

## 5. Kiểm tra thông điệp bằng `commit-msg`

Thông điệp commit là tài liệu ngắn gắn với lịch sử. Một quy ước rõ ràng giúp review, tìm kiếm, tạo changelog và hiểu lý do thay đổi. Nhiều nhóm dùng Conventional Commits với dạng:

```text
<type>(<scope>): <description>
```

Ví dụ:

```text
feat(auth): add refresh token rotation
fix(api): handle empty request body
docs(git): explain worktree cleanup
refactor(parser): extract token validation
```

Một số `type` thường dùng là `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore` và `revert`. `scope` có thể có hoặc không tùy quy ước của nhóm. Dấu `!` trước dấu hai chấm có thể biểu thị thay đổi không tương thích ngược, ví dụ `feat(api)!: remove legacy endpoint`.

Hook `commit-msg` nhận đường dẫn file thông điệp ở `$1`. Ví dụ script shell kiểm tra subject theo quy ước đơn giản:

```sh
#!/bin/sh
set -eu

message_file=$1
subject=$(sed -n '1p' "$message_file")

if ! printf '%s\n' "$subject" | grep -Eq '^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([[:alnum:]./_-]+\))?!?: .+'; then
    echo "Commit message must follow: type(scope): description" >&2
    exit 1
fi
```

Đặt script với tên `commit-msg` trong thư mục hooks đang dùng và cấp quyền thực thi. Đây là chính sách minh họa; hãy điều chỉnh danh sách type, scope và cách xử lý commit tự động theo quy ước của dự án. Một số nhóm cần cho phép thông điệp merge hoặc revert mặc định do Git tạo.

Hook này kiểm tra dòng đầu tiên, không đánh giá chất lượng nội dung. Một thông điệp đúng cú pháp như `fix(api): update code` vẫn có thể quá mơ hồ. Review của con người vẫn cần thiết để bảo đảm mô tả nói rõ điều gì thay đổi và vì sao.

## 6. Một số quy tắc viết commit message hữu ích

Ngoài kiểm tra cú pháp, nhóm có thể thống nhất các nguyên tắc:

- Subject dùng câu mệnh lệnh hoặc mô tả hành động ngắn gọn, nhất quán với ngôn ngữ nhóm.
- Dòng đầu nêu loại thay đổi và phạm vi khi cần.
- Phần body giải thích lý do, bối cảnh, tác động hoặc lựa chọn kỹ thuật quan trọng.
- Dùng footer cho mã issue, liên kết ticket hoặc thông tin breaking change theo quy ước.
- Tránh thông điệp chung chung như `fix`, `update`, `changes` hoặc `wip` trên nhánh chuẩn bị chia sẻ.

Ví dụ một commit message có body:

```text
fix(auth): reject expired refresh tokens

Reject refresh tokens after their configured expiration time so that
expired sessions cannot obtain a new access token.

Refs: AUTH-241
```

Hook có thể kiểm tra hình thức, nhưng không nên cố tự động đánh giá toàn bộ chất lượng giải thích. Hãy dùng review và template để hỗ trợ phần ngữ nghĩa.

## 7. Quét bí mật trước khi commit

Secret scanning tìm các giá trị có thể là thông tin xác thực như:

- API key, access token và refresh token.
- Mật khẩu, chuỗi kết nối có credential.
- Private key hoặc khóa ký.
- Credential cloud, service account key và webhook secret.
- Các chuỗi có entropy cao hoặc khớp mẫu của nhà cung cấp.

Quét trong `pre-commit` giúp phát hiện sớm trước khi dữ liệu đi vào commit. Nên dùng công cụ chuyên dụng như Gitleaks thay vì chỉ tìm một vài từ khóa bằng `grep`: secret có nhiều định dạng, tên biến khác nhau và có thể bị mã hóa hoặc chia nhỏ.

Ví dụ thêm Gitleaks vào `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.24.2
    hooks:
      - id: gitleaks
```

`rev` là phiên bản được pin trong ví dụ; nhóm nên chọn phiên bản đã phê duyệt và cập nhật có kiểm soát. Cài pre-commit framework và hook trong repository:

```bash
pre-commit install
pre-commit run --all-files
```

Lệnh đầu cài hook local để chạy trước commit. Lệnh thứ hai chạy các kiểm tra trên toàn bộ file được cấu hình, hữu ích khi thiết lập ban đầu hoặc kiểm tra lại repository. Trong workflow commit, hook Gitleaks được cấu hình để quét nội dung thay đổi staged.

Nếu dùng hook script riêng, hãy bảo đảm scanner nhận phạm vi staged diff hoặc staged files. Quét cả thư mục làm việc có thể bỏ sót khác biệt giữa working tree và index hoặc báo kết quả không khớp với nội dung commit.

## 8. Xử lý phát hiện bí mật

Khi scanner báo một chuỗi có thể là secret:

1. Dừng commit và xác định file, dòng hoặc diff bị phát hiện.
2. Xác minh đó là secret thật hay false positive; không in giá trị đầy đủ vào log hoặc ticket.
3. Nếu là secret thật, xóa khỏi nội dung staged và lấy credential từ secret manager hoặc biến môi trường khi ứng dụng chạy.
4. Stage lại file đã sửa và chạy scanner lần nữa.
5. Nếu credential đã từng được commit hoặc push, coi như đã lộ: thu hồi hoặc rotate ngay, sau đó đánh giá phạm vi truy cập và log sử dụng.

Xóa secret trong commit mới không xóa giá trị khỏi commit cũ. Nếu secret đã vào lịch sử, cần xử lý riêng việc loại bỏ khỏi lịch sử Git và phối hợp với người dùng repository; việc viết lại lịch sử không thay thế bước thu hồi credential.

False positive có thể được xử lý bằng allowlist có phạm vi hẹp, kèm lý do và thời hạn xem xét. Không thêm quy tắc bỏ qua rộng như toàn bộ thư mục cấu hình hoặc mọi chuỗi có định dạng giống token, vì điều đó có thể che giấu secret thật.

## 9. Không dựa hoàn toàn vào hook local

Hook local thường nằm trong `.git/hooks/` và không tự được chia sẻ khi người khác clone repository. Ngay cả khi hook được lưu trong `.githooks/` hoặc cấu hình bằng công cụ như pre-commit, mỗi clone vẫn cần bước cài đặt.

Người dùng cũng có thể bỏ qua một số hook bằng tùy chọn phù hợp, ví dụ:

```bash
git commit --no-verify
git push --no-verify
```

`git commit --no-verify` bỏ qua `pre-commit` và `commit-msg`; `git push --no-verify` bỏ qua `pre-push`. Vì vậy, hook local là lớp phản hồi nhanh cho người phát triển, không phải ranh giới bảo mật duy nhất.

Để thực thi chính sách cho mọi người, tổ chức nên bổ sung kiểm tra phía máy chủ và CI:

- Server-side `pre-receive` hoặc quy tắc push của nền tảng có thể từ chối cập nhật chứa dữ liệu không được phép.
- CI có thể chạy formatter, lint, test và secret scan trên commit hoặc pull request.
- Quy tắc bảo vệ branch yêu cầu status checks đạt trước khi merge.
- Secret scanning phía nền tảng có thể phát hiện credential trong lịch sử hoặc nội dung được push.

Server-side hook và CI cần kiểm tra đúng phạm vi commit được cập nhật, bao gồm commit mới trong push; không chỉ dựa vào working tree của một máy cá nhân.

## 10. Tổ chức hook để cả nhóm sử dụng

Có thể lưu hook trong repository, ví dụ:

```text
project/
  .githooks/
    pre-commit
    commit-msg
    pre-push
  .pre-commit-config.yaml
  package.json
```

Đặt thư mục hook cho repository:

```bash
git config core.hooksPath .githooks
```

Sau khi clone, thành viên cần chạy bước bootstrap được dự án hướng dẫn để cấu hình hook và cài công cụ phụ thuộc. Có thể đưa lệnh thiết lập vào tài liệu onboarding hoặc script cài đặt dự án.

Nếu dùng pre-commit framework, lưu `.pre-commit-config.yaml` trong repository và hướng dẫn mọi người chạy `pre-commit install`. Khi thay đổi phiên bản hook, review file cấu hình như dependency code để bảo đảm cùng một nhóm chạy cùng bộ kiểm tra.

Không lưu token hoặc private key trong script hook, cấu hình được commit hoặc tham số dòng lệnh. Hook nên gọi secret scanner và formatter đã cài đặt, còn credential phải lấy từ cơ chế bảo mật của môi trường.

## 11. Kiểm tra trước khi push

`pre-push` có thể chạy các kiểm tra tốn thời gian hơn so với `pre-commit`, chẳng hạn test tích hợp, kiểm tra branch hoặc scan bổ sung. Hook này nhận thông tin về remote và các ref sắp được push qua standard input; nếu cần phân tích chính xác phạm vi, hãy đọc tài liệu hook của Git và xử lý từng dòng input thay vì giả định chỉ có một branch.

Ví dụ hook đơn giản chạy bộ test nhanh:

```sh
#!/bin/sh
set -eu

npm test
```

Nếu test thất bại, hook trả mã khác `0` và Git dừng push. Không nên đặt toàn bộ test kéo dài vào mọi lần push local nếu điều đó khiến nhóm tìm cách vô hiệu hóa hook; có thể chạy kiểm tra nhanh trước push và kiểm tra đầy đủ trong CI.

## 12. Chẩn đoán khi hook không chạy hoặc chạy sai

Khi commit không kích hoạt hook như mong đợi, kiểm tra:

```bash
git config --show-origin --get core.hooksPath
git rev-parse --git-path hooks
git status --short
```

Các nguyên nhân thường gặp:

- File hook vẫn mang hậu tố `.sample` hoặc tên không đúng (`pre-commit`, `commit-msg`).
- Script chưa có quyền thực thi hoặc shebang không hợp lệ.
- `core.hooksPath` trỏ tới thư mục khác với nơi bạn vừa sửa.
- Công cụ được gọi trong hook không có trong `PATH` của tiến trình Git.
- Hook giả định working tree là nguồn dữ liệu trong khi commit lấy nội dung từ index.
- Hook chạy toàn dự án nên quá chậm hoặc lỗi ở file không liên quan.
- Một lệnh bên trong script thất bại nhưng script không truyền mã thoát lỗi ra ngoài.
- Người dùng dùng `--no-verify` hoặc môi trường CI cấu hình bỏ qua hook.

Để kiểm tra hook commit message, tạo một commit thử trên branch thử nghiệm hoặc dùng `git commit` trong repository sandbox. Không thử bằng cách đưa secret thật vào repository; dùng chuỗi giả có định dạng minh họa và xác nhận scanner phát hiện theo cấu hình.

## 13. Ví dụ cấu hình một luồng kiểm tra

Một dự án JavaScript có thể kết hợp kiểm tra định dạng file staged, quét secret và kiểm tra commit message như sau:

1. Cài formatter, `lint-staged`, pre-commit framework và Gitleaks theo phiên bản được nhóm phê duyệt.
2. Cấu hình `lint-staged` trong `package.json` để format các file staged.
3. Khai báo Gitleaks trong `.pre-commit-config.yaml` để quét nội dung staged.
4. Cài hook pre-commit bằng `pre-commit install`.
5. Thêm script `commit-msg` để kiểm tra quy ước Conventional Commits.
6. Cài các hook vào thư mục được chọn và xác minh bằng một commit thử không chứa secret thật.
7. Cấu hình CI chạy lại formatter, lint, test và secret scan để kiểm tra độc lập với máy local.

Luồng khi commit:

```text
git add
  |
  v
pre-commit
  |-- format staged files
  |-- scan staged changes for secrets
  |
  v
commit-msg
  |-- validate subject and message policy
  |
  v
commit created
  |
  v
CI rechecks commit / pull request
```

Khi một kiểm tra thất bại, sửa đúng nguyên nhân, stage lại nội dung cần commit và chạy lại. Không xóa hook hoặc thêm allowlist rộng chỉ để làm cho commit đi qua.

## 14. Ghi nhớ

Đặt kiểm tra đúng thời điểm: định dạng và secret scan trong `pre-commit`, quy ước thông điệp trong `commit-msg`, kiểm tra bổ sung trước khi chia sẻ trong `pre-push`. Hãy kiểm tra nội dung staged vì đó là dữ liệu Git sẽ commit, giữ script có mã thoát rõ ràng và chia sẻ cách cài hook cùng repository. Hook local giúp phát hiện sớm nhưng có thể bị bỏ qua; CI và chính sách phía máy chủ mới là lớp thực thi chung. Nếu secret đã lọt vào lịch sử, thu hồi credential trước và xử lý lịch sử theo quy trình phối hợp.
