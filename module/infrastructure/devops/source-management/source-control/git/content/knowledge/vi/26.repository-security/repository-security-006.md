# Xóa dữ liệu nhạy cảm khỏi lịch sử và giới hạn đối với bản sao, cache, fork

Khi token, mật khẩu, khóa riêng hoặc dữ liệu nhạy cảm đã được commit vào Git, xóa file khỏi working tree hoặc tạo commit sửa lỗi là chưa đủ. Nội dung cũ vẫn có thể nằm trong các commit trước đó, tag, branch, clone của đồng đội, fork, cache CI và bản sao lưu.

Xử lý đúng cần hai việc diễn ra song song: **thu hồi hoặc thay thế bí mật đã lộ** và **loại bỏ nội dung khỏi các tham chiếu Git có thể kiểm soát**. Sau đó phải đánh giá những bản sao nằm ngoài repository chính. Viết lại lịch sử giúp giảm khả năng tiếp tục truy cập dữ liệu qua Git, nhưng không thể bảo đảm mọi bản sao đã biến mất.

## 1. Phản ứng đầu tiên khi phát hiện dữ liệu nhạy cảm

Nếu một credential đã xuất hiện trong commit, hãy coi nó là đã bị lộ. Ngay cả khi repository riêng tư, người có quyền truy cập, bot, CI runner, fork hoặc bản clone có thể đã đọc được dữ liệu.

Thứ tự ưu tiên:

1. **Thu hồi hoặc xoay vòng bí mật ngay.** Vô hiệu hóa token, mật khẩu, khóa API, khóa deploy hoặc chứng chỉ bị lộ; cấp giá trị mới qua hệ thống quản lý secret.
2. **Đánh giá phạm vi ảnh hưởng.** Xác định loại credential, quyền mà nó cấp, thời gian bị lộ, repository, branch, tag, PR/MR và các hệ thống đã truy cập.
3. **Hạn chế truy cập nếu cần.** Với repository công khai hoặc sự cố nghiêm trọng, phối hợp maintainer để tạm thời giới hạn quyền truy cập trong lúc xử lý.
4. **Lập kế hoạch làm sạch lịch sử.** Xác định refs cần viết lại, công cụ sử dụng, người thực hiện và cách đồng đội đồng bộ lại.
5. **Kiểm tra các bản sao ngoài repository chính.** Bao gồm fork, clone, cache, artifact, log và backup.

Không chờ viết lại lịch sử xong mới thu hồi credential. Lịch sử Git có thể được làm sạch, nhưng một token đã bị sao chép vẫn có thể được sử dụng cho đến khi bị vô hiệu hóa.

Nếu dữ liệu thuộc diện phải báo cáo sự cố, dữ liệu cá nhân hoặc bí mật của khách hàng, hãy làm theo quy trình ứng phó và lưu giữ bằng chứng của tổ chức. Không tự ý xóa log hoặc backup cần thiết cho điều tra.

## 2. Vì sao xóa file hoặc thêm .gitignore chưa đủ?

Git lưu commit như các đối tượng bất biến. Một commit cũ có thể tiếp tục chứa blob nhạy cảm ngay cả khi branch hiện tại đã xóa file.

Ví dụ:

~~~text
A---B---C---D  main
     |
     +-- B chứa secret.env
              C xóa secret.env
              D thêm .gitignore
~~~

Ở trạng thái hiện tại, file có thể không còn trong working tree. Tuy nhiên, commit B vẫn giữ nội dung file. Người có quyền đọc lịch sử có thể checkout B hoặc đọc blob trực tiếp.

| Thao tác | Điều thực sự xảy ra |
|---|---|
| Xóa file và commit | Tạo commit mới không còn file ở trạng thái hiện tại; commit cũ vẫn giữ blob |
| Thêm đường dẫn vào .gitignore | Ngăn file chưa được theo dõi được thêm tự động; không xóa commit cũ |
| Dùng git rm | Xóa file khỏi phiên bản hiện tại và staging area; không viết lại commit trước |
| Xóa branch local | Xóa một tham chiếu; object có thể còn trong reflog hoặc refs khác |
| Xóa branch trên remote | Xóa ref trên remote; không bảo đảm object, fork hoặc cache đã bị xóa |
| Xóa PR/MR hoặc đóng PR | Không bảo đảm mọi ref nội bộ, bản xem trước hay cache của nền tảng đã biến mất |

Muốn loại bỏ nội dung khỏi lịch sử được chia sẻ, phải viết lại các commit chứa nội dung đó và cập nhật các refs liên quan trên remote. Việc này làm thay đổi hash của commit và ảnh hưởng tất cả người đang dựa trên lịch sử cũ.

