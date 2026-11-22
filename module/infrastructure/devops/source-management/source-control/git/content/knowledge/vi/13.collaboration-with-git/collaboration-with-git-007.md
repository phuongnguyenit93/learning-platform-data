# Thỏa thuận lựa chọn merge, squash hoặc rebase khi tích hợp

Khi một nhánh công việc đã sẵn sàng đi vào nhánh đích, nhóm cần thống nhất cách đưa thay đổi vào lịch sử Git. **Merge**, **squash** và **rebase** đều có thể đưa nội dung từ nhánh công việc vào nhánh đích, nhưng tạo ra lịch sử khác nhau. Lựa chọn không chỉ ảnh hưởng đến hình dạng đồ thị commit mà còn ảnh hưởng đến khả năng truy vết, review, revert và cách tiếp tục làm việc trên nhánh sau khi tích hợp.

Trong chương **Cộng tác bằng Git** của module **SOURCE_CONTROL_GIT**, bài học này tập trung vào việc xây dựng thỏa thuận tích hợp mà cả nhóm có thể áp dụng nhất quán. Ta sẽ phân biệt ba chiến lược, xác định tình huống phù hợp, thống nhất quy tắc với pull request và xử lý các ngoại lệ như nhánh đã chia sẻ, hotfix hoặc một thay đổi gồm nhiều phần cần truy vết riêng.

Sau bài học, bạn có thể:

- Giải thích lịch sử được tạo ra bởi merge commit, squash merge và rebase.
- Chọn chiến lược dựa trên mục tiêu review, truy vết, bảo toàn lịch sử và vận hành.
- Phân biệt rebase để cập nhật nhánh công việc với rebase như cách tích hợp cuối cùng.
- Đề xuất quy ước cho nhánh tính năng, pull request, nhánh phát hành và nhánh đã chia sẻ.
- Kiểm tra kết quả tích hợp và chọn cách revert phù hợp.

## 1. Vì sao nhóm cần một thỏa thuận?

Giả sử nhánh đích là main và một nhóm phát triển tính năng đăng nhập trên nhánh feature/login. Trong quá trình làm việc, nhánh tính năng có thể có nhiều commit:

- Tạo màn hình đăng nhập.
- Thêm kiểm tra dữ liệu đầu vào.
- Sửa lỗi sau review.
- Cập nhật test.
- Hoàn thiện tài liệu.

Khi tích hợp, nhóm có thể giữ tất cả commit đó và ghi nhận điểm hợp nhất, gom thay đổi thành một commit duy nhất hoặc phát lại từng commit trên nền mới của nhánh đích. Cả ba cách có thể tạo ra cùng nội dung cuối trong working tree, nhưng lịch sử lưu lại khác nhau.

Nếu mỗi thành viên tự chọn một cách, lịch sử của repository sẽ khó đọc và khó dự đoán. Một pull request có thể tạo merge commit, pull request khác chỉ có một commit squash, trong khi người khác lại rebase nhánh đã được đồng đội sử dụng. Khi cần truy tìm lỗi hoặc revert, nhóm phải hiểu nhiều kiểu lịch sử và có thể mất thời gian xác định thay đổi đã được đưa vào bằng cách nào.

Thỏa thuận chung giúp trả lời trước các câu hỏi:

- Nhóm muốn lịch sử thể hiện rõ nhánh công việc hay muốn mỗi pull request trở thành một commit?
- Các commit nhỏ trong quá trình phát triển có cần được giữ lại để truy vết không?
- Thành viên có được viết lại lịch sử của nhánh đã push không?
- Nhánh tính năng có được tiếp tục sử dụng sau khi đã tích hợp không?
- Khi nào một thay đổi cần giữ nguyên từng commit, chẳng hạn sửa lỗi phát hành hoặc thay đổi có nhiều bước độc lập?
- Ai chịu trách nhiệm giải quyết xung đột và xác nhận CI trước khi tích hợp?

## 2. Merge: giữ các commit và ghi nhận điểm hợp nhất

Merge kết hợp lịch sử của nhánh công việc với nhánh đích. Khi hai nhánh đã phân kỳ, Git tạo một merge commit có hai parent. Các commit gốc của cả hai nhánh vẫn giữ nguyên mã định danh và quan hệ tổ tiên.

