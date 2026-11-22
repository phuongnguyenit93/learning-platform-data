# Rebase nhánh công việc lên nhánh đích đã cập nhật

Trong quá trình phát triển, nhánh đích như `main` thường tiếp tục nhận commit mới trong khi bạn vẫn làm việc trên nhánh tính năng. Nhánh công việc vì thế có thể đang dựa trên một phiên bản cũ của `main`. Rebase giúp đặt lại các commit riêng của nhánh công việc lên đầu nhánh đích mới nhất để bạn tiếp tục phát triển trên nền cập nhật.

Ví dụ, bạn tạo `feature/payment` từ `main` tại commit `B`. Trong lúc bạn làm việc, `main` tiến thêm đến commit `C`. Rebase sẽ phát lại các commit tính năng lên sau `C`, tạo lịch sử mới mà vẫn giữ phần thay đổi của tính năng.

Rebase tạo commit mới cho phần lịch sử được phát lại. Các commit mới có parent và mã định danh khác với commit cũ. Nếu nhánh chỉ thuộc riêng bạn, việc cập nhật khá đơn giản. Nếu nhánh đã được push và đồng đội đang dựa trên nó, cần phối hợp trước khi viết lại lịch sử chung.

## 1. Mô hình khi nhánh đích tiến lên

Ban đầu, `feature/payment` được tạo từ commit `B`. Sau đó, nhánh `main` nhận thêm commit `C`:

```text
P---A---B---C  main
         \
          F1---F2  feature/payment
```

Khi rebase `feature/payment` lên `main`, Git phát lại các commit tính năng và tạo `F1'`, `F2'`:

```text
P---A---B---C  main
             \
              F1'---F2'  feature/payment
```

`F1` và `F2` vẫn tồn tại trong repository nếu còn ref hoặc object khác giữ chúng, nhưng nhánh `feature/payment` local giờ trỏ đến `F2'`. Một nhánh remote đã được push trước đó vẫn có thể trỏ đến `F2` cho đến khi có thao tác cập nhật remote.

Điều này gây ra vấn đề cho đồng đội. Giả sử một người khác đã tạo commit `G1` dựa trên `F2`:

```text
P---A---B---C
         \
          F1---F2---G1  teammate branch
```

Sau khi nhánh dùng chung được viết lại thành `F1'---F2'`, `G1` vẫn có parent là `F2`. Git không tự đoán rằng `G1` cần được chuyển sang nền mới. Người tạo `G1` phải đồng bộ lại lịch sử của mình theo hướng dẫn đã thống nhất.

Nếu người thực hiện rebase force-push mà không thông báo, đồng đội có thể tiếp tục commit trên lịch sử cũ, gặp lỗi non-fast-forward hoặc vô tình ghi đè công việc của nhau. Rebase nhánh đã chia sẻ vì thế là thay đổi quy ước lịch sử chung, không chỉ là thao tác cá nhân trong repository local.

## 2. Chọn rebase hay merge để cập nhật nhánh công việc

Hãy chọn cách tích hợp dựa trên việc ai đang sử dụng nhánh và chính sách của nhóm:

| Tình huống | Cách xử lý thường phù hợp |
|---|---|
| Nhánh công việc chỉ do bạn sử dụng, chưa công bố | Rebase thường thuận tiện để cập nhật nền và giữ lịch sử tuyến tính. |
| Nhánh công việc đã push nhưng chưa ai dựa trên đó | Có thể rebase nếu nhóm đồng ý và bạn thông báo trước khi cập nhật remote. |
| Nhiều người cùng commit lên một nhánh công việc | Ưu tiên merge để giữ nguyên commit đã chia sẻ. |
| Đồng đội đã tạo nhánh riêng từ commit trên nhánh công việc | Chỉ rebase khi mọi người thống nhất kế hoạch chuyển các commit phụ thuộc sang lịch sử mới. |
| Nhánh đích là release hoặc nhánh được bảo vệ | Tuân theo quy trình phát hành và chính sách máy chủ; không tự ý viết lại lịch sử nhánh đích. |

Merge giữ lại các commit đã tồn tại và tạo một commit merge (trong trường hợp cần merge commit). Rebase tạo lại các commit được phát lại. Merge thường làm đồ thị lịch sử thể hiện rõ điểm tích hợp; rebase thường tạo đường lịch sử tuyến tính hơn nhưng đòi hỏi người đang dựa vào commit cũ phải đồng bộ lại.

