# Xử lý nhánh phân kỳ và cập nhật đồng thời từ nhiều người

Trong một repository có nhiều người cùng phát triển, nhánh trên máy chủ có thể thay đổi trong lúc bạn đang làm việc. Đồng đội có thể đã push commit mới, trong khi bạn cũng tạo commit riêng dựa trên phiên bản cũ. Khi đó, nhánh local và nhánh remote không còn nằm trên cùng một đường lịch sử: mỗi phía có commit mà phía kia chưa có. Git gọi tình huống này là **nhánh phân kỳ** (diverged branches).

Phân kỳ là tình huống bình thường trong cộng tác. Điều quan trọng là nhận ra nó, lấy thông tin mới nhất từ remote, xem các commit ở cả hai phía rồi chọn cách tích hợp phù hợp. Nếu nhiều người push gần như cùng lúc lên một nhánh, Git sẽ bảo vệ lịch sử bằng cách từ chối cập nhật không thể fast-forward; người push sau cần đồng bộ và tích hợp commit mới trước khi thử lại.

Sau bài này, bạn có thể:

- Nhận biết trạng thái ahead, behind và diverged của một nhánh.
- Xác định commit chỉ có ở local hoặc chỉ có ở remote.
- Giải thích vì sao một lần push có thể bị từ chối do non-fast-forward.
- Đồng bộ nhánh phân kỳ bằng merge, rebase hoặc fast-forward-only.
- Xử lý tình huống nhiều người cập nhật cùng một nhánh.
- Hoàn tất tích hợp, kiểm tra kết quả và push an toàn.

## 1. Vì sao nhánh bị phân kỳ

Giả sử bạn và một đồng đội cùng bắt đầu từ commit C trên nhánh main. Bạn tạo commit A1, còn đồng đội tạo commit B1 và push lên origin/main. Sau đó, bạn tiếp tục tạo A2 mà chưa fetch thay đổi của đồng đội.

Lịch sử lúc này có dạng:

~~~text
             A1---A2  main (local)
            /
           C
            \
             B1      origin/main
~~~

Hai nhánh cùng có tổ tiên C nhưng đã phát triển theo hai hướng. Local có A1 và A2; remote có B1. Không thể chỉ di chuyển con trỏ main tới B1 mà vẫn giữ A1 và A2, vì việc đó sẽ bỏ các commit local khỏi lịch sử của nhánh.

Có ba trạng thái thường gặp khi so sánh nhánh local với upstream:

| Trạng thái | Ý nghĩa | Hướng xử lý thường gặp |
| --- | --- | --- |
| Up-to-date | Local và upstream cùng trỏ tới một commit. | Tiếp tục làm việc. |
| Ahead | Local có commit mới mà upstream chưa có. | Kiểm tra rồi push. |
| Behind | Upstream có commit mới mà local chưa có. | Fetch, sau đó cập nhật local theo quy ước nhóm. |
| Diverged | Cả local và upstream đều có commit riêng. | Fetch, kiểm tra hai phía, rồi merge hoặc rebase. |

Ahead và behind là quan hệ tương đối giữa hai tham chiếu. Một nhánh có thể vừa ahead vừa behind: ví dụ local ahead 2, behind 3 nghĩa là local có hai commit riêng, trong khi upstream có ba commit riêng.

## 2. Kiểm tra upstream và trạng thái nhánh

Trước khi đồng bộ, hãy xác nhận bạn đang đứng trên nhánh nào và nhánh đó theo dõi upstream nào:

~~~bash
git status --short --branch
git branch -vv
git branch -r
~~~

- git status --short --branch cho biết nhánh hiện tại và có thể hiển thị số commit ahead/behind nếu upstream đã được cấu hình và thông tin remote đã được cập nhật.
- git branch -vv hiển thị nhánh local cùng upstream mà nó theo dõi.
- git branch -r liệt kê các remote-tracking branches đang có trong repository local.

Nếu nhánh chưa có upstream, bạn có thể thiết lập khi push lần đầu:

~~~bash
git push -u origin feature/report-export
~~~

