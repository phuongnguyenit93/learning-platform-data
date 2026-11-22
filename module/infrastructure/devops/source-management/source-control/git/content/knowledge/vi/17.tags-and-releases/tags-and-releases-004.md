# Tạo tag tại commit trong quá khứ và kiểm tra đối tượng đích

Git cho phép tạo tag trỏ đến bất kỳ commit nào mà repository đang có, kể cả commit đã nằm sâu trong lịch sử. Bạn không cần checkout commit đó hoặc quay nhánh hiện tại về quá khứ. Chỉ cần xác định đúng commit, tạo tag trỏ đến commit ấy rồi kiểm tra đối tượng mà tag đang tham chiếu.

Trong chương **Tag và mốc phiên bản** của module **SOURCE_CONTROL_GIT**, bài học này hướng dẫn cách đánh dấu một mốc cũ, chẳng hạn commit đã phát hành nhưng trước đây chưa được gắn tag. Bạn sẽ phân biệt lightweight tag và annotated tag, xác minh tag có thực sự trỏ đến commit mong muốn hay không, đồng thời biết cách chia sẻ tag với remote mà không vô tình thay đổi một mốc phát hành đã công bố.

Sau bài học, bạn có thể:

- Tìm và xác nhận commit cần đánh dấu trong lịch sử.
- Tạo lightweight tag hoặc annotated tag tại commit cũ.
- Kiểm tra tag đang trỏ trực tiếp đến commit, tag object hay loại object khác.
- So sánh commit đích thực tế với commit dự kiến.
- Đẩy tag lên remote và xác minh tag đã được chia sẻ.
- Xử lý tag trùng tên hoặc tag phát hành bị gắn nhầm.

## 1. Tag đánh dấu một đối tượng trong lịch sử

Tag là một tham chiếu có tên trong namespace refs/tags. Tag thường được dùng để đánh dấu phiên bản phát hành, mốc bàn giao, bản build đã kiểm thử hoặc một commit quan trọng cần tìm lại.

Ví dụ lịch sử:

~~~text
A---B---C---D---E  (main)
        ^
        v1.0.0
~~~

Tag v1.0.0 trỏ đến commit C, dù nhánh main đã tiến đến E. Khi tạo tag tại commit cũ, Git không di chuyển main, không checkout C và không thay đổi working tree. Git chỉ tạo một tham chiếu mới có tên v1.0.0 trỏ đến đối tượng được chọn.

Điểm khác biệt quan trọng giữa branch và tag:

- Branch thường di chuyển khi tạo commit mới trên nhánh đó.
- Tag thông thường được xem là mốc cố định. Git không tự di chuyển tag khi nhánh tiếp tục phát triển.
- Tag nằm trong repository local cho đến khi được push lên remote.

Một tag có thể trỏ đến commit, tree, blob hoặc một tag object khác. Trong quy trình phát hành phần mềm, nhóm thường muốn tag cuối cùng xác định một commit cụ thể để có thể dựng lại mã nguồn của phiên bản.

## 2. Tìm commit cũ cần gắn tag

Trước khi tạo tag, hãy xác định chính xác commit cần đánh dấu. Đừng chọn chỉ dựa trên vị trí tương đối như “commit trước đó” nếu lịch sử đã thay đổi hoặc nhánh hiện tại đã tiến xa.

### Xem lịch sử commit

~~~bash
git log --oneline --decorate --all
~~~

Lệnh này hiển thị lịch sử có thể đi tới từ các tham chiếu hiện có, gồm nhánh và tag. Dùng các tùy chọn sau để thu hẹp kết quả:

~~~bash
git log --oneline --decorate --all -- path/to/file
git log --format=fuller --all
~~~

Lệnh đầu giúp tìm các commit đã thay đổi một file. Lệnh sau hiển thị thêm thông tin tác giả và thời điểm author/committer để đối chiếu một mốc phát hành.

### Kiểm tra nội dung commit

Khi đã tìm được hash hoặc revision dự kiến, xem thông tin commit:

~~~bash
git show --stat <commit>
git show --format=fuller --no-ext-diff <commit>
~~~

