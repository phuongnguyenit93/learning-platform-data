# Ý nghĩa của `? super T` trong Java Generics

## 1. `? super T` biểu diễn điều gì?

Trong Java Generics, **`? super T` là lower-bounded wildcard**, tức wildcard có **cận dưới**. Cú pháp này biểu diễn một đối số kiểu **chưa biết chính xác**, nhưng phải là **`T` hoặc một kiểu cha của `T`**. Kiểu cha ở đây được hiểu theo quan hệ kiểu con của Java, có thể là lớp cha hoặc interface mà `T` triển khai.

Ví dụ:

```java
List<? super Integer> destination;
```

Kiểu phần tử thực sự của danh sách có thể là `Integer`, `Number`, `Object`, hoặc một kiểu cha khác hợp lệ của `Integer`. Điều Java đảm bảo là: **một giá trị kiểu `Integer` có thể được đưa vào danh sách này một cách an toàn về kiểu**.

Hai thành phần của cú pháp có vai trò khác nhau:

- `?`: một đối số kiểu ẩn; mã nguồn tại vị trí này **không biết chính xác** danh sách khai báo `E` là kiểu nào.
- `super T`: ràng buộc rằng `T` là kiểu con hoặc chính là kiểu ẩn ấy; do đó một giá trị `T` có thể gán cho kiểu phần tử thực tế.

Có thể đọc `List<? super Integer>` như sau: “Một `List` có kiểu phần tử nào đó đủ rộng để **nhận giá trị `Integer`**”.

```java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();

List<? super Integer> a = integers; // Hợp lệ
List<? super Integer> b = numbers;  // Hợp lệ
List<? super Integer> c = objects;  // Hợp lệ
```

Các phép gán chỉ tạo **tham chiếu mới tới danh sách đã có**, không sao chép hoặc chuyển đổi phần tử. Nếu `a` trỏ tới `integers`, thay đổi phần tử thông qua `a` cũng được nhìn thấy qua `integers`.

Điều **không** được suy ra từ `? super Integer` là “đối số kiểu chắc chắn là `Number`” hoặc “danh sách chắc chắn là `List<Object>`”. Trong từng trường hợp, kiểu thực có thể khác nhau; việc compiler không biết nó dẫn tới những giới hạn cụ thể khi đọc.

## 2. Các danh sách nào tương thích với `? super T`?

Xem quan hệ kiểu:

```text
Object
  └── Number
       ├── Integer
       ├── Double
       └── Long
```

Với cận dưới `Integer`, các tham số kiểu `Integer`, `Number` và `Object` đều chấp nhận `Integer`. Ngược lại, `Double` là kiểu “ngang hàng” với `Integer`, không phải kiểu cha của `Integer`.

```java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();
List<Double> doubles = new ArrayList<>();

List<? super Integer> sink;

sink = integers; // Hợp lệ
sink = numbers;  // Hợp lệ
sink = objects;  // Hợp lệ
// sink = doubles; // Lỗi biên dịch
```

| Danh sách truyền vào | `List<? super Integer>` nhận được? | Vì sao? |
|---|---|---|
| `List<Integer>` | Có | `Integer` chính là cận dưới |
| `List<Number>` | Có | `Number` là kiểu cha của `Integer` |
| `List<Object>` | Có | `Object` là kiểu cha của `Integer` |
| `List<Double>` | Không | `Double` không phải kiểu cha của `Integer` |
| `List<String>` | Không | `String` không phải kiểu cha của `Integer` |
| `List<? extends Number>` | Không đảm bảo | Kiểu ẩn có thể là `Double`, không nhận được `Integer` |
| `List<?>` | Không đảm bảo | Chưa biết kiểu ẩn có nhận được `Integer` hay không |

Cột cuối của hai dòng wildcard nói về việc **không thể dựa vào kiểu tĩnh đó để gán trực tiếp** vào biến `List<? super Integer>`. Một đối tượng đứng phía sau biến có thể tình cờ có kiểu phù hợp, nhưng compiler không được phép dựa trên phỏng đoán ấy.

