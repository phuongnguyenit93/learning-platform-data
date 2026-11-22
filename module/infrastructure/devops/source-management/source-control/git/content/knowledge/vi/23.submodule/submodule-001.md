# Submodule là kho mã độc lập được kho cha ghim tại một commit

Git submodule cho phép một repository sử dụng nội dung của một repository Git khác như một phần của dự án. Kho chứa submodule được gọi là **superproject** (kho cha); repository được nhúng là **submodule** (kho con). Hai kho có lịch sử, commit và remote riêng, nhưng kho cha lưu lại chính xác commit của kho con mà dự án đang sử dụng.

Cách tổ chức này phù hợp khi dự án phụ thuộc vào một thư viện nội bộ, một thành phần được phát triển độc lập hoặc một repository dùng chung giữa nhiều sản phẩm. Điểm quan trọng nhất là kho cha không ghi lại toàn bộ lịch sử của kho con. Nó lưu một tham chiếu đặc biệt tới commit cụ thể của kho con, nhờ đó những người khác có thể tái tạo đúng phiên bản dependency đã được dự án kiểm thử.

## 1. Submodule là gì?

Giả sử dự án chính có cấu trúc:

```text
application/
├── src/
├── docs/
└── libs/
    └── shared-utils/   (submodule)
```

Thư mục `libs/shared-utils` là một repository riêng. Nó có branch, commit và remote của chính nó. Repository `application` theo dõi vị trí submodule và commit mà nó yêu cầu.

Có thể hình dung quan hệ như sau:

```text
Superproject: application
  commit A
    |
    +-- src/ ...
    |
    +-- libs/shared-utils -> commit S1

Submodule: shared-utils
  commit S0 --- S1 --- S2
                  ^
                  |
          commit được kho cha ghim
```

Trong ví dụ, kho cha đang ghim `shared-utils` tại commit `S1`, dù kho con đã có commit mới hơn `S2`. Khi một thành viên clone dự án, Git sẽ lấy đúng `S1` để mọi người dùng cùng phiên bản dependency.

Submodule có ba đặc điểm quan trọng:

- **Repository độc lập:** kho con có lịch sử commit, branch, tag và remote riêng.
- **Commit được ghim:** kho cha lưu mã commit cụ thể của kho con, không tự động chạy theo branch mới nhất.
- **Đường dẫn được khai báo:** kho cha lưu đường dẫn submodule và URL repository trong file `.gitmodules`.

Submodule không phải bản sao các file được kho cha quản lý trực tiếp. Khi làm việc bên trong thư mục submodule, bạn đang thao tác với repository con.

## 2. Kho cha lưu thông tin submodule như thế nào?

Khi thêm một submodule, Git thường tạo hoặc cập nhật hai thành phần trong superproject:

1. File `.gitmodules` chứa cấu hình tên, đường dẫn và URL của submodule.
2. Một mục **gitlink** trong index/tree của superproject, lưu mã commit mà submodule đang được ghim.

Ví dụ file `.gitmodules`:

```ini
[submodule "shared-utils"]
    path = libs/shared-utils
    url = https://example.com/team/shared-utils.git
```

- `submodule "shared-utils"` là tên định danh của submodule trong cấu hình.
- `path` là vị trí thư mục con trong superproject.
- `url` là địa chỉ repository mà Git dùng để lấy submodule.

Mục gitlink có mode đặc biệt `160000`. Có thể xem nó bằng:

```bash
git ls-tree HEAD libs/shared-utils
```

Ví dụ đầu ra:

```text
160000 commit 4a7b9c1...    libs/shared-utils
```

Điều này cho biết superproject đang ghi nhận submodule ở commit `4a7b9c1...`. Git không lưu nội dung thư mục con như một cây file thông thường trong tree của kho cha; nó lưu một liên kết tới commit của repository con.

Có thể xem thay đổi gitlink giữa index và commit:

```bash
git diff --submodule
git diff --cached --submodule
```

Lệnh đầu xem thay đổi submodule chưa stage ở superproject; lệnh thứ hai xem thay đổi gitlink đã stage. Tùy chọn `--submodule=log` có thể giúp hiển thị danh sách commit con nằm giữa hai mốc:

```bash
git diff --submodule=log
```

File `.gitmodules` được commit cùng superproject, vì vậy các thành viên khác nhận được cấu hình đường dẫn và URL. Cấu hình thực tế của từng submodule còn có bản sao trong cấu hình local của repository cha, thường ở `.git/config`. Điều này giải thích vì sao khi URL trong `.gitmodules` thay đổi, bạn có thể cần chạy `git submodule sync` để cập nhật cấu hình local.

## 3. Thêm submodule vào một dự án

Để thêm repository con vào dự án, dùng:

```bash
git submodule add https://example.com/team/shared-utils.git libs/shared-utils
```

Trong đó:

- URL là địa chỉ repository của submodule.
- `libs/shared-utils` là đường dẫn nơi submodule xuất hiện trong superproject.

Sau lệnh này, Git tạo thư mục submodule, tải repository con và cập nhật `.gitmodules` cùng mục gitlink trong index.

Kiểm tra kết quả:

```bash
git status
git submodule status
git diff --cached
```

Bạn thường thấy `.gitmodules` và đường dẫn submodule xuất hiện trong trạng thái của kho cha. Stage và commit thay đổi của superproject:

```bash
git add .gitmodules libs/shared-utils
git commit -m "Add shared-utils submodule"
```

Commit này lưu cấu hình submodule và commit con mà kho cha muốn sử dụng. Bản thân lịch sử commit của submodule vẫn nằm trong repository con.

Nếu repository con cần xác thực, hãy bảo đảm các thành viên trong nhóm có quyền truy cập URL đó. Một URL SSH chỉ hoạt động khi tài khoản đã cấu hình khóa phù hợp; URL HTTPS có thể cần thông tin xác thực theo chính sách máy chủ.

## 4. Clone repository có submodule

Khi clone superproject thông thường:

```bash
git clone https://example.com/team/application.git
cd application
```

Git tải repository cha, nhưng các submodule có thể chưa được khởi tạo. Thư mục submodule có thể rỗng hoặc chưa chứa nội dung checkout.

Để tải và checkout tất cả submodule ngay khi clone, dùng:

```bash
git clone --recurse-submodules https://example.com/team/application.git
```

Nếu đã clone repository cha trước đó, khởi tạo submodule bằng:

```bash
git submodule update --init
```

Với dự án có submodule lồng nhau, dùng đệ quy:

```bash
git submodule update --init --recursive
```

Các tùy chọn có ý nghĩa:

- `--init`: khởi tạo cấu hình local cho các submodule chưa được khởi tạo.
- `update`: lấy nội dung cần thiết và checkout commit mà superproject đang ghim.
- `--recursive`: thực hiện tương tự với các submodule nằm bên trong submodule khác.

Sau khi tải xong, kiểm tra:

```bash
git submodule status --recursive
git status
```

Nếu một submodule cần thông tin xác thực hoặc không thể truy cập URL, lệnh update sẽ báo lỗi cho submodule đó. Kiểm tra URL trong `.gitmodules`, quyền truy cập và kết nối trước khi thử lại.

## 5. Vì sao submodule thường ở detached HEAD?

Khi chạy:

```bash
git submodule update --init
```

Git thường checkout submodule tại đúng commit được ghi trong gitlink của superproject. Checkout một commit cụ thể thay vì một branch khiến `HEAD` trong submodule ở trạng thái **detached HEAD**.

Đây là hành vi bình thường. Kho cha cần ghim một commit bất biến để mọi người nhận được cùng một phiên bản; nếu submodule tự động theo branch đang di chuyển, cùng một commit của superproject có thể tạo ra nội dung khác nhau ở những thời điểm clone khác nhau.

Kiểm tra trạng thái bên trong submodule:

```bash
git -C libs/shared-utils status
git -C libs/shared-utils branch --show-current
git -C libs/shared-utils rev-parse --short HEAD
```

Khi detached HEAD, `git branch --show-current` thường không in tên branch. Bạn vẫn có thể đọc file và chạy test. Nếu cần phát triển thay đổi mới trong submodule, nên tạo hoặc chuyển sang một branch trước:

```bash
git -C libs/shared-utils switch -c fix/parse-edge-case
```

Sau đó sửa file, commit và push trong repository con theo quy trình riêng. Khi đã có commit mới, cập nhật gitlink của superproject để ghim commit đó.

Không nên tạo commit trong detached HEAD rồi rời khỏi submodule mà không lưu lại commit bằng branch hoặc ref khác. Commit có thể vẫn còn trong reflog một thời gian, nhưng sẽ khó tìm và có thể bị dọn nếu không còn ref nào giữ nó.

## 6. Cập nhật submodule khi kho cha thay đổi commit được ghim

Một superproject có thể được cập nhật để trỏ tới commit mới của submodule. Khi pull hoặc checkout commit mới ở kho cha, gitlink trong superproject có thể thay đổi.

Để đưa submodule về commit được kho cha ghi nhận, chạy:

```bash
git submodule update --init --recursive
```

Lệnh này checkout submodule theo gitlink của commit superproject hiện tại. Nó không có nghĩa là luôn lấy commit mới nhất từ branch của submodule.

Kiểm tra khác biệt giữa trạng thái submodule và commit được kho cha yêu cầu:

```bash
git submodule status
git status
```

Một số dấu hiệu ở đầu dòng của `git submodule status`:

| Ký hiệu | Ý nghĩa |
|---|---|
| Dấu cách | Submodule đã được khởi tạo và đang ở commit được superproject ghi nhận |
| `-` | Submodule chưa được khởi tạo |
| `+` | Commit hiện tại trong submodule khác commit được superproject ghi nhận |
| `U` | Gitlink đang có xung đột chưa được giải quyết |

Nếu thấy `+`, kiểm tra commit hiện tại và gitlink của kho cha trước khi quyết định có cần cập nhật superproject hay đưa submodule về commit cũ.

## 7. Cập nhật submodule theo branch remote

Có hai mục tiêu khác nhau:

- Lấy đúng commit mà superproject đã ghim.
- Chủ động cập nhật submodule tới commit mới trên một branch remote.

Mục tiêu thứ nhất dùng `git submodule update`. Mục tiêu thứ hai dùng `--remote`:

```bash
git submodule update --remote libs/shared-utils
```

Lệnh này fetch từ remote của submodule và cập nhật working tree submodule theo branch được cấu hình. Nếu `.gitmodules` có thuộc tính `branch`, Git dùng branch đó; nếu không, Git dùng branch remote mặc định theo cấu hình của submodule.

Ví dụ thêm branch vào `.gitmodules`:

```ini
[submodule "shared-utils"]
    path = libs/shared-utils
    url = https://example.com/team/shared-utils.git
    branch = main
```

Có thể cấu hình bằng lệnh:

```bash
git submodule set-branch --branch main shared-utils
```

Sau khi cập nhật remote, submodule có thể chuyển sang commit mới hơn. Superproject chưa tự lưu commit mới đó cho tới khi bạn stage gitlink:

```bash
git status
git add libs/shared-utils
git diff --cached --submodule=log
git commit -m "Update shared-utils submodule"
```

Commit của kho cha ghi nhận mã commit mới. Những người khác sau đó chạy `git submodule update --init --recursive` sẽ checkout đúng commit đã được ghim, không cần tự chọn branch.

Không dùng `--remote` trong quy trình tái tạo build hoặc deploy nếu yêu cầu là phải lấy đúng dependency đã được review trong commit superproject. Trong các quy trình đó, hãy dùng commit đã ghim; chỉ cập nhật theo remote khi chủ động nâng phiên bản dependency.

## 8. Thay đổi code bên trong submodule và cập nhật kho cha

Giả sử bạn cần sửa một lỗi trong `shared-utils`. Vì đây là repository độc lập, cần commit thay đổi ở kho con trước:

```bash
# Chuyển vào branch làm việc của submodule
git -C libs/shared-utils switch -c fix/null-input

# Sau khi chỉnh sửa file
git -C libs/shared-utils status
git -C libs/shared-utils add src/parser.java
git -C libs/shared-utils commit -m "Handle null parser input"
```

Nếu branch cần chia sẻ, push commit của repository con lên remote:

```bash
git -C libs/shared-utils push -u origin fix/null-input
```

Sau đó quay lại superproject và stage đường dẫn submodule:

```bash
git status
git add libs/shared-utils
git diff --cached --submodule=log
git commit -m "Use shared-utils null input fix"
```

Có hai commit riêng biệt trong quy trình:

1. Commit trong `shared-utils` chứa thay đổi code của thư viện.
2. Commit trong `application` cập nhật gitlink để trỏ tới commit mới của thư viện.

Thứ tự chia sẻ rất quan trọng: hãy push commit của submodule trước khi push commit superproject tham chiếu tới nó. Nếu chỉ push kho cha mà commit con chưa có trên remote mà người khác truy cập được, họ có thể không tải được submodule ở commit đã ghim.

Có thể kiểm tra commit được kho cha ghi nhận:

```bash
git ls-tree HEAD libs/shared-utils
git -C libs/shared-utils log --oneline -5
```

## 9. Cập nhật URL submodule

URL của submodule được khai báo trong `.gitmodules`. Khi repository con được chuyển máy chủ hoặc đổi địa chỉ, cập nhật file này:

```bash
git config -f .gitmodules submodule.shared-utils.url https://example.com/new-team/shared-utils.git
```

Sau đó đồng bộ URL mới vào cấu hình local của các submodule:

```bash
git submodule sync --recursive
```

Rồi fetch/update:

```bash
git submodule update --init --recursive
```

Kiểm tra URL:

```bash
git config -f .gitmodules --get submodule.shared-utils.url
git config --get submodule.shared-utils.url
```

