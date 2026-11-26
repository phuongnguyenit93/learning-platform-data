# Viết chương trình nhỏ với instance main và giảm phần khai báo lặp lại

Từ Java 25, có thể viết một chương trình Java nhỏ mà không cần khai báo tường minh @@BT@@class@@BT@@, không cần viết @@BT@@public static void main(String[] args)@@BT@@ và cũng không phải khai báo @@BT@@static@@BT@@ cho mọi phương thức trợ giúp. Hai khả năng kết hợp với nhau là *compact source file* (tệp nguồn gọn) và *instance main method* (phương thức @@BT@@main@@BT@@ dạng instance).

Đây là tính năng ngôn ngữ chính thức theo JEP 512, được hoàn thiện trong JDK 25. JDK 27 tiếp tục hỗ trợ cú pháp này như tính năng stable; không cần @@BT@@--enable-preview@@BT@@. Bài dùng trạng thái API hiện hành của JDK 27 và tương thích với JDK 25 LTS.

Tại thời điểm biên soạn (25/11/2026), JDK 27 đã phát hành GA ngày 15/09/2026 và JDK 25 là bản LTS mới nhất. Các ví dụ trong bài dùng cú pháp final của Java 25 và có thể biên dịch, chạy trên JDK 27.

## 1. Từ chương trình Java truyền thống đến tệp nguồn gọn

Một chương trình Hello World truyền thống thường cần khai báo class và phương thức main:

@@BT@@@@BT@@@@BT@@java
public class HelloWorld {
    public static void main(String[] args) {
        System.out.println("Hello, Java!");
    }
}
@@BT@@@@BT@@@@BT@@

Với chương trình chỉ có một vài dòng, phần khai báo class, @@BT@@public@@BT@@, @@BT@@static@@BT@@ và @@BT@@String[] args@@BT@@ có thể làm người mới học phải tiếp cận nhiều khái niệm trước khi viết được logic đầu tiên.

Compact source file cho phép viết trực tiếp các field và method ở cấp cao nhất của tệp:

@@BT@@@@BT@@@@BT@@java
void main() {
    IO.println("Hello, Java!");
}
@@BT@@@@BT@@@@BT@@

Tệp này có thể được lưu thành @@BT@@HelloWorld.java@@BT@@ và chạy bằng:

@@BT@@@@BT@@@@BT@@bash
java HelloWorld.java
@@BT@@@@BT@@@@BT@@

Lệnh @@BT@@java@@BT@@ ở chế độ source-file tự biên dịch rồi chạy chương trình. Không cần tạo class bằng tay hoặc chạy @@BT@@javac@@BT@@ trước.

## 2. Compact source file thực chất là gì?

Dù không viết @@BT@@class@@BT@@, Java vẫn tạo một class cho chương trình. Khi compiler gặp field hoặc method không nằm trong khai báo class tường minh, nó đặt các thành viên đó vào một *implicitly declared class* (class được khai báo ngầm).

Class được khai báo ngầm có các đặc điểm quan trọng:

- Là class top-level @@BT@@final@@BT@@ trong unnamed package.
- Kế thừa @@BT@@java.lang.Object@@BT@@ và không triển khai interface nào.
- Có constructor mặc định không tham số; không thể khai báo thêm constructor khác trong compact source file.
- Các field, method và class được viết ở cấp cao nhất trở thành thành viên của class này.
- Phải có một phương thức @@BT@@main@@BT@@ mà Java launcher có thể gọi.

Class ngầm định không thể được tham chiếu bằng tên trong mã nguồn. Vì vậy, compact source file phù hợp với chương trình độc lập hoặc entry point nhỏ; nó không phải cách khai báo một class để những package khác import và sử dụng như một API thông thường.

## 3. Instance main method

Instance main là phương thức @@BT@@main@@BT@@ không có từ khóa @@BT@@static@@BT@@. Với compact source file, có thể viết:

@@BT@@@@BT@@@@BT@@java
void main() {
    IO.println("Hello from an instance main method");
}
@@BT@@@@BT@@@@BT@@

Khi Java launcher chọn một instance main, launcher tạo instance của class được khai báo ngầm bằng constructor mặc định rồi gọi phương thức trên instance đó.

Phương thức main được chọn phải có kiểu trả về @@BT@@void@@BT@@ và thỏa một trong hai dạng:

- @@BT@@main(String[] args)@@BT@@: nhận tham số dòng lệnh.
- @@BT@@main()@@BT@@: không nhận tham số.

Phương thức có thể là @@BT@@static@@BT@@ hoặc instance method. Nó không bắt buộc phải khai báo @@BT@@public@@BT@@; ví dụ @@BT@@void main()@@BT@@ ở trên là hợp lệ.

Nếu có cả hai phương thức main đủ điều kiện và đều accessible, launcher ưu tiên phương thức nhận @@BT@@String[]@@BT@@. Nếu không có main phù hợp, chương trình không thể được khởi chạy theo giao thức này.

Ví dụ nhận đối số từ dòng lệnh:

@@BT@@@@BT@@@@BT@@java
void main(String[] args) {
    if (args.length == 0) {
        IO.println("No name was provided");
        return;
    }

    IO.println("Hello, " + args[0]);
}
@@BT@@@@BT@@@@BT@@

Chạy chương trình:

@@BT@@@@BT@@@@BT@@bash
java HelloWorld.java Linh
@@BT@@@@BT@@@@BT@@

Kết quả:

@@BT@@@@BT@@@@BT@@text
Hello, Linh
@@BT@@@@BT@@@@BT@@

## 4. Dùng field và method instance mà không cần khai báo static

Một lợi ích lớn của instance main là các field và method ở cấp cao nhất mặc định là thành viên instance. Phương thức main có thể gọi trực tiếp các method trợ giúp và đọc field mà không phải khai báo tất cả chúng là @@BT@@static@@BT@@.

Ví dụ:

@@BT@@@@BT@@@@BT@@java
String applicationName = "Task Tracker";
int completedTasks = 3;

String statusMessage() {
    return applicationName + ": " + completedTasks + " tasks completed";
}

void main() {
    IO.println(statusMessage());
}
@@BT@@@@BT@@@@BT@@

Ở đây:

- @@BT@@applicationName@@BT@@ và @@BT@@completedTasks@@BT@@ là field của class ngầm định.
- @@BT@@statusMessage()@@BT@@ là instance method.
- @@BT@@main()@@BT@@ gọi trực tiếp @@BT@@statusMessage()@@BT@@ trên cùng instance.

Cách viết này giúp một chương trình nhỏ dùng chung state và method theo mô hình hướng đối tượng quen thuộc. Khi chương trình lớn dần, có thể chuyển những phần logic phù hợp sang các class có tên rõ ràng.

## 5. Nhập dữ liệu và xuất kết quả với java.lang.IO

JDK 25 bổ sung class @@BT@@java.lang.IO@@BT@@ để hỗ trợ nhập xuất console theo dòng. Một số phương thức thường dùng:

| Phương thức | Công dụng |
|---|---|
| @@BT@@IO.print(value)@@BT@@ | Ghi nội dung ra standard output |
| @@BT@@IO.println(value)@@BT@@ | Ghi nội dung và xuống dòng |
| @@BT@@IO.readln()@@BT@@ | Đọc một dòng từ standard input |
| @@BT@@IO.readln(prompt)@@BT@@ | Hiển thị lời nhắc rồi đọc một dòng |

@@BT@@IO@@BT@@ thuộc package @@BT@@java.lang@@BT@@, vì vậy tên class được tự động khả dụng mà không cần import. Tuy nhiên, các phương thức của @@BT@@IO@@BT@@ là static và không được tự động static import trong compact source file. Hãy gọi bằng tên class, ví dụ @@BT@@IO.println(...)@@BT@@.