Đối với một `T` tổng quát, quy tắc giống hệt: nếu `T` là `Dog` thì các tham số kiểu `Dog`, `Animal`, `Object` có thể là những đích nhận `Dog`, giả sử `Dog extends Animal`. Chữ `super` trong wildcard biểu thị **hướng đi về phía kiểu cha**.

## 3. Vì sao có thể thêm `T` và các kiểu con của `T`?

Một `List<? super Integer>` có thể là `List<Integer>`, `List<Number>` hoặc `List<Object>`. **Cả ba đều chứa được `Integer`**, do đó compiler cho phép:

```java
List<Number> numbers = new ArrayList<>();
List<? super Integer> destination = numbers;

destination.add(10);
destination.add(Integer.valueOf(20));
destination.set(0, 15);

System.out.println(numbers); // [15, 20]
```

Các thao tác `add` và `set` trên đây an toàn về **kiểu phần tử**. Nếu một kiểu `T` có lớp con `S`, giá trị `S` cũng có thể được thêm vào `List<? super T>` nhờ quan hệ gán `S` → `T` → kiểu cha chưa biết. Ví dụ `? super Number` nhận được các giá trị `Integer` và `Double`, bởi cả hai đều là kiểu con của `Number`.

```java
List<Object> objects = new ArrayList<>();
List<? super Number> sink = objects;

sink.add(Integer.valueOf(7));
sink.add(Double.valueOf(2.5));
sink.add((Number) Long.valueOf(9L));

System.out.println(objects); // [7, 2.5, 9]
```

Tuy vậy:

```java
List<? super Integer> sink = new ArrayList<Number>();

// sink.add(2.5);        // Không biên dịch: Double không phải Integer
// sink.add(new Object()); // Không biên dịch: Object không được đảm bảo phù hợp
sink.add(42);             // Hợp lệ
sink.add(null);           // Hợp lệ về kiểm tra kiểu
```

Vì danh sách thực tế có thể là `List<Integer>`, thêm `Double` hoặc một `Object` tùy ý sẽ không an toàn. Một biến `List<? super Integer>` **không có quyền thêm mọi thứ chỉ vì trong một trường hợp cụ thể nó trỏ tới `List<Object>`**. Compiler đánh giá dựa trên hợp đồng kiểu tĩnh.

`null` là ngoại lệ đặc biệt về type checking, vì nó có thể gán cho mọi kiểu tham chiếu. Việc thêm null có thành công khi chạy hay không còn phụ thuộc implementation (khả năng sửa danh sách và chính sách cho phép null).

## 4. Tại sao đọc chỉ đảm bảo `Object`?

Với `List<? super Integer>`, ta **không biết** `E` thực sự là `Integer`, `Number` hay `Object`. Giả sử danh sách là `List<Object>`: nó có thể đã chứa cả chuỗi lẫn số trước khi được đưa vào phương thức. Ràng buộc cận dưới không đảm bảo các giá trị sẵn có đều là `Integer`.

```java
List<Object> mixed = new ArrayList<>();
mixed.add("existing text");
mixed.add(100);

List<? super Integer> sink = mixed;
sink.add(42);

Object first = sink.get(0);  // Hợp lệ
Object third = sink.get(2);  // Hợp lệ

// Integer number = sink.get(2); // Lỗi: get(2) chỉ đảm bảo Object
// Number value = sink.get(2);   // Cũng lỗi: có thể là Object khác Number
```

Dù phần tử ở vị trí 2 trên thực tế là `Integer`, compiler không dựa vào vị trí hay dữ liệu hiện có để thay đổi kiểu trả về của `get`.

Ví dụ hoạt động ở runtime:

```java
Object value = sink.get(2);
if (value instanceof Integer number) {
    System.out.println(number + 1); // 43
}
```

`instanceof` kiểm tra **riêng giá trị được lấy ra**. Nó không biến toàn bộ biến `sink` thành `List<Integer>` và không cam kết rằng các phần tử khác đều là `Integer`.

Sự bất đối xứng đọc/ghi là điểm cốt lõi:

- **Ghi:** có thể cung cấp một `Integer` vì mọi kiểu `E` phù hợp với `? super Integer` đều nhận được `Integer`.
- **Đọc:** chỉ có thể gán an toàn cho `Object` vì không biết giá trị gốc trong `List<E>` có phải `Integer` hay không.

