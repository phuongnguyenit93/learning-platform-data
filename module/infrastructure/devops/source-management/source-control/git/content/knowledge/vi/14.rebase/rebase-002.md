# Khi nào dùng rebase và khi nào giữ nguyên đồ thị bằng merge

Khi một nhánh tính năng được phát triển song song với `main`, hai nhánh có thể cùng tiến lên và tạo thành hai lịch sử phân kỳ. Git cung cấp hai cách tích hợp phổ biến: **merge** kết hợp các lịch sử hiện có, còn **rebase** phát lại các commit của một nhánh trên nền commit mới hơn.

Hai cách có thể tạo ra nội dung working tree giống nhau nhưng đồ thị commit khác nhau. Chọn đúng cách phụ thuộc vào việc nhánh có được người khác sử dụng hay không, nhóm muốn giữ dấu vết tích hợp đến mức nào và chính sách lịch sử của repository.

## 1. Hiểu hai cách tích hợp qua đồ thị commit

Giả sử `main` và `feature/payment` cùng xuất phát từ commit `B`. Sau đó `main` có commit `C`, còn nhánh tính năng có hai commit `D` và `E`:

```text
      D---E  feature/payment
     /
A---B---C    main
```

Hai nhánh đã phân kỳ vì mỗi nhánh có commit mà nhánh kia chưa có.

### Merge: giữ các commit và kết nối hai lịch sử

Nếu đang ở nhánh tính năng và chạy:

```bash
git switch feature/payment
git merge main
```

Git kết hợp hai nhánh bằng một merge commit `M` (nếu không thể fast-forward):

```text
A---B---C-------M  feature/payment
     \         /
      D---E---/
```

Merge commit có hai parent: một parent là đầu nhánh hiện tại trước khi merge (`E`), parent còn lại là đầu nhánh được tích hợp (`C`). Các commit `D`, `E` và `C` vẫn giữ nguyên mã định danh. Đồ thị cho thấy rõ hai lịch sử đã được kết hợp tại thời điểm nào.

Nếu đầu nhánh hiện tại là tổ tiên của nhánh được merge, Git có thể chỉ di chuyển con trỏ branch tiến lên. Cách này gọi là **fast-forward merge** và không tạo merge commit. Muốn luôn ghi lại một merge commit ngay cả khi fast-forward có thể thực hiện, dùng `--no-ff`.

### Rebase: phát lại commit trên nền mới

Thay vì merge `main` vào nhánh tính năng, bạn có thể phát lại các commit của nhánh tính năng trên `main`:

```bash
git switch feature/payment
git rebase main
```

Git lấy các thay đổi của `D` và `E`, rồi tạo các commit mới `D'` và `E'` trên đầu `C`:

```text
A---B---C---D'---E'  feature/payment
```

Lịch sử trở nên tuyến tính. Tuy nhiên, `D'` và `E'` là commit mới, có mã định danh khác `D` và `E`, vì parent của chúng đã thay đổi. Rebase không di chuyển commit cũ; nó tạo các commit thay thế và cập nhật nhánh hiện tại sang chuỗi mới.

## 2. Khác biệt quan trọng giữa merge và rebase

| Tiêu chí | Merge | Rebase |
|---|---|---|
| Cách hoạt động | Kết hợp hai lịch sử bằng merge commit hoặc fast-forward | Phát lại commit của nhánh hiện tại trên một nền mới |
| Mã commit cũ | Được giữ nguyên | Các commit được phát lại có mã mới |
| Đồ thị lịch sử | Có thể giữ các nhánh rẽ và merge commit | Thường tạo lịch sử tuyến tính |
| Dấu vết tích hợp | Merge commit ghi nhận điểm kết hợp hai nhánh | Không có merge commit cho lần phát lại thông thường |
| Xử lý conflict | Giải quyết trong lần merge | Có thể phải giải quyết ở nhiều commit được phát lại |
| Phù hợp | Nhánh chia sẻ, nhánh tích hợp, cần lưu dấu vết merge | Nhánh riêng chưa chia sẻ, muốn cập nhật nền và giữ lịch sử gọn |

