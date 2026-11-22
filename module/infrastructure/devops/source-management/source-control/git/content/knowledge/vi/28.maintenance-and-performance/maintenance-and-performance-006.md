# Commit-graph, bitmap và multi-pack-index

Khi repository có lịch sử lâu năm, hàng trăm nghìn commit hoặc rất nhiều packfile, một số thao tác Git có thể mất thời gian vì phải duyệt đồ thị commit hoặc tìm object trên nhiều pack. Git cung cấp các cấu trúc metadata để tăng tốc những công việc này mà không thay đổi nội dung commit hay mã nguồn.

Ba cấu trúc thường gặp là **commit-graph**, **reachability bitmap** và **multi-pack-index (MIDX)**. Chúng giải quyết ba nút thắt khác nhau:

- Commit-graph giúp Git duyệt quan hệ giữa các commit nhanh hơn.
- Bitmap giúp xác định tập object có thể truy cập từ các commit nhanh hơn, đặc biệt khi tạo pack cho fetch, clone hoặc push.
- Multi-pack-index giúp tìm object nhanh khi repository có nhiều packfile.

Các cấu trúc này có thể cùng tồn tại trong một repository. Hiểu rõ vai trò của từng cấu trúc giúp chọn đúng cách bảo trì, kiểm tra hiệu quả và tránh chạy các lệnh repack hoặc garbage collection không cần thiết.

## 1. Vì sao repository lớn cần metadata tăng tốc?

Git lưu nội dung dưới dạng object: commit, tree, blob và tag. Khi repository phát triển, số lượng object và commit tăng lên. Git phải thực hiện nhiều công việc khi xử lý lịch sử và trao đổi dữ liệu:

- Lần theo parent commit để tìm tổ tiên chung.
- Tính toán những commit nào nằm giữa hai refs.
- Xác định object nào có thể truy cập từ branch hoặc tag.
- Tìm object theo OID trong nhiều packfile.
- Tạo pack chỉ chứa object mà phía nhận chưa có.

Với repository nhỏ, chi phí này thường không đáng kể. Với monorepo hoặc repository có lịch sử dài, các lần duyệt lặp lại có thể làm fetch, clone, push, log hoặc các thao tác bảo trì chậm hơn.

Git dùng metadata phụ trợ để tránh phải tính lại mọi thứ từ đầu. Metadata này được xây dựng từ object và refs hiện có, nên có thể được tái tạo nếu bị thiếu hoặc hỏng. Nó không thay thế commit, tree hay blob gốc.

## 2. Ba cấu trúc giải quyết ba bài toán khác nhau

| Cấu trúc | Bài toán chính | Thông tin được lập chỉ mục |
|---|---|---|
| Commit-graph | Duyệt lịch sử commit và quan hệ ancestry | Commit OID, tree, parent, generation number và dữ liệu tăng tốc truy vấn đường dẫn |
| Reachability bitmap | Tính tập object reachable từ commit | Bitset biểu diễn các object có thể truy cập từ một số commit |
| Multi-pack-index | Tìm object khi có nhiều packfile | Ánh xạ object OID tới pack và vị trí trong pack |

Có thể nhớ theo câu hỏi:

- **Commit-graph:** commit nào là cha, tổ tiên của commit nào?
- **Bitmap:** từ commit này có thể truy cập những object nào?
- **MIDX:** object này đang nằm trong packfile nào?

Một repository có thể dùng cả ba. MIDX không thay thế bitmap; MIDX giúp tìm object trên nhiều pack, còn bitmap giúp tính tập object reachable. Commit-graph lại tập trung vào đồ thị commit, không lập chỉ mục vị trí của mọi blob trong pack.

## 3. Commit-graph lưu những gì?

Commit-graph là một file metadata chứa thông tin về các commit trong repository. Git có thể lưu OID của commit, OID của tree, parent commit, generation number và một số dữ liệu phục vụ tăng tốc duyệt lịch sử.

Một số thông tin quan trọng:

- **Commit OID:** định danh commit.
- **Tree OID:** tree gốc của snapshot trong commit.
- **Parent list:** quan hệ cha/con, bao gồm nhiều parent của merge commit.
- **Generation number:** thông tin thứ tự thế hệ giúp cắt ngắn việc duyệt ancestry.
- **Commit date:** thời gian commit được lưu trong metadata.
- **Changed-path Bloom filter:** bộ lọc xác suất cho biết một đường dẫn có thể đã thay đổi trong commit hay không, nếu được ghi.

