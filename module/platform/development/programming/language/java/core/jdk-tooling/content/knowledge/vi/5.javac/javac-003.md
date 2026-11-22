# Biên dịch nhiều source bằng javac

## 1. Vì sao cần biên dịch nhiều tệp Java cùng lúc?

Một ứng dụng Java thường được chia thành nhiều lớp và nhiều tệp nguồn để mỗi thành phần có một trách nhiệm rõ ràng. Ví dụ, một lớp quản lý dữ liệu có thể được dùng bởi lớp dịch vụ, còn lớp chính gọi lớp dịch vụ để chạy ứng dụng. Khi đó, một tệp nguồn có thể tham chiếu đến kiểu được khai báo trong tệp khác.

**javac** là trình biên dịch Java. Nó nhận một hoặc nhiều tệp nguồn **.java**, phân tích cú pháp, kiểm tra kiểu và quan hệ giữa các lớp, sau đó sinh bytecode trong các tệp **.class**. Khi các tệp phụ thuộc lẫn nhau, có thể đưa tất cả vào cùng một lần gọi javac. Trình biên dịch sẽ xử lý các khai báo và tham chiếu giữa chúng trong cùng lần biên dịch; thông thường không cần tự biên dịch theo thứ tự thủ công.

Biên dịch nhiều source cùng lúc hữu ích khi:

- Một chương trình gồm nhiều lớp trong các package khác nhau.
- Lớp chính sử dụng các lớp tiện ích hoặc lớp mô hình ở tệp khác.
- Nhiều lớp có tham chiếu kiểu qua lại và cần được biên dịch cùng một lượt.
- Muốn kiểm soát thư mục đầu ra, phiên bản Java và thư viện phụ thuộc bằng một lệnh nhất quán.

Biên dịch thành công chỉ tạo bytecode. Để chạy ứng dụng, runtime vẫn cần tìm được lớp chính và tất cả thư viện phụ thuộc.

## 2. Cú pháp cơ bản

Cú pháp tổng quát:

~~~bash
javac [compiler options] <source-file-1.java> <source-file-2.java> ...
~~~

Ví dụ đơn giản:

~~~bash
javac First.java Second.java Third.java
~~~

Lệnh trên yêu cầu javac biên dịch cả ba tệp trong cùng một lần gọi. Nếu một tệp sử dụng lớp được khai báo trong tệp khác, hãy đưa tệp nguồn đó vào danh sách hoặc cấu hình đường dẫn để javac tìm thấy nó.

Một lệnh thực tế thường có thêm tùy chọn:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/com/example/model/Message.java src/com/example/service/GreetingService.java src/com/example/app/Main.java
~~~

Ý nghĩa:

- **--release 17**: biên dịch theo mức tương thích Java 17, bao gồm cú pháp, định dạng bytecode và API nền tảng được hỗ trợ ở release đó.
- **-encoding UTF-8**: đọc mã nguồn theo UTF-8.
- **-d out**: ghi các tệp .class vào thư mục **out**.
- Các đường dẫn còn lại là những tệp nguồn cần biên dịch.

Có thể chỉ định đường dẫn tương đối tính từ thư mục terminal hiện tại hoặc đường dẫn tuyệt đối. Khi dùng đường dẫn tương đối, hãy chạy lệnh từ đúng thư mục gốc dự án để các đường dẫn nhất quán.

## 3. Cấu trúc package và thư mục source

Giả sử dự án có ba lớp:

~~~text
project/
├── src/
│   └── com/
│       └── example/
│           ├── model/
│           │   └── Message.java
│           ├── service/
│           │   └── GreetingService.java
│           └── app/
│               └── Main.java
└── out/
~~~

Mỗi tệp khai báo package tương ứng với vị trí logic của lớp:

**Message.java**

~~~java
package com.example.model;

public class Message {
    public String text() {
        return "Hello";
    }
}
~~~

**GreetingService.java**

~~~java
package com.example.service;

import com.example.model.Message;

public class GreetingService {
    public String greeting(String name) {
        return new Message().text() + ", " + name + "!";
    }
}
~~~

**Main.java**

~~~java
package com.example.app;

import com.example.service.GreetingService;

public class Main {
    public static void main(String[] args) {
        System.out.println(new GreetingService().greeting("Java"));
    }
}
~~~