Merge không tự động làm lịch sử rối: nếu có thể fast-forward, Git chỉ di chuyển branch. Rebase cũng không tự động làm lịch sử tốt hơn: nếu nhóm cần biết một nhánh đã được tích hợp qua những bước nào, merge commit có thể cung cấp thông tin quan trọng.

## 3. Khi nào nên dùng rebase?

Rebase thường phù hợp trong các tình huống sau:

- **Nhánh tính năng chỉ do bạn quản lý.** Bạn có thể phát lại commit của mình mà không làm thay đổi lịch sử mà đồng đội đang dựa vào.
- **Muốn cập nhật nhánh tính năng trước khi tạo pull request.** Đưa các commit mới từ `main` xuống dưới chuỗi commit tính năng để kiểm tra thay đổi trên nền mới nhất.
- **Nhóm yêu cầu lịch sử tuyến tính.** Sau rebase, nhánh có thể được tích hợp bằng fast-forward nếu `main` chưa tiến thêm.
- **Muốn sắp xếp commit trước khi chia sẻ.** `git rebase -i` cho phép đổi thứ tự, gộp, sửa hoặc bỏ các commit trong phạm vi được chọn.

Ví dụ cập nhật nhánh cá nhân trên `origin/main`:

```bash
git switch feature/payment
git status
git fetch origin
git rebase origin/main
```

Sau khi rebase, kiểm tra lịch sử và nội dung:

```bash
git log --oneline --graph --decorate --all
git diff origin/main...HEAD
```

Nếu nhánh chưa từng được push và kiểm tra đạt yêu cầu, bạn có thể mở pull request hoặc tích hợp theo quy trình của nhóm. Nếu nhánh đã được push nhưng chắc chắn chỉ mình bạn sử dụng, việc cập nhật remote có thể cần force-with-lease theo chính sách nhóm; xem phần về nhánh đã chia sẻ bên dưới.

Rebase cũng hữu ích khi dùng `git pull --rebase` để cập nhật nhánh cá nhân:

```bash
git pull --rebase origin main
```

Lệnh này fetch thay đổi từ `origin` rồi rebase các commit local chưa có trên `origin/main` lên đầu nhánh đó. Hãy chạy khi đang ở nhánh cần cập nhật và hiểu rõ các commit local sẽ được phát lại.

## 4. Khi nào nên dùng merge?

Merge phù hợp khi lịch sử đã được chia sẻ hoặc khi chính bản thân quá trình tích hợp là thông tin cần lưu lại:

- **Nhánh được nhiều người cùng làm việc.** Giữ mã định danh commit hiện có để không làm các clone khác phải xử lý lịch sử bị viết lại.
- **Nhánh release, integration hoặc nhánh dùng chung.** Merge ghi lại thời điểm và hai phía được kết hợp.
- **Cần lưu dấu vết của một pull request hoặc đợt tích hợp.** Merge commit thể hiện điểm hội tụ của nhánh tính năng và nhánh đích.
- **Muốn cập nhật nhánh chia sẻ từ `main` mà không viết lại commit.** Merge `main` vào nhánh hiện tại sẽ giữ nguyên các commit đã có.

Ví dụ đồng bộ nhánh tính năng đã được nhiều người sử dụng:

```bash
git switch feature/payment
git fetch origin
git merge origin/main
```

Nếu hai nhánh phân kỳ, Git tạo merge commit sau khi bạn giải quyết conflict. Các commit mà đồng đội đã tạo trên nhánh vẫn giữ nguyên mã. Sau đó bạn có thể push nhánh cập nhật theo quy trình của nhóm.

Khi tích hợp nhánh tính năng vào `main`, nhóm có thể chọn một trong các chính sách. Nếu repository cho phép fast-forward:

```bash
git switch main
git merge --ff-only feature/payment
```

Nếu nhóm muốn luôn tạo merge commit để ghi lại lần tích hợp:

```bash
git switch main
git merge --no-ff feature/payment
```

Chọn lệnh theo quy ước repository. Không cần dùng `--no-ff` nếu nhóm chủ đích giữ lịch sử tuyến tính; cũng không nên ép fast-forward nếu merge commit là dấu vết cần thiết.

## 5. Quy tắc quan trọng với nhánh đã chia sẻ

Rebase thay đổi mã commit của những commit được phát lại. Nếu bạn rebase một nhánh mà người khác đã checkout hoặc tạo commit dựa trên đó, lịch sử của họ sẽ không còn nối thẳng với lịch sử mới. Họ có thể phải xử lý lại commit, tạo commit trùng hoặc thực hiện thao tác phục hồi phức tạp.

Vì vậy, quy tắc cộng tác an toàn là:

- Rebase nhánh cá nhân khi chưa ai khác dựa trên các commit đó.
- Dùng merge để cập nhật nhánh đã chia sẻ hoặc nhánh mà đồng đội đang sử dụng.
- Không rebase các nhánh ổn định như `main` hoặc `release` đã được công bố, trừ khi nhóm có quy trình viết lại lịch sử rõ ràng và đã phối hợp với mọi người liên quan.

Nếu nhánh cá nhân đã được push và bạn cần cập nhật lại sau rebase, `--force-with-lease` có thể giúp tránh ghi đè một cập nhật remote mà bạn chưa fetch:

```bash
git fetch origin
git push --force-with-lease origin feature/payment
```

Tùy chọn này kiểm tra remote ref vẫn ở trạng thái mà local dự kiến trước khi cập nhật. Nó giảm nguy cơ ghi đè công việc mới trên remote, nhưng không làm cho việc viết lại nhánh chia sẻ trở nên an toàn đối với những người đã dựa trên lịch sử cũ. Chỉ dùng khi nhánh thực sự thuộc quyền quản lý của bạn và nhóm cho phép cập nhật lịch sử.

Tránh dùng `git push --force` như một cách xử lý mặc định. Force push có thể làm mất commit mới mà người khác đã đẩy lên remote.

## 6. Conflict khi merge và khi rebase

Cả merge và rebase đều có thể gặp conflict. Điểm khác nhau là merge kết hợp hai đầu lịch sử trong một thao tác, còn rebase lần lượt phát lại các commit. Nếu nhiều commit được phát lại cùng chạm vào một vùng nội dung, rebase có thể dừng ở nhiều bước khác nhau.

### Giải quyết conflict khi merge

```bash
git switch feature/payment
git merge origin/main
```

Nếu có conflict:

```bash
git status
# Mở file, kết hợp nội dung và xóa các conflict marker
git add <file-da-giai-quyet>
git merge --continue
```

Nếu quyết định không tiếp tục merge:

```bash
git merge --abort
```

### Giải quyết conflict khi rebase

```bash
git switch feature/payment
git rebase origin/main
```

Khi Git dừng ở một commit:

```bash
git status
# Mở file, kết hợp nội dung và xóa các conflict marker
git add <file-da-giai-quyet>
git rebase --continue
```

Nếu muốn bỏ qua commit hiện tại, chỉ dùng `git rebase --skip` khi đã xác nhận thay đổi của commit đó không còn cần thiết. Nếu muốn hủy toàn bộ quá trình rebase đang dở:

```bash
git rebase --abort
```

`--abort` đưa nhánh về trạng thái trước khi bắt đầu rebase. Trước khi bắt đầu merge hoặc rebase, hãy kiểm tra `git status` và lưu các thay đổi chưa commit để tránh trộn công việc dở dang vào thao tác tích hợp.

## 7. Merge commit có sẵn trong nhánh thì sao?

