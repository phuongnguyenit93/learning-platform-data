# Di chuyển tệp đã có trong lịch sử sang LFS và hệ quả viết lại commit

Git LFS giúp repository quản lý file lớn bằng cách lưu một **pointer file** nhỏ trong Git, còn nội dung thật được lưu trong kho LFS riêng. Nếu một file lớn đã được commit trước khi nhóm bật LFS, chỉ chạy `git lfs track` sẽ không chuyển các blob cũ trong lịch sử sang LFS. Muốn thay thế chúng, bạn cần di chuyển lịch sử bằng `git lfs migrate import`.

Thao tác này viết lại các commit có chứa file được chọn. Vì commit hash phụ thuộc vào nội dung tree và commit cha, các commit bị ảnh hưởng cùng những commit con phía sau có thể nhận mã SHA mới. Khi lịch sử đã được chia sẻ trên remote, việc công bố lịch sử mới cần phối hợp force-push và cập nhật các clone khác.

## 1. Vì sao cần migrate thay vì chỉ track?

Khi bạn chạy:

```bash
git lfs track "*.psd"
```

Git LFS thêm quy tắc vào `.gitattributes`, thường có dạng:

```gitattributes
*.psd filter=lfs diff=lfs merge=lfs -text
```

Quy tắc này khiến các lần `git add` tiếp theo xử lý file `.psd` qua bộ lọc LFS. Nội dung được stage trong các commit mới sẽ được thay bằng pointer file trong Git và object thật được lưu ở LFS.

Tuy nhiên, những commit cũ vẫn chứa blob nhị phân ban đầu. Git không tự sửa lịch sử chỉ vì `.gitattributes` thay đổi. Nếu một file 500 MB đã xuất hiện qua nhiều commit, các blob tương ứng với từng phiên bản nội dung vẫn có thể nằm trong lịch sử và làm clone repository nặng.

Để chuyển cả nội dung đã tồn tại trong lịch sử, dùng:

```bash
git lfs migrate import --include="*.psd"
```

Lệnh này tìm file khớp mẫu trong phạm vi ref được migrate, thay nội dung tương ứng bằng LFS pointer và viết lại các commit bị ảnh hưởng. Nó cũng cập nhật `.gitattributes` để các lần thêm file sau tiếp tục dùng LFS.

## 2. Hiểu pointer file và LFS object

Sau khi migrate, Git lưu một file văn bản nhỏ thay cho blob lớn. Ví dụ nội dung pointer:

```text
version https://git-lfs.github.com/spec/v1
oid sha256:4cac19622fc3ada9c0fdeadb33f88f367b541f38b891c6c6f2f3d2f4f5f6a7b8
size 52428800
```

Pointer chứa phiên bản định dạng, mã SHA-256 của nội dung thật và kích thước byte. Nội dung thật được lưu trong kho đối tượng LFS và truyền qua LFS endpoint của máy chủ. Git commit chỉ chứa pointer, vì vậy các thao tác Git thông thường không phải tải blob lớn vào object database của Git.

Khi checkout, Git LFS dùng pointer để tải nội dung tương ứng về working tree. Điều đó có nghĩa người clone cần cài Git LFS và có quyền truy cập LFS endpoint để lấy file thật.

## 3. Chuẩn bị trước khi viết lại lịch sử

Di chuyển lịch sử là thao tác ảnh hưởng đến commit hash và các ref. Trước khi bắt đầu, hãy chuẩn bị kỹ:

1. **Thông báo cho nhóm.** Xác định thời điểm migration, các branch/tag sẽ bị ảnh hưởng và người chịu trách nhiệm push lịch sử mới.
2. **Kiểm tra hỗ trợ LFS của remote.** Xác nhận máy chủ có bật Git LFS, tài khoản có quyền upload object và quota/dung lượng LFS còn đủ.
3. **Cài Git LFS.** Kiểm tra `git lfs version`, sau đó chạy `git lfs install` trong môi trường cần sử dụng.
4. **Dùng clone đầy đủ.** Nếu repository là shallow clone, hãy bổ sung lịch sử trước; migration chỉ có thể xử lý lịch sử và ref hiện có ở local.
5. **Fetch các ref cần migrate.** Cập nhật branch và tag liên quan. Với clone chỉ theo dõi một nhánh, cần fetch thêm các branch cần xử lý.
6. **Lưu công việc đang dở.** Commit hoặc stash thay đổi cần giữ và bảo đảm working tree sạch.
7. **Tạo bản sao lưu.** Giữ một mirror clone hoặc bundle chứa các ref và Git object trước migration; nếu repository đã có LFS object, sao lưu cả kho LFS object cần thiết.