## 3. Xác định dữ liệu và phạm vi cần làm sạch

Trước khi chạy công cụ viết lại lịch sử, hãy lập danh sách:

- Giá trị nhạy cảm hoặc loại dữ liệu cần loại bỏ.
- Đường dẫn file từng chứa dữ liệu, kể cả tên cũ sau khi đổi tên.
- Commit, branch, tag hoặc ref khác có thể chứa nội dung.
- Nội dung có xuất hiện trong commit message, annotated tag message, issue, PR/MR hoặc log hay không.
- File có được lưu bằng Git LFS hay không.
- Repository có submodule, fork hoặc mirror riêng hay không.

Một số lệnh hỗ trợ điều tra theo đường dẫn:

~~~bash
git log --all --oneline -- config/production.env
git log --all --stat -- config/production.env
git rev-list --objects --all
~~~

Nếu cần tìm chuỗi cụ thể trong lịch sử, dùng công cụ secret scanning được tổ chức phê duyệt. Tránh đưa giá trị bí mật trực tiếp vào câu lệnh hoặc shell history, vì terminal, log lệnh và bản ghi CI có thể lưu lại đối số.

Có thể dùng lệnh tìm kiếm theo nội dung như <code>git log -S</code> trong môi trường kiểm soát, nhưng hãy truyền mẫu qua file hoặc công cụ phù hợp để không ghi bí mật vào lịch sử shell. Không in secret ra terminal được chia sẻ hoặc log tự động.

### Kiểm tra tên file đã thay đổi qua các commit

Nếu file từng được đổi tên, cần tìm mọi đường dẫn lịch sử có liên quan. Git filter theo một đường dẫn hiện tại có thể bỏ sót tên cũ.

~~~bash
git log --all --follow --name-status -- config/production.env
~~~

Tùy chọn <code>--follow</code> hữu ích khi truy vết một file qua các lần rename trên một đường lịch sử. Với repository có nhiều nhánh hoặc nhiều lần đổi tên, cần kiểm tra các refs và đường dẫn cũ riêng; không giả định một lệnh đã tìm hết mọi biến thể.

## 4. Chọn công cụ viết lại lịch sử

Công cụ thường được khuyến nghị để viết lại lịch sử Git là **git-filter-repo**. Công cụ này linh hoạt, nhanh và thay thế cho quy trình cũ dựa trên <code>git filter-branch</code>.

| Công cụ | Mục đích | Ghi chú |
|---|---|---|
| git-filter-repo | Lọc file, đường dẫn, nội dung blob, commit message và refs | Lựa chọn thường dùng cho làm sạch lịch sử |
| BFG Repo-Cleaner | Xóa file lớn hoặc thay thế chuỗi nhạy cảm trong lịch sử | Giao diện đơn giản cho một số tình huống; vẫn cần phối hợp cập nhật refs |
| git filter-branch | Viết lại lịch sử bằng shell filter | Cũ, chậm và dễ sai; tránh dùng cho quy trình mới |

Cài git-filter-repo theo hướng dẫn của hệ điều hành hoặc tổ chức. Kiểm tra:

~~~bash
git filter-repo --version
git filter-repo --help
~~~

Tùy phiên bản, có thể có tùy chọn hỗ trợ tình huống xóa dữ liệu nhạy cảm như <code>--sensitive-data-removal</code>. Hãy kiểm tra phiên bản đang cài và tài liệu đi kèm trước khi dùng. Các ví dụ dưới đây tập trung vào các tùy chọn lọc lịch sử phổ biến như <code>--invert-paths</code> và <code>--replace-text</code>.

## 5. Chuẩn bị bản clone sạch để viết lại

Không nên thử nghiệm trên bản clone duy nhất mà nhóm đang làm việc. Tạo một mirror clone mới để có đầy đủ refs và giữ repository đang sử dụng làm nguồn đối chiếu.

~~~bash
git clone --mirror https://example.com/team/app.git app-clean.git
cd app-clean.git
git rev-parse --is-shallow-repository
git show-ref
~~~

Mirror clone là bare repository chứa các refs được lấy từ remote. Kết quả <code>git rev-parse --is-shallow-repository</code> nên là <code>false</code> để có đủ lịch sử cần lọc. Nếu repository nguồn hoặc bản clone bị shallow, cần lấy đầy đủ lịch sử trước khi viết lại.

Trước khi chạy filter, xác nhận:

- Đúng URL và đúng repository.
- Đã có bản sao lưu an toàn theo chính sách ứng phó sự cố.
- Đã xác định tất cả branch, tag và refs có thể ghi.
- Đã thông báo cho người có quyền push để tạm dừng cập nhật.
- Có kế hoạch thay thế credential và xử lý fork/cache.
- Bản clone làm sạch là bản thử nghiệm, không phải working copy đang có thay đổi cá nhân.

<code>git-filter-repo</code> thường yêu cầu repository có vẻ là bản clone mới để tránh viết lại nhầm. Mirror clone mới là lựa chọn phù hợp. Tránh dùng <code>--force</code> chỉ để bỏ qua kiểm tra an toàn nếu chưa hiểu vì sao công cụ từ chối.

## 6. Xóa toàn bộ file nhạy cảm khỏi lịch sử

Nếu một file như <code>config/production.env</code> đã chứa token hoặc mật khẩu, có thể loại bỏ đường dẫn đó khỏi mọi commit:

~~~bash
git filter-repo --invert-paths --path config/production.env
~~~

Tùy chọn <code>--path</code> chọn đường dẫn cần lọc; <code>--invert-paths</code> giữ phần còn lại và loại đường dẫn được chỉ định khỏi lịch sử.

Nếu file từng nằm ở nhiều vị trí, liệt kê tất cả đường dẫn đã biết:

~~~bash
git filter-repo --invert-paths --path config/production.env --path deploy/production.env --path old/config.env
~~~

Nếu muốn loại bỏ cả một thư mục chứa dữ liệu nhạy cảm:

~~~bash
git filter-repo --invert-paths --path private-config/
~~~

Sau khi lọc, file có thể không còn trong các commit cũ. Nếu ứng dụng vẫn cần cấu hình đó, thay bằng cơ chế quản lý secret ngoài Git, chẳng hạn secret manager, biến môi trường của hệ thống triển khai hoặc file mẫu không chứa giá trị thật.

### Đừng quên các đường dẫn cũ

Nếu file đã được đổi tên, cần cung cấp mọi tên cũ cho bộ lọc. Nếu chỉ lọc đường dẫn hiện tại, blob ở đường dẫn cũ vẫn có thể tồn tại trong lịch sử.

Kiểm tra các commit và refs trước khi chạy. Không dựa vào trạng thái working tree hiện tại để suy ra toàn bộ đường dẫn lịch sử.

## 7. Thay thế một giá trị bí mật trong nội dung file

Đôi khi chỉ một chuỗi nhạy cảm xuất hiện trong file cấu hình hoặc source code, trong khi vẫn cần giữ phần còn lại của file. Có thể dùng <code>--replace-text</code> với file biểu thức thay thế.

Tạo file biểu thức ở vị trí được bảo vệ, bên ngoài repository đang lọc. Ví dụ định dạng:

~~~text
literal:OLD_SECRET_VALUE==>***REMOVED***
~~~

<code>OLD_SECRET_VALUE</code> là placeholder, không phải giá trị thật. Trong file thực tế, thay nó bằng chuỗi cần loại bỏ. Giới hạn quyền đọc file biểu thức và không commit file đó.

Chạy:

~~~bash
git filter-repo --replace-text ../redact-expressions.txt
~~~

Công cụ thay chuỗi được chỉ định trong nội dung blob qua lịch sử. Sau đó, kiểm tra các file và commit đã được viết lại bằng secret scanner đã được phê duyệt.

Nếu chuỗi nhạy cảm xuất hiện trong commit message hoặc tag message, dùng tùy chọn lọc message riêng:

~~~bash
git filter-repo --replace-message ../redact-expressions.txt
~~~

Một số định dạng dữ liệu nhị phân không thể được xử lý như văn bản thông thường. Với file binary chứa dữ liệu nhạy cảm, nên loại bỏ đường dẫn hoặc thay thế file bằng một phiên bản sạch, sau đó xử lý cả LFS object nếu có.

### Bảo vệ file biểu thức thay thế

- Không đưa secret thật vào ví dụ, ticket, chat hoặc log.
- Không commit file biểu thức vào repository.
- Giới hạn quyền đọc file và xóa theo quy trình sau khi hoàn tất.
- Tránh truyền secret dưới dạng đối số lệnh vì shell history có thể lưu lại.
- Không dùng giá trị đã bị thu hồi như thể nó không còn nhạy cảm; vẫn xử lý các bản sao theo quy định.

## 8. Dữ liệu nhạy cảm trong commit message, tag và metadata

Secret có thể xuất hiện ngoài nội dung file:

- Commit message.
- Annotated tag message.
- Tên branch hoặc tag.
- Ghi chú Git notes.
- Nội dung được nhúng trong file binary.
- Metadata hoặc URL có chứa credential.

<code>--replace-message</code> có thể xử lý commit message và tag message theo biểu thức thay thế. Đối với tên ref, cần đổi hoặc xóa ref có tên nhạy cảm. Với Git notes hoặc metadata khác, cần xác định đúng loại ref và công cụ lọc phù hợp.

Việc viết lại commit có thể làm thay đổi hash của toàn bộ commit con. Chữ ký GPG/SSH của commit hoặc annotated tag cũ không còn xác thực cho nội dung đã viết lại. Nếu dự án yêu cầu ký, cần tạo chữ ký mới theo quy trình phát hành.

Đừng mặc định chỉ lọc file là đủ. Hãy kiểm tra mọi vị trí mà secret có thể xuất hiện và mọi refs có thể dẫn tới object chứa dữ liệu đó.

## 9. Xem lại kết quả trước khi cập nhật remote

Sau khi lọc, kiểm tra refs và lịch sử trong bản clone sạch:

~~~bash
git show-ref
git log --all --oneline --decorate
git rev-list --objects --all
~~~

Xác minh đường dẫn đã xóa không còn trong lịch sử được tham chiếu:

~~~bash
git log --all -- config/production.env
git rev-list --objects --all
~~~

Đối với secret dạng chuỗi, dùng secret scanner trên tất cả refs sau khi viết lại. Tránh in giá trị bí mật trong output. Kiểm tra cả commit message, tag message và các file được đổi tên.

Không thể kết luận chỉ từ việc <code>git status</code> sạch hoặc file không còn ở branch hiện tại. Mục tiêu là kiểm tra toàn bộ refs và object có thể truy cập trong repository đã lọc.

Nếu phát hiện còn commit hoặc ref chứa dữ liệu, sửa quy tắc lọc và chạy lại trên bản clone sạch. Không push bản làm sạch chưa được xác minh.

## 10. Cập nhật remote sau khi viết lại lịch sử

Viết lại local không tự thay đổi remote. Cần cập nhật các refs trên server để các branch và tag không còn trỏ tới lịch sử cũ.

Trước tiên, lưu URL remote vì git-filter-repo có thể xóa cấu hình remote như một biện pháp an toàn:

~~~bash
git remote -v
~~~

Nếu remote <code>origin</code> đã bị xóa sau khi lọc, thêm lại:

~~~bash
git remote add origin https://example.com/team/app.git
~~~

Trong một mirror repository đã được kiểm tra kỹ, có thể đồng bộ các refs bằng:

~~~bash
git push --force --mirror origin
~~~

**Cẩn trọng:** <code>--mirror</code> đồng bộ toàn bộ refs và có thể xóa refs trên remote không còn tồn tại trong bản clone. Chỉ dùng khi đã kiểm kê refs, phối hợp với quản trị viên và hiểu chính sách của máy chủ. Một số nền tảng có refs nội bộ cho Pull Request/Merge Request mà người dùng không được phép ghi; các refs này có thể cần nhà cung cấp xử lý.

Nếu không dùng mirror push, có thể cập nhật các branch và tag được phép một cách tường minh, nhưng phải bảo đảm không còn refs cũ nào giữ object nhạy cảm. Force push có thể bị branch protection chặn; maintainer cần điều phối thay đổi chính sách trong thời gian bảo trì theo quy trình của tổ chức.

Không dùng <code>--force</code> một cách tùy tiện trên repository đang có người push. Tạm dừng cập nhật, thông báo thời điểm thay đổi và chỉ cho một người chịu trách nhiệm thực hiện để tránh ghi đè commit mới của đồng đội.

## 11. Những giới hạn của remote, PR/MR và cache của nền tảng

Sau khi force push, branch và tag có thể đã trỏ tới lịch sử mới. Điều đó không bảo đảm nền tảng đã xóa ngay mọi bản sao nội bộ.

Nền tảng Git có thể lưu:

- Ref nội bộ cho Pull Request/Merge Request.
- Diff hoặc trang xem file đã được cache.
- Archive tải về, raw file cache hoặc bản dựng.
- Object cũ chưa được garbage collection.
- Bản sao phục vụ tìm kiếm, phân tích hoặc replication.

Một số refs nội bộ không thể được cập nhật bằng Git push thông thường. Nếu secret đã xuất hiện trong PR/MR, commit view, raw URL hoặc repository công khai, hãy liên hệ bộ phận quản trị hoặc bộ phận hỗ trợ của nhà cung cấp để yêu cầu xử lý cache và refs nội bộ theo quy trình của họ.