Tùy chọn -u thiết lập upstream cho nhánh local sau khi push thành công. Nếu nhánh đã tồn tại trên remote và bạn cần cấu hình lại upstream, dùng:

~~~bash
git branch --set-upstream-to=origin/feature/report-export feature/report-export
~~~

Hãy chắc chắn tên nhánh local và remote là đúng trước khi thay đổi cấu hình theo dõi. Upstream giúp các lệnh status, pull và push mặc định biết nhánh nào có liên quan.

## 3. Fetch trước khi quyết định tích hợp

Thông tin ahead/behind chỉ đáng tin khi remote-tracking refs đã được cập nhật gần đây. Hãy fetch trước:

~~~bash
git fetch origin
git status --short --branch
~~~

Fetch lấy dữ liệu mới và cập nhật các tham chiếu theo dõi từ xa như origin/main. Nó không tự sửa nhánh local hoặc working tree. Nhờ vậy, bạn có thể xem hai phía trước khi chọn cách tích hợp.

Giả sử nhánh hiện tại có upstream được cấu hình. Lệnh sau đếm commit chỉ có ở mỗi phía:

~~~bash
git rev-list --left-right --count HEAD...@{upstream}
~~~

Kết quả gồm hai số, cách nhau bằng tab:

~~~text
2    3
~~~

Với thứ tự HEAD...@{upstream}, số thứ nhất là commit chỉ có ở HEAD (local); số thứ hai là commit chỉ có ở upstream. Ví dụ 2 và 3 nghĩa là local có hai commit riêng, upstream có ba commit riêng.

Để xem cụ thể các commit:

~~~bash
# Xem commit riêng của mỗi phía trong một đồ thị
git log --oneline --left-right --graph HEAD...@{upstream}

# Chỉ xem commit local có mà upstream chưa có
git log --oneline @{upstream}..HEAD

# Chỉ xem commit upstream có mà local chưa có
git log --oneline HEAD..@{upstream}
~~~

Trong kết quả --left-right, dấu < đánh dấu commit chỉ có ở phía trái (HEAD), dấu > đánh dấu commit chỉ có ở phía phải (upstream). Cách xem này giúp xác nhận các commit của đồng đội và commit local trước khi thay đổi lịch sử.

Nếu muốn biết hai nhánh bắt đầu tách từ commit nào, dùng:

~~~bash
git merge-base HEAD @{upstream}
~~~

Lệnh trả về mã commit tổ tiên chung gần nhất (merge base) trong lịch sử thông thường. Đây là điểm Git dùng làm cơ sở để tính toán một phép hợp nhất ba phía.

## 4. Chọn cách cập nhật nhánh local

Khi đã hiểu hai phía có những commit nào, hãy chọn cách tích hợp theo chính sách của nhóm và trạng thái lịch sử.

### Fast-forward khi local chưa có commit riêng

Nếu upstream chỉ tiến lên phía trước và HEAD là tổ tiên của upstream, Git có thể cập nhật nhánh local bằng cách di chuyển con trỏ tới commit mới:

~~~text
C---D---E  origin/main
     ^
     main (local trước cập nhật)
~~~

Chạy:

~~~bash
git merge --ff-only @{upstream}
~~~

Tùy chọn --ff-only chỉ cho phép fast-forward. Nếu hai nhánh đã phân kỳ, lệnh dừng thay vì tự tạo merge commit. Đây là lựa chọn hữu ích khi bạn muốn cập nhật nhánh ổn định và yêu cầu lịch sử phải tiến thẳng.

### Merge khi muốn giữ nguyên lịch sử hai phía

Merge kết hợp hai dòng lịch sử và giữ nguyên các commit hiện có:

~~~bash
git merge @{upstream}
~~~

Nếu hai nhánh đã phân kỳ, Git thường tạo một merge commit có hai cha sau khi hợp nhất thành công. Đồ thị lịch sử cho thấy rõ các commit local và commit upstream đã được kết hợp.

~~~text
          A1---A2
         /       \
C-------+---------M  main
         \       /
          B1---B2    upstream
~~~

