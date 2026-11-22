# Thay đổi trạng thái và gán lại tham chiếu trong Java

Trong Java, khi một biến có **kiểu tham chiếu** (*reference type*), giá trị của biến giúp chương trình tham chiếu đến một đối tượng (hoặc là `null`). Hai thao tác thường bị nhầm lẫn là:

1. **Thay đổi trạng thái đối tượng** (*mutating object state*): sửa field hoặc dữ liệu bên trong **đối tượng mà biến đang tham chiếu**.
2. **Gán lại tham chiếu** (*reassigning a reference*): thay đổi **giá trị của biến tham chiếu** để nó trỏ đến đối tượng khác hoặc `null`.

Hai thao tác ảnh hưởng đến những thứ khác nhau. Chúng có thể làm các biểu thức trong chương trình cho kết quả rất khác nhau, đặc biệt khi **nhiều biến cùng tham chiếu một đối tượng**.

Ví dụ:

```java
class Box {
    int value;
}

Box first = new Box();
first.value = 10;

Box alias = first;
alias.value = 20;       // Thay đổi trạng thái Box hiện có

first = new Box();      // Gán lại biến first sang Box mới
first.value = 30;
```

Các khai báo/lệnh trên là minh họa cho một đoạn trong phương thức. Sau khi chạy:

- `alias.value` là **20**: `alias` vẫn tham chiếu đối tượng đầu tiên.
- `first.value` là **30**: `first` đã được gán sang đối tượng thứ hai.
- `first == alias` là **false**: hai biến không còn tham chiếu cùng đối tượng.

**Điểm cốt lõi:** câu lệnh `alias.value = 20` sửa **đối tượng**; câu lệnh `first = new Box()` sửa **biến tham chiếu**. Không nên đánh đồng hai phép gán chỉ vì chúng đều dùng dấu `=`.

## 1. Xác định chính xác thứ được đổi: reference hay object state?

Với hai thao tác `user = new User()` và `user.name = "Mai"`, dấu `=` giống nhau nhưng **đích ghi khác nhau**.

| Câu lệnh | Cái gì thay đổi? | Alias đang có sẽ thấy gì? |
| --- | --- | --- |
| `user = new User();` | Reference của biến `user` | Alias không tự đổi reference |
| `user.name = "Mai";` | Field của object mà user đang trỏ tới | Alias cùng object thấy tên mới |
| `holder.user = other;` | Reference field trong object holder | Alias tới holder thấy liên kết mới |
| `array[0] = other;` | Một slot trong array object | Alias tới array thấy slot mới |
| `user = null;` | Reference của biến user | Object cũ có thể vẫn được alias khác giữ |
| `user.updateName("Mai");` | Tùy implementation method | Phải xem hành vi API, không đoán từ tên |

Đây là các snippets cần classes và biến phù hợp. Trong bài này, người học sẽ theo dõi **mũi tên reference** và **state của từng object** qua method parameters, String immutable, arrays, collection mutation và field reassignment; không lặp lại cả bài khái niệm reference cơ bản.

## 2. Thay đổi trạng thái: sửa đối tượng được tham chiếu

Trong một lớp có field có thể cập nhật:

```java
class Counter {
    int value;
}
```

Đoạn mã sau:

```java
Counter counter = new Counter();
Counter otherName = counter;

counter.value = 5;
otherName.value += 2;
System.out.println(counter.value);  // 7
```

Cả `counter` và `otherName` cùng tham chiếu một đối tượng `Counter`. Vì thế phép cập nhật thông qua bất kỳ biến nào đều sửa cùng field `value`, và cả hai biến sẽ quan sát giá trị mới.

**Thao tác thay đổi trạng thái** có thể được viết bằng:

- Gán field trực tiếp, ví dụ `counter.value = 5` nếu field có quyền truy cập phù hợp.
- Toán tử cập nhật field, ví dụ `counter.value++` hoặc `counter.value += 2`.
- Gọi instance method có tác dụng sửa trạng thái, ví dụ `counter.increment()`.
- Sửa phần tử của đối tượng mảng, ví dụ `array[0] = 10`.
- Gọi phương thức sửa đổi collection, ví dụ `list.add("Java")` với một danh sách mutable.

Không phải mọi lời gọi method đều sửa trạng thái: getter như `counter.getValue()` thường chỉ đọc, còn các API bất biến có thể trả đối tượng mới thay vì sửa đối tượng cũ.

### Dấu chấm và phần bên trái phép gán

So sánh:

```java
counter = new Counter();   // Gán lại BIẾN counter
counter.value = 10;        // Gán lại FIELD value của ĐỐI TƯỢNG
```

Trong dòng thứ nhất, đích của phép gán là `counter`. Trong dòng thứ hai, đích của phép gán là `counter.value`. Hai biểu thức có **vế trái khác nhau**, do đó nơi bị cập nhật khác nhau.

## 3. Gán lại tham chiếu: biến trỏ đến đối tượng khác

Một biến tham chiếu thông thường không khai báo `final` có thể nhận tham chiếu khác:

```java
Counter first = new Counter();
first.value = 10;

Counter second = new Counter();
second.value = 20;

first = second;
```

Sau dòng `first = second;`:

- `first` và `second` cùng tham chiếu **đối tượng thứ hai**.
- `first.value` và `second.value` đều là `20`.
- Đối tượng đầu tiên từng được `first` tham chiếu **không bị biến thành** đối tượng thứ hai. Nó vẫn giữ trạng thái riêng nếu còn tồn tại.
- Nếu không còn tham chiếu nào đến đối tượng đầu tiên và nó không còn reachable qua các đường khác, đối tượng đó có thể **đủ điều kiện cho garbage collection**; không khẳng định JVM thu gom ngay lập tức.

