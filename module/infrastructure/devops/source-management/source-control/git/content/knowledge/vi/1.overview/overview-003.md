# Quản lý phiên bản tập trung và phân tán

## Vì sao cần quản lý phiên bản?

Quản lý phiên bản (Version Control) là cách ghi nhận và quản lý những thay đổi của mã nguồn, tài liệu cấu hình và các tệp dự án theo thời gian. Một hệ thống quản lý phiên bản (Version Control System — VCS) giúp nhóm phát triển biết ai đã thay đổi nội dung nào, thay đổi vào thời điểm nào, vì sao thay đổi được thực hiện và có thể khôi phục hoặc so sánh các trạng thái trước đó.

Khi nhiều người cùng làm việc trên một dự án, VCS còn cung cấp cơ chế để kết hợp thay đổi, phát triển tính năng song song và xử lý xung đột. Hai mô hình kiến trúc phổ biến là **quản lý phiên bản tập trung** (Centralized Version Control System — CVCS) và **quản lý phiên bản phân tán** (Distributed Version Control System — DVCS). Git thuộc mô hình phân tán.

## Mô hình quản lý phiên bản tập trung

Trong mô hình tập trung, toàn bộ lịch sử phiên bản chính được lưu tại một máy chủ hoặc kho lưu trữ trung tâm. Các thành viên lấy một bản làm việc (working copy) từ máy chủ, chỉnh sửa tệp trên máy của mình rồi gửi thay đổi trở lại máy chủ bằng thao tác commit.

~~~mermaid
flowchart TB
    S[Kho lưu trữ trung tâm]:::central
    A[Nhà phát triển A] -->|checkout / update| S
    B[Nhà phát triển B] -->|checkout / update| S
    A -->|commit| S
    B -->|commit| S
    classDef central fill:#dbeafe,stroke:#2563eb,color:#1e3a8a
~~~

Máy chủ là điểm tham chiếu chung cho lịch sử và trạng thái của dự án. Những hệ thống như Subversion (SVN) và Perforce thường được dùng theo mô hình này.

Quy trình cơ bản thường diễn ra như sau:

1. Thành viên checkout dự án hoặc một nhánh từ kho trung tâm.
2. Thành viên sửa tệp trong working copy và kiểm tra thay đổi cục bộ.
3. Thành viên cập nhật thay đổi mới từ máy chủ để phát hiện nội dung đã được người khác sửa.
4. Nếu có xung đột, thành viên giải quyết rồi commit thay đổi lên máy chủ.
5. Các thành viên khác update để nhận revision mới.

Ví dụ với SVN:

~~~bash
# Lấy working copy từ kho trung tâm
svn checkout https://svn.example.com/repos/app/trunk app
cd app

# Kiểm tra thay đổi và phần khác biệt
svn status
svn diff

# Đưa tệp mới vào quản lý phiên bản và commit lên máy chủ
svn add src/new-feature.java
svn commit -m "Add new feature"

# Nhận các revision mới từ máy chủ
svn update

# Xem lịch sử revision
svn log
~~~

Điểm dễ nhận thấy là lệnh svn commit gửi thay đổi lên kho trung tâm. Revision mới được ghi nhận tại máy chủ và trở thành một phần của lịch sử chung.

### Ưu điểm và giới hạn

- **Quản trị tập trung:** quản trị viên có một nơi chính để phân quyền, theo dõi hoạt động và áp dụng chính sách lưu trữ.
- **Mô hình cộng tác dễ hình dung:** thành viên làm việc với cùng một kho chính; trạng thái chung được cập nhật qua máy chủ.
- **Phù hợp với quy trình kiểm soát chặt:** một số tổ chức muốn kiểm soát quyền đọc, ghi và luồng thay đổi tại một điểm.
- **Phụ thuộc vào máy chủ:** nếu máy chủ không truy cập được, thành viên thường không thể commit revision mới vào lịch sử chung. Họ vẫn có thể sửa tệp cục bộ, nhưng việc ghi nhận thay đổi phải chờ máy chủ hoạt động lại.
- **Thao tác mạng thường xuyên:** checkout, update và commit cần kết nối tới máy chủ; độ trễ mạng có thể ảnh hưởng trải nghiệm.

