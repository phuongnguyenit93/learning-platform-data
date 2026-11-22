# Vì sao hai wildcard giống cách viết vẫn có thể là hai kiểu khác nhau?

## 1. Vấn đề: cùng viết `?` nhưng không chắc cùng một kiểu

Trong Java Generics, dấu `?` (*wildcard*) đại diện cho **một kiểu chưa biết**. Khi hai vị trí đều viết `List<?>`, ta chỉ biết mỗi danh sách có **một loại phần tử nào đó**; không có lời hứa rằng hai loại phần tử phải giống nhau.

~~~java
List<String> words = List.of("A", "B");
List<Integer> numbers = List.of(1, 2);

List<?> first = words;
List<?> second = numbers;

Object a = first.get(0);
Object b = second.get(0);
~~~

Hai biến `first` và `second` cùng có **kiểu khai báo** `List<?>`. Nhưng một danh sách chứa `String`, danh sách kia chứa `Integer`. Vì vậy không có cơ sở để chuyển phần tử lấy từ `first` sang `second`:

~~~java
// KHÔNG biên dịch:
second.add(first.get(0));
~~~

Đó là tình huống quan trọng nhất khi học **wildcard capture**. Khi compiler cần kiểm tra phép gọi phương thức của một generic type chứa wildcard, nó có thể **bắt giữ** (*capture*) kiểu chưa biết thành một type variable mới để suy luận. Hai lần capture có thể được compiler biểu diễn bằng `CAP#1` và `CAP#2`, mỗi kiểu có ràng buộc riêng. Cùng hình thức `?` **không tự tạo quan hệ bằng nhau** giữa các capture.

Trong bài này, ta sẽ phân biệt kiểu khai báo và kiểu capture, giải thích cả trường hợp hai vị trí dùng **chính một biến `List<?>`**, kiểm chứng lỗi biên dịch thật, rồi sửa thiết kế bằng generic helper `<T>` hoặc quan hệ PECS phù hợp.

## 2. Kiểu khai báo giống nhau khác với danh tính kiểu bị capture

### 2.1. `List<?>` là một kiểu hợp lệ; `CAP#1` không phải tên do lập trình viên viết

Ba khai báo sau đều hợp lệ:

~~~java
List<?> unknownA = List.of("Java");
List<?> unknownB = List.of(42);
List<?> unknownC = List.of(3.5);
~~~

Các biến có cùng *declared type* `List<?>` và đều có thể đọc phần tử như `Object`. Đây là một quan hệ an toàn, không có unchecked conversion.

Tuy nhiên, trong một phép gọi như `unknownB.add(...)`, tham số `E` của `List<E>` phải được xác định đủ để compiler biết giá trị có thể thêm không. Java áp dụng **capture conversion** để tạm biểu diễn wildcard bằng một kiểu ẩn, chẳng hạn:

~~~text
List<?>                -> List<CAP#1>
CAP#1 extends Object
~~~

Đây là **sơ đồ mô hình hóa**, không phải cú pháp Java. `CAP#1` là tên chẩn đoán do compiler tạo, không phải một class, một runtime type token hay một tham số kiểu người lập trình có thể viết trực tiếp.

Một phép capture khác có thể tạo ra:

~~~text
List<?>                -> List<CAP#2>
CAP#2 extends Object
~~~

Hai ràng buộc `CAP#1 extends Object` và `CAP#2 extends Object` **không suy ra** `CAP#1 == CAP#2`, `CAP#1 <: CAP#2` hoặc `CAP#2 <: CAP#1`. Việc compiler dùng nhãn `CAP#1`, `CAP#2` theo thứ tự nào là chi tiết thông báo lỗi; điều quan trọng là **không tồn tại bằng chứng tương thích giữa hai kiểu chưa biết**.

### 2.2. Capture là thao tác ở compile time, không làm thay đổi list

Khi gán `List<String>` cho `List<?>`, Java không chuyển phần tử sang kiểu mới và không tạo bản sao. Cả hai reference có thể cùng trỏ một object danh sách. **Capture conversion chỉ giúp hệ thống kiểu phân tích một biểu thức**.

