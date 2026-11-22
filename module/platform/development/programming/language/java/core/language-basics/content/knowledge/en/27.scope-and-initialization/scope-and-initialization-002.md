# Thời gian tồn tại của biến khác phạm vi sử dụng tên trong Java

## 1. Hai khái niệm không đồng nhất

Khi nói về biến Java, cần phân biệt **scope** (*phạm vi sử dụng tên*) với **lifetime** (*thời gian tồn tại khi chạy chương trình*).

- **Phạm vi sử dụng tên (scope)** là phần văn bản mã nguồn mà trình biên dịch cho phép dùng **tên định danh** để tham chiếu tới một khai báo. Đây chủ yếu là quy tắc tĩnh, được kiểm tra khi biên dịch.
- **Thời gian tồn tại của biến (variable lifetime)** liên quan tới thời điểm một lần thực thi tạo và ngừng sử dụng thực thể biến đó. Nó phụ thuộc loại biến: biến cục bộ/tham số, trường của đối tượng, hay trường `static`.
- **Thời gian tồn tại của đối tượng** lại là chuyện riêng. Đối tượng được tạo bằng `new` có thể vẫn được tham chiếu sau khi biến cục bộ ban đầu ra khỏi scope. JVM quản lý khả năng thu gom đối tượng bằng tính *reachability* (còn có thể tới được từ các gốc tham chiếu); không có bảo đảm thu gom ngay khi kết thúc một khối lệnh.

**Quy tắc quan trọng:** Hết phạm vi gọi tên biến **không đồng nghĩa** với đối tượng từng được biến ấy trỏ tới đã bị hủy; và còn trong phạm vi cú pháp **không đồng nghĩa** giá trị của đối tượng bắt buộc phải tồn tại đến cuối scope theo một bố trí bộ nhớ cố định.

Ví dụ đoạn mã minh họa đặt bên trong một phương thức:

```java
{
    int count = 5;
    System.out.println(count); // Được phép: count đang trong scope
}
// System.out.println(count); // LỖI BIÊN DỊCH: không thấy tên count
```

Bên ngoài khối lệnh `{}`, tên `count` không còn thuộc scope; trình biên dịch từ chối dùng tên đó. Không cần quan sát việc JVM cấp phát/giải phóng bộ nhớ để kết luận lỗi trên.

## 2. Các loại biến và ý nghĩa của scope/lifetime

| Loại biến | Nơi khai báo và phạm vi sử dụng tên | Thời gian tồn tại của thực thể biến |
| --- | --- | --- |
| **Biến cục bộ (local)** | Trong khối lệnh, thân phương thức, vòng lặp, hoặc khối tương ứng theo quy tắc ngôn ngữ | Gắn với lần thực thi đoạn mã và các phạm vi thực thi tương ứng; mỗi lần gọi phương thức có các biến cục bộ riêng |
| **Tham số phương thức/constructor** | Trong thân phương thức/constructor được khai báo, với quy tắc scope tương ứng | Biến tham số riêng cho mỗi lần gọi |
| **Trường instance** (không `static`) | Thành viên của lớp, truy cập qua `this`/tham chiếu đối tượng theo quyền truy cập | Là một phần trạng thái của từng đối tượng; có từ khi đối tượng được tạo đến lúc đối tượng không còn tồn tại |
| **Trường `static`** | Thành viên của lớp, truy cập theo quy tắc thành viên và quyền truy cập | Có một bản cho mỗi lần định nghĩa lớp trong một runtime class loader; gắn với vòng đời lớp được nạp/khởi tạo, không gắn từng instance |

Bảng này mô tả mô hình ngôn ngữ ở mức lập trình, **không** khẳng định mọi biến local bắt buộc luôn nằm vật lý trên stack hay mọi đối tượng luôn nằm ở một vùng bộ nhớ cụ thể. JVM/JIT có thể tối ưu hóa bố trí và lưu trữ mà vẫn giữ đúng hành vi Java.

**Ví dụ phân biệt instance với `static`:**

