# Viết lại lịch sử bằng công cụ lọc chuyên dụng và kế hoạch đồng bộ bản sao

Git lưu lịch sử theo các object có mã định danh dựa trên nội dung. Khi thay đổi nội dung của một commit, mã commit đó thay đổi; các commit con cũng nhận mã mới vì parent của chúng đã thay đổi. Do đó, việc xóa một file khỏi commit mới nhất không loại bỏ file khỏi các commit cũ. Nếu repository từng chứa secret, dữ liệu nhạy cảm hoặc file nhị phân lớn, ta có thể cần viết lại lịch sử để loại nội dung đó khỏi các commit liên quan.

Viết lại lịch sử là thao tác quản trị có ảnh hưởng tới mọi bản sao đang dựa trên commit cũ. Cần có công cụ phù hợp, bản backup đầy đủ, cửa sổ đóng băng thao tác ghi và kế hoạch đồng bộ cho clone, fork, pull request, CI và các hệ thống phụ thuộc. Bài học này tập trung vào `git filter-repo`, cách kiểm tra kết quả, cập nhật remote và đưa các bản sao của nhóm về lịch sử mới.

Trong dịch vụ quản lý mã nguồn Git, viết lại lịch sử thường được dùng để loại secret bị commit nhầm, xóa file không nên lưu trong Git hoặc chuyển đổi cấu trúc lịch sử theo chính sách mới. Đây không phải thao tác sửa lỗi commit thông thường; chỉ thực hiện khi có mục tiêu rõ ràng và đã thống nhất tác động với những người dùng repository.

## 1. Vì sao phải viết lại lịch sử?

Một số tình huống phổ biến:

- Một file `.env`, private key, token hoặc credential từng được commit.
- File build, archive hoặc binary lớn được đưa vào nhiều commit khiến repository phình to.
- Một thư mục hoặc file cần loại khỏi toàn bộ lịch sử theo yêu cầu pháp lý hoặc chính sách lưu trữ.
- Repository cần đổi cấu trúc đường dẫn trên toàn bộ các nhánh.
- Nhóm cần chuẩn hóa danh tính tác giả hoặc metadata commit trong một đợt di chuyển có kiểm soát.

Xóa file ở commit mới nhất chỉ tạo một commit mới ghi nhận việc xóa. Những commit trước vẫn chứa blob cũ:

```text
Trước khi xóa file:

A --- B --- C --- D  main
          |
          +-- B chứa secrets.env

Sau khi chạy git rm và commit:

A --- B --- C --- D --- E  main
          |
          +-- B vẫn chứa secrets.env
                         E chỉ ghi nhận việc xóa file
```

Muốn loại file khỏi các commit cũ, cần tạo lại các commit có chứa file đó. Sau khi viết lại, lịch sử có dạng mới:

```text
A' --- B' --- C' --- D' --- E'  main
        (không còn secrets.env trong các snapshot được lọc)
```

Các mã commit được tạo lại. Thay đổi này ảnh hưởng tới nhánh, tag, pull request và mọi clone đang dùng lịch sử cũ.

## 2. Viết lại lịch sử khác với revert hoặc commit xóa file

| Cách xử lý | Kết quả | Lịch sử cũ còn giữ nội dung không? |
| --- | --- | --- |
| `git rm` rồi commit | Xóa file khỏi snapshot mới nhất | Có |
| `git revert <commit>` | Tạo commit mới đảo ngược thay đổi của commit trước | Có |
| `git filter-repo` | Tạo lại commit/tree theo quy tắc lọc | Các object bị lọc có thể bị loại khỏi lịch sử mới; clone cũ và backup vẫn có thể giữ chúng |

Nếu mục tiêu là hoàn tác một thay đổi đã công bố, `git revert` thường phù hợp vì giữ lịch sử công khai. Nếu mục tiêu là loại bỏ dữ liệu nhạy cảm khỏi lịch sử, revert không đủ. Nếu mục tiêu là giảm dung lượng do blob lớn, xóa ở commit mới cũng không giải phóng blob cũ.

**Với secret bị lộ, hãy thu hồi hoặc rotate secret ngay lập tức trước khi viết lại Git history.** Viết lại lịch sử không làm token cũ mất hiệu lực và không xóa các bản sao mà người khác hoặc dịch vụ đã tải xuống.

## 3. Chọn công cụ lọc chuyên dụng

### `git filter-repo`

`git filter-repo` là công cụ chuyên dụng, hiện được khuyến nghị cho phần lớn nhu cầu lọc và viết lại lịch sử Git. Công cụ hỗ trợ lọc theo đường dẫn, nội dung blob, kích thước, ref và nhiều tiêu chí khác. Nó thường nhanh và an toàn hơn quy trình dựa trên `git filter-branch`.

