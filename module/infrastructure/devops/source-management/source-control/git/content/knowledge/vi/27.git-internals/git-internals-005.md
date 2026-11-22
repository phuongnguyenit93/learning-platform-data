# Đối tượng rời, packfile, nén delta và tệp chỉ mục pack

Git lưu lịch sử bằng các object bất biến được nhận diện theo nội dung. Khi một object mới được tạo, Git có thể lưu nó dưới dạng object rời (loose object). Khi repository lớn lên, nhiều object được gom vào packfile để giảm dung lượng và tăng hiệu quả lưu trữ. Packfile có thể dùng nén delta để lưu phần khác biệt giữa các object tương tự, còn tệp chỉ mục pack giúp Git tìm object nhanh mà không phải quét toàn bộ pack.

Hiểu các thành phần này giúp bạn giải thích vì sao thư mục .git/objects có nhiều file tên khó đọc, vì sao sau fetch hoặc garbage collection xuất hiện file .pack và .idx, cũng như cách kiểm tra dung lượng và tính toàn vẹn của object database.

Sau bài này, bạn có thể:

- Giải thích object rời và cách Git đặt tên object theo nội dung.
- Nhận diện các loại object commit, tree, blob và tag.
- Mô tả cấu trúc cơ bản của packfile.
- Giải thích delta compression và hai cách tham chiếu object nền.
- Phân biệt pack index .idx với staging index .git/index.
- Dùng các lệnh cat-file, count-objects, verify-pack và fsck để kiểm tra dữ liệu.
- Hiểu vai trò của repack và garbage collection.

## 1. Git object database lưu những gì?

Git không lưu lịch sử chỉ bằng các bản vá văn bản nối tiếp nhau. Repository lưu các object mô tả nội dung và quan hệ giữa các phiên bản. Bốn loại object cơ bản là:

| Loại object | Nội dung |
| --- | --- |
| blob | Nội dung của một file; không lưu tên file hoặc đường dẫn. |
| tree | Danh sách tên, mode, loại và object ID của các mục trong một thư mục. |
| commit | Snapshot gốc của một phiên bản, thông tin tác giả/committer, thông điệp và các commit cha. |
| tag | Đối tượng tag có chú giải, trỏ tới một object và lưu metadata như tagger, thời gian, thông điệp, có thể kèm chữ ký. |

Một commit thường trỏ tới một tree đại diện cho thư mục gốc của snapshot. Tree có thể trỏ tới tree con hoặc blob. Commit cũng trỏ tới commit cha để tạo thành lịch sử. Annotated tag là object riêng; lightweight tag chỉ là ref trỏ tới object.

Git object được nhận diện bằng object ID (OID), được tính từ biểu diễn chuẩn của object gồm header và nội dung. Header có dạng khái quát:

~~~text
<type> <size> NUL <content>
~~~

Ví dụ, object blob có header gồm loại blob, số byte nội dung và byte NUL phân cách trước nội dung thực tế. Git băm toàn bộ biểu diễn chuẩn này để tạo OID. Cùng loại và cùng nội dung sẽ tạo cùng OID trong cùng một định dạng hash repository.

Các repository Git truyền thống thường dùng SHA-1 với OID dài 40 ký tự hex. Git cũng hỗ trợ repository dùng SHA-256, trong đó OID dài 64 ký tự hex. Có thể xem định dạng hash của repository hiện tại:

~~~bash
git rev-parse --show-object-format
~~~

Đừng giả định mọi repository đều có OID 40 ký tự. Các lệnh Git thường chấp nhận OID đầy đủ hoặc dạng viết tắt đủ duy nhất trong repository.

## 2. Object rời (loose object) được lưu như thế nào?

Khi Git ghi một object chưa được đóng gói, object đó thường nằm trong object database theo đường dẫn:

~~~text
.git/objects/aa/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
~~~

Hai ký tự hex đầu của OID trở thành tên thư mục; phần còn lại trở thành tên file. Cách chia này tránh tạo một thư mục duy nhất chứa quá nhiều file.

Ví dụ OID:

~~~text
e69de29bb2d1d6434b8b29ae775ad8c2e48c5391
~~~

Đường dẫn loose object tương ứng:

~~~text
.git/objects/e6/9de29bb2d1d6434b8b29ae775ad8c2e48c5391
~~~

