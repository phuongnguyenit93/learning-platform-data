# Định vị commit gây lỗi bằng `git bisect`

Khi một lỗi xuất hiện trong dự án, ta thường biết phiên bản trước đó còn hoạt động và phiên bản hiện tại đã có lỗi, nhưng không biết commit nào đưa lỗi vào mã nguồn. Nếu phải đọc thủ công hàng trăm commit, việc tìm nguyên nhân có thể mất nhiều thời gian. `git bisect` giải quyết vấn đề bằng cách tìm kiếm nhị phân trên lịch sử commit: Git lần lượt chọn một commit ở giữa phạm vi, ta kiểm tra commit đó còn tốt hay đã lỗi, rồi thu hẹp phạm vi cho đến khi xác định được commit đầu tiên gây ra vấn đề.

Trong dịch vụ quản lý mã nguồn Git, `git bisect` là công cụ quan trọng để truy tìm thay đổi và phục hồi có cơ sở. Nó giúp khoanh vùng nguyên nhân trước khi quyết định sửa mã, revert commit hoặc phát hành bản vá. Kết quả có giá trị nhất khi ta có tiêu chí kiểm tra rõ ràng và có thể xác định đáng tin cậy một commit là `good` hay `bad`.

## 1. Ý tưởng tìm kiếm nhị phân trong lịch sử Git

Giả sử ứng dụng chạy tốt ở commit `A`, nhưng lỗi đã xuất hiện tại commit `H`. Giữa hai commit có nhiều thay đổi:

```text
A --- B --- C --- D --- E --- F --- G --- H
good                                      bad
```

Thay vì kiểm tra từng commit từ `A` đến `H`, Git chọn một commit ở giữa phạm vi, ví dụ `E`. Nếu `E` vẫn tốt, commit gây lỗi nằm sau `E`; nếu `E` đã lỗi, commit gây lỗi nằm trong phần từ `A` đến `E`. Mỗi lần kiểm tra, phạm vi ứng viên được thu hẹp khoảng một nửa.

```text
Lần 1:  A --- B --- C --- D --- E --- F --- G --- H
                              ^ kiểm tra E

Nếu E good:                    E --- F --- G --- H
                                     ^ kiểm tra giữa phần còn lại

Nếu E bad:   A --- B --- C --- D --- E
                   ^ tiếp tục tìm trong nửa đầu
```

Với lịch sử tuyến tính có N commit ứng viên, tìm kiếm nhị phân thường cần khoảng log cơ số 2 của N lần kiểm tra thay vì tối đa N lần. Ví dụ, phạm vi 128 commit thường chỉ cần khoảng 7 lần kiểm tra để tìm được ranh giới. Số lần thực tế có thể khác do cấu trúc DAG, commit bị bỏ qua hoặc kết quả kiểm tra không nhất quán.

`git bisect` không tự hiểu thế nào là lỗi. Người thực hiện phải cung cấp hai mốc đáng tin cậy:

- **Good:** commit mà tiêu chí kiểm tra xác nhận lỗi chưa xuất hiện.
- **Bad:** commit mà tiêu chí kiểm tra xác nhận lỗi đã xuất hiện.

Git sử dụng quan hệ tổ tiên giữa các commit để thu hẹp vùng tìm kiếm. Kết quả thường là commit đầu tiên trên đường lịch sử được kiểm tra mà trạng thái chuyển từ good sang bad.

## 2. Chuẩn bị trước khi chạy bisect

Trước tiên, xác định biểu hiện lỗi và cách kiểm tra có thể lặp lại. Ví dụ:

- Một API trả về HTTP 500 thay vì HTTP 200.
- Một unit test trước đây pass nhưng hiện tại fail.
- Một lệnh build bị lỗi sau một thay đổi gần đây.
- Một thao tác giao diện không còn hoạt động trong phiên bản mới.

