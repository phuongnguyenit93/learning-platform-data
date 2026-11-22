# Khởi tạo và cập nhật bằng git submodule update --init --recursive

## Submodule là gì và vì sao phải khởi tạo?

Git submodule cho phép một repository quản lý một repository Git khác như một thành phần nằm bên trong cây thư mục của nó. Repository chứa submodule được gọi là **superproject**. Submodule có lịch sử, commit và remote riêng; superproject lưu lại mã commit cụ thể mà mỗi submodule phải sử dụng.

Ví dụ một ứng dụng có cấu trúc:

~~~text
inventory-app/
├── src/
├── config/
├── libs/
│   ├── ui-kit/       # submodule
│   └── data-client/  # submodule
├── .gitmodules
└── README.md
~~~

Khi clone superproject, Git lấy mã nguồn và lịch sử của repository chính. Nội dung của các submodule có thể chưa được tải và checkout. Thư mục submodule có thể xuất hiện nhưng chưa chứa working tree đã khởi tạo.

Để khởi tạo và checkout các submodule theo đúng commit mà superproject yêu cầu, dùng:

~~~bash
git submodule update --init --recursive
~~~

Đây là lệnh thường cần chạy sau khi clone một repository có submodule hoặc sau khi chuyển sang một commit có thay đổi gitlink.

Các tùy chọn có ý nghĩa:

- **update:** đồng bộ working tree submodule với commit được ghi trong superproject.
- **--init:** khởi tạo cấu hình cho những submodule chưa được đăng ký trong cấu hình local.
- **--recursive:** tiếp tục khởi tạo và cập nhật các submodule lồng bên trong submodule khác.

Lệnh này đưa submodule về commit đã được superproject ghim (pinned commit). Nó không mặc định lấy commit mới nhất trên nhánh remote của từng submodule.

## Superproject ghi nhận submodule như thế nào?

Superproject không lưu toàn bộ nội dung tệp của submodule trong commit của chính nó. Nó lưu một **gitlink**: đường dẫn của submodule cùng mã commit mà superproject muốn sử dụng.

File .gitmodules được commit trong superproject và chứa thông tin như tên submodule, đường dẫn và URL:

~~~ini
[submodule "ui-kit"]
    path = libs/ui-kit
    url = https://example.com/team/ui-kit.git

[submodule "data-client"]
    path = libs/data-client
    url = https://example.com/team/data-client.git
~~~

Trong ví dụ:

- ui-kit và data-client là tên submodule.
- path là vị trí checkout trong superproject.
- url là địa chỉ repository của submodule.

Tên submodule là tên cấu hình; nó thường giống đường dẫn nhưng không bắt buộc phải giống. Superproject lưu gitlink tương ứng với đường dẫn, còn .gitmodules cung cấp thông tin để Git biết phải lấy repository nào.

Có thể xem các gitlink trong commit hiện tại:

~~~bash
git ls-tree HEAD
git ls-tree HEAD libs/ui-kit
~~~

Một gitlink thường có mode 160000, ví dụ:

~~~text
160000 commit 8a7b6c5d...    libs/ui-kit
~~~

Mã commit phía sau là commit mà superproject yêu cầu submodule checkout. Đây là lý do hai người clone cùng một commit superproject sẽ dùng cùng phiên bản submodule, miễn là commit đó có thể truy cập trên repository submodule.

Có thể xem trạng thái gitlink trong index:

~~~bash
git ls-files --stage -- libs/ui-kit
~~~

Nếu submodule được cập nhật sang commit khác, superproject sẽ thấy đường dẫn submodule thay đổi như một thay đổi gitlink. Để chia sẻ phiên bản mới, cần commit trong repository submodule, sau đó stage đường dẫn submodule ở superproject và commit thay đổi gitlink.

## Khác biệt giữa .gitmodules và cấu hình local

Hai nơi cấu hình có vai trò khác nhau:

| Nơi lưu | Vai trò |
|---|---|
| .gitmodules | Metadata được version control và chia sẻ cùng superproject, thường gồm path và URL |
| .git/config của superproject | Cấu hình local của submodule đã được khởi tạo trên bản clone hiện tại |
| Cấu hình trong repository submodule | Thiết lập riêng của repository con, ví dụ remote và danh tính commit |