Giả sử hai nhánh cùng bắt đầu từ B:

~~~text
Trước khi merge:
      C1---C2  (feature/login)
     /
A---B
     \
      D1---D2  (main)
~~~

Sau khi merge:

~~~text
      C1---C2
     /       \
A---B         M  (main)
     \       /
      D1---D2
~~~

Commit M ghi nhận thời điểm hai dòng lịch sử được kết hợp. Người đọc có thể xem các commit riêng của nhánh tính năng, lần theo thứ tự phát triển và xác định nhánh nào đã được tích hợp.

Có thể thực hiện merge từ nhánh đích:

~~~bash
git switch main
git merge --no-ff feature/login
~~~

Tùy chọn **--no-ff** yêu cầu tạo merge commit ngay cả khi Git có thể fast-forward. Nếu bỏ tùy chọn này, Git có thể chỉ di chuyển con trỏ nhánh khi lịch sử cho phép; khi hai nhánh phân kỳ, Git vẫn cần merge commit để nối chúng.

**Khi nào nên thỏa thuận dùng merge?**

- Nhóm muốn lưu lại cấu trúc nhánh và thời điểm tích hợp.
- Nhánh công việc có nhiều commit có ý nghĩa cần giữ riêng.
- Các commit đã được chia sẻ và cần bảo toàn mã định danh, quan hệ tổ tiên.
- Cần xem lại quá trình phát triển hoặc đối chiếu từng commit trong pull request.
- Repository có quy trình phát hành coi merge commit là dấu mốc tích hợp.

Merge giúp bảo toàn lịch sử nhưng đồ thị commit có thể nhiều nhánh hơn. Nếu nhóm dùng merge commit cho mọi thay đổi nhỏ, log có thể có nhiều commit chỉ phục vụ đồng bộ. Hãy xác định merge commit có thực sự cung cấp thông tin mà nhóm muốn lưu lại hay không.

## 3. Squash: gom thay đổi thành một commit

Squash lấy tổng thay đổi của nhánh công việc so với điểm chung với nhánh đích và ghi chúng thành một commit duy nhất trên nhánh đích. Các commit riêng của nhánh công việc không trở thành tổ tiên của commit squash.

Trước khi squash:

~~~text
      C1---C2---C3  (feature/login)
     /
A---B---D1  (main)
~~~

Sau khi squash và tạo commit S:

~~~text
A---B---D1---S  (main)
     \
      C1---C2---C3  (feature/login, lịch sử cũ)
~~~

Commit S chứa kết quả tổng hợp của thay đổi từ C1 đến C3, nhưng không có parent trỏ về C3. Vì vậy, Git không coi các commit C1, C2, C3 là đã được tích hợp theo quan hệ tổ tiên, dù nội dung của chúng đã được đưa vào main thông qua S.

Có thể tạo một lần squash bằng Git:

~~~bash
git switch main
git merge --squash feature/login
git diff --cached
git commit -m "feat(auth): add login flow"
~~~

Lệnh **git merge --squash** chuẩn bị working tree và index như thể đã merge thay đổi, nhưng không tạo merge commit và không tự tạo commit thường. Sau khi kiểm tra phần đã stage, người phát triển tạo một commit mới bằng **git commit**. Nếu có xung đột, giải quyết file, stage kết quả rồi tạo commit squash.

Nhiều nền tảng quản lý pull request cũng cung cấp nút hoặc tùy chọn **Squash and merge**. Nền tảng sẽ tạo commit tổng hợp trên nhánh đích theo quy trình của pull request. Cách thao tác giao diện có thể khác lệnh Git cục bộ, nhưng ý nghĩa lịch sử cơ bản giống nhau: thay đổi được ghi thành một commit mới, không giữ các commit nhánh tính năng làm tổ tiên của nhánh đích.

**Khi nào nên thỏa thuận dùng squash?**

- Mỗi pull request đại diện cho một đơn vị thay đổi có mục tiêu rõ ràng.
- Các commit trên nhánh tính năng chủ yếu là commit nháp, sửa theo review hoặc checkpoint.
- Nhóm muốn log của nhánh chính ngắn gọn, mỗi commit tương ứng với một pull request hoặc một thay đổi logic.
- Nhóm muốn revert một tính năng đã tích hợp bằng cách xác định một commit tổng hợp.

