# Vai trò của .gitmodules, gitlink và cấu hình cục bộ

Git submodule cho phép một repository tham chiếu đến một repository Git khác tại một thư mục con. Superproject (repository cha) không lưu toàn bộ nội dung của submodule như file thông thường; nó lưu một **gitlink** trỏ đến commit cụ thể của repository con. File `.gitmodules` ghi metadata để các clone khác biết submodule nằm ở đường dẫn nào và lấy từ URL nào. Mỗi clone còn có cấu hình cục bộ trong `.git/config` để điều khiển cách submodule được khởi tạo và cập nhật.

Ba thành phần này giải quyết ba việc khác nhau: `.gitmodules` mô tả submodule cho cả nhóm, gitlink khóa phiên bản submodule mà superproject sử dụng, còn cấu hình cục bộ lưu lựa chọn riêng của từng clone. Hiểu đúng vai trò của chúng giúp tránh tình trạng máy này chạy được nhưng clone mới không tìm thấy submodule hoặc checkout nhầm commit.

## 1. Submodule và superproject

Giả sử ứng dụng `storefront` sử dụng thư viện `payment-core` được phát triển trong repository riêng. Thay vì sao chép mã thư viện vào repository ứng dụng, bạn có thể thêm repository đó làm submodule:

```text
storefront/
|-- src/
|-- libs/
|   `-- payment-core/    # worktree của repository submodule
|-- .gitmodules
`-- .git/
```

Trong cấu trúc này:

- `storefront` là superproject, quản lý mã ứng dụng và vị trí phiên bản của thư viện.
- `libs/payment-core` là working tree của repository con, có lịch sử, branch, remote và cấu hình riêng.
- `.gitmodules` là file được commit trong superproject để công bố đường dẫn và URL submodule.
- Gitlink trong index/tree của superproject lưu commit SHA mà ứng dụng yêu cầu ở submodule.
- Cấu hình cục bộ trong `.git/config` điều khiển hành vi của submodule trong clone hiện tại.

Một commit của superproject chỉ ghi nhận rằng đường dẫn `libs/payment-core` phải trỏ tới một commit cụ thể. Nó không nhúng các file của repository con vào commit cha. Vì vậy, khi chia sẻ superproject, commit được gitlink tham chiếu cũng cần có thể truy cập từ remote của submodule.

## 2. Vai trò của file .gitmodules

`.gitmodules` là file cấu hình dạng Git config được lưu và version-control trong superproject. Mỗi submodule có một section với tên định danh:

```ini
[submodule "libs/payment-core"]
    path = libs/payment-core
    url = https://git.example.com/platform/payment-core.git
```

Hai khóa quan trọng nhất:

- `path`: đường dẫn của submodule bên trong superproject.
- `url`: địa chỉ repository mà clone khác dùng để lấy submodule.

Tên trong section, ví dụ `libs/payment-core`, là **tên submodule**. Nó thường trùng với path nhưng không bắt buộc. Một submodule có thể có tên riêng khác path:

```ini
[submodule "payment-library"]
    path = vendor/payment-core
    url = ../payment-core.git
```

Khi tên và path khác nhau, các khóa cấu hình dùng tên section (`payment-library`), còn lệnh `git submodule` thường nhận đường dẫn (`vendor/payment-core`). Hãy đọc `.gitmodules` thay vì đoán tên từ folder.

Ngoài `path` và `url`, `.gitmodules` có thể chứa các thiết lập như `branch`, `update`, `ignore` hoặc `shallow`. Ví dụ:

```ini
[submodule "payment-library"]
    path = vendor/payment-core
    url = ../payment-core.git
    branch = stable
    update = checkout
    ignore = dirty
```

Các thiết lập này là mặc định được chia sẻ cùng repository. Chúng không chứa commit SHA hiện tại mà superproject yêu cầu; commit SHA đó nằm trong gitlink.

### URL tuyệt đối và URL tương đối

URL tuyệt đối xác định đầy đủ máy chủ và đường dẫn:

```ini
url = https://git.example.com/platform/payment-core.git
```

URL tương đối có thể dùng khi các repository nằm cạnh nhau trên cùng máy chủ:

```ini
url = ../payment-core.git
```

URL tương đối được Git phân giải dựa trên URL remote mặc định của superproject, thường là `origin`, chứ không phải đường dẫn thư mục trên ổ đĩa. Cách này hữu ích khi tổ chức chuyển cả nhóm repository sang host khác mà vẫn giữ cấu trúc tương đối.

## 3. Vai trò của gitlink

