# PATH trong quá trình cài đặt JDK

## 1. PATH là gì và vì sao cần cấu hình?

PATH là một biến môi trường chứa danh sách các thư mục mà hệ điều hành hoặc shell dùng để tìm chương trình thực thi khi người dùng nhập tên lệnh. Khi gõ một lệnh như **java** hoặc **javac**, terminal cần xác định tệp chương trình tương ứng ở đâu. Nếu thư mục chứa chương trình không có trong PATH, lệnh có thể báo không tìm thấy dù JDK đã được cài đặt.

Trong JDK, các công cụ dòng lệnh thường nằm trong thư mục **bin**:

- **java**: khởi chạy ứng dụng Java.
- **javac**: biên dịch mã nguồn Java thành bytecode.
- **jar**: tạo và thao tác với tệp JAR.
- **javadoc**: sinh tài liệu API từ mã nguồn.
- **jshell**: chạy thử biểu thức và đoạn mã Java tương tác.

Ví dụ, nếu JDK được cài tại **C:\Program Files\Java\jdk-17**, thư mục cần đưa vào PATH là **C:\Program Files\Java\jdk-17\bin**. Đường dẫn thực tế phụ thuộc nhà phân phối, phiên bản và vị trí cài đặt; hãy dùng thư mục JDK đang có trên máy thay vì sao chép nguyên ví dụ.

PATH lưu thư mục, không lưu đường dẫn đến riêng tệp **java.exe** hay **javac.exe**. Vì vậy, hãy thêm thư mục **bin** của JDK.

## 2. Phân biệt PATH và JAVA_HOME

Hai biến thường được cấu hình cùng nhau nhưng có mục đích khác nhau:

- **JAVA_HOME** trỏ đến thư mục gốc của JDK.
- **PATH** chứa thư mục **bin** của JDK để có thể gọi các lệnh Java từ terminal ở bất kỳ thư mục làm việc nào.

Ví dụ trên Windows:

~~~text
JAVA_HOME = C:\Program Files\Java\jdk-17
PATH      = ...;%JAVA_HOME%\bin;...
~~~

Ví dụ trên Linux hoặc macOS:

~~~bash
export JAVA_HOME=/path/to/jdk-17
export PATH="$JAVA_HOME/bin:$PATH"
~~~

JAVA_HOME phải trỏ đến thư mục gốc JDK, không thêm **\bin** ở cuối. Các công cụ build và IDE thường đọc JAVA_HOME để biết bộ JDK cần dùng. Bản thân lệnh **java** được tìm thông qua PATH; việc đặt JAVA_HOME không tự động làm cho lệnh Java có thể chạy nếu PATH chưa chứa thư mục **bin**.

Đối với phát triển Java, nên trỏ JAVA_HOME đến một JDK đầy đủ. Một thư mục chỉ có runtime có thể chạy chương trình nhưng không cung cấp trình biên dịch **javac**.

## 3. PATH được tìm kiếm như thế nào?

Khi shell cần chạy một chương trình bên ngoài, nó tìm tên chương trình trong các thư mục PATH theo thứ tự. Thông thường, thư mục xuất hiện trước sẽ được ưu tiên nếu có nhiều chương trình trùng tên.

Dấu phân cách các thư mục phụ thuộc hệ điều hành:

| Hệ điều hành | Dấu phân cách | Ví dụ |
|---|---|---|
| Windows | Dấu chấm phẩy **;** | **C:\Java\jdk-17\bin;C:\Windows\System32** |
| Linux và macOS | Dấu hai chấm **:** | **/opt/jdk-17/bin:/usr/bin:/bin** |

Nếu máy có nhiều JDK, thứ tự PATH quyết định phiên bản nào được gọi khi nhập **java** hoặc **javac**. Ví dụ, nếu JDK 17 đứng trước JDK 21 thì lệnh có thể dùng JDK 17 dù JDK 21 cũng đã được cài đặt.

Hãy kiểm tra cả **java** và **javac**. Hai lệnh nên đến từ cùng một bản JDK. Nếu runtime thuộc một phiên bản nhưng compiler thuộc phiên bản khác, việc biên dịch và chạy có thể cho kết quả khó đoán hoặc không tương thích.

## 4. Cấu hình PATH trên Windows 10/11

### Bước 1: Xác định thư mục JDK