Không được hiểu `? super T` thành “mọi phần tử hiện có là kiểu cha của `T`”. Wildcard ràng buộc **đối số kiểu của cấu trúc**, không ràng buộc từng giá trị runtime theo hướng “lớn hơn” nào đó.

## 5. Ví dụ Java 17 hoàn chỉnh: một API nhận nhiều loại danh sách đích

Tạo tệp `SuperWildcardDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class SuperWildcardDemo {
    static void addDefaults(List<? super Integer> destination) {
        destination.add(10);
        destination.add(20);
    }

    static <T> void appendAll(
            List<? extends T> source,
            List<? super T> destination) {
        for (T element : source) {
            destination.add(element);
        }
    }

    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>();
        List<Number> numbers = new ArrayList<>();
        List<Object> objects = new ArrayList<>();

        addDefaults(integers);
        addDefaults(numbers);
        addDefaults(objects);

        System.out.println("Integers: " + integers);
        System.out.println("Numbers: " + numbers);
        System.out.println("Objects: " + objects);

        List<? super Integer> receiver = numbers;
        receiver.set(0, 99);
        Object first = receiver.get(0);
        System.out.println("First as Object: " + first);

        List<Integer> more = List.of(3, 4);
        appendAll(more, numbers);
        System.out.println("After appendAll: " + numbers);

        List<? super Number> numberReceiver = objects;
        numberReceiver.add(1.5);
        System.out.println("Objects with double: " + objects);
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```bash
javac SuperWildcardDemo.java
java SuperWildcardDemo
```

**Stdout chính xác:**

```text
Integers: [10, 20]
Numbers: [10, 20]
Objects: [10, 20]
First as Object: 99
After appendAll: [99, 20, 3, 4]
Objects with double: [10, 20, 1.5]
```

Vì sao ví dụ biên dịch và chạy được?

1. `addDefaults` nhận cả `List<Integer>`, `List<Number>` lẫn `List<Object>`, vì cả ba danh sách có thể nhận `Integer`.
2. `receiver.set(0, 99)` hợp lệ: `set` ghi một `Integer` vào một danh sách có kiểu ẩn là `Integer` hoặc kiểu cha của nó. `receiver.get(0)` chỉ có kiểu tĩnh an toàn là `Object`.
3. `appendAll` dùng một tham số kiểu `T` kết nối nguồn và đích. Ở lời gọi `appendAll(more, numbers)`, `T` có thể được suy luận sao cho nguồn `List<Integer>` và đích `List<Number>` đều phù hợp.
4. `numberReceiver` có cận dưới `Number`, vì vậy thêm `Double` an toàn về kiểu ngay cả khi biến đang tham chiếu `List<Object>`.

Các danh sách đều được tạo bằng `ArrayList` có thể sửa đổi, nên `add` và `set` thành công. Lệnh in danh sách dựa vào `toString()` của `ArrayList` và các phần tử số nguyên/`Double`, nên stdout đúng như trên.

## 6. PECS: “Consumer Super”

Quy tắc **PECS** là “**Producer Extends, Consumer Super**”. Đây là mẹo ghi nhớ khi thiết kế API với wildcard:

- Một **producer** tạo/cung cấp giá trị cho thuật toán, nên dùng `? extends T` để cho phép **đọc** giá trị dưới kiểu `T`.
- Một **consumer** nhận giá trị từ thuật toán, nên dùng `? super T` để cho phép **ghi** giá trị kiểu `T` vào đích.

Ví dụ khái quát:

```java
static <T> void appendAll(
        List<? extends T> source,
        List<? super T> destination) {
    for (T element : source) {
        destination.add(element);
    }
}
```

Trong vòng lặp, `source` sản xuất ra giá trị gán được cho `T`; `destination` nhận những giá trị `T` đó. Phương thức cho phép các lời gọi:

```java
List<Integer> ints = List.of(1, 2);
List<Number> nums = new ArrayList<>();
List<Object> objs = new ArrayList<>();