Tên package xác định tên đầy đủ của lớp. Ví dụ, lớp Main có tên đầy đủ là **com.example.app.Main**. Cấu trúc thư mục source nên phản ánh package để con người dễ quản lý và để javac tìm các source phụ thuộc theo quy ước package.

Nếu một tệp khai báo lớp public cấp cao nhất, tên tệp phải khớp tên lớp đó. Ví dụ, lớp public **GreetingService** nằm trong **GreetingService.java**. Sai tên tệp hoặc khai báo package không khớp có thể dẫn đến lỗi biên dịch hoặc lỗi không tìm thấy kiểu.

## 4. Cách 1: Liệt kê tất cả source trong một lệnh

Đứng tại thư mục **project** và chạy:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/com/example/model/Message.java src/com/example/service/GreetingService.java src/com/example/app/Main.java
~~~

Lệnh này biên dịch rõ ràng cả ba tệp. Vì mọi source đều được đưa vào cùng một lượt, javac có thể phân giải tham chiếu giữa **Main**, **GreetingService** và **Message** mà không cần tạo bytecode trước cho từng lớp.

Sau khi biên dịch, thư mục đầu ra có cấu trúc:

~~~text
out/
└── com/
    └── example/
        ├── model/
        │   └── Message.class
        ├── service/
        │   └── GreetingService.class
        └── app/
            └── Main.class
~~~

Tùy chọn **-d out** yêu cầu javac đặt bytecode trong thư mục đích và tạo các thư mục con theo package. Khi chạy ứng dụng, classpath cần trỏ đến thư mục gốc chứa cây package, tức **out**, không trỏ thẳng vào **out/com/example/app**.

Chạy chương trình:

~~~bash
java -cp out com.example.app.Main
~~~

Kết quả:

~~~text
Hello, Java!
~~~

Lưu ý: tên lớp chính khi chạy phải là tên đầy đủ gồm package. Không thêm phần mở rộng **.class** và không viết đường dẫn tệp thay cho tên lớp khi đang dùng chế độ chạy lớp thông thường.

## 5. Cách 2: Dùng -sourcepath để tìm source phụ thuộc

Không phải lúc nào cũng cần liệt kê mọi tệp nguồn. Khi một lớp tham chiếu đến lớp khác mà source của lớp đó nằm trong cây thư mục đã biết, có thể dùng **-sourcepath**:

~~~bash
javac --release 17 -encoding UTF-8 -sourcepath src -d out src/com/example/app/Main.java
~~~

Trong ví dụ trên:

- **src** là gốc cây source.
- **Main.java** là tệp nguồn được yêu cầu biên dịch trực tiếp.
- javac tìm **GreetingService.java** và **Message.java** dựa trên package và các tham chiếu kiểu.
- **-d out** đặt các tệp class được tạo vào thư mục đầu ra.

Đường dẫn source được ánh xạ theo tên package. Với lớp **com.example.service.GreetingService**, javac tìm đường dẫn tương ứng bên dưới source root, tức **src/com/example/service/GreetingService.java**.

Khi không chỉ định **-sourcepath**, javac có thể sử dụng classpath người dùng để tìm source theo quy tắc của trình biên dịch. Trong dự án có cấu trúc rõ ràng, khai báo **-sourcepath** tường minh giúp dễ hiểu và kiểm soát nơi tìm source hơn.

Cách này tiện cho dự án nhỏ hoặc ví dụ học tập. Với dự án lớn, việc biên dịch tường minh hoặc dùng hệ thống build sẽ giúp kiểm soát tập source, phụ thuộc và quá trình biên dịch lặp lại tốt hơn.

## 6. Phân biệt -sourcepath, -classpath và -d

Ba tùy chọn này giải quyết ba vấn đề khác nhau:

| Tùy chọn | Dùng để | Ví dụ |
|---|---|---|
| **-sourcepath** | Tìm các tệp nguồn .java mà compiler cần đọc | **-sourcepath src** |
| **-classpath** hoặc **-cp** | Tìm lớp đã biên dịch và thư viện JAR phụ thuộc | **-cp lib/library.jar** |
| **-d** | Chọn nơi ghi các tệp .class được tạo | **-d out** |

