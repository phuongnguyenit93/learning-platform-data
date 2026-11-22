# Cập nhật nhánh đang được xem xét sau khi nhận phản hồi

Khi một Pull Request (PR) hoặc Merge Request (MR) được mở, nhánh nguồn thường tiếp tục thay đổi trong suốt quá trình review. Người review có thể yêu cầu sửa logic, bổ sung kiểm thử, đổi tên, cập nhật tài liệu hoặc điều chỉnh cách triển khai. Người phát triển cần cập nhật đúng nhánh nguồn để các commit mới xuất hiện trong yêu cầu review đang mở.

Git cung cấp các thao tác branch, commit, fetch, merge, rebase và push để thực hiện việc này. Điều quan trọng là xác định đúng nhánh nguồn, remote chứa nhánh đó và chính sách cập nhật lịch sử của nhóm. Nếu tạo nhánh khác hoặc push nhầm đích, các thay đổi có thể không xuất hiện trong PR/MR hiện tại.

Bài học này trình bày cách tiếp nhận phản hồi, sửa trên nhánh đang được review, đồng bộ khi nhánh đích có commit mới, đẩy cập nhật lên đúng remote và theo dõi vòng review tiếp theo.

## 1. Hiểu mối quan hệ giữa PR/MR và nhánh Git

### 1.1. PR/MR theo dõi một cặp nhánh

Một yêu cầu review thường xác định:

- **Nhánh nguồn (source branch):** chứa các commit đề xuất thay đổi.
- **Nhánh đích (target/base branch):** nơi nhóm dự định tích hợp thay đổi, thường là `main`, `develop` hoặc một nhánh release.

Ví dụ, PR có thể yêu cầu tích hợp:

- Source: `feature/payment-validation`
- Target: `main`

PR/MR là chức năng của nền tảng lưu trữ mã nguồn như GitHub, GitLab hoặc dịch vụ tương tự. Git quản lý commit và nhánh; nền tảng review hiển thị diff, bình luận, trạng thái kiểm tra và quyết định phê duyệt.

Khi bạn push commit mới lên đúng nhánh nguồn, PR/MR đang theo dõi nhánh đó thường tự cập nhật diff. Không cần tạo yêu cầu review mới chỉ vì đã sửa code theo góp ý.

### 1.2. Phân biệt nhánh nguồn local và nhánh nguồn trên remote

Giả sử repository local có:

- `feature/payment-validation`: nhánh local đang làm việc.
- `origin/feature/payment-validation`: remote-tracking branch ghi nhận lần fetch gần nhất từ remote `origin`.
- PR/MR đang lấy nhánh nguồn `feature/payment-validation` từ repository `origin`.

Khi tạo commit mới trên local branch, remote branch chưa thay đổi cho đến khi push thành công. Sau khi push, nền tảng review nhận commit mới và cập nhật nội dung yêu cầu review.

Có thể xem nhánh hiện tại và nhánh theo dõi bằng:

~~~bash
git branch --show-current
git branch -vv
git status -sb
~~~

Đừng dựa vào tên nhánh hiển thị trong giao diện editor hoặc cửa sổ terminal cũ. Hãy kiểm tra trực tiếp trong repository trước khi sửa và push.

### 1.3. Remote của nhánh nguồn có thể khác remote của nhánh đích

Trong workflow dùng fork, PR có thể lấy source branch từ fork `origin`, còn target branch nằm trong repository gốc `upstream`.

Ví dụ:

- `origin/feature/payment-validation`: nhánh nguồn trong fork.
- `upstream/main`: nhánh đích trong repository chính.

Khi sửa theo review, bạn thường push lên `origin`. Khi cập nhật thay đổi mới từ nhánh đích, bạn fetch `upstream`. Cần phân biệt rõ hai remote để tránh gửi commit vào repository không đúng.

Kiểm tra:

~~~bash
git remote -v
git branch -vv
~~~

## 2. Đọc và phân loại phản hồi review

Trước khi chỉnh sửa, hãy đọc toàn bộ phản hồi đang mở và xác định phạm vi công việc. Bình luận có thể là yêu cầu bắt buộc, câu hỏi cần giải thích, đề xuất tùy chọn hoặc phát hiện lỗi mới.

