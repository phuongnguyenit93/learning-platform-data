# JVM Heap: nơi lưu đối tượng, mảng và sự khác nhau giữa đối tượng với biến tham chiếu

## Mục tiêu

Trong mô hình thực thi của JVM, **heap** là vùng dữ liệu runtime được chia sẻ giữa các thread, nơi tồn tại **class instances và arrays**. Tuy nhiên, một biến Java có kiểu tham chiếu như `Person person` không phải chính đối tượng `Person`. Biến chứa **giá trị tham chiếu**, có thể trỏ tới một đối tượng hoặc chứa `null`. Các biến tham chiếu có thể xuất hiện trong local variables của stack frame, trong field của object khác, trong static fields hoặc trong các phần tử mảng tham chiếu.

Sau bài học, bạn sẽ:
- Phân biệt rõ **object/array**, **reference value** và **reference variable**, không đồng nhất vùng nhớ của biến với vùng nhớ của object.
- Hiểu vai trò của **heap**, **JVM stack/frame**, **local variables**, **static fields** và các mối liên hệ giữa chúng.
- Mô tả `new`, khởi tạo field, mảng primitive/mảng tham chiếu, mảng đa chiều, aliasing, identity và equality.
- Dự đoán được khi nào việc gán, gọi phương thức, thay đổi field hoặc reassign biến làm thay đổi trạng thái quan sát được.
- Hiểu Java **luôn truyền tham số theo giá trị** — với tham số tham chiếu, bản sao được truyền là giá trị tham chiếu.
- Giải thích chính xác mối quan hệ giữa **reachability** và garbage collection, không cho rằng hết scope/đặt `null` sẽ lập tức giải phóng heap.
- Phân biệt **mô hình được JVMS bảo đảm** với chi tiết triển khai/tối ưu JIT như escape analysis và scalar replacement.
- Dùng Java 17+ và `javap` để khảo sát cơ chế này qua ví dụ chạy được.

## 1. Mô hình tổng quan: heap, stack frame và giá trị tham chiếu

Theo Java Virtual Machine Specification (JVMS), JVM có **heap** được chia sẻ giữa các thread, chứa các **class instances và arrays**. Mỗi thread có JVM stack riêng, gồm các **frame** của những phương thức đang được gọi; trong frame có **local variables** và **operand stack**. Bản thân static fields gắn với trạng thái của class/interface runtime, không phải với mỗi object được tạo.

Ví dụ:

~~~java
Person p = new Person("Lan");
~~~

Đây là đoạn minh họa, giả sử đã có class `Person` phù hợp. Về ngữ nghĩa:

1. Biểu thức `new Person("Lan")` tạo một instance `Person` mới, theo mô hình bộ nhớ JVM.
2. Constructor khởi tạo trạng thái instance đó; string `"Lan"` cũng là một đối tượng `String` theo ngữ nghĩa Java, với cơ chế literal/interning riêng.
3. Giá trị mà biểu thức tạo object trả về là **tham chiếu** đến instance.
4. Local variable `p` lưu **giá trị tham chiếu** ấy, không chứa toàn bộ bytes của Person ngay trong biến.
5. Nếu sau đó `p = null;` thì giá trị biến đổi thành null; **không có nghĩa object lập tức bị xóa**.

Sơ đồ khái niệm:

~~~text
Thread A / JVM stack
  frame main()
  local variable "p"
        |
        | reference value
        v
            SHARED HEAP
        +-------------------+
        | Person instance   |
        | name ----+        |
        +----------|--------+
                   | reference
                   v
             +-------------+
             | String "Lan"|
             +-------------+

Thread B / JVM stack
  frame other()
  local variable "another" ----> (có thể cùng Person instance)
~~~

Các mũi tên biểu thị quan hệ **tham chiếu logic**, **không phải** địa chỉ RAM thô mà JVM bắt buộc phơi bày. Object có thể sở hữu field primitive (lưu giá trị primitive) và field reference (lưu tham chiếu đến một object/array khác).

### Bảng phân biệt

| Khái niệm | Mô tả | Ví dụ | Vị trí theo mô hình |
| --- | --- | --- | --- |
| **Class instance** | Object có class, identity và instance fields | `new Person()` | Heap |
| **Array object** | Object có kiểu mảng, chiều dài cố định, các elements | `new int[3]` | Heap |
| **Local reference variable** | Slot chứa giá trị tham chiếu hoặc null | `Person p` trong method | Local variables của frame |
| **Instance reference field** | Thành phần của object chứa tham chiếu | `person.address` | Trong object chứa field |
| **Static reference field** | Trạng thái của class/interface runtime chứa tham chiếu | `static Person current` | Thuộc class runtime; không phải instance |
| **Reference-array element** | Một ô phần tử chứa tham chiếu/null | `people[0]` | Trong array object |
| **Primitive local variable** | Slot chứa giá trị số/boolean/char theo kiểu JVM thích hợp | `int count` | Local variables của frame |
| **Primitive instance field** | Giá trị primitive thuộc object | `person.age` | Trong object |
| **`null`** | Giá trị tham chiếu đặc biệt không tham chiếu object nào | `p = null` | Nằm ở nơi lưu reference value |

Không khẳng định mọi biến Java luôn có một “ô RAM vật lý” có thể truy cập: JVM/JIT được tối ưu hóa, có thể giữ giá trị trong register hoặc loại bỏ một số lưu trữ không quan sát được. Bảng trên là **mô hình ngữ nghĩa JVM**, không phải cam kết về bố cục vật lý của HotSpot trên mọi nền tảng.

## 2. Heap là gì? Heap không phải JVM stack

**Heap** được JVM tạo khi JVM khởi động. Các thread trong cùng JVM dùng chung heap theo mô hình runtime, và vùng này là đối tượng của cơ chế quản lý bộ nhớ/garbage collection. JVMS không yêu cầu một thuật toán GC, heap layout, generation hay thuật toán cấp phát cụ thể.

