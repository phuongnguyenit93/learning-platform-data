# Cấu hình push.default và tránh đẩy nhầm nhánh

Lệnh `git push` đưa commit từ repository local lên một remote để chia sẻ với người khác. Khi chỉ chạy `git push` mà không ghi rõ remote và nhánh đích, Git phải dựa vào cấu hình để quyết định sẽ gửi những nhánh nào và gửi đến đâu. Nếu không hiểu các quy tắc này, lập trình viên có thể đẩy nhầm nhánh, cập nhật một nhánh dùng chung hoặc gửi nhiều nhánh ngoài dự định.

Git cung cấp tùy chọn `push.default` để xác định hành vi khi lệnh push không có refspec cụ thể. Kết hợp cấu hình này với upstream, push remote, kiểm tra trạng thái và refspec tường minh sẽ giúp quy trình đồng bộ repository dễ dự đoán hơn.

## 1. Phân biệt local branch, remote-tracking branch và upstream

Trước khi cấu hình push, cần hiểu ba khái niệm thường xuất hiện cùng nhau.

### 1.1. Local branch

Local branch là nhánh nằm trong repository trên máy của bạn. Ví dụ:

~~~bash
git branch
git switch feature/payment-retry
~~~

Trong ví dụ này, `feature/payment-retry` là nhánh local. Các commit mới bạn tạo khi đang đứng trên nhánh này sẽ cập nhật tham chiếu của nhánh local.

Kiểm tra nhánh hiện tại:

~~~bash
git branch --show-current
~~~

Lệnh trả về tên nhánh đang checkout. Đây là thông tin cần kiểm tra trước khi push.

### 1.2. Remote-tracking branch

Khi clone hoặc fetch từ remote, Git lưu các tham chiếu theo dõi trạng thái nhánh ở remote, thường có tên như:

- `origin/main`
- `origin/feature/payment-retry`
- `upstream/main`

Ví dụ, `origin/main` là remote-tracking branch ghi nhận trạng thái nhánh `main` mà lần fetch gần nhất đã nhận từ remote tên `origin`. Nó không phải là nhánh local `main`, và cũng không tự cập nhật ngay khi máy chủ có commit mới.

Làm mới thông tin remote:

~~~bash
git fetch origin
~~~

Sau khi fetch, Git cập nhật các remote-tracking branch tương ứng. Lệnh fetch không tự merge thay đổi vào nhánh local hiện tại.

### 1.3. Upstream branch

Upstream branch là nhánh mà một local branch được cấu hình để theo dõi. Ví dụ, local branch `feature/payment-retry` có thể theo dõi `origin/feature/payment-retry`.

Cấu hình này giúp Git biết nhánh nào được dùng để so sánh trạng thái ahead/behind, và là căn cứ cho một số lệnh pull hoặc push không ghi rõ nhánh đích.

Xem upstream của các nhánh local:

~~~bash
git branch -vv
~~~

Dòng có dấu `*` là nhánh hiện tại. Phần trong ngoặc vuông cho biết upstream, nếu đã cấu hình, và có thể hiển thị trạng thái như `ahead 2` hoặc `behind 1`.

Xem upstream của nhánh hiện tại bằng:

~~~bash
git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'
~~~

Nếu lệnh báo không có upstream, nhánh hiện tại chưa được cấu hình nhánh theo dõi.

Có thể đặt upstream rõ ràng:

~~~bash
git branch --set-upstream-to=origin/main main
~~~

Lệnh trên cấu hình local branch `main` theo dõi `origin/main`. Chỉ dùng khi đây thực sự là quan hệ mong muốn.

## 2. Git chọn remote để push như thế nào?

Remote là tên đại diện cho một repository khác, thường là `origin`, `upstream` hoặc tên fork. Xem các địa chỉ đã cấu hình:

~~~bash
git remote -v
~~~

Khi chạy `git push` mà không chỉ định remote, Git cần chọn một remote đích. Quy tắc lựa chọn có thể chịu ảnh hưởng của các cấu hình theo thứ tự ưu tiên:

1. `branch.<ten-nhanh>.pushRemote`: remote push riêng cho nhánh hiện tại.
2. `remote.pushDefault`: remote push mặc định cho các nhánh.
3. `branch.<ten-nhanh>.remote`: remote mà nhánh hiện tại theo dõi.
4. `origin`: remote mặc định nếu không có cấu hình phù hợp khác.

Có thể kiểm tra cấu hình liên quan:

~~~bash
git config --show-origin --get remote.pushDefault
git config --show-origin --get branch.feature/payment-retry.pushRemote
git config --show-origin --get branch.feature/payment-retry.remote
~~~

Các lệnh `git config --get` có thể không in kết quả nếu khóa chưa được cấu hình. Điều đó không nhất thiết là lỗi; Git sẽ tiếp tục xét các nguồn mặc định tiếp theo.

Một số nhóm làm việc với fork có thể lấy code từ remote `upstream` nhưng push nhánh của mình lên `origin`. Trong trường hợp đó, remote dùng để lấy thay đổi và remote dùng để push có thể khác nhau. Có thể đặt remote push mặc định:

~~~bash
git config remote.pushDefault origin
~~~

Hoặc cấu hình riêng cho một nhánh:

~~~bash
git config branch.feature/payment-retry.pushRemote origin
~~~

Việc chọn remote và việc chọn nhánh cần push là hai quyết định riêng. `push.default` chủ yếu quyết định ref nào được gửi khi chưa có refspec; các cấu hình remote quyết định đích nhận.

Ngoài ra, nếu remote có cấu hình `remote.<ten-remote>.push`, refspec trong cấu hình đó sẽ quyết định những ref được push khi bạn không ghi refspec trên dòng lệnh. Có thể kiểm tra, ví dụ:

~~~bash
git config --show-origin --get-all remote.origin.push
~~~

Một refspec ghi trực tiếp trong lệnh `git push` sẽ giúp thể hiện rõ nguồn và đích của lần push đó.

## 3. push.default là gì?

`push.default` xác định hành vi của `git push` khi bạn không cung cấp refspec trên dòng lệnh và cũng không có refspec riêng được cấu hình cho remote. Giá trị này có thể được đặt ở cấp repository hoặc cấp người dùng.

Năm giá trị thường gặp:

| Giá trị | Hành vi | Lưu ý |
| --- | --- | --- |
| `nothing` | Không tự chọn nhánh để push; yêu cầu refspec rõ ràng | An toàn nhất khi muốn mọi lần push đều chỉ định đích |
| `current` | Push nhánh hiện tại lên nhánh cùng tên ở remote đích | Không cần upstream, nhưng vẫn phải chọn đúng remote |
| `upstream` | Push nhánh hiện tại lên upstream branch đã cấu hình | Có thể đẩy tới nhánh remote mang tên khác |
| `simple` | Trong workflow tập trung, push nhánh hiện tại lên upstream cùng tên và từ chối nếu tên khác | Giá trị mặc định từ Git 2.0; lựa chọn phù hợp cho phần lớn quy trình thông thường |
| `matching` | Push tất cả các nhánh local có nhánh cùng tên ở remote | Có thể cập nhật nhiều nhánh ngoài dự định |

### 3.1. nothing — bắt buộc chỉ định đích

~~~bash
git config --global push.default nothing
~~~

Với cấu hình này, lệnh:

~~~bash
git push
~~~

sẽ dừng vì không có refspec rõ ràng. Bạn phải chỉ định nhánh hoặc cặp nguồn/đích:

~~~bash
git push origin feature/payment-retry
~~~

Cách này phù hợp với người muốn chủ động xác nhận nhánh mỗi lần push, hoặc nhóm có quy trình phát hành nghiêm ngặt. Đổi lại, thao tác push sẽ dài hơn.

### 3.2. current — đẩy nhánh hiện tại lên nhánh cùng tên

~~~bash
git config --global push.default current
~~~

Nếu đang đứng trên local branch `feature/payment-retry`, Git sẽ đẩy nhánh đó đến nhánh cùng tên trên remote đã chọn.

Ưu điểm là không cần cấu hình upstream trước. Tuy nhiên, `current` không xác nhận rằng remote branch cùng tên chính là nhánh bạn định cập nhật. Nếu remote được chọn sai hoặc bạn đang đứng nhầm nhánh, kết quả vẫn có thể không như mong muốn.

### 3.3. upstream — đẩy đến nhánh đang theo dõi

~~~bash
git config --global push.default upstream
~~~

Giá trị này dùng upstream branch của nhánh hiện tại làm đích. Điều đó hữu ích khi local branch và remote branch có tên khác nhau nhưng quan hệ theo dõi đã được thiết lập có chủ đích.

Ví dụ, local branch `review/payment-retry` có thể theo dõi remote branch `origin/review/PR-42`. Với `upstream`, Git hướng push đến nhánh upstream đó.