Gán lại một biến **không** tự sao chép trạng thái của đối tượng vào đối tượng mới và cũng không cập nhật mọi bí danh (*alias*) đã từng tham chiếu đối tượng cũ.

### Ví dụ nhiều biến tham chiếu

```java
Counter first = new Counter();
first.value = 1;

Counter second = first;         // Hai biến cùng tham chiếu Counter #1
first = new Counter();          // Chỉ first chuyển sang Counter #2
first.value = 2;

System.out.println(first.value);  // 2
System.out.println(second.value); // 1
```

Sơ đồ sau dòng cuối:

```text
first  ───────────> Counter #2 { value: 2 }

second ───────────> Counter #1 { value: 1 }
```

Điểm khác biệt là **giá trị của biến `first` đổi**, nhưng **giá trị của biến `second` không đổi**. Hai biến không có liên kết “tự cập nhật cùng nhau” sau phép gán `Counter second = first;`.

## 4. Chương trình Java 17 hoàn chỉnh: quan sát cả hai thao tác

Lưu toàn bộ nội dung sau vào **`ReferenceChangeDemo.java`**:

```java
class Box {
    private int value;

    Box(int value) {
        this.value = value;
    }

    int value() {
        return value;
    }

    void setValue(int value) {
        this.value = value;
    }
}

public class ReferenceChangeDemo {
    public static void main(String[] args) {
        Box first = new Box(10);
        Box alias = first;

        System.out.println("Cùng đối tượng: " + (first == alias));

        alias.setValue(20);
        System.out.println("first sau mutate: " + first.value());
        System.out.println("alias sau mutate: " + alias.value());

        first = new Box(30);
        System.out.println("Cùng đối tượng sau reassign: " + (first == alias));
        System.out.println("first mới: " + first.value());
        System.out.println("alias cũ: " + alias.value());

        first = alias;
        System.out.println("Cùng đối tượng sau gán lại: " + (first == alias));
        System.out.println("first cuối: " + first.value());
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 ReferenceChangeDemo.java
java ReferenceChangeDemo
```

**Stdout chính xác:**

```text
Cùng đối tượng: true
first sau mutate: 20
alias sau mutate: 20
Cùng đối tượng sau reassign: false
first mới: 30
alias cũ: 20
Cùng đối tượng sau gán lại: true
first cuối: 20
```

Phân tích:

1. `first` và `alias` ban đầu chứa cùng giá trị tham chiếu nên `first == alias` là `true`.
2. `alias.setValue(20)` thay đổi field `value` của đối tượng chung. `first.value()` và `alias.value()` cùng trả `20`.
3. `first = new Box(30)` tạo một `Box` khác và gán tham chiếu mới vào **biến `first`**.
4. `alias` vẫn trỏ tới `Box` cũ có `value = 20`, nên `first == alias` chuyển thành `false`.
5. `first = alias` chỉ sao chép tham chiếu từ `alias` sang `first`; đối tượng mới có giá trị `30` không bị “ghi thành `20`”, mà `first` ngừng tham chiếu tới nó. Sau đó hai biến lại chỉ cùng đối tượng cũ.

Ví dụ dùng field `private` và setter `setValue` để phân biệt thêm rằng **gọi phương thức sửa trạng thái** vẫn là mutation, dù caller không được phép truy cập field trực tiếp.

## 5. Quan sát mutation qua alias; quan sát reassignment qua chính biến

Giả sử `Box` có `setValue(int)` và `value()`:

~~~java
Box original = new Box(5);
Box alias = original;
alias.setValue(7);
System.out.println(original.value()); // 7
alias = new Box(9);
System.out.println(original.value()); // vẫn 7
~~~

Đây là snippet minh họa trong method. Mutation tác động object cũ nên original nhìn thấy 7; việc gán lại alias chỉ thay reference trong alias, không hoàn tác mutation hoặc thay reference original.

Muốn dự đoán output, kẻ hai cột sau mỗi statement: **reference của từng biến đang trỏ object nào** và **state của từng object đang là gì**. Dùng reference `==` để kiểm tra cùng instance, không dùng `equals` khi câu hỏi chỉ là identity. Cách truy vết này khác với bài aliasing chuyên sâu về chia sẻ nested mutable objects và defensive copying.

## 6. Truyền đối số vào method: Java luôn pass-by-value

Một nhầm lẫn nghiêm trọng là cho rằng Java “truyền đối tượng bằng tham chiếu” nghĩa là method nhận có thể **gán lại biến của caller**. Thực tế, Java truyền **bản sao giá trị của từng đối số** vào tham số hình thức:

- Nếu đối số là primitive, bản sao là giá trị primitive.
- Nếu đối số là tham chiếu, bản sao là **giá trị tham chiếu**.
- Gán lại **biến tham số** chỉ sửa biến tham số đó.
- Sửa **trạng thái đối tượng qua tham số** có thể làm caller thấy thay đổi nếu caller còn tham chiếu cùng đối tượng.

### 6.1. Chương trình runnable: mutate rồi reassign tham số

Lưu thành **`ParameterReferenceDemo.java`**:

```java
class Counter {
    int value;

    Counter(int value) {
        this.value = value;
    }
}

public class ParameterReferenceDemo {
    static void mutate(Counter counter) {
        counter.value += 5;
    }

    static void reassign(Counter counter) {
        counter = new Counter(99);
        System.out.println("Trong reassign: " + counter.value);
    }

    static Counter replace(Counter counter) {
        counter = new Counter(counter.value * 2);
        return counter;
    }

    public static void main(String[] args) {
        Counter current = new Counter(10);

        mutate(current);
        System.out.println("Sau mutate: " + current.value);

        reassign(current);
        System.out.println("Sau reassign: " + current.value);

        Counter next = replace(current);
        System.out.println("current: " + current.value);
        System.out.println("next: " + next.value);
        System.out.println("Cùng tham chiếu: " + (current == next));
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 ParameterReferenceDemo.java
java ParameterReferenceDemo
```