Gitlink là một mục đặc biệt trong index và tree của superproject. Nó có mode `160000` và object ID là commit SHA của repository submodule. Nó không phải thư mục thông thường chứa các blob của file con.

Xem gitlink trong commit hiện tại:

```bash
git ls-tree HEAD libs/payment-core
```

Kết quả minh họa:

```text
160000 commit 7f3a91c...    libs/payment-core
```

Kiểm tra mục trong index:

```bash
git ls-files --stage -- libs/payment-core
```

Kết quả cũng thể hiện mode `160000`, object ID và đường dẫn. SHA ở đây là commit được superproject ghim lại. Nếu submodule checkout một commit khác, Git có thể báo đường dẫn submodule đã modified vì gitlink trong working tree không còn khớp với commit được ghi nhận.

Ví dụ:

```text
Subproject commit 7f3a91c...   # commit được superproject ghi nhận
Subproject commit a4d82be...   # commit hiện đang checkout trong submodule
```

Khi commit cha được checkout, Git cần đưa submodule về commit SHA được gitlink chỉ định. Mặc định, `git submodule update` checkout commit đó trong trạng thái detached `HEAD`; nó không tự chọn branch mới nhất của submodule.

### Gitlink không thay thế repository submodule

Gitlink chỉ ghi mã commit. Để xem nội dung của commit đó, máy cần lấy được repository submodule và đối tượng commit tương ứng. Nếu commit con chưa được push lên remote mà superproject tham chiếu, đồng đội có thể clone superproject nhưng không lấy được phiên bản submodule cần thiết.

Đây là lý do nên push commit của submodule lên remote trước khi commit gitlink mới trong superproject.

## 4. Vai trò của cấu hình cục bộ trong .git/config

Khi clone repository, `.gitmodules` được tải về cùng superproject. Tuy nhiên, Git không tự động kích hoạt và checkout tất cả submodule trong mọi thao tác clone thông thường. Lệnh `git submodule init` đọc metadata từ `.gitmodules` và đăng ký cấu hình cần thiết vào `.git/config` của clone hiện tại.

Ví dụ, `.gitmodules` có section:

```ini
[submodule "payment-library"]
    path = vendor/payment-core
    url = https://git.example.com/platform/payment-core.git
```

Sau khi khởi tạo, cấu hình local có thể chứa:

```ini
[submodule "payment-library"]
    url = https://git.example.com/platform/payment-core.git
```

Đây là cấu hình riêng của clone. Nó thường nằm trong `.git/config` của superproject và không được commit cùng `.gitmodules`.

Một số khóa cục bộ thường gặp:

| Khóa | Vai trò |
|---|---|
| `submodule.<name>.url` | URL dùng trong clone hiện tại |
| `submodule.<name>.active` | Cho biết submodule có được kích hoạt trong clone này không |
| `submodule.<name>.update` | Chiến lược cập nhật local, nếu được cấu hình |
| `submodule.<name>.ignore` | Điều chỉnh cách status/diff hiển thị thay đổi submodule |

Tên `<name>` là tên section trong `.gitmodules`, không nhất thiết bằng path. Cấu hình local có thể ghi đè một số mặc định chia sẻ, cho phép mỗi nhà phát triển dùng URL mirror, chiến lược update hoặc cách hiển thị phù hợp với môi trường của mình.

`submodule.<name>.active` là một khóa tùy chọn để bật/tắt submodule trong clone hiện tại; `submodule.active` có thể dùng pathspec để chọn nhóm submodule đang hoạt động. Không nên giả định `git submodule init` luôn ghi `active = true`: thao tác init chủ yếu đăng ký URL và chiến lược update cần thiết vào cấu hình local.

### Xem cấu hình submodule

Xem nội dung metadata được chia sẻ:

```bash
git config -f .gitmodules --get-regexp '^submodule\.'
```

Xem cấu hình local của clone hiện tại:

```bash
git config --local --get-regexp '^submodule\.'
```

Xem riêng URL của một submodule theo tên section:

```bash
git config -f .gitmodules --get submodule.payment-library.url
git config --local --get submodule.payment-library.url
```

Nếu hai URL khác nhau, cấu hình local đang dùng cho clone có thể khác URL mặc định được công bố trong `.gitmodules`. Điều này có thể là chủ đích, ví dụ dùng mirror nội bộ. Khi debug, hãy kiểm tra cả hai nguồn.

## 5. Khởi tạo và cập nhật submodule

Khi clone superproject thông thường, thư mục submodule có thể chưa được khởi tạo. Kiểm tra:

```bash
git submodule status
```

Một dòng bắt đầu bằng dấu `-` thường cho biết submodule chưa được khởi tạo. Để đăng ký cấu hình local:

```bash
git submodule init
```

Lệnh này đọc `.gitmodules` và ghi cấu hình cần thiết vào `.git/config`; nó không tự tải nội dung repository con hoặc checkout commit. Để thực hiện cả khởi tạo và cập nhật:

```bash
git submodule update --init
```

Nếu submodule có submodule lồng nhau, dùng:

```bash
git submodule update --init --recursive
```

Hoặc clone superproject và khởi tạo toàn bộ submodule ngay từ đầu:

```bash
git clone --recurse-submodules https://git.example.com/platform/storefront.git
```

`update` lấy repository con nếu cần và checkout commit SHA được gitlink ghi nhận. Mặc định, submodule thường ở detached `HEAD` vì superproject ghim commit chứ không ghim tên branch.

### Cập nhật URL local khi .gitmodules thay đổi

Nếu nhóm thay URL submodule trong `.gitmodules`, clone hiện tại có thể vẫn giữ URL cũ trong `.git/config`. Đồng bộ lại cấu hình local bằng:

```bash
git submodule sync
git submodule sync --recursive
```

Sau đó cập nhật submodule:

```bash
git submodule update --init --recursive
```

`sync` cập nhật URL local theo URL được công bố trong `.gitmodules` cho các submodule đã được khởi tạo. Nó không thay đổi gitlink và không tự cập nhật submodule sang commit mới nhất của branch.

## 6. Các chiến lược update và branch trong .gitmodules

`.gitmodules` có thể khai báo chiến lược cập nhật mặc định:

```ini
[submodule "payment-library"]
    path = vendor/payment-core
    url = ../payment-core.git
    update = checkout
```

Các giá trị phổ biến của `submodule.<name>.update` gồm:

- `checkout`: checkout commit được gitlink chỉ định; đây là hành vi mặc định.
- `merge`: merge commit được gitlink chỉ định vào branch hiện tại của submodule.
- `rebase`: rebase branch hiện tại của submodule lên commit được gitlink chỉ định.
- `none`: không tự cập nhật submodule khi chạy update chung.

Chiến lược có thể được ghi trong cấu hình local hoặc đặt tạm bằng tùy chọn của lệnh update. Cấu hình `!command` có thể tồn tại trong cấu hình local nhưng không được phép khai báo như một chiến lược tùy ý trong `.gitmodules`, nhằm tránh việc một repository từ xa yêu cầu clone khác chạy lệnh tùy ý.

Khóa `branch` được dùng khi muốn lấy commit mới nhất từ một branch remote với `git submodule update --remote`:

```ini
[submodule "payment-library"]
    path = vendor/payment-core
    url = ../payment-core.git
    branch = stable
```

Sau đó:

```bash
git submodule update --remote vendor/payment-core
```

Lệnh này fetch remote của submodule và cập nhật working tree theo branch được cấu hình (ở đây là `stable`). Nó khác với `git submodule update` thông thường, vốn checkout commit đã ghim trong gitlink. Sau khi dùng `--remote`, superproject có thể hiển thị submodule là modified vì commit đang checkout đã khác SHA được ghi nhận. Muốn chia sẻ phiên bản mới, cần stage gitlink và commit superproject.

## 7. Hiểu trạng thái submodule qua git submodule status

Chạy:

```bash
git submodule status --recursive
```

Ví dụ:

```text
-7f3a91c... vendor/payment-core
 a4d82be... vendor/ui-kit
+c18e5d2... vendor/logging
```

Dấu đứng đầu có ý nghĩa:

| Dấu | Ý nghĩa |
|---|---|
| `-` | Submodule chưa được khởi tạo |
| `+` | Commit hiện checkout khác commit được superproject ghi nhận |
| `U` | Gitlink đang có xung đột merge |
| Không có dấu | Submodule đang ở commit được ghi nhận |

Nếu thấy dấu `+`, hãy kiểm tra commit hiện tại trong submodule và gitlink của superproject:

```bash
git -C vendor/payment-core rev-parse HEAD
git ls-tree HEAD vendor/payment-core
```

Nếu thấy `U`, cần giải quyết xung đột gitlink bằng cách chọn commit submodule mong muốn, checkout commit đó trong submodule rồi stage đường dẫn submodule ở superproject.

## 8. Thay đổi submodule và cập nhật gitlink

Giả sử bạn cần nâng `payment-core` lên một commit mới.

Trước tiên, làm việc bên trong repository con:

```bash
git -C vendor/payment-core switch stable
git -C vendor/payment-core pull --ff-only
git -C vendor/payment-core log -1 --oneline
```