Tiêu chí cần đủ cụ thể để cùng một commit luôn cho kết quả tương tự. Nếu lỗi chỉ xuất hiện ngẫu nhiên, phụ thuộc dữ liệu bên ngoài hoặc môi trường, hãy ổn định điều kiện kiểm tra trước khi bisect.

Kiểm tra repository và lưu lại công việc chưa commit:

```bash
git status -sb
git log --oneline --decorate -10
```

`git bisect` sẽ di chuyển `HEAD` qua nhiều commit, thường đưa repository vào trạng thái detached HEAD. Vì vậy, nên có working tree sạch. Commit hoặc stash công việc đang làm trước khi bắt đầu; lưu riêng file untracked quan trọng nếu stash mặc định không bao gồm chúng.

Xác định hai mốc:

```bash
git log --oneline --decorate --all
```

Chọn một commit cũ đã xác nhận tốt và một commit mới đã xác nhận lỗi. Có thể dùng mã commit, tên nhánh, tag hoặc biểu thức revision. Ví dụ:

```text
v2.3.0       phiên bản còn tốt
HEAD         phiên bản hiện tại đã có lỗi
```

Nếu cần kiểm tra mốc tốt có phải tổ tiên của mốc lỗi hay không:

```bash
git merge-base --is-ancestor v2.3.0 HEAD
```

Lệnh trả về mã thoát 0 khi `v2.3.0` là tổ tiên của `HEAD`. Với quy trình bisect thông thường, mốc good nên nằm trên dòng lịch sử dẫn tới mốc bad để phạm vi tìm kiếm có ý nghĩa rõ ràng.

## 3. Chạy `git bisect` thủ công

Quy trình cơ bản có ba giai đoạn: bắt đầu, đánh giá commit được chọn và kết thúc.

### Bước 1: Bắt đầu phiên bisect

```bash
git bisect start
```

Lệnh này khởi tạo phiên bisect. Tiếp theo, đánh dấu commit hiện tại là bad và một commit cũ là good:

```bash
git bisect bad HEAD
git bisect good v2.3.0
```

Có thể truyền hai mốc ngay khi bắt đầu:

```bash
git bisect start HEAD v2.3.0
```

Trong cú pháp này, commit đầu tiên là mốc bad và commit thứ hai là mốc good. Dùng cách tách lệnh nếu muốn ghi nhận từng mốc hoặc cần kiểm tra lại trước khi bắt đầu tìm kiếm.

### Bước 2: Kiểm tra commit Git chọn

Sau khi nhận đủ mốc, Git checkout một commit ở giữa phạm vi. Thông báo thường cho biết còn bao nhiêu commit ứng viên và mã commit hiện tại.

Kiểm tra trạng thái:

```bash
git status -sb
git log -1 --oneline --decorate
```

Chạy lại đúng quy trình tái hiện lỗi. Nếu lỗi chưa xuất hiện, đánh dấu good:

```bash
git bisect good
```

Nếu lỗi xuất hiện, đánh dấu bad:

```bash
git bisect bad
```

Git tiếp tục checkout một commit khác trong phạm vi đã thu hẹp. Lặp lại việc kiểm tra và đánh dấu cho đến khi Git xác định commit gây lỗi đầu tiên.

### Bước 3: Đọc kết quả

Khi tìm được ranh giới, Git hiển thị thông báo tương tự:

```text
<commit-id> is the first bad commit
```

Thông tin này xác định commit đầu tiên mà quá trình bisect tìm thấy có trạng thái bad, trong phạm vi và theo các đánh giá đã cung cấp. Xem chi tiết commit:

```bash
git show --stat <commit-id>
git show <commit-id>
```

Đọc thông điệp, danh sách file và diff để hiểu thay đổi nào có thể gây lỗi. Nếu commit có nhiều thay đổi không liên quan, tiếp tục phân tích diff, test hoặc dùng các công cụ truy tìm khác để tìm dòng mã cụ thể.

### Bước 4: Kết thúc phiên bisect

```bash
git bisect reset
```

