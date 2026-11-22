# Kiểm tra bản sao sạch để phát hiện khác biệt môi trường

## Vì sao cần kiểm tra bằng một bản sao sạch?

Khi một lỗi chỉ xuất hiện trên máy của một thành viên, rất dễ kết luận rằng mã nguồn đang có vấn đề. Tuy nhiên, nguyên nhân có thể đến từ trạng thái cục bộ hoặc môi trường chạy: tệp chưa commit, tệp bị ignore, Git config, line ending, submodule chưa khởi tạo, Git LFS chưa tải dữ liệu, phiên bản runtime khác nhau hoặc biến môi trường không giống nhau.

Một **bản sao sạch** (clean clone) là một bản clone mới được lấy từ kho Git và checkout tại đúng commit cần kiểm tra. Bản sao này giúp xác định liệu lỗi có còn xuất hiện khi không mang theo các tệp cục bộ và lịch sử thao tác riêng của working tree hiện tại hay không.

So sánh có giá trị khi hai bên sử dụng cùng một commit. Nếu bản làm việc hiện tại đang ở commit A nhưng bản clone sạch đang ở commit B, kết quả khác nhau chưa thể quy cho môi trường. Vì vậy, hãy ghi nhận mã commit trước, sau đó đưa bản clone sạch về cùng commit và chạy cùng quy trình kiểm tra.

Việc kiểm tra này giúp trả lời ba câu hỏi:

1. Lỗi có xuất hiện trong một checkout sạch của cùng commit không?
2. Nếu chỉ máy hoặc working tree cũ bị lỗi, khác biệt nào đang ảnh hưởng tới kết quả?
3. Nếu cả hai bản sao đều lỗi, vấn đề có nằm trong mã nguồn, dependency hoặc cấu hình được quản lý bởi repository không?

Clean clone là một phép thử chẩn đoán. Nó không tự chứng minh môi trường hoàn toàn giống nhau, vì clone mới vẫn chịu ảnh hưởng của hệ điều hành, Git config toàn cục, credential helper, runtime, công cụ build và dịch vụ bên ngoài.

## Ghi nhận commit và trạng thái của bản làm việc hiện tại

Trước khi tạo bản sao mới, ghi lại repository, nhánh, commit và trạng thái tệp:

~~~bash
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git status --porcelain=v2 --branch
git log -1 --oneline --decorate
~~~

Trong đó:

- git rev-parse --show-toplevel xác định thư mục gốc của repository.
- git branch --show-current cho biết nhánh đang checkout; nếu HEAD detached, kết quả có thể rỗng.
- git rev-parse HEAD ghi lại commit chính xác đang được kiểm tra.
- git status --porcelain=v2 --branch cung cấp trạng thái máy đọc được, gồm thông tin nhánh và thay đổi.
- git log -1 cho biết commit gần nhất cùng nhãn tham chiếu nếu có.

Lưu mã commit đầy đủ để sử dụng ở bước checkout bản sao sạch. Không chỉ ghi tên nhánh, vì nhánh có thể di chuyển khi remote nhận commit mới.

### Xác định working tree có sạch hay không

Kiểm tra các thay đổi chưa stage và đã stage:

~~~bash
git diff --exit-code
git diff --cached --exit-code
~~~

Nếu lệnh trả mã thoát 0, không có khác biệt tương ứng trong các tệp được theo dõi. Nếu trả mã thoát 1, có khác biệt cần xem lại. Mã thoát khác có thể biểu thị lỗi thực thi.

Liệt kê tệp chưa được theo dõi:

~~~bash
git ls-files --others --exclude-standard
~~~

Xem cả các tệp bị ignore:

~~~bash
git status --short --ignored
~~~

Một số tệp không xuất hiện trong diff thông thường vì chúng chưa được Git theo dõi hoặc đang bị ignore. Chúng vẫn có thể làm ứng dụng hoạt động khác, ví dụ file cấu hình máy cá nhân, file generated, cache hoặc dữ liệu test cũ.