Kiểm tra trạng thái và môi trường:

```bash
git status
git rev-parse --is-shallow-repository
git remote -v
git lfs version
git lfs env
```

Nếu repository vẫn shallow, có thể lấy đủ lịch sử trước khi migrate:

```bash
git fetch --unshallow origin
```

Chỉ dùng lệnh này khi remote có thể cung cấp lịch sử đầy đủ. Nếu remote hoặc clone nguồn cũng bị giới hạn, cần xử lý phạm vi lịch sử theo chính sách của máy chủ.

### Tạo bản sao lưu refs trước migration

Một bundle có thể lưu các ref và Git object đang có trong repository:

```bash
git bundle create ../before-lfs-migration.bundle --all
```

Bundle không bao gồm file working tree chưa commit và không phải bản sao của kho LFS object. Vì vậy, hãy lưu riêng các thay đổi chưa commit và sao lưu LFS object nếu repository đã dùng LFS trước đó. Một mirror clone từ remote cũng hữu ích để giữ trạng thái remote trước khi cập nhật, nhưng nó chỉ chứa các ref mà remote công bố.

## 4. Khảo sát file lớn trước khi migrate

Git LFS có lệnh `migrate info` để phân tích file trong lịch sử mà không viết lại commit:

```bash
git lfs migrate info --everything
```

Lệnh này giúp xem phân bố dung lượng file theo lịch sử và xác định nhóm file nên chuyển sang LFS. Có thể lọc theo mẫu:

```bash
git lfs migrate info --everything --include="*.psd,*.zip,*.mp4"
```

Bạn cũng có thể chỉ quan tâm file lớn hơn một ngưỡng:

```bash
git lfs migrate info --everything --above=50MB
```

Kết quả phân tích giúp xác định phạm vi migrate. Hãy kiểm tra kỹ file nào thực sự cần lưu trong LFS: không phải mọi file lớn đều cần chuyển, và một số file sinh tự động hoặc dữ liệu build có thể nên được loại khỏi repository bằng `.gitignore`.

`--everything` yêu cầu công cụ xét các ref local trong phạm vi hỗ trợ của lệnh, gồm branch, tag và remote-tracking ref đã fetch. Nó không trực tiếp sửa remote server. Nếu một branch hoặc tag chưa được fetch vào clone hiện tại, nó không thể được migrate ở local clone này.

## 5. Migrate file đã tồn tại trong lịch sử

### Migrate một loại file trên các ref local

Giả sử repository đã chứa file Photoshop, archive và video trong lịch sử. Muốn chuyển chúng trên mọi ref local đã lấy về:

```bash
git lfs migrate import --everything --include="*.psd,*.zip,*.mp4"
```

Ý nghĩa:

- `import`: chuyển nội dung blob Git thông thường thành LFS object và pointer.
- `--everything`: áp dụng migration cho các ref local được công cụ hỗ trợ, thay vì chỉ ref đang checkout.
- `--include`: chọn các đường dẫn/file pattern cần chuyển.

Các mẫu trong `--include` được phân tách bằng dấu phẩy. Có thể dùng mẫu theo tên file hoặc đường dẫn, ví dụ `"*.psd,assets/**/*.tif"`. Hãy đặt chuỗi trong dấu nháy để shell không tự mở rộng wildcard trước khi Git LFS nhận được.

### Chỉ migrate một ref cụ thể

Nếu chỉ muốn chuyển lịch sử của branch `main`, có thể giới hạn ref:

```bash
git lfs migrate import --include="*.psd,*.zip" --include-ref=refs/heads/main
```

`--include-ref` nhận tên ref cần migrate. Cách này phù hợp khi nhóm muốn thử nghiệm trên một branch hoặc triển khai theo từng đợt. Các branch/tag khác chưa được migrate có thể vẫn chứa blob lớn cũ.

### Loại trừ một số đường dẫn

Nếu mẫu include rộng nhưng có một số file cần giữ dạng Git blob, thêm `--exclude`:

```bash
git lfs migrate import --everything --include="*.zip,*.7z" --exclude="fixtures/*.zip"
```

Hãy kiểm tra quy tắc khớp với cấu trúc thư mục thật. Đừng dựa vào tên file hiển thị ở working tree nếu cùng một tên xuất hiện ở nhiều đường dẫn.

### Kiểm tra file được chuyển

Sau migration:

```bash
git lfs ls-files --all
git lfs migrate info --everything --include="*.psd,*.zip,*.mp4"
git status
```

`git lfs ls-files --all` liệt kê các file LFS trong lịch sử/ref mà lệnh có thể duyệt. Kiểm tra `.gitattributes` để xác nhận các pattern được ghi nhận. Có thể kiểm tra một file cụ thể:

```bash
git check-attr filter diff merge text -- assets/design.psd
```

Với file được track bằng LFS, kết quả thường cho thấy `filter: lfs`, `diff: lfs`, `merge: lfs` và `text: unset`.

## 6. Phạm vi ref và lý do cần chọn đúng

Mặc định, nếu không chỉ định ref hoặc `--everything`, `git lfs migrate import` thường chỉ migrate branch hiện tại. Điều này có thể phù hợp cho thử nghiệm, nhưng không đủ nếu blob lớn vẫn còn trong branch khác hoặc tag cũ.

| Phạm vi | Cách chỉ định | Hệ quả |
|---|---|---|
| Branch hiện tại | Không chỉ định ref bổ sung | Chỉ lịch sử reachable từ branch hiện tại được xử lý |
| Một ref cụ thể | `--include-ref=refs/heads/main` | Các ref ngoài phạm vi vẫn có thể chứa blob cũ |
| Nhiều ref local | `--include-ref` cho từng ref hoặc `--everything` | Phù hợp khi cần xử lý nhiều branch/tag đã fetch |

Nếu repository có nhiều branch và tag phát hành, hãy lập danh sách ref cần migrate trước. Một tag cũ trỏ đến commit chứa blob lớn có thể tiếp tục giữ blob đó trong lịch sử ngay cả khi branch chính đã được chuyển sang LFS.

`--everything` chỉ thao tác với ref local trong repository mà bạn chạy lệnh; nó không thể tự cập nhật branch trên máy chủ hoặc các fork của người khác. Remote chỉ thay đổi sau khi bạn push các ref mới.

## 7. Vì sao commit hash thay đổi?

Một commit Git được định danh bằng hash phụ thuộc vào tree, parent commit, thông tin tác giả/người commit và thông điệp. Khi blob lớn được thay bằng pointer, tree của commit thay đổi. Commit đó vì thế có hash mới. Các commit con kế thừa parent mới nên hash của chúng cũng thay đổi, kể cả khi nội dung file khác trong các commit đó không đổi.

Ví dụ trước migration:

```text
A---B---C---D  main
        |
        B chứa assets/design.psd dạng blob Git
```

Sau migration, lịch sử có thể thành:

```text
A---B'---C'---D'  main
```

`B'` chứa pointer LFS thay cho blob; `C'` và `D'` có parent mới nên cũng có mã commit mới. Các commit cũ không bị chỉnh sửa tại chỗ. Chúng trở thành object không còn được ref mới tham chiếu và có thể vẫn tồn tại trong bản sao local, reflog, backup hoặc remote cho đến khi được dọn theo chính sách lưu trữ.

### Hệ quả với tag và chữ ký

- Tag trỏ đến commit cũ có thể cần được cập nhật để trỏ đến commit mới tương ứng.
- Annotated tag có chữ ký không thể giữ nguyên chữ ký cũ nếu tag object hoặc đối tượng đích thay đổi; cần tạo lại và ký lại tag theo quy trình phát hành.
- Chữ ký commit của các commit được viết lại không còn xác minh hợp lệ cho commit mới; nếu chính sách yêu cầu signed commit, cần tạo lại chữ ký phù hợp.
- Release trên nền tảng lưu mã có thể vẫn tham chiếu SHA cũ. Kiểm tra release, pull request, CI và các tích hợp ngoài repository sau migration.

Không giả định mọi tag đều tự động giữ đúng ý nghĩa sau migration. Hãy xác định tag nào cần di chuyển, tag nào là mốc lịch sử bất biến và cách nhóm công bố phiên bản mới.