Kiểm tra danh sách file thay đổi, nội dung diff, thông điệp commit và các thông tin liên quan. Nếu tag đại diện cho một bản phát hành, hãy xác nhận commit đó đúng với mã nguồn đã được kiểm thử và phát hành.

### Chuẩn hóa thành commit hash

Có thể yêu cầu Git xác nhận revision có thể phân giải thành commit:

~~~bash
git rev-parse --verify '<commit>^{commit}'
~~~

Thay <commit> bằng hash hoặc revision cần kiểm tra. Phần hậu tố ^{commit} yêu cầu Git phân giải đối tượng về một commit. Nếu revision không tồn tại hoặc không phân giải được thành commit, lệnh sẽ thất bại.

Sau khi xác minh, ghi lại hash đầy đủ để dùng trong lệnh tạo tag. Dùng hash cụ thể giúp tránh nhầm khi các nhánh hoặc tham chiếu di chuyển trong lúc chuẩn bị phát hành.

## 3. Lightweight tag: một tham chiếu trực tiếp

Lightweight tag về cơ bản là một tên tham chiếu trực tiếp đến object được chọn. Nó không tạo tag object riêng, không lưu thông điệp tagger và không có chữ ký tag.

Tạo lightweight tag tại commit cũ:

~~~bash
git tag v1.0.0 <commit>
~~~

Nếu bỏ đối số commit:

~~~bash
git tag v1.0.0
~~~

Git tạo tag tại commit mà HEAD đang trỏ tới.

Lightweight tag phù hợp cho mốc local tạm thời, điểm đánh dấu phục vụ thử nghiệm hoặc trường hợp chỉ cần tên ngắn trỏ đến một object. Với mốc phát hành cần lưu người tạo, thời điểm gắn tag, thông điệp và chữ ký, annotated tag thường phù hợp hơn.

Có thể liệt kê tag:

~~~bash
git tag --list
git tag --list 'v1.*'
~~~

Để xem commit mà lightweight tag trỏ đến:

~~~bash
git show --no-patch --oneline v1.0.0
git rev-parse 'v1.0.0^{commit}'
~~~

## 4. Annotated tag: một đối tượng tag có metadata

Annotated tag tạo một tag object riêng. Object này chứa:

- Hash của object đích.
- Loại object đích, chẳng hạn commit.
- Tên tag.
- Thông tin tagger và thời điểm tạo tag.
- Thông điệp tag.
- Chữ ký nếu tag được ký.

Tạo annotated tag tại commit cũ:

~~~bash
git tag -a v1.0.0 <commit> -m "Release v1.0.0"
~~~

Nếu không ghi commit, Git dùng HEAD hiện tại:

~~~bash
git tag -a v1.0.0 -m "Release v1.0.0"
~~~

Lệnh đầu phù hợp khi cần gắn tag cho commit đã nằm trong lịch sử. Bạn không phải checkout commit đó. Lệnh thứ hai tiện khi đang đứng đúng commit cần phát hành.

Annotated tag có thể được ký nếu môi trường đã cấu hình khóa ký:

~~~bash
git tag -s v1.0.0 <commit> -m "Release v1.0.0"
~~~

Chữ ký giúp người nhận xác minh danh tính người ký và tính toàn vẹn của tag object theo cấu hình xác minh. Để kiểm tra chữ ký:

~~~bash
git tag -v v1.0.0
~~~

Lệnh xác minh cần có khóa công khai và cấu hình tương ứng. Một tag không ký vẫn có thể là annotated tag hợp lệ; chữ ký là yêu cầu bổ sung của quy trình phát hành.

## 5. Tag một commit trong quá khứ không thay đổi ngày của commit

Khi tạo annotated tag hôm nay cho một commit cũ, có hai mốc thời gian khác nhau:

- **Commit date**: thời điểm commit được tạo hoặc ghi nhận theo metadata của commit.
- **Tagger date**: thời điểm người tạo annotated tag gắn mốc phiên bản.

