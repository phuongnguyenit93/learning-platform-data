# Quy tắc lựa chọn main khi tồn tại nhiều dạng phương thức phù hợp

> **Chương:** Hàm main  
> **Phiên bản:** Java 25 (JDK 25, tính năng chính thức — không cần `--enable-preview`).  
> **Trọng tâm:** Java launcher chọn phương thức `main` nào khi một lớp hoặc compact source file có nhiều phương thức mang tên `main`, kể cả các dạng `static`, instance, có tham số và không có tham số.

## 1. Đặt vấn đề

Một lớp Java 25 có thể chứa đồng thời hai phương thức hợp lệ để bắt đầu chạy chương trình:

~~~java
class TwoMains {
    static void main() {
        System.out.println("main khong tham so");
    }

    void main(String[] args) {
        System.out.println("main co tham so: " + args.length);
    }
}
~~~

Khi biên dịch và chạy:

~~~bash
javac TwoMains.java
java TwoMains alpha beta
~~~

Kết quả:

~~~text
main co tham so: 2
~~~

Điều đáng chú ý: **Java chọn phương thức instance có `String[]`, dù trong lớp còn có phương thức `static main()`**. Quy tắc chọn không dựa vào độ “cổ điển” của chữ ký hay ưu tiên `static`. Đây là hành vi được đặc tả trong **Java Language Specification (JLS) 25, `12.1.4**.

Trước khi thực hành, kiểm tra công cụ:

~~~bash
java --version
javac --version
~~~

Cả hai cần báo feature release **25**. Các ví dụ của bài dùng khả năng **compact source files và instance main methods** đã chính thức hóa trong Java 25 (JEP 512), không sử dụng dạng preview cũ hoặc các tham số kích hoạt preview.

**Mục tiêu học tập:** biết phương thức nào được xem là ứng viên (candidate), hiểu thứ tự chọn khi có nhiều ứng viên, giải thích lúc nào launcher phải tạo object, và phân biệt tình huống mã không biên dịch được với tình huống biên dịch thành công nhưng khởi chạy thất bại.

## 2. Phương thức main nào được xem là ứng viên?

Theo JLS 25 `12.1.4, một phương thức tên `main` được khai báo trong hoặc **được thừa kế bởi** lớp/interface khởi chạy được xem là *candidate main method* khi thỏa đồng thời:

1. Kiểu trả về là `void`.
2. Mức truy cập là `public`, `protected` hoặc **package-private** (không ghi modifier). `private` không hợp lệ để làm entry point.
3. Danh sách tham số là **một** `String[]` (bao gồm cú pháp `String...`) hoặc **không có** tham số.
4. Phương thức có thể là `static` hoặc **instance**. `throws` clause vẫn được phép.

Bảng tóm tắt:

| Chữ ký minh họa | Candidate trong Java 25? | Vì sao? |
|---|---|---|
| `public static void main(String[] args)` | Có | Dạng phổ biến, trả `void` và nhận `String[]` |
| `static void main(String... args)` | Có | `String...` được biểu diễn bằng `String[]` |
| `protected void main(String[] args)` | Có | Instance method, quyền `protected` |
| `void main(String[] args)` | Có | Instance method, package-private |
| `public static void main()` | Có | Static, không tham số |
| `void main()` | Có | Instance, không tham số |
| `private static void main(String[] args)` | Không | `private` không phải mức truy cập được phép |
| `private void main()` | Không | `private` không đủ điều kiện |
| `static int main(String[] args)` | Không | Kiểu trả về không phải `void` |
| `void main(Object[] args)` | Không | `Object[]` không phải `String[]` |
| `void main(String arg)` | Không | Nhận `String` đơn lẻ, không phải mảng |
| `void main(String[] args, int code)` | Không | Hai tham số |

Có tất cả **12 dạng** khi kết hợp ba mức truy cập hợp lệ, hai lựa chọn `static`/instance và hai dạng tham số. Có thể viết `String...` thay cho `String[]` trong nhóm nhận tham số, nhưng đây không phải một loại chữ ký bổ sung có thể overload với `String[]`.

**Phân biệt candidate và lời gọi phương thức thông thường:** Java vẫn có thể cho phép bạn khai báo `private void main()` hoặc `int main(int n)` để dùng như các phương thức bình thường; chúng đơn giản **không** phải entry point hợp lệ. Launcher chỉ xem xét tập candidate.

