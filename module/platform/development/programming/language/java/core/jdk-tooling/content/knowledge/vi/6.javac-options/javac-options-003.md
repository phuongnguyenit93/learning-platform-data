# Thông tin debug trong class file Java

Khi biên dịch mã nguồn Java, `javac` có thể ghi thêm metadata phục vụ gỡ lỗi vào class file. Metadata này giúp debugger liên hệ bytecode với dòng mã nguồn, hiển thị tên biến cục bộ và xác định vị trí thực thi khi đặt breakpoint.

Tùy chọn quan trọng là `-g`. Có thể chọn loại thông tin cụ thể bằng `-g:source,lines,vars` hoặc tắt hoàn toàn bằng `-g:none`. Hiểu rõ các lựa chọn này giúp bạn điều tra vì sao breakpoint không khớp dòng nguồn, vì sao debugger không hiện tên biến hoặc vì sao một bản build khó gỡ lỗi hơn bản khác.

## 1. Debug metadata là gì?

Class file Java chứa bytecode và metadata để JVM nạp, liên kết và thực thi class. Một số metadata chỉ phục vụ công cụ phát triển và debugger, không cần thiết cho logic chạy bình thường.

Các loại thông tin debug phổ biến:

| Thông tin | Mục đích |
|---|---|
| Source file | Ghi tên file nguồn liên quan đến class, thường qua thuộc tính `SourceFile` |
| Line numbers | Ánh xạ vị trí bytecode về số dòng mã nguồn, qua `LineNumberTable` |
| Local variables | Ghi tên, kiểu, slot và phạm vi hiệu lực của biến cục bộ, qua `LocalVariableTable` |
| Generic local variable signatures | Bổ sung kiểu generic cho biến cục bộ khi có, qua `LocalVariableTypeTable` |

Debug metadata không phải bản sao mã nguồn Java. `SourceFile` thường chỉ ghi tên tệp, còn `LineNumberTable` lưu ánh xạ dòng; source code thực tế vẫn cần được debugger hoặc IDE truy cập riêng nếu muốn hiển thị nội dung.

JVM có thể chạy class file dù thiếu phần lớn debug metadata. Bytecode và các quy tắc thực thi vẫn tồn tại; thông tin debug giúp con người và công cụ quan sát chương trình dễ hơn.

## 2. Tùy chọn javac -g

`javac` hỗ trợ các dạng chính:

| Lệnh | Thông tin được sinh |
|---|---|
| `javac -g ...` | Tất cả thông tin debug được compiler hỗ trợ, bao gồm source, line và local variables |
| `javac -g:source,lines,vars ...` | Chỉ định rõ cả ba nhóm thông tin |
| `javac -g:source,lines ...` | Tên source file và ánh xạ dòng, không yêu cầu local-variable table |
| `javac -g:lines ...` | Thông tin số dòng |
| `javac -g:vars ...` | Thông tin biến cục bộ |
| `javac -g:none ...` | Không sinh thông tin debug |

Nếu không chỉ định `-g`, `javac` mặc định sinh thông tin số dòng và tên source file, nhưng không sinh thông tin biến cục bộ. Vì vậy, khi cần xem tên và giá trị biến trong debugger, hãy biên dịch với `-g` hoặc ít nhất `-g:vars`.

Tên các nhóm được phân tách bằng dấu phẩy: `source`, `lines` và `vars`. Có thể xem trợ giúp của compiler đang dùng bằng:

~~~sh
javac -help
~~~

`-g` là tùy chọn của compiler, được đặt trên lệnh `javac`. Đây không phải tùy chọn runtime của `java`; không truyền `-g` vào lệnh chạy ứng dụng.

## 3. Ví dụ một class có biến cần debug

Tạo file `src/com/example/DebugInfoDemo.java`:

~~~java
package com.example;

public class DebugInfoDemo {
    public static void main(String[] args) {
        String message = "Debug metadata";
        int first = 20;
        int second = 22;
        int total = add(first, second);

        System.out.println(message + ": " + total);
    }

    private static int add(int left, int right) {
        int result = left + right;
        return result;
    }
}
~~~

Ví dụ có các biến cục bộ `message`, `first`, `second`, `total`, cùng các tham số và biến `result` trong phương thức `add`. Đây là các giá trị hữu ích khi đặt breakpoint và kiểm tra từng bước.

