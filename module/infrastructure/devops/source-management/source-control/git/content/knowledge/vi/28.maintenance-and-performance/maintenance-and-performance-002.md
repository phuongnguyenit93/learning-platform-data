# Thu gom rác bằng `git gc` và thời hạn giữ đối tượng chưa được tham chiếu

Trong quá trình làm việc, Git tạo ra nhiều object để lưu commit, tree và blob. Khi nhánh bị xóa, commit bị viết lại bằng rebase hoặc reset, hay file được thay thế qua nhiều lần commit, một số object có thể không còn được tham chiếu từ nhánh hoặc tag nào. Git không xóa chúng ngay lập tức vì chúng có thể vẫn cần để khôi phục thao tác hoặc vì một tiến trình khác vừa tạo ra chúng. Theo thời gian, các object không còn cần thiết có thể được thu gom để giảm dung lượng và cải thiện hiệu năng repository.

`git gc` (garbage collection) thực hiện các công việc bảo trì như gom object rời thành pack, tối ưu cách lưu trữ, cập nhật một số tham chiếu và dọn object không còn được giữ lại. Thời điểm dọn dẹp phụ thuộc vào reflog, thời hạn prune và cấu hình của repository. Hiểu các mốc thời gian này giúp ta biết khi nào một commit bị mất khỏi nhánh vẫn có thể phục hồi, cũng như tránh xóa dữ liệu quá sớm.

Trong dịch vụ quản lý mã nguồn Git, bảo trì repository là một phần của việc giữ lịch sử ổn định và truy xuất nhanh. Hãy xem `git gc` như một thao tác quản trị object database có quy tắc giữ dữ liệu, không phải lệnh xóa file rác tùy tiện.

## 1. Object nào được Git lưu trữ?

Git lưu nội dung và lịch sử dưới dạng các object trong object database. Bốn loại object cơ bản là:

| Loại object | Nội dung |
| --- | --- |
| Blob | Nội dung của file, không chứa tên file hay đường dẫn |
| Tree | Cấu trúc thư mục, tên file và tham chiếu tới blob hoặc tree con |
| Commit | Snapshot được ghi nhận, parent commit, tác giả, người commit và thông điệp |
| Tag object | Metadata của annotated tag, có thể chứa tagger, thông điệp và chữ ký |

Một commit trỏ tới tree của nó và có thể trỏ tới một hoặc nhiều commit cha. Tree trỏ tới các blob và tree con. Các ref như branch, tag và `HEAD` giúp Git tìm ra những commit cần thiết. Từ các commit đó, Git đi theo quan hệ parent và tree để xác định những object còn được sử dụng.

Ví dụ đơn giản:

```text
refs/heads/main
       |
       v
    Commit C3
       |
       v
      Tree
      /  \
   Blob  Tree
           |
          Blob
```

Khi một branch bị xóa, commit đầu nhánh có thể không còn được tham chiếu bởi ref đó. Tuy nhiên, commit vẫn có thể được giữ bởi branch khác, tag, reflog hoặc một ref khác. Một object chỉ trở thành ứng viên thu gom khi không còn đường tham chiếu được Git xem là root giữ nó.

## 2. Reachable, unreachable và dangling object

Để hiểu garbage collection, cần phân biệt ba khái niệm:

- **Reachable object:** object có thể đi tới từ một root mà Git đang xét, chẳng hạn ref, index hoặc reflog. Object này còn được sử dụng và không phải ứng viên xóa thông thường.
- **Unreachable object:** object không còn reachable từ các root đang xét. Ví dụ commit cũ sau khi reset nhánh hoặc commit trên branch đã bị xóa.
- **Dangling object:** object unreachable và không được object khác tham chiếu tới theo cách tạo thành chuỗi còn dùng. Một dangling commit thường là đầu của một phần lịch sử không còn được gắn với ref.

Một commit có thể unreachable từ branch nhưng vẫn có thể tìm thấy qua reflog. Vì vậy, “không còn thấy trong `git log --all`” không đồng nghĩa object đã bị xóa. `git log --all` chủ yếu duyệt từ các ref hiện có; reflog là một nguồn lịch sử riêng.

Ví dụ sau khi reset:

```text
Trước reset:

A --- B --- C  main
              ^ HEAD

Sau `git reset --hard B`:

A --- B  main
     \
      C  (không còn được branch main trỏ tới)
```

