# Một lớp tạo nhiều đối tượng có trạng thái độc lập

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **lớp (class)** là khuôn mẫu định nghĩa dữ liệu/hành vi với **đối tượng (object/instance)** là một thực thể được tạo từ lớp đó.
- Giải thích vì sao hai lần khởi tạo thành công bằng `new` tạo hai đối tượng khác nhau, mỗi đối tượng giữ các giá trị của **trường thực thể (instance fields)** riêng.
- Phân biệt tạo đối tượng mới với gán thêm **tham chiếu (reference)** đến một đối tượng có sẵn.
- Nhận biết trường `static`, đối tượng thành viên dùng chung và các trường hợp khiến trạng thái hai đối tượng ảnh hưởng nhau.
- Kiểm chứng tính độc lập bằng ví dụ Java chạy được và áp dụng đóng gói để quản lý trạng thái.

## 1. Một lớp, nhiều đối tượng nghĩa là gì?

**Lớp** mô tả các trường dữ liệu, constructor và phương thức mà các thực thể thuộc loại đó có thể sử dụng. **Đối tượng** là một thực thể cụ thể của lớp, với trạng thái của chính nó tại một thời điểm.

Ví dụ, lớp `Counter` quy định mỗi bộ đếm có tên `name` và giá trị `value`. Ta có thể tạo bộ đếm A và bộ đếm B từ cùng lớp mà không cần viết hai định nghĩa lớp khác nhau. Cả hai gọi cùng mã của phương thức `increment()`, nhưng phương thức thao tác trên đối tượng nhận lời gọi:

- `a.increment()` thay đổi trường `value` thuộc đối tượng mà `a` tham chiếu.
- `b.increment()` thay đổi trường `value` thuộc đối tượng mà `b` tham chiếu.
- Khi `a` và `b` tham chiếu hai đối tượng khác nhau, và không chia sẻ dữ liệu có thể thay đổi, cập nhật A không làm đổi giá trị B.

**Điều kiện quan trọng:** “Trạng thái độc lập” nói đến vùng trạng thái thực sự thuộc từng đối tượng, đặc biệt các trường thực thể kiểu nguyên thủy hoặc các đối tượng thành viên riêng biệt. Nó không có nghĩa là mọi đối tượng trong chương trình hoàn toàn không thể chia sẻ dữ liệu.

## 2. Ví dụ hoàn chỉnh: hai bộ đếm độc lập

Lưu chương trình dưới tên **`CounterDemo.java`**:

~~~java
public class CounterDemo {
    static final class Counter {
        private final String name; // Thuộc từng Counter
        private int value;         // Thuộc từng Counter, mặc định là 0

        private static int totalCreated; // Chung cho lớp Counter

        Counter(String name) {
            this.name = name;
            totalCreated++;
        }

        void increment() {
            value++;
        }

        String name() {
            return name;
        }

        int value() {
            return value;
        }

        static int totalCreated() {
            return totalCreated;
        }
    }