Một cách phân loại hữu ích:

| Loại phản hồi | Việc cần làm |
| --- | --- |
| Lỗi logic hoặc hành vi không đúng | Xác định nguyên nhân, sửa code và kiểm thử lại |
| Thiếu trường hợp biên | Bổ sung xử lý và test cho trường hợp đó |
| Thiếu hoặc chưa phù hợp kiểm thử | Thêm, sửa hoặc chạy lại test liên quan |
| Tên, cấu trúc hoặc khả năng bảo trì | Điều chỉnh theo quy ước của dự án |
| Tài liệu chưa rõ hoặc sai | Cập nhật tài liệu và ví dụ |
| Câu hỏi hoặc đề xuất chưa rõ | Làm rõ yêu cầu trước khi thay đổi hành vi |

Không phải mọi bình luận đều yêu cầu sửa code. Nếu reviewer hỏi vì sao chọn một cách triển khai, có thể trả lời bằng lý do và bằng chứng kiểm thử. Nếu đề xuất làm thay đổi phạm vi hoặc yêu cầu nghiệp vụ, cần thống nhất trước khi mở rộng công việc.

Nên ghi lại những điểm cần xử lý và liên hệ mỗi thay đổi với bình luận tương ứng. Điều này giúp tránh bỏ sót góp ý khi PR có nhiều người review.

## 3. Cập nhật đúng nhánh nguồn đang được review

### 3.1. Kiểm tra working tree trước khi chuyển nhánh

Trước khi bắt đầu, kiểm tra trạng thái:

~~~bash
git status --short --branch
git branch --show-current
git branch -vv
~~~

Nếu đang có thay đổi chưa commit, hãy xác định chúng thuộc công việc nào. Commit hoặc stash thay đổi theo quy trình của nhóm trước khi chuyển nhánh. Không dùng `git reset --hard` chỉ để làm sạch working tree nếu chưa bảo toàn nội dung cần giữ.

### 3.2. Chuyển sang nhánh nguồn hiện tại

Nếu nhánh nguồn đã tồn tại ở local:

~~~bash
git switch feature/payment-validation
~~~

Nếu nhánh chưa có local nhưng đã tồn tại trên remote:

~~~bash
git fetch origin
git switch --track origin/feature/payment-validation
~~~

Lệnh thứ hai tạo local branch theo dõi remote branch. Hãy dùng đúng remote chứa nhánh nguồn của PR/MR. Nếu nhánh đã có ở local, không tạo một nhánh mới cùng mục đích chỉ để xử lý góp ý.

Kiểm tra lại:

~~~bash
git branch --show-current
git status -sb
git branch -vv
~~~

Tên nhánh phải trùng với source branch của yêu cầu review. Nếu PR được tạo từ fork, source branch cần thuộc đúng repository fork.

### 3.3. Đồng bộ các commit mới trên chính nhánh nguồn

Trước khi sửa, lấy trạng thái mới nhất từ remote chứa source branch:

~~~bash
git fetch origin
git status -sb
~~~

Nếu local branch đang theo dõi đúng `origin/feature/payment-validation`, phần ahead/behind trong `git status -sb` hoặc `git branch -vv` giúp nhận biết hai phía có khác biệt hay không.

Có thể xem commit chỉ có ở một phía:

~~~bash
git log --oneline --left-right HEAD...origin/feature/payment-validation
~~~

Ký hiệu `<` và `>` phân biệt commit chỉ có ở một phía. Nếu remote branch có commit mới từ người khác, hãy xem xét và tích hợp chúng trước khi tiếp tục. Không ghi đè commit của đồng đội chỉ vì local branch đang có phiên bản cũ.

Nếu nhánh chỉ do bạn quản lý và remote không có commit mới, có thể bắt đầu sửa trực tiếp trên local branch.

## 4. Sửa theo phản hồi và tạo commit

### 4.1. Thực hiện thay đổi nhỏ, có mục đích rõ ràng

Nên xử lý từng nhóm phản hồi có liên quan với nhau. Ví dụ, nếu reviewer yêu cầu kiểm tra dữ liệu đầu vào và bổ sung test, một commit có thể chứa cả phần sửa logic và test tương ứng.

Trước khi sửa, có thể xem diff của nhánh:

~~~bash
git diff origin/feature/payment-validation...HEAD
~~~

Sau khi sửa, kiểm tra các tệp thay đổi:

~~~bash
git status
git diff
~~~

Nếu có nhiều góp ý độc lập, cân nhắc tách thành các commit riêng. Lịch sử rõ ràng giúp reviewer hiểu phần nào giải quyết yêu cầu nào.

### 4.2. Chạy kiểm thử phù hợp

Không nên chỉ dựa vào việc code biên dịch thành công. Chọn kiểm thử theo loại thay đổi:

- Sửa logic: chạy test đơn vị liên quan và kiểm thử hồi quy.
- Bổ sung trường hợp biên: chạy test mới cùng test cũ.
- Thay đổi API hoặc hợp đồng: kiểm tra bên gọi và tài liệu liên quan.
- Thay đổi cấu hình hoặc build: chạy kiểm tra build phù hợp.
- Thay đổi tài liệu: kiểm tra đường dẫn, lệnh và ví dụ có còn chính xác.

Ghi nhận kết quả kiểm thử để có thể trả lời reviewer. Nếu kiểm thử không thể chạy ở môi trường hiện tại, cần nêu rõ giới hạn khi phản hồi.

### 4.3. Stage và commit thay đổi

Xem nội dung trước khi stage:

~~~bash
git diff
git status --short
~~~

Stage các tệp liên quan:

~~~bash
git add src/PaymentValidator.java
git add src/test/PaymentValidatorTest.java
~~~

Kiểm tra nội dung đã stage:

~~~bash
git diff --cached
git status
~~~

Tạo commit với thông điệp nêu rõ mục đích:

~~~bash
git commit -m "Handle empty payment reference"
~~~

Một commit bổ sung sau review thường là cách dễ theo dõi vì commit cũ vẫn giữ nguyên và reviewer có thể xem phần cập nhật riêng. Nếu nhóm yêu cầu lịch sử gọn, có thể squash ở bước tích hợp theo quy trình đã thống nhất.

### 4.4. Có nên amend commit cũ không?

`git commit --amend` thay thế commit cuối bằng một commit mới. Cách này hữu ích khi sửa lỗi nhỏ trong commit local chưa chia sẻ hoặc khi nhóm yêu cầu chuẩn bị lịch sử trước khi push.

~~~bash
git add src/PaymentValidator.java
git commit --amend
~~~

Nếu commit đã push lên nhánh nguồn mà reviewer hoặc đồng đội đang theo dõi, amend sẽ viết lại lịch sử và thay đổi mã commit. Việc cập nhật remote sau đó cần force push. Điều này có thể làm mất commit mới của người khác nếu thao tác không được phối hợp.

Với nhánh đang được review, cách ít gây xáo trộn thường là tạo commit mới cho phản hồi. Chỉ amend hoặc squash commit đã chia sẻ khi quy trình của nhóm cho phép và những người cùng làm trên nhánh đã thống nhất.

## 5. Đẩy cập nhật lên đúng nhánh để PR/MR tự làm mới

### 5.1. Kiểm tra remote và upstream

Trước khi push:

~~~bash
git branch --show-current
git branch -vv
git remote -v
git status -sb
~~~

Xác nhận:

- Nhánh hiện tại là source branch của PR/MR.
- Remote push là repository chứa source branch.
- Upstream trỏ đến đúng remote branch nếu bạn định dùng lệnh push không tham số.
- Các commit mới là những thay đổi muốn chia sẻ.

Trong workflow fork, remote push thường là `origin`, còn remote lấy nhánh đích có thể là `upstream`.

### 5.2. Push vào cùng source branch

Nếu upstream đã được cấu hình đúng:

~~~bash
git push
~~~

Nếu muốn ghi rõ đích:

~~~bash
git push origin HEAD:refs/heads/feature/payment-validation
~~~

Lệnh dùng `HEAD` làm nguồn và ghi đầy đủ tên nhánh remote làm đích. Nó giúp thể hiện rõ rằng commit hiện tại sẽ cập nhật source branch `feature/payment-validation` trên `origin`.

Nếu đây là lần đầu push nhánh lên remote và muốn thiết lập upstream:

~~~bash
git push -u origin HEAD:refs/heads/feature/payment-validation
~~~

Sau khi push thành công, nền tảng review thường tự thêm commit mới vào PR/MR hiện tại vì source branch vẫn giữ nguyên. Nếu không thấy cập nhật, kiểm tra repository nguồn, tên nhánh, quyền push và trạng thái đồng bộ của nền tảng.

### 5.3. Không tạo PR/MR mới cho cùng một nhánh

Nếu yêu cầu review hiện tại vẫn mở và bạn tiếp tục làm trên source branch đó, commit mới sẽ cập nhật yêu cầu review hiện tại. Mở một PR/MR khác cho cùng thay đổi có thể tạo hai luồng review trùng nhau và làm reviewer khó xác định nơi cần phản hồi.

Chỉ tạo yêu cầu review mới khi nhóm chủ động tách phạm vi công việc, thay đổi source branch hoặc quy trình yêu cầu một yêu cầu độc lập.

## 6. Cập nhật nhánh nguồn khi nhánh đích có commit mới

Trong thời gian review, nhánh đích như `main` có thể tiếp tục nhận commit. Nhánh nguồn lúc đó có thể cần tích hợp thay đổi mới để giải quyết xung đột hoặc chạy lại kiểm thử trên nền mới.

Có hai cách phổ biến: merge nhánh đích vào source branch hoặc rebase source branch lên nhánh đích. Chọn theo quy ước của nhóm và tình trạng chia sẻ của source branch.

### 6.1. Cách merge — giữ nguyên các commit đã chia sẻ

Ví dụ target branch là `main` trên `upstream`, còn source branch nằm trên `origin`:

~~~bash
git fetch upstream
git switch feature/payment-validation
git merge upstream/main
~~~

Nếu có xung đột, giải quyết nội dung rồi stage các tệp đã xử lý:

~~~bash
git status
git add src/PaymentValidator.java
git merge --continue
~~~

Chạy lại test và kiểm tra lịch sử:

~~~bash
git status
git log --oneline --graph --decorate -8
~~~

Sau đó push merge commit và các thay đổi lên source branch:

~~~bash
git push origin HEAD:refs/heads/feature/payment-validation
~~~

Merge tạo một commit ghi nhận việc tích hợp hai dòng lịch sử nếu không thể fast-forward. Vì các commit đã chia sẻ vẫn giữ nguyên, cách này thường dễ phối hợp khi nhiều người cùng sử dụng source branch.

### 6.2. Cách rebase — đặt lại commit của source branch trên nền mới

Rebase phát lại các commit của source branch trên một commit nền mới, tạo mã commit mới cho các commit được phát lại.

Trước khi rebase một nhánh đã push, hãy cập nhật cả remote chứa source branch và remote chứa nhánh đích. Kiểm tra xem remote source branch có commit mới mà local chưa có hay không:

~~~bash
git fetch origin
git fetch upstream
git switch feature/payment-validation
git log --oneline --left-right HEAD...origin/feature/payment-validation
~~~

Nếu phía remote có commit mà local chưa tích hợp, hãy xem nội dung và phối hợp với người đang làm trên nhánh. Tích hợp các commit đó hoặc thống nhất cách xử lý trước khi viết lại lịch sử. Không dùng force push để bỏ qua commit remote chưa được kiểm tra.

Sau khi xác nhận source branch đã đồng bộ và nhánh đích đã được fetch, thực hiện rebase:

~~~bash
git rebase upstream/main
~~~

Nếu có xung đột:

1. Xem tệp xung đột bằng `git status`.
2. Chỉnh nội dung để giữ kết quả đúng.
3. Stage các tệp đã xử lý bằng `git add`.
4. Tiếp tục bằng `git rebase --continue`.

~~~bash
git status
git add src/PaymentValidator.java
git rebase --continue
~~~

Nếu cần hủy toàn bộ thao tác rebase đang dở:

~~~bash
git rebase --abort
~~~

Sau khi rebase thành công, chạy lại test và kiểm tra lịch sử. Vì các commit đã được phát lại, source branch trên remote có thể không còn là tổ tiên của lịch sử local. Nếu nhánh đã push trước đó, việc cập nhật remote thường cần:

~~~bash
git push --force-with-lease origin HEAD:refs/heads/feature/payment-validation
~~~

Chỉ dùng cách này khi nhóm cho phép viết lại lịch sử source branch và bạn đã kiểm tra remote branch mới nhất. `--force-with-lease` từ chối cập nhật nếu remote branch đã thay đổi kể từ lần fetch dùng làm điều kiện. Tuy nhiên, nó không tự phát hiện rằng bạn đã fetch một commit remote rồi nhưng chưa tích hợp commit đó vào local; vì vậy bước kiểm tra chênh lệch trước rebase là bắt buộc. Nếu nhiều người cùng đẩy vào source branch, cần phối hợp trước khi rebase và force push.

### 6.3. Chọn merge hay rebase?

| Tiêu chí | Merge | Rebase |
| --- | --- | --- |
| Lịch sử commit đã chia sẻ | Giữ nguyên commit hiện có | Tạo lại commit được phát lại |
| Thể hiện việc tích hợp nhánh đích | Có merge commit khi cần | Lịch sử tuyến tính hơn |
| Cộng tác trên cùng source branch | Thường ít gây xáo trộn hơn | Cần phối hợp khi phải force push |
| Xử lý xung đột | Có thể xử lý trong merge | Có thể phải xử lý lại theo từng commit |
| Quy ước nhóm | Phù hợp với nhóm giữ lịch sử tích hợp | Phù hợp khi nhóm yêu cầu lịch sử tuyến tính |

Không có lựa chọn đúng cho mọi repository. Hãy theo chính sách review và tích hợp của dự án. Tránh rebase một nhánh dùng chung nếu chưa thống nhất với những người đang làm trên nhánh đó.

## 7. Theo dõi vòng review tiếp theo

Sau khi push, quay lại PR/MR và kiểm tra:

- Commit mới đã xuất hiện trong danh sách commit của yêu cầu review.
- Diff hiện tại phản ánh đúng các thay đổi sau góp ý.
- Các bình luận liên quan có thể được đánh dấu đã xử lý sau khi thay đổi tương ứng được push.
- Các cuộc hội thoại cần giải thích đã có phản hồi.
- CI, build và test tự động đã chạy lại trên commit mới.
- Reviewer có thể xem phần thay đổi mới mà không phải tìm trong một nhánh khác.

Không nên đánh dấu một bình luận là đã giải quyết chỉ vì đã sửa local. Hãy xác nhận thay đổi đã được push và kết quả đáp ứng yêu cầu. Nếu không đồng ý với góp ý, giải thích lý do và dẫn chứng như test, tài liệu hoặc quyết định kỹ thuật đã thống nhất.

Nếu CI thất bại sau khi cập nhật, đọc log để xác định lỗi đến từ commit mới, thay đổi ở nhánh đích hay môi trường kiểm thử. Sửa trên cùng source branch, tạo commit tiếp theo và push lại để cập nhật PR/MR.

## 8. Ví dụ hoàn chỉnh: sửa theo góp ý và cập nhật PR

Giả sử PR đang đề xuất nhánh `feature/payment-validation` vào `main`. Reviewer phát hiện hàm kiểm tra mã tham chiếu thanh toán chưa xử lý chuỗi rỗng và yêu cầu bổ sung test.

**Bước 1 — Chuyển đến source branch và lấy trạng thái mới nhất**

~~~bash
git fetch origin
git switch feature/payment-validation
git status -sb
git branch -vv
~~~

**Bước 2 — Sửa logic và bổ sung test**

Sau khi chỉnh `PaymentValidator` và `PaymentValidatorTest`, kiểm tra diff:

~~~bash
git diff
git status --short
~~~

**Bước 3 — Chạy test liên quan**

~~~bash
./gradlew test
~~~

Lệnh là ví dụ cho dự án Gradle; hãy dùng lệnh kiểm thử thực tế của repository.

**Bước 4 — Tạo commit cho phản hồi**

~~~bash
git add src/PaymentValidator.java
git add src/test/PaymentValidatorTest.java
git diff --cached
git commit -m "Reject empty payment reference"
~~~

**Bước 5 — Push lên đúng source branch**

~~~bash
git push origin HEAD:refs/heads/feature/payment-validation
~~~