Squash giúp lịch sử nhánh đích gọn, nhưng làm mất cấu trúc commit riêng của nhánh tính năng trong lịch sử tổ tiên của nhánh đích. Nếu các commit nhỏ mang thông tin quan trọng như từng bước migration, thay đổi độc lập hoặc dấu mốc điều tra lỗi, gom chúng lại có thể làm giảm khả năng truy vết.

Sau khi squash, nên đóng hoặc xóa nhánh tính năng đã tích hợp. Nếu tiếp tục phát triển trên chính nhánh đó, các commit cũ vẫn không phải tổ tiên của commit squash trên main. Những lần tích hợp sau có thể khiến nhóm phải xem lại các thay đổi cũ hoặc gặp phần diff khó hiểu. Nếu công việc tiếp tục sau khi pull request đã squash, hãy tạo nhánh mới từ nhánh đích đã cập nhật.

## 4. Rebase: phát lại commit trên nền mới

Rebase lấy các commit của nhánh công việc chưa có trong nhánh đích và phát lại chúng lần lượt trên commit mới nhất của nhánh đích. Git tạo các commit mới vì parent của chúng thay đổi; do đó mã định danh commit cũng thay đổi.

Trước khi rebase:

~~~text
      C1---C2  (feature/login)
     /
A---B
     \
      D1---D2  (main)
~~~

Sau khi rebase:

~~~text
A---B---D1---D2---C1'---C2'  (feature/login)
             (main)
~~~

C1' và C2' là commit mới được phát lại từ thay đổi của C1 và C2. Lịch sử sau rebase có dạng tuyến tính và không có merge commit chỉ để cập nhật nhánh tính năng.

Quy trình cập nhật nhánh tính năng trên nền main mới nhất:

~~~bash
git fetch origin
git switch feature/login
git rebase origin/main
~~~

Sau khi rebase thành công, có thể tích hợp vào main bằng fast-forward nếu main vẫn ở đúng nền mà nhánh tính năng đã được rebase lên:

~~~bash
git switch main
git merge --ff-only feature/login
~~~

Trên nền tảng pull request, nhóm cũng có thể chọn chiến lược **Rebase and merge**. Nền tảng phát lại các commit của pull request lên nhánh đích và đưa các commit mới vào nhánh đích mà không tạo merge commit. Chi tiết về việc nhánh nguồn có được cập nhật hay không tùy nền tảng và thao tác; không nên mặc định rằng thao tác tích hợp pull request cũng tự cập nhật nhánh local của bạn.

**Khi nào nên thỏa thuận dùng rebase?**

- Nhánh tính năng còn thuộc quyền làm việc của một người hoặc một nhóm đã thống nhất viết lại lịch sử.
- Các commit riêng lẻ có ý nghĩa và cần được giữ lại sau khi tích hợp.
- Nhóm muốn lịch sử tuyến tính nhưng vẫn muốn xem từng commit thay vì gom thành một commit squash.
- Nhánh cần cập nhật trên nền mới của nhánh đích trước khi review hoặc tích hợp.

Rebase giữ các commit thành từng bước nhưng tạo mã định danh mới. Không tự ý rebase nhánh đã push và đang được người khác sử dụng. Nếu đã thống nhất viết lại một nhánh remote, cần thông báo cho những người cộng tác và push bằng cơ chế an toàn như **--force-with-lease** sau khi xác minh trạng thái remote:

~~~bash
git fetch origin
git push --force-with-lease origin feature/login
~~~

**--force-with-lease** kiểm tra remote vẫn ở trạng thái mà local dự kiến trước khi cập nhật tham chiếu. Nó giảm nguy cơ ghi đè commit mới của người khác so với force push thông thường, nhưng không thay thế việc phối hợp và kiểm tra. Nếu nhánh được nhiều người cùng sử dụng, cách an toàn hơn thường là tránh viết lại lịch sử đã chia sẻ.

## 5. Phân biệt cập nhật nhánh bằng rebase và tích hợp bằng rebase

Hai thao tác này thường bị gọi chung là rebase nhưng phục vụ hai mục đích khác nhau:

1. **Cập nhật nhánh công việc**: phát lại commit local lên nền mới của main để nhánh công việc kiểm tra được với thay đổi mới nhất. Sau đó nhóm vẫn có thể chọn merge commit hoặc squash khi tích hợp pull request.
2. **Tích hợp bằng rebase**: dùng rebase như chiến lược cuối cùng để đưa các commit của nhánh công việc vào nhánh đích, thường bằng tùy chọn Rebase and merge của nền tảng hoặc rebase rồi fast-forward.

Ví dụ, một pull request có thể được cập nhật bằng:

~~~bash
git fetch origin
git switch feature/login
git rebase origin/main
~~~

Sau đó nhóm vẫn chọn **Squash and merge** để mỗi pull request chỉ tạo một commit trên main. Việc đã rebase nhánh công việc không bắt buộc phải tích hợp cuối cùng bằng rebase. Tương tự, một pull request có thể được merge bằng merge commit mà không cần rebase nhánh nguồn trước nếu nhóm chấp nhận cấu trúc lịch sử hiện tại.

Khi viết quy ước, hãy ghi rõ hai quyết định riêng: **cách cập nhật nhánh tính năng** và **cách tích hợp pull request**. Điều này tránh hiểu nhầm rằng chọn rebase để đồng bộ nhánh đồng nghĩa phải dùng Rebase and merge ở bước cuối.

## 6. So sánh ba chiến lược

| Tiêu chí | Merge | Squash | Rebase |
| --- | --- | --- | --- |
| Commit nhánh tính năng có trở thành tổ tiên của nhánh đích? | Có, khi merge commit hoặc fast-forward tích hợp nhánh | Không | Có các commit được phát lại, với mã định danh mới |
| Tạo merge commit? | Có khi hai nhánh phân kỳ; có thể ép bằng --no-ff | Không | Không |
| Giữ từng commit của nhánh tính năng? | Có | Không trên lịch sử nhánh đích | Có, nhưng commit được tạo lại |
| Thay đổi mã định danh commit cũ? | Không | Commit tổng hợp có mã mới; commit nhánh cũ vẫn giữ nguyên ở nhánh nguồn | Có đối với commit được phát lại |
| Hình dạng lịch sử | Có thể phân nhánh | Gọn, thường tuyến tính | Thường tuyến tính |
| Phù hợp | Cần ghi nhận cấu trúc và điểm hợp nhất | Một pull request là một đơn vị thay đổi | Cần giữ từng commit và lịch sử tuyến tính |
| Điểm cần lưu ý | Đồ thị có thể nhiều merge commit | Không giữ quan hệ tổ tiên của commit nguồn | Tránh viết lại commit đã chia sẻ |

Không có chiến lược nào luôn tốt hơn hai chiến lược còn lại. Nhóm nên chọn dựa trên thông tin cần lưu trong lịch sử và cách mọi người sử dụng lịch sử đó để review, phát hành, điều tra và khôi phục.

## 7. Những tiêu chí cần thống nhất trong nhóm

### Mục tiêu của một commit trên nhánh chính

Nhóm cần thống nhất commit trên main đại diện cho điều gì:

- Một pull request hoặc một yêu cầu thay đổi: squash thường phù hợp.
- Một lần tích hợp nhiều commit có ý nghĩa riêng: merge hoặc rebase có thể phù hợp.
- Một mốc tích hợp giữa các nhánh dài hạn: merge commit thường thể hiện rõ quan hệ giữa các nhánh.

Một commit nên có thông điệp đủ rõ để người đọc hiểu thay đổi mà không phải mở toàn bộ pull request. Nếu squash, có thể dùng tiêu đề pull request làm commit message theo quy ước, kèm mã ticket hoặc phạm vi thay đổi.

### Khả năng truy vết và điều tra lỗi

Khi dùng merge hoặc rebase, nhóm có thể dùng log để lần theo từng commit trong nhánh tính năng. Với squash, lịch sử nhánh đích chỉ có commit tổng hợp; nội dung và thảo luận chi tiết cần được lưu trong pull request, issue hoặc hệ thống review.

