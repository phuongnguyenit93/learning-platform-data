# Khai báo khác với câu lệnh thực thi trong Java

Trong một tệp Java, có những dòng **giới thiệu cấu trúc hoặc tên** cho trình biên dịch, và có những dòng **tạo ra hành động khi chương trình chạy**. Phân biệt hai vai trò này giúp bạn giải thích vì sao một phương thức đã viết nhưng chưa in gì, hoặc vì sao khai báo biến có dấu `=` lại tạo hiệu ứng khi chương trình thực thi.

Ví dụ:

~~~java
int score;                  // Khai báo biến cục bộ.
score = 8;                  // Gán giá trị khi câu lệnh được thực thi.
System.out.println(score); // Thực thi lệnh gọi phương thức: in 8.
~~~

Ba dòng trên phải đặt **bên trong phương thức, constructor hoặc khối phù hợp**. Khai báo `score` xác định một tên và kiểu; phép gán đặt giá trị; `println` in dữ liệu.

Điểm cần nhớ từ đầu: **“khai báo” và “câu lệnh” không phải lúc nào cũng là hai loại cú pháp loại trừ nhau**. `int score = 8;` vừa là một *local variable declaration statement* theo ngữ pháp Java, vừa chứa biểu thức khởi tạo `8`, được đánh giá khi luồng thực thi tới dòng này.

## 1. Nhìn một tệp Java: phần nào khai báo, phần nào chạy?

Xem chương trình rút gọn:

~~~java
public class Example {
    static int limit = 10;           // Khai báo field kèm khởi tạo.

    static void greet() {            // Khai báo phương thức.
        System.out.println("Hello"); // Lệnh trong phần thân.
    }

    public static void main(String[] args) {
        int count = 2;               // Khai báo biến cục bộ có khởi tạo.
        if (count > 0) {             // Câu lệnh rẽ nhánh.
            greet();                 // Lệnh gọi phương thức.
        }
    }
}
~~~

Khi chạy `Example`, trình biên dịch đã biết có lớp `Example` và phương thức `greet`. Nhưng thân `greet` chỉ chạy vì `main` **gọi** `greet()`.

| Cấu trúc | Vai trò chính | Có tự in/chạy phần thân ngay chỉ vì được khai báo? |
| --- | --- | --- |
| `class Example { ... }` | Khai báo kiểu/lớp | Không; mã khởi tạo lớp là chuyện riêng |
| `static void greet() { ... }` | Khai báo phương thức và thân có thể được gọi | Không; phải có lời gọi hoặc cơ chế phù hợp kích hoạt |
| `int count;` trong phương thức | Khai báo biến cục bộ | Không có biểu thức khởi tạo để tính tại dòng đó |
| `int count = calculate();` | Khai báo biến cục bộ **kèm khởi tạo** | Có; `calculate()` được gọi khi tới dòng |
| `count = 5;` | Câu lệnh biểu thức gán | Có; gán giá trị khi tới dòng |
| `System.out.println(count);` | Câu lệnh gọi phương thức | Có; gọi phương thức khi tới dòng |
| `if`, `for`, `while` | Câu lệnh điều khiển | Có; đánh giá điều kiện và quyết định phần mã nào chạy |
| `import java.util.List;` | Khai báo nhập tên kiểu cho mã nguồn | Không tự tải dữ liệu hay gọi `List` |

Trong Java 17, nội dung ở cấp thân lớp không được tùy ý đặt câu lệnh như `System.out.println(...)` đứng một mình. Câu lệnh thông thường thuộc thân phương thức, constructor hoặc **khối khởi tạo** hợp lệ.

## 2. Chương trình đầy đủ: xem thứ tự thực thi

Tạo tệp **`DeclarationDemo.java`** đúng tên sau:

~~~java
public class DeclarationDemo {
    // Khai báo static field, có biểu thức khởi tạo.
    static int classValue = trace("1. static field", 10);

    static {
        System.out.println("2. static initializer");
    }

    // Khai báo instance field, khởi tạo khi tạo đối tượng.
    int objectValue = trace("5. instance field", 20);

    {
        System.out.println("6. instance initializer");
    }

    DeclarationDemo() {
        System.out.println("7. constructor");
    }

    // Chỉ khai báo phương thức không làm nó tự chạy.
    static int trace(String label, int value) {
        System.out.println(label);
        return value;
    }

    void greet() {
        System.out.println("8. greet method");
    }

    static void neverCalled() {
        System.out.println("KHONG DUOC IN");
    }

