# Cấu hình `JAVA_HOME`, `ANT_HOME` và `PATH`

Để chạy Apache Ant ổn định, máy cần có JDK và Apache Ant được cài đặt đúng chỗ. Ba biến môi trường `JAVA_HOME`, `ANT_HOME` và `PATH` giúp hệ điều hành cùng các tập lệnh của Ant tìm được Java và chương trình Ant mà không phải nhập đường dẫn đầy đủ mỗi lần chạy.

## 1. Vai trò của từng biến

| Biến | Giá trị cần trỏ tới | Mục đích |
|---|---|---|
| `JAVA_HOME` | Thư mục gốc của JDK | Cho Ant và các công cụ Java biết bộ JDK đang sử dụng |
| `ANT_HOME` | Thư mục gốc của Apache Ant | Cho các tập lệnh Ant tìm thư viện và tệp cài đặt của Ant |
| `PATH` | Danh sách các thư mục chứa chương trình thực thi | Cho phép gọi `java`, `javac` và `ant` từ bất kỳ thư mục làm việc nào |

Ví dụ, nếu JDK được cài ở `C:\Program Files\Java\jdk-21` và Ant được giải nén ở `C:\tools\apache-ant-<version>`, cấu hình sẽ có dạng:

```text
JAVA_HOME = C:\Program Files\Java\jdk-21
ANT_HOME  = C:\tools\apache-ant-<version>
PATH      = ...;%JAVA_HOME%\bin;%ANT_HOME%\bin;...
```

Hai biến `JAVA_HOME` và `ANT_HOME` phải trỏ tới **thư mục gốc**, không trỏ thẳng vào thư mục `bin`:

```text
JDK root
├── bin
│   ├── java.exe
│   └── javac.exe
└── ...

Ant root
├── bin
│   └── ant.bat
├── lib
│   └── ant.jar
└── ...
```

`JAVA_HOME` nên trỏ tới một JDK đầy đủ. Chỉ có môi trường chạy Java (JRE) có thể đủ để chạy một số chương trình Java, nhưng không cung cấp trình biên dịch `javac`; các tác vụ Ant biên dịch mã nguồn Java cần JDK.

## 2. Chuẩn bị JDK và Apache Ant

Trước khi sửa biến môi trường, hãy cài JDK và tải bản phân phối nhị phân của Apache Ant.

1. Cài một JDK tương thích với dự án. Ghi lại đường dẫn thư mục gốc sau khi cài đặt, chẳng hạn `C:\Program Files\Java\jdk-21`. Tên thư mục thực tế phụ thuộc nhà cung cấp và phiên bản JDK.
2. Tải gói binary distribution của Apache Ant từ trang tải chính thức của Apache Ant.
3. Giải nén Ant vào một thư mục cố định, ví dụ `C:\tools\apache-ant-<version>`. Sau khi giải nén, thư mục này cần có các thư mục con như `bin` và `lib`.
4. Kiểm tra trực tiếp rằng JDK có `bin\java.exe`, `bin\javac.exe` và Ant có `bin\ant.bat`.

Nên dùng đường dẫn cài đặt ổn định. Nếu di chuyển hoặc đổi tên thư mục JDK/Ant sau khi cấu hình, cần cập nhật lại các biến môi trường tương ứng.

## 3. Cấu hình trên Windows

### 3.1. Mở cửa sổ Environment Variables

1. Nhấn `Win + R`, nhập `sysdm.cpl`, rồi nhấn Enter.
2. Mở thẻ **Advanced**.
3. Chọn **Environment Variables...**.

Trong cửa sổ này có hai vùng:

- **User variables**: chỉ áp dụng cho tài khoản Windows hiện tại. Đây thường là lựa chọn phù hợp khi tự thiết lập môi trường học tập hoặc phát triển.
- **System variables**: áp dụng cho mọi tài khoản trên máy; việc chỉnh sửa thường cần quyền quản trị viên.

