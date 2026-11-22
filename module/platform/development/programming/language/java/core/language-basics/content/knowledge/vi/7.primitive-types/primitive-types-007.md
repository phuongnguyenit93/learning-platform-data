# Phân biệt kiểu nguyên thủy với kiểu tham chiếu trong Java 17+

Java phân biệt hai nhóm kiểu dữ liệu:

- **Kiểu nguyên thủy (*primitive type*)**: biến chứa trực tiếp một giá trị thuộc một trong tám kiểu `byte`, `short`, `int`, `long`, `float`, `double`, `char`, `boolean`.
- **Kiểu tham chiếu (*reference type*)**: biến chứa một giá trị tham chiếu tới đối tượng hoặc mảng, hoặc chứa `null`. Ví dụ: `String`, `int[]`, một lớp tự định nghĩa, interface, enum, record và wrapper `Integer`.

Điểm cần nhớ: **gán một biến nguyên thủy sang biến cùng kiểu sao chép giá trị; gán một biến tham chiếu sang biến tham chiếu khác sao chép giá trị tham chiếu**, không tự sao chép đối tượng. Vì vậy, hai tên có thể cùng truy cập *một đối tượng*.

## 1. Bảng đối chiếu

| Tiêu chí | Kiểu nguyên thủy | Kiểu tham chiếu |
| --- | --- | --- |
| Ví dụ | `int`, `double`, `char`, `boolean` | `String`, `Integer`, `int[]`, `Counter` |
| Biến chứa gì? | Giá trị primitive | Tham chiếu đến đối tượng/mảng hoặc `null` |
| Có thể gán trực tiếp `null`? | **Không** | Có |
| Gán `b = a` | Sao chép giá trị | Sao chép **tham chiếu**, không nhân bản đối tượng |
| `==` | So sánh giá trị sau quy tắc chuyển kiểu thích hợp | Với hai tham chiếu tương thích: kiểm tra **cùng đối tượng** (hoặc cùng `null`) |
| Truy cập thành viên | Không gọi phương thức trên một giá trị primitive | Thường có field/phương thức, tùy kiểu |
| Giá trị mặc định của **field** | `0`, `0.0`, `false`, `'\u0000'` theo kiểu | `null` |
| Biến cục bộ chưa khởi tạo | Không thể đọc | Cũng **không thể đọc** |

Java **không tự gán giá trị mặc định cho biến cục bộ** thuộc bất kỳ nhóm nào. Một biến cục bộ phải được gán chắc chắn trước khi đọc (*definite assignment*). Còn field của lớp/đối tượng được khởi tạo mặc định theo kiểu khi cần.

Không nên diễn giải hai nhóm thành quy tắc tuyệt đối “primitive luôn ở stack, object luôn ở heap”: JVM có thể tối ưu vị trí lưu trữ. Điều cần hiểu là **ngữ nghĩa giá trị và tham chiếu**, không phải một sơ đồ RAM đơn giản.

## 2. Chương trình Java 17+ runnable: sao chép, alias và tham số

Tạo tệp **`ValueAndReferenceDemo.java`**:

~~~java
public class ValueAndReferenceDemo {
    static class Counter {
        int value;

        Counter(int value) {
            this.value = value;
        }
    }

    static void changePrimitive(int number) {
        number += 10;
        System.out.println("insidePrimitive=" + number);
    }

    static void changeObject(Counter counter) {
        counter.value += 10;
    }

    static void replaceReference(Counter counter) {
        counter = new Counter(99);
        System.out.println("insideReplace=" + counter.value);
    }

    public static void main(String[] args) {
        int original = 5;
        int copied = original;
        copied = 8;
        System.out.println("primitive=" + original + "," + copied);

        Counter first = new Counter(5);
        Counter alias = first;
        alias.value = 8;
        Counter independent = new Counter(8);

        System.out.println("sharedField=" + first.value);
        System.out.println("aliasIdentity=" + (first == alias));
        System.out.println("separateIdentity=" + (first == independent));
        System.out.println(
                "sameFieldValue=" + (first.value == independent.value));

        changePrimitive(original);
        System.out.println("afterPrimitive=" + original);

        changeObject(first);
        System.out.println("afterMutation=" + first.value);

        replaceReference(first);
        System.out.println("afterReassign=" + first.value);

        int[] numbers = {1, 2};
        int[] sameArray = numbers;
        sameArray[0] = 7;
        System.out.println("arrayFirst=" + numbers[0]);

        String text = "Java";
        String oldText = text;
        text = text + "17";
        System.out.println("oldText=" + oldText);
        System.out.println("newText=" + text);

        String a = new String("ok");
        String b = new String("ok");
        System.out.println("stringIdentity=" + (a == b));
        System.out.println("stringContent=" + a.equals(b));

        Integer boxed = 10;
        int unboxed = boxed;
        System.out.println("boxed=" + boxed + ",unboxed=" + unboxed);

        Integer missing = null;
        System.out.println("missingIsNull=" + (missing == null));
        try {
            int unsafe = missing;
            System.out.println("unsafe=" + unsafe);
        } catch (NullPointerException ex) {
            System.out.println("unboxing=NullPointerException");
        }
    }
}
~~~

