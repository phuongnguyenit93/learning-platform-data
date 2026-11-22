# Phân tích ví dụ hoán đổi hai tham chiếu không thành công trong Java

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích tại sao method `swap(a, b)` nhận hai đối tượng làm đối số nhưng **không hoán đổi được hai biến tham chiếu của caller** bằng cách gán lại hai tham số.
- Mô phỏng từng bước các giá trị tham chiếu trước lời gọi, trong lời gọi và sau khi method trả về.
- Phân biệt **biến tham chiếu** với **đối tượng**, **gán lại tham chiếu** với **thay đổi trạng thái đối tượng**, và **pass-by-value** với pass-by-reference thực sự.
- Nhận biết tại sao tên parameter trùng với tên biến caller, generic method, kiểu `Object`, `String`, `final` hoặc từ khóa `static` không thay đổi quy tắc truyền tham trị của Java.
- Giải thích tại sao hai biến cùng tham chiếu một object, các phần tử mảng, field của holder object và biến local có hành vi khác nhau khi muốn “đổi chỗ”.
- Thực hiện việc hoán đổi thật sự bằng cách **sửa vị trí lưu tham chiếu** như phần tử mảng/`List`, **sửa field của holder**, hoặc **trả một cặp kết quả rồi caller chủ động gán lại**.
- Tự biên dịch ví dụ Java 17+, dự đoán stdout và nhận diện các nhầm lẫn thường gặp.

## 1. Đặt vấn đề: tưởng rằng `swap` sẽ đổi hai biến

Giả sử bạn có hai đối tượng:

~~~java
Box first = new Box("A");
Box second = new Box("B");
~~~

Bạn muốn sau khi gọi một phương thức:

~~~java
swap(first, second);
~~~

biến `first` tham chiếu Box B và biến `second` tham chiếu Box A. Một người mới học dễ viết:

~~~java
static void swap(Box a, Box b) {
    Box temp = a;
    a = b;
    b = temp;
}
~~~

Phần code này là **method declaration minh họa** cần đặt trong lớp có kiểu `Box`. Logic hoán đổi *có vẻ* đúng vì tại cuối method: tham số `a` giữ giá trị từng nằm trong `b`, còn tham số `b` giữ giá trị từng nằm trong `a`.

Tuy nhiên, khi lời gọi kết thúc:

- `first` vẫn tham chiếu **Box A**.
- `second` vẫn tham chiếu **Box B**.
- Hai tham số `a` và `b` đã được gán lại **bên trong lời gọi**, không phải hai biến của caller.

Đây là ví dụ điển hình để học ngữ nghĩa **Java chỉ truyền tham số theo giá trị** (*pass-by-value*).

### 1.1. Đâu là thứ đang được đổi?

Trong đoạn trên có **ít nhất bốn biến tham chiếu**:

| Biến | Thuộc đâu? | Vai trò |
| --- | --- | --- |
| `first` | Phạm vi caller | Giữ reference đến Box A |
| `second` | Phạm vi caller | Giữ reference đến Box B |
| `a` | Parameter của method `swap` | Ban đầu nhận bản sao reference của `first` |
| `b` | Parameter của method `swap` | Ban đầu nhận bản sao reference của `second` |
| `temp` | Local variable trong `swap` | Giữ một bản sao reference trung gian |

Dòng `Box temp = a;` **không** sao chép nội dung Box A: nó chép **giá trị tham chiếu** mà `a` đang giữ. Dòng `a = b;` chỉ gán vào **parameter variable `a`**; dòng `b = temp;` chỉ gán vào **parameter variable `b`**.

Nhiều biến có thể cùng giữ một reference, nhưng **chúng không trở thành cùng một biến**.

## 2. Quy tắc gốc: giá trị tham chiếu cũng được truyền theo giá trị

Trong Java:

- Với đối số kiểu nguyên thủy `int`, `double`, `boolean`..., caller truyền **giá trị primitive**.
- Với đối số kiểu tham chiếu như `Box`, `StringBuilder`, mảng, `List`..., caller truyền **giá trị tham chiếu tới object**.
- Với cả hai trường hợp, **biến tham số của callee được khởi tạo từ giá trị đối số**. Không có cơ chế ngôn ngữ để method nhận trực tiếp một “tham chiếu đến ô biến local của caller” theo kiểu pass-by-reference.

Ví dụ:

~~~java
static void changeNumber(int number) {
    number = 999;
}

static void changeReference(Box box) {
    box = new Box("new");
}
~~~

Cả hai khai báo đều minh họa trong lớp có `Box`. Method đầu gán lại parameter primitive; method sau gán lại parameter reference. **Cả hai đều không tự gán lại biến đã được caller dùng để truyền đối số**.

Trong lời gọi `swap(first, second)`, Java không cho method truy cập hai biến local có tên `first` và `second` của caller. Nó chỉ cho method hai parameter variables `a`, `b` chứa **các giá trị tham chiếu được chép**.

### 2.1. “Pass object by reference” là cách nói gây nhầm

Một số người mô tả Java là “truyền đối tượng bằng tham chiếu”, với ý muốn nói object **không được deep-copy** khi truyền vào method. Nếu diễn giải lỏng, câu này có thể gây hiểu sai.

Cách diễn đạt chính xác hơn:

> Java **pass-by-value**. Khi đối số mang kiểu reference, **giá trị được sao chép là object reference**. Callee có thể dùng reference này để truy cập cùng object, nhưng không thể gán lại biến tham chiếu của caller bằng cách gán lại parameter.

Hệ quả:

- **Sửa object:** có thể được caller quan sát khi hai phía cùng trỏ object mutable.
- **Gán lại parameter:** chỉ đổi local parameter reference của callee, không đổi biến reference bên caller.

## 3. Ví dụ chạy độc lập: swap thất bại dù bên trong đã đảo

Lưu thành **`FailedReferenceSwapDemo.java`**:

~~~java
public class FailedReferenceSwapDemo {
    static final class Box {
        final String id;

        Box(String id) {
            this.id = id;
        }
    }

