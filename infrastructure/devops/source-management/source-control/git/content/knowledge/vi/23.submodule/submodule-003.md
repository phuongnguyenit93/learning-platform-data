# Thêm submodule và ghi nhận thay đổi trong kho cha

Khi một dự án cần sử dụng một repository Git khác như thư viện hoặc thành phần độc lập, bạn có thể thêm repository đó vào dự án bằng **submodule**. Repository chứa submodule được gọi là kho cha (superproject); repository được nhúng là kho con (submodule). Hai repository có lịch sử commit riêng, nhưng kho cha ghi nhận chính xác commit mà mỗi submodule cần sử dụng.

Điểm quan trọng là kho cha không đưa toàn bộ tệp của submodule vào lịch sử của mình. Nó lưu một tham chiếu đến commit của repository con, cùng thông tin URL và đường dẫn trong `.gitmodules`. Vì vậy, khi thay đổi mã nguồn bên trong submodule, bạn phải commit thay đổi ở repository con trước, sau đó cập nhật và commit con trỏ submodule trong kho cha.

## 1. Submodule gồm những thành phần nào?

Giả sử dự án ứng dụng có cấu trúc:

```text
sample-app/
├── .git/
├── .gitmodules
├── src/
└── libs/
    └── math-core/     <- một repository Git độc lập
```

Ở đây:

- `sample-app` là kho cha, có `.git` và lịch sử commit riêng.
- `libs/math-core` là submodule, có repository và lịch sử commit riêng.
- `.gitmodules` lưu thông tin để Git biết submodule nào nằm ở đường dẫn nào và lấy từ URL nào.
- Tree của kho cha chứa một mục gitlink trỏ đến commit cụ thể của submodule.

Một submodule có hai phần thông tin chính trong kho cha:

| Thành phần | Vai trò |
|---|---|
| `.gitmodules` | File cấu hình được commit trong kho cha, ánh xạ tên submodule, đường dẫn và URL; có thể khai báo branch hoặc update strategy |
| Gitlink | Mục trong tree/index của kho cha, mode `160000`, trỏ đến OID của commit submodule cần checkout |

Gitlink là một tham chiếu đến commit, không phải thư mục chứa các blob của submodule. Khi checkout một commit của kho cha, Git biết submodule cần ở commit nào; lệnh submodule sẽ lấy repository con và checkout đúng commit đó.

## 2. Thêm submodule vào kho cha

Giả sử bạn đang ở thư mục gốc của `sample-app` và muốn thêm thư viện từ repository:

```bash
git submodule add https://github.com/example-org/math-core.git libs/math-core
```

Lệnh này thực hiện các việc chính:

1. Clone repository `math-core` vào đường dẫn `libs/math-core`.
2. Đăng ký submodule trong cấu hình của kho cha.
3. Tạo hoặc cập nhật file `.gitmodules`.
4. Đưa thông tin `.gitmodules` và gitlink của submodule vào index của kho cha.

Nếu không truyền đường dẫn đích, Git thường dùng tên repository làm thư mục submodule. Nên chỉ định đường dẫn rõ ràng để cấu trúc dự án dễ hiểu và ổn định.

Nếu muốn submodule theo dõi một nhánh cụ thể khi dùng `git submodule update --remote`, có thể thêm `-b`:

```bash
git submodule add -b main https://github.com/example-org/math-core.git libs/math-core
```

Tùy chọn `-b main` ghi cấu hình nhánh theo dõi vào `.gitmodules`. Nó không làm kho cha tự động nhận mọi commit mới của nhánh đó; kho cha vẫn chỉ ghi nhận commit gitlink khi bạn cập nhật và commit thay đổi ở kho cha.

Nếu thư mục đích đã tồn tại và không rỗng, hoặc đã là một repository được quản lý theo cách khác, `git submodule add` có thể từ chối thao tác. Hãy chọn đường dẫn chưa tồn tại hoặc xử lý thư mục hiện tại theo đúng trạng thái repository trước khi thêm.

## 3. Kiểm tra `.gitmodules` và gitlink

Sau khi thêm, xem trạng thái kho cha:

```bash
git status
git diff --cached
git diff --cached --submodule=log
```

Thông thường, `git submodule add` đã stage hai thay đổi: file `.gitmodules` và gitlink ở `libs/math-core`. Nội dung `.gitmodules` có thể tương tự:

```ini
[submodule "libs/math-core"]
    path = libs/math-core
    url = https://github.com/example-org/math-core.git
    branch = main
```

`branch = main` chỉ xuất hiện nếu bạn cấu hình nhánh theo dõi, ví dụ bằng `git submodule add -b main`. Nếu không chỉ định, Git không nhất thiết ghi trường branch vào `.gitmodules`.

