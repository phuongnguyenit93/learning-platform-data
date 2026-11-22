# Thu hồi bí mật bị lộ trước khi xử lý lịch sử

Khi một API key, mật khẩu, token truy cập hoặc private key xuất hiện trong commit Git, cần xử lý như một sự cố bảo mật. Việc xóa dòng chứa bí mật khỏi file hoặc tạo một commit mới không làm thông tin cũ biến mất khỏi lịch sử. Bất kỳ ai có thể đọc commit cũ vẫn có thể lấy lại giá trị đã lộ và thử sử dụng nó.

Thứ tự xử lý rất quan trọng: **vô hiệu hóa hoặc thu hồi bí mật bị lộ, cấp và triển khai thông tin xác thực thay thế, sau đó mới làm sạch lịch sử Git và phối hợp cập nhật các bản sao**. Nếu chỉ viết lại lịch sử mà không thu hồi credential, người đã lấy được giá trị cũ vẫn có thể sử dụng nó. Nếu chỉ thu hồi credential mà không làm sạch lịch sử, bí mật vẫn còn trong repository, bản clone, cache hoặc artifact và có thể tiếp tục bị phát hiện.

Bài này thuộc chương **Bảo mật kho mã** của module **SOURCE_CONTROL_GIT**. Module hướng dẫn Git từ working tree, staging area, commit và lịch sử đến branch, merge, rebase, remote và tag; đồng thời rèn cách cộng tác qua nhánh, giải quyết xung đột, truy tìm thay đổi và khôi phục thao tác sai mà vẫn bảo toàn lịch sử quan trọng. Nội dung tập trung vào quy trình ứng phó khi bí mật đã bị commit hoặc chia sẻ qua repository.

## 1. Điều gì được xem là bí mật bị lộ?

Bí mật là thông tin có thể cấp quyền truy cập hoặc tiết lộ dữ liệu mà người không được phép không nên biết. Trong dự án phần mềm, các loại thường gặp gồm:

- API key của dịch vụ bên thứ ba.
- Access token, refresh token, personal access token hoặc deploy token.
- Mật khẩu database, tài khoản dịch vụ hoặc tài khoản quản trị.
- Private key SSH, TLS hoặc khóa ký.
- Client secret, webhook secret và signing secret.
- Connection string chứa thông tin xác thực.
- File cấu hình môi trường có mật khẩu hoặc token thật.
- Credential của cloud, registry, CI/CD hoặc hệ thống giám sát.

Không phải mọi chuỗi trông giống token đều là credential đang hoạt động. Tuy nhiên, khi chưa xác minh được phạm vi và trạng thái, hãy bảo vệ giá trị đó như một bí mật thực sự. Không dán secret vào issue, pull request, chat, log hoặc lệnh shell chỉ để nhờ người khác kiểm tra.

## 2. Vì sao phải thu hồi trước khi viết lại lịch sử?

Git lưu các snapshot theo commit. Nếu một commit cũ chứa bí mật, commit đó có thể vẫn truy cập được qua nhánh, tag, pull request, reflog hoặc bản clone của thành viên. Xóa file trong commit mới chỉ thay đổi snapshot mới nhất.

Giả sử lịch sử như sau:

~~~text
A: add config/prod.env (có credential)
|
B: update application
|
C: remove config/prod.env
~~~

Ở commit C, file không còn trong snapshot hiện tại. Nhưng commit A vẫn chứa credential. Nếu người khác checkout A hoặc xem diff của commit đó, họ vẫn có thể đọc được giá trị cũ.

Viết lại lịch sử có thể làm commit A và các commit con mang hash mới, nhưng không tự làm credential cũ mất hiệu lực. Một bản clone cũ hoặc bản sao trong cache vẫn có thể chứa nội dung đó. Vì vậy:

1. Thu hồi hoặc vô hiệu hóa credential bị lộ.
2. Cấp credential mới và cập nhật hệ thống sử dụng nó.
3. Xác định phạm vi lộ và kiểm tra hoạt động đáng ngờ.
4. Sau đó mới làm sạch lịch sử và các bản sao liên quan.

Đây là thứ tự giúp giảm nguy cơ credential tiếp tục bị sử dụng trong lúc nhóm đang xử lý repository.

## 3. Phân biệt thu hồi và xoay vòng credential

Hai hành động thường đi cùng nhau nhưng có mục đích khác nhau:

| Hành động | Ý nghĩa | Ví dụ |
|---|---|---|
| Thu hồi / vô hiệu hóa (revoke) | Làm credential cũ không còn được chấp nhận | Disable API key, revoke token, thu hồi chứng thư |
| Xoay vòng (rotate) | Tạo credential thay thế và chuyển hệ thống sang dùng giá trị mới | Tạo API key mới, đổi mật khẩu database, thay private key |

Với một số dịch vụ, bạn có thể tạo credential mới, triển khai nó cho ứng dụng rồi thu hồi credential cũ ngay sau khi xác nhận hoạt động. Nếu có dấu hiệu đang bị khai thác, ưu tiên vô hiệu hóa credential bị lộ theo quy trình ứng phó sự cố, kể cả khi việc đó cần phối hợp để khôi phục dịch vụ.

Ví dụ theo từng loại:

- **API key hoặc token:** disable hoặc revoke giá trị cũ trong trang quản trị nhà cung cấp; tạo key mới với quyền tối thiểu cần thiết.
- **Mật khẩu database:** đổi mật khẩu hoặc tạo tài khoản dịch vụ mới; cập nhật secret store, biến môi trường và workload liên quan.
- **Private key:** thay cặp khóa, cập nhật public key hoặc chứng thư ở các hệ thống tin cậy, thu hồi khóa/chứng thư cũ nếu cơ chế hỗ trợ.
- **Credential cloud:** vô hiệu hóa access key bị lộ, tạo key thay thế hoặc chuyển workload sang identity ngắn hạn.
- **Webhook/signing secret:** thay secret ở cả bên gửi và bên xác minh, sau đó xác nhận chữ ký mới được chấp nhận.

Không đưa credential mới vào Git để thay credential cũ. Lưu nó trong secret manager, kho cấu hình được bảo vệ hoặc cơ chế cấp credential của nền tảng triển khai.

## 4. Những việc cần làm ngay khi phát hiện bí mật trong commit

Khi phát hiện một secret, hãy bắt đầu bằng các bước sau:

1. Báo sự cố qua kênh bảo mật nội bộ hoặc người phụ trách hệ thống.
2. Xác định loại credential, nhà cung cấp, quyền được cấp và môi trường đang sử dụng.
3. Thu hồi hoặc vô hiệu hóa credential cũ; cấp và triển khai giá trị thay thế.
4. Kiểm tra log truy cập, audit log, billing hoặc hoạt động bất thường kể từ thời điểm credential có thể đã bị lộ.
5. Ghi lại repository, commit hash, branch/tag, đường dẫn file và thời điểm phát hiện; không sao chép giá trị secret vào báo cáo.
6. Tạm dừng push hoặc merge vào các nhánh bị ảnh hưởng trong thời gian chuẩn bị làm sạch lịch sử.
7. Xác định repository đã được push đến remote nào, ai có quyền truy cập và có fork hoặc bản mirror nào liên quan.

Nếu secret chỉ được commit local và chưa từng rời khỏi máy, phạm vi tiếp xúc có thể nhỏ hơn. Dù vậy, cần xác minh backup, log, đồng bộ thư mục và công cụ khác có thể đã sao chép dữ liệu. Quyết định có phải rotate hay không cần dựa trên chính sách bảo mật và bằng chứng về phạm vi tiếp xúc; với credential có khả năng đã chia sẻ, hãy coi nó là bị xâm phạm.

## 5. Xác định bí mật xuất hiện ở đâu

