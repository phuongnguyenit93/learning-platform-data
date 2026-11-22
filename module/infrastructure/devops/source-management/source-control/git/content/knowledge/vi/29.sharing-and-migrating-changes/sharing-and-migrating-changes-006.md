# Nhập lịch sử từ kho Git khác và lựa chọn giữ quan hệ lịch sử

Khi hợp nhất hai dự án Git, bạn cần quyết định muốn đưa toàn bộ lịch sử của kho nguồn vào kho đích, chỉ lấy một phần thay đổi hay chỉ sao chép trạng thái file hiện tại. Quyết định này ảnh hưởng tới khả năng truy vết tác giả, xem lại commit cũ, merge các thay đổi tiếp theo và bảo trì dependency. Git có thể kết nối hai lịch sử vốn không có commit chung bằng `git merge --allow-unrelated-histories`; nếu muốn đưa một dự án vào thư mục con, `git subtree` hoặc viết lại đường dẫn lịch sử bằng công cụ chuyên dụng có thể phù hợp hơn.

## 1. Hai repository có thể có lịch sử độc lập

Mỗi repository Git có đồ thị commit riêng. Khi hai repository được tạo độc lập, commit gốc của chúng không có tổ tiên chung.

Ví dụ:

```text
Repository đích:                 Repository nguồn:

A---B---C  main                   X---Y---Z  main
```

`C` và `Z` không có quan hệ cha-con, cũng không có commit tổ tiên chung. Nếu thêm repository nguồn làm remote rồi merge như bình thường, Git có thể từ chối vì hai lịch sử không liên quan.

Điều này thường xảy ra khi:

- Một dự án mới được tạo từ repository riêng rồi cần nhập vào monorepo.
- Hai nhóm phát triển độc lập rồi quyết định hợp nhất sản phẩm.
- Một repository cũ cần được đưa vào repository mới nhưng phải giữ khả năng truy vết commit.
- Repository đích đã có README hoặc commit khởi tạo riêng, trong khi repository nguồn cũng có lịch sử riêng.

Trước khi nhập, hãy xác định mục tiêu: hợp nhất lịch sử thành một đồ thị, giữ dự án nguồn như một thành phần độc lập trong thư mục con, lấy một số commit chọn lọc hay chỉ lấy snapshot hiện tại. Không có một cách duy nhất phù hợp với mọi trường hợp.

## 2. Kiểm tra hai lịch sử trước khi nhập

Trước tiên, kiểm tra repository đích và trạng thái làm việc:

```bash
git status -sb
git log --oneline --graph --decorate --all
```

Working tree nên sạch trước thao tác merge. Nếu có thay đổi chưa commit, hãy commit hoặc stash theo quy trình phù hợp để tránh trộn công việc đang dở vào quá trình nhập lịch sử.

Thêm repository nguồn làm remote và tải refs:

```bash
git remote add legacy https://git.example.com/team/legacy-app.git
git fetch legacy
```

`git fetch` tải object và cập nhật remote-tracking refs như `legacy/main`; nó không tự thay đổi branch hiện tại hoặc working tree. Xem các branch nguồn:

```bash
git branch --remotes
git log --oneline --graph --decorate legacy/main
```

Kiểm tra hai tip có tổ tiên chung hay không:

```bash
git merge-base main legacy/main
```

Nếu lệnh trả về một commit ID, hai lịch sử có tổ tiên chung và có thể tích hợp bằng merge thông thường. Nếu không có kết quả và trả mã thoát khác `0`, có thể hai lịch sử không liên quan; hãy xác nhận đúng branch và repository trước khi chọn cách nhập.

Có thể kiểm tra rõ ràng hơn bằng:

```bash
git merge-base --is-ancestor main legacy/main
git merge-base --is-ancestor legacy/main main
```

Hai lệnh trên kiểm tra quan hệ tổ tiên theo từng chiều. Kết quả `0` nghĩa là commit thứ nhất là tổ tiên của commit thứ hai; mã thoát khác `0` nghĩa là không thỏa quan hệ đó. Nếu cả hai đều không phải tổ tiên của nhau nhưng `git merge-base main legacy/main` có kết quả, hai nhánh đã phân kỳ nhưng vẫn có lịch sử chung. Nếu không có merge base, lịch sử có thể độc lập.

## 3. Bảo toàn trạng thái trước khi nhập

Trước thao tác có thể tạo nhiều thay đổi, tạo một branch đánh dấu trạng thái hiện tại:

```bash
git switch main
git branch backup/main-before-import
```