Commit-graph không lưu nội dung file. Nó cũng không phải nguồn sự thật thay thế commit object. Git vẫn đọc commit object khi cần; commit-graph cung cấp thông tin đã chuẩn bị để giảm chi phí duyệt.

Có thể hình dung:

~~~text
Commit objects
  A <- B <- C <- E
        \       /
         D ----
           merge

Commit-graph
  OID A: parent []
  OID B: parent [A]
  OID C: parent [B]
  OID D: parent [B]
  OID E: parent [C, D]
  generation / tree / optional Bloom filters
~~~

Khi cần tìm tổ tiên chung hoặc duyệt commit theo thứ tự, Git có thể dùng graph metadata thay vì liên tục mở và phân tích từng commit object.

## 4. Generation number giúp duyệt ancestry nhanh hơn

Generation number biểu diễn một mức thứ tự trong đồ thị commit. Nó giúp Git nhận ra rằng một commit không thể là tổ tiên của commit khác nếu thế hệ của nó không thỏa điều kiện cần thiết.

Trong đồ thị tuyến tính, thế hệ tăng dần theo từng commit. Với merge commit, thế hệ được tính dựa trên các parent để vẫn phản ánh vị trí của commit trong DAG (directed acyclic graph).

Generation number không phải số thứ tự commit toàn repository và không nên dùng như timestamp. Nó là metadata phục vụ thuật toán duyệt đồ thị.

Git có thể dùng generation number trong các phép toán như:

- Tìm merge base.
- So sánh ancestry giữa hai commit.
- Duyệt commit trong phạm vi revision.
- Các truy vấn lịch sử cần xác định commit nào có thể là tổ tiên của commit khác.

Nếu commit-graph không có hoặc không hợp lệ, Git vẫn có thể tính toán từ commit object, nhưng có thể phải đọc nhiều dữ liệu hơn.

## 5. Changed-path Bloom filter tăng tốc log theo đường dẫn

Khi chạy:

~~~bash
git log -- src/payment
~~~

Git cần xác định commit nào đã thay đổi đường dẫn <code>src/payment</code>. Trong repository lớn, việc kiểm tra cây file của nhiều commit có thể tốn thời gian.

Commit-graph có thể lưu **Bloom filter** cho đường dẫn thay đổi của mỗi commit. Bloom filter là cấu trúc xác suất:

- Nếu filter cho biết đường dẫn chắc chắn không xuất hiện, Git có thể bỏ qua một số kiểm tra đắt hơn.
- Nếu filter cho biết có khả năng xuất hiện, Git phải kiểm tra chính xác.
- Có thể có false positive, nghĩa là filter báo có khả năng nhưng thực tế đường dẫn không thay đổi.
- Thiết kế này không được phép tạo false negative làm bỏ sót thay đổi thật.

Để tạo commit-graph có changed-path Bloom filters:

~~~bash
git commit-graph write --reachable --changed-paths
~~~

Tùy chọn <code>--changed-paths</code> yêu cầu Git ghi Bloom filter cho truy vấn đường dẫn. Tính năng này có ích khi thường xuyên chạy <code>git log -- &lt;path&gt;</code>, <code>git log --follow</code> hoặc công cụ phân tích lịch sử theo file.

Bloom filter không làm cho mọi lệnh log nhanh hơn. Lợi ích phụ thuộc kiểu truy vấn, số commit, cấu trúc cây và phiên bản Git.

## 6. Tạo và kiểm tra commit-graph

Tạo commit-graph từ các commit reachable qua refs:

~~~bash
git commit-graph write --reachable
~~~

Tạo thêm changed-path Bloom filters:

~~~bash
git commit-graph write --reachable --changed-paths
~~~

Kiểm tra tính nhất quán:

~~~bash
git commit-graph verify
~~~

Có thể bật hiển thị tiến trình cho repository lớn:

~~~bash
git commit-graph verify --progress
~~~

<code>--reachable</code> yêu cầu Git xây dựng graph cho các commit có thể truy cập từ refs mà repository đang biết. Điều này thường phù hợp với repository làm việc thông thường.

Nếu chỉ muốn tạo graph cho tập commit được cung cấp qua stdin, có thể dùng <code>--stdin-commits</code>; cần đảm bảo tập đầu vào và phạm vi refs đúng với mục tiêu bảo trì.

