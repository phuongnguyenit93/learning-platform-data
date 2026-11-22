# Giới hạn khi tra cứu, hợp nhất và làm việc ngoại tuyến với bản sao không đầy đủ

Sparse checkout và partial clone giúp làm việc với repository lớn mà không cần tải hoặc hiển thị mọi tệp ngay từ đầu. Chúng hữu ích trong monorepo, dự án có nhiều tài sản lớn hoặc nhóm chỉ phụ trách một vài thành phần. Tuy nhiên, một working tree nhỏ không đồng nghĩa máy đang có đầy đủ dữ liệu Git để thực hiện mọi thao tác.

Khi tra cứu lịch sử, tìm kiếm nội dung, merge hoặc làm việc ngoại tuyến, Git có thể cần commit, tree hoặc blob chưa có trong bản sao local. Với partial clone, Git thường cố gắng tải object còn thiếu từ promisor remote khi cần. Nếu không có mạng, không có quyền truy cập hoặc remote không còn cung cấp object, thao tác có thể thất bại. Shallow clone còn có một giới hạn khác: một phần lịch sử commit nằm ngoài ranh giới đã tải.

Muốn sử dụng kho mã chọn lọc an toàn, cần phân biệt **phạm vi tệp trong working tree**, **object được tải về** và **độ sâu lịch sử commit**. Ba yếu tố này liên quan nhưng không giống nhau.

## 1. Phân biệt sparse checkout, partial clone và shallow clone

### 1.1. Sparse checkout giới hạn những gì xuất hiện trong working tree

Sparse checkout cho phép chỉ checkout một phần đường dẫn của repository vào working tree. Các đường dẫn ngoài phạm vi được chọn thường không xuất hiện trong thư mục làm việc, dù repository có thể đã chứa đầy đủ object tương ứng.

Ví dụ, monorepo có các thư mục:

```text
project/
  services/
    billing/
    identity/
    search/
  libraries/
  docs/
  tools/
```

Một thành viên chỉ làm dịch vụ `billing` và thư viện dùng chung có thể chọn:

```bash
git sparse-checkout init --cone
git sparse-checkout set services/billing libraries
```

Working tree chỉ hiển thị các đường dẫn được chọn cùng những tệp cấp cao cần thiết theo quy tắc cone mode. Các đường dẫn khác không bị xóa khỏi lịch sử Git; chúng chỉ không được materialize trong working tree hiện tại.

Nếu repository là một clone đầy đủ, object của những đường dẫn không hiển thị vẫn có thể nằm local. Vì vậy, sparse checkout tự nó không nhất thiết giảm dung lượng object database.

### 1.2. Partial clone giới hạn object được tải về

Partial clone cho phép clone repository nhưng trì hoãn tải một số object. Git ghi nhận remote có thể cung cấp các object bị thiếu (promisor remote) và thường lazy-fetch chúng khi một thao tác cần dùng.

Ví dụ phổ biến:

```bash
git clone --filter=blob:none --sparse https://example.com/team/monorepo.git
```

`--filter=blob:none` yêu cầu không tải blob ngay trong lần clone ban đầu. Commit và tree thường vẫn được tải, còn nội dung tệp được lấy khi cần. Kết hợp `--sparse` giúp working tree ban đầu chỉ checkout phần tối thiểu theo cấu hình sparse mặc định.

Một bộ lọc khác là `--filter=tree:0`, thường gọi là treeless clone. Nó trì hoãn tải tree object; Git có thể phải lấy thêm tree để đi qua cấu trúc thư mục khi cần. Cấu hình này giảm dữ liệu ban đầu mạnh hơn nhưng nhiều thao tác duyệt cây có thể phát sinh thêm yêu cầu tới remote.

### 1.3. Shallow clone giới hạn độ sâu lịch sử

Shallow clone dùng `--depth` để chỉ tải lịch sử tới một độ sâu nhất định:

```bash
git clone --depth=1 https://example.com/team/monorepo.git
```

Clone này có thể chứa đầy đủ nội dung của snapshot hiện tại nhưng không có toàn bộ tổ tiên commit. Ranh giới lịch sử bị cắt được ghi nhận trong repository, thường qua `.git/shallow`.

### 1.4. Bảng so sánh