Nó không được lưu lại ở runtime thành những loại `CAP#1`/`CAP#2`. Generic type arguments phần lớn bị *type erasure* trong runtime representation. Java phải quyết định lời gọi `add`, `set` hay `get` có hợp lệ **trước khi chạy**.

### 2.3. “Không bằng nhau” không có nghĩa mọi việc đều bị cấm

~~~java
List<?> x = List.of("A");
List<?> y = List.of(10);

Object left = x.get(0);  // Hợp lệ.
Object right = y.get(0); // Hợp lệ.

boolean same = left.equals(right); // Hợp lệ: equals nhận Object.
boolean hasIt = y.contains(left);  // Hợp lệ: contains nhận Object.
~~~

`contains(Object)` không đòi đối số có đúng type parameter `E` của list. Trong khi đó `add(E)` và `set(int,E)` cần một giá trị phù hợp với `E`. Chính **chữ ký phương thức** quyết định liệu quan hệ giữa các kiểu capture có cần được chứng minh hay không.

## 3. Trường hợp hai biến `List<?>`: đọc được, nhưng không được chuyển phần tử tùy ý

Xét phương thức chỉ minh họa lỗi:

~~~java
static void brokenTransfer(List<?> source, List<?> target) {
    target.add(source.get(0)); // KHÔNG biên dịch.
}
~~~

Phân tích một cách khái niệm:

1. `source.get(0)` trả về giá trị thuộc một kiểu capture chưa biết, tạm gọi `CAP#1`.
2. `target.add(...)` chỉ nhận kiểu phần tử của `target`, tạm gọi `CAP#2`.
3. Không có bảo đảm `CAP#1` là subtype của `CAP#2`.
4. Compiler từ chối việc chuyển phần tử.

Ví dụ phản chứng cụ thể:

~~~java
List<String> source = List.of("text");
List<Integer> target = new ArrayList<>();
// Nếu được phép truyền cả hai như List<?> rồi target.add(source.get(0)),
// String sẽ bị thêm vào danh sách đã khai báo List<Integer>.
~~~

Dù một lần chạy nào đó người gọi truyền hai `List<String>`, chữ ký `brokenTransfer(List<?>, List<?>)` phải bảo đảm type safety cho **mọi cặp** hợp lệ, bao gồm `List<String>` và `List<Integer>`.

**Không nên chữa bằng ép kiểu raw/unchecked.** Ép `List<?>` sang `List<String>` khi chưa có bằng chứng về kiểu phần tử chỉ chuyển rủi ro sang runtime và có thể tạo heap pollution.

## 4. Cùng một biến `List<?>` vẫn có thể phát sinh hai capture khác nhau

Điểm dễ gây ngạc nhiên nhất: kể cả **một tham chiếu duy nhất** cũng không bảo đảm compiler nhận ra hai kết quả capture trong các biểu thức riêng rẽ là một kiểu có thể gán cho nhau.

~~~java
static void brokenSelfAssign(List<?> list) {
    list.set(0, list.get(0)); // KHÔNG biên dịch.
}
~~~

Ở góc nhìn con người, `get(0)` lấy một phần tử từ đúng list mà `set(0, ...)` sẽ ghi lại, nên thao tác này có thể an toàn nếu list mutable. Nhưng compiler phân tích các biểu thức generic chứa wildcard bằng capture conversion. Khi kiểm tra lời gọi `set`, nó có thể thấy một kiểu `CAP#1` cho tham số `E` cần ghi và một kiểu `CAP#2` cho kết quả `get`. Việc hai biểu thức dùng **cùng biến nguồn** không tự sinh ra ràng buộc `CAP#1 == CAP#2` trong lời gọi đó.

Biên dịch bằng Java 17 với `javac -Xdiags:verbose` sẽ cho lỗi với nội dung tương đương:

~~~text
required: int,CAP#1
found:    int,CAP#2
...
CAP#1 extends Object from capture of ?
CAP#2 extends Object from capture of ?
~~~

Thứ tự/cách đánh số CAP có thể khác theo compiler và phiên bản. Dòng `set(0, list.get(0))` **không biên dịch** dù hai biểu thức tham chiếu cùng object.

**Điểm chính xác cần ghi nhớ:** Không nên coi mỗi biến `List<?>` có một “mã CAP cố định” suốt cả phương thức. Những tên CAP là kết quả phân tích các biểu thức/capture; hãy giải quyết bằng quan hệ kiểu được biểu diễn rõ ràng thay vì dựa vào tên biến hay sự đồng nhất object lúc chạy.

### 4.1. Alias cũng không tự tạo bằng chứng capture bằng nhau

~~~java
List<String> actual = new ArrayList<>(List.of("A", "B"));
List<?> a = actual;
List<?> b = actual;
~~~

Hai reference `a` và `b` cùng trỏ đến `actual` tại runtime. Tuy nhiên, một hàm có chữ ký `f(List<?> a, List<?> b)` không thể giả định hai biến luôn trỏ chung object, hay có cùng kiểu phần tử trong mọi lần gọi. Khi muốn trao đổi giá trị theo type parameter, phải đặt quan hệ đó trong chữ ký hoặc capture qua helper cho **một list duy nhất**.

## 5. Wildcard giống nhau với `extends` cũng chưa chắc cùng subtype

Tình huống không chỉ xảy ra với `List<?>`. Hai biến cùng khai báo `List<? extends Number>` có thể tham chiếu đến:

~~~java
List<? extends Number> ints = List.of(2, 4);
List<? extends Number> doubles = List.of(1.5, 2.5);

Number a = ints.get(0);    // Hợp lệ.
Number b = doubles.get(0); // Hợp lệ.
~~~

Nhưng không thể chuyển trực tiếp giá trị đọc từ một list sang list kia:

~~~java
static void brokenUpperBound(
        List<? extends Number> source,
        List<? extends Number> target) {
    target.add(source.get(0)); // KHÔNG biên dịch.
}
~~~

Có thể mô hình hóa hai capture độc lập:

~~~text
CAP#1 <: Number
CAP#2 <: Number
~~~

Cả hai đều là subtype của `Number`; điều đó **không chứng minh CAP#1 là subtype của CAP#2**. Nếu `source` thực sự là `List<Integer>` và `target` là `List<Double>`, việc ghi `Integer` vào list `Double` sẽ sai.

Đây là lý do `? extends Number` phù hợp làm **nguồn đọc**: nó bảo đảm một kiểu chung ở chiều đọc, nhưng không cho phép đưa một `Number` tùy ý vào.

## 6. Wildcard `super`: có thể ghi giá trị đã biết, không thể suy ra kết quả đọc có cùng kiểu

Với `List<? super Integer>`, mỗi list có một kiểu phần tử chưa biết, nhưng **mỗi kiểu ấy đều nhận `Integer`**:

~~~java
List<? super Integer> x = new ArrayList<Number>();
List<? super Integer> y = new ArrayList<Object>();

x.add(10); // Hợp lệ.
y.add(20); // Hợp lệ.
~~~

Thế nhưng việc **chuyển phần tử đọc từ `x` sang `y`** vẫn không được bảo đảm:

~~~java
static void brokenLowerBound(
        List<? super Integer> source,
        List<? super Integer> target) {
    target.add(source.get(0)); // KHÔNG biên dịch.
}
~~~

Lý do: `source` có thể là `List<Object>` đang chứa `String`, trong khi `target` có thể là `List<Integer>`. Phần tử đọc từ `List<? super Integer>` chỉ được bảo đảm như `Object`, không phải `Integer`.

Có thể an toàn khi **thêm chính biến `Integer` đã có**, không phải mọi phần tử tình cờ đọc ra từ một list có thể nhận Integer:

~~~java
Integer n = 10;
x.add(n);
y.add(n);
~~~