CVCS vẫn có thể hỗ trợ nhánh và hợp nhất. Khác biệt nằm ở cách lưu trữ và phân phối lịch sử: kho trung tâm giữ lịch sử chính, còn working copy của thành viên thường không phải một bản sao đầy đủ, độc lập của toàn bộ kho.

## Mô hình quản lý phiên bản phân tán

Trong mô hình phân tán, mỗi bản clone của kho lưu trữ đều có dữ liệu kho và lịch sử phiên bản cần thiết để làm việc độc lập. Thành viên có thể tạo commit trên máy của mình mà chưa cần kết nối tới máy chủ dùng chung. Khi cần trao đổi thay đổi, họ đồng bộ với một hoặc nhiều kho khác thông qua các thao tác như fetch, pull và push.

~~~mermaid
flowchart TB
    A[Kho cục bộ của A<br/>lịch sử và commit] <-->|fetch / push| R[Kho dùng chung hoặc kho của nhóm]
    B[Kho cục bộ của B<br/>lịch sử và commit] <-->|fetch / push| R
    C[Kho cục bộ của C<br/>lịch sử và commit] <-->|fetch / push| R
    A <-->|trao đổi trực tiếp khi phù hợp| B
~~~

Git và Mercurial là các ví dụ tiêu biểu của DVCS. Với Git, một lệnh git clone thông thường tạo một kho cục bộ có lịch sử của dự án, bên cạnh working tree để chỉnh sửa tệp. (Các chế độ clone rút gọn như shallow clone có thể chỉ lấy một phần lịch sử.)

Quy trình cơ bản với Git:

~~~bash
# Tạo kho cục bộ từ kho từ xa
git clone https://example.com/team/app.git
cd app

# Tạo nhánh và làm việc độc lập
git switch -c feature/new-report

# Ghi nhận thay đổi vào kho cục bộ
git status
git add src/report.java
git commit -m "Add report generation"

# Lấy thông tin mới từ remote để xem và tích hợp
git fetch origin
git rebase origin/main

# Chia sẻ nhánh lên remote
git push -u origin feature/new-report
~~~

Lệnh git commit chỉ ghi nhận snapshot vào kho cục bộ. git fetch tải thông tin và commit mới từ remote về nhưng không tự tích hợp chúng vào nhánh hiện tại. git rebase trong ví dụ đặt các commit của nhánh đang làm lên trên origin/main; nhóm cũng có thể chọn git merge theo quy ước của dự án. git push gửi các commit cục bộ lên remote để người khác có thể lấy về.

### Ưu điểm và giới hạn

- **Làm việc ngoại tuyến:** có thể xem lịch sử, tạo nhánh, so sánh và commit cục bộ khi không có mạng.
- **Lịch sử có nhiều bản sao:** mỗi clone đầy đủ là một bản sao độc lập của kho. Nếu một máy gặp sự cố, các clone khác vẫn có thể giữ lịch sử và hỗ trợ khôi phục.
- **Phân nhánh linh hoạt:** tạo, chuyển và hợp nhất nhánh cục bộ nhanh, thuận tiện cho việc phát triển nhiều tính năng song song.
- **Nhiều cách cộng tác:** thành viên có thể trao đổi qua remote dùng chung, qua nền tảng review mã hoặc qua các kho trung gian.
- **Cần hiểu rõ đồng bộ:** commit cục bộ chưa tự xuất hiện trên remote. Thành viên phải fetch/pull để nhận thay đổi và push để chia sẻ commit.
- **Quản lý bản sao và quyền truy cập:** lịch sử được sao chép tới nhiều máy. Tổ chức cần quản lý quyền truy cập, bảo vệ thông tin nhạy cảm và chính sách lưu trữ các bản clone phù hợp.

DVCS không bắt buộc phải có một máy chủ trung tâm. Tuy nhiên, nhiều nhóm vẫn chọn một remote dùng chung làm nơi tích hợp chính để thống nhất nhánh phát hành, review và quy trình triển khai.

## So sánh hai mô hình

