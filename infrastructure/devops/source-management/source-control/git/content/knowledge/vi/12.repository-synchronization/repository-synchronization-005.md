# Đẩy đúng nhánh và refspec bằng git push

Khi làm việc với repository từ xa, `git push` gửi các commit từ repository cục bộ lên một remote. Một lệnh push có thể đẩy một nhánh, nhiều nhánh, một tag hoặc thậm chí ánh xạ nhánh local sang một tên nhánh khác trên remote. Muốn kiểm soát chính xác kết quả, cần hiểu **refspec**: quy tắc chỉ rõ nguồn nào được gửi và đích nào được cập nhật.

Điểm dễ nhầm nhất là tên nhánh được ghi trong lệnh là tên nhánh local hay tên nhánh remote. Trong `git push origin main`, Git lấy nhánh local `main` và đẩy lên nhánh `main` của remote `origin`. Nếu đang đứng ở nhánh `feature/cart`, lệnh đó vẫn đẩy nhánh local `main`, không tự động đẩy nhánh hiện tại.

## 1. Git push thực hiện điều gì?

Một repository Git có thể chứa nhiều nhánh và tag. Khi push, Git gửi các đối tượng commit cần thiết tới repository đích, sau đó yêu cầu cập nhật những tham chiếu được chỉ định, chẳng hạn nhánh `refs/heads/main`.

Ví dụ:

~~~bash
git push origin main
~~~

Lệnh trên có ba thành phần:

- `push`: gửi commit và cập nhật ref ở repository đích.
- `origin`: remote nhận dữ liệu.
- `main`: nhánh local được chọn làm nguồn; trong dạng viết ngắn này, Git cũng suy ra nhánh remote đích cùng tên.

Nếu remote từ chối cập nhật, nhánh trên remote không được thay đổi theo yêu cầu đó. Nguyên nhân có thể là lịch sử không thể fast-forward, thiếu quyền, nhánh được bảo vệ hoặc cấu hình máy chủ.

Push không đồng nghĩa với việc hợp nhất Pull Request/Merge Request. Push chỉ cập nhật ref trên remote theo quyền và quy tắc máy chủ; quy trình review và merge thường diễn ra ở bước riêng.

## 2. Cú pháp và cấu trúc refspec

Cú pháp tổng quát thường dùng:

~~~bash
git push [options] <remote> <refspec>...
~~~

Một refspec tường minh có dạng:

~~~text
<src>:<dst>
~~~

Trong đó:

- `<src>` là nguồn trong repository local, thường là tên nhánh, tag hoặc `HEAD`.
- `<dst>` là ref sẽ được cập nhật ở repository remote, thường là nhánh hoặc tag.
- Dấu hai chấm `:` phân cách nguồn và đích.

Ví dụ:

~~~bash
git push origin feature/cart:feature/cart
~~~

Git lấy nhánh local `feature/cart` và cập nhật nhánh `feature/cart` trên `origin`.

Có thể viết đích đầy đủ để tránh nhầm loại ref:

~~~bash
git push origin refs/heads/feature/cart:refs/heads/feature/cart
~~~

`refs/heads/` là không gian tên dành cho branch. Tag nằm trong `refs/tags/`. Khi dùng tên ngắn, Git cố gắng diễn giải theo ngữ cảnh; tên ref đầy đủ giúp lệnh rõ ràng hơn khi có tên dễ gây nhầm.

### Đọc nguồn và đích như một phép ánh xạ

Giả sử repository local có nhánh `feature/cart`, còn nhóm muốn nhánh đó xuất hiện trên remote với tên `review/cart-checkout`:

~~~bash
git push origin feature/cart:refs/heads/review/cart-checkout
~~~

Ánh xạ có thể hình dung như sau:

~~~text
Repository local                         Remote origin
refs/heads/feature/cart  ------------->  refs/heads/review/cart-checkout
       nguồn                                  đích
~~~

