# Chuẩn bị nhánh thay đổi nhỏ để người khác dễ xem xét

## Vì sao nên giữ nhánh thay đổi có phạm vi nhỏ?

Trong một nhóm phát triển, nhánh Git thường là nơi tập hợp các commit phục vụ một công việc trước khi được tích hợp vào nhánh chung. Khi nhánh chứa một thay đổi có mục tiêu rõ ràng, người review có thể hiểu vấn đề, lần theo cách giải quyết và xác nhận hành vi nhanh hơn.

Một nhánh thay đổi nhỏ thường có các đặc điểm:

- Giải quyết một mục tiêu hoặc một phần việc có thể mô tả bằng một câu.
- Chỉ sửa những thành phần cần thiết để đạt mục tiêu đó.
- Có kiểm thử hoặc bằng chứng xác nhận hành vi liên quan.
- Không trộn các việc độc lập như nâng cấp dependency, định dạng lại toàn bộ mã nguồn hay đổi tên hàng loạt.
- Có commit và mô tả đủ rõ để người khác hiểu thay đổi.

Ví dụ, yêu cầu “thêm bộ lọc ngày tạo cho màn hình xuất báo cáo” có thể cần cập nhật API, phần xử lý truy vấn, giao diện và kiểm thử. Những thay đổi đó cùng phục vụ một kết quả nên có thể nằm trong một nhánh. Nếu trong lúc làm việc phát hiện cần nâng cấp framework cho toàn hệ thống, đây thường là một công việc riêng và nên được tách ra để review độc lập.

**Nhỏ không có nghĩa là ít dòng bằng mọi giá.** Một thay đổi cần nhiều dòng để triển khai đúng và có kiểm thử đầy đủ vẫn có thể dễ review nếu mọi phần đều phục vụ cùng một mục tiêu. Ngược lại, một thay đổi chỉ vài dòng nhưng làm nhiều việc không liên quan có thể khó đánh giá.

## Xác định phạm vi trước khi tạo nhánh

Trước khi sửa mã, hãy diễn đạt kết quả mong muốn bằng một câu cụ thể. Sau đó xác định những phần cần thay đổi và cách chứng minh kết quả.

Ví dụ:

| Nội dung | Ví dụ |
|---|---|
| Mục tiêu | Cho phép lọc báo cáo theo ngày tạo |
| Phạm vi mã nguồn | Request filter, truy vấn báo cáo và màn hình xuất |
| Kiểm thử | Có dữ liệu trong khoảng ngày, ngoài khoảng ngày và không có dữ liệu |
| Tài liệu | Cập nhật mô tả tham số nếu API công khai thay đổi |
| Ngoài phạm vi | Nâng cấp framework hoặc đổi định dạng toàn bộ module |

Một phạm vi rõ ràng giúp trả lời ba câu hỏi trước khi bắt đầu:

1. Người dùng hoặc hệ thống sẽ nhận được thay đổi gì?
2. Những tệp hoặc thành phần nào thực sự cần sửa để đạt kết quả đó?
3. Kiểm tra nào cho thấy thay đổi hoạt động đúng và không làm hỏng hành vi cũ?

Nếu chưa thể trả lời các câu hỏi này, hãy làm rõ yêu cầu hoặc chia công việc thành các bước nhỏ hơn trước khi tạo nhánh.

### Nhận biết thay đổi nên đi cùng nhau hay tách riêng

Nên giữ các phần trong cùng một nhánh khi chúng phụ thuộc trực tiếp để tạo thành một hành vi hoàn chỉnh. Chẳng hạn, cập nhật mã nguồn, kiểm thử tương ứng và tài liệu mô tả chính tính năng đó thường thuộc cùng phạm vi.

Nên tách nhánh khi các thay đổi có thể được triển khai hoặc review độc lập, ví dụ:

- Một thay đổi sửa lỗi xác thực, thay đổi khác nâng cấp phiên bản thư viện.
- Một thay đổi thêm trường dữ liệu, thay đổi khác dọn dẹp định dạng toàn bộ module.
- Một thay đổi sửa lỗi đang chặn phát hành, thay đổi khác bổ sung tính năng mới chưa liên quan.

