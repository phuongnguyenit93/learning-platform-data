# Kiểm tra mức ngôn ngữ để tránh nhầm với cú pháp mới hơn

## Mục tiêu

Sau bài học này, bạn có thể:

- Phân biệt phiên bản JDK đang chạy, phiên bản trình biên dịch và mức ngôn ngữ Java mà source code được phép sử dụng.
- Chọn đúng mức Java khi biên dịch một ví dụ về Generics và type inference.
- Nhận ra cú pháp hoặc API được bổ sung sau Java 9, dù máy đang cài JDK mới hơn.
- Dùng \`javac --release\` để kiểm tra cả cú pháp, bytecode và Java SE API của một phiên bản mục tiêu.
- Đọc lỗi biên dịch để xác định code đang dùng cú pháp mới hay API chưa có ở phiên bản mục tiêu.

## 1. Vì sao cần kiểm tra mức ngôn ngữ?

Một máy có thể cài JDK 17, 21 hoặc mới hơn, nhưng project vẫn phải tương thích với Java 9. Nếu chỉ chạy \`javac\` bằng JDK mới nhất, compiler có thể chấp nhận cú pháp được bổ sung sau Java 9. Code đó có thể không biên dịch được khi build bằng JDK 9 hoặc khi đặt mức tương thích thấp hơn.

Có ba phiên bản cần phân biệt:

| Khái niệm | Ý nghĩa | Cách kiểm tra |
|---|---|---|
| JDK/compiler version | Phiên bản bộ công cụ dùng để biên dịch | \`javac -version\` |
| Runtime version | Phiên bản JVM chạy chương trình | \`java -version\` |
| Target/release level | Phiên bản Java mà source và output phải tương thích | Tham số \`--release\` trong lệnh biên dịch hoặc cấu hình build |

Ví dụ, \`javac 24\` có thể biên dịch source theo Java 9 bằng \`--release 9\`. Khi đó compiler mới đang áp dụng giới hạn của Java 9. Điều này không có nghĩa chương trình đã được chạy thử trên JVM Java 9; muốn kiểm tra runtime thực tế, cần chạy trên JVM mục tiêu.

**Quy tắc:** phiên bản JDK cài trên máy không tự động xác định phiên bản Java mà project hỗ trợ. Mức tương thích phải được khai báo và kiểm tra rõ ràng.

## 2. Cú pháp Generics thay đổi theo phiên bản

Generics được đưa vào Java từ Java 5. Các cú pháp type inference được bổ sung dần, vì vậy cần biết chính xác cú pháp nào có mặt ở mức Java đang dùng.

| Phiên bản | Điểm liên quan đến Generics | Ví dụ |
|---|---|---|
| Java 5 | Khai báo kiểu generic và type parameter | \`List<String>\` |
| Java 7 | Diamond operator trong khởi tạo đối tượng | \`new ArrayList<>()\` |
| Java 9 | Diamond operator được phép dùng với anonymous class | \`new Formatter<>() { ... }\` |
| Java 10 | Local variable type inference với \`var\` | \`var names = new ArrayList<String>();\` |

### 2.1. Generic type và diamond operator

Khai báo kiểu generic tường minh:

~~~java
List<String> names = new ArrayList<String>();
~~~

Từ Java 7, diamond operator \`<>\` cho phép compiler suy luận type argument từ ngữ cảnh:

~~~java
List<String> names = new ArrayList<>();
~~~

Trong ví dụ này, kiểu đích \`List<String>\` giúp compiler suy luận đối tượng được tạo là \`ArrayList<String>\`. Diamond operator chỉ rút gọn phần type argument ở vế phải; biến vẫn có kiểu generic rõ ràng.

### 2.2. Diamond operator với anonymous class: Java 9

Java 9 cho phép dùng diamond operator khi tạo anonymous class. Ví dụ:

~~~java
abstract class Formatter<T> {
    abstract T format(T value);
}

Formatter<String> formatter = new Formatter<>() {
    @Override
    String format(String value) {
        return value.trim().toUpperCase();
    }
};
~~~

Compiler suy luận type argument là \`String\` từ kiểu đích \`Formatter<String>\`. Cú pháp này không được hỗ trợ ở source level Java 8; khi cần tương thích Java 8, hãy ghi type argument tường minh:

~~~java
Formatter<String> formatter = new Formatter<String>() {
    @Override
    String format(String value) {
        return value.trim().toUpperCase();
    }
};
~~~

Hai cách đều dùng anonymous class, nhưng chỉ cách dùng diamond trong anonymous class cần mức ngôn ngữ Java 9 trở lên.

### 2.3. \`var\` là Java 10, không phải Java 9

Java 10 bổ sung local variable type inference:

~~~java
var names = new ArrayList<String>();
names.add("Java");
~~~

Compiler suy luận kiểu biến cục bộ là \`ArrayList<String>\`. \`var\` không xóa bỏ Generics: type argument \`String\` vẫn xác định kiểu phần tử của danh sách.

\`var\` chỉ dùng cho biến cục bộ có initializer. Không dùng nó để khai báo field, tham số method hoặc kiểu trả về method. Không thể suy luận kiểu từ initializer là \`null\`.

Đoạn sau không hợp lệ ở mức Java 9:

~~~java
var names = new ArrayList<String>();
~~~

Nếu project yêu cầu Java 9, hãy dùng kiểu biến tường minh:

~~~java
List<String> names = new ArrayList<>();
~~~

## 3. Phân biệt cú pháp ngôn ngữ với Java API

Không phải mọi lỗi liên quan đến phiên bản đều là lỗi cú pháp. Một chương trình có thể dùng cú pháp Java 9 hợp lệ nhưng gọi API chỉ xuất hiện ở Java 10 hoặc Java 11.

Ví dụ:

~~~java
List<String> names = List.of("An", "Binh");
~~~

\`List.of(...)\` là static factory method được thêm vào \`java.util.List\` trong Java 9. Đây là API của thư viện chuẩn, không phải một toán tử hay cú pháp Generics mới. Method dùng generic type inference để tạo danh sách \`List<String>\` từ các phần tử đầu vào. Danh sách trả về là unmodifiable: các thao tác thay đổi như \`add\` hoặc \`remove\` không được hỗ trợ.

Một ví dụ khác:

~~~java
String clean = input.strip();
~~~

\`String.strip()\` có từ Java 11. Nếu target là Java 9, API này không tồn tại. Với ví dụ cần tương thích Java 9, có thể dùng \`trim()\` khi ngữ nghĩa xử lý khoảng trắng của \`trim\` là phù hợp. Hai method không hoàn toàn tương đương: \`strip\` dùng định nghĩa whitespace của Unicode, trong khi \`trim\` loại bỏ các ký tự có mã không lớn hơn U+0020.

Hãy phân loại lỗi trước khi sửa:

- **Lỗi cú pháp/ngôn ngữ:** compiler không nhận ra cấu trúc source ở mức release đã chọn, ví dụ \`var\` với \`--release 9\`.
- **Lỗi API:** cú pháp hợp lệ nhưng method hoặc class không có trong Java SE API của release, ví dụ \`List.of\` với \`--release 8\` hoặc \`String.strip\` với \`--release 9\`.
- **Lỗi dependency:** thư viện bên thứ ba được project sử dụng yêu cầu Java mới hơn. \`--release\` không thể tự hạ phiên bản bytecode hay API của dependency đó.

## 4. Dùng \`javac --release\` để kiểm tra

Từ JDK 9, \`javac\` cung cấp tùy chọn \`--release N\`. Đây là lựa chọn nên dùng khi cần biên dịch cho một phiên bản Java xác định.

~~~bash
javac --release 9 -Xlint:all -d out src/Java9GenericLevelDemo.java
java -cp out Java9GenericLevelDemo
~~~

Với \`--release 9\`, compiler kiểm tra:

1. **Cú pháp/ngôn ngữ:** chỉ chấp nhận các tính năng của Java 9 trở xuống.
2. **Bytecode:** tạo class file tương thích với Java 9.
3. **Java SE API:** chỉ cho phép dùng API công khai có trong Java SE 9.

Để kiểm tra tương thích Java 8, dùng \`--release 8\`; để kiểm tra cú pháp \`var\`, dùng \`--release 10\` hoặc mức mới hơn.

### 4.1. Vì sao \`-source\` và \`-target\` chưa đủ?

Các tùy chọn riêng:

~~~bash
javac -source 9 -target 9 Example.java
~~~

\`-source\` giới hạn cú pháp source, còn \`-target\` chọn định dạng bytecode. Khi dùng chúng với JDK mới, compiler vẫn có thể nhìn thấy Java SE API của JDK đang cài. Vì vậy, source có thể gọi một API mới hơn Java 9 rồi biên dịch thành công, nhưng lỗi khi chạy trên Java 9.

\`--release 9\` kết hợp việc giới hạn ngôn ngữ, bytecode và Java SE API của release mục tiêu, nên phù hợp hơn cho kiểm tra tương thích. Không cần ghép \`--release\` với \`-source\` hoặc \`-target\`; compiler không cho dùng các tùy chọn này cùng nhau.

Lưu ý: \`--release\` chỉ kiểm soát Java SE API được compiler cung cấp. Nó không xác nhận phiên bản thư viện bên thứ ba, môi trường hệ điều hành, reflective access hoặc hành vi runtime của toàn bộ ứng dụng. Dependency và runtime vẫn cần được kiểm tra riêng.

### 4.2. Kiểm tra compiler và runtime

~~~bash
javac -version
java -version
~~~

Hai lệnh có thể cho kết quả khác nhau nếu máy có nhiều JDK hoặc PATH trỏ đến hai bản cài khác nhau. Với Gradle hoặc IDE, cần kiểm tra JDK mà chính Gradle daemon hoặc build tool đang sử dụng; kết quả \`java -version\` trong terminal chưa chắc đại diện cho JVM của IDE.

\`--release\` cần compiler từ JDK 9 trở lên. JDK 8 không nhận tùy chọn này. Nếu dùng JDK 9+ để tạo output Java 8, có thể chỉ định \`--release 8\`.

## 5. Ví dụ hoàn chỉnh: kiểm tra Java 9 và Java 10

Tạo file **Java9GenericLevelDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class Java9GenericLevelDemo {

    static abstract class Formatter<T> {
        abstract T format(T value);
    }

    public static void main(String[] args) {
        // Diamond operator đã có từ Java 7.
        List<String> names = new ArrayList<>();
        names.add("An");
        names.add("Binh");
        System.out.println(names);

        // List.of là API Java 9, trả về danh sách không sửa được.
        List<String> immutableNames = List.of("An", "Binh");
        System.out.println(immutableNames);

        // Diamond với anonymous class được hỗ trợ từ Java 9.
        Formatter<String> formatter = new Formatter<>() {
            @Override
            String format(String value) {
                return value.trim().toUpperCase();
            }
        };
        System.out.println(formatter.format("  java 9  "));
    }
}
~~~

Biên dịch theo Java 9:

~~~bash
javac --release 9 -d out Java9GenericLevelDemo.java
java -cp out Java9GenericLevelDemo
~~~

Output chính xác:

~~~text
[An, Binh]
[An, Binh]
JAVA 9
~~~

Nếu biên dịch chính file trên bằng \`--release 8\`, compiler báo lỗi vì \`List.of\` chưa có trong API Java 8 và diamond với anonymous class chưa được hỗ trợ ở source level 8.

Tạo file **VarLevelDemo.java** để kiểm tra Java 10:

~~~java
import java.util.ArrayList;

public class VarLevelDemo {
    public static void main(String[] args) {
        var names = new ArrayList<String>();
        names.add("Java");
        System.out.println(names);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 10 -d out VarLevelDemo.java
java -cp out VarLevelDemo
~~~

Output chính xác:

~~~text
[Java]
~~~

Nếu chạy lệnh compile với \`--release 9\`, source dùng \`var\` sẽ không biên dịch. Khi cần Java 9, hãy viết kiểu biến tường minh.

## 6. Quy trình kiểm tra khi đọc hoặc viết ví dụ

1. **Xác định phiên bản mục tiêu.** Đọc cấu hình project, yêu cầu triển khai hoặc môi trường runtime cần hỗ trợ.
2. **Kiểm tra JDK thực sự dùng để build.** Xem compiler, Gradle/IDE JVM và toolchain nếu có.
3. **Đọc cú pháp đáng ngờ.** Xác định feature được bổ sung ở phiên bản nào; đừng dựa vào việc compiler mới có chấp nhận hay không.
4. **Kiểm tra API.** Tra cứu phiên bản xuất hiện của method/class được gọi. Một cú pháp cũ vẫn có thể gọi API mới.
5. **Biên dịch bằng \`--release\` mục tiêu.** Ví dụ Java 9 thì dùng \`--release 9\`.
6. **Chạy thử trên runtime mục tiêu khi có thể.** Biên dịch đúng release là bằng chứng quan trọng, nhưng chưa thay thế kiểm thử môi trường thực tế.
7. **Ghi rõ phiên bản trong bài học.** Nếu ví dụ cần Java 10 hoặc mới hơn, nói rõ điều đó thay vì gắn nhãn Java 9.

## 7. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| \`var\` không được nhận diện | Mức source thấp hơn Java 10 | Dùng kiểu tường minh hoặc nâng release lên 10+ |
| Diamond trong anonymous class không được hỗ trợ | Source level Java 8 trở xuống | Dùng type argument tường minh hoặc đặt release từ 9 |
| Không tìm thấy \`List.of\` | API mục tiêu thấp hơn Java 9 | Dùng cách tạo collection phù hợp API mục tiêu hoặc nâng release |
| Không tìm thấy \`String.strip\` | API mục tiêu thấp hơn Java 11 | Chọn API có sẵn và phù hợp ngữ nghĩa |
| Build thành công nhưng runtime cũ lỗi \`NoSuchMethodError\` | Code hoặc dependency gọi API không có trên runtime | Kiểm tra release/API và dependency bằng đúng target |
| Terminal compile đúng nhưng IDE build lỗi | Terminal và IDE dùng JDK/cấu hình khác nhau | Đồng bộ Gradle JVM, toolchain và compiler release |

Đừng giải quyết lỗi bằng cách chỉ nâng JDK cài đặt nếu yêu cầu của project vẫn là Java 9. Trước hết xác định code đang dùng feature/API nào và mức tương thích thực sự cần đạt.

## 8. Checklist

- [ ] Đã xác định Java release mà project cần hỗ trợ.
- [ ] Đã phân biệt JDK compiler version với runtime version.
- [ ] Không dùng \`var\` trong source yêu cầu Java 9.
- [ ] Hiểu diamond operator thông thường có từ Java 7 và diamond với anonymous class có từ Java 9.
- [ ] Đã kiểm tra phiên bản của API như \`List.of\` và \`String.strip\`.
- [ ] Đã biên dịch bằng \`javac --release N\` với đúng N.
- [ ] Đã kiểm tra dependency và runtime mục tiêu khi cần.
- [ ] Ví dụ trong tài liệu ghi đúng phiên bản Java yêu cầu.