Tagger date là thời điểm tạo tag object, không phải ngày commit cũ được tạo. Gắn tag v1.0.0 hôm nay cho commit từ tháng trước không làm commit đó có ngày mới và cũng không biến tag thành bằng chứng rằng phiên bản đã được phát hành vào tháng trước.

Nếu cần tái lập mốc phát hành lịch sử, hãy kiểm tra thông tin phát hành thực tế từ hệ thống release, CI, artifact registry hoặc tài liệu dự án. Không sửa ngày tag để làm cho metadata trông giống ngày phát hành cũ nếu điều đó không phản ánh sự kiện thực tế.

Ví dụ:

~~~bash
git show --no-patch --format=fuller <commit>
git cat-file -p v1.0.0
~~~

Lệnh đầu xem metadata commit. Lệnh thứ hai xem nội dung tag object của annotated tag, trong đó có trường tagger và thời điểm gắn tag.

## 6. Kiểm tra tag đang trỏ đến object nào

Tên tag tồn tại chưa đủ để chứng minh tag trỏ đến đúng commit. Cần kiểm tra loại object và hash đích.

### Xác định loại object ngay dưới tên tag

~~~bash
git cat-file -t v1.0.0
~~~

Kết quả thường gặp:

- Lightweight tag trỏ trực tiếp đến commit: kết quả là commit.
- Annotated tag: kết quả là tag, vì tên tag trỏ đến tag object.

Do đó, thấy kết quả tag không có nghĩa tag sai. Cần bóc lớp tag object để kiểm tra object cuối cùng.

### Xem nội dung annotated tag object

~~~bash
git cat-file -p v1.0.0
~~~

Một annotated tag thường có nội dung tương tự:

~~~text
object 0123456789abcdef...
type commit
tag v1.0.0
tagger Developer <developer@example.com> 1730000000 +0700

Release v1.0.0
~~~

Trường object chứa hash của object được tag. Trường type cho biết loại object đó. Nếu type là commit, tag object đang trỏ trực tiếp đến commit. Nếu type là tree hoặc blob, tag không đánh dấu commit như mong đợi của một mốc phát hành mã nguồn.

### Bóc tag về commit đích

Dùng toán tử peel:

~~~bash
git rev-parse 'v1.0.0^{commit}'
~~~

Lệnh này yêu cầu Git phân giải tag thành một commit. Nó hoạt động với lightweight tag, annotated tag và chuỗi tag lồng nhau nếu cuối cùng phân giải được thành commit.

So sánh với commit dự kiến:

~~~bash
git rev-parse '<commit>^{commit}'
git rev-parse 'v1.0.0^{commit}'
~~~

Hai hash phải giống nhau nếu tag được gắn đúng commit đã chọn. Đây là phép kiểm tra trực tiếp và rõ ràng hơn việc chỉ nhìn tên tag trong danh sách.

Có thể xem thông tin commit mà tag phân giải tới:

~~~bash
git show --no-patch --format=fuller 'v1.0.0^{commit}'
~~~

Lệnh này hiển thị metadata của commit đích sau khi peel tag, giúp xác nhận thông điệp, tác giả và thời gian commit.

## 7. Kiểm tra tag và commit bằng nhiều góc nhìn

Một số lệnh hữu ích khi rà soát mốc phát hành:

~~~bash
git tag --list --sort=-version:refname
git tag --points-at <commit>
git show --no-patch --decorate <commit>
git for-each-ref refs/tags
~~~

- Lệnh thứ nhất liệt kê tag theo thứ tự phiên bản, hữu ích khi tên tag theo quy ước version.
- Lệnh thứ hai tìm các tag trỏ trực tiếp đến commit đã chọn.
- Lệnh thứ ba hiển thị commit cùng các tham chiếu liên quan.
- Lệnh thứ tư liệt kê các tag ref và metadata của chúng; có thể bổ sung format để hiển thị trường cụ thể.

Ví dụ xem tên tag, object hash và loại object:

~~~bash
git for-each-ref --format='%(refname:short) %(objectname) %(objecttype)' refs/tags
~~~

Với annotated tag, objecttype là tag. Với lightweight tag trỏ trực tiếp đến commit, objecttype là commit. Nếu cần biết commit cuối cùng mà mỗi tag đại diện, hãy dùng peel expression hoặc kiểm tra riêng từng tag.

