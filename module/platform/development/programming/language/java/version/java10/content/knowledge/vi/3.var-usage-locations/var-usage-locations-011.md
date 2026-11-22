# Giới hạn biểu thức khởi tạo tham chiếu chính biến đang khai báo với `var` (Java 10+)

## 1. Mục tiêu và quy tắc cốt lõi

Từ Java 10, `var` cho phép trình biên dịch **suy luận kiểu tĩnh của biến cục bộ từ biểu thức khởi tạo**. Tuy nhiên, **biểu thức khởi tạo của một biến khai báo bằng `var` không được chứa tham chiếu tới chính biến đang được khai báo**. Đây là quy tắc cấm ở **thời điểm biên dịch**; chương trình không thể chạy đến dòng đó để phát sinh lỗi runtime.

Theo Java Language Specification (JLS), mục *Local Variable Declarations*, một khai báo `var` là lỗi biên dịch nếu initializer của nó chứa tham chiếu đến biến đang khai báo. Quy tắc vẫn còn áp dụng trong Java hiện đại, kể cả JDK 17+.

Sau bài này, bạn cần phân biệt được:
- **Tự tham chiếu trong initializer**: `var x = x + 1;` — bị cấm.
- **Tham chiếu biến khác đã được khởi tạo**: `var y = x + 1;` — hợp lệ nếu `x` đã có giá trị và phép toán đúng kiểu.
- **Dùng lại chính biến sau khai báo**: `var x = 1; x = x + 1;` — hợp lệ vì quá trình khởi tạo đã kết thúc.
- **Truy cập field cùng tên** qua `this.field` hoặc `ClassName.field`: đây là thành viên của đối tượng/lớp, **không phải** tham chiếu đến biến cục bộ đang khai báo.

Quy tắc này là trọng tâm bài học. Những hạn chế khác của `var` như `var x = null` hoặc thiếu biểu thức khởi tạo là các quy tắc khác, không nên nhầm lẫn với lỗi tự tham chiếu.

## 2. Những ví dụ tự tham chiếu bị cấm

Các đoạn sau **cố ý không biên dịch**, chỉ dùng để nhận diện lỗi; không ghép vào chương trình chạy ở phần sau.

~~~java
// Sai 1: dùng chính x để tạo giá trị đầu tiên cho x
var x = x;

// Sai 2: dùng x trong biểu thức cộng
var x = x + 1;

// Sai 3: kể cả gán cho x ở bên trong initializer
var x = (x = 10);

// Sai 4: dùng x như đối số hàm
var x = Integer.toString(x);

// Sai 5: dùng x ở nhánh của biểu thức điều kiện
var x = true ? 10 : x;
~~~

Mỗi dòng là **một ví dụ độc lập**; không phải năm lần khai báo cùng tên `x` trong cùng khối. Nếu chạy lệnh `javac` trên một tệp chứa các khai báo không hợp lệ này, chương trình sẽ không biên dịch. Thông báo lỗi cụ thể có thể khác giữa các phiên bản và công cụ biên dịch; không nên phụ thuộc nguyên văn thông báo lỗi để xác định quy tắc.

Điểm đáng chú ý nhất là:

~~~java
var number = (number = 10); // Không hợp lệ
~~~

Thoạt nhìn, biểu thức gán ở vế phải dường như đã đặt giá trị `10` cho `number`. Nhưng quy tắc của `var` **cấm initializer chứa bất kỳ tham chiếu nào đến biến đang khai báo**, kể cả tham chiếu ở phía trái của một phép gán lồng. Đây không phải mẹo khởi tạo biến.

Cú pháp tăng/giảm cũng không tạo ngoại lệ:

~~~java
var counter = ++counter; // Không hợp lệ
var counter = counter++; // Không hợp lệ
~~~

Mỗi dòng ở đây cũng là ví dụ riêng. Không có chuyện khai báo `var` khiến biến nhận mặc định giá trị `0` rồi cho phép tăng lên 1; **biến cục bộ Java không tự được khởi tạo giá trị mặc định** như field của lớp.

## 3. Tại sao lỗi xảy ra ngay ở bước biên dịch?