**JVM stack** là vùng dữ liệu riêng cho mỗi thread, với các frame được tạo/hủy theo lời gọi/phương thức. Frame chứa local variables và operand stack, cùng những thông tin cần thiết cho phương thức. Một **reference value trong frame** có thể trỏ tới object tồn tại trên heap.

Ví dụ:

~~~java
static int lengthOf(String text) {
    return text.length();
}
~~~

Đây là phương thức minh họa:
- Tham số `text` là một local variable kiểu tham chiếu trong frame `lengthOf`.
- Giá trị của `text` chỉ tới String object do caller cung cấp (nếu không null).
- Lệnh `text.length()` tác động đến String instance qua tham chiếu; JVM không nhân bản String object chỉ vì truyền tham số.
- Khi phương thức kết thúc, **frame bị hủy** theo mô hình gọi, nhưng String object **không nhất thiết** bị hủy: caller hoặc object khác có thể còn tham chiếu đến nó.

Hai phát biểu thường bị diễn giải quá mức:
- “Biến local ở stack, object ở heap” là mô tả hữu ích cho bytecode, **không phải** lời hứa của mọi tối ưu JIT về vị trí RAM thật.
- “Kết thúc phương thức thì object bị thu hồi” là **sai**: thời gian sống của một object phụ thuộc **reachability**, không phụ thuộc duy nhất scope của một reference variable.

## 3. Biến tham chiếu khác đối tượng ra sao?

Xét đoạn code:

~~~java
Box first = new Box(5);
Box second = first;
~~~

Giả sử `Box` là class có instance field `int value`.

- `new Box(5)` tạo **một** Box instance.
- `first` chứa tham chiếu đến instance đó.
- `second = first` **sao chép giá trị tham chiếu**, không cấp phát một Box instance mới.
- Hai biến khác nhau có thể cùng chỉ đến một object — gọi là **aliasing**.

Sơ đồ:

~~~text
first  -----+
            |
            +----> [Box object: value=5]
            |
second -----+
~~~

Nếu chạy `second.value = 12;`, lần đọc `first.value` sẽ thấy 12 trong trường hợp tuần tự thông thường: hai biến truy cập **cùng một object**.

Ngược lại:

~~~java
Box a = new Box(5);
Box b = new Box(5);
~~~

có hai object riêng với field `value` ban đầu cùng bằng 5. Việc hai object có trạng thái giống nhau **không bắt buộc có cùng identity**. `a == b` trả false khi hai phép `new` tạo hai object riêng biệt.

### Một phép gán tham chiếu không sao chép object

| Mã nguồn | Điều thay đổi | Có tạo object mới? |
| --- | --- | --- |
| `b = a;` | Giá trị tham chiếu trong biến `b` | Không |
| `b = null;` | Biến `b` không còn tham chiếu object | Không; cũng không tự hủy object |
| `b = new Box(7);` | Tạo Box mới, đưa tham chiếu mới vào `b` | Có theo ngữ nghĩa biểu thức `new` |
| `a.value = 10;` | Field `value` bên trong object được `a` tham chiếu | Không chỉ vì gán field primitive |
| `a.child = b;` | Field tham chiếu `child` của object `a` trỏ tới object của `b` | Không tạo copy object `b` |
| `Box[] items = new Box[2];` | Tạo **array object** chứa hai reference elements mặc định null | Có một array object, chưa có Box element object |

**Gán một reference khác** và **đột biến trạng thái object** là hai hành động khác nhau. Đây là điểm then chốt khi viết collection, API và mã đồng thời.

## 4. Reference values, null và equality

Java có **primitive values** và **reference values**. Một reference value là tham chiếu đến object/array hoặc giá trị `null`.

~~~java
String text = null;
System.out.println(text == null); // true
~~~

Đây là snippet trong một phương thức. `null` không phải đối tượng `Null` được tạo trên heap. Việc dùng null như receiver của phần lớn thao tác đọc field/gọi method sẽ dẫn đến `NullPointerException`, ví dụ:

~~~java
String text = null;
// text.length(); // Ném NullPointerException khi chạy.
~~~

Một reference có thể tham chiếu instance của class con, object implement interface, hoặc array có kiểu tương thích theo quy tắc Java.

### So sánh identity với equality

- `a == b` với hai **reference operands** kiểm tra chúng là **cùng một tham chiếu object** (hoặc cả hai null), không tự so nội dung field.
- `a.equals(b)` gọi method, có thể thực hiện **so sánh nội dung** nếu class override `equals` đúng cách. Nếu không override, `Object.equals` mặc định so theo identity.
- `Objects.equals(a, b)` xử lý null an toàn rồi dùng `equals`, **không mặc định là deep comparison** của object graph.
- `Arrays.equals(int[], int[])` hoặc `Arrays.deepEquals(Object[], Object[])` có hợp đồng riêng; array object thường không override `Object.equals` để so phần tử.
- `System.identityHashCode(object)` có thể hỗ trợ điều tra identity, nhưng **không bảo đảm mọi object có hash khác nhau** và không phải địa chỉ heap.

Ví dụ:

~~~java
String a = new String("hi");
String b = new String("hi");

System.out.println(a == b);      // false
System.out.println(a.equals(b)); // true
~~~

Đây là đoạn minh họa bên trong method. Hai biểu thức `new String(...)` tạo hai String instances khác identity, nhưng String override `equals` để so nội dung.

### Reference equality với String literal

Hai literal cùng nội dung `"java"` được intern theo quy tắc String literal, nên trong một ví dụ đơn giản:

~~~java
String first = "java";
String second = "java";
System.out.println(first == second); // true
~~~

Không dùng kết luận đó để suy ra mọi hai String object có cùng text đều identity-equal: `new String("java")` tạo object riêng. **String intern pool không phải loại object thứ ba nằm ngoài heap theo một quy tắc đơn giản của Java source**; JVM vẫn quản lý String objects theo semantics runtime. Cơ chế lưu trữ intern/cache là chi tiết triển khai và phiên bản.