## 8. Đảm bảo commit cũ vẫn có thể truy cập

Git chỉ tạo tag khi object đích tồn tại trong repository. Nếu bạn có hash của một commit cũ nhưng repository hiện tại không có object đó, lệnh tạo tag sẽ thất bại.

Kiểm tra commit:

~~~bash
git cat-file -t <commit>
git show --no-patch --oneline <commit>
~~~

Nếu commit không có trong repository, hãy kiểm tra clone có phải shallow clone hoặc lịch sử đã bị giới hạn không. Có thể cần fetch thêm lịch sử từ remote có chứa commit. Không tạo tag dựa trên một hash chưa được xác minh hoặc một commit có nội dung không rõ nguồn gốc.

Sau khi tag được tạo, tag giữ tham chiếu đến object đích và giúp object đó tiếp tục có thể truy cập thông qua ref. Điều này đặc biệt hữu ích nếu commit cũ không còn nằm trên đầu một nhánh đang hoạt động.

## 9. Chia sẻ tag với remote

Tag mới tạo chỉ có trong repository local. Muốn đồng đội hoặc pipeline CI/CD nhìn thấy tag, hãy push tag lên remote.

### Push một tag cụ thể

~~~bash
git push origin v1.0.0
~~~

Đây là cách rõ ràng khi chỉ muốn chia sẻ một mốc. Nó tránh đẩy hàng loạt tag local không liên quan lên remote.

### Push các annotated tag có liên quan đến commit được đẩy

~~~bash
git push --follow-tags origin main
~~~

Tùy chọn follow-tags đẩy các annotated tag còn thiếu trên remote và có thể truy cập từ các commit đang được push. Nó không có nghĩa là mọi lightweight tag local đều được đẩy.

### Push tất cả tag

~~~bash
git push origin --tags
~~~

Lệnh này đẩy tất cả tag local chưa có trên remote. Chỉ dùng khi nhóm chủ ý đồng bộ toàn bộ tag; nếu repository local có tag thử nghiệm hoặc tag không liên quan, chúng cũng có thể được chia sẻ.

### Kiểm tra tag trên remote

~~~bash
git ls-remote --tags origin
git ls-remote --tags origin 'v1.0.0'
~~~

Với annotated tag, kết quả có thể có hai dòng: một dòng cho tag object và một dòng có hậu tố ^{} cho object cuối cùng sau khi peel. Dòng peel giúp kiểm tra commit mà annotated tag cuối cùng đại diện.

Để lấy tag từ remote về local:

~~~bash
git fetch origin --tags
~~~

Sau khi fetch, dùng git show hoặc git rev-parse để xác minh lại tag local.

## 10. Quy tắc đặt tên và quản lý tag phát hành

Tên tag nên nhất quán, dễ đọc và phù hợp với cách nhóm đánh số phiên bản. Một quy ước phổ biến là Semantic Versioning:

- v1.2.0: phiên bản phát hành chính thức.
- v1.2.1: bản vá sửa lỗi tương thích.
- v1.3.0: bổ sung tính năng tương thích ngược.
- v2.0.0: thay đổi có thể phá vỡ tương thích.

Đây là quy ước đặt tên, không phải yêu cầu của Git. Nếu dự án dùng lịch phát hành hoặc mã build riêng, có thể chọn một format khác nhưng cần ghi rõ ý nghĩa từng thành phần.

Đối với release tag, nhóm thường nên:

- Dùng annotated tag để lưu thông điệp và người tạo tag.
- Chỉ tag commit đã được review, kiểm thử và xác nhận là nội dung phát hành.
- Gắn tag vào commit trên nhánh phát hành hoặc commit đã được phê duyệt.
- Kiểm tra tag peel về đúng commit trước khi push.
- Ghi chú release và artifact liên quan để có thể truy ngược.
- Tránh di chuyển hoặc tái sử dụng tên tag đã công bố.

