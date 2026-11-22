# Triển khai bằng local class và anonymous class

Trong Java, **local class (lớp cục bộ)** và **anonymous class (lớp ẩn danh)** cho phép đặt một phần triển khai ngay gần nơi nó được dùng. Chúng thường hữu ích khi một phương thức cần một cách triển khai riêng cho interface hoặc abstract class, nhưng kiểu triển khai đó không cần trở thành một lớp cấp cao nhất hay một lớp thành viên của lớp khác.

- **Local class** có tên và được khai báo bên trong một khối lệnh, chẳng hạn trong phương thức, constructor hoặc initializer. Tên lớp chỉ có hiệu lực trong phạm vi khối đó.
- **Anonymous class** không có tên lớp do lập trình viên đặt. Nó được khai báo ngay trong biểu thức tạo đối tượng bằng cú pháp `new KiểuCha(...) { ... }`.

Cả hai có thể chứa trường, phương thức và logic riêng. Điểm khác biệt chính nằm ở cách khai báo, phạm vi tên lớp và việc có thể khai báo constructor riêng hay không.

## 1. Local class là gì?

Local class là một lớp được khai báo bên trong một khối lệnh. Ví dụ thường gặp nhất là khai báo lớp bên trong một phương thức:

~~~java
void process() {
    class LocalWorker {
        void work() {
            System.out.println("Đang xử lý");
        }
    }

    LocalWorker worker = new LocalWorker();
    worker.work();
}
~~~

Lớp `LocalWorker` chỉ có thể được tham chiếu bằng tên trong phạm vi khai báo của nó. Mã bên ngoài phương thức `process()` không thể viết `new LocalWorker()`, vì tên này không tồn tại ngoài khối đó.

Local class có thể:

- Triển khai một hoặc nhiều interface.
- Kế thừa một lớp cha, kể cả abstract class.
- Khai báo trường, phương thức và constructor của chính nó.
- Được tạo thành nhiều đối tượng nếu cần trong phạm vi khai báo.
- Truy cập thành viên của đối tượng bên ngoài khi lớp được khai báo trong ngữ cảnh instance và có đối tượng bên ngoài tương ứng.

Local class cũng có thể dùng tham số và biến cục bộ của phương thức bao quanh. Những biến này phải là `final` hoặc **effectively final**: sau khi được gán giá trị, chúng không bị gán lại. Java bảo đảm đối tượng của lớp cục bộ không phụ thuộc vào việc một biến cục bộ đã bị thay đổi sau đó.

~~~java
void greet() {
    String prefix = "Xin chào"; // effectively final

    class LocalGreeter {
        String greet(String name) {
            return prefix + ", " + name;
        }
    }

    System.out.println(new LocalGreeter().greet("Lan"));
}
~~~

Ví dụ trên hợp lệ vì `prefix` không bị gán lại. Nếu thêm `prefix = "Hello";` sau khi đã gán giá trị ban đầu, việc tham chiếu `prefix` bên trong `LocalGreeter` sẽ gây lỗi biên dịch.

## 2. Anonymous class là gì?

Anonymous class là một lớp không có tên được khai báo ngay tại biểu thức tạo đối tượng. Nó thường dùng để triển khai interface hoặc kế thừa abstract class tại một vị trí cụ thể.

Cú pháp khi triển khai interface:

~~~java
Greeter greeter = new Greeter() {
    @Override
    public String greet(String name) {
        return "Xin chào, " + name;
    }
};
~~~

Cú pháp khi kế thừa abstract class:

~~~java
TextFormatter formatter = new TextFormatter() {
    @Override
    String format(String text) {
        return "[" + text + "]";
    }
};
~~~

Ở cả hai trường hợp, phần thân trong cặp ngoặc nhọn là phần định nghĩa của lớp ẩn danh. Biểu thức `new ... { ... }` tạo ra một đối tượng thuộc lớp ẩn danh đó.