## 5. Chương trình Java 17+: aliasing, rebind và equality

Tạo file **`HeapReferenceDemo.java`**:

~~~java
import java.util.Arrays;

public class HeapReferenceDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static void mutate(Box box) {
        box.value = 12;
    }

    static void rebind(Box box) {
        box = new Box(99);
    }

    public static void main(String[] args) {
        Box first = new Box(5);
        Box alias = first;
        Box other = new Box(5);

        System.out.println("sameRef=" + (first == alias));
        System.out.println("otherRef=" + (first == other));
        System.out.println("sameValue=" + (first.value == other.value));

        alias.value = 8;
        System.out.println("afterAlias=" + first.value);

        mutate(first);
        System.out.println("afterMutate=" + first.value);

        rebind(first);
        System.out.println("afterRebind=" + first.value);

        Box empty = null;
        System.out.println("isNull=" + (empty == null));

        int[] numbers = {1, 2, 3};
        int[] shared = numbers;
        shared[1] = 20;

        int[] copy = numbers.clone();
        copy[0] = 99;

        System.out.println("arraySame=" + (numbers == shared));
        System.out.println("cloneSame=" + (numbers == copy));
        System.out.println("numbers=" + Arrays.toString(numbers));
        System.out.println("copy=" + Arrays.toString(copy));
    }
}
~~~

Biên dịch và chạy (JDK 17+):

~~~bash
javac --release 17 HeapReferenceDemo.java
java HeapReferenceDemo
~~~

**Stdout chính xác:**

~~~text
sameRef=true
otherRef=false
sameValue=true
afterAlias=8
afterMutate=12
afterRebind=12
isNull=true
arraySame=true
cloneSame=false
numbers=[1, 20, 3]
copy=[99, 20, 3]
~~~

Giải thích:

1. `alias = first` sao chép reference, nên `sameRef=true`.
2. `new Box(5)` trong `other` tạo object khác; trường `value` bằng nhau nhưng identity khác.
3. `alias.value = 8` sửa **object chung**, nên đọc từ `first` trả 8.
4. `mutate(first)` nhận bản sao reference và sửa object, nên `first.value` thành 12.
5. `rebind(first)` chỉ thay đổi **biến tham số cục bộ `box`** bên trong phương thức; `first` ở caller vẫn trỏ Box cũ, giá trị vẫn là 12.
6. `empty = null` không liên quan đến identity của các Box khác.
7. `shared = numbers` tạo alias cho cùng array; thay phần tử qua `shared` làm `numbers` thay đổi.
8. `numbers.clone()` tạo array object mới; vì array `int[]` chứa primitive values, các phần tử được sao chép theo giá trị. Thay `copy[0]` không làm đổi `numbers[0]`.

**Phạm vi xác định:** chương trình thực thi tuần tự, không phụ thuộc GC timing hay object address, vì vậy kết quả in ổn định theo Java 17+.

## 6. Java truyền tham số theo giá trị, kể cả khi là reference

Một câu nói gây nhầm lẫn là “Java truyền object theo tham chiếu”. Cách chính xác:

> Java truyền **giá trị của biểu thức đối số** vào tham số. Đối với biến tham chiếu, giá trị được sao chép là **reference value** tới object; cả caller và callee có thể thao tác trên cùng object.

Từ đó có hai hiện tượng:

~~~text
Caller: first ------> [Box value=5]

mutate(first):
  parameter box ----> cùng Box
  box.value = 12     -> sửa object chung

rebind(first):
  parameter box ----> cùng Box (lúc bắt đầu)
  box = new Box(99)  -> chỉ box cục bộ đổi sang object khác
  caller first -----> vẫn trỏ Box ban đầu
~~~

**Không phải call-by-reference** theo nghĩa callee có thể gán lại biến gốc của caller chỉ bằng việc gán tham số. Muốn caller đổi biến tham chiếu, có thể return giá trị tham chiếu mới rồi caller tự gán:

~~~java
static Box replace(Box original) {
    return new Box(99);
}

// Trong một phương thức:
first = replace(first);
~~~

Đây là đoạn code **minh họa** cần đặt trong cùng class có kiểu `Box`. Biến của caller chỉ đổi khi tự thực hiện `first = ...`. Việc return reference không copy toàn bộ object.

### Ví dụ swap không hoán đổi biến gốc

~~~java
static void swap(Box a, Box b) {
    Box temp = a;
    a = b;
    b = temp;
}
~~~

Đây là method minh họa. Nó hoán đổi **hai local reference values trong frame của swap**, không sửa hai biến caller. Nếu mục tiêu là hoán đổi nội dung Box, có thể thay đổi fields (điều đó đổi trạng thái object), hoặc caller hoán đổi biến trực tiếp.

## 7. Array là object trên heap

Mảng trong Java không chỉ là một đoạn dữ liệu đặc biệt “ngoài hệ object”; mỗi mảng là **object** với:
- Một **runtime array class** phù hợp kiểu component và chiều mảng.
- **Identity** riêng.
- Một độ dài `length` cố định sau khi cấp phát.
- Các phần tử có giá trị primitive hoặc reference theo component type.
- Các phần tử ban đầu nhận **default values**.
- Khả năng được tham chiếu bởi local variables, fields hoặc các mảng khác.

### Mảng kiểu primitive

~~~java
int[] scores = new int[3];
System.out.println(scores.length);  // 3
System.out.println(scores[0]);      // 0
~~~

Đây là snippet trong phương thức. `new int[3]` tạo một array object chứa ba **int values** mặc định 0; **không tạo ba đối tượng `Integer`**.

Ví dụ:
- `new boolean[2]`: hai phần tử `false`.
- `new double[2]`: hai phần tử `+0.0d`.
- `new char[2]`: hai phần tử NUL (code unit 0).

### Mảng kiểu tham chiếu

~~~java
Box[] boxes = new Box[2];
System.out.println(boxes[0] == null); // true