Khi chạy git submodule init, Git lấy thông tin URL từ .gitmodules và ghi cấu hình tương ứng vào .git/config của superproject. Lệnh init không tự clone và checkout nội dung submodule.

Nếu cấu hình local đã tồn tại, init không ghi đè tùy chỉnh URL hiện có. Khi URL trong .gitmodules thay đổi và cần đồng bộ lại cấu hình local, dùng git submodule sync.

Đọc file .gitmodules:

~~~bash
git config --file .gitmodules --list
~~~

Xem cấu hình submodule local:

~~~bash
git config --local --get-regexp '^submodule\.'
~~~

Một repository có thể chứa URL tương đối, ví dụ:

~~~ini
[submodule "ui-kit"]
    path = libs/ui-kit
    url = ../ui-kit.git
~~~

URL tương đối được Git phân giải dựa trên URL remote của superproject. Điều này hữu ích khi nhiều repository nằm cùng một tổ chức hoặc cùng một máy chủ. Nếu clone superproject từ một mirror hoặc nguồn có cấu trúc khác, cần xác nhận URL sau khi phân giải có trỏ tới đúng repository submodule hay không.

## Quy trình khởi tạo submodule sau khi clone

### Bước 1: Clone superproject

Clone repository chính như bình thường:

~~~bash
git clone https://example.com/team/inventory-app.git
cd inventory-app
~~~

Ở thời điểm này, thư mục submodule có thể chưa được khởi tạo. Kiểm tra:

~~~bash
git submodule status
~~~

Ví dụ:

~~~text
-8a7b6c5d... libs/ui-kit
-1f2e3d4c... libs/data-client
~~~

Dấu - ở đầu dòng cho biết submodule chưa được khởi tạo. Mã commit bên cạnh là commit mà superproject yêu cầu.

### Bước 2: Khởi tạo và cập nhật toàn bộ submodule

Chạy:

~~~bash
git submodule update --init --recursive
~~~

Git sẽ:

1. Đọc khai báo submodule từ .gitmodules.
2. Khởi tạo cấu hình local cho các submodule chưa được đăng ký.
3. Clone repository submodule nếu bản clone cần thiết chưa tồn tại.
4. Fetch dữ liệu cần thiết từ remote submodule.
5. Checkout commit được ghi trong gitlink của superproject.
6. Tiếp tục thực hiện các bước tương ứng cho submodule lồng nhau.

Nếu repository có nhiều submodule, quá trình này có thể cần thời gian và quyền truy cập tới nhiều remote khác nhau.

### Bước 3: Xác nhận trạng thái

Sau khi lệnh hoàn tất:

~~~bash
git submodule status --recursive
git status
~~~

Ví dụ kết quả:

~~~text
 8a7b6c5d... libs/ui-kit (v2.4.0-3-g8a7b6c5)
 1f2e3d4c... libs/data-client
~~~

Không có dấu -, + hoặc U ở đầu dòng thường cho biết submodule đã được khởi tạo và đang ở commit được superproject ghi nhận. Phần thông tin trong ngoặc có thể là mô tả nhánh, tag hoặc khoảng cách commit, tùy trạng thái repository.

Nếu submodule đang ở detached HEAD, đó thường là trạng thái bình thường khi Git checkout commit được ghim bởi superproject. Điều này giúp bảo đảm mọi thành viên dùng đúng phiên bản dependency.

## Khởi tạo submodule ngay trong lúc clone

Nếu muốn clone superproject và tải toàn bộ submodule ngay từ đầu, có thể dùng:

~~~bash
git clone --recurse-submodules https://example.com/team/inventory-app.git
~~~

Tùy chọn --recurse-submodules yêu cầu Git khởi tạo và cập nhật submodule trong quá trình clone. Với repository có submodule lồng nhau, thao tác này cũng xử lý đệ quy.

Lệnh trên thường tương đương quy trình:

~~~bash
git clone https://example.com/team/inventory-app.git
cd inventory-app
git submodule update --init --recursive
~~~

Nếu đã clone mà không dùng --recurse-submodules, không cần clone lại. Chỉ cần chạy git submodule update --init --recursive từ thư mục gốc superproject.