Tên sau dấu hai chấm quyết định ref trên remote sẽ được cập nhật. Nếu đổi thứ tự hai phần, ý nghĩa lệnh cũng đổi. Hãy luôn đọc refspec từ trái sang phải: **lấy nguồn nào, gửi tới đích nào**.

### Refspec dùng ký tự đại diện

Khi cần ánh xạ nhiều nhánh theo cùng một quy tắc, refspec có thể dùng ký tự đại diện `*` ở cả nguồn và đích:

~~~bash
git push origin 'refs/heads/release/*:refs/heads/archive/*'
~~~

Ví dụ, nhánh local `release/1.x` được ánh xạ thành `archive/1.x` trên remote. Mẫu này phù hợp với quy trình có quy tắc tên nhánh nhất quán; trước khi dùng, hãy chắc chắn mẫu khớp đúng các nhánh muốn gửi.

Một dấu cộng `+` ở đầu refspec cho phép cập nhật cưỡng bức đích đó, kể cả khi cập nhật không fast-forward:

~~~bash
git push origin +feature/cart:refs/heads/feature/cart
~~~

Đây là cách ghi force ngay trong refspec. Chỉ dùng khi chủ động thay thế lịch sử ở đích; phần về force push bên dưới giải thích cách cân nhắc `--force-with-lease`.

## 3. Đẩy nhánh hiện tại và tránh chọn nhầm nhánh

### Đẩy một nhánh có tên cụ thể

~~~bash
git push origin main
git push origin feature/cart
~~~

Mỗi lệnh chọn đúng nhánh local được ghi trong lệnh. Vị trí con trỏ hiện tại không thay đổi ý nghĩa của tên nhánh tường minh.

Kiểm tra nhánh hiện tại:

~~~bash
git branch --show-current
~~~

Kiểm tra các nhánh local:

~~~bash
git branch
~~~

Nếu đang đứng trên `feature/cart` nhưng chạy `git push origin main`, Git vẫn đẩy `main`. Đây là nguyên nhân phổ biến khiến người mới tưởng rằng Git đã gửi nhánh đang làm việc.

### Đẩy nhánh hiện tại sang nhánh remote có tên khác

Dùng `HEAD` làm nguồn để chỉ commit mà nhánh hiện tại đang trỏ tới, rồi ghi rõ đích:

~~~bash
git push origin HEAD:refs/heads/review/cart-checkout
~~~

Lệnh này đẩy trạng thái hiện tại lên nhánh remote `review/cart-checkout`. Nó hữu ích khi muốn gửi một nhánh local có tên riêng lên nhánh review hoặc nhánh thử nghiệm trên máy chủ.

### Thiết lập upstream sau lần push đầu

Khi tạo nhánh local mới và muốn theo dõi nhánh remote cùng tên:

~~~bash
git switch -c feature/cart
# chỉnh sửa và commit
git push --set-upstream origin feature/cart
~~~

Có thể viết ngắn tùy chọn `--set-upstream` thành `-u`. Sau khi push thành công, Git ghi nhận quan hệ theo dõi giữa nhánh local và nhánh remote. Khi đang ở nhánh đó, các lần sau thường có thể dùng:

~~~bash
git push
git pull
~~~

Quan hệ upstream giúp Git suy ra remote và nhánh theo dõi trong các lệnh không ghi rõ đích. Nó không có nghĩa mọi lần push đều tự động gửi mọi nhánh.

## 4. Đẩy nhiều nhánh trong một lần

Có thể truyền nhiều refspec trên cùng một lệnh:

~~~bash
git push origin main feature/cart feature/search
~~~

Git sẽ đẩy các nhánh local được liệt kê tới các nhánh cùng tên trên remote. Nếu một refspec bị từ chối, hãy đọc kết quả cho từng ref để biết ref nào đã được cập nhật và ref nào thất bại.

Khi cần ánh xạ tên khác nhau, ghi rõ từng cặp nguồn và đích:

~~~bash
git push origin main:refs/heads/stable feature/cart:refs/heads/review/cart
~~~

Không nên thêm nhiều nhánh theo thói quen nếu mục tiêu chỉ là gửi một nhánh tính năng. Ghi đúng refspec giúp giới hạn phạm vi thay đổi trên remote.

## 5. Đẩy tag

Tag thường đánh dấu phiên bản hoặc một mốc phát hành. Để đẩy một tag cụ thể:

~~~bash
git push origin v1.4.0
~~~

Có thể ghi đầy đủ loại ref:

~~~bash
git push origin refs/tags/v1.4.0:refs/tags/v1.4.0
~~~

Để đẩy tất cả tag local lên remote:

~~~bash
git push origin --tags
~~~

Tùy chọn `--follow-tags` có hành vi hẹp hơn: ngoài các ref đã push, Git đẩy thêm các annotated tag có thể tiếp cận từ những commit đang được push và chưa tồn tại trên remote. Đây thường là lựa chọn phù hợp khi muốn gửi tag phát hành liên quan tới các commit vừa đẩy.

Tag đã phát hành thường được xem là mốc cần giữ ổn định. Trước khi thay đổi hoặc ghi đè tag trên remote, hãy kiểm tra quy ước phát hành của nhóm.

## 6. Xóa nhánh trên remote

Để xóa nhánh remote, có thể dùng tùy chọn dễ đọc:

~~~bash
git push origin --delete feature/old-checkout
~~~

Cách viết refspec tương đương là để trống nguồn:

~~~bash
git push origin :refs/heads/feature/old-checkout
~~~

Trong trường hợp này, dấu hai chấm báo Git xóa ref đích. Lệnh xóa nhánh trên remote; nhánh local cùng tên vẫn còn cho đến khi bạn tự xóa bằng lệnh local, ví dụ:

~~~bash
git branch -d feature/old-checkout
~~~

Chỉ xóa nhánh remote khi chắc chắn nhánh đã được hợp nhất hoặc nhóm không còn cần nó. Máy chủ có thể từ chối xóa nhánh được bảo vệ.

## 7. Refspec mặc định và cấu hình push

Khi chạy `git push` mà không chỉ rõ remote hoặc refspec, Git phải suy ra nơi gửi và nhánh cần gửi từ cấu hình.

Một số cấu hình liên quan:

| Cấu hình | Vai trò |
|---|---|
| `branch.<name>.pushRemote` | Remote ưu tiên để push riêng cho nhánh đó |
| `remote.pushDefault` | Remote mặc định để push cho repository |
| `branch.<name>.remote` | Remote mà nhánh local theo dõi để lấy thay đổi |
| `remote.<name>.push` | Refspec mặc định khi push tới remote đó mà lệnh không cung cấp refspec |
| `push.default` | Quy tắc chọn nhánh khi không có refspec tường minh hoặc refspec mặc định riêng |

### Các giá trị thường gặp của push.default

Xem giá trị hiện tại:

~~~bash
git config --get push.default
~~~

Các chế độ phổ biến:

| Giá trị | Hành vi |
|---|---|
| `simple` | Chế độ mặc định phổ biến; trong workflow tập trung, push nhánh hiện tại tới upstream khi tên nhánh phù hợp và báo lỗi nếu tên không khớp. Khi push tới remote khác remote dùng để pull (workflow fork), hành vi giống `current` |
| `current` | Push nhánh hiện tại tới nhánh cùng tên trên remote được chọn |
| `upstream` | Push nhánh hiện tại tới nhánh upstream đã cấu hình |
| `matching` | Push các nhánh local có tên tương ứng với nhánh đã tồn tại trên remote |
| `nothing` | Không suy ra nhánh để push; cần chỉ rõ refspec |

