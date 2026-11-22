# Tham chiếu `final` không đổi nhưng đối tượng vẫn có thể thay đổi

> **Java core — language-basics / Biến và hằng**  
> **Môi trường:** Java 17+, chỉ sử dụng thư viện chuẩn.  
> **Mục tiêu:** Giải thích chính xác `final` ràng buộc **biến tham chiếu** chứ không tự khóa **trạng thái đối tượng**; phân biệt gán lại tham chiếu với thay đổi object, hiểu alias, mảng và collection, và nhận ra khi nào object thật sự bất biến.

## 1. `final` ràng buộc cái gì?

Khi khai báo:

~~~java
final StringBuilder message = new StringBuilder("Java");
message.append(" 17");                   // Hợp lệ: sửa object đang được tham chiếu.
// message = new StringBuilder("Kotlin"); // Lỗi biên dịch: gán lại biến final.
~~~

Có **hai đối tượng cần phân biệt về mặt khái niệm**:

- **Biến `message`:** một biến tham chiếu đã được gán đúng một lần. Từ khóa `final` ngăn **gán lại biến ấy** sang tham chiếu khác.
- **Đối tượng `StringBuilder`:** dữ liệu bên trong có thể được phương thức `append` thay đổi. `final` trên biến `message` **không** biến đối tượng này thành bất biến.

Bảng so sánh:

| Thao tác với `final StringBuilder message` | Hợp lệ? | Lý do |
| --- | --- | --- |
| `message.append("!");` | Có | Thay đổi trạng thái của object |
| `message.setLength(0);` | Có | Sửa object qua method |
| `message = new StringBuilder();` | Không | Gán lại biến `final` |
| `message = message;` | Không | Vẫn là phép gán lại, kể cả RHS là chính tham chiếu đó |
| `System.out.println(message);` | Có | Đọc/tham chiếu object, không gán lại |

**Ghi nhớ:** `final` trên tham chiếu mang nghĩa “**không đổi đối tượng mà biến này trỏ tới**”, chứ không có nghĩa “**mọi byte của đối tượng đều bị khóa**”.

## 2. Chương trình Java 17+ chạy được

Tạo tệp **FinalReferenceDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class FinalReferenceDemo {
    static class Counter {
        private int value;

        Counter(int value) {
            this.value = value;
        }

        void increment() {
            value++;
        }

        int getValue() {
            return value;
        }
    }

    private static void increase(final Counter target) {
        target.increment(); // Được: sửa object.
//      target = new Counter(0); // Sai: gán lại tham số final.
    }

    public static void main(String[] args) {
        final Counter counter = new Counter(10);
        Counter alias = counter;

        increase(counter);
        alias.increment();
        System.out.println("counter=" + counter.getValue());
        System.out.println("sameObject=" + (counter == alias));

        final int[] numbers = {1, 2, 3};
        numbers[0] = 9;
        System.out.println("array=" + Arrays.toString(numbers));

        final StringBuilder builder = new StringBuilder("Java");
        builder.append(" 17");
        System.out.println("builder=" + builder);

        final List<String> names = new ArrayList<>();
        names.add("Lan");
        names.add("Mai");
        System.out.println("names=" + names);

        final String language = "java";
        String upper = language.toUpperCase();
        System.out.println("string=" + language + ", upper=" + upper);

        final List<String> unmodifiable = List.of("A", "B");
        try {
            unmodifiable.add("C");
        } catch (UnsupportedOperationException exception) {
            System.out.println("listOfAdd=blocked");
        }

//      counter = new Counter(99); // Sai: gán lại biến final.
//      numbers = new int[3];      // Sai: gán lại biến final.
//      builder = new StringBuilder(); // Sai: gán lại biến final.
    }
}
~~~

Chạy trong thư mục chứa tệp bằng Bash, PowerShell hoặc Command Prompt:

~~~bash
javac -encoding UTF-8 FinalReferenceDemo.java
java FinalReferenceDemo
~~~

**Expected output chính xác:**

~~~text
counter=12
sameObject=true
array=[9, 2, 3]
builder=Java 17
names=[Lan, Mai]
string=java, upper=JAVA
listOfAdd=blocked
~~~

**Diễn giải:**