## 3. Quy tắc lựa chọn: ưu tiên tham số, sau đó mới xét static/instance

Khi lớp/interface được chỉ định làm điểm bắt đầu có nhiều candidate:

1. **Có candidate `void main(String[] args)` (hoặc `String... args`)?** Chọn phương thức đó.
2. **Nếu không có**, tìm candidate `void main()` và chọn phương thức đó.
3. Sau khi đã chọn: nếu là `static`, gọi trực tiếp; nếu là **instance**, tạo một instance của lớp được khởi chạy bằng constructor không tham số rồi gọi method trên instance đó.
4. Nếu không có candidate, hoặc không thể tạo instance cần thiết, chương trình không khởi chạy thành công.

~~~mermaid
flowchart TD
    A["Lớp được chọn để chạy\njava ClassName / java File.java"] --> B{"Có candidate main(String[])\nhoặc main(String...)?"}
    B -->|Có| C["Chọn main(String[])"]
    B -->|Không| D{"Có candidate main()?"}
    D -->|Có| E["Chọn main()"]
    D -->|Không| X["Không có main hợp lệ\n→ lỗi khởi chạy"]
    C --> F{"Method đã chọn là static?"}
    E --> F
    F -->|Có| G["Gọi trực tiếp"]
    F -->|Không| H["Tạo instance của lớp khởi chạy\nbằng constructor không tham số"]
    H --> I{"Tạo instance thành công?"}
    I -->|Có| J["Gọi main trên instance"]
    I -->|Không| X
~~~

**Không có thứ tự “static trước instance”.** Giữa hai dạng tham số khác nhau, dạng `String[]` được ưu tiên. Một phương thức `instance main(String[])` có thể được chọn trước `static main()`.

| Có candidate `main(String[])`? | Có candidate `main()`? | Launcher chọn |
|---|---|---|
| Có — static | Không | Static `main(String[])` |
| Có — instance | Không | Instance `main(String[])`, phải tạo object |
| Có — static | Có — instance | Static `main(String[])` |
| Có — instance | Có — static | **Instance `main(String[])`** |
| Không | Có — static | Static `main()` |
| Không | Có — instance | Instance `main()` |
| Không | Không | Lỗi: không có entry point phù hợp |

Mọi ví dụ trong bảng đều giả định lớp và constructor hợp lệ cho nhánh được chọn. Độ ưu tiên này áp dụng sau khi Java đã xác định **candidate** dựa trên tên, kiểu trả về, mức truy cập và tham số.

### Các tham số dòng lệnh được truyền thế nào?

Với lệnh:

~~~bash
java TwoMains red blue
~~~

Launcher nhận hai đối số `red` và `blue`. Nếu chọn `main(String[] args)`, method nhận mảng với `args.length == 2`. Nếu chỉ có `main()` thì phương thức được gọi **không nhận mảng**; việc truyền thêm token sau tên lớp không biến `main()` thành một dạng method có tham số.

## 4. Ví dụ A — Static main(String[]) thắng instance main()

Lưu thành `StaticArgsWins.java`:

~~~java
class StaticArgsWins {
    public static void main(String[] args) {
        System.out.println("static String[]: " + args.length);
    }

    void main() {
        System.out.println("instance no-args");
    }
}
~~~

Chạy:

~~~bash
javac StaticArgsWins.java
java StaticArgsWins one two three
~~~

Kết quả:

~~~text
static String[]: 3
~~~

Lớp có cả `public static void main(String[])` và `void main()`. Dạng nhận `String[]` được ưu tiên; JVM không cần tạo instance vì method đã chọn là `static`.

## 5. Ví dụ B — Instance main(String[]) thắng static main()

Lưu thành `InstanceArgsWins.java`:

~~~java
class InstanceArgsWins {
    static void main() {
        System.out.println("static no-args");
    }

    void main(String[] args) {
        System.out.println("instance String[]: " + String.join(",", args));
    }
}
~~~

Chạy:

~~~bash
javac InstanceArgsWins.java
java InstanceArgsWins apple pear
~~~

Kết quả:

~~~text
instance String[]: apple,pear
~~~

Ví dụ này giúp loại bỏ hiểu nhầm hay gặp nhất: việc một phương thức `static` tồn tại **không bảo đảm** launcher sẽ chọn nó. Chỉ khi không có candidate dạng nhận `String[]`, launcher mới xét `main()`.

## 6. Ví dụ C — Hai instance main cùng hợp lệ