Tạo thư mục output và biên dịch với đầy đủ debug metadata:

~~~sh
mkdir -p out
javac -g -d out src/com/example/DebugInfoDemo.java
~~~

Trên PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -g -d out src/com/example/DebugInfoDemo.java
~~~

Chạy ứng dụng:

~~~sh
java -cp out com.example.DebugInfoDemo
~~~

Kết quả stdout:

~~~text
Debug metadata: 42
~~~

Nếu biên dịch thành công, class file được tạo tại `out/com/example/DebugInfoDemo.class`. Thư mục `out` là classpath root; không dùng `out/com/example` làm classpath khi chạy tên đầy đủ `com.example.DebugInfoDemo`.

## 4. Kiểm tra metadata bằng javap

`javap` là công cụ disassembler của JDK, có thể hiển thị cấu trúc class file và các thuộc tính debug.

Dùng tùy chọn `-l` để xem thông tin line number và local variable:

~~~sh
javap -classpath out -l -p com.example.DebugInfoDemo
~~~

Các tùy chọn:

- `-classpath out` chỉ ra vị trí class file cần đọc.
- `-l` yêu cầu hiển thị thông tin line number và local variable.
- `-p` hiển thị cả thành viên không public.

Với class được biên dịch bằng `-g`, phần kết quả cho các phương thức có thể chứa `LineNumberTable` và `LocalVariableTable`. Các dòng cụ thể phụ thuộc vị trí mã nguồn và compiler; điều cần xác nhận là bảng tương ứng xuất hiện.

Để xem chi tiết class file và các attribute:

~~~sh
javap -classpath out -v com.example.DebugInfoDemo
~~~

Trong kết quả verbose, tìm các mục `SourceFile`, `LineNumberTable`, `LocalVariableTable` hoặc `LocalVariableTypeTable` tùy nội dung class.

Nếu class được biên dịch không có thông tin biến cục bộ, `javap -l` có thể vẫn hiển thị bảng dòng nhưng không có `LocalVariableTable`. Đây là dấu hiệu cần kiểm tra lại tùy chọn compiler hoặc build configuration.

## 5. So sánh các mức debug

Có thể biên dịch cùng source vào các thư mục khác nhau để thấy sự khác biệt:

~~~sh
mkdir -p out-default out-full out-lines out-none

# Mặc định: source và line information
javac -d out-default src/com/example/DebugInfoDemo.java

# Tất cả debug information
javac -g -d out-full src/com/example/DebugInfoDemo.java

# Chỉ source và line information
javac -g:source,lines -d out-lines src/com/example/DebugInfoDemo.java

# Không sinh debug information
javac -g:none -d out-none src/com/example/DebugInfoDemo.java
~~~

Trên Windows PowerShell, có thể tạo các thư mục bằng một lệnh:

~~~powershell
New-Item -ItemType Directory -Force out-default,out-full,out-lines,out-none | Out-Null
javac -d out-default src/com/example/DebugInfoDemo.java
javac -g -d out-full src/com/example/DebugInfoDemo.java
javac -g:source,lines -d out-lines src/com/example/DebugInfoDemo.java
javac -g:none -d out-none src/com/example/DebugInfoDemo.java
~~~

Kiểm tra từng bản:

~~~sh
javap -classpath out-default -l -p com.example.DebugInfoDemo
javap -classpath out-full -l -p com.example.DebugInfoDemo
javap -classpath out-lines -l -p com.example.DebugInfoDemo
javap -classpath out-none -l -p com.example.DebugInfoDemo
~~~

Có thể đối chiếu như sau:

| Bản build | Source/line info | Local variable info |
|---|---|---|
| Mặc định | Có | Không |
| `-g` | Có | Có |
| `-g:source,lines` | Có | Không |
| `-g:none` | Không | Không |

Các tùy chọn này ảnh hưởng metadata trong class file. Chúng không thay đổi kết quả logic của ví dụ khi chạy; cả bốn bản đều có thể in `Debug metadata: 42`.

## 6. Dùng debug information trong debugger và IDE

