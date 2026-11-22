# Mẫu đường dẫn, dấu /, ** và quy tắc phủ định trong .gitignore

Khi làm việc với Git, repository thường có những tệp chỉ phục vụ máy phát triển hoặc quá trình build, chẳng hạn thư mục output, file log, cache, file tạm và cấu hình riêng. Bạn có thể khai báo các mẫu trong <code>.gitignore</code> để Git không đề xuất những tệp chưa được theo dõi đó trong các thao tác thông thường. Tuy nhiên, một mẫu đặt sai vị trí dấu <code>/</code>, dùng wildcard chưa đúng hoặc phủ định thiếu thư mục cha có thể khiến Git bỏ qua nhiều tệp hơn dự kiến hoặc không đưa một tệp cần thiết trở lại.

Bài này giải thích cách Git diễn giải mẫu đường dẫn trong <code>.gitignore</code>, sự khác nhau giữa mẫu có và không có dấu <code>/</code>, ý nghĩa của <code>*</code> và <code>**</code>, thứ tự ưu tiên giữa các quy tắc và cách dùng <code>!</code> để bỏ qua ngoại lệ. Đây là kiến thức thuộc chương **Ignore và attributes** của module **SOURCE_CONTROL_GIT**, giúp bạn quản lý tệp dự án gọn gàng mà vẫn bảo đảm các nội dung cần chia sẻ được theo dõi đúng cách.

## 1. .gitignore dùng để làm gì?

File <code>.gitignore</code> chứa các mẫu đường dẫn mà Git dùng để xác định những tệp chưa được theo dõi cần được bỏ qua. Khi một tệp mới khớp với quy tắc ignore, <code>git status</code> thường không liệt kê nó trong nhóm untracked. Điều này hữu ích với file sinh ra tự động như:

- Thư mục build và output.
- File log và file tạm.
- Cache của IDE hoặc công cụ build.
- Thư mục dependency được cài lại từ package manager.
- Cấu hình local chứa đường dẫn hoặc thiết lập riêng của từng máy.

Ví dụ:

~~~gitignore
# Build output
build/
out/

# Log files
*.log

# Local environment settings
.env.local
~~~

Các mẫu trên bỏ qua thư mục <code>build</code>, <code>out</code>, mọi file có đuôi <code>.log</code> phù hợp với vị trí của file ignore và file <code>.env.local</code>.

Điểm cần nhớ: <code>.gitignore</code> chủ yếu điều khiển những đường dẫn chưa được Git theo dõi. Nếu một file đã được commit hoặc đã nằm trong index như một file tracked, thêm tên file vào <code>.gitignore</code> không tự động ngừng theo dõi file đó. Muốn giữ file trên ổ đĩa nhưng ngừng theo dõi, bạn cần gỡ nó khỏi index bằng lệnh phù hợp, ví dụ:

~~~bash
git rm --cached -- config/local-settings.json
~~~

Sau đó commit việc gỡ khỏi index cùng quy tắc ignore thích hợp. Nội dung file vẫn còn trên máy hiện tại, nhưng Git không tiếp tục theo dõi các thay đổi của file đó ở những commit sau.

## 2. File .gitignore được áp dụng ở đâu?

Một repository có thể có nhiều file <code>.gitignore</code>. File ở thư mục gốc áp dụng cho các đường dẫn trong toàn bộ cây thư mục bên dưới. Bạn cũng có thể đặt file <code>.gitignore</code> trong một thư mục con để quy tắc chỉ có phạm vi từ thư mục đó trở xuống.

Ví dụ cấu trúc:

~~~text
project/
|-- .gitignore
|-- src/
|   |-- .gitignore
|   |-- app.log
|   |-- main.java
|-- build/
|   |-- app.jar
|-- docs/
|   |-- draft.tmp
~~~

Quy tắc trong <code>project/.gitignore</code> được tính tương đối từ thư mục <code>project</code>. Quy tắc trong <code>project/src/.gitignore</code> được tính tương đối từ <code>src</code>, không phải từ gốc repository.