**Bước 6 — Kiểm tra PR**

Mở lại PR hiện tại, xác nhận commit mới và diff đã được cập nhật, chờ CI chạy xong rồi phản hồi reviewer về cách xử lý chuỗi rỗng và test đã bổ sung.

Nếu nhánh đích có commit mới trong lúc review, nhóm có thể merge hoặc rebase theo chính sách. Sau thao tác đó, chạy lại test và push lên cùng source branch.

## 9. Những sai lầm thường gặp

- **Sửa trên nhánh khác source branch:** commit không xuất hiện trong PR/MR đang mở. Kiểm tra `git branch --show-current` trước khi làm.
- **Tạo PR/MR mới cho mỗi lần sửa:** làm phân tán review và bình luận. Tiếp tục push vào source branch của yêu cầu hiện tại.
- **Push lên remote chứa nhánh đích thay vì remote chứa source branch:** có thể gửi thay đổi sai repository. Kiểm tra `git remote -v` và `git branch -vv`.
- **Amend commit đã chia sẻ mà không phối hợp:** làm thay đổi mã commit và buộc phải viết lại lịch sử remote. Ưu tiên commit bổ sung nếu nhóm chưa thống nhất.
- **Force push để cập nhật sau rebase mà không kiểm tra remote:** có thể ghi đè commit mới của người khác. Fetch, xem chênh lệch và dùng `--force-with-lease` theo quy trình.
- **Đánh dấu bình luận đã giải quyết trước khi push:** reviewer chưa thể xác nhận thay đổi trên nhánh review. Chờ push thành công rồi mới cập nhật trạng thái bình luận.
- **Không chạy lại test:** commit mới có thể tạo lỗi hồi quy hoặc xung đột với nhánh đích. Chạy kiểm thử phù hợp và theo dõi CI.
- **Gộp các góp ý không liên quan vào một commit lớn:** reviewer khó kiểm tra. Tách commit theo mục đích khi điều đó giúp lịch sử rõ ràng hơn.

## 10. Bảng tra cứu nhanh

| Nhu cầu | Lệnh |
| --- | --- |
| Xem nhánh hiện tại | `git branch --show-current` |
| Xem upstream và trạng thái ahead/behind | `git branch -vv` |
| Xem remote | `git remote -v` |
| Lấy thông tin mới từ source remote | `git fetch origin` |
| Chuyển đến source branch | `git switch feature/payment-validation` |
| Xem commit khác biệt với remote branch | `git log --oneline --left-right HEAD...origin/feature/payment-validation` |
| Xem thay đổi chưa stage | `git diff` |
| Xem thay đổi đã stage | `git diff --cached` |
| Push đúng source branch | `git push origin HEAD:refs/heads/feature/payment-validation` |
| Merge nhánh đích vào source branch | `git merge upstream/main` |
| Rebase source branch lên nhánh đích | `git rebase upstream/main` |
| Tiếp tục rebase sau khi xử lý conflict | `git rebase --continue` |
| Hủy rebase đang dở | `git rebase --abort` |
| Push sau rebase theo quy trình cho phép | `git push --force-with-lease origin HEAD:refs/heads/feature/payment-validation` |

## 11. Tổng kết

Khi nhận phản hồi review, hãy quay lại đúng source branch của PR/MR, đọc trạng thái remote mới nhất, sửa theo từng nhóm góp ý, kiểm thử và tạo commit có mục đích rõ ràng. Push các commit mới lên cùng source branch để yêu cầu review hiện tại tự cập nhật.

Nếu nhánh đích có thay đổi mới, chọn merge hoặc rebase theo quy ước của nhóm. Merge thường giữ nguyên lịch sử đã chia sẻ; rebase tạo lại commit và cần phối hợp khi cập nhật một nhánh đã push. Sau mỗi lần cập nhật, kiểm tra diff, CI và các bình luận để reviewer có thể xác nhận thay đổi đã hoàn tất.

Một vòng review hiệu quả là một chu trình liên tục: nhận phản hồi, cập nhật nhánh, kiểm thử, push và xác nhận lại trên yêu cầu review. Việc giữ đúng source branch và lịch sử có thể hiểu được giúp nhóm cộng tác mà không làm mất bối cảnh của những quyết định trước đó.