Nếu hai phần phụ thuộc chặt chẽ, không nên tách cơ học chỉ để giảm số dòng. Hãy ưu tiên một đơn vị thay đổi hoàn chỉnh, có thể hiểu và kiểm tra được.

## Kiểm tra kho trước khi tạo nhánh

Bắt đầu bằng cách xác định vị trí và trạng thái hiện tại:

~~~bash
git status
git branch --show-current
git branch --list
~~~

Lệnh git status cho biết working tree có thay đổi chưa commit hay không. Nếu đang có công việc dở dang, cần xác định rõ chúng thuộc yêu cầu hiện tại hay một công việc khác. Tránh đưa các thay đổi không liên quan vào nhánh mới.

Nếu working tree có thay đổi độc lập, hãy hoàn tất hoặc cô lập chúng theo quy trình của nhóm trước khi chuyển nhánh. Có thể dùng một worktree riêng khi cần làm nhiều công việc song song; không nên tùy tiện stash rồi quên mất nội dung đã cất.

Xác định nhánh đích mà nhóm dùng để tích hợp, thường là main hoặc một nhánh phát triển đã được quy định. Không mặc định mọi dự án đều dùng main.

## Cập nhật nhánh nền và tạo nhánh công việc

Một nhánh mới nên bắt đầu từ phiên bản mới nhất của nhánh nền để giảm khác biệt không cần thiết khi review và tích hợp.

Ví dụ nhóm sử dụng main làm nhánh tích hợp và remote có tên origin:

~~~bash
# Kiểm tra working tree trước khi chuyển nhánh
git status

# Lấy thông tin mới từ remote
git fetch origin

# Chuyển sang nhánh nền
git switch main

# Cập nhật main theo kiểu fast-forward
git pull --ff-only origin main

# Tạo nhánh cho một mục tiêu cụ thể
git switch -c feature/123-add-export-date-filter
~~~

Tùy chọn --ff-only yêu cầu Git chỉ cập nhật nếu có thể tiến tới bằng fast-forward. Nếu nhánh main cục bộ đã có commit riêng và không thể fast-forward, Git sẽ dừng thay vì tự tạo merge commit. Khi đó hãy kiểm tra lịch sử và xử lý theo quy ước của nhóm.

Có thể tạo nhánh trực tiếp từ remote-tracking branch sau khi fetch:

~~~bash
git fetch origin
git switch -c feature/123-add-export-date-filter origin/main
~~~

Cách này hữu ích khi muốn bắt đầu từ đúng trạng thái hiện tại của origin/main. Tên remote và nhánh nền trong ví dụ cần được thay bằng tên thực tế của dự án.

### Đặt tên nhánh dễ hiểu

Tên nhánh nên giúp thành viên khác nhận biết loại công việc và mục tiêu mà không cần mở mã nguồn. Một số quy ước phổ biến:

| Tiền tố | Mục đích | Ví dụ |
|---|---|---|
| feature/ | Tính năng mới | feature/123-add-export-filter |
| fix/ | Sửa lỗi | fix/245-handle-empty-report |
| docs/ | Tài liệu | docs/update-branch-guide |
| refactor/ | Tái cấu trúc | refactor/report-query |
| test/ | Bổ sung hoặc sửa kiểm thử | test/report-permission-cases |
| chore/ | Công việc bảo trì | chore/update-build-plugin |

Đây là quy ước đặt tên, không phải cú pháp bắt buộc của Git. Hãy theo chính sách của repository. Nếu nhóm có mã issue hoặc ticket, thêm mã đó giúp liên kết nhánh với yêu cầu công việc.

Tránh tên chung chung như temp, test, update hoặc fix-final. Một nhánh có tên cụ thể giúp việc trao đổi, tìm kiếm và dọn dẹp sau khi merge thuận tiện hơn.

## Thực hiện thay đổi theo từng bước nhỏ

Sau khi tạo nhánh, xác nhận đang ở đúng nhánh:

~~~bash
git branch --show-current
git status
~~~

Thực hiện thay đổi theo từng phần có thể kiểm tra được. Với một tính năng, trình tự có thể là:

1. Cập nhật phần xử lý hoặc hợp đồng dữ liệu cần thiết.
2. Thêm hoặc sửa kiểm thử cho hành vi mới.
3. Cập nhật giao diện hoặc nơi gọi nếu tính năng yêu cầu.
4. Cập nhật tài liệu và cấu hình liên quan.
5. Chạy kiểm tra sau mỗi phần quan trọng để phát hiện lỗi sớm.

Hãy tránh những thay đổi làm nhiễu review:

- Không định dạng lại tệp không liên quan.
- Không đổi tên hàng loạt chỉ vì đang chạm vào một khu vực.
- Không thêm log tạm, mã debug hoặc dữ liệu thử nghiệm không cần thiết.
- Không commit file build, cache, IDE hoặc file sinh tự động nếu repository không yêu cầu theo dõi chúng.
- Không đưa token, mật khẩu, khóa riêng hoặc dữ liệu thật nhạy cảm vào mã nguồn.

Nếu cần refactor để triển khai tính năng, hãy giữ refactor ở mức cần thiết và giải thích mối liên hệ với mục tiêu. Một thay đổi có thể chứa nhiều commit, miễn là các commit cùng phục vụ phạm vi đã xác định.

## Chọn lọc nội dung đưa vào commit

Staging area cho phép chọn chính xác phần thay đổi sẽ được ghi vào commit. Đây là công cụ quan trọng để giữ commit tập trung.

Xem các thay đổi chưa stage:

~~~bash
git status --short
git diff
~~~

Đưa một tệp liên quan vào staging:

~~~bash
git add src/report/ReportService.java
~~~

Nếu một tệp chứa cả thay đổi liên quan và không liên quan, có thể chọn từng phần bằng chế độ patch:

~~~bash
git add -p
~~~

Git sẽ hiển thị từng khối thay đổi để bạn chọn đưa vào staging. Các lựa chọn phổ biến gồm:

- y: đưa khối hiện tại vào staging.
- n: bỏ qua khối hiện tại.
- s: tách khối thành các phần nhỏ hơn nếu có thể.
- e: chỉnh sửa patch thủ công khi hiểu rõ cấu trúc diff.
- q: kết thúc việc chọn.

Sau khi stage, xem lại nội dung sẽ được commit:

~~~bash
git diff --cached
git diff --cached --stat
git diff --cached --check
~~~

Nếu thấy nội dung không thuộc mục tiêu, bỏ staging tệp hoặc phần đã chọn rồi thực hiện lại:

~~~bash
git restore --staged path/to/file
~~~

Lệnh này bỏ nội dung khỏi staging area nhưng giữ nguyên thay đổi trong working tree. Không nhầm nó với git restore path/to/file, vốn có thể ghi đè thay đổi chưa stage trong tệp.

### Tạo commit có ý nghĩa

Một commit nên biểu diễn một bước thay đổi có thể giải thích và xem xét. Ví dụ:

~~~bash
git commit -m "Add export date filter"
~~~

Thông điệp commit nên mô tả kết quả hoặc mục đích. Tránh những nội dung như update, fix bug, changes hoặc test vì chúng không cho biết commit đã làm gì.

Nếu có nhiều bước hợp lý trong cùng nhánh, có thể tạo nhiều commit:

~~~bash
git add src/report/ReportFilter.java
git commit -m "Add report date filter model"

git add src/report/ReportRepository.java
git commit -m "Apply date filter to report query"

git add src/test/java/report/ReportRepositoryTest.java
git commit -m "Test report date filtering"
~~~

Ví dụ trên chỉ minh họa cách chia commit. Trong dự án thực tế, có thể gộp các phần phụ thuộc chặt chẽ vào một commit để người review hiểu trọn vẹn thay đổi. Không cần tạo một commit cho mỗi dòng hoặc mỗi lần lưu tệp.

Kiểm tra lịch sử của nhánh:

~~~bash
git log --oneline --decorate main..HEAD
~~~

Nếu nhánh nền là origin/main và đã cập nhật bằng fetch, có thể dùng:

~~~bash
git log --oneline origin/main..HEAD
~~~

Các lệnh trên hiển thị commit có trong nhánh hiện tại mà chưa có ở nhánh nền được chỉ định.

## Đọc lại toàn bộ thay đổi trước khi chia sẻ