**Stdout:**

```text
Sau mutate: 15
Trong reassign: 99
Sau reassign: 15
current: 15
next: 30
Cùng tham chiếu: false
```

Diễn giải:

- `mutate(current)` sao chép tham chiếu của `current` vào tham số `counter`. Cả hai chọn cùng đối tượng; `counter.value += 5` khiến `current.value` thành `15`.
- `reassign(current)` nhận cùng tham chiếu ban đầu, nhưng `counter = new Counter(99)` chỉ thay đổi **biến tham số cục bộ**. Sau khi phương thức kết thúc, `current` vẫn trỏ đối tượng có `15`.
- `replace(current)` tạo đối tượng mới chứa `30`, **trả tham chiếu đối tượng mới**. Caller lưu giá trị đó vào `next`. Nếu muốn biến `current` chuyển sang đối tượng mới, caller phải **tự gán** `current = replace(current);`.
- `current == next` là `false` vì hai tham chiếu khác đối tượng.

**Quy tắc thao tác chính xác:** để một method tạo đối tượng mới rồi thay thế đối tượng mà caller sử dụng, thường **trả về tham chiếu mới**, sau đó caller quyết định **gán lại biến**.

### 6.2. Tại sao tham số kiểu `final` không làm object bất biến?

`final Counter counter` bên trong danh sách tham số cấm `counter = new Counter(...)`, nhưng **không cấm** `counter.value++` nếu field có thể sửa và quyền truy cập cho phép.

```java
static void increment(final Counter counter) {
    counter.value++;
    // counter = new Counter(0); // SAI: gán lại tham số final
}
```

`final` gắn với **biến tham số**, không tự khóa toàn bộ trạng thái của đối tượng mà biến tham số trỏ đến.

## 7. `return this` và thay đổi trạng thái: cùng một đối tượng hay đối tượng mới?

Một instance method có thể thay đổi trạng thái đối tượng rồi trả về **`this`**:

```java
class Score {
    private int points;

    Score(int points) {
        this.points = points;
    }

    Score add(int amount) {
        points += amount;
        return this;
    }

    int points() {
        return points;
    }
}
```

`Score next = score.add(10);` **không tự tạo đối tượng mới**: `next` và `score` cùng trỏ đến thể hiện hiện tại. Phong cách này thường dùng trong **mutable fluent API**.

So sánh một cách thiết kế khác:

```java
final class ImmutableScore {
    private final int points;

    ImmutableScore(int points) {
        this.points = points;
    }

    ImmutableScore add(int amount) {
        return new ImmutableScore(points + amount);
    }

    int points() {
        return points;
    }
}
```

`ImmutableScore newer = older.add(10);` trả về **đối tượng mới**. `older` vẫn tham chiếu đối tượng cũ, và nội dung của nó không đổi.

**Hai API đều có tên `add` nhưng ngữ nghĩa khác nhau.** Muốn xác định thao tác **mutate** hay **return new object**, phải đọc hợp đồng/phần cài đặt, không suy đoán từ kiểu trả về hoặc tên phương thức.

## 8. Gán lại tham chiếu và gán lại field kiểu tham chiếu

Một object có thể chứa **field tham chiếu đến object khác**:

```java
class Address {
    String city;

    Address(String city) {
        this.city = city;
    }
}

class Customer {
    Address address;

    Customer(Address address) {
        this.address = address;
    }
}
```

Với:

```java
Address address = new Address("Hà Nội");
Customer customer = new Customer(address);

customer.address.city = "Đà Nẵng"; // (A)
customer.address = new Address("Huế"); // (B)
```

Hai dòng ảnh hưởng khác nhau:

- **(A) Thay đổi trạng thái**: field `city` của đối tượng `Address` ban đầu đổi từ `"Hà Nội"` sang `"Đà Nẵng"`. Biến `address` vẫn trỏ đến chính đối tượng ban đầu, nên `address.city` đọc là `"Đà Nẵng"`.
- **(B) Gán lại field tham chiếu**: field `customer.address` được gán tham chiếu tới một `Address` mới có `city = "Huế"`. Biến cục bộ `address` **không thay đổi**, nó vẫn trỏ đối tượng ban đầu có `city = "Đà Nẵng"`.

Sơ đồ sau (B):

```text
address ──────────────────> Address #1 { city: "Đà Nẵng" }

customer ───> Customer
                 └── address ───> Address #2 { city: "Huế" }
```

**Gán lại tham chiếu không chỉ xảy ra với biến cục bộ.** Một field tham chiếu, phần tử mảng tham chiếu hoặc biến static cũng có thể được gán tham chiếu mới nếu các quy tắc kiểu, quyền truy cập và `final` cho phép.

### Ví dụ hoàn chỉnh về field tham chiếu

Lưu thành **`ReferenceFieldDemo.java`**:

```java
class Address {
    String city;

    Address(String city) {
        this.city = city;
    }
}

class Customer {
    Address address;

    Customer(Address address) {
        this.address = address;
    }
}

public class ReferenceFieldDemo {
    public static void main(String[] args) {
        Address firstAddress = new Address("Hà Nội");
        Customer customer = new Customer(firstAddress);

        customer.address.city = "Đà Nẵng";
        System.out.println(firstAddress.city);

        customer.address = new Address("Huế");
        System.out.println(customer.address.city);
        System.out.println(firstAddress.city);
        System.out.println(customer.address == firstAddress);
    }
}
```

```bash
javac -encoding UTF-8 ReferenceFieldDemo.java
java ReferenceFieldDemo
```

