# Đo kích thước và số đối tượng bằng git count-objects

Khi repository Git lớn dần, cần biết dữ liệu đang chiếm bao nhiêu dung lượng và được lưu dưới dạng nào trước khi quyết định bảo trì. Git có thể lưu object riêng lẻ (*loose objects*) hoặc gom nhiều object vào packfile (*packed objects*). Lệnh `git count-objects` cung cấp số lượng và dung lượng của các nhóm object này, giúp bạn quan sát tình trạng object database mà không thay đổi repository.

Lệnh thường dùng nhất là `git count-objects -vH`. Tùy chọn `-v` hiển thị chi tiết các bộ đếm, còn `-H` trình bày dung lượng ở đơn vị dễ đọc. Kết quả giúp nhận biết repository có nhiều loose object, nhiều packfile, object loose trùng với object đã được pack hay có dữ liệu rác cần điều tra.

## 1. Git object database lưu những gì?

Git lưu nội dung và lịch sử bằng các object. Bốn loại object cơ bản là:

- **Blob:** nội dung của một tệp.
- **Tree:** cấu trúc thư mục, tên đường dẫn và tham chiếu đến blob hoặc tree con.
- **Commit:** snapshot tree, parent commit, author, committer và thông điệp.
- **Tag object:** metadata và chữ ký của annotated tag.

Các object này được lưu trong object database, thường nằm tại `.git/objects` đối với repository thông thường. Git có thể lưu object theo hai cách chính:

### Loose objects

Loose object là object được lưu riêng thành tệp trong cấu trúc thư mục theo hai ký tự đầu của OID. Ví dụ object có OID bắt đầu bằng `ab` sẽ nằm trong thư mục `objects/ab/` với tên phần OID còn lại. Nội dung object được nén để giảm dung lượng.

Loose object thường xuất hiện sau khi tạo commit, thêm nội dung hoặc nhận dữ liệu từ remote. Git có thể giữ nhiều loose object cho đến khi một quy trình repack hoặc garbage collection gom chúng lại.

### Packed objects

Khi có nhiều object, Git có thể gom chúng vào packfile để tiết kiệm dung lượng và giảm số lượng tệp filesystem. Packfile thường có phần dữ liệu `.pack` và chỉ mục `.idx` để tra cứu object nhanh. Git có thể dùng delta compression để lưu khác biệt giữa các phiên bản object liên quan.

Một repository có thể đồng thời chứa loose object và nhiều packfile. Đây là trạng thái bình thường; không phải cứ có loose object là repository đang lỗi hoặc cần chạy dọn dẹp ngay.

## 2. Cú pháp cơ bản của git count-objects

Chạy lệnh tại bất kỳ thư mục nào bên trong repository:

```bash
git count-objects
```

Lệnh báo số loose object và dung lượng loose object theo đơn vị KiB. Để xem thêm thông tin về packfile, object trùng có thể dọn và dữ liệu rác:

```bash
git count-objects -v
```

Để hiển thị dung lượng ở đơn vị dễ đọc:

```bash
git count-objects -vH
```

`-H` là dạng rút gọn của `--human-readable`. Kết quả có thể dùng `KiB`, `MiB`, `GiB` hoặc đơn vị phù hợp. Nếu cần so sánh bằng script, nên dùng output số liệu không có `-H` để tránh phải phân tích chuỗi đơn vị.

## 3. Đọc các trường trong output verbose

Ví dụ kết quả minh họa:

```text
count: 125
size: 812
in-pack: 15230
packs: 3
size-pack: 46120
prune-packable: 12
garbage: 0
size-garbage: 0
```

Khi chạy với `-H`, các trường dung lượng sẽ được hiển thị ở dạng dễ đọc, ví dụ `812.00 KiB` hoặc `45.04 MiB`. Ý nghĩa các trường:

| Trường | Ý nghĩa |
|---|---|
| `count` | Số loose object trong object directory đang được kiểm tra |
| `size` | Dung lượng loose object, tính bằng KiB nếu không dùng `-H` |
| `in-pack` | Số object được lưu trong packfile |
| `packs` | Số packfile hiện có |
| `size-pack` | Dung lượng packfile, tính bằng KiB nếu không dùng `-H` |
| `prune-packable` | Số loose object đã có bản tương ứng trong packfile và có thể được loại bỏ khỏi dạng loose khi dọn phù hợp |
| `garbage` | Số tệp trong object directory không phải loose object hợp lệ hoặc packfile hợp lệ |
| `size-garbage` | Dung lượng các tệp được phân loại là garbage, tính bằng KiB nếu không dùng `-H` |

