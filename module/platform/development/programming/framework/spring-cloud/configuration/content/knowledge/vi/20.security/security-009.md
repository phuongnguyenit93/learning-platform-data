# Kiểm soát lịch sử Git và xử lý khi bí mật đã bị commit

## 1. Vì sao xóa secret khỏi file hiện tại chưa đủ?

Repository cấu hình của Spring Cloud Config thường chứa endpoint nội bộ, username, password, token, API key, private key hoặc thông tin kết nối database. Nếu một secret bị commit vào Git, xóa dòng đó trong commit mới chỉ làm file hiện tại sạch hơn. Giá trị cũ vẫn có thể tồn tại trong các commit trước, branch khác, tag, pull request, fork, clone của developer, mirror và cache của Git provider.

Git lưu lịch sử theo object bất biến. Một commit mới không ghi đè nội dung commit cũ; nó tạo một commit khác trỏ đến snapshot mới. Vì vậy, người có quyền đọc repository vẫn có thể checkout hoặc xem lịch sử cũ để tìm secret đã bị xóa khỏi phiên bản hiện tại.

Khi phát hiện secret đã được commit, cần xử lý hai mục tiêu riêng:

1. **Làm secret cũ mất hiệu lực**: revoke hoặc rotate credential tại hệ thống đã cấp nó.
2. **Làm sạch lịch sử và các bản sao**: viết lại Git history, cập nhật remote refs và xử lý clone, fork, cache, log, artifact có thể chứa secret.

Viết lại lịch sử giúp giảm khả năng tiếp tục truy cập secret từ repository. Nó không thay thế việc thu hồi secret đã lộ.

## 2. Xem secret đã commit là có khả năng bị lộ

Ngay cả khi repository là private, secret đã commit vẫn có thể bị đọc bởi thành viên, bot, CI runner, ứng dụng tích hợp, mirror hoặc tài khoản bị xâm nhập. Không thể kết luận secret an toàn chỉ vì commit tồn tại trong thời gian ngắn hoặc repository chưa public.

Các loại dữ liệu cần xử lý gồm:

| Loại dữ liệu | Ví dụ | Hành động ưu tiên |
|---|---|---|
| Password và database credential | `spring.datasource.password` | Đổi password, thu hồi credential cũ và kiểm tra connection đang dùng. |
| API key/token | Git token, cloud access key, payment API key | Revoke token cũ, cấp token mới với scope tối thiểu. |
| Private key | SSH deploy key, TLS private key, signing key | Thu hồi key/certificate cũ, thay key pair và cập nhật trust/authorized keys. |
| Signing/encryption key | JWT signing key, encryption key | Đánh giá dữ liệu/chữ ký phụ thuộc, triển khai key mới và giữ key cũ chỉ trong thời gian chuyển đổi cần thiết. |
| Connection string | URL chứa username/password | Thay credential, xóa thông tin nhạy cảm khỏi URL và kiểm tra log. |
| Secret của môi trường thử nghiệm | Sandbox token hoặc test password | Vẫn phải revoke nếu có quyền truy cập hệ thống hoặc được dùng lại ở môi trường khác. |

Nếu cùng một secret được tái sử dụng ở nhiều môi trường hoặc dịch vụ, phải kiểm tra và thay ở tất cả nơi sử dụng. Không chỉ thay giá trị trong repository cấu hình.

## 3. Quy trình ứng phó: thu hồi trước, rewrite history sau

Thứ tự xử lý khuyến nghị:

