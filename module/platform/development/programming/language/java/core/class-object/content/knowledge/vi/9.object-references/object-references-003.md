# Nhiều biến cùng tham chiếu một đối tượng trong Java

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích chính xác **biến tham chiếu** (*reference variable*), **đối tượng** (*object*) và **tham chiếu chung/aliasing** trong Java.
- Phân biệt nhiều biến cùng giữ **một giá trị tham chiếu** với nhiều đối tượng độc lập có **nội dung giống nhau**.
- Dự đoán tác dụng của **sửa trạng thái đối tượng** qua một biến, **gán lại biến tham chiếu**, đặt biến thành `null`, hoặc truyền tham chiếu vào phương thức.
- Dùng toán tử `==` và `equals()` đúng mục đích: so sánh **identity** hay **giá trị logic**.
- Hiểu `final`, `String` bất biến, mảng, collection, shallow copy và deep copy trong ngữ cảnh aliasing.
- Tránh rò rỉ trạng thái mutable qua constructor, getter, collection hoặc các tham chiếu được chia sẻ.
- Nhận biết liên hệ với garbage collection, khả năng truy cập (*reachability*) và thread safety.
- Biên dịch/chạy các chương trình Java 17+ và giải thích được stdout mà không dựa vào giả định sai về “truyền object theo tham chiếu”.

## 1. Aliasing là vấn đề chia sẻ trạng thái quan sát được

Có **aliasing** khi hai hoặc nhiều đường tham chiếu dẫn tới **cùng một mutable object**. Bài này tập trung vào hậu quả: một nơi có thể thay đổi state mà những nơi khác cùng nhìn thấy, kể cả khi references nằm trong field, mảng hay collection.

~~~java
Box a = new Box(10);
Box b = a;
Box independent = new Box(10);
b.value = 20;
~~~

Đây là snippet cần Box với constructor nhận int và field value truy cập được. Sau mutation, `a.value` là 20, `independent.value` là 10. `a == b` true, còn `a == independent` false. Phép gán reference **không** tự sao chép object.

Khi phát hiện “sửa một nơi, nơi khác cũng đổi”, hãy làm theo thứ tự:

1. Liệt kê tất cả đường references tới shared mutable object.
2. Phân biệt mutation của object với reassignment của biến.
3. Kiểm tra nested references: hai outer objects có thể riêng nhưng dùng chung List hoặc child object.
4. Nếu cần cách ly, cân nhắc defensive copy, immutable elements, read-only API hoặc ownership policy.
5. Nếu có nhiều threads, cần synchronization/transaction đúng yêu cầu; aliasing không làm code tự an toàn đồng thời.

Các ví dụ tiếp theo thực hành sâu từng trường hợp; đây không chỉ là bài đếm số lần `new`.

## 2. Ví dụ độc lập: tạo alias, sửa object và gán lại biến

Lưu tệp **`ReferenceAliasingDemo.java`**:

~~~java
public class ReferenceAliasingDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        Box first = new Box(10);
        Box alias = first;
        Box separate = new Box(10);

        System.out.println("first == alias: " + (first == alias));
        System.out.println("first == separate: " + (first == separate));

        alias.value = 25;
        System.out.println("after mutation: first=" + first.value
                + ", alias=" + alias.value
                + ", separate=" + separate.value);

        alias = new Box(99);
        System.out.println("after reassignment: first=" + first.value
                + ", alias=" + alias.value);

        alias = null;
        System.out.println("alias is null: " + (alias == null));
        System.out.println("first still=" + first.value);
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên trong thư mục chứa tệp:

~~~bash
javac ReferenceAliasingDemo.java
java ReferenceAliasingDemo
~~~

**Stdout chính xác:**

~~~text
first == alias: true
first == separate: false
after mutation: first=25, alias=25, separate=10
after reassignment: first=25, alias=99
alias is null: true
first still=25
~~~

Giải thích từng giai đoạn:

1. `first` và `alias` cùng tham chiếu Box A, nên `first == alias` là `true`.
2. `separate` trỏ Box B mới tạo, nên `first == separate` là `false` dù hai Box lúc đầu có giá trị field như nhau.
3. `alias.value = 25` thực hiện **field assignment trên Box A**. Đọc `first.value` hay `alias.value` đều thấy `25`.
4. `alias = new Box(99)` là **gán lại chính biến alias** sang Box C. Nó **không** thay Box A và không tự động thay biến `first`; `first.value` vẫn `25`.
5. `alias = null` chỉ thay giá trị biến `alias`, không xóa Box A, không đổi `first` và không phá hủy Box C tức thì. Box A còn được tham chiếu bởi `first`.

**Kết luận:** Phải phân biệt hai loại thao tác:

| Thao tác | Điều thay đổi | Alias khác có thấy thay đổi không? |
| --- | --- | --- |
| `alias.value = 25` | Trạng thái của object mà `alias` đang tham chiếu | **Có**, nếu alias khác tham chiếu cùng object |
| `alias = new Box(99)` | Giá trị tham chiếu lưu trong **biến `alias`** | **Không**, biến alias khác không tự chuyển theo |
| `alias = first` | Biến `alias` trỏ sang object của `first` | Hai biến lại cùng object, nhưng không có object mới |
| `alias = null` | Biến `alias` không tham chiếu object nào | Không ảnh hưởng các biến khác đang giữ reference |
| `first.value` | Đọc field thông qua tham chiếu | Không thay đổi trạng thái |

## 3. `==` so sánh identity, `equals()` so sánh theo hợp đồng của lớp

### 3.1. `==` giữa hai tham chiếu

Với hai biến kiểu tham chiếu tương thích, `a == b` kiểm tra chúng có cùng **giá trị tham chiếu** hay không: cùng object, hoặc cả hai cùng `null`.

~~~java
Object a = new Object();
Object alias = a;
Object other = new Object();

System.out.println(a == alias); // true
System.out.println(a == other); // false
~~~

Đây là đoạn đặt trong một method. Hai lần `new Object()` tạo hai object riêng; cùng lớp không có nghĩa cùng identity.

