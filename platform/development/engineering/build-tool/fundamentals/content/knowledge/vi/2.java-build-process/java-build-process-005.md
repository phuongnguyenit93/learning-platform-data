# Thêm thư viện JAR vào quy trình biên dịch và thực thi thủ công

Khi viết một chương trình Java có sử dụng thư viện bên ngoài, mã nguồn thường tham chiếu đến các lớp không nằm trong JDK. Những lớp đó có thể được cung cấp dưới dạng một hoặc nhiều tệp JAR. Để biên dịch và chạy chương trình bằng các lệnh Java trực tiếp, cần chỉ cho công cụ biết nơi tìm thấy các lớp này ở cả hai giai đoạn.

Cơ chế dùng để chỉ định những vị trí đó được gọi là **classpath**. Có thể hiểu đơn giản: classpath là danh sách các thư mục và tệp JAR mà trình biên dịch hoặc JVM sẽ tìm kiếm khi cần nạp một lớp. Một quy trình thủ công hoàn chỉnh thường gồm việc chuẩn bị JAR, thêm JAR vào classpath khi biên dịch, thêm các JAR cần thiết vào classpath khi chạy, rồi kiểm tra kết quả.

## 1. JAR là gì và vì sao chương trình cần classpath?

JAR (Java ARchive) là một tệp lưu trữ theo định dạng ZIP, thường chứa các tệp bytecode **.class**, tài nguyên và thông tin mô tả. Một thư viện Java thường được phân phối dưới dạng JAR để chương trình khác có thể sử dụng các lớp mà thư viện cung cấp.

Ví dụ, mã nguồn có thể nhập một lớp từ thư viện Gson:

~~~java
package com.example;

import com.google.gson.Gson;

public class Main {
    public static void main(String[] args) {
        Gson gson = new Gson();
        System.out.println(gson.toJson("Hello JAR"));
    }
}
~~~

Lớp **Gson** không thuộc JDK. Nếu chỉ gọi trình biên dịch với tệp nguồn, **javac** không biết lớp này nằm trong JAR nào và có thể báo lỗi không tìm thấy package hoặc symbol. Khi chạy, JVM cũng cần tìm được bytecode của **Gson** và các lớp mà thư viện phụ thuộc.

Vì vậy, cần cung cấp JAR cho hai công cụ:

- **javac** cần tìm thư viện để kiểm tra các kiểu dữ liệu, phương thức và trường được dùng trong mã nguồn.
- **java** cần tìm thư viện để nạp các lớp khi chương trình thực thi.

Biên dịch thành công không đồng nghĩa chương trình đã có đủ thư viện lúc chạy. JAR bên ngoài thường vẫn nằm ở vị trí riêng và không tự động được chép vào thư mục chứa các tệp **.class** của ứng dụng.

## 2. Chuẩn bị cấu trúc thư mục

Có thể sắp xếp một dự án Java nhỏ như sau:

~~~text
my-java-app/
├── lib/
│   └── gson-2.10.1.jar
├── src/
│   └── com/
│       └── example/
│           └── Main.java
└── out/
~~~

Trong cấu trúc này:

- **src/** chứa mã nguồn.
- **lib/** chứa các thư viện JAR bên ngoài.
- **out/** là nơi lưu các tệp **.class** sau khi biên dịch.
- **gson-2.10.1.jar** là ví dụ về một thư viện. Hãy thay tên và phiên bản bằng tệp JAR thực tế của dự án.

Nên chạy các lệnh từ thư mục gốc **my-java-app/** để các đường dẫn tương đối trong ví dụ có cùng ý nghĩa. Nếu chạy lệnh từ thư mục khác, hãy điều chỉnh đường dẫn cho phù hợp hoặc chuyển về thư mục gốc trước.

Một JAR có thể chứa nhiều package. Đường dẫn package trong JAR tương ứng với tên package trong mã nguồn. Chẳng hạn, lớp **com.google.gson.Gson** thường nằm tại đường dẫn **com/google/gson/Gson.class** bên trong JAR. Khi tìm lớp này, classpath phải trỏ đến **tệp JAR**, không phải một đường dẫn giả định đến từng tệp **.class** bên trong.

## 3. Thêm JAR vào classpath khi biên dịch

Tùy chọn **-cp** hoặc **-classpath** của **javac** chỉ định classpath dùng trong lúc biên dịch. Có thể dùng dạng ngắn **-cp** hoặc dạng dài **--class-path**.

~~~text
javac -cp "đường-dẫn-thư-viện" -d thư-mục-đầu-ra đường-dẫn-tệp-nguồn
~~~

Với cấu trúc ví dụ ở trên, lệnh biên dịch là:

~~~bash
javac -cp "lib/gson-2.10.1.jar" -d out src/com/example/Main.java
~~~

Ý nghĩa từng phần:

- **javac**: gọi trình biên dịch Java.
- **-cp "lib/gson-2.10.1.jar"**: thêm JAR Gson vào classpath để **javac** tìm thấy lớp **com.google.gson.Gson**.
- **-d out**: ghi các tệp **.class** vào thư mục **out**, đồng thời tạo các thư mục package cần thiết.
- **src/com/example/Main.java**: tệp mã nguồn cần biên dịch.

Sau khi biên dịch, cấu trúc đầu ra sẽ có dạng:

~~~text
my-java-app/
├── lib/
│   └── gson-2.10.1.jar
├── src/
│   └── com/
│       └── example/
│           └── Main.java
└── out/
    └── com/
        └── example/
            └── Main.class
~~~

Thư mục **out/** là **gốc của classpath** cho các lớp ứng dụng đã biên dịch. Khi tên lớp đầy đủ là **com.example.Main**, JVM tìm tệp **com/example/Main.class** bên dưới mỗi mục classpath. Do đó, classpath cần chứa **out/**, không phải **out/com/example/**.

### Biên dịch trên Windows

Trên Windows, dấu phân cách giữa các mục classpath là dấu chấm phẩy (**;**). Với một JAR, lệnh giống ví dụ trên:

~~~powershell
javac -cp "lib/gson-2.10.1.jar" -d out src/com/example/Main.java
~~~

Nếu đường dẫn chứa khoảng trắng, hãy đặt đường dẫn trong dấu ngoặc kép:

~~~powershell
javac -cp "third-party libraries/gson-2.10.1.jar" -d out src/com/example/Main.java
~~~

### Biên dịch trên macOS và Linux

Trên macOS và Linux, dấu phân cách giữa các mục classpath là dấu hai chấm (**:**):

~~~bash
javac -cp "lib/gson-2.10.1.jar" -d out src/com/example/Main.java
~~~

Dù lệnh ví dụ có một JAR nên chưa thể hiện sự khác nhau về dấu phân cách, quy tắc này sẽ quan trọng khi thêm nhiều mục classpath.

## 4. Thêm nhiều thư viện JAR

Một ứng dụng có thể cần nhiều thư viện cùng lúc. Hãy liệt kê tất cả thư mục hoặc JAR trong cùng một giá trị classpath và ngăn cách chúng bằng ký tự phù hợp với hệ điều hành.

Ví dụ, dự án có hai thư viện:

~~~text
lib/
├── gson-2.10.1.jar
└── commons-lang3-3.14.0.jar
~~~

Trên Windows:

~~~powershell
javac -cp "lib/gson-2.10.1.jar;lib/commons-lang3-3.14.0.jar" -d out src/com/example/Main.java
~~~

Trên macOS và Linux:

~~~bash
javac -cp "lib/gson-2.10.1.jar:lib/commons-lang3-3.14.0.jar" -d out src/com/example/Main.java
~~~

Nếu thư mục **lib/** chỉ chứa các JAR cần dùng, có thể sử dụng ký tự đại diện **\*** để đưa các JAR trực tiếp trong thư mục đó vào classpath:

~~~text
javac -cp "lib/*" -d out src/com/example/Main.java
~~~

Cách viết này được hỗ trợ trên cả Windows, macOS và Linux. Đặt biểu thức trong dấu ngoặc kép để shell không tự xử lý ký tự đại diện trước khi chuyển đối số cho công cụ Java.

Ký tự đại diện **\*** chỉ bao gồm các tệp JAR trực tiếp trong thư mục được chỉ định; nó không tự tìm JAR trong các thư mục con. Nếu thư viện được sắp xếp theo nhiều thư mục con, cần liệt kê từng thư mục hoặc JAR phù hợp.

Khi có nhiều phiên bản của cùng một thư viện hoặc nhiều JAR chứa lớp trùng tên, thứ tự classpath có thể ảnh hưởng đến lớp được tìm thấy trước. Trong tình huống đó, hãy khai báo rõ từng JAR và kiểm tra phiên bản để tránh nạp nhầm lớp.

## 5. Thêm JAR vào classpath khi chạy chương trình

Sau khi biên dịch, cần chỉ định cả:

1. Thư mục chứa các lớp của ứng dụng, ví dụ **out/**.
2. Các JAR mà ứng dụng cần khi thực thi, ví dụ **lib/gson-2.10.1.jar**.

Cú pháp tổng quát:

~~~text
java -cp "classpath" tên-lớp-đầy-đủ
~~~

Trên macOS và Linux:

~~~bash
java -cp "out:lib/gson-2.10.1.jar" com.example.Main
~~~

Trên Windows:

~~~powershell
java -cp "out;lib/gson-2.10.1.jar" com.example.Main
~~~

Kết quả ví dụ:

~~~text
"Hello JAR"
~~~

Tên **com.example.Main** là tên lớp đầy đủ (fully qualified class name), bao gồm package. Không thêm phần mở rộng **.class** và không viết đường dẫn tệp nguồn **.java** ở vị trí này.

Nếu chương trình cần nhiều JAR, hãy đưa chúng vào classpath khi chạy giống như khi biên dịch:

~~~text
# Windows
java -cp "out;lib/gson-2.10.1.jar;lib/commons-lang3-3.14.0.jar" com.example.Main

# macOS hoặc Linux
java -cp "out:lib/gson-2.10.1.jar:lib/commons-lang3-3.14.0.jar" com.example.Main
~~~

Có thể dùng **lib/*** để nạp tất cả JAR trực tiếp trong thư mục **lib/**:

~~~text
# Windows
java -cp "out;lib/*" com.example.Main

# macOS hoặc Linux
java -cp "out:lib/*" com.example.Main
~~~

Điều quan trọng là classpath khi chạy phải chứa mọi thư viện cần thiết ở thời điểm thực thi. Một thư viện có thể phụ thuộc vào thư viện khác; khi đó cần đưa cả dependency bắc cầu (transitive dependency) vào classpath nếu chúng không được đóng gói sẵn theo cách khác.

## 6. Phân biệt classpath lúc biên dịch và lúc chạy

Classpath của **javac** và **java** phục vụ hai giai đoạn khác nhau:

| Giai đoạn | Công cụ | Cần đưa vào classpath |
|---|---|---|
| Biên dịch | **javac** | Thư mục hoặc JAR chứa các lớp mà mã nguồn tham chiếu đến |
| Thực thi | **java** | Thư mục chứa lớp ứng dụng và mọi JAR cần để nạp lớp khi chạy |

Hai classpath thường có phần thư viện giống nhau, nhưng classpath lúc chạy còn cần chứa đầu ra biên dịch của ứng dụng. Ví dụ:

~~~text
Biên dịch:
javac -cp "lib/gson-2.10.1.jar" -d out src/com/example/Main.java

Thực thi trên Windows:
java -cp "out;lib/gson-2.10.1.jar" com.example.Main

Thực thi trên macOS hoặc Linux:
java -cp "out:lib/gson-2.10.1.jar" com.example.Main
~~~

Một số tình huống thường gặp:

- **Có JAR khi biên dịch nhưng thiếu lúc chạy:** **javac** có thể biên dịch thành công, nhưng JVM báo không tìm thấy lớp khi chương trình sử dụng thư viện.
- **Có JAR lúc chạy nhưng thiếu khi biên dịch:** nếu mã nguồn nhập hoặc tham chiếu trực tiếp đến lớp của thư viện, **javac** vẫn không thể biên dịch.
- **Thiếu dependency bắc cầu:** ứng dụng tìm thấy thư viện chính nhưng một lớp mà thư viện đó cần lại không có trên classpath. Lỗi thường xuất hiện khi đường chạy thực sự cần đến lớp bị thiếu.
- **Đưa sai thư mục vào classpath:** nếu lớp có package **com.example**, classpath phải trỏ đến thư mục nằm ngay phía trên **com/**.

Vì vậy, khi kiểm tra một quy trình thủ công, hãy xem riêng lệnh biên dịch và lệnh chạy. Không nên giả định rằng thiết lập ở lệnh thứ nhất tự động được áp dụng cho lệnh thứ hai.

## 7. Dùng biến môi trường CLASSPATH

Java cũng hỗ trợ biến môi trường **CLASSPATH**. Khi không truyền **-cp** hoặc **-classpath** trên dòng lệnh, công cụ Java có thể sử dụng giá trị biến môi trường này. Tuy nhiên, cách này làm cho lệnh biên dịch và thực thi phụ thuộc vào cấu hình của terminal hoặc máy đang dùng.

Ví dụ trên PowerShell:

~~~powershell
$env:CLASSPATH = "out;lib/gson-2.10.1.jar"
java com.example.Main
~~~

Trên macOS hoặc Linux:

~~~bash
export CLASSPATH="out:lib/gson-2.10.1.jar"
java com.example.Main
~~~

Có thể đặt lại biến môi trường trong PowerShell:

~~~powershell
Remove-Item Env:CLASSPATH
~~~

Và trong macOS hoặc Linux:

~~~bash
unset CLASSPATH
~~~

Với bài tập, hướng dẫn hoặc script cần chạy lặp lại, nên ghi rõ classpath ngay trong lệnh bằng **-cp**. Như vậy người đọc dễ biết chương trình đang dùng thư viện nào, đồng thời giảm ảnh hưởng của cấu hình cũ trong môi trường.

Khi truyền **-cp** trên dòng lệnh, giá trị đó được dùng làm classpath cho lệnh hiện tại. Nếu cần thư mục hiện hành, hãy thêm dấu chấm (**.**) như một mục classpath riêng. Ví dụ:

~~~text
# Windows
java -cp ".;out;lib/*" com.example.Main

# macOS hoặc Linux
java -cp ".:out:lib/*" com.example.Main
~~~

## 8. Phân biệt chạy một lớp bằng classpath và chạy ứng dụng bằng java -jar

Không phải mọi JAR đều là ứng dụng có thể chạy trực tiếp. Một JAR thư viện thường chỉ chứa các lớp để chương trình khác sử dụng; nó có thể không khai báo lớp khởi chạy.

### Chạy lớp chính bằng classpath

Khi dùng classpath, ta chỉ định tên lớp có phương thức **main**:

~~~text
java -cp "out;lib/*" com.example.Main
~~~

Trên macOS hoặc Linux, thay dấu chấm phẩy bằng dấu hai chấm:

~~~text
java -cp "out:lib/*" com.example.Main
~~~

Cách này phù hợp khi lớp chính nằm trong thư mục đầu ra và các thư viện được lưu riêng.

### Chạy một JAR thực thi bằng java -jar

Một JAR thực thi (executable JAR) cần khai báo thuộc tính **Main-Class** trong tệp manifest. Ví dụ nội dung **MANIFEST.MF**:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main
Class-Path: lib/gson-2.10.1.jar

~~~

Sau khi đã biên dịch lớp ứng dụng vào **out/**, có thể tạo JAR ứng dụng:

~~~bash
jar --create --file app.jar --manifest MANIFEST.MF -C out .
~~~

Sau đó chạy:

~~~bash
java -jar app.jar
~~~

Thuộc tính **Main-Class** cho JVM biết lớp nào cần chạy. Thuộc tính **Class-Path** khai báo các JAR bổ sung mà ứng dụng cần. Các đường dẫn trong **Class-Path** của manifest được phân giải tương đối từ vị trí của JAR ứng dụng; trong ví dụ, **lib/gson-2.10.1.jar** phải nằm trong thư mục **lib/** cạnh **app.jar**.

Có một điểm cần nhớ: khi dùng tùy chọn **-jar**, JVM lấy thông tin classpath từ JAR và manifest theo cơ chế của chế độ này; các thiết lập classpath khác trên dòng lệnh hoặc từ biến môi trường không được dùng để bổ sung classpath. Vì vậy, lệnh sau không phải cách để thêm Gson vào một JAR đang chạy bằng **-jar**:

~~~text
java -cp "lib/gson-2.10.1.jar" -jar app.jar
~~~

Hãy khai báo dependency trong manifest, đóng gói dependency theo cách phù hợp, hoặc chạy lớp chính bằng **-cp** thay vì **-jar**.

Một JAR thư viện không có **Main-Class** thường không thể chạy bằng **java -jar**. Điều đó không có nghĩa JAR bị hỏng; nó chỉ được thiết kế để đặt trên classpath của một ứng dụng khác.

## 9. Kiểm tra nội dung JAR và cấu hình Java

Khi nghi ngờ đường dẫn hoặc nội dung thư viện, có thể dùng các công cụ đi kèm JDK để kiểm tra.

Xem phiên bản Java:

~~~text
java -version
javac -version
~~~

Hai phiên bản nên tương thích với nhau. Nếu biên dịch bằng JDK mới nhưng chạy bằng một runtime cũ, chương trình có thể gặp lỗi phiên bản bytecode.

Liệt kê nội dung JAR:

~~~text
jar tf lib/gson-2.10.1.jar
~~~

Kết quả sẽ liệt kê các mục bên trong JAR. Có thể tìm đường dẫn lớp cần dùng, chẳng hạn **com/google/gson/Gson.class**, để xác nhận JAR có chứa lớp đó.

Kiểm tra một lớp công khai trong thư viện:

~~~text
javap -classpath lib/gson-2.10.1.jar com.google.gson.Gson
~~~

Lệnh này hiển thị chữ ký lớp và các thành phần công khai mà trình biên dịch có thể nhìn thấy. Đây là cách hữu ích để kiểm tra tên package, tên lớp hoặc phương thức khi ví dụ mã nguồn không khớp với phiên bản JAR đang có.

Khi đường dẫn có khoảng trắng, hãy đặt toàn bộ đường dẫn hoặc giá trị classpath trong dấu ngoặc kép. Khi dùng nhiều mục classpath, hãy kiểm tra dấu phân cách theo hệ điều hành và xác nhận từng tệp thực sự tồn tại.

## 10. Các lỗi thường gặp và cách xử lý

| Thông báo hoặc biểu hiện | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
|---|---|---|
| **package ... does not exist** | JAR chưa có trong classpath biên dịch, đường dẫn JAR sai hoặc JAR không chứa package cần dùng | Kiểm tra đường dẫn; dùng **jar tf** để xem nội dung; bổ sung JAR vào **javac -cp** |
| **cannot find symbol** | Lớp, phương thức hoặc trường không tồn tại trong phiên bản thư viện đang dùng; import sai; thiếu dependency khi biên dịch | Kiểm tra import, phiên bản JAR và chữ ký API bằng **javap** |
| **Could not find or load main class** | Tên lớp chính sai, package không khớp hoặc classpath không trỏ đến gốc chứa package | Kiểm tra tên đầy đủ, vị trí tệp **.class** và mục classpath |
| **NoClassDefFoundError** | JVM cần một lớp nhưng không tìm thấy khi chạy; thường do thiếu JAR hoặc thiếu dependency bắc cầu | Bổ sung JAR cần thiết vào classpath lúc chạy; kiểm tra thư viện phụ thuộc |
| **ClassNotFoundException** | Mã chương trình hoặc framework đang tìm một lớp theo tên nhưng classloader không tìm thấy lớp đó | Kiểm tra tên lớp, classpath và cơ chế nạp lớp đang sử dụng |
| **no main manifest attribute** | JAR không khai báo **Main-Class** nhưng được chạy bằng **java -jar** | Thêm **Main-Class** vào manifest hoặc chạy lớp chính bằng **java -cp** |
| **UnsupportedClassVersionError** | Bytecode được biên dịch bằng phiên bản Java mới hơn phiên bản runtime đang chạy | Kiểm tra **java -version** và **javac -version**; dùng runtime phù hợp hoặc biên dịch cho phiên bản mục tiêu tương thích |
| **NoSuchMethodError** | Lúc chạy JVM nạp một phiên bản thư viện khác với phiên bản mà mã đã biên dịch dựa vào | Kiểm tra thứ tự và phiên bản các JAR trên classpath; loại bỏ bản trùng hoặc bản không tương thích |

### Một quy trình chẩn đoán ngắn

Khi chương trình không chạy được, hãy kiểm tra theo thứ tự sau:

1. Xác nhận JAR tồn tại tại đúng đường dẫn mà lệnh sử dụng.
2. Dùng **jar tf** để xác nhận JAR có lớp cần thiết.
3. Kiểm tra classpath của lệnh **javac**, nếu lỗi xảy ra khi biên dịch.
4. Kiểm tra classpath của lệnh **java**, nếu lỗi xảy ra khi thực thi.
5. Kiểm tra tên package và tên lớp chính; classpath phải trỏ đến gốc của cây package.
6. Kiểm tra các dependency bắc cầu và phiên bản thư viện nếu lỗi chỉ xuất hiện khi một chức năng cụ thể được gọi.
7. Kiểm tra phiên bản JDK và runtime nếu thông báo lỗi đề cập đến phiên bản bytecode.

## 11. Quy trình mẫu hoàn chỉnh

Giả sử có mã nguồn **src/com/example/Main.java** sử dụng Gson, JAR nằm trong **lib/**, và kết quả biên dịch được ghi vào **out/**.

**Bước 1: Xác nhận cấu trúc dự án**

~~~text
my-java-app/
├── lib/
│   └── gson-2.10.1.jar
├── src/
│   └── com/
│       └── example/
│           └── Main.java
└── out/
~~~

**Bước 2: Biên dịch mã nguồn**

~~~text
javac -cp "lib/gson-2.10.1.jar" -d out src/com/example/Main.java
~~~

**Bước 3: Chạy ứng dụng**

Windows:

~~~powershell
java -cp "out;lib/gson-2.10.1.jar" com.example.Main
~~~

macOS hoặc Linux:

~~~bash
java -cp "out:lib/gson-2.10.1.jar" com.example.Main
~~~

**Bước 4: Kiểm tra kết quả**

Nếu chương trình in ra chuỗi JSON mong đợi, JVM đã tìm được lớp ứng dụng và thư viện trong ví dụ. Nếu có lỗi, hãy xác định lỗi phát sinh ở bước biên dịch hay bước chạy rồi kiểm tra classpath tương ứng.

## 12. Những nguyên tắc cần nhớ

- Một JAR thư viện cần được đưa vào classpath của **javac** nếu mã nguồn tham chiếu đến các lớp trong JAR đó.
- Các JAR cần thiết phải có trong classpath của JVM khi chạy chương trình.
- Khi chạy bằng classpath, phải đưa thư mục gốc chứa package của ứng dụng vào classpath và gọi lớp chính bằng tên đầy đủ.
- Dùng dấu chấm phẩy (**;**) để ngăn cách các mục classpath trên Windows; dùng dấu hai chấm (**:**) trên macOS và Linux.
- Có thể dùng **lib/*** để đưa các JAR trực tiếp trong một thư mục vào classpath; biểu thức này không tìm đệ quy trong thư mục con.
- **java -jar** cần JAR thực thi có khai báo **Main-Class**. Nếu ứng dụng cần JAR bên ngoài, hãy khai báo chúng trong manifest hoặc chọn cách chạy phù hợp.
- Ưu tiên ghi classpath rõ ràng trong lệnh hoặc script để quy trình biên dịch và thực thi có thể được lặp lại trên máy khác.

Nắm được cách thêm JAR vào classpath giúp ta hiểu rõ quy trình Java thủ công: mã nguồn được biên dịch thành bytecode, các thư viện được tham chiếu từ những vị trí xác định, và JVM nạp các lớp cần thiết khi chương trình chạy. Đây cũng là nền tảng để hiểu cách các công cụ build như Maven hoặc Gradle quản lý dependency và classpath tự động.
