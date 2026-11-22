# Vai trò của quyền máy chủ và bảo vệ nhánh đối với thao tác Git

## Vì sao Git cần quyền máy chủ và bảo vệ nhánh?

Git là hệ thống quản lý phiên bản phân tán. Mỗi bản clone có repository, object database, nhánh và lịch sử riêng. Bạn có thể tạo commit, tạo nhánh, merge hoặc rebase trong máy của mình mà không cần kết nối máy chủ. Những thao tác này chỉ thay đổi repository cục bộ.

Khi muốn chia sẻ commit với nhóm, bạn cần gửi thay đổi tới remote bằng git push hoặc thông qua quy trình Pull Request/Merge Request. Lúc này máy chủ sẽ xác thực danh tính, kiểm tra quyền truy cập và áp dụng chính sách của repository hoặc nhánh đích.

Điều đó tạo ra hai lớp kiểm soát khác nhau:

- **Quyền repository:** xác định ai được đọc, ghi hoặc quản trị repository.
- **Bảo vệ nhánh:** xác định những điều kiện phải đáp ứng khi tạo, cập nhật, xóa hoặc hợp nhất vào các nhánh quan trọng.

Ví dụ, một thành viên có quyền ghi repository có thể push lên nhánh feature/payment nhưng không được push trực tiếp vào main. Thành viên đó vẫn có thể tạo commit và merge cục bộ; máy chủ chỉ từ chối cập nhật main nếu thao tác không đáp ứng chính sách bảo vệ nhánh.

Git client không tự quyết định toàn bộ quyền trên remote. Máy chủ hoặc nền tảng lưu trữ Git mới là nơi thực thi quyền và chính sách cuối cùng.

## Phân biệt xác thực và phân quyền

Hai khái niệm này thường xuất hiện cùng nhau nhưng giải quyết hai câu hỏi khác nhau.

- **Xác thực (authentication):** máy chủ xác định bạn là ai.
- **Phân quyền (authorization):** sau khi biết danh tính, máy chủ xác định bạn được phép thực hiện hành động nào.

Các cách xác thực phổ biến:

- SSH key.
- HTTPS kết hợp credential manager hoặc access token.
- Tài khoản đăng nhập và cơ chế SSO của tổ chức.
- Danh tính dịch vụ hoặc bot trong CI/CD.

Sau khi xác thực, máy chủ kiểm tra quyền đọc hoặc ghi repository và các quy tắc áp dụng cho ref đích.

Ví dụ:

~~~bash
git clone <repository-url>
git fetch origin
git push origin feature/payment
~~~

Clone và fetch thường cần quyền đọc. Push cần quyền ghi phù hợp. Nếu push bị từ chối, nguyên nhân có thể là thiếu quyền ghi repository, nhánh đích bị bảo vệ, commit không đáp ứng quy tắc hoặc máy chủ không chấp nhận cập nhật ref.

Một SSH key hợp lệ chỉ chứng minh máy chủ nhận diện được danh tính tương ứng. Nó không tự cấp quyền ghi vào mọi repository hoặc mọi nhánh.

### Quyền repository thường được chia theo vai trò

Tên vai trò khác nhau giữa GitHub, GitLab, Bitbucket và máy chủ Git tự quản lý. Một mô hình thường gặp:

| Vai trò khái quát | Quyền thường có |
|---|---|
| Read | Clone, fetch, xem mã và lịch sử |
| Triage hoặc tương đương | Đọc và xử lý một số công việc như issue, không nhất thiết được push |
| Write/Developer | Push nhánh được phép, tạo Pull Request/Merge Request |
| Maintain/Maintainer | Quản lý một số thiết lập, nhãn, nhánh và quy trình repository |
| Admin/Owner | Quản trị quyền thành viên, chính sách và cấu hình bảo vệ |

Đây là mô hình khái quát, không phải bảng quyền áp dụng nguyên vẹn cho mọi nền tảng. Một vai trò có quyền ghi repository vẫn có thể bị hạn chế trên nhánh được bảo vệ.