appendAll(ints, nums); // Hợp lệ
appendAll(ints, objs); // Hợp lệ
appendAll(nums, objs); // Hợp lệ
```

Không có phép ép kiểu không kiểm tra và cũng không cần dùng raw `List`. Nếu thay tham số đích bằng `List<T>`, API bị bó hẹp một cách không cần thiết đối với nhiều lời gọi trong đó kiểu phần tử của đích là kiểu cha của `T`.

**PECS nói về vai trò của tham số trong thuật toán**, không có nghĩa `? super T` tuyệt đối “chỉ ghi”: vẫn đọc được dưới kiểu `Object`, đếm phần tử, xóa phần tử khi implementation hỗ trợ. Đồng thời `? extends T` không có nghĩa cấu trúc immutable; nó chỉ hạn chế việc tự ý thêm giá trị có kiểu cụ thể vào một kiểu ẩn.

## 7. Khi nào nên dùng `List<? super T>` thay cho `List<T>`?

So sánh hai chữ ký:

```java
static void addCountStrict(List<Integer> values) {
    values.add(1);
}

static void addCountFlexible(List<? super Integer> values) {
    values.add(1);
}
```

`addCountStrict` chỉ nhận `List<Integer>`. `addCountFlexible` còn nhận `List<Number>` và `List<Object>`. Nếu bên trong phương thức chỉ cần **đưa một `Integer` vào danh sách**, chữ ký thứ hai mô tả đúng quyền cần có và linh hoạt hơn.

Nhưng nếu thuật toán cần **đọc kết quả từ chính danh sách với kiểu `Integer`**, `List<? super Integer>` không bảo đảm điều đó:

```java
static Integer getFirstStrict(List<Integer> values) {
    return values.get(0);
}

static Object getFirstFlexible(List<? super Integer> values) {
    return values.get(0);
}
```

Đoạn minh họa trên giả định danh sách không rỗng; nếu rỗng, `get(0)` ném `IndexOutOfBoundsException` bất kể tham số generic là gì.

Điều cần hỏi khi thiết kế chữ ký là **“Phương thức có cần biết chính xác kiểu các phần tử đang đọc, hay chỉ cần đưa giá trị `T` vào danh sách?”**. Khi tác vụ chính là ghi `T`, `super` thường là lựa chọn phù hợp.

## 8. Dùng `? super T` với interface hoặc lớp con

`super` không đòi hỏi cận dưới là lớp có quan hệ `extends` trực tiếp. Nó cũng hỗ trợ quan hệ kiểu liên quan tới interface.

Giả sử một lớp tự định nghĩa:

```java
interface Event {
    String label();
}

record LoginEvent(String user) implements Event {
    public String label() {
        return "Login " + user;
    }
}
```

Đây là **đoạn khai báo minh họa**, chưa phải chương trình độc lập. Một `List<? super LoginEvent>` có thể tham chiếu `List<LoginEvent>`, `List<Event>` hoặc `List<Object>`; vào đó có thể thêm đối tượng `LoginEvent`:

```java
List<Event> log = new ArrayList<>();
List<? super LoginEvent> sink = log;

sink.add(new LoginEvent("Lan")); // Hợp lệ
Object entry = sink.get(0);      // Đọc an toàn dưới Object
```

Mặc dù biến `sink` trỏ tới `List<Event>` trong ví dụ, compiler vẫn chỉ cho phép `get` trả về thông tin an toàn chung là `Object` ở biến có kiểu wildcard cận dưới.

Khi cận dưới là một kiểu có lớp con, ta cũng có thể thêm các đối tượng thuộc kiểu con đó. Ví dụ `List<? super Number>` cho phép thêm `Integer` và `Double` vì chúng đều là `Number`.

## 9. Wildcard cận dưới có thay đổi khả năng sửa đổi danh sách không?

Không. Generics kiểm soát **kiểu giá trị**, còn danh sách cụ thể kiểm soát **khả năng mutation** và các hạn chế runtime khác.

```java
List<Number> mutable = new ArrayList<>();
List<? super Integer> a = mutable;
a.add(1);       // Được compiler chấp nhận và ArrayList cho phép
a.add(null);    // Được compiler chấp nhận; ArrayList cho phép null
```

Trái lại:

```java
List<Integer> immutable = List.of(1, 2);
List<? super Integer> b = immutable;