Để xem trước các tệp ignored sẽ bị loại bỏ bởi thao tác clean, dùng chế độ dry-run:

~~~bash
git clean -ndX
~~~

Để xem trước tất cả tệp và thư mục chưa được theo dõi có thể bị loại bỏ:

~~~bash
git clean -ndx
~~~

Các lệnh trên chỉ liệt kê dự kiến, không xóa tệp. Không chạy git clean với tùy chọn thực thi trong quá trình chẩn đoán nếu chưa xác định rõ từng đường dẫn và chưa bảo toàn dữ liệu cần thiết.

### Kiểm tra trạng thái đặc biệt của index

Một số cờ index có thể khiến thay đổi tệp không được báo cáo theo cách thông thường. Có thể xem danh sách tệp cùng cờ:

~~~bash
git ls-files -v
~~~

Với chế độ này, chữ cái viết thường có thể cho biết tệp đang mang cờ assume-unchanged. Nếu nghi ngờ skip-worktree hoặc sparse checkout, kiểm tra thêm:

~~~bash
git ls-files -t
git sparse-checkout list
git rev-parse --is-shallow-repository
~~~

Kết quả giúp nhận diện checkout chỉ chứa một phần cây thư mục hoặc clone nông. Một bản làm việc sparse có thể thiếu tệp mà bản clone đầy đủ có, trong khi không có lỗi checkout.

Không tự ý xóa cờ hoặc tắt sparse checkout chỉ để làm trạng thái trông sạch hơn. Hãy ghi nhận cấu hình trước và xác định nó có liên quan tới lỗi hay không.

## Tạo bản clone sạch tại đúng commit

Chọn một thư mục kiểm tra nằm ngoài repository hiện tại để tránh trộn các tệp của hai bản sao. Clone từ đúng remote mà nhóm dùng làm nguồn tích hợp:

~~~bash
git clone <repository-url> clean-check
cd clean-check
~~~

Clone mới thường checkout nhánh mặc định của remote. Để so sánh cùng mã nguồn, chuyển sang đúng commit đã ghi nhận ở bản làm việc ban đầu:

~~~bash
git switch --detach <commit-id>
git rev-parse HEAD
git status --short
~~~

Mã commit in ra phải trùng với mã commit đã ghi nhận. Nếu commit chưa có trong clone, fetch nhánh chứa commit đó rồi checkout lại:

~~~bash
git fetch origin <branch-name>
git switch --detach <commit-id>
~~~

Không dùng tên nhánh thay cho việc xác nhận commit. Nhánh remote có thể đã tiến lên sau thời điểm xảy ra lỗi.

### Nếu commit chỉ tồn tại cục bộ

Một clone từ remote không thể lấy commit chưa được push hoặc chưa được chia sẻ tới remote đó. Trong trường hợp này, có hai lựa chọn:

- Dùng git worktree add để tạo một working tree riêng từ commit cục bộ. Cách này giữ nguyên object database và cấu hình cấp repository của kho gốc, nên phù hợp để kiểm tra khác biệt do working tree.
- Đóng gói commit và các ref cần thiết bằng git bundle, rồi clone bundle sang thư mục khác. Cách này tạo repository riêng hơn, nhưng cần xác định ref nào phải được đưa vào bundle.

Ví dụ tạo worktree sạch từ commit hiện tại:

~~~bash
git worktree add --detach ../clean-check <commit-id>
~~~

Worktree mới có working tree riêng nhưng dùng chung object database và một số cấu hình của repository gốc. Nó không thay thế hoàn toàn phép thử bằng clone độc lập khi đang điều tra khác biệt Git config hoặc cấu hình repository.