| Cơ chế | Giới hạn chính | Dữ liệu có thể chưa có local? | Ảnh hưởng nổi bật |
|---|---|---|---|
| Sparse checkout | Đường dẫn hiện diện trong working tree | Không nhất thiết; clone đầy đủ vẫn có thể giữ mọi object | Tệp ngoài phạm vi không xuất hiện để chỉnh sửa trực tiếp |
| Partial clone | Loại object được tải về, ví dụ blob hoặc tree | Có; Git có thể lazy-fetch từ promisor remote | Tìm kiếm, diff, checkout hoặc merge có thể cần mạng để lấy object |
| Shallow clone | Độ sâu lịch sử commit | Có các commit tổ tiên nằm ngoài ranh giới shallow | Log, blame, merge-base, bisect, tag và push có thể bị giới hạn |

Ba cơ chế có thể kết hợp trong cùng một bản clone. Ví dụ một repository vừa shallow, vừa partial clone, vừa sparse checkout sẽ có cả giới hạn đường dẫn, object và lịch sử.

## 2. Cấu hình và kiểm tra bản sao không đầy đủ

### 2.1. Tạo sparse checkout

Với repository đã clone:

```bash
git sparse-checkout init --cone
git sparse-checkout set services/billing libraries
git sparse-checkout list
```

Cone mode phù hợp với phần lớn trường hợp chọn thư mục. Nó dùng tập quy tắc đơn giản, dễ dự đoán và có thể kết hợp với sparse index để giảm chi phí xử lý index ở repository lớn.

Muốn bổ sung thêm thư mục mà vẫn giữ lựa chọn hiện tại:

```bash
git sparse-checkout add services/identity
```

Muốn bỏ một thư mục khỏi phạm vi:

```bash
git sparse-checkout set services/billing libraries
```

`set` thay thế tập đường dẫn đã chọn bằng danh sách mới; vì vậy hãy liệt kê đầy đủ các thư mục muốn giữ. Lệnh `reapply` có mục đích khác: áp dụng lại các pattern sparse hiện tại vào working tree và index, chẳng hạn sau một thao tác đã materialize thêm đường dẫn.

Muốn trở lại checkout đầy đủ:

```bash
git sparse-checkout disable
```

Trong partial clone, việc mở rộng phạm vi có thể làm Git tải thêm blob hoặc tree. Hãy dự trù mạng và dung lượng trước khi tắt sparse checkout.

### 2.2. Kiểm tra partial clone và promisor remote

```bash
git config --show-origin --get-regexp '^remote\..*\.(promisor|partialclonefilter)$'
```

Kết quả có thể cho thấy cấu hình tương tự:

```text
file:.git/config remote.origin.promisor true
file:.git/config remote.origin.partialclonefilter blob:none
```

`promisor=true` cho biết remote được xem là nơi cung cấp các object bị thiếu theo mô hình partial clone. `partialclonefilter` cho biết bộ lọc object đã dùng.

Không phải mọi remote đều là promisor remote. Một repository có thể có nhiều remote, nhưng partial clone thường dựa vào remote được đánh dấu promisor để lazy-fetch object.

### 2.3. Kiểm tra shallow state

```bash
git rev-parse --is-shallow-repository
```

Kết quả `true` nghĩa là repository có ranh giới shallow; `false` nghĩa là Git không đánh dấu repository là shallow. Đây là phép kiểm tra riêng, không cho biết repository có phải partial clone hay đang dùng sparse checkout.

### 2.4. Kiểm tra các trạng thái cùng lúc

```bash
git sparse-checkout list
git rev-parse --is-shallow-repository
git config --show-origin --get-regexp '^remote\..*\.(promisor|partialclonefilter)$'
git status -sb
```

Đọc cả bốn kết quả để biết working tree đang chọn gì, lịch sử có bị cắt không, remote nào cung cấp object còn thiếu và working tree có thay đổi chưa commit hay không.

## 3. Giới hạn khi tra cứu và tìm kiếm

Tra cứu trong Git có thể cần dữ liệu ở nhiều tầng: tên đường dẫn nằm trong tree, nội dung tệp nằm trong blob và lịch sử thay đổi nằm trong commit. Một bản clone không đầy đủ có thể chỉ có một phần các object đó.