Nội dung file loose object được nén bằng zlib. Vì vậy, nếu mở file bằng trình soạn thảo văn bản, bạn sẽ không thấy nội dung header và file gốc ở dạng đọc được. Git giải nén và diễn giải object khi cần.

Loose object là đơn vị lưu trữ độc lập. Git có thể tạo chúng khi ghi object mới, ví dụ khi thêm nội dung vào index hoặc tạo commit. Khi repository được bảo trì hoặc nhận nhiều dữ liệu, Git có thể gom các object rời vào packfile.

## 3. Tạo và đọc object để quan sát

Có thể dùng git hash-object để tính OID của một file mà không ghi object vào database:

~~~bash
git hash-object README.md
~~~

Thêm tùy chọn -w để ghi object vào object database:

~~~bash
git hash-object -w README.md
~~~

Lệnh trả về OID của blob. Việc ghi object không tự tạo commit và cũng không tự stage file.

Giả sử lệnh trả về OID abc123...; bạn có thể kiểm tra loại object:

~~~bash
git cat-file -t abc123
~~~

Xem kích thước nội dung:

~~~bash
git cat-file -s abc123
~~~

In nội dung object:

~~~bash
git cat-file -p abc123
~~~

Với blob, -p in nội dung file. Với tree, lệnh hiển thị các mục và OID. Với commit, lệnh hiển thị metadata cùng tree và parent. Với tag, lệnh hiển thị nội dung đối tượng tag.

Có thể truy xuất OID của file tại một commit:

~~~bash
git rev-parse HEAD:README.md
~~~

Sau đó dùng cat-file để xem object mà tree của commit tham chiếu. Cách này cho thấy tên file không nằm trong blob; tên và đường dẫn được lưu trong tree, còn blob chỉ chứa byte nội dung.

## 4. Vì sao Git cần packfile?

Nếu repository giữ mọi object thành file rời mãi mãi, số lượng file trong .git/objects có thể rất lớn. Mỗi object có một file riêng, làm tăng chi phí metadata của hệ thống tệp và gây tốn thời gian khi duyệt hoặc sao chép nhiều object nhỏ.

Packfile gom nhiều object vào một file lớn hơn. Git có thể nén object và biểu diễn một số object bằng delta so với object nền tương tự. Việc gom này giúp:

- Giảm số lượng file trong object database.
- Giảm dung lượng khi nhiều object có nội dung tương tự.
- Truyền một nhóm object hiệu quả hơn qua fetch, clone hoặc push.
- Tổ chức dữ liệu để Git tra cứu và đọc tuần tự hiệu quả.

Packfile thường nằm trong:

~~~text
.git/objects/pack/
|-- pack-<hash>.pack
|-- pack-<hash>.idx
+-- pack-<hash>.rev
~~~

File .rev là reverse index có thể được tạo thêm trong một số phiên bản và quy trình bảo trì; không phải mọi pack đều bắt buộc phải có file này. Những file cơ bản cần nhận diện là .pack và .idx.

Đường dẫn object database và thư mục pack có thể lấy bằng Git thay vì tự ghép từ .git, đặc biệt khi làm việc với linked worktree hoặc cấu trúc repository đặc biệt:

~~~bash
git rev-parse --git-path objects
git rev-parse --git-path objects/pack
~~~

## 5. Cấu trúc cơ bản của packfile

Packfile là định dạng nhị phân. Ở mức khái niệm, một pack gồm:

1. Header nhận diện pack, phiên bản định dạng và số object được đóng gói.
2. Các entry mô tả object; entry có thể chứa object đầy đủ hoặc delta so với object nền.
3. Checksum ở cuối pack để kiểm tra tính toàn vẹn của dữ liệu pack.

Header bắt đầu bằng chuỗi ASCII PACK. Sau đó là số phiên bản pack và số entry. Các phiên bản pack phổ biến là 2 và 3. Mỗi entry có header mã hóa loại object và kích thước dữ liệu theo dạng số biến độ dài, tiếp theo là nội dung nén.

Với entry lưu object đầy đủ, nội dung sau khi giải nén tương ứng với nội dung object. Với entry delta, dữ liệu giải nén là chỉ dẫn để tái tạo object đích từ một object nền.

Packfile có thể chứa các object commit, tree, blob và tag. Nó cũng có thể chứa các entry delta, thường được biểu diễn bằng loại OFS_DELTA hoặc REF_DELTA. Hai loại này mô tả cách tìm object nền để tái tạo object đích.