`==` **không** tự so sánh toàn bộ field, chuỗi ký tự hay phần tử collection. Nếu cần so sánh trạng thái logic, xem `equals()` theo hợp đồng của kiểu.

### 3.2. `equals()` không mặc định có nghĩa “mọi field giống nhau”

Lớp `Object` khai báo `equals()` với hành vi mặc định dựa trên identity. Nếu một lớp **không override `equals()`**, hai instance khác nhau thường `equals` nhau là `false` ngay cả khi field chứa nội dung giống hệt.

Các lớp như `String`, wrapper numbers, các value objects thích hợp thường **override** `equals` để so sánh theo giá trị hoặc hợp đồng tương ứng.

Ví dụ độc lập **`IdentityVsEqualityDemo.java`**:

~~~java
import java.util.Objects;

public class IdentityVsEqualityDemo {
    static final class Person {
        private final String id;

        Person(String id) {
            this.id = Objects.requireNonNull(id);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof Person person)) {
                return false;
            }
            return id.equals(person.id);
        }

        @Override
        public int hashCode() {
            return id.hashCode();
        }
    }

    public static void main(String[] args) {
        Person first = new Person("P01");
        Person alias = first;
        Person other = new Person("P01");

        System.out.println("alias identity=" + (first == alias));
        System.out.println("other identity=" + (first == other));
        System.out.println("other equality=" + first.equals(other));

        String x = new String("java");
        String y = new String("java");
        System.out.println("string identity=" + (x == y));
        System.out.println("string equality=" + x.equals(y));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac IdentityVsEqualityDemo.java
java IdentityVsEqualityDemo
~~~

Output:

~~~text
alias identity=true
other identity=false
other equality=true
string identity=false
string equality=true
~~~

Ở `Person`, `equals` được override theo field `id`, nên hai Person **khác identity** vẫn có **giá trị logic bằng nhau**. Vì đã override `equals`, ví dụ cũng override `hashCode` nhất quán, cần thiết khi dùng với `HashSet`, `HashMap`.

`new String("java")` tạo object `String` mới ở từng biểu thức, vì vậy hai object riêng có `== false`, còn `String.equals` kiểm tra nội dung ký tự nên là `true`.

**Đừng dùng ví dụ với hai string literals giống nhau để chứng minh mọi String giống nội dung đều có cùng identity.** Literals có thể được intern; việc intern không làm `==` trở thành phép so sánh nội dung tổng quát.

### 3.3. Khi nào dùng `Objects.equals(a, b)`?

`java.util.Objects.equals(a,b)` giúp so sánh equality theo hợp đồng `equals` mà **an toàn với `null`**:

~~~java
String a = null;
String b = null;
System.out.println(java.util.Objects.equals(a, b)); // true
~~~

Nếu gọi `a.equals(b)` khi `a == null`, chương trình ném `NullPointerException`. Nhưng `Objects.equals` không thay đổi định nghĩa identity; nó chỉ triển khai kiểm tra equality có xử lý null.

## 4. Gán lại biến không làm alias khác đổi tham chiếu

Hãy xét:

~~~java
Box left = new Box(1);
Box right = left;
right = new Box(2);
~~~

Ở dòng 2, `left` và `right` cùng Box A. Dòng 3 tạo Box B mới rồi **gán lại biến `right`**; sau đó:

~~~text
left  -----> Box A { value = 1 }
right -----> Box B { value = 2 }
~~~

Nguyên tắc này đúng với local variables, instance fields, static fields và parameter variables (nếu được phép gán lại). Việc một biến trỏ sang object mới **không truyền tác động** đến các biến khác từng có cùng giá trị tham chiếu.

Một nhầm lẫn là viết:

~~~java
User old = currentUser;
currentUser = new User("Other");
~~~

rồi tưởng `old` cũng trỏ user mới. Nếu có đoạn mã đầy đủ và `User` phù hợp, `old` vẫn giữ reference cũ. Ngược lại, nếu **object cũ bị sửa field** trước hoặc sau đó thông qua reference khác, `old` vẫn có thể quan sát sự sửa đổi.

### 4.1. `null` không xóa đối tượng được biến khác tham chiếu

~~~java
Box first = new Box(5);
Box second = first;
first = null;
System.out.println(second.value); // 5
~~~

Trong một method với class `Box` phù hợp, `second` vẫn tham chiếu object. `null` là **giá trị tham chiếu đặc biệt** biểu thị không có object; nó không phải lệnh giải phóng object.

Nếu đọc `first.value` sau `first = null`, Java ném `NullPointerException`; nhưng `second.value` vẫn dùng được.

## 5. `final` cố định biến tham chiếu, không làm object bất biến

Một field/local/parameter kiểu tham chiếu có thể được khai báo `final`:

~~~java
final StringBuilder buffer = new StringBuilder("A");
buffer.append("B"); // Hợp lệ
// buffer = new StringBuilder("C"); // Không hợp lệ
~~~

`final` ngăn **gán lại biến `buffer`** sau khi nó đã được gán giá trị hợp lệ, nhưng không ngăn sửa đối tượng `StringBuilder` thông qua `append`.

Ví dụ độc lập **`FinalReferenceDemo.java`**:

~~~java
public class FinalReferenceDemo {
    static final class Counter {
        int value;

        Counter(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        final Counter a = new Counter(3);
        Counter b = a;

        b.value = 8;
        System.out.println("a.value=" + a.value);
        System.out.println("same object=" + (a == b));

        b = new Counter(100);
        System.out.println("a after b reassigned=" + a.value);
        System.out.println("b.value=" + b.value);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac FinalReferenceDemo.java
java FinalReferenceDemo
~~~

Output:

~~~text
a.value=8
same object=true
a after b reassigned=8
b.value=100
~~~

Ở đây `a` là final nên không thể gán lại; `b` không final và có thể chuyển sang Counter mới. Việc `a` final **không** bảo vệ `a.value` khỏi thay đổi qua alias `b`.

**Phân biệt ba cấp:**

1. **Biến tham chiếu không gán lại được**: `final Box b`.
2. **Đối tượng cung cấp API không sửa trạng thái**: ví dụ kiểu immutable được thiết kế đúng.
3. **Toàn bộ đồ thị đối tượng không sửa đổi được**: yêu cầu mạnh hơn; mọi nested mutable object cũng phải được bảo vệ hoặc sao chép theo hợp đồng.

Một object chứa `final List<String> items` **chưa chắc bất biến**, vì danh sách mà `items` trỏ tới có thể vẫn mutable.

## 6. String: aliasing vẫn có, nhưng chuỗi là immutable

`String` là kiểu tham chiếu. Hai biến `String` có thể cùng tham chiếu **một object**, nhưng nội dung String object **không thể sửa tại chỗ** bằng API thông thường.

Lưu **`ImmutableStringDemo.java`**:

~~~java
public class ImmutableStringDemo {
    public static void main(String[] args) {
        String first = "Hi";
        String alias = first;

        System.out.println("initial identity=" + (first == alias));

        alias = alias + "!";
        System.out.println("first=" + first);
        System.out.println("alias=" + alias);
        System.out.println("identity after concat=" + (first == alias));
    }
}
~~~

Chạy:

~~~bash
javac ImmutableStringDemo.java
java ImmutableStringDemo
~~~

Output:

~~~text
initial identity=true
first=Hi
alias=Hi!
identity after concat=false
~~~

`alias = alias + "!"` tạo **giá trị chuỗi mới** và gán lại biến `alias`. Nó không đổi nội dung String `"Hi"` mà `first` vẫn tham chiếu.

Điều này không có nghĩa aliasing “không xảy ra với immutable objects”. Alias vẫn có thể cùng reference; chỉ là **không thể quan sát thay đổi nội dung object qua một biến khác** vì object bất biến. Tính bất biến giúp việc chia sẻ tham chiếu an toàn hơn.

**Cẩn thận với kết luận `String a == b`**: String literals có thể cùng object do intern, nhưng String khác nguồn vẫn có thể không cùng identity. Để so nội dung, dùng `equals`, không dùng `==`.

## 7. Truyền tham số: Java truyền theo giá trị, kể cả giá trị tham chiếu

Khi caller truyền một object reference cho method, Java **sao chép giá trị tham chiếu** vào parameter variable. Vì vậy:

- Parameter ban đầu cùng tham chiếu object với biến caller.
- Method có thể sửa **object** thông qua parameter nếu object cho phép và quyền truy cập phù hợp.
- Gán lại **parameter** sang object khác **không gán lại biến caller**.
- Với primitive arguments, parameter nhận bản sao giá trị primitive; gán lại nó cũng không sửa biến caller.

Lưu tệp **`ReferenceParameterDemo.java`**:

~~~java
public class ReferenceParameterDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static void mutateThenReassign(Box parameter) {
        parameter.value += 5;
        parameter = new Box(999);
        System.out.println("inside object=" + parameter.value);
    }

    static void changePrimitive(int number) {
        number += 100;
        System.out.println("inside primitive=" + number);
    }

    public static void main(String[] args) {
        Box original = new Box(10);
        Box alias = original;

        mutateThenReassign(original);
        System.out.println("outside original=" + original.value);
        System.out.println("outside alias=" + alias.value);
        System.out.println("same object=" + (original == alias));

        int number = 7;
        changePrimitive(number);
        System.out.println("outside primitive=" + number);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ReferenceParameterDemo.java
java ReferenceParameterDemo
~~~

Output:

~~~text
inside object=999
outside original=15
outside alias=15
same object=true
inside primitive=107
outside primitive=7
~~~

Phân tích chi tiết:

1. `original` và `alias` giữ cùng reference tới Box A (ban đầu `value = 10`).
2. Gọi `mutateThenReassign(original)`: Java **chép giá trị tham chiếu A** vào parameter `parameter`. Không tạo Box mới ở bước truyền tham số.
3. `parameter.value += 5` sửa Box A thành `15`; caller và alias cùng quan sát được.
4. `parameter = new Box(999)` chỉ làm parameter của lời gọi trỏ Box B; `original` và `alias` ở caller **không** đổi reference.
5. `changePrimitive(number)` nhận bản sao `7`, in `107` trong method, còn biến `number` của `main` vẫn `7`.

**Cách nói chính xác:** Java là **pass-by-value**. Với đối tượng, giá trị được sao chép là **reference**, nên nhiều biến có thể cùng trỏ tới một object. Đó **không phải** pass-by-reference của *biến* theo nghĩa callee có thể gán lại trực tiếp biến caller.

### 7.1. Muốn đổi tham chiếu của caller thì làm thế nào?

Thay vì mong gán lại parameter sẽ tác động caller, hãy **trả về reference mới**, rồi caller tự gán:

~~~java
static Box replace(Box oldValue) {
    return new Box(oldValue.value + 1);
}

// Trong một method:
Box box = new Box(5);
box = replace(box);
~~~

Đây là đoạn minh họa cần class `Box` phù hợp. Sau câu lệnh gán, caller chủ động đổi `box` sang object mới. Cách này thường làm luồng dữ liệu rõ ràng hơn một method bí mật sửa trạng thái object không cần thiết.

## 8. Aliasing qua instance fields và object graph

Nhiều biến cùng tham chiếu object không chỉ xảy ra vì `Box b = a`. Aliasing còn xuất hiện khi **hai field ở các object khác nhau giữ cùng reference**.

Ví dụ:

~~~java
class Address {
    String city;

    Address(String city) {
        this.city = city;
    }
}

class Person {
    String name;
    Address address;

    Person(String name, Address address) {
        this.name = name;
        this.address = address;
    }
}
~~~

Đây là các khai báo class minh họa, chưa có `main`.

Nếu caller viết:

~~~java
Address common = new Address("Ha Noi");
Person a = new Person("An", common);
Person b = new Person("Binh", common);
~~~

thì `a` và `b` là **hai Person objects khác nhau**, nhưng:

~~~text
Person A ---- address ----+
                          |
                          +----> Address { city = "Ha Noi" }
                          |
Person B ---- address ----+
~~~

`a.address == b.address` là `true`. Khi `a.address.city = "Hue";`, đọc `b.address.city` sẽ thấy `"Hue"` vì cả hai tham chiếu cùng một `Address`.

Điều này giải thích vì sao “tạo object mới” **không bảo đảm toàn bộ dữ liệu bên trong đều độc lập**. Object mới có thể nhận tham chiếu tới các thành phần cũ và chia sẻ chúng.

### 8.1. Chương trình ngắn xác nhận chia sẻ field

Lưu **`SharedFieldDemo.java`**:

~~~java
public class SharedFieldDemo {
    static final class Address {
        String city;

        Address(String city) {
            this.city = city;
        }
    }

    static final class Person {
        final String name;
        final Address address;

        Person(String name, Address address) {
            this.name = name;
            this.address = address;
        }
    }

    public static void main(String[] args) {
        Address shared = new Address("Ha Noi");
        Person a = new Person("An", shared);
        Person b = new Person("Binh", shared);

        System.out.println("same address=" + (a.address == b.address));
        a.address.city = "Hue";
        System.out.println(a.name + "=" + a.address.city);
        System.out.println(b.name + "=" + b.address.city);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac SharedFieldDemo.java
java SharedFieldDemo
~~~

Output:

~~~text
same address=true
An=Hue
Binh=Hue
~~~

Cả hai `Person.address` fields đều được khai báo `final`, nhưng chỉ **giá trị tham chiếu trong field không được gán lại**; object `Address` vẫn mutable và vẫn chia sẻ. Đây là lý do cần thiết kế ownership hoặc defensive copying khi không muốn dữ liệu dùng chung.

## 9. Aliasing với mảng: `int[] b = a` không copy phần tử

Mảng là **object** trong Java. Biến có kiểu `int[]` lưu reference tới một mảng, không lưu bản sao các phần tử.

~~~java
int[] first = {1, 2, 3};
int[] alias = first;

alias[0] = 99;
System.out.println(first[0]); // 99
~~~

`alias[0]` và `first[0]` truy cập **phần tử số 0 của cùng array object**. Thao tác `alias = new int[]{7,8};` sẽ chỉ gán lại biến `alias`, không đổi `first`.

### 9.1. Copy mảng một chiều

Muốn có mảng `int[]` khác:

~~~java
int[] source = {1, 2, 3};
int[] copy = source.clone();
copy[0] = 100;

System.out.println(source[0]); // 1
System.out.println(copy[0]);   // 100
~~~

Đối với **mảng primitive một chiều**, `clone()` tạo mảng mới và sao chép **giá trị của từng phần tử**. `Arrays.copyOf(source, source.length)` và `System.arraycopy` cũng có thể dùng khi phù hợp.

Với **mảng chứa reference**, `clone()` chỉ sao chép **các phần tử reference**: các object được chúng trỏ tới vẫn có thể chia sẻ.

### 9.2. Mảng hai chiều: `clone()` thường chỉ copy lớp ngoài

Lưu tệp **`ArrayAliasingDemo.java`**:

~~~java
public class ArrayAliasingDemo {
    public static void main(String[] args) {
        int[][] source = {
                {1, 2},
                {3, 4}
        };

        int[][] alias = source;
        int[][] shallow = source.clone();

        int[][] deep = new int[source.length][];
        for (int i = 0; i < source.length; i++) {
            deep[i] = source[i].clone();
        }

        source[0][0] = 99;

        System.out.println("source == alias=" + (source == alias));
        System.out.println("source == shallow=" + (source == shallow));
        System.out.println("row shared=" + (source[0] == shallow[0]));
        System.out.println("shallow[0][0]=" + shallow[0][0]);
        System.out.println("deep[0][0]=" + deep[0][0]);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ArrayAliasingDemo.java
java ArrayAliasingDemo
~~~

Output:

~~~text
source == alias=true
source == shallow=false
row shared=true
shallow[0][0]=99
deep[0][0]=1
~~~

Giải thích:

- `alias` là **cùng mảng ngoài** với `source`.
- `shallow = source.clone()` tạo **mảng ngoài khác**, nhưng từng phần tử vẫn trỏ tới các **mảng con cũ**.
- Vì vậy `source[0] == shallow[0]` là `true`, và sửa `source[0][0]` xuất hiện trong `shallow[0][0]`.
- `deep` tạo mảng ngoài mới **và sao chép từng mảng con `int[]`**. Với cấu trúc ví dụ chỉ có các hàng `int[]`, đây là bản sao độc lập của các phần tử primitive; `deep[0][0]` vẫn `1`.

Từ “deep copy” luôn phải được hiểu **theo độ sâu cấu trúc cần sao chép**. Với một mảng chứa các object có nested references phức tạp, chỉ `clone()` một tầng con chưa chắc đủ tạo bản sao độc lập toàn bộ object graph.

## 10. Collection: alias, bản sao và read-only view

`List`, `Set`, `Map` đều được làm việc thông qua reference. Khi bạn viết:

~~~java
java.util.List<String> source = new java.util.ArrayList<>();
java.util.List<String> alias = source;
~~~

`source` và `alias` trỏ đến **cùng ArrayList**. `alias.add("Java")` làm `source.size()` tăng vì cùng object. Nhưng `alias = new ArrayList<>()` chỉ chuyển biến `alias` sang danh sách khác.

Có nhiều cách **không phải alias trực tiếp**, và phải phân biệt chúng:

| Cách tạo | Tạo container mới? | Có cùng trạng thái thành phần không? | Khi source thêm/xóa phần tử |
| --- | --- | --- | --- |
| `alias = source` | Không | Cùng chính collection object | Alias thấy thay đổi |
| `new ArrayList<>(source)` | Có | Bản sao **nông**: copy reference phần tử | Container mới không tự đổi kích thước |
| `List.copyOf(source)` | Trả list không sửa được, có thể reuse trong vài trường hợp theo API | Phần tử object mutable vẫn có thể được chia sẻ | Không phản ánh thay đổi cấu trúc source sau đó |
| `Collections.unmodifiableList(source)` | View không cho thao tác sửa qua view | Cùng **backing list** để quan sát | View có thể phản ánh thay đổi ở source |
| `List.of("A","B")` | Cung cấp list không sửa được | Các phần tử String bất biến | Không có source mutable tương ứng |

**“Không sửa được thông qua API list” khác với “danh sách và mọi phần tử hoàn toàn bất biến”.** Ví dụ `List.copyOf` tạo/cung cấp list không sửa được, nhưng nếu các phần tử là `StringBuilder`, việc sửa phần tử qua tham chiếu khác vẫn có thể quan sát được.

### 10.1. Ví dụ độc lập: snapshot và view

Lưu **`CollectionAliasingDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class CollectionAliasingDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));
        List<String> alias = source;
        List<String> copy = new ArrayList<>(source);
        List<String> snapshot = List.copyOf(source);
        List<String> view = Collections.unmodifiableList(source);

        alias.add("B");

        System.out.println("source=" + source);
        System.out.println("alias=" + alias);
        System.out.println("copy=" + copy);
        System.out.println("snapshot=" + snapshot);
        System.out.println("view=" + view);

        source.set(0, "X");
        System.out.println("snapshot later=" + snapshot);
        System.out.println("view later=" + view);

        try {
            snapshot.add("C");
        } catch (UnsupportedOperationException expected) {
            System.out.println("snapshot cannot add");
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac CollectionAliasingDemo.java
java CollectionAliasingDemo
~~~

Output:

~~~text
source=[A, B]
alias=[A, B]
copy=[A]
snapshot=[A]
view=[A, B]
snapshot later=[A]
view later=[X, B]
snapshot cannot add
~~~

**Điểm cần nhớ:**

- `alias.add("B")` thay đổi cùng list mà `source` trỏ tới.
- `copy` và `snapshot` lấy cấu trúc phần tử tại thời điểm tạo; chúng không tự nhận phần tử `"B"` được thêm sau.
- `view` là **unmodifiable view** của `source`; ngăn gọi `add` qua view nhưng vẫn phản ánh thay đổi của backing list.
- `snapshot.add("C")` ném `UnsupportedOperationException` vì `List.copyOf` trả list không sửa được.
- Không nên dựa vào `snapshot != source` như một **bảo đảm identity** cho mọi đầu vào: API có thể reuse object nếu đầu vào đã là list không sửa được phù hợp.

## 11. Shallow copy khác deep copy của object graph

Giả sử một `Person` chứa reference đến `Address`. Tạo Person mới bằng cách truyền **cùng `Address`** là **shallow copy** của cấu trúc theo ví dụ:

~~~java
Person clone = new Person(original.name, original.address);
~~~

`clone` là Person object mới, nhưng `clone.address == original.address` vẫn `true`. Sửa địa chỉ ở bản gốc cũng ảnh hưởng bản shallow.

Muốn tách trạng thái `Address`, cần tạo Address mới và sao chép nội dung có ý nghĩa, ví dụ `new Address(original.address.city)`. Đây là bước deep copy đối với object graph **hai tầng cụ thể** đang xét.

### 11.1. Ví dụ Java chạy độc lập về shallow/deep copy

Lưu **`CopyDepthDemo.java`**:

~~~java
public class CopyDepthDemo {
    static final class Address {
        String city;

        Address(String city) {
            this.city = city;
        }
    }

    static final class Person {
        final String name;
        final Address address;

        Person(String name, Address address) {
            this.name = name;
            this.address = address;
        }

        Person copyShallow() {
            return new Person(name, address);
        }

        Person copyDeepForThisModel() {
            return new Person(name, new Address(address.city));
        }
    }

    public static void main(String[] args) {
        Person original = new Person("Lan", new Address("Ha Noi"));
        Person shallow = original.copyShallow();
        Person deep = original.copyDeepForThisModel();

        System.out.println("same Person=" + (original == shallow));
        System.out.println("shallow shares Address=" +
                (original.address == shallow.address));
        System.out.println("deep shares Address=" +
                (original.address == deep.address));

        original.address.city = "Hue";
        System.out.println("original=" + original.address.city);
        System.out.println("shallow=" + shallow.address.city);
        System.out.println("deep=" + deep.address.city);
    }
}
~~~

Chạy:

~~~bash
javac CopyDepthDemo.java
java CopyDepthDemo
~~~

Output:

~~~text
same Person=false
shallow shares Address=true
deep shares Address=false
original=Hue
shallow=Hue
deep=Ha Noi
~~~

Phân tích:

1. Hai phương thức copy đều tạo `Person` mới: `original == shallow` là `false`.
2. `copyShallow` truyền `address` cũ, nên `original.address == shallow.address` là `true`.
3. `copyDeepForThisModel` tạo Address mới, nên reference tới Address không còn chung.
4. `original.address.city = "Hue"` thay đổi Address cũ; `shallow` quan sát thấy `Hue`, còn `deep` giữ `Ha Noi`.

**Giới hạn:** Đây là deep copy đối với model đơn giản chỉ có một field tham chiếu mutable `Address`. Trong object graph có cycles, identity cần bảo toàn, nested collections hoặc external resources, sao chép sâu thực sự có thể phức tạp và phải được xác định theo hợp đồng. Không nên gọi một phương thức `clone()` mặc định là “deep clone” khi chưa chứng minh nó sao chép mọi thành phần cần thiết.

### 11.2. Khi nào shallow copy đủ?

Shallow copy thường đủ khi:

- Các phần tử được chia sẻ là **immutable**, như `String`, một số value objects được thiết kế đúng.
- API **chủ đích chia sẻ** đối tượng thành phần, ví dụ các dịch vụ dùng chung hoặc cache.
- Dữ liệu không bị sửa trong vòng đời liên quan.
- Ownership và quy tắc cập nhật được xác định rõ.

Ngược lại, nếu dữ liệu bên trong mutable và mỗi bản copy cần độc lập hoàn toàn, phải xem từng reference lồng nhau trước khi lựa chọn deep copy, immutable model hoặc copy-on-write.

## 12. Thiết kế constructor/getter tránh aliasing ngoài ý muốn

Một cách rò rỉ mutable state thường gặp là constructor **giữ lại trực tiếp tham chiếu bên ngoài** hoặc getter **trả tham chiếu đến collection mutable nội bộ**.

### 12.1. Thiết kế dễ bị sửa từ bên ngoài

~~~java
class Team {
    private final java.util.List<String> members;

    Team(java.util.List<String> members) {
        this.members = members;
    }

    java.util.List<String> members() {
        return members;
    }
}
~~~

Đây là class minh họa biên dịch được. `members` được khai báo `final`, nhưng:

- Bên gọi vẫn có thể giữ biến `source` và `source.add("X")`; `Team.members` quan sát thay đổi vì cùng list.
- Caller lấy `team.members()` rồi gọi `add` lên list được trả về cũng sửa trực tiếp trạng thái Team.

Nếu Team muốn kiểm soát danh sách thành viên, đây là **exposure of mutable representation**.

### 12.2. Sử dụng defensive copy cho collection String

Lưu **`DefensiveCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class DefensiveCopyDemo {
    static final class Team {
        private final List<String> members;

        Team(List<String> input) {
            this.members = List.copyOf(input);
        }

        List<String> members() {
            return members;
        }
    }

    public static void main(String[] args) {
        List<String> external = new ArrayList<>(List.of("Lan"));
        Team team = new Team(external);

        external.add("Minh");

        System.out.println("external=" + external);
        System.out.println("team=" + team.members());

        try {
            team.members().add("An");
        } catch (UnsupportedOperationException expected) {
            System.out.println("team list cannot add");
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac DefensiveCopyDemo.java
java DefensiveCopyDemo
~~~

Output:

~~~text
external=[Lan, Minh]
team=[Lan]
team list cannot add
~~~

`List.copyOf(input)` tạo/cung cấp một danh sách không sửa được với **nội dung phần tử tại thời điểm gọi**. Vì các phần tử là `String` bất biến, Team không phải lo người dùng thay đổi nội dung từng `String`. Getter trả chính list không sửa được, nên caller không thể `add` vào danh sách Team.

**Nếu danh sách chứa object mutable**, `List.copyOf` vẫn giữ reference tới các phần tử đó. Khi cần bất biến sâu, phải sao chép các phần tử hoặc dùng các immutable value objects thích hợp. Ngoài ra, `List.copyOf` không chấp nhận phần tử null; nên điều đó cũng trở thành một phần hợp đồng constructor cần được tài liệu hóa.

### 12.3. Với mảng, hãy sao chép khi nhận và trả

~~~java
class Scores {
    private final int[] values;

    Scores(int[] values) {
        this.values = values.clone();
    }

    int[] values() {
        return values.clone();
    }
}
~~~

Đây là class minh họa hợp lệ. `clone()` của `int[]` tạo bản copy các primitive values; bên gọi không thể sửa array nội bộ chỉ bằng việc giữ array ban đầu hoặc thay đổi array được getter trả về.

Nếu `values` là `Person[]`, clone chỉ sao chép các **reference phần tử**, không tự copy từng Person. Khi đó mức bảo vệ cần thiết phụ thuộc Person có mutable không và quy tắc sở hữu dữ liệu.

## 13. Static fields có thể là một nguồn chia sẻ object

Hai instance fields thuộc hai đối tượng khác nhau thường giữ những giá trị reference **độc lập về nơi lưu field**, nhưng chúng **có thể cùng trỏ object** nếu được gán như vậy. Còn một **static field** bản thân gắn với lớp, có một giá trị dùng chung trong phạm vi lớp tương ứng.

Ví dụ:

~~~java
class Repository {
    static final java.util.List<String> SHARED =
            new java.util.ArrayList<>();

    private final java.util.List<String> local =
            new java.util.ArrayList<>();
}
~~~

Đây là class minh họa:

- `Repository.SHARED` là field static chứa một tham chiếu danh sách dùng chung; các mã truy cập nó thấy cùng list.
- Mỗi lần `new Repository()`, initializer `new ArrayList<>()` cấp một list riêng cho field `local` của object mới.
- Tuy nhiên `final` ở cả hai field chỉ ngăn **gán lại tham chiếu field**, không làm bản thân list bất biến.

Không nên dùng `static` chỉ để “tiện lấy dữ liệu” nếu dữ liệu thực ra thuộc riêng từng object. Cũng không nên nghĩ mọi instance field đều tự tạo list mới: nếu initializer là `local = Repository.SHARED`, các instance fields riêng vẫn có thể chứa **cùng một reference**.

## 14. Aliasing và garbage collection

Java tự động quản lý bộ nhớ thông qua cơ chế garbage collection (GC) của runtime. Nhiều biến giữ tham chiếu tới một object có thể làm object tiếp tục **reachable**, tùy phạm vi biến và quan hệ tham chiếu.

Ví dụ:

~~~java
Object first = new Object();
Object second = first;
first = null;
~~~

Ở thời điểm mã còn có thể dùng `second`, object vẫn reachable qua `second`. Gán `first = null` **không trực tiếp gọi destructor**, không buộc GC chạy ngay, và không xóa dữ liệu để biến `second` mất tác dụng.

Nếu về sau **không còn đường tham chiếu reachable** tới object từ các GC roots, object có thể đủ điều kiện để thu hồi. **Thời điểm GC không được Java bảo đảm ngay lập tức**. `System.gc()` cũng không phải lệnh chắc chắn giải phóng đúng object vào đúng lúc.

Đối tượng có thể tiếp tục reachable qua field, static cache, collection, closure/inner class, thread hoặc những reference khác chứ không chỉ biến local mà bạn đang nhìn thấy.

### 14.1. Vòng tham chiếu không tự có nghĩa rò rỉ

Hai object A và B có field trỏ qua lại có thể tạo cycle A → B → A. Nếu **không còn đường reachable từ GC roots**, cycle đó vẫn có thể được GC xử lý; Java không yêu cầu “đếm reference bằng tay” và không mặc định giữ sống mọi cycle mãi mãi.

Ngược lại, một static collection vô tình giữ object lâu dài có thể khiến dữ liệu không được thu hồi dù caller tưởng đã bỏ mọi biến local. Vấn đề là **reachability và lifecycle**, không đơn thuần là số mũi tên ở một sơ đồ.

## 15. Aliasing trong chương trình đa luồng

Nếu nhiều biến ở các thread khác nhau cùng trỏ tới **một object mutable**, chúng có thể truy cập và thay đổi **shared state**. Aliasing tự nó không đồng nghĩa có data race, nhưng nó tạo điều kiện chia sẻ dữ liệu.

Ví dụ minh họa:

~~~java
class Counter {
    int value;

    void increment() {
        value++;
    }
}
~~~

Nếu cùng một `Counter` được chia sẻ giữa nhiều thread và các thread đồng thời gọi `increment()` mà không đồng bộ, phép `value++` **không nguyên tử** và có thể mất lần tăng. Chỉ có hai biến tham chiếu tới cùng Counter **không** cung cấp synchronization.

Các phương án tùy bài toán:

- Tránh chia sẻ mutable objects; dùng immutable values hoặc copy theo ownership.
- Dùng synchronization/locks nếu nhiều thao tác phải giữ invariant cùng nhau.
- Dùng `AtomicInteger` hoặc kiểu atomic phù hợp cho thao tác số đơn giản.
- Xác định quy tắc thread confinement hoặc message passing khi thích hợp.

Lưu ý `final Counter c` không làm `c.value++` trở thành atomic. `final` ngăn đổi biến reference, không phải khóa đa luồng.

## 16. Những lỗi hiểu sai và cách sửa

| Nhầm lẫn | Giải thích đúng / cách sửa |
| --- | --- |
| “`Box b = a` tạo bản sao Box.” | Chỉ sao chép **giá trị reference**; để tạo Box mới cần constructor/copy/factory thích hợp. |
| “Hai biến thì chắc có hai object.” | Có thể có nhiều aliases cho một object hoặc một biến lần lượt trỏ nhiều objects. |
| “Hai object có field giống nhau thì `a == b` true.” | `==` với reference so **identity**, không so field. |
| “`equals()` mặc định so tất cả field.” | `Object.equals` mặc định theo identity; lớp phải override khi muốn value equality. |
| “Gán `b = new Box(...)` làm `a` đổi theo.” | Chỉ `b` đổi giá trị reference; `a` vẫn giữ reference cũ. |
| “`b.field = 10` chỉ thay đổi thông tin riêng của biến b.” | Field thuộc **object**, nên mọi alias cùng object sẽ quan sát trạng thái mới. |
| “`a = null` xóa object dù `b` còn tham chiếu.” | `a` chỉ không trỏ object nữa; `b` vẫn sử dụng object được. |
| “Java truyền object theo reference của biến caller.” | Java truyền **bản sao giá trị tham chiếu**; gán lại parameter không gán lại biến caller. |
| “`final List` là immutable list.” | `final` chỉ ngăn gán lại biến/field reference; list có thể mutable. |
| “`String b = a`, sau đó b nối ký tự sẽ sửa a.” | String immutable; phép nối tạo giá trị chuỗi mới và gán lại b. |
| “`int[][] copy = original.clone()` sao chép mọi phần tử ở mọi hàng.” | Chỉ copy array ngoài; các hàng `int[]` còn có thể chia sẻ. |
| “`new ArrayList<>(source)` sao chép luôn mọi object phần tử.” | Chỉ shallow copy của container; các reference phần tử vẫn chia sẻ. |
| “`Collections.unmodifiableList(source)` là snapshot.” | Thường là read-only **view** gắn với backing list; source đổi, view có thể phản ánh. |
| “`List.copyOf(source)` làm từng phần tử mutable trở thành immutable.” | Chỉ cấu trúc list không sửa được; nội dung object phần tử có thể thay đổi. |
| “Getter trả list nội bộ nhưng `private final` đã đủ bảo vệ.” | Caller có thể sửa list nếu mutable; dùng defensive copy/unmodifiable API phù hợp. |
| “Chia sẻ cùng object giữa thread tự an toàn.” | Không có bảo đảm thread safety; cần synchronization hoặc immutability đúng mức. |
| “Không còn biến local thì object chắc chắn bị xóa ngay.” | GC phụ thuộc reachability và quyết định runtime; object có thể còn được giữ qua field/cache. |

## 17. Quy trình suy luận khi thấy nhiều biến tham chiếu

Khi đọc đoạn mã có nhiều reference variables, có thể làm theo những bước sau:

1. **Đánh dấu mọi nơi tạo object**: `new`, factory, clone/copy, object trả về từ method. Đừng giả định factory luôn `new`.
2. **Vẽ các biến/field như mũi tên** tới objects; lúc khởi đầu ghi rõ mũi tên nào cùng object.
3. **Khi gặp `b = a`**, cho `b` trỏ cùng object như `a` tại **thời điểm gán**; không tạo object mới.
4. **Khi gặp `b.field = ...` hoặc `b.methodMutating()`**, thay đổi trạng thái **object mà b đang trỏ đến**, không phải “trạng thái nằm trong tên b”.
5. **Khi gặp `b = new ...` hoặc `b = null`**, đổi **mũi tên b**; các mũi tên khác không tự chuyển theo.
6. **Nếu method nhận reference**, thêm một parameter variable ban đầu trỏ cùng object; theo dõi mutation và rebinding riêng biệt.
7. **Nếu có copy**, hỏi rõ: copy container? copy phần tử? copy nested objects? Có immutable values hoặc shared dependencies có chủ ý không?
8. **Nếu so sánh**, tách `==` (identity) với `equals` (hợp đồng logic). Với nullable references cân nhắc `Objects.equals`.
9. **Nếu có đa luồng hoặc dữ liệu sống lâu**, xem alias nào còn giữ object reachable và mọi shared mutations có được đồng bộ hóa không.

Đây là quy trình hiệu quả hơn so với đoán `new` nào “được gọi gần đây nhất” hoặc giả định mỗi tên biến tương ứng với một object riêng.

## 18. Tự kiểm tra có lời giải

### Câu 1. Một object hay hai?

~~~java
Box x = new Box(2);
Box y = x;
~~~

**Hỏi:** Có mấy object `Box` được tạo bởi hai dòng này?  
**Đáp án:** Một. `y` nhận cùng reference với `x`, không gọi `new`.

### Câu 2. Đọc qua alias sau mutation

~~~java
Box x = new Box(2);
Box y = x;
y.value = 8;
~~~

**Hỏi:** `x.value` bằng bao nhiêu?  
**Đáp án:** `8`, vì x và y cùng Box.

### Câu 3. Đọc sau reassignment

~~~java
Box x = new Box(2);
Box y = x;
y = new Box(8);
~~~

**Hỏi:** `x.value` bằng bao nhiêu và `x == y` ra sao?  
**Đáp án:** `x.value == 2`, `x == y` là `false`. Gán lại y không sửa x.

### Câu 4. Object cùng field nhưng khác identity

~~~java
Box a = new Box(10);
Box b = new Box(10);
~~~

**Hỏi:** `a == b` là gì?  
**Đáp án:** `false`, vì có hai object riêng dù field bằng nhau.

### Câu 5. Truyền parameter

~~~java
static void reset(Box p) {
    p = new Box(0);
}
~~~

**Hỏi:** `reset(myBox)` có làm `myBox` trỏ object mới không?  
**Đáp án:** Không. Java chép reference vào p; chỉ p được gán lại. Muốn đổi biến caller, hãy trả reference mới và caller tự gán.

### Câu 6. Mutation bên trong method

~~~java
static void reset(Box p) {
    p.value = 0;
}
~~~

**Hỏi:** Sau `reset(myBox)`, `myBox.value` có thể thành `0` không?  
**Đáp án:** Có. p và myBox cùng object tại lúc gọi; method sửa object đó.

### Câu 7. Final reference

**Hỏi:** `final Box box = new Box(1);` có ngăn `box.value = 2;` không?  
**Đáp án:** Không. Field `value` vẫn mutable nếu không có ràng buộc khác; `final` chỉ ngăn gán lại biến box.

### Câu 8. String

**Hỏi:** `String a = "A"; String b = a; b += "B";` thì a là gì?  
**Đáp án:** `"A"`. String bất biến; b được gán sang chuỗi `"AB"` mới.

### Câu 9. Array clone

**Hỏi:** Với `int[][] original`, sao chép bằng `original.clone()` đã đảm bảo các mảng con độc lập chưa?  
**Đáp án:** Chưa. Clone copy mảng ngoài, mỗi phần tử mảng ngoài vẫn là reference tới các `int[]` con cũ.

### Câu 10. Collection copy

**Hỏi:** Vì sao `new ArrayList<>(listOfPersons)` có thể vẫn chia sẻ trạng thái với list cũ?  
**Đáp án:** Nó copy các **reference tới từng Person**, không copy Person objects; nếu các Person mutable, cả hai lists vẫn có thể quan sát thay đổi của Person được chia sẻ.

### Câu 11. Snapshot và view

**Hỏi:** Khác nhau giữa `List.copyOf(source)` và `Collections.unmodifiableList(source)` khi source có thay đổi cấu trúc sau đó?  
**Đáp án:** `List.copyOf` cung cấp unmodifiable list với phần tử ở thời điểm tạo; `Collections.unmodifiableList(source)` là unmodifiable **view** trên source nên có thể phản ánh thay đổi source.

### Câu 12. Null

**Hỏi:** Sau `Box a = new Box(1); Box b = a; a = null;`, `b.value` có truy cập được không?  
**Đáp án:** Có, vẫn đọc `1`, vì b còn tham chiếu object.

### Câu 13. Equality

**Hỏi:** Hai Person khác object nhưng cùng `id`, `a.equals(b)` có nhất thiết true không?  
**Đáp án:** Không nhất thiết. Nó phụ thuộc Person có override `equals` theo `id` hay không. `a == b` vẫn false nếu là hai object khác nhau.

### Câu 14. Thread safety

**Hỏi:** Hai thread cùng trỏ Counter và gọi `counter.value++`; chỉ việc biến tham chiếu là `final` có đủ tránh race không?  
**Đáp án:** Không. `final` không làm phép cập nhật field trở nên atomic hay synchronized.

## Tài liệu tham khảo

- Java Language Specification, [§4.3 — Reference Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.3): tham chiếu và đối tượng.
- Java Language Specification, [§4.12 — Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12): biến, kiểu biến và giá trị.
- Java Language Specification, [§15.21.3 — Reference Equality Operators == and !=](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.21.3): kiểm tra bằng nhau giữa các tham chiếu.
- Java Language Specification, [§15.12.4 — Run-Time Evaluation of Method Invocation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4): tính giá trị đối số và lời gọi method.

## Ghi nhớ

**Nhiều biến có thể cùng chứa một giá trị tham chiếu tới một object**. Viết `b = a` không tạo object mới: nó tạo **alias**. Sửa **trạng thái object** qua một alias thì các alias khác cùng object có thể quan sát thay đổi; ngược lại, **gán lại biến reference** sang object khác hoặc `null` không tự gán lại các biến còn lại.

`==` giữa references kiểm tra **cùng object**; `equals` kiểm tra **bằng nhau theo hợp đồng kiểu**. Java **truyền tham số theo giá trị**, kể cả khi giá trị được chép là reference. Với mảng/collections/nested objects, copy container thường chỉ là **shallow copy**; nếu cần trạng thái độc lập, phải quyết định mức defensive/deep copying hoặc dùng immutable values. Hiểu rõ những mối liên hệ này là nền tảng để tránh bug về shared mutable state, identity, ownership và concurrency.