## 8. Đẩy LFS object và lịch sử mới lên remote

Sau khi migrate, repository local chứa pointer trong Git và LFS object tương ứng trong kho LFS local. Remote cần nhận cả LFS object lẫn ref mới.

Có thể đẩy toàn bộ LFS object được tham chiếu bởi các ref local:

```bash
git lfs push --all origin
```

Sau đó cập nhật các branch đã viết lại. Ví dụ nếu migrate toàn bộ branch local:

```bash
git push --force origin --all
```

Nếu các tag cũng được migrate và cần cập nhật trên remote:

```bash
git push --force origin --tags
```

Các lệnh force push thay thế lịch sử/ref trên remote. Chỉ chạy sau khi nhóm đã thống nhất thời điểm, xác nhận remote không có commit mới chưa được tích hợp và có quyền cập nhật các branch/tag liên quan. Nếu chỉ migrate một branch, hãy push đúng branch đó thay vì force-push mọi branch:

```bash
git lfs push --all origin
git push --force origin main
```

Nếu remote bật bảo vệ branch hoặc cấm force push, cần người quản trị điều chỉnh quy trình hoặc dùng cửa sổ bảo trì được phê duyệt. Không xóa bảo vệ một cách tùy tiện.

Git LFS thường cài pre-push hook để upload LFS object liên quan khi bạn push Git refs. `git lfs push --all` là bước tường minh hữu ích khi cần bảo đảm các LFS object được tham chiếu bởi toàn bộ refs local đã được upload trước khi công bố refs mới.

## 9. Ảnh hưởng đến đồng đội và các clone hiện có

Sau khi force push lịch sử đã migrate, clone của đồng đội vẫn chứa commit cũ. Nếu họ tiếp tục push branch cũ, merge lịch sử cũ vào branch mới hoặc tạo pull request dựa trên commit cũ, repository có thể xuất hiện lại lịch sử cũ hoặc phát sinh xung đột khó xử lý.

Trước migration, hãy yêu cầu mọi người:

- Commit hoặc sao lưu thay đổi local chưa chia sẻ.
- Tạm dừng push vào các branch nằm trong phạm vi migration.
- Ghi lại branch và commit local cần giữ.
- Không tạo thêm commit trên lịch sử cũ trong thời gian migration.

Sau khi migration hoàn tất, cách đơn giản và an toàn nhất với clone không có công việc local cần giữ là clone lại repository. Nếu cần giữ công việc local, hãy lưu patch hoặc branch riêng trước, sau đó đồng bộ branch mới từ remote và cherry-pick các commit chưa chia sẻ đã được kiểm tra.

Ví dụ cập nhật một clone đã có sẵn sau khi nhóm thông báo migration hoàn tất:

```bash
git fetch origin
git switch main
git reset --hard origin/main
```

Lệnh `reset --hard` sẽ bỏ thay đổi tracked chưa commit trong working tree và index của branch đó. Chỉ dùng sau khi đã backup hoặc lưu riêng mọi công việc cần giữ. Với nhiều branch, tag hoặc thay đổi local phức tạp, clone lại thường ít rủi ro hơn.

Các fork và remote khác không tự được cập nhật. Chủ sở hữu từng fork cần đồng bộ theo hướng dẫn của nhóm; nếu không, họ vẫn có thể giữ lịch sử cũ và đưa blob lớn trở lại khi gửi thay đổi.

## 10. Những gì migration không tự giải quyết

- **Không xóa ngay dữ liệu Git cũ khỏi mọi nơi.** Blob cũ có thể còn trong object database, reflog, backup, fork và remote cho đến khi được dọn.
- **Không tự sửa tất cả remote.** Lệnh migrate viết lại ref local; cần push các ref mới lên từng remote có liên quan.
- **Không bảo đảm remote có đủ LFS storage.** Máy chủ có thể từ chối upload do quota, giới hạn kích thước hoặc quyền truy cập.
- **Không tự cài Git LFS cho người khác.** Clone mới cần Git LFS để tải nội dung thật từ pointer.
- **Không tự chuyển file chưa được chọn.** File ngoài `--include` vẫn là Git blob bình thường.
- **Không làm thay đổi nội dung nghiệp vụ có chủ đích.** Tuy nhiên, commit hash đổi vì representation của file trong tree thay đổi.