Lưu thành `BothInstance.java`:

~~~java
class BothInstance {
    private final String message = "instance da duoc tao";

    void main() {
        System.out.println("no-args: " + message);
    }

    protected void main(String... args) {
        System.out.println("varargs: " + args.length + " - " + message);
    }
}
~~~

Chạy:

~~~bash
javac BothInstance.java
java BothInstance A B
~~~

Kết quả:

~~~text
varargs: 2 - instance da duoc tao
~~~

`String... args` có cùng kiểu tham số như `String[] args` trong chữ ký method, vì vậy được ưu tiên so với `main()`. Lớp có constructor không tham số ngầm định nên launcher tạo được object và gọi method instance đã chọn.

### Khác biệt với hai phương thức trùng chữ ký

Đoạn sau **không biên dịch được** (đặt riêng trong `DuplicateSignature.java` để xem lỗi):

~~~java
class DuplicateSignature {
    static void main(String[] args) {}

    void main(String... args) {}
}
~~~

Cả hai có chữ ký `main(String[])`; Java không cho phép overload chỉ bằng cách đổi `static`/instance hoặc đổi cú pháp mảng sang varargs. Lỗi xảy ra ở **javac**, trước cả giai đoạn launcher lựa chọn entry point.

## 7. Ví dụ D — Chỉ có main() không tham số

Lưu `NoArgOnly.java`:

~~~java
class NoArgOnly {
    void main() {
        System.out.println("main() instance");
    }
}
~~~

Chạy:

~~~bash
javac NoArgOnly.java
java NoArgOnly alpha beta
~~~

Kết quả:

~~~text
main() instance
~~~

Đây là entry point hoàn toàn hợp lệ của Java 25. Launcher tạo instance rồi gọi `main()`. Các token `alpha beta` là đối số dòng lệnh mà `main()` không nhận trực tiếp; nếu ứng dụng cần xử lý đối số, nên khai báo `main(String[] args)` thay thế.

Đối với một chương trình khởi tạo nhỏ không có đối số, `static void main()` cũng hợp lệ:

~~~java
class StaticNoArg {
    static void main() {
        System.out.println("static main()");
    }
}
~~~

Chạy `javac StaticNoArg.java` rồi `java StaticNoArg`; kết quả là `static main()`. Không cần khởi tạo object ở nhánh `static` này.

## 8. Ví dụ E — Private main(String[]) bị loại khỏi tập candidate

Lưu `PrivateArgsIgnored.java`:

~~~java
class PrivateArgsIgnored {
    private static void main(String[] args) {
        System.out.println("private String[]");
    }

    static void main() {
        System.out.println("package-private no-args");
    }
}
~~~

Chạy:

~~~bash
javac PrivateArgsIgnored.java
java PrivateArgsIgnored hidden
~~~

Kết quả:

~~~text
package-private no-args
~~~

Mặc dù lớp chứa `main(String[])`, nó **không được xem xét** vì mang quyền `private`. Candidate còn lại là `static void main()`, nên launcher chọn phương thức không tham số. Không nên viết quá nhiều overload `main` có access khác nhau trong code thực tế vì người đọc dễ đoán sai điểm bắt đầu chương trình.

Nếu chỉ có một phương thức `private static void main(String[] args)` mà không có candidate khác, `javac` vẫn có thể biên dịch lớp đó, nhưng lệnh `java` không thể khởi chạy nó như entry point.

## 9. Ví dụ F — Kế thừa main có thể ảnh hưởng lựa chọn

JLS 25 không giới hạn candidate ở những method viết trực tiếp trong lớp ban đầu: **method được kế thừa cũng có thể là candidate**.

Tạo `InheritedEntry.java`:

~~~java
class BaseEntry {
    protected void main(String[] args) {
        System.out.println("inherited String[]: " + args.length);
    }
}

class InheritedEntry extends BaseEntry {
    static void main() {
        System.out.println("declared static no-args");
    }
}
~~~

Chạy:

~~~bash
javac InheritedEntry.java
java InheritedEntry X Y
~~~

Kết quả:

~~~text
inherited String[]: 2
~~~

Phương thức `protected void main(String[])` được thừa kế từ `BaseEntry` có quyền hợp lệ và được chọn trước `static void main()` của lớp con. Launcher tạo **instance của `InheritedEntry`**, rồi gọi method kế thừa trên instance đó.