Nếu cần kiểm tra chính xác một commit chỉ có trên máy cá nhân bằng clone độc lập, hãy chia sẻ commit theo quy trình của nhóm hoặc tạo bundle có chứa ref cần kiểm tra. Không thay đổi remote dùng chung chỉ để phục vụ phép thử nếu chưa có kế hoạch phù hợp.

### Xác nhận bản clone thực sự sạch

Trong thư mục clean-check:

~~~bash
git rev-parse HEAD
git status --porcelain=v2 --branch
git diff --exit-code
git diff --cached --exit-code
git ls-files --others --exclude-standard
~~~

Mục tiêu là xác nhận:

- HEAD trùng commit cần so sánh.
- Không có thay đổi tracked chưa stage.
- Không có thay đổi tracked đã stage.
- Không có tệp chưa được theo dõi ngoài dự kiến.
- Nhánh đang ở trạng thái mong muốn; nếu checkout detached, điều đó cần được hiểu và ghi nhận.

Một bản clone mới có thể vẫn chứa tệp do hook, filter, LFS hoặc công cụ setup tạo ra. Hãy kiểm tra trạng thái thực tế thay vì chỉ dựa vào tên thư mục clean-check.

## So sánh nội dung repository giữa hai bản sao

Khi hai bản sao ở cùng commit, nội dung Git được lưu trong commit là như nhau. Nếu working tree hiển thị khác biệt, hãy tìm nguyên nhân trong cách Git chuyển đổi nội dung hoặc trong tệp cục bộ.

Ở mỗi bản sao, chạy:

~~~bash
git rev-parse HEAD
git status --short
git diff --stat
git diff --cached --stat
git ls-files --others --exclude-standard
~~~

Nếu cần xác nhận một tệp cụ thể, so sánh working tree với commit:

~~~bash
git diff <commit-id> -- src/config/application.yml
~~~

Nếu diff không có kết quả, nội dung tracked của tệp đó trùng với snapshot commit theo cách Git đang diễn giải. Nếu có khác biệt, đọc nội dung để xác định line ending, filter, chỉnh sửa cục bộ hoặc lỗi phục hồi.

Có thể xem blob mà commit lưu cho một tệp:

~~~bash
git rev-parse <commit-id>:src/config/application.yml
~~~

Mã object này xác định nội dung blob trong Git. Hai bản sao cùng commit và cùng đường dẫn sẽ trỏ tới cùng blob nếu tệp được quản lý bình thường. Khác biệt ở working tree có thể đến từ clean/smudge filter, line ending hoặc nội dung chưa commit.

Không so sánh hash trực tiếp của tệp trên đĩa rồi kết luận repository khác nhau mà chưa xem Git attributes. Git có thể chuyển đổi line ending hoặc áp dụng filter khi checkout.

## Kiểm tra cấu hình Git có thể làm thay đổi checkout

Git có cấu hình ở nhiều cấp: system, global, local trong repository, worktree và command. Hai clone cùng commit có thể nhận cấu hình khác nhau vì máy người dùng hoặc cấu hình repository.

Xem nguồn của các thiết lập quan trọng:

~~~bash
git config --show-origin --get core.autocrlf
git config --show-origin --get core.eol
git config --show-origin --get core.filemode
git config --show-origin --get core.symlinks
git config --show-origin --get core.ignorecase
git config --show-origin --get core.hooksPath
~~~

Một khóa chưa được thiết lập có thể khiến lệnh trả mã thoát 1; điều đó không nhất thiết là lỗi repository. Hãy so sánh các giá trị hiện có và nguồn cấu hình giữa hai môi trường.

Ý nghĩa một số thiết lập:

| Thiết lập | Ảnh hưởng có thể có |
|---|---|
| core.autocrlf | Chuyển đổi line ending khi checkout và đưa nội dung vào index |
| core.eol | Kiểu line ending được dùng trong một số trường hợp checkout |
| core.filemode | Git có nhận biết thay đổi executable bit hay không |
| core.symlinks | Git tạo symbolic link hay checkout thành tệp thường trên một số môi trường |
| core.ignorecase | Cách Git xử lý khác biệt chữ hoa/chữ thường của đường dẫn |
| core.hooksPath | Vị trí chứa hook được thực thi khi chạy một số lệnh Git |