Git còn có các nguồn quy tắc ignore khác:

1. Các mẫu được truyền trực tiếp qua một số lệnh Git.
2. File <code>.gitignore</code> ở thư mục chứa đường dẫn và các thư mục cha.
3. File loại trừ riêng của repository tại <code>.git/info/exclude</code>.
4. File ignore toàn cục được cấu hình bằng <code>core.excludesFile</code>.

Quy tắc trong <code>.gitignore</code> được chia sẻ cùng repository khi commit file đó. <code>.git/info/exclude</code> phù hợp với quy tắc chỉ áp dụng cho bản clone hiện tại, còn file ignore toàn cục phù hợp với các file sinh ra bởi công cụ cá nhân mà bạn không muốn đưa vào mọi dự án.

## 3. Cấu trúc và ký tự đặc biệt trong mẫu

Mỗi dòng không rỗng trong <code>.gitignore</code> là một mẫu. Git diễn giải một số ký tự theo quy tắc glob, không phải biểu thức chính quy.

| Ký hiệu | Ý nghĩa |
|---|---|
| <code>*</code> | Khớp với không hoặc nhiều ký tự, nhưng không vượt qua dấu phân cách thư mục <code>/</code> |
| <code>?</code> | Khớp với đúng một ký tự, không phải dấu <code>/</code> |
| <code>[abc]</code> | Khớp với một ký tự thuộc tập ký tự được liệt kê |
| <code>[0-9]</code> | Khớp với một ký tự trong khoảng đã khai báo |
| <code>**</code> | Trong các vị trí được Git hỗ trợ, khớp qua nhiều cấp thư mục |
| <code>!</code> ở đầu dòng | Phủ định quy tắc ignore trước đó để đưa đường dẫn phù hợp trở lại |
| <code>#</code> ở đầu dòng | Bắt đầu dòng chú thích |
| <code>\</code> | Escape một ký tự đặc biệt trong mẫu |

Ví dụ:

~~~gitignore
*.log
report-?.txt
image-[0-9].png
~~~

Các mẫu lần lượt khớp với file có đuôi <code>.log</code>, file có một ký tự bất kỳ ở vị trí sau <code>report-</code> và trước <code>.txt</code>, cùng file ảnh có một chữ số ở vị trí được chỉ định.

### Dòng trống, chú thích và khoảng trắng

- Dòng trống không tạo quy tắc.
- Dòng bắt đầu bằng <code>#</code> là chú thích.
- Dấu <code>#</code> ở đầu tên cần được escape nếu muốn xem là ký tự bình thường.
- Khoảng trắng ở cuối dòng bị bỏ qua, trừ khi được escape bằng dấu gạch chéo ngược.
- Dấu <code>!</code> ở đầu dòng có ý nghĩa phủ định; nếu tên đường dẫn thực sự bắt đầu bằng <code>!</code>, hãy escape ký tự đó.

Ví dụ:

~~~gitignore
# Ignore generated reports
*.report

\#notes.txt
\!important.txt
name-with-space\ 
~~~

Trong ví dụ, <code>\#notes.txt</code> là tên file bắt đầu bằng dấu thăng, <code>\!important.txt</code> là tên file bắt đầu bằng dấu chấm than, và khoảng trắng cuối của mẫu cuối được giữ lại nhờ escape.

## 4. Ý nghĩa của dấu / trong .gitignore

Dấu <code>/</code> quyết định mẫu được neo ở đâu và có xét cấp thư mục hay không. Đây là điểm thường gây nhầm lẫn nhất khi viết quy tắc ignore.

### Mẫu không có dấu / ở giữa

Nếu mẫu không chứa dấu <code>/</code>, ngoại trừ trường hợp dấu <code>/</code> ở cuối để chỉ thư mục, mẫu có thể khớp ở mọi cấp bên dưới vị trí của file <code>.gitignore</code>.

