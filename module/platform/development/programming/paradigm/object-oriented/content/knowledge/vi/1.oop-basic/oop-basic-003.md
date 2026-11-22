# Lớp, kiểu và thể hiện: các khái niệm nền tảng

Khi đọc câu lệnh Java `CounterView view = new ClickCounter("Nút A", 10);`, người mới dễ gọi cả ba thành phần là “đối tượng”. Thực ra cần tách ba câu hỏi:

- **Lớp (class):** định nghĩa nào mô tả dữ liệu, phương thức, constructor và quy tắc của đối tượng?
- **Kiểu (type):** biến hoặc biểu thức cho phép ta sử dụng những thao tác nào ở thời điểm biên dịch?
- **Thể hiện (instance/object):** đối tượng cụ thể nào được tạo ra và có trạng thái riêng trong lúc chạy?

Thêm một khái niệm quan trọng là **tham chiếu (reference)**: trong Java, biến có kiểu tham chiếu thường chứa giá trị dùng để truy cập đối tượng, chứ bản thân biến không phải đối tượng. Bài học này tập trung vào cách phân biệt những khái niệm đó trên mã và kết quả thực thi.

## 1. Bản đồ bốn khái niệm

| Thuật ngữ | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| Lớp | Đối tượng được định nghĩa ra sao? | `class ClickCounter` có trạng thái `clicks` và hành vi `click()` |
| Kiểu | Thao tác nào hợp lệ qua biến này? | `CounterView` công bố `value()` |
| Thể hiện | Đối tượng cụ thể nào đang tồn tại? | Kết quả của `new ClickCounter("Nút A", 10)` |
| Tham chiếu | Biến đang truy cập đối tượng nào? | `view` giữ tham chiếu tới một `ClickCounter` |

Một **class cũng định nghĩa một kiểu** trong Java, nhưng “class” và “type” không hoàn toàn đồng nghĩa. Ngoài kiểu lớp còn có kiểu interface, kiểu mảng, kiểu nguyên thủy, v.v. Đồng thời, cùng một đối tượng có thể được truy cập qua nhiều **kiểu khai báo tương thích**.

Ví dụ:

~~~java
CounterView view = new ClickCounter("Nút A", 10);
~~~

Bên trái: `CounterView` là kiểu khai báo của biến `view`. Bên phải: `new ClickCounter(...)` tạo một thể hiện của lớp `ClickCounter`. Biến `view` nhận tham chiếu tới thể hiện đó. Một đối tượng được tạo ra, không phải hai đối tượng vì xuất hiện hai tên kiểu.

## 2. Class mô tả cấu trúc và hành vi chung

Lớp là nơi Java khai báo những thành phần và quy tắc cho các đối tượng thuộc lớp:

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Field của thể hiện | `private int clicks;` | Lưu số lượt nhấn của **mỗi** bộ đếm |
| Field cố định | `private final String label;` | Tên bộ đếm, được gán lúc khởi tạo rồi không gán lại |
| Constructor | `ClickCounter(String label, int initial)` | Tạo trạng thái ban đầu hợp lệ |
| Instance method | `void click()` | Tác động lên bộ đếm nhận lời gọi |
| Method truy vấn | `int value()` | Trả về số lượt nhấn hiện tại |
| Access modifier | `private`, `public` | Quy định nơi có thể sử dụng thành viên |

Chỉ viết `class ClickCounter { ... }` **chưa tạo ra** một bộ đếm cụ thể. Mỗi lần chạy biểu thức `new ClickCounter(...)`, Java tạo một đối tượng mới và thực hiện constructor phù hợp. Các đối tượng có cùng tập phương thức theo định nghĩa lớp nhưng có thể giữ giá trị field khác nhau.

**Đừng hiểu phép so sánh “class là bản thiết kế” quá máy móc.** Trong Java, lớp còn tham gia quy tắc kiểu, kế thừa, mức truy cập và lựa chọn phương thức. Bản thiết kế là hình ảnh để bắt đầu hiểu, không phải toàn bộ ngữ nghĩa của class.

