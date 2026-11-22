# Main class trong Java launcher

## Mục tiêu

Sau bài này, bạn có thể xác định main class mà Java launcher sẽ chạy, viết đúng entry point, truyền tham số dòng lệnh, chạy chương trình từ thư mục class, JAR, module hoặc source file, và hiểu các thay đổi về instance main method từ Java 25.

## 1. Main class là gì?

**Main class** là class được chọn làm điểm bắt đầu (initial class) khi khởi chạy một ứng dụng Java. Java launcher thường là chương trình có tên **java** trong thư mục bin của JDK. Launcher nhận biết class hoặc ứng dụng cần chạy, khởi động JVM, nạp class được chọn và yêu cầu JVM gọi một phương thức main hợp lệ.

Main class không bắt buộc phải có tên là Main. Tên class có thể là App, HelloWorld, Server, com.example.Application hoặc bất kỳ tên hợp lệ nào. Tên Main chỉ là quy ước thường gặp trong ví dụ.

Cần phân biệt:

- **Main class:** class được chọn để bắt đầu một lần chạy.
- **main method:** phương thức entry point bên trong main class.
- **Java launcher:** công cụ java nhận lệnh và thiết lập việc khởi chạy.
- **JVM:** máy ảo thực thi bytecode sau khi launcher khởi động runtime.

Một thư viện Java có thể chứa hàng trăm class mà không có main method. Chỉ chương trình cần chạy trực tiếp mới cần một entry point. Một dự án cũng có thể có nhiều class chứa main method để cung cấp nhiều ứng dụng hoặc công cụ khác nhau; mỗi lần chạy, launcher chọn một điểm bắt đầu cụ thể.

## 2. Entry point truyền thống

Trong Java 8 đến Java 24, dạng entry point thông dụng là:

~~~java
public class Main {
    public static void main(String[] args) {
        System.out.println("Hello, Java!");
    }
}
~~~

Phương thức này có bốn thành phần quan trọng:

| Thành phần | Ý nghĩa |
|---|---|
| public | Cho phép launcher truy cập phương thức theo quy tắc entry point truyền thống |
| static | Gọi phương thức trực tiếp trên class, không cần tạo object trước |
| void | Phương thức không trả về giá trị |
| String[] args | Mảng chứa các đối số chương trình nhận từ dòng lệnh |

Tên phương thức phải là main, viết thường. Java phân biệt chữ hoa và chữ thường, vì vậy Main, MAIN hoặc start không phải tên entry point tương đương.

### Vì sao main là static?

Với entry point truyền thống, JVM cần bắt đầu chạy chương trình trước khi ứng dụng có thể tự tạo các object thông thường. Phương thức static thuộc về class nên có thể được gọi mà không cần tạo một instance của class đó.

Từ Java 25, Java hỗ trợ thêm instance main method. Khi dùng dạng này, launcher tự tạo instance của main class trước khi gọi phương thức. Phần sau sẽ trình bày rõ sự khác nhau.

### Vì sao tham số là String[]?

Launcher chuyển các đối số trên dòng lệnh thành một mảng String và truyền mảng đó vào main. Ví dụ:

~~~java
public class Main {
    public static void main(String[] args) {
        System.out.println("Số đối số: " + args.length);

        for (int i = 0; i < args.length; i++) {
            System.out.println("args[" + i + "] = " + args[i]);
        }
    }
}
~~~

Chạy:

~~~text
java Main Alice "Java Core"
~~~

Kết quả:

~~~text
Số đối số: 2
args[0] = Alice
args[1] = Java Core
~~~

Đối số đầu tiên có chỉ số 0. Dấu ngoặc kép giúp shell giữ cụm Java Core thành một đối số duy nhất. Mảng args chỉ chứa các đối số nằm sau tên main class, tên JAR, tên source file hoặc mục tiêu module.

### String... có tương đương String[] không?

Có. Khai báo sau cũng hợp lệ:

~~~java
public static void main(String... args) {
    System.out.println(args.length);
}
~~~

Trong Java, String... là cú pháp varargs và có cùng kiểu mảng String[] ở mức chữ ký phương thức. Không thể khai báo đồng thời hai phương thức main với String[] và String... trong cùng class vì chúng có cùng signature.