| Tiêu chí | Tập trung (CVCS) | Phân tán (DVCS) |
|---|---|---|
| Nơi lưu lịch sử chính | Kho trung tâm | Có trong từng kho clone đầy đủ |
| Commit thông thường | Gửi revision lên máy chủ | Ghi commit vào kho cục bộ |
| Làm việc khi ngoại tuyến | Có thể sửa tệp; thường không thể commit vào kho chung | Có thể commit và thao tác với lịch sử cục bộ |
| Trao đổi thay đổi | Chủ yếu qua máy chủ trung tâm | Qua một hoặc nhiều remote/kho khác |
| Phân nhánh | Có thể hỗ trợ; nhánh được quản lý tại kho trung tâm | Nhánh cục bộ nhẹ và linh hoạt |
| Điểm phụ thuộc | Máy chủ trung tâm là điểm quan trọng của quy trình | Không cần máy chủ để commit cục bộ; remote vẫn có thể là điểm tích hợp của nhóm |
| Ví dụ | SVN, Perforce | Git, Mercurial |

Không nên kết luận rằng CVCS luôn lỗi thời hoặc DVCS luôn phù hợp hơn. Lựa chọn phụ thuộc vào cách tổ chức quản lý quyền, loại dữ liệu, quy mô nhóm, yêu cầu ngoại tuyến và quy trình phát hành. Một hệ thống tập trung có thể phù hợp với môi trường cần quản trị chặt; một hệ thống phân tán thường thuận lợi cho nhóm cần nhánh linh hoạt và cộng tác qua nhiều địa điểm.

## Git phân tán nhưng vẫn có thể dùng quy trình tập trung

Đây là điểm quan trọng khi học Git: **kiến trúc phân tán của Git không đồng nghĩa nhóm phải làm việc theo kiểu không có kho trung tâm**. Git cho phép mỗi thành viên có kho đầy đủ, trong khi nhóm vẫn thống nhất một remote, thường được đặt tên origin, làm nơi chia sẻ và tích hợp.

Một quy trình nhóm phổ biến là:

1. Thành viên clone remote dùng chung về máy.
2. Thành viên tạo nhánh riêng cho từng công việc và commit thường xuyên tại máy cục bộ.
3. Trước khi tích hợp, thành viên fetch thay đổi mới từ remote và cập nhật nhánh của mình theo quy ước merge hoặc rebase của nhóm.
4. Thành viên push nhánh lên remote, sau đó tạo yêu cầu review (pull request hoặc merge request) nếu nền tảng của nhóm hỗ trợ.
5. Sau khi được duyệt, thay đổi được merge vào nhánh tích hợp như main.
6. Các thành viên fetch hoặc pull để cập nhật kho cục bộ.

~~~mermaid
flowchart TD
    C[Clone remote] --> B[Tạo nhánh công việc]
    B --> L[Commit cục bộ]
    L --> F[Fetch thay đổi mới]
    F --> I[Merge hoặc rebase]
    I --> P[Push nhánh lên remote]
    P --> R[Review và tích hợp vào main]
    R --> U[Thành viên cập nhật kho cục bộ]
    U --> B
~~~

Trong quy trình này, remote đóng vai trò điểm phối hợp chung. Tuy vậy, mỗi thành viên vẫn có thể commit, xem lịch sử và tạo nhánh mà không cần máy chủ. Đó chính là lợi ích của DVCS được sử dụng trong một quy trình cộng tác có điểm tích hợp tập trung.

### Phân biệt các thao tác Git thường gặp

| Lệnh | Tác dụng chính |
|---|---|
| git clone | Tạo kho cục bộ từ một kho khác và cấu hình remote ban đầu |
| git status | Xem trạng thái working tree và staging area |
| git add | Đưa nội dung thay đổi vào staging area để chuẩn bị commit |
| git commit | Tạo commit trong kho cục bộ |
| git fetch | Lấy commit và tham chiếu mới từ remote; không tự hợp nhất vào nhánh hiện tại |
| git pull | Fetch rồi tích hợp thay đổi vào nhánh hiện tại theo cấu hình hoặc tùy chọn merge/rebase |
| git push | Gửi commit và cập nhật tham chiếu trên remote |
| git log | Xem lịch sử commit |