Ví dụ trong file <code>.gitignore</code> ở gốc repository:

~~~gitignore
temp
*.log
~~~

Quy tắc <code>temp</code> có thể khớp với file hoặc thư mục tên <code>temp</code> ở gốc, trong <code>src/temp</code>, <code>docs/temp</code> hoặc các cấp sâu hơn. Nếu khớp một thư mục, nội dung bên trong thư mục đó cũng bị bỏ qua.

Quy tắc <code>*.log</code> có thể khớp với file log ở nhiều thư mục con, chẳng hạn:

~~~text
app.log
src/debug.log
src/test/integration.log
~~~

### Mẫu có dấu / ở đầu

Dấu <code>/</code> ở đầu neo mẫu vào thư mục chứa file <code>.gitignore</code>. Nếu file nằm ở gốc repository, mẫu bắt đầu bằng <code>/</code> chỉ áp dụng từ gốc đó.

~~~gitignore
/TODO
/build/
~~~

Trong file ignore ở gốc:

- <code>/TODO</code> khớp với file hoặc thư mục <code>TODO</code> ngay tại gốc.
- <code>/build/</code> khớp với thư mục <code>build</code> ngay tại gốc và nội dung của nó.
- <code>src/TODO</code> không khớp với <code>/TODO</code>.
- <code>src/build/</code> không khớp với <code>/build/</code>.

### Mẫu có dấu / ở giữa

Nếu mẫu chứa dấu <code>/</code> ở giữa, mẫu được tính tương đối từ thư mục chứa file <code>.gitignore</code>. Ví dụ:

~~~gitignore
doc/frotz
logs/archive/
~~~

Trong file <code>.gitignore</code> ở gốc, <code>doc/frotz</code> khớp với đường dẫn <code>doc/frotz</code> bên dưới gốc. Nó không có nghĩa là khớp mọi file tên <code>frotz</code> ở bất kỳ thư mục nào. Tương tự, <code>logs/archive/</code> nhắm đến thư mục <code>archive</code> nằm trực tiếp trong <code>logs</code>.

### Dấu / ở cuối chỉ thư mục

Mẫu kết thúc bằng dấu <code>/</code> chỉ khớp thư mục:

~~~gitignore
cache/
~~~

Quy tắc này khớp thư mục có tên <code>cache</code> và nội dung bên trong, không khớp một file thường có tên đúng là <code>cache</code>. Khi Git bỏ qua thư mục, các file con cũng không được liệt kê riêng trong trạng thái untracked.

Nếu bỏ dấu <code>/</code>:

~~~gitignore
cache
~~~

mẫu có thể khớp cả file và thư mục tên <code>cache</code> ở mọi cấp dưới vị trí file ignore.

### So sánh nhanh

Giả sử các mẫu đều nằm trong file <code>.gitignore</code> ở gốc:

| Mẫu | Ví dụ khớp | Ví dụ không khớp |
|---|---|---|
| <code>build</code> | <code>build</code>, <code>src/build</code>, <code>src/a/build</code> | Không giới hạn theo cấp nếu tên thành phần là build |
| <code>/build</code> | <code>build</code> ở gốc | <code>src/build</code> |
| <code>build/</code> | Thư mục <code>build</code> ở bất kỳ cấp phù hợp | File thường tên <code>build</code> |
| <code>/build/</code> | Thư mục <code>build</code> ở gốc | <code>src/build/</code> |
| <code>src/build/</code> | Thư mục <code>src/build/</code> | <code>other/build/</code> |
| <code>*.log</code> | <code>app.log</code>, <code>src/app.log</code> | File không có đuôi <code>.log</code> |
| <code>/logs/*.log</code> | File log trực tiếp trong <code>logs/</code> ở gốc | <code>logs/archive/app.log</code> |

Hãy luôn tính đường dẫn từ vị trí của file <code>.gitignore</code> chứa mẫu. Nếu mẫu nằm trong thư mục con, dấu <code>/</code> đầu dòng neo vào thư mục con đó, không phải gốc repository.

## 5. Wildcard * và ?

Wildcard giúp gom nhiều tên file vào một quy tắc. Tuy nhiên, <code>*</code> không vượt qua dấu <code>/</code>; muốn khớp nhiều cấp thư mục, bạn cần hiểu cú pháp <code>**</code>.

Ví dụ:

~~~gitignore
*.tmp
report-?.csv
backup-[0-9].zip
~~~

Với các mẫu trên:

- <code>*.tmp</code> khớp file có phần mở rộng <code>.tmp</code> ở mọi cấp phù hợp với vị trí file ignore.
- <code>report-?.csv</code> khớp <code>report-1.csv</code> hoặc <code>report-a.csv</code>, nhưng không khớp <code>report-12.csv</code> vì dấu <code>?</code> chỉ đại diện một ký tự.
- <code>backup-[0-9].zip</code> khớp một chữ số tại vị trí trong ngoặc vuông.

Mẫu <code>src/*.log</code> chỉ khớp các file log trực tiếp trong <code>src</code>, ví dụ <code>src/app.log</code>. Nó không khớp <code>src/test/app.log</code>, vì dấu <code>*</code> không đi qua dấu phân cách thư mục.

Nếu muốn bỏ qua file log ở mọi cấp, dùng mẫu không có dấu <code>/</code> như <code>*.log</code>. Nếu muốn giới hạn một cây thư mục, hãy dùng dấu <code>/</code> và <code>**</code> có chủ đích.

## 6. Ý nghĩa đặc biệt của **

Git hỗ trợ <code>**</code> trong một số cấu trúc mẫu để khớp qua nhiều cấp thư mục. Các dạng quan trọng:

### **/ ở đầu mẫu

~~~gitignore
**/cache
~~~

Khớp thành phần tên <code>cache</code> ở mọi cấp thư mục. Với mẫu đơn giản không có dấu <code>/</code> như <code>cache</code>, kết quả thường tương đương.

### /** ở cuối mẫu

~~~gitignore
logs/**
~~~

Khớp mọi nội dung bên trong thư mục <code>logs</code>, ở độ sâu bất kỳ. Ví dụ:

~~~text
logs/app.log
logs/2026/11/app.log
logs/archive/old/server.log
~~~

Mẫu này nhắm vào nội dung bên trong <code>logs</code>. Nếu muốn bỏ qua chính thư mục <code>logs</code> cùng toàn bộ nội dung, có thể dùng <code>logs/</code>.

### /**/ ở giữa mẫu

~~~gitignore
a/**/b
~~~

Khớp đường dẫn:

~~~text
a/b
a/x/b
a/x/y/b
~~~

Phần <code>**/</code> có thể đại diện cho không hoặc nhiều cấp thư mục. Do đó, mẫu vẫn khớp khi không có thư mục trung gian giữa <code>a</code> và <code>b</code>.

### Ví dụ thực tế

~~~gitignore
# Bỏ qua thư mục node_modules ở mọi cấp
**/node_modules/

# Bỏ qua nội dung trong thư mục generated tại gốc
/generated/**

# Bỏ qua mọi file có tên secrets.json trong cây dự án
**/secrets.json

# Bỏ qua file cache ở mọi cấp
**/*.cache
~~~

Mẫu <code>**/node_modules/</code> giúp bắt các thư mục dependency được lồng trong nhiều package. Mẫu <code>/generated/**</code> giới hạn phạm vi vào thư mục <code>generated</code> ở gốc. Mẫu <code>**/secrets.json</code> áp dụng cho file có tên đó ở bất kỳ cấp nào.

Không cần lạm dụng <code>**</code>. Khi mẫu không có dấu <code>/</code> đã diễn đạt đúng ý, hãy dùng mẫu đơn giản hơn để người đọc dễ hiểu và tránh quy tắc khó bảo trì.