## 3. Trước khi bắt đầu: thống nhất với đồng đội

Với nhánh đã chia sẻ, hãy thống nhất các điểm sau trước khi thực hiện:

1. **Người điều phối:** xác định một người chịu trách nhiệm rebase và cập nhật nhánh remote.
2. **Thời gian tạm dừng:** thông báo thời điểm bắt đầu và kết thúc; trong khoảng đó, các thành viên không push thêm lên nhánh chung.
3. **Phạm vi commit:** xác định nhánh nền mới, commit nào được giữ, commit nào được phát lại và có cần giữ merge commit hay không.
4. **Bản sao công việc:** yêu cầu mỗi thành viên commit công việc riêng hoặc tạo ref dự phòng để có thể quay lại trạng thái trước khi đồng bộ.
5. **Cách cập nhật sau rebase:** thống nhất cách các thành viên đặt lại nhánh local và phát lại commit riêng của họ trên lịch sử mới.

Không bắt đầu viết lại lịch sử khi vẫn có người tiếp tục push mà không biết kế hoạch. Nếu không thể tạm dừng hoặc xác nhận mọi người đã nhận thông tin, hãy dùng merge để tích hợp thay đổi mới.

## 4. Kiểm tra trạng thái và tạo điểm khôi phục

Giả sử nhánh dùng chung là `feature/payment`, remote chia sẻ là `origin`, còn nhánh nền mới là `origin/main`. Trước hết, kiểm tra repository local:

```bash
git status
git branch --show-current
git branch -vv
git log --oneline --graph --decorate --all
```

Nếu working tree hoặc index có thay đổi chưa commit, hãy xử lý chúng trước. Có thể commit thành một commit riêng hoặc stash theo quy trình nhóm. Không chạy rebase khi còn thay đổi chưa được lưu mà bạn chưa hiểu rõ cách Git sẽ xử lý.

Fetch để lấy trạng thái remote mới nhất:

```bash
git fetch origin
```

Xác định nhánh local và nhánh remote có những commit nào riêng:

```bash
git log --oneline --left-right --graph origin/feature/payment...feature/payment
git rev-list --left-right --count origin/feature/payment...feature/payment
```

Trong kết quả `rev-list --left-right --count A...B`, số đầu là commit chỉ có ở `A`, số sau là commit chỉ có ở `B`. Nếu remote có commit mới mà local chưa có, cần hiểu và tích hợp chúng trước khi quyết định viết lại nhánh.

Tạo một nhánh dự phòng local để giữ điểm bắt đầu trước khi tích hợp commit của đồng đội:

```bash
git branch backup/feature-payment-before-sync feature/payment
```

Nhánh dự phòng giữ lại commit hiện tại của `feature/payment` để có thể xem lại nếu bước tích hợp tiếp theo không như dự kiến. Nó chỉ nằm trong local; nếu cần bản sao trên máy chủ, hãy thống nhất tên và cách lưu với nhóm trước khi push nhánh dự phòng.

Ghi lại OID hiện tại của nhánh remote sau lần fetch này:

```bash
git rev-parse origin/feature/payment
```

Lưu OID được in ra để dùng làm điều kiện lease khi cập nhật remote. Điều này giúp phát hiện nếu nhánh remote thay đổi sau thời điểm nhóm đã thống nhất đóng băng push.

## 5. Tích hợp commit mới của đồng đội trước khi rebase

Nếu `origin/feature/payment` có commit mà nhánh local chưa có, đừng bỏ qua chúng. Trước tiên hãy xem các commit ở hai phía:

```bash
# Commit có ở remote nhưng chưa có trong nhánh local
git log --oneline feature/payment..origin/feature/payment

# Commit có ở local nhưng chưa có trong nhánh remote
git log --oneline origin/feature/payment..feature/payment
```

Với nhánh đang được nhiều người dùng, cách ít viết lại lịch sử nhất là tích hợp nhánh remote vào local bằng merge:

```bash
git switch feature/payment
git merge origin/feature/payment
```

Sau khi merge, nhánh local có các commit đã được đồng đội push. Nếu nhóm đã quyết định rebase toàn bộ nhánh chung, hãy tính các commit đó vào phạm vi rebase và thông báo rõ cho mọi người rằng các commit thuộc phạm vi rebase sẽ được tạo lại với OID mới.