## 3. Chương trình chạy độc lập: một đối tượng, nhiều góc nhìn kiểu

Ví dụ sử dụng Java 11 trở lên. Lưu toàn bộ vào `Main.java`.

~~~java
interface CounterView {
    int value();
}

final class ClickCounter implements CounterView {
    private final String label;
    private int clicks;

    ClickCounter(String label, int initial) {
        if (label == null || label.isBlank()) {
            throw new IllegalArgumentException("Label must not be blank");
        }
        if (initial < 0) {
            throw new IllegalArgumentException("Initial count must not be negative");
        }
        this.label = label;
        this.clicks = initial;
    }

    @Override
    public int value() {
        return clicks;
    }

    public String label() {
        return label;
    }

    public void click() {
        clicks = Math.addExact(clicks, 1);
    }
}

public class Main {
    public static void main(String[] args) {
        ClickCounter first = new ClickCounter("Nút A", 10);
        CounterView view = first;
        Object general = first;
        ClickCounter second = new ClickCounter("Nút A", 10);

        first.click();

        System.out.println(first.value());                  // 11
        System.out.println(view.value());                   // 11
        System.out.println(second.value());                 // 10
        System.out.println(first == view);                  // true
        System.out.println(view == general);                // true
        System.out.println(first == second);                // false
        System.out.println(view.getClass().getSimpleName()); // ClickCounter
    }
}
~~~

Chạy bằng:

~~~bash
javac Main.java
java Main
~~~

Kết quả:

~~~text
11
11
10
true
true
false
ClickCounter
~~~

### Theo dõi từng lời gọi

1. `new ClickCounter("Nút A", 10)` tạo **thể hiện thứ nhất** có `clicks = 10`. Biến `first` chứa tham chiếu tới nó.
2. `CounterView view = first` **sao chép tham chiếu**. Nó không tạo một `ClickCounter` thứ hai.
3. `Object general = first` cũng trỏ tới thể hiện thứ nhất; một thể hiện giờ có ba biến tham chiếu.
4. `new ClickCounter("Nút A", 10)` tạo **thể hiện thứ hai** được gán cho `second`. Cùng tên và số đếm ban đầu không biến nó thành đối tượng thứ nhất.
5. `first.click()` sửa `clicks` trên thể hiện thứ nhất từ 10 lên 11. `view.value()` nhận 11 vì cùng đối tượng; `second.value()` vẫn 10 vì là một đối tượng khác.
6. Hai biểu thức `first == view` và `view == general` là `true` vì các tham chiếu tương ứng cùng trỏ một đối tượng. `first == second` là `false`.
7. `view.getClass().getSimpleName()` trả `ClickCounter` vì lớp runtime của đối tượng không đổi khi ta xem nó qua kiểu interface.

~~~mermaid
flowchart LR
    F["first: ClickCounter"] --> C1["ClickCounter #1<br/>label=Nút A; clicks=11"]
    V["view: CounterView"] --> C1
    G["general: Object"] --> C1
    S["second: ClickCounter"] --> C2["ClickCounter #2<br/>label=Nút A; clicks=10"]
~~~

Sơ đồ cho thấy **bốn biến tham chiếu** nhưng chỉ có **hai thể hiện**. Biến và đối tượng phải được đếm riêng.

## 4. Type quyết định được phép gọi gì qua biến

Trong ví dụ, cả ba biến `first`, `view`, `general` đều trỏ tới cùng đối tượng. Nhưng ở lúc biên dịch, chúng có **kiểu khai báo khác nhau**.

| Biến | Kiểu khai báo | Gọi trực tiếp được |
| --- | --- | --- |
| `first` | `ClickCounter` | `click()`, `value()`, `label()` và những method phù hợp khác |
| `view` | `CounterView` | `value()` và những method của `Object` được Java cho phép qua interface |
| `general` | `Object` | Những method công bố bởi `Object`, chẳng hạn `getClass()` |