Kiểm tra mục gitlink trong index:

```bash
git ls-files --stage -- libs/math-core
```

Kết quả có dạng:

```text
160000 <submodule-commit-oid> 0    libs/math-core
```

Mode `160000` cho biết đây là gitlink. OID phía sau là commit mà kho cha đang ghi nhận cho submodule. Có thể kiểm tra commit đã được lưu trong tree của commit kho cha bằng:

```bash
git ls-tree HEAD -- libs/math-core
```

Nếu submodule mới chỉ được stage mà chưa commit kho cha, `git ls-tree HEAD` vẫn hiển thị trạng thái của commit kho cha cũ; dùng `git ls-files --stage` để xem giá trị đã staged trong index.

## 4. Commit việc thêm submodule trong kho cha

Sau khi kiểm tra URL, đường dẫn và commit gitlink, tạo commit ở kho cha:

```bash
git diff --cached -- .gitmodules
git diff --cached --submodule=log
git commit -m "Add math-core submodule"
```

Commit này ghi nhận:

- File `.gitmodules` với đường dẫn và URL của submodule.
- Gitlink mode `160000` với OID commit của `math-core`.

Nó không sao chép nội dung mã nguồn của `math-core` vào kho cha. Khi người khác clone kho cha, họ cần khởi tạo submodule để lấy nội dung repository con.

Sau khi commit, kiểm tra:

```bash
git show --summary --submodule=log HEAD
git ls-tree HEAD -- libs/math-core
```

Nếu kho cha có remote, push commit chứa `.gitmodules` và gitlink lên remote theo workflow của nhóm:

```bash
git push origin main
```

Trước khi push kho cha, hãy bảo đảm commit submodule được trỏ tới đã tồn tại trên một remote mà những người cộng tác có thể truy cập. Nếu commit chỉ tồn tại trong clone local của bạn, người khác có thể clone kho cha nhưng không tải được đúng commit submodule.

## 5. Thay đổi mã nguồn bên trong submodule

Submodule là repository độc lập, vì vậy hãy chạy lệnh Git bên trong thư mục submodule. Ví dụ, cập nhật thư viện và tạo commit:

```bash
# Đi vào repository con
cd libs/math-core

# Kiểm tra branch và trạng thái của repository con
git status
git branch --show-current

# Tạo nhánh làm việc để giữ commit mới
git switch -c feature/matrix-helper

# Chỉnh sửa mã nguồn của thư viện
git add src
git commit -m "Add matrix helper"

# Đẩy commit mới lên remote của repository con
git push -u origin feature/matrix-helper

# Quay lại thư mục gốc của kho cha
cd ../..
```

Lệnh `git commit` ở trong `libs/math-core` chỉ cập nhật lịch sử repository con. Kho cha chưa tự thay đổi gitlink chỉ vì bạn đã tạo commit bên trong submodule. Ví dụ trên tạo nhánh riêng trước khi commit, vì submodule thường ở detached HEAD sau khi kho cha checkout một gitlink cụ thể. Commit OID được kho cha ghi nhận có thể thuộc bất kỳ nhánh nào; điều cần thiết là commit phải có thể truy cập từ remote mà các thành viên khác được phép fetch.

## 6. Cập nhật gitlink trong kho cha

Sau khi tạo commit trong submodule, quay lại kho cha và kiểm tra:

```bash
git status
git diff --submodule=log
```

Khi HEAD của submodule khác với OID mà kho cha đang ghi nhận, Git hiển thị submodule là một thay đổi. Để cập nhật gitlink trong index của kho cha, chạy:

```bash
git add libs/math-core
```

Lệnh này stage OID commit mà submodule đang checkout. Nó không stage từng tệp bên trong repository con; những tệp đó phải được commit trong repository con trước.

Kiểm tra thay đổi đã staged:

```bash
git diff --cached --submodule=log
git ls-files --stage -- libs/math-core
```

Sau đó tạo commit ở kho cha:

```bash
git commit -m "Update math-core submodule"
```

Commit mới của kho cha giờ trỏ đến commit mới trong `math-core`. Hai commit được lưu ở hai repository riêng: commit thư viện nằm trong repository con; commit cập nhật con trỏ nằm trong kho cha.

## 7. Thứ tự push để đồng đội lấy được submodule

Khi thay đổi cả mã nguồn submodule và gitlink của kho cha, hãy push repository con trước rồi mới push kho cha:

```bash
# Push commit của repository con trước
git -C libs/math-core push origin feature/matrix-helper

# Sau khi gitlink đã được stage và commit ở kho cha
git push origin main
```

