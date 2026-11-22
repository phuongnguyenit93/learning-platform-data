# Giới hạn độ sâu lịch sử bằng --depth và --shallow-since

Một repository Git đầy đủ có thể chứa lịch sử nhiều năm với hàng nghìn hoặc hàng triệu commit. Khi chỉ cần lấy mã nguồn để build, chạy test hoặc triển khai một phiên bản gần nhất, tải toàn bộ lịch sử có thể tốn thời gian và dung lượng không cần thiết. **Shallow clone** cho phép lấy repository với phần lịch sử bị giới hạn, nhờ đó giảm lượng commit và object phải tải ban đầu.

Git cung cấp hai cách chọn ranh giới lịch sử thường dùng:

- `--depth=<n>` giới hạn độ sâu theo số commit tính từ tip của nhánh được lấy.
- `--shallow-since=<date>` giới hạn lịch sử theo mốc thời gian, chỉ giữ các commit có thể truy cập sau ngày được chỉ định.

Hai tùy chọn này thay đổi phần lịch sử commit mà repository có thể nhìn thấy. Chúng không chọn thư mục trong working tree và cũng không lọc riêng nội dung file. Để hiểu đúng phạm vi, cần phân biệt shallow clone với partial clone và sparse checkout.

## 1. Shallow clone là gì?

Shallow clone là một bản clone có lịch sử bị cắt tại một hoặc nhiều ranh giới. Git tải các commit và object cần thiết cho phần lịch sử được chọn, nhưng không tải toàn bộ tổ tiên của các commit đó.

Ví dụ repository đầy đủ có lịch sử:

~~~text
A---B---C---D---E---F---G  main
~~~

Nếu clone với `--depth=3`, lịch sử nhìn thấy có thể chỉ gồm ba commit gần tip:

~~~text
        E---F---G  main
        ^
        shallow boundary
~~~

Các commit A đến D không có trong phần lịch sử được clone. Commit E được xem như điểm bắt đầu của lịch sử cục bộ dù trong repository gốc nó có parent là D.

Git lưu thông tin ranh giới shallow trong metadata của repository. Vì vậy, các lệnh duyệt lịch sử biết rằng không nên tiếp tục lần theo parent vượt qua ranh giới đó.

Shallow clone vẫn là repository Git bình thường ở các thao tác cơ bản: có working tree, index, branch, commit và remote. Bạn có thể sửa file, tạo commit mới và push trong các trường hợp được máy chủ cho phép. Điểm khác biệt là các thao tác cần lịch sử tổ tiên đầy đủ có thể bị giới hạn.

## 2. Shallow clone khác gì với clone thông thường?

| Đặc điểm | Clone đầy đủ | Shallow clone |
|---|---|---|
| Lịch sử commit | Lấy lịch sử theo phạm vi ref được clone, thường đầy đủ | Bị cắt theo độ sâu hoặc mốc thời gian |
| Dung lượng ban đầu | Có thể lớn nếu lịch sử lâu năm | Thường nhỏ hơn vì bỏ bớt lịch sử cũ |
| Tốc độ clone | Phụ thuộc lượng object phải tải | Thường nhanh hơn với repository có lịch sử lớn |
| Duyệt lịch sử lâu dài | Có thể lần theo toàn bộ lịch sử đã clone | Dừng tại shallow boundary |
| Merge/rebase/merge-base | Có đầy đủ ancestry đã clone | Có thể thiếu tổ tiên cần thiết |
| Phù hợp | Phát triển dài hạn, phân tích lịch sử, phát hành | CI, build hoặc tác vụ chỉ cần phần lịch sử gần đây |

Shallow clone không có nghĩa là chỉ tải một file hoặc một thư mục. Nếu clone branch thông thường, Git vẫn checkout cây thư mục của branch đó; phần bị giới hạn là lịch sử commit.

## 3. Tạo shallow clone bằng --depth

Tùy chọn `--depth=<n>` giới hạn lịch sử theo số commit từ tip của các nhánh được lấy.

Clone chỉ lấy commit gần nhất của nhánh main:

~~~bash
git clone --depth=1 --branch main --single-branch https://example.com/team/app.git
~~~

Trong ví dụ:

- `--depth=1` chỉ lấy một mức commit từ tip.
- `--branch main` chọn nhánh main để checkout.
- `--single-branch` chỉ lấy lịch sử của nhánh được chỉ định.

Khi dùng `--depth`, Git mặc định ngầm áp dụng hành vi single-branch trừ khi bạn chỉ định `--no-single-branch`. Viết rõ `--single-branch` vẫn hữu ích vì thể hiện ý định của lệnh.

Clone với độ sâu 20:

~~~bash
git clone --depth=20 --branch main https://example.com/team/app.git
~~~

Bản clone này có thể duyệt khoảng 20 commit tính từ tip của nhánh main, tùy cấu trúc đồ thị commit và các nhánh/ref được lấy.

### Lấy nhiều nhánh với độ sâu giới hạn

Nếu muốn lấy các nhánh remote thay vì chỉ một nhánh, dùng `--no-single-branch`:

~~~bash
git clone --depth=10 --no-single-branch https://example.com/team/app.git
~~~

Git lấy các nhánh theo phạm vi clone nhưng giới hạn lịch sử của chúng theo độ sâu đã chọn. Lệnh này hữu ích khi pipeline cần so sánh nhiều nhánh hoặc cần kiểm tra một số nhánh release.

Hãy cân nhắc số nhánh cần thiết. Lấy nhiều nhánh với depth vẫn có thể tải nhiều object hơn so với clone một nhánh.

## 4. Depth là số commit, không phải số ngày

`--depth` biểu thị độ sâu lịch sử theo commit, không phải khoảng thời gian.

Giả sử repository có tốc độ phát triển khác nhau:

- Một dự án có thể tạo 100 commit trong một ngày.
- Một dự án khác chỉ tạo 10 commit trong một tháng.

Với `--depth=50`, cả hai đều lấy tối đa phạm vi 50 commit tính từ tip được chọn, dù khoảng thời gian lịch sử được bao phủ rất khác nhau.

Trong đồ thị có merge commit, lịch sử không phải lúc nào cũng là một đường thẳng. Một tip có thể có nhiều parent và Git phải duyệt ancestry theo cấu trúc đồ thị. Vì vậy, không nên hiểu depth là “50 commit gần nhất theo thời gian trên toàn repository” hoặc “50 commit trên một nhánh tuyến tính duy nhất”.

Nếu mục tiêu là giữ một khoảng thời gian gần đây, `--shallow-since` thường diễn đạt yêu cầu rõ hơn.

## 5. Giới hạn lịch sử theo ngày bằng --shallow-since

Tùy chọn `--shallow-since=<date>` tạo shallow clone với lịch sử gồm các commit có thể truy cập sau mốc thời gian được chỉ định.

Ví dụ, lấy lịch sử kể từ ngày 1/1/2025:

~~~bash
git clone --shallow-since="2025-01-01" https://example.com/team/app.git
~~~

Có thể chỉ định branch và remote branch cần lấy:

~~~bash
git clone --shallow-since="2025-01-01" --branch main --single-branch https://example.com/team/app.git
~~~

Khác với `--depth`, `--shallow-since` không tự kéo theo chế độ single-branch. `--branch main` chọn nhánh được checkout; nếu chỉ muốn lấy lịch sử của nhánh đó, hãy thêm `--single-branch` như ví dụ trên.

Git dùng mốc thời gian để xác định ranh giới lịch sử. Những commit cũ hơn mốc có thể bị lược khỏi bản clone, dù chúng vẫn là tổ tiên của các commit mới hơn trong repository gốc.

Ví dụ:

~~~text
2024-10   A---B
               \
2025-01         C---D---E
                    main
~~~ 

Nếu chọn `--shallow-since="2025-01-01"`, Git có thể lấy các commit C, D và E, đồng thời đặt ranh giới tại C thay vì lần tiếp các parent cũ hơn.

### Chọn định dạng ngày

Git chấp nhận định dạng ngày mà bộ phân tích ngày của Git hiểu được. Để lệnh dễ đọc và ổn định giữa môi trường, nên ưu tiên ngày ISO:

~~~bash
git clone --shallow-since="2025-01-01T00:00:00Z" https://example.com/team/app.git
~~~

Có thể dùng biểu thức ngày tương đối nếu cần:

~~~bash
git clone --shallow-since="6 months ago" https://example.com/team/app.git
~~~

Hãy đặt giá trị ngày trong dấu ngoặc kép để shell truyền toàn bộ chuỗi thành một đối số. Với pipeline tái lập được, ngày tuyệt đối thường phù hợp hơn ngày tương đối vì cùng một lệnh sẽ cho cùng một mốc thời gian ở các lần chạy khác nhau.

## 6. So sánh --depth và --shallow-since

| Tiêu chí | `--depth=<n>` | `--shallow-since=<date>` |
|---|---|---|
| Cách đặt ranh giới | Theo số commit từ tip | Theo mốc thời gian |
| Phù hợp khi | Chỉ cần một số commit gần nhất | Cần lịch sử trong khoảng thời gian gần đây |
| Ảnh hưởng khi tần suất commit thay đổi | Số lượng commit vẫn bị giới hạn theo depth | Số commit có thể tăng/giảm theo hoạt động dự án |
| Ví dụ | `--depth=30` | `--shallow-since="2025-01-01"` |
| Cách diễn đạt mục tiêu | “Lấy 30 mức commit gần tip” | “Lấy lịch sử sau ngày đã chọn” |

Không có một giá trị luôn tốt hơn. Nếu CI chỉ cần mã nguồn mới nhất, depth nhỏ có thể đủ. Nếu nhóm cần phân tích các thay đổi trong ba tháng gần đây, mốc thời gian có thể hợp lý hơn.

Một repository có nhiều commit trong một ngày có thể tạo ra shallow clone rất lớn với `--shallow-since`. Ngược lại, một repository ít commit có thể chỉ chứa vài commit trong nhiều tháng. Hãy chọn theo tác vụ thực tế và đo thời gian/dung lượng trong pipeline.

## 7. Kiểm tra repository có phải shallow hay không

Sau khi clone, có thể kiểm tra trạng thái bằng:

~~~bash
git rev-parse --is-shallow-repository
~~~

Kết quả:

~~~text
true
~~~

nghĩa là repository đang là shallow repository. Kết quả `false` nghĩa là Git không đánh dấu repository này là shallow.

Xem cấu hình remote và branch:

~~~bash
git remote -v
git branch -vv
git branch -r
~~~

Xem lịch sử hiện có:

~~~bash
git log --oneline --graph --decorate --all
~~~

Nếu lịch sử dừng đột ngột tại một commit cũ mà bạn biết repository gốc còn tổ tiên trước đó, có thể bản clone đang bị giới hạn độ sâu. Dùng `git rev-parse --is-shallow-repository` để xác nhận thay vì chỉ dựa vào số dòng trong git log.

Có thể hỏi Git đường dẫn metadata shallow:

~~~bash
git rev-parse --git-path shallow
~~~

Đường dẫn này trỏ tới file nội bộ ghi nhận shallow boundary. Hãy dùng nó để hiểu trạng thái hoặc hỗ trợ chẩn đoán; không chỉnh sửa file này bằng tay. Thay đổi độ sâu bằng các lệnh fetch được Git hỗ trợ.

## 8. Mở rộng lịch sử sau khi đã clone shallow

Một pipeline có thể bắt đầu với depth nhỏ để tiết kiệm thời gian, sau đó lấy thêm lịch sử khi cần.

### Đặt độ sâu mong muốn bằng --depth

Ví dụ repository ban đầu có depth 10, giờ cần lịch sử sâu hơn đến 100 commit:

~~~bash
git fetch --depth=100 origin refs/heads/main:refs/remotes/origin/main
~~~

Với fetch vào shallow repository, `--depth=<n>` đặt độ sâu mục tiêu tính từ tip của nhánh được fetch. Giá trị này có thể làm lịch sử sâu thêm hoặc ngắn lại so với trạng thái trước đó.

### Mở rộng thêm một số commit bằng --deepen

Nếu muốn mở rộng thêm 50 commit tính từ shallow boundary hiện tại:

~~~bash
git fetch --deepen=50 origin refs/heads/main:refs/remotes/origin/main
~~~

Phân biệt:

- `--depth=100`: yêu cầu độ sâu tổng thể là 100 từ tip.
- `--deepen=50`: mở rộng thêm 50 commit từ ranh giới shallow hiện tại.