Lệnh này kết thúc phiên bisect và đưa `HEAD` trở lại vị trí trước khi bắt đầu phiên, thường là nhánh và commit mà ta đang đứng ban đầu. Sau đó kiểm tra:

```bash
git status -sb
git branch --show-current
```

Nên chạy `git bisect reset` sau khi đã ghi lại mã commit gây lỗi và thông tin cần thiết. Không cần giữ repository ở detached HEAD sau khi hoàn tất việc tìm kiếm.

## 4. Ví dụ hoàn chỉnh: tìm regression trong một ứng dụng

Giả sử nhóm nhận báo cáo rằng chức năng đăng nhập trả về lỗi khi người dùng nhập mật khẩu hợp lệ. Nhóm xác nhận:

- Tag `v1.8.0` vẫn đăng nhập bình thường.
- `HEAD` hiện tại đã tái hiện lỗi.
- Có thể chạy test `./gradlew test --tests LoginServiceTest` để kiểm tra.

Quy trình:

```bash
# Bắt đầu bisect và xác định hai mốc
git bisect start
git bisect bad HEAD
git bisect good v1.8.0

# Git checkout commit giữa phạm vi
# Chạy test tại commit hiện tại
./gradlew test --tests LoginServiceTest

# Nếu test pass:
git bisect good

# Nếu test fail do đúng regression đang tìm:
git bisect bad

# Lặp lại test và đánh dấu cho tới khi Git tìm được commit đầu tiên bị lỗi

# Xem commit kết quả rồi kết thúc phiên
git show --stat <first-bad-commit>
git bisect reset
```

Trong thực tế, không chạy cả hai lệnh `good` và `bad` cho cùng một lần kiểm tra. Chọn đúng một kết quả dựa trên tiêu chí đã định nghĩa. Nếu test fail vì lỗi build hoặc môi trường không liên quan tới regression, không đánh dấu bad; dùng `git bisect skip` như phần tiếp theo.

## 5. Bỏ qua commit không thể đánh giá bằng `git bisect skip`

Không phải commit nào cũng build hoặc chạy được trong môi trường hiện tại. Một commit ở giữa có thể:

- Thiếu file cấu hình hoặc phụ thuộc chỉ được thêm ở commit sau.
- Có lỗi build độc lập với lỗi đang điều tra.
- Chỉ chạy được với phiên bản JDK, compiler hoặc dịch vụ không còn sẵn.
- Không thể tái hiện lỗi do thiếu dữ liệu thử nghiệm.

Nếu không thể kết luận commit là good hay bad, dùng:

```bash
git bisect skip
```

Git bỏ qua commit hiện tại và chọn một commit khác. Có thể chỉ định nhiều commit hoặc một revision range cần bỏ qua:

```bash
git bisect skip <commit-a> <commit-b>
git bisect skip <good-base>..<bad-tip>
```

Hãy kiểm tra phạm vi trước khi bỏ qua một dải lớn. Càng nhiều commit bị skip, kết quả càng có thể kém chính xác.

Nếu các commit bị skip nằm gần ranh giới good/bad, Git có thể chỉ xác định được một tập commit có khả năng là đầu tiên gây lỗi thay vì một commit duy nhất. Thông báo kết quả sẽ nêu phạm vi hoặc danh sách ứng viên. Khi đó, cần kiểm tra thủ công các commit còn lại hoặc cải thiện môi trường để đánh giá lại.

Không dùng `skip` chỉ vì test fail khó hiểu. Trước tiên xác định test có thực sự đang đo lỗi cần tìm hay không; nếu commit làm xuất hiện regression, nó vẫn cần được đánh dấu bad ngay cả khi có thêm lỗi phụ khác.

## 6. Tự động hóa với `git bisect run`

Nếu đã có script kiểm tra trả về mã thoát nhất quán, có thể để Git tự chạy test ở từng commit:

```bash
git bisect start HEAD v1.8.0
git bisect run ./scripts/check-login-regression.sh
```

