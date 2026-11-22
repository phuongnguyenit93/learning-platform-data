# Trạng thái detached HEAD và cách phát triển trực tiếp trong submodule

Khi làm việc với Git submodule, bạn có thể thấy thông báo **HEAD detached** ngay sau khi clone hoặc cập nhật repository cha. Đây thường là trạng thái bình thường: repository cha ghi lại chính xác commit mà submodule phải sử dụng, vì vậy Git checkout commit đó thay vì tự chọn một branch đang di chuyển.

Detached HEAD không ngăn bạn đọc mã nguồn, build hoặc thậm chí tạo commit trong submodule. Tuy nhiên, nếu tạo commit khi HEAD chưa gắn với branch, commit mới chưa được một branch local giữ lại. Khi chuyển sang commit khác, bạn có thể khó tìm lại commit đó nếu chưa tạo ref để giữ nó.

Để phát triển trực tiếp trong submodule, hãy tạo hoặc chuyển sang một branch bên trong repository con, thực hiện commit và push commit đó lên remote của submodule. Sau đó quay lại repository cha, stage đường dẫn submodule và commit gitlink mới. Hai repository có lịch sử riêng và cần được chia sẻ theo đúng thứ tự.

## 1. Vì sao submodule thường ở trạng thái detached HEAD?

Submodule là một repository Git độc lập được gắn vào một repository khác, thường gọi là superproject hoặc repository cha. Trong tree của repository cha, Git không lưu toàn bộ nội dung commit của repository con. Nó lưu một **gitlink**: một entry trỏ tới mã commit cụ thể của submodule.

Ví dụ, repository cha có thể ghi nhận:

~~~text
Ứng dụng
├── src/
├── config/
└── libs/payment-engine  -> commit 8a31f2c của repository payment-engine
~~~

Khi người khác checkout một commit của repository cha, Git cần đưa submodule về đúng commit đã được ghi nhận. Commit đó có thể không phải tip mới nhất của branch main trong repository con. Vì vậy, Git checkout trực tiếp mã commit được ghim và HEAD ở trạng thái detached.

Một lần clone với submodule:

~~~sh
git clone --recurse-submodules https://example.com/team/store-app.git
~~~

Hoặc nếu repository cha đã được clone:

~~~sh
git submodule update --init --recursive
~~~

Các lệnh này khởi tạo submodule và checkout commit mà repository cha yêu cầu. Trong chế độ cập nhật mặc định, submodule thường ở detached HEAD.

### 1.1. Detached HEAD có phải là lỗi không?

Không. Đây là cách Git bảo đảm repository cha tham chiếu tới một phiên bản submodule xác định. Nếu Git tự động checkout branch main của submodule, cùng một commit của repository cha có thể nhận nội dung submodule khác nhau ở những thời điểm khác nhau khi main tiến lên.

Detached HEAD phù hợp khi:

- Chỉ cần build hoặc chạy dự án theo phiên bản đã ghim.
- Muốn kiểm tra chính xác mã nguồn submodule mà repository cha yêu cầu.
- Không cần phát triển hoặc tạo commit mới trong submodule.

Khi cần sửa mã nguồn submodule, hãy chuyển sang một branch để các commit mới có một tên ref giữ lại.

## 2. Nhận biết trạng thái của submodule

Giả sử submodule nằm tại đường dẫn libs/payment-engine. Có thể kiểm tra trạng thái từ repository cha:

~~~sh
git submodule status
git status --short
~~~

Lệnh git submodule status hiển thị commit mà mỗi submodule đang checkout. Ký tự ở đầu dòng giúp nhận biết tình trạng:

| Ký tự | Ý nghĩa |
|---|---|
| Dấu cách | Submodule đã khởi tạo và đang ở commit được repository cha ghi nhận |
| Dấu trừ (-) | Submodule chưa được khởi tạo |
| Dấu cộng (+) | Commit đang checkout khác commit được repository cha ghi nhận |
| U | Submodule đang có xung đột merge |

Đi vào repository con và kiểm tra trực tiếp:

~~~sh
git -C libs/payment-engine status -sb
git -C libs/payment-engine branch --show-current
git -C libs/payment-engine rev-parse --short HEAD
git -C libs/payment-engine log -1 --oneline --decorate
~~~

Nếu HEAD detached, git status thường thông báo HEAD detached tại một mã commit; git branch --show-current trả về chuỗi rỗng vì không có branch hiện tại.

