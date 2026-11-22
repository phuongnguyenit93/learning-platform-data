# Phân biệt shallow clone, partial clone và sparse checkout

Khi làm việc với repository lớn, Git có ba cơ chế thường được dùng để giảm lượng dữ liệu cần tải hoặc số file cần làm việc cùng lúc: shallow clone, partial clone và sparse checkout. Tên gọi khá gần nhau nhưng chúng giải quyết ba vấn đề khác nhau.

- **Shallow clone** giới hạn độ sâu lịch sử commit được lấy về.
- **Partial clone** lọc object Git được tải từ remote, thường là nội dung blob của file.
- **Sparse checkout** giới hạn những đường dẫn được hiện diện trong working tree.

Ba cơ chế này có thể dùng riêng hoặc kết hợp. Muốn chọn đúng, trước hết cần xác định nút thắt là lịch sử quá dài, object/file quá lớn hay working tree có quá nhiều thư mục không liên quan.

## 1. Nhìn ba cơ chế theo ba lớp khác nhau

Một repository Git có thể được nhìn qua ba lớp:

1. **Commit graph:** chuỗi commit và quan hệ cha-con tạo nên lịch sử.
2. **Object database:** commit, tree, blob và tag object mà Git lưu để tái tạo lịch sử, thư mục và nội dung file.
3. **Working tree:** các file và thư mục đang được checkout ra ổ đĩa để bạn đọc và chỉnh sửa.

Shallow clone, partial clone và sparse checkout tác động vào các lớp khác nhau:

| Cơ chế | Giới hạn chính | Thứ được giảm | Thứ không tự động giảm |
|---|---|---|---|
| Shallow clone | Độ sâu commit history | Số commit và phần lịch sử phải tải | Số file của snapshot đang checkout |
| Partial clone | Loại hoặc kích thước object được tải | Object được truyền và lưu local, thường là blob | Số đường dẫn trong working tree nếu vẫn checkout toàn bộ |
| Sparse checkout | Đường dẫn được checkout | Số file/thư mục hiện diện trong working tree | Lịch sử commit và object đã có trong local repository |

Ví dụ:

- Repository có mười năm lịch sử nhưng snapshot mới nhất nhỏ: shallow clone có thể giảm thời gian lấy lịch sử.
- Repository chứa nhiều file nhị phân lớn hoặc nhiều source không cần đọc: partial clone có thể trì hoãn tải blob.
- Monorepo có hàng trăm service nhưng bạn chỉ phát triển một service: sparse checkout giúp working tree chỉ hiện phần liên quan.
- Nếu monorepo vừa có lịch sử dài, nhiều blob lớn và nhiều thư mục không cần dùng, có thể kết hợp cả ba.

Không nên coi ba cơ chế là ba tên gọi cho cùng một kiểu clone rút gọn. Một shallow clone vẫn có thể checkout đầy đủ mọi file ở commit hiện tại. Một sparse checkout không tự xóa lịch sử hay object khỏi local database. Một partial clone vẫn có thể hiện toàn bộ file nếu checkout toàn bộ repository và Git tải các blob cần thiết.

## 2. Shallow clone: lấy lịch sử commit có giới hạn

Shallow clone tạo repository mà lịch sử commit bị cắt tại một ranh giới nhất định. Cách đơn giản nhất là giới hạn số commit:

~~~bash
git clone --depth 1 https://example.com/team/inventory.git inventory
~~~

Tùy chọn --depth 1 yêu cầu lấy lịch sử với độ sâu một commit cho branch được clone. Git vẫn checkout snapshot của commit đó. Nếu snapshot chứa 20.000 file tracked, working tree vẫn có thể có đủ 20.000 file.

Một số cách giới hạn lịch sử khác:

~~~bash
git clone --depth 20 https://example.com/team/inventory.git inventory
git clone --shallow-since="2025-01-01" https://example.com/team/inventory.git inventory
git clone --shallow-exclude=v1.0.0 https://example.com/team/inventory.git inventory
~~~

