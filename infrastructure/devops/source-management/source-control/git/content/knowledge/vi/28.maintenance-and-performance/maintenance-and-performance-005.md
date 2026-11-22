# Đóng gói lại đối tượng với repack và đánh đổi dung lượng với thời gian

Git lưu nội dung repository dưới dạng các object như blob, tree, commit và tag. Khi mới tạo, nhiều object có thể nằm riêng lẻ trong object database dưới dạng **loose objects**. Khi repository lớn dần, Git gom các object vào **packfile** để giảm chi phí lưu trữ và giúp truyền dữ liệu hiệu quả hơn. Lệnh `git repack` thực hiện việc đóng gói lại này, đồng thời có thể sắp xếp lại cách object được nén và chia sẻ dữ liệu.

Repack ảnh hưởng đến cách Git lưu object trên đĩa, không viết lại nội dung commit hay thay đổi OID của commit. Việc chọn cấu hình repack là một đánh đổi: tìm kiếm delta kỹ hơn thường tiết kiệm dung lượng hơn nhưng tốn CPU, bộ nhớ và thời gian; delta chain sâu hơn có thể giảm dung lượng nhưng làm việc tái tạo object tốn thêm công sức.

## 1. Loose object và packfile

Khi Git tạo object, object được lưu trong object database. Trong repository dùng backend file truyền thống, object mới thường bắt đầu dưới dạng loose object trong thư mục `objects`, được nén riêng. Khi có nhiều object, Git có thể đóng gói chúng vào packfile.

| Dạng lưu trữ | Cách tổ chức | Đặc điểm |
|---|---|---|
| Loose object | Mỗi object có file riêng, tên theo OID | Dễ ghi object mới, nhưng số lượng file có thể rất lớn |
| Packfile | Nhiều object được ghi nối tiếp trong một file `.pack` | Giảm overhead file và hỗ trợ nén delta giữa các object tương tự |
| Pack index | File `.idx` đi kèm pack | Ánh xạ OID đến vị trí object trong pack để Git tìm nhanh |
| Reverse index | File `.rev` tùy chọn | Ánh xạ thứ tự offset trong pack về thứ tự object, hữu ích cho một số thao tác duyệt pack |
| Bitmap index | File `.bitmap` tùy chọn | Lưu thông tin reachability để tăng tốc một số thao tác như clone và fetch |

Đường dẫn object database có thể khác nhau, nhất là trong linked worktree hoặc repository dùng common directory. Dùng lệnh Git để xác định vị trí thay vì mặc định `.git` luôn là thư mục:

```bash
git rev-parse --git-path objects
git rev-parse --git-path objects/pack
```

Packfile không phải một bản sao lưu độc lập. Git vẫn cần refs và object database để xác định những object nào đang được sử dụng. File `.idx` cho phép tìm object trong `.pack`; nếu thiếu index, Git có thể tái tạo nó trong một số tình huống, nhưng không nên tự xóa hoặc sửa các file pack.

## 2. Delta compression tiết kiệm dung lượng ra sao?

Nhiều object trong một repository có nội dung gần giống nhau. Ví dụ, một file mã nguồn được sửa qua nhiều commit có thể giữ lại phần lớn dòng cũ và chỉ thay đổi một số đoạn. Packfile có thể lưu một object làm **delta** so với một object cơ sở (base), thay vì lưu lại toàn bộ nội dung.

Minh họa đơn giản:

```text
Blob A: [phần đầu][logic cũ][phần cuối]
Blob B: [phần đầu][logic mới][phần cuối]
                     |
                     +-- delta: thay logic cũ bằng logic mới
```

Khi cần đọc Blob B, Git lấy base rồi áp dụng delta để tái tạo nội dung đầy đủ. Delta có thể tham chiếu object cơ sở bằng offset trong cùng pack (OFS_DELTA) hoặc bằng OID (REF_DELTA). Người dùng làm việc với object đã được Git tái tạo; chi tiết delta là cách pack lưu trữ object bên dưới.

