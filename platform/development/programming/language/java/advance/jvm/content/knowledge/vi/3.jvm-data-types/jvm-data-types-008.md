# Giá trị Java, tham chiếu JVM và địa chỉ vật lý: những khái niệm cần phân biệt

## 1. Ba tầng khái niệm khác nhau

Một lỗi tư duy thường gặp khi học JVM là dùng các từ **giá trị**, **tham chiếu** và **địa chỉ** như thể chúng đồng nghĩa. Chúng nằm ở các tầng khác nhau:

1. **Giá trị theo ngôn ngữ Java:** thứ một biểu thức tính ra hoặc một biến lưu được. Giá trị có thể là **primitive value** như `int`, `boolean`, `double`, hoặc là **reference value** như tham chiếu tới một `String`, `Box` hay mảng; biến tham chiếu còn có thể chứa `null`.
2. **Tham chiếu ở mô hình JVM:** giá trị thuộc nhóm reference, dùng để biểu thị một đối tượng/mảng mà các instruction và runtime xử lý. Đặc tả quy định ngữ nghĩa của việc tham chiếu, so sánh, gán, truy cập và ném `NullPointerException`, **không buộc mọi JVM triển khai reference như một con trỏ máy thuần túy**.
3. **Địa chỉ bộ nhớ ở tầng triển khai và phần cứng:** nơi dữ liệu được đặt hoặc ánh xạ trong **không gian địa chỉ ảo của tiến trình**, rồi có thể được hệ điều hành ánh xạ tới trang vật lý. Chi tiết này phụ thuộc JVM, JIT, garbage collector, hệ điều hành và cấu hình máy. Java thông thường **không có API công khai bảo đảm đưa ra địa chỉ vật lý của object**.

Ví dụ:

~~~java
int age = 25;
String name = new String("JVM");
String alias = name;
~~~

- `age` chứa **giá trị primitive** `25`.
- `name` chứa **giá trị tham chiếu** tới một đối tượng `String`.
- `alias = name` sao chép **giá trị tham chiếu**: hai biến cùng tham chiếu một đối tượng, **không** sao chép đối tượng `String` thành đối tượng mới.
- Không dòng nào cho phép suy ra “địa chỉ RAM vật lý” của đối tượng `String`. Dấu `=` ở Java biểu thị phép gán giá trị, không phải lời hứa rằng vị trí bộ nhớ được cố định.

Cần giữ một câu làm mốc: **tham chiếu cũng là một giá trị Java, nhưng giá trị tham chiếu không phải địa chỉ vật lý có thể sử dụng như số nguyên**.

## 2. Giá trị primitive, giá trị tham chiếu và `null`

### 2.1. Kiểu primitive

Java có tám kiểu primitive: `boolean`, `byte`, `short`, `char`, `int`, `long`, `float`, `double`. Biến thuộc một kiểu primitive lưu một giá trị của kiểu ấy theo quy tắc Java. Khi gán `int b = a;`, chương trình sao chép **giá trị số** hiện thời, nên đổi `b` không đổi `a`.

Không nhầm **độ rộng kiểu ở ngôn ngữ** với **kích thước ô nhớ thực tế**. Chẳng hạn `int` là kiểu số nguyên 32 bit của Java, nhưng cách JVM dùng thanh ghi, slot local variable, alignment và layout trong object là vấn đề triển khai. JVM dùng những computational type riêng trên operand stack; một số phép tính `byte`, `short`, `char`, `boolean` được thực hiện qua dạng `int` theo instruction tương ứng. Không suy luận “mỗi biến Java luôn chiếm đúng từng ấy byte RAM tại một địa chỉ cố định”.

### 2.2. Kiểu tham chiếu

Trong Java 17, các kiểu **class**, **interface** và **array** là reference type. Ví dụ `String`, `List<String>`, `int[]`, `Object` và `Box` đều thuộc nhóm này. Một biến có kiểu tham chiếu giữ một reference value tới một object tương thích kiểu, hoặc `null`. Mảng **là object**, kể cả `int[]`: phần tử của nó là các giá trị `int`, còn biến `int[]` là tham chiếu tới đối tượng mảng.