### Quyền đọc và quyền ghi ảnh hưởng tới thao tác nào?

| Thao tác | Nơi thực hiện | Quyền thường cần |
|---|---|---|
| git status, git log, git diff | Local | Không cần kết nối máy chủ |
| git add, git commit | Local | Không cần quyền remote |
| git branch, git switch, git merge cục bộ | Local | Không cần quyền remote |
| git clone, git fetch | Remote | Quyền đọc |
| git push | Remote | Quyền ghi và chính sách ref cho phép |
| Tạo Pull Request/Merge Request | Nền tảng lưu trữ | Quyền truy cập repository và quyền tạo yêu cầu |
| Merge Pull Request vào nhánh được bảo vệ | Nền tảng hoặc server | Quyền merge và mọi điều kiện bảo vệ nhánh |
| Thay đổi branch protection/ruleset | Nền tảng quản trị | Quyền quản trị phù hợp |

Bạn có thể tạo commit thành công ngay cả khi tài khoản chỉ có quyền đọc repository. Commit đó tồn tại trong clone của bạn; máy chủ sẽ kiểm tra quyền khi bạn cố chia sẻ nó.

## Máy chủ kiểm tra điều gì khi nhận push?

Khi chạy git push, Git client gửi các object cần thiết và yêu cầu cập nhật một hoặc nhiều ref trên remote. Máy chủ kiểm tra yêu cầu trước khi thay đổi ref.

Ví dụ push một nhánh:

~~~bash
git push -u origin feature/payment
~~~

Máy chủ có thể kiểm tra:

1. Danh tính đã được xác thực.
2. Danh tính có quyền ghi vào repository hay không.
3. Nhánh đích có nằm trong phạm vi được phép push không.
4. Cập nhật có phải fast-forward theo quy tắc Git hay không.
5. Nhánh có đang bị bảo vệ bởi branch protection hoặc ruleset không.
6. Các status check, review, chữ ký commit hoặc điều kiện khác đã đạt chưa.
7. Có chính sách cấm force push, xóa nhánh hoặc cập nhật tag hay không.

Nếu bất kỳ điều kiện bắt buộc nào không đạt, máy chủ có thể từ chối cập nhật ref và trả thông báo lỗi cho client.

Một lần push có thể cập nhật nhiều ref. Vì vậy, server-side hook có thể kiểm tra từng ref hoặc từ chối toàn bộ giao dịch tùy cơ chế và chính sách máy chủ.

### Fast-forward và quyền máy chủ là hai kiểm tra khác nhau

Git thường từ chối push non-fast-forward để tránh làm mất lịch sử đã có trên remote. Đây là kiểm tra quan hệ commit, không phải kiểm tra quyền thành viên.

Ví dụ, remote main đã có commit mới mà nhánh local chưa tích hợp:

~~~text
A---B---C  origin/main
     \
      D    local main
~~~

Push local main lên origin/main có thể bị từ chối vì cập nhật không phải fast-forward. Cần fetch và tích hợp lịch sử theo quy trình nhóm.

Ngay cả khi cập nhật là fast-forward, máy chủ vẫn có thể từ chối vì main được bảo vệ hoặc người push không có quyền. Ngược lại, có quyền ghi cũng không làm cho một push non-fast-forward tự động an toàn.

## Bảo vệ nhánh là gì?

Bảo vệ nhánh (branch protection) là chính sách đặt lên một hoặc nhiều nhánh để kiểm soát cách chúng được cập nhật. Tính năng này thường do nền tảng lưu trữ Git cung cấp; bản thân Git local không có một cơ chế branch protection chung áp dụng cho mọi máy chủ.

Những nhánh thường được bảo vệ:

- main hoặc master.
- release/*.
- stable/*.
- Các nhánh phát hành dài hạn.
- Nhánh dùng để triển khai production.

Mục tiêu là giữ cho nhánh quan trọng chỉ nhận thay đổi đã được review, kiểm thử và phê duyệt theo quy trình.

Một chính sách cho main có thể yêu cầu:

- Chỉ cập nhật thông qua Pull Request/Merge Request.
- Có ít nhất một hoặc hai phê duyệt hợp lệ.
- Các status check bắt buộc phải thành công.
- Không còn cuộc thảo luận review cần giải quyết.
- Không cho force push.
- Không cho xóa nhánh.
- Yêu cầu commit được ký hoặc lịch sử tuyến tính nếu nhóm áp dụng.
- Chỉ một nhóm hoặc vai trò nhất định được phép merge.

Tên và cách cấu hình tùy nền tảng. Branch protection cũng có thể được biểu diễn bằng ruleset áp dụng theo tên nhánh, mẫu tên, repository hoặc nhóm người dùng.

## Một luồng làm việc khi main được bảo vệ

Giả sử main là nhánh tích hợp chính và nhóm không cho push trực tiếp vào đó.

~~~text
Developer
    |
    v
Tạo nhánh feature/payment
    |
    v
Commit thay đổi cục bộ
    |
    v
Push feature/payment
    |
    v
Tạo Pull Request
    |
    +----> Review và phê duyệt
    |
    +----> CI chạy status checks
    |
    +----> Giải quyết nhận xét
    |
    v
Đủ điều kiện theo branch protection
    |
    v
Merge vào main
    |
    v
Máy chủ cập nhật ref main
~~~

Các bước Git điển hình:

~~~bash
git switch -c feature/payment
# Chỉnh sửa và kiểm tra mã nguồn
git add src/
git commit -m "feat(payment): add payment validation"

git push -u origin feature/payment
~~~

Sau đó tạo Pull Request/Merge Request trên nền tảng nhóm. Người review kiểm tra thay đổi, CI chạy test và máy chủ đánh giá các điều kiện bảo vệ nhánh.

Khi tất cả điều kiện đạt và người dùng có quyền merge, nền tảng mới cập nhật main theo phương thức merge được cấu hình.

Việc push thành công lên feature/payment không có nghĩa bạn được phép push trực tiếp vào main. Quyền ghi repository và quyền cập nhật từng nhánh có thể khác nhau.

## Những quy tắc thường có trong branch protection

### Yêu cầu Pull Request/Merge Request

Chính sách có thể cấm push trực tiếp vào nhánh được bảo vệ và yêu cầu mọi thay đổi đi qua yêu cầu hợp nhất.

Lợi ích:

- Có nơi tập trung review và thảo luận.
- Lưu lại ai phê duyệt thay đổi.
- Gắn CI và kết quả kiểm tra với commit.
- Có thể yêu cầu cập nhật nhánh nguồn trước khi merge.
- Lưu lịch sử quyết định tích hợp.

Nếu push trực tiếp bị từ chối, hãy push nhánh feature và mở Pull Request/Merge Request theo quy trình.

Không phải mọi nền tảng đều gọi cùng tên. GitHub thường dùng Pull Request, GitLab dùng Merge Request; các hệ thống khác có thuật ngữ riêng.

### Yêu cầu phê duyệt review

Branch protection có thể yêu cầu một số lượng phê duyệt tối thiểu trước khi merge. Một số nền tảng hỗ trợ yêu cầu người review thuộc nhóm hoặc CODEOWNERS của các đường dẫn bị thay đổi.

Ví dụ, thay đổi trong thư mục bảo mật có thể cần người sở hữu mã nguồn phê duyệt. Chính sách cũng có thể yêu cầu review mới sau khi có commit mới hoặc vô hiệu hóa phê duyệt cũ khi thay đổi được push thêm.

Cần đọc rõ quy tắc của nền tảng: số lượng phê duyệt, người được tính là reviewer, cách xử lý review bị dismiss và ngoại lệ cho người có quyền bypass.

### Yêu cầu status checks

Status check là kết quả kiểm tra gắn với commit hoặc nhánh, thường được tạo bởi CI và các ứng dụng tích hợp.

Ví dụ các check bắt buộc:

- Build.
- Unit test.
- Integration test.
- Lint và format.
- Security scan.
- Kiểm tra license hoặc dependency.
- Kiểm tra policy của repository.

Một status check chỉ có ý nghĩa khi được tạo bởi nguồn tin cậy và được cấu hình đúng trong branch protection. Tên check trùng nhau nhưng đến từ nguồn khác nhau có thể gây nhầm lẫn tùy nền tảng.

Nếu check bắt buộc đang pending hoặc fail, máy chủ thường không cho merge. Hãy mở log CI, tìm job lỗi và sửa nguyên nhân trên nhánh nguồn.

### Yêu cầu giải quyết thảo luận review

Một số nền tảng cho phép yêu cầu tất cả conversation hoặc thread review phải được đánh dấu resolved trước khi merge.

Điều này giúp đảm bảo phản hồi quan trọng không bị bỏ qua. Đánh dấu resolved chỉ có ý nghĩa khi vấn đề đã được xử lý hoặc reviewer đồng ý; không nên đóng thread chỉ để làm nút merge sáng lên.

### Cấm force push

Force push có thể di chuyển ref remote tới lịch sử khác và làm các commit đang được người khác sử dụng không còn nằm trên nhánh đó.

Nhánh quan trọng thường cấm force push để bảo toàn lịch sử đã chia sẻ. Khi bị từ chối, dùng fetch và tích hợp lịch sử theo quy trình nhóm thay vì cố tìm cách vượt qua bảo vệ.

Ngay cả lệnh:

~~~bash
git push --force-with-lease origin main
~~~

cũng không vượt qua được chính sách server cấm force push. --force-with-lease là biện pháp bảo vệ ở phía client để giảm nguy cơ ghi đè commit mới mà bạn chưa biết; nó không cấp thêm quyền và không thay thế branch protection.

### Cấm xóa nhánh

Nhánh mặc định hoặc nhánh release có thể bị cấm xóa. Chính sách này tránh mất ref quan trọng do thao tác nhầm hoặc tài khoản bị chiếm quyền.

Ví dụ lệnh xóa nhánh remote:

~~~bash
git push origin --delete main
~~~

có thể bị máy chủ từ chối nếu nhánh được bảo vệ hoặc người dùng không có quyền xóa. Đối với nhánh feature đã hoàn tất, nền tảng có thể cho phép xóa sau khi merge tùy chính sách.

### Yêu cầu lịch sử tuyến tính hoặc kiểu merge nhất định

Một số nhóm yêu cầu lịch sử tuyến tính để dễ đọc và truy vết. Chính sách có thể cấm merge commit hoặc chỉ cho phép squash/rebase merge qua giao diện nền tảng.

Các tùy chọn này ảnh hưởng tới cách commit được đưa vào nhánh đích:

- Merge commit giữ lại commit hợp nhất và quan hệ hai nhánh.
- Squash merge gom thay đổi của nhánh nguồn thành một commit trên nhánh đích.
- Rebase merge phát lại commit theo thứ tự trên nền nhánh đích, thường tạo lịch sử tuyến tính.

Bảo vệ nhánh có thể giới hạn các kiểu merge được phép. Hãy dùng kiểu merge mà nhóm đã cấu hình, không tự suy luận từ việc lệnh git merge local chạy thành công.

### Yêu cầu commit được ký

Một tổ chức có thể yêu cầu commit có chữ ký hợp lệ để xác minh nguồn gốc và tính toàn vẹn metadata theo chính sách của họ.

Git hỗ trợ ký commit bằng GPG hoặc SSH tùy cấu hình. Ví dụ:

~~~bash
git config --global commit.gpgsign true
~~~

Lệnh này yêu cầu Git ký commit theo cơ chế ký đã được cấu hình. Việc bật tùy chọn không tự tạo khóa hoặc đảm bảo máy chủ chấp nhận chữ ký. Cần cấu hình khóa, public key và danh tính theo hướng dẫn của nền tảng.

Nếu commit không được xác minh theo chính sách, status check hoặc branch rule có thể chặn merge.

## Phân biệt quyền push và quyền merge

Push và merge là hai hành động khác nhau, có thể được cấp cho các vai trò khác nhau.

| Tình huống | Ý nghĩa |
|---|---|
| Có quyền push nhánh feature | Có thể gửi commit lên nhánh feature nếu các quy tắc cho phép |
| Không có quyền push main | Máy chủ từ chối cập nhật trực tiếp main |
| Có quyền tạo Pull Request | Có thể đề nghị tích hợp thay đổi |
| Có quyền approve | Có thể phê duyệt theo quy tắc review |
| Có quyền merge | Có thể thực hiện merge khi mọi điều kiện bắt buộc đạt |
| Có quyền quản trị | Có thể quản lý một số thiết lập repository và branch rules |

Một người có thể tạo Pull Request nhưng không có quyền merge. Người khác có quyền merge sẽ hoàn tất sau khi review và CI đạt.

Trên một số nền tảng, merge được thực hiện bởi tài khoản người bấm nút; trên nền tảng khác, một bot hoặc tài khoản dịch vụ thực hiện cập nhật ref. Dù cơ chế nào, chính sách bảo vệ nhánh vẫn được đánh giá theo cấu hình và quyền liên quan.

## Server-side hooks và vai trò kiểm soát ở máy chủ Git

Ngoài branch protection của nền tảng, máy chủ Git tự quản lý có thể dùng server-side hooks để kiểm tra push.

Một số hook quan trọng:

| Hook | Thời điểm | Vai trò |
|---|---|---|
| pre-receive | Trước khi cập nhật các ref được push | Kiểm tra toàn bộ yêu cầu và từ chối giao dịch nếu vi phạm |
| update | Trước khi cập nhật từng ref | Kiểm tra riêng từng ref và có thể từ chối ref đó |
| post-receive | Sau khi ref đã được cập nhật | Thông báo, kích hoạt CI hoặc tác vụ hậu xử lý |

Hook pre-receive nhận các dòng qua stdin theo dạng:

~~~text
<old-oid> <new-oid> <ref-name>
~~~

Mỗi dòng mô tả một ref được yêu cầu cập nhật. Hook có thể kiểm tra nhánh đích, commit mới, thông điệp commit hoặc chính sách nội bộ. Nếu hook trả mã khác 0, máy chủ từ chối giao dịch nhận tương ứng.

Hook update thường được gọi riêng cho từng ref và nhận tên ref cùng mã commit cũ/mới qua tham số. Hook này có thể từ chối một ref cụ thể.

Hook post-receive chạy sau khi ref đã được cập nhật. Nó phù hợp để gửi thông báo hoặc kích hoạt tác vụ tiếp theo; trả mã lỗi ở giai đoạn này không thể hoàn tác việc cập nhật ref đã hoàn tất.

Server-side hook được quản trị viên cài và kiểm soát trên máy chủ. Người dùng clone repository không thể tự cài hook pre-receive cho remote bằng cách commit một file vào dự án.

### Cấu hình máy chủ có thể từ chối cập nhật không an toàn

Với máy chủ Git tự quản lý, quản trị viên có thể sử dụng các thiết lập nhận push như:

- receive.denyNonFastForwards: từ chối cập nhật non-fast-forward trong những trường hợp cấu hình áp dụng.
- receive.denyDeletes: từ chối yêu cầu xóa ref.
- receive.denyCurrentBranch: kiểm soát push vào nhánh đang được checkout trong repository không bare.

Các thiết lập này thuộc quản trị máy chủ, không phải lệnh cấu hình local để người dùng tự cấp quyền. Hành vi thực tế còn phụ thuộc loại repository và cấu hình server.

Không nhầm server-side hook với client-side hook:

- pre-push chạy trên máy người dùng trước khi gửi push.
- pre-receive và update chạy trên máy chủ khi nhận push.
- Client-side hook có thể bị bỏ qua hoặc không được cài.
- Server-side hook nằm trong vùng kiểm soát của máy chủ và được thực thi với mọi yêu cầu đi qua cơ chế nhận push tương ứng.

## Branch protection không thay thế quyền repository

Một nhánh được bảo vệ không có nghĩa mọi người đều có quyền đọc repository. Quyền đọc và ghi vẫn được kiểm tra ở cấp repository hoặc tổ chức.

Tương tự, quyền ghi repository không đồng nghĩa có quyền cập nhật mọi nhánh. Một người có thể push nhánh cá nhân nhưng bị chặn ở main.

Có thể hình dung thứ tự kiểm tra như sau:

1. Xác thực danh tính.
2. Kiểm tra quyền truy cập repository.
3. Xác định ref đích và quyền cập nhật ref.
4. Áp dụng branch protection, ruleset và server-side policy.
5. Kiểm tra quan hệ commit và các điều kiện bắt buộc.
6. Chấp nhận hoặc từ chối cập nhật.

Chi tiết triển khai có thể khác giữa nền tảng. Một số kiểm tra diễn ra ở các lớp hoặc thời điểm khác nhau, nhưng nguyên tắc là quyền repository và chính sách nhánh cùng quyết định thao tác có được chấp nhận hay không.

## Ví dụ chính sách cho repository nhóm

Giả sử nhóm có ba loại nhánh:

- main: nhánh tích hợp và phát hành.
- release/*: nhánh bảo trì phiên bản.
- feature/*: nhánh phát triển tính năng.

Một chính sách có thể được thiết kế như sau:

| Quy tắc | main | release/* | feature/* |
|---|---|---|---|
| Push trực tiếp | Chặn | Chỉ Maintainer | Cho phép theo quyền ghi |
| Pull/Merge Request | Bắt buộc | Bắt buộc | Không bắt buộc |
| Review | 2 phê duyệt | 1 phê duyệt | Theo nhóm |
| CI bắt buộc | Build, test, security | Build, regression | CI cơ bản |
| Force push | Chặn | Chặn | Theo chính sách |
| Xóa nhánh | Chặn | Chặn khi còn hỗ trợ | Có thể xóa sau merge |
| Merge method | Squash hoặc merge commit theo quy ước | Merge commit theo quy trình release | Tùy chọn |

Đây là ví dụ để thảo luận, không phải cấu hình mặc định. Nhóm cần chọn quy tắc dựa trên mức độ quan trọng của nhánh, khả năng kiểm thử, quy mô review và quy trình phát hành.

### Phân quyền theo nhóm thay vì từng cá nhân

Để quản lý lâu dài, nên cấp quyền thông qua team hoặc group:

- Developer: push nhánh feature và tạo yêu cầu merge.
- Reviewer: review và approve theo phạm vi sở hữu.
- Release manager: merge hoặc quản lý nhánh release.
- Repository administrator: thay đổi branch protection và thành viên.

Cấp quyền theo nhóm giúp onboarding và offboarding nhất quán hơn. Khi một thành viên đổi vai trò, quản trị viên thay đổi membership thay vì chỉnh nhiều quyền riêng lẻ.

Dùng nguyên tắc least privilege: chỉ cấp quyền cần thiết cho nhiệm vụ. Hạn chế số người có quyền bypass branch protection hoặc thay đổi ruleset.

## Cách chẩn đoán khi push hoặc merge bị từ chối

Khi nhận lỗi, trước tiên đọc đầy đủ thông báo từ server. Các thông báo có thể khác nhau theo nền tảng và ngôn ngữ.

### Kiểm tra remote và nhánh hiện tại

~~~bash
git remote -v
git branch --show-current
git status -sb
git branch -vv
~~~

Xác nhận đang push tới đúng remote và đúng nhánh. Nếu remote URL sai, bạn có thể đang gửi commit tới repository khác hoặc dùng credential không đúng.

Kiểm tra quyền đọc bằng fetch:

~~~bash
git fetch origin
~~~

Fetch thành công cho thấy danh tính có thể đọc remote và truy cập các ref được phép. Nó không chứng minh bạn có quyền ghi.

Có thể liệt kê các nhánh remote nhìn thấy:

~~~bash
git ls-remote --heads origin
~~~

Kết quả phụ thuộc quyền đọc và cấu hình server; một số ref có thể bị ẩn theo chính sách.

### Phân loại thông báo lỗi

| Thông báo hoặc hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Authentication failed | Credential hoặc SSH key không hợp lệ | Kiểm tra tài khoản, key và credential manager |
| Repository not found | URL sai hoặc tài khoản không có quyền đọc | Xác minh URL và quyền truy cập |
| Permission denied | Thiếu quyền ghi hoặc xác thực không đúng | Xác minh danh tính và vai trò repository |
| Protected branch hook declined | Nhánh bị bảo vệ hoặc vi phạm branch rule | Mở Pull Request/Merge Request, đáp ứng policy |
| Required status check is missing | CI chưa chạy hoặc check bắt buộc chưa được báo cáo | Kiểm tra pipeline và tên check |
| Review required | Chưa đủ phê duyệt | Chờ review hợp lệ và xử lý nhận xét |
| Non-fast-forward | Remote có commit mà local chưa tích hợp | Fetch và merge/rebase theo quy ước |
| Force push prohibited | Server cấm viết lại lịch sử nhánh | Dùng quy trình cập nhật lịch sử được nhóm cho phép |
| Cannot delete protected branch | Nhánh được bảo vệ khỏi xóa | Giữ nhánh hoặc yêu cầu quản trị viên theo quy trình |

Không dùng git push --force để xử lý mọi lỗi push. Force push không sửa được lỗi xác thực, thiếu quyền hoặc status check thất bại; nó còn có thể làm mất lịch sử nếu server cho phép.

### Quy trình khi main bị bảo vệ

Nếu bạn đã commit trên main cục bộ và push bị từ chối do nhánh được bảo vệ, hãy kiểm tra chính sách và trao đổi với nhóm để đưa commit vào nhánh feature rồi mở yêu cầu merge.

Có thể tạo nhánh từ commit hiện tại:

~~~bash
git switch -c feature/recover-main-work
git push -u origin feature/recover-main-work
~~~

Sau đó tạo Pull Request/Merge Request vào main. Nếu main local đã có commit mà remote chưa nhận, nhánh mới sẽ giữ commit đó để review. Hãy kiểm tra lịch sử và trạng thái trước khi di chuyển hoặc reset nhánh main local; không xóa commit chỉ vì push trực tiếp bị từ chối.

## Xử lý khi cần cập nhật khẩn cấp

Một số tình huống production có thể cần sửa lỗi khẩn cấp. Quy trình bảo vệ nhánh vẫn cần được tôn trọng theo chính sách của tổ chức.

Một luồng khẩn cấp có thể gồm:

1. Tạo nhánh hotfix từ commit phát hành phù hợp.
2. Thực hiện sửa lỗi nhỏ, có phạm vi rõ.
3. Chạy test mục tiêu.
4. Yêu cầu review nhanh từ người có trách nhiệm.
5. Đáp ứng các status check tối thiểu đã quy định.
6. Merge vào nhánh phát hành và main theo quy trình.
7. Ghi lại lý do, người phê duyệt và các bước hậu kiểm.

Nếu tổ chức có cơ chế bypass cho incident, chỉ người hoặc vai trò được ủy quyền mới sử dụng. Ghi lại lý do và kiểm tra lại sau sự cố. Không nên cấp quyền bypass thường trực cho mọi thành viên chỉ để giảm thời gian chờ.

## Bảo vệ tag và nhánh phát hành

Tag thường được dùng đánh dấu phiên bản phát hành. Một tag đã được công bố có thể được hệ thống triển khai hoặc người dùng bên ngoài tham chiếu.

Một số nền tảng cho phép bảo vệ tag theo mẫu như v* hoặc release-*. Chính sách có thể giới hạn ai được tạo, cập nhật hoặc xóa tag.

Ví dụ tạo và push tag:

~~~bash
git tag -a v2.1.0 -m "Release v2.1.0"
git push origin v2.1.0
~~~

Máy chủ có thể từ chối nếu người dùng không được phép tạo tag theo mẫu được bảo vệ. Không xóa hoặc di chuyển tag phát hành đã chia sẻ nếu chưa có quy trình phát hành cho phép.

Tag annotated có metadata và chữ ký tùy cấu hình. Việc bảo vệ tag giúp giữ mốc phát hành ổn định và hạn chế thay đổi ngoài ý muốn.

## Những điều branch protection không làm

Branch protection là một lớp kiểm soát cập nhật ref, không phải giải pháp bảo mật toàn diện.

Nó không tự:

- Thu hồi bản clone hoặc dữ liệu mà thành viên đã tải trước đó.
- Ngăn người có quyền đọc sao chép mã nguồn.
- Phát hiện mọi secret đã tồn tại trong lịch sử.
- Thay thế kiểm tra dependency, mã độc hoặc lỗ hổng.
- Bảo vệ thông tin xác thực bị lộ.
- Thay thế backup và kế hoạch phục hồi.
- Đảm bảo CI được cấu hình đúng hoặc mọi test đều có chất lượng.

Nếu cần thu hồi quyền truy cập, quản trị viên phải cập nhật membership, token, SSH key hoặc SSO theo quy trình. Nếu credential bị lộ, cần thu hồi hoặc xoay vòng credential và đánh giá phạm vi ảnh hưởng; chỉ xóa dòng chứa secret trong commit mới là chưa đủ.

## Checklist thiết kế quyền và bảo vệ nhánh

- [ ] Phân biệt rõ quyền đọc, ghi, review, merge và quản trị.
- [ ] Cấp quyền theo nhóm và nguyên tắc least privilege.
- [ ] Bảo vệ nhánh mặc định và nhánh release quan trọng.
- [ ] Quy định nhánh nào được push trực tiếp.
- [ ] Yêu cầu Pull Request/Merge Request khi phù hợp.
- [ ] Xác định số lượng và phạm vi reviewer cần thiết.
- [ ] Cấu hình status check bắt buộc từ CI tin cậy.
- [ ] Quy định cách xử lý conversation review chưa resolved.
- [ ] Chặn force push và xóa nhánh quan trọng.
- [ ] Chọn merge method và yêu cầu chữ ký nếu cần.
- [ ] Giới hạn người được bypass và ghi nhận ngoại lệ.
- [ ] Bảo vệ tag phát hành theo quy ước.
- [ ] Dùng server-side hook hoặc CI cho chính sách cần thực thi tập trung.
- [ ] Kiểm tra quyền truy cập khi onboarding, đổi vai trò và offboarding.

## Checklist khi thao tác Git trên repository có nhánh được bảo vệ

- [ ] Đã xác nhận remote và nhánh đích.
- [ ] Đã fetch để cập nhật trạng thái remote cần thiết.
- [ ] Đã làm việc trên nhánh feature hoặc hotfix phù hợp.
- [ ] Đã commit và push nhánh nguồn.
- [ ] Đã tạo Pull Request/Merge Request nếu chính sách yêu cầu.
- [ ] Đã có đủ review và status check.
- [ ] Đã giải quyết các nhận xét cần xử lý.
- [ ] Đã dùng merge method được phép.
- [ ] Đã kiểm tra kết quả sau merge.
- [ ] Không dùng force push hoặc bypass ngoài quy trình được phê duyệt.

## Ghi nhớ

Git cho phép bạn tạo commit và thao tác lịch sử trong repository cục bộ, nhưng máy chủ quyết định ai được đọc, push, merge hoặc quản trị repository. Branch protection bổ sung quy tắc cho các nhánh quan trọng như main và release: yêu cầu review, status check, cấm push trực tiếp, force push hoặc xóa nhánh. Quyền ghi repository không đồng nghĩa có quyền cập nhật mọi nhánh. Khi push bị từ chối, hãy phân biệt lỗi xác thực, quyền repository, chính sách nhánh và non-fast-forward; sau đó đi theo quy trình Pull Request/Merge Request và đáp ứng điều kiện máy chủ. Client-side hook hỗ trợ phản hồi sớm, còn CI, branch protection và server-side hook mới là nơi thực thi chính sách tập trung.