Các giá trị là số liệu tại thời điểm chạy. Repository có thể thay đổi ngay sau đó do commit, fetch, repack, maintenance hoặc thao tác khác.

## 4. Phân biệt số lượng object và dung lượng

`count` và `in-pack` là hai bộ đếm ở hai cách lưu trữ khác nhau. Không nên cộng chúng một cách máy móc để kết luận có bao nhiêu object duy nhất hoặc bao nhiêu object còn được lịch sử hiện tại tham chiếu.

Một object có thể đang tồn tại ở dạng loose và đồng thời có bản trong packfile. Trường `prune-packable` cho biết số loose object có bản tương ứng trong pack, tức có thể dọn bản loose sau khi pack đã bảo đảm giữ object đó. Vì vậy, nếu thấy `count` là 125 và `prune-packable` là 12, có 12 trong số loose object đã có bản đóng gói tương ứng.

`in-pack` cũng không phải số object có thể đi tới từ branch hiện tại. Packfile có thể chứa object không còn được branch hoặc tag hiện tại tham chiếu, ví dụ object còn lại sau khi viết lại lịch sử hoặc xóa branch. `git count-objects` tập trung đo object storage, không phân tích đầy đủ khả năng reachable của từng object.

Nếu cần xác định object nào còn được tham chiếu hoặc đang unreachable, cần kết hợp các lệnh khác như `git rev-list`, `git fsck` và kiểm tra reflog. Không dùng riêng tổng số từ `count-objects` để kết luận repository có dữ liệu thừa.

## 5. Loose object tăng có phải là vấn đề không?

Loose object là một phần bình thường trong hoạt động Git. Sau khi tạo commit, Git thường ghi các object mới dưới dạng loose. Khi repository có nhiều object hoặc đến thời điểm maintenance, Git có thể gom chúng vào packfile.

Một số dấu hiệu đáng quan sát:

- `count` tăng liên tục sau nhiều thao tác commit hoặc fetch.
- `size` tăng nhanh so với dung lượng source code dự kiến.
- `prune-packable` lớn, cho thấy nhiều loose object đã có bản trong packfile.
- Có nhiều packfile nhỏ sau nhiều lần fetch hoặc cập nhật.

Những dấu hiệu này không tự động đồng nghĩa repository lỗi. Cần so sánh theo thời gian và bối cảnh. Ví dụ, một lần fetch branch lớn có thể làm số object tăng đáng kể; một lần repack có thể giảm loose object nhưng tăng dung lượng hoặc số lượng pack theo cách khác.

Để theo dõi xu hướng, chạy cùng một lệnh tại các mốc trước/sau fetch, merge hoặc maintenance:

```bash
git count-objects -vH
```

Ghi lại kết quả cùng thời điểm và thao tác vừa thực hiện. Cách so sánh nhất quán hữu ích hơn một con số đơn lẻ.

## 6. Hiểu trường prune-packable

`prune-packable` là trường quan trọng khi đánh giá trạng thái object storage. Nó đếm loose object đã có bản tương ứng trong packfile. Nếu object đã nằm trong pack, bản loose riêng lẻ thường không còn cần thiết cho việc đọc object.

Ví dụ:

```text
count: 500
in-pack: 12000
prune-packable: 430
```

Có 500 loose object, trong đó 430 object đã có bản trong packfile. Điều này có thể xảy ra sau khi Git repack object nhưng các loose bản sao vẫn chưa được dọn.

Git có lệnh `git prune-packed` để xóa loose object đã có bản trong pack. Tuy nhiên, người dùng thông thường không cần chạy thủ công lệnh này sau mỗi lần đo. Các quy trình maintenance và `git gc` có thể thực hiện việc dọn phù hợp. Nếu muốn chạy, cần hiểu repository có đang được tiến trình Git khác sử dụng hay không và tuân theo chính sách bảo trì của dự án.

Không nhầm `prune-packable` với số object unreachable. Đây là các object có bản sao trong pack, không phải kết luận về việc object có còn được commit hoặc ref sử dụng hay không.

## 7. Hiểu trường garbage và size-garbage

`garbage` đếm các tệp trong object directory không được nhận diện là loose object hợp lệ hoặc packfile hợp lệ. `size-garbage` cho biết dung lượng của những tệp đó.