- --depth <n> giới hạn số commit tính từ đầu branch được lấy.
- --shallow-since=<date> giới hạn lịch sử theo thời điểm.
- --shallow-exclude=<revision> loại lịch sử có thể truy cập từ revision được chỉ định khỏi phần lấy về.

### 2.1. Hệ quả của --depth

Khi dùng --depth, Git mặc định chỉ clone một branch (--single-branch), trừ khi bạn yêu cầu --no-single-branch.

~~~bash
git clone --depth 1 --no-single-branch https://example.com/team/inventory.git inventory
~~~

Cách này hữu ích khi cần shallow history cho nhiều branch remote. Hãy cân nhắc số ref cần theo dõi vì nó có thể làm lượng commit tải về lớn hơn.

Kiểm tra repository có phải shallow clone hay không:

~~~bash
git rev-parse --is-shallow-repository
~~~

Kết quả true nghĩa là repository hiện có ranh giới shallow; false nghĩa là lịch sử không còn shallow theo cách Git nhận biết.

Có thể quan sát lịch sử hiện có:

~~~bash
git log --oneline --decorate --all
git log --oneline --all --graph
~~~

Lịch sử hiển thị bị giới hạn ở phần commit đã lấy. Việc không nhìn thấy commit cũ không có nghĩa commit đó đã bị xóa khỏi remote.

### 2.2. Deepen hoặc bỏ giới hạn shallow

Khi cần thêm lịch sử để tìm merge base, chạy blame, bisect hoặc xem commit cũ, có thể lấy sâu thêm:

~~~bash
git fetch --deepen=50 origin main
~~~

Lệnh yêu cầu lấy thêm 50 commit từ ranh giới shallow hiện tại cho branch được chỉ định. Số commit thực tế có thể ít hơn nếu remote không còn đủ lịch sử theo nhánh đó.

Để lấy toàn bộ lịch sử còn thiếu từ remote đầy đủ:

~~~bash
git fetch --unshallow origin
~~~

--unshallow chuyển shallow repository thành repository có lịch sử đầy đủ nếu nguồn fetch cung cấp đầy đủ lịch sử. Nếu nguồn cũng là shallow repository, kết quả không thể vượt quá phần lịch sử nguồn đang có.

Kiểm tra lại:

~~~bash
git rev-parse --is-shallow-repository
git log --oneline --all --max-count=30
~~~

Nếu cần nhiều lịch sử hơn nhưng chưa muốn tải tất cả, dùng --deepen thay vì unshallow ngay lập tức.

### 2.3. Ưu điểm và giới hạn của shallow clone

**Ưu điểm**

- Giảm số commit phải tải và xử lý khi clone.
- Hữu ích cho CI chạy kiểm thử một commit hoặc branch mới nhất.
- Giảm chi phí khởi tạo khi lịch sử rất dài nhưng tác vụ chỉ cần snapshot hiện tại.

**Giới hạn**

- Lệnh cần đi ngược lịch sử có thể không thấy đủ commit hoặc merge base.
- git log, git blame, git bisect, so sánh nhánh và một số thao tác merge/rebase có thể cần lấy thêm lịch sử.
- Shallow clone không tự giảm số file trong snapshot đang checkout.
- Khi cần điều tra một lỗi xuất hiện từ lâu, có thể phải deepen hoặc unshallow.

Chọn shallow clone khi tác vụ thực sự chỉ cần phần lịch sử gần hiện tại. Nếu công việc thường xuyên cần truy tìm nguyên nhân qua nhiều tháng hoặc nhiều nhánh, hãy cân nhắc clone đầy đủ hoặc đặt độ sâu đủ dùng.

## 3. Partial clone: lọc object được tải từ remote

Partial clone cho phép client yêu cầu remote bỏ qua một số object trong lần clone đầu. Git ghi nhận remote là promisor remote: remote hứa có thể cung cấp object còn thiếu khi client cần.

Trường hợp phổ biến nhất là không tải blob ngay từ đầu:

~~~bash
git clone --filter=blob:none https://example.com/team/monorepo.git monorepo
~~~