Với khai báo hợp lệ:

~~~java
var amount = 100;      // Trình biên dịch suy ra kiểu int
var label = "Java";    // Trình biên dịch suy ra kiểu String
~~~

Trình biên dịch xác định kiểu của biểu thức bên phải rồi gán kiểu tĩnh tương ứng cho biến. Khai báo `var` không yêu cầu lập trình viên viết tên kiểu, nhưng **không có nghĩa kiểu được quyết định động lúc chạy**.

Với:

~~~java
var amount = amount + 1; // Sai: initializer dùng chính amount
~~~

Vế phải lại đòi hỏi truy cập biến đang được tạo. JLS đưa ra một ràng buộc trực tiếp: initializer của khai báo `var` không được chứa tham chiếu đến biến đó. Trình biên dịch vì thế bác bỏ khai báo; không cần, và cũng không được, suy đoán một giá trị hay kiểu ban đầu cho biến.

Không nên giải thích đơn giản rằng Java “không thể suy ra kiểu từ bất kỳ phép gán nào”. Ví dụ:

~~~java
var amount = (amount = 100); // Vẫn sai, dù số 100 có kiểu int
~~~

Ở trường hợp này, bản thân phép gán có vẻ mang thông tin kiểu, nhưng nó **vẫn vi phạm lệnh cấm tham chiếu chính biến trong initializer**. Quy tắc của ngôn ngữ đủ để kết luận lỗi, không phụ thuộc vào cách một trình biên dịch sắp xếp các bước phân tích nội bộ.

### Khác với quy tắc definite assignment

Java còn có quy tắc **definite assignment**: trước khi đọc giá trị một biến cục bộ, trình biên dịch phải chứng minh biến đã được gán giá trị theo đường đi thực thi tương ứng.

Ví dụ sau dùng kiểu tường minh nhưng vẫn sai:

~~~java
int count = count + 1; // Sai: đọc count trước khi được gán giá trị
~~~

Vì vậy, **chỉ đổi `var` thành `int` không chữa được kiểu tự tham chiếu thông thường**. Bạn cần thay đổi cách tạo giá trị đầu tiên, chẳng hạn:

~~~java
int count = 0;
count = count + 1;
~~~

Sự phân biệt quan trọng:
- Với `var`, JLS có **lệnh cấm riêng** đối với mọi tham chiếu đến biến trong initializer.
- Với kiểu tường minh, quy tắc kiểu dữ liệu và definite assignment vẫn áp dụng; mỗi biểu thức phải được xem xét theo quy định của Java.
- Hai cơ chế đều được kiểm tra khi biên dịch, nhưng **không đồng nhất**. Không suy ra rằng mọi dạng phép gán lồng với kiểu tường minh luôn có cùng kết quả như với `var`.

## 4. Các cách sửa đúng theo mục đích

### Cách 1: Khởi tạo từ một giá trị độc lập, sau đó mới cập nhật

~~~java
var counter = 0;      // int
counter = counter + 1; // Hợp lệ
counter++;             // Hợp lệ
System.out.println(counter); // 2
~~~

Tại thời điểm khai báo, `counter` nhận giá trị `0` từ biểu thức không tham chiếu chính nó. Các phép cập nhật ở các câu lệnh tiếp theo hợp lệ vì biến đã được khởi tạo.

### Cách 2: Dùng một biến khác đã tồn tại

~~~java
var original = 10;
var increased = original + 5;  // increased được suy ra là int
System.out.println(increased); // 15
~~~

Initializer của `increased` chỉ đọc `original`, là một biến khác đã được khởi tạo. Không có tự tham chiếu.

Nếu biến nguồn chưa được gán giá trị thì vẫn có thể gặp lỗi **definite assignment**:

~~~java
int original;
// var increased = original + 5; // Sai: original chưa được gán giá trị
original = 10;
var increased = original + 5;    // Hợp lệ
~~~

Đây là một vấn đề khác với tự tham chiếu `increased`.

### Cách 3: Tính giá trị trong phương thức độc lập

~~~java
static int initialValue() {
    return 40;
}