Delta compression có thể giảm mạnh kích thước pack, đặc biệt với repository có nhiều phiên bản của cùng file hoặc nhiều file tương tự. Tuy nhiên, Git phải tìm object phù hợp làm base và có thể phải áp dụng nhiều lớp delta khi đọc object.

## 3. `git repack` làm gì?

`git repack` đọc object từ object database, chọn tập object cần đóng gói, tạo packfile mới và tùy tùy chọn sẽ xóa pack cũ đã trở nên dư thừa. Lệnh có thể:

- Gom loose objects vào packfile.
- Kết hợp nhiều pack nhỏ thành pack lớn hơn.
- Tìm lại delta base để cải thiện mức nén.
- Tạo bitmap index cho một số workload cần tính reachability nhanh.
- Đóng gói riêng object unreachable vào cruft pack để quản lý vòng đời của chúng.

Ví dụ thường gặp để đóng gói tất cả object reachable từ refs vào pack và xóa các pack cũ đã được thay thế:

```bash
git repack -a -d
```

Trong đó:

- `-a` yêu cầu đóng gói các object được tham chiếu (reachable) vào pack mới.
- `-d` xóa các pack cũ khi object của chúng đã được pack mới thay thế, đồng thời dọn loose object đã có trong pack.

Lệnh này không đồng nghĩa với việc xóa mọi object unreachable. Nếu pack cũ còn chứa object unreachable, Git cần xử lý chúng theo quy tắc tương ứng; có thể dùng `--cruft` hoặc `-A` tùy mục tiêu. Không xóa thủ công các pack cũ để cố giải phóng dung lượng.

Repack không thay đổi lịch sử commit theo nghĩa Git: OID của commit, tree và blob vẫn giữ nguyên. Nó thay đổi vị trí và cách mã hóa object trên đĩa. Working tree và nhánh hiện tại không bị đổi chỉ vì chạy repack.

## 4. Đo trạng thái object database trước khi repack

Trước khi tối ưu, ghi nhận số lượng loose object, số pack và dung lượng đang dùng:

```bash
git count-objects -vH
```

Một số trường thường gặp:

| Trường | Ý nghĩa |
|---|---|
| `count` | Số loose object |
| `size` | Dung lượng loose object |
| `in-pack` | Số object đang nằm trong pack |
| `packs` | Số packfile hiện có |
| `size-pack` | Dung lượng packfile |
| `prune-packable` | Số loose object đã có bản trong pack và có thể được dọn |
| `garbage` / `size-garbage` | File không được nhận diện là object hợp lệ và dung lượng tương ứng |

Kết quả là điểm đo ban đầu để so sánh sau repack. Dung lượng hiển thị là dung lượng object database mà Git nhận biết; nó không bao gồm toàn bộ working tree, log ứng dụng, file build hoặc bản sao lưu bên ngoài.

Kiểm tra các pack hiện có:

```bash
git verify-pack -v <pack-index-path>
```

Thay `<pack-index-path>` bằng đường dẫn file `.idx` thực tế trong thư mục pack. Kết quả chi tiết có thể cho biết OID, loại object, kích thước object sau tái tạo, kích thước dữ liệu packed, offset và độ sâu delta. Dòng tổng kết cho biết số object và thông tin kích thước của pack.

Nếu cần kiểm tra tính toàn vẹn object database, dùng:

```bash
git fsck --full
```

`git fsck` kiểm tra liên kết và tính hợp lệ của object. Nó là bước chẩn đoán khác với repack; repack không sửa nội dung object bị hỏng hoặc thay thế cho backup.

## 5. Đóng gói theo các mục tiêu khác nhau

### Đóng gói toàn bộ object reachable

```bash
git repack -a -d
```

Dùng khi muốn gom các object reachable vào pack mới và loại bỏ pack cũ đã dư thừa. Với repository lớn, thao tác có thể đọc và ghi lượng dữ liệu đáng kể, cần dung lượng trống tạm thời trong lúc tạo pack mới.

### Đóng gói object mới theo kiểu incremental

```bash
git repack -d
```