blob:none yêu cầu không tải blob trong lần lấy object ban đầu. Commit và tree cần thiết vẫn được lấy để Git biết lịch sử và cấu trúc thư mục. Khi một thao tác cần nội dung blob còn thiếu, Git có thể lazy-fetch blob đó từ promisor remote.

Blob là object chứa nội dung file. Tree là object mô tả tên, mode và object được tham chiếu trong một thư mục. Vì vậy, blob:none không có nghĩa repository không biết tên file hoặc cấu trúc thư mục; nó trì hoãn nội dung file.

### 3.1. Các filter thường gặp

| Filter | Ý nghĩa | Trường hợp sử dụng |
|---|---|---|
| blob:none | Không lấy blob ban đầu; tải khi cần | Muốn lấy lịch sử/cấu trúc trước, chỉ tải nội dung file được sử dụng |
| blob:limit=1m | Bỏ qua blob có kích thước từ ngưỡng chỉ định trở lên | Muốn tải phần lớn file nhỏ nhưng trì hoãn file lớn |
| tree:0 | Clone theo kiểu treeless, trì hoãn tree object cho đến khi cần | Workflow tập trung vào commit và chấp nhận nhiều lần lấy object theo nhu cầu |

Ví dụ lọc blob lớn:

~~~bash
git clone --filter=blob:limit=1m https://example.com/team/assets.git assets
~~~

Ngưỡng có thể dùng hậu tố kích thước như k, m, g. Filter này bỏ qua blob đạt hoặc vượt giới hạn được chỉ định; các blob nhỏ hơn vẫn được tải theo quy tắc filter.

tree:0 là lựa chọn nâng cao. Nó có thể giảm đáng kể object tải ban đầu nhưng các thao tác cần duyệt cấu trúc hoặc checkout có thể khiến Git phải lấy thêm tree object. Với người mới hoặc workflow phát triển thông thường, blob:none dễ hiểu và dễ kết hợp với sparse checkout hơn.

### 3.2. Lazy fetch hoạt động như thế nào?

Giả sử bạn clone với --filter=blob:none. Git có commit và tree để biết repository gồm src/, docs/, assets/, nhưng một số blob chưa có local. Nếu clone thực hiện checkout đầy đủ, Git cần tải các blob thuộc snapshot đang checkout để tạo các file trong working tree; những blob chỉ xuất hiện ở các commit lịch sử khác vẫn có thể được trì hoãn.

Khi bạn checkout hoặc mở một file cần blob đó, Git yêu cầu object còn thiếu từ promisor remote. Sau khi tải, blob được lưu local và các lần đọc tiếp theo có thể dùng object đã có.

Điều này có nghĩa partial clone không đảm bảo mọi thao tác đều offline. Nếu cần một blob chưa được tải mà không có kết nối tới remote, thao tác có thể thất bại.

Một số lệnh có thể làm Git lấy về nhiều blob hơn bạn dự định, ví dụ checkout toàn bộ working tree, xuất archive của nhiều file, tìm kiếm nội dung trên toàn repository hoặc chạy công cụ cần đọc tất cả source. Lợi ích phụ thuộc vào workflow thực tế, không chỉ vào câu lệnh clone.

### 3.3. Kiểm tra cấu hình partial clone

Với clone đã dùng filter, kiểm tra:

~~~bash
git config --get remote.origin.promisor
git config --get remote.origin.partialclonefilter
~~~

Thông thường, promisor remote có giá trị true; filter có thể là blob:none hoặc filter đã chọn. Nếu không có cấu hình, repository có thể không phải partial clone theo cách đó.

Partial clone cần client Git hỗ trợ và server cho phép object filtering. Nếu server không hỗ trợ filter, Git có thể cảnh báo và thực hiện clone không được lọc như mong đợi. Hãy đọc output của lệnh clone và kiểm tra cấu hình sau đó; đừng chỉ nhìn thấy --filter trong câu lệnh rồi kết luận dữ liệu đã được giảm.

### 3.4. Ưu điểm và giới hạn của partial clone

**Ưu điểm**

