# Các phép gán trường được cho phép trước lời gọi constructor theo quy tắc hiện hành

## 1. Flexible Constructor Bodies giải quyết vấn đề gì?

Trong Java, một constructor của lớp con phải gọi constructor của lớp cha hoặc một constructor khác trong cùng lớp. Trước Java 25, lời gọi super(...) hoặc this(...) bắt buộc phải là câu lệnh đầu tiên trong thân constructor. Điều này gây bất tiện khi cần kiểm tra tham số, chuẩn hóa dữ liệu hoặc chuẩn bị giá trị trước khi chuyển chúng cho constructor cha.

Ví dụ, trước đây muốn kiểm tra một số dương trước khi gọi super(...), lập trình viên thường phải đặt logic kiểm tra vào một phương thức static rồi gọi phương thức đó ngay trong danh sách đối số của super(...). Cách làm này có thể khiến biểu thức gọi constructor dài và khó đọc.

Flexible Constructor Bodies cho phép viết các câu lệnh trước lời gọi constructor tường minh. Các câu lệnh này tạo thành *prologue* (phần mở đầu) của constructor. Sau lời gọi super(...) hoặc this(...) là *epilogue* (phần tiếp theo).

Điểm cần hiểu chính xác là prologue vẫn chạy khi đối tượng chưa hoàn tất quá trình khởi tạo. Java cho phép một ngoại lệ quan trọng: có thể gán một số field của chính lớp đang được tạo trước super(...), nhưng vẫn cấm đọc trạng thái instance hoặc gọi phương thức instance trong giai đoạn này.

## 2. Trạng thái tính năng trên JDK hiện hành

Flexible Constructor Bodies được giới thiệu ở Java 22 dưới dạng preview với JEP 447 (Statements before super(...)), tiếp tục preview ở Java 23 với JEP 482 và Java 24 với JEP 492. Tính năng trở thành ngôn ngữ chính thức từ Java 25 qua JEP 513, không còn yêu cầu bật preview.

Tại thời điểm biên soạn, JDK 27 đã GA ngày 15-09-2026 và là feature release mới nhất; JDK 25 là LTS mới nhất. JEP 513 và JEP 512 (Compact Source Files and Instance Main Methods) đều là tính năng final từ JDK 25. JEP 512 là tính năng độc lập, không phải điều kiện để sử dụng Flexible Constructor Bodies.

Các ví dụ trong bài dùng cú pháp stable của Java 25 trở lên. Không cần --enable-preview. Không sử dụng các bản preview cũ như cách triển khai hiện hành.

## 3. Cấu trúc constructor sau khi có Flexible Constructor Bodies

Khi constructor có lời gọi constructor tường minh, thân constructor có thể được chia thành ba phần:

~~~java
class Child extends Parent {
    Child(int value) {
        // Prologue: các câu lệnh trước lời gọi constructor
        int prepared = value * 2;

        super(prepared); // hoặc this(...)

        // Epilogue: các câu lệnh sau lời gọi constructor
        System.out.println("Child đã được khởi tạo");
    }
}
~~~

| Phần | Vị trí | Vai trò |
|---|---|---|
| Prologue | Trước super(...) hoặc this(...) | Kiểm tra tham số, tính toán dữ liệu, chuẩn bị đối số hoặc gán những field được phép. |
| Constructor invocation | super(...) hoặc this(...) | Gọi constructor của lớp cha hoặc constructor khác trong cùng lớp. |
| Epilogue | Sau lời gọi constructor | Thực hiện phần khởi tạo còn lại khi constructor được gọi đã hoàn tất bước chuyển tiếp. |

Mỗi constructor body có tối đa một constructor invocation tường minh. Một constructor chọn this(...) hoặc super(...), không gọi cả hai trong cùng thân constructor.

Với constructor của class thông thường, nếu không viết lời gọi tường minh, Java tự chèn lời gọi super() trước các câu lệnh trong thân constructor. Vì vậy, các câu lệnh trong constructor đó được xem là epilogue và chạy sau constructor cha. Muốn có prologue trước constructor cha, hãy viết super(...) tường minh ở vị trí phù hợp. Record có quy tắc constructor riêng, vì vậy không nên suy rộng quy tắc implicit super() này cho mọi dạng constructor.

## 4. Early Construction Context là gì?

Các biểu thức và câu lệnh trong prologue, cùng với các biểu thức đối số của super(...) hoặc this(...), nằm trong *early construction context* (ngữ cảnh khởi tạo sớm).

Ở thời điểm này:

- Đối tượng hiện tại đã được cấp phát bộ nhớ, nhưng constructor của lớp cha chưa hoàn tất.
- Các field instance có thể vẫn đang mang giá trị mặc định như 0, false hoặc null.
- Java chưa cho phép mã nguồn sử dụng tùy ý đối tượng đang được tạo.
- Một số phép gán field của chính lớp hiện tại được cho phép theo quy tắc riêng.

Sau khi lời gọi super(...) hoàn tất, Java mới chạy các field initializer và instance initializer của lớp hiện tại theo thứ tự khai báo. Sau đó, phần epilogue của constructor tiếp tục chạy. Với lời gọi this(...), constructor được ủy quyền sẽ chịu trách nhiệm tiếp tục chuỗi khởi tạo.

## 5. Những thao tác được phép trong prologue

Prologue có thể chứa các câu lệnh thông thường miễn là chúng không truy cập instance đang được tạo trái với quy tắc early construction context.

Các thao tác thường dùng:

- Đọc tham số constructor và biến cục bộ đã khai báo.
- Khai báo biến cục bộ và tính toán giá trị mới.
- Kiểm tra điều kiện bằng if, vòng lặp hoặc biểu thức.
- Ném exception nếu tham số không hợp lệ.
- Gọi phương thức static hoặc truy cập field static.
- Tạo đối tượng độc lập không cần instance đang được tạo làm enclosing instance.
- Gán một field instance của chính lớp đang được tạo nếu field đó được khai báo không có initializer, theo quy tắc ở mục tiếp theo.

Ví dụ kiểm tra tham số trước khi gọi constructor cha:

~~~java
import java.math.BigInteger;

public class PositiveBigInteger extends BigInteger {
    public PositiveBigInteger(long value) {
        if (value <= 0) {
            throw new IllegalArgumentException("value phải lớn hơn 0");
        }

        String decimalText = Long.toString(value);
        super(decimalText);
    }
}
~~~

if kiểm tra tham số trước khi gọi BigInteger(String). Biến decimalText được tạo trong prologue rồi dùng làm đối số cho super(...). Không cần bật preview trên JDK 25 hoặc JDK 27.

## 6. Quy tắc gán field trước super(...)

Đây là phần quan trọng nhất của Flexible Constructor Bodies. Trong early construction context, Java cho phép gán field instance thuộc chính lớp đang được tạo nếu đáp ứng các điều kiện:

1. Field được khai báo trong lớp hiện tại, không phải field kế thừa từ superclass.
2. Field không có field initializer trong khai báo.
3. Biểu thức sử dụng field chỉ xuất hiện ở vế trái của phép gán đơn =.
4. Phép gán không nằm bên trong lambda hoặc khai báo inner class được lồng trong early construction context.
5. Nếu field là final, các quy tắc definite assignment vẫn phải được đáp ứng: field phải chưa được gán trước đó và chỉ được gán đúng một lần trên mỗi đường thực thi hợp lệ.

Ví dụ hợp lệ:

~~~java
class Parent {
    Parent() {
        printState();
    }

    void printState() {
        System.out.println("Parent constructor");
    }
}

class Child extends Parent {
    private final int id; // Blank final field: không có initializer

    Child(int id) {
        if (id <= 0) {
            throw new IllegalArgumentException("id phải lớn hơn 0");
        }

        this.id = id; // Được phép: gán field của Child trước super()
        super();
    }

    @Override
    void printState() {
        System.out.println("Child id = " + id);
    }
}
~~~

Khi tạo new Child(42), prologue gán id = 42 trước khi Parent() chạy. Constructor Parent gọi phương thức printState() được override trong Child, và phương thức này nhìn thấy giá trị 42 thay vì giá trị mặc định 0.

Ví dụ này cũng cho thấy vì sao tính năng hữu ích: constructor lớp cha đôi khi gọi một phương thức instance có thể bị override. Trước Java 25, phương thức override có thể đọc field của lớp con khi field đó vẫn chưa được gán.

### 6.1. Có thể dùng tên field không cần this không?

Có thể dùng tên field ở vế trái phép gán đơn nếu tên đó được phân giải thành field instance của lớp hiện tại và không bị tham số hoặc biến cục bộ che khuất:

~~~java
class Child extends Parent {
    private int code;

    Child(int code) {
        this.code = code; // Rõ ràng đây là field
        super();
    }
}
~~~