// b.add(3); // Hợp lệ về kiểu nhưng khi chạy sẽ ném UnsupportedOperationException
```

Ở đây `List.of(...)` trả về danh sách không sửa đổi được. Nếu bỏ comment `b.add(3)`, chương trình biên dịch nhưng ném `UnsupportedOperationException` tại runtime.

`List<? super Integer>` cũng cho phép gọi các phương thức không phụ thuộc vào việc thêm một phần tử cụ thể như `clear()`, `remove(Object)`, `remove(int)`, `size()`, `contains(Object)`. `remove(0)` chọn overload nhận **chỉ số `int`**, không phải overload xóa một đối tượng `Integer.valueOf(0)`. Các thao tác xóa và sửa đổi vẫn chịu quy tắc runtime của implementation.

Vì thế, đừng dùng `? super T` như cơ chế bảo vệ dữ liệu khỏi thay đổi; nếu cần hợp đồng không sửa đổi, hãy cấp một cấu trúc không sửa đổi được hoặc bản sao phù hợp.

## 10. Quan hệ giữa `? super T`, `? extends T`, `?` và kiểu cụ thể

Bảng sau dùng `T = Number`:

| Kiểu khai báo | Các tham số kiểu danh sách được chấp nhận | Kiểu đọc an toàn từ `get` | Thêm một `Number` tùy ý? |
|---|---|---|---|
| `List<Number>` | Chính xác `Number` | `Number` | Có |
| `List<? super Number>` | `Number` hoặc các kiểu cha như `Object` | `Object` | Có |
| `List<? extends Number>` | `Number` hoặc các kiểu con như `Integer`, `Double` | `Number` | Không |
| `List<?>` | Bất kỳ kiểu phần tử nào | `Object` | Không |
| Raw `List` | Bỏ thông tin đối số kiểu | `Object` | Có thể, nhưng không an toàn; có cảnh báo unchecked |

Ở hàng `List<?>` và `List<? extends Number>`, `add(null)` vẫn là ngoại lệ hợp kiểu. Ở các hàng có thể thêm giá trị, ta vẫn phải xem implementation có cho phép sửa danh sách hay không.

Các nhận xét cần phân biệt:

- `List<Number>` **không** phải là kiểu cha của `List<Integer>` dù `Number` là kiểu cha của `Integer`; Generic của Java là bất biến (*invariant*).
- `List<? super Integer>` **nhận được** `List<Number>`; đó là tính linh hoạt của wildcard theo cận dưới, không phải là phép kế thừa giữa `List<Integer>` và `List<Number>`.
- `? super Number` khác với `? extends Number`: thứ nhất thể hiện khả năng **nhận giá trị `Number`**, thứ hai thể hiện khả năng **cung cấp giá trị đọc được như `Number`**.

## 11. Ví dụ ngoài `List`: `Comparator<? super T>`

Nguyên lý “đưa giá trị `T` cho một consumer có kiểu cha” còn xuất hiện trong các API thư viện Java.

`List<E>.sort` nhận `Comparator<? super E>`. Một comparator biết so sánh `Number` có thể dùng để sắp xếp danh sách `Integer`, bởi comparator ấy **nhận được** các giá trị `Integer` dưới dạng `Number`:

```java
List<Integer> values = new ArrayList<>(List.of(30, 2, 11));
Comparator<Number> byNumericValue =
        Comparator.comparingDouble(Number::doubleValue);

values.sort(byNumericValue);
System.out.println(values); // [2, 11, 30]
```

Khi đưa đoạn này vào lớp Java, cần import `java.util.ArrayList`, `java.util.List` và `java.util.Comparator`. Đây là đoạn minh họa, không phải một `main` độc lập.

Nếu `sort` đòi hỏi `Comparator<Integer>` chính xác, một comparator tổng quát nhận `Number` sẽ không được sử dụng trực tiếp. Cận dưới `? super E` cho phép API dùng một consumer nhận kiểu cha, đúng theo hướng PECS.

## 12. Lưu ý với `Collections.copy` và việc “ghi vào đích”

Một API thư viện khác biểu diễn rất rõ vai trò nguồn/đích:

```java
static <T> void copy(
        List<? super T> dest,
        List<? extends T> src)