- Trì hoãn tải nội dung file chưa cần dùng.
- Hữu ích với repository có nhiều file lớn, lịch sử blob nặng hoặc nhiều khu vực ít được truy cập.
- Có thể giữ lịch sử commit đầy đủ trong khi không tải mọi nội dung file ngay từ đầu.

**Giới hạn**

- Cần remote hỗ trợ filtering và lazy fetch.
- Những thao tác đọc nhiều file có thể kích hoạt tải nhiều blob, làm giảm lợi ích ban đầu.
- Phụ thuộc kết nối mạng khi cần object còn thiếu.
- Tooling cũ hoặc script giả định object luôn có local có thể hoạt động khác mong đợi.
- Partial clone không tự giới hạn đường dẫn trong working tree; muốn giảm số file checkout, kết hợp sparse checkout.

## 4. Sparse checkout: chỉ hiện những đường dẫn cần làm việc

Sparse checkout điều khiển những đường dẫn tracked nào được checkout vào working tree. Các file ngoài phạm vi sparse pattern không được hiện diện trong working tree theo cách checkout thông thường, nhưng vẫn thuộc repository.

Có thể áp dụng sparse checkout lên một clone đã có:

~~~bash
git sparse-checkout init --cone
git sparse-checkout set services/catalog shared/java
~~~

Trong ví dụ, working tree sẽ hiện các file ở root và nội dung trong hai thư mục được chọn. Cone mode tối ưu cho việc chọn thư mục; nó phù hợp với monorepo khi bạn muốn làm việc trên một hoặc vài service cùng thư viện dùng chung.

Kiểm tra các thư mục đang chọn:

~~~bash
git sparse-checkout list
~~~

Thêm một thư mục mà vẫn giữ các thư mục đã chọn:

~~~bash
git sparse-checkout add services/pricing
~~~

### 4.1. Cone mode

--cone là chế độ được khuyến nghị cho phần lớn trường hợp. Thay vì tự viết các pattern phức tạp, bạn chỉ định các thư mục cần checkout:

~~~bash
git sparse-checkout set services/catalog shared/java docs/api
~~~

Cone mode được tối ưu cho các tập hợp thư mục lồng nhau. Nó giữ file ở repository root, các file nằm trực tiếp trong thư mục cha trên đường dẫn tới thư mục được chọn, và toàn bộ nội dung của các thư mục đã chọn. Các thư mục anh em không được chọn sẽ không được đưa đầy đủ vào working tree.

Một lợi ích là pattern dễ đọc, dễ kiểm tra và có thể được Git biểu diễn hiệu quả bằng sparse index ở repository lớn.

Nếu cần chọn những file riêng lẻ hoặc pattern tùy biến theo kiểu .gitignore, Git có non-cone mode (--no-cone). Chế độ này linh hoạt hơn nhưng khó viết và có thể kém hiệu quả hơn. Với bài toán chọn một vài project directory trong monorepo, hãy ưu tiên cone mode.

### 4.2. Bật sparse checkout ngay khi clone

Có thể yêu cầu clone khởi tạo sparse checkout:

~~~bash
git clone --sparse https://example.com/team/monorepo.git monorepo
cd monorepo
git sparse-checkout set services/catalog shared/java
~~~

Tùy chọn --sparse bắt đầu với checkout hẹp, ban đầu chỉ lấy các file ở cấp root. Sau đó git sparse-checkout set mở rộng working tree theo các thư mục bạn cần.

Nếu đã clone bình thường, không cần clone lại chỉ để dùng sparse checkout. Chạy git sparse-checkout init --cone rồi git sparse-checkout set trên repository hiện tại.

### 4.3. Xem và tắt sparse checkout

Liệt kê phạm vi đang chọn:

~~~bash
git sparse-checkout list
~~~

Tắt sparse checkout và đưa toàn bộ file tracked trở lại working tree:

~~~bash
git sparse-checkout disable
~~~

Lệnh này mở rộng working tree về đầy đủ snapshot hiện tại. Trong partial clone, các blob còn thiếu cho những file mới được đưa vào có thể phải tải từ promisor remote.