Đừng giả định xóa PR, đóng PR hoặc force push sẽ tự xóa mọi bản xem trước. Ghi lại phạm vi đã yêu cầu xử lý và xác minh theo hướng dẫn của nền tảng.

## 12. Fork và mirror là những bản sao độc lập

Fork là một repository riêng có thể giữ branch và commit cũ. Khi repository gốc được viết lại lịch sử, fork không tự động bị làm sạch.

Nếu secret đã đi vào fork:

1. Xác định các fork nội bộ và bên ngoài có thể truy cập.
2. Thông báo cho chủ sở hữu fork theo quy trình ứng phó sự cố.
3. Yêu cầu họ làm sạch lịch sử hoặc xóa fork nếu không cần giữ.
4. Liên hệ nhà cung cấp nếu cần xử lý fork network, refs ẩn hoặc bản sao mà chủ sở hữu không thể tự sửa.
5. Kiểm tra các mirror repository và bản sao được đồng bộ sang hệ thống khác.

Một fork có thể tiếp tục cung cấp commit cũ ngay cả khi branch chính đã sạch. Nếu người dùng tạo branch mới từ lịch sử cũ rồi mở PR lại, commit chứa dữ liệu có thể quay trở lại repository gốc.

Vì vậy, sau khi làm sạch, cần thông báo rõ rằng không được merge hoặc push lịch sử cũ trở lại. Contributor nên tạo clone mới từ repository đã làm sạch.

## 13. Clone của đồng đội và máy phát triển

Mỗi clone là một bản sao độc lập của object database. Force push trên server không xóa commit cũ trong thư mục <code>.git</code> của các máy đã clone.

Cách an toàn nhất sau khi viết lại lịch sử là:

1. Tạm dừng push từ các clone cũ.
2. Bảo toàn công việc chưa commit theo cách an toàn, không sao chép lại secret.
3. Clone lại repository đã được làm sạch.
4. Chuyển các thay đổi hợp lệ sang clone mới bằng patch hoặc cherry-pick đã kiểm tra.
5. Không merge branch cũ vào branch mới nếu commit cũ có thể đưa secret trở lại.
6. Xóa clone cũ và các bản sao cục bộ theo chính sách của tổ chức.

Nếu buộc phải giữ clone cũ, cần hiểu rằng fetch không tự xóa object cũ khỏi object database. Reset branch local cũng không bảo đảm xóa reflog hoặc object không còn được tham chiếu. Tạo clone mới thường dễ kiểm soát hơn.

Với công việc chưa commit, hãy kiểm tra patch hoặc bản sao trước khi chuyển. Nếu patch chứa secret, phải làm sạch patch trước; không gửi patch qua email, chat hoặc ticket không được phép.

## 14. Làm sạch reflog và object không còn được tham chiếu ở local

Sau khi refs local đã được viết lại, commit cũ có thể vẫn còn trong reflog hoặc object database. Trong một clone đã được xác nhận không còn công việc cần giữ, có thể hết hạn reflog và prune object không còn được tham chiếu:

~~~bash
git reflog expire --expire=now --all
git gc --prune=now
~~~

Các lệnh này ảnh hưởng repository local hiện tại. Chúng không xóa clone của người khác, fork, cache của nhà cung cấp hoặc object trên server từ xa.

Chỉ chạy trong bản clone đã được kiểm tra và có bản sao lưu phù hợp. Không dùng lệnh dọn object để thay thế bước viết lại refs và làm sạch remote.

Để kiểm tra trạng thái local, có thể chạy:

~~~bash
git fsck --full
git show-ref
~~~

<code>git fsck</code> hỗ trợ kiểm tra tính nhất quán của object database; nó không phải công cụ xác nhận mọi bản sao của secret đã biến mất khỏi hệ thống.

## 15. Cache CI, artifact, log và backup

Dữ liệu nhạy cảm có thể được sao chép ra ngoài Git trong quá trình build và triển khai.

