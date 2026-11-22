# Import trong JShell

**JShell** là Java Shell, một môi trường REPL (Read–Eval–Print Loop) đi kèm JDK. Bạn có thể nhập biểu thức, câu lệnh, biến, method, class và khai báo import trực tiếp rồi xem kết quả ngay. Trong JShell, **import declaration là một snippet**: sau khi được chấp nhận, tên kiểu hoặc static member được import có thể dùng trong những snippet tiếp theo của cùng session.

Ví dụ:

~~~text
jshell> import java.time.LocalDate;

jshell> LocalDate today = LocalDate.of(2026, 11, 10);
today ==> 2026-11-10

jshell> today.plusDays(7)
$... ==> 2026-11-17
~~~

Sau import, có thể dùng tên ngắn LocalDate thay vì viết đầy đủ java.time.LocalDate ở mỗi biểu thức. Tên biến kết quả tạm như $5 thay đổi theo session.

Import trong JShell tuân theo quy tắc import của Java. Điểm khác biệt quan trọng là JShell còn có startup script với một số import thường dùng, và các import được duy trì trong trạng thái tương tác của session.

## 1. Import declaration dùng để làm gì?

Một kiểu Java có tên đầy đủ (fully qualified name) gồm package và tên kiểu. Ví dụ:

~~~java
java.time.LocalDate
java.util.ArrayList
java.nio.file.Path
~~~

Nếu không import, bạn có thể phải viết đầy đủ tên kiểu:

~~~java
java.time.LocalDate today =
        java.time.LocalDate.now();
~~~

Khi import một kiểu, có thể dùng tên đơn giản:

~~~java
import java.time.LocalDate;

LocalDate today = LocalDate.now();
~~~

Import giúp trình biên dịch phân giải tên đơn giản trong source. Nó không:

- Tạo object.
- Khởi tạo class.
- Chạy static initializer.
- Thêm JAR hoặc thư mục vào classpath.
- Tải một thư viện chưa có trong môi trường biên dịch.
- Cấp quyền truy cập vào package mà module không export.

Import chỉ giúp viết tên ngắn hơn và xác định kiểu hoặc static member nào được tham chiếu. Kiểu vẫn phải có sẵn trong classpath/module path và phải truy cập được theo quy tắc Java.

Trong JShell, một import được nhập ở prompt có hiệu lực với những snippet tiếp theo trong cùng session. Bạn không phải lặp lại import ở mỗi dòng.

## 2. Import mặc định khi khởi động JShell

Khi chạy JShell theo cấu hình mặc định, công cụ nạp startup script tên **DEFAULT**. Script này thêm các import thường dùng để bạn có thể thử nghiệm nhanh.

Trong JDK 17, các import mặc định phổ biến gồm:

~~~java
import java.io.*;
import java.math.*;
import java.net.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.function.*;
import java.util.prefs.*;
import java.util.regex.*;
import java.util.stream.*;
~~~

Vì vậy, trong session mặc định bạn thường có thể dùng ngay các tên như:

~~~java
List.of("Java", "JShell");
Map.of("name", "Ada");
Path.of("notes.txt");
Pattern.compile("[A-Z]+");
Predicate.isEqual("ready");
~~~

Không cần nhập lại java.util.* hoặc java.nio.file.* nếu startup script hiện tại đã nạp chúng.

### java.lang là trường hợp riêng

Java tự động import các kiểu public trong package **java.lang** theo quy tắc ngôn ngữ. Điều này không phụ thuộc riêng vào JShell.

Ví dụ có thể dùng trực tiếp:

~~~java
String message = "Hello";
System.out.println(message);
Math.max(10, 20);
Integer.parseInt("42");
~~~

java.lang không cần được import tường minh. Bạn có thể viết import java.lang.* nhưng thường không có ích.

Cần phân biệt hai cơ chế:

- **java.lang:** được Java tự động import theo ngôn ngữ.
- **Các package trong DEFAULT:** được JShell nạp qua startup script. Chúng có thể thay đổi nếu bạn dùng startup script khác hoặc tắt startup.

### Xem import đã được nạp

Trong JShell, nhập:

~~~text
jshell> /imports
~~~

Lệnh này hiển thị các import đang hoạt động, bao gồm import từ startup script và script đã nạp lúc khởi động.