Kết luận chung cho cả `?`, `? extends T` và `? super T`: **hai wildcard có cùng biểu thức giới hạn không có nghĩa chúng biểu diễn cùng type argument**.

## 7. Sửa lỗi cho một list: wildcard capture helper với `<T>`

Trường hợp `brokenSelfAssign(List<?>)` có thể được giải quyết bằng **phương thức helper generic**. API ngoài vẫn cho phép bất cứ `List<?>` nào; bên trong helper, ta **đặt tên cho kiểu phần tử** để dùng nhất quán qua `get` và `set`.

~~~java
static void swapEnds(List<?> values) {
    swapEndsCaptured(values);
}

private static <T> void swapEndsCaptured(List<T> values) {
    if (values.size() < 2) {
        return;
    }
    int last = values.size() - 1;
    T temporary = values.get(0);
    values.set(0, values.get(last));
    values.set(last, temporary);
}
~~~

**Cơ chế:**

1. Lời gọi `swapEndsCaptured(values)` cho phép compiler suy luận một `T` tương ứng với kiểu được capture của list nguồn.
2. Trong helper, cả kết quả `get(...)` và đối số `set(..., value)` đều liên hệ với cùng **tham số kiểu `T` có tên**.
3. `T temporary = values.get(0)` tạo một biến có kiểu tĩnh `T`. Hai lần `set` cũng cần `T`, nên type checking thành công mà không có cast.
4. Caller không cần biết list chứa `String`, `Integer` hay kiểu cụ thể nào.

Đây là một phương thức an toàn về **kiểu phần tử**. Nó vẫn đòi collection mutable; `List.of(...)` không hỗ trợ `set` và có thể ném `UnsupportedOperationException` nếu đưa trực tiếp vào `swapEnds`. Việc kiểm tra `size() < 2` bảo vệ các danh sách rỗng/1 phần tử khỏi lỗi chỉ số.

### 7.1. Vì sao helper thành công còn biểu thức lồng trực tiếp lại thất bại?

Trong helper `List<T>`, **một chữ `T` được khai báo** và dùng tại mọi vị trí liên quan. Trong `List<?>`, mỗi lần kiểm tra biểu thức liên quan đến wildcard có thể cần capture khác. Việc compiler chấp nhận phương thức helper **không chứng minh các wildcard từ những tham số không liên quan đều giống nhau**: helper đang xử lý một object list dưới một `T` thống nhất.

Với hai biến `List<?> source` và `List<?> target` độc lập, không thể tùy ý làm cho chúng có cùng `T` chỉ bằng cách gọi một helper `<T>`; caller phải cung cấp **quan hệ kiểu thật sự** để compiler kiểm tra.

## 8. Hai list độc lập: biểu diễn quan hệ trong chữ ký phương thức

Nếu hai list thực sự cùng một loại phần tử, một phương thức có type parameter ở cả hai vị trí là hợp lý:

~~~java
static <T> void swapFirst(List<T> left, List<T> right) {
    T temporary = left.get(0);
    left.set(0, right.get(0));
    right.set(0, temporary);
}
~~~

Phương thức trên chấp nhận **hai `List<String>`** hoặc **hai `List<Integer>`**; nó bảo đảm type argument của cả hai phù hợp với cùng `T`. Giả định: hai list có ít nhất một phần tử và cho phép `set`.

~~~java
List<String> left = new ArrayList<>(List.of("A"));
List<String> right = new ArrayList<>(List.of("B"));
swapFirst(left, right); // Hợp lệ.
~~~

Nhưng một cặp `List<String>` và `List<Integer>` không thể truyền cho `swapFirst` theo kiểu `List<T>` chung; việc này là **đúng với hợp đồng** của thuật toán trao đổi phần tử. Đừng dùng raw type để ép lời gọi vượt qua giới hạn đó.

### 8.1. Trường hợp producer/consumer: `<T>` kết hợp với hai wildcard khác hướng