Commit-graph thường nằm trong metadata của Git, không xuất hiện như file trong working tree và không được commit vào source repository.

## 7. Split commit-graph cho repository cập nhật liên tục

Nếu mỗi lần fetch đều viết lại một commit-graph lớn, chi phí tạo graph có thể tăng theo lịch sử repository. Git hỗ trợ **split commit-graph chain** để ghi thêm lớp graph mới thay vì luôn xây dựng lại một file lớn.

Tạo hoặc cập nhật graph dạng split:

~~~bash
git commit-graph write --reachable --split
~~~

Có thể kết hợp Bloom filters:

~~~bash
git commit-graph write --reachable --split --changed-paths
~~~

Các lớp graph được liên kết thành chain. Git đọc chúng như một cấu trúc thống nhất. Khi chain có nhiều lớp hoặc cần hợp nhất, Git có thể thực hiện compaction theo chính sách của lệnh write.

Ưu điểm:

- Giảm lượng dữ liệu phải ghi lại trong một số lần cập nhật.
- Phù hợp repository thường xuyên fetch commit mới.
- Cho phép cập nhật graph theo từng đợt.

Hạn chế:

- Chain có thêm metadata và nhiều file hơn.
- Cần được bảo trì và hợp nhất khi thích hợp.
- Không phải lúc nào split cũng nhanh hơn một graph đơn; cần quan sát workload thực tế.

Không tự xóa file trong thư mục commit-graphs. Dùng <code>git commit-graph write</code> và <code>git commit-graph verify</code> để Git quản lý chain.

## 8. Tự động cập nhật commit-graph

Có thể yêu cầu Git ghi commit-graph trong quá trình fetch:

~~~bash
git config fetch.writeCommitGraph true
~~~

Hoặc chỉ định trong một lần fetch:

~~~bash
git fetch --write-commit-graph origin
~~~

Tên cấu hình và tùy chọn này giúp graph được cập nhật khi repository nhận commit mới. Nếu hệ thống đã dùng Git maintenance, có thể để tác vụ bảo trì quản lý commit-graph theo lịch.

Chạy riêng task:

~~~bash
git maintenance run --task=commit-graph
~~~

Kiểm tra cấu hình liên quan:

~~~bash
git config --show-origin --get fetch.writeCommitGraph
git config --show-origin --get core.commitGraph
~~~

Không cần ép mọi repository phải có cấu hình giống nhau. Với repository nhỏ hoặc tác vụ ngắn, chi phí graph có thể không đáng kể. Với repository lớn, commit-graph thường có lợi hơn, đặc biệt khi truy vấn lịch sử diễn ra thường xuyên.

## 9. Reachability bitmap là gì?

Reachability bitmap là cấu trúc bitset giúp Git xác định tập object có thể truy cập từ một commit. Thay vì duyệt toàn bộ đồ thị và thu thập object mỗi lần tạo pack, Git có thể kết hợp bitmap để tính tập object nhanh hơn.

Ví dụ, một commit reachable tới:

- Commit objects trong lịch sử.
- Tree objects của các snapshot.
- Blob objects của file.

Bitmap ghi nhận tập object đó theo các bit. Các bitmap của những commit khác nhau có thể được kết hợp bằng phép toán bit để tính phần object cần gửi hoặc phần object mà phía nhận còn thiếu.

Bitmap đặc biệt hữu ích khi server phục vụ nhiều clone/fetch hoặc khi phải tạo pack cho repository lớn.

### Bitmap không phải bản sao nội dung

Bitmap không lưu blob hay commit object. Nó chỉ lưu metadata về khả năng truy cập object. Nếu packfile bị thay thế, loại bỏ hoặc được tạo lại với tập object khác, bitmap tương ứng phải được cập nhật hoặc tạo lại.

Bitmap giúp tăng tốc tính toán tập object; nó không thay thế pack index và cũng không thay thế commit-graph.

## 10. Bitmap tăng tốc fetch, clone và push như thế nào?

Khi client yêu cầu clone hoặc fetch, server phải xác định object nào cần gửi. Nếu repository có nhiều commit và object, việc duyệt toàn bộ lịch sử để lập danh sách có thể tốn thời gian.

Với reachability bitmap, Git có thể:

1. Chọn bitmap tương ứng với tip commit được yêu cầu.
2. Kết hợp bitmap của các refs phía gửi và phía nhận khi phù hợp.
3. Tính phần object cần gửi bằng phép toán bit.
4. Tạo pack từ tập object đã xác định.