    public static void main(String[] args) {
        System.out.println("3. main begins");

        int count; // Biến cục bộ được khai báo nhưng chưa có giá trị.
        count = 2; // Lệnh gán thực thi tại đây.
        System.out.println("4. count=" + count);

        DeclarationDemo demo = new DeclarationDemo();
        demo.greet();
    }
}
~~~

**Lệnh chạy trên Windows PowerShell hoặc Linux/Bash** (terminal đặt trong thư mục chứa tệp):

~~~bash
javac -encoding UTF-8 DeclarationDemo.java
java DeclarationDemo
~~~

Kết quả mong đợi:

~~~text
1. static field
2. static initializer
3. main begins
4. count=2
5. instance field
6. instance initializer
7. constructor
8. greet method
~~~

Không có dòng `KHONG DUOC IN` vì phương thức `neverCalled` **được khai báo nhưng không được gọi**.

### Phân tích thứ tự in

1. Trước khi gọi `main`, JVM khởi tạo lớp `DeclarationDemo`. Bộ khởi tạo static field `classValue` gọi `trace` và in dòng 1.
2. Khối `static { ... }` chạy sau đó, in dòng 2. Các phần khởi tạo static được xử lý theo **thứ tự văn bản** trong lớp.
3. Launcher gọi `main`; dòng 3 được in.
4. Khai báo `int count;` **chưa gán giá trị**. Dòng `count = 2;` gán 2, sau đó in dòng 4.
5. Biểu thức `new DeclarationDemo()` tạo đối tượng mới. Field khởi tạo cho từng instance gọi `trace` và in dòng 5.
6. Khối khởi tạo instance in dòng 6, rồi phần thân constructor in dòng 7.
7. Lời gọi `demo.greet()` thực thi phương thức `greet` và in dòng 8.

**Giới hạn của ví dụ:** thứ tự trên áp dụng cho một lớp trực tiếp kế thừa `Object` như `DeclarationDemo`. Với lớp con, còn có bước khởi tạo của superclass; không nên suy rộng thứ tự trên thành mô tả đầy đủ mọi hệ phân cấp lớp.

Có thể chạy trực tiếp nguồn bằng JDK 17+:

~~~bash
java DeclarationDemo.java
~~~

Kết quả tương tự. Với chế độ chạy nguồn trực tiếp, launcher thực hiện biên dịch trong bộ nhớ; nếu dùng `javac` trước, tệp `DeclarationDemo.class` được tạo trên đĩa. Hai cách chạy này đều phù hợp để kiểm tra bài.

## 3. Khai báo biến có hoặc không có biểu thức khởi tạo

So sánh:

~~~java
int a;              // Khai báo biến cục bộ, chưa có giá trị để đọc.
a = 5;              // Gán giá trị.
int b = a * 2;      // Khai báo + đánh giá biểu thức khởi tạo.
System.out.println(b); // In 10.
~~~

Một cách đọc hữu ích:

- `int a;`: “Từ đây tồn tại tên `a` có kiểu `int` trong phạm vi phù hợp.”
- `a = 5;`: “Đặt giá trị của `a` thành 5.”
- `int b = a * 2;`: “Tạo tên `b` có kiểu `int`, **tính `a * 2` ở thời điểm thực thi dòng này** rồi gán kết quả.”
- `println`: “Gọi một phương thức thực hiện xuất dữ liệu.”

Lệnh `int b = a * 2;` không được trình biên dịch “chạy trước” để làm sẵn kết quả trong mọi hoàn cảnh. Nếu `a` thay đổi trước khi tới dòng này, kết quả khởi tạo `b` cũng thay đổi tương ứng.

### Khai báo không đồng nghĩa biến đã sẵn sàng được đọc

Đoạn sau **không biên dịch**:

~~~java
public class UnassignedLocal {
    public static void main(String[] args) {
        int amount;
        // System.out.println(amount); // Nếu bỏ // sẽ lỗi.
        amount = 10;
        System.out.println(amount);
    }
}
~~~

Java áp dụng quy tắc **definite assignment**: biến cục bộ phải được gán chắc chắn trước khi đọc. Việc có một khai báo tên biến **không tự gán mặc định 0** cho biến cục bộ. Trái lại, field `int` không được khởi tạo tường minh sẽ nhận giá trị mặc định 0 khi đối tượng/lớp được khởi tạo theo quy tắc Java.

### Biểu thức trong khai báo có thể gây tác dụng phụ

~~~java
static int nextValue() {
    System.out.println("Tinh gia tri");
    return 7;
}

// Đặt các câu lệnh sau bên trong một phương thức:
int first = nextValue();  // In "Tinh gia tri" khi chạy đến đây.
int second = 9;           // Gán giá trị, không tự in gì.
~~~