Git checkout từng commit ứng viên, chạy script và dựa vào mã thoát để quyết định trạng thái:

| Mã thoát của script | Cách Git hiểu |
| --- | --- |
| `0` | Good: test xác nhận lỗi chưa xuất hiện |
| `1` đến `127`, trừ `125` | Bad: test xác nhận lỗi xuất hiện |
| `125` | Skip: không thể kiểm tra commit này |
| `128` trở lên | Dừng bisect run vì script hoặc lệnh gặp lỗi nghiêm trọng |

### Ví dụ script kiểm tra

Trên Linux/macOS hoặc môi trường có shell POSIX, có thể tạo script:

```sh
#!/bin/sh

if [ ! -x ./gradlew ]; then
    # Wrapper không tồn tại hoặc không thể chạy ở commit này.
    exit 125
fi

./gradlew test --tests LoginServiceTest
result=$?

if [ "$result" -eq 0 ]; then
    exit 0
fi

# Nếu test không chạy được do môi trường/thiếu dependency,
# hãy phân biệt trường hợp này với regression thực sự.
if [ "$result" -eq 125 ]; then
    exit 125
fi

# Các lỗi test khác được xem là bad theo tiêu chí của bài kiểm tra.
exit 1
```

Script trên chỉ phù hợp nếu mọi lỗi test khác 0 đều thể hiện regression cần tìm. Nếu build thất bại vì dependency không sẵn có hoặc commit cũ không hỗ trợ lệnh test, script cần nhận diện trường hợp đó và trả `125` để skip. Không nên coi mọi lỗi build là bad một cách máy móc.

Đặt quyền thực thi nếu môi trường yêu cầu:

```bash
chmod +x scripts/check-login-regression.sh
```

Sau đó chạy `git bisect run`. Khi hoàn tất, Git hiển thị commit đầu tiên bị lỗi và thoát khỏi chuỗi chạy tự động; vẫn nên xem lại kết quả, kiểm tra diff và chạy xác minh độc lập. Cuối cùng:

```bash
git bisect reset
```

### Yêu cầu đối với script tự động

- Kết quả phải phản ánh đúng tiêu chí good/bad đã thống nhất.
- Script phải có thể chạy lặp lại ở mọi commit ứng viên.
- Không phụ thuộc vào trạng thái còn sót lại từ lần chạy trước.
- Không ghi đè dữ liệu hoặc file người dùng ngoài phạm vi thử nghiệm.
- Phân biệt lỗi test thực sự với lỗi môi trường hoặc lỗi build không thể đánh giá.
- Trả `125` khi không thể đưa ra kết luận cho commit hiện tại.

Script phải có sẵn ở mọi commit mà Git có thể kiểm tra. Nếu script chỉ được thêm ở commit mới, khi bisect checkout một commit cũ hơn Git sẽ không tìm thấy đường dẫn đó. Có thể đặt script ở ngoài working tree hoặc bảo đảm script tồn tại trong toàn bộ phạm vi lịch sử cần kiểm tra. Script cũng có thể tạo file build, cache hoặc log; những file này không nên làm thay đổi kết quả kiểm tra ở commit tiếp theo. Nếu cần, hãy dọn riêng các file sinh ra an toàn trong script, hoặc chạy trong môi trường/build directory dùng riêng.

## 7. Theo dõi và lưu lại phiên bisect

Git cung cấp các lệnh giúp quan sát và ghi lại quyết định trong phiên bisect:

```bash
git bisect log
git bisect visualize
git bisect terms
```

- `git bisect log` hiển thị các lệnh và quyết định good/bad/skip đã ghi nhận trong phiên.
- `git bisect visualize` mở công cụ xem lịch sử các commit còn trong phạm vi tìm kiếm; `git bisect view` là bí danh tương đương.
- `git bisect terms` hiển thị tên các thuật ngữ đang dùng cho hai trạng thái cũ/mới (mặc định là good/bad).

Có thể lưu nhật ký để tái hiện hoặc chia sẻ với đồng đội:

```bash
git bisect log > ../bisect-session.log
```

Nếu đang chạy lệnh từ thư mục gốc repository, đường dẫn `../bisect-session.log` đặt file log bên ngoài working tree để file untracked không ảnh hưởng tới việc Git checkout các commit ứng viên. Nếu chạy từ thư mục khác, hãy dùng một đường dẫn tuyệt đối nằm ngoài repository.

Sau khi kết thúc phiên, nếu cần tái hiện các quyết định trong một phiên bisect khác, bắt đầu bisect rồi phát lại log:

```bash
git bisect start
git bisect replay ../bisect-session.log
```

Nhật ký lưu các mốc và quyết định đã đưa ra. Nếu lịch sử repository thay đổi hoặc các ref không còn tồn tại, replay có thể không tái hiện được toàn bộ phiên. Hãy giữ file log cùng thông tin phiên bản repository và môi trường test khi cần báo cáo lỗi.

## 8. Dùng thuật ngữ khác thay cho good/bad

Trong một số tình huống, khái niệm good/bad có thể gây nhầm lẫn. Ví dụ, khi tìm commit đầu tiên thêm một tính năng, ta có thể muốn dùng `old` và `new` thay cho good/bad:

```bash
git bisect start --term-old=old --term-new=new
git bisect new HEAD
git bisect old v1.8.0
```

`old` đại diện cho trạng thái trước khi có thay đổi cần tìm; `new` đại diện cho trạng thái sau khi thay đổi xuất hiện. Có thể chọn tên dễ hiểu hơn:

```bash
git bisect start --term-old=without-feature --term-new=with-feature
```

Sau đó dùng các từ khóa tương ứng khi đánh dấu commit. Cần nhất quán giữa thuật ngữ và mục tiêu tìm kiếm; đừng dùng `good`/`bad` theo nghĩa chung chung nếu đang điều tra sự xuất hiện của tính năng hoặc một hành vi thay đổi có chủ đích.

## 9. Bisect trên lịch sử có merge commit

Lịch sử Git thường là DAG thay vì một đường thẳng. Một nhánh tính năng có thể được merge vào `main`, khiến vùng tìm kiếm có nhiều đường đi. Git bisect vẫn làm việc trên quan hệ tổ tiên, nhưng commit được chọn có thể nằm trên nhánh phụ hoặc là merge commit.

Nếu muốn chỉ kiểm tra các commit trên đường first-parent của nhánh chính, có thể bắt đầu:

```bash
git bisect start --first-parent HEAD v2.3.0
```

`--first-parent` giới hạn quá trình tìm kiếm theo chuỗi first-parent. Cách này hữu ích khi muốn tìm lần tích hợp nào đưa lỗi vào nhánh chính, ví dụ commit merge một pull request. Nó có thể không xác định commit cụ thể bên trong nhánh tính năng đã tạo ra lỗi; nếu cần tìm sâu trong nhánh phụ, hãy bisect phạm vi lịch sử của nhánh đó riêng.

Khi thấy commit gây lỗi là merge commit, kiểm tra các parent và nội dung tích hợp:

```bash
git show --no-patch --pretty=raw <merge-commit>
git show --stat <merge-commit>
git diff <merge-commit>^1 <merge-commit>
```

Parent thứ nhất thường là nhánh nhận merge trong quy trình thông thường, nhưng cần xác nhận bằng lịch sử thực tế. So sánh merge commit với parent thứ nhất giúp xem thay đổi được đưa vào nhánh chính tại lần tích hợp đó.

## 10. Giới hạn và các nguyên nhân làm kết quả sai lệch

### Tiêu chí kiểm tra không ổn định

Nếu cùng một commit lúc test pass, lúc test fail, Git có thể nhận các nhãn good/bad không nhất quán và đưa ra kết quả sai. Hãy ổn định dữ liệu, thời gian, dịch vụ ngoài, cấu hình và môi trường chạy trước khi bisect.

