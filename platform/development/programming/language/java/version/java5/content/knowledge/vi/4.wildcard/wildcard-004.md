# Tính bất biến của kiểu generic

## 1. Quan hệ của phần tử không tự truyền sang kiểu chứa nó

Trong Java, `Integer` là kiểu con của `Number`, nên một giá trị `Integer` có thể được dùng ở nơi yêu cầu `Number`. Nhưng với các kiểu generic có đối số cụ thể, quan hệ ấy không tự truyền qua lớp chứa:

```java
Integer value = 5;
Number number = value; // Hợp lệ.

java.util.List<Integer> integers = new java.util.ArrayList<>();
// java.util.List<Number> numbers = integers; // Lỗi biên dịch.
```

Quy tắc này được gọi là **bất biến theo tham số kiểu (invariance)**. `List<Integer>` không phải kiểu con của `List<Number>`, và `List<Number>` cũng không phải kiểu con của `List<Integer>` chỉ vì các đối số kiểu có quan hệ kế thừa.

Cần phân biệt hai nghĩa dễ nhầm của từ “bất biến”:

- **Bất biến theo tham số kiểu:** nói về quan hệ kiểu con và khả năng gán, như quan hệ giữa `List<Integer>` với `List<Number>`.
- **Đối tượng bất biến hoặc collection không cho sửa:** nói về việc dữ liệu có thể bị thay đổi khi chạy hay không.

Một `ArrayList<Integer>` có thể cho thêm, xóa phần tử nhưng vẫn tuân theo quy tắc invariance. Một danh sách tạo bằng `List.of` không cho sửa cũng không khiến `List<Integer>` tự trở thành `List<Number>`.

Bài này dùng kiến thức còn áp dụng trong Java hiện hành. Chương trình đầy đủ chạy bằng Java 17 trở lên.

## 2. Vì sao phép gán phải bị từ chối?

`List<Number>` không chỉ hứa đọc được một `Number`. Nó còn cho phép đưa các giá trị `Number` phù hợp vào danh sách, nếu đối tượng danh sách hỗ trợ cập nhật. Chẳng hạn, một `Double` hợp lệ ở vị trí đó.

Giả sử phép gán đang bị cấm được cho phép:

```java
// Kịch bản giả định, KHÔNG hợp lệ trong Java:
// List<Integer> integers = new ArrayList<>();
// List<Number> numbers = integers;
// numbers.add(2.5);
// Integer value = integers.get(0);
```

Hai biến sẽ cùng trỏ tới một danh sách. Thao tác qua `numbers` đưa một `Double` vào, trong khi thao tác qua `integers` hứa trả về `Integer`. Hợp đồng của một trong hai tham chiếu bị phá vỡ.

Java từ chối phép gán để ngăn tình huống đó trước khi chạy. Lý do không phải `Integer` không dùng được như `Number`; lý do là **toàn bộ hợp đồng đọc và ghi của danh sách** khác với quan hệ giữa một phần tử đơn lẻ và lớp cha của nó.

Chiều ngược lại cũng không an toàn. Một `List<Number>` có thể chứa `Double`, nên không thể dùng nó như `List<Integer>`. Việc các phần tử hiện tại tình cờ đều là số nguyên không thay đổi kiểu đã khai báo và các phép ghi mà hợp đồng cho phép trong tương lai.

## 3. Invariance không xóa quan hệ kế thừa của chính lớp generic

Các quan hệ này vẫn hợp lệ:

```java
java.util.ArrayList<Integer> concrete = new java.util.ArrayList<>();
java.util.List<Integer> list = concrete;
java.util.Collection<Integer> collection = list;
Iterable<Integer> iterable = collection;
```

`ArrayList<Integer>` thực hiện `List<Integer>`; `List<Integer>` mở rộng `Collection<Integer>`. Ở đây, đối số kiểu `Integer` được giữ theo quan hệ kế thừa đã khai báo.

Điều không được suy ra là đổi đối số kiểu từ `Integer` thành `Number` trong một phép gán đơn thuần.

```text
ArrayList<Integer> → List<Integer> → Collection<Integer>
        hợp lệ theo quan hệ kế thừa đã khai báo

List<Integer>     → List<Number>
        không tự tạo quan hệ kiểu con từ Integer → Number
```

Một kiểu có thể tự khai báo cách truyền hoặc cố định đối số kiểu khi kế thừa. Invariance không có nghĩa “mọi kiểu generic đều hoàn toàn không có quan hệ kiểu con”; nó có nghĩa không được tự nâng quan hệ của các đối số cụ thể thành quan hệ tương ứng giữa các cách tham số hóa.

## 4. Quy tắc cũng áp dụng với lớp generic tự viết

