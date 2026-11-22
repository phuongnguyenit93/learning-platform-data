# Ranh giới giữa lệnh Git, chính sách nhánh và chiến lược phân nhánh của nhóm

Khi nhiều người cùng phát triển một repository, nhóm thường thống nhất cách đặt tên branch, quy định review trước khi tích hợp, yêu cầu kiểm thử và cách đưa thay đổi vào nhánh chính. Những quy định này thường được gọi chung là quy trình cộng tác hoặc chính sách nhánh. Tuy nhiên, không phải quy định nào cũng do chính Git thực thi.

Git cung cấp các thao tác và cấu trúc để tạo branch, commit, merge, rebase, fetch và push. Chiến lược phân nhánh là cách nhóm tổ chức việc sử dụng các thao tác đó. Chính sách bảo vệ branch và quyền tích hợp thường được cấu hình ở Git server hoặc nền tảng cộng tác như GitHub, GitLab hay Bitbucket. Hiểu ranh giới giữa ba lớp này giúp nhóm biết quy tắc nào chỉ là thỏa thuận, quy tắc nào được công cụ kiểm tra và nơi cần cấu hình khi muốn ngăn một thao tác không phù hợp.

## 1. Ba lớp cần phân biệt

| Lớp | Ai hoặc thành phần nào quyết định? | Ví dụ | Vai trò |
|---|---|---|---|
| Lệnh và mô hình dữ liệu Git | Git client và repository | `git branch`, `git commit`, `git merge`, `git rebase`, `git push` | Thao tác với commit, ref và nội dung repository |
| Chiến lược phân nhánh | Nhóm phát triển lựa chọn | Trunk-based development, GitHub Flow, Git Flow | Tổ chức nhánh và luồng tích hợp theo cách làm việc của nhóm |
| Chính sách nhánh và quyền tích hợp | Quản trị repository, Git server hoặc nền tảng lưu trữ | Bắt buộc pull request, yêu cầu CI pass, cấm force-push vào `main` | Kiểm soát ai được cập nhật nhánh nào và điều kiện để thay đổi được chấp nhận |

Ba lớp có liên quan nhưng không thay thế nhau. Chẳng hạn, Git cho phép người dùng tạo branch tên `feature/payment`; quy ước nhóm có thể yêu cầu mọi tính năng dùng tiền tố `feature/`; còn máy chủ có thể từ chối push nếu người dùng không có quyền hoặc branch đích đang được bảo vệ.

## 2. Git cung cấp những gì?

Git là hệ thống quản lý phiên bản phân tán. Nó quản lý nội dung và lịch sử thông qua object, commit và các tham chiếu như branch, tag. Một số thao tác cốt lõi:

- `git branch` tạo, liệt kê, đổi tên hoặc xóa branch local.
- `git switch` chuyển working tree sang branch hoặc commit khác.
- `git commit` ghi nhận nội dung đã stage thành một commit trong repository local.
- `git merge` tích hợp lịch sử từ một branch khác vào branch hiện tại.
- `git rebase` phát lại các commit trên một base mới, tạo commit mới với mã định danh mới.
- `git fetch` tải object và cập nhật remote-tracking refs theo cấu hình fetch.
- `git push` yêu cầu remote nhận các object và cập nhật ref theo refspec, nếu máy chủ cho phép.

Ví dụ, Git không bắt buộc tên branch phải theo một mẫu cụ thể. Bạn có thể tạo branch bằng:

```bash
git switch -c feature/payment
```

Tên `feature/payment` là cách đặt tên do người dùng chọn. Git hiểu đây là một branch ref; nó không tự suy ra branch đó là tính năng, bản sửa lỗi hay bản phát hành.

Tương tự, `git merge` không tự yêu cầu pull request hoặc người review. Nếu có quyền ghi trực tiếp vào một branch remote và máy chủ không đặt ràng buộc, người dùng có thể push thay đổi theo quy trình kỹ thuật của Git. Yêu cầu review phải được thiết lập bằng chính sách ở nơi nhận push hoặc được nhóm thực hiện thông qua quy trình cộng tác.

## 3. Chiến lược phân nhánh là quy ước tổ chức công việc