boxes[0] = new Box(10);
boxes[1] = boxes[0];
System.out.println(boxes[0] == boxes[1]); // true
~~~

Đây là đoạn minh họa với class `Box` đã định nghĩa, cần đặt trong method. `new Box[2]` **chỉ tạo mảng chứa hai reference elements mặc định null**. Phải gọi `new Box(...)` riêng nếu muốn tạo Box instances. Gán phần tử thứ hai bằng phần tử thứ nhất tạo **aliasing giữa hai slots trong một array**.

Sơ đồ:

~~~text
boxes ------> [Box[] array length=2]
                   [0] ---+
                           +--> [Box value=10]
                   [1] ---+
~~~

Việc thay `boxes[0].value = 20` khiến lần đọc `boxes[1].value` trả 20, do cùng object.

### Độ dài mảng và kích thước dữ liệu

- `array.length` có giá trị cố định cho **array object đó** sau cấp phát.
- Ta có thể gán lại biến tham chiếu: `array = new int[10];` trỏ sang array object mới, không làm “nở” chính array cũ.
- `new int[-1]` ném `NegativeArraySizeException`; không tạo array.
- Truy cập ngoài đoạn `0..length-1` ném `ArrayIndexOutOfBoundsException`.
- Truy cập `arr.length` khi `arr == null` ném `NullPointerException`.
- Array object cũng có type và các members theo quy tắc Java. `length` không phải một mutable instance field user-defined; ở bytecode nó được đọc bằng opcode **`arraylength`**, không phải `getfield` thông thường.

## 8. Mảng hai chiều thực chất là mảng của mảng

Khi viết:

~~~java
int[][] table = new int[2][3];
~~~

theo mô hình Java, `table` tham chiếu **array ngoài** gồm hai references tới **hai mảng int[] bên trong**, mỗi mảng trong dài 3. Java hỗ trợ các mảng không đều (*jagged arrays*).

~~~text
table ---> int[][] outer array, length=2
                |
                +-- [0] ---> int[] length=3: [0, 0, 0]
                |
                +-- [1] ---> int[] length=3: [0, 0, 0]
~~~

Có **ba array objects** về mặt ngữ nghĩa: một outer array và hai inner arrays. Không được suy luận chắc chắn rằng dữ liệu mảng hai chiều phải nằm thành một ma trận chữ nhật liên tục về địa chỉ vật lý.

Đặc biệt:

~~~java
int[][] rows = new int[2][];
System.out.println(rows[0] == null); // true
rows[0] = new int[] {7};
rows[1] = new int[] {8, 9};
System.out.println(rows[0].length);  // 1
System.out.println(rows[1].length);  // 2
~~~

Đây là snippet trong method. `new int[2][]` chỉ tạo **outer array**, chưa tự cấp phát inner arrays. Cách này tạo mảng các hàng có độ dài khác nhau.

### Array covariance và runtime store check

Reference arrays trong Java là **covariant**. Ví dụ, `String[]` có thể được gán vào biến kiểu `Object[]`:

~~~java
Object[] items = new String[1];
items[0] = "ok";
~~~

Điều đó hợp lệ; nhưng:

~~~java
Object[] items = new String[1];
// items[0] = Integer.valueOf(3); // ArrayStoreException ở runtime.
~~~

Đây là đoạn minh họa, dòng exception được comment để không làm hỏng một chương trình chạy bình thường. Dù **biến** khai báo là `Object[]`, **object mảng thực tế** có component type `String`. JVM kiểm tra việc gán phần tử tham chiếu theo kiểu mảng runtime, nên cố đặt Integer sẽ ném `ArrayStoreException`.

Mảng primitive không có covariance kiểu tương tự: `int[]` không thể gán vào `Object[]`, dù chính `int[]` là một object và có thể gán vào biến `Object`.

## 9. Ví dụ Java 17+ hoàn chỉnh: mảng primitive, tham chiếu và mảng nhiều chiều

Tạo tệp **`HeapArrayDemo.java`**:

~~~java
import java.util.Arrays;

public class HeapArrayDemo {
    static final class Node {
        int number;

        Node(int number) {
            this.number = number;
        }
    }

    public static void main(String[] args) {
        int[] primitives = new int[3];
        Node[] references = new Node[2];

        System.out.println("primitiveDefault=" + primitives[1]);
        System.out.println("referenceDefault=" + (references[0] == null));

        Node node = new Node(6);
        references[0] = node;
        references[1] = node;
        references[0].number = 10;

        System.out.println("sameNode=" + (references[0] == references[1]));
        System.out.println("nodeValue=" + references[1].number);

        int[][] rows = new int[2][];
        System.out.println("unallocatedRow=" + (rows[0] == null));

        rows[0] = new int[] {7};
        rows[1] = new int[] {8, 9};
        System.out.println("rowSizes=" + rows[0].length + "," + rows[1].length);
        System.out.println("row0=" + Arrays.toString(rows[0]));

        Object[] covariant = new String[1];
        covariant[0] = "ok";

        try {
            covariant[0] = Integer.valueOf(3);
        } catch (ArrayStoreException expected) {
            System.out.println("storeCheck=ArrayStoreException");
        }
    }
}
~~~

Lệnh:

~~~bash
javac --release 17 HeapArrayDemo.java
java HeapArrayDemo
~~~

**Stdout chính xác:**

~~~text
primitiveDefault=0
referenceDefault=true
sameNode=true
nodeValue=10
unallocatedRow=true
rowSizes=1,2
row0=[7]
storeCheck=ArrayStoreException
~~~

Giải thích:
- `new int[3]` cấp phát array object với int elements có default 0.
- `new Node[2]` cấp phát array object với reference elements default null; chỉ `new Node(6)` mới tạo Node instance.
- Hai reference elements cùng giữ tham chiếu đến một Node, nên thay qua phần tử 0 nhìn thấy qua phần tử 1.
- Outer array `new int[2][]` có phần tử null cho đến khi được gán inner arrays.
- Runtime type của `covariant` là `String[]` dù kiểu biến `Object[]`, nên Integer store bị chặn.

