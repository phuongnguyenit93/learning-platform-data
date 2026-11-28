# Hành vi với tệp ẩn, symbolic link và yêu cầu vượt ra ngoài thư mục gốc

## 1. Phạm vi tài nguyên mà jwebserver cho phép truy cập

Từ **Java 18**, JDK cung cấp **Simple Web Server** qua lệnh `jwebserver` để phục vụ tệp tĩnh trong quá trình phát triển, thử nghiệm và gỡ lỗi. Tính năng này vẫn được hỗ trợ trên JDK hiện đại, bao gồm JDK 27.

Server phục vụ một cây thư mục được chọn làm **document root** bằng tùy chọn `-d` hoặc `--directory`. Khi nhận request, server ánh xạ URI path vào cây thư mục này rồi kiểm tra tài nguyên trước khi trả nội dung.

Có ba nhóm đường dẫn cần chú ý:

- **Tệp ẩn (hidden files):** không được liệt kê trong directory listing và không được phục vụ khi yêu cầu trực tiếp.
- **Symbolic link:** không được liệt kê hoặc phục vụ. Quy tắc này áp dụng cả khi symbolic link nằm ở một thư mục cha trong đường dẫn yêu cầu.
- **Đường dẫn vượt ra ngoài document root:** sau khi giải quyết và chuẩn hóa đường dẫn, server kiểm tra tài nguyên vẫn nằm trong cây gốc. Yêu cầu đi ra ngoài cây đó không được phục vụ.

Ví dụ, với document root:

```text
demo/
├── public/
│   ├── index.html
│   ├── docs/
│   │   └── guide.html
│   ├── .env
│   ├── .private/
│   │   └── notes.txt
│   └── shared-link -> ../private-data.txt
├── private-data.txt
└── README.md
```

Server được chạy với:

```sh
jwebserver -b 127.0.0.1 -p 8080 -d ./public
```

Các URL hợp lệ như `/` hoặc `/docs/guide.html` có thể trả nội dung tương ứng. Các URL trỏ tới `/.env`, `/.private/notes.txt` hoặc `/shared-link` không được phục vụ. Một request cố đi lên thư mục cha để đọc `private-data.txt` cũng không được phép.

> **Phạm vi sử dụng:** Simple Web Server là công cụ HTTP tĩnh dành cho phát triển, thử nghiệm và gỡ lỗi. Nó không có xác thực người dùng, phân quyền ứng dụng hoặc HTTPS. Không dùng nó làm ranh giới bảo mật để chia sẻ cây thư mục chứa dữ liệu nhạy cảm.

## 2. Tệp ẩn được nhận diện như thế nào?

Tài liệu Java SE mô tả rằng hidden files không được liệt kê hoặc phục vụ. Cách một tệp được xem là ẩn phụ thuộc hệ điều hành và file system provider.

| Hệ điều hành | Quy ước thường gặp |
| --- | --- |
| Linux và macOS | Tên bắt đầu bằng dấu chấm, ví dụ `.env`, `.ssh`, `.git`. |
| Windows | Tệp hoặc thư mục có thuộc tính DOS `hidden`. |
| File system provider khác | Theo định nghĩa hidden mà provider hỗ trợ. |

Java NIO cung cấp `Files.isHidden(Path)` để kiểm tra trạng thái này. API không định nghĩa một quy tắc tên tệp duy nhất cho mọi hệ điều hành; kết quả có thể phụ thuộc provider.

### 2.1. Ví dụ trên Linux và macOS

Tạo một tệp ẩn:

```sh
cd demo/public
printf 'do-not-publish\n' > .env
mkdir .private
printf 'private note\n' > .private/notes.txt
```

Nếu server phục vụ thư mục `public`, các URL sau không được phục vụ:

```text
http://127.0.0.1:8080/.env
http://127.0.0.1:8080/.private/
http://127.0.0.1:8080/.private/notes.txt
```

Tên bắt đầu bằng dấu chấm là quy ước hidden phổ biến trên hệ Unix. Không nên đổi tên một tệp bí mật thành tên bình thường rồi cho rằng server sẽ tự nhận biết nội dung của nó là nhạy cảm.

### 2.2. Ví dụ trên Windows

Windows có thể đánh dấu tệp hoặc thư mục bằng thuộc tính hidden. Trong PowerShell hoặc Command Prompt, có thể dùng:

```powershell
Set-Location .\demo\public
Set-Content -LiteralPath '.\internal-notes.txt' -Value 'do-not-publish'
attrib +h .\internal-notes.txt
Get-Item -Force .\internal-notes.txt | Format-List Name, Attributes
```

Sau khi đặt thuộc tính hidden, thử truy cập:

```text
http://127.0.0.1:8080/internal-notes.txt
```

Theo quy tắc của Simple Web Server, tệp được nhận diện là hidden không được phục vụ. Lưu ý thuộc tính hidden của Windows chỉ là thuộc tính file system; nó không phải mã hóa hay cơ chế cấp quyền truy cập.

### 2.3. Hidden file ở một thành phần cha

Không chỉ tệp cuối cùng mới được kiểm tra. Nếu URI path đi qua một thư mục ẩn, request tới tệp con bên trong cũng bị từ chối.

Ví dụ:

```text
public/
└── .private/
    └── notes.txt
```

Các request đều không được phục vụ:

```text
/.private
/.private/
/.private/notes.txt
```

Điều này quan trọng vì nếu chỉ kiểm tra tên tệp cuối, người dùng có thể truy cập một tệp bình thường nằm bên trong thư mục ẩn. Implementation Simple Web Server kiểm tra từng thành phần đường dẫn bên dưới document root; thành phần ẩn khiến việc ánh xạ dừng lại.

## 3. Symbolic link không được liệt kê hoặc phục vụ

### 3.1. Symbolic link là gì?

Symbolic link (symlink) là một mục trong file system trỏ tới một đường dẫn khác. Target có thể nằm trong cùng cây thư mục hoặc ở một vị trí bên ngoài document root.

Ví dụ trên Linux/macOS:

```sh
cd demo/public
ln -s ../private-data.txt private-link.txt
ln -s ../private-folder private-folder-link
```

Cấu trúc sau khi tạo link:

```text
demo/
├── public/
│   ├── index.html
│   ├── private-link.txt -> ../private-data.txt
│   └── private-folder-link -> ../private-folder
├── private-data.txt
└── private-folder/
    └── credentials.txt
```

Dù target có thể đọc được bằng đường dẫn file system, Simple Web Server không liệt kê và không phục vụ symbolic link.

### 3.2. Link tới tệp và link tới thư mục đều bị từ chối

Giả sử server phục vụ `demo/public`. Các request sau không được phục vụ:

```text
/private-link.txt
/private-folder-link/
/private-folder-link/credentials.txt
```

Không quan trọng target nằm ngoài hay bên trong document root: chính mục symbolic link bị loại khỏi phạm vi phục vụ.

Một link thư mục có thể làm nhiều tệp bên ngoài cây gốc xuất hiện như thư mục con nếu server theo link. Vì vậy, Simple Web Server từ chối link thay vì tự động đi theo target.

### 3.3. Symbolic link ở thành phần trung gian cũng bị từ chối

Xét cấu trúc:

```text
public/
└── docs-link -> ../external-docs/
    └── guide.html
```

Request:

```text
/docs-link/guide.html
```

cũng bị từ chối. Server kiểm tra các thành phần trên đường dẫn; nếu một thành phần là symbolic link, request không được ánh xạ tiếp tới tệp đích.

Đây là điểm khác với việc chỉ ẩn tên link trong directory listing. Kể cả khi client đoán được tên link, yêu cầu trực tiếp cũng không được phục vụ.

### 3.4. Tạo symbolic link trên Windows

Có thể tạo symbolic link bằng PowerShell:

```powershell
New-Item -ItemType SymbolicLink -Path '.\demo\public\private-link.txt' -Target '.\demo\private-data.txt'
```

Tùy cấu hình Windows, việc tạo symbolic link có thể cần quyền phù hợp hoặc Developer Mode. Nếu hệ thống không hỗ trợ hoặc không cấp quyền, lệnh có thể thất bại; khi đó hãy kiểm tra thuộc tính link bằng:

```powershell
Get-Item -Force '.\demo\public\private-link.txt' |
  Format-List FullName, LinkType, Target, Attributes
```

Không nhầm shortcut của Windows (`.lnk`) với symbolic link của file system. Shortcut thông thường là một tệp riêng, còn symbolic link là loại liên kết mà API file system nhận diện qua `Files.isSymbolicLink(Path)`.

## 4. Yêu cầu vượt ra ngoài document root

### 4.1. Path traversal là gì?

Path traversal (directory traversal) là tình huống đường dẫn do client gửi khiến server truy cập tệp nằm ngoài thư mục gốc mà ứng dụng định phục vụ. Thành phần `..` biểu thị thư mục cha trong đường dẫn file system.