1. **Xác nhận loại secret và phạm vi**: xác định nhà cung cấp, tài khoản, quyền, môi trường, thời điểm commit và các hệ thống đang sử dụng credential.
2. **Revoke hoặc rotate ngay**: làm secret cũ mất hiệu lực tại nơi cấp. Nếu không thể revoke tức thì, giới hạn quyền hoặc khóa tài khoản trong thời gian xử lý.
3. **Cấp secret mới an toàn**: tạo credential mới, scope tối thiểu, thời hạn phù hợp và cấp qua secret manager hoặc nền tảng triển khai.
4. **Kiểm tra hoạt động phụ thuộc**: cập nhật Config Server, Config Client, CI/CD, job, integration và workload sử dụng credential mới.
5. **Lưu bằng chứng sự cố**: ghi nhận commit SHA, refs, loại secret, thời điểm phát hiện, thời điểm revoke và hành động đã thực hiện; không sao chép plaintext vào ticket hoặc log.
6. **Viết lại lịch sử Git**: loại secret khỏi mọi commit/ref có liên quan và kiểm tra kết quả.
7. **Cập nhật remote và các bản sao**: phối hợp force-push, yêu cầu fresh clone, xử lý fork/mirror/cache và artifact.
8. **Quét lại và đóng sự cố**: xác nhận secret cũ không còn hoạt động, lịch sử đã được làm sạch và credential mới hoạt động bình thường.

Không trì hoãn revoke để chờ hoàn tất việc rewrite. Một lịch sử sạch không làm token cũ mất hiệu lực; ngược lại, token đã revoke vẫn có thể còn trong lịch sử nhưng không còn dùng được.

## 4. Khoanh vùng secret đã xuất hiện ở đâu

Trước khi rewrite, cần xác định phạm vi để không bỏ sót refs hoặc bản sao.

### Trong repository

- Commit chứa secret và commit cha/con liên quan.
- Tất cả branch đang tồn tại, kể cả branch feature chưa merge.
- Tag release và annotated tag.
- Branch đã xóa nhưng commit vẫn còn được tham chiếu ở nơi khác.
- File đã đổi tên hoặc di chuyển thư mục.
- Pull request, merge request, review diff và ref do Git provider quản lý.

### Ngoài repository chính

- Fork và mirror của tổ chức hoặc cá nhân.
- Clone trên máy developer, máy build và runner.
- CI logs, job artifacts, test reports và cache.
- Docker image, package, binary hoặc bundle được tạo từ repository.
- Backup, snapshot, archive và bản export repository.
- Chat, ticket, paste, tài liệu hoặc log đã nhận nội dung secret.

Secret scanning và audit log của Git provider có thể giúp tìm commit, người truy cập và thời gian phơi lộ. Khi tìm kiếm, tránh in plaintext secret vào terminal output hoặc gửi nó vào công cụ không được phép xử lý dữ liệu nhạy cảm.

## 5. Chuẩn bị trước khi viết lại Git history

Rewrite history làm thay đổi commit SHA của các commit bị ảnh hưởng và mọi commit con phụ thuộc vào chúng. Đây là thay đổi phối hợp, không nên thực hiện khi nhiều người vẫn tiếp tục push vào các branch cũ.

Trước khi làm:

1. Thông báo cửa sổ bảo trì repository và yêu cầu tạm dừng push/merge.
2. Ghi lại danh sách branch, tag và remote refs đang tồn tại.
3. Xác định tất cả đường dẫn lịch sử có chứa secret, bao gồm tên file cũ sau rename.
4. Tạo bản sao lưu repository có kiểm soát quyền truy cập để phục vụ điều tra/khôi phục khi cần; bản sao lưu vẫn chứa secret nên phải được bảo vệ như dữ liệu nhạy cảm.
5. Chọn một clone mới, không dùng working tree đang có thay đổi của developer.
6. Cài và xác minh công cụ rewrite được phê duyệt, thường là `git-filter-repo`.
7. Xác định cách cập nhật remote refs và các refs đặc biệt do Git provider quản lý.

Không để người khác tiếp tục push trong lúc rewrite. Một push từ clone cũ có thể đưa commit chứa secret trở lại remote sau khi đã làm sạch.

Viết lại commit cũng làm mất hiệu lực chữ ký số gắn với commit/tag đã thay đổi. Nếu tổ chức yêu cầu signed commit hoặc signed release tag, cần tạo lại chữ ký theo danh tính được phép sau khi rewrite và cập nhật quy trình xác minh provenance. Không coi chữ ký cũ còn hợp lệ chỉ vì tên tag vẫn giữ nguyên.

## 6. Dùng git-filter-repo để xóa file khỏi toàn bộ lịch sử