Khi debugger dừng tại breakpoint, nó cần ánh xạ vị trí bytecode về dòng source. `LineNumberTable` hỗ trợ việc này. Khi muốn xem tên biến cục bộ trong cửa sổ Variables hoặc dùng lệnh liệt kê locals, `LocalVariableTable` cung cấp tên, kiểu, slot và phạm vi hiệu lực của biến.

Với ví dụ đã biên dịch bằng `-g`, có thể chạy debugger dòng lệnh:

~~~sh
jdb -classpath out com.example.DebugInfoDemo
~~~

Tại dấu nhắc `jdb`, có thể dùng các lệnh cơ bản:

~~~text
stop in com.example.DebugInfoDemo.main
run
locals
step
where
cont
exit
~~~

`stop in` đặt breakpoint tại phương thức; `run` bắt đầu chương trình; `locals` yêu cầu hiển thị biến cục bộ của frame hiện tại; `step` thực hiện bước tiếp; `where` hiển thị call stack; `cont` tiếp tục chạy.

Trong IntelliJ IDEA, Eclipse hoặc IDE khác, hãy:

1. Chạy cấu hình **Debug** thay vì chỉ chạy ứng dụng bình thường.
2. Đặt breakpoint tại dòng có thể thực thi trong source.
3. Xác nhận IDE đang dùng đúng class file được build từ source hiện tại.
4. Dùng Step Over, Step Into, Variables và Watches để quan sát trạng thái.
5. Nếu biến không có tên hoặc breakpoint nhảy sai dòng, kiểm tra debug metadata và sự khớp nhau giữa source với class file.

Nếu class file cũ được giữ lại sau khi source đã thay đổi, debugger có thể hiển thị dòng hoặc biến không khớp. Hãy build lại đúng module, kiểm tra output directory và classpath mà ứng dụng thực sự sử dụng. Nếu có nhiều bản class trùng tên trên classpath, JVM có thể nạp bản khác với bản IDE đang mở.

## 7. Phân biệt debug metadata với -parameters

Tùy chọn `-parameters` cũng lưu tên tham số phương thức vào class file, nhưng nó phục vụ một mục đích khác với `-g`.

- `-g` và `-g:vars` cung cấp thông tin biến cục bộ cho debugger.
- `-parameters` lưu tên formal parameter để reflection có thể truy vấn qua API `java.lang.reflect.Parameter`.

Ví dụ, một framework dùng reflection có thể gọi `Parameter.getName()`. Nếu class không được biên dịch với `-parameters`, tên tham số có thể chỉ là dạng tổng quát như `arg0`, và `isNamePresent()` trả về `false`.

Có thể kết hợp hai tùy chọn:

~~~sh
javac -g -parameters -d out src/com/example/DebugInfoDemo.java
~~~

`-parameters` không thay thế `-g`; ngược lại, `-g` cũng không đảm bảo tên tham số sẽ có sẵn qua reflection.

## 8. Debug metadata và remote debugging là hai việc khác nhau

Biên dịch với `-g` chỉ thêm thông tin vào class file. Nó không tự bật debugger, không mở cổng mạng và không khiến JVM chờ IDE kết nối.

Để một JVM cho phép debugger kết nối qua JDWP, phải cấu hình agent lúc chạy. Ví dụ chỉ lắng nghe trên loopback của máy hiện tại:

~~~sh
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -cp out com.example.DebugInfoDemo
~~~

Trong đó:

- `transport=dt_socket` chọn kết nối qua socket.
- `server=y` yêu cầu JVM chờ debugger kết nối đến.
- `suspend=n` cho phép ứng dụng bắt đầu chạy mà không chờ debugger.
- `address=127.0.0.1:5005` giới hạn listener ở loopback trên cổng 5005.

Khi cần debugger kết nối trước khi ứng dụng chạy, có thể dùng `suspend=y`. Hãy cấu hình kết nối trong IDE tương ứng với host và port.

JDWP cho phép điều khiển tiến trình và quan sát dữ liệu runtime. Không mở cổng debug ra mạng công cộng hoặc môi trường không tin cậy; chỉ bật khi cần và giới hạn phạm vi truy cập. Dù có JDWP, thiếu line/local-variable metadata vẫn làm trải nghiệm debug theo dòng hoặc xem biến bị hạn chế.

## 9. Ảnh hưởng, giới hạn và lưu ý khi phát hành