Lời gọi `nextValue()` là một **biểu thức** nằm trong khai báo biến; khi tới dòng khởi tạo, biểu thức được đánh giá, kể cả tác dụng phụ của nó. Vì vậy, đừng kết luận “dòng có `int` chỉ là khai báo nên không thực thi gì”.

## 4. Phương thức được khai báo không có nghĩa được gọi

Ví dụ:

~~~java
public class MethodDeclaration {
    static void sayHello() {
        System.out.println("Xin chao");
    }

    public static void main(String[] args) {
        System.out.println("Bat dau");
        // sayHello();
        System.out.println("Ket thuc");
    }
}
~~~

Chạy:

~~~bash
javac MethodDeclaration.java
java MethodDeclaration
~~~

Đầu ra:

~~~text
Bat dau
Ket thuc
~~~

Nếu bỏ dấu chú thích ở `sayHello();`, dòng `Xin chao` xuất hiện **giữa** hai dòng trên. Trong Java, **tên phương thức + chữ ký + phần thân** định nghĩa nó sẽ làm gì *khi được gọi*, không khiến nó tự gọi trong quá trình biên dịch.

Đây cũng là lý do có thể viết nhiều helper method trong một lớp nhưng chỉ một số helper được sử dụng ở một lần chạy cụ thể.

## 5. Vị trí được phép khai báo và vị trí thực thi

| Vị trí trong tệp/lớp Java | Có thể chứa gì? | Chú ý |
| --- | --- | --- |
| Cấp tệp nguồn | `package`, `import` và khai báo kiểu top-level | Không đặt `System.out.println(...)` tùy ý trực tiếp ở đây |
| Thân lớp | Field, constructor, phương thức, nested type, khối khởi tạo | Không đặt một assignment statement hay method call đứng lẻ ngoài khối |
| Thân phương thức | Local variable declaration statements, biểu thức statement, `if`, `for`, `return`... | Thực thi theo luồng điều khiển |
| Constructor | Câu lệnh và các khai báo cục bộ hợp lệ | Chạy khi tạo đối tượng, trong trình tự khởi tạo |
| Khối `static { ... }` | Các câu lệnh khởi tạo lớp | Chạy khi lớp được khởi tạo, không phải mỗi lần tạo đối tượng |
| Khối `{ ... }` trong thân lớp | Các câu lệnh khởi tạo instance | Chạy khi tạo mỗi instance trong trình tự thích hợp |

**Lỗi sai vị trí điển hình:**

~~~java
public class WrongPlacement {
    // System.out.println("Hello"); // Sai nếu bỏ //:
    // câu lệnh gọi phương thức không được đứng lẻ trong thân lớp.

    public static void main(String[] args) {
        System.out.println("Hello"); // Đúng: nằm trong phương thức.
    }
}
~~~

Đừng nhầm dấu ngoặc `{}` trong khai báo lớp với khối phương thức. Không phải mọi câu lệnh hợp lệ bên trong `main` đều được phép chuyển ra trực tiếp cấp lớp.

## 6. Một biểu thức chưa chắc là câu lệnh hợp lệ

Ở Java, các dạng như phép gán, tăng/giảm, lời gọi phương thức và tạo đối tượng có thể xuất hiện như **expression statement**:

~~~java
int n = 2;
n = n + 1;
n++;
System.out.println(n); // 4
new StringBuilder("text");
~~~

Dòng `new StringBuilder("text");` tạo một đối tượng rồi bỏ tham chiếu; hợp lệ về cú pháp dù ít giá trị sử dụng. Ngược lại, không phải mọi biểu thức tính ra giá trị đều được viết một mình thành câu lệnh:

~~~java
// n + 1; // Sai: không phải statement expression hợp lệ.
~~~

Khi mới học, một câu hỏi hữu ích là: “Dòng này **khai báo gì**, **tính/gán gì**, **gọi gì**, hoặc **điều khiển luồng** thế nào?” Điều đó chính xác hơn việc chỉ nhìn dấu `;` và kết luận mọi dòng giống nhau.

## 7. Những lỗi thường gặp và cách phân biệt

| Mã/tình huống | Kết quả | Giải thích |
| --- | --- | --- |
| `int n; System.out.println(n);` trong phương thức | Lỗi biên dịch | Biến cục bộ chưa được gán chắc chắn |
| Khai báo `void work()` nhưng không gọi | Không in gì từ thân method | Method chỉ được định nghĩa, chưa thực thi |
| `int n = read();` | Gọi `read()` khi tới dòng | Initializer là biểu thức chạy |
| Đặt `System.out.println("Hi");` trực tiếp trong thân lớp | Lỗi biên dịch | Không phải khai báo thành viên/khối khởi tạo phù hợp |
| `static int x = trace(...);` | Có thể gây xuất dữ liệu trong khởi tạo lớp | Field initializer được đánh giá theo trình tự khởi tạo |
| `int n = 2;` ở trong `if` không được chọn | Không thực thi initializer đó | Luồng chạy không đi vào nhánh |
| `n + 1;` đứng một mình | Lỗi biên dịch | Không phải expression statement hợp lệ |