`git-filter-repo` là công cụ phổ biến để viết lại Git history. Nó không phải lệnh có sẵn trong mọi bản Git; cần cài theo hướng dẫn chính thức của dự án và phiên bản được tổ chức phê duyệt. Công cụ này thường được ưu tiên hơn `git filter-branch` cho tác vụ rewrite lớn.

Nếu một file chuyên chứa secret cần được loại bỏ hoàn toàn khỏi mọi commit, có thể dùng `--path` cùng `--invert-paths`.

Ví dụ trên một mirror clone mới:

```bash
git clone --mirror https://git.example.internal/platform/config-repo.git config-repo-clean.git
cd config-repo-clean.git
git filter-repo --path config/secrets-prod.yml --invert-paths
```

`--path` nhận đường dẫn tương đối từ root repository. `--invert-paths` giữ lại mọi nội dung khác và loại file được chỉ định khỏi lịch sử được xử lý.

Nếu file từng nằm ở nhiều đường dẫn do rename hoặc di chuyển, phải liệt kê tất cả đường dẫn lịch sử:

```bash
git filter-repo \
  --path config/old/secrets.yml \
  --path environments/prod/secrets.yml \
  --invert-paths
```

Chỉ xóa file nếu toàn bộ file không cần giữ trong lịch sử. Nếu file chứa cả cấu hình hợp lệ và secret, dùng phương pháp thay thế nội dung ở phần tiếp theo để giữ lại các dòng không nhạy cảm.

## 7. Thay một giá trị secret trong toàn bộ lịch sử

Nếu secret nằm trong file vẫn cần giữ, `git-filter-repo --replace-text` có thể thay chuỗi đã biết trong nội dung các commit.

Tạo file quy tắc thay thế tạm thời, ví dụ `replacements.txt`:

```text
literal:OLD_SECRET_VALUE==>***REMOVED***
```

Sau đó chạy trong clone rewrite:

```bash
git filter-repo --replace-text replacements.txt
```

`literal:` yêu cầu khớp chính xác chuỗi. Có thể thêm nhiều quy tắc cho các biến thể đã xuất hiện, nhưng phải xác định đúng giá trị cần loại bỏ. Nếu secret có nhiều dạng encode, URL-encode hoặc bị chia nhỏ trong file, cần tìm và xử lý từng dạng có thể khôi phục.

File quy tắc chứa secret cũ, do đó:

- Không commit file này.
- Hạn chế quyền đọc và lưu trong thư mục tạm an toàn.
- Không in nội dung file ra log hoặc terminal dùng chung.
- Xóa file theo chính sách xử lý dữ liệu nhạy cảm sau khi hoàn tất.

Nếu secret đã xuất hiện trong nhiều file hoặc nhiều dạng biểu diễn, quét toàn bộ history để xác định mọi vị trí. Đừng chỉ thay một lần xuất hiện đầu tiên.

Nếu secret bị ghi trong commit message hoặc annotated tag message thay vì nội dung file, dùng cơ chế thay thế message riêng của `git-filter-repo`, chẳng hạn `--replace-message`, với file quy tắc tương ứng. `--replace-text` tập trung vào nội dung file; không giả định nó tự làm sạch mọi metadata của commit/tag.

## 8. Kiểm tra lịch sử sau rewrite

Sau khi chạy filter, không chỉ mở file ở branch hiện tại rồi kết luận đã sạch. Cần kiểm tra tất cả refs mà clone xử lý.

Các kiểm tra nên thực hiện:

1. Liệt kê refs và xác nhận branch/tag dự kiến vẫn tồn tại.
2. Chạy secret scanner đã được tổ chức phê duyệt trên toàn bộ refs/history.
3. Tìm đường dẫn file cũ trong lịch sử để xác nhận không còn blob chứa file đó.
4. Kiểm tra diff của các commit đã viết lại để xác nhận file và cấu hình không liên quan vẫn được giữ.
5. Kiểm tra tag, branch release, branch bảo trì và refs khác ngoài branch chính.
6. Xác nhận ứng dụng vẫn có cấu hình hợp lệ sau khi file secret bị xóa hoặc thay thế.

