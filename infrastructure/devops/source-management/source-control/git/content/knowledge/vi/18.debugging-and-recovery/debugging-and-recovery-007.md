# Tự động hóa bisect bằng lệnh kiểm thử và xử lý commit không kiểm tra được

Khi một lỗi xuất hiện trong dự án đã có nhiều commit, việc đọc lần lượt toàn bộ lịch sử có thể mất nhiều thời gian. Git có lệnh **git bisect** để tìm commit đầu tiên làm thay đổi trạng thái từ tốt sang xấu bằng phương pháp chia đôi. Nếu có một lệnh kiểm thử đáng tin cậy, bạn có thể dùng **git bisect run** để tự động kiểm tra từng commit mà không cần đánh dấu good hoặc bad bằng tay.

Trong thực tế, không phải commit lịch sử nào cũng build hoặc chạy được trong môi trường hiện tại. Một commit có thể thiếu dependency, chưa có test phù hợp, phụ thuộc phiên bản runtime cũ hoặc không thể khởi động dịch vụ. Cần phân biệt trường hợp commit thực sự gây lỗi với trường hợp không thể kiểm tra. Git hỗ trợ đánh dấu commit không kiểm tra được bằng mã thoát 125 hoặc lệnh git bisect skip.

## 1. git bisect giải quyết vấn đề gì?

Giả sử một tính năng hoạt động bình thường ở commit A, nhưng lỗi đã xuất hiện ở commit Z. Giữa A và Z có hàng trăm commit. Nếu kiểm tra tuần tự từng commit, bạn có thể phải thử rất nhiều lần.

git bisect dùng cách chia đôi khoảng commit:

1. Chọn một commit đã biết là tốt (good).
2. Chọn một commit đã biết là lỗi (bad).
3. Git chọn một commit ở giữa khoảng để kiểm tra.
4. Nếu commit giữa tốt, phạm vi tìm kiếm chuyển về nửa sau.
5. Nếu commit giữa lỗi, phạm vi tìm kiếm chuyển về nửa trước.
6. Lặp lại cho đến khi tìm được commit đầu tiên làm trạng thái chuyển từ tốt sang lỗi.

~~~text
A---B---C---D---E---F---G---H
good                       bad

Lần 1:             D
Lần 2:        B hoặc F (tùy kết quả lần 1)
Lần tiếp:      tiếp tục chia đôi khoảng còn lại
~~~

Với lịch sử tuyến tính và kết quả kiểm tra nhất quán, số lần kiểm tra thường gần log2(N), trong đó N là số commit trong khoảng cần tìm. Ví dụ, khoảng 1.024 commit thường chỉ cần khoảng 10 lần kiểm tra để thu hẹp phạm vi.

git bisect không tự hiểu lỗi của ứng dụng. Người dùng phải cung cấp hai mốc có trạng thái đã biết và một tiêu chí xác định commit hiện tại là good hay bad.

## 2. Điều kiện để bisect cho kết quả có ý nghĩa

Trước khi chạy tự động, cần kiểm tra một số giả định:

- **Mốc good đáng tin:** Bạn đã xác nhận lỗi chưa xuất hiện tại commit đó.
- **Mốc bad đáng tin:** Bạn đã xác nhận lỗi xuất hiện tại commit đó.
- **Tiêu chí kiểm thử rõ ràng:** Có thể xác định kết quả là lỗi hoặc không lỗi bằng một phép kiểm tra cụ thể.
- **Lỗi có tính tái hiện:** Cùng một commit và cùng điều kiện phải cho kết quả ổn định.
- **Lịch sử có quan hệ phù hợp:** Khoảng commit giữa hai mốc phải chứa đường phát triển dẫn tới lỗi cần điều tra.

Phương pháp chia đôi giả định trạng thái có thể phân loại theo một ranh giới good rồi bad trên lịch sử đang xét. Nếu lỗi xuất hiện, biến mất rồi xuất hiện lại, hoặc phụ thuộc vào dữ liệu ngoài repository, kết quả có thể không phản ánh một ranh giới duy nhất.

Nếu có nhiều lần hồi quy độc lập, nhiều nhánh merge phức tạp hoặc test không ổn định, cần thu hẹp phạm vi, chọn đúng đường lịch sử hoặc điều tra từng lần thay đổi riêng.