Khi đã tích hợp đầy đủ các commit cần giữ và ngay trước khi rebase, tạo thêm một ref dự phòng trỏ đến toàn bộ lịch sử sắp được viết lại:

```bash
git branch backup/feature-payment-before-rebase feature/payment
```

Ref này là điểm so sánh chính sau rebase. Chọn tên khác nếu ref dự phòng đó đã tồn tại.

Không tự ý bỏ commit chỉ có ở remote để làm cho nhánh local trông tuyến tính. Nếu có commit không rõ chủ sở hữu hoặc chưa biết có ai đang dựa vào, dừng lại và xác nhận với nhóm.

## 6. Thực hiện rebase theo kế hoạch đã thống nhất

Khi mọi người đã tạm dừng push, trạng thái đã được sao lưu và phạm vi commit đã rõ, người điều phối có thể rebase:

```bash
git switch feature/payment
git rebase origin/main
```

Git xác định các commit của nhánh hiện tại chưa có trong nền `origin/main`, sau đó phát lại chúng trên nền mới. Nếu nhánh có merge commit và cần giữ cấu trúc merge, hãy đánh giá riêng tùy chọn `--rebase-merges`; rebase thông thường có thể tuyến tính hóa phần lịch sử được phát lại.

Nếu rebase thành công, kiểm tra đồ thị và nội dung:

```bash
git log --oneline --graph --decorate --all
git diff backup/feature-payment-before-rebase...feature/payment
git diff origin/main...feature/payment
```

So sánh với nhánh dự phòng để xem kết quả thay đổi thế nào, đồng thời kiểm tra phần thay đổi của nhánh tính năng so với nền mới. Chạy các kiểm tra và test phù hợp của dự án trước khi cập nhật remote.

## 7. Xử lý xung đột và hủy rebase khi cần

Nếu Git dừng vì xung đột, xem trạng thái:

```bash
git status
```

Mở các tệp được báo, kết hợp nội dung theo ý định của thay đổi, xóa conflict marker và kiểm tra kết quả. Sau khi giải quyết một tệp:

```bash
git add src/payment/PaymentService.java
git rebase --continue
```

Lặp lại cho đến khi rebase hoàn tất. Không đánh dấu tệp đã giải quyết nếu nội dung chưa được kiểm tra.

Nếu nhận ra nền hoặc phạm vi rebase sai, có thể hủy phiên rebase đang diễn ra:

```bash
git rebase --abort
```

Lệnh này đưa nhánh đang rebase về trạng thái trước khi phiên rebase bắt đầu. Nhánh dự phòng đã tạo ở bước trước vẫn là một điểm tham chiếu độc lập để kiểm tra lịch sử cũ.

`git rebase --skip` bỏ qua commit đang gây xung đột. Chỉ dùng khi nhóm xác nhận thay đổi của commit đó không còn cần thiết hoặc đã được áp dụng ở nơi khác; nếu không, bạn có thể vô tình làm mất một phần công việc.

## 8. Cập nhật nhánh remote có kiểm soát

Sau khi rebase, `feature/payment` local có lịch sử mới. Remote `origin/feature/payment` vẫn trỏ đến lịch sử cũ cho đến khi bạn cập nhật nó. Vì lịch sử mới không còn là phần tiếp nối trực tiếp của lịch sử cũ, push thông thường thường bị từ chối.

Với nhánh đã chia sẻ, chỉ force-push sau khi:

- Người điều phối đã thông báo hoàn tất rebase và xác nhận không còn ai push trên nhánh.
- Nhánh local đã được review và các kiểm tra cần thiết đã đạt.
- OID remote được ghi lại trước khi rebase vẫn là giá trị mà bạn dự kiến thay thế.
- Nhóm đã thống nhất rằng việc thay thế lịch sử remote là cần thiết.

Dùng `--force-with-lease` với OID mong đợi đã ghi lại:

```bash
git push --force-with-lease=refs/heads/feature/payment:<expected-remote-oid> origin HEAD:refs/heads/feature/payment
```

Thay `<expected-remote-oid>` bằng OID đầy đủ lấy từ `git rev-parse origin/feature/payment` trước khi rebase. Cú pháp lease tường minh yêu cầu ref trên remote vẫn có đúng OID đó. Nếu một đồng đội đã push commit mới sau lần kiểm tra, remote ref sẽ khác và Git từ chối cập nhật; khi đó hãy fetch, xem commit mới và thống nhất lại thay vì cố đẩy tiếp.