Giả sử:

```text
/srv/demo/
├── public/
│   └── index.html
└── secret.txt
```

Document root là `/srv/demo/public`. Nếu server ghép URI path một cách thiếu kiểm soát, request có thành phần `../` có thể khiến đường dẫn được giải quyết thành:

```text
/srv/demo/public/../secret.txt
```

Sau khi chuẩn hóa, đường dẫn đó trở thành:

```text
/srv/demo/secret.txt
```

Tệp đích nằm ngoài document root. Một file server phải từ chối request này.

### 4.2. Chuẩn hóa đường dẫn và kiểm tra containment

Implementation OpenJDK của Simple Web Server thực hiện các bước chính khi ánh xạ request:

1. Lấy URI path tương đối với HTTP context.
2. Tách path thành các thành phần.
3. Lần lượt giải quyết từng thành phần dưới thư mục root.
4. Kiểm tra thành phần có được phép hỗ trợ, có thể đọc, không ẩn và không phải symbolic link.
5. Chuẩn hóa đường dẫn bằng `Path.normalize()`.
6. Xác nhận đường dẫn đã chuẩn hóa vẫn nằm trong root bằng phép so sánh thành phần của `Path.startsWith(root)`.
7. Nếu đường dẫn không hợp lệ hoặc ra ngoài root, xử lý như tài nguyên không tìm thấy.

Sơ đồ:

```text
Document root: /srv/demo/public
Request path:  /../secret.txt
                 |
                 v
Resolve under root
/srv/demo/public/../secret.txt
                 |
                 v
Normalize
/srv/demo/secret.txt
                 |
                 v
Path startsWith(root)?
          /              \
        No                Yes
        |                  |
        v                  v
     Reject             Continue
      404               file checks
```

Điểm quan trọng là kiểm tra containment phải dùng đối tượng `Path` và ranh giới thành phần đường dẫn. Không nên chỉ so sánh chuỗi bằng `String.startsWith`: một đường dẫn như `/srv/demo/public-backup` bắt đầu bằng chuỗi `/srv/demo/public` nhưng không nằm trong thư mục `public`.

### 4.3. Vì sao yêu cầu vượt root nhận 404?

Khi đường dẫn không thể ánh xạ hợp lệ vào document root, Simple Web Server trả phản hồi không tìm thấy tài nguyên, thường là `404 Not Found`.

Phản hồi 404 chung cũng được dùng cho những trường hợp như đường dẫn chứa thành phần ẩn, symbolic link hoặc không đọc được. Điều này tránh cho client biết rõ một mục có tồn tại nhưng bị loại khỏi phạm vi phục vụ hay không.

| Request path | Lý do bị từ chối |
| --- | --- |
| `/../secret.txt` | Sau normalize, đường dẫn nằm ngoài root. |
| `/docs/../../secret.txt` | Đường dẫn đi lên khỏi root. |
| `/.private/notes.txt` | Có thành phần hidden. |
| `/outside-link/secret.txt` | Có thành phần symbolic link. |
| `/missing.txt` | Tài nguyên không tồn tại. |

Các trường hợp này có thể cùng trả 404, vì vậy không thể chỉ dựa vào status để xác định chính xác nguyên nhân. Hãy kiểm tra cấu trúc thư mục và log ở môi trường thử nghiệm.

### 4.4. Path dạng tuyệt đối và ký tự đặc biệt

Ngoài `..`, một đường dẫn bất thường có thể chứa ký tự được file system hiểu đặc biệt. Implementation của JDK có kiểm tra thành phần URI không được hỗ trợ; ví dụ trên Windows, một segment có dạng ký tự ổ đĩa như `C:` bị loại để tránh coi nó là đường dẫn ổ đĩa trong quá trình resolve.

Đường dẫn HTTP là URI path, không phải một pathname tùy ý của hệ điều hành. Client không thể yêu cầu server mở một đường dẫn tuyệt đối tùy ý bằng cách gửi tên ổ đĩa hoặc root path trong URI.

Khi kiểm thử, nên quan sát cả dạng literal và percent-encoded. URI API có thể cung cấp path đã giải mã, nên không nên chỉ lọc chuỗi thô trước khi ánh xạ file system.

## 5. Kiểm tra trên từng thành phần của đường dẫn

Một request tới:

```text
/docs/releases/v1/manual.pdf
```

được phân tách thành các thành phần:

```text
docs
releases
v1
manual.pdf
```