Có thể xem remote của submodule:

~~~sh
git -C libs/payment-engine remote -v
~~~

Đừng nhầm remote của repository cha với remote của submodule. Hai repository có thể dùng hai URL, hai quyền truy cập và hai quy trình push khác nhau.

## 3. Tạo branch trong submodule trước khi phát triển

### 3.1. Tạo branch mới từ commit đang checkout

Khi đang ở detached HEAD tại commit mà repository cha đã ghim, tạo branch mới ngay tại commit đó:

~~~sh
git -C libs/payment-engine switch -c feature/add-refund-support
~~~

Lệnh này tạo branch feature/add-refund-support trỏ tới commit hiện tại và chuyển HEAD sang branch đó. Các thay đổi tiếp theo được commit sẽ làm branch di chuyển, giúp lịch sử phát triển được giữ lại.

Kiểm tra:

~~~sh
git -C libs/payment-engine branch --show-current
git -C libs/payment-engine status -sb
~~~

Branch hiện tại phải là feature/add-refund-support.

### 3.2. Chuyển sang branch đã tồn tại

Nếu branch đã có local:

~~~sh
git -C libs/payment-engine switch feature/add-refund-support
~~~

Nếu branch chỉ tồn tại trên remote:

~~~sh
git -C libs/payment-engine fetch origin
git -C libs/payment-engine switch --track -c feature/add-refund-support origin/feature/add-refund-support
~~~

Lệnh switch --track tạo branch local theo dõi branch remote tương ứng. Nếu branch local đã tồn tại, chỉ cần chuyển sang branch đó và cập nhật theo quy ước của nhóm.

### 3.3. Chọn điểm bắt đầu phù hợp

Bạn có thể phát triển từ commit submodule mà repository cha đang ghim, hoặc từ một branch mới hơn trong repository con. Hai lựa chọn có ý nghĩa khác nhau:

- **Bắt đầu từ commit đã ghim:** phù hợp khi thay đổi phải tương thích trực tiếp với phiên bản submodule mà ứng dụng hiện tại đang sử dụng.
- **Bắt đầu từ branch mới hơn:** phù hợp khi nhóm muốn nâng submodule lên một phiên bản phát triển mới; cần kiểm tra tương thích và cập nhật gitlink trong repository cha.

Trước khi chọn, xem lịch sử và trao đổi với người phụ trách submodule nếu branch nền hoặc chính sách phát hành chưa rõ:

~~~sh
git -C libs/payment-engine fetch origin
git -C libs/payment-engine log --oneline --graph --decorate --all -15
~~~

Không mặc định branch main của submodule luôn là điểm bắt đầu đúng. Repository cha có thể đang dùng một release branch hoặc một commit đã được kiểm thử riêng.

## 4. Phát triển và commit trực tiếp trong submodule

Sau khi đã ở branch, làm việc như trong một repository Git bình thường.

### 4.1. Kiểm tra thay đổi

~~~sh
git -C libs/payment-engine status
git -C libs/payment-engine diff
git -C libs/payment-engine diff --check
~~~

Chỉ sửa các file thuộc repository con. Không đưa thay đổi của repository cha vào commit của submodule.

### 4.2. Stage và commit trong repository con

~~~sh
git -C libs/payment-engine add src/refund-service.ts tests/refund-service.test.ts
git -C libs/payment-engine diff --cached
git -C libs/payment-engine commit -m "Add refund support"
~~~

Commit này được tạo trong repository payment-engine. Nó không tự động tạo commit trong repository cha.

Kiểm tra:

~~~sh
git -C libs/payment-engine status -sb
git -C libs/payment-engine log -1 --oneline
~~~

Nếu working tree còn thay đổi, xác định phần nào chưa được stage hoặc commit. Không nên quay lại repository cha và cập nhật gitlink trước khi hiểu rõ trạng thái repository con.

### 4.3. Điều gì xảy ra nếu commit khi HEAD detached?

Git vẫn cho phép tạo commit khi HEAD detached. Commit đó có mã SHA và có thể xem bằng git log, nhưng không tự được gắn với branch. Nếu sau đó checkout commit khác, commit mới có thể không còn được tham chiếu bởi branch nào.

Nếu đã tạo commit khi detached, có thể giữ lại nó bằng cách tạo branch ngay tại commit hiện tại:

~~~sh
git -C libs/payment-engine switch -c rescue/refund-work
~~~