Ví dụ:

~~~java
first.click();      // Hợp lệ: ClickCounter khai báo click().
view.value();       // Hợp lệ: CounterView khai báo value().
general.getClass(); // Hợp lệ: Object khai báo getClass().

// view.click();        // Không biên dịch: CounterView không khai báo click().
// general.value();     // Không biên dịch: Object không khai báo value().
~~~

Đây là các dòng minh họa để đặt **bên trong một phương thức** có sẵn ba biến như ở `main`, không phải file Java độc lập. Đối tượng runtime vẫn có `click()`; lỗi xảy ra vì **kiểu mà trình biên dịch nhìn thấy tại vị trí gọi** không công bố method đó. Nếu cần gọi thêm khả năng riêng, có thể giữ biến kiểu cụ thể hoặc kiểm tra kiểu rồi ép kiểu có chủ đích. Không nên ép kiểu vô điều kiện khi chưa biết lớp runtime.

**Phân biệt hai ý:** kiểu khai báo giới hạn những thao tác có thể gọi hợp lệ; với **phương thức instance được override**, lớp runtime sẽ quyết định cách triển khai được thực thi. Đây là nền tảng cho bài đa hình, nhưng không đồng nghĩa việc gán biến sang kiểu interface đã tạo ra một đối tượng mới.

### Tập hợp các kiểu Java rộng hơn class

- **Class type:** `ClickCounter`, `String`, `Object`.
- **Interface type:** `CounterView`, `Runnable`. Interface định nghĩa hợp đồng và không thể `new CounterView()` trực tiếp.
- **Primitive type:** `int`, `long`, `boolean`; giá trị primitive không phải thể hiện được tạo bằng `new`.
- **Array type:** `int[]`, `String[]`; mảng là đối tượng và có kiểu mảng riêng.
- **Các kiểu trừu tượng:** Một `abstract class` vẫn là một class/type, nhưng không thể tạo instance trực tiếp bằng `new AbstractType()`.

Hai biến có cùng kiểu khai báo có thể trỏ đến hai đối tượng khác nhau; ngược lại, hai biến có kiểu khác nhau vẫn có thể trỏ **cùng một đối tượng** nếu các kiểu tương thích.

## 5. Thể hiện, danh tính và trạng thái khác nhau ra sao?

Một thể hiện là một đối tượng cụ thể ở thời điểm chạy. Ta cần phân biệt ba mặt:

| Mặt | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Identity** | Đây có phải chính đối tượng trước đó không? | `first == view` là `true` |
| **State** | Đối tượng đang chứa thông tin gì? | `clicks` của `first` đã tăng thành 11 |
| **Behavior** | Có thể thực hiện thao tác nào? | `click()` cập nhật; `value()` truy vấn |

Đối tượng có thể đổi trạng thái mà **vẫn là chính đối tượng ấy**. Ngược lại, hai đối tượng khác nhau có thể lưu dữ liệu giống hệt nhau mà không thành một đối tượng.

~~~java
ClickCounter a = new ClickCounter("Trùng tên", 5);
ClickCounter b = new ClickCounter("Trùng tên", 5);

System.out.println(a == b);      // false
System.out.println(a.equals(b)); // false với lớp mẫu hiện tại
~~~

`a.equals(b)` trả `false` ở lớp này vì `ClickCounter` chưa override `equals`, nên kế thừa so sánh danh tính của `Object`. Nếu một lớp định nghĩa so sánh bằng giá trị, hai instance khác nhau có thể `equals` nhau theo quy tắc đó. Do vậy:

- `==` giữa các tham chiếu kiểm tra **có cùng đối tượng**.
- `equals(...)` phản ánh **quy tắc bằng nhau do lớp cung cấp**.
- Dữ liệu nghiệp vụ trùng nhau (ví dụ cùng mã đơn hàng) không tự động làm các tham chiếu trỏ tới một đối tượng; sự duy nhất của mã nghiệp vụ là một quy tắc khác.

