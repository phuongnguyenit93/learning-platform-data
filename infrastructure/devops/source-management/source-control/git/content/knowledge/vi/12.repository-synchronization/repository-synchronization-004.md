# Chọn hành vi pull: fast-forward only, merge hoặc rebase

Khi làm việc với remote, lệnh `git pull` lấy thông tin mới từ remote rồi tích hợp nhánh upstream vào nhánh hiện tại. Nếu nhánh local và remote đã phát triển theo những hướng khác nhau, Git cần biết nên xử lý lịch sử đó bằng cách nào. Ba lựa chọn thường gặp là chỉ cho phép fast-forward, tích hợp bằng merge hoặc phát lại commit local bằng rebase.

Trong chương **Đồng bộ kho mã** của module **SOURCE_CONTROL_GIT**, bài học này giúp bạn chọn hành vi pull phù hợp với cách nhóm quản lý lịch sử. Bạn sẽ hiểu điều gì xảy ra khi hai nhánh đi cùng đường, khi local chỉ chậm hơn remote và khi cả hai phía đều có commit riêng; đồng thời biết cách cấu hình mặc định và xử lý khi pull không thể hoàn tất.

Sau bài học, bạn có thể:

- Giải thích pull thực hiện fetch và tích hợp upstream như thế nào.
- Phân biệt fast-forward only, merge và rebase qua đồ thị commit.
- Chọn hành vi pull dựa trên trạng thái nhánh và quy ước cộng tác.
- Cấu hình hành vi ở phạm vi repository hoặc người dùng.
- Kiểm tra tình trạng phân kỳ trước khi tích hợp và tiếp tục sau khi gặp xung đột.

## 1. Pull thực hiện những việc gì?

`git pull` là thao tác kết hợp hai bước:

1. **Fetch**: tải các commit và cập nhật remote-tracking branch, ví dụ `origin/main`.
2. **Integrate**: tích hợp nhánh upstream được theo dõi vào nhánh local hiện tại bằng fast-forward, merge hoặc rebase tùy lựa chọn và cấu hình.

Remote-tracking branch như `origin/main` là tham chiếu local ghi nhận trạng thái nhánh trên remote ở lần fetch gần nhất. Nó không tự thay đổi chỉ vì người khác vừa push; cần fetch để cập nhật thông tin đó.

Nếu nhánh hiện tại đang theo dõi `origin/main`, lệnh:

~~~bash
git pull
~~~

thường tương đương với việc fetch từ remote đã cấu hình rồi tích hợp upstream của nhánh hiện tại. Nếu chưa thiết lập upstream, bạn có thể chỉ rõ remote và nhánh:

~~~bash
git pull origin main
~~~

Phần fetch có thể hoàn tất ngay cả khi bước tích hợp thất bại. Khi đó remote-tracking branch đã được cập nhật, còn nhánh hiện tại có thể vẫn cần bạn giải quyết tình trạng phân kỳ hoặc xung đột.

## 2. Nhận diện ba trạng thái của nhánh local và upstream

Để chọn cách pull, trước tiên cần biết hai nhánh đang ở quan hệ nào. Giả sử:

- `L` là commit hiện tại của nhánh local.
- `R` là commit mới nhất của upstream sau khi fetch.
- Các ký hiệu L và R lần lượt đánh dấu con trỏ local và upstream.

### Local có thể tiến thẳng đến upstream

~~~text
A---B---C
    ^   ^
    L   R
~~~

Trong sơ đồ, `L` là local ở commit `B`, còn `R` là upstream ở commit `C`. Lịch sử local là tổ tiên của upstream. Git chỉ cần đưa con trỏ nhánh local tiến từ `B` đến `C`. Đây là fast-forward.

### Local đã có commit riêng nhưng upstream chưa tiến thêm

~~~text
A---B---C  (local)
    ^
    upstream
~~~

Local đang đi trước upstream. Không có commit mới từ upstream để tích hợp, vì vậy pull thường báo đã cập nhật. Việc local ahead không tự nó đòi hỏi merge hoặc rebase.

### Local và upstream đã phân kỳ

~~~text
      L1---L2  (local)
     /
A---B
     \
      R1---R2  (upstream)
~~~

