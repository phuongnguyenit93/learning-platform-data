# Khởi tạo dự án, loại tệp sinh ra và tạo chuỗi commit đầu tiên

Bài thực hành này đưa bạn qua một quy trình khởi tạo repository hoàn chỉnh: chọn đúng thư mục gốc, tạo cấu trúc dự án, chuẩn bị .gitignore và .gitattributes, thêm mã nguồn, tạo file build sinh ra để kiểm tra quy tắc ignore, rồi ghi nhận công việc bằng một chuỗi commit nhỏ và có ý nghĩa. Kết quả cuối cùng là một repository có thể clone trên máy khác, không chứa cache hoặc artifact không cần thiết và có lịch sử đủ rõ để người khác hiểu dự án được hình thành như thế nào.

Bạn sẽ tạo một ứng dụng Java nhỏ tên inventory-cli. Ví dụ dùng Java để tạo ra file .class và thư mục build/ thật, nhờ đó có thể kiểm chứng rằng Git chỉ theo dõi source và tài liệu, còn đầu ra build được loại khỏi lịch sử.

## 1. Mục tiêu và kết quả cần đạt

Sau khi hoàn thành, repository cần có:

- Một repository root đúng phạm vi dự án.
- Cấu trúc tách mã nguồn, tài liệu và cấu hình.
- .gitignore loại file build, cache, log và cấu hình local có thể chứa bí mật.
- .gitattributes quy định cách xử lý văn bản và một số file nhị phân.
- Một ứng dụng Java có thể biên dịch và chạy.
- Một thư mục build/ được tạo trong quá trình biên dịch nhưng không được Git theo dõi.
- Ít nhất ba commit đầu tiên, mỗi commit đại diện cho một bước công việc riêng.
- Working tree sạch sau commit cuối, ngoại trừ các file ignored vẫn tồn tại trên máy.

Chuỗi commit dự kiến:

~~~text
main
  |
  o  docs: add local build instructions
  |
  o  feat: add inventory greeting entry point
  |
  o  chore: initialize inventory-cli project
~~~

Tên commit trong sơ đồ là thông điệp minh họa; hash và thời gian sẽ do Git tạo trên máy của bạn.

## 2. Chuẩn bị môi trường

Kiểm tra Git và JDK đã sẵn sàng:

~~~bash
git --version
javac -version
java -version
~~~

javac và java cần thuộc cùng một JDK tương thích. Nếu chỉ có Java Runtime mà không có compiler, bước biên dịch sẽ không chạy được.

Kiểm tra danh tính commit:

~~~bash
git config --get user.name
git config --get user.email
~~~

Nếu chưa cấu hình, bạn sẽ đặt danh tính chỉ cho repository thực hành sau khi khởi tạo ở bước 4. Dùng thông tin thật mà bạn muốn ghi vào commit; không cần thay đổi cấu hình global nếu bạn chỉ đang làm bài thực hành.

Các lệnh tạo thư mục trong bài dùng cú pháp Bash hoặc Git Bash. Trên Windows, bạn có thể mở Git Bash trong thư mục làm việc. Các lệnh Git vẫn giống nhau trong PowerShell.

## 3. Chọn repository root và tạo thư mục dự án

Chọn một thư mục cha dành cho các bài thực hành, sau đó tạo dự án:

~~~bash
mkdir -p ~/git-practice
cd ~/git-practice
mkdir inventory-cli
cd inventory-cli
~~~

Không chạy git init trong ~/git-practice nếu thư mục này còn chứa nhiều dự án độc lập. Repository root của bài là inventory-cli/, vì vậy lịch sử Git chỉ quản lý nội dung của dự án này.

Tạo các thư mục cần thiết:

~~~bash
mkdir -p src/main/java/com/example/inventory
mkdir -p docs
~~~

Cấu trúc dự kiến:

~~~text
inventory-cli/
  src/
    main/java/com/example/inventory/
  docs/
~~~

Không cần tạo build/, target/, .gradle/ hoặc node_modules/ trong source tree. Đây là những thư mục có thể phát sinh khi build hoặc cài dependency và sẽ được ignore.

## 4. Khởi tạo repository trên branch main

Khởi tạo Git:

~~~bash
git init -b main
~~~

Tùy chọn -b main đặt tên branch khởi tạo ngay từ đầu. Nếu phiên bản Git quá cũ chưa hỗ trợ tùy chọn này, dùng:

~~~bash
git init
git branch -M main
~~~

Nếu chưa có danh tính commit ở cấp global, đặt danh tính local ngay trong repository này:

~~~bash
git config --local user.name "Your Name"
git config --local user.email "you@example.com"
~~~

Thay hai giá trị mẫu bằng tên và email phù hợp với bạn.

Xác nhận vị trí repository và branch:

~~~bash
git rev-parse --show-toplevel
git branch --show-current
git status --short
~~~

Đường dẫn --show-toplevel cần trỏ tới thư mục inventory-cli. Branch hiện tại cần là main. Nếu chạy git status đầy đủ (không có --short), Git cũng thông báo repository chưa có commit.

Kiểm tra thư mục Git metadata:

~~~bash
git rev-parse --git-dir
~~~

Thư mục .git/ lưu object database, refs, index và cấu hình local. Không đưa nội dung .git/ vào commit; Git tự quản lý metadata này.

## 5. Tạo .gitignore trước khi build

Tạo file .gitignore ở root:

~~~gitignore
# Java compiled files
*.class

# Build output
build/
target/
out/
.gradle/

# Logs and temporary files
*.log
*.tmp

# Local environment and secrets
.env
.env.*
!.env.example
application-local.yml

# IDE local state
.idea/workspace.xml
.vscode/settings.local.json

# Operating system files
.DS_Store
Thumbs.db
Desktop.ini
~~~

Các quy tắc này phù hợp với ví dụ Java nhỏ, nhưng vẫn cần điều chỉnh theo dự án thật:

- *.class loại bytecode Java sinh ra từ compiler.
- build/, target/ và out/ loại các thư mục output thường gặp.
- .gradle/ loại cache của Gradle; file wrapper và build script vẫn có thể được commit.
- .env và .env.* loại cấu hình local; !.env.example cho phép giữ file mẫu không chứa secret.
- Chỉ ignore trạng thái IDE cá nhân, không mặc định bỏ qua toàn bộ cấu hình IDE nếu nhóm cần chia sẻ formatter hoặc launch configuration.

.gitignore chủ yếu áp dụng cho đường dẫn chưa được theo dõi. Nếu một file đã được commit, thêm pattern sau đó không tự ngừng theo dõi file ấy.

## 6. Tạo .gitattributes để thống nhất cách xử lý file

Tạo file .gitattributes ở root:

~~~gitattributes
# Normalize text files in the repository
* text=auto

# Keep shell scripts with LF line endings
*.sh text eol=lf

# Keep Windows batch files with CRLF line endings
*.bat text eol=crlf

# Treat common binary assets as binary
*.png binary
*.jpg binary
*.jpeg binary
*.jar binary
~~~

text=auto cho phép Git nhận diện nội dung văn bản và chuẩn hóa line ending trong object database. eol quy định kiểu dòng kết thúc khi checkout cho các pattern cụ thể. Macro binary tắt xử lý text/diff/merge thông thường cho loại file tương ứng.

Kiểm tra attribute của một đường dẫn:

~~~bash
git check-attr text eol diff merge -- README.md
git check-attr text eol diff merge -- assets/logo.png
~~~

Ở ví dụ hiện tại, assets/logo.png chưa tồn tại; lệnh vẫn có thể hiển thị quy tắc theo pattern. Không cần tạo file giả chỉ để kiểm tra.

## 7. Tạo README mô tả dự án

Tạo README.md:

~~~markdown
# Inventory CLI

Ứng dụng Java dòng lệnh nhỏ dùng trong bài thực hành Git.

## Cấu trúc

- src/main/java/: mã nguồn ứng dụng.
- docs/: hướng dẫn phát triển.
- build/: bytecode và đầu ra build được tạo tự động, không commit.

## Yêu cầu

- Git
- JDK có java và javac

## Bắt đầu

Hướng dẫn build và chạy sẽ được bổ sung trong thư mục docs/.
~~~

README nên mô tả cách người mới hiểu và sử dụng dự án. Không ghi token, mật khẩu, URL có credential hoặc đường dẫn chỉ tồn tại trên máy cá nhân.

## 8. Review và tạo commit đầu tiên

Kiểm tra những file hiện có:

~~~bash
git status --short --untracked-files=all
~~~

Stage đúng ba file metadata/tài liệu ban đầu:

~~~bash
git add README.md .gitignore .gitattributes
~~~

Xem nội dung chuẩn bị commit:

~~~bash
git diff --cached --stat
git diff --cached --check
git diff --cached
~~~

- --stat cho biết số file và lượng thay đổi.
- --check phát hiện whitespace error như trailing whitespace.
- git diff --cached cho phép đọc nội dung chính xác đang nằm trong index.

Nếu mọi thứ đúng, tạo commit đầu tiên:

~~~bash
git commit -m "chore: initialize inventory-cli project"
~~~

Commit này thiết lập cấu trúc và quy tắc repository. Nó chưa chứa mã nguồn ứng dụng.

Kiểm tra commit:

~~~bash
git show --stat --oneline HEAD
git status --short
~~~

## 9. Thêm mã nguồn ứng dụng

Tạo file src/main/java/com/example/inventory/Main.java:

~~~java
package com.example.inventory;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String name = args.length > 0 ? args[0] : "Git";
        System.out.println("Hello, " + name + "!");
    }
}
~~~

Chương trình nhận một đối số tùy chọn. Nếu không truyền đối số, nó in Hello, Git!.

Kiểm tra file mới:

~~~bash
git status --short
git diff -- src/main/java/com/example/inventory/Main.java
~~~

Vì file mới chưa tracked, git diff thông thường chưa hiển thị nội dung. Bạn có thể đọc file trực tiếp hoặc stage rồi xem git diff --cached.

Stage riêng file Java và review:

~~~bash
git add src/main/java/com/example/inventory/Main.java
git diff --cached --check
git diff --cached
~~~

Tạo commit thứ hai:

~~~bash
git commit -m "feat: add inventory greeting entry point"
~~~

Commit này chỉ chứa entry point của ứng dụng. Tách commit theo mục đích giúp reviewer hiểu thay đổi và có thể tìm hoặc revert một phần lịch sử dễ hơn.

## 10. Biên dịch để tạo file sinh ra

Tạo output directory và biên dịch Java:

~~~bash
mkdir -p build/classes
javac -d build/classes src/main/java/com/example/inventory/Main.java
~~~

Chạy chương trình:

~~~bash
java -cp build/classes com.example.inventory.Main
java -cp build/classes com.example.inventory.Main Warehouse
~~~

Kết quả mong đợi:

~~~text
Hello, Git!
Hello, Warehouse!
~~~

Trên PowerShell, có thể thực hiện tương đương:

~~~powershell
New-Item -ItemType Directory -Force -Path build/classes | Out-Null
javac -d build/classes src/main/java/com/example/inventory/Main.java
java -cp build/classes com.example.inventory.Main
java -cp build/classes com.example.inventory.Main Warehouse
~~~

Sau biên dịch, build/classes/com/example/inventory/Main.class là file sinh ra. File này có thể tạo lại từ Main.java, vì vậy không cần commit.

## 11. Chứng minh .gitignore đang hoạt động

Kiểm tra quy tắc đã khớp:

~~~bash
git check-ignore -v build/classes/com/example/inventory/Main.class
~~~

Git cần hiển thị file .gitignore, số dòng và pattern đã bỏ qua file .class hoặc thư mục build/.

Xem cả file ignored trong trạng thái:

~~~bash
git status --short --ignored
~~~

Bạn có thể thấy dòng bắt đầu bằng !! cho thư mục build/. Đây là dấu hiệu file tồn tại trên ổ đĩa nhưng đang bị ignore.

Xác nhận Git chưa theo dõi output:

~~~bash
git ls-files -- build/
~~~

Lệnh không in đường dẫn nào nếu chưa có file trong build/ được track. git status --short thông thường cũng không liệt kê thư mục ignored.

### 11.1. Ignore không xóa file trên máy

.gitignore không xóa build/; nó chỉ yêu cầu Git không đưa file chưa tracked trong phạm vi đó vào danh sách untracked. File .class vẫn tồn tại và chương trình vẫn chạy được.

### 11.2. Ignore không tự bỏ theo dõi file đã commit

Nếu một file build đã được commit từ trước, thêm build/ vào .gitignore không làm file biến mất khỏi lịch sử hoặc ngừng tracked. Muốn bỏ file khỏi index nhưng giữ file local:

~~~bash
git rm --cached -r build/
git commit -m "chore: stop tracking generated build output"
~~~

Chỉ dùng ví dụ này khi build/ thực sự đã được track. Trong bài thực hành hiện tại, git ls-files -- build/ cần rỗng nên không cần chạy lệnh trên.

