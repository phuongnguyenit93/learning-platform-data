# Clone kèm submodule bằng `--recurse-submodules`

Một repository có thể sử dụng các repository Git khác làm thành phần phụ thuộc thông qua submodule. Khi clone repository cha theo cách thông thường, Git tải lịch sử của repository cha nhưng không tự tải nội dung submodule. Nếu quên bước khởi tạo, các thư mục submodule có thể xuất hiện nhưng chưa có mã nguồn bên trong. Tùy chọn `git clone --recurse-submodules` giúp clone repository cha, khởi tạo submodule và tải cả các submodule lồng nhau theo những commit mà repository cha đã ghi nhận.

## 1. Submodule được lưu trong repository cha như thế nào?

Submodule là một repository Git độc lập được gắn vào một đường dẫn trong repository cha, thường gọi là *superproject*. Repository cha không lưu toàn bộ file của submodule như file thông thường. Thay vào đó, Git lưu một mục đặc biệt trong tree gọi là **gitlink**, trỏ tới mã commit cụ thể của repository con.

File `.gitmodules` trong superproject ghi thông tin cấu hình cơ bản cho các submodule, thường gồm tên, đường dẫn và URL:

```ini
[submodule "shared-library"]
    path = libs/shared-library
    url = https://git.example.com/team/shared-library.git
```

- `path` là vị trí submodule bên trong working tree của superproject.
- `url` là địa chỉ repository mà Git dùng để tải submodule.
- Tên trong section (`shared-library`) là tên cấu hình submodule, thường được dùng trong các lệnh và cấu hình Git.

Commit của superproject ghi nhận gitlink, tức commit cụ thể mà submodule phải checkout. Vì vậy, `.gitmodules` cho biết tải repository nào ở đâu, còn gitlink cho biết phiên bản nào cần dùng.

Ví dụ, superproject có thể ghi nhận:

```text
project/
  .gitmodules
  src/
  libs/
    shared-library/   -> commit 8f31c2a của repository con
```

Commit được ghim trong gitlink giúp mọi người clone cùng superproject có thể nhận cùng phiên bản submodule, thay vì tự động lấy commit mới nhất của nhánh mặc định trong repository con.

## 2. Clone thông thường và clone có submodule khác nhau thế nào?

Giả sử repository cha chứa `libs/shared-library` là submodule.

Clone thông thường:

```bash
git clone https://git.example.com/team/application.git
```

Lệnh này clone superproject. Các submodule chưa được khởi tạo và tải nội dung; đường dẫn tương ứng có thể còn trống hoặc chưa có working tree của repository con.

Clone kèm toàn bộ submodule:

```bash
git clone --recurse-submodules https://git.example.com/team/application.git
```

`--recurse-submodules` yêu cầu Git khởi tạo và cập nhật các submodule sau khi clone superproject. Git tải repository con, checkout đúng commit được ghi trong gitlink, sau đó tiếp tục xử lý các submodule lồng nhau.

Có thể chỉ định thư mục đích:

```bash
git clone --recurse-submodules https://git.example.com/team/application.git application
```

Lệnh tạo thư mục `application` và đặt superproject cùng các submodule vào đó.

## 3. Git thực hiện những bước nào khi clone đệ quy?

Ở mức khái niệm, `git clone --recurse-submodules` thực hiện quy trình:

1. Clone repository cha và checkout branch hoặc commit được chọn.
2. Đọc các khai báo submodule trong `.gitmodules` của commit vừa checkout.
3. Khởi tạo cấu hình submodule cần thiết trong repository local.
4. Clone hoặc lấy dữ liệu của từng repository con.
5. Checkout mỗi submodule tới commit mà gitlink của superproject yêu cầu.
6. Tiếp tục khởi tạo và cập nhật submodule bên trong các submodule đó khi có yêu cầu đệ quy.

Như vậy, lệnh này không chỉ tải các URL được liệt kê ở cấp đầu tiên. Khi có submodule lồng nhau, `--recurse-submodules` tiếp tục xử lý các cấp bên trong.

## 4. Chọn branch của superproject khi clone

Bạn có thể kết hợp `--branch` để chọn branch hoặc tag của repository cha:

```bash
git clone --recurse-submodules --branch release/2.4 https://git.example.com/team/application.git application
```

Git checkout `release/2.4` của superproject rồi tải các submodule theo gitlink trong commit của branch đó. `--branch` chọn phiên bản repository cha; nó không yêu cầu từng submodule checkout branch cùng tên hoặc branch mới nhất.