Nếu nhóm thường dùng **git bisect** để tìm commit gây lỗi, hãy cân nhắc kích thước của commit. Squash tạo một bước lớn có thể chứa nhiều thay đổi; merge và rebase giữ các bước nhỏ hơn nhưng các commit nhỏ cần ở trạng thái có thể build hoặc test nếu muốn bisect hiệu quả.

### Cách hoàn tác thay đổi

Với squash, một pull request thường tương ứng một commit nên có thể revert commit đó:

~~~bash
git revert <squash-commit>
~~~

Với merge commit, có thể revert toàn bộ kết quả tích hợp bằng cách chỉ định parent chính:

~~~bash
git revert -m 1 <merge-commit>
~~~

Tham số **-m 1** chọn parent thứ nhất làm mainline trong tình huống thông thường khi merge nhánh tính năng vào main. Trước khi chạy, phải kiểm tra thứ tự parent bằng log hoặc show; chọn sai parent có thể tạo kết quả ngược với mong muốn. Revert merge commit cũng ảnh hưởng đến cách Git xử lý các lần merge sau này, vì vậy cần hiểu tác động trước khi áp dụng.

Với rebase, các commit đã được phát lại là commit riêng trên nhánh đích. Có thể revert từng commit hoặc một dải commit theo kế hoạch, nhưng cần xác định đúng commit và thứ tự phụ thuộc. Revert tạo commit mới để đảo thay đổi, không xóa lịch sử đã công bố.

### Trạng thái chia sẻ của nhánh

Trước khi rebase, hỏi xem commit đã được push hay người khác đã dựa vào nhánh chưa. Commit chỉ tồn tại local thường có thể viết lại dễ dàng hơn. Nhánh remote dùng chung cần quy tắc phối hợp rõ ràng; nếu không, một lần force push có thể làm mất tham chiếu đến công việc mới của đồng đội.

### Cách nhóm review và kiểm thử

Squash không thay thế review từng phần. Pull request vẫn cần mô tả mục tiêu, phạm vi, ảnh hưởng và kết quả kiểm thử. Nếu dùng merge hoặc rebase để giữ từng commit, nhóm có thể yêu cầu commit riêng có nội dung tập trung, thông điệp rõ và không chứa trạng thái build hỏng.

Nên xác định điều kiện tích hợp tối thiểu:

- Review đã được phê duyệt theo quy định.
- CI và các kiểm thử bắt buộc đã thành công.
- Xung đột đã được giải quyết và người giải quyết hiểu thay đổi của cả hai phía.
- Nhánh đích đã được cập nhật theo chính sách đồng bộ của nhóm.
- Tiêu đề và commit message đủ rõ để truy vết sau này.

## 8. Một ma trận quyết định tham khảo

| Tình huống | Chiến lược thường phù hợp | Lý do |
| --- | --- | --- |
| Pull request nhỏ, một mục tiêu, có nhiều commit sửa theo review | Squash | Nhánh chính có một commit đại diện cho thay đổi cuối cùng. |
| Pull request gồm nhiều commit độc lập, mỗi commit có ý nghĩa và đã được kiểm thử | Merge hoặc rebase | Giữ được các bước phát triển để truy vết. |
| Cần thấy rõ thời điểm hai nhánh dài hạn được tích hợp | Merge commit | Đồ thị lưu quan hệ giữa hai dòng lịch sử. |
| Nhánh tính năng cá nhân chưa chia sẻ, muốn cập nhật trên main mới nhất | Rebase nhánh nguồn | Commit local được phát lại trên nền mới. |
| Nhánh tính năng đã chia sẻ cho nhiều người | Merge hoặc quy trình rebase có phối hợp | Tránh viết lại lịch sử mà người khác đang dựa vào. |
| Nhánh phát hành hoặc hotfix cần giữ dấu mốc và thứ tự thay đổi | Thường là merge hoặc rebase theo quy ước phát hành | Lịch sử cần phản ánh quan hệ giữa nhánh phát triển và nhánh phát hành. |

Đây là gợi ý để thảo luận, không phải quy tắc cứng. Ví dụ, một pull request lớn vẫn có thể cần merge commit nếu cấu trúc nhánh quan trọng; một thay đổi nhỏ vẫn có thể cần giữ từng commit nếu mỗi commit đại diện cho một bước migration có thể kiểm chứng.

## 9. Ví dụ về một chính sách tích hợp có thể áp dụng