**Không phụ thuộc** vào GC hay JIT mode để có stdout như trên.

## 10. Biến `final` không khiến object bất biến

Một reference variable/field có thể là `final`, ví dụ:

~~~java
final int[] numbers = {1, 2, 3};
numbers[0] = 99; // Hợp lệ.
// numbers = new int[3]; // Không hợp lệ: reassign biến final.
~~~

Đây là snippet trong một phương thức. `final` đối với biến tham chiếu **ngăn gán lại chính biến**, không tự bảo đảm object mà nó tham chiếu là immutable.

Với class:

~~~java
class Holder {
    final int[] data = new int[2];
}
~~~

Một biến/field khác vẫn có thể nắm reference đến cùng array và thay đổi phần tử, trừ khi thiết kế phòng thủ. Để cung cấp bất biến thực tế, cần xem toàn bộ thiết kế: defensive copy, API không phơi bày mutable internals, immutable value types và quy tắc đồng thời thích hợp.

Tương tự, `final Box box` có thể giữ reference ổn định nhưng `box.value` vẫn có thể thay đổi nếu `Box` là kiểu mutable.

## 11. Sao chép mảng và sao chép object

**Sao chép reference** ≠ **sao chép object**. Và **clone array** thường là **shallow copy** với reference elements.

~~~java
Node[] original = {new Node(1)};
Node[] copy = original.clone();

System.out.println(original == copy);        // false
System.out.println(original[0] == copy[0]);  // true
~~~

Đây là snippet với class `Node` có constructor phù hợp trong một method. `clone()` trên array tạo array object mới và sao chép các element values. Vì element type là reference, value được sao chép chính là **reference tới Node**, nên cả hai arrays cùng trỏ tới Node đầu tiên.

Để deep-copy một object graph, cần chính sách sao chép các object bên trong theo domain. Không có một hành vi mặc định “gọi clone hoặc gán bằng” luôn deep-copy cả cây references. Với graph có chu trình hoặc shared subobjects, deep copy còn cần quy tắc giữ/không giữ sharing và theo dõi identity.

### Khác biệt giữa `Arrays.copyOf` và assignment

- `copied = original;` chỉ alias, không tạo array mới.
- `copied = Arrays.copyOf(original, original.length);` tạo array mới (đối với kiểu mảng phù hợp), nhưng reference elements vẫn là reference values được copy.
- `copied = original.clone();` tạo array mới với các element values copy.
- `new int[10]` tạo array giá trị mặc định, không copy dữ liệu cũ nếu không gán/copy phần tử.

## 12. GC và reachability: lúc nào object có thể thu hồi?

**Garbage collection (GC)** quản lý các object không còn cần thiết theo khả năng tiếp cận (*reachability*). Một object có thể được thu hồi khi không còn reachable từ các **GC roots** theo mô hình/thuật toán VM. JVM **không cam kết một thời điểm cụ thể** mà memory của một object sẽ được reclaim.

Các root hoặc nguồn giữ tham chiếu điển hình trong triển khai JVM gồm references còn sống trong các thread stacks/frames, static fields reachable qua class runtime, JNI/native handles và các cấu trúc runtime thích hợp. Danh sách root cụ thể và thuật toán liveness thuộc về VM/GC implementation; không coi một sơ đồ đơn giản là specification bắt buộc cho mọi collector.

Ví dụ:

~~~java
Box a = new Box(1);
Box b = a;            // Hai references cùng object
a = null;             // b vẫn trỏ đến Box.
b.value = 2;          // Box vẫn sử dụng được.
b = null;             // Không còn reference qua hai biến này.
~~~

Đây là đoạn minh họa trong phương thức. Sau `a = null`, object **vẫn reachable qua b**. Sau `b = null`, object *có thể* không còn reachable, **nếu không còn tham chiếu khác** và JVM không giữ reference live vì một mục đích phù hợp. Không được kết luận rằng ngay tại dấu chấm phẩy ấy heap memory phải lập tức được trả về hệ điều hành.

### Những hiểu nhầm về GC

- `reference = null` **không gọi trực tiếp deallocation**; nó chỉ thay đổi một reference variable/field.
- Một object không nhất thiết mất đi khi biến local ra khỏi scope: reference có thể được lưu ở static field, object khác, array hoặc nơi khác.
- Một object còn nằm trong biến trên source không nhất thiết buộc JVM luôn giữ object tới hết method nếu variable không còn được dùng về mặt thực thi; GC/JIT có thể phân tích liveness.
- Java không bảo đảm thứ tự hay thời điểm finalization hoặc GC; **không thiết kế logic nghiệp vụ dựa trên thời điểm thu hồi**.
- `System.gc()` chỉ là **yêu cầu/gợi ý** GC theo API/VM configuration, không phải cam kết thu hồi ngay một object cụ thể.
- Memory leak vẫn có thể xảy ra theo nghĩa **reference vô tình giữ object còn reachable**, ví dụ static cache không dọn, collection tích lũy, listener không unregister, thread-local giữ dữ liệu lâu.

### WeakReference không phải phép đo thời gian thu gom

`WeakReference<T>` cho phép tham chiếu yếu với semantics riêng, nhưng thời điểm referent bị clear/collect **không xác định trước**. Vì vậy không dùng:

~~~java
System.gc();
// System.out.println(weak.get() == null); // Không có kết quả stdout bảo đảm.
~~~

Đây là snippet minh họa và dòng kiểm tra được comment. Nếu cần quản lý **resource bên ngoài heap** như socket/file, dùng try-with-resources hoặc API close phù hợp; **đừng chờ GC** để đóng tài nguyên đúng hạn.

## 13. Object graph, vùng nhớ và memory leak

Object chứa reference fields và reference arrays tạo một **đồ thị tham chiếu** trên heap:

~~~text
GC root: static Registry
          |
          v
      [Registry object]
          |
          +--> list --------> [ArrayList backing array]
                                  |
                                  +--> entry0 -> [Session object]
                                  +--> entry1 -> [Session object]
                                  +--> entry2 -> [Session object]