Cần tách **kiểu khai báo** khỏi **kiểu runtime**:

~~~java
Object item = new StringBuilder("x");
~~~

Biến `item` có kiểu khai báo `Object`, giá trị hiện tại tham chiếu tới object mà lớp runtime là `StringBuilder`. `Object` không có nghĩa biến chứa toàn bộ object ngay trong slot biến.

### 2.3. `null` không phải một object

`null` là một giá trị đặc biệt có thể gán cho biến reference. Nó biểu thị không tham chiếu tới object nào; không có class instance tên `null`. Gọi instance method hoặc truy cập instance field qua giá trị `null` sẽ gây `NullPointerException` tại thao tác cần dereference.

~~~java
String value = null;
System.out.println(value == null); // true
// value.length(); // nếu chạy: NullPointerException
~~~

Đừng diễn dịch `null` thành “địa chỉ vật lý 0” theo chuẩn Java. JVM implementation có thể dùng một biểu diễn tiện lợi cho null bên trong, nhưng đặc tả không cấp cho chương trình Java quyền thao tác địa chỉ ấy.

## 3. Mô hình tham chiếu của JVM: hợp đồng ngữ nghĩa, không phải pointer arithmetic

Đặc tả JVM phân loại giá trị thành primitive và reference. JVM reference value có thể biểu thị một instance của class, một instance của array, hoặc giá trị `null` đặc biệt. Bytecode sử dụng giá trị tham chiếu trong nhiều thao tác như:

| Instruction / nhóm instruction | Ngữ nghĩa ở JVM |
| --- | --- |
| `aconst_null` | Đẩy `null` lên operand stack |
| `new` | Tạo một class instance, trả về tham chiếu chưa khởi tạo đầy đủ ở mức verification cho tới khi constructor chạy |
| `aload`, `astore` | Nạp/lưu reference value qua local variables |
| `getfield`, `putfield` | Đọc/ghi instance field thông qua một tham chiếu object |
| `aaload`, `aastore` | Đọc/ghi phần tử tham chiếu trong mảng reference |
| `if_acmpeq`, `if_acmpne` | So sánh hai giá trị reference về cùng object hay không |
| `checkcast`, `instanceof` | Kiểm tra quan hệ kiểu runtime dựa trên object được tham chiếu |

Đây là những thao tác có **ý nghĩa do JVM định nghĩa**. Chúng không tương đương việc cộng/trừ số byte vào pointer kiểu C. Java cũng không cho dùng `+ 8` với một reference để “chuyển sang field kế tiếp”. Thậm chí `new` không cam kết một lệnh cấp máy duy nhất luôn cấp phát tại một địa chỉ cụ thể: JIT có thể tối ưu hoặc GC có thể thay đổi vị trí lưu trữ.

Một class file mô tả loại giá trị bằng **descriptor**, ví dụ:

| Descriptor | Kiểu hoặc ý nghĩa |
| --- | --- |
| `I` | primitive `int` |
| `D` | primitive `double` |
| `Z` | primitive `boolean` |
| `Ljava/lang/String;` | reference tới `java.lang.String` |
| `[I` | reference tới một mảng `int[]` |
| `[Ljava/lang/String;` | reference tới một mảng `String[]` |
| `(I)Ljava/lang/String;` | method nhận `int`, trả tham chiếu `String` |

Descriptor diễn tả **loại giá trị** theo hợp đồng nhị phân JVM, không chỉ ra object nằm ở địa chỉ vật lý nào.

## 4. Gán giá trị, aliasing và quy tắc pass-by-value của Java

Java **luôn truyền đối số theo giá trị** (*pass-by-value*). Điểm hay gây nhầm lẫn là khi đối số là biến reference, **giá trị được sao chép chính là reference value**.

### 4.1. Biến primitive: sao chép giá trị, không nối hai biến

~~~java
int a = 10;
int b = a;
b = 20;
// a vẫn là 10; b là 20
~~~

Không tồn tại liên kết ngầm khiến đổi `b` làm đổi `a`. Mỗi biến biểu diễn một vị trí giá trị ở mức ngôn ngữ, dù JVM/JIT có thể tối ưu biểu diễn vật lý.