Một nhóm có thể bắt đầu với quy ước sau rồi điều chỉnh theo nhu cầu:

| Phạm vi | Quy ước mẫu |
| --- | --- |
| Nhánh tính năng ngắn hạn | Mỗi pull request chỉ giải quyết một mục tiêu và có mô tả, review, CI đầy đủ. |
| Cập nhật nhánh tính năng | Fetch rồi rebase lên main khi commit chưa chia sẻ; nếu nhánh đã dùng chung, phối hợp trước khi viết lại lịch sử. |
| Tích hợp pull request thông thường | Squash and merge để main có một commit cho mỗi pull request. |
| Pull request cần giữ từng commit | Cho phép merge hoặc rebase and merge khi commit có ý nghĩa riêng và nhóm đã thống nhất. |
| Nhánh phát hành hoặc nhánh dài hạn | Dùng merge commit khi cần giữ rõ quan hệ tích hợp giữa các nhánh. |
| Sau khi tích hợp squash | Đóng hoặc xóa nhánh nguồn; tạo nhánh mới từ main nếu tiếp tục công việc. |
| Hoàn tác | Revert commit squash hoặc commit tích hợp theo hướng dẫn của người phụ trách nhánh. |

Ví dụ này phù hợp với nhóm dùng pull request ngắn hạn và muốn main gọn. Nhóm có workflow release, audit hoặc yêu cầu truy vết từng commit có thể chọn merge mặc định thay cho squash. Điều quan trọng là ghi rõ ngoại lệ và người có quyền quyết định ngoại lệ.

## 10. Quy trình thống nhất trước khi tích hợp

### Bước 1: xác định nhánh đích và mục tiêu thay đổi

Ghi rõ pull request sẽ đi vào main, develop hay một nhánh release. Xác nhận pull request chỉ chứa một mục tiêu logic hay đang gom nhiều thay đổi độc lập. Mục tiêu càng rõ thì việc chọn một commit squash hay giữ nhiều commit càng dễ.

### Bước 2: kiểm tra trạng thái nhánh và lịch sử

~~~bash
git status -sb
git fetch origin
git log --oneline --graph --decorate --left-right 'HEAD...origin/main'
~~~

Đảm bảo working tree không có thay đổi ngoài dự kiến. Xác định nhánh đã phân kỳ chưa, có commit nào đã được chia sẻ và nhánh nguồn có tiếp tục được sử dụng sau khi tích hợp hay không.

### Bước 3: chọn chiến lược theo quy ước

Trước khi bấm nút merge trên nền tảng hoặc chạy lệnh, xác nhận pull request dùng:

- Merge commit để giữ cấu trúc nhánh.
- Squash and merge để gom thành một commit.
- Rebase and merge để giữ từng commit nhưng phát lại chúng trên nhánh đích.

Đừng nhầm tùy chọn cập nhật nhánh nguồn bằng rebase với lựa chọn Rebase and merge của pull request. Đây là hai quyết định có thể độc lập.

### Bước 4: review và kiểm thử

Review phần diff cuối cùng, xác nhận commit message, kiểm tra CI và bảo đảm xung đột đã được giải quyết đúng. Nếu chiến lược rebase tạo commit mới, cần xác nhận lại trạng thái kiểm thử trên lịch sử sau rebase theo chính sách CI.

### Bước 5: tích hợp và kiểm tra nhánh đích

Sau khi tích hợp, kiểm tra lịch sử:

~~~bash
git fetch origin
git log --oneline --graph --decorate -12 origin/main
~~~

Xác nhận thay đổi đã xuất hiện trên nhánh đích, lịch sử phù hợp với chiến lược đã chọn và pull request được đóng đúng trạng thái. Nếu squash, lưu liên kết tới pull request hoặc issue để người đọc có thể tìm thảo luận và bằng chứng review.

### Bước 6: dọn nhánh và thông báo

Nếu nhánh nguồn không còn dùng, xóa nhánh theo quy định của nhóm. Với nhánh đã squash, không tiếp tục phát triển từ lịch sử cũ nếu không có lý do rõ ràng; tạo nhánh mới từ nhánh đích. Nếu nhánh được giữ lại để tiếp tục làm việc, xác định cách đồng bộ để tránh tích hợp lặp thay đổi.