Ví dụ:

```text
garbage: 2
size-garbage: 4096
```

Điều này cho biết có hai tệp bị phân loại là garbage với tổng dung lượng 4096 KiB. Chúng có thể là tệp tạm còn sót, tệp hỏng, file không đúng định dạng hoặc dữ liệu được tạo bởi một tiến trình bị gián đoạn.

Không nên xóa thủ công các tệp chỉ vì `garbage` khác 0. Trước hết, xác định file cụ thể và nguồn tạo ra nó. Một số thao tác Git có thể đang diễn ra hoặc vừa bị ngắt; xóa nhầm tệp trong object directory có thể làm hỏng dữ liệu repository.

Để điều tra sâu hơn, có thể xem object directory:

```bash
git rev-parse --git-path objects
```

Sau đó kiểm tra danh sách tệp bằng công cụ filesystem phù hợp. Không sửa nội dung object, packfile hoặc index bằng tay. Nếu nghi ngờ object database không nhất quán, dùng `git fsck --full` để kiểm tra tính toàn vẹn và sao lưu repository trước khi thực hiện biện pháp khắc phục.

## 8. Dùng số liệu để đánh giá packfile

Hai trường `packs` và `size-pack` giúp quan sát số lượng packfile cùng dung lượng dữ liệu đóng gói. Nhiều packfile nhỏ có thể xuất hiện sau nhiều lần fetch, push hoặc maintenance chưa gom lại. Tuy nhiên, số lượng pack lớn không tự động là lỗi; Git có thể quản lý nhiều pack theo thiết kế, bao gồm pack cruft và các pack có mục đích riêng tùy phiên bản/cấu hình.

Ví dụ:

```text
in-pack: 250000
packs: 18
size-pack: 840.00 MiB
```

Repository có 250.000 object trong packfile và 18 packfile với dung lượng pack khoảng 840 MiB. Nếu thao tác Git vẫn nhanh và dung lượng phù hợp, có thể không cần can thiệp. Nếu số pack tăng nhiều, fetch chậm hoặc dung lượng tăng bất thường, hãy xem xét thêm thông tin từ `git maintenance`, `git gc` hoặc phân tích packfile trước khi quyết định.

`size-pack` là dung lượng pack được Git báo cáo; nó không phải tổng dung lượng toàn bộ thư mục `.git`. Các thành phần như index pack, commit-graph, multi-pack-index, reflog, config, refs, hook và dữ liệu LFS có thể nằm ngoài con số này.

## 9. Quy trình đo trước và sau bảo trì

`git count-objects` là lệnh quan sát. Nó không tự repack, prune, xóa tệp hay thay đổi commit. Có thể dùng nó làm mốc đo trước và sau một thao tác bảo trì.

Ví dụ quy trình:

```bash
# 1. Kiểm tra trạng thái repository.
git status --short --branch

# 2. Đo object storage trước bảo trì.
git count-objects -vH

# 3. Xem phiên bản Git và trạng thái maintenance nếu cần.
git --version
git maintenance run --auto

# 4. Đo lại sau thao tác.
git count-objects -vH
```

`git maintenance run --auto` có thể quyết định thực hiện một số tác vụ bảo trì tùy cấu hình và ngưỡng. Nó được đưa vào ví dụ để minh họa cách đo trước/sau; không cần chạy chỉ vì `count` lớn. Trong môi trường production hoặc repository dùng chung, hãy tuân thủ lịch maintenance và chính sách vận hành.

Nếu cần chạy garbage collection thủ công, `git gc` có thể gom object và dọn dữ liệu theo quy tắc của Git. Hãy đọc tài liệu lệnh và đánh giá tác động trước khi chạy; `git count-objects` không yêu cầu phải gọi `git gc` sau mỗi lần đo.

## 10. Những gì git count-objects không đo

Kết quả `git count-objects` không phải tổng dung lượng của thư mục làm việc hoặc toàn bộ repository trên đĩa. Nó tập trung vào object database và các nhóm file object mà lệnh nhận diện.

Các thành phần không thể suy ra đầy đủ chỉ từ output này gồm:

- **Working tree:** các tệp đang checkout trong thư mục dự án.
- **Index:** dữ liệu staging area.
- **Refs và reflogs:** tên branch/tag và lịch sử cập nhật ref.
- **Metadata khác:** commit-graph, multi-pack-index, cấu hình, hook và file phụ trợ.
- **Git LFS:** nội dung LFS được lưu trong kho riêng, thường dưới `.git/lfs/objects`, không phải blob thông thường trong Git object database.
- **Submodule:** mỗi submodule là một repository riêng với object database riêng.
- **Alternate object database:** repository có thể dùng object từ một kho khác; cần hiểu cấu hình alternate khi diễn giải số liệu của object directory hiện tại.

Nếu mục tiêu là đo tổng dung lượng `.git` hoặc thư mục repository, hãy dùng công cụ filesystem để đo thư mục tương ứng. Nếu cần đo riêng LFS, dùng các lệnh `git lfs` và kiểm tra LFS storage. Không cộng các số liệu khác nguồn mà không xác định rõ chúng có chồng lặp hay không.

## 11. Kết hợp với lệnh kiểm tra khác

`git count-objects` trả lời câu hỏi tổng quan về số lượng và dung lượng object. Khi cần điều tra chi tiết, kết hợp các lệnh sau:

| Nhu cầu | Lệnh | Vai trò |
|---|---|---|
| Kiểm tra định dạng object database | `git count-objects -vH` | Đo loose/packed objects và dung lượng |
| Kiểm tra tính toàn vẹn object | `git fsck --full` | Phát hiện object hỏng, thiếu hoặc unreachable theo phạm vi kiểm tra |
| Xem lịch sử commit | `git log --oneline --all --decorate` | Hiểu branch/ref đang giữ lịch sử nào |
| Xem object database path | `git rev-parse --git-path objects` | Xác định nơi Git lưu object |
| Xem object type và nội dung | `git cat-file -t <oid>` / `git cat-file -p <oid>` | Kiểm tra object cụ thể |
| Phân tích packfile | `git verify-pack -v <pack-index>` | Xem object trong một pack và thông tin kích thước/delta |

Ví dụ, khi dung lượng pack tăng đột biến, có thể bắt đầu bằng:

```bash
git count-objects -vH
git log --oneline --all --decorate -20
git fsck --full
```

Nếu cần tìm blob lớn nhất, phải phân tích danh sách object và kích thước của chúng; `git count-objects` không cho biết tệp nào chiếm nhiều dung lượng. Một quy trình phân tích có thể dùng `git rev-list --objects --all` kết hợp `git cat-file --batch-check` hoặc công cụ chuyên dụng để xếp hạng blob.

## 12. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| `git count-objects` cho biết tổng dung lượng repository | Lệnh đo các nhóm object trong object database; không bao gồm toàn bộ working tree, LFS và metadata khác |
| `count + in-pack` luôn là số object duy nhất | Loose object có thể đã có bản trong pack; `prune-packable` thể hiện phần chồng lặp này |
| Nhiều loose object nghĩa là repository hỏng | Loose object là trạng thái lưu trữ bình thường và có thể được pack trong maintenance |
| `prune-packable` là số object unreachable | Đây là số loose object có bản tương ứng trong pack, không phải phép đo reachability |
| `garbage` khác 0 thì có thể xóa ngay | Cần xác định nguồn file và kiểm tra object database trước khi dọn |
| `-H` làm phép đo chính xác hơn | `-H` chỉ đổi cách trình bày dung lượng sang đơn vị dễ đọc |
| Chạy `git count-objects` sẽ dọn repository | Đây là lệnh đo, không tự repack hoặc prune object |
| Dung lượng pack là tổng dung lượng `.git` | Pack là một phần của metadata repository; còn nhiều thư mục và file khác |

## 13. Ghi nhớ

Để xem nhanh object storage, dùng:

```bash
git count-objects -vH
```

Đọc `count` và `size` cho loose object; `in-pack`, `packs` và `size-pack` cho dữ liệu đóng gói; `prune-packable` cho loose object đã có bản trong pack; `garbage` và `size-garbage` cho tệp không được nhận diện là object hoặc pack hợp lệ.

Hãy dùng số liệu như một chỉ báo để theo dõi xu hướng, không coi một giá trị riêng lẻ là bằng chứng repository cần dọn dẹp. `git count-objects` không xóa dữ liệu và không đo tổng dung lượng working tree, Git LFS hay mọi metadata. Khi cần quyết định maintenance, kết hợp kết quả với trạng thái repository, lịch sử, `git fsck` và công cụ phân tích phù hợp.