Kiểm tra công cụ:

```bash
git filter-repo --version
```

Nếu chưa có, cài theo hướng dẫn chính thức phù hợp với hệ điều hành và phiên bản Python/package manager của môi trường. Sau khi cài, xác nhận lệnh `git filter-repo` có trong PATH.

### `git filter-branch`

`git filter-branch` là công cụ cũ được Git cung cấp lâu năm, nhưng có nhiều giới hạn về hiệu năng và dễ mắc lỗi khi viết script lọc. Với dự án mới, ưu tiên `git filter-repo`; chỉ duy trì `filter-branch` khi phải tương thích với môi trường cũ và đã hiểu rõ rủi ro.

### BFG Repo-Cleaner

BFG là một lựa chọn khác cho một số tác vụ phổ biến như xóa file lớn hoặc thay thế nội dung nhạy cảm. Công cụ có cách sử dụng riêng và có thể phù hợp khi nhóm đã có quy trình BFG ổn định. Bài này dùng `git filter-repo` làm ví dụ chính vì hỗ trợ nhiều kiểu lọc và có thể kiểm soát phạm vi refs.

## 4. Lập kế hoạch trước khi viết lại

Viết lại lịch sử cần được xem như một đợt bảo trì có lịch, đặc biệt với repository đã được chia sẻ.

### Xác định phạm vi

Trả lời các câu hỏi:

1. Nội dung nào cần loại bỏ hoặc thay đổi: một đường dẫn, nhiều đường dẫn, chuỗi bí mật, blob vượt kích thước hay metadata?
2. Cần lọc mọi branch/tag hay chỉ một tập ref cụ thể?
3. Những tag release, branch bảo trì, fork và pull request nào bị ảnh hưởng?
4. Có LFS object, submodule, package, release asset hoặc artifact liên quan không?
5. Những nhóm nào cần đồng bộ clone và thời điểm nào được phép push trở lại?

### Đóng băng thao tác ghi

Trước khi chạy filter:

- Thông báo thời gian bảo trì và yêu cầu tạm dừng push, merge pull request, tạo tag hoặc cập nhật branch.
- Tạm dừng pipeline có khả năng ghi ngược vào repository.
- Ghi nhận danh sách branch và tag đang tồn tại.
- Xác định các ref đặc biệt do dịch vụ Git tạo ra, chẳng hạn ref pull request hoặc ref nội bộ mà người dùng không thể push.
- Chỉ định người chịu trách nhiệm chạy filter và người xác minh kết quả.

Nếu có người push trong lúc lọc, bản rewrite có thể bỏ sót commit mới hoặc ghi đè thay đổi vừa được đẩy. Đóng băng thao tác ghi giúp mọi người cùng bắt đầu từ một snapshot nhất quán.

### Bảo vệ dữ liệu và backup

Tạo backup Git đầy đủ trước khi lọc. Nếu repository dùng Git LFS, backup LFS object riêng vì mirror clone Git không tự bảo đảm đã tải toàn bộ nội dung LFS.

Ví dụ:

```bash
git clone --mirror https://git.example.com/team/project.git project-backup.git
git -C project-backup.git lfs fetch --all origin
```

Lệnh thứ hai chỉ cần khi repository dùng LFS và môi trường đã cài Git LFS. Xác nhận cả mirror clone và LFS fetch hoàn tất. Bảo vệ backup bằng quyền truy cập phù hợp; nếu lý do viết lại là secret bị lộ, backup vẫn chứa secret cũ và phải được lưu trong vùng hạn chế truy cập.

Không dùng bản backup chứa dữ liệu nhạy cảm như một remote làm việc thường xuyên. Khi quy trình xử lý sự cố cho phép, lưu trữ hoặc hủy backup theo chính sách bảo mật và retention.

## 5. Kiểm kê refs và dung lượng trước khi lọc

Trong clone được dùng để viết lại, ghi nhận các refs hiện có:

```bash
git show-ref
git for-each-ref --format='%(refname) %(objectname)'
```

Kiểm tra branch và tag:

```bash
git branch -a
git tag --list
```

Đo dung lượng object:

```bash
git count-objects -vH
```

Với file lớn, có thể phân tích các object và đường dẫn trước khi chọn tiêu chí lọc. `git filter-repo` cung cấp chế độ phân tích:

```bash
git filter-repo --analyze
```