Debug metadata thường làm class file lớn hơn một chút. Mức tăng phụ thuộc số lượng phương thức, dòng nguồn và biến. Nó không làm thay đổi ngữ nghĩa chương trình, nhưng có thể tiết lộ tên source file, số dòng, tên biến và một số chi tiết cấu trúc nội bộ.

Cần hiểu một số giới hạn:

- `LocalVariableTable` chỉ mô tả biến trong phạm vi bytecode tương ứng. Biến ngoài scope không xuất hiện ở frame hiện tại.
- Hai biến ở các scope không chồng lấn có thể dùng chung local-variable slot. Slot là vị trí lưu trong frame, không phải một địa chỉ cố định cho toàn bộ thời gian chạy.
- Một số giá trị có thể không quan sát được khi JVM tối ưu mã trong lúc chạy; debugger có thể báo unavailable hoặc hiển thị giá trị không còn tồn tại như biến độc lập.
- Có debug metadata không có nghĩa debugger có thể tự khôi phục toàn bộ source code. IDE vẫn cần source phù hợp để hiển thị nội dung.
- Công cụ shrinker, obfuscator hoặc quá trình đóng gói có thể loại bỏ hay biến đổi metadata; hãy kiểm tra class file cuối cùng được phát hành nếu cần hỗ trợ chẩn đoán.
- `-g:none` không phải cơ chế bảo mật để giấu logic hay dữ liệu. Bytecode vẫn có thể được phân tích bằng công cụ phù hợp.

Trong dự án phát triển, thường nên giữ line và local-variable information để hỗ trợ debugger. Với production, quyết định giữ hay bỏ metadata cần dựa trên yêu cầu chẩn đoán, kích thước artifact và chính sách tiết lộ thông tin. Không nên tắt metadata một cách máy móc nếu đội vận hành cần phân tích lỗi.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Breakpoint không dừng đúng dòng | Thiếu line table, source và class file không khớp hoặc đang nạp class khác | Build lại với line info; xác minh source, output directory và classpath |
| Debugger không hiện tên biến cục bộ | Class được biên dịch mặc định hoặc chỉ có source/line info | Biên dịch lại với `-g` hoặc `-g:vars` |
| `javap -l` không có LocalVariableTable | Compiler không sinh biến debug hoặc metadata đã bị loại bỏ | Kiểm tra lệnh `javac`, build tool và artifact sau đóng gói |
| Reflection trả về tên `arg0` | Thiếu MethodParameters attribute | Biên dịch với `-parameters` |
| IDE hiển thị source khác với bytecode | Source hiện tại không tương ứng với class file đang chạy | Clean/rebuild đúng module và kiểm tra classpath |
| `jdb` không kết nối được | JVM chưa bật JDWP hoặc host/port không đúng | Khởi chạy với `-agentlib:jdwp=...` và kiểm tra cấu hình kết nối |
| Biến hiển thị unavailable khi chạy | Biến ngoài scope hoặc runtime đã tối ưu giá trị | Dừng ở đúng frame và kiểm tra bản build/debug level; không giả định mọi giá trị luôn tồn tại |

## 11. Checklist biên dịch phục vụ debug

- [ ] Chọn đúng JDK/compiler dùng để build class.
- [ ] Dùng `-g` khi cần source, line và local-variable metadata.
- [ ] Dùng `-g:source,lines` nếu chỉ cần ánh xạ dòng.
- [ ] Dùng `-g:none` khi có chủ đích loại bỏ debug metadata.
- [ ] Dùng `-parameters` riêng khi cần tên tham số qua reflection.
- [ ] Dùng `javap -l` hoặc `javap -v` để xác nhận metadata thực tế.
- [ ] Build lại đúng class file mà IDE hoặc JVM sẽ nạp.
- [ ] Cung cấp source tương ứng cho debugger.
- [ ] Chỉ bật JDWP khi cần remote debugging và giới hạn địa chỉ truy cập.
- [ ] Kiểm tra artifact cuối cùng nếu quy trình phát hành có shrink/obfuscate.

`-g` giúp `javac` tạo metadata để debugger liên kết bytecode với source và quan sát biến cục bộ. Kết hợp đúng mức debug, `javap` và debugger của IDE sẽ giúp tìm lỗi nhanh hơn mà vẫn kiểm soát được nội dung class file được phát hành.