Hai nhánh có tổ tiên chung là `B`, nhưng local có `L1`, `L2` và upstream có `R1`, `R2`. Không thể chỉ di chuyển con trỏ local đến upstream mà vẫn giữ nguyên các commit local. Lúc này cần quyết định tạo merge commit hay rebase các commit local lên trên upstream. Nếu chọn fast-forward only, Git sẽ từ chối tích hợp.

Có thể xem trạng thái tóm tắt bằng:

~~~bash
git status -sb
git branch -vv
~~~

Để cập nhật thông tin remote trước khi phân tích:

~~~bash
git fetch
~~~

Sau đó xem các commit chỉ có ở mỗi phía:

~~~bash
git log --oneline --graph --decorate --left-right 'HEAD...@{upstream}'
~~~

Các dòng được đánh dấu `<` là commit chỉ có ở phía trái (HEAD/local); các dòng `>` là commit chỉ có ở phía phải (upstream). Nếu chưa biết nhánh hiện tại có upstream nào, kiểm tra:

~~~bash
git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'
~~~

## 3. Fast-forward only: chỉ tích hợp khi có thể tiến thẳng

Fast-forward xảy ra khi commit hiện tại là tổ tiên của commit upstream. Git chỉ cập nhật con trỏ nhánh local đến commit mới; không tạo merge commit và không viết lại commit hiện có.

~~~text
Trước:
A---B---C---D
    ^       ^
    L       R

Sau:
A---B---C---D  (local, upstream)
~~~

Chạy một lần:

~~~bash
git pull --ff-only
~~~

Hoặc cấu hình mặc định cho repository:

~~~bash
git config --local pull.ff only
~~~

Fast-forward only phù hợp khi nhóm muốn mọi lần cập nhật local diễn ra theo một đường lịch sử thẳng và muốn được báo ngay khi local có commit riêng làm hai nhánh phân kỳ. Lựa chọn này đặc biệt dễ dự đoán trong workflow mà developer thường xuyên cập nhật nhánh trước khi tạo commit local hoặc trước khi đưa thay đổi lên remote.

Nếu local và upstream phân kỳ, lệnh `git pull --ff-only` dừng với thông báo không thể fast-forward. Git không tự tạo merge commit hoặc rebase thay bạn. Sau khi kiểm tra hai phía, bạn có thể chọn merge hoặc rebase cho lần đó theo quy ước của nhóm.

Fast-forward only không có nghĩa là mọi pull đều tạo một commit mới. Nếu local đã ở đúng commit upstream hoặc đang đi trước upstream, có thể không cần cập nhật gì.

## 4. Merge: giữ nguyên commit hai phía và nối lịch sử

Merge tích hợp hai nhánh bằng cách tạo một commit có hai parent khi chúng đã phân kỳ. Các commit local và commit upstream giữ nguyên mã định danh, vì lịch sử cũ không bị viết lại.

~~~text
Trước:
      L1---L2  (local)
     /
A---B
     \
      R1---R2  (upstream)

Sau:
      L1---L2
     /       \
A---B         M  (local)
     \       /
      R1---R2  (upstream)
~~~

Chạy một lần:

~~~bash
git pull --no-rebase
~~~

Đây là lựa chọn pull theo merge. Nếu upstream chỉ tiến lên và có thể fast-forward, Git thường chỉ fast-forward; nếu hai phía phân kỳ, Git tạo merge commit để nối hai lịch sử.

Nếu repository đang đặt pull.ff=only, chính sách đó vẫn yêu cầu fast-forward và pull sẽ bị từ chối khi hai nhánh phân kỳ. Muốn dùng merge trong repository này, hãy điều chỉnh chính sách fast-forward theo quy ước của nhóm.

Nếu muốn luôn tạo merge commit kể cả khi fast-forward có thể thực hiện, có thể dùng:

~~~bash
git pull --no-rebase --no-ff
~~~

Để chọn merge làm hành vi mặc định khi cần tích hợp hai lịch sử:

~~~bash
git config --local pull.rebase false
~~~

Merge phù hợp khi nhóm muốn giữ nguyên cấu trúc phân nhánh, cần thể hiện rõ thời điểm tích hợp hoặc đang cộng tác trên các commit đã được chia sẻ. Merge commit cho biết hai dòng lịch sử đã được kết hợp ở đâu. Đổi lại, lịch sử có thể có nhiều nhánh và cần đọc đồ thị commit để theo dõi.

Merge không đồng nghĩa luôn tạo merge commit. Nếu một phía là tổ tiên của phía kia và không yêu cầu `--no-ff`, Git có thể fast-forward.