Có thể xem các snippet startup bằng:

~~~text
jshell> /list -start
~~~

Trong output, các snippet startup thường có ID bắt đầu bằng chữ s, ví dụ s1, s2. Danh sách cụ thể phụ thuộc JDK và startup script.

Không nên mặc định mọi package thường dùng đều đã có. Khi một tên kiểu không được nhận diện, kiểm tra /imports trước rồi import rõ ràng nếu cần.

## 3. Import một kiểu cụ thể (single-type import)

Cú pháp:

~~~java
import package.name.TypeName;
~~~

Ví dụ:

~~~java
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
~~~

Sau đó có thể dùng các tên đơn giản:

~~~java
LocalDate date = LocalDate.of(2026, 11, 10);
LocalTime time = LocalTime.of(9, 30);

DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("dd/MM/uuuu");

formatter.format(date);
~~~

Single-type import phù hợp khi:

- Chỉ cần một hoặc vài kiểu từ package.
- Muốn thể hiện rõ dependency của đoạn code.
- Package có nhiều kiểu dễ trùng tên.
- Muốn người đọc biết chính xác kiểu đang được sử dụng.

Có thể import nested type nếu kiểu đó có thể truy cập:

~~~java
import java.util.Map.Entry;
~~~

Sau đó dùng Entry như một tên kiểu đơn giản trong phạm vi session.

Import một kiểu không import toàn bộ package chứa kiểu đó. Ví dụ import java.time.LocalDate không tự import LocalTime hoặc DateTimeFormatter.

## 4. Import theo package (type-import-on-demand)

Cú pháp:

~~~java
import package.name.*;
~~~

Ví dụ:

~~~java
import java.time.*;
import java.nio.file.*;
~~~

Sau đó có thể dùng các kiểu public trực tiếp trong package:

~~~java
LocalDate today = LocalDate.now();
LocalTime now = LocalTime.now();
Path file = Path.of("notes.txt");
~~~

Dấu * được gọi là on-demand import. Nó không có nghĩa là tải tất cả class hoặc toàn bộ thư viện vào bộ nhớ; compiler chỉ dùng khai báo này để phân giải tên kiểu khi cần.

### Import wildcard không bao gồm subpackage

~~~java
import java.util.*;
~~~

Import này không tự động import các kiểu trong:

- java.util.concurrent
- java.util.function
- java.util.regex
- java.util.stream

Mỗi subpackage là một package riêng. Nếu startup script chưa nạp chúng, cần import riêng:

~~~java
import java.util.concurrent.*;
import java.util.function.*;
import java.util.stream.*;
~~~

Không có cú pháp wildcard đệ quy để import mọi subpackage của một package.

### Khi nào dùng wildcard?

Wildcard có thể tiện trong JShell khi thử nghiệm nhanh nhiều kiểu cùng package. Với code được lưu thành file hoặc ví dụ cần thể hiện dependency rõ ràng, single-type import thường dễ đọc và ít tạo tên mơ hồ hơn.

Wildcard không làm tăng số class được khởi tạo. Nó chỉ mở rộng tập tên kiểu có thể được tham chiếu bằng tên đơn giản.

## 5. Static import

Static import cho phép tham chiếu static field, static method hoặc static nested type mà không cần ghi tên class ở phía trước.

Cú pháp import một static member:

~~~java
import static package.TypeName.memberName;
~~~

Cú pháp import các static member phù hợp trong một kiểu:

~~~java
import static package.TypeName.*;
~~~

Ví dụ import hằng số PI và method sqrt:

~~~java
import static java.lang.Math.PI;
import static java.lang.Math.sqrt;

PI;
sqrt(81);
~~~

Kết quả lần lượt là giá trị của PI và 9.0.

Có thể import toàn bộ static member:

~~~java
import static java.lang.Math.*;
~~~

Sau đó gọi:

~~~java
max(12, 30);
abs(-5);
pow(2, 5);
~~~

Static import chỉ áp dụng cho static member. Nó không import instance method hoặc instance field.

### Static import với collection

Ví dụ:

~~~java
import static java.util.Collections.emptyList;
import static java.util.Collections.singletonList;

emptyList();
singletonList("ready");
~~~