Không sao chép toàn bộ output git config --list vào báo cáo công khai. Cấu hình có thể chứa URL remote, tên người dùng, đường dẫn nội bộ hoặc thông tin nhạy cảm. Chỉ thu thập các khóa cần thiết và che thông tin xác thực trước khi chia sẻ.

### Kiểm tra remote và ref nguồn

Đảm bảo hai bản sao lấy từ cùng repository và đúng nhánh nguồn. Khi xem URL remote, kiểm tra host và đường dẫn repository; nếu URL chứa credential, phải che phần đó trước khi ghi log.

~~~bash
git remote -v
git branch -avv
git show-ref --heads --tags
~~~

Remote-tracking branch là thông tin lần fetch gần nhất. Nếu cần so sánh với trạng thái mới nhất của server, chạy fetch trước và ghi lại thời điểm kiểm tra. Không so sánh một bản sao đã fetch với một bản sao chưa fetch rồi kết luận chúng đang dùng cùng trạng thái remote.

## Kiểm tra line ending và Git attributes

Khác biệt giữa Windows, Linux và macOS có thể làm line ending trở thành nguồn gây nhiễu. Repository nên quy định chính sách phù hợp trong .gitattributes, ví dụ:

~~~text
* text=auto
*.sh text eol=lf
*.bat text eol=crlf
*.java text
~~~

Đây chỉ là ví dụ. Chính sách thực tế phụ thuộc công cụ và định dạng tệp của dự án.

Xem attributes được áp dụng cho một đường dẫn:

~~~bash
git check-attr -a -- src/Main.java
git check-attr text eol -- scripts/build.sh
~~~

Đọc cấu hình line ending:

~~~bash
git config --show-origin --get core.autocrlf
git config --show-origin --get core.eol
~~~

Nếu một máy checkout CRLF còn máy kia checkout LF, nội dung tệp trên đĩa có thể khác nhưng Git vẫn chuẩn hóa nội dung theo attributes khi so sánh và commit. Hãy kiểm tra .gitattributes, cấu hình Git và diff trước khi thay đổi chính sách.

Không chạy git add --renormalize . một cách tùy tiện trong lúc điều tra. Lệnh này có thể tạo thay đổi hàng loạt trong index; chỉ dùng khi nhóm đã quyết định chuẩn hóa line ending và có kế hoạch review riêng.

### Kiểm tra filter và Git LFS

Một số repository dùng filter để biến đổi nội dung khi checkout hoặc stage. Git LFS là ví dụ phổ biến: Git lưu pointer trong repository, còn nội dung tệp lớn được tải từ LFS server.

Kiểm tra attributes và filter:

~~~bash
git check-attr -a -- path/to/large-file.bin
git lfs version
git lfs ls-files
git lfs status
~~~

Nếu dự án dùng LFS, clone sạch cần có Git LFS và quyền truy cập LFS server. Sau khi clone, có thể cần lấy nội dung theo hướng dẫn dự án:

~~~bash
git lfs pull
~~~

Nếu một máy có nội dung thực còn máy khác chỉ có pointer, ứng dụng có thể cho kết quả khác dù hai bản sao đang ở cùng commit. Kiểm tra trạng thái LFS và log tải file trước khi kết luận mã nguồn bị sai.

Filter tùy chỉnh cũng có thể phụ thuộc chương trình ngoài, phiên bản công cụ hoặc biến môi trường. So sánh cấu hình filter và phiên bản chương trình giữa hai máy.

## Kiểm tra submodule và sparse checkout

Submodule là repository lồng bên trong repository chính. Commit của repository chính chỉ ghi nhận mã commit mà submodule cần trỏ tới; clone mới có thể chưa tải nội dung submodule.