Một lớp có thể mô tả đối tượng **bất biến** (không thay đổi trạng thái quan sát được sau khởi tạo). Việc một đối tượng mutable hay immutable là quyết định thiết kế, không quyết định nó có phải thể hiện của lớp hay không.

## 6. Ba thao tác thường bị nhầm: new, gán tham chiếu, thay đổi trạng thái

~~~java
ClickCounter x = new ClickCounter("X", 3); // Tạo đối tượng thứ nhất.
ClickCounter y = x;                        // Không tạo đối tượng mới.
x = new ClickCounter("Z", 7);              // Tạo đối tượng thứ hai rồi gán lại x.

y.click();
System.out.println(y.value()); // 4
System.out.println(x.value()); // 7
~~~

Đoạn mã này cũng được đặt trong một phương thức, và dùng định nghĩa `ClickCounter` từ ví dụ chính.

Điểm khác biệt:

- `new ClickCounter(...)` tạo một đối tượng mới với trạng thái ban đầu được constructor kiểm tra.
- `ClickCounter y = x` sao chép **giá trị tham chiếu**, không sao chép đối tượng; `x` và `y` cùng trỏ đến đối tượng X cho đến khi một biến được gán lại.
- `x = new ClickCounter("Z", 7)` chỉ thay đổi đối tượng mà **biến x** trỏ tới; không tự thay đổi đối tượng cũ mà `y` đang trỏ.
- `y.click()` thay đổi **nội dung đối tượng X** qua biến `y`; nó không tác động đến đối tượng Z.

Biến tham chiếu cũng có thể chứa `null`:

~~~java
CounterView missing = null;
// missing.value(); // Nếu bỏ chú thích sẽ ném NullPointerException.
~~~

`null` không phải là “một thể hiện rỗng” của `CounterView` hay `ClickCounter`. Một biến cục bộ khai báo nhưng chưa được gán (`CounterView c;`) cũng không được đọc/gọi trước khi được gán giá trị hợp lệ theo kiểm tra definite assignment của Java.

## 7. Instance member và static member là hai chuyện khác

Một **instance field** không có từ khóa `static` được lưu riêng cho từng đối tượng. Trong ví dụ, `first` và `second` có hai giá trị `clicks` độc lập. Nếu thêm một field `static int createdCount` vào lớp và tăng nó trong constructor, đó sẽ là một bộ đếm chung theo lớp được nạp, chứ không phải mỗi thể hiện có một `createdCount` riêng.

~~~java
class Sample {
    static int createdCount;
    int value;

    Sample() {
        createdCount++;
    }
}

Sample a = new Sample();
Sample b = new Sample();
a.value = 9;

System.out.println(a.value);            // 9
System.out.println(b.value);            // 0
System.out.println(Sample.createdCount); // 2
~~~

Đoạn dùng thử phải nằm trong một method; không chèn trần các câu lệnh phía sau khai báo class. Dữ liệu `static` thuộc lớp (trong phạm vi lớp đã được nạp), còn dữ liệu `instance` thuộc đối tượng. Việc có cùng kiểu không khiến mọi field của đối tượng được chia sẻ.

Ngược lại, hai instance field riêng biệt chứa **tham chiếu** vẫn có thể cùng trỏ đến một đối tượng mutable khác. “Mỗi instance có field riêng” không có nghĩa cả đồ thị đối tượng đều tự động được sao chép sâu.