Có thể gọi trực tiếp emptyList() và singletonList() mà không cần viết Collections.emptyList().

### Static import không tạo object

~~~java
import static java.lang.Math.PI;
~~~

Dòng này không tạo một object Math và cũng không gọi method. Nó chỉ cho phép dùng tên PI không cần qualifier Math.

Nếu một static method trả về object, object chỉ được tạo khi bạn thực sự gọi method đó:

~~~java
import static java.util.List.of;

of("A", "B", "C");
~~~

Trong ví dụ này, List.of được thực thi khi snippet gọi of(...).

### Static import và import thông thường khác nhau

| Khai báo | Thành phần được import | Cách dùng |
|---|---|---|
| import java.time.LocalDate; | Kiểu LocalDate | LocalDate.now() |
| import java.time.*; | Các kiểu trong java.time | LocalDate.now() |
| import static java.lang.Math.PI; | Static field PI | PI |
| import static java.lang.Math.sqrt; | Static method sqrt | sqrt(81) |
| import static java.lang.Math.*; | Các static member có thể truy cập | max(1, 2) |

Import thông thường không làm cho static member có thể gọi trực tiếp. Muốn bỏ tên class khỏi static member, cần static import.

## 6. Phạm vi và thời gian tồn tại của import

Trong Java source truyền thống, import declaration nằm ở đầu compilation unit và áp dụng cho toàn bộ file đó. JShell không yêu cầu tạo một file source riêng cho từng snippet.

Khi nhập:

~~~java
import java.time.LocalDate;
~~~

JShell ghi nhận import trong trạng thái của session. Các snippet tiếp theo có thể sử dụng LocalDate:

~~~java
LocalDate start = LocalDate.of(2026, 11, 10);
LocalDate end = start.plusDays(5);
end;
~~~

Bạn không cần import lại LocalDate trước mỗi biểu thức.

Import không tự động được lưu thành cấu hình toàn cục cho mọi lần mở JShell. Khi session được reset, các snippet do người dùng nhập có thể bị xóa; startup script sẽ được chạy lại theo cấu hình hiện tại.

### Import từ startup và import nhập trực tiếp

Có hai nguồn phổ biến:

- **Startup imports:** được nạp khi JShell khởi động hoặc chạy lại startup script.
- **Session imports:** được nhập trực tiếp tại prompt hoặc được nạp từ script bằng /open.

Lệnh /imports hiển thị tập import đang hoạt động, giúp bạn biết một tên kiểu đến từ đâu ở mức import.

## 7. Lệnh JShell liên quan tới import

Các lệnh sau hữu ích khi quản lý import:

| Lệnh | Tác dụng |
|---|---|
| /imports | Hiển thị import hiện đang hoạt động |
| /list -start | Hiển thị snippet được nạp từ startup script |
| /list -all | Hiển thị snippet, gồm startup, lỗi, bị thay thế hoặc bị drop |
| /open file | Nạp snippet và lệnh từ script vào session hiện tại |
| /save file | Lưu các snippet hiện tại theo tùy chọn |
| /save -start file | Lưu nội dung startup script hiện tại |
| /set start | Xem hoặc thay đổi startup script cho lần reset tiếp theo |
| /reset | Xóa trạng thái snippet và chạy lại startup script |
| /reload | Khởi động lại môi trường rồi replay lịch sử hợp lệ |
| /env | Xem hoặc thay đổi classpath/module path; thay đổi môi trường sẽ reset và replay session |

Lệnh bắt đầu bằng dấu / là lệnh điều khiển của JShell, không phải Java import declaration. Ví dụ import java.time.*; là snippet Java, còn /imports là lệnh của công cụ.

### Xem import hiện hoạt động

~~~text
jshell> /imports
~~~

Output hiển thị các dòng import. Danh sách thay đổi theo startup script, import bạn đã nhập và script được nạp.

### Xem import startup

~~~text
jshell> /list -start
~~~

Lệnh này hữu ích khi bạn cần phân biệt import mặc định với import tự nhập. Startup snippet thường có ID riêng bắt đầu bằng s.

### Reset session

~~~text
jshell> /reset
~~~

/reset loại bỏ các snippet trong session, sau đó chạy startup scripts. Những import nhập thủ công sau khi khởi động không còn trong trạng thái mới, trừ khi chúng nằm trong startup script.