### 3.1. Tìm kiếm trong working tree chỉ thấy tệp đang có

Lệnh:

```bash
git grep -n "PaymentService"
```

thường tìm trong các tệp tracked hiện diện trong working tree hiện tại. Nếu `services/identity` không thuộc sparse set, tìm kiếm mặc định có thể không thấy mã nguồn trong thư mục đó vì các tệp không được checkout.

Có thể tìm trong một tree-ish cụ thể:

```bash
git grep -n "PaymentService" HEAD -- services/identity
```

Lệnh này yêu cầu tìm trong snapshot `HEAD` ở đường dẫn được chỉ định, ngay cả khi đường dẫn không hiện diện trong working tree. Với partial clone, Git có thể phải lazy-fetch blob cần thiết. Nếu remote không truy cập được và blob chưa có local, lệnh có thể thất bại.

### 3.2. Tìm trong lịch sử có thể tải nhiều blob

Các lệnh tìm nội dung qua nhiều commit như:

```bash
git log -S"legacyToken" --all -- services/
git log -G"password\\s*=" --all -- config/
```

có thể cần đọc nội dung blob ở nhiều revision. Trong blobless clone, các blob chưa có sẽ được lấy từ promisor remote khi cần. Một truy vấn tưởng như chỉ đọc có thể phát sinh nhiều lượt tải mạng và tăng thời gian đáng kể.

`git log -- path/to/file` có thể chỉ cần một phần tree để lần theo lịch sử đường dẫn, còn các tùy chọn như `-S`, `-G` hoặc yêu cầu hiển thị patch cần nội dung blob nhiều hơn. Mức object phải tải phụ thuộc lệnh, phạm vi commit và loại filter.

### 3.3. `git blame` và `git show` cũng cần nội dung tệp

Ví dụ:

```bash
git blame HEAD -- services/billing/InvoiceService.java
git show <commit-id>:services/billing/InvoiceService.java
```

`git blame` cần so sánh nội dung tệp qua các commit để xác định dòng được giới thiệu ở đâu. `git show <commit>:<path>` cần blob của đường dẫn tại commit đó. Partial clone có thể lazy-fetch các blob chưa có; shallow clone có thể không có đủ tổ tiên để lần ngược tới thay đổi ban đầu.

Do đó, kết quả blame trong shallow clone có thể dừng ở ranh giới shallow và không đại diện cho toàn bộ lịch sử của tệp.

### 3.4. Tìm kiếm bằng công cụ ngoài Git

IDE, `ripgrep`, `grep`, công cụ lập chỉ mục mã nguồn và trình phân tích tĩnh thường quét filesystem hiện tại. Chúng không tự biết các thư mục sparse đã bị bỏ khỏi working tree, cũng không tự lazy-fetch nội dung từ Git.

Nếu kết quả tìm kiếm trong IDE thiếu module, hãy kiểm tra sparse set trước khi kết luận mã nguồn không tồn tại. Có thể mở rộng phạm vi:

```bash
git sparse-checkout add services/identity
```

Hoặc tìm trực tiếp trong tree/history bằng lệnh Git nếu phù hợp. Mỗi cách có chi phí object và mạng khác nhau.

## 4. Giới hạn khi merge và giải quyết conflict

Merge cần hiểu quan hệ giữa commit và kết hợp nội dung của các đường dẫn liên quan. Sparse checkout, partial clone và shallow clone tác động tới những phần khác nhau của quá trình đó.

### 4.1. Sparse checkout không có nghĩa merge chỉ tác động tới thư mục đang thấy

Sparse checkout điều khiển phần working tree được materialize. Nó không biến các đường dẫn ngoài sparse set thành những đường dẫn không tồn tại trong repository.

Khi merge một branch có thay đổi ở nhiều thư mục, Git vẫn phải xử lý trạng thái index và lịch sử của các đường dẫn liên quan. Một số thay đổi ngoài sparse set có thể được ghi nhận trong index mà không xuất hiện như tệp bình thường trong working tree. Tùy phiên bản Git, sparse index và tình huống conflict, Git có thể cần mở rộng hoặc materialize thêm đường dẫn.

Vì vậy, đừng kết luận merge đã sạch chỉ vì thư mục đang mở không có conflict. Sau merge, kiểm tra:

```bash
git status
git diff --name-only --diff-filter=U
git ls-files -u
```

`git ls-files -u` liệt kê các index entry chưa hợp nhất. Nếu conflict nằm ngoài sparse set, có thể mở rộng sparse checkout tới thư mục liên quan để xem và sửa nội dung:

```bash
git sparse-checkout add path/to/conflicted-area
```

Sau khi giải quyết, stage đúng tệp và hoàn tất merge theo thông báo Git.

### 4.2. Partial clone có thể cần tải blob khi merge

Merge thường cần commit và tree để xác định base và các thay đổi. Khi nội dung của một tệp cần hợp nhất chưa có local, Git có thể yêu cầu blob từ promisor remote.

Với `--filter=blob:none`, commit và tree thường đã có, nhưng blob cần cho ba phía merge (base, ours, theirs) có thể chưa có. Với `--filter=tree:0`, Git còn có thể cần tải tree để duyệt cấu trúc thư mục.

Nếu đang online và remote hoạt động, Git thường lazy-fetch các object còn thiếu. Nếu offline, thiếu quyền hoặc remote không còn object, merge có thể dừng do không lấy được dữ liệu cần thiết.

### 4.3. Shallow clone có thể thiếu merge base

Merge cần tìm tổ tiên chung phù hợp giữa hai branch. Trong shallow clone, một hoặc nhiều chuỗi tổ tiên có thể bị cắt ở ranh giới shallow. Git có thể xử lý một số tình huống bằng thông tin còn lại, nhưng merge base hoặc lịch sử cần thiết có thể không đầy đủ.

Nếu Git báo không thể xác định base hoặc kết quả merge đáng ngờ, kiểm tra:

```bash
git rev-parse --is-shallow-repository
git log --graph --oneline --decorate --all
```

Khi cần thêm lịch sử, fetch sâu hơn:

```bash
git fetch --deepen=100 origin
```

Hoặc lấy toàn bộ lịch sử từ remote nếu remote cho phép:

```bash
git fetch --unshallow origin
```

`--unshallow` chỉ giải quyết giới hạn độ sâu lịch sử. Nó không tự bảo đảm mọi blob đã được tải nếu repository vẫn dùng partial clone filter.

### 4.4. Quy trình xử lý merge trong sparse checkout

Trước khi merge branch lớn hoặc có thay đổi ngoài phạm vi đang chọn:

1. Kiểm tra working tree sạch bằng `git status`.
2. Fetch branch cần tích hợp khi đang online.
3. Xem danh sách đường dẫn thay đổi của branch đích:

   ```bash
   git diff --name-status HEAD...origin/feature/integration
   ```

4. Bổ sung các thư mục có khả năng cần review hoặc conflict:

   ```bash
   git sparse-checkout add services/identity
   ```

5. Thực hiện merge:

   ```bash
   git merge origin/feature/integration
   ```

6. Kiểm tra conflict cả trong working tree lẫn index:

   ```bash
   git status
   git diff --name-only --diff-filter=U
   git ls-files -u
   ```

7. Nếu cần, mở rộng sparse set hoặc tạm tắt sparse checkout để giải quyết đầy đủ; sau đó chạy test liên quan.

Không nên tắt sparse checkout một cách bất ngờ trên repository lớn vì thao tác này có thể làm working tree phình to và kích hoạt nhiều lượt lazy-fetch.

## 5. Giới hạn khi làm việc ngoại tuyến

### 5.1. Sparse checkout trong clone đầy đủ

Nếu clone đầy đủ, sparse checkout chỉ giới hạn working tree. Các commit, tree và blob của repository vẫn có thể có sẵn local. Vì vậy, nhiều thao tác tra cứu lịch sử và merge vẫn hoạt động ngoại tuyến, dù tệp ngoài sparse set không xuất hiện trong filesystem.

Tuy nhiên, công cụ tìm kiếm chỉ quét filesystem vẫn không nhìn thấy tệp bị bỏ khỏi working tree. Muốn làm việc với chúng, dùng Git tree/history command hoặc mở rộng sparse set.

### 5.2. Partial clone cần mạng khi object chưa có

Partial clone có thể chưa tải blob hoặc tree. Khi Git cần một object bị thiếu, nó thường yêu cầu promisor remote cung cấp. Nếu mất mạng, các lệnh cần object đó có thể thất bại.