Vì đích có thể khác tên local branch, hãy kiểm tra `git branch -vv` trước khi dùng. Nếu upstream được cấu hình nhầm, push không tham số có thể cập nhật sai nhánh.

### 3.4. simple — lựa chọn mặc định an toàn cho workflow tập trung

~~~bash
git config --global push.default simple
~~~

Trong workflow tập trung, `simple` yêu cầu local branch hiện tại có upstream và tên hai nhánh phải trùng nhau. Nếu tên khác nhau, Git từ chối push để tránh cập nhật một nhánh có thể không phải đích dự định.

Đây là giá trị mặc định kể từ Git 2.0. Trong workflow tam giác — chẳng hạn lấy code từ một remote nhưng push lên fork khác — `simple` hoạt động theo cách của `current`, tức là đẩy nhánh hiện tại đến nhánh cùng tên trên push remote.

Nếu nhánh chưa có upstream, lệnh push mặc định sẽ yêu cầu bạn thiết lập upstream. Có thể thực hiện một lần bằng:

~~~bash
git push -u origin feature/payment-retry
~~~

Sau khi upstream được ghi nhận, các lần push tiếp theo có thể dùng `git push` nếu bạn đã kiểm tra đúng nhánh và đúng remote.

### 3.5. matching — đẩy tất cả nhánh có tên trùng

~~~bash
git config --global push.default matching
~~~

Giá trị này gửi mọi nhánh local có nhánh cùng tên ở remote. Ví dụ, nếu local có `main`, `release/1.4` và `feature/search`, còn remote có cả ba nhánh tương ứng, một lệnh push có thể cập nhật cả ba.

Cách này có thể phù hợp với quy trình đồng bộ nhiều nhánh có chủ đích, nhưng dễ gây bất ngờ nếu lập trình viên chỉ muốn chia sẻ một nhánh. Không nên chọn `matching` làm mặc định cho quy trình làm việc thông thường.

## 4. Chọn cấu hình phù hợp và kiểm tra cấu hình đang có

### 4.1. Kiểm tra giá trị hiệu lực

Xem giá trị được cấu hình và nguồn của nó:

~~~bash
git config --show-origin --get-all push.default
~~~

Nếu không có kết quả, Git dùng giá trị mặc định theo phiên bản Git đang sử dụng. Với các phiên bản Git hiện đại, giá trị mặc định là `simple`.

Cấu hình có thể tồn tại ở nhiều cấp:

- System: áp dụng cho toàn máy.
- Global: áp dụng cho người dùng hiện tại.
- Local: áp dụng riêng cho repository và thường ghi đè global.
- Worktree: áp dụng riêng cho worktree nếu cấu hình hỗ trợ.

Đặt cấu hình global:

~~~bash
git config --global push.default simple
~~~

Đặt cấu hình riêng cho repository hiện tại:

~~~bash
git config --local push.default simple
~~~

Nếu repository có cấu hình local khác với global, hãy xem nguồn cấu hình trước khi thay đổi. Không cần đặt lại giá trị mặc định ở mọi repository nếu không có lý do.

### 4.2. Khuyến nghị lựa chọn

- Dùng `simple` cho phần lớn người dùng và workflow tập trung.
- Dùng `nothing` nếu chính sách nhóm yêu cầu mỗi lần push phải chỉ rõ nhánh đích.
- Dùng `upstream` khi chủ động làm việc với nhánh local và upstream khác tên.
- Dùng `current` khi muốn đẩy nhánh hiện tại đến nhánh cùng tên mà không phụ thuộc upstream.
- Chỉ dùng `matching` khi thực sự muốn đồng bộ nhiều nhánh có cùng tên.

Không có một giá trị phù hợp cho mọi workflow. Điều quan trọng là cả nhóm hiểu cấu hình đang áp dụng và biết lệnh không tham số sẽ chọn nhánh nào.

## 5. Dùng refspec để chỉ định chính xác nhánh nguồn và đích

### 5.1. Cú pháp refspec

Cú pháp push cơ bản:

~~~bash
git push <remote> <source>:<destination>
~~~

Trong đó:

- `<remote>` là repository nhận commit.
- `<source>` là nhánh hoặc commit local được gửi đi.
- `<destination>` là nhánh đích trên remote.

Ví dụ:

~~~bash
git push origin feature/payment-retry:refs/heads/feature/payment-retry
~~~

Lệnh này đẩy local branch `feature/payment-retry` đến remote branch cùng tên trên `origin`.