Xem trạng thái:

~~~bash
git submodule status --recursive
~~~

Các ký hiệu đầu dòng thường giúp nhận biết trạng thái:

- Dấu cách: submodule đang ở commit được repository chính yêu cầu.
- Dấu trừ: submodule chưa được khởi tạo.
- Dấu cộng: submodule đang checkout ở commit khác commit được ghi trong repository chính.
- Chữ U: submodule có xung đột chưa được giải quyết.

Khởi tạo và checkout đúng commit đã ghi nhận:

~~~bash
git submodule update --init --recursive
git submodule status --recursive
~~~

Nếu submodule cần quyền truy cập riêng, xác minh credential và URL trong .gitmodules. Không nhúng token vào URL hoặc báo cáo.

Sparse checkout chỉ lấy một phần cây thư mục. Kiểm tra:

~~~bash
git sparse-checkout list
git config --show-origin --get core.sparseCheckout
~~~

Một bản clone sạch đầy đủ có thể chứa tệp mà working tree sparse không có. Nếu lỗi chỉ xuất hiện khi thiếu một thư mục, xác nhận cấu hình sparse checkout trước khi điều tra logic ứng dụng.

## So sánh hệ điều hành, runtime và công cụ build

Khi commit và Git configuration đã được đối chiếu, kiểm tra các thành phần bên ngoài repository.

Tùy dự án, có thể ghi nhận:

~~~bash
git --version
java -version
./gradlew --version
node --version
npm --version
python --version
~~~

Chỉ chạy các lệnh liên quan tới stack của dự án. Một dự án Java không cần kiểm tra Node nếu Node không tham gia build hoặc frontend.

So sánh các thông tin sau:

| Thành phần | Khác biệt cần xem xét |
|---|---|
| Hệ điều hành | Windows, Linux, macOS và phiên bản hệ điều hành |
| Git | Phiên bản Git, cấu hình và filter |
| Runtime | JDK, Node.js, Python, .NET hoặc runtime thực tế |
| Build tool | Gradle, Maven, npm, pnpm, pip, dotnet và phiên bản |
| Dependency | Lockfile, dependency cache và nguồn tải |
| Shell | PowerShell, CMD, Bash hoặc shell script khác |
| Locale | Encoding, locale, định dạng số và ngày giờ |
| Timezone | Quy tắc chuyển đổi thời gian và test phụ thuộc múi giờ |
| Filesystem | Chữ hoa/thường, symlink, quyền thực thi và giới hạn đường dẫn |
| Container | Image tag hoặc digest, kiến trúc CPU và cấu hình mount |

Nếu dự án có wrapper như Gradle Wrapper hoặc Maven Wrapper, ưu tiên dùng wrapper đã được commit để giảm khác biệt phiên bản công cụ. Wrapper vẫn phụ thuộc JDK, mạng, cấu hình proxy và dependency repository.

### Kiểm tra biến môi trường một cách có chọn lọc

Biến môi trường có thể làm ứng dụng kết nối tới database khác, bật profile khác hoặc thay đổi hành vi test.

Hãy xác định danh sách biến mà ứng dụng thực sự sử dụng, ví dụ:

- APP_ENV hoặc SPRING_PROFILES_ACTIVE.
- TZ hoặc locale mà ứng dụng dựa vào.
- JAVA_HOME hoặc đường dẫn runtime.
- URL dịch vụ phụ thuộc trong môi trường kiểm thử.
- Biến cấu hình feature flag không chứa bí mật.

Không in toàn bộ môi trường bằng env, set hoặc Get-ChildItem Env: vào log chia sẻ. Những lệnh này có thể làm lộ token, password, API key và thông tin xác thực. Chỉ kiểm tra tên biến cần thiết, che giá trị nhạy cảm và so sánh profile hoặc trạng thái đã được chuẩn hóa.