Chế độ này tạo các báo cáo phân tích trong thư mục metadata của filter-repo. Xem báo cáo để nhận diện đường dẫn hoặc blob chiếm dung lượng lớn, sau đó quyết định rõ file nào thực sự cần loại bỏ. Không xóa file chỉ vì nó đứng đầu danh sách dung lượng; có thể đó là tài sản cần được chuyển sang LFS hoặc kho artifact.

## 6. Thực hiện trong một mirror clone mới

Với repository đã chia sẻ, nên lọc trong một mirror clone mới được tạo riêng cho đợt rewrite. Ví dụ:

```bash
git clone --mirror https://git.example.com/team/project.git project-rewrite.git
```

Mirror clone là repository bare, chứa các refs được máy chủ quảng bá và không có working tree. Đây là lựa chọn phù hợp khi cần viết lại nhiều branch và tag cùng lúc.

Chuyển vào repository:

```bash
cd project-rewrite.git
git show-ref
git remote -v
```

`git filter-repo` thường yêu cầu clone mới để giảm nguy cơ vô tình viết lại một repository đang chứa công việc local. Nếu công cụ từ chối chạy vì repository không có vẻ là fresh clone, hãy tạo clone mới và thực hiện trong đó. Chỉ dùng `--force` khi đã hiểu cảnh báo, đã có backup và có lý do rõ ràng phải chạy trên repository hiện tại; không dùng `--force` như cách bỏ qua kiểm tra mặc định.

## 7. Loại một hoặc nhiều đường dẫn khỏi toàn bộ lịch sử

Giả sử file `config/secrets.env` từng được commit ở nhiều thời điểm và cần loại khỏi mọi snapshot:

```bash
git filter-repo --path config/secrets.env --invert-paths
```

Ý nghĩa:

- `--path config/secrets.env` chọn đường dẫn cần giữ trong phạm vi lọc.
- `--invert-paths` đảo lựa chọn, tức loại đường dẫn đó khỏi lịch sử.

Muốn loại nhiều đường dẫn:

```bash
git filter-repo \
  --path config/secrets.env \
  --path deploy/private-key.pem \
  --invert-paths
```

Đường dẫn được tính tương đối từ gốc repository. Nếu file từng được đổi tên hoặc di chuyển, cần đưa tất cả đường dẫn cũ và mới vào danh sách lọc. Nếu chỉ lọc tên hiện tại, phiên bản ở đường dẫn cũ có thể vẫn còn trong commit lịch sử.

Ví dụ file từng tồn tại ở hai vị trí:

```bash
git filter-repo \
  --path old/config/secrets.env \
  --path config/secrets.env \
  --invert-paths
```

Nếu chỉ muốn giữ một thư mục hoặc một tập file, bỏ `--invert-paths` và liệt kê các `--path` cần giữ. Hãy kiểm tra cách khớp đường dẫn của công cụ trước khi lọc để tránh đảo ngược phạm vi ngoài ý muốn.

## 8. Thay thế chuỗi nhạy cảm trong nội dung lịch sử

Khi secret được chép vào nhiều file hoặc nhiều commit, có thể dùng `--replace-text` để thay chuỗi trong blob lịch sử.

Tạo file biểu thức ở bên ngoài repository làm việc, ví dụ `../replacements.txt`:

```text
literal:EXAMPLE_OLD_TOKEN_VALUE==>***REMOVED***
literal:old-password-for-demo==>***REMOVED***
```

Các chuỗi ở trên chỉ là giá trị giả lập. Không đưa secret thật vào lệnh shell, log hoặc tài liệu hướng dẫn. Bảo vệ file biểu thức nếu nó có chứa chuỗi nhạy cảm thật.

Chạy lọc:

```bash
git filter-repo --replace-text ../replacements.txt
```

`--replace-text` thay nội dung khớp trong các blob được xử lý. File biểu thức hỗ trợ các dạng như `literal:`, `regex:` hoặc `glob:` tùy cú pháp của phiên bản công cụ. Hãy kiểm tra tài liệu `git filter-repo --help` trước khi dùng biểu thức phức tạp.

Thay thế chuỗi trong Git history không thu hồi secret. Token, mật khẩu và khóa riêng phải được thu hồi hoặc thay mới tại hệ thống phát hành chúng. Ngoài ra, secret có thể xuất hiện trong encoding khác, dạng đã mã hóa, file nhị phân, log hoặc bản sao ngoài repository; cần dùng công cụ secret scanning và kiểm tra theo phạm vi sự cố.

## 9. Loại blob vượt kích thước hoặc theo danh sách object

Nếu repository chứa nhiều blob lớn không nên được lưu trong Git, có thể dùng:

```bash
git filter-repo --strip-blobs-bigger-than 50M
```