## Cập nhật submodule sau khi chuyển nhánh hoặc pull

Một commit mới của superproject có thể thay đổi gitlink của submodule. Ví dụ, nhánh main được cập nhật để dùng phiên bản mới của libs/ui-kit.

Sau khi lấy commit mới của superproject:

~~~bash
git switch main
git pull --ff-only
~~~

Kiểm tra trạng thái submodule:

~~~bash
git submodule status --recursive
~~~

Nếu submodule chưa ở đúng commit mà superproject yêu cầu, cập nhật:

~~~bash
git submodule update --init --recursive
~~~

Lệnh này đưa từng submodule về commit được ghi trong commit superproject hiện tại. Nó có thể clone submodule mới được thêm, checkout commit mới của submodule đã tồn tại và khởi tạo các submodule lồng nhau.

**Fetch hoặc pull superproject không bảo đảm mọi submodule đã được khởi tạo và checkout đệ quy.** Một số cấu hình hoặc tùy chọn recurse có thể yêu cầu Git fetch submodule trong quá trình pull; để chủ động khởi tạo và checkout theo gitlink của commit superproject, hãy chạy submodule update --init --recursive.

### Khi superproject thay đổi phiên bản submodule

Giả sử trước đó superproject ghim libs/ui-kit ở commit A. Một commit mới trên main thay gitlink sang commit B.

~~~text
Superproject trước:
main -> commit P1 -> libs/ui-kit @ A

Superproject sau:
main -> commit P2 -> libs/ui-kit @ B
~~~

Sau khi cập nhật superproject tới P2, chạy:

~~~bash
git submodule update --init --recursive
~~~

Git checkout libs/ui-kit tại B. Nếu submodule đang có thay đổi cục bộ có thể bị ghi đè, Git có thể từ chối cập nhật. Hãy kiểm tra và bảo toàn thay đổi đó trước khi tiếp tục.

### Cập nhật một submodule cụ thể

Nếu chỉ cần khởi tạo hoặc cập nhật một đường dẫn:

~~~bash
git submodule update --init --recursive -- libs/ui-kit
~~~

Cách này hữu ích trong repository lớn khi bạn chỉ cần làm việc với một phần phụ thuộc. Tuy nhiên, nếu submodule được chọn có submodule lồng nhau, tùy chọn --recursive vẫn yêu cầu cập nhật các cấp con của nó.

## --init và --recursive phối hợp ra sao?

Ba cách gọi sau có phạm vi khác nhau:

~~~bash
# Chỉ cập nhật submodule đã được khởi tạo
git submodule update

# Khởi tạo và cập nhật các submodule cấp hiện tại
git submodule update --init

# Khởi tạo, cập nhật cả các submodule lồng nhau
git submodule update --init --recursive
~~~

| Tùy chọn | Tác dụng |
|---|---|
| Không có --init | Cập nhật các submodule đã được khởi tạo |
| --init | Đăng ký cấu hình cho submodule chưa khởi tạo rồi cập nhật |
| --recursive | Tiếp tục xử lý các submodule lồng bên trong |
| --init --recursive | Khởi tạo và cập nhật cả cây submodule theo commit superproject yêu cầu |

Nếu dự án có submodule lồng nhau mà bỏ --recursive, các repository con sâu hơn có thể vẫn chưa được khởi tạo. Vì vậy, khi chuẩn bị môi trường phát triển hoặc CI, dùng --init --recursive thường giúp checkout đầy đủ cây phụ thuộc.

## Hiểu đúng commit được cập nhật: commit ghim và nhánh remote

Một nhầm lẫn phổ biến là cho rằng:

~~~bash
git submodule update --init --recursive
~~~

sẽ lấy commit mới nhất của nhánh main trong từng submodule. Thực tế, lệnh mặc định checkout commit được ghi trong gitlink của superproject.

Ví dụ .gitmodules khai báo URL của libs/ui-kit, còn gitlink trong commit superproject trỏ tới commit 8a7b6c5. Dù remote của submodule đã có commit mới hơn, lệnh update mặc định vẫn checkout 8a7b6c5.

Cách làm này giúp build có thể tái lập: commit superproject quyết định phiên bản chính xác của từng submodule.