Với người mới, giữ chế độ `simple` thường giúp tránh đẩy nhầm nhánh khi tên nhánh local và upstream không khớp. Chế độ `matching` có thể đẩy nhiều nhánh hơn dự định, vì vậy cần hiểu rõ trước khi sử dụng.

Có thể đặt cấu hình ở cấp repository:

~~~bash
git config push.default simple
~~~

Thêm `--global` nếu muốn áp dụng cho các repository của người dùng hiện tại:

~~~bash
git config --global push.default simple
~~~

Cấu hình global ảnh hưởng nhiều dự án, nên chỉ thay đổi khi đã hiểu tác động. Trong môi trường có fork, remote dùng để fetch và remote dùng để push có thể khác nhau; cấu hình `pushRemote` hoặc `remote.pushDefault` giúp chỉ định đích push phù hợp.

## 8. Kiểm tra trước khi push

Trước khi gửi commit lên máy chủ, nên xác minh nhánh, remote và thay đổi đang có:

~~~bash
# Xác nhận repository và nhánh hiện tại
git status
git branch --show-current

# Xem các remote và URL
git remote -v

# Xem commit gần nhất của nhánh hiện tại
git log -1 --oneline

# Xem các nhánh local
git branch
~~~

Có thể xem các nhánh đang tồn tại trên remote:

~~~bash
git ls-remote --heads origin
~~~

Lệnh này truy vấn các branch refs trên remote `origin`; nó không cập nhật remote-tracking branch trong repository local như `git fetch`.

Dùng `--dry-run` để xem Git dự định push gì mà không cập nhật remote:

~~~bash
git push --dry-run origin feature/cart:refs/heads/review/cart
~~~

`--dry-run` hữu ích để rà lại refspec, nhưng không đảm bảo lần push thật sẽ thành công: quyền, trạng thái remote hoặc chính sách máy chủ có thể thay đổi sau đó.

## 9. Khi push bị từ chối

### Non-fast-forward

Ví dụ:

~~~text
! [rejected]  main -> main (non-fast-forward)
error: failed to push some refs
~~~

Remote có commit mà nhánh local chưa tích hợp, nên cập nhật theo cách thông thường sẽ làm mất lịch sử trên remote. Hãy lấy thông tin mới và xem lịch sử:

~~~bash
git fetch origin
git log --oneline --graph --decorate --all
~~~

Sau đó tích hợp nhánh remote vào nhánh local theo quy trình của nhóm, bằng merge hoặc rebase, giải quyết xung đột nếu có, rồi push lại.

### Không có quyền hoặc nhánh được bảo vệ

Nếu máy chủ báo thiếu quyền, xác thực thất bại hoặc nhánh được bảo vệ, refspec đúng vẫn không giúp push thành công. Kiểm tra URL, tài khoản, SSH key/token, quyền ghi và chính sách bảo vệ nhánh. Với nhánh chính được bảo vệ, thông thường cần push nhánh tính năng rồi tạo Pull Request/Merge Request.

### Refspec không khớp

Các lỗi như `src refspec ... does not match any` thường xuất hiện khi tên nguồn không tồn tại, nhánh chưa được tạo hoặc repository chưa có commit phù hợp.

Kiểm tra tên nhánh và commit:

~~~bash
git branch --list
git show-ref
git status
~~~

Sửa nguồn trong refspec cho đúng với nhánh hoặc tag thực tế trước khi push lại.

## 10. Force push và cách bảo vệ lịch sử

Một cập nhật bị từ chối đôi khi là do lịch sử đã được viết lại bằng rebase hoặc amend. Git mặc định chặn cập nhật không fast-forward để tránh ghi đè commit mà người khác có thể đang dựa vào.

`--force` buộc cập nhật ref đích:

~~~bash
git push --force origin feature/cart
~~~

Lệnh này có thể làm mất commit đang có trên remote nếu chúng không nằm trong lịch sử được gửi lên. Chỉ dùng khi bạn hiểu lịch sử sẽ bị thay thế và đã phối hợp với người liên quan.