Thứ tự này bảo đảm commit mà gitlink tham chiếu đã có trên remote của submodule trước khi kho cha công bố OID đó. Nếu push kho cha trước nhưng commit submodule chưa được chia sẻ, người khác có thể gặp lỗi khi khởi tạo hoặc cập nhật submodule.

Nếu commit submodule được push lên một nhánh tính năng thay vì `main`, hãy xác nhận remote và quyền truy cập của đồng đội. Gitlink lưu OID commit, không lưu tên nhánh. Trường `branch` trong `.gitmodules` chỉ hỗ trợ chọn nhánh cho thao tác cập nhật remote; nó không thay thế OID mà kho cha ghi nhận.

## 8. Clone kho cha và khởi tạo submodule

Người cộng tác có thể clone kho cha cùng tất cả submodule đệ quy:

```bash
git clone --recurse-submodules https://github.com/example-org/sample-app.git
```

Nếu đã clone kho cha mà chưa lấy submodule, chạy:

```bash
git submodule update --init --recursive
```

Các tùy chọn có ý nghĩa:

- `--init` đăng ký và khởi tạo các submodule được khai báo trong `.gitmodules`.
- `--recursive` tiếp tục khởi tạo submodule lồng bên trong các submodule khác.
- `update` checkout submodule về commit mà commit hiện tại của kho cha ghi nhận.

Lệnh này thường đưa submodule về đúng commit gitlink, thường ở detached HEAD. Đây là hành vi mong đợi: kho cha yêu cầu một phiên bản cụ thể của repository con, không yêu cầu mọi người tự động đi theo đầu nhánh mới nhất.

Kiểm tra trạng thái:

```bash
git submodule status --recursive
git status
```

Trong kết quả `git submodule status`, ký tự đầu dòng thường giúp nhận biết trạng thái:

| Ký tự | Ý nghĩa |
|---|---|
| Dấu cách | Submodule đang ở commit được kho cha ghi nhận |
| `-` | Submodule chưa được khởi tạo |
| `+` | Submodule đang checkout commit khác gitlink của kho cha |
| `U` | Gitlink đang ở trạng thái xung đột merge |

## 9. Cập nhật submodule lên commit mới từ remote

Có hai cách thường dùng để cập nhật submodule.

### Chuyển nhánh và cập nhật thủ công

Nếu bạn muốn chủ động chọn nhánh trong repository con:

```bash
git -C libs/math-core fetch origin
git -C libs/math-core switch main
git -C libs/math-core pull --ff-only origin main
```

Sau khi submodule ở commit mới, quay lại kho cha, stage gitlink và commit:

```bash
git add libs/math-core
git diff --cached --submodule=log
git commit -m "Advance math-core submodule"
```

### Cập nhật theo branch cấu hình trong `.gitmodules`

Nếu `.gitmodules` có `branch = main`, có thể yêu cầu Git lấy commit mới nhất của nhánh đó:

```bash
git submodule update --remote libs/math-core
```

Lệnh `--remote` fetch remote-tracking branch được cấu hình cho submodule rồi cập nhật checkout đến commit mới. Nếu không cấu hình branch, Git dùng nhánh remote HEAD mặc định. Sau đó, kho cha vẫn cần stage và commit gitlink:

```bash
git status
git add libs/math-core
git diff --cached --submodule=log
git commit -m "Update math-core submodule pointer"
```

`git submodule update --remote` không tự commit thay đổi gitlink trong kho cha. Việc cập nhật commit nào được dùng cần được review như một thay đổi dependency: kiểm tra release, tương thích API, test và commit log của repository con trước khi commit con trỏ mới.

## 10. Phân biệt thay đổi trong kho con và thay đổi con trỏ ở kho cha

Khi làm việc với submodule, có hai lớp trạng thái:

| Vị trí | Thay đổi | Lệnh kiểm tra |
|---|---|---|
| Bên trong repository con | Tệp được sửa, stage hoặc commit trong thư viện | `git -C libs/math-core status`, `git -C libs/math-core log` |
| Trong kho cha | OID gitlink thay đổi so với commit cha đang tham chiếu | `git status`, `git diff --submodule=log`, `git ls-files --stage` |

Nếu bạn sửa tệp trong submodule nhưng chưa commit, kho cha có thể hiển thị trạng thái submodule có nội dung đã sửa. Việc chạy `git add libs/math-core` không biến những sửa đổi đó thành commit trong repository con. Hãy commit bên trong submodule trước, sau đó mới stage gitlink ở kho cha.

Một quy trình kiểm tra hai lớp:

```bash
# Kiểm tra repository con
git -C libs/math-core status
git -C libs/math-core log -1 --oneline

# Kiểm tra con trỏ mà kho cha đang ghi nhận
git ls-tree HEAD -- libs/math-core
git ls-files --stage -- libs/math-core

# Xem khác biệt gitlink
git diff --submodule=log
git diff --cached --submodule=log
```

Lệnh đầu xem trạng thái và commit hiện tại trong repository con. Hai lệnh `ls-tree` và `ls-files` lần lượt cho biết OID đã commit và OID đã stage trong kho cha. `git diff --submodule=log` giúp đọc các commit thay đổi giữa hai OID thay vì chỉ nhìn một mã hash.

## 11. Xử lý khi URL hoặc quyền truy cập submodule thay đổi

URL của submodule được lưu trong `.gitmodules`. Nếu repository con được chuyển sang máy chủ mới, sửa URL trong kho cha:

```bash
git config -f .gitmodules submodule.libs/math-core.url https://github.com/new-org/math-core.git
git add .gitmodules
git commit -m "Update math-core submodule URL"
```

Sau khi cập nhật `.gitmodules`, đồng bộ cấu hình local của submodule:

```bash
git submodule sync -- libs/math-core
```

Nếu có submodule lồng nhau, có thể dùng `git submodule sync --recursive`. Lệnh `sync` cập nhật URL trong cấu hình local từ `.gitmodules`; nó không thay đổi commit gitlink.

Nếu đồng đội không thể clone submodule, hãy kiểm tra:

1. URL trong `.gitmodules` có đúng và truy cập được không.
2. Commit OID mà gitlink tham chiếu đã được push lên remote của submodule chưa.
3. Người cộng tác có quyền đọc repository con không.
4. Repository con có yêu cầu SSH key, token hoặc quyền tổ chức riêng không.
5. Submodule có lồng nhau và cần `--recursive` không.

## 12. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
|---|---|
| Kho cha lưu toàn bộ mã nguồn submodule | Kho cha lưu `.gitmodules` và gitlink mode `160000` trỏ đến commit của repository con. |
| Commit trong submodule tự cập nhật kho cha | Không. Phải chạy `git add <submodule-path>` rồi commit trong kho cha. |
| `git add libs/math-core` stage mọi tệp đã sửa bên trong submodule | Không. Nó cập nhật gitlink theo commit đang checkout; tệp trong submodule phải được commit ở repository con. |
| `.gitmodules` chứa OID commit của submodule | `.gitmodules` lưu cấu hình như path, URL và branch; OID được lưu trong gitlink của tree/index kho cha. |
| Gitlink lưu tên nhánh `main` | Gitlink lưu OID commit cụ thể. Tên nhánh không phải giá trị mà kho cha dùng để pin phiên bản. |
| `git submodule update --remote` tự commit thay đổi ở kho cha | Không. Bạn vẫn cần stage và commit gitlink trong kho cha. |
| Clone kho cha luôn tải đầy đủ submodule | Cần `--recurse-submodules` khi clone hoặc chạy `git submodule update --init --recursive` sau đó. |
| Có thể push kho cha trước khi push commit submodule | Có thể tạo tham chiếu đến commit chưa được chia sẻ; đồng đội có thể không fetch được commit đó. Nên push repository con trước. |

## 13. Tự kiểm tra

1. **Lệnh nào thêm một repository khác làm submodule?**
   - `git submodule add <url> <path>`.
2. **File nào ghi URL và đường dẫn của submodule trong kho cha?**
   - `.gitmodules`.
3. **Gitlink có mode nào và lưu thông tin gì?**
   - Mode `160000`, lưu OID commit mà kho cha yêu cầu cho submodule.
4. **Sau khi commit thay đổi trong repository con, cần làm gì ở kho cha?**
   - Stage đường dẫn submodule bằng `git add <path>`, kiểm tra gitlink rồi commit kho cha.
5. **Lệnh nào clone kho cha cùng submodule lồng nhau?**
   - `git clone --recurse-submodules <url>`.
6. **Vì sao nên push submodule trước kho cha?**
   - Để commit mà gitlink tham chiếu đã có trên remote và đồng đội có thể tải được.

## Kết luận

Thêm submodule bằng `git submodule add` sẽ đăng ký repository con trong `.gitmodules` và stage gitlink mode `160000` trong kho cha. Mọi thay đổi mã nguồn phải được commit ở repository con; sau đó kho cha mới stage đường dẫn submodule để ghi nhận OID commit mới. Khi chia sẻ, push repository con trước rồi push kho cha. Người cộng tác clone bằng `--recurse-submodules` hoặc khởi tạo bằng `git submodule update --init --recursive` để checkout đúng commit mà kho cha đã pin.