Một anonymous class có thể có trường, phương thức và khối khởi tạo instance. Tuy nhiên, nó **không thể khai báo constructor có tên riêng**, vì bản thân lớp không có tên để dùng làm tên constructor. Khi tạo lớp ẩn danh kế thừa một lớp, phần `new KiểuCha(...)` gọi constructor của lớp cha.

Nếu lớp ẩn danh triển khai interface có nhiều phương thức trừu tượng, nó phải triển khai đầy đủ các phương thức cần thiết để trở thành lớp cụ thể. Nếu chỉ cần triển khai một phương thức trừu tượng duy nhất của functional interface và không cần thêm trạng thái hay logic đặc biệt, lambda thường gọn hơn.

### Phạm vi biến và từ khóa `this`

Anonymous class cũng chỉ được dùng các biến cục bộ bên ngoài nếu chúng là `final` hoặc effectively final.

Trong thân anonymous class, `this` tham chiếu đến đối tượng của chính lớp ẩn danh. Nếu lớp được khai báo bên trong một lớp bao ngoài và cần tham chiếu đến đối tượng của lớp bao ngoài, có thể dùng cú pháp `OuterClass.this` trong ngữ cảnh instance thích hợp.

Với lambda, `this` có ý nghĩa khác: nó tham chiếu đến đối tượng bao quanh lambda, vì lambda không tạo ra một lớp ẩn danh với đối tượng `this` riêng. Đây là một điểm cần nhớ khi chuyển từ anonymous class sang lambda.

## 3. Ví dụ Java hoàn chỉnh

Ví dụ sau minh họa ba trường hợp: local class triển khai interface, anonymous class triển khai cùng interface và anonymous class kế thừa abstract class. Tất cả được đặt trong một tệp để có thể biên dịch và chạy trực tiếp.

~~~java
import java.util.Locale;

interface Greeter {
    String greet(String name);
}

abstract class TextFormatter {
    abstract String format(String text);
}

public class LocalAndAnonymousClassesDemo {
    public static void main(String[] args) {
        String prefix = "Xin chào";

        // Local class: có tên, phạm vi giới hạn trong main().
        class LocalGreeter implements Greeter {
            @Override
            public String greet(String name) {
                // prefix được capture vì effectively final.
                return prefix + ", " + name + "!";
            }
        }

        Greeter localGreeter = new LocalGreeter();

        // Anonymous class: triển khai Greeter ngay tại nơi tạo đối tượng.
        Greeter anonymousGreeter = new Greeter() {
            @Override
            public String greet(String name) {
                return "Hello, " + name + "!";
            }
        };

        // Anonymous class: kế thừa abstract class và ghi đè phương thức.
        TextFormatter formatter = new TextFormatter() {
            @Override
            String format(String text) {
                return "[" + text.toUpperCase(Locale.ROOT) + "]";
            }
        };

        System.out.println(localGreeter.greet("Lan"));
        System.out.println(anonymousGreeter.greet("Minh"));
        System.out.println(formatter.format("java"));
    }
}
~~~

Lưu nội dung vào tệp `LocalAndAnonymousClassesDemo.java`, sau đó chạy bằng Java 17 trở lên:

~~~text
javac LocalAndAnonymousClassesDemo.java
java LocalAndAnonymousClassesDemo
~~~

Kết quả chuẩn của chương trình:

~~~text
Xin chào, Lan!
Hello, Minh!
[JAVA]
~~~

Tên tệp phải khớp chính xác với tên lớp `public LocalAndAnonymousClassesDemo`. Hai interface/lớp hỗ trợ trong ví dụ không được khai báo `public`, nên có thể cùng nằm trong tệp đó. `Locale.ROOT` giúp chuyển chữ hoa theo quy tắc không phụ thuộc ngôn ngữ mặc định của máy chạy.

## 4. So sánh local class và anonymous class