Vì vậy, “đã commit” và “đã push” là hai trạng thái khác nhau. Một commit có thể tồn tại an toàn trong kho cục bộ nhưng chưa được chia sẻ với nhóm. Trước khi kết luận thay đổi đã có trên remote, hãy kiểm tra trạng thái đồng bộ và nhánh đích.

## Chọn mô hình và áp dụng trong thực tế

Khi đánh giá mô hình quản lý phiên bản, nhóm nên xem xét các câu hỏi sau:

- **Nhóm có cần làm việc ngoại tuyến không?** Nếu thành viên thường xuyên di chuyển hoặc làm việc ở mạng không ổn định, DVCS đem lại lợi thế rõ rệt.
- **Ai cần quyền truy cập vào lịch sử?** CVCS tập trung điểm kiểm soát. Với DVCS, cần tính đến việc lịch sử được sao chép tới các clone và thiết lập chính sách bảo vệ dữ liệu.
- **Nhóm có thường xuyên phát triển song song không?** DVCS như Git hỗ trợ nhánh cục bộ thuận tiện, nhưng vẫn cần quy ước đặt tên nhánh, review và tích hợp.
- **Dự án quản lý loại tệp nào?** Mã nguồn dạng văn bản thường phù hợp với Git. Dự án có nhiều tệp nhị phân lớn hoặc quy trình khóa tệp có thể cần đánh giá thêm công cụ và phần mở rộng phù hợp.
- **Quy trình tích hợp và phát hành ra sao?** Dù dùng mô hình nào, nhóm vẫn cần quy định nơi tích hợp, cách giải quyết xung đột, cách tạo bản phát hành và cách sao lưu.

Với dự án sử dụng Git, nên thống nhất remote chính, nhánh mặc định, quy tắc tạo nhánh, cách cập nhật nhánh, cách review và quyền push vào nhánh quan trọng. Hãy tạo commit có phạm vi rõ ràng, viết thông điệp dễ hiểu, thường xuyên đồng bộ và giải quyết xung đột ngay trong ngữ cảnh của thay đổi. Không đưa mật khẩu, token hoặc khóa bí mật vào lịch sử commit; nếu bí mật đã bị commit và push, cần xử lý như một sự cố lộ thông tin, kể cả khi tệp đã bị xóa ở commit sau.

## Những hiểu lầm thường gặp

- **“GitHub hoặc GitLab là Git.”** Git là hệ thống quản lý phiên bản phân tán. GitHub và GitLab là các nền tảng cung cấp dịch vụ lưu trữ kho, review và cộng tác dựa trên Git.
- **“Có remote nghĩa là hệ thống tập trung.”** Remote chỉ là một kho mà Git có thể trao đổi dữ liệu. Một kho có thể có nhiều remote, và không remote nào là bắt buộc về mặt kiến trúc.
- **“Commit trong Git đã chia sẻ cho cả nhóm.”** Commit được tạo cục bộ; cần push để gửi commit lên remote.
- **“DVCS không có điểm trung tâm.”** DVCS không yêu cầu điểm trung tâm để lưu lịch sử, nhưng nhóm hoàn toàn có thể chọn một remote làm nơi tích hợp chính.
- **“CVCS không có nhánh.”** Nhiều CVCS hỗ trợ nhánh. Cách tạo, lưu và chia sẻ nhánh mới là phần khác nhau giữa các hệ thống.

## Ghi nhớ

CVCS tổ chức lịch sử quanh một kho trung tâm và thường yêu cầu kết nối máy chủ để ghi nhận revision chung. DVCS lưu lịch sử trong các kho clone, cho phép thành viên commit và phát triển độc lập rồi đồng bộ thay đổi khi cần. Git là DVCS; nhóm có thể khai thác tính linh hoạt đó trong quy trình có remote trung tâm, nhánh dùng chung và bước review rõ ràng. Hiểu đúng vị trí của working tree, kho cục bộ, commit và remote là nền tảng để sử dụng Git an toàn và cộng tác hiệu quả.