Branch mới sẽ trỏ tới commit HEAD đang đứng, qua đó giữ commit trong lịch sử có tên. Thực hiện việc này trước khi chuyển sang commit khác nếu muốn bảo toàn công việc.

## 5. Push commit lên remote của submodule

Repository cha chỉ có thể tham chiếu một commit submodule hữu ích cho người khác nếu commit đó có thể được lấy từ remote mà họ có quyền truy cập.

### 5.1. Push branch lần đầu

~~~sh
git -C libs/payment-engine push -u origin feature/add-refund-support
~~~

Tùy chọn -u thiết lập upstream để những lần push tiếp theo có thể dùng:

~~~sh
git -C libs/payment-engine push
~~~

Nếu remote của submodule dùng tên khác origin, hãy dùng remote đúng mà lệnh git remote -v đã hiển thị.

### 5.2. Review thay đổi của submodule

Nếu submodule do một nhóm khác quản lý, hãy mở pull request hoặc merge request trong repository con theo quy trình của nhóm đó. Repository cha có thể tiếp tục tham chiếu commit branch trong thời gian phát triển, nhưng trước khi tích hợp vào branch chính hoặc phát hành, nên dùng commit đã được review và chia sẻ ổn định.

Khi branch bị bảo vệ, hãy push branch công việc và chờ review thay vì cố đẩy trực tiếp vào branch chính.

### 5.3. Vì sao nên push submodule trước repository cha?

Giả sử repository cha ghi nhận commit mới 91ab23c của submodule. Nếu commit đó chỉ tồn tại trên máy của bạn, người khác clone repository cha sẽ không lấy được nội dung tương ứng từ remote submodule.

Vì vậy, thứ tự nên là:

1. Commit thay đổi trong submodule.
2. Push commit hoặc branch chứa commit đó lên remote của submodule.
3. Quay lại repository cha và cập nhật gitlink.
4. Commit và push thay đổi gitlink của repository cha.

Thứ tự này giúp commit được tham chiếu có thể truy cập khi người khác khởi tạo submodule.

## 6. Cập nhật gitlink trong repository cha

Sau khi commit trong submodule, repository cha nhận thấy đường dẫn submodule đang ở commit khác với commit đã ghi trước đó.

Chuyển về thư mục gốc repository cha:

~~~sh
cd ../..
git status --short
git diff --submodule=log
~~~

Đường dẫn submodule có thể được hiển thị là modified với thông tin new commits. Đây là dấu hiệu gitlink đang trỏ tới commit mới.

Stage đường dẫn submodule:

~~~sh
git add libs/payment-engine
git diff --cached --submodule=log
git status --short
~~~

Thao tác git add ở repository cha ghi nhận commit mà submodule đang checkout. Nó không stage từng file bên trong repository con; các file đó đã được commit ở repository con.

Tạo commit trong repository cha:

~~~sh
git commit -m "Update payment-engine submodule"
~~~

Sau đó push repository cha:

~~~sh
git push
~~~

Commit của repository cha chứa gitlink mới, tức mã commit cụ thể của submodule. Khi người khác checkout commit cha đó rồi chạy git submodule update --init --recursive, Git sẽ checkout đúng commit submodule đã được ghim.

## 7. Hiểu vai trò của .gitmodules và branch trong submodule

File .gitmodules ở repository cha lưu thông tin cần thiết để Git biết submodule nằm ở đâu và lấy từ URL nào. Ví dụ:

~~~ini
[submodule "libs/payment-engine"]
    path = libs/payment-engine
    url = https://example.com/team/payment-engine.git
    branch = main
~~~

Các trường quan trọng:

- path: đường dẫn submodule trong repository cha.
- url: địa chỉ repository con.
- branch: branch remote được dùng khi chạy thao tác cập nhật theo remote như git submodule update --remote.

Trường branch là tùy chọn. Nếu không khai báo, Git dùng branch mặc định của remote theo cơ chế của submodule update --remote.

### 7.1. Khai báo branch dùng cho cập nhật remote

Có thể đặt branch bằng lệnh:

~~~sh
git submodule set-branch --branch main -- libs/payment-engine
git diff -- .gitmodules
git add .gitmodules
git commit -m "Track payment-engine main branch"
~~~

Thay đổi này cập nhật cấu hình trong repository cha. Nó không biến submodule đang detached thành branch main ngay lập tức và cũng không thay đổi gitlink đang được ghi nhận.

Một giá trị đặc biệt là dấu chấm:

~~~ini
branch = .
~~~