Tìm thư mục JDK đã cài. Một số vị trí thường gặp:

~~~text
C:\Program Files\Java\jdk-17
C:\Program Files\Eclipse Adoptium\jdk-17.0.x
C:\Program Files\Microsoft\jdk-17.x
~~~

Tên thư mục thay đổi theo nhà cung cấp và bản cập nhật. Hãy xác nhận trong File Explorer rằng thư mục đó có thư mục con **bin** và bên trong có **java.exe** cùng **javac.exe**.

### Bước 2: Mở cửa sổ Environment Variables

1. Mở **Settings** → **System** → **About**.
2. Chọn **Advanced system settings**.
3. Trong cửa sổ **System Properties**, chọn **Environment Variables**.

Có thể tìm từ Start menu bằng từ khóa **Edit the system environment variables**, sau đó chọn **Environment Variables**.

### Bước 3: Tạo JAVA_HOME

Trong phần **User variables** (biến của tài khoản hiện tại), chọn **New**:

- Variable name: **JAVA_HOME**
- Variable value: đường dẫn thư mục gốc JDK, ví dụ **C:\Program Files\Java\jdk-17**

Không thêm **\bin** vào giá trị JAVA_HOME và không đặt dấu ngoặc kép bao quanh đường dẫn trong hộp giá trị.

Nếu cần cấu hình cho tất cả tài khoản trên máy, có thể đặt biến trong **System variables**; thao tác này có thể yêu cầu quyền quản trị. Với máy cá nhân, User variables thường là đủ.

### Bước 4: Thêm JDK vào PATH

Trong cùng khu vực biến môi trường:

1. Chọn biến **Path** rồi nhấn **Edit**.
2. Chọn **New** và thêm **%JAVA_HOME%\bin**.
3. Đưa mục này lên trước các mục Java cũ nếu muốn JDK được chọn làm mặc định.
4. Nhấn **OK** để đóng và lưu tất cả các cửa sổ.

Chỉ thêm một mục mới vào danh sách Path. Không xóa toàn bộ giá trị Path hiện có, vì Windows và các ứng dụng khác cần những thư mục đã được cấu hình trước đó. Đường dẫn có khoảng trắng vẫn dùng được trong danh sách Path; không thêm dấu ngoặc kép vào mục vừa tạo.

### Cấu hình tạm thời trong PowerShell

Nếu chỉ muốn thử trong cửa sổ PowerShell hiện tại, có thể đặt biến cho tiến trình đó:

~~~powershell
$env:JAVA_HOME = 'C:\Program Files\Java\jdk-17'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
java -version
javac -version
~~~

Thay đường dẫn ví dụ bằng thư mục JDK thực tế. Thay đổi này có hiệu lực trong cửa sổ PowerShell hiện tại và các tiến trình con được khởi chạy từ đó. Đóng cửa sổ sẽ kết thúc cấu hình tạm này.

### Cấu hình tạm thời trong Command Prompt

~~~bat
set "JAVA_HOME=C:\Program Files\Java\jdk-17"
set "PATH=%JAVA_HOME%\bin;%PATH%"
java -version
javac -version
~~~

Các lệnh **set** trên chỉ thay đổi môi trường của cửa sổ Command Prompt hiện tại. Để cấu hình lâu dài, hãy dùng cửa sổ Environment Variables. Tránh tự ghép lại toàn bộ PATH bằng **setx PATH ...** khi chưa hiểu rõ cách lệnh xử lý giá trị cũ và biến tham chiếu; thao tác sai có thể làm mất các mục PATH đang cần thiết.

Sau khi lưu thay đổi qua giao diện Windows, hãy mở một cửa sổ terminal mới. Terminal đang mở trước đó thường vẫn giữ bản sao môi trường cũ.

## 5. Cấu hình PATH trên Linux

Trước tiên, xác định thư mục JDK thực tế. Nếu **javac** đã chạy được, lệnh sau cho biết đường dẫn thực của trình biên dịch trên nhiều bản phân phối Linux:

~~~bash
readlink -f "$(command -v javac)"
~~~

Ví dụ kết quả có thể là:

~~~text
/usr/lib/jvm/jdk-17/bin/javac
~~~

Trong ví dụ này, thư mục gốc JDK là **/usr/lib/jvm/jdk-17** — tức thư mục cha của **bin**. Đường dẫn trên máy có thể khác nếu JDK được cài bằng package manager hoặc đặt ở vị trí riêng.