Sau khi xác nhận commit mới, quay lại superproject và xem trạng thái:

```bash
git status
git diff --submodule
```

Git sẽ cho biết submodule đang checkout commit khác với gitlink đã ghi nhận. Để cập nhật gitlink trong index:

```bash
git add vendor/payment-core
git diff --cached --submodule
```

Sau đó commit thay đổi ở superproject:

```bash
git commit -m "Update payment-core submodule"
```

Commit này chỉ cập nhật SHA gitlink và các metadata khác như `.gitmodules` nếu có thay đổi. Nó không tự commit nội dung bên trong repository con.

**Trước khi push superproject, hãy push commit mới của submodule lên remote của nó.** Nếu không, đồng đội có thể nhận gitlink trỏ đến commit mà remote submodule không cung cấp.

Ví dụ:

```bash
git -C vendor/payment-core push origin stable
git push origin main
```

Đảm bảo remote branch và quyền truy cập phù hợp với cấu hình của dự án. Trong một số workflow, submodule commit có thể được đẩy bởi pipeline hoặc maintainer; điều quan trọng là commit con phải truy cập được trước khi gitlink mới được chia sẻ.

## 9. Thay đổi .gitmodules và cấu hình local

Khi muốn thay URL mặc định cho cả nhóm, sửa `.gitmodules` và commit file này:

```bash
git config -f .gitmodules submodule.payment-library.url https://git.example.com/platform/payment-core.git
git add .gitmodules
git commit -m "Update payment-core submodule URL"
```

Sau khi pull thay đổi, các clone đã khởi tạo submodule cần đồng bộ URL local:

```bash
git submodule sync --recursive
```

Nếu chỉ một nhà phát triển muốn dùng mirror riêng, có thể thay URL local mà không sửa `.gitmodules`:

```bash
git config --local submodule.payment-library.url https://mirror.example.net/payment-core.git
```

Thay đổi local này không được commit và chỉ có hiệu lực trong clone hiện tại. Nếu sau đó chạy `git submodule sync`, URL local có thể được đồng bộ lại theo `.gitmodules`.

Không đặt token hoặc mật khẩu trực tiếp trong URL được commit vào `.gitmodules`. Dùng credential manager hoặc cơ chế xác thực an toàn của môi trường.

## 10. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế |
|---|---|
| `.gitmodules` ghi commit SHA của submodule | `.gitmodules` ghi tên, path, URL và một số thiết lập; SHA nằm trong gitlink của tree/index |
| Gitlink chứa toàn bộ file của submodule | Gitlink chỉ lưu mode `160000` và commit SHA |
| `git submodule init` tải repository con | `init` đăng ký cấu hình local; `update` mới fetch/checkout nội dung cần thiết |
| `git submodule update` lấy commit mới nhất trên branch | Mặc định nó checkout đúng commit được gitlink ghim |
| Thay URL trong `.gitmodules` tự cập nhật mọi clone | Clone đã khởi tạo cần `git submodule sync` để đồng bộ cấu hình local |
| Commit superproject tự lưu commit mới của submodule | Cần commit trong submodule, push commit đó, rồi stage và commit gitlink ở superproject |
| `.git/config` được chia sẻ với đồng đội | Đây là cấu hình local của từng clone, không được commit cùng repository |

## 11. Bài tập thực hành

Trong hai repository thử nghiệm, tạo một superproject và một repository thư viện riêng. Không dùng repository sản xuất cho bài tập.

1. Dùng `git submodule add` để thêm thư viện vào superproject, rồi đọc file `.gitmodules`.
2. Chạy `git ls-files --stage` và `git ls-tree HEAD` sau khi commit để tìm mục gitlink mode `160000`.
3. Chạy `git config -f .gitmodules --get-regexp '^submodule\.'` và `git config --local --get-regexp '^submodule\.'` để so sánh metadata chia sẻ với cấu hình local.
4. Clone superproject vào thư mục mới, chạy `git submodule status`, rồi dùng `git submodule update --init --recursive` để khởi tạo submodule.
5. Thay URL trong `.gitmodules`, pull thay đổi vào clone khác và dùng `git submodule sync` để cập nhật URL local.
6. Tạo commit mới trong repository con, push commit đó lên remote, stage gitlink trong superproject và commit thay đổi.
7. Giải thích vì sao `.gitmodules`, gitlink và `.git/config` có vai trò khác nhau.

Bạn hoàn thành bài tập khi xác định được submodule lấy từ đâu, superproject ghim commit nào, cấu hình nào được chia sẻ và cấu hình nào chỉ tồn tại trong clone hiện tại.