Nếu mục tiêu là cập nhật submodule theo nhánh remote mới nhất, đó là một quy trình khác, thường sử dụng --remote:

~~~bash
git submodule update --remote --recursive
~~~

Tùy chọn --remote lấy trạng thái mới từ remote-tracking branch theo cấu hình của submodule, thay vì chỉ checkout gitlink hiện tại. Nhánh có thể được chỉ định bằng khóa submodule.<name>.branch trong .gitmodules hoặc cấu hình local; nếu không chỉ định, Git dùng nhánh remote HEAD. Kết quả có thể làm gitlink trong superproject thay đổi; cần review và commit thay đổi đó như một thay đổi dependency có chủ đích.

Không dùng --remote thay cho lệnh init/update thông thường khi cần tái tạo đúng phiên bản mà một commit superproject đã ghim.

## Cập nhật URL submodule khi địa chỉ repository thay đổi

Nếu nhóm chuyển repository submodule sang URL mới, người maintain cập nhật .gitmodules và commit thay đổi trong superproject.

Ví dụ URL thay đổi:

~~~ini
[submodule "ui-kit"]
    path = libs/ui-kit
    url = https://git.example.com/platform/ui-kit.git
~~~

Trên bản clone đã tồn tại, cấu hình local có thể vẫn giữ URL cũ. Đồng bộ URL từ .gitmodules:

~~~bash
git submodule sync --recursive
~~~

Sau đó khởi tạo hoặc cập nhật:

~~~bash
git submodule update --init --recursive
~~~

Kiểm tra URL của submodule:

~~~bash
git -C libs/ui-kit remote -v
~~~

sync cập nhật URL đã đăng ký trong cấu hình local theo khai báo trong .gitmodules; nó không tự thay đổi URL trong file .gitmodules và không commit thay đổi cho superproject.

Nếu URL mới yêu cầu quyền truy cập khác, hãy xác nhận SSH key, credential helper hoặc quyền đọc repository submodule. Không nhúng token hay mật khẩu vào URL được commit.

## Kiểm tra trạng thái submodule bằng git submodule status

Lệnh:

~~~bash
git submodule status --recursive
~~~

hiển thị commit hiện tại của mỗi submodule và một ký hiệu trạng thái ở đầu dòng.

| Ký hiệu đầu dòng | Ý nghĩa |
|---|---|
| Dấu cách | Submodule đã khởi tạo và đang ở commit được superproject ghi nhận |
| - | Submodule chưa được khởi tạo |
| + | Submodule đang checkout ở commit khác gitlink của superproject |
| U | Gitlink đang có xung đột chưa được giải quyết |

Ví dụ:

~~~text
-8a7b6c5... libs/ui-kit
+1f2e3d4... libs/data-client
U3a4b5c6... libs/legacy-client
~~~

Cách đọc:

- libs/ui-kit chưa được khởi tạo.
- libs/data-client đã có working tree nhưng đang ở commit khác với commit superproject yêu cầu.
- libs/legacy-client có xung đột gitlink cần giải quyết.

Sau khi chạy update và xử lý các xung đột cần thiết, chạy lại status để xác nhận.

Có thể xem trạng thái bên trong từng submodule:

~~~bash
git -C libs/ui-kit status
git -C libs/data-client log -1 --oneline --decorate
~~~

Hoặc duyệt các submodule đã khởi tạo:

~~~bash
git submodule foreach --recursive 'git status --short'
~~~

Lệnh foreach chạy lệnh trong từng submodule. Tùy chọn --recursive tiếp tục đi vào các submodule lồng nhau.

## Detached HEAD trong submodule là bình thường

Sau khi git submodule update, submodule thường ở trạng thái detached HEAD vì Git checkout trực tiếp commit được ghi trong gitlink. Ví dụ:

~~~bash
git -C libs/ui-kit status
~~~

Có thể hiển thị:

~~~text
HEAD detached at 8a7b6c5
nothing to commit, working tree clean
~~~

Điều này không có nghĩa submodule bị lỗi hoặc mất nhánh. Superproject đang yêu cầu một commit cụ thể chứ không yêu cầu một nhánh phát triển.