// Bên trong một phương thức khác:
var answer = initialValue() + 2; // int, bằng 42
~~~

Đoạn trên **minh họa trong ngữ cảnh một lớp có phương thức `initialValue()` và một phương thức chứa khai báo `answer`**. Nó hợp lệ vì initializer không dùng biến `answer`; việc gọi phương thức khác chỉ cung cấp một giá trị có kiểu đã biết.

Nếu cần lặp tính toán cho đến khi đạt điều kiện, khai báo giá trị đầu trước vòng lặp rồi cập nhật ở những bước tiếp theo:

~~~java
var sum = 0;
for (var i = 1; i <= 3; i++) {
    sum += i;
}
System.out.println(sum); // 6
~~~

`i` của vòng `for` cũng được khởi tạo độc lập bằng `1` trước khi dùng ở điều kiện và bước cập nhật.

## 5. Trường hợp dễ nhầm: field và biến cục bộ cùng tên

Giả sử một lớp có field `score`. Nếu trong phương thức bạn viết:

~~~java
class ScoreExample {
    private int score = 20;

    void print() {
        // var score = score + 1; // Sai: tên score không định danh field ở đây
    }
}
~~~

Biến cục bộ `score` trong phần khai báo sẽ che khuất (*shadow*) field cùng tên trong phạm vi tương ứng. Việc viết `score` ở vế phải có thể dẫn đến tham chiếu chính biến cục bộ đang khai báo; đừng mong trình biên dịch tự chọn field để hoàn tất initializer.

Cách rõ ràng và hợp lệ:

~~~java
class ScoreExample {
    private int score = 20;

    void print() {
        var score = this.score + 1; // Đọc field bằng this.score
        System.out.println(score); // 21
    }
}
~~~

Ở đây:
- `score` bên trái là **biến cục bộ mới**.
- `this.score` bên phải là **field của đối tượng**, không phải biến cục bộ ấy.
- Biểu thức `this.score + 1` có kiểu `int` nên `var score` được suy ra là `int`.

Với field tĩnh (*static*), có thể dùng tên lớp:

~~~java
class LimitExample {
    private static final int LIMIT = 100;

    void print() {
        var limit = LimitExample.LIMIT - 1;
        System.out.println(limit); // 99
    }
}
~~~

Đặt tên khác nhau, hoặc dùng `this.field`/`ClassName.field` rõ ràng, sẽ giúp người đọc tránh nhầm giữa **khai báo mới** và **đọc trạng thái đã tồn tại**.

## 6. Ví dụ Java 17+ hoàn chỉnh, có thể chạy ngay

Tạo tệp **VarSelfReferenceDemo.java** với nội dung:

~~~java
public class VarSelfReferenceDemo {
    private int score = 20;
    private static final int DEFAULT_BONUS = 5;

    private static int doubleValue(int value) {
        return value * 2;
    }

    private void demonstrate() {
        var base = 10;                   // Suy ra int
        var total = base + 3;            // Đọc biến khác đã có
        total = total + 2;               // Đọc lại total sau khởi tạo
        var doubled = doubleValue(total); // Không tự tham chiếu

        var score = this.score + 1;      // Đọc field cùng tên bằng this
        var bonus = VarSelfReferenceDemo.DEFAULT_BONUS;

        var label = "Java";
        label = label + " 10";           // Cập nhật sau khi khởi tạo

        System.out.println("base = " + base);
        System.out.println("total = " + total);
        System.out.println("doubled = " + doubled);
        System.out.println("field score = " + this.score);
        System.out.println("local score = " + score);
        System.out.println("bonus = " + bonus);
        System.out.println("label = " + label);
    }

    public static void main(String[] args) {
        new VarSelfReferenceDemo().demonstrate();
    }
}
~~~

Mở terminal trong thư mục chứa tệp, dùng JDK 17 trở lên:

~~~bash
javac VarSelfReferenceDemo.java
java VarSelfReferenceDemo
~~~

**Đầu ra chính xác:**

~~~text
base = 10
total = 15
doubled = 30
field score = 20
local score = 21
bonus = 5
label = Java 10
~~~