Nếu bỏ this trong ví dụ trên, code = code sẽ chỉ gán tham số cho chính nó vì tham số constructor che khuất field. Vì vậy, nên dùng this.field = parameter để biểu đạt rõ mục đích. Trong trường hợp này, this chỉ được dùng làm qualifier của field assignment được cho phép.

### 6.2. Field có initializer không được gán trong prologue

Field có initializer không thuộc nhóm field được phép gán trước lời gọi constructor:

~~~java
class Child extends Parent {
    private int status = 1;

    Child(int status) {
        // this.status = status; // Compile-time error trong prologue
        super();
    }
}
~~~

Ngoài quy tắc ngôn ngữ, thứ tự khởi tạo cũng giải thích giới hạn này: field initializer và instance initializer của Child chạy sau khi constructor cha hoàn tất. Nếu field có initializer được gán sớm, initializer sau đó có thể ghi đè giá trị.

Nếu cần truyền một giá trị tính toán vào constructor cha, hãy lưu nó trong biến cục bộ rồi dùng làm đối số super(...). Nếu cần khởi tạo field có initializer, hãy thực hiện sau super(...) trong epilogue hoặc thiết kế lại initializer.

### 6.3. Không được đọc field trước super(...)

Quyền gán field không đồng nghĩa với quyền đọc field. Những biểu thức sau không hợp lệ trong prologue:

~~~java
class Child extends Parent {
    private int count;

    Child(int initial) {
        // System.out.println(count); // Lỗi: đọc field instance
        // int next = this.count + 1;  // Lỗi: đọc field instance
        // count++;                   // Lỗi: đọc rồi ghi field
        // count += initial;          // Lỗi: phép gán kết hợp cần đọc giá trị cũ

        count = initial;              // Hợp lệ nếu count không có initializer
        super();
    }
}
~~~

Chỉ phép gán đơn vào field hợp lệ mới được cho phép. Các phép tăng/giảm, compound assignment (+=, -=, *=, ...) hoặc biểu thức đọc field ở vế phải đều cần giá trị hiện tại nên không hợp lệ.

## 7. Những thao tác bị cấm trong early construction context

Java vẫn bảo vệ đối tượng đang được tạo bằng cách hạn chế việc truy cập instance:

| Thao tác | Hợp lệ? | Lý do |
|---|---|---|
| Đọc tham số constructor | Có | Tham số đã có giá trị trước khi constructor chạy. |
| Gọi phương thức static | Có | Không cần instance hiện tại. |
| Đọc field static | Có | Field thuộc lớp, không thuộc instance đang tạo. |
| Gọi phương thức instance của lớp hiện tại | Không | Phương thức có thể đọc trạng thái instance chưa hoàn chỉnh. |
| Dùng this như một giá trị | Không | Không được tham chiếu instance đang tạo trước constructor invocation. |
| Đọc this.field | Không | Field có thể chưa được khởi tạo. |
| Đọc field kế thừa qua tên đơn hoặc super.field | Không | Không được đọc field instance của đối tượng hiện tại trong early context. |
| Gọi super.method() hoặc dùng method reference qua super | Không | Truy cập hành vi instance của superclass. |
| Gán đơn this.field = value cho field đủ điều kiện | Có | Đây là ngoại lệ được đặc tả cho việc khởi tạo sớm field của lớp hiện tại. |
| Tạo inner class cần instance của lớp đang tạo làm enclosing instance | Không | Việc tạo inner class cần tham chiếu instance chưa hoàn tất. |

Ví dụ không hợp lệ:

~~~java
class Child extends Parent {
    private int value;

    Child(int initialValue) {
        // System.out.println(this.value); // Lỗi: đọc field instance
        // this.toString();                // Lỗi: gọi instance method
        // printValue();                   // Lỗi: gọi instance method
        // System.out.println(this);       // Lỗi: dùng this như một giá trị
        this.value = initialValue;         // Gán field được phép
        super();
    }

    private void printValue() {
        System.out.println(value);
    }
}
~~~

Để tránh nhầm lẫn do trùng tên, có thể đổi tên tham số thành initialValue. Khi đó, việc đọc tham số và gán field được thể hiện rõ:

~~~java
Child(int initialValue) {
    this.value = initialValue;
    super();
}
~~~

## 8. Vì sao gán field trước constructor cha hữu ích?

Một constructor cha có thể gọi một phương thức instance được override trong lớp con. Đây là hành vi cần tránh trong thiết kế constructor nói chung, vì lớp con chưa hoàn tất khởi tạo khi constructor cha chạy.

Trước Java 25, field của lớp con chỉ được gán sau khi super() hoàn tất:

~~~java
class Parent {
    Parent() {
        display();
    }