Trước khi sửa lịch sử, hãy lập phạm vi cần xử lý:

- Commit đầu tiên có chứa secret.
- Các commit sau có sao chép hoặc sửa lại giá trị đó.
- Branch và tag nào trỏ đến các commit bị ảnh hưởng.
- Secret có xuất hiện trong nhiều file, tên file, script, test fixture hoặc tài liệu không.
- Remote nào đã nhận commit: origin, fork, mirror hoặc repository khác.
- Pull request, release, CI artifact, package, image hoặc log nào có thể chứa nội dung.
- Các bản clone local của thành viên và máy build có thể còn lịch sử cũ.

Một số lệnh giúp tìm đường dẫn và lịch sử liên quan:

~~~bash
# Xem các commit thay đổi một đường dẫn
git log --all --oneline -- config/prod.env

# Xem các refs và tag hiện có
git branch -a
git tag --list

# Xem một commit nghi ngờ mà không in giá trị secret ra báo cáo
git show --stat <commit-hash>
~~~

Nếu cần tìm nội dung cụ thể, dùng secret scanner được phê duyệt trong môi trường an toàn và bật chế độ che giá trị phát hiện. Không dùng lệnh in toàn bộ dòng chứa secret ra terminal dùng chung hoặc log CI. Khi chia sẻ kết quả, chỉ ghi loại secret, đường dẫn, commit hash và trạng thái xử lý.

## 6. Làm sạch file hiện tại

Sau khi credential cũ đã được thu hồi, hãy sửa working tree để không tiếp tục lưu secret trong snapshot mới.

### Nếu file chỉ chứa cấu hình local

Giả sử file <code>config/prod.env</code> chỉ dành cho máy hoặc môi trường triển khai, bạn có thể ngừng theo dõi file nhưng giữ nó trên máy:

~~~bash
# Gỡ file khỏi index, giữ file local trên ổ đĩa
git rm --cached -- config/prod.env
~~~

Thêm quy tắc phù hợp vào <code>.gitignore</code>:

~~~gitignore
config/prod.env
~~~

Nếu nhóm cần một ví dụ cấu hình, tạo file mẫu chỉ chứa tên biến và giá trị giả:

~~~text
DB_HOST=localhost
DB_USER=app_user
DB_PASSWORD=replace-me-locally
API_TOKEN=replace-me-locally
~~~

Lưu mẫu đó với tên như <code>config/prod.env.example</code>, rồi hướng dẫn mỗi môi trường tạo file thật từ secret manager hoặc biến môi trường.

Nếu file thật vẫn nằm trên máy, hãy xóa giá trị đã bị thu hồi và nạp credential mới từ nguồn được bảo vệ. Nếu không còn cần file local đó, xóa nó theo quy trình quản lý dữ liệu của máy. Quy tắc ignore chỉ ngăn Git theo dõi file chưa được theo dõi; nó không xóa bản sao local hoặc bản sao bên ngoài repository.

### Nếu file phải tiếp tục được version hóa

Xóa giá trị bí mật khỏi nội dung file, thay bằng biến môi trường hoặc tham chiếu secret manager:

~~~yaml
database:
  password: ${DB_PASSWORD}
service:
  apiToken: ${SERVICE_API_TOKEN}
~~~

Đảm bảo ứng dụng có cơ chế nạp giá trị ở runtime. Không commit giá trị thật vào file mẫu, test, script hoặc tài liệu.

### Vì sao chỉ sửa file hiện tại là chưa đủ?

Các bước trên bảo vệ snapshot tiếp theo. Nếu secret từng nằm trong commit cũ, nó vẫn có thể được đọc từ lịch sử. Khi đó cần đánh giá việc viết lại lịch sử ở các phần sau.

## 7. Trường hợp commit chứa secret chưa được push

Nếu secret chỉ nằm trong commit local chưa chia sẻ, phạm vi làm sạch có thể đơn giản hơn, nhưng vẫn cần kiểm tra mọi commit local liên quan và mọi nơi đã sao lưu repository.