    static void swap(Box a, Box b) {
        System.out.println("inside before=" + a.id + "," + b.id);
        Box temp = a;
        a = b;
        b = temp;
        System.out.println("inside after=" + a.id + "," + b.id);
    }

    public static void main(String[] args) {
        Box first = new Box("A");
        Box second = new Box("B");

        Box originalFirst = first;
        Box originalSecond = second;

        System.out.println("outside before=" + first.id + "," + second.id);
        swap(first, second);
        System.out.println("outside after=" + first.id + "," + second.id);
        System.out.println("same first=" + (first == originalFirst));
        System.out.println("same second=" + (second == originalSecond));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac FailedReferenceSwapDemo.java
java FailedReferenceSwapDemo
~~~

**Stdout chính xác:**

~~~text
outside before=A,B
inside before=A,B
inside after=B,A
outside after=A,B
same first=true
same second=true
~~~

**Giải thích đầu ra:**

1. Trước khi gọi, `first` trỏ Box A và `second` trỏ Box B.
2. `swap(first, second)` **chép hai giá trị reference** vào parameter `a` và `b`.
3. Tại đầu method, `a.id` là A, `b.id` là B.
4. Ba phép gán `temp = a; a = b; b = temp;` thực sự đảo **hai parameter variables** trong method. Vì thế dòng `inside after` in B,A.
5. Khi method trả về, không có phép gán nào đã thực hiện lên **biến `first`, `second` ở `main`**. Vì vậy `outside after` vẫn A,B.
6. Các phép so `first == originalFirst` và `second == originalSecond` đều `true`: hai biến caller vẫn trỏ đúng objects ban đầu.

**Đặc biệt:** hai object Box A và Box B **không bị hoán đổi vị trí trong bộ nhớ**, cũng không bị sao chép. Chỉ các biến tham chiếu cục bộ bên trong `swap` đổi chỗ.

## 4. Vẽ trạng thái tham chiếu trước, trong và sau lời gọi

### 4.1. Trước `swap(first, second)`

~~~text
CALLER
first  -----------------> Box A { id = "A" }
second -----------------> Box B { id = "B" }
~~~

### 4.2. Ngay lúc đi vào `swap`

Callee được khởi tạo hai tham số độc lập:

~~~text
CALLER                         CALLEE
first  ---------> Box A <------ a
second ---------> Box B <------ b
~~~

Các mũi tên từ `first` và `a` cùng trỏ **Box A**. Điều đó không có nghĩa `first` và `a` là cùng một biến.

### 4.3. Sau `temp = a;`

~~~text
CALLER                         CALLEE
first  ---------> Box A <------ a, temp
second ---------> Box B <------ b
~~~

Biến `temp` mới lưu tham chiếu Box A. Không có Box C được tạo.

### 4.4. Sau `a = b;`

~~~text
CALLER                         CALLEE
first  ---------> Box A <------ temp
second ---------> Box B <------ a, b
~~~

Chỉ biến `a` trỏ sang Box B. Biến `first` vẫn trỏ Box A.

### 4.5. Sau `b = temp;`

~~~text
CALLER                         CALLEE
first  ---------> Box A <------ b, temp
second ---------> Box B <------ a
~~~

Các parameter `a` và `b` đã đổi object chúng tham chiếu; còn `first` và `second` **không đổi**.

### 4.6. Sau khi `swap` trả về

~~~text
CALLER
first  -----------------> Box A { id = "A" }
second -----------------> Box B { id = "B" }
~~~

Các local variables `a`, `b`, `temp` của lần gọi không còn có thể dùng từ caller. Không tồn tại thao tác “ghi trả lại tham số đã đổi” vào các biến đối số của caller.

Lưu ý sơ đồ chỉ mô tả quan hệ reference. Java không cam kết reference phải là một địa chỉ máy cụ thể, hoặc các objects phải được lưu theo vị trí trong sơ đồ.

## 5. Vì sao `swap(Object a, Object b)` và generic `swap(T a, T b)` cũng thất bại?

Thay đổi **kiểu khai báo parameter** không thay đổi cơ chế truyền:

~~~java
static void swapObjects(Object a, Object b) {
    Object temp = a;
    a = b;
    b = temp;
}

static <T> void swapGeneric(T a, T b) {
    T temp = a;
    a = b;
    b = temp;
}
~~~

Đây là các khai báo method hợp lệ trong lớp thích hợp. Gọi:

~~~java
swapObjects(first, second);
swapGeneric(first, second);
~~~

vẫn chỉ gán lại **hai parameter references** trong callee.

Generic type parameter `T` cho phép tái sử dụng phương thức với nhiều kiểu object và thêm kiểm tra kiểu tĩnh. Nó **không** biến parameter `T a` thành tham chiếu tới **biến caller**. Tương tự, dùng `Object` làm kiểu tham số cũng không cấp quyền thay đổi biến caller.

### 5.1. Vì sao đổi tên parameter cũng không có tác dụng?

~~~java
static void swap(Box first, Box second) {
    Box temp = first;
    first = second;
    second = temp;
}
~~~

Dù parameter của callee trùng tên với local variables trong caller, đó vẫn là **hai khai báo biến thuộc các phạm vi khác nhau**. Tên chữ giống nhau không tạo một ràng buộc ngầm.

### 5.2. `final` và hoán đổi tham số

Nếu viết:

~~~java
static void swap(final Box a, final Box b) {
    // a = b; // Không hợp lệ vì a là final parameter
}
~~~

compiler **ngăn phép gán lại parameter**, nên ngay cả việc đảo hai local parameter variables như ví dụ sai ban đầu cũng không thể viết theo cách đó.

Không dùng `final` không đồng nghĩa caller variables có thể bị sửa. Dù parameter có thể gán lại hay không, chúng vẫn nhận reference **theo giá trị**.

## 6. Thay đổi trạng thái object có thể thành công, nhưng không phải swap references

Đây là điểm quan trọng nhất sau khi hiểu ví dụ thất bại. Nếu method **gọi một mutating method** hoặc **ghi field của object**, caller có thể quan sát thay đổi vì tham số và caller cùng tham chiếu object.

Lưu **`MutationNotReferenceSwapDemo.java`**:

~~~java
public class MutationNotReferenceSwapDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static void modifyThenSwapLocals(Box a, Box b) {
        a.value += 10;
        b.value += 20;

        Box temp = a;
        a = b;
        b = temp;

        a.value += 1;
        System.out.println("inside values=" + a.value + "," + b.value);
    }

    public static void main(String[] args) {
        Box first = new Box(1);
        Box second = new Box(2);

        Box firstBefore = first;
        Box secondBefore = second;

        modifyThenSwapLocals(first, second);

        System.out.println("outside values=" + first.value + "," + second.value);
        System.out.println("references unchanged=" +
                (first == firstBefore && second == secondBefore));
    }
}
~~~

Lệnh:

~~~bash
javac MutationNotReferenceSwapDemo.java
java MutationNotReferenceSwapDemo
~~~

Output:

~~~text
inside values=23,11
outside values=11,23
references unchanged=true
~~~

**Truy vết:**

- Ban đầu Box A.value = 1, Box B.value = 2.
- `a.value += 10` sửa Box A thành 11.
- `b.value += 20` sửa Box B thành 22.
- Ba phép gán local swap làm `a` trỏ Box B, `b` trỏ Box A.
- `a.value += 1` giờ sửa Box B thành 23.
- Callee in `inside values=23,11`.
- Caller vẫn có `first` → Box A (11), `second` → Box B (23). Không có biến caller nào được hoán đổi.
- `references unchanged=true` xác nhận reference variables của caller giữ nguyên.

**Chú ý phân biệt:** Dòng `outside values=11,23` có vẻ như hai **con số** “đã đổi”, nhưng trong thực tế method đã **sửa các field value**, không hề đổi vị trí hai reference của caller. Đây là lý do nên kiểm tra cả **object identity** và **trạng thái object** khi phân tích.

### 6.1. Hoán đổi nội dung object khác với hoán đổi references

Bạn có thể viết một method đổi giá trị field:

~~~java
static void swapValues(Box a, Box b) {
    int temp = a.value;
    a.value = b.value;
    b.value = temp;
}
~~~

Đây là code minh họa với `Box.value` là field `int` có thể sửa. Sau `swapValues(first, second)`, **các giá trị trong Box A và Box B** đã đổi, còn biến `first` vẫn trỏ Box A và `second` vẫn trỏ Box B.

Nếu Box chứa nhiều fields, đổi một field không đồng nghĩa “hoán đổi toàn bộ object”; cố hoán đổi mọi field có thể vi phạm invariants, aliasing khác hoặc các ràng buộc như `final`. Nếu mục tiêu là đổi **biến tham chiếu**, cần giải pháp khác.

## 7. Vì sao không thể hoán đổi hai local reference variables qua tham số thông thường?

Trong Java, khi một method được gọi với hai biểu thức như:

~~~java
swap(first, second);
~~~

callee chỉ nhận **hai giá trị tham chiếu**. Nó không được cấp một primitive “địa chỉ của biến `first`” hay một reference-to-variable cho phép lệnh `a = ...` sửa biến caller.

Điều này còn đúng khi:

- Hai biến caller là instance fields và được truyền dưới dạng `swap(this.left, this.right)`.
- Hai đối số là phần tử mảng, ví dụ `swap(items[0], items[1])`.
- Method có kiểu tham số `Object` hoặc generic `<T>`.
- Method trả `void` hoặc có return type khác nhưng caller **không tự gán lại**.
- Method được khai báo `static` hoặc instance method.
- Đối số là object mutable, immutable, hoặc `null` (nếu signature cho phép).

**Tuy nhiên:** một method **có thể tự mình thay đổi field hoặc phần tử mảng** nếu được cung cấp đối tượng/array container có thể sửa. Đó là một kiểu API khác: thay vì nhận **giá trị tại hai vị trí**, method nhận **vị trí lưu các giá trị** thông qua một container mutable.

Ví dụ:

~~~java
swap(items[0], items[1]); // Không hoán đổi items[0] và items[1]
swapAt(items, 0, 1);      // Có thể hoán đổi hai phần tử trong mảng items
~~~

Hai lời gọi trên có ý nghĩa khác nhau. Lời gọi đầu truyền **giá trị của hai phần tử**; lời gọi sau truyền **tham chiếu tới chính mảng** và **hai chỉ số**, cho phép method cập nhật các phần tử đó.

## 8. Cách đúng số 1: hoán đổi hai phần tử trong mảng

Lưu **`ArrayReferenceSwapDemo.java`**:

~~~java
public class ArrayReferenceSwapDemo {
    static final class Box {
        final String id;