    void display() {
        System.out.println("Parent");
    }
}

class Child extends Parent {
    private final int number;

    Child(int number) {
        super();          // Parent gọi display() khi number vẫn bằng 0
        this.number = number;
    }

    @Override
    void display() {
        System.out.println(number);
    }
}
~~~

Khi tạo new Child(42), Parent() gọi Child.display() trước khi câu lệnh this.number = number chạy. Kết quả in ra là 0, giá trị mặc định của int.

Từ Java 25, có thể gán field trước super():

~~~java
class Child extends Parent {
    private final int number;

    Child(int number) {
        this.number = number;
        super();
    }

    @Override
    void display() {
        System.out.println(number);
    }
}
~~~

Kết quả là 42, vì field đã được gán trước khi constructor cha gọi phương thức override.

Tuy nhiên, Flexible Constructor Bodies không biến việc gọi phương thức override trong constructor thành một thực hành tốt. Nếu có thể, hãy tránh gọi phương thức có thể bị override trong constructor cha. Việc gán sớm chỉ giải quyết những field được chuẩn bị rõ ràng; phương thức override vẫn có thể truy cập những field khác chưa được khởi tạo hoặc gọi các phương thức khác phụ thuộc vào trạng thái chưa hoàn chỉnh.

## 9. Dùng prologue trước this(...) để ủy quyền constructor

Flexible Constructor Bodies cũng cho phép đặt câu lệnh trước lời gọi this(...), tức lời gọi một constructor khác trong cùng lớp. Trường hợp thường gặp là chuẩn hóa và xác thực tham số trước khi ủy quyền:

~~~java
class Account {
    private final String owner;
    private final long creditLimit;

    Account(String rawOwner) {
        String normalizedOwner =
                rawOwner == null ? "" : rawOwner.strip();

        if (normalizedOwner.isEmpty()) {
            throw new IllegalArgumentException("owner không được rỗng");
        }

        this(normalizedOwner, 0L);
    }

    private Account(String owner, long creditLimit) {
        this.owner = owner;
        this.creditLimit = creditLimit;
    }
}
~~~

Constructor đầu tiên thực hiện xác thực trong prologue rồi gọi constructor thứ hai bằng this(...). Constructor đích chịu trách nhiệm gán các field. Cách này giúp mọi constructor dùng chung một đường khởi tạo chuẩn.

Nếu constructor ủy quyền bằng this(...), không được tự gán blank final field trước lời gọi đó. Theo quy tắc definite assignment, blank final field của lớp phải vẫn chưa được gán khi alternate constructor invocation được thực hiện; constructor đích là nơi chịu trách nhiệm hoàn tất phép gán final.

## 10. Những lưu ý về thứ tự khởi tạo và field final

Với constructor gọi super(...), thứ tự khái quát là:

1. Cấp phát bộ nhớ cho đối tượng; field instance bắt đầu với giá trị mặc định.
2. Chạy các câu lệnh prologue.
3. Đánh giá đối số và gọi constructor của superclass.
4. Khi constructor superclass hoàn tất, chạy field initializer và instance initializer của lớp hiện tại theo thứ tự khai báo.
5. Chạy epilogue của constructor hiện tại.

Với constructor gọi this(...), constructor được ủy quyền tiếp tục quá trình khởi tạo. Các field initializer của lớp hiện tại chỉ chạy trong đường constructor cuối cùng gọi super(...), không chạy lại cho mỗi lần ủy quyền this(...).

Đối với blank final field:

- Có thể gán trước super(...) nếu field được khai báo trong lớp hiện tại và không có initializer.
- Không được đọc field trước lời gọi constructor.
- Phải bảo đảm field được gán đúng một lần trên mọi đường thực thi hoàn tất bình thường.
- Không gán field trước this(...) vì constructor được ủy quyền phải chịu trách nhiệm gán field đó.

Đối với field có initializer:

- Không thể gán field đó trong prologue.
- Field initializer chạy sau constructor cha.
- Nếu muốn giá trị phụ thuộc tham số constructor, hãy thiết kế field không có initializer rồi gán ở vị trí hợp lệ, hoặc tính giá trị trong prologue và dùng sau super(...).

## 11. Những lỗi thường gặp