Đôi khi source và target không có cùng type argument nhưng vẫn **chuyển phần tử an toàn** được. Ví dụ `List<Integer>` cung cấp `Integer` cho `List<Number>`.

~~~java
static <T> void appendAll(
        List<? extends T> source,
        List<? super T> destination) {
    for (T element : source) {
        destination.add(element);
    }
}
~~~

`T` là cầu nối giữa nơi đọc và nơi ghi; các wildcard thể hiện vai trò:

- `source: List<? extends T>` bảo đảm **đọc ra `T`**.
- `destination: List<? super T>` bảo đảm **có thể ghi `T`**.
- Không cần bắt hai type argument thực tế phải giống nhau: một bên có thể là `Integer`, bên kia là `Number`.

Ví dụ:

~~~java
List<Integer> ints = List.of(2, 4);
List<Number> numbers = new ArrayList<>(List.of(1.5));
appendAll(ints, numbers);
System.out.println(numbers); // [1.5, 2, 4]
~~~

Đây là áp dụng **PECS** (*Producer Extends, Consumer Super*) cho một quan hệ mà Java có thể kiểm tra. Nó **khác** với việc giả định hai wildcard cùng ký pháp là cùng một capture.

API chuẩn `Collections.copy(List<? super T> dest, List<? extends T> src)` thể hiện cùng mô hình quan hệ kiểu, nhưng hành vi của nó là **thay thế phần tử theo vị trí**, yêu cầu list đích có đủ kích thước; không phải append như đoạn code trên.

## 9. Chương trình Java 17+ chạy được để quan sát sự khác biệt

Tạo tệp **WildcardCaptureIdentityDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class WildcardCaptureIdentityDemo {
    static void rotateEnds(List<?> values) {
        rotateEndsCaptured(values);
    }

    private static <T> void rotateEndsCaptured(List<T> values) {
        if (values.size() < 2) {
            return;
        }
        int last = values.size() - 1;
        T temporary = values.get(0);
        values.set(0, values.get(last));
        values.set(last, temporary);
    }

    static <T> void swapFirst(List<T> left, List<T> right) {
        T temporary = left.get(0);
        left.set(0, right.get(0));
        right.set(0, temporary);
    }

    static <T> void appendAll(List<? extends T> source, List<? super T> destination) {
        for (T element : source) {
            destination.add(element);
        }
    }

    public static void main(String[] args) {
        List<String> left = new ArrayList<>(List.of("A", "B", "C"));
        List<String> right = new ArrayList<>(List.of("X", "Y"));

        rotateEnds(left);
        System.out.println("rotated: " + left);

        swapFirst(left, right);
        System.out.println("left: " + left);
        System.out.println("right: " + right);

        List<?> view1 = left;
        List<?> view2 = right;
        Object first = view1.get(0);
        Object second = view2.get(0);
        System.out.println("read: " + first + " / " + second);

        List<Integer> integers = List.of(2, 4);
        List<Number> destination = new ArrayList<>(List.of(1.5));
        appendAll(integers, destination);
        System.out.println("numbers: " + destination);

        List<? extends Number> n1 = List.of(5);
        List<? extends Number> n2 = List.of(8.5);
        Number a = n1.get(0);
        Number b = n2.get(0);
        System.out.println("numeric views: " + a + " / " + b);
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac --release 17 -Xlint:all WildcardCaptureIdentityDemo.java
java WildcardCaptureIdentityDemo
~~~

**Stdout chính xác**:

~~~text
rotated: [C, B, A]
left: [X, B, A]
right: [C, Y]
read: X / C
numbers: [1.5, 2, 4]
numeric views: 5 / 8.5
~~~

Chương trình đã được kiểm tra với `javac --release 17 -Xlint:all`: biên dịch thành công, không có unchecked warning.

Diễn biến:

1. `rotateEnds` nhận wildcard, helper `<T>` giữ một kiểu capture xuyên suốt thao tác hoán đổi; kết quả `[C, B, A]`.
2. `swapFirst` nhận hai `List<String>` có chung type argument, nên hoán đổi phần tử đầu thành công.
3. Hai view `List<?>` đọc an toàn dưới dạng `Object`. Cùng kiểu viết không cho biết giá trị thực tế hoặc cấp phép chuyển tùy ý giữa chúng.
4. `appendAll` cho phép source `List<Integer>` truyền phần tử vào destination `List<Number>` bằng một `T` chung và hai wildcard khác hướng.
5. Hai `List<? extends Number>` đọc an toàn như `Number` nhưng có thể chứa hai subtype thực tế khác nhau, như `Integer` và `Double`.

## 10. Kiểm chứng các trường hợp KHÔNG biên dịch

Tạo riêng tệp **InvalidCaptures.java** sau để thử lỗi chủ đích. **Tệp này cố ý không biên dịch** và không phải phần của chương trình chạy ở mục 9.

~~~java
import java.util.List;

class InvalidCaptures {
    static void sameVariable(List<?> list) {
        list.set(0, list.get(0)); // Hai capture không được suy ra là một.
    }

    static void twoVariables(List<?> source, List<?> target) {
        target.add(source.get(0)); // Không có quan hệ giữa hai wildcard.
    }

    static void twoUpperBounds(List<? extends Number> source,
                               List<? extends Number> target) {
        target.add(source.get(0)); // Cùng upper bound vẫn không đủ.
    }
}
~~~

Lệnh thử:

~~~bash
javac --release 17 -Xdiags:verbose InvalidCaptures.java
~~~

**Kỳ vọng:** `javac` kết thúc **khác 0**, báo ba lỗi biên dịch. Các đoạn chẩn đoán tiêu biểu đã được kiểm tra bằng Java hỗ trợ `--release 17`:

~~~text
required: int,CAP#1
found:    int,CAP#2
...
no suitable method found for add(CAP#1)
...
CAP#1 extends Number from capture of ? extends Number
CAP#2 extends Number from capture of ? extends Number
3 errors
~~~

Đây là các **đoạn rút gọn tiêu biểu**, không phải nguyên văn toàn bộ stderr; số thứ tự `CAP#`, vị trí file và cách trình bày có thể đổi theo compiler. Ba lỗi cùng chỉ đến một nguyên nhân: chữ ký chưa đưa ra bằng chứng rằng một giá trị thuộc kiểu capture ở vị trí đọc phù hợp với kiểu capture ở vị trí ghi.

Không sửa bằng `@SuppressWarnings("unchecked")`: ba trường hợp trên là **lỗi không tương thích kiểu**, không đơn thuần là cảnh báo unchecked mà annotation có thể làm biến mất. Giải pháp là **đổi chữ ký/hợp đồng kiểu** hoặc dùng helper capture khi làm việc với chính một collection.

## 11. Điều gì xảy ra nếu hai wildcard được tạo từ cùng một nguồn?

Xem:

~~~java
List<String> strings = new ArrayList<>(List.of("A", "B"));
List<?> one = strings;
List<?> two = strings;
~~~

Biết `one` và `two` đang trỏ cùng object **không phải một điều kiện kiểu hóa do `List<?>` diễn đạt**. Dữ liệu alias là một sự kiện runtime tại thời điểm đó; một phương thức khai báo hai `List<?>` vẫn chấp nhận hai list hoàn toàn khác nhau.

Mặt khác, ta có thể giữ thông tin `List<String>` ở call site và truyền nó cho một phương thức `<T>` cần hai `List<T>`. Khi đó hai tham số được kiểm tra theo một quan hệ kiểu rõ ràng. Nếu API bên ngoài chỉ nhận **hai `List<?>` độc lập**, không tồn tại một cách generic hoàn toàn an toàn để giả định chúng có cùng kiểu phần tử chỉ bằng cách so sánh reference hoặc nhìn ký pháp wildcard.

Đối chiếu:

| Trường hợp | Compiler có bằng chứng gì? | Chuyển phần tử giữa hai list? |
| --- | --- | --- |
| `List<String> a`, `List<String> b` | Cùng type argument `String` | Hợp lệ nếu đích hỗ trợ sửa. |
| `List<?> a`, `List<?> b` | Hai loại chưa biết, có thể khác nhau | Không được bảo đảm. |
| `List<? extends Number> a` và `b` cùng loại khai báo | Mỗi loại là subtype nào đó của `Number` | Không thể `b.add(a.get(0))`. |
| `List<? super Integer> a` và `b` cùng loại khai báo | Mỗi loại nhận được `Integer` | Có thể thêm một `Integer` đã biết vào cả hai, không thể chuyển mọi phần tử `a.get(...)` sang `b`. |
| `<T> swap(List<T> a,List<T> b)` | Hai list cùng một `T` trong lời gọi | Hợp lệ khi caller đáp ứng chữ ký. |
| `<T> append(List<? extends T>,List<? super T>)` | Nguồn đọc được `T`, đích nhận được `T` | Hợp lệ dù type arguments thực tế khác nhau. |

## 12. Giới hạn và lỗi thường gặp

### 12.1. Hiểu sai “cùng `?`” thành “cùng subtype”

Wildcard là một ràng buộc, **không phải một biến được đặt tên**. Hai vị trí cùng `? extends Number` chỉ có upper bound chung là `Number`, không mặc nhiên cùng là `Integer` hoặc `Double`.

### 12.2. Tin rằng `CAP#1` là lớp runtime

Các nhãn `CAP#1`, `CAP#2` là cách compiler diễn giải các kiểu ẩn trong quá trình type checking. Chúng không xuất hiện như những class mới. Không dùng `instanceof CAP#1`, không thể viết `new CAP#1()` hoặc đặt tên type variable bằng cú pháp này.

### 12.3. Dùng cùng một alias rồi kỳ vọng compiler theo dõi danh tính object

Java không dựa vào việc hai reference trỏ cùng list để tự cho phép mọi phép ghi qua generic wildcard. Khi thuật toán cần quan hệ, hãy trình bày bằng type parameter hoặc helper capture.

### 12.4. Coi `? extends Number` là `List<Number>`

`List<Integer>` không phải subtype của `List<Number>` do invariance. `List<? extends Number>` là view đọc theo upper bound; nó không cho phép thêm `Number` tùy ý và không đồng nhất kiểu capture giữa hai list.

### 12.5. Dùng `? super Integer` rồi giả định giá trị đọc là Integer

`List<? super Integer>` có thể trỏ đến `List<Number>` hoặc `List<Object>` với phần tử rộng hơn `Integer`. Kiểu đọc an toàn của `List<E>` là `Object`. Một `Integer` do caller chủ động tạo vẫn có thể thêm vào mọi `List<? super Integer>`.

### 12.6. Nghĩ bất kỳ helper `<T>` nào cũng buộc được hai wildcard độc lập giống nhau

Một helper có thể **giữ capture của một list** xuyên các thao tác. Với **hai list độc lập**, quan hệ phải được chứng minh bởi chữ ký method và các đối số caller truyền vào. Generic type parameter không tự cho phép tráo kiểu của `List<String>` với `List<Integer>`.

### 12.7. Bỏ qua mutability và lỗi chỉ số

Generic typing chỉ cho phép hoặc cấm thao tác **về mặt kiểu**. `get(0)`, `set(0, value)` vẫn có thể ném `IndexOutOfBoundsException` nếu danh sách rỗng; `List.of(...)` không sửa được và có thể ném `UnsupportedOperationException` khi gọi `add` hoặc `set`.

## 13. Quy trình chẩn đoán lỗi wildcard capture

1. **Đọc đúng dòng lỗi `CAP#n`:** hai nhãn khác nhau thường báo compiler chưa chứng minh hai kiểu capture có quan hệ phù hợp.
2. **Xác định chữ ký của phương thức đang gọi:** `get` trả về `E`; `add` cần `E`; `set` vừa nhận vừa trả `E`; `contains` lại nhận `Object`.
3. **Kiểm tra số lượng nguồn chứa wildcard:** một list cần thao tác nội bộ, hay hai list thực sự độc lập?
4. **Với một list:** cân nhắc public method `List<?>` chuyển sang private helper `<T> ... (List<T>)` để capture một kiểu thống nhất.
5. **Với hai list:** yêu cầu quan hệ mà thuật toán thực sự cần bằng `List<T>`/`List<T>` hoặc `List<? extends T>`/`List<? super T>`.
6. **Không sửa bằng raw type hoặc unchecked cast** khi không có bằng chứng về nội dung. Kiểm thử lại các call site với `javac -Xlint:unchecked`.
7. **Phân biệt lỗi tĩnh và rủi ro runtime:** compile-time capture error khác với `ClassCastException`/heap pollution do cố tình vượt hệ thống kiểu.

## 14. Câu hỏi ôn tập

1. Hai biến đều là `List<?>` có chắc có cùng type argument không? **Không.** Một bên có thể là `List<String>`, bên kia `List<Integer>`.
2. Hai `CAP#1` và `CAP#2` cùng `extends Object` có đồng nghĩa hai kiểu bằng nhau không? **Không.** Chung upper bound không chứng minh quan hệ bằng nhau.
3. Vì sao `list.set(0,list.get(0))` không biên dịch trong method nhận `List<?>`? **Vì hai biểu thức có thể bị capture riêng; compiler không nối chúng thành cùng type variable.**
4. Vì sao helper `<T> void swap(List<T>)` có thể thao tác an toàn? **Vì `T` được dùng nhất quán ở cả đầu vào và đầu ra của các thao tác.**
5. Hai `List<? extends Number>` có thể chuyển phần tử trực tiếp cho nhau không? **Không bảo đảm**, vì có thể là `List<Integer>` và `List<Double>`.
6. Hai `List<? super Integer>` có thể cùng nhận `Integer n` không? **Có về mặt kiểu**, vì mỗi supertype hợp lệ đều nhận `Integer`. Nhưng không suy ra có thể chuyển mọi `source.get(...)` sang đích.
7. Khi source là `List<Integer>` và target là `List<Number>`, chữ ký nào mô tả chép phần tử an toàn? **`<T> void append(List<? extends T>,List<? super T>)`**.
8. `CAP#1` có phải một class tồn tại ở runtime không? **Không**, đó là type variable do compiler dùng khi kiểm tra kiểu.
9. Nếu hai biến wildcard cùng tham chiếu một object, liệu đó có thay thế generic contract không? **Không**, cần thể hiện quan hệ kiểu trong chữ ký hoặc dùng helper đúng phạm vi.
10. Có thể dùng `@SuppressWarnings("unchecked")` để biến lỗi capture incompatibility thành hợp lệ không? **Không.** Đây là lỗi type checking, không phải chỉ là unchecked warning.

## 15. Tài liệu tham khảo

- [JLS Java SE 17 §5.1.10 — Capture Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.10): quy tắc tạo fresh capture variables từ wildcard và tính không tương đương giữa các capture.
- [JLS Java SE 17 §4.5.1 — Type Arguments of Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5.1): upper/lower bounded wildcards, các giới hạn type argument và quan hệ containment.
- [JLS Java SE 17 §4.10.2 — Subtyping Among Class and Interface Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.10.2): quan hệ subtype của parameterized types, lý do `List<Integer>` không là subtype của `List<Number>`.
- [Oracle Java Tutorials — Wildcard Capture and Helper Methods](https://docs.oracle.com/javase/tutorial/java/generics/capture.html): lỗi `CAP#`, ví dụ helper generic dùng để capture wildcard.
- [Oracle Java Tutorials — Guidelines for Wildcard Use](https://docs.oracle.com/javase/tutorial/java/generics/wildcardGuidelines.html): PECS, cách chọn wildcard cho nguồn và đích.
- [Java SE 17 API — List<E>](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): hợp đồng `get`, `set`, `add` và phân biệt type safety với khả năng sửa list.