Mở Windows PowerShell hoặc Linux/Bash ở thư mục chứa tệp. Cần **JDK 17+**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 ValueAndReferenceDemo.java
java ValueAndReferenceDemo
~~~

**Expected output (đúng thứ tự):**

~~~text
primitive=5,8
sharedField=8
aliasIdentity=true
separateIdentity=false
sameFieldValue=true
insidePrimitive=15
afterPrimitive=5
afterMutation=18
insideReplace=99
afterReassign=18
arrayFirst=7
oldText=Java
newText=Java17
stringIdentity=false
stringContent=true
boxed=10,unboxed=10
missingIsNull=true
unboxing=NullPointerException
~~~

### Phân tích những điểm dễ nhầm

**Sao chép primitive:** `copied = original` nhận số `5`. Đổi `copied` thành `8` không thay đổi `original`; hai biến giữ các giá trị độc lập.

**Sao chép reference:** `alias = first` không tạo `Counter` mới. Hai biến cùng tham chiếu một đối tượng nên `alias.value = 8` làm `first.value` bằng `8`. Còn `independent = new Counter(8)` tạo đối tượng **khác**; dù hai field bằng 8, `first == independent` vẫn là `false`.

**Java luôn truyền tham số theo giá trị:** Trong `changePrimitive`, tham số nhận bản sao số nguyên nên cộng 10 không đổi biến `original`. Trong `changeObject`, tham số nhận bản sao **giá trị tham chiếu** tới cùng Counter; thay field của đối tượng nên bên gọi nhìn thấy 18. Trong `replaceReference`, chỉ biến tham số `counter` được gán tham chiếu khác: đối tượng mà `first` đang trỏ tới **không bị thay thế**, nên vẫn có giá trị 18.

**Mảng và chuỗi:** `int[]` là **kiểu tham chiếu** dù các phần tử là `int` nguyên thủy; sửa qua `sameArray` ảnh hưởng tới mảng chung. `String` cũng là kiểu tham chiếu nhưng bản thân đối tượng chuỗi **bất biến**: `text + "17"` tạo nội dung chuỗi mới và gán lại biến `text`, không sửa nội dung chuỗi cũ của `oldText`.

## 3. `==`, `equals` và việc so sánh đúng ý nghĩa

~~~java
int x = 100;
int y = 100;
System.out.println(x == y); // true: gia tri int bang nhau.

String left = new String("hi");
String right = new String("hi");
System.out.println(left == right);      // false: hai doi tuong khac.
System.out.println(left.equals(right)); // true: noi dung bang nhau.
~~~

- Với các số nguyên thủy, `==` so sánh giá trị sau các phép chuyển đổi số cần thiết. Với `boolean`, nó so sánh hai giá trị logic.
- Với hai tham chiếu có kiểu so sánh được, `==` kiểm tra **đồng nhất đối tượng**, không tự so sánh nội dung.
- `equals` là **phương thức**; cách so sánh do lớp quyết định. `String.equals` so sánh nội dung, nhưng một lớp như `Counter` trong ví dụ **không override `equals`** thì kế thừa hành vi nhận diện đồng nhất của `Object`.

**Đừng dùng `==` để so sánh nội dung hai `String` bất kỳ**, kể cả khi đôi lúc `"a" == "a"` trả true vì Java có cơ chế intern string literal. Để xử lý chuỗi có thể null, dùng `java.util.Objects.equals(left, right)` khi thích hợp.

## 4. `null`, boxing và unboxing

`null` biểu thị một tham chiếu không trỏ tới đối tượng:

~~~java
String missing = null; // Hop le.
Integer number = null; // Hop le: Integer la reference type.

// int count = null;    // Loi bien dich: int la primitive.
// boolean ok = null;   // Loi bien dich.
~~~

`Integer` là **wrapper class** cho `int`, không phải một primitive mới. Java có thể tự **boxing** và **unboxing**:

~~~java
Integer boxed = 7;   // boxing: int -> Integer.
int raw = boxed;     // unboxing: Integer -> int.
~~~

Nếu `boxed == null`, việc unboxing sang `int` **ném `NullPointerException` lúc chạy**. Đây là khác biệt giữa lỗi **biên dịch** (`int x = null;` bị từ chối) và lỗi **runtime** (`int x = nullableInteger;` được chấp nhận về kiểu nhưng có thể thất bại).