Lệnh đầu đọc URL được lưu trong file chia sẻ `.gitmodules`; lệnh sau đọc cấu hình local đã được khởi tạo trong repository cha. Sau khi sửa `.gitmodules`, hãy commit file đó trong superproject để thay đổi được chia sẻ với thành viên khác.

Một số repository dùng URL tương đối như `../shared-utils.git`. Git phân giải URL tương đối dựa trên URL remote của superproject. Cách này hữu ích khi nhiều repository cùng nằm dưới một máy chủ hoặc tổ chức, nhưng cần kiểm tra cấu trúc URL trước khi đổi remote của kho cha.

## 10. Kiểm tra trạng thái và xử lý lỗi thường gặp

Các lệnh kiểm tra nhanh:

```bash
git status
git submodule status --recursive
git diff --submodule
git -C libs/shared-utils status
git -C libs/shared-utils log --oneline -5
```

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Thư mục submodule rỗng sau clone | Chưa khởi tạo submodule | Chạy `git submodule update --init --recursive` |
| `git submodule status` có dấu `-` | Submodule chưa được khởi tạo | Chạy `git submodule update --init` |
| Có dấu `+` | Commit đang checkout khác gitlink của kho cha | Kiểm tra commit con; chạy update để về commit được ghim hoặc stage gitlink nếu muốn nâng phiên bản |
| Submodule ở detached HEAD | Git checkout commit được superproject ghim | Bình thường; tạo branch nếu cần phát triển |
| Không tải được submodule | URL sai, mạng hoặc quyền truy cập không đủ | Kiểm tra `.gitmodules`, chạy `git submodule sync` và xác thực remote |
| Kho cha báo submodule modified | Commit pointer hoặc nội dung bên trong submodule đã thay đổi | Kiểm tra trạng thái repository con và quyết định có cập nhật gitlink không |
| Người khác không checkout được commit submodule | Commit con chưa được push lên remote dùng chung | Push repository con trước rồi chia sẻ commit superproject |
| Submodule lồng nhau còn thiếu | Chỉ init/update cấp đầu | Dùng `--recursive` |

Khi kho cha báo submodule thay đổi, phân biệt hai tình huống:

- **Commit pointer thay đổi:** submodule đang ở một commit khác với gitlink đã ghi trong index/HEAD. Đây là thay đổi mà superproject có thể stage bằng `git add <path>`.
- **Working tree bên trong submodule thay đổi:** có file được sửa hoặc chưa được theo dõi bên trong repository con. Những thay đổi này cần được xử lý và commit trong repository con; chỉ stage gitlink ở kho cha không tự đưa nội dung file con vào commit của kho cha.

Có thể xem chi tiết bằng:

```bash
git -C libs/shared-utils status --short
git diff --submodule=log
git diff --cached --submodule=log
```

## 11. Quy trình làm việc cơ bản với submodule

Một quy trình hợp tác thường có thể tóm tắt như sau:

**Khi clone dự án:**

```bash
git clone --recurse-submodules https://example.com/team/application.git
```

Hoặc nếu đã clone:

```bash
git submodule update --init --recursive
```

**Khi cập nhật superproject sang commit mới:**

```bash
git pull
git submodule update --init --recursive
```

**Khi sửa code của submodule:**

```bash
git -C libs/shared-utils switch -c fix/something
git -C libs/shared-utils add .
git -C libs/shared-utils commit -m "Fix something"
git -C libs/shared-utils push -u origin fix/something

git add libs/shared-utils
git commit -m "Update shared-utils"
git push
```

Trong ví dụ, `git add .` bên trong submodule stage các thay đổi trong phạm vi thư mục hiện tại; hãy xem `git status` trước để chắc chắn không thêm file sinh tự động hoặc dữ liệu không mong muốn. Commit và push submodule phải hoàn tất trước khi push superproject.

**Khi chủ động nâng submodule theo branch remote:**

```bash
git submodule update --remote libs/shared-utils
git status
git add libs/shared-utils
git commit -m "Update shared-utils dependency"
git push
```

Quy trình này cập nhật gitlink trong kho cha sau khi bạn review commit mới. Nếu có thay đổi code bên trong submodule, xử lý chúng trong repository con trước.

## Kết luận

Submodule là một repository Git độc lập được superproject tham chiếu bằng gitlink tới một commit cụ thể. File `.gitmodules` lưu đường dẫn và URL để người khác biết cách lấy repository con; gitlink lưu phiên bản chính xác mà kho cha sử dụng. Dùng `git clone --recurse-submodules` hoặc `git submodule update --init --recursive` để khởi tạo, và dùng `git submodule update` để checkout commit đã ghim. Khi thay đổi code con, commit và push trong repository con trước, rồi stage gitlink và commit superproject để chia sẻ phiên bản dependency mới.