Phương thức main có thể khai báo throws, ví dụ public static void main(String[] args) throws Exception. Kiểu trả về vẫn phải là void.

## 3. Ví dụ đầy đủ: compile và chạy main class

Tạo file Main.java:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Java launcher started the application.");
        System.out.println("Argument count: " + args.length);

        for (int i = 0; i < args.length; i++) {
            System.out.printf("args[%d] = %s%n", i, args[i]);
        }
    }
}
~~~

Giả sử cấu trúc thư mục ban đầu là:

~~~text
project/
└── src/
    └── com/
        └── example/
            └── Main.java
~~~

Mở terminal tại thư mục project và biên dịch:

~~~bash
javac -d out src/com/example/Main.java
~~~

Tùy chọn -d out yêu cầu compiler đặt các file .class trong thư mục out và tạo cấu trúc thư mục package tương ứng.

Sau khi biên dịch, cấu trúc sẽ có dạng:

~~~text
project/
├── src/
│   └── com/
│       └── example/
│           └── Main.java
└── out/
    └── com/
        └── example/
            └── Main.class
~~~

Chạy main class:

~~~bash
java -cp out com.example.Main Alice "Java Core"
~~~

Kết quả chính xác:

~~~text
Java launcher started the application.
Argument count: 2
args[0] = Alice
args[1] = Java Core
~~~

Giải thích:

- java gọi Java launcher.
- -cp out đặt thư mục out vào classpath để JVM tìm class và các class phụ thuộc.
- com.example.Main là tên đầy đủ của class (fully qualified class name), gồm package và class name.
- Alice và Java Core là đối số dành cho main method.

### Tên class, tên file và package

Nếu một source file khai báo public top-level class tên Main thì tên file theo quy tắc Java phải là Main.java. Với package com.example, file thường nằm trong thư mục com/example bên dưới source root.

Khi chạy class đã biên dịch:

- Ghi tên đầy đủ của class, ví dụ com.example.Main.
- Không ghi đuôi .class.
- Không ghi đường dẫn file Main.class thay cho tên class.
- Classpath phải trỏ đến thư mục gốc nằm phía trên thư mục package.

Ví dụ, với out/com/example/Main.class, classpath là out và tên class là com.example.Main. Nếu đặt classpath thành out/com/example thì JVM sẽ tìm class ở sai cấp thư mục khi dùng tên đầy đủ com.example.Main.

## 4. Java launcher chọn và gọi main như thế nào?

Một lần khởi chạy thông thường có thể hiểu theo trình tự:

1. Launcher đọc các tùy chọn JVM và xác định mục tiêu cần chạy: class, JAR, module hoặc source file.
2. Launcher thiết lập classpath/module path và các thông tin môi trường cần thiết.
3. JVM nạp initial class hoặc interface được chỉ định.
4. JVM liên kết class: kiểm tra cấu trúc bytecode, chuẩn bị dữ liệu runtime và giải quyết các tham chiếu khi cần.
5. JVM khởi tạo class. Các static field initializer và static initializer của class được thực thi theo quy tắc khởi tạo Java.
6. JVM xác định một main method hợp lệ theo phiên bản Java và gọi phương thức đó.
7. Chương trình tiếp tục chạy, tạo object, gọi method và sử dụng các class khác theo logic của ứng dụng.

Vì class được khởi tạo trước khi main được gọi, static initializer có thể chạy trước dòng lệnh đầu tiên bên trong main. Nếu main là instance method, constructor của main class còn chạy trước phần thân main.

Ví dụ:

~~~java
public class StartupOrder {
    static {
        System.out.println("1. Static initializer");
    }

    public StartupOrder() {
        System.out.println("2. Constructor");
    }

    public static void main(String[] args) {
        System.out.println("3. main method");
    }
}
~~~

Kết quả:

~~~text
1. Static initializer
3. main method
~~~

Trong ví dụ này main là static nên launcher không tạo StartupOrder object. Constructor không chạy. Nếu dùng instance main method trên Java 25+, constructor sẽ được gọi trước main.

Lưu ý: thứ tự khởi tạo superclass và class, cũng như thời điểm nạp/liên kết các class phụ thuộc, tuân theo Java Language Specification và JVM Specification. Không nên giả định mọi class của ứng dụng đều được nạp hết trước khi main bắt đầu.