## 7. Quy tắc phủ định bằng dấu !

Dấu <code>!</code> ở đầu dòng phủ định một quy tắc ignore trước đó. Nó cho phép đưa một đường dẫn cụ thể trở lại danh sách được Git theo dõi, dù đường dẫn đó khớp với mẫu bỏ qua rộng hơn.

Ví dụ, bỏ qua tất cả file log nhưng giữ lại file log mẫu:

~~~gitignore
*.log
!examples/sample.log
~~~

Trong ví dụ này, file <code>examples/sample.log</code> được đưa trở lại, miễn là các thư mục cha của nó không bị loại bỏ khỏi quá trình duyệt.

### Thứ tự quy tắc có ý nghĩa

Trong cùng một mức ưu tiên, quy tắc khớp sau cùng quyết định kết quả. Vì vậy, quy tắc phủ định thường được đặt sau quy tắc ignore mà nó cần đảo ngược:

~~~gitignore
*.log
!important.log
~~~

<code>important.log</code> không bị bỏ qua, còn các file log khác vẫn bị ignore.

Nếu đổi thứ tự:

~~~gitignore
!important.log
*.log
~~~

quy tắc ignore ở dòng sau lại khớp với file đó, nên file vẫn bị bỏ qua.

### Không thể mở lại file bên trong thư mục cha đã bị ignore

Đây là giới hạn quan trọng nhất của quy tắc phủ định. Nếu Git đã bỏ qua một thư mục, Git không duyệt các đường dẫn bên trong thư mục đó để tìm mẫu phủ định. Vì vậy, chỉ viết:

~~~gitignore
build/
!build/keep.txt
~~~

thường không đủ để đưa <code>build/keep.txt</code> trở lại. Thư mục <code>build</code> đã bị loại khỏi quá trình duyệt.

Một cách viết phù hợp là bỏ qua các mục con thay vì bỏ qua toàn bộ thư mục cha:

~~~gitignore
build/*
!build/keep.txt
~~~

Ở đây <code>build/</code> vẫn được Git duyệt, các mục trực tiếp bên trong bị ignore bởi <code>build/*</code>, rồi file <code>keep.txt</code> được phủ định ở dòng sau.

### Mở lại một thư mục con và một file cụ thể

Giả sử bạn muốn bỏ qua hầu hết nội dung trong <code>build</code>, nhưng giữ lại <code>build/keep/important.txt</code>. Có thể viết:

~~~gitignore
build/*
!build/keep/
build/keep/*
!build/keep/important.txt
~~~

Diễn giải:

1. <code>build/*</code> bỏ qua các mục trực tiếp trong <code>build</code>.
2. <code>!build/keep/</code> mở lại thư mục <code>keep</code> để Git có thể duyệt bên trong.
3. <code>build/keep/*</code> bỏ qua các mục trực tiếp trong thư mục <code>keep</code>.
4. <code>!build/keep/important.txt</code> mở lại file cần giữ.

Nếu file cần giữ nằm sâu hơn, từng thư mục cha trên đường dẫn cũng phải được mở lại để Git có thể duyệt xuống. Hãy kiểm tra quy tắc với <code>git check-ignore</code> thay vì chỉ suy luận từ tên file.

## 8. Quy tắc nào có độ ưu tiên cao hơn?

Khi nhiều nguồn cung cấp quy tắc ignore, Git áp dụng thứ tự ưu tiên. Từ cao xuống thấp:

1. Các mẫu được truyền qua dòng lệnh cho lệnh hỗ trợ chúng.
2. Các file <code>.gitignore</code> trong thư mục chứa đường dẫn và các thư mục cha. File ở thư mục sâu hơn có thể ghi đè file ở thư mục cha.
3. File <code>$GIT_DIR/info/exclude</code> của repository hiện tại.
4. File ignore toàn cục được chỉ định bởi <code>core.excludesFile</code>.

Trong cùng một file hoặc cùng mức ưu tiên, quy tắc khớp cuối cùng có hiệu lực. Quy tắc ở file <code>.gitignore</code> sâu hơn có thể ghi đè quy tắc ở file cha, giúp một thư mục con có ngoại lệ riêng.

Ví dụ:

~~~text
project/
|-- .gitignore
|-- logs/
|   |-- .gitignore
|   |-- important.log
|   |-- debug.log
~~~

File ở gốc:

~~~gitignore
*.log
~~~

File <code>logs/.gitignore</code>:

~~~gitignore
!important.log
~~~

Quy tắc trong thư mục <code>logs</code> có thể đưa <code>logs/important.log</code> trở lại, trong khi <code>logs/debug.log</code> vẫn bị bỏ qua bởi quy tắc ở gốc. Thư mục cha <code>logs</code> không bị ignore trong ví dụ này nên Git có thể đọc file ignore bên trong nó.

## 9. Đường dẫn trong .gitignore trên Windows và Linux

Trong mẫu <code>.gitignore</code>, dấu phân cách thư mục cần viết bằng dấu gạch chéo xuôi <code>/</code>, kể cả khi bạn làm việc trên Windows.

Ví dụ:

~~~gitignore
build/
src/generated/
logs/**/*.log
~~~