Merge phù hợp khi nhóm muốn giữ nguyên lịch sử đã chia sẻ, khi nhiều người cùng làm trên một nhánh, hoặc khi việc thể hiện điểm hợp nhất có ý nghĩa với quy trình review. Nếu có xung đột, Git yêu cầu giải quyết trước khi tạo merge commit.

### Rebase khi muốn đặt commit riêng lên nền mới

Rebase lấy các commit riêng của nhánh local và phát lại chúng trên đầu upstream:

~~~bash
git rebase @{upstream}
~~~

Trước rebase:

~~~text
             A1---A2  main
            /
C----------+
            \
             B1---B2  upstream
~~~

Sau rebase thành công:

~~~text
C---B1---B2---A1'---A2'  main
~~~

Các commit A1' và A2' có mã định danh mới vì cha và nội dung commit được tạo lại. Rebase thường tạo lịch sử tuyến tính, dễ đọc, nhưng chỉ nên dùng cho commit riêng chưa được người khác dựa vào, trừ khi nhóm đã thống nhất việc viết lại lịch sử.

Không rebase tùy tiện một nhánh dùng chung hoặc commit đã công bố mà đồng đội đang phát triển tiếp. Việc thay mã commit có thể khiến những người khác phải xử lý lại lịch sử của họ.

### Bảng chọn nhanh

| Cách | Kết quả lịch sử | Khi phù hợp |
| --- | --- | --- |
| merge | Giữ hai dòng commit và thêm điểm hợp nhất khi cần. | Nhánh dùng chung, cần lưu dấu lần tích hợp hoặc muốn giữ nguyên commit đã chia sẻ. |
| rebase | Phát lại commit local trên đầu upstream; mã commit local thay đổi. | Commit local riêng, chưa chia sẻ và nhóm muốn lịch sử tuyến tính. |
| merge --ff-only | Chỉ di chuyển nhánh nếu upstream là hậu duệ của local. | Muốn cập nhật an toàn mà không tạo merge commit hoặc viết lại lịch sử. |

Không có lựa chọn duy nhất cho mọi repository. Hãy tuân theo quy ước của nhóm, đặc biệt với main, release và các nhánh đã được nhiều người sử dụng.

## 5. Pull và cấu hình cách tích hợp

Lệnh pull thực hiện fetch rồi tích hợp dữ liệu lấy được vào nhánh hiện tại. Cách tích hợp phụ thuộc tùy chọn trên lệnh và cấu hình:

~~~bash
# Chỉ chấp nhận fast-forward
git pull --ff-only

# Fetch rồi rebase commit local lên upstream
git pull --rebase

# Fetch rồi merge upstream vào nhánh hiện tại
git pull --no-rebase
~~~

Nếu muốn repository luôn dùng một chính sách rõ ràng, có thể cấu hình riêng cho repository hiện tại:

~~~bash
# Từ chối pull nếu nhánh phân kỳ
git config pull.ff only

# Hoặc ưu tiên rebase khi pull
git config pull.rebase true

# Hoặc ưu tiên merge khi pull
git config pull.rebase false
~~~

Chỉ chọn một chính sách phù hợp với quy trình nhóm. Nếu chưa biết cấu hình đang áp dụng, kiểm tra bằng:

~~~bash
git config --show-origin --get pull.rebase
git config --show-origin --get pull.ff
~~~

Fetch riêng rồi kiểm tra log thường dễ đánh giá hơn khi nhánh đã phân kỳ hoặc repository có nhiều người cùng cập nhật. Pull tiện cho thao tác thường ngày khi bạn đã hiểu và thống nhất chính sách tích hợp.

## 6. Vì sao push đồng thời có thể bị từ chối

Git không cho phép một lần push thông thường làm mất commit đang được tham chiếu trên remote. Khi máy chủ nhận push, nó kiểm tra xem cập nhật ref có thể tiến theo kiểu fast-forward hay không.

Ví dụ:

1. Bạn và đồng đội đều có bản local bắt đầu từ commit C.
2. Đồng đội tạo A1 và push; origin/main chuyển từ C sang A1.
3. Bạn tạo B1 dựa trên C rồi push.
4. Máy chủ từ chối vì cập nhật C thành B1 sẽ làm nhánh remote bỏ mất A1.