Bitmap giúp giảm chi phí duyệt object, nhưng không loại bỏ chi phí truyền dữ liệu mạng, nén pack hoặc ghi dữ liệu trên máy nhận.

Hiệu quả phụ thuộc vào:

- Số lượng commit và object.
- Số refs và cách chúng chia sẻ lịch sử.
- Bitmap có bao phủ commit cần thiết không.
- Loại object và cấu trúc pack.
- Phiên bản Git và cấu hình server.

## 11. Tạo bitmap cho packfile bằng git repack

Một cách phổ biến để tạo bitmap là repack các object reachable thành pack và ghi bitmap index:

~~~bash
git repack -adb
~~~

Các tùy chọn chính:

- <code>-a</code>: đóng gói các object reachable vào pack mới.
- <code>-d</code>: xóa các pack dư thừa sau khi repack.
- <code>-b</code>: ghi bitmap index nếu điều kiện hỗ trợ phù hợp.

Lệnh này có thể đọc và ghi nhiều dữ liệu, tạo pack lớn và tốn CPU/IO. Không chạy tùy tiện trên server đang chịu tải cao. Với repository lớn, chọn thời điểm bảo trì và bảo đảm đủ dung lượng tạm thời.

Để kiểm tra các tùy chọn của phiên bản đang dùng, xem <code>git repack -h</code> hoặc tài liệu cài đặt trước khi đưa lệnh vào script bảo trì.

### Bitmap đi cùng pack nào?

Bitmap truyền thống gắn với packfile cụ thể. Khi repack tạo pack mới, Git có thể tạo bitmap index tương ứng. Nếu sau đó pack bị thay thế hoặc xóa, bitmap đó cũng không còn là metadata hợp lệ cho pack cũ.

Do đó, bitmap packfile cần được tạo lại khi cấu trúc pack thay đổi đáng kể. Không sao chép riêng file <code>.bitmap</code> từ repository khác hoặc đổi tên thủ công.

## 12. Bitmap và Multi-pack-index bitmap

Trong repository có nhiều packfile, một bitmap gắn với một pack duy nhất có thể không mô tả thuận tiện toàn bộ tập object. Git hỗ trợ **MIDX bitmap** để lập reachability bitmap trên tập object được lập chỉ mục bởi multi-pack-index.

Tạo hoặc cập nhật MIDX bitmap:

~~~bash
git multi-pack-index write --bitmap
~~~

Tùy chọn <code>--bitmap</code> yêu cầu Git ghi bitmap gắn với MIDX. Khả năng này phụ thuộc phiên bản Git; kiểm tra <code>git multi-pack-index -h</code> hoặc tài liệu của phiên bản đang triển khai.

MIDX bitmap cho phép Git sử dụng bitmap trong khi vẫn giữ object phân tán trên nhiều packfile. Đây là một thành phần quan trọng của quy trình incremental repack cho repository lớn.

Không nên giả định MIDX bitmap luôn được tạo tự động chỉ vì đã có MIDX. Hãy kiểm tra lệnh, cấu hình và hành vi của phiên bản Git đang chạy.

## 13. Multi-pack-index (MIDX) là gì?

Khi repository có nhiều packfile, mỗi pack thường có file index <code>.idx</code> riêng. Git có thể phải tra cứu qua nhiều index để tìm object theo OID.

Multi-pack-index tạo một index tổng hợp cho nhiều pack. Nó ánh xạ object OID tới pack chứa object và vị trí tương ứng, giúp tra cứu nhanh hơn mà không cần gộp tất cả pack thành một pack duy nhất.

Ví dụ:

~~~text
objects/pack/
  pack-a.pack
  pack-a.idx
  pack-b.pack
  pack-b.idx
  pack-c.pack
  pack-c.idx
  multi-pack-index
~~~

MIDX giúp Git biết object nằm trong pack nào. Các pack gốc vẫn tồn tại; MIDX không tự ghép nội dung của chúng thành một pack mới.

Lợi ích rõ nhất khi repository có nhiều packfile do fetch thường xuyên, incremental repack hoặc lưu trữ object theo nhiều đợt.

## 14. Tạo và xác minh multi-pack-index

Tạo hoặc cập nhật MIDX:

~~~bash
git multi-pack-index write
~~~

Kiểm tra MIDX:

~~~bash
git multi-pack-index verify
~~~

Có thể bật tiến trình:

~~~bash
git multi-pack-index verify --progress
~~~

MIDX được lưu trong thư mục pack của object database. Git tự sử dụng khi có file MIDX hợp lệ; người dùng không cần chỉ định file này trong mỗi lệnh log, fetch hoặc checkout.

MIDX không chứa nội dung object. Nếu packfile bị hỏng hoặc bị xóa thủ công, index có thể trỏ tới dữ liệu không còn tồn tại. Dùng lệnh verify và quy trình maintenance để cập nhật, không sửa file MIDX bằng tay.

## 15. Expire và repack các packfile qua MIDX

MIDX hỗ trợ các thao tác bảo trì pack:

~~~bash
git multi-pack-index expire
git multi-pack-index repack
~~~

**Expire** xử lý các packfile không còn cần được giữ trong tập được MIDX quản lý, theo trạng thái index và quy tắc của Git.

**Repack** chọn object từ các pack phù hợp để đóng gói lại, giúp giảm sự phân mảnh và số pack nhỏ. Có thể điều chỉnh batch size trong các phiên bản hỗ trợ:

~~~bash
git multi-pack-index repack --batch-size=2g
~~~

Batch size giới hạn quy mô batch repack theo đơn vị mà Git chấp nhận. Xem <code>git multi-pack-index repack -h</code> để kiểm tra cú pháp và tùy chọn của phiên bản đang cài.

Một quy trình incremental repack có thể cập nhật MIDX, repack một phần object rồi expire pack cũ không còn cần. Không xóa pack thủ công khi chưa hiểu MIDX đang tham chiếu chúng.

## 16. So sánh pack index, MIDX và bitmap

| Thành phần | Phạm vi | Vai trò |
|---|---|---|
| Pack index <code>.idx</code> | Một packfile | Tìm OID và vị trí object trong pack đó |
| Multi-pack-index | Nhiều packfile | Tìm object trên toàn bộ tập pack được lập chỉ mục |
| Pack bitmap | Một pack được hỗ trợ | Tính object reachable từ các commit đã bitmap hóa |
| MIDX bitmap | Tập pack trong MIDX | Tính object reachable trên nhiều pack |
| Commit-graph | Đồ thị commit | Tăng tốc truy vấn ancestry và lịch sử |

Một repository có thể có nhiều <code>.idx</code>, một MIDX và bitmap. Đây không phải các định dạng thay thế lẫn nhau; chúng được Git phối hợp để tối ưu các bước khác nhau.

## 17. Incremental repack và Git maintenance

Trong repository hoạt động lâu dài, mỗi fetch có thể thêm packfile mới. Nếu để số pack tăng không kiểm soát, thao tác tìm object và quản lý pack có thể chậm hơn.

Git có task maintenance <code>incremental-repack</code> để quản lý các pack theo nhiều đợt thay vì luôn tạo một pack khổng lồ. Task này phối hợp MIDX, repack và expire theo chiến lược của Git.

Chạy task:

~~~bash
git maintenance run --task=incremental-repack
~~~

Chạy task commit-graph:

~~~bash
git maintenance run --task=commit-graph
~~~

Chạy các task maintenance mặc định:

~~~bash
git maintenance run
~~~

Có thể bật lịch bảo trì nền:

~~~bash
git maintenance start
~~~

Lịch chạy cụ thể phụ thuộc hệ điều hành, scheduler và cấu hình Git. Trước khi bật trên repository dùng chung hoặc server, hãy hiểu task nào sẽ chạy và thời điểm thực thi. Không để hai quy trình repack/gc độc lập chạy đồng thời trên cùng object database.

## 18. Cấu hình liên quan tới commit-graph, bitmap và MIDX

Một số cấu hình có thể ảnh hưởng cách Git sử dụng metadata tăng tốc:

~~~bash
git config --show-origin --get core.commitGraph
git config --show-origin --get fetch.writeCommitGraph
git config --show-origin --get pack.useBitmaps
git config --show-origin --get maintenance.incremental-repack.auto
~~~

Ý nghĩa tổng quát:

| Cấu hình | Mục đích |
|---|---|
| <code>core.commitGraph</code> | Điều khiển việc đọc commit-graph |
| <code>fetch.writeCommitGraph</code> | Cho phép cập nhật commit-graph khi fetch |
| <code>pack.useBitmaps</code> | Điều khiển việc sử dụng bitmap trong các thao tác đóng gói phù hợp |
| <code>maintenance.incremental-repack.auto</code> | Điều khiển ngưỡng/tự động chạy incremental repack trong maintenance |