Lệnh loại các blob vượt ngưỡng khỏi lịch sử được lọc. Đây là thao tác rộng: có thể xóa cả tài sản hợp lệ như video, model hoặc dữ liệu kiểm thử. Phân tích trước bằng `--analyze`, xác định file cần giữ và cân nhắc chuyển chúng sang LFS hoặc artifact storage.

Nếu đã có danh sách blob cụ thể cần loại, có thể dùng `--strip-blobs-with-ids` với file chứa các object ID theo định dạng công cụ yêu cầu. Đây là cách nhắm mục tiêu hơn so với xóa mọi blob trên một ngưỡng kích thước.

Sau khi loại blob, các commit mà snapshot thay đổi có thể được viết lại; commit rỗng hoặc merge trở nên suy biến có thể bị xử lý theo quy tắc của công cụ. Kiểm tra kỹ lịch sử mới và các merge commit quan trọng.

## 10. Chỉ lọc một số refs

Không phải đợt rewrite nào cũng cần tác động tới toàn bộ refs. `git filter-repo` hỗ trợ `--refs` để giới hạn phạm vi ref được viết lại, ví dụ:

```bash
git filter-repo \
  --path config/obsolete.yml \
  --invert-paths \
  --refs refs/heads/main refs/heads/release/2.x
```

Trước khi dùng phạm vi giới hạn, cần hiểu quan hệ giữa các branch và tag. Một commit có thể được nhiều ref cùng tham chiếu; nếu chỉ viết lại một số ref, các ref không được chọn có thể tiếp tục trỏ tới lịch sử cũ. Điều này có thể là chủ đích khi chỉ sửa một nhánh riêng, nhưng không đáp ứng mục tiêu loại bỏ dữ liệu khỏi toàn repository.

Với sự cố secret, thông thường phải kiểm kê và xử lý mọi ref có thể truy cập nội dung nhạy cảm, gồm branch, tag và các ref khác được nhà cung cấp quảng bá. Không mặc định `--refs` là lựa chọn an toàn hơn; phạm vi phải khớp mục tiêu xử lý.

## 11. Kiểm tra kết quả sau khi lọc

Không push ngay sau khi lệnh filter kết thúc. Trước hết, kiểm tra refs và nội dung mới.

### Kiểm tra lịch sử và file đã loại

```bash
git log --all --oneline --decorate -20
git show-ref
git log --all -- config/secrets.env
```

Lệnh cuối không nên còn commit nào ghi nhận đường dẫn đã loại trong phạm vi refs được lọc. Kiểm tra cả đường dẫn cũ nếu file từng được di chuyển.

### Kiểm tra object và tính toàn vẹn

```bash
git fsck --full
git count-objects -vH
```

Các cảnh báo dangling hoặc unreachable có thể xuất hiện tùy loại object và công cụ; cần xác định chúng có thuộc phạm vi cần loại hay là dữ liệu khác được giữ hợp lệ. Không bỏ qua lỗi missing/corrupt object.

### Kiểm tra bằng secret scanner

Chạy secret scanner hoặc công cụ kiểm tra lịch sử trên repository đã lọc. Với secret đã biết, xác nhận chuỗi không còn xuất hiện trong lịch sử được quảng bá. Tránh dùng `grep` với secret thật theo cách khiến giá trị bị in ra terminal hoặc lưu vào log.

### Xem bản đồ commit được tạo lại

`git filter-repo` có thể tạo các file metadata như `commit-map` và `ref-map` trong thư mục `.git/filter-repo` (với mirror clone bare, metadata nằm trong thư mục Git tương ứng). Các bản đồ này giúp đối chiếu mã commit cũ và mới, hữu ích khi cần thông báo cho nhóm hoặc cập nhật tham chiếu trong hệ thống ngoài Git.

Lưu các bản đồ cần thiết vào hồ sơ bảo trì có kiểm soát. Không công khai bản đồ hoặc log nếu chúng có thể làm lộ thông tin nhạy cảm hay mã commit dẫn tới dữ liệu bị loại.

## 12. Khôi phục remote sau khi filter-repo

Để tránh push nhầm, `git filter-repo` thường xóa remote `origin` khỏi cấu hình repository sau khi chạy. Kiểm tra:

```bash
git remote -v
```

Nếu `origin` không còn, thêm lại URL chính thức:

```bash
git remote add origin https://git.example.com/team/project.git
git remote -v
```

Xác nhận URL đúng repository đích và không chứa username/token. Không thêm remote backup làm đích push nhầm.

## 13. Đẩy lịch sử mới lên remote

Đây là bước ảnh hưởng trực tiếp tới người khác. Chỉ thực hiện trong cửa sổ bảo trì đã thông báo, sau khi xác minh backup, phạm vi refs và kết quả lọc.