Mở tệp cấu hình của shell đang dùng. Với Bash tương tác, thường là **~/.bashrc**; với Zsh tương tác, thường là **~/.zshrc**. Một số môi trường đăng nhập đọc **~/.profile**; hãy chọn tệp phù hợp với cách terminal khởi chạy shell để tránh khai báo trùng lặp.

Thêm hai dòng sau và thay đường dẫn mẫu bằng thư mục JDK trên máy:

~~~bash
export JAVA_HOME="/usr/lib/jvm/jdk-17"
export PATH="$JAVA_HOME/bin:$PATH"
~~~

Lưu tệp, sau đó nạp lại cấu hình. Ví dụ với Bash:

~~~bash
source ~/.bashrc
~~~

Hoặc với Zsh:

~~~bash
source ~/.zshrc
~~~

Có thể đóng rồi mở terminal mới để nhận môi trường đã cập nhật. Đặt **$JAVA_HOME/bin** ở đầu PATH giúp ưu tiên JDK được chọn trước các lệnh Java khác đã có trên hệ thống.

## 6. Cấu hình PATH trên macOS

macOS cung cấp công cụ **/usr/libexec/java_home** để tìm JDK đã cài. Liệt kê các bản JDK được nhận diện:

~~~bash
/usr/libexec/java_home -V
~~~

Để chọn JDK 17, có thể dùng:

~~~bash
export JAVA_HOME=$(/usr/libexec/java_home -v 17)
export PATH="$JAVA_HOME/bin:$PATH"
~~~

Lệnh trên đặt JAVA_HOME theo JDK 17 đã cài trên máy và thêm thư mục **bin** vào đầu PATH. Nếu đang dùng phiên bản khác, thay **17** bằng phiên bản mong muốn đã được cài đặt.

Để cấu hình lâu dài, macOS hiện thường dùng Zsh làm shell mặc định. Thêm hai dòng cấu hình vào **~/.zshrc**:

~~~bash
export JAVA_HOME=$(/usr/libexec/java_home -v 17)
export PATH="$JAVA_HOME/bin:$PATH"
~~~

Sau đó nạp lại:

~~~bash
source ~/.zshrc
~~~

Nếu đang dùng Bash, hãy đặt cấu hình trong tệp khởi tạo mà shell của bạn thực sự đọc, thường là **~/.bash_profile** hoặc **~/.bashrc**. Có thể dùng **/usr/libexec/java_home -V** để kiểm tra các phiên bản JDK mà macOS nhận diện.

## 7. Kiểm tra cấu hình

Sau khi cấu hình, mở terminal mới và kiểm tra JAVA_HOME, vị trí chương trình được tìm thấy và phiên bản thực tế.

### Windows PowerShell

~~~powershell
$env:JAVA_HOME
Get-Command java -All
Get-Command javac -All
where.exe java
where.exe javac
java -version
javac -version
~~~

**where.exe** liệt kê các tệp có thể được tìm thấy theo PATH. Dòng đầu tiên thường là mục được ưu tiên khi gọi lệnh bên ngoài cùng tên. **Get-Command -All** còn giúp nhận diện alias hoặc command khác có thể ảnh hưởng đến việc phân giải lệnh trong PowerShell.

### Windows Command Prompt

~~~bat
echo %JAVA_HOME%
where java
where javac
java -version
javac -version
~~~

### Linux và macOS

~~~bash
printf '%s\n' "$JAVA_HOME"
command -v java
command -v javac
type -a java javac
java -version
javac -version
~~~

Một cấu hình đúng thường đáp ứng các điều kiện sau:

- JAVA_HOME trỏ đến thư mục gốc của JDK đã chọn.
- Đường dẫn tìm được cho **java** và **javac** thuộc cùng JDK.
- **java -version** và **javac -version** hiển thị phiên bản mong muốn.
- Không có một JDK cũ hoặc một đường dẫn Java khác đứng trước JDK đã chọn trong PATH.

Lưu ý: **java -version** cho biết runtime đang chạy; **javac -version** xác nhận trình biên dịch JDK có thể được gọi. Chỉ kiểm tra một trong hai lệnh là chưa đủ để phát hiện mọi trường hợp PATH bị trộn nhiều phiên bản.