### Reload session

~~~text
jshell> /reload
~~~

/reload khởi động lại môi trường và replay lịch sử hợp lệ. Vì vậy các import trong lịch sử có thể được nạp lại cùng những snippet liên quan.

### Thay đổi môi trường

~~~text
jshell> /env
~~~

Không có tùy chọn, /env hiển thị cấu hình môi trường hiện tại. Khi thêm classpath hoặc module path bằng /env, JShell reset trạng thái thực thi, chạy startup scripts và replay lịch sử hợp lệ theo quy tắc của công cụ.

## 8. Tạo startup script chứa import riêng

Nếu thường xuyên dùng cùng một nhóm package, bạn có thể tạo startup script để tự động nạp import mỗi khi mở JShell.

Ví dụ file **my-imports.jsh**:

~~~java
import java.time.*;
import java.time.format.*;
import java.nio.file.*;
import static java.time.temporal.ChronoUnit.DAYS;
import static java.lang.Math.*;
~~~

Đây là script gồm các import declaration. Mỗi snippet hoặc lệnh JShell nên nằm trên dòng riêng để dễ quản lý.

### Nạp script khi khởi động

~~~bash
jshell --startup my-imports.jsh
~~~

Tùy chọn --startup dùng startup script được chỉ định thay cho cấu hình mặc định. Nếu muốn giữ import mặc định và nạp thêm script cá nhân, chỉ định cả hai:

~~~bash
jshell --startup DEFAULT --startup my-imports.jsh
~~~

Có thể chỉ định nhiều startup script; chúng được chạy theo thứ tự khai báo.

### Dùng /open trong session đang chạy

~~~text
jshell> /open my-imports.jsh
~~~

/open nạp các snippet trong file vào session hiện tại. Import được nạp theo script và có thể dùng cho các snippet tiếp theo.

Khác biệt chính:

- --startup: nạp script khi bắt đầu session và khi startup scripts được chạy lại.
- /open: nạp script ngay trong session hiện tại.
- /set start: thay đổi danh sách startup script được dùng trong lần reset tiếp theo.

### Lưu startup script

Có thể lưu cấu hình startup hiện tại:

~~~text
jshell> /save -start my-startup.jsh
~~~

Có thể dùng /set start để cấu hình script và /set start -retain để lưu cấu hình startup cho những lần mở JShell sau.

Ví dụ:

~~~text
jshell> /set start DEFAULT my-imports.jsh
jshell> /set start -retain
~~~

Tùy chọn -retain giúp giữ cấu hình startup cho các session sau. Hãy kiểm tra lại bằng /set start và /imports để xác nhận script mong muốn đã được nạp.

## 9. Tắt import mặc định và kiểm soát môi trường

Đôi khi cần một session sạch để kiểm tra import có thực sự cần thiết hay không.

Khởi động không dùng startup script:

~~~bash
jshell --no-startup
~~~

Trong chế độ này, các import do startup script DEFAULT cung cấp sẽ không được nạp. Tuy nhiên, java.lang vẫn tự động import theo quy tắc của Java.

Bạn có thể nhập import rõ ràng:

~~~java
import java.util.List;
import java.time.LocalDate;

List<String> names = List.of("Ada", "Linus");
LocalDate date = LocalDate.of(2026, 11, 10);
~~~

Không thể dùng đồng thời --no-startup và --startup. Nếu cần cấu hình startup tùy chỉnh, dùng --startup với file mong muốn.

Cách này hữu ích khi:

- Viết hướng dẫn cần thể hiện rõ mọi import.
- Kiểm tra một snippet có phụ thuộc import ngầm không.
- Tìm hiểu import nào đến từ DEFAULT.
- Tạo môi trường thử nghiệm gần với source file Java thông thường.

## 10. Import từ thư viện bên ngoài

Import không tự tìm hoặc tải thư viện bên thứ ba. Trước khi import một class, thư viện phải có mặt trong môi trường của JShell.

Giả sử đã biên dịch thư viện vào build/classes hoặc có JAR tại lib/helper.jar.

### Đặt classpath khi khởi động

Linux/macOS:

~~~bash
jshell --class-path "build/classes:lib/helper.jar"
~~~

Windows:

~~~powershell
jshell --class-path "build/classes;lib/helper.jar"
~~~