Một số lệnh Git hữu ích để kiểm kê refs và đường dẫn:

```bash
git for-each-ref --format="%(refname)"
git log --all --full-history -- config/secrets-prod.yml
git rev-list --objects --all
```

Các lệnh trên hỗ trợ kiểm kê nhưng không tự chứng minh mọi secret đã biến mất. `git log` theo đường dẫn không phát hiện một secret đã được copy sang file khác; `git rev-list --objects` liệt kê object/path chứ không quét nội dung blob. Hãy dùng secret scanner có khả năng quét lịch sử hoặc quy trình kiểm tra nội dung object được phê duyệt.

Không đưa secret vào tham số lệnh hoặc truy vấn tìm kiếm nếu shell history, process list hay log có thể lưu lại. Báo cáo kết quả bằng tên rule, file, commit và trạng thái phát hiện; không in plaintext.

## 9. Cập nhật remote sau khi rewrite

Sau khi rewrite, commit SHA đã thay đổi. Cần cập nhật các branch/tag tương ứng trên Git provider bằng quy trình được phê duyệt.

`git-filter-repo` thường xóa remote tên `origin` sau khi chạy để tránh push nhầm lịch sử đã viết lại. Kiểm tra lại remote trước khi push:

```bash
git remote -v
git remote add origin https://git.example.internal/platform/config-repo.git
```

Trước khi rewrite, hãy lưu SHA hiện tại của từng remote ref. Khi push, có thể dùng explicit lease để chỉ ghi đè nếu remote vẫn trỏ đến SHA đã kiểm kê:

Ví dụ cập nhật một branch:

```bash
git push --force-with-lease=refs/heads/main:OLD_REMOTE_SHA origin refs/heads/main:refs/heads/main
```

Thay `OLD_REMOTE_SHA` bằng SHA thật đã ghi nhận trước khi rewrite; không dùng nguyên văn placeholder. `--force-with-lease` kiểm tra remote ref chưa thay đổi ngoài dự kiến trước khi ghi đè. Với nhiều branch và tag, cần cập nhật từng ref đã được kiểm kê, theo chính sách của tổ chức. Nếu remote đã thay đổi kể từ lúc kiểm kê, dừng lại và đối chiếu thay đổi trước khi thử push lại.

Nếu phải xóa một branch remote đã bị loại khỏi lịch sử:

```bash
git push origin :refs/heads/obsolete-feature
```

Nếu tag phải được cập nhật theo commit mới sau rewrite, cần xử lý rõ ràng theo chính sách tag release; tag được bảo vệ có thể cần quyền quản trị hoặc quy trình riêng. Không tự ý force-update tag phát hành đã được công bố mà chưa đánh giá hệ thống triển khai và kiểm toán đang tham chiếu tag đó.

Không chạy `git push --mirror` một cách máy móc trên Git provider dùng refs đặc biệt cho pull request, merge request hoặc hệ thống nội bộ. Mirror push có thể force-update hoặc xóa refs ngoài dự kiến. Chỉ dùng khi đã hiểu chính xác toàn bộ refs sẽ bị thay đổi và có phê duyệt rõ ràng.

Một số Git provider giữ refs hoặc cache do nền tảng quản lý mà người dùng không thể cập nhật bằng push thông thường. Với pull request refs, cached views hoặc object còn được nền tảng giữ lại, cần dùng quy trình hỗ trợ chính thức của provider.

## 10. Phối hợp developer sau khi lịch sử bị viết lại

Sau force-push, clone cũ vẫn giữ commit SHA và object lịch sử trước khi rewrite. Nếu developer tiếp tục làm việc trên branch cũ rồi push, họ có thể đưa lịch sử chứa secret trở lại remote.

Với repository chứa secret nhạy cảm, cách an toàn thường là:

1. Yêu cầu developer dừng push từ clone cũ.
2. Lưu riêng các thay đổi chưa được tích hợp nếu chúng không chứa secret.
3. Xóa hoặc cách ly clone cũ theo chính sách xử lý dữ liệu nhạy cảm.
4. Clone lại repository từ remote đã làm sạch.
5. Áp dụng lại thay đổi hợp lệ bằng patch/cherry-pick có kiểm tra từ các commit sạch.
6. Không merge branch cũ hoặc tag cũ vào lịch sử mới.

Nếu buộc phải giữ clone hiện tại, phải xử lý branch, tag, reflog và object cũ theo quy trình Git chuyên biệt. Chỉ `git pull` hoặc `git reset --hard origin/main` không bảo đảm secret đã biến mất khỏi object database và reflog của clone.

## 11. Làm sạch fork, mirror, CI và artifact

Viết lại remote chính không tự sửa mọi bản sao đã được tạo trước đó.

| Nơi có thể còn dữ liệu | Việc cần làm |
|---|---|
| Fork cá nhân/tổ chức | Xác định owner, phối hợp rewrite hoặc xóa fork theo chính sách. Nếu không kiểm soát được, yêu cầu provider hỗ trợ. |
| Mirror repository | Đồng bộ lịch sử đã rewrite, kiểm tra refs và dừng mirror job trong cửa sổ bảo trì. |
| CI runner/workspace | Xóa workspace/cache có chứa clone cũ và tạo runner workspace sạch. |
| Job log và artifact | Thu hồi quyền truy cập, xóa artifact/log chứa secret theo chính sách retention và incident response. |
| Docker image/package | Build lại từ source sạch, thu hồi image/package cũ và kiểm tra layer/cache. |
| Backup/snapshot | Đánh dấu dữ liệu có secret, giới hạn quyền truy cập và áp dụng retention/secure deletion phù hợp. |
| Git provider cached views | Dùng quy trình xóa cached view hoặc liên hệ support theo hướng dẫn của provider. |
| Ticket/chat/document | Xóa hoặc hạn chế truy cập nội dung đã dán secret; thay bằng mã tham chiếu sự cố. |

Nếu secret đã bị public, giả định mọi người có thể đã sao chép nó. Không thể chứng minh mọi bản sao ngoài tổ chức đã bị xóa; vì vậy revoke/rotate credential vẫn là biện pháp bảo vệ quan trọng nhất.

## 12. Cập nhật ứng dụng Spring Cloud Config sau sự cố

Với repository cấu hình, secret có thể được đọc bởi Config Server và phân phối đến nhiều Config Client. Sau khi rotate credential:

1. Cập nhật secret mới trong secret manager hoặc nguồn cấu hình được phép.
2. Cấp quyền cho Config Server/Client cần sử dụng secret mới theo đúng mô hình bảo mật.
3. Xóa giá trị cũ khỏi file cấu hình hiện tại và làm sạch toàn bộ Git history.
4. Kiểm tra Config Server trả giá trị mới cho đúng application/profile/label.
5. Refresh client hoặc restart nếu bean/tài nguyên không hỗ trợ cập nhật động.
6. Kiểm tra kết nối thực tế, log lỗi xác thực và metric sau thay đổi.
7. Thu hồi credential cũ sau khi xác nhận không còn workload hợp lệ sử dụng nó.

Nếu secret được mã hóa bằng Spring Cloud Config `{cipher}`, cần xác định key mã hóa riêng với credential ứng dụng. Nếu key mã hóa cũng bị commit, phải xử lý như một secret độc lập, đánh giá toàn bộ ciphertext phụ thuộc và lập kế hoạch re-encrypt trước khi thu hồi key cũ.

## 13. Ngăn secret bị commit trở lại

Sau khi xử lý sự cố, cần thêm lớp phòng ngừa ở nhiều giai đoạn:

- **Secret manager**: lưu credential trong Vault hoặc secret store của cloud/platform; Git chỉ chứa tên tham chiếu hoặc cấu hình không nhạy cảm.
- **Least privilege**: token chỉ có quyền cần thiết, tách credential theo môi trường và dịch vụ.
- **Short-lived credentials**: ưu tiên token ngắn hạn hoặc workload identity thay cho key lâu dài.
- **`.gitignore`**: loại file local secret khỏi các lần add mới; nhớ rằng `.gitignore` không xóa file đã được track.
- **Pre-commit hook**: quét secret trước khi tạo commit, nhưng xem đây là lớp hỗ trợ vì hook có thể bị bỏ qua.
- **Server-side scanning/push protection**: bật secret scanning và push protection trên Git provider nếu được hỗ trợ.
- **CI scanning**: quét diff và lịch sử trong pipeline, chặn build/release khi phát hiện secret.
- **Review**: yêu cầu review file cấu hình và kiểm tra các URL, header, credential hoặc private key được thêm vào.
- **Audit**: theo dõi secret access, token issuance, revoke và thay đổi quyền repository.

Ví dụ `.gitignore`:

```gitignore
# Local secrets and developer-specific configuration
.env
.env.*
*.local-secrets.yml
config/private/
*.p12
*.jks
```

Điều chỉnh pattern theo cấu trúc dự án; không ignore rộng các file cấu hình mẫu mà nhóm cần version control. `.gitignore` chỉ ngăn Git tự động đề xuất file chưa được track; nếu file đã được `git add` hoặc commit, cần gỡ khỏi index và xử lý history riêng.

## 14. Những cách xử lý sai thường gặp

| Cách làm sai | Vì sao chưa đủ hoặc nguy hiểm | Cách làm đúng |
|---|---|---|
| Chỉ xóa dòng secret trong commit mới | Commit cũ vẫn chứa blob và diff cũ. | Revoke secret, sau đó rewrite toàn bộ refs/history. |
| Chỉ xóa branch chứa secret | Commit có thể vẫn tồn tại qua tag, branch khác, fork hoặc reflog. | Kiểm kê mọi refs và bản sao. |
| Chỉ đổi tên file | Lịch sử vẫn chứa nội dung cũ ở đường dẫn trước. | Rewrite path cũ và path mới trên toàn bộ history. |
| Rewrite history nhưng không rotate token | Secret cũ vẫn có thể dùng được nếu ai đó đã sao chép. | Revoke/rotate trước hoặc ngay khi phát hiện. |
| Force-push mà không thông báo nhóm | Clone cũ có thể đưa commit cũ trở lại. | Dừng push, phối hợp, cập nhật clone và kiểm tra remote sau rewrite. |
| Chạy `git push --mirror` không kiểm tra refs | Có thể xóa/ghi đè refs do provider quản lý hoặc refs ngoài phạm vi. | Kiểm kê refs và cập nhật theo quy trình provider. |
| Tin rằng private repository không bị lộ | Thành viên, bot, CI và integration vẫn có thể đọc. | Xử lý như secret đã bị lộ và xem audit log. |
| Chỉ bật `.gitignore` | Không ảnh hưởng file đã được track hoặc lịch sử cũ. | Gỡ khỏi index, rewrite history và thêm scanning. |

## 15. Checklist đóng sự cố

Chỉ đóng sự cố khi các mục phù hợp đã được xác minh:

- [ ] Secret cũ đã revoke/rotate và không còn xác thực được.
- [ ] Credential mới đã được cấp qua kênh an toàn và chỉ có quyền tối thiểu.
- [ ] Đã kiểm kê branch, tag, refs và đường dẫn lịch sử chứa secret.
- [ ] Git history đã được rewrite trên tất cả refs có quyền kiểm soát.
- [ ] Secret scanner không còn phát hiện giá trị cũ trong remote repository đã làm sạch.
- [ ] Git provider đã xử lý cached views/refs đặc biệt nếu cần.
- [ ] Fork, mirror, clone, CI workspace, logs, artifacts và images đã được xử lý.
- [ ] Developer đã clone lại hoặc làm sạch clone cũ theo hướng dẫn.
- [ ] Config Server và Config Client dùng credential mới; kết nối thực tế đã được kiểm tra.
- [ ] Audit log, thời điểm phơi lộ, phạm vi truy cập và hành động ứng phó đã được ghi nhận mà không lưu plaintext secret.
- [ ] Secret scanning, push protection và quy trình review đã được cải thiện.