### Push các branch đã viết lại

Với repository thông thường, có thể cập nhật các branch local:

```bash
git push --force --all origin
```

Lệnh này force update các branch local lên remote. Nó không tự xóa mọi branch remote không còn tồn tại local và không thay thế việc xử lý các ref đặc biệt của nhà cung cấp.

### Push các tag đã viết lại

```bash
git push --force --tags origin
```

Tag trỏ tới commit cũ cần được cập nhật theo kế hoạch. Annotated tag có thể được tạo lại; chữ ký của tag cũ không còn xác thực cho object mới. Nếu quy trình phát hành yêu cầu chữ ký, hãy ký lại tag sau khi rewrite và kiểm tra chính sách bảo vệ tag.

Nếu một tag cần bị loại bỏ hoàn toàn, việc không còn tag đó trong clone local không tự xóa tag trên remote khi dùng `git push --tags`. Xóa tag remote theo tên sau khi xác nhận phạm vi:

```bash
git push origin --delete v1.2.3
```

Chỉ xóa tag phát hành khi chủ sở hữu release và nhóm đã thống nhất; nếu tag cần giữ tên nhưng trỏ tới commit mới, hãy tạo/cập nhật tag theo quy trình ký và phát hành của dự án.

### Khi cần mirror toàn bộ refs

Trong trường hợp mirror clone là bản đầy đủ và được xác nhận là nguồn chuẩn cho toàn bộ refs mà remote cho phép quản lý, có thể dùng:

```bash
git push --force --mirror origin
```

`--mirror` đồng bộ toàn bộ refs mà mirror clone quản lý và có thể xóa refs trên remote nếu chúng không còn tồn tại trong local. Đây là thao tác có phạm vi rộng; không chạy trên remote dùng chung nếu chưa kiểm kê ref ẩn, pull request refs, refs do nhà cung cấp quản lý và chính sách branch/tag.

### `--force-with-lease` và cửa sổ đóng băng

Với cập nhật một branch cụ thể, `--force-with-lease` có thể giúp từ chối push nếu remote đã thay đổi so với giá trị mà local đang kỳ vọng:

```bash
git push --force-with-lease origin main
```

Tuy nhiên, với một đợt rewrite toàn bộ refs, cần kế hoạch riêng cho từng ref và trạng thái remote. Force push có chủ đích chỉ an toàn khi nhóm đã đóng băng ghi, kiểm kê refs và xác nhận không có commit mới cần giữ. Nếu có cập nhật mới ngoài kế hoạch, dừng và xử lý chúng trước khi ghi đè.

## 14. Các hệ thống có thể vẫn giữ lịch sử cũ

Sau khi cập nhật remote, dữ liệu cũ có thể vẫn tồn tại ở:

- Clone local của developer và máy build.
- Fork của repository.
- Pull request hoặc merge request refs do máy chủ quản lý.
- Cache của CI/CD, mirror, backup và workspace runner.
- Tag, release asset, package hoặc artifact được tạo từ commit cũ.
- Log, patch, bundle, archive, tài liệu hoặc liên kết commit được lưu bên ngoài.
- LFS server nếu file lớn được quản lý bằng Git LFS.

Viết lại refs chính không tự động xóa mọi bản sao hoặc cache ở các hệ thống này. Nếu xử lý secret, coi mọi bản sao cũ là có khả năng đã lộ và thu hồi secret tại nguồn. Nếu xử lý dung lượng, xác định retention của từng hệ thống và lên kế hoạch dọn dẹp riêng.

## 15. Kế hoạch đồng bộ clone của thành viên

Các clone cũ có branch local và reflog trỏ tới commit cũ. Nếu người dùng tiếp tục push branch cũ, họ có thể đưa lịch sử đã loại trở lại remote. Vì vậy, đồng bộ clone là phần bắt buộc của đợt rewrite.

### Phương án khuyến nghị: clone lại

Với đa số thành viên, clone mới là cách đơn giản và ít rủi ro nhất:

1. Lưu patch hoặc commit chưa push cần giữ từ clone cũ.
2. Đóng các tiến trình IDE, Git GUI và công cụ đang dùng clone cũ.
3. Đổi tên hoặc di chuyển clone cũ sang thư mục lưu tạm theo chính sách của nhóm.
4. Clone lại repository từ remote đã được rewrite.
5. Khôi phục các thay đổi cá nhân bằng cách áp dụng patch hoặc cherry-pick commit phù hợp lên lịch sử mới.
6. Xóa clone cũ sau khi xác nhận không còn công việc cần giữ và sau khi xử lý backup theo chính sách.