### 4.2. Biến reference: sao chép tham chiếu, có thể cùng object

~~~java
StringBuilder first = new StringBuilder("A");
StringBuilder second = first;

second.append("B");
// first.toString() và second.toString() đều là "AB"
~~~

Hai biến `first` và `second` cùng tham chiếu một `StringBuilder` **mutable**. `append()` thay đổi trạng thái của object chung. Nếu viết `second = new StringBuilder("X");` thì chỉ **gán lại biến second** sang object mới, không đổi biến `first` hay object cũ.

~~~text
Biểu diễn khái niệm, KHÔNG phải sơ đồ địa chỉ thật:

Biến/slot first ───┐
                   ├────> Object A: StringBuilder("AB")
Biến/slot second ──┘

Sau second = new StringBuilder("X"):

first ─────────────────> Object A: StringBuilder("AB")
second ────────────────> Object B: StringBuilder("X")
~~~

Một số đối tượng như `String` là bất biến theo API thông thường: phép nối `s = s + "!"` tạo kết quả `String` mới về mặt ngữ nghĩa và gán lại tham chiếu `s`; không chỉnh sửa ký tự của object cũ. Bất biến của object **không biến reference thành primitive**.

### 4.3. Tham số method cũng nhận một bản sao giá trị

~~~java
static void mutate(Box parameter) {
    parameter.count++;           // ghi trạng thái object chung
    parameter = new Box(100);    // chỉ đổi biến parameter cục bộ
}
~~~

Câu đầu làm object caller nhìn thấy thay đổi; câu thứ hai không thể đổi biến reference ở caller. Vì vậy cách nói “Java truyền object theo tham chiếu” dễ gây hiểu lầm: **Java truyền bản sao của reference value**, khác với cơ chế pass-by-reference có khả năng thay chính biến của caller.

## 5. Ví dụ Java 17+ biên dịch và chạy được

Tạo một tệp duy nhất tên `JvmValueReferenceDemo.java`:

~~~java
public class JvmValueReferenceDemo {
    static final class Box {
        int count;

        Box(int count) {
            this.count = count;
        }
    }

    static void incrementNumber(int value) {
        value++;
    }

    static void modifyAndReassign(Box parameter) {
        parameter.count++;
        parameter = new Box(99);
        parameter.count++;
    }