Commit `C` có thể vẫn còn trong reflog của `main` hoặc `HEAD`. Nếu reflog còn giữ mục đó, ta thường có thể tạo branch mới trỏ tới `C`. Chỉ sau khi các cơ chế giữ lại hết hiệu lực và object vượt qua thời hạn prune, Git mới có thể thu gom object đó.

## 3. `git gc` thực hiện những công việc nào?

Lệnh cơ bản:

```bash
git gc
```

Git thực hiện các công việc bảo trì phù hợp với repository và phiên bản đang dùng. Những công việc thường gặp gồm:

- **Repack object:** gom nhiều object rời hoặc pack nhỏ thành pack lớn hơn, giảm overhead và giúp truy xuất hiệu quả hơn.
- **Prune object không còn được giữ:** loại object unreachable đã quá thời hạn an toàn.
- **Expire reflog:** xóa các mục reflog đã quá thời hạn theo cấu hình.
- **Pack refs:** có thể gom các ref phù hợp vào file packed-refs.
- **Dọn dữ liệu phụ trợ:** thực hiện một số bước bảo trì như dọn thông tin rerere hoặc worktree cũ tùy cấu hình và phiên bản.

Không nên giả định mọi phiên bản Git đều thực hiện chính xác cùng một chuỗi lệnh nội bộ. Mục tiêu của `git gc` là bảo trì object database và dữ liệu liên quan theo chính sách của repository.

### Object rời và packfile

Khi Git tạo object, object có thể ban đầu được lưu thành file riêng trong `.git/objects`. Khi số lượng object rời tăng, Git có thể gom chúng vào packfile trong `.git/objects/pack`.

Packfile lưu nhiều object cùng nhau và có thể dùng delta compression để lưu phần khác biệt giữa các object tương tự. Điều này thường tiết kiệm dung lượng, đặc biệt với các phiên bản file gần nhau.

Kiểm tra số lượng object và dung lượng:

```bash
git count-objects -vH
```

Một số trường thông dụng:

| Trường | Ý nghĩa |
| --- | --- |
| `count` | Số object rời |
| `size` | Dung lượng object rời, tính theo KiB |
| `in-pack` | Số object trong packfile |
| `packs` | Số packfile |
| `size-pack` | Tổng dung lượng packfile, tính theo KiB |
| `prune-packable` | Object rời đã có bản tương ứng trong pack và có thể được dọn |
| `garbage` | Số file không hợp lệ hoặc không nhận diện trong object database |

Sau khi chạy GC, số object rời hoặc số packfile có thể giảm, trong khi tổng số object được giữ lại vẫn tương tự. GC không nhất thiết làm repository nhỏ đi đáng kể nếu hầu hết object vẫn đang được tham chiếu.

## 4. Reflog giữ lại lịch sử đã rời khỏi branch

Reflog ghi lại những lần một ref thay đổi vị trí. Ví dụ, khi commit mới, checkout, reset, rebase hoặc cập nhật branch, Git có thể ghi lại vị trí cũ và mới trong reflog.

Xem reflog của `HEAD`:

```bash
git reflog
```

Xem reflog của một branch:

```bash
git reflog show main
```

Xem các mục của mọi ref:

```bash
git reflog show --all
```

Reflog hữu ích khi cần phục hồi commit sau một thao tác như `reset --hard`, rebase hoặc xóa branch. Ví dụ, nếu vừa reset nhầm, có thể tìm commit trước reset trong reflog rồi tạo branch cứu hộ:

```bash
git reflog show --date=local main
git branch rescue/before-reset <commit-id>
```

Branch cứu hộ tạo một ref mới để giữ commit và toàn bộ lịch sử reachable từ commit đó. Hãy kiểm tra commit bằng `git show <commit-id>` trước khi tạo branch nếu chưa chắc đó là vị trí cần phục hồi.

### Reflog chỉ có tính cục bộ

Reflog được lưu trong repository local và không được push lên remote như commit hay branch. Một thành viên khác có thể không có cùng reflog. Khi cần bảo vệ một commit quan trọng, hãy tạo branch hoặc tag rõ ràng và push theo quy trình nhóm thay vì dựa vào reflog như một bản sao lưu dùng chung.

## 5. Thời hạn giữ reflog

Git có hai cấu hình chính điều khiển thời gian giữ các mục reflog:

| Cấu hình | Giá trị mặc định thường gặp | Ý nghĩa |
| --- | --- | --- |
| `gc.reflogExpire` | `90 days` | Thời hạn giữ các mục reflog nói chung |
| `gc.reflogExpireUnreachable` | `30 days` | Thời hạn giữ mục reflog dẫn tới commit không còn reachable từ tip hiện tại của ref |

Các giá trị trên là mặc định phổ biến của Git, có thể bị thay đổi bởi cấu hình system, global, local hoặc cấu hình theo từng ref. Mục reflog đang trỏ tới lịch sử còn reachable có thể được giữ lâu hơn mục dẫn tới commit đã rời khỏi tip hiện tại.

Xem cấu hình:

```bash
git config --show-origin --get gc.reflogExpire
git config --show-origin --get gc.reflogExpireUnreachable
```

Nếu lệnh không trả kết quả, Git có thể đang dùng giá trị mặc định. Có thể cấu hình riêng cho repository:

```bash
git config --local gc.reflogExpire 90.days.ago
git config --local gc.reflogExpireUnreachable 30.days.ago
```

Hoặc đặt chính sách cho tài khoản:

```bash
git config --global gc.reflogExpire 90.days.ago
git config --global gc.reflogExpireUnreachable 30.days.ago
```

Git cũng hỗ trợ cấu hình theo ref bằng dạng `gc.<pattern>.reflogExpire` và `gc.<pattern>.reflogExpireUnreachable`. Điều này hữu ích nếu nhóm muốn giữ reflog của một số ref lâu hơn. Cần xem tài liệu Git của phiên bản đang dùng để chọn pattern chính xác.

### Điều chỉnh thời hạn cần cân nhắc

Tăng thời hạn reflog giúp có thêm thời gian phục hồi commit cũ, nhưng cũng giữ thêm object và có thể làm repository tốn dung lượng hơn. Giảm thời hạn giúp dọn nhanh hơn nhưng rút ngắn cửa sổ phục hồi. Không nên giảm thời hạn chỉ để giảm dung lượng khi chưa có chính sách backup và khôi phục thay thế.

## 6. Thời hạn prune object không còn được tham chiếu

`gc.pruneExpire` điều khiển thời điểm object unreachable đủ điều kiện được prune. Mặc định thường là `2 weeks ago` (hai tuần trước). Khoảng chờ này là một vùng an toàn để tránh xóa object vừa được tạo nhưng chưa được tham chiếu do một tiến trình Git khác đang thực hiện thao tác.

Xem cấu hình:

```bash
git config --show-origin --get gc.pruneExpire
```

Có thể đặt riêng trong repository:

```bash
git config --local gc.pruneExpire 2.weeks.ago
```

Hoặc giữ object unreachable lâu hơn:

```bash
git config --local gc.pruneExpire 30.days.ago
```

Thời hạn prune và thời hạn reflog là hai cơ chế khác nhau:

- Reflog giữ lại các vị trí ref cũ để ta có thể tìm lại commit.
- Prune expiry quy định object unreachable được giữ thêm bao lâu trước khi đủ điều kiện xóa.

Ví dụ, một commit vừa bị loại khỏi branch vẫn có thể được giữ bởi reflog. Khi mục reflog hết hạn, commit trở thành ứng viên thu gom; nếu object vẫn còn trong thời hạn prune, Git tiếp tục giữ nó. Khi không còn root giữ và đã qua thời hạn prune, object có thể bị loại bỏ trong lần GC phù hợp.

Không nên hiểu hai mốc này như một bộ đếm duy nhất bắt đầu từ lúc xóa branch. Reflog và object có thời điểm, trạng thái reachable và quy tắc giữ riêng; kết quả thực tế còn phụ thuộc packfile, cruft pack và phiên bản Git.

## 7. Cruft pack và object unreachable trong Git hiện đại

Trong các phiên bản Git mới, object unreachable có thể được gom vào **cruft pack** thay vì chỉ nằm dưới dạng object rời hoặc bị loại ngay. Cruft pack là packfile chứa object không còn reachable, đi kèm metadata về thời điểm object được đưa vào pack để Git có thể áp dụng chính sách prune sau này.

Điều này giúp Git quản lý số lượng lớn object unreachable hiệu quả hơn, đồng thời vẫn giữ chúng trong thời hạn an toàn. Vì vậy, không phải lúc nào ta cũng nhìn thấy object unreachable như file riêng trong `.git/objects`.

Một số cấu hình liên quan:

```bash
git config --show-origin --get gc.cruftPacks
git config --show-origin --get gc.maxCruftSize
```

`gc.cruftPacks` điều khiển việc dùng cruft pack trong các phiên bản hỗ trợ. `gc.maxCruftSize` có thể giới hạn kích thước cruft pack. Cấu hình khả dụng và giá trị mặc định tùy phiên bản Git; không nên chỉnh chúng nếu chưa hiểu cách repository đang lưu pack.

Cruft pack không phải bản backup lâu dài. Object vẫn có thể bị loại khi hết hạn prune và được GC xử lý. Nếu commit cần giữ, hãy tạo branch hoặc tag tham chiếu tới nó.

## 8. Quy trình chạy `git gc` thông thường

Trước khi chạy GC thủ công, kiểm tra repository:

```bash
git status -sb
git count-objects -vH
git reflog --all --date=relative
```

Nếu đang có thao tác rebase, cherry-pick, merge hoặc một tiến trình Git khác chạy, hãy đợi thao tác hoàn tất. Không chạy các lệnh dọn dẹp mạnh trong lúc một tiến trình khác đang ghi object database.

Chạy GC thông thường:

```bash
git gc
```

Sau đó kiểm tra:

```bash
git count-objects -vH
git status -sb
git fsck --full
```

`git fsck --full` kiểm tra tính toàn vẹn của object database. Nó có thể báo object unreachable hoặc dangling nếu repository còn các object không được tham chiếu; những thông báo này không nhất thiết là lỗi hỏng dữ liệu. Cần đọc loại thông báo và đánh giá xem object có cần phục hồi không.

### Chạy tự động

Nhiều lệnh Git có thể kích hoạt `git gc --auto` khi số object rời hoặc packfile vượt ngưỡng cấu hình. Cơ chế này giúp repository được bảo trì dần mà người dùng không cần chạy GC thủ công sau mỗi commit.

Kiểm tra các ngưỡng:

```bash
git config --show-origin --get gc.auto
git config --show-origin --get gc.autoPackLimit
```

Trong nhiều phiên bản Git, `gc.auto` mặc định kích hoạt khi số object rời vượt khoảng 6.700; `gc.autoPackLimit` mặc định kích hoạt khi số packfile vượt khoảng 50. Đây là ngưỡng mặc định phổ biến, có thể khác theo phiên bản hoặc cấu hình. Đặt `gc.auto` bằng `0` sẽ tắt kích hoạt GC tự động từ ngưỡng object rời; việc này không đồng nghĩa tắt mọi hoạt động bảo trì khác.

## 9. Các tùy chọn prune và aggressive

### Chỉ định thời điểm prune

```bash
git gc --prune=2.weeks.ago
```

Lệnh chỉ prune object đủ điều kiện theo mốc thời gian đã chỉ định. Đây là cách tường minh để dùng grace period mặc định phổ biến.

Có thể giữ object unreachable trong lần GC này:

```bash
git gc --prune=never
```

Tùy chọn `never` hữu ích khi cần repack nhưng chưa muốn prune object. Kiểm tra phiên bản Git và tài liệu lệnh nếu môi trường cũ không hỗ trợ cú pháp này.

### Vì sao cần cẩn thận với `--prune=now`?

```bash
git gc --prune=now
```

`now` bỏ qua khoảng chờ an toàn thông thường. Nếu một tiến trình khác đang ghi object nhưng chưa kịp tạo ref tới object đó, GC có thể xóa object vừa được tạo và gây hỏng thao tác đang diễn ra. Chỉ dùng khi đã bảo đảm không có tiến trình Git nào khác truy cập repository và có lý do rõ ràng cần dọn ngay. Trong bảo trì thường ngày, giữ grace period mặc định an toàn hơn.

### `git gc --aggressive`

```bash
git gc --aggressive
```

Tùy chọn này yêu cầu repack tốn công hơn để tìm cách nén delta tốt hơn. Nó có thể mất nhiều thời gian và CPU, nhưng không bảo đảm repository luôn nhỏ hơn đáng kể. Không nên chạy định kỳ theo thói quen hoặc dùng như cách sửa mọi vấn đề hiệu năng. Hãy đo dung lượng, thời gian truy xuất và số lượng pack trước; chỉ thử trên bản sao hoặc trong cửa sổ bảo trì khi có bằng chứng cần tối ưu sâu.

## 10. Tìm object chưa được tham chiếu trước khi GC