Branch backup giữ tip hiện tại để có thể so sánh hoặc quay lại nếu quá trình nhập cần làm lại. Nếu repository có tag release hoặc refs quan trọng, ghi nhận chúng theo chính sách sao lưu của nhóm.

Kiểm tra remote và URL nguồn:

```bash
git remote -v
git config --get-regexp '^remote\.'
```

Xác minh URL, quyền truy cập và commit nguồn với người duy trì repository. Khi nhập mã từ nguồn chưa được xác minh, xem xét `.gitattributes`, `.gitmodules`, `.lfsconfig`, hook/bootstrap script và dependency trước khi checkout hoặc chạy build.

## 4. Kết nối hai lịch sử bằng `--allow-unrelated-histories`

Nếu muốn giữ nguyên lịch sử của cả repository đích và nguồn trong cùng một đồ thị, dùng:

```bash
git switch main
git merge --allow-unrelated-histories legacy/main
```

Tùy chọn `--allow-unrelated-histories` cho phép Git tạo merge giữa hai tip không có tổ tiên chung. Git không viết lại các commit cũ của hai bên; nó tạo một merge commit mới có hai parent:

```text
      A---B---C---------M  main
                         /
X---Y---Z---------------
```

Trong sơ đồ, `M` là merge commit mới. Một parent là tip của lịch sử đích (`C`), parent còn lại là tip lịch sử nguồn (`Z`). Các commit cũ giữ nguyên object ID; đồ thị giờ có một điểm kết nối.

Đây là lựa chọn phù hợp khi:

- Hai dự án cần trở thành một repository và lịch sử cả hai cần được giữ nguyên.
- Muốn tiếp tục truy vết commit, tác giả, thời điểm và quan hệ cha-con của repository nguồn.
- Có thể chấp nhận một merge commit nối hai gốc lịch sử.

Merge commit mới chỉ kết nối lịch sử; nó không tự giải quyết xung đột về tên file hoặc cấu trúc dự án.

## 5. Xử lý xung đột khi hai repository có cùng file gốc

Hai repository độc lập thường cùng có những file như `README.md`, `.gitignore`, `LICENSE` hoặc cấu hình build. Khi merge, Git có thể báo xung đột vì cả hai lịch sử đều tạo nội dung cho cùng đường dẫn mà không có tổ tiên chung để so sánh thay đổi.

Kiểm tra trạng thái:

```bash
git status
git diff --name-only --diff-filter=U
```

Mở từng file xung đột và quyết định nội dung cuối cùng. Ví dụ:

```text
<<<<<<< HEAD
# Application Platform
=======
# Legacy Service
>>>>>>> legacy/main
```

Các marker trên chỉ minh họa. Hãy kết hợp nội dung phù hợp, xóa marker và stage file đã giải quyết:

```bash
git add README.md .gitignore
git status
git diff --cached
git commit
```

Khi merge dừng vì xung đột, `git commit` sau khi stage đầy đủ sẽ hoàn tất merge nếu Git yêu cầu tạo merge commit. Bạn cũng có thể dùng `git merge --continue` trong workflow merge tương ứng.

Nếu nhận ra đã chọn sai nguồn hoặc muốn thiết kế lại cách nhập, hủy merge đang dừng:

```bash
git merge --abort
```

Sau đó kiểm tra branch backup và lập lại quy trình với phạm vi phù hợp. Không xóa thủ công các file trong `.git` để thoát trạng thái merge.

## 6. Xác minh đồ thị sau khi merge

Sau khi merge hoàn tất:

```bash
git log --oneline --graph --decorate --all
git show --no-patch --pretty=raw HEAD
git rev-list --count main
```

Với merge commit, `git show --pretty=raw` hiển thị hai dòng `parent`. Xác nhận cả tip lịch sử cũ và nguồn đều là tổ tiên của merge commit:

```bash
git merge-base --is-ancestor backup/main-before-import HEAD
git merge-base --is-ancestor legacy/main HEAD
```

Nếu cả hai lệnh trả mã thoát `0`, merge commit hiện tại có chứa cả hai lịch sử theo quan hệ tổ tiên. Kiểm tra nội dung tree và chạy test/build cần thiết để xác nhận kết quả tích hợp.

Khi đã xác minh, có thể giữ remote `legacy` để tiếp tục fetch thay đổi từ nguồn, hoặc xóa remote nếu chỉ dùng cho lần nhập một lần:

```bash
git remote remove legacy
```

Xóa remote chỉ gỡ cấu hình và remote-tracking refs liên quan ở local; nó không xóa repository nguồn hoặc các commit đã được kết nối vào lịch sử đích.