## 12. Thêm hướng dẫn build và chạy

Tạo docs/development.md:

~~~~~markdown
# Phát triển Inventory CLI

## Biên dịch

Từ repository root, chạy:

~~~~bash
mkdir -p build/classes
javac -d build/classes src/main/java/com/example/inventory/Main.java
~~~~

## Chạy

~~~~bash
java -cp build/classes com.example.inventory.Main
java -cp build/classes com.example.inventory.Main Warehouse
~~~~

## Đầu ra

Bytecode nằm trong build/classes/. Đây là dữ liệu sinh ra, được .gitignore loại khỏi Git và có thể tạo lại bằng lệnh biên dịch.
~~~~~

Trong README.md, thay câu thông báo tạm ở mục Bắt đầu bằng liên kết tới tài liệu vừa tạo:

~~~markdown
Xem [hướng dẫn build và chạy](docs/development.md).
~~~

Tài liệu cần mô tả lệnh chạy từ repository root và chỉ rõ thư mục output. Điều này giúp người khác tái tạo kết quả mà không cần nhận file .class từ máy của bạn.

Kiểm tra thay đổi:

~~~bash
git status --short --untracked-files=all
~~~

File mới chưa được stage không xuất hiện trong git diff thông thường. Sau khi stage, git diff --cached bên dưới sẽ hiển thị toàn bộ nội dung chuẩn bị commit.

Stage riêng tài liệu và review:

~~~bash
git add docs/development.md README.md
git diff --cached --check
git diff --cached --stat
git diff --cached
~~~

Tạo commit thứ ba:

~~~bash
git commit -m "docs: add local build instructions"
~~~

Commit này bổ sung hướng dẫn phát triển, không cần đưa output build vào lịch sử.

## 13. Kiểm tra toàn bộ chuỗi commit đầu tiên

Xem lịch sử:

~~~bash
git log --oneline --decorate --graph
~~~

Kết quả cần có ba commit theo thứ tự mới nhất tới cũ nhất:

~~~text
* <hash-3> (HEAD -> main) docs: add local build instructions
* <hash-2> feat: add inventory greeting entry point
* <hash-1> chore: initialize inventory-cli project
~~~

Xem từng commit:

~~~bash
git show --stat HEAD
git show --stat HEAD~1
git show --stat HEAD~2
~~~

Kiểm tra file được theo dõi:

~~~bash
git ls-files
~~~

Danh sách nên có .gitignore, .gitattributes, README, mã nguồn và tài liệu phát triển. Không nên có build/classes/Main.class, file log, .env hoặc thư mục cache.

Kiểm tra working tree và index:

~~~bash
git status --short
git diff
git diff --cached
~~~

Ba lệnh cuối cần không hiển thị thay đổi tracked sau khi commit hoàn tất. File ignored vẫn có thể tồn tại và được xác nhận bằng git status --short --ignored.

## 14. Kiểm tra khả năng tái tạo từ clone sạch

Một repository được tổ chức đúng không nên phụ thuộc vào file build hoặc cấu hình local chỉ có trên máy người tạo. Có thể kiểm tra bằng cách clone sang một thư mục anh em:

~~~bash
cd ..
git clone inventory-cli inventory-cli-clean
cd inventory-cli-clean
git status --short
mkdir -p build/classes
javac -d build/classes src/main/java/com/example/inventory/Main.java
java -cp build/classes com.example.inventory.Main CleanClone
~~~

Kết quả mong đợi là Hello, CleanClone!. Clone sạch ban đầu không có build/classes/; thư mục này chỉ xuất hiện sau khi biên dịch.

Nếu clone sạch không build được, kiểm tra README, dependency manifest, wrapper, cấu hình mẫu và các file cần thiết có bị bỏ sót khỏi commit hay không. Không giải quyết bằng cách commit cache hoặc credential cá nhân.

Sau khi thử nghiệm, quay lại thư mục làm việc ban đầu nếu cần:

~~~bash
cd ../inventory-cli
~~~

Có thể xóa clone thử nghiệm sau khi xác nhận không còn cần giữ. Không xóa repository gốc hoặc thư mục làm việc đang có thay đổi.

## 15. Các tình huống cần xử lý trong lúc thực hành

### File .class xuất hiện trong git status

Kiểm tra pattern:

~~~bash
git check-ignore -v build/classes/com/example/inventory/Main.class
~~~