Sau đó có thể import kiểu public trong package của thư viện:

~~~java
import com.example.helper.TextFormatter;

TextFormatter.uppercase("hello");
~~~

Class trong default package (unnamed package) không thể được truy cập từ JShell. Hãy đặt code thư viện trong một package có tên.

### Thêm classpath trong session

Có thể dùng:

~~~text
jshell> /env --class-path build/classes
~~~

JShell sẽ thông báo thay đổi tùy chọn môi trường và khôi phục session bằng cách reset rồi replay lịch sử hợp lệ.

Lưu ý: /env có thể làm session khởi động lại. Nếu một snippet trước đó phụ thuộc vào trạng thái bên ngoài hoặc có side effect, replay có thể tạo kết quả khác. Hãy lưu công việc quan trọng trước khi thay đổi môi trường.

### Module path

Nếu thư viện được đóng gói thành named module, dùng module path:

~~~bash
jshell --module-path mods --add-modules com.example.api
~~~

Sau đó import public type từ package mà module đã export:

~~~java
import com.example.api.GreetingService;
~~~

Điều kiện cần:

- Module có mặt trên module path.
- Module được resolve, ví dụ qua --add-modules.
- Package chứa kiểu đã được export cho module đang sử dụng.
- Kiểu và member có quyền truy cập phù hợp.

Classpath và module path giải quyết hai loại dependency khác nhau. Không đặt một JAR lên classpath rồi mong import có thể vượt qua ranh giới module của một named module.

## 11. Xử lý tên trùng và import mơ hồ

Một số package có thể chứa kiểu cùng tên. Ví dụ Date tồn tại trong java.util và java.sql.

Nếu import cả hai package theo wildcard:

~~~java
import java.util.*;
import java.sql.*;
~~~

thì tham chiếu đơn giản:

~~~java
Date today;
~~~

có thể mơ hồ vì cả hai package đều có kiểu Date.

Cách giải quyết là dùng tên đầy đủ:

~~~java
java.util.Date utilDate = new java.util.Date();
java.sql.Date sqlDate = java.sql.Date.valueOf("2026-11-10");
~~~

Hoặc chỉ import một kiểu cụ thể và dùng tên đầy đủ cho kiểu còn lại.

### Hai single-type import cùng tên

Nếu nhập hai single-type import có cùng simple name nhưng trỏ tới hai kiểu khác nhau, Java báo lỗi import conflict:

~~~java
import java.util.Date;
import java.sql.Date;
~~~

Trong trường hợp này, hãy giữ một import và dùng tên đầy đủ cho kiểu còn lại.

### Static import mơ hồ

Hai class có thể có static member trùng tên. Nếu import nhiều member cùng tên và compiler không thể xác định member phù hợp, lời gọi có thể bị ambiguous.

Ví dụ tổng quát:

~~~java
import static java.lang.Math.max;
~~~

Nếu một static import khác cũng đưa một method max có signature cạnh tranh vào cùng phạm vi, hãy gọi method qua tên class để làm rõ:

~~~java
Math.max(10, 20);
~~~

### Cách tránh xung đột

- Dùng single-type import cho kiểu quan trọng.
- Hạn chế wildcard khi package có nhiều tên dễ trùng.
- Dùng fully qualified name ở điểm xung đột.
- Dùng static import có chọn lọc thay vì import toàn bộ static member.
- Kiểm tra /imports khi session có nhiều startup script hoặc script được nạp nối tiếp.

JShell áp dụng quy tắc phân giải tên của Java; REPL không tự chọn một kiểu theo thứ tự import để che giấu sự mơ hồ.

## 12. Những điều wildcard không làm

Có một số hiểu nhầm thường gặp:

**Wildcard không import subpackage**

java.util.* không bao gồm java.util.stream.*.

**Wildcard không import static member**

import java.lang.Math.* không cho phép gọi trực tiếp sqrt(9). Muốn vậy phải dùng import static java.lang.Math.sqrt hoặc import static java.lang.Math.*.

**Import không thêm dependency**

import com.example.Tool không làm JAR chứa Tool tự xuất hiện trên classpath.

**Import không cấp quyền truy cập module**

Nếu package không export hoặc module không được resolve, import vẫn có thể thất bại.