Tag không tự bảo đảm artifact được build từ commit đó. Pipeline phát hành nên lưu commit hash cùng tag trong metadata artifact để người dùng có thể xác nhận mã nguồn tạo ra gói phát hành.

## 11. Xử lý tag trùng tên hoặc gắn nhầm

Git không cho tạo một tag mới bằng tên đã tồn tại nếu không yêu cầu ghi đè. Trước tiên, kiểm tra tag cũ:

~~~bash
git show --no-patch --decorate v1.0.0
git rev-parse 'v1.0.0^{commit}'
~~~

Nếu tag chưa từng được chia sẻ và bạn xác nhận muốn thay đổi tag local, có thể xóa rồi tạo lại:

~~~bash
git tag -d v1.0.0
git tag -a v1.0.0 <correct-commit> -m "Release v1.0.0"
~~~

Hoặc dùng tùy chọn force để di chuyển tag local:

~~~bash
git tag -f -a v1.0.0 <correct-commit> -m "Release v1.0.0"
~~~

Không dùng force chỉ để làm lệnh tạo tag chạy qua lỗi tên đã tồn tại. Việc thay đổi tag có thể khiến người khác hoặc pipeline đang dùng hash cũ hiểu sai mốc phát hành.

Nếu tag đã được push, không tự ý ghi đè hoặc xóa trên remote. Hãy thông báo cho nhóm, xác định hệ thống nào đã tiêu thụ tag và thống nhất cách sửa. Với một release đã công bố, cách rõ ràng thường là giữ nguyên tag cũ, phát hành tag mới như v1.0.1 hoặc một tên sửa lỗi theo chính sách dự án.

Nếu nhóm thực sự cho phép di chuyển remote tag, cần thực hiện có chủ đích và thông báo cho mọi bên tiêu thụ. Git hỗ trợ push cập nhật tag đã tồn tại bằng force, nhưng đó là thao tác viết lại tham chiếu được chia sẻ; không coi nó là cách sửa mặc định.

## 12. Quy trình tạo và xác minh tag tại commit quá khứ

Giả sử nhóm phát hiện phiên bản 1.0.0 đã được phát hành từ commit cũ nhưng repository chưa có tag. Có thể thực hiện theo quy trình sau.

### Bước 1: cập nhật thông tin remote và xem lịch sử

~~~bash
git fetch origin
git log --oneline --decorate --all
~~~

Tìm commit đã được phát hành dựa trên thông tin release, CI hoặc artifact. Không chọn commit chỉ vì nó đang là HEAD của main.

### Bước 2: kiểm tra commit đích

~~~bash
git show --stat <release-commit>
git show --format=fuller --no-ext-diff <release-commit>
git rev-parse --verify '<release-commit>^{commit}'
~~~

Xác nhận diff, metadata và hash đầy đủ. Nếu cần, đối chiếu với hash đã lưu trong artifact hoặc thông tin build.

### Bước 3: kiểm tra tên tag chưa được sử dụng

~~~bash
git tag --list 'v1.0.0'
git ls-remote --tags origin 'v1.0.0'
~~~

Nếu tag đã tồn tại ở local hoặc remote, dừng lại để kiểm tra tag đang trỏ đến đâu. Không tự tạo một tag cùng tên bằng cách ghi đè.

### Bước 4: tạo annotated tag tại commit cũ

~~~bash
git tag -a v1.0.0 <release-commit> -m "Release v1.0.0"
~~~

Thay <release-commit> bằng hash đã xác minh ở bước 2. Tag được tạo tại commit đó dù HEAD hiện tại đang ở commit mới hơn.

### Bước 5: xác minh object type và commit đích

~~~bash
git cat-file -t v1.0.0
git cat-file -p v1.0.0
git rev-parse 'v1.0.0^{commit}'
git show --no-patch --format=fuller 'v1.0.0^{commit}'
~~~

Với annotated tag, lệnh đầu trả về tag. Nội dung tag object phải cho thấy object đích có type commit. Hash từ lệnh rev-parse phải trùng với hash release-commit đã xác minh.

### Bước 6: push tag và kiểm tra remote

~~~bash
git push origin v1.0.0
git ls-remote --tags origin 'v1.0.0'
~~~

