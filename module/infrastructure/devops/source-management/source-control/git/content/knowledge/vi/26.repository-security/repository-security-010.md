# Kho mã không tin cậy: hook, filter, submodule và công cụ ngoài

Một repository Git có thể chứa mã nguồn, script, cấu hình build và metadata điều khiển cách Git xử lý file. Clone một repository không đồng nghĩa với việc bạn đã tin cậy mọi nội dung bên trong. Một số cơ chế chỉ lưu mô tả trong repository nhưng có thể kích hoạt chương trình bên ngoài khi checkout, diff, merge, add hoặc cập nhật submodule. Trước khi chạy script, cài dependency hay bật hook của một dự án lạ, hãy xác định những thành phần nào có thể thực thi mã, chúng lấy lệnh từ đâu và chúng có thể truy cập tài nguyên nào trên máy.

## 1. Xác định ranh giới tin cậy

Khi nhận một repository từ nguồn chưa được xác minh, cần phân biệt ba việc:

- **Đọc dữ liệu Git:** xem commit, tree, blob, diff hoặc metadata để hiểu repository.
- **Lấy dữ liệu từ bên ngoài:** clone submodule, tải Git LFS object, tải dependency hoặc truy cập URL được khai báo trong dự án.
- **Thực thi mã:** chạy hook, filter, build script, package install script, test, IDE task hoặc công cụ ngoài.

Ba việc này có mức rủi ro khác nhau. Đọc một blob bằng `git show` thường không thực thi nội dung blob. Ngược lại, checkout có thể gọi filter đã được cấu hình; chạy `npm install`, `make`, `gradle`, script shell hoặc task IDE có thể thực thi mã do repository cung cấp.

Không nên suy luận rằng repository an toàn chỉ vì nó được lưu trên một nền tảng quen thuộc, có nhiều star hoặc clone thành công. Một repository có thể chứa thay đổi độc hại, dependency bị chiếm quyền, submodule từ nguồn khác hoặc cấu hình khiến công cụ local chạy một lệnh không mong muốn.

## 2. Những gì clone thông thường có và không tự thực thi

Trong một lần clone thông thường từ remote, Git không tự sao chép các hook trong `.git/hooks/` của người tạo repository sang `.git/hooks/` của bạn. Các file hook mẫu được Git tạo tại máy local thường có hậu tố `.sample` và không tự chạy. Tương tự, file `.git/config` local của người tạo repository không phải nội dung được chia sẻ như commit thông thường.

Tuy vậy, điều đó không có nghĩa mọi bước trong clone và checkout đều luôn thụ động:

- Git có thể gọi **smudge filter** đã được cấu hình trên máy khi checkout file có attribute `filter`.
- Git LFS có thể được gọi qua filter để lấy nội dung file lớn từ LFS endpoint.
- Nếu dùng `--recurse-submodules`, Git sẽ truy cập URL submodule và tải repository con.
- Công cụ IDE hoặc tiện ích được cấu hình tự mở project có thể kích hoạt task hoặc extension riêng.
- Script cài đặt, build, test và package manager chỉ chạy khi bạn hoặc công cụ tự động gọi chúng, nhưng chúng có thể thực hiện nhiều hành động trên máy.

Hook được lưu trong source tree, ví dụ `.githooks/pre-commit`, không tự trở thành hook hoạt động chỉ vì file có mặt trong clone. Nó cần được cấu hình qua `core.hooksPath`, sao chép vào thư mục hooks hoặc cài bằng công cụ tương ứng. Hãy kiểm tra lệnh bootstrap trước khi chạy vì chính script cài đặt có thể thực thi mã.

## 3. Hook: script được Git gọi tại một thời điểm cụ thể

Hook là chương trình hoặc script được Git gọi ở các điểm trong workflow, chẳng hạn `pre-commit`, `commit-msg`, `pre-push`, `post-checkout` hoặc `post-merge`. Hook có thể kiểm tra chất lượng, nhưng cũng có thể thực hiện lệnh tùy ý với quyền của tài khoản đang chạy Git.