Diễn giải:
1. `base` và `total` đều được suy ra là `int`; `total` dựa trên **biến khác** `base`.
2. `total = total + 2` hợp lệ vì nằm **sau** khai báo và khởi tạo `total`.
3. `doubled` được tạo từ giá trị trả về của phương thức, không gọi lại chính `doubled` trong initializer.
4. `var score = this.score + 1` đọc field `score = 20` rồi tạo biến cục bộ có giá trị `21`.
5. `var bonus = VarSelfReferenceDemo.DEFAULT_BONUS` đọc một field tĩnh đã khai báo. Không có tự tham chiếu đến `bonus`.
6. `label` được suy ra là `String` và cập nhật về sau bằng chuỗi cùng kiểu. `var` không làm kiểu thay đổi động.

Ví dụ không phụ thuộc thư viện ngoài hoặc tính năng preview.

## 7. Tham chiếu ẩn trong biểu thức phức tạp cũng bị cấm

Điều kiện trong JLS là **initializer chứa tham chiếu đến biến đang khai báo**, không chỉ trường hợp biến đứng ngay sau dấu `=`.

Các ví dụ sau **cố ý không biên dịch**, xét độc lập từng dòng:

~~~java
var result = Math.max(1, result);          // Trong danh sách đối số
var result = (result == 0) ? 1 : 2;        // Trong điều kiện
var result = (result = 100);               // Ở vế trái phép gán lồng
var result = Integer.valueOf(result);      // Trong lời gọi factory
var result = (Runnable) () -> System.out.println(result);
                                            // Trong lambda thuộc initializer
~~~

Riêng dòng lambda còn liên quan đến quy tắc tham chiếu biến cục bộ của lambda. Dù có ép biểu thức lambda về `Runnable` để cung cấp **target functional interface**, nó vẫn chứa tham chiếu tới chính `result` trong initializer nên không hợp lệ.

Một cách viết đúng nếu mục tiêu chỉ là tạo và chạy tác vụ:

~~~java
var message = "ready";
var task = (Runnable) () -> System.out.println(message);
task.run(); // ready
~~~

Ở đây initializer của `task` tham chiếu biến **khác** là `message`, đã được khởi tạo. Biến `message` không bị gán lại nên thỏa điều kiện *effectively final* dành cho biến cục bộ được lambda capture. `task` được suy ra kiểu `Runnable` từ phép ép kiểu tường minh.

**Lưu ý:** nếu chỉ cần lambda, cách khai báo dễ đọc hơn thường là `Runnable task = () -> System.out.println(message);`, vì khai báo `var task = () -> ...` trực tiếp không có target functional interface và cũng không hợp lệ theo một quy tắc khác của suy luận kiểu.

## 8. Phân biệt tự tham chiếu với các lỗi `var` khác

| Đoạn khai báo | Kết quả | Giải thích |
| --- | --- | --- |
| `var n = n + 1;` | Lỗi biên dịch | Initializer chứa tham chiếu đến chính `n` |
| `var n = (n = 1);` | Lỗi biên dịch | Tự tham chiếu ở phép gán lồng vẫn bị cấm |
| `var n = 1; n++;` | Hợp lệ | Chỉ dùng `n` sau khi đã khởi tạo |
| `var a = 1; var b = a + 1;` | Hợp lệ | `b` sử dụng một biến khác là `a` |
| `var n = null;` | Lỗi biên dịch | Không suy ra được kiểu từ biểu thức có null type, **không phải** lỗi tự tham chiếu |
| `var n;` | Lỗi biên dịch | Thiếu biểu thức khởi tạo |
| `var n = new int[]{1, 2};` | Hợp lệ | Biểu thức tạo mảng có kiểu `int[]`, không tự tham chiếu |
| `var n = this.score;` | Hợp lệ trong phương thức instance có field `score` phù hợp | Đọc field của đối tượng, không đọc biến cục bộ `n` |
| `var n = n == null ? 1 : 2;` | Lỗi biên dịch | Dù biểu thức có nhánh trả kiểu cụ thể, initializer vẫn tham chiếu `n` |