Server kiểm tra lần lượt đường dẫn được tạo sau mỗi thành phần. Điều này có ba hệ quả:

- Nếu `docs` là hidden directory, mọi request bên dưới nó đều bị từ chối.
- Nếu `releases` là symbolic link, request không được đi tiếp tới `v1/manual.pdf`.
- Nếu đường dẫn sau chuẩn hóa vượt khỏi root, request bị từ chối ngay cả khi tên tệp cuối cùng là một tệp bình thường và có thể đọc.

Kiểm tra từng thành phần giúp tránh trường hợp chỉ nhìn vào thuộc tính của tệp cuối mà bỏ qua một thư mục cha ẩn, không đọc được hoặc là symbolic link.

## 6. Thực hành: kiểm tra hidden file và symbolic link

### 6.1. Tạo cây thư mục mẫu

Tạo cấu trúc:

```text
demo/
├── public/
│   ├── index.html
│   ├── visible.txt
│   ├── .hidden.txt
│   ├── .private/
│   │   └── note.txt
│   └── docs/
│       └── guide.txt
├── private-data.txt
└── private-folder/
    └── secret.txt
```

Nội dung mẫu trên Linux/macOS:

```sh
mkdir -p public/.private public/docs private-folder
printf '<h1>Public page</h1>\n' > public/index.html
printf 'Visible resource\n' > public/visible.txt
printf 'Hidden resource\n' > public/.hidden.txt
printf 'Hidden directory resource\n' > public/.private/note.txt
printf 'Documentation\n' > public/docs/guide.txt
printf 'Outside document root\n' > private-data.txt
printf 'Outside directory secret\n' > private-folder/secret.txt
```

### 6.2. Tạo symbolic link

Trên Linux/macOS:

```sh
ln -s ../private-data.txt public/private-link.txt
ln -s ../private-folder public/private-folder-link
```

Kiểm tra link:

```sh
ls -la public
readlink public/private-link.txt
```

Trên Windows PowerShell, nếu được phép tạo symlink:

```powershell
New-Item -ItemType SymbolicLink -Path '.\public\private-link.txt' -Target '..\private-data.txt'
New-Item -ItemType SymbolicLink -Path '.\public\private-folder-link' -Target '..\private-folder'
```

### 6.3. Khởi động server

Từ thư mục `demo`:

```sh
jwebserver -b 127.0.0.1 -p 8080 -d ./public -o info
```

Server chỉ phục vụ cây `public`. Mở terminal thứ hai để gửi request.

### 6.4. Kiểm tra tài nguyên bình thường

```sh
curl -i http://127.0.0.1:8080/
curl -i http://127.0.0.1:8080/visible.txt
curl -i http://127.0.0.1:8080/docs/guide.txt
```

Các tài nguyên bình thường, có thể đọc và nằm dưới document root sẽ trả phản hồi thành công, thường là `200 OK`.

### 6.5. Kiểm tra hidden file và hidden directory

```sh
curl -i http://127.0.0.1:8080/.hidden.txt
curl -i http://127.0.0.1:8080/.private/
curl -i http://127.0.0.1:8080/.private/note.txt
```

Các request này phải bị từ chối, thường nhận `404 Not Found`. Mở directory listing của `/` cũng không thấy mục ẩn.

### 6.6. Kiểm tra symbolic link

```sh
curl -i http://127.0.0.1:8080/private-link.txt
curl -i http://127.0.0.1:8080/private-folder-link/
curl -i http://127.0.0.1:8080/private-folder-link/secret.txt
```

Các request qua symbolic link không được phục vụ. Directory listing của root cũng không hiển thị các link đó.

### 6.7. Kiểm tra yêu cầu vượt root

Dùng tùy chọn `--path-as-is` của curl để giữ nguyên các thành phần dấu chấm trong request path. Nếu không, một số client có thể tự chuẩn hóa đường dẫn trước khi gửi request.

```sh
curl --path-as-is -i http://127.0.0.1:8080/../private-data.txt
curl --path-as-is -i http://127.0.0.1:8080/docs/../../private-data.txt
curl --path-as-is -i http://127.0.0.1:8080/%2e%2e/private-data.txt
```

Các request vượt khỏi document root phải bị từ chối, thường nhận `404 Not Found`. Không được nhận nội dung của `private-data.txt`.

Trên Windows, có thể thử thêm dạng separator được percent-encode trong một môi trường kiểm thử riêng:

```sh
curl --path-as-is -i "http://127.0.0.1:8080/%2e%2e%5cprivate-data.txt"
```

Kết quả thực tế có thể khác theo shell, HTTP client và cách URI được xử lý. Mục tiêu của phép thử là xác minh không có nội dung bên ngoài document root bị trả về.

### 6.8. Bảng kết quả cần quan sát

| Request | Kết quả mong đợi |
| --- | --- |
| `/visible.txt` | `200`, nội dung tệp bình thường. |
| `/.hidden.txt` | `404`, không phục vụ tệp ẩn. |
| `/.private/note.txt` | `404`, thành phần thư mục cha bị ẩn. |
| `/private-link.txt` | `404`, symbolic link không được phục vụ. |
| `/private-folder-link/secret.txt` | `404`, symbolic link ở thành phần trung gian. |
| `/../private-data.txt` | `404`, đường dẫn ra ngoài root. |
| `/%2e%2e/private-data.txt` | `404`, kiểm tra traversal ở dạng percent-encoded. |

Sau khi hoàn tất, dừng server bằng **Ctrl+C**.

## 7. Hidden file trên Windows và Unix không giống nhau

Không nên chỉ kiểm tra tên bắt đầu bằng dấu chấm rồi suy ra mọi hệ điều hành sẽ xử lý như nhau.

| Tên/thuộc tính | Linux/macOS | Windows |
| --- | --- | --- |
| `.env` | Thường được xem là hidden do tên bắt đầu bằng dấu chấm. | Không mặc nhiên hidden nếu không có thuộc tính DOS hidden. |
| `settings.ini` có DOS hidden attribute | Không có quy ước tương đương phổ biến từ tên. | Được xem là hidden nếu provider nhận diện thuộc tính. |
| `.config/secret.txt` | Thành phần thư mục hidden làm request bị từ chối. | Tên có dấu chấm không tự động đồng nghĩa thuộc tính hidden. |

Java API `Files.isHidden` giao việc nhận diện cho file system provider. Do đó, cùng một tên tệp có thể được xem là hidden trên Unix nhưng không hidden trên Windows, hoặc ngược lại nếu thuộc tính file system khác nhau.

## 8. Giới hạn bảo vệ cần hiểu

### 8.1. Hidden không phải là mã hóa

Việc một tệp không được liệt kê hoặc không được phục vụ qua `jwebserver` không có nghĩa nội dung tệp đã được mã hóa hoặc người dùng hệ điều hành khác không thể đọc nó.

Quy tắc hidden là bộ lọc khi server ánh xạ request. Nó không thay đổi quyền truy cập file system và không bảo vệ tệp khỏi tiến trình khác.

### 8.2. Symbolic link khác hard link

Simple Web Server từ chối symbolic link. **Hard link** là một directory entry khác trỏ tới cùng file object, không phải symbolic link. Việc loại trừ symbolic link không đồng nghĩa server nhận diện mọi alias hoặc mọi cách một file có thể được tham chiếu trong file system.

Không tạo hard link tới dữ liệu nhạy cảm bên trong document root rồi coi đó là cách an toàn để chia sẻ thư mục. Chỉ đặt các tệp được phép công khai trong document root.

### 8.3. Kiểm tra readability không phải phân quyền ứng dụng

Implementation kiểm tra khả năng đọc theo file system của tiến trình. Trao đổi review của OpenJDK nêu rõ Simple Web Server không thực hiện thêm mô hình kiểm tra quyền owner/group/other như một lớp kiểm soát truy cập ứng dụng.

Nếu tiến trình Java chạy bằng một tài khoản có quyền đọc nhiều dữ liệu, các tệp mà tài khoản đó đọc được có thể rộng hơn những gì người dùng dự định chia sẻ. Hãy chạy trong thư mục và tài khoản phù hợp, và giữ document root nhỏ.

### 8.4. Không dùng làm ranh giới bảo mật production

Simple Web Server được thiết kế cho prototyping, testing và debugging. Nó không cung cấp xác thực, phân quyền theo người dùng, HTTPS hoặc chính sách chia sẻ dữ liệu phức tạp.

Với dữ liệu nhạy cảm hoặc hệ thống thật, hãy dùng một máy chủ/ứng dụng có cấu hình quyền truy cập rõ ràng, kiểm tra đường dẫn và kiểm soát file system phù hợp.