## 3. Chuẩn bị trước khi chạy bisect

### 3.1. Kiểm tra repository

Đảm bảo đang ở đúng repository và hiểu trạng thái hiện tại:

~~~
git rev-parse --show-toplevel
git status -sb
git log --oneline --decorate -15
~~~

Nên bắt đầu với working tree sạch. git bisect sẽ checkout các commit lịch sử, thường đưa HEAD vào trạng thái detached HEAD trong lúc điều tra. Thay đổi chưa commit có thể cản trở việc chuyển commit hoặc khiến bạn nhầm lẫn kết quả.

Nếu còn thay đổi đang làm, hãy commit hoặc cất chúng bằng stash sau khi đã xem nội dung:

~~~
git stash push -m "WIP before bisect"
git stash list
~~~

Không dùng git reset --hard hoặc git clean chỉ để làm sạch repository khi chưa xác định các thay đổi đó có cần giữ hay không.

### 3.2. Xác định commit good và bad

Ví dụ, phiên bản hiện tại ở main bị lỗi, còn một phiên bản cũ đã được xác nhận hoạt động:

~~~
git log --oneline --decorate --all
git show --no-patch --oneline <known-good-commit>
git show --no-patch --oneline <known-bad-commit>
~~~

Ghi lại hai mã commit cụ thể thay vì chỉ dựa vào tên branch có thể tiếp tục di chuyển. Khi đã chọn mốc:

- Commit good phải thực sự không có lỗi đang điều tra.
- Commit bad phải thực sự có lỗi đó.
- Hai mốc cần nằm trong cùng dòng lịch sử có thể dùng để tìm thay đổi gây lỗi.

Nếu chưa biết commit good hoặc bad, cần tìm mốc có thể tái hiện trước khi chạy bisect. Chọn sai một trong hai mốc sẽ làm kết quả tìm kiếm sai ngay từ đầu.

### 3.3. Thiết kế lệnh kiểm thử

Lệnh kiểm thử nên:

- Tập trung vào đúng lỗi cần tìm, tránh chạy toàn bộ test suite nếu không cần thiết.
- Có kết quả rõ ràng và ổn định.
- Chạy được trên nhiều commit lịch sử nhất có thể.
- Không cần thao tác thủ công hoặc tương tác với người dùng.
- Không phụ thuộc dịch vụ bên ngoài không ổn định nếu có thể thay bằng fixture hoặc môi trường kiểm thử cô lập.
- Trả về mã thoát theo hợp đồng mà git bisect run hiểu được.

Ví dụ, thay vì kiểm tra chung chung “ứng dụng chạy được”, hãy có một test tái hiện lỗi cụ thể như “tìm kiếm không phân biệt chữ hoa chữ thường” hoặc “tổng tiền đơn hàng phải bao gồm phí vận chuyển”.

## 4. Hợp đồng mã thoát của git bisect run

git bisect run gọi lệnh bạn cung cấp tại mỗi commit mà Git chọn. Mã thoát của lệnh quyết định cách Git phân loại commit đó.

| Mã thoát | Ý nghĩa với git bisect run | Cách dùng |
|---|---|---|
| 0 | Good | Kiểm thử thành công, lỗi chưa xuất hiện |
| 1 đến 127, ngoại trừ 125 | Bad | Kiểm thử xác nhận lỗi đã xuất hiện |
| 125 | Skip | Không thể kiểm tra commit này một cách đáng tin cậy |
| Lớn hơn 127 | Abort | Dừng quá trình bisect do lỗi thực thi hoặc tín hiệu bất thường |

Mã 125 là giá trị đặc biệt. Nó không có nghĩa commit tốt hay xấu; nó có nghĩa không thể kết luận ở commit hiện tại và Git cần bỏ qua commit đó để tiếp tục tìm kiếm.

Các mã khác 0 và nằm trong khoảng 1 đến 127, trừ 125, đều được xem là bad. Vì vậy, nếu lệnh kiểm thử trả về 2 do thiếu cấu hình hoặc trả về 127 vì không tìm thấy chương trình, Git có thể phân loại commit là bad dù lỗi thực tế chỉ là môi trường kiểm thử. Đây là lý do cần thiết kế wrapper kiểm thử để chuẩn hóa kết quả.