Nếu vừa xóa branch, reset nhầm hoặc rebase sai, hãy tìm và bảo vệ commit trước khi chạy GC mạnh.

### Bước 1: Kiểm tra reflog

```bash
git reflog --all --date=iso
```

Tìm mã commit trước thao tác nhầm. Xem commit:

```bash
git show --stat <commit-id>
```

Nếu đúng là công việc cần giữ, tạo branch cứu hộ:

```bash
git branch rescue/recovered-work <commit-id>
```

### Bước 2: Tìm object unreachable không còn trong reflog

Nếu reflog không giúp được, có thể kiểm tra object database:

```bash
git fsck --full --no-reflogs --unreachable
```

`--no-reflogs` yêu cầu `fsck` không dùng reflog làm root khi tính reachability. Lệnh có thể liệt kê commit, tree hoặc blob không reachable từ các ref còn lại. Kết quả có thể nhiều; tập trung vào object loại `commit` trước nếu đang tìm lịch sử branch bị mất.

Xem commit nghi ngờ:

```bash
git show --stat <commit-id>
git log --oneline --decorate <commit-id> -10
```

Nếu đúng commit cần giữ, tạo ref:

```bash
git branch rescue/from-unreachable <commit-id>
```

Khi branch được tạo, commit và các object reachable từ nó được giữ lại qua ref mới.

### Bước 3: Xem object dangling

```bash
git fsck --full --dangling
```

Lệnh tập trung báo các object dangling. Một dangling commit có thể là tip của chuỗi commit đã bị bỏ khỏi branch. Dùng `git show` để xem nội dung trước khi quyết định giữ hoặc bỏ.

Không tạo branch cho mọi object được liệt kê một cách máy móc. Tree và blob có thể chỉ là thành phần của một snapshot cũ; hãy tìm commit gốc phù hợp và kiểm tra nội dung.

## 11. Khi nào một object thực sự bị xóa?

Hãy xét một commit `C` vừa bị loại khỏi branch:

1. **Branch/ref di chuyển hoặc bị xóa:** `C` có thể không còn reachable từ ref đó.
2. **Reflog còn ghi vị trí cũ:** `C` vẫn có thể được tìm thấy và được giữ lại theo chính sách reflog.
3. **Mục reflog hết hạn:** nếu không còn ref hoặc root nào khác giữ `C`, object trở thành unreachable theo góc nhìn GC.
4. **Hết thời hạn prune:** object đủ điều kiện bị loại khi GC thực hiện prune; nếu đang nằm trong cruft pack, Git dùng metadata expiration tương ứng.
5. **GC hoàn tất:** object có thể không còn trong object database local và không thể phục hồi bằng reflog hoặc `fsck` tại repository đó.

```text
Commit C được branch tham chiếu
          |
          v
Branch bị reset/xóa
          |
          v
Reflog còn giữ vị trí cũ
          |
          v
Reflog entry hết hạn
          |
          v
Object unreachable, còn trong prune grace period
          |
          v
GC prune sau khi hết hạn
          |
          v
Object bị loại khỏi object database local
```

Đây là mô hình khái niệm. Một object có thể được giữ bởi branch khác, tag, ref ẩn, index, alternate object database hoặc bản sao repository khác; vì thế không thể kết luận object sẽ bị xóa chỉ từ việc branch ban đầu biến mất.

## 12. Phục hồi commit trước khi object bị prune

Ví dụ vừa reset nhầm branch:

```bash
git reset --hard HEAD~2
```

Nếu cần tìm tip cũ:

```bash
git reflog --date=local
```

Giả sử reflog cho thấy `HEAD@{1}` là vị trí trước reset. Tạo branch cứu hộ:

```bash
git branch rescue/before-reset HEAD@{1}
```

Sau đó xác nhận:

```bash
git log --oneline --decorate rescue/before-reset -10
git show --stat rescue/before-reset
```

Nếu commit đã không còn trong reflog nhưng object vẫn tồn tại:

```bash
git fsck --full --no-reflogs --unreachable
```

Tìm commit phù hợp rồi tạo branch theo mã hash. Hãy làm việc trên bản sao hoặc tạo ref cứu hộ trước khi chạy thêm GC để tránh mất cơ hội phục hồi.