Điểm này rất quan trọng khi dự án có nhiều phiên bản thư viện con. Branch `main` của submodule có thể đã tiến lên nhiều commit, nhưng superproject vẫn có thể ghim một commit cũ đã được kiểm thử. Clone đệ quy giữ đúng commit đã ghim đó.

## 5. Submodule thường ở trạng thái detached HEAD

Sau khi clone đệ quy, kiểm tra một submodule:

```bash
cd application/libs/shared-library
git status -sb
git branch --show-current
git rev-parse HEAD
```

Submodule thường ở trạng thái **detached HEAD** vì Git checkout trực tiếp commit mà superproject ghi nhận, thay vì checkout một branch local của repository con. Khi detached HEAD, `git branch --show-current` thường trả về rỗng.

Đây là trạng thái bình thường. Nó bảo đảm submodule đang ở đúng phiên bản mà superproject yêu cầu. Nếu bạn cần phát triển bên trong submodule, hãy chủ động checkout một branch:

```bash
git switch -c feature/library-change
```

Sau khi commit thay đổi trong submodule, repository cha sẽ thấy gitlink trỏ tới commit mới. Bạn cần commit thay đổi gitlink trong superproject nếu muốn chia sẻ phiên bản submodule mới cho những người khác.

## 6. Xác minh submodule sau khi clone

Quay lại thư mục gốc của superproject và kiểm tra:

```bash
cd application
git status
git submodule status --recursive
```

`git submodule status --recursive` liệt kê commit mà mỗi submodule đang checkout, bao gồm các submodule lồng nhau. Ký tự đầu dòng giúp nhận biết trạng thái:

| Ký tự đầu | Ý nghĩa |
|---|---|
| Dấu cách | Submodule đã checkout đúng commit được superproject ghi nhận |
| `-` | Submodule chưa được khởi tạo |
| `+` | Submodule đang checkout commit khác với commit được ghi trong index của superproject |
| `U` | Gitlink đang ở trạng thái xung đột |

Với clone đệ quy thành công, các submodule cần dùng thường xuất hiện với dấu cách ở đầu và mã commit khớp gitlink. Nếu có `-`, submodule chưa được tải hoặc khởi tạo. Nếu có `+`, hãy kiểm tra xem có ai đã checkout hoặc commit phiên bản khác trong submodule hay chưa.

Có thể xem cấu hình submodule trong superproject:

```bash
git config --file .gitmodules --get-regexp '^submodule\..*\.(path|url)$'
```

Lệnh này liệt kê các cặp tên submodule với `path` và `url`. Nếu cần kiểm tra nội dung từng submodule, dùng `git -C` để chạy lệnh tại đường dẫn tương ứng mà không cần đổi thư mục:

```bash
git -C libs/shared-library status -sb
git -C libs/shared-library log -1 --oneline
```

## 7. Khi repository đã clone nhưng quên `--recurse-submodules`

Bạn không cần clone lại toàn bộ superproject. Từ thư mục gốc repository cha, chạy:

```bash
git submodule update --init --recursive
```

- `init` khởi tạo cấu hình local cho các submodule chưa được khởi tạo.
- `update` tải và checkout commit được ghi trong gitlink.
- `--recursive` áp dụng cùng quy trình cho các submodule lồng nhau.

Lệnh này là cách phổ biến để hoàn tất bước submodule sau một lần clone thông thường. Nếu chỉ muốn khởi tạo một submodule cụ thể, có thể chỉ định path:

```bash
git submodule update --init libs/shared-library
```

Nếu submodule đó chứa submodule lồng nhau, thêm `--recursive`:

```bash
git submodule update --init --recursive libs/shared-library
```

Khi cần khôi phục đầy đủ tất cả submodule theo commit mà superproject đang ghi nhận, dùng lệnh không giới hạn path ở đầu bài.

## 8. Các tùy chọn clone hữu ích khi repository có nhiều submodule

### 8.1. Clone submodule song song với `--jobs`

Repository lớn có nhiều submodule có thể mất thời gian nếu tải tuần tự. Dùng `--jobs` để giới hạn số submodule được tải đồng thời:

```bash
git clone --recurse-submodules --jobs 4 https://git.example.com/team/application.git application
```

Git có thể tải tối đa số submodule được chỉ định cùng lúc. Giá trị phù hợp phụ thuộc tốc độ mạng, tài nguyên máy và tải của máy chủ Git.

### 8.2. Clone submodule nông với `--shallow-submodules`

Nếu không cần toàn bộ lịch sử của repository con, có thể dùng:

```bash
git clone --recurse-submodules --shallow-submodules https://git.example.com/team/application.git application
```