## 5. Rebase: phát lại commit local trên nền upstream

Rebase lấy các commit local chưa có trong upstream và lần lượt phát lại chúng trên commit mới nhất của upstream. Kết quả thường tạo ra lịch sử tuyến tính, không cần merge commit cho lần tích hợp đó.

~~~text
Trước:
      L1---L2  (local)
     /
A---B
     \
      R1---R2  (upstream)

Sau:
A---B---R1---R2---L1'---L2'  (local)
             (upstream)
~~~

Các commit `L1'` và `L2'` là commit mới được tạo khi phát lại thay đổi. Chúng có nội dung thay đổi tương ứng với commit cũ nhưng có parent mới, nên mã định danh commit thay đổi.

Chạy một lần:

~~~bash
git pull --rebase
~~~

Để chọn rebase làm hành vi mặc định:

~~~bash
git config --local pull.rebase true
~~~

Rebase phù hợp khi các commit local chưa được chia sẻ và nhóm muốn lịch sử dễ đọc theo một đường thẳng. Khi đọc log, người xem có thể lần lượt theo các thay đổi mà ít gặp merge commit chỉ phục vụ đồng bộ.

Vì rebase tạo commit mới, không nên tự ý rebase các commit đã được push và người khác đang dựa vào. Việc thay đổi mã định danh của commit dùng chung có thể khiến các thành viên phải xử lý lịch sử bị viết lại, phải đồng bộ lại nhánh hoặc gặp commit trùng lặp. Hãy thống nhất với nhóm trước khi viết lại lịch sử đã công bố.

Rebase cũng không tự giải quyết được xung đột về ý nghĩa. Nếu một commit được phát lại không áp dụng sạch lên nền mới, Git tạm dừng để bạn xử lý xung đột rồi tiếp tục hoặc hủy rebase.

## 6. So sánh và chọn hành vi pull

| Tiêu chí | Fast-forward only | Merge | Rebase |
| --- | --- | --- | --- |
| Khi local chỉ chậm hơn upstream | Fast-forward | Thường fast-forward | Cập nhật trên nền upstream |
| Khi hai nhánh phân kỳ | Từ chối tích hợp | Tạo merge commit | Phát lại commit local trên upstream |
| Giữ nguyên mã định danh commit local | Có, nếu chỉ fast-forward thành công | Có | Không, commit được phát lại có mã mới |
| Hình dạng lịch sử | Tuyến tính khi thành công | Giữ cấu trúc nhánh và merge | Thường tuyến tính |
| Phù hợp khi | Muốn pull chỉ tiến thẳng và phát hiện phân kỳ sớm | Muốn ghi nhận rõ điểm hợp nhất và giữ lịch sử đã chia sẻ | Muốn lịch sử gọn, local commit chưa công bố |

Một cách chọn thực tế:

- **Chọn fast-forward only** nếu quy trình yêu cầu local không tự có commit riêng khi cập nhật. Khi bị từ chối, kiểm tra phân kỳ và quyết định rõ bước tiếp theo.
- **Chọn merge** nếu nhóm cần giữ cấu trúc nhánh, hoặc commit local đã được chia sẻ và cần bảo toàn lịch sử.
- **Chọn rebase** nếu commit local chỉ thuộc công việc của bạn và nhóm ưu tiên lịch sử tuyến tính.

Không có lựa chọn nào tự động đúng cho mọi repository. Hành vi nên phản ánh cách nhóm chia sẻ commit, cách review và cách phát hành. Nếu chưa rõ quy ước, hãy kiểm tra trạng thái và trao đổi với nhóm trước khi thay đổi lịch sử đã công bố.

## 7. Cấu hình pull theo repository hoặc người dùng

Có thể cấu hình hành vi cho riêng repository bằng `--local`, hoặc làm mặc định cho các repository của người dùng bằng `--global`.

**Yêu cầu chỉ fast-forward**

~~~bash
git config --local pull.ff only
~~~

**Chọn merge khi hai nhánh phân kỳ**

~~~bash
git config --local pull.rebase false
~~~

**Chọn rebase khi hai nhánh phân kỳ**

~~~bash
git config --local pull.rebase true
~~~

Các lệnh trên là những lựa chọn cấu hình khác nhau. Hãy chọn theo chính sách của repository thay vì đặt nhiều giá trị mâu thuẫn rồi dựa vào hành vi ngầm.