Trước khi push, hãy so sánh nhánh hiện tại với nhánh nền. Dùng cú pháp ba dấu chấm để xem thay đổi trên nhánh hiện tại kể từ điểm phân nhánh chung:

~~~bash
git diff --stat origin/main...HEAD
git diff --name-status origin/main...HEAD
git diff --check origin/main...HEAD
git diff origin/main...HEAD
~~~

Thay origin/main bằng nhánh nền mà pull request sẽ nhắm tới. Cú pháp ba dấu chấm giúp diff tập trung vào phần thay đổi của nhánh công việc so với merge base, thay vì so sánh hai đầu nhánh theo cách hai dấu chấm.

Khi đọc diff, kiểm tra theo các nhóm sau:

| Nhóm kiểm tra | Câu hỏi |
|---|---|
| Phạm vi | Mọi tệp có phục vụ cùng mục tiêu không? |
| Logic | Có giữ đúng luồng xử lý và trường hợp biên không? |
| Tương thích | API, cấu trúc dữ liệu và cấu hình có còn tương thích không? |
| Kiểm thử | Có kiểm thử hành vi mới và hành vi cũ bị ảnh hưởng không? |
| Tài liệu | Hướng dẫn hoặc mô tả có cần cập nhật không? |
| Độ sạch | Có debug, file tạm, secret hoặc thay đổi định dạng không liên quan không? |
| Khả năng review | Người khác có thể hiểu mục tiêu và lý do từ diff không? |

Nếu diff quá lớn vì có nhiều định dạng lại hoặc tệp sinh tự động, cân nhắc loại bỏ phần nhiễu hoặc tách công việc. Nếu thay đổi lớn vì một hành vi thực sự cần nhiều phần phối hợp, hãy nhóm các phần đó có cấu trúc và giải thích rõ trong mô tả review.

### Giữ nhánh cập nhật với nhánh nền

Trong lúc phát triển, nhánh nền có thể tiếp tục nhận commit mới. Trước khi gửi review hoặc khi có xung đột, cập nhật thông tin remote:

~~~bash
git fetch origin
~~~

Nếu nhóm dùng rebase để giữ lịch sử tuyến tính và nhánh của bạn chưa được người khác dựa vào:

~~~bash
git rebase origin/main
~~~

Sau rebase, kiểm tra lại diff và chạy lại các kiểm thử bị ảnh hưởng. Rebase thay đổi mã commit của nhánh, vì vậy không tự ý rebase nhánh dùng chung mà người khác đang phát triển trên đó. Nếu nhóm quy định merge thay vì rebase, làm theo quy trình đó.

## Push nhánh và tạo yêu cầu review

Khi thay đổi đã được kiểm tra, chia sẻ nhánh lên remote:

~~~bash
git push -u origin feature/123-add-export-date-filter
~~~

Tùy chọn -u thiết lập upstream cho nhánh cục bộ. Những lần push sau có thể dùng git push theo cấu hình của nhánh.

Sau khi push, tạo pull request hoặc merge request trên nền tảng mà nhóm sử dụng. Chọn đúng nhánh đích, thường là main hoặc nhánh tích hợp theo chính sách dự án.

Một mô tả review hữu ích thường trả lời:

- **Vấn đề:** Điều gì cần được giải quyết?
- **Thay đổi:** Nhánh đã thay đổi hành vi nào và ở những phần nào?
- **Kiểm tra:** Đã chạy test, build hoặc kiểm tra thủ công nào?
- **Ảnh hưởng:** Có thay đổi API, cấu hình, schema hoặc cách sử dụng không?
- **Điểm cần chú ý:** Có quyết định kỹ thuật nào người review nên xem kỹ không?

Ví dụ mô tả:

~~~text
Mục tiêu
Cho phép người dùng lọc báo cáo theo ngày tạo.

Thay đổi
- Bổ sung fromDate và toDate vào bộ lọc báo cáo.
- Áp dụng điều kiện ngày vào truy vấn.
- Bổ sung kiểm thử cho khoảng ngày và trường hợp không có dữ liệu.

Kiểm tra
- Chạy unit test của ReportRepository.
- Chạy kiểm thử API xuất báo cáo.

Lưu ý
Nếu chỉ truyền một đầu mốc ngày, hệ thống áp dụng điều kiện tương ứng cho đầu mốc đó.
~~~