Ví dụ khi source sử dụng một thư viện đã đóng gói thành JAR:

~~~bash
javac --release 17 -cp "lib/library.jar" -d out src/com/example/app/Main.java
~~~

Classpath ở đây cho javac biết vị trí lớp và API trong JAR mà source đang tham chiếu. Nó không thay thế sourcepath nếu cần tìm các tệp .java chưa biên dịch.

Có thể kết hợp cả ba:

~~~bash
javac --release 17 -encoding UTF-8 -sourcepath src -cp "lib/*" -d out src/com/example/app/Main.java
~~~

Dấu **\*** trong **lib/*** cho phép classpath bao gồm các tệp JAR trong thư mục **lib**. Wildcard này áp dụng cho các JAR trực tiếp trong thư mục đó, không tự tìm đệ quy trong mọi thư mục con.

Nếu đã chỉ định **-cp**, hãy nhớ rằng classpath mặc định có thể bị thay thế. Khi cần dùng cả lớp đã biên dịch trong **out** và các thư viện trong **lib**, hãy thêm cả hai vào classpath.

Dấu phân cách nhiều mục classpath phụ thuộc hệ điều hành:

| Hệ điều hành | Dấu phân cách | Ví dụ |
|---|---|---|
| Windows | Dấu chấm phẩy **;** | **out;lib/*;tools/helper.jar** |
| Linux và macOS | Dấu hai chấm **:** | **out:lib/*:tools/helper.jar** |

Đặt classpath trong dấu nháy giúp shell không diễn giải ký tự wildcard trước khi Java nhận được chuỗi.

## 7. Các tùy chọn javac hữu ích khi biên dịch nhiều source

### Chọn phiên bản Java với --release

~~~bash
javac --release 17 -d out src/com/example/app/Main.java
~~~

**--release 17** yêu cầu compiler tạo bytecode và chỉ cho phép sử dụng API nền tảng được hỗ trợ ở Java 17. Đây là cách phù hợp khi dùng JDK mới hơn để biên dịch ứng dụng cần chạy trên Java 17.

**--release** có từ JDK 9. Nếu cần hỗ trợ một JDK cũ hơn JDK 9, phải xem tùy chọn tương thích có sẵn trong phiên bản compiler đó.

### Chọn encoding

~~~bash
javac -encoding UTF-8 -d out src/com/example/app/Main.java
~~~

**-encoding UTF-8** chỉ định bộ mã ký tự dùng để đọc source. Nên thống nhất UTF-8 cho toàn dự án, đặc biệt khi mã nguồn có tiếng Việt hoặc ký tự ngoài ASCII. Nếu source lưu theo encoding khác nhưng compiler đọc bằng encoding không khớp, chuỗi và comment có thể bị sai ký tự.

### Hiển thị cảnh báo

~~~bash
javac -Xlint:all -d out src/com/example/app/Main.java
~~~

**-Xlint:all** yêu cầu compiler báo thêm các cảnh báo. Có thể dùng **-Werror** để biến cảnh báo thành lỗi trong quy trình kiểm soát chất lượng khi dự án đã xử lý các cảnh báo cần thiết:

~~~bash
javac -Xlint:all -Werror -d out src/com/example/app/Main.java
~~~

Không nên bật **-Werror** một cách bất ngờ trong dự án cũ chưa được kiểm tra cảnh báo, vì các cảnh báo mới có thể làm lần biên dịch thất bại.

### Xem quá trình biên dịch

~~~bash
javac -verbose -d out src/com/example/app/Main.java
~~~

**-verbose** in thêm thông tin về các tệp được nạp và các lớp được biên dịch. Đây là công cụ chẩn đoán hữu ích khi cần biết compiler đang tìm source hoặc lớp ở đâu; đầu ra có thể rất dài.

## 8. Dùng argument file khi có nhiều tệp nguồn

Một dự án có hàng chục hoặc hàng trăm source có thể tạo lệnh rất dài. Khi đó, đưa các tùy chọn và đường dẫn vào một argument file, ví dụ **sources.txt**:

~~~text
--release
17
-encoding
UTF-8
-d
out
src/com/example/model/Message.java
src/com/example/service/GreetingService.java
src/com/example/app/Main.java
~~~

Sau đó gọi:

~~~bash
javac @sources.txt
~~~

Ký tự **@** yêu cầu javac đọc các đối số từ tệp được chỉ định. Argument file có thể chứa compiler option và tên tệp nguồn; mỗi dòng là một đối số trong ví dụ đơn giản này.

Nếu đường dẫn có dấu cách, đặt riêng đường dẫn đó trong dấu nháy kép theo cú pháp argument file. Khi tạo file, dùng encoding phù hợp với môi trường chạy javac. Đường dẫn tương đối bên trong file cần được hiểu theo thư mục làm việc khi gọi lệnh; hãy thống nhất thư mục chạy để tránh lỗi tìm tệp.

Argument file giúp tránh giới hạn độ dài dòng lệnh của shell hoặc hệ điều hành và giúp lưu tập source cần biên dịch để tái sử dụng. Khi dự án có nhiều phụ thuộc và cần biên dịch gia tăng, Maven hoặc Gradle thường phù hợp hơn việc tự quản lý danh sách file thủ công.

## 9. Biên dịch source có phụ thuộc vào thư viện ngoài

Giả sử một lớp sử dụng kiểu được cung cấp bởi **library.jar**. javac phải có thư viện đó trên classpath khi biên dịch:

~~~bash
javac --release 17 -cp "lib/library.jar" -d out src/com/example/app/Main.java
~~~

Nếu chương trình còn phụ thuộc các lớp khác của dự án, thêm thư mục chứa các lớp đã biên dịch vào classpath. Ví dụ:

~~~bash
javac --release 17 -cp "out;lib/*" -d out src/com/example/app/Main.java
~~~

Ví dụ trên dùng dấu phân cách của Windows. Trên Linux hoặc macOS, thay dấu chấm phẩy bằng dấu hai chấm:

~~~bash
javac --release 17 -cp "out:lib/*" -d out src/com/example/app/Main.java
~~~

Biên dịch thành công chưa có nghĩa chương trình sẽ chạy được nếu runtime không tìm thấy thư viện. Khi chạy, classpath cũng phải bao gồm thư mục **out** và các JAR cần thiết:

Windows:

~~~bat
java -cp "out;lib/*" com.example.app.Main
~~~

Linux hoặc macOS:

~~~bash
java -cp "out:lib/*" com.example.app.Main
~~~

Hãy bảo đảm các thư viện có mặt cả ở bước biên dịch lẫn bước chạy. Classpath khi chạy không được tự động kế thừa từ lệnh javac trước đó.

## 10. Kiểm tra kết quả biên dịch

Sau khi biên dịch, kiểm tra thư mục đầu ra có các tệp class theo package:

~~~text
out/com/example/model/Message.class
out/com/example/service/GreetingService.class
out/com/example/app/Main.class
~~~

Trên Windows có thể dùng:

~~~bat
dir /s /b out\*.class
~~~

Trên Linux hoặc macOS:

~~~bash
find out -name "*.class"
~~~

Chạy lớp chính bằng tên đầy đủ:

~~~bash
java -cp out com.example.app.Main
~~~

Nếu ứng dụng có thư viện ngoài, thêm các JAR vào classpath chạy. Nếu dùng module Java, cách biên dịch và chạy cần tuân theo module path và cấu trúc module tương ứng; không trộn tùy tiện classpath với module path.

## 11. Lỗi thường gặp và cách xử lý

### error: file not found

javac không tìm thấy đường dẫn source đã nhập. Kiểm tra thư mục làm việc hiện tại, tên tệp, phần mở rộng .java và cách viết dấu phân cách thư mục theo hệ điều hành. Nếu dùng đường dẫn tương đối, xác nhận lệnh đang được chạy từ thư mục gốc dự án như dự định.

### package ... does not exist hoặc cannot find symbol

Compiler không tìm thấy kiểu hoặc package được import. Kiểm tra:

- Tệp nguồn khai báo package đúng với cấu trúc thư mục.
- Tệp nguồn phụ thuộc đã nằm trong danh sách lệnh hoặc có thể được tìm qua **-sourcepath**.
- Lớp đã biên dịch hoặc thư viện JAR nằm trong **-cp**.
- Tên package, lớp và chữ hoa/chữ thường chính xác.

Nếu phụ thuộc là source chưa biên dịch, **-cp** đơn thuần không thay thế cho **-sourcepath**. Nếu phụ thuộc là JAR hoặc class đã biên dịch, hãy thêm chúng vào classpath.

### class ... is public, should be declared in a file named ...

Tên tệp không khớp tên lớp public cấp cao nhất. Đổi tên tệp hoặc tên lớp cho khớp. Ví dụ **public class GreetingService** phải được khai báo trong **GreetingService.java**.

### duplicate class

Có thể cùng một lớp được khai báo ở nhiều tệp hoặc cùng source bị đưa vào nhiều lần từ các thư mục khác nhau. Kiểm tra package, tên lớp và danh sách source. Không biên dịch đồng thời hai phiên bản cùng tên đầy đủ của một lớp.

### incompatible types hoặc lỗi tham chiếu giữa các lớp

Kiểm tra chữ ký phương thức, kiểu trả về, constructor, phạm vi truy cập và import. Biên dịch nhiều source trong cùng lệnh giúp javac nhìn thấy các khai báo cùng lượt, nhưng không sửa được mâu thuẫn kiểu hoặc thiết kế kế thừa vòng không hợp lệ.

### Unsupported release

Compiler hiện tại không hỗ trợ release được yêu cầu. Kiểm tra phiên bản bằng **javac -version** và dùng JDK có hỗ trợ mức **--release** đó. Ví dụ muốn dùng **--release 17**, hãy dùng javac từ JDK 17 trở lên.

### Chạy gặp ClassNotFoundException hoặc NoClassDefFoundError

Đây thường là vấn đề ở bước chạy. Kiểm tra thư mục gốc classpath có chứa cây package đã biên dịch hay không, tên lớp chính có đầy đủ package hay không, và thư viện phụ thuộc đã có trên classpath runtime hay chưa. Không trỏ classpath thẳng vào thư mục package con khi lớp chính được gọi bằng tên đầy đủ.

### Biên dịch được nhưng chạy mã cũ

Có thể thư mục output còn các tệp .class cũ hoặc bạn đang chạy từ classpath khác. Biên dịch vào một thư mục output riêng, kiểm tra thời gian và vị trí tệp class, rồi bảo đảm lệnh java dùng đúng thư mục đó. Với dự án lớn, dùng build tool để quản lý việc xóa output cũ và biên dịch lại phần bị ảnh hưởng.

## 12. Khi nào nên dùng Maven hoặc Gradle?

Gọi javac trực tiếp phù hợp với bài học, chương trình nhỏ, ví dụ độc lập hoặc khi cần hiểu rõ quy trình compiler. Khi dự án có nhiều module, thư viện, tài nguyên, kiểm thử, plugin và cấu hình môi trường, danh sách source và classpath thủ công sẽ khó duy trì.

Maven và Gradle giúp quản lý:

- Danh sách source và cấu trúc source set.
- Thư viện phụ thuộc và phiên bản.
- Biên dịch gia tăng, thứ tự tác vụ và thư mục output.
- Kiểm thử, đóng gói JAR và quy trình build trên CI.
- Phiên bản Java mục tiêu và toolchain của dự án.

Dù dùng build tool, hiểu **javac**, **-sourcepath**, **-cp**, **-d** và **--release** vẫn hữu ích khi đọc log build hoặc xử lý lỗi biên dịch.

## 13. Checklist biên dịch nhiều source

- [ ] Đang chạy lệnh từ đúng thư mục gốc dự án.
- [ ] Mỗi source có package và tên tệp hợp lệ.
- [ ] Đã liệt kê mọi source cần thiết hoặc khai báo **-sourcepath**.
- [ ] Các lớp và JAR đã biên dịch nằm trong **-cp** nếu source cần chúng.
- [ ] Đã dùng **-d** để quản lý nơi lưu bytecode.
- [ ] Đã thống nhất encoding, thường là UTF-8.
- [ ] Đã chọn mức Java tương thích bằng **--release**.
- [ ] Đã kiểm tra cấu trúc .class được tạo theo package.
- [ ] Classpath khi chạy có thư mục output và mọi thư viện cần thiết.
- [ ] Đã chạy lớp chính bằng tên đầy đủ và kiểm tra kết quả.
