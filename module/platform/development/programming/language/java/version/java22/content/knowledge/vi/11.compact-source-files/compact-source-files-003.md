# Các dạng phương thức main được hỗ trợ và quy tắc lựa chọn điểm vào

Từ JDK 25, Java hỗ trợ nhiều dạng phương thức `main` làm điểm bắt đầu chương trình. Phương thức này không bắt buộc phải là `public static void main(String[] args)`: nó có thể là phương thức instance, có thể không nhận tham số và có thể dùng phạm vi truy cập `protected` hoặc package-private. Quy tắc mới cũng áp dụng cho lớp thông thường, không chỉ compact source file.

JEP 512 — Compact Source Files and Instance Main Methods — là tính năng chính thức từ JDK 25. Tại thời điểm biên soạn, JDK 27 là feature release mới nhất và JDK 25 là LTS mới nhất. Vì vậy, các ví dụ dưới đây dùng cú pháp stable của JDK 25 trở lên; không cần bật preview. Các lần preview từ JDK 21 đến JDK 24 chỉ là lịch sử phát triển của tính năng.

## 1. Những dạng main được launcher chấp nhận

Một candidate `main` phải có kiểu trả về `void` và một trong hai danh sách tham số:

- Không có tham số.
- Một tham số kiểu `String[]`. Cách viết varargs `String...` tương đương vì cùng có kiểu mảng `String`.

Phương thức có thể là `static` hoặc instance. Phạm vi truy cập có thể là `public`, `protected` hoặc package-private (không ghi modifier). Phương thức `private` không phải candidate. Một mệnh đề `throws` có thể được khai báo như với phương thức Java thông thường.

| Dạng khai báo | Được chọn làm điểm vào? | Ghi chú |
| --- | --- | --- |
| `public static void main(String[] args)` | Có | Dạng truyền thống, vẫn được hỗ trợ. |
| `static void main(String... args)` | Có | Varargs tương đương `String[]`. |
| `protected static void main(String[] args)` | Có | Không bắt buộc `public` khi khởi chạy class theo launch protocol mới. |
| `void main(String[] args)` | Có | Instance main, package-private. |
| `protected void main()` | Có | Instance main không nhận tham số. |
| `static void main()` | Có | Static main không nhận tham số. |
| `private static void main(String[] args)` | Không | `private` không được launcher chọn. |
| `public int main(String[] args)` | Không | Kiểu trả về phải là `void`. |
| `public static void main(int code)` | Không | Tham số phải là `String[]` hoặc không có tham số. |
| `public static void main(String name, String[] args)` | Không | Không hỗ trợ hai tham số. |

Như vậy, có 12 tổ hợp cơ bản: ba mức truy cập (`public`, `protected`, package-private), hai dạng thành viên (`static`, instance) và hai dạng tham số (một `String[]` hoặc không tham số). `String...` là cách viết khác của `String[]`, không tạo thêm một chữ ký riêng.

## 2. Quy tắc lựa chọn main khi có nhiều candidate

Launcher ưu tiên phương thức nhận mảng `String` trước. Chỉ khi không có candidate `main(String[])` hoặc `main(String...)` mới xét `main()` không tham số. Việc phương thức là static hay instance không làm thay đổi thứ tự ưu tiên này.

Thứ tự lựa chọn:

1. Candidate `void main(String[] args)` hoặc `void main(String... args)` có phạm vi truy cập được chấp nhận.
2. Nếu không có dạng trên, chọn candidate `void main()` có phạm vi truy cập được chấp nhận.
3. Nếu không có candidate nào, quá trình khởi chạy thất bại.

Sau khi chọn phương thức, launcher mới quyết định cách gọi:

- Nếu phương thức là `static`, gọi trực tiếp trên class.
- Nếu phương thức là instance, tạo một đối tượng của class bằng constructor không tham số được phép truy cập, rồi gọi phương thức trên đối tượng đó.

Ví dụ sau có cả static main không tham số và instance main có tham số:

```java
class LaunchChoice {
    static void main() {
        System.out.println("static main()");
    }

    void main(String[] args) {
        System.out.println("instance main(String[])");
        System.out.println("Số đối số: " + args.length);
    }
}
```