Ví dụ:

```bash
git clone https://git.example.com/team/project.git project-clean
```

Không merge nguyên branch cũ vào branch mới vì việc đó có thể nối lịch sử cũ trở lại. Chỉ chuyển các thay đổi công việc cần giữ bằng patch hoặc cherry-pick sau khi review nội dung.

### Phương án cập nhật clone hiện có

Chỉ dùng khi người dùng hiểu rõ branch local, commit chưa push và working tree của mình. Trước tiên, lưu công việc chưa commit:

```bash
git status -sb
git diff > ../worktree-changes.patch
git diff --cached > ../staged-changes.patch
```

Các file untracked cần được sao lưu riêng hoặc thêm vào patch bằng cách phù hợp. Ghi lại commit local cần giữ và tạo branch cứu hộ nếu cần. Sau khi backup, fetch lịch sử mới:

```bash
git fetch --prune origin
```

Đưa branch làm việc về ref mới chỉ sau khi xác nhận không có commit local cần giữ:

```bash
git switch main
git reset --hard origin/main
```

`reset --hard` xóa thay đổi tracked chưa commit trong working tree và index. Không chạy nếu chưa lưu chúng. Với branch local khác, xử lý từng branch theo ref tương ứng; xóa branch cũ chỉ khi đã xác nhận không cần commit riêng.

Nếu có commit local riêng, tạo patch hoặc cherry-pick các commit đó lên branch mới:

```bash
git switch -c feature/work-on-new-history origin/main
git cherry-pick <local-commit-id>
```

Không merge branch local cũ chứa lịch sử trước rewrite vào branch mới. Điều đó có thể làm commit cũ reachable trở lại.

### Đồng bộ tag local

Tag cũ có thể vẫn trỏ tới commit cũ. Kiểm kê tag trước khi cập nhật. Sau khi đã lưu các tag cần giữ, xóa tag local cũ và tải lại tag mới theo hướng dẫn của nhóm:

```bash
git tag --list
git fetch --tags --force origin
```

Lệnh fetch tag với force có thể cập nhật tag đã tồn tại local; cần dùng sau khi đã xác nhận tag remote mới là nguồn chuẩn. Nếu một tag đã bị xóa khỏi remote, xóa tag local tương ứng bằng `git tag -d <tag-name>` sau khi xác nhận không còn cần tham chiếu cũ. Với tag release đã ký, xác minh chữ ký mới theo chính sách phát hành.

## 16. Đồng bộ fork, pull request và CI

### Fork

Fork là một repository riêng và có thể vẫn giữ lịch sử cũ. Chủ sở hữu fork cần đồng bộ hoặc tạo lại fork theo quy trình của nhà cung cấp. Nếu dữ liệu nhạy cảm bị lộ, thông báo cho chủ fork và quản trị dịch vụ để xử lý các bản sao, cache và ref mà người dùng không thể tự sửa.

### Pull request / merge request

Pull request có thể tham chiếu commit cũ và ref do nền tảng quản lý. Sau rewrite, một số PR có thể không còn cập nhật đúng hoặc cần tạo lại. Kiểm tra trạng thái review, CI checks, comment và liên kết commit trước khi đóng hoặc mở lại PR. Không mặc định rằng force push branch đã cập nhật mọi ref PR ẩn.

### CI/CD và build cache

Runner có thể đang giữ clone cũ hoặc cache object. Sau rewrite:

- Hủy hoặc hoàn tất job đang chạy trước khi cho phép job mới.
- Xóa workspace/cache Git theo quy trình của nền tảng CI.
- Clone/fetch lại từ remote mới.
- Cập nhật checkout ref, tag, commit pin và submodule reference nếu bị ảnh hưởng.
- Kiểm tra artifact hoặc package đã publish từ commit cũ có cần thay thế hay thu hồi không.

Nếu CI có quyền push, bảo đảm job cũ không chạy lại và đẩy ref cũ lên remote sau khi đợt rewrite kết thúc.

## 17. Submodule, LFS và các tham chiếu bên ngoài

Viết lại lịch sử repository cha có thể thay đổi commit mà submodule trỏ tới. Kiểm tra file `.gitmodules` và gitlink trong các commit mới. Nếu repository con cũng được rewrite, cập nhật URL, commit pointer và hướng dẫn clone đồng bộ.

Git LFS lưu binary ở máy chủ riêng. Lọc pointer khỏi Git history không đồng nghĩa object LFS đã bị xóa khỏi LFS storage. Nếu mục tiêu là loại nội dung nhạy cảm hoặc giải phóng dung lượng LFS, cần dùng công cụ và quy trình của nhà cung cấp để kiểm tra/xóa LFS object sau khi bảo đảm không còn ref hợp lệ cần chúng.