## 7. Khi muốn nhập repository nguồn vào thư mục con

Nếu repository đích là monorepo và bạn muốn đặt toàn bộ nội dung repository nguồn vào một thư mục như `components/legacy-app/`, merge nguyên root có thể gây nhiều xung đột tên file và làm lẫn cấu trúc dự án.

Trong trường hợp này, `git subtree` thường phù hợp. Subtree đưa nội dung của repository nguồn vào một prefix trong repository đích và có thể giữ lịch sử nguồn trong đồ thị commit.

Ví dụ:

```bash
git remote add legacy https://git.example.com/team/legacy-app.git
git fetch legacy
git subtree add --prefix=components/legacy-app legacy main
```

Lệnh trên nhập nội dung branch `legacy/main` vào thư mục `components/legacy-app/` và tạo merge commit kết nối lịch sử. Không thêm `--squash` nếu mục tiêu là giữ chuỗi lịch sử nguồn có thể truy vết.

Nếu muốn chỉ ghi nhận một commit tổng hợp cho lần nhập, dùng:

```bash
git subtree add --prefix=components/legacy-app --squash legacy main
```

Với `--squash`, Git tạo một commit tổng hợp đại diện cho nội dung nguồn tại thời điểm nhập thay vì đưa toàn bộ chuỗi commit nguồn vào lịch sử đích theo cách subtree đầy đủ. Đây là lựa chọn giảm độ dài lịch sử hiển thị trong dự án chính, nhưng làm giảm khả năng xem từng commit nguồn trực tiếp trong đồ thị chính.

`git subtree` có thể không được cài sẵn trong mọi bản phân phối Git hoặc môi trường tối giản. Nếu Git báo `subtree` không phải lệnh hợp lệ, cài hoặc bật thành phần Git subtree theo cách quản trị phần mềm của môi trường. Đừng thay thế bằng một script tải từ nguồn không xác minh.

## 8. Viết lại lịch sử nguồn để chuyển toàn bộ file vào prefix

Một lựa chọn khác là viết lại lịch sử repository nguồn sao cho mọi commit đều đặt nội dung dưới một thư mục con. Công cụ `git filter-repo` hỗ trợ việc này, ví dụ:

```bash
git clone --no-local https://git.example.com/team/legacy-app.git legacy-filtered
cd legacy-filtered
git filter-repo --to-subdirectory-filter components/legacy-app
```

Sau thao tác, các commit nguồn được tạo lại với tree đã chuyển vào `components/legacy-app/`. Quan hệ cha-con nội bộ của chuỗi commit được giữ, nhưng object ID thay đổi vì nội dung tree và commit đã thay đổi. Chữ ký commit cũ không còn xác minh cho các commit mới được viết lại.

Sau đó, có thể fetch lịch sử đã lọc vào repository đích và kết nối bằng merge cho hai lịch sử không liên quan. Quy trình này phức tạp hơn subtree và cần kiểm tra refs, tag, branch, commit ký và các tham chiếu ngoài repository trước khi áp dụng.

Chỉ dùng `git filter-repo` khi có lý do rõ ràng, chẳng hạn cần chuyển cả lịch sử vào prefix, loại bỏ dữ liệu nhạy cảm hoặc chuẩn hóa repository. Hãy sao lưu repository nguồn, thông báo người dùng và lập kế hoạch force-update remote nếu lịch sử đã chia sẻ bị viết lại.

## 9. Chỉ lấy một số commit bằng cherry-pick

Nếu không cần toàn bộ lịch sử nguồn, nhưng muốn mang một số thay đổi cụ thể vào repository đích, có thể dùng `cherry-pick`.

Sau khi fetch:

```bash
git log --oneline legacy/main
git switch -c import/fix-selected main
git cherry-pick <commit-id>
```

Git áp dụng thay đổi của commit được chọn lên branch hiện tại và tạo commit mới. Commit mới có parent thuộc lịch sử đích, nên nó không giữ nguyên quan hệ tổ tiên với commit nguồn. Thông tin author thường được giữ, còn committer và commit ID phản ánh commit được tạo trong repository đích.

Cherry-pick phù hợp khi:

- Chỉ cần một bug fix hoặc feature độc lập.
- Không muốn đưa toàn bộ repository nguồn vào lịch sử đích.
- Nhóm chấp nhận lịch sử mới ghi nhận thay đổi được áp dụng lại thay vì kết nối hai đồ thị.

Nếu cần mang nhiều commit phụ thuộc nhau, hãy chọn phạm vi và thứ tự cẩn thận. Sau khi cherry-pick, kiểm tra test và diff; không giả định commit mới giống hệt object nguồn.

