# Các modifier ít gặp không hợp lệ với phương thức `abstract` trong Java

Phương thức `abstract` không có thân Java và cần được hiện thực theo hợp đồng kế thừa. Ngoài ba xung đột thường gặp `private`, `static` và `final`, còn có các modifier ít gặp là `synchronized`, `native`, `strictfp`, cùng từ khóa `default` trong interface. Bài này tập trung vào những trường hợp ít gặp và phân biệt chúng với từ khóa vốn không phải modifier của phương thức.

## 1. `synchronized abstract`: không có thân để khóa khi thực thi

```java
abstract class Job {
    public synchronized abstract void runJob(); // Lỗi biên dịch
}
```

`synchronized` kiểm soát việc lấy monitor khi một phương thức có thân được thực thi. Một khai báo abstract chưa có thân nên không thể đặt chính sách khóa thực thi lên khai báo đó. Lớp triển khai có thể tự chọn đồng bộ hóa:

```java
abstract class Job {
    public abstract void runJob();
}

final class SafeJob extends Job {
    @Override
    public synchronized void runJob() {
        System.out.println("Running safely");
    }
}
```

Hai lớp trên là khai báo hợp lệ. Tuy nhiên, `abstract` không tự bảo đảm mọi lớp con đều dùng `synchronized`; nếu tính đúng đắn cần một chính sách luồng chung, hãy đặt cơ chế đó trong một phương thức cụ thể được chia sẻ hoặc thiết kế rõ hợp đồng và trạng thái dùng chung.

## 2. `native abstract`: hai cơ chế hiện thực khác nhau

```java
abstract class NativeBridge {
    public native abstract int callNative(); // Lỗi biên dịch
}
```

`native int callNative();` có thể hợp lệ mà không có thân Java vì phần hiện thực được cung cấp qua cơ chế native như JNI. Khi gọi thật, chương trình vẫn cần thư viện và hàm native được liên kết đúng; nếu thiếu, có thể gặp `UnsatisfiedLinkError`.

Ngược lại, `abstract int callNative();` yêu cầu một lớp con Java cung cấp phần thân. Không thể gộp hai cách cung cấp implementation trên cùng một phương thức. Hãy chọn `native` khi hiện thực nằm ở mã native, hoặc `abstract` khi lớp con Java phải hiện thực hợp đồng.

## 3. `strictfp abstract`: modifier về phép tính không thay thế thân phương thức

```java
abstract class Geometry {
    public strictfp abstract double area(); // Lỗi biên dịch
}
```

`strictfp` từng được dùng để ràng buộc ngữ nghĩa phép tính dấu phẩy động. Từ Java 17, phép tính dấu phẩy động đã có ngữ nghĩa nghiêm ngặt mặc định, nên `strictfp` trên khai báo được phép dùng không còn cần thiết và có thể phát cảnh báo. Dù vậy, `strictfp abstract` vẫn là tổ hợp không hợp lệ. Khai báo `public abstract double area();` là hợp lệ.

## 4. `default abstract` trong interface

Một phương thức instance thông thường không có thân trong interface mặc định là `public abstract`:

```java
interface MessageFormatter {
    String format(String text);
}
```

Một phương thức `default` lại cung cấp phần thân mặc định:

```java
interface Formatter {
    String format(String text);

    default String wrap(String text) {
        return "[" + format(text) + "]";
    }

    static boolean isBlank(String text) {
        return text == null || text.isBlank();
    }

    private String decorate(String text) {
        return "[" + text + "]";
    }
}
```

`default`, `static` và `private` trong ví dụ đều có thân. Khai báo sau không hợp lệ:

```java
interface InvalidFormatter {
    default abstract String format(String text); // Lỗi biên dịch
}
```

`default` yêu cầu một implementation mặc định, còn `abstract` biểu thị không có thân. Trong interface, phương thức `private` cũng phải có thân; nó là helper nội bộ, không phải hợp đồng cho lớp triển khai. Đừng nhầm từ khóa `default` này với mức truy cập package-private của thành viên class không ghi access modifier.

## 5. Từ khóa không phải modifier của phương thức

Một số từ khóa vốn áp dụng cho thành phần khác, nên khai báo phương thức với chúng sai dù có hay không có `abstract`:

| Từ khóa | Thành phần áp dụng | Lý do |
|---|---|---|
| `volatile` | Field | Không phải modifier của method |
| `transient` | Field | Điều khiển serialization của field, không phải method |
| `sealed` / `non-sealed` | Class hoặc interface trong hierarchy sealed | Kiểm soát kiểu nào được kế thừa/thực hiện, không áp dụng lên method |

Ví dụ `volatile abstract void compute();` sai vì `volatile` không phải modifier của method; `volatile void compute() { ... }` cũng sai. Constructor cũng không thể khai báo `abstract`, vì constructor không được override như instance method. Không có `abstract field` hoặc `abstract constructor` trong Java.

Để đối chiếu, `private`, `static` và `final` cũng không được kết hợp với phương thức abstract: private ngăn override, static dùng method hiding thay vì override instance, còn final cấm override. Lớp abstract vẫn có thể chứa các phương thức private/static/final **có thân**; tính hợp lệ được xét trên từng khai báo.

## 6. Ví dụ Java 17+ chạy được: modifier hợp lệ ở những phương thức khác nhau

Lưu toàn bộ vào `AbstractModifierDemo.java`:

```java
abstract class Processor {
    protected abstract String transform(String input);

    private String normalize(String input) {
        return input.strip();
    }

    public final String process(String input) {
        return "[" + transform(normalize(input)) + "]";
    }

    public static String version() {
        return "v1";
    }
}

final class UppercaseProcessor extends Processor {
    @Override
    protected String transform(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}

public class AbstractModifierDemo {
    public static void main(String[] args) {
        Processor processor = new UppercaseProcessor();
        System.out.println(processor.process("  Java  "));
        System.out.println(Processor.version());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 AbstractModifierDemo.java
java AbstractModifierDemo
```

Kết quả:

```text
[JAVA]
v1
```

`transform` là hook abstract mà lớp con triển khai; `normalize` là helper private có thân; `process` là phương thức final cụ thể cố định trình tự; `version` là static có thân. Những modifier đó có thể cùng xuất hiện trong một abstract class vì chúng nằm trên các khai báo riêng biệt.

## 7. Bảng chẩn đoán nhanh

| Khai báo | Hợp lệ? | Cách hiểu |
|---|---|---|
| `synchronized abstract void run();` | Không | Không có thân để thực thi cơ chế đồng bộ |
| `native abstract int call();` | Không | Native implementation và abstract subclass implementation là hai cơ chế khác nhau |
| `strictfp abstract double area();` | Không | Modifier không thể đi cùng abstract |
| `default abstract String format();` trong interface | Không | Default method cần có thân |
| `private void helper() { ... }` trong abstract class | Có | Helper cụ thể, không yêu cầu override |
| `public final void process() { ... }` trong abstract class | Có | Phương thức cụ thể, cấm override |
| `static String version() { ... }` trong abstract class | Có | Phương thức lớp có thân |

Khi đọc lỗi modifier, hãy phân biệt ba nguyên nhân: modifier ngăn override; modifier yêu cầu một cơ chế thực thi khác; hoặc từ khóa vốn không áp dụng cho phương thức. Chẩn đoán theo nhóm này giúp chọn đúng cách sửa thay vì chỉ xóa từ khóa ngẫu nhiên.