1. **Đặt câu lệnh trước super() nhưng lại đọc field instance.** Prologue không cho phép đọc field của instance đang tạo.
2. **Gọi phương thức instance trong prologue.** Phương thức có thể quan sát trạng thái chưa hoàn chỉnh; hãy chuyển logic sang static helper hoặc xử lý sau constructor invocation.
3. **Gán field có initializer trước super().** Chỉ field được khai báo không có initializer mới thuộc ngoại lệ gán sớm.
4. **Dùng +=, ++ hoặc -- để cập nhật field.** Các phép này đọc giá trị hiện tại, nên không hợp lệ trong early context.
5. **Gán field của superclass.** Ngoại lệ chỉ cho phép gán field được khai báo trong lớp đang được tạo.
6. **Quên viết super() tường minh.** Nếu không có this(...) hoặc super(...) tường minh, Java chèn super() trước các câu lệnh trong thân constructor; chúng không trở thành prologue.
7. **Gán blank final field trước this(...).** Constructor được ủy quyền phải chịu trách nhiệm gán field đó.
8. **Cho rằng có thể truyền this vào super(...).** Đối số constructor cũng thuộc early construction context; không được làm lộ instance đang tạo.

## 12. Kiểm tra phiên bản và biên dịch

Flexible Constructor Bodies là ngôn ngữ final từ Java 25. Có thể biên dịch ví dụ theo mức tương thích Java 25 bằng:

~~~bash
javac --release 25 FlexibleConstructorDemo.java
~~~

Hoặc chạy source file bằng JDK 25 trở lên mà không bật preview:

~~~bash
java --source 25 FlexibleConstructorDemo.java
~~~

Nếu dự án dùng JDK 27 nhưng muốn giới hạn mã nguồn theo Java 25, có thể dùng --release 25 khi biên dịch. JVM vẫn là JDK 27, còn cú pháp và API nền tảng được giới hạn theo release 25.

JDK 27 có các preview feature độc lập với Flexible Constructor Bodies. Về ngôn ngữ, JEP 532 (Primitive Types in Patterns, instanceof, and switch) là preview lần thứ năm trong JDK 27. Về thư viện, JEP 531 (Lazy Constants) là preview lần thứ ba, JEP 533 (Structured Concurrency) là preview lần thứ bảy và JEP 538 (PEM Encodings of Cryptographic Objects) là preview lần thứ ba. Các preview này không cần thiết cho bài học này.

Khi chủ động thử preview feature của JDK 27, phải bật preview ở cả compile time và run time, đồng thời biên dịch theo release 27:

~~~bash
javac --enable-preview --release 27 PreviewExample.java
java --enable-preview PreviewExample
~~~

Không thể dùng --enable-preview của JDK 27 để bật lại preview feature của JDK 22, 23 hoặc 24. Các preview cũ chỉ có hiệu lực trên đúng JDK release đã giới thiệu chúng.

JDK 27 còn có Vector API (JEP 537, lần incubator thứ mười hai). Đây là API incubator, không phải preview; chương trình sử dụng module này cần thêm --add-modules jdk.incubator.vector khi biên dịch và chạy. Bài học Flexible Constructor Bodies không dùng Vector API.

## 13. Tài liệu tham khảo

- [JEP 513: Flexible Constructor Bodies](https://openjdk.org/jeps/513) — đặc tả tính năng final từ Java 25.
- [JEP 447: Statements before super(...) (Preview)](https://openjdk.org/jeps/447) — lần preview đầu tiên trong Java 22.
- [JEP 482: Flexible Constructor Bodies (Second Preview)](https://openjdk.org/jeps/482) — vòng preview Java 23.
- [JEP 492: Flexible Constructor Bodies (Third Preview)](https://openjdk.org/jeps/492) — vòng preview Java 24.
- [Oracle Java SE 27: Flexible Constructor Bodies](https://docs.oracle.com/en/java/javase/27/language/flexible-constructor-bodies.html) — ví dụ hiện hành về prologue, early construction context và gán field trước super(...).
- [Java SE 27 JLS, §8.8.7 Constructor Body](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.8.7) — định nghĩa prologue, epilogue và early construction context.
- [Java SE 27 JLS, §6.5.6.1 Simple Expression Names](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-6.html#jls-6.5.6.1) — giới hạn truy cập và gán instance field trong early construction context.
- [Oracle Java SE 27: Java Language Changes by Release](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html) — trạng thái preview/final theo từng phiên bản Java.
- [Oracle: Significant Changes in JDK 27](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html) — danh sách preview API, preview ngôn ngữ và incubator của JDK 27.
- [Oracle: Java 27 Release Announcement](https://www.oracle.com/news/announcement/oracle-releases-java-27-and-strengthens-post-quantum-cryptography-support-2026-09-15/) — ngày phát hành GA của JDK 27.