Nếu secret chỉ nằm trong commit mới nhất, bạn có thể sửa snapshot và thay commit đó:

~~~bash
# Gỡ file cấu hình local khỏi index nhưng giữ file trên máy
git rm --cached -- config/prod.env

# Cập nhật .gitignore và file mẫu an toàn
git add .gitignore config/prod.env.example

# Thay commit gần nhất bằng nội dung đã sửa
git commit --amend
~~~

Trước khi amend, hãy xác nhận index chỉ chứa nội dung bạn muốn đưa vào commit. Nếu file cần được giữ trong repository, sửa giá trị bên trong rồi stage phiên bản an toàn thay vì chỉ gỡ file khỏi index.

Nếu secret xuất hiện trong nhiều commit local, bạn cần sửa hoặc loại bỏ tất cả commit bị ảnh hưởng, chẳng hạn bằng interactive rebase khi phạm vi nhỏ và đã xác định rõ. Không nên chỉ sửa commit cuối cùng nếu commit cũ hơn vẫn chứa giá trị.

Sau khi xử lý, kiểm tra các refs local bằng secret scanner và xác minh commit cũ không còn reachable từ nhánh hoặc tag. Nếu có backup hoặc bản clone khác chứa lịch sử cũ, chúng vẫn có thể giữ secret dù repository hiện tại đã sạch.

Lưu ý: amend hoặc rebase thay đổi lịch sử của nhánh, nhưng commit cũ có thể vẫn còn trong reflog và object database local cho đến khi được dọn theo chính sách. Nếu yêu cầu sự cố là loại bỏ cả object unreachable khỏi máy, cần kiểm kê refs, giữ backup bảo mật theo chính sách rồi mới cân nhắc hết hạn reflog và prune object:

~~~bash
git reflog expire --expire=now --all
git gc --prune=now
~~~

Đây là thao tác ảnh hưởng khả năng khôi phục trạng thái cũ và không nên chạy tùy tiện. Nó chỉ xử lý repository local đang thao tác, không làm sạch remote, clone khác, backup hoặc cache.

## 8. Trường hợp secret đã được push lên remote

Nếu commit đã được push, hãy coi bí mật là đã được chia sẻ với mọi người hoặc hệ thống có quyền đọc repository trong khoảng thời gian đó. Việc đổi lịch sử trên remote chỉ là một phần của quá trình.

Quy trình thường gồm:

1. Hoàn tất thu hồi và xoay vòng credential.
2. Thông báo cho người quản lý repository và thống nhất thời gian đóng băng push/merge.
3. Tạo bản sao làm việc riêng để viết lại lịch sử; giữ backup bảo mật theo chính sách.
4. Loại secret khỏi tất cả commit và refs bị ảnh hưởng.
5. Kiểm tra kết quả bằng secret scanner và rà soát lịch sử.
6. Cập nhật remote bằng force push có kiểm soát cho các refs đã làm sạch.
7. Yêu cầu thành viên tạo clone mới hoặc đồng bộ theo hướng dẫn; không merge lại nhánh cũ.
8. Xử lý cache, fork, pull request, artifact và bản sao do nền tảng lưu giữ.

Không force push khi chưa xác định các branch, tag và refs nào sẽ bị tác động. Việc rewrite có thể ảnh hưởng pull request, release, pipeline và công việc chưa push của thành viên khác.

## 9. Dùng git-filter-repo để loại secret khỏi lịch sử

Đối với việc viết lại lịch sử, <code>git-filter-repo</code> thường được khuyến nghị hơn <code>git filter-branch</code> vì có thiết kế và hiệu năng phù hợp hơn cho tác vụ lọc lịch sử. Hãy cài đặt và kiểm tra phiên bản theo hướng dẫn chính thức của công cụ và chính sách máy phát triển.

Trước khi chạy, phân biệt hai trường hợp:

- **Bỏ toàn bộ một file khỏi lịch sử:** dùng path filter nếu file không cần tồn tại trong bất kỳ commit nào.
- **Giữ file nhưng thay giá trị bí mật:** dùng replace-text để thay chuỗi nhạy cảm trong các blob lịch sử.

Thực hiện trên một bản clone sạch, riêng biệt. Không chạy rewrite trực tiếp trên repository làm việc duy nhất của nhóm.

### Chuẩn bị mirror clone

~~~bash
git clone --mirror <repository-url> repo-clean.git
cd repo-clean.git
~~~

Mirror clone lấy các refs mà remote công bố và tạo repository bare phù hợp cho thao tác trên toàn bộ lịch sử. Kiểm tra remote và refs trước khi lọc:

~~~bash
git show-ref
git remote -v
~~~

Giữ bản clone gốc và backup theo quy trình bảo mật cho đến khi nhóm xác nhận việc làm sạch hoàn tất.

### Loại toàn bộ file chứa secret

Nếu file chỉ là cấu hình local bị commit nhầm và không cần giữ trong lịch sử:

~~~bash
git filter-repo --sensitive-data-removal --path config/prod.env --invert-paths
~~~

Lệnh này loại đường dẫn <code>config/prod.env</code> khỏi các commit được lọc. Nếu file từng được lưu dưới nhiều đường dẫn hoặc tên khác, cần thêm tất cả đường dẫn tương ứng. Hãy kiểm tra lịch sử để không bỏ sót bản sao đã đổi tên.

Tùy phiên bản <code>git-filter-repo</code>, cờ <code>--sensitive-data-removal</code> có thể chưa được hỗ trợ. Kiểm tra trợ giúp của phiên bản đã cài và làm theo tài liệu tương ứng; không tự bỏ qua cảnh báo hoặc dùng một lệnh chưa hiểu rõ.

### Thay giá trị bí mật nhưng giữ file

Nếu file vẫn cần trong lịch sử nhưng giá trị phải được loại bỏ, tạo một file thay thế tạm thời bên ngoài repository. Ví dụ minh họa cú pháp:

~~~text
literal:EXAMPLE-LEAKED-VALUE==>***REMOVED***
~~~

Trong thực tế, thay <code>EXAMPLE-LEAKED-VALUE</code> bằng chuỗi cần loại bỏ trong môi trường local được bảo vệ. Không commit file thay thế, không đưa nó vào issue hoặc log, và hạn chế quyền đọc của file. Sau khi dùng xong, xử lý file tạm theo chính sách bảo vệ dữ liệu của tổ chức.

Chạy:

~~~bash
git filter-repo --sensitive-data-removal --replace-text ../replacements.txt
~~~

<code>--replace-text</code> thay chuỗi khớp trong nội dung blob theo quy tắc của file. Nếu secret xuất hiện dưới nhiều dạng mã hóa, escape hoặc biến thể, phải xác định và xử lý từng dạng liên quan. Không mặc định một chuỗi thay thế duy nhất sẽ xóa mọi biểu diễn của credential.

Nếu phiên bản công cụ không hỗ trợ <code>--sensitive-data-removal</code>, tham khảo trợ giúp để dùng cú pháp tương thích. Không dùng <code>git filter-branch</code> như một lệnh thay thế nhanh nếu chưa có kế hoạch kiểm thử và hiểu rõ các refs mà nó tác động.

### Kiểm tra sau khi lọc

Sau khi rewrite, xác minh:

- Các branch và tag cần giữ vẫn tồn tại.
- File hoặc giá trị bí mật đã biến mất khỏi mọi commit reachable.
- File cấu hình hiện tại dùng biến môi trường hoặc secret manager.
- Lịch sử commit mới không còn chứa các biến thể của credential.
- Ứng dụng và pipeline vẫn hoạt động sau khi dùng credential mới.

Có thể kiểm tra đường dẫn:

~~~bash
git log --all --oneline -- config/prod.env
git rev-list --objects --all
git show-ref
~~~

Với việc thay chuỗi, chạy secret scanner đã được phê duyệt trên toàn bộ lịch sử reachable sau rewrite. Không chỉ kiểm tra working tree hiện tại.

## 10. Cập nhật remote sau khi viết lại lịch sử

<code>git-filter-repo</code> có thể xóa remote <code>origin</code> như một biện pháp bảo vệ để tránh push nhầm. Kiểm tra:

~~~bash
git remote -v
~~~

Nếu remote đã bị xóa và nhóm đã xác nhận bản rewrite là bản cần phát hành, thêm lại remote:

~~~bash
git remote add origin <repository-url>
~~~

Trước khi push, xác nhận đúng URL, quyền truy cập, branch và tag đã được làm sạch. Sau khi có sự phối hợp của người quản lý repository, có thể cập nhật các branch và tag tương ứng:

~~~bash
git push --force --all origin
git push --force --tags origin
~~~

Hai lệnh trên cập nhật branch và tag. Chúng không bao phủ mọi loại ref tùy chỉnh hoặc ref nội bộ của nền tảng lưu trữ. Nếu repository dùng notes, release refs, pull request refs hoặc ref riêng, hãy kiểm kê và xử lý theo tài liệu của nhà cung cấp.

Không dùng <code>git push --mirror</code> một cách máy móc. Mirror push có thể xóa refs trên remote không có trong bản local; chỉ dùng khi đã kiểm kê đầy đủ và hiểu chính xác tác động. Các branch được bảo vệ có thể cần quy trình quản trị riêng để cho phép cập nhật lịch sử.

## 11. Phối hợp với người có bản clone cũ

Sau khi rewrite remote, bản clone của thành viên khác vẫn có thể chứa commit cũ và secret cũ. Nếu họ push hoặc merge nhánh cũ trở lại, lịch sử chứa secret có thể được đưa trở lại remote.

Với sự cố nhạy cảm, phương án dễ kiểm soát nhất thường là:

1. Thông báo thời điểm lịch sử mới đã được công bố.
2. Yêu cầu thành viên ngừng push từ clone cũ.
3. Tạo clone mới từ remote đã làm sạch.
4. Chuyển các thay đổi local chưa chia sẻ sang clone mới bằng patch hoặc cherry-pick đã kiểm tra.
5. Không merge nhánh cũ có chứa commit trước rewrite.
6. Xóa hoặc cô lập bản clone cũ theo chính sách lưu giữ và ứng phó sự cố.

Nếu không thể clone mới, người quản lý dự án cần cung cấp hướng dẫn đồng bộ chính xác cho từng nhánh và xác nhận không còn ref local giữ lịch sử cũ. Không hướng dẫn mọi người chạy <code>git pull</code> thông thường sau khi rewrite vì thao tác đó có thể nối lịch sử cũ trở lại.

## 12. Những bản sao ngoài Git remote cũng cần được xử lý

Force push chỉ cập nhật refs trên remote mà bạn đang quản lý. Secret có thể vẫn còn trong:

- Fork của thành viên hoặc tổ chức khác.
- Pull request diff, review comment hoặc ref do nền tảng tạo.
- Cache commit, trang xem file hoặc bản mirror của nhà cung cấp.
- CI log, build artifact, package, container image và release bundle.
- Backup, snapshot ổ đĩa và bản clone trên máy phát triển.
- Công cụ phân tích mã nguồn, secret scanner hoặc hệ thống quan sát đã lưu nội dung.

Liên hệ quản trị viên hoặc nhà cung cấp nền tảng để làm sạch cache, pull request refs hoặc bản sao mà nhóm không thể tự quản lý. Một số nhà cung cấp có quy trình hỗ trợ riêng cho việc xóa dữ liệu nhạy cảm khỏi lịch sử; hãy làm theo quy trình đó sau khi đã thu hồi credential.