Nếu không có kết quả, xem .gitignore có nằm ở repository root và pattern có đúng đường dẫn không. Nếu file đã tracked, dùng git ls-files --error-unmatch để xác nhận và xử lý bằng git rm --cached nếu muốn ngừng theo dõi.

### .env.example bị ignore cùng .env

Đảm bảo có ngoại lệ sau pattern ignore:

~~~gitignore
.env.*
!.env.example
~~~

Chạy git check-ignore -v .env.example. Nếu ngoại lệ hoạt động, lệnh không in quy tắc ignore và trả mã thoát 1 vì file không bị ignore. File mẫu chỉ được commit nếu không chứa credential thật.

### Stage nhầm file

Xem nội dung index:

~~~bash
git diff --cached
~~~

Nếu muốn unstage một file nhưng giữ nguyên nội dung trong working tree:

~~~bash
git restore --staged -- path/to/file
~~~

### Đã commit file sinh ra

Thêm quy tắc ignore không đủ. Bỏ file khỏi index nhưng giữ bản local:

~~~bash
git rm --cached -- path/to/generated-file
git commit -m "chore: stop tracking generated file"
~~~

Nếu file lớn hoặc chứa secret đã có trong lịch sử, cần quy trình xử lý riêng; commit xóa file mới không xóa dữ liệu khỏi các commit cũ. Với secret, thu hồi hoặc rotate credential trước.

### Commit báo thiếu danh tính

Kiểm tra và đặt cấu hình local:

~~~bash
git config --local user.name "Your Name"
git config --local user.email "you@example.com"
~~~

Không đưa danh tính giả vào lịch sử dùng chung. Dùng thông tin tác giả phù hợp với chính sách nhóm.

## 16. Checklist hoàn thành

- [ ] git rev-parse --show-toplevel trỏ đúng thư mục dự án.
- [ ] Branch hiện tại là main.
- [ ] .gitignore và .gitattributes nằm ở root và đã được commit.
- [ ] README mô tả cấu trúc và cách bắt đầu.
- [ ] Mã nguồn Java được commit và biên dịch thành công.
- [ ] build/classes/ được tạo nhưng bị ignore.
- [ ] git check-ignore -v chỉ ra đúng quy tắc bỏ qua file sinh ra.
- [ ] git ls-files -- build/ không liệt kê file build.
- [ ] Có ít nhất ba commit với thông điệp riêng, mô tả đúng mục đích.
- [ ] git log --oneline --graph hiển thị chuỗi commit theo thứ tự mong đợi.
- [ ] git status --short không còn thay đổi chưa commit.
- [ ] Clone sạch có thể biên dịch và chạy mà không cần file build từ máy gốc.

## 17. Bài tập mở rộng

1. Thêm src/test/README.md mô tả cách tổ chức test và commit riêng với thông điệp test: document test layout.
2. Tạo file .env.example chỉ có tên biến và placeholder, sau đó xác nhận file được phép stage trong khi .env vẫn bị ignore.
3. Tạo một file log trong build/ và một file log ở root; kiểm tra cả hai có bị ignore theo quy tắc hiện tại không.
4. Tạo một file .txt trong thư mục docs/, chạy git check-attr text eol -- docs/example.txt để quan sát attribute được áp dụng.
5. Dùng git add -p để stage một phần thay đổi trong README và tạo một commit riêng.
6. Tạo thêm một commit sửa thông điệp README, rồi dùng git show để so sánh commit mới với commit trước.

Sau mỗi bài tập, hãy kiểm tra git status, git diff --cached và git log. Mỗi commit nên thể hiện một thay đổi có thể giải thích độc lập.

## 18. Ghi nhớ

Một repository ban đầu tốt bắt đầu từ đúng root và có cấu trúc đủ rõ để người khác hiểu, build và kiểm tra dự án. Hãy tạo .gitignore trước khi sinh output để tránh đưa cache, bytecode, log và cấu hình local vào lịch sử; dùng .gitattributes để thống nhất cách xử lý line ending và file nhị phân. Stage theo từng nhóm có chủ đích, review index trước commit và chia quá trình khởi tạo thành các commit nhỏ. Cuối cùng, kiểm tra clone sạch: nếu dự án chỉ build được trên máy người tạo vì có file sinh ra hoặc cấu hình cá nhân chưa được ghi lại, repository vẫn chưa sẵn sàng để cộng tác.