`--shallow-submodules` làm cho các submodule được clone ở độ sâu 1. Điều này giảm lượng lịch sử cần tải nhưng hạn chế khả năng xem log cũ, tìm commit tổ tiên hoặc phát triển dựa trên lịch sử sâu của submodule.

Có thể kết hợp với shallow clone của superproject:

```bash
git clone --depth 1 --recurse-submodules --shallow-submodules https://git.example.com/team/application.git application
```

`--depth 1` giới hạn lịch sử của superproject; `--shallow-submodules` áp dụng shallow clone cho các submodule. Hai tùy chọn điều khiển hai phần repository khác nhau.

### 8.3. Cẩn trọng với `--remote-submodules`

Mặc định, clone đệ quy checkout commit submodule đã được superproject ghi trong gitlink. Tùy chọn `--remote-submodules` thay đổi cách cập nhật: submodule sử dụng trạng thái của remote-tracking branch thay vì commit SHA được superproject ghi nhận.

```bash
git clone --recurse-submodules --remote-submodules https://git.example.com/team/application.git application
```

Với dự án cần build có thể tái lập, nên hiểu rõ sự khác nhau trước khi dùng tùy chọn này. Lấy trạng thái remote mới nhất có thể làm kết quả clone khác với phiên bản submodule đã được superproject ghim và kiểm thử. Không dùng `--remote-submodules` như lựa chọn mặc định khi mục tiêu là tái tạo chính xác trạng thái của một commit superproject.

## 9. Xử lý lỗi khi clone submodule

Clone superproject có thể thành công nhưng bước tải submodule thất bại. Một số nguyên nhân thường gặp:

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| `Repository not found` | URL submodule sai hoặc tài khoản không có quyền đọc | Kiểm tra `url` trong `.gitmodules` và quyền repository con |
| `Authentication failed` hoặc `Permission denied (publickey)` | Credential HTTPS/SSH chưa đúng hoặc chưa được cấp quyền | Kiểm tra token, SSH key và tài khoản cho từng repository con |
| `Could not resolve host` hoặc timeout | DNS, VPN, proxy hoặc kết nối mạng | Kiểm tra hostname, mạng và cấu hình proxy |
| Submodule directory rỗng hoặc chưa khởi tạo | Clone không dùng recurse hoặc bước submodule bị dừng giữa chừng | Chạy `git submodule status` rồi `git submodule update --init --recursive` |
| `fatal: remote error: upload-pack: not our ref` | Máy chủ không cung cấp commit gitlink yêu cầu, hoặc commit đã không còn truy cập được | Xác minh gitlink và lịch sử repository con với người quản trị |

Một tài khoản có thể đọc được superproject nhưng không có quyền đọc mọi submodule. Hãy xác minh quyền truy cập cho từng URL trong `.gitmodules`, đặc biệt khi các repository con thuộc nhóm hoặc tổ chức khác.

Nếu URL submodule đã được sửa trong `.gitmodules`, đồng bộ URL vào cấu hình local rồi cập nhật lại:

```bash
git submodule sync --recursive
git submodule update --init --recursive
```

`sync` cập nhật URL trong cấu hình local của submodule theo URL đang khai báo trong `.gitmodules`. Nó không tự sửa file `.gitmodules`; nếu URL trong file đó sai, cần sửa nguồn cấu hình và commit thay đổi ở superproject trước.

## 10. Hiểu URL tương đối trong `.gitmodules`

`.gitmodules` có thể dùng URL tuyệt đối:

```ini
[submodule "shared-library"]
    path = libs/shared-library
    url = https://git.example.com/team/shared-library.git
```

Hoặc URL tương đối:

```ini
[submodule "shared-library"]
    path = libs/shared-library
    url = ../shared-library.git
```

URL tương đối được Git phân giải dựa trên URL mặc định của remote superproject, thường là remote được dùng để clone. Nó không được tính từ thư mục làm việc hiện tại. Ví dụ, nếu superproject có URL `https://git.example.com/team/application.git`, URL `../shared-library.git` thường được phân giải thành `https://git.example.com/team/shared-library.git`.

URL tương đối hữu ích khi nhiều repository cùng nằm trong một nhóm hoặc namespace và có thể được mirror sang máy chủ khác. Tuy nhiên, nếu superproject được clone từ một mirror có cấu trúc khác, hãy xác minh URL được phân giải đúng trước khi clone submodule.

## 11. Clone đệ quy trong dự án có submodule lồng nhau

Một submodule có thể chứa `.gitmodules` riêng và tiếp tục khai báo submodule khác. Ví dụ:

```text
application/                       superproject
  .gitmodules
  libs/
    shared-library/                submodule cấp 1
      .gitmodules
      vendor/
        codec/                     submodule cấp 2
```