Hai tùy chọn giải quyết hai cách diễn đạt khác nhau. Khi pipeline chạy nhiều lần, `--deepen` có thể hữu ích nếu muốn tăng lịch sử từng bước; `--depth` phù hợp khi muốn một độ sâu mục tiêu cụ thể.

### Mở rộng theo mốc thời gian

Nếu ban đầu clone theo ngày, có thể yêu cầu lấy thêm lịch sử bằng một mốc cũ hơn:

~~~bash
git fetch --shallow-since="2024-07-01" origin refs/heads/main:refs/remotes/origin/main
~~~

Lệnh yêu cầu lịch sử bao gồm các commit có thể truy cập sau mốc ngày mới. Chọn mốc sớm hơn để lấy thêm phần lịch sử cũ hơn.

### Lấy toàn bộ lịch sử bằng --unshallow

Khi cần lịch sử đầy đủ và remote có đủ lịch sử:

~~~bash
git fetch --unshallow origin
~~~

Lệnh này chuyển shallow repository thành repository không còn shallow boundary bằng cách lấy phần lịch sử còn thiếu. Nếu repository nguồn trên remote cũng là shallow, Git chỉ có thể lấy phần lịch sử mà nguồn đó có.

Sau khi fetch, xác minh lại:

~~~bash
git rev-parse --is-shallow-repository
git log --oneline --graph --decorate --all
~~~

Kết quả `false` cho biết repository local không còn ở trạng thái shallow.

## 9. Kết hợp với branch và refspec khi fetch

Một shallow clone thường được tạo cho một branch. Khi cần lấy thêm một branch khác, xác định rõ remote và refspec để tránh fetch ngoài phạm vi.

Ví dụ lấy thêm branch release:

~~~bash
git fetch --depth=30 origin refs/heads/release/2.x:refs/remotes/origin/release/2.x
~~~

Sau đó kiểm tra:

~~~bash
git branch -r
git log --oneline --decorate origin/release/2.x
~~~

Fetch cập nhật remote-tracking ref. Nó không tự chuyển branch local hiện tại sang branch vừa lấy và cũng không tự merge commit vào working tree.

Nếu cần làm việc trên branch đó:

~~~bash
git switch -c release/2.x --track origin/release/2.x
~~~

Trong shallow repository, việc tạo branch từ remote-tracking ref vẫn có thể thực hiện, nhưng lịch sử ancestry của branch mới vẫn bị giới hạn theo các shallow boundary hiện có.

## 10. Shallow clone và tag

Tag là nhãn gắn với object, thường là commit. Trong shallow clone, các tag liên quan tới lịch sử được fetch có thể được lấy tự động, nhưng không nên giả định mọi tag cũ trong repository đều đã có local.

Kiểm tra tag hiện có:

~~~bash
git tag --list
~~~

Nếu cần tag cụ thể:

~~~bash
git fetch origin tag v2.0.0
~~~

Tag có thể trỏ tới commit nằm ngoài phần lịch sử hiện có. Việc lấy tag không đồng nghĩa toàn bộ tổ tiên của commit đó đã được tải. Nếu cần xem lịch sử trước phiên bản, có thể phải deepen hoặc unshallow thêm.

Một số lệnh như `git describe` dựa vào tag có thể cho kết quả khác với clone đầy đủ nếu tag phù hợp không được fetch hoặc commit tổ tiên nằm ngoài shallow boundary. Trong CI tạo version string, hãy bảo đảm chiến lược fetch lấy đủ tag và lịch sử mà lệnh cần.

## 11. Tác động của shallow boundary tới các thao tác Git

Shallow clone rất phù hợp cho tác vụ ngắn, nhưng lịch sử bị cắt có thể ảnh hưởng các thao tác cần ancestry.