Thông báo thường gặp:

~~~text
! [rejected] main -> main (non-fast-forward)
error: failed to push some refs
~~~

Đây là cơ chế bảo vệ lịch sử. Push bị từ chối không có nghĩa commit local đã mất; commit của bạn vẫn nằm trong repository local. Bạn cần fetch thay đổi mới, tích hợp chúng vào nhánh local rồi push lại.

Quy trình xử lý:

~~~bash
# 1. Lấy trạng thái mới nhất
git fetch origin

# 2. Xem commit hai phía
git log --oneline --left-right --graph HEAD...@{upstream}

# 3. Chọn merge hoặc rebase theo quy ước
git rebase @{upstream}

# 4. Chạy kiểm tra phù hợp, sau đó push lại
git push
~~~

Trong ví dụ này dùng rebase như một lựa chọn cho commit riêng chưa chia sẻ. Nếu nhánh là nhánh dùng chung hoặc nhóm yêu cầu giữ merge commit, hãy dùng merge thay cho rebase.

## 7. Nhiều người push gần như cùng lúc

Hãy hình dung A và B cùng fetch origin/main khi remote đang ở C. A tạo A1 và push thành công trước. B tạo B1 từ C và push sau đó. Vì origin/main đã tiến tới A1, push của B không còn fast-forward và bị từ chối.

~~~text
Ban đầu:
C  origin/main, A/main, B/main

Sau khi A push:
C---A1  origin/main
 \
  B1    B/main
~~~

B cần fetch và tích hợp A1:

~~~bash
git fetch origin
git log --oneline --left-right --graph HEAD...origin/main
git rebase origin/main
~~~

Sau khi rebase:

~~~text
C---A1---B1'  B/main
      ^
      origin/main
~~~

B chạy test và push lại. Nếu trong lúc B đang xử lý, một người thứ ba lại push A2, push của B có thể tiếp tục bị từ chối vì remote đã thay đổi thêm. Khi đó, B fetch lần nữa, kiểm tra commit mới, tích hợp A2 rồi mới push. Lặp lại quy trình này là bình thường khi nhánh có nhiều hoạt động.

Máy chủ cập nhật tham chiếu theo cách có kiểm soát để hai lần push đồng thời không âm thầm ghi đè nhau. Một lần push chỉ thành công nếu điều kiện cập nhật ref vẫn hợp lệ tại thời điểm máy chủ áp dụng nó. Vì vậy, đừng xem kết quả fetch trước đó là bảo đảm rằng remote sẽ đứng yên cho tới khi bạn push.

## 8. Xử lý xung đột khi tích hợp

Nếu hai phía sửa cùng vùng nội dung theo cách Git không thể tự kết hợp, merge hoặc rebase có thể dừng với conflict. Hãy xác định tệp xung đột:

~~~bash
git status
git diff
~~~

Mở từng tệp, đọc các vùng xung đột và quyết định nội dung cuối cùng dựa trên yêu cầu của cả hai thay đổi. Sau khi sửa:

~~~bash
# Đánh dấu tệp đã giải quyết trong quá trình merge hoặc rebase
git add path/to/file
~~~

Nếu đang merge, hoàn tất bằng commit khi Git yêu cầu:

~~~bash
git merge --continue
~~~

Nếu đang rebase:

~~~bash
git rebase --continue
~~~

Chạy lại các lệnh kiểm tra phù hợp sau khi giải quyết. Nếu cần quay lại trạng thái trước khi bắt đầu quá trình tích hợp:

~~~bash
git merge --abort
git rebase --abort
~~~

Chỉ chạy lệnh abort tương ứng với thao tác đang diễn ra. Abort hủy quá trình merge hoặc rebase đang dở; nó không thay thế việc lưu giữ các chỉnh sửa độc lập khác. Trước khi bắt đầu tích hợp, hãy kiểm tra working tree và commit hoặc stash phần việc đang dang dở.

## 9. Bảo vệ nhánh dùng chung và xử lý force push