Không có `-a`, Git có thể đóng gói các loose object chưa nằm trong pack và dọn các pack dư thừa theo phạm vi lựa chọn. Cách này thường phù hợp cho bảo trì tăng dần, tránh yêu cầu tạo lại một pack duy nhất từ toàn bộ lịch sử.

### Giữ object unreachable dưới dạng loose

```bash
git repack -A -d
```

`-A` có hành vi tương tự `-a`, nhưng các object unreachable trong pack cũ được unpack thành loose object thay vì bị loại bỏ cùng pack cũ. Tùy chọn này hữu ích khi muốn thay pack nhưng vẫn giữ object chưa reachable để có thời gian kiểm tra hoặc phục hồi. Nó không có nghĩa là object unreachable sẽ được giữ vĩnh viễn; các object đó vẫn có thể bị dọn sau này theo chính sách prune và thời hạn lưu trữ.

### Đóng gói object unreachable bằng cruft pack

```bash
git repack -d --cruft
```

Cruft pack là pack dành cho các object unreachable. Nó giúp quản lý các object này riêng với pack chứa object reachable, đồng thời lưu metadata cần thiết để Git áp dụng chính sách hết hạn. Khi dùng `--cruft-expiration=<date>`, Git có thể loại bỏ object unreachable cũ hơn mốc đã chọn; chỉ dùng khi đã hiểu ảnh hưởng đến khả năng phục hồi.

Object unreachable có thể vẫn cần thiết sau một lần reset hoặc rebase. Trước khi đặt thời hạn ngắn hoặc dọn cruft, hãy kiểm tra reflog, backup và các commit cần giữ.

## 6. Delta window và delta depth

Hai tham số quan trọng ảnh hưởng trực tiếp đến mức nén là `--window` và `--depth`.

| Tham số | Ý nghĩa | Khi tăng giá trị |
|---|---|---|
| `--window=<n>` | Số object ứng viên Git xem xét trong cửa sổ tìm delta base | Có thêm cơ hội tìm base tương tự hơn; thường tốn CPU và bộ nhớ hơn |
| `--depth=<n>` | Độ sâu tối đa của chuỗi delta | Cho phép chuỗi delta dài hơn; có thể giảm dung lượng nhưng làm tăng chi phí tái tạo object |

Ví dụ yêu cầu tìm kiếm rộng hơn và cho phép delta chain sâu hơn:

```bash
git repack -a -d --window=100 --depth=50
```

Giá trị lớn không phải lúc nào cũng tốt. Nếu object không có base tương tự, cửa sổ lớn hơn có thể tốn thời gian mà không giảm pack đáng kể. Delta chain quá sâu có thể khiến một số thao tác đọc object hoặc duyệt lịch sử tốn thêm CPU.

### Ví dụ tối ưu nén lại từ đầu

```bash
git repack -a -d -f --window=100 --depth=50
```

`-f` yêu cầu không tái sử dụng delta hiện có khi tạo pack, để Git tính toán delta mới theo tham số hiện tại. Việc này có thể cải thiện mức nén nếu pack cũ được tạo với cửa sổ nhỏ, nhưng thường tốn thời gian đáng kể. Không chạy thường xuyên nếu không có số liệu cho thấy pack hiện tại đang cần tối ưu.

## 7. CPU, bộ nhớ và số luồng

Repack có thể sử dụng nhiều CPU trong bước tìm delta và nén object. Tham số `--threads=<n>` điều khiển số luồng xử lý nén trong các phần hỗ trợ đa luồng:

```bash
git repack -a -d --threads=4
```

Nhiều luồng có thể giảm thời gian chạy trên máy có CPU dư, nhưng cũng làm tăng mức sử dụng CPU và bộ nhớ. Nếu máy đang chạy IDE, build hoặc database local, repack nhiều luồng có thể làm các tác vụ tương tác chậm đi.

`--window-memory=<n>` giới hạn bộ nhớ dùng cho cửa sổ tìm delta theo cách Git hỗ trợ. Kích thước cửa sổ, bộ nhớ cửa sổ và số luồng cần được cân nhắc cùng nhau; tăng tất cả cùng lúc có thể làm mức dùng RAM tăng đáng kể.