Đoạn khai báo sau là một ví dụ độc lập có thể đặt trong một tệp Java:

```java
class Holder<T> {
    private T value;

    Holder(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    void set(T value) {
        this.value = value;
    }
}
```

Trong một phương thức sử dụng:

```java
Holder<Integer> integerHolder = new Holder<>(1);
// Holder<Number> numberHolder = integerHolder; // Lỗi biên dịch.
```

Nếu phép gán ấy được cho phép, `numberHolder.set(1.5)` có thể phá vỡ bảo đảm của `integerHolder.get()`. Cơ chế giống tình huống của `List`.

Ngay cả nếu một kiểu chỉ cung cấp `get` và không có `set`, Java cũng không tự suy ra cách khai báo kiểu của nó là đồng biến từ việc phân tích các phương thức. Muốn diễn đạt một góc nhìn nhận được các đối số kiểu khác nhau, dùng wildcard ở nơi sử dụng hoặc thiết kế một quan hệ kiểu rõ ràng.

Với `Map`, quy tắc cần xét cho từng đối số: `Map<String, Integer>` không tự gán được sang `Map<String, Number>`; cũng không tự gán được sang `Map<Object, Integer>` chỉ vì `String` là kiểu con của `Object`.

## 5. Wildcard tạo sự linh hoạt ở nơi sử dụng

Wildcard không làm `List<Integer>` trở thành `List<Number>`. Nó tạo một hợp đồng khác, cố ý giới hạn một số thao tác để phép dùng chung trở nên an toàn.

### Đọc số từ nhiều kiểu danh sách bằng extends

```java
java.util.List<Integer> integers = java.util.List.of(1, 2, 3);
java.util.List<? extends Number> source = integers;
Number first = source.get(0);
// source.add(4); // Lỗi biên dịch.
```

`List<? extends Number>` có nghĩa kiểu phần tử cụ thể chưa biết nhưng là `Number` hoặc một kiểu con phù hợp của `Number`. Vì vậy, đọc phần tử dưới kiểu `Number` là an toàn.

Không thể thêm tùy ý một `Integer` hay `Double`, vì danh sách thật có thể là `List<Double>` hoặc `List<Integer>` tương ứng. Về kiểm tra kiểu, `null` vẫn là một trường hợp được phép ở vị trí tham chiếu; khả năng thêm khi chạy phụ thuộc đối tượng danh sách.

Một thuật toán chỉ đọc các số có thể dùng chữ ký:

```java
static double total(java.util.List<? extends Number> values) {
    double result = 0;
    for (Number value : values) {
        result += value.doubleValue();
    }
    return result;
}
```

Phương thức minh họa này cần được đặt trong một lớp. Nó nhận được `List<Integer>` hoặc `List<Double>`. Ví dụ giả định danh sách và các phần tử khác `null`; chuyển qua `doubleValue()` có thể mất độ chính xác với một số loại số, nên không coi đây là phép tính chính xác cho mọi miền dữ liệu.

### Ghi số nguyên vào các kiểu đích phù hợp bằng super

```java
java.util.List<Number> numbers = new java.util.ArrayList<>();
java.util.List<? super Integer> destination = numbers;
destination.add(7);
Object first = destination.get(0);
```

`List<? super Integer>` nhận được các đối tượng có hợp đồng như `List<Integer>`, `List<Number>` hoặc `List<Object>`. Chúng đều có thể tiếp nhận một `Integer`, nếu cho phép thay đổi.

Nhưng khi đọc, chỉ có thể dựa vào kiểu `Object`. Danh sách thật có thể là `List<Number>` đã chứa `Double`, hoặc `List<Object>` đã chứa chuỗi. Việc có quyền thêm một số nguyên không có nghĩa mọi phần tử cũ đều là số nguyên.

Quy tắc nhớ thường dùng là **PECS — Producer Extends, Consumer Super**: khi nguồn cung cấp giá trị cần đọc như một kiểu, cân nhắc `extends`; khi đích nhận giá trị thuộc một kiểu, cân nhắc `super`. Đây là hướng dẫn thiết kế theo thao tác, không phải bảo đảm rằng một tham chiếu wildcard trở thành chỉ đọc hoặc chỉ ghi tuyệt đối.

### Quan hệ cần phân biệt

| Nguồn | Kiểu đích | Hợp lệ? |
| --- | --- | --- |
| `List<Integer>` | `List<Number>` | Không |
| `List<Number>` | `List<Integer>` | Không |
| `List<Integer>` | `List<? extends Number>` | Có |
| `List<Number>` | `List<? super Integer>` | Có |
| `List<Object>` | `List<? super Integer>` | Có |
| `List<Integer>` | `List<?>` | Có |

