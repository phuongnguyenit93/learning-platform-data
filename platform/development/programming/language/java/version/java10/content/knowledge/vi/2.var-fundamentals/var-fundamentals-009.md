# Phạm vi biến cục bộ và việc che khuất tên với `var` trong Java

**Chủ đề:** Nền tảng `var` (Java 10 trở lên). Các quy tắc dưới đây vẫn áp dụng trong Java hiện đại; các chương trình hoàn chỉnh được viết để chạy với Java 17+.

## 1. `var` chỉ suy luận kiểu, không thay đổi phạm vi

`var` cho phép trình biên dịch suy luận **kiểu tĩnh** của một biến cục bộ từ biểu thức khởi tạo:

~~~java
var quantity = 3;           // kiểu int
var title = "Java";         // kiểu String
var prices = new int[]{5, 8}; // kiểu int[]
~~~

Sau khi suy luận, kiểu của biến đã cố định. Chẳng hạn, `quantity = 4;` hợp lệ nhưng `quantity = "bốn";` không hợp lệ. `var` không biến Java thành ngôn ngữ kiểu động, không làm biến tự động thành `final`, và **không tạo thêm phạm vi (scope)**. Quy tắc về tên, khả năng truy cập và thời điểm biến hết phạm vi giống như khi viết kiểu tường minh (`int quantity = 3;`).

Để suy luận kiểu, biến phải có biểu thức khởi tạo phù hợp. Các khai báo `var x;` và `var x = null;` đều không biên dịch được; với giá trị `null`, hãy viết kiểu tường minh nếu cần: `String x = null;`.

## 2. Phạm vi từ vị trí khai báo đến hết khối bao quanh

**Biến cục bộ** được khai báo trong thân phương thức, constructor hoặc một khối lệnh. Phạm vi của nó được xác định theo cấu trúc mã nguồn, chủ yếu bởi cặp ngoặc nhọn `{ ... }`:

- Biến khai báo trong khối chỉ được tham chiếu tại những vị trí hợp lệ sau khai báo **bên trong khối đó** và những khối con không có xung đột tên.
- Biến không thể được dùng trước khi được khai báo, hoặc sau khi khối chứa khai báo đã kết thúc.
- Biến cục bộ phải được gán giá trị chắc chắn trước khi đọc (*definite assignment*). Với `var`, yêu cầu khởi tạo ngay lúc khai báo còn chặt hơn.

Ví dụ sau **chỉ minh họa lỗi phạm vi**, không phải chương trình độc lập để biên dịch:

~~~java
if (true) {
    var message = "Bên trong if";
    System.out.println(message); // hợp lệ
}
// System.out.println(message);  // lỗi: message nằm ngoài phạm vi
~~~

Ngoặc nhọn tạo một khối mới, nhưng không phải mọi ngoặc nhọn đều tạo một tên biến mới có thể trùng với biến cục bộ bên ngoài. Quy tắc khai báo trùng tên được giải thích ở mục 4.

### Phạm vi trong các cấu trúc thường gặp

| Vị trí khai báo | Vùng có thể dùng biến |
| --- | --- |
| `var x = ...;` trong thân phương thức | Từ khai báo đến hết khối bao quanh, trừ các vị trí không đáp ứng luật gán giá trị |
| `var x = ...;` trong khối `if`/`else` có ngoặc nhọn | Khối nhánh tương ứng; không dùng ở ngoài nhánh |
| `for (var i = 0; ...; i++)` | Phần điều kiện, cập nhật và thân vòng lặp; không dùng sau `for` |
| `for (var item : items)` | Thân vòng lặp `for-each`; không dùng sau vòng lặp |
| `try (var resource = ...)` | Phần khai báo tài nguyên và thân `try` liên quan; không dùng `resource` trong `catch`/`finally` |
| Tham số lambda `(var x) -> ...` | Thân biểu thức hoặc khối lambda; cú pháp `var` cho tham số lambda được hỗ trợ từ Java 11 |

`var` cũng không được dùng thay kiểu của field, kiểu trả về phương thức hay tham số phương thức thông thường. Trường hợp tham số lambda ở hàng cuối bảng là ngoại lệ hiện vẫn được hỗ trợ.

## 3. Ví dụ chạy được: phạm vi khối, `if`, `for` và truy cập field

Lưu đoạn sau thành **`VarScopeDemo.java`**:

~~~java
public class VarScopeDemo {
    private final String label = "FIELD";

    public static void main(String[] args) {
        new VarScopeDemo().run();
    }

    void run() {
        var label = "LOCAL";
        System.out.println(label);
        System.out.println(this.label);

        if (label.startsWith("L")) {
            var detail = "IN_IF";
            System.out.println(detail);
        }

        for (var index = 0; index < 2; index++) {
            System.out.println("index=" + index);
        }

        {
            var temp = "BLOCK";
            System.out.println(temp);
        }

        var temp = "OUTER";
        System.out.println(temp);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac VarScopeDemo.java
java VarScopeDemo
~~~

Kết quả chính xác:

~~~text
LOCAL
FIELD
IN_IF
index=0
index=1
BLOCK
OUTER
~~~

Cách đọc chương trình:

1. `var label = "LOCAL";` nằm trong phương thức `run`, có cùng tên với field `label`. Tên ngắn `label` trỏ đến biến cục bộ; `this.label` trỏ đến field của đối tượng, nên in ra hai giá trị khác nhau.
2. `detail` chỉ nằm trong khối `if`. Đưa `System.out.println(detail);` ra sau dấu `}` của khối `if` sẽ làm chương trình không biên dịch.
3. `index` được khai báo ở phần khởi tạo `for`; có thể dùng trong điều kiện, bước tăng và thân vòng lặp, nhưng không thể dùng sau vòng lặp.
4. `temp` đầu tiên ở khối lồng bên trong. Khi khối kết thúc, phạm vi của nó kết thúc. Khai báo `var temp = "OUTER";` sau khối vì vậy hợp lệ: hai phạm vi không chồng lấn tại điểm khai báo.

Một lưu ý nhỏ: **phạm vi tên biến** là khái niệm về nơi mã nguồn có thể tham chiếu đến tên; nó không đồng nghĩa với vòng đời của đối tượng hay thời điểm bộ gom rác giải phóng bộ nhớ.

## 4. Che khuất tên (*shadowing*) và khai báo trùng tên

**Che khuất tên** xảy ra khi một khai báo ở phạm vi gần hơn làm tên không định danh trực tiếp đến khai báo ở xa hơn. Với `var`, trường hợp điển hình là **biến cục bộ che khuất field cùng tên**:

~~~java
class Account {
    private String status = "FIELD";

    void printStatus() {
        var status = "LOCAL";  // che khuất field status
        System.out.println(status);      // LOCAL
        System.out.println(this.status); // FIELD
    }
}
~~~

Đây là **đoạn minh họa** nằm trong một lớp, không có `main` độc lập. Phần `this.status` giúp nói rõ muốn đọc field. Tham số phương thức cũng có thể che khuất field cùng tên.

**Không nhầm shadowing field với khai báo lại biến cục bộ:** Java không cho phép khai báo thêm một biến cục bộ cùng tên trong khối con nếu tên biến cục bộ ở khối ngoài vẫn đang trong phạm vi. Ví dụ **không biên dịch**:

~~~java
void invalid() {
    var score = 10;
    {
        // var score = 20; // LỖI: score cục bộ bên ngoài vẫn trong phạm vi
    }
}
~~~

Tương tự, trong thân một phương thức, không thể khai báo biến cục bộ trùng tên với tham số phương thức:

~~~java
void invalid(int score) {
    // var score = 20; // LỖI: trùng tên tham số score
}
~~~

Hai ví dụ trên là các **đoạn mã minh họa quy tắc**; những dòng gây lỗi đã được đặt trong comment. Nếu muốn có hai biến với tên giống nhau mà đều là biến cục bộ, hãy đặt chúng trong **hai khối độc lập không chồng phạm vi**:

~~~java
{
    var score = 10;
    System.out.println(score);
}
{
    var score = 20; // hợp lệ: score của khối trước đã hết phạm vi
    System.out.println(score);
}
~~~

Trong mã thực tế, nên chọn tên biểu đạt vai trò (`localStatus`, `savedStatus`, `currentScore`) thay vì cố tình dùng cùng tên ở nhiều vị trí. Khi tên tham số trùng field là có chủ ý (ví dụ trong constructor hoặc setter), dùng `this.field = field;` để tránh nhập nhằng.

## 5. Ví dụ chạy được: tham số che khuất field và lambda sử dụng biến `var`

Lưu thành **`ShadowingDemo.java`**:

~~~java
public class ShadowingDemo {
    private final int count = 100;

    void show(int count) {
        System.out.println("parameter=" + count);
        System.out.println("field=" + this.count);
    }

    public static void main(String[] args) {
        var demo = new ShadowingDemo();
        demo.show(3);

        var base = 7;
        Runnable printBase = () -> System.out.println("base=" + base);
        printBase.run();
    }
}
~~~

Chạy:

~~~bash
javac ShadowingDemo.java
java ShadowingDemo
~~~

Kết quả:

~~~text
parameter=3
field=100
base=7
~~~

Ở `show(int count)`, tham số `count` che khuất field `count`, nên `this.count` được dùng để chỉ field. Trong `main`, `base` là biến cục bộ được suy luận kiểu `int`. Lambda có thể **capture** biến cục bộ đó vì `base` là *effectively final* (được gán một lần và không bị gán lại). Nếu thêm `base = 8;` sau khai báo rồi vẫn capture trong lambda, mã sẽ không biên dịch. Viết `var` không bỏ quy tắc *final/effectively final* của lambda.

Lambda có thể khai báo tham số với `var` (ví dụ `(var a, var b) -> a + b`) khi tất cả tham số được khai báo theo cách phù hợp; việc đặt tên tham số lambda trùng với một biến cục bộ đang nằm trong phạm vi bao quanh cũng bị cấm. Đây là quy tắc hiện còn áp dụng trong Java hiện đại.

## 6. Các lỗi dễ gặp và cách sửa

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Dùng biến khai báo trong `if` sau khi khối `if` kết thúc | Ngoài phạm vi khối | Khai báo bên ngoài nếu cần dùng ở cả hai nơi; gán giá trị theo các nhánh thích hợp |
| Dùng `index` sau `for (var index = ... )` | Phạm vi biến khởi tạo vòng lặp đã kết thúc | Tính/lưu giá trị cần dùng sau vòng lặp vào biến khai báo bên ngoài |
| Khai báo `var count` trong khối con khi `count` cục bộ ở khối ngoài vẫn còn phạm vi | Java cấm hai biến cục bộ trùng tên ở các phạm vi lồng nhau | Đổi tên biến con hoặc tái sử dụng đúng biến ngoài |
| Tưởng `var status` tự lấy giá trị field `status` | Khai báo mới che khuất field | Dùng `this.status` để đọc field hoặc đổi tên cục bộ |
| `var value;` hoặc `var value = null;` | Không có kiểu khởi tạo để suy luận | Gán giá trị cụ thể ngay khi khai báo, hoặc viết kiểu tường minh |
| Gán lại biến `var` đã được lambda capture | Lambda chỉ capture biến cục bộ `final` hoặc *effectively final* | Giữ biến không gán lại, hoặc tạo giá trị riêng cho phép tính cần thay đổi |
| Cho rằng `var` thay đổi kiểu theo phép gán sau | Kiểu được suy luận tại thời điểm biên dịch | Chọn kiểu tường minh phù hợp hoặc tạo biến mới |

Khi cần truy cập một tên, hãy kiểm tra theo thứ tự: **nó được khai báo ở đâu, có đang nằm trong phạm vi tại dòng hiện tại không, và có field cùng tên đang bị che khuất không?** Sau đó kiểm tra giá trị đã được gán chắc chắn chưa và kiểu suy luận của `var` có phù hợp với phép toán hay không.

## 7. Tự kiểm tra

1. Trong `for (var i = 0; i < 3; i++)`, vì sao có thể dùng `i` ở điều kiện và thân vòng lặp nhưng không dùng được ở dòng sau vòng lặp?
2. Vì sao `var name = "local";` trong một phương thức có thể cùng tên với field `name`, trong khi `var name` ở khối con thường không được trùng với `name` cục bộ của khối ngoài?
3. Nếu muốn in field khi tham số phương thức cùng tên, dùng cú pháp nào?
4. Vì sao lambda đọc được `var base = 7;` nhưng báo lỗi khi `base` bị gán lại?

**Đáp án ngắn:** (1) `i` chỉ tồn tại trong phạm vi cấu trúc `for`; (2) Java cho phép cục bộ/tham số che khuất field nhưng không cho khai báo trùng biến cục bộ ở các khối lồng có phạm vi giao nhau; (3) `this.name` trong phương thức thực thể; (4) biến cục bộ được lambda capture phải `final` hoặc *effectively final*.