Không viết đường dẫn mẫu theo dạng Windows với dấu gạch chéo ngược làm dấu phân cách thư mục:

~~~text
build\
src\generated\
~~~

Dấu gạch chéo ngược trong mẫu Git có vai trò escape ký tự đặc biệt, không phải cách viết dấu phân cách thư mục nên dùng trong <code>.gitignore</code>. Hãy dùng <code>/</code> để mẫu có tính nhất quán giữa các hệ điều hành.

## 10. Kiểm tra vì sao một file bị ignore

Khi <code>git status</code> không hiển thị một file mà bạn nghĩ cần được theo dõi, đừng vội thêm nhiều quy tắc phủ định. Hãy hỏi Git quy tắc nào đang khớp.

### Dùng git check-ignore -v

~~~bash
git check-ignore -v -- build/app.jar
~~~

Tùy chọn <code>-v</code> hiển thị nguồn quy tắc, số dòng và mẫu đã khớp. Kết quả có thể tương tự:

~~~text
.gitignore:4:/build/    build/app.jar
~~~

Kết quả cho biết dòng 4 trong file <code>.gitignore</code> ở gốc đang bỏ qua đường dẫn này. Bạn có thể sửa đúng quy tắc thay vì thêm một ngoại lệ ở vị trí không liên quan.

### Kiểm tra cả đường dẫn đã tracked

Thông thường, <code>git check-ignore</code> không báo một đường dẫn đã được Git theo dõi trong index. Nếu muốn kiểm tra mẫu ignore có khớp với đường dẫn tracked hay không, dùng <code>--no-index</code>:

~~~bash
git check-ignore -v --no-index -- config/application.yml
~~~

Tùy chọn này hữu ích khi bạn vừa thêm một mẫu vào <code>.gitignore</code> và muốn xác nhận nó có khớp với file đã tracked hay không. Kết quả khớp không có nghĩa file đã tự ngừng được theo dõi; bạn vẫn cần thao tác trên index nếu muốn bỏ theo dõi.

### Liệt kê file ignored

~~~bash
# Hiển thị cả các đường dẫn ignored trong trạng thái
git status --ignored

# Dạng ngắn, dễ quan sát
git status --short --ignored
~~~

Lệnh này giúp kiểm tra phạm vi ignore thực tế. Repository có nhiều thư mục build có thể tạo ra đầu ra dài; bạn có thể chỉ định đường dẫn khi kiểm tra bằng <code>git check-ignore</code>.

## 11. Khi cần thêm một file đang bị ignore

Đôi khi bạn muốn thêm một file mẫu hoặc file cấu hình được ignore theo quy tắc chung. Có hai cách tùy mục tiêu.

