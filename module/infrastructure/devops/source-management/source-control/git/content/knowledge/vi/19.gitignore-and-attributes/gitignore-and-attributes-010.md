# Thuộc tính export-ignore, export-subst và nội dung bản xuất

Git không chỉ lưu lịch sử mã nguồn. Git còn có thể tạo một bản xuất dạng archive từ một commit hoặc tag bằng lệnh **git archive**. Bản xuất này thường được dùng làm gói mã nguồn để tải xuống, làm đầu vào cho một quy trình đóng gói hoặc cung cấp cho người dùng không cần clone repository.

File **.gitattributes** cho phép điều khiển nội dung archive bằng hai thuộc tính quan trọng:

- **export-ignore:** loại những đường dẫn được chỉ định khỏi archive.
- **export-subst:** thay các placeholder **$Format:...$** trong nội dung file bằng thông tin của commit đang được xuất.

Hai thuộc tính này chỉ tác động đến cách Git tạo bản xuất. Chúng không xóa file khỏi repository, không thay đổi working tree và không thay thế cơ chế bảo mật hay quy trình build artifact.

## 1. git archive tạo ra bản xuất như thế nào?

git archive tạo archive từ một tree-ish, thường là commit, branch hoặc tag. Nội dung được lấy từ snapshot đã lưu trong Git tại mốc đó.

Ví dụ, tạo file tar từ tag v1.2.0:

~~~sh
git archive --format=tar --prefix=app-v1.2.0/ -o app-v1.2.0.tar v1.2.0
~~~

Tạo file ZIP:

~~~sh
git archive --format=zip --prefix=app-v1.2.0/ -o app-v1.2.0.zip v1.2.0
~~~

Trong đó:

- --format=tar hoặc --format=zip chọn định dạng archive.
- --prefix=app-v1.2.0/ đặt các file bên trong một thư mục gốc có tên nhất quán.
- -o chỉ định file đầu ra.
- v1.2.0 là tag được dùng làm mốc nội dung.

Nếu không chỉ định --prefix, các đường dẫn trong archive bắt đầu từ thư mục gốc của tree được xuất. Dùng tag cụ thể giúp mọi lần tạo lại archive đều lấy cùng một mốc mã nguồn, miễn tag đó được giữ nguyên.

git archive chỉ xuất nội dung được lưu trong tree của commit. File chưa được theo dõi hoặc thay đổi chưa commit trong working tree không tự xuất hiện trong archive. Archive cũng không phải một bản clone đầy đủ: nó không mang theo toàn bộ lịch sử commit và metadata quản lý repository như thư mục .git.

## 2. .gitattributes điều khiển nội dung archive

.gitattributes là file cấu hình thuộc tính cho từng đường dẫn trong repository. Mỗi dòng thường có dạng:

~~~text
<pattern> <attribute> <attribute> ...
~~~

Ví dụ:

~~~gitattributes
/.gitattributes export-ignore
/.gitignore export-ignore
/tests/** export-ignore
/docs/internal/** export-ignore
VERSION export-subst
~~~

Trong ví dụ này:

- /.gitattributes export-ignore loại file .gitattributes ở thư mục gốc khỏi archive.
- /.gitignore export-ignore loại file .gitignore ở thư mục gốc khỏi archive.
- /tests/** export-ignore loại các file bên dưới thư mục tests khỏi archive.
- /docs/internal/** export-ignore loại các file bên dưới docs/internal khỏi archive.
- VERSION export-subst cho phép thay placeholder trong file VERSION khi tạo archive.

Các dòng trên là ví dụ về chính sách đóng gói. Không phải dự án nào cũng nên loại tài liệu hoặc test; chỉ đặt export-ignore cho nội dung mà người nhận gói xuất thực sự không cần.

### 2.1. Phạm vi của pattern

Pattern trong .gitattributes được so khớp với đường dẫn tương đối từ thư mục chứa file .gitattributes.

- Pattern có dấu / được so khớp theo đường dẫn tương đối đó.
- Pattern không có dấu / thường được so khớp theo tên thành phần đường dẫn ở các cấp bên dưới.
- Dấu / ở đầu pattern giúp neo đường dẫn vào thư mục chứa .gitattributes.
- Wildcard như *, ? và cú pháp ** có thể dùng để mô tả nhiều đường dẫn.

Ví dụ, .gitattributes ở thư mục gốc:

~~~gitattributes
/LICENSE export-ignore
/docs/drafts/** export-ignore
*.tmp export-ignore
~~~

/LICENSE chỉ nhắm tới file LICENSE ở gốc. *.tmp có thể áp dụng cho các file có tên kết thúc bằng .tmp ở nhiều thư mục con. Nếu đặt .gitattributes trong một thư mục con, các pattern trong file đó được xét tương đối với thư mục con ấy.

Pattern của .gitattributes có một số khác biệt với .gitignore. Không dùng dòng phủ định bắt đầu bằng ! để đảo ngược pattern. Ký hiệu ! trong cú pháp giá trị attribute có ý nghĩa khác: nó đặt attribute về trạng thái unspecified.

### 2.2. Thuộc tính có thể được đặt, bỏ hoặc để unspecified

Git hỗ trợ các dạng gán thuộc tính:

| Cú pháp | Ý nghĩa |
|---|---|
| attr | Đặt attribute |
| -attr | Bỏ attribute |
| !attr | Đặt attribute về trạng thái unspecified |
| attr=value | Gán giá trị cho attribute |

Với hai thuộc tính đang học, cách dùng thông thường là đặt export-ignore hoặc export-subst:

~~~gitattributes
/tests/** export-ignore
VERSION export-subst
~~~

Nếu một quy tắc ở phạm vi rộng đặt attribute nhưng một quy tắc cụ thể hơn cần bỏ nó, có thể dùng:

~~~gitattributes
*.md export-ignore
/README.md -export-ignore
~~~

Khi đó, README ở gốc không mang attribute export-ignore, còn các file Markdown khác vẫn có thể bị loại theo quy tắc rộng. Hãy kiểm tra bằng git check-attr thay vì suy đoán kết quả pattern.

### 2.3. Thứ tự ưu tiên của file attributes

Git có thể đọc thuộc tính từ nhiều nơi. Thứ tự ưu tiên từ cao xuống thấp thường là:

1. $GIT_DIR/info/attributes của repository hiện tại.
2. File .gitattributes trong thư mục chứa đường dẫn và các thư mục cha; file ở thư mục gần đường dẫn hơn có ưu tiên cao hơn.
3. File attributes toàn cục được cấu hình qua core.attributesFile.
4. File attributes cấp hệ thống.

Trong cùng một file, quy tắc khớp ở dòng sau có thể ghi đè giá trị của cùng attribute từ dòng trước. Các attribute khác nhau vẫn được xử lý độc lập.

Với archive từ một commit hoặc tag, Git dùng các file .gitattributes thuộc snapshot được xuất. Vì thế, một tag cũ có thể có quy tắc export khác với branch hiện tại. Tùy chọn --worktree-attributes yêu cầu Git dùng các file .gitattributes trong working tree thay vì phiên bản trong tree được xuất. Tùy chọn này hữu ích khi thử nghiệm quy tắc local, nhưng nếu muốn tạo bản xuất có thể tái lập từ tag, nên commit quy tắc vào đúng mốc phát hành.

## 3. export-ignore: loại file khỏi archive

export-ignore cho Git biết rằng đường dẫn được đánh dấu không nên xuất hiện trong archive được tạo bởi git archive.

Một dự án có thể muốn giữ test, tài liệu nội bộ, cấu hình phát triển hoặc file hỗ trợ đóng góp trong repository nhưng không đưa chúng vào gói mã nguồn dành cho người dùng cuối.

Ví dụ .gitattributes:

~~~gitattributes
/tests/** export-ignore
/docs/internal/** export-ignore
/.github/** export-ignore
~~~

Sau khi commit file .gitattributes, tạo archive:

~~~sh
git archive --format=tar --prefix=app-v1.2.0/ -o app-v1.2.0.tar v1.2.0
~~~

Các đường dẫn khớp với export-ignore sẽ không có trong archive. Chúng vẫn tồn tại trong repository, vẫn xuất hiện khi clone và vẫn có thể được truy cập qua lịch sử Git.

### 3.1. Những nội dung thường cân nhắc loại khỏi bản xuất

Tùy mục đích gói mã nguồn, có thể cân nhắc:

- Test chỉ phục vụ phát triển nội bộ, nếu người nhận không cần chạy chúng.
- Tài liệu nội bộ không dành cho người dùng gói.
- Cấu hình CI hoặc script hỗ trợ đóng góp không cần thiết trong gói phân phối.
- File mẫu, ghi chú hoặc dữ liệu phát triển chỉ phục vụ nhóm.

Không nên loại một cách máy móc mọi thư mục tests, docs hoặc .github. Một số thư viện cần phân phối test để downstream package có thể tự xác minh; một số sản phẩm cần tài liệu offline hoặc script build để người dùng tự đóng gói.

### 3.2. export-ignore không phải cơ chế bảo vệ bí mật

Đây là giới hạn quan trọng. export-ignore chỉ điều khiển archive được tạo bằng git archive. Nó không:

- Xóa file khỏi Git.
- Ngăn người có quyền clone repository đọc file.
- Xóa nội dung nhạy cảm khỏi commit cũ.
- Ngăn file xuất hiện trong pull request, fork hoặc bản sao repository.
- Thay thế phân quyền, secret manager hoặc quy trình xử lý sự cố lộ bí mật.

Không commit mật khẩu, token, private key hoặc dữ liệu nhạy cảm rồi trông chờ export-ignore che giấu chúng. Nếu bí mật đã vào lịch sử Git, cần thu hồi hoặc xoay vòng bí mật và xử lý lịch sử theo quy trình bảo mật của dự án.

## 4. export-subst: thay placeholder khi xuất

export-subst cho phép Git thay thế các chuỗi placeholder dạng $Format:...$ trong file khi chạy git archive.

Thuộc tính này hữu ích khi gói mã nguồn cần chứa thông tin nhận diện phiên bản hoặc commit mà không phải sửa file trong working tree trước khi tạo archive.

### 4.1. Khai báo thuộc tính

Trong .gitattributes, đánh dấu file cần thay thế:

~~~gitattributes
VERSION export-subst
~~~

Trong file VERSION, đặt placeholder:

~~~text
Version: $Format:%H$
Short commit: $Format:%h$
Subject: $Format:%s$
~~~

Các placeholder dùng định dạng pretty format mà Git hỗ trợ. Ví dụ:

- %H: mã SHA đầy đủ của commit.
- %h: mã SHA rút gọn.
- %s: subject của commit.
- %an: tên tác giả.

Nên chỉ đưa thông tin cần thiết vào file xuất. Tránh đưa thông tin cá nhân hoặc metadata nội bộ vào gói phát hành nếu người nhận không cần.

### 4.2. Tạo archive để thay thế placeholder

Sau khi .gitattributes và VERSION đã được commit, tạo archive từ một tag:

~~~sh
git archive --format=tar --prefix=app-v1.2.0/ -o app-v1.2.0.tar v1.2.0
~~~

Trong archive, nội dung VERSION sẽ được thay placeholder bằng thông tin của commit mà tag v1.2.0 phân giải tới. File VERSION trong repository không bị sửa; khi checkout tag hoặc xem file trong working tree, placeholder vẫn còn nguyên.

Có thể kiểm tra nội dung file được xuất bằng tar:

~~~sh
git archive --format=tar v1.2.0 | tar -xOf - VERSION
~~~

Kết quả sẽ hiển thị các giá trị đã được thay thế. Nếu dùng prefix khi tạo archive, tên đường dẫn cần truyền cho tar -xOf phải bao gồm prefix đó.

### 4.3. Chỉ thay thế khi có attribute

Chỉ viết $Format:%H$ vào file là chưa đủ. File phải có attribute export-subst tại mốc được archive.

Nếu file .gitattributes ở tag không chứa quy tắc này, Git sẽ giữ nguyên placeholder trong archive. Đây là lý do cần kiểm tra cả nội dung file và thuộc tính ở đúng tag đang phát hành.

export-subst chỉ áp dụng cho quá trình git archive. Nó không thay nội dung khi:

- Checkout branch hoặc tag.
- Clone repository.
- Xem file bằng git show.
- Tạo commit thông thường.
- Chạy ứng dụng trực tiếp từ working tree.

Nếu ứng dụng cần đọc version trong lúc chạy ở môi trường phát triển, hãy cung cấp cơ chế tạo metadata riêng cho build; đừng giả định placeholder luôn được thay ngoài archive.

## 5. Kết hợp export-ignore và export-subst

Hai thuộc tính có thể cùng được dùng trong một dự án:

~~~gitattributes
/.gitattributes export-ignore
/.gitignore export-ignore
/tests/** export-ignore
/docs/internal/** export-ignore
VERSION export-subst
~~~

Chính sách này tạo ra một archive có thể phân phối:

- Bỏ các file cấu hình Git và nội dung phát triển không cần thiết.
- Loại test và tài liệu nội bộ theo chính sách dự án.
- Giữ file VERSION nhưng thay placeholder bằng thông tin commit.

Hãy nhớ .gitattributes được dùng để quyết định archive, vì vậy nếu đánh dấu chính nó bằng export-ignore, quy tắc vẫn được Git đọc trước khi loại file khỏi kết quả. Việc không có file .gitattributes trong archive không làm mất tác dụng của các quy tắc đã dùng để tạo archive đó.

## 6. Ví dụ thực hành từ cấu hình đến archive

Giả sử dự án store-service muốn phát hành gói mã nguồn v2.3.0. Nhóm muốn giữ test và tài liệu nội bộ trong repository nhưng bỏ chúng khỏi archive phân phối, đồng thời ghi commit SHA vào file VERSION.

### Bước 1: Tạo file .gitattributes

~~~gitattributes
/.gitattributes export-ignore
/.gitignore export-ignore
/tests/** export-ignore
/docs/internal/** export-ignore
VERSION export-subst
~~~

### Bước 2: Tạo file VERSION

~~~text
Release: $Format:%h$
Commit: $Format:%H$
Subject: $Format:%s$
~~~

### Bước 3: Commit quy tắc và file version

~~~sh
git add .gitattributes VERSION
git commit -m "Configure source archive metadata"
~~~

### Bước 4: Tích hợp và tạo tag phát hành

Sau khi thay đổi đã được review, kiểm thử và tích hợp vào branch phát hành, tạo annotated tag:

~~~sh
git tag -a v2.3.0 -m "Release store-service 2.3.0"
git show --no-patch --decorate v2.3.0
git rev-parse "v2.3.0^{commit}"
~~~

### Bước 5: Tạo archive

~~~sh
git archive --format=tar --prefix=store-service-2.3.0/ -o store-service-2.3.0.tar v2.3.0
git archive --format=zip --prefix=store-service-2.3.0/ -o store-service-2.3.0.zip v2.3.0
~~~

### Bước 6: Kiểm tra nội dung

Liệt kê file trong tar:

~~~sh
tar -tf store-service-2.3.0.tar
~~~

Kiểm tra VERSION đã được thay:

~~~sh
tar -xOf store-service-2.3.0.tar store-service-2.3.0/VERSION
~~~

Kiểm tra test và tài liệu nội bộ đã được loại khỏi archive bằng cách xem danh sách file:

~~~sh
tar -tf store-service-2.3.0.tar
~~~

Đối chiếu danh sách với chính sách đóng gói đã thống nhất. Không chỉ kiểm tra một file VERSION; hãy xác nhận những đường dẫn cần giữ và cần loại đều đúng.

### Bước 7: Lưu thông tin phát hành

Ghi nhận:

- Tag v2.3.0.
- Commit SHA mà tag trỏ tới.
- Tên và checksum của archive.
- Kết quả kiểm tra nội dung archive.
- Release note và các artifact khác nếu có.

Archive được tạo từ tag giúp nhóm có thể tái tạo nội dung theo cùng một mốc Git. Để bảo đảm artifact có thể xác minh, pipeline phát hành nên ghi checksum và lưu lại môi trường hoặc công cụ đóng gói cần thiết.

## 7. Kiểm tra attributes trước khi phát hành

Khi archive thiếu file hoặc placeholder chưa được thay, hãy kiểm tra thuộc tính trước.

### 7.1. Dùng git check-attr

Kiểm tra thuộc tính trên file trong working tree:

~~~sh
git check-attr export-ignore export-subst -- tests/example.test.ts VERSION
~~~

Kết quả cho biết mỗi attribute đang ở trạng thái set, unset, unspecified hoặc có giá trị cụ thể. Ví dụ, VERSION cần có export-subst: set; file test được cấu hình loại khỏi archive cần có export-ignore: set.

Có thể xem toàn bộ attribute áp dụng cho một đường dẫn:

~~~sh
git check-attr --all -- VERSION
~~~

Nếu cần kiểm tra nội dung .gitattributes tại một tag cụ thể, xem file từ tag đó:

~~~sh
git show v2.3.0:.gitattributes
~~~

git check-attr mặc định kiểm tra theo ngữ cảnh hiện tại. Khi cần kiểm tra chính xác archive của tag cũ, hãy tạo archive từ tag đó và xác minh trực tiếp đầu ra; không suy luận chỉ từ .gitattributes đang có trong working tree.

### 7.2. Dùng --worktree-attributes khi thử nghiệm local

Mặc định, Git dùng attributes trong tree đang được xuất. Nếu bạn vừa chỉnh .gitattributes trong working tree nhưng chưa commit và muốn thử quy tắc local, có thể chạy:

~~~sh
git archive --worktree-attributes --format=tar HEAD
~~~

Kết quả lúc này có thể khác archive được tạo từ tag hoặc commit trên remote. Không dùng tùy chọn này cho bản phát hành cần tái lập từ tag nếu quy tắc chưa được commit vào tag đó.

### 7.3. So sánh archive với snapshot nguồn

Khi kiểm tra gói, hãy xác nhận:

- File ứng dụng cần thiết vẫn có trong archive.
- File bị đánh dấu export-ignore đã vắng mặt.
- File có export-subst chứa thông tin commit đúng.
- Không có file tạm, dữ liệu cá nhân hoặc cấu hình máy phát triển bị đưa vào.
- Archive có prefix và cấu trúc thư mục như người nhận mong đợi.

Nếu phát hiện thiếu file cần thiết, sửa pattern và tạo lại commit/tag phát hành theo quy trình dự án. Với tag đã công bố, ưu tiên một phiên bản mới để giữ nguyên tính nhất quán của mốc cũ.

## 8. Những giới hạn của bản xuất

git archive rất tiện cho việc tạo source archive, nhưng không phải công cụ đóng gói tổng quát.

**Không chứa lịch sử Git.** Archive chỉ chứa snapshot của tree được chọn. Người nhận không thể dùng archive đó như một clone đầy đủ để xem toàn bộ commit, branch hoặc tag.

**Không bao gồm thay đổi chưa commit.** File chưa được track hoặc thay đổi local chưa commit không có trong tree của tag/commit.

**Không tự lấy nội dung submodule.** Repository cha lưu gitlink trỏ tới commit của submodule. Archive của repository cha không tự đóng gói toàn bộ repository con. Nếu sản phẩm cần nội dung submodule, quy trình build phải lấy và đóng gói chúng riêng.

**Không tự biến source thành artifact chạy được.** Archive không tự cài dependency, biên dịch, bundle frontend, tạo container hoặc ký gói. Những bước này thuộc build pipeline.

**Không bảo vệ bí mật.** export-ignore chỉ ẩn đường dẫn khỏi archive. Người có quyền đọc repository vẫn có thể lấy nội dung từ Git.

**Không bảo đảm cùng kết quả nếu đầu vào thay đổi.** Tag bị di chuyển, attributes khác nhau hoặc công cụ đóng gói khác nhau có thể tạo archive khác. Cần giữ tag ổn định, ghi commit SHA và checksum.

## 9. Phân biệt .gitignore với export-ignore

Hai tên thuộc về hai cơ chế khác nhau:

| Tiêu chí | .gitignore | export-ignore |
|---|---|---|
| Nơi cấu hình | File .gitignore | Attribute trong .gitattributes |
| Mục đích | Bỏ qua file chưa được theo dõi khi Git xét trạng thái/add | Loại đường dẫn khỏi archive git archive |
| Tác động tới file đã được track | Không tự bỏ file đã track khỏi index | Không xóa file đã track khỏi repository |
| Tác động tới clone | Không ngăn file đã commit được clone | Không ngăn file được clone |
| Tác động tới archive | Không phải cơ chế lọc archive | Có |

Ví dụ, thêm build/ vào .gitignore giúp Git bỏ qua các file build chưa được theo dõi. Nếu một file trong build/ đã được commit, .gitignore không xóa nó khỏi lịch sử. Tương tự, export-ignore có thể loại file đã track khỏi archive nhưng vẫn giữ nguyên file trong repository.

## 10. Lỗi thường gặp

**Placeholder vẫn còn nguyên trong archive.** Kiểm tra file có export-subst trong .gitattributes tại tag đang xuất hay không. Xác nhận bạn đang dùng git archive và không chỉ mở file trong working tree.

**File vẫn xuất hiện dù đã khai báo export-ignore.** Kiểm tra pattern có khớp đường dẫn thực tế không, file .gitattributes đã được commit vào tag chưa, và có quy tắc attributes ưu tiên cao hơn ghi đè hay không.

**Archive từ tag cũ có kết quả khác branch hiện tại.** Điều này có thể đúng vì Git dùng .gitattributes tại snapshot của tag. Hãy xem git show <tag>:.gitattributes.

**Dùng nhầm --worktree-attributes.** Tùy chọn này lấy quy tắc từ working tree, có thể khiến archive không tái lập từ commit/tag. Chỉ dùng khi cố ý thử nghiệm.

**Nghĩ rằng export-ignore che giấu bí mật.** File vẫn còn trong Git và lịch sử. Thu hồi bí mật và xử lý repository theo quy trình bảo mật.

**Đưa quá nhiều nội dung ra khỏi gói.** Người nhận có thể cần test, tài liệu, license hoặc script build. Kiểm tra archive với yêu cầu phân phối thực tế trước khi phát hành.

**Quên submodule.** Archive repository cha không tự đóng gói nội dung submodule. Cần bước riêng để lấy đúng commit của từng submodule nếu gói cần chúng.

## 11. Checklist trước khi công bố source archive

**Cấu hình**

- [ ] Đã xác định rõ file nào cần giữ và file nào cần loại khỏi archive.
- [ ] Pattern export-ignore khớp đúng đường dẫn.
- [ ] File cần thay placeholder đã có export-subst.
- [ ] .gitattributes đã được commit vào mốc phát hành.
- [ ] Không dùng export-ignore như cơ chế bảo mật.

**Tạo archive**

- [ ] Dùng commit hoặc tag cụ thể làm đầu vào.
- [ ] Đặt prefix và định dạng archive theo quy ước.
- [ ] Không dùng --worktree-attributes ngoài mục đích thử nghiệm đã xác định.
- [ ] Đã xử lý nội dung submodule nếu sản phẩm cần.

**Kiểm tra đầu ra**

- [ ] Đã liệt kê nội dung archive.
- [ ] File cần thiết có mặt.
- [ ] File bị loại đã vắng mặt.
- [ ] Placeholder được thay bằng thông tin đúng.
- [ ] Cấu trúc thư mục và tên archive đúng.
- [ ] Đã ghi commit SHA và checksum archive.

## 12. Kết luận

export-ignore và export-subst là hai thuộc tính trong .gitattributes giúp điều khiển source archive do git archive tạo ra. export-ignore loại đường dẫn khỏi archive; export-subst thay placeholder $Format:...$ bằng metadata của commit được xuất.

Hãy cấu hình các thuộc tính trong .gitattributes và commit chúng vào đúng mốc phát hành. Sau đó tạo archive từ tag hoặc commit cụ thể, kiểm tra danh sách file và nội dung đã thay thế, đồng thời ghi lại commit SHA cùng checksum. Các thuộc tính này giúp chuẩn hóa gói mã nguồn, còn bảo mật, build artifact và phát hành vẫn cần quy trình riêng.