| Thao tác | Ảnh hưởng có thể gặp |
|---|---|
| `git log` | Lịch sử dừng tại shallow boundary |
| `git merge-base` | Có thể không tìm thấy merge base vì thiếu tổ tiên |
| `git merge` | Có thể cần fetch thêm lịch sử để tính toán quan hệ ancestry |
| `git rebase` | Có thể thiếu commit nền hoặc lịch sử để chọn đúng tập commit |
| `git blame` | Không thể lần về tác giả/thay đổi trước boundary |
| `git bisect` | Không thể kiểm tra commit nằm ngoài lịch sử đã tải |
| `git describe` | Có thể thiếu tag hoặc tổ tiên cần để tìm tag gần nhất |
| Phân tích release/changelog | Có thể thiếu commit và tag từ phiên bản trước |

Không phải mọi lệnh này luôn thất bại trong shallow clone. Chúng chỉ bị giới hạn khi tác vụ cần phần lịch sử chưa được tải. Khi gặp kết quả thiếu hoặc không tìm được merge base, hãy kiểm tra trạng thái shallow và fetch thêm lịch sử trước khi kết luận repository không có commit cần tìm.

## 12. Hạn chế khi push từ shallow repository

Shallow clone chủ yếu tối ưu thao tác lấy dữ liệu. Khi push, máy chủ cần kiểm tra quan hệ lịch sử giữa commit được gửi và ref đích.

Nếu shallow boundary làm thiếu commit cần thiết để xác minh cập nhật, máy chủ có thể từ chối push hoặc yêu cầu lấy thêm lịch sử. Hành vi cụ thể còn phụ thuộc cấu hình máy chủ và giao thức.

Nếu push bị từ chối vì lịch sử shallow:

1. Đọc thông báo lỗi và xác định ref nào bị từ chối.
2. Fetch thêm lịch sử từ remote.
3. Kiểm tra quan hệ giữa branch local và remote-tracking branch.
4. Tích hợp thay đổi theo quy trình nhóm.
5. Push lại sau khi xác nhận lịch sử phù hợp.

Ví dụ:

~~~bash
git fetch --unshallow origin
git log --oneline --graph --decorate --all
git push origin feature/payment
~~~

Không dùng force push để vượt qua vấn đề thiếu lịch sử. Force push có thể thay thế lịch sử remote và gây mất commit của người khác.

## 13. Shallow clone trong CI/CD

Shallow clone thường hữu ích trong pipeline vì runner chỉ cần mã nguồn của commit đang build hoặc một khoảng lịch sử ngắn để chạy test.

Ví dụ pipeline cần build commit hiện tại:

~~~bash
git clone --depth=1 --branch main --single-branch https://example.com/team/app.git
cd app
git rev-parse --short HEAD
./gradlew test
~~~

Nếu pipeline cần so sánh với một commit nền, ví dụ kiểm tra thay đổi giữa branch hiện tại và main, depth 1 có thể không đủ. Cần fetch thêm branch và lịch sử cần thiết:

~~~bash
git fetch --depth=100 origin refs/heads/main:refs/remotes/origin/main
git merge-base HEAD origin/main
~~~

Nếu pipeline tạo changelog từ tag gần nhất, cần fetch tag phù hợp và đủ ancestry:

~~~bash
git fetch --tags --unshallow origin
git describe --tags --abbrev=0
~~~

Ví dụ trên dùng unshallow khi cần toàn bộ lịch sử. Nếu repository rất lớn, có thể chọn depth hoặc shallow-since vừa đủ thay vì luôn tải tất cả.

### Chọn depth theo mục đích pipeline

| Mục tiêu CI | Cách chọn thường gặp |
|---|---|
| Build một commit, chạy unit test | `--depth=1` |
| So sánh vài commit gần nhất | Depth vừa đủ cho phạm vi so sánh |
| Tạo changelog theo release | Lấy tag và lịch sử từ mốc release trước |
| Chạy git bisect | Cần toàn bộ khoảng commit muốn tìm lỗi |
| Kiểm tra merge request | Fetch cả branch đích và đủ lịch sử để tính merge base |
| Tạo version bằng git describe | Fetch tag và ancestry cần thiết |

Depth càng nhỏ thì clone thường càng nhẹ, nhưng pipeline có thể phải fetch thêm ở các bước sau. Hãy cân bằng thời gian clone với nhu cầu của từng job.

## 14. Phân biệt shallow clone, partial clone và sparse checkout

Chương này nhóm các kỹ thuật giảm footprint của bản sao Git. Ba kỹ thuật có mục tiêu khác nhau:

| Kỹ thuật | Giới hạn điều gì? | Cơ chế chính | Ví dụ |
|---|---|---|---|
| Shallow clone | Lịch sử commit | Cắt ancestry tại shallow boundary | `git clone --depth=20` |
| Partial clone | Các object được tải | Lọc object, có thể lấy object còn thiếu khi cần | `git clone --filter=blob:none` |
| Sparse checkout | Đường dẫn trong working tree | Chỉ materialize các thư mục/file được chọn | `git sparse-checkout set src docs` |

### Shallow clone

Giảm lượng lịch sử commit phải tải. Working tree vẫn có thể chứa đầy đủ file của branch được checkout. Các commit cũ hơn boundary không có trong local history.

### Partial clone

Giảm object được tải từ server bằng object filter. Ví dụ `--filter=blob:none` trì hoãn tải blob cho tới khi cần. Lịch sử commit có thể vẫn đầy đủ nếu không kết hợp shallow option.

Partial clone cần server hỗ trợ filtering và cơ chế promisor remote. Khi công cụ truy cập blob chưa có, Git có thể lấy object đó từ remote theo cơ chế lazy fetch.

### Sparse checkout

Giảm số đường dẫn xuất hiện trong working tree. Repository có thể vẫn có lịch sử và object cần thiết; chỉ tập file được materialize ra working tree bị giới hạn. Sparse checkout hữu ích trong monorepo khi người dùng chỉ làm việc với một số thư mục.

Có thể kết hợp các kỹ thuật nếu phù hợp:

- Shallow clone để giới hạn lịch sử.
- Partial clone để giảm blob tải ban đầu.
- Sparse checkout để giới hạn file xuất hiện trong working tree.

Kết hợp nhiều cơ chế làm cấu hình và chẩn đoán phức tạp hơn. Hãy chọn theo nút thắt thực tế: lịch sử quá lớn, object file quá lớn hay working tree có quá nhiều thư mục.

## 15. Khi nào nên và không nên dùng shallow clone?

Shallow clone phù hợp khi:

- CI chỉ cần build/test commit mới nhất.
- Runner hoặc môi trường tạm thời cần checkout nhanh.
- Job chỉ cần một khoảng lịch sử ngắn.
- Repository lớn và pipeline không thực hiện thao tác cần ancestry sâu.
- Dữ liệu lưu trữ của runner bị giới hạn.

Cần cân nhắc clone đầy đủ khi:

- Phát triển tính năng dài hạn và thường xuyên rebase/merge.
- Điều tra bug cần git blame hoặc bisect qua lịch sử cũ.
- Tạo changelog, release note hoặc version dựa trên tag lâu đời.
- Kiểm toán lịch sử, xác minh nguồn gốc commit hoặc so sánh nhiều nhánh dài hạn.
- Công cụ build yêu cầu merge base hoặc ancestry đầy đủ.

Shallow clone không phải lựa chọn mặc định tốt nhất cho mọi repository. Nếu tác vụ thường xuyên phải unshallow ngay sau clone, có thể depth ban đầu đang quá nhỏ hoặc shallow clone không phù hợp với pipeline đó.

## 16. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `git log` dừng ở một commit cũ | Repository đang shallow | Kiểm tra `git rev-parse --is-shallow-repository`, fetch thêm history |
| `git merge-base` không tìm thấy kết quả | Thiếu tổ tiên do shallow boundary hoặc hai nhánh thật sự không có ancestor chung | Fetch branch đích và deepen/unshallow rồi thử lại |
| Không thấy tag release cũ | Tag không nằm trong tập ref/object đã fetch | Fetch tag cần thiết và lịch sử liên quan |
| Rebase hoặc merge bị lỗi liên quan shallow | Thiếu commit nền hoặc ancestry | Fetch thêm lịch sử trước khi tích hợp |
| Pipeline build được nhưng changelog sai/thiếu | Depth không đủ cho công cụ tạo changelog | Fetch từ tag hoặc mốc release trước |
| Clone depth nhỏ nhưng vẫn tải nhiều dữ liệu | Nhiều branch/ref được lấy hoặc file object lớn | Kiểm tra single-branch và cân nhắc partial clone |
| `git fetch --unshallow` không lấy được toàn bộ lịch sử | Remote nguồn cũng là shallow hoặc server giới hạn | Kiểm tra nguồn remote và chính sách server |
| Push bị từ chối | Máy chủ không thể xác minh quan hệ cập nhật từ lịch sử bị cắt | Fetch thêm history, xem log rồi push lại |