`--force-with-lease` an toàn hơn `--force` vì nó có điều kiện kiểm tra trạng thái remote. Tuy nhiên, nó không thay thế việc phối hợp: nếu bạn ghi lại OID sau khi một commit của đồng đội đã xuất hiện rồi dùng OID mới làm giá trị mong đợi, lease vẫn có thể cho phép ghi đè commit đó. Hãy lưu OID trước giai đoạn đóng băng và kiểm tra với nhóm.

Không dùng lệnh force push chung chung trên nhánh được bảo vệ hoặc nhánh release. Máy chủ có thể chặn thao tác này; hãy làm theo quy trình quản trị repository.

## 9. Hướng dẫn đồng đội đồng bộ sau khi nhánh được viết lại

Sau khi cập nhật remote thành công, thông báo OID mới và thời điểm nhánh đã sẵn sàng. Mỗi đồng đội cần giữ lại commit riêng chưa được tích hợp, rồi chuyển sang lịch sử mới.

Ví dụ một đồng đội có nhánh local `feature/payment` với một vài commit riêng được tạo sau commit cũ `F2`. Họ nên:

```bash
# Kiểm tra và lưu công việc chưa commit trước
git status

# Nếu còn thay đổi chưa commit và muốn cất tạm, lưu cả tệp chưa được theo dõi
git stash push -u -m "before syncing rewritten feature/payment"

# Tạo nhánh dự phòng giữ commit hiện tại của nhánh
git branch backup/feature-payment-local feature/payment

# Lấy lịch sử mới sau khi người điều phối đã cập nhật remote
git fetch origin
```

Sau đó, xác định commit cuối cùng của lịch sử cũ mà các commit riêng của mình dựa trên. Trong ví dụ, đó là `F2`. Tạo một nhánh làm việc mới từ bản sao dự phòng và phát lại các commit nằm sau `F2` lên nhánh remote mới:

```bash
git switch -c feature/payment-rebased backup/feature-payment-local
git rebase --onto origin/feature/payment <old-shared-tip>
```

Thay `<old-shared-tip>` bằng OID của commit cuối cùng trên lịch sử cũ đã được chia sẻ trước rebase. Lệnh sẽ phát lại các commit có trên nhánh hiện tại nhưng không nằm trong lịch sử bắt đầu từ commit đó, đặt chúng lên `origin/feature/payment` mới.

Nếu đã stash thay đổi chưa commit ở bước trước, khôi phục chúng sau khi nhánh mới đã được tạo và kiểm tra:

```bash
git stash pop
```

Nếu có xung đột khi áp dụng stash, xử lý và kiểm tra tệp như một lần tích hợp thay đổi thông thường. Chỉ push công việc đã được kiểm tra lên nhánh đích mà nhóm thống nhất; có thể dùng nhánh mới riêng để mở pull request nếu không được phép cập nhật trực tiếp nhánh chung.

Nếu nhánh local của đồng đội chỉ chứa lịch sử cũ mà không có commit riêng, họ có thể tạo lại nhánh local từ remote sau khi đã lưu mọi thay đổi cần giữ:

```bash
git switch -c feature/payment-fresh origin/feature/payment
```

Chỉ sau khi kiểm tra nhánh mới, nhóm mới quyết định đổi tên hoặc thay thế nhánh local cũ. Không chạy `git reset --hard` trên nhánh đang chứa công việc chưa được lưu. Nhánh dự phòng và OID cũ giúp xác định chính xác phần commit riêng cần phát lại.

Nếu đồng đội đã tạo nhiều nhánh phụ dựa trên lịch sử cũ, từng nhánh phụ cũng cần được xem xét. Với mỗi nhánh, xác định commit nền cũ và các commit riêng, sau đó rebase hoặc cherry-pick theo kế hoạch. Không áp dụng một lệnh reset chung cho mọi người vì cấu trúc công việc của mỗi người có thể khác nhau.

## 10. Quy trình phối hợp mẫu cho cả nhóm