```java
class Counter {
    static int totalCreated;
    int value;

    Counter(int value) {
        this.value = value;
        totalCreated++;
    }
}
```

Hai đối tượng `Counter` có hai trường `value` độc lập, còn `Counter.totalCreated` được chia sẻ trong cùng một lớp runtime. Scope của tên `value` trong lớp và thời gian tồn tại của trạng thái `value` trong từng đối tượng là hai vấn đề khác nhau.

### Khi một phương thức chạy nhiều lần

```java
static int square(int n) {
    int result = n * n;
    return result;
}
```

Mỗi lần gọi `square` tạo ngữ cảnh thực thi riêng cho tham số `n` và biến cục bộ `result`. Các lần gọi lồng nhau/đệ quy không dùng chung một biến local, dù trong mã nguồn chúng cùng có tên `result`. Sau `return`, nơi gọi nhận **giá trị trả về**, chứ không tiếp tục truy cập biến `result` theo tên.

## 3. Scope của tên biến trong khối và vòng lặp

Quy tắc cơ bản là tên local có thể được tham chiếu từ nơi khai báo đến hết khối thích hợp; biến khai báo trong phần khởi tạo `for` chỉ có phạm vi trong câu lệnh `for`:

~~~java
for (int i = 0; i < 2; i++) {
    int square = i * i;
    System.out.println(square); // 0, rồi 1
}
// i và square không còn trong scope ở đây.
~~~

Đây là quy tắc **mã nguồn**, không chỉ ra thời điểm GC hay cách JVM bố trí vật lý các biến. Trong vòng lặp, `i` tồn tại qua các lượt cập nhật chỉ số, còn biểu thức khởi tạo `square` được thực hiện lại mỗi khi đi vào thân vòng. Một lần gọi phương thức khác tạo ngữ cảnh local khác, dù chúng có cùng tên trong source.

Hai khối anh em có thể dùng cùng tên local vì phạm vi không chồng nhau; khối lồng không được khai báo lại tên local/parameter đang trong scope của khối ngoài. Muốn hiểu chính xác các lỗi khai báo trùng, xem bài về *biến cục bộ trùng tên*. Ở đây cần tập trung vào câu hỏi khác: **khi không còn gọi được tên, giá trị tham chiếu và đối tượng có tiếp tục tồn tại không?**

## 4. Biến tham chiếu hết scope nhưng đối tượng vẫn còn

Xét một phương thức tạo mảng rồi trả về:

```java
static int[] createValues() {
    int[] numbers = {3, 6, 9};
    return numbers;
}

int[] received = createValues();
System.out.println(received[1]); // 6
```

Ở cuối `createValues()`, tên local `numbers` không còn dùng được ở nơi gọi; lần thực thi phương thức cũng kết thúc. **Nhưng đối tượng mảng `int[]` vẫn có thể truy cập qua biến `received`**, vì phương thức trả về giá trị tham chiếu trỏ tới chính mảng ấy.

Tương tự, đối tượng có thể tiếp tục tồn tại khi tham chiếu tới nó được lưu ở field, phần tử mảng khác, hoặc cấu trúc dữ liệu còn sống. Thời gian tồn tại của **đối tượng** không bị ràng buộc bởi scope của **một biến local ban đầu**.

Ở chiều ngược lại, khi một biến tham chiếu vẫn ở trong scope, không nên suy ra đối tượng cũ vẫn cần thiết sau một phép gán lại:

```java
StringBuilder builder = new StringBuilder("old");
builder = new StringBuilder("new");
```

Biến `builder` vẫn đang dùng được, nhưng nó không còn trỏ tới đối tượng `StringBuilder("old")`. Nếu không có tham chiếu sống nào khác tới đối tượng cũ, đối tượng đó **có thể trở thành ứng viên thu gom rác**. Thời điểm JVM thật sự thu gom không được quy định và không nên dùng `System.gc()` để suy ra một thời gian sống chính xác.

## 5. Lambda và việc bắt giá trị local (*capture*)