Ví dụ chương trình hỏi tên người dùng:

@@BT@@@@BT@@@@BT@@java
void main() {
    String name = IO.readln("Your name: ");

    if (name == null) {
        IO.println("No input was received.");
        return;
    }

    IO.println("Welcome, " + name + "!");
}
@@BT@@@@BT@@@@BT@@

@@BT@@readln@@BT@@ trả về @@BT@@null@@BT@@ nếu đã đến cuối luồng đầu vào mà không đọc được ký tự nào. Các phương thức đọc của @@BT@@IO@@BT@@ có thể ném @@BT@@IOError@@BT@@ nếu xảy ra lỗi I/O.

@@BT@@IO@@BT@@ được thiết kế cho I/O console đơn giản theo dòng. Sau lần gọi @@BT@@IO.readln@@BT@@ đầu tiên, không nên trộn cách đọc này với @@BT@@Scanner@@BT@@ hoặc một reader khác cùng đọc @@BT@@System.in@@BT@@, vì bộ giải mã có thể đã đọc đệm thêm dữ liệu.

@@BT@@System.out.println@@BT@@ vẫn là API hợp lệ. @@BT@@IO@@BT@@ chỉ là cách viết ngắn gọn cho những chương trình console nhỏ; không bắt buộc phải thay toàn bộ code I/O hiện có.

## 6. Tự động import các kiểu thuộc java.base

Compact source file tự động import theo nhu cầu tất cả public top-level class và interface thuộc các package được module @@BT@@java.base@@BT@@ export. Quy tắc này tương đương việc có khai báo @@BT@@import module java.base;@@BT@@ ở đầu compact source file.

Vì vậy, có thể dùng các kiểu phổ biến như @@BT@@List@@BT@@, @@BT@@Map@@BT@@, @@BT@@Stream@@BT@@ hoặc @@BT@@Collectors@@BT@@ mà không cần viết import riêng.

Ví dụ:

@@BT@@@@BT@@@@BT@@java
void main() {
    List<String> languages = List.of("Java", "Kotlin", "Scala");

    Map<Integer, List<String>> groupedByLength =
        languages.stream()
            .collect(Collectors.groupingBy(String::length));

    groupedByLength.forEach((length, names) ->
        IO.println(length + ": " + names)
    );
}
@@BT@@@@BT@@@@BT@@

Không phải mọi package trong JDK đều thuộc @@BT@@java.base@@BT@@. Nếu dùng kiểu thuộc module khác, chẳng hạn @@BT@@java.sql@@BT@@, vẫn cần khai báo import phù hợp và bảo đảm module đó có mặt trong môi trường chạy.

Quy tắc tự động import này chỉ áp dụng cho compact source file. Với một class Java được khai báo tường minh, hãy tiếp tục viết import theo quy tắc thông thường.

## 7. Chạy trực tiếp hoặc biên dịch trước

Có hai cách chạy compact source file phổ biến.

**Chạy trực tiếp ở source-file mode:**

@@BT@@@@BT@@@@BT@@bash
java HelloWorld.java
@@BT@@@@BT@@@@BT@@

Java launcher biên dịch tệp nguồn rồi chạy chương trình. Đây là cách nhanh để thử một ý tưởng, làm bài tập hoặc viết tiện ích nhỏ.

**Biên dịch thành class file rồi chạy:**

@@BT@@@@BT@@@@BT@@bash
javac HelloWorld.java
java HelloWorld
@@BT@@@@BT@@@@BT@@

Nếu dùng JDK 27 để biên dịch nhưng muốn giới hạn ngôn ngữ và API ở Java 25, có thể dùng:

@@BT@@@@BT@@@@BT@@bash
javac --release 25 HelloWorld.java
java HelloWorld
@@BT@@@@BT@@@@BT@@