### Regression xuất hiện rồi biến mất

Tìm kiếm nhị phân giả định có một ranh giới đủ rõ giữa vùng good và bad trong phạm vi đã chọn. Nếu một commit thêm lỗi nhưng commit sau sửa lỗi, trạng thái có thể chuyển good → bad → good. Khi đó không có một đường ranh giới đơn giản để bisect xác định theo cách thông thường. Hãy thu hẹp phạm vi, xác định thời điểm lỗi xuất hiện và biến mất, hoặc dùng tiêu chí kiểm tra cụ thể hơn.

### Commit trung gian không build được

Một commit có thể chưa tương thích với compiler, dependency hoặc cấu trúc build hiện tại. Phân loại commit đó là skip nếu không thể đánh giá. Nếu quá nhiều commit bị skip, hãy phục hồi môi trường lịch sử hoặc xây dựng test tương thích hơn.

### Lỗi phụ thuộc môi trường

Lỗi do hệ điều hành, biến môi trường, dịch vụ bên ngoài, dữ liệu test hoặc quyền truy cập có thể khiến kết quả không phản ánh nội dung commit. Cố định các yếu tố này trước khi chạy.

### Mốc good/bad chọn sai

Nếu commit được đánh dấu good thực ra đã có lỗi hoặc commit bad vẫn hoạt động, Git sẽ tìm ranh giới dựa trên thông tin sai. Khi nghi ngờ, kiểm tra lại hai mốc và chạy test trực tiếp trước khi bắt đầu.

## 11. Sau khi tìm được commit gây lỗi

`git bisect` giúp định vị thay đổi; bước tiếp theo là hiểu vì sao thay đổi đó gây lỗi và chọn cách xử lý phù hợp.

### Xem nội dung và ngữ cảnh commit

```bash
git show --format=fuller --stat <first-bad-commit>
git show <first-bad-commit>
git log --oneline --decorate --ancestry-path <good-commit>..<first-bad-commit>
```

Kiểm tra tác giả, thời gian, thông điệp, file bị thay đổi và các commit trước đó trong đường lịch sử. Đọc code xung quanh thay đổi để xác định nguyên nhân thực sự.

### Chọn cách sửa

- Nếu thay đổi sai và chưa cần giữ lại, tạo commit sửa lỗi hoặc revert commit gây lỗi theo quy trình nhóm.
- Nếu thay đổi đúng nhưng thiếu xử lý trường hợp biên, bổ sung test và sửa logic.
- Nếu lỗi chỉ xuất hiện khi nhiều commit kết hợp, kiểm tra tương tác giữa các thay đổi thay vì chỉ nhìn một dòng code.
- Nếu lỗi thuộc nhánh release, xác định cách backport bản sửa và kiểm tra trên chính phiên bản đó.

Không nên revert ngay chỉ vì bisect chỉ ra một commit. Commit đó có thể là thay đổi hợp lệ làm lộ ra lỗi tiềm ẩn ở thành phần khác. Cần phân tích diff và tái hiện lỗi trước khi quyết định sửa hoặc revert.

## 12. Các lệnh thường dùng

| Lệnh | Mục đích |
| --- | --- |
| `git bisect start` | Bắt đầu phiên tìm kiếm |
| `git bisect bad <rev>` | Đánh dấu một commit có lỗi |
| `git bisect good <rev>` | Đánh dấu một commit chưa có lỗi |
| `git bisect skip [<rev>...]` | Bỏ qua commit không thể đánh giá |
| `git bisect run <cmd>` | Tự động chạy lệnh kiểm tra ở từng commit |
| `git bisect log` | Xem các quyết định trong phiên |
| `git bisect replay <file>` | Phát lại các quyết định từ nhật ký |
| `git bisect visualize` | Xem các commit còn trong phạm vi |
| `git bisect terms` | Xem thuật ngữ trạng thái hiện dùng |
| `git bisect reset` | Kết thúc phiên và quay về vị trí trước khi bisect |