Mã thoát lớn hơn 127 khiến bisect run dừng. Ví dụ, tiến trình bị kết thúc bởi tín hiệu có thể tạo mã thoát trong nhóm này. Khi lệnh dừng bất thường, hãy đọc log và sửa nguyên nhân trước khi tiếp tục.

## 5. Viết wrapper để phân biệt lỗi phần mềm và lỗi môi trường

Một test runner thông thường có thể trả về mã khác 0 vì nhiều nguyên nhân:

- Assertion thất bại: hành vi cần kiểm tra đã bị hồi quy.
- Không biên dịch được vì chính commit làm hỏng mã nguồn: có thể là bad nếu đây là tiêu chí của cuộc điều tra.
- Thiếu JDK, SDK hoặc dependency: chưa thể kết luận commit có lỗi hay không.
- Dịch vụ kiểm thử không khởi động được: môi trường chưa sẵn sàng.
- Test không tồn tại ở commit cũ: commit đó không thể chạy phép kiểm tra hiện tại.

Không nên coi mọi mã khác 0 là bad. Hãy tạo wrapper để chuyển kết quả của test harness sang hợp đồng của git bisect.

### 5.1. Quy định mã thoát của test harness

Giả sử một script kiểm thử chuyên biệt có quy ước:

| Mã của test harness | Ý nghĩa |
|---|---|
| 0 | Hành vi đúng, không tái hiện lỗi |
| 10 | Assertion tái hiện đúng lỗi cần tìm |
| 20 | Không thể kiểm tra: thiếu môi trường, dependency hoặc test không áp dụng |
| Mã khác | Chưa phân loại được, cần điều tra |

Các mã 10 và 20 là quy ước của ví dụ, không phải quy ước mặc định của Git hoặc Gradle. Dự án cần thống nhất hợp đồng này trong test harness.

### 5.2. Wrapper shell mẫu

Đặt wrapper ở vị trí có thể truy cập trong toàn bộ lần bisect, ví dụ bên ngoài working tree hoặc trong một công cụ ổn định không bị checkout thay đổi theo từng commit.

~~~sh
#!/bin/sh

# Không dùng set -e vì cần đọc mã thoát của test harness.
set -u

if [ ! -x "./gradlew" ]; then
    echo "SKIP: Gradle wrapper không có ở commit này" >&2
    exit 125
fi

./scripts/check-regression.sh
result=$?

case "$result" in
    0)
        echo "GOOD: test không tái hiện lỗi"
        exit 0
        ;;
    10)
        echo "BAD: test tái hiện lỗi"
        exit 1
        ;;
    20)
        echo "SKIP: môi trường hoặc test không sẵn sàng"
        exit 125
        ;;
    *)
        echo "SKIP: không phân loại được mã thoát $result" >&2
        exit 125
        ;;
esac
~~~

Trong ví dụ này, check-regression.sh là test harness do dự án định nghĩa. Nó cần phân biệt assertion thất bại với việc không thể chạy test. Wrapper chuyển mã 10 thành 1 để Git hiểu là bad, chuyển mã 20 hoặc mã chưa phân loại thành 125 để skip.

Không phải mọi dự án đều cần skip mã không xác định. Nếu một mã thoát cụ thể đã được xác nhận là lỗi phần mềm, hãy ánh xạ nó sang bad. Nếu mã đó có thể là lỗi môi trường, đừng tự động gắn nhãn bad trước khi điều tra.

### 5.3. Vì sao nên đặt wrapper bên ngoài repository?

git bisect run checkout từng commit. Nếu wrapper nằm trong repository nhưng chỉ được thêm ở commit mới, tại commit cũ tệp có thể không tồn tại. Khi đó shell có thể trả về mã 127 (command not found), và Git hiểu mã này là bad.

Có hai cách:

- Đặt wrapper bên ngoài working tree, chẳng hạn trong thư mục công cụ cá nhân hoặc thư mục tạm.
- Đặt wrapper trong repository nhưng bảo đảm nó tồn tại và có cùng ý nghĩa ở mọi commit trong khoảng bisect.

Ví dụ chạy wrapper bên ngoài repository:

~~~
git bisect run sh /tmp/bisect-runner.sh
~~~