Stdout:

```text
Đà Nẵng
Huế
Đà Nẵng
false
```

Chương trình xác nhận **mutation của Address cũ** không đồng nghĩa **thay field tham chiếu đến Address mới**.

## 9. Mảng: thay phần tử khác với gán lại biến mảng

**Mảng là đối tượng** trong Java. Vì vậy với `int[]`:

```java
int[] numbers = {1, 2};
int[] alias = numbers;
```

`numbers` và `alias` đều là các biến tham chiếu tới cùng đối tượng mảng.

- `numbers[0] = 9;` thay đổi **trạng thái mảng**; `alias[0]` cũng là `9`.
- `numbers = new int[]{3, 4};` gán lại **biến `numbers`** để nó trỏ mảng mới; `alias[0]` vẫn là `9`.
- `alias = null;` chỉ đặt biến `alias` thành `null`; mảng cũ không tự biến thành `null`.

### Ví dụ Java 17 về alias của mảng

Lưu thành **`ArrayReferenceDemo.java`**:

```java
import java.util.Arrays;

public class ArrayReferenceDemo {
    public static void main(String[] args) {
        int[] first = {1, 2};
        int[] alias = first;

        first[0] = 9;
        System.out.println(Arrays.toString(alias));

        first = new int[]{3, 4};
        System.out.println(Arrays.toString(first));
        System.out.println(Arrays.toString(alias));
        System.out.println(first == alias);
    }
}
```

```bash
javac -encoding UTF-8 ArrayReferenceDemo.java
java ArrayReferenceDemo
```

Stdout:

```text
[9, 2]
[3, 4]
[9, 2]
false
```

Chú ý **mảng có số phần tử cố định**: có thể đổi phần tử, nhưng không thể trực tiếp tăng `length` của một đối tượng mảng. Nếu cần số phần tử khác, thường tạo mảng mới hoặc dùng collection như `ArrayList`. Khi `numbers = Arrays.copyOf(numbers, 3)`, đó là gán lại biến sang một **đối tượng mảng mới**.

## 10. Collection: `add`, `set` và gán lại biến danh sách

`ArrayList` là đối tượng mutable. Vì vậy hai biến trỏ cùng một danh sách sẽ thấy các cập nhật:

```java
java.util.List<String> left = new java.util.ArrayList<>();
left.add("A");

java.util.List<String> right = left;
right.add("B");
```

Sau đó `left` và `right` cùng nhìn thấy `[A, B]`.

Nếu viết `right = new java.util.ArrayList<>();`, chỉ biến `right` chuyển sang danh sách mới. `left` tiếp tục trỏ danh sách cũ với `[A, B]`.

### Chương trình tổng hợp về hai thao tác

Lưu thành **`ListReferenceDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class ListReferenceDemo {
    public static void main(String[] args) {
        List<String> first = new ArrayList<>();
        first.add("Java");

        List<String> second = first;
        second.add("Core");

        System.out.println(first);
        System.out.println(first == second);

        second = new ArrayList<>(first);
        second.set(0, "Spring");

        System.out.println(first);
        System.out.println(second);
        System.out.println(first == second);
    }
}
```

```bash
javac -encoding UTF-8 ListReferenceDemo.java
java ListReferenceDemo
```

Stdout:

```text
[Java, Core]
true
[Java, Core]
[Spring, Core]
false
```

Giải thích:

1. `second = first` tạo **alias**.
2. `second.add("Core")` sửa **cùng đối tượng list**. `first` thấy phần tử mới.
3. `second = new ArrayList<>(first)` tạo **đối tượng danh sách mới**, có các phần tử được sao chép theo cơ chế của constructor; đây là **shallow copy** của danh sách.
4. `second.set(0, "Spring")` chỉ thay phần tử trong danh sách mới, không sửa danh sách `first`.
5. `first == second` là `false` vì từ bước (3) đã có hai list khác nhau.

**Shallow copy quan trọng:** `new ArrayList<>(first)` sao chép cấu trúc chứa các **tham chiếu phần tử**, không clone sâu mọi object thành viên. Nếu phần tử là đối tượng mutable và hai list cùng trỏ phần tử ấy, sửa trạng thái phần tử đó vẫn có thể quan sát qua cả hai list.

## 11. `String` và kiểu bất biến: tưởng như sửa nhưng thực chất là tham chiếu mới

**`String` trong Java là immutable**: sau khi một đối tượng chuỗi được tạo, không có API thông thường nào sửa nội dung của chính đối tượng đó.

```java
String first = "Java";
String alias = first;

first = first + " 17";
```

Dòng cuối tạo/nhận một giá trị tham chiếu `String` đại diện nội dung `"Java 17"` và gán lại biến `first`. Nó **không sửa nội dung** của đối tượng chuỗi `"Java"` mà `alias` vẫn tham chiếu.

Vì vậy:

```java
System.out.println(first); // Java 17
System.out.println(alias); // Java
```

Trong trường hợp này, `first = first + " 17"` là **gán lại biến tham chiếu**, không phải mutation của một đối tượng `String`.

### `StringBuilder` khác `String`

`StringBuilder` là đối tượng mutable:

```java
StringBuilder builder = new StringBuilder("Java");
StringBuilder aliasBuilder = builder;

builder.append(" 17");
System.out.println(aliasBuilder); // Java 17
```

`append` thay đổi **trạng thái StringBuilder hiện có**, nên alias nhìn thấy thay đổi. Nếu viết `builder = new StringBuilder("Khác");`, `aliasBuilder` vẫn trỏ builder cũ với `"Java 17"`.

### Ví dụ chạy được để đối chiếu

Lưu thành **`StringReferenceDemo.java`**:

```java
public class StringReferenceDemo {
    public static void main(String[] args) {
        String text = "Java";
        String sameText = text;

        text = text.concat(" 17");
        System.out.println(text);
        System.out.println(sameText);

        StringBuilder builder = new StringBuilder("Core");
        StringBuilder sameBuilder = builder;

        builder.append(" API");
        System.out.println(builder);
        System.out.println(sameBuilder);

        builder = new StringBuilder("New");
        System.out.println(builder);
        System.out.println(sameBuilder);
    }
}
```

```bash
javac -encoding UTF-8 StringReferenceDemo.java
java StringReferenceDemo
```

Stdout:

```text
Java 17
Java
Core API
Core API
New
Core API
```

Điểm kiểm tra: nhìn thấy `text` khác `sameText` sau phép nối chuỗi **không phải do Java copy-on-write mọi object**. Lý do cụ thể là `String` bất biến và lời gọi `concat` trả về một giá trị tham chiếu; biến `text` được gán lại.

## 12. `final`: cấm gán lại biến nhưng chưa chắc cấm mutation

Một biến tham chiếu khai báo `final` không được gán lại sau khi đã khởi tạo hợp lệ:

```java
final Box box = new Box(10);

// box = new Box(20); // SAI: box là biến final
box.setValue(20);      // HỢP LỆ nếu phương thức cho phép
```

Từ `final` trong dòng `final Box box` **ràng buộc biến `box`**, không tự làm đối tượng `Box` trở thành immutable. Có thể thay đổi các field mutable của đối tượng qua tham chiếu `box`.

Một số tình huống cần phân biệt:

| Khai báo | Có được gán lại tham chiếu? | Có được sửa đối tượng? |
| --- | --- | --- |
| `Box b = new Box(1);` | Có | Có, nếu API cho phép |
| `final Box b = new Box(1);` | Không | Có, nếu API cho phép |
| `final String s = "A";` | Không | `String` bất biến nên không sửa nội dung trực tiếp |
| `final List<String> list = new ArrayList<>();` | Không | Có thể `list.add(...)` vì `ArrayList` mutable |
| `final List<String> list = List.of("A");` | Không | Không thể sửa list bằng những mutator bị từ chối của `List.of` |

Tương tự, **final field** giữ giá trị tham chiếu không đổi sau khi được khởi tạo hợp lệ, nhưng **đối tượng nằm sau tham chiếu có thể mutable**.

```java
class Holder {
    final java.util.List<String> items = new java.util.ArrayList<>();

    void add(String item) {
        items.add(item);          // Hợp lệ
        // items = new ArrayList<>(); // SAI: field final
    }
}
```

Nếu cần **bất biến thực sự**, phải xem cả khả năng sửa trạng thái của object và tham chiếu đến các object mutable bên trong, không chỉ thêm từ khóa `final`.

### Biến `final` và hằng tham chiếu không đồng nghĩa

`static final List<String> VALUES = new ArrayList<>();` ngăn gán lại field `VALUES`, nhưng list vẫn có thể bị sửa thông qua các API mutable. Khi muốn dữ liệu bất biến, dùng cấu trúc phù hợp như `List.of(...)`, `List.copyOf(...)` hoặc một lớp tự bảo vệ trạng thái — đồng thời phải cân nhắc tính mutable của **phần tử**.

## 13. `null`: gán lại tham chiếu rỗng khác với xóa đối tượng

Một biến tham chiếu có thể chứa `null`:

```java
Box box = new Box(10);
Box other = box;

box = null;
```

Sau đó:

- `box == null` là `true`.
- `other` vẫn tham chiếu đối tượng `Box` ban đầu.
- `other.value()` vẫn có thể trả `10`.
- `box.value()` ném `NullPointerException` nếu lời gọi được thực thi, vì `box` không tham chiếu đối tượng.

**`box = null` không phá hủy đối tượng theo lệnh**, không đặt các field của đối tượng thành `null` và không tự ảnh hưởng `other`. Nó chỉ thay đổi **giá trị một biến tham chiếu**.

Khi đối tượng không còn reachable, JVM có thể thu gom theo chiến lược garbage collector; việc `box = null` không bảo đảm thu gom tức thì hay gọi một hành vi dọn dẹp xác định.

### Ví dụ có guard

```java
if (box != null) {
    System.out.println(box.value());
} else {
    System.out.println("Không có Box");
}
```

Ở đây kiểm tra `null` chỉ cho biết **biến có tham chiếu hay không**; nó không chứng minh object bất biến, còn sống cho tới một thời điểm cụ thể, hoặc được dùng bởi bao nhiêu alias.

## 14. Mutate qua tham chiếu khác không yêu cầu cùng tên biến

Các đối tượng có thể được chia sẻ qua **field**, **tham số**, **phần tử mảng** hoặc **collection**, không chỉ qua hai biến cục bộ.

Ví dụ:

```java
class Node {
    int value;
}

Node shared = new Node();
Node[] nodes = {shared};
java.util.List<Node> list = new java.util.ArrayList<>();
list.add(shared);

nodes[0].value = 7;
System.out.println(list.get(0).value); // 7
```

`shared`, `nodes[0]` và `list.get(0)` đều cung cấp tham chiếu đến cùng một `Node`. Thay đổi `value` qua một đường truy cập được thấy qua các đường khác.

Nhưng nếu gán:

```java
nodes[0] = new Node();
nodes[0].value = 3;
```

thì **phần tử mảng `nodes[0]` bị gán tham chiếu mới**; biến `shared` và phần tử trong `list` vẫn trỏ `Node` cũ có `value = 7`.

Không nhầm **thay phần tử mảng tham chiếu** với **sửa trạng thái đối tượng được phần tử đó tham chiếu**:

- `nodes[0].value = 3;`: sửa field `value` của object hiện tại.
- `nodes[0] = new Node();`: thay tham chiếu nằm ở vị trí `nodes[0]`.

## 15. Shallow copy và deep copy: không phải mọi “copy” đều tách trạng thái

**Sao chép tham chiếu**:

```java
Address second = first;
```

`second` và `first` cùng trỏ đối tượng, nên mọi mutation trên đối tượng có thể được chia sẻ.

**Shallow copy** tạo một object chứa mới nhưng giữ lại tham chiếu đến những object lồng bên trong. Ví dụ:

```java
class Person {
    String name;
    Address address;

    Person(String name, Address address) {
        this.name = name;
        this.address = address;
    }
}
```

Giả sử:

```java
Address address = new Address("Hà Nội");
Person original = new Person("An", address);
Person shallow = new Person(original.name, original.address);
```

`original` và `shallow` là **hai thể hiện `Person` khác nhau**. Tuy nhiên `original.address` và `shallow.address` cùng tham chiếu **một `Address`**, vì constructor dùng cùng giá trị tham chiếu.

Vì thế:

```java
shallow.name = "Bình";           // Chỉ sửa Person shallow
shallow.address.city = "Huế";    // Sửa Address dùng chung
```

Sau đó `original.name` vẫn là `"An"`, còn `original.address.city` đã thành `"Huế"`.

**Deep copy** (sao chép sâu) thường nhằm tạo các đối tượng lồng cần thiết theo cách tránh chia sẻ trạng thái mutable. Với `Person` đơn giản ở trên, có thể cân nhắc:

```java
Person deep = new Person(
        original.name,
        new Address(original.address.city)
);
```

Lúc này `deep.address` khác object `original.address`. Tuy nhiên **deep copy không có một phép thuật chung** cho mọi object graph: nếu đối tượng chứa nhiều liên kết, chu trình, tài nguyên ngoài bộ nhớ hay đối tượng bất biến, cần chính sách sao chép phù hợp để tránh lỗi hoặc sao chép không cần thiết.

### Khi API trả về một field mutable

```java
class Library {
    private final java.util.List<String> names = new java.util.ArrayList<>();

    java.util.List<String> names() {
        return names; // Trả cùng tham chiếu mutable
    }
}
```

Bên gọi được phép sử dụng list trả về theo access và có thể `library.names().add("X")`, từ đó sửa trạng thái **bên trong `Library`**.

Nếu không muốn lộ mutable state, một phương án là trả `List.copyOf(names)` (một list không sửa được qua các mutator chuẩn, sao chép phần tử theo tham chiếu và không hỗ trợ phần tử `null`), hoặc trả một bản sao khác phù hợp với hợp đồng. Cần nhớ bản sao **shallow** vẫn có thể giữ tham chiếu đến phần tử mutable.

## 16. Gán lại tham chiếu trong vòng lặp và điều kiện

Một biến có thể đổi đối tượng được tham chiếu nhiều lần:

```java
Box chosen = new Box(1);

if (chosen.value() < 5) {
    chosen = new Box(10);
}
System.out.println(chosen.value()); // 10
```

Nhánh `if` thay đổi **biến `chosen`**, không cập nhật Box có `value = 1`. Những alias khác (nếu có) đến Box cũ sẽ không bị ảnh hưởng.

Trong vòng lặp, chú ý scope của biến:

```java
Box current = new Box(0);

for (int i = 0; i < 3; i++) {
    current = new Box(i);
}
System.out.println(current.value()); // 2
```

Mỗi vòng lặp tạo Box mới và gán tham chiếu vào `current`. Cuối cùng `current` trỏ Box có `value = 2`. Nếu bên ngoài còn giữ các Box từ vòng trước, chúng vẫn độc lập; nếu không, chúng có thể trở thành đối tượng không reachable.

**Mục đích học tập:** chỉ nhìn thấy biến `current` có một tên không có nghĩa chương trình chỉ tạo một object qua tất cả vòng lặp.

## 17. Gán lại trường `static` tham chiếu và chia sẻ toàn chương trình

Một field tham chiếu `static` thuộc lớp theo quy tắc của Java. Nếu mã thay `static field` từ object A sang object B, các nơi truy cập chính field đó có thể thấy tham chiếu mới sau khi thỏa quy tắc bộ nhớ Java.

```java
class Registry {
    static Box current = new Box(1);
}
```

Trong một phương thức:

```java
Box saved = Registry.current;
Registry.current.setValue(2); // Mutate Box #1
Registry.current = new Box(3); // Reassign static field

System.out.println(saved.value());          // 2
System.out.println(Registry.current.value()); // 3
```

`saved` giữ tham chiếu Box cũ; gán lại `Registry.current` không làm `saved` đổi.

**Lưu ý đa luồng:** nếu các thread khác nhau cùng đọc/ghi một static hoặc instance reference field, quy tắc *happens-before*, `volatile`, synchronization và các kiểu atomic có ý nghĩa thực tế. Một phép gán tham chiếu đơn lẻ có những đặc tính nguyên tử cơ bản, nhưng **không** biến toàn bộ thao tác “đọc trạng thái → sửa trạng thái → thay tham chiếu” thành một giao dịch nguyên tử. Dùng `AtomicReference`, khóa hoặc thiết kế immutable snapshot khi cần phối hợp đồng thời; đừng dựa vào “trông có vẻ là một phép gán”.

## 18. Gán lại tham chiếu và immutable object: thay vì sửa, tạo bản mới

Với **immutable object**, các giá trị trạng thái quan trọng không được thay đổi sau khi tạo. Muốn trạng thái logic khác, thường **tạo đối tượng mới và gán lại biến**.

Ví dụ sử dụng `record` trong Java 17:

```java
record Point(int x, int y) {
    Point moveX(int delta) {
        return new Point(x + delta, y);
    }
}
```

Trong một phương thức:

```java
Point original = new Point(1, 2);
Point updated = original.moveX(3);

System.out.println(original);  // Point[x=1, y=2]
System.out.println(updated);   // Point[x=4, y=2]
System.out.println(original == updated); // false
```

`Point.moveX` không sửa object `original` mà tạo một `Point` mới. Nếu caller muốn biến `original` tham chiếu trạng thái mới, phải viết `original = original.moveX(3);` (nếu biến không `final`).

Lưu ý: record component có final fields nhưng điều này chỉ cung cấp **bất biến nông** đối với các component. Nếu record giữ một `List` mutable, state của list ấy vẫn có thể bị thay đổi trừ khi thiết kế tự sao chép/bảo vệ phù hợp.

### Chương trình chạy được với immutable record

Lưu **`RecordReferenceDemo.java`**:

```java
record Point(int x, int y) {
    Point moveX(int delta) {
        return new Point(x + delta, y);
    }
}

public class RecordReferenceDemo {
    public static void main(String[] args) {
        Point original = new Point(1, 2);
        Point updated = original.moveX(3);

        System.out.println(original);
        System.out.println(updated);
        System.out.println(original == updated);

        original = updated;
        System.out.println(original);
    }
}
```

```bash
javac -encoding UTF-8 RecordReferenceDemo.java
java RecordReferenceDemo
```

Stdout:

```text
Point[x=1, y=2]
Point[x=4, y=2]
false
Point[x=4, y=2]
```

Dòng cuối cho thấy **biến `original` được gán tham chiếu mới**, chứ không phải object `Point` ban đầu bị sửa.

## 19. Quyền truy cập ảnh hưởng khả năng sửa object, không thay đổi cơ chế tham chiếu

Không phải mọi đối tượng đều cho phép caller sửa field trực tiếp. Ví dụ:

```java
class BankAccount {
    private int balance;

    BankAccount(int initial) {
        if (initial < 0) {
            throw new IllegalArgumentException("negative initial balance");
        }
        balance = initial;
    }

    void deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("nonpositive deposit");
        }
        balance += amount;
    }

    int balance() {
        return balance;
    }
}
```

Với:

```java
BankAccount first = new BankAccount(100);
BankAccount alias = first;

alias.deposit(50);
System.out.println(first.balance()); // 150

// first.balance = -20;  // Lỗi biên dịch: balance là private
```

**Điểm chính:** field `private` không ngăn **aliasing**. Hai tham chiếu vẫn trỏ cùng object và thấy cùng trạng thái. Tuy nhiên lớp kiểm soát **cách trạng thái được phép thay đổi**, ví dụ qua `deposit` với điều kiện nghiệp vụ.

Đóng gói (*encapsulation*) giảm nguy cơ mã bên ngoài sửa tùy tiện trạng thái, nhưng không ngăn một API hợp lệ của object mutable cập nhật object đó.

## 20. Những lỗi thường gặp

| Tình huống | Hiểu nhầm | Cách hiểu/sửa |
| --- | --- | --- |
| `Box b = a;` | Nghĩ là clone `a` | Chỉ sao chép giá trị tham chiếu; `a` và `b` alias nhau |
| `b.value = 5;` | Nghĩ rằng chỉ “sửa biến b” | Đang sửa field của object `b` trỏ tới |
| `b = new Box();` | Nghĩ đã reset object cũ | Đang gán biến `b` sang object mới |
| `void reassign(Box b) { b = new Box(); }` | Nghĩ biến của caller được thay | Chỉ biến tham số `b` đổi; caller không đổi |
| `String s = s + "x";` | Nghĩ nội dung object `String` cũ đổi | `String` bất biến; biến `s` nhận tham chiếu tới chuỗi kết quả |
| `final Box b = new Box();` | Nghĩ object không thể sửa | `final` trên biến chỉ cấm gán lại `b` |
| `list2 = new ArrayList<>(list1);` | Nghĩ clone sâu mọi phần tử | Mới là copy cấu trúc list, thường **shallow copy** |
| `a.equals(b)` trả `true` | Nghĩ hai biến trỏ cùng instance | Có thể là hai object bằng nhau theo nội dung nhưng identity khác |
| `a = null;` | Nghĩ object bị xóa ngay | Chỉ biến `a` nhận `null`; alias khác có thể còn object |
| `array[0] = new Box();` | Nghĩ object cũ ở vị trí đó được sửa | Phần tử mảng tham chiếu sang object mới |
| `holder.field = new Box();` | Nghĩ biến cục bộ khác cũng đổi | Chỉ field tham chiếu `holder.field` được gán lại |
| Gọi mutation trên shared state từ nhiều thread | Nghĩ có alias là an toàn khi đồng thời | Cần đồng bộ/hợp đồng thread-safety phù hợp |
| `record` hoặc `final` | Nghĩ mọi object bên trong đều immutable | Kiểm tra component/field tham chiếu tới dữ liệu mutable |
| `counter++` trên field dùng chung | Nghĩ là một phép nguyên tử nhiều thread | Đây là thao tác đọc–sửa–ghi; cần giải pháp đồng thời phù hợp |

Khi gặp bug, hãy hỏi **vế trái phép gán là gì?** Nếu là biến tham chiếu, biến đó đổi. Nếu là field hoặc phần tử của object, trạng thái object tương ứng đổi. Nếu là giá trị trả về từ method, cần đọc hợp đồng phương thức để biết liệu nó đã sửa object hay tạo object mới.

## 21. Bài tự luyện với đáp án

### Bài 1 — Alias và gán lại

```java
class Item {
    int count;

    Item(int count) {
        this.count = count;
    }
}
```

Đoạn mã:

```java
Item x = new Item(1);
Item y = x;
x.count = 2;
x = new Item(3);
System.out.println(x.count);
System.out.println(y.count);
System.out.println(x == y);
```

**Đáp án:**

```text
3
2
false
```

`y` vẫn tham chiếu object cũ được cập nhật thành `2`. `x` chuyển sang object mới có `3`.

### Bài 2 — Tham số truyền theo giá trị

```java
static void change(Item item) {
    item.count = 4;
    item = new Item(10);
}
```

Caller:

```java
Item original = new Item(1);
change(original);
System.out.println(original.count);
```

**Đáp án:** `4`. Phép sửa field trước khi reassign tham số tác động lên object của caller; phép gán lại biến tham số sau đó không thay đổi `original`.

### Bài 3 — Thay tham chiếu trong field

```java
Address shared = new Address("A");
Customer customer = new Customer(shared);
customer.address.city = "B";
customer.address = new Address("C");
System.out.println(shared.city);
System.out.println(customer.address.city);
```

**Đáp án:** lần lượt `B` và `C`. Object `Address` cũ vẫn giữ `B`; field `customer.address` trỏ đến object mới `C`.

### Bài 4 — `final` có cấm sửa list?

```java
final java.util.List<String> names = new java.util.ArrayList<>();
names.add("Java");
```

**Đáp án:** `names.add("Java")` hợp lệ vì list mutable. `names = new ArrayList<>();` không hợp lệ vì `names` là biến final. Đó là hai giới hạn khác nhau.

### Bài 5 — Mảng và alias

```java
int[] a = {1, 2};
int[] b = a;
a[0] = 7;
a = new int[]{8, 9};

System.out.println(b[0]);
System.out.println(a[0]);
```

**Đáp án:** `7` rồi `8`. `b` giữ mảng cũ bị sửa phần tử đầu; `a` trỏ mảng mới.

### Bài 6 — Sao chép danh sách có tách object phần tử?

Giả sử một `List<Item>` chứa một `Item` mutable. Tạo `List<Item> copy = new ArrayList<>(original);` có bảo đảm sửa `copy.get(0).count` không ảnh hưởng `original.get(0).count` không?

**Đáp án:** **Không.** `ArrayList` mới có cấu trúc độc lập, nhưng các phần tử là tham chiếu tới object `Item` cũ. Cần chính sách sao chép phần tử nếu muốn trạng thái độc lập.

### Bài 7 — String và StringBuilder

```java
String s1 = "A";
String s2 = s1;
s1 += "B";

StringBuilder b1 = new StringBuilder("A");
StringBuilder b2 = b1;
b1.append("B");
```

**Đáp án:** `s1` là `"AB"`, `s2` là `"A"` vì chuỗi bất biến và biến `s1` đã được gán lại; `b1` và `b2` đều thể hiện nội dung `"AB"` vì cùng tham chiếu mutable `StringBuilder`.

## 22. Checklist phân tích thay đổi trạng thái và tham chiếu

1. **Xác định kiểu biến:** primitive hay reference type?
2. **Xác định số đối tượng được tạo:** mỗi `new` hoàn tất bình thường có thể tạo một thể hiện mới; đừng đếm số tên biến như số object.
3. **Vẽ sơ đồ alias:** biến/field/phần tử mảng nào đang trỏ cùng object?
4. **Nhìn đích của phép gán:** `ref = ...` gán biến; `ref.field = ...` gán field; `array[i] = ...` gán phần tử mảng.
5. **Phân biệt kiểu field:** field primitive được ghi giá trị; field tham chiếu có thể được gán sang object khác.
6. **Đọc phương thức được gọi:** getter, setter, mutator, builder hay immutable “with” có thể có tác động khác nhau.
7. **Kiểm tra `final`:** ràng buộc với biến/field tham chiếu không tự động khóa object mutable.
8. **Kiểm tra `null`:** biến `null` không có object để truy cập instance field/method; gán `null` không hủy các alias khác.
9. **Xem tham số method:** Java pass-by-value; mutate qua tham số có thể tác động object chung, reassign tham số không thay biến caller.
10. **Nếu tạo bản sao, xác định nông hay sâu:** sao chép collection không nhất thiết sao chép phần tử.
11. **Xem chuyện chia sẻ trạng thái:** đối tượng được nhiều thành phần/thread giữ tham chiếu có thể cần đóng gói, bảo vệ bất biến và đồng bộ.
12. **Kiểm tra kết quả bằng identity khi cần:** `a == b` với tham chiếu cho biết có đang trỏ cùng object không, nhưng đừng nhầm nó với `equals` so sánh giá trị logic.

## Ghi nhớ

- **Thay đổi trạng thái (mutation)** tác động lên dữ liệu **bên trong đối tượng hiện có**; mọi alias tới cùng đối tượng có thể quan sát thay đổi đó.
- **Gán lại tham chiếu (reassignment)** thay đổi **biến, field hoặc phần tử mảng chứa tham chiếu**; nó không cập nhật mọi alias đang trỏ object trước đó.
- **`Box other = box` chỉ sao chép tham chiếu**, không clone đối tượng; `other.value = 3` khác hoàn toàn `other = new Box()`.
- Java **truyền đối số theo giá trị**. Với tham chiếu, bên nhận có bản sao giá trị tham chiếu, không thể gán lại biến của caller.
- **`final` trên biến tham chiếu cấm gán lại biến**, nhưng có thể vẫn cho phép sửa object mutable; `String` và các immutable object thường biểu diễn thay đổi bằng đối tượng mới và phép gán lại tham chiếu.
- Khi không chắc, hãy vẽ **biến → đối tượng** trước và sau từng dòng; đó là cách đơn giản, đáng tin để tránh nhầm lẫn.