Đổi `--local` thành `--global` nếu muốn áp dụng mặc định cho các repository của người dùng. Chọn đúng một lệnh theo chính sách mong muốn:

- Chỉ cho phép fast-forward:

~~~bash
git config --global pull.ff only
~~~

- Dùng merge khi hai nhánh phân kỳ:

~~~bash
git config --global pull.rebase false
~~~

- Dùng rebase khi hai nhánh phân kỳ:

~~~bash
git config --global pull.rebase true
~~~

Có thể kiểm tra giá trị cấu hình hiện hành và file cấu hình đã cung cấp giá trị đó:

~~~bash
git config --show-origin --get-regexp '^(pull\.(ff|rebase)|branch\..*\.rebase)$'
~~~

Git cũng hỗ trợ cấu hình rebase theo từng nhánh qua `branch.<name>.rebase`. Điều này hữu ích khi một repository có các nhánh theo dõi remote nhưng workflow của từng nhánh khác nhau. Khi dùng cấu hình theo nhánh, hãy kiểm tra tên nhánh và upstream để hiểu chính xác quy tắc nào đang áp dụng.

## 8. Chọn hành vi cho một lần pull

Tùy chọn trên dòng lệnh giúp quyết định riêng cho lần chạy hiện tại:

~~~bash
git pull --ff-only
git pull --no-rebase
git pull --rebase
~~~

Nếu muốn merge commit ngay cả khi có thể fast-forward:

~~~bash
git pull --no-rebase --no-ff
~~~

Tùy chọn chỉ định trực tiếp trên lệnh phù hợp khi cần xử lý một tình huống đặc biệt mà không đổi mặc định repository. Khi pull từ remote và nhánh cụ thể, có thể viết:

~~~bash
git pull --rebase origin main
~~~

Để tránh phụ thuộc vào cấu hình không rõ nguồn gốc, hãy kiểm tra cấu hình và dùng tùy chọn tường minh khi cần. Tùy chọn dòng lệnh có hiệu lực cho lần gọi đó; nó không tự thay đổi giá trị đã lưu trong config.

## 9. Quy trình an toàn trước và sau khi pull

### Bước 1: kiểm tra working tree

~~~bash
git status
~~~

Nếu có thay đổi chưa commit, hãy xác định chúng thuộc công việc nào. Commit thay đổi đã hoàn tất hoặc stash phần đang làm dở trước khi pull nếu thao tác tích hợp có thể ảnh hưởng đến file đó. Không nên bắt đầu bằng một lần pull khi chưa biết working tree đang chứa gì.

### Bước 2: fetch để biết upstream mới nhất

~~~bash
git fetch
git status -sb
~~~

Fetch cập nhật remote-tracking branch mà không tích hợp thay đổi vào nhánh hiện tại. Nhờ đó, bạn có thể kiểm tra tình trạng hai phía trước khi quyết định.

### Bước 3: xem commit chỉ có ở mỗi phía

~~~bash
git log --oneline --graph --decorate --left-right 'HEAD...@{upstream}'
~~~

Nếu local không có commit riêng và chỉ chậm hơn upstream, fast-forward là đủ. Nếu hai phía phân kỳ, dùng quy ước nhóm để chọn merge hoặc rebase. Nếu local đã đi trước và upstream không có commit mới, không cần tích hợp gì.

### Bước 4: pull với lựa chọn rõ ràng

~~~bash
git pull --ff-only
~~~

Hoặc thay bằng `--no-rebase` hay `--rebase` tùy quyết định. Không chạy liên tiếp cả ba lệnh như một chuỗi thử nghiệm; mỗi lệnh đại diện cho một cách tích hợp khác nhau.

### Bước 5: kiểm tra kết quả

~~~bash
git status
git log --oneline --graph --decorate -12
~~~

Xác nhận working tree sạch hoặc chỉ còn các thay đổi dự kiến, và đồ thị commit thể hiện đúng cách tích hợp đã chọn. Chạy kiểm thử liên quan trước khi tiếp tục công việc hoặc push.

## 10. Xử lý khi pull gặp xung đột

Merge và rebase có thể dừng giữa chừng nếu Git không thể kết hợp tự động.

**Nếu pull đang thực hiện merge**, xem trạng thái, sửa các file xung đột, rồi stage và tiếp tục:

~~~bash
git status
git add -- path/to/file
git merge --continue
~~~