| Tiêu chí | Local class | Anonymous class |
|---|---|---|
| Tên lớp | Có tên do lập trình viên đặt | Không có tên lớp được đặt trong mã nguồn |
| Cách khai báo | Khai báo lớp trong một khối lệnh | Khai báo phần thân lớp trong biểu thức `new ... { ... }` |
| Phạm vi | Tên lớp dùng được trong khối khai báo | Không có tên lớp để tham chiếu trực tiếp ở nơi khác |
| Tạo đối tượng | Có thể tạo nhiều đối tượng từ lớp đã khai báo | Mỗi lần biểu thức được thực thi sẽ tạo một đối tượng mới |
| Constructor riêng | Có thể khai báo constructor | Không thể khai báo constructor riêng có tên |
| Trạng thái và logic | Phù hợp khi cần nhiều trường, phương thức hoặc logic dài hơn | Phù hợp với phần triển khai ngắn, gắn với một điểm sử dụng |
| Kế thừa/triển khai | Có thể kế thừa một lớp và triển khai interface | Có thể kế thừa một lớp hoặc triển khai một interface tại biểu thức tạo đối tượng |

Cả hai đều có thể truy cập biến cục bộ effectively final và đều có thể được dùng để cung cấp triển khai cho một kiểu trừu tượng. Khác biệt nằm ở cách định danh lớp và cách tổ chức mã nguồn.

## 5. Khi nào nên dùng mỗi loại?

Chọn **local class** khi phần triển khai có nhiều bước, cần tên gọi rõ ràng, có constructor hoặc cần tạo nhiều đối tượng cùng kiểu trong một phương thức. Việc đặt lớp gần nơi sử dụng vẫn giữ phạm vi của nó nhỏ, đồng thời làm phần triển khai dễ đọc hơn một khối anonymous class dài.

Chọn **anonymous class** khi cần một triển khai cục bộ ngắn và chỉ cần dùng lớp tại biểu thức đó. Ví dụ điển hình là ghi đè một callback hoặc cung cấp một triển khai riêng của interface cho một lời gọi cụ thể.

Nếu kiểu cần triển khai là functional interface và chỉ cần cung cấp phần thân cho một phương thức trừu tượng, hãy cân nhắc lambda:

~~~java
Greeter greeter = name -> "Xin chào, " + name;
~~~

Lambda không thể thay thế anonymous class trong mọi trường hợp. Lambda chỉ dùng được với functional interface, trong khi anonymous class còn có thể kế thừa abstract class. Anonymous class cũng có thể có trường instance và ghi đè nhiều phương thức, nên vẫn phù hợp khi cần những khả năng đó.

## 6. Lỗi thường gặp và cách xử lý

1. **Dùng tên local class ngoài phạm vi khai báo.** Hãy chuyển phần sử dụng vào đúng khối hoặc chọn một lớp có phạm vi rộng hơn nếu nhiều nơi thực sự cần dùng.
2. **Gán lại biến cục bộ đã được capture.** Giữ biến effectively final, hoặc thiết kế lại cách truyền trạng thái thay vì thay đổi trực tiếp biến đó.
3. **Quên triển khai phương thức trừu tượng.** Kiểm tra đầy đủ các phương thức bắt buộc của interface hoặc abstract class. Với phương thức interface, phần triển khai thông thường phải khai báo `public`.
4. **Cố khai báo constructor cho anonymous class.** Anonymous class không có tên lớp để đặt tên constructor. Nếu cần constructor riêng hoặc nhiều cấu hình khởi tạo, local class hay một lớp được đặt tên thường phù hợp hơn.
5. **Gọi phương thức bổ sung qua kiểu tham chiếu quá tổng quát.** Nếu biến được khai báo là kiểu interface, chỉ những phương thức có trong interface mới có thể được gọi trực tiếp qua biến đó, dù anonymous class có thêm phương thức riêng.
6. **Nhầm ý nghĩa của `this`.** Trong anonymous class, `this` trỏ đến đối tượng ẩn danh; dùng `OuterClass.this` khi cần đối tượng bao ngoài và ngữ cảnh cho phép.

Khi đọc hoặc thiết kế mã, hãy xác định trước kiểu trừu tượng cần triển khai, phạm vi sử dụng, lượng trạng thái cần lưu và số phương thức cần ghi đè. Những yếu tố này giúp quyết định giữa local class, anonymous class và lambda một cách rõ ràng.