**Import không tạo object**

import java.time.LocalDate không gọi LocalDate.now() và không tạo ngày hiện tại.

**Import không phải alias**

Java không có cú pháp import kiểu đổi tên như một số ngôn ngữ khác. Nếu hai kiểu trùng tên, dùng fully qualified name hoặc đổi cách tổ chức code.

## 13. Ví dụ thực hành: import ngày tháng và static member

Ví dụ này dùng Java 17+ và chạy trực tiếp trong JShell.

Khởi động:

~~~bash
jshell
~~~

Nhập single-type import:

~~~java
import java.time.LocalDate;
~~~

Nhập static import:

~~~java
import static java.time.temporal.ChronoUnit.DAYS;
~~~

Tạo hai ngày:

~~~java
LocalDate start = LocalDate.of(2026, 11, 10);
LocalDate due = start.plusDays(14);
~~~

Tính số ngày:

~~~java
DAYS.between(start, due);
~~~

Kết quả:

~~~text
14
~~~

JShell có thể hiển thị kết quả dưới dạng biến tạm, ví dụ $5 ==> 14. ID biến tạm thay đổi theo session; giá trị số ngày vẫn là 14.

Trong ví dụ này:

- LocalDate được import tường minh từ java.time.
- DAYS được import tường minh bằng static import.
- between là method của giá trị ChronoUnit.DAYS.
- Các snippet dùng chung import đã khai báo trước đó.

Có thể kiểm tra danh sách import:

~~~text
jshell> /imports
~~~

Bạn sẽ thấy import LocalDate và static import DAYS cùng với các import startup đang hoạt động.

## 14. Ví dụ thực hành: wildcard import và stream

Trong JShell mặc định, java.util.* và java.util.stream.* thường đã được nạp bởi DEFAULT. Có thể kiểm tra bằng /imports.

Ví dụ:

~~~java
List<String> languages =
        List.of("Java", "Kotlin", "Scala", "JavaScript");

List<String> result = languages.stream()
        .filter(name -> name.startsWith("J"))
        .map(String::toUpperCase)
        .toList();

result;
~~~

Kết quả:

~~~text
[JAVA, JAVASCRIPT]
~~~

Để thấy import tường minh, có thể chạy session không startup:

~~~bash
jshell --no-startup
~~~

Sau đó nhập:

~~~java
import java.util.List;
import java.util.stream.Collectors;

List<String> result = List.of("Java", "Kotlin", "Scala")
        .stream()
        .filter(name -> name.length() > 4)
        .collect(Collectors.toList());

result;
~~~

Kết quả:

~~~text
[Kotlin, Scala]
~~~

Đây là cách tốt để phân biệt import đến từ Java language, import do JShell startup script cung cấp và import mà bạn tự khai báo.

## 15. Ví dụ thực hành: static import và xử lý số

Trong một session mới hoặc session hiện tại, nhập:

~~~java
import static java.lang.Math.PI;
import static java.lang.Math.sqrt;
import static java.lang.Math.pow;
~~~

Thực hiện:

~~~java
double radius = 3.0;
double area = PI * pow(radius, 2);
double diagonal = sqrt(3 * 3 + 4 * 4);
~~~

Kiểm tra:

~~~java
area;
diagonal;
~~~

Kết quả xấp xỉ:

~~~text
28.274333882308138
5.0
~~~

Static import làm công thức gọn hơn. Nếu đoạn code có nhiều class cùng cung cấp method cùng tên, nên giữ qualifier để tránh mơ hồ và giúp người đọc nhận diện nguồn method.

## 16. Đưa import vào file script

Khi cần lặp lại một bài thử nghiệm, có thể lưu import và snippet vào file .jsh.

Ví dụ file **date-demo.jsh**:

~~~java
import java.time.LocalDate;
import static java.time.temporal.ChronoUnit.DAYS;

LocalDate start = LocalDate.of(2026, 11, 10);
LocalDate due = start.plusDays(14);
DAYS.between(start, due);
~~~

Nạp file khi khởi động:

~~~bash
jshell date-demo.jsh
~~~

Hoặc từ session đang chạy:

~~~text
jshell> /open date-demo.jsh
~~~