Tương tự, một `default void main(String[] args)` của interface có thể là candidate nếu lớp khởi chạy kế thừa method ấy và không có xung đột chữ ký. Đây là quy tắc chung của kế thừa phương thức trong Java, không phải một kiểu launcher riêng cho interface.

**Thực hành phòng ngừa:** nếu ứng dụng là CLI lớn, tránh tình cờ kế thừa một `main` khác dạng tham số từ superclass/interface; hãy cho entry point một chữ ký rõ ràng và có test chạy chính class định khởi động.

## 10. Constructor của lớp ảnh hưởng thế nào đến instance main?

Khi chọn **instance `main`**, Java launcher cần tạo instance của **lớp được chọn khởi chạy**, sử dụng constructor không tham số có thể gọi được. Đó không nhất thiết là lớp khai báo method `main` nếu method được kế thừa.

### Trường hợp thành công

Lưu `ConstructedEntry.java`:

~~~java
class ConstructedEntry {
    ConstructedEntry() {
        System.out.println("constructor");
    }

    void main() {
        System.out.println("instance main");
    }
}
~~~

Chạy `javac ConstructedEntry.java` rồi `java ConstructedEntry`:

~~~text
constructor
instance main
~~~

Đây là trường hợp constructor không tham số, package-private, khởi tạo đối tượng thành công. Nếu chọn `static main`, launcher không phải tạo đối tượng theo quy tắc này.

### Trường hợp có candidate được ưu tiên nhưng không tạo được instance

Lưu `InaccessibleConstructor.java`:

~~~java
class InaccessibleConstructor {
    private InaccessibleConstructor() {
        System.out.println("private constructor");
    }

    void main(String[] args) {
        System.out.println("instance String[]");
    }

    static void main() {
        System.out.println("static fallback?");
    }
}
~~~

Biên dịch và thử chạy:

~~~bash
javac InaccessibleConstructor.java
java InaccessibleConstructor demo
~~~

`javac` chấp nhận hai overload khác tham số. Khi khởi chạy, launcher **chọn instance `main(String[])` trước**, sau đó không tạo được đối tượng bằng constructor không tham số hợp lệ vì constructor đó là `private`. Chương trình **khởi chạy thất bại**; không chuyển sang `static main()` để “dự phòng”. Nội dung thông báo lỗi cụ thể phụ thuộc cách triển khai launcher/JDK.

Quy tắc cần nhớ: **việc lựa chọn candidate xảy ra trước thao tác tạo instance**, và thất bại khởi tạo không làm launcher chọn ứng viên thứ hai.

Nếu bạn viết một lớp chỉ có constructor nhận tham số:

~~~java
class RequiresArgument {
    RequiresArgument(String name) {}

    void main() {
        System.out.println("will not launch");
    }
}
~~~

Lớp không có constructor không tham số nên `main()` không thể được launcher gọi thành công dưới dạng instance entry point. Khi thực sự cần xây đối tượng phức tạp, nên tạo một entry point `static` rõ ràng để tự xây dependency, hoặc thiết kế constructor không tham số phù hợp.

## 11. Compact source files của Java 25 cũng tuân theo quy tắc này

Java 25 hỗ trợ **compact source files** (JEP 512, đã chính thức), cho phép khai báo field và method ở cấp tệp mà không viết `class`. Compiler tạo một lớp ngầm định trong unnamed package; lớp này có constructor không tham số mặc định.

Lưu `CompactSelection.java`:

~~~java
void main() {
    IO.println("compact no-args");
}

void main(String[] args) {
    IO.println("compact String[]: " + args.length);
}
~~~

Chạy trực tiếp:

~~~bash
java CompactSelection.java a b c
~~~

Kết quả:

~~~text
compact String[]: 3
~~~

Bởi vì compact source file có cả hai ứng viên, launcher vẫn ưu tiên `main(String[])`. Không cần `--enable-preview` trên Java 25. Trong compact source file, các type công khai được xuất bởi `java.base` được import tự động; `IO` thuộc `java.lang` cũng sẵn dùng.

Một compact source file chỉ gồm:

~~~java
void main() {
    IO.println("Hello Java 25");
}
~~~

cũng có thể chạy bằng `java HelloCompact.java` (nếu lưu tệp dưới tên `HelloCompact.java`). Dạng đơn giản này phù hợp cho ví dụ, tiện ích nhỏ hoặc hướng dẫn nhập môn. Với ứng dụng có nhiều lớp, package, dependency injection hoặc thư viện tái sử dụng, khai báo class/package rõ ràng vẫn hữu ích để quản lý kiến trúc.