Runtime để chạy class file phải hỗ trợ phiên bản bytecode được tạo. Với class file nhắm Java 25, có thể chạy bằng JDK 25 hoặc mới hơn.

Compact source file vẫn là mã Java chuẩn và được biên dịch thành class file. Khác biệt nằm ở cách khai báo class ngầm định và giao thức tìm phương thức main, không phải một ngôn ngữ riêng.

## 8. Giới hạn của compact source file

Compact source file giúp giảm phần khai báo ban đầu, nhưng không thay thế class thông thường trong mọi tình huống.

| Giới hạn | Ý nghĩa |
|---|---|
| Class nằm trong unnamed package | Không thể khai báo package có tên cho class ngầm định; class trong named package không thể tham chiếu class này bằng tên |
| Không thể tham chiếu class ngầm định | Không thể gọi constructor hoặc dùng tên class ngầm định trong source code |
| Chỉ có constructor mặc định không tham số | Không thể khai báo constructor riêng trong compact source file |
| Phải có launchable main | Tệp phải có main method mà Java launcher có thể gọi |
| Không phải API tái sử dụng | Phù hợp với chương trình độc lập hoặc entry point, không phù hợp làm class public cho module khác |
| Hạn chế với Javadoc | @@BT@@javadoc@@BT@@ không thể tạo API documentation cho chính class ngầm định vì class này không được truy cập từ class khác |

Khi cần package rõ ràng, constructor có tham số, nhiều class phối hợp, access control hoặc API dùng lại giữa các module, hãy chuyển sang class được khai báo tường minh.

## 9. Mở rộng thành class tường minh và Flexible Constructor Bodies

Compact source file giúp bắt đầu với ít cú pháp. Khi chương trình cần một class có tên, có thể chuyển các field và method vào trong khai báo @@BT@@class@@BT@@:

@@BT@@@@BT@@@@BT@@java
public class TaskTracker {
    private String applicationName = "Task Tracker";
    private int completedTasks = 3;

    private String statusMessage() {
        return applicationName + ": " + completedTasks + " tasks completed";
    }

    public static void main(String[] args) {
        TaskTracker tracker = new TaskTracker();
        System.out.println(tracker.statusMessage());
    }
}
@@BT@@@@BT@@@@BT@@

Từ Java 25, JEP 513 cũng hoàn thiện *Flexible Constructor Bodies*. Đây là một thay đổi ngôn ngữ riêng, hữu ích khi class tường minh cần kiểm tra dữ liệu hoặc tính toán đối số trước khi gọi constructor của superclass.

Ví dụ, có thể kiểm tra tham số trước khi gọi @@BT@@super(...)@@BT@@:

@@BT@@@@BT@@@@BT@@java
import java.math.BigInteger;

public class PositiveBigInteger extends BigInteger {

    public PositiveBigInteger(long value) {
        if (value <= 0) {
            throw new IllegalArgumentException("value must be positive");
        }

        super(Long.toString(value));
    }
}
@@BT@@@@BT@@@@BT@@

Trước JEP 513, lời gọi @@BT@@super(...)@@BT@@ hoặc @@BT@@this(...)@@BT@@ phải đứng trước các statement thông thường trong constructor. Từ Java 25, phần prologue trước lời gọi constructor tường minh có thể chứa các statement để xác thực dữ liệu, tính đối số hoặc gán field của instance đang tạo.

Giới hạn vẫn rất quan trọng: trong *early construction context*, không được đọc instance đang tạo, gọi instance method hoặc truy cập thành viên của @@BT@@super@@BT@@. Chỉ sau lời gọi @@BT@@super(...)@@BT@@ hoặc @@BT@@this(...)@@BT@@ mới có thể dùng @@BT@@this@@BT@@ theo cách thông thường.

Một compact source file không thể khai báo constructor riêng, nên Flexible Constructor Bodies chỉ áp dụng khi bạn đã chuyển sang class hoặc record có constructor tường minh. Hai tính năng bổ trợ cho quá trình phát triển chương trình: bắt đầu với cú pháp gọn, rồi bổ sung cấu trúc class và constructor khi cần.