Chiến lược phân nhánh (*branching strategy*) mô tả nhóm tạo, duy trì và tích hợp các branch như thế nào. Git không áp đặt một chiến lược duy nhất; nhóm lựa chọn dựa trên quy mô, tốc độ phát hành, mức độ ổn định cần thiết và cách triển khai phần mềm.

### 3.1. Trunk-based development

Nhóm tập trung phát triển quanh một nhánh chính (*trunk*), thường là `main`. Thành viên tích hợp thay đổi nhỏ, thường xuyên; branch tính năng nếu có thường tồn tại trong thời gian ngắn. CI và các kỹ thuật như feature flag giúp đưa thay đổi vào trunk an toàn hơn.

```text
main:       A---B---C---D---E
                 \     /
feature:          F---G
```

Mục tiêu là giảm thời gian branch bị tách xa nhánh chính và phát hiện vấn đề tích hợp sớm. Mô hình này đòi hỏi kiểm thử tự động tốt và kỷ luật tích hợp thường xuyên.

### 3.2. GitHub Flow

Một quy trình đơn giản thường dùng một nhánh chính có thể triển khai và branch ngắn hạn cho từng thay đổi. Thành viên tạo branch, push lên remote, mở pull request, review và tích hợp sau khi đạt điều kiện của repository.

```text
main:          A---B-----------M
                    \         /
feature/profile:     C---D---E
```

Tên gọi GitHub Flow là một quy ước quy trình phổ biến, không phải một chế độ đặc biệt được bật bên trong Git. Pull request là tính năng của nền tảng lưu trữ; Git client cung cấp branch, commit, push và merge/rebase để thực hiện các bước liên quan.

### 3.3. Git Flow

Git Flow dùng các nhánh có vai trò tương đối rõ, thường gồm `main` cho lịch sử phát hành, `develop` cho tích hợp phát triển, cùng các nhánh ngắn hạn như `feature/*`, `release/*` và `hotfix/*`.

```text
main:       A-------------------R---------H
             \                 /         /
develop:      B---C---D---E----/---------/
                    \       /
feature:             F-----G
```

Mô hình này có thể phù hợp với sản phẩm phát hành theo phiên bản và cần nhánh chuẩn bị release riêng. Đổi lại, nhóm phải quản lý nhiều nhánh lâu hơn và xử lý đồng bộ giữa các nhánh vai trò. Git Flow cũng là quy ước tổ chức branch; Git không tự tạo hoặc bảo vệ các nhánh đó nếu nhóm chưa cấu hình công cụ hay quy trình hỗ trợ.

Không có chiến lược nào phù hợp với mọi nhóm. Điều quan trọng là chọn một cách làm rõ ràng, ghi lại quy tắc và bảo đảm công cụ hỗ trợ thực thi những điều kiện cần thiết.

## 4. Chính sách nhánh được thực thi ở đâu?

Chính sách nhánh (*branch policy* hoặc *branch protection rule*) là các điều kiện kiểm soát việc cập nhật một branch, đặc biệt là nhánh quan trọng như `main` hoặc `release/*`.

Những yêu cầu thường gặp:

- Chỉ một số nhóm hoặc vai trò được push trực tiếp.
- Thay đổi phải đi qua pull request hoặc merge request.
- Cần ít nhất một hoặc nhiều lượt approve từ reviewer.
- Các kiểm tra CI bắt buộc phải pass trước khi merge.
- Không cho force-push hoặc xóa branch được bảo vệ.
- Yêu cầu conversation được giải quyết trước khi tích hợp.
- Giới hạn ai được phép tạo, cập nhật hoặc xóa branch theo pattern.

Các nền tảng như GitHub, GitLab và Bitbucket cung cấp cấu hình tương ứng, với tên gọi và phạm vi khác nhau theo sản phẩm, phiên bản và gói dịch vụ. Ở mức Git server tự quản lý, quản trị viên có thể dùng quyền truy cập và server-side hooks để kiểm tra hoặc từ chối cập nhật ref.

Ví dụ về sự khác biệt:

| Quy tắc | Chỉ ghi trong tài liệu nhóm | Có thể thực thi bằng công cụ |
|---|---|---|
| Đặt tên branch theo `feature/*` | Thành viên tự tuân thủ | Server hoặc nền tảng có thể kiểm tra pattern khi tạo/push branch |
| Mỗi thay đổi cần người review | Reviewer nhớ làm theo | Bắt buộc pull request và số lượng approve tối thiểu |
| Kiểm thử phải pass | Thành viên tự chạy test | Required status checks hoặc pipeline bắt buộc |
| Không push trực tiếp vào `main` | Thành viên tự tránh | Branch protection, quyền ghi hoặc server-side hook |
| Commit message theo quy ước | Thành viên tự viết đúng | Hook hoặc quy trình kiểm tra commit message |

Một dòng trong README chỉ giúp truyền đạt quy tắc; bản thân nó không ngăn một lệnh push. Nếu yêu cầu phải được áp dụng nhất quán cho mọi người, hãy cấu hình kiểm soát ở nơi nhận thay đổi và kiểm tra quyền truy cập.

## 5. Hook ở local và hook phía server

Git hỗ trợ hook để chạy chương trình tại một số thời điểm trong vòng đời thao tác.

### Client-side hooks

Client-side hooks chạy trên máy người dùng, ví dụ:

- `pre-commit`: chạy trước khi tạo commit.
- `commit-msg`: kiểm tra thông điệp commit.
- `pre-push`: chạy trước khi push.

Nhóm có thể dùng chúng để chạy formatter, lint, test nhanh hoặc kiểm tra quy ước commit. Tuy nhiên, hook phía client nằm trong môi trường local của từng người dùng; nếu không được cài đặt hoặc được cấu hình đúng, nó không tạo thành ranh giới bảo vệ đáng tin cậy cho repository chung. Một số hook có thể bị bỏ qua bằng tùy chọn tương ứng, ví dụ `--no-verify` với các thao tác hỗ trợ tùy chọn đó.

### Server-side hooks

Với Git server tự quản lý, các hook như `pre-receive`, `update` và `post-receive` chạy ở phía nhận push. Hook `pre-receive` hoặc `update` có thể từ chối cập nhật ref khi không đáp ứng chính sách. Người dùng push từ máy cá nhân không thể vô hiệu hóa hook đang chạy ở server chỉ bằng cách thêm tùy chọn vào lệnh local.

Các nền tảng lưu trữ thường cung cấp branch protection, ruleset, merge checks hoặc pipeline thay cho việc người dùng tự viết server hook. Dù dùng cơ chế nào, điều kiện quan trọng phải được kiểm tra ở phía có quyền quyết định nhận hay từ chối cập nhật.

## 6. Merge strategy cũng là một quyết định của quy trình

Khi pull request được chấp thuận, nhóm cần thống nhất cách đưa commit vào branch đích. Các nền tảng thường cung cấp một số lựa chọn:

| Cách tích hợp | Kết quả lịch sử | Khi nào có thể phù hợp? |
|---|---|---|
| Merge commit | Tạo commit merge, giữ lại quan hệ nhánh và lịch sử hai phía | Khi muốn giữ rõ điểm tích hợp và lịch sử phân nhánh |
| Squash merge | Gộp thay đổi của branch thành một commit trên nhánh đích | Khi muốn lịch sử nhánh chính gọn theo từng thay đổi |
| Rebase and merge | Phát lại commit của branch trên base mới rồi tích hợp | Khi muốn lịch sử tuyến tính và nhóm chấp nhận việc commit được tạo lại |

Git cung cấp lệnh `merge` và `rebase`; giao diện pull request và cách nhóm chọn squash hoặc rebase merge thường do nền tảng cùng chính sách repository quyết định. Squash merge trên giao diện cũng không đơn giản tương đương với một lệnh `git merge --squash` trong mọi chi tiết quy trình, vì nền tảng còn quản lý commit kết quả và trạng thái pull request.

Nhóm nên thống nhất cách tích hợp để người phát triển hiểu lịch sử sẽ được ghi lại như thế nào, nhất là khi branch đã được chia sẻ hoặc nhiều người cùng làm việc trên đó.

## 7. Ví dụ: biến quy ước thành quy trình có thể kiểm soát

Giả sử nhóm chọn quy tắc:

1. Mọi tính năng được phát triển trên branch `feature/<ten-tinh-nang>`.
2. Nhánh `main` không nhận push trực tiếp từ thành viên phát triển.
3. Mọi thay đổi vào `main` phải qua pull request.
4. Pull request cần ít nhất một lượt approve và các kiểm tra CI bắt buộc phải pass.
5. Tích hợp bằng merge commit để giữ điểm hợp nhất trong lịch sử.