## 5. Các cách chỉ định main class khi chạy ứng dụng

Java launcher có nhiều chế độ chạy. Cần phân biệt mục tiêu được chỉ định với main method nằm bên trong mục tiêu đó.

### Chạy class đã biên dịch

~~~bash
java -cp out com.example.Main
~~~

Có thể dùng -classpath hoặc --class-path thay cho -cp:

~~~bash
java --class-path out com.example.Main
~~~

Nếu classpath chứa nhiều thư mục hoặc JAR, dấu phân cách phụ thuộc hệ điều hành:

~~~text
Windows:       out;lib/*;config
Linux/macOS:   out:lib/*:config
~~~

Đường dẫn có khoảng trắng nên được đặt trong dấu ngoặc kép theo quy tắc của shell đang sử dụng.

### Chạy source file trực tiếp

Từ JDK 11, Java launcher hỗ trợ source-file mode, cho phép chạy một chương trình từ file .java mà không cần gọi javac riêng:

~~~bash
java Hello.java
~~~

Launcher biên dịch source file trong quá trình khởi chạy rồi chạy class phù hợp. Chế độ này hữu ích cho ví dụ nhỏ, script và công cụ dòng lệnh đơn giản.

Có thể chỉ định phiên bản ngôn ngữ/API bằng tùy chọn --source, ví dụ:

~~~bash
java --source 17 Hello.java
~~~

Ví dụ --source 17 yêu cầu launcher thuộc JDK 17 trở lên. Khi chỉ định --source 17, source code được kiểm tra theo mức ngôn ngữ và API Java 17. Một file dùng tính năng chỉ có từ Java 25 sẽ không thể chạy bằng source level 17.

Source-file mode không thay thế đầy đủ một build system. Launcher không tự động tìm và biên dịch mọi source file trong dự án như một lệnh build tổng thể. Với ứng dụng nhiều module, nhiều dependency hoặc cần annotation processing, hãy dùng javac, Gradle hoặc Maven.

### Chạy main class trong JAR

Một JAR có thể khai báo main class mặc định trong manifest bằng thuộc tính Main-Class.

Ví dụ, nếu class đã biên dịch nằm trong out, tạo executable JAR bằng JDK 9 trở lên:

~~~bash
jar --create --file app.jar --main-class com.example.Main -C out .
~~~

Chạy:

~~~bash
java -jar app.jar Alice
~~~

Khi dùng -jar, launcher lấy main class từ thuộc tính Main-Class trong manifest. Với chế độ này, JAR được chỉ định là nguồn class người dùng; các thiết lập classpath khác trên command line bị bỏ qua. Nếu ứng dụng cần dependency bên ngoài, hãy đóng gói chúng theo chiến lược phù hợp, khai báo Class-Path trong manifest khi thích hợp, hoặc sử dụng một cơ chế triển khai khác.

Ví dụ manifest:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main
~~~

Tên class trong Main-Class phải là tên đầy đủ theo package và không có phần mở rộng .class.

### Chạy main class trong module

Với ứng dụng modular, có thể chỉ định module path và main class:

~~~bash
java --module-path mods -m com.example.app/com.example.Main
~~~

Trong đó:

- --module-path hoặc -p chỉ định nơi chứa các module.
- -m hoặc --module chọn module cần chạy.
- com.example.app là tên module.
- com.example.Main là main class trong module.

Nếu module đã khai báo main class mặc định trong module descriptor, có thể chạy module mà không cần ghi phần /com.example.Main. Khi muốn rõ ràng hoặc cần chọn một entry point khác, hãy ghi cả tên module và main class.

### java và javaw trên Windows

java khởi chạy ứng dụng Java gắn với console hiện tại. javaw cũng khởi chạy ứng dụng Java nhưng không mở cửa sổ console đi kèm. javaw thường phù hợp với ứng dụng desktop không cần console. Khi launch thất bại, javaw có thể hiển thị hộp thoại lỗi.

## 6. Thay đổi từ Java 25: instance main methods

Trước Java 25, entry point truyền thống phải có dạng public static void main(String[] args) hoặc public static void main(String... args). Java 25 chuẩn hóa tính năng **Compact Source Files and Instance Main Methods** qua JEP 512. Từ phiên bản này, launch protocol chấp nhận thêm các dạng main method đơn giản hơn.

Trong Java 25 trở lên, một candidate main method phải:

- Có tên main.
- Có kiểu trả về void.
- Có một tham số String[] (hoặc String...) hoặc không có tham số.
- Có mức truy cập public, protected hoặc package-private.
- Có thể là static hoặc instance method.

Private method không phải candidate main method theo quy tắc này. Dạng truyền thống public static void main(String[] args) vẫn hợp lệ và tiếp tục là lựa chọn tương thích rộng.

### Bốn dạng thường gặp từ Java 25

~~~java
public static void main(String[] args) {
    System.out.println("Static main with arguments");
}
~~~

~~~java
static void main() {
    System.out.println("Static main without arguments");
}
~~~

~~~java
void main(String[] args) {
    System.out.println("Instance main with arguments");
}
~~~

~~~java
void main() {
    System.out.println("Instance main without arguments");
}
~~~

Các ví dụ trên giả định được biên dịch và chạy bằng JDK 25 trở lên. Trên Java 8 đến Java 24, chỉ dạng static với một tham số String[]/String... là entry point chuẩn.

### Quy tắc chọn main method

Nếu class có nhiều candidate main method, launcher ưu tiên theo tham số:

1. Nếu có candidate main với một tham số String[], launcher chọn candidate đó.
2. Nếu không có candidate một tham số, launcher chọn candidate main không có tham số.
3. Nếu phương thức được chọn là static, launcher gọi trực tiếp.
4. Nếu phương thức được chọn là instance method, launcher tạo một instance của main class bằng constructor không có tham số rồi gọi method trên object đó.

Ví dụ:

~~~java
public class MainChoice {
    public static void main(String[] args) {
        System.out.println("main(String[] args)");
    }

    void main() {
        System.out.println("main()");
    }
}
~~~

Khi chạy trên JDK 25 trở lên, output là:

~~~text
main(String[] args)
~~~

Phương thức có tham số được ưu tiên. Việc class có thêm main() không khiến launcher gọi cả hai phương thức.

### Instance main cần constructor không tham số

Ví dụ sau có thể chạy trên JDK 25 trở lên:

~~~java
public class InstanceMain {
    private final String applicationName;

    public InstanceMain() {
        applicationName = "Java Core";
    }

    void main(String[] args) {
        System.out.println("Application: " + applicationName);
        System.out.println("Arguments: " + args.length);
    }
}
~~~

Chạy:

~~~bash
javac InstanceMain.java
java InstanceMain one two
~~~

Kết quả:

~~~text
Application: Java Core
Arguments: 2
~~~

Launcher tạo object InstanceMain bằng constructor không tham số, sau đó gọi instance main method. Nếu class không khai báo constructor nào, compiler tự tạo default constructor không tham số. Nếu class chỉ có constructor yêu cầu tham số, launcher không thể tạo instance theo quy trình này; hãy cung cấp constructor không tham số phù hợp hoặc dùng static main.

### Khi nào nên dùng static main?

Dạng public static void main(String[] args) có lợi thế tương thích với các JDK cũ, framework, IDE, build tool và tài liệu lâu đời. Nó cũng giúp người đọc nhận biết entry point ngay lập tức.

Instance main phù hợp với bài học, ví dụ nhỏ hoặc chương trình cần truy cập instance field/method mà không phải tự tạo object đầu tiên. Với ứng dụng cần chạy trên nhiều thế hệ JDK, hãy ưu tiên signature truyền thống trừ khi dự án đã xác định JDK tối thiểu là 25.

## 7. Compact source file trong Java 25+

Java 25 cho phép viết một chương trình nhỏ mà không cần bao quanh các method và field bằng một class declaration tường minh. Source file như vậy được gọi là **compact source file**.

Ví dụ file Hello.java:

~~~java
String greeting = "Hello from Java 25";

void main() {
    IO.println(greeting);
}
~~~

Chạy trực tiếp:

~~~bash
java Hello.java
~~~

Output:

~~~text
Hello from Java 25
~~~

Compiler ngầm khai báo một class top-level cho các thành viên được viết trực tiếp trong file. Class ngầm định này thuộc unnamed package, là final, có default constructor không tham số và không thể được tham chiếu bằng tên class trong source code. Instance main method có thể dùng field và method của chính class ngầm định.

Từ Java 25, lớp IO nằm trong package java.lang và cung cấp các hàm console đơn giản như IO.print, IO.println và IO.readln. Vì java.lang được import ngầm, không cần viết import cho IO. Các method static vẫn được gọi thông qua tên class IO, ví dụ IO.println(...).

Compact source file là một cách viết Java hợp lệ, không phải một ngôn ngữ script tách biệt. Khi chương trình lớn dần, có thể chuyển các field và method vào một class tường minh rồi tổ chức package, module và dependency như các dự án Java thông thường.

Lưu ý phiên bản: instance main methods và compact source files từng xuất hiện dưới dạng preview trong các JDK 21–24. Chúng trở thành tính năng chính thức từ Java 25 qua JEP 512. Khi đọc tài liệu hoặc chạy ví dụ cũ, hãy kiểm tra phiên bản JDK và trạng thái preview của đúng phiên bản đó.

## 8. Main class có thể được kế thừa không?

Có. Theo quy tắc Java, candidate main method có thể được khai báo trực tiếp hoặc được kế thừa từ superclass. Ví dụ:

~~~java
class BaseApplication {
    public static void main(String[] args) {
        System.out.println("Started from inherited main");
    }
}

public class ChildApplication extends BaseApplication {
}
~~~

Có thể chạy:

~~~bash
javac ChildApplication.java
java ChildApplication
~~~

Output:

~~~text
Started from inherited main
~~~

Trong ví dụ này, ChildApplication kế thừa static main method từ BaseApplication. Vì vậy, launcher vẫn tìm thấy entry point khi ChildApplication là class được chỉ định.

Dù hợp lệ, không nên dựa quá nhiều vào main method kế thừa trong ứng dụng thông thường vì người đọc có thể khó nhận ra điểm bắt đầu. Khai báo entry point trực tiếp ở main class thường rõ ràng hơn.

## 9. Phân biệt launcher options và application arguments

Các tùy chọn JVM phải nằm trước tên main class hoặc mục tiêu chạy. Các đối số của ứng dụng nằm sau mục tiêu đó.

Ví dụ:

~~~bash
java -Xms256m -Xmx1g -cp out com.example.Main --mode test
~~~

| Thành phần | Ý nghĩa |
|---|---|
| java | Java launcher |
| -Xms256m | Heap ban đầu của JVM |
| -Xmx1g | Giới hạn heap tối đa của JVM |
| -cp out | Classpath của ứng dụng |
| com.example.Main | Main class |
| --mode test | Hai đối số ứng dụng được truyền vào args |

Trong main method, args[0] là --mode và args[1] là test. Launcher không tự diễn giải --mode; ứng dụng phải tự phân tích và xác thực các đối số đó.

Không nhầm tùy chọn của launcher với tham số của ứng dụng. Ví dụ, đặt -Xmx1g sau tên class sẽ khiến nó trở thành đối số của chương trình, không còn là tùy chọn cấu hình heap của JVM.

## 10. Lỗi thường gặp khi khởi chạy main class

### Could not find or load main class

**Nguyên nhân thường gặp:**

- Tên class viết sai hoặc sai chữ hoa/chữ thường.
- Thiếu package trong tên đầy đủ.
- Classpath trỏ sai thư mục gốc.
- File .class chưa được biên dịch hoặc không nằm trong classpath.
- Đang chạy một JDK khác với môi trường đã dùng để biên dịch.

**Cách xử lý:** kiểm tra cấu trúc thư mục, tên package, vị trí class file và giá trị -cp. Ví dụ, nếu class file là out/com/example/Main.class thì chạy com.example.Main với classpath out.

### Main method not found hoặc no main method

**Nguyên nhân thường gặp:**

- Phương thức viết sai tên, sai kiểu trả về hoặc sai kiểu tham số.
- Dùng private main method.
- Dùng instance main method nhưng đang chạy trên JDK trước Java 25.
- Dùng instance main method nhưng main class không thể được tạo bằng constructor không tham số.
- Chọn nhầm class làm mục tiêu khởi chạy.

**Cách xử lý:** kiểm tra signature và phiên bản JDK. Nếu cần tương thích rộng, dùng public static void main(String[] args).

### Main-Class attribute required

Khi chạy java -jar app.jar, lỗi có thể xuất hiện nếu manifest không có thuộc tính Main-Class hoặc giá trị class không hợp lệ.

**Cách xử lý:** tạo lại manifest hoặc dùng tùy chọn --main-class khi tạo JAR. Kiểm tra chính tả, package và class đã được đóng gói vào JAR.

### NoClassDefFoundError hoặc ClassNotFoundException

Main class có thể tìm thấy nhưng một class phụ thuộc lại không có trong runtime classpath/module path. Đây là lỗi tìm dependency, không nhất thiết là lỗi main method.

**Cách xử lý:** kiểm tra dependency đã được đóng gói chưa, classpath có chứa đúng JAR chưa và module có khai báo dependency cần thiết không.

### UnsupportedClassVersionError

Class file được biên dịch bằng phiên bản Java mới hơn runtime hiện tại. Ví dụ compile bằng JDK 25 rồi chạy bằng JDK 17 có thể gây lỗi này.

**Cách xử lý:** nâng runtime lên phiên bản phù hợp hoặc biên dịch bằng --release theo Java version mục tiêu. Kiểm tra cả java và javac đang được shell tìm thấy.

### Chạy nhầm file source hoặc class

- java Main chạy class Main đã biên dịch.
- java Main.java chạy source-file mode.
- java -jar app.jar chạy main class được khai báo trong manifest.
- java -m module.name/package.Main chạy main class của module.

Đừng thêm .java khi muốn chạy class đã biên dịch, và đừng bỏ .java khi muốn launcher chạy source-file mode.

## 11. Checklist kiểm tra trước khi bàn giao ứng dụng

- [ ] Xác định đúng main class và tên đầy đủ theo package.
- [ ] Dùng entry point hợp lệ với JDK tối thiểu của dự án.
- [ ] Đảm bảo public class nằm trong file có tên phù hợp.
- [ ] Kiểm tra classpath hoặc module path chứa main class và dependency.
- [ ] Nếu chạy JAR, xác minh manifest có Main-Class đúng.
- [ ] Kiểm tra thứ tự tùy chọn JVM và đối số ứng dụng.
- [ ] Kiểm thử args với trường hợp không có đối số, có nhiều đối số và có khoảng trắng.
- [ ] Kiểm tra static initializer/constructor nếu chương trình có logic khởi tạo.
- [ ] Xác minh JDK trong terminal, IDE, Gradle/Maven, CI và container.
- [ ] Nếu dùng instance main hoặc compact source file, xác nhận runtime/compiler từ Java 25 trở lên.
- [ ] Chạy thử trên môi trường triển khai thực tế và kiểm tra dependency.

## 12. Ghi nhớ

Main class là class mà launcher chọn để bắt đầu một lần chạy. Main method là phương thức entry point trong class đó. Với các dự án cần tương thích rộng, public static void main(String[] args) vẫn là lựa chọn dễ nhận biết và phổ biến. Từ Java 25, launch protocol hỗ trợ thêm instance main methods và compact source files, giúp viết chương trình nhỏ gọn hơn.

Khi chạy chương trình, hãy luôn trả lời được ba câu hỏi: launcher đang được gọi từ JDK nào, class/JAR/module/source file nào được chọn, và main method nào sẽ được gọi.

## 13. Tài liệu tham khảo chính thức

- [Java Language Specification, Java SE 26 — Chapter 12: Execution](https://docs.oracle.com/javase/specs/jls/se26/html/jls-12.html) — quy trình khởi động JVM và quy tắc chọn/invoke main method.
- [Java - Your Application Launcher (dev.java)](https://dev.java/learn/jvm/tools/core/java/) — cú pháp lệnh java, class/JAR/module/source-file mode và cách truyền đối số.
- [Java SE 25 Language Updates — Compact Source Files and Instance main Methods](https://docs.oracle.com/en/java/javase/25/language/java-se-language-updates.pdf) — JEP 512, compact source file, java.lang.IO và instance main methods.
- [JEP 512: Compact Source Files and Instance Main Methods](https://openjdk.org/jeps/512) — mục tiêu và thiết kế của tính năng được chuẩn hóa trong JDK 25.

Khi một ví dụ phụ thuộc vào instance main method hoặc compact source file, hãy ghi rõ JDK 25+ để người học không nhầm với quy tắc entry point truyền thống của các JDK cũ.