**Câu hỏi “khi nào chạy?” phụ thuộc vào vị trí và luồng điều khiển**. Một khối phương thức không tự chạy do tồn tại trong mã nguồn; một field initializer có thể chạy trong khởi tạo đối tượng/lớp; một local initializer chỉ chạy khi luồng tới nó.

## 8. Bài tập tự kiểm tra

**Bài 1 — Dự đoán kết quả.** Đoạn sau in gì?

~~~java
public class OrderDemo {
    static void later() {
        System.out.println("B");
    }

    public static void main(String[] args) {
        System.out.println("A");
        later();
        System.out.println("C");
    }
}
~~~

*Đáp án:* `A`, `B`, `C` trên ba dòng. Thân `later` chạy tại lời gọi giữa hai câu in.

**Bài 2 — Tìm chỗ sai.** Cho:

~~~java
public class ScopeDemo {
    public static void main(String[] args) {
        int score;
        // System.out.println(score);
    }
}
~~~

Tại sao bỏ `//` trước `println` sẽ làm `javac` báo lỗi? Hãy sửa bằng cách gán `score = 10;` trước lời gọi. Sau khi sửa, dự đoán giá trị in ra.

*Đáp án:* Biến cục bộ chưa được gán chắc chắn; sau khi gán, in `10`.

**Bài 3 — Một dòng vừa khai báo vừa thực thi.**

~~~java
int value = Integer.parseInt("21");
~~~

Đâu là phần khai báo? Phần nào được thực thi khi dòng này được chạy? Nếu đổi chuỗi thành `"hai muoi mot"` thì điều gì xảy ra?

*Đáp án:* `int value` khai báo tên/kiểu. `Integer.parseInt(...)` được gọi lúc chạy; chuỗi không hợp lệ gây `NumberFormatException`.

**Bài 4 — Khối nào chạy?** Trong chương trình `DeclarationDemo`, thử bỏ lời gọi `demo.greet();`. Dòng in số 8 còn xuất hiện không? Các dòng khởi tạo instance 5–7 còn xuất hiện không?

*Đáp án:* Không còn số 8; các dòng 5–7 vẫn in vì `new DeclarationDemo()` còn được thực thi.

**Bài 5 — Luyện nhận diện.** Hãy phân loại trong ví dụ sau: khai báo kiểu, khai báo phương thức, khai báo biến có khởi tạo, phép gán và câu lệnh điều kiện.

~~~java
class Sample {
    static boolean enough(int n) {
        int limit = 5;
        n = n + 1;
        if (n >= limit) {
            return true;
        }
        return false;
    }
}
~~~

*Gợi ý:* `class Sample` khai báo kiểu; `enough` khai báo phương thức; `int limit = 5;` vừa khai báo local vừa khởi tạo; `n = n + 1;` là phép gán; `if` chọn nhánh.

## Checklist ghi nhớ

- [ ] Phân biệt khai báo lớp, field và phương thức với hành động khi thực thi.
- [ ] Hiểu rằng local variable declaration **là một dạng statement** trong Java, và initializer của nó được tính khi luồng tới dòng.
- [ ] Không đọc biến cục bộ trước khi chắc chắn đã gán.
- [ ] Dự đoán thứ tự static initialization, instance initialization, constructor, `main` và lời gọi helper qua ví dụ cụ thể.
- [ ] Biết phương thức đã khai báo nhưng không gọi sẽ không tự in output.
- [ ] Không đặt method invocation đứng lẻ ở thân lớp.
- [ ] Biết không phải mọi expression đều có thể đứng một mình thành statement.
- [ ] Chạy được `javac DeclarationDemo.java` và `java DeclarationDemo`, đối chiếu đủ tám dòng kết quả.

**Ghi nhớ:** Trong Java, **khai báo** giúp chương trình định nghĩa tên, kiểu và cấu trúc; **thực thi** đánh giá biểu thức và câu lệnh theo luồng chạy. Một khai báo có thể chứa initializer có hiệu ứng khi chạy, nên hai khái niệm liên quan nhưng **không hoàn toàn đối lập**. Hãy hỏi: “Dòng này khai báo điều gì, và phần nào thực sự được đánh giá khi chương trình tới đó?”