### Phân biệt cách chạy nguồn và cách chạy class

Với `java CompactSelection.java a b`, launcher biên dịch mã nguồn để chạy, không cần người học biên dịch trước. Với `javac CompactSelection.java` rồi `java CompactSelection a b`, bạn biên dịch trước và chạy class được tạo. Trong cả hai trường hợp, quy tắc chọn `main` về mặt ngôn ngữ là như nhau.

Nên đặt các ví dụ độc lập trong **các tệp khác nhau**, chạy bằng đúng tên tệp/class tương ứng. Nếu vô tình chạy class cũ trong thư mục khác hoặc sai classpath, bạn có thể tưởng rằng một phương thức `main` đã được chọn sai.

## 12. Tình huống không hợp lệ và nhầm lẫn thường gặp

| Hiện tượng | Nguyên nhân | Cách diễn giải/sửa |
|---|---|---|
| `java` báo không tìm thấy entry point | Không có `main` trả `void`, với kiểu tham số và access phù hợp | Thêm `main()` hoặc `main(String[])` hợp lệ |
| Có `private main(String[])` nhưng launcher chọn `main()` | Method private không phải candidate | Dùng `public`/`protected`/package-private nếu muốn nó là entry point |
| `static main()` không chạy dù có trong lớp | Còn có candidate `main(String[])` ưu tiên hơn | Kiểm tra toàn bộ overload và inherited method |
| Chạy lỗi tạo instance | Candidate được chọn là instance nhưng constructor không tham số không dùng được | Sửa constructor hoặc chọn thiết kế entry point `static` |
| `javac` báo duplicate method | `String[]` và `String...` có cùng chữ ký; `static`/instance không tạo overload mới | Chỉ giữ một `main(String[])` theo chữ ký |
| `javac` báo kiểu trả về xung đột | Overload/override sai quy tắc phương thức Java | Đọc lỗi biên dịch trước khi xét launcher |
| `void main(Object[] args)` không được chọn | `Object[]` không phải `String[]` | Dùng `String[]` hoặc không có tham số |
| Command line arguments không xuất hiện trong output | Chọn `main()` nên không nhận `args` | Dùng `main(String[] args)` và xử lý mảng |
| Cùng mã nhưng JDK khác chọn main khác | Khác phiên bản hoặc cấu hình language level/toolchain | Xác minh `java --version`, `javac --version`, IDE/CI |
| Biên dịch xong chạy kết quả cũ | Chạy class file chưa biên dịch lại hoặc sai classpath | Biên dịch lại đúng file và chạy đúng class |

Một số lỗi không liên quan quy tắc chọn `main`: lỗi `ClassNotFoundException`, `UnsupportedClassVersionError`, classpath hoặc module-path sai đều cần xử lý ở tầng nạp lớp/phiên bản trước khi suy luận về entry point.

### Các lỗi biên dịch độc lập với lựa chọn của launcher

Không thể khai báo hai method chỉ khác kiểu trả về:

~~~java
class InvalidReturnOverload {
    void main() {}
    int main() { return 1; } // Compile error: duplicate signature
}
~~~

Và cũng không thể dùng `static` làm yếu tố duy nhất phân biệt chữ ký:

~~~java
class InvalidStaticOverload {
    static void main() {}
    void main() {} // Compile error: duplicate signature
}
~~~

Các ví dụ trên **cố ý sai** nhằm phân biệt quy tắc overload của ngôn ngữ với quy tắc chọn entry point của launcher. Không đưa chúng vào cùng dự án test đang cần biên dịch thành công.

## 13. Quy trình kiểm chứng và bài tập

### 13.1. Một quy trình test lặp lại được

Với mỗi ví dụ:

1. Lưu source vào tệp có tên được chỉ rõ trong bài.
2. Kiểm tra `java --version` và `javac --version` đều là JDK 25.
3. Chạy `javac TenLop.java`; phân biệt lỗi compiler (không có class file mới) với lỗi launcher.
4. Chạy `java TenLop` với đối số minh họa; ghi lại chính xác dòng output.
5. Nếu có hai candidate, tự áp dụng quy tắc **`String[]` trước, `main()` sau**; chỉ sau đó mới xét có cần constructor.
6. Nếu method không phải candidate, loại nó ra trước khi so sánh độ ưu tiên.

### 13.2. Dự đoán kết quả: ba bài tập