Nếu tên nguồn và đích giống nhau, có thể viết ngắn:

~~~bash
git push origin feature/payment-retry
~~~

Điểm cần nhớ: lệnh này chọn local branch có tên `feature/payment-retry`, không phụ thuộc bạn đang checkout nhánh nào. Vì thế, khi muốn đẩy nhánh hiện tại, cần xác nhận tên nhánh hoặc dùng refspec bắt đầu từ `HEAD`.

### 5.2. Đẩy commit của nhánh hiện tại đến đích được chỉ định

Giả sử bạn đang đứng trên `feature/payment-retry` và muốn đẩy đúng nội dung hiện tại đến remote branch cùng tên:

~~~bash
git push origin HEAD:refs/heads/feature/payment-retry
~~~

`HEAD` đại diện cho commit hiện tại. Phần đích được ghi đầy đủ là `refs/heads/feature/payment-retry`, vì vậy lệnh thể hiện rõ nhánh remote sẽ nhận cập nhật.

Nếu muốn local branch bắt đầu theo dõi nhánh remote đó:

~~~bash
git push --set-upstream origin HEAD:refs/heads/feature/payment-retry
~~~

Tùy chọn `-u` là cách viết ngắn của `--set-upstream`.

### 5.3. Đẩy đến nhánh remote có tên khác

Có thể chủ động ánh xạ một local branch đến một nhánh remote khác:

~~~bash
git push origin HEAD:refs/heads/review/payment-retry-42
~~~

Lệnh này gửi commit hiện tại đến nhánh `review/payment-retry-42` trên `origin`. Hãy chắc chắn đó là đích được nhóm thống nhất. Nếu muốn nhánh local theo dõi đích này, thêm `-u`:

~~~bash
git push -u origin HEAD:refs/heads/review/payment-retry-42
~~~

Refspec tường minh thường hữu ích trong CI, quy trình tạo nhánh review hoặc khi tên nhánh local và remote khác nhau.

## 6. Quy trình an toàn trước khi push

Một lệnh push không tham số ngắn gọn nhưng có thể che giấu nhiều quyết định. Trước khi gửi commit, hãy xác nhận nhánh hiện tại, remote, upstream và nội dung sẽ được gửi.

### 6.1. Kiểm tra nhánh và trạng thái working tree

~~~bash
git branch --show-current
git status -sb
git branch -vv
~~~

Xác nhận:

- Bạn đang đứng trên nhánh dành cho công việc cần chia sẻ.
- Working tree không chứa thay đổi chưa được kiểm tra.
- Upstream hiển thị đúng remote và nhánh mong muốn.
- Không có dấu hiệu nhánh đang lệch với remote mà bạn chưa xử lý.

Nếu nhánh đang có thay đổi chưa commit, hãy quyết định có cần commit hoặc stash trước khi push. Push chỉ gửi commit; nó không tự gửi các sửa đổi chưa commit trong working tree.

### 6.2. Kiểm tra remote đích

~~~bash
git remote -v
git remote get-url --push origin
~~~

Lệnh thứ hai cho biết URL push của remote `origin`. Một remote có thể dùng URL fetch và URL push khác nhau. Vì vậy, hãy kiểm tra đúng URL nhận dữ liệu, nhất là khi làm việc với fork hoặc nhiều máy chủ.

Nếu đang dùng remote mặc định khác `origin`, thay tên tương ứng trong lệnh.

### 6.3. Cập nhật thông tin remote và xem commit chênh lệch

~~~bash
git fetch origin
git status -sb
git log --oneline --decorate --graph '@{upstream}..HEAD'
~~~

Lệnh cuối liệt kê các commit local chưa có trong upstream, nếu upstream đã được cấu hình. Có thể xem cả hai phía bằng:

~~~bash
git log --oneline --left-right '@{upstream}...HEAD'
~~~

Ký hiệu `<` và `>` giúp phân biệt commit chỉ có ở một phía. Nếu upstream chưa tồn tại, hãy dùng refspec tường minh hoặc thiết lập upstream trước khi dựa vào các phép so sánh này.

### 6.4. Chạy thử push

Trước khi gửi thật, có thể chạy:

~~~bash
git push --dry-run --porcelain origin HEAD:refs/heads/feature/payment-retry
~~~

`--dry-run` yêu cầu Git mô phỏng cập nhật mà không thực sự gửi ref update lên remote. Kết quả giúp kiểm tra nguồn và đích mà lệnh đang nhắm tới.

Đọc kỹ đầu ra và xác nhận:

- Remote là repository mong muốn.
- Nhánh nguồn là nhánh hiện tại.
- Nhánh đích là nhánh công việc dự định.
- Không có nhánh khác được liệt kê ngoài ý muốn.

Sau khi xác nhận, thực hiện push thật bằng cùng refspec:

~~~bash
git push -u origin HEAD:refs/heads/feature/payment-retry
~~~

Không thay đổi nguồn hoặc đích giữa bước dry-run và bước push thật nếu chưa kiểm tra lại.

## 7. Những tình huống dễ đẩy nhầm nhánh

### 7.1. Đang ở nhánh feature nhưng gõ tên main

Giả sử bạn đang đứng trên `feature/payment-retry`, nhưng chạy:

~~~bash
git push origin main
~~~

Git hiểu `main` là local branch nguồn. Lệnh sẽ đẩy local branch `main` lên remote branch cùng tên, dù bạn đang checkout nhánh feature. Lệnh này không có nghĩa “push nhánh hiện tại”.

Cách xử lý là kiểm tra `git branch --show-current` và chỉ định đúng nguồn:

~~~bash
git push origin feature/payment-retry
~~~

Hoặc dùng `HEAD` cùng nhánh đích tường minh như phần trước.

### 7.2. Đang ở main nhưng muốn push nhánh feature

Nếu cần chia sẻ nhánh feature, hãy chuyển sang nhánh đó và kiểm tra:

~~~bash
git switch feature/payment-retry
git branch --show-current
git status -sb
git push -u origin feature/payment-retry
~~~

Việc chuyển nhánh trước giúp giảm khả năng nhầm lẫn khi dùng lệnh không tham số về sau. Tuy nhiên, lệnh push vẫn cần được kiểm tra theo remote và upstream.

### 7.3. Upstream bị cấu hình sai

Nếu `git branch -vv` cho thấy nhánh feature theo dõi `origin/main`, hãy dừng lại và xác định quan hệ mong muốn. Nếu đúng ra nhánh phải theo dõi `origin/feature/payment-retry`, có thể sửa:

~~~bash
git branch --set-upstream-to=origin/feature/payment-retry feature/payment-retry
~~~

Sau đó kiểm tra lại:

~~~bash
git branch -vv
git status -sb
~~~

Chỉ sửa upstream khi nhánh remote thực sự tồn tại và đó là nhánh cần theo dõi. Nếu chưa có nhánh remote, dùng `git push -u` với remote và đích chính xác để tạo và thiết lập upstream.

### 7.4. Remote push khác remote fetch

Trong workflow dùng fork, bạn có thể lấy cập nhật từ `upstream` nhưng đẩy công việc lên `origin`. Nếu không phân biệt hai remote, có thể vô tình gửi commit lên repository chính của dự án.

Kiểm tra:

~~~bash
git remote -v
git branch -vv
git config --show-origin --get remote.pushDefault
~~~

Nếu quy trình yêu cầu push lên fork `origin`, có thể chỉ định trực tiếp:

~~~bash
git push -u origin feature/payment-retry
~~~

Chỉ dùng `upstream` làm remote push khi bạn có quyền và có chủ đích cập nhật repository đó.

### 7.5. Dùng các tùy chọn push phạm vi rộng

Một số lệnh có phạm vi rộng hơn một nhánh:

- `git push --all`: đẩy tất cả local branch.
- `git push --tags`: đẩy tất cả tag.
- `git push --mirror`: đồng bộ mirror các tham chiếu, có thể tạo, cập nhật và xóa ref trên remote.

Không dùng các tùy chọn này chỉ vì muốn “đồng bộ mọi thứ”. Hãy hiểu rõ phạm vi và hệ quả trước khi chạy, đặc biệt với `--mirror`.

## 8. Cấu hình push remote trong workflow dùng fork

Một quy trình phổ biến là clone repository gốc, sau đó làm việc qua fork cá nhân. Ví dụ:

- `upstream`: repository chính để fetch nhánh mới nhất.
- `origin`: fork của bạn để push nhánh công việc.

Cấu hình remote:

~~~bash
git remote -v
git config remote.pushDefault origin
git config --global push.default simple
~~~

Khi tạo nhánh từ nhánh chính:

~~~bash
git fetch upstream
git switch -c feature/payment-retry upstream/main
~~~

Sau khi hoàn tất công việc, push nhánh lên fork:

~~~bash
git push -u origin feature/payment-retry
~~~