Các phép gán wildcard ở bảng không tạo bản sao dữ liệu. Thay đổi hợp lệ qua một tham chiếu có thể xuất hiện qua tham chiếu khác cùng trỏ đến nguồn.

## 6. Chương trình chạy đầy đủ

Lưu thành **`GenericInvarianceDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class GenericInvarianceDemo {
    static double total(List<? extends Number> values) {
        double result = 0;
        for (Number value : values) {
            result += value.doubleValue();
        }
        return result;
    }

    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>(List.of(1, 2, 3));
        List<? extends Number> source = integers;
        Number first = source.get(0);
        System.out.println("first=" + first);
        System.out.println("total=" + total(integers));

        List<Number> numbers = new ArrayList<>();
        numbers.add(2.5);
        List<? super Integer> destination = numbers;
        destination.add(7);
        Object existing = destination.get(0);
        System.out.println("destination=" + numbers);
        System.out.println("existing=" + existing);

        List<Number> copied = new ArrayList<>(integers);
        copied.add(9.5);
        System.out.println("copied=" + copied);
        System.out.println("original=" + integers);

        Number[] arrayView = new Integer[] {1, 2};
        try {
            arrayView[0] = 2.5;
        } catch (ArrayStoreException ex) {
            System.out.println("array store rejected");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all GenericInvarianceDemo.java
java GenericInvarianceDemo
```

Stdout chính xác:

```text
first=1
total=6.0
destination=[2.5, 7]
existing=2.5
copied=[1, 2, 3, 9.5]
original=[1, 2, 3]
array store rejected
```

Nguồn số nguyên được đọc dưới hợp đồng `? extends Number`, còn danh sách đích nhận số nguyên dưới hợp đồng `? super Integer`. Giá trị cũ `2.5` chứng minh vì sao kết quả đọc từ đích không được giả định là `Integer`.

Bản sao `copied` là một đối tượng danh sách riêng. Thêm `Double` vào nó không phá vỡ danh sách nguồn số nguyên. Khối mảng ở cuối minh họa sự khác nhau giữa quy tắc của mảng và generic, được giải thích tiếp dưới đây.

## 7. Sao chép không phải phép gán cùng một đối tượng

Câu lệnh này hợp lệ:

```java
java.util.List<Number> copied = new java.util.ArrayList<>(integers);
```

Constructor tạo danh sách mới, rồi đưa các tham chiếu phần tử từ nguồn vào. Mỗi phần tử `Integer` có thể được dùng ở vị trí `Number`, nên việc sao chép dữ liệu an toàn.

Điều đó không mâu thuẫn với việc phép gán `List<Number> numbers = integers` bị cấm. Phép gán dùng chung **một đối tượng danh sách**, còn constructor tạo **danh sách khác** với hợp đồng phần tử mới phù hợp.

Đây là sao chép nông đối với các đối tượng phần tử. Nếu phần tử có trạng thái có thể thay đổi, hai danh sách có thể cùng giữ tham chiếu đến một đối tượng. Trong ví dụ dùng `Integer` bất biến, không có thao tác sửa nội dung một đối tượng số tại chỗ.

## 8. Vì sao mảng lại cho phép một phép gán tương tự?

Mảng kiểu tham chiếu của Java có tính đồng biến theo kiểu phần tử: `Integer[]` có thể dùng như `Number[]`. Nhưng mảng giữ thông tin kiểu phần tử thực tế để kiểm tra việc lưu giá trị khi chạy.

```java
Number[] values = new Integer[] {1, 2};
// values[0] = 2.5; // Biên dịch được, nhưng chạy ném ArrayStoreException.
```

Biến `values` có kiểu `Number[]`, nhưng đối tượng mảng thật chỉ nhận `Integer`. JVM từ chối lưu một `Double` vào mảng ấy. Trong chương trình đầy đủ, ngoại lệ này được bắt có chủ đích.

Với generic, quan hệ `List<Integer>` → `List<Number>` bị chặn ngay ở bước kiểm tra kiểu. Không dùng trực giác từ mảng để suy ra rằng các kiểu generic cũng có cùng quy tắc gán.

Cũng không coi `ArrayStoreException` như một cơ chế tự bảo vệ tương tự cho mọi phép thêm vào một `ArrayList`. Tính an toàn của generic dựa vào hợp đồng kiểu và việc không phá hợp đồng bằng các phép chuyển đổi không được kiểm tra.

## 9. Những nhầm lẫn thường gặp

### “Danh sách không cho sửa thì phải gán được”

`List<Integer> fixed = List.of(1, 2)` vẫn không tự gán được cho `List<Number>`. Kiểu tĩnh `List<Integer>` và quy tắc generic không thay đổi tùy theo việc đối tượng hiện tại hỗ trợ cập nhật hay không. Nếu cần một góc nhìn đọc số tổng quát, khai báo `List<? extends Number>`.