### Kiểm tra file cấu hình cục bộ

Một file .env, application-local.yml hoặc file cấu hình trong thư mục ignored có thể tồn tại trên máy cũ nhưng không có trong clone sạch. Đây là nguyên nhân phổ biến khiến hai máy chạy cùng commit nhưng kết quả khác nhau.

Xác định các file cấu hình được dự án hỗ trợ, so sánh tên khóa và profile mà không sao chép secret. Dùng file mẫu như .env.example hoặc application-example.yml nếu dự án cung cấp. Tạo cấu hình cục bộ từ mẫu theo hướng dẫn dự án và lấy secret từ secret manager hoặc cơ chế cấp phát phù hợp.

Không commit file cấu hình chứa credential chỉ để làm cho clean clone chạy giống máy cá nhân.

## Chạy cùng quy trình kiểm tra trên hai bản sao

Sau khi đã checkout cùng commit và chuẩn bị các dependency cần thiết, chạy cùng một chuỗi lệnh build/test ở cả hai bản sao.

Ví dụ minh họa cho dự án Java dùng Gradle Wrapper:

~~~bash
./gradlew clean test
~~~

Nếu dự án dùng Maven Wrapper:

~~~bash
./mvnw clean verify
~~~

Chọn đúng lệnh theo tài liệu của repository. Không giả định cả hai lệnh đều cần chạy.

Ghi nhận cho mỗi lần chạy:

- Commit đầy đủ.
- Nhánh hoặc trạng thái detached HEAD.
- Hệ điều hành và phiên bản Git.
- Runtime và build tool.
- Trạng thái submodule và LFS.
- Profile hoặc nhóm biến môi trường đã dùng, không ghi secret.
- Lệnh build/test và mã thoát.
- Test nào PASS, FAIL, bị bỏ qua hoặc chưa chạy.

Nếu bản làm việc hiện tại thất bại nhưng clone sạch thành công, hãy kiểm tra khác biệt trong working tree, ignored files, local config, cache, hook, index flags và toolchain. Nếu cả hai cùng thất bại, tập trung vào commit, dependency, cấu hình được quản lý trong repository hoặc dịch vụ phụ thuộc.

Nếu clone sạch thất bại nhưng bản cũ thành công, kiểm tra file cục bộ còn thiếu, secret chưa được cấp, submodule/LFS, hook không được cài, dependency cache hoặc bước bootstrap môi trường.

## Đọc kết quả so sánh để khoanh vùng nguyên nhân

Bảng sau giúp chọn hướng điều tra tiếp theo:

| Kết quả | Nhóm nguyên nhân nên kiểm tra |
|---|---|
| Bản cũ lỗi, clone sạch cùng commit chạy được | Thay đổi cục bộ, ignored file, cache, index flag, Git config hoặc hook |
| Cả hai cùng lỗi ở cùng test | Mã nguồn, dependency, cấu hình đã commit hoặc dịch vụ phụ thuộc |
| Bản cũ chạy được, clone sạch lỗi | Thiếu file cấu hình local, secret, submodule, LFS hoặc bước setup |
| Cùng commit nhưng diff tracked khác nhau | Line ending, attributes, filter, symlink hoặc chỉnh sửa cục bộ |
| HEAD khác nhau | Chưa so sánh cùng snapshot; fetch hoặc checkout đúng commit |
| Build khác nhau dù diff sạch | Runtime, build tool, environment variable, locale, timezone hoặc cache |
| Chỉ CI khác kết quả | Image, runner, secret, service, kiến trúc hoặc cấu hình CI |

Đây là các hướng kiểm tra, không phải kết luận tự động. Hãy thay đổi từng yếu tố một nếu có thể để biết yếu tố nào làm kết quả thay đổi.

## Kiểm tra cache và trạng thái sinh tự động

Build tool thường lưu cache bên ngoài repository hoặc trong thư mục bị ignore. Cache cũ có thể che giấu dependency bị thiếu hoặc làm build khác giữa hai máy.