## 10. Trạng thái phiên bản và preview trên JDK hiện hành

Tính năng compact source file và instance main đã trải qua nhiều vòng preview trước khi ổn định:

| Phiên bản | Trạng thái |
|---|---|
| Java 21 | JEP 445 — Unnamed Classes and Instance Main Methods (preview lần đầu) |
| Java 22 | JEP 463 — Implicitly Declared Classes and Instance Main Methods (preview lần hai) |
| Java 23 | JEP 477 — Implicitly Declared Classes and Instance Main Methods (preview lần ba) |
| Java 24 | JEP 495 — Simple Source Files and Instance Main Methods (preview lần bốn) |
| Java 25 | JEP 512 — Compact Source Files and Instance Main Methods (final) |
| Java 27 | Tính năng final, không cần preview flag |

Flexible Constructor Bodies cũng được hoàn thiện trong Java 25 theo JEP 513. Các tên JEP 447, JEP 482 và JEP 492 lần lượt mô tả các giai đoạn preview trước đó.

JDK 27 vẫn có một số preview khác không liên quan đến bài này. Ví dụ, Primitive Types in Patterns, @@BT@@instanceof@@BT@@ and @@BT@@switch@@BT@@ đang ở lần preview thứ năm theo JEP 532. Nếu thử tính năng preview đó bằng JDK 27, phải bật preview khi biên dịch và chạy:

@@BT@@@@BT@@@@BT@@bash
javac --enable-preview --release 27 Example.java
java --enable-preview Example
@@BT@@@@BT@@@@BT@@

Các lệnh này chỉ dành cho code thực sự sử dụng preview feature của JDK 27. Compact source files, instance main methods và Flexible Constructor Bodies trong bài này đều là tính năng final từ Java 25, nên không dùng @@BT@@--enable-preview@@BT@@.

## Kết luận

Compact source file cho phép viết field và method trực tiếp trong tệp nguồn, còn instance main method cho phép Java launcher gọi @@BT@@void main()@@BT@@ mà không cần @@BT@@static@@BT@@ hoặc tham số @@BT@@String[]@@BT@@. Kết hợp với @@BT@@java.lang.IO@@BT@@ và tự động import các kiểu thuộc @@BT@@java.base@@BT@@, cú pháp này giúp viết chương trình nhỏ ngắn gọn hơn.

Tính năng đã stable từ Java 25 và chạy trên JDK 27 mà không cần preview flag. Khi chương trình phát triển thành ứng dụng có nhiều class, package hoặc constructor riêng, hãy chuyển sang cấu trúc class tường minh; Flexible Constructor Bodies từ Java 25 giúp việc xác thực và chuẩn bị đối số trước lời gọi superclass constructor rõ ràng hơn.

## Tài liệu tham khảo

- [JEP 512: Compact Source Files and Instance Main Methods](https://openjdk.org/jeps/512)
- [JEP 513: Flexible Constructor Bodies](https://openjdk.org/jeps/513)
- [Oracle JDK 27 Release Notes — GA 15 September 2026](https://www.oracle.com/java/technologies/javase/27all-relnotes.html)
- [Oracle Java Downloads — JDK 25 LTS and JDK 27](https://www.oracle.com/java/technologies/downloads/)
- [Oracle Java 27 — Compact Source Files and Instance main Methods](https://docs.oracle.com/en/java/javase/27/language/compact-source-files-instance-main-methods.html)
- [Oracle Java 27 — Flexible Constructor Bodies](https://docs.oracle.com/en/java/javase/27/language/flexible-constructor-bodies.html)
- [Java SE 27 API — java.lang.IO](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/IO.html)
- [Oracle Java 27 — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html)
- [Oracle Java 27 — Preview Features](https://docs.oracle.com/en/java/javase/27/language/preview-language-vm-features.html)