Đường dẫn /tmp là ví dụ cho môi trường POSIX hoặc Git Bash tương thích. Trên Windows, dùng đường dẫn mà shell đang chạy Git có thể truy cập, hoặc gọi wrapper qua Git Bash/WSL theo cấu hình của dự án.

Đảm bảo wrapper có quyền đọc và thực thi, các công cụ cần thiết đã được cài và lệnh kiểm thử chạy từ thư mục gốc repository. git bisect run thực thi lệnh tại working tree đang được bisect.

## 6. Chạy bisect tự động

### 6.1. Bắt đầu phiên bisect

Có thể bắt đầu rồi đánh dấu hai mốc:

~~~
git bisect start
git bisect bad <known-bad-commit>
git bisect good <known-good-commit>
~~~

Hoặc truyền hai mốc ngay khi bắt đầu:

~~~
git bisect start <known-bad-commit> <known-good-commit>
~~~

Sau đó Git chọn commit ở giữa phạm vi và checkout commit đó để kiểm tra.

### 6.2. Giao việc kiểm thử cho Git

Chạy wrapper:

~~~
git bisect run sh /tmp/bisect-runner.sh
~~~

Git sẽ:

1. Gọi wrapper tại commit đang được kiểm tra.
2. Đọc mã thoát.
3. Đánh dấu commit là good, bad hoặc skip.
4. Chọn commit tiếp theo.
5. Lặp lại cho tới khi xác định được kết quả hoặc không thể thu hẹp thêm.

Nếu lệnh chạy thành công và lịch sử có ranh giới rõ ràng, Git sẽ báo commit đầu tiên được xác định là bad. Hãy ghi lại mã SHA và thông điệp commit để điều tra.

### 6.3. Xem kết quả và xác nhận thủ công

Sau khi bisect kết thúc:

~~~
git show --stat --oneline <first-bad-commit>
git show <first-bad-commit>
~~~

Đọc diff của commit được tìm thấy để hiểu thay đổi nào có khả năng gây lỗi. Sau đó có thể checkout hoặc tạo branch điều tra riêng nếu cần chạy thêm kiểm tra:

~~~
git switch -c debug/inspect-first-bad <first-bad-commit>
~~~

Lệnh này tạo branch mới tại commit được tìm thấy. Nếu bạn chỉ muốn tiếp tục bisect hoặc trở về branch ban đầu, dùng git bisect reset theo hướng dẫn ở phần kết thúc.

## 7. Xử lý commit không kiểm tra được

Không phải commit nào cũng có thể chạy cùng một test. Có thể gặp các trường hợp:

- Commit cũ chưa có test harness hoặc chưa có script kiểm thử.
- Dự án thay đổi cấu trúc build, nên lệnh hiện tại không còn đúng.
- Dependency đã bị gỡ khỏi registry hoặc không còn phiên bản tương thích.
- Commit cần runtime, compiler hoặc hệ điều hành cũ.
- Một service hoặc dữ liệu test không còn sẵn có.
- Commit nằm giữa quá trình chuyển đổi API nên test hiện tại chưa áp dụng.

Nếu không thể đưa ra kết luận good hoặc bad, hãy skip commit.

### 7.1. Skip tự động bằng mã 125

Trong wrapper, trả về 125 khi không thể kiểm tra:

~~~sh
if [ ! -f "./gradlew" ]; then
    echo "SKIP: commit chưa có Gradle wrapper" >&2
    exit 125
fi
~~~

Khi git bisect run nhận mã 125, nó bỏ qua commit hiện tại và tiếp tục tìm trong phạm vi còn lại.

Chỉ dùng skip khi thực sự không thể kiểm tra. Nếu build thất bại vì chính thay đổi đang điều tra làm mã nguồn không biên dịch được, đó có thể là kết quả bad chứ không phải skip. Quyết định phụ thuộc vào tiêu chí lỗi của cuộc điều tra.

### 7.2. Skip thủ công một commit

Nếu bạn đang chạy bisect thủ công và nhận thấy commit hiện tại không thể kiểm tra:

~~~
git bisect skip
~~~

Có thể chỉ định một hoặc nhiều commit:

~~~
git bisect skip <commit-a> <commit-b>
~~~

Lệnh này đánh dấu các commit được chỉ định là không thể dùng để phân loại. Git sẽ tiếp tục chọn commit khác trong phạm vi tìm kiếm.