Không phải mọi phiên bản Git đều có cùng cấu hình hoặc mặc định. Nếu <code>git config --get</code> không trả về giá trị, cấu hình có thể chưa được đặt tường minh; Git vẫn có thể sử dụng hành vi mặc định.

Kiểm tra nguồn cấu hình để biết giá trị đến từ system, global, local hay command scope. Tránh sao chép cấu hình của một server lớn sang máy phát triển nhỏ mà không đo hiệu quả.

## 19. Đo hiệu quả trước và sau bảo trì

Không nên đánh giá hiệu quả chỉ bằng việc lệnh đã chạy thành công. Hãy đo các tác vụ thực tế trước và sau khi tạo metadata.

Một số chỉ số:

- Thời gian chạy <code>git log -- &lt;path&gt;</code>.
- Thời gian chạy <code>git merge-base</code> trên hai branch dài.
- Thời gian fetch/clone từ server thử nghiệm.
- Thời gian push khi phải tạo pack.
- Số lượng packfile.
- Dung lượng pack và object database.
- Thời gian và tài nguyên CPU/IO của maintenance.

Kiểm tra tổng quan object và pack:

~~~bash
git count-objects -vH
~~~

Lệnh hiển thị số object loose, dung lượng loose, số pack, dung lượng pack và một số thông tin liên quan. Dùng cùng một repository và cùng trạng thái refs khi so sánh trước/sau.

Để đo một lệnh cụ thể trên môi trường Unix-like, có thể dùng <code>time</code>:

~~~bash
time git log --oneline -- src/payment
time git merge-base main feature/payment
~~~

Trên Windows, dùng công cụ đo thời gian tương ứng trong PowerShell hoặc CI. Chạy lặp lại trong điều kiện tương đương để tránh kết luận từ một lần đo có cache nóng/lạnh khác nhau.

## 20. Chẩn đoán khi metadata thiếu hoặc hỏng

Nếu thao tác Git chậm bất thường hoặc verify báo lỗi, xác định cấu trúc nào gặp vấn đề.

### Commit-graph

Kiểm tra:

~~~bash
git commit-graph verify
~~~

Nếu graph thiếu, có thể tạo lại:

~~~bash
git commit-graph write --reachable --split --changed-paths
~~~

Nếu graph hỏng, giữ lại log lỗi và xem xét rebuild bằng lệnh Git. Không xóa thủ công các file graph khi chưa hiểu chain split hiện tại.

### Multi-pack-index

Kiểm tra:

~~~bash
git multi-pack-index verify
~~~

Nếu MIDX thiếu hoặc cần cập nhật:

~~~bash
git multi-pack-index write
~~~

Sau khi pack được repack hoặc expire, cập nhật MIDX theo quy trình bảo trì.

### Bitmap

Bitmap thường được xác minh gián tiếp thông qua thao tác repack/pack và công cụ kiểm tra phù hợp của phiên bản Git. Nếu nghi ngờ bitmap không còn tương thích với pack, tạo lại bằng quy trình repack có bitmap hoặc MIDX bitmap.

Không xóa riêng bitmap đang được Git sử dụng trong lúc repository đang có thao tác đọc/ghi đồng thời.

## 21. Những điều không nên làm

- Không sửa commit-graph, bitmap hoặc MIDX bằng hex editor.
- Không sao chép file metadata từ repository khác.
- Không xóa packfile chỉ vì thấy có nhiều file <code>.pack</code>.
- Không chạy repack, gc và maintenance đồng thời trên cùng object database.
- Không chạy <code>git repack -adb</code> trên server đang tải cao mà chưa đo chi phí.
- Không giả định MIDX sẽ giảm tổng dung lượng object; nó chủ yếu tăng tốc tra cứu trên nhiều pack.
- Không giả định bitmap giúp mọi lệnh Git nhanh hơn; lợi ích tập trung vào duyệt object và tạo pack.
- Không coi commit-graph là nguồn dữ liệu commit chính; commit object vẫn là nguồn sự thật.

Các file metadata có thể được tạo lại, nhưng packfile chứa object gốc không phải lúc nào cũng có thể khôi phục nếu bị xóa nhầm. Hãy phân biệt file index phụ trợ với pack chứa dữ liệu.

## 22. Quy trình mẫu cho repository lớn