Ví dụ những thao tác có thể cần object chưa có:

- Checkout một branch hoặc đường dẫn mới ngoài phạm vi đã materialize.
- Mở tệp lịch sử bằng `git show <commit>:<path>`.
- Tìm nội dung qua nhiều commit bằng `git log -S` hoặc `git log -G`.
- Chạy `git blame` trên tệp chưa được tải.
- Merge hoặc rebase cần nội dung của blob/tree chưa có.
- Tạo archive hoặc chạy công cụ quét toàn bộ source cần đọc các tệp vắng mặt.

Nếu object đã có local, các thao tác tương ứng có thể hoạt động ngoại tuyến. Vấn đề không phải mọi partial clone đều luôn cần mạng, mà là không thể giả định tất cả object cần thiết đã có.

### 5.3. Shallow clone giới hạn lịch sử dù có mạng hay không

Shallow clone thiếu các commit tổ tiên ngoài độ sâu đã lấy. Có mạng không có nghĩa Git tự động tải toàn bộ lịch sử cho mọi lệnh. Cần chủ động deepen hoặc unshallow khi một tác vụ cần lịch sử sâu hơn.

Các công việc như điều tra regression lâu đời, `git bisect`, `git blame`, tìm merge base hoặc tạo bản phát hành có thể cần lịch sử đầy đủ và tag cũ.

### 5.4. Commit offline có được không?

Có thể tạo commit offline nếu dữ liệu cần thiết cho commit hiện tại đã có local và working tree/index ở trạng thái hợp lệ. Git không cần remote để ghi commit local.

Nhưng commit không đồng nghĩa có thể thực hiện mọi thao tác tiếp theo. Nếu cần nội dung ngoài sparse set hoặc object chưa được tải, thao tác đó có thể cần mạng. Push từ shallow clone cũng có thể bị giới hạn vì remote có thể cần lịch sử tổ tiên mà local không có.

## 6. Chuẩn bị để làm việc ngoại tuyến

Nếu biết trước sẽ mất kết nối, cần chuẩn bị dữ liệu trong lúc còn online.

### 6.1. Chọn đủ đường dẫn

```bash
git sparse-checkout add services/billing services/identity libraries docs
```

Chọn tất cả module, tài liệu, schema, test fixture và script build cần cho công việc. Đừng chỉ chọn thư mục mã nguồn nếu quá trình build phụ thuộc vào tệp ở nơi khác.

### 6.2. Materialize các tệp cần dùng

Trong partial clone, checkout hoặc truy cập các đường dẫn cần thiết khi còn online để Git có thể lazy-fetch object. Có thể kiểm tra từng tệp bằng cách mở, build hoặc chạy test liên quan.

Nếu cần kiểm tra một revision lịch sử, truy cập revision đó khi online và xác nhận các blob cần dùng đã được tải. Việc chỉ mở phiên bản hiện tại không bảo đảm blob của mọi commit cũ đã có local.

### 6.3. Lấy thêm lịch sử nếu tác vụ cần

```bash
git fetch --deepen=200 origin
```

Hoặc:

```bash
git fetch --unshallow origin
```

Chọn độ sâu dựa trên thời gian cần điều tra và các branch liên quan. Nếu công việc phụ thuộc tag hoặc branch release cũ, hãy kiểm tra các ref đó đã được fetch.

### 6.4. Kiểm tra ngoại tuyến thật sự

Sau khi chuẩn bị, ngắt mạng hoặc dùng môi trường test offline để chạy các tác vụ dự kiến:

- Mở các tệp cần chỉnh sửa.
- Chạy build và test.
- Tra cứu lịch sử cần thiết.
- Thực hiện thử merge trên branch thử nghiệm nếu đó là công việc dự kiến.
- Kiểm tra các công cụ ngoài Git có đủ file trong working tree.

Một lệnh đã chạy thành công khi online chưa chứng minh rằng toàn bộ object cần thiết đã được lưu local; Git có thể vừa lazy-fetch object trong lần chạy đó. Chỉ thử trong môi trường không có mạng mới cho thấy rõ giới hạn offline.

### 6.5. Khi cần khả năng offline đáng tin cậy