Cả **`var` và kiểu tường minh đều tuân theo kiểm tra kiểu tĩnh**. Chúng không làm Java trở thành ngôn ngữ kiểu động. Điểm cần học ở đây là lệnh cấm đặc thù cho initializer của `var` và nguyên tắc chỉ đọc biến cục bộ sau khi nó đã có giá trị hợp lệ.

### Một trường hợp cần kiểm tra tên và scope

Ví dụ có field và biến cục bộ cùng tên:

~~~java
class OrderExample {
    private int amount = 12;

    void demonstrate() {
        // var amount = amount + 1; // Sai: tham chiếu biến cục bộ đang khai báo
        var amount = this.amount + 1; // Đúng: field và local rõ ràng
        System.out.println(amount);   // 13
    }
}
~~~

Trong `OrderExample`, chỉ có dòng không bị comment mới được biên dịch. Nếu đặt cả hai khai báo cùng tên trong cùng khối, còn xuất hiện lỗi khai báo trùng tên; đó là lý do ví dụ sai đã được comment.

## 9. Bài tập đọc code

**Bài 1.** Đoạn nào biên dịch?

~~~java
// A (độc lập):
var count = count + 1;

// B (độc lập):
var count = 1;
count = count + 1;
~~~

**Đáp án:** Chỉ B. Với A, initializer tham chiếu chính biến mới; B có giá trị ban đầu `1`, sau đó mới dùng lại `count`.

**Bài 2.** Vì sao dòng sau vẫn lỗi, dù bên phải có hằng số `42`?

~~~java
var answer = (answer = 42);
~~~

**Đáp án:** Initializer chứa tham chiếu tới biến `answer`. JLS cấm cả dạng tự gán bên trong initializer, không cho phép dùng nó để “đánh lừa” suy luận kiểu.

**Bài 3.** Đoạn này có hợp lệ không?

~~~java
var first = 4;
var second = first * 3;
second = second + first;
System.out.println(second);
~~~

**Đáp án:** Có. `first` và `second` đều suy ra `int`; stdout là `16`. `second` chỉ được dùng lại ở câu lệnh sau khi khởi tạo.

**Bài 4.** Trong phương thức instance của lớp có field `price`, nên viết gì nếu muốn tạo biến cục bộ `price` lớn hơn field một đơn vị?

~~~java
var price = this.price + 1;
~~~

**Đáp án:** Dùng `this.price` để chỉ đích danh field; tên `price` bên trái là biến cục bộ đang khai báo.

**Bài 5.** `var value = null;` có phải ví dụ tự tham chiếu không?

**Đáp án:** Không. Nó là lỗi suy luận kiểu từ `null` đơn độc. Nắm riêng nguyên nhân giúp sửa đúng: thay initializer bằng biểu thức có kiểu đủ xác định, hoặc chọn kiểu tường minh cho biến tham chiếu nếu cần nhận `null`.

## 10. Ghi nhớ khi viết Java hiện đại

- Với `var`, **toàn bộ biểu thức khởi tạo phải độc lập với chính biến đang khai báo**.
- Dùng một literal, kết quả phương thức, biểu thức tạo đối tượng, field được chỉ rõ hoặc **biến khác đã có giá trị** để tính giá trị đầu tiên.
- Nếu muốn cập nhật dựa trên giá trị cũ, phải khởi tạo xong trước rồi mới viết `x = ...x...`, `x++` hoặc `x += ...`.
- Không có giá trị mặc định dành cho biến cục bộ chỉ vì dùng `var`; không có phép bỏ qua kiểm tra kiểu hay definite assignment.
- Khi field và local cùng tên, dùng `this.field` hoặc `ClassName.field` khi phù hợp để tránh tự tham chiếu nhầm.

**Nguồn đặc tả để đối chiếu:** [Java Language Specification, §14.4 – Local Variable Declarations (Java 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.4) và [§16 – Definite Assignment](https://docs.oracle.com/javase/specs/jls/se17/html/jls-16.html). Các quy tắc cốt lõi nêu trong bài vẫn xuất hiện trong các bản đặc tả Java mới hơn.