Nếu object đã bị prune khỏi repository local, `reflog` và `fsck` không thể tạo lại nội dung đã bị xóa. Khi đó, tìm trong clone của đồng đội, remote còn giữ branch/tag, backup hoặc bản mirror. Reflog của một clone khác có thể vẫn giữ commit mà clone hiện tại đã mất.

## 13. Thận trọng với reflog expire và prune thủ công

Có thể expire reflog thủ công:

```bash
git reflog expire --expire=90.days.ago --expire-unreachable=30.days.ago --all
```

Lệnh này loại các mục reflog vượt quá thời hạn được chỉ định. Khi mục reflog bị xóa, cơ hội phục hồi commit chỉ còn được giữ bởi reflog đó cũng mất đi. Nếu sau đó GC prune object, commit có thể biến mất khỏi repository local.

Có thể kết hợp expire và GC:

```bash
git reflog expire --expire=90.days.ago --expire-unreachable=30.days.ago --all
git gc --prune=2.weeks.ago
```

Đây là thao tác bảo trì có ảnh hưởng tới khả năng phục hồi. Trước khi chạy, cần kiểm tra reflog và bảo đảm không có commit quan trọng chỉ được giữ ở đó. Không dùng lệnh expire rút ngắn thời hạn trong lúc đang điều tra một sự cố hoặc trước khi xác nhận các nhánh đã được backup.

`git prune` là lệnh mức thấp hơn, thường không cần chạy riêng trong quy trình thông thường. Ưu tiên `git gc` vì GC phối hợp repack, reflog và prune theo chính sách phù hợp.

## 14. Các cấu hình GC thường dùng

| Cấu hình | Vai trò | Giá trị mặc định phổ biến |
| --- | --- | --- |
| `gc.auto` | Ngưỡng số object rời kích hoạt GC tự động | `6700` |
| `gc.autoPackLimit` | Ngưỡng số packfile kích hoạt repack tự động | `50` |
| `gc.pruneExpire` | Thời hạn giữ object unreachable trước khi prune | `2 weeks ago` |
| `gc.reflogExpire` | Thời hạn giữ reflog nói chung | `90 days` |
| `gc.reflogExpireUnreachable` | Thời hạn giữ reflog cho entry unreachable | `30 days` |
| `gc.cruftPacks` | Cho phép dùng cruft pack để lưu object unreachable | Phụ thuộc phiên bản/cấu hình |

Xem cấu hình đang có và nguồn:

```bash
git config --show-origin --get-regexp '^gc\.'
```

Đặt cấu hình theo repository:

```bash
git config --local gc.pruneExpire 30.days.ago
git config --local gc.reflogExpire 180.days.ago
git config --local gc.reflogExpireUnreachable 60.days.ago
```

Ví dụ này kéo dài cửa sổ phục hồi. Đổi lại, repository có thể giữ thêm object và reflog. Chọn thời hạn theo yêu cầu audit, khả năng backup, dung lượng lưu trữ và chính sách nội bộ.

## 15. Quy trình bảo trì an toàn

Một quy trình bảo trì repository có thể gồm:

### Trước khi GC

1. Kiểm tra `git status -sb` và bảo đảm không có thao tác Git đang dở.
2. Kiểm tra các branch, tag và remote-tracking refs quan trọng.
3. Xem reflog nếu gần đây có reset, rebase hoặc xóa branch.
4. Tạo branch/tag cứu hộ cho commit cần giữ.
5. Ghi nhận dung lượng bằng `git count-objects -vH`.
6. Xác nhận không có tiến trình Git khác đang ghi repository, nhất là khi định dùng prune mạnh.

### Trong khi GC

Chạy lệnh phù hợp với mục tiêu:

```bash
git gc
```

Chỉ chỉ định thời hạn prune khác mặc định khi có chính sách rõ ràng. Tránh `--prune=now` trong môi trường đang có tiến trình Git đồng thời. Không chạy `--aggressive` nếu chưa có số liệu cho thấy cần tối ưu sâu.

### Sau khi GC

```bash
git count-objects -vH
git fsck --full
git status -sb
```

So sánh số object và dung lượng trước/sau. Nếu `fsck` báo lỗi missing hoặc corrupt object, dừng các thao tác ghi tiếp theo và kiểm tra backup, packfile, filesystem và tiến trình đã chạy. Các cảnh báo unreachable/dangling có thể là dữ liệu cũ chưa được thu gom, không đồng nghĩa repository bị hỏng.