Kiểm tra vị trí hook và cấu hình đường dẫn:

```bash
git rev-parse --git-path hooks
git config --show-origin --show-scope --get core.hooksPath
```

Xem nội dung thư mục hooks và kiểm tra các file không có hậu tố `.sample`. Nếu `core.hooksPath` được cấu hình ở global hoặc system, Git có thể dùng thư mục đó cho repository hiện tại. Một cấu hình hook toàn cục có thể áp dụng cả khi bạn mở repository không tin cậy.

Một số lưu ý:

- Hook trong `.git/hooks` của repository clone từ remote thường là hook local do người dùng hoặc công cụ cài đặt.
- Hook được commit trong `.githooks/` chỉ là file trong repository cho đến khi có cấu hình kích hoạt.
- `git config core.hooksPath .githooks` khiến Git dùng thư mục đó làm nơi tìm hook; hãy chỉ cấu hình sau khi review script.
- `git commit --no-verify` và `git push --no-verify` có thể bỏ qua một số hook client-side, nên hook local không phải ranh giới bảo mật bắt buộc.

Nếu repository đã được bàn giao dưới dạng thư mục có sẵn cả `.git`, không phải clone mới, hãy xem `.git/config` và thư mục hooks như dữ liệu chưa đáng tin. Chúng có thể chứa cấu hình local hoặc hook được cài từ trước.

## 4. Filter trong `.gitattributes` có thể gọi chương trình ngoài

`.gitattributes` có thể gán attribute cho từng đường dẫn. Một số attribute chỉ điều khiển cách Git hiển thị hoặc xử lý nội dung, nhưng các attribute như `filter`, `diff` và `merge` có thể chọn một driver đã được cấu hình để chạy chương trình bên ngoài.

Ví dụ repository có thể chứa:

```gitattributes
*.asset filter=asset-clean diff=asset-view merge=asset-merge
```

Dòng này chỉ đặt tên driver. Lệnh thực thi thực tế thường được lấy từ cấu hình Git trên máy, ví dụ:

```ini
[filter "asset-clean"]
    clean = asset-tool clean
    smudge = asset-tool checkout

[diff "asset-view"]
    textconv = asset-tool render-text

[merge "asset-merge"]
    driver = asset-tool merge %O %A %B %L %P
```

Các cấu hình driver có thể nằm trong global, system hoặc local config. Nếu máy đã cài driver có cùng tên, attribute từ repository có thể khiến Git gọi driver đó ở thời điểm phù hợp.

| Cơ chế | Thời điểm có thể gọi chương trình | Rủi ro cần kiểm tra |
|---|---|---|
| `filter.<name>.smudge` hoặc `process` | Checkout, restore hoặc materialize nội dung | Chạy lệnh khi đưa nội dung ra working tree |
| `filter.<name>.clean` hoặc `process` | Add hoặc xử lý nội dung để đưa vào index | Chạy lệnh khi chuẩn bị nội dung commit |
| `diff.<name>.textconv` hoặc `command` | Khi xem diff có dùng driver đó | Chạy công cụ chuyển đổi hoặc diff ngoài |
| `merge.<name>.driver` | Khi merge file dùng driver đó | Chạy lệnh hợp nhất bên ngoài |

Không phải mọi attribute đều thực thi mã. Điểm cần chú ý là attribute có thể chọn một driver, còn lệnh của driver được cấu hình ở nơi khác. Một `.gitattributes` độc hại có thể tận dụng một driver tin cậy đã tồn tại trên máy để kích hoạt lệnh ở thời điểm bạn checkout hoặc diff.

## 5. Kiểm tra attributes và cấu hình driver trước khi dùng

Đọc các file `.gitattributes` trong repository, bao gồm cả file ở thư mục con. Có thể xem bản đã commit mà không cần checkout nội dung:

```bash
git show HEAD:.gitattributes
git ls-tree -r --name-only HEAD
```

Lệnh thứ hai liệt kê đường dẫn trong tree để tìm các file `.gitattributes` ở cấp con. Sau khi xác định đường dẫn, dùng `git show HEAD:path/to/.gitattributes` để đọc từng file.

Kiểm tra attribute Git tính cho một đường dẫn:

```bash
git check-attr --all -- path/to/file.asset
```

Kiểm tra cấu hình filter, diff và merge driver cùng nguồn của chúng:

```bash
git config --show-origin --show-scope --get-regexp '^(filter|diff|merge)\.'
```

Kết quả có thể chứa đường dẫn nội bộ hoặc lệnh riêng của máy; hãy xem cẩn thận trước khi chia sẻ log. Nếu thấy driver không rõ nguồn gốc, không checkout hoặc diff các file kích hoạt driver đó cho tới khi xác minh lệnh và nguồn cấu hình.

Git LFS là ví dụ phổ biến về filter được cài hợp lệ. Nếu repository dùng LFS, xem `.gitattributes` và `.lfsconfig`, kiểm tra LFS endpoint cùng quyền truy cập trước khi tải nội dung. Có thể dùng `GIT_LFS_SKIP_SMUDGE=1` khi clone để trì hoãn việc materialize nội dung LFS, rồi tải sau khi đã xác minh nguồn và endpoint.

## 6. Diff và merge cũng có thể dùng công cụ ngoài

Không phải mọi lệnh trông như chỉ đọc đều chắc chắn không thực thi chương trình ngoài. Khi xem diff, Git có thể gọi external diff hoặc textconv driver nếu cấu hình và attributes yêu cầu. Khi merge, Git có thể gọi merge driver đã đăng ký.

Trước khi dùng công cụ diff/merge của repository lạ:

1. Xem `.gitattributes` và các driver được gán cho file.
2. Kiểm tra cấu hình `diff.*`, `merge.*` và `diff.external` bằng `git config --show-origin --show-scope`.
3. Xác minh executable được gọi đến từ đâu và có phải công cụ bạn chủ động cài đặt không.
4. Nếu không cần driver ngoài, dùng môi trường sạch hoặc cấu hình an toàn đã được kiểm tra để xem nội dung thô.

Không tự chạy lệnh được tìm thấy trong `.gitattributes` như thể đó là hướng dẫn đáng tin. Attribute chỉ là tên driver; hãy tìm lệnh thực tế trong cấu hình Git đang có hiệu lực.

## 7. Submodule: repository cha có thể yêu cầu tải thêm nguồn bên ngoài

File `.gitmodules` khai báo tên, đường dẫn và URL của submodule. Khi chạy:

```bash
git clone --recurse-submodules <repository-url>
```

Git truy cập các URL submodule và tải repository con. Những repository này có thể thuộc tổ chức khác, dùng máy chủ khác hoặc có lịch sử và mã nguồn riêng. Việc tải submodule không tự chứng minh nguồn đó đáng tin.

Trước khi khởi tạo submodule, đọc cấu hình:

```bash
git show HEAD:.gitmodules
git submodule status --recursive
```

Kiểm tra các gitlink trong tree:

```bash
git ls-tree HEAD
```

Gitlink thường có mode `160000` và trỏ tới commit cụ thể của repository con. Hãy xác minh URL, commit được ghim và quyền truy cập cho từng submodule. Không bật `--recurse-submodules` tự động cho repository lạ trước khi review `.gitmodules`.

Một điểm bảo vệ quan trọng: `git submodule init` không sao chép một lệnh update tùy chỉnh dạng `!command` từ `.gitmodules` vào cấu hình local, vì lý do bảo mật. Dù vậy, URL submodule vẫn có thể khiến Git kết nối tới máy chủ không mong muốn; repository con cũng có thể chứa filter, script build và dependency riêng. Cần đánh giá toàn bộ chuỗi nguồn.