Không nên chỉnh sửa .pack bằng trình soạn thảo hoặc xóa file riêng lẻ. Packfile là dữ liệu nhị phân có cấu trúc và được liên kết với chỉ mục tương ứng.

## 6. Delta compression là gì?

Trong lịch sử Git, nhiều blob có thể rất giống nhau. Ví dụ, một file source code có vài dòng thay đổi qua nhiều commit. Nếu mỗi phiên bản đều lưu nguyên vẹn trong pack, dung lượng có thể tăng đáng kể.

Delta compression lưu một object đích dưới dạng hướng dẫn tái tạo từ một object nền (base object). Thay vì lặp lại toàn bộ nội dung, delta có thể:

- Sao chép một đoạn byte từ object nền.
- Chèn một đoạn byte mới.
- Kết hợp nhiều thao tác sao chép và chèn để tạo nội dung hoàn chỉnh.

Ví dụ minh họa:

~~~text
Object nền:
    public class Search {
        return query;
    }

Object đích:
    public class Search {
        return normalize(query);
    }

Delta khái niệm:
    COPY phần đầu từ object nền
    INSERT "normalize("
    COPY phần còn lại phù hợp
    INSERT ")"
~~~

Đây chỉ là mô hình minh họa, không phải cú pháp delta thực tế của packfile. Delta thật là dữ liệu nhị phân với chỉ dẫn copy/insert và thông tin kích thước.

Khi Git cần object đích, nó tìm object nền, áp dụng các chỉ dẫn delta và tái tạo byte nội dung hoàn chỉnh. Sau khi tái tạo, object có cùng OID như khi được lưu dưới dạng loose object hoặc object đầy đủ trong pack.

Điều quan trọng: delta compression là tối ưu lưu trữ. Nó không thay đổi ý nghĩa lịch sử, nội dung logic hoặc mã OID của object. Việc Git hiển thị diff giữa hai commit là một hoạt động khác; delta trong pack là cách biểu diễn vật lý object trên đĩa.

## 7. OFS_DELTA và REF_DELTA

Pack format có hai cách phổ biến để chỉ ra object nền của một delta:

| Loại delta | Cách tham chiếu base | Đặc điểm |
| --- | --- | --- |
| OFS_DELTA | Dùng độ lệch byte tới entry nền trước đó trong cùng pack. | Không cần ghi đầy đủ OID của base; phù hợp khi base nằm trong cùng pack. |
| REF_DELTA | Dùng OID của object nền. | Có thể tìm base bằng OID trong object database; không phụ thuộc vị trí byte của base trong pack hiện tại. |

OFS_DELTA cho phép xác định base bằng offset tương đối trong pack. REF_DELTA dùng OID để xác định base, do đó Git có thể tìm base trong các object đã có sẵn theo cơ chế tra cứu object database.

Một delta có thể phụ thuộc vào một delta khác. Khi đó Git phải tái tạo chuỗi từ base ban đầu qua các lớp delta cho tới object cần đọc. Chuỗi quá sâu có thể làm tăng chi phí giải nén, nên khi repack Git cân nhắc độ sâu và hiệu quả nén.

Không phải mọi object trong pack đều được lưu dưới dạng delta. Commit và tree thường nhỏ; một số blob cũng không phù hợp để delta. Git chọn cách lưu dựa trên kích thước, độ tương đồng và chính sách đóng gói.

## 8. Tệp chỉ mục pack (.idx) làm nhiệm vụ gì?

Packfile có thể chứa hàng nghìn hoặc hàng triệu object. Nếu muốn tìm object theo OID, Git không nên phải quét tuần tự toàn bộ file pack để tìm entry tương ứng. Tệp chỉ mục pack .idx cung cấp ánh xạ từ OID tới vị trí entry trong pack.

Chỉ mục pack thường chứa:

- Bảng fanout 256 phần tử giúp thu hẹp vùng tìm kiếm theo byte đầu tiên của OID.
- Danh sách OID được sắp xếp.
- CRC32 tương ứng với dữ liệu entry trong pack ở định dạng index phiên bản 2.
- Offset tới entry trong pack.
- Bảng offset 64-bit bổ sung khi offset không vừa trường 32-bit.
- Checksum của pack và checksum của chính file index.