Giá trị này yêu cầu Git dùng branch cùng tên với branch hiện tại của superproject khi thực hiện cập nhật remote. Cách này chỉ phù hợp khi nhóm có quy ước branch tương ứng ở cả hai repository.

### 7.2. git submodule update --remote có ý nghĩa gì?

Lệnh:

~~~sh
git submodule update --remote -- libs/payment-engine
~~~

yêu cầu Git fetch remote branch được cấu hình cho submodule rồi cập nhật submodule tới commit mới nhất của branch đó. Mặc định, phương thức cập nhật là checkout nên submodule thường lại ở detached HEAD.

Lệnh này khác với git submodule update thông thường:

- git submodule update checkout commit được repository cha ghi nhận.
- git submodule update --remote lấy commit mới từ branch remote được cấu hình và cập nhật submodule theo commit đó.

Sau khi dùng --remote, repository cha có thể báo gitlink đã thay đổi. Nếu muốn chia sẻ phiên bản mới, cần stage đường dẫn submodule và commit gitlink trong repository cha.

### 7.3. Cập nhật remote branch trong khi vẫn làm việc trên branch local

Nếu đang phát triển trên branch riêng và muốn tích hợp commit mới từ branch remote:

~~~sh
git -C libs/payment-engine fetch origin
git -C libs/payment-engine switch feature/add-refund-support
git -C libs/payment-engine merge origin/main
~~~

Hoặc dùng rebase nếu chính sách nhóm cho phép và branch chưa được người khác dựa vào:

~~~sh
git -C libs/payment-engine rebase origin/main
~~~

Git cũng hỗ trợ yêu cầu submodule update hợp nhất hoặc rebase commit remote vào branch đang checkout:

~~~sh
git submodule update --remote --merge -- libs/payment-engine
~~~

hoặc:

~~~sh
git submodule update --remote --rebase -- libs/payment-engine
~~~

Các tùy chọn --merge và --rebase giữ submodule trên branch hiện tại trong khi tích hợp commit được fetch, nếu branch và working tree đáp ứng điều kiện. Hãy kiểm tra trạng thái và giải quyết conflict trong repository con như một repository bình thường.

## 8. Làm việc với detached HEAD mà không mất công việc

### 8.1. Chưa sửa file và chỉ cần sử dụng submodule

Nếu chỉ cần build hoặc chạy dự án theo commit đã ghim, có thể giữ detached HEAD. Không cần tạo branch chỉ để loại bỏ thông báo detached HEAD.

### 8.2. Đã sửa file nhưng chưa commit

Nếu HEAD detached và đã có thay đổi chưa commit, tạo branch ngay tại vị trí hiện tại thường giữ nguyên working tree:

~~~sh
git -C libs/payment-engine switch -c feature/local-fix
~~~

Sau đó kiểm tra:

~~~sh
git -C libs/payment-engine status
git -C libs/payment-engine diff
~~~

Nếu Git không cho chuyển branch vì thay đổi có thể bị ghi đè, đừng ép checkout. Hãy commit phần thay đổi phù hợp hoặc stash sau khi xem kỹ nội dung, rồi chuyển branch.

### 8.3. Đã commit trong detached HEAD

Nếu vừa tạo commit khi detached và chưa chuyển đi nơi khác, tạo branch để giữ commit:

~~~sh
git -C libs/payment-engine switch -c rescue/keep-detached-commit
~~~

Sau đó push branch nếu cần chia sẻ:

~~~sh
git -C libs/payment-engine push -u origin rescue/keep-detached-commit
~~~

Nếu đã chuyển sang commit khác và không còn thấy commit mới trong branch, có thể tìm lại bằng reflog:

~~~sh
git -C libs/payment-engine reflog --date=local
~~~

Tìm entry commit vừa tạo, sau đó tạo branch trỏ tới mã SHA tương ứng:

~~~sh
git -C libs/payment-engine branch rescue/recovered-work <commit-sha>
~~~

Reflog lưu dấu vết di chuyển của HEAD và ref trong repository local trong một khoảng thời gian. Nó hữu ích để cứu commit chưa được branch giữ lại, nhưng không thay thế việc push hoặc tạo branch backup.

### 8.4. Repository cha chạy update khi bạn đang phát triển

Trước khi chạy git submodule update, hãy kiểm tra repository con:

~~~sh
git -C libs/payment-engine status -sb
git -C libs/payment-engine branch --show-current
git -C libs/payment-engine log -1 --oneline
~~~