| Giai đoạn | Người điều phối | Các thành viên khác |
|---|---|---|
| Trước rebase | Thông báo lịch, phạm vi và người thực hiện; fetch và ghi lại OID remote | Dừng push; commit hoặc lưu công việc riêng; ghi lại commit nền đang dùng |
| Trong rebase | Tạo backup ref, rebase, xử lý xung đột và kiểm tra kết quả | Không push lên nhánh chung; không tiếp tục phát triển dựa trên ref cũ |
| Cập nhật remote | Kiểm tra OID lease, force-push có điều kiện và xác nhận kết quả | Chờ xác nhận nhánh mới đã sẵn sàng |
| Sau rebase | Thông báo OID mới và commit nền mới | Fetch, backup nhánh local, phát lại commit riêng lên lịch sử mới và kiểm tra |
| Kết thúc | Xác nhận mọi người đã đồng bộ; mở lại quyền push theo quy ước nhóm | Tiếp tục làm việc trên lịch sử mới |

Nếu phát hiện một commit bị thiếu sau rebase, dừng việc push thêm. So sánh nhánh dự phòng, lịch sử cũ và mới để xác định commit bị bỏ sót; sau đó dùng cherry-pick hoặc rebase có kiểm soát để khôi phục. Không xóa backup ref cho đến khi nhóm xác nhận mọi công việc đã được chuyển thành công.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
|---|---|
| Rebase chỉ di chuyển tên nhánh | Rebase phát lại commit và tạo commit mới cho phần lịch sử được viết lại; tên nhánh local sau đó trỏ đến commit mới. |
| Rebase local lập tức thay đổi remote | Chỉ cập nhật local; remote thay đổi sau khi push thành công. |
| `--force-with-lease` bảo đảm không thể ghi đè công việc đồng đội | Nó kiểm tra OID remote theo điều kiện lease; vẫn cần ghi lại OID đúng thời điểm và phối hợp với nhóm. |
| Đồng đội chỉ cần chạy `git pull` sau force-push | Nhánh local của họ có thể vẫn dựa trên commit cũ; cần backup, fetch và phát lại commit riêng theo kế hoạch. |
| Merge và rebase có tác động lịch sử giống nhau | Merge giữ các commit cũ và kết nối lịch sử; rebase tạo commit mới cho phần được phát lại. |
| Có thể rebase nhánh dùng chung bất cứ lúc nào | Chỉ nên làm khi nhóm thống nhất thời gian, phạm vi, người thực hiện và cách đồng bộ lại. |
| `git rebase --skip` là cách bỏ qua xung đột an toàn | Lệnh bỏ qua commit đang phát lại; chỉ dùng khi đã xác nhận thay đổi của commit không cần giữ. |

## 12. Tự kiểm tra

1. **Vì sao rebase một nhánh đã chia sẻ có thể ảnh hưởng đến đồng đội?**
   - Vì các commit được phát lại có OID mới; nhánh hoặc commit của đồng đội có thể vẫn dựa trên lịch sử cũ.
2. **Nếu không thể yêu cầu mọi người tạm dừng push, nên chọn cách nào để tích hợp thay đổi mới?**
   - Thường nên merge để giữ nguyên commit đã chia sẻ.
3. **Vì sao tạo nhánh dự phòng trước khi rebase?**
   - Để giữ ref trỏ đến lịch sử cũ, giúp kiểm tra và khôi phục nếu kết quả không đúng.
4. **`--force-with-lease` kiểm tra điều gì?**
   - Nó chỉ cho phép cập nhật ref nếu giá trị remote vẫn khớp với OID mong đợi đã chỉ định hoặc điều kiện lease đang dùng.
5. **Sau khi nhánh remote được viết lại, đồng đội nên làm gì với commit riêng của họ?**
   - Backup trạng thái local, fetch lịch sử mới, xác định commit nền cũ và phát lại các commit riêng lên nhánh mới.

## Kết luận

Rebase nhánh đã chia sẻ làm thay đổi mã định danh và quan hệ cha-con của các commit được phát lại. Muốn thực hiện an toàn, nhóm cần tạm dừng push, xác định phạm vi, lưu ref dự phòng, ghi lại OID remote, rebase và kiểm tra kết quả, rồi cập nhật remote bằng `--force-with-lease` có điều kiện. Sau đó, từng thành viên fetch lịch sử mới và phát lại commit riêng của mình. Nếu không thể phối hợp đầy đủ, merge thường là cách phù hợp hơn để giữ lịch sử mà mọi người đang cùng sử dụng.