        Box(String id) {
            this.id = id;
        }
    }

    static <T> void ineffectiveSwap(T first, T second) {
        T temporary = first;
        first = second;
        second = temporary;
    }

    static <T> void swapAt(T[] items, int left, int right) {
        T temporary = items[left];
        items[left] = items[right];
        items[right] = temporary;
    }

    public static void main(String[] args) {
        Box a = new Box("A");
        Box b = new Box("B");
        Box[] items = {a, b};

        ineffectiveSwap(items[0], items[1]);
        System.out.println("after ineffective=" + items[0].id + "," + items[1].id);

        swapAt(items, 0, 1);
        System.out.println("after swapAt=" + items[0].id + "," + items[1].id);

        System.out.println("items[0] is b=" + (items[0] == b));
        System.out.println("items[1] is a=" + (items[1] == a));
        System.out.println("caller a=" + a.id + ", caller b=" + b.id);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ArrayReferenceSwapDemo.java
java ArrayReferenceSwapDemo
~~~

Output:

~~~text
after ineffective=A,B
after swapAt=B,A
items[0] is b=true
items[1] is a=true
caller a=A, caller b=B
~~~

**Giải thích:**

- `ineffectiveSwap(items[0], items[1])` đọc **hai reference values** từ mảng rồi truyền bản sao vào method. Các phép gán lại `first`, `second` chỉ đổi parameters; mảng `items` không đổi.
- `swapAt(items, 0, 1)` nhận một **bản sao tham chiếu tới mảng `items`** cùng hai primitive indices.
- Dù parameter `items` cũng được truyền theo giá trị, nó trỏ **cùng array object** với caller.
- Câu lệnh `items[left] = items[right]` và `items[right] = temporary` trực tiếp **sửa các phần tử của array object**. Vì vậy hai vị trí mảng đổi reference.
- Hai biến local `a` và `b` trong `main` **vẫn** trỏ các Box ban đầu. Hoán đổi **mảng** không tự hoán đổi hai biến local ấy.

### 8.1. Mảng là container mutable, nhưng phải kiểm tra chỉ số

`swapAt(items, i, j)` chỉ hợp lệ nếu `items` không `null` và hai chỉ số nằm trong miền `0 .. items.length-1`. Nếu không, Java có thể ném `NullPointerException` hoặc `ArrayIndexOutOfBoundsException`.

Nếu `i == j`, cách swap ba bước trên gán lại cùng phần tử với chính giá trị của nó, nên thứ tự không thay đổi. Với API tổng quát, có thể kiểm tra trước nếu cần rõ thông báo lỗi hoặc hiệu năng.

### 8.2. Mảng generic `T[]` có phải lúc nào cũng an toàn?

Java cho phép khai báo method `static <T> void swapAt(T[] array, int i, int j)` như trên. Đối với các phần tử được lấy từ **chính mảng**, chúng có kiểu tương thích để gán lại vào mảng đó. Nhưng array covariance và runtime store checks là chủ đề rộng hơn: đừng suy ra từ việc generic method biên dịch rằng mọi phép gán object bất kỳ vào mảng đều hợp lệ ở runtime.

Điểm chính của ví dụ không phụ thuộc vào generics: đổi **array elements** là mutate container; đổi **local parameters** không mutate caller variables.

## 9. Cách đúng số 2: dùng `List` và `Collections.swap`

Đối với một `List` mutable, Java cung cấp `java.util.Collections.swap(list, i, j)` để hoán đổi các phần tử tại hai vị trí.

Lưu **`ListReferenceSwapDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ListReferenceSwapDemo {
    static final class Box {
        final String id;

        Box(String id) {
            this.id = id;
        }
    }

    public static void main(String[] args) {
        Box a = new Box("A");
        Box b = new Box("B");

        List<Box> boxes = new ArrayList<>(List.of(a, b));
        System.out.println("before=" + boxes.get(0).id + "," + boxes.get(1).id);

        Collections.swap(boxes, 0, 1);
        System.out.println("after=" + boxes.get(0).id + "," + boxes.get(1).id);

        System.out.println("box a still A=" + a.id);
        System.out.println("box b still B=" + b.id);
        System.out.println("positions swapped=" +
                (boxes.get(0) == b && boxes.get(1) == a));
    }
}
~~~

Chạy:

~~~bash
javac ListReferenceSwapDemo.java
java ListReferenceSwapDemo
~~~

Output:

~~~text
before=A,B
after=B,A
box a still A=A
box b still B=B
positions swapped=true
~~~

`Collections.swap` sửa **các vị trí trong `ArrayList`**, không yêu cầu hoán đổi hai local variables `a` và `b`. Nếu list không hỗ trợ `set` tại các vị trí, phép swap có thể ném `UnsupportedOperationException`. `List.of(a,b)` không sửa được; vì vậy ví dụ bọc nó bằng `new ArrayList<>(...)` để có mutable list.

**Thiết kế API:** nếu bạn đang quản lý danh sách objects, hãy thao tác trực tiếp trên cấu trúc dữ liệu chứa chúng. Không cần mô phỏng pass-by-reference của biến local.

## 10. Cách đúng số 3: dùng holder objects để hoán đổi field tham chiếu

Nếu nghiệp vụ đòi hoán đổi hai **ô lưu trữ** nằm trong objects, bạn có thể tạo một kiểu holder có field mutable. Method nhận reference đến holder objects và **sửa field** bên trong chúng.

Lưu **`HolderReferenceSwapDemo.java`**:

~~~java
public class HolderReferenceSwapDemo {
    static final class Box {
        final String id;

        Box(String id) {
            this.id = id;
        }
    }

    static final class Holder<T> {
        T value;

        Holder(T value) {
            this.value = value;
        }
    }

    static <T> void swapValues(Holder<T> left, Holder<T> right) {
        T temporary = left.value;
        left.value = right.value;
        right.value = temporary;
    }

    public static void main(String[] args) {
        Box a = new Box("A");
        Box b = new Box("B");

        Holder<Box> first = new Holder<>(a);
        Holder<Box> second = new Holder<>(b);

        swapValues(first, second);

        System.out.println("first holder=" + first.value.id);
        System.out.println("second holder=" + second.value.id);
        System.out.println("holders unchanged=" +
                (first != second));
        System.out.println("first points to b=" + (first.value == b));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac HolderReferenceSwapDemo.java
java HolderReferenceSwapDemo
~~~

Output:

~~~text
first holder=B
second holder=A
holders unchanged=true
first points to b=true
~~~

Ở đây:

- `first` và `second` là hai **holder objects** khác nhau.
- Parameter `left` và `right` nhận **bản sao reference** tới hai holder objects.
- `left.value = right.value` và `right.value = temporary` sửa **các fields `value`** của holders mà caller vẫn tham chiếu.
- Biến caller `first`, `second` không đổi holder object; nhưng **nội dung field reference** của mỗi holder đã đổi.

Đây là **mutating API có chủ đích**, không phải pass-by-reference của các biến `first` hoặc `second`. Nếu các holders/fields được chia sẻ giữa threads, việc hoán đổi nhiều fields không tự động atomic; cần synchronization thích hợp nếu muốn invariant đa luồng.

### 10.1. Có nên dùng `AtomicReference` thay holder không?

`AtomicReference<T>` là một kiểu holder reference với các primitive operations có semantics đồng bộ hóa hữu ích. Nhưng hai lệnh `left.set(right.get())` và `right.set(temp)` **không tạo một phép swap hai ô atomic như một đơn vị**. Chúng có thể bị thread khác quan sát ở trạng thái trung gian nếu thiếu cơ chế đồng bộ phối hợp.

Đừng dùng `AtomicReference` chỉ vì mong Java chuyển thành pass-by-reference. Nó giải quyết các nhu cầu concurrency/cập nhật reference cụ thể, **không thay cơ chế truyền tham số** của ngôn ngữ.

## 11. Cách đúng số 4: trả về cặp giá trị rồi caller tự gán

Để thực sự đổi hai **local variables** ở caller, cách dễ hiểu là method trả lại các giá trị mới và **caller thực hiện các phép gán**.

Trong Java 17, một `record` có thể diễn đạt cặp kết quả rõ hơn một mảng `Object[]` không có tên/kiểu phần tử cụ thể.

Lưu **`SwapResultDemo.java`**:

~~~java
public class SwapResultDemo {
    static final class Box {
        final String id;

        Box(String id) {
            this.id = id;
        }
    }

    record Pair<T>(T first, T second) { }

    static <T> Pair<T> swapped(T left, T right) {
        return new Pair<>(right, left);
    }

    public static void main(String[] args) {
        Box first = new Box("A");
        Box second = new Box("B");

        System.out.println("before=" + first.id + "," + second.id);

        Pair<Box> result = swapped(first, second);
        System.out.println("before assigning=" + first.id + "," + second.id);

        first = result.first();
        second = result.second();

        System.out.println("after assigning=" + first.id + "," + second.id);
    }
}
~~~

Lệnh:

~~~bash
javac SwapResultDemo.java
java SwapResultDemo
~~~

Output:

~~~text
before=A,B
before assigning=A,B
after assigning=B,A
~~~

**Vì sao cách này hoạt động?**

- Method `swapped` **không** thay hai biến local `first`, `second`; nó chỉ tạo và trả một giá trị `Pair<Box>` chứa hai references theo thứ tự đảo.
- Sau khi method trả về, biến caller vẫn giữ A/B (dòng `before assigning`).
- Chính hai phép gán `first = result.first(); second = result.second();` trong `main` thay đổi reference values mà các biến local của caller lưu.
- Vì `Pair<Box>` giữ đồng thời hai giá trị đầu ra nên việc gán tuần tự không mất giá trị cũ; nếu chỉ viết `first = second; second = first;` thì cả hai kết thúc trỏ B.

### 11.1. Nếu caller variables là `final` thì sao?

Với:

~~~java
final Box first = new Box("A");
final Box second = new Box("B");
~~~

bạn **không thể** gán lại `first = ...` hoặc `second = ...` sau khi chúng được khởi tạo. Đó là chính sách của `final`, không phải giới hạn của factory/record.

Nếu code cần giữ references bất biến, có thể tạo **một cặp mới**:

~~~java
Pair<Box> original = new Pair<>(first, second);
Pair<Box> reversed = swapped(original.first(), original.second());
~~~

Đây là đoạn minh họa với kiểu `Box` và `Pair` đã khai báo phù hợp. Không cần sửa biến `first`, `second`: caller chọn dùng `reversed` làm kết quả logic mới.

## 12. Phân biệt các mục tiêu “swap” thường gặp

Từ “hoán đổi hai đối tượng” có thể bị hiểu theo nhiều nghĩa. Trước khi chọn code, nên hỏi **chính xác cái gì cần đổi**.

| Mục tiêu | Cách tiếp cận | Biến local reference ban đầu có đổi? | Object data có đổi? |
| --- | --- | --- | --- |
| Đảo hai parameter references của callee | `swap(Box a, Box b)` dùng ba phép gán | **Không** | Không, nếu chỉ gán biến |
| Hoán đổi **field values** của hai Box mutable | Ghi `a.value` và `b.value` | Không | **Có** |
| Hoán đổi hai **phần tử array** | `swapAt(Box[] array,i,j)` | Biến array không đổi | **Array entries đổi**; Box data không cần đổi |
| Hoán đổi hai **phần tử List** | `Collections.swap(list,i,j)` | Biến list không đổi | **List entries đổi** |
| Hoán đổi fields trong hai holders | `swapValues(Holder<T>,Holder<T>)` | Các biến holder không đổi | **Holder fields đổi** |
| Hoán đổi hai **local variables** của caller | Return pair, caller tự gán lại | **Có**, do caller gán | Không cần sửa objects |
| Tạo view đảo mà không đổi dữ liệu gốc | Trả pair/list mới có thứ tự đảo | Không | Không đổi dữ liệu gốc |

**Đừng gọi mọi kết quả trông như B,A là “swap references thành công”.** Hãy phân biệt nơi lưu references được đổi: **parameter variables**, **caller variables**, **array elements**, **list elements**, **object fields**.

## 13. Trường hợp cả hai biến cùng tham chiếu một object

Giả sử:

~~~java
Box first = new Box("A");
Box second = first;
swap(first, second);
~~~

Hai biến caller ngay từ đầu đã là **aliases** của cùng Box A. Việc hoán đổi hai giá trị tham chiếu giống hệt nhau (ngay cả nếu caller tự làm) không có hiệu ứng quan sát được về identity: cả hai vẫn trỏ Box A.

Điều này dễ làm test sai nếu bạn chỉ thử hai aliases giống nhau; method `swap` bị lỗi logic có thể trông như “không có thay đổi nào là đúng”. Muốn kiểm tra swap references, dùng **hai object khác nhau**, và so identity sau thao tác.

### 13.1. Trường hợp tham số có giá trị `null`

Ví dụ:

~~~java
Box first = new Box("A");
Box second = null;
swap(first, second);
~~~

Nếu `swap` chỉ gán lại parameters và **không truy cập field hoặc gọi instance method** trên `null`, lời gọi vẫn biên dịch và có thể thực thi bình thường. Nhưng khi trả về:

- `first` vẫn giữ tham chiếu Box A.
- `second` vẫn là `null`.

Đừng hiểu “`null` được gán cho parameter a” nghĩa caller `first` cũng thành `null`. Mọi phép gán bên trong chỉ áp dụng parameter local.

Nếu dùng giải pháp array/holder, phải tuân thủ contract: một phần tử có thể là `null` và việc hoán đổi các references đó vẫn có thể có nghĩa, miễn code không dereference null.

## 14. Gán lại biến tham chiếu và sửa nội dung `StringBuilder`

`StringBuilder` là object mutable, cho thấy rõ khác biệt giữa **gán lại reference** với **sửa object**.

Lưu **`StringBuilderReferenceDemo.java`**:

~~~java
public class StringBuilderReferenceDemo {
    static void swapLocals(StringBuilder a, StringBuilder b) {
        StringBuilder temp = a;
        a = b;
        b = temp;
        a.append("!");
    }

    public static void main(String[] args) {
        StringBuilder first = new StringBuilder("A");
        StringBuilder second = new StringBuilder("B");

        swapLocals(first, second);

        System.out.println("first=" + first);
        System.out.println("second=" + second);
    }
}
~~~

Chạy:

~~~bash
javac StringBuilderReferenceDemo.java
java StringBuilderReferenceDemo
~~~

Output:

~~~text
first=A
second=B!
~~~

Trong method:

1. `a` ban đầu trỏ StringBuilder A, `b` trỏ StringBuilder B.
2. Sau ba phép gán local, `a` trỏ StringBuilder B, `b` trỏ StringBuilder A.
3. `a.append("!")` **thay đổi object B** thành B!.
4. Caller vẫn trỏ A qua `first` và B qua `second`, nên in A và B!.

Ví dụ này vừa cho thấy **swap local references không ảnh hưởng caller variables**, vừa cho thấy một method nhận bản sao reference vẫn **có thể mutate object**.

## 15. Tại sao `String` thường làm người học nhầm lẫn?

`String` là reference type nhưng **immutable**. Xem:

~~~java
static void swapStrings(String a, String b) {
    String temp = a;
    a = b;
    b = temp;
}
~~~

Nếu caller có `String first = "A", second = "B";` rồi gọi `swapStrings(first, second)`, hai biến caller vẫn giữ `"A"` và `"B"`.

Cũng như với `Box`, ba phép gán chỉ đảo **tham số local**. Không phải vì String immutable mà swap không thành; **mọi reference type** đều có quy tắc pass-by-value này.

Khác biệt ở chỗ String **không có mutating method thông thường** như `append` để sửa nội dung String object. Ví dụ:

~~~java
static void addSuffix(String text) {
    text = text + "!";
}
~~~

không sửa caller string variable; phép nối tạo giá trị chuỗi mới và gán lại parameter `text`.

Do string literals có thể được intern, dùng `==` giữa literals để suy đoán rằng hai biến cùng object có thể gây nhầm. Khi phân tích bài swap, nên dùng hai object độc lập có identity rõ và kiểm tra reference equality có chủ đích.

## 16. Truyền reference vào method không tạo bản sao object

Một cách hiểu sai khác là: “Vì Java pass-by-value nên mỗi lần truyền `Box` vào method là tạo một Box mới.” Điều đó **không đúng**.

~~~java
Box first = new Box("A");
use(first);
~~~

Với một method `use(Box p)`, Java **sao chép reference value** vào `p`. Không có bước tự động gọi copy constructor hoặc deep clone `Box`. Vì vậy `p == first` có thể là `true` ngay khi method bắt đầu.

Hãy tách hai hành động:

- **Copy reference value**: callee và caller cùng có reference tới object cũ.
- **Copy object**: tạo object mới rồi sao chép nội dung có chủ đích; yêu cầu constructor/copy API riêng.

Bản chất của thất bại `swap` nằm ở **phép gán lại parameter variables**, không phải ở việc objects được hay không được copy.

## 17. Có thể dùng array để hoán đổi chính biến local không?

Không trực tiếp. Xem:

~~~java
Box first = new Box("A");
Box second = new Box("B");
Box[] holder = {first, second};
swapAt(holder, 0, 1);
~~~

Sau đó:

- `holder[0]` trỏ B, `holder[1]` trỏ A.
- Nhưng **biến local `first` vẫn trỏ A, `second` vẫn trỏ B**.

Array là **một nơi lưu tham chiếu mới**, riêng biệt với local variables. Muốn biến local cũng đổi, caller phải viết:

~~~java
first = holder[0];
second = holder[1];
~~~

Điều này giống dùng return pair: **caller** chịu trách nhiệm gán lại hai local variables.

Dùng array hoặc holder chỉ có lợi khi **vị trí lưu dữ liệu trong container** là thứ mà API thật sự sở hữu/cần thay đổi. Đừng dựng thêm mutable holder chỉ để “đi đường vòng” thay cho hai phép gán đơn giản ở caller.

## 18. Thứ tự đánh giá đối số: có thể sửa caller trước khi swap được gọi

Một tình huống tinh tế: biểu thức đối số có thể có **side effects** trước khi method bắt đầu.

Ví dụ minh họa:

~~~java
static void swap(Object a, Object b) {
    Object temp = a;
    a = b;
    b = temp;
}

// Trong caller:
Object first = new Object();
Object second = new Object();
swap(first = second, second);
~~~

Sau lời gọi, biến `first` của caller thực sự đã đổi tham chiếu để trỏ cùng object với `second`. Nhưng **nguyên nhân là biểu thức đối số `first = second` đã gán lại caller variable trước khi vào method**, không phải do ba phép gán trong body của `swap`.

Quy tắc đánh giá đối số từ trái sang phải đảm bảo biểu thức `first = second` chạy trước khi tính đối số thứ hai `second`. Đó là lý do **không** thể dựa vào việc “giá trị caller thay đổi sau lời gọi” như bằng chứng method dùng pass-by-reference; cần kiểm tra **thao tác nào thực sự gán biến caller**.

Trong mã ứng dụng, tránh đặt những phép gán làm thay đổi cùng dữ liệu vào một danh sách đối số khó đọc. Tách thành các câu lệnh có tên và mục đích rõ ràng sẽ dễ kiểm soát hơn.

## 19. Hoán đổi references trong fields: khi nào có thể làm?

Giả sử một object quản lý hai fields `left` và `right`:

~~~java
class PairBox {
    Box left;
    Box right;

    void swapFields() {
        Box temp = left;
        left = right;
        right = temp;
    }
}
~~~

Đoạn này là class minh họa cần khai báo `Box`. `swapFields()` **sửa trực tiếp hai fields thuộc cùng object `PairBox`**, chứ không sửa hai parameter variables bản sao. Vì thế caller đang tham chiếu `PairBox` đó sẽ quan sát các fields đã hoán đổi.

Nếu fields được khai báo `final` sau khi khởi tạo, Java không cho phương thức thông thường gán lại chúng. Khi cần mô hình bất biến, hãy tạo một `PairBox`/record mới có thứ tự đảo và trả về thay vì thay đổi fields.

Nếu đối tượng chứa hai fields có thể được nhiều threads cùng đọc/ghi, thao tác đổi hai fields bằng ba phép gán **không atomic** theo mặc định. Cần synchronization hoặc thiết kế dữ liệu không sửa đổi nếu trạng thái trung gian không được phép lộ ra.

## 20. Những lỗi phổ biến và cách sửa

| Nhầm lẫn | Điều đúng |
| --- | --- |
| “`swap(a,b)` giống C++ pass-by-reference nên đổi được hai biến caller.” | Java pass-by-value. Không có parameter kiểu reference-to-variable như ví dụ C++ tương ứng. |
| “Vì Box là object, method nhận Box sẽ sửa được chính biến reference caller.” | Nó sửa được **trạng thái object** qua reference, nhưng không gán lại biến caller qua parameter. |
| “Trong method đã in B,A thì bên ngoài chắc cũng B,A.” | B,A có thể chỉ là giá trị của **hai parameter locals** sau phép gán. |
| “`Box temp=a` tạo Box mới.” | Nó chỉ copy reference; không gọi `new`. |
| “Hoán đổi tên biến parameter giống tên biến caller sẽ sửa caller.” | Hai phạm vi có khai báo biến khác nhau, bất kể tên có giống nhau. |
| “`static` method không swap được, instance method sẽ swap được.” | Cả hai đều nhận arguments theo giá trị; `static` không phải nguyên nhân. |
| “Generic `<T>` làm pass-by-reference.” | Không. Generic chỉ điều chỉnh kiểu/kiểm tra kiểu, không thay semantics truyền tham số. |
| “`Object` khác `Box` về cách truyền tham chiếu.” | Đều copy reference values; khác nhau về kiểu tĩnh và phương thức sẵn có. |
| “Gán `a = b` trong callee sẽ thay đổi field của Box a.” | Không, nó chỉ thay giá trị biến reference `a`. |
| “Nếu mutate rồi swap local thì toàn bộ kết quả sẽ bị mất.” | Mutations lên objects đã xảy ra có thể được caller thấy; chỉ việc rebind local parameter không ảnh hưởng caller variables. |
| “`swapAt(items,0,1)` đổi hai biến local ban đầu.” | Nó đổi **array entries**, không tự đổi biến local từng được dùng đưa vào mảng. |
| “`Collections.swap` tạo Box mới.” | Nó đổi vị trí các phần tử list; không bắt buộc tạo lại Box objects. |
| “Đổi hai holder fields nghĩa là Java có pass-by-reference.” | Không; method sửa **object fields** qua copied references. |
| “Trả Pair đã đổi là tự sửa biến caller.” | Caller chỉ đổi biến khi **tự gán lại** từ Pair kết quả. |
| “`final Box a` làm Box object immutable.” | `final` hạn chế gán lại biến/field reference; trạng thái Box có thể vẫn mutable. |
| “`null` không thể xuất hiện trong method swap reference.” | Có thể truyền null cho reference parameters; lỗi chỉ xảy ra nếu dereference null hoặc vi phạm điều kiện khác. |
| “Hai biến cùng object rồi swap sẽ chứng minh được tính đúng.” | Khi hai references giống nhau, swap không đổi identity; cần test hai objects độc lập. |
| “Muốn swap threadsafe chỉ cần AtomicReference cho mỗi field.” | Hai thao tác trên hai AtomicReference riêng không mặc định là một transaction atomic. |

## 21. Checklist debug ví dụ swap references

Khi gặp một đoạn Java có vẻ hoán đổi object references, làm tuần tự:

1. **Xác định nơi lưu reference cần hoán đổi**: local variables, array elements, list positions, instance fields hay holder fields?
2. **Đếm các object riêng**: có bao nhiêu lần `new`, factory reuse hay aliases? Cẩn thận nếu hai biến từ đầu đã cùng object.
3. **Phân biệt biến caller và parameter callee**: vẽ riêng hai hàng cho chúng.
4. **Truy vết parameter binding ngay khi gọi**: `a` nhận *copy* reference của argument 1; `b` nhận *copy* reference của argument 2.
5. **Xem từng phép gán có đích ở đâu**: `a = b` đổi parameter; `a.field = x` đổi object; `array[0] = b` đổi array entry.
6. **Nếu thân method không ghi lại vào container/field của caller và không trả giá trị được caller gán**, các local reference variables ở caller không tự đổi.
7. **Kiểm tra cả identity `==` và nội dung field**: đôi khi object data bị sửa khiến chương trình in trông như hoán đổi thành công.
8. **Nếu giải pháp dùng return pair**, caller phải gán các results trở lại vị trí lưu mong muốn.
9. **Nếu giải pháp dùng mutable container**, bảo đảm quyền sửa, phạm vi chỉ số, contract null và thread safety khi cần.
10. **Nếu code có side effects trong argument expressions**, xét thứ tự đánh giá để không nhầm thay đổi trước lời gọi với tác động của method.

## 22. Bài tập tự kiểm tra

**Câu 1.** Hai biến `Box a`, `Box b` trỏ hai objects A/B. Method `swap(Box x,Box y)` gán `Box t=x; x=y; y=t;`. Sau lời gọi `swap(a,b)`, a/b trỏ đâu?  
**Đáp án:** a vẫn A, b vẫn B. Chỉ parameter x/y của method được đảo.

**Câu 2.** Vì sao `x=y` trong `swap` không gán lại `a` ở caller?  
**Đáp án:** x là một **parameter variable khác** đã nhận bản sao reference của đối số; Java không cho x là alias của vị trí lưu biến a.

**Câu 3.** Nếu gọi `swap(a,b)` khi a và b vốn cùng trỏ Box A, điều gì xảy ra ở caller?  
**Đáp án:** Cả hai vẫn trỏ A. Ngay cả swap đúng cũng không làm hai references giống nhau trông khác đi; test này không đủ để chứng minh implementation.

**Câu 4.** Generic `static <T> void swap(T a,T b)` có thể sửa caller variables không?  
**Đáp án:** Không. Generic không thay đổi pass-by-value.

**Câu 5.** `Box[] arr={a,b}; swap(arr[0],arr[1]);` với method chỉ hoán đổi parameter locals có làm array đổi không?  
**Đáp án:** Không. Nó chỉ nhận bản sao hai element references.

**Câu 6.** `swapAt(arr,0,1)` với body ghi `arr[0]` và `arr[1]` có làm array đổi không?  
**Đáp án:** Có. Method nhận reference tới cùng array object, rồi sửa **array elements**.

**Câu 7.** Sau `swapAt(arr,0,1)`, hai local variables a và b (từng dùng tạo mảng) cũng tự đổi chỗ không?  
**Đáp án:** Không. Muốn đổi hai local variables, caller phải gán lại từ array hoặc từ kết quả khác.

**Câu 8.** Với hai `Holder<Box>` độc lập, method gán lại `left.value` và `right.value` có làm holder objects của caller đổi nội dung không?  
**Đáp án:** Có, nếu fields mutable và references hợp lệ. Nhưng các biến caller trỏ holders vẫn không được gán lại.

**Câu 9.** Nếu method swap return `Pair<Box>` chứa (B,A), caller có biến a/b tự đổi không?  
**Đáp án:** Không. Caller phải thực hiện các phép gán `a=result.first(); b=result.second();`.

**Câu 10.** `swap` vừa mutate `a.value`, `b.value` rồi rebind parameters. Caller có thấy mutation không?  
**Đáp án:** Có thể có, vì ban đầu parameters trỏ cùng objects với caller. Việc rebind parameters sau đó không hoàn tác mutations đã xảy ra.

**Câu 11.** `String a="A", b="B"; swap(a,b);` có làm biến string ở caller đổi không?  
**Đáp án:** Không. String vẫn là reference type được truyền theo giá trị. Tính immutable của String không phải lý do chủ yếu khiến swap fail.

**Câu 12.** Tại sao test chỉ in `a.value` và `b.value` có thể không đủ kiểm tra swap references?  
**Đáp án:** Method có thể đổi **nội dung field** thay vì đổi references; cần kiểm tra object identities `==` hoặc những tham chiếu gốc được giữ lại.

**Câu 13.** Một method `void swapFields()` không nhận tham số, nhưng đổi `this.left` và `this.right`. Vì sao caller có thể quan sát đổi chỗ?  
**Đáp án:** Thân method trực tiếp **ghi fields của object**; quy tắc pass-by-value của các arguments không cấm phương thức sửa shared mutable state.

**Câu 14.** Một method dùng hai `AtomicReference` và gọi `get/set` để đổi fields. Điều đó đảm bảo swap hai ô atomic trong đa luồng chưa?  
**Đáp án:** Chưa. Từng thao tác atomic không mặc nhiên làm **cả chuỗi hai ghi** thành một giao dịch atomic; cần đồng bộ hóa phối hợp nếu đó là yêu cầu.

**Câu 15.** Nếu lời gọi là `swap(first=second,second)`, và sau lời gọi first đổi reference, điều đó có chứng minh `swap` sửa biến caller không?  
**Đáp án:** Không. Chính **biểu thức gán first=second trong đối số** đã thay biến caller *trước* khi method bắt đầu.

## Tài liệu tham khảo

- Java Language Specification, [`4.3 — Reference Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.3): reference values và object identity.
- Java Language Specification, [`4.12 — Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12): biến và kiểu biến.
- Java Language Specification, [`8.4.1 — Formal Parameters](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.1): tham số hình thức và khai báo của chúng.
- Java Language Specification, [`15.12.4 — Run-Time Evaluation of Method Invocation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4): đánh giá các đối số trước khi invoke method.
- Java Platform API, [`Collections.swap(List,int,int)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#swap(java.util.List,int,int)): đổi chỗ phần tử trong list.

## Ghi nhớ

`swap(a,b)` với phần thân `T t=a; a=b; b=t;` **không thể hoán đổi hai biến tham chiếu của caller**, vì Java truyền **giá trị tham chiếu** vào **parameter variables độc lập**. Sau khi method kết thúc, hai biến caller vẫn giữ giá trị tham chiếu ban đầu. Code trong method có thể hoán đổi **parameters** và in kết quả B,A, nhưng đó không phải bằng chứng đã đổi caller.

Để hoán đổi thật sự, hãy thao tác đúng **nơi lưu references**: đổi hai **array/list entries**, đổi hai **fields của holder objects**, hoặc **trả một Pair mới và để caller tự gán lại**. Đừng lẫn lộn **reassignment của biến tham chiếu** với **mutation của object**, và đừng coi “tham số là object” là ngoại lệ của pass-by-value. Phân biệt ba tầng — **biến**, **giá trị tham chiếu**, **đối tượng** — là chìa khóa để đọc đúng ví dụ swap trong Java.