Hãy bắt đầu bằng mặc định hoặc một số luồng vừa phải, đo thời gian và dung lượng sau repack, rồi mới tăng tham số. Nếu repository lớn và máy có giới hạn RAM, một repack lâu hơn nhưng ổn định có thể phù hợp hơn một lần chạy quá tải.

## 8. Giới hạn kích thước pack và số lượng pack

`--max-pack-size=<n>` đặt giới hạn kích thước pack được tạo. Khi giới hạn nhỏ, Git có thể tạo nhiều pack hơn thay vì một pack lớn:

```bash
git repack -a -d --max-pack-size=2g
```

Chia pack có thể hữu ích khi môi trường có giới hạn kích thước file hoặc cần quản lý dữ liệu theo lô. Tuy nhiên, quá nhiều pack làm tăng số index phải tra cứu và có thể làm một số thao tác object tốn thêm chi phí. Khi repository giữ nhiều pack, Multi-Pack Index (MIDX) giúp tra cứu OID trên nhiều pack mà không phải mở từng index theo cách độc lập.

Kiểm tra hoặc tạo multi-pack-index:

```bash
git multi-pack-index write
git multi-pack-index verify
```

MIDX không gộp các pack thành một pack duy nhất; nó tạo index chung để Git tìm object trong tập pack hiện có. Khi cần tối ưu số pack, hãy xem các tác vụ incremental repack và bảo trì tự động của Git thay vì tùy tiện xóa pack.

## 9. Bitmap index và tốc độ clone/fetch

Một pack có thể đi kèm bitmap index để Git xác định tập object reachable từ các ref nhanh hơn trong một số thao tác truyền dữ liệu. Bitmap đặc biệt hữu ích ở repository server có nhiều clone hoặc fetch.

Có thể yêu cầu tạo bitmap index trong lần repack:

```bash
git repack -a -d --write-bitmap-index
```

Bitmap cần thêm dung lượng lưu trữ và việc tạo bitmap có chi phí tính toán. Không phải mọi cấu hình repository hoặc mọi loại pack đều có thể tạo bitmap theo cùng cách; Git có các điều kiện và giới hạn tùy phiên bản, loại object và cấu hình. Hãy kiểm tra kết quả và đo hiệu năng fetch/clone thực tế.

Bitmap giúp tăng tốc tính toán reachability khi tạo pack để truyền đi; nó không làm working tree hoặc lệnh đọc file thông thường nhanh lên một cách tự động.

## 10. Repack hình học và bảo trì incremental

Repository có nhiều pack không nhất thiết phải gộp toàn bộ thành một pack trong mỗi lần bảo trì. Repack hình học giúp chọn một nhóm pack nhỏ để hợp nhất sao cho kích thước pack có xu hướng tăng theo cấp số nhân, tránh việc liên tục viết lại pack lớn nhất.

Ví dụ:

```bash
git repack --geometric=2 -d
```

Hệ số hình học lớn hơn có thể giữ nhiều pack nhỏ hơn và giảm lượng dữ liệu cần repack mỗi lần, nhưng đổi lại Git có thể phải quản lý nhiều pack. Hệ số nhỏ hơn thường gom nhiều pack hơn, giảm số pack nhưng làm mỗi lần bảo trì tốn nhiều I/O hơn.

Với repository lớn, Git còn hỗ trợ incremental maintenance và Multi-Pack Index. Tùy phiên bản, có thể chạy tác vụ incremental repack qua:

```bash
git maintenance run --task=incremental-repack
```

Tác vụ này thường làm việc cùng MIDX để hợp nhất các pack nhỏ theo từng đợt. Đây là cách giảm chi phí của một lần full repack kéo dài, đặc biệt khi repository nhận object liên tục.

## 11. Bảng đánh đổi giữa dung lượng và thời gian