## 9. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Tệp có tên bắt đầu bằng dấu chấm trả `404` trên Unix | File được xem là hidden. | Dùng `ls -la` và kiểm tra đường dẫn. |
| Tệp Windows không có dấu chấm nhưng không được phục vụ | Tệp có thuộc tính DOS hidden. | Dùng `attrib` hoặc xem thuộc tính trong PowerShell. |
| Symbolic link không xuất hiện trong listing | Đây là hành vi được thiết kế. | Dùng `ls -l` hoặc `Get-Item` để xác nhận link. |
| Tệp con trong thư mục ẩn trả `404` | Một thành phần cha của path bị hidden. | Kiểm tra từng thư mục trên đường dẫn. |
| Request qua symlink trả `404` dù target tồn tại | Server không theo symbolic link. | Kiểm tra loại file/link và yêu cầu trực tiếp target chỉ khi target nằm trong root. |
| Request `../` trả `404` | Sau chuẩn hóa, path nằm ngoài root. | Dùng `curl --path-as-is` để xác minh client đã gửi nguyên path. |
| Tệp bình thường trả `404` | Tệp không tồn tại, không đọc được, hoặc một thành phần cha bị loại. | Kiểm tra document root, quyền đọc và mọi thành phần của đường dẫn. |
| Không tạo được symlink trên Windows | Thiếu quyền, Developer Mode hoặc file system không hỗ trợ. | Kiểm tra thông báo tạo link và quyền hệ thống. |

## 10. Bài tập tự kiểm tra

1. Tạo tệp `.hidden.txt` trên Linux/macOS và tệp có thuộc tính DOS hidden trên Windows. Kiểm tra directory listing và request trực tiếp.
2. Tạo thư mục ẩn chứa một tệp có tên bình thường. Giải thích vì sao request tới tệp con vẫn bị từ chối.
3. Tạo symbolic link trỏ tới tệp bên ngoài document root. Kiểm tra cả tên link trong listing và request trực tiếp.
4. Tạo symbolic link trỏ tới một thư mục khác. Thử request tới chính link và một tệp con qua link.
5. Gửi request `/../secret.txt` bằng `curl --path-as-is`. Giải thích vai trò của bước normalize và kiểm tra containment.
6. Thử path traversal với percent-encoding, ví dụ `/%2e%2e/secret.txt`. So sánh request được gửi với response server trả.
7. Tạo thư mục anh em có tên `public-backup`. Giải thích vì sao kiểm tra `Path.startsWith(root)` an toàn hơn so sánh chuỗi tiền tố.
8. Giải thích sự khác nhau giữa symbolic link và hard link, và vì sao không nên đặt hard link tới dữ liệu nhạy cảm trong document root.
9. Giải thích vì sao `404` chung không cho biết chắc chắn tài nguyên không tồn tại.
10. Nêu các giới hạn khiến `jwebserver` không phù hợp để làm lớp bảo vệ dữ liệu production.

**Tiêu chí hoàn thành:** bạn phân biệt được hidden file theo hệ điều hành, hiểu vì sao symbolic link và mọi thành phần hidden bị từ chối, giải thích cách chuẩn hóa và xác nhận path vẫn nằm trong document root, kiểm tra được request traversal bằng curl và nhận thức đúng giới hạn bảo mật của Simple Web Server.

## 11. Tài liệu tham khảo

- [Oracle Java SE 27 — The jwebserver Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jwebserver.html): xác nhận hidden files và symbolic links không được liệt kê hoặc phục vụ; giới hạn Simple Web Server dành cho phát triển, thử nghiệm và gỡ lỗi.
- [Oracle Java SE 27 — Files.isHidden](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Files.html#isHidden(java.nio.file.Path)): định nghĩa hidden phụ thuộc nền tảng/provider; ví dụ Unix dùng tên bắt đầu bằng dấu chấm và Windows dùng thuộc tính DOS hidden.
- [Oracle Java SE 27 — Files.isSymbolicLink](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Files.html#isSymbolicLink(java.nio.file.Path)): API kiểm tra một đường dẫn có phải symbolic link hay không.
- [OpenJDK — Simple Web Server implementation review](https://www.mail-archive.com/search?f=1&l=core-libs-dev%40openjdk.java.net&o=newest&q=from%3A%22Julia+Boes%22): trao đổi review về việc kiểm tra từng thành phần path, trả 404 chung cho hidden/symlink/không đọc được và giới hạn kiểm tra quyền file system.
- [OpenJDK JEP 408 — Simple Web Server](https://openjdk.org/jeps/408): mục đích thiết kế Simple Web Server được giới thiệu trong Java 18.