Với nhánh dùng chung như main, release hoặc nhánh tích hợp của nhóm, hãy ưu tiên push fast-forward và dùng merge request/pull request cùng quy tắc bảo vệ nhánh khi có thể. Không dùng git push --force để vượt qua lỗi non-fast-forward trên nhánh dùng chung: lệnh đó có thể làm mất commit mà người khác đã push.

Trong một số trường hợp, bạn sở hữu nhánh tính năng riêng và cần cập nhật lại lịch sử đã push trước đó, chẳng hạn sau một lần rebase có chủ đích. Khi nhóm cho phép, dùng:

~~~bash
git push --force-with-lease origin feature/report-export
~~~

--force-with-lease kiểm tra kỳ vọng về vị trí ref remote trước khi ghi đè. Nếu remote đã thay đổi ngoài kỳ vọng, Git từ chối để bảo vệ commit mới. Dù có cơ chế này, hãy thông báo và phối hợp với người đang dùng nhánh trước khi viết lại lịch sử. Tùy chọn này không biến force push thành thao tác phù hợp cho nhánh dùng chung.

Nếu nhóm không cho phép viết lại lịch sử đã công bố, hãy tạo commit sửa tiếp theo hoặc merge thay vì force push.

## 10. Một quy trình đồng bộ có thể lặp lại

Khi phát hiện nhánh local và upstream có thể đã thay đổi đồng thời, có thể áp dụng quy trình sau:

~~~bash
# 1. Kiểm tra nhánh và các chỉnh sửa chưa commit
git status --short --branch
git branch -vv

# 2. Lưu công việc đang dang dở bằng commit hoặc stash nếu cần
# Không bắt đầu tích hợp khi chưa biết các thay đổi local đang ở đâu.

# 3. Lấy trạng thái mới nhất từ remote
git fetch origin

# 4. Đếm và xem commit riêng của hai phía
git rev-list --left-right --count HEAD...@{upstream}
git log --oneline --left-right --graph HEAD...@{upstream}

# 5. Tích hợp theo quy ước của nhóm
git rebase @{upstream}

# 6. Kiểm tra lịch sử và chạy test
git status --short --branch
git log --oneline --decorate --graph -n 15

# 7. Chia sẻ kết quả
git push
~~~

Ví dụ dùng rebase ở bước 5 dành cho commit local riêng chưa chia sẻ. Với nhánh dùng chung, thay bằng merge theo chính sách nhóm. Nếu nhánh không phân kỳ và chỉ cần tiến tới upstream, có thể dùng merge --ff-only. Nếu push lại bị từ chối vì remote tiếp tục thay đổi, quay lại bước fetch và kiểm tra; đừng lặp lại push với giả định remote vẫn giữ nguyên.

## 11. Thói quen cộng tác giúp giảm phân kỳ

- Fetch thường xuyên trước khi bắt đầu một phần việc dài và trước khi tích hợp thay đổi.
- Giữ nhánh tính năng ngắn hạn, chia công việc thành commit nhỏ có mục đích rõ ràng.
- Tránh nhiều người cùng sửa trực tiếp một nhánh dùng chung nếu quy trình có thể dùng nhánh riêng và pull request.
- Thống nhất trong nhóm việc dùng merge, rebase hay fast-forward-only.
- Kiểm tra upstream và staged/unstaged changes trước khi pull, merge hoặc rebase.
- Push sau khi tích hợp và chạy kiểm tra; nếu bị từ chối, fetch và đánh giá lại.
- Không force push nhánh dùng chung hoặc commit mà người khác đang dựa vào.
- Trao đổi trước khi viết lại lịch sử của một nhánh đã chia sẻ.

Nhánh phân kỳ phản ánh việc nhiều người đang tiến hành công việc độc lập trên cùng lịch sử. Fetch giúp nhìn thấy thay đổi mới; log và diff giúp hiểu khác biệt; merge hoặc rebase kết hợp các dòng công việc theo chính sách nhóm. Khi mọi người cùng tuân thủ một quy trình rõ ràng, các lần cập nhật đồng thời có thể được xử lý lặp lại mà không làm mất commit của nhau.