Backup có thể phải được giữ theo yêu cầu pháp lý hoặc chính sách lưu trữ. Trong trường hợp đó, hạn chế quyền truy cập, ghi nhận thời hạn lưu và bảo đảm credential trong backup đã bị vô hiệu hóa. Không tự ý xóa backup thuộc chính sách bắt buộc.

## 13. Xác minh sự cố đã được xử lý

Một sự cố chỉ nên được đóng khi nhóm có bằng chứng cho cả hai phần: credential cũ không còn sử dụng được và dữ liệu nhạy cảm đã được xử lý trong phạm vi kiểm soát.

### Kiểm tra credential

- Credential cũ có trạng thái revoked/disabled hoặc đã hết hiệu lực.
- Credential mới đã được triển khai qua secret manager hoặc cơ chế được bảo vệ.
- Dịch vụ phụ thuộc hoạt động bằng credential mới.
- Audit log đã được rà soát theo khoảng thời gian có thể bị lộ.
- Quyền truy cập của credential mới được giới hạn ở mức cần thiết.

### Kiểm tra Git

- Branch và tag trên remote đã trỏ đến lịch sử đã làm sạch.
- Secret scanner không phát hiện giá trị cũ trong lịch sử reachable.
- File cấu hình hiện tại không chứa credential thật.
- Các bản clone cũ và nhánh chưa push đã được xử lý.
- Không có commit cũ được merge hoặc push trở lại.
- Pull request, cache, artifact và fork liên quan đã được rà soát.

Ghi lại commit hash trước và sau rewrite, các refs đã cập nhật, thời điểm revoke, thời điểm triển khai credential mới và các hệ thống đã kiểm tra. Báo cáo không cần chứa giá trị bí mật.

## 14. Phòng ngừa để không lặp lại sự cố

Sau khi xử lý, hãy cải thiện quy trình để secret khó đi vào Git:

- Lưu credential trong secret manager hoặc cơ chế quản lý cấu hình bảo mật của nền tảng.
- Dùng biến môi trường hoặc workload identity khi ứng dụng cần credential lúc chạy.
- Commit file mẫu như <code>.env.example</code> chỉ chứa placeholder, không chứa giá trị thật.
- Thêm <code>.gitignore</code> cho file cấu hình local và file chứa secret.
- Bật secret scanning trên repository và trong pipeline.
- Dùng pre-commit hook hoặc kiểm tra CI để phát hiện secret trước khi merge.
- Giới hạn quyền đọc repository, token và service account theo nguyên tắc quyền tối thiểu.
- Định kỳ xoay vòng credential và kiểm tra audit log.
- Hướng dẫn thành viên cách báo cáo sự cố mà không sao chép secret vào kênh công khai.

Ví dụ cấu trúc:

~~~text
project/
|-- .env.example       # placeholder an toàn, được commit
|-- .env               # giá trị local, được ignore
|-- config/
|   |-- app.example.yml
|   |-- app.local.yml   # được ignore nếu có credential
|-- src/
~~~

Quy tắc ignore minh họa:

~~~gitignore
.env
.env.*
!.env.example
config/*.local.yml
~~~

Hãy điều chỉnh mẫu theo cấu trúc thực tế. Đảm bảo các file mẫu được phép commit không chứa giá trị bí mật thật và các file local đã tracked trước đây được gỡ khỏi index khi cần.

## 15. Lỗi thường gặp khi xử lý secret bị lộ

| Cách xử lý sai | Vì sao chưa đủ | Hướng xử lý đúng |
|---|---|---|
| Chỉ xóa dòng secret ở commit mới | Commit cũ vẫn chứa giá trị | Revoke/rotate credential và làm sạch lịch sử khi cần |
| Chỉ thêm file vào <code>.gitignore</code> | Ignore không tác động lên lịch sử hoặc file tracked | Gỡ khỏi index và xử lý commit cũ |
| Chỉ chạy <code>git gc</code> | Object reachable từ commit cũ vẫn được giữ | Rewrite refs chứa commit cũ, rồi xử lý bản sao theo chính sách |
| Rewrite lịch sử trước khi revoke | Credential cũ vẫn có thể hoạt động trong lúc xử lý | Thu hồi hoặc vô hiệu hóa credential trước |
| Chỉ force push một branch | Tag, branch khác hoặc refs khác có thể vẫn giữ secret | Kiểm kê và làm sạch tất cả refs liên quan |
| Yêu cầu mọi người pull nhánh mới | Clone cũ có thể nối lại lịch sử chứa secret | Tạo clone mới hoặc dùng hướng dẫn đồng bộ đã kiểm tra |
| Chỉ làm sạch remote chính | Fork, cache, artifact và backup vẫn có thể giữ dữ liệu | Kiểm tra các bản sao ngoài remote và làm việc với nhà cung cấp |
| Đưa secret vào lệnh shell hoặc issue để tìm kiếm | Shell history, log và hệ thống ticket có thể tạo thêm bản sao | Dùng secret scanner và file tạm được bảo vệ |
| Xóa lịch sử nhưng không đổi credential | Người đã lấy secret vẫn có thể dùng nó | Revoke/rotate và rà soát audit log |

## 16. Quy trình ứng phó mẫu

Khi một token bị commit và push lên remote, có thể dùng trình tự sau:

~~~text
Phát hiện secret trong commit
        |
        v
Thông báo sự cố và xác định loại credential
        |
        v
Revoke/disable credential cũ
        |
        v
Cấp credential mới và cập nhật workload
        |
        v
Rà soát audit log và phạm vi lộ
        |
        v
Đóng băng push/merge vào refs bị ảnh hưởng
        |
        v
Rewrite lịch sử trong clone sạch
        |
        v
Secret scan và xác minh refs đã làm sạch
        |
        v
Force push có kiểm soát, xử lý clone/fork/cache/artifact
        |
        v
Xác nhận credential cũ vô hiệu và không còn đường tái đưa lịch sử cũ
~~~

Trình tự này có thể cần điều chỉnh theo nhà cung cấp và mức độ nghiêm trọng. Với credential đang bị khai thác, việc vô hiệu hóa và ngăn truy cập trái phép có thể cần thực hiện ngay song song với việc khôi phục dịch vụ bằng credential mới.

## 17. Bài tập tự kiểm tra

Thực hành trong repository thử nghiệm với một chuỗi giả không có giá trị truy cập:

1. Tạo file cấu hình chứa một chuỗi placeholder giả và commit file.
2. Tạo thêm commit thay đổi mã nguồn, sau đó xóa file cấu hình ở commit tiếp theo.
3. Dùng <code>git log --all --oneline -- &lt;path&gt;</code> để thấy file vẫn xuất hiện trong lịch sử cũ.
4. Thực hành gỡ file khỏi index, thêm quy tắc ignore và tạo file mẫu an toàn.
5. Tạo mirror clone riêng và dùng <code>git-filter-repo</code> để loại file giả khỏi lịch sử.
6. Kiểm tra branch, tag và object reachable sau khi rewrite.
7. Giải thích vì sao <code>git gc</code> và một commit xóa file không thay thế được history rewrite.
8. Lập kế hoạch xử lý một credential giả đã được push: ai thu hồi, ai tạo giá trị mới, refs nào phải rewrite và các bản clone nào cần làm mới.
9. Viết một báo cáo sự cố không chứa giá trị secret, chỉ ghi loại credential, phạm vi, commit hash và trạng thái khắc phục.

Khi xử lý bí mật bị lộ, hãy ưu tiên làm cho credential cũ không còn sử dụng được, sau đó làm sạch lịch sử và mọi bản sao trong phạm vi quản lý. Việc xác minh phải bao gồm cả hệ thống đang dùng credential, repository remote, clone của thành viên và các artifact hoặc cache có thể giữ nội dung cũ.