Chọn một phạm vi nhất quán. Tránh tạo hai biến cùng tên ở cả hai vùng với giá trị khác nhau vì điều đó dễ khiến mỗi cửa sổ ứng dụng nhận được cấu hình khó dự đoán.

### 3.2. Tạo `JAVA_HOME`

Trong vùng đã chọn, tìm biến `JAVA_HOME`:

- Nếu chưa có, chọn **New...**.
- Nếu đã có, chọn biến đó rồi nhấn **Edit...**.
- Đặt tên biến là `JAVA_HOME`.
- Đặt giá trị là đường dẫn thư mục gốc của JDK, ví dụ `C:\Program Files\Java\jdk-21`.

Không thêm `\bin` vào cuối giá trị. Đường dẫn cần tồn tại và bên trong phải có thư mục `bin` chứa `java.exe` cùng `javac.exe`.

### 3.3. Tạo `ANT_HOME`

Tương tự, tạo hoặc sửa biến `ANT_HOME` với giá trị là thư mục gốc nơi đã giải nén Apache Ant, ví dụ:

```text
C:\tools\apache-ant-<version>
```

Không đặt giá trị thành `C:\tools\apache-ant-<version>\bin`. Tập lệnh Ant nằm trong `bin`, còn `ANT_HOME` đại diện cho toàn bộ thư mục cài đặt.

### 3.4. Thêm thư mục vào `Path`

Trong cùng vùng User variables hoặc System variables, chọn biến `Path` rồi nhấn **Edit...**. Nếu giao diện hiển thị mỗi đường dẫn trên một dòng, chọn **New** để thêm lần lượt:

```text
%JAVA_HOME%\bin
%ANT_HOME%\bin
```

Giữ nguyên các mục `Path` đang có. Không xóa toàn bộ `Path` và không thay giá trị hiện tại chỉ bằng hai dòng trên, vì các chương trình khác của Windows có thể cần những mục đã tồn tại.

Nếu cửa sổ đang hiển thị `Path` dưới dạng một chuỗi, các mục được phân cách bằng dấu chấm phẩy (`;`). Khi đó, thêm hai mục vào chuỗi hiện có và bảo đảm chúng được phân cách đúng.

Nhấn **OK** để đóng từng cửa sổ và lưu thay đổi.

### 3.5. Kiểm tra bằng cửa sổ mới

Đóng Command Prompt hoặc PowerShell đang mở, sau đó mở một cửa sổ mới. Tiến trình đã chạy thường giữ bản sao môi trường tại thời điểm nó khởi động nên không tự nhận thay đổi vừa lưu. Nếu dùng IDE, có thể cần khởi động lại IDE để IDE nhận `JAVA_HOME` và `Path` mới.

Trong Command Prompt, chạy:

```bat
echo %JAVA_HOME%
echo %ANT_HOME%
where java
where javac
where ant
java -version
javac -version
ant -version
```

Trong PowerShell, có thể chạy các lệnh tương đương:

```powershell
$env:JAVA_HOME
$env:ANT_HOME
where.exe java
where.exe javac
where.exe ant
java -version
javac -version
ant -version
```

Kết quả mong đợi:

- `JAVA_HOME` hiển thị đúng thư mục gốc JDK.
- `ANT_HOME` hiển thị đúng thư mục gốc Apache Ant.
- `where java` và `where javac` tìm thấy chương trình trong thư mục `bin` của JDK dự kiến.
- `where ant` tìm thấy `ant.bat` trong thư mục `bin` của Ant.
- `java -version`, `javac -version` và `ant -version` hiển thị thông tin phiên bản thay vì báo không nhận diện được lệnh.

Nếu máy có nhiều phiên bản Java hoặc Ant, `where` có thể liệt kê nhiều kết quả. Windows thường sử dụng kết quả đầu tiên phù hợp trong `Path`; hãy kiểm tra thứ tự để chắc chắn chương trình đang gọi đúng phiên bản mong muốn.

## 4. Thử cấu hình tạm thời trên Windows