| Nơi có thể lưu bản sao | Việc cần kiểm tra |
|---|---|
| CI workspace và cache | Xóa hoặc làm mất hiệu lực cache chứa .git, file cấu hình hoặc secret |
| Build artifact | Xác định archive, package hoặc binary có nhúng file nhạy cảm không |
| Log pipeline | Kiểm tra secret có bị in ra output, debug log hoặc trace không |
| Container image/layer | Kiểm tra secret có nằm trong layer cũ, image registry hoặc build cache không |
| Release asset | Kiểm tra file tải về có chứa credential hoặc cấu hình nhạy cảm không |
| Backup và snapshot | Áp dụng chính sách hạn chế truy cập, thời hạn lưu giữ và xóa an toàn |
| IDE và công cụ phát triển | Kiểm tra local history, file tạm, crash dump hoặc workspace cache |
| Package registry và artifact store | Kiểm tra package đã phát hành có chứa dữ liệu không |

Xóa một CI cache có thể không xóa artifact đã được publish. Xóa artifact mới nhất cũng không nhất thiết xóa phiên bản cũ hoặc bản sao ở mirror registry.

Không tự ý xóa backup có nghĩa vụ lưu giữ. Hãy phối hợp với nhóm bảo mật, vận hành hoặc pháp chế để áp dụng chính sách lưu giữ, giới hạn quyền truy cập và thời điểm hủy phù hợp.

## 16. Trường hợp file được quản lý bằng Git LFS

Nếu file nhạy cảm được lưu bằng Git LFS, Git repository chỉ chứa pointer; nội dung thật nằm trong LFS storage.

Lọc hoặc xóa pointer khỏi Git history không nhất thiết xóa LFS object đã upload lên server. Object có thể vẫn tồn tại trong LFS storage hoặc cache, kể cả khi không còn ref Git nào trỏ tới nó.

Cần thực hiện thêm:

- Xác định OID LFS và các pointer từng tham chiếu tới object.
- Kiểm tra object có còn trong local LFS cache, CI cache hoặc LFS server không.
- Liên hệ quản trị viên/nền tảng để xử lý object LFS phía server theo khả năng hỗ trợ.
- Kiểm tra các fork hoặc clone có thể tải object bằng pointer cũ.
- Không coi <code>git lfs prune</code> là lệnh xóa object trên server; lệnh này chỉ dọn cache local.

Nếu file LFS chứa secret, hãy thu hồi secret trước và làm sạch cả pointer history lẫn bản lưu LFS theo quy trình của dịch vụ.

## 17. Submodule và repository liên quan

Nếu dữ liệu nhạy cảm nằm trong repository submodule, việc lọc repository cha không tự lọc lịch sử submodule. Git repository cha chỉ lưu gitlink trỏ tới commit của repository con.

Cần xử lý repository chứa dữ liệu thực:

1. Xác định submodule nào chứa file hoặc secret.
2. Làm sạch lịch sử trong repository submodule theo quy trình riêng.
3. Cập nhật gitlink trong repository cha tới commit mới của submodule.
4. Xử lý clone, fork và cache của repository submodule.
5. Kiểm tra các script hoặc pipeline có tải submodule từ URL cũ hay không.

Tương tự, nếu secret được sao chép giữa nhiều repository, phải xử lý từng repository và nơi lưu bản sao. Làm sạch một repository không làm sạch các repository liên quan.

## 18. Hướng dẫn đồng đội sau khi lịch sử đã được viết lại

Sau khi maintainer thông báo lịch sử đã được làm sạch và remote đã được cập nhật, các thành viên cần đồng bộ theo hướng dẫn cụ thể.

**Khuyến nghị: clone mới**

~~~bash
git clone https://example.com/team/app.git app-clean
cd app-clean
git status
git log --all --oneline --decorate
~~~

Sau đó đưa các thay đổi hợp lệ chưa được chia sẻ sang clone mới. Không copy nguyên thư mục <code>.git</code> từ clone cũ và không merge branch cũ có commit chứa secret.

**Nếu phải giữ clone cũ**

Hãy dừng push, lưu công việc chưa commit đã được kiểm tra, fetch refs mới và tạo nhánh làm việc mới từ lịch sử sạch. Chỉ cherry-pick commit an toàn sau khi xác nhận commit đó không chứa secret trong chính nó hoặc tổ tiên được đưa trở lại. Sau khi hoàn tất, xóa clone cũ theo chính sách.

Thông báo cho đồng đội cần bao gồm:

- Thời điểm lịch sử được viết lại.
- Các branch/tag đã được cập nhật.
- Yêu cầu clone mới hoặc quy trình đồng bộ.
- Danh sách fork/mirror cần xử lý.
- Lệnh hoặc quy trình xác minh.
- Người liên hệ nếu phát hiện commit cũ hoặc secret xuất hiện lại.

## 19. Xác minh sau khi làm sạch

Kiểm tra phải bao phủ cả Git refs lẫn hệ thống lưu trữ liên quan.