Các hệ thống bên ngoài có thể lưu mã commit cũ trong deployment manifest, release note, package metadata, ticket hoặc tài liệu. Dùng commit map do filter-repo tạo để đối chiếu khi cần cập nhật các tham chiếu đó.

## 18. Tác động tới chữ ký, tag và mã định danh commit

Khi commit được tạo lại, mã hash mới được tính từ nội dung và parent mới. Điều này có một số hệ quả:

- Liên kết web tới commit cũ có thể không còn là tham chiếu phù hợp.
- Commit GPG/SSH signature cũ không xác thực cho commit mới.
- Annotated tag trỏ tới object cũ cần được xử lý; chữ ký tag có thể không còn hợp lệ nếu tag object thay đổi.
- Commit ID được lưu trong ticket, tài liệu hoặc hệ thống triển khai có thể cần cập nhật.
- Các branch local và remote-tracking refs của clone cũ không tự chuyển sang mã commit mới.

Sau rewrite, nếu dự án yêu cầu commit/tag có chữ ký, hãy ký lại theo quy trình và xác minh chữ ký mới. Không sao chép chữ ký cũ sang commit đã viết lại.

## 19. Quy trình tổng thể từ backup tới đồng bộ

Một đợt rewrite có kiểm soát có thể thực hiện theo trình tự sau:

### Giai đoạn A: Chuẩn bị

1. Xác định chính xác nội dung cần lọc và phạm vi refs.
2. Nếu có secret, thu hồi/rotate trước khi làm các bước khác.
3. Thông báo và đóng băng push, merge, tag, CI có quyền ghi.
4. Kiểm kê refs, fork, PR, LFS, submodule và hệ thống phụ thuộc.
5. Tạo mirror backup và backup LFS object nếu có.
6. Tạo mirror clone mới để làm việc.

### Giai đoạn B: Lọc và xác minh

1. Chạy `git filter-repo --analyze` nếu cần hiểu dung lượng.
2. Chạy filter với tiêu chí đã review, chẳng hạn `--path ... --invert-paths` hoặc `--replace-text`.
3. Kiểm tra commit map, ref map, branch, tag và diff.
4. Chạy `git fsck --full` và secret scanner.
5. Xác nhận nội dung cần loại không còn trong refs được quảng bá.
6. Thêm lại remote chính thức và kiểm tra URL.

### Giai đoạn C: Cập nhật remote

1. Xác nhận mọi người vẫn đang dừng push.
2. Push các branch/tag đã viết lại theo phạm vi được duyệt.
3. Xử lý refs bị xóa hoặc refs do nền tảng quản lý riêng.
4. Clone mới từ remote và kiểm tra lịch sử sau push.
5. Xác nhận secret scanner và kiểm tra nội dung trên bản clone mới.

### Giai đoạn D: Đồng bộ người dùng và hệ thống

1. Hướng dẫn developer clone lại hoặc cập nhật clone hiện có theo quy trình.
2. Rebase/cherry-pick phần công việc local cần giữ; không merge lịch sử cũ trở lại.
3. Đồng bộ fork, pull request, tag, submodule và CI cache.
4. Kiểm tra release asset, package và artifact liên quan.
5. Mở lại quyền push sau khi các nhóm xác nhận đã đồng bộ.
6. Xử lý backup cũ theo chính sách bảo mật và retention.

## 20. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| `git filter-repo` từ chối chạy | Repository không được nhận diện là fresh clone | Tạo mirror clone mới; chỉ dùng `--force` khi hiểu rủi ro và đã backup |
| File vẫn xuất hiện trong lịch sử | File từng được đổi tên hoặc có đường dẫn cũ chưa lọc | Liệt kê tất cả đường dẫn lịch sử cần loại rồi chạy lại trong clone rewrite mới |
| Secret scanner vẫn phát hiện token | Token có biến thể khác, encoding khác hoặc nằm trong ref chưa lọc | Thu hồi token, kiểm tra mọi refs và dùng scanner trên toàn bộ lịch sử |
| Push bị từ chối | Branch/tag được bảo vệ hoặc quyền không cho force update | Dùng quy trình quản trị/maintenance của host; không tìm cách lách bảo vệ |
| Remote `origin` biến mất sau filter | filter-repo loại remote để tránh push nhầm | Xác minh URL rồi thêm lại remote chính thức |
| Clone cũ làm xuất hiện commit cũ trên remote | Thành viên push branch chưa đồng bộ | Tạm khóa ghi, tìm ref cũ vừa được push, xử lý lại và nhắc đồng bộ clone |
| Pull request không cập nhật đúng | PR ref do host quản lý hoặc commit base đã thay đổi | Kiểm tra công cụ của host, cập nhật hoặc tạo lại PR |
| LFS storage vẫn còn file đã lọc | LFS object nằm ngoài Git object database | Dùng quy trình quản lý LFS object của nhà cung cấp |
| Commit/tag signature không còn hợp lệ | Object đã được tạo lại | Ký lại commit/tag theo chính sách dự án |