Nhờ danh sách OID được sắp xếp và bảng fanout, Git có thể tìm object nhanh, sau đó dùng offset để đọc entry tương ứng trong .pack.

Tên file index thường có cùng basename với pack:

~~~text
pack-abc123.pack
pack-abc123.idx
~~~

Hai file thuộc cùng một cặp. Nếu xóa hoặc thay một file mà không cập nhật file còn lại, object database có thể không đọc được pack như mong muốn. Hãy để Git quản lý chúng qua fetch, repack và garbage collection.

## 9. Phân biệt pack index với staging index

Tên gọi index dễ gây nhầm lẫn:

| Thành phần | Đường dẫn thường gặp | Vai trò |
| --- | --- | --- |
| Staging index | .git/index | Lưu snapshot tạm đã stage để chuẩn bị tạo commit tiếp theo. |
| Pack index | .git/objects/pack/pack-<hash>.idx | Tra cứu OID và offset của object trong một packfile. |

Staging index tham gia vào quy trình working tree → staging area → commit. Pack index thuộc object database và phục vụ tra cứu dữ liệu đã đóng gói. Chúng không thay thế hoặc cập nhật lẫn nhau.

Ví dụ:

~~~bash
# Xem các thay đổi trong staging area
git diff --cached

# Xem file staging index của repository
git rev-parse --git-path index

# Xem thư mục pack chứa .pack và .idx
git rev-parse --git-path objects/pack
~~~

Đừng xóa file .git/index để sửa packfile, và cũng đừng xóa file pack .idx để bỏ một thay đổi khỏi staging area. Đây là hai loại index khác nhau, phục vụ hai mục đích khác nhau.

## 10. Quan sát object rời và packfile trong repository

Lệnh tổng quan hữu ích:

~~~bash
git count-objects -vH
~~~

Một kết quả minh họa:

~~~text
count: 42
size: 180.00 KiB
in-pack: 1250
packs: 3
size-pack: 8.40 MiB
prune-packable: 12
garbage: 0
size-garbage: 0 bytes
~~~

Ý nghĩa chính:

| Trường | Ý nghĩa |
| --- | --- |
| count | Số object rời trong object database. |
| size | Tổng dung lượng object rời, ở dạng dễ đọc khi dùng -H. |
| in-pack | Số object được lưu trong packfile. |
| packs | Số packfile được nhận diện. |
| size-pack | Tổng dung lượng packfile. |
| prune-packable | Object rời đã có bản tương ứng trong pack và có thể được dọn trong quá trình bảo trì. |
| garbage | Số file không phải object hợp lệ trong object database. |
| size-garbage | Tổng dung lượng các file rác được phát hiện. |

Các số liệu thay đổi theo repository và hoạt động gần đây. Có nhiều object rời không nhất thiết là lỗi; Git có thể giữ chúng cho tới khi hoạt động bảo trì phù hợp diễn ra.

Để xem các pack đang tồn tại:

~~~bash
git rev-parse --git-path objects/pack
~~~

Sau đó liệt kê các file trong thư mục được trả về bằng công cụ hệ thống tệp. Đừng giả định đường dẫn luôn là .git/objects/pack, vì cấu trúc Git directory có thể khác trong linked worktree hoặc repository được cấu hình đặc biệt.

## 11. Kiểm tra nội dung pack bằng git verify-pack

git verify-pack kiểm tra tính nhất quán của pack index và packfile tương ứng, đồng thời có thể hiển thị thông tin từng object:

~~~bash
git verify-pack -v .git/objects/pack/pack-<hash>.idx
~~~

Đường dẫn trên là ví dụ; thay <hash> bằng basename pack thực tế. Trên Windows hoặc linked worktree, dùng đường dẫn được xác định từ git rev-parse --git-path objects/pack.

Output thường có các cột:

| Trường | Ý nghĩa |
| --- | --- |
| OID | Object ID sau khi tái tạo object. |
| Type | Loại object như commit, tree, blob hoặc tag. |
| Size | Kích thước object sau khi giải nén. |
| Packed size | Kích thước dữ liệu entry được lưu trong pack. |
| Offset | Vị trí entry trong file pack. |
| Depth | Độ sâu delta chain, nếu object được lưu bằng delta. |
| Base OID | OID của object nền trong trường hợp output có trường này. |

Object không được delta thường không có thông tin depth/base. Object delta có thể cho thấy packed size nhỏ hơn nhiều so với kích thước object sau khi giải nén.