Nếu cần phát triển bên trong submodule, hãy chuyển sang nhánh phù hợp trong repository con:

~~~bash
git -C libs/ui-kit switch -c feature/button-accessibility
~~~

Sau khi commit và push thay đổi trong submodule, quay về superproject và stage đường dẫn submodule để cập nhật gitlink:

~~~bash
git add libs/ui-kit
git commit -m "Update ui-kit submodule"
~~~

Trước khi chia sẻ commit superproject, bảo đảm commit mới của submodule đã được push tới remote mà các thành viên khác có thể truy cập. Nếu superproject ghim một commit chưa được chia sẻ, người khác có thể không fetch được submodule khi clone hoặc update.

## Lỗi thường gặp khi khởi tạo và cập nhật

### Submodule chưa được khởi tạo

Dấu - trong git submodule status cho biết submodule chưa được khởi tạo.

Chạy:

~~~bash
git submodule update --init --recursive
~~~

Nếu chỉ cần một đường dẫn:

~~~bash
git submodule update --init --recursive -- libs/ui-kit
~~~

### Không truy cập được repository submodule

Lỗi có thể do URL sai, repository đã chuyển, thiếu quyền hoặc credential chưa được cấu hình.

Kiểm tra:

~~~bash
git config --file .gitmodules --list
git submodule sync --recursive
git -C libs/ui-kit remote -v
~~~

Sau khi xác nhận URL đúng, thử cập nhật lại:

~~~bash
git submodule update --init --recursive
~~~

Nếu dùng SSH, kiểm tra key và quyền truy cập. Nếu dùng HTTPS, kiểm tra credential manager hoặc cơ chế xác thực được tổ chức hỗ trợ. Không đưa thông tin xác thực vào .gitmodules.

### URL đã đổi nhưng bản clone vẫn dùng địa chỉ cũ

File .gitmodules có thể đã cập nhật nhưng .git/config trên máy vẫn chứa URL cũ. Đồng bộ:

~~~bash
git submodule sync --recursive
git submodule update --init --recursive
~~~

Sau đó xác nhận bằng git -C <path> remote -v.

### Submodule đang ở sai commit

Nếu status có dấu +, submodule đang checkout ở commit khác với gitlink. Để đưa về commit được superproject yêu cầu:

~~~bash
git submodule update --init --recursive
~~~

Nếu lệnh từ chối vì có thay đổi cục bộ, kiểm tra bên trong submodule trước:

~~~bash
git -C libs/ui-kit status
git -C libs/ui-kit diff
git -C libs/ui-kit diff --cached
~~~

Commit, stash hoặc lưu riêng thay đổi cần giữ theo quy trình của nhóm. Chỉ sau khi bảo toàn dữ liệu mới cập nhật submodule. Không dùng tùy chọn force để ghi đè thay đổi chưa được kiểm tra.

### Submodule lồng nhau vẫn chưa được tải

Nếu submodule cấp ngoài đã checkout nhưng bên trong còn thư mục con chưa khởi tạo, kiểm tra:

~~~bash
git submodule status --recursive
~~~

Sau đó chạy:

~~~bash
git submodule update --init --recursive
~~~

Đảm bảo các URL và quyền truy cập của từng cấp submodule đều hợp lệ.

### Git báo tệp cục bộ sẽ bị ghi đè

Có thể submodule đang có sửa đổi tracked hoặc tệp untracked trùng đường dẫn với nội dung cần checkout.

Kiểm tra:

~~~bash
git -C libs/ui-kit status --short
git -C libs/ui-kit diff
git -C libs/ui-kit ls-files --others --exclude-standard
~~~

Di chuyển hoặc lưu các tệp cần giữ, commit/stash thay đổi phù hợp, rồi chạy update lại. Không xóa thư mục submodule bằng tay khi chưa xác định dữ liệu cục bộ có cần bảo toàn không.

### Superproject báo gitlink conflict

Khi hai nhánh thay đổi commit được tham chiếu bởi cùng một submodule, superproject có thể báo xung đột ở đường dẫn gitlink.

Kiểm tra:

~~~bash
git status
git ls-files -u -- libs/ui-kit
~~~

Xem các commit đang được index giữ ở từng stage nếu có:

~~~bash
git ls-files --stage -- libs/ui-kit
~~~

Xác định phiên bản submodule cần dùng theo mục tiêu merge, bảo đảm commit đó có thể truy cập, rồi checkout đúng commit trong submodule. Stage lại đường dẫn ở superproject:

~~~bash
git add libs/ui-kit
git status
~~~

Sau khi không còn conflict, hoàn tất merge theo quy trình của repository. git submodule update --init --recursive không tự quyết định thay nhóm rằng nên chọn gitlink từ phía nào khi có conflict.

## Quy trình mẫu cho thành viên mới

Một thành viên mới clone dự án và cần chuẩn bị toàn bộ submodule:

~~~bash
# Clone superproject
git clone https://example.com/team/inventory-app.git
cd inventory-app

# Khởi tạo và cập nhật toàn bộ submodule, kể cả submodule lồng nhau
git submodule update --init --recursive

# Kiểm tra commit và trạng thái của từng submodule
git submodule status --recursive

# Xác nhận trạng thái repository chính
git status
~~~

Nếu dự án yêu cầu clone một bước:

~~~bash
git clone --recurse-submodules https://example.com/team/inventory-app.git
cd inventory-app
git submodule status --recursive
~~~

Sau khi chuyển sang nhánh khác hoặc pull commit mới:

~~~bash
git switch feature/report
git pull --ff-only
git submodule update --init --recursive
git submodule status --recursive
~~~

Dùng đúng nhánh và cách pull theo quy ước của nhóm. Mục tiêu là đảm bảo các submodule checkout theo gitlink của commit superproject đang dùng.

## Quy trình mẫu trong CI

CI thường clone repository từ đầu, vì vậy cần chủ động khởi tạo submodule. Một bước checkout có thể thực hiện:

~~~bash
git clone <repository-url> project
cd project
git submodule update --init --recursive
~~~

Hoặc cấu hình action/checkout task của nền tảng CI để bật tùy chọn recursive submodule. Cách cấu hình cụ thể tùy hệ thống CI.

Trong pipeline, nên xác nhận:

- Commit superproject đúng với revision pipeline đang build.
- Mọi submodule cần thiết đã được khởi tạo.
- Submodule đang ở commit được gitlink yêu cầu.
- Submodule lồng nhau đã được cập nhật.
- Runner có quyền đọc tất cả repository submodule.
- Các commit submodule được tham chiếu đã tồn tại trên remote.

Không cập nhật --remote tùy tiện trong CI nếu mục tiêu là build tái lập từ một commit superproject. CI thông thường nên sử dụng đúng commit gitlink đã được review và commit.

## Checklist sau khi chạy update --init --recursive

- [ ] Đang chạy lệnh từ thư mục gốc của superproject.
- [ ] .gitmodules có khai báo đúng path và URL.
- [ ] Cấu hình local đã được khởi tạo hoặc đồng bộ nếu URL thay đổi.
- [ ] Lệnh git submodule update --init --recursive hoàn tất thành công.
- [ ] git submodule status --recursive không còn dấu -, + hoặc U ngoài dự kiến.
- [ ] Mỗi submodule đang ở commit được gitlink yêu cầu.
- [ ] Các submodule lồng nhau đã được khởi tạo.
- [ ] Không có thay đổi cục bộ hoặc tệp untracked bị ghi đè.
- [ ] Các commit submodule có thể truy cập từ remote của nhóm.
- [ ] Build/test của superproject chạy được với các dependency đã checkout.

## Ghi nhớ

Superproject lưu đường dẫn và commit cụ thể của từng submodule dưới dạng gitlink; .gitmodules cung cấp URL và metadata để Git khởi tạo repository con. Sau khi clone, chuyển nhánh hoặc cập nhật superproject, dùng git submodule update --init --recursive để khởi tạo submodule còn thiếu, checkout đúng commit được ghim và xử lý cả submodule lồng nhau. Lệnh mặc định không lấy phiên bản mới nhất của nhánh remote. Hãy kiểm tra git submodule status --recursive, bảo toàn thay đổi cục bộ và xác nhận mọi commit submodule đều có thể truy cập trước khi build hoặc chia sẻ thay đổi.

