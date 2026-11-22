# Truyền bản sao tham chiếu vào phương thức trong Java

Trong Java, **mọi đối số đều được truyền theo giá trị (*pass-by-value*)**, kể cả đối số có kiểu tham chiếu như `String`, `Customer`, `int[]`, `List<String>` hoặc một interface. Khi gọi method với một biến tham chiếu, Java **sao chép giá trị tham chiếu** vào **biến tham số hình thức (*formal parameter*)** của method. **Không sao chép toàn bộ object**, và cũng **không truyền chính biến của người gọi để method gán lại nó**.

Đây là quy tắc rất quan trọng nhưng dễ gây hiểu nhầm vì Java cho phép method **thay đổi trạng thái của object** mà cả caller và callee cùng tham chiếu. Một thao tác như `parameter.name = "Mai"` có thể được caller nhìn thấy; nhưng `parameter = new Customer("Mai")` **không** đổi biến mà caller đã truyền vào. Cả hai đều hoàn toàn phù hợp với cơ chế **pass-by-value**.

Bài học dùng Java 17+, trình bày từ sơ đồ tham chiếu đến code chạy được, cùng các trường hợp String bất biến, mảng/collection, `null`, `final`, generic, varargs, phương thức trả về tham chiếu và thiết kế API tránh tác dụng phụ ngoài ý muốn.

## 1. Phân biệt biến tham chiếu, giá trị tham chiếu và object

Xem khai báo:

~~~java
class Customer {
    String name;

    Customer(String name) {
        this.name = name;
    }
}
~~~

Đây là **đoạn khai báo class**, chưa có `main` chạy độc lập.

Trong một method khác:

~~~java
Customer first = new Customer("Lan");
Customer alias = first;
~~~

Có ba khái niệm cần tách biệt:

1. `first` là **biến** có kiểu khai báo `Customer`.
2. **Giá trị của `first`** là một **tham chiếu** đến một instance `Customer`.
3. Instance được tạo bởi `new Customer("Lan")` là **object**, mang field `name` có giá trị `"Lan"`.

`alias = first` sao chép **giá trị tham chiếu** vào biến `alias`, nên hai biến trỏ cùng một object. Không có object thứ hai được tạo bởi phép gán đó.

~~~text
Biến first  -----+
                 +------> Customer object { name = "Lan" }
Biến alias  -----+
~~~

Các đường nối chỉ thể hiện quan hệ tham chiếu, không phải địa chỉ RAM vật lý. Đặc tả Java không yêu cầu source code được truy cập địa chỉ thô của object.

**Quy tắc cần nhớ trước khi học truyền tham số:** một biến tham chiếu không phải object; nó **chứa giá trị tham chiếu tới object hoặc `null`**. Khi gán biến tham chiếu này cho biến khác, Java sao chép giá trị tham chiếu, chứ không tự clone object.

## 2. Điều gì xảy ra tại lời gọi phương thức?

Xét method:

~~~java
static void inspect(Customer person) {
    System.out.println(person.name);
}
~~~

Và lời gọi:

~~~java
Customer customer = new Customer("Lan");
inspect(customer);
~~~

Khi lời gọi được thực hiện:

1. Java đánh giá biểu thức đối số `customer`, thu được **giá trị tham chiếu** tới object `Customer`.
2. Tham số `person` của method nhận **bản sao của giá trị tham chiếu đó**.
3. Trong suốt lời gọi, `customer` và `person` là **hai biến riêng**, nhưng cùng trỏ tới **một object**.
4. Khi method kết thúc, biến tham số `person` không còn phạm vi sử dụng trong lời gọi đó; biến `customer` của caller vẫn tồn tại và vẫn có giá trị tham chiếu ban đầu, trừ khi chính caller hoặc một cơ chế khác đã thay nó.

~~~text
CALLER                                      CALLEE

customer -------+                          person ------+
                |                                        |
                +------------------+---------------------+
                                   |
                                   v
                       Customer { name = "Lan" }
~~~

**Không có “truyền object by value” ở đây:** object không bị sao chép sâu trong lúc gọi. **Cũng không có “truyền biến customer by reference”:** method không được quyền thay giá trị của biến `customer` chỉ bằng cách gán lại `person`.

Java dùng cơ chế truyền giá trị cho **mọi tham số**. Sự khác nhau giữa primitive và reference là **loại giá trị được sao chép**, không phải Java chuyển từ pass-by-value sang pass-by-reference.

## 3. Hai hành vi phải phân biệt: sửa object và gán lại tham số

### 3.1. Sửa trạng thái của object được chia sẻ

~~~java
static void rename(Customer person) {
    person.name = "Mai";
}
~~~

Giả sử caller có:

~~~java
Customer customer = new Customer("Lan");
rename(customer);
System.out.println(customer.name); // Mai
~~~

Method `rename` nhận bản sao tham chiếu trong `person`. Sau đó `person.name = "Mai"` **truy cập và sửa field của object** mà cả `person` và `customer` cùng trỏ tới. Caller nhìn thấy `"Mai"` vì **object đã thay đổi**, chứ không phải vì biến `customer` được truyền theo tham chiếu.

### 3.2. Gán lại tham số sang object khác

~~~java
static void replace(Customer person) {
    person = new Customer("Hà");
}
~~~

Caller:

~~~java
Customer customer = new Customer("Lan");
replace(customer);
System.out.println(customer.name); // Lan
~~~

Lần này method thực hiện `person = new Customer("Hà")`. Nó tạo một `Customer` mới rồi **gán lại biến tham số cục bộ `person`**. Biến `customer` tại caller không bị gán lại; nó vẫn trỏ tới object `"Lan"` ban đầu.

~~~text
TRƯỚC khi replace gán lại:

customer ------+
               +----> Customer A { name = "Lan" }
person --------+