## 16. Bài thực hành

### Bước 1: Tạo repository thử nghiệm có secret giả

Tạo repository local với một file `config/secrets.yml`, commit một chuỗi giả lập như `DEMO_TOKEN_DO_NOT_USE`, sau đó sửa file và commit để xóa chuỗi đó.

**Kết quả cần đạt:** xác nhận giá trị vẫn xuất hiện trong lịch sử cũ dù file hiện tại đã sạch.

### Bước 2: Rewrite bằng git-filter-repo

Tạo mirror clone của repository thử nghiệm. Dùng `--path ... --invert-paths` để loại file giả khỏi mọi commit; sau đó kiểm tra refs và lịch sử.

**Kết quả cần đạt:** hiểu rewrite history thay đổi commit SHA và loại nội dung file khỏi lịch sử được xử lý.

### Bước 3: Thay một chuỗi thay vì xóa file

Tạo lại repository thử nghiệm với một file có cả cấu hình hợp lệ và chuỗi giả. Dùng file quy tắc `--replace-text` để thay chuỗi giả bằng `***REMOVED***`.

**Kết quả cần đạt:** giữ nội dung hợp lệ nhưng loại chuỗi nhạy cảm khỏi các commit.

### Bước 4: Cập nhật remote và clone cộng tác

Tạo remote thử nghiệm, push history ban đầu, sau đó rewrite và force-update branch trong cửa sổ bảo trì. Dùng một clone cũ để quan sát nguy cơ đưa commit cũ trở lại; sau đó clone lại từ remote sạch.

**Kết quả cần đạt:** hiểu vì sao phải phối hợp mọi contributor và không merge branch cũ.

### Bước 5: Diễn tập incident response

Giả lập một API token test bị commit. Thu hồi token ở hệ thống cấp, cấp token mới, cập nhật workload, rewrite Git history và quét lại repository.

**Kết quả cần đạt:** thực hiện đúng thứ tự revoke/rotate trước, rewrite và cleanup sau.

## 17. Tự kiểm tra

1. Vì sao xóa secret khỏi file hiện tại không loại bỏ nó khỏi Git history?
2. Khi phát hiện secret đã commit, vì sao phải revoke/rotate trước khi rewrite history?
3. Branch, tag, fork, clone và reflog có thể giữ secret như thế nào?
4. `git-filter-repo --path ... --invert-paths` làm gì?
5. Khi file đã bị rename, cần làm gì để xóa mọi phiên bản lịch sử?
6. `--replace-text` phù hợp với tình huống nào?
7. Vì sao phải quét toàn bộ refs thay vì chỉ branch chính?
8. Force-push sau rewrite ảnh hưởng thế nào đến clone của developer?
9. Vì sao `git push --mirror` cần được kiểm tra cẩn thận trên Git provider?
10. Ngoài repository chính, những nơi nào có thể còn bản sao secret?
11. Sau khi rotate secret trong Git backend, cần xác minh Config Server và Config Client ra sao?
12. `.gitignore`, pre-commit hook và secret scanning có vai trò khác nhau thế nào?

Khi hoàn thành bài thực hành, người học có thể xử lý sự cố secret bị commit theo một quy trình đầy đủ: thu hồi credential, rewrite Git history, cập nhật remote refs, làm sạch bản sao và CI artifacts, xác minh hệ thống Spring Cloud Config dùng secret mới, đồng thời giảm nguy cơ tái diễn.

## Tài liệu tham khảo

- [GitHub Docs – Removing sensitive data from a repository](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository): phối hợp rewrite history, fork, cached views và xử lý dữ liệu nhạy cảm.
- [git-filter-repo – Documentation](https://github.com/newren/git-filter-repo): lọc đường dẫn, thay thế nội dung và viết lại lịch sử Git.
- [Git – git-push](https://git-scm.com/docs/git-push): force push, force-with-lease và cập nhật refs từ xa.
- [Git – gitignore](https://git-scm.com/docs/gitignore): quy tắc bỏ qua file chưa được track.