## 11. Những nhầm lẫn thường gặp

### Squash có phải là merge commit?

Không. Squash đưa tổng thay đổi vào index để tạo một commit thường trên nhánh đích. Commit đó không có hai parent như merge commit và không ghi nhận commit của nhánh nguồn là tổ tiên.

### Rebase có xóa commit cũ không?

Rebase tạo commit mới từ các thay đổi cũ. Commit cũ có thể vẫn tồn tại trong nhánh nguồn, remote hoặc reflog cho đến khi không còn tham chiếu và được dọn dẹp. Điều thay đổi là nhánh sau rebase trỏ đến lịch sử mới; không nên hiểu rebase là thao tác xóa ngay lập tức mọi bản ghi cũ.

### Có thể rebase nhánh rồi vẫn squash khi tích hợp không?

Có. Rebase có thể dùng để cập nhật nhánh nguồn trên nền main mới nhất. Khi pull request hoàn tất, nhóm vẫn có thể chọn squash để tạo một commit duy nhất trên main.

### Squash có giữ lại nội dung review không?

Squash chỉ quyết định cách lưu commit trong Git. Thảo luận, review, CI và liên kết issue phụ thuộc nền tảng quản lý pull request và chính sách lưu trữ của nhóm. Vì vậy, hãy dùng commit message và liên kết pull request để giữ khả năng truy ngược.

### Merge commit có luôn tốt hơn vì giữ nhiều thông tin?

Không. Nó giữ quan hệ nhánh và điểm tích hợp, nhưng cũng làm đồ thị phức tạp hơn. Nếu các commit trong nhánh chỉ là checkpoint hoặc sửa lặt vặt, giữ tất cả có thể làm lịch sử khó đọc.

### Rebase có luôn cần force push?

Không. Rebase một nhánh chỉ ở local không cần push. Nếu nhánh đã được push và rebase làm thay đổi commit trên remote, cần cập nhật remote bằng một lần push viết lại lịch sử; chỉ thực hiện sau khi phối hợp với người đang dùng nhánh và kiểm tra bằng force-with-lease.

## 12. Tự kiểm tra lựa chọn chiến lược

Một pull request thêm tính năng xuất báo cáo có ba commit:

- E1: thêm bộ lọc dữ liệu.
- E2: thêm định dạng CSV.
- E3: sửa test và tài liệu sau review.

Hãy cân nhắc:

1. Nếu E1, E2 và E3 chỉ là các bước hoàn thiện của một tính năng, nhóm muốn main có một commit đại diện, nên chọn gì?
2. Nếu E1 và E2 là hai thay đổi độc lập cần truy vết riêng, E3 chỉ là bước sửa test, chiến lược nào giữ được lịch sử commit?
3. Nếu nhánh xuất báo cáo đã được hai thành viên cùng push và sử dụng, cần cân nhắc điều gì trước khi rebase?
4. Nếu nhóm muốn cập nhật nhánh nguồn trên main mới nhất nhưng vẫn squash pull request, có thể thực hiện cả hai không?

**Gợi ý:** Squash phù hợp với một tính năng có một mục tiêu và muốn một commit trên main. Merge hoặc rebase phù hợp khi cần giữ từng commit; lựa chọn giữa chúng phụ thuộc việc nhóm có cần merge commit và quan hệ nhánh hay không. Với nhánh dùng chung, cần phối hợp trước khi viết lại lịch sử; merge thường tránh việc đổi mã định danh commit đã chia sẻ. Có thể rebase nhánh nguồn để cập nhật, sau đó vẫn chọn squash khi tích hợp pull request.

## Kết luận

Merge giữ các commit và ghi nhận điểm hợp nhất; squash gom tổng thay đổi thành một commit mới trên nhánh đích; rebase phát lại từng commit trên nền mới và tạo mã định danh commit mới. Thỏa thuận hiệu quả cần nói rõ cách cập nhật nhánh công việc, chiến lược tích hợp pull request, quy tắc với nhánh đã chia sẻ, tiêu chuẩn commit message, điều kiện review/CI và cách revert. Khi mọi người hiểu cùng một quy ước, lịch sử Git sẽ dễ đọc và dễ bảo trì hơn.