### 7.3. Skip một khoảng commit

Nếu biết trước một khoảng lịch sử không thể kiểm thử, có thể skip một range:

~~~
git bisect skip <first-commit>..<last-commit>
~~~

Range dùng cú pháp hai chấm, không bao gồm first-commit nhưng bao gồm các commit có thể đi tới từ last-commit mà không đi qua first-commit. Hãy kiểm tra đúng phạm vi trước khi dùng vì skip quá rộng có thể làm mất khả năng xác định commit gây lỗi.

Không nên skip cả một khoảng chỉ vì một lệnh build đang lỗi. Trước tiên xác định nguyên nhân là do môi trường, do test không áp dụng hay do chính mã nguồn đã hỏng.

## 8. Kết quả bisect có thể mơ hồ khi có commit bị skip

Skip giúp tiếp tục tìm kiếm, nhưng không thể cung cấp thông tin mà test không đo được. Nếu commit đầu tiên bad nằm trong vùng đã skip, Git không thể biết chính xác commit nào trong vùng đó gây lỗi.

Ví dụ:

~~~text
A---B---C---D---E---F---G
good       ?   ?       bad
           skip
~~~

Nếu C và D không kiểm tra được, trong khi B là good và E là bad, commit đầu tiên gây lỗi có thể là C, D hoặc E tùy lịch sử và kết quả. Git có thể thu hẹp phạm vi nhưng vẫn báo một nhóm ứng viên thay vì một commit duy nhất.

Khi nhận được thông báo rằng first bad commit có thể nằm trong các commit bị skip:

1. Đọc danh sách các commit ứng viên Git hiển thị.
2. Kiểm tra xem có thể dựng lại môi trường lịch sử để chạy test ở một số commit hay không.
3. Tìm test tương thích với phiên bản cũ hoặc tạo adapter cho API/build cũ.
4. Dùng kiểm tra thủ công hoặc một tiêu chí khác có thể áp dụng cho vùng đó.
5. Chạy lại bisect với các mốc hoặc lệnh kiểm tra phù hợp hơn.

Không chọn ngẫu nhiên một commit trong vùng skip làm first bad. Kết luận nên ghi rõ phạm vi chưa thể phân biệt nếu không có thêm bằng chứng.

## 9. Phân biệt regression với lỗi kiểm thử và lỗi môi trường

Đây là phần quyết định chất lượng kết quả tự động. Một lệnh trả về non-zero không tự động chứng minh commit có lỗi.

| Tình huống | Phân loại phù hợp | Lý do |
|---|---|---|
| Assertion tái hiện đúng bug | Bad | Hành vi lỗi đã xuất hiện |
| Test qua và không tái hiện bug | Good | Hành vi được kiểm tra vẫn đúng |
| Thiếu runtime hoặc dependency ngoài | Skip | Không thể chạy phép kiểm tra |
| Test chưa tồn tại ở commit lịch sử | Skip hoặc dùng test tương thích | Chưa thể đánh giá bằng test hiện tại |
| Build fail do chính commit làm mã nguồn hỏng | Bad nếu build thành công là tiêu chí | Build failure là regression đang điều tra |
| Test timeout do dịch vụ ngoài mất kết nối | Skip hoặc chạy lại có kiểm soát | Không đủ bằng chứng về mã nguồn |
| Test flaky, kết quả thay đổi giữa các lần chạy | Chưa phân loại | Cần ổn định test trước |

### 9.1. Lỗi biên dịch có thể là bad

Nếu mục tiêu điều tra là “commit nào làm dự án không còn biên dịch”, lỗi compile là tín hiệu bad. Không nên skip chỉ vì build thất bại.

Ngược lại, nếu mục tiêu là “commit nào làm chức năng tìm kiếm trả kết quả sai”, một commit không thể build do JDK không tương thích với máy kiểm thử chưa chắc là bad. Cần xác định có thể dựng đúng toolchain lịch sử hay không.

### 9.2. Test không tồn tại ở commit cũ

Nếu test được thêm sau khi bug đã xuất hiện, các commit cũ không có test đó. Có thể đặt test bên ngoài repository và viết adapter để gọi API tương ứng ở từng giai đoạn, hoặc dùng một test hành vi qua giao diện ổn định.