Mô tả cần trung thực với những gì đã thực hiện. Không ghi “đã test” nếu chưa chạy kiểm thử; nếu một kiểm tra bị bỏ qua, hãy nêu rõ.

## Khi phạm vi thay đổi lớn dần

Trong quá trình làm việc, có thể phát hiện thêm vấn đề liên quan. Trước khi mở rộng nhánh, đánh giá mối quan hệ của vấn đề mới với mục tiêu ban đầu.

- Nếu vấn đề mới là điều kiện cần để tính năng hoạt động đúng, giữ trong cùng nhánh và cập nhật mô tả phạm vi.
- Nếu vấn đề có thể phát hành độc lập, tạo issue hoặc nhánh riêng để xử lý sau.
- Nếu cần nhiều nhánh phụ thuộc nhau, trao đổi với nhóm về thứ tự tích hợp và cách review từng phần.
- Nếu nhánh đã trở nên quá rộng, cân nhắc tách phần độc lập trước khi gửi review.

Không tách một thay đổi thành nhiều pull request nếu reviewer không thể hiểu hoặc kiểm thử từng phần một cách độc lập. Khi các nhánh phụ thuộc, mô tả rõ nhánh nào cần được tích hợp trước và nhánh nào dựa trên thay đổi đó.

Nếu công việc không còn cần thiết hoặc được thay thế, trao đổi với nhóm trước khi đóng review và xóa nhánh theo quy trình của repository.

## Quy trình mẫu hoàn chỉnh

Ví dụ tạo nhánh để bổ sung bộ lọc ngày cho báo cáo:

~~~bash
# Kiểm tra trạng thái và cập nhật nhánh nền
git status
git fetch origin
git switch main
git pull --ff-only origin main

# Tạo nhánh có tên mô tả công việc
git switch -c feature/123-add-export-date-filter

# Thực hiện sửa mã nguồn và kiểm thử
# Sau đó xem lại thay đổi
git status --short
git diff

# Chọn đúng các phần liên quan
git add -p
git diff --cached
git diff --cached --check

# Tạo commit có mục đích rõ ràng
git commit -m "Add export date filter"

# Kiểm tra lịch sử và phạm vi nhánh
git log --oneline main..HEAD
git diff --stat origin/main...HEAD
git diff origin/main...HEAD

# Chia sẻ nhánh lên remote
git push -u origin feature/123-add-export-date-filter
~~~

Sau đó mở pull request hoặc merge request tới nhánh nền. Trong quá trình review, tiếp nhận góp ý, sửa đổi trên cùng nhánh nếu vẫn thuộc mục tiêu ban đầu, chạy lại kiểm thử và push commit bổ sung.

## Checklist trước khi yêu cầu review

- [ ] Nhánh được tạo từ nhánh nền phù hợp và có tên mô tả mục tiêu.
- [ ] Phạm vi nhánh tập trung vào một kết quả có thể giải thích.
- [ ] Các thay đổi không liên quan đã được tách ra.
- [ ] Kiểm thử cần thiết đã được bổ sung hoặc cập nhật.
- [ ] Đã xem cả thay đổi staged và unstaged.
- [ ] Đã kiểm tra diff so với nhánh nền.
- [ ] Không còn mã debug, file tạm hoặc thông tin bí mật.
- [ ] Thông điệp commit mô tả rõ mục đích.
- [ ] Nhánh đã được push lên đúng remote.
- [ ] Mô tả review nêu vấn đề, thay đổi và kết quả kiểm tra.

## Ghi nhớ

Một nhánh dễ review bắt đầu từ phạm vi rõ ràng, được tạo trên nhánh nền cập nhật và chỉ chứa những thay đổi cùng phục vụ một mục tiêu. Trong quá trình làm việc, hãy chọn lọc nội dung vào staging area, tạo commit có ý nghĩa, đọc lại diff so với nhánh nền, chạy kiểm thử phù hợp và mô tả trung thực kết quả trước khi chia sẻ. Kích thước nhánh nên đủ nhỏ để người khác hiểu và xác nhận, đồng thời vẫn giữ trọn vẹn một thay đổi có thể kiểm tra và tích hợp an toàn.