Khi muốn kiểm tra đường dẫn trước khi lưu cấu hình lâu dài, có thể đặt biến trong một cửa sổ terminal. Các lệnh dưới đây chỉ có hiệu lực trong cửa sổ hiện tại và các tiến trình được khởi chạy từ cửa sổ đó.

Với Command Prompt:

```bat
set "JAVA_HOME=C:\Program Files\Java\jdk-21"
set "ANT_HOME=C:\tools\apache-ant-<version>"
set "PATH=%JAVA_HOME%\bin;%ANT_HOME%\bin;%PATH%"

java -version
javac -version
ant -version
```

Với PowerShell:

```powershell
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-21'
$env:ANT_HOME = 'C:\tools\apache-ant-<version>'
$env:Path = "$env:JAVA_HOME\bin;$env:ANT_HOME\bin;$env:Path"

java -version
javac -version
ant -version
```

Thay các đường dẫn ví dụ bằng vị trí thực tế trên máy. Cú pháp `set` của Command Prompt và `$env:` của PowerShell là hai cách đặt biến khác nhau; không dùng lẫn cú pháp giữa hai loại terminal.

## 5. Cấu hình trên Linux và macOS

Trên Linux và macOS, tên biến vẫn là `JAVA_HOME` và `ANT_HOME`, nhưng cách phân cách các thư mục trong `PATH` là dấu hai chấm (`:`), không phải dấu chấm phẩy.

Trước tiên, xác định đường dẫn JDK và thư mục cài đặt Ant. Ví dụ, một máy Linux có thể dùng `/usr/lib/jvm/java-21-openjdk` cho JDK; một máy macOS có thể lấy đường dẫn JDK bằng lệnh `/usr/libexec/java_home`. Đường dẫn thực tế phụ thuộc cách cài đặt và nhà cung cấp.

Nếu đã giải nén bản phân phối Ant thủ công, thêm cấu hình vào tệp khởi tạo shell phù hợp. Ví dụ với Bash (`~/.bashrc`) hoặc Zsh (`~/.zshrc`):

```sh
export JAVA_HOME="/path/to/jdk"
export ANT_HOME="/path/to/apache-ant"
export PATH="$JAVA_HOME/bin:$ANT_HOME/bin:$PATH"
```

Thay `/path/to/jdk` và `/path/to/apache-ant` bằng đường dẫn thực tế. Lưu tệp rồi nạp lại cấu hình trong terminal hiện tại, ví dụ:

```sh
source ~/.bashrc
```

Với Zsh, dùng `source ~/.zshrc`. Trên macOS, tùy cách mở terminal và cấu hình đăng nhập, biến môi trường có thể cần được đặt trong `~/.zprofile` thay vì `~/.zshrc` để các ứng dụng được mở từ môi trường đăng nhập nhận được chúng.

Kiểm tra cấu hình:

```sh
printf '%s\n' "$JAVA_HOME" "$ANT_HOME"
command -v java
command -v javac
command -v ant
java -version
javac -version
ant -version
```

Nếu cài Ant bằng trình quản lý gói của hệ điều hành, lệnh `ant` có thể đã tự thiết lập đường dẫn cần thiết và `ANT_HOME` có thể không bắt buộc. Hãy kiểm tra cách đóng gói của bản Ant đang dùng trước khi tự đặt một giá trị `ANT_HOME` khác.

## 6. Chạy thử Apache Ant trong dự án

Sau khi các lệnh kiểm tra phiên bản hoạt động, chuyển terminal tới thư mục dự án có tệp `build.xml` rồi chạy:

```sh
ant -version
ant
```

Lệnh `ant` không kèm tên target sẽ chạy target mặc định được khai báo trong `build.xml`. Nếu muốn chạy một target cụ thể, dùng:

```sh
ant compile
```