Nếu có thay đổi chưa commit hoặc commit local chưa push, hãy lưu chúng bằng commit và branch, sau đó push hoặc backup phù hợp. Chạy update ở chế độ checkout có thể đưa submodule về commit mà repository cha yêu cầu; điều đó có thể làm bạn rời khỏi commit đang làm việc.

## 9. Xử lý conflict trong submodule

Conflict xảy ra bên trong repository submodule khi merge hoặc rebase các thay đổi của chính repository con. Quy trình xử lý giống Git thông thường:

~~~sh
git -C libs/payment-engine status
~~~

Mở từng file conflict, giữ logic đúng từ các phía, rồi stage và tiếp tục:

~~~sh
git -C libs/payment-engine add src/refund-service.ts
git -C libs/payment-engine merge --continue
~~~

Nếu đang rebase, dùng:

~~~sh
git -C libs/payment-engine rebase --continue
~~~

Sau khi hoàn tất, chạy test trong repository con. Nếu cần hủy quy trình:

~~~sh
git -C libs/payment-engine merge --abort
~~~

hoặc:

~~~sh
git -C libs/payment-engine rebase --abort
~~~

Repository cha cũng có thể gặp xung đột khi hai branch thay đổi gitlink của cùng một submodule tới hai commit khác nhau. Khi đó, cần chọn commit submodule phù hợp trong repository cha; nếu cần kết hợp hai thay đổi, thực hiện merge/rebase trong repository con trước, push commit kết quả, rồi cập nhật gitlink của repository cha tới commit mới.

Không giải quyết xung đột gitlink bằng cách chỉ chọn một SHA mà chưa kiểm tra nội dung tương ứng trong repository con.

## 10. Cách kiểm tra toàn bộ trạng thái giữa hai repository

Khi làm việc trực tiếp trong submodule, hãy kiểm tra cả repository con và repository cha.

Trong repository con:

~~~sh
git -C libs/payment-engine status -sb
git -C libs/payment-engine branch --show-current
git -C libs/payment-engine log -3 --oneline --decorate
git -C libs/payment-engine remote -v
~~~

Trong repository cha:

~~~sh
git status --short
git diff --submodule=log
git submodule status
~~~

Hai góc nhìn này trả lời các câu hỏi khác nhau:

| Kiểm tra | Câu hỏi |
|---|---|
| Status trong submodule | File nào trong repository con đang sửa hoặc staged? |
| Branch trong submodule | HEAD đang ở branch nào hay detached? |
| Log trong submodule | Commit mới nhất của repository con là gì? |
| Status trong superproject | Gitlink của submodule đã thay đổi chưa? |
| Diff submodule của superproject | Repository cha sẽ ghi nhận commit submodule nào? |
| Submodule status | Submodule đã init và có khớp commit cha ghi nhận không? |

Đừng chỉ nhìn git status ở repository cha rồi cho rằng mọi file trong submodule đã được commit. Hãy kiểm tra trực tiếp bên trong repository con.

## 11. Quy trình mẫu: sửa thư viện submodule và cập nhật ứng dụng

Giả sử ứng dụng store-app dùng submodule libs/payment-engine. Bạn cần thêm hỗ trợ hoàn tiền vào thư viện.

**Bước 1 — Khởi tạo và kiểm tra submodule**

~~~sh
git submodule update --init --recursive
git -C libs/payment-engine status -sb
git -C libs/payment-engine log -1 --oneline
~~~

**Bước 2 — Tạo branch trong repository con**

~~~sh
git -C libs/payment-engine switch -c feature/add-refund-support
~~~

**Bước 3 — Sửa mã và commit**

~~~sh
git -C libs/payment-engine add src/refund-service.ts tests/refund-service.test.ts
git -C libs/payment-engine diff --cached
git -C libs/payment-engine commit -m "Add refund support"
~~~

**Bước 4 — Push repository con**

~~~sh
git -C libs/payment-engine push -u origin feature/add-refund-support
~~~

**Bước 5 — Review và tích hợp trong repository con**

Mở PR/MR trong payment-engine. Sau khi được review, merge theo quy trình của repository con. Nếu ứng dụng cần dùng commit cụ thể trước khi branch được merge, nhóm phải thống nhất cách tham chiếu và bảo đảm commit đã được push lên remote có thể truy cập.

**Bước 6 — Cập nhật gitlink trong repository cha**