Một lambda có thể sử dụng biến cục bộ của phạm vi bao ngoài khi biến đó là `final` hoặc **effectively final** (được gán tối đa một lần và không bị gán lại). Điều này không biến Java thành ngôn ngữ truyền tham số theo tham chiếu: lambda nắm giữ giá trị cần thiết để thực hiện hành vi sau đó.

```java
static Runnable makePrinter() {
    String message = "Xin chao";
    return () -> System.out.println(message);
}

Runnable printer = makePrinter();
printer.run(); // Xin chao
```

Lệnh `printer.run()` vẫn thực thi được **sau khi** `makePrinter()` đã trả về và tên `message` không còn tồn tại trong ngữ cảnh thực thi trước đó. Lambda giữ dữ liệu cần thiết để sử dụng `message`; với một giá trị tham chiếu, đối tượng được tham chiếu có thể vẫn tồn tại.

Không được gán lại biến local đã được lambda bắt:

```java
int count = 2;
Runnable show = () -> System.out.println(count);
// count++; // LỖI BIÊN DỊCH: count không còn effectively final
```

Nếu biến local tham chiếu tới **đối tượng mutable**, lambda vẫn có thể sửa trạng thái đối tượng ấy, miễn là không gán lại chính biến local đã bắt:

```java
int[] counter = {0};
Runnable increase = () -> counter[0]++;
increase.run();
// counter[0] == 1
```

Scope của tên `counter`, việc lambda giữ giá trị tham chiếu, và thời gian tồn tại của mảng là **ba yếu tố riêng biệt**. Không nên dùng mảng một phần tử chỉ để “lách” ràng buộc effectively final trong thiết kế chương trình; hãy chọn cấu trúc trạng thái có ý nghĩa rõ ràng khi thật sự cần.

## 6. Chương trình Java 17+ độc lập

Tạo tệp **`ScopeLifetimeDemo.java`**:

```java
import java.util.Arrays;

public class ScopeLifetimeDemo {
    private static int created;
    private int value;

    public ScopeLifetimeDemo(int value) {
        this.value = value;
        created++;
    }

    static int calculate(int input) {
        int result;
        {
            int temp = input * 2;
            result = temp + 1;
            System.out.println("Khoi mot: " + temp);
        }
        {
            int temp = input + 10; // Ten temp duoc su dung lai
            System.out.println("Khoi hai: " + temp);
        }
        return result;
    }

    static int[] makeArray() {
        int[] localArray = {3, 6, 9};
        return localArray; // Tham chieu thoat ra khoi phuong thuc
    }

    static Runnable makePrinter() {
        String message = "Hello";
        return () -> System.out.println("Lambda: " + message);
    }

    public static void main(String[] args) {
        int outer = 5;
        {
            int inside = outer * 2;
            System.out.println("Trong khoi: " + inside);
        }
        System.out.println("Ngoai khoi: " + outer);

        int answer = calculate(4);
        System.out.println("Ket qua: " + answer);

        ScopeLifetimeDemo object = new ScopeLifetimeDemo(12);
        System.out.println("Instance field: " + object.value);
        System.out.println("Static field: " + ScopeLifetimeDemo.created);

        int[] returned = makeArray();
        System.out.println("Mang sau return: " + Arrays.toString(returned));

        Runnable action = makePrinter();
        action.run();

        for (int i = 0; i < 2; i++) {
            System.out.println("Lap: " + i);
        }
    }
}
```

Trong thư mục chứa tệp, sử dụng JDK 17 trở lên trên Windows PowerShell/CMD hoặc Linux/macOS:

```bash
javac -encoding UTF-8 ScopeLifetimeDemo.java
java ScopeLifetimeDemo
```

Kết quả stdout **chính xác** (biên dịch thành công không in dòng nào):

```text
Trong khoi: 10
Ngoai khoi: 5
Khoi mot: 8
Khoi hai: 14
Ket qua: 9
Instance field: 12
Static field: 1
Mang sau return: [3, 6, 9]
Lambda: Hello
Lap: 0
Lap: 1
```

Giải thích kết quả:

1. `inside` chỉ được gọi tên bên trong khối, nhưng `outer` vẫn dùng được sau khối đó.
2. Hai biến `temp` ở hai khối anh em hợp lệ, dù cùng tên. `result` được khai báo bên ngoài hai khối, nên có thể nhận kết quả bên trong khối rồi được trả về.
3. `object.value` là trường của đối tượng `ScopeLifetimeDemo`, còn `created` là trường `static` của lớp.
4. Mảng tạo trong `makeArray()` vẫn được dùng sau khi phương thức kết thúc, vì giá trị tham chiếu được trả về.
5. Lambda trả về từ `makePrinter()` vẫn in `Hello`; điều này **không có nghĩa** local `message` vẫn đang truy cập được bằng tên từ `main`.
6. Biến đếm `i` của `for` có thể sử dụng trong vòng lặp, nhưng không thể gọi tên bên ngoài vòng lặp.

## 7. Thời gian tồn tại của field và các lưu ý thực tế

### Field instance

Khi tạo một đối tượng, trạng thái instance được khởi tạo theo các quy tắc Java. Mỗi đối tượng có các field instance riêng; field được giữ như một phần trạng thái của đối tượng khi đối tượng còn tồn tại. Một phương thức có thể kết thúc trong khi đối tượng vẫn được truy cập qua field của đối tượng khác, biến trả về, hay tham chiếu khác.

### Field `static`

Trường `static` thuộc về lớp tại runtime, không thuộc về từng đối tượng. Việc khởi tạo trường `static` xảy ra theo cơ chế khởi tạo lớp; các lần gọi phương thức hoặc tạo thêm instance không tạo một bản static mới cho mỗi instance. Không nên đơn giản hóa thành “trường static sống cho đến khi máy tính tắt”: vòng đời lớp và class loader có thể kết thúc khi điều kiện runtime cho phép.

### GC và `null`

- `reference = null` chỉ **thay giá trị của một biến tham chiếu**; nó không trực tiếp xóa đối tượng.
- Đối tượng có thể còn được tham chiếu từ nơi khác; ngay cả khi không còn truy cập được, thời điểm GC thu gom là không xác định.
- Biến local hết scope không phải một **hàm hủy** và không làm JVM buộc phải gọi cleanup.
- Đối với tài nguyên như file, socket, database connection, phải chủ động đóng đúng cách; ưu tiên `try-with-resources` cho đối tượng `AutoCloseable`, không đợi GC.

## 8. Các nhầm lẫn cần tránh

| Nhận định | Đánh giá | Vì sao? |
| --- | --- | --- |
| “Không gọi được tên biến sau dấu `}` nghĩa là đối tượng nó giữ đã bị hủy.” | Sai | Scope của tên và reachability của đối tượng độc lập. |
| “Biến cục bộ trong phương thức được chia sẻ giữa các lần gọi.” | Sai | Mỗi lần thực thi có biến cục bộ và tham số riêng, kể cả đệ quy. |
| “Mảng được trả về sẽ mất vì biến local ban đầu kết thúc.” | Sai | Giá trị tham chiếu trả về giữ khả năng truy cập mảng. |
| “`static` tạo một bản giá trị cho mỗi đối tượng.” | Sai | Field `static` gắn với lớp tại runtime. |
| “Dùng `System.gc()` bảo đảm đối tượng bị thu gom ngay.” | Sai | Không có bảo đảm thu gom tức thời. |
| “Lambda có thể giữ giá trị local để chạy sau khi phương thức tạo lambda kết thúc.” | Đúng | Quy tắc capture với biến final/effectively final cho phép hành vi này. |

**Ghi nhớ:** *Scope trả lời “ở đâu trong mã được viết tên biến?”; lifetime trả lời “một thực thể biến/đối tượng còn tồn tại trong lúc chạy đến khi nào?”*. Để hiểu đúng Java, hãy tiếp tục phân biệt **biến chứa giá trị tham chiếu** với **đối tượng mà giá trị ấy trỏ tới**.