| Lựa chọn | Dung lượng pack | Thời gian repack | Chi phí khi đọc / truyền |
|---|---|---|---|
| Window nhỏ | Có thể lớn hơn do ít ứng viên base | Thường nhanh hơn | Ít delta được tối ưu hơn; pack lớn hơn có thể tăng dữ liệu truyền |
| Window lớn | Có thể nhỏ hơn nếu tìm được base tốt | Tốn CPU hơn | Có thể giảm dữ liệu truyền; hiệu quả phụ thuộc cấu trúc object |
| Depth thấp | Có thể lớn hơn vì chuỗi delta ngắn | Thường dễ tạo hơn | Tái tạo object ít lớp hơn |
| Depth cao | Có thể nhỏ hơn | Có thể tốn thêm thời gian tìm và tạo delta | Có thể tốn thêm CPU khi tái tạo object |
| Nhiều thread | Không trực tiếp bảo đảm pack nhỏ hơn | Có thể nhanh hơn trên CPU nhiều lõi | Tăng tranh chấp CPU/RAM nếu chạy đồng thời với tác vụ khác |
| Nhiều pack nhỏ | Thường có thêm overhead index/pack | Repack từng phần có thể nhẹ hơn | MIDX giúp tra cứu; nếu thiếu MIDX, nhiều pack có thể làm tăng chi phí tìm object |
| Một pack lớn | Có thể giảm overhead và tối ưu delta toàn cục tốt hơn | Full repack có thể lâu và cần nhiều I/O | Có thể thuận tiện cho truyền dữ liệu, nhưng thao tác cập nhật pack lớn tốn tài nguyên |
| Bitmap index | Tăng nhẹ dung lượng metadata | Tốn thêm thời gian tạo bitmap | Có thể tăng tốc tính reachability khi clone/fetch |

Không có cấu hình tối ưu cho mọi repository. Repository lưu nhiều file text tương tự có thể hưởng lợi từ window lớn; repository chứa nhiều file nhị phân đã nén thường ít được lợi từ delta compression. Hãy đo dữ liệu thực tế thay vì chỉ tăng tham số theo cảm tính.

## 12. Quy trình repack có kiểm soát

Một quy trình an toàn trước và sau repack:

```bash
# 1. Kiểm tra trạng thái làm việc
git status --short

# 2. Ghi nhận dung lượng và số object trước khi repack
git count-objects -vH

# 3. Kiểm tra object database nếu đang chẩn đoán bất thường
git fsck --full

# 4. Đóng gói các object reachable và loại pack dư thừa
git repack -a -d

# 5. Đo lại sau repack
git count-objects -vH

# 6. Xác minh pack mới nếu cần
git verify-pack -v <pack-index-path>
```

So sánh `size-pack`, `packs`, `in-pack` và thời gian chạy trước/sau. Nếu mục tiêu là giảm thời gian clone/fetch, hãy đo cả thao tác truyền dữ liệu; nếu mục tiêu là giảm dung lượng đĩa, so sánh kích thước object database trên cùng một repository và cùng trạng thái refs.

Repack có thể cần dung lượng trống để giữ pack cũ trong lúc tạo pack mới. Trên repository lớn, hãy lên lịch vào thời điểm ít hoạt động, bảo đảm đủ dung lượng đĩa và tránh chạy nhiều tiến trình bảo trì cạnh tranh cùng lúc. Git sử dụng lock để bảo vệ nhiều thao tác nội bộ, nhưng không nên dựa vào lock để cho phép xóa hoặc sửa file pack thủ công.

## 13. Khi nào nên dùng `git gc` thay vì tự gọi repack?

`git gc` là lệnh bảo trì cấp cao, có thể thực hiện repack cùng các công việc dọn dẹp khác như prune object hết hạn, cập nhật metadata và tối ưu repository. Git cũng có cơ chế auto maintenance khi một số ngưỡng được đạt đến.

```bash
# Chạy bảo trì tổng quát theo chính sách Git
git gc

# Yêu cầu bảo trì tự động nếu cần thiết
git gc --auto

# Xem cấu hình bảo trì liên quan
git config --show-origin --get gc.auto
git config --show-origin --get maintenance.auto
```

`git gc` không chỉ là cách viết khác của `git repack -a -d`: nó có thể thực hiện thêm các bước quản lý object và metadata. Nếu cần tối ưu riêng cách nén hoặc delta, dùng `git repack` với tham số cụ thể. Nếu chỉ cần bảo trì thường kỳ, ưu tiên cơ chế mặc định của Git hoặc lịch `git maintenance` đã được nhóm thống nhất.