Checkout commit đã được chọn trong submodule, rồi quay lại store-app:

~~~sh
git -C libs/payment-engine fetch origin
git -C libs/payment-engine switch --detach <approved-commit>
git add libs/payment-engine
git diff --cached --submodule=log
git commit -m "Update payment-engine submodule"
~~~

Ở ví dụ này, checkout detach là có chủ đích vì repository cha chỉ cần ghi nhận commit đã được duyệt. Người phát triển thư viện có thể tiếp tục dùng branch trong repository con; trạng thái checkout ở máy của người làm ứng dụng có thể được điều chỉnh sau khi commit gitlink.

**Bước 7 — Push repository cha**

~~~sh
git push
~~~

Người khác lấy thay đổi:

~~~sh
git pull
git submodule update --init --recursive
~~~

Họ nhận đúng commit payment-engine mà store-app đã ghim.

## 12. Lỗi thường gặp và cách xử lý

**Thấy detached HEAD và nghĩ submodule bị hỏng.** Đây là trạng thái bình thường khi Git checkout commit được repository cha ghim. Chỉ tạo branch nếu cần phát triển trực tiếp.

**Commit trong submodule nhưng quên push.** Repository cha có thể ghi nhận gitlink mới, nhưng người khác không lấy được commit nếu remote submodule chưa có nó. Push repository con trước khi push repository cha.

**Commit trong submodule nhưng quên commit gitlink.** Thay đổi trong repository con không tự cập nhật repository cha. Chạy git add đường dẫn submodule và tạo commit trong superproject.

**Chạy git submodule update và rời khỏi branch đang làm.** Lệnh update mặc định checkout commit đã ghim. Trước khi chạy, lưu commit bằng branch và push/backup nếu cần.

**Tạo commit khi detached rồi chuyển đi.** Tạo branch rescue tại commit đó hoặc tìm lại bằng reflog trước khi garbage collection dọn object không còn được tham chiếu.

**Nhầm branch trong .gitmodules với gitlink.** Trường branch định hướng thao tác update --remote; gitlink trong repository cha vẫn ghi một commit SHA cụ thể.

**Push nhầm remote.** Repository cha và submodule có remote riêng. Kiểm tra git remote -v trong đúng repository trước khi push.

**Cập nhật gitlink tới commit không thể truy cập.** Xác nhận commit submodule đã được push lên remote và người dùng khác có quyền đọc trước khi commit pointer trong repository cha.

## 13. Checklist phát triển trực tiếp trong submodule

**Trước khi sửa**

- [ ] Đã xác nhận đúng đường dẫn submodule và remote của repository con.
- [ ] Đã kiểm tra commit mà repository cha đang ghim.
- [ ] Đã kiểm tra working tree và trạng thái detached HEAD.
- [ ] Đã tạo hoặc chuyển sang branch phù hợp trong submodule.

**Khi phát triển**

- [ ] Chỉ sửa và stage file thuộc repository con.
- [ ] Đã kiểm tra diff và chạy test của submodule.
- [ ] Đã commit trên branch có tên.
- [ ] Đã push commit lên remote submodule.
- [ ] Đã hoàn tất review hoặc có quyết định rõ về commit được sử dụng.

**Khi cập nhật repository cha**

- [ ] Submodule đang checkout đúng commit cần ghim.
- [ ] Đã kiểm tra git diff --submodule=log.
- [ ] Đã stage đúng đường dẫn submodule.
- [ ] Đã commit gitlink trong repository cha.
- [ ] Đã push repository cha sau khi commit submodule có thể truy cập.
- [ ] Đã thử git submodule update trên một bản clone hoặc môi trường khác nếu cần.

## 14. Kết luận

Detached HEAD trong submodule là hệ quả tự nhiên của việc repository cha ghim một commit cụ thể của repository con. Trạng thái này giúp mọi người checkout cùng một phiên bản submodule, nhưng không phải nơi thuận tiện để phát triển commit mới lâu dài.

Khi cần sửa submodule, hãy tạo branch ngay trong repository con, commit và push thay đổi lên remote của nó. Sau đó cập nhật gitlink bằng cách stage đường dẫn submodule và commit trong repository cha. Luôn kiểm tra cả hai repository và giữ commit submodule có thể truy cập trước khi chia sẻ commit cha. Cách làm này giúp tránh mất commit detached, nhầm remote và tình trạng repository cha tham chiếu tới một phiên bản submodule mà đồng đội không thể lấy được.