Xác nhận remote có tag và dòng peel của annotated tag trỏ đến commit mong muốn. Ghi nhận tag, commit hash và thông tin artifact trong ghi chú phát hành.

## 13. Những nhầm lẫn thường gặp

### Tạo tag ở commit cũ có làm thay đổi nhánh hiện tại không?

Không. Git chỉ tạo một tham chiếu tag trỏ đến object đã chọn. HEAD, branch hiện tại và working tree không bị di chuyển bởi lệnh tạo tag.

### Tên tag có chứng minh tag trỏ đến commit phát hành đúng không?

Không. Tên như v1.0.0 chỉ là tên tham chiếu. Hãy kiểm tra object type, peel tag về commit và so sánh hash với commit đã được xác nhận.

### Annotated tag luôn trỏ trực tiếp đến commit?

Không. Tag object có thể trỏ đến commit, tree, blob hoặc một tag object khác. Dùng biểu thức ^{commit} để xác nhận đối tượng cuối cùng phân giải được thành commit.

### Lightweight tag có lưu ngày tạo tag riêng không?

Không có tag object riêng để lưu tagger và tagger date. Các công cụ có thể hiển thị ngày từ commit mà lightweight tag trỏ đến; không nên diễn giải ngày đó là ngày tag được tạo.

### Tạo tag local có tự xuất hiện trên remote không?

Không. Cần push tag cụ thể, dùng follow-tags hoặc push tất cả tag theo chính sách của nhóm.

### Có nên sửa một release tag đã công bố nếu gắn nhầm commit?

Không nên tự ý di chuyển tag đã được chia sẻ. Việc thay đổi có thể khiến người dùng, pipeline và artifact tham chiếu đến các commit khác nhau dưới cùng tên. Hãy phối hợp và ưu tiên tạo một tag sửa lỗi mới theo chính sách release.

## 14. Tự kiểm tra

Giả sử nhánh main đang ở commit H. Phiên bản 2.1.0 thực tế được phát hành từ commit F, nhưng tag v2.1.0 chưa tồn tại. Repository hiện có các commit:

~~~text
A---B---C---D---E---F---G---H  (main)
                  ^
                  commit phát hành 2.1.0
~~~

Hãy trả lời:

1. Có cần checkout F trước khi tạo tag không?
2. Lệnh nào tạo annotated tag v2.1.0 tại F?
3. Lệnh nào xác nhận tên tag phân giải đến một commit?
4. Vì sao git cat-file -t v2.1.0 có thể trả về tag thay vì commit?
5. Làm thế nào so sánh commit mà tag trỏ tới với hash của F?
6. Sau khi tạo tag local, cần làm gì để CI trên remote nhìn thấy tag?
7. Nếu tag v2.1.0 đã được push nhưng trỏ nhầm E, nhóm nên xử lý ra sao?

**Gợi ý:** Không cần checkout F. Dùng git tag -a v2.1.0 F -m "Release v2.1.0". Dùng git rev-parse 'v2.1.0^{commit}' để xác nhận tag phân giải thành commit và so sánh với git rev-parse 'F^{commit}'. Với annotated tag, tên tag trỏ đến tag object nên cat-file -t trả về tag; cần peel để xem commit đích. Dùng git push origin v2.1.0 rồi xác minh bằng git ls-remote. Nếu tag đã công bố sai, phối hợp với nhóm và ưu tiên phát hành tag sửa lỗi mới thay vì tự ý di chuyển mốc cũ.

## Kết luận

Tạo tag tại commit trong quá khứ chỉ cần xác định đúng commit và tạo tham chiếu trỏ đến nó; không cần checkout hoặc di chuyển nhánh hiện tại. Lightweight tag là tham chiếu trực tiếp, còn annotated tag lưu metadata và có thể được ký nên thường phù hợp cho release. Sau khi tạo, hãy kiểm tra loại object, peel tag về commit và so sánh hash với commit phát hành đã xác nhận. Cuối cùng push tag lên remote và xác minh từ remote để mọi thành viên, hệ thống CI và artifact đều sử dụng cùng một mốc.