Nếu không thể tạo phép kiểm tra tương thích, skip các commit không áp dụng và ghi lại giới hạn của kết quả.

### 9.3. Test không ổn định

Một test flaky có thể đánh dấu cùng một commit lúc good, lúc bad. Điều này phá vỡ giả định của bisect. Hãy:

- Chạy test nhiều lần để đo độ ổn định.
- Cô lập dữ liệu và dịch vụ phụ thuộc.
- Tắt yếu tố ngẫu nhiên hoặc cố định seed nếu phù hợp.
- Tách lỗi môi trường khỏi assertion.
- Chỉ bắt đầu bisect khi tiêu chí đã đủ tin cậy.

## 10. Lưu và phát lại phiên bisect

git bisect ghi lại các quyết định good, bad và skip trong log. Có thể lưu log để tái hiện cuộc điều tra:

~~~ 
git bisect log > bisect-session.log
~~~

Sau đó phát lại trong repository phù hợp:

~~~ 
git bisect reset
git bisect replay bisect-session.log
~~~

Log giúp chia sẻ cách chọn mốc và những commit đã skip với đồng đội. Tuy nhiên, log không tự đóng gói môi trường, dependency hay script kiểm thử. Để người khác tái hiện được, hãy lưu cả phiên bản wrapper, test harness, yêu cầu toolchain và thông tin dữ liệu test.

Trong một phiên đang chạy, xem log:

~~~ 
git bisect log
~~~

Có thể dùng git bisect visualize để xem các commit còn liên quan trong phạm vi điều tra bằng công cụ log được cấu hình.

## 11. Kết thúc bisect và khôi phục branch

Khi đã tìm được commit hoặc muốn dừng điều tra, chạy:

~~~ 
git bisect reset
~~~

Git thoát chế độ bisect và quay về vị trí ban đầu trước khi bắt đầu phiên, thường là branch hoặc commit bạn đang đứng lúc chạy git bisect start.

Nếu cần trở về một vị trí cụ thể:

~~~ 
git bisect reset <branch-or-commit>
~~~

Trước khi reset, hãy lưu mã SHA và log cần thiết. Nếu đã tạo branch điều tra tại commit tìm được, branch đó vẫn trỏ tới commit điều tra sau khi thoát bisect.

Không nhầm git bisect reset với git reset. Lệnh đầu kết thúc phiên bisect; lệnh thứ hai di chuyển HEAD hoặc cập nhật index/working tree tùy tùy chọn và có thể làm mất thay đổi nếu dùng không đúng.

## 12. Ví dụ hoàn chỉnh: tìm commit làm hỏng tìm kiếm

Giả sử nhóm phát hiện tìm kiếm không còn bỏ qua khác biệt chữ hoa và chữ thường. Commit v1.2.0 đã được kiểm tra là tốt, còn main hiện tại bị lỗi.

**Bước 1 — Xác nhận mốc**

~~~ 
git status -sb
git fetch origin
git show --no-patch --oneline v1.2.0
git show --no-patch --oneline origin/main
~~~

**Bước 2 — Bắt đầu bisect**

~~~ 
git bisect start
git bisect bad origin/main
git bisect good v1.2.0
~~~

**Bước 3 — Chạy kiểm thử tự động**

Giả sử wrapper ở ngoài repository và test harness có hợp đồng mã thoát đã thống nhất:

~~~ 
git bisect run sh /tmp/bisect-search.sh
~~~

Trong quá trình chạy:

- Commit có kết quả test 0 được đánh dấu good.
- Commit có kết quả regression được wrapper chuyển thành 1 và đánh dấu bad.
- Commit không có môi trường hoặc test phù hợp được wrapper chuyển thành 125 và skip.

**Bước 4 — Đọc kết quả**

~~~ 
git show --stat --oneline <first-bad-commit>
git show <first-bad-commit>
git bisect log
~~~

Nếu Git báo một commit duy nhất, xác nhận lại bằng cách chạy test tại commit đó và commit cha của nó. Nếu kết quả còn mơ hồ do commit bị skip, điều tra vùng ứng viên và cải thiện test trước khi kết luận.

**Bước 5 — Kết thúc phiên**

~~~ 
git bisect reset
~~~