Biên dịch và chạy bằng JDK 25 trở lên:

```bash
javac --release 25 LaunchChoice.java
java LaunchChoice one two
```

Kết quả:

```text
instance main(String[])
Số đối số: 2
```

Launcher chọn `main(String[])` dù đó là instance method và trong class cũng có `static main()`. Sau khi chọn, launcher tạo đối tượng `LaunchChoice` bằng constructor không tham số mặc định rồi truyền mảng đối số vào instance main.

Nếu đổi ví dụ để có `static main(String[])` và instance `main()`, phương thức static có tham số sẽ được chọn. Vì `String[]` được ưu tiên trước `main()` không tham số, không có quy tắc ưu tiên static trước instance.

## 3. Constructor cần có khi dùng instance main

Khi candidate được chọn là instance method, launcher phải tạo đối tượng của class khởi chạy. Do đó class cần một constructor không tham số mà launcher có thể sử dụng. Trên JDK 27, constructor này không được là `private`.

```java
class InstanceEntry {
    private final String message;

    InstanceEntry() {
        message = "Khởi tạo từ constructor";
    }

    void main() {
        System.out.println(message);
    }
}
```

Chạy class:

```bash
javac --release 25 InstanceEntry.java
java InstanceEntry
```

Launcher tạo `InstanceEntry` bằng constructor không tham số rồi gọi `main()`. Trường hợp constructor được khai báo `private` hoặc class chỉ có constructor nhận tham số sẽ không đáp ứng yêu cầu tạo instance của instance main trên JDK 27.

Nếu class chỉ có static main, launcher không cần tạo instance và không cần constructor không tham số để gọi điểm vào đó:

```java
class StaticEntry {
    private StaticEntry(int value) {
        // Constructor riêng phục vụ mục đích khác.
    }

    static void main(String[] args) {
        System.out.println("Ứng dụng bắt đầu");
    }
}
```

Ở ví dụ này, `main(String[])` là static nên launcher gọi trực tiếp. Constructor private có tham số không ảnh hưởng đến việc chọn static main.

## 4. String[] và String... là cùng một chữ ký

Java cho phép khai báo tham số mảng theo cú pháp varargs:

```java
class ArgumentEntry {
    static void main(String... args) {
        for (int i = 0; i < args.length; i++) {
            System.out.println(i + ": " + args[i]);
        }
    }
}
```

Khi khởi chạy:

```bash
javac --release 25 ArgumentEntry.java
java ArgumentEntry red blue
```

Launcher truyền một mảng `String` chứa `red` và `blue`. Trong chữ ký phương thức, `String...` và `String[]` có cùng kiểu tham số nên không thể khai báo cả hai thành hai overload riêng trong cùng class.

## 5. Đối số dòng lệnh được truyền như thế nào?

Nếu launcher chọn dạng có một tham số `String[]`, toàn bộ đối số sau tên class hoặc source file được truyền thành các phần tử của mảng:

```java
void main(String[] args) {
    System.out.println("Số đối số: " + args.length);
    for (String arg : args) {
        System.out.println(arg);
    }
}
```

Chạy:

```bash
java ArgumentDemo.java hello 22 "Java hiện đại"
```

Mảng `args` có ba phần tử. Nếu launcher chọn `main()` không tham số, phương thức không nhận mảng đối số; các giá trị dòng lệnh không được chuyển vào phương thức đó.

## 6. Quy tắc áp dụng cho lớp thông thường

Instance main không yêu cầu phải dùng compact source file. Một class thông thường vẫn có thể khai báo instance main và sử dụng field, constructor cùng các thành viên instance như bình thường.

```java
public class GreeterApp {
    private final String greeting = "Xin chào";

    public GreeterApp() {
        // Khởi tạo trạng thái của đối tượng.
    }

    void main(String[] args) {
        String name = args.length == 0 ? "Java" : args[0];
        System.out.println(greeting + ", " + name + "!");
    }
}
```

Chạy:

```bash
javac --release 25 GreeterApp.java
java GreeterApp Phuong
```