Không nên chỉnh sửa trực tiếp file shallow metadata để khắc phục. Dùng các tùy chọn fetch được Git cung cấp và kiểm tra trạng thái sau mỗi lần mở rộng lịch sử.

## 17. Quy trình mẫu: clone nhẹ rồi mở rộng khi cần

Giả sử pipeline build nhánh main và chỉ cần một commit mới nhất cho phần lớn job.

**Bước 1 — Clone nông**

~~~bash
git clone --depth=1 --branch main --single-branch https://example.com/team/app.git
cd app
~~~

**Bước 2 — Xác nhận trạng thái**

~~~bash
git rev-parse --is-shallow-repository
git log --oneline --decorate -5
~~~

**Bước 3 — Chạy tác vụ không cần lịch sử sâu**

~~~bash
./gradlew test
~~~

**Bước 4 — Khi cần so sánh với main hoặc tạo changelog, lấy thêm lịch sử**

~~~bash
git fetch --deepen=50 origin refs/heads/main:refs/remotes/origin/main
git log --oneline --graph --decorate --all
~~~

**Bước 5 — Nếu tác vụ yêu cầu lịch sử đầy đủ, unshallow**

~~~bash
git fetch --unshallow origin
git rev-parse --is-shallow-repository
~~~

**Bước 6 — Tiếp tục tác vụ**

~~~bash
git merge-base HEAD origin/main
~~~

Cách làm này giữ bước clone ban đầu nhẹ, nhưng vẫn cho phép pipeline lấy thêm dữ liệu đúng lúc cần. Trong workflow ổn định, nên đo thời gian và dung lượng để quyết định độ sâu ban đầu hợp lý.

## 18. Checklist trước khi chọn độ sâu lịch sử

- [ ] Job cần bao nhiêu commit để build/test?
- [ ] Có cần merge-base với branch đích không?
- [ ] Có cần git describe, changelog hoặc tag cũ không?
- [ ] Có chạy blame, bisect, rebase hoặc phân tích lịch sử không?
- [ ] Cần một branch hay nhiều branch?
- [ ] Chọn depth theo số commit hay mốc thời gian?
- [ ] Remote có hỗ trợ fetch thêm hoặc unshallow không?
- [ ] Pipeline có bước mở rộng lịch sử khi cần không?
- [ ] Đã kiểm tra bằng `git rev-parse --is-shallow-repository` chưa?
- [ ] Có thể dùng partial clone hoặc sparse checkout để giải quyết một nút thắt khác không?

## 19. Những điểm cần ghi nhớ

- Shallow clone là repository có lịch sử commit bị cắt tại shallow boundary.
- `--depth=<n>` giới hạn độ sâu theo commit từ tip; không phải số ngày và không phải số file.
- `--shallow-since=<date>` giới hạn lịch sử theo mốc thời gian.
- `--depth` mặc định kéo theo single-branch trừ khi dùng `--no-single-branch`.
- Dùng `git rev-parse --is-shallow-repository` để kiểm tra trạng thái.
- Dùng `git fetch --depth`, `--deepen` hoặc `--shallow-since` để lấy thêm lịch sử; `--unshallow` để lấy toàn bộ khi remote có đủ.
- Shallow boundary có thể ảnh hưởng merge-base, merge, rebase, blame, bisect, describe và changelog.
- Shallow clone giới hạn lịch sử; partial clone lọc object; sparse checkout giới hạn đường dẫn trong working tree.
- Chọn độ sâu theo nhu cầu thực tế của CI/CD hoặc công việc phát triển, và mở rộng lịch sử khi tác vụ cần.

Shallow clone giúp giảm thời gian và dung lượng lấy repository bằng cách chỉ tải một phần lịch sử. Khi chọn đúng giữa số commit và mốc thời gian, đồng thời hiểu giới hạn của ancestry, bạn có thể tăng tốc pipeline mà vẫn lấy đủ lịch sử cho từng tác vụ.