Trong clone sạch:

~~~bash
git rev-parse --is-shallow-repository
git show-ref
git log --all --oneline --decorate
git rev-list --objects --all
~~~

Sau đó:

- Chạy secret scanner trên toàn bộ refs.
- Kiểm tra các đường dẫn cũ và mới đã biết.
- Kiểm tra commit message, tag message và Git notes nếu có.
- Kiểm tra branch/tag trên remote.
- Yêu cầu nhà cung cấp xử lý PR/MR refs hoặc cache mà người dùng không thể cập nhật.
- Xác minh fork, mirror và CI cache đã được xử lý theo phạm vi cho phép.
- Thử credential mới và xác nhận credential cũ đã bị thu hồi.

Lệnh <code>git ls-remote --heads --tags origin</code> giúp xem branch/tag đang công khai trên remote, nhưng không chứng minh server đã xóa mọi object cũ hoặc cache nội bộ.

Không in lại secret trong báo cáo xác minh. Chỉ ghi trạng thái, phạm vi, hash commit hoặc mã sự cố theo quy định bảo mật.

## 20. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
|---|---|---|
| Chỉ xóa file ở commit mới | Secret vẫn nằm trong commit cũ | Viết lại toàn bộ lịch sử liên quan |
| Chỉ thêm .gitignore | Không tác động tới blob đã commit | Xóa khỏi history và thêm rule ngăn tái diễn |
| Chỉ force push branch main | Tag, branch khác hoặc ref khác vẫn có thể giữ commit cũ | Kiểm kê và xử lý tất cả refs có thể ghi |
| Không thu hồi token | Người đã sao chép token vẫn có thể sử dụng | Rotate/revoke trước khi làm sạch history |
| Nghĩ fork tự cập nhật theo upstream | Fork vẫn có thể chứa commit cũ | Xử lý từng fork và liên hệ nền tảng khi cần |
| Cho đồng đội tiếp tục push từ clone cũ | Lịch sử chứa secret có thể được đưa trở lại | Tạm dừng push, clone mới và chuyển commit an toàn |
| Chỉ xóa Git pointer của LFS | LFS object thật có thể còn trên server | Xử lý riêng LFS storage và cache |
| Chạy git gc trên một máy rồi kết luận đã xóa hết | Chỉ dọn object local của máy đó | Kiểm tra server, fork, CI, backup và clone |
| In secret vào lệnh hoặc ticket | Tạo thêm bản sao không cần thiết | Dùng scanner/file bảo vệ và báo cáo không chứa giá trị bí mật |
| Dùng --mirror mà không kiểm kê refs | Có thể xóa hoặc ghi đè refs ngoài dự kiến | Kiểm tra refs và phối hợp maintainer trước khi push |

## 21. Ngăn sự cố tái diễn

Sau khi xử lý, bổ sung biện pháp phòng ngừa:

- Lưu credential trong secret manager hoặc biến môi trường được bảo vệ.
- Commit file mẫu như .env.example chỉ chứa tên biến, không chứa giá trị thật.
- Thêm file nhạy cảm vào .gitignore nếu chúng không thuộc repository.
- Bật secret scanning hoặc pre-commit/pre-receive scanning theo chính sách tổ chức.
- Bảo vệ branch quan trọng và giới hạn quyền push.
- Hướng dẫn contributor xử lý khi phát hiện secret đã stage hoặc commit.
- Giới hạn quyền của token theo phạm vi và thời hạn cần thiết.
- Xoay vòng credential định kỳ hoặc khi có dấu hiệu lộ.
- Kiểm tra CI logs, artifact và cache để tránh vô tình xuất bản secret.

<code>.gitignore</code> giúp ngăn một số file được thêm mới, nhưng không phải cơ chế quản lý bí mật. Secret vẫn cần được cấp phát, lưu trữ, thu hồi và kiểm soát quyền ở hệ thống phù hợp.

## 22. Quy trình ứng phó mẫu

Giả sử một file <code>config/prod.env</code> chứa token truy cập production đã được push lên remote.

**Bước 1 — Thu hồi token**

Vô hiệu hóa token cũ, cấp token mới trong secret manager và kiểm tra log sử dụng để đánh giá hoạt động bất thường.

**Bước 2 — Tạm dừng push**

Thông báo cho nhóm ngừng push vào repository trong thời gian viết lại lịch sử. Ghi nhận branch/tag/PR và fork có liên quan.

**Bước 3 — Tạo mirror clone sạch**

~~~bash
git clone --mirror https://example.com/team/app.git app-clean.git
cd app-clean.git
git rev-parse --is-shallow-repository
git show-ref
~~~