Sau lần đầu, local branch sẽ theo dõi nhánh tương ứng trên `origin`. Các lần tiếp theo có thể dùng `git push`, nhưng vẫn nên kiểm tra `git branch -vv` và `git remote -v` khi chuyển giữa các dự án hoặc thay đổi cấu hình.

Nếu mỗi nhánh có remote push khác nhau, có thể đặt riêng:

~~~bash
git config branch.feature/payment-retry.pushRemote origin
~~~

Cấu hình này hữu ích khi một số nhánh cần push đến fork, trong khi nhánh khác cần push đến remote riêng. Đừng đặt cấu hình theo thói quen nếu nhóm chưa thống nhất remote nào được phép nhận thay đổi.

## 9. Bảo vệ nhánh dùng chung

Cấu hình local giúp giảm rủi ro nhưng không thay thế chính sách bảo vệ trên máy chủ. Với các nhánh như `main`, `develop` hoặc `release/*`, nhóm nên dùng quyền bảo vệ nhánh trên nền tảng lưu trữ mã nguồn để hạn chế push trực tiếp, yêu cầu review hoặc kiểm tra tự động theo quy trình.

Khi cần cập nhật một nhánh đã được nhiều người dùng, tránh force push tùy tiện. Nếu phải viết lại lịch sử, hãy phối hợp với nhóm và hiểu tác động đến các bản clone khác. `--force-with-lease` có kiểm tra trạng thái remote gần nhất của bạn trước khi ghi đè, nhưng vẫn có thể thay thế commit của người khác nếu dùng sai mục tiêu. Nó không phải cách sửa lỗi push thông thường.

Nếu phát hiện đã push nhầm nhánh:

1. Dừng các lần push tiếp theo để tránh làm tình hình phức tạp hơn.
2. Xác định remote, nhánh đích và commit đã được gửi.
3. Trao đổi với người quản lý nhánh hoặc nhóm nếu đó là nhánh dùng chung.
4. Chọn cách khôi phục phù hợp, thường là tạo commit revert nếu thay đổi đã được chia sẻ.
5. Kiểm tra lại lịch sử và trạng thái remote trước khi tiếp tục làm việc.

Không tự ý force push để “xóa dấu vết” trên nhánh dùng chung. Lịch sử cần được sửa theo quy trình mà nhóm thống nhất.

## 10. Bảng tra cứu nhanh

| Nhu cầu | Lệnh hoặc cấu hình |
| --- | --- |
| Xem nhánh hiện tại | `git branch --show-current` |
| Xem upstream | `git branch -vv` |
| Xem remote và URL | `git remote -v` |
| Xem cấu hình push.default | `git config --show-origin --get-all push.default` |
| Đặt mặc định simple | `git config --global push.default simple` |
| Buộc chỉ push khi ghi rõ đích | `git config --global push.default nothing` |
| Push nhánh và thiết lập upstream | `git push -u origin feature/my-branch` |
| Push HEAD đến đích cụ thể | `git push origin HEAD:refs/heads/feature/my-branch` |
| Mô phỏng push | `git push --dry-run origin HEAD:refs/heads/feature/my-branch` |
| Đặt remote push mặc định | `git config remote.pushDefault origin` |
| Đặt remote push cho một nhánh | `git config branch.feature/my-branch.pushRemote origin` |

Cần nhớ rằng `push.default` chọn hành vi khi thiếu refspec; nó không xác nhận nội dung commit có đúng yêu cầu hay không. Remote và upstream cũng là hai cấu hình khác nhau, nên hãy kiểm tra cả hai trước khi push.

## 11. Tổng kết

Để tránh đẩy nhầm nhánh, hãy hiểu rõ nhánh local, remote-tracking branch và upstream; kiểm tra remote push; rồi chọn cách push phù hợp với workflow. `simple` là lựa chọn mặc định hợp lý cho đa số quy trình tập trung vì yêu cầu tên local branch và upstream khớp nhau. `nothing` phù hợp khi muốn bắt buộc chỉ định đích; `current`, `upstream` và `matching` cần được chọn khi bạn hiểu rõ hành vi của chúng.

Trước một lần push quan trọng, hãy kiểm tra nhánh hiện tại bằng `git branch --show-current`, xem upstream bằng `git branch -vv`, xác nhận URL bằng `git remote -v`, rồi dùng refspec tường minh hoặc `--dry-run` để xác nhận nhánh đích. Những bước này biến một lệnh push ngắn thành một thao tác có thể kiểm tra và dự đoán được.