## 13. Checklist thực hiện bisect

Trước khi bắt đầu:

1. Mô tả lỗi bằng một tiêu chí có thể kiểm tra lặp lại.
2. Xác nhận một commit good và một commit bad đáng tin cậy.
3. Đảm bảo mốc good nằm trong lịch sử dẫn tới mốc bad.
4. Commit hoặc stash công việc dở dang và kiểm tra working tree.
5. Chuẩn bị môi trường có thể build/test ở các commit lịch sử.

Trong quá trình tìm kiếm:

1. Kiểm tra đúng commit Git đã checkout.
2. Chạy cùng một test hoặc kịch bản ở mỗi lần.
3. Đánh dấu good hoặc bad dựa trên kết quả đã định nghĩa.
4. Chỉ dùng skip khi không thể đưa ra kết luận.
5. Ghi lại log và thông tin môi trường nếu cần chia sẻ kết quả.

Sau khi tìm thấy commit:

1. Ghi lại mã commit và thông điệp.
2. Đọc diff và kiểm tra các thay đổi liên quan.
3. Tái hiện lỗi và xác minh nguyên nhân.
4. Chọn cách sửa, revert hoặc backport phù hợp.
5. Chạy `git bisect reset` và kiểm tra lại trạng thái repository.

## 14. Thực hành

Tạo repository thử nghiệm với chuỗi commit có chủ ý:

1. Tạo commit đầu tiên thêm chương trình nhỏ và xác nhận chương trình chạy đúng.
2. Tạo thêm một số commit chỉnh sửa khác nhau.
3. Ở một commit giữa, cố ý thêm lỗi có thể kiểm tra tự động, ví dụ đổi điều kiện khiến test thất bại.
4. Tạo thêm vài commit sau đó nhưng không sửa lỗi.
5. Xác nhận commit đầu chuỗi là good và commit cuối chuỗi là bad.
6. Chạy `git bisect start`, đánh dấu hai mốc rồi kiểm tra từng commit được Git chọn.
7. Xác nhận Git chỉ ra commit đã cố ý thêm lỗi.
8. Kết thúc bằng `git bisect reset`.
9. Lặp lại bài tập bằng script và `git bisect run`.
10. Tạo một commit trung gian không thể build và thử skip để quan sát ảnh hưởng đến độ chính xác của kết quả.

## 15. Tự kiểm tra kiến thức

1. `git bisect` sử dụng nguyên tắc nào để thu hẹp số commit cần kiểm tra?
2. Vì sao phải có ít nhất một mốc good và một mốc bad đáng tin cậy?
3. Git checkout trạng thái nào trong lúc bisect và vì sao thường thấy detached HEAD?
4. Khi nào nên dùng `git bisect skip`?
5. `git bisect run` diễn giải các mã thoát `0`, `125` và mã khác như thế nào?
6. Vì sao test không ổn định có thể làm sai kết quả bisect?
7. `--first-parent` hữu ích trong tình huống nào và có giới hạn gì?
8. Sau khi tìm được first bad commit, cần kiểm tra những thông tin nào trước khi revert?
9. `git bisect log` và `git bisect replay` hỗ trợ việc gì?
10. Vì sao phải chạy `git bisect reset` sau khi hoàn thành?

## Kết luận

`git bisect` dùng tìm kiếm nhị phân để định vị commit đầu tiên làm thay đổi trạng thái từ good sang bad trong một phạm vi lịch sử. Hãy bắt đầu bằng hai mốc đã xác minh, chạy cùng một tiêu chí kiểm tra ở mỗi commit và dùng `skip` khi không thể kết luận. Với test có thể tự động hóa, `git bisect run` giúp giảm thao tác thủ công; với lịch sử có merge, `--first-parent` giúp tập trung vào các lần tích hợp. Sau khi tìm được commit, hãy đọc diff, xác minh nguyên nhân và kết thúc phiên bằng `git bisect reset` trước khi sửa hoặc phục hồi mã nguồn.