SAU khi replace gán lại:

customer ------------> Customer A { name = "Lan" }
person --------------> Customer B { name = "Hà" }
~~~

Hai biến chỉ chia sẻ object cho đến lúc `person` nhận giá trị tham chiếu khác. **Không có con trỏ tới “ô biến customer” để phép gán trong method sửa biến của caller**.

### 3.3. Gán tham số thành `null` cũng không xóa biến của caller

~~~java
static void clearParameter(Customer person) {
    person = null;
}
~~~

Sau `clearParameter(customer)`, caller vẫn giữ `customer` trỏ đến object cũ. Việc gán `person = null` chỉ thay giá trị của tham số trong method.

Nếu caller muốn biến `customer` thành null, **caller phải tự gán** `customer = null` hoặc chủ động sử dụng giá trị được trả từ method theo hợp đồng.

## 4. Ví dụ Java 17+ hoàn chỉnh: sửa object, thay tham số, truyền alias

Lưu tệp **`ReferencePassingDemo.java`**:

~~~java
public class ReferencePassingDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static void mutate(Box item) {
        item.value = 20;
    }

    static void reassign(Box item) {
        item = new Box(90);
        item.value = 91;
    }

    static void mutateThenReassign(Box item) {
        item.value = 30;
        item = new Box(70);
        item.value = 80;
    }

    static void clearParameter(Box item) {
        item = null;
    }

    static Box createReplacement(Box old) {
        return new Box(old.value + 100);
    }

    public static void main(String[] args) {
        Box original = new Box(10);
        Box alias = original;

        mutate(original);
        System.out.println("After mutate = " + original.value);

        reassign(original);
        System.out.println("After reassign = " + original.value);

        mutateThenReassign(original);
        System.out.println("After both = " + original.value);

        clearParameter(original);
        System.out.println("Still non-null = " + (original != null));
        System.out.println("Alias same = " + (alias == original));

        Box replacement = createReplacement(original);
        System.out.println("New value = " + replacement.value);
        System.out.println("Old value = " + original.value);
        System.out.println("Same object = " + (replacement == original));

        original = replacement;
        System.out.println("Caller reassigned = " + original.value);
        System.out.println("Alias still old = " + alias.value);
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 ReferencePassingDemo.java
java ReferencePassingDemo
~~~

**Stdout chính xác:**

~~~text
After mutate = 20
After reassign = 20
After both = 30
Still non-null = true
Alias same = true
New value = 130
Old value = 30
Same object = false
Caller reassigned = 130
Alias still old = 30
~~~

Giải thích theo thứ tự:

1. `original` trỏ tới `Box(10)`; `alias = original` tạo **alias tới cùng object**, không clone.
2. `mutate(original)` sao chép giá trị tham chiếu sang `item`. `item.value = 20` sửa object dùng chung, nên caller thấy 20.
3. `reassign(original)` tạo `Box(90)` và gán cho **tham số** `item`. Nó tiếp tục sửa object mới thành 91, nhưng `original` vẫn trỏ tới Box cũ đang có giá trị 20.
4. `mutateThenReassign(original)` sửa object cũ thành 30 **trước** khi gán `item` sang Box mới. Caller thấy 30, chứ không thấy 80; điều này chứng minh hai thao tác có hiệu ứng khác nhau.
5. `clearParameter(original)` chỉ gán `item = null`; `original != null` vẫn true.
6. `alias == original` vẫn true vì cả hai còn trỏ cùng Box cũ.
7. `createReplacement(original)` **trả về tham chiếu** tới một object mới có giá trị `30 + 100 = 130`. `replacement == original` là false.
8. Chính caller thực hiện `original = replacement`, nên từ lúc đó `original` trỏ tới Box mới. `alias` vẫn trỏ Box cũ có giá trị 30.

Một cách ghi nhớ: **thay đổi đối tượng qua tham số có thể quan sát từ caller; gán lại chính tham số không thay đổi biến tham chiếu phía caller**.

## 5. So sánh với truyền tham số primitive

Primitive và reference đều pass-by-value, nhưng giá trị được sao chép khác nhau.

~~~java
static void updateNumber(int value) {
    value = 99;
}

static void updateBox(Box box) {
    box.value = 99;
}
~~~

Với primitive:

~~~java
int number = 10;
updateNumber(number);
// number vẫn bằng 10
~~~

Method nhận **bản sao của số 10** trong tham số `value`. Thay `value` không tác động biến `number` của caller.

Với reference:

~~~java
Box box = new Box(10);
updateBox(box);
// box.value là 99
~~~

Method nhận **bản sao tham chiếu**, trỏ tới cùng Box. Nó không gán lại biến `box`, nhưng thay đổi object `Box` qua tham chiếu.

| Tình huống | Cái được sao chép khi gọi | Caller nhìn thấy gì? |
| --- | --- | --- |
| `change(int n)` rồi `n = 99` | Giá trị `int` | Biến `int` của caller không đổi |
| `change(Box b)` rồi `b = new Box(...)` | Giá trị tham chiếu | Biến `Box` của caller không đổi |
| `change(Box b)` rồi `b.value = 99` | Giá trị tham chiếu | Object chia sẻ có field mới là 99 |
| `change(Box b)` rồi `b = null` | Giá trị tham chiếu | Biến caller vẫn giữ tham chiếu cũ |
| `change(Box b)` rồi `b.update()` | Giá trị tham chiếu | Tùy `update()`, object có thể bị sửa |

**Lưu ý:** không nên nói “Java truyền tham trị chỉ cho primitive, truyền tham chiếu cho object”. Cách nói chính xác là **Java truyền giá trị**, và một **giá trị có thể là tham chiếu**.

## 6. Vì sao gọi method trên đối tượng lại tác động caller?

Một method như:

~~~java
static void addItem(java.util.List<String> items) {
    items.add("Java");
}
~~~

nhận một **tham chiếu đến List object**. Vì `add` là một thao tác trên chính object, caller giữ tham chiếu tới cùng List sẽ thấy phần tử mới, nếu collection mutable và thao tác thành công.

~~~java
java.util.List<String> list = new java.util.ArrayList<>();
addItem(list);
System.out.println(list); // [Java]
~~~

Đây là fragment trong một method. Chia sẻ object là cơ chế bình thường của Java OOP, không phải bằng chứng có “pass-by-reference” theo nghĩa truyền biến của caller.

So sánh cách viết sau:

~~~java
static void replaceList(java.util.List<String> items) {
    items = new java.util.ArrayList<>();
    items.add("Khác");
}
~~~

Gọi `replaceList(list)` không làm `list` bên caller trỏ sang ArrayList mới. Object mới chỉ được gán vào tham số `items`; caller vẫn giữ list cũ.

### 6.1. Tham số tham chiếu là một biến mới

Về mặt trực giác, lời gọi:

~~~java
updateBox(box);
~~~

có thể được hình dung như method nhận một **biến riêng** được khởi tạo bằng giá trị tham chiếu của đối số:

~~~text
Ở caller:     box  -> Box object
Khi gọi:      param = bản sao của giá trị trong box
Trong method: param -> cùng Box object (cho đến khi param được gán lại)
~~~

Tuy nhiên, đây là sơ đồ ý niệm chứ không phải việc người viết Java thật sự khai báo tham số bằng phép gán như trong code. Java xác định chi tiết đánh giá đối số, binding tham số và lời gọi theo đặc tả ngôn ngữ; compiler/JIT có thể tối ưu triển khai mà vẫn giữ đúng ngữ nghĩa quan sát được.

## 7. Mảng: thay phần tử khác gán lại tham số mảng

Mảng trong Java là object. Một tham số `int[] values` là tham số **kiểu tham chiếu**, không phải tham số primitive chỉ vì phần tử là `int`.

~~~java
static void changeElement(int[] values) {
    values[0] = 99;
}

static void replaceArray(int[] values) {
    values = new int[]{7, 8, 9};
}
~~~

Với caller:

~~~java
int[] numbers = {1, 2, 3};

changeElement(numbers);  // numbers[0] thành 99
replaceArray(numbers);   // numbers vẫn trỏ mảng cũ
~~~

Sau đó `numbers` vẫn tham chiếu mảng có nội dung `[99, 2, 3]`.

**Phân biệt rõ:**

- `values[0] = 99` sửa một **phần tử của array object được chia sẻ**.
- `values = new int[]{...}` gán lại **biến tham số `values`**, không thay biến `numbers` ở caller.
- `values = null` cũng chỉ gán lại tham số; mảng của caller không vì thế biến mất.
- Nếu caller và callee cùng giữ tham chiếu tới **mảng của các object mutable**, các object phần tử còn có thể được chia sẻ riêng.

### 7.1. Ví dụ Java hoàn chỉnh về mảng và StringBuilder

Lưu thành **`ArrayAndBuilderDemo.java`**:

~~~java
import java.util.Arrays;

public class ArrayAndBuilderDemo {
    static void changeElements(int[] data) {
        data[0] = 9;
        data[1] = 8;
    }

    static void replaceArray(int[] data) {
        data = new int[]{100, 200};
    }

    static void changeBuilder(StringBuilder builder) {
        builder.append("!");
        builder = new StringBuilder("Other");
        builder.append("?");
    }

    static void replaceString(String text) {
        text = text.toUpperCase();
    }

    public static void main(String[] args) {
        int[] numbers = {1, 2};

        changeElements(numbers);
        replaceArray(numbers);

        System.out.println("Numbers = " + Arrays.toString(numbers));

        StringBuilder text = new StringBuilder("Hi");
        changeBuilder(text);
        System.out.println("Builder = " + text);

        String label = "java";
        replaceString(label);
        System.out.println("String = " + label);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ArrayAndBuilderDemo.java
java ArrayAndBuilderDemo
~~~

**Stdout chính xác:**

~~~text
Numbers = [9, 8]
Builder = Hi!
String = java
~~~

Giải thích:

1. `changeElements(numbers)` sửa phần tử mảng được chia sẻ; mảng của caller đổi thành `[9, 8]`.
2. `replaceArray(numbers)` tạo mảng mới trong callee nhưng chỉ gán lại tham số. `numbers` của caller vẫn là mảng `[9, 8]`.
3. `changeBuilder(text)` gọi `append("!")` trên cùng StringBuilder object, nên caller thấy `Hi!`. Sau đó gán tham số `builder` sang StringBuilder mới và sửa object mới, không làm object của caller thành `Other?`.
4. `replaceString(label)` gán tham số `text` sang String khác có nội dung `JAVA`; biến `label` của caller vẫn là tham chiếu `"java"`.

Ví dụ nhấn mạnh **ba yếu tố khác nhau**: loại object, khả năng thay đổi (*mutability*) và việc gán lại biến tham số.

## 8. String: tham chiếu được sao chép, nhưng nội dung object bất biến

`String` là **reference type**, không phải primitive. Một `String` object **immutable**: không có cách thông thường để đổi nội dung của chính instance String sau khi tạo.

~~~java
static void changeName(String name) {
    name = name.toUpperCase();
}
~~~

Nếu caller:

~~~java
String name = "Lan";
changeName(name);
System.out.println(name); // Lan
~~~

thì `name` của caller vẫn là `"Lan"`. Phương thức `toUpperCase()` trả một kết quả String; phép gán trong callee chỉ thay **tham số `name`**.

Điều này thường gây nhầm: “Truyền String sao mà giống primitive?”. Lý do **không phải** Java dùng cơ chế truyền khác cho String. Java vẫn **sao chép giá trị tham chiếu** như với mọi object; chỉ là **String không cho sửa nội dung object dùng chung**.

So với `StringBuilder` mutable:

~~~java
static void appendSuffix(StringBuilder builder) {
    builder.append("!");
}
~~~

Khi caller có `new StringBuilder("Lan")` và truyền vào `appendSuffix`, caller nhìn thấy `Lan!` vì method sửa object.

| Kiểu tham số | Có thể sửa object qua tham số? | Việc gán lại tham số đổi biến caller? |
| --- | --- | --- |
| `String` | Không sửa nội dung String object bằng API thường | Không |
| `StringBuilder` | Có, ví dụ `append` | Không |
| `int[]` | Có, ví dụ sửa phần tử | Không |
| `List<String>` mutable | Có, ví dụ `add` | Không |
| Immutable record với component immutable | Không sửa trạng thái qua accessor thông thường | Không |

**Đừng dùng `==` để so sánh nội dung String** chỉ vì cả hai biến có thể cùng tham chiếu một String literal. `==` trên reference so sánh identity; muốn so nội dung hãy dùng `equals` với xử lý null phù hợp.

## 9. Truyền `null` cũng chỉ là sao chép giá trị tham chiếu

`null` là một giá trị hợp lệ cho các tham số kiểu tham chiếu theo quy tắc ngôn ngữ:

~~~java
static void inspect(String text) {
    if (text == null) {
        System.out.println("Missing");
        return;
    }
    System.out.println(text.length());
}
~~~

Lời gọi `inspect(null)` chuyển giá trị null vào tham số `text`. **Không có object nào được tạo hoặc sao chép**.

Nếu code cố dereference null:

~~~java
static void wrong(StringBuilder builder) {
    builder.append("!"); // NPE nếu builder == null
}
~~~

thì method ném `NullPointerException`. Đây là vấn đề **receiver null** khi gọi instance method, không phải sự khác biệt của Java pass-by-value.

### 9.1. Method không thể “làm hết null” cho caller bằng cách gán tham số

~~~java
static void initialize(StringBuilder buffer) {
    if (buffer == null) {
        buffer = new StringBuilder("ready");
    }
}
~~~

Caller:

~~~java
StringBuilder result = null;
initialize(result);
System.out.println(result == null); // true
~~~

Vì `buffer` là tham số riêng, việc gán object mới chỉ làm callee có một tham chiếu mới. Caller vẫn có `result == null`.

**Cách đúng khi muốn caller có object mới:** trả tham chiếu rồi để caller gán:

~~~java
static StringBuilder ensureBuffer(StringBuilder buffer) {
    return buffer == null
            ? new StringBuilder("ready")
            : buffer;
}

// Trong caller:
StringBuilder result = null;
result = ensureBuffer(result);
~~~

Sau đó `result` có thể trỏ tới StringBuilder non-null; **chính câu lệnh gán ở caller** đã thay giá trị của biến caller.

## 10. Muốn thay tham chiếu của caller thì có những cách nào?

Vì tham số không phải alias của **biến** phía caller, một method không thể đơn giản thực hiện `parameter = new Object()` rồi khiến biến được truyền từ caller đổi theo. Hãy dùng một hợp đồng chủ động.

### 10.1. Trả về object mới và gán tại caller

~~~java
class Address {
    String city;

    Address(String city) {
        this.city = city;
    }
}

class AddressOps {
    static Address movedTo(Address old, String city) {
        return new Address(city);
    }
}
~~~

Caller:

~~~java
Address address = new Address("Huế");
address = AddressOps.movedTo(address, "Hà Nội");
~~~

`movedTo` nhận một bản sao của tham chiếu `old`; kết quả là tham chiếu đến **một Address khác**. Biến `address` được gán lại ở **caller**.

Trong một API thật, tham số `old` ở ví dụ không được sử dụng, nên có thể bỏ đi hoặc thiết kế method copy các dữ liệu còn lại của địa chỉ cũ để tránh một parameter thừa. Đây là ví dụ tối giản để nhấn mạnh cách trả về và nhận tham chiếu.

### 10.2. Sửa field tham chiếu bên trong một holder object

~~~java
class Holder<T> {
    T value;

    Holder(T value) {
        this.value = value;
    }
}

class HolderOps {
    static void replace(Holder<StringBuilder> holder) {
        holder.value = new StringBuilder("new");
    }
}
~~~

Nếu caller có `Holder<StringBuilder> holder`, sau `HolderOps.replace(holder)`, field `holder.value` có thể đổi. Vì cả caller và callee cùng tham chiếu tới **Holder object**, method sửa **state của Holder**, không gán lại biến `holder` của caller.

Cơ chế này hữu ích ở một số API có output holder, nhưng có thể làm thiết kế phức tạp, tạo shared mutable state và yêu cầu concurrency control. Nếu chỉ cần một kết quả mới, **return value thường rõ ràng hơn**.

### 10.3. Thay phần tử mảng hoặc collection do caller nắm giữ

~~~java
static void replaceFirst(StringBuilder[] slots) {
    slots[0] = new StringBuilder("new");
}
~~~

Method này thay **phần tử của array object được chia sẻ**. Caller đọc `slots[0]` thấy object mới, nhưng biến `slots` của caller vẫn giữ giá trị tham chiếu tới cùng mảng. Đây cũng **không phải** pass-by-reference của biến caller.

## 11. `final` trên tham số không đổi cơ chế truyền

Bạn có thể khai báo tham số là `final`:

~~~java
static void update(final Customer person) {
    person.name = "Mai"; // Có thể hợp lệ: sửa object mutable
    // person = new Customer("An"); // Lỗi compile: gán lại final parameter
}
~~~

Modifier `final` ở đây **không làm object immutable**. Nó chỉ **ngăn biến tham số `person` bị gán lại** trong method. Method vẫn nhận bản sao giá trị tham chiếu như bình thường.

Một số trường hợp:

- `final int n`: không gán lại tham số số `n`.
- `final String text`: không gán lại tham số tham chiếu `text`.
- `final List<String> values`: không gán lại `values`, nhưng vẫn có thể gọi `values.add(...)` nếu list mutable và hợp đồng cho phép.
- `final Customer customer`: không thay reference trong tham số, nhưng có thể sửa field mutable trên object.

**Khác biệt quan trọng:** `final` giới hạn phép gán lại **biến**, không thay đổi Java pass-by-value, không clone object và không phải biện pháp concurrency/thread-safety.

### 11.1. Không nhầm với `final` field

~~~java
class Registry {
    private final java.util.List<String> values;

    Registry(java.util.List<String> values) {
        this.values = values;
    }
}
~~~

Field `values` là final, nhưng vì constructor **giữ tham chiếu tới List object** do caller cung cấp, caller có thể tiếp tục sửa chính list đó nếu mutable. Muốn ngăn aliasing, cần snapshot/defensive copy khi hợp đồng yêu cầu.

## 12. Tránh làm lộ mutable state: defensive copying

Biết Java truyền bản sao tham chiếu giúp giải thích vì sao constructor như sau có thể nguy hiểm:

~~~java
import java.util.List;

class UnsafeTeam {
    private final List<String> members;

    UnsafeTeam(List<String> members) {
        this.members = members;
    }

    List<String> members() {
        return members;
    }
}
~~~

Caller và object `UnsafeTeam` cùng giữ tham chiếu tới **một List mutable**. Gọi `externalList.clear()` có thể xóa thành viên của team sau khi constructor hoàn tất; gọi `team.members().add(...)` cũng sửa state nội bộ mà không qua method kiểm soát.

### 12.1. Bảo vệ bằng snapshot phù hợp

~~~java
import java.util.List;

class Team {
    private final List<String> members;

    Team(List<String> source) {
        if (source == null || source.isEmpty()) {
            throw new IllegalArgumentException("Danh sách trống");
        }

        List<String> snapshot = List.copyOf(source);
        for (String member : snapshot) {
            if (member.isBlank()) {
                throw new IllegalArgumentException("Tên thành viên trống");
            }
        }

        this.members = snapshot;
    }

    List<String> members() {
        return members;
    }
}
~~~

`List.copyOf` tạo một danh sách không sửa được qua API và không chấp nhận phần tử null. Với các thành viên kiểu `String` immutable, snapshot cấu trúc đủ để ngăn caller thay đổi nội dung team qua List của mình.

**Không nhầm shallow copy với deep copy.** Nếu list chứa `MutableMember`, `List.copyOf` vẫn giữ các tham chiếu tới cùng các phần tử MutableMember; caller có thể sửa phần tử nếu giữ tham chiếu. Tùy invariant, cần sao chép/đóng băng từng object con hoặc thiết kế ownership rõ ràng.

### 12.2. Với mảng primitive

~~~java
class Scores {
    private final int[] values;

    Scores(int[] source) {
        this.values = source.clone();
    }

    int[] values() {
        return values.clone();
    }
}
~~~

Constructor này cần thêm validation `source != null` trong API thực tế (nếu source null, `clone()` ném NPE). Với mảng `int[]`, `clone()` tạo một mảng riêng và sao chép giá trị nguyên thủy từng phần tử; do đó caller sửa mảng gốc không sửa mảng nội bộ, và sửa kết quả getter cũng không tác động mảng nội bộ.

**Không có clone tự động ở ranh giới method:** chính code `source.clone()` mới tạo copy. Chỉ truyền `source` qua constructor không hề clone mảng.

## 13. Phương thức generic vẫn pass-by-value

Một generic method dùng type parameter tham chiếu:

~~~java
class GenericOps {
    static <T> T identity(T item) {
        return item;
    }
}
~~~

Ví dụ `Customer returned = GenericOps.identity(customer)`: tham số `item` nhận bản sao tham chiếu, rồi method **trả lại cùng giá trị tham chiếu**. Không có object `Customer` mới được tạo ra.

Nếu `item == null`, method cũng có thể trả null theo khai báo `T` trong ngữ cảnh tương ứng. Generic method không tạo ra một cơ chế truyền tham số khác và cũng không tự bảo đảm non-null.

### 13.1. Java không hỗ trợ truyền tham số theo tham chiếu kiểu C++ `T&`

Một số ngôn ngữ cho phép một function nhận **alias đến chính biến của caller** và gán lại biến ấy. Java không có cú pháp parameter tương đương để method được quyền gán trực tiếp lại biến local của caller qua lời gọi.

Khi thấy `Customer parameter` trong method Java, hãy hiểu nó là một **biến tham số riêng** mang tham chiếu đã được sao chép, không phải “tham chiếu đến ô biến Customer của người gọi”.

## 14. Varargs vẫn nhận một giá trị tham chiếu mảng

Một method:

~~~java
static int count(String... names) {
    return names.length;
}
~~~

sử dụng tham số varargs. Trong body, `names` có kiểu mảng `String[]`, nghĩa là một **tham số tham chiếu** theo quy tắc Java.

Khi caller gọi `count("Lan", "Mai")`, compiler/runtime xử lý argument list theo cơ chế invocation và mảng varargs phù hợp. Nếu caller truyền trực tiếp một mảng `String[]` theo lời gọi có arity thích hợp, method có thể nhận tham chiếu tới mảng đó. Dù trường hợp nào, **biến tham số `names` vẫn là một biến riêng**, được gán giá trị tham chiếu theo cơ chế pass-by-value.

Ví dụ sửa phần tử:

~~~java
static void changeFirst(String... names) {
    names[0] = "New";
}
~~~

Nếu caller làm:

~~~java
String[] a = {"Old"};
changeFirst(a);
System.out.println(a[0]); // New
~~~

thì `changeFirst` sửa **phần tử trong cùng mảng** `a`. Nếu caller gọi `changeFirst("Old")`, mảng do lời gọi varargs tạo ra không được caller nắm giữ qua một biến mảng tương ứng; side effect vào mảng tạm đó không có nghĩa caller có biến String bị gán lại.

**Lưu ý:** `changeFirst` giả định mảng khác null và có ít nhất một phần tử. Trong code thực tế phải kiểm tra các tiền điều kiện nếu caller được phép truyền mảng rỗng hoặc null.

## 15. Tham chiếu dùng chung và aliasing

Nếu caller có nhiều biến tham chiếu cùng object:

~~~java
Box first = new Box(5);
Box second = first;
~~~

thì sau `mutate(first)`, caller có thể quan sát thay đổi qua `second.value` vì **hai biến cùng trỏ tới một object**. Điều này không liên quan đến việc tên biến có giống hay khác tên tham số.

Mô hình:

~~~text
first  -------+
              +--------> Box { value = 20 }
second -------+
param  -------+  (trong lúc mutate đang chạy)
~~~

Lưu ý phân biệt **tham chiếu được chia sẻ** và **object có thể thay đổi**:

- Nếu cùng tham chiếu một `String` immutable, caller và callee không sửa nội dung String.
- Nếu cùng tham chiếu một `StringBuilder` mutable, sửa qua một bên có thể được bên kia nhìn thấy.
- Nếu cùng tham chiếu một mảng `int[]`, thay phần tử có thể được bên kia nhìn thấy.
- Nếu cùng tham chiếu immutable record chứa chỉ các component immutable, code thường chỉ quan sát state, không sửa object.
- Nếu record có component là mutable reference, record final không tự làm object con immutable.

**Bản sao tham chiếu không phải bản sao state của object.** Nếu cần những thay đổi của callee không ảnh hưởng caller, phải dựa vào immutable data, copy phù hợp hoặc hợp đồng quyền sở hữu.

## 16. Method có thể thay đổi object rồi trả về chính object đó

~~~java
class Counter {
    private int value;

    Counter add(int n) {
        this.value += n;
        return this;
    }

    int value() {
        return value;
    }
}
~~~

Nếu caller thực hiện:

~~~java
Counter counter = new Counter();
Counter returned = counter.add(3);
System.out.println(returned == counter); // true
~~~

`return this` trả **giá trị tham chiếu tới current object**. `returned == counter` là true vì chúng cùng chỉ đến một instance.

Trong ví dụ này có hai lần sao chép giá trị tham chiếu đáng chú ý:

1. Tại lời gọi `counter.add(3)`, receiver là current object; `3` được sao chép vào tham số primitive `n`.
2. Tại câu lệnh `return this`, kết quả là giá trị tham chiếu được chuyển cho caller và gán vào biến `returned`.

Method chaining như `counter.add(1).add(2)` dựa trên `return this` để tiếp tục gọi trên cùng object. Nó không chứng minh rằng Java có pass-by-reference của biến caller.

## 17. Không nhầm tham chiếu được sao chép với object copy

Có nhiều mức “copy” khác nhau:

| Tác vụ | Điều được sao chép |
| --- | --- |
| `Customer b = a;` | Giá trị tham chiếu |
| Truyền `a` vào `modify(Customer c)` | Giá trị tham chiếu vào parameter `c` |
| `return a;` | Giá trị tham chiếu được trả |
| `new Customer(a.name)` | Tạo object Customer mới, sao chép/chuyển những dữ liệu constructor xử lý |
| `int[] b = a.clone();` | Mảng mới; các phần tử `int` được sao chép |
| `Address[] b = a.clone();` | Mảng mới; các phần tử là các tham chiếu sao chép nông |
| `List.copyOf(mutableList)` | List không sửa được chứa tham chiếu phần tử, không deep-copy object con |
| Deep copy theo cấu trúc | Mỗi object mutable cần được copy theo hợp đồng thiết kế |

Khi người khác nói “Java copy object khi truyền parameter”, hãy hỏi **object nào được tạo ra? Lệnh `new`, `clone` hoặc factory copy nằm ở đâu?** Nếu method chỉ nhận `Customer c` và caller chỉ truyền `customer`, chưa có bước copy object nào từ cú pháp truyền tham số.

### 17.1. Cơ chế truyền tham số không quy định layout bộ nhớ

Một số tài liệu dùng câu “Java truyền địa chỉ bộ nhớ” như một cách ví von, nhưng lời giải thích chính xác hơn là **sao chép giá trị tham chiếu**. Java không cho code bình thường đọc/gán một địa chỉ bộ nhớ thô, và JVM có thể triển khai/ tối ưu tham chiếu theo nhiều cách miễn bảo đảm ngữ nghĩa của Java Language Specification.

Cũng đừng suy ra mọi primitive bắt buộc ở stack và mọi reference bắt buộc ở heap từ cú pháp truyền tham số. Cách JVM/JIT bố trí hoặc loại bỏ allocation là chi tiết triển khai, không thay đổi kết quả logic của các ví dụ.

## 18. Tác động khi có nhiều thread

Pass-by-value **không** đồng nghĩa thread-safe. Hai thread có thể nhận **hai bản sao giá trị tham chiếu tới cùng một mutable object**. Nếu chúng đồng thời sửa object, có thể xảy ra data race.

~~~java
class UnsafeCounter {
    private int value;

    void increment() {
        value++;
    }
}
~~~

Nếu hai thread nhận cùng `UnsafeCounter` object rồi gọi `increment()`, cả hai thao tác `value++` có thể tranh chấp, gây lost update. Dù mỗi thread có biến parameter riêng, **object chung** vẫn cần một chiến lược đồng bộ.

Ví dụ bảo vệ bằng monitor:

~~~java
class SynchronizedCounter {
    private int value;

    synchronized void increment() {
        value++;
    }

    synchronized int current() {
        return value;
    }
}
~~~

Các thao tác trên cùng `SynchronizedCounter` object được đồng bộ qua monitor của instance, miễn mọi truy cập liên quan tuân thủ quy tắc đó. **Việc chỉ khai báo `final Box parameter` hoặc sao chép tham chiếu không tạo synchronization.**

Đối với method chuyển một object mới cho caller bằng cách trả kết quả, nếu caller/chương trình sử dụng object ở thread khác, việc **safe publication** và tính mutable của object được trả cũng phải được xét; cơ chế argument passing không tự giải quyết toàn bộ Java Memory Model.

## 19. Thiết kế API: có cho method sửa object truyền vào không?

Một số API **chủ đích sửa mutable input**:

~~~java
static void sortValues(int[] values) {
    java.util.Arrays.sort(values);
}
~~~

Caller muốn mảng của họ được sắp xếp tại chỗ, và hiệu ứng đó nên được ghi rõ.

API khác mong muốn **không sửa dữ liệu caller**:

~~~java
static int[] sortedCopy(int[] values) {
    int[] copy = values.clone();
    java.util.Arrays.sort(copy);
    return copy;
}
~~~

Cách thứ hai tạo array mới, sắp xếp trên copy, rồi trả tham chiếu tới copy. Caller có thể chọn gán kết quả vào biến mới hoặc biến hiện tại.

Ví dụ:

~~~java
int[] numbers = {3, 1, 2};
int[] sorted = sortedCopy(numbers);
// numbers vẫn [3, 1, 2], sorted là [1, 2, 3]
~~~

Phần này là fragment method; `values == null` sẽ làm `clone()` lỗi NPE. API thực tế nên quyết định có từ chối null hay dùng mặc định, rồi tài liệu hóa.

**Những điều cần nêu rõ trong hợp đồng method nhận reference:**

- Parameter có cho phép `null` không?
- Method có được phép thay đổi state của object được truyền vào không?
- Nếu tạo object mới, method trả tham chiếu mới hay cập nhật field trong một holder?
- Caller hay callee chịu trách nhiệm đóng resource/lifecycle?
- Có giữ lại tham chiếu để dùng sau khi method kết thúc không?
- Cấu trúc dữ liệu có được copy nông, copy sâu hoặc dùng làm read-only view không?
- Method có an toàn với concurrent callers cùng dùng một object không?

Không nên “sửa object mà caller không biết” trong một method đặt tên `get...` hoặc `calculate...` nếu caller có lý do kỳ vọng đó là query không mutate. Chọn tên `sortInPlace`, `updateCustomer` hoặc `appendTo` khi side effect là hợp đồng chính.

## 20. Những nhầm lẫn phổ biến

1. **“Java truyền object theo tham chiếu như C++ reference parameter.”** Không chính xác. Java truyền **giá trị tham chiếu theo giá trị**; method có biến parameter riêng, không gán lại được biến caller.
2. **“Method sửa được field của object, vậy chắc là pass-by-reference.”** Không. Caller và callee trỏ cùng object; method sửa object được chia sẻ.
3. **“`param = new Box(...)` sẽ thay object mà caller trỏ tới.”** Sai. Nó chỉ đổi biến `param` trong callee.
4. **“`param = null` làm caller mất object.”** Sai. Biến caller không đổi và các alias khác vẫn giữ object.
5. **“`String` được truyền theo một cơ chế riêng.”** Sai. String là reference; nó có hành vi quan sát khác do **immutable**.
6. **“`int[]` là primitive parameter vì phần tử là int.”** Sai. Mảng là object; tham số mảng là reference type.
7. **“Gọi `items.add(x)` giống gán `items = new List(...)`.”** Sai. Một bên sửa List object; bên kia thay giá trị biến parameter.
8. **“`final Customer c` khiến Customer không thay đổi.”** Sai. Final hạn chế gán lại **c**, không làm object bất biến.
9. **“Trả lại object mới từ method tự cập nhật biến caller.”** Không. Caller cần nhận và gán giá trị trả về nếu muốn thay biến của mình.
10. **“Truyền object vào method tự clone object.”** Sai. Nếu cần copy, phải có logic copy cụ thể.
11. **“Sao chép List bằng `List.copyOf` là deep copy.”** Sai nếu phần tử mutable; tham chiếu phần tử vẫn có thể được chia sẻ.
12. **“Một biến tham chiếu null được truyền vào method sẽ tự tạo object khi cần.”** Sai. Null cũng được sao chép; callee phải xử lý hoặc từ chối nó.
13. **“Chỉ cần copy giá trị tham chiếu là tránh race giữa thread.”** Sai. Hai reference có thể vẫn trỏ chung mutable object.
14. **“Tên biến của caller và parameter giống nhau nghĩa là một biến duy nhất.”** Sai. Cùng tên trong các scope khác nhau không đồng nghĩa cùng variable.
15. **“`return this` chứng minh caller đã truyền theo tham chiếu.”** Sai. Nó là thao tác trả một giá trị tham chiếu từ method.
16. **“Mọi thay đổi bên trong callee đều visible với caller.”** Sai. Chỉ thay đổi lên trạng thái dùng chung mới có thể quan sát; các phép gán local/parameter không tự xuất hiện ở caller.

## 21. Bài tập tự kiểm tra có đáp án

**Câu 1.** Nếu `Box b = new Box(10);` và `void f(Box x) { x.value = 20; }`, sau `f(b)` thì `b.value` bằng bao nhiêu?

**Đáp án:** `20`. Cả `b` và `x` trỏ cùng Box object; callee sửa field trên object chung.

**Câu 2.** Nếu `void f(Box x) { x = new Box(20); }`, sau `f(b)` thì biến `b` có trỏ sang object mới không?

**Đáp án:** Không. Callee chỉ gán lại parameter `x`; biến `b` vẫn trỏ tới Box cũ.

**Câu 3.** Một method nhận `String s` rồi gán `s = s.toUpperCase()`. Caller có thấy biến String của mình đổi không?

**Đáp án:** Không. Tham số nhận bản sao tham chiếu; String immutable; gán lại `s` chỉ sửa biến của callee.

**Câu 4.** `StringBuilder builder` được truyền vào method gọi `builder.append("!")`. Caller có thể thấy dấu `!` không?

**Đáp án:** Có, nếu builder khác null và có cùng object được chia sẻ. `append` sửa state của StringBuilder.

**Câu 5.** `int[] values` là primitive parameter hay reference parameter?

**Đáp án:** Reference parameter, vì mảng là object trong Java. Các phần tử của mảng mới có kiểu primitive `int`.

**Câu 6.** Gọi `void reset(StringBuilder b) { b = null; }` có làm biến caller thành null không?

**Đáp án:** Không. `b` là một parameter riêng và chỉ nó được gán null.

**Câu 7.** Khi cần caller nhận object mới, cách nào đơn giản hơn: gán tham số trong method hay trả object rồi gán ở caller?

**Đáp án:** Trả object mới bằng `return` và để caller viết `variable = method(variable);` thường rõ ràng hơn.

**Câu 8.** Nếu một tham số khai báo `final List<String> list`, callee có thể gọi `list.add("A")` không?

**Đáp án:** Có thể, nếu List object mutable và điều kiện khác cho phép. `final` chỉ ngăn gán lại biến tham số `list`.

**Câu 9.** Một constructor giữ `this.values = externalList`; caller sửa externalList sau đó có thể làm state bên trong object đổi không?

**Đáp án:** Có, vì constructor chỉ giữ bản sao tham chiếu tới cùng List object. Có thể defensive copy nếu cần snapshot độc lập.

**Câu 10.** Hai thread nhận hai tham số tham chiếu cùng một `Counter` object có tự động được cô lập state không?

**Đáp án:** Không. Parameter variables là riêng, nhưng **object referent** vẫn chung; cần đồng bộ thích hợp khi cùng sửa mutable state.

**Câu 11.** Truyền `null` cho một method nhận `Customer` có làm object Customer nào được sao chép không?

**Đáp án:** Không. Giá trị null được chuyển vào parameter; không có object đích để sao chép hoặc thao tác.

**Câu 12.** `int[] a = {1}; mutate(a);`, trong `mutate` method gán `a[0] = 5` rồi `a = new int[]{9}`. Caller thấy `a[0]` bằng bao nhiêu?

**Đáp án:** `5`. Phép gán phần tử đầu tiên sửa mảng chung; phép gán `a` sang mảng mới chỉ sửa biến parameter của callee.

**Câu 13.** `Holder<Customer> h` được truyền vào method, và method gán `h.value = new Customer("A")`. Biến `h` caller có thay đổi tham chiếu không?

**Đáp án:** Không; `h` vẫn trỏ cùng Holder. Nhưng **field `value` của Holder object** đã đổi, nên caller quan sát được Customer mới qua `h.value`.

**Câu 14.** Vì sao `return item;` trong generic method `<T> T identity(T item)` không tạo copy object?

**Đáp án:** Method trả **giá trị tham chiếu** đang nằm trong tham số; không có `new` hoặc thao tác copy object trong method.

## 22. Checklist khi đọc hoặc thiết kế lời gọi phương thức

1. **Phân loại đối số:** primitive hay reference? Với reference, giá trị được sao chép là tham chiếu.
2. **Xác định object thật:** biến nào đang trỏ tới object nào? Có nhiều alias không?
3. **Đọc chính xác thao tác trong method:** `param = ...` là gán lại parameter; `param.field = ...` là sửa object.
4. **Nếu truyền array/collection:** method sửa phần tử/cấu trúc hay gán parameter sang object mới?
5. **Nếu tham số là String/immutable type:** object có thể thay đổi không, hay method chỉ tạo kết quả mới?
6. **Nếu parameter có `final`:** nhớ rằng nó ngăn gán lại biến, không làm object immutable.
7. **Nếu muốn thay biến caller:** cần return + caller assignment, hoặc chủ động dùng holder với hợp đồng rõ.
8. **Nếu muốn bảo vệ mutable input:** copy phù hợp ngay ranh giới và xem xét cả object con.
9. **Nếu có `null`:** method xử lý, validate hay dereference null theo hợp đồng?
10. **Nếu có nhiều thread:** nhiều bản sao tham chiếu vẫn có thể cùng chỉ tới mutable object; xem synchronization.
11. **Nếu API có side effect:** đặt tên và tài liệu hóa rõ khả năng sửa object tham số.
12. **Khi đọc kết quả:** luôn đối chiếu trạng thái biến ở caller với trạng thái object được tham chiếu, vì đó là hai thứ khác nhau.

**Kết luận:** Trong Java, lời gọi method **sao chép giá trị tham chiếu vào một tham số mới**, không sao chép object và không truyền “ô biến” của caller. Vì cả hai tham chiếu có thể cùng trỏ tới **một object**, method được phép sửa state của object theo API, nhưng **không thể gán lại biến caller bằng cách gán parameter**. Phân biệt rạch ròi **biến**, **giá trị tham chiếu** và **object được tham chiếu** là chìa khóa để hiểu đúng Java pass-by-value, aliasing, mutable state và cách thiết kế phương thức an toàn.