## 21. Checklist trước khi kết thúc đợt rewrite

- [ ] Secret đã được thu hồi/rotate nếu từng bị lộ.
- [ ] Đã có backup Git và LFS object cần thiết.
- [ ] Đã kiểm kê branch, tag và refs đặc biệt.
- [ ] Tiêu chí filter đã được review trên clone riêng.
- [ ] Commit map/ref map được lưu theo chính sách.
- [ ] `git fsck --full` không báo lỗi object bị thiếu hoặc hỏng.
- [ ] Secret scanner không còn phát hiện nội dung cần loại trong refs đã lọc.
- [ ] Remote được cập nhật trong cửa sổ đóng băng.
- [ ] Clone mới từ remote đã được kiểm tra.
- [ ] Developer, fork, PR, CI, submodule và artifact đã có kế hoạch đồng bộ.
- [ ] Không còn pipeline hoặc clone cũ có thể push lịch sử trước rewrite.
- [ ] Backup cũ được bảo vệ hoặc xử lý theo chính sách retention.

## 22. Thực hành

Thực hiện trên repository thử nghiệm riêng, không dùng token hoặc dữ liệu thật:

1. Tạo repository có vài commit và một file giả lập `config/demo-secret.txt`.
2. Tạo thêm commit chỉnh sửa file đó để nó xuất hiện ở nhiều snapshot.
3. Clone repository bằng `git clone --mirror` sang thư mục riêng.
4. Chạy `git filter-repo --analyze` và xem báo cáo.
5. Chạy `git filter-repo --path config/demo-secret.txt --invert-paths`.
6. Kiểm tra `git log --all -- config/demo-secret.txt`, `git show-ref` và `git fsck --full`.
7. Xem commit map và ref map do công cụ tạo ra.
8. Thêm remote thử nghiệm lại nếu công cụ đã xóa `origin`, rồi push lịch sử mới tới một remote thử nghiệm.
9. Clone lại remote và xác nhận file demo không còn trong lịch sử mới.
10. Tạo một clone cũ trước rewrite, thử fetch và quan sát vì sao branch local vẫn trỏ tới commit cũ; thảo luận cách clone lại hoặc cherry-pick công việc cần giữ.

Không chạy force push lên repository thật trong bài thực hành. Mục tiêu là hiểu sự thay đổi commit ID và quy trình đồng bộ các bản sao.

## 23. Tự kiểm tra kiến thức

1. Vì sao `git rm` rồi commit không loại file khỏi các commit trước?
2. Khi nào nên dùng `git filter-repo` thay cho `git revert`?
3. Vì sao nên chạy filter trong mirror clone mới và tạo backup trước?
4. `--path` kết hợp `--invert-paths` có ý nghĩa gì?
5. Nếu file từng đổi tên, cần làm gì để loại mọi phiên bản đường dẫn?
6. `--replace-text` hỗ trợ loại dữ liệu nào và vì sao vẫn phải rotate secret?
7. Vì sao filter-repo có thể xóa remote `origin` và ta cần xác minh gì trước khi thêm lại?
8. Force push ảnh hưởng tới clone, fork và pull request như thế nào?
9. Vì sao clone mới thường an toàn hơn việc tiếp tục dùng clone cũ?
10. Làm thế nào để đưa commit local cần giữ sang lịch sử mới mà không nối lại lịch sử cũ?

## Kết luận

`git filter-repo` giúp viết lại lịch sử theo đường dẫn, nội dung, kích thước hoặc phạm vi ref. Vì commit ID và các tham chiếu liên quan thay đổi, cần tạo backup Git/LFS, đóng băng thao tác ghi, lọc trong clone riêng, kiểm tra toàn bộ refs rồi mới cập nhật remote. Sau đó, hướng dẫn developer clone lại hoặc chuyển phần công việc riêng bằng patch/cherry-pick, đồng bộ fork, pull request và CI, đồng thời ngăn clone cũ đẩy lịch sử cũ trở lại. Với secret bị lộ, thu hồi hoặc rotate ngay; viết lại lịch sử chỉ xử lý nội dung trong các refs đã lọc và không xóa những bản sao bên ngoài repository.