Nếu quyết định hủy lần merge đang dở:

~~~bash
git merge --abort
~~~

**Nếu pull đang thực hiện rebase**, sau khi sửa file và stage:

~~~bash
git status
git add -- path/to/file
git rebase --continue
~~~

Nếu muốn hủy rebase và quay lại trạng thái trước khi rebase bắt đầu:

~~~bash
git rebase --abort
~~~

Đọc `git status` để biết Git đang ở giữa merge hay rebase; chỉ dùng lệnh tiếp tục hoặc hủy tương ứng. Sau khi xử lý xong, kiểm tra lại log và chạy kiểm thử. Fast-forward only không bắt đầu merge hoặc rebase khi bị từ chối do phân kỳ, vì vậy thường không có tiến trình tích hợp dở để tiếp tục hoặc abort.

## 11. Những nhầm lẫn thường gặp

### Fast-forward và merge có phải hai lựa chọn hoàn toàn loại trừ nhau?

Không. Fast-forward là cách cập nhật con trỏ khi lịch sử cho phép. Chế độ pull dùng merge vẫn có thể fast-forward nếu không có phân kỳ. Khi hai nhánh phân kỳ, merge mới cần tạo commit nối hai phía.

### Rebase có làm mất thay đổi local không?

Rebase phát lại các commit local trên nền mới và tạo commit mới. Nếu có xung đột, Git tạm dừng để người phát triển quyết định. Tuy nhiên, vì lịch sử bị viết lại, cần kiểm tra trạng thái trước khi bắt đầu và tránh rebase commit đã chia sẻ nếu chưa thống nhất.

### Fast-forward only bị từ chối có nghĩa là fetch thất bại?

Không. Fetch có thể đã thành công và cập nhật remote-tracking branch. Bước tích hợp bị từ chối vì local và upstream phân kỳ. Hãy xem log hai phía rồi chọn merge hoặc rebase theo quy ước.

### Đặt pull.rebase=true có luôn tạo commit mới?

Không. Nếu không có commit local cần phát lại hoặc local chỉ chậm hơn upstream, Git có thể cập nhật mà không cần tạo lại commit local. Rebase chỉ tạo commit mới cho các commit local được phát lại.

### Đổi cấu hình global có phù hợp với mọi dự án?

Không nhất thiết. Các nhóm có thể dùng quy ước khác nhau. Cấu hình local cho phép một repository tuân theo chính sách riêng; tùy chọn dòng lệnh cho phép chọn cách tích hợp cho một lần cụ thể.

## 12. Tự kiểm tra lựa chọn pull

Giả sử sau khi fetch, đồ thị commit là:

~~~text
      C---D  (feature hiện tại)
     /
A---B
     \
      E---F  (origin/feature)
~~~

Trả lời các câu hỏi:

1. Vì sao `git pull --ff-only` không thể tích hợp trạng thái này?
2. Nếu C và D chỉ là commit local chưa chia sẻ, nhóm muốn lịch sử tuyến tính, nên chọn lệnh nào?
3. Nếu C và D đã được chia sẻ và nhóm muốn giữ nguyên mã định danh commit, nên chọn cách nào?
4. Sau khi pull bị từ chối bởi fast-forward only, bước nào giúp xem commit riêng của từng phía?

**Gợi ý:** Hai nhánh đã phân kỳ từ B nên không thể fast-forward. Nếu commit local chưa chia sẻ và nhóm chọn lịch sử tuyến tính, dùng `git pull --rebase`. Nếu commit đã chia sẻ và cần giữ nguyên lịch sử, dùng `git pull --no-rebase` để merge. Sau khi fetch, dùng `git log --oneline --graph --decorate --left-right 'HEAD...@{upstream}'` để xem commit chỉ có ở mỗi phía.

## Kết luận

Hãy chọn hành vi pull dựa trên quan hệ giữa local và upstream cùng quy ước cộng tác của nhóm. Fast-forward only giúp phát hiện phân kỳ và chỉ cho phép tiến thẳng; merge giữ nguyên hai dòng lịch sử và nối chúng bằng merge commit khi cần; rebase phát lại commit local trên upstream để tạo lịch sử tuyến tính nhưng thay đổi mã định danh commit. Kiểm tra working tree, fetch và đọc đồ thị commit trước khi tích hợp sẽ giúp bạn chọn đúng cách và xử lý xung đột có kiểm soát.