1. `counter` và `alias` trỏ tới **cùng một object**. `increase(counter)` tăng từ 10 lên 11; `alias.increment()` tăng tiếp thành 12. Biến `counter` không được gán lại lần nào.
2. `numbers` luôn giữ tham chiếu tới cùng mảng, nhưng `numbers[0] = 9` được phép: `final` **không khóa phần tử mảng**.
3. `builder.append` và `names.add` thay đổi các object có tính mutable.
4. `String` là kiểu **immutable**. `toUpperCase()` cho ra chuỗi khác `"JAVA"`, không sửa nội dung chuỗi `language` đang trỏ tới.
5. `List.of("A", "B")` tạo danh sách **không cho thêm/xóa/thay thế phần tử**; gọi `add` ném `UnsupportedOperationException`. Điều này là **tính chất của đối tượng danh sách**, không đến từ biến `final`.

Những dòng mã sai về phép gán lại đang được comment để chương trình chính vẫn biên dịch. Bạn có thể **bỏ comment từng dòng riêng** để xem thông báo lỗi compiler, rồi đưa lại về comment trước khi chạy.

## 3. Vì sao alias vẫn sửa được object?

Giả sử:

~~~java
final Counter original = new Counter(1);
Counter otherName = original;

otherName.increment(); // original.getValue() cũng trở thành 2.
~~~

Sơ đồ quan hệ tham chiếu:

~~~mermaid
flowchart LR
    A["final original"] --> O["Counter object: value = 2"]
    B["otherName"] --> O
    C["otherName.increment()"] --> O
~~~

`final` chỉ ràng buộc phép gán cho tên `original`. Nó **không thu hồi** các tham chiếu khác và không cấm object nhận thay đổi qua:

- Một **alias** (`otherName`).
- Một **phương thức** nhận tham số tham chiếu (`increase(final Counter target)`).
- Một **field** hoặc một collection khác đang giữ tham chiếu tới object.

Bởi vậy, chỉ nhìn thấy `final` ở nơi khai báo là **chưa đủ** để kết luận trạng thái object sẽ giữ nguyên suốt vòng đời chương trình.

## 4. Phân biệt `final`, immutable và unmodifiable

| Khái niệm | Ràng buộc điều gì? | Ví dụ |
| --- | --- | --- |
| **Biến tham chiếu `final`** | Không được gán lại tham chiếu đã gán | `final StringBuilder b = new StringBuilder();` |
| **Object mutable** | Trạng thái bên trong có thể đổi | `b.append("X")`, `list.add("X")`, `array[0] = 2` |
| **Object immutable** | API/thiết kế object không cho đổi trạng thái quan sát được sau khi tạo | `String`, `Integer` |
| **Unmodifiable collection** | Không thể sửa cấu trúc/phần tử qua các thao tác thay đổi của collection | `List.of("A", "B")` |

Một biến **không có `final`** vẫn có thể giữ object bất biến:

~~~java
String label = "A";
label = "B"; // Đổi tham chiếu tới String khác; không sửa object "A".
~~~

Một biến **có `final`** lại hoàn toàn có thể trỏ tới object mutable:

~~~java
final List<String> labels = new ArrayList<>();
labels.add("A"); // Được.
~~~

`List.of` ngăn thay đổi **cấu trúc/danh sách phần tử** qua API của nó; nhưng nếu phần tử bên trong là object mutable, **trạng thái phần tử đó vẫn có thể đổi**. Đừng xem “danh sách không sửa được” là bảo đảm bất biến sâu (*deep immutability*) của cả đồ thị object.

## 5. Áp dụng với biến cục bộ, tham số và field

`final` có thể gắn với **biến cục bộ**, **tham số phương thức** hoặc **field**:

~~~java
class Basket {
    private final List<String> items = new ArrayList<>();

    void add(String item) {
        items.add(item); // Được: sửa List đang tham chiếu.
    }

    int size() {
        return items.size();
    }

//  void reset() {
//      items = new ArrayList<>(); // Sai: gán lại final field.
//  }
}
~~~

- Với **biến cục bộ `final`**, Java cho phép gán lần đầu theo đúng quy tắc definite assignment, nhưng không cho phép gán lại sau đó.
- Với **tham số `final`**, code trong phương thức không được gán tham số sang object khác; nó vẫn có thể gọi method làm đổi object truyền vào.
- Với **field `final`**, nó phải được khởi tạo hợp lệ (ví dụ ngay tại khai báo hoặc trong constructor với instance field). Sau khi được gán, field không được gán lại theo cách Java thông thường.