File script có thể chứa snippet Java và lệnh JShell. Nên đặt mỗi snippet hoặc lệnh trên dòng riêng để dễ đọc, sửa và tái sử dụng.

Nếu muốn tạo file startup chỉ chứa import, hãy đặt các import ở đầu script rồi thêm các method hoặc helper cần dùng sau đó. Tránh đưa các thao tác có side effect vào startup script nếu không muốn chúng chạy lại sau mỗi lần reset.

## 17. Chẩn đoán lỗi import thường gặp

### Cannot find symbol: class LocalDate

Nguyên nhân thường gặp là thiếu import hoặc startup script không nạp java.time.

Cách xử lý:

~~~java
import java.time.LocalDate;
~~~

Hoặc dùng tên đầy đủ:

~~~java
java.time.LocalDate.now();
~~~

### Package does not exist

Tên package có thể sai, hoặc thư viện chưa có trong classpath/module path. Kiểm tra tên package, JAR, đường dẫn và cách khởi động JShell.

Với thư viện ngoài:

~~~bash
jshell --class-path lib/helper.jar
~~~

### Reference to Date is ambiguous

Có nhiều kiểu cùng tên được import. Dùng tên đầy đủ:

~~~java
java.util.Date
java.sql.Date
~~~

Hoặc chỉ import một kiểu cụ thể.

### Import static không tìm thấy member

Kiểm tra class có public static member đó hay không. Static import không thể import instance method hoặc instance field.

Ví dụ Math.PI là static field, còn một method instance không thể import bằng import static.

### Import thành công nhưng class vẫn không truy cập được

Import không vượt qua visibility hoặc module encapsulation. Kiểm tra class có public hay không, package có được export hay không và module có được resolve hay không.

### Vừa reset xong thì import biến mất

/reset xóa snippet do người dùng nhập và chạy lại startup script. Đưa import thường dùng vào startup script hoặc nhập lại sau reset.

### Script nạp nhưng import không có hiệu lực

Kiểm tra file path, lỗi cú pháp trong script và thứ tự startup scripts. Dùng /imports và /list -start để xem snippet thực tế đã được nạp.

### Đã thêm JAR nhưng vẫn không import được

Kiểm tra JAR có chứa class trong package có tên, class có thể truy cập và classpath trỏ đúng file. Nếu là named module, dùng module path và resolve module thay vì chỉ thêm classpath.

## 18. Quy trình làm việc hiệu quả với import trong JShell

1. Mở JShell bằng JDK mong muốn.
2. Chạy /imports để xem những import startup đã cung cấp.
3. Chỉ import thêm package hoặc kiểu chưa có.
4. Dùng single-type import cho kiểu quan trọng hoặc dễ trùng tên.
5. Dùng wildcard khi thử nghiệm nhiều kiểu cùng package.
6. Dùng static import khi biểu thức ngắn và nguồn member rõ ràng.
7. Khi có lỗi tên mơ hồ, dùng fully qualified name để xác định kiểu.
8. Nếu dùng thư viện ngoài, cấu hình classpath/module path trước khi import.
9. Đưa import lặp lại vào script .jsh hoặc startup script.
10. Sau /reset hoặc /env, kiểm tra lại import vì trạng thái session có thể đã được tạo lại.
11. Dùng /save hoặc /save -start để lưu snippet và cấu hình cần tái sử dụng.
12. Khi cần kiểm tra tính độc lập, chạy jshell --no-startup và khai báo import tường minh.

Import giúp JShell trở thành môi trường thử nghiệm thuận tiện: bạn có thể tập trung vào API và logic thay vì lặp lại tên package dài. Khi hiểu startup imports, single-type import, wildcard import, static import và cách quản lý session, bạn sẽ tránh được phần lớn lỗi không tìm thấy kiểu hoặc tên mơ hồ khi làm việc với Java REPL.

## Tài liệu tham khảo

- [Java Shell User’s Guide — Scripts (JDK 17)](https://docs.oracle.com/en/java/javase/17/jshell/scripts.html)
- [Java Shell User’s Guide — External Code (JDK 17)](https://docs.oracle.com/en/java/javase/17/jshell/external-code.html)
- [The jshell Command — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jshell.html)
- [Java Shell User’s Guide — Scripts (JDK 24)](https://docs.oracle.com/en/java/javase/24/jshell/scripts.html)