Sparse checkout không xóa commit hoặc object khỏi repository. Nếu trước đó đã clone đầy đủ, các file ngoài sparse set vẫn có thể có blob local. Nó chỉ thay đổi nội dung checkout và trạng thái index liên quan tới sparse working tree.

### 4.4. Sparse checkout không phải cơ chế phân quyền

File nằm ngoài sparse set chỉ bị ẩn khỏi working tree hiện tại. Điều đó không có nghĩa người dùng không thể truy cập nội dung nếu object đã có local hoặc có thể fetch từ remote.

Không dùng sparse checkout để bảo vệ secret, mã nguồn nhạy cảm hoặc phân tách quyền truy cập. Hãy dùng repository permission, branch protection, server-side access control và quy trình quản lý secret phù hợp.

## 5. So sánh tác động và trade-off

Bảng dưới đây giúp chọn đúng công cụ theo nhu cầu:

| Câu hỏi | Shallow clone | Partial clone | Sparse checkout |
|---|---|---|---|
| Giảm commit history? | Có | Không, mặc định giữ lịch sử theo yêu cầu clone | Không |
| Lọc blob/tree object lúc tải? | Không theo filter object | Có | Không tự lọc object |
| Giảm file hiện diện trong working tree? | Không | Không nếu checkout đầy đủ | Có |
| Có thể tải thêm dữ liệu về sau? | Có thể deepen/unshallow | Có lazy fetch object | Có thể mở rộng sparse set; partial clone có thể fetch blob mới cần |
| Phụ thuộc server filter? | Không cần object filter | Có | Không cần object filter |
| Hữu ích nhất cho | CI hoặc tác vụ cần lịch sử ngắn | Repository nặng object, blob lớn | Monorepo có nhiều thư mục không cần dùng |

### 5.1. Chọn shallow clone khi

- CI chỉ cần checkout commit đang kiểm thử.
- Build không cần git describe dựa trên tag cũ, changelog dài hoặc lịch sử merge.
- Muốn giảm thời gian lấy lịch sử trong pipeline ngắn hạn.

Không chọn depth 1 nếu pipeline cần tính version từ tag, chạy git log để tạo changelog, hoặc dùng git merge-base với branch có lịch sử xa.

### 5.2. Chọn partial clone khi

- Repository có nhiều blob lớn hoặc nhiều nội dung ít khi truy cập.
- Bạn muốn giữ lịch sử commit nhưng trì hoãn tải nội dung file.
- Remote hỗ trợ filtering và môi trường có thể lazy-fetch khi cần.

Nếu luôn checkout và quét toàn bộ repository, partial clone có thể chỉ chuyển thời điểm tải blob từ lúc clone sang lúc build/test.

### 5.3. Chọn sparse checkout khi

- Monorepo có nhiều service hoặc project độc lập.
- Developer chỉ làm việc trên một số thư mục.
- Muốn working tree nhỏ, giảm số file IDE index và giảm nhiễu khi tìm kiếm.

Nếu clone đã có đầy đủ object, sparse checkout chủ yếu giảm số file trên ổ đĩa và lượng file tool phải xử lý; nó không làm repository object database nhỏ lại.

## 6. Kết hợp cả ba cho monorepo lớn

Trong một monorepo rất lớn, có thể cần:

- Lịch sử ngắn cho pipeline chỉ kiểm tra commit mới nhất.
- Chỉ tải blob khi cần.
- Chỉ checkout service và thư viện liên quan.

Ví dụ clone branch main với depth 1, blob filter và sparse checkout:

~~~bash
git clone \
  --depth 1 \
  --filter=blob:none \
  --sparse \
  --branch main \
  https://example.com/team/monorepo.git monorepo
~~~

Sau đó chọn khu vực làm việc:

~~~bash
cd monorepo
git sparse-checkout set services/catalog shared/java
~~~

Kiểm tra ba trạng thái:

~~~bash
git rev-parse --is-shallow-repository
git config --get remote.origin.promisor
git config --get remote.origin.partialclonefilter
git sparse-checkout list
git status -sb
~~~

Kỳ vọng:

- Shallow repository trả true.
- Promisor remote được cấu hình và filter thể hiện blob:none.
- Sparse list hiển thị services/catalog và shared/java.
- Working tree chỉ hiện root files cùng các khu vực được chọn theo cone mode.

Lưu ý quan trọng: --depth mặc định kéo theo --single-branch. Nếu pipeline cần nhiều branch, cần cân nhắc --no-single-branch, nhưng điều đó có thể tăng lượng lịch sử phải lấy. Chỉ mở rộng branch refs khi tác vụ thực sự cần.

Nếu developer cần lịch sử đầy đủ để bisect hoặc xem commit cũ, có thể deepen hoặc unshallow sau:

~~~bash
git fetch --deepen=100 origin main
~~~

Nếu cần file ở một khu vực khác, mở rộng sparse set:

~~~bash
git sparse-checkout add services/pricing
~~~

Nếu cần đầy đủ working tree:

~~~bash
git sparse-checkout disable
~~~

Các thao tác này giải quyết các giới hạn khác nhau: deepen bổ sung commit history; lazy fetch lấy object còn thiếu; sparse add/disable thay đổi phạm vi checkout.

## 7. Thực hành riêng từng cơ chế

Thay URL ví dụ bằng remote repository bạn được phép clone. Nên dùng repository thử nghiệm hoặc clone read-only để quan sát.

### 7.1. Thử shallow clone

~~~bash
git clone --depth 1 --branch main https://example.com/team/project.git project-shallow
cd project-shallow
git rev-parse --is-shallow-repository
git log --oneline --all
git ls-files
~~~

Quan sát:

- Repository được đánh dấu shallow.
- Lịch sử hiển thị ngắn.
- git ls-files vẫn có thể liệt kê toàn bộ file tracked của snapshot main.

Lấy thêm lịch sử:

~~~bash
git fetch --deepen=20 origin main
git log --oneline --all --max-count=30
git rev-parse --is-shallow-repository
~~~

Nếu cần đầy đủ lịch sử và remote có đủ object:

~~~bash
git fetch --unshallow origin
git rev-parse --is-shallow-repository
~~~

### 7.2. Thử partial clone

~~~bash
git clone --filter=blob:none https://example.com/team/project.git project-partial
cd project-partial
git config --get remote.origin.promisor
git config --get remote.origin.partialclonefilter
~~~

Quan sát cấu hình promisor và filter. Vì clone này checkout toàn bộ snapshot mặc định, Git có thể tải blob của các file trong snapshot hiện tại ngay trong quá trình checkout; filter vẫn giúp trì hoãn blob chỉ được tham chiếu bởi các commit lịch sử chưa cần. Khi mở file hoặc chạy lệnh cần nội dung blob còn thiếu, Git có thể lấy object từ remote.

Để thấy tác động rõ hơn trong repository lớn, kết hợp với sparse checkout ở phần tiếp theo. Nếu clone bình thường và checkout toàn bộ source ngay, Git có thể phải tải phần lớn blob cần cho working tree, khiến mức tiết kiệm ban đầu giảm.

### 7.3. Thử sparse checkout trên clone hiện có

~~~bash
git clone https://example.com/team/monorepo.git project-sparse
cd project-sparse
git sparse-checkout init --cone
git sparse-checkout set services/catalog shared/java
git sparse-checkout list
git status -sb
~~~

Quan sát working tree: các thư mục được chọn có nội dung, còn khu vực khác không được checkout. Lịch sử branch và các ref vẫn còn như trước.

Mở rộng rồi khôi phục đầy đủ:

~~~bash
git sparse-checkout add services/pricing
git sparse-checkout list
git sparse-checkout disable
~~~

Sau disable, các file tracked trong snapshot hiện tại được checkout đầy đủ. Nếu repository là partial clone, thao tác này có thể kích hoạt tải blob còn thiếu.

## 8. Những giới hạn cần tính trước

### 8.1. Shallow clone và thao tác cần lịch sử

Các tác vụ sau có thể cần thêm commit:

- Tìm merge base giữa hai branch.
- Rebase hoặc merge một branch có lịch sử nằm ngoài shallow boundary.
- Chạy git bisect qua một khoảng lịch sử dài.
- Dùng git blame hoặc git log để truy nguyên thay đổi cũ.
- Sinh changelog hoặc version từ tag xa.

Khi lệnh không tìm được tổ tiên hoặc lịch sử cần thiết, kiểm tra:

~~~bash
git rev-parse --is-shallow-repository
git log --oneline --all --decorate
~~~

Sau đó deepen có chủ đích hoặc unshallow nếu tác vụ cần lịch sử đầy đủ.

### 8.2. Partial clone và kết nối remote

Nếu object cần thiết chưa có local, Git cần liên hệ promisor remote để lazy-fetch. Một số môi trường CI bị cô lập mạng hoặc credential hết hạn có thể khiến thao tác đọc file thất bại.

Trước khi chạy tác vụ offline, hãy đảm bảo các object cần thiết đã được tải hoặc dùng clone đầy đủ phù hợp với nhu cầu. Đừng giả định git clone --filter=blob:none đã tải mọi nội dung file.

### 8.3. Sparse checkout và công cụ bên ngoài Git

Một số IDE, formatter, build tool hoặc script giả định mọi source directory đều hiện diện. Với sparse checkout, chúng có thể báo thiếu project hoặc bỏ qua module không nằm trong working tree.

Hãy chọn đủ các thư mục cần thiết như source, shared library, build script, schema, test fixture và cấu hình. Khi một build cần module ngoài sparse set, dùng git sparse-checkout add để mở rộng thay vì kết luận repository thiếu file.

### 8.4. Sparse index là tùy chọn riêng

Sparse checkout có thể dùng sparse index để giảm lượng entry trong index ở repository rất lớn:

~~~bash
git sparse-checkout init --cone --sparse-index
~~~

Sparse index nén các phần thư mục nằm ngoài sparse set thành directory entry thay vì giữ mọi file entry riêng lẻ trong index. Nó có thể tăng hiệu năng cho một số thao tác Git.

Tuy nhiên, tool bên ngoài đọc trực tiếp cấu trúc index có thể chưa tương thích với sparse index. Chỉ bật khi phiên bản Git và tooling của nhóm hỗ trợ; sparse checkout vẫn có thể dùng mà không cần sparse index.

## 9. Cách xác minh đã chọn đúng cơ chế

Dùng các lệnh sau để kiểm tra thay vì chỉ dựa vào tên thư mục hoặc output clone:

| Cần xác minh | Lệnh | Điều cần quan sát |
|---|---|---|
| Repository có shallow không | git rev-parse --is-shallow-repository | true hoặc false |
| Filter partial clone | git config --get remote.origin.partialclonefilter | Ví dụ blob:none |
| Promisor remote | git config --get remote.origin.promisor | Thường là true |
| Sparse paths | git sparse-checkout list | Danh sách thư mục đang chọn |
| File tracked trong index | git ls-files | Danh sách đường dẫn tracked; sparse checkout không xóa chúng khỏi repository |
| Working tree | git status -sb | Trạng thái file hiện checkout và thay đổi local |

Có thể xem thêm branch và remote:

~~~bash
git branch -avv
git remote -v
git status --short --branch
~~~

Đừng dùng git ls-files một mình để kết luận sparse checkout không hoạt động: lệnh này liệt kê file tracked trong index, kể cả đường dẫn hiện không có trong working tree vì sparse pattern. Nếu bật sparse index, một số lệnh có tùy chọn hiển thị dạng rút gọn có thể biểu diễn các thư mục ngoài sparse set bằng directory entry.

## 10. Chọn cấu hình theo tình huống