Có thể dùng kết quả để tìm object lớn hoặc delta chain sâu. Tuy nhiên, không nên chỉ nhìn packed size rồi kết luận object đó không quan trọng; mọi entry đều có thể được tham chiếu bởi commit, tree, tag hoặc object khác.

## 12. Kiểm tra tính toàn vẹn bằng git fsck

git fsck kiểm tra tính toàn vẹn của object database và quan hệ tham chiếu giữa các object:

~~~bash
git fsck --full
~~~

Lệnh có thể phát hiện object bị thiếu, object hỏng hoặc object không thể truy cập từ các ref hiện tại. Tùy trạng thái repository, output cũng có thể liệt kê dangling hoặc unreachable object.

Dangling object không nhất thiết là lỗi. Ví dụ, sau khi reset một branch hoặc xóa ref, commit cũ có thể không còn được branch/tag nào tham chiếu nhưng vẫn còn trong object database một thời gian. Git có thể giữ object đó để hỗ trợ khôi phục trước khi garbage collection đủ điều kiện dọn.

Nếu fsck báo missing hoặc corrupt object, hãy lưu nguyên output và xác định object bị ảnh hưởng. Đừng chạy các lệnh dọn dữ liệu hoặc xóa pack thủ công trước khi hiểu phạm vi sự cố. Với repository quan trọng, hãy tạo bản sao an toàn trước khi thử sửa chữa.

## 13. Repack và garbage collection

Khi có nhiều object rời hoặc nhiều pack nhỏ, Git có thể gom và sắp xếp lại object database. Hai lệnh cần biết:

~~~bash
git repack -ad
git gc
~~~

git repack tạo pack mới theo tập object được chọn và có thể loại các pack dư thừa khi dùng tùy chọn phù hợp. Ví dụ -a yêu cầu đóng gói object reachable trong repository; -d yêu cầu xóa pack dư thừa sau khi tạo pack mới.

git gc chạy các công việc bảo trì như repack và xử lý object không còn cần thiết theo chính sách hết hạn. Git có thể tự chạy bảo trì tự động trong một số thao tác nếu repository đạt ngưỡng cần thiết.

Trước khi chạy bảo trì thủ công trên repository đang được nhiều tiến trình sử dụng, hãy đảm bảo không có thao tác Git khác đang ghi vào object database. Không xóa file .pack hoặc .idx bằng tay để giải phóng dung lượng; thao tác đó có thể làm mất object và phá vỡ khả năng tra cứu pack.

Việc repack thay đổi cách object được lưu trên đĩa, không thay đổi OID của object, nội dung commit hoặc branch đang trỏ tới đâu. Nếu object được chuyển từ loose sang packed, lệnh cat-file vẫn đọc được bằng cùng OID.

### Tại sao không phải object rời nào cũng được đóng gói ngay?

Git có thể giữ object rời mới tạo trong một khoảng thời gian hoặc cho tới khi hoạt động bảo trì diễn ra. Điều này giúp giảm chi phí repack liên tục và tránh xóa object có thể vừa trở nên unreachable nhưng vẫn cần cho việc khôi phục. Ngưỡng và thời gian hết hạn phụ thuộc cấu hình cùng phiên bản Git.

## 14. Delta compression là tối ưu vật lý, không phải lịch sử commit

Một nhầm lẫn thường gặp là cho rằng Git lưu commit dưới dạng patch nối tiếp commit trước. Thực tế, commit tham chiếu một tree mô tả snapshot. Các tree tham chiếu blob và tree con. Packfile có thể chọn lưu một blob bằng delta để giảm dung lượng, nhưng cách lưu đó không làm thay đổi mô hình snapshot của Git.

Ví dụ, hai commit có thể cùng tham chiếu nhiều blob giống nhau. Nếu một file thay đổi ít, pack có thể lưu blob mới dưới dạng delta so với blob cũ. Nhưng khi checkout commit mới, Git tái tạo blob hoàn chỉnh rồi ghi nội dung vào working tree.

Điều này cũng giải thích vì sao:

- Một object có thể tồn tại dưới dạng loose hoặc packed mà OID không đổi.
- Một object có thể được biểu diễn bằng delta nhưng cat-file vẫn trả nội dung đầy đủ.
- Repack có thể thay đổi kích thước repository mà không tạo commit mới.
- Git diff không phải là bản sao trực tiếp của delta instruction bên trong packfile.