## 16. Lỗi và tình huống thường gặp

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| Repository không nhỏ đi sau GC | Phần lớn object vẫn reachable hoặc dữ liệu đã được nén tốt | Xem `git count-objects -vH`, xác định pack và object lớn trước khi tối ưu |
| Commit không còn trong `git log --all` | Branch/ref đã bị xóa hoặc di chuyển | Kiểm tra `git reflog --all` trước khi kết luận commit mất |
| `git fsck` báo unreachable/dangling | Có object không còn được ref hiện tại giữ | Kiểm tra commit; tạo branch cứu hộ nếu cần |
| Không tìm được commit trong reflog | Reflog đã hết hạn hoặc commit đến từ clone khác | Thử `git fsck`, tìm trong clone/remote/backup khác |
| Sau GC commit không thể phục hồi | Object đã bị prune và không còn bản sao | Tìm backup hoặc clone khác; không thể khôi phục chỉ bằng reflog local |
| GC chạy lâu | Repository có nhiều object, pack lớn hoặc đang repack | Để thao tác hoàn tất, kiểm tra dung lượng và cân nhắc bảo trì theo lịch |
| GC làm mất object mới tạo | Prune quá sớm trong lúc tiến trình khác ghi repository | Tránh `--prune=now`, dùng grace period và không chạy đồng thời |
| Reflog quá lớn hoặc giữ lịch sử quá lâu | Thời hạn expire được đặt dài | Đánh giá nhu cầu phục hồi trước khi rút ngắn thời hạn |

## 17. Thực hành

Thực hiện trên repository thử nghiệm để quan sát vòng đời của object:

1. Tạo một branch `feature/gc-lab` và thực hiện vài commit.
2. Ghi lại mã commit đầu nhánh bằng `git log --oneline`.
3. Xóa branch thử nghiệm hoặc reset về commit trước đó.
4. Dùng `git reflog --all` để tìm lại commit đã rời khỏi branch.
5. Tạo branch `rescue/gc-lab` trỏ tới commit cần giữ.
6. Chạy `git count-objects -vH` để ghi nhận số object và dung lượng.
7. Chạy `git gc` rồi kiểm tra lại bằng `git count-objects -vH` và `git fsck --full`.
8. Trong một repository thử nghiệm khác, tạo commit unreachable, dùng `git fsck --full --no-reflogs --unreachable` để quan sát object.
9. Xem cấu hình `gc.reflogExpire`, `gc.reflogExpireUnreachable` và `gc.pruneExpire`.
10. Giải thích vì sao không nên dùng `git gc --prune=now` khi có tiến trình Git khác đang chạy.

Không thử nghiệm expire hoặc prune mạnh trên repository đang chứa công việc thật. Nếu muốn quan sát object bị thu gom, hãy dùng một repository riêng có thể xóa và tạo lại.

## 18. Tự kiểm tra kiến thức

1. Git object database lưu những loại object cơ bản nào?
2. Reachable, unreachable và dangling object khác nhau ra sao?
3. `git gc` thường thực hiện những công việc bảo trì nào?
4. Vì sao một commit đã rời khỏi branch vẫn có thể phục hồi bằng reflog?
5. `gc.reflogExpire` và `gc.reflogExpireUnreachable` khác nhau thế nào?
6. `gc.pruneExpire` điều khiển thời điểm nào?
7. Vì sao thời hạn reflog và thời hạn prune là hai cơ chế riêng?
8. Cruft pack giúp quản lý object unreachable như thế nào?
9. `git gc --prune=now` có rủi ro gì khi repository đang được ghi đồng thời?
10. Nếu commit đã bị prune khỏi local, có thể tìm bản phục hồi ở đâu?

## Kết luận

`git gc` bảo trì object database bằng cách repack, expire reflog và prune object không còn được giữ theo chính sách. Reflog thường giữ lịch sử ref cũ trong khoảng 90 ngày, các entry dẫn tới commit unreachable thường có thời hạn ngắn hơn khoảng 30 ngày, còn object unreachable có grace period prune mặc định khoảng hai tuần; các mốc này có thể được cấu hình và phụ thuộc phiên bản. Khi cần phục hồi, hãy kiểm tra reflog và `git fsck`, rồi tạo branch cứu hộ trước khi GC loại object. Giữ grace period mặc định, tránh prune ngay khi có tiến trình đồng thời và chỉ rút ngắn thời hạn sau khi đã có backup cùng chính sách phục hồi phù hợp.