Kết quả:

```text
Xin chào, Phuong!
```

Ở đây `main` có package-private access và là instance method. Launcher vẫn có thể chọn nó, tạo `GreeterApp` bằng constructor không tham số rồi gọi phương thức. Cách này hữu ích khi chương trình cần khởi tạo trạng thái instance trước khi bắt đầu xử lý.

## 7. Các candidate main có thể được kế thừa

Candidate main có thể được khai báo trong class khởi chạy hoặc được kế thừa từ superclass hay superinterface. Ví dụ, một default method của interface là instance method; nếu class khởi chạy kế thừa method `main` phù hợp thì nó có thể trở thành candidate.

Điều này có nghĩa khi đọc một class để xác định điểm vào, cần xem cả thành viên được khai báo và thành viên kế thừa. Một method `main` `private` không được kế thừa và không phải candidate. Với các class có nhiều lớp cha/interface và nhiều overload `main`, nên kiểm tra chữ ký thực tế mà class khởi chạy nhìn thấy thay vì chỉ tìm chuỗi `main` trong file hiện tại.

## 8. Compact source file tạo ra class ngầm định

Compact source file cho phép khai báo field và method mà không bọc chúng trong `class` declaration. Compiler xem các thành viên đó là thành viên của một class top-level được khai báo ngầm định.

Ví dụ file `Hello.java`:

```java
String greeting = "Hello";

void main() {
    System.out.println(greeting + ", Java!");
}
```

Chạy trực tiếp bằng source-file mode:

```bash
java Hello.java
```

Hoặc biên dịch rồi chạy:

```bash
javac --release 25 Hello.java
java Hello
```

Compiler tạo một class ngầm định và đặt field `greeting`, method `main()` vào class đó. Vì `main()` là instance method, launcher tạo instance của class ngầm định bằng default constructor rồi gọi phương thức.

Class được khai báo ngầm định có các đặc điểm quan trọng:

- Là class top-level `final` trong unnamed package.
- Kế thừa `java.lang.Object` và không implements interface.
- Có default constructor không tham số; không thể khai báo constructor riêng trong compact source file.
- Chứa các field, method, member class và member interface được khai báo trong file.
- Không thể tham chiếu class ngầm định bằng tên trong source code; file được dùng như một chương trình độc lập hoặc điểm vào.
- Phải có ít nhất một candidate main hợp lệ.

Vì có default constructor không tham số, compact source file có thể dùng instance `main()` mà không cần tự khai báo constructor. Các method và field không ghi `static` là thành viên instance, nên có thể được truy cập trực tiếp từ instance main.

## 9. Compact source file và class thông thường khác nhau thế nào?

| Đặc điểm | Compact source file | Class thông thường |
| --- | --- | --- |
| Khai báo class | Compiler khai báo class ngầm định | Lập trình viên khai báo tường minh |
| Package | Class ngầm định thuộc unnamed package | Có thể thuộc package có tên hoặc unnamed package |
| Class modifier | Class ngầm định là `final` | Tùy thiết kế class |
| Constructor | Có default constructor không tham số; không khai báo constructor riêng trong file compact | Có thể khai báo constructor và overload theo nhu cầu |
| Field/method | Khai báo trực tiếp trong file và trở thành thành viên class ngầm định | Nằm trong phần thân class |
| Điểm vào | Phải có candidate main | Cần candidate main nếu class được dùng để khởi chạy |
| Mục đích | Script, ví dụ, chương trình nhỏ | Ứng dụng có cấu trúc, thư viện và hệ thống lớn |

Compact source file không phải một ngôn ngữ Java riêng. Khi chương trình phát triển, có thể chuyển các thành viên vào một class khai báo tường minh mà không phải thay đổi bản chất của các field và method đó.

## 10. Giới hạn khi đóng gói thành executable JAR

Launch protocol mới hỗ trợ các candidate main linh hoạt khi khởi chạy class theo tên class hoặc chương trình compact source file. Tuy nhiên, tài liệu lệnh `java` của JDK 27 vẫn quy định entry trong manifest của executable JAR theo dạng truyền thống:

```java
public static void main(String[] args)
```

Ví dụ manifest:

```text
Main-Class: com.example.App
```

Khi chạy:

```bash
java -jar app.jar
```

hãy bảo đảm class được chỉ định bởi `Main-Class` có `public static void main(String[] args)`. Nếu cần dùng instance main hoặc `main()` không tham số làm điểm vào của một class, hãy khởi chạy class theo tên class hoặc cấu hình một static main truyền thống làm adapter cho ứng dụng đóng gói JAR.

## 11. Những lỗi thường gặp

- **Dùng `private main`:** launcher không xem method private là candidate.
- **Quên `void`:** main trả về `int`, `String` hoặc kiểu khác không được chấp nhận.
- **Dùng sai danh sách tham số:** chỉ chấp nhận không tham số hoặc một tham số `String[]`/`String...`.
- **Cho rằng static luôn được ưu tiên:** launcher ưu tiên dạng có `String[]` trước; sau đó mới xét dạng không tham số. Static hay instance không quyết định thứ tự này.
- **Instance main nhưng thiếu constructor phù hợp:** class thông thường phải có constructor không tham số mà launcher có thể sử dụng; constructor private hoặc chỉ có constructor nhận tham số sẽ khiến việc khởi chạy instance main thất bại trên JDK 27.
- **Khai báo cả `String[]` và `String...` như hai overload:** hai dạng này có cùng chữ ký nên không thể tồn tại như hai method riêng trong cùng class.
- **Cho rằng compact source file có thể khai báo constructor:** class ngầm định đã có default constructor và compact source file không cho phép khai báo constructor riêng.
- **Dùng instance main cho manifest `Main-Class` của JAR:** theo tài liệu JDK 27, executable JAR vẫn yêu cầu dạng `public static void main(String[] args)`.

## 12. Lịch sử preview và trạng thái hiện hành

Compact source files và instance main methods trải qua nhiều vòng preview trước khi được hoàn thiện:

| JDK | Đề xuất | Trạng thái |
| --- | --- | --- |
| 21 | JEP 445 — Unnamed Classes and Instance Main Methods | Preview lần đầu |
| 22 | JEP 463 — Implicitly Declared Classes and Instance Main Methods | Preview lần hai |
| 23 | JEP 477 — Implicitly Declared Classes and Instance Main Methods | Preview lần ba |
| 24 | JEP 495 — Simple Source Files and Instance Main Methods | Preview lần bốn |
| 25 | JEP 512 — Compact Source Files and Instance Main Methods | Chính thức (final) |
| 27 | JEP 512 | Vẫn là tính năng chính thức, không cần preview |

Khi biên dịch chương trình dùng tính năng này trên JDK 25 trở lên, không thêm `--enable-preview`. Ví dụ:

```bash
javac --release 25 Hello.java
java Hello
```

Hoặc với JDK 27, có thể biên dịch theo release 27:

```bash
javac --release 27 Hello.java
java Hello
```

Không dùng tên preview cũ như “Unnamed Classes” hoặc “Implicitly Declared Classes” để mô tả trạng thái hiện hành. Tên chính thức từ JDK 25 là Compact Source Files and Instance Main Methods.

## 13. Tài liệu tham khảo

- [JEP 512: Compact Source Files and Instance Main Methods](https://openjdk.org/jeps/512) — tính năng chính thức từ JDK 25.
- [JDK 27 — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html) — xác nhận JEP 512 là tính năng permanent từ JDK 25 và không phải preview của JDK 27.
- [Java Language Specification, JDK 27 — 12.1.4 Invoke a main Method](https://download.java.net/java/early_access/jdk27/docs/specs/jls/jls-12.html) — định nghĩa candidate main và thứ tự lựa chọn phương thức.
- [Java Language Specification, JDK 27 — 8.1.8 Implicitly Declared Classes](https://download.java.net/java/early_access/jdk27/docs/specs/jls/jls-8.html) — quy tắc về class được khai báo ngầm định trong compact source file.
- [JDK 27 — The `java` Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html) — cách khởi chạy class, source file và yêu cầu entry point của executable JAR.