## 10. Chỉ sao chép snapshot hiện tại

Nếu chỉ cần nội dung file hiện tại mà không cần lịch sử nguồn, có thể sao chép file vào repository đích rồi commit như thay đổi mới. Ví dụ dùng archive để lấy snapshot của branch nguồn:

```bash
mkdir -p imported-files
git archive --format=tar legacy/main | tar -xf - -C imported-files
```

Sau đó đưa nội dung đã chọn vào thư mục đích và commit:

```bash
git add imported-files/
git commit -m "Import legacy application snapshot"
```

Phương pháp này chỉ nhập snapshot được xuất ra; lịch sử commit của repository nguồn không trở thành tổ tiên của repository đích. Hãy ghi lại nguồn, branch, commit ID và ngày nhập trong thông điệp hoặc tài liệu để sau này có thể truy nguyên.

Nếu cần giữ file trong một thư mục con, hãy đặt archive vào đúng thư mục đích ngay từ đầu hoặc di chuyển nội dung trước khi stage. Kiểm tra kỹ đường dẫn để tránh ghi đè file hiện có.

## 11. So sánh các lựa chọn nhập lịch sử

| Cách làm | Lịch sử nguồn | Quan hệ commit | Trường hợp phù hợp |
|---|---|---|---|
| `merge --allow-unrelated-histories` | Giữ toàn bộ lịch sử | Kết nối hai đồ thị bằng merge commit | Hợp nhất hai repository thành một root chung |
| `git subtree add` | Có thể giữ lịch sử nguồn | Kết nối lịch sử và đặt nội dung dưới prefix | Nhập dự án thành thư mục con trong monorepo |
| `git subtree add --squash` | Không đưa từng commit nguồn vào đồ thị chính theo cách đầy đủ | Ghi một commit tổng hợp cho snapshot nhập | Chỉ cần trạng thái nguồn tại thời điểm nhập |
| `git filter-repo --to-subdirectory-filter` | Giữ chuỗi thay đổi nội bộ sau khi viết lại | Commit ID đổi; có thể merge lịch sử đã lọc | Cần chuyển toàn bộ lịch sử vào prefix hoặc chuẩn hóa lịch sử |
| `cherry-pick` | Chỉ lấy các thay đổi được chọn | Tạo commit mới trên lịch sử đích | Lấy bug fix/feature chọn lọc |
| Sao chép snapshot | Không giữ lịch sử nguồn | Chỉ tạo commit mới ghi nhận file được copy | Chỉ cần nội dung hiện tại |
| Submodule | Lịch sử vẫn ở repository riêng | Superproject lưu gitlink tới commit nguồn | Muốn giữ thành phần độc lập và cập nhật riêng |

Hãy chọn dựa trên cách nhóm sẽ bảo trì nội dung sau khi nhập. Nếu thành phần vẫn phát triển độc lập, submodule hoặc subtree có thể phù hợp hơn việc trộn toàn bộ file vào root. Nếu cần truy vết đầy đủ trong một repository, merge hoặc subtree không squash thường phù hợp.

## 12. Di chuyển lịch sử qua môi trường không có kết nối mạng

Nếu repository nguồn không thể truy cập trực tiếp từ máy đích, có thể chuyển lịch sử bằng Git bundle. Từ repository nguồn:

```bash
git bundle create ../legacy-repository.bundle --all
git bundle verify ../legacy-repository.bundle
```

Bundle chứa các object và refs được chọn theo phạm vi tạo bundle. Chuyển file bundle qua kênh nội bộ được phép, sau đó ở repository đích:

```bash
git fetch ../legacy-repository.bundle main:refs/remotes/legacy/main
```

Sau khi fetch, kiểm tra lịch sử:

```bash
git log --oneline --graph --decorate refs/remotes/legacy/main
```

Tiếp tục chọn merge, subtree hoặc cherry-pick như các phần trước. Bundle không tự quyết định cách kết nối lịch sử; nó chỉ chuyển object và refs để repository đích có thể truy cập.

## 13. Những điều cần kiểm tra sau khi nhập

Sau khi merge, subtree hoặc cherry-pick, hãy kiểm tra cả đồ thị và nội dung:

```bash
git status -sb
git log --oneline --graph --decorate --all
git diff backup/main-before-import...HEAD
git ls-tree -r --name-only HEAD
```

Các điểm cần xác nhận:

- Commit nguồn có nằm trong lịch sử theo cách dự định không?
- Merge commit có parent đúng không?
- File có nằm ở đúng đường dẫn, đặc biệt khi nhập vào prefix không?
- `.gitignore`, `.gitattributes`, `.gitmodules`, LFS và cấu hình build có xung đột không?
- Có file trùng tên hoặc license cần xử lý không?
- Build, test, lint và quy trình CI có chạy được sau khi nhập không?
- README hoặc tài liệu có ghi lại nguồn gốc, branch và commit được nhập không?

Nếu nhập repository nguồn có tag, kiểm tra tên tag bị trùng. Tag là ref dùng chung trong repository đích; hai repository có thể có cùng tên tag nhưng trỏ tới commit khác nhau. Không tự ghi đè tag release hiện có mà chưa thống nhất.

## 14. Những nhầm lẫn thường gặp

- **Dùng merge bình thường khi hai lịch sử không có tổ tiên chung.** Git từ chối; chỉ dùng `--allow-unrelated-histories` sau khi xác nhận đúng hai repository.
- **Cho rằng `--allow-unrelated-histories` viết lại commit cũ.** Tùy chọn này cho phép nối đồ thị; các commit cũ vẫn giữ object ID.
- **Cho rằng merge tự xử lý file trùng tên.** Các file root như README hoặc LICENSE có thể xung đột và cần quyết định thủ công.
- **Dùng cherry-pick rồi nghĩ commit nguồn vẫn là tổ tiên.** Cherry-pick tạo commit mới trên branch đích; quan hệ ancestry nguồn không được giữ.
- **Dùng `--squash` nhưng vẫn kỳ vọng xem từng commit nguồn trong lịch sử chính.** Squash tổng hợp thay đổi thành một commit thay vì nối toàn bộ chuỗi commit nguồn.
- **Dùng filter-repo mà không thông báo.** Lịch sử được viết lại làm hash thay đổi và có thể ảnh hưởng mọi clone, tag, chữ ký và pipeline.
- **Chỉ sao chép file nhưng quên ghi nguồn gốc.** Sau này khó xác định snapshot đến từ branch hoặc commit nào.
- **Nhập repository rồi bỏ qua license và cấu hình.** Hợp nhất kỹ thuật không tự giải quyết quyền sử dụng, dependency hoặc chính sách bảo mật.

## 15. Quy trình thực hành: hợp nhất hai repository và giữ nguyên lịch sử

Giả sử repository `platform` có branch `main`, còn repository `legacy-app` cũng có branch `main`. Hai repository được tạo độc lập và nhóm muốn giữ lịch sử cả hai trong cùng một repository.

1. Kiểm tra repository đích sạch và tạo branch backup:

   ```bash
   git status -sb
   git switch main
   git branch backup/main-before-legacy-import
   ```

2. Thêm remote và fetch repository nguồn:

   ```bash
   git remote add legacy https://git.example.com/team/legacy-app.git
   git fetch legacy
   ```

3. Xem lịch sử và xác nhận không có merge base:

   ```bash
   git log --oneline --graph --decorate main legacy/main
   git merge-base main legacy/main
   ```

4. Nối hai lịch sử:

   ```bash
   git merge --allow-unrelated-histories legacy/main
   ```

5. Giải quyết file xung đột, stage và hoàn tất merge.
6. Xác nhận hai tip cũ đều là tổ tiên của `HEAD`:

   ```bash
   git merge-base --is-ancestor backup/main-before-legacy-import HEAD
   git merge-base --is-ancestor legacy/main HEAD
   ```

7. Chạy test, kiểm tra license, tài liệu và pipeline.
8. Push branch đã tích hợp theo quy trình review của nhóm:

   ```bash
   git push origin main
   ```

Không push thẳng vào branch được bảo vệ nếu quy trình yêu cầu pull request. Sau khi nhập, giữ remote `legacy` nếu cần tiếp tục đồng bộ; nếu chỉ dùng một lần, xóa cấu hình remote sau khi đã xác nhận lịch sử nguồn đã được kết nối.

## 16. Ghi nhớ

Trước khi nhập một repository khác, hãy xác định hai lịch sử có chung tổ tiên hay không và quyết định cần giữ toàn bộ lịch sử, một phần commit hay chỉ snapshot. `git merge --allow-unrelated-histories` nối hai đồ thị bằng merge commit mà không viết lại commit cũ. `git subtree` phù hợp khi đưa nội dung vào thư mục con; `filter-repo` có thể chuyển toàn bộ lịch sử vào prefix nhưng làm thay đổi hash; `cherry-pick` và sao chép snapshot chỉ nhập các thay đổi được chọn. Tạo backup, kiểm tra nguồn, xác minh đồ thị và chạy test trước khi chia sẻ kết quả.