~~~

Nếu application quên remove các Session hết hạn khỏi registry, các object có thể vẫn reachable và GC không thể thu hồi chúng như “rác”, dù business logic không còn cần. Đây là **logical memory leak**.

Nguyên tắc:
1. Xác định **ai sở hữu** references tới object.
2. Tránh giữ các đối tượng lớn trong static caches không giới hạn.
3. Giới hạn eviction/TTL cho cache và xóa listeners/registrations khi không dùng.
4. Xem heap dump bằng profiler/diagnostic tools khi cần để tìm retainers và đường đi từ GC roots.
5. Không xem việc đặt một local reference về null là giải pháp chữa leak nếu còn references lâu dài ở nơi khác.

Với quy trình kiểm tra, dùng dữ liệu thực tế (số instances, retained heap, GC roots) thay vì chỉ nhìn số lần mã nguồn gọi `new`.

## 14. JIT, escape analysis và giới hạn của câu “object luôn ở heap”

**Ở cấp đặc tả JVM**, heap là vùng runtime mà các class instances và arrays được cấp phát về mặt ngữ nghĩa. Nhưng triển khai JVM hiện đại có thể tối ưu khi kết quả **không làm thay đổi hành vi quan sát được**.

Ví dụ:

~~~java
static int total(int a, int b) {
    Pair pair = new Pair(a, b);
    return pair.first + pair.second;
}

static final class Pair {
    final int first;
    final int second;

    Pair(int first, int second) {
        this.first = first;
        this.second = second;
    }
}
~~~

Đây là **đoạn minh họa cần đặt trong class**. Trong mô hình Java, `new Pair` tạo instance. Một JVM JIT có thể phân tích escape và loại bỏ cấp phát object vật lý bằng **scalar replacement**, vì chỉ cần giá trị hai fields cho kết quả. Tuy nhiên:
- **Không được khẳng định** JIT chắc chắn tối ưu ví dụ này trong mọi lần chạy, JVM, cấu hình hoặc compilation tier.
- Sự tối ưu hóa không làm sai identity/equality hay thay đổi side effects cần quan sát.
- Không nên mô tả chắc chắn “object Pair chuyển sang stack” chỉ vì escape analysis. JVM có thể loại bỏ allocation, scalarize hoặc dùng chiến lược khác; “stack allocation” không phải một ngữ nghĩa Java công khai bắt buộc.
- Khi object escape sang thread khác, được trả về hoặc được dùng theo cách identity có thể quan sát, điều kiện tối ưu hóa khác nhau.

Vì vậy câu học liệu chính xác là: **JVM mô hình hóa class instances và arrays ở heap; nơi lưu trữ vật lý thực tế chịu các tối ưu hợp lệ**. Cách nói “mọi object Java bắt buộc luôn chiếm một khối RAM heap riêng” là quá cứng đối với JIT.

## 15. Static reference cũng có thể trỏ đến object trên heap

Ví dụ:

~~~java
class AppState {
    static final int LIMIT = 100;
    static Box current = new Box(7);
}
~~~

Đây là class minh họa. Hãy phân biệt:
- `LIMIT` là static primitive field (và có thể là constant variable), không phải heap object Integer.
- `current` là **static reference field** thuộc class runtime.
- Biểu thức `new Box(7)` tạo Box object theo ngữ nghĩa trên heap.
- Field `current` giữ giá trị reference tới Box, không chứa toàn bộ object Box.
- Nếu `current` tiếp tục giữ reference tới Box, object đó có thể còn reachable qua static state, làm ảnh hưởng thời gian sống.

Việc field static có thể được JVM quản lý trong runtime data structures nào là chi tiết thực thi. Không được coi biến static như “một object nằm trên heap” chỉ vì static field có kiểu reference.

### Object references có thể nằm trong heap

Với:

~~~java
class Node {
    Node next;
    int value;
}
~~~

một Node object có field `next` kiểu reference **nằm trong chính Node object**; Node object theo mô hình JVM nằm trên heap. Vì vậy không phải **mọi reference** đều “nằm trên stack”. Reference values có thể nằm trong object fields, array elements, static fields hoặc local frames.

## 16. Bytecode Java liên quan đến heap và reference values

Compiler Java thường sinh các opcode sau khi tạo/truy cập object và array:

| Opcode | Vai trò | Ví dụ Java |
| --- | --- | --- |
| `new` | Tạo class instance chưa hoàn tất constructor initialization | `new Box(5)` |
| `invokespecial` | Gọi constructor `<init>` trong quy tắc tương ứng | `new Box(5)` |
| `newarray` | Tạo array một chiều của primitive | `new int[3]` |
| `anewarray` | Tạo array của reference component type | `new Box[2]` |
| `multianewarray` | Tạo mảng nhiều chiều với những chiều được chỉ định | `new int[2][3]` |
| `aload` / `astore` | Nạp/lưu **reference value** từ/vào local variable | `Box b = ...` |
| `getfield` / `putfield` | Đọc/ghi instance field theo symbolic reference | `b.value` |
| `getstatic` / `putstatic` | Đọc/ghi static field | `AppState.current` |
| `aaload` / `aastore` | Đọc/ghi reference elements trong array | `boxes[0]` |
| `iaload` / `iastore` | Đọc/ghi int elements trong array | `numbers[0]` |
| `arraylength` | Đọc độ dài array | `arr.length` |
| `if_acmpeq` / `if_acmpne` | So sánh hai reference values theo identity | `a == b` |
| `ifnull` / `ifnonnull` | Kiểm tra reference bằng null | `b == null` |
| `checkcast` / `instanceof` | Kiểm tra/chuyển kiểu reference theo quy tắc JVM | `(Box)obj`, `obj instanceof Box` |

Một đoạn disassembly minh họa:

~~~text
new           #7     // class Box
dup
iconst_5
invokespecial #9     // Box.<init>:(I)V
astore_1             // Lưu reference vào local variable
aload_1              // Nạp reference từ local variable
getfield      #12    // Box.value:I
~~~

Chỉ số `#7/#9/#12` là **minh họa**, không phải chỉ số cố định. Instruction `new` tạo instance; `dup` giữ reference phù hợp để constructor call và assignment; `astore` lưu reference value trong slot, **không sao chép object Box**.

Với array:

~~~text
iconst_3
newarray int
astore_2

aload_2
iconst_0
iaload
~~~

Đây cũng là sơ đồ bytecode, không phải dump exact. Nó cho thấy `newarray` tạo array object; `astore_2` chỉ lưu reference; `iaload` đọc int element.

### Thực hành bằng javap

Sau khi biên dịch các ví dụ trên:

~~~bash
javap -c -p HeapReferenceDemo
javap -c -p HeapArrayDemo
javap -v -p HeapReferenceDemo
~~~

Quan sát trong `main`:
1. Các instruction `new`/`invokespecial` để tạo Box/Node.
2. `astore`/`aload` khi gán hoặc truyền reference values.
3. `getfield`/`putfield` khi đọc/ghi field primitive của Box/Node.
4. `newarray`, `anewarray` và các opcode nạp/ghi phần tử.
5. `if_acmp*` hoặc `ifnull/ifnonnull` trong các phép kiểm tra reference.
6. Các lời gọi như `Arrays.toString` hay `PrintStream.println` dùng opcode invoke, không được nhầm với instruction field/array access.

Đừng ép quan hệ “mỗi biểu thức Java = một opcode JVM”: compiler có thể constant-fold, dùng các chuỗi instruction phụ, hoặc JIT tối ưu khi thực thi. Điều JVM cần bảo đảm là **semantics** của chương trình.

## 17. Heap sizing, GC và các công cụ chẩn đoán

Trong HotSpot/JDK phổ biến, bạn có thể cấu hình giới hạn heap bằng các tham số như:
- `-Xms<size>`: heap initial size (theo JVM implementation).
- `-Xmx<size>`: heap maximum size.
- `-Xlog:gc` hoặc `-Xlog:gc*`: log hoạt động GC (với unified logging của HotSpot/JDK hiện đại).

Ví dụ minh họa (không có stdout cố định vì phụ thuộc collector và chương trình):

~~~bash
java -Xms64m -Xmx256m -Xlog:gc -cp . HeapReferenceDemo
~~~

Thông tin giám sát có thể dùng thêm:
- **JFR (Java Flight Recorder)** để khảo sát allocation và hành vi GC.
- **JDK Mission Control** hoặc profiler phù hợp để xem heap usage và retained objects.
- **jcmd** với diagnostic commands hỗ trợ trên JVM cụ thể; cú pháp/khả dụng phụ thuộc phiên bản.
- **Heap dump** để điều tra object graph, classloader và đường đến GC roots; cần chú ý dữ liệu nhạy cảm trong dump.

Cần phân biệt các tình huống:
- `java.lang.OutOfMemoryError: Java heap space` thường chỉ ra heap không cấp phát đủ cho yêu cầu tại thời điểm đó, nhưng nguyên nhân có thể là heap hạn chế, allocation peak hoặc object còn được giữ lâu.
- Không phải mọi `OutOfMemoryError` đều xuất phát từ Java heap: native memory, metaspace, direct buffers, thread creation... có thể liên quan.
- Tăng `-Xmx` có thể che triệu chứng chứ không giải quyết object retention/leak; cần đo **retained heap** và reference paths.
- Memory “không giảm ngay trên OS” không chứng minh object còn alive: JVM có thể giữ lại committed heap để tái sử dụng.

## 18. Những ngộ nhận phổ biến

| Nhận định | Cách hiểu đúng |
| --- | --- |
| “`Box a = new Box()` nghĩa là toàn bộ Box nằm ngay trong biến a trên stack.” | Biến a giữ **reference value**; object được cấp phát theo ngữ nghĩa heap. |
| “Gán `b = a` tạo một bản copy Box mới.” | Chỉ sao chép reference; a và b có thể alias cùng object. |
| “Java truyền object theo reference nên callee gán tham số sẽ đổi biến caller.” | Java **pass-by-value**; callee chỉ nhận bản sao reference. |
| “Hai object có field bằng nhau nên `==` là true.” | `==` trên references kiểm tra identity; equality logic phải dùng method thích hợp. |
| “`new Box[5]` tạo năm Box instances.” | Chỉ tạo một array chứa 5 references default null. |
| “Array primitive chứa các Integer/Double objects.” | `int[]` chứa int values; `double[]` chứa double values, không boxing mỗi phần tử. |
| “Array 2D là một object ma trận duy nhất.” | Theo mô hình Java, là mảng của references tới các mảng con; độ dài hàng có thể khác nhau. |
| “`final Box b` làm Box immutable.” | Final ngăn reassign biến/field; Box có thể mutable. |
| “Clone reference array là deep copy toàn bộ objects.” | Mặc định shallow copy element references. |
| “`reference = null` lập tức giải phóng heap.” | Chỉ thay reference; GC quyết định lúc thu gom dựa reachability. |
| “Ra khỏi method thì object bị hủy cùng frame.” | Frame kết thúc, object có thể vẫn reachable từ nơi khác. |
| “Mọi reference luôn ở stack.” | Reference values có thể nằm trong fields, static fields và array elements. |
| “Mọi object vật lý bắt buộc ở heap với một địa chỉ cố định.” | JVM semantics đặt objects ở heap, JIT có thể tối ưu allocation/scalar replacement. |
| “Một static reference ở class là chính object mà nó chỉ tới.” | Static field chứa reference; referent là object riêng. |
| “Heap shared có nghĩa đa luồng sửa object luôn thread-safe.” | Shared heap không bảo đảm atomicity/visibility; cần Java Memory Model và synchronization phù hợp. |
| “`System.gc()` bảo đảm object biến mất ngay.” | Chỉ là gợi ý; GC timing không xác định. |