## 15. Quy trình chẩn đoán khi object database lớn hoặc bất thường

Khi thư mục .git/objects chiếm nhiều dung lượng hoặc Git báo lỗi object, hãy kiểm tra theo thứ tự:

~~~bash
# 1. Xác định object database và pack directory
git rev-parse --git-path objects
git rev-parse --git-path objects/pack

# 2. Đếm loose objects và packfiles
git count-objects -vH

# 3. Kiểm tra tính toàn vẹn
git fsck --full

# 4. Kiểm tra một pack cụ thể nếu cần
git verify-pack -v .git/objects/pack/pack-<hash>.idx

# 5. Chỉ chạy bảo trì sau khi hiểu trạng thái
git gc
~~~

Nếu dung lượng tăng do nhiều blob lớn hoặc lịch sử chứa nhiều phiên bản tệp nhị phân, delta compression có thể không giảm được nhiều vì các file đó ít giống nhau. Khi đó, cần xem xét chính sách quản lý file lớn, Git LFS hoặc cách lưu artifact phù hợp thay vì liên tục repack.

Nếu packfile bị thiếu hoặc hỏng, không tự tạo file .idx bằng cách đổi tên hoặc copy từ pack khác. Cần khôi phục object từ remote, bản clone khác hoặc bản sao lưu đáng tin cậy, sau đó chạy kiểm tra toàn vẹn.

## 16. Những lỗi thường gặp

### Mở file loose object nhưng không đọc được

Đây là dữ liệu nén zlib và có header nhị phân. Dùng git cat-file -t, -s hoặc -p để Git giải mã và hiển thị object.

### Xóa file .idx để giảm dung lượng

Không nên. Pack index là bảng tra cứu cho packfile. Xóa nó có thể khiến Git không thể truy cập pack theo cách bình thường. Dùng git gc hoặc git repack để bảo trì.

### Nhầm pack index với staging index

.git/index lưu nội dung đã stage; file pack-<hash>.idx nằm cạnh packfile và ánh xạ OID tới offset. Hai file không liên quan về chức năng.

### Nghĩ delta compression thay đổi OID

Không đúng. OID được tính từ nội dung object chuẩn sau khi giải nén, không phải từ cách object được nén hoặc delta-encode trong pack.

### Cho rằng dangling object luôn là lỗi

Không đúng. Object có thể trở thành unreachable sau khi ref bị di chuyển hoặc xóa nhưng vẫn còn được giữ để khôi phục. Đọc kết quả fsck và hiểu ref trước khi dọn.

### Tự xóa pack để giải phóng dung lượng

Rất rủi ro. Một pack có thể chứa object được nhiều commit và ref cần dùng. Hãy dùng công cụ bảo trì Git, không xóa riêng .pack hoặc .idx.

## 17. Ghi nhớ

- Git lưu blob, tree, commit và annotated tag dưới dạng object bất biến, được nhận diện bằng OID.
- Loose object thường là nội dung chuẩn được nén zlib và đặt trong thư mục theo hai ký tự đầu của OID.
- Packfile gom nhiều object vào một file và có thể lưu một số object bằng delta.
- Delta compression tái tạo object từ base bằng chỉ dẫn copy/insert; nó tối ưu lưu trữ, không thay đổi lịch sử logic hoặc OID.
- OFS_DELTA tham chiếu base bằng offset trong cùng pack; REF_DELTA tham chiếu base bằng OID.
- Pack index .idx ánh xạ OID tới offset trong .pack; nó khác staging index .git/index.
- git count-objects -vH, git verify-pack -v và git fsck --full giúp quan sát và kiểm tra object database.
- git repack và git gc là công cụ bảo trì; không tự xóa pack hoặc index bằng tay.
- Repack có thể thay đổi cách lưu object trên đĩa mà không đổi OID, commit hay nội dung working tree.

Loose object giúp Git ghi dữ liệu đơn giản theo từng object; packfile gom và nén dữ liệu để repository lưu trữ hiệu quả hơn. Delta compression giảm phần nội dung lặp lại, còn pack index giúp tìm object nhanh. Khi hiểu ba lớp này, bạn có thể đọc cấu trúc object database, chẩn đoán dung lượng và bảo trì repository mà không nhầm dữ liệu lưu trữ với lịch sử hoặc staging area.