Đối với **primitive**, `final` ngăn thay đổi chính giá trị của biến vì primitive lưu giá trị thay vì tham chiếu:

~~~java
final int maxItems = 10;
// maxItems++; // Lỗi: cố thay đổi biến final.
~~~

Đó là lý do `final int` thường trông như một hằng, còn `final SomeMutableObject` **không** hứa rằng object là hằng.

## 6. Bẫy thường gặp và hướng xử lý

| Hiểu nhầm / triệu chứng | Điều đúng |
| --- | --- |
| “`final` làm cho `ArrayList` bất biến.” | Sai. `final` cấm gán lại biến, `add` vẫn sửa được danh sách mutable. |
| “`final int[] a` không sửa được `a[0]`.” | Sai. Phần tử mảng vẫn có thể đổi. |
| “`final String s` rồi gọi `toUpperCase()` sẽ đổi `s`.” | Sai. `String` bất biến; method trả String khác hoặc một kết quả phù hợp, không sửa `s`. |
| “Gán `x = x` không tính là gán lại.” | Sai khi `x` là biến `final` đã được gán. |
| “Đổi object qua alias thì biến `final` sẽ chặn.” | Sai. Alias có thể sửa trạng thái object, không gán lại biến `final`. |
| “`List.of(...)` không sửa được nhờ từ khóa `final`.” | Sai. Đối tượng List không hỗ trợ thao tác sửa; dù biến không `final`, các phép `add` vẫn bị chặn. |
| “`final` bảo đảm an toàn giữa các thread.” | Sai. Object mutable vẫn có thể bị truy cập/sửa đồng thời; cần thiết kế đồng bộ hoặc immutable phù hợp. |

Nếu cần bảo vệ dữ liệu khỏi thay đổi không mong muốn, hãy xem xét **loại object và cách chia sẻ tham chiếu**, không chỉ thêm `final`:

- Chọn **kiểu immutable** khi phù hợp, ví dụ `String` và các kiểu giá trị được thiết kế bất biến.
- Tránh để lộ object mutable trực tiếp; dùng **defensive copy** nếu cần cách ly dữ liệu.
- Với collection, cân nhắc API tạo bản sao không sửa được như `List.copyOf` theo hợp đồng dữ liệu; chú ý không đồng nghĩa sao chép sâu mọi phần tử.
- Với truy cập đa luồng, cần kiểm soát đồng bộ/trạng thái chung; `final` một mình không phải khóa (*lock*).

## 7. Bài tập tự kiểm tra

**Bài 1.** Cho `final int[] a = {1, 2};`. Dòng `a[1] = 5;` có biên dịch không? Còn `a = new int[]{3, 4};`? Giải thích thứ gì thay đổi.

**Bài 2.** Dùng hai tên tham chiếu cùng một `StringBuilder`, trong đó tên thứ nhất có `final`. Gọi `append` từ tên thứ hai rồi in tên thứ nhất: dự đoán kết quả.

**Bài 3.** Cho `final List<String> a = new ArrayList<>();`. `a.add("x")` hợp lệ không? Đổi cách tạo thành `List.of("x")` rồi thử `add("y")`; xác định bước nào là lỗi compiler, bước nào là exception khi chạy.

**Bài 4.** Viết `final String s = "Java";` rồi gọi `s.concat(" 17");`. Chuỗi `s` có đổi không? Làm thế nào dùng được kết quả nối mà không gán lại `s`?

**Bài 5.** Trong `FinalReferenceDemo`, để `Counter alias = counter;` rồi gọi `alias.increment()` hai lần; kiểm tra giá trị in từ `counter`. Biến `final` đã đổi hay object đã đổi?

### Kết luận

**`final` trên biến tham chiếu ngăn phép gán lại biến, không đóng băng object.** Đối tượng có thể thay đổi qua cùng biến, method nhận tham chiếu hoặc alias nếu bản thân nó mutable. Tính bất biến là **thuộc tính của thiết kế object/API**; còn an toàn đa luồng và chống thay đổi qua alias là những yêu cầu riêng cần được giải quyết bằng thiết kế phù hợp.