## 8. Thử biên dịch và chạy một chương trình Java

Tạo tệp **Hello.java** với nội dung:

~~~java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello, Java!");
    }
}
~~~

Mở terminal tại thư mục chứa tệp rồi chạy:

~~~bash
javac Hello.java
java Hello
~~~

Kết quả chuẩn:

~~~text
Hello, Java!
~~~

Ví dụ này kiểm tra hai phần của JDK qua PATH: lệnh **javac** phải tìm được trình biên dịch để tạo **Hello.class**, sau đó lệnh **java** phải tìm được runtime để chạy lớp **Hello**. Nếu cả hai lệnh chạy đúng và cho ra kết quả trên, cấu hình cơ bản đã hoạt động.

PATH chỉ giúp tìm chương trình thực thi. Nó không tự tìm tệp nguồn ở mọi thư mục. Khi chạy ví dụ, terminal vẫn cần đang ở thư mục chứa **Hello.java** hoặc bạn phải cung cấp đường dẫn thích hợp đến tệp.

## 9. Lỗi thường gặp và cách xử lý

### Lỗi “java is not recognized” hoặc “command not found”

Nguyên nhân thường gặp:

- Chưa thêm thư mục **bin** của JDK vào PATH.
- Đường dẫn nhập sai hoặc trỏ đến thư mục không tồn tại.
- Đã sửa PATH nhưng vẫn dùng terminal mở từ trước.
- Đã đặt JAVA_HOME nhưng quên thêm JAVA_HOME/bin vào PATH.

Cách xử lý: kiểm tra thư mục JDK có **java** hay không, kiểm tra mục PATH, lưu lại rồi mở terminal mới. Trên Windows có thể dùng **where.exe java**; trên Linux/macOS có thể dùng **command -v java**.

### Lệnh java chạy được nhưng javac không tìm thấy

Có thể PATH đang trỏ đến một runtime-only installation hoặc một thư mục Java không chứa compiler. Hãy xác nhận đã cài JDK đầy đủ và mục PATH trỏ đến đúng thư mục **bin** của JDK đó. Sau đó kiểm tra lại bằng **javac -version**.

### Phiên bản Java không đúng mong muốn

Máy có thể đang có nhiều JDK hoặc một đường dẫn Java cũ đứng trước đường dẫn mới. Dùng **where.exe java** và **where.exe javac** trên Windows, hoặc **type -a java javac** trên Linux/macOS để xem tất cả vị trí được tìm thấy. Đưa thư mục **bin** của JDK muốn dùng lên trước, loại bỏ mục cũ chỉ khi chắc chắn không còn cần, rồi mở terminal mới và kiểm tra lại.

### JAVA_HOME trỏ sai vị trí

JAVA_HOME phải trỏ đến thư mục gốc JDK. Ví dụ, giá trị nên kết thúc ở **jdk-17**, không phải **jdk-17\bin**. Sau đó PATH mới tham chiếu đến **%JAVA_HOME%\bin** trên Windows hoặc **$JAVA_HOME/bin** trên Linux/macOS.

### Dùng sai dấu phân cách

Trên Windows, các thư mục trong PATH ngăn cách bằng dấu chấm phẩy. Trên Linux và macOS, chúng ngăn cách bằng dấu hai chấm. Dùng sai dấu phân cách có thể khiến toàn bộ chuỗi bị hiểu thành một mục đường dẫn không hợp lệ.

### Vô tình ghi đè PATH

Không thay toàn bộ PATH bằng duy nhất thư mục JDK. PATH còn chứa thư mục hệ thống và công cụ khác. Khi cấu hình, chỉ thêm mục JDK vào danh sách hiện có và giữ lại những mục cần thiết.

## 10. Checklist hoàn tất

- [ ] Đã cài JDK đầy đủ, không chỉ runtime.
- [ ] JAVA_HOME trỏ đến thư mục gốc của JDK.
- [ ] PATH chứa thư mục **bin** của JDK.
- [ ] Dùng đúng dấu phân cách theo hệ điều hành.
- [ ] Đã mở terminal mới sau khi thay đổi biến môi trường.
- [ ] **java -version** và **javac -version** hiển thị phiên bản mong muốn.
- [ ] Đã biên dịch và chạy thử chương trình Java thành công.
