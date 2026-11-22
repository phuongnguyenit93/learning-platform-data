# Giới hạn tham chiếu trước trong biểu thức và khối khởi tạo Java

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **phạm vi tên** của field với **thời điểm field nhận giá trị khởi tạo**; hiểu tại sao field được khai báo phía dưới có thể đang nằm trong scope nhưng vẫn bị báo `illegal forward reference`.
- Áp dụng đúng quy tắc **JLS §8.3.3 — Restrictions on Field References in Initializers** cho static field initializers, `static { ... }`, instance field initializers và instance initializer blocks `{ ... }`.
- Nhận biết những điều kiện phối hợp khiến một **lần đọc bằng tên đơn giản** ở phía trước khai báo hoặc ngay trong initializer của chính field đó trở thành compile-time error.
- Phân biệt **đọc giá trị** với **gán vào vế trái** của một assignment, cũng như `x = 2` với `x += 2` và `x++`.
- Giải thích tại sao `ClassName.field` hoặc `this.field` có thể qua được kiểm tra *simple-name forward reference*, nhưng vẫn thấy **giá trị mặc định** nếu initializer đích chưa chạy.
- Hiểu tại sao **gọi method** để đọc field phía sau không tự bị kiểm tra cùng cách, nhưng có thể dẫn đến dữ liệu chưa hoàn chỉnh.
- Dự đoán thứ tự static và instance initializers, quan hệ với constructors, compile-time constant variables, inherited fields và dependency cycles.
- Viết lại các trường hợp nguy hiểm bằng **sắp xếp phụ thuộc trước**, **giá trị ứng viên** và **factory/constructor** rõ ràng, thay vì cố “lách” compiler.
- Chạy các ví dụ Java 17+ độc lập, xác định output và tìm nguyên nhân của lỗi khởi tạo.

## 1. “Tham chiếu trước” là gì?

Xem đoạn khai báo:

~~~java
class Sample {
    int first = later;
    int later = 10;
}
~~~

Đây là **ví dụ cố ý sai**, không phải chương trình runnable. Trong `first = later`, tên `later` xuất hiện trong một **instance field initializer** ở bên trái vị trí khai báo field `later`. Compiler Java báo lỗi kiểu `illegal forward reference`.

Nhiều người nghĩ: “Lớp Sample có field later rồi, sao không được dùng?” Cần phân biệt:

1. **Scope:** tên của một member được khai báo trong class có phạm vi theo class body. Nói đơn giản, compiler biết class có field `later`.
2. **Restrictions on forward references:** Java **cấm một số dạng đọc field quá sớm** ngay trong field initializers hoặc initializer blocks thuộc chính class.
3. **Initialization order:** lúc chương trình chạy, fields có **giá trị mặc định** trước khi initializer tương ứng gán giá trị cuối; thứ tự khai báo ảnh hưởng giá trị quan sát được.

Vì thế “compiler nhận ra field tồn tại” **không đồng nghĩa** “mọi biểu thức dùng field ấy đều hợp lệ” và càng không đồng nghĩa “field đã mang giá trị mong muốn”.

### 1.1. Hai điều cần phân biệt

| Tình huống | Kết luận |
| --- | --- |
| `int a = b; int b = 10;` trong cùng class | **Lỗi**: đọc instance field `b` bằng tên đơn giản quá sớm |
| `static int a = b; static int b = 10;` trong cùng class | **Lỗi**: đọc static field `b` bằng tên đơn giản quá sớm |
| `int a = this.b; int b = 10;` | Có thể **biên dịch**, nhưng `a` có thể nhận `0` |
| `static int a = Sample.b; static int b = 10;` | Có thể **biên dịch**, nhưng `a` có thể nhận `0` |
| `int a = readB(); int b = 10;`, method `readB()` trả `b` | Có thể biên dịch; lúc gọi sớm có thể trả `0` |
| `static { b = 4; } static int b = 10;` | Phép gán vào `b` hợp lệ, nhưng initializer phía sau ghi đè thành `10` |
| `int a = 10; int b = a;` | Hợp lệ: đọc field đã xuất hiện trước |
| Constructor đọc field khai báo phía sau | Không thuộc đúng phép kiểm tra `8.3.3` dành cho field/instance initializers; runtime order vẫn quan trọng |

Bảng nêu **dạng sử dụng và context cụ thể**. Những mã minh họa được đánh dấu sai có thể không compile; các trường hợp hợp lệ vẫn phải thỏa typing, access, definite assignment và quy tắc khác của Java.

## 2. Java thực thi field initializer và initializer blocks ra sao?

Một class có thể khai báo:

- **Static field initializer**: `static int x = expression;`.
- **Static initializer block**: `static { statements; }`.
- **Instance field initializer**: `int y = expression;`.
- **Instance initializer block**: `{ statements; }`.
- **Constructor**: `Sample() { statements; }`.

**Static initializers** được thực thi khi runtime class được initialized, theo **thứ tự xuất hiện trong class body** của class ấy.

**Instance initializers** được thực thi khi tạo một instance, theo **thứ tự xuất hiện trong class body** của class ấy, sau phần constructor invocation tới superclass/constructor đích theo quy tắc Java 17, trước body constructor của cấp lớp tương ứng.

Java không tự gom tất cả field initializers chạy trước mọi initializer blocks: chúng **xen kẽ theo textual order** ở mỗi nhóm static hoặc instance.

### 2.1. Trước initializer là giá trị mặc định

Một `int` field có default `0`, `boolean` có default `false`, reference field có default `null`. Các bước gán `= 10`, `= true`, `= new Object()` thuộc giai đoạn initializer tương ứng.

Đây là sự khác biệt rất quan trọng với biến cục bộ. Java không cho bạn tự đọc một **local variable chưa definitely assigned**, nhưng một field có thể được đọc trong những context hợp lệ ngay cả khi initializer biểu thức của nó chưa chạy và lúc đó có default value.

### 2.2. Ví dụ đầu tiên: thứ tự chạy bình thường

Lưu **`OrderedInitializersDemo.java`**:

~~~java
public class OrderedInitializersDemo {
    static class Example {
        static int base = trace("static base", 4);

        static {
            System.out.println("static block sees base=" + base);
        }

        static int total = trace("static total", base + 2);

        int id = trace("instance id", 7);

        {
            System.out.println("instance block sees id=" + id);
        }

        int doubled = trace("instance doubled", id * 2);

        Example() {
            System.out.println("constructor doubled=" + doubled);
        }

        static int trace(String label, int value) {
            System.out.println(label + "=" + value);
            return value;
        }
    }