Một wrapper còn có thể khiến `==` dễ hiểu nhầm: so sánh các **tham chiếu wrapper với nhau** không phải lựa chọn tốt để kiểm tra giá trị số. Khi mục tiêu là giá trị, hãy dùng `equals` thích hợp hoặc unboxing có kiểm tra null. Không dựa vào chuyện JVM có thể dùng lại một số đối tượng wrapper.

## 5. `final` không nhất thiết làm đối tượng bất biến

~~~java
final int limit = 3;
// limit = 4; // Loi: primitive final khong duoc gan lai.

final int[] scores = {1, 2};
scores[0] = 9; // Hop le: sua doi tuong mang.
// scores = new int[]{3}; // Loi: khong gan lai reference final.
~~~

`final` ràng buộc việc **gán lại biến**. Với kiểu tham chiếu, đối tượng được trỏ tới có thể vẫn thay đổi nếu API/kiểu cho phép; với `String`, đối tượng bất biến là do **thiết kế của lớp String**, không phải vì mọi tham chiếu tới nó đều `final`.

## 6. Lỗi phổ biến và cách sửa

| Triệu chứng | Vì sao? | Hướng xử lý |
| --- | --- | --- |
| `int n = null;` không biên dịch | Primitive không chấp nhận `null` | Chọn giá trị hợp lệ hoặc kiểu tham chiếu nếu thật sự cần thiếu giá trị |
| `String s = null; s.length();` | Dereference tham chiếu null | Kiểm tra `s != null` hoặc quy ước đầu vào không null |
| `Integer x = null; int n = x;` | Unboxing giá trị null | Kiểm tra null trước khi chuyển |
| Hai biến thay đổi chung một đối tượng | Cùng trỏ tới một object | Tạo bản sao thực sự khi cần dữ liệu độc lập |
| `new String("x") == new String("x")` cho false | `==` so sánh hai đối tượng | Dùng `equals` để so sánh chuỗi |
| Đổi tham số sang `new` nhưng biến bên gọi không đổi | Tham số nhận bản sao reference | Trả về reference mới và gán lại ở phía gọi nếu cần |
| `int[]` bị xem như primitive | Mảng luôn là reference type | Phân biệt kiểu mảng và kiểu phần tử |

### Quy tắc thực hành

1. Hỏi **biến chứa giá trị trực tiếp hay tham chiếu?** Đó là bước đầu để dự đoán tác động của phép gán.
2. Hỏi **hai biến có đang trỏ cùng đối tượng không?** Khi cùng trỏ, sửa trạng thái đối tượng có thể quan sát qua cả hai tên.
3. Hỏi **đối tượng có mutable không?** Chia sẻ tham chiếu tới `String` khác chia sẻ tham chiếu tới mảng hoặc đối tượng có field thay đổi.
4. Hỏi **tham chiếu có thể null không?** Kiểm tra trước khi gọi phương thức, truy cập field hoặc unboxing.

## 7. Bài tập tự kiểm tra

**Bài 1.** Với `int a = 3; int b = a; b++;`, `a` bằng bao nhiêu?  
*Đáp án:* 3. `b` nhận bản sao giá trị.

**Bài 2.** Với `int[] a = {1}; int[] b = a; b[0] = 5;`, `a[0]` bằng bao nhiêu?  
*Đáp án:* 5. Hai biến cùng trỏ một mảng.

**Bài 3.** Vì sao `new String("ok") == new String("ok")` là false nhưng `equals` là true?  
*Đáp án:* Hai `new` tạo hai đối tượng; `==` kiểm tra identity, `String.equals` so sánh nội dung.

**Bài 4.** Có thể truyền một đối tượng vào phương thức Java rồi gán `param = new Counter(...)` để thay luôn biến của bên gọi không?  
*Đáp án:* Không. Java truyền **bản sao giá trị tham chiếu**; gán lại tham số không đổi biến gốc.

**Bài 5.** Tại sao `Integer n = null;` hợp lệ nhưng `int x = n;` có thể gây lỗi?  
*Đáp án:* `Integer` là reference type chấp nhận null; unboxing null sang `int` gây `NullPointerException`.

## Ghi nhớ

**Primitive variable giữ giá trị; reference variable giữ giá trị tham chiếu.** Java luôn truyền tham số theo giá trị, nên truyền đối tượng nghĩa là sao chép *tham chiếu*, không nhân bản đối tượng. Hãy phân biệt `==` (identity với tham chiếu) và `equals` (theo cách lớp định nghĩa), chú ý `null`/unboxing và kiểm tra liệu trạng thái đối tượng có thể thay đổi. Đây là nền tảng để hiểu mảng, `String`, object, method và cách chia sẻ dữ liệu trong Java.