### Thêm cưỡng bức một file

~~~bash
git add -f examples/sample.env
~~~

Tùy chọn <code>-f</code> buộc Git thêm đường dẫn dù nó khớp quy tắc ignore. Cách này phù hợp với một trường hợp ngoại lệ đơn lẻ, nhưng không thay đổi quy tắc trong <code>.gitignore</code>. Nếu file tiếp tục cần được chia sẻ, nhóm nên cân nhắc có quy tắc phủ định rõ ràng để các thành viên khác cũng có thể thêm file đó bình thường.

### Viết ngoại lệ trong .gitignore

~~~gitignore
*.env
!examples/sample.env
~~~

Sau đó kiểm tra:

~~~bash
git check-ignore -v -- examples/sample.env
git status --short
~~~

Nếu đường dẫn vẫn bị ignore, hãy kiểm tra các thư mục cha và thứ tự quy tắc. Một mẫu phủ định không thể mở lại file nếu thư mục cha vẫn đang bị ignore.

## 12. Các mẫu thực tế thường dùng

### Bỏ qua output build nhưng giữ file hướng dẫn

~~~gitignore
/build/*
!/build/README.md
~~~

Mẫu này bỏ qua các mục bên trong thư mục <code>build</code> ở gốc, nhưng giữ file hướng dẫn. Vì thư mục <code>build</code> không bị ignore trực tiếp, Git có thể duyệt để áp dụng ngoại lệ.

### Bỏ qua file log ở mọi cấp, giữ log mẫu

~~~gitignore
*.log
!examples/sample.log
~~~

Mẫu này phù hợp khi log sinh ra không cần commit nhưng nhóm muốn giữ một file mẫu minh họa định dạng log. Nếu thư mục <code>examples</code> bị ignore bởi quy tắc khác, cần mở lại thư mục trước.

### Bỏ qua cache ở mọi cấp

~~~gitignore
**/.cache/
**/*.tmp
~~~

Quy tắc đầu bỏ qua thư mục <code>.cache</code> ở mọi cấp; quy tắc thứ hai bỏ qua file tạm có đuôi <code>.tmp</code>.

### Bỏ qua cấu hình local nhưng giữ file mẫu

~~~gitignore
.env
.env.*
!.env.example
~~~

Ví dụ này bỏ qua file môi trường và các biến thể, nhưng cho phép commit file mẫu <code>.env.example</code>. Hãy chắc chắn file mẫu không chứa mật khẩu, token hoặc giá trị bí mật thực tế.

### Chỉ bỏ qua thư mục generated ở gốc

~~~gitignore
/generated/
~~~

Thư mục <code>generated</code> ở gốc bị ignore, trong khi một thư mục cùng tên nằm trong <code>src/generated</code> không bị quy tắc này tác động.

## 13. Quy trình thiết kế và kiểm tra quy tắc

Khi viết hoặc sửa <code>.gitignore</code>, hãy làm theo quy trình:

1. Xác định chính xác đường dẫn cần bỏ qua và đường dẫn ngoại lệ cần giữ.
2. Xác định file <code>.gitignore</code> đặt ở đâu để tính phạm vi tương đối.
3. Chọn mẫu đơn giản nhất có thể: không có slash nếu cần khớp mọi cấp, có slash nếu cần giới hạn đường dẫn.
4. Dùng <code>*</code> cho một thành phần tên và <code>**</code> khi thực sự cần đi qua nhiều cấp thư mục.
5. Đặt quy tắc phủ định sau quy tắc ignore mà nó cần đảo ngược.
6. Bảo đảm mọi thư mục cha của đường dẫn ngoại lệ đều có thể được Git duyệt.
7. Kiểm tra bằng <code>git check-ignore -v</code> và <code>git status --ignored</code>.
8. Xác nhận các file đã tracked không bị nhầm là đã được bỏ theo dõi.

Ví dụ kiểm tra một quy tắc mới:

~~~bash
# Xem quy tắc nào đang bỏ qua file
git check-ignore -v -- logs/app.log

# Xem trạng thái các file, gồm cả ignored
git status --short --ignored

# Nếu cần kiểm tra mẫu đối với file đã tracked
git check-ignore -v --no-index -- config/application.yml
~~~

Hãy kiểm tra cả trường hợp cần ignore và trường hợp cần giữ. Một quy tắc tốt không chỉ bỏ qua đúng file sinh ra mà còn không che mất file nguồn, file cấu hình mẫu hoặc tài liệu mà nhóm cần commit.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| <code>*.log</code> không khớp như mong đợi | File ignore nằm trong thư mục con hoặc file đã tracked | Xác định vị trí <code>.gitignore</code>; dùng <code>git check-ignore -v</code> |
| <code>/build/</code> không bỏ qua <code>src/build/</code> | Dấu slash đầu neo mẫu vào thư mục chứa file ignore | Dùng <code>build/</code> hoặc mẫu phù hợp với cây thư mục |
| <code>src/*.log</code> không khớp log trong thư mục con | <code>*</code> không vượt qua dấu slash | Dùng <code>src/**/*.log</code> nếu cần nhiều cấp |
| File ngoại lệ vẫn bị ignore | Thư mục cha bị ignore hoặc quy tắc ignore xuất hiện sau quy tắc phủ định | Mở lại thư mục cha và đặt ngoại lệ sau quy tắc ignore |
| Thêm mẫu vào .gitignore nhưng file tracked vẫn hiện thay đổi | Ignore không tác động lên file đã được theo dõi | Dùng <code>git rm --cached</code> nếu chủ đích ngừng theo dõi |
| File trên Windows không khớp | Mẫu dùng dấu gạch chéo ngược làm dấu phân cách | Dùng dấu <code>/</code> trong mẫu |
| Không biết quy tắc đến từ đâu | Có nhiều file ignore hoặc nguồn cấu hình | Dùng <code>git check-ignore -v</code> để xem nguồn và dòng |