    public static void main(String[] args) {
        System.out.println("start");
        new Example();
        System.out.println("again");
        new Example();
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac OrderedInitializersDemo.java
java OrderedInitializersDemo
~~~

**Stdout chính xác:**

~~~text
start
static base=4
static block sees base=4
static total=6
instance id=7
instance block sees id=7
instance doubled=14
constructor doubled=14
again
instance id=7
instance block sees id=7
instance doubled=14
constructor doubled=14
~~~

Ở lần tạo instance đầu tiên, `Example` cần class initialization nên chạy nhóm static trước. Mỗi lần tạo object lại chạy nhóm instance, rồi constructor. Mỗi field initializer tham chiếu những fields đã được khởi tạo **theo thứ tự rõ ràng**.

**Thực hành tốt:** khai báo fields được sử dụng làm dependency **trước** fields tiêu thụ chúng, hạn chế biến việc khởi tạo thành một mạng quan hệ khó theo dõi.

## 3. Quy tắc JLS §8.3.3 cho static field

Với một static field `f` được khai báo trong class/interface `C`, Java báo compile-time error đối với một lần **tham chiếu bằng tên đơn giản** `f` khi **đồng thời**:

1. Lần tham chiếu nằm trong **static field initializer** hoặc **static initializer block** của `C`.
2. Vị trí tham chiếu nằm trong **initializer của chính `f`**, hoặc ở vị trí source **trước declarator của `f`**.
3. Lần tham chiếu **không** ở vế trái của assignment expression.
4. **Innermost enclosing class/interface** của lần tham chiếu vẫn là `C`.

Nhấn mạnh từ **đồng thời**. Đây không phải quy tắc “không bao giờ được nhắc tới field khai báo sau”, mà là một tổ hợp điều kiện về **loại field**, **vị trí**, **dạng tham chiếu** và **class bao trong cùng**.

### 3.1. Hai dạng lỗi thường gặp

~~~java
class BadStatic {
    static int first = later + 1; // ERROR: đọc later bằng simple name.
    static int later = 10;
}
~~~

~~~java
class BadStaticBlock {
    static {
        // System.out.println(later); // ERROR nếu bỏ comment.
    }

    static int later = 10;
}
~~~

Đoạn thứ nhất cố ý **không biên dịch**. Đoạn thứ hai comment dòng sai để nêu điểm lỗi. Không được gộp các đoạn này vào cùng source có ý định chạy như một demo hoàn chỉnh.

### 3.2. Đọc sau declarator thường hợp lệ

~~~java
class GoodStatic {
    static int later = 10;
    static int first = later + 1;

    static {
        System.out.println(first);
    }
}
~~~

Các khai báo biên dịch hợp lệ. Trong lần class initialized, `later` được gán 10 trước khi `first` đọc nó, nên `first` nhận 11.

### 3.3. Self-reference cũng bị giới hạn

~~~java
class BadSelfReference {
    static int x = x + 1; // ERROR: simple-name read trong initializer của x.
}
~~~

Vấn đề không chỉ là “field khai báo sau”. `x` ở ngay initializer **của chính `x`**, và phép đọc `x` bằng tên đơn giản thỏa các điều kiện bị cấm.

Tuy nhiên, Java không nhất thiết chặn mọi dạng indirect/self-reference; qualified access hoặc method call có thể khiến chương trình compile rồi đọc default value. Vì vậy compiler check là **một rào chắn**, không phải một bộ chứng minh mọi dependency acyclic.

## 4. Quy tắc tương ứng cho instance field

Với một **instance field `f`** khai báo trong class `C`, lần đọc bằng tên đơn giản bị lỗi khi **đồng thời**:

1. Tham chiếu nằm trong **instance field initializer** hoặc **instance initializer block** của `C`.
2. Tham chiếu nằm tại initializer của chính `f` hoặc ở phía trước declarator của `f`.
3. Nó **không** là vế trái của assignment expression.
4. Innermost enclosing class chứa tham chiếu là `C`.

Quy tắc instance tương ứng với quy tắc static, nhưng **context của nó khác**. Instance initializer được thực hiện cho từng object, trong khi static initializer được thực hiện khi class initialized.

### 4.1. Ví dụ lỗi trong instance field initializer

~~~java
class BadInstance {
    int copied = later; // ERROR: illegal forward reference.
    int later = 11;
}
~~~

### 4.2. Ví dụ lỗi trong instance initializer block

~~~java
class BadInstanceBlock {
    {
        // System.out.println(later); // ERROR nếu mở comment.
    }

    int later = 11;
}
~~~

### 4.3. Ví dụ hợp lệ khi chuyển dependency lên trên

~~~java
class GoodInstance {
    int later = 11;
    int copied = later;

    {
        System.out.println("copied=" + copied);
    }
}
~~~

Ở đây `copied` nhận 11 khi tạo instance, sau đó block in 11. Đó là cách xử lý rõ ràng nhất nếu logic yêu cầu copied phụ thuộc later.

## 5. Tên đủ điều kiện có thể hợp lệ nhưng không an toàn về giá trị

JLS §8.3.3 kiểm tra **simple-name reference** như `later`. Một biểu thức **qualified** như `State.later` (static) hoặc `this.later` (instance) không cùng dạng tham chiếu bị chặn bởi điều kiện đó.

**Điều này không có nghĩa field được khởi tạo sớm hơn.** Nó chỉ có nghĩa source có thể biên dịch, còn thứ tự runtime không thay đổi.

### 5.1. Ví dụ hoàn chỉnh: static qualified forward reference

Lưu **`QualifiedStaticForwardDemo.java`**:

~~~java
public class QualifiedStaticForwardDemo {
    static class State {
        static int copied = State.later;
        static int later = 25;

        static {
            System.out.println("block later=" + later);
        }
    }

    public static void main(String[] args) {
        System.out.println("copied=" + State.copied);
        System.out.println("later=" + State.later);
    }
}
~~~

Chạy:

~~~bash
javac QualifiedStaticForwardDemo.java
java QualifiedStaticForwardDemo
~~~

Output:

~~~text
block later=25
copied=0
later=25
~~~

**Truy vết:**

1. Khi `State` initialized, static fields thông thường được chuẩn bị với default `0` trước khi initializer expressions chạy.
2. `copied = State.later` được đánh giá trước khi `later = 25`.
3. Qualified access `State.later` **biên dịch được**, nhưng đọc default `0`.
4. `later = 25` mới chạy, sau đó static block in `block later=25`.
5. `copied` **không tự cập nhật lại** khi `later` nhận 25.

Đây không phải chỉ là khác biệt cú pháp: chương trình có thể chứa **logic bug khó phát hiện** dù compiler chấp nhận.

### 5.2. Ví dụ hoàn chỉnh: instance qualified forward reference

Lưu **`QualifiedInstanceForwardDemo.java`**:

~~~java
public class QualifiedInstanceForwardDemo {
    static final class Pair {
        int copied = this.later;
        int later = 11;

        Pair() {
            System.out.println("constructor copied=" + copied);
            System.out.println("constructor later=" + later);
        }
    }

    public static void main(String[] args) {
        new Pair();
    }
}
~~~

Chạy:

~~~bash
javac QualifiedInstanceForwardDemo.java
java QualifiedInstanceForwardDemo
~~~

Output:

~~~text
constructor copied=0
constructor later=11
~~~

Instance field `copied` được khởi tạo trước `later`. `this.later` đọc giá trị mặc định 0 của **cùng object**; sau đó `later = 11` chạy. Constructor body chỉ chạy sau các instance field initializers thuộc Pair, nên ở đó in lần lượt 0 và 11.

### 5.3. Khi nào nên tránh qualified forward reference?

Nếu `copied` được kỳ vọng là bản sao **giá trị cuối** của `later`, thì viết `this.later` để “vượt compiler” **không giải quyết yêu cầu**.

Cách sửa thực sự:

~~~java
class CorrectPair {
    int later = 11;
    int copied = later;
}
~~~

Hoặc tính cả hai fields trong constructor từ một giá trị ứng viên đã validate. Dùng qualified forward read chỉ khi bạn **thực sự muốn** phụ thuộc vào trạng thái hiện tại chưa hoàn tất — trường hợp này hiếm và dễ gây hiểu lầm.

## 6. Vế trái assignment: được gán trước khi declarator xuất hiện

Một điều kiện chính của JLS là **không cấm lần tham chiếu nằm bên trái assignment**.

Ví dụ:

~~~java
class EarlyWrite {
    static {
        number = 5; // Hợp lệ: number ở LHS của phép gán.
    }

    static int number = 20;
}
~~~

Khối `static` gán `number = 5` trước; sau đó field initializer `number = 20` vẫn chạy và **ghi đè**. Đây là một phép gán hợp lệ về cú pháp nhưng có thể vô ích hoặc gây nhầm.

### 6.1. Chương trình quan sát gán trước rồi bị ghi đè

Lưu **`WriteBeforeDeclarationDemo.java`**:

~~~java
public class WriteBeforeDeclarationDemo {
    static class StaticHolder {
        static {
            number = 5;
            System.out.println("static early=" + StaticHolder.number);
        }

        static int number = 20;
    }

    static class InstanceHolder {
        {
            later = 7;
            System.out.println("instance early=" + this.later);
        }

        int later = 30;
    }

    public static void main(String[] args) {
        System.out.println("static final=" + StaticHolder.number);

        InstanceHolder holder = new InstanceHolder();
        System.out.println("instance final=" + holder.later);
    }
}
~~~

Lệnh:

~~~bash
javac WriteBeforeDeclarationDemo.java
java WriteBeforeDeclarationDemo
~~~

Output:

~~~text
static early=5
static final=20
instance early=7
instance final=30
~~~

**Từng bước:**

- `number = 5` trong static block là assignment LHS nên được phép trước khi `number` được khai báo.
- `StaticHolder.number` trong dòng in có qualification nên có thể đọc 5 ở thời điểm đó.
- `static int number = 20` chạy tiếp và ghi đè.
- Instance block có thể gán `later = 7` trước declarator.
- `this.later` trong block đọc 7, nhưng field initializer `later = 30` chạy sau block và ghi đè thành 30.

**Đừng suy ra rằng “gán trước” được compiler chấp nhận thì luôn là thiết kế hợp lý.** Hãy tránh sử dụng initialization order để ghi đè các trạng thái khó theo dõi.

### 6.2. Vế trái assignment đơn giản khác với phép đọc

~~~java
class Examples {
    static {
        next = 3;        // Hợp lệ: assignment LHS.
        // next += 2;     // ERROR: compound assignment còn đọc giá trị next.
        // next++;        // ERROR: ++ đọc giá trị hiện tại của next.
        // next = next+1; // ERROR: RHS đọc next bằng simple name.
    }

    static int next = 10;
}
~~~

`next += 2` không chỉ ghi; về mặt ngữ nghĩa nó còn cần đọc giá trị hiện tại của field. `next++` cũng đọc (và viết), nên không thuộc trường hợp “chỉ gán ở bên trái một phép assignment” được miễn.

### 6.3. Assignment expression lồng nhau

~~~java
class NestedAssign {
    static int first = (later = 2);
    static int later = 9;
}
~~~

Ở initializer của `first`, `later` nằm ở vế trái của `later = 2`, không phải một lần đọc. Code có thể biên dịch, và nếu được initialized, `first` nhận 2, còn `later` cuối cùng bị initializer phía sau gán thành 9.

Khi cần tạo dependency hợp lệ, tốt hơn viết các assignments minh bạch trong một constructor hoặc method, thay vì xâu chuỗi nhiều assignments trong field initializers.

## 7. Gọi method để đọc field được khai báo sau

Phép kiểm tra `8.3.3` chỉ áp dụng trong các **initializer contexts** đã nêu. Khi một method body đọc field phía sau, nó không tự bị cấm theo đúng bộ điều kiện ấy, kể cả method được gọi rất sớm từ field initializer.

Nhưng method được gọi ở **thời điểm nào** vẫn quyết định giá trị trả về.

### 7.1. Chương trình đầy đủ: static method đọc default

Lưu **`IndirectStaticReadDemo.java`**:

~~~java
public class IndirectStaticReadDemo {
    static class Data {
        static int copied = readLater();

        static int readLater() {
            return later;
        }

        static int later = 9;
    }

    public static void main(String[] args) {
        System.out.println("copied=" + Data.copied);
        System.out.println("later=" + Data.later);
    }
}
~~~

Chạy:

~~~bash
javac IndirectStaticReadDemo.java
java IndirectStaticReadDemo
~~~

Output:

~~~text
copied=0
later=9
~~~

`copied = readLater()` gọi method trong khi `Data` đang initialized. Method `readLater()` trả `later`, nhưng initializer `later = 9` chưa chạy. Compiler không báo `illegal forward reference` cho cách đọc nằm trong method, và giá trị trả về là default 0.

### 7.2. Chương trình đầy đủ: instance method đọc default

Lưu **`IndirectInstanceReadDemo.java`**:

~~~java
public class IndirectInstanceReadDemo {
    static class Data {
        int copied = readLater();

        int readLater() {
            return later;
        }

        int later = 9;
    }

    public static void main(String[] args) {
        Data data = new Data();
        System.out.println("copied=" + data.copied);
        System.out.println("later=" + data.later);
    }
}
~~~

Lệnh:

~~~bash
javac IndirectInstanceReadDemo.java
java IndirectInstanceReadDemo
~~~

Output:

~~~text
copied=0
later=9
~~~

Với instance field, cơ chế tương tự: `copied` initializer gọi `readLater()` trong lúc đang khởi tạo object. Method đọc instance field `later` vẫn ở default 0; sau đó initializer `later = 9` hoàn tất.

**Bài học:** đổi từ `copied = later` sang `copied = readLater()` để tránh lỗi compiler **không bảo đảm** `copied` đúng theo nghiệp vụ. Bạn phải điều chỉnh thứ tự/thiết kế, không chỉ hình thức access.

## 8. Self-reference bằng qualification: hợp lệ nhưng dễ gây hại

Self-reference là trường hợp field tự tham chiếu trong initializer của chính nó.

### 8.1. Phép đọc đơn giản bị cấm

~~~java
class BadSelf {
    static int count = count + 1; // ERROR.
}
~~~

~~~java
class BadSelfInstance {
    int count = count + 1; // ERROR.
}
~~~

### 8.2. Tham chiếu đủ điều kiện có thể compile

Lưu **`QualifiedSelfReferenceDemo.java`**:

~~~java
public class QualifiedSelfReferenceDemo {
    static class StaticNode {
        static int value = StaticNode.value + 1;
    }

    static class InstanceNode {
        int value = this.value + 1;
    }

    public static void main(String[] args) {
        System.out.println("static=" + StaticNode.value);
        System.out.println("instance=" + new InstanceNode().value);
    }
}
~~~

Chạy:

~~~bash
javac QualifiedSelfReferenceDemo.java
java QualifiedSelfReferenceDemo
~~~

Output:

~~~text
static=1
instance=1
~~~

- StaticNode.value bắt đầu với default 0. Initializer đọc `StaticNode.value` (qualified), cộng 1 rồi gán 1.
- InstanceNode.value cũng bắt đầu 0 cho mỗi object. Initializer đọc `this.value`, cộng 1 rồi gán 1.
- Kết quả 1 **không** có nghĩa Java chạy initializer hai lần. Đây là một lần tính dựa trên default value.

Trong hầu hết business code, cách viết tự tham chiếu như trên không nên dùng làm cơ chế đếm. Nếu cần counter, hãy định nghĩa phép tăng ở method/constructor với trạng thái rõ ràng.

## 9. Phân biệt field khai báo sau với field thuộc lớp khác hoặc superclass

Quy tắc không phải “mọi field nằm ở dòng phía sau đều bị cấm”. Nó xét **field nào được khai báo trong class `C`**, context nào đang đọc và class nào bao quanh tham chiếu.

### 9.1. Instance initializer có thể tham chiếu static field khai báo sau

JLS `8.3.2 cho phép một **instance field initializer** tham chiếu bằng tên đơn giản đến class variables thích hợp, kể cả field static được khai báo phía sau trong cùng class. Lúc tạo instance bình thường, class đã initialized phần static.

Lưu **`CrossKindForwardDemo.java`**:

~~~java
public class CrossKindForwardDemo {
    static class Data {
        int snapshot = SHARED;

        static int SHARED = 12;

        Data() {
            System.out.println("snapshot=" + snapshot);
        }
    }

    public static void main(String[] args) {
        Data data = new Data();
        System.out.println("shared=" + Data.SHARED);
    }
}
~~~

Chạy:

~~~bash
javac CrossKindForwardDemo.java
java CrossKindForwardDemo
~~~

Output:

~~~text
snapshot=12
shared=12
~~~

`snapshot` là instance field, `SHARED` là static field. Lúc constructor tạo instance, static initialization của Data đã hoàn thành trong ví dụ. Quy tắc cấm **instance-field simple-name read trong instance initializer quá sớm** không áp dụng cho lần đọc static `SHARED` này.

**Không suy rộng:** nếu một static initializer cố đọc instance field bằng tên đơn giản, đó là lỗi **static context** (không có current instance), không phải cùng một loại lỗi forward reference.

### 9.2. Field kế thừa được khai báo ở lớp cha

Ví dụ:

~~~java
class Parent {
    protected int inherited = 17;
}

class Child extends Parent {
    int copied = inherited;
    int local = 25;
}
~~~

Đây là các lớp minh họa biên dịch được trong cùng package. `inherited` được **khai báo trong Parent**, không phải một instance field của Child nằm phía sau khai báo `copied`. Trong quy trình tạo Child, phần instance initialization của Parent đã chạy trước khi Child khởi tạo `copied`.

Cẩn thận trường hợp subclass **hiding** một field cùng tên: name resolution có thể chọn một khai báo khác, khiến việc đọc đổi nghĩa hoặc trở thành forward reference. Dùng names rõ ràng thay vì cố dựa vào shadowing/hiding phức tạp.

### 9.3. Khác giữa field reference và biến local

~~~java
static void example() {
    // System.out.println(local); // local chưa được khai báo.
    int local = 3;
    System.out.println(local);
}
~~~

Biến cục bộ có scope/definite-assignment rules riêng. Đừng áp dụng “qualified name vượt forward reference” của field cho một local variable; không có `this.local` để truy cập local ngoài phạm vi.

## 10. Constant variables và ngoại lệ về thời điểm được khởi tạo

Với:

~~~java
static final int PORT = 8080;
static final String APP = "Demo";
~~~

nếu hai field thỏa định nghĩa **constant variable** (final, primitive/String, constant-expression initializer), JVM có cơ chế xử lý giá trị hằng sớm theo quy tắc class initialization, và compiler có thể dùng giá trị hằng trực tiếp ở client.

Điều này cần **tách** với kiểm tra `8.3.3`:

- **Forward-reference check** xét vị trí, dạng tên và context.
- **Constant-variable semantics** xét modifier/kiểu/initializer và thời điểm giá trị hằng được cung cấp.
- **Runtime static field initialization** xét thứ tự đánh giá phần còn lại của static field initializers và blocks.

Đừng kết luận mọi lần đọc `static final` đều an toàn: nếu initializer là `calculate()` hoặc field có kiểu `List`, nó không phải constant variable theo định nghĩa JLS.

### 10.1. Ví dụ tránh nhập nhằng bằng qualification

Lưu **`ConstantAndRuntimeForwardDemo.java`**:

~~~java
public class ConstantAndRuntimeForwardDemo {
    static class Values {
        static int constantCopy = Values.CONSTANT;
        static int runtimeCopy = Values.RUNTIME;

        static final int CONSTANT = 40;
        static final int RUNTIME = calculate();

        private static int calculate() {
            System.out.println("calculate runtime");
            return 9;
        }
    }

    public static void main(String[] args) {
        System.out.println("constantCopy=" + Values.constantCopy);
        System.out.println("runtimeCopy=" + Values.runtimeCopy);
        System.out.println("constant=" + Values.CONSTANT);
        System.out.println("runtime=" + Values.RUNTIME);
    }
}
~~~

Chạy:

~~~bash
javac ConstantAndRuntimeForwardDemo.java
java ConstantAndRuntimeForwardDemo
~~~

Output:

~~~text
calculate runtime
constantCopy=40
runtimeCopy=0
constant=40
runtime=9
~~~

**Giải thích:**

- `Values.CONSTANT` là compile-time constant variable, có giá trị 40 khi tham chiếu từ initializer của `constantCopy`.
- `Values.RUNTIME` là static final nhưng gọi method `calculate()`, **không** là constant variable.
- Tại thời điểm `runtimeCopy = Values.RUNTIME`, `calculate()` chưa chạy, nên `runtimeCopy` nhận default 0.
- Sau đó field initializer `RUNTIME = calculate()` mới chạy và in `calculate runtime`.
- Lúc `main` in kết quả, field `RUNTIME` là 9, nhưng `runtimeCopy` vẫn giữ 0.

Mọi lần đọc phía trước ở đây dùng **qualified names**, tránh lỗi simple-name forward reference. Sự khác nhau xuất phát từ **constant-expression semantics**, không phải một field “được JVM ưu tiên” tùy ý.

### 10.2. Tránh tham chiếu hằng thiếu điều kiện

Nếu có:

~~~java
static final int LATER = Integer.parseInt("40");
~~~

`LATER` không là compile-time constant. Dù kết quả về số là 40, một access sớm qua qualification vẫn có thể nhìn thấy default 0 trước khi initializer chạy.

Vì vậy hãy kiểm tra **loại initializer**, không chỉ nhìn `static final` hay giá trị dự đoán được.

## 11. Sự phụ thuộc vòng giữa static fields hoặc classes

Một cách dễ tạo lỗi khó đoán là đặt các initializers phụ thuộc qua lại. Compiler có thể chặn direct simple-name forward read, nhưng **gián tiếp qua methods** hoặc **qua classes khác** có thể vượt qua một phần kiểm tra.

### 11.1. Hai classes tham chiếu lẫn nhau

Lưu **`CircularStaticDependencyDemo.java`**:

~~~java
public class CircularStaticDependencyDemo {
    static class A {
        static int value = B.value + 1;
    }

    static class B {
        static int value = A.value + 1;
    }

    public static void main(String[] args) {
        System.out.println("A=" + A.value);
        System.out.println("B=" + B.value);
    }
}
~~~

Chạy:

~~~bash
javac CircularStaticDependencyDemo.java
java CircularStaticDependencyDemo
~~~

Output:

~~~text
A=2
B=1
~~~

Truy vết:

1. `A.value` được truy cập trước, bắt đầu khởi tạo A.
2. A cần `B.value`, dẫn đến khởi tạo B.
3. B đọc `A.value` trong khi A **đang khởi tạo bởi cùng luồng**, nên quan sát default 0 theo cơ chế recursive initialization.
4. B tính 0 + 1 = 1 và hoàn tất.
5. A tính 1 + 1 = 2 và hoàn tất.

Nếu thứ tự kích hoạt A/B đảo đi, kết quả có thể khác. Đây là lý do **đừng dùng circular static initializers** làm cơ chế xác lập state ứng dụng.

### 11.2. Đừng cho rằng mọi vòng đều bị compiler phát hiện

`8.3.3` là một bộ ràng buộc **cục bộ** liên quan tới cách đọc field trong initializer. Nó không phải thuật toán phát hiện mọi chu trình phụ thuộc giữa methods, classes, nested objects, services hay modules.

Cần áp dụng thiết kế acyclic và chủ động kiểm tra dependency graph, thay vì dựa vào Java để từ chối mọi vòng ở compile time.

## 12. Static initializer và instance initializer khác nhau về ngữ cảnh

| Ngữ cảnh | Có `this`? | Đọc static field bằng simple name? | Đọc instance field bằng simple name? |
| --- | --- | --- | --- |
| `static int x = ...` | Không | Có, theo forward-reference restrictions | Không có current instance |
| `static { ... }` | Không | Có, theo forward-reference restrictions | Không có current instance |
| `int x = ...` | Có, trong context instance hợp lệ | Có, kể cả một số static fields khai báo sau | Có, theo instance forward-reference restrictions |
| `{ ... }` instance block | Có | Có, theo rules tương ứng | Có, theo instance forward-reference restrictions |
| Constructor body | Có, sau explicit constructor invocation phù hợp | Có theo scope/access/static rules | Có; không chịu đúng kiểm tra `8.3.3` dành cho field/block initializers |
| Static method body | Không | Có theo scope/access | Không có current instance nếu không chỉ receiver |
| Instance method body | Có | Có | Có theo scope/access |

Thử dùng `this.later` trong static block là **sai cú pháp/ngữ cảnh** ngay cả khi muốn tránh lỗi simple name. `this` chỉ có ý nghĩa khi tồn tại instance context thích hợp.

### 12.1. Constructor có thể tham chiếu field khai báo phía dưới

~~~java
class ConstructorRead {
    ConstructorRead() {
        System.out.println(later);
    }

    int later = 5;
}
~~~

Đây là **class minh họa** hợp lệ: khi `new ConstructorRead()`, instance field initializer `later = 5` của class chạy trước constructor body, nên constructor in 5. Dù field khai báo sau constructor textually, điều đó không thành illegal forward reference theo `8.3.3`.

**Tuy nhiên**, từ constructor superclass gọi một overridable instance method của subclass, method đó có thể thấy subclass fields còn default 0/null. Đây là một rủi ro khác về thứ tự khởi tạo, không phải simple-name forward reference trong field initializer.

## 13. Innermost enclosing class: ngoại lệ khi có nested/anonymous class

JLS §8.3.3 có điều kiện **innermost class/interface chứa reference phải là chính C**. Nếu một field được đọc từ bên trong một **nested/anonymous class khác**, điều kiện đó có thể không đúng; tham chiếu không bị chặn bởi đúng quy tắc này.

### 13.1. Minh họa qua anonymous class

Lưu **`NestedReferenceDemo.java`**:

~~~java
public class NestedReferenceDemo {
    static class Owner {
        static int result = new Object() {
            int read() {
                return later;
            }
        }.read();

        static int later = 8;
    }

    public static void main(String[] args) {
        System.out.println("result=" + Owner.result);
        System.out.println("later=" + Owner.later);
    }
}
~~~

Chạy:

~~~bash
javac NestedReferenceDemo.java
java NestedReferenceDemo
~~~

Output:

~~~text
result=0
later=8
~~~

Trong method `read()` của anonymous class, compiler không dùng đúng phép kiểm tra simple-name field read ở static initializer của `Owner` như một lần đọc trực tiếp ở cùng innermost class. Method chạy trước khi `Owner.later = 8`, nên kết quả vẫn là default 0.

**Không nên dùng cấu trúc anonymous class chỉ để tránh forward-reference error.** Nó làm code dài hơn nhưng không giúp state đúng hơn. Ví dụ được đưa ra để hiểu chính xác điều kiện của JLS và quan hệ giữa lexical nesting với runtime order.

### 13.2. Lambda không phải cách sửa thiết kế

Dù biểu thức lambda có thể trì hoãn việc thực thi body cho tới khi được gọi, nó **không** biến dependency chưa hợp lệ hoặc circular thành một mô hình chắc chắn đúng. Khi đọc code có lambda trong initializer, phải kiểm tra **lúc nào functional method thực thi**, nơi tên được phân giải, và fields nào đã sẵn sàng. Tách construction khỏi sử dụng runtime vẫn dễ hiểu hơn.

## 14. Vì sao đọc default values có thể gây lỗi nghiệp vụ?

Một field được khởi tạo từ một field khác quá sớm có thể âm thầm giữ dữ liệu sai:

~~~java
class Limits {
    static int DEFAULT = Limits.MAX;
    static int MAX = 100;
}
~~~

Mã minh họa này compile với qualified `Limits.MAX`, nhưng `DEFAULT` nhận 0. Sau đó `MAX` nhận 100; không có cơ chế “tự tính lại” `DEFAULT`.

Điều nguy hiểm là chương trình **không nhất thiết ném exception**, và 0 có thể trông như một giá trị bình thường. Với data validation, 0 có thể gây logic khác hoàn toàn: hạn mức vô hiệu, timeout lập tức, kích thước bộ nhớ bằng 0, v.v.

### 14.1. Khi đọc một reference field quá sớm

~~~java
class Endpoints {
    static String first = Endpoints.second;
    static String second = "service";
}
~~~

`first` có thể nhận `null`, trong khi `second` sau đó là `"service"`. Nếu code trong initializer của `first` gọi method trên reference `null`, class initialization có thể thất bại vì `NullPointerException` được phát sinh.

### 14.2. Thất bại trong class initialization khác với giá trị default

Nếu exception được ném trong static field initializer/static block, quá trình class initialization có thể thất bại; lần đầu thường thấy `ExceptionInInitializerError` nếu throwable là non-`Error`, lần active use tiếp theo của erroneous runtime class có thể thấy `NoClassDefFoundError`.

Vì vậy có hai dạng lỗi khác nhau:

- **Silent wrong value:** initialized class thành công nhưng một field copy giá trị 0/null không đúng ý định.
- **Initialization failure:** static initializer ném exception và runtime class trở nên không dùng được theo cơ chế initialization failure.

Một forward-reference restriction không bảo đảm phòng ngừa đầy đủ cả hai.

## 15. Ví dụ runtime failure do đọc reference trước

Lưu **`EarlyNullInitializationDemo.java`**:

~~~java
public class EarlyNullInitializationDemo {
    static class Bad {
        static int length = Bad.text.length();

        static String text = "READY";
    }

    public static void main(String[] args) {
        try {
            System.out.println(Bad.length);
        } catch (ExceptionInInitializerError error) {
            System.out.println("initialization failed");
            System.out.println("cause=" +
                    error.getCause().getClass().getSimpleName());
        }
    }
}
~~~

Chạy:

~~~bash
javac EarlyNullInitializationDemo.java
java EarlyNullInitializationDemo
~~~

Output:

~~~text
initialization failed
cause=NullPointerException
~~~

Giải thích:

1. Khi bắt đầu khởi tạo `Bad`, `Bad.text` có default value `null`.
2. `Bad.length` initializer đọc `Bad.text` bằng qualified access rồi gọi `length()`.
3. Vì receiver `null`, một `NullPointerException` xảy ra trước khi đến initializer `text = "READY"`.
4. JVM báo lỗi class initialization theo cơ chế `ExceptionInInitializerError`, và `main` bắt lỗi này để in nguyên nhân.

**Cảnh báo:** đây là ví dụ minh họa cơ chế; code sản xuất thường không nên bắt `Error` rồi bỏ qua như chiến lược khởi động. Hãy sửa thứ tự khai báo hoặc dùng factory khởi tạo dữ liệu rõ ràng.

## 16. Tránh phụ thuộc vào giá trị mặc định bằng thứ tự và phương thức rõ ràng

Khi một field cần field khác:

### 16.1. Đặt dependency lên trước

~~~java
class Limits {
    static int max = 100;
    static int defaultLimit = max;
}
~~~

Đây thường là cách đơn giản nhất khi các values thuộc cùng class, không có chu trình và không cần cấu hình động.

### 16.2. Đặt logic phức tạp trong một static factory method

~~~java
class Limits {
    private static final Settings SETTINGS = createSettings();

    private static Settings createSettings() {
        int max = 100;
        int defaultLimit = max / 2;
        return new Settings(max, defaultLimit);
    }

    record Settings(int max, int defaultLimit) {
        Settings {
            if (max <= 0 || defaultLimit < 0 ||
                    defaultLimit > max) {
                throw new IllegalArgumentException("invalid limits");
            }
        }
    }
}
~~~

Đoạn này là **class hợp lệ** trong một tệp Java phù hợp. Thay vì dùng nhiều static fields phụ thuộc lẫn nhau và textually distant, factory tạo một giá trị cấu hình có invariant rõ. `Settings` là immutable record chỉ chứa primitive ints; caller khác không sửa nội dung của nó qua setters.

**Lưu ý:** factory được gọi từ field initializer vẫn chạy lúc class initialized; nó **không tự trở thành lazy initialization**. Lợi ích ở đây là dependency/validation dễ kiểm tra và không cần forward read.

### 16.3. Khởi tạo cả nhóm trong một static block

~~~java
class GoodConfig {
    static final int MAX;
    static final int DEFAULT;

    static {
        int candidateMax = 100;
        int candidateDefault = candidateMax / 2;

        if (candidateDefault < 0 ||
                candidateDefault > candidateMax) {
            throw new IllegalStateException("invalid values");
        }

        MAX = candidateMax;
        DEFAULT = candidateDefault;
    }
}
~~~

Đây là ví dụ có thể biên dịch (blank static final fields được gán hợp lệ). Giá trị được tính trong các **local variables** đã khai báo và assigned theo trình tự rõ; sau validation mới gán vào fields.

Ở ví dụ này, `MAX` và `DEFAULT` là static final fields nhưng **không phải compile-time constant variables**, bởi chúng được gán trong block chứ không được khởi tạo bằng constant-expression initializer ngay ở declarator.

### 16.4. Constructor cho trạng thái thuộc từng object

~~~java
class Range {
    private final int maximum;
    private final int preferred;

    Range(int maximum) {
        if (maximum <= 0) {
            throw new IllegalArgumentException("maximum must be positive");
        }
        this.maximum = maximum;
        this.preferred = maximum / 2;
    }

    int preferred() {
        return preferred;
    }
}
~~~

Nếu state phụ thuộc từng instance, constructor như trên phù hợp hơn việc dùng static fields. Không cần `this.preferred` đọc trước khi `maximum` được initialized qua một field initializer; mọi dependency hiển thị trong constructor.

## 17. Debug một lỗi `illegal forward reference`

Khi compiler báo `illegal forward reference`, hãy tự hỏi:

1. **Đang đọc field nào?** Tên đơn giản có resolve tới static field hay instance field?
2. **Field đó khai báo ở class nào?** Chính class chứa initializer hay superclass/outer class?
3. **Vị trí đọc thuộc đâu?** Static field initializer, static block, instance field initializer, instance block hay method/constructor?
4. **Đang đọc chính field hoặc field được khai báo phía sau?**
5. **Biểu thức dùng tên đơn giản hay qualified name?**
6. **Tên ở vế phải hay vế trái assignment?** Nếu compound assignment hoặc ++/--, có cả đọc.
7. **Innermost enclosing class/interface có đúng class khai báo field không?**
8. **Nếu đổi thành qualified/method call, giá trị nào sẽ được thấy ở runtime?** Có default 0/null không?
9. **Có constant variable nào liên quan và ý nghĩa thời điểm khởi tạo của nó không?**
10. **Có thể đặt dependency trước hoặc tính chung trong factory/constructor không?**

Tuy có nhiều điều kiện, cách sửa thường rất đơn giản: **đừng đọc field trước khi giá trị cần thiết của nó được khởi tạo**.

### 17.1. Tại sao không nên chỉ thêm `this.` hoặc tên class?

Đổi:

~~~java
int copied = later;
~~~

thành:

~~~java
int copied = this.later;
~~~

có thể thay compile-time error thành chương trình hợp lệ, nhưng **không bảo đảm `copied` đúng**. Nếu `later` được gán 11 ở dòng sau, `copied` rất có thể nhận 0 như demo.

Để sửa **semantics**, hãy di chuyển `later` initializer lên trước hoặc bỏ redundant field copy để một nguồn sự thật được đọc khi cần.

### 17.2. Tại sao không nên chỉ đổi thành getter?

~~~java
int copied = getLater();

int getLater() {
    return later;
}

int later = 11;
~~~

Method call không tự bị cùng forward-read check, nhưng getter được gọi **khi later chưa có giá trị 11**. Kết quả có thể vẫn là 0. Phương thức chỉ nên dùng khi thứ tự/giá trị đầu vào đã được kiểm soát.

## 18. Phân biệt các vấn đề thường bị gọi chung là “forward reference”

| Tình huống | Nhóm quy tắc |
| --- | --- |
| `int a = b; int b = 1;` ở cùng class | JLS `8.3.3` instance forward read |
| `static int a = b; static int b = 1;` | JLS `8.3.3` static forward read |
| `int a = this.b; int b = 1;` | Biên dịch có thể hợp lệ, nhưng runtime initialization order |
| `static int a = C.b; static int b = 1;` | Qualified access; runtime default values |
| `{ b = 1; } int b = 5;` | Assignment LHS exception, later initializer overwrites |
| `{ b++; } int b;` | Read-before-declaration restriction |
| `int a = readB(); int b = 5;` | Indirect read và thứ tự khởi tạo |
| `int a = STATIC_B; static int STATIC_B = 5;` | Instance initializer đọc static field, phạm vi/rules khác |
| Local variable dùng trước khai báo | Local scope, không phải `8.3.3` field check |
| Local được khai báo nhưng chưa gán | Definite assignment |
| Constructor gọi method override ở subclass quá sớm | Object initialization + dynamic dispatch |
| Static initializer dùng `this.b` | Static context không có `this` |
| Hai static classes đọc lẫn nhau | Class initialization dependency/cycle |
| `final` field chưa được gán theo đường hợp lệ | Definite assignment và final field rules |

**Phân loại đúng** rất quan trọng. Lỗi tên trong scope, lỗi definite assignment, lỗi static context và lỗi khởi tạo chưa đến lượt có cách giải quyết khác nhau.

## 19. Những hiểu nhầm và lỗi phổ biến

| Nhầm lẫn | Thực tế |
| --- | --- |
| “Field khai báo sau thì compiler không biết tên.” | Member có scope theo class body; restriction là kiểm tra bổ sung. |
| “Bất kỳ tham chiếu trước nào cũng cấm.” | JLS giới hạn những trường hợp đọc qua simple name trong context cụ thể. |
| “Chỉ static fields có forward-reference restrictions.” | Instance field initializers và instance initializer blocks cũng có. |
| “Mọi lần dùng tên field khai báo sau đều illegal.” | Constructor/method body và qualified reference có ngữ nghĩa khác. |
| “`this.later` không compile vì field khai báo phía sau.” | Có thể compile; nguy cơ là đọc default value. |
| “`ClassName.later` chạy initializer của later trước.” | Qualification không đổi textual execution order. |
| “Dùng getter sẽ tự đợi field hoàn tất.” | Method gọi sớm vẫn thấy field chưa khởi tạo. |
| “`x = 3` và `x += 3` giống nhau khi field khai báo sau.” | Compound assignment đọc giá trị cũ, nên khác. |
| “Assignment trước field rồi field initializer sẽ giữ giá trị assignment.” | Initializer phía sau có thể ghi đè. |
| “Compile được nghĩa là initialization order đúng.” | Vẫn có thể thấy 0/null hoặc vòng phụ thuộc. |
| “`final` khiến mọi field có giá trị cuối ngay từ đầu.” | Blank final/runtime final và constant variables có ngữ nghĩa khác nhau. |
| “`static final` luôn là constant variable.” | Cần primitive/String và constant-expression initializer. |
| “Lỗi forward-reference trong local giống field.” | Local scope/definite-assignment rules khác. |
| “Tất cả static blocks chạy trước static fields.” | Field initializers và blocks chạy theo textual order. |
| “Instance field initializer chạy sau constructor body.” | Thông thường chạy trước constructor body của cấp class đó. |
| “Đọc instance field của superclass sau sẽ giống đọc field Child sau.” | Declaring class và constructor order khác nhau. |
| “Compiler sẽ phát hiện mọi vòng phụ thuộc.” | Không; indirect và cross-class cycles có thể lọt qua. |
| “Không báo lỗi nên static dependency an toàn đa luồng.” | Class initialization coordination không thay thế synchronization cho mutable state. |
| “Đổi lỗi thành null là cải thiện.” | Chuyển lỗi compile-time thành lỗi runtime thường làm debug khó hơn. |

## 20. Câu hỏi tự kiểm tra kèm đáp án

**Câu 1.** Vì sao `int a = b; int b = 5;` trong cùng class báo lỗi?  
**Đáp án:** `a` initializer đọc instance field `b` bằng simple name ở phía trước khai báo `b`; thuộc JLS `8.3.3`.

**Câu 2.** `static int a = b; static int b = 5;` khác trường hợp trên như thế nào?  
**Đáp án:** Đây là phiên bản **static**; lần đọc thuộc static field initializer và thỏa các điều kiện cấm tương ứng.

**Câu 3.** Vì sao `int a = this.b; int b = 5;` có thể compile nhưng a bằng 0?  
**Đáp án:** Qualified reference không thuộc phép cấm simple-name read, nhưng `b` vẫn ở default 0 khi initializer `a` chạy.

**Câu 4.** Nếu viết `static int a = Sample.b; static int b = 5;`, a có tự thành 5 sau khi b được gán không?  
**Đáp án:** Không. Nó có thể nhận default 0 và giữ 0; không có reactive recomputation.

**Câu 5.** Một static block trước field `x` có được viết `x = 10` không?  
**Đáp án:** Có nếu các rules khác hợp lệ; đây là assignment LHS được miễn forward-read check.

**Câu 6.** Sau `static { x = 10; } static int x = 20;`, x cuối cùng là bao nhiêu?  
**Đáp án:** 20, vì field initializer phía sau ghi đè phép gán trong block trước.

**Câu 7.** `x += 1` trước khai báo x có giống `x = 1` không?  
**Đáp án:** Không; `x += 1` phải đọc giá trị cũ của x, nên không hưởng ngoại lệ chỉ gán vế trái.

**Câu 8.** `x++` trước khai báo x có hợp lệ theo ngoại lệ assignment LHS không?  
**Đáp án:** Không. ++ đọc giá trị hiện tại; bị cấm ở context thỏa quy tắc.

**Câu 9.** Vì sao method `readX()` trả x khai báo sau vẫn có thể compile?  
**Đáp án:** Lần đọc thuộc method body, không nằm trực tiếp ở initializer context thỏa toàn bộ điều kiện `8.3.3`.

**Câu 10.** Dùng method `readX()` từ field initializer có đảm bảo được giá trị initializer cuối của x không?  
**Đáp án:** Không. Method chạy sớm vẫn đọc default 0/null.

**Câu 11.** `static int x = x + 1;` có hợp lệ không?  
**Đáp án:** Không, simple-name self-reference read trong initializer của chính x bị cấm.

**Câu 12.** `static int x = Owner.x + 1;` có thể cho x bằng bao nhiêu khi class initialized lần đầu?  
**Đáp án:** Có thể bằng 1 vì qualified read thấy default 0 rồi cộng 1.

**Câu 13.** `int x = this.x + 1;` khi tạo object lần đầu có thể cho kết quả gì?  
**Đáp án:** 1, cũng dựa trên default int 0. Không nên dùng làm pattern thiết kế.

**Câu 14.** Vì sao instance field initializer có thể dùng static field khai báo phía sau?  
**Đáp án:** `8.3.3` phân biệt instance-field read với class-variable read; static class initialization thông thường đã xảy ra trước tạo instance.

**Câu 15.** Một subclass đọc instance field của superclass có luôn bị coi là forward reference trong subclass không?  
**Đáp án:** Không. Field được khai báo ở superclass và có initialization order riêng; cần xét declaring class, accessibility và name resolution.

**Câu 16.** Nếu static initializer của class A đọc field của B, B lại đọc field của A, compiler có luôn báo lỗi không?  
**Đáp án:** Không. Chu trình qua nhiều classes có thể compile nhưng đọc default values ở runtime.

**Câu 17.** Vì sao hai fields có initializer `static final` không nhất thiết cùng được xử lý như compile-time constants?  
**Đáp án:** Chỉ final primitive/String với constant-expression initializer là constant variables; initializer từ method call không đáp ứng.

**Câu 18.** Constructor đọc field khai báo phía dưới có chắc gây `illegal forward reference` không?  
**Đáp án:** Không. `8.3.3` không kiểm tra constructor body theo đúng các điều kiện dành cho field/initializer blocks; runtime value vẫn phụ thuộc initialization order.

**Câu 19.** Nếu static qualified forward read một `String` field chưa initialized, giá trị mặc định nào thường được thấy?  
**Đáp án:** `null`, trừ trường hợp compile-time constant variable hay các semantics khởi tạo đặc biệt khác.

**Câu 20.** Tại sao dùng `this.x` trong `static { ... }` không hợp lệ?  
**Đáp án:** Static context không có current instance; đây là lỗi static-context rules, không đơn thuần là forward reference.

**Câu 21.** Để sửa `int a = b; int b = compute();`, cách tốt nhất khi a cần giá trị đã khởi tạo của b là gì?  
**Đáp án:** Đặt `b` initializer lên trước `a` hoặc tính cả hai trong constructor/factory với dependency rõ; không chỉ thay `b` bằng `this.b`.

**Câu 22.** Vì sao ví dụ `int a = this.b; int b = 5;` là code smell dù compiler chấp nhận?  
**Đáp án:** Nó phụ thuộc vào default value chưa có nghĩa nghiệp vụ và dễ tạo silent wrong state khi refactor.

**Câu 23.** `final int b` gán trong constructor có trở thành compile-time constant variable khi constructor luôn gán 5 không?  
**Đáp án:** Không. Nó không có constant-expression initializer tại khai báo.

**Câu 24.** Nếu compiler báo lỗi trong initializer block, bước phân tích đầu tiên nên là gì?  
**Đáp án:** Xác định field đang đọc, loại static/instance, vị trí trước declarator hay self-reference, dạng simple/qualified và LHS/RHS.

## 21. Tài liệu tham khảo

- Java Language Specification (Java SE 17), [`8.3.3 — Restrictions on Field References in Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.3): quy tắc cốt lõi cho **forward reference và self-reference** ở field/static/instance initializers.
- Java Language Specification, [`8.3.2 — Field Initialization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.2): field initializer semantics; ghi chú về static constants và instance initializers.
- Java Language Specification, [`8.6 — Instance Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.6): khối khởi tạo instance.
- Java Language Specification, [`8.7 — Static Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.7): khối khởi tạo static.
- Java Language Specification, [`12.4.2 — Detailed Initialization Procedure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2): thời điểm static fields nhận giá trị và các bước initialization.
- Java Language Specification, [`12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): instance field initialization và constructor order.
- Java Language Specification, [`4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): constant variable.
- Java Language Specification, [`16 — Definite Assignment](https://docs.oracle.com/javase/specs/jls/se17/html/jls-16.html): quy tắc gán trước khi đọc, đặc biệt với local và blank final variables.

## Ghi nhớ

**Giới hạn tham chiếu trước** của Java không có nghĩa một field “chưa được biết tên” nếu đặt phía sau. Theo JLS §8.3.3, Java ngăn những lần **đọc bằng tên đơn giản** của static/instance fields trong **initializer cùng loại** khi field được khai báo phía sau hoặc tự tham chiếu, đồng thời xét điều kiện assignment LHS và innermost enclosing class.

Đổi sang `ClassName.field`, `this.field` hoặc gọi method có thể làm mã **biên dịch**, nhưng không thay đổi thứ tự runtime và có thể khiến giá trị được đọc là `0`, `false` hoặc `null`. Vì thế đừng sửa lỗi chỉ bằng cú pháp: hãy **khởi tạo dependency trước**, kiểm tra trạng thái ứng viên và tránh phụ thuộc vòng. Phân biệt ba câu hỏi **“field có scope?” → “cách tham chiếu này có hợp lệ?” → “đã nhận giá trị cần thiết chưa?”** là chìa khóa để đọc và thiết kế field initializers trong Java.