## 8. Git LFS và các endpoint bên ngoài

Repository dùng Git LFS lưu pointer trong Git và tải nội dung thật từ LFS endpoint. File `.lfsconfig` có thể chứa thiết lập LFS được chia sẻ, bao gồm URL endpoint. Khi clone hoặc checkout với Git LFS đã cài, filter có thể khởi tạo yêu cầu mạng để tải nội dung.

Trước khi tải LFS từ repository không tin cậy:

- Đọc `.gitattributes` để xác định pattern nào dùng `filter=lfs`.
- Đọc `.lfsconfig` nếu có và xác minh endpoint.
- Kiểm tra endpoint có thuộc nhà cung cấp hoặc tổ chức mong đợi không.
- Dùng chế độ bỏ qua smudge để trì hoãn tải nếu cần review trước.
- Không cung cấp credential nhạy cảm cho endpoint chưa được xác minh.

LFS object là dữ liệu, không tự thực thi chỉ vì được tải. Rủi ro thực thi xuất hiện khi một công cụ mở, xử lý hoặc chạy nội dung đó; rủi ro mạng và rò rỉ credential có thể xuất hiện ngay trong quá trình tải nếu endpoint hoặc cấu hình xác thực không đáng tin.

## 9. Build script, package manager và IDE là các bề mặt thực thi khác

Nhiều hành động nguy hiểm không đến từ Git core mà từ công cụ bạn chạy sau khi clone:

- `npm install` hoặc `npm ci` có thể chạy lifecycle scripts của package.
- Maven và Gradle có thể thực thi plugin, task hoặc script build.
- `make`, shell script, PowerShell và task runner chạy lệnh được khai báo trong repository.
- IDE có thể đề xuất hoặc tự kích hoạt task, extension, debugger hoặc cấu hình chạy.
- Container build có thể chạy lệnh trong Dockerfile; image base cũng là một thành phần cần tin cậy.

Trước khi chạy, đọc các file liên quan như `package.json`, lockfile, `pom.xml`, `build.gradle`, `settings.gradle`, `Makefile`, Dockerfile, `.vscode/tasks.json`, cấu hình IDE và script bootstrap. Kiểm tra dependency có được pin và nguồn package có hợp lệ không.

Đừng bấm “Trust project”, bật toàn bộ extension hoặc chạy lệnh cài đặt chỉ vì IDE đề nghị. Chỉ bật các tính năng đó sau khi đã xác minh nguồn và hiểu hành động mà chúng sẽ thực hiện.

## 10. Cấu hình local trong `.git/config` cũng cần được xem xét

Khi clone từ remote thông thường, Git tạo `.git/config` local cho repository mới dựa trên tùy chọn clone và remote URL. Các cấu hình local của người tạo repository không tự được tải về như một phần của commit.

Tuy nhiên, nếu bạn nhận một thư mục repository đã có sẵn `.git`, một bản sao ổ đĩa, archive chứa metadata hoặc môi trường do người khác chuẩn bị, `.git/config` có thể chứa thiết lập không mong muốn. Những khóa cần chú ý gồm:

- `core.hooksPath`: thay đổi nơi Git tìm hook.
- `core.fsmonitor`: có thể chỉ định chương trình hỗ trợ theo dõi thay đổi file.
- `filter.*`, `diff.*`, `merge.*`: khai báo lệnh xử lý nội dung hoặc diff/merge.
- `credential.helper`: chỉ định cơ chế lấy credential.
- `core.sshCommand`, `core.gitProxy`: thay đổi cách kết nối tới remote.
- `include.path` và `includeIf.*`: nạp thêm file cấu hình từ đường dẫn khác.

Xem cấu hình cùng nguồn và scope:

```bash
git config --list --show-origin --show-scope
```

Không sao chép nguyên `.git/config` từ một máy không tin cậy sang máy làm việc có credential. Nếu cần sử dụng repository được bàn giao sẵn, hãy xem xét từng thiết lập trước khi chạy lệnh Git có thể kích hoạt hook, filter hoặc helper.