    public static void main(String[] args) {
        Counter a = new Counter("A");
        Counter b = new Counter("B");

        a.increment();
        a.increment();
        b.increment();

        System.out.println("a = " + a.name() + ":" + a.value());
        System.out.println("b = " + b.name() + ":" + b.value());
        System.out.println("created = " + Counter.totalCreated());
        System.out.println("a == b: " + (a == b));

        Counter alias = a;
        alias.increment();
        System.out.println("a after alias: " + a.value());
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac CounterDemo.java
java CounterDemo
~~~

Kết quả chuẩn của chương trình:

~~~text
a = A:2
b = B:1
created = 2
a == b: false
a after alias: 3
~~~

**Phân tích lần lượt:**

1. `new Counter("A")` tạo đối tượng thứ nhất; `new Counter("B")` tạo đối tượng thứ hai. Hai biến `a` và `b` giữ hai tham chiếu khác nhau.
2. Mỗi đối tượng có trường `name` và `value` của riêng nó. Hai lời gọi `a.increment()` nâng A lên 2; một lời gọi `b.increment()` nâng B lên 1.
3. `totalCreated` được khai báo `static`, nên không có một bản `totalCreated` riêng cho A và B. Constructor tăng cùng một trường của lớp; sau hai lần tạo, giá trị là 2.
4. `a == b` là `false` vì đây là hai tham chiếu tới hai đối tượng khác nhau.
5. `Counter alias = a` **không tạo bộ đếm thứ ba**. `alias` và `a` cùng tham chiếu đối tượng A; gọi `alias.increment()` khiến `a.value()` thành 3. Biến `totalCreated` vẫn là 2.

Tại thời điểm sau ba lời gọi `increment()` đầu tiên, có thể hình dung:

~~~text
Biến tham chiếu                 Hai đối tượng Counter
a --------------------------->  #1 { name: "A", value: 2 }
b --------------------------->  #2 { name: "B", value: 1 }

Counter.totalCreated = 2        (trường của lớp)
~~~

Sau câu lệnh `Counter alias = a`, cả hai biến `a` và `alias` cùng hướng tới đối tượng #1. Hình trên là **mô hình khái niệm**, không phải cam kết về bố trí vật lý trong bộ nhớ JVM.

## 3. Trường thực thể và trường lớp khác nhau thế nào?

| Tiêu chí | Trường thực thể (không có `static`) | Trường lớp (có `static`) |
| --- | --- | --- |
| Gắn với | Từng đối tượng được tạo | Lớp trong ngữ cảnh lớp được nạp |
| Số bản trạng thái | Mỗi đối tượng có trường tương ứng riêng | Một trường lớp được dùng chung trong ngữ cảnh đó |
| Truy cập thông thường | `object.field` hoặc qua phương thức của object | `ClassName.field` hoặc qua phương thức `static` |
| Thay đổi giá trị | Chỉ thay đổi trường trên đối tượng đích | Các đối tượng cùng dùng/truy cập trạng thái lớp sẽ thấy thay đổi |
| Ví dụ | `private int value;` | `private static int totalCreated;` |

Trong ví dụ, Java thực thi mã `increment()` theo đối tượng đang nhận lời gọi; biểu thức `value++` tương đương thao tác trên `this.value`. Cùng một phương thức, nhưng `this` khác nhau ở `a.increment()` và `b.increment()`.

Giá trị ban đầu của trường thực thể kiểu `int` là `0` nếu constructor không gán giá trị khác. Các trường kiểu nguyên thủy còn có giá trị mặc định riêng (ví dụ `boolean` là `false`); trường tham chiếu mặc định là `null`. **Biến cục bộ** phải được gán trước khi đọc, không tự động tuân theo quy tắc giá trị mặc định của trường.

Khai báo `final` trên trường như `private final String name` có nghĩa là trường chỉ được gán theo quy tắc khởi tạo và không thể được gán lại sau khi đã khởi tạo đối tượng; nó không khiến toàn bộ đối tượng trở thành bất biến. Trong ví dụ, `value` vẫn có thể tăng.

**Lưu ý giới hạn:** Các thực thể còn có thể gặp trạng thái dùng chung khác, chẳng hạn biến `static`, cache hoặc dịch vụ được truyền chung. Ngoài ra, cập nhật `totalCreated++` trong ví dụ chỉ nhằm minh họa trạng thái lớp ở chương trình đơn luồng; nếu nhiều luồng tạo đối tượng đồng thời, phép tăng này không bảo đảm tính nguyên tử.

## 4. `new` tạo đối tượng; phép gán tham chiếu không tạo đối tượng

Xem ba câu lệnh:

~~~java
Counter a = new Counter("A");
Counter b = new Counter("B");
Counter c = a;
~~~

Đây là đoạn minh họa dùng lớp `Counter` ở ví dụ trước, không phải chương trình độc lập. Sau khi ba câu lệnh chạy thành công:

- Có **hai đối tượng** `Counter`: một cho A, một cho B.
- Có **ba biến tham chiếu**: `a`, `b`, `c`.
- `a == c` là `true` vì chúng cùng tham chiếu đối tượng A; `a == b` là `false`.
- Thay đổi đối tượng thông qua `c` cũng quan sát được thông qua `a`; thay đổi đối tượng qua `b` không tác động trực tiếp đến A.

Trong Java, biến kiểu lớp chứa **giá trị tham chiếu**, không chứa nguyên đối tượng. Gán `c = a` chép giá trị tham chiếu; nó không tự tạo bản sao của đối tượng. Việc truyền một tham chiếu vào tham số phương thức cũng truyền **bản sao của giá trị tham chiếu**, vì Java luôn truyền tham số theo giá trị. Phương thức có thể sửa đối tượng mà tham chiếu đó trỏ tới, nhưng gán lại biến tham số không làm biến tham chiếu bên ngoài đổi sang đối tượng mới.

Hai đối tượng có cùng nội dung trường vẫn có thể là hai đối tượng khác nhau. Toán tử `==` đối với tham chiếu kiểm tra chúng có trỏ cùng một đối tượng hay không; `equals()` biểu diễn quan hệ bằng nhau do lớp quy định (mặc định kế thừa từ `Object` thì dựa trên đồng nhất tham chiếu). Không dùng `==` để kết luận hai đối tượng có dữ liệu giống nhau.

## 5. Vì sao hai đối tượng khác nhau vẫn có thể ảnh hưởng nhau?

Các trường thực thể là những vị trí lưu dữ liệu riêng, nhưng **giá trị của trường tham chiếu** có thể trỏ đến cùng một đối tượng có thể thay đổi. Ví dụ hai hồ sơ khác nhau cùng giữ một tham chiếu tới `ArrayList`. Khi một hồ sơ thêm phần tử vào danh sách chung, hồ sơ còn lại thấy phần tử mới.

Lưu mã sau vào **`SharedStateDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SharedStateDemo {
    static final class UnsafeProfile {
        private final List<String> tags;

        UnsafeProfile(List<String> tags) {
            this.tags = tags; // Giữ tham chiếu của caller
        }

        void addTag(String tag) {
            tags.add(tag);
        }

        List<String> tags() {
            return List.copyOf(tags);
        }
    }

    static final class SafeProfile {
        private final List<String> tags;

        SafeProfile(List<String> tags) {
            this.tags = new ArrayList<>(tags); // Tạo danh sách riêng
        }

        void addTag(String tag) {
            tags.add(tag);
        }

        List<String> tags() {
            return List.copyOf(tags); // Trả snapshot không sửa được
        }
    }

    public static void main(String[] args) {
        List<String> shared = new ArrayList<>();
        UnsafeProfile p1 = new UnsafeProfile(shared);
        UnsafeProfile p2 = new UnsafeProfile(shared);

        p1.addTag("java");
        System.out.println("unsafe p2: " + p2.tags());

        SafeProfile safe1 = new SafeProfile(shared);
        SafeProfile safe2 = new SafeProfile(shared);
        safe1.addTag("oop");

        System.out.println("safe1: " + safe1.tags());
        System.out.println("safe2: " + safe2.tags());
    }
}
~~~

Chạy:

~~~bash
javac SharedStateDemo.java
java SharedStateDemo
~~~

Kết quả:

~~~text
unsafe p2: [java]
safe1: [java, oop]
safe2: [java]
~~~

Ở hai đối tượng `UnsafeProfile`, các trường `tags` là **hai trường riêng** nhưng cả hai chứa **cùng tham chiếu** tới một `ArrayList`. Trạng thái danh sách vì thế được chia sẻ. Ở `SafeProfile`, constructor sao chép các phần tử sang `ArrayList` mới. Thay đổi danh sách bên trong `safe1` không lan sang `safe2`. Phương thức `tags()` trả một danh sách không cho sửa trực tiếp.

Cách sao chép `new ArrayList<>(tags)` là **sao chép nông (shallow copy)**: danh sách mới vẫn chứa tham chiếu đến các phần tử cũ. Trong ví dụ, phần tử là `String` bất biến nên đủ để minh họa tách trạng thái danh sách. Nếu phần tử là đối tượng có thể thay đổi, hai danh sách vẫn có thể chia sẻ các phần tử đó; khi cần cách ly sâu, phải xem xét sao chép từng phần tử theo hợp đồng dữ liệu thích hợp.

**Phân biệt:** Hai đối tượng cùng trỏ một `String` không gây vấn đề sửa nội dung vì `String` bất biến. Ngược lại, `final List<String> tags` chỉ ngăn gán lại tham chiếu `tags`; nó không tự ngăn `tags.add(...)`.

## 6. Thiết kế đối tượng có trạng thái độc lập

Khi một đối tượng cần tự quản lý dữ liệu, hãy xét các bước:

1. **Đặt trạng thái thuộc từng thực thể vào instance fields**, chẳng hạn `balance` của mỗi tài khoản hoặc `quantity` của mỗi giỏ hàng. Chỉ dùng `static` cho trạng thái thật sự thuộc lớp hoặc được chia sẻ có chủ đích.
2. **Khởi tạo bằng constructor** để mỗi đối tượng nhận giá trị ban đầu hợp lệ. Dùng `this.field` khi cần phân biệt trường với tham số cùng tên.
3. **Đóng gói trạng thái** bằng trường `private` và phương thức thể hiện hành vi (`deposit`, `increment`, `addItem`) để kiểm soát điều kiện cập nhật. Chỉ công khai getter/setter khi phù hợp thiết kế.
4. **Kiểm soát tham chiếu tới dữ liệu có thể thay đổi**: tạo mới cấu trúc dữ liệu trong constructor, sao chép phòng vệ khi nhận/trả dữ liệu, hoặc thiết kế kiểu bất biến nếu yêu cầu.
5. **Kiểm thử trên ít nhất hai đối tượng**: chụp trạng thái B, thay đổi A, rồi xác nhận B không đổi; đồng thời thử trường hợp hai biến cùng tham chiếu một đối tượng để hiểu khác biệt.

Một ví dụ kiểm thử theo tư duy “A thay đổi, B giữ nguyên”, giả sử dùng lớp `Counter` trong `CounterDemo`:

~~~java
Counter a = new Counter("A");
Counter b = new Counter("B");
a.increment();

if (a.value() != 1 || b.value() != 0) {
    throw new AssertionError("Two counters must have independent values");
}
~~~

Đoạn kiểm tra này là ví dụ chèn trong một phương thức có thể truy cập `Counter`, không phải tệp Java chạy độc lập. Khác với câu lệnh `assert` của Java vốn mặc định có thể bị vô hiệu hóa nếu không bật `-ea`, việc ném `AssertionError` ở đây không phụ thuộc cờ kích hoạt assertion.

## 7. Sai lầm phổ biến và cách nhận biết

| Nhầm lẫn | Điều đúng cần nhớ |
| --- | --- |
| “Một lớp chỉ có một đối tượng.” | Có thể khởi tạo nhiều đối tượng từ cùng lớp. Mỗi lần `new` thành công tạo một đối tượng mới. |
| “Hai biến cùng kiểu luôn chứa hai đối tượng khác nhau.” | Hai biến có thể giữ cùng một tham chiếu; `b = a` không tạo đối tượng mới. |
| “Mọi trường trong lớp đều có bản riêng.” | Trường `static` thuộc trạng thái lớp, được chia sẻ trong ngữ cảnh nạp lớp tương ứng. |
| “Hai đối tượng khác nhau thì không thể ảnh hưởng nhau.” | Chúng có thể tham chiếu cùng đối tượng con có thể thay đổi hoặc cùng dùng trạng thái `static`/dịch vụ chia sẻ. |
| “Khai báo `final` làm danh sách bất biến.” | `final` khóa việc gán lại trường tham chiếu, không đóng băng đối tượng được tham chiếu. |
| “Sao chép danh sách là sao chép sâu.” | `new ArrayList<>(old)` tạo danh sách mới nhưng vẫn chia sẻ các phần tử kiểu tham chiếu. |
| “`a == b` so sánh nội dung hai đối tượng.” | Với biến tham chiếu, `==` so sánh đồng nhất đối tượng; `equals()` có thể được định nghĩa để so sánh nội dung. |

## 8. Tự kiểm tra

**Câu 1.** Nếu tạo `Counter x = new Counter("X"); Counter y = new Counter("Y");` rồi chỉ gọi `x.increment()`, `y.value()` là bao nhiêu?  
**Đáp án:** `0`, vì `y` giữ một đối tượng khác với trường `value` riêng chưa tăng.

**Câu 2.** Nếu sau đó chạy `Counter z = x; z.increment();`, số đối tượng mới là bao nhiêu và `x.value()` bằng bao nhiêu?  
**Đáp án:** Không tạo thêm đối tượng nào; `z` chỉ là bí danh của `x`. `x.value()` thành `2`.

**Câu 3.** Hai đối tượng khác nhau cùng giữ một `List` có thể thay đổi. Chỉ cập nhật một đối tượng thì đối tượng kia có luôn độc lập không?  
**Đáp án:** Không. Nếu chúng cùng trỏ một `List`, sửa danh sách sẽ quan sát được từ cả hai. Muốn tách trạng thái cần tạo bản danh sách riêng hoặc dùng thiết kế bất biến thích hợp.

**Câu 4.** Vì sao `Counter.totalCreated()` tăng khi tạo cả A lẫn B, trong khi `a.value()` và `b.value()` không tự động tăng lẫn nhau?  
**Đáp án:** `totalCreated` là trường `static` dùng chung, còn `value` là trường thực thể thuộc từng `Counter`.

**Ghi nhớ:** Một lớp có thể sinh nhiều đối tượng; mỗi đối tượng có các trường thực thể riêng. Tuy nhiên, tính độc lập của **toàn bộ trạng thái** còn phụ thuộc liệu các trường đó có tham chiếu tới dữ liệu có thể thay đổi được chia sẻ hay không, và liệu lớp có dùng trạng thái `static` hoặc tài nguyên chung hay không.
