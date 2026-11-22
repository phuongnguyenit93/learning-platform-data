# Biên dịch, tạo đối tượng và chạy chương trình Java đầu tiên

Một chương trình Java dùng đối tượng thường đi qua chuỗi thao tác: **viết định nghĩa class → biên dịch mã nguồn → chạy class có phương thức `main` → dùng `new` để tạo object → gọi phương thức trên object → quan sát kết quả**. Bài học này hướng dẫn từng bước bằng Java 17+, từ một tệp `.java` đến chương trình console hoạt động được.

Sau bài học, bạn cần tự làm được những việc sau:

- Kiểm tra JDK và sử dụng chính xác hai lệnh `javac`, `java`.
- Tạo tệp Java có một `public class` và một class hỗ trợ; hiểu quan hệ tên tệp, tên class và sản phẩm biên dịch.
- Khai báo class có trường (field), constructor và phương thức (method), sau đó tạo nhiều object bằng `new`.
- Phân biệt class, object, biến tham chiếu và phương thức `static main`.
- Giải thích thứ tự các dòng chương trình được thực thi và dự đoán stdout.
- Phân biệt lỗi biên dịch với lỗi khi chạy, biết xử lý các lỗi phổ biến về tên tệp, constructor, classpath và truy cập thành viên.

## 1. Chuẩn bị môi trường: JDK và terminal

**JDK (Java Development Kit)** cung cấp công cụ biên dịch và chạy chương trình Java. Để tự xây dựng và chạy ví dụ, cài JDK **17 trở lên**; các ví dụ trong bài dùng cú pháp tương thích Java 17. Một IDE có thể hỗ trợ thao tác biên dịch, nhưng hiểu lệnh ở terminal giúp xác định lỗi thuộc mã nguồn hay cấu hình môi trường.

Mở PowerShell, Terminal hoặc command prompt, chạy:

~~~bash
java -version
javac -version
~~~

Ý nghĩa:

- `java -version` cho biết bản Java runtime đang được lệnh `java` sử dụng.
- `javac -version` cho biết phiên bản trình biên dịch `javac`.
- Nếu `java` hoạt động nhưng `javac` không có, thường cần kiểm tra lại cài đặt JDK và cấu hình `PATH`.
- Nếu hai lệnh trỏ đến phiên bản khác nhau, kiểm tra thứ tự thư mục trong `PATH` và cấu hình Java của IDE; không mặc định rằng IDE dùng cùng JDK với terminal.

Các kết quả phiên bản phụ thuộc máy nên không có một stdout cố định cho hai lệnh này.

### Mã nguồn, bytecode và JVM

Quy trình thông dụng:

~~~text
FirstObjectApp.java    (mã nguồn Java)
        |
        | javac -encoding UTF-8 FirstObjectApp.java
        v
FirstObjectApp.class   (bytecode của class chính)
Student.class          (bytecode của class hỗ trợ)
        |
        | java -cp . FirstObjectApp
        v
JVM nạp class, tìm main, chạy mã và in kết quả
~~~

`javac` kiểm tra cú pháp, kiểu dữ liệu và nhiều quy tắc ngôn ngữ trước khi tạo file `.class`. `java` khởi động runtime, nạp class cần thiết và thực thi chương trình. Hai bước có mục đích khác nhau: **biên dịch thành công chưa đảm bảo chương trình chạy không phát sinh exception**.

Ở bài đầu tiên, ta để mọi tệp trong **cùng một thư mục**, chưa khai báo `package` và chưa sử dụng công cụ build. Điều này giúp nhận diện cơ chế của class và object trước khi học cấu trúc dự án nhiều thư mục.

## 2. Viết chương trình đầu tiên trong một tệp

Tạo một thư mục thực hành tùy ý, chẳng hạn `java-first-object`. Bên trong thư mục đó, tạo **đúng tên tệp `FirstObjectApp.java`** và nhập toàn bộ nội dung sau:

~~~java
public class FirstObjectApp {
    public static void main(String[] args) {
        Student lan = new Student("Lan", 8);
        Student minh = new Student("Minh", 6);

        System.out.println(lan.describe());

        lan.study(2);

        System.out.println(lan.describe());
        System.out.println(minh.describe());
        System.out.println("Same object: " + (lan == minh));
    }
}

class Student {
    private final String name;
    private int completedLessons;

    Student(String name, int completedLessons) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Invalid name");
        }
        if (completedLessons < 0) {
            throw new IllegalArgumentException("Lesson count cannot be negative");
        }
        this.name = name;
        this.completedLessons = completedLessons;
    }

    void study(int additionalLessons) {
        if (additionalLessons <= 0) {
            throw new IllegalArgumentException("Additional lessons must be positive");
        }
        completedLessons = Math.addExact(completedLessons, additionalLessons);
    }

    String describe() {
        return name + ": " + completedLessons + " lessons";
    }
}
~~~

Hai class trong một tệp nguồn vẫn hợp lệ: `FirstObjectApp` là **public top-level class**, còn `Student` là **package-private top-level class** vì không viết access modifier. Java yêu cầu tên tệp trùng tên của public top-level class: `FirstObjectApp.java`. Class `Student` không cần nằm trong `Student.java` ở ví dụ một tệp này, mặc dù trong dự án thực tế việc tách mỗi class chính ra tệp riêng thường giúp quản lý tốt hơn.

**Không cần đặt `public` trước `class Student`:** một tệp nguồn không được khai báo hai public top-level class có tên khác nhau; nếu muốn cả hai class đều public, cần đưa chúng vào những tệp nguồn tương ứng.

### Biên dịch

Mở terminal tại thư mục đang chứa `FirstObjectApp.java`:

~~~bash
javac -encoding UTF-8 FirstObjectApp.java
~~~

Trong trường hợp mã hợp lệ, `javac` thường kết thúc **không in gì ra stdout**. Kiểm tra thư mục sẽ thấy những file được biên dịch:

~~~text
FirstObjectApp.java
FirstObjectApp.class
Student.class
~~~

Tên và vị trí `.class` trên là của ví dụ **không package**, với lệnh `javac` đã dùng. Các file `.class` là kết quả biên dịch; bạn vẫn cần giữ mã nguồn `.java` để chỉnh sửa chương trình.

`-encoding UTF-8` giúp trình biên dịch đọc mã nguồn theo UTF-8 một cách rõ ràng, có ích khi bài học và chuỗi hiển thị chứa tiếng Việt. Nếu dùng terminal trên Windows, nên lưu file ở UTF-8 thay vì encoding hệ thống cũ.

### Chạy

Sau khi biên dịch, chạy:

~~~bash
java -cp . FirstObjectApp
~~~

Đầu ra chính xác:

~~~text
Lan: 8 lessons
Lan: 10 lessons
Minh: 6 lessons
Same object: false
~~~

Lệnh `java` nhận **tên class đầy đủ**, không phải tên tệp `.class` hay `.java` trong chế độ chạy bytecode thông dụng ở đây. Tham số `-cp .` chỉ định **class path** là thư mục hiện tại, nơi Java tìm `FirstObjectApp.class` và `Student.class`. Dấu chấm ở đây có nghĩa “thư mục hiện tại”, không phải dấu kết thúc câu.

Nếu chạy lệnh từ thư mục khác, class path `.` cũng chuyển sang thư mục khác và có thể không tìm thấy class. Khi mới học, hãy biên dịch và chạy ngay trong thư mục chứa mã nguồn, hoặc truyền một class path chính xác.

## 3. Đọc chương trình theo thứ tự JVM thực thi

Điểm vào của chương trình console trong ví dụ là:

~~~java
public static void main(String[] args) {
    // Các lệnh được chạy từ đây
}
~~~

Đây là một phần của class `FirstObjectApp`. Ý nghĩa từng thành phần:

| Thành phần | Vai trò |
| --- | --- |
| `public` | Cho phép launcher truy cập phương thức điểm vào |
| `static` | Phương thức gắn với class; launcher không phải tự tạo `FirstObjectApp` |
| `void` | `main` không trả về giá trị cho mã Java gọi nó |
| `main` | Tên phương thức điểm vào quen thuộc trong Java |
| `String[] args` | Mảng chuỗi chứa tham số dòng lệnh; trong ví dụ chưa sử dụng |

Không nên nhầm **`main` là static** với việc mọi class hay mọi object đều là static. Method `main` chỉ là điểm vào để chương trình bắt đầu; bên trong nó vẫn dùng `new` để tạo những object khác.

Theo trình tự:

1. JVM chạy `main` của `FirstObjectApp`.
2. `new Student("Lan", 8)` tạo một object `Student` mới và chạy constructor với tên Lan, số bài đã hoàn thành bằng 8. Tham chiếu đến object này được gán cho biến `lan`.
3. `new Student("Minh", 6)` tạo **object thứ hai**, được gán cho biến tham chiếu `minh`. Hai object có các trường riêng.
4. `lan.describe()` trả về chuỗi `Lan: 8 lessons`; `System.out.println` in chuỗi này.
5. `lan.study(2)` cập nhật số bài đã hoàn thành của Lan từ 8 thành 10.
6. `lan.describe()` lần thứ hai phản ánh trạng thái mới. `minh.describe()` vẫn in `Minh: 6 lessons` vì object của Minh chưa bị cập nhật.
7. `lan == minh` so sánh **danh tính tham chiếu** của hai biến: chúng trỏ đến hai object khác nhau nên biểu thức nhận giá trị `false`.

### Class, object, tham chiếu: ba thứ cần tách bạch

Đọc dòng:

~~~java
Student lan = new Student("Lan", 8);
~~~

Cụ thể:

- `Student` bên trái là **kiểu tham chiếu** do class `Student` định nghĩa.
- `lan` là **biến tham chiếu** thuộc phương thức `main`.
- `new` yêu cầu tạo một đối tượng mới.
- `Student("Lan", 8)` gọi constructor tương ứng để khởi tạo object.
- Kết quả của biểu thức `new` là tham chiếu đến object được tạo; phép `=` gán tham chiếu đó vào `lan`.

Minh họa:

~~~text
main()
    lan  --------> Student object #1
                    name = "Lan"
                    completedLessons = 10

    minh --------> Student object #2
                    name = "Minh"
                    completedLessons = 6
~~~

Các mũi tên là **quan hệ tham chiếu**, không biểu diễn địa chỉ bộ nhớ JVM cụ thể. Đối tượng được tạo và tồn tại theo ngữ nghĩa chương trình; chỉ từ ví dụ này không thể khẳng định JVM luôn đặt các object ở địa chỉ cố định hoặc cấp phát trên vùng nhớ vật lý nào.

**Một biến không phải là chính object.** Có thể có nhiều biến trỏ đến cùng một object; ngược lại, mỗi lần `new Student(...)` trong ví dụ là một lần tạo instance riêng.

## 4. Định nghĩa `Student` gồm những phần nào?

Trong class:

~~~java
class Student {
    private final String name;
    private int completedLessons;

    Student(String name, int completedLessons) {
        // Khởi tạo trạng thái
    }

    void study(int additionalLessons) {
        // Hành vi cập nhật
    }

    String describe() {
        // Hành vi đọc trạng thái
    }
}
~~~

Đoạn trên là **khung minh họa**, không phải một tệp độc lập để chạy. Ví dụ đầy đủ ở mục 2 chứa toàn bộ thân phương thức cần thiết.

### Field lưu trạng thái của từng instance

`name` và `completedLessons` là **instance fields**. Mỗi `Student` được tạo có giá trị trường của riêng nó. `private` giới hạn việc truy cập trực tiếp từ bên ngoài class. Nhờ đó, mã bên ngoài không tự ý gán `completedLessons = -1` mà phải đi qua một hành vi được kiểm soát.