Một thành viên có thể làm việc bằng Git như sau:

```bash
# Cập nhật thông tin từ remote.
git switch main
git pull --ff-only

# Tạo branch tính năng.
git switch -c feature/user-profile

# Thực hiện thay đổi và tạo commit.
git add src/profile/UserProfileService.java
git commit -m "feat: add user profile service"

# Đẩy branch lên remote.
git push -u origin feature/user-profile
```

Sau đó, thành viên mở pull request trên nền tảng lưu trữ. Nền tảng kiểm tra reviewer và CI theo branch protection. Khi đủ điều kiện, người có quyền tích hợp merge pull request bằng phương thức nhóm đã thống nhất.

Các lệnh trên tạo branch, commit và push; chúng không tự tạo pull request, không tự yêu cầu approve và không tự bật CI. Những điều kiện đó cần được cấu hình ở nền tảng lưu trữ hoặc quy trình nhóm.

## 8. Cách xác định một quy tắc đang được thực thi hay chỉ là thỏa thuận

Khi được giao một quy trình cộng tác, hãy tự hỏi:

1. **Quy tắc nói về thao tác nào?** Ví dụ tạo branch, commit, push hay merge.
2. **Ai kiểm tra quy tắc?** Git client, hook local, Git server, nền tảng lưu trữ hay thành viên trong nhóm?
3. **Điều gì xảy ra nếu vi phạm?** Có thông báo lỗi và từ chối thao tác, hay chỉ có hướng dẫn để người dùng tự làm đúng?
4. **Quy tắc có áp dụng cho tất cả người có quyền ghi không?** Nếu không, cần xem lại quyền hoặc phạm vi bảo vệ.
5. **Có thể kiểm chứng cấu hình ở đâu?** Ví dụ branch ruleset, protected branches, required checks, repository permissions hoặc server hook.

Một quy tắc chỉ được xem là có tính cưỡng chế khi cơ chế kiểm soát thực sự được bật và bao phủ đúng branch, người dùng cùng loại thao tác cần bảo vệ. Việc một nhóm đã viết quy tắc trong tài liệu hoặc thêm hook local vào một số máy chưa đủ để kết luận mọi push đều bị kiểm soát.

## 9. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| Git tự áp dụng Git Flow | Git chỉ cung cấp thao tác và cấu trúc branch; Git Flow là chiến lược do nhóm lựa chọn |
| Đặt tên branch `main` khiến branch tự được bảo vệ | Tên branch không tạo quyền hoặc chính sách bảo vệ |
| `git merge` bắt buộc phải qua pull request | Pull request là quy trình của nền tảng cộng tác; Git có thể merge trực tiếp nếu repository và quyền cho phép |
| Có file hướng dẫn là đã ngăn được push sai | Tài liệu truyền đạt quy tắc; cần branch protection, quyền hoặc server-side hook để thực thi |
| Hook pre-commit bảo đảm mọi commit đều được kiểm tra | Hook local có thể chưa cài hoặc bị bỏ qua; kiểm tra bắt buộc nên được thực thi ở server/CI phù hợp |
| Upstream tự quyết định ai được push | Upstream giúp xác định quan hệ theo dõi; quyền ghi và chính sách nhận push do remote/server quản lý |
| Chọn rebase là bật một branching strategy | Rebase là thao tác viết lại commit trên base mới; chiến lược phân nhánh là quy ước rộng hơn về cách nhóm dùng branch |

## 10. Ghi nhớ

Git cung cấp nền tảng kỹ thuật để lưu lịch sử và phối hợp thay đổi. Nhóm lựa chọn chiến lược phân nhánh để tổ chức công việc. Quản trị viên cấu hình chính sách ở Git server hoặc nền tảng lưu trữ để kiểm soát những thao tác được phép.

Khi thiết kế quy trình cộng tác, hãy mô tả rõ branch nào được dùng cho mục đích gì, thay đổi được review và tích hợp ra sao, đồng thời xác định cơ chế nào sẽ thực thi từng điều kiện. Cách phân định này giúp thành viên biết họ cần chạy lệnh Git nào, còn người quản trị biết phải cấu hình quyền, hook hay branch protection ở đâu.