Nếu dự án yêu cầu làm việc ngoại tuyến trong thời gian dài, xử lý merge phức tạp hoặc điều tra toàn bộ lịch sử, cách đơn giản và dễ dự đoán nhất là chuẩn bị một bản clone đầy đủ riêng:

```bash
git clone https://example.com/team/monorepo.git monorepo-full
```

Không thêm `--filter` hoặc `--depth` để clone thông thường lấy đầy đủ object và lịch sử được remote cung cấp. Có thể dùng sparse checkout trong clone đầy đủ nếu chỉ muốn giới hạn các tệp hiển thị, trong khi object vẫn có sẵn local.

Giữ bản clone chọn lọc để tiết kiệm dung lượng và bản clone đầy đủ cho tác vụ cần toàn bộ dữ liệu là một lựa chọn thực tế với repository rất lớn.

## 7. Chẩn đoán khi lệnh thất bại

### 7.1. Xác định loại giới hạn

```bash
git rev-parse --is-shallow-repository
git sparse-checkout list
git config --show-origin --get-regexp '^remote\..*\.(promisor|partialclonefilter)$'
```

Đọc kết quả để phân biệt:

- Đường dẫn không hiện diện vì sparse checkout.
- Blob/tree chưa có vì partial clone.
- Commit tổ tiên không có vì shallow clone.

Ba nguyên nhân có thể đồng thời tồn tại, nên không kết luận chỉ từ một lệnh.

### 7.2. Kiểm tra object thiếu

Có thể yêu cầu Git liệt kê object được tham chiếu nhưng chưa có local:

```bash
git rev-list --objects --all --missing=print
```

Các object thiếu có thể được in với tiền tố `?`. Trong partial clone, object được promisor remote hứa cung cấp không nhất thiết là corruption; chúng có thể được lazy-fetch khi cần. Nếu cần kiểm tra chi tiết, chạy lệnh khi online và quan sát việc Git tải object.

Không chạy `git gc` hoặc `git prune` chỉ để xử lý danh sách object thiếu. Trước tiên phải hiểu chúng thiếu do filter, shallow boundary hay do repository thực sự hỏng.

### 7.3. Mở rộng sparse checkout khi không thấy tệp

```bash
git sparse-checkout add path/to/module
```

Sau đó kiểm tra lại tệp và lệnh tìm kiếm. Nếu tệp vẫn không có, kiểm tra branch, commit và đường dẫn; tệp có thể không tồn tại trong revision hiện tại.

### 7.4. Lấy thêm object hoặc lịch sử

Nếu thiếu object và đang có mạng, thử lại thao tác sau khi xác nhận promisor remote, quyền truy cập và trạng thái dịch vụ. Nếu thiếu lịch sử do shallow clone, dùng `--deepen` hoặc `--unshallow`.

Nếu Git báo object không thể lấy từ promisor remote, có thể remote đã bị thay đổi, object đã bị xóa hoặc cấu hình remote không đúng. Hãy giữ thông báo lỗi và xác minh URL, quyền truy cập cùng ref liên quan trước khi sửa cấu hình.

## 8. Những hiểu lầm thường gặp

### “Sparse checkout xóa các thư mục ngoài phạm vi khỏi repository”

Không. Nó chỉ giới hạn working tree. Commit và lịch sử vẫn có thể chứa các đường dẫn đó.

### “Sparse checkout tự làm clone nhẹ hơn”

Không nhất thiết. Với clone đầy đủ, object database vẫn có thể chứa mọi blob và tree. Muốn giảm object tải ban đầu, cần partial clone filter.

### “Partial clone là shallow clone”

Không. Partial clone giới hạn object được tải; shallow clone giới hạn độ sâu commit. Có thể dùng một loại hoặc kết hợp cả hai.

### “Đã checkout một lần thì luôn làm việc offline được”

Chỉ các object đã có local mới sẵn sàng ngoại tuyến. Một lệnh tìm lịch sử hoặc checkout revision khác có thể cần blob/tree chưa được tải.

### “Không thấy conflict trong working tree nghĩa là merge sạch”

Không nên kết luận như vậy khi dùng sparse checkout. Hãy kiểm tra `git status`, `git diff --name-only --diff-filter=U` và `git ls-files -u`, đặc biệt với thay đổi ngoài sparse set.