| Tình huống | Cấu hình gợi ý | Lý do |
|---|---|---|
| CI chỉ build commit hiện tại | git clone --depth 1 ... | Không cần tải toàn bộ commit history |
| Cần lịch sử đầy đủ nhưng repository có nhiều blob lớn | git clone --filter=blob:none ... | Giữ commit graph, trì hoãn blob |
| Monorepo, chỉ làm một service, clone đã đầy đủ | git sparse-checkout set services/catalog | Giảm working tree, không phải tải lại repository |
| Monorepo lớn, cần một vài service và shared library | --filter=blob:none --sparse rồi sparse-checkout set | Vừa trì hoãn blob, vừa giới hạn checkout |
| CI cần nhanh nhưng vẫn dùng monorepo một phần | --depth 1 --filter=blob:none --sparse | Giảm history, object ban đầu và working tree; cần kiểm tra tác vụ build có đủ dữ liệu |
| Điều tra regression lâu năm | Clone đầy đủ hoặc deepen/unshallow | Cần đủ ancestry, tag và commit cũ |

Không có cấu hình tối ưu cho mọi repository. Hãy đo thời gian clone, dung lượng object local, số file checkout và thời gian build trong workflow thực tế.

## 11. Những hiểu lầm thường gặp

- **Shallow clone chỉ tải vài file:** sai. Nó giới hạn commit history; snapshot được checkout vẫn có thể chứa toàn bộ file.
- **Partial clone không bao giờ tải blob:** sai. Blob bị trì hoãn và có thể được lazy-fetch khi thao tác cần nội dung.
- **Sparse checkout xóa file khỏi repository:** sai. File ngoài sparse set chỉ không được checkout vào working tree.
- **Sparse checkout tự giảm commit history:** sai. Nó không thay đổi độ sâu lịch sử.
- **Partial clone tự giảm số file đang checkout:** sai nếu vẫn checkout toàn bộ repository; cần sparse checkout để giới hạn đường dẫn.
- **Shallow clone và partial clone loại trừ nhau:** sai. Có thể kết hợp depth và object filter trong cùng lệnh clone.
- **Sparse checkout là biện pháp bảo mật:** sai. Nó không phải ranh giới quyền truy cập.
- **Clone với --filter chắc chắn đã được lọc:** chưa chắc. Server phải hỗ trợ filtering; hãy kiểm tra cảnh báo và cấu hình promisor/filter.
- **Tắt sparse checkout sẽ khôi phục lịch sử bị thiếu:** sai. git sparse-checkout disable mở rộng working tree; muốn lấy lịch sử phải dùng fetch/deepen hoặc unshallow.
- **Unshallow sẽ tải các blob bị filter bỏ qua:** không nhất thiết. Shallow history và object filter là hai cơ chế riêng; partial clone có thể vẫn giữ filter sau khi history được mở rộng.

## 12. Checklist trước khi chọn

- [ ] Xác định vấn đề là lịch sử commit, dung lượng object hay số file trong working tree.
- [ ] Kiểm tra tác vụ có cần git log, blame, bisect, merge base hoặc tag cũ không.
- [ ] Xác nhận remote hỗ trợ partial clone nếu dùng --filter.
- [ ] Chọn đúng branch và phạm vi branch refs nếu dùng --depth.
- [ ] Chọn đủ thư mục source, shared code, build scripts, test data và cấu hình nếu dùng sparse checkout.
- [ ] Kiểm tra promisor/filter, shallow state và sparse list sau khi clone.
- [ ] Xác minh build/test hoạt động trong working tree đã chọn.
- [ ] Đánh giá tác động tới offline workflow, IDE và công cụ của nhóm.
- [ ] Ghi lại cách mở rộng history, tải thêm object và mở rộng sparse paths khi cần.

## 13. Ghi nhớ

Shallow clone giảm độ sâu commit history; partial clone lọc object được tải, thường trì hoãn blob; sparse checkout giới hạn đường dẫn hiện diện trong working tree. Chúng giải quyết ba nút thắt độc lập và có thể kết hợp. Với CI chỉ cần commit mới nhất, shallow clone thường đủ. Với repository nặng blob, partial clone giúp tải nội dung theo nhu cầu. Với monorepo, sparse checkout giúp chỉ hiện những project đang làm. Khi kết hợp, hãy kiểm tra cả history, promisor/filter và sparse paths, đồng thời đảm bảo build/test có đủ source và object cần thiết.