`final` ở `private final String name` giới hạn việc gán lại field này sau khi đã được khởi tạo. Không nên suy luận rằng mọi field hoặc cả object tự động bất biến chỉ vì một field `final`. Trong ví dụ, `completedLessons` vẫn thay đổi được thông qua `study`.

### Constructor xây dựng trạng thái ban đầu hợp lệ

Đoạn:

~~~java
Student(String name, int completedLessons) {
    if (name == null || name.isBlank()) {
        throw new IllegalArgumentException("Invalid name");
    }
    if (completedLessons < 0) {
        throw new IllegalArgumentException("Lesson count cannot be negative");
    }
    this.name = name;
    this.completedLessons = completedLessons;
}
~~~

Constructor có **tên giống class** và **không khai báo kiểu trả về**, kể cả `void`. Khi `new Student("Lan", 8)` được thực hiện, các tham số tên và số bài được dùng để thiết lập fields cho object.

`this.name` là field `name` của object đang được xây dựng; `name` phía bên phải là tham số constructor. Dùng `this` giúp phân biệt hai tên trùng nhau. Tương tự với `completedLessons`.

Constructor còn kiểm tra: tên phải khác null, không chỉ chứa khoảng trắng; số bài đã hoàn thành không âm. Nếu dữ liệu sai, constructor ném `IllegalArgumentException`. Điều này giúp object hoàn tất quá trình tạo trong trạng thái hợp lệ.

Khi class đã khai báo constructor có tham số, Java **không tự thêm** default constructor không tham số. Bởi vậy lệnh `new Student()` sẽ gây lỗi biên dịch trong phiên bản class đang học.

### Instance method cung cấp hành vi

`study` và `describe` là **instance methods**, phải gọi trên một tham chiếu object thích hợp như `lan.study(2)`:

~~~java
void study(int additionalLessons) {
    if (additionalLessons <= 0) {
        throw new IllegalArgumentException("Additional lessons must be positive");
    }
    completedLessons = Math.addExact(completedLessons, additionalLessons);
}
~~~

`study` yêu cầu lượng bài học mới lớn hơn 0 và tính tổng an toàn bằng `Math.addExact`. Nếu phép cộng `int` tràn số, `Math.addExact` ném `ArithmeticException`; field không bị gán kết quả tràn. Với bài học đầu tiên, mục tiêu chính là thấy method có thể kiểm tra tham số và cập nhật trạng thái của object.

~~~java
String describe() {
    return name + ": " + completedLessons + " lessons";
}
~~~

`describe` **trả về** `String`, không tự in ra terminal. Khi `main` gọi `System.out.println(lan.describe())`, `describe` tạo chuỗi, rồi `println` chịu trách nhiệm in chuỗi. Tách “tạo dữ liệu” và “in dữ liệu” giúp class dễ dùng lại và kiểm tra hơn.

## 5. Phân biệt phương thức static và phương thức instance

`main` là phương thức `static`, trong khi `study` và `describe` là phương thức instance.

| Tình huống | Cú pháp thường dùng | Ý nghĩa |
| --- | --- | --- |
| Gọi phương thức static | `FirstObjectApp.main(new String[0])` | Gọi method thuộc class; thường Java launcher tự gọi trong bài này |
| Tạo instance | `new Student("Lan", 8)` | Tạo Student object |
| Gọi instance method | `lan.study(2)` | Thực thi hành vi của Student được `lan` tham chiếu |
| Đọc kết quả instance method | `lan.describe()` | Lấy chuỗi mô tả trạng thái của cùng object |

Viết `Student.study(2)` là **sai** vì `study` không phải static; compiler không thể biết bạn muốn cập nhật instance nào. Cũng không thể truy cập `completedLessons` trực tiếp từ static `main` mà không có một tham chiếu và quyền truy cập hợp lệ.