## 8. Tránh các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Khai báo class là tạo object.” | Khai báo tạo định nghĩa; cần có hành động tạo hoặc nhận đối tượng ở runtime. |
| “`CounterView c;` tạo bộ đếm.” | Nó chỉ khai báo biến; chưa có thể hiện nào được tạo từ dòng đó. |
| “Có hai tên kiểu thì có hai đối tượng.” | Một object có thể dùng qua nhiều kiểu và nhiều biến tham chiếu. |
| “`view` có kiểu interface nên đối tượng không có `click()`.” | Method vẫn thuộc lớp runtime; chỉ không được gọi trực tiếp qua kiểu interface không công bố method đó. |
| “Gán `b = a` sao chép toàn bộ field.” | Chỉ sao chép tham chiếu; thay đổi trạng thái qua một biến được thấy qua biến kia nếu cùng object. |
| “Hai object cùng field có cùng identity.” | Cùng giá trị không đồng nghĩa cùng object. |
| “`null` là một đối tượng mặc định.” | `null` không tham chiếu tới đối tượng nào. |
| “Mọi kiểu Java đều có thể new.” | Primitive, interface và abstract class không được khởi tạo trực tiếp bằng `new`. |
| “Class nào cũng phải chứa mutable state.” | Đối tượng có thể bất biến, không có instance field hoặc chỉ cung cấp hành vi. |
| “Mọi field cùng class đều thuộc mỗi instance.” | Field `static` thuộc lớp, không phải bản riêng cho từng đối tượng. |

Nhận ra class/type/instance còn giúp hiểu lý do code chỉ dùng biến `CounterView` không cần biết đầy đủ chi tiết triển khai của `ClickCounter`. Đây là sự tách biệt giữa **hợp đồng có thể nhìn thấy** và **đối tượng thực tế**, rất hữu ích khi học tiếp interface và đa hình.

## 9. Tự kiểm tra trước khi chạy

**Câu 1.** Cho `ClickCounter a = new ClickCounter("A", 1); ClickCounter b = a;`. Sau `b.click()`, `a.value()` bằng bao nhiêu?

**Đáp án:** `2`. Hai biến trỏ cùng một thể hiện, nên lời gọi qua `b` làm tăng trạng thái mà `a` cũng quan sát được.

**Câu 2.** Thay `ClickCounter b = a;` bằng `ClickCounter b = new ClickCounter("A", 1);`. Sau `b.click()`, `a.value()` bằng bao nhiêu?

**Đáp án:** `1`. Hai lần `new` tạo hai đối tượng; cùng nhãn không làm chúng chia sẻ trạng thái.

**Câu 3.** Với `CounterView view = new ClickCounter("A", 1);`, gọi `view.click()` có biên dịch không? Có thể gọi `view.value()` không?

**Đáp án:** `view.click()` không biên dịch vì kiểu `CounterView` không công bố `click()`. `view.value()` hợp lệ. Đối tượng runtime vẫn thuộc lớp `ClickCounter`.

**Câu 4.** Viết `CounterView view = null;` có tạo instance nào không? Lời gọi `view.value()` dẫn tới gì?

**Đáp án:** Không tạo instance; gọi instance method qua tham chiếu null gây `NullPointerException`.

**Câu 5.** Một instance có kiểu runtime `ClickCounter` có thể được tham chiếu qua `Object` không? Sau phép gán đó, lớp runtime có đổi không?

**Đáp án:** Có thể dùng `Object x = first;`. Phép gán không làm đổi lớp runtime của đối tượng; `x.getClass()` vẫn là `ClickCounter.class`.

**Câu 6.** Vì sao `ClickCounter` là một class và cũng là một type, còn `CounterView` là type nhưng không phải class?

**Đáp án:** Class định nghĩa kiểu lớp và phần triển khai; interface công bố hợp đồng kiểu mà lớp có thể implements. Java có nhiều loại type nên không thể đồng nhất “type” với “class”.

Khi đọc mã OOP, hãy chỉ ra **lớp tạo đối tượng, kiểu khai báo của biến, số lần thực sự tạo thể hiện và các tham chiếu cùng trỏ một thể hiện**. Nếu còn xác định được method nào trình biên dịch cho phép gọi và đối tượng nào thực hiện lời gọi đó, bạn đã có nền tảng vững để học đóng gói, kế thừa và đa hình.