Sau khi các ref mới đã được công bố và mọi clone được cập nhật, quản trị viên máy chủ có thể cần quy trình garbage collection riêng để giải phóng Git object cũ. Thời điểm và khả năng thu hồi dung lượng phụ thuộc nền tảng lưu trữ; LFS object cũng tiếp tục chiếm dung lượng LFS theo chính sách retention của máy chủ.

## 11. Quy trình migration mẫu cho một repository

Giả sử nhóm muốn chuyển mọi file `.psd` và `.mp4` trong toàn bộ branch/tag local sang LFS.

**Bước 1: Chuẩn bị clone và backup**

```bash
git status
git fetch --all --tags
git bundle create ../before-lfs-migration.bundle --all
git lfs install
```

Đảm bảo working tree sạch, repository không shallow và remote có hỗ trợ LFS. Nếu dùng clone single-branch, fetch thêm các branch cần migrate.

**Bước 2: Khảo sát phạm vi**

```bash
git lfs migrate info --everything --include="*.psd,*.mp4"
```

Xem danh sách file và dung lượng sẽ được chuyển. Xác nhận không chọn nhầm file cần giữ dạng Git blob.

**Bước 3: Migrate lịch sử local**

```bash
git lfs migrate import --everything --include="*.psd,*.mp4"
```

Lệnh này viết lại các ref local trong phạm vi `--everything` và cập nhật `.gitattributes`. Hãy chờ lệnh hoàn tất và đọc kỹ mọi thông báo.

**Bước 4: Xác minh pointer và LFS object**

```bash
git lfs ls-files --all
git lfs migrate info --everything --include="*.psd,*.mp4"
git check-attr filter diff merge text -- assets/design.psd
git status
```

Kiểm tra các file được liệt kê là LFS, `.gitattributes` có pattern phù hợp và working tree không chứa thay đổi ngoài dự kiến. Có thể dùng `git lfs fsck` để kiểm tra tính toàn vẹn các LFS object hiện có trong phạm vi lệnh hỗ trợ.

**Bước 5: Công bố lịch sử mới**

```bash
git lfs push --all origin
git push --force origin --all
git push --force origin --tags
```

Chỉ thực hiện force push khi đã có kế hoạch phối hợp và chấp thuận cập nhật các ref trên remote. Nếu chỉ migrate một branch, push branch đó thay vì dùng `--all`; nếu tag không nằm trong phạm vi hoặc cần giữ bất biến, xử lý theo chính sách tag của nhóm.

**Bước 6: Đồng bộ đội ngũ và pipeline**

Thông báo commit hash mới, yêu cầu clone mới hoặc đồng bộ branch local sau khi backup, cập nhật CI để cài Git LFS và kiểm tra LFS endpoint/quota. Kiểm tra lại clone sạch có thể checkout và tải được file thật.

## 12. Bài tập thực hành

Trong repository thử nghiệm, tạo file nhị phân giả lập có dung lượng đủ lớn, commit nó ở vài mốc khác nhau và tạo thêm một branch. Không dùng repository sản xuất cho bài tập.

1. Chạy `git lfs migrate info --everything --above=1MB` để khảo sát file lớn trong lịch sử.
2. Tạo một bản sao lưu bằng `git bundle create ../before-lfs.bundle --all`.
3. Chạy `git lfs migrate import --include="*.bin" --include-ref=refs/heads/main` để chỉ migrate branch `main`.
4. Dùng `git lfs ls-files --all`, `git log --oneline --all` và `git check-attr` để kiểm tra kết quả.
5. So sánh commit SHA trước và sau migration, giải thích vì sao các commit con cũng đổi hash.
6. Thử migrate tất cả ref trong một clone thử nghiệm khác bằng `--everything`, rồi xác định các branch/tag nào cần cập nhật trên remote.
7. Viết kế hoạch thông báo cho đồng đội, backup, force push và đồng bộ clone sau khi viết lại lịch sử.

Bạn hoàn thành bài tập khi phân biệt được `git lfs track` với `git lfs migrate import`, biết chọn phạm vi ref phù hợp và giải thích được ảnh hưởng của việc viết lại commit đối với remote, tag, pull request và clone của đồng đội.