Rebase thông thường phát lại các commit theo tuyến tính và không giữ nguyên các merge commit trung gian của nhánh. Nếu nhánh tính năng đã có một cấu trúc merge riêng và cấu trúc đó có ý nghĩa, hãy cân nhắc giữ nguyên bằng merge hoặc dùng chế độ nâng cao:

```bash
git rebase --rebase-merges origin/main
```

`--rebase-merges` yêu cầu Git cố gắng dựng lại cấu trúc merge khi phát lại lịch sử. Kết quả vẫn là lịch sử được viết lại; merge commit mới có thể có mã khác và các conflict vẫn cần được xử lý. Tùy chọn này không biến rebase thành thao tác bảo toàn nguyên vẹn mọi commit cũ.

Nếu mục tiêu là lưu lại đúng đồ thị tích hợp đã xảy ra và tránh thay mã commit, merge thông thường thường dễ hiểu và ít bất ngờ hơn.

## 8. Cách chọn trong quy trình làm việc thực tế

| Tình huống | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Nhánh tính năng cá nhân, chưa push | Rebase lên `origin/main` | Làm mới nền và giữ lịch sử tuyến tính |
| Nhánh tính năng cá nhân đã push, chưa ai dựa vào | Có thể rebase nếu nhóm cho phép | Cần cập nhật remote có kiểm soát sau khi viết lại lịch sử |
| Nhánh tính năng nhiều người cùng sử dụng | Merge `origin/main` vào nhánh | Giữ mã commit hiện có của mọi người |
| Tích hợp pull request cần lưu dấu vết | Merge commit hoặc chính sách merge của nền tảng | Ghi nhận điểm kết hợp hai lịch sử |
| Repository yêu cầu lịch sử tuyến tính | Rebase nhánh riêng trước khi tích hợp, sau đó fast-forward | Không tạo merge commit không cần thiết |
| Nhánh release đã công bố | Merge theo chính sách release | Giữ lịch sử đã chia sẻ ổn định |

Trước khi quyết định, hãy tự trả lời ba câu hỏi:

1. Có ai khác đã lấy commit từ nhánh này hoặc đang phát triển dựa trên nó chưa?
2. Nhóm có cần giữ lại merge commit để truy vết lần tích hợp không?
3. Repository yêu cầu lịch sử tuyến tính hay cho phép đồ thị có nhánh rẽ?

Nếu nhánh đã được chia sẻ và không có quy trình viết lại lịch sử, merge thường là lựa chọn ít gây gián đoạn hơn. Nếu nhánh còn riêng tư và nhóm muốn lịch sử tuyến tính, rebase thường phù hợp.

## 9. Bài tập thực hành

Tạo repository thử nghiệm với nhánh `main` và `feature/demo`. Tạo một commit trên `main`, sau đó tạo hai commit trên `feature/demo`; cuối cùng quay lại `main` và tạo thêm một commit để hai nhánh phân kỳ.

1. Dùng `git log --oneline --graph --decorate --all` để quan sát đồ thị trước khi tích hợp.
2. Tạo một nhánh thử nghiệm từ `feature/demo`, rồi merge `main` vào nhánh đó. Quan sát merge commit và mã các commit cũ.
3. Tạo một nhánh thử nghiệm khác từ `feature/demo`, rồi rebase nhánh đó lên `main`. So sánh mã commit trước và sau rebase.
4. Thử tạo conflict trong cả hai cách. Ghi lại số lần Git dừng để yêu cầu giải quyết và cách tiếp tục hoặc hủy thao tác.
5. Giải thích cách bạn sẽ chọn merge hay rebase nếu `feature/demo` là nhánh cá nhân, rồi thay đổi câu trả lời nếu nhánh đó được ba thành viên cùng sử dụng.

Bạn hoàn thành bài tập khi có thể đọc đồ thị commit, giải thích vì sao rebase tạo mã commit mới và chọn được chiến lược phù hợp với mức độ chia sẻ của nhánh.