Trong ví dụ trên, `compile` phải là tên target thực sự tồn tại trong `build.xml` của dự án. Cấu hình biến môi trường giúp tìm chương trình Java và Ant; nó không tự tạo target, không thay thế `build.xml` và cũng không quyết định thứ tự các tác vụ build.

Có thể xem thông tin chẩn đoán của Ant bằng:

```sh
ant -diagnostics
```

Thông tin này hữu ích khi cần kiểm tra Ant đang nhận Java, thư viện và môi trường nào.

## 7. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `java` không được nhận diện | `JAVA_HOME\bin` hoặc thư mục Java chưa có trong `Path`, hoặc terminal chưa được mở lại | Kiểm tra `JAVA_HOME`, thêm đúng thư mục `bin` vào `Path`, mở terminal mới |
| `javac` không được nhận diện nhưng `java` chạy được | Đang trỏ tới JRE hoặc một thư mục Java không có bộ công cụ phát triển | Cài JDK và đặt `JAVA_HOME` tới thư mục gốc của JDK |
| `ant` không được nhận diện | `ANT_HOME` sai, thiếu `ANT_HOME\bin` trong `Path`, hoặc giải nén Ant chưa đúng cấp thư mục | Kiểm tra thư mục có `bin\ant.bat`, sửa `ANT_HOME` và `Path` |
| `JAVA_HOME` hoặc `ANT_HOME` hiển thị kèm `\bin` | Đã đặt biến tới thư mục con thay vì thư mục gốc | Xóa phần `\bin` khỏi giá trị biến; giữ `\bin` trong mục `Path` |
| `ant` chạy nhưng không tìm thấy Java | `JAVA_HOME` trỏ sai hoặc Java không có trong `Path` | Kiểm tra đường dẫn JDK và chạy lại `java -version`, `javac -version` |
| Chạy sai phiên bản Java hoặc Ant | Có nhiều bản cài đặt và bản khác đứng trước trong `Path` | Dùng `where.exe java` / `where.exe ant` trên Windows hoặc `command -v` trên Linux/macOS; điều chỉnh thứ tự `Path` |
| Terminal nhận cấu hình mới nhưng IDE vẫn dùng cấu hình cũ | IDE được mở trước khi thay đổi biến môi trường | Đóng và mở lại IDE; kiểm tra cấu hình JDK riêng trong IDE nếu có |
| Cấu hình trên Linux/macOS không có hiệu lực | Sửa nhầm tệp khởi tạo shell hoặc chưa nạp lại tệp | Xác định shell đang dùng, sửa đúng `.bashrc`, `.zshrc` hoặc tệp đăng nhập tương ứng rồi mở terminal mới hoặc chạy `source` |

Một lưu ý quan trọng trên Windows: tránh dùng `setx PATH ...` với toàn bộ chuỗi `Path` hiện tại nếu chưa hiểu rõ cách lệnh xử lý giá trị. Việc ghi đè hoặc làm mất các mục có sẵn có thể khiến những lệnh khác không còn hoạt động. Giao diện **Environment Variables** là cách trực quan để thêm từng mục mà vẫn giữ các mục hiện hữu.

## 8. Checklist hoàn tất

Trước khi chạy build, hãy xác nhận:

- [ ] `JAVA_HOME` trỏ tới thư mục gốc của JDK.
- [ ] Thư mục `%JAVA_HOME%\bin` trên Windows hoặc `$JAVA_HOME/bin` trên Linux/macOS có `java` và `javac`.
- [ ] `ANT_HOME` trỏ tới thư mục gốc của Apache Ant nếu đang quản lý Ant bằng bản phân phối giải nén thủ công.
- [ ] Thư mục `bin` của Ant có trong `Path`.
- [ ] `java -version`, `javac -version` và `ant -version` đều chạy được trong terminal mới.
- [ ] Nếu có nhiều phiên bản cài đặt, phiên bản được tìm thấy đầu tiên là phiên bản dự định sử dụng.

Khi các điều kiện trên đạt, terminal đã có thể tìm thấy JDK và Apache Ant để thực thi các build script của dự án.