**Bước 4 — Loại bỏ file khỏi lịch sử**

~~~bash
git filter-repo --invert-paths --path config/prod.env
~~~

Nếu file từng có tên khác, thêm từng đường dẫn lịch sử vào lệnh.

**Bước 5 — Kiểm tra kết quả**

~~~bash
git log --all -- config/prod.env
git show-ref
git rev-list --objects --all
~~~

Chạy secret scanner trên toàn bộ refs và xác minh các vị trí khác có thể chứa token.

**Bước 6 — Cập nhật remote**

Nếu filter đã xóa remote <code>origin</code>, thêm lại URL đã xác minh. Sau khi kiểm kê refs và được maintainer cho phép, đồng bộ các refs đã làm sạch. Với mirror workflow, <code>git push --force --mirror origin</code> có thể được dùng khi đã hiểu phạm vi refs và tác động xóa/ghi đè.

**Bước 7 — Xử lý các bản sao**

Liên hệ nền tảng để xử lý cache và refs nội bộ; yêu cầu fork/mirror được làm sạch; xóa hoặc thay thế CI cache/artifact có chứa file; áp dụng chính sách cho backup.

**Bước 8 — Đồng bộ lại thành viên**

Yêu cầu clone mới. Chuyển các thay đổi hợp lệ đã được kiểm tra; không merge lịch sử cũ trở lại.

**Bước 9 — Xác minh và đóng sự cố**

Chạy scanner, kiểm tra remote refs, xác nhận credential cũ không còn hiệu lực và ghi lại các hệ thống đã xử lý. Báo cáo không chứa giá trị bí mật.

## 23. Checklist xử lý dữ liệu nhạy cảm trong Git

- [ ] Đã thu hồi hoặc thay thế credential bị lộ.
- [ ] Đã xác định loại dữ liệu và phạm vi ảnh hưởng.
- [ ] Đã kiểm tra mọi branch, tag, commit và đường dẫn cũ.
- [ ] Đã kiểm tra commit message, tag message, PR/MR và notes khi cần.
- [ ] Đã tạo mirror clone đầy đủ và bản sao lưu an toàn.
- [ ] Đã dùng git-filter-repo hoặc công cụ phù hợp để viết lại lịch sử.
- [ ] Đã xác minh kết quả bằng secret scanner trên toàn bộ refs.
- [ ] Đã cập nhật remote refs theo kế hoạch được duyệt.
- [ ] Đã yêu cầu nhà cung cấp xử lý cache hoặc refs nội bộ nếu cần.
- [ ] Đã kiểm tra fork, mirror, clone, CI cache, artifact, log và backup.
- [ ] Đã xử lý riêng Git LFS hoặc submodule nếu có.
- [ ] Đã hướng dẫn đồng đội clone mới và tránh đưa lịch sử cũ trở lại.
- [ ] Đã xác nhận credential cũ bị vô hiệu hóa và biện pháp phòng ngừa được bổ sung.

## 24. Những điểm cần ghi nhớ

- Secret đã commit phải được coi là đã lộ; thu hồi hoặc xoay vòng credential trước khi làm sạch lịch sử.
- Xóa file ở commit mới hoặc thêm .gitignore không loại bỏ blob trong commit cũ.
- git-filter-repo là công cụ phổ biến để xóa đường dẫn hoặc thay thế nội dung trong lịch sử.
- Viết lại lịch sử làm thay đổi commit hash, có thể làm mất hiệu lực chữ ký và cần force update refs.
- Phải kiểm tra tất cả branch, tag và refs có thể ghi; mirror push có thể xóa refs trên remote nên cần kiểm kê.
- Force push không xóa tự động fork, clone, cache, PR/MR refs, artifact, log hoặc backup.
- Git LFS object và repository submodule cần được xử lý riêng nếu chứa dữ liệu nhạy cảm.
- Clone mới thường là cách đáng tin cậy nhất để đồng đội bắt đầu từ lịch sử sạch.
- Secret scanner và quy trình quản lý credential giúp giảm nguy cơ lặp lại sự cố.

Làm sạch lịch sử Git là một phần của ứng phó sự cố, không phải cách thu hồi bí mật. Hãy thu hồi credential, viết lại các refs có thể kiểm soát, phối hợp xử lý fork/cache/bản sao và xác minh sau cùng. Chỉ khi các bước này được thực hiện cùng nhau, nguy cơ dữ liệu nhạy cảm tiếp tục bị truy cập mới được giảm xuống đáng kể.