### “extends nghĩa là đối tượng không thể bị sửa”

`List<? extends Number>` hạn chế việc cung cấp phần tử mới vì không biết kiểu cụ thể. Nhưng nó vẫn có thể cho `clear()` hoặc xóa phần tử khi đối tượng hỗ trợ. Wildcard không tạo bất biến dữ liệu và không ngăn một tham chiếu khác thay đổi nguồn.

### “Có cùng dữ liệu hoặc cùng lớp triển khai thì hai kiểu tương đương”

Một `ArrayList<Integer>` và một `ArrayList<Number>` có thể tạm chứa cùng các số nguyên. Hợp đồng vẫn khác nhau: bản `Number` cho phép thêm `Double`. Không suy ra khả năng gán chỉ bằng nội dung hiện tại hay tên lớp triển khai chung.

### “Một tầng wildcard sẽ tự giải quyết mọi tầng generic”

`List<List<Integer>>` không tự trở thành `List<List<Number>>`. Với cấu trúc lồng nhau, phải xét quan hệ ở từng tầng và đặt wildcard theo đúng thao tác cần làm. Không chỉ thay một kiểu sâu bên trong rồi giả định lớp chứa bên ngoài sẽ tự tương thích.

### “Ép kiểu là cách mở rộng quan hệ kế thừa”

Không ép một danh sách số nguyên thành danh sách số tổng quát để thêm số thực. Phép ép không tạo một danh sách mới và không chuyển đổi hợp đồng của các tham chiếu đang cùng giữ nguồn. Hãy dùng wildcard với quyền thao tác đúng hoặc tạo một bản sao có kiểu phù hợp.

## 10. Áp dụng khi thiết kế tham số phương thức

Trước khi chọn chữ ký, xác định thuật toán cần làm gì:

- Nếu vừa nhận vừa trả/ghi phần tử theo đúng một kiểu cụ thể, dùng kiểu cụ thể hoặc tham số kiểu có tên để giữ quan hệ đó.
- Nếu chỉ cần đọc các phần tử dưới kiểu `Number`, cân nhắc `List<? extends Number>`.
- Nếu cần đưa các giá trị `Integer` vào một nơi chứa phù hợp, cân nhắc `List<? super Integer>`.
- Nếu chỉ quan sát kích thước hoặc duyệt như `Object`, cân nhắc `List<?>`.

Không mở rộng API thành `List<Number>` chỉ vì muốn nhận thêm `List<Integer>`; đó là một hợp đồng khác. Thiết kế theo quyền thao tác giúp API vừa linh hoạt vừa giữ bảo đảm kiểm tra kiểu.

## 11. Tự thực hành

1. Thử gán `List<Double>` cho `List<Number>` và giải thích lỗi bằng một phép thêm `Integer` giả định qua tham chiếu đích.
2. Sửa một phương thức chỉ tính tổng đang nhận `List<Number>` để nó nhận được cả `List<Integer>` mà không ép kiểu. Kiểm tra giới hạn dữ liệu và độ chính xác của phép tính.
3. Tạo `List<Object>`, nhìn nó qua `List<? super Integer>` rồi thêm một số nguyên. Giải thích vì sao đọc kết quả chỉ được bảo đảm dưới kiểu `Object`.
4. Tạo bản sao `List<Number>` từ nguồn `List<Integer>` rồi thêm `Double` vào bản sao. Xác nhận nguồn giữ nguyên cấu trúc.
5. So sánh lỗi gán generic ở lúc biên dịch với `ArrayStoreException` trong chương trình đầy đủ. Chỉ ra bước nào phát hiện vấn đề trong từng cơ chế.

Tính bất biến theo tham số kiểu bảo vệ các hợp đồng khác nhau đang cùng muốn nhìn vào một đối tượng chứa dữ liệu. Wildcard cho phép chọn một hợp đồng sử dụng linh hoạt hơn; sao chép cho phép tạo một đối tượng chứa mới. Hai cách đó giải quyết những nhu cầu khác nhau và đều giữ rõ ý định của mã.

## Tài liệu đối chiếu

- [JLS §4.10.2 — Subtyping among Class and Interface Types](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.10.2): quan hệ kiểu con của các kiểu generic.
- [JLS §4.5.1 — Type Arguments of Parameterized Types](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.5.1): wildcard và giới hạn tại nơi sử dụng kiểu.
- [JLS §10.5 — Array Store Exception](https://docs.oracle.com/javase/specs/jls/se25/html/jls-10.html#jls-10.5): kiểm tra kiểu phần tử khi lưu vào mảng.