Không bắt buộc phải biến mọi phương thức thành static để gọi được trong `main`; hãy tạo instance phù hợp và sử dụng qua biến tham chiếu.

## 6. Biến tham chiếu có thể dùng chung một object: kiểm chứng bằng chương trình thứ hai

Sau khi biết tạo hai object độc lập, bước tiếp theo là quan sát **hai biến cùng trỏ đến một object**. Tạo tệp riêng **`ReferenceDemo.java`**:

~~~java
public class ReferenceDemo {
    public static void main(String[] args) {
        Counter first = new Counter(1);
        Counter alias = first;
        Counter second = new Counter(1);

        alias.increment();

        System.out.println("first: " + first.value());
        System.out.println("second: " + second.value());
        System.out.println("first == alias: " + (first == alias));
        System.out.println("first == second: " + (first == second));
    }
}

class Counter {
    private int count;

    Counter(int count) {
        this.count = count;
    }

    void increment() {
        count++;
    }

    int value() {
        return count;
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ReferenceDemo.java
java -cp . ReferenceDemo
~~~

Stdout chính xác:

~~~text
first: 2
second: 1
first == alias: true
first == second: false
~~~

Phân tích:

- `first` tham chiếu đến Counter thứ nhất, ban đầu có `count = 1`.
- `alias = first` sao chép **giá trị tham chiếu**, không tạo Counter mới.
- `second = new Counter(1)` tạo Counter thứ hai có cùng giá trị ban đầu, nhưng là object khác.
- `alias.increment()` làm Counter thứ nhất tăng lên 2. Đọc qua `first.value()` cho kết quả 2 vì `first` và `alias` chỉ cùng object.
- `first == alias` là true, `first == second` là false. Với hai biến kiểu tham chiếu, `==` kiểm tra có trỏ cùng object không, **không** kiểm tra nội dung fields.

Đừng nhầm phép so sánh này với `String.equals` hoặc phương thức `equals` được class tự định nghĩa để so sánh giá trị. Bài này đang kiểm tra **cách tạo và trỏ đến object**, nên phép `==` là phù hợp cho phần minh họa danh tính.

## 7. Hai cách tổ chức mã nguồn khi bắt đầu

### Cách A: Một file có nhiều top-level class

Mẫu `FirstObjectApp.java` chứa `public class FirstObjectApp` và `class Student`. Đây là cách dễ chạy nhất khi học vì chỉ cần biên dịch một file. Compiler tạo file `.class` cho từng class cần thiết trong file đó.

Chỉ class `FirstObjectApp` có `main` của ví dụ; việc compiler tạo `Student.class` **không** khiến `Student` trở thành chương trình console độc lập. Nếu cố chạy `java -cp . Student`, launcher sẽ không tìm được phương thức `main` phù hợp và báo lỗi.

### Cách B: Tách thành hai tệp nguồn

Khi chương trình phát triển, có thể tách ra:

~~~text
java-first-object/
    FirstObjectApp.java
    Student.java
~~~

`FirstObjectApp.java` sẽ chỉ chứa `public class FirstObjectApp` với `main`; `Student.java` chỉ chứa định nghĩa `class Student`. Hai class có thể ở cùng default package như ví dụ ban đầu. Nội dung và logic giống mục 2, chỉ chuyển vị trí định nghĩa class sang tệp riêng.

Biên dịch minh bạch hai tệp:

~~~bash
javac -encoding UTF-8 Student.java FirstObjectApp.java
java -cp . FirstObjectApp
~~~

**Lưu ý:** Đây là **hướng dẫn tách mã đã có**, không phải hai đoạn source độc lập được liệt kê lại. Không giữ đồng thời một `class Student` trong cả `FirstObjectApp.java` và `Student.java` cùng package, vì như vậy có thể gây lỗi định nghĩa class trùng lặp.

Trong một project thật, class còn thường nằm trong package có tên; phần dưới giới thiệu bước chuyển tiếp ngắn để bạn không nhầm khi chạy từ terminal.

## 8. Khi bắt đầu dùng package: tên class đầy đủ và classpath

`package` nhóm class vào một không gian tên. Nếu file nguồn khai báo `package edu.demo;`, JVM cần dùng tên class đầy đủ `edu.demo.Main` khi khởi chạy. Đây là ví dụ nâng cao vừa đủ để bạn nhận diện khác biệt so với default package.

Tạo thư mục `src/edu/demo/`, rồi tạo file **`src/edu/demo/Main.java`**:

~~~java
package edu.demo;

public class Main {
    public static void main(String[] args) {
        Message message = new Message("Java");
        System.out.println(message.text());
    }
}

class Message {
    private final String subject;

    Message(String subject) {
        this.subject = subject;
    }

    String text() {
        return "Hello, " + subject + "!";
    }
}
~~~

Từ thư mục **gốc của ví dụ**, tạo thư mục output và chạy:

~~~bash
mkdir out
javac -encoding UTF-8 -d out src/edu/demo/Main.java
java -cp out edu.demo.Main
~~~

Stdout:

~~~text
Hello, Java!
~~~

`javac -d out` đặt các file bytecode vào cấu trúc package dưới `out`, chẳng hạn `out/edu/demo/Main.class` và `out/edu/demo/Message.class`. Lệnh `java -cp out edu.demo.Main` có hai phần quan trọng:

- `-cp out`: gốc classpath là thư mục `out`, **không** phải chính thư mục `out/edu/demo`.
- `edu.demo.Main`: tên đầy đủ (fully qualified class name) gồm package và class; không viết đường dẫn file hay đuôi `.class`.

Nếu bạn đã có thư mục `out`, không cần tạo lại. Các lệnh này độc lập với ví dụ `FirstObjectApp`; bạn có thể thử ở một thư mục khác để tránh trộn hai cấu trúc.

Tại giai đoạn làm quen, không cần học thuộc toàn bộ module path và cơ chế packaging chuyên sâu. Chỉ cần hiểu rằng **package quyết định tên đầy đủ của class** và **classpath quyết định nơi runtime tìm các file class**.

## 9. Đừng nhầm biên dịch trước với chế độ chạy thẳng tệp nguồn

Từ Java 11, công cụ `java` hỗ trợ chạy trực tiếp chương trình từ tệp mã nguồn trong những tình huống phù hợp, ví dụ:

~~~bash
java FirstObjectApp.java
~~~

Cách này thường được gọi là **source-file mode**: launcher xử lý mã nguồn để chạy chương trình, không yêu cầu bạn gõ riêng lệnh `javac` trước. Tuy nhiên, mục tiêu của bài này là làm rõ cả hai giai đoạn nên nên thực hành:

~~~bash
javac -encoding UTF-8 FirstObjectApp.java
java -cp . FirstObjectApp
~~~

Đừng coi `java FirstObjectApp.java` và `java -cp . FirstObjectApp` là cùng một cú pháp; chúng sử dụng hai chế độ khởi chạy khác nhau. Với các dự án có nhiều package, dependencies hoặc build tool, cách chạy sẽ còn phụ thuộc cấu hình dự án.

## 10. Các lỗi phổ biến khi tạo và chạy class đầu tiên

| Lỗi / triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `javac` không được nhận diện | JDK chưa cài đúng, hoặc `PATH` chưa trỏ tới `bin` của JDK | Kiểm tra `javac -version`, cài JDK và cấu hình PATH |
| `class FirstObjectApp is public, should be declared in a file named FirstObjectApp.java` | Tên file khác tên public top-level class | Đặt file là `FirstObjectApp.java`, đúng chữ hoa/chữ thường |
| `';' expected`, `'}' expected` | Thiếu dấu `;` hoặc dấu đóng ngoặc | Xem vị trí lỗi biên dịch và các dòng gần đó |
| `cannot find symbol` | Sai chính tả tên field/method/class, sai phạm vi, hoặc class chưa được tìm thấy khi biên dịch | Kiểm tra tên, khai báo, import/package và những file được compile |
| `constructor Student ... cannot be applied to given types` | Gọi constructor bằng số lượng hoặc kiểu tham số không khớp | Dùng `new Student("Lan", 8)` đúng chữ ký |
| `Student()` không biên dịch | Class chỉ khai báo constructor có tham số | Truyền đủ tham số hoặc định nghĩa thêm constructor phù hợp |
| `non-static method ... cannot be referenced from a static context` | Gọi instance method bằng tên class từ ngữ cảnh static | Tạo object và gọi `object.method()` |
| `... has private access in Student` | Đọc hoặc ghi field private ở class khác | Dùng public API hợp lệ; không tự sửa modifier chỉ để bỏ lỗi |
| `Could not find or load main class FirstObjectApp` | Đang chạy sai thư mục, sai classpath hoặc tên class | Kiểm tra `.class`, chạy `java -cp . FirstObjectApp` ở đúng thư mục |
| `Main method not found ...` | Class được chạy không có điểm vào `main` phù hợp | Chạy class có `main` thay vì class hỗ trợ như `Student` |
| `NullPointerException` | Gọi phương thức qua tham chiếu `null` | Kiểm tra object đã tạo chưa, validate giá trị trước khi dùng |
| Chương trình chạy nhưng kết quả không đổi sau cập nhật | Gọi method trên object khác, chưa gọi method hoặc đang đọc biến sai | Theo dõi các lần `new`, phép gán tham chiếu và method gọi |
| In giá trị sai vì `==` với `String` | So sánh hai tham chiếu thay vì nội dung chuỗi | Khi cần so sánh nội dung chuỗi, dùng `equals` |
| Sửa `.java` rồi chạy vẫn là kết quả cũ | Chưa biên dịch lại `.java`; đang chạy `.class` cũ | Biên dịch lại trước khi chạy |

### Cách phân loại lỗi để xử lý nhanh

**Lỗi biên dịch** xuất hiện khi `javac` không tạo được bytecode hợp lệ, ví dụ thiếu dấu ngoặc, truy cập thành viên không cho phép hoặc gọi sai constructor. Hãy sửa mã nguồn theo thông báo của compiler rồi chạy lại `javac`.

**Lỗi lúc chạy** xảy ra sau khi chương trình đã biên dịch, ví dụ `IllegalArgumentException` khi gọi `study(-1)`, `NullPointerException` hoặc cấu hình classpath sai. Hãy đọc tên exception, thông điệp và stack trace. Nếu một method kiểm tra đầu vào và chủ động ném exception, đó có thể là hành vi bảo vệ trạng thái, không nhất thiết là lỗi compiler.

**Lỗi logic** là chương trình biên dịch và chạy bình thường nhưng tính ra giá trị sai. Ví dụ, vô tình dùng `minh.study(2)` thay vì `lan.study(2)`. Compiler không thể biết ý định nghiệp vụ nên cần tự dự đoán và kiểm tra kết quả.

## 11. Bài thực hành sau khi chạy ví dụ

### Bài A — Tự dự đoán state

Giữ nguyên chương trình `FirstObjectApp`, thay lần gọi:

~~~java
lan.study(2);
~~~

thành:

~~~java
lan.study(5);
minh.study(1);
~~~

Trước khi chạy, hãy đoán ba dòng mô tả Student: lần in đầu vẫn là `Lan: 8 lessons`, lần in thứ hai là `Lan: 13 lessons`, dòng của Minh là `Minh: 7 lessons`. Biểu thức `lan == minh` vẫn là `false` vì cập nhật field không biến hai object thành một.

### Bài B — Thử quy tắc constructor

Thay `new Student("Lan", 8)` bằng `new Student("Lan", -1)`. Dự đoán điều xảy ra: trình biên dịch vẫn **chấp nhận cú pháp và kiểu dữ liệu**, nhưng khi chạy constructor ném `IllegalArgumentException` với thông điệp `Lesson count cannot be negative`. Chương trình không đi tới các dòng `println` sau lệnh tạo object thất bại, trừ khi có mã xử lý exception thích hợp.

### Bài C — Tạo alias và so sánh danh tính

Bổ sung vào `main` sau khi tạo `lan`:

~~~java
Student alias = lan;
System.out.println("Alias: " + (alias == lan));
alias.study(1);
~~~

Đây là **đoạn thêm vào chương trình đã có**, không phải tệp độc lập. Kết quả kiểm tra alias là `Alias: true`. Lời gọi `alias.study(1)` làm thay đổi chính object mà `lan` trỏ đến. Dự đoán lại những lần `lan.describe()` xuất hiện sau đó.

### Bài D — Tách class thành file riêng

Tách `Student` sang `Student.java` theo mục 7; xóa định nghĩa `Student` khỏi tệp `FirstObjectApp.java`. Biên dịch bằng hai file và chạy lại. Nếu stdout giữ nguyên, bạn đã chứng minh rằng cách tổ chức file nguồn có thể thay đổi mà hành vi của chương trình vẫn giữ nguyên.

### Bài E — Tạo chương trình của riêng bạn

Thiết kế class `Lamp` có trường `private boolean on`, constructor khởi tạo trạng thái tắt, phương thức `turnOn()` và `turnOff()`, phương thức `status()` trả về `"ON"` hoặc `"OFF"`. Viết `LampApp` có `main` tạo **hai đèn riêng**, bật một đèn rồi in trạng thái cả hai.

Yêu cầu tự kiểm tra:

1. Hai đèn mới đều ở trạng thái `OFF`.
2. Gọi `first.turnOn()` chỉ làm đèn `first` chuyển thành `ON`.
3. Gọi `first.turnOff()` đưa nó về `OFF`.
4. Nếu `Lamp alias = first` thì thao tác qua `alias` ảnh hưởng đến `first`.
5. Biên dịch và chạy được từ terminal, giải thích tên tệp nào chứa `main`.

## 12. Checklist hoàn thành

Bạn đã nắm yêu cầu của bài khi có thể tự trả lời và thao tác được tất cả các câu sau:

- [ ] Tôi có thể chạy `java -version` và `javac -version`, xác định JDK đang dùng.
- [ ] Tôi tự tạo `FirstObjectApp.java`, biên dịch và khởi chạy từ đúng thư mục.
- [ ] Tôi biết vì sao `javac` tạo hai file `.class` dù ví dụ chỉ có một file nguồn.
- [ ] Tôi biết vì sao lệnh chạy phải chỉ đến `FirstObjectApp` có `main`.
- [ ] Tôi đọc được cấu trúc class gồm instance field, constructor và instance method.
- [ ] Tôi chỉ được biểu thức nào tạo object (`new Student(...)`) và biến nào đang giữ tham chiếu (`lan`, `minh`).
- [ ] Tôi giải thích được vì sao `lan` và `minh` có state riêng.
- [ ] Tôi giải thích được vì sao `alias = first` không tạo thêm object.
- [ ] Tôi phân biệt `static main` với instance method `study`.
- [ ] Tôi biết dùng `this.field` khi tham số cùng tên field.
- [ ] Tôi biết lỗi biên dịch, lỗi chạy và lỗi logic khác nhau như thế nào.
- [ ] Tôi thay đổi mã nguồn, biên dịch lại và xác minh stdout bằng kết quả dự đoán.

Khi các thao tác trên đã quen, hãy tiếp tục tìm hiểu sâu hơn về khai báo class, constructor overload, khởi tạo field, mức truy cập, `this`, instance/static, state/behavior/identity và cách các đối tượng tương tác. Tất cả kiến thức đó sẽ dễ hiểu hơn khi bạn đã **tự tạo được object, gọi được phương thức và nhìn thấy sự thay đổi trạng thái trong một chương trình chạy thực tế**.