Trong nhiều trường hợp, `--force-with-lease` an toàn hơn:

~~~bash
git push --force-with-lease origin feature/cart
~~~

Git chỉ cho phép cập nhật cưỡng bức nếu ref remote vẫn ở giá trị mà local dự kiến, thường được đối chiếu với remote-tracking ref đã biết. Điều này giúp phát hiện việc người khác vừa cập nhật remote sau lần bạn kiểm tra. Với yêu cầu kiểm soát chặt hơn, có thể chỉ rõ giá trị kỳ vọng:

~~~bash
git push --force-with-lease=refs/heads/feature/cart:<expected-object-id> origin feature/cart
~~~

Ngay cả `--force-with-lease` cũng cần được dùng có chủ đích. Hãy fetch và kiểm tra lịch sử trước khi viết lại nhánh dùng chung. Không force push lên nhánh chính hoặc nhánh được chia sẻ nếu chưa có sự đồng thuận và quy trình cho phép.

## 11. Ví dụ thực tế: gửi nhánh tính năng để review

Giả sử bạn đang phát triển tính năng giỏ hàng. Nhánh local tên `feature/cart`, và nhóm muốn tạo nhánh review `review/cart-checkout` trên remote `origin`.

1. Xác nhận đang ở đúng repository và nhánh:

~~~bash
git status
git branch --show-current
~~~

2. Xem các commit sẽ gửi và cập nhật thông tin remote nếu cần:

~~~bash
git fetch origin
git log --oneline --decorate origin/main..feature/cart
~~~

3. Đẩy nhánh local sang nhánh review có tên khác, đồng thời thiết lập upstream:

~~~bash
git push --set-upstream origin feature/cart:review/cart-checkout
~~~

Vì tên nhánh local và remote khác nhau, chế độ `push.default=simple` có thể từ chối một lệnh `git push` trần ở lần sau. Khi tiếp tục dùng tên đích khác, hãy ghi rõ refspec; hoặc thống nhất cấu hình push phù hợp với workflow của nhóm.

4. Kiểm tra nhánh remote đã xuất hiện:

~~~bash
git ls-remote --heads origin review/cart-checkout
~~~

5. Tạo Pull Request/Merge Request từ `review/cart-checkout` về nhánh đích của dự án theo quy trình nhóm.

Nếu nhóm muốn đích review luôn trùng tên local, dùng `git push -u origin feature/cart` sẽ đơn giản hơn. Điều cần xác định trước khi push là nguồn local và đích remote có đúng với mục tiêu review hay không.

## 12. Những điều cần nhớ

- Refspec có dạng `<src>:<dst>`: bên trái là nguồn local, bên phải là ref đích trên remote.
- `git push origin main` đẩy nhánh local `main`; nó không có nghĩa “đẩy nhánh đang checkout”.
- Dùng `HEAD:refs/heads/<ten-nhanh>` khi muốn gửi nhánh hiện tại tới một tên nhánh remote cụ thể.
- Dùng `-u` để thiết lập upstream sau lần push đầu tiên.
- Có thể đẩy nhiều nhánh, tag hoặc xóa nhánh remote bằng refspec và các tùy chọn tương ứng.
- Khi không ghi refspec, Git dựa vào cấu hình remote và `push.default`; hãy hiểu cấu hình trước khi dùng lệnh rút gọn.
- Dùng `--dry-run` để xem dự định push. Chỉ force push khi đã hiểu tác động lên lịch sử và phối hợp với nhóm.

Một lệnh push an toàn bắt đầu bằng việc xác định rõ ba điều: **remote nào nhận dữ liệu, nguồn local nào được gửi và ref nào trên remote sẽ thay đổi**. Khi đọc được ba phần đó trong refspec, bạn có thể chủ động đẩy đúng nhánh thay vì dựa vào phỏng đoán về nhánh hiện tại.