## 15. Bài tập tự kiểm tra

Thực hành trong một repository thử nghiệm:

1. Tạo các đường dẫn <code>app.log</code>, <code>src/debug.log</code> và <code>src/test/result.log</code>. Thêm mẫu <code>*.log</code> rồi kiểm tra trạng thái.
2. Thay mẫu bằng <code>/app.log</code>. Giải thích vì sao file ở thư mục con không còn khớp.
3. Thử <code>src/*.log</code> và <code>src/**/*.log</code>. So sánh kết quả với file log ở thư mục con sâu hơn.
4. Tạo <code>build/keep.txt</code>. Viết quy tắc ignore các mục trong build nhưng giữ lại file này.
5. Thử bỏ qua trực tiếp <code>build/</code> rồi phủ định file con. Quan sát vì sao ngoại lệ không có hiệu lực nếu thư mục cha vẫn bị ignore.
6. Tạo một file đã tracked, sau đó thêm mẫu khớp với file. Xác nhận file vẫn được Git theo dõi.
7. Dùng <code>git check-ignore -v</code> để tìm dòng quy tắc khớp với một file.
8. Tạo file <code>.gitignore</code> trong một thư mục con và kiểm tra phạm vi của mẫu neo bằng dấu <code>/</code>.
9. Giải thích sự khác nhau giữa <code>*</code>, <code>**/</code> và <code>/**</code>.

Khi có thể dự đoán một mẫu khớp với file nào, tính đúng phạm vi từ vị trí file <code>.gitignore</code>, và mở lại ngoại lệ mà không bỏ qua thư mục cha, bạn đã nắm được phần quan trọng nhất của cú pháp ignore. Hãy ưu tiên mẫu rõ ràng, kiểm tra bằng Git và giữ các quy tắc cần thiết trong repository để cả nhóm có cùng hành vi.