### “Unshallow sẽ tải tất cả blob”

Không. `git fetch --unshallow` mở rộng lịch sử commit; partial clone filter vẫn có thể khiến blob hoặc tree chưa có local.

## 9. Checklist chọn chế độ clone

| Nhu cầu | Cách cân nhắc |
|---|---|
| Chỉ muốn working tree có một số thư mục nhưng cần toàn bộ lịch sử và object offline | Clone đầy đủ rồi dùng sparse checkout. |
| Muốn giảm tải nội dung tệp ban đầu, có mạng khi cần tra cứu thêm | Partial clone, thường bắt đầu với `--filter=blob:none`. |
| CI chỉ cần snapshot mới nhất để build/test ngắn hạn | Có thể dùng shallow clone, nếu pipeline không cần lịch sử sâu hoặc thao tác push đặc biệt. |
| Cần tìm kiếm/blame/merge trên lịch sử dài khi offline | Ưu tiên clone đầy đủ và fetch đủ refs. |
| Repository cực lớn, công việc chủ yếu ở một module | Kết hợp sparse checkout với partial clone; kiểm thử trước các tác vụ tìm kiếm và merge. |
| Cần chuẩn bị đi công tác hoặc vào vùng không có mạng | Materialize đường dẫn, object, lịch sử và kiểm thử offline; nếu rủi ro cao, tạo thêm clone đầy đủ. |

## 10. Quy trình làm việc mẫu cho monorepo lớn

Giả sử nhóm phát triển dịch vụ billing trong monorepo, nhưng thỉnh thoảng cần review thay đổi của identity và merge branch tích hợp.

**Bước 1: Clone có chọn lọc**

```bash
git clone --filter=blob:none --sparse https://example.com/team/monorepo.git monorepo
cd monorepo
```

**Bước 2: Chọn module cần làm**

```bash
git sparse-checkout init --cone
git sparse-checkout set services/billing libraries
```

**Bước 3: Trước khi review branch tích hợp, xem các đường dẫn thay đổi**

```bash
git fetch origin
git diff --name-status HEAD...origin/feature/integration
```

**Bước 4: Mở rộng sparse set tới các module liên quan**

```bash
git sparse-checkout add services/identity
```

**Bước 5: Merge và kiểm tra conflict**

```bash
git merge origin/feature/integration
git status
git ls-files -u
```

Nếu có conflict, giải quyết nội dung, stage tệp và hoàn tất merge theo hướng dẫn Git. Chạy test cho cả module có thay đổi, không chỉ thư mục ban đầu.

**Bước 6: Chuẩn bị offline**

Trước khi rời mạng, mở và kiểm thử các tệp, test fixture, script build, lịch sử và branch sẽ cần. Nếu cần blame sâu, fetch thêm lịch sử; nếu cần mọi dữ liệu offline, dùng clone đầy đủ.

## 11. Ghi nhớ

- Sparse checkout quyết định đường dẫn nào xuất hiện trong working tree.
- Partial clone quyết định object nào được tải; object thiếu có thể được lazy-fetch từ promisor remote.
- Shallow clone giới hạn lịch sử commit và có thể làm thiếu merge base hoặc kết quả blame/log sâu.
- Tìm kiếm trong working tree không thấy thư mục ngoài sparse set; tìm trong tree/history có thể cần tải blob/tree.
- Merge có thể cần object chưa có local và có thể cần xử lý đường dẫn ngoài sparse set; kiểm tra cả index bằng `git ls-files -u`.
- Làm việc offline chỉ đáng tin khi mọi object, đường dẫn và lịch sử mà tác vụ cần đã có local.
- `git fetch --unshallow` mở rộng lịch sử shallow nhưng không tự loại bỏ partial clone filter.
- Clone đầy đủ là lựa chọn dễ dự đoán hơn khi cần tra cứu, merge và làm việc ngoại tuyến toàn diện.

Trước khi chọn một bản clone nhẹ, hãy xác định công việc thực tế cần những tệp nào, lịch sử sâu tới đâu và có thể cần truy cập object nào. Tối ưu dung lượng tải ban đầu chỉ có ích khi nhóm hiểu rõ những lúc Git phải quay lại remote và đã có phương án cho thời điểm không có mạng.