Sau đó ghi lại commit gây lỗi, test đã dùng, các commit bị skip, lý do skip và giới hạn của kết quả trong ticket hoặc báo cáo điều tra.

## 13. Lỗi thường gặp khi tự động hóa bisect

**Mã thoát bị ánh xạ sai.** Test thất bại do môi trường có thể bị đánh dấu bad. Xây dựng wrapper có hợp đồng rõ ràng và thử nghiệm mã thoát trước khi chạy toàn bộ bisect.

**Runner không tồn tại ở commit cũ.** Nếu script được checkout theo repository và không có ở lịch sử cũ, shell có thể trả về 127; Git xem đây là bad. Đặt runner bên ngoài repository hoặc bảo đảm nó tồn tại ở mọi commit.

**Dùng set -e rồi không đọc được mã thoát.** Với shell, set -e có thể kết thúc script ngay khi test trả về non-zero. Nếu cần ánh xạ mã thoát, gọi lệnh, lưu mã vào biến rồi dùng case hoặc if để phân loại.

**Skip quá nhiều commit.** Skip quá rộng có thể khiến Git chỉ xác định được một khoảng ứng viên. Hãy cố gắng dựng lại toolchain hoặc viết test tương thích.

**Dùng test flaky.** Kết quả không ổn định làm bisect phân nhánh sai. Cần ổn định test trước khi chạy.

**Không lưu log.** Nếu không lưu git bisect log, nhóm khó tái hiện các quyết định good, bad và skip.

**Quên thoát bisect.** Sau khi điều tra, chạy git bisect reset để trở về branch hoặc commit ban đầu.

**Đồng nhất compile failure với lỗi chức năng.** Hãy xác định mục tiêu cuộc điều tra. Build failure chỉ là bad khi khả năng build là tiêu chí đang kiểm tra hoặc failure do chính thay đổi trong commit gây ra.

## 14. Checklist cho một phiên bisect tự động

**Trước khi chạy**

- [ ] Đã xác nhận đúng repository và working tree sạch.
- [ ] Đã chọn commit good và bad có bằng chứng.
- [ ] Đã xác định một tiêu chí kiểm thử có thể tái hiện.
- [ ] Đã kiểm tra test harness có thể chạy trên các commit lịch sử.
- [ ] Đã đặt runner ở vị trí tồn tại trong toàn bộ phiên bisect.
- [ ] Đã định nghĩa mã thoát good, bad và skip rõ ràng.

**Trong khi chạy**

- [ ] Mã 0 chỉ được dùng khi test xác nhận trạng thái good.
- [ ] Mã 1 đến 127, trừ 125, chỉ được dùng khi xác nhận bad.
- [ ] Mã 125 được dùng khi không thể kiểm tra.
- [ ] Lỗi thực thi nghiêm trọng được xử lý để bisect dừng.
- [ ] Test flaky hoặc lỗi dịch vụ ngoài không bị nhầm thành regression.

**Sau khi chạy**

- [ ] Đã lưu first bad commit và git bisect log.
- [ ] Đã xác minh lại commit tìm được và commit cha.
- [ ] Đã xem danh sách commit bị skip và đánh giá độ mơ hồ.
- [ ] Đã ghi rõ giới hạn nếu không thể xác định duy nhất một commit.
- [ ] Đã chạy git bisect reset để kết thúc phiên.

## 15. Kết luận

git bisect run tự động hóa việc tìm commit gây lỗi bằng cách chạy một lệnh kiểm thử tại từng commit được chọn. Để kết quả chính xác, lệnh kiểm thử cần có tiêu chí ổn định và trả về mã thoát đúng: 0 cho good, mã từ 1 đến 127 trừ 125 cho bad, 125 cho commit không thể kiểm tra, còn mã lớn hơn 127 làm quá trình dừng.

Commit không kiểm tra được cần được skip có chủ đích, không gán nhãn good hoặc bad theo suy đoán. Khi có nhiều commit bị skip, kết quả có thể chỉ ra một nhóm ứng viên. Hãy lưu log, điều tra phạm vi mơ hồ, xác nhận lại commit tìm được và kết thúc phiên bằng git bisect reset. Cách làm này giúp nhóm tìm nguyên nhân hồi quy nhanh hơn mà vẫn giữ được độ tin cậy của kết luận.