**Bài 1:** File `CaseOne.java`:

~~~java
class CaseOne {
    protected static void main() {
        System.out.println("A");
    }

    void main(String[] args) {
        System.out.println("B:" + args.length);
    }
}
~~~

Dự đoán `java CaseOne x y` in gì?

**Bài 2:** File `CaseTwo.java`:

~~~java
class CaseTwo {
    private void main(String... args) {
        System.out.println("A");
    }

    protected void main() {
        System.out.println("B");
    }
}
~~~

Dự đoán `java CaseTwo input` in gì?

**Bài 3:** File `CaseThree.java`:

~~~java
class CaseThree {
    CaseThree() {
        System.out.println("constructed");
    }

    static void main(String[] args) {
        System.out.println("static");
    }

    void main() {
        System.out.println("instance");
    }
}
~~~

Dự đoán `java CaseThree test` có tạo object không?

<details>
<summary>Gợi ý tự đối chiếu</summary>

- **Bài 1:** In `B:2`. Candidate nhận `String[]` là instance và được chọn dù `main()` là static.
- **Bài 2:** In `B`. `main(String...)` mang quyền `private` nên bị loại; `protected void main()` được chọn.
- **Bài 3:** In `static`, **không tạo object** theo cơ chế gọi `main`. Phương thức được chọn là `static main(String[])` nên constructor không được gọi chỉ để chạy entry point.

</details>

### 13.3. Các câu hỏi kiểm tra hiểu bản chất

1. Vì sao `instance main(String[])` có thể được gọi trước `static main()`?
2. Khi cả `String[]` và `String...` xuất hiện trong hai overload `main`, tại sao compiler chặn ngay từ đầu?
3. Tại sao `private static void main(String[])` không được xem là candidate nhưng `protected void main()` thì được?
4. Với instance `main` được kế thừa từ superclass, launcher tạo object thuộc lớp nào?
5. Vì sao thất bại khi gọi constructor không tham số không khiến launcher quay lại thử `static main()`?
6. Khi chuyển một chương trình Java 25 nhỏ sang compact source file, quy tắc chọn `main` có khác lớp tường minh không?

## 14. Khuyến nghị khi viết ứng dụng thực tế

Với chương trình command-line/console đơn giản hoặc ví dụ học Java 25, `void main()` trong compact source file rất gọn. Khi ứng dụng có tham số dòng lệnh, dùng `void main(String[] args)` hoặc `static void main(String[] args)` tùy thiết kế.

Với dự án lớn, thư viện, ứng dụng server hoặc chương trình cần tương thích với toolchain đa phiên bản, nên chọn **một entry point rõ ràng** và hạn chế overload `main` không cần thiết. Dạng `public static void main(String[] args)` vẫn là lựa chọn dễ nhận diện với nhiều công cụ và người đọc; nó **không bị thay thế hay lỗi thời** trong Java 25.

Không dùng việc đổi chữ ký `main` như một giải pháp tự động cho các chủ đề khác như AOT cache, ScopedValue, API dẫn xuất khóa hay JFR. Các tính năng này nằm ở phần lập trình/vận hành riêng; bài này chỉ mô tả **cách Java chọn và gọi entry point**.

## 15. Tài liệu chính thức

- [Java SE 25 JLS `12.1.4 — Invoke a main Method](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.1.4): định nghĩa candidate, độ ưu tiên `main(String[])` / `main()`, cách gọi static/instance và xử lý khi tạo instance thất bại.
- [Oracle JDK 25 — Compact Source Files and Instance main Methods](https://docs.oracle.com/en/java/javase/25/language/compact-source-files-instance-main-methods.html): ví dụ source-file mode, compact source file, lớp ngầm định và cách launcher chọn phương thức `main`.
- [OpenJDK JEP 512 — Simple Source Files and Instance Main Methods](https://openjdk.org/jeps/512): lý do thiết kế và trạng thái tính năng được hoàn thiện trong JDK 25.
- [Java SE 25 JLS `8.4.2 — Method Signature](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.2): vì sao `String[]` và `String...` không tạo hai overload khác nhau.

> **Ghi nhớ:** Java 25 chọn **candidate `main(String[])`/`main(String...)` trước `main()`**, bất kể `static` hay instance. Khi đã chọn instance method, launcher cần tạo instance của lớp khởi chạy bằng constructor không tham số; nếu thất bại, nó không chuyển sang overload khác.