## 11. `safe.directory` không phải sandbox

Git có cơ chế kiểm tra quyền sở hữu repository để giảm rủi ro khi chạy trong thư mục thuộc sở hữu của người dùng khác. Khi Git báo `dubious ownership`, không nên giải quyết bằng cách thêm wildcard rộng vào cấu hình toàn cục:

```bash
git config --global --add safe.directory '*'
```

Thiết lập này làm suy yếu kiểm tra ownership trên mọi repository. Nếu đã xác minh một đường dẫn cụ thể và có lý do chính đáng để tin cậy nó, có thể thêm đúng đường dẫn đó:

```bash
git config --global --add safe.directory /path/to/trusted/repository
```

Trên Windows, dùng đường dẫn tuyệt đối phù hợp với môi trường. `safe.directory` chỉ giải quyết kiểm tra ownership của Git; nó không chứng minh mã nguồn, hook, filter, submodule hoặc build script an toàn và không cô lập chúng khỏi hệ thống.

## 12. Xác minh nguồn gốc và tính toàn vẹn không đồng nghĩa xác minh an toàn

Có thể kiểm tra chữ ký commit hoặc tag nếu dự án sử dụng quy trình ký:

```bash
git verify-commit <commit>
git verify-tag <tag>
```

Chữ ký hợp lệ cho biết đối tượng được ký không bị thay đổi kể từ khi ký và chữ ký khớp với khóa được kiểm tra. Bạn vẫn phải xác minh khóa đó thuộc đúng người hoặc tổ chức theo kênh tin cậy. Chữ ký hợp lệ không bảo đảm mã nguồn không có lỗ hổng, không chứa mã độc hoặc không gọi dịch vụ ngoài.

Tương tự, kiểm tra object integrity bằng `git fsck` có thể phát hiện object hỏng hoặc liên kết không hợp lệ, nhưng không phải công cụ phân tích hành vi của chương trình. Hãy phân biệt tính toàn vẹn dữ liệu, nguồn gốc và độ an toàn của mã.

## 13. Quy trình mở repository không tin cậy

Một quy trình thận trọng có thể thực hiện theo từng giai đoạn:

1. **Xác minh nguồn:** kiểm tra URL, tổ chức, người gửi, commit hoặc tag được yêu cầu và kênh xác nhận độc lập.
2. **Tạo môi trường cô lập:** dùng VM hoặc container dùng một lần, tài khoản không có quyền quản trị, không gắn thư mục chứa bí mật và không chuyển tiếp SSH agent.
3. **Clone mà chưa checkout hoặc tải submodule:**

   ```bash
   git clone --no-checkout --no-recurse-submodules <repository-url> review-repo
   ```

   Cách này lấy Git repository nhưng trì hoãn checkout file và không tự tải submodule. Vẫn cần tin cậy URL transport đã chọn và giữ Git được cập nhật.

4. **Đọc metadata trước:**

   ```bash
   git show HEAD:.gitattributes
   git show HEAD:.gitmodules
   git ls-tree -r HEAD
   git log --oneline --decorate -20
   ```

   Nếu một file không tồn tại, `git show` sẽ báo không tìm thấy; điều đó không nhất thiết là lỗi repository.

5. **Kiểm tra cấu hình local và global:**

   ```bash
   git config --list --show-origin --show-scope
   git config --show-origin --show-scope --get-regexp '^(filter|diff|merge)\.'
   git config --show-origin --show-scope --get core.hooksPath
   ```