Giả sử repository có lịch sử commit dài và nhiều packfile do fetch liên tục.

**Bước 1 — Ghi nhận trạng thái ban đầu**

~~~bash
git count-objects -vH
git show-ref
git commit-graph verify
git multi-pack-index verify
~~~

Nếu commit-graph hoặc MIDX chưa tồn tại, verify có thể báo chưa có cấu trúc để kiểm tra; ghi nhận trạng thái thay vì coi đó là lỗi dữ liệu commit.

**Bước 2 — Cập nhật commit-graph**

~~~bash
git commit-graph write --reachable --split --changed-paths
git commit-graph verify
~~~

**Bước 3 — Cập nhật MIDX**

~~~bash
git multi-pack-index write
git multi-pack-index verify
~~~

**Bước 4 — Tạo bitmap khi workload cần**

Nếu server thường xuyên tạo pack cho clone/fetch:

~~~bash
git multi-pack-index write --bitmap
~~~

Nếu dùng bitmap gắn với pack đơn, cân nhắc repack có bitmap trong cửa sổ bảo trì:

~~~bash
git repack -adb
~~~

Không nhất thiết chạy cả hai cách. Chọn pack bitmap hay MIDX bitmap theo cấu trúc pack, phiên bản Git và workflow server.

**Bước 5 — Bảo trì incremental repack nếu phù hợp**

~~~bash
git maintenance run --task=incremental-repack
~~~

**Bước 6 — Đo lại**

~~~bash
git count-objects -vH
git commit-graph verify
git multi-pack-index verify
~~~

So sánh thời gian tác vụ và dung lượng với số liệu ban đầu. Nếu không có cải thiện, xem lại nút thắt thực tế thay vì tiếp tục chạy repack.

## 23. Checklist vận hành

- [ ] Đã xác định thao tác chậm là duyệt commit, tính reachable object hay tìm object trong nhiều pack.
- [ ] Đã kiểm tra phiên bản Git hỗ trợ tùy chọn cần dùng.
- [ ] Đã tạo/verify commit-graph nếu repository có lịch sử lớn.
- [ ] Đã cân nhắc changed-path Bloom filters cho truy vấn lịch sử theo file.
- [ ] Đã kiểm tra số packfile và tình trạng MIDX.
- [ ] Đã cân nhắc bitmap khi server thường xuyên tạo pack.
- [ ] Đã chọn pack bitmap hay MIDX bitmap theo cấu trúc repository.
- [ ] Đã lên lịch repack/maintenance vào thời điểm phù hợp.
- [ ] Không có tiến trình gc/repack khác chạy đồng thời.
- [ ] Đã đo thời gian và dung lượng trước/sau.
- [ ] Đã lưu log verify và kết quả vận hành.
- [ ] Đã có backup phù hợp trước các thao tác repack lớn trên server quan trọng.

## 24. Những điểm cần ghi nhớ

- Commit-graph tăng tốc duyệt commit và quan hệ ancestry; changed-path Bloom filters hỗ trợ truy vấn lịch sử theo đường dẫn.
- Reachability bitmap tăng tốc tính tập object cần gửi hoặc xử lý khi tạo pack.
- Multi-pack-index ánh xạ object OID tới pack và vị trí, hữu ích khi repository có nhiều packfile.
- Pack bitmap gắn với pack; MIDX bitmap có thể mô tả reachability trên nhiều pack.
- Dùng <code>git commit-graph write</code> và <code>git commit-graph verify</code> để tạo/kiểm tra graph.
- Dùng <code>git multi-pack-index write</code> và <code>git multi-pack-index verify</code> để tạo/kiểm tra MIDX.
- <code>git repack -adb</code> có thể tạo pack và bitmap nhưng có chi phí IO/CPU đáng kể.
- <code>git maintenance run --task=incremental-repack</code> và <code>--task=commit-graph</code> giúp tự động hóa bảo trì theo task.
- Các metadata này không thay thế object gốc và không làm thay đổi commit hash.
- Đo workload trước/sau và tránh chạy nhiều thao tác repack/gc đồng thời.

Commit-graph, bitmap và multi-pack-index là ba lớp metadata bổ trợ cho nhau. Khi xác định đúng nút thắt, tạo và kiểm tra đúng cấu trúc, rồi đo lại trên workload thật, repository lớn có thể duyệt lịch sử và trao đổi object hiệu quả hơn mà vẫn giữ nguyên dữ liệu Git.