    public static void main(String[] args) {
        int original = 7;
        int copied = original;
        copied = 9;
        System.out.println("primitive values: " + original + ", " + copied);
        incrementNumber(original);
        System.out.println("primitive after call: " + original);

        Box first = new Box(10);
        Box alias = first;
        Box another = new Box(10);
        System.out.println("alias same object: " + (first == alias));
        System.out.println("another same object: " + (first == another));
        System.out.println("initial fields equal: " + (first.count == another.count));

        alias.count = 12;
        System.out.println("after alias writes: " + first.count);
        modifyAndReassign(first);
        System.out.println("after method call: " + first.count);
        System.out.println("other object: " + another.count);
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac --release 17 JvmValueReferenceDemo.java
java JvmValueReferenceDemo
~~~

**Stdout chính xác** của chương trình:

~~~text
primitive values: 7, 9
primitive after call: 7
alias same object: true
another same object: false
initial fields equal: true
after alias writes: 12
after method call: 13
other object: 10
~~~

Giải thích lần lượt:

1. `copied` nhận giá trị số 7 từ `original`, nhưng được đổi độc lập thành 9. `incrementNumber(original)` chỉ tăng bản sao `value`, nên `original` vẫn 7.
2. `first == alias` là `true` do hai biến cùng tham chiếu object Box đầu tiên.
3. `first == another` là `false` vì hai lệnh `new Box(10)` tạo hai object khác nhau về **identity**, dù ban đầu cùng `count = 10`.
4. Ghi `alias.count = 12` thay đổi object chung nên đọc `first.count` thấy 12.
5. Method nhận bản sao của tham chiếu `first`. Lệnh tăng `parameter.count` làm object đầu tiên thành 13; gán lại `parameter = new Box(99)` chỉ đổi tham số cục bộ. Object `another` vẫn 10.

Mã và stdout trên đã được kiểm tra bằng `javac --release 17` và chạy với JDK 21. Không hề dùng địa chỉ bộ nhớ để chứng minh hai tham chiếu cùng object: phép `==` với reference là đủ cho kiểm tra **identity**.

## 6. Object identity, nội dung logic và địa chỉ bộ nhớ là ba chuyện riêng

### 6.1. `==` và `equals()`

- Với hầu hết primitive, `==` so sánh **giá trị** (cần nhớ quy tắc đặc biệt của floating-point như `NaN != NaN`).
- Với hai biểu thức reference tương thích, `==` hỏi liệu chúng là `null` như nhau hoặc tham chiếu tới **cùng object**, không hỏi object nằm ở tọa độ RAM nào.
- `equals()` là phương thức Java: `Object.equals()` mặc định dùng identity, nhưng lớp con có thể override để định nghĩa **logical equality**. Ví dụ, `String.equals()` so nội dung ký tự; `StringBuilder` không override `equals()` để so nội dung.
- Với mảng, `array1.equals(array2)` mặc định vẫn là so identity; để so các phần tử mảng dùng `Arrays.equals` (hoặc `Arrays.deepEquals` cho cấu trúc lồng phù hợp).

~~~java
String a = new String("JVM");
String b = new String("JVM");
System.out.println(a == b);      // false: hai object riêng
System.out.println(a.equals(b)); // true: nội dung bằng nhau
~~~

**Không so nội dung String bằng `==`.** Literal String có thể được intern khiến hai biến tình cờ nhận cùng object; kết quả ấy không thay đổi nghĩa của `==` là so identity.

### 6.2. `hashCode()` và `System.identityHashCode()` không phải địa chỉ

`Object.toString()` mặc định thường có dạng `TenClass@maHex`. Phần mã hexa là biểu diễn hash code identity theo triển khai của `Object.toString()`, **không phải con trỏ hoặc địa chỉ RAM**. `System.identityHashCode(obj)` lấy hash code gắn với identity theo cơ chế JVM mà không gọi override `hashCode()` của lớp, song **không bảo đảm duy nhất**: hai object khác nhau có thể trùng hash code. Hash code có thể được giữ ổn định về ngữ nghĩa ngay cả khi GC di chuyển object.

~~~java
Object a = new Object();
Object b = new Object();

System.out.println(a == b);                    // false
System.out.println(System.identityHashCode(a)); // một số int, KHÔNG phải address
~~~

Giá trị số identity hash code phụ thuộc lần chạy/JVM, nên **không** viết một stdout cố định cho dòng hash code. Đừng dùng `hashCode()` hoặc `toString()` để suy ra physical address, kích thước object, hay thứ tự các object trong heap.

### 6.3. Wrapper, autoboxing và “value object”

Các lớp `Integer`, `Long`, `Boolean` là **class reference**, mặc dù chúng bọc giá trị primitive. Ví dụ `Integer x = 100;` sử dụng autoboxing; `x` là một biến reference tới wrapper object. Một số giá trị wrapper được cache theo quy tắc/implementation, nên `x == y` có thể cho kết quả khác mong đợi nếu dùng để so số. Dùng `equals()` hoặc unbox về primitive đúng cách khi mục tiêu là so **giá trị số**.

Một `record` Java 17 vẫn là **reference type có object identity**; từ “value-like” hoặc “immutable” trong thiết kế API không tự biến nó thành một primitive type. “Giá trị Java” trong bài này là giá trị tại mức ngôn ngữ/JVM, **không phải tên một cơ chế object layout cố định**.

## 7. Object, local variable và operand stack được mô hình hóa ở đâu?

Theo mô hình JVM, mỗi thread có stack chứa **frame** cho các lời gọi method. Mỗi frame có local-variable array và operand stack. Một local slot hoặc vị trí trên operand stack có thể chứa primitive value hoặc reference value tùy quy tắc instruction/verifier. Instance field của một object cũng có thể chứa primitive hoặc reference; các phần tử của reference array chứa reference value.

**Heap** là vùng runtime chung nơi các class instance và array object được cấp phát ở mức mô hình JVM. Tuy nhiên, các câu “primitive luôn ở stack” hay “reference luôn nằm trên stack” đều **sai**:

- Primitive có thể nằm trong local variable, trong field của một object trên heap hoặc trong phần tử `int[]`.
- Reference có thể nằm trong local variable, operand stack, field của object, static field hoặc phần tử `Object[]`.
- Một reference value có thể được giữ trong thanh ghi CPU hoặc được JIT xử lý bằng biểu diễn nội bộ tùy lúc.
- JIT có thể inline method, thực hiện escape analysis, scalar replacement hoặc loại bỏ một allocation không quan sát được. Vì thế mô hình “mọi `new` đều tạo object thực ở vị trí heap có thể đo ngay” không phải bảo đảm vật lý trong mọi lần chạy.

~~~text
Mô hình ngữ nghĩa, không mô tả byte/offset của JVM cụ thể:

Thread frame:                 Shared heap (mô hình):
  local primitive n = 7
  local reference x ──────────> Object A:
  local reference y ──────────>   int count = 13
  local reference z ──────────> Object B:
                                  int count = 10

Một object khác hoặc static field có thể lưu thêm reference tới Object A.
~~~

JVM garbage collector dựa trên **reachability** theo các root và quan hệ tham chiếu (cùng những quy tắc cụ thể của các kiểu tham chiếu như weak/soft/phantom khi có) để quản lý object. Đối tượng không còn được dùng hoặc trở nên unreachable **không nhất thiết bị thu gom ngay lập tức**. `System.gc()` chỉ là một yêu cầu/đề xuất tùy implementation, không phải lệnh bắt buộc giải phóng đúng object ngay lúc gọi.

### GC di chuyển object nhưng identity vẫn là identity

Nhiều collector có khả năng **di chuyển/compact** object để quản lý heap. Khi object được di chuyển, JVM và GC duy trì tính đúng đắn của những tham chiếu còn sống theo cơ chế nội bộ. Mã Java vẫn quan sát cùng object qua `==`, thay vì phải tự sửa các con trỏ. Cũng có collector hoặc giai đoạn không di chuyển object; không nói “mọi GC luôn dịch chuyển toàn bộ heap”.

Từ đó suy ra: giả sử JVM dùng một vị trí bộ nhớ để lưu object tại thời điểm T, không thể mặc định vị trí ấy luôn giữ nguyên tại T+1. **Định danh object không đồng nhất với vị trí byte trong RAM**.

## 8. Ba tầng địa chỉ: JVM reference, địa chỉ ảo và địa chỉ vật lý

Phân biệt rõ:

| Khái niệm | Ai định nghĩa và quản lý? | Java thông thường có thao tác như số địa chỉ không? |
| --- | --- | --- |
| **JVM reference value** | Hợp đồng JVM và biểu diễn nội bộ của implementation | **Không**; Java dùng thao tác kiểu object như dereference, method call, `==` |
| **Địa chỉ ảo của tiến trình** | CPU/OS cùng cơ chế virtual memory; JVM/native runtime dùng để lưu trữ | Không có API Java chuẩn thông thường trả địa chỉ ảo ổn định của managed object |
| **Địa chỉ vật lý của bộ nhớ** | Hệ điều hành/phần cứng ánh xạ các trang ảo tới bộ nhớ vật lý (nếu được resident) | **Không**; càng không phải giá trị của biến reference |

Thông thường chương trình native trên OS hiện đại làm việc với **địa chỉ ảo**, không trực tiếp với số địa chỉ RAM vật lý. Hệ điều hành có thể thay đổi ánh xạ tới trang vật lý, chuyển trang ra/vào hoặc dùng cơ chế quản lý bộ nhớ khác. Ngay cả giả sử có một pointer native trỏ tới vùng nhớ, nó **không tự đồng nghĩa physical address**.

Ở một số cấu hình HotSpot 64-bit, reference nội bộ có thể được biểu diễn bằng **compressed ordinary object pointer (compressed oop)** để giảm chi phí bộ nhớ. Trường hợp khác JVM có thể dùng biểu diễn khác (ví dụ địa chỉ trực tiếp, encoding, handle/indirection). Chi tiết phụ thuộc version, JVM, GC, kích thước heap và cấu hình; **không phải hợp đồng class-file/JLS**. Không phát biểu “reference Java luôn đúng 4 byte” hay “luôn đúng 8 byte”.

Một ví dụ tư duy: máy có thể thay đổi vị trí vật lý của trang RAM; GC có thể chuyển vị trí logic của object trong vùng nhớ tiến trình. Tất cả đều có thể xảy ra trong khi `referenceA == referenceB` vẫn là `true` nếu cả hai biểu thị cùng object. JVM đảm bảo **ngữ nghĩa tham chiếu** cho chương trình, không công khai bố trí vật lý.

### JNI, direct buffer và công cụ nội bộ không thay đổi hợp đồng Java

Java có thể tương tác với native memory qua JNI hoặc các API off-heap như `ByteBuffer.allocateDirect()`. Nhưng **native pointer, managed object reference và physical address** vẫn là những thứ khác nhau. Một direct buffer có thể dùng vùng nhớ ngoài Java heap, nhưng object `ByteBuffer` mà Java giữ vẫn là managed object. Các API nội bộ không được bảo đảm như `sun.misc.Unsafe` không phải cách dạy chuẩn để đổi reference thành địa chỉ vật lý, và phụ thuộc triển khai/version.

Cũng không nên dựa vào mẹo đo “địa chỉ” từ `System.identityHashCode`, debug `toString`, hoặc thông tin object layout nội bộ. Các giá trị ấy có mục đích riêng và không đại diện cho pointer ổn định, portable.

## 9. Java Memory Model: tính nhìn thấy và thứ tự khác với vị trí bộ nhớ

Khi nhiều thread cùng dùng một reference, Java Memory Model (JMM) tập trung vào **visibility, ordering và happens-before**, không đưa ra quy tắc “địa chỉ nào sẽ được ghi trước”. Việc hai thread có reference tới cùng object **không tự bảo đảm** rằng mọi đọc/ghi field mutable của object đều được đồng bộ đúng.

Ví dụ:

~~~java
final class State {
    int counter;
}

State shared = new State();
// Hai thread cùng gọi shared.counter++ mà không đồng bộ:
// có thể lost update vì phép tăng gồm nhiều bước.
~~~

Đoạn trên là **minh họa ý tưởng**, không phải một chương trình độc lập. Dù hai thread dùng chung reference, phép `counter++` không tự atomic. `volatile` giúp bảo đảm một số quan hệ visibility/ordering cho truy cập tới field tương ứng, nhưng `volatile int counter` vẫn **không làm phép `counter++` thành nguyên tử**. Có thể dùng `synchronized`, `AtomicInteger`, lock hoặc mô hình ownership phù hợp.

Đặc biệt: `volatile Box ref` là một trường reference volatile; nó có ngữ nghĩa đồng bộ khi đọc/ghi **chính biến ref**. Nó không biến mọi field mutable bên trong mọi object mà ref từng trỏ tới thành thread-safe. Phải xem cách object được công bố, cập nhật và đọc.

## 10. Các câu hỏi thực tiễn và sai lầm thường gặp

**Hỏi: “Object Java có nằm trên heap không?”** Ở **mô hình thực thi JVM**, class instance và array được cấp phát trong heap. Nhưng JVM/JIT có thể tối ưu biểu diễn vật lý hoặc loại bỏ allocation nếu ngữ nghĩa quan sát được không đổi. Không coi sơ đồ heap/stack sách giáo khoa là bản đồ địa chỉ chính xác ở mọi thời điểm.

**Hỏi: “Biến `Object x` có chứa toàn bộ object?”** Không. Biến giữ một reference value (hoặc null), còn trạng thái object được biểu diễn ở runtime theo cơ chế JVM.

**Hỏi: “Gán `y = x` có copy object?”** Không nếu `x` là reference: đó là copy reference value. Muốn object độc lập cần chủ động tạo/copy theo API, đồng thời chọn shallow hay deep copy đúng nhu cầu.

**Hỏi: “Java truyền object bằng tham chiếu?”** Java truyền **giá trị tham chiếu** theo cơ chế pass-by-value. Method có thể đổi trạng thái object được tham chiếu nhưng không thể gán lại biến của caller bằng cách gán tham số cục bộ.

**Hỏi: “Có thể dùng `==` để biết hai object ở cùng địa chỉ?”** `==` với reference kiểm tra **object identity** theo Java/JVM. Có thể dùng nó để xác định hai reference biểu thị cùng object, nhưng kết quả không cho địa chỉ của object.

**Hỏi: “`hashCode()` là địa chỉ của object?”** Không. Hash code là giá trị hash phục vụ hợp đồng Java; identity hash code không được bảo đảm duy nhất và không phải địa chỉ. Không dùng nó làm object ID toàn cục trong hệ phân tán hoặc thay địa chỉ.

**Hỏi: “GC move object thì mọi reference cũ sẽ hỏng?”** Không. JVM/GC phải duy trì ngữ nghĩa hợp lệ của reference vẫn còn sống. Mã Java thông thường không thấy quá trình cập nhật biểu diễn pointer nội bộ.

**Hỏi: “Kiểu `long` 64 bit nghĩa là 8 byte nằm liền nhau trên stack?”** Độ rộng kiểu Java không xác định mọi lựa chọn slot/frame/register/object layout. JVM specification và implementation có quy tắc riêng; JIT có thể tối ưu.

**Hỏi: “Reference giống con trỏ C, có thể cộng offset được không?”** Không. Reference Java không hỗ trợ pointer arithmetic. Nếu làm việc với native/off-heap memory, cần API chuyên biệt và chú ý lifetime, bounds, thread safety và tính portable.

**Hỏi: “Hai thread nhìn cùng reference thì không còn race?”** Sai. Identity/aliasing khác với JMM synchronization; mutable state vẫn cần thiết kế đồng bộ.

## 11. Bài tập tự kiểm tra

1. Sau `int b = a` và `b++`, `a` có đổi không? **Không**, vì sao chép giá trị primitive.
2. Sau `Box b = a` và `b.count++`, `a.count` có thể đổi không? **Có**, khi cả hai tham chiếu cùng một object mutable.
3. Trong method, gán `parameter = new Box(...)` có gán lại biến của caller không? **Không**, vì tham số là bản sao của reference value.
4. Hai `String` khác object nhưng cùng nội dung, `==` và `equals()` cho kết quả thế nào? **`==` false, `equals()` true**, nếu tạo hai object riêng bằng `new String(...)`.
5. `System.identityHashCode(o)` có thể dùng để in physical address không? **Không.**
6. Khi GC chuyển object tới vị trí khác, so sánh hai reference đang cùng trỏ object ấy có phải đổi kết quả không? **Không**, JVM duy trì ngữ nghĩa identity.
7. `int[] data` là primitive hay reference type? **Reference type tới object mảng**, còn từng phần tử `data[i]` là primitive `int`.
8. Để sửa race condition trên `shared.counter++`, việc ép hai thread cùng giữ một reference có đủ không? **Không**; phải xử lý đồng bộ/atomicity.

## 12. Tài liệu chuẩn để đào sâu

- Java Virtual Machine Specification (Java SE 17), chương **Run-Time Data Areas** và **Data Types**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html
- Java Language Specification (Java SE 17), phần **Types, Values, and Variables**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html
- Java Language Specification, phần **Method Invocation Expressions** (đánh giá và truyền đối số): https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4.2
- Java Language Specification, chương **Threads and Locks** (JMM/happens-before): https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html

**Kết luận kỹ thuật:** primitive value và reference value đều là **giá trị** mà Java/JVM xử lý. Reference value mang ngữ nghĩa **tham chiếu tới một object**, không phải hứa hẹn có thể đọc địa chỉ RAM. Object identity, lưu trữ bộ nhớ ảo/vật lý, layout của JVM và visibility giữa các thread là những tầng khác nhau; phân biệt được chúng sẽ giúp tránh lỗi về aliasing, tham số method, so sánh object, GC và lập trình đồng thời.