6. **Đánh giá các nguồn phụ:** xác minh submodule URL, LFS endpoint, dependency registry, build script, IDE task và công cụ ngoài.
7. **Checkout có kiểm soát:** chỉ checkout sau khi đã đánh giá attributes và filter có thể được gọi. Nếu không cần filter ngoài, dùng môi trường sạch không cài driver tùy chỉnh.
8. **Chạy mã trong sandbox:** tắt hoặc giới hạn mạng, không mount credential, SSH key, cloud config hay thư mục cá nhân; dùng dữ liệu giả và quyền tối thiểu.
9. **Theo dõi hành vi:** quan sát tiến trình con, truy cập file và kết nối mạng nếu đang đánh giá mã có rủi ro cao.
10. **Hủy môi trường sau khi review:** bỏ VM/container dùng một lần theo quy trình, không mang credential hoặc artifact không rõ nguồn trở lại máy chính.

Các lệnh kiểm tra metadata vẫn có thể chịu ảnh hưởng bởi cấu hình local của repository hoặc công cụ ngoài đã cài trên máy. Với repository được bàn giao sẵn cả `.git`, hãy kiểm tra config và hooks trước khi dùng các lệnh rộng hơn.

## 14. Cô lập thực thi và bảo vệ credential

Khi phải build hoặc chạy test của repository chưa tin cậy, hãy dùng một môi trường riêng:

- Tài khoản không có quyền admin/root.
- VM hoặc container dùng một lần, với thư mục mount chỉ đọc nếu có thể.
- Không mount thư mục home, SSH keys, cloud credentials, browser profile hoặc socket của host.
- Không chuyển tiếp SSH agent và không dùng credential helper chứa token cá nhân.
- Hạn chế mạng ở mức cần thiết; nếu build cần tải dependency, chỉ cho phép registry đã xác minh.
- Dùng dữ liệu thử nghiệm, không dùng database hoặc dịch vụ production.
- Cập nhật Git, runtime, package manager và image nền để giảm rủi ro từ lỗ hổng đã biết.

Container không tự động là sandbox hoàn hảo. Container chia sẻ kernel với host; quyền mount, capabilities, socket và network quyết định mức cô lập. Với mã có mức rủi ro cao, VM dùng một lần hoặc môi trường phân tích chuyên dụng có thể phù hợp hơn.

## 15. Dấu hiệu cần dừng và điều tra

Dừng trước khi thực thi nếu thấy một trong các dấu hiệu:

- `.gitattributes` gán filter/diff/merge driver lạ hoặc có cấu hình local tương ứng không rõ nguồn.
- `.gitmodules` chứa URL không liên quan, URL dùng giao thức hoặc máy chủ bất ngờ.
- `.lfsconfig` chuyển endpoint sang host chưa xác minh.
- Script bootstrap yêu cầu quyền admin, tải và chạy lệnh từ URL không pin phiên bản hoặc sửa cấu hình global.
- Build script đọc thư mục home, SSH key, token, biến môi trường cloud hoặc gửi dữ liệu ra ngoài không có lý do rõ ràng.
- IDE yêu cầu bật extension không rõ nhà phát hành hoặc chạy task tự động.
- Hook hoặc helper thực hiện thao tác ngoài phạm vi kiểm tra mà không có giải thích.

Không cần kết luận repository chắc chắn độc hại chỉ từ một dấu hiệu. Hãy dừng hành động có thể thực thi, xác minh mục đích và nguồn của thành phần đó qua người duy trì hoặc kênh độc lập.

## 16. Ghi nhớ

Repository là dữ liệu cần đánh giá trước khi trở thành mã được thực thi. Hook không tự được mang sang trong clone thông thường, nhưng filter, external diff/merge driver, submodule, Git LFS và build/IDE tools có thể tạo hành động ngoài khi được kích hoạt. Hãy đọc `.gitattributes`, `.gitmodules`, `.lfsconfig` và cấu hình Git đang có hiệu lực; trì hoãn checkout hoặc tải dependency khi chưa rõ nguồn; cô lập môi trường thực thi và giữ credential ngoài tầm với. Chữ ký và kiểm tra object chỉ hỗ trợ xác minh nguồn gốc/tính toàn vẹn, không thay thế việc đánh giá an toàn của mã.