Không dùng `git gc --prune=now` như một lệnh dọn dung lượng thông thường. Tham số này có thể loại bỏ object unreachable ngay, làm mất cơ hội phục hồi commit vừa bị reset hoặc rebase. Chỉ prune khi đã xác nhận object không còn cần thiết và repository không có thao tác đang diễn ra cần các object đó.

## 14. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
|---|---|
| Repack tạo lại commit và đổi OID | Repack thay đổi cách lưu object trên đĩa; OID của commit/tree/blob không đổi. |
| `git repack -a -d` xóa mọi object unreachable | Nó đóng gói object reachable và xóa pack dư thừa; object unreachable cần được xử lý theo chính sách riêng. |
| Window càng lớn thì luôn tốt hơn | Window lớn tìm nhiều base hơn nhưng tốn CPU/RAM và không bảo đảm pack nhỏ hơn. |
| Depth càng lớn thì Git luôn nhanh hơn | Delta chain sâu có thể tiết kiệm dung lượng nhưng tăng chi phí tái tạo object. |
| Nhiều thread luôn giảm tổng thời gian | Hiệu quả phụ thuộc CPU, RAM, I/O và tác vụ chạy đồng thời. |
| `.idx` chứa nội dung object | `.idx` ánh xạ OID đến vị trí trong `.pack`; dữ liệu object nằm trong packfile. |
| Bitmap làm mọi lệnh Git nhanh hơn | Bitmap chủ yếu hỗ trợ tính reachability và tạo pack cho một số thao tác truyền dữ liệu. |
| Có thể xóa pack cũ bằng tay sau repack | Dùng `-d` và công cụ Git để quản lý pack; xóa thủ công có thể làm mất object còn được tham chiếu. |
| Reflog không còn thì object chắc chắn đã mất | Object có thể còn trong pack hoặc cruft pack; khả năng phục hồi phụ thuộc object còn tồn tại và có ref giữ lại hay không. |

## 15. Tự kiểm tra

1. **Loose object khác packfile như thế nào?**
   - Loose object được lưu riêng từng file; packfile gom nhiều object vào một file và có thể dùng delta compression.
2. **File `.idx` có nhiệm vụ gì?**
   - Ánh xạ OID đến offset object trong packfile.
3. **`git repack -a -d` thường dùng để làm gì?**
   - Đóng gói object reachable vào pack mới và loại bỏ pack cũ đã trở nên dư thừa.
4. **Tăng `--window` có đánh đổi gì?**
   - Git có thêm ứng viên tìm delta base, có thể nén tốt hơn nhưng tốn CPU và bộ nhớ hơn.
5. **`--depth` điều khiển điều gì?**
   - Độ sâu tối đa của chuỗi delta; chuỗi sâu hơn có thể tiết kiệm dung lượng nhưng tăng chi phí tái tạo object.
6. **Bitmap index hữu ích nhất trong tình huống nào?**
   - Tăng tốc một số phép tính reachability và tạo pack phục vụ clone/fetch.
7. **Vì sao không nên chạy prune ngay sau khi phát hiện commit bị mất?**
   - Object unreachable có thể là dữ liệu cần phục hồi; prune có thể loại bỏ object đó khỏi object database.

## Kết luận

`git repack` gom loose object và các pack hiện có thành packfile mới, có thể dùng delta compression để giảm dung lượng. `--window` quyết định phạm vi tìm base, `--depth` giới hạn chuỗi delta, còn số thread và giới hạn pack ảnh hưởng CPU, RAM, I/O và số pack phải quản lý. Hãy đo bằng `git count-objects -vH`, kiểm tra pack bằng `git verify-pack -v` và chọn mức tối ưu theo workload thực tế. Với bảo trì thường kỳ, cân nhắc `git gc` hoặc incremental maintenance; luôn thận trọng với object unreachable và các thao tác prune vì chúng có thể làm mất cơ hội phục hồi lịch sử.