Một số ví dụ:

- Gradle cache trong thư mục người dùng.
- Maven local repository.
- npm, pnpm hoặc Yarn cache.
- Python virtual environment và package cache.
- Build output như build/, target/, dist/ hoặc out/.

Clone sạch không nhất thiết có cache rỗng ở cấp người dùng. Nếu muốn kiểm tra ảnh hưởng cache, sử dụng cơ chế clean hoặc cache directory riêng của build tool theo hướng dẫn dự án. Ghi lại thay đổi cấu hình và kết quả; tránh xóa cache toàn máy khi chưa biết các dự án khác có đang dùng nó hay không.

Phân biệt lệnh clean của build tool với git clean. Build clean thường xóa output do công cụ tạo ra; git clean có thể xóa tệp chưa được theo dõi trong repository. Chúng có phạm vi và rủi ro khác nhau.

## Tạo bản sao sạch có thể lặp lại

Để nhóm có thể tái hiện lỗi, hãy chuẩn hóa quy trình:

1. Chọn repository nguồn và commit đầy đủ.
2. Tạo clone mới ở thư mục kiểm tra.
3. Checkout detached tại đúng commit.
4. Khởi tạo submodule và tải LFS nếu dự án sử dụng.
5. Cài runtime và dependency theo wrapper hoặc lockfile.
6. Tạo cấu hình môi trường từ file mẫu và secret manager.
7. Chạy cùng lệnh test/build.
8. Ghi nhận kết quả và môi trường.
9. Giữ lại log cần thiết, loại bỏ credential và dữ liệu nhạy cảm.
10. Xóa bản sao kiểm tra khi không còn cần thiết theo chính sách lưu trữ của nhóm.

Có thể dùng một tên thư mục chứa mã commit để tránh nhầm các lần kiểm tra:

~~~text
clean-check-4a5b6c7/
clean-check-8d9e0f1/
~~~

Không nên dùng lại một thư mục clone cũ mà không kiểm tra trạng thái, vì nó có thể đã phát sinh tệp generated, thay đổi cục bộ hoặc cấu hình khác từ lần kiểm tra trước.

### Ví dụ quy trình từ đầu đến cuối

Giả sử bản làm việc hiện tại có lỗi khi chạy test xuất báo cáo. Nhóm muốn kiểm tra xem lỗi có đến từ tệp cấu hình cục bộ hay không.

Ở repository ban đầu:

~~~bash
git rev-parse HEAD
git status --porcelain=v2 --branch
git diff --exit-code
git diff --cached --exit-code
git ls-files --others --exclude-standard
~~~

Ghi lại commit, sau đó tạo clone mới từ remote:

~~~bash
git clone <repository-url> clean-check
cd clean-check
git switch --detach <commit-id>
git rev-parse HEAD
git status --short
~~~

Nếu dự án dùng submodule hoặc LFS:

~~~bash
git submodule update --init --recursive
git submodule status --recursive
git lfs pull
~~~

Chuẩn bị runtime, cấu hình và dependency theo hướng dẫn dự án. Sau đó chạy cùng lệnh test như ở bản làm việc ban đầu:

~~~bash
./gradlew clean test
~~~

Ghi nhận kết quả và so sánh với lần chạy trước. Nếu clean clone chạy thành công, kiểm tra các file ignored và cấu hình local trong bản cũ. Nếu clean clone cũng thất bại, kiểm tra test, dependency, cấu hình được commit và dịch vụ bên ngoài.

Ví dụ này dùng Gradle để minh họa. Hãy thay lệnh bằng quy trình build/test thực tế của repository.

## Báo cáo kết quả kiểm tra

Một báo cáo có thể ngắn nhưng cần đủ dữ liệu để người khác lặp lại:

| Trường | Ví dụ nội dung |
|---|---|
| Repository | Tên repository và remote đã che credential |
| Commit | SHA đầy đủ của commit được kiểm tra |
| Bản sao | Working tree hiện tại hoặc clean clone |
| Git | Phiên bản Git và cấu hình liên quan |
| Môi trường | OS, runtime, build tool |
| Thành phần phụ | Trạng thái submodule và LFS |
| Cấu hình | Profile và tên biến môi trường cần thiết |
| Lệnh | Build/test thực tế đã chạy |
| Kết quả | PASS, FAIL, BLOCKED hoặc chưa chạy |
| Khác biệt | Những yếu tố đã xác định giữa hai bản sao |

Nếu lỗi chỉ xuất hiện ở bản làm việc cũ, nêu rõ khác biệt đã xác nhận bằng bằng chứng như diff, file ignored, cấu hình Git hoặc phiên bản runtime. Nếu chưa tìm ra nguyên nhân, ghi các giả thuyết và bước kiểm tra tiếp theo thay vì khẳng định môi trường là nguyên nhân.

## Những hiểu lầm thường gặp

- **“Clone mới luôn có môi trường sạch hoàn toàn.”** Clone mới có working tree và cấu hình repository mới, nhưng vẫn dùng Git config toàn cục, runtime, cache người dùng, credential và dịch vụ của máy.
- **“Cùng tên nhánh nghĩa là cùng mã nguồn.”** Nhánh có thể trỏ tới commit khác nhau. Hãy so sánh SHA đầy đủ.
- **“git status sạch nghĩa là không có file ảnh hưởng.”** Tệp ignored, biến môi trường và dữ liệu bên ngoài vẫn có thể ảnh hưởng tới ứng dụng.
- **“Khác line ending luôn là khác commit.”** Attributes và cấu hình Git có thể chuẩn hóa line ending; hãy xem diff và check-attr.
- **“Clone sạch tự tải mọi nội dung phụ.”** Submodule và Git LFS có thể cần bước khởi tạo hoặc tải riêng.
- **“Build thành công trên máy cũ chứng minh clone sạch cũng sẽ chạy.”** Máy cũ có thể đang phụ thuộc vào file local, cache hoặc secret chưa được khai báo trong quy trình setup.

## Checklist trước khi kết luận khác biệt môi trường

- [ ] Đã ghi lại commit đầy đủ của bản làm việc ban đầu.
- [ ] Bản clone sạch đã checkout đúng cùng commit.
- [ ] Đã xác nhận trạng thái working tree và staging area.
- [ ] Đã kiểm tra untracked, ignored và cờ index đặc biệt.
- [ ] Đã đối chiếu remote và trạng thái fetch.
- [ ] Đã kiểm tra Git config liên quan cùng nguồn cấu hình.
- [ ] Đã kiểm tra line ending, attributes và filter.
- [ ] Đã xác nhận submodule và LFS ở đúng trạng thái.
- [ ] Đã so sánh hệ điều hành, runtime và build tool.
- [ ] Đã chuẩn bị cùng profile và cấu hình môi trường mà không lộ secret.
- [ ] Đã chạy cùng lệnh build/test trên hai bản sao.
- [ ] Đã ghi nhận kết quả và bằng chứng có thể lặp lại.

## Ghi nhớ

Để phát hiện khác biệt môi trường, hãy tạo một clone mới và checkout đúng commit đang gây lỗi. So sánh trạng thái tệp, index, ignored files, Git config, attributes, submodule, LFS và toolchain; sau đó chạy cùng lệnh build/test với cấu hình tương đương. Nếu clone sạch chạy được còn bản cũ lỗi, tập trung vào trạng thái cục bộ và cấu hình riêng của máy. Nếu cả hai cùng lỗi, điều tra commit, dependency và dịch vụ liên quan. Một kết luận tốt phải dựa trên cùng commit, cùng quy trình kiểm tra và các khác biệt đã được ghi nhận rõ ràng.