```

Đây là **chữ ký rút gọn** của `java.util.Collections.copy`, không phải một phương thức tự định nghĩa để đặt cạnh tên này trong chương trình. `src` là nguồn có cận trên vì ta đọc `T` từ nó; `dest` có cận dưới vì ta ghi `T` vào đó.

Khác với `appendAll` ở phần trước, `Collections.copy` **thay thế** các phần tử tương ứng trong đích. Danh sách đích phải có kích thước **ít nhất bằng** danh sách nguồn; nó không tự mở rộng đích bằng cách gọi `add`.

Ví dụ Java 17:

```java
List<Integer> source = List.of(7, 8);
List<Number> destination =
        new ArrayList<>(List.of(0, 0, 0));

Collections.copy(destination, source);
System.out.println(destination); // [7, 8, 0]
```

Cần import `java.util.Collections`, `java.util.List` và `java.util.ArrayList`. Nếu `destination` rỗng, lệnh `Collections.copy(destination, source)` sẽ ném `IndexOutOfBoundsException`; nếu đích không sửa đổi được, có thể gặp `UnsupportedOperationException`. Đây là ràng buộc hành vi của API, độc lập với việc kiểu generic đã phù hợp.

## 13. Không phải khai báo nào có `super` cũng là syntax hợp lệ

`super` trong cú pháp đang học là giới hạn **lower bound cho wildcard** ở vị trí đối số kiểu:

```java
List<? super Integer> sink;
Consumer<? super Integer> handler;
Comparator<? super Integer> comparator;
```

Nhưng Java **không** cho phép khai báo type parameter có tên bằng cú pháp `<T super Integer>`:

```java
// class Box<T super Integer> { } // Lỗi cú pháp Java
// static <T super Number> void f() { } // Lỗi cú pháp Java
// List<super Integer> list; // Lỗi: thiếu dấu ? của wildcard
```

Type parameter có tên như `<T extends Number>` sử dụng ràng buộc cận trên. Khi muốn thể hiện một **consumer** của `T` tại vị trí tham số kiểu, ta viết `? super T` trong một kiểu generic, chẳng hạn `List<? super T>`.

Ngoài ra, `? super T` không phải cú pháp dùng trong phép tạo đối tượng:

```java
// List<? super Integer> bad = new ArrayList<? super Integer>(); // Lỗi
List<? super Integer> good = new ArrayList<Number>();          // Đúng
```

Vế tạo đối tượng sử dụng đối số kiểu cụ thể (`Number`) hoặc dấu diamond `<>` để compiler suy luận. Wildcard ở vế khai báo mô tả cách nhìn và quyền thao tác qua biến `good`.

## 14. Những lỗi thường gặp khi học `? super T`

**Lỗi 1: “`? super Integer` nghĩa là mỗi phần tử được đọc ra là `Integer` hoặc kiểu cha.”** Sai. Ràng buộc áp dụng cho đối số kiểu của danh sách. Nếu đối số kiểu thực là `Object`, danh sách có thể chứa `String` từ trước. Khi đọc, chỉ chắc chắn nhận được `Object`.

**Lỗi 2: “Đích `List<? super Integer>` nhận được `Double` vì `Double` và `Integer` cùng là `Number`.”** Sai. `List<? super Integer>` có thể thực chất là `List<Integer>`; chỉ bảo đảm chấp nhận `Integer` và các kiểu con của `Integer` (nếu tồn tại).

**Lỗi 3: “`List<Integer>` truyền được cho `List<Number>` vì `Integer extends Number`.”** Sai. Generics bất biến. Muốn thiết kế hàm nhận danh sách để thêm `Integer`, có thể dùng `List<? super Integer>`.

**Lỗi 4: “Dấu `super` cho biết danh sách bắt buộc có kiểu phần tử chính xác là lớp cha `Number`.”** Sai. Kiểu phần tử có thể là chính `Integer`, một lớp cha hoặc interface cha phù hợp; wildcard không nêu chính xác kiểu đó.

**Lỗi 5: “Nếu `get` chỉ trả về `Object` thì không nên dùng `? super T`.”** Sai khi API là consumer. Chữ ký consumer ưu tiên khả năng ghi `T` an toàn; nếu cần đọc ra `T`, hãy xem lại hợp đồng hoặc dùng một kiểu generic được đặt tên phù hợp.

**Lỗi 6: “`? super T` đảm bảo mọi lời gọi `add` thành công.”** Sai. `add(T)` hợp lệ về kiểu nhưng vẫn có thể ném `UnsupportedOperationException` hoặc lỗi khác do đối tượng danh sách quyết định.

**Lỗi 7: “`Collections.copy` hoạt động giống vòng lặp `add`.”** Sai. `Collections.copy` thay thế phần tử đã có, yêu cầu đích đủ lớn; vòng lặp `add` nối phần tử vào cuối (khi implementation hỗ trợ).

**Lỗi 8: “Dùng raw `List` là cách tránh giới hạn của wildcard.”** Dùng raw type bỏ đi kiểm tra generic và có thể gây *heap pollution*, rồi lỗi `ClassCastException` ở đoạn mã khác. Nên chọn hợp đồng wildcard đúng, không tắt an toàn kiểu.

## 15. Bài tự kiểm tra

Cho đoạn mã:

```java
List<Integer> integers = new ArrayList<>(List.of(1, 2));
List<Number> numbers = new ArrayList<>(List.of(5, 6));
List<Object> objects = new ArrayList<>(List.of("before"));
List<? super Integer> target = numbers;
```

Trả lời trước khi xem đáp án:

1. Có thể gán `target = integers` và `target = objects` không? `target = new ArrayList<Double>()` thì sao?
2. `target.add(7)` và `target.add(null)` có biên dịch không?
3. `target.add(7.5)` có biên dịch không, dù ngay lúc đầu `target` trỏ tới `List<Number>`?
4. Có thể viết `Integer x = target.get(0)` hoặc `Number y = target.get(0)` mà không ép kiểu không?
5. `target.set(0, 99)` có biên dịch không? Nó sửa phần tử ở đâu?
6. `List<? super Number> numberSink = objects;` có biên dịch không? Có thể gọi `numberSink.add(3.14)` không?
7. Nếu `target` tham chiếu `List.of(1, 2)` qua một biến kiểu hợp lệ, `target.add(3)` có được runtime chấp nhận không?

**Đáp án:**

1. Cả `List<Integer>` và `List<Object>` đều hợp lệ. `List<Double>` không phù hợp vì `Double` không phải kiểu cha của `Integer`.
2. Cả hai lời gọi đều hợp lệ khi biên dịch. Đối tượng thực phải hỗ trợ thêm phần tử và có thể có chính sách null riêng.
3. Không. `Double` không phải `Integer`. Compiler dựa vào kiểu tĩnh `List<? super Integer>` thay vì kiểu thực tình cờ là `List<Number>`.
4. Không. Với `get(0)`, kiểu tĩnh an toàn nhất là `Object`. Phép gán cho `Number` hoặc `Integer` cần thêm bằng chứng/kiểm tra phù hợp.
5. Có. `set` được phép nhận `Integer`, sẽ thay phần tử ở chỉ số 0 của đối tượng danh sách mà `target` đang tham chiếu; ở tình huống ban đầu đó là `numbers`.
6. Có. `List<Object>` nhận được `Number` và các kiểu con; `3.14` được boxing thành `Double` là một `Number`.
7. Không. Lời gọi hợp lệ về kiểu nhưng danh sách tạo bởi `List.of` không cho sửa, nên ném `UnsupportedOperationException`.

## 16. Quy tắc ghi nhớ

**`? super T` = “một kiểu chưa biết nhưng đủ rộng để nhận `T`”.** Đây là một ràng buộc của đối số kiểu, giúp API chấp nhận đích kiểu `T` hoặc kiểu cha của `T` và vẫn kiểm tra giá trị ghi vào ở compile time. Đọc phần tử của đích chỉ chắc chắn dưới kiểu `Object` vì dữ liệu đã có có thể thuộc một kiểu rộng hơn `T`.

Khi một tham số đóng vai trò **nơi nhận giá trị `T`**, cân nhắc `? super T`. Khi nó đóng vai trò **nguồn cung cấp giá trị `T`**, cân nhắc `? extends T`. Khi nhiều vị trí cần liên hệ với cùng một kiểu `T`, kết hợp wildcard với type parameter có tên theo nguyên tắc PECS.