Nếu chỉ tải submodule cấp đầu mà không đệ quy, `vendor/codec` có thể chưa được khởi tạo. `--recurse-submodules` yêu cầu Git tiếp tục xử lý các cấp lồng nhau. Khi kiểm tra, dùng:

```bash
git submodule status --recursive
```

Khi một submodule lồng nhau không tải được, xác định `.gitmodules` thuộc repository cấp nào và kiểm tra URL từ đúng cấp đó. URL tương đối của submodule lồng nhau được phân giải theo remote của repository chứa khai báo submodule ấy.

## 12. Clone xong rồi cập nhật submodule như thế nào?

Thông thường, khi đồng đội cập nhật superproject để trỏ tới commit submodule mới, bạn chỉ cần cập nhật superproject rồi đồng bộ submodule:

```bash
git pull
git submodule update --init --recursive
```

Lệnh thứ hai đưa các submodule về đúng commit được ghi trong phiên bản superproject mới. Nếu nhóm cấu hình pull theo rebase hoặc merge, `git pull` sẽ tuân theo cấu hình đó; hãy hiểu chính sách pull của repository trước khi chạy.

Không nhầm thao tác này với:

```bash
git submodule update --remote
```

`--remote` yêu cầu Git lấy trạng thái mới từ remote-tracking branch được cấu hình cho submodule, thay vì chỉ checkout commit gitlink đã ghim. Khi dùng nó, bạn có thể tạo ra một gitlink mới trong superproject và cần review, commit thay đổi đó như một cập nhật dependency.

## 13. Quy trình clone đề xuất cho thành viên mới

Khi nhận một repository có submodule, thực hiện theo trình tự:

1. Xác nhận Git đã được cài đặt và bạn có quyền đọc superproject cùng các repository con.
2. Đọc tài liệu dự án nếu có quy định về giao thức HTTPS/SSH, VPN hoặc credential.
3. Clone với `--recurse-submodules`:

   ```bash
   git clone --recurse-submodules <repository-url> <directory>
   ```

4. Kiểm tra danh sách submodule:

   ```bash
   git submodule status --recursive
   ```

5. Kiểm tra working tree của superproject và các submodule:

   ```bash
   git status --short
   git submodule foreach --recursive 'git status --short'
   ```

6. Xác nhận submodule đang ở đúng commit mà superproject yêu cầu; nếu có trạng thái `-`, `+` hoặc `U`, xử lý theo nguyên nhân trước khi build.
7. Chạy build/test theo hướng dẫn dự án sau khi tất cả dependency đã sẵn sàng.

Nếu đã clone mà thiếu submodule, dùng `git submodule update --init --recursive` từ gốc superproject để hoàn tất.

## 14. Những nhầm lẫn thường gặp

- **Nghĩ clone superproject tự tải mọi repository con.** Cần `--recurse-submodules` hoặc chạy `git submodule update --init --recursive` sau đó.
- **Nghĩ submodule sẽ tự checkout branch mặc định mới nhất.** Mặc định Git checkout commit được ghi trong gitlink.
- **Nghĩ `--branch` chọn branch cho cả submodule.** Tùy chọn này chọn branch hoặc tag của superproject.
- **Coi detached HEAD trong submodule là lỗi.** Đây là trạng thái thường gặp khi submodule được checkout theo commit đã ghim.
- **Chỉ kiểm tra submodule cấp đầu.** Dùng `--recursive` khi update và status để bao gồm các cấp lồng nhau.
- **Cho rằng có quyền đọc superproject là có quyền đọc submodule.** Mỗi URL có thể có chính sách truy cập riêng.
- **Dùng `--remote-submodules` mà không hiểu hệ quả.** Tùy chọn này thay đổi cách chọn commit và có thể làm mất tính tái lập theo gitlink.
- **Sửa URL trong `.gitmodules` nhưng quên đồng bộ cấu hình local.** Dùng `git submodule sync --recursive` rồi update lại.

## 15. Ghi nhớ

`git clone --recurse-submodules` clone superproject, khởi tạo và tải các submodule theo commit gitlink mà superproject ghi nhận, đồng thời xử lý các submodule lồng nhau. `.gitmodules` cho biết path và URL; gitlink xác định commit cần checkout. Sau khi clone, kiểm tra bằng `git submodule status --recursive`, lưu ý trạng thái detached HEAD là bình thường và bảo đảm bạn có quyền truy cập từng repository con. Nếu clone thiếu submodule hoặc bước tải bị gián đoạn, có thể hoàn tất lại bằng `git submodule update --init --recursive`.