## 19. Tự kiểm tra kiến thức

**Câu 1.** `Box a = new Box(1); Box b = a;` có bao nhiêu Box instances mới được tạo?

**Đáp án:** **Một**, từ biểu thức `new Box(1)`. `b = a` chỉ sao chép reference value.

**Câu 2.** Nếu `b.value = 5`, `a.value` sẽ bằng bao nhiêu trong ví dụ trên?

**Đáp án:** **5**, vì cả hai variables tham chiếu cùng Box object (khi chạy tuần tự, không có thay đổi khác).

**Câu 3.** Tại sao method `rebind(Box b) { b = new Box(9); }` không đổi tham chiếu caller?

**Đáp án:** Java pass-by-value: tham số b chỉ là **bản sao reference**. Gán lại tham số không đổi biến nguồn trong caller.

**Câu 4.** `Box[] boxes = new Box[3];` tạo ba Box objects hay không?

**Đáp án:** **Không.** Nó tạo một Box[] array object với ba element references mặc định null.

**Câu 5.** `int[] xs = new int[4];` chứa bốn Integer objects?

**Đáp án:** **Không.** Chứa bốn primitive int values có default 0.

**Câu 6.** `int[][] grid = new int[2][3];` có bao nhiêu array objects theo semantics thông thường?

**Đáp án:** **Ba**: một outer array length 2 và hai inner int arrays length 3.

**Câu 7.** `int[][] grid = new int[2][];` thì sao?

**Đáp án:** Ban đầu có **một outer array**, hai reference elements của nó là null, chưa có inner arrays.

**Câu 8.** `a == b` và `a.equals(b)` có cùng ý nghĩa đối với references không?

**Đáp án:** Không. `==` so identity; `equals` là phương thức có thể được override để so nội dung, tùy class.

**Câu 9.** Đặt biến `a = null` khi vẫn có `b` trỏ cùng object sẽ giải phóng object chứ?

**Đáp án:** Không. Object vẫn reachable qua b; dù không còn reference nào, GC cũng không cam kết thu hồi ngay.

**Câu 10.** Reference nào có thể nằm trong heap?

**Đáp án:** Reference values trong **instance fields và reference-array elements** có thể nằm trong heap objects. Không phải mọi reference đều chỉ nằm trong stack frames.

**Câu 11.** JIT scalar replacement có làm Java “không còn heap” không?

**Đáp án:** Không. Heap là thành phần của mô hình JVM; các tối ưu chỉ được thực hiện khi bảo toàn semantics quan sát được, và không có bảo đảm áp dụng mọi object.

**Câu 12.** `final int[] numbers` làm gì?

**Đáp án:** Ngăn gán lại reference variable/field phù hợp, nhưng **không ngăn thay đổi elements** của array.

**Câu 13.** Vì sao `Object[] objects = new String[1]` có thể ném `ArrayStoreException`?

**Đáp án:** Runtime array object thực sự có component type String; JVM kiểm tra element store, không chỉ dựa vào kiểu khai báo Object[] của biến.

**Câu 14.** Biến `static Box shared` có phải Box object được đặt trong static field không?

**Đáp án:** Không. Static field lưu **reference value**. Referent Box object là một thực thể riêng theo mô hình heap.

**Câu 15.** Heap shared giữa các thread có bảo đảm `counter++` trên field của object được thực thi nguyên tử?

**Đáp án:** Không. Phép đọc–tính–ghi cần đồng bộ hoặc atomic operations khi có concurrent updates.

## 20. Bản đồ ghi nhớ

~~~text
                    JVM RUNTIME DATA AREAS
                +----------------------------+
                | HEAP (được các thread share)|
                |  - Class instances         |
                |  - Array objects           |
                |  - Object graphs           |
                +----------------------------+
                     ^                ^
                     |                |
       reference value                reference value
                     |                |
   +-----------------+----+       +---+------------------+
   | THREAD A / FRAME     |       | STATIC FIELD /      |
   | local variable       |       | INSTANCE REF FIELD  |
   | operand stack        |       | / ARRAY REF ELEMENT |
   +----------------------+       +----------------------+

new Box()       -> class instance trên heap (ngữ nghĩa)
new Box[3]      -> array object, ba refs null
new int[3]      -> array object, ba primitive ints 0
b = a           -> copy reference, KHÔNG copy object
b.value = 10    -> mutate object được reference chỉ tới
method(b)       -> copy reference value vào parameter
b = null        -> đổi reference, KHÔNG immediate free
GC              -> dựa reachability, không theo 1 dấu chấm phẩy
JIT             -> có thể tối ưu allocation, bảo toàn semantics
~~~

**Kết luận:** **Đối tượng/mảng** và **biến tham chiếu** là hai khái niệm tách biệt. Heap lưu class instances và arrays theo mô hình JVM; references có thể nằm ở local frames, fields hoặc array elements. Hiểu aliasing, truyền tham số theo giá trị, identity, array semantics và GC reachability giúp giải thích đúng hành vi Java và tránh lỗi thiết kế bộ nhớ.

## Tài liệu tham khảo chuẩn

- [JVMS Java SE 21 — §2.5.3 Heap](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.5.3).
- [JVMS Java SE 21 — §2.5.2 Java Virtual Machine Stacks](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.5.2).
- [JVMS Java SE 21 — §2.6 Frames](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.6).
- [JVMS Java SE 21 — §2.4 Reference Types and Values](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.4).
- [JVMS Java SE 21 — §6.5 Instructions](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html#jvms-6.5).
- [JLS Java SE 21 — §4.3 Reference Types and Values](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.3).
- [JLS Java SE 21 — §10 Arrays](https://docs.oracle.com/javase/specs/jls/se21/html/jls-10.html).
- [JLS Java SE 21 — §15.9 Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.9).
- [JLS Java SE 21 — §12.6 Finalization of Class Instances](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.6).
- [JDK 21 — javap](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html).
